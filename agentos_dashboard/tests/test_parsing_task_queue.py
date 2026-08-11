"""TC-01/TC-02 — `parsing.task_queue`, exercised against `docs/TASK_QUEUE.md`-shaped headings
and the mirrors' Markdown-table shape."""

from __future__ import annotations

from pathlib import Path

import pytest

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


EMPTY_CURRENT_TASK = """\
# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## No task is currently active

FAKE-001 — First task was closed `Current -> Done` on 2026-08-09 by explicit Human Owner
approval. The Current set is therefore empty. Under self-governance.yaml's
maximum_current_tasks: 1 this is a legal state — the maximum is a ceiling, not a quota.
"""

NARRATIVE_REMAINING_TASKS = """\
# Remaining Work

| Task | Title | Status |
|---|---|---|
| FAKE-003 | Third task | Planned |

## FAKE-001 closure — 2026-08-05

FAKE-001 was closed `Current -> Done` on 2026-08-05. This heading merely narrates that
closure; it names an id in passing but is not itself a task record.

## FAKE-002 implementation update — 2026-08-08

FAKE-002 was implemented and validated the same day, stopped for Human Owner approval.
"""


# ---------------------------------------------------------------------------
# REC-001, corrected per the REC001-REV-001/REC001-REV-002 review round.
#
# REC001-REV-001: the empty-declaration matcher was too permissive (crossed lines, accepted
# pluralization errors and narrative qualifiers) and had no notion of *which* document is allowed
# to mean "this collection is empty" — and it overrode genuine parser diagnostics rather than
# coexisting with them. REC001-REV-002: heading classification only validated what followed a
# located id, not the complete heading shape, so a genuine emphasized heading (`## **FAKE-001**
# — Real task`) could silently disappear, and a narrative heading with real prose *before* the id
# (`## Closure record for FAKE-001 — 2026-08-08`) could still be misread as a task record.
# ---------------------------------------------------------------------------


