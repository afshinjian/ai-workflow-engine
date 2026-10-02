"""AUTO-018: the lifecycle event schema, the chain, the fold and the append protocol.

Contract: `docs/workflow-automation/stage-prompts/AUTO-018.md` sections 5, 6, 7.1-7.3 and 9, and
the section 12 obligations T-EVENT-SCHEMA, T-EVENT-CHAIN, T-EVENT-IDEMPOTENT, T-EVENT-FOLD,
T-EVENT-PROJECTION, T-EVENT-ATOMIC, T-EVENT-TAIL and T-EVENT-LOCK.

Everything here is real: a real repository-scoped artifact root under a redirected `HOME`, a real
`flock`, real exclusive links and atomic replaces, real fsyncs. Faults are injected by replacing
one `os` primitive for one exact target, never by timing.
"""

import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from ai_workflow_engine.milestone_runner.application import revise_record, transition_to
from ai_workflow_engine.milestone_runner.events import (
    EVENTS_DIRECTORY,
    LIFECYCLE_SCHEMA_VERSION,
    PUBLICATION_WITNESS_FILE_NAME,
    ApplicationMutationIncomplete,
    ApplicationStepEvidence,
    EventChainBroken,
    EventConflict,
    EventPins,
    EventStore,
    LifecycleEvent,
    LifecycleEventType,
    LifecycleSchemaUnknown,
    MutationAction,
    MutationCommand,
    PlannedChange,
    ProjectionStatus,
    RunRecordUpdatedPayload,
    StateTransitionedPayload,
    body_digest,
    build_event,
    fold,
    integrity_bytes,
    parse_event_bytes,
    parse_event_file_name,
    projection_bytes,
    record_updates,
)
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    ProviderRole,
    ProviderRunRecord,
    RunRecord,
    RunStatus,
    StopReason,
    VerificationResult,
)
from ai_workflow_engine.milestone_runner.state import (
    PublicationUncertain,
    RunStateStore,
    StatePublicationFailure,
)

IDENTITY = "demo-repo--2059e82cffa9"
RUN_ID = "auto018-20260930T120000Z-0000e018"
STAGE_ID = "AUTO-099"
STAGE_START_ID = "5" * 64
POLICY_DIGEST = "6" * 64
CONTRACT = "7" * 64
BASELINE = "8" * 40
T0 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


def stamp(offset: int = 0) -> str:
    return (T0 + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------
# Fixtures: a real run directory, a real lock, real authority bytes
# --------------------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "worktree"
    root.mkdir()
    return root


@pytest.fixture
def store(home: Path, repository: Path) -> RunStateStore:
    pinned = RunStateStore.pin(repository_id=IDENTITY, run_id=RUN_ID, repository_root=repository)
    authority = pinned.artifact_root / "stage-starts"
    authority.mkdir()
    for suffix, text in (
        (".json", "authorization"),
        (".binding.json", "binding"),
        (".consumed.json", "witness"),
    ):
        (authority / f"{STAGE_START_ID}{suffix}").write_text(f'{{"{text}":1}}', encoding="utf-8")
    pinned.policy_path.write_text('{"policy":1}', encoding="utf-8")
    return pinned


def new_lock(store: RunStateStore) -> RunLock:
    return RunLock(
        run_id=RUN_ID, repository_identity=IDENTITY, artifact_root=store.artifact_root
    ).bind_repository_root(store.repository_root)


HELD: list[RunLock] = []


@pytest.fixture
def lock(store: RunStateStore) -> Iterator[RunLock]:
    held = new_lock(store)
    held.acquire()
    HELD.append(held)
    try:
        yield held
    finally:
        held.release()
        HELD.remove(held)


def release_writers() -> None:
    """End this test's hold, so an unlocked reader's verdict is final rather than contention."""
    for held in HELD:
        held.release()


def pins() -> EventPins:
    return EventPins(
        repository_identity=IDENTITY,
        stage_id=STAGE_ID,
        run_id=RUN_ID,
        contract_sha256=CONTRACT,
        policy_digest=POLICY_DIGEST,
        stage_start_id=STAGE_START_ID,
    )


def idle_record(repository: Path) -> RunRecord:
    return RunRecord(
        schema_version=2,
        run_id=RUN_ID,
        repository_root=str(repository),
        repository_identity=IDENTITY,
        expected_branch="main",
        baseline_sha=BASELINE,
        contract_sha256=CONTRACT,
        workflow_state=RunStatus.IDLE,
        created_at=stamp(),
        updated_at=stamp(),
        policy_digest=POLICY_DIGEST,
        stage_start_id=STAGE_START_ID,
    )


def genesis(store: RunStateStore, lock: RunLock) -> EventStore:
    events = store.begin_lifecycle(lock, pins())
    record = idle_record(store.repository_root)
    events.initialize(record, record.created_at)
    store.record_bootstrap_evidence(events, record.created_at)
    return events


def transition(events: EventStore, target: RunStatus, offset: int, **kwargs: Any) -> RunRecord:
    before = events.record
    after = transition_to(before, target, moment=T0 + timedelta(seconds=offset), **kwargs)
    events.append_transition(before, after, after.updated_at)
    return events.record


def update(events: EventStore, offset: int, **updates: Any) -> RunRecord:
    before = events.record
    after = revise_record(before, moment=T0 + timedelta(seconds=offset), updates=updates)
    events.record_update(before, after, after.updated_at)
    return events.record


def passing(index: int) -> VerificationResult:
    return VerificationResult(
        command=["true", str(index)],
        exit_code=0,
        passed=True,
        duration_ms=1,
        stdout_path=f"transcripts/{index:04d}-20260930T120000Z-verification.stdout.txt",
        stderr_path=f"transcripts/{index:04d}-20260930T120000Z-verification.stderr.txt",
    )


@pytest.fixture
def chain(store: RunStateStore, lock: RunLock) -> EventStore:
    """Seven events: genesis, two bootstrap facts, and four ordinary body events."""
    events = genesis(store, lock)
    transition(events, RunStatus.PREFLIGHT, 1)
    transition(events, RunStatus.IMPLEMENTING, 2, updates={"current_milestone": "AUTO-099-M01"})
    transition(events, RunStatus.FOCUSED_VERIFYING, 3, updates={"changed_paths": ["src/a.py"]})
    update(events, 4, verification_results=[passing(1)])
    return events


def event_files(store: RunStateStore) -> list[Path]:
    return sorted((store.run_directory / EVENTS_DIRECTORY).iterdir())


def tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "run.lock"
    }


# --------------------------------------------------------------------------------------
# T-EVENT-SCHEMA
# --------------------------------------------------------------------------------------


