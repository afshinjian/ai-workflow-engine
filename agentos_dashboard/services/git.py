"""DR-080..083 (`PRODUCT_SPEC.md`): the Git page — status with staged/modified/untracked
breakdown, a bounded recent-commit log, branches with merged-into-target indication, tags,
upstream verification mirroring `workflowctl check-git`'s `upstream_missing` semantics (DR-081),
PR references named in documentation (DR-082, explicitly labeled unverified — `OD-D7` defers any
live GitHub check), and doc-referenced commit resolution badges (DR-032/TR-07: every SHA named in
`docs/DECISION_LOG.md` or `docs/implementation/orchestration/implementation-state.yaml`, resolved
against real Git).

Never raises for repository content, mirroring `services.consistency.run_consistency_checks`'s
SC-34 discipline: every Git read or document read that fails degrades to an empty result plus a
`ConsistencyFinding`, never an exception a page render would surface as a 500.

`UpstreamCheck.default_branch`/`require_upstream` are documented constants equal to
`self-governance.yaml`'s `project.default_branch`/`project.require_upstream`, for the same reason
`services.consistency.DEFAULT_MAXIMUM_CURRENT_TASKS` is a documented constant rather than a parsed
value: this package has no general `self-governance.yaml` config reader, and `PRODUCT_SPEC.md`
DR-081 itself states the mirrored value literally ("default branch `main`"). A violation is
reported at `ConsistencySeverity.ERROR` — the most severe level this package's finding type
defines, and the one already rendered with the `badge-error` style everywhere else in this
package — which is this module's mapping of `UI_SPEC.md`'s "Blocker" severity term onto the
existing three-level `ConsistencySeverity` scale rather than a new severity enum.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.gitread import (
    BranchRef,
    GitCommit,
    GitReadError,
    GitStatus,
    GitStatusEntry,
    TagRef,
    read_branches,
    read_log,
    read_merged_branch_names,
    read_tags,
    resolve_revision,
)
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.decision_log import parse_decision_log
from agentos_dashboard.services._prose import extract_commit_references
from agentos_dashboard.services.consistency import (
    DECISION_LOG_PATH,
    IMPLEMENTATION_STATE_PATH,
    TASK_QUEUE_PATH,
    ConsistencyFinding,
    ConsistencySeverity,
)

__all__ = [
    "DEFAULT_BRANCH",
    "MAX_COMMITS",
    "REQUIRE_UPSTREAM",
    "BranchInfo",
    "CommitBadge",
    "GitPageData",
    "PrReference",
    "UpstreamCheck",
    "build_git_page",
    "build_upstream_check",
]

# `self-governance.yaml`: project.default_branch / project.require_upstream.
DEFAULT_BRANCH = "main"
REQUIRE_UPSTREAM = True

# `UI_SPEC.md` §1: "Tables: ... pagination over ~200 rows."
MAX_COMMITS = 200

# Bare (non-backtick-quoted) full SHAs named as `implementation-state.yaml` field values, e.g.
# `expected_base_head: fcabc0ba...`, `implementation_commit: 857d2c9b...`. Restricted to keys
# ending in `_head`/`_commit` so an unrelated 40-hex-character-looking token elsewhere in the
# document (there is none today, but the grammar should not assume that) is never mistaken for a
# commit reference.
_SHA_FIELD = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:_head|_commit)):\s*([0-9a-f]{40})\b")
_PR_REF = re.compile(r"\bPR\s*#(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class BranchInfo:
    """DR-080: one branch, plus whether it is already merged into `DEFAULT_BRANCH`."""

    name: str
    upstream: str | None
    sha: str
    is_head: bool
    is_remote: bool
    merged: bool


@dataclass(frozen=True)
class CommitBadge:
    """DR-032/TR-07: one SHA-shaped value named in a governance document, resolved against Git."""

    source: str
    line: int
    field: str
    token: str
    resolved_sha: str | None
    resolvable: bool


@dataclass(frozen=True)
class PrReference:
    """DR-082: a `PR #N` mention in documentation. Never verified against GitHub (`OD-D7`)."""

    number: int
    source: str
    line: int
    context: str


@dataclass(frozen=True)
class GitPageData:
    """PG-07's aggregate."""

    status: GitStatus | None
    staged_entries: tuple[GitStatusEntry, ...]
    modified_entries: tuple[GitStatusEntry, ...]
    untracked_entries: tuple[GitStatusEntry, ...]
    commits: tuple[GitCommit, ...]
    commits_truncated: bool
    branches: tuple[BranchInfo, ...]
    tags: tuple[TagRef, ...]
    commit_badges: tuple[CommitBadge, ...]
    pr_references: tuple[PrReference, ...]
    findings: tuple[ConsistencyFinding, ...]


