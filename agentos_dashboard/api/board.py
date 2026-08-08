"""EP-04/EP-05/EP-06 (`API_SPEC.md` §2): the board, task-detail, and workflow-machine JSON
views DASH-005 delivers."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.orchestration import OrchestrationStage
from agentos_dashboard.services.board import BoardCard, UnclassifiedCard, build_board
from agentos_dashboard.services.consistency import ConsistencyFinding
from agentos_dashboard.services.tasks import TaskDetail
from agentos_dashboard.services.workflow import (
    TRANSITIONS,
    WORKFLOW_STAGES,
    is_verdict_stage,
    outcomes_for,
)

__all__ = ["board_to_json", "task_detail_to_json", "workflow_view_to_json"]


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
    }


def workflow_view_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    """EP-06: the engine's coded workflow-stage machine plus per-task queue-status transitions
    (`API_SPEC.md` EP-06: "workflow-stage machine + per-task allowed/blocked transitions")."""
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
            }
            for card in all_cards
        ],
    }
