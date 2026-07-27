"""Per-target-repository workflow lock (ARCHITECTURE.md §5; OPEN_QUESTIONS.md OD-3).

Mutual exclusion is provided exclusively by an OS-level advisory lock (`fcntl.flock`,
`LOCK_EX | LOCK_NB`) on the lock file's open file description. The JSON metadata written
alongside it is diagnostic only, never authoritative: a live `flock` hold is the sole proof
that a lock is active. A lock file's mere existence, or the process identity recorded in its
metadata, is never sufficient to conclude a lock is held or free — the metadata may be stale
(e.g. left behind by a process that crashed without releasing), and PIDs are reused by the
operating system, so a PID appearing in metadata is never itself checked for liveness.

`release()` deliberately never unlinks the lock file: unlinking while another process might be
racing to open the same path can let a third process create a fresh inode at that path and
believe it holds the lock while the second process's original file description is still locked,
defeating mutual exclusion. Leaving the file in place and relying purely on `flock` avoids that
race; a stale file with old metadata is always safely reusable by the next `acquire()`.

`canonical_lock_path` — not `state_directory` — is the sole authority for *where* a target
repository's lock lives: it is a pure function of the target repository's own canonical
(symlink-resolved, absolute) filesystem path, reusing the same per-repository `.agentos/`
directory `CONFIGURATION_MODEL.md` §2 already establishes as convention for that repository's
own `workflow.yaml`. `state_directory` is a separately-configurable knob (per-target, but not
required to be derived from `repository_path`); deriving the lock path from it instead would let
two configurations that name the *same* physical target repository but different
`state_directory` values obtain two independent, non-contending locks — defeating "exactly one
active workflow per target repository" (`ARCHITECTURE.md` §5). Deriving from the canonical
repository path instead means any two configurations (or any two directly-constructed
`RepositoryLock` instances) naming the same physical repository — including through a symlink
alias — always resolve to the identical lock file, so they always genuinely contend.

Resolving the *repository root* is not by itself enough to keep the lock inside that repository
(AUTO002-IR-01): `canonical_lock_path` resolves `repository_path`, but then appends
`.agentos/workflow.lock` lexically, so a symlinked `<repo>/.agentos` — or a symlinked
`workflow.lock` inside a real `.agentos` — was still followed at open time, creating and
truncating a file physically outside the repository. Every lock open therefore walks the path one
component at a time with `O_NOFOLLOW` relative to a directory file descriptor (`dir_fd`), starting
from the already-canonical root: a symlinked component is refused by the kernel *at the open
itself* rather than by a separate check that a racing attacker could invalidate between check and
open, and no external file is created, truncated, or read. This module is POSIX-only regardless
(`fcntl.flock` above), and `dir_fd`/`O_NOFOLLOW` are POSIX facilities, so this adds no portability
constraint the module did not already have.
"""

import errno
import fcntl
import os
import socket
import stat
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from pydantic import BaseModel, ConfigDict

from agentos_workflow.config.schema import WorkflowConfig

DEFAULT_LOCK_FILENAME = "workflow.lock"
_AGENTOS_DIRECTORY_NAME = ".agentos"

# `O_NOFOLLOW` on a path component that *is* a symlink fails with `ELOOP` on Linux and `EMLINK` on
# the BSDs/macOS. Combined with `O_DIRECTORY`, Linux reports the un-followed symlink as `ENOTDIR`
# instead (the link itself is not a directory) — the same errno a plain regular file would give,
# which is why `_refused_symlink` below distinguishes the two by inspecting the name rather than
# trusting the errno alone.
_SYMLINK_REFUSED_ERRNOS = frozenset({errno.ELOOP, errno.EMLINK, errno.ENOTDIR})


def _refused_symlink(parent_fd: int, name: str, exc: OSError) -> bool:
    """Whether `exc` from an `O_NOFOLLOW` open of `name` means "that component is a symlink".

    Consulted only to *classify an already-failed open* — the open itself, not this check, is what
    enforces confinement, so the inherent raciness of a follow-up `lstat` cannot widen the
    refusal: by the time this runs nothing has been created, truncated, or written either way.
    """
    if exc.errno not in _SYMLINK_REFUSED_ERRNOS:
        return False
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=parent_fd).st_mode)
    except OSError:
        return False


