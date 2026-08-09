"""EN-07/EN-08 (`DATA_MODEL.md`): the engine's seven workflow stages and fixed transition table
as an explanatory, display-only reference diagram, plus the task queue's own three-status
lifecycle (Planned/Current/Done) and the sole-`Current` transition rule
`self-governance.yaml`'s `maximum_current_tasks` already enforces
(`services.consistency.DEFAULT_MAXIMUM_CURRENT_TASKS`).

**DASH-005 remediation (`OPEN_QUESTIONS.md` OD-D12, resolved):** `WORKFLOW_STAGES`,
`VERDICT_STAGES`, and `INITIAL_STAGE` are now re-exports of the engine's own
`ai_workflow_engine.prompt.models.WORKFLOW_STAGES`,
`ai_workflow_engine.workflow.events.VERDICT_STAGES`, and
`ai_workflow_engine.workflow.transitions.INITIAL_STAGE` -- not hand-copies -- and `TRANSITIONS`
is built from the engine's own transition table (`ai_workflow_engine.workflow.transitions`) at
import time. This module never reproduces transition rules; it reads the engine's one fixed
graph and adds only the explicit `push` terminal row that module leaves implicit as a special
case in `next_stage_after` ("if event.stage == 'push': return None"), so `TRANSITIONS` is
complete on its own rather than depending on an undocumented special case at every call site that
walks it.

**What this module is *not*:** a per-task stage computation. Which of the seven engine stages a
given task is "currently at" is never guessed from prose keywords here (`SOURCE_OF_TRUTH.md`
TR-04 forbids presenting a fabricated position as fact) -- it is read from the engine's own
persisted, event-sourced workflow state (`ai_workflow_engine.workflow.event_store`) by
`services.legacy_workflow.load_legacy_workflow`, the one authoritative source for a task's actual
Legacy-workflow position. `WORKFLOW_STAGES`/`TRANSITIONS` below remain a fixed reference diagram
of the engine's pipeline shape, rendered identically regardless of any task's real position --
useful as explanatory UI, never a substitute for `services.legacy_workflow`'s per-task output.
What *is* genuinely per-task and prose-derived here is the task-queue status transition below (a
distinct concept from the Legacy workflow stage -- see `services.legacy_workflow`'s module
docstring), and the free-text lifecycle history `services.tasks` extracts (DR-031).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.parsing.task_queue import TaskRecord
from agentos_dashboard.services.consistency import DEFAULT_MAXIMUM_CURRENT_TASKS
from ai_workflow_engine.prompt.models import WORKFLOW_STAGES as WORKFLOW_STAGES
from ai_workflow_engine.workflow.events import VERDICT_STAGES as VERDICT_STAGES
from ai_workflow_engine.workflow.transitions import _TRANSITIONS as _ENGINE_TRANSITIONS
from ai_workflow_engine.workflow.transitions import INITIAL_STAGE as INITIAL_STAGE

__all__ = [
    "INITIAL_STAGE",
    "TRANSITIONS",
    "VERDICT_STAGES",
    "WORKFLOW_STAGES",
    "QueueTransition",
    "StageTransition",
    "compute_queue_transitions",
    "is_verdict_stage",
    "outcomes_for",
]


@dataclass(frozen=True)
class StageTransition:
    """One `(stage, outcome) -> next_stage` edge of the engine's fixed transition table."""

    stage: str
    outcome: str
    next_stage: str | None


def _build_transitions() -> tuple[StageTransition, ...]:
    """`_ENGINE_TRANSITIONS` (the engine's own fixed graph) plus the explicit `push` terminal
    edge -- see the module docstring for why that edge is spelled out here."""
    edges = [
        StageTransition(stage, outcome, next_stage)
        for (stage, outcome), next_stage in _ENGINE_TRANSITIONS.items()
    ]
    edges.append(StageTransition("push", "completed", None))
    return tuple(edges)


TRANSITIONS: tuple[StageTransition, ...] = _build_transitions()


def is_verdict_stage(stage: str) -> bool:
    return stage in VERDICT_STAGES


def outcomes_for(stage: str) -> tuple[str, ...]:
    """The outcome tokens `stage` may be recorded with: two verdicts, or one `completed`."""
    return ("APPROVED", "REJECTED") if is_verdict_stage(stage) else ("completed",)


@dataclass(frozen=True)
class QueueTransition:
    """DR-021's "allowed/blocked next workflow transition, with reason" for one task-queue
    record -- the queue's own three-status lifecycle (Planned -> Current -> Done), never the
    engine's seven-stage machine above. Display-only (DR-023): the board renders this, it never
    acts on it.
    """

    task_id: str
    status: TaskStatus
    next_status: TaskStatus | None
    allowed: bool
    reason: str


def compute_queue_transitions(
    records: tuple[TaskRecord, ...],
    *,
    maximum_current_tasks: int = DEFAULT_MAXIMUM_CURRENT_TASKS,
) -> tuple[QueueTransition, ...]:
    """One `QueueTransition` per record.

    `Planned -> Current` is gated by the one invariant this package can observe without
    inventing one: the sole-`Current` rule (`self-governance.yaml` `maximum_current_tasks`).
    `Current -> Done` requires governance closeout and Human Owner approval this package cannot
    observe from the queue alone, so it is reported allowed-but-gated rather than guessed at a
    finer grain a board must never claim (DR-023: read-only, no mutation affordance).
    """
    current_ids = tuple(record.task_id for record in records if record.status is TaskStatus.CURRENT)
    transitions: list[QueueTransition] = []
    for record in records:
        if record.status is TaskStatus.PLANNED:
            at_capacity = len(current_ids) >= maximum_current_tasks
            if at_capacity:
                reason = (
                    f"blocked: {', '.join(current_ids)} already at the "
                    f"maximum_current_tasks limit ({maximum_current_tasks})"
                )
            else:
                reason = (
                    f"allowed: {len(current_ids)}/{maximum_current_tasks} "
                    "maximum_current_tasks in use"
                )
            transitions.append(
                QueueTransition(
                    task_id=record.task_id,
                    status=record.status,
                    next_status=TaskStatus.CURRENT,
                    allowed=not at_capacity,
                    reason=reason,
                )
            )
        elif record.status is TaskStatus.CURRENT:
            transitions.append(
                QueueTransition(
                    task_id=record.task_id,
                    status=record.status,
                    next_status=TaskStatus.DONE,
                    allowed=True,
                    reason=(
                        "allowed: requires governance closeout and Human Owner approval "
                        "(this board never mutates task state)"
                    ),
                )
            )
        else:
            transitions.append(
                QueueTransition(
                    task_id=record.task_id,
                    status=record.status,
                    next_status=None,
                    allowed=False,
                    reason="terminal: task is Done",
                )
            )
    return tuple(transitions)
