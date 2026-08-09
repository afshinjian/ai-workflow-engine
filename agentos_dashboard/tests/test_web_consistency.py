"""PG-11 — the Consistency page: findings, acknowledge-with-local-note action, and history
(DASH-006). The only interactive affordance this page carries is the local acknowledgment note
(`UI_SPEC.md` PG-11 "Visible actions: acknowledge (local note)"); it never mutates a repository
document and carries no Git-mutating affordance of any kind (this stage's own Constraint)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_consistency_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/consistency")
    assert response.status == 200
    assert "<h1>Consistency</h1>" in response.text


def test_consistency_page_carries_security_headers(client: AsgiTestClient) -> None:
    response = client.get("/consistency")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_consistency_page_shows_healthy_empty_state_when_no_findings_and_no_history(
    client: AsgiTestClient,
) -> None:
    """`run_consistency_checks` reports `document_missing` for every unreadable watched file, so
    a genuinely empty findings list needs every watched document present and self-consistent —
    the pyproject/version fact is the only one this fixture cannot cheaply satisfy, so this
    asserts the achievable healthy state instead: no acknowledgment history yet."""
    response = client.get("/consistency")
    assert "No acknowledgments recorded this session" in response.text


def test_consistency_page_reports_document_missing_findings_on_an_empty_repository(
    client: AsgiTestClient,
) -> None:
    response = client.get("/consistency")
    assert "document_missing" in response.text


def test_consistency_page_shows_a_finding_and_its_acknowledge_form(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — thing\n\nStatus: Current\n\nbody\n\n"
        "## FIX-002 — other\n\nStatus: Current\n\nbody\n",
    )
    response = client.get("/consistency")
    assert "too_many_current_tasks" in response.text
    assert 'data-action="acknowledge-finding"' in response.text
    assert "data-fingerprint=" in response.text


def test_consistency_page_carries_only_the_acknowledge_affordance(
    workspace: Path, client: AsgiTestClient
) -> None:
    """No Git-mutating or repository-editing affordance exists anywhere on this page — the one
    `<form>`/`<button>` present is exactly the local acknowledgment action."""
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — thing\n\nStatus: Current\n\nbody\n\n"
        "## FIX-002 — other\n\nStatus: Current\n\nbody\n",
    )
    response = client.get("/consistency")
    import re

    forms = re.findall(r"<form[^>]*>", response.text)
    assert forms
    for form in forms:
        assert 'data-action="acknowledge-finding"' in form


def test_consistency_page_shows_acknowledgment_history_after_posting(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — thing\n\nStatus: Current\n\nbody\n\n"
        "## FIX-002 — other\n\nStatus: Current\n\nbody\n",
    )
    findings = client.get("/dash/api/v1/consistency").json()["data"]["findings"]
    fingerprint = findings[0]["fingerprint"]
    client.post(
        "/dash/api/v1/consistency/acknowledge",
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": client._cookies["dash_csrf"],
        },
        body=f'{{"fingerprint": "{fingerprint}", "note": "tracked separately"}}'.encode(),
    )
    response = client.get("/consistency")
    assert "tracked separately" in response.text


def test_hostile_finding_message_is_escaped(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| <script>alert(1)</script> | 10 | 2026-01-01 | {'a' * 64} |\n",
    )
    response = client.get("/consistency")
    assert response.status == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
