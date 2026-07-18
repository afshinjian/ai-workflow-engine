import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.workflow import event_store
from ai_workflow_engine.workflow.event_store import (
    SequenceConflict,
    StateAddressingError,
    StateCorrupt,
    StateIdentityMismatch,
    _event_bytes,
    append,
    derive_state,
    load_history,
    record_outcome,
    state_directory,
    task_dir_name,
)
from ai_workflow_engine.workflow.events import VERDICT_STAGES, Verdict, WorkflowEvent, WorkflowStage
from ai_workflow_engine.workflow.transitions import TerminalTask, TransitionViolation

_HEAD = "a" * 40
_REPO = "/tmp/not-the-state-dir"


@pytest.fixture(autouse=True)
def _isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def build_event(
    *,
    project_id: str = "proj",
    task_id: str = "T-1",
    stage: WorkflowStage,
    verdict: Verdict | None = None,
    sequence: int = 1,
    parent_digest: str | None = None,
    head: str = _HEAD,
    note: str = "",
) -> WorkflowEvent:
    action = "verdict" if stage in VERDICT_STAGES else "completed"
    return WorkflowEvent(
        schema_version="1.0",
        project_id=project_id,
        task_id=task_id,
        sequence=sequence,
        parent_digest=parent_digest,
        stage=stage,
        action=action,
        verdict=verdict,
        prompt_id=None,
        agent_run_id=None,
        head=head,
        note=note,
    )


# ---- addressing -----------------------------------------------------------------


def test_task_dir_is_collision_free_for_colliding_readable() -> None:
    # "a/b" and "a_b" sanitize to the same readable prefix but must not share a directory.
    assert task_dir_name("a/b") != task_dir_name("a_b")
    assert task_dir_name("a/b").startswith("a_b-")
    assert task_dir_name("a_b").startswith("a_b-")


def test_invalid_project_id_rejected() -> None:
    with pytest.raises(StateAddressingError):
        state_directory("-bad", "T-1")


def test_repository_containment_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point the state root inside the "repository" and confirm append refuses.
    repo = tmp_path / "repo"
    (repo / ".ai-workflow-engine").mkdir(parents=True)
    monkeypatch.setattr(event_store, "_artifact_root", lambda: repo / ".ai-workflow-engine" / "s")
    event = build_event(stage="plan-review", verdict="APPROVED")
    with pytest.raises(StateAddressingError):
        append(event, repository=str(repo))


# ---- append / load round trip --------------------------------------------------


def test_append_and_load_round_trip() -> None:
    event = build_event(stage="plan-review", verdict="APPROVED")
    append(event, repository=_REPO)
    history = load_history("proj", "T-1")
    assert len(history) == 1
    assert history[0] == event


def test_sequence_conflict_on_differing_bytes() -> None:
    append(build_event(stage="plan-review", verdict="APPROVED"), repository=_REPO)
    with pytest.raises(SequenceConflict):
        append(build_event(stage="plan-review", verdict="REJECTED"), repository=_REPO)


def test_identical_append_is_idempotent() -> None:
    event = build_event(stage="plan-review", verdict="APPROVED")
    append(event, repository=_REPO)
    append(event, repository=_REPO)  # no raise
    assert len(load_history("proj", "T-1")) == 1


def test_concurrent_differing_appends_exactly_one_wins() -> None:
    barrier = threading.Barrier(2)
    events = [
        build_event(stage="plan-review", verdict="APPROVED"),
        build_event(stage="plan-review", verdict="REJECTED"),
    ]

    def worker(event: WorkflowEvent) -> str:
        barrier.wait()
        try:
            append(event, repository=_REPO)
            return "ok"
        except SequenceConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(worker, events))
    assert results == ["conflict", "ok"]
    assert len(load_history("proj", "T-1")) == 1


# ---- load verification ---------------------------------------------------------


