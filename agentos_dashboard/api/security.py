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
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agentos_dashboard.api.envelope import err
from agentos_dashboard.api.errors import ApiErrorCode, status_code_for

__all__ = [
    "CSP_HEADER_VALUE",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "MAX_REQUEST_BODY_BYTES",
    "SAFE_METHODS",
    "RequestBodyLimitMiddleware",
    "SecurityMiddleware",
    "apply_security_headers",
    "ensure_csrf_cookie",
]

CSRF_COOKIE_NAME = "dash_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Applied before Starlette/FastAPI buffers JSON or form data. Per-field Pydantic limits are not
# a request-size limit: a client can otherwise send a huge unknown field that validation later
# discards only after consuming memory.
MAX_REQUEST_BODY_BYTES = 1_048_576

# SC-05: self-hosted assets only, no inline script execution, no plugins, never framed.
CSP_HEADER_VALUE = (
    "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
)


def _reject(code: ApiErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code_for(code), content=err(code.value, message))


def apply_security_headers(response: Response) -> None:
    """SC-04/SC-05: the CSP/no-sniff/no-cache headers every response this app sends must carry.

    A module-level function, not only a method on `SecurityMiddleware`, because a response built
    by `main.py`'s top-level `Exception` handler runs inside Starlette's `ServerErrorMiddleware`,
    which always wraps *outside* `SecurityMiddleware` (`app.add_middleware`) in the fixed stack
    order — an unhandled exception unwinds straight past this middleware's `dispatch` and never
    reaches it. That response needs the same headers applied directly, or the one failure path an
    operator is most likely to hit is exactly the one response missing them.
    """
    response.headers["Content-Security-Policy"] = CSP_HEADER_VALUE
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"


def ensure_csrf_cookie(request: Request, response: Response) -> None:
    """Issue a CSRF token cookie whenever the request did not already carry one.

    See `apply_security_headers` for why this must also be reachable outside
    `SecurityMiddleware.dispatch`. Not `httponly`: the double-submit pattern requires the
    browser-side script that performs a POST to read this cookie and echo it back in
    `X-CSRF-Token`; a same-origin attacker who could read it via script could already forge the
    request another way, and SC-05's CSP (`script-src 'self'`) is what actually prevents foreign
    script execution.
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


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject a body over the fixed cap before route code can create partial state."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        content_lengths = [
            value for name, value in scope.get("headers", ()) if name.lower() == b"content-length"
        ]
        if content_lengths:
            try:
                declared = int(content_lengths[-1])
            except ValueError:
                declared = -1
            if declared < 0 or declared > self._max_body_bytes:
                await self._rejection(scope, receive, send)
                return

        consumed = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self._max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await self._rejection(scope, receive, send)

    @staticmethod
    async def _rejection(scope: Scope, receive: Receive, send: Send) -> None:
        response = _reject(ApiErrorCode.VALIDATION_ERROR, "request body exceeds the size limit")
        await response(scope, receive, send)


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

        apply_security_headers(response)
        ensure_csrf_cookie(request, response)
        return response

    @staticmethod
    def _csrf_ok(request: Request) -> bool:
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not cookie_token or not header_token:
            return False
        return secrets.compare_digest(cookie_token, header_token)
