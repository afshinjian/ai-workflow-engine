"""Local SQLite persistence for DASH-008.

The database is disposable and non-authoritative, but it is still opened fail-closed: an
unsupported version or a partially-created version-1 schema is never silently overwritten or
treated as valid.  Audit mirror bytes are flushed before the SQLite transaction commits.  A
subsequent SQLite commit failure can therefore leave an orphan JSONL event, but never a committed
mutation with no durable mirror line; :mod:`agentos_dashboard.services.audit` detects and reports
that documented reconciliation state without modifying or truncating the mirror.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from agentos_dashboard.core import DashboardError

__all__ = [
    "AUDIT_LOG_FILENAME",
    "DATA_DIR_RELATIVE",
    "DB_FILENAME",
    "SCHEMA_SQL",
    "USER_VERSION",
    "AuditMirrorWriteError",
    "DashboardDatabase",
    "DatabaseSchemaError",
    "DatabaseVersionError",
    "IdempotencyConflict",
    "canonical_request_hash",
    "connect",
    "default_audit_log_path",
    "default_db_path",
    "queue_audit_line",
]

DATA_DIR_RELATIVE = ("data", "agentos_dashboard")
DB_FILENAME = "dashboard.db"
AUDIT_LOG_FILENAME = "audit.jsonl"
USER_VERSION = 1
BUSY_TIMEOUT_MS = 5_000


class DatabaseVersionError(DashboardError):
    """The database uses a version this stage has no authorized migration for."""


class DatabaseSchemaError(DashboardError):
    """The database is partial or does not match the exact version-1 schema."""


class AuditMirrorWriteError(DashboardError):
    """The JSONL mirror could not be durably appended before transaction commit."""


class IdempotencyConflict(DashboardError):
    """An idempotency UUID was reused with a different canonical request payload."""


_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS stage_runs (
        uuid TEXT PRIMARY KEY,
        client_token TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        prompt_hash TEXT,
        tool TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        reported_result TEXT NOT NULL,
        report_path TEXT,
        validation_summary TEXT,
        findings_text TEXT,
        notes TEXT,
        external_reference TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_runs (
        uuid TEXT PRIMARY KEY,
        run_uuid TEXT NOT NULL REFERENCES stage_runs(uuid),
        command TEXT NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('PASS', 'FAIL', 'UNKNOWN')),
        counts TEXT,
        origin TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        recorded_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generated_prompts (
        uuid TEXT PRIMARY KEY,
        stage_id TEXT NOT NULL,
        template_version TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        precondition_report TEXT,
        export_path TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approvals (
        uuid TEXT PRIMARY KEY,
        client_token TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL,
        run_uuid TEXT REFERENCES stage_runs(uuid),
        layer TEXT NOT NULL CHECK (
            layer IN ('implementation_review', 'independent_review', 'human_approval')
        ),
        verdict TEXT NOT NULL CHECK (verdict IN ('approved', 'rejected', 'pending')),
        target_hash TEXT,
        target_commit TEXT,
        target_commit_resolved INTEGER CHECK (target_commit_resolved IN (0, 1)),
        reconciled INTEGER NOT NULL DEFAULT 0 CHECK (reconciled IN (0, 1)),
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS findings (
        uuid TEXT PRIMARY KEY,
        client_token TEXT UNIQUE,
        request_hash TEXT,
        run_uuid TEXT REFERENCES stage_runs(uuid),
        severity TEXT NOT NULL CHECK (
            severity IN ('blocker', 'major', 'minor', 'observation')
        ),
        text TEXT NOT NULL,
        disposition TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_notes (
        uuid TEXT PRIMARY KEY,
        client_token TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL,
        target_ref TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consistency_history (
        uuid TEXT PRIMARY KEY,
        rule TEXT NOT NULL,
        severity TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        reconciled INTEGER NOT NULL DEFAULT 0 CHECK (reconciled IN (0, 1))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        uuid TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_events_no_update
    BEFORE UPDATE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
    BEFORE DELETE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END
    """,
)

_OTHER_IMMUTABLE_TABLES = (
    "stage_runs",
    "validation_runs",
    "generated_prompts",
    "approvals",
    "findings",
    "user_notes",
    "consistency_history",
)
_SCHEMA_STATEMENTS += tuple(
    f"""
    CREATE TRIGGER IF NOT EXISTS {table}_no_update
    BEFORE UPDATE ON {table}
    BEGIN
        SELECT RAISE(ABORT, '{table} is immutable');
    END
    """
    for table in _OTHER_IMMUTABLE_TABLES
)
_SCHEMA_STATEMENTS += tuple(
    f"""
    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
    BEFORE DELETE ON {table}
    BEGIN
        SELECT RAISE(ABORT, '{table} is immutable');
    END
    """
    for table in _OTHER_IMMUTABLE_TABLES
)

