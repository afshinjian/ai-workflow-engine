"""Focused GOV-AUTO-04 tests for the shared branch-preparation library
(`scripts/lib/branch_prepare.sh`), sourced directly against disposable Git repositories rather
than through either wrapper script, so every refusal path (dirty worktree, wrong starting branch,
divergent existing branch) can be exercised in isolation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "scripts" / "lib" / "branch_prepare.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "LC_ALL": "C",
}


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "lib repo"  # deliberate space: paths with spaces must work
    repo_dir.mkdir()
    git(repo_dir, "init", "-b", "main")
    git(repo_dir, "config", "user.name", "Test")
    git(repo_dir, "config", "user.email", "test@example.invalid")
    (repo_dir / "README.md").write_text("baseline\n", encoding="utf-8")
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "-m", "chore: baseline")
    return repo_dir


def call_function(func: str, *args: str) -> subprocess.CompletedProcess[str]:
    script = f'set -euo pipefail; source "{LIB}"; {func} ' + " ".join(f'"{arg}"' for arg in args)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
    )


# =====================================================================================
# workflow_registered_branch
# =====================================================================================


def _write_registry(repo_dir: Path, relative: str, task_id: str, branch: str) -> None:
    path = repo_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Registry\n\n"
        "## 4. Registry\n\n"
        "| Stage | Title | Role | State | Branch | Prompt |\n"
        "|---|---|---|---|---|---|\n"
        f"| {task_id} | title | role | AUTHORIZED | `{branch}` | `p.md` |\n",
        encoding="utf-8",
    )


def test_registered_branch_found_in_workflow_automation_registry(repo: Path) -> None:
    _write_registry(
        repo, "docs/workflow-automation/STAGE_REGISTRY.md", "AUTO-002", "feature/auto-002"
    )
    result = call_function("workflow_registered_branch", str(repo), "AUTO-002")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "feature/auto-002"


def test_registered_branch_found_in_dashboard_registry(repo: Path) -> None:
    _write_registry(
        repo,
        "docs/agentos-dashboard/STAGE_REGISTRY.md",
        "DASH-002",
        "feature/dash-002-repo-adapter",
    )
    result = call_function("workflow_registered_branch", str(repo), "DASH-002")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "feature/dash-002-repo-adapter"


def test_registered_branch_empty_when_no_row(repo: Path) -> None:
    result = call_function("workflow_registered_branch", str(repo), "GOV-AUTO-04")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_registered_branch_empty_when_task_absent_from_present_registry(repo: Path) -> None:
    _write_registry(
        repo, "docs/workflow-automation/STAGE_REGISTRY.md", "AUTO-002", "feature/auto-002"
    )
    result = call_function("workflow_registered_branch", str(repo), "AUTO-003")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


# =====================================================================================
# workflow_prepare_branch
# =====================================================================================


def test_prepare_is_noop_when_required_equals_default(repo: Path) -> None:
    before = git(repo, "rev-parse", "HEAD")
    result = call_function("workflow_prepare_branch", str(repo), "main", "main")
    assert result.returncode == 0, result.stderr
    assert git(repo, "branch", "--show-current") == "main"
    assert git(repo, "rev-parse", "HEAD") == before


def test_prepare_is_noop_when_required_branch_empty(repo: Path) -> None:
    result = call_function("workflow_prepare_branch", str(repo), "main", "")
    assert result.returncode == 0, result.stderr
    assert git(repo, "branch", "--show-current") == "main"


def test_prepare_creates_branch_from_clean_default(repo: Path) -> None:
    head_before = git(repo, "rev-parse", "HEAD")
    result = call_function("workflow_prepare_branch", str(repo), "main", "feature/auto-002")
    assert result.returncode == 0, result.stderr
    assert git(repo, "branch", "--show-current") == "feature/auto-002"
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "rev-parse", "main") == head_before


def test_prepare_is_idempotent_when_branch_already_matches_head(repo: Path) -> None:
    git(repo, "branch", "feature/auto-002")
    result = call_function("workflow_prepare_branch", str(repo), "main", "feature/auto-002")
    assert result.returncode == 0, result.stderr
    assert git(repo, "branch", "--show-current") == "feature/auto-002"


def test_prepare_switches_when_already_on_required_branch(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/auto-002")
    result = call_function("workflow_prepare_branch", str(repo), "main", "feature/auto-002")
    assert result.returncode == 0, result.stderr
    assert git(repo, "branch", "--show-current") == "feature/auto-002"


def test_prepare_refuses_dirty_worktree(repo: Path) -> None:
    (repo / "dirty.txt").write_text("wip\n", encoding="utf-8")
    result = call_function("workflow_prepare_branch", str(repo), "main", "feature/auto-002")
    assert result.returncode == 1
    assert "not clean" in result.stderr
    assert git(repo, "branch", "--show-current") == "main"
    assert not (repo / ".git" / "refs" / "heads" / "feature" / "auto-002").exists()


def test_prepare_refuses_when_not_on_default_branch(repo: Path) -> None:
    git(repo, "checkout", "-b", "some-other-branch")
    result = call_function("workflow_prepare_branch", str(repo), "main", "feature/auto-002")
    assert result.returncode == 1
    assert "expected to be on" in result.stderr
    assert git(repo, "branch", "--show-current") == "some-other-branch"


def test_prepare_refuses_when_existing_branch_diverges(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/auto-002")
    (repo / "extra.txt").write_text("extra\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "test: unrelated divergent commit")
    git(repo, "checkout", "main")

    result = call_function("workflow_prepare_branch", str(repo), "main", "feature/auto-002")
    assert result.returncode == 1
    assert "diverging" in result.stderr
    assert git(repo, "branch", "--show-current") == "main"


# =====================================================================================
# workflow_verify_branch
# =====================================================================================


def test_verify_passes_when_no_registry_row(repo: Path) -> None:
    result = call_function("workflow_verify_branch", str(repo), "GOV-AUTO-04", "main")
    assert result.returncode == 0, result.stderr


def test_verify_passes_when_branch_matches(repo: Path) -> None:
    _write_registry(
        repo, "docs/workflow-automation/STAGE_REGISTRY.md", "AUTO-002", "feature/auto-002"
    )
    result = call_function("workflow_verify_branch", str(repo), "AUTO-002", "feature/auto-002")
    assert result.returncode == 0, result.stderr


def test_verify_fails_when_branch_mismatches(repo: Path) -> None:
    _write_registry(
        repo, "docs/workflow-automation/STAGE_REGISTRY.md", "AUTO-002", "feature/auto-002"
    )
    result = call_function("workflow_verify_branch", str(repo), "AUTO-002", "main")
    assert result.returncode == 1
    assert "AUTO-002" in result.stderr
    assert "feature/auto-002" in result.stderr
    assert "main" in result.stderr


def test_library_contains_no_eval_push_merge_or_reset() -> None:
    body = LIB.read_text()
    executable = "\n".join(
        line for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )
    assert "eval " not in executable
    assert " git push" not in executable
    assert " git merge" not in executable
    assert "--hard" not in executable
    assert "branch -D" not in executable
    assert "branch -d" not in executable
