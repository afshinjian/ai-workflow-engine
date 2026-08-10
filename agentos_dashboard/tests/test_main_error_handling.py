"""`main._install_exception_handlers`'s `Exception` handler: no traceback or exception text ever
crosses either surface this app serves, and a browser-facing page degrades to a themed HTML page
rather than a raw JSON envelope (SC-09; "graceful error pages without tracebacks")."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.tests._asgi_client import AsgiTestClient


class _Boom(RuntimeError):
    def __str__(self) -> str:
        return "sk-THISISAFAKESECRETLEAKEDBYACRASH1234"


def _break_snapshot_cache(dashboard_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(self: SnapshotCache) -> None:
        raise _Boom("unexpected failure deep in snapshot construction")

    monkeypatch.setattr(SnapshotCache, "get", _raise)


def test_web_route_unexpected_exception_renders_a_themed_html_page(
    client: AsgiTestClient, dashboard_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _break_snapshot_cache(dashboard_app, monkeypatch)
    response = client.get("/")
    assert response.status == 500
    assert (response.header("content-type") or "").startswith("text/html")
    body = response.text
    assert "Something went wrong" in body
    assert "sk-THISISAFAKESECRETLEAKEDBYACRASH1234" not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert response.header("content-security-policy") is not None
    assert "dash_csrf=" in (response.header("set-cookie") or "")


def test_web_route_unexpected_exception_still_carries_security_headers(
    client: AsgiTestClient, dashboard_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _break_snapshot_cache(dashboard_app, monkeypatch)
    response = client.get("/board")
    assert response.status == 500
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("cache-control") == "no-store"


def test_api_route_unexpected_exception_still_returns_the_json_envelope(
    client: AsgiTestClient, dashboard_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _break_snapshot_cache(dashboard_app, monkeypatch)
    response = client.get("/dash/api/v1/health")
    assert response.status == 500
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INTERNAL"
    assert "sk-THISISAFAKESECRETLEAKEDBYACRASH1234" not in response.text
    assert "Traceback" not in response.text
    assert response.header("content-security-policy") is not None
    assert response.header("x-content-type-options") == "nosniff"
    assert response.header("cache-control") == "no-store"


def test_route_crash_is_contained_before_the_server_exception_boundary(
    dashboard_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _break_snapshot_cache(dashboard_app, monkeypatch)
    strict_client = AsgiTestClient(dashboard_app, raise_server_exceptions=True)
    response = strict_client.get("/dash/api/v1/health")
    assert response.status == 500
    assert response.json()["error"]["message"] == "internal error"
