"""Immutable repository snapshot and its staleness fingerprint (`ARCHITECTURE.md` §3-4).

A snapshot is one coherent read of the repository: the watched files of
`SOURCE_OF_TRUTH.md` §3 plus Git `HEAD`, captured together and never mutated afterwards. Every
page in later stages renders exactly one snapshot, so an operator never sees half of one read
and half of another.

Two rules from `SOURCE_OF_TRUTH.md` are implemented here rather than left to callers:

* **TR-04** — a missing or unreadable watched file becomes an explicit "unknown" entry plus a
  finding. It never becomes a silent default, and it never aborts the snapshot: a repository
  that legitimately lacks one of these files still yields a usable view of the rest.
* **TR-05** — staleness is a comparison between the fingerprint a snapshot was built with and
  the fingerprint of the repository now. `is_stale()` re-reads; it never guesses from a clock.

The fingerprint intentionally uses `stat` facts (existence, size, mtime) rather than content
hashes: it must be cheap enough to evaluate on every request, and its job is to detect that a
re-read is needed, not to prove two files are byte-identical.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agentos_dashboard.core import DashboardError, utc_now
from agentos_dashboard.core.files import FileAccessError, FileRefusal, stat_file
from agentos_dashboard.core.gitread import GitReadError, GitStatus, read_head, read_status
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot

__all__ = [
    "WATCHED_FILES",
    "FindingSeverity",
    "RepositorySnapshot",
    "SnapshotFinding",
    "SnapshotFingerprint",
    "WatchedFileState",
    "build_snapshot",
    "compute_fingerprint",
]

# `SOURCE_OF_TRUTH.md` §3, verbatim and in that document's order. Extending this list is a
# MINOR change to that document, so the list lives here as data rather than being derived.
WATCHED_FILES: tuple[str, ...] = (
    "docs/PROJECT_STATE.md",
    "docs/TASK_QUEUE.md",
    "docs/current_task.md",
    "docs/remaining_tasks.md",
    "docs/CONTEXT.md",
    "docs/DECISION_LOG.md",
    "docs/CHANGELOG.md",
    "self-governance.yaml",
    "pyproject.toml",
    "handover/PROJECT_HANDOVER.md",
    "handover/PROJECT_CHECKSUM.md",
    "docs/implementation/orchestration/implementation-state.yaml",
)


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class SnapshotFinding:
    """A condition the operator must be told about, never resolved silently (TR-01, TR-04)."""

    rule: str
    severity: FindingSeverity
    message: str
    path: str | None = None


@dataclass(frozen=True)
class WatchedFileState:
    """One watched file's `stat` facts. `exists=False` is a first-class state, not an error."""

    path: str
    exists: bool
    size_bytes: int | None = None
    mtime_ns: int | None = None

    def canonical(self) -> str:
        if not self.exists:
            return f"{self.path}\tmissing"
        return f"{self.path}\t{self.size_bytes}\t{self.mtime_ns}"


@dataclass(frozen=True)
class SnapshotFingerprint:
    """The staleness key: watched-file `stat` facts plus HEAD, reduced to one digest."""

    head: str | None
    files: tuple[WatchedFileState, ...]
    digest: str

    @classmethod
    def of(cls, head: str | None, files: tuple[WatchedFileState, ...]) -> SnapshotFingerprint:
        payload = "\n".join(("head\t" + (head or "-"), *(state.canonical() for state in files)))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return cls(head=head, files=files, digest=digest)


@dataclass(frozen=True)
class RepositorySnapshot:
    """EN-02: an immutable read of the repository, with its own staleness test."""

    root: RepositoryRoot
    generated_at: datetime
    fingerprint: SnapshotFingerprint
    git_status: GitStatus | None
    findings: tuple[SnapshotFinding, ...]

    @property
    def head(self) -> str | None:
        return self.fingerprint.head

    def is_stale(self) -> bool:
        """True when the repository has changed since this snapshot was built.

        Re-reads the fingerprint inputs. A fingerprint that cannot be computed at all is
        reported as stale rather than fresh: the honest answer to "is my view current?" when
        the repository has become unreadable is "no".
        """
        try:
            current = compute_fingerprint(self.root)
        except DashboardError:
            return True
        return current.digest != self.fingerprint.digest


