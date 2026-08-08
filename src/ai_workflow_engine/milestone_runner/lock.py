"""Single-holder run lock for the AUTO-016 milestone runner (contract section 12).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 12 (process
locking and concurrency), section 4 entry condition 9, section 6 defect P-6 (a state write taken
while holding no lock) and section 22 invariant 10 (single-holder mutual exclusion).

Adopt the discipline, import nothing
------------------------------------
`agentos_workflow/orchestrator/lock.py` already solves this problem well, and section 12 is
explicit that AUTO-016 adopts its **documented disciplines** without importing it --
`ARCHITECTURE.md` section 4 forbids the edge and its `for_config` constructor requires a
target-repository `WorkflowConfig` that does not exist here. Nothing in this module is imported
from that package, and section 22 invariant 6 is asserted by test. The four disciplines carried
over verbatim:

* **An OS-level advisory `fcntl.flock` hold is the sole authority.** Whether a lock is held is
  decided by the kernel, never by a file's existence and never by its recorded metadata.
* **Metadata is diagnostic, never authoritative.** :class:`LockHolder` exists so a refusal can
  *name* the holding run. It is read without any lock and may describe a hold that ended
  microseconds ago; nothing branches on it except the wording of an error.
* **The lock file is never unlinked on release.** Unlinking races a second acquirer onto a fresh
  inode at the same path while the first file description is still locked, which defeats mutual
  exclusion outright. A stale file with old metadata is always safely reusable.
* **Every component below the repository-scoped root is opened `O_NOFOLLOW` relative to a
  directory descriptor.** The kernel refuses a symlinked component at the open itself, so no
  check-then-open window exists for a racing attacker to widen.

No PID-liveness heuristic
-------------------------
Section 12 is explicit: the prototype's `os.kill(pid, 0)` probe is **not** carried over. It is
racy under PID reuse -- the operating system is free to hand a dead runner's PID to an unrelated
process, at which point the probe reports a hold that does not exist -- and it is unnecessary,
because `flock` is released by the kernel when the holding process exits for any reason. A stale
hold is therefore reacquirable without anyone asking whether a recorded PID is alive. There is no
`os.kill` call in this module, and a test asserts its absence at the source level.

One lock per canonical repository, and a note on where it lives
---------------------------------------------------------------
Section 12 fixes the unit of exclusion as the **canonical repository**: "exactly one runner
process per canonical repository", and contention is a typed refusal (`LOCK_CONTENTION`) naming
the holding run rather than a wait-and-steal. The flock target is therefore
`~/.ai-workflow-engine/milestone-runs/<repository-id>/run.lock` -- the repository-scoped artifact
root itself, which every run of that repository shares.

Section 11's directory sketch draws `run.lock` one level lower, inside `<run-id>/`. A per-run
path cannot deliver what section 12 requires: two runners with two run ids would contend for two
different files and both would succeed, which is precisely the failure
`agentos_workflow/orchestrator/lock.py`'s own docstring records having had to fix. Where the two
sections disagree the narrower, more restrictive reading is implemented -- repository-scoped
exclusion -- and the file keeps section 11's `run.lock` name.
"""

import errno
import fcntl
import os
import re
import socket
import stat
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import ClassVar, Final

from pydantic import Field, ValidationError, field_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.models import MilestoneRunnerModel, StopReason

#: Section 11's name for the flock target, kept verbatim.
RUN_LOCK_FILE_NAME: Final = "run.lock"

#: The lock file's mode. Diagnostic metadata about a run is nobody else's business.
LOCK_FILE_MODE: Final = 0o600

#: The mode of any directory component this module creates.
LOCK_DIRECTORY_MODE: Final = 0o700

#: The largest metadata document this module will read back. Metadata is a handful of short
#: scalars; a larger file is corrupt or hostile and is treated as unreadable either way.
MAX_LOCK_METADATA_BYTES: Final = 4_096

# `O_NOFOLLOW` on a component that *is* a symlink fails with `ELOOP` on Linux and `EMLINK` on the
# BSDs; combined with `O_DIRECTORY` Linux reports `ENOTDIR` instead, because the link itself is
# not a directory -- the same errno a plain regular file yields. The three are therefore
# candidates for "that component was a symlink" rather than proof of it, which is why
# :func:`_refused_symlink` confirms with an `lstat` before choosing the wording.
_SYMLINK_REFUSED_ERRNOS: Final[frozenset[int]] = frozenset(
    {errno.ELOOP, errno.EMLINK, errno.ENOTDIR}
)

