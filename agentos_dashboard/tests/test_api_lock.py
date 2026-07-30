"""`api.lock` — the single-instance PID lockfile (SC-02/SC-24, EN-27)."""

from __future__ import annotations

import os
from pathlib import Path

from agentos_dashboard.api.lock import LockAcquisitionError, acquire_lock, lock_path_for


def test_acquire_and_close_round_trips(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    try:
        assert lock.info.path.exists()
        assert lock.info.path.read_text(encoding="utf-8").strip() == str(os.getpid())
        assert lock.info.pid == os.getpid()
    finally:
        lock.close()
    assert not lock.info.path.exists()


def test_second_acquire_by_a_live_process_is_refused(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    try:
        try:
            acquire_lock(workspace)
        except LockAcquisitionError as exc:
            assert str(os.getpid()) in str(exc)
        else:
            raise AssertionError("expected LockAcquisitionError")
    finally:
        lock.close()


def test_stale_lock_from_a_dead_pid_is_reclaimed(workspace: Path) -> None:
    path = lock_path_for(workspace)
    # A PID that (almost certainly) does not exist: the max on Linux is well below this.
    path.write_text("999999999", encoding="utf-8")
    try:
        lock = acquire_lock(workspace)
        try:
            assert lock.info.pid == os.getpid()
        finally:
            lock.close()
    finally:
        if path.exists():
            path.unlink()


def test_lock_path_is_stable_and_keyed_by_repository_root(workspace: Path, tmp_path: Path) -> None:
    other = tmp_path / "other-repo"
    other.mkdir()
    assert lock_path_for(workspace) == lock_path_for(workspace)
    assert lock_path_for(workspace) != lock_path_for(other)


def test_lock_close_is_a_no_op_when_already_released(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    lock.close()
    lock.close()  # must not raise


def test_lock_close_never_deletes_another_processes_lockfile(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    try:
        lock.info.path.write_text("123456789", encoding="utf-8")
        lock.close()
        assert lock.info.path.exists()
    finally:
        if lock.info.path.exists():
            lock.info.path.unlink()
