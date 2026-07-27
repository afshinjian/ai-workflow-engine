"""Tests for agentos_workflow.orchestrator.lock (ARCHITECTURE.md §5; OPEN_QUESTIONS.md OD-3)."""

import multiprocessing as mp
import os
from pathlib import Path

import pytest

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator.lock import (
    DEFAULT_LOCK_FILENAME,
    LockContentionError,
    LockMetadata,
    LockPathConfinementError,
    LockStateError,
    RepositoryLock,
    canonical_lock_path,
)


def _make_lock(
    tmp_path: Path,
    *,
    workflow_id: str = "wf-1",
    repository_identity: str = "github.com/org/repo",
) -> RepositoryLock:
    return RepositoryLock(
        workflow_id=workflow_id,
        repository_identity=repository_identity,
        repository_path=tmp_path,
    )


def _valid_config_dict(repository_path: Path, state_directory: Path) -> dict[str, object]:
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
        "state_directory": str(state_directory),
        "audit_directory": str(state_directory / "audit"),
    }


class TestAcquireAndRelease:
    def test_acquire_creates_lock_file_and_metadata(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path, workflow_id="wf-42")
        assert not lock.is_held
        lock.acquire()
        try:
            assert lock.is_held
            assert lock.lock_path.is_file()
            metadata = lock.read_metadata()
            assert metadata is not None
            assert metadata.workflow_id == "wf-42"
            assert metadata.process_id == os.getpid()
            assert metadata.repository_identity == "github.com/org/repo"
            assert metadata.repository_path == str(tmp_path)
            assert metadata.acquired_at  # non-empty ISO-8601 timestamp
        finally:
            lock.release()

    def test_release_clears_held_state(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        lock.acquire()
        lock.release()
        assert not lock.is_held

    def test_release_is_idempotent(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        lock.acquire()
        lock.release()
        lock.release()  # must not raise
        assert not lock.is_held

    def test_double_acquire_same_instance_rejected(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        lock.acquire()
        try:
            with pytest.raises(LockStateError):
                lock.acquire()
        finally:
            lock.release()

    def test_reacquire_after_release_succeeds(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        lock.acquire()
        lock.release()
        lock.acquire()
        lock.release()


class TestSameRepositoryContention:
    def test_second_instance_rejected_while_first_holds(self, tmp_path: Path) -> None:
        first = _make_lock(tmp_path, workflow_id="wf-first")
        second = _make_lock(tmp_path, workflow_id="wf-second")
        first.acquire()
        try:
            with pytest.raises(LockContentionError):
                second.acquire()
            assert not second.is_held
        finally:
            first.release()

    def test_second_instance_succeeds_after_first_releases(self, tmp_path: Path) -> None:
        first = _make_lock(tmp_path, workflow_id="wf-first")
        second = _make_lock(tmp_path, workflow_id="wf-second")
        first.acquire()
        first.release()
        second.acquire()
        try:
            metadata = second.read_metadata()
            assert metadata is not None
            assert metadata.workflow_id == "wf-second"
        finally:
            second.release()


class TestDifferentRepositoriesIndependent:
    def test_locks_for_different_repositories_do_not_block(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "repo-a"
        repo_b = tmp_path / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        lock_a = _make_lock(repo_a, workflow_id="wf-a", repository_identity="org/repo-a")
        lock_b = _make_lock(repo_b, workflow_id="wf-b", repository_identity="org/repo-b")
        lock_a.acquire()
        try:
            lock_b.acquire()  # must not raise LockContentionError
            lock_b.release()
        finally:
            lock_a.release()


class TestStaleMetadataHandling:
    def test_stale_metadata_alone_does_not_block_acquisition(self, tmp_path: Path) -> None:
        lock_path = canonical_lock_path(tmp_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        stale = LockMetadata(
            workflow_id="wf-dead",
            process_id=999_999,  # not a live process; must never be trusted as proof
            hostname="stale-host",
            repository_identity="github.com/org/repo",
            repository_path=str(tmp_path),
            acquired_at="2020-01-01T00:00:00+00:00",
        )
        lock_path.write_text(stale.model_dump_json(), encoding="utf-8")

        lock = _make_lock(tmp_path, workflow_id="wf-fresh")
        lock.acquire()  # must succeed: no live flock holder, stale content is irrelevant
        try:
            metadata = lock.read_metadata()
            assert metadata is not None
            assert metadata.workflow_id == "wf-fresh"  # overwritten, not preserved
        finally:
            lock.release()

    def test_read_metadata_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        assert lock.read_metadata() is None

    def test_read_metadata_returns_none_for_unparseable_file(self, tmp_path: Path) -> None:
        lock_path = canonical_lock_path(tmp_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("not json", encoding="utf-8")
        lock = _make_lock(tmp_path)
        assert lock.read_metadata() is None

    def test_release_never_deletes_the_lock_file(self, tmp_path: Path) -> None:
        # A stale-but-present file is always safely reusable by the next acquire(); deleting on
        # release would reopen the unlink/flock race the module docstring documents.
        lock = _make_lock(tmp_path)
        lock.acquire()
        lock.release()
        assert lock.lock_path.is_file()


class TestContextManagerUsage:
    def test_context_manager_acquires_and_releases(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        with lock as held:
            assert held is lock
            assert lock.is_held
        assert not lock.is_held

    def test_context_manager_releases_on_exception(self, tmp_path: Path) -> None:
        lock = _make_lock(tmp_path)
        with pytest.raises(ValueError):
            with lock:
                raise ValueError("boom")
        assert not lock.is_held

    def test_context_manager_second_instance_contends(self, tmp_path: Path) -> None:
        first = _make_lock(tmp_path, workflow_id="wf-first")
        second = _make_lock(tmp_path, workflow_id="wf-second")
        with first:
            with pytest.raises(LockContentionError):
                second.acquire()


class TestForConfig:
    def test_for_config_derives_lock_path_from_canonical_repository_path(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        state_directory = tmp_path / "state"
        config = WorkflowConfig.model_validate(_valid_config_dict(repository_path, state_directory))
        lock = RepositoryLock.for_config(config, workflow_id="wf-config")
        # The lock path comes from the repository's own canonical path, never state_directory
        # (Finding 4: two configs for the same repository with different state_directory values
        # must still contend for the same lock).
        assert lock.lock_path == canonical_lock_path(repository_path)
        assert lock.lock_path != state_directory / "workflow.lock"
        lock.acquire()
        try:
            metadata = lock.read_metadata()
            assert metadata is not None
            assert metadata.workflow_id == "wf-config"
            assert metadata.repository_identity == config.repository_identity
        finally:
            lock.release()

    def test_for_config_ignores_state_directory_for_the_same_repository(
        self, tmp_path: Path
    ) -> None:
        # Finding 4's core defect: two configurations naming the *same* physical target
        # repository but different state_directory values must produce the identical lock path
        # (and so genuinely contend), not two independent, non-blocking locks.
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        config_a = WorkflowConfig.model_validate(
            _valid_config_dict(repository_path, tmp_path / "state-a")
        )
        config_b = WorkflowConfig.model_validate(
            _valid_config_dict(repository_path, tmp_path / "state-b")
        )
        lock_a = RepositoryLock.for_config(config_a, workflow_id="wf-a")
        lock_b = RepositoryLock.for_config(config_b, workflow_id="wf-b")
        assert lock_a.lock_path == lock_b.lock_path
        lock_a.acquire()
        try:
            with pytest.raises(LockContentionError):
                lock_b.acquire()
        finally:
            lock_a.release()

    def test_for_config_different_repositories_remain_non_blocking(self, tmp_path: Path) -> None:
        repository_a = tmp_path / "repo-a"
        repository_a.mkdir()
        repository_b = tmp_path / "repo-b"
        repository_b.mkdir()
        config_a = WorkflowConfig.model_validate(
            _valid_config_dict(repository_a, tmp_path / "state-a")
        )
        config_b = WorkflowConfig.model_validate(
            _valid_config_dict(repository_b, tmp_path / "state-b")
        )
        lock_a = RepositoryLock.for_config(config_a, workflow_id="wf-a")
        lock_b = RepositoryLock.for_config(config_b, workflow_id="wf-b")
        assert lock_a.lock_path != lock_b.lock_path
        lock_a.acquire()
        try:
            lock_b.acquire()  # must not raise: distinct repositories never contend
            lock_b.release()
        finally:
            lock_a.release()

    def test_symlink_alias_to_same_repository_produces_identical_lock_path(
        self, tmp_path: Path
    ) -> None:
        real_repository = tmp_path / "real-repo"
        real_repository.mkdir()
        alias = tmp_path / "alias-repo"
        alias.symlink_to(real_repository)
        assert canonical_lock_path(real_repository) == canonical_lock_path(alias)

    def test_for_config_symlink_alias_repositories_contend(self, tmp_path: Path) -> None:
        real_repository = tmp_path / "real-repo"
        real_repository.mkdir()
        alias = tmp_path / "alias-repo"
        alias.symlink_to(real_repository)
        config_real = WorkflowConfig.model_validate(
            _valid_config_dict(real_repository, tmp_path / "state-real")
        )
        config_alias = WorkflowConfig.model_validate(
            _valid_config_dict(alias, tmp_path / "state-alias")
        )
        lock_real = RepositoryLock.for_config(config_real, workflow_id="wf-real")
        lock_alias = RepositoryLock.for_config(config_alias, workflow_id="wf-alias")
        assert lock_real.lock_path == lock_alias.lock_path
        lock_real.acquire()
        try:
            with pytest.raises(LockContentionError):
                lock_alias.acquire()
        finally:
            lock_real.release()


class TestAUTO002F04CanonicalLockPathCannotBeBypassed:
    """AUTO002-F04: an earlier revision's public constructor accepted an arbitrary
    caller-selected `lock_path`, so two `RepositoryLock` instances for the identical canonical
    repository could point at two different files and both hold `flock` simultaneously —
    defeating "exactly one active workflow per target repository" (`ARCHITECTURE.md` §5) at the
    primitive level. The fix removes `lock_path` as a constructor input entirely; these tests
    prove there is no remaining way to construct a `RepositoryLock` bound to anything other than
    `canonical_lock_path(repository_path)`.
    """

    def test_constructor_no_longer_accepts_a_lock_path_argument(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            RepositoryLock(  # type: ignore[misc]
                tmp_path / "attacker-chosen.lock",  # type: ignore[arg-type]
                workflow_id="wf-1",
                repository_identity="github.com/org/repo",
                repository_path=tmp_path,
            )
        with pytest.raises(TypeError):
            RepositoryLock(  # type: ignore[call-arg]
                lock_path=tmp_path / "attacker-chosen.lock",
                workflow_id="wf-1",
                repository_identity="github.com/org/repo",
                repository_path=tmp_path,
            )

    def test_direct_construction_always_resolves_to_the_canonical_path(
        self, tmp_path: Path
    ) -> None:
        lock = RepositoryLock(
            workflow_id="wf-1",
            repository_identity="github.com/org/repo",
            repository_path=tmp_path,
        )
        assert lock.lock_path == canonical_lock_path(tmp_path)

    def test_direct_construction_and_for_config_are_identical_for_the_same_repository(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        state_directory = tmp_path / "state"
        config = WorkflowConfig.model_validate(_valid_config_dict(repository_path, state_directory))
        direct = RepositoryLock(
            workflow_id="wf-direct",
            repository_identity=config.repository_identity,
            repository_path=repository_path,
        )
        via_config = RepositoryLock.for_config(config, workflow_id="wf-config")
        assert direct.lock_path == via_config.lock_path == canonical_lock_path(repository_path)

    def test_two_directly_constructed_locks_for_the_same_repository_always_contend(
        self, tmp_path: Path
    ) -> None:
        # Even with entirely different workflow_id/repository_identity ("caller preference"),
        # two instances naming the same repository_path must land on one lock file and genuinely
        # contend — there is no parameter through which a second, independent lock could be
        # obtained for the same physical repository.
        first = RepositoryLock(
            workflow_id="wf-first",
            repository_identity="org/repo-as-seen-by-first",
            repository_path=tmp_path,
        )
        second = RepositoryLock(
            workflow_id="wf-second",
            repository_identity="org/repo-as-seen-by-second",
            repository_path=tmp_path,
        )
        assert first.lock_path == second.lock_path
        first.acquire()
        try:
            with pytest.raises(LockContentionError):
                second.acquire()
            assert not second.is_held
        finally:
            first.release()

    def test_direct_construction_via_symlink_alias_still_contends(self, tmp_path: Path) -> None:
        real_repository = tmp_path / "real-repo"
        real_repository.mkdir()
        alias = tmp_path / "alias-repo"
        alias.symlink_to(real_repository)
        real_lock = RepositoryLock(
            workflow_id="wf-real",
            repository_identity="github.com/org/repo",
            repository_path=real_repository,
        )
        alias_lock = RepositoryLock(
            workflow_id="wf-alias",
            repository_identity="github.com/org/repo",
            repository_path=alias,
        )
        assert real_lock.lock_path == alias_lock.lock_path
        real_lock.acquire()
        try:
            with pytest.raises(LockContentionError):
                alias_lock.acquire()
        finally:
            real_lock.release()


def _child_acquire_hold_and_wait(
    repository_path: Path,
    held_event: "mp.synchronize.Event",
    release_event: "mp.synchronize.Event",
) -> None:
    lock = RepositoryLock(
        workflow_id="wf-child",
        repository_identity="github.com/org/repo",
        repository_path=repository_path,
    )
    lock.acquire()
    held_event.set()
    release_event.wait(timeout=10)
    lock.release()


def _child_acquire_via_config_hold_and_wait(
    repository_path: Path,
    state_directory: Path,
    held_event: "mp.synchronize.Event",
    release_event: "mp.synchronize.Event",
) -> None:
    config = WorkflowConfig.model_validate(_valid_config_dict(repository_path, state_directory))
    lock = RepositoryLock.for_config(config, workflow_id="wf-child")
    lock.acquire()
    held_event.set()
    release_event.wait(timeout=10)
    lock.release()


class TestCrossProcessContention:
    def test_for_config_same_repository_different_state_directories_contend_across_real_processes(
        self, tmp_path: Path
    ) -> None:
        # The genuine-concurrency counterpart to test_for_config_ignores_state_directory_for_
        # the_same_repository: two real OS processes, each configured with a *different*
        # state_directory but the *same* repository_path, must still contend for one lock.
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        ctx = mp.get_context("fork")
        held_event = ctx.Event()
        release_event = ctx.Event()
        child = ctx.Process(
            target=_child_acquire_via_config_hold_and_wait,
            args=(repository_path, tmp_path / "state-child", held_event, release_event),
        )
        child.start()
        try:
            assert held_event.wait(timeout=10), "child process never acquired the lock"
            config = WorkflowConfig.model_validate(
                _valid_config_dict(repository_path, tmp_path / "state-parent")
            )
            contender = RepositoryLock.for_config(config, workflow_id="wf-parent")
            with pytest.raises(LockContentionError):
                contender.acquire()
        finally:
            release_event.set()
            child.join(timeout=10)
        assert child.exitcode == 0

    def test_flock_is_enforced_across_real_processes(self, tmp_path: Path) -> None:
        # A same-process second-instance test only proves this module's own bookkeeping; this
        # test proves genuine OS-level exclusion (requirement: do not rely only on PID existence
        # as the mutual-exclusion mechanism) by holding the lock in a separate real process.
        ctx = mp.get_context("fork")
        held_event = ctx.Event()
        release_event = ctx.Event()
        child = ctx.Process(
            target=_child_acquire_hold_and_wait,
            args=(tmp_path, held_event, release_event),
        )
        child.start()
        try:
            assert held_event.wait(timeout=10), "child process never acquired the lock"
            contender = _make_lock(tmp_path, workflow_id="wf-parent")
            with pytest.raises(LockContentionError):
                contender.acquire()
        finally:
            release_event.set()
            child.join(timeout=10)
        assert child.exitcode == 0

        # Once the child process exits (and its OS-held flock is released with it), a fresh
        # acquisition must succeed.
        after = _make_lock(tmp_path, workflow_id="wf-after")
        after.acquire()
        after.release()


class TestAcquireFailureCleanup:
    """A failure while writing lock metadata — after the OS-level flock is already held — must
    never leak the fd or the flock (stage contract requirement 5). Each test proves this two
    ways: `lock.is_held` is False immediately after the failure, and a *fresh* acquisition on
    the same path succeeds afterward, which is only possible if the OS-level flock was actually
    released, not merely that this instance's own bookkeeping looks clean.
    """

    def test_write_failure_releases_flock_and_fd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lock = _make_lock(tmp_path)

        def _raise_on_write(fd: int, data: bytes) -> int:
            raise OSError("simulated disk-full failure while writing lock metadata")

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.lock.os.write", _raise_on_write)
            with pytest.raises(OSError):
                lock.acquire()
        assert not lock.is_held

        recovery_lock = _make_lock(tmp_path)
        recovery_lock.acquire()
        recovery_lock.release()

    def test_short_write_still_persists_complete_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POSIX permits `os.write` to write fewer bytes than requested. Simulate a one-byte-at-
        a-time short write and confirm the full, valid metadata JSON is still persisted intact —
        never silently truncated.
        """
        lock = _make_lock(tmp_path)
        real_os_write = os.write

        def _one_byte_at_a_time(fd: int, data: bytes) -> int:
            return real_os_write(fd, data[:1]) if data else 0

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.lock.os.write", _one_byte_at_a_time)
            lock.acquire()
        try:
            metadata = lock.read_metadata()
            assert metadata is not None
            assert metadata.workflow_id == "wf-1"
        finally:
            lock.release()

    def test_fsync_failure_releases_flock_and_fd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lock = _make_lock(tmp_path)

        def _raise_on_fsync(fd: int) -> None:
            raise OSError("simulated fsync failure")

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.lock.os.fsync", _raise_on_fsync)
            with pytest.raises(OSError):
                lock.acquire()
        assert not lock.is_held

        recovery_lock = _make_lock(tmp_path)
        recovery_lock.acquire()
        recovery_lock.release()

    def test_metadata_construction_failure_releases_flock_and_fd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lock = _make_lock(tmp_path)

        def _raise_on_gethostname() -> str:
            raise OSError("simulated hostname lookup failure")

        with monkeypatch.context() as patched:
            patched.setattr(
                "agentos_workflow.orchestrator.lock.socket.gethostname", _raise_on_gethostname
            )
            with pytest.raises(OSError):
                lock.acquire()
        assert not lock.is_held

        recovery_lock = _make_lock(tmp_path)
        recovery_lock.acquire()
        recovery_lock.release()

    def test_ftruncate_failure_releases_flock_and_fd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lock = _make_lock(tmp_path)

        def _raise_on_ftruncate(fd: int, length: int) -> None:
            raise OSError("simulated ftruncate failure")

        with monkeypatch.context() as patched:
            patched.setattr("agentos_workflow.orchestrator.lock.os.ftruncate", _raise_on_ftruncate)
            with pytest.raises(OSError):
                lock.acquire()
        assert not lock.is_held

        recovery_lock = _make_lock(tmp_path)
        recovery_lock.acquire()
        recovery_lock.release()


class TestAUTO002IR01LockCannotEscapeRepositoryViaSymlink:
    """AUTO002-IR-01: `canonical_lock_path` resolves only the repository *root*, then appends
    `.agentos/workflow.lock` lexically. An independent review reproduced a symlinked
    `<repo>/.agentos` being followed at open time, creating and truncating `workflow.lock`
    physically outside the repository. Every lock-related directory and file must stay physically
    within the canonical repository root.
    """

    def test_symlinked_agentos_directory_is_rejected_and_creates_no_external_file(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        external = tmp_path / "external"
        external.mkdir()
        (repository_path / ".agentos").symlink_to(external, target_is_directory=True)

        lock = _make_lock(repository_path)
        with pytest.raises(LockPathConfinementError):
            lock.acquire()

        assert not lock.is_held
        # The literal escape the review reproduced: no lock file may appear outside the repository.
        assert list(external.iterdir()) == []

    def test_symlinked_agentos_directory_leaves_existing_external_file_byte_identical(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        external = tmp_path / "external"
        external.mkdir()
        sentinel = external / DEFAULT_LOCK_FILENAME
        sentinel.write_bytes(b"SENTINEL-EXTERNAL-CONTENT")
        sentinel_mtime = sentinel.stat().st_mtime_ns
        (repository_path / ".agentos").symlink_to(external, target_is_directory=True)

        lock = _make_lock(repository_path)
        with pytest.raises(LockPathConfinementError):
            lock.acquire()

        # Rejection must happen before any create/truncate/write: the pre-fix code opened this
        # file with O_RDWR|O_CREAT and then ftruncate'd it to zero.
        assert sentinel.read_bytes() == b"SENTINEL-EXTERNAL-CONTENT"
        assert sentinel.stat().st_mtime_ns == sentinel_mtime
        assert not lock.is_held

    def test_symlinked_lock_file_inside_real_control_directory_is_rejected(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        control = repository_path / ".agentos"
        control.mkdir()
        external_target = tmp_path / "external-lock-target"
        external_target.write_bytes(b"SENTINEL-EXTERNAL-LOCK")
        (control / DEFAULT_LOCK_FILENAME).symlink_to(external_target)

        lock = _make_lock(repository_path)
        with pytest.raises(LockPathConfinementError):
            lock.acquire()

        assert external_target.read_bytes() == b"SENTINEL-EXTERNAL-LOCK"
        assert not lock.is_held

    def test_read_metadata_does_not_disclose_bytes_through_symlinked_control_directory(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        external = tmp_path / "external"
        external.mkdir()
        (external / DEFAULT_LOCK_FILENAME).write_text(
            '{"workflow_id":"external","process_id":1,"hostname":"h",'
            '"repository_identity":"i","repository_path":"p","acquired_at":"2026-07-27T00:00:00+00:00"}',
            encoding="utf-8",
        )
        (repository_path / ".agentos").symlink_to(external, target_is_directory=True)

        # Diagnostic-only contract: unreadable/confined is reported as "no metadata", never by
        # reading the external file's bytes through the symlink.
        assert _make_lock(repository_path).read_metadata() is None

    def test_symlinked_control_directory_never_created_by_a_rejected_acquire(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        external = tmp_path / "external"
        external.mkdir()
        (repository_path / ".agentos").symlink_to(external, target_is_directory=True)

        with pytest.raises(LockPathConfinementError):
            _make_lock(repository_path).acquire()

        # The symlink itself must be left exactly as found — not replaced by a real directory.
        assert (repository_path / ".agentos").is_symlink()
        assert os.readlink(repository_path / ".agentos") == str(external)

    def test_normal_repository_locking_still_works_after_confinement_hardening(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        lock = _make_lock(repository_path)
        lock.acquire()
        try:
            assert lock.is_held
            assert lock.lock_path.is_file()
            assert not lock.lock_path.parent.is_symlink()
            assert lock.lock_path.resolve().is_relative_to(repository_path.resolve())
            metadata = lock.read_metadata()
            assert metadata is not None
            assert metadata.workflow_id == "wf-1"
        finally:
            lock.release()
        assert not lock.is_held
        # Release must leave the lock file reusable, not unlinked (module docstring).
        assert lock.lock_path.is_file()
        reacquired = _make_lock(repository_path)
        reacquired.acquire()
        reacquired.release()

    def test_equivalent_repository_spellings_still_contend_for_one_lock(
        self, tmp_path: Path
    ) -> None:
        real_repository = tmp_path / "real-repo"
        real_repository.mkdir()
        alias = tmp_path / "alias-repo"
        alias.symlink_to(real_repository, target_is_directory=True)

        # A symlinked *repository root* is still legitimately collapsed by resolve(); only
        # symlinks at or below `.agentos` are refused. Both spellings must be one lock identity.
        direct = _make_lock(real_repository)
        aliased = _make_lock(alias)
        assert direct.lock_path == aliased.lock_path

        direct.acquire()
        try:
            with pytest.raises(LockContentionError):
                aliased.acquire()
        finally:
            direct.release()
        aliased.acquire()
        aliased.release()

    def test_cross_process_contention_still_effective_after_confinement_hardening(
        self, tmp_path: Path
    ) -> None:
        repository_path = tmp_path / "repo"
        repository_path.mkdir()
        ctx = mp.get_context("fork")
        held_event = ctx.Event()
        release_event = ctx.Event()
        child = ctx.Process(
            target=_child_acquire_hold_and_wait,
            args=(repository_path, held_event, release_event),
        )
        child.start()
        try:
            assert held_event.wait(timeout=10)
            with pytest.raises(LockContentionError):
                _make_lock(repository_path).acquire()
        finally:
            release_event.set()
            child.join(timeout=10)
        assert child.exitcode == 0
        # Once the holding process is gone the lock must be genuinely free again.
        recovered = _make_lock(repository_path)
        recovered.acquire()
        recovered.release()
