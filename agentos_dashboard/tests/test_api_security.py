"""`api.security.SecurityMiddleware` — Host allowlist (SC-36), CSRF double-submit (SC-03), and
the security headers/no-cache posture applied to every response (SC-04, SC-05, `API_SPEC.md` §1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_dashboard.api.security import CSP_HEADER_VALUE, CSRF_COOKIE_NAME
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


def test_no_mutating_git_verb_or_shell_call_in_security_module_source() -> None:
    """Defense in depth (SC-11, SC-29 idiom): this middleware must never shell out."""
    import agentos_dashboard.api.security as module

    assert module.__file__ is not None
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "shell=True"):
        assert forbidden not in source
