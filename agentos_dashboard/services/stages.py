"""DR-040..043 (`PRODUCT_SPEC.md`): the stage registry loader and the precondition engine that
gates prompt generation (`services.prompts`).

Reads `docs/agentos-dashboard/STAGE_REGISTRY.md` §3's own Markdown table and cross-checks every
row against `prompt_templates.schema.STAGE_SCHEMA`, a coded, independently-maintained copy of the
same ten stages' identity — any disagreement (title, role, branch, or prompt path drift) becomes
a `ConsistencyFinding` rather than a silently-trusted value (`DASH-007.md` Build: "cross-checked
against a coded schema (divergence = finding)").

The precondition engine evaluates the six named preconditions from the same Build section for
one stage at a time: owner authorization recorded, predecessor `COMPLETE`, clean tree, correct
branch, the sole-active-DASH-stage invariant, and any blocking `OPEN_QUESTIONS.md` entry
resolved. It never mutates anything and never decides on the operator's behalf — `services.
prompts.generate_stage_prompt` is the only caller that turns an unmet precondition into a
refusal.

Never raises for repository content, mirroring every other service in this package (SC-34): a
missing or unparsable document degrades to an itemized finding/failed precondition, never an
exception a page or route would surface as a 500.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.gitread import GitReadError, read_status
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.models import Confidence, TaskStatus
from agentos_dashboard.parsing.task_queue import TaskRecord, parse_task_records
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA, STAGE_SCHEMA_BY_ID, StageSchema
from agentos_dashboard.services.consistency import (
    CURRENT_TASK_PATH,
    DEFAULT_MAXIMUM_CURRENT_TASKS,
    REMAINING_TASKS_PATH,
    TASK_QUEUE_PATH,
    ConsistencyFinding,
    ConsistencySeverity,
)

__all__ = [
    "OPEN_QUESTIONS_PATH",
    "STAGE_REGISTRY_PATH",
    "PreconditionReport",
    "PreconditionResult",
    "RegistryRow",
    "StageRegistryView",
    "build_stage_registry_view",
    "evaluate_preconditions",
]

STAGE_REGISTRY_PATH = "docs/agentos-dashboard/STAGE_REGISTRY.md"
OPEN_QUESTIONS_PATH = "docs/agentos-dashboard/OPEN_QUESTIONS.md"

# Registry states that map to the task queue's `Current` status (`STAGE_REGISTRY.md` §1).
_CURRENT_LIKE_STATES = frozenset(
    {"AUTHORIZED", "IN_PROGRESS", "SELF_REVIEW", "REVIEW", "APPROVAL", "BLOCKED"}
)
_PROMPT_ELIGIBLE_STATES = _CURRENT_LIKE_STATES - {"BLOCKED"}
_KNOWN_REGISTRY_STATES = frozenset(
    {
        "NOT_STARTED",
        "PROPOSED",
        "AUTHORIZED",
        "IN_PROGRESS",
        "SELF_REVIEW",
        "REVIEW",
        "APPROVAL",
        "COMPLETE",
        "BLOCKED",
        "SUPERSEDED",
    }
)

_STAGE_ID_RE = re.compile(r"DASH-\d+")
_ENTRY_HEADING_RE = re.compile(r"^###\s+.*$", re.MULTILINE)
_BLOCKED_FIELD_RE = re.compile(r"-\s*\*\*Blocked:?\*\*\s*(.+)", re.IGNORECASE)
_NONE_OPEN_RE = re.compile(r"none\s+currently\s+open", re.IGNORECASE)
_DASH_TASK_HEADING_RE = re.compile(
    r"^#{2,6}\s+(DASH-\d{3})(?:\s*(?:\u2014|\u2013|--|-(?=\s)|:).*)?\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class RegistryRow:
    """One `STAGE_REGISTRY.md` §3 row, as actually written in the live document."""

    stage_id: str
    title: str
    role: str
    state: str
    branch: str
    prompt_path: str


@dataclass(frozen=True)
class StageRegistryView:
    """EN-10: the coded schema plus the live registry, cross-checked against each other."""

    rows: tuple[RegistryRow, ...]
    findings: tuple[ConsistencyFinding, ...]

    def row_for(self, stage_id: str) -> RegistryRow | None:
        return next((row for row in self.rows if row.stage_id == stage_id), None)


@dataclass(frozen=True)
class PreconditionResult:
    """One named precondition's live pass/fail state, with a human-readable reason (DR-041)."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PreconditionReport:
    stage_id: str
    results: tuple[PreconditionResult, ...]

    @property
    def all_passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def unmet(self) -> tuple[PreconditionResult, ...]:
        return tuple(result for result in self.results if not result.passed)


