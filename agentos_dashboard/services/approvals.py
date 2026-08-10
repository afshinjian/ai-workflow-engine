"""EN-14 `Approval` draft records (`DATA_MODEL.md`; `API_SPEC.md` EP-23; `PRODUCT_SPEC.md`
DR-060/DR-061).

A draft approval is always local-only (`DR-062`: "the dashboard never writes authoritative
repository state") — this module never touches `docs/DECISION_LOG.md` or any other governance
document. `DR-061`'s "reconciliation tracked against later authoritative records; divergence
raises a finding" is implemented as the one concrete, machine-checkable reading available at this
stage: when a draft names a `target_commit`, that revision is resolved against the repository's
real Git history (`core.gitread.resolve_revision`) at creation time and recorded separately as
`target_commit_resolved`.  `reconciled` remains false: commit existence is not evidence that a
local draft matches any authoritative approval record.  Failure to resolve automatically raises
a `findings` row plus a `reconciliation_divergence` audit event.  A draft that names no
`target_commit` has nothing to compare and raises no finding.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import UUID, uuid4

from agentos_dashboard.core import DashboardError, utc_now
from agentos_dashboard.core.gitread import GitFailure, GitReadError, resolve_revision
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.audit import record_audit_event
from agentos_dashboard.storage.db import IdempotencyConflict, canonical_request_hash

__all__ = [
    "Approval",
    "ApprovalLayer",
    "ApprovalVerdict",
    "InvalidApprovalPayload",
    "ReconciliationUnavailable",
    "create_approval",
    "get_approval",
    "get_approval_by_token",
    "list_approvals",
]


class ApprovalLayer(StrEnum):
    """`PRODUCT_SPEC.md` DR-060's three review layers, mirroring `docs/AGENT_PROTOCOL.md`."""

    IMPLEMENTATION_REVIEW = "implementation_review"
    INDEPENDENT_REVIEW = "independent_review"
    HUMAN_APPROVAL = "human_approval"


class ApprovalVerdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


class InvalidApprovalPayload(DashboardError):
    """A draft field is invalid and no local row may be written."""


class ReconciliationUnavailable(DashboardError):
    """Live Git truth was unavailable; this must not be persisted as a divergence."""

    def __init__(self, failure: GitFailure) -> None:
        super().__init__("live Git reconciliation is unavailable")
        self.failure = failure


@dataclass(frozen=True)
class Approval:
    uuid: str
    client_token: str | None
    request_hash: str
    run_uuid: str | None
    layer: ApprovalLayer
    verdict: ApprovalVerdict
    target_hash: str | None
    target_commit: str | None
    target_commit_resolved: bool | None
    reconciled: bool
    notes: str | None
    created_at: str


def _row_to_approval(row: Any) -> Approval:
    return Approval(
        uuid=row["uuid"],
        client_token=row["client_token"],
        request_hash=row["request_hash"],
        run_uuid=row["run_uuid"],
        layer=ApprovalLayer(row["layer"]),
        verdict=ApprovalVerdict(row["verdict"]),
        target_hash=row["target_hash"],
        target_commit=row["target_commit"],
        target_commit_resolved=(
            bool(row["target_commit_resolved"])
            if row["target_commit_resolved"] is not None
            else None
        ),
        reconciled=bool(row["reconciled"]),
        notes=row["notes"],
        created_at=row["created_at"],
    )


def get_approval(conn: Connection, approval_uuid: str) -> Approval | None:
    row = conn.execute(
        "SELECT uuid, client_token, request_hash, run_uuid, layer, verdict, target_hash, "
        "target_commit, target_commit_resolved, reconciled, notes, created_at "
        "FROM approvals WHERE uuid = ?",
        (approval_uuid,),
    ).fetchone()
    return _row_to_approval(row) if row is not None else None


def get_approval_by_token(conn: Connection, client_token: str) -> Approval | None:
    row = conn.execute(
        "SELECT uuid FROM approvals WHERE client_token = ?", (client_token,)
    ).fetchone()
    return get_approval(conn, row["uuid"]) if row is not None else None


def list_approvals(conn: Connection, *, run_uuid: str | None = None) -> tuple[Approval, ...]:
    if run_uuid is None:
        rows = conn.execute(
            "SELECT uuid FROM approvals ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT uuid FROM approvals WHERE run_uuid = ? ORDER BY created_at DESC, rowid DESC",
            (run_uuid,),
        ).fetchall()
    approvals = (get_approval(conn, row["uuid"]) for row in rows)
    return tuple(a for a in approvals if a is not None)


