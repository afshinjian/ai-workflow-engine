"""PG-02 — the Board page: rendering, lanes, read-only posture, and escape-first XSS proof
(`SECURITY_MODEL.md` SC-04/SC-05; `TEST_STRATEGY.md` TC-06)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import record_legacy_event, write, write_self_governance


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


def test_board_page_stage_strip_is_labeled_reference_only(client: AsgiTestClient) -> None:
    """DASH-005 remediation item 4: the global seven-stage strip must not read as any task's
    actual state."""
    response = client.get("/board")
    assert "reference diagram" in response.text
    assert "never a per-task computed state" in response.text
    assert "shown on its card below" in response.text


def test_board_card_shows_no_persisted_history_without_legacy_events(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    response = client.get("/board")
    assert "Legacy workflow" in response.text
    assert "NO PERSISTED HISTORY" in response.text or "UNAVAILABLE" in response.text


def test_board_card_shows_its_own_derived_legacy_stage(
    workspace: Path, client: AsgiTestClient, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    response = client.get("/board")
    assert "implementation" in response.text
