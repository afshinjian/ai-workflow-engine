import inspect
import subprocess
from pathlib import Path

import pytest

from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.writer import GitWriteError, GitWriter


def git(repo: object, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_read_only_forms_unchanged() -> None:
    # The read-only allowlist must be exactly these eight single-element forms (byte-unchanged).
    assert GitClient.READ_ONLY_FORMS == (
        ("rev-parse",),
        ("status",),
        ("symbolic-ref",),
        ("rev-list",),
        ("show",),
        ("diff",),
        ("ls-files",),
        ("cat-file",),
    )


def test_writer_has_no_arbitrary_argv_entry_point() -> None:
    # The only way to run git through the writer is a typed method; there is no public method
    # that accepts a caller-supplied argv (the sole argv-taking method is the private _run).
    public = [
        name
        for name, _ in inspect.getmembers(GitWriter, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    assert set(public) == {
        "stage_paths",
        "unstage_paths",
        "commit",
        "push",
        "apply_check",
        "apply_patch",
    }


def test_stage_paths_rejects_empty_and_dash_paths(repository: Path) -> None:
    writer = GitWriter(repository)
    with pytest.raises(GitWriteError):
        writer.stage_paths([])
    with pytest.raises(GitWriteError):
        writer.stage_paths(["-x"])
    with pytest.raises(GitWriteError):
        writer.stage_paths([""])


def test_stage_and_commit_round_trip(repository: Path) -> None:
    writer = GitWriter(repository)
    client = GitClient(repository)
    (repository / "newfile.txt").write_text("hi\n", encoding="utf-8")
    writer.stage_paths(["newfile.txt"])
    assert client.staged_names() == ["newfile.txt"]
    writer.commit("add newfile")
    assert client.commit_message(client.head()).rstrip("\n") == "add newfile"


def test_unstage_paths_restores_index_only(repository: Path) -> None:
    writer = GitWriter(repository)
    client = GitClient(repository)
    (repository / "newfile.txt").write_text("hi\n", encoding="utf-8")
    writer.stage_paths(["newfile.txt"])
    assert client.staged_names() == ["newfile.txt"]
    writer.unstage_paths(["newfile.txt"])
    assert client.staged_names() == []
    # The working-tree file is untouched (index-only restore).
    assert (repository / "newfile.txt").read_text(encoding="utf-8") == "hi\n"


def test_commit_message_is_operand_not_scanned(repository: Path) -> None:
    # A message containing git-flag-looking words must commit fine (operand, never scanned).
    writer = GitWriter(repository)
    client = GitClient(repository)
    (repository / "f.txt").write_text("x\n", encoding="utf-8")
    writer.stage_paths(["f.txt"])
    writer.commit("reset --hard and push --force in the message")
    assert "reset --hard" in client.commit_message(client.head())


def test_push_argv_is_exactly_push(repository_with_remote: Path) -> None:
    writer = GitWriter(repository_with_remote)
    client = GitClient(repository_with_remote)
    (repository_with_remote / "f.txt").write_text("x\n", encoding="utf-8")
    writer.stage_paths(["f.txt"])
    writer.commit("c")
    local_head = client.head()
    writer.push()
    remote_head = git(repository_with_remote, "rev-parse", "origin/main")
    assert remote_head == local_head


def test_apply_check_and_apply_patch(repository: Path) -> None:
    writer = GitWriter(repository)
    # Build a patch that adds a new file, then reset and confirm check + apply.
    (repository / "added.txt").write_text("content\n", encoding="utf-8")
    git(repository, "add", "added.txt")
    patch = git(repository, "diff", "--cached", "--binary").encode() + b"\n"
    git(repository, "reset", "--hard")
    assert not (repository / "added.txt").exists()
    assert writer.apply_check(patch) is True
    writer.apply_patch(patch)
    assert (repository / "added.txt").read_text(encoding="utf-8") == "content\n"


def test_apply_check_false_on_bad_patch(repository: Path) -> None:
    writer = GitWriter(repository)
    assert writer.apply_check(b"not a valid patch\n") is False
