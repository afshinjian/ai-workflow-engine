"""DASH-008 acceptance: "the append-only audit table has no UPDATE/DELETE code path"
(`DATA_MODEL.md` §4, SC-22) — both a source scan across every module that can reach
`audit_events`, and a behavioral proof that two recorded events never collide or overwrite each
other."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services import approvals, audit, findings, notes, runs
from agentos_dashboard.services.audit import list_audit_events, record_audit_event
from agentos_dashboard.services.runs import create_run
from agentos_dashboard.storage import db as storage_db
from agentos_dashboard.storage.db import DashboardDatabase

# Matches `UPDATE ... audit_events` or `DELETE FROM audit_events` (or `DELETE ... audit_events`)
# regardless of whitespace/newlines between the verb and the table name — the actual shape a SQL
# statement string would need for a mutation to reach this table.
_MUTATES_AUDIT_EVENTS_RE = re.compile(
    r"(UPDATE\s+audit_events|DELETE\s+FROM\s+audit_events)", re.IGNORECASE
)

_SCANNED_MODULES = (storage_db, audit, runs, approvals, findings, notes)


def test_no_module_reachable_from_the_api_contains_an_audit_events_mutation() -> None:
    for module in _SCANNED_MODULES:
        source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
        assert not _MUTATES_AUDIT_EVENTS_RE.search(
            source
        ), f"{module.__name__} contains an UPDATE/DELETE statement targeting audit_events"


def test_audit_event_recording_only_ever_inserts(tmp_path: Path) -> None:
    """Behavioral companion to the source scan: recording two events never changes the first."""
    database = DashboardDatabase(tmp_path)
    with database.connection() as conn:
        first = record_audit_event(
            conn, database.audit_log_path, kind="run_created", payload={"n": 1}
        )
        second = record_audit_event(
            conn, database.audit_log_path, kind="run_created", payload={"n": 2}
        )
        events = list_audit_events(conn)

    assert first.uuid != second.uuid
    by_uuid = {event.uuid: event for event in events}
    assert by_uuid[first.uuid].payload == {"n": 1}
    assert by_uuid[second.uuid].payload == {"n": 2}
    assert len(events) == 2


def test_audit_log_jsonl_mirror_is_append_only(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path)
    with database.connection() as conn:
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={"n": 1})
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={"n": 2})

    lines = database.audit_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_schema_rejects_direct_update_and_delete_of_audit_rows(tmp_path: Path) -> None:
    database = DashboardDatabase(tmp_path)
    with database.connection() as conn:
        event = record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})

    with database.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE audit_events SET kind = 'changed' WHERE uuid = ?", (event.uuid,))
    with database.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM audit_events WHERE uuid = ?", (event.uuid,))

    with database.connection() as conn:
        assert [row["kind"] for row in conn.execute("SELECT kind FROM audit_events")] == [
            "run_created"
        ]


def test_schema_rejects_direct_update_and_delete_of_run_records(tmp_path: Path) -> None:
    root = RepositoryRoot.from_path(tmp_path)
    database = DashboardDatabase(tmp_path)
    with database.connection() as conn:
        run = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="manual",
            started_at="2026-08-10T00:00:00+00:00",
            reported_result="recorded",
            client_token="90000000-0000-4000-8000-000000000011",
        )
    with database.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE stage_runs SET tool = 'changed' WHERE uuid = ?", (run.uuid,))
    with database.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM stage_runs WHERE uuid = ?", (run.uuid,))
