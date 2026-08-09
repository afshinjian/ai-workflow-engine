"""EP-12 (`API_SPEC.md` §2): the Consistency page's JSON view — findings plus their local
acknowledgment history (`api.acknowledgments`)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentos_dashboard.api.acknowledgments import AcknowledgmentRecord, finding_fingerprint
from agentos_dashboard.services.consistency import ConsistencyFinding, ConsistencyReport

__all__ = [
    "AcknowledgeRequest",
    "acknowledgment_to_json",
    "consistency_report_to_json",
]


class AcknowledgeRequest(BaseModel):
    """`POST /dash/api/v1/consistency/acknowledge`'s body."""

    fingerprint: str = Field(min_length=1, max_length=64)
    note: str = Field(min_length=1, max_length=2000)


def acknowledgment_to_json(record: AcknowledgmentRecord) -> dict[str, Any]:
    return {
        "fingerprint": record.fingerprint,
        "note": record.note,
        "acknowledged_at": record.acknowledged_at,
    }


def _finding_to_json(
    finding: ConsistencyFinding, acknowledgments: tuple[AcknowledgmentRecord, ...]
) -> dict[str, Any]:
    fingerprint = finding_fingerprint(finding)
    matching = tuple(a for a in acknowledgments if a.fingerprint == fingerprint)
    return {
        "fingerprint": fingerprint,
        "rule": finding.rule,
        "severity": finding.severity.value,
        "message": finding.message,
        "sources": list(finding.sources),
        "acknowledgments": [acknowledgment_to_json(a) for a in matching],
    }


def consistency_report_to_json(
    report: ConsistencyReport, acknowledgments: tuple[AcknowledgmentRecord, ...]
) -> dict[str, Any]:
    return {
        "generated_at": report.generated_at.isoformat(),
        "findings": [_finding_to_json(f, acknowledgments) for f in report.findings],
        "acknowledgment_history": [acknowledgment_to_json(a) for a in acknowledgments],
    }
