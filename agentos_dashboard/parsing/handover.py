"""Tolerant parser for `handover/PROJECT_CHECKSUM.md`'s Markdown checksum table
(`SOURCE_OF_TRUTH.md` Authority Table: "Handover pair").

Structurally mirrors `ai_workflow_engine.handover.manifest.parse_manifest`'s row grammar —
`| path | size | (optional column) | digest |` — but degrades on a malformed row to a
`ConsistencyFinding`-worthy note instead of raising `ManifestParseError`
(`DASH-003.md`: "no exceptions escape"). Recomputing each record's digest against the real
repository and reconciling it belongs to `agentos_dashboard.services.consistency`, which is the
only caller with access to the file adapter; this module only extracts what the manifest
*claims*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_dashboard.parsing.models import Confidence, ParsedDocument

__all__ = [
    "ManifestRecord",
    "parse_checksum_manifest",
]

_ROW = re.compile(
    r"^\|\s*`?(?P<path>[^|`]+?)`?\s*\|\s*(?P<size>\d+)\s*\|"
    r"(?:[^|]*\|)?\s*`?(?P<digest>[0-9a-fA-F]{8,64})(?:…|\.\.\.)?`?\s*\|\s*$"
)


@dataclass(frozen=True)
class ManifestRecord:
    """EN-25: one claimed checksum-manifest row."""

    path: str
    size: int
    digest: str
    source: str
    line: int


def parse_checksum_manifest(text: str, source: str) -> ParsedDocument[tuple[ManifestRecord, ...]]:
    records: list[ManifestRecord] = []
    skipped = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("|") or "---" in line or "Relative path" in line:
            continue
        match = _ROW.match(line)
        if match is None:
            skipped += 1
            continue
        records.append(
            ManifestRecord(
                path=match.group("path").strip(),
                size=int(match.group("size")),
                digest=match.group("digest").lower(),
                source=source,
                line=line_number,
            )
        )

    if not records:
        notes: tuple[str, ...] = (
            ("no manifest records found",)
            if skipped == 0
            else (f"{skipped} malformed row(s), no valid record recovered",)
        )
        return ParsedDocument(
            source=source, confidence=Confidence.NONE, value=None, raw_text=text, notes=notes
        )

    notes = () if skipped == 0 else (f"{skipped} malformed row(s) skipped",)
    confidence = Confidence.HIGH if not notes else Confidence.LOW
    return ParsedDocument(
        source=source,
        confidence=confidence,
        value=tuple(records),
        raw_text=text,
        notes=notes,
    )
