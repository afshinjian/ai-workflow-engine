"""EN-29 `UserNote` (`DATA_MODEL.md`; `API_SPEC.md` EP-23; `PRODUCT_SPEC.md` PG-05/PG-10's "add
note" action).

`target_ref` is a free-text pointer such as `"run:<uuid>"` or `"task:DASH-008"` — this module
does not validate that the referenced entity exists, since a note may legitimately be attached
before or after the entity it discusses is otherwise recorded, and this table is never
authoritative over anything it references (`DR-062`). Rendering escapes `text` by Jinja2's default
autoescaping, never by this module — EN-29's own "escaped on render" note is a rendering-layer
property, not a storage-layer transformation.

`text` is passed through `core.redact.redact_secrets` before it is ever written (SC-09): an
operator pasting a credential into a note must not have it persist in `dashboard.db`, appear in
any API/web response, or be included in the idempotency request-hash's identity of what a caller
"said" — redaction happens first, so the hash and the stored row agree with what is ever shown.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import UUID, uuid4

from agentos_dashboard.core import DashboardError, utc_now
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.services.audit import record_audit_event
from agentos_dashboard.storage.db import IdempotencyConflict, canonical_request_hash

__all__ = [
    "InvalidNotePayload",
    "UserNote",
    "create_note",
    "get_note_by_token",
    "list_notes",
]


class InvalidNotePayload(DashboardError):
    """A `create_note` field failed validation before any write occurred."""


@dataclass(frozen=True)
class UserNote:
    uuid: str
    client_token: str | None
    request_hash: str
    target_ref: str
    text: str
    created_at: str


def _row_to_note(row: Any) -> UserNote:
    return UserNote(
        uuid=row["uuid"],
        client_token=row["client_token"],
        request_hash=row["request_hash"],
        target_ref=row["target_ref"],
        text=row["text"],
        created_at=row["created_at"],
    )


def get_note_by_token(conn: Connection, client_token: str) -> UserNote | None:
    row = conn.execute(
        "SELECT uuid, client_token, request_hash, target_ref, text, created_at FROM user_notes "
        "WHERE client_token = ?",
        (client_token,),
    ).fetchone()
    return _row_to_note(row) if row is not None else None


def list_notes(
    conn: Connection,
    *,
    target_ref: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[UserNote, ...]:
    if limit < 1 or limit > 200 or offset < 0:
        raise ValueError("note pagination must use limit 1..200 and offset >= 0")
    if target_ref is None:
        rows = conn.execute(
            "SELECT uuid, client_token, request_hash, target_ref, text, created_at FROM user_notes "
            "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT uuid, client_token, request_hash, target_ref, text, created_at FROM user_notes "
            "WHERE target_ref = ? ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (target_ref, limit, offset),
        ).fetchall()
    return tuple(_row_to_note(row) for row in rows)


def create_note(
    conn: Connection,
    audit_log_path: Path,
    *,
    target_ref: str,
    text: str,
    client_token: str,
    now: Callable[[], datetime] = utc_now,
) -> UserNote:
    """Create one `UserNote`, or return the existing one for a replayed `client_token`
    unchanged (SC-23)."""
    if not target_ref.strip():
        raise InvalidNotePayload("target_ref must not be empty")
    if not text.strip():
        raise InvalidNotePayload("text must not be empty")
    try:
        client_token = str(UUID(client_token))
    except ValueError as exc:
        raise InvalidNotePayload("client_token must be a UUID") from exc
    target_ref = redact_secrets(target_ref)
    text = redact_secrets(text)
    request_hash = canonical_request_hash({"target_ref": target_ref, "text": text})

    existing = get_note_by_token(conn, client_token)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflict("client_token was already used for a different note payload")
        return existing

    note_uuid = str(uuid4())
    created_at = now().isoformat()
    inserted = conn.execute(
        "INSERT OR IGNORE INTO user_notes "
        "(uuid, client_token, request_hash, target_ref, text, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (note_uuid, client_token, request_hash, target_ref, text, created_at),
    )
    if inserted.rowcount == 0:
        concurrent = get_note_by_token(conn, client_token)
        assert concurrent is not None
        if concurrent.request_hash != request_hash:
            raise IdempotencyConflict("client_token was already used for a different note payload")
        return concurrent
    record_audit_event(
        conn,
        audit_log_path,
        kind="note_created",
        payload={"note_uuid": note_uuid, "request_hash": request_hash},
    )
    row = conn.execute(
        "SELECT uuid, client_token, request_hash, target_ref, text, created_at "
        "FROM user_notes WHERE uuid = ?",
        (note_uuid,),
    ).fetchone()
    assert row is not None
    return _row_to_note(row)
