"""Tests for retry/reconciliation policy in agentos_workflow.orchestrator.engine
(WORKFLOW_STATES.md §5, §5a; FAILURE_RECOVERY.md §1, §1a)."""

import multiprocessing as mp
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentos_workflow.orchestrator.engine import (
    AttemptKind,
    AttemptLimitExceededError,
    AttemptPhase,
    AuthorizationContext,
    AuthorizationRecord,
    CommitEvidence,
    CorruptedAttemptRecordError,
    CorruptedHistoryError,
    DuplicateAttemptNumberError,
    EvidenceConsistencyError,
    EvidenceOperationMismatchError,
    EvidenceScopeMismatchError,
    ImplementationDiffEvidence,
    InconsistentAttemptHistoryError,
    InconsistentHistoryError,
    InitialExecutionFailureKind,
    MissingAttemptReservationError,
    MissingPersistedStateError,
    MissingReconciliationEvidenceError,
    NotRetryableStateError,
    PullRequestEvidence,
    ReconciliationEvidence,
    ReconciliationVerifierUnavailableError,
    RemoteRefEvidence,
    RetryAttemptRecord,
    RetryOutcome,
    RetryReconciliationResult,
    SkippedAttemptNumberError,
    UnexpectedWorkflowStateError,
    UnreconciledAttemptError,
    WorkflowAlreadyTerminalError,
    WorkflowStageMismatchError,
    WorkflowState,
    WorkflowStateMachine,
    authorize,
    evaluate_initial_execution_failure,
    evaluate_repair_attempt,
    has_unreconciled_initial_execution_attempt,
    reconstruct_initial_execution_attempts,
    record_initial_execution_attempt,
    record_initial_execution_attempt_started,
)
from agentos_workflow.orchestrator.state_store import StateStore, StateTransitionRecord

_REPOSITORY_IDENTITY = "github.com/org/repo"
_STAGE_BRANCH = "feature/auto-002-orchestrator-state-machine"
_ARTIFACT_NAME = "auto-002-implementation-report.json"


def _init_real_repository() -> tuple[str, str, str, str, tuple[str, ...]]:
    """Build a genuine, read-only-after-creation local Git repository backing this module's
    evidence fixtures (AUTO002-F07, Human Owner decision 2026-07-27): `evaluate_initial_execution_
    failure` now independently re-derives every locally-verifiable evidence fact from real Git
    state, so a fabricated repository path or a synthetic SHA can no longer pass verification —
    every test that expects confirmed evidence to be *accepted* needs a real commit, reachable
    from a real branch, in a real repository. Built once at import time (never mutated by any
    test) rather than per-test, since nothing here ever needs to differ across tests.
    """
    directory = Path(tempfile.mkdtemp(prefix="auto002-f07-fixture-repo-"))

    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(directory), *args], check=True, text=True, capture_output=True
        )

    _git("init", "-b", _STAGE_BRANCH)
    _git("config", "user.name", "AUTO-002 Test Fixture")
    _git("config", "user.email", "auto-002-test-fixture@example.invalid")
    (directory / "README.md").write_text(
        "AUTO-002 F07 evidence fixture repository — never mutated after creation.\n",
        encoding="utf-8",
    )
    _git("add", "README.md")
    _git("commit", "-m", "AUTO-002 F07 fixture base commit")
    baseline_sha = _git("rev-parse", "HEAD").stdout.strip()
    (directory / "implementation.txt").write_text("implemented\n", encoding="utf-8")
    _git("add", "implementation.txt")
    _git("commit", "-m", "AUTO-002 F07 fixture implementation")
    head_sha = _git("rev-parse", "HEAD").stdout.strip()
    tree_sha = _git("rev-parse", f"{head_sha}^{{tree}}").stdout.strip()
    return str(directory), baseline_sha, head_sha, tree_sha, ("implementation.txt",)


_REPOSITORY_PATH, _BASELINE_SHA, _COMMIT_SHA, _TREE_SHA, _CHANGED_PATHS = _init_real_repository()
_OTHER_SHA = "c" * 40  # well-formed but never a real commit in the fixture repository


def _store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def _evaluate_initial_execution_failure(
    *,
    workflow_id: str = "wf-1",
    stage_id: str = "AUTO-002",
    state: WorkflowState,
    state_store: StateStore,
    failure_kind: InitialExecutionFailureKind,
    evidence: ReconciliationEvidence | None = None,
    repository_identity: str = _REPOSITORY_IDENTITY,
    repository_path: str = _REPOSITORY_PATH,
) -> RetryReconciliationResult:
    return evaluate_initial_execution_failure(
        workflow_id=workflow_id,
        repository_identity=repository_identity,
        repository_path=repository_path,
        stage_id=stage_id,
        state=state,
        state_store=state_store,
        failure_kind=failure_kind,
        evidence=evidence,
        allowed_changed_paths=["**"],
        forbidden_changed_paths=[],
    )


def _evidence(
    *,
    workflow_id: str = "wf-1",
    repository_identity: str = _REPOSITORY_IDENTITY,
    repository_path: str = _REPOSITORY_PATH,
    stage_id: str = "AUTO-002",
    side_effect_confirmed: bool,
    side_effect_succeeded: bool | None = None,
    evidence: object | None = None,
    recoverable: bool | None = None,
    description: str = "",
) -> ReconciliationEvidence:
    return ReconciliationEvidence.model_validate(
        {
            "workflow_id": workflow_id,
            "repository_identity": repository_identity,
            "repository_path": repository_path,
            "stage_id": stage_id,
            "side_effect_confirmed": side_effect_confirmed,
            "side_effect_succeeded": side_effect_succeeded,
            "evidence": evidence,
            "recoverable": recoverable,
            "description": description,
        }
    )


def _write_completion_report_artifact(
    store: StateStore,
    *,
    workflow_id: str = "wf-1",
    state: WorkflowState = WorkflowState.IMPLEMENTING,
    artifact_name: str = _ARTIFACT_NAME,
    attempt_number: int = 1,
    content: str | None = None,
) -> Path:
    directory = store.audit_directory / workflow_id / "evidence" / state.value
    directory.mkdir(parents=True, exist_ok=True)
    artifact_path = directory / artifact_name
    if content is None:
        import json

        content = json.dumps(
            {
                "workflow_id": workflow_id,
                "stage_id": "AUTO-002",
                "attempt_number": attempt_number,
                "stage_branch": _STAGE_BRANCH,
                "observed_head_sha": _COMMIT_SHA,
                "changed_paths": list(_CHANGED_PATHS),
            }
        )
    artifact_path.write_text(content, encoding="utf-8")
    return artifact_path


def _commit_evidence(*, succeeded: bool = True, **_ignored: object) -> CommitEvidence:
    # `observed_tree_sha` is always the real, independently-verifiable tree of `_COMMIT_SHA`
    # (AUTO002-F07 recomputes it and compares against exactly this field); `expected_tree_sha` is
    # never independently checked (it names a target, not an observed Git fact), so it alone
    # varies to produce a genuine expected/observed mismatch for the `succeeded=False` case.
    return CommitEvidence(
        commit_sha=_COMMIT_SHA,
        expected_tree_sha=_TREE_SHA if succeeded else _OTHER_SHA,
        observed_tree_sha=_TREE_SHA,
    )