def _read_or_none(root: RepositoryRoot, relative: str) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError):
        return None


def _strip_code(cell: str) -> str:
    return cell.strip().strip("`").strip()


def _extract_section(text: str, start_heading: str, end_prefix: str) -> str | None:
    """Slice `text` between `start_heading` and the next line starting with `end_prefix`.

    The next-heading search is anchored to a line start (`"\\n" + end_prefix`), never a bare
    substring search: `"## "` is itself a substring of `"### "`, so an unanchored search would
    stop at the first sub-heading inside the section instead of the next real same-level one.
    """
    start = text.find(start_heading)
    if start == -1:
        return None
    start += len(start_heading)
    end = text.find("\n" + end_prefix, start)
    return text[start:] if end == -1 else text[start:end]


def _parse_registry_rows(text: str) -> tuple[tuple[RegistryRow, ...], tuple[str, ...]]:
    section = _extract_section(text, "## 3. Registry", "## 4.")
    if section is None:
        return (), ("registry section is missing",)
    rows: list[RegistryRow] = []
    malformed: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and (cells[0] == "Stage" or all(set(cell) <= {"-", ":"} for cell in cells)):
            continue
        if len(cells) != 6 or not re.fullmatch(r"DASH-\d{3}", cells[0]):
            malformed.append(f"malformed registry table row: {stripped!r}")
            continue
        rows.append(
            RegistryRow(
                stage_id=cells[0],
                title=cells[1],
                role=cells[2],
                state=cells[3],
                branch=_strip_code(cells[4]),
                prompt_path=_strip_code(cells[5]),
            )
        )
    return tuple(rows), tuple(malformed)


def _cross_check_schema(rows: tuple[RegistryRow, ...]) -> tuple[ConsistencyFinding, ...]:
    findings: list[ConsistencyFinding] = []
    grouped: dict[str, list[RegistryRow]] = {}
    for row in rows:
        grouped.setdefault(row.stage_id, []).append(row)

    for stage_id, duplicates in grouped.items():
        if len(duplicates) > 1:
            findings.append(
                ConsistencyFinding(
                    rule="stage_registry_duplicate_row",
                    severity=ConsistencySeverity.ERROR,
                    message=f"{STAGE_REGISTRY_PATH} lists {stage_id!r} more than once",
                    sources=(STAGE_REGISTRY_PATH,),
                )
            )

    actual_order = tuple(row.stage_id for row in rows)
    expected_order = tuple(stage.stage_id for stage in STAGE_SCHEMA)
    if actual_order != expected_order:
        findings.append(
            ConsistencyFinding(
                rule="stage_registry_order_mismatch",
                severity=ConsistencySeverity.ERROR,
                message=(
                    f"registry stage order is {list(actual_order)!r}; expected "
                    f"{list(expected_order)!r}"
                ),
                sources=(STAGE_REGISTRY_PATH,),
            )
        )

    for schema in STAGE_SCHEMA:
        matching = grouped.get(schema.stage_id, [])
        if not matching:
            findings.append(
                ConsistencyFinding(
                    rule="stage_schema_missing_row",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"{schema.stage_id} is in the coded schema but has no row in "
                        f"{STAGE_REGISTRY_PATH}"
                    ),
                    sources=(STAGE_REGISTRY_PATH,),
                )
            )
            continue
        row = matching[0]
        for field_name, schema_value, row_value in (
            ("title", schema.title, row.title),
            ("role", schema.role, row.role),
            ("branch", schema.branch, row.branch),
            ("prompt_path", schema.prompt_path, row.prompt_path),
        ):
            if schema_value != row_value:
                findings.append(
                    ConsistencyFinding(
                        rule="stage_schema_mismatch",
                        severity=ConsistencySeverity.ERROR,
                        message=(
                            f"{schema.stage_id} {field_name}: registry says {row_value!r}, "
                            f"coded schema says {schema_value!r}"
                        ),
                        sources=(STAGE_REGISTRY_PATH,),
                    )
                )

    for row in rows:
        if row.stage_id not in STAGE_SCHEMA_BY_ID:
            findings.append(
                ConsistencyFinding(
                    rule="stage_registry_unknown_row",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"{STAGE_REGISTRY_PATH} lists {row.stage_id!r}, which is not in the "
                        "coded schema"
                    ),
                    sources=(STAGE_REGISTRY_PATH,),
                )
            )
        if row.state not in _KNOWN_REGISTRY_STATES:
            findings.append(
                ConsistencyFinding(
                    rule="stage_registry_unknown_state",
                    severity=ConsistencySeverity.ERROR,
                    message=f"{row.stage_id} has unknown registry state {row.state!r}",
                    sources=(STAGE_REGISTRY_PATH,),
                )
            )
    return tuple(findings)


