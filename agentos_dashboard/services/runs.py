"""EN-11 `StageRun`, EN-16 `ValidationRun` (`DATA_MODEL.md`): manual run records (`API_SPEC.md`
EP-15/EP-22; `PRODUCT_SPEC.md` DR-050..052).

`create_run` is the one write path. It is idempotent on the caller-supplied `client_token`
(`API_SPEC.md` §1, SC-23): a replayed token returns the original record unchanged, with no new
row and no new `AuditEvent`. Report-path existence is verified *live*, against the repository the
running process currently sees, every time a `StageRun` is read back — never persisted as a stale
boolean — so `DR-051`'s "report-path existence verified" reflects the repository's current state
even if a report file is created or removed after the run record itself was written; the recorded
`report_path` string is `stage.py`'s own field (`DATA_MODEL.md` EN-11), the *claim*, and
`report_path_verified` is the one field on `StageRunView` that is always repo-derived
(`SOURCE_OF_TRUTH.md` TR-02: the split `PRODUCT_SPEC.md` DR-051 requires).

Every free-text field an operator types — including `tool`, `reported_result`, `notes`,
`findings_text`, `validation_summary`, `external_reference`, and each validation entry's
`command`/`origin`/count names — is passed through
`core.redact.redact_secrets` before the idempotency hash is computed or anything is written
(SC-09), for the same reason `services/notes.py` does: a pasted credential must not survive into
`dashboard.db` or any later response. `report_path` itself is never redacted — it is a path, not
free text, and is validated by `core.paths`/`core.files` on every read instead.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import UUID, uuid4

from agentos_dashboard.core import DashboardError, utc_now
from agentos_dashboard.core.files import FileAccessError, digest_file, stat_file
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.services.audit import record_audit_event
from agentos_dashboard.storage.db import IdempotencyConflict, canonical_request_hash

__all__ = [
    "MAX_EVIDENCE_FILE_BYTES",
    "InvalidRunPayload",
    "StageRun",
    "StageRunView",
    "ValidationEntry",
    "ValidationEntryInput",
    "ValidationResult",
    "create_run",
    "get_run",
    "get_run_by_token",
    "list_runs",
    "verify_report_path",
]


class ValidationResult(StrEnum):
    """`PRODUCT_SPEC.md` DR-071's tri-state, applied to one recorded validation command."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class InvalidRunPayload(DashboardError):
    """A `create_run`/`ValidationEntryInput` field failed validation before any write occurred."""


@dataclass(frozen=True)
class ValidationEntryInput:
    """One `POST /runs` validation-matrix line, as supplied by the caller (DR-070)."""

    command: str
    result: ValidationResult
    origin: str
    counts: dict[str, int] | None = None


@dataclass(frozen=True)
class ValidationEntry:
    """One persisted `validation_runs` row."""

    uuid: str
    run_uuid: str
    command: str
    result: ValidationResult
    origin: str
    counts: dict[str, int] | None
    recorded_at: str


@dataclass(frozen=True)
class StageRun:
    """One persisted `stage_runs` row (EN-11), exactly as stored — the user's *claim*."""

    uuid: str
    client_token: str | None
    request_hash: str
    stage_id: str
    prompt_hash: str | None
    tool: str
    started_at: str
    ended_at: str | None
    reported_result: str
    report_path: str | None
    validation_summary: str | None
    findings_text: str | None
    notes: str | None
    external_reference: str | None
    created_at: str
    validation_entries: tuple[ValidationEntry, ...]


@dataclass(frozen=True)
class StageRunView(StageRun):
    """A `StageRun` plus the one repo-verified field (DR-051): never persisted, always
    recomputed against the repository state at read time."""

    report_path_verified: bool | None  # None when no report_path was recorded at all
    report_size_bytes: int | None
    report_sha256: str | None
    report_hash_verified: bool | None


MAX_EVIDENCE_FILE_BYTES = 5 * 1024 * 1024
_SHA256_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")


def verify_report_path(root: RepositoryRoot, report_path: str | None) -> bool | None:
    """`None` when no path was recorded; else whether that path currently resolves to a real
    file in the repository (`DR-051`)."""
    if not report_path:
        return None
    try:
        stat_file(root, report_path)
    except (FileAccessError, PathRefusedError):
        return False
    return True


def _report_evidence(
    root: RepositoryRoot, report_path: str | None
) -> tuple[bool | None, int | None, str | None, bool | None]:
    if not report_path:
        return None, None, None, None
    try:
        before = stat_file(root, report_path)
        if before.size_bytes > MAX_EVIDENCE_FILE_BYTES:
            return True, before.size_bytes, None, False
        digest = digest_file(root, report_path)
        after = stat_file(root, report_path)
    except (FileAccessError, PathRefusedError):
        return False, None, None, False
    stable = before == after
    return True, after.size_bytes, digest if stable else None, stable


