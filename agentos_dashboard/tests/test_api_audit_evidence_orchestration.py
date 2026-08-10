"""EP-16 (`GET /audit`), EP-17 (`GET /evidence/{ref}`), and EP-18 (`GET /orchestration`) —
`API_SPEC.md` §2, including EP-18's negative acceptance proofs (zero `dashboard.db` write, zero
Git invocation, zero agent/subprocess invocation)."""

from __future__ import annotations

import json
import subprocess

import pytest
from fastapi import FastAPI

from agentos_dashboard.storage.db import DashboardDatabase
from agentos_dashboard.tests._asgi_client import AsgiTestClient


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def _create_run(client: AsgiTestClient, *, token: str) -> dict[str, object]:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": token,
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
            "validation": [{"command": "pytest", "result": "PASS", "origin": "reported"}],
        }
    ).encode()
    response = client.post("/dash/api/v1/runs", headers=headers, body=body)
    assert response.status == 200
    result: dict[str, object] = response.json()["data"]
    return result


# ---- EP-16 audit -----------------------------------------------------------------------------


def test_audit_timeline_reflects_a_recorded_run(client: AsgiTestClient) -> None:
    _create_run(client, token="30000000-0000-4000-8000-000000000001")
    response = client.get("/dash/api/v1/audit")
    assert response.status == 200
    entries = response.json()["data"]["entries"]
    assert any(entry["kind"] == "run_created" for entry in entries)


def test_audit_timeline_kind_filter(client: AsgiTestClient) -> None:
    _create_run(client, token="30000000-0000-4000-8000-000000000002")
    response = client.get("/dash/api/v1/audit?kind=note_created")
    assert response.status == 200
    assert response.json()["data"]["entries"] == []


# ---- EP-17 evidence ---------------------------------------------------------------------------


def test_evidence_detail_reflects_verified_and_claimed_split(git_client: AsgiTestClient) -> None:
    data = _create_run(git_client, token="30000000-0000-4000-8000-000000000003")
    # Recreate a run with a real, existing report path against the git-backed workspace.
    headers = _csrf_headers(git_client)
    body = json.dumps(
        {
            "client_token": "30000000-0000-4000-8000-000000000004",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
            "report_path": "README.md",
            "validation": [
                {"command": "pytest", "result": "PASS", "origin": "reported"},
                {"command": "ruff", "result": "FAIL", "origin": "reported"},
            ],
        }
    ).encode()
    created = git_client.post("/dash/api/v1/runs", headers=headers, body=body).json()["data"]

    response = git_client.get(f"/dash/api/v1/evidence/{created['uuid']}")
    assert response.status == 200
    evidence = response.json()["data"]
    assert evidence["run"]["report_path_verified"] is True
    assert evidence["pass_count"] == 1
    assert evidence["fail_count"] == 1

    unverified = git_client.get(f"/dash/api/v1/evidence/{data['uuid']}")
    assert unverified.json()["data"]["run"]["report_path_verified"] is None


def test_evidence_unknown_ref_is_404(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/evidence/90000000-0000-4000-8000-000000000001")
    assert response.status == 404


def test_evidence_malformed_ref_is_422(client: AsgiTestClient) -> None:
    assert client.get("/dash/api/v1/evidence/does-not-exist").status == 422


# ---- EP-18 orchestration ------------------------------------------------------------------


def test_orchestration_view_is_reachable_and_read_only(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/orchestration")
    assert response.status == 200
    data = response.json()["data"]
    assert "stages" in data
    assert isinstance(data["stages"], list)


def test_orchestration_endpoint_writes_nothing_to_dashboard_db(dashboard_app: FastAPI) -> None:
    client = AsgiTestClient(dashboard_app)
    database: DashboardDatabase = dashboard_app.state.dashboard_database
    assert not database.db_path.exists()

    response = client.get("/dash/api/v1/orchestration")

    assert response.status == 200
    assert not database.db_path.exists()  # no connection was ever opened


def test_orchestration_http_path_never_invokes_git_or_subprocess(
    dashboard_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EP-18 says zero Git invocation across the endpoint, so prove the whole HTTP path."""

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("EP-18 HTTP path must never invoke a subprocess")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    client = AsgiTestClient(dashboard_app)
    response = client.get("/dash/api/v1/orchestration")
    assert response.status == 200


def test_orchestration_response_never_carries_a_mutation_affordance(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/orchestration")
    data = response.json()["data"]
    assert set(data.keys()) == {
        "available",
        "source",
        "notes",
        "feature_id",
        "current_stage",
        "next_eligible_stage",
        "delivery_order",
        "stages",
    }
