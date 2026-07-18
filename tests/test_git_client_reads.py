import subprocess
from pathlib import Path

import pytest

from ai_workflow_engine.exceptions import GitCommandError
from ai_workflow_engine.git.client import GitClient


def git(repo: object, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_staged_names(repository: Path) -> None:
    client = GitClient(repository)
    assert client.staged_names() == []
    (repository / "a.txt").write_text("x\n", encoding="utf-8")
    (repository / "b.txt").write_text("y\n", encoding="utf-8")
    git(repository, "add", "a.txt", "b.txt")
    assert client.staged_names() == ["a.txt", "b.txt"]


def test_commit_parent_and_change_names(repository: Path) -> None:
    client = GitClient(repository)
    parent = client.head()
    (repository / "c.txt").write_text("z\n", encoding="utf-8")
    git(repository, "add", "c.txt")
    git(repository, "commit", "-m", "add c")
    new_head = client.head()
    assert client.commit_parent(new_head) == parent
    assert client.commit_change_names(parent, new_head) == ["c.txt"]


def test_commit_message(repository: Path) -> None:
    client = GitClient(repository)
    git(repository, "commit", "--allow-empty", "-m", "a multi\nline message")
    assert client.commit_message(client.head()).rstrip("\n") == "a multi\nline message"


def test_diff_check_clean_and_dirty(repository: Path) -> None:
    client = GitClient(repository)
    assert client.diff_check() is True
    # `git diff --check` inspects UNSTAGED changes to tracked files; a conflict marker in an
    # unstaged edit to a tracked file trips it.
    (repository / "pyproject.toml").write_text(
        'version = "1.0.0"\n<<<<<<< HEAD\n', encoding="utf-8"
    )
    assert client.diff_check() is False


def test_strict_left_right_count(repository_with_remote: Path) -> None:
    client = GitClient(repository_with_remote)
    # In sync with upstream: (behind, ahead) == (0, 0).
    assert client.strict_left_right_count() == (0, 0)
    (repository_with_remote / "d.txt").write_text("z\n", encoding="utf-8")
    git(repository_with_remote, "add", "d.txt")
    git(repository_with_remote, "commit", "-m", "ahead by one")
    assert client.strict_left_right_count() == (0, 1)


def test_read_only_methods_reject_writes_via_run(repository: Path) -> None:
    # The private guard still rejects any non-allowlisted form, proving the new methods did not
    # widen the surface.
    client = GitClient(repository)
    with pytest.raises(GitCommandError):
        client._run(["commit", "-m", "nope"])
    with pytest.raises(GitCommandError):
        client._run(["push"])
