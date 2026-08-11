"""Consistency engine v1 (`DASH-003.md`).

Reads the repository's governance documents through the read-only adapters
(`agentos_dashboard.core`), parses them with the tolerant parsers in `agentos_dashboard.parsing`,
and cross-checks them against each other and against Git. Every disagreement, degraded parse, or
unreadable document becomes a `ConsistencyFinding` — this module never picks a winner between two
contradictory authoritative records (`SOURCE_OF_TRUTH.md` TR-01) and never raises for repository
content (mirroring `agentos_dashboard.core.snapshot.build_snapshot`'s SC-34 discipline).

Rules implemented, each mirroring a named `SOURCE_OF_TRUTH.md`/`workflowctl` counterpart without
importing it:

* `current_task_mismatch` / `task_state_mismatch` — queue-vs-mirror agreement, mirroring
  `workflowctl check-task-state`.
* `too_many_current_tasks` — the sole-`Current` invariant, `workflow.maximum_current_tasks` in
  `self-governance.yaml` (see `DEFAULT_MAXIMUM_CURRENT_TASKS`).
* `version_fact_missing` / `version_fact_mismatch` — `pyproject.toml` vs
  `docs/PROJECT_STATE.md`, mirroring `workflowctl check-governance`.
* `project_state_task_queue_contradiction` — a task named in `docs/PROJECT_STATE.md`'s
  `## Completed` section that `docs/TASK_QUEUE.md` does not (yet) call `Done`.
* `commit_reference_unresolvable` — every backtick-quoted commit hash named in
  `docs/DECISION_LOG.md` is resolved against Git (`SOURCE_OF_TRUTH.md` TR-07).
* `handover_file_missing` / `handover_size_mismatch` / `handover_checksum_mismatch` — the
  checksum manifest recomputed against the real files, mirroring `workflowctl check-handover`.
  A checksum mismatch *is* this engine's staleness signal for the handover pair: the manifest no
  longer describes the file's current bytes.
* `orchestration_delivery_order_unknown_stage` / `orchestration_current_stage_unknown` /
  `orchestration_next_eligible_unknown` / `orchestration_prerequisite_unknown` — structural
  schema sanity for `docs/implementation/orchestration/implementation-state.yaml` (TR-09).
* `document_missing` / `parse_failed` / `parse_degraded` — a watched document could not be read
  or parsed at all, or was parsed with reduced confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from agentos_dashboard.core import utc_now
from agentos_dashboard.core.files import FileAccessError, digest_file, read_text, stat_file
from agentos_dashboard.core.gitread import GitReadError, resolve_revision
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.parsing.decision_log import DecisionEntry, parse_decision_log
from agentos_dashboard.parsing.handover import ManifestRecord, parse_checksum_manifest
from agentos_dashboard.parsing.models import Confidence, ParsedDocument, TaskStatus
from agentos_dashboard.parsing.orchestration import (
    OrchestrationStateView,
    parse_implementation_state,
)
from agentos_dashboard.parsing.project_state import ProjectStateView, parse_project_state
from agentos_dashboard.parsing.task_queue import TaskRecord, parse_task_records

__all__ = [
    "CURRENT_TASK_PATH",
    "DECISION_LOG_PATH",
    "DEFAULT_MAXIMUM_CURRENT_TASKS",
    "HANDOVER_MANIFEST_PATH",
    "IMPLEMENTATION_STATE_PATH",
    "PROJECT_STATE_PATH",
    "PYPROJECT_PATH",
    "REMAINING_TASKS_PATH",
    "TASK_QUEUE_PATH",
    "ConsistencyFinding",
    "ConsistencyReport",
    "ConsistencySeverity",
    "run_consistency_checks",
]

PROJECT_STATE_PATH = "docs/PROJECT_STATE.md"
TASK_QUEUE_PATH = "docs/TASK_QUEUE.md"
CURRENT_TASK_PATH = "docs/current_task.md"
REMAINING_TASKS_PATH = "docs/remaining_tasks.md"
DECISION_LOG_PATH = "docs/DECISION_LOG.md"
IMPLEMENTATION_STATE_PATH = "docs/implementation/orchestration/implementation-state.yaml"
HANDOVER_MANIFEST_PATH = "handover/PROJECT_CHECKSUM.md"
PYPROJECT_PATH = "pyproject.toml"

# `self-governance.yaml`'s `workflow.maximum_current_tasks` value. This stage's contract names
# five parsers (`docs/PROJECT_STATE.md`, the task queue + mirrors, `docs/DECISION_LOG.md`,
# `implementation-state.yaml`, the handover manifest) and does not include a general
# `self-governance.yaml` config reader, so the invariant is a documented constant here rather
# than parsed — it must be kept equal to that file's configured value by hand.
DEFAULT_MAXIMUM_CURRENT_TASKS = 1

_PYPROJECT_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_VERSION_NUMBER = re.compile(r"\d+\.\d+\.\d+")
_COMMIT_TOKEN = re.compile(r"`([0-9a-f]{7,40})`")


def _source(path: str, line: int | None = None) -> str:
    return f"{path}:{line}" if line is not None else path


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _yaml_key_line(text: str, key: str) -> int:
    match = re.search(rf"^(?:\s*){re.escape(key)}\s*:", text, re.MULTILINE)
    return _line_number(text, match.start()) if match is not None else 1


class ConsistencySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ConsistencyFinding:
    """EN-28: one cross-document disagreement, degraded parse, or unreadable document."""

    rule: str
    severity: ConsistencySeverity
    message: str
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConsistencyReport:
    generated_at: datetime
    findings: tuple[ConsistencyFinding, ...]


def _read_or_finding(
    root: RepositoryRoot, relative: str, findings: list[ConsistencyFinding]
) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError) as exc:
        findings.append(
            ConsistencyFinding(
                rule="document_missing",
                severity=ConsistencySeverity.ERROR,
                message=f"{relative} could not be read: {exc}",
                sources=(relative,),
            )
        )
        return None


def _note_parse_quality(
    parse: ParsedDocument[Any] | None, findings: list[ConsistencyFinding]
) -> None:
    if parse is None:
        return
    if parse.confidence is Confidence.NONE:
        findings.append(
            ConsistencyFinding(
                rule="parse_failed",
                severity=ConsistencySeverity.ERROR,
                message=(
                    f"{parse.source} could not be parsed: "
                    f"{'; '.join(parse.notes) or 'no recognizable structure'}"
                ),
                sources=(parse.source,),
            )
        )
    elif parse.confidence is Confidence.LOW:
        findings.append(
            ConsistencyFinding(
                rule="parse_degraded",
                severity=ConsistencySeverity.WARNING,
                message=f"{parse.source} parsed with degraded confidence: {'; '.join(parse.notes)}",
                sources=(parse.source,),
            )
        )


def _status_map(parse: ParsedDocument[tuple[TaskRecord, ...]] | None) -> dict[str, TaskStatus]:
    if parse is None or parse.value is None:
        return {}
    return {record.task_id: record.status for record in parse.value}


def _record_map(parse: ParsedDocument[tuple[TaskRecord, ...]] | None) -> dict[str, TaskRecord]:
    if parse is None or parse.value is None:
        return {}
    return {record.task_id: record for record in parse.value}


def _current_set(parse: ParsedDocument[tuple[TaskRecord, ...]] | None) -> set[str]:
    return {
        task_id for task_id, status in _status_map(parse).items() if status is TaskStatus.CURRENT
    }


def _check_task_mirrors(
    queue_parse: ParsedDocument[tuple[TaskRecord, ...]],
    current_parse: ParsedDocument[tuple[TaskRecord, ...]] | None,
    remaining_parse: ParsedDocument[tuple[TaskRecord, ...]] | None,
    findings: list[ConsistencyFinding],
) -> None:
    """Mirrors `check_task_state`'s `_task_mirror_findings`: the queue is authoritative, and
    only `docs/current_task.md` is required to hold the *exact* Current set (`remaining_tasks.md`
    legitimately mirrors Current+Planned, so it is checked per-record only, same as the engine)."""
    authority = _status_map(queue_parse)
    authority_records = _record_map(queue_parse)
    authority_current = {tid for tid, status in authority.items() if status is TaskStatus.CURRENT}

    if current_parse is not None and current_parse.value is not None:
        mirror_current = _current_set(current_parse)
        if authority_current != mirror_current:
            findings.append(
                ConsistencyFinding(
                    rule="current_task_mismatch",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"Task queue Current set {sorted(authority_current)} differs from "
                        f"{CURRENT_TASK_PATH} {sorted(mirror_current)}"
                    ),
                    sources=tuple(
                        dict.fromkeys(
                            (
                                *(
                                    _source(record.source, record.line)
                                    for record in queue_parse.value or ()
                                    if record.status is TaskStatus.CURRENT
                                ),
                                *(
                                    _source(record.source, record.line)
                                    for record in current_parse.value
                                    if record.status is TaskStatus.CURRENT
                                ),
                            )
                        )
                    )
                    or (TASK_QUEUE_PATH, CURRENT_TASK_PATH),
                )
            )

    for mirror_parse in (current_parse, remaining_parse):
        if mirror_parse is None or mirror_parse.value is None:
            continue
        for record in mirror_parse.value:
            expected = authority.get(record.task_id)
            if expected is not None and record.status is not expected:
                findings.append(
                    ConsistencyFinding(
                        rule="task_state_mismatch",
                        severity=ConsistencySeverity.ERROR,
                        message=(
                            f"{record.task_id} is {record.status} in {mirror_parse.source} but "
                            f"{expected} in {TASK_QUEUE_PATH}"
                        ),
                        sources=(
                            _source(
                                TASK_QUEUE_PATH,
                                authority_records[record.task_id].line,
                            ),
                            _source(record.source, record.line),
                        ),
                    )
                )


def _check_sole_current(
    queue_parse: ParsedDocument[tuple[TaskRecord, ...]], findings: list[ConsistencyFinding]
) -> None:
    current_count = len(_current_set(queue_parse))
    if current_count > DEFAULT_MAXIMUM_CURRENT_TASKS:
        findings.append(
            ConsistencyFinding(
                rule="too_many_current_tasks",
                severity=ConsistencySeverity.ERROR,
                message=(
                    f"Found {current_count} Current tasks; maximum is "
                    f"{DEFAULT_MAXIMUM_CURRENT_TASKS}"
                ),
                sources=tuple(
                    _source(record.source, record.line)
                    for record in queue_parse.value or ()
                    if record.status is TaskStatus.CURRENT
                ),
            )
        )


def _check_version_fact(
    project_state_parse: ParsedDocument[ProjectStateView],
    pyproject_text: str,
    findings: list[ConsistencyFinding],
) -> None:
    view = project_state_parse.value
    pyproject_match = _PYPROJECT_VERSION.search(pyproject_text)
    pyproject_line = (
        _line_number(pyproject_text, pyproject_match.start()) if pyproject_match else None
    )
    pyproject_version = pyproject_match.group(1) if pyproject_match else None
    state_version_raw = view.version_fact if view is not None else None
    state_match = _VERSION_NUMBER.search(state_version_raw) if state_version_raw else None
    state_version = state_match.group(0) if state_match else None

    if pyproject_version is None or state_version is None:
        findings.append(
            ConsistencyFinding(
                rule="version_fact_missing",
                severity=ConsistencySeverity.ERROR,
                message="version fact missing from pyproject.toml or docs/PROJECT_STATE.md",
                sources=(
                    _source(PYPROJECT_PATH, pyproject_line),
                    _source(
                        PROJECT_STATE_PATH,
                        view.version_fact_line if view is not None else None,
                    ),
                ),
            )
        )
        return
    if pyproject_version != state_version:
        findings.append(
            ConsistencyFinding(
                rule="version_fact_mismatch",
                severity=ConsistencySeverity.ERROR,
                message=(
                    f"version differs: {PYPROJECT_PATH}={pyproject_version!r} vs "
                    f"{PROJECT_STATE_PATH}={state_version_raw!r}"
                ),
                sources=(
                    _source(PYPROJECT_PATH, pyproject_line),
                    _source(PROJECT_STATE_PATH, view.version_fact_line if view else None),
                ),
            )
        )


def _check_project_state_vs_task_queue(
    project_state_parse: ParsedDocument[ProjectStateView],
    queue_parse: ParsedDocument[tuple[TaskRecord, ...]],
    findings: list[ConsistencyFinding],
) -> None:
    view = project_state_parse.value
    if view is None:
        return
    authority = _status_map(queue_parse)
    authority_records = _record_map(queue_parse)
    for ref in view.completed_task_refs:
        actual = authority.get(ref.task_id)
        if actual is not None and actual is not TaskStatus.DONE:
            findings.append(
                ConsistencyFinding(
                    rule="project_state_task_queue_contradiction",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"{PROJECT_STATE_PATH}:{ref.line} lists {ref.task_id} under "
                        f"'## Completed' but {TASK_QUEUE_PATH} says {actual}"
                    ),
                    sources=(
                        _source(PROJECT_STATE_PATH, ref.line),
                        _source(TASK_QUEUE_PATH, authority_records[ref.task_id].line),
                    ),
                )
            )


def _check_doc_named_commits(
    root: RepositoryRoot,
    decision_parse: ParsedDocument[tuple[DecisionEntry, ...]],
    findings: list[ConsistencyFinding],
) -> None:
    entries = decision_parse.value
    if entries is None:
        return
    checked: set[str] = set()
    for entry in entries:
        for token in _COMMIT_TOKEN.findall(entry.body):
            if token in checked:
                continue
            checked.add(token)
            try:
                resolve_revision(root.path, token)
            except GitReadError as exc:
                findings.append(
                    ConsistencyFinding(
                        rule="commit_reference_unresolvable",
                        severity=ConsistencySeverity.WARNING,
                        message=(
                            f"commit reference {token!r} named in {decision_parse.source}:"
                            f"{entry.line} could not be resolved: {exc}"
                        ),
                        sources=(_source(decision_parse.source, entry.line),),
                    )
                )


def _check_handover_checksum(
    root: RepositoryRoot,
    manifest_parse: ParsedDocument[tuple[ManifestRecord, ...]],
    findings: list[ConsistencyFinding],
) -> None:
    records = manifest_parse.value
    if records is None:
        return
    for record in records:
        try:
            facts = stat_file(root, record.path)
            actual_digest = digest_file(root, record.path)
        except (FileAccessError, PathRefusedError) as exc:
            findings.append(
                ConsistencyFinding(
                    rule="handover_file_missing",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"{record.path} named in {manifest_parse.source} could not be read: {exc}"
                    ),
                    sources=(_source(manifest_parse.source, record.line), record.path),
                )
            )
            continue
        if facts.size_bytes != record.size:
            findings.append(
                ConsistencyFinding(
                    rule="handover_size_mismatch",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"{record.path}: manifest size {record.size} != actual "
                        f"{facts.size_bytes}"
                    ),
                    sources=(_source(manifest_parse.source, record.line), _source(record.path, 1)),
                )
            )
        if not actual_digest.startswith(record.digest):
            findings.append(
                ConsistencyFinding(
                    rule="handover_checksum_mismatch",
                    severity=ConsistencySeverity.ERROR,
                    message=f"{record.path}: SHA-256 digest does not match {manifest_parse.source}",
                    sources=(_source(manifest_parse.source, record.line), _source(record.path, 1)),
                )
            )


def _check_orchestration_schema(
    orchestration_parse: ParsedDocument[OrchestrationStateView],
    findings: list[ConsistencyFinding],
) -> None:
    view = orchestration_parse.value
    if view is None:
        return
    source = orchestration_parse.source
    stage_ids = {stage.stage_id for stage in view.stages}

    unknown_in_order = [sid for sid in view.delivery_order if sid not in stage_ids]
    if unknown_in_order:
        findings.append(
            ConsistencyFinding(
                rule="orchestration_delivery_order_unknown_stage",
                severity=ConsistencySeverity.ERROR,
                message=f"delivery_order references stage(s) not in 'stages': {unknown_in_order}",
                sources=(
                    _source(source, _yaml_key_line(orchestration_parse.raw_text, "delivery_order")),
                ),
            )
        )
    if view.current_stage is not None and view.current_stage not in stage_ids:
        findings.append(
            ConsistencyFinding(
                rule="orchestration_current_stage_unknown",
                severity=ConsistencySeverity.ERROR,
                message=f"current_stage {view.current_stage!r} is not a known stage",
                sources=(
                    _source(source, _yaml_key_line(orchestration_parse.raw_text, "current_stage")),
                ),
            )
        )
    if view.next_eligible_stage is not None and view.next_eligible_stage not in stage_ids:
        findings.append(
            ConsistencyFinding(
                rule="orchestration_next_eligible_unknown",
                severity=ConsistencySeverity.ERROR,
                message=f"next_eligible_stage {view.next_eligible_stage!r} is not a known stage",
                sources=(
                    _source(
                        source, _yaml_key_line(orchestration_parse.raw_text, "next_eligible_stage")
                    ),
                ),
            )
        )
    for stage in view.stages:
        unknown_prereqs = [p for p in stage.prerequisites if p not in stage_ids]
        if unknown_prereqs:
            findings.append(
                ConsistencyFinding(
                    rule="orchestration_prerequisite_unknown",
                    severity=ConsistencySeverity.WARNING,
                    message=f"{stage.stage_id} lists unknown prerequisite(s): {unknown_prereqs}",
                    sources=(_source(stage.source, stage.line),),
                )
            )


def run_consistency_checks(root: RepositoryRoot) -> ConsistencyReport:
    """Read, parse, and cross-check every document this engine knows about.

    Never raises for repository content: an unreadable or unparsable document becomes a
    `document_missing`/`parse_failed` finding and every check that depends on it is skipped,
    exactly as a missing watched file degrades `agentos_dashboard.core.snapshot.build_snapshot`
    rather than aborting it.
    """
    findings: list[ConsistencyFinding] = []

    queue_text = _read_or_finding(root, TASK_QUEUE_PATH, findings)
    current_text = _read_or_finding(root, CURRENT_TASK_PATH, findings)
    remaining_text = _read_or_finding(root, REMAINING_TASKS_PATH, findings)
    project_state_text = _read_or_finding(root, PROJECT_STATE_PATH, findings)
    pyproject_text = _read_or_finding(root, PYPROJECT_PATH, findings)
    decision_log_text = _read_or_finding(root, DECISION_LOG_PATH, findings)
    orchestration_text = _read_or_finding(root, IMPLEMENTATION_STATE_PATH, findings)
    manifest_text = _read_or_finding(root, HANDOVER_MANIFEST_PATH, findings)

    queue_parse = (
        parse_task_records(queue_text, TASK_QUEUE_PATH) if queue_text is not None else None
    )
    current_parse = (
        parse_task_records(current_text, CURRENT_TASK_PATH, recognize_empty_current=True)
        if current_text is not None
        else None
    )
    remaining_parse = (
        parse_task_records(remaining_text, REMAINING_TASKS_PATH)
        if remaining_text is not None
        else None
    )
    project_state_parse = (
        parse_project_state(project_state_text, PROJECT_STATE_PATH)
        if project_state_text is not None
        else None
    )
    decision_parse = (
        parse_decision_log(decision_log_text, DECISION_LOG_PATH)
        if decision_log_text is not None
        else None
    )
    orchestration_parse = (
        parse_implementation_state(orchestration_text, IMPLEMENTATION_STATE_PATH)
        if orchestration_text is not None
        else None
    )
    manifest_parse = (
        parse_checksum_manifest(manifest_text, HANDOVER_MANIFEST_PATH)
        if manifest_text is not None
        else None
    )

    for parse in (
        queue_parse,
        current_parse,
        remaining_parse,
        project_state_parse,
        decision_parse,
        orchestration_parse,
        manifest_parse,
    ):
        _note_parse_quality(parse, findings)

    if queue_parse is not None and queue_parse.value is not None:
        _check_task_mirrors(queue_parse, current_parse, remaining_parse, findings)
        _check_sole_current(queue_parse, findings)
        if project_state_parse is not None:
            _check_project_state_vs_task_queue(project_state_parse, queue_parse, findings)

    if project_state_parse is not None and pyproject_text is not None:
        _check_version_fact(project_state_parse, pyproject_text, findings)

    if decision_parse is not None:
        _check_doc_named_commits(root, decision_parse, findings)

    if manifest_parse is not None:
        _check_handover_checksum(root, manifest_parse, findings)

    if orchestration_parse is not None:
        _check_orchestration_schema(orchestration_parse, findings)

    # Findings are display objects. Keep all comparisons above byte-faithful, then redact only
    # their human-readable messages at the return boundary (DD-17/SC-09).
    return ConsistencyReport(
        generated_at=utc_now(),
        findings=tuple(
            ConsistencyFinding(
                rule=finding.rule,
                severity=finding.severity,
                message=redact_secrets(finding.message),
                sources=finding.sources,
            )
            for finding in findings
        ),
    )
