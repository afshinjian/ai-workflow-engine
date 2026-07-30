"""Tests for workflow resume/recovery in agentos_workflow.orchestrator.engine
(WORKFLOW_STATES.md §6)."""

from pathlib import Path

import pytest

from agentos_workflow.orchestrator.engine import (
    AuthorizationBindingDriftError,
    AuthorizationBypassError,
    AuthorizationContext,
    AuthorizationRecord,
    AuthorizationScopeMismatchError,
    CorruptedAuthorizationRecordError,
    CorruptedHistoryError,
    CurrentAuthorizationBinding,
    InconsistentHistoryError,
    InvalidActorForTransitionError,
    InvalidTransitionError,
    MissingAuthorizationRecordError,
    MissingPersistedStateError,
    RepositoryLockIdentityMismatchError,
    RepositoryLockUnavailableError,
    ResumedWorkflow,
    WorkflowAlreadyTerminalError,
    WorkflowSession,
    WorkflowState,
    WorkflowStateMachine,
    authorize,
    resume_workflow,
)
from agentos_workflow.orchestrator.lock import RepositoryLock, canonical_lock_path
from agentos_workflow.orchestrator.state_store import StateStore, StateTransitionRecord


def _context(**overrides: object) -> AuthorizationContext:
    defaults: dict[str, object] = {
        "workflow_id": "wf-1",
        "repository_identity": "github.com/org/repo",
        "stage_id": "AUTO-002",
        "planned_stage_branch": "feature/auto-002-orchestrator-state-machine",
        "baseline_branch": "main",
    }
    defaults.update(overrides)
    return AuthorizationContext.model_validate(defaults)


def _repository_path(tmp_path: Path) -> Path:
    """A real, per-test-isolated directory standing in for the target repository — required
    since Finding 4 derives the authoritative lock path from `repository_path` itself
    (`canonical_lock_path`), so it must be a genuine, writable, per-test location, never an
    arbitrary unwritable string.
    """
    repository_path = tmp_path / "repo"
    repository_path.mkdir(exist_ok=True)
    return repository_path


def _authorization_record(tmp_path: Path, **overrides: object) -> AuthorizationRecord:
    defaults: dict[str, object] = {
        "workflow_id": "wf-1",
        "repository_identity": "github.com/org/repo",
        "repository_path": str(_repository_path(tmp_path)),
        "stage_id": "AUTO-002",
        "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
        "stage_contract_hash": "sha256:deadbeef",
        "baseline_branch": "main",
        "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
        "planned_stage_branch": "feature/auto-002-orchestrator-state-machine",
        "authorized_at": "2026-07-24T10:00:00+00:00",
        "authorized_by": "human-owner",
        "engine_version": "0.1.0",
    }
    defaults.update(overrides)
    return AuthorizationRecord.model_validate(defaults)


def _current_binding(tmp_path: Path, **overrides: object) -> CurrentAuthorizationBinding:
    """Matches `_authorization_record`'s defaults for the five fields it doesn't already carry,
    so a resume against a fixture seeded via `_seed_authorized(store, tmp_path)` with no
    overrides sees no drift. Pass overrides to simulate a specific field having drifted since
    authorization.
    """
    defaults: dict[str, object] = {
        "repository_path": str(_repository_path(tmp_path)),
        "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
        "stage_contract_hash": "sha256:deadbeef",
        "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
        "engine_version": "0.1.0",
    }
    defaults.update(overrides)
    return CurrentAuthorizationBinding.model_validate(defaults)


def _seed_authorized(store: StateStore, tmp_path: Path, **overrides: object) -> None:
    """Seed a resumable CREATED -> AUTHORIZED fixture through the real, public authorize() API,
    so both the StateTransitionRecord and the full AuthorizationRecord end up persisted exactly
    as production code would produce them — resume_workflow now requires both.
    """
    record = _authorization_record(tmp_path, **overrides)
    context = AuthorizationContext(
        workflow_id=record.workflow_id,
        repository_identity=record.repository_identity,
        stage_id=record.stage_id,
        planned_stage_branch=record.planned_stage_branch,
        baseline_branch=record.baseline_branch,
    )
    authorize(WorkflowStateMachine(), context, record, state_store=store)


def _transition(
    *,
    tmp_path: Path,
    workflow_id: str = "wf-1",
    target_repository: str = "github.com/org/repo",
    repository_path: str | None = None,
    stage_id: str = "AUTO-002",
    from_state: str,
    to_state: str,
    timestamp: str = "2026-07-24T10:00:00+00:00",
    actor: str | None = None,
) -> StateTransitionRecord:
    # `repository_path` defaults to the same real, per-test directory `_seed_authorized`/
    # `_authorization_record`/`_current_binding`/`_lock` already default to (`_repository_path
    # (tmp_path)`) — so a raw `_transition(...)` fixture record combined with a genuine
    # `authorize()`-seeded one (e.g. `_write_happy_path`) always agrees on repository_path,
    # exactly as production code would produce, rather than tripping the new cross-record
    # repository_path consistency check for an unrelated reason.
    if repository_path is None:
        # Resolved, matching exactly what `authorize()` itself now persists (it canonicalizes
        # `AuthorizationRecord.repository_path` via `Path(...).resolve()`) — never a byte-for-byte
        # coincidence that happens to hold only because this test environment's tmp directory has
        # no symlink components.
        repository_path = str(_repository_path(tmp_path).resolve())
    # Default actor mirrors real production behavior for the edge being recorded: "human" only
    # for the one authorization gate and cancellation (AUDIT_MODEL.md §3), "orchestrator"
    # everywhere else — a caller testing something unrelated to actor semantics can omit `actor`
    # entirely and still get a realistic, permitted value for whatever edge it's constructing.
    if actor is None:
        actor = "human" if to_state in ("AUTHORIZED", "CANCELLED") else "orchestrator"
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


def _store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def _lock(
    tmp_path: Path,
    *,
    workflow_id: str = "wf-1",
    repository_identity: str = "github.com/org/repo",
    repository_path: Path | None = None,
) -> RepositoryLock:
    # AUTO002-F04: `RepositoryLock` no longer accepts a `lock_path` argument at all — its path is
    # always `canonical_lock_path(repository_path)`, computed internally. There is therefore no
    # way to construct a lock bound to one repository_path but physically located elsewhere; the
    # two can no longer diverge.
    resolved_repository_path = (
        repository_path if repository_path is not None else _repository_path(tmp_path)
    )
    return RepositoryLock(
        workflow_id=workflow_id,
        repository_identity=repository_identity,
        repository_path=resolved_repository_path,
    )


