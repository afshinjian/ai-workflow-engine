"""Tolerant parser for `docs/TASK_QUEUE.md` task sections and the mirror documents
`docs/current_task.md`/`docs/remaining_tasks.md` (`SOURCE_OF_TRUTH.md` TR-03).

Structurally mirrors `ai_workflow_engine.governance.parser.parse_tasks`: `## <ID> — …` headings
followed by a `Status: Current|Planned|Done` field, plus Markdown table rows carrying the same
two facts (the mirrors' summary tables) — first live occurrence wins on a duplicate id, same as
the engine. This module is independent code, not an import of the engine's parser
(`DASH-003.md` Stage-Specific Notes), but the extraction rules are deliberately identical,
including the known multi-hyphen id quirk documented in `_common.py`.

Each recognized task section additionally carries its raw prose body as `detail_text`
(`DATA_MODEL.md` EN-06's scope/acceptance-criteria/rollback prose, as recorded — not
sub-parsed into separate typed fields, since the queue's prose has no uniform per-field
structure to parse against; a later stage that needs finer-grained extraction makes that an
explicit decision).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_dashboard.parsing._common import TASK_ID, plain
from agentos_dashboard.parsing.models import Confidence, ParsedDocument, TaskStatus

__all__ = [
    "TaskRecord",
    "parse_task_records",
]

_TASK_HEADING = re.compile(r"^#{2,6}\s+.*?\b([A-Za-z]+-\d+)\b", re.MULTILINE)
_STATUS_FIELD = re.compile(
    r"(?:\*\*)?Status:?(?:\*\*)?\s*(?:\*\*|`)?(Current|Done|Planned)\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class TaskRecord:
    """EN-05/EN-06: one task's status plus its recorded prose, with file+line provenance."""

    task_id: str
    status: TaskStatus
    source: str
    line: int
    detail_text: str
    detail_line: int


def _status(value: str) -> TaskStatus | None:
    try:
        return TaskStatus(value.strip().title())
    except ValueError:
        return None


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _heading_records(text: str, source: str) -> tuple[list[tuple[int, TaskRecord]], int]:
    occurrences: list[tuple[int, TaskRecord]] = []
    headings = list(_TASK_HEADING.finditer(text))
    skipped = 0
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end() : end]
        status_match = _STATUS_FIELD.search(section)
        status = _status(status_match.group(1)) if status_match else None
        if status is None:
            skipped += 1
            continue
        line_number = _line_number(text, heading.start())
        occurrences.append(
            (
                heading.start(),
                TaskRecord(
                    task_id=heading.group(1).upper(),
                    status=status,
                    source=source,
                    line=line_number,
                    detail_text=section.strip(),
                    detail_line=line_number,
                ),
            )
        )
    return occurrences, skipped


def _table_row_records(text: str, source: str) -> tuple[list[tuple[int, TaskRecord]], int]:
    occurrences: list[tuple[int, TaskRecord]] = []
    skipped = 0
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        if not line.lstrip().startswith("|"):
            offset += len(line)
            continue
        cells = [plain(cell) for cell in line.strip().strip("|").split("|")]
        status = next((parsed for cell in cells if (parsed := _status(cell)) is not None), None)
        match = next((TASK_ID.search(cell) for cell in cells if TASK_ID.search(cell)), None)
        if status is None or match is None:
            if any(TASK_ID.search(cell) for cell in cells):
                skipped += 1
            offset += len(line)
            continue
        occurrences.append(
            (
                offset,
                TaskRecord(
                    task_id=match.group(1).upper(),
                    status=status,
                    source=source,
                    line=line_number,
                    detail_text=line.strip(),
                    detail_line=line_number,
                ),
            )
        )
        offset += len(line)
    return occurrences, skipped


def parse_task_records(text: str, source: str) -> ParsedDocument[tuple[TaskRecord, ...]]:
    heading_occurrences, skipped_headings = _heading_records(text, source)
    row_occurrences, skipped_rows = _table_row_records(text, source)
    occurrences = heading_occurrences + row_occurrences

    records: list[TaskRecord] = []
    seen: set[str] = set()
    for _, record in sorted(occurrences, key=lambda item: item[0]):
        if record.task_id in seen:
            continue
        seen.add(record.task_id)
        records.append(record)

    if not records:
        return ParsedDocument(
            source=source,
            confidence=Confidence.NONE,
            value=None,
            raw_text=text,
            notes=("no recognizable task records found",),
        )

    notes: list[str] = []
    if skipped_headings:
        notes.append(f"{skipped_headings} heading(s) skipped: no recognizable Status field")
    if skipped_rows:
        notes.append(f"{skipped_rows} table row(s) skipped: no recognizable Status cell")

    confidence = Confidence.HIGH if not notes else Confidence.LOW
    return ParsedDocument(
        source=source,
        confidence=confidence,
        value=tuple(records),
        raw_text=text,
        notes=tuple(notes),
    )
