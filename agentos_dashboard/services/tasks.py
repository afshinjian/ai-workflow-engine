"""DR-030..033 (`PRODUCT_SPEC.md`): the task detail view — the full recorded task record,
lifecycle history parsed from queue prose plus, where present, the engine's persisted Legacy
workflow events (DR-031, `OPEN_QUESTIONS.md` OD-D12 resolved — see `services.legacy_workflow`'s
module docstring), Git provenance badges (DR-032), and links to related documents (DR-033).

`docs/TASK_QUEUE.md` prose has no uniform per-field structure (`parsing.task_queue`'s module
docstring), so every field below is an honestly-labeled, tolerant extraction over the recorded
prose rather than a claim of independently-verified structure:

* **Recorded scope** is the task's raw recorded prose verbatim (`TaskRecord.detail_text`) —
  the queue's own account of what the task is/was, not a sub-parsed "scope" distinct from it.
* **Acceptance-criteria checklist** splits that prose into clauses (`services._prose`); each
  clause becomes one checklist line, and every line's checked state is the task's own overall
  recorded status (Done -> checked) — a single derived signal, not independent per-item
  verification, and labeled as such wherever it renders.
* **Validation / rollback / documentation notes** are the clauses that happen to mention the
  relevant keywords — again labeled "as recorded", present only "where recorded" (DR-030), an
  empty result being a legitimate, correctly-parsed state rather than a defect.
* A DASH-family task additionally gets a `StageContractRef` pointing at its own
  `stage-prompts/DASH-0XX.md` contract, which *does* carry a structured `**Allowed**:` field —
  the one case where "allowed/forbidden files" (DR-030) has a genuinely authoritative source
  beyond the queue's narrative summary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.parsing.task_queue import parse_task_records
from agentos_dashboard.services._prose import (
    DocRef,
    ResolvedCommit,
    extract_commit_references,
    extract_doc_references,
    extract_task_references,
    split_into_clauses,
)
from agentos_dashboard.services.consistency import (
    TASK_QUEUE_PATH,
    ConsistencyFinding,
    run_consistency_checks,
)
from agentos_dashboard.services.legacy_workflow import (
    LegacyWorkflowProjection,
    load_legacy_workflow,
)

__all__ = [
    "AcceptanceItem",
    "LifecycleEvent",
    "StageContractRef",
    "TaskDetail",
    "build_task_detail",
]

_DASH_STAGE_ID = re.compile(r"\ADASH-\d+\Z")
# Matches both the common `**Allowed**:` field and DASH-001's older `**Allowed files
# (create)**:`/`**Allowed files (modify)**:` variant; only the first occurrence is captured.
_ALLOWED_FIELD = re.compile(r"\*\*Allowed[^*\n]*\*\*:\s*(.+?)(?:\n\n|\Z)", re.DOTALL)

_REVIEW_VERDICT = re.compile(
    r"(?:round-\d+\s+)?(?:independent\s+)?[a-z][a-z -]*?review\s+(APPROVED|REJECTED)",
    re.IGNORECASE,
)
_DATE_TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}")
_MILESTONE_KEYWORDS = re.compile(r"\b(completed|closed|authorized)\b", re.IGNORECASE)
_MERGE_KEYWORDS = re.compile(r"\bmerged\b", re.IGNORECASE)
_VALIDATION_KEYWORDS = re.compile(
    r"\b(tests?|suite|pytest|mypy|ruff|pre-commit|lint|coverage|green|validated|validation)\b",
    re.IGNORECASE,
)
_ROLLBACK_KEYWORDS = re.compile(r"\b(rollback|roll[ -]back|revert(?:ed)?)\b", re.IGNORECASE)
_DOCUMENTATION_KEYWORDS = re.compile(r"\b(document(?:ed|ation)?|changelog|readme)\b", re.IGNORECASE)


@dataclass(frozen=True)
class AcceptanceItem:
    text: str
    done: bool


@dataclass(frozen=True)
class LifecycleEvent:
    """One clause of queue prose recognizable as a lifecycle milestone (DR-031)."""

    kind: str  # "review" | "milestone" | "merge"
    text: str


@dataclass(frozen=True)
class StageContractRef:
    """A DASH-family task's own `stage-prompts/DASH-0XX.md` contract (DR-030/DR-033)."""

    path: str
    allowed_text: str | None


