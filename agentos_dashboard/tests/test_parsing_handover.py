"""TC-01/TC-02 — `parsing.handover`."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.parsing.handover import parse_checksum_manifest
from agentos_dashboard.parsing.models import Confidence

FIXTURES = Path(__file__).parent / "fixtures" / "malformed"

WELL_FORMED = """\
# Project Checksum Manifest

| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |
|---|---|---|---|
| handover/PROJECT_HANDOVER.md | 19326 | 2026-07-29 | be62a17ad2cd3d7543977bd611987ceea467614 |
"""


def test_well_formed_manifest_parses_at_high_confidence() -> None:
    parsed = parse_checksum_manifest(WELL_FORMED, "handover/PROJECT_CHECKSUM.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert len(parsed.value) == 1
    record = parsed.value[0]
    assert record.path == "handover/PROJECT_HANDOVER.md"
    assert record.size == 19326
    assert record.digest == "be62a17ad2cd3d7543977bd611987ceea467614"
    assert record.line == 5


def test_header_and_separator_rows_are_ignored() -> None:
    parsed = parse_checksum_manifest(WELL_FORMED, "handover/PROJECT_CHECKSUM.md")
    assert parsed.value is not None
    assert len(parsed.value) == 1  # the header row and the `---` row never became records


def test_malformed_row_is_skipped_and_degrades_confidence() -> None:
    text = (FIXTURES / "checksum_manifest_malformed_row.md").read_text(encoding="utf-8")
    parsed = parse_checksum_manifest(text, "fixture")
    assert parsed.confidence is Confidence.LOW
    assert parsed.value is not None
    assert len(parsed.value) == 1
    assert parsed.value[0].path == "handover/PROJECT_CHECKSUM.md"
    assert any("malformed" in note for note in parsed.notes)


def test_document_with_no_valid_rows_degrades_to_raw_text() -> None:
    parsed = parse_checksum_manifest("# Not a manifest\n\nJust prose.\n", "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None


def test_real_checksum_manifest_parses_at_high_confidence() -> None:
    real_path = Path(__file__).resolve().parents[2] / "handover" / "PROJECT_CHECKSUM.md"
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_checksum_manifest(text, "handover/PROJECT_CHECKSUM.md")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert any(record.path == "handover/PROJECT_HANDOVER.md" for record in parsed.value)