def _implementation_diff_evidence(
    *,
    succeeded: bool = True,
    store: StateStore | None = None,
    workflow_id: str = "wf-1",
    **_ignored: object,
) -> ImplementationDiffEvidence:
    attempt_number = 1
    if store is not None:
        completed = reconstruct_initial_execution_attempts(
            workflow_id, "AUTO-002", WorkflowState.IMPLEMENTING, store
        )
        if completed:
            attempt_number = completed[-1].attempt_number
        elif not has_unreconciled_initial_execution_attempt(
            workflow_id, "AUTO-002", WorkflowState.IMPLEMENTING, store
        ):
            record_initial_execution_attempt_started(
                workflow_id=workflow_id,
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=1,
                state_store=store,
                start_time="2026-07-24T10:00:01+00:00",
            )
        _write_completion_report_artifact(
            store, workflow_id=workflow_id, attempt_number=attempt_number
        )
    return ImplementationDiffEvidence(
        stage_branch=_STAGE_BRANCH,
        observed_head_sha=_COMMIT_SHA,
        attempt_number=attempt_number,
        changed_paths=_CHANGED_PATHS,
        completion_report_reference=_ARTIFACT_NAME,
    )


def _remote_ref_evidence(*, succeeded: bool = True, **_ignored: object) -> RemoteRefEvidence:
    return RemoteRefEvidence(
        remote_ref="refs/heads/feature/auto-002-orchestrator-state-machine",
        expected_sha=_COMMIT_SHA,
        observed_sha=_COMMIT_SHA if succeeded else _OTHER_SHA,
    )


def _pull_request_evidence(*, succeeded: bool = True, **_ignored: object) -> PullRequestEvidence:
    return PullRequestEvidence(
        pr_number=1,
        head_branch="feature/auto-002-orchestrator-state-machine",
        base_branch="main",
        expected_head_sha=_COMMIT_SHA,
        observed_head_sha=_COMMIT_SHA if succeeded else _OTHER_SHA,
    )


_EVIDENCE_FACTORY_BY_STATE: dict[WorkflowState, Callable[..., object]] = {
    WorkflowState.IMPLEMENTING: _implementation_diff_evidence,
    WorkflowState.READY_TO_COMMIT: _commit_evidence,
    WorkflowState.COMMITTED: _remote_ref_evidence,
    WorkflowState.PUSHED: _pull_request_evidence,
}


def _transition(
    *,
    workflow_id: str = "wf-1",
    target_repository: str = "github.com/org/repo",
    repository_path: str = _REPOSITORY_PATH,
    stage_id: str = "AUTO-002",
    from_state: str,
    to_state: str,
    timestamp: str = "2026-07-24T10:00:00+00:00",
    actor: str = "orchestrator",
) -> StateTransitionRecord:
    return StateTransitionRecord(
        workflow_id=workflow_id,
        target_repository=target_repository,
        repository_path=repository_path,
        stage_id=stage_id,
        from_state=from_state,
        to_state=to_state,
        timestamp=timestamp,
        actor=actor,
        gate_evidence_ref=None,
    )


def _authorization_record(
    *,
    workflow_id: str = "wf-1",
    stage_id: str = "AUTO-002",
    repository_identity: str = _REPOSITORY_IDENTITY,
    repository_path: str = _REPOSITORY_PATH,
) -> AuthorizationRecord:
    return AuthorizationRecord.model_validate(
        {
            "workflow_id": workflow_id,
            "repository_identity": repository_identity,
            "repository_path": repository_path,
            "stage_id": stage_id,
            "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
            "stage_contract_hash": "sha256:deadbeef",
            "baseline_branch": "main",
            "baseline_commit_sha": _BASELINE_SHA,
            "planned_stage_branch": "feature/auto-002-orchestrator-state-machine",
            "authorized_at": "2026-07-24T10:00:00+00:00",
            "authorized_by": "human-owner",
            "engine_version": "0.1.0",
        }
    )


def _seed_authorized(
    store: StateStore,
    *,
    workflow_id: str = "wf-1",
    stage_id: str = "AUTO-002",
    repository_identity: str = _REPOSITORY_IDENTITY,
    repository_path: str = _REPOSITORY_PATH,
) -> None:
    """Persist a genuine `CREATED -> AUTHORIZED` transition through the real, public `authorize()`
    API — the only way `_replay_history` (and therefore every retry/reconciliation entry point
    exercised in this file) will ever cross that edge, since it independently loads and validates
    a persisted `AuthorizationRecord` rather than trusting a fabricated `StateTransitionRecord`
    (Finding 1 corrective pass). A raw `store.record_transition(_transition(from_state="CREATED",
    to_state="AUTHORIZED"))` — this file's old pattern — no longer produces a resumable/
    evaluable workflow at all.
    """
    record = _authorization_record(
        workflow_id=workflow_id,
        stage_id=stage_id,
        repository_identity=repository_identity,
        repository_path=repository_path,
    )
    context = AuthorizationContext(
        workflow_id=record.workflow_id,
        repository_identity=record.repository_identity,
        stage_id=record.stage_id,
        planned_stage_branch=record.planned_stage_branch,
        baseline_branch=record.baseline_branch,
    )
    authorize(WorkflowStateMachine(), context, record, state_store=store)


def _seed_to_validating(
    store: StateStore, *, workflow_id: str = "wf-1", stage_id: str = "AUTO-002"
) -> None:
    _seed_authorized(store, workflow_id=workflow_id, stage_id=stage_id)
    for from_state, to_state in [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
    ]:
        store.record_transition(
            _transition(
                workflow_id=workflow_id, stage_id=stage_id, from_state=from_state, to_state=to_state
            )
        )


def _seed_to_implementing(
    store: StateStore, *, workflow_id: str = "wf-1", stage_id: str = "AUTO-002"
) -> None:
    _seed_authorized(store, workflow_id=workflow_id, stage_id=stage_id)
    for from_state, to_state in [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
    ]:
        store.record_transition(
            _transition(
                workflow_id=workflow_id, stage_id=stage_id, from_state=from_state, to_state=to_state
            )
        )


def _repair_cycle(
    store: StateStore,
    count: int,
    *,
    workflow_id: str = "wf-1",
    stage_id: str = "AUTO-002",
    triggering_state: WorkflowState = WorkflowState.VALIDATING,
) -> None:
    """Append `count` VALIDATING -> REPAIRING -> VALIDATING cycles, each backed by a durable,
    completed repair-attempt event (`record_repair_attempt_started`/`record_repair_attempt`) —
    matching what a real caller is now required to do, since `evaluate_repair_attempt` counts
    from `attempts.jsonl`, never from `StateTransitionRecord` history (Finding 8).
    """
    from agentos_workflow.orchestrator.engine import (
        record_repair_attempt as _record_repair_attempt,
    )
    from agentos_workflow.orchestrator.engine import (
        record_repair_attempt_started as _record_repair_attempt_started,
    )

    for i in range(count):
        attempt_number = i + 1
        store.record_transition(
            _transition(
                workflow_id=workflow_id,
                stage_id=stage_id,
                from_state=triggering_state.value,
                to_state="REPAIRING",
            )
        )
        # The reservation/completion pair is only ever recorded while the workflow is actually
        # in REPAIRING (the repair provider only ever runs there) — `state=triggering_state` is
        # audit metadata identifying which gate triggered this cycle, not the current position.
        _record_repair_attempt_started(
            workflow_id=workflow_id,
            stage_id=stage_id,
            state=triggering_state,
            attempt_number=attempt_number,
            attempt_limit=3,
            state_store=store,
            start_time=f"2026-07-24T10:{attempt_number:02d}:00+00:00",
        )
        _record_repair_attempt(
            workflow_id=workflow_id,
            stage_id=stage_id,
            state=triggering_state,
            attempt_number=attempt_number,
            state_store=store,
            completion_time=f"2026-07-24T10:{attempt_number:02d}:05+00:00",
        )
        store.record_transition(
            _transition(
                workflow_id=workflow_id,
                stage_id=stage_id,
                from_state="REPAIRING",
                to_state="VALIDATING",
            )
        )


