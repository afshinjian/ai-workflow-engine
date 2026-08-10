"""SC-02/SC-24: the single-instance PID lockfile (EN-27 `ExecutionLock`).

The lockfile lives outside the repository entirely — under the platform temp directory, keyed by
a digest of the resolved repository root — so acquiring it is never a repository write
(`SECURITY_MODEL.md` §5) and DASH-008's not-yet-created `data/agentos_dashboard/` directory is
never touched by this stage. One dashboard process per repository root: a second
`python -m agentos_dashboard` against the same root refuses to start rather than silently running
two servers against one repository.
"""

from __future__ import annotations

import fcntl
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

    def __init__(self, info: LockInfo, fd: int) -> None:
        self.info = info
        self._fd: int | None = fd

    def close(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> ExecutionLock:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def acquire_lock(repo_root: Path) -> ExecutionLock:
    """Acquire the single-instance lock for `repo_root`, or raise `LockAcquisitionError`.

    The PID file is a persistent temp-directory sentinel; live ownership is an advisory lock on
    its open descriptor. The kernel releases that ownership on normal close *and* abrupt process
    exit, so recovery has no read/unlink race and a stale or malformed PID string cannot wedge a
    restart (SC-26). The file is intentionally not unlinked at close: unlinking a locked inode can
    let a third process create and lock a second inode while a waiting process acquires the first.
    """
    path = lock_path_for(repo_root)
    pid = os.getpid()
    try:
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LockAcquisitionError(f"could not open the dashboard lock at {path}") from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.lseek(fd, 0, os.SEEK_SET)
            holder = os.read(fd, 64).decode("ascii", errors="replace").strip()
            label = f"pid {holder}" if holder.isdigit() else "unknown pid"
            raise LockAcquisitionError(
                f"another dashboard process ({label}) already holds the lock for "
                f"this repository root: {path}"
            ) from exc
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(pid).encode("ascii"))
        os.fsync(fd)
        return ExecutionLock(LockInfo(path=path, acquired_at=utc_now(), pid=pid), fd)
    except BaseException:
        os.close(fd)
        raise
