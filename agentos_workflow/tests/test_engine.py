"""Tests for agentos_workflow.orchestrator.engine (WORKFLOW_STATES.md §2-4)."""

from itertools import product
from pathlib import Path

import pytest

from agentos_workflow.orchestrator.engine import (
    _INTERNAL_TOKEN,  # whitebox: capability token
    TERMINAL_STATES,
    AuthorizationBypassError,
    AuthorizationContext,
    AuthorizationRecord,
    InvalidTransitionError,
    WorkflowState,
    WorkflowStateMachine,
    authorize,
    is_transition_allowed,
    validate_transition,
)
from agentos_workflow.orchestrator.state_store import StateStore

# Independently transcribed from WORKFLOW_STATES.md §3's fenced transition table, kept separate
# from agentos_workflow.orchestrator.engine.ALLOWED_TRANSITIONS so the exhaustive test below
# checks the module's behavior against the governing document, not against itself.
S = WorkflowState
EXPECTED_ALLOWED_TRANSITIONS: frozenset[tuple[WorkflowState, WorkflowState]] = frozenset(
    {
        (S.CREATED, S.AUTHORIZED),
        (S.AUTHORIZED, S.PRECONDITIONS_CHECKED),
        (S.AUTHORIZED, S.FAILED),
        (S.PRECONDITIONS_CHECKED, S.BRANCH_CREATED),
        (S.PRECONDITIONS_CHECKED, S.FAILED),
        (S.BRANCH_CREATED, S.IMPLEMENTING),
        (S.BRANCH_CREATED, S.FAILED),
        (S.IMPLEMENTING, S.VALIDATING),
        (S.IMPLEMENTING, S.FAILED),
        (S.VALIDATING, S.QA_RUNNING),
        (S.VALIDATING, S.REPAIRING),
        (S.VALIDATING, S.FAILED),
        (S.QA_RUNNING, S.READY_TO_COMMIT),
        (S.QA_RUNNING, S.REPAIRING),
        (S.QA_RUNNING, S.FAILED),
        (S.REPAIRING, S.VALIDATING),
        (S.REPAIRING, S.FAILED),
        (S.READY_TO_COMMIT, S.COMMITTED),
        (S.READY_TO_COMMIT, S.FAILED),
        (S.COMMITTED, S.PUSHED),
        (S.COMMITTED, S.FAILED),
        (S.PUSHED, S.PR_OPEN),
        (S.PUSHED, S.FAILED),
        (S.PR_OPEN, S.AUTO_MERGE_ENABLED),
        (S.PR_OPEN, S.FAILED),
        (S.AUTO_MERGE_ENABLED, S.WAITING_FOR_CHECKS),
        (S.AUTO_MERGE_ENABLED, S.FAILED),
        (S.WAITING_FOR_CHECKS, S.MERGED),
        (S.WAITING_FOR_CHECKS, S.FAILED),
        (S.MERGED, S.CLOSING),
        (S.MERGED, S.FAILED),
        (S.CLOSING, S.DONE),
        (S.CLOSING, S.FAILED),
        (S.CREATED, S.CANCELLED),
        (S.AUTHORIZED, S.CANCELLED),
        (S.PRECONDITIONS_CHECKED, S.CANCELLED),
        (S.BRANCH_CREATED, S.CANCELLED),
    }
)

EXPECTED_STATE_NAMES = {
    "CREATED",
    "AUTHORIZED",
    "PRECONDITIONS_CHECKED",
    "BRANCH_CREATED",
    "IMPLEMENTING",
    "VALIDATING",
    "QA_RUNNING",
    "REPAIRING",
    "READY_TO_COMMIT",
    "COMMITTED",
    "PUSHED",
    "PR_OPEN",
    "AUTO_MERGE_ENABLED",
    "WAITING_FOR_CHECKS",
    "MERGED",
    "CLOSING",
    "DONE",
    "FAILED",
    "CANCELLED",
}


class TestStateDefinitions:
    def test_exactly_nineteen_states(self) -> None:
        assert len(WorkflowState) == 19

    def test_state_names_match_governing_document(self) -> None:
        assert {state.value for state in WorkflowState} == EXPECTED_STATE_NAMES

    def test_terminal_states_are_exactly_done_failed_cancelled(self) -> None:
        assert TERMINAL_STATES == {
            WorkflowState.DONE,
            WorkflowState.FAILED,
            WorkflowState.CANCELLED,
        }


