"""Primitives shared by the dashboard's repository adapters and its snapshot builder.

This module deliberately holds only the shared base error, the shared limits, and the single
timestamp source: the three sibling modules (`paths`, `files`, `gitread`) and the snapshot
builder import *from* it and are never imported *by* it, so the package has no import cycle and
each adapter can be imported in isolation. The same layering the engine's `agentos_workflow`
package uses.

Every adapter failure in this package is a typed exception deriving from `DashboardError`; no
adapter ever raises a bare `OSError`, `ValueError`, or `subprocess` exception at its boundary
(`SECURITY_MODEL.md` SC-34: malformed or missing input degrades to a reported condition, never
a crash).
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = [
    "DEFAULT_HEAD_TAIL_BYTES",
    "DEFAULT_MAX_READ_BYTES",
    "GIT_TIMEOUT_SECONDS",
    "DashboardError",
    "utc_now",
]

# `ARCHITECTURE.md` §3: per-file read caps (default 2 MB display; head/tail views for larger).
DEFAULT_MAX_READ_BYTES = 2 * 1024 * 1024
DEFAULT_HEAD_TAIL_BYTES = 64 * 1024

# `SECURITY_MODEL.md` SC-25: 5 s git subprocess timeout.
GIT_TIMEOUT_SECONDS = 5


class DashboardError(Exception):
    """Base class for every typed failure this package raises."""


def utc_now() -> datetime:
    """The single timestamp source, so snapshots are comparable and always timezone-aware."""
    return datetime.now(UTC)
