"""EP-11 (`API_SPEC.md` §2): the handover viewer's JSON view."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.services.consistency import ConsistencyFinding
from agentos_dashboard.services.handover import HandoverData, HandoverRecord

__all__ = ["handover_view_to_json"]


def _finding_to_json(finding: ConsistencyFinding) -> dict[str, Any]:
    return {
        "rule": finding.rule,
        "severity": finding.severity.value,
        "message": finding.message,
        "sources": list(finding.sources),
    }


def _record_to_json(record: HandoverRecord) -> dict[str, Any]:
    return {
        "path": record.path,
        "claimed_size": record.claimed_size,
        "claimed_digest": record.claimed_digest,
        "exists": record.exists,
        "actual_size": record.actual_size,
        "actual_digest": record.actual_digest,
        "size_match": record.size_match,
        "digest_match": record.digest_match,
    }


def handover_view_to_json(data: HandoverData) -> dict[str, Any]:
    return {
        "manifest_path": data.manifest_path,
        "manifest_instructions": data.manifest_instructions,
        "narrative_path": data.narrative_path,
        "narrative_text": data.narrative_text,
        "narrative_truncated": data.narrative_truncated,
        "records": [_record_to_json(r) for r in data.records],
        "narrative_mtime_ns": data.narrative_mtime_ns,
        "newest_governance_mtime_ns": data.newest_governance_mtime_ns,
        "newest_governance_path": data.newest_governance_path,
        "stale": data.stale,
        "findings": [_finding_to_json(f) for f in data.findings],
    }
