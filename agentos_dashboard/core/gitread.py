"""Read-only Git adapter (`ARCHITECTURE.md` §3; SC-25, SC-28, SC-29).

Named functions over `subprocess.run` with fixed argv. There is no general "run a git command"
entry point, no caller-supplied verb, and no mutating verb anywhere in this package: the
subcommand of each function is a literal in that function's own argv tuple, so the operations
`SECURITY_MODEL.md` §5 prohibits (commit, push, merge, tag creation, branch deletion, history
rewrite) are not merely refused at runtime — they are unreachable by construction.
`test_gitread.py::test_no_mutating_git_verb_in_package_source` asserts that property against
this package's source rather than trusting the review that wrote it (SC-29).

Where a caller does supply a value — a revision — it is validated against a strict pattern and
passed after `--end-of-options`, and every revision is resolved to a 40-character SHA before it
is interpolated into a range, so no caller string ever reaches Git as an option or a pathspec.

This mirrors the discipline of the engine's own read-only `GitClient`
(`src/ai_workflow_engine/git/client.py`) without importing or modifying it: the dashboard must
not couple itself to engine internals, and the engine's client is not a dependency the
dashboard is permitted to add to.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agentos_dashboard.core import GIT_TIMEOUT_SECONDS, DashboardError

__all__ = [
    "MAX_LOG_LIMIT",
    "READ_ONLY_SUBCOMMANDS",
    "BranchRef",
    "DiffCheck",
    "DiffStat",
    "GitCommit",
    "GitFailure",
    "GitReadError",
    "GitStatus",
    "GitStatusEntry",
    "TagRef",
    "read_branches",
    "read_diff_check",
    "read_diff_stat",
    "read_head",
    "read_log",
    "read_merged_branch_names",
    "read_status",
    "read_tags",
    "resolve_revision",
]

# The complete set of Git subcommands this package may run. Every one of them is read-only in
# the forms used below; `_run` refuses anything else, which makes an accidentally-added
# mutating call a failing test rather than a repository change.
READ_ONLY_SUBCOMMANDS: frozenset[str] = frozenset(
    {"status", "log", "branch", "tag", "rev-parse", "diff"}
)

MAX_LOG_LIMIT = 1000

_UNIT = "\x1f"
_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
# Conservative revision grammar: enough for `HEAD`, `main`, `origin/main`, `v1.0.0`, `HEAD~3`,
# `abc123`, and refuses anything that could be read as an option or a pathspec.
_REVISION_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/@^~{}-]{0,199}\Z")


class GitFailure(StrEnum):
    """Why a Git read failed."""

    UNSAFE_ARGUMENT = "unsafe_argument"
    GIT_UNAVAILABLE = "git_unavailable"
    NOT_A_REPOSITORY = "not_a_repository"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    MALFORMED_OUTPUT = "malformed_output"


class GitReadError(DashboardError):
    """A typed Git failure. Nothing from `subprocess` crosses this module's boundary."""

    def __init__(self, failure: GitFailure, detail: str) -> None:
        super().__init__(f"{failure.value}: {detail}")
        self.failure = failure
        self.detail = detail


@dataclass(frozen=True)
class GitStatusEntry:
    """One changed path from `status --porcelain=v2`."""

    index_status: str
    worktree_status: str
    path: str

    @property
    def is_untracked(self) -> bool:
        return self.index_status == "?" and self.worktree_status == "?"


@dataclass(frozen=True)
class GitStatus:
    """EN-04: branch, upstream, divergence, and working-tree state."""

    head: str | None
    branch: str | None
    detached: bool
    upstream: str | None
    ahead: int | None
    behind: int | None
    entries: tuple[GitStatusEntry, ...]

    @property
    def clean(self) -> bool:
        return not self.entries

    @property
    def unborn(self) -> bool:
        """True on a fresh repository whose branch has no commit yet."""
        return self.head is None


@dataclass(frozen=True)
class GitCommit:
    """EN-20: one commit from a bounded `log`."""

    sha: str
    abbreviated_sha: str
    author_name: str
    authored_at: str
    parents: tuple[str, ...]
    subject: str

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1


@dataclass(frozen=True)
class BranchRef:
    """EN-19: one local or remote-tracking branch."""

    name: str
    upstream: str | None
    sha: str
    is_head: bool
    is_remote: bool