def _tamper_persisted_authorization_record(
    tmp_path: Path, store: StateStore, **record_overrides: object
) -> None:
    """Seed a fully self-consistent CREATED -> AUTHORIZED fixture via the real, public
    `authorize()` API, then directly overwrite the persisted `authorization.json` with
    `record_overrides` applied on top of `_authorization_record`'s defaults.

    `authorize()` itself guarantees the persisted `AuthorizationRecord` and
    `StateTransitionRecord` agree (both are validated against the same context before either is
    written) — so the only way to construct a fixture where the *persisted record itself* has
    drifted from the transition history/context that originally produced it (as opposed to the
    caller simply supplying a wrong `context`, already covered by `TestAuthorizationMismatch`) is
    to bypass `authorize()` and tamper with the file directly, simulating either on-disk drift
    since authorization or direct tampering. This is what independently exercises
    `_detect_authorization_binding_drift` for `workflow_id`, `repository_identity`, `stage_id`,
    `baseline_branch`, and `planned_stage_branch` beyond the coarser, already-tested
    `_check_identity_matches_context` check.
    """
    _seed_authorized(store, tmp_path)
    tampered = _authorization_record(tmp_path, **record_overrides)
    authorization_path = store.state_directory / "wf-1" / "authorization.json"
    authorization_path.write_text(tampered.model_dump_json(), encoding="utf-8")


def _write_happy_path(store: StateStore, tmp_path: Path, *, up_to: WorkflowState) -> None:
    # CREATED -> AUTHORIZED must go through the real authorize() API, not a raw transition
    # record: resume_workflow now requires a genuinely persisted AuthorizationRecord to cross
    # that edge during replay (Finding 1 remediation), so a fixture that skips authorize() can no
    # longer stand in for a legitimately-authorized workflow.
    _seed_authorized(store, tmp_path)
    if up_to is WorkflowState.AUTHORIZED:
        return
    chain = [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
        ("VALIDATING", "QA_RUNNING"),
        ("QA_RUNNING", "READY_TO_COMMIT"),
        ("READY_TO_COMMIT", "COMMITTED"),
        ("COMMITTED", "PUSHED"),
        ("PUSHED", "PR_OPEN"),
        ("PR_OPEN", "AUTO_MERGE_ENABLED"),
        ("AUTO_MERGE_ENABLED", "WAITING_FOR_CHECKS"),
        ("WAITING_FOR_CHECKS", "MERGED"),
        ("MERGED", "CLOSING"),
        ("CLOSING", "DONE"),
    ]
    for from_state, to_state in chain:
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state=from_state, to_state=to_state)
        )
        if to_state == up_to.value:
            return
    raise AssertionError(f"{up_to} not reached by the happy path fixture")


