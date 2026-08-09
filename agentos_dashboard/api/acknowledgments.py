"""PG-11's "acknowledge (local note)" action (`UI_SPEC.md` §3): an in-process, in-memory
acknowledgment log for consistency findings.

Deliberately not persisted: `docs/agentos-dashboard/OPEN_QUESTIONS.md` OD-D5 approved
`data/agentos_dashboard/dashboard.db` for DASH-008, which does not exist yet, and this stage's
Allowed list grants no local-database work. An acknowledgment note is process-lifetime state —
lost on restart (`SECURITY_MODEL.md` SC-26's "restart recovers all derived state" already treats
this whole class of cache as disposable) — held here rather than in `RepositorySnapshot` (which
must stay an immutable, rebuildable read of the repository) or in the repository itself (this
package never writes to the repository, `TR-08`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from agentos_dashboard.core import utc_now
from agentos_dashboard.services.consistency import ConsistencyFinding

__all__ = ["AcknowledgmentRecord", "AcknowledgmentStore", "finding_fingerprint"]


def finding_fingerprint(finding: ConsistencyFinding) -> str:
    """A stable identity for one `ConsistencyFinding` across re-renders of the same condition.

    Findings carry no persisted id (they are recomputed on every request), so the fingerprint is
    derived from the finding's own content — rule, message, and sources — which is exactly the
    set of fields that changes if and only if the underlying condition changes.
    """
    payload = "\x1f".join((finding.rule, finding.message, *finding.sources))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AcknowledgmentRecord:
    fingerprint: str
    note: str
    acknowledged_at: str


class AcknowledgmentStore:
    """One process-lifetime, in-memory acknowledgment log (EN-style, append-only within a run)."""

    def __init__(self) -> None:
        self._records: list[AcknowledgmentRecord] = []

    def add(self, *, fingerprint: str, note: str) -> AcknowledgmentRecord:
        record = AcknowledgmentRecord(
            fingerprint=fingerprint, note=note, acknowledged_at=utc_now().isoformat()
        )
        self._records.append(record)
        return record

    def all(self) -> tuple[AcknowledgmentRecord, ...]:
        return tuple(self._records)

    def for_fingerprint(self, fingerprint: str) -> tuple[AcknowledgmentRecord, ...]:
        return tuple(r for r in self._records if r.fingerprint == fingerprint)
