"""EP-23 (`API_SPEC.md` §3): `POST /approvals`, `POST /findings`, `POST /notes`."""

from __future__ import annotations

import json

from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def test_create_approval_requires_csrf(client: AsgiTestClient) -> None:
    body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000001",
            "layer": "human_approval",
            "verdict": "approved",
        }
    ).encode()
    assert client.post("/dash/api/v1/approvals", body=body).status == 403


def test_create_approval_success(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000002",
            "layer": "human_approval",
            "verdict": "approved",
            "notes": "looks good",
        }
    ).encode()
    response = client.post("/dash/api/v1/approvals", headers=headers, body=body)
    assert response.status == 200
    data = response.json()["data"]
    assert data["layer"] == "human_approval"
    assert data["reconciled"] is False
    assert data["target_commit_resolved"] is None
    assert "LOCAL" in data["reconciliation_scope"]


def test_create_approval_rejects_unknown_layer(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000003",
            "layer": "not_a_layer",
            "verdict": "approved",
        }
    ).encode()
    response = client.post("/dash/api/v1/approvals", headers=headers, body=body)
    assert response.status == 422


def test_create_approval_idempotent_replay(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000004",
            "layer": "implementation_review",
            "verdict": "pending",
        }
    ).encode()
    first = client.post("/dash/api/v1/approvals", headers=headers, body=body)
    second = client.post("/dash/api/v1/approvals", headers=headers, body=body)
    assert first.json()["data"]["uuid"] == second.json()["data"]["uuid"]

    conflicting_body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000004",
            "layer": "implementation_review",
            "verdict": "rejected",
        }
    ).encode()
    conflict = client.post("/dash/api/v1/approvals", headers=headers, body=conflicting_body)
    assert conflict.status == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_create_finding_success_and_replay(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000005",
            "severity": "blocker",
            "text": "something is broken",
        }
    ).encode()
    first = client.post("/dash/api/v1/findings", headers=headers, body=body)
    assert first.status == 200
    assert first.json()["data"]["severity"] == "blocker"
    second = client.post("/dash/api/v1/findings", headers=headers, body=body)
    assert second.json()["data"]["uuid"] == first.json()["data"]["uuid"]


def test_create_finding_rejects_empty_text(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {"client_token": "20000000-0000-4000-8000-000000000006", "severity": "minor", "text": ""}
    ).encode()
    response = client.post("/dash/api/v1/findings", headers=headers, body=body)
    assert response.status == 422


def test_create_note_success_and_replay(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000007",
            "target_ref": "run:abc",
            "text": "a note",
        }
    ).encode()
    first = client.post("/dash/api/v1/notes", headers=headers, body=body)
    assert first.status == 200
    second = client.post("/dash/api/v1/notes", headers=headers, body=body)
    assert second.json()["data"]["uuid"] == first.json()["data"]["uuid"]

    conflicting = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000007",
            "target_ref": "run:different",
            "text": "different",
        }
    ).encode()
    conflict = client.post("/dash/api/v1/notes", headers=headers, body=conflicting)
    assert conflict.status == 409


def test_draft_payload_rejects_unexpected_field_and_stale_run_uuid(
    client: AsgiTestClient,
) -> None:
    headers = _csrf_headers(client)
    unexpected = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000008",
            "severity": "minor",
            "text": "x",
            "unexpected": True,
        }
    ).encode()
    stale = json.dumps(
        {
            "client_token": "20000000-0000-4000-8000-000000000009",
            "severity": "minor",
            "text": "x",
            "run_uuid": "90000000-0000-4000-8000-000000000001",
        }
    ).encode()
    assert client.post("/dash/api/v1/findings", headers=headers, body=unexpected).status == 422
    assert client.post("/dash/api/v1/findings", headers=headers, body=stale).status == 422
