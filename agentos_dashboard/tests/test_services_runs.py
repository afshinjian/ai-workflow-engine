"""`services.runs`: EN-11 `StageRun` creation, idempotent replay, and the live report-path
verification split (DR-050/DR-051)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.runs import (
    ValidationEntryInput,
    ValidationResult,
    create_run,
    get_run,
    list_runs,
    to_view,
)
from agentos_dashboard.storage.db import DashboardDatabase, IdempotencyConflict

_START = "2026-08-10T00:00:00+00:00"


def _root(workspace: Path) -> RepositoryRoot:
    return RepositoryRoot.from_path(workspace)


def test_create_run_persists_all_dr050_fields(workspace: Path) -> None:
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        view = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at="2026-08-10T00:00:00+00:00",
            reported_result="COMPLETED",
            client_token="11111111-1111-4111-8111-111111111111",
            prompt_hash="d" * 64,
            report_path="README.md",
            validation_entries=[
                ValidationEntryInput(
                    command="pytest", result=ValidationResult.PASS, origin="reported"
                )
            ],
            validation_summary="all green",
            findings_text="none",
            notes="a note",
            external_reference="PR #1",
        )
    assert view.stage_id == "DASH-008"
    assert view.tool == "claude"
    assert view.prompt_hash == "d" * 64
    assert view.report_path == "README.md"
    assert view.validation_summary == "all green"
    assert view.findings_text == "none"
    assert view.notes == "a note"
    assert view.external_reference == "PR #1"
    assert len(view.validation_entries) == 1
    assert view.validation_entries[0].result is ValidationResult.PASS


def test_create_run_redacts_secret_shaped_free_text_fields(workspace: Path) -> None:
    """SC-09: pasted credentials in any operator-authored free-text field must not persist in
    `dashboard.db` or survive into the returned view."""
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        view = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-009",
            tool="claude",
            started_at=_START,
            reported_result="COMPLETED",
            client_token="11111111-1111-4111-8111-111111111119",
            validation_entries=[
                ValidationEntryInput(
                    command="curl -H 'Authorization: Bearer abcDEF012345secretpart'",
                    result=ValidationResult.PASS,
                    origin="token=zzzz9999yyyy8888",
                )
            ],
            validation_summary="api_key=abcd1234efgh5678wxyz all green",
            findings_text="password=hunter2-not-a-real-password",
            notes="token=zzzz9999yyyy8888needle",
            external_reference="secret=abcd1234efgh5678wxyz",
        )
    for field in (
        view.validation_summary,
        view.findings_text,
        view.notes,
        view.external_reference,
        view.validation_entries[0].command,
        view.validation_entries[0].origin,
    ):
        assert field is not None
        assert "abcd1234efgh5678wxyz" not in field
        assert "zzzz9999yyyy8888" not in field
        assert "hunter2-not-a-real-password" not in field
        assert "abcDEF012345secretpart" not in field

    with database.connection() as conn:
        row = conn.execute(
            "SELECT notes, findings_text, validation_summary, external_reference "
            "FROM stage_runs WHERE uuid = ?",
            (view.uuid,),
        ).fetchone()
    for value in row:
        assert "abcd1234efgh5678wxyz" not in value
        assert "zzzz9999yyyy8888" not in value


def test_report_path_verified_true_for_existing_file(workspace: Path) -> None:
    (workspace / "README.md").write_text("hello\n", encoding="utf-8")
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        view = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="y",
            client_token="22222222-2222-4222-8222-222222222222",
            report_path="README.md",
        )
    assert view.report_path_verified is True
    assert view.report_sha256 == hashlib.sha256(b"hello\n").hexdigest()
    assert view.report_hash_verified is True


def test_report_path_verified_false_for_missing_file(workspace: Path) -> None:
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        view = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="y",
            client_token="33333333-3333-4333-8333-333333333333",
            report_path="docs/reports/does-not-exist.md",
        )
    assert view.report_path_verified is False


def test_report_path_verified_none_when_no_path_recorded(workspace: Path) -> None:
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        view = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="y",
            client_token="44444444-4444-4444-8444-444444444444",
        )
    assert view.report_path_verified is None


def test_report_path_verified_is_recomputed_live_not_cached(workspace: Path) -> None:
    """DR-051: the verified flag reflects the repository's *current* state, not a snapshot
    frozen at creation time."""
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        view = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="y",
            client_token="55555555-5555-4555-8555-555555555555",
            report_path="report.md",
        )
    assert view.report_path_verified is False

    (workspace / "report.md").write_text("now it exists\n", encoding="utf-8")
    with database.connection() as conn:
        run = get_run(conn, view.uuid)
        assert run is not None
        refreshed = to_view(root, run)
    assert refreshed.report_path_verified is True


def test_create_run_idempotent_replay_returns_original(workspace: Path) -> None:
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    token = "66666666-6666-4666-8666-666666666666"
    with database.connection() as conn:
        first = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="first",
            client_token=token,
        )
        replay = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="first",
            client_token=token,
        )
        assert replay.uuid == first.uuid
        with pytest.raises(IdempotencyConflict):
            create_run(
                root,
                conn,
                database.audit_log_path,
                stage_id="DASH-999",
                tool="codex",
                started_at=_START,
                reported_result="different",
                client_token=token,
            )
    with database.connection() as conn:
        assert len(list_runs(conn)) == 1


def test_list_runs_orders_newest_first(workspace: Path) -> None:
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="A",
            tool="t",
            started_at=_START,
            reported_result="r",
            client_token="77777777-7777-4777-8777-777777777771",
        )
        create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="B",
            tool="t",
            started_at="2026-08-10T00:00:01+00:00",
            reported_result="r",
            client_token="77777777-7777-4777-8777-777777777772",
        )
        runs = list_runs(conn)
    assert [r.stage_id for r in runs] == ["B", "A"]


def test_report_path_traversal_and_symlink_escape_are_unverified(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret\n", encoding="utf-8")
    (workspace / "escape.md").symlink_to(outside)
    root = _root(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        traversal = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="recorded",
            client_token="88888888-8888-4888-8888-888888888881",
            report_path="../outside.md",
        )
        symlink = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at=_START,
            reported_result="recorded",
            client_token="88888888-8888-4888-8888-888888888882",
            report_path="escape.md",
        )
    assert traversal.report_path_verified is False
    assert symlink.report_path_verified is False
    assert traversal.report_sha256 is None
    assert symlink.report_sha256 is None
