"""PG-04 (`UI_SPEC.md`): the `/stages` page."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient


def test_stages_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/stages")
    assert response.status == 200
    text = response.text
    assert "Stages &amp; Prompts" in text or "Stages & Prompts" in text
    assert "DASH-001" in text
    assert "DASH-010" in text


def test_stages_page_shows_generate_button_disabled_with_reasons_when_unmet(
    client: AsgiTestClient,
) -> None:
    response = client.get("/stages")
    text = response.text
    assert 'data-action="generate-prompt"' in text
    assert "disabled" in text
    assert "Disabled — unmet:" in text


def test_prompt_frontend_surfaces_generate_copy_and_export_failures() -> None:
    script = (Path(__file__).resolve().parents[1] / "web/static/app.js").read_text(encoding="utf-8")
    assert "generation request failed — no prompt was generated" in script
    assert "Copy failed — no prompt bytes were copied" in script
    assert "Export failed — no download was started" in script