@dataclass(frozen=True)
class UpstreamCheck:
    """DR-081: upstream verification, mirroring `workflowctl check-git`'s own logic exactly —
    a violation is `require_upstream and upstream is None`, independent of which branch is
    checked out (`src/ai_workflow_engine/git/validators.py::check_git`)."""

    default_branch: str
    require_upstream: bool
    branch: str | None
    on_default_branch: bool
    upstream: str | None
    ahead: int | None
    behind: int | None
    violation: bool
    findings: tuple[ConsistencyFinding, ...]


def _read_or_none(root: RepositoryRoot, relative: str) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError):
        return None


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _status_entries(
    status: GitStatus | None,
) -> tuple[tuple[GitStatusEntry, ...], tuple[GitStatusEntry, ...], tuple[GitStatusEntry, ...]]:
    """DR-080's staged/modified/untracked breakdown of one `git status --porcelain=v2` read.

    Porcelain v2's `XY` codes put the index (staged) state in `X` and the worktree (unstaged)
    state in `Y`; `.` means "no change in that half". An entry can be both staged and modified
    at once (partially staged), so it can appear in both tuples — that is an accurate report of
    the working tree, not a bug.
    """
    if status is None:
        return (), (), ()
    staged = tuple(e for e in status.entries if not e.is_untracked and e.index_status != ".")
    modified = tuple(e for e in status.entries if not e.is_untracked and e.worktree_status != ".")
    untracked = tuple(e for e in status.entries if e.is_untracked)
    return staged, modified, untracked


def _commit_log(root: RepositoryRoot) -> tuple[tuple[GitCommit, ...], ConsistencyFinding | None]:
    try:
        commits = read_log(root.path, limit=MAX_COMMITS)
    except GitReadError as exc:
        return (), ConsistencyFinding(
            rule="git_log_unavailable",
            severity=ConsistencySeverity.WARNING,
            message=f"commit log could not be read: {exc.detail}",
            sources=(),
        )
    return commits, None


def _branch_infos(
    root: RepositoryRoot, branches: tuple[BranchRef, ...]
) -> tuple[tuple[BranchInfo, ...], ConsistencyFinding | None]:
    try:
        merged = read_merged_branch_names(root.path, DEFAULT_BRANCH)
    except GitReadError as exc:
        return (
            tuple(
                BranchInfo(
                    name=b.name,
                    upstream=b.upstream,
                    sha=b.sha,
                    is_head=b.is_head,
                    is_remote=b.is_remote,
                    merged=False,
                )
                for b in branches
            ),
            ConsistencyFinding(
                rule="merged_branch_check_unavailable",
                severity=ConsistencySeverity.WARNING,
                message=(
                    f"merged-into-{DEFAULT_BRANCH!r} status could not be computed: {exc.detail}"
                ),
                sources=(),
            ),
        )
    infos = tuple(
        BranchInfo(
            name=b.name,
            upstream=b.upstream,
            sha=b.sha,
            is_head=b.is_head,
            is_remote=b.is_remote,
            merged=b.name in merged,
        )
        for b in branches
    )
    return infos, None


def _branches(
    root: RepositoryRoot,
) -> tuple[tuple[BranchInfo, ...], ConsistencyFinding | None]:
    try:
        raw = read_branches(root.path)
    except GitReadError as exc:
        return (), ConsistencyFinding(
            rule="git_branches_unavailable",
            severity=ConsistencySeverity.WARNING,
            message=f"branches could not be read: {exc.detail}",
            sources=(),
        )
    return _branch_infos(root, raw)


def _tags(root: RepositoryRoot) -> tuple[tuple[TagRef, ...], ConsistencyFinding | None]:
    try:
        return read_tags(root.path), None
    except GitReadError as exc:
        return (), ConsistencyFinding(
            rule="git_tags_unavailable",
            severity=ConsistencySeverity.WARNING,
            message=f"tags could not be read: {exc.detail}",
            sources=(),
        )


def _decision_log_commit_badges(root: RepositoryRoot) -> tuple[CommitBadge, ...]:
    text = _read_or_none(root, DECISION_LOG_PATH)
    if text is None:
        return ()
    parsed = parse_decision_log(text, DECISION_LOG_PATH)
    entries = parsed.value or ()
    badges: list[CommitBadge] = []
    for entry in entries:
        for resolved in extract_commit_references(root, entry.body):
            badges.append(
                CommitBadge(
                    source=DECISION_LOG_PATH,
                    line=entry.line,
                    field=entry.heading,
                    token=resolved.token,
                    resolved_sha=resolved.resolved_sha,
                    resolvable=resolved.resolvable,
                )
            )
    return tuple(badges)


