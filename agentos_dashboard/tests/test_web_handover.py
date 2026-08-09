"""PG-09 — the Handover page: rendering, MISSING rows, staleness, and no mutation affordance
(DASH-006)."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_handover_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/handover")
    assert response.status == 200
    assert "<h1>Handover</h1>" in response.text


def test_handover_page_carries_security_headers(client: AsgiTestClient) -> None:
    response = client.get("/handover")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_handover_page_has_no_mutation_affordance(client: AsgiTestClient) -> None:
    response = client.get("/handover")
    assert "<button" not in response.text
    assert "<form" not in response.text
    assert "<input" not in response.text


def test_handover_page_shows_missing_state_by_default(client: AsgiTestClient) -> None:
    response = client.get("/handover")
    assert "unavailable" in response.text.lower() or "No manifest rows" in response.text


def test_handover_page_shows_a_missing_row(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | 10 | 2026-01-01 | {'a' * 64} |\n",
    )
    response = client.get("/handover")
    assert "MISSING" in response.text


def test_handover_page_shows_verified_row_and_narrative(
    workspace: Path, client: AsgiTestClient
) -> None:
    narrative = "# Handover\n\nAll good here.\n"
    write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    digest = hashlib.sha256(narrative.encode("utf-8")).hexdigest()
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "Recompute size + sha256sum to refresh.\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(narrative.encode('utf-8'))} | 2026-01-01 | "
        f"{digest} |\n",
    )
    response = client.get("/handover")
    assert "VERIFIED" in response.text
    assert "All good here." in response.text
    assert "Recompute size" in response.text


def test_handover_page_shows_stale_banner(workspace: Path, client: AsgiTestClient) -> None:
    narrative_path = write(workspace, "handover/PROJECT_HANDOVER.md", "# Old\n")
    old = time.time() - 10_000
    os.utime(narrative_path, (old, old))
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — thing\n\nStatus: Current\n\n")

    response = client.get("/handover")
    assert "STALE" in response.text
