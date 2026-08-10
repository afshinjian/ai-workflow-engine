"""`storage.db`: schema creation, `PRAGMA` settings, deletion-safety, and the append-only
source-scan proof for `audit_events` (`DATA_MODEL.md` §3/§4; DASH-008 acceptance)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentos_dashboard.storage import db as storage_db

_EXPECTED_TABLES = {
    "stage_runs",
    "validation_runs",
    "generated_prompts",
    "approvals",
    "findings",
    "user_notes",
    "consistency_history",
    "audit_events",
}


def test_connect_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "data" / "agentos_dashboard" / "dashboard.db"
    assert not db_path.parent.exists()
    conn = storage_db.connect(db_path)
    try:
        assert db_path.exists()
    finally:
        conn.close()


def test_connect_creates_every_table(tmp_path: Path) -> None:
    conn = storage_db.connect(tmp_path / "dashboard.db")
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        names = {row["name"] for row in rows}
        assert _EXPECTED_TABLES.issubset(names)
    finally:
        conn.close()


def test_connect_sets_user_version_and_foreign_keys(tmp_path: Path) -> None:
    conn = storage_db.connect(tmp_path / "dashboard.db")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == storage_db.USER_VERSION
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_connect_is_idempotent_after_manual_deletion(tmp_path: Path) -> None:
    db_path = tmp_path / "dashboard.db"
    first = storage_db.connect(db_path)
    first.execute(
        "INSERT INTO stage_runs (uuid, client_token, request_hash, stage_id, tool, started_at, "
        "reported_result, created_at) VALUES "
        "('u1', 't1', 'h1', 'DASH-008', 'claude', 'x', 'y', 'z')"
    )
    first.commit()
    first.close()

    db_path.unlink()
    assert not db_path.exists()

    second = storage_db.connect(db_path)
    try:
        rows = second.execute("SELECT * FROM stage_runs").fetchall()
        assert rows == []  # recreated empty, not an error
    finally:
        second.close()


def test_default_paths_are_under_data_agentos_dashboard(tmp_path: Path) -> None:
    db_path = storage_db.default_db_path(tmp_path)
    log_path = storage_db.default_audit_log_path(tmp_path)
    assert db_path == tmp_path / "data" / "agentos_dashboard" / "dashboard.db"
    assert log_path == tmp_path / "data" / "agentos_dashboard" / "logs" / "audit.jsonl"


def test_dashboard_database_connection_commits_on_success(tmp_path: Path) -> None:
    database = storage_db.DashboardDatabase(tmp_path)
    with database.connection() as conn:
        conn.execute(
            "INSERT INTO user_notes "
            "(uuid, client_token, request_hash, target_ref, text, created_at) "
            "VALUES ('n1', 'tok1', 'h1', 'run:x', 'hello', 'z')"
        )
    with database.connection() as conn:
        rows = conn.execute("SELECT text FROM user_notes WHERE uuid = 'n1'").fetchall()
    assert rows[0]["text"] == "hello"


def test_dashboard_database_connection_rolls_back_on_exception(tmp_path: Path) -> None:
    database = storage_db.DashboardDatabase(tmp_path)
    try:
        with database.connection() as conn:
            conn.execute(
                "INSERT INTO user_notes "
                "(uuid, client_token, request_hash, target_ref, text, created_at) "
                "VALUES ('n2', 'tok2', 'h2', 'run:x', 'hello', 'z')"
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with database.connection() as conn:
        rows = conn.execute("SELECT text FROM user_notes WHERE uuid = 'n2'").fetchall()
    assert rows == []


def test_dashboard_database_survives_manual_file_deletion(tmp_path: Path) -> None:
    database = storage_db.DashboardDatabase(tmp_path)
    with database.connection() as conn:
        conn.execute(
            "INSERT INTO user_notes "
            "(uuid, client_token, request_hash, target_ref, text, created_at) "
            "VALUES ('n3', 'tok3', 'h3', 'run:x', 'hello', 'z')"
        )
    database.db_path.unlink()
    with database.connection() as conn:
        rows = conn.execute("SELECT * FROM user_notes").fetchall()
    assert rows == []


def test_sqlite_connection_type_is_stdlib(tmp_path: Path) -> None:
    """Stdlib `sqlite3` only, per `DATA_MODEL.md` §3 ("Stdlib `sqlite3`; ... no Alembic")."""
    conn = storage_db.connect(tmp_path / "dashboard.db")
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_unsupported_user_version_fails_closed_without_overwrite(tmp_path: Path) -> None:
    db_path = tmp_path / "dashboard.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 99")
    conn.execute("CREATE TABLE preserved (value TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(storage_db.DatabaseVersionError):
        storage_db.connect(db_path)

    check = sqlite3.connect(db_path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 99
        assert check.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='preserved'"
        ).fetchone() == ("preserved",)
    finally:
        check.close()


def test_partial_version_zero_and_partial_version_one_fail_closed(tmp_path: Path) -> None:
    for version in (0, 1):
        db_path = tmp_path / f"partial-{version}.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE stage_runs (uuid TEXT PRIMARY KEY)")
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
        conn.close()
        with pytest.raises(storage_db.DatabaseSchemaError):
            storage_db.connect(db_path)


def test_every_reopened_connection_enforces_foreign_keys_and_wal(tmp_path: Path) -> None:
    database = storage_db.DashboardDatabase(tmp_path)
    for _ in range(2):
        with database.connection() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_runtime_parent_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "data").symlink_to(outside, target_is_directory=True)
    with pytest.raises(storage_db.DatabaseSchemaError):
        storage_db.DashboardDatabase(repo)
