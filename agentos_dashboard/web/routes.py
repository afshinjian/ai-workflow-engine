"""PG-01 — the Overview page (`UI_SPEC.md` §3): the one HTML page DASH-004 delivers."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agentos_dashboard.api.overview import build_overview
from agentos_dashboard.api.snapshot_cache import SnapshotCache

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
            {"overview": overview, "snapshot": snapshot},
        )

    return router
