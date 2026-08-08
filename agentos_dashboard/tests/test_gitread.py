"""TC-04 — the Git read adapter against temporary real Git repositories.

`TEST_STRATEGY.md` §3 allows mocking only the subprocess *timeout*; every other case runs real
Git against a real repository, covering the documented fixture matrix: init, commit, tag,
branch, merge, dirty tree, detached HEAD, and missing upstream.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentos_dashboard.core import GIT_TIMEOUT_SECONDS
from agentos_dashboard.core.gitread import (
    MAX_LOG_LIMIT,
    READ_ONLY_SUBCOMMANDS,
    GitFailure,
    GitReadError,
    read_branches,
    read_diff_check,
    read_diff_stat,
    read_head,
    read_log,
    read_status,
    read_tags,
    resolve_revision,
)

from .conftest import git, write

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# Git subcommands that write. None of these may appear as a string literal anywhere in the
# package's non-test source.
MUTATING_SUBCOMMANDS = frozenset(
    {
        "add",
        "am",
        "apply",
        "checkout",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "fetch",
        "filter-branch",
        "gc",
        "init",
        "merge",
        "mv",
        "prune",
        "pull",
        "push",
        "rebase",
        "reset",
        "restore",
        "revert",
        "rm",
        "stash",
        "submodule",
        "switch",
        "update-ref",
        "worktree",
    }
)

# `branch` and `tag` are on the read-only allowlist, so their mutating forms are flag-driven.
# These flags must not appear either, which closes `branch -d` / `tag -a` without banning the
# two subcommands the adapter legitimately reads with.
MUTATING_FLAGS = frozenset(
    {"-d", "-D", "-f", "--delete", "--force", "--force-with-lease", "--hard", "--amend"}
)


def test_read_head_returns_the_commit_sha(git_repo: Path) -> None:
    head = read_head(git_repo)
    assert head == git(git_repo, "rev-parse", "HEAD")


def test_read_head_is_none_on_an_unborn_branch(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    assert read_head(repo) is None


def test_read_status_of_a_clean_repository(git_repo: Path) -> None:
    status = read_status(git_repo)
    assert status.branch == "main"
    assert status.detached is False
    assert status.upstream is None
    assert status.ahead is None and status.behind is None
    assert status.clean is True
    assert status.unborn is False
    assert status.head == read_head(git_repo)


def test_read_status_of_a_dirty_repository(git_repo: Path) -> None:
    write(git_repo, "README.md", "changed\n")
    write(git_repo, "new file.md", "untracked with a space in its name\n")
    write(git_repo, "staged.md", "staged\n")
    git(git_repo, "add", "staged.md")

    status = read_status(git_repo)
    assert status.clean is False
    paths = {entry.path for entry in status.entries}
    assert paths == {"README.md", "staged.md", "new file.md"}

    by_path = {entry.path: entry for entry in status.entries}
    assert by_path["README.md"].worktree_status == "M"
    assert by_path["staged.md"].index_status == "A"
    assert by_path["new file.md"].is_untracked is True


def test_read_status_collapses_a_wholly_untracked_directory(git_repo: Path) -> None:
    """Git's default `--untracked-files=normal` reports the directory, not its contents.

    The adapter reports what Git reports rather than expanding it, so the dashboard shows the
    operator exactly what `git status` would.
    """
    write(git_repo, "untracked_dir/one.md", "one\n")
    write(git_repo, "untracked_dir/two.md", "two\n")
    status = read_status(git_repo)
    assert {entry.path for entry in status.entries} == {"untracked_dir/"}


def test_read_status_reports_a_rename_by_its_current_path(git_repo: Path) -> None:
    git(git_repo, "mv", "README.md", "READ.md")
    status = read_status(git_repo)
    assert {entry.path for entry in status.entries} == {"READ.md"}
    assert status.entries[0].index_status == "R"


def test_read_status_of_an_unborn_repository(tmp_path: Path) -> None:
    repo = tmp_path / "unborn"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    status = read_status(repo)
    assert status.unborn is True
    assert status.head is None
    assert status.branch == "main"


def test_read_status_of_a_detached_head(git_repo: Path) -> None:
    write(git_repo, "second.md", "second\n")
    git(git_repo, "add", "second.md")
    git(git_repo, "commit", "--quiet", "-m", "second commit")
    git(git_repo, "checkout", "--quiet", "HEAD~1")

    status = read_status(git_repo)
    assert status.detached is True
    assert status.branch is None


def test_read_status_reports_upstream_and_divergence(tmp_path: Path, git_repo: Path) -> None:
    remote = tmp_path / "remote.git"
    git(git_repo, "clone", "--quiet", "--bare", str(git_repo), str(remote))
    git(git_repo, "remote", "add", "origin", str(remote))
    git(git_repo, "fetch", "--quiet", "origin")
    git(git_repo, "branch", "--set-upstream-to=origin/main", "main")

    status = read_status(git_repo)
    assert status.upstream == "origin/main"
    assert (status.ahead, status.behind) == (0, 0)

    write(git_repo, "ahead.md", "ahead\n")
    git(git_repo, "add", "ahead.md")
    git(git_repo, "commit", "--quiet", "-m", "ahead commit")
    assert read_status(git_repo).ahead == 1


def test_read_log_is_newest_first_and_bounded(git_repo: Path) -> None:
    for index in range(3):
        write(git_repo, f"file{index}.md", f"{index}\n")
        git(git_repo, "add", f"file{index}.md")
        git(git_repo, "commit", "--quiet", "-m", f"commit {index}")

    commits = read_log(git_repo, limit=2)
    assert [commit.subject for commit in commits] == ["commit 2", "commit 1"]
    assert commits[0].sha == read_head(git_repo)
    assert commits[0].author_name == "Fixture"
    assert commits[0].authored_at.startswith("2026-01-01T")
    assert commits[0].is_merge is False
    assert commits[0].parents == (commits[1].sha,)


def test_read_log_preserves_a_subject_containing_separators(git_repo: Path) -> None:
    write(git_repo, "odd.md", "odd\n")
    git(git_repo, "add", "odd.md")
    git(git_repo, "commit", "--quiet", "-m", "feat: a subject with | pipes and 'quotes'")
    assert read_log(git_repo, limit=1)[0].subject == "feat: a subject with | pipes and 'quotes'"


def test_read_log_marks_a_merge_commit(git_repo: Path) -> None:
    git(git_repo, "checkout", "--quiet", "-b", "topic")
    write(git_repo, "topic.md", "topic\n")
    git(git_repo, "add", "topic.md")
    git(git_repo, "commit", "--quiet", "-m", "topic commit")
    git(git_repo, "checkout", "--quiet", "main")
    git(git_repo, "merge", "--quiet", "--no-ff", "topic", "-m", "merge topic")

    merge = read_log(git_repo, limit=1)[0]
    assert merge.is_merge is True
    assert len(merge.parents) == 2


@pytest.mark.parametrize("limit", [0, -1, MAX_LOG_LIMIT + 1])
def test_read_log_refuses_an_out_of_range_limit(git_repo: Path, limit: int) -> None:
    with pytest.raises(GitReadError) as caught:
        read_log(git_repo, limit=limit)
    assert caught.value.failure is GitFailure.UNSAFE_ARGUMENT


def test_read_log_on_an_unborn_repository_is_a_typed_failure(tmp_path: Path) -> None:
    repo = tmp_path / "unborn"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    with pytest.raises(GitReadError) as caught:
        read_log(repo, limit=5)
    assert caught.value.failure is GitFailure.COMMAND_FAILED


def test_read_branches_lists_local_and_remote_branches(tmp_path: Path, git_repo: Path) -> None:
    remote = tmp_path / "remote.git"
    git(git_repo, "clone", "--quiet", "--bare", str(git_repo), str(remote))
    git(git_repo, "remote", "add", "origin", str(remote))
    git(git_repo, "fetch", "--quiet", "origin")
    git(git_repo, "branch", "--set-upstream-to=origin/main", "main")
    git(git_repo, "branch", "feature/dash")

    branches = {branch.name: branch for branch in read_branches(git_repo)}
    assert branches["main"].is_head is True
    assert branches["main"].upstream == "origin/main"
    assert branches["main"].is_remote is False
    assert branches["feature/dash"].is_head is False
    assert branches["feature/dash"].upstream is None
    assert branches["origin/main"].is_remote is True


def test_read_tags_reports_annotated_and_lightweight_tags(git_repo: Path) -> None:
    git(git_repo, "tag", "-a", "v1.0.0", "-m", "release one")
    git(git_repo, "tag", "light")

    tags = {tag.name: tag for tag in read_tags(git_repo)}
    head = read_head(git_repo)
    assert tags["v1.0.0"].target_sha == head
    assert tags["v1.0.0"].sha != head  # the annotated tag object, not the commit
    assert tags["light"].sha == head
    assert tags["light"].target_sha is None


def test_read_tags_of_a_repository_without_tags(git_repo: Path) -> None:
    assert read_tags(git_repo) == ()


def test_resolve_revision_returns_a_full_sha(git_repo: Path) -> None:
    head = read_head(git_repo)
    assert head is not None
    assert resolve_revision(git_repo, "HEAD") == head
    assert resolve_revision(git_repo, "main") == head
    assert resolve_revision(git_repo, head[:8]) == head


def test_resolve_revision_refuses_an_unknown_revision(git_repo: Path) -> None:
    with pytest.raises(GitReadError) as caught:
        resolve_revision(git_repo, "no-such-ref")
    assert caught.value.failure is GitFailure.COMMAND_FAILED


@pytest.mark.parametrize(
    "revision",
    ["--upload-pack=touch /tmp/pwned", "-x", "HEAD; rm -rf /", "HEAD main", "", "a" * 500],
)
def test_resolve_revision_refuses_unsafe_input(git_repo: Path, revision: str) -> None:
    with pytest.raises(GitReadError) as caught:
        resolve_revision(git_repo, revision)
    assert caught.value.failure is GitFailure.UNSAFE_ARGUMENT


def test_resolve_revision_refuses_a_range(git_repo: Path) -> None:
    with pytest.raises(GitReadError) as caught:
        resolve_revision(git_repo, "HEAD~1..HEAD")
    assert caught.value.failure is GitFailure.UNSAFE_ARGUMENT


def test_read_diff_stat_between_two_revisions(git_repo: Path) -> None:
    base = read_head(git_repo)
    assert base is not None
    write(git_repo, "added.md", "added\n")
    git(git_repo, "add", "added.md")
    git(git_repo, "commit", "--quiet", "-m", "add a file")

    stat = read_diff_stat(git_repo, base, "HEAD")
    assert stat.base == base
    assert stat.head == read_head(git_repo)
    assert any("added.md" in line for line in stat.lines)


def test_read_diff_stat_of_an_identical_range_is_empty(git_repo: Path) -> None:
    assert read_diff_stat(git_repo, "HEAD", "HEAD").lines == ()


def test_read_diff_check_is_clean_on_a_clean_tree(git_repo: Path) -> None:
    result = read_diff_check(git_repo)
    assert result.clean is True
    assert result.problems == ()


def test_read_diff_check_reports_a_conflict_marker(git_repo: Path) -> None:
    write(git_repo, "README.md", "first\n<<<<<<< HEAD\nx\n")
    result = read_diff_check(git_repo)
    assert result.clean is False
    assert any("conflict marker" in problem for problem in result.problems)


def test_a_directory_that_is_not_a_repository_is_a_typed_failure(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitReadError) as caught:
        read_status(plain)
    assert caught.value.failure is GitFailure.NOT_A_REPOSITORY


def test_a_timeout_is_a_typed_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="git", timeout=GIT_TIMEOUT_SECONDS)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitReadError) as caught:
        read_status(git_repo)
    assert caught.value.failure is GitFailure.TIMEOUT


def test_a_missing_git_binary_is_a_typed_failure(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> Any:
        raise OSError("No such file or directory: 'git'")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitReadError) as caught:
        read_head(git_repo)
    assert caught.value.failure is GitFailure.GIT_UNAVAILABLE


def test_malformed_git_output_is_a_typed_failure(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @dataclass
    class FakeCompleted:
        returncode: int = 0
        stdout: str = "# branch.ab not-a-count\n"
        stderr: str = ""

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitReadError) as caught:
        read_status(git_repo)
    assert caught.value.failure is GitFailure.MALFORMED_OUTPUT


def _recording_run(seen: dict[str, Any]) -> Callable[..., Any]:
    """Wrap the real `subprocess.run`, capturing the keyword arguments it was called with."""
    real_run = subprocess.run

    def recording_run(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real_run(*args, **kwargs)

    return recording_run


def test_the_timeout_is_the_documented_five_seconds(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-25: every Git subprocess carries the 5 s bound, not merely the documented intent."""
    seen: dict[str, Any] = {}
    monkeypatch.setattr(subprocess, "run", _recording_run(seen))
    read_head(git_repo)
    assert seen["timeout"] == GIT_TIMEOUT_SECONDS == 5