class TestEventSchema:
    """T-EVENT-SCHEMA: every field, type, version and enum boundary, and full digest vectors."""

    def test_the_event_type_vocabulary_is_exactly_the_closed_st02_set(self) -> None:
        assert {member.value for member in LifecycleEventType} == {
            "RUN_INITIALIZED",
            "RUN_BASELINED",
            "STAGE_START_BOUND",
            "POLICY_PUBLISHED",
            "APPLICATION_MUTATION_DECLARED",
            "RUN_RECORD_UPDATED",
            "RECOVERY_LEDGER_APPENDED",
            "OPERATION_REQUEST_CREATED",
            "OPERATION_DISPATCH_INTENT",
            "OPERATION_DISPATCH_RECEIVED",
            "OPERATION_PRE_SPAWN_FAILED",
            "OPERATION_RESULT_RECEIVED",
            "OPERATION_RESULT_VALIDATED",
            "OPERATION_RESULT_ACCEPTED",
            "OPERATION_RESULT_REJECTED",
            "STATE_TRANSITIONED",
        }

    def test_the_envelope_carries_exactly_the_contract_fields(self) -> None:
        assert set(LifecycleEvent.model_fields) == {
            "schema_version",
            "repository_identity",
            "stage_id",
            "run_id",
            "contract_sha256",
            "policy_digest",
            "stage_start_id",
            "sequence",
            "state_version",
            "event_type",
            "recorded_at",
            "payload",
            "payload_digest",
            "prev_event_digest",
            "event_id",
            "mutation_id",
            "mutation_index",
        }

    def test_full_digest_vectors_are_independently_reproducible(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        """payload_digest, event_id and the full-file digest, recomputed without production code."""

        def independent(value: object) -> bytes:
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")

        previous = None
        for path in event_files(store):
            raw = path.read_bytes()
            document = json.loads(raw)
            assert independent(document) == raw, "event bytes are canonical, no trailing newline"
            assert (
                hashlib.sha256(independent(document["payload"])).hexdigest()
                == document["payload_digest"]
            )
            without_id = {key: value for key, value in document.items() if key != "event_id"}
            assert hashlib.sha256(independent(without_id)).hexdigest() == document["event_id"]
            assert document["prev_event_digest"] == previous
            assert document["event_id"] != hashlib.sha256(raw).hexdigest()
            previous = hashlib.sha256(raw).hexdigest()
            assert document["state_version"] == document["sequence"]
            assert path.name == f"{document['sequence']:08d}-{document['event_type']}.json"

    def test_body_digests_include_timestamps(self, repository: Path) -> None:
        record = idle_record(repository)
        later = RunRecord.model_validate({**record.model_dump(), "updated_at": stamp(9)})
        assert body_digest(record) != body_digest(later)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("sequence", True),
            ("sequence", 1.0),
            ("sequence", "1"),
            ("sequence", 0),
            ("sequence", 100_000_000),
            ("state_version", 2),
            ("schema_version", 2),
            ("event_type", "UNKNOWN_EVENT"),
            ("recorded_at", "2026-09-30 12:00:00"),
            ("policy_digest", None),
            ("stage_start_id", "X" * 64),
            ("prev_event_digest", "0" * 64),
            ("mutation_id", "a" * 64),
        ],
    )
    def test_every_boundary_is_refused_on_read(
        self, chain: EventStore, store: RunStateStore, field: str, value: Any
    ) -> None:
        first = event_files(store)[0]
        document = json.loads(first.read_bytes())
        document[field] = value
        payload = (
            integrity_bytes(document)
            if not isinstance(value, float)
            else json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        )
        with pytest.raises((EventChainBroken, LifecycleSchemaUnknown)):
            parse_event_bytes(first.name, payload)

    def test_an_unknown_lifecycle_version_is_its_own_typed_refusal(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        first = event_files(store)[0]
        document = json.loads(first.read_bytes())
        for version in (2, 0, "1", True):
            document["schema_version"] = version
            with pytest.raises(LifecycleSchemaUnknown) as refused:
                parse_event_bytes(first.name, json.dumps(document).encode())
            assert refused.value.stop_reason is StopReason.LIFECYCLE_SCHEMA_UNKNOWN

    def test_duplicate_keys_at_any_depth_are_refused(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        first = event_files(store)[0]
        raw = first.read_bytes()
        nested = raw.replace(b'"origin":', b'"origin":"x","origin":', 1)
        top = raw.replace(b'"run_id":', b'"run_id":"x","run_id":', 1)
        for payload in (nested, top):
            with pytest.raises(EventChainBroken, match=r"duplicate|strict"):
                parse_event_bytes(first.name, payload)

    def test_noncanonical_bytes_and_invalid_utf8_are_refused(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        first = event_files(store)[0]
        raw = first.read_bytes()
        pretty = json.dumps(json.loads(raw), indent=2, sort_keys=True).encode()
        for payload in (raw + b"\n", pretty, b"\xff" + raw[1:]):
            with pytest.raises(EventChainBroken):
                parse_event_bytes(first.name, payload)

    def test_timestamp_tampering_breaks_the_identity(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        path = event_files(store)[3]
        document = json.loads(path.read_bytes())
        document["recorded_at"] = "2026-09-30T12:00:59Z"
        with pytest.raises(EventChainBroken, match="event_id"):
            parse_event_bytes(path.name, integrity_bytes(document))

    def test_a_filename_type_mismatch_is_refused(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        path = event_files(store)[0]
        with pytest.raises(EventChainBroken):
            parse_event_bytes("00000001-RUN_BASELINED.json", path.read_bytes())

    def test_floats_and_surrogates_never_reach_integrity_bytes(self) -> None:
        for value in ({"a": 1.5}, {"a": "\ud800"}, {1: "a"}):
            with pytest.raises(ValueError):
                integrity_bytes(value)


# --------------------------------------------------------------------------------------
# T-EVENT-CHAIN and T-EVENT-TAIL
# --------------------------------------------------------------------------------------


def reload_refuses(store: RunStateStore, match: str = "") -> EventChainBroken:
    release_writers()
    with pytest.raises(EventChainBroken, match=match) as refused:
        store.load()
    assert refused.value.stop_reason is StopReason.EVENT_CHAIN_BROKEN
    assert refused.value.effective_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
    return refused.value


class TestEventChain:
    """T-EVENT-CHAIN: every structural tamper refuses; nothing is truncated or repaired."""

    def test_the_untampered_chain_loads_as_its_fold(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        assert store.load() == chain.record
        assert store.load().workflow_state is RunStatus.FOCUSED_VERIFYING

    @pytest.mark.parametrize("position", [0, 3, -1])
    def test_deleting_one_event_refuses(
        self, chain: EventStore, store: RunStateStore, position: int
    ) -> None:
        event_files(store)[position].unlink()
        reload_refuses(store)

    def test_deleting_every_event_refuses(self, chain: EventStore, store: RunStateStore) -> None:
        for path in event_files(store):
            path.unlink()
        reload_refuses(store)

    def test_deleting_the_whole_events_directory_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        for path in event_files(store):
            path.unlink()
        (store.run_directory / EVENTS_DIRECTORY).rmdir()
        reload_refuses(store)

    def test_a_version_3_record_without_events_or_witness_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        for path in event_files(store):
            path.unlink()
        (store.run_directory / EVENTS_DIRECTORY).rmdir()
        (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).unlink()
        reload_refuses(store, "event-backed record")

    def test_reordering_two_events_refuses(self, chain: EventStore, store: RunStateStore) -> None:
        files = event_files(store)
        third, fourth = files[3], files[4]
        a, b = third.read_bytes(), fourth.read_bytes()
        third.write_bytes(b)
        fourth.write_bytes(a)
        reload_refuses(store)

    def test_renaming_an_event_refuses(self, chain: EventStore, store: RunStateStore) -> None:
        path = event_files(store)[4]
        path.rename(path.with_name(path.name.replace("STATE_TRANSITIONED", "RUN_RECORD_UPDATED")))
        reload_refuses(store)

    def test_editing_an_event_payload_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        path = event_files(store)[5]
        path.write_bytes(path.read_bytes().replace(b"src/a.py", b"src/b.py"))
        reload_refuses(store)

    def test_a_duplicate_sequence_under_another_type_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        path = event_files(store)[4]
        twin = path.with_name(f"{path.name[:8]}-RUN_RECORD_UPDATED.json")
        twin.write_bytes(path.read_bytes())
        reload_refuses(store, "two event files claim one sequence")

    def test_an_unknown_entry_in_the_events_directory_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        (store.run_directory / EVENTS_DIRECTORY / "notes.txt").write_text("x")
        reload_refuses(store, "unknown entry")

    def test_an_owned_temporary_file_is_ignored(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        (store.run_directory / EVENTS_DIRECTORY / ".milestone-runner-tmp-abc").write_text("x")
        assert store.load() == chain.record

    def test_a_subdirectory_at_a_canonical_name_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        (store.run_directory / EVENTS_DIRECTORY / "00000099-RUN_RECORD_UPDATED.json").mkdir()
        reload_refuses(store)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("run_id", "auto018-foreign-run"),
            ("policy_digest", "9" * 64),
            ("contract_sha256", "9" * 64),
            ("stage_start_id", "9" * 64),
        ],
    )
    def test_a_foreign_event_refuses_even_when_internally_consistent(
        self,
        chain: EventStore,
        store: RunStateStore,
        field: str,
        value: str,
    ) -> None:
        """Re-sign the last event under foreign pins: its own digests verify, the chain does not."""
        last_event, _ = chain.events[-1]
        previous_digest = chain.events[-2][1]
        foreign = EventPins.model_validate({**pins().model_dump(), field: value})
        forged = build_event(
            pins=foreign,
            sequence=last_event.sequence,
            event_type=last_event.event_type,
            recorded_at=last_event.recorded_at,
            payload=last_event.payload,
            prev_event_digest=previous_digest,
        )
        event_files(store)[-1].write_bytes(forged.canonical_bytes())
        reload_refuses(store)

    def test_a_broken_predecessor_link_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        last_event, _ = chain.events[-1]
        forged = build_event(
            pins=pins(),
            sequence=last_event.sequence,
            event_type=last_event.event_type,
            recorded_at=last_event.recorded_at,
            payload=last_event.payload,
            prev_event_digest="0" * 64,
        )
        event_files(store)[-1].write_bytes(forged.canonical_bytes())
        reload_refuses(store, "chain")

    def test_a_witness_naming_another_event_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        witness = store.run_directory / PUBLICATION_WITNESS_FILE_NAME
        document = json.loads(witness.read_bytes())
        document["event_id"] = "0" * 64
        witness.write_bytes(integrity_bytes(document))
        reload_refuses(store, "witness")

    def test_a_missing_witness_with_existing_events_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).unlink()
        reload_refuses(store, "witness is mandatory")

    def test_a_regressed_witness_refuses(self, chain: EventStore, store: RunStateStore) -> None:
        witness = store.run_directory / PUBLICATION_WITNESS_FILE_NAME
        document = json.loads(witness.read_bytes())
        earlier, earlier_digest = chain.events[-3]
        document.update(
            sequence=earlier.sequence, event_id=earlier.event_id, event_sha256=earlier_digest
        )
        document["prev_event_digest"] = earlier.prev_event_digest
        witness.write_bytes(integrity_bytes(document))
        reload_refuses(store, "witness")


class TestUnlockedReaders:
    """Section 6: an unlocked reader never mistakes a live writer's view for corruption."""

    def test_an_inconsistent_view_under_a_live_writer_is_retryable_contention(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        from ai_workflow_engine.milestone_runner.state import LifecycleReadContention

        # The writer's witness names an event it has not linked yet -- as between steps 3 and 4.
        last, _ = chain.events[-1]
        (store.run_directory / EVENTS_DIRECTORY / last.file_name).unlink()
        before = tree_snapshot(store.run_directory)
        with pytest.raises(LifecycleReadContention) as refused:
            store.load()
        assert refused.value.stop_reason is StopReason.LOCK_CONTENTION
        assert tree_snapshot(store.run_directory) == before

    def test_the_same_view_without_a_writer_is_a_stable_verdict(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        last, _ = chain.events[-1]
        (store.run_directory / EVENTS_DIRECTORY / last.file_name).unlink()
        reload_refuses(store, "missing")


class TestEventTail:
    """T-EVENT-TAIL: the witness detects a lost suffix even with a deliberately stale cache."""

    def test_deleting_the_last_event_with_a_stale_projection_is_detected(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        last, _ = chain.events[-1]
        previous, _ = chain.events[-2]
        # A projection describing the plausible shorter prefix, byte-exact for it.
        store.state_path.write_bytes(
            projection_bytes(
                fold(chain.events[:-1]).record,
                state_version=previous.sequence,
                last_event_id=previous.event_id,
            )
        )
        (store.run_directory / EVENTS_DIRECTORY / last.file_name).unlink()
        refused = reload_refuses(store, "missing")
        assert "lost" in str(refused)

    def test_no_fallback_to_the_shorter_prefix_even_under_the_lock(
        self, chain: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        last, _ = chain.events[-1]
        (store.run_directory / EVENTS_DIRECTORY / last.file_name).unlink()
        before = tree_snapshot(store.run_directory)
        with pytest.raises(EventChainBroken):
            store.open_lifecycle(lock)
        assert tree_snapshot(store.run_directory) == before


# --------------------------------------------------------------------------------------
# T-EVENT-IDEMPOTENT
# --------------------------------------------------------------------------------------


class TestEventIdempotence:
    """T-EVENT-IDEMPOTENT: exact duplicates change nothing; conflicting reuse refuses."""

    def test_an_exact_duplicate_changes_no_byte_mtime_or_counter(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        before = tree_snapshot(store.run_directory)
        envelope, digest = chain.events[4]
        appended = chain.publish_envelope(envelope)
        assert appended.duplicate and appended.sha256 == digest
        assert tree_snapshot(store.run_directory) == before
        assert chain.require_state().sequence == 7

    def test_the_same_sequence_with_other_content_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        envelope, _ = chain.events[4]
        other = build_event(
            pins=pins(),
            sequence=envelope.sequence,
            event_type=envelope.event_type,
            recorded_at="2026-09-30T13:00:00Z",
            payload=envelope.payload,
            prev_event_digest=envelope.prev_event_digest,
        )
        before = tree_snapshot(store.run_directory)
        with pytest.raises(EventConflict) as refused:
            chain.publish_envelope(other)
        assert refused.value.stop_reason is StopReason.EVENT_CONFLICT
        assert tree_snapshot(store.run_directory) == before

    def test_a_retry_with_a_new_clock_reading_is_not_a_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        before = chain.record
        after = revise_record(
            before, moment=T0 + timedelta(seconds=30), updates={"changed_paths": []}
        )
        first = chain.record_update(before, after, after.updated_at)
        with pytest.raises(EventConflict):
            # The original envelope, re-sent, is a duplicate; a re-computed one at a new tip is a
            # stale append against a record that is no longer the verified tip.
            chain.record_update(before, after, after.updated_at)
        assert chain.publish_envelope(first.event).duplicate

    def test_a_later_hold_confirms_before_a_duplicate_is_reported_durable(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Visible identical bytes are not durable success until this hold's barriers succeed."""
        envelope, _ = chain.events[4]
        lock.release()
        later = new_lock(store)
        later.acquire()
        try:
            real = os.fsync
            fsynced: list[tuple[int, int]] = []

            def failing(descriptor: int) -> None:
                raise OSError(5, "Input/output error")

            monkeypatch.setattr(os, "fsync", failing)
            before = tree_snapshot(store.run_directory)
            with pytest.raises(PublicationUncertain) as uncertain:
                store.open_lifecycle(later)
            assert uncertain.value.stop_reason is StopReason.PUBLICATION_UNCERTAIN
            assert tree_snapshot(store.run_directory) == before

            def recording(descriptor: int) -> None:
                status = os.fstat(descriptor)
                fsynced.append((status.st_dev, status.st_ino))
                real(descriptor)

            monkeypatch.setattr(os, "fsync", recording)
            reopened, _ = store.open_lifecycle(later)
            event_path = store.run_directory / EVENTS_DIRECTORY / envelope.file_name
            for path in (event_path, event_path.parent, store.run_directory, store.artifact_root):
                status = path.stat()
                assert (status.st_dev, status.st_ino) in fsynced, path
            assert reopened.publish_envelope(envelope).duplicate
            assert tree_snapshot(store.run_directory) == before
        finally:
            later.release()


# --------------------------------------------------------------------------------------
# T-EVENT-FOLD
# --------------------------------------------------------------------------------------


class TestFold:
    """T-EVENT-FOLD: deterministic prefixes; illegal updates refuse despite valid hashes."""

    def test_every_prefix_folds_deterministically(self, chain: EventStore) -> None:
        events = chain.events
        for length in range(1, len(events) + 1):
            first = fold(events[:length])
            second = fold(events[:length])
            assert first.record == second.record
            assert first.body_digest == second.body_digest
            assert first.sequence == length

    def _append_forged(
        self, chain: EventStore, event_type: LifecycleEventType, payload: Any
    ) -> None:
        state = chain.require_state()
        envelope = build_event(
            pins=pins(),
            sequence=state.sequence + 1,
            event_type=event_type,
            recorded_at=stamp(50),
            payload=payload,
            prev_event_digest=state.event_sha256,
        )
        chain.publish_envelope(envelope)

    def test_an_illegal_transition_refuses_even_with_valid_digests(self, chain: EventStore) -> None:
        before = chain.record
        after = RunRecord.model_validate(
            {**before.model_dump(), "workflow_state": RunStatus.DONE, "updated_at": stamp(50)}
        )
        payload = StateTransitionedPayload(
            event_type="STATE_TRANSITIONED",
            before_body_digest=body_digest(before),
            after_body_digest=body_digest(after),
            from_state=before.workflow_state,
            to_state=RunStatus.DONE,
            updates=record_updates(before, after).model_copy(update={}),
        )
        with pytest.raises(EventConflict, match="append_transition"):
            self._append_forged(chain, LifecycleEventType.STATE_TRANSITIONED, payload)
        with pytest.raises(EventChainBroken, match="not allowed"):
            chain.append_transition(before, after, stamp(50))

    def test_a_generic_update_cannot_move_workflow_state(self, chain: EventStore) -> None:
        before = chain.record
        after = RunRecord.model_validate(
            {**before.model_dump(), "workflow_state": RunStatus.MILESTONE_COMPLETE}
        )
        with pytest.raises(EventConflict, match="never changes workflow_state"):
            chain.record_update(before, after, stamp(50))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("successful_review_rounds", 1),
            ("correction_round", 1),
            ("closure_round", 1),
            ("provider_failure_count", 1),
            ("review_attempts", 2),
        ],
    )
    def test_counters_cannot_be_applied_through_a_second_route(
        self, chain: EventStore, field: str, value: int
    ) -> None:
        before = chain.record
        after = revise_record(before, moment=T0 + timedelta(seconds=50), updates={field: value})
        with pytest.raises(EventChainBroken):
            chain.record_update(before, after, after.updated_at)

    def test_review_attempts_moves_by_exactly_one(self, chain: EventStore) -> None:
        before = chain.record
        after = revise_record(
            before, moment=T0 + timedelta(seconds=50), updates={"review_attempts": 1}
        )
        chain.record_update(before, after, after.updated_at)
        assert chain.record.review_attempts == 1

    def test_blocking_findings_never_move_through_a_generic_update(self, chain: EventStore) -> None:
        from ai_workflow_engine.milestone_runner.models import Finding, FindingSeverity

        before = chain.record
        finding = Finding(
            finding_id="R-1", severity=FindingSeverity.HIGH, title="A blocker", summary="Blocks."
        )
        after = revise_record(
            before, moment=T0 + timedelta(seconds=50), updates={"blocking_findings": [finding]}
        )
        with pytest.raises(EventChainBroken, match="cannot assign"):
            chain.record_update(before, after, after.updated_at)

    def test_an_append_only_list_cannot_be_rewritten(self, chain: EventStore) -> None:
        before = chain.record
        after = revise_record(
            before, moment=T0 + timedelta(seconds=50), updates={"verification_results": []}
        )
        with pytest.raises(EventChainBroken, match="append-only"):
            chain.record_update(before, after, after.updated_at)

    def test_a_ledger_append_outside_a_declared_recovery_refuses(self, chain: EventStore) -> None:
        from ai_workflow_engine.milestone_runner.events import RecoveryLedgerAppendedPayload

        payload = RecoveryLedgerAppendedPayload.model_construct()
        with pytest.raises((EventChainBroken, EventConflict, Exception)):
            self._append_forged(chain, LifecycleEventType.RECOVERY_LEDGER_APPENDED, payload)

    def test_a_before_digest_that_is_not_the_tip_refuses(self, chain: EventStore) -> None:
        before = chain.record
        after = revise_record(
            before, moment=T0 + timedelta(seconds=50), updates={"changed_paths": []}
        )
        payload = RunRecordUpdatedPayload(
            event_type="RUN_RECORD_UPDATED",
            before_body_digest="0" * 64,
            after_body_digest=body_digest(after),
            updates=record_updates(before, after),
        )
        with pytest.raises(EventChainBroken, match="before-body"):
            self._append_forged(chain, LifecycleEventType.RUN_RECORD_UPDATED, payload)

    def test_a_completed_provider_row_without_transcript_evidence_refuses(
        self, chain: EventStore
    ) -> None:
        before = chain.record
        row = ProviderRunRecord(
            sequence=1,
            role=ProviderRole.IMPLEMENTATION,
            provider="fake",
            milestone_id="AUTO-099-M01",
            started_at=stamp(40),
            completed_at=stamp(41),
            duration_ms=1,
            exit_code=0,
            prompt_path="transcripts/0001-20260930T120040Z-fake-implementation.prompt.md",
            stdout_path="transcripts/0001-20260930T120040Z-fake-implementation.stdout.txt",
            stderr_path="transcripts/0001-20260930T120040Z-fake-implementation.stderr.txt",
        )
        after = revise_record(
            before, moment=T0 + timedelta(seconds=50), updates={"provider_runs": [row]}
        )
        with pytest.raises(EventChainBroken, match="digest-bound references"):
            chain.record_update(before, after, after.updated_at)


# --------------------------------------------------------------------------------------
# T-EVENT-PROJECTION
# --------------------------------------------------------------------------------------


class TestProjection:
    """T-EVENT-PROJECTION: the cache is repaired only under the lock, never trusted over events."""

    def test_the_published_projection_is_the_fold_byte_for_byte(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        state = fold(chain.events)
        assert store.state_path.read_bytes() == projection_bytes(
            state.record, state_version=state.sequence, last_event_id=state.event_id
        )
        document = json.loads(store.state_path.read_bytes())
        assert document["schema_version"] == 3
        assert document["state_version"] == 7

    @pytest.mark.parametrize("damage", ["missing", "stale", "corrupt"])
    def test_a_read_only_load_returns_the_fold_and_writes_nothing(
        self, chain: EventStore, store: RunStateStore, damage: str
    ) -> None:
        self._damage(chain, store, damage)
        before = tree_snapshot(store.run_directory)
        view = store.load_lifecycle()
        assert view.record == chain.record
        assert (
            view.projection
            is {
                "missing": ProjectionStatus.MISSING,
                "stale": ProjectionStatus.STALE,
                "corrupt": ProjectionStatus.DAMAGED,
            }[damage]
        )
        assert tree_snapshot(store.run_directory) == before

    @pytest.mark.parametrize("damage", ["missing", "stale", "corrupt"])
    def test_a_locked_open_repairs_from_the_verified_chain_and_spawns_nothing(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        damage: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import subprocess

        self._damage(chain, store, damage)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("repair spawned"))
        events_before = [path.read_bytes() for path in event_files(store)]
        _, view = store.open_lifecycle(lock)
        state = fold(chain.events)
        assert store.state_path.read_bytes() == projection_bytes(
            state.record, state_version=state.sequence, last_event_id=state.event_id
        )
        assert [path.read_bytes() for path in event_files(store)] == events_before
        assert view.record == chain.record

    def test_a_projection_ahead_of_the_chain_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        document = json.loads(store.state_path.read_bytes())
        document["state_version"] = 99
        store.state_path.write_bytes(integrity_bytes(document))
        reload_refuses(store, "later than the verified chain")

    def test_a_state_only_write_cannot_advance_an_event_backed_run(
        self, chain: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        with pytest.raises(StatePublicationFailure, match="event-backed"):
            store.publish(chain.record, lock=lock)

    @staticmethod
    def _damage(chain: EventStore, store: RunStateStore, damage: str) -> None:
        if damage == "missing":
            store.state_path.unlink()
        elif damage == "stale":
            state = fold(chain.events[:-1])
            store.state_path.write_bytes(
                projection_bytes(
                    state.record, state_version=state.sequence, last_event_id=state.event_id
                )
            )
        else:
            store.state_path.write_bytes(b"{not json")


# --------------------------------------------------------------------------------------
# T-EVENT-ATOMIC
# --------------------------------------------------------------------------------------


def _target_is(descriptor: int, path: Path) -> bool:
    try:
        return os.fstat(descriptor).st_ino == path.stat().st_ino
    except OSError:
        return False


class TestAppendAtomicity:
    """T-EVENT-ATOMIC: a fault at each step leaves canonical bytes, a committed tip, a typed
    refusal and no subsequent effect."""

    def _next(self, chain: EventStore) -> Callable[[], Any]:
        before = chain.record
        after = revise_record(
            before, moment=T0 + timedelta(seconds=60), updates={"changed_paths": []}
        )
        return lambda: chain.record_update(before, after, after.updated_at)

    def _names(self, store: RunStateStore) -> list[str]:
        return [path.name for path in event_files(store)]

    def test_failure_writing_the_witness_temporary_publishes_nothing(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = self._names(store)
        witness = (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).read_bytes()
        real = os.write

        def failing(descriptor: int, data: Any) -> int:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "write", failing)
        with pytest.raises(StatePublicationFailure):
            self._next(chain)()
        monkeypatch.setattr(os, "write", real)
        assert self._names(store) == names
        assert (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).read_bytes() == witness
        assert not [
            p for p in store.run_directory.iterdir() if p.name.startswith(".milestone-runner-tmp-")
        ]
        assert store.load() == chain.record

    def test_failure_at_the_witness_replace_publishes_nothing(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = self._names(store)

        def failing(*args: Any, **kwargs: Any) -> None:
            raise OSError(5, "Input/output error")

        with monkeypatch.context() as fault:
            fault.setattr(os, "replace", failing)
            with pytest.raises(StatePublicationFailure):
                self._next(chain)()
        assert self._names(store) == names
        assert store.load() == chain.record

    def test_failure_at_the_event_link_leaves_an_incomplete_publication_that_stops_on_load(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = self._names(store)

        def failing(*args: Any, **kwargs: Any) -> None:
            raise OSError(5, "Input/output error")

        with monkeypatch.context() as fault:
            fault.setattr(os, "link", failing)
            with pytest.raises(StatePublicationFailure):
                self._next(chain)()
        assert self._names(store) == names
        # The witness names an event that never became canonical: the load stops, and ST-02
        # neither invents nor auto-appends the missing event.
        reload_refuses(store, "missing")

    def test_a_failed_event_directory_fsync_is_uncertain_not_a_no_effect_failure(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events_directory = store.run_directory / EVENTS_DIRECTORY
        real = os.fsync
        armed = {"after_link": False}
        real_link = os.link

        def link(*args: Any, **kwargs: Any) -> None:
            real_link(*args, **kwargs)
            armed["after_link"] = True

        def fsync(descriptor: int) -> None:
            if armed["after_link"] and _target_is(descriptor, events_directory):
                raise OSError(5, "Input/output error")
            real(descriptor)

        with monkeypatch.context() as fault:
            fault.setattr(os, "link", link)
            fault.setattr(os, "fsync", fsync)
            with pytest.raises(PublicationUncertain) as uncertain:
                self._next(chain)()
            assert uncertain.value.stop_reason is StopReason.PUBLICATION_UNCERTAIN
            assert uncertain.value.barrier == "directory_fsync"
        # The bytes are visible and intact; they are evidence, not deleted and not "durable".
        assert len(self._names(store)) == 8
        assert store.load().changed_paths == []

    def test_a_failed_projection_replace_leaves_a_committed_event(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = os.replace

        def replace(source: Any, destination: Any, **kwargs: Any) -> None:
            if destination == "state.json":
                raise OSError(5, "Input/output error")
            real(source, destination, **kwargs)

        with monkeypatch.context() as fault:
            fault.setattr(os, "replace", replace)
            with pytest.raises(StatePublicationFailure):
                self._next(chain)()
        view = store.load_lifecycle()
        assert view.state.sequence == 8
        assert view.projection is ProjectionStatus.STALE
        assert view.record.changed_paths == []

    def test_a_failed_file_fsync_before_visibility_is_not_published(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = self._names(store)
        real = os.fsync

        def fsync(descriptor: int) -> None:
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError(5, "Input/output error")
            real(descriptor)

        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", fsync)
            with pytest.raises(StatePublicationFailure):
                self._next(chain)()
        assert self._names(store) == names
        assert store.load() == chain.record


# --------------------------------------------------------------------------------------
# T-EVENT-LOCK
# --------------------------------------------------------------------------------------


class TestAppendRequiresTheLock:
    """T-EVENT-LOCK: no write without the correct held lock; one appender per sequence."""

    def test_an_unheld_lock_writes_nothing(self, store: RunStateStore) -> None:
        unheld = new_lock(store)
        with pytest.raises(Exception, match="not held"):
            store.begin_lifecycle(unheld, pins())
        assert not store.lifecycle_present()

    def test_a_released_hold_cannot_append(
        self, chain: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        before = tree_snapshot(store.run_directory)
        lock.release()
        with pytest.raises(Exception, match="not held"):
            TestAppendAtomicity()._next(chain)()
        assert tree_snapshot(store.run_directory) == before

    def test_two_appenders_cannot_allocate_one_sequence(
        self, chain: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        second, _ = store.open_lifecycle(lock)
        TestAppendAtomicity()._next(chain)()
        # The second view is now stale: its expected tip no longer matches the chain.
        before = second.record
        after = revise_record(
            before, moment=T0 + timedelta(seconds=70), updates={"changed_paths": ["x"]}
        )
        with pytest.raises((EventChainBroken, EventConflict)):
            second.record_update(before, after, after.updated_at)
        assert len(event_files(store)) == 8

    def test_a_stale_expected_tip_refuses(self, chain: EventStore) -> None:
        state = chain.require_state()
        stale = build_event(
            pins=pins(),
            sequence=state.sequence + 2,
            event_type=LifecycleEventType.RUN_RECORD_UPDATED,
            recorded_at=stamp(70),
            payload=chain.events[-1][0].payload,
            prev_event_digest=state.event_sha256,
        )
        with pytest.raises(EventConflict, match="stale expected tip"):
            chain.publish_envelope(stale)


# --------------------------------------------------------------------------------------
# Section 6.1 at the store level
# --------------------------------------------------------------------------------------


class TestDeclarationsAtTheStore:
    """The declaration rule, independent of any application command."""

    def _declare(self, chain: EventStore) -> tuple[Any, list[PlannedChange]]:
        before = chain.record
        middle = revise_record(
            before, moment=T0 + timedelta(seconds=80), updates={"changed_paths": ["x"]}
        )
        after = transition_to(middle, RunStatus.MILESTONE_FAILED, moment=T0 + timedelta(seconds=80))
        changes = [
            PlannedChange(LifecycleEventType.RUN_RECORD_UPDATED, before, middle, middle.updated_at),
            PlannedChange(LifecycleEventType.STATE_TRANSITIONED, middle, after, after.updated_at),
        ]
        declaration = chain.declare(
            action=MutationAction.APPLICATION_STEP,
            command=MutationCommand.RESUME,
            initiated_at=middle.updated_at,
            evidence=ApplicationStepEvidence(kind="APPLICATION_STEP", description="test step"),
            changes=changes,
        )
        return declaration, changes

    def test_a_declaration_applies_none_of_its_effects(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        before = chain.record
        declaration, _ = self._declare(chain)
        assert chain.record == before
        view = store.load_lifecycle()
        assert view.record == before
        assert view.incomplete is not None
        assert view.incomplete.applied_prefix_length == 0
        assert view.incomplete.declaration == declaration

    def test_nothing_else_is_appended_while_a_declaration_is_incomplete(
        self, chain: EventStore
    ) -> None:
        declaration, _ = self._declare(chain)
        chain.append_constituent(declaration, 1)
        with pytest.raises(ApplicationMutationIncomplete):
            TestAppendAtomicity()._next(chain)()

    def test_a_transition_constituent_is_never_emitted_generically(self, chain: EventStore) -> None:
        declaration, _ = self._declare(chain)
        chain.append_constituent(declaration, 1)
        with pytest.raises(EventConflict, match="append_transition"):
            chain.append_constituent(declaration, 2)

    def test_the_complete_mutation_folds_and_closes(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        declaration, changes = self._declare(chain)
        chain.append_constituent(declaration, 1)
        chain.append_transition(
            changes[1].before,
            changes[1].after,
            changes[1].recorded_at,
            constituent=(declaration, 2),
        )
        view = store.load_lifecycle()
        assert view.incomplete is None
        assert view.record.workflow_state is RunStatus.MILESTONE_FAILED

    def test_an_oversize_manifest_is_refused_before_any_effect(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        before = chain.record
        wide = [
            VerificationResult(
                command=["x" * 4_000, str(index)],
                exit_code=0,
                passed=True,
                duration_ms=1,
                stdout_path="transcripts/0001-20260930T120000Z-verification.stdout.txt",
                stderr_path="transcripts/0001-20260930T120000Z-verification.stderr.txt",
            )
            for index in range(5_000)
        ]
        huge = revise_record(
            before, moment=T0 + timedelta(seconds=90), updates={"verification_results": wide}
        )
        after = transition_to(huge, RunStatus.MILESTONE_FAILED, moment=T0 + timedelta(seconds=90))
        names = [path.name for path in event_files(store)]
        with pytest.raises(EventConflict, match="ceiling"):
            chain.declare(
                action=MutationAction.APPLICATION_STEP,
                command=MutationCommand.RESUME,
                initiated_at=huge.updated_at,
                evidence=ApplicationStepEvidence(kind="APPLICATION_STEP", description="huge"),
                changes=[
                    PlannedChange(
                        LifecycleEventType.RUN_RECORD_UPDATED, before, huge, huge.updated_at
                    ),
                    PlannedChange(
                        LifecycleEventType.STATE_TRANSITIONED, huge, after, after.updated_at
                    ),
                ],
            )
        assert [path.name for path in event_files(store)] == names

    def test_the_lifecycle_schema_version_constant_is_one(self) -> None:
        assert LIFECYCLE_SCHEMA_VERSION == 1


class TestReferenceClassification:
    """T-PROSPECTIVE-REFERENCE and T-HOSTILE-IO at the schema level."""

    @pytest.mark.parametrize(
        "kind, path",
        [
            ("TRANSCRIPT", "transcripts/../state.json"),
            ("TRANSCRIPT", "../transcripts/0001-20260930T120000Z-fake.stdout.txt"),
            ("TRANSCRIPT", "/abs/transcripts/0001-20260930T120000Z-fake.stdout.txt"),
            ("OPERATION_REQUEST", "operations/" + "a" * 64 + "/../request.json"),
            ("POLICY", "stage-starts/policy.json"),
            ("STAGE_START_BINDING", "stage-starts/../" + "5" * 64 + ".binding.json"),
        ],
    )
    def test_a_traversal_or_misfiled_reference_is_unrepresentable(
        self, kind: str, path: str
    ) -> None:
        from pydantic import ValidationError

        from ai_workflow_engine.milestone_runner.events import DurableEvidenceReference

        root = "REPOSITORY" if kind.startswith("STAGE_START") else "RUN"
        with pytest.raises(ValidationError):
            DurableEvidenceReference.model_validate_json(
                json.dumps(
                    {"kind": kind, "root": root, "path": path, "sha256": "a" * 64, "byte_count": 1}
                )
            )

    def test_a_manifest_carries_prospective_fields_and_a_durable_reference_distinctly(
        self, chain: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        """A declared mutation completing row 1 with digest-bound transcripts and declaring a
        pending row 2 whose outputs do not exist: the first is evidence, the second is not."""
        from ai_workflow_engine.milestone_runner.events import (
            DurableEvidenceReference,
            EvidenceKind,
            EvidenceRoot,
        )

        def row(sequence: int, completed: bool) -> ProviderRunRecord:
            name = f"transcripts/{sequence:04d}-20260930T12{sequence:02d}00Z-fake-implementation"
            return ProviderRunRecord(
                sequence=sequence,
                role=ProviderRole.IMPLEMENTATION,
                provider="fake",
                milestone_id="AUTO-099-M01",
                started_at=f"2026-09-30T12:{sequence:02d}:00Z",
                completed_at=f"2026-09-30T12:{sequence:02d}:30Z" if completed else None,
                duration_ms=1 if completed else 0,
                exit_code=0 if completed else None,
                prompt_path=f"{name}.prompt.md",
                stdout_path=f"{name}.stdout.txt",
                stderr_path=f"{name}.stderr.txt",
            )

        references = []
        for path in (row(1, True).prompt_path, row(1, True).stdout_path, row(1, True).stderr_path):
            target = store.run_directory / path
            target.write_bytes(b"" if path.endswith("stderr.txt") else b"bytes")
            references.append(
                DurableEvidenceReference(
                    kind=EvidenceKind.TRANSCRIPT,
                    root=EvidenceRoot.RUN,
                    path=path,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    byte_count=target.stat().st_size,
                )
            )
        start = chain.record
        pending_one = revise_record(
            start, moment=T0 + timedelta(seconds=100), updates={"provider_runs": [row(1, False)]}
        )
        chain.record_update(start, pending_one, pending_one.updated_at)
        before = chain.record
        completed = revise_record(
            before, moment=T0 + timedelta(seconds=101), updates={"provider_runs": [row(1, True)]}
        )
        pending_two = revise_record(
            completed,
            moment=T0 + timedelta(seconds=102),
            updates={"provider_runs": [row(1, True), row(2, False)]},
        )
        declaration = chain.declare(
            action=MutationAction.APPLICATION_STEP,
            command=MutationCommand.START,
            initiated_at=completed.updated_at,
            evidence=ApplicationStepEvidence(kind="APPLICATION_STEP", description="mixed"),
            changes=[
                PlannedChange(
                    LifecycleEventType.RUN_RECORD_UPDATED,
                    before,
                    completed,
                    completed.updated_at,
                    evidence=tuple(references),
                ),
                PlannedChange(
                    LifecycleEventType.RUN_RECORD_UPDATED,
                    completed,
                    pending_two,
                    pending_two.updated_at,
                ),
            ],
        )
        chain.append_constituent(declaration, 1)
        chain.append_constituent(declaration, 2)
        view = store.load_lifecycle(lock=lock)
        assert view.state.prospective_paths == (
            row(2, False).stdout_path,
            row(2, False).stderr_path,
        )
        assert not (store.run_directory / row(2, False).stdout_path).exists()
        (store.run_directory / row(1, True).stdout_path).unlink()
        from ai_workflow_engine.milestone_runner.events import OperationRecordInvalid

        with pytest.raises(OperationRecordInvalid):
            store.load_lifecycle(lock=lock)


# ======================================================================================
# AUTO-018 remediation cycle 1 -- AUTO018-IMPL-R02, R04, R06, R07, R10 and R12
# ======================================================================================


def _next_update(chain: EventStore, offset: int = 60) -> Callable[[], Any]:
    before = chain.record
    after = revise_record(
        before, moment=T0 + timedelta(seconds=offset), updates={"changed_paths": []}
    )
    return lambda: chain.record_update(before, after, after.updated_at)


def _detach(directory: Path) -> Path:
    """Rename `directory` away and put a fresh, empty directory at its canonical name."""
    detached = directory.with_name(directory.name + ".detached")
    directory.rename(detached)
    directory.mkdir(mode=0o700)
    return detached


RAW_PATH = f"operations/{'e' * 64}/attempts/0001/result.raw"


class TestAuto018R02NamespaceSwap:
    """AUTO018-IMPL-R02: success is never acknowledged into a detached child directory.

    Each case renames an opened child directory away and replaces it at a deterministic point
    -- before the link, after the link or replace, or during confirmation. The publication must
    refuse with LOCK_OWNERSHIP_LOST and the store must not advance.
    """

    def test_a_swap_before_the_link_publishes_nothing_canonically(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost

        events_directory = store.run_directory / EVENTS_DIRECTORY
        real_fsync = os.fsync
        detached: list[Path] = []

        def fsync(descriptor: int) -> None:
            real_fsync(descriptor)
            # The event's own temporary file is the first regular file fsynced in the events
            # directory: swap the run directory before the link is reached.
            if (
                not detached
                and stat.S_ISREG(os.fstat(descriptor).st_mode)
                and os.fstat(descriptor).st_nlink == 1
                and any(
                    name.startswith(".")
                    for name in os.listdir(events_directory)
                    if events_directory.exists()
                )
            ):
                detached.append(_detach(store.run_directory))

        sequence = chain.require_state().sequence
        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", fsync)
            with pytest.raises(LockOwnershipLost) as lost:
                _next_update(chain)()
        assert lost.value.stop_reason is StopReason.LOCK_OWNERSHIP_LOST
        assert detached
        assert chain.require_state().sequence == sequence
        assert not (store.run_directory / EVENTS_DIRECTORY).exists()
        assert len(list((detached[0] / EVENTS_DIRECTORY).glob("0*.json"))) == sequence
        assert not lock.is_held

    def test_a_swap_after_the_event_link_prevents_acknowledgment(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost

        real_link = os.link
        detached: list[Path] = []

        def link(*args: Any, **kwargs: Any) -> None:
            real_link(*args, **kwargs)
            if str(args[1]).startswith("00000008-"):
                detached.append(_detach(store.run_directory))

        with monkeypatch.context() as fault:
            fault.setattr(os, "link", link)
            with pytest.raises(LockOwnershipLost):
                _next_update(chain)()
        assert chain.require_state().sequence == 7, "the detached event was never acknowledged"
        assert (detached[0] / EVENTS_DIRECTORY / "00000008-RUN_RECORD_UPDATED.json").exists()
        assert not (store.run_directory / EVENTS_DIRECTORY).exists()
        assert not lock.is_held

    @pytest.mark.parametrize("name", [PUBLICATION_WITNESS_FILE_NAME, "state.json"])
    def test_a_swap_after_a_replace_prevents_acknowledgment(
        self,
        chain: EventStore,
        store: RunStateStore,
        monkeypatch: pytest.MonkeyPatch,
        name: str,
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost

        real_replace = os.replace

        def replace(source: Any, destination: Any, **kwargs: Any) -> None:
            real_replace(source, destination, **kwargs)
            if destination == name:
                _detach(store.run_directory)

        with monkeypatch.context() as fault:
            fault.setattr(os, "replace", replace)
            with pytest.raises(LockOwnershipLost):
                _next_update(chain)()
        if name == PUBLICATION_WITNESS_FILE_NAME:
            assert chain.require_state().sequence == 7

    def test_a_swap_of_the_operation_ancestry_after_the_link_prevents_acknowledgment(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost

        real_link = os.link
        attempt_directory = store.run_directory / Path(RAW_PATH).parent

        def link(*args: Any, **kwargs: Any) -> None:
            real_link(*args, **kwargs)
            if args[1] == "result.raw":
                _detach(attempt_directory.parent.parent)  # operations/<operation-id>

        with monkeypatch.context() as fault:
            fault.setattr(os, "link", link)
            with pytest.raises(LockOwnershipLost):
                chain.publish_operation_text(RAW_PATH, "raw bytes")
        assert not (store.run_directory / RAW_PATH).exists()

    def test_a_swap_of_the_authority_ancestry_after_the_link_prevents_acknowledgment(
        self, store: RunStateStore, lock: RunLock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost
        from ai_workflow_engine.milestone_runner.state import DurableTarget, publish_exclusively

        authority = store.artifact_root / "stage-starts"
        real_link = os.link

        def link(*args: Any, **kwargs: Any) -> None:
            real_link(*args, **kwargs)
            if args[1] == "probe.json":
                _detach(authority)

        target = DurableTarget(
            lock=lock,
            storage_root=store.artifact_root,
            repository_root=store.repository_root,
            parts=("stage-starts",),
            name="probe.json",
        )
        with monkeypatch.context() as fault:
            fault.setattr(os, "link", link)
            with pytest.raises(LockOwnershipLost):
                publish_exclusively(authority / "probe.json", b"{}", target=target)
        assert not (authority / "probe.json").exists()

    def test_a_swap_during_confirmation_reports_no_success(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost

        lock.release()
        later = new_lock(store)
        later.acquire()
        real_fsync = os.fsync
        swapped: list[Path] = []

        def fsync(descriptor: int) -> None:
            real_fsync(descriptor)
            if not swapped and stat.S_ISREG(os.fstat(descriptor).st_mode):
                swapped.append(_detach(store.run_directory))

        try:
            with monkeypatch.context() as fault:
                fault.setattr(os, "fsync", fsync)
                with pytest.raises(LockOwnershipLost):
                    store.open_lifecycle(later)
            assert swapped
            assert not later.is_held
        finally:
            later.release()


def _fsync_recorder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    seen: list[tuple[int, int]] = []
    real = os.fsync

    def recording(descriptor: int) -> None:
        status = os.fstat(descriptor)
        seen.append((status.st_dev, status.st_ino))
        real(descriptor)

    monkeypatch.setattr(os, "fsync", recording)
    return seen


def _identity(path: Path) -> tuple[int, int]:
    status = path.stat()
    return status.st_dev, status.st_ino


class TestAuto018R04AncestryDurability:
    """AUTO018-IMPL-R04: a directory left visible by a failed parent fsync is not durable."""

    def _fail_once_after_mkdir(self, store: RunStateStore, monkeypatch: pytest.MonkeyPatch) -> None:
        real_mkdir = os.mkdir
        real_fsync = os.fsync
        armed = {"value": False}

        def mkdir(path: Any, *args: Any, **kwargs: Any) -> None:
            real_mkdir(path, *args, **kwargs)
            if path == "operations":
                armed["value"] = True

        def fsync(descriptor: int) -> None:
            if armed["value"] and _target_is(descriptor, store.run_directory):
                armed["value"] = False
                raise OSError(5, "Input/output error")
            real_fsync(descriptor)

        monkeypatch.setattr(os, "mkdir", mkdir)
        monkeypatch.setattr(os, "fsync", fsync)

    def test_a_retry_under_the_same_hold_refsyncs_the_whole_ancestry(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with monkeypatch.context() as fault:
            self._fail_once_after_mkdir(store, fault)
            with pytest.raises(StatePublicationFailure):
                chain.publish_operation_text(RAW_PATH, "raw bytes")
        operations = store.run_directory / "operations"
        assert operations.is_dir(), "the directory is visible, but its entry was never fsynced"
        with monkeypatch.context() as recording:
            seen = _fsync_recorder(recording)
            reference = chain.publish_operation_text(RAW_PATH, "raw bytes")
        artifact = store.run_directory / RAW_PATH
        assert reference.sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
        for path in (
            artifact,
            artifact.parent,
            artifact.parent.parent,
            artifact.parent.parent.parent,
            operations,
            store.run_directory,
            store.artifact_root,
        ):
            assert _identity(path) in seen, path

    def test_a_retry_under_a_later_hold_refsyncs_the_whole_ancestry(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with monkeypatch.context() as fault:
            self._fail_once_after_mkdir(store, fault)
            with pytest.raises(StatePublicationFailure):
                chain.publish_operation_text(RAW_PATH, "raw bytes")
        lock.release()
        later = new_lock(store)
        later.acquire()
        try:
            events, _ = store.open_lifecycle(later)
            with monkeypatch.context() as recording:
                seen = _fsync_recorder(recording)
                events.publish_operation_text(RAW_PATH, "raw bytes")
            assert _identity(store.run_directory) in seen
            assert _identity(store.run_directory / "operations") in seen
            assert _identity(store.artifact_root) in seen
        finally:
            later.release()

    def test_a_still_failing_ancestor_barrier_never_reports_durable(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with monkeypatch.context() as fault:
            self._fail_once_after_mkdir(store, fault)
            with pytest.raises(StatePublicationFailure):
                chain.publish_operation_text(RAW_PATH, "raw bytes")
        real = os.fsync

        def failing(descriptor: int) -> None:
            if _target_is(descriptor, store.run_directory):
                raise OSError(5, "Input/output error")
            real(descriptor)

        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", failing)
            with pytest.raises(PublicationUncertain):
                chain.publish_operation_text(RAW_PATH, "raw bytes")
            # The identical-existing branch is not durable either while the barrier fails.
            with pytest.raises(PublicationUncertain):
                chain.publish_operation_text(RAW_PATH, "raw bytes")

    def test_a_dependent_event_is_not_emitted_while_the_ancestry_is_unconfirmed(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed mkdir-parent fsync under the events directory: no event is acknowledged."""
        events_directory = store.run_directory / EVENTS_DIRECTORY
        real = os.fsync
        armed = {"after_link": False}
        real_link = os.link

        def link(*args: Any, **kwargs: Any) -> None:
            real_link(*args, **kwargs)
            armed["after_link"] = True

        def fsync(descriptor: int) -> None:
            if armed["after_link"] and _target_is(descriptor, store.artifact_root):
                raise OSError(5, "Input/output error")
            real(descriptor)

        with monkeypatch.context() as fault:
            fault.setattr(os, "link", link)
            fault.setattr(os, "fsync", fsync)
            with pytest.raises(PublicationUncertain):
                _next_update(chain)()
        assert chain.require_state().sequence == 7
        assert len(list(events_directory.glob("0*.json"))) == 8


def _recovery_record(repository: Path, rounds: int) -> RunRecord:
    return RunRecord.model_validate_json(
        json.dumps(
            {
                **idle_record(repository).model_dump(mode="json"),
                "workflow_state": "HUMAN_INTERVENTION_REQUIRED",
                "stop_reason": "GOVERNANCE_CONTRADICTION",
                "current_milestone": "AUTO-099-M01",
                "review_attempts": rounds,
                "successful_review_rounds": rounds,
            }
        )
    )


class TestAuto018R06AggregateBudgets:
    """AUTO018-IMPL-R06: a declared budget delta applies exactly once across the manifest."""

    @pytest.fixture
    def recovering(self, store: RunStateStore, lock: RunLock) -> EventStore:
        events = store.begin_lifecycle(lock, pins())
        record = _recovery_record(store.repository_root, 2)
        events.baseline(
            record, source_sha256="a" * 64, source_byte_count=1, recorded_at=record.updated_at
        )
        store.record_bootstrap_evidence(events, record.updated_at)
        return events

    @staticmethod
    def _entry() -> Any:
        from ai_workflow_engine.milestone_runner.models import (
            ProviderFailureClass,
            RecoveryCommand,
            RecoveryLedgerEntry,
        )

        return RecoveryLedgerEntry(
            command=RecoveryCommand.RECOVER_FAILED_REVIEW,
            reason="the review provider failed before returning a verdict",
            recorded_at=stamp(50),
            pre_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            post_state=RunStatus.REVIEWING,
            branch="main",
            head_sha=BASELINE,
            budgets_touched={"successful_review_rounds": -1},
            classification=next(iter(ProviderFailureClass)),
            human_owner_ruling="restore one review budget",
        )

    def _changes(self, events: EventStore, counter_steps: list[dict[str, int]]) -> list[Any]:
        entry = self._entry()
        changes: list[PlannedChange] = []
        current = events.record
        for offset, updates in enumerate(counter_steps, start=51):
            after = revise_record(current, moment=T0 + timedelta(seconds=offset), updates=updates)
            changes.append(
                PlannedChange(
                    LifecycleEventType.RUN_RECORD_UPDATED, current, after, after.updated_at
                )
            )
            current = after
        appended = RunRecord.model_validate_json(
            json.dumps(
                {
                    **current.model_dump(mode="json"),
                    "review_recoveries": [entry.model_dump(mode="json")],
                }
            )
        )
        changes.append(
            PlannedChange(
                LifecycleEventType.RECOVERY_LEDGER_APPENDED,
                current,
                appended,
                appended.updated_at,
                ledger_entry=entry,
            )
        )
        moved = transition_to(appended, RunStatus.REVIEWING, moment=T0 + timedelta(seconds=60))
        changes.append(
            PlannedChange(LifecycleEventType.STATE_TRANSITIONED, appended, moved, moved.updated_at)
        )
        return changes

    def _declare(self, events: EventStore, counter_steps: list[dict[str, int]]) -> Any:
        from ai_workflow_engine.milestone_runner.events import (
            RecoveryCommandEvidence,
            RecoveryLedgerName,
        )
        from ai_workflow_engine.milestone_runner.models import RecoveryCommand

        entry = self._entry()
        return events.declare(
            action=MutationAction.RECOVERY_COMMAND,
            command=MutationCommand.RECOVER_FAILED_REVIEW,
            initiated_at=stamp(51),
            evidence=RecoveryCommandEvidence(
                kind="RECOVERY_COMMAND",
                command=RecoveryCommand.RECOVER_FAILED_REVIEW,
                ledger=RecoveryLedgerName.REVIEW_RECOVERIES,
                entry=entry,
                original_ledger_length=0,
                budgets_touched={"successful_review_rounds": -1},
                summary="restore one review budget",
            ),
            changes=self._changes(events, counter_steps),
        )

    def test_the_declared_delta_applied_once_completes_exactly_once(
        self, recovering: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        declaration = self._declare(recovering, [{"successful_review_rounds": 1}])
        recovering.append_constituent(declaration, 1)
        recovering.append_constituent(declaration, 2)
        before = recovering.record
        moved = transition_to(before, RunStatus.REVIEWING, moment=T0 + timedelta(seconds=60))
        recovering.append_transition(before, moved, moved.updated_at, constituent=(declaration, 3))
        loaded = store.load_lifecycle(lock=lock)
        assert loaded.record.successful_review_rounds == 1
        assert len(loaded.record.review_recoveries) == 1
        assert loaded.record.workflow_state is RunStatus.REVIEWING
        assert loaded.incomplete is None

    @pytest.mark.parametrize(
        "steps, why",
        [
            ([{"successful_review_rounds": 1}, {"successful_review_rounds": 0}], "more than once"),
            ([], "never applied"),
            ([{"successful_review_rounds": 0}], "not by the declared delta"),
            ([{"successful_review_rounds": 1, "review_attempts": 3}], "budgets no change"),
        ],
        ids=["repeated", "omitted", "altered", "unbudgeted-counter"],
    )
    def test_a_wrong_aggregate_is_refused_before_the_declaration_is_published(
        self,
        recovering: EventStore,
        store: RunStateStore,
        steps: list[dict[str, int]],
        why: str,
    ) -> None:
        names = sorted(path.name for path in event_files(store))
        sequence = recovering.require_state().sequence
        with pytest.raises(EventChainBroken, match=why):
            self._declare(recovering, steps)
        assert sorted(path.name for path in event_files(store)) == names
        assert recovering.require_state().sequence == sequence

    def test_a_published_repeated_delta_is_refused_on_verified_load(
        self,
        recovering: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A writer without the aggregate check could chain it; the verified load refuses."""
        import ai_workflow_engine.milestone_runner.events as events_module

        steps = [{"successful_review_rounds": 1}, {"successful_review_rounds": 0}]
        with monkeypatch.context() as bypass:
            bypass.setattr(events_module, "_validate_budget_effects", lambda *_: None)
            declaration = self._declare(recovering, steps)
            for index in (1, 2, 3):
                recovering.append_constituent(declaration, index)
        with pytest.raises(EventChainBroken, match="more than once"):
            store.load_lifecycle(lock=lock)


class TestAuto018R07DuplicateDependencies:
    """AUTO018-IMPL-R07: a duplicate is acknowledged only with its whole dependency set."""

    def _refused(self, chain: EventStore, envelope: LifecycleEvent) -> None:
        from ai_workflow_engine.milestone_runner.events import LIFECYCLE_ERRORS
        from ai_workflow_engine.milestone_runner.state import StateError

        with pytest.raises((*LIFECYCLE_ERRORS, StateError)):
            chain.publish_envelope(envelope)

    def test_a_missing_witness_refuses_the_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        envelope, _ = chain.events[4]
        (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).unlink()
        self._refused(chain, envelope)

    def test_a_corrupt_witness_refuses_the_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        envelope, _ = chain.events[4]
        witness = store.run_directory / PUBLICATION_WITNESS_FILE_NAME
        witness.write_bytes(witness.read_bytes() + b" ")
        self._refused(chain, envelope)

    def test_a_regressed_witness_refuses_the_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        from ai_workflow_engine.milestone_runner.events import model_bytes, witness_for

        earlier, earlier_digest = chain.events[5]
        envelope, _ = chain.events[4]
        (store.run_directory / PUBLICATION_WITNESS_FILE_NAME).write_bytes(
            model_bytes(witness_for(earlier, earlier_digest))
        )
        self._refused(chain, envelope)

    def test_a_corrupted_predecessor_refuses_the_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        envelope, _ = chain.events[4]
        predecessor = event_files(store)[3]
        predecessor.write_bytes(predecessor.read_bytes().replace(b'"', b"'", 1))
        self._refused(chain, envelope)

    def test_an_unavailable_predecessor_refuses_the_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        envelope, _ = chain.events[4]
        event_files(store)[1].unlink()
        self._refused(chain, envelope)

    def test_a_missing_referenced_dependency_refuses_the_duplicate(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        envelope, _ = chain.events[4]
        store.policy_path.unlink()
        self._refused(chain, envelope)

    def test_a_valid_duplicate_preserves_bytes_mtimes_and_counters(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        before = tree_snapshot(store.run_directory)
        record = chain.record
        for envelope, digest in chain.events:
            appended = chain.publish_envelope(envelope)
            assert appended.duplicate and appended.sha256 == digest
        assert tree_snapshot(store.run_directory) == before
        assert chain.record == record
        assert chain.require_state().sequence == 7


class TestAuto018R10WitnessPredecessor:
    """AUTO018-IMPL-R10: the witness's predecessor is validated, not merely carried."""

    @staticmethod
    def _forge(store: RunStateStore, **changes: Any) -> None:
        witness = store.run_directory / PUBLICATION_WITNESS_FILE_NAME
        document = json.loads(witness.read_bytes())
        document.update(changes)
        witness.write_bytes(integrity_bytes(document))

    @pytest.mark.parametrize(
        "prev",
        [None, "not-a-digest", "A" * 64, "0" * 64],
        ids=["null-for-non-genesis", "malformed", "uppercase", "wrong-digest"],
    )
    def test_a_bad_predecessor_on_an_established_chain_refuses(
        self, chain: EventStore, store: RunStateStore, prev: str | None
    ) -> None:
        self._forge(store, prev_event_digest=prev)
        reload_refuses(store)

    def test_a_contradictory_predecessor_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        """A well-formed digest of a real event that is not the witnessed event's predecessor."""
        self._forge(store, prev_event_digest=chain.events[2][1])
        reload_refuses(store, "predecessor")

    def test_a_missing_predecessor_field_refuses(
        self, chain: EventStore, store: RunStateStore
    ) -> None:
        witness = store.run_directory / PUBLICATION_WITNESS_FILE_NAME
        document = json.loads(witness.read_bytes())
        del document["prev_event_digest"]
        witness.write_bytes(integrity_bytes(document))
        reload_refuses(store)

    def test_the_genesis_witness_names_no_predecessor(
        self, store: RunStateStore, lock: RunLock
    ) -> None:
        events = store.begin_lifecycle(lock, pins())
        record = idle_record(store.repository_root)
        events.initialize(record, record.created_at)
        witness = json.loads((store.run_directory / PUBLICATION_WITNESS_FILE_NAME).read_bytes())
        assert witness["sequence"] == 1 and witness["prev_event_digest"] is None
        assert store.load_lifecycle(lock=lock).state.sequence == 1
        self._forge(store, prev_event_digest="0" * 64)
        reload_refuses(store)


class TestAuto018R12StreamingChain:
    """AUTO018-IMPL-R12: the verified load streams the chain and retains no event bodies."""

    def test_each_event_is_parsed_then_folded_before_the_next_is_read(
        self,
        chain: EventStore,
        store: RunStateStore,
        lock: RunLock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import ai_workflow_engine.milestone_runner.state as state_module

        calls: list[tuple[str, Any]] = []
        real_parse, real_fold, real_read = (
            state_module.parse_event_bytes,
            state_module.fold_step,
            state_module._read_named,
        )

        def read(directory: int, name: str, *args: Any, **kwargs: Any) -> Any:
            if parse_event_file_name(name) is not None:
                calls.append(("read", int(name[:8])))
            return real_read(directory, name, *args, **kwargs)

        def parse(name: str, payload: bytes) -> Any:
            calls.append(("parse", int(name[:8])))
            return real_parse(name, payload)

        def fold(state: Any, event: Any, digest: str, **kwargs: Any) -> Any:
            calls.append(("fold", event.sequence))
            return real_fold(state, event, digest, **kwargs)

        monkeypatch.setattr(state_module, "_read_named", read)
        monkeypatch.setattr(state_module, "parse_event_bytes", parse)
        monkeypatch.setattr(state_module, "fold_step", fold)
        view = store.load_lifecycle(lock=lock)
        expected = [
            (step, sequence) for sequence in range(1, 8) for step in ("read", "parse", "fold")
        ]
        assert calls == expected
        assert view.record == chain.record

    def test_an_invalid_prefix_stops_before_any_later_event_is_read(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ai_workflow_engine.milestone_runner.state as state_module

        third = event_files(store)[2]
        third.write_bytes(third.read_bytes()[:-1])
        opened: list[str] = []
        real_read = state_module._read_named

        def read(directory: int, name: str, *args: Any, **kwargs: Any) -> Any:
            opened.append(name)
            return real_read(directory, name, *args, **kwargs)

        monkeypatch.setattr(state_module, "_read_named", read)
        reload_refuses(store)
        event_reads = [name for name in opened if parse_event_file_name(name) is not None]
        assert event_reads and max(int(name[:8]) for name in event_reads) == 3

    def test_the_verified_view_retains_no_event_bodies(
        self, chain: EventStore, store: RunStateStore, lock: RunLock
    ) -> None:
        import gc

        from ai_workflow_engine.milestone_runner.events import ChainEntry

        def live_events() -> int:
            gc.collect()
            return sum(1 for item in gc.get_objects() if isinstance(item, LifecycleEvent))

        baseline = live_events()
        view = store.load_lifecycle(lock=lock)
        assert live_events() == baseline, "a verified load retained event bodies"
        assert len(view.chain) == 7
        assert all(isinstance(entry, ChainEntry) for entry in view.chain)
        assert not any(
            isinstance(value, LifecycleEvent)
            for value in (view.record, view.state, view.projection, *view.chain)
        )
        # The diagnostic accessor still re-reads exactly the verified bodies.
        assert [digest for _, digest in view.events] == [entry.sha256 for entry in view.chain]

    def test_an_oversize_event_is_refused_before_it_is_read(
        self, chain: EventStore, store: RunStateStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_workflow_engine.milestone_runner.events import MAX_LIFECYCLE_DOCUMENT_BYTES

        third = event_files(store)[2]
        with third.open("r+b") as handle:
            handle.truncate(MAX_LIFECYCLE_DOCUMENT_BYTES + 1)
        oversize = third.stat().st_ino
        read_inodes: list[int] = []
        real_read = os.read

        def read(descriptor: int, count: int) -> bytes:
            read_inodes.append(os.fstat(descriptor).st_ino)
            return real_read(descriptor, count)

        monkeypatch.setattr(os, "read", read)
        reload_refuses(store)
        assert oversize not in read_inodes
