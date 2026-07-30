"""`python -m agentos_dashboard` — startup smoke tests (`TEST_STRATEGY.md` TC-15)."""

from __future__ import annotations

import contextlib
import socket
from pathlib import Path

import pytest

from agentos_dashboard import __main__ as dunder_main
from agentos_dashboard.api.lock import acquire_lock, lock_path_for


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_check_mode_succeeds_with_valid_configuration(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    exit_code = dunder_main.main(["--check"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "configuration OK" in out


def test_check_mode_never_creates_a_lockfile(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    dunder_main.main(["--check"])
    assert not lock_path_for(workspace).exists()


def test_non_loopback_host_is_refused_before_any_bind(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    monkeypatch.setenv("AWED_HOST", "0.0.0.0")
    exit_code = dunder_main.main([])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "configuration error" in err
    assert "Traceback" not in err
    assert not lock_path_for(workspace).exists()


def test_invalid_port_is_refused_with_a_clean_error(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    monkeypatch.setenv("AWED_PORT", "not-a-port")
    exit_code = dunder_main.main(["--check"])
    assert exit_code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_lock_already_held_is_refused_with_a_clean_error(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    held = acquire_lock(workspace)
    try:
        monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
        monkeypatch.setenv("AWED_PORT", str(_free_port()))
        exit_code = dunder_main.main([])
        assert exit_code == 3
        err = capsys.readouterr().err
        assert "Traceback" not in err
    finally:
        held.close()


def test_port_already_in_use_is_refused_with_a_clean_error_and_releases_the_lock(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    port = _free_port()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    try:
        monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
        monkeypatch.setenv("AWED_PORT", str(port))
        exit_code = dunder_main.main([])
        assert exit_code == 4
        err = capsys.readouterr().err
        assert "Traceback" not in err
    finally:
        blocker.close()
    assert not lock_path_for(workspace).exists()