def test_the_environment_is_locale_pinned_and_minimal(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setenv("GIT_DIR", "/somewhere/else/.git")
    monkeypatch.setattr(subprocess, "run", _recording_run(seen))
    read_head(git_repo)

    environment = seen["env"]
    assert isinstance(environment, dict)
    assert environment["LC_ALL"] == "C"
    assert environment["LANG"] == "C"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    # Inherited by allowlist only: an ambient GIT_DIR must not reach the subprocess.
    assert "GIT_DIR" not in environment


def test_run_refuses_a_subcommand_outside_the_allowlist(git_repo: Path) -> None:
    from agentos_dashboard.core.gitread import _run

    with pytest.raises(GitReadError) as caught:
        _run(git_repo, ("commit", "-m", "nope"), allowed_exit_codes=(0,))
    assert caught.value.failure is GitFailure.UNSAFE_ARGUMENT


def test_read_only_subcommand_allowlist_is_exactly_the_contracted_set() -> None:
    assert READ_ONLY_SUBCOMMANDS == frozenset(
        {"status", "log", "branch", "tag", "rev-parse", "diff"}
    )


def test_no_mutating_git_verb_in_package_source() -> None:
    """SC-29 — proven by scanning this package's own source, not by review.

    Every string literal in every module that could plausibly build a `subprocess` argv is
    checked against the mutating-verb list, so a future edit that adds `("commit", ...)` to an
    argv tuple fails here even if it never runs in a test.

    Scanned modules are narrowed to those that import `subprocess` at all (`core/gitread.py`
    today — the package's *only* subprocess call site, `ARCHITECTURE.md` §3: "The two adapters
    ... are the only code permitted to touch the repository"). A module that never imports
    `subprocess` cannot construct a Git argv, so it cannot pose the SC-29 risk this test exists
    to catch; without this narrowing, a display-only module that legitimately names the engine's
    own workflow vocabulary — `push` is the seventh of the engine's seven fixed workflow stages
    (`ai_workflow_engine.prompt.models.WORKFLOW_STAGES`), and `merge` labels one kind of queue-
    prose lifecycle event (`agentos_dashboard.services.tasks`) — would be flagged as a false
    positive on an English word that is never, in that module, an argument to anything. Any
    module that starts importing `subprocess` in the future is automatically back under full
    literal scanning with no test change required.
    """
    scanned: list[Path] = []
    offenders: list[str] = []
    for module in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "tests" in module.relative_to(PACKAGE_ROOT).parts:
            continue
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module))
        imports_subprocess = any(
            (
                isinstance(node, ast.Import)
                and any(alias.name == "subprocess" for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module == "subprocess")
            for node in ast.walk(tree)
        )
        if not imports_subprocess:
            continue
        scanned.append(module)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            literal = node.value.strip()
            if literal in MUTATING_SUBCOMMANDS or literal in MUTATING_FLAGS:
                offenders.append(f"{module.relative_to(PACKAGE_ROOT)}:{node.lineno}:{literal!r}")

    # A scan that silently found no files would pass vacuously.
    assert scanned, f"expected at least the Git adapter to be scanned, saw {scanned}"
    assert not offenders, f"mutating Git verbs must not appear in dashboard source: {offenders}"
