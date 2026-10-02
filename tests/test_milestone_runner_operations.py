"""AUTO-018 section 8: deterministic operation identity and the ordered phase ladder.

Section 12 obligations covered here at the journal level: T-OP-ID, the phase-order half of
T-OP-ORDER, T-OP-SPAWN's attempt rules, T-OP-INVALID's "no accepted-success" rule, T-OP-APPLIED
and T-HOSTILE-IO for the operation artifact types. The end-to-end halves -- a counting fake for
every role driven by the real application -- live in `test_milestone_runner_application.py`.
"""

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from ai_workflow_engine.milestone_runner.application import transition_to
from ai_workflow_engine.milestone_runner.events import (
    EventChainBroken,
    EventStore,
    LifecycleEventType,
    MutationAction,
    MutationCommand,
    OperationRecordConflict,
    OperationRecordInvalid,
    PlannedChange,
    RejectionSource,
    ResultEvidence,
)
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    MilestoneRunnerModel,
    ProviderRole,
    RunRecord,
    RunStatus,
    StopReason,
)
from ai_workflow_engine.milestone_runner.operations import (
    MAX_OPERATION_ATTEMPTS,
    AdapterIdentity,
    DispatchReceipt,
    ExecutionOutcome,
    OperationHandle,
    OperationPhase,
    OperationStep,
    OperationStepKind,
    PersistenceKind,
    ReceiptKind,
    ValidatedResult,
    ValidationVerdict,
    operation_artifact_path,
    operation_id,
    provider_step,
    reopening_count,
)
from ai_workflow_engine.milestone_runner.providers.base import MAX_SPAWN_RETRY_ATTEMPTS
from ai_workflow_engine.milestone_runner.results import MilestoneReportStatus, MilestoneResult
from ai_workflow_engine.milestone_runner.state import RunStateStore

IDENTITY = "demo-repo--2059e82cffa9"
RUN_ID = "auto018-20260930T120000Z-0000e018"
STAGE_START_ID = "5" * 64
T0 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


