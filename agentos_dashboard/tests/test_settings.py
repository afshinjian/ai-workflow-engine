"""`DashboardSettings.from_env` — AWED_-prefixed parsing, loopback-only enforcement (SC-01)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_dashboard.settings import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DashboardSettings,
    SettingsError,
)


def test_defaults_when_no_env_vars_set(workspace: Path) -> None:
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(workspace)})
    assert settings.host == DEFAULT_HOST
    assert settings.port == DEFAULT_PORT
    assert settings.repo_root == workspace.resolve()


def test_host_and_port_overridden_from_env(workspace: Path) -> None:
    settings = DashboardSettings.from_env(
        {"AWED_HOST": "localhost", "AWED_PORT": "9001", "AWED_REPO_ROOT": str(workspace)}
    )
    assert settings.host == "localhost"
    assert settings.port == 9001


@pytest.mark.parametrize("host", ["0.0.0.0", "1.2.3.4", "example.com", ""])
def test_non_loopback_host_is_refused(workspace: Path, host: str) -> None:
    with pytest.raises(SettingsError):
        DashboardSettings.from_env({"AWED_HOST": host, "AWED_REPO_ROOT": str(workspace)})


def test_non_integer_port_is_refused(workspace: Path) -> None:
    with pytest.raises(SettingsError):
        DashboardSettings.from_env({"AWED_PORT": "not-a-number", "AWED_REPO_ROOT": str(workspace)})


@pytest.mark.parametrize("port", ["0", "70000", "-1"])
def test_out_of_range_port_is_refused(workspace: Path, port: str) -> None:
    with pytest.raises(SettingsError):
        DashboardSettings.from_env({"AWED_PORT": port, "AWED_REPO_ROOT": str(workspace)})


def test_missing_repo_root_is_refused(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SettingsError):
        DashboardSettings.from_env({"AWED_REPO_ROOT": str(missing)})


def test_display_url_reflects_host_and_port(workspace: Path) -> None:
    settings = DashboardSettings.from_env(
        {"AWED_HOST": "127.0.0.1", "AWED_PORT": "8642", "AWED_REPO_ROOT": str(workspace)}
    )
    assert settings.display_url == "http://127.0.0.1:8642"


def test_allowed_host_headers_covers_every_loopback_alias(workspace: Path) -> None:
    settings = DashboardSettings.from_env({"AWED_PORT": "8642", "AWED_REPO_ROOT": str(workspace)})
    assert settings.allowed_host_headers == frozenset(
        {"127.0.0.1:8642", "localhost:8642", "[::1]:8642"}
    )


def test_settings_are_frozen(workspace: Path) -> None:
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(workspace)})
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError on a frozen model
        settings.port = 1234


def test_from_env_defaults_to_real_process_environment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    monkeypatch.setenv("AWED_PORT", "9100")
    settings = DashboardSettings.from_env()
    assert settings.port == 9100
    assert settings.repo_root == workspace.resolve()
