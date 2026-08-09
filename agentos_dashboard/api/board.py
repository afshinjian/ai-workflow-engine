"""EP-04/EP-05/EP-06 (`API_SPEC.md` §2): the board, task-detail, and workflow-machine JSON
views DASH-005 delivers.

**DASH-005 remediation (`OPEN_QUESTIONS.md` OD-D12, resolved):** every JSON view below keeps the
task queue's own `status` (Planned/Current/Done) and the Legacy engine's authoritative,
event-sourced `legacy_workflow` projection as two separate keys — never merged, never presented
as the same fact (`services.legacy_workflow`'s module docstring). `legacy_workflow` carries the
persisted events and the derived current/next/terminal state exactly as
`services.legacy_workflow.load_legacy_workflow` computed them; this module performs no further
derivation over it.
"""

from __future__ import annotations

from typing import Any

from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.orchestration import OrchestrationStage
from agentos_dashboard.services.board import BoardCard, UnclassifiedCard, build_board
from agentos_dashboard.services.consistency import ConsistencyFinding
from agentos_dashboard.services.legacy_workflow import (
    LegacyWorkflowEventView,
    LegacyWorkflowProjection,
)
from agentos_dashboard.services.tasks import TaskDetail
from agentos_dashboard.services.workflow import (
    TRANSITIONS,
    WORKFLOW_STAGES,
    is_verdict_stage,
    outcomes_for,
)

__all__ = ["board_to_json", "task_detail_to_json", "workflow_view_to_json"]


def _legacy_event_to_json(event: LegacyWorkflowEventView) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "stage": event.stage,
        "action": event.action,
        "verdict": event.verdict,
        "outcome": event.outcome,
        "resulting_stage": event.resulting_stage,
        "parent_digest": event.parent_digest,
        "prompt_id": event.prompt_id,
        "agent_run_id": event.agent_run_id,
        "head": event.head,
        "note": event.note,
    }


def _legacy_workflow_to_json(projection: LegacyWorkflowProjection) -> dict[str, Any]:
    """EN-07/EN-08 remediation: the authoritative per-task Legacy-workflow projection, read via
    `ai_workflow_engine.workflow.event_store` (`services.legacy_workflow`) -- never a second,
    dashboard-computed stage."""
    return {
        "project_id": projection.project_id,
        "available": projection.available,
        "error": projection.error,
        "has_history": projection.has_history,
        "current_stage": projection.current_stage,
        "next_stage": projection.next_stage,
        "terminal": projection.terminal,
        "latest_event": (
            _legacy_event_to_json(projection.latest_event)
            if projection.latest_event is not None
            else None
        ),
        "events": [_legacy_event_to_json(event) for event in projection.events],
    }


def _finding_to_json(finding: ConsistencyFinding) -> dict[str, Any]:
    return {
        "rule": finding.rule,
        "severity": finding.severity.value,
        "message": finding.message,
        "sources": list(finding.sources),
    }


def _card_to_json(card: BoardCard) -> dict[str, Any]:
    return {
        "task_id": card.task_id,
        "title": card.title,
        "program": card.program,
        "status": card.status.value,
        "referenced_tasks": list(card.referenced_tasks),
        "evidence": card.evidence.value,
        "evidence_notes": list(card.evidence_notes),
        "next_status": card.transition.next_status.value if card.transition.next_status else None,
        "transition_allowed": card.transition.allowed,
        "transition_reason": card.transition.reason,
        "legacy_workflow": _legacy_workflow_to_json(card.legacy_workflow),
        "source": card.source,
        "line": card.line,
    }


def _unclassified_to_json(card: UnclassifiedCard) -> dict[str, Any]:
    return {
        "task_id": card.task_id,
        "title": card.title,
        "raw_status": card.raw_status,
        "source": card.source,
        "line": card.line,
    }


def _orch_stage_to_json(stage: OrchestrationStage) -> dict[str, Any]:
    return {
        "stage_id": stage.stage_id,
        "title": stage.title,
        "status": stage.status,
        "prerequisites": list(stage.prerequisites),
        "blockers": list(stage.blockers),
        "evidence": list(stage.evidence),
    }


