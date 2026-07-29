from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from ai_workflow_engine.config import load_config
from ai_workflow_engine.governance.models import RegistryState, TaskStatus
from ai_workflow_engine.governance.registry import (
    REGISTRY_STATE_TO_TASK_STATUS,
    classify_state,
    parse_registry,
)
from ai_workflow_engine.governance.validators import check_registries
from ai_workflow_engine.result import Status

AUTO_REGISTRY = """\
# AgentOS Workflow Automation — Stage Registry

## 4. Registry

Report paths: `docs/reports/workflow-automation/AUTO-0XX-completion-report.md`.

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| AUTO-001 | Architecture | Session | COMPLETE | `governance/auto-001` | `AUTO-001.md` |
| AUTO-002 | Orchestrator | Session | IN_PROGRESS | `feature/auto-002` | `AUTO-002.md` |
| AUTO-003 | Skills | Session | NOT_STARTED | `feature/auto-003` | `AUTO-003.md` |

## 5. Authorization Log (append-only)

| Date | Stage | Authorization record | Recorded by |
|---|---|---|---|
| 2026-07-23 | AUTO-001 | Human Owner: "I authorize AUTO-001." | Session |
"""


def _write_registry_config(
    config_factory: Callable[[Path], Path], repository: Path, registries: list[str]
) -> Path:
    """Reuse the shared `config_factory` yaml, adding `governance.registries`."""
    path = config_factory(repository)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["governance"]["registries"] = registries
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _write_queue(repository: Path, rows: list[tuple[str, str]]) -> None:
    table = "| Task | Status |\n|---|---|\n" + "".join(
        f"| {task_id} | {status} |\n" for task_id, status in rows
    )
    (repository / "docs/TASK_QUEUE.md").write_text(table + "Version: 1.0.0\n", encoding="utf-8")


# --- parse_registry: structural extraction -------------------------------------------------


def test_parse_registry_extracts_stage_and_state_ignoring_auth_log() -> None:
    parse = parse_registry(AUTO_REGISTRY, "reg.md")
    assert parse.table_found is True
    assert [(row.stage_id, row.raw_state) for row in parse.rows] == [
        ("AUTO-001", "COMPLETE"),
        ("AUTO-002", "IN_PROGRESS"),
        ("AUTO-003", "NOT_STARTED"),
    ]


def test_parse_registry_reports_line_numbers() -> None:
    parse = parse_registry(AUTO_REGISTRY, "reg.md")
    # The first data row is line 9 of the fixture (1-based).
    assert parse.rows[0].line == 9


def test_parse_registry_missing_section_returns_not_found() -> None:
    parse = parse_registry("# Title\n\nNo registry table here.\n", "reg.md")
    assert parse.table_found is False
    assert parse.rows == []


def test_parse_registry_tolerates_reordered_columns_and_markup() -> None:
    text = """\
## Registry

| State | Stage | Notes |
|---|---|---|
| **COMPLETE** | `AUTO-009` | done |
"""
    parse = parse_registry(text, "reg.md")
    assert [(row.stage_id, row.raw_state) for row in parse.rows] == [("AUTO-009", "COMPLETE")]


def test_parse_registry_stops_at_next_heading() -> None:
    text = """\
## 3. Registry

| Stage | State |
|---|---|
| DASH-001 | COMPLETE |

## 4. Authorization Log

| Stage | State |
|---|---|
| DASH-999 | BOGUS |
"""
    parse = parse_registry(text, "reg.md")
    assert [row.stage_id for row in parse.rows] == ["DASH-001"]


def test_parse_registry_ignores_rows_without_a_stage_id() -> None:
    text = """\
## Registry

| Stage | State |
|---|---|
| (none) | COMPLETE |
| AUTO-001 | COMPLETE |
"""
    parse = parse_registry(text, "reg.md")
    assert [row.stage_id for row in parse.rows] == ["AUTO-001"]


# --- classify_state and the documented mapping ---------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("COMPLETE", RegistryState.COMPLETE),
        ("  in_progress  ", RegistryState.IN_PROGRESS),
        ("BlOcKeD", RegistryState.BLOCKED),
        ("nonsense", None),
        ("", None),
    ],
)
def test_classify_state(raw: str, expected: RegistryState | None) -> None:
    assert classify_state(raw) == expected


def test_mapping_covers_every_state() -> None:
    assert set(REGISTRY_STATE_TO_TASK_STATUS) == set(RegistryState)


