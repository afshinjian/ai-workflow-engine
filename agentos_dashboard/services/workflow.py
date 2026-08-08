"""EN-07/EN-08 (`DATA_MODEL.md`): a coded, display-only mirror of the engine's seven workflow
stages and fixed transition table (`DASH-005.md`: "a per-task workflow-stage strip driven by a
coded mirror of the engine's seven workflow stages and fixed transition table (display-only)"),
plus the task queue's own three-status lifecycle (Planned/Current/Done) and the sole-`Current`
transition rule `self-governance.yaml`'s `maximum_current_tasks` already enforces
(`services.consistency.DEFAULT_MAXIMUM_CURRENT_TASKS`).

`WORKFLOW_STAGES`/`VERDICT_STAGES`/`TRANSITIONS` are literal copies of
`ai_workflow_engine.prompt.models.WORKFLOW_STAGES`,
`ai_workflow_engine.workflow.events.VERDICT_STAGES`, and
`ai_workflow_engine.workflow.transitions._TRANSITIONS` **by value only** — this package never
imports the engine (`DASH-005.md` Stage-Specific Notes: "read as prior art only, never imported
or modified"; `agentos_dashboard/__init__.py`). Keeping this table in sync with the engine's own
on a future engine change is a documented risk (see the stage completion report), the same
trade-off `parsing.models.TaskStatus` already accepts for the task queue's three statuses.

This module intentionally does **not** attempt to compute which of the seven engine stages a
given task-queue task is "currently at": that fact lives in the engine's own persisted,
event-sourced workflow state (`ai_workflow_engine.workflow.event_store`), which is stored under
the operator's home directory (`~/.ai-workflow-engine/workflow-runs/state/**`) — outside the
repository root every adapter in this package is confined to (`SECURITY_MODEL.md` SC-06..SC-08).
Reading outside that confinement is a scope decision no dashboard document has authorized (see
`OPEN_QUESTIONS.md` OD-D12); guessing a task's stage from prose keywords instead would risk
presenting a fabricated position as fact, which `SOURCE_OF_TRUTH.md` TR-04 forbids. The seven-
stage strip is therefore rendered identically on every task as a fixed reference diagram of the
engine's pipeline, never as a per-task computed position. What *is* genuinely per-task and
prose-derived is the task-queue status transition below, and the free-text lifecycle history
`services.tasks` extracts (DR-031).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.parsing.task_queue import TaskRecord
from agentos_dashboard.services.consistency import DEFAULT_MAXIMUM_CURRENT_TASKS

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

# Verbatim copy of `ai_workflow_engine.prompt.models.WORKFLOW_STAGES`.
WORKFLOW_STAGES: tuple[str, ...] = (
    "plan-review",
    "implementation",
    "implementation-review",
    "remediation",
    "governance-closeout",
    "governance-review",
    "push",
)

# Verbatim copy of `ai_workflow_engine.workflow.transitions.INITIAL_STAGE`.
INITIAL_STAGE = "plan-review"

# Verbatim copy of `ai_workflow_engine.workflow.events.VERDICT_STAGES`.
VERDICT_STAGES: frozenset[str] = frozenset(
    {"plan-review", "implementation-review", "governance-review"}
)


@dataclass(frozen=True)
class StageTransition:
    """One `(stage, outcome) -> next_stage` edge of the engine's fixed transition table."""

    stage: str
    outcome: str
    next_stage: str | None


# Verbatim copy of `ai_workflow_engine.workflow.transitions._TRANSITIONS`, with one addition:
# the `push` "completed" row that module leaves implicit as a special case in
# `next_stage_after` ("if event.stage == 'push': return None") is spelled out here as an
# explicit terminal edge, so this table is complete on its own rather than depending on an
# undocumented special case at every call site that walks it.
TRANSITIONS: tuple[StageTransition, ...] = (
    StageTransition("plan-review", "APPROVED", "implementation"),
    StageTransition("plan-review", "REJECTED", "plan-review"),
    StageTransition("implementation", "completed", "implementation-review"),
    StageTransition("implementation-review", "APPROVED", "governance-closeout"),
    StageTransition("implementation-review", "REJECTED", "remediation"),
    StageTransition("remediation", "completed", "implementation-review"),
    StageTransition("governance-closeout", "completed", "governance-review"),
    StageTransition("governance-review", "APPROVED", "push"),
    StageTransition("governance-review", "REJECTED", "governance-closeout"),
    StageTransition("push", "completed", None),
)


def is_verdict_stage(stage: str) -> bool:
    return stage in VERDICT_STAGES


def outcomes_for(stage: str) -> tuple[str, ...]:
    """The outcome tokens `stage` may be recorded with: two verdicts, or one `completed`."""
    return ("APPROVED", "REJECTED") if is_verdict_stage(stage) else ("completed",)


@dataclass(frozen=True)
class QueueTransition:
    """DR-021's "allowed/blocked next workflow transition, with reason" for one task-queue
    record — the queue's own three-status lifecycle (Planned -> Current -> Done), never the
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
