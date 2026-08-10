"""The coded DASH-001..010 stage schema (EN-10/EN-12), maintained independently of
`docs/agentos-dashboard/STAGE_REGISTRY.md` §3's own Markdown table.

`services.stages` parses the live registry table and cross-checks every row against this
schema; any disagreement (a title, role, or branch that drifted between the two) becomes a
finding rather than a silently-trusted value, exactly as `DASH-007.md`'s Build section requires
("cross-checked against a coded schema (divergence = finding)"). This module is data only: it
reads no file and calls nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["STAGE_SCHEMA", "STAGE_SCHEMA_BY_ID", "StageSchema"]


@dataclass(frozen=True)
class StageSchema:
    """One DASH stage's coded identity, independent of the registry document's own prose."""

    stage_id: str
    title: str
    role: str
    branch: str
    prompt_path: str
    report_path: str
    prerequisite: str | None


STAGE_SCHEMA: tuple[StageSchema, ...] = (
    StageSchema(
        stage_id="DASH-001",
        title="Planning foundation and dashboard contracts",
        role="Documentation & Governance session",
        branch="governance/dash-001-documentation",
        prompt_path="stage-prompts/DASH-001.md",
        report_path="docs/reports/agentos-dashboard/STAGE-01-completion.md",
        prerequisite=None,
    ),
    StageSchema(
        stage_id="DASH-002",
        title="Repository adapter and read-only snapshot",
        role="Dashboard implementation session",
        branch="feature/dash-002-repo-adapter",
        prompt_path="stage-prompts/DASH-002.md",
        report_path="docs/reports/agentos-dashboard/STAGE-02-completion.md",
        prerequisite="DASH-001",
    ),
    StageSchema(
        stage_id="DASH-003",
        title="Governance and Markdown parsing",
        role="Dashboard implementation session",
        branch="feature/dash-003-governance-parsing",
        prompt_path="stage-prompts/DASH-003.md",
        report_path="docs/reports/agentos-dashboard/STAGE-03-completion.md",
        prerequisite="DASH-002",
    ),
    StageSchema(
        stage_id="DASH-004",
        title="Local backend and dashboard shell",
        role="Dashboard implementation session",
        branch="feature/dash-004-dashboard-shell",
        prompt_path="stage-prompts/DASH-004.md",
        report_path="docs/reports/agentos-dashboard/STAGE-04-completion.md",
        prerequisite="DASH-003",
    ),
    StageSchema(
        stage_id="DASH-005",
        title="Workflow board and task detail",
        role="Dashboard implementation session",
        branch="feature/dash-005-board-task-detail",
        prompt_path="stage-prompts/DASH-005.md",
        report_path="docs/reports/agentos-dashboard/STAGE-05-completion.md",
        prerequisite="DASH-004",
    ),
    StageSchema(
        stage_id="DASH-006",
        title="Git, upstream, handover, consistency views",
        role="Dashboard implementation session",
        branch="feature/dash-006-git-handover-views",
        prompt_path="stage-prompts/DASH-006.md",
        report_path="docs/reports/agentos-dashboard/STAGE-06-completion.md",
        prerequisite="DASH-005",
    ),
    StageSchema(
        stage_id="DASH-007",
        title="Stage registry and prompt generation",
        role="Dashboard implementation session",
        branch="feature/dash-007-prompt-generation",
        prompt_path="stage-prompts/DASH-007.md",
        report_path="docs/reports/agentos-dashboard/STAGE-07-completion.md",
        prerequisite="DASH-006",
    ),
    StageSchema(
        stage_id="DASH-008",
        title="Run records, evidence, audit timeline",
        role="Dashboard implementation session",
        branch="feature/dash-008-runs-evidence-audit",
        prompt_path="stage-prompts/DASH-008.md",
        report_path="docs/reports/agentos-dashboard/STAGE-08-completion.md",
        prerequisite="DASH-007",
    ),
    StageSchema(
        stage_id="DASH-009",
        title="Security hardening and failure handling",
        role="Dashboard implementation session (+ mandatory independent security review)",
        branch="fix/dash-009-security-hardening",
        prompt_path="stage-prompts/DASH-009.md",
        report_path="docs/reports/agentos-dashboard/STAGE-09-completion.md",
        prerequisite="DASH-008",
    ),
    StageSchema(
        stage_id="DASH-010",
        title="Integration testing, documentation, release readiness",
        role="Dashboard implementation session",
        branch="feature/dash-010-release-readiness",
        prompt_path="stage-prompts/DASH-010.md",
        report_path="docs/reports/agentos-dashboard/STAGE-10-completion.md",
        prerequisite="DASH-009",
    ),
)

STAGE_SCHEMA_BY_ID: dict[str, StageSchema] = {stage.stage_id: stage for stage in STAGE_SCHEMA}
