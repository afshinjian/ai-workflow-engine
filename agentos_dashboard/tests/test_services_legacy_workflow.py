"""`services.legacy_workflow` -- DASH-005 remediation (`OPEN_QUESTIONS.md` OD-D12): the
authoritative per-task Legacy-workflow projection, read via the real
`ai_workflow_engine.workflow.event_store` (never a dashboard-local re-implementation).

Covers remediation test items A-F and part of G:
A. persisted Legacy event history is loaded
B. `derive_state` semantics (current/next stage, terminal) are reflected in the projection
C. different tasks can appear at different actual workflow stages
D. a task with no workflow history does not receive a fabricated stage
E. rejection/remediation event histories replay correctly
F. terminal workflow histories render correctly
G. (partial) `available`/`error` failure handling never invents state and never mutates
"""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.legacy_workflow import load_legacy_workflow, read_project_id
from agentos_dashboard.tests.conftest import (
    event_digest,
    record_legacy_event,
    write,
    write_self_governance,
)
from ai_workflow_engine.workflow import event_store


def test_read_project_id_is_none_without_self_governance_yaml(root: RepositoryRoot) -> None:
    assert read_project_id(root) is None


def test_read_project_id_is_none_for_malformed_yaml(workspace: Path, root: RepositoryRoot) -> None:
    write(workspace, "self-governance.yaml", "project: [this, is, not, a, mapping]\n")
    assert read_project_id(root) is None


def test_read_project_id_reads_the_configured_id(workspace: Path, root: RepositoryRoot) -> None:
    write_self_governance(workspace, "my-project")
    assert read_project_id(root) == "my-project"


def test_no_self_governance_yaml_yields_unavailable_not_a_fabricated_stage(
    root: RepositoryRoot,
) -> None:
    projection = load_legacy_workflow(root, "T-1")
    assert projection.available is False
    assert projection.error is not None
    assert projection.has_history is False
    assert projection.current_stage is None
    assert projection.events == ()


def test_task_with_no_persisted_events_has_history_false_and_no_fabricated_current_stage(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    projection = load_legacy_workflow(root, "T-1")
    assert projection.available is True
    assert projection.error is None
    assert projection.has_history is False
    # `current_stage` must never be synthesized even though the engine's own `expected_stage([])`
    # legitimately reports `plan-review` as the next stage that *may* be recorded.
    assert projection.current_stage is None
    assert projection.next_stage == "plan-review"
    assert projection.terminal is False
    assert projection.events == ()
    assert projection.latest_event is None


def test_one_persisted_event_is_loaded_and_reflected_in_derived_state(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    projection = load_legacy_workflow(root, "T-1")
    assert projection.available is True
    assert projection.has_history is True
    assert len(projection.events) == 1
    assert projection.latest_event is not None
    assert projection.latest_event.stage == "plan-review"
    assert projection.latest_event.outcome == "APPROVED"
    assert projection.latest_event.resulting_stage == "implementation"
    # Not terminal, so the "current" position is the engine's own computed next stage.
    assert projection.current_stage == "implementation"
    assert projection.next_stage == "implementation"
    assert projection.terminal is False


def test_different_tasks_show_different_derived_stages(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    t2_e1 = record_legacy_event(
        project_id="proj",
        task_id="T-2",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    record_legacy_event(
        project_id="proj",
        task_id="T-2",
        stage="implementation",
        sequence=2,
        parent_digest=event_digest(t2_e1),
        repository=str(workspace),
    )

    t1 = load_legacy_workflow(root, "T-1")
    t2 = load_legacy_workflow(root, "T-2")
    assert t1.current_stage == "implementation"
    assert t2.current_stage == "implementation-review"
    assert t1.current_stage != t2.current_stage


def test_rejection_and_remediation_history_replays_correctly(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    e1 = record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    e2 = record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="implementation",
        sequence=2,
        parent_digest=event_digest(e1),
        repository=str(workspace),
    )
    e3 = record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="implementation-review",
        verdict="REJECTED",
        sequence=3,
        parent_digest=event_digest(e2),
        repository=str(workspace),
    )
    e4 = record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="remediation",
        sequence=4,
        parent_digest=event_digest(e3),
        repository=str(workspace),
    )
    record_legacy_event(
        project_id="proj",
        task_id="T-1",
        stage="implementation-review",
        verdict="APPROVED",
        sequence=5,
        parent_digest=event_digest(e4),
        repository=str(workspace),
    )

    projection = load_legacy_workflow(root, "T-1")
    assert projection.available is True
    assert len(projection.events) == 5
    assert projection.terminal is False
    assert projection.current_stage == "governance-closeout"

    rejected = [event for event in projection.events if event.outcome == "REJECTED"]
    assert len(rejected) == 1
    assert rejected[0].stage == "implementation-review"
    assert rejected[0].resulting_stage == "remediation"

    remediation_events = [event for event in projection.events if event.stage == "remediation"]
    assert len(remediation_events) == 1
    assert remediation_events[0].resulting_stage == "implementation-review"

    # The task was reviewed at `implementation-review` twice: REJECTED, then APPROVED.
    review_events = [event for event in projection.events if event.stage == "implementation-review"]
    assert [event.outcome for event in review_events] == ["REJECTED", "APPROVED"]


def test_terminal_workflow_history_renders_correctly(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    stages_and_verdicts: list[tuple[str, str | None]] = [
        ("plan-review", "APPROVED"),
        ("implementation", None),
        ("implementation-review", "APPROVED"),
        ("governance-closeout", None),
        ("governance-review", "APPROVED"),
        ("push", None),
    ]
    parent_digest = None
    for index, (stage, verdict) in enumerate(stages_and_verdicts, start=1):
        event = record_legacy_event(
            project_id="proj",
            task_id="T-1",
            stage=stage,  # type: ignore[arg-type]
            verdict=verdict,  # type: ignore[arg-type]
            sequence=index,
            parent_digest=parent_digest,
            repository=str(workspace),
        )
        parent_digest = event_digest(event)

    projection = load_legacy_workflow(root, "T-1")
    assert projection.available is True
    assert projection.has_history is True
    assert projection.terminal is True
    assert projection.next_stage is None
    assert projection.current_stage == "push"
    assert len(projection.events) == 6
    assert projection.latest_event is not None
    assert projection.latest_event.stage == "push"
    assert projection.latest_event.resulting_stage is None


def test_corrupt_event_store_yields_unavailable_never_raises_never_mutates(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    directory = event_store.state_directory("proj", "T-1")
    directory.mkdir(parents=True)
    # Bytes that are valid JSON but not canonical-form/verified: corrupts the store without going
    # through `event_store.append`.
    (directory / "00000001.json").write_bytes(b'{"not": "a workflow event"}\n')

    queue_before = workspace / "docs" / "TASK_QUEUE.md"
    assert not queue_before.exists()  # sanity: nothing to accidentally mutate either

    projection = load_legacy_workflow(root, "T-1")
    assert projection.available is False
    assert projection.error is not None
    assert projection.has_history is False
    assert projection.current_stage is None
    assert projection.events == ()
    assert not queue_before.exists()


def test_invalid_task_id_yields_unavailable_not_a_raise(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    projection = load_legacy_workflow(root, "   ")
    assert projection.available is False
    assert projection.error is not None