def stamp(offset: int = 0) -> str:
    return (T0 + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------
# T-OP-ID
# --------------------------------------------------------------------------------------


def independent_id(run_id: str, kind: str, cycle: int, role: str, slot: str) -> str:
    return hashlib.sha256(f"{run_id}|{kind}|{cycle}|{role}|{slot}".encode()).hexdigest()


class TestOperationIdentity:
    """T-OP-ID: fixed vectors per role and slot; stable; distinct; attempts do not change it."""

    VECTORS: ClassVar[list[tuple[ProviderRole, int, str]]] = [
        (ProviderRole.IMPLEMENTATION, 0, "AUTO-099-M01:0"),
        (ProviderRole.IMPLEMENTATION, 0, "AUTO-099-M01:1"),
        (ProviderRole.IMPLEMENTATION, 0, "AUTO-099-M02:0"),
        (ProviderRole.REVIEW, 0, "discovery"),
        (ProviderRole.CORRECTION, 1, "correction"),
        (ProviderRole.CLOSURE, 1, "closure"),
    ]

    @pytest.mark.parametrize("role, cycle, slot", VECTORS)
    def test_the_identity_is_the_master_plan_derivation(
        self, role: ProviderRole, cycle: int, slot: str
    ) -> None:
        step = OperationStep(
            step_kind=OperationStepKind.PROVIDER, cycle_no=cycle, role=role, slot=slot
        )
        expected = independent_id(RUN_ID, "provider", cycle, role.value, slot)
        assert operation_id(RUN_ID, step) == expected
        assert operation_id(RUN_ID, step) == operation_id(RUN_ID, step)

    def test_the_pinned_vector_never_drifts(self) -> None:
        step = OperationStep(
            step_kind=OperationStepKind.PROVIDER,
            cycle_no=0,
            role=ProviderRole.REVIEW,
            slot="discovery",
        )
        assert (
            operation_id("auto016-run-0001", step)
            == hashlib.sha256(b"auto016-run-0001|provider|0|REVIEW|discovery").hexdigest()
        )

    def test_every_vector_is_distinct(self) -> None:
        identities = {
            operation_id(
                RUN_ID,
                OperationStep(
                    step_kind=OperationStepKind.PROVIDER, cycle_no=cycle, role=role, slot=slot
                ),
            )
            for role, cycle, slot in self.VECTORS
        }
        assert len(identities) == len(self.VECTORS)

    @pytest.mark.parametrize(
        "role, cycle, slot",
        [
            (ProviderRole.REVIEW, 1, "discovery"),
            (ProviderRole.REVIEW, 0, "correction"),
            (ProviderRole.CORRECTION, 0, "correction"),
            (ProviderRole.CLOSURE, 2, "closure"),
            (ProviderRole.IMPLEMENTATION, 1, "AUTO-099-M01:0"),
            (ProviderRole.IMPLEMENTATION, 0, "AUTO-099-M01"),
            (ProviderRole.IMPLEMENTATION, 0, "AUTO-099-M01:01"),
            (ProviderRole.IMPLEMENTATION, 0, "not-a-milestone:0"),
            (ProviderRole.IMPLEMENTATION, 0, "AUTO-099-M01|x:0"),
        ],
    )
    def test_no_tuple_expresses_a_new_cycle_or_slot(
        self, role: ProviderRole, cycle: int, slot: str
    ) -> None:
        with pytest.raises(ValidationError):
            OperationStep(
                step_kind=OperationStepKind.PROVIDER, cycle_no=cycle, role=role, slot=slot
            )

    def test_the_reopening_count_comes_from_durable_entries(self, tmp_path: Path) -> None:
        from ai_workflow_engine.milestone_runner.models import (
            RecoveryCommand,
            RecoveryLedgerEntry,
        )

        record = base_record(tmp_path, RunStatus.IMPLEMENTING)
        entry = RecoveryLedgerEntry(
            command=RecoveryCommand.REOPEN_MILESTONE,
            reason="reopened",
            recorded_at=stamp(),
            pre_state=RunStatus.MILESTONE_FAILED,
            post_state=RunStatus.IMPLEMENTING,
            branch="main",
            head_sha="8" * 40,
            milestone_id="AUTO-099-M01",
            human_owner_ruling="ruled",
        )
        reopened = RunRecord.model_validate(
            {**record.model_dump(), "reopenings": [entry.model_dump()]}
        )
        assert reopening_count(record, "AUTO-099-M01") == 0
        assert reopening_count(reopened, "AUTO-099-M01") == 1
        assert reopening_count(reopened, "AUTO-099-M02") == 0
        first = provider_step(record, ProviderRole.IMPLEMENTATION, "AUTO-099-M01")
        second = provider_step(reopened, ProviderRole.IMPLEMENTATION, "AUTO-099-M01")
        assert first.slot == "AUTO-099-M01:0" and second.slot == "AUTO-099-M01:1"
        assert operation_id(RUN_ID, first) != operation_id(RUN_ID, second)

    def test_the_attempt_bound_is_the_existing_retry_ceiling(self) -> None:
        assert MAX_OPERATION_ATTEMPTS == MAX_SPAWN_RETRY_ATTEMPTS == 3
        assert operation_artifact_path("a" * 64, "dispatch-intent.json", attempt=3).endswith(
            "attempts/0003/dispatch-intent.json"
        )
        with pytest.raises(ValueError):
            operation_artifact_path("a" * 64, "dispatch-intent.json", attempt=4)


# --------------------------------------------------------------------------------------
# Artifact schemas
# --------------------------------------------------------------------------------------


class TestArtifactSchemas:
    def test_a_receipt_never_carries_an_invented_process_id(self) -> None:
        common: dict[str, Any] = dict(
            schema_version=1,
            pins=dict(
                repository_identity=IDENTITY,
                stage_id="AUTO-099",
                run_id=RUN_ID,
                contract_sha256="7" * 64,
                policy_digest="6" * 64,
                stage_start_id=STAGE_START_ID,
            ),
            operation_id="a" * 64,
            attempt=1,
            intent_sha256="b" * 64,
            observed_started_at=stamp(),
        )

        def receipt(**fields: Any) -> DispatchReceipt:
            return DispatchReceipt.model_validate_json(json.dumps({**common, **fields}))

        receipt(kind="SCRIPTED_FAKE_ACKNOWLEDGMENT")
        receipt(kind="LOCAL_PROCESS", process_id=42)
        with pytest.raises(ValidationError):
            receipt(kind="SCRIPTED_FAKE_ACKNOWLEDGMENT", process_id=42)
        with pytest.raises(ValidationError):
            receipt(kind="LOCAL_PROCESS")

    def test_an_invalid_result_never_carries_a_typed_result(self) -> None:
        result = MilestoneResult(milestone="AUTO-099-M01", status=MilestoneReportStatus.COMPLETE)
        common: dict[str, Any] = dict(
            schema_version=1,
            pins=dict(
                repository_identity=IDENTITY,
                stage_id="AUTO-099",
                run_id=RUN_ID,
                contract_sha256="7" * 64,
                policy_digest="6" * 64,
                stage_start_id=STAGE_START_ID,
            ),
            operation_id="a" * 64,
            attempt=1,
            role="IMPLEMENTATION",
            raw_result_sha256="b" * 64,
            recorded_at=stamp(),
        )

        def validated(**fields: Any) -> ValidatedResult:
            return ValidatedResult.model_validate_json(json.dumps({**common, **fields}))

        typed = result.model_dump(mode="json")
        validated(verdict="VALID", milestone_result=typed)
        with pytest.raises(ValidationError):
            validated(verdict="INVALID", milestone_result=typed)
        with pytest.raises(ValidationError):
            validated(verdict="VALID")
        with pytest.raises(ValidationError):
            validated(
                verdict="VALID", milestone_result=typed, review_result={"verdict": "APPROVED"}
            )


# --------------------------------------------------------------------------------------
# The journal on a real store
# --------------------------------------------------------------------------------------


def base_record(repository: Path, state: RunStatus) -> RunRecord:
    return RunRecord(
        schema_version=2,
        run_id=RUN_ID,
        repository_root=str(repository),
        repository_identity=IDENTITY,
        expected_branch="main",
        baseline_sha="8" * 40,
        contract_sha256="7" * 64,
        workflow_state=state,
        created_at=stamp(),
        updated_at=stamp(),
        policy_digest="6" * 64,
        stage_start_id=STAGE_START_ID,
        current_milestone="AUTO-099-M01" if state is not RunStatus.IDLE else None,
    )


@pytest.fixture
def journal_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[RunStateStore, RunLock, EventStore]]:
    from ai_workflow_engine.milestone_runner.events import EventPins

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    repository = tmp_path / "worktree"
    repository.mkdir()
    store = RunStateStore.pin(repository_id=IDENTITY, run_id=RUN_ID, repository_root=repository)
    authority = store.artifact_root / "stage-starts"
    authority.mkdir()
    for suffix in (".json", ".binding.json", ".consumed.json"):
        (authority / f"{STAGE_START_ID}{suffix}").write_text("{}", encoding="utf-8")
    store.policy_path.write_text("{}", encoding="utf-8")
    lock = RunLock(
        run_id=RUN_ID, repository_identity=IDENTITY, artifact_root=store.artifact_root
    ).bind_repository_root(repository)
    lock.acquire()
    try:
        events = store.begin_lifecycle(
            lock,
            EventPins(
                repository_identity=IDENTITY,
                stage_id="AUTO-099",
                run_id=RUN_ID,
                contract_sha256="7" * 64,
                policy_digest="6" * 64,
                stage_start_id=STAGE_START_ID,
            ),
        )
        record = base_record(repository, RunStatus.IDLE)
        events.initialize(record, record.created_at)
        store.record_bootstrap_evidence(events, record.created_at)
        for offset, target in enumerate((RunStatus.PREFLIGHT, RunStatus.IMPLEMENTING), start=1):
            before = events.record
            after = transition_to(
                before,
                target,
                moment=T0 + timedelta(seconds=offset),
                updates={"current_milestone": "AUTO-099-M01"},
            )
            events.append_transition(before, after, after.updated_at)
        yield store, lock, events
    finally:
        lock.release()


ADAPTER = AdapterIdentity(provider="fake", adapter_type="tests.FakeAdapter")


def open_request(events: EventStore, *, prompt: str = "Implement AUTO-099-M01.") -> OperationHandle:
    return events.journal.create_request(
        step=provider_step(events.record, ProviderRole.IMPLEMENTATION, "AUTO-099-M01"),
        adapter=ADAPTER,
        invoking_state=RunStatus.IMPLEMENTING,
        repository_root="/worktree",
        allowed_environment_variables=["PATH"],
        prompt=prompt,
        recorded_at=stamp(10),
    )


def intent(events: EventStore, handle: OperationHandle, attempt: int) -> str:
    return events.journal.record_intent(
        handle,
        attempt=attempt,
        provider_request_sha256="1" * 64,
        argv_sha256="2" * 64,
        timeout_seconds=60,
        transcript_label="fake-implementation",
        transcript_sequence=attempt,
        fingerprint_sha256="3" * 64,
        recorded_at=stamp(10 + attempt),
    ).sha256


def spawned(events: EventStore, handle: OperationHandle, attempt: int, intent_sha: str) -> None:
    events.journal.record_receipt(
        handle,
        attempt=attempt,
        intent_sha256=intent_sha,
        kind=ReceiptKind.SCRIPTED_FAKE_ACKNOWLEDGMENT,
        process_id=None,
        observed_started_at=stamp(20),
    )


