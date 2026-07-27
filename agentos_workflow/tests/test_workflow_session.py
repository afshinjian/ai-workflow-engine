"""Tests for `WorkflowSession` (`agentos_workflow.orchestrator.engine`) — the single,
orchestrator-owned runtime facade (`ARCHITECTURE.md` §2, §5).

These tests exercise the facade itself (construction discipline, delegation, lock lifecycle) and
the structural "single authority" invariant: external callers must never be handed a mutable
`WorkflowStateMachine`, `RepositoryLock`, or `StateStore` through this class or through the
package's public surface. They do not re-test the underlying primitives' own behavior (already
covered by `test_engine.py`, `test_engine_authorization.py`, `test_engine_resume.py`,
`test_engine_retry.py`, `test_lock.py`, `test_state_store.py`) beyond what is needed to confirm
`WorkflowSession` delegates to them faithfully.
"""

import json
import subprocess
from pathlib import Path

import pytest

import agentos_workflow.orchestrator as orchestrator_package
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.observation import ResumeObservation
from agentos_workflow.orchestrator.engine import (
    AttemptLimitExceededError,
    AuthorizationBindingDriftError,
    AuthorizationRecord,
    CurrentAuthorizationBinding,
    EvidenceScopeMismatchError,
    ImplementationDiffEvidence,
    InitialExecutionFailureKind,
    InvalidActorForTransitionError,
    InvalidTransitionError,
    ReconciliationEvidence,
    RetryOutcome,
    WorkflowAlreadyTerminalError,
    WorkflowIdReuseError,
    WorkflowSession,
    WorkflowSessionError,
    WorkflowState,
)
from agentos_workflow.orchestrator.lock import LockContentionError, RepositoryLock
from agentos_workflow.orchestrator.state_store import StateStore, StateTransitionRecord

_ENGINE_VERSION = "0.1.0"
_STAGE_CONTRACT_PATH = "docs/workflow-automation/stage-prompts/AUTO-002.md"
_STAGE_CONTRACT_HASH = "sha256:deadbeef"
_BASELINE_SHA = "163bcee1c280bccd6ad4b41fd3840777ef0769f1"


def _config(tmp_path: Path, **overrides: object) -> WorkflowConfig:
    repository_path = tmp_path / "repo"
    repository_path.mkdir(exist_ok=True)
    (repository_path / "docs" / "workflow-automation").mkdir(parents=True, exist_ok=True)
    defaults: dict[str, object] = {
        "repository_path": repository_path,
        "repository_identity": "github.com/org/repo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/workflow-automation",
        "stage_branch_naming": "governance/{stage_id}-{slug}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests"],
        "merge_method": "squash",
        "claude_cli_executable": Path("/usr/local/bin/claude"),
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": Path("/usr/local/bin/codex"),
        "codex_cli_timeout_seconds": 1800,
        "allowed_environment_variables": ["PATH", "HOME"],
        "allowed_changed_paths": ["docs/**"],
        "forbidden_changed_paths": ["src/**"],
        "repair_attempt_limit": 3,
        "state_directory": tmp_path / "state",
        "audit_directory": tmp_path / "audit",
    }
    defaults.update(overrides)
    return WorkflowConfig.model_validate(defaults)


def _current_binding(config: WorkflowConfig, **overrides: object) -> CurrentAuthorizationBinding:
    defaults: dict[str, object] = {
        "repository_path": str(config.repository_path),
        "stage_contract_path": _STAGE_CONTRACT_PATH,
        "stage_contract_hash": _STAGE_CONTRACT_HASH,
        "baseline_commit_sha": _BASELINE_SHA,
        "engine_version": _ENGINE_VERSION,
    }
    defaults.update(overrides)
    return CurrentAuthorizationBinding.model_validate(defaults)


class _StaticObserver:
    """Raw-observation test double; it never returns an authorization verdict."""

    def __init__(self, config: WorkflowConfig, **overrides: object) -> None:
        defaults: dict[str, object] = {
            "canonical_repository_path": str(config.repository_path.resolve()),
            "repository_exists": True,
            "is_git_repository": True,
            "observed_repository_identity": config.repository_identity,
            "current_branch": "feature/auto-002-orchestrator-state-machine",
            "head_sha": _BASELINE_SHA,
            "baseline_sha": _BASELINE_SHA,
            "planned_branch_sha": _BASELINE_SHA,
            "baseline_is_ancestor_of_planned": True,
            "worktree_changes": (),
            "canonical_contract_path": str(
                (config.repository_path / _STAGE_CONTRACT_PATH).resolve()
            ),
            "contract_exists": True,
            "contract_hash": _STAGE_CONTRACT_HASH,
            "engine_version": _ENGINE_VERSION,
        }
        defaults.update(overrides)
        self.observation = ResumeObservation(**defaults)  # type: ignore[arg-type]

    def observe(self, **_: str) -> ResumeObservation:
        return self.observation


