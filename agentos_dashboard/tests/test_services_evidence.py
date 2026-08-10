"""`services.evidence`: the verified-vs-claimed gate-matrix aggregate (EP-17; DR-070/DR-071)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.evidence import build_evidence_view, list_evidence_views
from agentos_dashboard.services.runs import ValidationEntryInput, ValidationResult, create_run
from agentos_dashboard.storage.db import DashboardDatabase


def test_build_evidence_view_tallies_tri_state_results(workspace: Path) -> None:
    (workspace / "report.md").write_text("ok\n", encoding="utf-8")
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        run = create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="DASH-008",
            tool="claude",
            started_at="2026-08-10T00:00:00+00:00",
            reported_result="y",
            client_token="11111111-1111-4111-8111-111111111111",
            report_path="report.md",
            validation_entries=[
                ValidationEntryInput(
                    command="pytest", result=ValidationResult.PASS, origin="reported"
                ),
                ValidationEntryInput(
                    command="ruff", result=ValidationResult.FAIL, origin="reported"
                ),
                ValidationEntryInput(
                    command="mypy", result=ValidationResult.UNKNOWN, origin="reported"
                ),
                ValidationEntryInput(
                    command="black", result=ValidationResult.PASS, origin="reported"
                ),
            ],
        )
        view = build_evidence_view(root, conn, run.uuid)
    assert view is not None
    assert view.pass_count == 2
    assert view.fail_count == 1
    assert view.unknown_count == 1
    assert view.run.report_path_verified is True


def test_build_evidence_view_unknown_run_returns_none(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        assert build_evidence_view(root, conn, "does-not-exist") is None


def test_list_evidence_views_covers_every_run(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="A",
            tool="t",
            started_at="2026-08-10T00:00:00+00:00",
            reported_result="r",
            client_token="22222222-2222-4222-8222-222222222221",
        )
        create_run(
            root,
            conn,
            database.audit_log_path,
            stage_id="B",
            tool="t",
            started_at="2026-08-10T00:00:01+00:00",
            reported_result="r",
            client_token="22222222-2222-4222-8222-222222222222",
        )
        views = list_evidence_views(root, conn)
    assert {v.run.stage_id for v in views} == {"A", "B"}
