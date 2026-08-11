"""DASH-010 final cross-page verification/evidence closure for DR-121 (staleness banner on every
page) and DR-122 (file+line provenance with raw fallback) — `STAGE_REGISTRY.md` §5 names DASH-010
their *final* delivery/evidence owner, distinct from the page-delivering stages (DASH-004 through
DASH-008) that already built the underlying per-page behavior as they shipped each page
(`stage-prompts/DASH-010.md`: "DASH-010 does not re-build them, and does not claim implementation
credit those stages' own completion records already hold"). This module verifies the two
requirements hold across the whole delivered page set rather than wherever one earlier stage
happened to sample them.
"""

from __future__ import annotations

import re
from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.e2e.conftest import (
    E2E_GOVERNANCE_DOC_ID,
    E2E_TASK_ID,
    create_fixture_run,
    csrf_headers,
)

_WEB_ROUTES_SOURCE = (Path(__file__).resolve().parents[2] / "web" / "routes.py").read_text(
    encoding="utf-8"
)


# ---------------------------------------------------------------------------
# DR-121: snapshot staleness banner on every page
# ---------------------------------------------------------------------------


def test_dr121_every_html_page_route_passes_the_shared_snapshot_into_its_template() -> None:
    """Structural half: the persistent header's staleness banner (`base.html`) reads
    `snapshot.is_stale()`, so every page must hand the same `cache.get()` result to its
    template — checked over the whole route module's source, not by sampling one page."""
    html_route_count = len(re.findall(r"response_class=HTMLResponse", _WEB_ROUTES_SOURCE))
    snapshot_context_count = len(re.findall(r'"snapshot":\s*snapshot', _WEB_ROUTES_SOURCE))
    assert html_route_count > 0
    assert snapshot_context_count == html_route_count


def test_dr121_every_delivered_page_shows_real_cache_staleness_until_explicit_refresh(
    e2e_repo: Path, e2e_client: AsgiTestClient
) -> None:
    """Behavioral proof over all 14 routes, including DASH-007/008/010 pages.

    This drives the real ``SnapshotCache`` request path. It would fail under the former silent
    stale-cache rebuild even though rendering ``base.html`` directly appeared to pass.
    """
    run_uuid = create_fixture_run(e2e_client)
    pages = (
        "/",
        "/board",
        f"/tasks/{E2E_TASK_ID}",
        "/stages",
        "/runs",
        f"/runs/{run_uuid}",
        "/evidence",
        "/git",
        "/governance",
        f"/governance/{E2E_GOVERNANCE_DOC_ID}",
        "/handover",
        "/audit",
        "/consistency",
        "/settings",
    )
    banner = "STALE — refresh to update"
    for page in pages:
        assert banner not in e2e_client.get(page).text, page

    task_queue = e2e_repo / "docs" / "TASK_QUEUE.md"
    task_queue.write_text(task_queue.read_text(encoding="utf-8") + "\n<!-- changed -->\n")
    for page in pages:
        response = e2e_client.get(page)
        assert response.status == 200, page
        assert banner in response.text, page

    refreshed = e2e_client.post(
        "/dash/api/v1/snapshot/refresh", headers=csrf_headers(e2e_client), body=b"{}"
    )
    assert refreshed.status == 200
    for page in pages:
        assert banner not in e2e_client.get(page).text, page


# ---------------------------------------------------------------------------
# DR-122: every parsed value links to its file+line; raw fallback on parse failure
# ---------------------------------------------------------------------------


def test_dr122_board_cards_carry_file_and_line_provenance(e2e_client: AsgiTestClient) -> None:
    response = e2e_client.get("/board")
    assert "docs/TASK_QUEUE.md:" in response.text


def test_dr122_task_detail_carries_file_and_line_provenance(e2e_client: AsgiTestClient) -> None:
    response = e2e_client.get(f"/tasks/{E2E_TASK_ID}")
    assert "Recorded at docs/TASK_QUEUE.md:" in response.text


def test_dr122_governance_document_offers_a_raw_source_fallback(
    e2e_client: AsgiTestClient,
) -> None:
    rendered = e2e_client.get("/governance/task-queue")
    assert rendered.status == 200
    assert 'href="/governance/task-queue?raw=1"' in rendered.text

    raw = e2e_client.get("/governance/task-queue?raw=1")
    assert raw.status == 200
    assert '<pre class="mono">' in raw.text


def test_dr122_governance_search_results_carry_file_and_line_provenance(
    e2e_client: AsgiTestClient,
) -> None:
    response = e2e_client.get("/governance?q=fixture")
    assert response.status == 200
    assert re.search(r'/governance/task-queue">[^<]+:\d+<', response.text) is not None


def test_dr122_overview_stages_orchestration_handover_and_consistency_render_provenance(
    e2e_client: AsgiTestClient, e2e_repo: Path
) -> None:
    overview = e2e_client.get("/").text
    assert "docs/PROJECT_STATE.md:" in overview
    assert "docs/TASK_QUEUE.md:" in overview
    assert 'href="/governance/project-state?raw=1"' in overview

    stages = e2e_client.get("/stages").text
    assert "docs/agentos-dashboard/STAGE_REGISTRY.md:" in stages
    assert "Raw registry source fallback" in stages

    orchestration = e2e_repo / "docs" / "implementation" / "orchestration"
    orchestration.mkdir(parents=True, exist_ok=True)
    (orchestration / "implementation-state.yaml").write_text(
        "feature_id: fixture\nstages:\n  ORCH-001:\n    title: fixture\n"
        "    status: complete\n    prerequisites: []\n    blockers: []\n    evidence: []\n",
        encoding="utf-8",
    )
    # Explicit refresh makes the new authoritative source part of the held snapshot.
    assert (
        e2e_client.post(
            "/dash/api/v1/snapshot/refresh", headers=csrf_headers(e2e_client), body=b"{}"
        ).status
        == 200
    )
    board = e2e_client.get("/board").text
    assert "docs/implementation/orchestration/implementation-state.yaml:3" in board
    assert "Raw orchestration source fallback" in board

    handover = e2e_client.get("/handover").text
    assert "handover/PROJECT_CHECKSUM.md:" in handover
    assert "Raw manifest source fallback" in handover

    # Force a two-sided finding and prove both parsed task records retain line provenance.
    current_mirror = e2e_repo / "docs" / "current_task.md"
    current_mirror.write_text("## DASH-001 — fixture\n\nStatus: Done\n", encoding="utf-8")
    consistency = e2e_client.get("/consistency").text
    assert "docs/TASK_QUEUE.md:" in consistency
    assert "docs/current_task.md:" in consistency


def test_dr122_run_evidence_still_renders_when_no_report_path_was_recorded(
    e2e_client: AsgiTestClient,
) -> None:
    """SC-34: a run recorded with no verifiable report path must degrade to a typed state, never
    a crash — the evidence-page analogue of a governance parse failure's raw fallback."""
    run_uuid = create_fixture_run(e2e_client)
    response = e2e_client.get("/evidence")
    assert response.status == 200
    assert run_uuid in response.text
