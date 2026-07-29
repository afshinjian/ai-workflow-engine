"""Tolerant parser for `docs/PROJECT_STATE.md` (`SOURCE_OF_TRUTH.md` Authority Table: "Live
project state" / "Version fact").

Extracts the `Current Version:` fact line (cross-checked against `pyproject.toml` by
`workflowctl check-governance`; the dashboard mirrors that check in
`agentos_dashboard.services.consistency`), the `## Summary` section body, the `## Blockers`
section body, and — narrowly — the task ids named at the start of each top-level `## Completed`
bullet (`- <ID> (...): ...`). That last extraction is intentionally bounded to `## Completed`
and to bullet-start position only: `## In progress`/`## Planned` are free-form prose in this
document (see the real file), and a task id appearing mid-sentence there is not a structured
claim about that task's status, so scanning for it would manufacture false contradictions against
`docs/TASK_QUEUE.md`. `## Completed`'s bullets are structured enough (one bullet per closed
task, id first) to support the "PROJECT_STATE-vs-TASK_QUEUE contradiction" consistency rule
`DASH-003.md`'s Acceptance section asks for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_dashboard.parsing._common import TASK_ID
from agentos_dashboard.parsing.models import Confidence, ParsedDocument

__all__ = [
    "BlockerEntry",
    "ProjectStateView",
    "SectionTaskRef",
    "parse_project_state",
]

_VERSION_LINE = re.compile(r"^Current Version:\s*(\S.*?)\s*$", re.MULTILINE)
_SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_BULLET_LINE = re.compile(r"^-\s+(.*)$")

# The one section this module extracts structured task references from; see the module
# docstring for why `In progress`/`Planned` are excluded.
_COMPLETED_SECTION_NAME = "completed"


@dataclass(frozen=True)
class BlockerEntry:
    """One line of the `## Blockers` section body."""

    text: str
    line: int


@dataclass(frozen=True)
class SectionTaskRef:
    """A task id named at the start of a `## Completed` bullet, with its provenance."""

    section: str
    task_id: str
    line: int


@dataclass(frozen=True)
class ProjectStateView:
    version_fact: str | None
    version_fact_line: int | None
    summary: str | None
    summary_line: int | None
    blockers: tuple[BlockerEntry, ...]
    completed_task_refs: tuple[SectionTaskRef, ...]


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _section_body(text: str, heading_name: str) -> tuple[str, int] | None:
    """The body text of the first `## <heading_name>` section, and that heading's line number."""
    for match in _SECTION_HEADING.finditer(text):
        if match.group(1).strip().lower() != heading_name.lower():
            continue
        body_start = match.end()
        following = _SECTION_HEADING.search(text, body_start)
        body_end = following.start() if following else len(text)
        return text[body_start:body_end].strip("\n"), _line_number(text, match.start())
    return None


def _blockers(text: str, section_start_line: int, body: str) -> tuple[BlockerEntry, ...]:
    entries: list[BlockerEntry] = []
    for offset, line in enumerate(body.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        entries.append(BlockerEntry(text=stripped, line=section_start_line + 1 + offset))
    return tuple(entries)


def _completed_task_refs(text: str, body: str, body_line: int) -> tuple[SectionTaskRef, ...]:
    refs: list[SectionTaskRef] = []
    for offset, line in enumerate(body.splitlines()):
        bullet = _BULLET_LINE.match(line)
        if bullet is None:
            continue
        match = TASK_ID.search(bullet.group(1))
        if match is None:
            continue
        refs.append(
            SectionTaskRef(
                section="Completed",
                task_id=match.group(1).upper(),
                line=body_line + 1 + offset,
            )
        )
    return tuple(refs)


def parse_project_state(text: str, source: str) -> ParsedDocument[ProjectStateView]:
    version_match = _VERSION_LINE.search(text)
    version_fact = version_match.group(1) if version_match else None
    version_fact_line = _line_number(text, version_match.start()) if version_match else None

    summary = _section_body(text, "Summary")
    blockers_section = _section_body(text, "Blockers")
    completed_section = _section_body(text, _COMPLETED_SECTION_NAME)

    summary_text, summary_line = summary if summary else (None, None)
    blockers = _blockers(text, blockers_section[1], blockers_section[0]) if blockers_section else ()
    completed_refs = (
        _completed_task_refs(text, completed_section[0], completed_section[1])
        if completed_section
        else ()
    )

    missing: list[str] = []
    if version_fact is None:
        missing.append("no 'Current Version:' line found")
    if summary is None:
        missing.append("no '## Summary' section found")
    if blockers_section is None:
        missing.append("no '## Blockers' section found")

    if version_fact is None and summary is None and blockers_section is None:
        return ParsedDocument(
            source=source,
            confidence=Confidence.NONE,
            value=None,
            raw_text=text,
            notes=tuple(missing),
        )

    view = ProjectStateView(
        version_fact=version_fact,
        version_fact_line=version_fact_line,
        summary=summary_text,
        summary_line=summary_line,
        blockers=blockers,
        completed_task_refs=completed_refs,
    )
    confidence = Confidence.HIGH if not missing else Confidence.LOW
    return ParsedDocument(
        source=source, confidence=confidence, value=view, raw_text=text, notes=tuple(missing)
    )
