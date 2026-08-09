"""The application factory (`ARCHITECTURE.md` §2): wires settings, the snapshot cache, the
security middleware, the JSON API, and the HTML pages into one FastAPI app.

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
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from agentos_dashboard.api.acknowledgments import AcknowledgmentStore
from agentos_dashboard.api.envelope import err
from agentos_dashboard.api.errors import (
    INTERNAL_ERROR_MESSAGE,
    ApiErrorCode,
    DashboardAPIError,
    status_code_for,
)
from agentos_dashboard.api.lock import ExecutionLock
from agentos_dashboard.api.routes import build_router as build_api_router
from agentos_dashboard.api.security import SecurityMiddleware
from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.web.routes import build_router as build_web_router

__all__ = ["WEB_ROOT", "create_app"]

WEB_ROOT = Path(__file__).parent / "web"


def create_app(settings: DashboardSettings, *, lock: ExecutionLock | None = None) -> FastAPI:
    root = RepositoryRoot(path=settings.repo_root)
    cache = SnapshotCache(root)
    acknowledgments = AcknowledgmentStore()

    app = FastAPI(title="AgentOS Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    # Exposed for introspection (tests, `--check`) only; every route closes over `cache`
    # directly rather than reading it back from here.
    app.state.snapshot_cache = cache
    app.add_middleware(SecurityMiddleware, allowed_host_headers=settings.allowed_host_headers)

    app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")
    templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))

    app.include_router(
        build_api_router(
            settings=settings, cache=cache, lock=lock, acknowledgments_store=acknowledgments
        )
    )
    app.include_router(
        build_web_router(cache=cache, templates=templates, acknowledgments_store=acknowledgments)
    )

    _install_exception_handlers(app)
    return app


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DashboardAPIError)
    async def _handle_api_error(request: Request, exc: DashboardAPIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=err(exc.code.value, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code_for(ApiErrorCode.VALIDATION_ERROR),
            content=err(ApiErrorCode.VALIDATION_ERROR.value, str(exc)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ApiErrorCode.NOT_FOUND if exc.status_code == 404 else ApiErrorCode.INTERNAL
        detail = exc.detail if isinstance(exc.detail, str) else code.value
        return JSONResponse(status_code=exc.status_code, content=err(code.value, detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # SC-09: no exception text, no traceback, ever crosses this boundary.
        return JSONResponse(
            status_code=status_code_for(ApiErrorCode.INTERNAL),
            content=err(ApiErrorCode.INTERNAL.value, INTERNAL_ERROR_MESSAGE),
        )
