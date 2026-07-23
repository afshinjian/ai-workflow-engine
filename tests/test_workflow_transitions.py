import pytest

from ai_workflow_engine.prompt.models import WORKFLOW_STAGES, is_workflow_stage
from ai_workflow_engine.workflow.events import VERDICT_STAGES, Verdict, WorkflowEvent, WorkflowStage
from ai_workflow_engine.workflow.transitions import (
    INITIAL_STAGE,
    TerminalTask,
    TransitionViolation,
    VerdictForbidden,
    VerdictRequired,
    check_new_stage,
    check_outcome_kind,
    event_outcome,
    expected_stage,
    next_stage_after,
)

_HEAD = "a" * 40


def event(
    stage: WorkflowStage, *, verdict: Verdict | None = None, sequence: int = 1
) -> WorkflowEvent:
    action = "verdict" if stage in VERDICT_STAGES else "completed"
    return WorkflowEvent(
        schema_version="1.0",
        project_id="proj",
        task_id="T-1",
        sequence=sequence,
        parent_digest=None if sequence == 1 else "b" * 64,
        stage=stage,
        action=action,
        verdict=verdict,
        prompt_id=None,
        agent_run_id=None,
        head=_HEAD,
        note="",
    )


def test_expected_stage_empty_history() -> None:
    assert expected_stage([]) == INITIAL_STAGE == "plan-review"


@pytest.mark.parametrize(
    "stage,verdict,expected",
    [
        ("plan-review", "APPROVED", "implementation"),
        ("plan-review", "REJECTED", "plan-review"),
        ("implementation", None, "implementation-review"),
        ("implementation-review", "APPROVED", "governance-closeout"),
        ("implementation-review", "REJECTED", "remediation"),
        ("remediation", None, "implementation-review"),
        ("governance-closeout", None, "governance-review"),
        ("governance-review", "APPROVED", "push"),
        ("governance-review", "REJECTED", "governance-closeout"),
    ],
)
def test_transition_rows(stage: WorkflowStage, verdict: Verdict | None, expected: str) -> None:
    assert next_stage_after(event(stage, verdict=verdict)) == expected


def test_push_is_terminal() -> None:
    assert next_stage_after(event("push")) is None


def test_event_outcome() -> None:
    assert event_outcome(event("plan-review", verdict="APPROVED")) == "APPROVED"
    assert event_outcome(event("implementation")) == "completed"


def test_full_happy_path_reaches_terminal() -> None:
    history: list[WorkflowEvent] = []
    steps: list[tuple[WorkflowStage, Verdict | None]] = [
        ("plan-review", "APPROVED"),
        ("implementation", None),
        ("implementation-review", "APPROVED"),
        ("governance-closeout", None),
        ("governance-review", "APPROVED"),
        ("push", None),
    ]
    for index, (stage, verdict) in enumerate(steps, start=1):
        assert expected_stage(history) == stage
        check_new_stage(history, stage)
        history.append(event(stage, verdict=verdict, sequence=index))
    assert expected_stage(history) is None


def test_rejection_loops() -> None:
    # implementation-review REJECTED -> remediation -> implementation-review
    history = [
        event("plan-review", verdict="APPROVED", sequence=1),
        event("implementation", sequence=2),
        event("implementation-review", verdict="REJECTED", sequence=3),
    ]
    assert expected_stage(history) == "remediation"
    history.append(event("remediation", sequence=4))
    assert expected_stage(history) == "implementation-review"


def test_check_new_stage_rejects_wrong_stage() -> None:
    with pytest.raises(TransitionViolation):
        check_new_stage([], "implementation")


def test_check_new_stage_terminal() -> None:
    history = [
        event("plan-review", verdict="APPROVED", sequence=1),
        event("implementation", sequence=2),
        event("implementation-review", verdict="APPROVED", sequence=3),
        event("governance-closeout", sequence=4),
        event("governance-review", verdict="APPROVED", sequence=5),
        event("push", sequence=6),
    ]
    with pytest.raises(TerminalTask):
        check_new_stage(history, "plan-review")


@pytest.mark.parametrize("stage", sorted(VERDICT_STAGES))
def test_check_outcome_kind_requires_verdict(stage: WorkflowStage) -> None:
    with pytest.raises(VerdictRequired):
        check_outcome_kind(stage, has_verdict=False)
    check_outcome_kind(stage, has_verdict=True)  # no raise


@pytest.mark.parametrize("stage", ["implementation", "remediation", "governance-closeout", "push"])
def test_check_outcome_kind_forbids_verdict(stage: WorkflowStage) -> None:
    with pytest.raises(VerdictForbidden):
        check_outcome_kind(stage, has_verdict=True)
    check_outcome_kind(stage, has_verdict=False)  # no raise


@pytest.mark.parametrize("stage", WORKFLOW_STAGES)
def test_is_workflow_stage_accepts_every_canonical_stage(stage: WorkflowStage) -> None:
    assert is_workflow_stage(stage)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-stage",
        "Implementation",
        "implementation ",
        "plan_review",
        "push\n",
    ],
)
def test_is_workflow_stage_rejects_unsupported_values(value: str) -> None:
    """Unsupported stage strings are rejected, including near-miss casing/whitespace variants."""
    assert not is_workflow_stage(value)