@dataclass(frozen=True)
class TagRef:
    name: str
    sha: str
    target_sha: str | None
    created_at: str


@dataclass(frozen=True)
class DiffStat:
    """The verbatim `diff --stat` body plus the range it describes."""

    base: str
    head: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class DiffCheck:
    """`git diff --check`: whitespace errors and conflict markers in the working tree."""

    clean: bool
    problems: tuple[str, ...]


@dataclass(frozen=True)
class _Completed:
    exit_code: int
    stdout: str
    stderr: str


def _environment() -> dict[str, str]:
    """A minimal, locale-pinned environment (`LC_ALL=C`, per the stage contract's named risk).

    Built from an explicit allowlist rather than inherited wholesale: `PATH` is needed to find
    Git at all, and everything else that could change Git's output (config paths, pagers,
    credential helpers, locale) is either pinned or absent.
    """
    return {
        "PATH": os.environ.get("PATH", ""),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _run(
    root: Path, argv_tail: tuple[str, ...], *, allowed_exit_codes: tuple[int, ...]
) -> _Completed:
    """Run one fixed-argv read-only Git command inside `root`.

    `argv_tail[0]` must be on `READ_ONLY_SUBCOMMANDS`; this is a second, independent check on
    top of the fact that every call site passes a literal, so a future edit cannot introduce a
    mutating verb by changing one tuple.
    """
    if not argv_tail or argv_tail[0] not in READ_ONLY_SUBCOMMANDS:
        raise GitReadError(
            GitFailure.UNSAFE_ARGUMENT,
            f"subcommand is not on the read-only allowlist: {argv_tail!r}",
        )
    argv = (
        "git",
        "--no-optional-locks",
        # Non-ASCII paths are returned verbatim instead of C-quoted, so a path never has to be
        # unescaped by a caller. A fixed global option, never caller-supplied.
        "-c",
        "core.quotePath=false",
        "-C",
        str(root),
        *argv_tail,
    )
    try:
        process = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            env=_environment(),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitReadError(
            GitFailure.TIMEOUT, f"git {argv_tail[0]} exceeded {GIT_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise GitReadError(GitFailure.GIT_UNAVAILABLE, f"unable to execute git: {exc}") from exc

    if process.returncode not in allowed_exit_codes:
        stderr = process.stderr.strip()
        failure = (
            GitFailure.NOT_A_REPOSITORY
            if "not a git repository" in stderr.lower()
            else GitFailure.COMMAND_FAILED
        )
        raise GitReadError(failure, f"git {argv_tail[0]} exited {process.returncode}: {stderr}")
    return _Completed(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr)


def _validated_revision(revision: str) -> str:
    if not _REVISION_RE.match(revision):
        raise GitReadError(GitFailure.UNSAFE_ARGUMENT, f"unsupported revision: {revision!r}")
    if ".." in revision:
        raise GitReadError(GitFailure.UNSAFE_ARGUMENT, f"ranges are not revisions: {revision!r}")
    return revision


def _malformed(detail: str) -> GitReadError:
    return GitReadError(GitFailure.MALFORMED_OUTPUT, detail)


def read_status(root: Path) -> GitStatus:
    """`git status --porcelain=v2 --branch` — branch, upstream, divergence, changed paths.

    Untracked *directories* are reported as one entry (Git's default
    `--untracked-files=normal`), exactly as plain `git status` shows them to an operator; the
    adapter reports what Git reported rather than expanding it.
    """
    completed = _run(root, ("status", "--porcelain=v2", "--branch"), allowed_exit_codes=(0,))

    head: str | None = None
    branch: str | None = None
    detached = False
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    entries: list[GitStatusEntry] = []

    for line in completed.stdout.splitlines():
        if not line:
            continue
        if line.startswith("# branch.oid "):
            value = line[len("# branch.oid ") :]
            head = None if value == "(initial)" else value
        elif line.startswith("# branch.head "):
            value = line[len("# branch.head ") :]
            if value == "(detached)":
                detached = True
            else:
                branch = value
        elif line.startswith("# branch.upstream "):
            upstream = line[len("# branch.upstream ") :]
        elif line.startswith("# branch.ab "):
            ahead, behind = _parse_ahead_behind(line)
        elif line.startswith("#"):
            continue
        else:
            entries.append(_parse_status_entry(line))

    return GitStatus(
        head=head,
        branch=branch,
        detached=detached,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        entries=tuple(entries),
    )


def _parse_ahead_behind(line: str) -> tuple[int, int]:
    fields = line[len("# branch.ab ") :].split()
    if len(fields) != 2 or not fields[0].startswith("+") or not fields[1].startswith("-"):
        raise _malformed(f"unparsable branch.ab header: {line!r}")
    try:
        return int(fields[0][1:]), int(fields[1][1:])
    except ValueError as exc:
        raise _malformed(f"unparsable branch.ab header: {line!r}") from exc


def _parse_status_entry(line: str) -> GitStatusEntry:
    """Parse one porcelain-v2 entry line.

    The four record kinds put the path in different columns, and a rename record (`2`) appends
    the original path after a tab. `maxsplit` is fixed per kind so a path containing spaces
    survives intact.
    """
    kind = line[0]
    if kind in {"?", "!"}:
        fields = line.split(" ", 1)
        if len(fields) != 2:
            raise _malformed(f"unparsable status entry: {line!r}")
        status = "?" if kind == "?" else "!"
        return GitStatusEntry(index_status=status, worktree_status=status, path=fields[1])

    field_counts = {"1": 8, "2": 9, "u": 10}
    if kind not in field_counts:
        raise _malformed(f"unrecognised status record: {line!r}")
    fields = line.split(" ", field_counts[kind])
    if len(fields) != field_counts[kind] + 1:
        raise _malformed(f"unparsable status entry: {line!r}")
    xy = fields[1]
    if len(xy) != 2:
        raise _malformed(f"unparsable status flags: {line!r}")
    path = fields[-1].split("\t", 1)[0] if kind == "2" else fields[-1]
    return GitStatusEntry(index_status=xy[0], worktree_status=xy[1], path=path)


def read_head(root: Path) -> str | None:
    """The HEAD commit SHA, or `None` on an unborn branch (a repository with no commit)."""
    completed = _run(
        root, ("rev-parse", "--verify", "--quiet", "HEAD^{commit}"), allowed_exit_codes=(0, 1)
    )
    if completed.exit_code == 1:
        return None
    sha = completed.stdout.strip()
    if not _SHA_RE.match(sha):
        raise _malformed(f"rev-parse returned an unexpected value: {sha!r}")
    return sha


def resolve_revision(root: Path, revision: str) -> str:
    """Resolve a caller-supplied revision to its 40-character commit SHA."""
    validated = _validated_revision(revision)
    completed = _run(
        root,
        ("rev-parse", "--verify", "--quiet", "--end-of-options", f"{validated}^{{commit}}"),
        allowed_exit_codes=(0, 1),
    )
    sha = completed.stdout.strip()
    if completed.exit_code == 1 or not sha:
        raise GitReadError(GitFailure.COMMAND_FAILED, f"unknown revision: {revision!r}")
    if not _SHA_RE.match(sha):
        raise _malformed(f"rev-parse returned an unexpected value: {sha!r}")
    return sha


def read_log(root: Path, *, limit: int = 50) -> tuple[GitCommit, ...]:
    """A bounded `git log` with a fixed record format, newest first.

    The bound is required, not advisory: an unbounded log on a large repository is both a
    latency problem and a response-size problem (SC-25's "bounded response sizes").

    An unborn branch (a repository with no commit) has no log at all, and Git says so with a
    non-zero exit; that surfaces here as a typed `COMMAND_FAILED` rather than as an empty
    result, so a caller cannot mistake "no history yet" for "no commits matched".
    """
    if limit < 1 or limit > MAX_LOG_LIMIT:
        raise GitReadError(
            GitFailure.UNSAFE_ARGUMENT, f"log limit must be within 1..{MAX_LOG_LIMIT}: {limit}"
        )
    fmt = _UNIT.join(("%H", "%h", "%an", "%aI", "%P", "%s"))
    completed = _run(
        root,
        ("log", "-z", f"--max-count={limit}", f"--format={fmt}"),
        allowed_exit_codes=(0,),
    )
    commits: list[GitCommit] = []
    for record in completed.stdout.split("\0"):
        if not record.strip():
            continue
        fields = record.split(_UNIT)
        if len(fields) != 6:
            raise _malformed(f"unparsable log record: {record!r}")
        sha, abbreviated, author, authored_at, parents, subject = fields
        if not _SHA_RE.match(sha):
            raise _malformed(f"unparsable log commit id: {sha!r}")
        commits.append(
            GitCommit(
                sha=sha,
                abbreviated_sha=abbreviated,
                author_name=author,
                authored_at=authored_at,
                parents=tuple(parents.split()),
                subject=subject,
            )
        )
    return tuple(commits)


def read_branches(root: Path) -> tuple[BranchRef, ...]:
    """`git branch -a --format` — local and remote-tracking branches with their upstreams."""
    fmt = "%(refname:short)%1f%(upstream:short)%1f%(objectname)%1f%(HEAD)%1f%(refname)"
    completed = _run(root, ("branch", "-a", f"--format={fmt}"), allowed_exit_codes=(0,))
    branches: list[BranchRef] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split(_UNIT)
        if len(fields) != 5:
            raise _malformed(f"unparsable branch record: {line!r}")
        name, upstream, sha, head_marker, refname = fields
        branches.append(
            BranchRef(
                name=name,
                upstream=upstream or None,
                sha=sha,
                is_head=head_marker.strip() == "*",
                is_remote=refname.startswith("refs/remotes/"),
            )
        )
    return tuple(branches)


def read_tags(root: Path) -> tuple[TagRef, ...]:
    """`git tag --format` — tag names with both the tag object and its target."""
    fmt = "%(refname:short)%1f%(objectname)%1f%(*objectname)%1f%(creatordate:iso-strict)"
    completed = _run(root, ("tag", f"--format={fmt}"), allowed_exit_codes=(0,))
    tags: list[TagRef] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split(_UNIT)
        if len(fields) != 4:
            raise _malformed(f"unparsable tag record: {line!r}")
        name, sha, target, created_at = fields
        tags.append(TagRef(name=name, sha=sha, target_sha=target or None, created_at=created_at))
    return tuple(tags)


def read_merged_branch_names(root: Path, target: str) -> frozenset[str]:
    """`git branch -a --merged <target>` — short names of every branch already an ancestor of
    `target` (`DASH-006.md` DR-080's "merged-into-target indication").

    Reuses the already-allowlisted `branch` subcommand (no new verb added to
    `READ_ONLY_SUBCOMMANDS`): `--merged` is a read-only filter on `git branch`'s own listing, not
    a different operation. `target` is validated exactly as `resolve_revision` validates a
    caller-supplied revision (`_validated_revision`, which requires a leading alphanumeric
    character), so it can never be interpreted as an option itself; `--end-of-options` is not used
    here because `git branch --merged` consumes the token immediately following `--merged` as its
    own argument and rejects an intervening `--end-of-options` marker (verified against the
    installed Git).
    """
    validated = _validated_revision(target)
    completed = _run(
        root,
        ("branch", "-a", "--format=%(refname:short)", "--merged", validated),
        allowed_exit_codes=(0,),
    )
    return frozenset(line.strip() for line in completed.stdout.splitlines() if line.strip())


def read_diff_stat(root: Path, base: str, head: str) -> DiffStat:
    """`git diff --stat <sha>..<sha>` between two revisions.

    Both revisions are resolved to SHAs first, so the range Git actually receives is built from
    40-character hex strings this module produced, never from the caller's text.
    """
    base_sha = resolve_revision(root, base)
    head_sha = resolve_revision(root, head)
    completed = _run(
        root,
        ("diff", "--stat", "--no-color", "--end-of-options", f"{base_sha}..{head_sha}"),
        allowed_exit_codes=(0,),
    )
    lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
    return DiffStat(base=base_sha, head=head_sha, lines=lines)


def read_diff_check(root: Path) -> DiffCheck:
    """`git diff --check` — conflict markers and whitespace errors in the working tree.

    A non-zero exit here means "problems found" (Git reports 2 for a leftover conflict marker),
    which is a result rather than a failure; only an unexpected exit code raises.
    """
    completed = _run(root, ("diff", "--check"), allowed_exit_codes=(0, 1, 2))
    problems = tuple(line for line in completed.stdout.splitlines() if line.strip())
    return DiffCheck(clean=completed.exit_code == 0, problems=problems)