# ---------------------------------------------------------------------------------------------
# evaluate_repair_attempt — first/subsequent/boundary/exhaustion
# ---------------------------------------------------------------------------------------------


class TestRepairAttemptProgression:
    def test_first_permitted_attempt_is_no_retry_required(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        result = evaluate_repair_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            attempt_limit=3,
            state_store=store,
        )
        assert result.outcome is RetryOutcome.NO_RETRY_REQUIRED
        assert result.retry_allowed is True
        assert result.attempt_count == 0
        assert result.next_allowed_state is WorkflowState.REPAIRING

    def test_second_permitted_attempt_is_retry_allowed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        _repair_cycle(store, 1)
        result = evaluate_repair_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            attempt_limit=3,
            state_store=store,
        )
        assert result.outcome is RetryOutcome.RETRY_ALLOWED
        assert result.attempt_count == 1
        assert result.next_allowed_state is WorkflowState.REPAIRING

    def test_third_permitted_attempt_at_exact_limit_boundary(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        _repair_cycle(store, 2)
        result = evaluate_repair_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            attempt_limit=3,
            state_store=store,
        )
        assert result.outcome is RetryOutcome.RETRY_ALLOWED
        assert result.attempt_count == 2
        assert result.retry_allowed is True

    def test_limit_exhausted_after_configured_max(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        _repair_cycle(store, 3)
        result = evaluate_repair_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            attempt_limit=3,
            state_store=store,
        )
        assert result.outcome is RetryOutcome.RETRY_LIMIT_EXHAUSTED
        assert result.retry_allowed is False
        assert result.attempt_count == 3
        assert result.next_allowed_state is WorkflowState.FAILED

    def test_qa_running_shares_the_same_per_workflow_counter_as_validating(
        self, tmp_path: Path
    ) -> None:
        # FAILURE_RECOVERY.md §1: "Maximum repair attempts: 3, per workflow" — not per-gate.
        store = _store(tmp_path)
        _seed_to_validating(store)
        _repair_cycle(store, 2)
        store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
        result = evaluate_repair_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.QA_RUNNING,
            attempt_limit=3,
            state_store=store,
        )
        assert result.attempt_count == 2
        assert result.outcome is RetryOutcome.RETRY_ALLOWED

    def test_attempt_limit_exceeded_in_persisted_history_rejected(self, tmp_path: Path) -> None:
        # The normal write-time guard (record_repair_attempt_started) already refuses a 4th
        # attempt; this test proves the *reconstruct-time* check independently catches 4 already-
        # persisted attempts too — written directly to attempts.jsonl, bypassing that guard, the
        # same way test_recording_beyond_fixed_limit_rejected proves it for initial-execution.
        store = _store(tmp_path)
        _seed_to_validating(store)
        attempts_path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for n in range(1, 5):  # 4 attempts, limit is 3
            for phase in ("started", "completed"):
                lines.append(
                    f'{{"workflow_id": "wf-1", "stage_id": "AUTO-002", "state": "VALIDATING", '
                    f'"kind": "repair", "attempt_number": {n}, "phase": "{phase}", '
                    f'"timestamp": "2026-07-24T10:{n:02d}:00+00:00"}}'
                )
        attempts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(AttemptLimitExceededError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )


