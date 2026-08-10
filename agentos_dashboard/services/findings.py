"""EN-15 `Finding` draft records (`DATA_MODEL.md`; `API_SPEC.md` EP-23; `PRODUCT_SPEC.md`
DR-060).

A finding created here is always the local, draft kind (`DATA_MODEL.md` EN-15: "both" repo-report
and dashboard.db, labeled) — this module writes only to `dashboard.db`'s `findings` table, never
to a repository report file. `services.approvals` also inserts rows into this same table when a
draft approval's `target_commit` fails to reconcile (DR-061); those rows carry `disposition =
"auto-reconciliation"` and no `client_token`, so they are exempt from idempotent replay (they are
system-raised, not a user-submitted form) but otherwise read through the same `get_finding`/
`list_findings` functions below.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import UUID, uuid4

from agentos_dashboard.core import DashboardError, utc_now
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.services.audit import record_audit_event
from agentos_dashboard.storage.db import IdempotencyConflict, canonical_request_hash

__all__ = [
    "Finding",
    "FindingSeverity",
    "InvalidFindingPayload",
    "create_finding",
    "get_finding",
    "get_finding_by_token",
    "list_findings",
]


class FindingSeverity(StrEnum):
    """`UI_SPEC.md` §4 badge vocabulary severities, exactly as DR-060 names them."""

    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    OBSERVATION = "observation"


class InvalidFindingPayload(DashboardError):
    """A `create_finding` field failed validation before any write occurred."""


@dataclass(frozen=True)
class Finding:
    uuid: str
    client_token: str | None
    request_hash: str | None
    run_uuid: str | None
    severity: FindingSeverity
    text: str
    disposition: str | None
    created_at: str


def _row_to_finding(row: Any) -> Finding:
    return Finding(
        uuid=row["uuid"],
        client_token=row["client_token"],
        request_hash=row["request_hash"],
        run_uuid=row["run_uuid"],
        severity=FindingSeverity(row["severity"]),
        text=row["text"],
        disposition=row["disposition"],
        created_at=row["created_at"],
    )


def get_finding(conn: Connection, finding_uuid: str) -> Finding | None:
    row = conn.execute(
        "SELECT uuid, client_token, request_hash, run_uuid, severity, text, disposition, "
        "created_at "
        "FROM findings WHERE uuid = ?",
        (finding_uuid,),
    ).fetchone()
    return _row_to_finding(row) if row is not None else None


def get_finding_by_token(conn: Connection, client_token: str) -> Finding | None:
    row = conn.execute(
        "SELECT uuid FROM findings WHERE client_token = ?", (client_token,)
    ).fetchone()
    return get_finding(conn, row["uuid"]) if row is not None else None


def list_findings(conn: Connection, *, run_uuid: str | None = None) -> tuple[Finding, ...]:
    if run_uuid is None:
        rows = conn.execute(
            "SELECT uuid FROM findings ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT uuid FROM findings WHERE run_uuid = ? ORDER BY created_at DESC, rowid DESC",
            (run_uuid,),
        ).fetchall()
    findings = (get_finding(conn, row["uuid"]) for row in rows)
    return tuple(f for f in findings if f is not None)


def create_finding(
    conn: Connection,
    audit_log_path: Path,
    *,
    severity: FindingSeverity,
    text: str,
    client_token: str,
    run_uuid: str | None = None,
    disposition: str | None = None,
    now: Callable[[], datetime] = utc_now,
) -> Finding:
    """Create one draft `Finding`, or return the existing one for a replayed `client_token`
    unchanged (SC-23)."""
    if not text.strip():
        raise InvalidFindingPayload("text must not be empty")
    try:
        client_token = str(UUID(client_token))
    except ValueError as exc:
        raise InvalidFindingPayload("client_token must be a UUID") from exc
    if run_uuid is not None:
        try:
            UUID(run_uuid)
        except ValueError as exc:
            raise InvalidFindingPayload("run_uuid must be a UUID") from exc
        if conn.execute("SELECT 1 FROM stage_runs WHERE uuid = ?", (run_uuid,)).fetchone() is None:
            raise InvalidFindingPayload("run_uuid does not identify a recorded run")
    text = redact_secrets(text)
    disposition = redact_secrets(disposition) if disposition is not None else None
    request_hash = canonical_request_hash(
        {
            "severity": severity.value,
            "text": text,
            "run_uuid": run_uuid,
            "disposition": disposition,
        }
    )

    existing = get_finding_by_token(conn, client_token)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflict(
                "client_token was already used for a different finding payload"
            )
        return existing

    finding_uuid = str(uuid4())
    created_at = now().isoformat()
    inserted = conn.execute(
        "INSERT OR IGNORE INTO findings (uuid, client_token, request_hash, run_uuid, severity, "
        "text, disposition, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            finding_uuid,
            client_token,
            request_hash,
            run_uuid,
            severity.value,
            text,
            disposition,
            created_at,
        ),
    )
    if inserted.rowcount == 0:
        concurrent = get_finding_by_token(conn, client_token)
        assert concurrent is not None
        if concurrent.request_hash != request_hash:
            raise IdempotencyConflict(
                "client_token was already used for a different finding payload"
            )
        return concurrent
    record_audit_event(
        conn,
        audit_log_path,
        kind="finding_created",
        payload={
            "finding_uuid": finding_uuid,
            "severity": severity.value,
            "run_uuid": run_uuid,
            "request_hash": request_hash,
        },
    )
    created = get_finding(conn, finding_uuid)
    assert created is not None
    return created
