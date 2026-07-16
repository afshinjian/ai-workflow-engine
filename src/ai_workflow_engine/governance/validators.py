from collections import defaultdict

from ai_workflow_engine.config import repository_path
from ai_workflow_engine.governance.models import TaskSnapshot, TaskStatus
from ai_workflow_engine.governance.parser import extract_fact, parse_tasks
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.result import CheckResult, Finding, Status


def task_snapshot(config: EngineConfig) -> TaskSnapshot:
    by_source = {}
    for relative in config.governance.document_paths():
        text = repository_path(config.project.repository, relative).read_text(encoding="utf-8")
        by_source[relative] = parse_tasks(text, relative)

    # The configured task queue is authoritative for counts. Other files are mirrors.
    authoritative = by_source[config.governance.task_queue]
    grouped: dict[TaskStatus, list[str]] = defaultdict(list)
    for record in authoritative:
        grouped[record.status].append(record.task_id)
    return TaskSnapshot(
        by_source=by_source,
        current=sorted(grouped[TaskStatus.CURRENT]),
        done=sorted(grouped[TaskStatus.DONE]),
        planned=sorted(grouped[TaskStatus.PLANNED]),
    )


def _task_mirror_findings(
    snapshot: TaskSnapshot, authoritative_path: str, current_mirror_path: str
) -> list[Finding]:
    findings: list[Finding] = []
    authority = {record.task_id: record.status for record in snapshot.by_source[authoritative_path]}
    authority_current = {
        task_id for task_id, status in authority.items() if status == TaskStatus.CURRENT
    }
    mirror_current = {
        record.task_id
        for record in snapshot.by_source[current_mirror_path]
        if record.status == TaskStatus.CURRENT
    }
    if authority_current != mirror_current:
        findings.append(
            Finding(
                code="current_task_mismatch",
                message=(
                    f"Task queue Current set {sorted(authority_current)} differs from "
                    f"current-task mirror {sorted(mirror_current)}"
                ),
                path=current_mirror_path,
            )
        )
    for source, records in snapshot.by_source.items():
        if source == authoritative_path:
            continue
        for record in records:
            expected = authority.get(record.task_id)
            if expected is not None and record.status != expected:
                findings.append(
                    Finding(
                        code="task_state_mismatch",
                        message=(
                            f"{record.task_id} is {record.status} here but {expected} in task queue"
                        ),
                        path=source,
                    )
                )
    return findings


def check_task_state(config: EngineConfig) -> CheckResult:
    snapshot = task_snapshot(config)
    findings = _task_mirror_findings(
        snapshot, config.governance.task_queue, config.governance.current_task
    )
    maximum = config.workflow.maximum_current_tasks
    if len(snapshot.current) > maximum:
        findings.append(
            Finding(
                code="too_many_current_tasks",
                message=f"Found {len(snapshot.current)} Current tasks; maximum is {maximum}",
            )
        )
    evidence = snapshot.model_dump(mode="json")
    evidence["current_count"] = len(snapshot.current)
    evidence["maximum_current_tasks"] = maximum
    return CheckResult(
        check_name="task-state",
        status=Status.FAIL if findings else Status.PASS,
        summary=(
            f"Detected {len(snapshot.current)} Current, {len(snapshot.done)} Done, "
            f"and {len(snapshot.planned)} Planned tasks"
        ),
        findings=findings,
        evidence=evidence,
        affected_paths=sorted({finding.path for finding in findings if finding.path}),
        remediation_hint=(
            "Reconcile task states across configured governance mirrors." if findings else None
        ),
    )


def check_governance(config: EngineConfig) -> CheckResult:
    snapshot = task_snapshot(config)
    findings = _task_mirror_findings(
        snapshot, config.governance.task_queue, config.governance.current_task
    )
    facts: dict[str, dict[str, str | None]] = {}
    for rule in config.governance.facts:
        values: dict[str, str | None] = {}
        for relative in rule.paths:
            text = repository_path(config.project.repository, relative).read_text(encoding="utf-8")
            values[relative] = extract_fact(text, rule.pattern, rule.group)
        facts[rule.name] = values
        present = {value for value in values.values() if value is not None}
        if rule.required and any(value is None for value in values.values()):
            findings.append(
                Finding(
                    code="governance_fact_missing",
                    message=f"Required fact {rule.name!r} is missing",
                )
            )
        if len(present) > 1:
            findings.append(
                Finding(
                    code="governance_fact_mismatch", message=f"Fact {rule.name!r} differs: {values}"
                )
            )
    return CheckResult(
        check_name="governance",
        status=Status.FAIL if findings else Status.PASS,
        summary=(
            "Governance mirrors are consistent"
            if not findings
            else f"Found {len(findings)} governance inconsistency(s)"
        ),
        findings=findings,
        evidence={"facts": facts},
        affected_paths=sorted({finding.path for finding in findings if finding.path}),
        remediation_hint=(
            "Update authoritative governance mirrors to repeat the same facts."
            if findings
            else None
        ),
    )
