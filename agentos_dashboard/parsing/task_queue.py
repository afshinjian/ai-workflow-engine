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

Two refinements over a literal "zero records" reading (`REC-001`, corrected per the
`REC001-REV-001`/`REC001-REV-002` review round):

* A document containing zero recognized records is a *recognized legal empty collection* — not
  a parse failure — only when **all** of the following hold: the caller has opted in via
  `parse_task_records(..., recognize_empty_current=True)` (the Current-task mirror role only —
  `docs/TASK_QUEUE.md` and `docs/remaining_tasks.md` never opt in, so the same heading appearing
  there does not mean "this collection is empty"); the document's heading text is an *exact*
  single-line match, apart from Markdown whitespace normalization, of the established
  `docs/current_task.md` declaration (`## No task is currently active`, e.g.
  `docs/reports/workflow-automation/GOV-AUTO-10-completion-report.md`) — no prefixes, suffixes,
  qualifiers, pluralization errors, or multi-line variants accepted; and zero heading/table-row
  candidates were skipped as malformed. An empty declaration never overrides a diagnostic — a
  document that has the declaration *and* a genuinely malformed task-shaped heading or row still
  fails/degrades. Anything else with zero records is `Confidence.NONE`: legal emptiness must be
  explicitly and exactly declared, never inferred from an absence of structure.
