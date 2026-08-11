"""`python -m agentos_dashboard` — startup smoke tests (`TEST_STRATEGY.md` TC-15)."""

from __future__ import annotations

import contextlib
import socket
import sqlite3
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


def test_check_mode_exercises_and_releases_the_process_lock(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    assert dunder_main.main(["--check"]) == 0
    # The hardened lock uses a persistent diagnostic sentinel. Live ownership, not file
    # existence, is the invariant: a replacement acquisition proves --check released it.
    replacement = acquire_lock(workspace)
    replacement.close()
    assert lock_path_for(workspace).exists()


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


def test_check_mode_builds_the_snapshot_and_opens_the_database(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DASH-010: `--check` must exercise the two lazy subsystems `create_app` only wires up, not
    merely construct the app object — a broken repository read or an unwritable data directory
    should surface here, not on an operator's first click."""
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    exit_code = dunder_main.main(["--check"])
    assert exit_code == 0
    assert (workspace / "data" / "agentos_dashboard" / "dashboard.db").exists()
    assert dunder_main.main(["--check"]) == 0, "the initialized database must reopen cleanly"


def test_check_mode_reports_an_unwritable_data_directory_cleanly(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `--check` snapshot-build/DB-open smoke test must degrade to the same clean
    `configuration error` message every other startup failure uses, never an uncaught
    traceback, when the local database cannot be opened."""
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    (workspace / "data").mkdir()
    (workspace / "data" / "agentos_dashboard").write_text("not a directory", encoding="utf-8")

    exit_code = dunder_main.main(["--check"])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "configuration error" in err
    assert "Traceback" not in err


def test_check_mode_refuses_a_live_lock_conflict_without_opening_the_database(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    held = acquire_lock(workspace)
    try:
        exit_code = dunder_main.main(["--check"])
    finally:
        held.close()

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "configuration error" in err
    assert "already holds the lock" in err
    assert "Traceback" not in err
    assert not (workspace / "data" / "agentos_dashboard" / "dashboard.db").exists()


def test_check_mode_reports_an_incompatible_database_cleanly(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    db_path = workspace / "data" / "agentos_dashboard" / "dashboard.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 99")

    exit_code = dunder_main.main(["--check"])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "configuration error" in err
    assert "unsupported dashboard database user_version 99" in err
    assert "Traceback" not in err
    replacement = acquire_lock(workspace)
    replacement.close()


def test_check_mode_reports_a_malformed_database_without_a_traceback(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    db_path = workspace / "data" / "agentos_dashboard" / "dashboard.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"not a sqlite database")

    assert dunder_main.main(["--check"]) == 2
    err = capsys.readouterr().err
    assert "configuration error" in err
    assert "Traceback" not in err


def test_invalid_port_is_refused_with_a_clean_error(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWED_REPO_ROOT", str(workspace))
    monkeypatch.setenv("AWED_PORT", "not-a-port")
    exit_code = dunder_main.main(["--check"])
    assert exit_code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_check_mode_refuses_a_missing_repository_root_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing-repository"
    monkeypatch.setenv("AWED_REPO_ROOT", str(missing))

    assert dunder_main.main(["--check"]) == 2
    err = capsys.readouterr().err
    assert "configuration error" in err
    assert "Traceback" not in err
    assert not missing.exists()


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
    replacement = acquire_lock(workspace)
    replacement.close()
