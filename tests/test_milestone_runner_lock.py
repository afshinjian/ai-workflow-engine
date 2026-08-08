"""AUTO-016 section 12: the `fcntl.flock` run lock and what it refuses.

Every test here contends against a **real second process**. Mutual exclusion is a property of the
kernel's advisory locks, and a test double for `fcntl.flock` would only assert that the double
behaves as written -- the one thing already known. Child processes are spawned with the running
interpreter, acquire the real lock on a real file under `tmp_path`, and signal readiness by
creating a file, so the parent's refusal is contended against a hold that genuinely exists.

The three properties section 12 names, and how each is proven:

* **The hold is the sole authority.** `TestLockReleasedOnProcessExit` kills nothing and cleans
  nothing up: a child acquires and exits without calling `release()`, and the parent's subsequent
  acquisition succeeds because the kernel dropped the hold at process exit. No PID is consulted,
  which is also asserted at the source level -- section 12 forbids the prototype's
  `os.kill(pid, 0)` probe outright as racy under PID reuse.
* **The lock file is never unlinked.** `TestLockFileNotDeletedOnRelease` asserts the file is still
  there after a clean release, and that the inode is unchanged across a release/reacquire cycle.
  Unlinking would race a second acquirer onto a fresh inode at the same path.
* **Contention is a typed refusal that names the holder.** Never a wait, never a steal.
"""

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_workflow_engine.milestone_runner.lock import (
    RUN_LOCK_FILE_NAME,
    LockContention,
    LockHolder,
    LockPathRefused,
    LockStateError,
    RunLock,
)
from ai_workflow_engine.milestone_runner.models import StopReason

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCK_SOURCE = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner" / "lock.py"

REPOSITORY_IDENTITY = "demo-repo--2059e82cffa9"

#: Spawned as a real child process. It acquires the lock, announces the fact by creating
#: `ready_path`, holds for `hold_seconds` and then exits **without releasing** -- which is exactly
#: the crash-shaped case section 12 says must leave the lock reacquirable.
CHILD_SOURCE = """
import sys
import time
from pathlib import Path

from ai_workflow_engine.milestone_runner.lock import RunLock

artifact_root, run_id, identity, ready_path, hold_seconds = sys.argv[1:6]
lock = RunLock(
    run_id=run_id, repository_identity=identity, artifact_root=Path(artifact_root)
)
lock.acquire()
Path(ready_path).write_text("held", encoding="utf-8")
time.sleep(float(hold_seconds))
"""


