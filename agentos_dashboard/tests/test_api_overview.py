"""`api.overview.build_overview` — DR-010..013's aggregate."""

from __future__ import annotations

import json
from pathlib import Path

from agentos_dashboard.api.overview import (
    NO_CURRENT_TASK_MESSAGE,
    build_overview,
    overview_to_json,
)
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.tests.conftest import write


def _populate_governed_fixture(workspace: Path) -> None:
    write(
        workspace,
        "docs/PROJECT_STATE.md",
        "Current Version: 3.2.1\n\n"
        "## Summary\n\nA fixture project.\n\n"
        "## Blockers\n\nnone recorded\n",
    )
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Current\n\nDo the thing carefully.\n\n"
        "## FIX-002 — later\n\nStatus: Planned\n\n"
        "## FIX-000 — earlier\n\nStatus: Done\n\n",
    )
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
        "    status: blocked\n"
        "    prerequisites: []\n"
        "    blockers:\n"
        "      - summary: waiting on a fixture decision\n"
        "    evidence: []\n",
    )


def test_healthy_empty_state_with_no_governance_documents(root: RepositoryRoot) -> None:
    overview = build_overview(build_snapshot(root))
    assert overview.current_task_id is None
    assert overview.current_task_summary == NO_CURRENT_TASK_MESSAGE
    assert overview.task_counts.current == 0
    assert overview.blockers == ()
    assert overview.git is None
    assert overview.version is None


def test_current_task_and_counts_are_derived_from_the_queue(
    workspace: Path, root: RepositoryRoot
) -> None:
    _populate_governed_fixture(workspace)
    overview = build_overview(build_snapshot(root))
    assert overview.current_task_id == "FIX-001"
    assert "do the thing" in overview.current_task_summary.lower()
    assert overview.task_counts.current == 1
    assert overview.task_counts.planned == 1
    assert overview.task_counts.done == 1


def test_version_and_summary_come_from_project_state(workspace: Path, root: RepositoryRoot) -> None:
    _populate_governed_fixture(workspace)
    overview = build_overview(build_snapshot(root))
    assert overview.version == "3.2.1"
    assert overview.summary == "A fixture project."


def test_orchestration_blockers_are_aggregated_across_stages(
    workspace: Path, root: RepositoryRoot
) -> None:
    _populate_governed_fixture(workspace)
    overview = build_overview(build_snapshot(root))
    assert overview.orch_blockers == ("waiting on a fixture decision",)


def test_git_overview_is_none_outside_a_git_repository(root: RepositoryRoot) -> None:
    overview = build_overview(build_snapshot(root))
    assert overview.git is None


def test_git_overview_reflects_a_real_repository(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    overview = build_overview(build_snapshot(root))
    assert overview.git is not None
    assert overview.git.branch == "main"
    assert overview.git.clean is True
    assert overview.git.head is not None


def test_overview_to_json_round_trips_through_json_dumps(
    workspace: Path, root: RepositoryRoot
) -> None:
    _populate_governed_fixture(workspace)
    overview = build_overview(build_snapshot(root))
    payload = overview_to_json(overview)
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["current_task_id"] == "FIX-001"
    assert decoded["task_counts"] == {"current": 1, "planned": 1, "done": 1}
    assert decoded["orch_blockers"] == ["waiting on a fixture decision"]
