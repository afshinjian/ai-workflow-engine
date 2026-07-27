"""Regression tests for the third independent review's persistence findings."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentos_workflow.orchestrator.engine import (
    AttemptKind,
    AttemptPhase,
    AuthorizationRecord,
    CorruptedAttemptRecordError,
    CorruptedAuthorizationRecordError,
    RetryAttemptRecord,
    WorkflowState,
    _append_attempt_record_unlocked,
    _load_authorization_record,
    _persist_authorization_record,
    _read_persisted_attempts,
)
from agentos_workflow.orchestrator.lock import LockPathConfinementError, RepositoryLock
from agentos_workflow.orchestrator.state_store import (
    StateStore,
    StateStorePathConfinementError,
    StateTransitionRecord,
)


def _store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def _authorization() -> AuthorizationRecord:
    return AuthorizationRecord(
        workflow_id="wf",
        repository_identity="example/repo",
        repository_path="/repo",
        stage_id="S",
        stage_contract_path="contracts/S.md",
        stage_contract_hash="sha256:test",
        baseline_branch="main",
        baseline_commit_sha="a" * 40,
        planned_stage_branch="feature/S",
        authorized_at="2026-07-27T00:00:00+00:00",
        engine_version="1",
    )


def _transition() -> StateTransitionRecord:
    return StateTransitionRecord(
        workflow_id="wf",
        target_repository="example/repo",
        repository_path="/repo",
        stage_id="S",
        from_state="CREATED",
        to_state="CANCELLED",
        timestamp=datetime.now(UTC).isoformat(),
        actor="human",
    )


def _attempt() -> RetryAttemptRecord:
    return RetryAttemptRecord(
        workflow_id="wf",
        stage_id="S",
        state=WorkflowState.IMPLEMENTING,
        kind=AttemptKind.INITIAL_EXECUTION,
        attempt_number=1,
        phase=AttemptPhase.STARTED,
        timestamp=datetime.now(UTC).isoformat(),
    )


def test_lock_rejects_hard_link_without_touching_external_file(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    control = repository / ".agentos"
    control.mkdir(parents=True)
    external = tmp_path / "external"
    external.write_bytes(b"unchanged")
    os.link(external, control / "workflow.lock")

    lock = RepositoryLock(
        workflow_id="wf", repository_identity="example/repo", repository_path=repository
    )
    with pytest.raises(LockPathConfinementError):
        lock.acquire()
    assert external.read_bytes() == b"unchanged"


def test_transition_store_rejects_hard_link_without_appending_external_file(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    workflow = store.state_directory / "wf"
    workflow.mkdir(parents=True)
    external = tmp_path / "external"
    external.write_bytes(b"unchanged")
    os.link(external, workflow / "transitions.jsonl")

    with pytest.raises(StateStorePathConfinementError):
        store.record_transition(_transition())
    assert external.read_bytes() == b"unchanged"


def test_attempt_store_rejects_hard_link_without_appending_external_file(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    workflow = store.state_directory / "wf"
    workflow.mkdir(parents=True)
    external = tmp_path / "external"
    external.write_bytes(b"unchanged")
    os.link(external, workflow / "attempts.jsonl")

    with pytest.raises(StateStorePathConfinementError):
        _append_attempt_record_unlocked(store, "wf", _attempt())
    assert external.read_bytes() == b"unchanged"


@pytest.mark.parametrize("artifact", ["authorization", "attempt"])
def test_sidecar_write_rejects_cross_workflow_directory_symlink(
    tmp_path: Path, artifact: str
) -> None:
    store = _store(tmp_path)
    other = store.state_directory / "other"
    other.mkdir(parents=True)
    os.symlink("other", store.state_directory / "wf")

    with pytest.raises(StateStorePathConfinementError):
        if artifact == "authorization":
            _persist_authorization_record(store, _authorization())
        else:
            _append_attempt_record_unlocked(store, "wf", _attempt())
    assert list(other.iterdir()) == []


def test_authorization_duplicate_json_key_is_corruption(tmp_path: Path) -> None:
    store = _store(tmp_path)
    workflow = store.state_directory / "wf"
    workflow.mkdir(parents=True)
    raw = _authorization().model_dump_json()
    ambiguous = raw.replace('"workflow_id":"wf"', '"workflow_id":"other","workflow_id":"wf"')
    (workflow / "authorization.json").write_text(ambiguous, encoding="utf-8")

    with pytest.raises(CorruptedAuthorizationRecordError):
        _load_authorization_record(store, "wf")


def test_attempt_duplicate_json_key_is_corruption(tmp_path: Path) -> None:
    store = _store(tmp_path)
    workflow = store.state_directory / "wf"
    workflow.mkdir(parents=True)
    raw = _attempt().model_dump_json()
    ambiguous = raw.replace('"workflow_id":"wf"', '"workflow_id":"other","workflow_id":"wf"')
    (workflow / "attempts.jsonl").write_text(ambiguous + "\n", encoding="utf-8")

    with pytest.raises(CorruptedAttemptRecordError):
        _read_persisted_attempts(store, "wf")