def _resolves(root: RepositoryRoot, target_commit: str) -> bool:
    try:
        resolve_revision(root.path, target_commit)
    except GitReadError as exc:
        if exc.failure is GitFailure.UNSAFE_ARGUMENT:
            raise InvalidApprovalPayload("target_commit is not a safe Git revision") from exc
        # The shared read-only adapter uses COMMAND_FAILED both for its explicit unknown-revision
        # result and for abnormal non-zero Git exits.  Only the former is live evidence that the
        # named commit does not exist; an I/O/config/process failure must never become a persisted
        # reconciliation finding.
        if exc.failure is GitFailure.COMMAND_FAILED and exc.detail.startswith("unknown revision:"):
            return False
        raise ReconciliationUnavailable(exc.failure) from exc
    return True


def create_approval(
    root: RepositoryRoot,
    conn: Connection,
    audit_log_path: Path,
    *,
    layer: ApprovalLayer,
    verdict: ApprovalVerdict,
    client_token: str,
    run_uuid: str | None = None,
    target_hash: str | None = None,
    target_commit: str | None = None,
    notes: str | None = None,
    now: Callable[[], datetime] = utc_now,
) -> Approval:
    """Create one draft `Approval`, or return the existing one for a replayed `client_token`
    unchanged (SC-23)."""
    try:
        client_token = str(UUID(client_token))
    except ValueError as exc:
        raise InvalidApprovalPayload("client_token must be a UUID") from exc
    if run_uuid is not None:
        try:
            UUID(run_uuid)
        except ValueError as exc:
            raise InvalidApprovalPayload("run_uuid must be a UUID") from exc
        if conn.execute("SELECT 1 FROM stage_runs WHERE uuid = ?", (run_uuid,)).fetchone() is None:
            raise InvalidApprovalPayload("run_uuid does not identify a recorded run")
    if target_hash is not None and re.fullmatch(r"[0-9a-fA-F]{64}", target_hash) is None:
        raise InvalidApprovalPayload("target_hash must be a 64-character SHA-256 hex digest")
    request_hash = canonical_request_hash(
        {
            "layer": layer.value,
            "verdict": verdict.value,
            "run_uuid": run_uuid,
            "target_hash": target_hash,
            "target_commit": target_commit,
            "notes": notes,
        }
    )
    existing = get_approval_by_token(conn, client_token)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflict(
                "client_token was already used for a different approval payload"
            )
        return existing

    target_commit_resolved = _resolves(root, target_commit) if target_commit else None

    approval_uuid = str(uuid4())
    created_at = now().isoformat()
    inserted = conn.execute(
        "INSERT OR IGNORE INTO approvals (uuid, client_token, request_hash, run_uuid, layer, "
        "verdict, target_hash, "
        "target_commit, target_commit_resolved, reconciled, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            approval_uuid,
            client_token,
            request_hash,
            run_uuid,
            layer.value,
            verdict.value,
            target_hash,
            target_commit,
            None if target_commit_resolved is None else int(target_commit_resolved),
            0,
            notes,
            created_at,
        ),
    )
    if inserted.rowcount == 0:
        concurrent = get_approval_by_token(conn, client_token)
        assert concurrent is not None
        if concurrent.request_hash != request_hash:
            raise IdempotencyConflict(
                "client_token was already used for a different approval payload"
            )
        return concurrent
    record_audit_event(
        conn,
        audit_log_path,
        kind="approval_created",
        payload={
            "approval_uuid": approval_uuid,
            "layer": layer.value,
            "verdict": verdict.value,
            "target_commit_resolved": target_commit_resolved,
            "reconciled": False,
            "request_hash": request_hash,
        },
    )

    if target_commit and target_commit_resolved is False:
        finding_uuid = str(uuid4())
        conn.execute(
            "INSERT INTO findings (uuid, client_token, request_hash, run_uuid, severity, text, "
            "disposition, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding_uuid,
                None,
                None,
                run_uuid,
                "major",
                f"approval {approval_uuid}: target_commit {target_commit!r} does not resolve "
                "in the repository's Git history",
                "auto-reconciliation",
                created_at,
            ),
        )
        record_audit_event(
            conn,
            audit_log_path,
            kind="reconciliation_divergence",
            payload={
                "approval_uuid": approval_uuid,
                "finding_uuid": finding_uuid,
                "request_hash": request_hash,
            },
        )

    created = get_approval(conn, approval_uuid)
    assert created is not None
    return created