class TestRepairAttemptRejections:
    def test_non_retryable_state_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        with pytest.raises(NotRetryableStateError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.PRECONDITIONS_CHECKED,
                attempt_limit=3,
                state_store=store,
            )

    def test_terminal_state_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store)
        store.record_transition(_transition(from_state="AUTHORIZED", to_state="FAILED"))
        with pytest.raises(WorkflowAlreadyTerminalError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_mismatched_reconstructed_state_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)  # actual state is IMPLEMENTING, not VALIDATING
        with pytest.raises(UnexpectedWorkflowStateError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_cross_stage_attempt_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store, stage_id="AUTO-002")
        with pytest.raises(WorkflowStageMismatchError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-999",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_cross_workflow_attempt_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store, workflow_id="wf-1")
        with pytest.raises(MissingPersistedStateError):
            evaluate_repair_attempt(
                workflow_id="wf-does-not-exist",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_corrupted_history_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        transitions_path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        with transitions_path.open("a", encoding="utf-8") as handle:
            handle.write("not valid json\n")
        with pytest.raises(CorruptedHistoryError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_inconsistent_history_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        # Gap: skips PRECONDITIONS_CHECKED entirely.
        # actor="human": isolates the missing-record case from the separate actor-shape check.
        store.record_transition(
            _transition(from_state="CREATED", to_state="AUTHORIZED", actor="human")
        )
        store.record_transition(
            _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
        )
        with pytest.raises(InconsistentHistoryError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_no_mutation_of_persisted_state_on_rejected_evaluation(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        before_transitions = store.read_transitions("wf-1")
        before_commands = store.read_command_executions("wf-1")
        with pytest.raises(WorkflowStageMismatchError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="wrong-stage",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )
        assert store.read_transitions("wf-1") == before_transitions
        assert store.read_command_executions("wf-1") == before_commands


# ---------------------------------------------------------------------------------------------
# reconstruct_initial_execution_attempts / record_initial_execution_attempt
# ---------------------------------------------------------------------------------------------


def _record_completed_attempt(
    store: StateStore,
    *,
    workflow_id: str = "wf-1",
    stage_id: str = "AUTO-002",
    state: WorkflowState,
    attempt_number: int,
    start_time: str = "2026-07-24T10:00:00+00:00",
    completion_time: str = "2026-07-24T10:00:01+00:00",
) -> None:
    """Reserve (STARTED) then complete (COMPLETED) one attempt — the now-mandatory two-step
    sequence Finding 6 requires; nothing in the production API accepts a completed outcome
    without a prior reservation.
    """
    record_initial_execution_attempt_started(
        workflow_id=workflow_id,
        stage_id=stage_id,
        state=state,
        attempt_number=attempt_number,
        state_store=store,
        start_time=start_time,
    )
    record_initial_execution_attempt(
        workflow_id=workflow_id,
        stage_id=stage_id,
        state=state,
        attempt_number=attempt_number,
        state_store=store,
        completion_time=completion_time,
    )


class TestInitialExecutionAttemptAccounting:
    def test_no_attempts_reconstructs_empty_list(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        attempts = reconstruct_initial_execution_attempts(
            "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
        )
        assert attempts == []

    def test_record_and_reconstruct_single_attempt(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=1)
        attempts = reconstruct_initial_execution_attempts(
            "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
        )
        assert [a.attempt_number for a in attempts] == [1]

    def test_completed_without_reservation_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(MissingAttemptReservationError):
            record_initial_execution_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=1,
                state_store=store,
                completion_time="2026-07-24T10:00:01+00:00",
            )

    def test_duplicate_started_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        with pytest.raises(DuplicateAttemptNumberError):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=1,
                state_store=store,
                start_time="2026-07-24T10:00:05+00:00",
            )

    def test_second_completion_for_same_attempt_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=1)
        with pytest.raises(DuplicateAttemptNumberError):
            record_initial_execution_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=1,
                state_store=store,
                completion_time="2026-07-24T10:00:05+00:00",
            )

    def test_skipped_attempt_number_rejected_at_reservation_time(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(SkippedAttemptNumberError):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=2,  # attempt 1 was never reserved
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )

    def test_corrupted_attempt_record_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        attempts_path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        attempts_path.write_text(
            '{"workflow_id": "wf-1", "stage_id": "AUTO-002", "state": "IMPLEMENTING", '
            '"kind": "initial_execution", "attempt_number": -1, "phase": "started", '
            '"timestamp": "2026-07-24T10:00:00+00:00"}\n',
            encoding="utf-8",
        )
        with pytest.raises(CorruptedAttemptRecordError):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_blank_line_in_attempts_file_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=1)
        attempts_path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        with attempts_path.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with pytest.raises(CorruptedAttemptRecordError):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_completed_without_started_on_disk_rejected_on_read(self, tmp_path: Path) -> None:
        # Defense in depth: even though normal writes can never produce this shape, a read must
        # still refuse to trust a tampered file that somehow contains one.
        store = _store(tmp_path)
        _seed_to_implementing(store)
        attempts_path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        attempts_path.write_text(
            '{"workflow_id": "wf-1", "stage_id": "AUTO-002", "state": "IMPLEMENTING", '
            '"kind": "initial_execution", "attempt_number": 1, "phase": "completed", '
            '"timestamp": "2026-07-24T10:00:00+00:00"}\n',
            encoding="utf-8",
        )
        with pytest.raises(MissingAttemptReservationError):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_cross_workflow_attempt_in_history_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        attempts_path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        # Physically stored under wf-1's file but claiming a different workflow_id inside.
        attempts_path.write_text(
            '{"workflow_id": "wf-other", "stage_id": "AUTO-002", "state": "IMPLEMENTING", '
            '"kind": "initial_execution", "attempt_number": 1, "phase": "started", '
            '"timestamp": "2026-07-24T10:00:00+00:00"}\n',
            encoding="utf-8",
        )
        with pytest.raises(InconsistentAttemptHistoryError):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_cross_stage_attempt_in_history_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        attempts_path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        attempts_path.write_text(
            '{"workflow_id": "wf-1", "stage_id": "AUTO-999", "state": "IMPLEMENTING", '
            '"kind": "initial_execution", "attempt_number": 1, "phase": "started", '
            '"timestamp": "2026-07-24T10:00:00+00:00"}\n',
            encoding="utf-8",
        )
        with pytest.raises(InconsistentAttemptHistoryError):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_recording_beyond_fixed_limit_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        for n in (1, 2, 3):
            _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=n)
        with pytest.raises(AttemptLimitExceededError):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=4,
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )

    def test_fourth_attempt_refused_even_if_caller_wants_a_larger_limit(
        self, tmp_path: Path
    ) -> None:
        # INITIAL_EXECUTION_ATTEMPT_LIMIT is a fixed module constant, not a caller-suppliable
        # parameter at all — there is no argument left to pass a larger value through.
        import inspect

        for fn in (
            record_initial_execution_attempt_started,
            record_initial_execution_attempt,
            reconstruct_initial_execution_attempts,
            evaluate_initial_execution_failure,
        ):
            assert "attempt_limit" not in inspect.signature(fn).parameters

    def test_restart_reconstruction_from_persisted_attempts_file(self, tmp_path: Path) -> None:
        writer_store = _store(tmp_path)
        _seed_to_implementing(writer_store)
        _record_completed_attempt(writer_store, state=WorkflowState.IMPLEMENTING, attempt_number=1)
        _record_completed_attempt(writer_store, state=WorkflowState.IMPLEMENTING, attempt_number=2)

        # A brand-new StateStore instance, as a resumed process would construct.
        resumed_store = _store(tmp_path)
        attempts = reconstruct_initial_execution_attempts(
            "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, resumed_store
        )
        assert [a.attempt_number for a in attempts] == [1, 2]

        result = _evaluate_initial_execution_failure(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            state_store=resumed_store,
            failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
        )
        assert result.attempt_count == 2
        assert result.outcome is RetryOutcome.RETRY_ALLOWED

    def test_concurrent_reservations_for_the_same_next_number_serialize(
        self, tmp_path: Path
    ) -> None:
        # Two real OS processes race to reserve attempt_number=1 for the same scope. Exactly one
        # must win; the other must observe a well-formed rejection — never both "ok" (which would
        # mean the read-validate-append sequence was not actually atomic).
        import multiprocessing as mp

        def _attempt(state_dir: str, audit_dir: str, result_queue: object) -> None:
            from pathlib import Path as _Path

            from agentos_workflow.orchestrator.engine import (
                DuplicateAttemptNumberError as _Dup,
            )
            from agentos_workflow.orchestrator.engine import (
                record_initial_execution_attempt_started as _start,
            )
            from agentos_workflow.orchestrator.state_store import StateStore as _StateStore

            local_store = _StateStore(
                state_directory=_Path(state_dir), audit_directory=_Path(audit_dir)
            )
            try:
                _start(
                    workflow_id="wf-1",
                    stage_id="AUTO-002",
                    state=WorkflowState.IMPLEMENTING,
                    attempt_number=1,
                    state_store=local_store,
                    start_time="2026-07-24T10:00:00+00:00",
                )
                result_queue.put("ok")  # type: ignore[attr-defined]
            except _Dup:
                result_queue.put("rejected")  # type: ignore[attr-defined]

        store = _store(tmp_path)
        _seed_to_implementing(store)
        ctx = mp.get_context("fork")
        result_queue = ctx.Queue()
        state_dir = str(tmp_path / "state")
        audit_dir = str(tmp_path / "audit")
        proc_a = ctx.Process(target=_attempt, args=(state_dir, audit_dir, result_queue))
        proc_b = ctx.Process(target=_attempt, args=(state_dir, audit_dir, result_queue))
        proc_a.start()
        proc_b.start()
        proc_a.join(timeout=10)
        proc_b.join(timeout=10)
        assert proc_a.exitcode == 0
        assert proc_b.exitcode == 0

        outcomes = {result_queue.get(timeout=5), result_queue.get(timeout=5)}
        assert outcomes == {"ok", "rejected"}
        scoped_lines = [
            line
            for line in (tmp_path / "state" / "wf-1" / "attempts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        assert len(scoped_lines) == 1


# ---------------------------------------------------------------------------------------------
# evaluate_initial_execution_failure — §5a item 1 (proven no side effect)
# ---------------------------------------------------------------------------------------------


class TestInitialExecutionProvenNoSideEffect:
    def test_first_attempt_no_retry_required(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        result = _evaluate_initial_execution_failure(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
        )
        assert result.outcome is RetryOutcome.NO_RETRY_REQUIRED
        assert result.next_allowed_state is None  # same-state retry, not a transition

    def test_exhaustion_recommends_failed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        for n in (1, 2, 3):
            _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=n)
        result = _evaluate_initial_execution_failure(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
        )
        assert result.outcome is RetryOutcome.RETRY_LIMIT_EXHAUSTED
        assert result.next_allowed_state is WorkflowState.FAILED


# ---------------------------------------------------------------------------------------------
# evaluate_initial_execution_failure — §5a items 2-6 (reconciliation)
# ---------------------------------------------------------------------------------------------


class TestReconciliation:
    def test_missing_evidence_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(MissingReconciliationEvidenceError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            )

    def test_unconfirmed_evidence_requires_reconciliation(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        result = _evaluate_initial_execution_failure(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(side_effect_confirmed=False),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_REQUIRED
        assert result.consistent is False
        assert result.next_allowed_state is None

    def test_confirmed_success_advances_to_forward_edge(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        result = _evaluate_initial_execution_failure(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](
                    succeeded=True, store=store
                ),
            ),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_SUCCESSFUL
        assert result.consistent is True
        assert result.next_allowed_state is WorkflowState.VALIDATING

    def test_confirmed_success_forward_edge_for_locally_verifiable_states(
        self, tmp_path: Path
    ) -> None:
        # Only IMPLEMENTING (ImplementationDiffEvidence) and READY_TO_COMMIT (CommitEvidence) are
        # independently verifiable from local Git/filesystem state alone (AUTO002-F07, Human
        # Owner decision 2026-07-27); COMMITTED (RemoteRefEvidence) and PUSHED (PullRequestEvidence)
        # describe remote/GitHub facts with no authorized local verifier and are covered
        # separately by test_remote_ref_evidence_fails_closed_without_verifier and
        # test_pull_request_evidence_fails_closed_without_verifier below.
        expected = {
            WorkflowState.IMPLEMENTING: WorkflowState.VALIDATING,
            WorkflowState.READY_TO_COMMIT: WorkflowState.COMMITTED,
        }
        for state, forward in expected.items():
            store = _store(tmp_path / state.value)
            _seed_authorized(store)
            store.record_transition(
                _transition(from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED")
            )
            store.record_transition(
                _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
            )
            store.record_transition(
                _transition(from_state="BRANCH_CREATED", to_state="IMPLEMENTING")
            )
            if state is not WorkflowState.IMPLEMENTING:
                store.record_transition(
                    _transition(from_state="IMPLEMENTING", to_state="VALIDATING")
                )
                store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
                store.record_transition(
                    _transition(from_state="QA_RUNNING", to_state="READY_TO_COMMIT")
                )
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
            assert result.next_allowed_state is forward

    def test_remote_ref_evidence_fails_closed_without_verifier(self, tmp_path: Path) -> None:
        # AUTO002-F07: RemoteRefEvidence describes remote/GitHub state AUTO-002 has no authorized
        # network-reaching observer for — a caller's claim alone can never confirm it, regardless
        # of internal self-consistency, so this must fail closed rather than advance.
        store = _store(tmp_path)
        _seed_to_implementing(store)
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
        store.record_transition(_transition(from_state="QA_RUNNING", to_state="READY_TO_COMMIT"))
        store.record_transition(_transition(from_state="READY_TO_COMMIT", to_state="COMMITTED"))
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.COMMITTED,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_remote_ref_evidence(succeeded=True),
                ),
            )

    def test_pull_request_evidence_fails_closed_without_verifier(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        for from_state, to_state in [
            ("IMPLEMENTING", "VALIDATING"),
            ("VALIDATING", "QA_RUNNING"),
            ("QA_RUNNING", "READY_TO_COMMIT"),
            ("READY_TO_COMMIT", "COMMITTED"),
            ("COMMITTED", "PUSHED"),
        ]:
            store.record_transition(_transition(from_state=from_state, to_state=to_state))
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.PUSHED,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_pull_request_evidence(succeeded=True),
                ),
            )

    def test_confirmed_failure_recoverable_only_from_implementing(self, tmp_path: Path) -> None:
        # WORKFLOW_STATES.md §5a item 4, verbatim: "no new IMPLEMENTING -> REPAIRING edge is
        # added" — a recoverable inconsistency proceeds forward via the existing
        # IMPLEMENTING -> VALIDATING edge; validation's own VALIDATING -> REPAIRING gate is what
        # actually engages repair if a real problem is found there.
        store = _store(tmp_path)
        _seed_to_implementing(store)
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

    def test_confirmed_failure_not_recoverable_is_unrecoverable(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
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

    def test_recoverable_evidence_rejected_for_non_implementing_state(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store)
        store.record_transition(
            _transition(from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED")
        )
        store.record_transition(
            _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
        )
        store.record_transition(_transition(from_state="BRANCH_CREATED", to_state="IMPLEMENTING"))
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
        store.record_transition(_transition(from_state="QA_RUNNING", to_state="READY_TO_COMMIT"))
        with pytest.raises(InconsistentAttemptHistoryError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.READY_TO_COMMIT,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=False,
                    recoverable=True,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.READY_TO_COMMIT](
                        succeeded=False
                    ),
                ),
            )

    def test_no_mutation_of_persisted_state_on_reconciliation(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        before_transitions = store.read_transitions("wf-1")
        before_commands = store.read_command_executions("wf-1")
        _evaluate_initial_execution_failure(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](
                    succeeded=True, store=store
                ),
            ),
        )
        assert store.read_transitions("wf-1") == before_transitions
        assert store.read_command_executions("wf-1") == before_commands

    def test_evidence_scope_mismatch_workflow_id_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(EvidenceScopeMismatchError) as exc_info:
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    workflow_id="wf-other",
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](succeeded=True),
                ),
            )
        assert exc_info.value.field == "workflow_id"

    def test_evidence_scope_mismatch_repository_identity_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(EvidenceScopeMismatchError) as exc_info:
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    repository_identity="github.com/org/wrong-repo",
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](succeeded=True),
                ),
            )
        assert exc_info.value.field == "repository_identity"

    def test_evidence_scope_mismatch_repository_path_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(EvidenceScopeMismatchError) as exc_info:
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    repository_path="/home/user/wrong-repo",
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](succeeded=True),
                ),
            )
        assert exc_info.value.field == "repository_path"

    def test_evidence_scope_mismatch_stage_id_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(EvidenceScopeMismatchError) as exc_info:
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    stage_id="AUTO-999",
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](succeeded=True),
                ),
            )
        assert exc_info.value.field == "stage_id"

    def test_wrong_operation_evidence_type_rejected(self, tmp_path: Path) -> None:
        # A caller supplies CommitEvidence (READY_TO_COMMIT's shape) while evaluating IMPLEMENTING
        # (which requires ImplementationDiffEvidence) — wrong operation, must fail closed.
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(EvidenceOperationMismatchError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_commit_evidence(succeeded=True),
                ),
            )

    def test_fabricated_sha_reference_rejected_by_format(self, tmp_path: Path) -> None:
        # "commit_sha:deadbeef" — the exact kind of unvalidated label the old design accepted —
        # is not a well-formed 40-character git SHA and must be rejected at the schema level.
        with pytest.raises(ValidationError):
            CommitEvidence(
                commit_sha="deadbeef",
                expected_tree_sha=_TREE_SHA,
                observed_tree_sha=_TREE_SHA,
            )

    def test_remote_ref_wrong_sha_rejected(self, tmp_path: Path) -> None:
        # The remote ref points to a different SHA than expected — reconciliation must not
        # advance the workflow, and the caller cannot simultaneously claim success.
        store = _store(tmp_path)
        _seed_to_implementing(store)
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
        store.record_transition(_transition(from_state="QA_RUNNING", to_state="READY_TO_COMMIT"))
        store.record_transition(_transition(from_state="READY_TO_COMMIT", to_state="COMMITTED"))
        with pytest.raises(EvidenceConsistencyError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.COMMITTED,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,  # claims success
                    evidence=RemoteRefEvidence(
                        remote_ref="refs/heads/feature/auto-002-orchestrator-state-machine",
                        expected_sha=_COMMIT_SHA,
                        observed_sha=_OTHER_SHA,  # but the remote actually points elsewhere
                    ),
                ),
            )

    def test_pr_wrong_base_or_head_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError):
            PullRequestEvidence(
                pr_number=1,
                head_branch="",  # blank — an invalid PR identity
                base_branch="main",
                expected_head_sha=_COMMIT_SHA,
                observed_head_sha=_COMMIT_SHA,
            )

    def test_claimed_success_disagreeing_with_evidence_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
        store.record_transition(_transition(from_state="QA_RUNNING", to_state="READY_TO_COMMIT"))
        with pytest.raises(EvidenceConsistencyError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.READY_TO_COMMIT,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=True,
                    evidence=_commit_evidence(succeeded=False),  # expected != observed
                ),
            )

    def test_claimed_failure_disagreeing_with_matching_evidence_rejected(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        store.record_transition(_transition(from_state="VALIDATING", to_state="QA_RUNNING"))
        store.record_transition(_transition(from_state="QA_RUNNING", to_state="READY_TO_COMMIT"))
        with pytest.raises(EvidenceConsistencyError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.READY_TO_COMMIT,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=_evidence(
                    side_effect_confirmed=True,
                    side_effect_succeeded=False,
                    evidence=_commit_evidence(succeeded=True),  # expected == observed
                ),
            )

    def test_valid_evidence_advances_exactly_one_documented_edge(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        result = _evaluate_initial_execution_failure(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](
                    succeeded=True, store=store
                ),
            ),
        )
        # Exactly one edge recommended, and it is the sole documented forward edge for this state.
        assert result.next_allowed_state is WorkflowState.VALIDATING


