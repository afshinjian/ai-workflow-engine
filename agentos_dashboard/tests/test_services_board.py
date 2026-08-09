"""`services.board` — DR-020..023's board data: lanes, the workflow-stage strip, the ORCH
program lane, and the unclassified lane + finding."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.services.board import EvidenceState, build_board
from agentos_dashboard.services.workflow import WORKFLOW_STAGES
from agentos_dashboard.tests.conftest import record_legacy_event, write, write_self_governance


def test_board_is_empty_with_no_governance_documents(root: RepositoryRoot) -> None:
    board = build_board(build_snapshot(root))
    assert board.planned == ()
    assert board.current == ()
    assert board.done == ()
    assert board.unclassified == ()
    assert board.workflow_stages == WORKFLOW_STAGES
    assert any(f.rule == "document_missing" for f in board.findings)


def test_cards_are_sorted_into_the_three_queue_lanes(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-000 — earlier\n\nStatus: Done\n\nAll done.\n\n"
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing.\n\n"
        "## FIX-002 — later\n\nStatus: Planned\n\nLater work.\n\n",
    )
    board = build_board(build_snapshot(root))
    assert [c.task_id for c in board.done] == ["FIX-000"]
    assert [c.task_id for c in board.current] == ["FIX-001"]
    assert [c.task_id for c in board.planned] == ["FIX-002"]


def test_card_program_is_derived_from_the_task_id_prefix(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## DASH-005 — Workflow board\n\nStatus: Current\n\nBuild it.\n\n",
    )
    board = build_board(build_snapshot(root))
    (card,) = board.current
    assert card.program == "DASH"
    assert card.title == "Workflow board"


def test_card_title_falls_back_to_task_id_when_the_heading_has_no_suffix(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-003\n\nStatus: Planned\n\nBody.\n\n")
    board = build_board(build_snapshot(root))
    (card,) = board.planned
    assert card.title == "FIX-003"


def test_referenced_tasks_are_extracted_from_prose(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-002 — follow-up\n\nStatus: Planned\n\n"
        "Follow-up to FIX-001, closes the gap FIX-001 left open.\n\n",
    )
    board = build_board(build_snapshot(root))
    (card,) = board.planned
    assert card.referenced_tasks == ("FIX-001",)


def test_evidence_is_unknown_when_no_document_is_referenced(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — bare\n\nStatus: Planned\n\nNo refs.\n\n")
    board = build_board(build_snapshot(root))
    (card,) = board.planned
    assert card.evidence is EvidenceState.UNKNOWN


def test_evidence_passes_when_every_referenced_document_exists(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "docs/reports/STAGE-01-completion.md", "report body\n")
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — reported\n\nStatus: Done\n\n"
        "Report: `docs/reports/STAGE-01-completion.md`.\n\n",
    )
    board = build_board(build_snapshot(root))
    (card,) = board.done
    assert card.evidence is EvidenceState.PASS


def test_evidence_fails_when_a_referenced_document_is_missing(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — reported\n\nStatus: Done\n\n"
        "Report: `docs/reports/STAGE-01-completion.md`.\n\n",
    )
    board = build_board(build_snapshot(root))
    (card,) = board.done
    assert card.evidence is EvidenceState.FAIL


def test_unclassified_status_renders_in_its_own_lane_with_a_finding(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-009 — mystery status\n\nStatus: Blocked\n\nSomething odd.\n\n"
        "## FIX-001 — normal\n\nStatus: Planned\n\nFine.\n\n",
    )
    board = build_board(build_snapshot(root))
    assert [c.task_id for c in board.planned] == ["FIX-001"]
    assert len(board.unclassified) == 1
    unclassified = board.unclassified[0]
    assert unclassified.task_id == "FIX-009"
    assert unclassified.raw_status is not None
    assert "Blocked" in unclassified.raw_status
    assert any(f.rule == "unclassified_task_status" for f in board.findings)


def test_missing_status_field_is_also_unclassified(workspace: Path, root: RepositoryRoot) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-009 — no status at all\n\nNo status here.\n\n")
    board = build_board(build_snapshot(root))
    assert len(board.unclassified) == 1
    assert board.unclassified[0].raw_status is None


def test_a_heading_without_a_task_id_is_never_unclassified(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## Just a section heading\n\nNo id here at all.\n\n")
    board = build_board(build_snapshot(root))
    assert board.unclassified == ()


def test_orch_stages_are_read_from_the_implementation_state_yaml(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/implementation/orchestration/implementation-state.yaml",
        "feature_id: fixture\n"
        "current_stage: ORCH-001\n"
        "next_eligible_stage: null\n"
        "delivery_order: [ORCH-001]\n"
        "stages:\n"
        "  ORCH-001:\n"
        "    title: Fixture stage\n"
        "    status: in_progress\n"
        "    prerequisites: []\n"
        "    blockers: []\n"
        "    evidence: []\n",
    )
    board = build_board(build_snapshot(root))
    assert [s.stage_id for s in board.orch_stages] == ["ORCH-001"]


def test_the_real_repository_renders_gov_1_and_t_501_as_done() -> None:
    real_root = RepositoryRoot.from_path(Path(__file__).resolve().parents[2])
    board = build_board(build_snapshot(real_root))
    done_ids = {card.task_id for card in board.done}
    assert "GOV-1" in done_ids
    assert "T-501" in done_ids
    dash_001 = next(card for card in board.done if card.task_id == "DASH-001")
    assert dash_001.status is TaskStatus.DONE


# ---- DASH-005 remediation: per-task Legacy workflow projection (`services.legacy_workflow`) --


def test_board_card_legacy_workflow_is_unavailable_without_self_governance_yaml(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    board = build_board(build_snapshot(root))
    (card,) = board.planned
    assert card.legacy_workflow.available is False
    assert card.legacy_workflow.error is not None


def test_board_card_legacy_workflow_has_no_history_when_none_persisted(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    board = build_board(build_snapshot(root))
    (card,) = board.planned
    assert card.legacy_workflow.available is True
    assert card.legacy_workflow.has_history is False
    assert card.legacy_workflow.current_stage is None


def test_board_cards_expose_independent_queue_status_and_legacy_workflow_stage(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    """DR-020/DR-023 (remediation item 2): the queue's Planned/Current/Done status and the
    Legacy engine's own event-sourced stage are two separate facts, never merged -- a Planned
    task can already have Legacy workflow history, and a Done task can have none recorded."""
    write_self_governance(workspace, "proj")
    record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — has legacy history\n\nStatus: Planned\n\nBody.\n\n"
        "## FIX-002 — no legacy history\n\nStatus: Done\n\nBody.\n\n",
    )
    board = build_board(build_snapshot(root))
    (planned_card,) = board.planned
    (done_card,) = board.done

    assert planned_card.status is TaskStatus.PLANNED
    assert planned_card.legacy_workflow.has_history is True
    assert planned_card.legacy_workflow.current_stage == "implementation"

    assert done_card.status is TaskStatus.DONE
    assert done_card.legacy_workflow.has_history is False
    assert done_card.legacy_workflow.current_stage is None

    # Different tasks, different actual Legacy-workflow positions.
    assert planned_card.legacy_workflow.current_stage != done_card.legacy_workflow.current_stage