SCHEMA_SQL = ";\n".join(statement.strip() for statement in _SCHEMA_STATEMENTS) + ";\n"

_EXPECTED_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "stage_runs": (
        "uuid",
        "client_token",
        "request_hash",
        "stage_id",
        "prompt_hash",
        "tool",
        "started_at",
        "ended_at",
        "reported_result",
        "report_path",
        "validation_summary",
        "findings_text",
        "notes",
        "external_reference",
        "created_at",
    ),
    "validation_runs": (
        "uuid",
        "run_uuid",
        "command",
        "result",
        "counts",
        "origin",
        "ordinal",
        "recorded_at",
    ),
    "generated_prompts": (
        "uuid",
        "stage_id",
        "template_version",
        "sha256",
        "precondition_report",
        "export_path",
        "created_at",
    ),
    "approvals": (
        "uuid",
        "client_token",
        "request_hash",
        "run_uuid",
        "layer",
        "verdict",
        "target_hash",
        "target_commit",
        "target_commit_resolved",
        "reconciled",
        "notes",
        "created_at",
    ),
    "findings": (
        "uuid",
        "client_token",
        "request_hash",
        "run_uuid",
        "severity",
        "text",
        "disposition",
        "created_at",
    ),
    "user_notes": (
        "uuid",
        "client_token",
        "request_hash",
        "target_ref",
        "text",
        "created_at",
    ),
    "consistency_history": (
        "uuid",
        "rule",
        "severity",
        "first_seen_at",
        "last_seen_at",
        "reconciled",
    ),
    "audit_events": ("uuid", "ts", "actor", "kind", "payload"),
}
_EXPECTED_TRIGGERS = {
    "audit_events_no_update",
    "audit_events_no_delete",
    *(f"{table}_no_update" for table in _OTHER_IMMUTABLE_TABLES),
    *(f"{table}_no_delete" for table in _OTHER_IMMUTABLE_TABLES),
}


class _DashboardConnection(sqlite3.Connection):
    """Connection subtype carrying mirror lines until the surrounding transaction commits."""

    pending_audit_lines: list[tuple[Path, bytes]]


def default_db_path(repo_root: Path) -> Path:
    return repo_root.joinpath(*DATA_DIR_RELATIVE, DB_FILENAME)


