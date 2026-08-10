"""`services.notes`: EN-29 `UserNote` creation and idempotent replay."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from agentos_dashboard.services.notes import InvalidNotePayload, create_note, list_notes
from agentos_dashboard.storage.db import DashboardDatabase, IdempotencyConflict


def test_create_note_persists_fields(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        note = create_note(
            conn,
            database.audit_log_path,
            target_ref="run:abc",
            text="hello",
            client_token="11111111-1111-4111-8111-111111111111",
        )
    assert note.target_ref == "run:abc"
    assert note.text == "hello"


def test_create_note_redacts_secret_shaped_text_before_storing(workspace: Path) -> None:
    """SC-09: a pasted credential must not persist in `dashboard.db` at all, so a later replay
    with the same client_token still matches on the *redacted* payload."""
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        note = create_note(
            conn,
            database.audit_log_path,
            target_ref="run:abc",
            text="see api_key=abcd1234efgh5678wxyz for context",
            client_token="11111111-1111-4111-8111-111111111112",
        )
    assert "abcd1234efgh5678wxyz" not in note.text
    assert "[REDACTED]" in note.text
    with database.connection() as conn:
        row = conn.execute("SELECT text FROM user_notes WHERE uuid = ?", (note.uuid,)).fetchone()
    assert "abcd1234efgh5678wxyz" not in row["text"]


@pytest.mark.parametrize("target_ref,text", [("", "hello"), ("run:abc", "   ")])
def test_create_note_rejects_empty_fields(workspace: Path, target_ref: str, text: str) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn, pytest.raises(InvalidNotePayload):
        create_note(
            conn,
            database.audit_log_path,
            target_ref=target_ref,
            text=text,
            client_token="22222222-2222-4222-8222-222222222222",
        )


def test_create_note_idempotent_replay_returns_original(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    token = "33333333-3333-4333-8333-333333333333"
    with database.connection() as conn:
        first = create_note(
            conn, database.audit_log_path, target_ref="run:a", text="first", client_token=token
        )
        second = create_note(
            conn, database.audit_log_path, target_ref="run:a", text="first", client_token=token
        )
    assert first.uuid == second.uuid
    assert second.target_ref == "run:a"
    assert second.text == "first"
    with database.connection() as conn, pytest.raises(IdempotencyConflict):
        create_note(
            conn,
            database.audit_log_path,
            target_ref="run:b",
            text="different",
            client_token=token,
        )


def test_list_notes_filters_by_target_ref(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        create_note(
            conn,
            database.audit_log_path,
            target_ref="run:a",
            text="a",
            client_token="44444444-4444-4444-8444-444444444444",
        )
        create_note(
            conn,
            database.audit_log_path,
            target_ref="run:b",
            text="b",
            client_token="55555555-5555-4555-8555-555555555555",
        )
        only_a = list_notes(conn, target_ref="run:a")
    assert [n.text for n in only_a] == ["a"]


def test_list_notes_is_bounded_and_paginated(workspace: Path) -> None:
    database = DashboardDatabase(workspace)
    with database.connection() as conn:
        for index in range(3):
            create_note(
                conn,
                database.audit_log_path,
                target_ref="run:one",
                text=f"note {index}",
                client_token=f"90000000-0000-4000-8000-{index:012d}",
            )
    with database.connection() as conn:
        first = list_notes(conn, target_ref="run:one", limit=2)
        second = list_notes(conn, target_ref="run:one", limit=2, offset=2)
        with pytest.raises(ValueError):
            list_notes(conn, limit=201)
    assert len(first) == 2
    assert len(second) == 1


def test_concurrent_duplicate_uses_database_uniqueness_and_one_audit_event(
    workspace: Path,
) -> None:
    database = DashboardDatabase(workspace)
    with database.connection():
        pass
    barrier = Barrier(2)
    token = "90000000-0000-4000-8000-000000000031"

    def _create() -> str:
        with database.connection() as conn:
            barrier.wait()
            return create_note(
                conn,
                database.audit_log_path,
                target_ref="run:x",
                text="same",
                client_token=token,
            ).uuid

    with ThreadPoolExecutor(max_workers=2) as executor:
        uuids = list(executor.map(lambda _: _create(), range(2)))
    assert uuids[0] == uuids[1]
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_notes").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1