class TestReconciliationEvidenceShape:
    def test_succeeded_without_confirmed_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _evidence(side_effect_confirmed=False, side_effect_succeeded=True)

    def test_confirmed_without_succeeded_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _evidence(side_effect_confirmed=True)

    def test_recoverable_without_failure_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                recoverable=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](succeeded=True),
            )


class TestNoCommandExecution:
    def test_engine_module_imports_no_execution_capability(self) -> None:
        # An AST check, not a substring search: this module's own docstrings legitimately
        # discuss "a git/gh subprocess" in prose, which a naive text search would misfire on.
        # `os`/`pathlib` are imported for ordinary, non-executing filesystem bookkeeping (atomic
        # authorization-record persistence) — the same kind of usage lock.py and state_store.py
        # already have; what actually matters is whether *subprocess* (any use of it always
        # means spawning a process) or a specific process-spawning call from `os`/`pty` appears.
        import ast

        import agentos_workflow.orchestrator.engine as engine_module

        source = engine_module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "subprocess", alias.name
            elif isinstance(node, ast.ImportFrom):
                assert node.module is None or node.module.split(".")[0] != "subprocess", node.module
            elif isinstance(node, ast.Attribute):
                owner = node.value
                if isinstance(owner, ast.Name) and owner.id in {"os", "pty"}:
                    assert node.attr not in {
                        "system",
                        "popen",
                        "spawnl",
                        "spawnle",
                        "spawnlp",
                        "spawnlpe",
                        "spawnv",
                        "spawnve",
                        "spawnvp",
                        "spawnvpe",
                        "execl",
                        "execle",
                        "execlp",
                        "execlpe",
                        "execv",
                        "execve",
                        "execvp",
                        "execvpe",
                        "fork",
                        "posix_spawn",
                        "spawn",
                    }, f"{owner.id}.{node.attr}"


