"""`services.workflow` — EN-07/EN-08's coded stage mirror and queue-status transitions."""

from __future__ import annotations

from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.parsing.task_queue import TaskRecord
from agentos_dashboard.services.workflow import (
    INITIAL_STAGE,
    TRANSITIONS,
    VERDICT_STAGES,
    WORKFLOW_STAGES,
    compute_queue_transitions,
    is_verdict_stage,
    outcomes_for,
)


def _record(task_id: str, status: TaskStatus) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        status=status,
        source="docs/TASK_QUEUE.md",
        line=1,
        detail_text="fixture",
        detail_line=1,
    )


def test_workflow_stages_are_the_engines_exact_seven_in_order() -> None:
    assert WORKFLOW_STAGES == (
        "plan-review",
        "implementation",
        "implementation-review",
        "remediation",
        "governance-closeout",
        "governance-review",
        "push",
    )


def test_initial_stage_is_plan_review() -> None:
    assert INITIAL_STAGE == "plan-review"


def test_verdict_stages_are_exactly_the_three_review_stages() -> None:
    assert VERDICT_STAGES == frozenset(
        {"plan-review", "implementation-review", "governance-review"}
    )
    for stage in WORKFLOW_STAGES:
        assert is_verdict_stage(stage) == (stage in VERDICT_STAGES)


def test_outcomes_for_a_verdict_stage_are_the_two_verdicts() -> None:
    assert outcomes_for("plan-review") == ("APPROVED", "REJECTED")


def test_outcomes_for_a_non_verdict_stage_is_completed_only() -> None:
    assert outcomes_for("implementation") == ("completed",)
    assert outcomes_for("push") == ("completed",)


def test_transition_table_has_ten_edges_covering_every_stage() -> None:
    # The engine's own nine `(stage, outcome) -> next` edges, plus the explicit `push`
    # terminal row this module spells out (see `services.workflow`'s module docstring).
    assert len(TRANSITIONS) == 10
    stages_seen = {edge.stage for edge in TRANSITIONS}
    assert stages_seen == set(WORKFLOW_STAGES)


def test_transition_table_matches_the_engines_fixed_graph() -> None:
    edges = {(edge.stage, edge.outcome): edge.next_stage for edge in TRANSITIONS}
    assert edges == {
        ("plan-review", "APPROVED"): "implementation",
        ("plan-review", "REJECTED"): "plan-review",
        ("implementation", "completed"): "implementation-review",
        ("implementation-review", "APPROVED"): "governance-closeout",
        ("implementation-review", "REJECTED"): "remediation",
        ("remediation", "completed"): "implementation-review",
        ("governance-closeout", "completed"): "governance-review",
        ("governance-review", "APPROVED"): "push",
        ("governance-review", "REJECTED"): "governance-closeout",
        ("push", "completed"): None,
    }


def test_push_is_the_sole_terminal_stage() -> None:
    terminal = [edge.stage for edge in TRANSITIONS if edge.next_stage is None]
    assert terminal == ["push"]


def test_planned_task_transition_is_allowed_when_no_task_is_current() -> None:
    records = (_record("FIX-001", TaskStatus.PLANNED),)
    (transition,) = compute_queue_transitions(records)
    assert transition.next_status is TaskStatus.CURRENT
    assert transition.allowed is True
    assert "0/1" in transition.reason


def test_planned_task_transition_is_blocked_by_the_sole_current_task() -> None:
    records = (_record("FIX-001", TaskStatus.PLANNED), _record("FIX-002", TaskStatus.CURRENT))
    transitions = {t.task_id: t for t in compute_queue_transitions(records)}
    assert transitions["FIX-001"].allowed is False
    assert "FIX-002" in transitions["FIX-001"].reason
    assert transitions["FIX-001"].next_status is TaskStatus.CURRENT


def test_current_task_transition_targets_done_and_is_reported_allowed_but_gated() -> None:
    records = (_record("FIX-002", TaskStatus.CURRENT),)
    (transition,) = compute_queue_transitions(records)
    assert transition.next_status is TaskStatus.DONE
    assert transition.allowed is True
    assert "governance closeout" in transition.reason


def test_done_task_transition_is_terminal() -> None:
    records = (_record("FIX-000", TaskStatus.DONE),)
    (transition,) = compute_queue_transitions(records)
    assert transition.next_status is None
    assert transition.allowed is False
    assert transition.reason == "terminal: task is Done"


def test_maximum_current_tasks_parameter_raises_the_capacity_before_blocking() -> None:
    records = (_record("FIX-001", TaskStatus.PLANNED), _record("FIX-002", TaskStatus.CURRENT))
    transitions = {
        t.task_id: t for t in compute_queue_transitions(records, maximum_current_tasks=2)
    }
    # One task already Current is under a capacity of 2, so a second may legally become Current.
    assert transitions["FIX-001"].allowed is True
    assert "1/2" in transitions["FIX-001"].reason


def test_default_maximum_current_tasks_matches_the_consistency_engines_constant() -> None:
    from agentos_dashboard.services.consistency import DEFAULT_MAXIMUM_CURRENT_TASKS

    records = (_record("FIX-001", TaskStatus.PLANNED), _record("FIX-002", TaskStatus.CURRENT))
    (fix_001,) = (t for t in compute_queue_transitions(records) if t.task_id == "FIX-001")
    assert DEFAULT_MAXIMUM_CURRENT_TASKS == 1
    assert fix_001.allowed is False
