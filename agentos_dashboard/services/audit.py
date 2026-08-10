"""EN-26 `AuditEvent` (`DATA_MODEL.md`), the append-only local audit log, and the merged audit
timeline (`API_SPEC.md` EP-16; `PRODUCT_SPEC.md` DR-110/DR-111).

`record_audit_event` is the *only* function in this package that writes to `audit_events`, and it
only ever `INSERT`s — there is no update or delete path here or anywhere else, verified by a
source-scan test (`DATA_MODEL.md` §4, SC-22). Every write also appends one line to the JSONL
mirror (`storage.db.DashboardDatabase.audit_log_path`) so the audit trail survives independently
of `dashboard.db` itself.

`build_audit_timeline` merges this local, non-authoritative stream with the engine's own
persisted Legacy workflow events for one task (`services.legacy_workflow`, TR-09's sibling
authority for task lifecycle rather than ORCH state) when a `task_id` is given. The two sources
carry different notions of order — local events have a wall-clock timestamp, engine events have
only a monotonic `sequence` — so they are never coerced onto one synthetic clock: local entries
sort by `ts` (newest first), repository entries sort by `sequence` (newest first) and are listed
after them, each row honestly labeled with its own `origin`. This is a real, narrower scope than a
single chronologically-interleaved feed, and is a deliberate call: inventing a synthetic timestamp
for events that were never given one would misrepresent event ordering as more precise than the
source data actually supports (`SOURCE_OF_TRUTH.md` TR-02).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import uuid4

from agentos_dashboard.core import utc_now
from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.legacy_workflow import load_legacy_workflow
from agentos_dashboard.storage.db import queue_audit_line

__all__ = [
    "DEFAULT_ACTOR",
    "AuditEvent",
    "AuditMirrorStatus",
    "TimelineEntry",
    "build_audit_timeline",
    "inspect_audit_mirror",
    "list_audit_events",
    "record_audit_event",
]

# `PRODUCT_SPEC.md` §1: single local Human Owner, no accounts/roles — every event this package
# itself records carries this one fixed actor identity.
DEFAULT_ACTOR = "operator"


@dataclass(frozen=True)
class AuditEvent:
    """One row of `audit_events`, exactly as persisted (payload already decoded)."""

    uuid: str
    ts: str
    actor: str
    kind: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class TimelineEntry:
    """One row of the merged audit timeline (EP-16)."""

    origin: str  # "local" | "repository"
    kind: str
    summary: str
    actor: str | None
    ts: str | None
    sequence: int | None
    contradiction: bool
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class AuditMirrorStatus:
    """Detectable DB/JSONL reconciliation state; inspection never edits either source."""

    coherent: bool
    database_events: int
    mirror_events: int
    issues: tuple[str, ...]


def _row_to_event(row: Any) -> AuditEvent:
    return AuditEvent(
        uuid=row["uuid"],
        ts=row["ts"],
        actor=row["actor"],
        kind=row["kind"],
        payload=json.loads(row["payload"]),
    )


def record_audit_event(
    conn: Connection,
    audit_log_path: Path,
    *,
    kind: str,
    payload: Mapping[str, Any],
    actor: str = DEFAULT_ACTOR,
    now: Callable[[], datetime] = utc_now,
) -> AuditEvent:
    """Append one `AuditEvent` to `audit_events` and to the JSONL mirror. Never updates, never
    deletes — the only statement this function issues against `audit_events` is `INSERT`."""
    event = AuditEvent(
        uuid=str(uuid4()), ts=now().isoformat(), actor=actor, kind=kind, payload=payload
    )
    payload_json = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    conn.execute(
        "INSERT INTO audit_events (uuid, ts, actor, kind, payload) VALUES (?, ?, ?, ?, ?)",
        (event.uuid, event.ts, event.actor, event.kind, payload_json),
    )
    line = json.dumps(
        {
            "uuid": event.uuid,
            "ts": event.ts,
            "actor": event.actor,
            "kind": event.kind,
            "payload": dict(payload),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    queue_audit_line(conn, audit_log_path, line)
    return event


_MAX_MIRROR_LINES = 100_000
_MAX_MIRROR_LINE_BYTES = 1_000_000
_MAX_MIRROR_ISSUES = 100


def inspect_audit_mirror(conn: Connection, audit_log_path: Path) -> AuditMirrorStatus:
    """Compare append-only JSONL records with committed DB events.

    Orphan, missing, duplicate, malformed, oversized, and truncated records are reported.  This
    is intentionally observation-only: append-only evidence is never repaired in place.
    """
    rows = conn.execute(
        "SELECT uuid, ts, actor, kind, payload FROM audit_events ORDER BY rowid ASC"
    ).fetchall()
    expected = {
        str(row["uuid"]): {
            "uuid": str(row["uuid"]),
            "ts": str(row["ts"]),
            "actor": str(row["actor"]),
            "kind": str(row["kind"]),
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    }
    if not audit_log_path.exists():
        issues: tuple[str, ...] = (
            ("mirror file missing for committed audit events",) if expected else ()
        )
        return AuditMirrorStatus(not issues, len(expected), 0, issues)

    issues_list: list[str] = []
    seen: dict[str, Mapping[str, Any]] = {}
    line_count = 0

    def add_issue(message: str) -> None:
        if len(issues_list) < _MAX_MIRROR_ISSUES:
            issues_list.append(message)
        elif len(issues_list) == _MAX_MIRROR_ISSUES:
            issues_list.append("additional mirror issues omitted at the response bound")

    try:
        with audit_log_path.open("rb") as handle:
            while raw := handle.readline(_MAX_MIRROR_LINE_BYTES + 1):
                line_count += 1
                if line_count > _MAX_MIRROR_LINES:
                    add_issue("mirror exceeds the inspection line bound")
                    break
                if len(raw) > _MAX_MIRROR_LINE_BYTES:
                    add_issue(f"mirror line {line_count} exceeds the size bound")
                    while raw and not raw.endswith(b"\n"):
                        raw = handle.readline(_MAX_MIRROR_LINE_BYTES + 1)
                    continue
                if not raw.endswith(b"\n"):
                    add_issue(f"mirror line {line_count} is truncated")
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    add_issue(f"mirror line {line_count} is malformed")
                    continue
                if not isinstance(value, dict) or not isinstance(value.get("uuid"), str):
                    add_issue(f"mirror line {line_count} has no valid event uuid")
                    continue
                event_uuid = value["uuid"]
                if event_uuid in seen:
                    add_issue(f"mirror event {event_uuid} is duplicated")
                    continue
                seen[event_uuid] = value
    except OSError:
        add_issue("mirror file is unreadable")

    for event_uuid, value in seen.items():
        if event_uuid not in expected:
            add_issue(f"mirror event {event_uuid} has no committed database row")
        elif value != expected[event_uuid]:
            add_issue(f"mirror event {event_uuid} differs from its database row")
    for event_uuid in expected.keys() - seen.keys():
        add_issue(f"database event {event_uuid} is missing from the mirror")
    issues = tuple(issues_list)
    return AuditMirrorStatus(not issues, len(expected), len(seen), issues)


def list_audit_events(conn: Connection, *, kind: str | None = None) -> tuple[AuditEvent, ...]:
    """All recorded local audit events, newest first."""
    if kind is None:
        rows = conn.execute(
            "SELECT uuid, ts, actor, kind, payload FROM audit_events ORDER BY ts DESC, rowid DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT uuid, ts, actor, kind, payload FROM audit_events "
            "WHERE kind = ? ORDER BY ts DESC, rowid DESC",
            (kind,),
        ).fetchall()
    return tuple(_row_to_event(row) for row in rows)


_LOCAL_SUMMARIES: Mapping[str, str] = {
    "run_created": "manual run record created",
    "approval_created": "draft approval recorded",
    "reconciliation_divergence": (
        "approval target commit does not resolve in Git — divergence finding raised"
    ),
    "finding_created": "draft finding recorded",
    "note_created": "user note recorded",
}


def _local_entry(event: AuditEvent) -> TimelineEntry:
    return TimelineEntry(
        origin="local",
        kind=event.kind,
        summary=_LOCAL_SUMMARIES.get(event.kind, event.kind),
        actor=event.actor,
        ts=event.ts,
        sequence=None,
        contradiction=event.kind == "reconciliation_divergence",
        payload=event.payload,
    )


def _repository_entries(root: RepositoryRoot, task_id: str) -> tuple[TimelineEntry, ...]:
    projection = load_legacy_workflow(root, task_id)
    if not projection.available:
        return ()
    # `WorkflowStage`/`StateAction`/`Verdict` are `Literal[str, ...]` type aliases
    # (`ai_workflow_engine.models`/`workflow.events`), not enum classes — `view.stage`,
    # `view.action`, and `view.verdict` are already plain strings, never `.value`-bearing.
    entries = []
    for view in projection.events:
        entries.append(
            TimelineEntry(
                origin="repository",
                kind="workflow_event",
                summary=f"{view.stage}: {view.action} ({view.outcome})",
                actor="engine",
                ts=None,
                sequence=view.sequence,
                contradiction=False,
                payload={
                    "task_id": task_id,
                    "sequence": view.sequence,
                    "stage": view.stage,
                    "action": view.action,
                    "verdict": view.verdict,
                    "outcome": view.outcome,
                    "parent_digest": view.parent_digest,
                    "head": view.head,
                },
            )
        )
    return tuple(sorted(entries, key=lambda entry: entry.sequence or 0, reverse=True))


def build_audit_timeline(
    root: RepositoryRoot,
    conn: Connection,
    *,
    task_id: str | None = None,
    kind: str | None = None,
    audit_log_path: Path | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[TimelineEntry, ...]:
    """The merged timeline (DR-110): every local audit event, newest first, followed by the
    named task's repository-derived Legacy workflow events (if `task_id` is given and resolvable),
    newest-sequence first. Contradictions (DR-111) are the local `reconciliation_divergence`
    entries, flagged `contradiction=True`."""
    if limit < 1 or limit > 200 or offset < 0:
        raise ValueError("timeline pagination must use limit 1..200 and offset >= 0")
    local_entries = tuple(_local_entry(event) for event in list_audit_events(conn, kind=kind))
    if audit_log_path is not None:
        mirror = inspect_audit_mirror(conn, audit_log_path)
        if not mirror.coherent and kind in (None, "audit_mirror_divergence"):
            local_entries = (
                TimelineEntry(
                    origin="local",
                    kind="audit_mirror_divergence",
                    summary="database and append-only JSONL audit mirror diverge",
                    actor="system",
                    ts=None,
                    sequence=None,
                    contradiction=True,
                    payload={"issues": list(mirror.issues)},
                ),
                *local_entries,
            )
    repository_entries = (
        _repository_entries(root, task_id) if task_id and kind in (None, "workflow_event") else ()
    )
    return (local_entries + repository_entries)[offset : offset + limit]