def default_audit_log_path(repo_root: Path) -> Path:
    return repo_root.joinpath(*DATA_DIR_RELATIVE, "logs", AUDIT_LOG_FILENAME)


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    """Stable SHA-256 identity for conflict-safe idempotency comparisons."""
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _schema_objects(conn: sqlite3.Connection, object_type: str) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (object_type,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _normalize_schema_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


@lru_cache(maxsize=1)
def _expected_schema_signatures() -> Mapping[tuple[str, str], str]:
    reference = sqlite3.connect(":memory:")
    try:
        for statement in _SCHEMA_STATEMENTS:
            reference.execute(statement)
        rows = reference.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {(str(row[0]), str(row[1])): _normalize_schema_sql(str(row[2])) for row in rows}
    finally:
        reference.close()


def _validate_schema(conn: sqlite3.Connection) -> None:
    tables = _schema_objects(conn, "table")
    if tables != set(_EXPECTED_COLUMNS):
        raise DatabaseSchemaError(
            f"version-1 table set mismatch: expected {sorted(_EXPECTED_COLUMNS)}, "
            f"found {sorted(tables)}"
        )
    for table, expected in _EXPECTED_COLUMNS.items():
        columns = tuple(str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})"))
        if columns != expected:
            raise DatabaseSchemaError(
                f"version-1 columns for {table!r} do not match the authorized schema"
            )
    triggers = _schema_objects(conn, "trigger")
    if triggers != _EXPECTED_TRIGGERS:
        raise DatabaseSchemaError(
            f"version-1 audit trigger set mismatch: expected {sorted(_EXPECTED_TRIGGERS)}, "
            f"found {sorted(triggers)}"
        )
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'trigger') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual_signatures = {
        (str(row["type"]), str(row["name"])): _normalize_schema_sql(str(row["sql"])) for row in rows
    }
    if actual_signatures != _expected_schema_signatures():
        raise DatabaseSchemaError("version-1 schema SQL differs from the authorized definition")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open one connection, creating only a genuinely empty version-0 database.

    Version 1 is validated exactly.  Any other version, or a version-0 file containing user
    objects (the observable shape of interrupted/partial initialization), fails closed.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        timeout=BUSY_TIMEOUT_MS / 1000,
        factory=_DashboardConnection,
    )
    conn.row_factory = sqlite3.Row
    typed_conn = conn
    assert isinstance(typed_conn, _DashboardConnection)
    typed_conn.pending_audit_lines = []
    try:
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, USER_VERSION):
            raise DatabaseVersionError(
                f"unsupported dashboard database user_version {version}; expected {USER_VERSION}"
            )

        tables = _schema_objects(conn, "table")
        triggers = _schema_objects(conn, "trigger")
        if version == 0:
            if tables or triggers:
                raise DatabaseSchemaError(
                    "version-0 database contains schema objects; refusing partial initialization"
                )
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA_STATEMENTS:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {USER_VERSION}")
                _validate_schema(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        else:
            _validate_schema(conn)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")

        if int(conn.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
            raise DatabaseSchemaError("SQLite foreign-key enforcement could not be enabled")
        return conn
    except BaseException:
        conn.close()
        raise


def queue_audit_line(conn: sqlite3.Connection, audit_log_path: Path, line: bytes) -> None:
    """Queue one complete UTF-8 JSONL record for the transaction's pre-commit flush."""
    if not isinstance(conn, _DashboardConnection):
        raise AuditMirrorWriteError("audit events require a DashboardDatabase connection")
    if b"\n" in line or b"\r" in line:
        raise AuditMirrorWriteError("audit JSONL records must be one stable line")
    conn.pending_audit_lines.append((audit_log_path, line))


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("audit mirror append made no progress")
        view = view[written:]


def _append_audit_lines(path: Path, lines: list[bytes]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            # Preserve a truncated final record as detectable evidence and delimit the next valid
            # record.  Never seek backwards to overwrite, truncate, or repair prior bytes.
            size = os.fstat(fd).st_size
            if size:
                read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                read_flags |= getattr(os, "O_NOFOLLOW", 0)
                read_fd = os.open(path, read_flags)
                try:
                    os.lseek(read_fd, -1, os.SEEK_END)
                    final_byte = os.read(read_fd, 1)
                finally:
                    os.close(read_fd)
                if final_byte != b"\n":
                    _write_all(fd, b"\n")
            for line in lines:
                _write_all(fd, line + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise AuditMirrorWriteError("unable to durably append the local audit mirror") from exc


class DashboardDatabase:
    """Repository-confined database/mirror paths and fresh per-use connections."""

    def __init__(
        self, repo_root: Path, *, db_path: Path | None = None, audit_log_path: Path | None = None
    ) -> None:
        self.repo_root = repo_root.resolve(strict=True)
        requested_db = db_path if db_path is not None else default_db_path(self.repo_root)
        requested_log = (
            audit_log_path if audit_log_path is not None else default_audit_log_path(self.repo_root)
        )
        self.db_path = self._confined(requested_db)
        self.audit_log_path = self._confined(requested_log)

    def _confined(self, path: Path) -> Path:
        candidate = path if path.is_absolute() else self.repo_root / path
        lexical = Path(os.path.abspath(candidate))
        if not lexical.is_relative_to(self.repo_root):
            raise DatabaseSchemaError("dashboard runtime path is outside the repository")
        current = self.repo_root
        for component in lexical.relative_to(self.repo_root).parts:
            current /= component
            if current.is_symlink():
                raise DatabaseSchemaError("dashboard runtime path contains a symlink")
        resolved = lexical.resolve(strict=False)
        if not resolved.is_relative_to(self.repo_root):
            raise DatabaseSchemaError("dashboard runtime path resolves outside the repository")
        return lexical

    def _revalidate_paths(self) -> None:
        # Recheck on every use so a post-construction parent symlink replacement fails safely.
        for path in (self.db_path, self.audit_log_path):
            current = self.repo_root
            contains_symlink = False
            for component in path.relative_to(self.repo_root).parts:
                current /= component
                if current.is_symlink():
                    contains_symlink = True
                    break
            if contains_symlink or not path.resolve(strict=False).is_relative_to(self.repo_root):
                raise DatabaseSchemaError("dashboard runtime path is no longer repository-confined")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Commit mutation + audit as one outcome under the documented mirror reconciliation.

        Mirror records are appended and fsynced before SQLite commit.  Mirror failure rolls the
        database transaction back.  A later SQLite commit failure can leave only an orphan mirror
        record; mirror inspection reports it and no successful API response is returned.
        """
        self._revalidate_paths()
        conn = connect(self.db_path)
        assert isinstance(conn, _DashboardConnection)
        try:
            yield conn
            grouped: dict[Path, list[bytes]] = {}
            for path, line in conn.pending_audit_lines:
                grouped.setdefault(path, []).append(line)
            self._revalidate_paths()
            for path, lines in grouped.items():
                if path != self.audit_log_path:
                    raise AuditMirrorWriteError("audit event targeted an unexpected mirror path")
                _append_audit_lines(path, lines)
            conn.commit()
            conn.pending_audit_lines.clear()
        except BaseException:
            conn.rollback()
            conn.pending_audit_lines.clear()
            raise
        finally:
            conn.close()