# ---------------------------------------------------------------------------------------------
# Durable retry accounting for uncertain execution (stage contract repair requirement 6):
# record_initial_execution_attempt_started / has_unreconciled_initial_execution_attempt /
# evaluate_initial_execution_failure's refusal of a blind PROVEN_NO_SIDE_EFFECT retry.
# ---------------------------------------------------------------------------------------------


class TestUnreconciledAttemptDetection:
    def test_no_attempts_is_not_unreconciled(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert (
            has_unreconciled_initial_execution_attempt(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )
            is False
        )

    def test_completed_only_attempt_is_not_unreconciled(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=1)
        assert (
            has_unreconciled_initial_execution_attempt(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )
            is False
        )

    def test_started_without_completed_is_unreconciled(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        assert (
            has_unreconciled_initial_execution_attempt(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )
            is True
        )

    def test_started_then_completed_is_no_longer_unreconciled(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        record_initial_execution_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            completion_time="2026-07-24T10:00:05+00:00",
        )
        assert (
            has_unreconciled_initial_execution_attempt(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )
            is False
        )

    def test_started_attempt_reconstructs_after_process_restart(self, tmp_path: Path) -> None:
        # The durable "started" marker must survive a crash: a fresh StateStore instance, as a
        # resumed process would construct, must still see it as unreconciled.
        writer_store = _store(tmp_path)
        _seed_to_implementing(writer_store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=writer_store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        resumed_store = _store(tmp_path)
        assert (
            has_unreconciled_initial_execution_attempt(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, resumed_store
            )
            is True
        )

    def test_started_records_do_not_count_toward_completed_attempts(self, tmp_path: Path) -> None:
        # requirement 6/8's shared principle: a STARTED-only record is not a completed attempt.
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        attempts = reconstruct_initial_execution_attempts(
            "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
        )
        assert attempts == []

    def test_proven_no_side_effect_refused_while_unreconciled(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        with pytest.raises(UnreconciledAttemptError):
            _evaluate_initial_execution_failure(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
            )

    def test_possible_side_effect_still_available_while_unreconciled(self, tmp_path: Path) -> None:
        # The correct path for an unreconciled attempt remains open: POSSIBLE_SIDE_EFFECT with
        # real evidence is exactly how the caller is expected to resolve this.
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        result = _evaluate_initial_execution_failure(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=_evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](
                    succeeded=True, store=store
                ),
            ),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_SUCCESSFUL

    def test_started_record_numbering_reuses_the_same_numbering_guard(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        with pytest.raises(SkippedAttemptNumberError):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=2,  # attempt 1 was never recorded at all
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )

    def test_started_record_beyond_limit_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        for n in (1, 2, 3):
            _record_completed_attempt(store, state=WorkflowState.IMPLEMENTING, attempt_number=n)
        with pytest.raises(AttemptLimitExceededError):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=4,
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )


# ---------------------------------------------------------------------------------------------
# Strengthened reconciliation evidence (stage contract repair requirement 7): a confirmed claim
# must cite concrete repository evidence, not a bare boolean.
# ---------------------------------------------------------------------------------------------


class TestReconciliationEvidenceReference:
    def test_typed_evidence_required_once_confirmed(self) -> None:
        with pytest.raises(ValidationError, match="evidence"):
            _evidence(side_effect_confirmed=True, side_effect_succeeded=True, evidence=None)

    def test_typed_evidence_must_be_absent_when_confirmed_is_false(self) -> None:
        with pytest.raises(ValidationError, match="evidence"):
            _evidence(
                side_effect_confirmed=False,
                evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.IMPLEMENTING](succeeded=True),
            )


# ---------------------------------------------------------------------------------------------
# Finding 1 corrective pass: every retry/reconciliation/repair-attempt public entry point in this
# module reconstructs workflow state via the same authorization-gated `_replay_history`
# `resume_workflow` uses (never the removed, unhardened `_replay_history_state_only`). A history
# whose CREATED -> AUTHORIZED edge is not backed by a genuine, matching, persisted
# AuthorizationRecord is rejected at every one of these public functions, not merely at
# `resume_workflow`.
# ---------------------------------------------------------------------------------------------


def _tamper_authorization_record(
    store: StateStore, path_workflow_id: str, **overrides: object
) -> None:
    """Persist a genuine record via authorize() (`_seed_to_implementing`/`_seed_to_validating`
    already did this), then directly overwrite it — the only way to produce a persisted record
    that disagrees with the persisted history that originally produced it, since `authorize()`
    itself always writes a self-consistent pair. `path_workflow_id` always names the on-disk
    *file location* (matching the persisted history it's paired with) — pass a `workflow_id`
    override in `overrides` to make the tampered record's own *content* disagree with that
    location.
    """
    overrides.setdefault("workflow_id", path_workflow_id)
    defaults: dict[str, object] = _authorization_record().model_dump()
    defaults.update(overrides)
    tampered = AuthorizationRecord.model_validate(defaults)
    (store.state_directory / path_workflow_id / "authorization.json").write_text(
        tampered.model_dump_json(), encoding="utf-8"
    )


class TestFinding1CorrectivePassAcrossRetryAPIs:
    """Confirmed remaining bypasses 2/3 from the Human Owner's corrective-pass review: the retry/
    reconciliation section used a second, unhardened replay helper
    (`_replay_history_state_only`) that accepted a caller-fabricated `CREATED -> AUTHORIZED`
    `StateTransitionRecord` with no `StateStore` and no persisted `AuthorizationRecord` at all.
    That helper no longer exists; every function here now goes through the same hardened
    `_replay_history` `resume_workflow` uses, so a workflow whose authorization can't be verified
    is rejected identically everywhere, not just on resume.
    """

    def test_evaluate_repair_attempt_rejects_missing_authorization_record(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        # Raw, unauthorized history — no authorize() call, no authorization.json.
        # actor="human": isolates the missing-record case from the separate actor-shape check.
        store.record_transition(
            _transition(from_state="CREATED", to_state="AUTHORIZED", actor="human")
        )
        store.record_transition(
            _transition(from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED")
        )
        store.record_transition(
            _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
        )
        store.record_transition(_transition(from_state="BRANCH_CREATED", to_state="IMPLEMENTING"))
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        from agentos_workflow.orchestrator.engine import MissingAuthorizationRecordError

        with pytest.raises(MissingAuthorizationRecordError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_evaluate_repair_attempt_rejects_malformed_authorization_record(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        (store.state_directory / "wf-1" / "authorization.json").write_text(
            "not valid json", encoding="utf-8"
        )
        from agentos_workflow.orchestrator.engine import CorruptedAuthorizationRecordError

        with pytest.raises(CorruptedAuthorizationRecordError):
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )

    def test_evaluate_repair_attempt_rejects_record_for_another_workflow(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        _tamper_authorization_record(store, "wf-1", workflow_id="wf-tampered")
        from agentos_workflow.orchestrator.engine import AuthorizationBindingDriftError

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )
        assert exc_info.value.field == "workflow_id"

    def test_evaluate_repair_attempt_rejects_record_for_another_stage(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        _tamper_authorization_record(store, "wf-1", stage_id="AUTO-099")
        from agentos_workflow.orchestrator.engine import AuthorizationBindingDriftError

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )
        assert exc_info.value.field == "stage_id"

    def test_evaluate_repair_attempt_rejects_record_for_another_repository_identity(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        _tamper_authorization_record(
            store, "wf-1", repository_identity="github.com/org/some-other-repo"
        )
        from agentos_workflow.orchestrator.engine import AuthorizationBindingDriftError

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            evaluate_repair_attempt(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_limit=3,
                state_store=store,
            )
        assert exc_info.value.field == "repository_identity"

    def test_evaluate_initial_execution_failure_rejects_missing_authorization_record(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        # actor="human": isolates the missing-record case from the separate actor-shape check.
        store.record_transition(
            _transition(from_state="CREATED", to_state="AUTHORIZED", actor="human")
        )
        store.record_transition(
            _transition(from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED")
        )
        store.record_transition(
            _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
        )
        store.record_transition(_transition(from_state="BRANCH_CREATED", to_state="IMPLEMENTING"))
        from agentos_workflow.orchestrator.engine import MissingAuthorizationRecordError

        with pytest.raises(MissingAuthorizationRecordError):
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
            )

    def test_evaluate_initial_execution_failure_rejects_record_for_another_workflow(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        _tamper_authorization_record(store, "wf-1", workflow_id="wf-tampered")
        from agentos_workflow.orchestrator.engine import AuthorizationBindingDriftError

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _evaluate_initial_execution_failure(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT,
            )
        assert exc_info.value.field == "workflow_id"

    def test_record_repair_attempt_started_rejects_missing_authorization_record(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        # actor="human": isolates the missing-record case from the separate actor-shape check.
        store.record_transition(
            _transition(from_state="CREATED", to_state="AUTHORIZED", actor="human")
        )
        store.record_transition(
            _transition(from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED")
        )
        store.record_transition(
            _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
        )
        store.record_transition(_transition(from_state="BRANCH_CREATED", to_state="IMPLEMENTING"))
        store.record_transition(_transition(from_state="IMPLEMENTING", to_state="VALIDATING"))
        store.record_transition(_transition(from_state="VALIDATING", to_state="REPAIRING"))
        from agentos_workflow.orchestrator.engine import (
            MissingAuthorizationRecordError,
            record_repair_attempt_started,
        )

        with pytest.raises(MissingAuthorizationRecordError):
            record_repair_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_number=1,
                attempt_limit=3,
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )

    def test_record_repair_attempt_started_rejects_record_for_another_repository_identity(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        store.record_transition(_transition(from_state="VALIDATING", to_state="REPAIRING"))
        _tamper_authorization_record(
            store, "wf-1", repository_identity="github.com/org/some-other-repo"
        )
        from agentos_workflow.orchestrator.engine import (
            AuthorizationBindingDriftError,
            record_repair_attempt_started,
        )

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            record_repair_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.VALIDATING,
                attempt_number=1,
                attempt_limit=3,
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )
        assert exc_info.value.field == "repository_identity"

    def test_record_initial_execution_attempt_started_rejects_missing_authorization_record(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        # actor="human": isolates the missing-record case from the separate actor-shape check.
        store.record_transition(
            _transition(from_state="CREATED", to_state="AUTHORIZED", actor="human")
        )
        store.record_transition(
            _transition(from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED")
        )
        store.record_transition(
            _transition(from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED")
        )
        store.record_transition(_transition(from_state="BRANCH_CREATED", to_state="IMPLEMENTING"))
        from agentos_workflow.orchestrator.engine import MissingAuthorizationRecordError

        with pytest.raises(MissingAuthorizationRecordError):
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=1,
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )

    def test_legitimate_evaluate_repair_attempt_still_succeeds(self, tmp_path: Path) -> None:
        """Positive control: a genuinely authorized workflow is unaffected by any of the above."""
        store = _store(tmp_path)
        _seed_to_validating(store)
        result = evaluate_repair_attempt(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            attempt_limit=3,
            state_store=store,
        )
        assert result.outcome is RetryOutcome.NO_RETRY_REQUIRED

    def test_legitimate_record_repair_attempt_started_still_succeeds(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_validating(store)
        store.record_transition(_transition(from_state="VALIDATING", to_state="REPAIRING"))
        from agentos_workflow.orchestrator.engine import record_repair_attempt_started

        record_repair_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            attempt_number=1,
            attempt_limit=3,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )  # must not raise

    def test_typed_evidence_accepted_when_confirmed_and_present(self) -> None:
        evidence = _evidence(
            side_effect_confirmed=True,
            side_effect_succeeded=True,
            evidence=_EVIDENCE_FACTORY_BY_STATE[WorkflowState.PUSHED](succeeded=True),
        )
        assert isinstance(evidence.evidence, PullRequestEvidence)
        assert evidence.evidence.pr_number == 1

    def test_a_bare_string_label_is_never_accepted_as_evidence(self) -> None:
        # A caller may not simply pass a string where the typed evidence object belongs — this
        # is Finding 7's core requirement: "a string label alone must never authorize
        # advancement."
        with pytest.raises(ValidationError):
            _evidence(
                side_effect_confirmed=True,
                side_effect_succeeded=True,
                evidence="pr_url:https://github.com/org/repo/pull/1",
            )


def _reserve_attempt_1_in_subprocess(
    state_directory_str: str,
    audit_directory_str: str,
    start_barrier: "mp.synchronize.Barrier",
    result_queue: "mp.queues.Queue[str]",
) -> None:
    """Run in a real, separate OS process. Both processes race to reserve
    initial-execution attempt_number=1 for the same workflow/state after synchronizing on a
    barrier, so their attempts to acquire `_held_attempts_lock` genuinely overlap.
    """
    store = StateStore(
        state_directory=Path(state_directory_str), audit_directory=Path(audit_directory_str)
    )
    start_barrier.wait(timeout=10)
    try:
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        result_queue.put("succeeded")
    except DuplicateAttemptNumberError:
        result_queue.put("duplicate_rejected")
    except Exception as exc:  # pragma: no cover - diagnostic only on unexpected failure
        result_queue.put(f"unexpected:{type(exc).__name__}:{exc}")


class TestAUTO002F06AttemptAccountingHardening:
    """AUTO002-F06: three defects in `agentos_workflow/orchestrator/engine.py`'s retry-attempt
    bookkeeping, found during fresh-session reconciliation and independently reproduced before
    any fix: (1) `_append_attempt_record_unlocked` performed zero `fsync` calls, unlike every
    other durable append in this codebase; (2) `_scoped_attempts` filtered by `kind`/`state`
    before checking `workflow_id`/`stage_id` ownership, so a foreign-workflow record could hide
    undetected as long as its kind/state didn't match whatever query happened to be running; (3)
    `_read_persisted_attempts` had no terminal-newline check, so a crash that lost only the final
    record's trailing newline byte (JSON content otherwise complete) was silently accepted as a
    genuine, durable record.
    """

    def test_attempt_reservation_append_is_fsynced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        calls: list[int] = []
        real_fsync = os.fsync

        def _tracking_fsync(fd: int) -> None:
            calls.append(fd)
            real_fsync(fd)

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.engine.os.fsync", _tracking_fsync)
            record_initial_execution_attempt_started(
                workflow_id="wf-1",
                stage_id="AUTO-002",
                state=WorkflowState.IMPLEMENTING,
                attempt_number=1,
                state_store=store,
                start_time="2026-07-24T10:00:00+00:00",
            )
        # One fsync for the file, one for the containing directory (mirrors state_store.py's
        # own durable-append discipline).
        assert len(calls) >= 2

    def test_ownership_is_validated_before_kind_state_filtering(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        # A foreign-workflow record whose kind/state does *not* match the query below — under
        # the old filter-then-check ordering, this would be `continue`d away and never trigger
        # the ownership check at all.
        path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        foreign = RetryAttemptRecord(
            workflow_id="wf-INJECTED-FOREIGN",
            stage_id="AUTO-002",
            state=WorkflowState.VALIDATING,
            kind=AttemptKind.REPAIR,
            attempt_number=1,
            phase=AttemptPhase.COMPLETED,
            timestamp="2026-07-24T10:00:00+00:00",
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(foreign.model_dump_json() + "\n")

        with pytest.raises(InconsistentAttemptHistoryError):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )
        with pytest.raises(InconsistentAttemptHistoryError):
            has_unreconciled_initial_execution_attempt(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_missing_terminal_newline_is_rejected_as_torn_append(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        record_initial_execution_attempt_started(
            workflow_id="wf-1",
            stage_id="AUTO-002",
            state=WorkflowState.IMPLEMENTING,
            attempt_number=1,
            state_store=store,
            start_time="2026-07-24T10:00:00+00:00",
        )
        path = tmp_path / "state" / "wf-1" / "attempts.jsonl"
        path.write_bytes(path.read_bytes().rstrip(b"\n"))

        with pytest.raises(CorruptedAttemptRecordError, match="terminal newline"):
            reconstruct_initial_execution_attempts(
                "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
            )

    def test_concurrent_processes_reserving_the_same_attempt_number_have_exactly_one_winner(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store)
        ctx = mp.get_context("fork")
        barrier = ctx.Barrier(2)
        result_queue: mp.queues.Queue[str] = ctx.Queue()
        state_directory = str(tmp_path / "state")
        audit_directory = str(tmp_path / "audit")
        proc_a = ctx.Process(
            target=_reserve_attempt_1_in_subprocess,
            args=(state_directory, audit_directory, barrier, result_queue),
        )
        proc_b = ctx.Process(
            target=_reserve_attempt_1_in_subprocess,
            args=(state_directory, audit_directory, barrier, result_queue),
        )
        proc_a.start()
        proc_b.start()
        proc_a.join(timeout=30)
        proc_b.join(timeout=30)
        assert proc_a.exitcode == 0
        assert proc_b.exitcode == 0

        results = {result_queue.get(timeout=5), result_queue.get(timeout=5)}
        assert results == {"succeeded", "duplicate_rejected"}

        # Exactly one STARTED record for attempt 1 must exist — no interleaving, no double
        # reservation.
        scoped = reconstruct_initial_execution_attempts(
            "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
        )
        assert has_unreconciled_initial_execution_attempt(
            "wf-1", "AUTO-002", WorkflowState.IMPLEMENTING, store
        )  # the winner's STARTED record has no matching COMPLETED yet
        assert scoped == []  # nothing *completed* yet — the winner only reserved, didn't finish
