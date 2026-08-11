"""PG-12 — the Settings/About page: read-only rendering and zero mutation affordance (DASH-010,
`DECISIONS.md` DD-16)."""

from __future__ import annotations

from agentos_dashboard.api.lock import acquire_lock
from agentos_dashboard.main import create_app
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.tests._asgi_client import AsgiTestClient


def test_settings_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/settings")
    assert response.status == 200
    text = response.text
    assert "<h1>Settings &amp; About</h1>" in text
    assert "Repository" in text
    assert "Bind address" in text
    assert "Configured caps" in text
    assert "Process lock" in text
    assert "About" in text


def test_settings_page_shows_repo_root_bind_and_caps(client: AsgiTestClient, workspace) -> None:
    response = client.get("/settings")
    text = response.text
    assert str(workspace) in text
    assert "127.0.0.1" in text
    assert "Request body" in text
    assert "File read" in text
    assert "Head/tail excerpt" in text
    assert "Git subprocess timeout" in text


def test_settings_page_shows_lock_not_held_outside_a_real_process(client: AsgiTestClient) -> None:
    response = client.get("/settings")
    assert "NOT HELD" in response.text
    assert "normal server startup and `--check` both acquire it" in response.text


def test_settings_page_carries_security_headers(client: AsgiTestClient) -> None:
    response = client.get("/settings")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_settings_page_has_no_form_and_no_write_endpoint_reference(client: AsgiTestClient) -> None:
    """The only interactive control is the browser-side copy-config button: no `<form>`, and no
    reference to any `POST`-capable `/dash/api/v1` write endpoint anywhere in the page."""
    response = client.get("/settings")
    text = response.text
    assert "<form" not in text
    assert "/dash/api/v1/runs" not in text
    assert "/dash/api/v1/approvals" not in text
    assert "/dash/api/v1/findings" not in text
    assert "/dash/api/v1/notes" not in text
    assert "/dash/api/v1/snapshot/refresh" not in text


def test_settings_page_nav_link_is_enabled(client: AsgiTestClient) -> None:
    response = client.get("/")
    assert 'href="/settings"' in response.text
    disabled_placeholder = (
        '<li class="disabled" aria-disabled="true" title="Not yet available">Settings</li>'
    )
    assert disabled_placeholder not in response.text


def test_settings_page_is_active_in_nav_when_visited(client: AsgiTestClient) -> None:
    response = client.get("/settings")
    assert 'href="/settings" aria-current="page"' in response.text


def test_settings_page_escapes_a_hostile_repository_root(tmp_path) -> None:
    hostile_root = tmp_path / "<script>alert(1)</script>"
    hostile_root.mkdir(parents=True)
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(hostile_root)})
    response = AsgiTestClient(create_app(settings)).get("/settings")
    assert response.status == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_settings_page_reports_the_real_process_lock(workspace) -> None:
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(workspace)})
    lock = acquire_lock(settings.repo_root)
    try:
        response = AsgiTestClient(create_app(settings, lock=lock)).get("/settings")
    finally:
        lock.close()
    assert response.status == 200
    assert "HELD" in response.text
    assert str(lock.info.pid) in response.text