_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


class LockError(WorkflowEngineError):
    """Base run-lock failure.

    `stop_reason` is `None` here and set only on :class:`LockContention`, the one condition
    section 12 gives a code to. No code is invented for the others.
    """

    stop_reason: ClassVar[StopReason | None] = None


class LockStateError(LockError):
    """A lock operation was attempted from an impossible local state (a double acquire)."""


class LockPathRefused(LockError):
    """The lock path could not be opened without following a symlink or a shared inode.

    Raised **before** any create, truncate or write, so whatever the component pointed at is
    left byte-for-byte untouched.
    """


class LockContention(LockError):
    """Another runner holds the lock for this canonical repository (section 12).

    A typed refusal, never a wait and never a steal. `holder` carries the diagnostic metadata the
    holding process recorded, so the refusal can name the run an operator has to go and look at;
    it may be `None` when the file carries nothing readable, and a non-`None` value is never
    evidence about liveness -- the failed `flock` already established that.
    """

    stop_reason: ClassVar[StopReason | None] = StopReason.LOCK_CONTENTION

    def __init__(self, message: str, *, holder: "LockHolder | None" = None) -> None:
        super().__init__(message)
        self.holder = holder


class LockHolder(MilestoneRunnerModel):
    """Diagnostic metadata about whoever last acquired the lock -- never authoritative.

    Every field is generated by the runner itself: a run id, this process's own PID, the host
    name, the canonical repository identity and the moment of acquisition. None of it is derived
    from provider output or command output, which is why writing it does not pass through
    `state.write_redacted_artifact` (section 17a governs transcript, verification-output and state
    bytes) and cannot: the metadata must be written to the very descriptor that holds the flock,
    and an atomic publication would replace that inode and drop the hold with it.

    `process_id` is recorded for a human reading a stale file. Nothing in this module consults it,
    and section 12 forbids anything else from probing it for liveness.
    """

    run_id: str
    process_id: int = Field(ge=1)
    hostname: str = Field(min_length=1, max_length=255)
    repository_identity: str
    acquired_at: str

    @field_validator("run_id")
    @classmethod
    def _validate_run_id(cls, value: str) -> str:
        if _RUN_ID_RE.fullmatch(value) is None:
            raise ValueError(f"run_id must match {_RUN_ID_RE.pattern!r}")
        return value

    @field_validator("repository_identity")
    @classmethod
    def _validate_repository_identity(cls, value: str) -> str:
        if not value or len(value) > 128 or "/" in value:
            raise ValueError("repository_identity must be a bounded, separator-free identity")
        return value

    @field_validator("acquired_at")
    @classmethod
    def _validate_acquired_at(cls, value: str) -> str:
        if _UTC_TIMESTAMP_RE.fullmatch(value) is None:
            raise ValueError("acquired_at must be an ISO-8601 UTC timestamp YYYY-MM-DDThh:mm:ssZ")
        return value


