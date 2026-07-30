"""Shared fixtures: real temporary directories and real temporary Git repositories.

`TEST_STRATEGY.md` §3 permits mocking only time, subprocess timeouts, and the clipboard.
Filesystem and Git are always real here — a traversal or symlink test against a mocked
filesystem would prove nothing about the adapter that actually runs.
"""

from __future__ import annotations

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
