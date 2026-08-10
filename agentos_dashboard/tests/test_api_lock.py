"""`api.lock` — the single-instance PID lockfile (SC-02/SC-24, EN-27)."""

from __future__ import annotations

import multiprocessing
import multiprocessing.synchronize
import os
from pathlib import Path

import pytest

from agentos_dashboard.api.lock import LockAcquisitionError, acquire_lock, lock_path_for


def _hold_lock_until_released(
    workspace: Path,
    ready: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    """Child-process body for the real cross-process contention test below."""
    lock = acquire_lock(workspace)
    ready.set()
    release.wait(timeout=10)
    lock.close()


def _acquire_then_exit(workspace: Path, ready: multiprocessing.synchronize.Event) -> None:
    acquire_lock(workspace)
    ready.set()
    os._exit(0)


def test_acquire_and_close_round_trips(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    try:
        assert lock.info.path.exists()
        assert lock.info.path.read_text(encoding="utf-8").strip() == str(os.getpid())
        assert lock.info.pid == os.getpid()
    finally:
        lock.close()
    # The temp sentinel remains, but it carries no live ownership after close.
    assert lock.info.path.exists()
    replacement = acquire_lock(workspace)
    replacement.close()


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


def test_malformed_stale_lock_is_reclaimed(workspace: Path) -> None:
    path = lock_path_for(workspace)
    path.write_text("not-a-pid", encoding="utf-8")
    lock = acquire_lock(workspace)
    try:
        assert path.read_text(encoding="utf-8") == str(os.getpid())
    finally:
        lock.close()


def test_process_exit_releases_lock_without_explicit_cleanup(workspace: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    ready = ctx.Event()
    child = ctx.Process(target=_acquire_then_exit, args=(workspace, ready))
    child.start()
    assert ready.wait(timeout=10)
    child.join(timeout=10)
    assert child.exitcode == 0
    lock = acquire_lock(workspace)
    lock.close()


def test_symlink_lockfile_is_refused_without_touching_target(
    workspace: Path, tmp_path: Path
) -> None:
    target = tmp_path / "target"
    target.write_text("preserved", encoding="utf-8")
    path = lock_path_for(workspace)
    path.symlink_to(target)
    with pytest.raises(LockAcquisitionError):
        acquire_lock(workspace)
    assert target.read_text(encoding="utf-8") == "preserved"


def test_concurrent_process_contention_is_refused_then_reclaimable_after_release(
    workspace: Path,
) -> None:
    """SC-24: a genuine second OS process — not just a repeated call in this test process —
    holding the lock refuses a concurrent acquire, and releasing it lets a fresh acquire
    succeed. `test_second_acquire_by_a_live_process_is_refused` above proves the same liveness
    check via `os.getpid()`; this proves it holds across a real process boundary too."""
    ctx = multiprocessing.get_context("fork")
    ready = ctx.Event()
    release = ctx.Event()
    child = ctx.Process(target=_hold_lock_until_released, args=(workspace, ready, release))
    child.start()
    try:
        assert ready.wait(timeout=10), "child process never acquired the lock"
        try:
            acquire_lock(workspace)
        except LockAcquisitionError as exc:
            assert str(child.pid) in str(exc)
        else:
            raise AssertionError("expected LockAcquisitionError while the child holds the lock")
    finally:
        release.set()
        child.join(timeout=10)
    assert child.exitcode == 0

    lock = acquire_lock(workspace)
    lock.close()


def test_lock_path_is_stable_and_keyed_by_repository_root(workspace: Path, tmp_path: Path) -> None:
    other = tmp_path / "other-repo"
    other.mkdir()
    assert lock_path_for(workspace) == lock_path_for(workspace)
    assert lock_path_for(workspace) != lock_path_for(other)


def test_lock_close_is_a_no_op_when_already_released(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    lock.close()
    lock.close()  # must not raise


def test_lock_close_releases_ownership_without_unlinking_the_sentinel(workspace: Path) -> None:
    lock = acquire_lock(workspace)
    try:
        lock.close()
        assert lock.info.path.exists()
        replacement = acquire_lock(workspace)
        replacement.close()
    finally:
        if lock.info.path.exists():
            lock.info.path.unlink()
