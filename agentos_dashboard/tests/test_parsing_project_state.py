"""TC-01/TC-02 — `parsing.project_state`."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.parsing.models import Confidence
from agentos_dashboard.parsing.project_state import parse_project_state

FIXTURES = Path(__file__).parent / "fixtures" / "malformed"

WELL_FORMED = """\
# Project State

Current Version: 1.2.3

## Summary

A one-paragraph summary of the project.

## Completed
- FAKE-001 (closed 2026-07-01): done.
- FAKE-002 (closed 2026-07-02): also done.
  continuation line, not a new bullet.

## Blockers

There is no active blocker.
"""


def test_well_formed_document_parses_at_high_confidence() -> None:
    parsed = parse_project_state(WELL_FORMED, "docs/PROJECT_STATE.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert parsed.value.version_fact == "1.2.3"
    assert parsed.value.version_fact_line == 3
    assert parsed.value.summary == "A one-paragraph summary of the project."
    assert len(parsed.value.blockers) == 1
    assert parsed.value.blockers[0].text == "There is no active blocker."


def test_completed_section_task_refs_carry_line_provenance() -> None:
    parsed = parse_project_state(WELL_FORMED, "docs/PROJECT_STATE.md")
    assert parsed.value is not None
    refs = parsed.value.completed_task_refs
    assert [ref.task_id for ref in refs] == ["FAKE-001", "FAKE-002"]
    assert all(ref.section == "Completed" for ref in refs)
    # Exactly one ref per bullet: the indented continuation line under FAKE-002 must not be
    # mistaken for a second bullet.
    assert len(refs) == 2
    assert refs[0].line == 10
    assert refs[1].line == 11


def test_prose_outside_a_completed_bullet_is_not_extracted() -> None:
    text = """\
Current Version: 1.0.0

## Summary

Mentions FAKE-999 in prose, not as a bullet.

## Completed
Not a bullet: FAKE-998 appears here too but this line does not start with "- ".

## Blockers

None.
"""
    parsed = parse_project_state(text, "docs/PROJECT_STATE.md")
    assert parsed.value is not None
    assert parsed.value.completed_task_refs == ()


def test_document_with_no_recognizable_structure_degrades_to_raw_text() -> None:
    text = (FIXTURES / "project_state_no_structure.md").read_text(encoding="utf-8")
    parsed = parse_project_state(text, "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None
    assert parsed.raw_text == text
    assert parsed.notes


def test_partial_document_degrades_to_low_confidence_but_keeps_what_it_found() -> None:
    text = "Current Version: 2.0.0\n\nNo Summary or Blockers heading here.\n"
    parsed = parse_project_state(text, "docs/PROJECT_STATE.md")
    assert parsed.confidence is Confidence.LOW
    assert parsed.value is not None
    assert parsed.value.version_fact == "2.0.0"
    assert parsed.value.summary is None
    assert parsed.value.blockers == ()
    assert len(parsed.notes) == 2


def test_empty_document_degrades_without_crashing() -> None:
    """SC-34: a truncated-to-empty `PROJECT_STATE.md` must degrade to a reported condition, not
    raise, and must not be mistaken for a well-formed document with nothing in it."""
    parsed = parse_project_state("", "docs/PROJECT_STATE.md")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None
    assert parsed.raw_text == ""
    assert parsed.notes


def test_real_repository_project_state_parses_at_high_confidence() -> None:
    """Guards against the parser being too strict for this repository's actual document."""
    real_path = Path(__file__).resolve().parents[2] / "docs" / "PROJECT_STATE.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_project_state(text, "docs/PROJECT_STATE.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert parsed.value.version_fact is not None
    assert parsed.value.summary is not None
    assert parsed.value.completed_task_refs != ()