def _start(
    tmp_path: Path,
    *,
    workflow_id: str = "wf-1",
    config: WorkflowConfig | None = None,
    baseline_commit_sha: str = _BASELINE_SHA,
) -> WorkflowSession:
    cfg = config if config is not None else _config(tmp_path)
    return WorkflowSession.start(
        cfg,
        workflow_id=workflow_id,
        stage_id="AUTO-002",
        stage_contract_path=_STAGE_CONTRACT_PATH,
        stage_contract_hash=_STAGE_CONTRACT_HASH,
        planned_stage_branch="feature/auto-002-orchestrator-state-machine",
        baseline_commit_sha=baseline_commit_sha,
        authorized_at="2026-07-24T10:00:00+00:00",
        engine_version=_ENGINE_VERSION,
        authorized_by="human-owner",
    )


class TestBareConstructionForbidden:
    def test_direct_construction_without_token_rejected(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        with pytest.raises(WorkflowSessionError):
            WorkflowSession(
                resumed=session._resumed, repository_path=str(tmp_path), repair_attempt_limit=3
            )
        session.transition_to(WorkflowState.CANCELLED, actor="human")


class TestNeverExposesMutableRuntimeObjects:
    """The structural core of the PRIMARY ARCHITECTURE GOAL: a caller holding only a
    `WorkflowSession` can never obtain the machine, lock, or state store it wraps."""

    def test_no_public_attribute_or_property_returns_a_mutable_runtime_object(
        self, tmp_path: Path
    ) -> None:
        session = _start(tmp_path)
        public_names = [name for name in dir(session) if not name.startswith("_")]
        for name in public_names:
            value = getattr(session, name)
            assert not isinstance(value, WorkflowConfig | RepositoryLock | StateStore)
            assert type(value).__name__ != "WorkflowStateMachine"
            assert type(value).__name__ != "ResumedWorkflow"
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_transitions_property_is_an_immutable_tuple(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        transitions = session.transitions
        assert isinstance(transitions, tuple)
        with pytest.raises(AttributeError):
            transitions.append(transitions[0])  # type: ignore[attr-defined]
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_package_public_surface_excludes_mutable_runtime_types(self) -> None:
        """`agentos_workflow.orchestrator.__all__` — the package's declared public surface — must
        never name `WorkflowStateMachine`, `RepositoryLock`, or `StateStore`: only `WorkflowSession`
        is the intended external entry point (`ARCHITECTURE.md` §2, §5)."""
        forbidden = {"WorkflowStateMachine", "RepositoryLock", "StateStore", "ResumedWorkflow"}
        assert forbidden.isdisjoint(set(orchestrator_package.__all__))
        assert "WorkflowSession" in orchestrator_package.__all__

    def test_package_namespace_has_no_attribute_for_mutable_runtime_types(self) -> None:
        """Stronger than the `__all__` check above: `__all__` only changes what
        `from agentos_workflow.orchestrator import *` binds — it does nothing to stop
        `from agentos_workflow.orchestrator import WorkflowStateMachine` naming the package
        directly, since Python does not enforce `__all__` as an access-control list. What
        actually prevents that specific import from succeeding is that `orchestrator/__init__.py`
        never binds those names in its own namespace at all (it imports a fixed, explicit list
        from `.engine`/`.lock`/`.state_store` that excludes them) — checked here directly via
        `getattr`, independent of `__all__`. The submodule itself (`agentos_workflow.orchestrator.
        engine.WorkflowStateMachine`) remains reachable by design (DD-12's documented whitebox
        exception) — this test asserts only that the *package* namespace itself carries nothing,
        not that the underlying module is sealed.
        """
        for name in ("WorkflowStateMachine", "RepositoryLock", "StateStore", "ResumedWorkflow"):
            assert not hasattr(
                orchestrator_package, name
            ), f"agentos_workflow.orchestrator.{name} must not exist as a package attribute"


class TestStartLifecycle:
    def test_start_acquires_lock_and_persists_created_to_authorized(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        assert session.state is WorkflowState.AUTHORIZED
        assert session.lock_is_held is True
        assert session.workflow_id == "wf-1"
        assert session.stage_id == "AUTO-002"
        assert session.repository_identity == "github.com/org/repo"
        assert len(session.transitions) == 1
        assert session.transitions[0].from_state == "CREATED"
        assert session.transitions[0].to_state == "AUTHORIZED"
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_second_start_for_same_repository_contends_on_the_lock(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, workflow_id="wf-1", config=config)
        with pytest.raises(LockContentionError):
            _start(tmp_path, workflow_id="wf-2", config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_losing_concurrent_start_never_persists_an_authorization_record(
        self, tmp_path: Path
    ) -> None:
        """ARCHITECTURE.md §5: a second `authorize` against a locked repository is refused
        "before any target-repository mutation occurs" — the lock must be acquired before
        `authorize()` ever runs, not after, so the loser of a concurrent `start()` race never
        durably persists an `AuthorizationRecord` for a workflow that will never actually run.
        """
        config = _config(tmp_path)
        first = _start(tmp_path, workflow_id="wf-1", config=config)
        with pytest.raises(LockContentionError):
            _start(tmp_path, workflow_id="wf-2", config=config)
        store = StateStore.for_config(config)
        assert store.read_transitions("wf-2") == []
        authorization_path = config.state_directory / "wf-2" / "authorization.json"
        assert not authorization_path.exists()
        first.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_second_start_after_release_succeeds(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, workflow_id="wf-1", config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")
        assert first.lock_is_held is False
        second = WorkflowSession.start(
            config,
            workflow_id="wf-2",
            stage_id="AUTO-002",
            stage_contract_path=_STAGE_CONTRACT_PATH,
            stage_contract_hash=_STAGE_CONTRACT_HASH,
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            baseline_commit_sha=_BASELINE_SHA,
            authorized_at="2026-07-24T11:00:00+00:00",
            engine_version=_ENGINE_VERSION,
        )
        assert second.lock_is_held is True
        second.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_symlink_aliased_repository_path_still_contends(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, workflow_id="wf-1", config=config)
        alias = tmp_path / "alias"
        alias.symlink_to(config.repository_path)
        aliased_config = _config(tmp_path, repository_path=alias)
        with pytest.raises(LockContentionError):
            _start(tmp_path, workflow_id="wf-2", config=aliased_config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")


class TestWorkflowIdReuseRejected:
    """Release-gate finding: `WorkflowSession.start()` must fail closed
    (`WorkflowIdReuseError`) whenever durable transition history already exists for the requested
    `workflow_id` — whatever state that history reached — never silently appending a second
    `CREATED -> AUTHORIZED` record. The one narrow exception is a genuinely incomplete first
    authorization transaction (zero persisted transitions), which remains recoverable.
    """

    def test_repeated_start_after_successful_authorization_rejected(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        assert first.state is WorkflowState.AUTHORIZED
        first._resumed.lock.release()  # simulate the original process exiting

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        store = StateStore.for_config(config)
        assert len(store.read_transitions("wf-1")) == 1
        first.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_repeated_start_after_cancellation_rejected(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")
        assert first.lock_is_held is False

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

    def test_repeated_start_after_failure_rejected(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.FAILED, actor="orchestrator")
        assert first.lock_is_held is False

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

    def test_repeated_start_after_terminal_completion_rejected(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        for state in (
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
        ):
            first.transition_to(state, actor="orchestrator")
        assert first.state is WorkflowState.DONE
        assert first.lock_is_held is False

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

    def test_incomplete_first_authorization_transaction_recovers(self, tmp_path: Path) -> None:
        """A crash between persisting the `AuthorizationRecord` and appending its
        `StateTransitionRecord` leaves zero persisted transitions — the one case this check does
        not cover; a retried `start()` with identical authorization content still succeeds via
        `authorize()`'s own idempotent-identical-record handling.
        """
        from agentos_workflow.orchestrator.engine import _persist_authorization_record

        config = _config(tmp_path)
        state_store = StateStore.for_config(config)
        record = AuthorizationRecord(
            workflow_id="wf-1",
            repository_identity=config.repository_identity,
            repository_path=str(config.repository_path),
            stage_id="AUTO-002",
            stage_contract_path=_STAGE_CONTRACT_PATH,
            stage_contract_hash=_STAGE_CONTRACT_HASH,
            baseline_branch=config.baseline_branch,
            baseline_commit_sha=_BASELINE_SHA,
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            authorized_at="2026-07-24T10:00:00+00:00",
            authorized_by="human-owner",
            engine_version=_ENGINE_VERSION,
        )
        _persist_authorization_record(state_store, record)
        assert state_store.read_transitions("wf-1") == []

        session = _start(tmp_path, config=config)
        assert session.state is WorkflowState.AUTHORIZED
        assert len(session.transitions) == 1
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_rejected_reuse_appends_no_duplicate_authorization_transition(
        self, tmp_path: Path
    ) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        store = StateStore.for_config(config)
        transitions = store.read_transitions("wf-1")
        assert len(transitions) == 2
        authorized_transitions = [t for t in transitions if t.to_state == "AUTHORIZED"]
        assert len(authorized_transitions) == 1

    def test_rejected_reuse_does_not_modify_existing_bytes(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")

        transitions_path = config.state_directory / "wf-1" / "transitions.jsonl"
        authorization_path = config.state_directory / "wf-1" / "authorization.json"
        before_transitions = transitions_path.read_bytes()
        before_authorization = authorization_path.read_bytes()

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        assert transitions_path.read_bytes() == before_transitions
        assert authorization_path.read_bytes() == before_authorization

    def _lock_path(self, config: WorkflowConfig) -> Path:
        return config.repository_path / ".agentos" / "workflow.lock"

    def test_repeated_start_after_successful_authorization_preserves_all_bytes_including_lock(
        self, tmp_path: Path
    ) -> None:
        """Release-gate finding: reuse rejection must occur *before* `lock.acquire()` is ever
        called — proven here by leaving the original session's lock actively held (never
        released) and confirming a rejected reuse attempt still leaves every existing artifact,
        including `.agentos/workflow.lock`'s own bytes, byte-for-byte identical. If the fix
        instead acquired the lock before checking history, this would either deadlock/contend on
        the still-held lock (wrong error) or rewrite the lock file's metadata before rejecting.
        """
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        assert first.state is WorkflowState.AUTHORIZED
        assert first.lock_is_held is True  # deliberately never released

        transitions_path = config.state_directory / "wf-1" / "transitions.jsonl"
        authorization_path = config.state_directory / "wf-1" / "authorization.json"
        lock_path = self._lock_path(config)
        before_transitions = transitions_path.read_bytes()
        before_authorization = authorization_path.read_bytes()
        before_lock = lock_path.read_bytes()

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        assert transitions_path.read_bytes() == before_transitions
        assert authorization_path.read_bytes() == before_authorization
        assert lock_path.read_bytes() == before_lock

        first.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_repeated_start_after_failure_preserves_all_bytes_including_lock(
        self, tmp_path: Path
    ) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.FAILED, actor="orchestrator")
        assert first.lock_is_held is False

        transitions_path = config.state_directory / "wf-1" / "transitions.jsonl"
        authorization_path = config.state_directory / "wf-1" / "authorization.json"
        lock_path = self._lock_path(config)
        before_transitions = transitions_path.read_bytes()
        before_authorization = authorization_path.read_bytes()
        before_lock = lock_path.read_bytes()

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        assert transitions_path.read_bytes() == before_transitions
        assert authorization_path.read_bytes() == before_authorization
        assert lock_path.read_bytes() == before_lock

    def test_repeated_start_after_cancellation_preserves_all_bytes_including_lock(
        self, tmp_path: Path
    ) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")
        assert first.lock_is_held is False

        transitions_path = config.state_directory / "wf-1" / "transitions.jsonl"
        authorization_path = config.state_directory / "wf-1" / "authorization.json"
        lock_path = self._lock_path(config)
        before_transitions = transitions_path.read_bytes()
        before_authorization = authorization_path.read_bytes()
        before_lock = lock_path.read_bytes()

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        assert transitions_path.read_bytes() == before_transitions
        assert authorization_path.read_bytes() == before_authorization
        assert lock_path.read_bytes() == before_lock

    def test_repeated_start_after_terminal_completion_preserves_all_bytes_including_lock(
        self, tmp_path: Path
    ) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        for state in (
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
        ):
            first.transition_to(state, actor="orchestrator")
        assert first.state is WorkflowState.DONE
        assert first.lock_is_held is False

        transitions_path = config.state_directory / "wf-1" / "transitions.jsonl"
        authorization_path = config.state_directory / "wf-1" / "authorization.json"
        lock_path = self._lock_path(config)
        before_transitions = transitions_path.read_bytes()
        before_authorization = authorization_path.read_bytes()
        before_lock = lock_path.read_bytes()

        with pytest.raises(WorkflowIdReuseError):
            _start(tmp_path, config=config)

        assert transitions_path.read_bytes() == before_transitions
        assert authorization_path.read_bytes() == before_authorization
        assert lock_path.read_bytes() == before_lock

    def test_straightforward_reuse_never_calls_lock_acquire(self, tmp_path: Path) -> None:
        """Direct proof — independent of byte-comparison — that the obvious, common reuse case
        (history already exists) never even calls `RepositoryLock.acquire()`, not merely that
        its observable side effects happen to net out to no change.
        """
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.CANCELLED, actor="human")

        original_acquire = RepositoryLock.acquire
        calls = {"n": 0}

        def spy_acquire(self: RepositoryLock) -> None:
            calls["n"] += 1
            original_acquire(self)

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(RepositoryLock, "acquire", spy_acquire)
            with pytest.raises(WorkflowIdReuseError):
                _start(tmp_path, config=config)

        assert calls["n"] == 0

    def test_race_between_precheck_and_lock_acquisition_is_detected(self, tmp_path: Path) -> None:
        """Simulates a concurrent `start()` for the same `workflow_id` whose own authorization
        completes in the window between this call's read-only precheck (before lock acquisition)
        and its lock acquisition: the precheck's read returns empty (nothing persisted yet), but
        the second, lock-held recheck must independently discover the now-persisted history and
        reject — proving the race window the two-check design exists to close is actually closed,
        not just documented.
        """
        config = _config(tmp_path)
        concurrent_record = StateTransitionRecord(
            workflow_id="wf-1",
            target_repository=config.repository_identity,
            repository_path=str(config.repository_path.resolve()),
            stage_id="AUTO-002",
            from_state="CREATED",
            to_state="AUTHORIZED",
            timestamp="2026-07-24T09:00:00+00:00",
            actor="human",
            gate_evidence_ref=None,
        )
        call_count = {"n": 0}
        original_read_transitions = StateStore.read_transitions

        def racy_read_transitions(
            self_store: StateStore, workflow_id: str
        ) -> list[StateTransitionRecord]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return original_read_transitions(self_store, workflow_id)
            return [concurrent_record]

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(StateStore, "read_transitions", racy_read_transitions)
            with pytest.raises(WorkflowIdReuseError):
                _start(tmp_path, config=config)
        assert call_count["n"] == 2

        # The real store never actually gained a "wf-1" record (the race was faked, not real),
        # and — crucially — the race-rejection path must still have released the lock: a fresh
        # start() for a different workflow_id against the same repository must not contend.
        store = StateStore.for_config(config)
        assert store.read_transitions("wf-1") == []
        fresh = _start(tmp_path, workflow_id="wf-2", config=config)
        assert fresh.state is WorkflowState.AUTHORIZED
        fresh.transition_to(WorkflowState.CANCELLED, actor="human")


class TestContextManagerReleasesLockOnException:
    def test_exception_inside_with_block_still_releases_lock(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        with pytest.raises(RuntimeError):
            with _start(tmp_path, config=config) as session:
                assert session.lock_is_held is True
                raise RuntimeError("simulated crash mid-session")
        # A fresh start for the same repository must now succeed — the lock was released even
        # though the `with` block exited via an exception, never a normal transition_to() call.
        second = WorkflowSession.start(
            config,
            workflow_id="wf-2",
            stage_id="AUTO-002",
            stage_contract_path=_STAGE_CONTRACT_PATH,
            stage_contract_hash=_STAGE_CONTRACT_HASH,
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            baseline_commit_sha=_BASELINE_SHA,
            authorized_at="2026-07-24T11:00:00+00:00",
            engine_version=_ENGINE_VERSION,
        )
        second.transition_to(WorkflowState.CANCELLED, actor="human")


class TestTransitionToDelegation:
    def test_illegal_transition_rejected_without_mutating_state(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        with pytest.raises(InvalidTransitionError):
            session.transition_to(WorkflowState.COMMITTED, actor="orchestrator")
        assert session.state is WorkflowState.AUTHORIZED
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_human_actor_rejected_on_ordinary_machine_edge(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        with pytest.raises(InvalidActorForTransitionError):
            session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="human")
        assert session.state is WorkflowState.AUTHORIZED  # never mutated
        assert len(session.transitions) == 1  # never persisted
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_transition_persists_repository_identity_and_canonical_path(
        self, tmp_path: Path
    ) -> None:
        session = _start(tmp_path)
        session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        record = session.transitions[-1]
        assert record.target_repository == "github.com/org/repo"
        assert record.repository_path == str(Path(session._repository_path).resolve())
        session.transition_to(WorkflowState.CANCELLED, actor="human")

    def test_reaching_terminal_state_releases_lock_automatically(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        session.transition_to(WorkflowState.CANCELLED, actor="human")
        assert session.is_terminal is True
        assert session.lock_is_held is False


class TestResumeLifecycle:
    def test_resume_reconstructs_identical_state_from_a_fresh_session(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        first.transition_to(WorkflowState.BRANCH_CREATED, actor="orchestrator")
        assert first.lock_is_held is True
        first.release_lock_if_terminal()  # no-op: not terminal yet
        first._resumed.lock.release()  # simulate the original process exiting

        resumed = WorkflowSession.resume(
            config,
            workflow_id="wf-1",
            stage_id="AUTO-002",
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            current_binding=_current_binding(config),
            _observer=_StaticObserver(config),
        )
        assert resumed.state is WorkflowState.BRANCH_CREATED
        assert resumed.lock_is_held is True
        assert len(resumed.transitions) == 3
        resumed.transition_to(WorkflowState.IMPLEMENTING, actor="orchestrator")
        resumed._resumed.lock.release()

    def test_resume_with_drifted_binding_fails_workflow_and_releases_lock(
        self, tmp_path: Path
    ) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        first._resumed.lock.release()

        with pytest.raises(AuthorizationBindingDriftError):
            WorkflowSession.resume(
                config,
                workflow_id="wf-1",
                stage_id="AUTO-002",
                planned_stage_branch="feature/auto-002-orchestrator-state-machine",
                current_binding=_current_binding(config, baseline_commit_sha="f" * 40),
                _observer=_StaticObserver(config, baseline_sha="f" * 40),
            )

        # The drifted workflow was durably failed; a second resume attempt finds it terminal.
        with pytest.raises(WorkflowAlreadyTerminalError):
            WorkflowSession.resume(
                config,
                workflow_id="wf-1",
                stage_id="AUTO-002",
                planned_stage_branch="feature/auto-002-orchestrator-state-machine",
                current_binding=_current_binding(config),
                _observer=_StaticObserver(config),
            )


class TestRepairAttemptDelegation:
    def _to_validating(self, session: WorkflowSession) -> None:
        session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        session.transition_to(WorkflowState.BRANCH_CREATED, actor="orchestrator")
        session.transition_to(WorkflowState.IMPLEMENTING, actor="orchestrator")
        session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")

    def test_evaluate_record_and_reconstruct_round_trip_through_the_session(
        self, tmp_path: Path
    ) -> None:
        session = _start(tmp_path)
        self._to_validating(session)

        first = session.evaluate_repair_attempt(WorkflowState.VALIDATING)
        assert first.outcome is RetryOutcome.NO_RETRY_REQUIRED

        # A repair attempt can only be recorded while the workflow is durably in REPAIRING (the
        # repair provider only ever runs there) — `state=VALIDATING` identifies which gate
        # *triggered* this REPAIRING cycle, for the per-workflow aggregate counter.
        session.transition_to(WorkflowState.REPAIRING, actor="orchestrator")
        session.record_repair_attempt_started(
            WorkflowState.VALIDATING,
            attempt_number=1,
            start_time="2026-07-24T12:00:00+00:00",
        )
        assert session.has_unreconciled_repair_attempt() is True
        session.record_repair_attempt(
            WorkflowState.VALIDATING,
            attempt_number=1,
            completion_time="2026-07-24T12:05:00+00:00",
        )
        assert session.has_unreconciled_repair_attempt() is False
        attempts = session.reconstruct_repair_attempts()
        assert len(attempts) == 1
        session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")

        second = session.evaluate_repair_attempt(WorkflowState.VALIDATING)
        assert second.outcome is RetryOutcome.RETRY_ALLOWED
        session.transition_to(WorkflowState.FAILED, actor="orchestrator")


class TestRepairAttemptLimitIsFixedAtThree:
    """Release-gate finding: every repair-attempt method on the supported `WorkflowSession`
    facade must be bound to `WorkflowConfig.repair_attempt_limit` (schema-fixed `Literal[3]`) —
    none of them accept an `attempt_limit` argument at all, so no caller of this facade can
    request evaluation, reservation, or completion of a fourth repair attempt, whatever value it
    might otherwise have tried to supply.
    """

    def _to_validating(self, session: WorkflowSession) -> None:
        session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        session.transition_to(WorkflowState.BRANCH_CREATED, actor="orchestrator")
        session.transition_to(WorkflowState.IMPLEMENTING, actor="orchestrator")
        session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")

    def _complete_one_repair_attempt(
        self, session: WorkflowSession, *, attempt_number: int, minute: int
    ) -> None:
        session.transition_to(WorkflowState.REPAIRING, actor="orchestrator")
        session.record_repair_attempt_started(
            WorkflowState.VALIDATING,
            attempt_number=attempt_number,
            start_time=f"2026-07-24T12:{minute:02d}:00+00:00",
        )
        session.record_repair_attempt(
            WorkflowState.VALIDATING,
            attempt_number=attempt_number,
            completion_time=f"2026-07-24T12:{minute + 1:02d}:00+00:00",
        )
        session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")

    def test_attempts_one_two_and_three_are_permitted(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        self._to_validating(session)
        for attempt_number, minute in ((1, 0), (2, 10), (3, 20)):
            result = session.evaluate_repair_attempt(WorkflowState.VALIDATING)
            assert result.outcome in (RetryOutcome.NO_RETRY_REQUIRED, RetryOutcome.RETRY_ALLOWED)
            self._complete_one_repair_attempt(session, attempt_number=attempt_number, minute=minute)
        attempts = session.reconstruct_repair_attempts()
        assert len(attempts) == 3
        session.transition_to(WorkflowState.FAILED, actor="orchestrator")

    def test_attempt_four_is_rejected(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        self._to_validating(session)
        for attempt_number, minute in ((1, 0), (2, 10), (3, 20)):
            self._complete_one_repair_attempt(session, attempt_number=attempt_number, minute=minute)

        fourth_evaluation = session.evaluate_repair_attempt(WorkflowState.VALIDATING)
        assert fourth_evaluation.outcome is RetryOutcome.RETRY_LIMIT_EXHAUSTED

        session.transition_to(WorkflowState.REPAIRING, actor="orchestrator")
        with pytest.raises(AttemptLimitExceededError):
            session.record_repair_attempt_started(
                WorkflowState.VALIDATING,
                attempt_number=4,
                start_time="2026-07-24T13:00:00+00:00",
            )
        # Rejected reservation must never let a 4th attempt be recorded as completed either.
        assert len(session.reconstruct_repair_attempts()) == 3
        session.transition_to(WorkflowState.FAILED, actor="orchestrator")

    def test_callers_cannot_override_the_limit(self, tmp_path: Path) -> None:
        session = _start(tmp_path)
        self._to_validating(session)
        with pytest.raises(TypeError):
            session.evaluate_repair_attempt(  # type: ignore[call-arg]
                WorkflowState.VALIDATING, attempt_limit=999
            )
        with pytest.raises(TypeError):
            session.reconstruct_repair_attempts(attempt_limit=999)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            session.record_repair_attempt_started(  # type: ignore[call-arg]
                WorkflowState.VALIDATING,
                attempt_number=1,
                attempt_limit=999,
                start_time="2026-07-24T12:00:00+00:00",
            )
        session.transition_to(WorkflowState.FAILED, actor="orchestrator")

    def test_restart_reconstructs_the_same_fixed_limit(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        first = _start(tmp_path, config=config)
        self._to_validating(first)
        for attempt_number, minute in ((1, 0), (2, 10), (3, 20)):
            self._complete_one_repair_attempt(first, attempt_number=attempt_number, minute=minute)
        first._resumed.lock.release()

        resumed = WorkflowSession.resume(
            config,
            workflow_id="wf-1",
            stage_id="AUTO-002",
            planned_stage_branch="feature/auto-002-orchestrator-state-machine",
            current_binding=_current_binding(config),
            _observer=_StaticObserver(config),
        )
        assert resumed._repair_attempt_limit == 3
        fourth_evaluation = resumed.evaluate_repair_attempt(WorkflowState.VALIDATING)
        assert fourth_evaluation.outcome is RetryOutcome.RETRY_LIMIT_EXHAUSTED
        resumed.transition_to(WorkflowState.FAILED, actor="orchestrator")


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, text=True, capture_output=True
    )


class TestInitialExecutionEvidenceDelegation:
    def test_evaluate_initial_execution_failure_supplies_repository_scope_automatically(
        self, tmp_path: Path
    ) -> None:
        # AUTO002-F07 (Human Owner decision 2026-07-27): confirmed evidence is now independently
        # re-verified against real local Git/filesystem state, so this session's repository must
        # be a genuine Git repository with a real, branch-reachable commit — a fabricated SHA (the
        # old `"a" * 40`) can no longer pass.
        repository_path = tmp_path / "repo"
        (repository_path / "docs" / "workflow-automation").mkdir(parents=True)
        (repository_path / "docs" / "workflow-automation" / "AUTO-002.md").write_text(
            "contract\n", encoding="utf-8"
        )
        _git(repository_path, "init", "-b", "feature/auto-002-orchestrator-state-machine")
        _git(repository_path, "config", "user.name", "F07 Test")
        _git(repository_path, "config", "user.email", "f07@example.invalid")
        _git(repository_path, "add", ".")
        _git(repository_path, "commit", "-m", "baseline")
        baseline_sha = _git(repository_path, "rev-parse", "HEAD").stdout.strip()
        implementation_path = (
            repository_path / "docs" / "workflow-automation" / "implementation.txt"
        )
        implementation_path.write_text("implemented\n", encoding="utf-8")
        _git(repository_path, "add", ".")
        _git(repository_path, "commit", "-m", "implementation commit")
        head_sha = _git(repository_path, "rev-parse", "HEAD").stdout.strip()
        changed_paths = ("docs/workflow-automation/implementation.txt",)

        config = _config(tmp_path, repository_path=repository_path)
        session = _start(tmp_path, config=config, baseline_commit_sha=baseline_sha)
        session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        session.transition_to(WorkflowState.BRANCH_CREATED, actor="orchestrator")
        session.transition_to(WorkflowState.IMPLEMENTING, actor="orchestrator")

        session.record_initial_execution_attempt_started(
            WorkflowState.IMPLEMENTING,
            attempt_number=1,
            start_time="2026-07-24T12:00:00+00:00",
        )
        session.record_initial_execution_attempt(
            WorkflowState.IMPLEMENTING,
            attempt_number=1,
            completion_time="2026-07-24T12:01:00+00:00",
        )

        artifact_directory = (
            config.audit_directory / session.workflow_id / "evidence" / "IMPLEMENTING"
        )
        artifact_directory.mkdir(parents=True)
        (artifact_directory / "impl-1.json").write_text(
            json.dumps(
                {
                    "workflow_id": session.workflow_id,
                    "stage_id": session.stage_id,
                    "attempt_number": 1,
                    "stage_branch": "feature/auto-002-orchestrator-state-machine",
                    "observed_head_sha": head_sha,
                    "changed_paths": list(changed_paths),
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Evidence bound to a *different* repository_path than the session's own must be
        # rejected — the session supplies its own repository_identity/repository_path
        # automatically; a caller cannot silently smuggle in evidence scoped elsewhere.
        wrong_scope_evidence = ReconciliationEvidence(
            workflow_id=session.workflow_id,
            repository_identity=session.repository_identity,
            repository_path=str(tmp_path / "some-other-repo"),
            stage_id=session.stage_id,
            side_effect_confirmed=True,
            side_effect_succeeded=True,
            evidence=ImplementationDiffEvidence(
                stage_branch="feature/auto-002-orchestrator-state-machine",
                observed_head_sha=head_sha,
                completion_report_reference="impl-1.json",
                attempt_number=1,
                changed_paths=changed_paths,
            ),
        )
        with pytest.raises(EvidenceScopeMismatchError):
            session.evaluate_initial_execution_failure(
                WorkflowState.IMPLEMENTING,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=wrong_scope_evidence,
            )

        correct_evidence = wrong_scope_evidence.model_copy(
            update={"repository_path": str(session._repository_path)}
        )
        result = session.evaluate_initial_execution_failure(
            WorkflowState.IMPLEMENTING,
            failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
            evidence=correct_evidence,
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_SUCCESSFUL
        assert result.next_allowed_state is WorkflowState.VALIDATING
        session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
        session.transition_to(WorkflowState.FAILED, actor="orchestrator")