def _watched_file_state(
    root: RepositoryRoot, relative: str
) -> tuple[WatchedFileState, SnapshotFinding | None]:
    try:
        facts = stat_file(root, relative)
    except FileAccessError as exc:
        severity = (
            FindingSeverity.WARNING
            if exc.refusal is FileRefusal.NOT_FOUND
            else FindingSeverity.ERROR
        )
        return (
            WatchedFileState(path=relative, exists=False),
            SnapshotFinding(
                rule="watched_file_unavailable",
                severity=severity,
                message=f"watched file could not be read: {exc.detail}",
                path=relative,
            ),
        )
    except PathRefusedError as exc:
        # Only reachable if WATCHED_FILES ever names a denied path; a configuration defect, so
        # it is surfaced rather than swallowed.
        return (
            WatchedFileState(path=relative, exists=False),
            SnapshotFinding(
                rule="watched_file_refused",
                severity=FindingSeverity.ERROR,
                message=f"watched file was refused by the path adapter: {exc.detail}",
                path=relative,
            ),
        )
    return (
        WatchedFileState(
            path=relative,
            exists=True,
            size_bytes=facts.size_bytes,
            mtime_ns=facts.mtime_ns,
        ),
        None,
    )


def compute_fingerprint(root: RepositoryRoot) -> SnapshotFingerprint:
    """The current fingerprint of `root`, without building a whole snapshot.

    Used by `RepositorySnapshot.is_stale`, and cheap enough to call on every request. A Git
    failure yields `head=None` rather than raising, so a repository that is temporarily
    unreadable by Git still produces a comparable fingerprint (and a snapshot built from it
    carries the corresponding finding).
    """
    try:
        head = read_head(root.path)
    except GitReadError:
        head = None
    states = tuple(_watched_file_state(root, relative)[0] for relative in WATCHED_FILES)
    return SnapshotFingerprint.of(head, states)


def build_snapshot(
    root: RepositoryRoot,
    *,
    now: Callable[[], datetime] = utc_now,
) -> RepositorySnapshot:
    """Build one immutable snapshot of `root`.

    Never raises for repository content: a missing watched file, a repository that is not a Git
    worktree, and a Git binary that is absent all become findings on an otherwise usable
    snapshot (SC-34). Only a root that is not a usable directory is an error, and that is
    `RepositoryRoot.from_path`'s business, before a snapshot exists.
    """
    findings: list[SnapshotFinding] = []

    head: str | None = None
    git_status: GitStatus | None = None
    try:
        head = read_head(root.path)
    except GitReadError as exc:
        findings.append(
            SnapshotFinding(
                rule="git_head_unavailable",
                severity=FindingSeverity.ERROR,
                message=f"HEAD could not be read: {exc.detail}",
            )
        )
    else:
        if head is None:
            findings.append(
                SnapshotFinding(
                    rule="git_head_unborn",
                    severity=FindingSeverity.WARNING,
                    message="the repository has no commit yet (unborn branch)",
                )
            )

    try:
        git_status = read_status(root.path)
    except GitReadError as exc:
        findings.append(
            SnapshotFinding(
                rule="git_status_unavailable",
                severity=FindingSeverity.ERROR,
                message=f"git status could not be read: {exc.detail}",
            )
        )

    states: list[WatchedFileState] = []
    for relative in WATCHED_FILES:
        state, finding = _watched_file_state(root, relative)
        states.append(state)
        if finding is not None:
            findings.append(finding)

    return RepositorySnapshot(
        root=root,
        generated_at=now(),
        fingerprint=SnapshotFingerprint.of(head, tuple(states)),
        git_status=git_status,
        findings=tuple(findings),
    )
