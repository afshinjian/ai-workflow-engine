"""PG-06 (`UI_SPEC.md` §3): `/evidence`."""

from __future__ import annotations

import json
import re

from agentos_dashboard.tests._asgi_client import AsgiTestClient

_BUTTON_RE = re.compile(r"<button[^>]*>.*?</button>", re.IGNORECASE | re.DOTALL)


def _csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def test_evidence_page_renders_empty_state(client: AsgiTestClient) -> None:
    response = client.get("/evidence")
    assert response.status == 200
    assert "No runs recorded yet" in response.text


def test_evidence_page_lists_gate_matrix(client: AsgiTestClient) -> None:
    headers = _csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "60000000-0000-4000-8000-000000000001",
            "stage_id": "DASH-008",
            "tool": "claude",
            "started_at": "2026-08-10T00:00:00+00:00",
            "reported_result": "y",
            "validation": [{"command": "pytest", "result": "PASS", "origin": "reported"}],
        }
    ).encode()
    client.post("/dash/api/v1/runs", headers=headers, body=body)
    response = client.get("/evidence")
    assert response.status == 200
    assert "DASH-008" in response.text


def test_evidence_page_has_no_rerun_affordance(client: AsgiTestClient) -> None:
    """PG-06: "re-run buttons absent" — no `<button>` element offers to re-run anything."""
    response = client.get("/evidence")
    buttons = _BUTTON_RE.findall(response.text)
    assert not any("re-run" in button.lower() for button in buttons)
