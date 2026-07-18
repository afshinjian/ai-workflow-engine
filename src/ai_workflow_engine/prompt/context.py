"""Normalization and read-only context collection for governed prompts."""

import posixpath
import unicodedata
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath

from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.models import GitStatus
from ai_workflow_engine.git.validators import check_git, matching_paths
from ai_workflow_engine.governance.models import TaskRecord, TaskSnapshot
from ai_workflow_engine.governance.validators import (
    check_governance,
    check_task_state,
    task_snapshot,
)
from ai_workflow_engine.handover.validators import HandoverSource, check_handover
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.models import (
    WORKFLOW_STAGES,
    CanonicalAgentSettings,
    CanonicalCheckResult,
    CanonicalEngineConfig,
    CanonicalFactRule,
    CanonicalFinding,
    CanonicalGitStatus,
    CanonicalGovernanceSettings,
    CanonicalHandoverSettings,
    CanonicalProjectSettings,
    CanonicalProtectedPathsSettings,
    CanonicalTaskRecord,
    CanonicalTaskSnapshot,
    CanonicalWorkflowSettings,
    JsonValue,
    PromptContext,
    WorkflowStage,
    canonicalize_json_value,
)
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.prompt.templates import get_template
from ai_workflow_engine.result import CheckResult, Finding, Status

_STAGES_REQUIRING_ALLOWED_PATHS = frozenset({"implementation", "remediation"})
_STAGES_REQUIRING_FINDINGS = frozenset({"remediation"})


def _has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _nfc_dedupe_sort(values: list[str]) -> list[str]:
    return sorted({_nfc(value) for value in values})


def normalize_text(value: str) -> str:
    """Normalize a task ID or remediation finding per the exact CLI textual algorithm."""
    if _has_surrogate(value):
        raise ValueError("Text must not contain a surrogate code point")
    normalized = unicodedata.normalize("NFC", value)
    collapsed: list[str] = []
    in_run = False
    for character in normalized:
        if character.isspace():
            if not in_run:
                collapsed.append(" ")
                in_run = True
        else:
            collapsed.append(character)
            in_run = False
    result = "".join(collapsed).strip(" ")
    if result == "":
        raise ValueError("Text must not be empty after normalization")
    return result


def normalize_allowed_path(raw: str, *, repository: Path) -> str:
    """Normalize and validate one repository-relative allowed path per the exact algorithm."""
    if _has_surrogate(raw):
        raise ValueError(f"Allowed path must not contain a surrogate code point: {raw!r}")
    normalized_unicode = unicodedata.normalize("NFC", raw)
    if normalized_unicode == "":
        raise ValueError("Allowed path must not be empty")
    if any(character.isspace() for character in normalized_unicode):
        raise ValueError(f"Allowed path must not contain whitespace: {raw!r}")
    if "\\" in normalized_unicode:
        raise ValueError(f"Allowed path must not contain a backslash: {raw!r}")
    if normalized_unicode.startswith("/"):
        raise ValueError(f"Allowed path must not be rooted: {raw!r}")
    windows = PureWindowsPath(normalized_unicode)
    if windows.drive or windows.root:
        raise ValueError(f"Allowed path must not be drive-qualified or rooted: {raw!r}")
    normalized_posix = posixpath.normpath(normalized_unicode)
    if normalized_posix in {"", ".", ".."} or normalized_posix.startswith("../"):
        raise ValueError(f"Allowed path must not escape the repository: {raw!r}")
    root = repository.expanduser().resolve(strict=True)
    candidate = (root / Path(normalized_posix)).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError(f"Allowed path escapes the repository: {raw!r}")
    relative = PurePosixPath(candidate.relative_to(root)).as_posix()
    if relative in {"", ".", ".."} or relative.startswith("../") or relative.startswith("/"):
        raise ValueError(f"Allowed path escapes the repository: {raw!r}")
    return relative


