"""Fixtures for the DASH-010 end-to-end suite: a constructed repository seeded with the minimum
governance/handover surface every delivered page reads from, so a full page-set walk exercises
real parsers rather than only empty-state branches (`TEST_STRATEGY.md` TC-16)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI

from agentos_dashboard.main import create_app
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA
from agentos_dashboard.services.stages import OPEN_QUESTIONS_PATH, STAGE_REGISTRY_PATH
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write, write_self_governance

E2E_TASK_ID = "DASH-001"
E2E_GOVERNANCE_DOC_ID = "task-queue"


def _stage_registry_text() -> str:
    lines = [
        "## 3. Registry",
        "",
        "| Stage | Title | Role | State | Branch | Prompt |",
        "|---|---|---|---|---|---|",
    ]
    for index, schema in enumerate(STAGE_SCHEMA):
        state = "COMPLETE" if index == 0 else "NOT_STARTED"
        lines.append(
            f"| {schema.stage_id} | {schema.title} | {schema.role} | {state} | "
            f"`{schema.branch}` | `{schema.prompt_path}` |"
        )
    lines += [
        "",
        "## 4. Authorization Log",
        "",
        f'| 2026-01-01 | {STAGE_SCHEMA[0].stage_id} | Human Owner: "I authorize '
        f'{STAGE_SCHEMA[0].stage_id}." | Human Owner |',
        "",
    ]
    return "\n".join(lines)


def _open_questions_text() -> str:
    return "## Open\n\nNone currently open.\n\n## Resolved\n\nNone.\n"


def _task_queue_text() -> str:
    return (
        f"## {E2E_TASK_ID} — E2E fixture task\n\n"
        "Status: Current\n\n"
        "Fixture task used to drive the Board and Task detail pages end-to-end "
        "(`TEST_STRATEGY.md` TC-16).\n"
    )


def _project_state_text() -> str:
    return (
        "# Project State\n\nCurrent Version: 0.0.0\n\n"
        "## Summary\n\nFixture project state for the E2E suite.\n\n"
        "## Blockers\n\n"
    )


def _decision_log_text() -> str:
    return "# Decision Log\n\n## 2026-01-01 — E2E fixture decision\n\nFixture entry.\n"


def _write_handover_pair(repo: Path) -> None:
    narrative = "# Project Handover\n\nFixture narrative for the DASH-010 end-to-end suite.\n"
    write(repo, "handover/PROJECT_HANDOVER.md", narrative)
    narrative_bytes = narrative.encode("utf-8")
    digest = hashlib.sha256(narrative_bytes).hexdigest()
    manifest = (
        "# Project Checksum Manifest\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(narrative_bytes)} | 2026-01-01 | {digest} |\n"
    )
    write(repo, "handover/PROJECT_CHECKSUM.md", manifest)


@pytest.fixture
def e2e_repo(git_repo: Path) -> Path:
    """A real Git repository (one commit on `main`, from the shared `git_repo` fixture) seeded
    with governance, task, and handover documents so every delivered page has real content to
    render, not only its empty-state branch."""
    write_self_governance(git_repo, "e2e-fixture")
    write(git_repo, "docs/TASK_QUEUE.md", _task_queue_text())
    write(git_repo, "docs/current_task.md", _task_queue_text())
    write(git_repo, "docs/remaining_tasks.md", _task_queue_text())
    write(git_repo, "docs/PROJECT_STATE.md", _project_state_text())
    write(git_repo, "docs/DECISION_LOG.md", _decision_log_text())
    write(git_repo, STAGE_REGISTRY_PATH, _stage_registry_text())
    write(git_repo, OPEN_QUESTIONS_PATH, _open_questions_text())
    _write_handover_pair(git_repo)
    return git_repo


@pytest.fixture
def e2e_app(e2e_repo: Path) -> FastAPI:
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(e2e_repo)})
    return create_app(settings)


@pytest.fixture
def e2e_client(e2e_app: FastAPI) -> AsgiTestClient:
    return AsgiTestClient(e2e_app)


def csrf_headers(client: AsgiTestClient) -> dict[str, str]:
    """Prime the CSRF double-submit cookie (SC-03) and return the header set every POST needs."""
    client.get("/dash/api/v1/health")
    return {"X-CSRF-Token": client._cookies["dash_csrf"], "Content-Type": "application/json"}


def create_fixture_run(client: AsgiTestClient) -> str:
    """Record one manual run via the real `POST /dash/api/v1/runs` path (EP-22) so the Runs,
    Run detail, Evidence, and Audit pages all have a real row to render. Returns the run UUID."""
    headers = csrf_headers(client)
    body = json.dumps(
        {
            "client_token": "10000000-0000-4000-8000-0000000000e2",
            "stage_id": E2E_TASK_ID,
            "tool": "claude",
            "started_at": "2026-01-01T00:00:00+00:00",
            "reported_result": "COMPLETED",
            "validation_summary": "pytest: 1 passed",
        }
    ).encode()
    response = client.post("/dash/api/v1/runs", headers=headers, body=body)
    assert response.status == 200, response.text
    uuid: str = response.json()["data"]["uuid"]
    return uuid
