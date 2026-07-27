"""Tests for agentos_workflow.orchestrator.state_store (AUDIT_MODEL.md)."""

import json
import multiprocessing as mp
import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator.state_store import (
    CommandExecutionRecord,
    StateStore,
    StateStoreCorruptionError,
    StateStoreError,
    StateStoreOrderingError,
    StateStorePathConfinementError,
    StateTransitionRecord,
)


def _transition(
    *,
    workflow_id: str = "wf-1",
    repository_path: str = "/tmp/agentos-test-fixture-repo",
    from_state: str = "CREATED",
    to_state: str = "AUTHORIZED",
    timestamp: str = "2026-07-24T10:00:00+00:00",
    actor: str = "human",
    gate_evidence_ref: str | None = None,
) -> StateTransitionRecord:
    return StateTransitionRecord(
        workflow_id=workflow_id,
        target_repository="github.com/org/repo",
        repository_path=repository_path,
        stage_id="AUTO-002",
        from_state=from_state,
        to_state=to_state,
        timestamp=timestamp,
        actor=actor,
        gate_evidence_ref=gate_evidence_ref,
    )


def _command(
    *,
    start_time: str = "2026-07-24T10:00:00+00:00",
    completion_time: str = "2026-07-24T10:00:01+00:00",
    exit_code: int | None = 0,
    timeout_status: bool = False,
) -> CommandExecutionRecord:
    return CommandExecutionRecord(
        normalized_command_identity="run_tests",
        start_time=start_time,
        completion_time=completion_time,
        exit_code=exit_code,
        timeout_status=timeout_status,
        stdout_ref="stdout/run_tests-1.log",
        stderr_ref="stderr/run_tests-1.log",
    )


def _make_store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def _valid_config_dict(repository_path: Path, tmp_path: Path) -> dict[str, object]:
    return {
        "repository_path": str(repository_path),
        "repository_identity": "github.com/org/some-other-repo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/some-program/stage-prompts",
        "stage_branch_naming": "governance/{stage_id}-{slug}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests"],
        "merge_method": "squash",
        "claude_cli_executable": "/usr/local/bin/claude",
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": "/usr/local/bin/codex",
        "codex_cli_timeout_seconds": 1800,
        "allowed_environment_variables": ["PATH", "HOME", "LANG"],
        "allowed_changed_paths": ["docs/some-program/**"],
        "forbidden_changed_paths": ["src/**", "tests/**", ".github/**"],
        "repair_attempt_limit": 3,
        "state_directory": str(tmp_path / "state"),
        "audit_directory": str(tmp_path / "audit"),
    }


class TestRecordSchemas:
    def test_state_transition_record_round_trips(self) -> None:
        record = _transition(gate_evidence_ref="evidence/precondition-1.json")
        loaded = StateTransitionRecord.model_validate_json(record.model_dump_json())
        assert loaded == record

    def test_state_transition_record_rejects_extra_field(self) -> None:
        raw = _transition().model_dump()
        raw["unexpected"] = "nope"
        with pytest.raises(ValidationError):
            StateTransitionRecord.model_validate(raw)

    def test_state_transition_record_rejects_bad_timestamp(self) -> None:
        with pytest.raises(ValidationError, match="ISO-8601"):
            _transition(timestamp="not-a-timestamp")

    def test_state_transition_record_rejects_bad_actor(self) -> None:
        with pytest.raises(ValidationError, match="actor"):
            _transition(actor="robot")

    def test_state_transition_record_accepts_agent_actor(self) -> None:
        record = _transition(actor="agent:ImplementationAgent")
        assert record.actor == "agent:ImplementationAgent"

    def test_state_transition_record_persists_both_identity_and_path(self) -> None:
        """AUDIT_MODEL.md §3: every transition record binds repository *identity*
        (`target_repository`) and canonical repository *path* (`repository_path`) as two
        independently persisted fields — a caller must be able to recover both from a stored
        record, not merely one opaque combined string.
        """
        record = _transition(repository_path="/srv/repos/example")
        assert record.target_repository == "github.com/org/repo"
        assert record.repository_path == "/srv/repos/example"
        loaded = StateTransitionRecord.model_validate_json(record.model_dump_json())
        assert loaded.target_repository == "github.com/org/repo"
        assert loaded.repository_path == "/srv/repos/example"

    def test_state_transition_record_rejects_missing_repository_path(self) -> None:
        raw = _transition().model_dump()
        del raw["repository_path"]
        with pytest.raises(ValidationError, match="repository_path"):
            StateTransitionRecord.model_validate(raw)

    def test_state_transition_record_rejects_blank_repository_path(self) -> None:
        with pytest.raises(ValidationError, match="repository_path"):
            _transition(repository_path="")

    def test_command_execution_record_round_trips(self) -> None:
        record = _command()
        loaded = CommandExecutionRecord.model_validate_json(record.model_dump_json())
        assert loaded == record

    def test_command_execution_record_allows_null_exit_code(self) -> None:
        record = _command(exit_code=None, timeout_status=True)
        assert record.exit_code is None
        assert record.timeout_status is True

    def test_command_execution_record_rejects_bad_start_time(self) -> None:
        with pytest.raises(ValidationError, match="ISO-8601"):
            _command(start_time="whenever")


