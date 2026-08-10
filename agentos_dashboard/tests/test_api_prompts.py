"""EP-14/EP-21 (`API_SPEC.md` §2-3): `POST /prompts/generate` and `GET /prompts/{uuid}/export`."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from agentos_dashboard.main import create_app
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.test_services_prompts import _TARGET, _seed_success


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


@pytest.fixture
def ready_stage_app(git_repo: Path) -> FastAPI:
    _seed_success(git_repo)
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(git_repo)})
    return create_app(settings)


@pytest.fixture
def ready_stage_client(ready_stage_app: FastAPI) -> AsgiTestClient:
    return AsgiTestClient(ready_stage_app)


def test_generate_requires_csrf(client: AsgiTestClient) -> None:
    response = client.post(
        "/dash/api/v1/prompts/generate",
        body=b'{"stage_id": "DASH-002", "client_token": "00000000-0000-4000-8000-000000000001"}',
    )
    assert response.status == 403


def test_generate_refuses_stage_with_unmet_preconditions(client: AsgiTestClient) -> None:
    """DASH-007.md acceptance: refusal is a 422 with itemized unmet preconditions."""
    headers = _csrf_headers(client)
    response = client.post(
        "/dash/api/v1/prompts/generate",
        headers=headers,
        body=b'{"stage_id": "DASH-002", "client_token": "00000000-0000-4000-8000-000000000002"}',
    )
    assert response.status == 422
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    message = body["error"]["message"]
    assert "owner_authorization_recorded" in message or "predecessor_complete" in message


def test_generate_unknown_stage_is_404(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        "/dash/api/v1/prompts/generate",
        headers=headers,
        body=b'{"stage_id": "NOT-A-STAGE", "client_token": "00000000-0000-4000-8000-000000000003"}',
    )
    assert response.status == 404


def test_generate_success_and_export_bytes_hash_match_preview(
    ready_stage_client: AsgiTestClient,
) -> None:
    headers = _csrf_headers(ready_stage_client)
    response = ready_stage_client.post(
        "/dash/api/v1/prompts/generate",
        headers=headers,
        body=(
            f'{{"stage_id": "{_TARGET.stage_id}", '
            '"client_token": "00000000-0000-4000-8000-000000000004"}'
        ).encode(),
    )
    assert response.status == 200
    data = response.json()["data"]
    assert data["stage_id"] == _TARGET.stage_id
    assert data["sha256"]

    export = ready_stage_client.get(f"/dash/api/v1/prompts/{data['prompt_uuid']}/export")
    assert export.status == 200
    export_data = export.json()["data"]
    assert export_data["markdown"] == data["markdown"]
    assert export_data["sha256"] == data["sha256"]


def test_export_unknown_uuid_is_404(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/prompts/00000000-0000-0000-0000-000000000000/export")
    assert response.status == 404


def test_generate_idempotent_replay_via_client_token(ready_stage_client: AsgiTestClient) -> None:
    headers = _csrf_headers(ready_stage_client)
    body = (
        f'{{"stage_id": "{_TARGET.stage_id}", '
        '"client_token": "00000000-0000-4000-8000-000000000005"}'
    ).encode()
    first = ready_stage_client.post("/dash/api/v1/prompts/generate", headers=headers, body=body)
    second = ready_stage_client.post("/dash/api/v1/prompts/generate", headers=headers, body=body)
    assert first.json()["data"]["prompt_uuid"] == second.json()["data"]["prompt_uuid"]


def test_generate_rejects_non_uuid_client_token(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        "/dash/api/v1/prompts/generate",
        headers=headers,
        body=b'{"stage_id": "DASH-002", "client_token": "not-a-uuid"}',
    )
    assert response.status == 422


def test_export_rejects_malformed_uuid(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/prompts/not-a-uuid/export")
    assert response.status == 422