def _safe_check(name: str, operation: Callable[[], CheckResult]) -> CheckResult:
    try:
        return operation()
    except Exception as exc:  # converted into a stable ERROR result
        return CheckResult(
            check_name=name,
            status=Status.ERROR,
            summary=str(exc),
            findings=[Finding(code="check_error", message=str(exc))],
            remediation_hint="Re-run with --debug for diagnostic details.",
        )


def _coerce_enums(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [_coerce_enums(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_enums(item) for key, item in value.items()}
    return value


def _require_type(value: object, expected: type, field: str) -> None:
    if type(value) is not expected:
        raise ValueError(f"{field} must be of type {expected.__name__}, got {type(value).__name__}")


def _require_optional_type(value: object, expected: type, field: str) -> None:
    if value is not None and type(value) is not expected:
        raise ValueError(
            f"{field} must be of type {expected.__name__} or null, got {type(value).__name__}"
        )


def _require_str_list(value: object, field: str) -> None:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f"{field} must be an array of strings")


def _require_exact_keys(
    mapping: object, expected_keys: frozenset[str], field: str
) -> dict[str, object]:
    if type(mapping) is not dict:
        raise ValueError(f"{field} must be a JSON object")
    actual_keys = frozenset(mapping)
    if actual_keys != expected_keys:
        raise ValueError(
            f"{field} evidence keys {sorted(actual_keys)} do not match the exact required "
            f"keys {sorted(expected_keys)}"
        )
    return mapping


_GIT_EVIDENCE_KEYS = frozenset(
    {
        "branch",
        "head",
        "upstream",
        "ahead",
        "behind",
        "modified_files",
        "staged_files",
        "untracked_files",
    }
)


def _validate_git_evidence(evidence: object) -> None:
    mapping = _require_exact_keys(evidence, _GIT_EVIDENCE_KEYS, "git")
    _require_type(mapping["branch"], str, "git.branch")
    _require_type(mapping["head"], str, "git.head")
    _require_optional_type(mapping["upstream"], str, "git.upstream")
    _require_optional_type(mapping["ahead"], int, "git.ahead")
    _require_optional_type(mapping["behind"], int, "git.behind")
    _require_str_list(mapping["modified_files"], "git.modified_files")
    _require_str_list(mapping["staged_files"], "git.staged_files")
    _require_str_list(mapping["untracked_files"], "git.untracked_files")


_TASK_STATE_EVIDENCE_KEYS = frozenset(
    {"by_source", "current", "done", "planned", "current_count", "maximum_current_tasks"}
)
_TASK_RECORD_KEYS = frozenset({"task_id", "status", "source", "line"})
_TASK_STATUSES = frozenset({"Current", "Done", "Planned"})


def _validate_task_record(record: object, field: str) -> None:
    mapping = _require_exact_keys(record, _TASK_RECORD_KEYS, field)
    _require_type(mapping["task_id"], str, f"{field}.task_id")
    _require_type(mapping["status"], str, f"{field}.status")
    if mapping["status"] not in _TASK_STATUSES:
        raise ValueError(f"{field}.status must be one of {sorted(_TASK_STATUSES)}")
    _require_type(mapping["source"], str, f"{field}.source")
    _require_type(mapping["line"], int, f"{field}.line")


def _validate_task_state_evidence(evidence: object) -> None:
    mapping = _require_exact_keys(evidence, _TASK_STATE_EVIDENCE_KEYS, "task-state")
    by_source = mapping["by_source"]
    if type(by_source) is not dict:
        raise ValueError("task-state.by_source must be a JSON object")
    for source_key, records in by_source.items():
        if type(source_key) is not str:
            raise ValueError("task-state.by_source keys must be strings")
        if type(records) is not list:
            raise ValueError("task-state.by_source values must be arrays")
        for record in records:
            _validate_task_record(record, "task-state.by_source[]")
    _require_str_list(mapping["current"], "task-state.current")
    _require_str_list(mapping["done"], "task-state.done")
    _require_str_list(mapping["planned"], "task-state.planned")
    _require_type(mapping["current_count"], int, "task-state.current_count")
    _require_type(mapping["maximum_current_tasks"], int, "task-state.maximum_current_tasks")


def _validate_governance_evidence(evidence: object) -> None:
    mapping = _require_exact_keys(evidence, frozenset({"facts"}), "governance")
    facts = mapping["facts"]
    if type(facts) is not dict:
        raise ValueError("governance.facts must be a JSON object")
    for fact_name, values in facts.items():
        if type(fact_name) is not str:
            raise ValueError("governance.facts keys must be strings")
        if type(values) is not dict:
            raise ValueError(f"governance.facts[{fact_name!r}] must be a JSON object")
        for path_key, value in values.items():
            if type(path_key) is not str:
                raise ValueError("governance.facts[*] keys must be strings")
            if value is not None and type(value) is not str:
                raise ValueError(
                    f"governance.facts[{fact_name!r}][{path_key!r}] must be a string or null"
                )


_HANDOVER_ERROR_KEYS = frozenset({"source", "commit"})
_HANDOVER_FULL_KEYS = frozenset({"source", "commit", "records"})
_HANDOVER_RECORD_KEYS = frozenset(
    {"path", "expected_size", "actual_size", "expected_digest", "actual_digest"}
)


def _validate_handover_record(record: object) -> None:
    mapping = _require_exact_keys(record, _HANDOVER_RECORD_KEYS, "handover.records[]")
    _require_type(mapping["path"], str, "handover.records[].path")
    _require_type(mapping["expected_size"], int, "handover.records[].expected_size")
    _require_type(mapping["actual_size"], int, "handover.records[].actual_size")
    _require_type(mapping["expected_digest"], str, "handover.records[].expected_digest")
    _require_type(mapping["actual_digest"], str, "handover.records[].actual_digest")


def _validate_handover_evidence(evidence: object) -> None:
    if type(evidence) is not dict:
        raise ValueError("handover evidence must be a JSON object")
    keys = frozenset(evidence)
    if keys == _HANDOVER_ERROR_KEYS:
        _require_type(evidence["source"], str, "handover.source")
        _require_type(evidence["commit"], str, "handover.commit")
        return
    if keys == _HANDOVER_FULL_KEYS:
        _require_type(evidence["source"], str, "handover.source")
        _require_type(evidence["commit"], str, "handover.commit")
        records = evidence["records"]
        if type(records) is not list:
            raise ValueError("handover.records must be an array")
        for record in records:
            _validate_handover_record(record)
        return
    raise ValueError(
        f"handover evidence keys {sorted(keys)} match neither the early-error shape "
        f"{sorted(_HANDOVER_ERROR_KEYS)} nor the full shape {sorted(_HANDOVER_FULL_KEYS)}"
    )


_EVIDENCE_VALIDATORS: dict[str, Callable[[object], None]] = {
    "git": _validate_git_evidence,
    "task-state": _validate_task_state_evidence,
    "governance": _validate_governance_evidence,
    "handover": _validate_handover_evidence,
}


def _validate_evidence_schema(check_name: str, evidence: object) -> None:
    # The universal _safe_check exception fallback always carries exactly {} evidence,
    # regardless of check name; every other shape must match that check's exact schema.
    if isinstance(evidence, dict) and len(evidence) == 0:
        return
    validator = _EVIDENCE_VALIDATORS.get(check_name)
    if validator is None:
        raise ValueError(f"No evidence schema is defined for check {check_name!r}")
    validator(evidence)


def _prepare_evidence(check_name: str, raw_evidence: dict[str, object]) -> dict[str, JsonValue]:
    coerced = _coerce_enums(raw_evidence)
    _validate_evidence_schema(check_name, coerced)
    if (
        check_name == "handover"
        and isinstance(coerced, dict)
        and isinstance(coerced.get("records"), list)
    ):
        coerced = dict(coerced)
        coerced["records"] = sorted(
            coerced["records"],
            key=lambda record: (
                record["path"],
                record["expected_size"],
                record["actual_size"],
                record["expected_digest"],
                record["actual_digest"],
            ),
        )
    normalized = canonicalize_json_value(coerced)
    assert isinstance(normalized, dict)
    return normalized


def _canonicalize_check_result(result: CheckResult) -> CanonicalCheckResult:
    findings = sorted(
        (
            CanonicalFinding(
                code=_nfc(finding.code),
                message=_nfc(finding.message),
                severity=_nfc(finding.severity),
                path=_nfc(finding.path) if finding.path is not None else None,
            )
            for finding in result.findings
        ),
        key=lambda finding: (finding.code, finding.path or "", finding.severity, finding.message),
    )
    return CanonicalCheckResult(
        check_name=result.check_name,  # type: ignore[arg-type]
        status=result.status.value,
        summary=_nfc(result.summary),
        findings=findings,
        evidence=_prepare_evidence(result.check_name, result.evidence),
        affected_paths=_nfc_dedupe_sort(result.affected_paths),
        remediation_hint=(
            _nfc(result.remediation_hint) if result.remediation_hint is not None else None
        ),
    )


def _canonicalize_git_status(status: GitStatus) -> CanonicalGitStatus:
    return CanonicalGitStatus(
        branch=_nfc(status.branch),
        head=_nfc(status.head),
        upstream=_nfc(status.upstream) if status.upstream is not None else None,
        ahead=status.ahead,
        behind=status.behind,
        modified_files=_nfc_dedupe_sort(status.modified_files),
        staged_files=_nfc_dedupe_sort(status.staged_files),
        untracked_files=_nfc_dedupe_sort(status.untracked_files),
    )


def _canonicalize_task_record(record: TaskRecord) -> CanonicalTaskRecord:
    return CanonicalTaskRecord(
        task_id=_nfc(record.task_id),
        status=record.status.value,
        source=_nfc(record.source),
        line=record.line,
    )


def _canonicalize_task_snapshot(snapshot: TaskSnapshot) -> CanonicalTaskSnapshot:
    by_source: dict[str, list[CanonicalTaskRecord]] = {}
    for source, records in snapshot.by_source.items():
        canonical_records = sorted(
            (_canonicalize_task_record(record) for record in records),
            key=lambda record: (record.source, record.line, record.task_id, record.status),
        )
        by_source[_nfc(source)] = canonical_records
    return CanonicalTaskSnapshot(
        by_source=by_source,
        current=_nfc_dedupe_sort(snapshot.current),
        done=_nfc_dedupe_sort(snapshot.done),
        planned=_nfc_dedupe_sort(snapshot.planned),
    )


def _fact_rule_sort_key(rule: CanonicalFactRule) -> tuple[str, bytes, str, bytes, bool]:
    return (
        rule.name,
        canonical_json(rule.paths),
        rule.pattern,
        canonical_json(rule.group),
        rule.required,
    )


def _canonicalize_config(config: EngineConfig) -> CanonicalEngineConfig:
    project = config.project
    canonical_project = CanonicalProjectSettings(
        id=_nfc(project.id),
        repository=project.repository.as_posix(),
        default_branch=_nfc(project.default_branch),
        timezone=_nfc(project.timezone),
        require_upstream=project.require_upstream,
        conda_environment=_nfc(project.conda_environment),
    )
    governance = config.governance
    canonical_facts = sorted(
        (
            CanonicalFactRule(
                name=_nfc(rule.name),
                paths=_nfc_dedupe_sort(rule.paths),
                pattern=_nfc(rule.pattern),
                group=rule.group,
                required=rule.required,
            )
            for rule in governance.facts
        ),
        key=_fact_rule_sort_key,
    )
    canonical_governance = CanonicalGovernanceSettings(
        project_state=_nfc(governance.project_state),
        task_queue=_nfc(governance.task_queue),
        current_task=_nfc(governance.current_task),
        remaining_tasks=_nfc(governance.remaining_tasks),
        context=_nfc(governance.context),
        pyproject=_nfc(governance.pyproject),
        facts=canonical_facts,
    )
    handover = config.handover
    canonical_handover = CanonicalHandoverSettings(
        manifest=_nfc(handover.manifest),
        files=_nfc_dedupe_sort(handover.files),
    )
    protected = config.protected_paths
    canonical_protected = CanonicalProtectedPathsSettings(
        never_stage=_nfc_dedupe_sort(protected.never_stage),
        never_commit=_nfc_dedupe_sort(protected.never_commit),
    )
    workflow = config.workflow
    canonical_workflow = CanonicalWorkflowSettings(
        maximum_current_tasks=workflow.maximum_current_tasks,
        require_designer_approval_for_promotion=workflow.require_designer_approval_for_promotion,
        allow_automatic_commit=workflow.allow_automatic_commit,
        allow_automatic_push=workflow.allow_automatic_push,
    )
    canonical_agents = sorted(
        (
            CanonicalAgentSettings(
                name=_nfc(agent.name),
                executable=agent.executable.as_posix(),
                args=[_nfc(arg) for arg in agent.args],
                mode=agent.mode,
                timeout_seconds=agent.timeout_seconds,
                stages=sorted(agent.stages, key=WORKFLOW_STAGES.index),
            )
            for agent in config.agents
        ),
        key=lambda agent: agent.name,
    )
    return CanonicalEngineConfig(
        project=canonical_project,
        governance=canonical_governance,
        handover=canonical_handover,
        protected_paths=canonical_protected,
        workflow=canonical_workflow,
        agents=canonical_agents,
    )


def build_prompt_context(
    config: EngineConfig,
    *,
    stage: WorkflowStage,
    task_id: str,
    allowed_paths: Sequence[str] = (),
    remediation_findings: Sequence[str] = (),
) -> PromptContext:
    if stage in _STAGES_REQUIRING_ALLOWED_PATHS:
        if not allowed_paths:
            raise ValueError(f"Stage {stage!r} requires at least one --allowed-path")
    elif allowed_paths:
        raise ValueError(f"Stage {stage!r} does not accept --allowed-path")

    if stage in _STAGES_REQUIRING_FINDINGS:
        if not remediation_findings:
            raise ValueError(f"Stage {stage!r} requires at least one --finding")
    elif remediation_findings:
        raise ValueError(f"Stage {stage!r} does not accept --finding")

    normalized_task_id = normalize_text(task_id)
    normalized_allowed_paths = sorted(
        {normalize_allowed_path(raw, repository=config.project.repository) for raw in allowed_paths}
    )
    normalized_findings = [normalize_text(raw) for raw in remediation_findings]

    template = get_template(stage)
    canonical_config = _canonicalize_config(config)

    git_status = GitClient(config.project.repository).status()
    canonical_git_status = _canonicalize_git_status(git_status)

    snapshot = task_snapshot(config)
    canonical_snapshot = _canonicalize_task_snapshot(snapshot)

    protected_path_violations = _nfc_dedupe_sort(
        matching_paths(git_status.staged_files, config.protected_paths.never_stage)
        + matching_paths(git_status.staged_files, config.protected_paths.never_commit)
    )

    checks = [
        _canonicalize_check_result(_safe_check("git", lambda: check_git(config))),
        _canonicalize_check_result(_safe_check("task-state", lambda: check_task_state(config))),
        _canonicalize_check_result(_safe_check("governance", lambda: check_governance(config))),
        _canonicalize_check_result(
            _safe_check(
                "handover",
                lambda: check_handover(config, source=HandoverSource.WORKING_TREE, commit="HEAD"),
            )
        ),
    ]

    return PromptContext(
        schema_version="1.1",
        config=canonical_config,
        stage=stage,
        task_id=normalized_task_id,
        template=template,
        git_status=canonical_git_status,
        task_snapshot=canonical_snapshot,
        protected_path_violations=protected_path_violations,
        checks=checks,
        remediation_findings=normalized_findings,
        allowed_paths=normalized_allowed_paths,
    )
