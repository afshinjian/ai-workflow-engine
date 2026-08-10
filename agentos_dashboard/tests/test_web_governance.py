"""PG-08 (`UI_SPEC.md`): the `/governance` and `/governance/{doc_id}` pages."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_governance_index_lists_documents(client: AsgiTestClient) -> None:
    response = client.get("/governance")
    assert response.status == 200
    assert "Agent Protocol" in response.text
    assert "self-governance.yaml" in response.text


def test_governance_doc_page_unknown_id_is_404(client: AsgiTestClient) -> None:
    response = client.get("/governance/not-a-real-doc")
    assert response.status == 404
    assert "not found" in response.text.lower()


def test_governance_doc_page_renders_known_document(
    client: AsgiTestClient, workspace: Path
) -> None:
    write(workspace, "README.md", "# Hello\n\nSome content.\n")
    response = client.get("/governance/readme")
    assert response.status == 200
    assert "<h1" in response.text


def test_governance_doc_raw_toggle(client: AsgiTestClient, workspace: Path) -> None:
    write(workspace, "README.md", "# Hello\n\nSome content.\n")
    response = client.get("/governance/readme?raw=1")
    assert response.status == 200
    assert "<pre" in response.text
    assert "Raw source" not in response.text  # already viewing raw; link points back to rendered


def test_governance_search_page_escapes_hostile_content(
    client: AsgiTestClient, workspace: Path
) -> None:
    """Acceptance: search against hostile (script-injection-shaped) document content renders as
    inert escaped text on the actual HTML page."""
    write(workspace, "README.md", "before <script>alert(1)</script> needle after\n")
    response = client.get("/governance?q=needle")
    assert response.status == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_governance_search_page_query_too_long(client: AsgiTestClient) -> None:
    response = client.get("/governance?q=" + "x" * 300)
    assert response.status == 200
    assert "Query too long" in response.text


def test_governance_search_page_refuses_traversal_shaped_query(client: AsgiTestClient) -> None:
    response = client.get("/governance?q=../../etc/passwd")
    assert response.status == 200
    assert "Traversal-shaped queries are not allowed" in response.text


def test_governance_doc_page_escapes_hostile_body_content(
    client: AsgiTestClient, workspace: Path
) -> None:
    write(workspace, "docs/AGENT_PROTOCOL.md", "# T\n\n<script>alert(1)</script> text\n")
    response = client.get("/governance/agent-protocol")
    assert response.status == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
