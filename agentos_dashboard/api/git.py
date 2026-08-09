"""EP-09/EP-10 (`API_SPEC.md` §2): the Git page's JSON views and upstream verification."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.core.gitread import GitCommit, GitStatusEntry, TagRef
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.services.consistency import ConsistencyFinding
from agentos_dashboard.services.git import (
    BranchInfo,
    CommitBadge,
    PrReference,
    UpstreamCheck,
    build_git_page,
)

__all__ = [
    "git_branches_to_json",
    "git_commits_to_json",
    "git_status_to_json",
    "git_tags_to_json",
    "upstream_check_to_json",
]


def _finding_to_json(finding: ConsistencyFinding) -> dict[str, Any]:
    return {
        "rule": finding.rule,
        "severity": finding.severity.value,
        "message": finding.message,
        "sources": list(finding.sources),
    }


def _entry_to_json(entry: GitStatusEntry) -> dict[str, Any]:
    return {
        "index_status": entry.index_status,
        "worktree_status": entry.worktree_status,
        "path": entry.path,
        "is_untracked": entry.is_untracked,
    }


def _commit_to_json(commit: GitCommit) -> dict[str, Any]:
    return {
        "sha": commit.sha,
        "abbreviated_sha": commit.abbreviated_sha,
        "author_name": commit.author_name,
        "authored_at": commit.authored_at,
        "parents": list(commit.parents),
        "subject": commit.subject,
        "is_merge": commit.is_merge,
    }


def _branch_to_json(branch: BranchInfo) -> dict[str, Any]:
    return {
        "name": branch.name,
        "upstream": branch.upstream,
        "sha": branch.sha,
        "is_head": branch.is_head,
        "is_remote": branch.is_remote,
        "merged": branch.merged,
    }


def _tag_to_json(tag: TagRef) -> dict[str, Any]:
    return {
        "name": tag.name,
        "sha": tag.sha,
        "target_sha": tag.target_sha,
        "created_at": tag.created_at,
    }


def _commit_badge_to_json(badge: CommitBadge) -> dict[str, Any]:
    return {
        "source": badge.source,
        "line": badge.line,
        "field": badge.field,
        "token": badge.token,
        "resolved_sha": badge.resolved_sha,
        "resolvable": badge.resolvable,
    }


def _pr_reference_to_json(ref: PrReference) -> dict[str, Any]:
    return {
        "number": ref.number,
        "source": ref.source,
        "line": ref.line,
        "context": ref.context,
        "verified": False,
    }


def git_status_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-09 `GET /git/status`."""
    data = build_git_page(snapshot)
    status = data.status
    return {
        "head": status.head if status else None,
        "branch": status.branch if status else None,
        "detached": status.detached if status else False,
        "clean": status.clean if status else None,
        "unborn": status.unborn if status else None,
        "staged": [_entry_to_json(e) for e in data.staged_entries],
        "modified": [_entry_to_json(e) for e in data.modified_entries],
        "untracked": [_entry_to_json(e) for e in data.untracked_entries],
        "pr_references": [_pr_reference_to_json(ref) for ref in data.pr_references],
        "commit_badges": [_commit_badge_to_json(badge) for badge in data.commit_badges],
        "findings": [_finding_to_json(f) for f in data.findings],
    }


def git_commits_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-09 `GET /git/commits`."""
    data = build_git_page(snapshot)
    return {
        "commits": [_commit_to_json(c) for c in data.commits],
        "truncated": data.commits_truncated,
        "limit": len(data.commits) if data.commits_truncated else None,
    }


def git_branches_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-09 `GET /git/branches`."""
    data = build_git_page(snapshot)
    return {"branches": [_branch_to_json(b) for b in data.branches]}


def git_tags_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-09 `GET /git/tags`."""
    data = build_git_page(snapshot)
    return {"tags": [_tag_to_json(t) for t in data.tags]}


def upstream_check_to_json(check: UpstreamCheck) -> dict[str, Any]:
    """EP-10 `GET /git/upstream`."""
    return {
        "default_branch": check.default_branch,
        "require_upstream": check.require_upstream,
        "branch": check.branch,
        "on_default_branch": check.on_default_branch,
        "upstream": check.upstream,
        "ahead": check.ahead,
        "behind": check.behind,
        "violation": check.violation,
        "findings": [_finding_to_json(f) for f in check.findings],
    }
