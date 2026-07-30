"""`api.snapshot_cache.SnapshotCache` — lazy build, staleness rebuild, refresh contention."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_dashboard.api.snapshot_cache import SnapshotBuildInProgress, SnapshotCache
from agentos_dashboard.core.paths import RepositoryRoot


def test_get_builds_once_and_then_serves_the_cached_snapshot(root: RepositoryRoot) -> None:
    cache = SnapshotCache(root)
    first = cache.get()
    second = cache.get()
    assert first is second


def test_get_rebuilds_after_a_watched_file_changes(workspace: Path, root: RepositoryRoot) -> None:
    cache = SnapshotCache(root)
    first = cache.get()
    (workspace / "docs").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "PROJECT_STATE.md").write_text("Current Version: 9.9.9\n")
    second = cache.get()
    assert first.fingerprint.digest != second.fingerprint.digest


def test_refresh_forces_a_rebuild(root: RepositoryRoot) -> None:
    cache = SnapshotCache(root)
    first = cache.get()
    refreshed = cache.refresh()
    assert refreshed is not first
    assert cache.get() is refreshed


def test_refresh_raises_when_the_lock_is_already_held(root: RepositoryRoot) -> None:
    cache = SnapshotCache(root)
    cache._lock.acquire()
    try:
        with pytest.raises(SnapshotBuildInProgress):
            cache.refresh()
    finally:
        cache._lock.release()
