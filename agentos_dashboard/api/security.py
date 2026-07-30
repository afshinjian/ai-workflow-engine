"""One ASGI middleware enforcing the dashboard's request-level security controls.

`SECURITY_MODEL.md` SC-36 (Host allowlist), SC-03 (CSRF double-submit cookie on every
state-changing request), and the response headers SC-04/SC-05 (CSP, no sniffing) and the
no-cache posture `API_SPEC.md` §1 requires of every response, all live in one dispatch path so
their relative order — Host check, then CSRF, then the route, then headers on whatever comes
back — is a single reviewable fact rather than spread across several independently-ordered
middlewares.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from agentos_dashboard.api.envelope import err
from agentos_dashboard.api.errors import ApiErrorCode, status_code_for

__all__ = [
    "CSP_HEADER_VALUE",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "SAFE_METHODS",
    "SecurityMiddleware",
]

CSRF_COOKIE_NAME = "dash_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# SC-05: self-hosted assets only, no inline script execution, no plugins, never framed.
CSP_HEADER_VALUE = (
    "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
)


def _reject(code: ApiErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code_for(code), content=err(code.value, message))


class SecurityMiddleware(BaseHTTPMiddleware):
    """SC-03/SC-04/SC-05/SC-36, applied identically to every request this app serves."""

    def __init__(self, app: ASGIApp, *, allowed_host_headers: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed_host_headers = allowed_host_headers

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host_header = (request.headers.get("host") or "").lower()
        response: Response
        if host_header not in self._allowed_host_headers:
            response = _reject(
                ApiErrorCode.HOST_REJECTED, f"Host header not allowed: {host_header!r}"
            )
        elif request.method not in SAFE_METHODS and not self._csrf_ok(request):
            response = _reject(
                ApiErrorCode.CSRF_REQUIRED,
                "missing or mismatched CSRF token (double-submit cookie + X-CSRF-Token header)",
            )
        else:
            response = await call_next(request)

        self._apply_security_headers(response)
        self._ensure_csrf_cookie(request, response)
        return response

    @staticmethod
    def _csrf_ok(request: Request) -> bool:
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not cookie_token or not header_token:
            return False
        return secrets.compare_digest(cookie_token, header_token)

    @staticmethod
    def _apply_security_headers(response: Response) -> None:
        response.headers["Content-Security-Policy"] = CSP_HEADER_VALUE
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"

    @staticmethod
    def _ensure_csrf_cookie(request: Request, response: Response) -> None:
        """Issue a CSRF token cookie whenever the request did not already carry one.

        Not `httponly`: the double-submit pattern requires the browser-side script that
        performs a POST to read this cookie and echo it back in `X-CSRF-Token`; a same-origin
        attacker who could read it via script could already forge the request another way, and
        SC-05's CSP (`script-src 'self'`) is what actually prevents foreign script execution.
        """
        if CSRF_COOKIE_NAME in request.cookies:
            return
        response.set_cookie(
            CSRF_COOKIE_NAME,
            secrets.token_urlsafe(32),
            httponly=False,
            samesite="strict",
            secure=False,
            path="/",
        )