class TestMissingPersistedState:
    def test_no_history_raises_missing_persisted_state_error(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(MissingPersistedStateError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held  # lock released after a rejected resume


class TestCorruptedHistory:
    def test_corrupted_transitions_file_raises_corrupted_history_error(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CREATED", to_state="AUTHORIZED")
        )
        transitions_path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        with transitions_path.open("a", encoding="utf-8") as handle:
            handle.write("not valid json\n")

        lock = _lock(tmp_path)
        with pytest.raises(CorruptedHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held


class TestInconsistentHistory:
    def test_history_not_starting_at_created_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_gap_in_transition_chain_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CREATED", to_state="AUTHORIZED")
        )
        # Skips PRECONDITIONS_CHECKED entirely: this record's from_state doesn't match the
        # previous record's to_state.
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED"
            )
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_illegal_edge_rejected_even_with_continuous_chain(self, tmp_path: Path) -> None:
        # The chain is continuous (from_state always matches the prior to_state) but the second
        # edge itself, BRANCH_CREATED -> COMMITTED, skips intermediate states and is not in
        # WORKFLOW_STATES.md §3's allowed set.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED"
            )
        )
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="BRANCH_CREATED", to_state="COMMITTED")
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_multiple_terminal_states_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CREATED", to_state="AUTHORIZED")
        )
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="AUTHORIZED", to_state="FAILED")
        )
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="FAILED", to_state="DONE")
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_transition_after_terminal_state_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CREATED", to_state="AUTHORIZED")
        )
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="AUTHORIZED", to_state="CANCELLED")
        )
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CANCELLED", to_state="PRECONDITIONS_CHECKED")
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_record_workflow_id_disagreeing_with_file_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, workflow_id="wf-1", from_state="CREATED", to_state="AUTHORIZED"
            )
        )
        # Simulate corruption: a record physically stored under wf-1's file but claiming a
        # different workflow_id inside its own payload. record_transition() would route a
        # differently-workflow_id-ed record to a different file, so this is injected directly.
        transitions_path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        mismatched = _transition(
            tmp_path=tmp_path,
            workflow_id="wf-not-1",
            from_state="AUTHORIZED",
            to_state="PRECONDITIONS_CHECKED",
        )
        with transitions_path.open("a", encoding="utf-8") as handle:
            handle.write(mismatched.model_dump_json() + "\n")

        lock = _lock(tmp_path)
        # AUTO002-F08 hardened `StateStore.read_transitions` itself to reject a record whose own
        # `workflow_id` disagrees with the file it was read from — this identity check now runs
        # one layer earlier than `_validate_history_consistency`'s equivalent engine-level check,
        # so the raised type is `CorruptedHistoryError` (state_store-detected corruption) rather
        # than `InconsistentHistoryError` (engine-detected inconsistency); the corruption is still
        # caught, just closer to the read that first observes it (defense in depth).
        with pytest.raises(CorruptedHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_multiple_target_repositories_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path,
                target_repository="github.com/org/repo",
                from_state="CREATED",
                to_state="AUTHORIZED",
            )
        )
        store.record_transition(
            _transition(
                tmp_path=tmp_path,
                target_repository="github.com/org/other-repo",
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
            )
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_multiple_stage_ids_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, stage_id="AUTO-002", from_state="CREATED", to_state="AUTHORIZED"
            )
        )
        store.record_transition(
            _transition(
                tmp_path=tmp_path,
                stage_id="AUTO-003",
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
            )
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held


class TestWorkflowAlreadyTerminal:
    def test_done_workflow_is_not_resumable(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _write_happy_path(store, tmp_path, up_to=WorkflowState.DONE)
        lock = _lock(tmp_path)
        with pytest.raises(WorkflowAlreadyTerminalError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_failed_workflow_is_not_resumable(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="AUTHORIZED", to_state="FAILED")
        )
        lock = _lock(tmp_path)
        with pytest.raises(WorkflowAlreadyTerminalError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_cancelled_workflow_is_not_resumable(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="AUTHORIZED", to_state="CANCELLED")
        )
        lock = _lock(tmp_path)
        with pytest.raises(WorkflowAlreadyTerminalError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held


class TestAuthorizationMismatch:
    def test_workflow_id_not_found_raises_missing_persisted_state_not_scope_mismatch(
        self, tmp_path: Path
    ) -> None:
        # A context.workflow_id that was never persisted can never surface as an
        # AuthorizationScopeMismatchError: the workflow_id IS the lookup key used to read
        # history in the first place, so "mismatch" is structurally impossible here — it
        # degrades to "nothing found for this id" instead, one step earlier in the pipeline.
        store = _store(tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, workflow_id="wf-1", from_state="CREATED", to_state="AUTHORIZED"
            )
        )
        lock = _lock(tmp_path, workflow_id="wf-other")
        with pytest.raises(MissingPersistedStateError):
            resume_workflow(
                _context(workflow_id="wf-other"),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path),
            )
        assert not lock.is_held

    def test_mismatched_repository_identity_in_context_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)  # persisted for github.com/org/repo
        # The lock must itself be bound to the *requested* (wrong) repository, or the new
        # lock-identity check (TestRepositoryLockIdentity below) fires first instead — this test
        # is specifically about the deeper persisted-authorization scope check.
        lock = _lock(tmp_path, repository_identity="github.com/org/wrong-repo")
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            resume_workflow(
                _context(repository_identity="github.com/org/wrong-repo"),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path),
            )
        assert exc_info.value.field == "repository_identity"
        assert not lock.is_held

    def test_mismatched_stage_id_in_context_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            resume_workflow(
                _context(stage_id="AUTO-003"),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path),
            )
        assert exc_info.value.field == "stage_id"
        assert not lock.is_held

    def test_missing_authorization_record_rejected(self, tmp_path: Path) -> None:
        # A StateTransitionRecord shows CREATED -> AUTHORIZED, but no AuthorizationRecord was
        # ever persisted for it (e.g. history from before this repair, or written by bypassing
        # authorize()) — resume must not trust the transition alone.
        store = _store(tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CREATED", to_state="AUTHORIZED")
        )
        lock = _lock(tmp_path)
        with pytest.raises(MissingAuthorizationRecordError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held


class TestRepositoryLockIdentity:
    def test_lock_bound_to_a_different_repository_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path, repository_identity="github.com/org/some-other-repo")
        with pytest.raises(RepositoryLockIdentityMismatchError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_lock_bound_to_a_different_workflow_rejected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path, workflow_id="wf-different")
        with pytest.raises(RepositoryLockIdentityMismatchError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_arbitrary_caller_selected_lock_path_is_no_longer_constructible(
        self, tmp_path: Path
    ) -> None:
        # Finding 4 originally described a caller repeating the expected identity strings in
        # metadata while the lock's own physical path was an arbitrary location the caller chose.
        # AUTO002-F04 closed this at the primitive level: `RepositoryLock` no longer accepts a
        # `lock_path` argument at all, so this exact construction is now a TypeError, not merely
        # a resume-time rejection. `resume_workflow`'s own `lock.lock_path` binding check (below,
        # `test_correct_identity_but_wrong_repository_path_in_metadata_rejected`) remains as
        # defense-in-depth for the one axis that can still vary — the lock's `repository_path`
        # differing from what `current_binding` independently names.
        with pytest.raises(TypeError):
            RepositoryLock(  # type: ignore[misc]
                tmp_path / "not-the-canonical-location.lock",  # type: ignore[arg-type]
                workflow_id="wf-1",
                repository_identity="github.com/org/repo",
                repository_path=_repository_path(tmp_path),
            )

    def test_correct_identity_but_wrong_repository_path_in_metadata_rejected(
        self, tmp_path: Path
    ) -> None:
        # The lock's workflow_id/repository_identity match, but it was constructed for a
        # genuinely different repository_path than the one current_binding independently names —
        # since AUTO002-F04, this is the only way the lock's physical path and current_binding's
        # expectation can still diverge (lock_path is always derived from repository_path, so the
        # two can no longer be set inconsistently by construction).
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        other_repository_path = tmp_path / "a-different-repo"
        other_repository_path.mkdir()
        lock = _lock(tmp_path, repository_path=other_repository_path)
        assert lock.lock_path != canonical_lock_path(_repository_path(tmp_path))
        with pytest.raises(RepositoryLockIdentityMismatchError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_matching_lock_identity_proceeds_past_the_check(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()

    def test_symlink_aliased_repository_path_in_metadata_still_matches(
        self, tmp_path: Path
    ) -> None:
        # The lock's metadata.repository_path and current_binding.repository_path are different
        # *strings* naming the same physical repository through a symlink alias — this must
        # still succeed, since canonical_lock_path already collapsed the alias for the lock path
        # itself; the metadata-level check must tolerate the same aliasing, not reject on raw
        # string inequality.
        store = _store(tmp_path)
        real_repository_path = _repository_path(tmp_path)
        alias = tmp_path / "repo-alias"
        alias.symlink_to(real_repository_path)
        # authorization_record and current_binding agree (both the real path) — this test is
        # specifically about the lock metadata's repository_path being an alias of that same
        # path, not about Finding 3's separate authorization-record-vs-current-binding check.
        _seed_authorized(store, tmp_path)
        # Lock constructed via the alias path; metadata.repository_path records the alias string
        # verbatim (matching for_config's own behavior of never resolving repository_path).
        lock = _lock(tmp_path, repository_path=alias)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()


class TestRepositoryLockUnavailable:
    def test_lock_held_by_another_process_rejects_resume(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="CREATED", to_state="AUTHORIZED")
        )

        holder = _lock(tmp_path)
        holder.acquire()
        try:
            contender = _lock(tmp_path)
            with pytest.raises(RepositoryLockUnavailableError):
                resume_workflow(
                    _context(),
                    state_store=store,
                    lock=contender,
                    current_binding=_current_binding(tmp_path),
                )
            assert not contender.is_held
        finally:
            holder.release()

    def test_lock_unavailable_means_history_is_never_even_read(self, tmp_path: Path) -> None:
        # No history exists at all (would raise MissingPersistedStateError if reached); confirm
        # the lock check happens first and its own error type is what surfaces.
        store = _store(tmp_path)
        holder = _lock(tmp_path)
        holder.acquire()
        try:
            contender = _lock(tmp_path)
            with pytest.raises(RepositoryLockUnavailableError):
                resume_workflow(
                    _context(),
                    state_store=store,
                    lock=contender,
                    current_binding=_current_binding(tmp_path),
                )
        finally:
            holder.release()


class TestSuccessfulResume:
    def test_resumes_partial_workflow_mid_chain(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="PRECONDITIONS_CHECKED", to_state="BRANCH_CREATED"
            )
        )
        lock = _lock(tmp_path)

        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )

        assert isinstance(resumed, ResumedWorkflow)
        assert resumed.machine.state == WorkflowState.BRANCH_CREATED
        assert not resumed.machine.is_terminal
        assert len(resumed.transitions) == 3
        assert resumed.lock is lock
        assert resumed.lock.is_held  # lock remains held on success
        resumed.lock.release()

    def test_resumed_machine_still_enforces_transition_table(self, tmp_path: Path) -> None:
        # The reconstructed machine is a real WorkflowStateMachine, not a bypass: further
        # transitions on it are still validated exactly as any fresh machine would be.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            with pytest.raises(InvalidTransitionError):
                resumed.machine.transition_to(WorkflowState.DONE)  # illegal skip
            resumed.machine.transition_to(WorkflowState.PRECONDITIONS_CHECKED)  # legal
            assert resumed.machine.state == WorkflowState.PRECONDITIONS_CHECKED
        finally:
            resumed.lock.release()

    def test_single_record_history_resumes_to_authorized(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()

    def test_resume_after_a_fresh_process_restart_style_store(self, tmp_path: Path) -> None:
        writer_store = _store(tmp_path)
        _seed_authorized(writer_store, tmp_path)
        writer_store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )

        # A brand-new StateStore instance, as a resumed process would construct.
        resumed_store = _store(tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(),
            state_store=resumed_store,
            lock=lock,
            current_binding=_current_binding(tmp_path),
        )
        try:
            assert resumed.machine.state == WorkflowState.PRECONDITIONS_CHECKED
        finally:
            resumed.lock.release()

    def test_with_statement_releases_lock_on_exception(self, tmp_path: Path) -> None:
        # Requirement 9: "exception exits must always release the repository lock." Using
        # ResumedWorkflow as a context manager guarantees this even when the exception comes
        # from the caller's own code, not from resume_workflow itself.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(RuntimeError):
            with resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            ) as resumed:
                assert resumed.lock.is_held
                raise RuntimeError("caller-side failure mid-operation")
        assert not lock.is_held

    def test_with_statement_releases_lock_on_normal_exit(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        ) as resumed:
            assert resumed.lock.is_held
        assert not lock.is_held

    def test_release_lock_if_terminal_noop_while_in_progress(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert resumed.release_lock_if_terminal() is False
            assert resumed.lock.is_held
        finally:
            resumed.lock.release()

    def test_release_lock_if_terminal_releases_once_done(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state="PRECONDITIONS_CHECKED", to_state="CANCELLED")
        )
        lock = _lock(tmp_path)
        with pytest.raises(WorkflowAlreadyTerminalError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        # resume_workflow itself already released the lock for the terminal-rejection case;
        # release_lock_if_terminal is exercised directly against a machine reconstructed the
        # same way _reconstruct_workflow_for_evaluation would, to prove its own conditional logic
        # independent of resume_workflow's up-front terminal rejection.
        from agentos_workflow.orchestrator.engine import _INTERNAL_TOKEN
        from agentos_workflow.orchestrator.engine import ResumedWorkflow as _ResumedWorkflow
        from agentos_workflow.orchestrator.engine import WorkflowStateMachine as _Machine

        terminal_machine = _Machine(initial_state=WorkflowState.CANCELLED, _token=_INTERNAL_TOKEN)
        fresh_lock = _lock(tmp_path)
        fresh_lock.acquire()
        bundle = _ResumedWorkflow(
            machine=terminal_machine,
            transitions=[],
            lock=fresh_lock,
            state_store=store,
            repository_path=str(_repository_path(tmp_path)),
        )
        assert bundle.release_lock_if_terminal() is True
        assert not fresh_lock.is_held


class TestAuthorizationBindingDrift:
    """Finding 3: resume must independently validate every HUMAN_AUTHORIZATION_MODEL.md §2
    binding that has a live counterpart, against independently supplied current values — never
    against a copy of the persisted record — and fail closed to FAILED on the first drift.
    """

    def test_workflow_id_drift_detected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _tamper_persisted_authorization_record(tmp_path, store, workflow_id="wf-tampered")
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert exc_info.value.field == "workflow_id"
        assert not lock.is_held

    def test_repository_identity_drift_detected_independently_of_transition_history(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _tamper_persisted_authorization_record(
            tmp_path, store, repository_identity="github.com/org/drifted-repo"
        )
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert exc_info.value.field == "repository_identity"
        assert not lock.is_held

    def test_drift_message_reports_expected_and_found_in_argument_order(
        self, tmp_path: Path
    ) -> None:
        """The message must not transpose its two values (AUTO-008).

        The old message labelled `actual` as "bound value" and `expected` as "current value". That
        was backwards *here*: `_detect_authorization_binding_drift` passes the independently
        supplied current value as `expected` and the persisted record as `actual`, so a reader was
        told the live identity was the bound one and the tampered record was current — on the
        primary safety-invalidation path.

        It could not be fixed by simply swapping the words, because
        `_validate_live_resume_observation` passes those two sides the other way round; a fixed
        "bound/current" wording is necessarily wrong at one of the two. The message therefore
        states the reference and the finding in received-argument order, which holds at every raise
        site. Both attributes were always correct, so only the rendered text can catch this.
        """
        store = _store(tmp_path)
        _tamper_persisted_authorization_record(
            tmp_path, store, repository_identity="github.com/org/drifted-repo"
        )
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        error = exc_info.value
        message = str(error)
        # This path compares the live/current value (`expected`) against the persisted record
        # (`actual`); the tampered record is what was *found*.
        assert error.actual == "github.com/org/drifted-repo"
        assert error.expected != error.actual
        assert f"expected {error.expected!r}" in message
        assert f"found {error.actual!r}" in message
        # The decisive check: the two values appear in the order the constructor received them.
        assert message.index(f"expected {error.expected!r}") < message.index(
            f"found {error.actual!r}"
        )
        # And the message must not re-assert which side is the authorization binding, since the
        # two raise sites disagree about that.
        assert "bound value" not in message

    def test_repository_path_drift_detected(self, tmp_path: Path) -> None:
        # Simulates the repository having genuinely moved: the caller independently observes
        # the new location and constructs *both* current_binding and the lock from it (matching
        # what a real caller would do — a stale lock at the old location would instead be caught
        # by the Finding 4 lock-identity check, a separate concern from this binding-drift check).
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        moved_repository_path = tmp_path / "repo-moved"
        moved_repository_path.mkdir()
        lock = _lock(tmp_path, repository_path=moved_repository_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(
                    tmp_path, repository_path=str(moved_repository_path)
                ),
            )
        assert exc_info.value.field == "repository_path"
        assert not lock.is_held

    def test_stage_id_drift_detected_independently_of_transition_history(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _tamper_persisted_authorization_record(tmp_path, store, stage_id="AUTO-099")
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert exc_info.value.field == "stage_id"
        assert not lock.is_held

    def test_stage_contract_path_drift_detected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(
                    tmp_path,
                    stage_contract_path="docs/workflow-automation/stage-prompts/AUTO-099.md",
                ),
            )
        assert exc_info.value.field == "stage_contract_path"
        assert not lock.is_held

    def test_stage_contract_hash_drift_detected_after_simulated_restart(
        self, tmp_path: Path
    ) -> None:
        # The stage contract's contents changed on disk after authorization (e.g. someone edited
        # it); a freshly-computed hash, supplied through current_binding as a fresh StateStore
        # instance would after a process restart, no longer matches the bound hash.
        writer_store = _store(tmp_path)
        _seed_authorized(writer_store, tmp_path)
        resumed_store = _store(tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(),
                state_store=resumed_store,
                lock=lock,
                current_binding=_current_binding(
                    tmp_path, stage_contract_hash="sha256:changedcontents"
                ),
            )
        assert exc_info.value.field == "stage_contract_hash"
        assert not lock.is_held

    def test_baseline_branch_drift_detected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(baseline_branch="develop"),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path),
            )
        assert exc_info.value.field == "baseline_branch"
        assert not lock.is_held

    def test_baseline_commit_sha_drift_detected_changed_baseline_head(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(
                    tmp_path, baseline_commit_sha="ffffffffffffffffffffffffffffffffffffffff"
                ),
            )
        assert exc_info.value.field == "baseline_commit_sha"
        assert not lock.is_held

    def test_planned_stage_branch_drift_detected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(planned_stage_branch="feature/some-other-branch"),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path),
            )
        assert exc_info.value.field == "planned_stage_branch"
        assert not lock.is_held

    def test_engine_version_mismatch_detected(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path, engine_version="0.2.0"),
            )
        assert exc_info.value.field == "engine_version"
        assert not lock.is_held

    def test_corrupted_authorization_record_raises_before_drift_check(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        authorization_path = store.state_directory / "wf-1" / "authorization.json"
        authorization_path.write_text("not valid json", encoding="utf-8")
        lock = _lock(tmp_path)
        with pytest.raises(CorruptedAuthorizationRecordError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held

    def test_drift_rejection_persists_exactly_one_failed_transition(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        before = store.read_transitions("wf-1")
        assert len(before) == 1  # CREATED -> AUTHORIZED, from _seed_authorized
        with pytest.raises(AuthorizationBindingDriftError):
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path, engine_version="0.2.0"),
            )
        after = store.read_transitions("wf-1")
        assert len(after) == 2
        assert after[0] == before[0]  # the original record is untouched, not rewritten
        failure = after[1]
        assert failure.from_state == "AUTHORIZED"
        assert failure.to_state == "FAILED"
        assert failure.actor == "orchestrator"

    def test_drift_rejection_does_not_modify_the_authorization_record(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        authorization_path = store.state_directory / "wf-1" / "authorization.json"
        original_bytes = authorization_path.read_bytes()
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError):
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path, engine_version="0.2.0"),
            )
        assert authorization_path.read_bytes() == original_bytes

    def test_repeated_resume_after_drift_failure_is_idempotent(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        drifted_binding = _current_binding(tmp_path, engine_version="0.2.0")
        with pytest.raises(AuthorizationBindingDriftError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=drifted_binding
            )
        assert not lock.is_held

        # A second resume attempt against the now-FAILED workflow must not raise
        # AuthorizationBindingDriftError again or persist a second FAILED transition — the
        # workflow is already terminal, so the existing terminal-state check (step 6) rejects it
        # first, exactly like any other already-FAILED workflow.
        second_lock = _lock(tmp_path)
        with pytest.raises(WorkflowAlreadyTerminalError):
            resume_workflow(
                _context(), state_store=store, lock=second_lock, current_binding=drifted_binding
            )
        assert not second_lock.is_held

        transitions = store.read_transitions("wf-1")
        assert len(transitions) == 2  # CREATED -> AUTHORIZED, AUTHORIZED -> FAILED; never a third
        assert [t.to_state for t in transitions] == ["AUTHORIZED", "FAILED"]


def _seed_mismatched_transition_repository_path(
    tmp_path: Path,
    store: StateStore,
    *,
    transition_repository_path: Path,
    **authorization_record_overrides: object,
) -> None:
    """Persists a genuine `AuthorizationRecord` (via the same `_persist_authorization_record`
    primitive `authorize()` itself uses — `repository_path` is `_repository_path(tmp_path)`
    unless overridden), paired with a *directly-written* `CREATED -> AUTHORIZED`
    `StateTransitionRecord` whose own `repository_path` is `transition_repository_path` instead.

    This simulates a persisted transition history that consistently claims one repository path
    throughout — enough to satisfy `_validate_history_consistency`'s single-path uniformity check
    entirely on its own — while the actual persisted authorization evidence names a different one.
    Never goes through the real `authorize()` for the transition half, since `authorize()` itself
    always keeps the two in agreement by construction; this is exactly the gap the replay-time
    `repository_path` binding check in `_apply_validated_authorization` exists to close.
    """
    from agentos_workflow.orchestrator.engine import _persist_authorization_record

    record = _authorization_record(tmp_path, **authorization_record_overrides)
    _persist_authorization_record(store, record)
    store.record_transition(
        _transition(
            tmp_path=tmp_path,
            repository_path=str(transition_repository_path),
            from_state="CREATED",
            to_state="AUTHORIZED",
        )
    )


class TestReplayRepositoryPathBinding:
    """Release-gate finding: replay must bind every transition's `repository_path` to the
    canonical path bound by the persisted `AuthorizationRecord` — never accept a transition
    history that is merely internally self-consistent (agrees with itself) while disagreeing
    with what was actually authorized. Exercises `_apply_validated_authorization` via
    `resume_workflow`, the sole replay boundary every caller of `_replay_history` shares.
    """

    def test_transition_repository_path_disagreeing_with_authorization_rejected(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        repo_b = tmp_path / "repo-b"
        repo_b.mkdir()
        _seed_mismatched_transition_repository_path(
            tmp_path, store, transition_repository_path=repo_b
        )
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert exc_info.value.field == "repository_path"
        assert not lock.is_held

    def test_consistently_wrong_transition_repository_path_does_not_validate(
        self, tmp_path: Path
    ) -> None:
        """Every subsequent transition also claims the same wrong path B, satisfying
        `_validate_history_consistency`'s cross-record uniformity check entirely on its own — the
        history is not internally contradictory, it is just wrong relative to what was actually
        authorized. Internal self-consistency must never substitute for binding to the persisted
        `AuthorizationRecord`.
        """
        store = _store(tmp_path)
        repo_b = tmp_path / "repo-b"
        repo_b.mkdir()
        _seed_mismatched_transition_repository_path(
            tmp_path, store, transition_repository_path=repo_b
        )
        store.record_transition(
            _transition(
                tmp_path=tmp_path,
                repository_path=str(repo_b),
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
            )
        )
        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert exc_info.value.field == "repository_path"
        assert not lock.is_held

    def test_repository_identity_equal_but_path_different_rejected(self, tmp_path: Path) -> None:
        """`target_repository` (identity) is left at its default and therefore matches the
        authorization's `repository_identity` exactly — isolating that the rejection is driven
        specifically by the path mismatch, not by an identity mismatch a different, already-tested
        check would also catch.
        """
        store = _store(tmp_path)
        repo_b = tmp_path / "repo-b"
        repo_b.mkdir()
        record = _authorization_record(tmp_path)
        _seed_mismatched_transition_repository_path(
            tmp_path, store, transition_repository_path=repo_b
        )
        persisted_transition = store.read_transitions("wf-1")[0]
        assert persisted_transition.target_repository == record.repository_identity  # unchanged
        assert persisted_transition.repository_path != str(record.repository_path)

        lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert exc_info.value.field == "repository_path"
        assert not lock.is_held

    def test_symlink_aliased_transition_repository_path_still_matches(self, tmp_path: Path) -> None:
        """A transition history recorded through a symlink alias of the same real repository the
        authorization was bound to is not drift — canonical (`Path.resolve()`), not raw-string,
        comparison is what the contract requires here.
        """
        store = _store(tmp_path)
        real_repository_path = _repository_path(tmp_path)
        alias = tmp_path / "repo-alias"
        alias.symlink_to(real_repository_path)
        _seed_mismatched_transition_repository_path(
            tmp_path, store, transition_repository_path=alias
        )
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()

    def test_valid_repository_path_match_resumes_successfully(self, tmp_path: Path) -> None:
        """Baseline: a transition history whose `repository_path` genuinely agrees with the
        persisted authorization (the only way `authorize()` itself ever produces one) resumes
        without incident — the new binding check rejects only a genuine mismatch.
        """
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert resumed.machine.state == WorkflowState.PRECONDITIONS_CHECKED
        finally:
            resumed.lock.release()

    def test_repeated_rejection_is_deterministic_and_appends_no_failure_history(
        self, tmp_path: Path
    ) -> None:
        """Unlike `TestAuthorizationBindingDrift`'s step-8a drift (which durably fails the
        workflow so a second resume finds it terminal), this rejection happens while crossing
        `CREATED -> AUTHORIZED` itself, and `CREATED` has no `-> FAILED` edge in
        `ALLOWED_TRANSITIONS` — nothing is ever persisted for it (`resume_workflow`'s own
        docstring: "the workflow was never actually authorized in the first place"). Repeating the
        rejected resume attempt must therefore raise the identical error, every time, while the
        persisted history stays at exactly the one (mismatched) record it started with.
        """
        store = _store(tmp_path)
        repo_b = tmp_path / "repo-b"
        repo_b.mkdir()
        _seed_mismatched_transition_repository_path(
            tmp_path, store, transition_repository_path=repo_b
        )

        first_lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as first_exc:
            resume_workflow(
                _context(),
                state_store=store,
                lock=first_lock,
                current_binding=_current_binding(tmp_path),
            )
        assert not first_lock.is_held

        second_lock = _lock(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as second_exc:
            resume_workflow(
                _context(),
                state_store=store,
                lock=second_lock,
                current_binding=_current_binding(tmp_path),
            )
        assert not second_lock.is_held

        assert first_exc.value.field == second_exc.value.field == "repository_path"
        transitions = store.read_transitions("wf-1")
        assert len(transitions) == 1  # never grows: nothing is ever appended for this rejection


class TestResumedWorkflowTransitionTo:
    """Finding 5: `ResumedWorkflow.transition_to` is the sole sanctioned runtime path — it must
    validate and durably persist before ever exposing the new in-memory state, and must release
    the lock automatically on reaching a terminal state.
    """

    def test_transition_is_durably_persisted_before_being_applied_in_memory(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            resumed.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
            assert resumed.machine.state == WorkflowState.PRECONDITIONS_CHECKED
            # Read via a brand-new StateStore instance, as a resumed process would — proves this
            # was genuinely written to disk, not merely cached in the original store object.
            fresh_store = _store(tmp_path)
            persisted = fresh_store.read_transitions("wf-1")
            assert [t.to_state for t in persisted] == ["AUTHORIZED", "PRECONDITIONS_CHECKED"]
            assert resumed.transitions[-1] == persisted[-1]  # .transitions kept in sync
        finally:
            resumed.lock.release()

    def test_persistence_failure_leaves_machine_state_and_history_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            before_count = len(store.read_transitions("wf-1"))

            def _raise(*args: object, **kwargs: object) -> None:
                raise OSError("simulated disk-full failure persisting the transition")

            with monkeypatch.context() as patched:
                patched.setattr(store, "record_transition", _raise)
                with pytest.raises(OSError):
                    resumed.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
            # Transition succeeds in memory only if persistence succeeds: neither changed.
            assert resumed.machine.state == WorkflowState.AUTHORIZED
            assert len(store.read_transitions("wf-1")) == before_count
            assert len(resumed.transitions) == before_count
            assert resumed.lock.is_held  # not terminal; the failure must not release it either
        finally:
            resumed.lock.release()

    def test_invalid_transition_rejected_before_any_persistence_attempt(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            before_count = len(store.read_transitions("wf-1"))
            with pytest.raises(InvalidTransitionError):
                resumed.transition_to(WorkflowState.DONE, actor="orchestrator")  # illegal skip
            assert resumed.machine.state == WorkflowState.AUTHORIZED
            assert len(store.read_transitions("wf-1")) == before_count
        finally:
            resumed.lock.release()

    def test_direct_machine_transition_bypasses_persistence_unlike_the_wrapper(
        self, tmp_path: Path
    ) -> None:
        # Documents the contrast the wrapper exists to close: the lower-level
        # `.machine.transition_to` remains directly reachable (WorkflowStateMachine has no way
        # to know about StateStore/RepositoryLock), and using it does *not* persist anything —
        # proving `ResumedWorkflow.transition_to` is a genuinely different, durable path, not a
        # thin no-op wrapper.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            before_count = len(store.read_transitions("wf-1"))
            resumed.machine.transition_to(WorkflowState.PRECONDITIONS_CHECKED)  # bypass
            assert resumed.machine.state == WorkflowState.PRECONDITIONS_CHECKED
            assert len(store.read_transitions("wf-1")) == before_count  # nothing persisted
            assert resumed.lock.is_held  # and the lock lifecycle never even engaged
        finally:
            resumed.lock.release()

    def test_reaching_done_releases_the_lock_automatically(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        _write_happy_path_transitions_via_store(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        assert resumed.machine.state == WorkflowState.CLOSING
        new_state = resumed.transition_to(WorkflowState.DONE, actor="orchestrator")
        assert new_state == WorkflowState.DONE  # return value confirms the applied state
        assert not resumed.lock.is_held

    def test_reaching_failed_releases_the_lock_automatically(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        resumed.transition_to(WorkflowState.FAILED, actor="orchestrator")
        assert resumed.machine.state == WorkflowState.FAILED
        assert not resumed.lock.is_held

    def test_transition_after_reaching_terminal_rejected_without_re_release_or_duplicate_persist(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        resumed.transition_to(WorkflowState.FAILED, actor="orchestrator")
        assert not resumed.lock.is_held
        count_after_first = len(store.read_transitions("wf-1"))
        with pytest.raises(InvalidTransitionError):
            resumed.transition_to(WorkflowState.CANCELLED, actor="orchestrator")
        assert len(store.read_transitions("wf-1")) == count_after_first  # no duplicate write
        assert not resumed.lock.is_held  # release_lock_if_terminal is idempotent, no error

    def test_reaching_cancelled_releases_the_lock_automatically(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        resumed.transition_to(WorkflowState.CANCELLED, actor="human")
        assert resumed.machine.state == WorkflowState.CANCELLED
        assert not resumed.lock.is_held

    def test_non_terminal_transition_retains_the_lock(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        resumed.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        assert resumed.machine.state == WorkflowState.PRECONDITIONS_CHECKED
        assert resumed.lock.is_held
        resumed.lock.release()

    def test_exception_path_still_releases_lock_via_context_manager(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        with pytest.raises(InvalidTransitionError):
            with resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path),
            ) as resumed:
                resumed.transition_to(WorkflowState.DONE, actor="orchestrator")  # illegal skip
        assert not lock.is_held

    def test_resume_replay_appends_no_new_transition_records(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path, from_state="AUTHORIZED", to_state="PRECONDITIONS_CHECKED"
            )
        )
        before_count = len(store.read_transitions("wf-1"))
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            assert len(store.read_transitions("wf-1")) == before_count  # replay wrote nothing
            assert len(resumed.transitions) == before_count
        finally:
            resumed.lock.release()


class TestAUTO002F10ResumedWorkflowAuthorizedBypassRejected:
    """AUTO002-F10: `ResumedWorkflow` (unlike `WorkflowSession`) has no construction guard — its
    own docstring says so — so nothing stops a caller holding a `StateStore`/`RepositoryLock` from
    building one directly with a fresh, never-replayed `WorkflowStateMachine()` (which starts at
    `CREATED`), entirely bypassing `resume_workflow()`'s replay, evidence, and reuse checks.
    `(CREATED, AUTHORIZED)` is a legal edge in `ALLOWED_TRANSITIONS` and `actor="human"` is legal
    for it, so before this fix, `ResumedWorkflow.transition_to(AUTHORIZED, actor="human")` would
    reach `self.state_store.record_transition(new_record)` and durably persist a fabricated
    `CREATED -> AUTHORIZED` record — with no `AuthorizationRecord` ever validated — before its own
    trailing `self.machine.transition_to(to_state)` call finally raised `AuthorizationBypassError`.
    The corrupting write happened first every time; the rejection came too late.
    """

    def _fabricated_resumed_workflow(self, tmp_path: Path, store: StateStore) -> ResumedWorkflow:
        # A directly-constructed ResumedWorkflow, never produced by resume_workflow(): its
        # .machine is a brand-new WorkflowStateMachine() at CREATED, and .transitions is an
        # arbitrary, caller-supplied list — exactly what a caller holding only a StateStore and a
        # RepositoryLock could assemble without ever calling authorize() or resume_workflow().
        representative = _transition(tmp_path=tmp_path, from_state="FAILED", to_state="FAILED")
        lock = _lock(tmp_path)
        lock.acquire()
        return ResumedWorkflow(
            machine=WorkflowStateMachine(),
            transitions=[representative],
            lock=lock,
            state_store=store,
            repository_path=str(_repository_path(tmp_path)),
        )

    def test_fabricated_resumed_workflow_cannot_reach_authorized(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        resumed = self._fabricated_resumed_workflow(tmp_path, store)
        try:
            with pytest.raises(AuthorizationBypassError):
                resumed.transition_to(WorkflowState.AUTHORIZED, actor="human")
        finally:
            resumed.lock.release()

    def test_rejected_authorized_bypass_persists_nothing(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        resumed = self._fabricated_resumed_workflow(tmp_path, store)
        try:
            with pytest.raises(AuthorizationBypassError):
                resumed.transition_to(WorkflowState.AUTHORIZED, actor="human")
            # The durable write must never have happened at all — not merely been undone.
            assert store.read_transitions("wf-1") == []
        finally:
            resumed.lock.release()

    def test_rejected_authorized_bypass_leaves_in_memory_state_unchanged(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        resumed = self._fabricated_resumed_workflow(tmp_path, store)
        try:
            with pytest.raises(AuthorizationBypassError):
                resumed.transition_to(WorkflowState.AUTHORIZED, actor="human")
            assert resumed.machine.state == WorkflowState.CREATED
            assert resumed.transitions == [resumed.transitions[0]]  # unchanged, no append
        finally:
            resumed.lock.release()

    def test_rejection_happens_regardless_of_actor(self, tmp_path: Path) -> None:
        # Even an actor value that would otherwise be legal for CREATED -> AUTHORIZED ("human")
        # must not matter: the AUTHORIZED guard runs unconditionally, before from_state is even
        # read, so no actor value can reach the persisting code path for this to_state.
        store = _store(tmp_path)
        resumed = self._fabricated_resumed_workflow(tmp_path, store)
        try:
            with pytest.raises(AuthorizationBypassError):
                resumed.transition_to(WorkflowState.AUTHORIZED, actor="orchestrator")
            assert store.read_transitions("wf-1") == []
        finally:
            resumed.lock.release()

    def test_legitimately_resumed_workflow_also_rejects_authorized(self, tmp_path: Path) -> None:
        # A genuine resume_workflow() result is never at CREATED (replay always ends at AUTHORIZED
        # or later), so this was already unreachable via ALLOWED_TRANSITIONS alone — this test
        # pins that a legitimately resumed workflow is covered by the same guard, not merely the
        # fabricated case above.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            before_count = len(store.read_transitions("wf-1"))
            with pytest.raises(AuthorizationBypassError):
                resumed.transition_to(WorkflowState.AUTHORIZED, actor="human")
            assert len(store.read_transitions("wf-1")) == before_count
        finally:
            resumed.lock.release()


class TestActorSemantics:
    """Release-gate finding: `AUDIT_MODEL.md` §3 reserves `actor="human"` for the one
    authorization edge and the operator-cancellation edges. Every other, machine-driven edge must
    reject an inappropriate `"human"` actor, both when appended live
    (`ResumedWorkflow.transition_to`) and when replayed from persisted history.
    """

    def test_human_actor_rejected_on_ordinary_forward_machine_edge(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        try:
            before_count = len(store.read_transitions("wf-1"))
            with pytest.raises(InvalidActorForTransitionError):
                resumed.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="human")
            assert resumed.machine.state == WorkflowState.AUTHORIZED  # never mutated
            assert len(store.read_transitions("wf-1")) == before_count  # never persisted
        finally:
            resumed.lock.release()

    def test_valid_human_cancellation_actor_accepted(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        resumed.transition_to(WorkflowState.CANCELLED, actor="human")
        assert resumed.machine.state == WorkflowState.CANCELLED
        assert not resumed.lock.is_held

    def test_valid_human_authorization_actor_accepted(self, tmp_path: Path) -> None:
        # authorize() itself always records actor="human" for CREATED -> AUTHORIZED; a successful
        # _seed_authorized (used throughout this file) already proves this edge is accepted.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        transitions = store.read_transitions("wf-1")
        assert transitions[0].from_state == "CREATED"
        assert transitions[0].to_state == "AUTHORIZED"
        assert transitions[0].actor == "human"

    def test_non_human_actor_permitted_on_a_human_eligible_cancellation_edge(
        self, tmp_path: Path
    ) -> None:
        # Only an inappropriate "human" is ever rejected — an automated abort recorded as
        # "orchestrator" remains legal on the same edge.
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        lock = _lock(tmp_path)
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
        )
        resumed.transition_to(WorkflowState.CANCELLED, actor="orchestrator")
        assert resumed.machine.state == WorkflowState.CANCELLED

    def test_replay_rejects_invalid_actor_edge_history(self, tmp_path: Path) -> None:
        """A persisted `StateTransitionRecord` claiming `actor="human"` for an ordinary
        machine-driven edge is corruption, not a legitimate history — replay (via
        `resume_workflow`, and therefore every entry point built on `_replay_history`) must
        refuse it, never silently accept the forged actor.
        """
        store = _store(tmp_path)
        _seed_authorized(store, tmp_path)
        store.record_transition(
            _transition(
                tmp_path=tmp_path,
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                actor="human",
            )
        )
        lock = _lock(tmp_path)
        with pytest.raises(InconsistentHistoryError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=_current_binding(tmp_path)
            )
        assert not lock.is_held


class TestProductionLiveVerificationCannotBeReplacedByCopiedBinding:
    """AUTO002-F03 regression: production resume observes raw live facts itself."""

    def test_copied_persisted_binding_cannot_override_observed_engine_drift(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.tests.test_workflow_session import (
            _config,
            _current_binding,
            _start,
            _StaticObserver,
        )

        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first._resumed.lock.release()

        copied_binding = _current_binding(config)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            WorkflowSession.resume(
                config,
                workflow_id="wf-1",
                stage_id="AUTO-002",
                planned_stage_branch="feature/auto-002-orchestrator-state-machine",
                current_binding=copied_binding,
                _observer=_StaticObserver(config, engine_version="0.2.0"),
            )
        assert exc_info.value.field == "engine_version"


def _write_happy_path_transitions_via_store(store: StateStore, tmp_path: Path) -> None:
    for from_state, to_state in [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
        ("VALIDATING", "QA_RUNNING"),
        ("QA_RUNNING", "READY_TO_COMMIT"),
        ("READY_TO_COMMIT", "COMMITTED"),
        ("COMMITTED", "PUSHED"),
        ("PUSHED", "PR_OPEN"),
        ("PR_OPEN", "AUTO_MERGE_ENABLED"),
        ("AUTO_MERGE_ENABLED", "WAITING_FOR_CHECKS"),
        ("WAITING_FOR_CHECKS", "MERGED"),
        ("MERGED", "CLOSING"),
    ]:
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state=from_state, to_state=to_state)
        )
