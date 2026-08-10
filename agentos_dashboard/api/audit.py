"""EP-16 (`API_SPEC.md` §2): the merged audit timeline (PG-10)."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.services.audit import TimelineEntry

__all__ = ["timeline_entry_to_json"]


def timeline_entry_to_json(entry: TimelineEntry) -> dict[str, Any]:
    return {
        "origin": entry.origin,
        "kind": entry.kind,
        "summary": entry.summary,
        "actor": entry.actor,
        "ts": entry.ts,
        "sequence": entry.sequence,
        "contradiction": entry.contradiction,
        "payload": dict(entry.payload),
    }
