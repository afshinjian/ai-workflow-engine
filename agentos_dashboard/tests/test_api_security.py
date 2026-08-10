"""`api.security.SecurityMiddleware` — Host allowlist (SC-36), CSRF double-submit (SC-03), and
the security headers/no-cache posture applied to every response (SC-04, SC-05, `API_SPEC.md` §1).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send

from agentos_dashboard.api.security import (
    CSP_HEADER_VALUE,
    CSRF_COOKIE_NAME,
    MAX_REQUEST_BODY_BYTES,
    RequestBodyLimitMiddleware,
)
from agentos_dashboard.tests._asgi_client import AsgiTestClient


def test_get_is_never_refused_for_missing_csrf(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/health")
    assert response.status == 200


def test_first_response_issues_a_csrf_cookie(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/health")
    assert response.header("set-cookie") is not None
    assert CSRF_COOKIE_NAME in (response.header("set-cookie") or "")


def test_post_without_csrf_token_is_refused(client: AsgiTestClient) -> None:
    client.get("/dash/api/v1/health")  # obtain a cookie first
    response = client.post("/dash/api/v1/snapshot/refresh")
    assert response.status == 403
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CSRF_REQUIRED"


def test_post_with_mismatched_csrf_token_is_refused(client: AsgiTestClient) -> None:
    client.get("/dash/api/v1/health")
    response = client.post(
        "/dash/api/v1/snapshot/refresh", headers={"X-CSRF-Token": "not-the-real-token"}
    )
    assert response.status == 403
    assert response.json()["error"]["code"] == "CSRF_REQUIRED"


@pytest.mark.parametrize("header", ["", " ", "malformed-token"])
def test_post_with_malformed_csrf_token_is_refused(client: AsgiTestClient, header: str) -> None:
    client.get("/dash/api/v1/health")
    response = client.post("/dash/api/v1/snapshot/refresh", headers={"X-CSRF-Token": header})
    assert response.status == 403
    assert response.json()["error"]["code"] == "CSRF_REQUIRED"


def test_cross_origin_style_post_without_double_submit_token_is_refused(
    client: AsgiTestClient,
) -> None:
    response = client.post(
        "/dash/api/v1/snapshot/refresh", headers={"Origin": "https://evil.example"}
    )
    assert response.status == 403
    assert response.json()["error"]["code"] == "CSRF_REQUIRED"


def test_post_with_matching_double_submit_token_succeeds(client: AsgiTestClient) -> None:
    client.get("/dash/api/v1/health")
    token = client._cookies[CSRF_COOKIE_NAME]
    response = client.post("/dash/api/v1/snapshot/refresh", headers={"X-CSRF-Token": token})
    assert response.status == 200
    assert response.json()["ok"] is True


@pytest.mark.parametrize("host", ["localhost:8642", "127.0.0.1:8642", "[::1]:8642"])
def test_allowed_host_headers_are_accepted(client: AsgiTestClient, host: str) -> None:
    response = client.get("/dash/api/v1/health", headers={"Host": host})
    assert response.status == 200


@pytest.mark.parametrize(
    "host", ["evil.example.com", "127.0.0.1:9999", "127.0.0.1.evil.com:8642", ""]
)
def test_disallowed_host_headers_are_rejected(client: AsgiTestClient, host: str) -> None:
    response = client.get("/dash/api/v1/health", headers={"Host": host})
    assert response.status == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "HOST_REJECTED"


def test_security_headers_present_on_a_success_response(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/health")
    assert response.header("content-security-policy") == CSP_HEADER_VALUE
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("cache-control") == "no-store"


def test_normal_html_response_has_headers_and_csrf_cookie(client: AsgiTestClient) -> None:
    response = client.get("/")
    assert response.status == 200
    assert (response.header("content-type") or "").startswith("text/html")
    assert response.header("content-security-policy") == CSP_HEADER_VALUE
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("cache-control") == "no-store"
    assert CSRF_COOKIE_NAME in (response.header("set-cookie") or "")


def test_security_headers_present_on_a_refused_response(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/health", headers={"Host": "evil.example.com"})
    assert response.header("content-security-policy") == CSP_HEADER_VALUE
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("cache-control") == "no-store"


def test_security_headers_present_on_a_not_found_response(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/does-not-exist")
    assert response.status == 404
    assert response.header("content-security-policy") == CSP_HEADER_VALUE
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert CSRF_COOKIE_NAME in (response.header("set-cookie") or "")


def test_405_and_validation_422_keep_json_envelope_and_security_headers(
    client: AsgiTestClient,
) -> None:
    client.get("/dash/api/v1/health")
    token = client._cookies[CSRF_COOKIE_NAME]
    method = client.request("DELETE", "/dash/api/v1/runs", headers={"X-CSRF-Token": token})
    malformed = client.post(
        "/dash/api/v1/runs",
        headers={"X-CSRF-Token": token, "Content-Type": "application/json"},
        body=b'{"client_token":',
    )
    assert method.status == 405
    assert malformed.status == 422
    for response in (method, malformed):
        assert response.json()["ok"] is False
        assert response.header("content-security-policy") == CSP_HEADER_VALUE
        assert response.header("x-content-type-options") == "nosniff"
        assert response.header("cache-control") == "no-store"


async def _body_echo_app(scope: Scope, receive: Receive, send: Send) -> None:
    consumed = 0
    more = True
    while more:
        message = await receive()
        consumed += len(message.get("body", b""))
        more = bool(message.get("more_body", False))
    response = PlainTextResponse(str(consumed))
    await response(scope, receive, send)


def test_request_body_limit_accepts_the_exact_boundary() -> None:
    client = AsgiTestClient(RequestBodyLimitMiddleware(_body_echo_app, max_body_bytes=8))
    response = client.post("/", body=b"12345678")
    assert response.status == 200
    assert response.text == "8"


def test_request_body_limit_rejects_one_byte_over_with_typed_error() -> None:
    client = AsgiTestClient(RequestBodyLimitMiddleware(_body_echo_app, max_body_bytes=8))
    response = client.post("/", body=b"123456789")
    assert response.status == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_dashboard_rejects_oversized_json_before_routing_with_security_headers(
    client: AsgiTestClient,
) -> None:
    client.get("/dash/api/v1/health")
    token = client._cookies[CSRF_COOKIE_NAME]
    response = client.post(
        "/dash/api/v1/notes",
        headers={"X-CSRF-Token": token, "Content-Type": "application/json"},
        body=b"{" + b'"ignored":"' + b"x" * MAX_REQUEST_BODY_BYTES + b'"}',
    )
    assert response.status == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.header("content-security-policy") == CSP_HEADER_VALUE
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("cache-control") == "no-store"


def test_no_mutating_git_verb_or_shell_call_in_security_module_source() -> None:
    """Defense in depth (SC-11, SC-29 idiom): this middleware must never shell out."""
    import agentos_dashboard.api.security as module

    assert module.__file__ is not None
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "shell=True"):
        assert forbidden not in source
