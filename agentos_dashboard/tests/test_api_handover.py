"""EP-11 (`API_SPEC.md` §2) — the handover viewer's JSON route (DASH-006)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_handover_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/handover")
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    for key in (
        "manifest_path",
        "manifest_instructions",
        "narrative_path",
        "records",
        "stale",
        "findings",
    ):
        assert key in data


def test_handover_reports_missing_documents_by_default(client: AsgiTestClient) -> None:
    data = client.get("/dash/api/v1/handover").json()["data"]
    assert data["records"] == []
    assert any(f["rule"] == "document_missing" for f in data["findings"])


def test_handover_verifies_a_matching_manifest_row(workspace: Path, client: AsgiTestClient) -> None:
    narrative = "# Handover\n\nfine\n"
    write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    digest = hashlib.sha256(narrative.encode("utf-8")).hexdigest()
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(narrative.encode('utf-8'))} | 2026-01-01 | "
        f"{digest} |\n",
    )
    data = client.get("/dash/api/v1/handover").json()["data"]
    assert len(data["records"]) == 1
    assert data["records"][0]["exists"] is True
    assert data["records"][0]["digest_match"] is True
    assert data["narrative_text"] == narrative
