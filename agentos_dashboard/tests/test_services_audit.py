"""`services.audit`: `record_audit_event`, `list_audit_events`, and the merged timeline
`build_audit_timeline` (`API_SPEC.md` EP-16; `PRODUCT_SPEC.md` DR-110/DR-111)."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.audit import (
    build_audit_timeline,
    inspect_audit_mirror,
    list_audit_events,
    record_audit_event,
)
from agentos_dashboard.services.notes import create_note
from agentos_dashboard.storage.db import (
    AuditMirrorWriteError,
    DashboardDatabase,
    DatabaseSchemaError,
)
from agentos_dashboard.tests.conftest import (
    event_digest,
    record_legacy_event,
    write_self_governance,
)


def test_record_audit_event_writes_row_and_jsonl_line(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        event = record_audit_event(
            conn, database.audit_log_path, kind="run_created", payload={"run_uuid": "u1"}
        )
    assert event.actor == "operator"
    assert event.kind == "run_created"
    lines = database.audit_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert event.uuid in lines[0]


def test_audit_payload_is_recursively_redacted_before_database_and_jsonl(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    secret = "sk-dddddddddddddddddddddddd"
    with database.connection() as conn:
        event = record_audit_event(
            conn,
            database.audit_log_path,
            kind="security_probe",
            payload={"nested": {"message": f"api_key={secret}"}, "items": ["token=gone"]},
            actor="Authorization: Basic dXNlcjpwYXNz",
        )
        row = conn.execute(
            "SELECT actor, payload FROM audit_events WHERE uuid = ?", (event.uuid,)
        ).fetchone()
    assert event.payload["nested"]["message"] == "api_key=[REDACTED]"
    assert row["actor"] == "Authorization: Basic [REDACTED]"
    persisted = database.db_path.read_bytes() + database.audit_log_path.read_bytes()
    assert secret.encode() not in persisted
    assert b"dXNlcjpwYXNz" not in persisted


def test_list_audit_events_filters_by_kind(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})
        record_audit_event(conn, database.audit_log_path, kind="note_created", payload={})
        only_notes = list_audit_events(conn, kind="note_created")
    assert len(only_notes) == 1
    assert only_notes[0].kind == "note_created"


def test_audit_query_and_timeline_apply_pagination_inside_the_database(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    root = RepositoryRoot.from_path(workspace)
    with database.connection() as conn:
        for index in range(205):
            record_audit_event(
                conn, database.audit_log_path, kind="bounded", payload={"index": index}
            )
    with database.connection() as conn:
        first_page = list_audit_events(conn, kind="bounded")
        final_page = list_audit_events(conn, kind="bounded", limit=10, offset=200)
        timeline_final = build_audit_timeline(root, conn, kind="bounded", limit=10, offset=200)
    assert len(first_page) == 200
    assert len(final_page) == 5
    assert len(timeline_final) == 5


def test_build_audit_timeline_without_task_id_returns_only_local_entries(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})
        entries = build_audit_timeline(root, conn)
    assert len(entries) == 1
    assert entries[0].origin == "local"


def test_build_audit_timeline_merges_repository_derived_events(
    workspace: Path, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    root = RepositoryRoot.from_path(workspace)
    e1 = record_legacy_event(
        project_id="proj",
        task_id="DASH-008",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    record_legacy_event(
        project_id="proj",
        task_id="DASH-008",
        stage="implementation",
        sequence=2,
        parent_digest=event_digest(e1),
        repository=str(workspace),
    )

    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})
        entries = build_audit_timeline(root, conn, task_id="DASH-008")

    origins = [entry.origin for entry in entries]
    assert origins.count("local") == 1
    repository_entries = [entry for entry in entries if entry.origin == "repository"]
    assert len(repository_entries) == 2
    # Newest sequence first.
    assert repository_entries[0].sequence == 2
    assert repository_entries[1].sequence == 1


def test_timeline_kind_filter_applies_to_repository_entries(
    workspace: Path, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    root = RepositoryRoot.from_path(workspace)
    record_legacy_event(
        project_id="proj",
        task_id="DASH-008",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})
        only_local = build_audit_timeline(root, conn, task_id="DASH-008", kind="run_created")
        only_repository = build_audit_timeline(
            root, conn, task_id="DASH-008", kind="workflow_event"
        )
    assert [entry.kind for entry in only_local] == ["run_created"]
    assert [entry.kind for entry in only_repository] == ["workflow_event"]


def test_timeline_kind_filter_applies_to_synthetic_mirror_divergence(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})
    database.audit_log_path.write_text("malformed\n", encoding="utf-8")
    with database.connection() as conn:
        only_runs = build_audit_timeline(
            root,
            conn,
            kind="run_created",
            audit_log_path=database.audit_log_path,
        )
        only_divergence = build_audit_timeline(
            root,
            conn,
            kind="audit_mirror_divergence",
            audit_log_path=database.audit_log_path,
        )
    assert [entry.kind for entry in only_runs] == ["run_created"]
    assert [entry.kind for entry in only_divergence] == ["audit_mirror_divergence"]


def test_build_audit_timeline_contradiction_flag_marks_reconciliation_divergence(
    workspace: Path,
) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        record_audit_event(
            conn, database.audit_log_path, kind="reconciliation_divergence", payload={}
        )
        entries = build_audit_timeline(root, conn)
    assert entries[0].contradiction is True


def test_mirror_failure_rolls_back_mutation_and_does_not_consume_token(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection():
        pass
    database.audit_log_path.parent.parent.mkdir(parents=True, exist_ok=True)
    database.audit_log_path.parent.write_text("blocks directory creation", encoding="utf-8")
    token = "90000000-0000-4000-8000-000000000001"

    with pytest.raises(AuditMirrorWriteError):
        with database.connection() as conn:
            create_note(
                conn,
                database.audit_log_path,
                target_ref="run:x",
                text="secret note",
                client_token=token,
            )
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_notes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0

    database.audit_log_path.parent.unlink()
    with database.connection() as conn:
        note = create_note(
            conn,
            database.audit_log_path,
            target_ref="run:x",
            text="secret note",
            client_token=token,
        )
    assert note.client_token == token
    assert "secret note" not in database.audit_log_path.read_text(encoding="utf-8")


def test_commit_failure_leaves_detectable_orphan_mirror_event(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with pytest.raises(sqlite3.IntegrityError):
        with database.connection() as conn:
            conn.execute("PRAGMA defer_foreign_keys = ON")
            conn.execute(
                "INSERT INTO approvals (uuid, client_token, request_hash, run_uuid, layer, "
                "verdict, reconciled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "90000000-0000-4000-8000-000000000002",
                    "90000000-0000-4000-8000-000000000003",
                    "h",
                    "90000000-0000-4000-8000-000000000004",
                    "human_approval",
                    "pending",
                    0,
                    "2026-08-10T00:00:00+00:00",
                ),
            )
            record_audit_event(conn, database.audit_log_path, kind="approval_created", payload={})

    with database.connection() as conn:
        status = inspect_audit_mirror(conn, database.audit_log_path)
        assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0
    assert status.coherent is False
    assert any("no committed database row" in issue for issue in status.issues)


def test_truncated_existing_line_is_preserved_and_detected(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection():
        pass
    database.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = b'{"uuid":"partial"'
    database.audit_log_path.write_bytes(prefix)
    with database.connection() as conn:
        event = record_audit_event(conn, database.audit_log_path, kind="run_created", payload={})
    raw = database.audit_log_path.read_bytes()
    assert raw.startswith(prefix + b"\n")
    assert event.uuid.encode() in raw
    with database.connection() as conn:
        status = inspect_audit_mirror(conn, database.audit_log_path)
    assert status.coherent is False
    assert any("malformed" in issue for issue in status.issues)


def test_duplicate_orphan_missing_and_malformed_mirror_records_are_all_reported(
    workspace: Path,
) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        first = record_audit_event(conn, database.audit_log_path, kind="first", payload={})
        second = record_audit_event(conn, database.audit_log_path, kind="second", payload={})
    first_line = database.audit_log_path.read_text(encoding="utf-8").splitlines()[0]
    database.audit_log_path.write_text(
        first_line
        + "\n"
        + first_line
        + "\n"
        + '{"uuid":"orphan","ts":"x","actor":"x","kind":"x","payload":{}}\n'
        + "malformed\n",
        encoding="utf-8",
    )
    with database.connection() as conn:
        status = inspect_audit_mirror(conn, database.audit_log_path)
    assert status.coherent is False
    assert any(first.uuid in issue and "duplicated" in issue for issue in status.issues)
    assert any(second.uuid in issue and "missing" in issue for issue in status.issues)
    assert any("orphan" in issue and "no committed" in issue for issue in status.issues)
    assert any("malformed" in issue for issue in status.issues)


def test_symlinked_mirror_is_refused_without_touching_target(
    workspace: Path, tmp_path: Path
) -> None:
    database = DashboardDatabase(workspace)
    database.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "outside.jsonl"
    target.write_text("preserved\n", encoding="utf-8")
    database.audit_log_path.symlink_to(target)
    with pytest.raises((DatabaseSchemaError, AuditMirrorWriteError)):
        with database.connection() as conn:
            record_audit_event(conn, database.audit_log_path, kind="probe", payload={})
    assert target.read_text(encoding="utf-8") == "preserved\n"


def test_concurrent_audit_appends_remain_complete_and_coherent(workspace: Path) -> None:
    database = DashboardDatabase(workspace)

    def write_event(index: int) -> None:
        with database.connection() as conn:
            record_audit_event(
                conn, database.audit_log_path, kind="concurrent", payload={"index": index}
            )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write_event, range(8)))
    with database.connection() as conn:
        status = inspect_audit_mirror(conn, database.audit_log_path)
    assert status.coherent is True
    assert status.database_events == 8
    assert status.mirror_events == 8


def test_audit_and_idempotency_survive_reopen(workspace: Path) -> None:
    first = DashboardDatabase(workspace)
    token = "90000000-0000-4000-8000-000000000005"
    with first.connection() as conn:
        note = create_note(
            conn,
            first.audit_log_path,
            target_ref="run:x",
            text="persisted",
            client_token=token,
        )
    reopened = DashboardDatabase(workspace)
    with reopened.connection() as conn:
        replay = create_note(
            conn,
            reopened.audit_log_path,
            target_ref="run:x",
            text="persisted",
            client_token=token,
        )
        status = inspect_audit_mirror(conn, reopened.audit_log_path)
    assert replay.uuid == note.uuid
    assert status.coherent is True
    assert status.database_events == 1
