"""DASH-008 acceptance: "the database is non-authoritative: deleting it must not break any
read-only view" (`DATA_MODEL.md` TR-06/TR-08; stage contract Build/Acceptance)."""

from __future__ import annotations

import json

from fastapi import FastAPI

from agentos_dashboard.storage.db import DashboardDatabase
from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def test_deleting_dashboard_db_does_not_break_any_read_only_view(dashboard_app: FastAPI) -> None:
    client = AsgiTestClient(dashboard_app)
    database: DashboardDatabase = dashboard_app.state.dashboard_database

    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "40000000-0000-4000-8000-000000000001",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
        }
    ).encode()
    created = client.post("/dash/api/v1/runs", headers=headers, body=body)
    assert created.status == 200
    assert database.db_path.exists()

    database.db_path.unlink()
    assert not database.db_path.exists()

    for path in (
        "/",
        "/board",
        "/git",
        "/handover",
        "/consistency",
        "/stages",
        "/governance",
        "/runs",
        "/evidence",
        "/audit",
    ):
        response = client.get(path)
        assert response.status == 200, f"{path} broke after dashboard.db was deleted"

    api_health = client.get("/dash/api/v1/health")
    assert api_health.status == 200

    api_runs = client.get("/dash/api/v1/runs")
    assert api_runs.status == 200
    assert api_runs.json()["data"]["runs"] == []  # recreated empty, not an error

    api_audit = client.get("/dash/api/v1/audit")
    assert api_audit.status == 200
    entries = api_audit.json()["data"]["entries"]
    assert [entry["kind"] for entry in entries] == ["audit_mirror_divergence"]
    assert entries[0]["contradiction"] is True

    api_orchestration = client.get("/dash/api/v1/orchestration")
    assert api_orchestration.status == 200
