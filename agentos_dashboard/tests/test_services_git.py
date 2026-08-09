"""DR-080..083 — `services.git`: the Git page's aggregate and upstream verification (DASH-006)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.services.git import (
    DEFAULT_BRANCH,
    MAX_COMMITS,
    build_git_page,
    build_upstream_check,
)

from .conftest import git, write


def test_git_page_outside_a_git_repository_degrades_to_empty(root: RepositoryRoot) -> None:
    data = build_git_page(build_snapshot(root))
    assert data.status is None
    assert data.commits == ()
    assert data.branches == ()
    assert data.tags == ()


def test_git_page_reflects_a_real_repository(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    assert data.status is not None
    assert data.status.branch == "main"
    assert len(data.commits) == 1
    assert data.commits[0].subject == "first commit"
    assert data.commits_truncated is False


def test_git_page_status_breakdown_staged_modified_untracked(git_repo: Path) -> None:
    write(git_repo, "README.md", "changed\n")
    write(git_repo, "new.txt", "new\n")
    git(git_repo, "add", "new.txt")
    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    assert [e.path for e in data.staged_entries] == ["new.txt"]
    assert [e.path for e in data.modified_entries] == ["README.md"]
    assert [e.path for e in data.untracked_entries] == []


def test_git_page_commits_are_bounded(git_repo: Path) -> None:
    for i in range(3):
        write(git_repo, f"file{i}.txt", "x\n")
        git(git_repo, "add", f"file{i}.txt")
        git(git_repo, "commit", "--quiet", "-m", f"commit {i}")
    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    assert len(data.commits) == 4  # the fixture's own first commit + 3 more
    assert data.commits_truncated is False


def test_branch_merged_indication(git_repo: Path) -> None:
    git(git_repo, "checkout", "--quiet", "-b", "feature/unmerged")
    write(git_repo, "unmerged.txt", "x\n")
    git(git_repo, "add", "unmerged.txt")
    git(git_repo, "commit", "--quiet", "-m", "never merged")
    git(git_repo, "checkout", "--quiet", "main")

    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    by_name = {b.name: b for b in data.branches}
    assert by_name["main"].merged is True
    assert by_name["feature/unmerged"].merged is False


def test_tags_are_listed(git_repo: Path) -> None:
    git(git_repo, "tag", "v1.0.0")
    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    assert [t.name for t in data.tags] == ["v1.0.0"]


def test_upstream_check_violates_when_no_upstream_is_configured(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    check = build_upstream_check(build_snapshot(root))
    assert check.default_branch == DEFAULT_BRANCH
    assert check.require_upstream is True
    assert check.upstream is None
    assert check.violation is True
    assert check.findings[0].rule == "upstream_missing"
    assert check.findings[0].severity.value == "error"


def test_upstream_check_passes_when_upstream_is_configured(tmp_path: Path, git_repo: Path) -> None:
    remote = tmp_path / "remote.git"
    git(git_repo, "clone", "--quiet", "--bare", str(git_repo), str(remote))
    git(git_repo, "remote", "add", "origin", str(remote))
    git(git_repo, "fetch", "--quiet", "origin")
    git(git_repo, "branch", "--set-upstream-to=origin/main", "main")

    root = RepositoryRoot.from_path(git_repo)
    check = build_upstream_check(build_snapshot(root))
    assert check.upstream == "origin/main"
    assert check.violation is False
    assert check.on_default_branch is True
    assert check.ahead == 0
    assert check.behind == 0


def test_upstream_check_outside_a_git_repository_is_a_violation(root: RepositoryRoot) -> None:
    check = build_upstream_check(build_snapshot(root))
    assert check.violation is True
    assert check.findings[0].rule == "upstream_check_unavailable"


def test_commit_badges_resolve_decision_log_and_orchestration_shas(git_repo: Path) -> None:
    head = git(git_repo, "rev-parse", "HEAD")
    write(
        git_repo,
        "docs/DECISION_LOG.md",
        f"## 2026-01-01 — a decision\n\nSee commit `{head}` for details.\n",
    )
    write(
        git_repo,
        "docs/implementation/orchestration/implementation-state.yaml",
        f"feature_id: FIX\nstages:\n  ORCH-000: {{title: t, status: s, prerequisites: [], "
        f"implementation_commit: {head}, expected_base_head: {'a' * 40}, blockers: [], "
        f"evidence: []}}\n",
    )
    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    by_field = {(b.source, b.field): b for b in data.commit_badges}
    assert by_field[("docs/DECISION_LOG.md", "a decision")].resolvable is True
    assert (
        by_field[
            (
                "docs/implementation/orchestration/implementation-state.yaml",
                "implementation_commit",
            )
        ].resolvable
        is True
    )
    assert (
        by_field[
            ("docs/implementation/orchestration/implementation-state.yaml", "expected_base_head")
        ].resolvable
        is False
    )


def test_pr_references_are_extracted_and_labeled_unverified(git_repo: Path) -> None:
    write(
        git_repo,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — thing\n\nStatus: Done\n\nMerged via PR #42.\n",
    )
    root = RepositoryRoot.from_path(git_repo)
    data = build_git_page(build_snapshot(root))
    assert len(data.pr_references) == 1
    assert data.pr_references[0].number == 42
    assert data.pr_references[0].source == "docs/TASK_QUEUE.md"


def test_max_commits_constant_matches_ui_spec_pagination_bound() -> None:
    assert MAX_COMMITS == 200
