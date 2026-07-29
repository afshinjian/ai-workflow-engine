"""AUTO-007 §4b deliverable: the initial-execution retry/reconciliation matrix
(`TEST_STRATEGY.md` §4b, `WORKFLOW_STATES.md` §5a).

`test_engine_retry.py` already proves `evaluate_initial_execution_failure`'s decision logic in
depth, but almost every case in it (attempt accounting, exhaustion, the six-item reconciliation
policy) is exercised only for `IMPLEMENTING`. This module is the explicit (state x outcome)
matrix `TEST_STRATEGY.md` §4b names for all four states the policy applies to — `IMPLEMENTING`,
`READY_TO_COMMIT`, `COMMITTED`, `PUSHED` — reusing the same real fixtures, evidence factories,
and public `evaluate_initial_execution_failure`/`record_initial_execution_attempt*` API
`test_engine_retry.py` already establishes.

**A genuine, load-bearing gap this matrix surfaces rather than papers over**: for `COMMITTED`
and `PUSHED`, whose reconciliation evidence describes remote/GitHub facts
(`RemoteRefEvidence`/`PullRequestEvidence`), `evaluate_initial_execution_failure` has no
authorized local verifier and *always* raises `ReconciliationVerifierUnavailableError` once a
possible side effect is confirmed — regardless of whether the caller claims success or failure
(`engine.py`'s `_verify_evidence_locally`, AUTO002-F07, Human Owner decision 2026-07-27). AUTO-006
delivered the GitHub-facing Skills that could eventually back a real observer, but wiring one into
this reconciliation policy is `agentos_workflow/orchestrator/engine.py` production work outside
this stage's allowed files (`agentos_workflow/tests/e2e/**`, `agentos_workflow/tests/recovery/**`
only) — so items 3 ("reconciliation confirms success") and 5 ("unrecoverable/indeterminate ->
FAILED") for these two states are, today, both the *same* fail-closed
`ReconciliationVerifierUnavailableError` outcome, which is itself the correct, safe behavior
under §5a item 6 ("never report success solely because... unconfirmed") — not a bug, but a
documented capability gap. This module tests that current, real behavior precisely rather than
asserting a forward edge the engine cannot yet produce.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_workflow.orchestrator.engine import (
    InitialExecutionFailureKind,
    ReconciliationVerifierUnavailableError,
    RetryOutcome,
    WorkflowState,
    record_initial_execution_attempt,
    record_initial_execution_attempt_started,
)
from agentos_workflow.orchestrator.state_store import StateStore
from agentos_workflow.tests.test_engine_retry import (
    _EVIDENCE_FACTORY_BY_STATE,
    _evaluate_initial_execution_failure,
    _evidence,
    _seed_authorized,
    _store,
    _transition,
)

# The four states WORKFLOW_STATES.md §5a's policy applies to, and the transitions needed to
# reach each from a freshly authorized workflow.
_CHAIN_TO: dict[WorkflowState, list[tuple[str, str]]] = {
    WorkflowState.IMPLEMENTING: [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
    ],
    WorkflowState.READY_TO_COMMIT: [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
        ("VALIDATING", "QA_RUNNING"),
        ("QA_RUNNING", "READY_TO_COMMIT"),
    ],
    WorkflowState.COMMITTED: [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
        ("VALIDATING", "QA_RUNNING"),
        ("QA_RUNNING", "READY_TO_COMMIT"),
        ("READY_TO_COMMIT", "COMMITTED"),
    ],
    WorkflowState.PUSHED: [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
        ("VALIDATING", "QA_RUNNING"),
        ("QA_RUNNING", "READY_TO_COMMIT"),
        ("READY_TO_COMMIT", "COMMITTED"),
        ("COMMITTED", "PUSHED"),
    ],
}

_ALL_FOUR_STATES = (
    WorkflowState.IMPLEMENTING,
    WorkflowState.READY_TO_COMMIT,
    WorkflowState.COMMITTED,
    WorkflowState.PUSHED,
)

# Only these two states have a reconciliation-evidence type this engine can independently verify
# from local Git/filesystem state alone (AUTO002-F07); the other two always fail closed (see
# module docstring).
_LOCALLY_VERIFIABLE_STATES = (WorkflowState.IMPLEMENTING, WorkflowState.READY_TO_COMMIT)
_REMOTE_ONLY_STATES = (WorkflowState.COMMITTED, WorkflowState.PUSHED)

_FORWARD_EDGE = {
    WorkflowState.IMPLEMENTING: WorkflowState.VALIDATING,
    WorkflowState.READY_TO_COMMIT: WorkflowState.COMMITTED,
}


def _seed_to(store: StateStore, state: WorkflowState) -> None:
    _seed_authorized(store)
    for from_state, to_state in _CHAIN_TO[state]:
        store.record_transition(_transition(from_state=from_state, to_state=to_state))


class TestOutcome1ProvenNoSideEffectPermitsRetry:
    """Item 1: a proven-pre-side-effect failure on the first attempt permits a same-state retry
    (`RetryOutcome.NO_RETRY_REQUIRED`) — never a transition."""

    @pytest.mark.parametrize("state", _ALL_FOUR_STATES, ids=lambda s: s.value)
    def test_first_attempt_permits_retry_without_transitioning(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        store = _store(tmp_path)
        _seed_to(store, state)
        result = _evaluate_initial_execution_failure(
            state=state,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
        )
        assert result.outcome is RetryOutcome.NO_RETRY_REQUIRED
        assert result.next_allowed_state is None


class TestOutcome2RetryLimitExhaustedReachesFailed:
    """Item 1: exhausting the retry limit reaches `FAILED` — never a silent further retry."""

    @pytest.mark.parametrize("state", _ALL_FOUR_STATES, ids=lambda s: s.value)
    def test_exhaustion_recommends_failed(self, tmp_path: Path, state: WorkflowState) -> None:
        store = _store(tmp_path)
        _seed_to(store, state)
        for attempt_number in (1, 2, 3):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=state,
                attempt_number=attempt_number,
                state_store=store,
                start_time=f"2026-07-24T10:00:0{attempt_number}+00:00",
            )
            record_initial_execution_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=state,
                attempt_number=attempt_number,
                state_store=store,
                completion_time=f"2026-07-24T10:00:0{attempt_number + 1}+00:00",
            )
        result = _evaluate_initial_execution_failure(
            state=state,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
        )
        assert result.outcome is RetryOutcome.RETRY_LIMIT_EXHAUSTED
        assert result.next_allowed_state is WorkflowState.FAILED


class TestOutcome3ReconciliationConfirmsSuccess:
    """Item 3, for the two locally-verifiable states: reconciliation confirming the side effect
    already occurred advances via the same forward edge ordinary success would, with no
    duplicated side effect (the evidence factory never re-invokes the Skill)."""

    @pytest.mark.parametrize("state", _LOCALLY_VERIFIABLE_STATES, ids=lambda s: s.value)
    def test_confirmed_success_advances_via_the_ordinary_forward_edge(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        store = _store(tmp_path)
        _seed_to(store, state)
        result = _evaluate_initial_execution_failure(
            state=state,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[state](succeeded=True, store=store),
            ),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_SUCCESSFUL
        assert result.next_allowed_state is _FORWARD_EDGE[state]

    @pytest.mark.parametrize("state", _REMOTE_ONLY_STATES, ids=lambda s: s.value)
    def test_remote_evidence_states_fail_closed_instead_of_a_fabricated_success(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        """`COMMITTED`/`PUSHED` describe remote/GitHub facts this engine has no authorized local
        verifier for (module docstring); a claimed success is never trusted on the caller's word
        alone, so this is the safe, current, "confirmed success" outcome for these two states."""
        store = _store(tmp_path)
        _seed_to(store, state)
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate_initial_execution_failure(
                state=state,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[state](succeeded=True),
                ),
            )


class TestOutcome4RecoverableInconsistencyOnlyFromImplementing:
    """Item 4: a recoverable inconsistency is only ever reachable from `IMPLEMENTING`, via the
    existing `IMPLEMENTING -> VALIDATING` edge — never a new `-> REPAIRING` edge, and never
    reachable at all from the other three states."""

    def test_implementing_recoverable_inconsistency_proceeds_to_validating(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to(store, WorkflowState.IMPLEMENTING)
        result = _evaluate_initial_execution_failure(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=False,
                recoverable=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](
                    succeeded=False, store=store
                ),
            ),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_FAILED
        assert result.next_allowed_state is WorkflowState.VALIDATING


class TestOutcome5UnrecoverableOrIndeterminateReachesFailed:
    """Item 5: everything else — exhausted retries (covered above), an unresolvable
    inconsistency, or (for the two remote-evidence states) an indeterminate claim this engine
    cannot verify at all — reaches `FAILED`, never silently continuing."""

    def test_implementing_unrecoverable_failure_reaches_failed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to(store, WorkflowState.IMPLEMENTING)
        result = _evaluate_initial_execution_failure(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=False,
                recoverable=False,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](
                    succeeded=False, store=store
                ),
            ),
        )
        assert result.outcome is RetryOutcome.UNRECOVERABLE_FAILURE
        assert result.next_allowed_state is WorkflowState.FAILED

    def test_ready_to_commit_unrecoverable_failure_reaches_failed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to(store, WorkflowState.READY_TO_COMMIT)
        result = _evaluate_initial_execution_failure(
            state=WorkflowState.READY_TO_COMMIT,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=False,
                recoverable=False,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.READY_TO_COMMIT](succeeded=False),
            ),
        )
        assert result.outcome is RetryOutcome.UNRECOVERABLE_FAILURE
        assert result.next_allowed_state is WorkflowState.FAILED

    @pytest.mark.parametrize("state", _REMOTE_ONLY_STATES, ids=lambda s: s.value)
    def test_remote_evidence_states_fail_closed_rather_than_a_fabricated_verdict(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        store = _store(tmp_path)
        _seed_to(store, state)
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate_initial_execution_failure(
                state=state,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=False,
                    recoverable=False,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[state](succeeded=False),
                ),
            )


class TestOutcome6TimeoutAloneNeverReadsAsSuccess:
    """§5a item 6's explicit safety test: a bare timeout, with no reconciliation evidence
    supplied at all, must never produce `RECONCILIATION_SUCCESSFUL` — the caller cannot skip
    reconciliation and still be read as a pass."""

    @pytest.mark.parametrize("state", _ALL_FOUR_STATES, ids=lambda s: s.value)
    def test_possible_side_effect_without_evidence_never_reads_as_success(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        from agentos_workflow.orchestrator.engine import MissingReconciliationEvidenceError

        store = _store(tmp_path)
        _seed_to(store, state)
        with pytest.raises(MissingReconciliationEvidenceError):
            _evaluate_initial_execution_failure(
                state=state,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            )

    @pytest.mark.parametrize("state", _ALL_FOUR_STATES, ids=lambda s: s.value)
    def test_unconfirmed_side_effect_requires_reconciliation_not_a_pass(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        store = _store(tmp_path)
        _seed_to(store, state)
        result = _evaluate_initial_execution_failure(
            state=state,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(side_effect_confirmed=False),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_REQUIRED
        assert result.next_allowed_state is None