class TestAppendAndRead:
    def test_record_and_read_single_transition(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        record = _transition()
        store.record_transition(record)
        assert store.read_transitions("wf-1") == [record]

    def test_transitions_persist_in_order(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        first = _transition(from_state="CREATED", to_state="AUTHORIZED")
        second = _transition(
            from_state="AUTHORIZED",
            to_state="PRECONDITIONS_CHECKED",
            timestamp="2026-07-24T10:00:05+00:00",
            actor="orchestrator",
        )
        store.record_transition(first)
        store.record_transition(second)
        assert store.read_transitions("wf-1") == [first, second]

    def test_record_and_read_single_command_execution(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        record = _command()
        store.record_command_execution("wf-1", record)
        assert store.read_command_executions("wf-1") == [record]

    def test_command_executions_persist_in_order(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        first = _command(
            start_time="2026-07-24T10:00:00+00:00", completion_time="2026-07-24T10:00:01+00:00"
        )
        second = _command(
            start_time="2026-07-24T10:05:00+00:00", completion_time="2026-07-24T10:05:01+00:00"
        )
        store.record_command_execution("wf-1", first)
        store.record_command_execution("wf-1", second)
        assert store.read_command_executions("wf-1") == [first, second]

    def test_read_empty_history_returns_empty_list(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        assert store.read_transitions("never-recorded") == []
        assert store.read_command_executions("never-recorded") == []

    def test_transitions_and_commands_stored_under_separate_configured_roots(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition())
        store.record_command_execution("wf-1", _command())
        assert (tmp_path / "state" / "wf-1" / "transitions.jsonl").is_file()
        assert (tmp_path / "audit" / "wf-1" / "commands.jsonl").is_file()

    def test_different_workflow_ids_do_not_share_history(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(workflow_id="wf-a", to_state="AUTHORIZED"))
        store.record_transition(_transition(workflow_id="wf-b", to_state="FAILED"))
        assert [r.to_state for r in store.read_transitions("wf-a")] == ["AUTHORIZED"]
        assert [r.to_state for r in store.read_transitions("wf-b")] == ["FAILED"]

    def test_rejects_workflow_id_with_path_traversal(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        with pytest.raises(StateStoreError):
            store.record_transition(_transition(workflow_id="../../escape"))


class TestRestartRecovery:
    def test_new_store_instance_reads_prior_process_history(self, tmp_path: Path) -> None:
        first_process_store = _make_store(tmp_path)
        first_process_store.record_transition(_transition(to_state="AUTHORIZED"))
        first_process_store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
                actor="orchestrator",
            )
        )

        # A brand-new StateStore object, as a resumed process would construct, must see the
        # exact same history purely from what is on disk (AUDIT_MODEL.md: state persisted after
        # every transition; WORKFLOW_STATES.md §6: resume reloads persisted state).
        resumed_store = _make_store(tmp_path)
        assert [r.to_state for r in resumed_store.read_transitions("wf-1")] == [
            "AUTHORIZED",
            "PRECONDITIONS_CHECKED",
        ]

    def test_current_state_reflects_latest_transition_after_restart(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
                actor="orchestrator",
            )
        )
        resumed = _make_store(tmp_path)
        assert resumed.current_state("wf-1") == "PRECONDITIONS_CHECKED"

    def test_current_state_is_none_for_unknown_workflow(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        assert store.current_state("never-recorded") is None


class TestAppendOnlyGuarantee:
    def test_public_api_exposes_no_edit_or_delete_operation(self) -> None:
        # AUDIT_MODEL.md §4: the engine itself never edits or deletes a previously written
        # record. Assert that no such method exists on the public surface at all.
        forbidden = {"delete", "remove", "update", "edit", "truncate", "clear", "overwrite"}
        public_methods = {name for name in dir(StateStore) if not name.startswith("_")}
        assert forbidden.isdisjoint(public_methods)

    def test_recording_never_shrinks_an_existing_file(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        size_after_first = path.stat().st_size
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
                actor="orchestrator",
            )
        )
        assert path.stat().st_size > size_after_first

    def test_earlier_lines_are_never_rewritten(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        first_line_before = path.read_text(encoding="utf-8").splitlines()[0]
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
                actor="orchestrator",
            )
        )
        first_line_after = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line_before == first_line_after


class TestCorruptionHandling:
    def test_corrupt_json_line_raises_and_does_not_truncate_history(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{not valid json\n")

        with pytest.raises(StateStoreCorruptionError):
            store.read_transitions("wf-1")

        # The corrupt line must not have been silently dropped by the failed read attempt.
        assert path.read_text(encoding="utf-8").count("\n") == 2

    def test_schema_violating_line_raises_corruption_error(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"workflow_id": "wf-1"}\n')  # missing required fields

        with pytest.raises(StateStoreCorruptionError):
            store.read_transitions("wf-1")

    def test_blank_lines_are_rejected_as_corruption(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with pytest.raises(StateStoreCorruptionError):
            store.read_transitions("wf-1")

    def test_missing_terminal_newline_is_rejected_as_torn_append(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.write_bytes(path.read_bytes().rstrip(b"\n"))

        with pytest.raises(StateStoreCorruptionError, match="terminal newline"):
            store.read_transitions("wf-1")

    def test_valid_records_before_a_corrupt_line_are_never_silently_discarded(
        self, tmp_path: Path
    ) -> None:
        # The failure must be loud (an exception), never a quiet partial-history return that
        # looks like a complete, valid read.
        store = _make_store(tmp_path)
        store.record_transition(_transition(to_state="AUTHORIZED"))
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
                actor="orchestrator",
            )
        )
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("garbage\n")

        try:
            store.read_transitions("wf-1")
            pytest.fail("expected StateStoreCorruptionError")
        except StateStoreCorruptionError as exc:
            assert "3" in str(exc)  # identifies the failing line, not just "somewhere"


class TestWriteFailureSafety:
    """Adversarial: a write-path failure (fsync failure, permission-denied directory) must
    propagate loudly rather than being swallowed or leaving a torn/partial record silently
    accepted as a successful append (AUDIT_MODEL.md §4 — audit completeness is a safety
    property).
    """

    def test_short_write_is_completed_across_multiple_os_write_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POSIX permits `os.write` to write fewer bytes than requested. Simulate a short write
        (one byte at a time) and confirm the full record is still written intact, byte for byte
        — never silently truncated (AUDIT_MODEL.md §4).
        """
        store = _make_store(tmp_path)
        real_os_write = os.write

        def _one_byte_at_a_time(fd: int, data: bytes) -> int:
            return real_os_write(fd, data[:1]) if data else 0

        with monkeypatch.context() as patched:
            patched.setattr(
                "agentos_workflow.orchestrator.state_store.os.write", _one_byte_at_a_time
            )
            store.record_transition(_transition(to_state="AUTHORIZED"))

        assert [r.to_state for r in store.read_transitions("wf-1")] == ["AUTHORIZED"]

    def test_write_making_zero_progress_raises_rather_than_hanging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(tmp_path)

        def _zero_progress(fd: int, data: bytes) -> int:
            return 0

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.state_store.os.write", _zero_progress)
            with pytest.raises(OSError):
                store.record_transition(_transition(to_state="AUTHORIZED"))

    def test_fsync_failure_propagates_and_leaves_no_fd_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_store(tmp_path)
        real_fsync = os.fsync

        def _raise_on_fsync(fd: int) -> None:
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("simulated fsync failure")
            real_fsync(fd)

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.state_store.os.fsync", _raise_on_fsync)
            with pytest.raises(OSError):
                store.record_transition(_transition(to_state="AUTHORIZED"))

        # The fd must have been closed despite the fsync failure (no leaked descriptor blocking
        # a later, successful append against the same path). The first line's bytes were
        # already handed to the OS by os.write() before the simulated fsync failure, so it is
        # still present; the caller still saw the failure as an exception, never a silent
        # success, and can decide for itself whether to treat this as needing reconciliation.
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
                actor="orchestrator",
            )
        )
        assert [r.to_state for r in store.read_transitions("wf-1")] == [
            "AUTHORIZED",
            "PRECONDITIONS_CHECKED",
        ]

    def test_permission_denied_directory_raises_and_does_not_silently_no_op(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        workflow_dir = tmp_path / "state" / "wf-1"
        workflow_dir.mkdir(parents=True)
        workflow_dir.chmod(0o500)  # read+execute only: cannot create/write a file inside it
        try:
            with pytest.raises(OSError):
                store.record_transition(_transition(to_state="AUTHORIZED"))
        finally:
            workflow_dir.chmod(0o700)  # restore so pytest's own tmp_path cleanup can remove it


def _concurrent_short_write_appender(
    state_directory_str: str,
    audit_directory_str: str,
    workflow_id: str,
    tag: str,
    count: int,
    start_barrier: "mp.synchronize.Barrier",
) -> None:
    """Run in a real, separate OS process. Patches `os.write` to write one byte at a time,
    widening the race window a genuinely concurrent, non-excluded append would corrupt, then
    waits at a barrier so both processes' write bursts actually overlap in time rather than
    merely running back-to-back.
    """
    import agentos_workflow.orchestrator.state_store as state_store_module

    real_write = os.write

    def _one_byte_at_a_time(fd: int, data: bytes) -> int:
        return real_write(fd, data[:1]) if data else 0

    state_store_module.os.write = _one_byte_at_a_time  # type: ignore[attr-defined]
    store = StateStore(
        state_directory=Path(state_directory_str), audit_directory=Path(audit_directory_str)
    )
    start_barrier.wait(timeout=10)
    for i in range(count):
        store.record_transition(
            _transition(
                workflow_id=workflow_id,
                from_state="CREATED",
                to_state="AUTHORIZED",
                timestamp="2026-07-24T10:00:00+00:00",
                actor="human",
                gate_evidence_ref=f"{tag}-{i}-{'x' * 40}",
            )
        )


class TestAUTO002F05ConcurrentAppendExclusion:
    """AUTO002-F05: `_append_jsonl_line` previously had no exclusion of its own around the
    open-write-fsync-close sequence. `os.O_APPEND` only makes a single `write()` syscall atomic;
    `_write_all`'s short-write retry loop can issue several `write()` calls per logical record,
    so two concurrent writers could interleave mid-record and corrupt both. Independently
    reproduced before this fix: two real OS processes, each forced into one-byte-at-a-time
    writes, produced byte-interleaved garbage on well over half of all appended lines. The fix
    holds an exclusive `flock` for the entire sequence.
    """

    def test_two_processes_with_short_writes_never_interleave(self, tmp_path: Path) -> None:
        state_directory = tmp_path / "state"
        audit_directory = tmp_path / "audit"
        ctx = mp.get_context("fork")
        barrier = ctx.Barrier(2)
        per_process = 25
        proc_a = ctx.Process(
            target=_concurrent_short_write_appender,
            args=(str(state_directory), str(audit_directory), "wf-race", "A", per_process, barrier),
        )
        proc_b = ctx.Process(
            target=_concurrent_short_write_appender,
            args=(str(state_directory), str(audit_directory), "wf-race", "B", per_process, barrier),
        )
        proc_a.start()
        proc_b.start()
        proc_a.join(timeout=30)
        proc_b.join(timeout=30)
        assert proc_a.exitcode == 0
        assert proc_b.exitcode == 0

        path = state_directory / "wf-race" / "transitions.jsonl"
        raw = path.read_text(encoding="utf-8")

        # Every line must be independently valid JSON — no interleaved bytes from the other
        # process's concurrent write burst.
        lines = raw.splitlines()
        assert len(lines) == per_process * 2
        for line in lines:
            json.loads(line)  # raises json.JSONDecodeError on any interleaved/corrupt line

        # The store's own reader must accept the full history without raising, and every
        # expected gate_evidence_ref from both processes must be present exactly once.
        store = StateStore(state_directory=state_directory, audit_directory=audit_directory)
        records = store.read_transitions("wf-race")
        assert len(records) == per_process * 2
        expected_refs = {f"A-{i}-{'x' * 40}" for i in range(per_process)} | {
            f"B-{i}-{'x' * 40}" for i in range(per_process)
        }
        assert {r.gate_evidence_ref for r in records} == expected_refs

    def test_append_holds_an_exclusive_flock_for_the_write_sequence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """White-box: assert the lock is actually acquired and released around the write, not
        just that concurrent writes happen not to corrupt in this particular test run.
        """
        import fcntl

        calls: list[tuple[str, int]] = []
        real_flock = fcntl.flock

        def _tracking_flock(fd: int, operation: int) -> None:
            calls.append(("flock", operation))
            real_flock(fd, operation)

        store = _make_store(tmp_path)
        with monkeypatch.context() as patched:
            patched.setattr(
                "agentos_workflow.orchestrator.state_store.fcntl.flock", _tracking_flock
            )
            store.record_transition(_transition(to_state="AUTHORIZED"))

        assert ("flock", fcntl.LOCK_EX) in calls
        assert ("flock", fcntl.LOCK_UN) in calls
        assert calls.index(("flock", fcntl.LOCK_EX)) < calls.index(("flock", fcntl.LOCK_UN))


class TestForConfig:
    def test_for_config_uses_state_and_audit_directories(self, tmp_path: Path) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        config = WorkflowConfig.model_validate(_valid_config_dict(repository_path, tmp_path))
        store = StateStore.for_config(config)
        assert store.state_directory == config.state_directory
        assert store.audit_directory == config.audit_directory

        store.record_transition(_transition())
        assert (config.state_directory / "wf-1" / "transitions.jsonl").is_file()


# ---------------------------------------------------------------------------------------------
# AUTO002-F08: audit record validation gaps — identity, timestamps, path confinement, ordering.
# Every record schema and read path previously accepted a caller-supplied value with no
# independent check; each class below reproduces one gap adversarially and confirms it is now
# closed, without weakening any legitimate, already-passing use (covered by every test above).
# ---------------------------------------------------------------------------------------------


class TestF08TimestampsMustBeTimezoneAware:
    def test_naive_transition_timestamp_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _transition(timestamp="2026-07-24T10:00:00")

    def test_naive_command_start_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _command(start_time="2026-07-24T10:00:00", completion_time="2026-07-24T10:00:01+00:00")

    def test_naive_command_completion_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _command(start_time="2026-07-24T10:00:00+00:00", completion_time="2026-07-24T10:00:01")

    def test_aware_timestamps_still_accepted(self) -> None:
        _transition(timestamp="2026-07-24T10:00:00+00:00")
        _command(
            start_time="2026-07-24T10:00:00+00:00", completion_time="2026-07-24T10:00:01+00:00"
        )


class TestF08CommandCompletionNotBeforeStart:
    def test_completion_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _command(
                start_time="2026-07-24T10:05:00+00:00", completion_time="2026-07-24T10:00:00+00:00"
            )

    def test_completion_equal_to_start_accepted(self) -> None:
        # A command that starts and finishes within the same recorded instant is legitimate
        # (e.g. a coarse timestamp granularity), never an inconsistency.
        _command(
            start_time="2026-07-24T10:00:00+00:00", completion_time="2026-07-24T10:00:00+00:00"
        )

    def test_completion_after_start_accepted(self) -> None:
        _command(
            start_time="2026-07-24T10:00:00+00:00", completion_time="2026-07-24T10:00:05+00:00"
        )


class TestF08AuditRefPathConfinement:
    """`stdout_ref`/`stderr_ref` (`AUDIT_MODEL.md` §2: "a reference... under the audit
    directory") previously accepted any nonblank string, including one that would resolve
    outside the audit directory entirely."""

    def test_absolute_stdout_ref_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandExecutionRecord(
                normalized_command_identity="run_tests",
                start_time="2026-07-24T10:00:00+00:00",
                completion_time="2026-07-24T10:00:01+00:00",
                exit_code=0,
                timeout_status=False,
                stdout_ref="/etc/passwd",
                stderr_ref="stderr/run_tests-1.log",
            )

    def test_absolute_stderr_ref_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandExecutionRecord(
                normalized_command_identity="run_tests",
                start_time="2026-07-24T10:00:00+00:00",
                completion_time="2026-07-24T10:00:01+00:00",
                exit_code=0,
                timeout_status=False,
                stdout_ref="stdout/run_tests-1.log",
                stderr_ref="/etc/shadow",
            )

    def test_parent_traversal_stdout_ref_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandExecutionRecord(
                normalized_command_identity="run_tests",
                start_time="2026-07-24T10:00:00+00:00",
                completion_time="2026-07-24T10:00:01+00:00",
                exit_code=0,
                timeout_status=False,
                stdout_ref="../../../etc/passwd",
                stderr_ref="stderr/run_tests-1.log",
            )

    def test_embedded_parent_traversal_segment_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandExecutionRecord(
                normalized_command_identity="run_tests",
                start_time="2026-07-24T10:00:00+00:00",
                completion_time="2026-07-24T10:00:01+00:00",
                exit_code=0,
                timeout_status=False,
                stdout_ref="stdout/../../escape.log",
                stderr_ref="stderr/run_tests-1.log",
            )

    def test_nul_byte_ref_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandExecutionRecord(
                normalized_command_identity="run_tests",
                start_time="2026-07-24T10:00:00+00:00",
                completion_time="2026-07-24T10:00:01+00:00",
                exit_code=0,
                timeout_status=False,
                stdout_ref="stdout/run_tests-1.log\x00.png",
                stderr_ref="stderr/run_tests-1.log",
            )

    def test_safe_relative_ref_still_accepted(self) -> None:
        _command()


class TestF08TransitionIdentityCrossCheckedOnRead:
    """A `StateTransitionRecord`'s own `workflow_id` field must agree with the file it is read
    from — the only binding between a persisted record and the workflow it claims to belong to,
    if a record were ever appended (by a bug, a race, or direct tampering) into the wrong file.
    """

    def test_matching_identity_reads_normally(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(workflow_id="wf-1"))
        assert len(store.read_transitions("wf-1")) == 1

    def test_mismatched_identity_rejected_on_read(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.parent.mkdir(parents=True)
        mismatched = _transition(workflow_id="wf-other")
        path.write_text(mismatched.model_dump_json() + "\n", encoding="utf-8")
        with pytest.raises(StateStoreCorruptionError):
            store.read_transitions("wf-1")

    def test_on_disk_file_left_untouched_after_rejection(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.parent.mkdir(parents=True)
        mismatched = _transition(workflow_id="wf-other")
        before = mismatched.model_dump_json() + "\n"
        path.write_text(before, encoding="utf-8")
        with pytest.raises(StateStoreCorruptionError):
            store.read_transitions("wf-1")
        assert path.read_text(encoding="utf-8") == before


class TestF08MonotonicTimestampOrdering:
    """A real append-only writer can never itself produce an out-of-order file (every append is
    serialized by `flock` for its entire write-fsync sequence); timestamps going backwards across
    a persisted sequence is evidence of tampering or corruption, not a legitimate scenario."""

    def test_in_order_transitions_read_normally(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(
            _transition(
                from_state="CREATED", to_state="AUTHORIZED", timestamp="2026-07-24T10:00:00+00:00"
            )
        )
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:05+00:00",
            )
        )
        assert len(store.read_transitions("wf-1")) == 2

    def test_out_of_order_transitions_rejected_on_read(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.parent.mkdir(parents=True)
        lines = [
            _transition(
                from_state="CREATED", to_state="AUTHORIZED", timestamp="2026-07-24T10:00:10+00:00"
            ).model_dump_json(),
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T09:00:00+00:00",
            ).model_dump_json(),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(StateStoreCorruptionError):
            store.read_transitions("wf-1")

    def test_equal_consecutive_timestamps_accepted(self, tmp_path: Path) -> None:
        # Two events recorded at the same instant (coarse timestamp granularity) are legitimate —
        # only strictly *decreasing* order is corruption.
        store = _make_store(tmp_path)
        store.record_transition(
            _transition(
                from_state="CREATED", to_state="AUTHORIZED", timestamp="2026-07-24T10:00:00+00:00"
            )
        )
        store.record_transition(
            _transition(
                from_state="AUTHORIZED",
                to_state="PRECONDITIONS_CHECKED",
                timestamp="2026-07-24T10:00:00+00:00",
            )
        )
        assert len(store.read_transitions("wf-1")) == 2

    def test_out_of_order_command_executions_rejected_on_read(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        path = tmp_path / "audit" / "wf-1" / "commands.jsonl"
        path.parent.mkdir(parents=True)
        lines = [
            _command(
                start_time="2026-07-24T10:00:00+00:00", completion_time="2026-07-24T10:00:10+00:00"
            ).model_dump_json(),
            _command(
                start_time="2026-07-24T09:00:00+00:00", completion_time="2026-07-24T09:00:05+00:00"
            ).model_dump_json(),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(StateStoreCorruptionError):
            store.read_command_executions("wf-1")


class TestAUTO002IR02RecordsCannotEscapeConfiguredRootViaSymlink:
    """AUTO002-IR-02: `_safe_workflow_id` validated the workflow identifier as a safe path
    *component*, but the component was still joined lexically and opened by path. An independent
    review reproduced a symlinked `<root>/<workflow_id>` directory being followed at append time,
    writing audit records outside the configured root. Every state and audit record must remain
    physically under its configured canonical root, for reads as well as writes.
    """

    @staticmethod
    def _external_symlinked_workflow_directory(
        tmp_path: Path, *, root_name: str, external_name: str
    ) -> tuple[Path, Path]:
        root = tmp_path / root_name
        root.mkdir()
        external = tmp_path / external_name
        external.mkdir()
        (root / "wf-1").symlink_to(external, target_is_directory=True)
        return root, external

    def test_transition_write_rejected_through_symlinked_workflow_directory(
        self, tmp_path: Path
    ) -> None:
        state, external = self._external_symlinked_workflow_directory(
            tmp_path, root_name="state", external_name="ext-state"
        )
        store = StateStore(state_directory=state, audit_directory=tmp_path / "audit")

        with pytest.raises(StateStorePathConfinementError):
            store.record_transition(_transition())

        # No external target existed: none may be created.
        assert list(external.iterdir()) == []

    def test_command_write_rejected_through_symlinked_workflow_directory(
        self, tmp_path: Path
    ) -> None:
        audit, external = self._external_symlinked_workflow_directory(
            tmp_path, root_name="audit", external_name="ext-audit"
        )
        store = StateStore(state_directory=tmp_path / "state", audit_directory=audit)

        with pytest.raises(StateStorePathConfinementError):
            store.record_command_execution("wf-1", _command())

        assert list(external.iterdir()) == []

    def test_existing_external_transition_target_left_byte_identical(self, tmp_path: Path) -> None:
        state, external = self._external_symlinked_workflow_directory(
            tmp_path, root_name="state", external_name="ext-state"
        )
        sentinel = external / "transitions.jsonl"
        sentinel.write_bytes(b"SENTINEL-EXTERNAL-STATE\n")
        sentinel_mtime = sentinel.stat().st_mtime_ns
        store = StateStore(state_directory=state, audit_directory=tmp_path / "audit")

        with pytest.raises(StateStorePathConfinementError):
            store.record_transition(_transition())

        assert sentinel.read_bytes() == b"SENTINEL-EXTERNAL-STATE\n"
        assert sentinel.stat().st_mtime_ns == sentinel_mtime

    def test_existing_external_command_target_left_byte_identical(self, tmp_path: Path) -> None:
        audit, external = self._external_symlinked_workflow_directory(
            tmp_path, root_name="audit", external_name="ext-audit"
        )
        sentinel = external / "commands.jsonl"
        sentinel.write_bytes(b"SENTINEL-EXTERNAL-AUDIT\n")
        sentinel_mtime = sentinel.stat().st_mtime_ns
        store = StateStore(state_directory=tmp_path / "state", audit_directory=audit)

        with pytest.raises(StateStorePathConfinementError):
            store.record_command_execution("wf-1", _command())

        assert sentinel.read_bytes() == b"SENTINEL-EXTERNAL-AUDIT\n"
        assert sentinel.stat().st_mtime_ns == sentinel_mtime

    def test_symlinked_workflow_directory_is_not_replaced_by_a_real_directory(
        self, tmp_path: Path
    ) -> None:
        state, _external = self._external_symlinked_workflow_directory(
            tmp_path, root_name="state", external_name="ext-state"
        )
        store = StateStore(state_directory=state, audit_directory=tmp_path / "audit")

        with pytest.raises(StateStorePathConfinementError):
            store.record_transition(_transition())

        assert (state / "wf-1").is_symlink()

    def test_symlinked_transition_file_inside_real_workflow_directory_is_rejected(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        (state / "wf-1").mkdir(parents=True)
        external = tmp_path / "ext-transitions.jsonl"
        external.write_bytes(b"SENTINEL-EXTERNAL\n")
        (state / "wf-1" / "transitions.jsonl").symlink_to(external)
        store = StateStore(state_directory=state, audit_directory=tmp_path / "audit")

        with pytest.raises(StateStorePathConfinementError):
            store.record_transition(_transition())

        assert external.read_bytes() == b"SENTINEL-EXTERNAL\n"

    def test_symlinked_command_file_inside_real_workflow_directory_is_rejected(
        self, tmp_path: Path
    ) -> None:
        audit = tmp_path / "audit"
        (audit / "wf-1").mkdir(parents=True)
        external = tmp_path / "ext-commands.jsonl"
        external.write_bytes(b"SENTINEL-EXTERNAL\n")
        (audit / "wf-1" / "commands.jsonl").symlink_to(external)
        store = StateStore(state_directory=tmp_path / "state", audit_directory=audit)

        with pytest.raises(StateStorePathConfinementError):
            store.record_command_execution("wf-1", _command())

        assert external.read_bytes() == b"SENTINEL-EXTERNAL\n"

    def test_reads_are_confined_too_and_never_replay_external_history(self, tmp_path: Path) -> None:
        state, external = self._external_symlinked_workflow_directory(
            tmp_path, root_name="state", external_name="ext-state"
        )
        # A plausible-looking but externally-planted history must never be replayed as if it were
        # this root's own: `current_state` would otherwise trust attacker-chosen state.
        (external / "transitions.jsonl").write_text(
            _transition(to_state="MERGED").model_dump_json() + "\n", encoding="utf-8"
        )
        store = StateStore(state_directory=state, audit_directory=tmp_path / "audit")

        with pytest.raises(StateStorePathConfinementError):
            store.read_transitions("wf-1")
        with pytest.raises(StateStorePathConfinementError):
            store.current_state("wf-1")

    def test_confinement_error_is_a_state_store_error_but_not_corruption(
        self, tmp_path: Path
    ) -> None:
        state, _unused = self._external_symlinked_workflow_directory(
            tmp_path, root_name="state", external_name="ext-state"
        )
        store = StateStore(state_directory=state, audit_directory=tmp_path / "audit")

        with pytest.raises(StateStoreError) as caught:
            store.record_transition(_transition())
        # Taxonomy: the records are well-formed; the defect is *where* the path points.
        assert isinstance(caught.value, StateStorePathConfinementError)
        assert not isinstance(caught.value, StateStoreCorruptionError)

    def test_ordinary_nested_storage_and_reopen_still_work(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))
        store.record_transition(
            _transition(
                from_state="AUTHORIZED", to_state="EXECUTING", timestamp="2026-07-24T10:00:01+00:00"
            )
        )
        store.record_command_execution("wf-1", _command())

        transitions_path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        commands_path = tmp_path / "audit" / "wf-1" / "commands.jsonl"
        assert transitions_path.is_file() and not transitions_path.is_symlink()
        assert commands_path.is_file() and not commands_path.is_symlink()

        reopened = _make_store(tmp_path)
        assert [record.to_state for record in reopened.read_transitions("wf-1")] == [
            "AUTHORIZED",
            "EXECUTING",
        ]
        assert reopened.current_state("wf-1") == "EXECUTING"
        assert len(reopened.read_command_executions("wf-1")) == 1


class TestAUTO002IR04WriterEnforcesChronologicalOrder:
    """AUTO002-IR-04: the public writer accepted a record older than the one already persisted.
    The append succeeded, and `_require_monotonic_order` then rejected the entire history on every
    subsequent read — the store could be driven into a permanently unreadable state through its
    own supported API. Anything successfully written through the supported writer must remain
    replayable by the supported reader. The rule is the reader's own: timestamps must be
    non-decreasing, so equal timestamps are accepted and only a strictly earlier one is refused.
    """

    def test_transition_append_with_older_timestamp_is_rejected(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:05+00:00"))
        with pytest.raises(StateStoreOrderingError):
            store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))

    def test_command_append_with_older_completion_time_is_rejected(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_command_execution(
            "wf-1",
            _command(
                start_time="2026-07-24T10:00:04+00:00",
                completion_time="2026-07-24T10:00:05+00:00",
            ),
        )
        with pytest.raises(StateStoreOrderingError):
            store.record_command_execution(
                "wf-1",
                _command(
                    start_time="2026-07-24T09:59:59+00:00",
                    completion_time="2026-07-24T10:00:00+00:00",
                ),
            )

    def test_rejected_transition_append_leaves_original_bytes_unchanged(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:05+00:00"))
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        before = path.read_bytes()

        with pytest.raises(StateStoreOrderingError):
            store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))

        assert path.read_bytes() == before

    def test_rejected_command_append_leaves_original_bytes_unchanged(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_command_execution("wf-1", _command())
        path = tmp_path / "audit" / "wf-1" / "commands.jsonl"
        before = path.read_bytes()

        with pytest.raises(StateStoreOrderingError):
            store.record_command_execution(
                "wf-1",
                _command(
                    start_time="2026-07-24T09:00:00+00:00",
                    completion_time="2026-07-24T09:00:01+00:00",
                ),
            )

        assert path.read_bytes() == before

    def test_history_still_replayable_after_a_rejected_append(self, tmp_path: Path) -> None:
        # The whole point of IR-04: a rejection must never leave the store unreadable.
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:05+00:00"))
        with pytest.raises(StateStoreOrderingError):
            store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))

        reopened = _make_store(tmp_path)
        assert len(reopened.read_transitions("wf-1")) == 1
        assert reopened.current_state("wf-1") == "AUTHORIZED"

    def test_equal_timestamps_are_accepted_matching_the_reader_rule(self, tmp_path: Path) -> None:
        # Explicit rule: non-decreasing, not strictly increasing — the reader accepts equal
        # timestamps, so the writer must too, or writer and reader would disagree.
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))
        store.record_transition(
            _transition(from_state="AUTHORIZED", timestamp="2026-07-24T10:00:00+00:00")
        )
        store.record_command_execution("wf-1", _command())
        store.record_command_execution("wf-1", _command())

        assert len(store.read_transitions("wf-1")) == 2
        assert len(store.read_command_executions("wf-1")) == 2

    def test_equal_timestamps_expressed_in_a_different_offset_are_accepted(
        self, tmp_path: Path
    ) -> None:
        # Ordering compares instants, not strings: 10:00:00+00:00 and 11:00:00+01:00 are equal.
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))
        store.record_transition(
            _transition(from_state="AUTHORIZED", timestamp="2026-07-24T11:00:00+01:00")
        )
        assert len(store.read_transitions("wf-1")) == 2

    def test_first_append_to_empty_history_has_no_ordering_constraint(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2020-01-01T00:00:00+00:00"))
        assert len(store.read_transitions("wf-1")) == 1

    def test_append_to_an_existing_empty_file_has_no_ordering_constraint(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")
        store = _make_store(tmp_path)
        store.record_transition(_transition())
        assert len(store.read_transitions("wf-1")) == 1

    @pytest.mark.parametrize(
        "tail",
        [
            b"not json at all\n",
            b'{"timestamp": "not-a-timestamp"}\n',
            b'{"no_timestamp_field": 1}\n',
            b'{"timestamp": "2026-07-24T10:00:00+00:00"}',  # no terminal newline: torn append
            b'{"timestamp": "2026-07-24T10:00:00+00:00"}\n\n',
        ],
    )
    def test_append_onto_malformed_history_fails_closed_without_writing(
        self, tmp_path: Path, tail: bytes
    ) -> None:
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.parent.mkdir(parents=True)
        path.write_bytes(tail)
        store = _make_store(tmp_path)

        with pytest.raises(StateStoreCorruptionError):
            store.record_transition(_transition(timestamp="2030-01-01T00:00:00+00:00"))

        # Extending a history that cannot be replayed would only deepen the damage.
        assert path.read_bytes() == tail

    def test_ordering_is_enforced_across_a_reopened_store(self, tmp_path: Path) -> None:
        _make_store(tmp_path).record_transition(_transition(timestamp="2026-07-24T10:00:05+00:00"))
        restarted = _make_store(tmp_path)
        with pytest.raises(StateStoreOrderingError):
            restarted.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))
        assert len(restarted.read_transitions("wf-1")) == 1

    def test_ordering_error_is_a_state_store_error_but_not_corruption(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record_transition(_transition(timestamp="2026-07-24T10:00:05+00:00"))
        with pytest.raises(StateStoreError) as caught:
            store.record_transition(_transition(timestamp="2026-07-24T10:00:00+00:00"))
        # Nothing on disk is wrong; the submitted record is.
        assert isinstance(caught.value, StateStoreOrderingError)
        assert not isinstance(caught.value, StateStoreCorruptionError)

    def test_monotonic_appends_across_both_histories_still_succeed(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        for second in range(5):
            store.record_transition(_transition(timestamp=f"2026-07-24T10:00:0{second}+00:00"))
            store.record_command_execution(
                "wf-1",
                _command(
                    start_time=f"2026-07-24T10:00:0{second}+00:00",
                    completion_time=f"2026-07-24T10:00:0{second}+00:00",
                ),
            )
        assert len(store.read_transitions("wf-1")) == 5
        assert len(store.read_command_executions("wf-1")) == 5


def _transition_json(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "workflow_id": "wf-1",
        "target_repository": "github.com/org/repo",
        "repository_path": "/tmp/agentos-test-fixture-repo",
        "stage_id": "AUTO-002",
        "from_state": "CREATED",
        "to_state": "AUTHORIZED",
        "timestamp": "2026-07-24T10:00:00+00:00",
        "actor": "human",
        "gate_evidence_ref": None,
    }
    payload.update(overrides)
    return payload


def _with_duplicate_key(payload: dict[str, object], key: str, second_value: str) -> str:
    """Serialize `payload` with `key` emitted twice — a shape `json.dumps` cannot produce."""
    body = json.dumps(payload)[1:-1]
    return "{" + f"{json.dumps(key)}: {json.dumps(second_value)}, " + body + "}"


class TestAUTO002IR05DuplicateJSONKeysRejected:
    """AUTO002-IR-05: standard JSON parsing accepts duplicate object keys with last-key-wins
    semantics, so a tampered record carrying two `to_state` or `timestamp` values was replayed as
    whichever value the parser happened to keep — silently, and with no single correct reading.
    Independently reproduced: a duplicate `to_state` replayed as `MERGED`, and a duplicate
    `timestamp` drove the persisted history backwards in time. Ambiguous persisted records must
    fail closed, as `StateStoreCorruptionError`, before model validation.
    """

    @staticmethod
    def _write_transitions(tmp_path: Path, *lines: str) -> Path:
        path = tmp_path / "state" / "wf-1" / "transitions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return path

    @staticmethod
    def _write_commands(tmp_path: Path, *lines: str) -> Path:
        path = tmp_path / "audit" / "wf-1" / "commands.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return path

    def test_duplicate_workflow_id_rejected(self, tmp_path: Path) -> None:
        self._write_transitions(
            tmp_path, _with_duplicate_key(_transition_json(), "workflow_id", "wf-1")
        )
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            _make_store(tmp_path).read_transitions("wf-1")

    def test_duplicate_timestamp_rejected(self, tmp_path: Path) -> None:
        # Last-key-wins previously let this rewrite the record's position in time.
        self._write_transitions(
            tmp_path,
            _with_duplicate_key(_transition_json(), "timestamp", "2020-01-01T00:00:00+00:00"),
        )
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            _make_store(tmp_path).read_transitions("wf-1")

    def test_duplicate_other_top_level_field_rejected(self, tmp_path: Path) -> None:
        # `to_state` is what `current_state` replays, so last-key-wins was state-machine relevant.
        self._write_transitions(
            tmp_path, _with_duplicate_key(_transition_json(), "to_state", "MERGED")
        )
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            _make_store(tmp_path).read_transitions("wf-1")

    def test_duplicate_key_in_a_nested_object_rejected(self, tmp_path: Path) -> None:
        # Nested duplicates are only detectable via `object_pairs_hook`; a top-level-only check
        # would pass this straight through.
        nested = (
            '{"workflow_id": "wf-1", "target_repository": "github.com/org/repo", '
            '"repository_path": "/tmp/r", "stage_id": "AUTO-002", "from_state": "CREATED", '
            '"to_state": "AUTHORIZED", "timestamp": "2026-07-24T10:00:00+00:00", '
            '"actor": "human", "gate_evidence_ref": {"ref": "a", "ref": "b"}}'
        )
        self._write_transitions(tmp_path, nested)
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            _make_store(tmp_path).read_transitions("wf-1")

    def test_duplicate_key_in_command_history_rejected(self, tmp_path: Path) -> None:
        command = json.loads(_command().model_dump_json())
        self._write_commands(
            tmp_path, _with_duplicate_key(command, "completion_time", "2026-07-24T10:00:09+00:00")
        )
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            _make_store(tmp_path).read_command_executions("wf-1")

    def test_duplicate_key_on_the_first_line_rejected(self, tmp_path: Path) -> None:
        path = self._write_transitions(
            tmp_path,
            _with_duplicate_key(_transition_json(), "to_state", "MERGED"),
            json.dumps(_transition_json(timestamp="2026-07-24T10:00:05+00:00")),
        )
        with pytest.raises(StateStoreCorruptionError) as caught:
            _make_store(tmp_path).read_transitions("wf-1")
        assert f"{path}:1" in str(caught.value)

    def test_duplicate_key_on_a_later_line_rejected_with_line_context(self, tmp_path: Path) -> None:
        path = self._write_transitions(
            tmp_path,
            json.dumps(_transition_json()),
            json.dumps(_transition_json(timestamp="2026-07-24T10:00:05+00:00")),
            _with_duplicate_key(
                _transition_json(timestamp="2026-07-24T10:00:09+00:00"), "to_state", "MERGED"
            ),
        )
        with pytest.raises(StateStoreCorruptionError) as caught:
            _make_store(tmp_path).read_transitions("wf-1")
        message = str(caught.value)
        assert f"{path}:3" in message
        # Useful context, without dumping the surrounding records' contents.
        assert "to_state" in message
        assert "github.com/org/repo" not in message

    def test_valid_neighbouring_records_do_not_mask_the_duplicate(self, tmp_path: Path) -> None:
        self._write_transitions(
            tmp_path,
            json.dumps(_transition_json()),
            _with_duplicate_key(
                _transition_json(timestamp="2026-07-24T10:00:05+00:00"), "actor", "orchestrator"
            ),
            json.dumps(_transition_json(timestamp="2026-07-24T10:00:09+00:00")),
        )
        # Never a quiet partial read that looks complete.
        with pytest.raises(StateStoreCorruptionError):
            _make_store(tmp_path).read_transitions("wf-1")

    def test_raised_exception_is_a_state_store_corruption_error(self, tmp_path: Path) -> None:
        self._write_transitions(
            tmp_path, _with_duplicate_key(_transition_json(), "to_state", "MERGED")
        )
        with pytest.raises(StateStoreError) as caught:
            _make_store(tmp_path).read_transitions("wf-1")
        assert isinstance(caught.value, StateStoreCorruptionError)

    def test_current_state_never_replays_an_ambiguous_record(self, tmp_path: Path) -> None:
        self._write_transitions(
            tmp_path, _with_duplicate_key(_transition_json(), "to_state", "MERGED")
        )
        with pytest.raises(StateStoreCorruptionError):
            _make_store(tmp_path).current_state("wf-1")

    def test_writer_refuses_to_append_onto_an_ambiguous_final_record(self, tmp_path: Path) -> None:
        path = self._write_transitions(
            tmp_path, _with_duplicate_key(_transition_json(), "to_state", "MERGED")
        )
        before = path.read_bytes()
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            _make_store(tmp_path).record_transition(
                _transition(timestamp="2030-01-01T00:00:00+00:00")
            )
        assert path.read_bytes() == before

    def test_records_without_duplicates_are_unaffected(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        first = _transition()
        second = _transition(from_state="AUTHORIZED", timestamp="2026-07-24T10:00:05+00:00")
        store.record_transition(first)
        store.record_transition(second)
        store.record_command_execution("wf-1", _command())

        assert store.read_transitions("wf-1") == [first, second]
        assert store.read_command_executions("wf-1") == [_command()]
        assert store.current_state("wf-1") == "AUTHORIZED"
