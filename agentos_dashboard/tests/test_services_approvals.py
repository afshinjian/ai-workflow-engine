"""`services.approvals`: EN-14 draft `Approval` creation, idempotent replay, and DR-061's
reconciliation-divergence finding."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_dashboard.core.gitread import GitFailure, GitReadError
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.approvals import (
    ApprovalLayer,
    ApprovalVerdict,
    InvalidApprovalPayload,
    ReconciliationUnavailable,
    create_approval,
)
from agentos_dashboard.services.audit import list_audit_events
from agentos_dashboard.services.findings import list_findings
from agentos_dashboard.storage.db import DashboardDatabase, IdempotencyConflict


def test_create_approval_without_target_commit_is_unreconciled_with_no_finding(
    workspace: Path,
) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        approval = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.HUMAN_APPROVAL,
            verdict=ApprovalVerdict.APPROVED,
            client_token="11111111-1111-4111-8111-111111111111",
        )
        findings = list_findings(conn)
    assert approval.reconciled is False
    assert approval.target_commit_resolved is None
    assert findings == ()


def test_create_approval_with_resolvable_commit_is_reconciled(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    database = DashboardDatabase(git_repo)
    with database.connection() as conn:
        approval = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.IMPLEMENTATION_REVIEW,
            verdict=ApprovalVerdict.APPROVED,
            client_token="22222222-2222-4222-8222-222222222222",
            target_commit="HEAD",
        )
        findings = list_findings(conn)
    assert approval.reconciled is False
    assert approval.target_commit_resolved is True
    assert findings == ()


def test_create_approval_with_unresolvable_commit_raises_finding_and_audit_event(
    git_repo: Path,
) -> None:
    root = RepositoryRoot.from_path(git_repo)
    database = DashboardDatabase(git_repo)
    with database.connection() as conn:
        approval = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.INDEPENDENT_REVIEW,
            verdict=ApprovalVerdict.REJECTED,
            client_token="33333333-3333-4333-8333-333333333333",
            target_commit="0000000000000000000000000000000000dead",
        )
        findings = list_findings(conn)
        events = list_audit_events(conn, kind="reconciliation_divergence")
    assert approval.reconciled is False
    assert approval.target_commit_resolved is False
    assert len(findings) == 1
    assert findings[0].severity.value == "major"
    assert approval.uuid in findings[0].text
    assert len(events) == 1
    assert events[0].payload["approval_uuid"] == approval.uuid


def test_create_approval_idempotent_replay_returns_original(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    database = DashboardDatabase(git_repo)
    token = "44444444-4444-4444-8444-444444444444"
    with database.connection() as conn:
        first = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.HUMAN_APPROVAL,
            verdict=ApprovalVerdict.APPROVED,
            client_token=token,
            notes="first",
        )
        second = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.HUMAN_APPROVAL,
            verdict=ApprovalVerdict.APPROVED,
            client_token=token,
            notes="first",
        )
    assert first.uuid == second.uuid
    assert second.notes == "first"
    assert second.verdict is ApprovalVerdict.APPROVED

    with database.connection() as conn, pytest.raises(IdempotencyConflict):
        create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.HUMAN_APPROVAL,
            verdict=ApprovalVerdict.REJECTED,
            client_token=token,
            notes="different",
        )


def test_approval_notes_are_redacted_before_hash_database_and_audit(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    token = "44444444-4444-4444-8444-444444444445"
    secret_a = "sk-aaaaaaaaaaaaaaaaaaaaaaaa"
    secret_b = "sk-bbbbbbbbbbbbbbbbbbbbbbbb"
    with database.connection() as conn:
        first = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.HUMAN_APPROVAL,
            verdict=ApprovalVerdict.APPROVED,
            client_token=token,
            notes=f"Authorization: Bearer {secret_a}",
        )
        replay = create_approval(
            root,
            conn,
            database.audit_log_path,
            layer=ApprovalLayer.HUMAN_APPROVAL,
            verdict=ApprovalVerdict.APPROVED,
            client_token=token,
            notes=f"Authorization: Bearer {secret_b}",
        )
        row = conn.execute(
            "SELECT notes, request_hash FROM approvals WHERE uuid = ?", (first.uuid,)
        ).fetchone()
    assert first.uuid == replay.uuid
    assert first.notes == "Authorization: Bearer [REDACTED]"
    assert row["notes"] == first.notes
    assert secret_a not in str(row["request_hash"])
    persisted = database.db_path.read_bytes() + database.audit_log_path.read_bytes()
    assert secret_a.encode() not in persisted
    assert secret_b.encode() not in persisted


def test_transient_git_failure_creates_no_approval_finding_or_audit(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = RepositoryRoot.from_path(git_repo)
    database = DashboardDatabase(git_repo)

    def _timeout(*args: object, **kwargs: object) -> str:
        raise GitReadError(GitFailure.TIMEOUT, "injected")

    monkeypatch.setattr("agentos_dashboard.services.approvals.resolve_revision", _timeout)
    with pytest.raises(ReconciliationUnavailable):
        with database.connection() as conn:
            create_approval(
                root,
                conn,
                database.audit_log_path,
                layer=ApprovalLayer.HUMAN_APPROVAL,
                verdict=ApprovalVerdict.PENDING,
                client_token="90000000-0000-4000-8000-000000000021",
                target_commit="HEAD",
            )
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


def test_abnormal_git_command_failure_is_not_mistaken_for_unknown_revision(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = RepositoryRoot.from_path(git_repo)
    database = DashboardDatabase(git_repo)

    def _abnormal_failure(*args: object, **kwargs: object) -> str:
        raise GitReadError(GitFailure.COMMAND_FAILED, "git rev-parse exited 128: I/O failure")

    monkeypatch.setattr("agentos_dashboard.services.approvals.resolve_revision", _abnormal_failure)
    with pytest.raises(ReconciliationUnavailable):
        with database.connection() as conn:
            create_approval(
                root,
                conn,
                database.audit_log_path,
                layer=ApprovalLayer.HUMAN_APPROVAL,
                verdict=ApprovalVerdict.PENDING,
                client_token="90000000-0000-4000-8000-000000000023",
                target_commit="HEAD",
            )
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


def test_malformed_revision_fails_before_any_write(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    database = DashboardDatabase(git_repo)
    with pytest.raises(InvalidApprovalPayload):
        with database.connection() as conn:
            create_approval(
                root,
                conn,
                database.audit_log_path,
                layer=ApprovalLayer.HUMAN_APPROVAL,
                verdict=ApprovalVerdict.PENDING,
                client_token="90000000-0000-4000-8000-000000000022",
                target_commit="--help",
            )
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
