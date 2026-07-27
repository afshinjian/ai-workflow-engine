"""Tests for the human-authorization binding in agentos_workflow.orchestrator.engine
(HUMAN_AUTHORIZATION_MODEL.md)."""

import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.observation import WorktreeChange
from agentos_workflow.orchestrator.engine import (
    _INTERNAL_TOKEN,  # whitebox: capability token
    AuthorizationBindingDriftError,
    AuthorizationBypassError,
    AuthorizationContext,
    AuthorizationRecord,
    AuthorizationRecordError,
    AuthorizationScopeMismatchError,
    InvalidTransitionError,
    MissingAuthorizationError,
    WorkflowState,
    WorkflowStateMachine,
    _classify_worktree,
    _WorktreeClassification,
    authorize,
    parse_authorization_record,
    validate_authorization_scope,
)
from agentos_workflow.orchestrator.state_store import StateStore, StateTransitionRecord


def _record(**overrides: object) -> AuthorizationRecord:
    defaults: dict[str, object] = {
        "workflow_id": "wf-1",
        "repository_identity": "github.com/org/repo",
        "repository_path": "/home/user/repo",
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


def _store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


class TestAuthorizationRecordSchema:
    def test_valid_record_parses(self) -> None:
        record = _record()
        assert record.workflow_id == "wf-1"
        assert record.authorized_by == "human-owner"

    def test_authorized_by_optional(self) -> None:
        record = _record(authorized_by=None)
        assert record.authorized_by is None

    def test_authorized_by_rejects_blank_string(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            _record(authorized_by="   ")

    def test_missing_required_field_rejected(self) -> None:
        raw = _record().model_dump()
        del raw["baseline_commit_sha"]
        with pytest.raises(ValidationError):
            AuthorizationRecord.model_validate(raw)

    def test_extra_field_forbidden(self) -> None:
        raw = _record().model_dump()
        raw["unexpected_field"] = "nope"
        with pytest.raises(ValidationError):
            AuthorizationRecord.model_validate(raw)

    def test_bad_timestamp_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ISO-8601"):
            _record(authorized_at="not-a-timestamp")

    def test_empty_workflow_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _record(workflow_id="")


class TestParseAuthorizationRecord:
    def test_parses_valid_dict(self) -> None:
        raw = _record().model_dump()
        parsed = parse_authorization_record(raw)
        assert parsed == _record()

    def test_malformed_missing_field_raises_authorization_record_error(self) -> None:
        raw = _record().model_dump()
        del raw["stage_contract_hash"]
        with pytest.raises(AuthorizationRecordError):
            parse_authorization_record(raw)

    def test_malformed_wrong_type_raises_authorization_record_error(self) -> None:
        raw = _record().model_dump()
        raw["workflow_id"] = 12345
        with pytest.raises(AuthorizationRecordError):
            parse_authorization_record(raw)

    def test_malformed_non_mapping_raises_authorization_record_error(self) -> None:
        with pytest.raises(AuthorizationRecordError):
            parse_authorization_record(["not", "a", "mapping"])


class TestValidateAuthorizationScope:
    def test_matching_record_and_context_passes(self) -> None:
        validate_authorization_scope(_context(), _record())  # must not raise

    def test_none_record_raises_missing_authorization_error(self) -> None:
        with pytest.raises(MissingAuthorizationError):
            validate_authorization_scope(_context(), None)

    def test_mismatched_workflow_id_rejected(self) -> None:
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            validate_authorization_scope(_context(workflow_id="wf-other"), _record())
        assert exc_info.value.field == "workflow_id"

    def test_mismatched_repository_identity_rejected(self) -> None:
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            validate_authorization_scope(
                _context(repository_identity="github.com/org/other-repo"), _record()
            )
        assert exc_info.value.field == "repository_identity"

    def test_mismatched_stage_id_rejected(self) -> None:
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            validate_authorization_scope(_context(stage_id="AUTO-003"), _record())
        assert exc_info.value.field == "stage_id"

    def test_mismatched_planned_branch_rejected(self) -> None:
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            validate_authorization_scope(
                _context(planned_stage_branch="feature/some-other-branch"), _record()
            )
        assert exc_info.value.field == "planned_stage_branch"

    def test_mismatched_baseline_branch_rejected(self) -> None:
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            validate_authorization_scope(
                _context(baseline_branch="recovery/project-baseline"), _record()
            )
        assert exc_info.value.field == "baseline_branch"

    def test_error_carries_expected_and_actual_values(self) -> None:
        with pytest.raises(AuthorizationScopeMismatchError) as exc_info:
            validate_authorization_scope(_context(workflow_id="wf-other"), _record())
        assert exc_info.value.expected == "wf-other"
        assert exc_info.value.actual == "wf-1"


class TestAuthorize:
    def test_successful_authorization_transitions_machine(self, tmp_path: Path) -> None:
        machine = WorkflowStateMachine()
        result = authorize(machine, _context(), _record(), state_store=_store(tmp_path))
        assert machine.state == WorkflowState.AUTHORIZED
        assert result == _record()

    def test_missing_record_leaves_machine_in_created(self, tmp_path: Path) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(MissingAuthorizationError):
            authorize(machine, _context(), None, state_store=_store(tmp_path))
        assert machine.state == WorkflowState.CREATED

    def test_scope_mismatch_leaves_machine_in_created(self, tmp_path: Path) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationScopeMismatchError):
            authorize(
                machine,
                _context(workflow_id="wf-other"),
                _record(),
                state_store=_store(tmp_path),
            )
        assert machine.state == WorkflowState.CREATED

    def test_authorization_is_single_use_per_workflow(self, tmp_path: Path) -> None:
        # Re-running authorize() against an already-AUTHORIZED machine must fail: CREATED is the
        # only source state for this edge, enforced by the transition table itself (Step 5A),
        # not by separate logic in this module.
        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)
        with pytest.raises(InvalidTransitionError):
            authorize(machine, _context(), _record(), state_store=store)
        assert machine.state == WorkflowState.AUTHORIZED  # unchanged by the rejected retry

    def test_cannot_authorize_from_a_non_created_state(self, tmp_path: Path) -> None:
        machine = WorkflowStateMachine(
            initial_state=WorkflowState.IMPLEMENTING, _token=_INTERNAL_TOKEN
        )
        with pytest.raises(InvalidTransitionError):
            authorize(machine, _context(), _record(), state_store=_store(tmp_path))
        assert machine.state == WorkflowState.IMPLEMENTING