def _orchestration_commit_badges(root: RepositoryRoot) -> tuple[CommitBadge, ...]:
    """The `expected_base_head`/`implementation_commit`-shaped SHAs named in
    `implementation-state.yaml` (TR-07's own named example). Read as raw text and scanned by
    `_SHA_FIELD` rather than through `parsing.orchestration` — that parser's `OrchestrationStage`
    deliberately extracts only the structural fields `DASH-003.md` named, and adding new fields
    to it is outside this stage's Allowed list; a self-contained regex scan over the document this
    module already reads needs no change to that parser.
    """
    text = _read_or_none(root, IMPLEMENTATION_STATE_PATH)
    if text is None:
        return ()
    badges: list[CommitBadge] = []
    seen: set[tuple[int, str]] = set()
    for match in _SHA_FIELD.finditer(text):
        field, token = match.group(1), match.group(2)
        line = _line_number(text, match.start())
        if (line, token) in seen:
            continue
        seen.add((line, token))
        try:
            sha = resolve_revision(root.path, token)
        except GitReadError:
            badges.append(
                CommitBadge(
                    source=IMPLEMENTATION_STATE_PATH,
                    line=line,
                    field=field,
                    token=token,
                    resolved_sha=None,
                    resolvable=False,
                )
            )
        else:
            badges.append(
                CommitBadge(
                    source=IMPLEMENTATION_STATE_PATH,
                    line=line,
                    field=field,
                    token=token,
                    resolved_sha=sha,
                    resolvable=True,
                )
            )
    return tuple(badges)


def _pr_references(root: RepositoryRoot) -> tuple[PrReference, ...]:
    """DR-082: `PR #N` mentions in documentation, deduplicated by (number, source, line).

    Deliberately unverified: `OD-D7` defers any live GitHub `gh` integration, so this is only a
    text-scan report of what the repository's own prose claims, labeled as such wherever it
    renders — never presented as a confirmed pull-request state.
    """
    refs: list[PrReference] = []
    seen: set[tuple[int, str, int]] = set()
    for source in (DECISION_LOG_PATH, TASK_QUEUE_PATH):
        text = _read_or_none(root, source)
        if text is None:
            continue
        for match in _PR_REF.finditer(text):
            number = int(match.group(1))
            line = _line_number(text, match.start())
            key = (number, source, line)
            if key in seen:
                continue
            seen.add(key)
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            if line_end == -1:
                line_end = len(text)
            context = text[line_start:line_end].strip()
            refs.append(PrReference(number=number, source=source, line=line, context=context))
    return tuple(refs)


def build_git_page(snapshot: RepositorySnapshot) -> GitPageData:
    """Build one `GitPageData` from `snapshot`'s root and cached `git_status`."""
    root = snapshot.root
    findings: list[ConsistencyFinding] = []

    staged, modified, untracked = _status_entries(snapshot.git_status)

    commits, commits_finding = _commit_log(root)
    if commits_finding is not None:
        findings.append(commits_finding)

    branches, branches_finding = _branches(root)
    if branches_finding is not None:
        findings.append(branches_finding)

    tags, tags_finding = _tags(root)
    if tags_finding is not None:
        findings.append(tags_finding)

    commit_badges = _decision_log_commit_badges(root) + _orchestration_commit_badges(root)
    pr_references = _pr_references(root)

    return GitPageData(
        status=snapshot.git_status,
        staged_entries=staged,
        modified_entries=modified,
        untracked_entries=untracked,
        commits=commits,
        commits_truncated=len(commits) == MAX_COMMITS,
        branches=branches,
        tags=tags,
        commit_badges=commit_badges,
        pr_references=pr_references,
        findings=tuple(findings),
    )


def build_upstream_check(snapshot: RepositorySnapshot) -> UpstreamCheck:
    """Build one `UpstreamCheck` from `snapshot`'s cached `git_status` (DR-081)."""
    status = snapshot.git_status
    if status is None:
        return UpstreamCheck(
            default_branch=DEFAULT_BRANCH,
            require_upstream=REQUIRE_UPSTREAM,
            branch=None,
            on_default_branch=False,
            upstream=None,
            ahead=None,
            behind=None,
            violation=True,
            findings=(
                ConsistencyFinding(
                    rule="upstream_check_unavailable",
                    severity=ConsistencySeverity.ERROR,
                    message="git status is unavailable, so upstream verification cannot run",
                    sources=(),
                ),
            ),
        )

    violation = REQUIRE_UPSTREAM and status.upstream is None
    findings: list[ConsistencyFinding] = []
    if violation:
        findings.append(
            ConsistencyFinding(
                rule="upstream_missing",
                severity=ConsistencySeverity.ERROR,
                message="the configured project requires an upstream, and none is configured",
                sources=(),
            )
        )
    if status.behind:
        findings.append(
            ConsistencyFinding(
                rule="branch_behind_upstream",
                severity=ConsistencySeverity.INFO,
                message=f"local branch is behind its upstream by {status.behind} commit(s)",
                sources=(),
            )
        )

    return UpstreamCheck(
        default_branch=DEFAULT_BRANCH,
        require_upstream=REQUIRE_UPSTREAM,
        branch=status.branch,
        on_default_branch=status.branch == DEFAULT_BRANCH,
        upstream=status.upstream,
        ahead=status.ahead,
        behind=status.behind,
        violation=violation,
        findings=tuple(findings),
    )
