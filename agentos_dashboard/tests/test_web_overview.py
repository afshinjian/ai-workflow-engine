"""PG-01 — the Overview page: rendering, healthy-empty states, and escape-first XSS proof
(`SECURITY_MODEL.md` SC-04/SC-05; `TEST_STRATEGY.md` TC-06)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_overview_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/")
    assert response.status == 200
    assert "text/html" in (response.header("content-type") or "")
    assert "<h1>Overview</h1>" in response.text


def test_overview_page_shows_healthy_empty_current_task(client: AsgiTestClient) -> None:
    response = client.get("/")
    assert "No Current task" in response.text


def test_overview_page_has_primary_navigation_landmark(client: AsgiTestClient) -> None:
    response = client.get("/")
    assert 'aria-label="Primary"' in response.text
    assert 'id="main-content"' in response.text


def test_overview_page_carries_security_headers(client: AsgiTestClient) -> None:
    response = client.get("/")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_static_stylesheet_is_served_from_this_app(client: AsgiTestClient) -> None:
    response = client.get("/static/style.css")
    assert response.status == 200
    assert "text/css" in (response.header("content-type") or "")


def test_static_script_is_served_from_this_app(client: AsgiTestClient) -> None:
    response = client.get("/static/app.js")
    assert response.status == 200


def test_hostile_blocker_text_is_escaped_not_executed(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/PROJECT_STATE.md",
        "Current Version: 1.0.0\n\n## Summary\n\nfixture\n\n"
        "## Blockers\n\n<script>alert('xss')</script>\n",
    )
    response = client.get("/")
    assert response.status == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text


def test_hostile_task_title_is_escaped_not_executed(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## XSS-001 — <img src=x onerror=alert(1)>\n\nStatus: Current\n\nbody\n",
    )
    response = client.get("/")
    assert response.status == 200
    assert "<img src=x onerror" not in response.text
    assert "&lt;img src=x onerror" in response.text


def test_javascript_uri_in_repository_text_is_not_rendered_as_a_link(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/PROJECT_STATE.md",
        "Current Version: 1.0.0\n\n## Summary\n\nfixture\n\n"
        "## Blockers\n\njavascript:alert(1)\n",
    )
    response = client.get("/")
    assert 'href="javascript:alert(1)"' not in response.text
