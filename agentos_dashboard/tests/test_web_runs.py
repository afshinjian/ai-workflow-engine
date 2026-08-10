"""PG-05 (`UI_SPEC.md` §3): `/runs`, `/runs/{uuid}`."""

from __future__ import annotations

import json

from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def test_runs_page_renders_empty_state(client: AsgiTestClient) -> None:
    response = client.get("/runs")
    assert response.status == 200
    assert "No runs recorded yet" in response.text
    assert "Record a run" in response.text


def test_runs_page_lists_a_recorded_run(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "50000000-0000-4000-8000-000000000001",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
        }
    ).encode()
    client.post("/dash/api/v1/runs", headers=headers, body=body)
    response = client.get("/runs")
    assert response.status == 200
    assert "DASH-008" in response.text


def test_run_detail_page_404_for_unknown_uuid(client: AsgiTestClient) -> None:
    response = client.get("/runs/does-not-exist")
    assert response.status == 404
    assert "Run not found" in response.text


def test_run_detail_page_renders_recorded_fields(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "50000000-0000-4000-8000-000000000002",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "COMPLETED",
        }
    ).encode()
    created = client.post("/dash/api/v1/runs", headers=headers, body=body).json()["data"]
    response = client.get(f"/runs/{created['uuid']}")
    assert response.status == 200
    assert "COMPLETED" in response.text
    assert "Add note" in response.text


def test_run_detail_page_shows_notes(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    run_body = json.dumps(
        {
            "client_token": "50000000-0000-4000-8000-000000000003",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
        }
    ).encode()
    created = client.post("/dash/api/v1/runs", headers=headers, body=run_body).json()["data"]
    note_body = json.dumps(
        {
            "client_token": "50000000-0000-4000-8000-000000000004",
            "target_ref": f"run:{created['uuid']}",
            "text": "hello from a note",
        }
    ).encode()
    client.post("/dash/api/v1/notes", headers=headers, body=note_body)
    response = client.get(f"/runs/{created['uuid']}")
    assert "hello from a note" in response.text


def test_run_and_note_claims_are_html_escaped(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    hostile = "<script>alert('x')</script>"
    run_body = json.dumps(
        {
            "client_token": "50000000-0000-4000-8000-000000000005",
            "stage_id": "DASH-008",
            "tool": "manual",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": hostile,
        }
    ).encode()
    created = client.post("/dash/api/v1/runs", headers=headers, body=run_body).json()["data"]
    note_body = json.dumps(
        {
            "client_token": "50000000-0000-4000-8000-000000000006",
            "target_ref": f"run:{created['uuid']}",
            "text": hostile,
        }
    ).encode()
    client.post("/dash/api/v1/notes", headers=headers, body=note_body)
    response = client.get(f"/runs/{created['uuid']}")
    assert hostile not in response.text
    assert "&lt;script&gt;" in response.text