@dataclass(frozen=True)
class TaskDetail:
    task_id: str
    title: str
    status: TaskStatus
    program: str
    source: str
    line: int
    raw_text: str
    referenced_tasks: tuple[str, ...]
    acceptance_items: tuple[AcceptanceItem, ...]
    validation_notes: tuple[str, ...]
    rollback_notes: tuple[str, ...]
    documentation_notes: tuple[str, ...]
    doc_references: tuple[DocRef, ...]
    commit_references: tuple[ResolvedCommit, ...]
    lifecycle_events: tuple[LifecycleEvent, ...]
    stage_contract: StageContractRef | None
    related_findings: tuple[ConsistencyFinding, ...]
    legacy_workflow: LegacyWorkflowProjection


def _title_from_detail(detail_text: str, fallback: str) -> str:
    first_line = detail_text.strip().splitlines()[0] if detail_text.strip() else ""
    return re.sub(r"^[\s—-]+", "", first_line).strip() or fallback


def _keyword_clauses(clauses: tuple[str, ...], pattern: re.Pattern[str]) -> tuple[str, ...]:
    return tuple(clause for clause in clauses if pattern.search(clause))


def _lifecycle_events(clauses: tuple[str, ...]) -> tuple[LifecycleEvent, ...]:
    events: list[LifecycleEvent] = []
    for clause in clauses:
        if _REVIEW_VERDICT.search(clause):
            events.append(LifecycleEvent(kind="review", text=clause))
        elif _MERGE_KEYWORDS.search(clause):
            events.append(LifecycleEvent(kind="merge", text=clause))
        elif _MILESTONE_KEYWORDS.search(clause) and _DATE_TOKEN.search(clause):
            events.append(LifecycleEvent(kind="milestone", text=clause))
    return tuple(events)


def _stage_contract_reference(root: RepositoryRoot, task_id: str) -> StageContractRef | None:
    if not _DASH_STAGE_ID.match(task_id):
        return None
    path = f"docs/agentos-dashboard/stage-prompts/{task_id}.md"
    try:
        content = read_text(root, path).text
    except (FileAccessError, PathRefusedError):
        return None
    match = _ALLOWED_FIELD.search(content)
    allowed_text = redact_secrets(" ".join(match.group(1).split())) if match else None
    return StageContractRef(path=path, allowed_text=allowed_text)


def build_task_detail(snapshot: RepositorySnapshot, task_id: str) -> TaskDetail | None:
    """Build one `TaskDetail`, or `None` if `task_id` is not a recognized `docs/TASK_QUEUE.md`
    record (the API layer turns that into a typed 404; `API_SPEC.md` EP-05)."""
    root = snapshot.root
    try:
        queue_text = read_text(root, TASK_QUEUE_PATH).text
    except (FileAccessError, PathRefusedError):
        return None

    parsed = parse_task_records(queue_text, TASK_QUEUE_PATH)
    records = parsed.value or ()
    normalized = task_id.strip().upper()
    record = next((r for r in records if r.task_id == normalized), None)
    if record is None:
        return None

    clauses = split_into_clauses(record.detail_text)
    report = run_consistency_checks(root)
    related_findings = tuple(
        finding for finding in report.findings if record.task_id in finding.message
    )

    return TaskDetail(
        task_id=record.task_id,
        title=redact_secrets(_title_from_detail(record.detail_text, record.task_id)),
        status=record.status,
        program=record.task_id.split("-", 1)[0],
        source=record.source,
        line=record.line,
        raw_text=redact_secrets(record.detail_text),
        referenced_tasks=extract_task_references(record.detail_text, exclude=record.task_id),
        acceptance_items=tuple(
            AcceptanceItem(text=redact_secrets(clause), done=record.status is TaskStatus.DONE)
            for clause in clauses
        ),
        validation_notes=tuple(
            redact_secrets(value) for value in _keyword_clauses(clauses, _VALIDATION_KEYWORDS)
        ),
        rollback_notes=tuple(
            redact_secrets(value) for value in _keyword_clauses(clauses, _ROLLBACK_KEYWORDS)
        ),
        documentation_notes=tuple(
            redact_secrets(value) for value in _keyword_clauses(clauses, _DOCUMENTATION_KEYWORDS)
        ),
        doc_references=extract_doc_references(root, record.detail_text),
        commit_references=extract_commit_references(root, record.detail_text),
        lifecycle_events=tuple(
            LifecycleEvent(kind=event.kind, text=redact_secrets(event.text))
            for event in _lifecycle_events(clauses)
        ),
        stage_contract=_stage_contract_reference(root, record.task_id),
        related_findings=related_findings,
        legacy_workflow=load_legacy_workflow(root, record.task_id),
    )