* A `## <words containing an id>` heading only counts as a task-record candidate — and so only
  counts against confidence when it lacks a `Status:` field — when the *entire* heading has the
  shape `## <ID>` or `## <ID> — <Title>` (one optional Markdown wrapper around the id tolerated,
  e.g. `## **FAKE-001** — Real task`, consistent with what the authoritative engine parser
  (`ai_workflow_engine.governance.parser.parse_tasks`) would recognize as a real task heading):
  nothing but paired Markdown markers or the multi-hyphen id quirk's own glued prefix (e.g.
  `GOV-` in `GOV-AUTO-08`) may precede the id, and only the title separator or end-of-line may
  follow it. A narrative heading with a real word *before* the id (`## Closure record for
  FAKE-001 — 2026-08-08`) or a real word *after* it with no separator (`## AUTO-016 closure —
  2026-08-08`) is not a task record in either direction, and must not degrade — or masquerade
  as — a genuine one.
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
# The separator every genuine `## <ID> — <Title>` heading in this repository uses directly after
# the id, distinguishing a task-record heading from a narrative heading that merely mentions an id
# (`## AUTO-016 closure — 2026-08-08`), which has another word in between instead.
_TITLE_SEPARATOR = re.compile(r"\A[ \t]*(?:[\u2014\u2013]|--|-(?=[ \t])|:)")
# One paired Markdown wrapper directly around the id (`**FAKE-001**`, `` `FAKE-001` ``, or
# `~~FAKE-001~~`), stripped before evaluating what precedes/follows the id; never crosses into the
# next word. These are the wrappers the authoritative Core heading regex can locate around an id.
_MARKDOWN_WRAPPER = re.compile(r"\A(?:\*{1,3}|_{1,3}|`|~~)")
# The authoritative parser's known multi-hyphen quirk locates the final `<letters>-<digits>`
# portion of an id such as `GOV-AUTO-08`, leaving `GOV-` before the captured `AUTO-08`. Permit
# only that identifier-shaped prefix, never arbitrary glued punctuation such as
# `Related:FAKE-001` or `/FAKE-001`.
_MULTI_HYPHEN_PREFIX = re.compile(r"(?:[A-Za-z]+-)*")
# `docs/current_task.md`'s established convention for a legal, recognized zero-Current
# declaration (confirmed by `docs/reports/workflow-automation/GOV-AUTO-10-completion-report.md`).
# Deliberately an *exact* single-line match (`[ \t]` only, never `\s`, so it cannot cross lines):
# REC001-REV-001 found the prior `\s`-based, unanchored, pluralization-tolerant form accepted
# malformed/qualified/multi-line variants it must not.
_EMPTY_DECLARATION = re.compile(
    r"^##[ \t]+No[ \t]+task[ \t]+is[ \t]+currently[ \t]+active[ \t]*$",
    re.MULTILINE,
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


def _heading_prefix_wrapper(text: str, heading: re.Match[str]) -> str | None:
    """No real narrative word may precede the id within its heading line. Only Markdown wrapper
    markers, or an identifier-shaped prefix glued directly onto the id (the multi-hyphen id
    quirk's own prefix, e.g. `GOV-` in `GOV-AUTO-08` — `_common.py`), are tolerated. Return the
    opening wrapper so the suffix check can require its exact closing counterpart."""
    line_start = text.rfind("\n", 0, heading.start()) + 1
    prefix_match = re.match(r"#{2,6}[ \t]+", text[line_start:])
    if prefix_match is None:  # pragma: no cover - _TASK_HEADING already matched this shape
        return None
    content_start = line_start + prefix_match.end()
    before = text[content_start : heading.start(1)]
    wrapper_match = _MARKDOWN_WRAPPER.match(before)
    wrapper = wrapper_match.group(0) if wrapper_match else ""
    if wrapper:
        before = before[len(wrapper) :]
    if _MULTI_HYPHEN_PREFIX.fullmatch(before) is None:
        return None
    return wrapper


def _heading_suffix_ok(text: str, heading: re.Match[str], wrapper: str) -> bool:
    """Immediately after the id (requiring the exact closing Markdown wrapper when one opened),
    only the title separator or end-of-line may follow — otherwise a real word follows the id and
    this is a narrative heading, not a task record
    (`## AUTO-016 closure — 2026-08-08`)."""
    line_end = text.find("\n", heading.end())
    remainder = text[heading.end() : line_end if line_end != -1 else len(text)].strip()
    if wrapper:
        if not remainder.startswith(wrapper):
            return False
        remainder = remainder[len(wrapper) :].lstrip()
    if not remainder:
        return True
    return bool(_TITLE_SEPARATOR.match(remainder))


def _is_task_record_heading(text: str, heading: re.Match[str]) -> bool:
    """Whether `heading` has the full `## <ID>` or `## <ID> — <Title>` shape (one optional paired
    Markdown wrapper around the id tolerated) of a genuine task record, as opposed to a
    narrative heading that merely mentions an id in passing while saying something else in either
    direction (see module docstring)."""
    wrapper = _heading_prefix_wrapper(text, heading)
    return wrapper is not None and _heading_suffix_ok(text, heading, wrapper)


def _heading_records(text: str, source: str) -> tuple[list[tuple[int, TaskRecord]], int]:
    occurrences: list[tuple[int, TaskRecord]] = []
    headings = list(_TASK_HEADING.finditer(text))
    skipped = 0
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        if not _is_task_record_heading(text, heading):
            continue
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


def parse_task_records(
    text: str, source: str, *, recognize_empty_current: bool = False
) -> ParsedDocument[tuple[TaskRecord, ...]]:
    """`recognize_empty_current` opts in to recognizing a legal, recognized zero-Current
    declaration (module docstring) as a valid empty collection instead of a parse failure. Pass
    it only for the Current-task mirror role (`docs/current_task.md`) — never for
    `docs/TASK_QUEUE.md` or `docs/remaining_tasks.md`, where the same heading text would not mean
    "this entire collection is empty" (REC001-REV-001)."""
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

    notes: list[str] = []
    if skipped_headings:
        notes.append(f"{skipped_headings} heading(s) skipped: no recognizable Status field")
    if skipped_rows:
        notes.append(f"{skipped_rows} table row(s) skipped: no recognizable Status cell")

    if not records:
        # An empty declaration never overrides a diagnostic: it means "there are intentionally no
        # Current tasks", not "ignore malformed task-shaped content elsewhere in this document"
        # (REC001-REV-001). Only a document with *zero* skipped candidates and the exact
        # declaration heading is a trusted empty collection.
        if recognize_empty_current and not notes and _EMPTY_DECLARATION.search(text):
            return ParsedDocument(
                source=source,
                confidence=Confidence.HIGH,
                value=(),
                raw_text=text,
                notes=(),
            )
        if not notes:
            notes = ["no recognizable task records found"]
        return ParsedDocument(
            source=source,
            confidence=Confidence.NONE,
            value=None,
            raw_text=text,
            notes=tuple(notes),
        )

    confidence = Confidence.HIGH if not notes else Confidence.LOW
    return ParsedDocument(
        source=source,
        confidence=confidence,
        value=tuple(records),
        raw_text=text,
        notes=tuple(notes),
    )
