"""Conservative parsers for explicit Markdown table facts."""

import re

from ai_workflow_engine.governance.models import TaskRecord, TaskStatus

TASK_ID = re.compile(r"\b([A-Za-z]+-\d+)\b")
MARKUP = re.compile(r"[*_`~]")
TASK_HEADING = re.compile(r"^#{2,6}\s+.*?\b([A-Za-z]+-\d+)\b", re.MULTILINE)
STATUS_FIELD = re.compile(
    r"(?:\*\*)?Status:?(?:\*\*)?\s*(?:\*\*|`)?(Current|Done|Planned)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _plain(value: str) -> str:
    return MARKUP.sub("", value).strip()


def _parse_task_status(value: str) -> TaskStatus | None:
    normalized_value = value.strip().title()
    try:
        return TaskStatus(normalized_value)
    except ValueError:
        return None


def parse_tasks(text: str, source: str) -> list[TaskRecord]:
    """Parse task sections/table rows; first live occurrence wins."""
    occurrences: list[tuple[int, TaskRecord]] = []
    headings = list(TASK_HEADING.finditer(text))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end() : end]
        status_match = STATUS_FIELD.search(section)
        if not status_match:
            continue
        status = _parse_task_status(status_match.group(1))
        if status is None:
            continue
        task_id = heading.group(1).upper()
        line_number = text.count("\n", 0, heading.start()) + 1
        occurrences.append(
            (
                heading.start(),
                TaskRecord(
                    task_id=task_id,
                    status=status,
                    source=source,
                    line=line_number,
                ),
            )
        )
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        if not line.lstrip().startswith("|"):
            offset += len(line)
            continue
        cells = [_plain(cell) for cell in line.strip().strip("|").split("|")]
        status = next(
            (
                parsed_status
                for cell in cells
                if (parsed_status := _parse_task_status(cell)) is not None
            ),
            None,
        )
        match = next((TASK_ID.search(cell) for cell in cells if TASK_ID.search(cell)), None)
        if not status or not match:
            offset += len(line)
            continue
        task_id = match.group(1).upper()
        occurrences.append(
            (
                offset,
                TaskRecord(task_id=task_id, status=status, source=source, line=line_number),
            )
        )
        offset += len(line)

    records: list[TaskRecord] = []
    seen: set[str] = set()
    for _, record in sorted(occurrences, key=lambda occurrence: occurrence[0]):
        if record.task_id in seen:
            continue
        seen.add(record.task_id)
        records.append(record)
    return records


def extract_fact(text: str, pattern: str, group: int | str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    return " ".join(match.group(group).strip().split())
