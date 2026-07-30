"""`python -m agentos_dashboard` — the loopback-only startup entry point (`ARCHITECTURE.md` §5).

Refuses any non-loopback bind (SC-01, enforced by `DashboardSettings.from_env` before this
module does anything else), acquires the single-instance PID lockfile (SC-02/SC-24), prints the
exact URL an operator should open, and serves via Uvicorn. `--check` builds and validates the app
and settings without binding a socket or a lockfile — a fast startup smoke test
(`TEST_STRATEGY.md` TC-15) that never leaves a stray lockfile behind.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from agentos_dashboard.api.lock import ExecutionLock, LockAcquisitionError, acquire_lock
from agentos_dashboard.main import create_app
from agentos_dashboard.settings import DashboardSettings, SettingsError

__all__ = ["main"]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m agentos_dashboard")
    parser.add_argument(
        "--check",
        action="store_true",
        help="build and validate the app without binding a socket or acquiring the lockfile",
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
        create_app(settings)
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
