"""The in-process cache the API layer serves every read from (`ARCHITECTURE.md` §4).

One `RepositorySnapshot` is kept per running dashboard process. `get()` builds lazily and then
keeps serving that immutable snapshot even after its fingerprint diverges, so TR-05/DR-121 can
surface the stale state instead of silently hiding it. `refresh()` is EP-20's forced rebuild:
it never blocks behind a concurrent build, because a caller waiting on `SNAPSHOT_BUILDING` wants
to know a build is already under way, not to queue behind it (`API_SPEC.md` EP-20: "409 while
building").
"""

from __future__ import annotations

import threading

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import RepositorySnapshot, build_snapshot

__all__ = ["SnapshotBuildInProgress", "SnapshotCache"]


class SnapshotBuildInProgress(Exception):
    """A rebuild was requested while another rebuild already held the lock."""


class SnapshotCache:
    """Single-instance snapshot cache (SC-24: this process serves exactly one dashboard)."""

    def __init__(self, root: RepositoryRoot) -> None:
        self._root = root
        self._lock = threading.Lock()
        self._snapshot: RepositorySnapshot | None = None

    @property
    def root(self) -> RepositoryRoot:
        return self._root

    def get(self) -> RepositorySnapshot:
        """The held snapshot, building it once if necessary.

        A stale snapshot remains held until an explicit ``refresh()``. This is intentional:
        TR-05 requires divergence to produce the persistent banner rather than a silent refresh.
        """
        with self._lock:
            if self._snapshot is None:
                self._snapshot = build_snapshot(self._root)
            return self._snapshot

    def refresh(self) -> RepositorySnapshot:
        """Force an unconditional rebuild.

        Raises `SnapshotBuildInProgress` instead of waiting if another build (a concurrent
        `refresh()`, or a `get()` racing to fill an empty cache) already holds the lock.
        """
        if not self._lock.acquire(blocking=False):
            raise SnapshotBuildInProgress()
        try:
            self._snapshot = build_snapshot(self._root)
            return self._snapshot
        finally:
            self._lock.release()
