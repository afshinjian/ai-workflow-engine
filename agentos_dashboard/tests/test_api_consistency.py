"""EP-12 (`API_SPEC.md` §2) — the Consistency page's JSON route and the local
acknowledgment action (`UI_SPEC.md` PG-11, DASH-006)."""

from __future__ import annotations

import json

from agentos_dashboard.api.acknowledgments import finding_fingerprint
from agentos_dashboard.services.consistency import ConsistencyFinding, ConsistencySeverity
from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def test_consistency_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/consistency")
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    for key in ("generated_at", "findings", "acknowledgment_history"):
        assert key in data


def test_finding_fingerprint_is_stable_for_the_same_content() -> None:
    a = ConsistencyFinding(
        rule="r", severity=ConsistencySeverity.ERROR, message="m", sources=("s",)
    )
    b = ConsistencyFinding(
        rule="r", severity=ConsistencySeverity.ERROR, message="m", sources=("s",)
    )
    assert finding_fingerprint(a) == finding_fingerprint(b)


def test_finding_fingerprint_differs_for_different_content() -> None:
    a = ConsistencyFinding(rule="r", severity=ConsistencySeverity.ERROR, message="m1", sources=())
    b = ConsistencyFinding(rule="r", severity=ConsistencySeverity.ERROR, message="m2", sources=())
    assert finding_fingerprint(a) != finding_fingerprint(b)


def test_acknowledge_requires_csrf(client: AsgiTestClient) -> None:
    response = client.post(
        "/dash/api/v1/consistency/acknowledge",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"fingerprint": "abc", "note": "note"}).encode("utf-8"),
    )
    assert response.status == 403
    assert response.json()["error"]["code"] == "CSRF_REQUIRED"


def test_acknowledge_records_a_note_and_it_appears_in_history(
    workspace, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — thing\n\nStatus: Current\n\nbody\n\n"
        "## FIX-002 — other\n\nStatus: Current\n\nbody\n",
    )
    findings = client.get("/dash/api/v1/consistency").json()["data"]["findings"]
    assert findings  # sole-Current invariant violated by the two Current tasks above
    fingerprint = findings[0]["fingerprint"]

    response = client.post(
        "/dash/api/v1/consistency/acknowledge",
        headers=_csrf_headers(client),
        body=json.dumps({"fingerprint": fingerprint, "note": "known, tracked in FIX-003"}).encode(
            "utf-8"
        ),
    )
    assert response.status == 200
    ack_body = response.json()["data"]
    assert ack_body["fingerprint"] == fingerprint
    assert ack_body["note"] == "known, tracked in FIX-003"

    refreshed = client.get("/dash/api/v1/consistency").json()["data"]
    assert len(refreshed["acknowledgment_history"]) == 1
    matching = next(f for f in refreshed["findings"] if f["fingerprint"] == fingerprint)
    assert len(matching["acknowledgments"]) == 1
    assert matching["acknowledgments"][0]["note"] == "known, tracked in FIX-003"


def test_acknowledge_rejects_an_empty_note(client: AsgiTestClient) -> None:
    response = client.post(
        "/dash/api/v1/consistency/acknowledge",
        headers=_csrf_headers(client),
        body=json.dumps({"fingerprint": "abc", "note": ""}).encode("utf-8"),
    )
    assert response.status == 422


def test_acknowledgment_note_is_redacted_before_in_memory_storage(
    client: AsgiTestClient,
) -> None:
    response = client.post(
        "/dash/api/v1/consistency/acknowledge",
        headers=_csrf_headers(client),
        body=json.dumps({"fingerprint": "abc", "note": "Authorization: Basic dXNlcjpwYXNz"}).encode(
            "utf-8"
        ),
    )
    assert response.status == 200
    assert response.json()["data"]["note"] == "Authorization: Basic [REDACTED]"
    history = client.get("/dash/api/v1/consistency").json()["data"]["acknowledgment_history"]
    assert history[0]["note"] == "Authorization: Basic [REDACTED]"