def _dir_for(task_id: str = "T-1") -> Path:
    directory = state_directory("proj", task_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_load_rejects_foreign_file() -> None:
    directory = _dir_for()
    (directory / "notes.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_gap() -> None:
    append(build_event(stage="plan-review", verdict="APPROVED"), repository=_REPO)
    directory = state_directory("proj", "T-1")
    # Rename 00000001 -> 00000002 to create a gap (no 00000001).
    (directory / "00000001.json").rename(directory / "00000002.json")
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_invalid_event_json() -> None:
    directory = _dir_for()
    # Well-formed JSON that is not a valid WorkflowEvent (missing/extra fields).
    (directory / "00000001.json").write_bytes(b'{ "x": 1 }\n')
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_valid_event_stored_noncanonically() -> None:
    # A fully valid event, but serialized with non-canonical byte layout (default json.dumps
    # spacing, unsorted keys). It parses and model-validates, so this exercises the canonical
    # re-serialization guard specifically, not the model-validation branch.
    directory = _dir_for()
    event = build_event(stage="plan-review", verdict="APPROVED")
    noncanonical = json.dumps(event.model_dump(mode="json")).encode("utf-8") + b"\n"
    assert noncanonical != _event_bytes(event)  # confirms it is genuinely non-canonical
    assert noncanonical.count(b"\n") == 1  # so it passes the terminal-newline check first
    (directory / "00000001.json").write_bytes(noncanonical)
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_duplicate_keys() -> None:
    directory = _dir_for()
    (directory / "00000001.json").write_bytes(b'{"a":1,"a":2}\n')
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_missing_terminal_newline() -> None:
    directory = _dir_for()
    event = build_event(stage="plan-review", verdict="APPROVED")
    (directory / "00000001.json").write_bytes(_event_bytes(event).rstrip(b"\n"))
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_identity_mismatch() -> None:
    directory = _dir_for("T-1")
    # A valid event that belongs to a different task, planted in T-1's directory.
    foreign = build_event(task_id="T-2", stage="plan-review", verdict="APPROVED")
    (directory / "00000001.json").write_bytes(_event_bytes(foreign))
    with pytest.raises(StateIdentityMismatch):
        load_history("proj", "T-1")


def test_load_rejects_broken_parent_chain() -> None:
    directory = _dir_for()
    first = build_event(stage="plan-review", verdict="APPROVED")
    (directory / "00000001.json").write_bytes(_event_bytes(first))
    # Second event with a wrong parent_digest.
    second = build_event(stage="implementation", sequence=2, parent_digest="f" * 64)
    (directory / "00000002.json").write_bytes(_event_bytes(second))
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_rejects_stored_transition_violation() -> None:
    directory = _dir_for()
    first = build_event(stage="plan-review", verdict="APPROVED")
    (directory / "00000001.json").write_bytes(_event_bytes(first))
    parent = hashlib.sha256(_event_bytes(first)).hexdigest()
    # plan-review APPROVED expects "implementation"; store "remediation" instead.
    bad = build_event(stage="remediation", sequence=2, parent_digest=parent)
    (directory / "00000002.json").write_bytes(_event_bytes(bad))
    with pytest.raises(StateCorrupt):
        load_history("proj", "T-1")


def test_load_ignores_leftover_temp_files() -> None:
    append(build_event(stage="plan-review", verdict="APPROVED"), repository=_REPO)
    directory = state_directory("proj", "T-1")
    (directory / ".deadbeef.json.tmp").write_bytes(b"garbage")
    assert len(load_history("proj", "T-1")) == 1


# ---- record_outcome (needs a real git repo for HEAD) ---------------------------


def test_record_outcome_happy_path(engine_config: EngineConfig) -> None:
    project = engine_config.project.id
    event = record_outcome(engine_config, "T-42", stage="plan-review", verdict="APPROVED")
    assert event.sequence == 1
    assert event.head  # real commit hash from the temp repo
    state = derive_state(project, "T-42")
    assert state.next_stage == "implementation"
    assert not state.terminal


def test_record_outcome_full_cycle_to_terminal(engine_config: EngineConfig) -> None:
    project = engine_config.project.id
    steps: list[tuple[WorkflowStage, Verdict | None]] = [
        ("plan-review", "APPROVED"),
        ("implementation", None),
        ("implementation-review", "APPROVED"),
        ("governance-closeout", None),
        ("governance-review", "APPROVED"),
        ("push", None),
    ]
    for stage, verdict in steps:
        record_outcome(engine_config, "T-9", stage=stage, verdict=verdict)
    state = derive_state(project, "T-9")
    assert state.terminal
    assert state.next_stage is None
    with pytest.raises(TerminalTask):
        record_outcome(engine_config, "T-9", stage="plan-review", verdict="APPROVED")


def test_record_outcome_transition_violation(engine_config: EngineConfig) -> None:
    with pytest.raises(TransitionViolation):
        record_outcome(engine_config, "T-7", stage="implementation", verdict=None)


def test_record_outcome_two_colliding_readable_tasks_stay_separate(
    engine_config: EngineConfig,
) -> None:
    project = engine_config.project.id
    record_outcome(engine_config, "a/b", stage="plan-review", verdict="APPROVED")
    record_outcome(engine_config, "a_b", stage="plan-review", verdict="REJECTED")
    assert derive_state(project, "a/b").events[0].verdict == "APPROVED"
    assert derive_state(project, "a_b").events[0].verdict == "REJECTED"
