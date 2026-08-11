"""TC-16 (`TEST_STRATEGY.md`): the delivered page set driven read-only against the real
`ai-workflow-engine` working tree — the repository this dashboard instance is most often actually
pointed at, per `MVP_SCOPE.md` §4's cold-start acceptance criterion.

Scope is deliberately every page that reads only Git/the filesystem, not the four pages backed by
the local `dashboard.db` mirror (Runs, Run detail, Evidence, Audit): opening that mirror creates
`data/agentos_dashboard/**` on first use (`storage/db.py::connect`), and doing that against the
real repository's working tree — rather than a disposable `tmp_path` fixture — is not something a
read-only verification pass should do as a side effect, even though the path is git-ignored and
is the dashboard's own sanctioned local storage (`SECURITY_MODEL.md` §5). Those four pages are
already covered end-to-end against the constructed fixture repository in
`test_full_page_set_fixture_repo.py`; `test_dash_task_stage_contract_is_shown`
(`tests/test_web_task_detail.py`) already established the precedent of pointing `create_app` at
this real repository for a non-database page.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.main import create_app
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.tests._asgi_client import AsgiTestClient

_REAL_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_DB_PATH = _REAL_REPO_ROOT / "data" / "agentos_dashboard" / "dashboard.db"
_REAL_DB_EXISTED_BEFORE_TESTS = _REAL_DB_PATH.exists()

_REAL_REPO_PAGES = (
    "/",
    "/board",
    "/tasks/DASH-001",
    "/stages",
    "/git",
    "/governance",
    "/governance/task-queue",
    "/handover",
    "/consistency",
    "/settings",
)


@pytest.fixture(scope="module")
def real_repo_client() -> AsgiTestClient:
    root = RepositoryRoot.from_path(_REAL_REPO_ROOT)
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(root.path)})
    app: FastAPI = create_app(settings)
    return AsgiTestClient(app)


def test_every_non_database_page_renders_200_against_the_real_repository(
    real_repo_client: AsgiTestClient,
) -> None:
    failures = []
    for page in _REAL_REPO_PAGES:
        response = real_repo_client.get(page)
        if response.status != 200:
            failures.append((page, response.status))
    assert failures == [], f"pages that did not render 200 against the real repository: {failures}"


def test_the_real_repository_never_gains_a_dashboard_database_from_this_walk(
    real_repo_client: AsgiTestClient,
) -> None:
    for page in _REAL_REPO_PAGES:
        real_repo_client.get(page)
    assert _REAL_DB_PATH.exists() is _REAL_DB_EXISTED_BEFORE_TESTS


def test_the_overview_page_reflects_the_real_repositorys_head(
    real_repo_client: AsgiTestClient,
) -> None:
    response = real_repo_client.get("/")
    assert response.status == 200
    assert "HEAD:" in response.text


def test_a_stable_historical_dashboard_task_appears_on_its_own_detail_page(
    real_repo_client: AsgiTestClient,
) -> None:
    # DASH-001 is a completed program invariant. Do not couple this E2E test to whichever task is
    # transiently Current while the suite runs.
    response = real_repo_client.get("/tasks/DASH-001")
    assert response.status == 200
    assert "DASH-001" in response.text