def board_to_json(
    snapshot: RepositorySnapshot,
    *,
    status: str | None = None,
    program: str | None = None,
) -> dict[str, Any]:
    """EP-04: board data with optional `status`/`program` filters (`API_SPEC.md` EP-04)."""
    board = build_board(snapshot)
    lanes: dict[str, tuple[BoardCard, ...]] = {
        "planned": board.planned,
        "current": board.current,
        "done": board.done,
    }
    if status is not None:
        key = status.strip().lower()
        lanes = {name: cards for name, cards in lanes.items() if name == key}
    if program is not None:
        wanted = program.strip().upper()
        lanes = {
            name: tuple(card for card in cards if card.program == wanted)
            for name, cards in lanes.items()
        }
    return {
        **{name: [_card_to_json(card) for card in cards] for name, cards in lanes.items()},
        "unclassified": [_unclassified_to_json(card) for card in board.unclassified],
        "orch_stages": [_orch_stage_to_json(stage) for stage in board.orch_stages],
        "workflow_stages": list(board.workflow_stages),
        "findings": [_finding_to_json(finding) for finding in board.findings],
    }


def task_detail_to_json(detail: TaskDetail) -> dict[str, Any]:
    """EP-05: task detail + record + history + provenance (`API_SPEC.md` EP-05)."""
    return {
        "task_id": detail.task_id,
        "title": detail.title,
        "status": detail.status.value,
        "program": detail.program,
        "source": detail.source,
        "line": detail.line,
        "raw_text": detail.raw_text,
        "referenced_tasks": list(detail.referenced_tasks),
        "acceptance_items": [
            {"text": item.text, "done": item.done} for item in detail.acceptance_items
        ],
        "validation_notes": list(detail.validation_notes),
        "rollback_notes": list(detail.rollback_notes),
        "documentation_notes": list(detail.documentation_notes),
        "doc_references": [
            {"path": ref.path, "exists": ref.exists} for ref in detail.doc_references
        ],
        "commit_references": [
            {
                "token": ref.token,
                "resolved_sha": ref.resolved_sha,
                "resolvable": ref.resolvable,
            }
            for ref in detail.commit_references
        ],
        "lifecycle_events": [
            {"kind": event.kind, "text": event.text} for event in detail.lifecycle_events
        ],
        "stage_contract": (
            {
                "path": detail.stage_contract.path,
                "allowed_text": detail.stage_contract.allowed_text,
            }
            if detail.stage_contract is not None
            else None
        ),
        "related_findings": [_finding_to_json(finding) for finding in detail.related_findings],
        "legacy_workflow": _legacy_workflow_to_json(detail.legacy_workflow),
    }


def workflow_view_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-06: the engine's reference workflow-stage diagram, per-task queue-status transitions,
    and (DASH-005 remediation) each task's authoritative Legacy-workflow projection
    (`API_SPEC.md` EP-06). `stages`/`transitions` remain the fixed, explanatory diagram
    (`services.workflow`); `tasks[].legacy_workflow` is the one per-task authoritative source,
    never derived from `stages`/`transitions` here."""
    board = build_board(snapshot)
    all_cards = board.planned + board.current + board.done
    return {
        "stages": [
            {
                "stage": stage,
                "verdict_stage": is_verdict_stage(stage),
                "outcomes": list(outcomes_for(stage)),
            }
            for stage in WORKFLOW_STAGES
        ],
        "transitions": [
            {"stage": t.stage, "outcome": t.outcome, "next_stage": t.next_stage}
            for t in TRANSITIONS
        ],
        "tasks": [
            {
                "task_id": card.task_id,
                "status": card.status.value,
                "next_status": (
                    card.transition.next_status.value if card.transition.next_status else None
                ),
                "allowed": card.transition.allowed,
                "reason": card.transition.reason,
                "legacy_workflow": _legacy_workflow_to_json(card.legacy_workflow),
            }
            for card in all_cards
        ],
    }
