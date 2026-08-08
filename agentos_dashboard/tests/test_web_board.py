"""PG-02 — the Board page: rendering, lanes, read-only posture, and escape-first XSS proof
(`SECURITY_MODEL.md` SC-04/SC-05; `TEST_STRATEGY.md` TC-06)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_board_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/board")
    assert response.status == 200
    assert "text/html" in (response.header("content-type") or "")
    assert "<h1>Board</h1>" in response.text


def test_board_page_has_primary_navigation_landmark(client: AsgiTestClient) -> None:
    response = client.get("/board")
    assert 'aria-label="Primary"' in response.text
    assert 'id="main-content"' in response.text
    assert 'aria-current="page"' in response.text


def test_board_page_carries_security_headers(client: AsgiTestClient) -> None:
    response = client.get("/board")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_board_page_shows_healthy_empty_lanes(client: AsgiTestClient) -> None:
    response = client.get("/board")
    assert "No Planned tasks" in response.text
    assert "No Current task" in response.text
    assert "No Done tasks" in response.text
    assert "No unclassified task headings" in response.text
    assert "No orchestration stages recorded" in response.text


def test_board_page_shows_engine_workflow_stage_strip(client: AsgiTestClient) -> None:
    response = client.get("/board")
    assert "plan-review" in response.text
    assert "push" in response.text


def test_board_page_has_no_mutation_affordance(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing.\n\n",
    )
    response = client.get("/board")
    assert "<button" not in response.text
    assert "<form" not in response.text
    assert "<input" not in response.text


def test_board_page_card_links_to_task_detail(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing.\n\n",
    )
    response = client.get("/board")
    assert 'href="/tasks/FIX-001"' in response.text


def test_hostile_task_title_is_escaped_not_executed(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## XSS-001 — <img src=x onerror=alert(1)>\n\nStatus: Current\n\nbody\n",
    )
    response = client.get("/board")
    assert response.status == 200
    assert "<img src=x onerror" not in response.text
    assert "&lt;img src=x onerror" in response.text


def test_unclassified_status_value_is_escaped(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## XSS-002 — odd\n\nStatus: <script>alert(1)</script>\n\nbody\n",
    )
    response = client.get("/board")
    assert response.status == 200
    assert "<script>alert" not in response.text
