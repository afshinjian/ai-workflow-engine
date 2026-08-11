"""`python -m agentos_dashboard` — the loopback-only startup entry point (`ARCHITECTURE.md` §5).

Refuses any non-loopback bind (SC-01, enforced by `DashboardSettings.from_env` before this
module does anything else), acquires the single-instance PID lockfile (SC-02/SC-24), prints the
exact URL an operator should open, and serves via Uvicorn. `--check` builds and validates the app
and settings without binding a socket — a fast startup smoke test (`TEST_STRATEGY.md` TC-15).
It briefly acquires and releases the same advisory process lock used by a real start, then
exercises the two lazy subsystems `create_app` merely wires up but does not itself touch: it builds
the repository snapshot once (the same read `SnapshotCache.get()` performs on the first real
request) and opens one local-database connection (the same open
`DashboardDatabase.connection()` performs on the
first write), so a broken repository read or an unwritable `data/agentos_dashboard/` directory is
reported before an operator ever opens a browser tab, not on their first click (DASH-010).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

import uvicorn

from agentos_dashboard.api.lock import ExecutionLock, LockAcquisitionError, acquire_lock
from agentos_dashboard.api.snapshot_cache import SnapshotCache
from agentos_dashboard.core import DashboardError
from agentos_dashboard.main import create_app
from agentos_dashboard.settings import DashboardSettings, SettingsError
from agentos_dashboard.storage.db import DashboardDatabase

__all__ = ["main"]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m agentos_dashboard")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate local readiness without binding a socket",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    try:
        settings = DashboardSettings.from_env()
    except SettingsError as exc:
        print(f"agentos_dashboard: configuration error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        check_lock: ExecutionLock | None = None
        try:
            check_lock = acquire_lock(settings.repo_root)
            app = create_app(settings, lock=check_lock)
            cache: SnapshotCache = app.state.snapshot_cache
            database: DashboardDatabase = app.state.dashboard_database
            cache.get()
            with database.connection():
                pass
        except (DashboardError, LockAcquisitionError, OSError, sqlite3.Error) as exc:
            print(f"agentos_dashboard: configuration error: {exc}", file=sys.stderr)
            return 2
        finally:
            if check_lock is not None:
                check_lock.close()
        print(f"agentos_dashboard: configuration OK ({settings.display_url})")
        return 0

    lock: ExecutionLock
    try:
        lock = acquire_lock(settings.repo_root)
    except LockAcquisitionError as exc:
        print(f"agentos_dashboard: {exc}", file=sys.stderr)
        return 3

    try:
        app = create_app(settings, lock=lock)
        print(f"AgentOS Dashboard: {settings.display_url}")
        try:
            uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
        except OSError as exc:
            print(
                f"agentos_dashboard: failed to bind {settings.display_url}: {exc}",
                file=sys.stderr,
            )
            return 4
        except SystemExit as exc:
            # Uvicorn's own bind-failure path (`Server.startup`) logs the OSError itself and
            # then calls `sys.exit`, rather than letting the OSError propagate — caught here so
            # a port-in-use refusal is a clean exit code, not an uncaught `SystemExit`.
            if exc.code not in (None, 0):
                print(
                    f"agentos_dashboard: failed to bind {settings.display_url}",
                    file=sys.stderr,
                )
                return 4
            raise
    finally:
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