def _row_to_run(row: Any, validation_entries: tuple[ValidationEntry, ...]) -> StageRun:
    return StageRun(
        uuid=row["uuid"],
        client_token=row["client_token"],
        request_hash=row["request_hash"],
        stage_id=row["stage_id"],
        prompt_hash=row["prompt_hash"],
        tool=row["tool"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        reported_result=row["reported_result"],
        report_path=row["report_path"],
        validation_summary=row["validation_summary"],
        findings_text=row["findings_text"],
        notes=row["notes"],
        external_reference=row["external_reference"],
        created_at=row["created_at"],
        validation_entries=validation_entries,
    )


def _validation_entries_for(conn: Connection, run_uuid: str) -> tuple[ValidationEntry, ...]:
    rows = conn.execute(
        "SELECT uuid, run_uuid, command, result, counts, origin, recorded_at "
        "FROM validation_runs WHERE run_uuid = ? ORDER BY recorded_at ASC, ordinal ASC, uuid ASC",
        (run_uuid,),
    ).fetchall()
    return tuple(
        ValidationEntry(
            uuid=row["uuid"],
            run_uuid=row["run_uuid"],
            command=row["command"],
            result=ValidationResult(row["result"]),
            origin=row["origin"],
            counts=json.loads(row["counts"]) if row["counts"] else None,
            recorded_at=row["recorded_at"],
        )
        for row in rows
    )


def get_run(conn: Connection, run_uuid: str) -> StageRun | None:
    row = conn.execute(
        "SELECT uuid, client_token, request_hash, stage_id, prompt_hash, tool, started_at, "
        "ended_at, "
        "reported_result, report_path, validation_summary, findings_text, notes, "
        "external_reference, created_at FROM stage_runs WHERE uuid = ?",
        (run_uuid,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_run(row, _validation_entries_for(conn, run_uuid))


def get_run_by_token(conn: Connection, client_token: str) -> StageRun | None:
    row = conn.execute(
        "SELECT uuid FROM stage_runs WHERE client_token = ?", (client_token,)
    ).fetchone()
    if row is None:
        return None
    return get_run(conn, row["uuid"])


def list_runs(conn: Connection, *, limit: int = 200, offset: int = 0) -> tuple[StageRun, ...]:
    if limit < 1 or limit > 200 or offset < 0:
        raise ValueError("run pagination must use limit 1..200 and offset >= 0")
    rows = conn.execute(
        "SELECT uuid FROM stage_runs ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    runs = (get_run(conn, row["uuid"]) for row in rows)
    return tuple(run for run in runs if run is not None)


def to_view(root: RepositoryRoot, run: StageRun) -> StageRunView:
    verified, size_bytes, sha256, hash_verified = _report_evidence(root, run.report_path)
    return StageRunView(
        uuid=run.uuid,
        client_token=run.client_token,
        request_hash=run.request_hash,
        stage_id=run.stage_id,
        prompt_hash=run.prompt_hash,
        tool=run.tool,
        started_at=run.started_at,
        ended_at=run.ended_at,
        reported_result=run.reported_result,
        report_path=run.report_path,
        validation_summary=run.validation_summary,
        findings_text=run.findings_text,
        notes=run.notes,
        external_reference=run.external_reference,
        created_at=run.created_at,
        validation_entries=run.validation_entries,
        report_path_verified=verified,
        report_size_bytes=size_bytes,
        report_sha256=sha256,
        report_hash_verified=hash_verified,
    )


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidRunPayload(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidRunPayload(f"{field} must include a timezone offset")
    return parsed


def _request_identity(
    *,
    stage_id: str,
    tool: str,
    started_at: str,
    reported_result: str,
    prompt_hash: str | None,
    ended_at: str | None,
    report_path: str | None,
    validation_entries: Sequence[ValidationEntryInput],
    validation_summary: str | None,
    findings_text: str | None,
    notes: str | None,
    external_reference: str | None,
) -> str:
    return canonical_request_hash(
        {
            "stage_id": stage_id,
            "tool": tool,
            "started_at": started_at,
            "reported_result": reported_result,
            "prompt_hash": prompt_hash,
            "ended_at": ended_at,
            "report_path": report_path,
            "validation": [
                {
                    "command": entry.command,
                    "result": entry.result.value,
                    "origin": entry.origin,
                    "counts": entry.counts,
                }
                for entry in validation_entries
            ],
            "validation_summary": validation_summary,
            "findings_text": findings_text,
            "notes": notes,
            "external_reference": external_reference,
        }
    )


def create_run(
    root: RepositoryRoot,
    conn: Connection,
    audit_log_path: Path,
    *,
    stage_id: str,
    tool: str,
    started_at: str,
    reported_result: str,
    client_token: str,
    prompt_hash: str | None = None,
    ended_at: str | None = None,
    report_path: str | None = None,
    validation_entries: Sequence[ValidationEntryInput] = (),
    validation_summary: str | None = None,
    findings_text: str | None = None,
    notes: str | None = None,
    external_reference: str | None = None,
    now: Callable[[], datetime] = utc_now,
) -> StageRunView:
    """Create one `StageRun`, or return the existing one for a replayed `client_token`
    unchanged (`API_SPEC.md` EP-22, SC-23)."""
    if not stage_id.strip():
        raise InvalidRunPayload("stage_id must not be empty")
    if not tool.strip():
        raise InvalidRunPayload("tool must not be empty")
    if not reported_result.strip():
        raise InvalidRunPayload("reported_result must not be empty")
    try:
        client_token = str(UUID(client_token))
    except ValueError as exc:
        raise InvalidRunPayload("client_token must be a UUID") from exc
    start = _parse_timestamp(started_at, "started_at")
    if ended_at is not None:
        end = _parse_timestamp(ended_at, "ended_at")
        if end < start:
            raise InvalidRunPayload("ended_at must not precede started_at")
    if prompt_hash is not None and not _SHA256_RE.fullmatch(prompt_hash):
        raise InvalidRunPayload("prompt_hash must be a 64-character SHA-256 hex digest")
    for entry in validation_entries:
        if not entry.command.strip() or len(entry.command) > 500:
            raise InvalidRunPayload("validation command must contain 1..500 characters")
        if not entry.origin.strip() or len(entry.origin) > 100:
            raise InvalidRunPayload("validation origin must contain 1..100 characters")
        if entry.counts is not None and any(
            not key or len(key) > 100 or value < 0 for key, value in entry.counts.items()
        ):
            raise InvalidRunPayload(
                "validation counts require bounded names and non-negative values"
            )

    stage_id = redact_secrets(stage_id)
    tool = redact_secrets(tool)
    reported_result = redact_secrets(reported_result)
    if report_path is not None and redact_secrets(report_path) != report_path:
        raise InvalidRunPayload("report_path contains credential-shaped content")
    notes = redact_secrets(notes) if notes is not None else None
    findings_text = redact_secrets(findings_text) if findings_text is not None else None
    validation_summary = (
        redact_secrets(validation_summary) if validation_summary is not None else None
    )
    external_reference = (
        redact_secrets(external_reference) if external_reference is not None else None
    )
    validation_entries = tuple(
        ValidationEntryInput(
            command=redact_secrets(entry.command),
            result=entry.result,
            origin=redact_secrets(entry.origin),
            counts=(
                {redact_secrets(key): value for key, value in entry.counts.items()}
                if entry.counts is not None
                else None
            ),
        )
        for entry in validation_entries
    )

    request_hash = _request_identity(
        stage_id=stage_id,
        tool=tool,
        started_at=started_at,
        reported_result=reported_result,
        prompt_hash=prompt_hash,
        ended_at=ended_at,
        report_path=report_path,
        validation_entries=validation_entries,
        validation_summary=validation_summary,
        findings_text=findings_text,
        notes=notes,
        external_reference=external_reference,
    )

    existing = get_run_by_token(conn, client_token)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflict("client_token was already used for a different run payload")
        return to_view(root, existing)

    run_uuid = str(uuid4())
    created_at = now().isoformat()
    inserted = conn.execute(
        "INSERT OR IGNORE INTO stage_runs "
        "(uuid, client_token, request_hash, stage_id, prompt_hash, tool, started_at, "
        "ended_at, reported_result, report_path, validation_summary, findings_text, notes, "
        "external_reference, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_uuid,
            client_token,
            request_hash,
            stage_id,
            prompt_hash,
            tool,
            started_at,
            ended_at,
            reported_result,
            report_path,
            validation_summary,
            findings_text,
            notes,
            external_reference,
            created_at,
        ),
    )
    if inserted.rowcount == 0:
        concurrent = get_run_by_token(conn, client_token)
        assert concurrent is not None
        if concurrent.request_hash != request_hash:
            raise IdempotencyConflict("client_token was already used for a different run payload")
        return to_view(root, concurrent)
    for ordinal, entry in enumerate(validation_entries):
        conn.execute(
            "INSERT INTO validation_runs (uuid, run_uuid, command, result, counts, origin, "
            "ordinal, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                run_uuid,
                entry.command,
                entry.result.value,
                json.dumps(entry.counts, sort_keys=True) if entry.counts is not None else None,
                entry.origin,
                ordinal,
                created_at,
            ),
        )

    record_audit_event(
        conn,
        audit_log_path,
        kind="run_created",
        payload={
            "run_uuid": run_uuid,
            "stage_id": stage_id,
            "prompt_hash": prompt_hash,
            "request_hash": request_hash,
        },
    )

    created = get_run(conn, run_uuid)
    assert created is not None  # just inserted, in the same connection/transaction
    return to_view(root, created)
