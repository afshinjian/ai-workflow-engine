"""DR-010..013: the Overview page's aggregate, built once per request from the cached snapshot
plus the governance documents a snapshot's `stat`-only fingerprint deliberately does not parse.

`RepositorySnapshot` (DASH-002) carries `stat` facts, Git status, and TR-04 unavailability
findings only — it never parses document content. This module supplies Overview's actual
content: the task-queue and project-state parsers and the consistency engine (DASH-003) for
DR-010/DR-011, and the snapshot's own Git status for DR-012. Fields nothing yet populates —
`AuditEvent`s do not exist until DASH-008 builds `dashboard.db` — render as an explicit
healthy-empty state (DR-013) rather than a guess or a silent omission.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.parsing.orchestration import parse_implementation_state
from agentos_dashboard.parsing.project_state import parse_project_state
from agentos_dashboard.parsing.task_queue import parse_task_records
from agentos_dashboard.services.consistency import (
    IMPLEMENTATION_STATE_PATH,
    PROJECT_STATE_PATH,
    TASK_QUEUE_PATH,
    ConsistencyFinding,
    run_consistency_checks,
)

__all__ = [
    "NO_CURRENT_TASK_MESSAGE",
    "NO_RECORDED_EVENTS_MESSAGE",
    "GitOverview",
    "OverviewData",
    "TaskCounts",
    "build_overview",
    "overview_to_json",
]

# DR-013: the contract's own literal healthy-empty text (`DASH-004.md`).
NO_CURRENT_TASK_MESSAGE = "No Current task — expected between authorized tasks"
NO_RECORDED_EVENTS_MESSAGE = (
    "No recorded workflow events yet — the audit trail arrives in a later stage"
)


@dataclass(frozen=True)
class TaskCounts:
    current: int
    planned: int
    done: int


@dataclass(frozen=True)
class GitOverview:
    head: str | None
    branch: str | None
    detached: bool
    upstream: str | None
    ahead: int | None
    behind: int | None
    clean: bool


@dataclass(frozen=True)
class OverviewData:
    """DR-010..013's aggregate: everything the Overview page (PG-01) and `GET /status` render."""

    version: str | None
    summary: str | None
    current_task_id: str | None
    current_task_summary: str
    task_counts: TaskCounts
    blockers: tuple[str, ...]
    orch_blockers: tuple[str, ...]
    git: GitOverview | None
    consistency_findings: tuple[ConsistencyFinding, ...]
    last_event_summary: str
    stale: bool


def _read_or_none(root: RepositoryRoot, relative: str) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError):
        return None


def _task_summary(detail_text: str) -> str:
    stripped = detail_text.strip()
    if not stripped:
        return ""
    return stripped.splitlines()[0].lstrip("#").strip()


def build_overview(snapshot: RepositorySnapshot) -> OverviewData:
    """Build one `OverviewData` from `snapshot`'s root.

    Never raises for repository content, mirroring `build_snapshot`/`run_consistency_checks`'s
    own SC-34 discipline: every document this function reads degrades to `None`/empty on any
    read or parse failure rather than propagating an exception to a page render.
    """
    root = snapshot.root

    project_state_text = _read_or_none(root, PROJECT_STATE_PATH)
    project_state = (
        parse_project_state(project_state_text, PROJECT_STATE_PATH).value
        if project_state_text is not None
        else None
    )

    queue_text = _read_or_none(root, TASK_QUEUE_PATH)
    records = (
        parse_task_records(queue_text, TASK_QUEUE_PATH).value if queue_text is not None else None
    ) or ()

    current = [record for record in records if record.status is TaskStatus.CURRENT]
    counts = TaskCounts(
        current=len(current),
        planned=sum(1 for record in records if record.status is TaskStatus.PLANNED),
        done=sum(1 for record in records if record.status is TaskStatus.DONE),
    )
    current_task_id = current[0].task_id if current else None
    current_task_summary = (
        _task_summary(current[0].detail_text) if current else NO_CURRENT_TASK_MESSAGE
    )

    orch_text = _read_or_none(root, IMPLEMENTATION_STATE_PATH)
    orch_view = (
        parse_implementation_state(orch_text, IMPLEMENTATION_STATE_PATH).value
        if orch_text is not None
        else None
    )
    orch_blockers = (
        tuple(blocker for stage in orch_view.stages for blocker in stage.blockers)
        if orch_view is not None
        else ()
    )

    git: GitOverview | None = None
    if snapshot.git_status is not None:
        status = snapshot.git_status
        git = GitOverview(
            head=status.head,
            branch=redact_secrets(status.branch) if status.branch is not None else None,
            detached=status.detached,
            upstream=redact_secrets(status.upstream) if status.upstream is not None else None,
            ahead=status.ahead,
            behind=status.behind,
            clean=status.clean,
        )

    consistency = run_consistency_checks(root)

    return OverviewData(
        version=project_state.version_fact if project_state is not None else None,
        summary=(
            redact_secrets(project_state.summary)
            if project_state is not None and project_state.summary is not None
            else None
        ),
        current_task_id=current_task_id,
        current_task_summary=redact_secrets(current_task_summary),
        task_counts=counts,
        blockers=(
            tuple(redact_secrets(entry.text) for entry in project_state.blockers)
            if project_state
            else ()
        ),
        orch_blockers=tuple(redact_secrets(blocker) for blocker in orch_blockers),
        git=git,
        consistency_findings=consistency.findings,
        last_event_summary=NO_RECORDED_EVENTS_MESSAGE,
        stale=snapshot.is_stale(),
    )


def overview_to_json(data: OverviewData) -> dict[str, Any]:
    """The JSON-safe form of `OverviewData`, for `GET /dash/api/v1/status`."""
    return {
        "version": data.version,
        "summary": data.summary,
        "current_task_id": data.current_task_id,
        "current_task_summary": data.current_task_summary,
        "task_counts": asdict(data.task_counts),
        "blockers": list(data.blockers),
        "orch_blockers": list(data.orch_blockers),
        "git": asdict(data.git) if data.git is not None else None,
        "consistency_findings": [
            {
                "rule": finding.rule,
                "severity": finding.severity.value,
                "message": finding.message,
                "sources": list(finding.sources),
            }
            for finding in data.consistency_findings
        ],
        "last_event_summary": data.last_event_summary,
        "stale": data.stale,
    }
