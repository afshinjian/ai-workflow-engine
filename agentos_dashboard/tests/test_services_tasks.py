"""`services.tasks` — DR-030..033's task detail view: recorded scope, the acceptance-criteria
checklist, lifecycle history, Git provenance, and related documents."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.services.tasks import build_task_detail
from agentos_dashboard.tests.conftest import (
    event_digest,
    git,
    record_legacy_event,
    write,
    write_self_governance,
)


def test_unknown_task_id_returns_none(root: RepositoryRoot) -> None:
    assert build_task_detail(build_snapshot(root), "NOPE-1") is None


def test_missing_queue_document_returns_none(workspace: Path, root: RepositoryRoot) -> None:
    assert build_task_detail(build_snapshot(root), "FIX-001") is None


def test_task_id_lookup_is_case_insensitive(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "fix-001")
    assert detail is not None
    assert detail.task_id == "FIX-001"


def test_recorded_scope_is_the_raw_prose_verbatim(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing carefully.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert detail.raw_text == "— do the thing\n\nStatus: Current\n\nDo the thing carefully."


def test_task_repository_text_is_redacted_only_in_the_display_model(
    workspace: Path, root: RepositoryRoot
) -> None:
    secret = "sk-eeeeeeeeeeeeeeeeeeeeeeee"
    source = f"## FIX-001 — api_key={secret}\n\nStatus: Current\n\nBearer {secret}.\n\n"
    write(workspace, "docs/TASK_QUEUE.md", source)
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert secret not in detail.title
    assert secret not in detail.raw_text
    assert (workspace / "docs/TASK_QUEUE.md").read_text(encoding="utf-8") == source


def test_acceptance_checklist_items_are_checked_only_when_the_task_is_done(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — planned work\n\nStatus: Planned\n\nDo one thing. Then do another.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert len(detail.acceptance_items) >= 1
    assert all(item.done is False for item in detail.acceptance_items)


def test_acceptance_checklist_items_are_checked_when_the_task_is_done(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — finished work\n\nStatus: Done\n\nDid one thing. Did another.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert len(detail.acceptance_items) >= 1
    assert all(item.done is True for item in detail.acceptance_items)


def test_validation_and_rollback_notes_are_recognized_by_keyword(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — careful work\n\nStatus: Done\n\n"
        "The test suite is green. Rollback is a straight revert of this commit.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert any("suite" in note.lower() for note in detail.validation_notes)
    assert any(
        "rollback" in note.lower() or "revert" in note.lower() for note in detail.rollback_notes
    )


def test_validation_and_rollback_notes_are_empty_when_not_recorded(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — bare\n\nStatus: Planned\n\nNothing keyword-worthy here.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert detail.validation_notes == ()
    assert detail.rollback_notes == ()


def test_lifecycle_events_recognize_a_review_verdict(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — reviewed\n\nStatus: Done\n\n"
        "Round-1 independent plan review REJECTED (one finding); round-2 independent review "
        "APPROVED.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    kinds = [event.kind for event in detail.lifecycle_events]
    assert "review" in kinds


def test_lifecycle_events_recognize_a_merge(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — merged\n\nStatus: Done\n\nMerged into `main` via PR #1.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert any(event.kind == "merge" for event in detail.lifecycle_events)


def test_doc_references_report_existence(workspace: Path, root: RepositoryRoot) -> None:
    write(workspace, "docs/reports/STAGE-01-completion.md", "report body\n")
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — reported\n\nStatus: Done\n\n"
        "Report: `docs/reports/STAGE-01-completion.md`. Also see `docs/MISSING.md`.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    by_path = {ref.path: ref.exists for ref in detail.doc_references}
    assert by_path["docs/reports/STAGE-01-completion.md"] is True
    assert by_path["docs/MISSING.md"] is False


def test_commit_references_are_resolved_against_real_git(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "README.md", "hello\n")
    git(workspace, "init", "--quiet", "--initial-branch=main")
    git(workspace, "add", "README.md")
    git(workspace, "commit", "--quiet", "-m", "first commit")
    sha = git(workspace, "rev-parse", "HEAD")
    short = sha[:7]
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        f"## FIX-001 — has a commit\n\nStatus: Done\n\n"
        f"Committed as `{short}`. Also mentions `deadbee` which resolves to nothing real.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    by_token = {ref.token: ref for ref in detail.commit_references}
    assert by_token[short].resolvable is True
    assert by_token[short].resolved_sha == sha
    assert by_token["deadbee"].resolvable is False
    assert by_token["deadbee"].resolved_sha is None


def test_referenced_tasks_exclude_self(workspace: Path, root: RepositoryRoot) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-002 — follow-up\n\nStatus: Planned\n\n" "FIX-002 follows on from FIX-001.\n\n",
    )
    detail = build_task_detail(build_snapshot(root), "FIX-002")
    assert detail is not None
    assert detail.referenced_tasks == ("FIX-001",)


def test_non_dash_task_has_no_stage_contract(workspace: Path, root: RepositoryRoot) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — plain\n\nStatus: Planned\n\nWork.\n\n")
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert detail.stage_contract is None


def test_dash_task_with_no_contract_file_has_no_stage_contract(
    workspace: Path, root: RepositoryRoot
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## DASH-099 — future\n\nStatus: Planned\n\nTBD.\n\n")
    detail = build_task_detail(build_snapshot(root), "DASH-099")
    assert detail is not None
    assert detail.stage_contract is None


def test_the_real_repository_renders_t_401s_two_round_review_history() -> None:
    real_root = RepositoryRoot.from_path(Path(__file__).resolve().parents[2])
    detail = build_task_detail(build_snapshot(real_root), "T-401")
    assert detail is not None
    assert detail.status is TaskStatus.DONE
    assert any(event.kind == "review" for event in detail.lifecycle_events)


def test_the_real_repository_renders_dash_001_with_its_stage_contract() -> None:
    real_root = RepositoryRoot.from_path(Path(__file__).resolve().parents[2])
    detail = build_task_detail(build_snapshot(real_root), "DASH-001")
    assert detail is not None
    assert detail.status is TaskStatus.DONE
    assert detail.stage_contract is not None
    assert detail.stage_contract.path == "docs/agentos-dashboard/stage-prompts/DASH-001.md"


def test_the_real_repository_renders_gov_1_and_t_501_as_done() -> None:
    real_root = RepositoryRoot.from_path(Path(__file__).resolve().parents[2])
    snapshot = build_snapshot(real_root)
    gov_1 = build_task_detail(snapshot, "GOV-1")
    t_501 = build_task_detail(snapshot, "T-501")
    assert gov_1 is not None and gov_1.status is TaskStatus.DONE
    assert t_501 is not None and t_501.status is TaskStatus.DONE


# ---- DASH-005 remediation: per-task Legacy workflow projection (`services.legacy_workflow`) --


def test_task_detail_legacy_workflow_has_no_history_without_persisted_events(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert detail.legacy_workflow.available is True
    assert detail.legacy_workflow.has_history is False
    assert detail.legacy_workflow.current_stage is None


def test_task_detail_legacy_workflow_reflects_a_rejection_and_remediation_replay(
    workspace: Path, root: RepositoryRoot, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Current\n\nBody.\n\n")
    e1 = record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="plan-review",
        verdict="APPROVED",
        sequence=1,
        parent_digest=None,
        repository=str(workspace),
    )
    e2 = record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="implementation",
        sequence=2,
        parent_digest=event_digest(e1),
        repository=str(workspace),
    )
    record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="implementation-review",
        verdict="REJECTED",
        sequence=3,
        parent_digest=event_digest(e2),
        repository=str(workspace),
    )

    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    # Task Queue status and Legacy workflow position are independent facts.
    assert detail.status is TaskStatus.CURRENT
    assert detail.legacy_workflow.has_history is True
    assert detail.legacy_workflow.current_stage == "remediation"
    assert detail.legacy_workflow.terminal is False
    assert len(detail.legacy_workflow.events) == 3
    rejected = [e for e in detail.legacy_workflow.events if e.outcome == "REJECTED"]
    assert len(rejected) == 1
    assert rejected[0].stage == "implementation-review"
    assert rejected[0].resulting_stage == "remediation"


def test_task_detail_legacy_workflow_unavailable_is_distinct_from_no_history(
    workspace: Path, root: RepositoryRoot
) -> None:
    """No `self-governance.yaml` at all -> `available=False` (an explicit error), never
    conflated with the legitimate "no persisted events yet" (`has_history=False`) state."""
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    detail = build_task_detail(build_snapshot(root), "FIX-001")
    assert detail is not None
    assert detail.legacy_workflow.available is False
    assert detail.legacy_workflow.has_history is False
    assert detail.legacy_workflow.error is not None