def spawn_holder(
    artifact_root: Path, run_id: str, ready: Path, hold_seconds: float
) -> subprocess.Popen[bytes]:
    """Start a child that really holds the lock, and wait until it really holds it."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            CHILD_SOURCE,
            str(artifact_root),
            run_id,
            REPOSITORY_IDENTITY,
            str(ready),
            str(hold_seconds),
        ],
        env={**os.environ},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if ready.exists():
            return process
        if process.poll() is not None:
            _, stderr = process.communicate()
            pytest.fail(f"The holding child exited before acquiring: {stderr.decode()}")
        time.sleep(0.02)
    process.kill()
    process.wait(timeout=10)
    pytest.fail("The holding child never acquired the lock")


@pytest.fixture
def artifact_root(tmp_path: Path) -> Path:
    """A repository-scoped artifact root, laid out exactly as section 11 fixes it."""
    root = tmp_path / "home" / ".ai-workflow-engine" / "milestone-runs" / REPOSITORY_IDENTITY
    root.parent.mkdir(parents=True)
    return root


def lock_for(artifact_root: Path, run_id: str = "auto016-run-0001") -> RunLock:
    return RunLock(
        run_id=run_id, repository_identity=REPOSITORY_IDENTITY, artifact_root=artifact_root
    )


class TestLockPathIsDerivedNeverSupplied:
    """The lock path is a pure function of the artifact root, which is the guarantee itself.

    `flock` only serializes callers contending on the *same* file, so a constructor that accepted
    an arbitrary path would let two locks for one canonical repository be held simultaneously --
    the exact defect the reference implementation's own docstring records having had to fix.
    """

    def test_the_lock_lives_at_run_lock_under_the_repository_scoped_root(
        self, artifact_root: Path
    ) -> None:
        assert lock_for(artifact_root).lock_path == artifact_root / RUN_LOCK_FILE_NAME

    def test_two_instances_for_one_repository_derive_one_path(self, artifact_root: Path) -> None:
        first = lock_for(artifact_root, "auto016-run-0001")
        second = lock_for(artifact_root, "auto016-run-0002")
        assert first.lock_path == second.lock_path

    def test_the_constructor_exposes_no_path_parameter(self) -> None:
        import inspect

        parameters = set(inspect.signature(RunLock.__init__).parameters)
        assert parameters == {"self", "run_id", "repository_identity", "artifact_root"}

    def test_a_malformed_run_id_is_refused_before_any_filesystem_touch(
        self, artifact_root: Path
    ) -> None:
        with pytest.raises(Exception, match="not a usable run id"):
            RunLock(
                run_id="../escape",
                repository_identity=REPOSITORY_IDENTITY,
                artifact_root=artifact_root,
            )
        assert not artifact_root.exists()


class TestLockContentionRefused:
    """Contention is a typed refusal naming the holding run -- never a wait, never a steal."""

    def test_a_second_acquisition_in_one_process_is_a_state_error(
        self, artifact_root: Path
    ) -> None:
        lock = lock_for(artifact_root)
        lock.acquire()
        try:
            with pytest.raises(LockStateError):
                lock.acquire()
        finally:
            lock.release()

    def test_a_contending_process_is_refused_with_the_typed_stop_reason(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        holder = spawn_holder(artifact_root, "auto016-run-holder", tmp_path / "ready", 30.0)
        try:
            with pytest.raises(LockContention) as refusal:
                lock_for(artifact_root, "auto016-run-second").acquire()
            assert LockContention.stop_reason is StopReason.LOCK_CONTENTION
            assert refusal.value.holder is not None
            assert refusal.value.holder.run_id == "auto016-run-holder"
            assert "auto016-run-holder" in str(refusal.value)
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_the_refusal_is_immediate_rather_than_a_wait(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        """`LOCK_NB` is the whole concurrency model: nothing queues behind a held lock."""
        holder = spawn_holder(artifact_root, "auto016-run-holder", tmp_path / "ready", 30.0)
        try:
            started = time.monotonic()
            with pytest.raises(LockContention):
                lock_for(artifact_root, "auto016-run-second").acquire()
            assert time.monotonic() - started < 5.0
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_a_refused_acquirer_holds_nothing_afterwards(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        holder = spawn_holder(artifact_root, "auto016-run-holder", tmp_path / "ready", 30.0)
        second = lock_for(artifact_root, "auto016-run-second")
        try:
            with pytest.raises(LockContention):
                second.acquire()
            assert second.is_held is False
        finally:
            holder.kill()
            holder.wait(timeout=10)


class TestConcurrentRunnersMutuallyExcluded:
    """Section 22 invariant 10: two runners against one canonical repository never both hold it."""

    def test_only_one_of_two_real_processes_holds_the_lock(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        holder = spawn_holder(artifact_root, "auto016-run-first", tmp_path / "ready", 30.0)
        try:
            for run_id in ("auto016-run-second", "auto016-run-third"):
                with pytest.raises(LockContention):
                    lock_for(artifact_root, run_id).acquire()
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_exclusion_is_by_canonical_repository_not_by_run(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        """Section 12's unit of exclusion is the repository, so a fresh run id buys nothing.

        This is why the flock target is the repository-scoped root rather than section 11's
        per-run directory: a per-run path would give two run ids two files, and both would
        succeed.
        """
        holder = spawn_holder(artifact_root, "auto016-run-first", tmp_path / "ready", 30.0)
        try:
            with pytest.raises(LockContention) as refusal:
                lock_for(artifact_root, "auto016-run-completely-different").acquire()
            assert refusal.value.holder is not None
            assert refusal.value.holder.repository_identity == REPOSITORY_IDENTITY
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_a_different_repository_contends_with_nobody(self, tmp_path: Path) -> None:
        runs = tmp_path / "home" / ".ai-workflow-engine" / "milestone-runs"
        runs.mkdir(parents=True)
        first = RunLock(
            run_id="auto016-run-0001",
            repository_identity="repo-one--000000000001",
            artifact_root=runs / "repo-one--000000000001",
        )
        second = RunLock(
            run_id="auto016-run-0001",
            repository_identity="repo-two--000000000002",
            artifact_root=runs / "repo-two--000000000002",
        )
        first.acquire()
        second.acquire()
        try:
            assert first.is_held and second.is_held
            assert first.lock_path != second.lock_path
        finally:
            first.release()
            second.release()


class TestLockReleasedOnProcessExit:
    """A stale hold is reacquirable because `flock` is released by the kernel, not by a probe."""

    def test_a_holder_that_exits_without_releasing_leaves_the_lock_acquirable(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        holder = spawn_holder(artifact_root, "auto016-run-crashed", tmp_path / "ready", 0.0)
        assert holder.wait(timeout=30) == 0

        reacquired = lock_for(artifact_root, "auto016-run-next")
        reacquired.acquire()
        try:
            assert reacquired.is_held
        finally:
            reacquired.release()

    def test_the_stale_metadata_of_a_dead_holder_never_blocks_reacquisition(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        """Metadata is diagnostic. A record naming a dead run is not a hold."""
        holder = spawn_holder(artifact_root, "auto016-run-crashed", tmp_path / "ready", 0.0)
        assert holder.wait(timeout=30) == 0

        stale = lock_for(artifact_root, "auto016-run-next").read_holder()
        assert stale is not None
        assert stale.run_id == "auto016-run-crashed"

        successor = lock_for(artifact_root, "auto016-run-next")
        successor.acquire()
        try:
            assert successor.read_holder() is not None
            holder_record = successor.read_holder()
            assert holder_record is not None
            assert holder_record.run_id == "auto016-run-next"
        finally:
            successor.release()

    def test_no_pid_liveness_probe_exists_in_the_module(self) -> None:
        """Section 12: `os.kill(pid, 0)` is racy under PID reuse and is deliberately absent.

        Asserted at the source level rather than behaviourally, because the claim is that no such
        probe exists at all -- a behavioural test could only show that one particular path does
        not take it. Every `kill`-named attribute and bare name is rejected, not only a call, so
        binding the function to another name first would fail here too. The module docstring's
        own mention of `os.kill` is prose and carries no `Attribute` node, which is why this
        works on the AST and would not work on the raw text.
        """
        tree = ast.parse(LOCK_SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr != "kill", "lock.py must take no PID-liveness probe (section 12)"
            if isinstance(node, ast.Name):
                assert node.id not in {"kill", "getpgid"}


class TestLockFileNotDeletedOnRelease:
    """Deleting the lock file races a second acquirer onto a different inode (section 12)."""

    def test_the_file_survives_a_clean_release(self, artifact_root: Path) -> None:
        lock = lock_for(artifact_root)
        lock.acquire()
        lock.release()
        assert lock.lock_path.is_file()

    def test_the_inode_is_unchanged_across_release_and_reacquisition(
        self, artifact_root: Path
    ) -> None:
        lock = lock_for(artifact_root)
        lock.acquire()
        first_inode = lock.lock_path.stat().st_ino
        lock.release()
        lock.acquire()
        try:
            assert lock.lock_path.stat().st_ino == first_inode
        finally:
            lock.release()

    def test_release_without_a_hold_is_a_no_op(self, artifact_root: Path) -> None:
        """`release()` is safe on every failure path, which is why nothing here guards it."""
        lock = lock_for(artifact_root)
        lock.release()
        assert lock.is_held is False

    def test_the_context_manager_releases_but_does_not_delete(self, artifact_root: Path) -> None:
        lock = lock_for(artifact_root)
        with lock as held:
            assert held is lock
            assert lock.is_held
        assert lock.is_held is False
        assert lock.lock_path.is_file()

    def test_the_context_manager_releases_on_an_exception(self, artifact_root: Path) -> None:
        lock = lock_for(artifact_root)
        with pytest.raises(RuntimeError), lock:
            raise RuntimeError("the run stopped at a safety gate")
        assert lock.is_held is False
        assert lock.lock_path.is_file()


class TestLockPathSymlinkRejected:
    """Invariant 8: a symlinked component is refused at the open, never followed."""

    def test_a_symlinked_repository_scoped_root_is_refused(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        artifact_root.symlink_to(elsewhere, target_is_directory=True)

        with pytest.raises(LockPathRefused, match="symbolic link"):
            lock_for(artifact_root).acquire()
        assert not (elsewhere / RUN_LOCK_FILE_NAME).exists()

    def test_a_symlinked_lock_file_is_refused_and_its_target_is_untouched(
        self, artifact_root: Path, tmp_path: Path
    ) -> None:
        artifact_root.mkdir(parents=True)
        target = tmp_path / "outside.txt"
        target.write_text("untouched\n", encoding="utf-8")
        (artifact_root / RUN_LOCK_FILE_NAME).symlink_to(target)

        with pytest.raises(LockPathRefused, match="symbolic link"):
            lock_for(artifact_root).acquire()
        assert target.read_text(encoding="utf-8") == "untouched\n"

    def test_a_hard_linked_lock_file_is_refused(self, artifact_root: Path, tmp_path: Path) -> None:
        """A second name for the inode means a second directory owns the lock's truncation."""
        artifact_root.mkdir(parents=True)
        (artifact_root / RUN_LOCK_FILE_NAME).write_text("{}", encoding="utf-8")
        os.link(artifact_root / RUN_LOCK_FILE_NAME, tmp_path / "alias.lock")

        with pytest.raises(LockPathRefused, match="hard links"):
            lock_for(artifact_root).acquire()

    def test_a_directory_at_the_lock_name_is_refused(self, artifact_root: Path) -> None:
        artifact_root.mkdir(parents=True)
        (artifact_root / RUN_LOCK_FILE_NAME).mkdir()
        with pytest.raises((LockPathRefused, OSError)):
            lock_for(artifact_root).acquire()