class TestTransitionTableExhaustive:
    @pytest.mark.parametrize(
        ("from_state", "to_state"), list(product(WorkflowState, WorkflowState))
    )
    def test_every_state_pair_matches_the_governing_document(
        self, from_state: WorkflowState, to_state: WorkflowState
    ) -> None:
        # 19 x 19 = 361 pairs. Every one not explicitly listed in WORKFLOW_STATES.md §3 must be
        # rejected — this is what "reject every forbidden transition" means made exhaustive,
        # rather than a handful of spot checks that could miss an unlisted edge.
        expected = (from_state, to_state) in EXPECTED_ALLOWED_TRANSITIONS
        assert is_transition_allowed(from_state, to_state) is expected

    def test_exactly_thirty_seven_allowed_transitions(self) -> None:
        allowed = [
            (a, b) for a, b in product(WorkflowState, WorkflowState) if is_transition_allowed(a, b)
        ]
        assert len(allowed) == 37


class TestForbiddenTransitionCategories:
    """WORKFLOW_STATES.md §4, named categories, as readable individual cases (in addition to the
    exhaustive grid above)."""

    def test_skipping_an_intermediate_state_is_forbidden(self) -> None:
        assert not is_transition_allowed(WorkflowState.BRANCH_CREATED, WorkflowState.COMMITTED)

    def test_returning_to_created_from_any_later_state_is_forbidden(self) -> None:
        for state in WorkflowState:
            if state is WorkflowState.CREATED:
                continue
            assert not is_transition_allowed(state, WorkflowState.CREATED)

    def test_returning_to_authorized_from_any_later_state_is_forbidden(self) -> None:
        for state in WorkflowState:
            if state in {WorkflowState.CREATED, WorkflowState.AUTHORIZED}:
                continue
            assert not is_transition_allowed(state, WorkflowState.AUTHORIZED)

    @pytest.mark.parametrize("terminal_state", sorted(TERMINAL_STATES, key=str))
    def test_no_transition_leaves_a_terminal_state(self, terminal_state: WorkflowState) -> None:
        for to_state in WorkflowState:
            assert not is_transition_allowed(terminal_state, to_state)

    def test_cancelled_unreachable_after_implementing_begins(self) -> None:
        # Only {CREATED, AUTHORIZED, PRECONDITIONS_CHECKED, BRANCH_CREATED} may reach CANCELLED.
        post_implementing_states = set(WorkflowState) - {
            WorkflowState.CREATED,
            WorkflowState.AUTHORIZED,
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.BRANCH_CREATED,
        }
        for state in post_implementing_states:
            assert not is_transition_allowed(state, WorkflowState.CANCELLED)

    def test_validate_transition_raises_for_forbidden_pair(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(WorkflowState.DONE, WorkflowState.IMPLEMENTING)
        assert exc_info.value.from_state == WorkflowState.DONE
        assert exc_info.value.to_state == WorkflowState.IMPLEMENTING

    def test_validate_transition_passes_silently_for_allowed_pair(self) -> None:
        validate_transition(WorkflowState.CREATED, WorkflowState.AUTHORIZED)  # must not raise


class TestWorkflowStateMachine:
    def test_default_initial_state_is_created(self) -> None:
        machine = WorkflowStateMachine()
        assert machine.state == WorkflowState.CREATED
        assert not machine.is_terminal

    def test_explicit_initial_state(self) -> None:
        machine = WorkflowStateMachine(
            initial_state=WorkflowState.VALIDATING, _token=_INTERNAL_TOKEN
        )
        assert machine.state == WorkflowState.VALIDATING

    def test_can_transition_to_reflects_allowed_set(self) -> None:
        machine = WorkflowStateMachine()
        assert machine.can_transition_to(WorkflowState.AUTHORIZED)
        assert not machine.can_transition_to(WorkflowState.DONE)

    def test_transition_to_applies_allowed_transition(self) -> None:
        # CREATED -> AUTHORIZED is deliberately not used here: transition_to() now refuses that
        # specific edge outright (only authorize() may apply it) — see
        # test_transition_to_refuses_authorized_directly below. CREATED -> CANCELLED exercises
        # the same "transition_to applies an allowed transition" behavior via a different,
        # unrestricted edge.
        machine = WorkflowStateMachine()
        result = machine.transition_to(WorkflowState.CANCELLED)
        assert result == WorkflowState.CANCELLED
        assert machine.state == WorkflowState.CANCELLED

    def test_transition_to_refuses_authorized_directly(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine.transition_to(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED  # unchanged

    def test_construction_directly_in_authorized_refused(self) -> None:
        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED)

    def test_transition_to_rejects_forbidden_transition_without_mutating_state(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(InvalidTransitionError):
            machine.transition_to(WorkflowState.IMPLEMENTING)
        assert machine.state == WorkflowState.CREATED  # unchanged

    def test_terminal_state_rejects_every_further_transition(self) -> None:
        machine = WorkflowStateMachine(initial_state=WorkflowState.FAILED, _token=_INTERNAL_TOKEN)
        assert machine.is_terminal
        for target in WorkflowState:
            # AUTHORIZED is refused unconditionally by transition_to (AuthorizationBypassError),
            # regardless of current state; every other target is rejected by the ordinary
            # transition-table check (InvalidTransitionError) since FAILED has no outgoing edges.
            expected_error = (
                AuthorizationBypassError
                if target is WorkflowState.AUTHORIZED
                else InvalidTransitionError
            )
            with pytest.raises(expected_error):
                machine.transition_to(target)
        assert machine.state == WorkflowState.FAILED  # never budged

    def test_full_happy_path_created_to_done(self, tmp_path: Path) -> None:
        # This test validates the raw ALLOWED_TRANSITIONS table end to end. The one step
        # transition_to() itself refuses (CREATED -> AUTHORIZED) is applied via the real,
        # public authorize() — test code has no other legitimate way to reach AUTHORIZED, by
        # design (TestStructuralNonBypassability in test_engine_authorization.py) — so the table
        # check for every other edge is still exercised through the ordinary transition_to().
        machine = WorkflowStateMachine()
        store = StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")
        context = AuthorizationContext(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            stage_id="AUTO-002",
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            baseline_branch="main",
        )
        record = AuthorizationRecord(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path="/home/user/repo",
            stage_id="AUTO-002",
            stage_contract_path="docs/workflow-automation/stage-prompts/AUTO-002.md",
            stage_contract_hash="sha256:deadbeef",
            baseline_branch="main",
            baseline_commit_sha="163bcee1c280bccd6ad4b41fd3840777ef0769f1",
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            authorized_at="2026-07-24T10:00:00+00:00",
            engine_version="0.1.0",
        )
        authorize(machine, context, record, state_store=store)
        happy_path = [
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.BRANCH_CREATED,
            WorkflowState.IMPLEMENTING,
            WorkflowState.VALIDATING,
            WorkflowState.QA_RUNNING,
            WorkflowState.READY_TO_COMMIT,
            WorkflowState.COMMITTED,
            WorkflowState.PUSHED,
            WorkflowState.PR_OPEN,
            WorkflowState.AUTO_MERGE_ENABLED,
            WorkflowState.WAITING_FOR_CHECKS,
            WorkflowState.MERGED,
            WorkflowState.CLOSING,
            WorkflowState.DONE,
        ]
        for next_state in happy_path:
            machine.transition_to(next_state)
        assert machine.state == WorkflowState.DONE
        assert machine.is_terminal

    def test_repair_cycle_returns_to_validating(self) -> None:
        machine = WorkflowStateMachine(
            initial_state=WorkflowState.VALIDATING, _token=_INTERNAL_TOKEN
        )
        machine.transition_to(WorkflowState.REPAIRING)
        machine.transition_to(WorkflowState.VALIDATING)
        assert machine.state == WorkflowState.VALIDATING

    def test_early_cancellation_path(self) -> None:
        machine = WorkflowStateMachine(
            initial_state=WorkflowState.BRANCH_CREATED, _token=_INTERNAL_TOKEN
        )
        machine.transition_to(WorkflowState.CANCELLED)
        assert machine.state == WorkflowState.CANCELLED
        assert machine.is_terminal
