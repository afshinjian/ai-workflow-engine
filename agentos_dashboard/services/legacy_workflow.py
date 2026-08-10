"""DASH-005 remediation (`OPEN_QUESTIONS.md` OD-D12): the authoritative, per-task Legacy
`ai_workflow_engine` workflow projection.

This module is the dashboard's one, narrowly-scoped read of the engine's persisted,
event-sourced workflow-event store (`ai_workflow_engine.workflow.event_store`). That store lives
under `~/.ai-workflow-engine/workflow-runs/state/<project_id>/<task_dir>/` — outside the
repository working copy, and therefore outside every other adapter's `RepositoryRoot`
confinement (`core/paths.py`; `SECURITY_MODEL.md` SC-06..SC-08). `event_store` enforces its own
fixed, non-configurable containment to that state root, its own no-clobber write protocol, and
its own verified, canonical-bytes replay — so this module borrows *that* read-only guarantee
rather than granting the dashboard package any broader filesystem access. No path outside the
state root is ever touched here.

Deliberately **not** a second workflow authority: every stage name, verdict, transition rule, and
terminal-state judgement below is read directly from `ai_workflow_engine.workflow.event_store`
and `ai_workflow_engine.workflow.transitions` — this module calls `derive_state`, it does not
recompute what `derive_state` computes. `services.workflow`'s own coded constants remain a
separate, explicitly-labeled *reference* diagram (never a per-task position); this module is the
one and only source for what a specific task's actual, persisted position is.

Two concepts stay independent throughout, per the remediation's scope: the task queue's own
three-status lifecycle (Planned/Current/Done, `services.workflow.compute_queue_transitions`) and
the Legacy engine's seven-stage event-sourced workflow (below). Nothing here reads or writes
`docs/TASK_QUEUE.md`, and nothing in `services.tasks`/`services.board`'s queue-status logic reads
this module's output to decide a queue status.

Failure handling (`SOURCE_OF_TRUTH.md` TR-04): a read/verification failure against the event
store (corruption, a sequence conflict, an identity mismatch, an unreadable directory) never
raises into a page render and never invents a plausible-looking state — it is reported as
`available=False` with `error` set. A task that simply has no persisted events is a distinct,
legitimate state (`available=True, has_history=False`), not an error, and never receives a
fabricated `current_stage`.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from ai_workflow_engine.prompt.context import normalize_text
from ai_workflow_engine.prompt.models import WorkflowStage
from ai_workflow_engine.workflow import event_store
from ai_workflow_engine.workflow.events import StateAction, Verdict, WorkflowEvent
from ai_workflow_engine.workflow.transitions import (
    WorkflowStateError,
    event_outcome,
    next_stage_after,
)

__all__ = [
    "SELF_GOVERNANCE_PATH",
    "LegacyWorkflowEventView",
    "LegacyWorkflowProjection",
    "load_legacy_workflow",
    "read_project_id",
]

SELF_GOVERNANCE_PATH = "self-governance.yaml"


@dataclass(frozen=True)
class LegacyWorkflowEventView:
    """One persisted `WorkflowEvent`, verbatim engine fields plus the transition it recorded."""

    sequence: int
    stage: WorkflowStage
    action: StateAction
    verdict: Verdict | None
    outcome: str
    resulting_stage: WorkflowStage | None
    parent_digest: str | None
    prompt_id: str | None
    agent_run_id: str | None
    head: str
    note: str


@dataclass(frozen=True)
class LegacyWorkflowProjection:
    """The authoritative per-task Legacy-workflow projection for one task.

    `available=False` means the event store could not be read/verified at all (an explicit
    error, `error` set) — distinct from `has_history=False`, which means the store was read
    successfully and simply holds no events yet for this task. `current_stage` is populated only
    when at least one event has been persisted; it is never guessed.
    """

    task_id: str
    project_id: str | None
    available: bool
    error: str | None
    has_history: bool
    current_stage: WorkflowStage | None
    next_stage: WorkflowStage | None
    terminal: bool
    events: tuple[LegacyWorkflowEventView, ...]
    latest_event: LegacyWorkflowEventView | None


def _unavailable(*, task_id: str, project_id: str | None, error: str) -> LegacyWorkflowProjection:
    return LegacyWorkflowProjection(
        task_id=task_id,
        project_id=redact_secrets(project_id) if project_id is not None else None,
        available=False,
        error=redact_secrets(error),
        has_history=False,
        current_stage=None,
        next_stage=None,
        terminal=False,
        events=(),
        latest_event=None,
    )


def read_project_id(root: RepositoryRoot) -> str | None:
    """The Legacy engine's `project.id` (`self-governance.yaml`), or `None` if unavailable.

    Read through the same root-confined adapter every other watched document uses
    (`self-governance.yaml` is already `core.snapshot.WATCHED_FILES`); this function adds no new
    filesystem access surface, only a tolerant extraction of one field.
    """
    try:
        text = read_text(root, SELF_GOVERNANCE_PATH).text
    except (FileAccessError, PathRefusedError):
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    project_id = project.get("id")
    return project_id if isinstance(project_id, str) and project_id else None


def _event_view(event: WorkflowEvent) -> LegacyWorkflowEventView:
    return LegacyWorkflowEventView(
        sequence=event.sequence,
        stage=event.stage,
        action=event.action,
        verdict=event.verdict,
        outcome=event_outcome(event),
        resulting_stage=next_stage_after(event),
        parent_digest=event.parent_digest,
        prompt_id=redact_secrets(event.prompt_id) if event.prompt_id is not None else None,
        agent_run_id=(
            redact_secrets(event.agent_run_id) if event.agent_run_id is not None else None
        ),
        head=event.head,
        note=redact_secrets(event.note),
    )


def load_legacy_workflow(root: RepositoryRoot, task_id: str) -> LegacyWorkflowProjection:
    """The authoritative Legacy-workflow projection for `task_id`, read via `event_store`.

    Never raises: every failure mode (no configured `project.id`, a malformed task id, a
    corrupt/unreadable event store) degrades to `available=False` with `error` set, mirroring
    `core.snapshot.build_snapshot`'s SC-34 discipline. The repository is never mutated — only
    `event_store.load_history`/`derive_state` are called, never `append`/`record_outcome`.
    """
    try:
        normalized_task_id = normalize_text(task_id)
    except ValueError as exc:
        return _unavailable(task_id=task_id, project_id=None, error=f"invalid task id: {exc}")

    project_id = read_project_id(root)
    if project_id is None:
        return _unavailable(
            task_id=normalized_task_id,
            project_id=None,
            error=f"{SELF_GOVERNANCE_PATH} does not name a readable project.id",
        )

    try:
        state = event_store.derive_state(project_id, normalized_task_id)
    except WorkflowStateError as exc:
        return _unavailable(task_id=normalized_task_id, project_id=project_id, error=str(exc))
    except OSError as exc:
        return _unavailable(
            task_id=normalized_task_id,
            project_id=project_id,
            error=f"workflow event store could not be read: {exc}",
        )

    events = tuple(_event_view(event) for event in state.events)
    has_history = bool(events)
    current_stage: WorkflowStage | None = None
    if has_history:
        current_stage = state.events[-1].stage if state.terminal else state.next_stage
    return LegacyWorkflowProjection(
        task_id=normalized_task_id,
        project_id=redact_secrets(project_id),
        available=True,
        error=None,
        has_history=has_history,
        current_stage=current_stage,
        next_stage=state.next_stage,
        terminal=state.terminal,
        events=events,
        latest_event=events[-1] if events else None,
    )