class TestLockMetadataIsDiagnosticOnly:
    """Metadata names a holder for a human. It never decides whether a lock is held."""

    def test_the_recorded_holder_names_the_run_and_this_process(self, artifact_root: Path) -> None:
        lock = lock_for(artifact_root)
        holder = lock.acquire()
        try:
            assert holder.run_id == "auto016-run-0001"
            assert holder.process_id == os.getpid()
            assert holder.repository_identity == REPOSITORY_IDENTITY
            assert holder.acquired_at.endswith("Z")
        finally:
            lock.release()

    def test_reading_a_holder_before_any_acquisition_yields_none(self, artifact_root: Path) -> None:
        assert lock_for(artifact_root).read_holder() is None

    def test_an_unparseable_metadata_document_yields_none_rather_than_raising(
        self, artifact_root: Path
    ) -> None:
        artifact_root.mkdir(parents=True)
        (artifact_root / RUN_LOCK_FILE_NAME).write_text("not json at all", encoding="utf-8")
        lock = lock_for(artifact_root)
        assert lock.read_holder() is None
        # And it is still acquirable: a corrupt diagnostic record is not a hold.
        lock.acquire()
        try:
            assert lock.is_held
        finally:
            lock.release()

    def test_the_holder_model_is_a_closed_schema(self) -> None:
        with pytest.raises(ValidationError):
            LockHolder.model_validate_json(
                '{"run_id":"r","process_id":1,"hostname":"h",'
                '"repository_identity":"i","acquired_at":"2026-08-06T00:00:00Z","extra":1}'
            )

    def test_a_naive_acquisition_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            LockHolder(
                run_id="r",
                process_id=1,
                hostname="h",
                repository_identity=REPOSITORY_IDENTITY,
                acquired_at="2026-08-06 00:00:00",
            )


