"""SC-02/SC-24: the single-instance PID lockfile (EN-27 `ExecutionLock`).

The lockfile lives outside the repository entirely — under the platform temp directory, keyed by
a digest of the resolved repository root — so acquiring it is never a repository write
(`SECURITY_MODEL.md` §5) and DASH-008's not-yet-created `data/agentos_dashboard/` directory is
never touched by this stage. One dashboard process per repository root: a second
`python -m agentos_dashboard` against the same root refuses to start rather than silently running
two servers against one repository.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agentos_dashboard.core import utc_now

__all__ = ["ExecutionLock", "LockAcquisitionError", "LockInfo", "acquire_lock", "lock_path_for"]


class LockAcquisitionError(Exception):
    """Another live process already holds the lock for this repository root."""


@dataclass(frozen=True)
class LockInfo:
    path: Path
    acquired_at: datetime
    pid: int


def lock_path_for(repo_root: Path) -> Path:
    digest = hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"agentos_dashboard-{digest}.lock"


class ExecutionLock:
    """An acquired PID lockfile, released by `close()` or on context-manager exit."""

    def __init__(self, info: LockInfo) -> None:
        self.info = info

    def close(self) -> None:
        try:
            if self.info.path.read_text(encoding="utf-8").strip() == str(self.info.pid):
                self.info.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> ExecutionLock:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _living_pid(path: Path) -> int | None:
    """The PID recorded in `path` if that process still exists, else `None` (stale lockfile)."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw.isdigit():
        return None
    pid = int(raw)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid  # exists, owned by another user — still alive
    return pid


def _create_exclusive(path: Path, pid: int) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(pid))


def acquire_lock(repo_root: Path) -> ExecutionLock:
    """Acquire the single-instance lock for `repo_root`, or raise `LockAcquisitionError`.

    A lockfile left behind by a process that no longer exists (a crash, `kill -9`) is reclaimed
    automatically: `os.kill(pid, 0)` proves liveness without sending a real signal, so a stale PID
    never permanently wedges the dashboard (SC-26 — restart recovers all derived state).
    """
    path = lock_path_for(repo_root)
    pid = os.getpid()
    try:
        _create_exclusive(path, pid)
    except FileExistsError:
        existing_pid = _living_pid(path)
        if existing_pid is not None:
            raise LockAcquisitionError(
                f"another dashboard process (pid {existing_pid}) already holds the lock for "
                f"this repository root: {path}"
            ) from None
        try:
            path.unlink()
        except OSError:
            pass
        try:
            _create_exclusive(path, pid)
        except FileExistsError as exc:
            raise LockAcquisitionError(
                f"could not acquire lock at {path}: lost the race with another process"
            ) from exc
    return ExecutionLock(LockInfo(path=path, acquired_at=utc_now(), pid=pid))
