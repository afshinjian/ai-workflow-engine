"""PG-01 (Overview), PG-02 (Board), and PG-03 (Task detail) — `UI_SPEC.md` §3."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agentos_dashboard.api.overview import build_overview
from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.services.board import build_board
from agentos_dashboard.services.tasks import build_task_detail

__all__ = ["build_router"]


def build_router(*, cache: SnapshotCache, templates: Jinja2Templates) -> APIRouter:
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

    return router
