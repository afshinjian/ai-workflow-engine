"""Tests for the Repository Skills (`SKILL_CONTRACTS.md` §2) against temporary real Git
repositories, per `TEST_STRATEGY.md` §3's fixture matrix (init/commit/branch/merge/dirty/
detached-HEAD). No test reaches the network: the "remote" is a local `file://`-style path, the
same technique this repository's own M-4 push tests use.
"""

from __future__ import annotations

import ast
import subprocess
from datetime import UTC
from pathlib import Path

import pytest

from agentos_workflow.skills import FailureKind, MergeConfirmation, RetryClassification, utc_now
from agentos_workflow.skills.repository import (
    checkout_baseline,
    create_stage_branch,
    delete_local_branch,
    delete_remote_branch,
    fast_forward_pull,
    inspect_current_branch,
    inspect_diff,
    inspect_working_tree,
    list_changed_files,
    verify_baseline_ancestry,
    verify_final_repository_state,
    verify_repository_identity,
)

BASELINE = "main"


def git(repo: Path, *args: str) -> str:
    """Direct Git for fixture setup only — never the code under test."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": __import__("os").environ.get("PATH", ""),
            "HOME": str(repo),
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
    )
    return result.stdout.strip()


def write(repo: Path, relative: str, content: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one commit on `main` and an `origin` remote pointing at a bare clone."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", BASELINE, str(origin)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-b", BASELINE)
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.invalid")
    write(work, "README.md", "baseline\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-u", "origin", BASELINE)
    return work


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def confirmation(branch: str) -> MergeConfirmation:
    return MergeConfirmation(branch=branch, merge_commit_sha="0" * 40, verified_at=utc_now())


# ---------------------------------------------------------------------------------------------
# Structural prohibitions (`SECURITY_MODEL.md` §2)
# ---------------------------------------------------------------------------------------------


def test_no_forbidden_argv_tokens() -> None:
    """Force-push and history rewriting must be *unreachable by construction*, not just refused.

    Asserted against the module's own string literals rather than trusted to review: if a future
    change introduces `--force` or `reset --hard` into an argv, this fails immediately.
    """
    source = Path(__file__).resolve().parent.parent / "skills" / "repository.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    forbidden = {
        "--force",
        "-f",
        "--force-with-lease",
        "--force-if-includes",
        "-D",
        "--hard",
        "--mixed",
        "reset",
        "rebase",
        "filter-branch",
        "--amend",
        "update-ref",
        "reflog",
        "gc",
        "prune",
    }
    assert not (literals & forbidden), f"forbidden argv token(s) present: {literals & forbidden}"


def test_baseline_is_never_a_deletable_or_creatable_target(repo: Path) -> None:
    """Every ref-mutating Skill refuses when its target equals the configured baseline."""
    create = create_stage_branch(
        repo, branch_name=BASELINE, base_sha=head_sha(repo), baseline_branch=BASELINE
    )
    assert not create.ok and create.error is not None
    assert create.error.kind is FailureKind.PERMANENT

    local = delete_local_branch(
        repo, branch=BASELINE, baseline_branch=BASELINE, merge_confirmation=confirmation(BASELINE)
    )
    assert not local.ok and local.error is not None
    assert local.error.kind is FailureKind.PERMANENT

    remote = delete_remote_branch(
        repo,
        branch=BASELINE,
        baseline_branch=BASELINE,
        remote="origin",
        merge_confirmation=confirmation(BASELINE),
    )
    assert not remote.ok and remote.error is not None
    assert remote.error.kind is FailureKind.PERMANENT
    # The baseline still exists on the remote.
    assert BASELINE in git(repo, "ls-remote", "--heads", "origin")


@pytest.mark.parametrize(
    "hostile",
    [
        "--force",
        "-f",
        "--upload-pack=touch /tmp/x",
        "a b",
        "a..b",
        "a~1",
        "refs/heads/x:y",
        "trailing.lock",
        ".hidden",
        "double//slash",
        "with\nnewline",
    ],
)
def test_hostile_ref_names_are_rejected_before_argv(repo: Path, hostile: str) -> None:
    """A branch named `--force` must never reach Git as an option."""
    result = create_stage_branch(
        repo, branch_name=hostile, base_sha=head_sha(repo), baseline_branch=BASELINE
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE


def test_hostile_remote_names_are_rejected(repo: Path) -> None:
    result = delete_remote_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        remote="--upload-pack=evil",
        merge_confirmation=confirmation("feature/x"),
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


# ---------------------------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------------------------


def test_verify_repository_identity_matches_equivalent_url_spellings(repo: Path) -> None:
    git(repo, "remote", "set-url", "origin", "https://github.com/owner/project.git")
    for spelling in (
        "https://github.com/owner/project.git",
        "https://github.com/owner/project",
        "git@github.com:owner/project.git",
        "ssh://git@github.com/owner/project",
        "https://TOKEN:x@github.com/owner/project.git",
    ):
        result = verify_repository_identity(repo, expected_identity=spelling, remote_name="origin")
        assert result.ok, f"{spelling} should match: {result.error}"
        assert result.value is not None
        assert result.value.normalized_identity == "github.com/owner/project"


def test_verify_repository_identity_rejects_a_different_repository(repo: Path) -> None:
    git(repo, "remote", "set-url", "origin", "https://github.com/owner/project.git")
    result = verify_repository_identity(
        repo, expected_identity="https://github.com/attacker/project.git", remote_name="origin"
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PERMANENT
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE


def test_verify_repository_identity_never_surfaces_credentials(repo: Path) -> None:
    git(repo, "remote", "set-url", "origin", "https://user:ghp_" + "A" * 36 + "@github.com/o/p.git")
    result = verify_repository_identity(
        repo, expected_identity="https://github.com/o/p", remote_name="origin"
    )
    assert result.ok and result.value is not None
    assert "ghp_" not in result.value.remote_url
    assert "user" not in result.value.remote_url


def test_verify_repository_identity_rejects_a_non_repository(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    result = verify_repository_identity(plain, expected_identity="x/y", remote_name="origin")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_verify_repository_identity_rejects_a_missing_directory(tmp_path: Path) -> None:
    result = verify_repository_identity(
        tmp_path / "absent", expected_identity="x/y", remote_name="origin"
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.NOT_FOUND


# ---------------------------------------------------------------------------------------------
# Working tree and branch inspection
# ---------------------------------------------------------------------------------------------


def test_inspect_working_tree_clean(repo: Path) -> None:
    result = inspect_working_tree(repo)
    assert result.ok and result.value is not None
    assert result.value.clean is True
    assert result.value.entries == ()


def test_inspect_working_tree_reports_every_dirty_category(repo: Path) -> None:
    write(repo, "README.md", "modified\n")
    write(repo, "untracked.txt", "new\n")
    write(repo, "staged.txt", "staged\n")
    git(repo, "add", "staged.txt")
    result = inspect_working_tree(repo)
    assert result.ok and result.value is not None
    assert result.value.clean is False
    assert set(result.value.paths) == {"README.md", "untracked.txt", "staged.txt"}
    assert any(entry.is_untracked for entry in result.value.entries)


def test_inspect_working_tree_handles_renames(repo: Path) -> None:
    """A rename record is followed by its origin path in the NUL stream; it must not be
    mistaken for a second entry."""
    git(repo, "mv", "README.md", "RENAMED.md")
    result = inspect_working_tree(repo)
    assert result.ok and result.value is not None
    assert "RENAMED.md" in result.value.paths
    assert "" not in result.value.paths


def test_inspect_working_tree_handles_paths_with_spaces_and_unicode(repo: Path) -> None:
    write(repo, "a file with spaces.txt", "x\n")
    write(repo, "docs/ünïcode.md", "y\n")
    result = inspect_working_tree(repo)
    assert result.ok and result.value is not None
    assert "a file with spaces.txt" in result.value.paths
    assert "docs/ünïcode.md" in result.value.paths


def test_inspect_current_branch_on_a_branch(repo: Path) -> None:
    result = inspect_current_branch(repo)
    assert result.ok and result.value is not None
    assert result.value.branch == BASELINE
    assert result.value.detached is False
    assert result.value.head_sha == head_sha(repo)


def test_inspect_current_branch_detached_head(repo: Path) -> None:
    sha = head_sha(repo)
    git(repo, "checkout", "--detach", sha)
    result = inspect_current_branch(repo)
    assert result.ok and result.value is not None
    assert result.value.detached is True
    assert result.value.branch is None
    assert result.value.head_sha == sha


def test_inspect_current_branch_on_a_non_repository(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    result = inspect_current_branch(plain)
    assert not result.ok


# ---------------------------------------------------------------------------------------------
# Ancestry, diff, changed files
# ---------------------------------------------------------------------------------------------


def test_verify_baseline_ancestry_passes_for_a_descendant(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "new.txt", "x\n")
    git(repo, "add", "new.txt")
    git(repo, "commit", "-m", "work")
    result = verify_baseline_ancestry(repo, baseline_branch=BASELINE)
    assert result.ok and result.value is True


def test_verify_baseline_ancestry_fails_for_an_unrelated_history(repo: Path) -> None:
    git(repo, "checkout", "--orphan", "orphan")
    write(repo, "other.txt", "x\n")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-m", "unrelated")
    result = verify_baseline_ancestry(repo, baseline_branch=BASELINE)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_list_changed_files_uses_merge_base_semantics(repo: Path) -> None:
    """Two-dot would attribute later baseline commits to the branch; three-dot must not."""
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "feature.txt", "f\n")
    git(repo, "add", "feature.txt")
    git(repo, "commit", "-m", "feature work")
    git(repo, "checkout", BASELINE)
    write(repo, "baseline-moved.txt", "b\n")
    git(repo, "add", "baseline-moved.txt")
    git(repo, "commit", "-m", "unrelated baseline commit")

    result = list_changed_files(repo, base=BASELINE, branch="feature/x")
    assert result.ok and result.value is not None
    assert result.value == ("feature.txt",)
    assert "baseline-moved.txt" not in result.value


def test_list_changed_files_handles_unicode_and_spaces(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "a file.txt", "x\n")
    write(repo, "dir/ünï.md", "y\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "odd names")
    result = list_changed_files(repo, base=BASELINE, branch="feature/x")
    assert result.ok and result.value is not None
    assert set(result.value) == {"a file.txt", "dir/ünï.md"}


def test_inspect_diff_counts_and_paths(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "added.txt", "one\ntwo\nthree\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "add lines")
    result = inspect_diff(repo, base=BASELINE, branch="feature/x")
    assert result.ok and result.value is not None
    assert result.value.files_changed == 1
    assert result.value.insertions == 3
    assert result.value.deletions == 0
    assert result.value.paths == ("added.txt",)


def test_inspect_diff_handles_binary_files(repo: Path) -> None:
    """Binary line counts are undefined (`-`), not zero; parsing must not crash on them."""
    git(repo, "checkout", "-b", "feature/x")
    (repo / "blob.bin").write_bytes(bytes(range(256)) * 8)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "binary")
    result = inspect_diff(repo, base=BASELINE, branch="feature/x")
    assert result.ok and result.value is not None
    assert result.value.paths == ("blob.bin",)


def test_inspect_diff_rejects_hostile_revisions(repo: Path) -> None:
    result = inspect_diff(repo, base="--output=/tmp/pwned", branch="feature/x")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


# ---------------------------------------------------------------------------------------------
# create_stage_branch
# ---------------------------------------------------------------------------------------------


def test_create_stage_branch_creates_and_is_idempotent(repo: Path) -> None:
    sha = head_sha(repo)
    first = create_stage_branch(
        repo, branch_name="feature/x", base_sha=sha, baseline_branch=BASELINE
    )
    assert first.ok and first.value is not None
    assert first.value.head_sha == sha

    second = create_stage_branch(
        repo, branch_name="feature/x", base_sha=sha, baseline_branch=BASELINE
    )
    assert second.ok, "a second identical call must be a successful no-op"


def test_create_stage_branch_refuses_to_move_an_existing_branch(repo: Path) -> None:
    """Moving an existing branch would rewrite the stage's baseline."""
    original = head_sha(repo)
    git(repo, "branch", "feature/x", original)
    write(repo, "second.txt", "x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "second")
    moved = head_sha(repo)

    result = create_stage_branch(
        repo, branch_name="feature/x", base_sha=moved, baseline_branch=BASELINE
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION
    assert git(repo, "rev-parse", "feature/x") == original


def test_create_stage_branch_requires_a_full_sha(repo: Path) -> None:
    short = head_sha(repo)[:8]
    result = create_stage_branch(
        repo, branch_name="feature/x", base_sha=short, baseline_branch=BASELINE
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


# ---------------------------------------------------------------------------------------------
# checkout_baseline
# ---------------------------------------------------------------------------------------------


def test_checkout_baseline_switches_and_is_idempotent(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    result = checkout_baseline(repo, baseline_branch=BASELINE)
    assert result.ok and result.value is not None
    assert result.value.branch == BASELINE
    assert checkout_baseline(repo, baseline_branch=BASELINE).ok


def test_checkout_baseline_refuses_to_discard_uncommitted_work(repo: Path) -> None:
    """`SECURITY_MODEL.md` §5: the precondition is re-verified immediately before execution."""
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "work-in-progress.txt", "precious\n")
    result = checkout_baseline(repo, baseline_branch=BASELINE)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION
    assert (repo / "work-in-progress.txt").exists()
    assert inspect_current_branch(repo).unwrap().branch == "feature/x"


# ---------------------------------------------------------------------------------------------
# fast_forward_pull
# ---------------------------------------------------------------------------------------------


def test_fast_forward_pull_advances_the_baseline(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(tmp_path / "origin.git"), str(other)], check=True, capture_output=True
    )
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.invalid")
    write(other, "remote-change.txt", "x\n")
    git(other, "add", "-A")
    git(other, "commit", "-m", "remote work")
    git(other, "push", "origin", BASELINE)

    result = fast_forward_pull(repo, baseline_branch=BASELINE, remote="origin")
    assert result.ok, f"{result.error}"
    assert (repo / "remote-change.txt").exists()


def test_fast_forward_pull_refuses_divergence(repo: Path, tmp_path: Path) -> None:
    """Divergence is a hard refusal, never a forced update."""
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(tmp_path / "origin.git"), str(other)], check=True, capture_output=True
    )
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.invalid")
    write(other, "remote.txt", "r\n")
    git(other, "add", "-A")
    git(other, "commit", "-m", "remote work")
    git(other, "push", "origin", BASELINE)

    write(repo, "local.txt", "l\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "divergent local work")
    local_sha = head_sha(repo)

    result = fast_forward_pull(repo, baseline_branch=BASELINE, remote="origin")
    assert not result.ok
    # The local commit is untouched — no forced update, no reset.
    assert head_sha(repo) == local_sha


def test_fast_forward_pull_requires_the_baseline_checked_out(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    result = fast_forward_pull(repo, baseline_branch=BASELINE, remote="origin")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_fast_forward_pull_requires_a_clean_tree(repo: Path) -> None:
    write(repo, "dirty.txt", "x\n")
    result = fast_forward_pull(repo, baseline_branch=BASELINE, remote="origin")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_fast_forward_pull_network_failure_is_possible_side_effect(repo: Path) -> None:
    git(repo, "remote", "set-url", "origin", str(repo / "nonexistent-remote.git"))
    result = fast_forward_pull(repo, baseline_branch=BASELINE, remote="origin")
    assert not result.ok and result.error is not None
    assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT


# ---------------------------------------------------------------------------------------------
# Branch deletion
# ---------------------------------------------------------------------------------------------


def test_delete_local_branch_requires_a_matching_merge_confirmation(repo: Path) -> None:
    git(repo, "branch", "feature/x")
    result = delete_local_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        merge_confirmation=confirmation("feature/other"),
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION
    assert "feature/x" in git(repo, "branch", "--list", "feature/x")


def test_delete_local_branch_deletes_a_merged_branch_and_is_idempotent(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "f.txt", "x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "work")
    git(repo, "checkout", BASELINE)
    git(repo, "merge", "--no-ff", "-m", "merge", "feature/x")

    first = delete_local_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        merge_confirmation=confirmation("feature/x"),
    )
    assert first.ok and first.value is True
    second = delete_local_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        merge_confirmation=confirmation("feature/x"),
    )
    assert second.ok and second.value is False, "already absent must be an idempotent no-op"


def test_delete_local_branch_refuses_an_unmerged_branch(repo: Path) -> None:
    """`branch -d` (never `-D`) means Git independently refuses even with a confirmation token."""
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "f.txt", "x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "unmerged work")
    git(repo, "checkout", BASELINE)

    result = delete_local_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        merge_confirmation=confirmation("feature/x"),
    )
    assert not result.ok
    assert "feature/x" in git(repo, "branch", "--list", "feature/x")


