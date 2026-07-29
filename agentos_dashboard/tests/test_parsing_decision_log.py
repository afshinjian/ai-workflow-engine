"""TC-01/TC-02 — `parsing.decision_log`."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.parsing.decision_log import parse_decision_log
from agentos_dashboard.parsing.models import Confidence

FIXTURES = Path(__file__).parent / "fixtures" / "malformed"

WELL_FORMED = """\
# Decision Log

Preamble prose before the first dated entry, which must not be mistaken for one.

## 2026-07-29 — Second entry

Body of the second (newest) entry, mentioning commit `abc1234`.

## 2026-07-28 — First entry

Body of the first entry.
"""


def test_dated_entries_parse_in_document_order() -> None:
    parsed = parse_decision_log(WELL_FORMED, "docs/DECISION_LOG.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert [entry.date for entry in parsed.value] == ["2026-07-29", "2026-07-28"]
    assert parsed.value[0].heading == "Second entry"
    assert "abc1234" in parsed.value[0].body


def test_entry_line_provenance() -> None:
    parsed = parse_decision_log(WELL_FORMED, "docs/DECISION_LOG.md")
    assert parsed.value is not None
    assert parsed.value[0].line == 5


def test_undated_headings_are_not_entries() -> None:
    text = (FIXTURES / "decision_log_no_dates.md").read_text(encoding="utf-8")
    parsed = parse_decision_log(text, "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None


def test_a_lexically_date_shaped_but_impossible_date_is_skipped() -> None:
    text = (FIXTURES / "decision_log_invalid_date.md").read_text(encoding="utf-8")
    parsed = parse_decision_log(text, "fixture")
    assert parsed.confidence is Confidence.LOW
    assert parsed.value is not None
    assert [entry.date for entry in parsed.value] == ["2026-07-29"]
    assert any("skipped" in note for note in parsed.notes)


def test_real_decision_log_parses_at_high_confidence() -> None:
    real_path = Path(__file__).resolve().parents[2] / "docs" / "DECISION_LOG.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_decision_log(text, "docs/DECISION_LOG.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert len(parsed.value) > 5