@pytest.mark.parametrize(
    ("state", "status"),
    [
        (RegistryState.NOT_STARTED, TaskStatus.PLANNED),
        (RegistryState.PROPOSED, TaskStatus.PLANNED),
        (RegistryState.AUTHORIZED, TaskStatus.CURRENT),
        (RegistryState.BLOCKED, TaskStatus.CURRENT),
        (RegistryState.APPROVAL, TaskStatus.CURRENT),
        (RegistryState.COMPLETE, TaskStatus.DONE),
        (RegistryState.SUPERSEDED, TaskStatus.DONE),
    ],
)
def test_mapping_values(state: RegistryState, status: TaskStatus) -> None:
    assert REGISTRY_STATE_TO_TASK_STATUS[state] == status


# --- check_registries ----------------------------------------------------------------------


def test_no_registries_configured_passes(
    repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    result = check_registries(load_config(config_factory(repository)))
    assert result.status == Status.PASS
    assert result.summary == "No stage registries configured"


def test_consistent_registry_passes(
    repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    (repository / "docs/STAGE_REGISTRY.md").write_text(AUTO_REGISTRY, encoding="utf-8")
    _write_queue(
        repository,
        [("AUTO-001", "Done"), ("AUTO-002", "Current"), ("AUTO-003", "Planned")],
    )
    config = load_config(
        _write_registry_config(config_factory, repository, ["docs/STAGE_REGISTRY.md"])
    )
    result = check_registries(config)
    assert result.status == Status.PASS
    assert result.evidence["registries"]["docs/STAGE_REGISTRY.md"]["stages"] == 3


def test_state_mismatch_is_flagged(
    repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    (repository / "docs/STAGE_REGISTRY.md").write_text(AUTO_REGISTRY, encoding="utf-8")
    # AUTO-002 is IN_PROGRESS in the registry (≈ Current) but Done in the queue.
    _write_queue(
        repository,
        [("AUTO-001", "Done"), ("AUTO-002", "Done"), ("AUTO-003", "Planned")],
    )
    config = load_config(
        _write_registry_config(config_factory, repository, ["docs/STAGE_REGISTRY.md"])
    )
    result = check_registries(config)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert codes == {"registry_state_mismatch"}
    assert "AUTO-002" in result.findings[0].message


def test_stage_missing_from_queue_is_flagged(
    repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    (repository / "docs/STAGE_REGISTRY.md").write_text(AUTO_REGISTRY, encoding="utf-8")
    _write_queue(repository, [("AUTO-001", "Done"), ("AUTO-002", "Current")])  # AUTO-003 absent
    config = load_config(
        _write_registry_config(config_factory, repository, ["docs/STAGE_REGISTRY.md"])
    )
    result = check_registries(config)
    assert result.status == Status.FAIL
    assert {finding.code for finding in result.findings} == {"registry_stage_missing_from_queue"}


def test_unknown_state_is_flagged(repository: Path, config_factory: Callable[[Path], Path]) -> None:
    registry = AUTO_REGISTRY.replace("NOT_STARTED", "MAYBE")
    (repository / "docs/STAGE_REGISTRY.md").write_text(registry, encoding="utf-8")
    _write_queue(
        repository,
        [("AUTO-001", "Done"), ("AUTO-002", "Current"), ("AUTO-003", "Planned")],
    )
    config = load_config(
        _write_registry_config(config_factory, repository, ["docs/STAGE_REGISTRY.md"])
    )
    result = check_registries(config)
    assert result.status == Status.FAIL
    assert {finding.code for finding in result.findings} == {"registry_unknown_state"}


def test_missing_registry_table_is_flagged(
    repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    (repository / "docs/STAGE_REGISTRY.md").write_text("# Title\n\nNo table.\n", encoding="utf-8")
    config = load_config(
        _write_registry_config(config_factory, repository, ["docs/STAGE_REGISTRY.md"])
    )
    result = check_registries(config)
    assert result.status == Status.FAIL
    assert {finding.code for finding in result.findings} == {"registry_table_missing"}


def test_multiple_registries_are_all_checked(
    repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    (repository / "docs/AUTO.md").write_text(AUTO_REGISTRY, encoding="utf-8")
    dash = """\
## 3. Registry

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| DASH-001 | Planning | Session | COMPLETE | `governance/dash-001` | `p.md` |
"""
    (repository / "docs/DASH.md").write_text(dash, encoding="utf-8")
    # DASH-001 is COMPLETE (≈ Done) in the registry but Planned in the queue → one mismatch.
    _write_queue(
        repository,
        [
            ("AUTO-001", "Done"),
            ("AUTO-002", "Current"),
            ("AUTO-003", "Planned"),
            ("DASH-001", "Planned"),
        ],
    )
    config = load_config(
        _write_registry_config(config_factory, repository, ["docs/AUTO.md", "docs/DASH.md"])
    )
    result = check_registries(config)
    assert result.status == Status.FAIL
    assert [finding.path for finding in result.findings] == ["docs/DASH.md"]
    assert result.evidence["registries"]["docs/AUTO.md"]["stages"] == 3
