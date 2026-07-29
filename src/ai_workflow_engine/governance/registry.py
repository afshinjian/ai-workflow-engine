"""Tolerant parsing of a program's stage-registry Registry table, and the documented
state→task-status mapping both program registries share.

This module is purely structural and policy-lite: `parse_registry` extracts each Registry-table
row's stage id and its verbatim State cell (matching this project's conservative-parsing
principle, `docs/DECISION_LOG.md` "Milestone 1" entry), while `classify_state` and
`REGISTRY_STATE_TO_TASK_STATUS` encode the single documented mapping that
`docs/workflow-automation/STAGE_REGISTRY.md` §2 and `docs/agentos-dashboard/STAGE_REGISTRY.md` §1
both state identically. The mapping lives here, once, rather than being hard-coded per program.
"""

import re

from ai_workflow_engine.governance.models import (
    RegistryParse,
    RegistryRow,
    RegistryState,
    TaskStatus,
)
from ai_workflow_engine.governance.parser import TASK_ID

# Surrounding Markdown emphasis/code markers stripped from a cell. Unlike the task parser's
# `MARKUP`, the underscore is deliberately preserved: it is significant inside state names such as
# `IN_PROGRESS` and `NOT_STARTED`, not emphasis to be removed.
_MARKUP = re.compile(r"[*`~]")

# The `## N. Registry` section heading (the level-1 `# ... Stage Registry` document title is not
# matched: it is a different level and its text is "Stage Registry", not "Registry"). The section
# number is optional and tolerated so a registry that drops the numbering still parses.
REGISTRY_HEADING = re.compile(r"^#{2,6}\s+(?:\d+\.\s*)?Registry\s*$", re.MULTILINE)
_ANY_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)
_SEPARATOR_CELL = re.compile(r":?-+:?")

# The documented state→task-status mapping (identical across both program registries). The three
# `docs/TASK_QUEUE.md` statuses are the only targets; `BLOCKED` is deliberately `Current`, and
# `COMPLETE`/`SUPERSEDED` both map to `Done` (their distinct meanings are a task-prose concern,
# not a machine-checkable status difference).
REGISTRY_STATE_TO_TASK_STATUS: dict[RegistryState, TaskStatus] = {
    RegistryState.NOT_STARTED: TaskStatus.PLANNED,
    RegistryState.PROPOSED: TaskStatus.PLANNED,
    RegistryState.AUTHORIZED: TaskStatus.CURRENT,
    RegistryState.IN_PROGRESS: TaskStatus.CURRENT,
    RegistryState.SELF_REVIEW: TaskStatus.CURRENT,
    RegistryState.REVIEW: TaskStatus.CURRENT,
    RegistryState.APPROVAL: TaskStatus.CURRENT,
    RegistryState.BLOCKED: TaskStatus.CURRENT,
    RegistryState.COMPLETE: TaskStatus.DONE,
    RegistryState.SUPERSEDED: TaskStatus.DONE,
}


def classify_state(raw: str) -> RegistryState | None:
    """Recognize a verbatim State cell as a `RegistryState`, or `None` if it is not one."""
    try:
        return RegistryState(raw.strip().upper())
    except ValueError:
        return None


def _plain(value: str) -> str:
    return _MARKUP.sub("", value).strip()


def _table_cells(line: str) -> list[str]:
    return [_plain(cell) for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    non_empty = [cell for cell in cells if cell]
    return bool(non_empty) and all(_SEPARATOR_CELL.fullmatch(cell) for cell in non_empty)


def parse_registry(text: str, source: str) -> RegistryParse:
    """Parse the first `Registry` section's table into structural stage/state rows.

    Only the section under the `## N. Registry` heading is examined, so the append-only
    Authorization Log table (which also has a `Stage` column but no `State` column) is never
    mistaken for the Registry table. Column positions are located by their header labels rather
    than fixed indices, so a future column reorder does not silently misread the table.
    """
    heading = REGISTRY_HEADING.search(text)
    if heading is None:
        return RegistryParse(source=source, table_found=False, rows=[])
    body_start = heading.end()
    following = _ANY_HEADING.search(text, body_start)
    body_end = following.start() if following else len(text)

    rows: list[RegistryRow] = []
    table_found = False
    stage_index: int | None = None
    state_index: int | None = None
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        start = offset
        offset += len(line)
        if start < body_start or start >= body_end:
            continue
        if not line.lstrip().startswith("|"):
            if stage_index is not None:
                break  # The contiguous Registry table has ended.
            continue
        cells = _table_cells(line)
        if stage_index is None:
            lowered = [cell.lower() for cell in cells]
            if "stage" in lowered and "state" in lowered:
                stage_index = lowered.index("stage")
                state_index = lowered.index("state")
                table_found = True
            continue
        if _is_separator_row(cells):
            continue
        assert state_index is not None  # set together with stage_index
        if stage_index >= len(cells) or state_index >= len(cells):
            continue
        match = TASK_ID.search(cells[stage_index])
        if match is None:
            continue
        rows.append(
            RegistryRow(
                stage_id=match.group(1).upper(),
                raw_state=cells[state_index],
                source=source,
                line=line_number,
            )
        )
    return RegistryParse(source=source, table_found=table_found, rows=rows)
