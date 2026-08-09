"""Shared fixtures: real temporary directories and real temporary Git repositories.

`TEST_STRATEGY.md` §3 permits mocking only time, subprocess timeouts, and the clipboard.
Filesystem and Git are always real here — a traversal or symlink test against a mocked
filesystem would prove nothing about the adapter that actually runs.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.main import create_app
from agentos_dashboard.settings import DashboardSettings
from agentos_dashboard.tests._asgi_client import AsgiTestClient
from ai_workflow_engine.workflow import event_store
from ai_workflow_engine.workflow.events import VERDICT_STAGES, Verdict, WorkflowEvent, WorkflowStage

GIT_FIXTURE_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


def git(repo: Path, *args: str) -> str:
    """Direct Git for fixture setup only — never the code under test."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**GIT_FIXTURE_ENV, "HOME": str(repo)},
    )
    return result.stdout.strip()


def write(root: Path, relative: str, content: str) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A plain (non-Git) directory to act as a repository root."""
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture
def root(workspace: Path) -> RepositoryRoot:
    return RepositoryRoot.from_path(workspace)


@pytest.fixture
def git_repo(tmp_path: Path) -> Iterator[Path]:
    """A real Git repository with one commit on `main`."""
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    write(repo, "README.md", "first\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "--quiet", "-m", "first commit")
    yield repo


@pytest.fixture
def dashboard_app(workspace: Path) -> FastAPI:
    """A `create_app()` instance rooted at `workspace`, with no process lock (DASH-004)."""
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(workspace)})
    return create_app(settings)


@pytest.fixture
def client(dashboard_app: FastAPI) -> AsgiTestClient:
    """A stateful ASGI test client (cookies persist across calls) for `dashboard_app`."""
    return AsgiTestClient(dashboard_app)


@pytest.fixture
def git_dashboard_app(git_repo: Path) -> FastAPI:
    """A `create_app()` instance rooted at a real Git repository (`git_repo`), for the Git/
    handover/consistency pages' HTTP-level tests (DASH-006), which need real Git status/log/
    branch data rather than `workspace`'s plain non-Git directory."""
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(git_repo)})
    return create_app(settings)


@pytest.fixture
def git_client(git_dashboard_app: FastAPI) -> AsgiTestClient:
    return AsgiTestClient(git_dashboard_app)


@pytest.fixture
def isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolates `~` for `ai_workflow_engine.workflow.event_store` (DASH-005 remediation,
    `services.legacy_workflow`), so a test never reads or writes the real operator's
    `~/.ai-workflow-engine/workflow-runs/state/**` — the same isolation technique the engine's
    own `tests/test_workflow_event_store.py` uses."""
    home = tmp_path / "awe-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def write_self_governance(root: Path, project_id: str) -> Path:
    """A minimal `self-governance.yaml` naming `project.id` — the one field
    `services.legacy_workflow.read_project_id` extracts to address the engine's event store."""
    return write(root, "self-governance.yaml", f"project:\n  id: {project_id}\n")


def record_legacy_event(
    *,
    project_id: str,
    task_id: str,
    stage: WorkflowStage,
    verdict: Verdict | None = None,
    sequence: int,
    parent_digest: str | None,
    repository: str,
    head: str = "a" * 40,
    note: str = "",
) -> WorkflowEvent:
    """Append one real `ai_workflow_engine.workflow.event_store` event (never a dashboard-local
    fake) under whatever `~` `isolated_state_home` currently points at, mirroring the engine's own
    `tests/test_workflow_event_store.py::build_event` construction."""
    action = "verdict" if stage in VERDICT_STAGES else "completed"
    event = WorkflowEvent(
        schema_version="1.0",
        project_id=project_id,
        task_id=task_id,
        sequence=sequence,
        parent_digest=parent_digest,
        stage=stage,
        action=action,
        verdict=verdict,
        prompt_id=None,
        agent_run_id=None,
        head=head,
        note=note,
    )
    event_store.append(event, repository=repository)
    return event


def event_digest(event: WorkflowEvent) -> str:
    """The parent-digest one more event in the same chain must carry."""
    return hashlib.sha256(event_store._event_bytes(event)).hexdigest()