def test_delete_local_branch_refuses_the_checked_out_branch(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    result = delete_local_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        merge_confirmation=confirmation("feature/x"),
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_delete_remote_branch_deletes_and_is_idempotent(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    write(repo, "f.txt", "x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "work")
    git(repo, "push", "origin", "feature/x")
    git(repo, "checkout", BASELINE)
    assert "feature/x" in git(repo, "ls-remote", "--heads", "origin")

    first = delete_remote_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        remote="origin",
        merge_confirmation=confirmation("feature/x"),
    )
    assert first.ok and first.value is True
    assert "feature/x" not in git(repo, "ls-remote", "--heads", "origin")

    second = delete_remote_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        remote="origin",
        merge_confirmation=confirmation("feature/x"),
    )
    assert second.ok and second.value is False


def test_delete_remote_branch_requires_a_matching_confirmation(repo: Path) -> None:
    result = delete_remote_branch(
        repo,
        branch="feature/x",
        baseline_branch=BASELINE,
        remote="origin",
        merge_confirmation=confirmation("feature/other"),
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_merge_confirmation_is_required_by_signature() -> None:
    """ "Delete without verifying" must be unexpressible, not merely discouraged."""
    with pytest.raises(TypeError):
        delete_local_branch(Path("."), branch="x", baseline_branch=BASELINE)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        delete_remote_branch(  # type: ignore[call-arg]
            Path("."), branch="x", baseline_branch=BASELINE, remote="origin"
        )


def test_merge_confirmation_carries_timezone_aware_time() -> None:
    token = confirmation("feature/x")
    assert token.verified_at.tzinfo is not None
    assert token.verified_at.astimezone(UTC) == token.verified_at


# ---------------------------------------------------------------------------------------------
# verify_final_repository_state
# ---------------------------------------------------------------------------------------------


def test_verify_final_repository_state_passes_on_clean_baseline(repo: Path) -> None:
    result = verify_final_repository_state(repo, baseline_branch=BASELINE)
    assert result.ok and result.value is not None
    assert result.value.branch == BASELINE


def test_verify_final_repository_state_fails_off_baseline(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/x")
    result = verify_final_repository_state(repo, baseline_branch=BASELINE)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_verify_final_repository_state_fails_when_dirty(repo: Path) -> None:
    write(repo, "dirty.txt", "x\n")
    result = verify_final_repository_state(repo, baseline_branch=BASELINE)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION


def test_verify_final_repository_state_fails_on_detached_head(repo: Path) -> None:
    git(repo, "checkout", "--detach", head_sha(repo))
    result = verify_final_repository_state(repo, baseline_branch=BASELINE)
    assert not result.ok and result.error is not None
    assert "detached" in result.error.detail
