"""`AWED_`-prefixed environment settings (`ARCHITECTURE.md` §6; SC-01, SC-10).

No `.env` file is ever loaded: SC-10 requires credential/configuration input to come only from
the real process environment, never from a dotenv file that could itself carry secrets into the
repository working copy. Every setting is validated eagerly in `from_env`, so a misconfiguration
(a non-loopback bind address, an unusable repository root, a malformed port) fails before the
server acquires a socket or a lockfile, not on first request (SC-01).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from agentos_dashboard.core.paths import RepositoryRoot, RepositoryRootError

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ENV_PREFIX",
    "LOOPBACK_HOSTS",
    "DashboardSettings",
    "SettingsError",
]

ENV_PREFIX = "AWED_"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8642

# SC-01: the complete set of bind/Host addresses this application ever trusts. Anything else is
# refused, both as a bind address (`__main__.py`) and as an incoming `Host` header (`api.security`).
LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})


class SettingsError(Exception):
    """A configured setting is invalid. Raised before anything binds a socket or a lockfile."""


class DashboardSettings(BaseModel):
    """Validated startup configuration. Immutable once constructed."""

    model_config = {"frozen": True}

    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    repo_root: Path

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value not in LOOPBACK_HOSTS:
            raise ValueError(
                f"non-loopback bind address refused (SC-01): {value!r}; "
                f"allowed: {sorted(LOOPBACK_HOSTS)}"
            )
        return value

    @property
    def display_url(self) -> str:
        """The exact URL `__main__.py` prints on startup."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    @property
    def allowed_host_headers(self) -> frozenset[str]:
        """SC-36: every `Host` header value this instance accepts, port-qualified.

        An IPv6 literal (`::1`) must be bracketed in a `Host` header per RFC 3986/7230 — a bare
        `::1:8642` is not what any real client sends, so accepting it would accept nothing a
        browser ever actually produces.
        """
        return frozenset(
            f"[{host}]:{self.port}" if ":" in host else f"{host}:{self.port}"
            for host in LOOPBACK_HOSTS
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DashboardSettings:
        """Build settings from `AWED_`-prefixed environment variables only.

        `env` defaults to the real process environment; a caller may pass an explicit mapping
        (tests do) so behavior never depends on ambient variables leaking into a test process.
        """
        source: Mapping[str, str] = env if env is not None else os.environ

        host = source.get(f"{ENV_PREFIX}HOST", DEFAULT_HOST)

        port_raw = source.get(f"{ENV_PREFIX}PORT", str(DEFAULT_PORT))
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise SettingsError(f"{ENV_PREFIX}PORT must be an integer: {port_raw!r}") from exc

        repo_root_raw = source.get(f"{ENV_PREFIX}REPO_ROOT", os.getcwd())
        try:
            root = RepositoryRoot.from_path(repo_root_raw)
        except RepositoryRootError as exc:
            raise SettingsError(str(exc)) from exc

        try:
            return cls(host=host, port=port, repo_root=root.path)
        except ValidationError as exc:
            raise SettingsError(str(exc)) from exc
