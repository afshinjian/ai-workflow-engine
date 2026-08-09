"""PG-01 (Overview), PG-02 (Board), PG-03 (Task detail), PG-07 (Git), PG-09 (Handover), and
PG-11 (Consistency) — `UI_SPEC.md` §3."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agentos_dashboard.api.acknowledgments import AcknowledgmentStore, finding_fingerprint
from agentos_dashboard.api.overview import build_overview
from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.services.board import build_board
from agentos_dashboard.services.consistency import run_consistency_checks
from agentos_dashboard.services.git import build_git_page, build_upstream_check
from agentos_dashboard.services.handover import build_handover_view
from agentos_dashboard.services.tasks import build_task_detail

__all__ = ["build_router"]


def build_router(
    *,
    cache: SnapshotCache,
    templates: Jinja2Templates,
    acknowledgments_store: AcknowledgmentStore | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def overview_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        overview = build_overview(snapshot)
        return templates.TemplateResponse(
            request,
            "overview.html",
            {"overview": overview, "snapshot": snapshot, "active_nav": "overview"},
        )

    @router.get("/board", response_class=HTMLResponse)
    async def board_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        board = build_board(snapshot)
        return templates.TemplateResponse(
            request,
            "board.html",
            {"board": board, "snapshot": snapshot, "active_nav": "board"},
        )

    @router.get("/tasks/{task_id}", response_class=HTMLResponse)
    async def task_detail_page(request: Request, task_id: str) -> HTMLResponse:
        snapshot = cache.get()
        detail = build_task_detail(snapshot, task_id)
        return templates.TemplateResponse(
            request,
            "task_detail.html",
            {
                "detail": detail,
                "requested_task_id": task_id,
                "snapshot": snapshot,
                "active_nav": "board",
            },
            status_code=200 if detail is not None else 404,
        )

    @router.get("/git", response_class=HTMLResponse)
    async def git_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        git_data = build_git_page(snapshot)
        upstream = build_upstream_check(snapshot)
        return templates.TemplateResponse(
            request,
            "git.html",
            {
                "git_data": git_data,
                "upstream": upstream,
                "snapshot": snapshot,
                "active_nav": "git",
            },
        )

    @router.get("/handover", response_class=HTMLResponse)
    async def handover_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        handover = build_handover_view(snapshot)
        return templates.TemplateResponse(
            request,
            "handover.html",
            {"handover": handover, "snapshot": snapshot, "active_nav": "handover"},
        )

    @router.get("/consistency", response_class=HTMLResponse)
    async def consistency_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        report = run_consistency_checks(snapshot.root)
        acknowledgments = acknowledgments_store.all() if acknowledgments_store else ()
        rows = [
            {
                "finding": finding,
                "fingerprint": finding_fingerprint(finding),
                "acknowledgments": tuple(
                    a for a in acknowledgments if a.fingerprint == finding_fingerprint(finding)
                ),
            }
            for finding in report.findings
        ]
        return templates.TemplateResponse(
            request,
            "consistency.html",
            {
                "report": report,
                "rows": rows,
                "acknowledgments": acknowledgments,
                "snapshot": snapshot,
                "active_nav": "consistency",
            },
        )

    return router
