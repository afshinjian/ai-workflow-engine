from pathlib import Path

import pytest

from ai_workflow_engine.config import load_config
from ai_workflow_engine.governance.models import TaskStatus
from ai_workflow_engine.governance.parser import parse_tasks
from ai_workflow_engine.governance.validators import check_governance, check_task_state
from ai_workflow_engine.result import Status


@pytest.mark.parametrize(
    ("statuses", "expected", "passes"),
    [([], 0, True), (["Current"], 1, True), (["Current", "Current"], 2, False)],
)
def test_zero_one_and_multiple_current_tasks(
    repository: Path, config_factory: object, statuses: list[str], expected: int, passes: bool
) -> None:
    rows = "\n".join(f"| T-{index} | {status} |" for index, status in enumerate(statuses, 1))
    content = f"| Task | Status |\n|---|---|\n{rows}\nVersion: 1.0.0\n"
    for name in [
        "TASK_QUEUE.md",
        "PROJECT_STATE.md",
        "current_task.md",
        "remain_task.md",
        "CHATGPT_CONTEXT.md",
    ]:
        (repository / "docs" / name).write_text(content)
    result = check_task_state(load_config(config_factory(repository)))  # type: ignore[operator]
    assert result.evidence["current_count"] == expected
    assert (result.status == Status.PASS) is passes


def test_parser_uses_first_task_occurrence() -> None:
    records = parse_tasks("| T-9 | Current |\n| T-9 | Done |", "x.md")
    assert len(records) == 1
    assert records[0].status == "Current"


def test_parser_uses_document_order_across_tables_and_headings() -> None:
    text = """\
| T-9 | Current |

### T-9 — Later duplicate
- **Status:** Done
"""
    records = parse_tasks(text, "queue.md")
    assert [(record.task_id, record.status, record.line) for record in records] == [
        ("T-9", TaskStatus.CURRENT, 1)
    ]


def test_parser_constructs_task_status_enum_on_python_311() -> None:
    records = parse_tasks("| T-31 | Planned |", "queue.md")
    assert records[0].status is TaskStatus.PLANNED


def test_parser_normalizes_status_and_ignores_unknown_table_cells() -> None:
    text = """\
| Task | Status |
|---|---|
| T-7 |  cUrReNt  |
| T-8 | DONE |
| T-9 | planned |
| T-10 | Unknown |
| T-11 | T-12 |
"""
    records = parse_tasks(text, "queue.md")
    assert [(record.task_id, record.status) for record in records] == [
        ("T-7", "Current"),
        ("T-8", "Done"),
        ("T-9", "Planned"),
    ]


def test_parser_reads_task_heading_metadata() -> None:
    text = "### T-10 — Work\n- **Phase:** 1 · **Status:** Planned\n"
    records = parse_tasks(text, "queue.md")
    assert [(record.task_id, record.status) for record in records] == [("T-10", "Planned")]


def test_governance_version_mismatch(repository: Path, config_factory: object) -> None:
    context = repository / "docs/CHATGPT_CONTEXT.md"
    context.write_text(context.read_text().replace("1.0.0", "2.0.0"))
    result = check_governance(load_config(config_factory(repository)))  # type: ignore[operator]
    assert result.status == Status.FAIL
    assert "governance_fact_mismatch" in {finding.code for finding in result.findings}


def test_missing_current_task_in_mirror_is_inconsistent(
    repository: Path, config_factory: object
) -> None:
    queue = repository / "docs/TASK_QUEUE.md"
    queue.write_text("### T-1 — Work\n- **Status:** Current\nVersion: 1.0.0\n")
    mirror = repository / "docs/current_task.md"
    mirror.write_text("No task has been promoted.\nVersion: 1.0.0\n")
    result = check_task_state(load_config(config_factory(repository)))  # type: ignore[operator]
    assert result.status == Status.FAIL
    assert "current_task_mismatch" in {finding.code for finding in result.findings}