class TestLockModuleBoundary:
    """Section 22 invariant 6: the disciplines are adopted, the package is never imported."""

    def test_no_agentos_workflow_import_exists_in_lock_py(self) -> None:
        tree = ast.parse(LOCK_SOURCE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        offenders = {
            name
            for name in imported
            if name == "agentos_workflow"
            or name.startswith("agentos_workflow.")
            or name == "agentos_dashboard"
            or name.startswith("agentos_dashboard.")
        }
        assert offenders == set()

    def test_the_module_writes_only_its_own_lock_metadata(self) -> None:
        """Section 17a's boundary lives in `state.py`; this is the one documented carve-out.

        The flock is held by a specific open file description, so its metadata has to be written
        to that same descriptor -- an atomic publication would replace the inode and drop the
        hold. The carve-out is bounded here: every write primitive in `lock.py` sits inside
        `_write_holder`, whose only content is a `LockHolder` the runner generated, so no provider
        or command byte can reach disk through this module.
        """
        tree = ast.parse(LOCK_SOURCE.read_text(encoding="utf-8"))
        writers = {"_write_all", "_write_holder"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name in writers:
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                    assert inner.func.attr not in {
                        "write",
                        "write_text",
                        "write_bytes",
                        "writelines",
                    }, f"{node.name} must not write to the filesystem"
