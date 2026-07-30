"""EP-01/EP-02/EP-03/EP-20 (`API_SPEC.md` §2-3) — envelope shape and route behavior."""

from __future__ import annotations

from fastapi import FastAPI

from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"]}


def test_health_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/health")
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    assert body["error"] is None
    data = body["data"]
    assert data["status"] == "ok"
    assert data["locked"] is False
    assert data["bind"].startswith("http://")
    assert isinstance(data["snapshot_age_seconds"], float)


def test_snapshot_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/snapshot")
    assert response.status == 200
    data = response.json()["data"]
    assert "fingerprint" in data
    assert "generated_at" in data
    assert isinstance(data["findings"], list)
    assert data["stale"] is False


def test_status_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/status")
    assert response.status == 200
    data = response.json()["data"]
    for key in (
        "version",
        "current_task_id",
        "current_task_summary",
        "task_counts",
        "blockers",
        "orch_blockers",
        "git",
        "consistency_findings",
        "last_event_summary",
        "stale",
    ):
        assert key in data


def test_status_reports_healthy_empty_current_task(client: AsgiTestClient) -> None:
    data = client.get("/dash/api/v1/status").json()["data"]
    assert data["current_task_id"] is None
    assert "No Current task" in data["current_task_summary"]


def test_snapshot_refresh_returns_a_fresh_fingerprint(client: AsgiTestClient) -> None:
    first = client.get("/dash/api/v1/snapshot").json()["data"]["fingerprint"]
    response = client.post("/dash/api/v1/snapshot/refresh", headers=_csrf_headers(client))
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["fingerprint"] == first  # nothing changed, same digest is correct


def test_snapshot_refresh_while_a_build_is_in_progress_returns_409(
    dashboard_app: FastAPI, client: AsgiTestClient
) -> None:
    cache: SnapshotCache = dashboard_app.state.snapshot_cache
    headers = _csrf_headers(client)  # obtained before locking: cache.get() takes the same lock
    cache._lock.acquire()
    try:
        response = client.post("/dash/api/v1/snapshot/refresh", headers=headers)
        assert response.status == 409
        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "SNAPSHOT_BUILDING"
    finally:
        cache._lock.release()


def test_unknown_api_path_returns_typed_not_found(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/no-such-endpoint")
    assert response.status == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_no_repository_write_endpoint_exists() -> None:
    """DR-062/`API_SPEC.md` §4: absent-by-design mutating verbs, asserted by source scan."""
    from pathlib import Path

    import agentos_dashboard.api.routes as module

    assert module.__file__ is not None
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "shutil.", "open(", "Path.write", "os.remove", "os.system"):
        assert forbidden not in source
