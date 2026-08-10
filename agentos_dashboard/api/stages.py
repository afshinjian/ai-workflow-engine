"""EP-13 (`API_SPEC.md` §2): the stage registry plus live precondition state for every coded
DASH stage (PG-04)."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA
from agentos_dashboard.services.consistency import ConsistencyFinding
from agentos_dashboard.services.stages import (
    PreconditionReport,
    build_stage_registry_view,
    evaluate_preconditions,
)

__all__ = ["precondition_report_to_json", "stage_registry_to_json"]


def _finding_to_json(finding: ConsistencyFinding) -> dict[str, Any]:
    return {
        "rule": finding.rule,
        "severity": finding.severity.value,
        "message": finding.message,
        "sources": list(finding.sources),
    }


def precondition_report_to_json(report: PreconditionReport) -> dict[str, Any]:
    return {
        "stage_id": report.stage_id,
        "all_passed": report.all_passed,
        "results": [
            {"name": result.name, "passed": result.passed, "detail": result.detail}
            for result in report.results
        ],
    }


def stage_registry_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-13 `GET /stages`: the coded schema, cross-checked against the live registry, with a
    live precondition report attached to every stage (DR-041's precondition panel)."""
    view = build_stage_registry_view(snapshot.root)
    row_by_id = {row.stage_id: row for row in view.rows}

    stages: list[dict[str, Any]] = []
    for schema in STAGE_SCHEMA:
        row = row_by_id.get(schema.stage_id)
        report = evaluate_preconditions(snapshot, schema.stage_id)
        stages.append(
            {
                "stage_id": schema.stage_id,
                "title": schema.title,
                "role": schema.role,
                "branch": schema.branch,
                "report_path": schema.report_path,
                "prerequisite": schema.prerequisite,
                "registry_state": row.state if row is not None else None,
                "precondition_report": (
                    precondition_report_to_json(report) if report is not None else None
                ),
            }
        )
    return {"stages": stages, "findings": [_finding_to_json(f) for f in view.findings]}
