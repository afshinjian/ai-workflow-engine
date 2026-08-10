"""PG-10 (`UI_SPEC.md` §3): `/audit`."""

from __future__ import annotations

import json

from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def test_audit_page_renders_empty_state(client: AsgiTestClient) -> None:
    response = client.get("/audit")
    assert response.status == 200
    assert "No audit events recorded yet" in response.text


def test_audit_page_lists_recorded_events(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "70000000-0000-4000-8000-000000000001",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
        }
    ).encode()
    client.post("/dash/api/v1/runs", headers=headers, body=body)
    response = client.get("/audit")
    assert response.status == 200
    assert "run_created" in response.text


def test_audit_page_has_no_delete_affordance(client: AsgiTestClient) -> None:
    """SC-22: deletion is never possible from this page."""
    response = client.get("/audit")
    assert "delete" not in response.text.lower()


def test_audit_page_kind_filter_query_param_round_trips(client: AsgiTestClient) -> None:
    response = client.get("/audit?kind=run_created&task=DASH-008")
    assert response.status == 200
    assert 'value="run_created"' in response.text
    assert 'value="DASH-008"' in response.text


def test_audit_page_rejects_oversized_filters(client: AsgiTestClient) -> None:
    response = client.get(f"/audit?task={'x' * 65}")
    assert response.status == 422