class TestEmptyCurrentDeclaration:
    """Section 3 "Empty declaration" cases from the REC-001 correction review."""

    def test_exact_valid_declaration(self) -> None:
        parsed = parse_task_records(
            "## No task is currently active\n", "docs/current_task.md", recognize_empty_current=True
        )
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value == ()
        assert parsed.notes == ()

    def test_valid_declaration_with_ordinary_surrounding_content(self) -> None:
        """The real `docs/current_task.md` shape: the declaration heading plus explanatory prose
        below it (not on the same line) must still be recognized."""
        parsed = parse_task_records(
            EMPTY_CURRENT_TASK, "docs/current_task.md", recognize_empty_current=True
        )
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value == ()
        assert parsed.notes == ()

    def test_declaration_plus_genuine_missing_status_heading_fails_closed(self) -> None:
        """An empty declaration does not override a diagnostic: a genuine task-shaped heading
        that fails to parse (no Status field) alongside the declaration must NOT produce a
        pristine `Confidence.HIGH, value=()` — it must still fail/degrade."""
        text = (
            "# Current Task\n\n"
            "## No task is currently active\n\n"
            "## FAKE-001 — Missing status\n\n"
            "Scope only.\n"
        )
        parsed = parse_task_records(text, "docs/current_task.md", recognize_empty_current=True)
        assert parsed.confidence is not Confidence.HIGH
        assert parsed.notes != ()
        assert any("skipped" in note for note in parsed.notes)

    def test_declaration_plus_malformed_table_row_fails_closed(self) -> None:
        text = (
            "# Current Task\n\n"
            "## No task is currently active\n\n"
            "| Task | Notes |\n"
            "|---|---|\n"
            "| FAKE-005 | orphaned row, no status column |\n"
        )
        parsed = parse_task_records(text, "docs/current_task.md", recognize_empty_current=True)
        assert parsed.confidence is not Confidence.HIGH
        assert parsed.notes != ()
        assert any("skipped" in note for note in parsed.notes)

    def test_malformed_plural_declaration_is_rejected(self) -> None:
        parsed = parse_task_records(
            "## No tasks is currently active\n",
            "docs/current_task.md",
            recognize_empty_current=True,
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_multiline_declaration_is_rejected(self) -> None:
        """`\\s` must never be used for this match — it would silently cross the heading's own
        line boundary."""
        parsed = parse_task_records(
            "## No\ntask is currently active\n",
            "docs/current_task.md",
            recognize_empty_current=True,
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_qualified_declaration_is_rejected(self) -> None:
        parsed = parse_task_records(
            "## No task is currently active according to this stale draft\n",
            "docs/current_task.md",
            recognize_empty_current=True,
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_noncanonical_heading_level_is_rejected(self) -> None:
        """The established declaration is exactly a level-two heading, not merely the same words
        at any Markdown heading level."""
        parsed = parse_task_records(
            "### No task is currently active\n",
            "docs/current_task.md",
            recognize_empty_current=True,
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_declaration_in_a_non_current_mirror_role_is_not_recognized(self) -> None:
        """The legal-empty semantic is opt-in per call site (`recognize_empty_current`), not
        inferred from heading text alone — the same heading in `docs/TASK_QUEUE.md` or
        `docs/remaining_tasks.md` must not mean "this collection is empty"."""
        parsed = parse_task_records("## No task is currently active\n", "docs/TASK_QUEUE.md")
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_malformed_empty_document_without_a_declaration_still_fails(self) -> None:
        """A document with zero recognizable records and no recognized empty-declaration heading
        is still `Confidence.NONE`, even when the caller opted in to `recognize_empty_current` —
        legal emptiness must be explicitly declared, never merely inferred from an absence of
        structure. Fail-closed behaviour for malformed governance data is preserved."""
        text = (FIXTURES / "task_queue_no_records.md").read_text(encoding="utf-8")
        parsed = parse_task_records(text, "fixture", recognize_empty_current=True)
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None


class TestFullHeadingClassification:
    """Section 3 "Full-heading classification" cases from the REC-001 correction review. Every
    assertion goes through the public `parse_task_records` behavior, never the private
    heading-classification helpers directly."""

    def test_bare_task_id_heading(self) -> None:
        parsed = parse_task_records("## FAKE-001\n\nStatus: Current\n", "src")
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value is not None
        assert {r.task_id for r in parsed.value} == {"FAKE-001"}

    def test_task_id_with_supported_title_separator(self) -> None:
        parsed = parse_task_records("## FAKE-001 — Real task\n\nStatus: Current\n", "src")
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value is not None
        assert {r.task_id for r in parsed.value} == {"FAKE-001"}

    def test_markdown_emphasized_task_id_is_not_silently_dropped(self) -> None:
        """REC001-REV-002: `## **FAKE-001** — Real task` is a genuine task heading and must be
        recognized, matching what the authoritative engine parser would treat as a real task
        heading — it must not silently disappear."""
        parsed = parse_task_records("## **FAKE-001** — Real task\n\nStatus: Current\n", "src")
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value is not None
        by_id = {r.task_id: r for r in parsed.value}
        assert by_id.keys() == {"FAKE-001"}
        assert by_id["FAKE-001"].status is TaskStatus.CURRENT

    @pytest.mark.parametrize("wrapper", ["`", "~~"])
    def test_other_core_supported_markdown_wrappers_are_not_silently_dropped(
        self, wrapper: str
    ) -> None:
        text = f"## {wrapper}FAKE-001{wrapper} — Real task\n\nStatus: Current\n"
        parsed = parse_task_records(text, "src")
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value is not None
        assert [(r.task_id, r.status) for r in parsed.value] == [("FAKE-001", TaskStatus.CURRENT)]

    def test_prose_before_task_id_is_not_a_task_record(self) -> None:
        """REC001-REV-002: a real word before the id disqualifies the heading regardless of what
        follows the id — a document consisting only of such a heading has no recognizable
        records."""
        parsed = parse_task_records(
            "## Closure record for FAKE-001 — 2026-08-08\n\nStatus: Current\n", "src"
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_glued_punctuation_before_task_id_is_not_a_task_record(self) -> None:
        """Full-heading validation rejects punctuation-prefixed narrative references while still
        allowing the identifier-shaped `GOV-` prefix needed by the established multi-hyphen
        parser behavior."""
        for heading in ("## Related:FAKE-001 — 2026", "## /FAKE-001 — 2026"):
            parsed = parse_task_records(f"{heading}\n\nStatus: Current\n", "src")
            assert parsed.confidence is Confidence.NONE
            assert parsed.value is None

    def test_multi_hyphen_identifier_prefix_remains_supported(self) -> None:
        parsed = parse_task_records("## GOV-AUTO-08 — Real task\n\nStatus: Done\n", "src")
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value is not None
        assert [(r.task_id, r.status) for r in parsed.value] == [("AUTO-08", TaskStatus.DONE)]

    def test_mismatched_emphasis_does_not_make_a_task_heading(self) -> None:
        parsed = parse_task_records("## *FAKE-001** — Malformed\n\nStatus: Current\n", "src")
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_historical_closure_heading_is_not_a_task_record(self) -> None:
        parsed = parse_task_records(
            "## AUTO-016 closure — 2026-08-08\n\nAUTO-016 was closed.\n", "src"
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_implementation_update_heading_is_not_a_task_record(self) -> None:
        parsed = parse_task_records(
            "## DASH-005 implementation update — 2026-08-08\n\nImplemented and validated.\n", "src"
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_genuine_heading_missing_status_is_detected(self) -> None:
        parsed = parse_task_records(
            "## FAKE-001 — A task with no Status field\n\nNo status here.\n", "src"
        )
        assert parsed.confidence is Confidence.NONE
        assert any("skipped" in note for note in parsed.notes)

    def test_narrative_heading_containing_status_like_text_is_not_a_false_record(self) -> None:
        """REC001-REV-002: prose before the id disqualifies the heading even when its body
        happens to contain Status-shaped text — it must not become a false task record."""
        text = (
            "## Closure record for FAKE-001 — 2026-08-08\n\nStatus: Current (narrative, not real)\n"
        )
        parsed = parse_task_records(text, "src")
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_multiple_ids_in_one_heading_is_not_a_task_record(self) -> None:
        parsed = parse_task_records(
            "## FAKE-001 and FAKE-002 — dual task\n\nStatus: Current\n", "src"
        )
        assert parsed.confidence is Confidence.NONE
        assert parsed.value is None

    def test_unusual_but_valid_whitespace_still_parses(self) -> None:
        parsed = parse_task_records(
            "##   FAKE-001   —   Title with extra spacing\n\nStatus:   Current\n", "src"
        )
        assert parsed.confidence is Confidence.HIGH
        assert parsed.value is not None
        assert {r.task_id for r in parsed.value} == {"FAKE-001"}

    def test_mixed_table_plus_valid_heading_plus_historical_heading(self) -> None:
        text = (
            "| Task | Title | Status |\n"
            "|---|---|---|\n"
            "| FAKE-003 | Third task | Planned |\n\n"
            "## FAKE-006 — Something\n\n"
            "Status: Done\n\n"
            "## FAKE-001 closure — 2026-08-05\n\n"
            "FAKE-001 was closed.\n"
        )
        parsed = parse_task_records(text, "src")
        assert parsed.confidence is Confidence.HIGH
        assert parsed.notes == ()
        assert parsed.value is not None
        assert {r.task_id for r in parsed.value} == {"FAKE-003", "FAKE-006"}

    def test_ignoring_an_emphasized_missing_status_heading_would_falsely_pass(self) -> None:
        """REC001-REV-002: before the fix, an emphasized heading missing Status was excluded from
        candidacy entirely (its markup broke the suffix check), so this document wrongly returned
        `Confidence.HIGH` despite a genuine defect. It must now degrade."""
        text = (
            "| Task | Title | Status |\n"
            "|---|---|---|\n"
            "| FAKE-003 | Third task | Planned |\n\n"
            "## **FAKE-007** — Missing status\n\n"
            "No status field here.\n"
        )
        parsed = parse_task_records(text, "src")
        assert parsed.confidence is Confidence.LOW
        assert parsed.value is not None
        assert {r.task_id for r in parsed.value} == {"FAKE-003"}
        assert any("skipped" in note for note in parsed.notes)


def test_recognized_empty_current_declaration_parses_as_valid_empty_collection() -> None:
    """REC-001: a document that declares zero Current tasks via the established
    `## No task is currently active` heading, parsed in the Current-task mirror role, is a
    *recognized* empty collection, not a parse failure — the semantic distinction the task
    requires between a legal empty mirror and a genuinely unparseable one."""
    parsed = parse_task_records(
        EMPTY_CURRENT_TASK, "docs/current_task.md", recognize_empty_current=True
    )
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value == ()
    assert parsed.notes == ()


def test_real_current_task_mirror_parses_without_assuming_a_transient_task_count() -> None:
    """The live mirror may legally contain zero or one Current task depending on governance
    phase. The parser contract is high-confidence recognition, not a transient repository fact."""
    real_path = Path(__file__).resolve().parents[2] / "docs" / "current_task.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_task_records(text, "docs/current_task.md", recognize_empty_current=True)
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert len(parsed.value) <= 1
    assert all(record.status is TaskStatus.CURRENT for record in parsed.value)


def test_malformed_empty_document_without_a_declaration_still_fails() -> None:
    """A document with zero recognizable records and no recognized empty-declaration heading is
    still `Confidence.NONE` — legal emptiness must be explicitly declared, not merely inferred
    from an absence of structure. Fail-closed behaviour for malformed governance data is
    preserved."""
    text = (FIXTURES / "task_queue_no_records.md").read_text(encoding="utf-8")
    parsed = parse_task_records(text, "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None


def test_historical_narrative_headings_do_not_degrade_an_otherwise_valid_mirror() -> None:
    """REC-001: dateline headings like `## FAKE-001 closure — 2026-08-05` merely mention a task
    id in passing (no `## <ID> — <Title>` shape, no Status field) and must not be counted as
    skipped task records or degrade the document's confidence, unlike a genuine task heading
    missing its Status field."""
    parsed = parse_task_records(NARRATIVE_REMAINING_TASKS, "docs/remaining_tasks.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.notes == ()
    assert parsed.value is not None
    ids = {record.task_id for record in parsed.value}
    assert ids == {"FAKE-003"}


def test_genuine_heading_missing_status_is_still_detected_amid_narrative_headings() -> None:
    """Companion to the above: a genuine `## <ID> — <Title>` heading with no Status field must
    still degrade confidence and be reported as skipped, even in a document that also contains
    narrative headings that must NOT be counted."""
    text = NARRATIVE_REMAINING_TASKS.replace(
        "## FAKE-001 closure — 2026-08-05",
        "## FAKE-004 — A task with no Status field\n\n## FAKE-001 closure — 2026-08-05",
    )
    parsed = parse_task_records(text, "docs/remaining_tasks.md")
    assert parsed.confidence is Confidence.LOW
    assert parsed.value is not None
    ids = {record.task_id for record in parsed.value}
    assert "FAKE-004" not in ids
    assert any("skipped" in note for note in parsed.notes)


def test_real_remaining_tasks_historical_headings_do_not_degrade_confidence() -> None:
    """Acceptance-level regression: the live `docs/remaining_tasks.md` contains exactly the
    narrative dateline headings this correction targets (`## AUTO-016 closure — 2026-08-08`,
    `## AUTO-015 closure — 2026-08-05`, `## DASH-005 implementation update — 2026-08-08`) and must
    parse without their false degradation."""
    real_path = Path(__file__).resolve().parents[2] / "docs" / "remaining_tasks.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_task_records(text, "docs/remaining_tasks.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.notes == ()


def test_real_task_queue_remains_parseable() -> None:
    """The live task queue still parses at full confidence.

    Deliberately asserts *parseability and internal consistency*, never a particular task's
    status. The previous form of this test pinned `DASH-003` to `Current`; DASH-003 was closed to
    `Done` on 2026-07-29 and the test began failing on a governance transition it was never meant
    to police. A parser test whose fixture is a mutable governance document fails every time the
    project makes normal progress, which trains readers to ignore it.

    Status-specific parsing behaviour is covered exhaustively by the fixture-based tests above,
    where the input is fixed and the expected output can be stated precisely. What this test adds
    that a fixture cannot is that the parser still copes with the *real* document's current shape
    and scale -- so a hand edit to the live queue that broke the format would still be caught.
    """
    real_path = Path(__file__).resolve().parents[2] / "docs" / "TASK_QUEUE.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_task_records(text, "docs/TASK_QUEUE.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert parsed.value, "the live task queue should contain at least one parsed record"
    by_id = {record.task_id: record for record in parsed.value}
    assert len(by_id) == len(parsed.value), "task IDs in the live queue must be unique"
    assert all(isinstance(record.status, TaskStatus) for record in parsed.value)
    # `self-governance.yaml`'s `maximum_current_tasks: 1` is a ceiling, so an empty Current set is
    # legal; more than one Current task is not, and `workflowctl check-task-state` would refuse it.
    current_ids = [tid for tid, record in by_id.items() if record.status is TaskStatus.CURRENT]
    assert len(current_ids) <= 1, f"at most one Current task is permitted, found {current_ids}"
