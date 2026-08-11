"""PG-12 (`UI_SPEC.md`): the bounded, read-only Settings/About surface.

`DECISIONS.md` DD-16 bounds this page to repo root display, bind/port, configured caps, lock
status, and about information, plus a browser-side copy-config action — nothing here is a new
adapter or a new read path, only a view over data the process already holds
(`DashboardSettings`, the security/file/git module caps, and the current process's
`ExecutionLock`). Editable configuration, persistent preferences, governance editing, repository
switching, agent/provider configuration, secret editing, and any authoritative write are all
explicitly excluded — this module has no write path and takes no request body.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos_dashboard import __version__ as DASHBOARD_VERSION
from agentos_dashboard.api.lock import ExecutionLock
from agentos_dashboard.api.security import MAX_REQUEST_BODY_BYTES
from agentos_dashboard.core import (
    DEFAULT_HEAD_TAIL_BYTES,
    DEFAULT_MAX_READ_BYTES,
    GIT_TIMEOUT_SECONDS,
)
from agentos_dashboard.settings import DashboardSettings

__all__ = ["CapLimit", "LockStatus", "SettingsView", "build_settings_view"]


@dataclass(frozen=True)
class CapLimit:
    name: str
    value: int
    unit: str
    description: str


@dataclass(frozen=True)
class LockStatus:
    held: bool
    path: str | None
    pid: int | None


@dataclass(frozen=True)
class SettingsView:
    repo_root: str
    host: str
    port: int
    display_url: str
    allowed_host_headers: tuple[str, ...]
    caps: tuple[CapLimit, ...]
    lock: LockStatus
    dashboard_version: str


def build_settings_view(settings: DashboardSettings, lock: ExecutionLock | None) -> SettingsView:
    """Assemble PG-12's view from already-constructed process state — no new read is performed."""
    lock_status = LockStatus(
        held=lock is not None,
        path=str(lock.info.path) if lock is not None else None,
        pid=lock.info.pid if lock is not None else None,
    )
    caps = (
        CapLimit(
            name="Request body",
            value=MAX_REQUEST_BODY_BYTES,
            unit="bytes",
            description="maximum accepted size of any POST/PUT request body",
        ),
        CapLimit(
            name="File read",
            value=DEFAULT_MAX_READ_BYTES,
            unit="bytes",
            description="maximum bytes read from a single repository file before truncation",
        ),
        CapLimit(
            name="Head/tail excerpt",
            value=DEFAULT_HEAD_TAIL_BYTES,
            unit="bytes",
            description="size of the head/tail window shown for a truncated file",
        ),
        CapLimit(
            name="Git subprocess timeout",
            value=GIT_TIMEOUT_SECONDS,
            unit="seconds",
            description="hard timeout applied to every Git read subprocess",
        ),
    )
    return SettingsView(
        repo_root=str(settings.repo_root),
        host=settings.host,
        port=settings.port,
        display_url=settings.display_url,
        allowed_host_headers=tuple(sorted(settings.allowed_host_headers)),
        caps=caps,
        lock=lock_status,
        dashboard_version=DASHBOARD_VERSION,
    )