def build_stage_registry_view(root: RepositoryRoot) -> StageRegistryView:
    """Load the live registry table and cross-check it against the coded schema."""
    text = _read_or_none(root, STAGE_REGISTRY_PATH)
    if text is None:
        return StageRegistryView(
            rows=(),
            findings=(
                ConsistencyFinding(
                    rule="document_missing",
                    severity=ConsistencySeverity.ERROR,
                    message=f"{STAGE_REGISTRY_PATH} could not be read",
                    sources=(STAGE_REGISTRY_PATH,),
                ),
            ),
        )
    rows, malformed = _parse_registry_rows(text)
    if not rows:
        return StageRegistryView(
            rows=(),
            findings=(
                ConsistencyFinding(
                    rule="parse_failed",
                    severity=ConsistencySeverity.ERROR,
                    message=f"no recognizable stage rows found in {STAGE_REGISTRY_PATH}",
                    sources=(STAGE_REGISTRY_PATH,),
                ),
            ),
        )
    malformed_findings = tuple(
        ConsistencyFinding(
            rule="stage_registry_malformed_row",
            severity=ConsistencySeverity.ERROR,
            message=message,
            sources=(STAGE_REGISTRY_PATH,),
        )
        for message in malformed
    )
    return StageRegistryView(rows=rows, findings=malformed_findings + _cross_check_schema(rows))


def _authorization_log_records(text: str | None, stage_id: str) -> bool:
    """Require an explicit Human Owner authorization row in registry section 4.

    Task status alone is lifecycle state, not evidence of who authorized it.  Section 4 is the
    program's append-only authorization authority, so a missing/malformed log fails closed.
    """
    if text is None:
        return False
    section = _extract_section(text, "## 4. Authorization Log", "## 5.")
    if section is None:
        return False
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[1] != stage_id:
            continue
        record = cells[2].lower()
        if "human owner" in record and "authoriz" in record:
            return True
    return False


def _parse_task_mirror(
    root: RepositoryRoot, path: str, *, recognize_empty_current: bool = False
) -> tuple[tuple[TaskRecord, ...], bool]:
    text = _read_or_none(root, path)
    if text is None:
        return (), False
    parsed = parse_task_records(text, path, recognize_empty_current=recognize_empty_current)
    if parsed.confidence is not Confidence.HIGH or parsed.value is None:
        return (), False
    return parsed.value, True


