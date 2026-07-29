"""TC-08 — snapshot construction, fingerprint stability, staleness, and TR-04 findings."""

from __future__ import annotations

import dataclasses
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentos_dashboard.core import DashboardError
from agentos_dashboard.core import snapshot as snapshot_module
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import (
    WATCHED_FILES,
    FindingSeverity,
    RepositorySnapshot,
    SnapshotFingerprint,
    build_snapshot,
    compute_fingerprint,
)

from .conftest import git, write

FIXED_TIME = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def fixed_now() -> datetime:
    return FIXED_TIME


def populate(repo: Path) -> None:
    """Give a repository every watched file, so the default case has no missing-file finding."""
    for relative in WATCHED_FILES:
        write(repo, relative, f"content of {relative}\n")


@pytest.fixture
def populated_repo(git_repo: Path) -> Path:
    populate(git_repo)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "populate watched files")
    return git_repo


@pytest.fixture
def populated_root(populated_repo: Path) -> RepositoryRoot:
    return RepositoryRoot.from_path(populated_repo)


def test_watched_files_match_the_source_of_truth_document() -> None:
    """The list is normative (`SOURCE_OF_TRUTH.md` §3); drift is a defect, not a preference."""
    assert WATCHED_FILES == (
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


def test_snapshot_of_a_fully_populated_repository(populated_root: RepositoryRoot) -> None:
    snapshot = build_snapshot(populated_root, now=fixed_now)
    assert snapshot.findings == ()
    assert snapshot.generated_at == FIXED_TIME
    assert snapshot.head is not None
    assert snapshot.git_status is not None
    assert snapshot.git_status.branch == "main"
    assert [state.path for state in snapshot.fingerprint.files] == list(WATCHED_FILES)
    assert all(state.exists for state in snapshot.fingerprint.files)


def test_snapshot_is_immutable(populated_root: RepositoryRoot) -> None:
    snapshot = build_snapshot(populated_root, now=fixed_now)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.fingerprint = snapshot.fingerprint  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.fingerprint.files[0].exists = False  # type: ignore[misc]
    assert isinstance(snapshot.fingerprint.files, tuple)
    assert isinstance(snapshot.findings, tuple)


def test_fingerprint_is_stable_across_repeated_reads(populated_root: RepositoryRoot) -> None:
    first = compute_fingerprint(populated_root)
    second = compute_fingerprint(populated_root)
    assert first.digest == second.digest
    assert build_snapshot(populated_root, now=fixed_now).fingerprint.digest == first.digest


def test_fingerprint_ignores_a_file_outside_the_watched_list(
    populated_root: RepositoryRoot, populated_repo: Path
) -> None:
    before = compute_fingerprint(populated_root).digest
    write(populated_repo, "docs/unwatched.md", "not watched\n")
    assert compute_fingerprint(populated_root).digest == before


def test_fingerprint_changes_when_a_watched_file_changes(
    populated_root: RepositoryRoot, populated_repo: Path
) -> None:
    snapshot = build_snapshot(populated_root, now=fixed_now)
    assert snapshot.is_stale() is False

    target = populated_repo / "docs" / "TASK_QUEUE.md"
    target.write_text("edited\n", encoding="utf-8")
    # mtime granularity is not guaranteed to distinguish two writes in the same instant, so the
    # timestamp is advanced explicitly; the size change alone would also suffice here, which is
    # exactly why the fingerprint carries both.
    stat_result = target.stat()
    os.utime(target, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1_000_000_000))

    assert snapshot.is_stale() is True
    assert compute_fingerprint(populated_root).digest != snapshot.fingerprint.digest


def test_fingerprint_changes_when_head_moves(
    populated_root: RepositoryRoot, populated_repo: Path
) -> None:
    snapshot = build_snapshot(populated_root, now=fixed_now)
    write(populated_repo, "unwatched-source.py", "print('x')\n")
    git(populated_repo, "add", "unwatched-source.py")
    git(populated_repo, "commit", "--quiet", "-m", "a commit touching no watched file")

    assert snapshot.head != compute_fingerprint(populated_root).head
    assert snapshot.is_stale() is True


def test_fingerprint_changes_when_a_watched_file_is_deleted(
    populated_root: RepositoryRoot, populated_repo: Path
) -> None:
    snapshot = build_snapshot(populated_root, now=fixed_now)
    (populated_repo / "docs" / "CONTEXT.md").unlink()
    assert snapshot.is_stale() is True


def test_missing_watched_file_becomes_an_explicit_unknown_plus_a_finding(
    git_repo: Path,
) -> None:
    """TR-04: never a silent default, and never a failed snapshot."""
    write(git_repo, "docs/TASK_QUEUE.md", "queue\n")
    root = RepositoryRoot.from_path(git_repo)

    snapshot = build_snapshot(root, now=fixed_now)
    states = {state.path: state for state in snapshot.fingerprint.files}
    assert states["docs/TASK_QUEUE.md"].exists is True
    missing = {
        finding.path for finding in snapshot.findings if finding.rule == "watched_file_unavailable"
    }
    assert "docs/CONTEXT.md" in missing
    assert "docs/TASK_QUEUE.md" not in missing
    assert states["docs/CONTEXT.md"].exists is False
    assert states["docs/CONTEXT.md"].size_bytes is None
    for finding in snapshot.findings:
        assert finding.severity is FindingSeverity.WARNING


def test_snapshot_of_a_directory_that_is_not_a_repository_degrades_to_findings(
    workspace: Path, root: RepositoryRoot
) -> None:
    """SC-34: a non-repository must produce findings, not an exception."""
    write(workspace, "docs/TASK_QUEUE.md", "queue\n")
    snapshot = build_snapshot(root, now=fixed_now)

    rules = {finding.rule for finding in snapshot.findings}
    assert {"git_head_unavailable", "git_status_unavailable"} <= rules
    assert snapshot.git_status is None
    assert snapshot.head is None
    # The file half of the snapshot still works.
    states = {state.path: state for state in snapshot.fingerprint.files}
    assert states["docs/TASK_QUEUE.md"].exists is True


def test_snapshot_of_an_unborn_repository_reports_it(tmp_path: Path) -> None:
    repo = tmp_path / "unborn"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    populate(repo)

    snapshot = build_snapshot(RepositoryRoot.from_path(repo), now=fixed_now)
    assert snapshot.head is None
    assert {finding.rule for finding in snapshot.findings} == {"git_head_unborn"}
    assert snapshot.git_status is not None
    assert snapshot.git_status.unborn is True


def test_is_stale_reports_true_when_the_fingerprint_cannot_be_computed(
    populated_root: RepositoryRoot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The honest answer to "is my view current?" when the repository is unreadable is "no"."""
    snapshot = build_snapshot(populated_root, now=fixed_now)

    def exploding_fingerprint(root: RepositoryRoot) -> SnapshotFingerprint:
        raise DashboardError("repository became unreadable")

    monkeypatch.setattr(snapshot_module, "compute_fingerprint", exploding_fingerprint)
    assert snapshot.is_stale() is True


def test_snapshot_carries_the_root_it_was_built_from(populated_root: RepositoryRoot) -> None:
    snapshot: RepositorySnapshot = build_snapshot(populated_root, now=fixed_now)
    assert snapshot.root is populated_root
