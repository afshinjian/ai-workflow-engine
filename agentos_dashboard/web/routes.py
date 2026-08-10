"""PG-01 (Overview), PG-02 (Board), PG-03 (Task detail), PG-05 (Run detail), PG-06 (Evidence),
PG-07 (Git), PG-09 (Handover), PG-10 (Audit), and PG-11 (Consistency) — `UI_SPEC.md` §3."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agentos_dashboard.api.acknowledgments import AcknowledgmentStore, finding_fingerprint
from agentos_dashboard.api.overview import build_overview
from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.api.stages import stage_registry_to_json
from agentos_dashboard.services.audit import TimelineEntry, build_audit_timeline
from agentos_dashboard.services.board import build_board
from agentos_dashboard.services.consistency import run_consistency_checks
from agentos_dashboard.services.evidence import EvidenceView, list_evidence_views
from agentos_dashboard.services.git import build_git_page, build_upstream_check
from agentos_dashboard.services.governance import (
    GovernanceQueryRefused,
    GovernanceQueryTooLong,
    list_governance_documents,
    render_document,
    search_governance,
)
from agentos_dashboard.services.handover import build_handover_view
from agentos_dashboard.services.notes import UserNote, list_notes
from agentos_dashboard.services.runs import StageRunView, get_run, list_runs, to_view
from agentos_dashboard.services.tasks import build_task_detail
from agentos_dashboard.storage.db import DashboardDatabase

__all__ = ["build_router"]


def build_router(
    *,
    cache: SnapshotCache,
    templates: Jinja2Templates,
    acknowledgments_store: AcknowledgmentStore | None = None,
    database: DashboardDatabase | None = None,
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

    @router.get("/stages", response_class=HTMLResponse)
    async def stages_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        registry = stage_registry_to_json(snapshot)
        return templates.TemplateResponse(
            request,
            "stages.html",
            {"registry": registry, "snapshot": snapshot, "active_nav": "stages"},
        )

    @router.get("/governance", response_class=HTMLResponse)
    async def governance_index_page(request: Request, q: str = "") -> HTMLResponse:
        snapshot = cache.get()
        query = q.strip()
        results: tuple[object, ...] = ()
        search_findings: tuple[object, ...] = ()
        query_error: str | None = None
        if query:
            try:
                search = search_governance(snapshot.root, query)
                results = search.results
                search_findings = search.findings
            except GovernanceQueryTooLong:
                query_error = "Query too long — 200 characters maximum."
            except GovernanceQueryRefused:
                query_error = "Traversal-shaped queries are not allowed."
        return templates.TemplateResponse(
            request,
            "governance.html",
            {
                "documents": list_governance_documents(),
                "query": query,
                "results": results,
                "search_findings": search_findings,
                "query_error": query_error,
                "snapshot": snapshot,
                "active_nav": "governance",
            },
        )

    @router.get("/governance/{doc_id}", response_class=HTMLResponse)
    async def governance_doc_page(request: Request, doc_id: str, raw: int = 0) -> HTMLResponse:
        snapshot = cache.get()
        document = render_document(snapshot.root, doc_id)
        return templates.TemplateResponse(
            request,
            "governance_doc.html",
            {
                "document": document,
                "raw": bool(raw),
                "snapshot": snapshot,
                "active_nav": "governance",
            },
            status_code=200 if document is not None else 404,
        )

    @router.get("/runs", response_class=HTMLResponse)
    async def runs_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        runs: list[StageRunView] = []
        if database is not None:
            with database.connection() as conn:
                runs = [to_view(snapshot.root, run) for run in list_runs(conn)]
        return templates.TemplateResponse(
            request, "runs.html", {"runs": runs, "snapshot": snapshot, "active_nav": "runs"}
        )

    @router.get("/runs/{run_uuid}", response_class=HTMLResponse)
    async def run_detail_page(request: Request, run_uuid: str) -> HTMLResponse:
        snapshot = cache.get()
        view: StageRunView | None = None
        notes: tuple[UserNote, ...] = ()
        if database is not None:
            with database.connection() as conn:
                run = get_run(conn, run_uuid)
                view = to_view(snapshot.root, run) if run is not None else None
                notes = list_notes(conn, target_ref=f"run:{run_uuid}")
        return templates.TemplateResponse(
            request,
            "run_detail.html",
            {
                "view": view,
                "notes": notes,
                "requested_run_uuid": run_uuid,
                "snapshot": snapshot,
                "active_nav": "runs",
            },
            status_code=200 if view is not None else 404,
        )

    @router.get("/evidence", response_class=HTMLResponse)
    async def evidence_page(request: Request) -> HTMLResponse:
        snapshot = cache.get()
        views: tuple[EvidenceView, ...] = ()
        if database is not None:
            with database.connection() as conn:
                views = list_evidence_views(snapshot.root, conn)
        return templates.TemplateResponse(
            request,
            "evidence.html",
            {"views": views, "snapshot": snapshot, "active_nav": "evidence"},
        )

    @router.get("/audit", response_class=HTMLResponse)
    async def audit_page(
        request: Request,
        task: str = Query(default="", max_length=64),
        kind: str = Query(default="", max_length=64),
    ) -> HTMLResponse:
        snapshot = cache.get()
        entries: tuple[TimelineEntry, ...] = ()
        if database is not None:
            with database.connection() as conn:
                entries = build_audit_timeline(
                    snapshot.root,
                    conn,
                    task_id=task.strip() or None,
                    kind=kind.strip() or None,
                    audit_log_path=database.audit_log_path,
                )
        return templates.TemplateResponse(
            request,
            "audit.html",
            {
                "entries": entries,
                "task": task,
                "kind": kind,
                "snapshot": snapshot,
                "active_nav": "audit",
            },
        )

    return router