def _prompt_sources_status(root: RepositoryRoot, schema: StageSchema) -> tuple[bool, str]:
    paths = (
        "docs/agentos-dashboard/stage-prompts/README.md",
        f"docs/agentos-dashboard/{schema.prompt_path}",
    )
    texts: list[str] = []
    for path in paths:
        try:
            read = read_text(root, path)
        except (FileAccessError, PathRefusedError):
            return False, f"required prompt source {path} could not be read"
        if read.truncated or read.decoded_with_replacement:
            return False, f"required prompt source {path} is truncated or malformed"
        texts.append(read.text)
    if "## Standard Stage Protocol (SSP)" not in texts[0]:
        return False, "SSP source has no canonical Standard Stage Protocol section"
    if "## Canonical Prompt" not in texts[1]:
        return False, f"{schema.stage_id} source has no canonical prompt section"
    return True, f"tracked SSP and {schema.stage_id} prompt sources are readable and complete"


def _blocking_stage_ids(text: str | None) -> frozenset[str] | Literal["all"]:
    """The stage ids a still-open `OPEN_QUESTIONS.md` entry names as blocked, or the literal
    string `"all"` when an open entry exists but names no specific stage (fail-closed: an
    unattributed blocker is treated as blocking every stage rather than none)."""
    if text is None:
        return "all"
    section = _extract_section(text, "## Open", "## ")
    if section is None:
        return "all"
    stripped = section.strip()
    if not stripped or _NONE_OPEN_RE.search(stripped):
        return frozenset()

    entries = _ENTRY_HEADING_RE.split(section)
    bodies = entries[1:] if len(entries) > 1 else [section]
    blocking: set[str] = set()
    for body in bodies:
        match = _BLOCKED_FIELD_RE.search(body)
        if match is None:
            return "all"
        stage_ids = set(_STAGE_ID_RE.findall(match.group(1)))
        if not stage_ids and not re.search(r"\bnone\b", match.group(1), re.IGNORECASE):
            return "all"
        blocking |= stage_ids
    return frozenset(blocking)


