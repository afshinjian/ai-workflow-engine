"""The fixed workflow transition table and replay/next-stage logic (task T-302).

This is the complete graph — there are no other transitions, no skips, and no administrative
overrides. See ``docs/milestone-3-plan.md`` for the normative table.
"""

from ai_workflow_engine.prompt.models import WorkflowStage
from ai_workflow_engine.workflow.events import VERDICT_STAGES, WorkflowEvent

INITIAL_STAGE: WorkflowStage = "plan-review"

# (stage, outcome) -> next expected stage. Outcome is the verdict token for verdict stages, or
# the literal "completed" for non-verdict stages. `push completed` is terminal and intentionally
# absent (handled as None by next_stage_after).
_TRANSITIONS: dict[tuple[WorkflowStage, str], WorkflowStage] = {
    ("plan-review", "APPROVED"): "implementation",
    ("plan-review", "REJECTED"): "plan-review",
    ("implementation", "completed"): "implementation-review",
    ("implementation-review", "APPROVED"): "governance-closeout",
    ("implementation-review", "REJECTED"): "remediation",
    ("remediation", "completed"): "implementation-review",
    ("governance-closeout", "completed"): "governance-review",
    ("governance-review", "APPROVED"): "push",
    ("governance-review", "REJECTED"): "governance-closeout",
}


class WorkflowStateError(ValueError):
    """Base for workflow-state errors; ``code`` names the specific failure for findings."""

    code = "state_error"


class TransitionViolation(WorkflowStateError):
    code = "transition_violation"


class TerminalTask(WorkflowStateError):
    code = "terminal_task"


class VerdictRequired(WorkflowStateError):
    code = "verdict_required"


class VerdictForbidden(WorkflowStateError):
    code = "verdict_forbidden"


def event_outcome(event: WorkflowEvent) -> str:
    """The transition-table outcome key for an event: its verdict, or ``"completed"``."""
    if event.action == "verdict":
        assert event.verdict is not None  # guaranteed by WorkflowEvent cross-field validation
        return event.verdict
    return "completed"


def next_stage_after(event: WorkflowEvent) -> WorkflowStage | None:
    """The expected next stage after ``event``, or ``None`` if the task is now terminal."""
    if event.stage == "push":
        return None
    return _TRANSITIONS[(event.stage, event_outcome(event))]


def expected_stage(history: list[WorkflowEvent]) -> WorkflowStage | None:
    """The stage that may be recorded next given ``history`` (``None`` == terminal)."""
    if not history:
        return INITIAL_STAGE
    return next_stage_after(history[-1])


def check_new_stage(history: list[WorkflowEvent], stage: WorkflowStage) -> None:
    """Raise if recording ``stage`` next is not permitted by the transition table."""
    expected = expected_stage(history)
    if expected is None:
        raise TerminalTask(
            "The task is already terminal (push completed); no further event may be recorded"
        )
    if stage != expected:
        raise TransitionViolation(
            f"Cannot record stage {stage!r}: the expected next stage is {expected!r}"
        )


def check_outcome_kind(stage: WorkflowStage, *, has_verdict: bool) -> None:
    """Raise if the supplied outcome kind (verdict vs. completed) is wrong for ``stage``."""
    if stage in VERDICT_STAGES and not has_verdict:
        raise VerdictRequired(f"stage {stage!r} requires an APPROVED or REJECTED verdict")
    if stage not in VERDICT_STAGES and has_verdict:
        raise VerdictForbidden(f"stage {stage!r} does not take a verdict; use --completed")
