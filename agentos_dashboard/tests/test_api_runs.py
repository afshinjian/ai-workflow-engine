"""EP-15/EP-22 (`API_SPEC.md` §2-3): `GET/POST /runs`, `GET /runs/{uuid}`."""

from __future__ import annotations

import json

from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def _create_run_body(**overrides: object) -> bytes:
    payload: dict[str, object] = {
        "client_token": "10000000-0000-4000-8000-000000000001",
        "stage_id": "DASH-008",
        "tool": "claude",
        "started_at": "2026-08-10T00:00:00+00:00",
        "reported_result": "COMPLETED",
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def test_create_run_requires_csrf(client: AsgiTestClient) -> None:
    response = client.post("/dash/api/v1/runs", body=_create_run_body())
    assert response.status == 403


def test_create_run_success_then_get_by_uuid(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    created = client.post("/dash/api/v1/runs", headers=headers, body=_create_run_body())
    assert created.status == 200
    data = created.json()["data"]
    assert data["stage_id"] == "DASH-008"
    assert data["report_path_verified"] is None

    fetched = client.get(f"/dash/api/v1/runs/{data['uuid']}")
    assert fetched.status == 200
    assert fetched.json()["data"]["uuid"] == data["uuid"]


def test_create_run_records_validation_matrix(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = _create_run_body(
        client_token="10000000-0000-4000-8000-000000000002",
        validation=[
            {"command": "pytest", "result": "PASS", "origin": "reported", "counts": {"passed": 3}}
        ],
    )
    response = client.post("/dash/api/v1/runs", headers=headers, body=body)
    assert response.status == 200
    entries = response.json()["data"]["validation_entries"]
    assert len(entries) == 1
    assert entries[0]["result"] == "PASS"
    assert entries[0]["counts"] == {"passed": 3}


def test_create_run_report_path_verified_reflects_repository(git_client: AsgiTestClient) -> None:
    headers = _csrf_headers(git_client)
    body = _create_run_body(
        client_token="10000000-0000-4000-8000-000000000003", report_path="README.md"
    )
    response = git_client.post("/dash/api/v1/runs", headers=headers, body=body)
    assert response.status == 200
    assert response.json()["data"]["report_path_verified"] is True


def test_create_run_idempotent_replay_returns_original(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = _create_run_body(client_token="10000000-0000-4000-8000-000000000004")
    first = client.post("/dash/api/v1/runs", headers=headers, body=body)
    second = client.post("/dash/api/v1/runs", headers=headers, body=body)
    assert first.json()["data"]["uuid"] == second.json()["data"]["uuid"]

    conflict = client.post(
        "/dash/api/v1/runs",
        headers=headers,
        body=_create_run_body(
            client_token="10000000-0000-4000-8000-000000000004",
            stage_id="DASH-999",
            reported_result="different — must not apply",
        ),
    )
    assert conflict.status == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    listing = client.get("/dash/api/v1/runs")
    assert len(listing.json()["data"]["runs"]) == 1


def test_get_unknown_run_is_404(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/runs/90000000-0000-4000-8000-000000000001")
    assert response.status == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_run_rejects_malformed_uuid(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/runs/does-not-exist")
    assert response.status == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_run_rejects_unexpected_fields_and_malformed_json(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    unexpected = client.post(
        "/dash/api/v1/runs",
        headers=headers,
        body=_create_run_body(unexpected="value"),
    )
    malformed = client.post("/dash/api/v1/runs", headers=headers, body=b'{"client_token":')
    assert unexpected.status == 422
    assert malformed.status == 422


def test_run_endpoint_rejects_unsupported_method_with_typed_envelope(
    client: AsgiTestClient,
) -> None:
    headers = _csrf_headers(client)
    response = client.request("DELETE", "/dash/api/v1/runs", headers=headers)
    assert response.status == 405
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_run_rejects_empty_stage_id(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        "/dash/api/v1/runs",
        headers=headers,
        body=_create_run_body(client_token="10000000-0000-4000-8000-000000000005", stage_id=""),
    )
    assert response.status == 422
