"""EP-01/EP-02/EP-03/EP-20 (`API_SPEC.md` §2-3): health, snapshot metadata, the Overview
aggregate, and the manual snapshot-rebuild action — the read surface DASH-004 delivers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agentos_dashboard.api.acknowledgments import AcknowledgmentStore
from agentos_dashboard.api.board import board_to_json, task_detail_to_json, workflow_view_to_json
from agentos_dashboard.api.consistency import (
    AcknowledgeRequest,
    acknowledgment_to_json,
    consistency_report_to_json,
)
from agentos_dashboard.api.envelope import ok
from agentos_dashboard.api.errors import ApiErrorCode, DashboardAPIError
from agentos_dashboard.api.git import (
    git_branches_to_json,
    git_commits_to_json,
    git_status_to_json,
    git_tags_to_json,
    upstream_check_to_json,
)
from agentos_dashboard.api.handover import handover_view_to_json
from agentos_dashboard.api.lock import ExecutionLock
from agentos_dashboard.api.overview import build_overview, overview_to_json
from agentos_dashboard.api.snapshot_cache import SnapshotBuildInProgress, SnapshotCache
from agentos_dashboard.core import utc_now
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.services.consistency import run_consistency_checks
from agentos_dashboard.services.git import build_upstream_check
from agentos_dashboard.services.handover import build_handover_view
from agentos_dashboard.services.tasks import build_task_detail
from agentos_dashboard.settings import DashboardSettings

__all__ = ["build_router"]


def _snapshot_payload(snapshot: RepositorySnapshot) -> dict[str, Any]:
    return {
        "head": snapshot.head,
        "generated_at": snapshot.generated_at.isoformat(),
        "fingerprint": snapshot.fingerprint.digest,
        "stale": snapshot.is_stale(),
        "findings": [
            {
                "rule": finding.rule,
                "severity": finding.severity.value,
                "message": finding.message,
                "path": finding.path,
            }
            for finding in snapshot.findings
        ],
    }


def build_router(
    *,
    settings: DashboardSettings,
    cache: SnapshotCache,
    lock: ExecutionLock | None,
    acknowledgments_store: AcknowledgmentStore | None = None,
) -> APIRouter:
    """The `/dash/api/v1` router, closed over this process's cache and lock (no global state)."""
    router = APIRouter(prefix="/dash/api/v1")

    @router.get("/health")
    async def health() -> dict[str, Any]:
        snapshot = cache.get()
        age_seconds = (utc_now() - snapshot.generated_at).total_seconds()
        return ok(
            {
                "status": "ok",
                "locked": lock is not None,
                "lock_path": str(lock.info.path) if lock is not None else None,
                "bind": settings.display_url,
                "snapshot_age_seconds": age_seconds,
            }
        )

    @router.get("/snapshot")
    async def snapshot() -> dict[str, Any]:
        return ok(_snapshot_payload(cache.get()))

    @router.get("/status")
    async def status() -> dict[str, Any]:
        return ok(overview_to_json(build_overview(cache.get())))

    @router.post("/snapshot/refresh")
    async def refresh_snapshot() -> dict[str, Any]:
        try:
            refreshed = cache.refresh()
        except SnapshotBuildInProgress as exc:
            raise DashboardAPIError(
                ApiErrorCode.SNAPSHOT_BUILDING, "a snapshot rebuild is already in progress"
            ) from exc
        return ok(_snapshot_payload(refreshed))

    @router.get("/tasks")
    async def tasks_board(status: str | None = None, program: str | None = None) -> dict[str, Any]:
        return ok(board_to_json(cache.get(), status=status, program=program))

    @router.get("/tasks/{task_id}")
    async def task_detail(task_id: str) -> dict[str, Any]:
        detail = build_task_detail(cache.get(), task_id)
        if detail is None:
            raise DashboardAPIError(ApiErrorCode.NOT_FOUND, f"unknown task id: {task_id!r}")
        return ok(task_detail_to_json(detail))

    @router.get("/workflow")
    async def workflow_view() -> dict[str, Any]:
        return ok(workflow_view_to_json(cache.get()))

    @router.get("/git/status")
    async def git_status() -> dict[str, Any]:
        return ok(git_status_to_json(cache.get()))

    @router.get("/git/commits")
    async def git_commits() -> dict[str, Any]:
        return ok(git_commits_to_json(cache.get()))

    @router.get("/git/branches")
    async def git_branches() -> dict[str, Any]:
        return ok(git_branches_to_json(cache.get()))

    @router.get("/git/tags")
    async def git_tags() -> dict[str, Any]:
        return ok(git_tags_to_json(cache.get()))

    @router.get("/git/upstream")
    async def git_upstream() -> dict[str, Any]:
        return ok(upstream_check_to_json(build_upstream_check(cache.get())))

    @router.get("/handover")
    async def handover() -> dict[str, Any]:
        return ok(handover_view_to_json(build_handover_view(cache.get())))

    @router.get("/consistency")
    async def consistency() -> dict[str, Any]:
        report = run_consistency_checks(cache.get().root)
        acknowledgments = acknowledgments_store.all() if acknowledgments_store else ()
        return ok(consistency_report_to_json(report, acknowledgments))

    @router.post("/consistency/acknowledge")
    async def acknowledge_consistency_finding(payload: AcknowledgeRequest) -> dict[str, Any]:
        if acknowledgments_store is None:
            raise DashboardAPIError(ApiErrorCode.INTERNAL, "acknowledgment store is not configured")
        record = acknowledgments_store.add(fingerprint=payload.fingerprint, note=payload.note)
        return ok(acknowledgment_to_json(record))

    return router
