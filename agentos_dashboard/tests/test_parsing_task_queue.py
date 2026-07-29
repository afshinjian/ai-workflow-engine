"""TC-01/TC-02 — `parsing.task_queue`, exercised against `docs/TASK_QUEUE.md`-shaped headings
and the mirrors' Markdown-table shape."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.parsing.models import Confidence, TaskStatus
from agentos_dashboard.parsing.task_queue import parse_task_records

FIXTURES = Path(__file__).parent / "fixtures" / "malformed"

HEADING_QUEUE = """\
# Task Queue

## FAKE-001 — First task

Status: Current

Some scope prose.

## FAKE-002 — Second task

Status: Done

## FAKE-001 — Duplicate, must be ignored (first occurrence wins)

Status: Planned
"""

TABLE_MIRROR = """\
# Remaining Work

| Task | Title | Status |
|---|---|---|
| FAKE-003 | Third task | Current |
| FAKE-004 | Fourth task (blocked on OD-D9) | Planned |
"""


def test_heading_sections_parse_status_and_detail_text() -> None:
    parsed = parse_task_records(HEADING_QUEUE, "docs/TASK_QUEUE.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    by_id = {record.task_id: record for record in parsed.value}
    assert by_id["FAKE-001"].status is TaskStatus.CURRENT
    assert by_id["FAKE-001"].line == 3
    assert "Some scope prose." in by_id["FAKE-001"].detail_text
    assert by_id["FAKE-002"].status is TaskStatus.DONE


def test_first_occurrence_of_a_duplicate_id_wins() -> None:
    parsed = parse_task_records(HEADING_QUEUE, "docs/TASK_QUEUE.md")
    assert parsed.value is not None
    ids = [record.task_id for record in parsed.value]
    assert ids.count("FAKE-001") == 1
    assert next(r for r in parsed.value if r.task_id == "FAKE-001").status is TaskStatus.CURRENT


def test_table_row_shape_parses_the_same_two_facts() -> None:
    parsed = parse_task_records(TABLE_MIRROR, "docs/remaining_tasks.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    by_id = {record.task_id: record for record in parsed.value}
    assert by_id["FAKE-003"].status is TaskStatus.CURRENT
    assert by_id["FAKE-004"].status is TaskStatus.PLANNED


def test_heading_without_a_status_field_is_skipped_and_degrades_confidence() -> None:
    text = (FIXTURES / "task_queue_missing_status.md").read_text(encoding="utf-8")
    parsed = parse_task_records(text, "fixture")
    assert parsed.confidence is Confidence.LOW
    assert parsed.value is not None
    ids = {record.task_id for record in parsed.value}
    assert ids == {"FAKE-002"}
    assert any("skipped" in note for note in parsed.notes)


def test_document_with_no_task_records_degrades_to_raw_text() -> None:
    text = (FIXTURES / "task_queue_no_records.md").read_text(encoding="utf-8")
    parsed = parse_task_records(text, "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None
    assert parsed.raw_text == text


def test_real_task_queue_parses_dash_003_as_current() -> None:
    real_path = Path(__file__).resolve().parents[2] / "docs" / "TASK_QUEUE.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_task_records(text, "docs/TASK_QUEUE.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    by_id = {record.task_id: record for record in parsed.value}
    assert by_id["DASH-003"].status is TaskStatus.CURRENT
    current_ids = [tid for tid, record in by_id.items() if record.status is TaskStatus.CURRENT]
    assert current_ids == ["DASH-003"]
