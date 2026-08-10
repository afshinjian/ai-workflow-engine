"""`services.findings`: EN-15 draft `Finding` creation and idempotent replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.findings import (
    FindingSeverity,
    InvalidFindingPayload,
    create_finding,
    list_findings,
)
from agentos_dashboard.services.runs import create_run
from agentos_dashboard.storage.db import DashboardDatabase, IdempotencyConflict


def test_create_finding_persists_fields(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        finding = create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.BLOCKER,
            text="something is wrong",
            client_token="11111111-1111-4111-8111-111111111111",
            disposition="open",
        )
    assert finding.severity is FindingSeverity.BLOCKER
    assert finding.text == "something is wrong"
    assert finding.disposition == "open"


def test_finding_text_and_disposition_are_redacted_before_persistence(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    secret = "sk-cccccccccccccccccccccccc"
    with database.connection() as conn:
        finding = create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.MAJOR,
            text=f"failure used api_key={secret}",
            client_token="11111111-1111-4111-8111-111111111112",
            disposition="Authorization: Basic dXNlcjpwYXNz",
        )
        row = conn.execute(
            "SELECT text, disposition FROM findings WHERE uuid = ?", (finding.uuid,)
        ).fetchone()
    assert secret not in finding.text
    assert "dXNlcjpwYXNz" not in (finding.disposition or "")
    assert row["text"] == finding.text
    assert row["disposition"] == finding.disposition
    persisted = database.db_path.read_bytes() + database.audit_log_path.read_bytes()
    assert secret.encode() not in persisted
    assert b"dXNlcjpwYXNz" not in persisted


def test_create_finding_rejects_empty_text(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn, pytest.raises(InvalidFindingPayload):
        create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.MINOR,
            text="   ",
            client_token="22222222-2222-4222-8222-222222222222",
        )


def test_create_finding_idempotent_replay_returns_original(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    token = "33333333-3333-4333-8333-333333333333"
    with database.connection() as conn:
        first = create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.MAJOR,
            text="first",
            client_token=token,
        )
        second = create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.MAJOR,
            text="first",
            client_token=token,
        )
    assert first.uuid == second.uuid
    assert second.text == "first"
    with database.connection() as conn, pytest.raises(IdempotencyConflict):
        create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.OBSERVATION,
            text="different",
            client_token=token,
        )


def test_list_findings_filters_by_run(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        run_a = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="A",
            tool="t",
            started_at="2026-08-10T00:00:00+00:00",
            reported_result="r",
            client_token="66666666-6666-4666-8666-666666666661",
        )
        run_b = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="B",
            tool="t",
            started_at="2026-08-10T00:00:01+00:00",
            reported_result="r",
            client_token="66666666-6666-4666-8666-666666666662",
        )
        create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.MINOR,
            text="a",
            client_token="44444444-4444-4444-8444-444444444444",
            run_uuid=run_a.uuid,
        )
        create_finding(
            conn,
            database.audit_log_path,
            severity=FindingSeverity.MINOR,
            text="b",
            client_token="55555555-5555-4555-8555-555555555555",
            run_uuid=run_b.uuid,
        )
        only_a = list_findings(conn, run_uuid=run_a.uuid)
    assert [f.text for f in only_a] == ["a"]