def _write_all(fd: int, payload: bytes) -> None:
    """`os.write` is permitted by POSIX to write fewer bytes than requested (a "short write").
    Silently ignoring the return value here would risk persisting truncated lock metadata; every
    byte is written in a loop, and a call that makes zero progress raises rather than spinning
    forever. (Mirrors `state_store.py`'s identical helper — duplicated rather than imported
    across modules to keep `lock.py` free of a dependency on `state_store.py`.)
    """
    view = memoryview(payload)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError(
                f"os.write made no progress (0 of {len(view) - written} remaining bytes written)"
            )
        written += count


def canonical_lock_path(repository_path: Path) -> Path:
    """The single, deterministic lock-file location for a target repository.

    A pure function of `repository_path` alone, resolved (`Path.resolve()`) to collapse any
    symlink alias to the same underlying real path before deriving the location — two callers
    naming the same physical repository through different symlinks, different `state_directory`
    configurations, or any other caller-supplied variation always land on this same path.
    """
    return repository_path.resolve() / _AGENTOS_DIRECTORY_NAME / DEFAULT_LOCK_FILENAME


class LockError(Exception):
    """Base error for repository-lock failures."""


class LockContentionError(LockError):
    """Raised when the lock is already held by another live process."""


class LockStateError(LockError):
    """Raised when a lock operation is attempted from an invalid local state."""


class LockPathConfinementError(LockError):
    """Raised when the lock path cannot be opened without leaving the canonical repository.

    Specifically: a component of `<canonical repository>/.agentos/workflow.lock` is a symlink, so
    following it would place the lock — and the metadata write that truncates it — at a physical
    location the repository does not own. Raised *before* any create, truncate, or write, so the
    external target is left byte-for-byte untouched.
    """


def _open_directory_component(parent_fd: int, name: str, *, create: bool) -> int:
    """Open the directory `name` inside `parent_fd`, refusing to follow it if it is a symlink.

    `O_NOFOLLOW` constrains only the final path component, which is exactly one component here:
    `name` is a single literal segment resolved relative to `parent_fd`, never a multi-segment
    path. Creation is attempted first and its `FileExistsError` ignored, so an already-present
    real directory is reused, while a *symlink* occupying the name survives the `mkdir` only to be
    refused by the `O_NOFOLLOW` open below — the open, not a prior check, is what enforces this.
    """
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        if _refused_symlink(parent_fd, name, exc):
            raise LockPathConfinementError(
                f"Refusing to use lock directory {name!r}: it is a symlink, so the lock would be "
                "placed outside the canonical repository."
            ) from exc
        raise


def _open_lock_file_component(parent_fd: int, name: str, *, create: bool) -> int:
    """Open the lock file `name` inside `parent_fd`, refusing to follow it if it is a symlink.

    `O_CREAT | O_NOFOLLOW` is a single atomic step: an existing symlink at `name` fails the open
    outright instead of being created through, and a file created here is necessarily a real file
    physically inside `parent_fd`'s directory.
    """
    flags = os.O_RDWR | os.O_NOFOLLOW
    if create:
        flags |= os.O_CREAT
    try:
        fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        if _refused_symlink(parent_fd, name, exc):
            raise LockPathConfinementError(
                f"Refusing to use lock file {name!r}: it is a symlink, so the lock would be "
                "placed outside the canonical repository."
            ) from exc
        raise
    status = os.fstat(fd)
    if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
        os.close(fd)
        detail = (
            "not a regular file"
            if not stat.S_ISREG(status.st_mode)
            else f"has {status.st_nlink} hard links"
        )
        raise LockPathConfinementError(
            f"Refusing to use lock file {name!r}: it {detail}; the lock inode must have exactly "
            "one repository-owned name before it can be truncated or written."
        )
    return fd


def _open_confined_lock_fd(repository_path: Path, *, create: bool) -> int:
    """Open `<canonical repository>/.agentos/workflow.lock`, never leaving the repository.

    The walk starts from the *canonical* (fully symlink-resolved) repository root and descends one
    literal component at a time with `O_NOFOLLOW`, so the returned descriptor is guaranteed to
    refer to a file physically under that root: nothing between the root and the lock file can be
    a symlink, and the caller never re-opens by path (which is what would reintroduce a race).
    """
    root = repository_path.resolve()
    if create:
        os.makedirs(root, exist_ok=True)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        control_fd = _open_directory_component(root_fd, _AGENTOS_DIRECTORY_NAME, create=create)
        try:
            return _open_lock_file_component(control_fd, DEFAULT_LOCK_FILENAME, create=create)
        finally:
            os.close(control_fd)
    finally:
        os.close(root_fd)


class LockMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    process_id: int
    hostname: str
    repository_identity: str
    repository_path: str
    acquired_at: str


