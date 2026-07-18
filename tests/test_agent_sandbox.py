from pathlib import Path

import pytest

from ai_workflow_engine.agents.sandbox import (
    SandboxError,
    SandboxGit,
    SnapshotUnavailable,
    create_sandbox,
    is_managed,
    teardown,
)
from ai_workflow_engine.git.client import GitClient


def _head(repository: Path) -> str:
    return GitClient(repository).head()


def test_create_sandbox_clones_and_checks_out_head(repository: Path) -> None:
    sandbox = create_sandbox(repository, _head(repository))
    try:
        assert sandbox.exists()
        assert is_managed(sandbox)
        # The sandbox is a real worktree detached at the recorded head.
        assert GitClient(sandbox).head() == _head(repository)
        # It is created outside the target repository.
        assert not sandbox.resolve().is_relative_to(repository.resolve())
    finally:
        teardown(sandbox)


def test_snapshot_unavailable_for_missing_commit(repository: Path) -> None:
    with pytest.raises(SnapshotUnavailable):
        create_sandbox(repository, "0" * 40)


def test_teardown_removes_and_unregisters(repository: Path) -> None:
    sandbox = create_sandbox(repository, _head(repository))
    parent = sandbox.parent
    teardown(sandbox)
    assert not parent.exists()
    assert not is_managed(sandbox)
    teardown(sandbox)  # idempotent, no raise


def test_sandbox_git_refuses_unmanaged_directory(repository: Path, tmp_path: Path) -> None:
    with pytest.raises(SandboxError):
        SandboxGit(tmp_path)
    with pytest.raises(SandboxError):
        SandboxGit(repository)


def test_sandbox_git_reports_changed_paths(repository: Path) -> None:
    sandbox = create_sandbox(repository, _head(repository))
    try:
        (sandbox / "docs" / "PROJECT_STATE.md").write_text("changed\n", encoding="utf-8")
        (sandbox / "newfile.txt").write_text("new\n", encoding="utf-8")
        git = SandboxGit(sandbox)
        git.stage_all()
        assert git.changed_paths() == ["docs/PROJECT_STATE.md", "newfile.txt"]
        patch = git.diff_cached_binary()
        assert b"newfile.txt" in patch
    finally:
        teardown(sandbox)


def test_sandbox_git_apply_round_trip(repository: Path) -> None:
    sandbox = create_sandbox(repository, _head(repository))
    try:
        (sandbox / "newfile.txt").write_text("new\n", encoding="utf-8")
        git = SandboxGit(sandbox)
        git.stage_all()
        patch = git.diff_cached_binary()
        # Reset the sandbox and confirm the captured patch re-applies cleanly.
        (sandbox / "newfile.txt").unlink()
        import subprocess

        subprocess.run(
            ["git", "-C", str(sandbox), "reset", "--hard"], check=True, capture_output=True
        )
        git.apply_check(patch)
        git.apply(patch)
        assert (sandbox / "newfile.txt").read_text(encoding="utf-8") == "new\n"
    finally:
        teardown(sandbox)