def _refused_symlink(parent_fd: int, name: str, exc: OSError) -> bool:
    """Whether `exc` from an `O_NOFOLLOW` open of `name` means "that component is a symlink".

    Consulted only to classify an already-failed open. The open itself, not this check, is what
    enforces confinement, so the inherent raciness of a follow-up `lstat` cannot widen the
    refusal: by the time this runs, nothing has been created, truncated or written either way.
    """
    if exc.errno not in _SYMLINK_REFUSED_ERRNOS:
        return False
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=parent_fd).st_mode)
    except OSError:
        return False


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write every byte of `payload`; POSIX permits `os.write` to make a short write.

    Silently accepting a short write would persist truncated metadata. A call that makes zero
    progress raises rather than spinning forever.
    """
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError(f"os.write made no progress with {len(view)} bytes remaining")
        view = view[written:]


def _open_directory_component(parent_fd: int, name: str, *, create: bool) -> int:
    """Open the directory `name` inside `parent_fd`, refusing to follow it if it is a symlink.

    `O_NOFOLLOW` constrains exactly the final component, and `name` is exactly one literal
    segment. Creation is attempted first and its `FileExistsError` ignored, so a real directory
    already there is reused while a *symlink* occupying the name survives the `mkdir` only to be
    refused by the open below -- the open, not a prior check, is the enforcement.
    """
    if create:
        try:
            os.mkdir(name, LOCK_DIRECTORY_MODE, dir_fd=parent_fd)
        except FileExistsError:
            pass
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        if _refused_symlink(parent_fd, name, exc):
            raise LockPathRefused(
                f"Refusing the lock directory {name!r}: it is a symbolic link, so the lock would "
                "be placed outside the repository-scoped artifact root"
            ) from exc
        # Anything else -- most usefully `FileNotFoundError` when a read-only caller asks for a
        # lock that was never created -- is the caller's to interpret, not this module's to
        # relabel as a confinement failure.
        raise


def _open_lock_file_component(parent_fd: int, name: str, *, create: bool) -> int:
    """Open the lock file `name` inside `parent_fd`, refusing to follow it if it is a symlink.

    `O_CREAT | O_NOFOLLOW` is one atomic step: an existing symlink at `name` fails the open
    outright instead of being created through, so a descriptor returned here necessarily refers
    to a real file physically inside `parent_fd`'s directory.
    """
    flags = os.O_RDWR | os.O_NOFOLLOW
    if create:
        flags |= os.O_CREAT
    try:
        descriptor = os.open(name, flags, LOCK_FILE_MODE, dir_fd=parent_fd)
    except OSError as exc:
        if _refused_symlink(parent_fd, name, exc):
            raise LockPathRefused(
                f"Refusing the lock file {name!r}: it is a symbolic link, so the flock would be "
                "taken on a file outside the repository-scoped artifact root"
            ) from exc
        raise
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
        os.close(descriptor)
        detail = (
            "is not a regular file"
            if not stat.S_ISREG(status.st_mode)
            else f"has {status.st_nlink} hard links"
        )
        raise LockPathRefused(
            f"Refusing the lock file {name!r}: it {detail}; the lock inode must have exactly one "
            "name owned by the artifact root before it is truncated or written"
        )
    return descriptor


class RunLock:
    """Section 12's mutual exclusion: one runner process per canonical repository.

    The lock path is derived, never supplied. A caller passes the repository-scoped artifact root
    -- `state.artifact_root_for(<repository-id>)` -- and the file name is fixed, so two
    `RunLock` instances naming the same canonical repository always contend on the same inode.
    An earlier revision of the reference implementation accepted an arbitrary lock path and
    thereby let two locks for one repository be held at once; `flock` only serializes callers
    contending on the *same* file, so the derivation is the guarantee.

    The instance is a context manager. `release()` unlocks and closes the descriptor and
    deliberately leaves the file in place.
    """

    def __init__(
        self,
        *,
        run_id: str,
        repository_identity: str,
        artifact_root: Path,
    ) -> None:
        if _RUN_ID_RE.fullmatch(run_id) is None:
            raise LockError(f"{run_id!r} is not a usable run id for a lock holder record")
        if not repository_identity or "/" in repository_identity:
            raise LockError(
                f"{repository_identity!r} is not a usable canonical repository identity"
            )
        self._run_id = run_id
        self._repository_identity = repository_identity
        self._artifact_root = artifact_root
        self._lock_path = artifact_root / RUN_LOCK_FILE_NAME
        self._descriptor: int | None = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def repository_identity(self) -> str:
        return self._repository_identity

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    @property
    def lock_path(self) -> Path:
        """Where the flock is taken. A pure function of the artifact root; never caller-supplied."""
        return self._lock_path

    @property
    def is_held(self) -> bool:
        """Whether *this instance* holds the lock. Never a claim about any other process."""
        return self._descriptor is not None

    def acquire(self) -> LockHolder:
        """Take the lock, or refuse with :class:`LockContention` naming the holding run.

        `LOCK_EX | LOCK_NB` is the whole concurrency model: a non-blocking exclusive hold, so
        contention is an immediate typed refusal rather than a queue. Nothing waits, nothing
        retries and nothing steals.
        """
        if self._descriptor is not None:
            raise LockStateError(f"This instance already holds {self._lock_path}")

        descriptor = self._open_confined(create=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            # The metadata read is diagnostic and deliberately taken while holding nothing: it
            # only decides how the refusal is worded.
            holder = self._read_holder(descriptor)
            os.close(descriptor)
            named = (
                f" It is held by run {holder.run_id} (recorded at {holder.acquired_at})."
                if holder is not None
                else " The lock file records no readable holder."
            )
            raise LockContention(
                f"Another runner holds the run lock for {self._repository_identity} at "
                f"{self._lock_path}.{named}",
                holder=holder,
            ) from exc
        except BaseException:
            os.close(descriptor)
            raise

        # The flock is now held by `descriptor`. Everything below is bookkeeping that can still
        # fail; if it does, the hold and the descriptor must both be released here or they leak.
        # A bare `int` has no destructor, `self._descriptor` was never set, so nothing else could
        # ever find it and the kernel would keep the repository wedged for this process's life.
        try:
            holder = LockHolder(
                run_id=self._run_id,
                process_id=os.getpid(),
                hostname=socket.gethostname()[:255] or "unknown",
                repository_identity=self._repository_identity,
                acquired_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            self._write_holder(descriptor, holder)
        except BaseException:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
            raise

        self._descriptor = descriptor
        return holder

    def release(self) -> None:
        """Release the hold and close the descriptor. The lock **file** is never unlinked.

        Deleting it would let a third process create a fresh inode at the same path and believe
        it holds a lock while a second process's original file description is still locked --
        the exact race section 12 names. Releasing a lock this instance does not hold is a no-op,
        so `release()` is safe on every failure path.
        """
        if self._descriptor is None:
            return
        descriptor = self._descriptor
        self._descriptor = None
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def read_holder(self) -> LockHolder | None:
        """Read the recorded holder without attempting acquisition -- diagnostic only.

        `None` means the file is absent, empty or unparseable. A non-`None` result is never proof
        that a lock is currently held: the record may have been left by a process that exited
        without releasing, and the kernel released the hold on its behalf.
        """
        try:
            descriptor = self._open_confined(create=False)
        except FileNotFoundError:
            return None
        try:
            return self._read_holder(descriptor)
        finally:
            os.close(descriptor)

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    # -- the confined path walk ----------------------------------------------------------

    def _open_confined(self, *, create: bool) -> int:
        """Open the lock file without letting a symlink move it out of the artifact root.

        The walk is anchored at the *realized* parent of the artifact root -- the shared
        `~/.ai-workflow-engine/milestone-runs/` directory -- and descends the two components that
        decide **which repository** this lock serializes, `<repository-id>/run.lock`, one at a
        time with `O_NOFOLLOW`. Anchoring rather than walking from `/` is deliberate: a home
        directory is legitimately a symlink on some systems, whereas a symlinked `<repository-id>`
        or `run.lock` is what would silently alias two repositories onto one lock, or one
        repository onto two.
        """
        anchor = Path(os.path.realpath(self._artifact_root.parent))
        if create:
            os.makedirs(anchor, mode=LOCK_DIRECTORY_MODE, exist_ok=True)
        anchor_fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            root_fd = _open_directory_component(anchor_fd, self._artifact_root.name, create=create)
            try:
                return _open_lock_file_component(root_fd, RUN_LOCK_FILE_NAME, create=create)
            finally:
                os.close(root_fd)
        finally:
            os.close(anchor_fd)

    # -- metadata: written to the locked descriptor, read positionally --------------------

    def _write_holder(self, descriptor: int, holder: LockHolder) -> None:
        """Replace the metadata document on the descriptor that holds the flock.

        The write goes to *this* descriptor rather than through an atomic publication precisely
        because the hold belongs to this open file description: replacing the inode would drop
        the lock. Truncate-then-write leaves a torn document visible to a concurrent reader, and
        that is acceptable here and nowhere else -- a torn metadata read yields `None`, which the
        refusal wording already handles, and no decision is ever taken from it.
        """
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        _write_all(descriptor, holder.model_dump_json().encode("utf-8"))
        os.fsync(descriptor)

    def _read_holder(self, descriptor: int) -> LockHolder | None:
        """Read and parse the metadata document positionally, leaving the offset untouched."""
        try:
            payload = os.pread(descriptor, MAX_LOCK_METADATA_BYTES, 0)
        except OSError:
            return None
        if not payload:
            return None
        try:
            return LockHolder.model_validate_json(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValidationError, ValueError):
            return None