class TestAuthorizeRequiresStateStore:
    """Stage contract repair Finding 1: "authorization must require a state store; absence of
    persistence must fail before mutation." `state_store` is a required keyword-only parameter,
    not an optional one — calling without it is a `TypeError` before `authorize()`'s own body
    (and therefore before any mutation) ever runs.
    """

    def test_missing_state_store_raises_type_error(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(TypeError):
            authorize(machine, _context(), _record())  # type: ignore[call-arg]
        assert machine.state == WorkflowState.CREATED

    def test_none_state_store_rejected(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises((TypeError, AttributeError)):
            authorize(machine, _context(), _record(), state_store=None)  # type: ignore[arg-type]
        assert machine.state == WorkflowState.CREATED


class TestCrossWorkflowScopeReuseRejected:
    def test_record_for_one_workflow_does_not_authorize_another(self, tmp_path: Path) -> None:
        record_for_wf1 = _record(workflow_id="wf-1")
        machine_for_wf2 = WorkflowStateMachine()
        context_for_wf2 = _context(workflow_id="wf-2")
        with pytest.raises(AuthorizationScopeMismatchError):
            authorize(
                machine_for_wf2,
                context_for_wf2,
                record_for_wf1,
                state_store=_store(tmp_path),
            )
        assert machine_for_wf2.state == WorkflowState.CREATED

    def test_record_for_one_workflow_still_authorizes_its_own_workflow(
        self, tmp_path: Path
    ) -> None:
        record_for_wf1 = _record(workflow_id="wf-1")
        machine_for_wf1 = WorkflowStateMachine()
        context_for_wf1 = _context(workflow_id="wf-1")
        authorize(machine_for_wf1, context_for_wf1, record_for_wf1, state_store=_store(tmp_path))
        assert machine_for_wf1.state == WorkflowState.AUTHORIZED


class TestCrossRepositoryScopeReuseRejected:
    def test_record_for_one_repository_does_not_authorize_another(self, tmp_path: Path) -> None:
        record_for_repo_a = _record(repository_identity="github.com/org/repo-a")
        machine_for_repo_b = WorkflowStateMachine()
        context_for_repo_b = _context(repository_identity="github.com/org/repo-b")
        with pytest.raises(AuthorizationScopeMismatchError):
            authorize(
                machine_for_repo_b,
                context_for_repo_b,
                record_for_repo_a,
                state_store=_store(tmp_path),
            )
        assert machine_for_repo_b.state == WorkflowState.CREATED

    def test_record_for_one_repository_still_authorizes_its_own_repository(
        self, tmp_path: Path
    ) -> None:
        record_for_repo_a = _record(repository_identity="github.com/org/repo-a")
        machine_for_repo_a = WorkflowStateMachine()
        context_for_repo_a = _context(repository_identity="github.com/org/repo-a")
        authorize(
            machine_for_repo_a,
            context_for_repo_a,
            record_for_repo_a,
            state_store=_store(tmp_path),
        )
        assert machine_for_repo_a.state == WorkflowState.AUTHORIZED


class TestCrossBranchScopeReuseRejected:
    def test_record_for_one_planned_branch_does_not_authorize_another(self, tmp_path: Path) -> None:
        record_for_branch_a = _record(planned_stage_branch="feature/branch-a")
        machine = WorkflowStateMachine()
        context_for_branch_b = _context(planned_stage_branch="feature/branch-b")
        with pytest.raises(AuthorizationScopeMismatchError):
            authorize(
                machine, context_for_branch_b, record_for_branch_a, state_store=_store(tmp_path)
            )
        assert machine.state == WorkflowState.CREATED


class TestAuthorizationPersistence:
    def test_successful_authorization_persists_audited_transition(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)

        transitions = store.read_transitions("wf-1")
        assert len(transitions) == 1
        recorded = transitions[0]
        assert recorded.from_state == "CREATED"
        assert recorded.to_state == "AUTHORIZED"
        assert recorded.actor == "human"
        assert recorded.target_repository == "github.com/org/repo"
        assert recorded.stage_id == "AUTO-002"
        assert recorded.timestamp == "2026-07-24T10:00:00+00:00"

    def test_failed_authorization_persists_nothing(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationScopeMismatchError):
            authorize(machine, _context(workflow_id="wf-other"), _record(), state_store=store)
        assert store.read_transitions("wf-1") == []
        assert store.read_transitions("wf-other") == []

    def test_persisted_transition_survives_a_fresh_store_instance(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)

        resumed_store = _store(tmp_path)
        assert [r.to_state for r in resumed_store.read_transitions("wf-1")] == ["AUTHORIZED"]


class TestAuthorizationRecordPersistence:
    """Stage contract requirement 2: persist every HUMAN_AUTHORIZATION_MODEL.md §2 binding field
    of the complete AuthorizationRecord, not just the StateTransitionRecord fact of it.
    """

    def test_full_record_persisted_and_reloadable(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _load_authorization_record

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)

        reloaded = _load_authorization_record(store, "wf-1")
        assert reloaded == _record()  # every field round-trips, not a subset

    def test_missing_record_reload_returns_none(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _load_authorization_record

        store = _store(tmp_path)
        assert _load_authorization_record(store, "wf-never-authorized") is None

    def test_corrupted_record_file_raises_on_reload(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import (
            CorruptedAuthorizationRecordError,
            _load_authorization_record,
        )

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)

        record_path = tmp_path / "state" / "wf-1" / "authorization.json"
        record_path.write_text("not valid json", encoding="utf-8")

        with pytest.raises(CorruptedAuthorizationRecordError):
            _load_authorization_record(store, "wf-1")

    def test_record_survives_a_fresh_store_instance(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _load_authorization_record

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)

        resumed_store = _store(tmp_path)
        assert _load_authorization_record(resumed_store, "wf-1") == _record()


class TestAuthorizeAtomicity:
    """Stage contract requirement 4: a transition is not complete unless persistence succeeds;
    no in-memory state may ever diverge from what is durably on disk.
    """

    def test_transition_write_failure_leaves_machine_in_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store(tmp_path)
        machine = WorkflowStateMachine()

        def _raise(*args: object, **kwargs: object) -> None:
            raise OSError("simulated disk failure persisting the state transition")

        monkeypatch.setattr(store, "record_transition", _raise)

        with pytest.raises(OSError):
            authorize(machine, _context(), _record(), state_store=store)
        assert machine.state == WorkflowState.CREATED

    def test_authorization_record_write_failure_leaves_machine_in_created_and_persists_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)
        machine = WorkflowStateMachine()

        def _raise(*args: object, **kwargs: object) -> None:
            raise OSError("simulated disk failure persisting the authorization record")

        monkeypatch.setattr(engine_module, "_publish_authorization_record", _raise)

        with pytest.raises(OSError):
            authorize(machine, _context(), _record(), state_store=store)
        assert machine.state == WorkflowState.CREATED
        # The authorization record is persisted *before* the transition (fixed ordering): if the
        # record write itself fails, the transition is never even attempted.
        assert store.read_transitions("wf-1") == []

    def test_authorization_record_persisted_before_transition_is_attempted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If the *transition* write fails (the second persistence step), the authorization
        # record from the first step must still be on disk — proving the fixed ordering (record
        # first, transition second, in-memory mutation last), not some other order that could
        # leave a transition record with no backing authorization.
        from agentos_workflow.orchestrator.engine import _load_authorization_record

        store = _store(tmp_path)
        machine = WorkflowStateMachine()

        def _raise(*args: object, **kwargs: object) -> None:
            raise OSError("simulated disk failure persisting the state transition")

        monkeypatch.setattr(store, "record_transition", _raise)

        with pytest.raises(OSError):
            authorize(machine, _context(), _record(), state_store=store)
        assert machine.state == WorkflowState.CREATED
        assert _load_authorization_record(store, "wf-1") == _record()


class TestStructuralNonBypassability:
    """Finding 1 adversarial suite: every way to reach AUTHORIZED other than authorize() must
    fail, and a leading underscore alone must not be what stops any of them.

    `AUTHORIZED` is never gated by presenting *any* value — not a token, not a flag, not a
    caller's claimed identity. Both legitimate paths (`authorize()`, and the replay section's
    `_apply_validated_authorization`) independently load and validate real, persisted
    authorization evidence from a `StateStore` in the same call that mutates state.
    `test_ordinary_external_import_of_internal_token_can_reach_authorized` below is a permanent
    regression test proving a bare, importable capability object can never satisfy this. Other,
    lower-sensitivity non-CREATED construction (`VALIDATING`, `FAILED`, etc., for isolated unit
    tests) still legitimately uses `_INTERNAL_TOKEN` — that surface was not the reported defect
    and is unchanged. See `TestFinding1ReplayCannotFabricateAuthorization` below for the
    adversarial suite covering the actual reported bypass (`_replay_history` with
    caller-fabricated, unpersisted records).
    """

    def test_direct_public_transition_to_authorized_rejected(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine.transition_to(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED

    def test_direct_construction_at_authorized_rejected(self) -> None:
        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED)

    def test_direct_construction_at_authorized_rejected_even_with_the_real_token(self) -> None:
        # AUTHORIZED takes no token bypass at all, unlike other non-CREATED states — there is no
        # legitimate caller for it (authorize() always constructs at CREATED and transitions
        # forward; replay always starts at CREATED and walks forward), so presenting even the
        # genuine internal token must not help.
        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED, _token=_INTERNAL_TOKEN)

    def test_direct_construction_at_any_other_non_created_state_rejected_without_token(
        self,
    ) -> None:
        # Not just AUTHORIZED: fabricating a machine already at ANY later state, without
        # presenting the internal capability token, is refused — construction always starts at
        # CREATED for ordinary callers.
        for state in (
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.IMPLEMENTING,
            WorkflowState.DONE,
            WorkflowState.FAILED,
        ):
            with pytest.raises(AuthorizationBypassError):
                WorkflowStateMachine(initial_state=state)

    def test_construction_at_non_created_non_authorized_state_succeeds_with_the_token(
        self,
    ) -> None:
        # This lower-sensitivity, whitebox/testing-only capability is unaffected by the
        # AUTHORIZED-specific redesign below — it never claimed to represent "authorization."
        machine = WorkflowStateMachine(
            initial_state=WorkflowState.VALIDATING, _token=_INTERNAL_TOKEN
        )
        assert machine.state == WorkflowState.VALIDATING

    def test_direct_invocation_of_apply_transition_rejected(self) -> None:
        # Calling _apply_transition(AUTHORIZED) directly is rejected unconditionally, regardless
        # of caller or anything passed — this method never applies AUTHORIZED for anyone.
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine._apply_transition(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED

    def test_ordinary_external_import_of_internal_token_can_reach_authorized(self) -> None:
        """The adversarial check that found the original design's flaw, kept as a permanent
        regression test: an "ordinary external caller" needs nothing more than a normal import
        to obtain `_INTERNAL_TOKEN` — proving a token-based check can never legitimately gate
        AUTHORIZED, since possessing the token proves nothing about who the real caller is. This
        must now fail (the fix no longer accepts *any* token for AUTHORIZED — see
        `test_direct_construction_at_authorized_rejected_even_with_the_real_token` and
        `test_apply_transition_stolen_token_does_not_help` above/below)."""
        from agentos_workflow.orchestrator.engine import (
            _INTERNAL_TOKEN as stolen_token,  # exactly what an external importer would do
        )

        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine._apply_transition(WorkflowState.AUTHORIZED)  # token is not even accepted
        assert machine.state == WorkflowState.CREATED
        # Confirm the import itself is trivially possible (that was never in question — it's
        # *presenting* it that must now fail) and that even the genuine object is powerless here.
        assert stolen_token is _INTERNAL_TOKEN
        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED, _token=stolen_token)

    def test_apply_transition_stolen_token_does_not_help(self) -> None:
        machine = WorkflowStateMachine()

        class _Forged:
            """A caller-fabricated object — irrelevant now, since AUTHORIZED is never applied by
            _apply_transition for anyone, regardless of any value presented."""

        with pytest.raises(AuthorizationBypassError):
            machine._apply_transition(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED
        # _apply_transition no longer even accepts a _token kwarg for any purpose.
        with pytest.raises(TypeError):
            machine._apply_transition(WorkflowState.AUTHORIZED, _token=_Forged())  # type: ignore[call-arg]

    def test_only_authorize_and_replay_can_reach_authorized_via_apply_transition(
        self, tmp_path: Path
    ) -> None:
        # Positive control: confirms both legitimate paths — a fresh authorize() and a resume
        # that replays genuinely persisted, validated history — actually reach AUTHORIZED, not
        # merely that everything else is rejected (which a permanently-broken path would also do).
        store = _store(tmp_path)
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        record = _record(repository_path=str(repository_path))
        machine = WorkflowStateMachine()
        authorize(machine, _context(), record, state_store=store)  # via authorize()
        assert machine.state == WorkflowState.AUTHORIZED

        from agentos_workflow.orchestrator.engine import (
            CurrentAuthorizationBinding,
            resume_workflow,
        )
        from agentos_workflow.orchestrator.lock import RepositoryLock

        lock = RepositoryLock(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path=repository_path,
        )
        current_binding = CurrentAuthorizationBinding.model_validate(
            {
                "repository_path": str(repository_path),
                "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
                "stage_contract_hash": "sha256:deadbeef",
                "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
                "engine_version": "0.1.0",
            }
        )
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=current_binding
        )  # via a validated replay of the persisted history
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()


def _fabricated_created_to_authorized_record(**overrides: object) -> StateTransitionRecord:
    defaults: dict[str, object] = {
        "workflow_id": "wf-1",
        "target_repository": "repo",
        "repository_path": "/home/user/repo",  # matches _record()'s own default
        "stage_id": "S",
        "from_state": "CREATED",
        "to_state": "AUTHORIZED",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "actor": "human",
        "gate_evidence_ref": None,
    }
    defaults.update(overrides)
    return StateTransitionRecord.model_validate(defaults)


class TestFinding1ReplayCannotFabricateAuthorization:
    """Reviewer-reported bypass: `_replay_history([fabricated_record])` reached AUTHORIZED with
    no `StateStore` and no persisted `AuthorizationRecord` at all — the entire "sanctioned
    caller" mechanism trusted *which function* was calling `_apply_transition`, and
    `_replay_history` was one of the two sanctioned callers despite performing no authorization
    validation of its own. The fix removes that trust decision entirely: `_replay_history` now
    requires a `StateStore` and independently loads and validates a persisted
    `AuthorizationRecord` before ever crossing `CREATED -> AUTHORIZED`, regardless of who calls
    it or what the replayed `StateTransitionRecord` claims.
    """

    def test_exact_reported_reproduction_now_fails_closed(self) -> None:
        """The literal repro from the report: `_replay_history([record])`, no StateStore, no
        AuthorizationRecord, nothing but an in-memory fabricated record. Must no longer reach
        AUTHORIZED — it must not even be callable this way."""
        from agentos_workflow.orchestrator.engine import _replay_history

        record = _fabricated_created_to_authorized_record()
        with pytest.raises(TypeError):
            _replay_history([record])  # type: ignore[call-arg]

    def test_replay_with_no_state_store_cannot_reach_authorized(self) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        record = _fabricated_created_to_authorized_record()
        with pytest.raises(TypeError):
            _replay_history([record])  # type: ignore[call-arg]
        with pytest.raises((TypeError, AttributeError)):
            _replay_history(
                [record], state_store=None, workflow_id="wf-1"  # type: ignore[arg-type]
            )

    def test_replay_with_state_store_but_no_persisted_record_fails(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)  # empty: nothing ever persisted for wf-1
        record = _fabricated_created_to_authorized_record()
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history([record], state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "transition_history"

    def test_replay_with_malformed_persisted_record_fails(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorization_path = tmp_path / "state" / "wf-1" / "authorization.json"
        authorization_path.parent.mkdir(parents=True)
        authorization_path.write_text("not valid json", encoding="utf-8")
        record = _fabricated_created_to_authorized_record()
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history([record], state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "transition_history"

    def test_replay_of_scope_mismatched_persisted_record_fails_via_resume(
        self, tmp_path: Path
    ) -> None:
        """A well-formed, persisted `AuthorizationRecord` that has been tampered to disagree
        with the workflow it is filed under must still fail resume end-to-end. Full field-by-
        field drift coverage lives in test_engine_resume.py::TestAuthorizationBindingDrift; this
        is the self-contained representative case for this regression suite."""
        from agentos_workflow.orchestrator.engine import (
            AuthorizationBindingDriftError,
            CurrentAuthorizationBinding,
            resume_workflow,
        )
        from agentos_workflow.orchestrator.lock import RepositoryLock

        store = _store(tmp_path)
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        record = _record(repository_path=str(repository_path))
        authorize(WorkflowStateMachine(), _context(), record, state_store=store)

        tampered = _record(repository_path=str(repository_path), stage_id="AUTO-099")
        (store.state_directory / "wf-1" / "authorization.json").write_text(
            tampered.model_dump_json(), encoding="utf-8"
        )

        lock = RepositoryLock(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path=repository_path,
        )
        current_binding = CurrentAuthorizationBinding.model_validate(
            {
                "repository_path": str(repository_path),
                "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
                "stage_contract_hash": "sha256:deadbeef",
                "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
                "engine_version": "0.1.0",
            }
        )
        with pytest.raises(AuthorizationBindingDriftError):
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=current_binding
            )
        assert not lock.is_held

    def test_internal_token_import_cannot_fabricate_a_resumable_authorized_machine(self) -> None:
        from agentos_workflow.orchestrator.engine import _INTERNAL_TOKEN as stolen_token

        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED, _token=stolen_token)
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine._apply_transition(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED

    def test_direct_construction_and_direct_transition_to_authorized_remain_rejected(self) -> None:
        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED)
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine.transition_to(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED

    def test_legitimate_authorize_persists_before_exposing_authorized(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _load_authorization_record

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        authorize(machine, _context(), _record(), state_store=store)
        assert machine.state == WorkflowState.AUTHORIZED
        assert _load_authorization_record(store, "wf-1") == _record()
        assert store.read_transitions("wf-1")[-1].to_state == "AUTHORIZED"

    def test_legitimate_resume_workflow_still_resumes_valid_persisted_history(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            CurrentAuthorizationBinding,
            resume_workflow,
        )
        from agentos_workflow.orchestrator.lock import RepositoryLock

        store = _store(tmp_path)
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        record = _record(repository_path=str(repository_path))
        authorize(WorkflowStateMachine(), _context(), record, state_store=store)

        lock = RepositoryLock(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path=repository_path,
        )
        current_binding = CurrentAuthorizationBinding.model_validate(
            {
                "repository_path": str(repository_path),
                "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
                "stage_contract_hash": "sha256:deadbeef",
                "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
                "engine_version": "0.1.0",
            }
        )
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=current_binding
        )
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()

    def test_replay_history_succeeds_with_a_genuinely_persisted_record(
        self, tmp_path: Path
    ) -> None:
        """Positive control: the hardened `_replay_history` is not merely broken for everyone —
        it succeeds precisely when backed by real, persisted authorization evidence."""
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        records = store.read_transitions("wf-1")
        machine = _replay_history(records, state_store=store, workflow_id="wf-1")
        assert machine.state == WorkflowState.AUTHORIZED


class TestFinding1CorrectivePass:
    """Second, corrective adversarial suite: the first remediation still left three callable,
    evidence-free ways to reach `AUTHORIZED`, all confirmed by the Human Owner's own review:

    1. `WorkflowStateMachine._set_state_authorized()` was a bare mutator — callable directly,
       with zero authorization evidence, and it succeeded.
    2. `_replay_history_state_only()` was a second, unhardened replay helper (used by the retry/
       reconciliation section) that accepted a caller-fabricated `CREATED -> AUTHORIZED` record
       with no `StateStore` and no persisted `AuthorizationRecord` at all.
    3. `_apply_validated_authorization` only checked that *some* parseable `AuthorizationRecord`
       existed under the supplied workflow ID — never that it actually belonged to the replayed
       history's own repository/stage.

    All three are closed here: there is now exactly one replay primitive (`_replay_history`),
    used by every production reconstruction path (`resume_workflow`, and — through it —
    `evaluate_repair_attempt`, `evaluate_initial_execution_failure`,
    `record_repair_attempt_started`, `record_repair_attempt`,
    `record_initial_execution_attempt_started`, `record_initial_execution_attempt`), and it
    validates the loaded `AuthorizationRecord`'s `workflow_id`/`repository_identity`/`stage_id`
    against the replayed history's own `StateTransitionRecord` fields, plus `from_state ==
    "CREATED"` and `actor == "human"`, before ever mutating state. No callable, public or
    private, sets `.state` to `AUTHORIZED` without performing this validation in the same call.
    """

    def test_bare_mutator_no_longer_exists(self) -> None:
        machine = WorkflowStateMachine()
        assert not hasattr(machine, "_set_state_authorized")
        with pytest.raises(AttributeError):
            machine._set_state_authorized()  # type: ignore[attr-defined]
        assert machine.state == WorkflowState.CREATED

    def test_weak_replay_helper_no_longer_exists(self) -> None:
        import agentos_workflow.orchestrator.engine as engine_module

        assert not hasattr(engine_module, "_replay_history_state_only")
        with pytest.raises(ImportError):
            from agentos_workflow.orchestrator.engine import (  # type: ignore[attr-defined] # noqa: F401
                _replay_history_state_only,
            )

    def test_replay_rejects_record_for_another_workflow(self, tmp_path: Path) -> None:
        """The persisted AuthorizationRecord exists, parses, and even lives at the path keyed by
        the replayed history's own workflow_id — but its own `workflow_id` field names a
        different workflow (simulating tampering/corruption, the only way this can occur since
        `authorize()` itself always writes a self-consistent record). `_replay_history` must
        reject this directly, not merely `resume_workflow`."""
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        tampered = _record(workflow_id="wf-tampered")
        (store.state_directory / "wf-1" / "authorization.json").write_text(
            tampered.model_dump_json(), encoding="utf-8"
        )
        records = store.read_transitions("wf-1")
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(records, state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "workflow_id"

    def test_replay_rejects_record_for_another_stage(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        tampered = _record(stage_id="AUTO-099")
        (store.state_directory / "wf-1" / "authorization.json").write_text(
            tampered.model_dump_json(), encoding="utf-8"
        )
        records = store.read_transitions("wf-1")
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(records, state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "stage_id"

    def test_replay_rejects_record_for_another_repository_identity(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        tampered = _record(repository_identity="github.com/org/some-other-repo")
        (store.state_directory / "wf-1" / "authorization.json").write_text(
            tampered.model_dump_json(), encoding="utf-8"
        )
        records = store.read_transitions("wf-1")
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(records, state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "repository_identity"

    def test_replay_rejects_non_human_actor_on_the_authorized_edge(self, tmp_path: Path) -> None:
        """`AUDIT_MODEL.md` §3: `actor` is `"human"` for the authorization edge specifically. A
        `StateTransitionRecord` claiming `CREATED -> AUTHORIZED` with any other actor is rejected
        even when a real, matching `AuthorizationRecord` is persisted — the transition record
        itself must carry the required human-actor shape, not just point at a valid record."""
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        forged_history = [_fabricated_created_to_authorized_record(actor="orchestrator")]
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(forged_history, state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "transition_history"

    def test_replay_rejects_authorized_edge_not_starting_at_created(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        forged_history = [
            _fabricated_created_to_authorized_record(from_state="PRECONDITIONS_CHECKED")
        ]
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(forged_history, state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "transition_history"


class TestAUTO002F01AuthorizationInvariantsCannotBeBypassed:
    """AUTO002-F01 (release-gate review, sixth remediation round): three concrete, reproduced
    bypasses the prior "structural non-bypassability" suite did not actually close.

    1. `machine._state = WorkflowState.AUTHORIZED` — ordinary Python attribute assignment against
       the leading-underscore `_state` field — silently succeeded, since a leading underscore is
       convention only and Python does not enforce it.
    2. `authorize()` persisted both the `AuthorizationRecord` and the paired `StateTransitionRecord`
       *before* checking `machine.state` was actually `CREATED` — so a second `authorize()` call
       against an already-`AUTHORIZED` (or any non-`CREATED`) machine durably appended an illegal
       second `CREATED -> AUTHORIZED` transition to disk before the in-memory transition was
       rejected.
    3. `_replay_history`/`_apply_validated_authorization` validated a caller-supplied
       `StateTransitionRecord` against a persisted `AuthorizationRecord`, but never verified the
       replayed transition itself was ever actually durably recorded in the state store — an
       orphaned `AuthorizationRecord` (persisted with no paired transition at all) plus a
       caller-fabricated, never-persisted `CREATED -> AUTHORIZED` record was enough to reach
       `AUTHORIZED`.

    All three are closed: (1) `WorkflowStateMachine.__setattr__` unconditionally rejects ordinary
    assignment of `AUTHORIZED` to `_state`; (2) `authorize()` now calls
    `validate_transition(machine.state, AUTHORIZED)` before any persistence; (3)
    `_apply_validated_authorization` now independently re-reads `state_store.read_transitions(...)`
    and requires a genuine, durably-recorded `CREATED -> AUTHORIZED`/`actor="human"` transition to
    actually be present before ever crossing the gate.
    """

    def test_direct_state_assignment_cannot_produce_authoritative_authorized(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine._state = WorkflowState.AUTHORIZED
        assert machine.state == WorkflowState.CREATED
        assert not machine.is_terminal

    def test_object_setattr_cannot_produce_authoritative_authorized(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            object.__setattr__(machine, "_state", WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED
        assert not machine.is_terminal

    def test_instance_dictionary_injection_cannot_produce_authoritative_authorized(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(AttributeError):
            machine.__dict__["_state"] = WorkflowState.AUTHORIZED
        assert machine.state == WorkflowState.CREATED
        assert not machine.is_terminal

    def test_second_authorize_raises_before_persistence_and_preserves_all_bytes(
        self, tmp_path: Path
    ) -> None:
        store = _store(tmp_path)
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        context = _context()
        record = _record(repository_path=str(repository_path))
        machine = WorkflowStateMachine()
        authorize(machine, context, record, state_store=store)
        assert machine.state == WorkflowState.AUTHORIZED

        transitions_path = store.state_directory / "wf-1" / "transitions.jsonl"
        authorization_path = store.state_directory / "wf-1" / "authorization.json"
        before_transitions_bytes = transitions_path.read_bytes()
        before_authorization_bytes = authorization_path.read_bytes()
        before_count = len(store.read_transitions("wf-1"))
        assert before_count == 1

        with pytest.raises(InvalidTransitionError):
            authorize(machine, context, record, state_store=store)

        assert machine.state == WorkflowState.AUTHORIZED  # unchanged by the rejected call
        assert len(store.read_transitions("wf-1")) == before_count  # still exactly one
        assert transitions_path.read_bytes() == before_transitions_bytes
        assert authorization_path.read_bytes() == before_authorization_bytes

    def test_authorize_from_every_non_created_state_writes_nothing(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        # AUTHORIZED itself is excluded: WorkflowStateMachine.__init__ already rejects
        # constructing directly at AUTHORIZED unconditionally (even with the real token — see
        # TestStructuralNonBypassability), so it can never reach authorize() this way at all; the
        # "second authorize() against an already-AUTHORIZED machine" case is covered separately by
        # test_second_authorize_raises_before_persistence_and_preserves_all_bytes above.
        for index, state in enumerate(
            (
                WorkflowState.PRECONDITIONS_CHECKED,
                WorkflowState.IMPLEMENTING,
                WorkflowState.VALIDATING,
                WorkflowState.DONE,
                WorkflowState.FAILED,
                WorkflowState.CANCELLED,
            )
        ):
            workflow_id = f"wf-non-created-{index}"
            machine = WorkflowStateMachine(initial_state=state, _token=_INTERNAL_TOKEN)
            context = _context(workflow_id=workflow_id)
            record = _record(workflow_id=workflow_id)

            with pytest.raises(InvalidTransitionError):
                authorize(machine, context, record, state_store=store)

            assert machine.state is state  # unchanged
            assert store.read_transitions(workflow_id) == []
            authorization_path = store.state_directory / workflow_id / "authorization.json"
            assert not authorization_path.exists()

    def test_orphaned_authorization_plus_fabricated_transition_cannot_replay_to_authorized(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            _persist_authorization_record,
            _replay_history,
        )

        store = _store(tmp_path)
        record = _record()
        _persist_authorization_record(store, record)  # orphaned: no transition ever recorded
        assert store.read_transitions("wf-1") == []

        fabricated = _fabricated_created_to_authorized_record()
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history([fabricated], state_store=store, workflow_id="wf-1")
        assert exc_info.value.field == "transition_history"
        assert store.read_transitions("wf-1") == []  # replay attempt wrote nothing

    def test_repeated_replay_rejection_is_deterministic_and_writes_nothing(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            _persist_authorization_record,
            _replay_history,
        )

        store = _store(tmp_path)
        record = _record()
        _persist_authorization_record(store, record)
        authorization_path = store.state_directory / "wf-1" / "authorization.json"
        before_bytes = authorization_path.read_bytes()
        fabricated = _fabricated_created_to_authorized_record()

        first_fields = []
        for _ in range(2):
            with pytest.raises(AuthorizationBindingDriftError) as exc_info:
                _replay_history([fabricated], state_store=store, workflow_id="wf-1")
            first_fields.append(exc_info.value.field)

        assert first_fields == ["transition_history", "transition_history"]
        assert store.read_transitions("wf-1") == []
        assert authorization_path.read_bytes() == before_bytes

    def test_legitimate_persisted_authorization_and_history_still_replay_successfully(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            CurrentAuthorizationBinding,
            _replay_history,
            resume_workflow,
        )
        from agentos_workflow.orchestrator.lock import RepositoryLock

        store = _store(tmp_path)
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        record = _record(repository_path=str(repository_path))
        authorize(WorkflowStateMachine(), _context(), record, state_store=store)

        # Whitebox: the replay primitive itself, fed genuinely persisted records.
        records = store.read_transitions("wf-1")
        machine = _replay_history(records, state_store=store, workflow_id="wf-1")
        assert machine.state == WorkflowState.AUTHORIZED

        # Blackbox: the full resume_workflow path, through the real public orchestrator API.
        lock = RepositoryLock(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path=repository_path,
        )
        current_binding = CurrentAuthorizationBinding.model_validate(
            {
                "repository_path": str(repository_path),
                "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
                "stage_contract_hash": "sha256:deadbeef",
                "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
                "engine_version": "0.1.0",
            }
        )
        resumed = resume_workflow(
            _context(), state_store=store, lock=lock, current_binding=current_binding
        )
        try:
            assert resumed.machine.state == WorkflowState.AUTHORIZED
        finally:
            resumed.lock.release()

    def test_direct_construction_public_transition_and_underscore_paths_remain_rejected(
        self,
    ) -> None:
        """Regression re-confirmation (not new coverage on its own — see
        `TestStructuralNonBypassability` for the dedicated suite) that every previously-closed
        bypass remains closed alongside the three newly-closed ones above, all asserted together
        against one machine instance.
        """
        with pytest.raises(AuthorizationBypassError):
            WorkflowStateMachine(initial_state=WorkflowState.AUTHORIZED)

        machine = WorkflowStateMachine()
        with pytest.raises(AuthorizationBypassError):
            machine.transition_to(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED

        with pytest.raises(AuthorizationBypassError):
            machine._apply_transition(WorkflowState.AUTHORIZED)
        assert machine.state == WorkflowState.CREATED

        with pytest.raises(AuthorizationBypassError):
            machine._state = WorkflowState.AUTHORIZED
        assert machine.state == WorkflowState.CREATED


class TestAUTO002F01ExactPersistedReplayMembership:
    """Caller-supplied replay records are assertions, never authoritative state."""

    @staticmethod
    def _seed(
        tmp_path: Path, *, include_second_transition: bool = False
    ) -> tuple[StateStore, Path]:
        store = _store(tmp_path)
        repository_path = tmp_path / "repo"
        repository_path.mkdir(exist_ok=True)
        authorize(
            WorkflowStateMachine(),
            _context(),
            _record(repository_path=str(repository_path)),
            state_store=store,
        )
        if include_second_transition:
            authorization = store.read_transitions("wf-1")[0]
            store.record_transition(
                authorization.model_copy(
                    update={
                        "from_state": WorkflowState.AUTHORIZED.value,
                        "to_state": WorkflowState.PRECONDITIONS_CHECKED.value,
                        "timestamp": "2026-07-24T10:01:00+00:00",
                        "actor": "orchestrator",
                        "gate_evidence_ref": "audit/preconditions.json",
                    }
                )
            )
        return store, repository_path

    @staticmethod
    def _persisted_bytes(store: StateStore) -> tuple[bytes, bytes]:
        workflow_root = store.state_directory / "wf-1"
        return (
            (workflow_root / "transitions.jsonl").read_bytes(),
            (workflow_root / "authorization.json").read_bytes(),
        )

    @pytest.mark.parametrize(
        ("case", "updates"),
        (
            ("changed-timestamp", {"timestamp": "2099-01-01T00:00:00+00:00"}),
            ("changed-evidence", {"gate_evidence_ref": "fabricated:evidence"}),
            ("changed-actor", {"actor": "orchestrator"}),
            ("changed-repository", {"target_repository": "github.com/org/other"}),
            ("changed-stage", {"stage_id": "AUTO-099"}),
            ("changed-source", {"from_state": "PRECONDITIONS_CHECKED"}),
            ("changed-destination", {"to_state": "CANCELLED"}),
            ("another-workflow", {"workflow_id": "wf-other"}),
        ),
        ids=lambda value: value if isinstance(value, str) else None,
    )
    def test_changed_load_bearing_field_is_not_persisted_membership(
        self, tmp_path: Path, case: str, updates: dict[str, object]
    ) -> None:
        del case
        from agentos_workflow.orchestrator.engine import _replay_history

        store, _ = self._seed(tmp_path)
        persisted = store.read_transitions("wf-1")
        supplied = [persisted[0].model_copy(update=updates)]
        before = self._persisted_bytes(store)

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(supplied, state_store=store, workflow_id="wf-1")

        assert exc_info.value.field == "transition_history"
        assert self._persisted_bytes(store) == before
        assert store.read_transitions("wf-1") == persisted

    def test_changed_canonical_repository_path_is_rejected(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store, _ = self._seed(tmp_path)
        other_repository = tmp_path / "other-repo"
        other_repository.mkdir()
        persisted = store.read_transitions("wf-1")
        supplied = [
            persisted[0].model_copy(update={"repository_path": str(other_repository.resolve())})
        ]
        before = self._persisted_bytes(store)

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(supplied, state_store=store, workflow_id="wf-1")

        assert exc_info.value.field == "transition_history"
        assert self._persisted_bytes(store) == before

    @pytest.mark.parametrize("sequence_case", ("omitted", "additional", "reordered"))
    def test_length_and_order_must_exactly_match(self, tmp_path: Path, sequence_case: str) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store, _ = self._seed(tmp_path, include_second_transition=True)
        persisted = store.read_transitions("wf-1")
        if sequence_case == "omitted":
            supplied = persisted[:-1]
        elif sequence_case == "additional":
            supplied = [
                *persisted,
                persisted[-1].model_copy(
                    update={
                        "from_state": WorkflowState.PRECONDITIONS_CHECKED.value,
                        "to_state": WorkflowState.BRANCH_CREATED.value,
                        "timestamp": "2026-07-24T10:02:00+00:00",
                    }
                ),
            ]
        else:
            supplied = list(reversed(persisted))
        before = self._persisted_bytes(store)

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(supplied, state_store=store, workflow_id="wf-1")

        assert exc_info.value.field == "transition_history"
        assert self._persisted_bytes(store) == before
        assert store.read_transitions("wf-1") == persisted

    def test_orphan_authorization_record_is_rejected_without_writes(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import (
            _persist_authorization_record,
            _replay_history,
        )

        store = _store(tmp_path)
        _persist_authorization_record(store, _record())
        authorization_path = store.state_directory / "wf-1" / "authorization.json"
        before = authorization_path.read_bytes()

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _replay_history(
                [_fabricated_created_to_authorized_record()],
                state_store=store,
                workflow_id="wf-1",
            )

        assert exc_info.value.field == "transition_history"
        assert store.read_transitions("wf-1") == []
        assert authorization_path.read_bytes() == before

    def test_exact_persisted_history_reaches_exact_final_state_without_writes(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store, _ = self._seed(tmp_path, include_second_transition=True)
        persisted = store.read_transitions("wf-1")
        before = self._persisted_bytes(store)

        machine = _replay_history(persisted, state_store=store, workflow_id="wf-1")

        assert machine.state is WorkflowState.PRECONDITIONS_CHECKED
        assert self._persisted_bytes(store) == before
        assert store.read_transitions("wf-1") == persisted

    def test_symlink_equivalent_canonical_repository_path_is_accepted(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store, repository_path = self._seed(tmp_path)
        alias = tmp_path / "repo-alias"
        alias.symlink_to(repository_path)
        persisted = store.read_transitions("wf-1")
        supplied = [persisted[0].model_copy(update={"repository_path": str(alias)})]
        before = self._persisted_bytes(store)

        machine = _replay_history(supplied, state_store=store, workflow_id="wf-1")

        assert machine.state is WorkflowState.AUTHORIZED
        assert self._persisted_bytes(store) == before

    def test_repeated_rejection_is_deterministic_and_byte_preserving(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _replay_history

        store, _ = self._seed(tmp_path)
        persisted = store.read_transitions("wf-1")
        supplied = [persisted[0].model_copy(update={"timestamp": "2099-01-01T00:00:00+00:00"})]
        before = self._persisted_bytes(store)
        observed: list[tuple[str, str, str]] = []

        for _ in range(2):
            with pytest.raises(AuthorizationBindingDriftError) as exc_info:
                _replay_history(supplied, state_store=store, workflow_id="wf-1")
            observed.append(
                (
                    exc_info.value.field,
                    exc_info.value.expected,
                    exc_info.value.actual,
                )
            )

        assert observed[0] == observed[1]
        assert observed[0][0] == "transition_history"
        assert self._persisted_bytes(store) == before
        assert store.read_transitions("wf-1") == persisted

    def test_direct_replay_apply_rejects_nonmember_record(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _apply_validated_authorization

        store, _ = self._seed(tmp_path)
        persisted = store.read_transitions("wf-1")
        supplied = persisted[0].model_copy(update={"gate_evidence_ref": "fabricated:not-persisted"})
        machine = WorkflowStateMachine()
        before = self._persisted_bytes(store)

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _apply_validated_authorization(machine, record=supplied, state_store=store)

        assert exc_info.value.field == "transition_history"
        assert machine.state is WorkflowState.CREATED
        assert self._persisted_bytes(store) == before

    def test_resume_releases_lock_when_independent_reload_differs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            CurrentAuthorizationBinding,
            resume_workflow,
        )
        from agentos_workflow.orchestrator.lock import RepositoryLock

        store, repository_path = self._seed(tmp_path)
        persisted = store.read_transitions("wf-1")
        before = self._persisted_bytes(store)
        real_read = store.read_transitions
        call_count = 0

        def stale_second_read(workflow_id: str) -> list[StateTransitionRecord]:
            nonlocal call_count
            call_count += 1
            records = real_read(workflow_id)
            if call_count == 2:
                return [records[0].model_copy(update={"timestamp": "2099-01-01T00:00:00+00:00"})]
            return records

        monkeypatch.setattr(store, "read_transitions", stale_second_read)
        lock = RepositoryLock(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path=repository_path,
        )
        current_binding = CurrentAuthorizationBinding.model_validate(
            {
                "repository_path": str(repository_path),
                "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
                "stage_contract_hash": "sha256:deadbeef",
                "baseline_commit_sha": "163bcee1c280bccd6ad4b41fd3840777ef0769f1",
                "engine_version": "0.1.0",
            }
        )

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(), state_store=store, lock=lock, current_binding=current_binding
            )

        assert exc_info.value.field == "transition_history"
        assert not lock.is_held
        assert self._persisted_bytes(store) == before
        assert real_read("wf-1") == persisted


class TestAuthorizationPersistenceSafety:
    """Finding 2 adversarial suite: append-only-by-comparison, confined, concurrency-safe,
    crash-recoverable authorization persistence.
    """

    def test_traversal_workflow_id_rejected(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _persist_authorization_record
        from agentos_workflow.orchestrator.state_store import StateStoreError

        store = _store(tmp_path)
        traversal_record = _record(workflow_id="../../etc/evil")
        with pytest.raises(StateStoreError):
            _persist_authorization_record(store, traversal_record)
        # Confirm nothing was written outside state_directory.
        assert not (tmp_path / ".." / ".." / "etc" / "evil").resolve().exists()

    def test_traversal_workflow_id_rejected_via_authorize(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.state_store import StateStoreError

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        context = _context(workflow_id="../../etc/evil")
        record = _record(workflow_id="../../etc/evil")
        with pytest.raises(StateStoreError):
            authorize(machine, context, record, state_store=store)
        assert machine.state == WorkflowState.CREATED

    def test_second_different_authorization_for_same_workflow_rejected(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            AuthorizationAlreadyPersistedError,
            _load_authorization_record,
            _persist_authorization_record,
        )

        store = _store(tmp_path)
        first = _record(stage_contract_hash="sha256:first")
        _persist_authorization_record(store, first)

        second = _record(stage_contract_hash="sha256:second")
        with pytest.raises(AuthorizationAlreadyPersistedError):
            _persist_authorization_record(store, second)

        # The original bytes are provably untouched.
        assert _load_authorization_record(store, "wf-1") == first

    def test_identical_repeated_authorization_is_a_safe_no_op(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import (
            _load_authorization_record,
            _persist_authorization_record,
        )

        store = _store(tmp_path)
        record = _record()
        _persist_authorization_record(store, record)
        path = tmp_path / "state" / "wf-1" / "authorization.json"
        bytes_after_first_write = path.read_bytes()

        _persist_authorization_record(store, record)  # identical repeat: must not raise
        assert path.read_bytes() == bytes_after_first_write  # untouched, not merely equal
        assert _load_authorization_record(store, "wf-1") == record

    def test_no_bytes_overwritten_on_rejected_conflicting_write(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import (
            AuthorizationAlreadyPersistedError,
            _persist_authorization_record,
        )

        store = _store(tmp_path)
        first = _record(stage_contract_hash="sha256:original")
        _persist_authorization_record(store, first)
        path = tmp_path / "state" / "wf-1" / "authorization.json"
        original_bytes = path.read_bytes()

        with pytest.raises(AuthorizationAlreadyPersistedError):
            _persist_authorization_record(store, _record(stage_contract_hash="sha256:attack"))
        assert path.read_bytes() == original_bytes

    def test_no_orphan_tmp_files_left_after_successful_write(self, tmp_path: Path) -> None:
        from agentos_workflow.orchestrator.engine import _persist_authorization_record

        store = _store(tmp_path)
        _persist_authorization_record(store, _record())
        workflow_dir = tmp_path / "state" / "wf-1"
        leftover_tmp_files = [p for p in workflow_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftover_tmp_files == []

    def test_concurrent_differing_authorization_attempts_serialize_and_one_wins_cleanly(
        self, tmp_path: Path
    ) -> None:
        # Both processes race to persist a DIFFERENT record for the same workflow_id. Whichever
        # one's flock is granted first must win outright (a clean write, or later confirmed as
        # already-identical); the other must observe a well-formed rejection or a benign
        # identical-content no-op — never a torn/interleaved file and never a silent overwrite.
        import multiprocessing as mp

        def _attempt(
            state_dir: str, audit_dir: str, hash_suffix: str, result_queue: object
        ) -> None:
            from pathlib import Path as _Path

            from agentos_workflow.orchestrator.engine import (
                AuthorizationAlreadyPersistedError,
                AuthorizationRecord,
                _persist_authorization_record,
            )
            from agentos_workflow.orchestrator.state_store import StateStore as _StateStore

            local_store = _StateStore(
                state_directory=_Path(state_dir), audit_directory=_Path(audit_dir)
            )
            record = AuthorizationRecord(
                workflow_id="wf-1",
                repository_identity="github.com/org/repo",
                repository_path="/home/user/repo",
                stage_id="AUTO-002",
                stage_contract_path="docs/workflow-automation/stage-prompts/AUTO-002.md",
                stage_contract_hash=f"sha256:{hash_suffix}",
                baseline_branch="main",
                baseline_commit_sha="163bcee1c280bccd6ad4b41fd3840777ef0769f1",
                planned_stage_branch="feature/auto-002-orchestrator-state-machine",
                authorized_at="2026-07-24T10:00:00+00:00",
                engine_version="0.1.0",
            )
            try:
                _persist_authorization_record(local_store, record)
                result_queue.put(("ok", hash_suffix))  # type: ignore[attr-defined]
            except AuthorizationAlreadyPersistedError:
                result_queue.put(("rejected", hash_suffix))  # type: ignore[attr-defined]

        ctx = mp.get_context("fork")
        result_queue = ctx.Queue()
        state_dir = str(tmp_path / "state")
        audit_dir = str(tmp_path / "audit")
        proc_a = ctx.Process(target=_attempt, args=(state_dir, audit_dir, "AAAA", result_queue))
        proc_b = ctx.Process(target=_attempt, args=(state_dir, audit_dir, "BBBB", result_queue))
        proc_a.start()
        proc_b.start()
        proc_a.join(timeout=10)
        proc_b.join(timeout=10)
        assert proc_a.exitcode == 0
        assert proc_b.exitcode == 0

        results = {result_queue.get(timeout=5), result_queue.get(timeout=5)}
        # Exactly one process's write must have won ("ok"), and the other must have been
        # cleanly rejected as a conflicting write ("rejected") — never both "ok" (which would
        # mean one silently clobbered the other).
        outcomes = {outcome for outcome, _ in results}
        assert outcomes == {"ok", "rejected"}

        from agentos_workflow.orchestrator.engine import _load_authorization_record

        store = _store(tmp_path)
        final = _load_authorization_record(store, "wf-1")
        assert final is not None
        winner_hash = next(suffix for outcome, suffix in results if outcome == "ok")
        assert final.stage_contract_hash == f"sha256:{winner_hash}"

    def test_restart_after_partial_transition_failure_can_retry_and_adopt_the_orphan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If the transition-record write fails after the authorization record already
        # succeeded, the "orphaned" authorization.json is safely adopted by a retried,
        # identical authorize() call — self-healing rather than a stuck, ambiguous state.
        store = _store(tmp_path)
        machine = WorkflowStateMachine()

        def _raise(*args: object, **kwargs: object) -> None:
            raise OSError("simulated crash persisting the transition")

        with monkeypatch.context() as patched:
            patched.setattr(store, "record_transition", _raise)
            with pytest.raises(OSError):
                authorize(machine, _context(), _record(), state_store=store)
        assert machine.state == WorkflowState.CREATED

        # "Restart": a fresh machine, the same record, patch reverted (store.record_transition
        # is real again).
        fresh_machine = WorkflowStateMachine()
        authorize(fresh_machine, _context(), _record(), state_store=store)
        assert fresh_machine.state == WorkflowState.AUTHORIZED
        assert store.read_transitions("wf-1") != []

    def test_corrupted_existing_record_detected_before_any_write_attempt(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import (
            CorruptedAuthorizationRecordError,
            _persist_authorization_record,
        )

        store = _store(tmp_path)
        record_path = tmp_path / "state" / "wf-1" / "authorization.json"
        record_path.parent.mkdir(parents=True)
        record_path.write_text("not valid json", encoding="utf-8")

        with pytest.raises(CorruptedAuthorizationRecordError):
            _persist_authorization_record(store, _record())
        # The corrupt bytes are left exactly as they were — never silently repaired/overwritten.
        assert record_path.read_text(encoding="utf-8") == "not valid json"


class TestAUTO002F02AuthorizationCrashAtomicity:
    """Confirmed F02 persistence and crash-boundary regressions."""

    @staticmethod
    def _workflow_snapshot(store: StateStore) -> dict[str, bytes]:
        root = store.state_directory / "wf-1"
        if not root.exists():
            return {}
        return {path.name: path.read_bytes() for path in sorted(root.iterdir()) if path.is_file()}

    def test_reconstructed_duplicate_is_rejected_before_mutation_and_preserves_bytes(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import AuthorizationAlreadyPersistedError

        store = _store(tmp_path)
        authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        before = self._workflow_snapshot(store)
        machine = WorkflowStateMachine()

        with pytest.raises(AuthorizationAlreadyPersistedError):
            authorize(machine, _context(), _record(), state_store=store)

        assert machine.state is WorkflowState.CREATED
        assert len(store.read_transitions("wf-1")) == 1
        assert self._workflow_snapshot(store) == before

    def test_concurrent_identical_lower_level_authorizations_have_exactly_one_winner(
        self, tmp_path: Path
    ) -> None:
        import threading

        from agentos_workflow.orchestrator.engine import AuthorizationAlreadyPersistedError

        store = _store(tmp_path)
        start = threading.Barrier(2)
        outcomes: list[tuple[str, WorkflowState]] = []

        def attempt() -> None:
            machine = WorkflowStateMachine()
            start.wait(timeout=5)
            try:
                authorize(machine, _context(), _record(), state_store=store)
                outcomes.append(("ok", machine.state))
            except AuthorizationAlreadyPersistedError:
                outcomes.append(("rejected", machine.state))

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert sorted(outcomes) == [
            ("ok", WorkflowState.AUTHORIZED),
            ("rejected", WorkflowState.CREATED),
        ]
        assert len(store.read_transitions("wf-1")) == 1
        assert len(list((store.state_directory / "wf-1").glob("authorization.json.*.tmp"))) == 0

    def test_partial_temp_write_failure_is_cleaned(self, tmp_path: Path) -> None:
        import os

        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)
        real_write = os.write

        def partial_then_fail(fd: int, payload: bytes) -> None:
            real_write(fd, payload[:7])
            raise OSError("injected authorization temp write failure")

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(engine_module, "_write_all", partial_then_fail)
            with pytest.raises(OSError):
                engine_module._persist_authorization_record(store, _record())

        workflow_dir = store.state_directory / "wf-1"
        assert not (workflow_dir / "authorization.json").exists()
        assert list(workflow_dir.glob("authorization.json.*.tmp")) == []

    def test_failed_attempts_use_distinct_exclusive_temp_names(self, tmp_path: Path) -> None:
        import os

        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)
        real_open = os.open
        observed_temp_paths: list[str] = []

        def tracking_open(
            path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            if str(path).endswith(".tmp"):
                observed_temp_paths.append(str(path))
            return real_open(path, flags, mode, dir_fd=dir_fd)

        def fail_write(fd: int, payload: bytes) -> None:
            del fd, payload
            raise OSError("injected write failure")

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "open", tracking_open)
            patched.setattr(engine_module, "_write_all", fail_write)
            for _ in range(2):
                with pytest.raises(OSError):
                    engine_module._persist_authorization_record(store, _record())

        assert len(observed_temp_paths) == 2
        assert len(set(observed_temp_paths)) == 2
        assert list((store.state_directory / "wf-1").glob("authorization.json.*.tmp")) == []

    def test_temp_file_fsync_failure_is_cleaned(self, tmp_path: Path) -> None:
        import os
        import stat

        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)
        real_fsync = os.fsync

        def fail_regular_file_fsync(fd: int) -> None:
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("injected authorization file fsync failure")
            real_fsync(fd)

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "fsync", fail_regular_file_fsync)
            with pytest.raises(OSError):
                engine_module._persist_authorization_record(store, _record())

        workflow_dir = store.state_directory / "wf-1"
        assert not (workflow_dir / "authorization.json").exists()
        assert list(workflow_dir.glob("authorization.json.*.tmp")) == []

    def test_failed_publication_cleans_temp_and_preserves_existing_winner(
        self, tmp_path: Path
    ) -> None:
        import os

        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)
        winner = _record(stage_contract_hash="sha256:concurrent-winner")
        record_path = store.state_directory / "wf-1" / "authorization.json"
        real_link = os.link

        def publish_competing_winner(
            source: str,
            destination: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
            follow_symlinks: bool,
        ) -> None:
            winner_fd = os.open(
                destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dst_dir_fd
            )
            try:
                os.write(winner_fd, winner.model_dump_json().encode("utf-8"))
            finally:
                os.close(winner_fd)
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "link", publish_competing_winner)
            with pytest.raises(engine_module.AuthorizationAlreadyPersistedError):
                engine_module._persist_authorization_record(store, _record())

        assert record_path.read_bytes() == winner.model_dump_json().encode("utf-8")
        assert list(record_path.parent.glob("authorization.json.*.tmp")) == []

    def test_link_failure_cleans_temp_and_publishes_nothing(self, tmp_path: Path) -> None:
        import os

        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)

        def fail_link(*args: object, **kwargs: object) -> None:
            raise OSError("injected no-replace publication failure")

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "link", fail_link)
            with pytest.raises(OSError):
                engine_module._persist_authorization_record(store, _record())

        workflow_dir = store.state_directory / "wf-1"
        assert not (workflow_dir / "authorization.json").exists()
        assert list(workflow_dir.glob("authorization.json.*.tmp")) == []

    def test_publication_never_uses_overwrite_capable_replace(self, tmp_path: Path) -> None:
        import os

        from agentos_workflow.orchestrator.engine import _persist_authorization_record

        store = _store(tmp_path)

        def forbidden_replace(*args: object, **kwargs: object) -> None:
            raise AssertionError("authorization publication must not call os.replace")

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "replace", forbidden_replace)
            _persist_authorization_record(store, _record())

        assert (store.state_directory / "wf-1" / "authorization.json").is_file()

    def test_stale_crash_temp_is_removed_under_lock_before_publication(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import _persist_authorization_record

        store = _store(tmp_path)
        workflow_dir = store.state_directory / "wf-1"
        workflow_dir.mkdir(parents=True)
        stale = workflow_dir / "authorization.json.crashed.tmp"
        stale.write_bytes(b"partial")

        _persist_authorization_record(store, _record())

        assert not stale.exists()
        assert list(workflow_dir.glob("authorization.json.*.tmp")) == []

    def test_authorization_publication_and_transition_append_fsync_files_and_directories(
        self, tmp_path: Path
    ) -> None:
        import os
        import stat

        store = _store(tmp_path)
        real_fsync = os.fsync
        fsync_targets: list[str] = []

        def tracking_fsync(fd: int) -> None:
            mode = os.fstat(fd).st_mode
            fsync_targets.append("directory" if stat.S_ISDIR(mode) else "file")
            real_fsync(fd)

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "fsync", tracking_fsync)
            authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)

        assert fsync_targets.count("file") >= 2  # authorization temp and transition JSONL
        assert fsync_targets.count("directory") >= 2

    def test_directory_fsync_failure_after_publication_is_recoverable(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        real_fsync = os.fsync
        publication_seen = False

        def fail_once_after_publication(fd: int) -> None:
            nonlocal publication_seen
            descriptor_path = Path(f"/proc/self/fd/{fd}")
            resolved = descriptor_path.resolve()
            if (
                resolved.is_dir()
                and (resolved / "authorization.json").exists()
                and not publication_seen
            ):
                publication_seen = True
                raise OSError("injected directory fsync failure after publication")
            real_fsync(fd)

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(os, "fsync", fail_once_after_publication)
            with pytest.raises(OSError):
                authorize(machine, _context(), _record(), state_store=store)

        assert machine.state is WorkflowState.CREATED
        assert store.read_transitions("wf-1") == []
        assert list((store.state_directory / "wf-1").glob("authorization.json.*.tmp")) == []

        recovered = WorkflowStateMachine()
        authorize(recovered, _context(), _record(), state_store=store)
        assert recovered.state is WorkflowState.AUTHORIZED
        assert len(store.read_transitions("wf-1")) == 1

    def test_transition_append_failure_leaves_detectable_recoverable_orphan(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import AuthorizationAlreadyPersistedError

        store = _store(tmp_path)
        machine = WorkflowStateMachine()

        def fail_append(*args: object, **kwargs: object) -> None:
            raise OSError("injected transition append failure")

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(store, "record_transition", fail_append)
            with pytest.raises(OSError):
                authorize(machine, _context(), _record(), state_store=store)

        authorization_path = store.state_directory / "wf-1" / "authorization.json"
        orphan_bytes = authorization_path.read_bytes()
        assert machine.state is WorkflowState.CREATED
        assert store.read_transitions("wf-1") == []

        recovered = WorkflowStateMachine()
        authorize(recovered, _context(), _record(), state_store=store)
        assert recovered.state is WorkflowState.AUTHORIZED
        assert authorization_path.read_bytes() == orphan_bytes
        assert len(store.read_transitions("wf-1")) == 1

        completed_bytes = self._workflow_snapshot(store)
        with pytest.raises(AuthorizationAlreadyPersistedError):
            authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        assert self._workflow_snapshot(store) == completed_bytes

    def test_partial_transition_append_is_detected_and_never_repaired_destructively(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.state_store import StateStoreCorruptionError

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        transition_path = store.state_directory / "wf-1" / "transitions.jsonl"

        def torn_append(record: StateTransitionRecord) -> None:
            transition_path.write_bytes(record.model_dump_json().encode("utf-8")[:31])
            raise OSError("injected torn transition append")

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(store, "record_transition", torn_append)
            with pytest.raises(OSError):
                authorize(machine, _context(), _record(), state_store=store)

        before = self._workflow_snapshot(store)
        assert machine.state is WorkflowState.CREATED
        with pytest.raises(StateStoreCorruptionError):
            authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        assert self._workflow_snapshot(store) == before

    def test_transition_without_authorization_is_rejected_without_filesystem_mutation(
        self, tmp_path: Path
    ) -> None:
        from agentos_workflow.orchestrator.engine import AuthorizationPersistenceStateError

        store = _store(tmp_path)
        store.record_transition(_fabricated_created_to_authorized_record())
        before = self._workflow_snapshot(store)
        machine = WorkflowStateMachine()

        with pytest.raises(AuthorizationPersistenceStateError):
            authorize(machine, _context(), _record(), state_store=store)

        assert machine.state is WorkflowState.CREATED
        assert self._workflow_snapshot(store) == before
        assert not (store.state_directory / "wf-1" / "authorization.json").exists()

    def test_crash_after_transition_before_memory_requires_resume_not_reauthorization(
        self, tmp_path: Path
    ) -> None:
        from unittest.mock import Mock

        import agentos_workflow.orchestrator.engine as engine_module

        store = _store(tmp_path)
        machine = WorkflowStateMachine()

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(
                engine_module,
                "_commit_validated_authorized_machine_state",
                Mock(side_effect=OSError("injected crash after durable transition")),
            )
            with pytest.raises(OSError):
                authorize(machine, _context(), _record(), state_store=store)

        before = self._workflow_snapshot(store)
        assert machine.state is WorkflowState.CREATED
        assert len(store.read_transitions("wf-1")) == 1

        with pytest.raises(engine_module.AuthorizationAlreadyPersistedError):
            authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)

        assert self._workflow_snapshot(store) == before

    def test_transition_directory_fsync_failure_leaves_completed_detectable_pair(
        self, tmp_path: Path
    ) -> None:
        import stat as stat_module

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        real_fsync = os.fsync
        failed = False

        # AUTO002-IR-02 moved the post-append directory fsync from a path-based helper
        # (`_fsync_directory`, which reopened the directory by path — the check-then-open race the
        # confinement fix removes) onto the already-open workflow-directory descriptor. The
        # invariant under test is unchanged: a failure of that directory fsync must propagate and
        # leave a detectable pair. The injection is therefore re-targeted at the descriptor-level
        # fsync of the workflow directory, identified by its own contents rather than by the name
        # of any internal helper.
        def fail_after_transition_append(fd: int) -> None:
            nonlocal failed
            if (
                not failed
                and stat_module.S_ISDIR(os.fstat(fd).st_mode)
                and "transitions.jsonl" in os.listdir(fd)
            ):
                failed = True
                raise OSError("injected transition directory fsync failure")
            real_fsync(fd)

        with pytest.MonkeyPatch.context() as patched:
            # `state_store` does a plain `import os`, so patching the module attribute here is
            # exactly what its `os.fsync(directory_fd)` call resolves to.
            patched.setattr(os, "fsync", fail_after_transition_append)
            with pytest.raises(OSError):
                authorize(machine, _context(), _record(), state_store=store)

        before = self._workflow_snapshot(store)
        assert machine.state is WorkflowState.CREATED
        assert len(store.read_transitions("wf-1")) == 1

        from agentos_workflow.orchestrator.engine import AuthorizationAlreadyPersistedError

        with pytest.raises(AuthorizationAlreadyPersistedError):
            authorize(WorkflowStateMachine(), _context(), _record(), state_store=store)
        assert self._workflow_snapshot(store) == before

    @pytest.mark.parametrize(
        "workflow_id",
        (
            "../evil",
            "/tmp/evil",
            "nested/evil",
            r"nested\evil",
            "%2e%2e%2fescape",
            "..",
            " leading-space",
            "évil",
        ),
    )
    def test_malformed_workflow_id_creates_no_directory(
        self, tmp_path: Path, workflow_id: str
    ) -> None:
        from agentos_workflow.orchestrator.state_store import StateStoreError

        store = _store(tmp_path)
        machine = WorkflowStateMachine()
        context = _context(workflow_id=workflow_id)
        record = _record(workflow_id=workflow_id)

        with pytest.raises(StateStoreError):
            authorize(machine, context, record, state_store=store)

        assert machine.state is WorkflowState.CREATED
        assert not store.state_directory.exists()


def _ir03_config_dict(tmp_path: Path) -> dict[str, object]:
    return {
        "repository_path": str(tmp_path),
        "repository_identity": "github.com/org/repo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/contracts",
        "stage_branch_naming": "governance/{stage_id}-{slug}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests"],
        "merge_method": "squash",
        "claude_cli_executable": "/usr/local/bin/claude",
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": "/usr/local/bin/codex",
        "codex_cli_timeout_seconds": 1800,
        "allowed_environment_variables": ["PATH", "HOME", "LANG"],
        "allowed_changed_paths": ["docs/**"],
        "forbidden_changed_paths": ["src/**"],
        "repair_attempt_limit": 3,
        "state_directory": str(tmp_path / "state"),
        "audit_directory": str(tmp_path / "audit"),
    }


class TestAUTO002IR03ChangedPathAuthorizationCanonicalMatching:
    """AUTO002-IR-03: changed-path authorization must operate on one deterministic
    repository-relative POSIX representation on both sides, so that semantically equivalent paths
    and patterns can never produce different authorization outcomes — in particular, a forbidden
    rule must never be silently defeated by a spelling difference and lose to a broader allowed
    rule.
    """

    @staticmethod
    def _config(tmp_path: Path, *, allowed: list[str], forbidden: list[str]) -> WorkflowConfig:
        raw = dict(_ir03_config_dict(tmp_path))
        raw["allowed_changed_paths"] = allowed
        raw["forbidden_changed_paths"] = forbidden
        return WorkflowConfig.model_validate(raw)

    @staticmethod
    def _classify(config: WorkflowConfig, *paths: str) -> _WorktreeClassification:
        observation = Mock(
            worktree_changes=tuple(
                WorktreeChange(index_status="?", worktree_status="?", path=path) for path in paths
            )
        )
        return _classify_worktree(observation, config)

    def test_forbidden_canonical_pattern_overrides_broader_allowed_pattern(
        self, tmp_path: Path
    ) -> None:
        config = self._config(tmp_path, allowed=["docs/**"], forbidden=["docs/secret/**"])
        classification = self._classify(config, "docs/secret/keys.md", "docs/public/notes.md")
        assert classification.forbidden_paths == ("docs/secret/keys.md",)
        assert classification.allowed_paths == ("docs/public/notes.md",)

    @pytest.mark.parametrize(
        "observed",
        [
            "docs/secret/keys.md",
            "docs/./secret/keys.md",
            "docs//secret/keys.md",
            "./docs/secret/keys.md",
            "docs/public/../secret/keys.md",
        ],
    )
    def test_every_spelling_of_an_observed_path_hits_the_same_forbidden_rule(
        self, tmp_path: Path, observed: str
    ) -> None:
        # The precise failure the review reproduced from the other direction: a representation
        # mismatch must never let a forbidden path fall through into `allowed`/`unexpected`.
        config = self._config(tmp_path, allowed=["docs/**"], forbidden=["docs/secret/**"])
        classification = self._classify(config, observed)
        assert classification.forbidden_paths == (observed,)
        assert classification.allowed_paths == ()
        assert classification.unexpected_paths == ()

    def test_no_configuration_can_forbid_a_path_while_actually_allowing_it(
        self, tmp_path: Path
    ) -> None:
        # A configuration expressing "allow docs, except docs/secret" cannot be written in any
        # accepted spelling that fails to forbid docs/secret: the noncanonical spellings that
        # used to be inert are now rejected at load time rather than silently allowed.
        for inert_spelling in ("docs/./secret/**", "docs//secret/**", "docs\\secret\\**"):
            with pytest.raises(ValidationError):
                self._config(tmp_path, allowed=["docs/**"], forbidden=[inert_spelling])
        config = self._config(tmp_path, allowed=["docs/**"], forbidden=["docs/secret/**"])
        assert self._classify(config, "docs/secret/keys.md").forbidden_paths == (
            "docs/secret/keys.md",
        )

    def test_glob_tokens_still_behave_after_canonical_matching(self, tmp_path: Path) -> None:
        config = self._config(
            tmp_path, allowed=["docs/*.md", "docs/[ab]/**"], forbidden=["docs/x?.md"]
        )
        classification = self._classify(
            config, "docs/notes.md", "docs/a/deep/file.md", "docs/x1.md", "docs/b/other.md"
        )
        assert classification.forbidden_paths == ("docs/x1.md",)
        assert set(classification.allowed_paths) == {
            "docs/notes.md",
            "docs/a/deep/file.md",
            "docs/b/other.md",
        }
        assert classification.unexpected_paths == ()

    def test_reported_paths_are_the_observed_spellings_not_the_canonical_ones(
        self, tmp_path: Path
    ) -> None:
        # Canonicalisation governs the authorization *decision* only; drift reporting still shows
        # operators exactly what Git reported.
        config = self._config(tmp_path, allowed=["docs/**"], forbidden=["docs/secret/**"])
        assert self._classify(config, "docs/./secret/keys.md").forbidden_paths == (
            "docs/./secret/keys.md",
        )
