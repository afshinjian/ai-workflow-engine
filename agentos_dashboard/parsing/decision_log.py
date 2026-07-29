"""Tolerant parser for `docs/DECISION_LOG.md` dated entries (`SOURCE_OF_TRUTH.md` Authority
Table: "Decisions").

Only this document's own `## <YYYY-MM-DD>[ —-]<heading>` entries are in scope — the subordinate
program `DECISIONS.md` files (`DD-##` headings, no date) are a separate, undated format the
`DASH-003.md` contract does not name, and are left to a later stage's decision browser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from agentos_dashboard.parsing.models import Confidence, ParsedDocument

__all__ = [
    "DecisionEntry",
    "parse_decision_log",
]

# Both a hyphen and an em dash separate the date from the heading in this repository's history
# (`docs/DECISION_LOG.md` uses "—"; tolerated either way, matching this package's conservative-
# parsing principle of degrading gracefully rather than rejecting a minor formatting variant).
_DATED_HEADING = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*[—-]\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class DecisionEntry:
    """EN-22: one dated decision-log entry."""

    date: str
    heading: str
    body: str
    source: str
    line: int


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def parse_decision_log(text: str, source: str) -> ParsedDocument[tuple[DecisionEntry, ...]]:
    all_headings = list(_DATED_HEADING.finditer(text))
    headings = [heading for heading in all_headings if _valid_date(heading.group(1))]
    skipped = len(all_headings) - len(headings)

    if not headings:
        notes: tuple[str, ...] = (
            ("no dated entries found",)
            if skipped == 0
            else (f"{skipped} heading(s) skipped: unparsable date",)
        )
        return ParsedDocument(
            source=source, confidence=Confidence.NONE, value=None, raw_text=text, notes=notes
        )

    entries: list[DecisionEntry] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end() : end].strip()
        entries.append(
            DecisionEntry(
                date=heading.group(1),
                heading=heading.group(2).strip(),
                body=body,
                source=source,
                line=_line_number(text, heading.start()),
            )
        )

    notes = () if skipped == 0 else (f"{skipped} heading(s) skipped: unparsable date",)
    confidence = Confidence.HIGH if not notes else Confidence.LOW
    return ParsedDocument(
        source=source,
        confidence=confidence,
        value=tuple(entries),
        raw_text=text,
        notes=notes,
    )
