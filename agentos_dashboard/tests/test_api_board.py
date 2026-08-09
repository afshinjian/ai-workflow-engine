"""EP-04/EP-05/EP-06 (`API_SPEC.md` §2) — the board, task-detail, and workflow-machine JSON
routes DASH-005 delivers."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import (
    event_digest,
    record_legacy_event,
    write,
    write_self_governance,
)


def test_tasks_envelope_shape_with_no_governance_documents(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/tasks")
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    for key in (
        "planned",
        "current",
        "done",
        "unclassified",
        "orch_stages",
        "workflow_stages",
        "findings",
    ):
        assert key in data
    assert len(data["workflow_stages"]) == 7
    assert data["workflow_stages"][-1] == "push"


def test_tasks_lanes_reflect_the_queue(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing.\n\n"
        "## FIX-002 — later\n\nStatus: Planned\n\n",
    )
    data = client.get("/dash/api/v1/tasks").json()["data"]
    assert [c["task_id"] for c in data["current"]] == ["FIX-001"]
    assert [c["task_id"] for c in data["planned"]] == ["FIX-002"]
    card = data["current"][0]
    assert card["status"] == "Current"
    assert card["program"] == "FIX"
    assert "next_status" in card
    assert "transition_allowed" in card


def test_tasks_status_filter(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — current\n\nStatus: Current\n\nBody.\n\n"
        "## FIX-002 — planned\n\nStatus: Planned\n\nBody.\n\n",
    )
    data = client.get("/dash/api/v1/tasks?status=current").json()["data"]
    assert "current" in data
    assert "planned" not in data


def test_tasks_program_filter(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n"
        "## DASH-005 — b\n\nStatus: Planned\n\nBody.\n\n",
    )
    data = client.get("/dash/api/v1/tasks?program=DASH").json()["data"]
    assert [c["task_id"] for c in data["planned"]] == ["DASH-005"]


def test_unclassified_status_appears_on_the_board_endpoint(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-009 — odd\n\nStatus: Blocked\n\nBody.\n\n",
    )
    data = client.get("/dash/api/v1/tasks").json()["data"]
    assert [c["task_id"] for c in data["unclassified"]] == ["FIX-009"]
    assert any(f["rule"] == "unclassified_task_status" for f in data["findings"])


def test_task_detail_envelope_shape(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Done\n\nDid the thing.\n\n",
    )
    response = client.get("/dash/api/v1/tasks/FIX-001")
    assert response.status == 200
    data = response.json()["data"]
    for key in (
        "task_id",
        "title",
        "status",
        "program",
        "source",
        "line",
        "raw_text",
        "referenced_tasks",
        "acceptance_items",
        "validation_notes",
        "rollback_notes",
        "documentation_notes",
        "doc_references",
        "commit_references",
        "lifecycle_events",
        "stage_contract",
        "related_findings",
        "legacy_workflow",
    ):
        assert key in data
    assert data["status"] == "Done"
    for key in (
        "project_id",
        "available",
        "error",
        "has_history",
        "current_stage",
        "next_stage",
        "terminal",
        "latest_event",
        "events",
    ):
        assert key in data["legacy_workflow"]


def test_task_detail_unknown_id_returns_typed_404(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/tasks/NOPE-1")
    assert response.status == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_workflow_view_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/workflow")
    assert response.status == 200
    data = response.json()["data"]
    assert len(data["stages"]) == 7
    assert len(data["transitions"]) == 10
    assert isinstance(data["tasks"], list)
    verdict_stages = {s["stage"] for s in data["stages"] if s["verdict_stage"]}
    assert verdict_stages == {"plan-review", "implementation-review", "governance-review"}


def test_workflow_view_reports_per_task_transitions(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — current\n\nStatus: Current\n\nBody.\n\n",
    )
    data = client.get("/dash/api/v1/workflow").json()["data"]
    (task,) = data["tasks"]
    assert task["task_id"] == "FIX-001"
    assert task["status"] == "Current"
    assert task["next_status"] == "Done"
    assert task["allowed"] is True
    assert "legacy_workflow" in task
    assert task["legacy_workflow"]["has_history"] is False


# ---- DASH-005 remediation: the board/task-detail/workflow endpoints expose the authoritative
# per-task Legacy-workflow projection, distinct from the task-queue status above ------------


def test_board_endpoint_card_exposes_legacy_workflow_projection(
    workspace: Path, client: AsgiTestClient, isolated_state_home: Path
) -> None:
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
        "## FIX-001 — has legacy history\n\nStatus: Planned\n\nBody.\n\n",
    )
    data = client.get("/dash/api/v1/tasks").json()["data"]
    (card,) = data["planned"]
    assert card["status"] == "Planned"  # queue status: unaffected by Legacy workflow state
    legacy = card["legacy_workflow"]
    assert legacy["available"] is True
    assert legacy["has_history"] is True
    assert legacy["current_stage"] == "implementation"
    assert legacy["terminal"] is False
    assert len(legacy["events"]) == 1
    assert legacy["events"][0]["stage"] == "plan-review"
    assert legacy["events"][0]["outcome"] == "APPROVED"
    assert legacy["latest_event"]["stage"] == "plan-review"


def test_task_detail_endpoint_exposes_terminal_legacy_workflow(
    workspace: Path, client: AsgiTestClient, isolated_state_home: Path
) -> None:
    write_self_governance(workspace, "proj")
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
    e3 = record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="implementation-review",
        verdict="APPROVED",
        sequence=3,
        parent_digest=event_digest(e2),
        repository=str(workspace),
    )
    e4 = record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="governance-closeout",
        sequence=4,
        parent_digest=event_digest(e3),
        repository=str(workspace),
    )
    e5 = record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="governance-review",
        verdict="APPROVED",
        sequence=5,
        parent_digest=event_digest(e4),
        repository=str(workspace),
    )
    record_legacy_event(
        project_id="proj",
        task_id="FIX-001",
        stage="push",
        sequence=6,
        parent_digest=event_digest(e5),
        repository=str(workspace),
    )
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — shipped\n\nStatus: Done\n\nBody.\n\n",
    )
    data = client.get("/dash/api/v1/tasks/FIX-001").json()["data"]
    legacy = data["legacy_workflow"]
    assert legacy["terminal"] is True
    assert legacy["current_stage"] == "push"
    assert legacy["next_stage"] is None
    assert len(legacy["events"]) == 6


def test_no_repository_write_in_board_module() -> None:
    """DR-023/DR-062: board/task-detail JSON is read-only, asserted by source scan."""
    import agentos_dashboard.api.board as module
    import agentos_dashboard.services.board as board_module
    import agentos_dashboard.services.legacy_workflow as legacy_workflow_module
    import agentos_dashboard.services.tasks as tasks_module

    for mod in (module, board_module, tasks_module, legacy_workflow_module):
        assert mod.__file__ is not None
        source = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "shutil.", "open(", "Path.write", "os.remove", "os.system"):
            assert forbidden not in source


def test_legacy_workflow_module_never_calls_the_engines_write_path() -> None:
    """DASH-005 remediation, requirement 1/7: the dashboard reads the Legacy engine's workflow
    event store (`load_history`/`derive_state`) but never appends to it -- it introduces no
    second workflow authority and no write path of its own."""
    import agentos_dashboard.services.legacy_workflow as legacy_workflow_module

    assert legacy_workflow_module.__file__ is not None
    source = Path(legacy_workflow_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("event_store.append(", "event_store.record_outcome("):
        assert forbidden not in source