class RepositoryLock:
    """A per-target-repository mutual-exclusion lock. See module docstring for the model."""

    def __init__(
        self,
        *,
        workflow_id: str,
        repository_identity: str,
        repository_path: Path,
    ) -> None:
        """The lock path is never a caller-supplied value — it is always
        `canonical_lock_path(repository_path)`, computed here and exposed only as a read-only
        `lock_path` property. This is deliberate, not an oversight: an earlier revision accepted
        an arbitrary `lock_path` constructor argument, which let two `RepositoryLock` instances
        for the identical canonical repository hold two independent OS-level `flock`s
        simultaneously (one per distinct path), defeating "exactly one active workflow per
        target repository" (`ARCHITECTURE.md` §5) at the primitive level — `flock` only
        serializes callers contending on the *same* file. There is no parameter through which a
        caller can select a different path, and no diagnostic-metadata check could substitute for
        this, since metadata is explicitly never authoritative (module docstring).
        """
        self._lock_path = canonical_lock_path(repository_path)
        self._workflow_id = workflow_id
        self._repository_identity = repository_identity
        self._repository_path = repository_path
        self._fd: int | None = None

    @classmethod
    def for_config(cls, config: WorkflowConfig, *, workflow_id: str) -> "RepositoryLock":
        """Derive the lock from an already-loaded `WorkflowConfig`.

        The lock file's location comes from `canonical_lock_path(config.repository_path)` —
        never from `config.state_directory`. `state_directory` is per-config, not guaranteed
        unique per physical repository, so two configurations naming the same target repository
        with different `state_directory` values must still produce the *same* lock path (and so
        genuinely contend) — deriving from the repository's own canonical path, rather than a
        separately-configurable storage location, is what guarantees that. This is now identical
        in effect to direct construction: both paths through this class derive the lock's
        location purely from `repository_path`, so there is no divergent "canonical factory vs.
        low-level constructor" behavior to reconcile.
        """
        return cls(
            workflow_id=workflow_id,
            repository_identity=config.repository_identity,
            repository_path=config.repository_path,
        )

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    @property
    def is_held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        if self._fd is not None:
            raise LockStateError(f"Lock already held by this instance: {self._lock_path}")
        fd = _open_confined_lock_fd(self._repository_path, create=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            held_by = self._read_metadata_unlocked()
            os.close(fd)
            detail = f" recorded holder: {held_by.model_dump()}" if held_by is not None else ""
            raise LockContentionError(
                f"Repository lock already held: {self._lock_path}.{detail}"
            ) from exc
        except BaseException:
            os.close(fd)
            raise
        # The OS-level flock is now held by `fd`. Everything below is bookkeeping (building and
        # writing metadata) that can still fail (e.g. disk full, encoding error) — if it does,
        # the flock and the fd must both be released here, or they leak: a bare `int` fd has no
        # destructor, so nothing else will ever close it, and the kernel keeps the flock held by
        # this process until it exits, effectively wedging the lock for as long as the process
        # runs (`self._fd` is never set, so `is_held`/`release()` have no way to find it either).
        try:
            metadata = LockMetadata(
                workflow_id=self._workflow_id,
                process_id=os.getpid(),
                hostname=socket.gethostname(),
                repository_identity=self._repository_identity,
                repository_path=str(self._repository_path),
                acquired_at=datetime.now(UTC).isoformat(),
            )
            os.ftruncate(fd, 0)
            _write_all(fd, metadata.model_dump_json().encode("utf-8"))
            os.fsync(fd)
        except BaseException:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
            raise
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def read_metadata(self) -> LockMetadata | None:
        """Read the lock file's metadata without attempting acquisition.

        Diagnostic only: the returned value may describe a stale, no-longer-held lock, or be
        `None` if the file is absent, empty, or unparseable. Never treat a non-`None` result as
        proof the lock is currently active.
        """
        return self._read_metadata_unlocked()

    def _read_metadata_unlocked(self) -> LockMetadata | None:
        """Reads through the same confined walk `acquire` uses (never `Path.read_text`, which
        would happily follow a symlinked `.agentos` and disclose the bytes of an external file).
        A confinement violation is reported as "no readable metadata" rather than raised, matching
        this method's existing contract that absent/empty/unparseable all yield `None`.
        """
        try:
            fd = _open_confined_lock_fd(self._repository_path, create=False)
        except (LockPathConfinementError, OSError):
            return None
        try:
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError:
            return None
        if not raw.strip():
            return None
        try:
            return LockMetadata.model_validate_json(raw)
        except ValueError:
            return None

    def __enter__(self) -> "RepositoryLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