def evaluate_preconditions(
    snapshot: RepositorySnapshot, stage_id: str
) -> PreconditionReport | None:
    """Evaluate the six Build-section preconditions for `stage_id`, or `None` if `stage_id` is
    not one of the ten coded DASH stages."""
    schema: StageSchema | None = STAGE_SCHEMA_BY_ID.get(stage_id)
    if schema is None:
        return None

    root = snapshot.root
    results: list[PreconditionResult] = []

    queue_text = _read_or_none(root, TASK_QUEUE_PATH)
    queue_parse = (
        parse_task_records(queue_text, TASK_QUEUE_PATH) if queue_text is not None else None
    )
    queue_trusted = queue_parse is not None and queue_parse.confidence is Confidence.HIGH
    queue_stage_ids = _DASH_TASK_HEADING_RE.findall(queue_text or "")
    queue_stage_unambiguous = len(queue_stage_ids) == len(set(queue_stage_ids))
    records = (
        queue_parse.value
        if queue_trusted and queue_parse is not None and queue_parse.value is not None
        else ()
    )
    record = next((r for r in records if r.task_id == stage_id), None)

    registry_text = _read_or_none(root, STAGE_REGISTRY_PATH)
    registry_view = build_stage_registry_view(root)
    stage_row = registry_view.row_for(stage_id)
    authorization_logged = _authorization_log_records(registry_text, stage_id)

    results.append(
        PreconditionResult(
            name="owner_authorization_recorded",
            passed=(
                queue_trusted
                and queue_stage_unambiguous
                and record is not None
                and record.status is TaskStatus.CURRENT
                and stage_row is not None
                and stage_row.state in _PROMPT_ELIGIBLE_STATES
                and authorization_logged
            ),
            detail=(
                f"queue_trusted={queue_trusted}; queue_stage_unambiguous="
                f"{queue_stage_unambiguous}; task_status="
                f"{record.status.value if record is not None else 'missing'}; registry_state="
                f"{stage_row.state if stage_row is not None else 'missing'}; "
                f"authorization_log_recorded={authorization_logged}"
            ),
        )
    )

    results.append(
        PreconditionResult(
            name="registry_schema_consistent",
            passed=not registry_view.findings,
            detail=(
                "registry and coded schema agree"
                if not registry_view.findings
                else "; ".join(f.message for f in registry_view.findings)
            ),
        )
    )
    if schema.prerequisite is None:
        predecessor_ok = True
        predecessor_detail = "no predecessor stage"
    else:
        predecessor_row = registry_view.row_for(schema.prerequisite)
        predecessor_ok = predecessor_row is not None and predecessor_row.state == "COMPLETE"
        predecessor_detail = (
            f"{schema.prerequisite} is {predecessor_row.state}"
            if predecessor_row is not None
            else f"{schema.prerequisite} has no row in {STAGE_REGISTRY_PATH}"
        )
    results.append(
        PreconditionResult(
            name="predecessor_complete", passed=predecessor_ok, detail=predecessor_detail
        )
    )

    try:
        status = read_status(root.path)
        clean = status.clean
        branch = status.branch
        tree_detail = "working tree is clean" if clean else "working tree has uncommitted changes"
    except GitReadError as exc:
        clean = False
        branch = None
        tree_detail = f"git status could not be read: {exc.detail}"
    results.append(PreconditionResult(name="clean_tree", passed=clean, detail=tree_detail))

    branch_ok = branch == schema.branch
    results.append(
        PreconditionResult(
            name="correct_branch",
            passed=branch_ok,
            detail=f"current branch is {branch!r}; stage requires {schema.branch!r}",
        )
    )

    current_ids = tuple(r.task_id for r in records if r.status is TaskStatus.CURRENT)
    current_records, current_mirror_ok = _parse_task_mirror(
        root, CURRENT_TASK_PATH, recognize_empty_current=True
    )
    remaining_records, remaining_mirror_ok = _parse_task_mirror(root, REMAINING_TASKS_PATH)
    current_mirror_ids = tuple(r.task_id for r in current_records if r.status is TaskStatus.CURRENT)
    remaining_current_ids = tuple(
        r.task_id for r in remaining_records if r.status is TaskStatus.CURRENT
    )
    registry_active_ids = tuple(
        row.stage_id for row in registry_view.rows if row.state in _CURRENT_LIKE_STATES
    )
    sole_active_ok = (
        queue_trusted
        and current_mirror_ok
        and remaining_mirror_ok
        and current_ids == (stage_id,)
        and current_mirror_ids == (stage_id,)
        and remaining_current_ids == (stage_id,)
        and registry_active_ids == (stage_id,)
        and len(current_ids) <= DEFAULT_MAXIMUM_CURRENT_TASKS
    )
    results.append(
        PreconditionResult(
            name="sole_active_invariant",
            passed=sole_active_ok,
            detail=(
                f"queue={list(current_ids)}; current_mirror={list(current_mirror_ids)}; "
                f"remaining_mirror={list(remaining_current_ids)}; "
                f"registry_active={list(registry_active_ids)}"
            ),
        )
    )

    open_questions_text = _read_or_none(root, OPEN_QUESTIONS_PATH)
    blocking = _blocking_stage_ids(open_questions_text)
    blocked = blocking == "all" or stage_id in blocking
    results.append(
        PreconditionResult(
            name="blocking_open_questions_resolved",
            passed=not blocked,
            detail=(
                f"an unresolved {OPEN_QUESTIONS_PATH} entry blocks {stage_id}"
                if blocked
                else f"no open {OPEN_QUESTIONS_PATH} entry blocks {stage_id}"
            ),
        )
    )

    prompt_sources_ok, prompt_sources_detail = _prompt_sources_status(root, schema)
    results.append(
        PreconditionResult(
            name="prompt_sources_available",
            passed=prompt_sources_ok,
            detail=prompt_sources_detail,
        )
    )

    return PreconditionReport(stage_id=stage_id, results=tuple(results))
