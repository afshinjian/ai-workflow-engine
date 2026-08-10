"""The application factory (`ARCHITECTURE.md` §2): wires settings, the snapshot cache, the
local `dashboard.db` (`storage.db.DashboardDatabase`), the security middleware, the JSON API, and
the HTML pages into one FastAPI app.

`create_app` is the single place that constructs a `FastAPI` instance. `__main__.py` calls it
after acquiring the process lock; tests call it directly with `lock=None`, since a lockfile has
no meaning outside a real running process. The interactive API docs (`/docs`, `/redoc`) are
disabled outright: their default assets load from a CDN, which SC-05's self-hosted-only posture
forbids, and this is a local single-operator tool with no need for them.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agentos_dashboard.api.acknowledgments import AcknowledgmentStore
from agentos_dashboard.api.envelope import err
from agentos_dashboard.api.errors import (
    INTERNAL_ERROR_MESSAGE,
    ApiErrorCode,
    DashboardAPIError,
    status_code_for,
)
from agentos_dashboard.api.lock import ExecutionLock
from agentos_dashboard.api.routes import API_PREFIX
from agentos_dashboard.api.routes import build_router as build_api_router
from agentos_dashboard.api.security import (
    RequestBodyLimitMiddleware,
    SecurityMiddleware,
    apply_security_headers,
    ensure_csrf_cookie,
)
from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.services.prompts import PromptAuditLog, PromptStore
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.storage.db import DashboardDatabase, IdempotencyConflict
from agentos_dashboard.web.routes import build_router as build_web_router

__all__ = ["WEB_ROOT", "create_app"]

WEB_ROOT = Path(__file__).parent / "web"


def _unexpected_error_response(
    request: Request, templates: Jinja2Templates
) -> JSONResponse | HTMLResponse:
    """Build the fixed failure response without inspecting the triggering exception."""
    path = request.url.path
    if path == API_PREFIX or path.startswith(f"{API_PREFIX}/"):
        return JSONResponse(
            status_code=status_code_for(ApiErrorCode.INTERNAL),
            content=err(ApiErrorCode.INTERNAL.value, INTERNAL_ERROR_MESSAGE),
        )
    return templates.TemplateResponse(request, "error.html", {"active_nav": None}, status_code=500)


class _UnhandledErrorMiddleware:
    """Contain pre-response route crashes before Uvicorn can log raw exception text."""

    def __init__(self, app: ASGIApp, *, templates: Jinja2Templates) -> None:
        self._app = app
        self._templates = templates

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, receive, tracked_send)
        except Exception:
            # Once headers have been emitted the status cannot safely be replaced. Dashboard
            # routes are bounded, non-streaming responses, so all route failures are caught
            # before this point; retain the protocol-correct fail-fast behavior for a future
            # streaming response rather than emitting a second response start.
            if response_started:
                raise
            response: Response = _unexpected_error_response(Request(scope), self._templates)
            await response(scope, receive, send)


def create_app(settings: DashboardSettings, *, lock: ExecutionLock | None = None) -> FastAPI:
    root = RepositoryRoot(path=settings.repo_root)
    cache = SnapshotCache(root)
    acknowledgments = AcknowledgmentStore()
    prompt_store = PromptStore()
    prompt_audit_log = PromptAuditLog()
    database = DashboardDatabase(settings.repo_root)

    app = FastAPI(title="AgentOS Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    # Exposed for introspection (tests, `--check`) only; every route closes over `cache`
    # directly rather than reading it back from here.
    app.state.snapshot_cache = cache
    app.state.dashboard_database = database
    app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")
    templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))
    # A plain-string filter: Jinja retains its normal autoescaping after redaction. This is used
    # for the one raw snapshot object shared by every base template, never with ``|safe``.
    templates.env.filters["redact_secrets"] = redact_secrets
    # Starlette inserts each middleware at the outer edge. The resulting order is Security ->
    # failure containment -> body limit -> routes. Thus every rejection/failure receives the
    # headers/cookie, body overflow remains typed, and a route exception never reaches Uvicorn's
    # raw exception logger.
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(_UnhandledErrorMiddleware, templates=templates)
    app.add_middleware(SecurityMiddleware, allowed_host_headers=settings.allowed_host_headers)

    app.include_router(
        build_api_router(
            settings=settings,
            cache=cache,
            lock=lock,
            acknowledgments_store=acknowledgments,
            prompt_store=prompt_store,
            prompt_audit_log=prompt_audit_log,
            database=database,
        )
    )
    app.include_router(
        build_web_router(
            cache=cache,
            templates=templates,
            acknowledgments_store=acknowledgments,
            database=database,
        )
    )

    _install_exception_handlers(app, templates)
    return app


def _install_exception_handlers(app: FastAPI, templates: Jinja2Templates) -> None:
    @app.exception_handler(IdempotencyConflict)
    async def _handle_idempotency_conflict(
        request: Request, exc: IdempotencyConflict
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code_for(ApiErrorCode.IDEMPOTENCY_CONFLICT),
            content=err(ApiErrorCode.IDEMPOTENCY_CONFLICT.value, str(exc)),
        )

    @app.exception_handler(DashboardAPIError)
    async def _handle_api_error(request: Request, exc: DashboardAPIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=err(exc.code.value, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code_for(ApiErrorCode.VALIDATION_ERROR),
            # Pydantic's rendered exception can include endpoint reprs and local source paths.
            # The stable envelope needs only the typed failure, never those implementation facts.
            content=err(ApiErrorCode.VALIDATION_ERROR.value, "request validation failed"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code = ApiErrorCode.NOT_FOUND
        elif exc.status_code == 405:
            code = ApiErrorCode.VALIDATION_ERROR
        else:
            code = ApiErrorCode.INTERNAL
        detail = exc.detail if isinstance(exc.detail, str) else code.value
        return JSONResponse(status_code=exc.status_code, content=err(code.value, detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse | HTMLResponse:
        # SC-09: no exception text, no traceback, ever crosses this boundary, on either surface.
        #
        # This handler runs inside `starlette.middleware.errors.ServerErrorMiddleware`, which
        # Starlette always places *outside* `SecurityMiddleware` (`app.add_middleware`) — an
        # unhandled exception unwinds straight past that middleware's `dispatch` without ever
        # reaching its header/CSRF-cookie logic. The response built here must therefore apply
        # both directly, or the one failure path an operator is most likely to hit (a genuine
        # bug) would be the one response missing SC-03/SC-04/SC-05's controls.
        del exc
        response = _unexpected_error_response(request, templates)
        apply_security_headers(response)
        ensure_csrf_cookie(request, response)
        return response
