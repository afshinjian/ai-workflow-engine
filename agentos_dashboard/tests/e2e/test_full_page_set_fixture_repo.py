"""TC-16 (`TEST_STRATEGY.md`): the full delivered page set, driven in one flow against a
constructed fixture repository — real Git, real governance/task/handover documents, and one real
run record created through the write API — rather than one page tested in isolation."""

from __future__ import annotations

import re

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.e2e.conftest import (
    E2E_GOVERNANCE_DOC_ID,
    E2E_TASK_ID,
    create_fixture_run,
)


def test_every_delivered_page_renders_200_against_the_fixture_repository(
    e2e_client: AsgiTestClient,
) -> None:
    run_uuid = create_fixture_run(e2e_client)

    pages = [
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
    ]
    failures = []
    for page in pages:
        response = e2e_client.get(page)
        if response.status != 200:
            failures.append((page, response.status))
    assert failures == [], f"pages that did not render 200: {failures}"


def test_every_delivered_page_renders_its_expected_integrated_content(
    e2e_client: AsgiTestClient,
) -> None:
    run_uuid = create_fixture_run(e2e_client)
    expected = {
        "/": (
            "<h1>Overview</h1>",
            "Fixture project state",
            "pytest: 1 passed",
            "run_created",
        ),
        "/board": ("<h1>Board</h1>", E2E_TASK_ID),
        f"/tasks/{E2E_TASK_ID}": ("<h1>DASH-001", "Recorded at docs/TASK_QUEUE.md:"),
        "/stages": ("<h1>Stages &amp; Prompts</h1>", "Stage registry"),
        "/runs": ("<h1>Runs</h1>", run_uuid),
        f"/runs/{run_uuid}": ("<h1>Run", "pytest: 1 passed"),
        "/evidence": ("<h1>Evidence</h1>", run_uuid),
        "/git": ("<h1>Git</h1>", "main"),
        "/governance": ("<h1>Governance</h1>", "Task Queue"),
        f"/governance/{E2E_GOVERNANCE_DOC_ID}": ("Task Queue", "E2E fixture task"),
        "/handover": ("<h1>Handover</h1>", "VERIFIED"),
        "/audit": ("<h1>Audit</h1>", "run_created"),
        "/consistency": ("<h1>Consistency</h1>", "Findings"),
        "/settings": ("<h1>Settings &amp; About</h1>", "127.0.0.1"),
    }
    for page, markers in expected.items():
        response = e2e_client.get(page)
        assert response.status == 200, page
        for marker in markers:
            assert marker in response.text, (page, marker)


def test_every_delivered_page_carries_the_security_baseline(e2e_client: AsgiTestClient) -> None:
    """SC-03/SC-04/SC-05 must hold on every page, not only the ones DASH-009 happened to sample."""
    run_uuid = create_fixture_run(e2e_client)
    pages = [
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
    ]
    for page in pages:
        response = e2e_client.get(page)
        assert response.header("content-security-policy") is not None, page
        assert response.header("x-content-type-options") == "nosniff", page
        assert response.header("cache-control") == "no-store", page


def test_every_enabled_primary_navigation_link_resolves(e2e_client: AsgiTestClient) -> None:
    response = e2e_client.get("/")
    nav = response.text.split('<nav aria-label="Primary">', 1)[1].split("</nav>", 1)[0]
    links = tuple(dict.fromkeys(re.findall(r'href="([^"#]+)(?:#[^"]*)?"', nav)))
    assert links
    for link in links:
        linked = e2e_client.get(link)
        assert linked.status == 200, link
    assert "Not yet available" not in nav


def test_the_fixture_task_appears_on_the_board_and_its_own_detail_page(
    e2e_client: AsgiTestClient,
) -> None:
    board = e2e_client.get("/board")
    assert E2E_TASK_ID in board.text

    detail = e2e_client.get(f"/tasks/{E2E_TASK_ID}")
    assert detail.status == 200
    assert E2E_TASK_ID in detail.text


def test_the_fixture_run_appears_on_the_runs_evidence_and_audit_pages(
    e2e_client: AsgiTestClient,
) -> None:
    run_uuid = create_fixture_run(e2e_client)

    runs = e2e_client.get("/runs")
    assert run_uuid in runs.text

    detail = e2e_client.get(f"/runs/{run_uuid}")
    assert detail.status == 200

    evidence = e2e_client.get("/evidence")
    assert evidence.status == 200
    assert run_uuid in evidence.text

    audit = e2e_client.get("/audit")
    assert audit.status == 200
    assert "run_created" in audit.text