def received(events: EventStore, handle: OperationHandle, attempt: int) -> str:
    return events.journal.record_result(
        handle,
        attempt=attempt,
        raw_text="AUTO016_MILESTONE_RESULT ...",
        outcome=ExecutionOutcome(
            exit_code=0,
            timed_out=False,
            duration_ms=1,
            stdout_truncated=False,
            stderr_truncated=False,
        ),
        transcripts=(),
        recorded_at=stamp(30),
    ).sha256


class TestPhaseOrder:
    """The ladder's ordering rules, enforced before anything is published."""

    def test_the_ladder_in_order_derives_its_highest_phase(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        store, _, events = journal_run
        handle = open_request(events)
        view = events.operation(handle.operation_id)
        assert view.highest_phase is OperationPhase.REQUEST_CREATED
        intent_sha = intent(events, handle, 1)
        assert events.operation(handle.operation_id).highest_phase is OperationPhase.DISPATCH_INTENT
        spawned(events, handle, 1, intent_sha)
        raw = received(events, handle, 1)
        result = MilestoneResult(milestone="AUTO-099-M01", status=MilestoneReportStatus.COMPLETE)
        events.journal.record_validation(
            handle,
            attempt=1,
            raw_result_sha256=raw,
            verdict=ValidationVerdict.VALID,
            result=result,
            diagnostics=(),
            recorded_at=stamp(31),
        )
        view = events.operation(handle.operation_id)
        assert view.highest_phase is OperationPhase.RESULT_VALIDATED
        assert view.attempts[0].verdict is ValidationVerdict.VALID
        assert view.adapter == ADAPTER
        # The derived view reloads identically from disk.
        assert (
            store.load_lifecycle(lock=journal_run[1]).state.operations[handle.operation_id] == view
        )

    def test_a_repeated_identical_request_is_a_confirmed_duplicate(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        sequence = events.require_state().sequence
        again = open_request(events)
        assert again == handle
        assert events.require_state().sequence == sequence

    def test_a_different_request_under_one_identity_conflicts(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        open_request(events)
        sequence = events.require_state().sequence
        with pytest.raises(OperationRecordConflict) as refused:
            open_request(events, prompt="A different prompt under the same identity.")
        assert refused.value.stop_reason is StopReason.OPERATION_RECORD_CONFLICT
        assert events.require_state().sequence == sequence

    def test_a_receipt_without_an_intent_is_invalid(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        with pytest.raises(OperationRecordInvalid):
            spawned(events, handle, 1, "0" * 64)

    def test_a_result_without_a_receipt_is_invalid(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        intent(events, handle, 1)
        with pytest.raises(OperationRecordInvalid):
            received(events, handle, 1)

    def test_one_attempt_cannot_hold_a_receipt_and_a_pre_spawn_failure(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        intent_sha = intent(events, handle, 1)
        spawned(events, handle, 1, intent_sha)
        with pytest.raises(OperationRecordConflict):
            events.journal.record_pre_spawn_failure(
                handle, attempt=1, intent_sha256=intent_sha, detail="refused", recorded_at=stamp(40)
            )

    def test_a_retry_follows_only_a_positive_pre_spawn_failure(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        first = intent(events, handle, 1)
        # Receipt absent is never "no spawn": without a positive refusal there is no attempt 2.
        with pytest.raises(OperationRecordConflict):
            intent(events, handle, 2)
        events.journal.record_pre_spawn_failure(
            handle, attempt=1, intent_sha256=first, detail="ENOENT", recorded_at=stamp(40)
        )
        second = intent(events, handle, 2)
        view = events.operation(handle.operation_id)
        assert view.operation_id == handle.operation_id
        assert [attempt.attempt for attempt in view.attempts] == [1, 2]
        assert view.attempts[0].pre_spawn_failure_sha256 is not None
        assert view.attempts[1].intent_sha256 == second

    def test_attempts_are_gap_free_and_bounded(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        with pytest.raises(OperationRecordConflict):
            intent(events, handle, 2)
        for attempt in (1, 2, 3):
            sha = intent(events, handle, attempt)
            events.journal.record_pre_spawn_failure(
                handle, attempt=attempt, intent_sha256=sha, detail="ENOENT", recorded_at=stamp(40)
            )
        with pytest.raises(ValueError):
            intent(events, handle, 4)

    def test_evidence_is_immutable_and_a_second_result_conflicts(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle = open_request(events)
        intent_sha = intent(events, handle, 1)
        spawned(events, handle, 1, intent_sha)
        received(events, handle, 1)
        with pytest.raises((OperationRecordConflict, OperationRecordInvalid)):
            events.journal.record_result(
                handle,
                attempt=1,
                raw_text="a different result under the same attempt",
                outcome=ExecutionOutcome(
                    exit_code=0,
                    timed_out=False,
                    duration_ms=1,
                    stdout_truncated=False,
                    stderr_truncated=False,
                ),
                transcripts=(),
                recorded_at=stamp(31),
            )


class TestOnlyValidResultsAreAccepted:
    """T-OP-INVALID's storage half: an invalid result can never become an accepted success."""

    def _to_validation(self, events: EventStore, verdict: ValidationVerdict) -> tuple[Any, Any]:
        handle = open_request(events)
        intent_sha = intent(events, handle, 1)
        spawned(events, handle, 1, intent_sha)
        raw = received(events, handle, 1)
        result = (
            MilestoneResult(milestone="AUTO-099-M01", status=MilestoneReportStatus.COMPLETE)
            if verdict is ValidationVerdict.VALID
            else None
        )
        reference = events.journal.record_validation(
            handle,
            attempt=1,
            raw_result_sha256=raw,
            verdict=verdict,
            result=result,
            diagnostics=["diagnostic"] if result is None else (),
            recorded_at=stamp(31),
        )
        return handle, reference

    def _declare(
        self,
        events: EventStore,
        handle: Any,
        reference: Any,
        kind: LifecycleEventType,
        disposition: PersistenceKind,
    ) -> None:
        from ai_workflow_engine.milestone_runner.application import revise_record

        before = events.record
        middle = revise_record(before, moment=T0 + timedelta(seconds=40), updates={})
        after = transition_to(
            middle,
            (
                RunStatus.FOCUSED_VERIFYING
                if disposition is PersistenceKind.ACCEPTED
                else RunStatus.MILESTONE_FAILED
            ),
            moment=T0 + timedelta(seconds=40),
        )
        declaration = events.declare(
            action=(
                MutationAction.RESULT_ACCEPTANCE
                if disposition is PersistenceKind.ACCEPTED
                else MutationAction.RESULT_REJECTION
            ),
            command=MutationCommand.START,
            initiated_at=middle.updated_at,
            evidence=ResultEvidence(
                kind="RESULT",
                operation_id=handle.operation_id,
                disposition=disposition,
                verdict=reference,
            ),
            changes=[
                PlannedChange(
                    kind,
                    before,
                    middle,
                    middle.updated_at,
                    operation_id=handle.operation_id,
                    accepted_result_sha256=reference.sha256,
                    rejection_source=RejectionSource.VALIDATION,
                    verdict_sha256=reference.sha256,
                ),
                PlannedChange(
                    LifecycleEventType.STATE_TRANSITIONED,
                    middle,
                    after,
                    after.updated_at,
                    operation_id=handle.operation_id,
                ),
            ],
        )
        events.append_constituent(declaration, 1)
        appended = events.append_transition(
            middle,
            after,
            after.updated_at,
            operation_id=handle.operation_id,
            constituent=(declaration, 2),
        )
        events.journal.write_applied(handle.operation_id, appended.event, appended.sha256)

    @pytest.mark.parametrize(
        "verdict", [ValidationVerdict.INVALID, ValidationVerdict.EXECUTION_FAILED]
    )
    def test_an_invalid_or_failed_verdict_is_never_accepted(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], verdict: ValidationVerdict
    ) -> None:
        _, _, events = journal_run
        handle, reference = self._to_validation(events, verdict)
        sequence = events.require_state().sequence
        with pytest.raises(OperationRecordInvalid, match="VALID"):
            self._declare(
                events,
                handle,
                reference,
                LifecycleEventType.OPERATION_RESULT_ACCEPTED,
                PersistenceKind.ACCEPTED,
            )
        # The declaration was refused at candidate validation, before any byte was published.
        assert events.require_state().sequence == sequence

    def test_a_rejected_verdict_is_persisted_and_its_transition_applied_once(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle, reference = self._to_validation(events, ValidationVerdict.INVALID)
        self._declare(
            events,
            handle,
            reference,
            LifecycleEventType.OPERATION_RESULT_REJECTED,
            PersistenceKind.REJECTED,
        )
        view = events.operation(handle.operation_id)
        assert view.persisted is PersistenceKind.REJECTED
        assert view.highest_phase is OperationPhase.TRANSITION_APPLIED
        assert events.record.workflow_state is RunStatus.MILESTONE_FAILED
        assert events.record.successful_review_rounds == 0


class TestAppliedReceipt:
    """T-OP-APPLIED: the transition is durable first; a lost receipt is rebuilt, not re-applied."""

    def _complete(self, journal_run: tuple[RunStateStore, RunLock, EventStore]) -> tuple[Any, Path]:
        store, _, events = journal_run
        helper = TestOnlyValidResultsAreAccepted()
        handle, reference = helper._to_validation(events, ValidationVerdict.VALID)
        helper._declare(
            events,
            handle,
            reference,
            LifecycleEventType.OPERATION_RESULT_ACCEPTED,
            PersistenceKind.ACCEPTED,
        )
        return handle, store.run_directory / operation_artifact_path(
            handle.operation_id, "applied.json"
        )

    def test_the_receipt_names_the_durable_causative_transition(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        _, _, events = journal_run
        handle, applied = self._complete(journal_run)
        document = json.loads(applied.read_bytes())
        event_id, version, event_sha = events.require_state().causative_events[handle.operation_id]
        assert (document["event_id"], document["state_version"], document["event_sha256"]) == (
            event_id,
            version,
            event_sha,
        )

    def test_a_missing_receipt_is_rebuilt_without_a_second_transition(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        store, lock, events = journal_run
        handle, applied = self._complete(journal_run)
        original = applied.read_bytes()
        applied.unlink()
        sequence = events.require_state().sequence
        record = events.record
        reopened, view = store.open_lifecycle(lock)
        assert applied.read_bytes() == original
        assert reopened.require_state().sequence == sequence
        assert reopened.record == record
        assert view.missing_applied == (handle.operation_id,)

    def test_a_contradictory_receipt_refuses(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        store, lock, _ = journal_run
        _, applied = self._complete(journal_run)
        document = json.loads(applied.read_bytes())
        document["state_version"] = 1
        applied.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
        with pytest.raises(OperationRecordConflict):
            store.load_lifecycle(lock=lock)


class TestHostileOperationArtifacts:
    """T-HOSTILE-IO for operation artifacts: every hostile shape refuses; nothing escapes."""

    @pytest.fixture
    def request_path(self, journal_run: tuple[RunStateStore, RunLock, EventStore]) -> Path:
        store, _, events = journal_run
        handle = open_request(events)
        return store.run_directory / operation_artifact_path(handle.operation_id, "request.json")

    def _refuses(self, store: RunStateStore, lock: RunLock) -> None:
        with pytest.raises((OperationRecordInvalid, EventChainBroken)):
            store.load_lifecycle(lock=lock)

    def test_a_symlinked_final_component(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        request_path: Path,
        tmp_path: Path,
    ) -> None:
        store, lock, _ = journal_run
        outside = tmp_path / "outside.json"
        outside.write_bytes(request_path.read_bytes())
        request_path.unlink()
        request_path.symlink_to(outside)
        self._refuses(store, lock)

    def test_a_symlinked_parent_component(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        request_path: Path,
        tmp_path: Path,
    ) -> None:
        store, lock, _ = journal_run
        moved = tmp_path / "moved-operation"
        request_path.parent.rename(moved)
        request_path.parent.symlink_to(moved, target_is_directory=True)
        self._refuses(store, lock)

    def test_a_fifo_in_place_of_the_artifact_does_not_hang(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], request_path: Path
    ) -> None:
        store, lock, _ = journal_run
        request_path.unlink()
        os.mkfifo(request_path)
        self._refuses(store, lock)

    def test_a_directory_in_place_of_the_artifact(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], request_path: Path
    ) -> None:
        store, lock, _ = journal_run
        request_path.unlink()
        request_path.mkdir()
        self._refuses(store, lock)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda raw: raw + b" ",
            lambda raw: raw.replace(
                b'"schema_version":1', b'"schema_version":1,"schema_version":1'
            ),
            lambda raw: b"\xff" + raw[1:],
            lambda raw: raw.replace(b"IMPLEMENTING", b"REVIEWING"),
            lambda raw: b"",
        ],
    )
    def test_altered_bytes_refuse(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        request_path: Path,
        mutate: Any,
    ) -> None:
        store, lock, _ = journal_run
        request_path.write_bytes(mutate(request_path.read_bytes()))
        self._refuses(store, lock)

    def test_a_missing_artifact_refuses_and_is_never_recreated(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], request_path: Path
    ) -> None:
        store, lock, _ = journal_run
        request_path.unlink()
        self._refuses(store, lock)
        assert not request_path.exists()


def test_every_artifact_model_is_closed_and_strict() -> None:
    from ai_workflow_engine.milestone_runner.operations import ARTIFACT_MODELS

    for model in ARTIFACT_MODELS.values():
        assert issubclass(model, MilestoneRunnerModel)
        assert model.model_config.get("extra") == "forbid"
        assert model.model_config.get("strict") is True


# ======================================================================================
# AUTO-018 remediation cycle 1 -- AUTO018-IMPL-R05 and R09
# ======================================================================================

from ai_workflow_engine.milestone_runner.events import (  # noqa: E402
    EVENTS_DIRECTORY,
    PUBLICATION_WITNESS_FILE_NAME,
    EvidenceKind,
    EvidenceRoot,
    LifecycleEvent,
    build_event,
    model_bytes,
    parse_event_bytes,
    witness_for,
)
from ai_workflow_engine.milestone_runner.operations import (  # noqa: E402
    DISPATCH_INTENT_FILE_NAME,
    DISPATCH_RECEIPT_FILE_NAME,
    REQUEST_FILE_NAME,
    VALIDATED_RESULT_FILE_NAME,
    DispatchIntent,
    OperationRequest,
)
from ai_workflow_engine.milestone_runner.results import (  # noqa: E402
    AddressedFinding,
    ClosureResult,
    ClosureRuling,
    CorrectionResult,
    ReportedVerification,
    ReportedVerificationStatus,
    ReviewResult,
)


def to_validated(events: EventStore, result: Any = None) -> tuple[OperationHandle, str]:
    handle = open_request(events)
    intent_sha = intent(events, handle, 1)
    spawned(events, handle, 1, intent_sha)
    raw = received(events, handle, 1)
    events.journal.record_validation(
        handle,
        attempt=1,
        raw_result_sha256=raw,
        verdict=ValidationVerdict.VALID,
        result=result
        or MilestoneResult(milestone="AUTO-099-M01", status=MilestoneReportStatus.COMPLETE),
        diagnostics=(),
        recorded_at=stamp(31),
    )
    return handle, raw


def rehash_artifact(store: RunStateStore, path: str, artifact: MilestoneRunnerModel) -> None:
    """A hostile but consistent rewrite: new canonical artifact bytes, every digest that names
    them updated, every later event re-chained, and the witness re-pointed at the new tip."""
    payload = model_bytes(artifact)
    target = store.run_directory / path
    old_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    target.write_bytes(payload)
    new_sha = hashlib.sha256(payload).hexdigest()

    def repoint(value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("path") == path and value.get("sha256") == old_sha:
                return {**value, "sha256": new_sha, "byte_count": len(payload)}
            return {key: repoint(item) for key, item in value.items()}
        if isinstance(value, list):
            return [repoint(item) for item in value]
        return value

    directory = store.run_directory / EVENTS_DIRECTORY
    previous: str | None = None
    last: tuple[LifecycleEvent, str] | None = None
    for file in sorted(directory.iterdir()):
        event, _ = parse_event_bytes(file.name, file.read_bytes())
        payload_type = type(event.payload)
        rebuilt = build_event(
            pins=event.pins,
            sequence=event.sequence,
            event_type=event.event_type,
            recorded_at=event.recorded_at,
            payload=payload_type.model_validate_json(
                json.dumps(repoint(event.payload.model_dump(mode="json")))
            ),
            prev_event_digest=previous,
            mutation_id=event.mutation_id,
            mutation_index=event.mutation_index,
        )
        data = rebuilt.canonical_bytes()
        file.write_bytes(data)
        previous = hashlib.sha256(data).hexdigest()
        last = (rebuilt, previous)
    assert last is not None
    (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).write_bytes(
        model_bytes(witness_for(*last))
    )
    (store.run_directory / "state.json").unlink(missing_ok=True)


def read_artifact(store: RunStateStore, path: str, model: type[Any]) -> Any:
    return model.model_validate_json((store.run_directory / path).read_bytes())


class TestAuto018R05ArtifactFactCrossCheck:
    """AUTO018-IMPL-R05: consistently rehashed but contradictory artifacts fail closed."""

    def _variant(self, handle: OperationHandle, store: RunStateStore, name: str) -> tuple[str, Any]:
        identifier = handle.operation_id
        if name == "validated-invalid-on-valid-event":
            path = operation_artifact_path(identifier, VALIDATED_RESULT_FILE_NAME, attempt=1)
            current = read_artifact(store, path, ValidatedResult)
            return path, current.model_copy(
                update={
                    "verdict": ValidationVerdict.INVALID,
                    "milestone_result": None,
                    "diagnostics": ["forged"],
                }
            )
        if name == "validated-other-raw-result":
            path = operation_artifact_path(identifier, VALIDATED_RESULT_FILE_NAME, attempt=1)
            current = read_artifact(store, path, ValidatedResult)
            return path, current.model_copy(update={"raw_result_sha256": "9" * 64})
        if name == "validated-other-milestone":
            path = operation_artifact_path(identifier, VALIDATED_RESULT_FILE_NAME, attempt=1)
            current = read_artifact(store, path, ValidatedResult)
            assert current.milestone_result is not None
            return path, current.model_copy(
                update={
                    "milestone_result": current.milestone_result.model_copy(
                        update={"milestone": "AUTO-099-M02"}
                    )
                }
            )
        if name == "request-other-adapter":
            path = operation_artifact_path(identifier, REQUEST_FILE_NAME)
            current = read_artifact(store, path, OperationRequest)
            return path, current.model_copy(
                update={"adapter": AdapterIdentity(provider="other", adapter_type="tests.Other")}
            )
        if name == "intent-other-request":
            path = operation_artifact_path(identifier, DISPATCH_INTENT_FILE_NAME, attempt=1)
            current = read_artifact(store, path, DispatchIntent)
            return path, current.model_copy(update={"request_sha256": "9" * 64})
        if name == "intent-other-adapter":
            path = operation_artifact_path(identifier, DISPATCH_INTENT_FILE_NAME, attempt=1)
            current = read_artifact(store, path, DispatchIntent)
            return path, current.model_copy(
                update={"adapter": AdapterIdentity(provider="other", adapter_type="tests.Other")}
            )
        assert name == "receipt-other-intent"
        path = operation_artifact_path(identifier, DISPATCH_RECEIPT_FILE_NAME, attempt=1)
        current = read_artifact(store, path, DispatchReceipt)
        return path, current.model_copy(update={"intent_sha256": "9" * 64})

    @pytest.mark.parametrize(
        "name",
        [
            "validated-invalid-on-valid-event",
            "validated-other-raw-result",
            "validated-other-milestone",
            "request-other-adapter",
            "intent-other-request",
            "intent-other-adapter",
            "receipt-other-intent",
        ],
    )
    def test_a_rehashed_contradictory_chain_fails_closed_on_verified_load(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], name: str
    ) -> None:
        store, lock, events = journal_run
        handle, _ = to_validated(events)
        path, forged = self._variant(handle, store, name)
        rehash_artifact(store, path, forged)
        with pytest.raises(OperationRecordInvalid) as refused:
            store.load_lifecycle(lock=lock)
        assert refused.value.stop_reason is StopReason.OPERATION_RECORD_INVALID

    def test_the_untampered_rehash_still_loads(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        """Control: the rehash helper itself produces a valid chain when nothing contradicts."""
        store, lock, events = journal_run
        handle, _ = to_validated(events)
        path = operation_artifact_path(handle.operation_id, VALIDATED_RESULT_FILE_NAME, attempt=1)
        rehash_artifact(store, path, read_artifact(store, path, ValidatedResult))
        assert store.load_lifecycle(lock=lock).state.operations[handle.operation_id]

    def test_an_invalid_artifact_is_never_appended_under_a_valid_event_fact(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        store, _, events = journal_run
        handle = open_request(events)
        intent_sha = intent(events, handle, 1)
        spawned(events, handle, 1, intent_sha)
        raw = received(events, handle, 1)
        forged = ValidatedResult(
            schema_version=1,
            pins=events.journal.pins(),
            operation_id=handle.operation_id,
            attempt=1,
            role=ProviderRole.IMPLEMENTATION,
            raw_result_sha256=raw,
            verdict=ValidationVerdict.INVALID,
            diagnostics=["forged"],
            recorded_at=stamp(31),
        )
        reference = events.publish_operation_artifact(
            operation_artifact_path(handle.operation_id, VALIDATED_RESULT_FILE_NAME, attempt=1),
            forged,
        )
        sequence = events.require_state().sequence
        with pytest.raises(OperationRecordInvalid):
            events.record_operation_validation(
                operation_id=handle.operation_id,
                attempt=1,
                verdict=ValidationVerdict.VALID,
                reference=reference,
                recorded_at=stamp(32),
            )
        assert events.require_state().sequence == sequence
        assert len(list((store.run_directory / EVENTS_DIRECTORY).iterdir())) == sequence

    @pytest.mark.parametrize("variant", ["missing", "other-digest", "other-artifact"])
    def test_an_acceptance_declared_on_a_foreign_verdict_reference_refuses(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], variant: str
    ) -> None:
        from ai_workflow_engine.milestone_runner.application import revise_record
        from ai_workflow_engine.milestone_runner.events import DurableEvidenceReference

        _, _, events = journal_run
        handle, _ = to_validated(events)
        genuine = events.operation(handle.operation_id).attempts[0].validated_sha256
        assert genuine is not None
        validated_path = operation_artifact_path(
            handle.operation_id, VALIDATED_RESULT_FILE_NAME, attempt=1
        )
        foreign = {
            "missing": None,
            "other-digest": DurableEvidenceReference(
                kind=EvidenceKind.VALIDATED_RESULT,
                root=EvidenceRoot.RUN,
                path=validated_path,
                sha256="9" * 64,
                byte_count=1,
            ),
            "other-artifact": DurableEvidenceReference(
                kind=EvidenceKind.DISPATCH_INTENT,
                root=EvidenceRoot.RUN,
                path=operation_artifact_path(
                    handle.operation_id, DISPATCH_INTENT_FILE_NAME, attempt=1
                ),
                sha256=genuine,
                byte_count=1,
            ),
        }[variant]
        before = events.record
        middle = revise_record(before, moment=T0 + timedelta(seconds=40), updates={})
        after = transition_to(
            middle, RunStatus.FOCUSED_VERIFYING, moment=T0 + timedelta(seconds=40)
        )
        sequence = events.require_state().sequence
        with pytest.raises(OperationRecordInvalid):
            events.declare(
                action=MutationAction.RESULT_ACCEPTANCE,
                command=MutationCommand.START,
                initiated_at=middle.updated_at,
                evidence=ResultEvidence(
                    kind="RESULT",
                    operation_id=handle.operation_id,
                    disposition=PersistenceKind.ACCEPTED,
                    verdict=foreign,
                ),
                changes=[
                    PlannedChange(
                        LifecycleEventType.OPERATION_RESULT_ACCEPTED,
                        before,
                        middle,
                        middle.updated_at,
                        operation_id=handle.operation_id,
                        accepted_result_sha256=genuine,
                    ),
                    PlannedChange(
                        LifecycleEventType.STATE_TRANSITIONED,
                        middle,
                        after,
                        after.updated_at,
                        operation_id=handle.operation_id,
                    ),
                ],
            )
        assert events.require_state().sequence == sequence


SECRET = "ghp_" + "A1b2C3d4E5f6G7h8I9j0" * 2


def secret_results() -> dict[ProviderRole, Any]:
    leaked = f"the provider echoed token={SECRET} in its prose"
    return {
        ProviderRole.IMPLEMENTATION: MilestoneResult(
            milestone="AUTO-099-M01",
            status=MilestoneReportStatus.COMPLETE,
            verification=[
                ReportedVerification(
                    command=f"pytest  # {leaked}", result=ReportedVerificationStatus.PASS
                )
            ],
            blockers=[leaked],
        ),
        ProviderRole.REVIEW: ReviewResult.model_validate_json(
            json.dumps(
                {
                    "verdict": "BLOCKED",
                    "blockers": [
                        {
                            "finding_id": "F-001",
                            "severity": "HIGH",
                            "title": f"Leak {SECRET}",
                            "summary": leaked,
                        }
                    ],
                    "deferred": [],
                }
            )
        ),
        ProviderRole.CORRECTION: CorrectionResult(
            status=MilestoneReportStatus.COMPLETE,
            findings_addressed=[AddressedFinding(id="F-001", resolution=leaked)],
        ),
        ProviderRole.CLOSURE: ClosureResult(
            findings=[
                ClosureRuling.model_validate_json(
                    json.dumps({"id": "F-001", "status": "CLOSED", "reason": leaked})
                )
            ]
        ),
    }


class TestAuto018R09TypedResultRedaction:
    """AUTO018-IMPL-R09: valid results with secret-shaped free text are accepted, redacted."""

    @pytest.mark.parametrize("role", list(ProviderRole))
    def test_every_role_accepts_a_result_with_secret_shaped_free_text(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore], role: ProviderRole
    ) -> None:
        store, lock, events = journal_run
        handle = events.journal.create_request(
            step=provider_step(events.record, role, "AUTO-099-M01"),
            adapter=ADAPTER,
            invoking_state=RunStatus.IMPLEMENTING,
            repository_root="/worktree",
            allowed_environment_variables=["PATH"],
            prompt=f"prompt for {role.value}",
            recorded_at=stamp(10),
        )
        intent_sha = intent(events, handle, 1)
        spawned(events, handle, 1, intent_sha)
        raw = received(events, handle, 1)
        counted: list[tuple[str, int]] = []
        reference = events.journal.record_validation(
            handle,
            attempt=1,
            raw_result_sha256=raw,
            verdict=ValidationVerdict.VALID,
            result=secret_results()[role],
            diagnostics=(),
            recorded_at=stamp(31),
            on_redaction=lambda path, found: counted.append(
                (path, sum(item.occurrences for item in found))
            ),
        )
        validated = read_artifact(store, reference.path, ValidatedResult)
        assert validated.verdict is ValidationVerdict.VALID
        typed = {
            ProviderRole.IMPLEMENTATION: validated.milestone_result,
            ProviderRole.REVIEW: validated.review_result,
            ProviderRole.CORRECTION: validated.correction_result,
            ProviderRole.CLOSURE: validated.closure_result,
        }[role]
        assert typed is not None and type(typed) is type(secret_results()[role])
        assert counted and counted[0][0] == reference.path and counted[0][1] >= 1
        for path in store.run_directory.rglob("*"):
            if path.is_file():
                assert SECRET not in path.read_text(encoding="utf-8", errors="replace"), path
        assert (
            store.load_lifecycle(lock=lock)
            .state.operations[handle.operation_id]
            .attempts[0]
            .verdict
            is ValidationVerdict.VALID
        )

    def test_identity_fields_are_never_rewritten_and_a_secret_there_still_fails_closed(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        from ai_workflow_engine.milestone_runner.state import StatePublicationFailure

        store, _, events = journal_run
        handle = events.journal.create_request(
            step=provider_step(events.record, ProviderRole.REVIEW, None),
            adapter=ADAPTER,
            invoking_state=RunStatus.REVIEWING,
            repository_root="/worktree",
            allowed_environment_variables=["PATH"],
            prompt="review",
            recorded_at=stamp(10),
        )
        intent_sha = intent(events, handle, 1)
        spawned(events, handle, 1, intent_sha)
        raw = received(events, handle, 1)
        structural = ReviewResult.model_validate_json(
            json.dumps(
                {
                    "verdict": "BLOCKED",
                    "blockers": [
                        {
                            "finding_id": SECRET,
                            "severity": "HIGH",
                            "title": "t",
                            "summary": "s",
                        }
                    ],
                    "deferred": [],
                }
            )
        )
        sequence = events.require_state().sequence
        with pytest.raises((StatePublicationFailure, OperationRecordInvalid, ValidationError)):
            events.journal.record_validation(
                handle,
                attempt=1,
                raw_result_sha256=raw,
                verdict=ValidationVerdict.VALID,
                result=structural,
                diagnostics=(),
                recorded_at=stamp(31),
            )
        assert events.require_state().sequence == sequence
        for path in store.run_directory.rglob("*"):
            if path.is_file():
                assert SECRET not in path.read_text(encoding="utf-8", errors="replace"), path


# ======================================================================================
# AUTO-018 remediation cycle 2 -- AUTO018-IMPL-R02 and R07: confirmation is bound to the
# current canonical namespace, cached or not
# ======================================================================================


def _rename_away(directory: Path) -> Path:
    detached = directory.with_name(directory.name + ".detached")
    directory.rename(detached)
    return detached


def _symlink_to_detached(directory: Path) -> None:
    """The cycle-1 closure probe: the canonical name now redirects to the detached original."""
    directory.symlink_to(_rename_away(directory), target_is_directory=True)


def _copy_of_detached(directory: Path) -> None:
    """A different directory at the canonical name, holding byte- and mtime-identical files."""
    import shutil

    shutil.copytree(_rename_away(directory), directory, symlinks=True)


def _empty_directory(directory: Path) -> None:
    _rename_away(directory)
    directory.mkdir(mode=0o700)


MUTATIONS: dict[str, Any] = {
    "symlink-to-detached": _symlink_to_detached,
    "other-directory-copy": _copy_of_detached,
    "other-directory-empty": _empty_directory,
}


def dependency_directory(store: RunStateStore, events: EventStore, dependency: str) -> Path:
    """The governed directory a relied-upon dependency of the established chain lives in."""
    (operation,) = events.require_state().operations
    return {
        "authority": store.artifact_root / "stage-starts",
        "run-witness": store.run_directory,
        "events-predecessor": store.run_directory / "events",
        "operation-request": store.run_directory / "operations" / operation,
        "attempt-artifact": store.run_directory / "operations" / operation / "attempts" / "0001",
    }[dependency]


def established(events: EventStore) -> OperationHandle:
    """An operation with an attempt, so every governed ancestry is relied upon by the chain."""
    handle = open_request(events)
    spawned(events, handle, 1, intent(events, handle, 1))
    return handle


def namespace_snapshot(root: Path) -> dict[str, tuple[bytes, int, int, int]]:
    """Bytes, mtime, inode and link count of every file, followed through nothing."""
    snapshot = {}
    for path in sorted(root.rglob("*")):
        status = path.lstat()
        if path.name != "run.lock" and stat_is_file(status):
            snapshot[path.relative_to(root).as_posix()] = (
                path.read_bytes(),
                status.st_mtime_ns,
                status.st_ino,
                status.st_nlink,
            )
    return snapshot


def stat_is_file(status: os.stat_result) -> bool:
    import stat

    return stat.S_ISREG(status.st_mode)


DEPENDENCIES = (
    "authority",
    "run-witness",
    "events-predecessor",
    "operation-request",
    "attempt-artifact",
)


class TestAuto018Cycle2NamespaceBoundConfirmation:
    """AUTO018-IMPL-R02 / R07 (remediation cycle 2).

    Every confirmation -- including one answered from the process-local cache -- re-walks the
    canonical namespace no-follow from the hold's retained root and requires each governed child
    directory to be the very directory the hold bound at its name. A parent renamed away and
    replaced by a symlink to the detached original, by another directory with identical bytes,
    or by an empty directory refuses before any acknowledgment or dependent effect.
    """

    def _refuses(
        self, store: RunStateStore, events: EventStore, lock: RunLock, attempt: Any
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost

        sequence = events.require_state().sequence
        tree = namespace_snapshot(store.artifact_root)
        with pytest.raises(LockOwnershipLost) as lost:
            attempt()
        assert lost.value.stop_reason is StopReason.LOCK_OWNERSHIP_LOST
        assert events.require_state().sequence == sequence
        assert namespace_snapshot(store.artifact_root) == tree, "a refusal has no effect"
        assert not lock.is_held, "the namespace loss invalidates the hold"

    def test_the_cycle_1_closure_probe_now_fails_closed(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        """Rename `stage-starts`, symlink its name to the detached directory, retry a duplicate."""
        store, lock, events = journal_run
        envelope, _ = events.events[2]
        assert events.publish_envelope(envelope).duplicate
        _symlink_to_detached(store.artifact_root / "stage-starts")
        self._refuses(store, events, lock, lambda: events.publish_envelope(envelope))

    def test_unchanged_ancestry_acknowledges_duplicates_without_mutation(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        store, lock, events = journal_run
        handle = established(events)
        tree = namespace_snapshot(store.artifact_root)
        record, sequence = events.record, events.require_state().sequence
        for envelope, digest in events.events:
            appended = events.publish_envelope(envelope)
            assert appended.duplicate and appended.sha256 == digest
        assert open_request(events) == handle
        # Twice: the second pass is answered from the cache the first one populated.
        for envelope, _ in events.events:
            assert events.publish_envelope(envelope).duplicate
        assert namespace_snapshot(store.artifact_root) == tree
        assert events.record == record
        assert events.require_state().sequence == sequence
        assert lock.is_held

    @pytest.mark.parametrize("mutation", list(MUTATIONS))
    @pytest.mark.parametrize("dependency", DEPENDENCIES)
    def test_a_cached_duplicate_event_refuses_a_changed_ancestry(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        dependency: str,
        mutation: str,
    ) -> None:
        """R07 items 2-7: a prior successful confirmation populated the cache first."""
        store, lock, events = journal_run
        established(events)
        envelope, _ = events.events[3]
        assert events.publish_envelope(envelope).duplicate
        MUTATIONS[mutation](dependency_directory(store, events, dependency))
        self._refuses(store, events, lock, lambda: events.publish_envelope(envelope))

    @pytest.mark.parametrize("mutation", list(MUTATIONS))
    @pytest.mark.parametrize("dependency", DEPENDENCIES)
    def test_a_cached_duplicate_request_refuses_a_changed_ancestry(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        dependency: str,
        mutation: str,
    ) -> None:
        store, lock, events = journal_run
        handle = established(events)
        assert open_request(events) == handle
        MUTATIONS[mutation](dependency_directory(store, events, dependency))
        self._refuses(store, events, lock, lambda: open_request(events))

    @pytest.mark.parametrize("mutation", list(MUTATIONS))
    @pytest.mark.parametrize("dependency", DEPENDENCIES)
    def test_a_later_hold_refuses_a_change_after_it_bound_the_namespace(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        dependency: str,
        mutation: str,
    ) -> None:
        """No cache yet: a fresh hold's storage bound the namespace when it opened the run."""
        store, lock, events = journal_run
        established(events)
        envelope, _ = events.events[3]
        lock.release()
        later = RunLock(
            run_id=RUN_ID, repository_identity=IDENTITY, artifact_root=store.artifact_root
        ).bind_repository_root(store.repository_root)
        later.acquire()
        try:
            reopened, _ = store.open_lifecycle(later)
            MUTATIONS[mutation](dependency_directory(store, reopened, dependency))
            self._refuses(store, reopened, later, lambda: reopened.publish_envelope(envelope))
        finally:
            later.release()

    @pytest.mark.parametrize("mutation", list(MUTATIONS))
    @pytest.mark.parametrize("dependency", DEPENDENCIES)
    def test_a_change_before_confirmation_refuses_the_open(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        monkeypatch: pytest.MonkeyPatch,
        dependency: str,
        mutation: str,
    ) -> None:
        """R02 item 3: the ancestry changes after the verified load, before its confirmation."""
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost
        from ai_workflow_engine.milestone_runner.state import RunLifecycleStorage

        store, lock, events = journal_run
        established(events)
        directory = dependency_directory(store, events, dependency)
        lock.release()
        later = RunLock(
            run_id=RUN_ID, repository_identity=IDENTITY, artifact_root=store.artifact_root
        ).bind_repository_root(store.repository_root)
        later.acquire()
        real_confirm_all = RunLifecycleStorage.confirm_all

        def mutate_then_confirm(self: RunLifecycleStorage, view: Any) -> None:
            MUTATIONS[mutation](directory)
            real_confirm_all(self, view)

        try:
            tree = namespace_snapshot(store.artifact_root)
            with monkeypatch.context() as fault:
                fault.setattr(RunLifecycleStorage, "confirm_all", mutate_then_confirm)
                with pytest.raises(LockOwnershipLost) as lost:
                    store.open_lifecycle(later)
            assert lost.value.stop_reason is StopReason.LOCK_OWNERSHIP_LOST
            assert not later.is_held
            # Nothing was repaired, rebuilt or added: every file keeps its bytes and mtime, and
            # the only new paths are the detached original's.
            after = namespace_snapshot(store.artifact_root)
            assert {path: entry[:2] for path, entry in after.items() if path in tree} == {
                path: entry[:2] for path, entry in tree.items() if path in after
            }
            assert all(".detached/" in path for path in set(after) - set(tree))
        finally:
            later.release()

    @pytest.mark.parametrize("dependency", DEPENDENCIES)
    def test_a_redirected_ancestor_refuses_a_fresh_hold_before_confirmation(
        self,
        journal_run: tuple[RunStateStore, RunLock, EventStore],
        dependency: str,
    ) -> None:
        """A symlinked canonical name is never followed, even before anything was bound."""
        from ai_workflow_engine.milestone_runner.events import LIFECYCLE_ERRORS
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost
        from ai_workflow_engine.milestone_runner.state import StateError

        store, lock, events = journal_run
        established(events)
        _symlink_to_detached(dependency_directory(store, events, dependency))
        lock.release()
        later = RunLock(
            run_id=RUN_ID, repository_identity=IDENTITY, artifact_root=store.artifact_root
        ).bind_repository_root(store.repository_root)
        later.acquire()
        try:
            tree = namespace_snapshot(store.artifact_root)
            with pytest.raises((*LIFECYCLE_ERRORS, StateError, LockOwnershipLost)):
                store.open_lifecycle(later)
            assert namespace_snapshot(store.artifact_root) == tree
        finally:
            later.release()

    def test_a_later_hold_with_unchanged_ancestry_opens_and_acknowledges(
        self, journal_run: tuple[RunStateStore, RunLock, EventStore]
    ) -> None:
        store, lock, events = journal_run
        handle = established(events)
        envelope, digest = events.events[3]
        lock.release()
        later = RunLock(
            run_id=RUN_ID, repository_identity=IDENTITY, artifact_root=store.artifact_root
        ).bind_repository_root(store.repository_root)
        later.acquire()
        try:
            tree = namespace_snapshot(store.artifact_root)
            reopened, _ = store.open_lifecycle(later)
            appended = reopened.publish_envelope(envelope)
            assert appended.duplicate and appended.sha256 == digest
            assert open_request(reopened) == handle
            assert namespace_snapshot(store.artifact_root) == tree
            assert later.is_held
        finally:
            later.release()
