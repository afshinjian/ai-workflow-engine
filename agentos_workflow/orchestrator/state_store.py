"""Persistent state store and audit log (AUDIT_MODEL.md; ARCHITECTURE.md §2).

Two record schemas, matching `AUDIT_MODEL.md` §2-3 field-for-field (no fields added or
renamed): `StateTransitionRecord` (workflow-state history) and `CommandExecutionRecord`
(command-execution audit trail). Storage layout is explicitly left as "AUTO-002 implementation
detail" by `AUDIT_MODEL.md` §5; this module's choice: state-transition records are appended to
`<state_directory>/<workflow_id>/transitions.jsonl` (matching `CONFIGURATION_MODEL.md`'s own
description of `state_directory` as "persistent workflow-state storage"), and command-execution
records to `<audit_directory>/<workflow_id>/commands.jsonl` (matching `AUDIT_MODEL.md` §2's own
description of `stdout_ref`/`stderr_ref` as paths "under the audit directory"). Both are
append-only JSONL: every write is a single `O_APPEND` write of one complete, `fsync`-flushed
line; nothing in this module's public API can edit, truncate, or delete a previously written
record (`AUDIT_MODEL.md` §4).

The "current state" of a workflow (requirement: reading the persisted state must faithfully
reconstruct the latest workflow state) is never stored as a separate, independently-mutable
snapshot — that would create a second source of truth that could drift from the append-only
history. It is always derived by replaying `transitions.jsonl` and taking the last record's
`to_state`, so the audit trail alone remains authoritative.

Validating `workflow_id` as a safe path *component* (`_safe_workflow_id`) is not by itself enough
to keep a record inside its configured root (AUTO002-IR-02): the component was still joined
lexically and opened by path, so a symlinked `<root>/<workflow_id>` directory — or a symlinked
`transitions.jsonl`/`commands.jsonl` inside a real one — was followed at append time, writing
audit records to a physical location outside the configured root. Every record path is therefore
walked one component at a time with `O_NOFOLLOW` relative to a directory file descriptor
(`dir_fd`), starting from the already-canonical root, for reads as well as writes: a symlinked
component is refused by the kernel *at the open itself*, so no separate check can be invalidated
by a race, and nothing outside the root is created, appended to, truncated, or read. Transition
and command storage share one primitive (`_confined_record_fd`) so the two histories cannot
drift apart in what they enforce. This module is POSIX-only regardless (`fcntl.flock`), so
`dir_fd`/`O_NOFOLLOW` add no portability constraint it did not already have.
"""

import errno
import fcntl
import json
import os
import re
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from agentos_workflow.config.schema import WorkflowConfig


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_iso8601(value: str) -> str:
    """Every audit timestamp must be timezone-aware: a naive value cannot be safely compared
    against another timestamp (Python raises `TypeError` mixing naive/aware `datetime`s), which
    would silently defeat the monotonic-ordering check `_require_monotonic_order` below relies on.
    Every timestamp this codebase actually produces is already tz-aware (`datetime.now(UTC)`), so
    this only ever rejects a value nothing legitimate would produce.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"must be an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(
            f"must be a timezone-aware ISO-8601 timestamp (naive value rejected): {value!r}"
        )
    return value


_ACTOR_AGENT_RE = re.compile(r"agent:.+")


def _validate_actor(value: str) -> str:
    if value in {"human", "orchestrator"} or _ACTOR_AGENT_RE.fullmatch(value):
        return value
    raise ValueError('actor must be "human", "orchestrator", or "agent:<Name>"')


_AUDIT_REF_FORBIDDEN_TOKENS = ("..", "\x00")


def _validate_audit_ref(value: str, field: str) -> str:
    """`stdout_ref`/`stderr_ref` are documented (`AUDIT_MODEL.md` §2) as "a reference (file path
    under the audit directory)" — never inlined content, never an arbitrary filesystem location.
    A bare `Field(min_length=1)` accepted any nonblank string, including an absolute path or a
    `..` parent-traversal segment that would point outside the audit directory entirely. This
    checks only syntactic confinement (no absolute path, no parent-traversal token, no NUL byte)
    since a bare field validator has no access to a configured audit root to check existence
    against — the same structural-safety discipline `agentos_workflow/observation/evidence.py`
    (AUTO002-F07) applies to evidence-artifact references.
    """
    if (
        not value
        or value.startswith("/")
        or any(token in value for token in _AUDIT_REF_FORBIDDEN_TOKENS)
    ):
        raise ValueError(
            f"{field} must be a safe, relative path confined under the audit directory (no "
            f"absolute path, no parent-traversal segment, no NUL byte): {value!r}"
        )
    return value


class CommandExecutionRecord(StrictModel):
    """AUDIT_MODEL.md §2."""

    normalized_command_identity: str = Field(min_length=1)
    start_time: str
    completion_time: str
    exit_code: int | None
    timeout_status: bool
    stdout_ref: str = Field(min_length=1)
    stderr_ref: str = Field(min_length=1)

    _validate_start_time = field_validator("start_time")(_validate_iso8601)
    _validate_completion_time = field_validator("completion_time")(_validate_iso8601)
    _validate_stdout_ref = field_validator("stdout_ref")(
        lambda value: _validate_audit_ref(value, "stdout_ref")
    )
    _validate_stderr_ref = field_validator("stderr_ref")(
        lambda value: _validate_audit_ref(value, "stderr_ref")
    )

    @model_validator(mode="after")
    def _validate_completion_not_before_start(self) -> "CommandExecutionRecord":
        if datetime.fromisoformat(self.completion_time) < datetime.fromisoformat(self.start_time):
            raise ValueError(
                f"completion_time {self.completion_time!r} is before start_time "
                f"{self.start_time!r} — a command cannot complete before it starts."
            )
        return self


class StateTransitionRecord(StrictModel):
    """AUDIT_MODEL.md §3.

    `target_repository` binds repository *identity*; `repository_path` independently binds the
    canonical repository *path* bound at authorization. AUDIT_MODEL.md §3 documents these as
    distinct fields because identity and path are two facts a caller could each independently get
    wrong (or a corrupted record could each independently drift) — the same "every binding field
    independently checkable" discipline `AuthorizationRecord` applies to its own identity/path
    pair.
    """

    workflow_id: str = Field(min_length=1)
    target_repository: str = Field(min_length=1)
    repository_path: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    from_state: str = Field(min_length=1)
    to_state: str = Field(min_length=1)
    timestamp: str
    actor: str
    gate_evidence_ref: str | None = None

    _validate_timestamp = field_validator("timestamp")(_validate_iso8601)
    _validate_actor = field_validator("actor")(_validate_actor)


class StateStoreError(Exception):
    """Base error for state-store persistence and read failures."""


class StateStoreCorruptionError(StateStoreError):
    """Raised when a persisted record cannot be parsed or fails schema validation.

    Never silently skipped and never causes a truncated read: audit completeness is a safety
    property (AUDIT_MODEL.md §8), so a compromised history is surfaced as a hard failure. The
    on-disk file itself is left completely untouched by a read.
    """


class StateStoreOrderingError(StateStoreError):
    """Raised when an append would place a record earlier than the last persisted one.

    Distinct from `StateStoreCorruptionError`: nothing on disk is wrong: the *submitted* record
    is. Raised before any byte is written, so the existing history is left byte-for-byte intact
    and still replayable. See `_append_jsonl_line` for the ordering rule (non-decreasing).
    """


class StateStorePathConfinementError(StateStoreError):
    """Raised when a record path cannot be opened without leaving its configured root.

    Distinct from `StateStoreCorruptionError`: the persisted records themselves may be perfectly
    well-formed — the defect is *where* the path points. A component of
    `<root>/<workflow_id>/<file>.jsonl` is a symlink, so following it would read or append audit
    records outside the root the configuration designated. Raised before any `mkdir`, create,
    append, truncate, or read, so the external target is left byte-for-byte untouched.
    """


_TRANSITIONS_FILENAME = "transitions.jsonl"
_COMMANDS_FILENAME = "commands.jsonl"
_WORKFLOW_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _safe_workflow_id(workflow_id: str) -> str:
    if not _WORKFLOW_ID_RE.fullmatch(workflow_id):
        raise StateStoreError(
            f"workflow_id {workflow_id!r} must match {_WORKFLOW_ID_RE.pattern!r} "
            "(it is used as a path component; this also blocks path traversal)"
        )
    return workflow_id


def _write_all(fd: int, payload: bytes) -> None:
    """`os.write` is permitted by POSIX to write fewer bytes than requested (a "short write") —
    a real possibility for a pipe or a write interrupted by a signal, and not something the
    stdlib's raw `os.write` guards against itself (unlike a buffered `io` stream's `.write()`,
    which always writes its complete argument or raises). Silently ignoring the return value
    would risk appending a truncated, unparseable JSON line — corrupting the append-only audit
    trail (`AUDIT_MODEL.md` §4) — so every byte is written in a loop, and a call that makes zero
    progress raises rather than spinning forever.
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


def _fsync_directory(path: Path) -> None:
    """Durably flush directory-entry changes (create/link/unlink/rename) for `path`."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_directory_durable(path: Path) -> None:
    """Create `path` and durably publish every newly-created directory entry."""
    missing: list[Path] = []
    candidate = path
    while not candidate.exists():
        missing.append(candidate)
        candidate = candidate.parent
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        _fsync_directory(created.parent)


# `O_NOFOLLOW` on a component that *is* a symlink fails with `ELOOP` on Linux and `EMLINK` on the
# BSDs/macOS; combined with `O_DIRECTORY`, Linux reports it as `ENOTDIR` instead (the link itself
# is not a directory) — the same errno a plain regular file gives, which is why `_refused_symlink`
# distinguishes the two by inspecting the name rather than trusting the errno alone.
_SYMLINK_REFUSED_ERRNOS = frozenset({errno.ELOOP, errno.EMLINK, errno.ENOTDIR})


def _refused_symlink(parent_fd: int, name: str, exc: OSError) -> bool:
    """Whether `exc` from an `O_NOFOLLOW` open of `name` means "that component is a symlink".

    Consulted only to *classify an already-failed open*. The open itself, not this check, is what
    enforces confinement, so this follow-up `lstat` being inherently racy cannot widen the
    refusal: by the time it runs, nothing has been created, appended to, truncated, or read.
    """
    if exc.errno not in _SYMLINK_REFUSED_ERRNOS:
        return False
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=parent_fd).st_mode)
    except OSError:
        return False


def _open_confined_subdirectory(parent_fd: int, name: str, *, create: bool) -> int | None:
    """Open subdirectory `name` of `parent_fd`, refusing to follow it if it is a symlink.

    Returns `None` when `create` is false and the directory simply does not exist yet (a workflow
    with no persisted history is not an error). `O_NOFOLLOW` constrains only the final component,
    which is exactly one single literal segment here — never a multi-segment path.
    """
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        else:
            os.fsync(parent_fd)  # durably publish the new directory entry
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except FileNotFoundError:
        if create:
            raise
        return None
    except OSError as exc:
        if _refused_symlink(parent_fd, name, exc):
            raise StateStorePathConfinementError(
                f"Refusing to use workflow directory {name!r}: it is a symlink, so records would "
                "be stored outside the configured root."
            ) from exc
        raise


def _validate_confined_regular_file(fd: int, *, display_path: Path) -> None:
    """Require a regular, single-link inode before any confined file is trusted.

    ``O_NOFOLLOW`` prevents a symlink from being followed at open time, but a hard link is another
    name for the same inode and is intentionally invisible to pathname resolution.  A record path
    hard-linked to a same-user file outside the configured root would otherwise let an append here
    mutate that external file.  A link count other than one is therefore a confinement violation,
    as is any non-regular file (FIFO/device/socket).
    """
    status = os.fstat(fd)
    if not stat.S_ISREG(status.st_mode):
        raise StateStorePathConfinementError(
            f"Refusing to use {display_path}: confined record targets must be regular files."
        )
    if status.st_nlink != 1:
        raise StateStorePathConfinementError(
            f"Refusing to use {display_path}: inode has {status.st_nlink} hard links; a record "
            "file must have exactly one name so writes cannot alias a file outside its boundary."
        )


@contextmanager
def _confined_workflow_directory_fd(
    root: Path, workflow_id: str, *, create: bool
) -> Iterator[int | None]:
    """Yield the literal workflow directory below ``root`` through a no-symlink descriptor walk."""
    safe_workflow_id = _safe_workflow_id(workflow_id)
    canonical_root = root.resolve()
    if create:
        _ensure_directory_durable(canonical_root)
    try:
        root_fd = os.open(canonical_root, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        if create:
            raise
        yield None
        return
    try:
        workflow_fd = _open_confined_subdirectory(root_fd, safe_workflow_id, create=create)
        if workflow_fd is None:
            yield None
            return
        try:
            yield workflow_fd
        finally:
            os.close(workflow_fd)
    finally:
        os.close(root_fd)


@contextmanager
def _confined_record_fd(
    root: Path, workflow_id: str, filename: str, *, write: bool
) -> Iterator[tuple[int | None, int | None]]:
    """Open `<canonical root>/<workflow_id>/<filename>` without ever leaving the canonical root.

    The single primitive behind *both* transition and command storage, and behind both reads and
    writes, so the two histories cannot enforce different confinement rules. The walk starts at
    the fully symlink-resolved root and descends one literal component at a time with
    `O_NOFOLLOW`; the yielded descriptor therefore necessarily refers to a file physically under
    that root, and callers work from the descriptor rather than re-opening by path (which is what
    would reintroduce a check-then-open race).

    Yields `(record_fd, workflow_directory_fd)`, or `(None, None)` when a read finds no history.
    The workflow directory's descriptor is yielded alongside — and held open for the caller's
    whole operation — so an append can `fsync` it afterwards to durably publish a newly created
    record file's directory entry without reopening that directory by path.
    """
    with _confined_workflow_directory_fd(root, workflow_id, create=write) as workflow_fd:
        if workflow_fd is None:
            yield (None, None)
            return
        record_fd = _open_confined_record_file(workflow_fd, filename, write=write)
        if record_fd is None:
            yield (None, None)
            return
        try:
            _validate_confined_regular_file(record_fd, display_path=root / workflow_id / filename)
            yield (record_fd, workflow_fd)
        finally:
            os.close(record_fd)


def _open_confined_record_file(parent_fd: int, name: str, *, write: bool) -> int | None:
    """Open record file `name` inside `parent_fd`, refusing to follow it if it is a symlink.

    For writes, `O_CREAT | O_APPEND | O_NOFOLLOW` is one atomic step: an existing symlink at
    `name` fails the open outright rather than being created through, and append-only semantics
    are preserved exactly as before (no `O_TRUNC`). The write mode is `O_RDWR`, not `O_WRONLY`,
    solely so the ordering check (AUTO002-IR-04) can read the existing tail through this *same*
    file description while holding its lock; `O_APPEND` still forces every write to end-of-file,
    so readability grants no ability to overwrite or truncate an existing record.
    """
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND if write else os.O_RDONLY
    try:
        return os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
    except FileNotFoundError:
        if write:
            raise
        return None
    except OSError as exc:
        if _refused_symlink(parent_fd, name, exc):
            raise StateStorePathConfinementError(
                f"Refusing to use record file {name!r}: it is a symlink, so records would be "
                "read from or written outside the configured root."
            ) from exc
        raise


class _DuplicateJSONKeyError(Exception):
    """Internal signal from the duplicate-key hook, carrying only the offending key.

    Not a `ValueError`, so it can never be mistaken for an ordinary `JSONDecodeError`, and not
    part of the public taxonomy: every call site converts it to `StateStoreCorruptionError` with
    the file and line context the hook itself cannot know.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"duplicate JSON object key {key!r}")


def _loads_rejecting_duplicate_keys(text: str) -> object:
    """`json.loads`, but a repeated key in *any* object — at any nesting level — is an error.

    Standard JSON parsing silently applies last-key-wins, so a tampered record could carry two
    `to_state` or `timestamp` values and be replayed as whichever the parser happened to keep
    (AUTO002-IR-05). An ambiguous persisted record has no single correct reading, so it must fail
    closed before model validation rather than have one meaning chosen for it. `object_pairs_hook`
    sees the raw key/value pairs of every object before any dict collapses them, which is what
    makes nested duplicates detectable at all. Mirrors the shape of the packaged event store's own
    `_parse_json_no_duplicate_keys` for consistency, deliberately re-implemented here rather than
    imported, so this package takes on no dependency on `ai_workflow_engine`'s internals.
    """

    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJSONKeyError(key)
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


def _pread_all(fd: int) -> bytes:
    """Read a whole record file positionally, leaving the descriptor's own offset untouched."""
    chunks: list[bytes] = []
    offset = 0
    while True:
        chunk = os.pread(fd, 65536, offset)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        offset += len(chunk)


def _last_persisted_timestamp(fd: int, path: Path, timestamp_field: str) -> datetime | None:
    """The ordering timestamp of the last durable record, or `None` if there is no history.

    Called with the append `flock` already held, and reads through the *same* file description
    that the append will use, so no other writer can slip a record in between the check and the
    write. A malformed tail is reported as corruption rather than being appended onto: extending
    a history that cannot be replayed would only deepen the damage.
    """
    data = _pread_all(fd)
    if not data:
        return None
    if not data.endswith(b"\n"):
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: missing terminal newline (possible torn append); "
            "refusing to append onto an unreadable history."
        )
    last_line = data.decode("utf-8").split("\n")[-2]
    if last_line == "":
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: final record is blank; refusing to append onto an "
            "unreadable history."
        )
    try:
        payload = _loads_rejecting_duplicate_keys(last_line)
    except _DuplicateJSONKeyError as exc:
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: final record has a duplicate JSON object key "
            f"{exc.key!r}; refusing to append onto an unreadable history."
        ) from exc
    except ValueError as exc:
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: final record is not valid JSON; refusing to append "
            "onto an unreadable history."
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get(timestamp_field), str):
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: final record has no usable {timestamp_field!r}; "
            "refusing to append onto an unreadable history."
        )
    try:
        return datetime.fromisoformat(payload[timestamp_field])
    except ValueError as exc:
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: final record's {timestamp_field!r} is not an ISO-8601 "
            "timestamp; refusing to append onto an unreadable history."
        ) from exc


def _append_jsonl_line(
    root: Path,
    workflow_id: str,
    filename: str,
    json_line: str,
    *,
    timestamp_field: str,
    new_timestamp: str,
) -> None:
    """`os.O_APPEND` only guarantees that a single `write()` syscall lands at end-of-file
    atomically — it says nothing about two concurrent writers each issuing *multiple* `write()`
    calls for one logical record (a real possibility: `_write_all` above loops on a short write).
    Without exclusion, two such writers' syscalls can interleave byte-for-byte, corrupting both
    records. An exclusive `flock` held for the entire open-write-fsync-close sequence — the same
    OS-level mutual-exclusion primitive `lock.py` already relies on for the repository lock
    (DD-10) — serializes every append to this file, whether from threads or separate processes.

    Chronological ordering is enforced here, under that same lock, *before* any byte is written
    (AUTO002-IR-04). Previously the writer accepted a record older than the one already persisted;
    the append succeeded, and `_require_monotonic_order` then rejected the whole history on every
    subsequent read — the store could be driven into a permanently unreadable state through its
    own supported API. The rule applied is exactly the reader's: timestamps must be
    *non-decreasing*, so an equal timestamp is accepted and only a strictly earlier one is
    refused. Reading the tail through the same locked file description (rather than a separate
    open) is what makes the check-then-append indivisible.
    """
    payload = (json_line + "\n").encode("utf-8")
    with _confined_record_fd(root, workflow_id, filename, write=True) as (fd, directory_fd):
        # `write=True` creates or raises, so neither descriptor can be None here.
        if fd is None or directory_fd is None:  # pragma: no cover - unreachable for write=True
            raise StateStoreError(f"Failed to open record file {filename!r} for append.")
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            display_path = root / workflow_id / filename
            previous = _last_persisted_timestamp(fd, display_path, timestamp_field)
            current = datetime.fromisoformat(new_timestamp)
            if previous is not None and current < previous:
                raise StateStoreOrderingError(
                    f"Refusing to append to {display_path}: {timestamp_field} {new_timestamp!r} "
                    f"precedes the last persisted record's {previous.isoformat()!r}. Records must "
                    "be appended in non-decreasing timestamp order, or the resulting history "
                    "would be unreadable."
                )
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.fsync(directory_fd)


_RecordT = TypeVar("_RecordT", bound=BaseModel)


def _read_jsonl(
    root: Path, workflow_id: str, filename: str, model: type[_RecordT]
) -> list[_RecordT]:
    """Read a whole confined JSONL history. `path` below is used only to label errors."""
    path = root / workflow_id / filename
    with _confined_record_fd(root, workflow_id, filename, write=False) as (fd, _):
        if fd is None:
            return []
        data = _read_all(fd)
    return _parse_jsonl(path, data, model)


def _read_all(fd: int) -> bytes:
    """Read a record file to EOF from an already-confined descriptor (never reopened by path)."""
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _parse_jsonl(path: Path, data: bytes, model: type[_RecordT]) -> list[_RecordT]:
    if data and not data.endswith(b"\n"):
        raise StateStoreCorruptionError(
            f"Corrupt record file {path}: missing terminal newline (possible torn append)."
        )
    records: list[_RecordT] = []
    if not data:
        return records
    # `data` ends with a newline, so the final split element is always a trailing empty string
    # that is not itself a record.
    for line_number, line in enumerate(data.decode("utf-8").split("\n")[:-1], start=1):
        if line == "":
            raise StateStoreCorruptionError(
                f"Corrupt record at {path}:{line_number}: blank JSONL records are forbidden."
            )
        # Parsed separately from validation so an *ambiguous* record fails closed before any
        # model ever sees one arbitrarily-chosen reading of it (AUTO002-IR-05).
        try:
            payload = _loads_rejecting_duplicate_keys(line)
        except _DuplicateJSONKeyError as exc:
            raise StateStoreCorruptionError(
                f"Corrupt record at {path}:{line_number}: duplicate JSON object key "
                f"{exc.key!r} — the record has no single unambiguous reading."
            ) from exc
        except ValueError as exc:
            raise StateStoreCorruptionError(
                f"Corrupt record at {path}:{line_number}: not valid JSON."
            ) from exc
        try:
            records.append(model.model_validate(payload))
        except ValidationError as exc:
            raise StateStoreCorruptionError(
                f"Corrupt record at {path}:{line_number}: {exc}"
            ) from exc
    return records


def _require_monotonic_order(
    path: Path, records: list[_RecordT], *, timestamp_of: Callable[[_RecordT], str]
) -> None:
    """Raise `StateStoreCorruptionError` unless `records`' timestamps are non-decreasing in
    on-disk (append) order — a real append-only writer (`_append_jsonl_line`, serialized by
    `flock` for the entire open-write-fsync-close sequence) can never itself produce an
    out-of-order file; timestamps going backwards is evidence of direct tampering or a corrupted
    write outside this module's own append path, and is treated with the same severity as any
    other audit corruption (`AUDIT_MODEL.md` §8: audit completeness is a safety property).
    """
    previous_timestamp: datetime | None = None
    previous_index = 0
    for index, record in enumerate(records):
        current_timestamp = datetime.fromisoformat(timestamp_of(record))
        if previous_timestamp is not None and current_timestamp < previous_timestamp:
            raise StateStoreCorruptionError(
                f"Corrupt record file {path}: record {index + 1} (timestamp "
                f"{timestamp_of(record)!r}) precedes record {previous_index + 1} (timestamp "
                f"{timestamp_of(records[previous_index])!r}) — records are not in non-decreasing "
                "timestamp order."
            )
        previous_timestamp = current_timestamp
        previous_index = index


class StateStore:
    """Append-only persistence for workflow-state transitions and command-execution audit
    records, split across the configured `state_directory` and `audit_directory` respectively.
    See the module docstring for the storage-layout decision.
    """

    def __init__(self, *, state_directory: Path, audit_directory: Path) -> None:
        self._state_directory = state_directory
        self._audit_directory = audit_directory

    @classmethod
    def for_config(cls, config: WorkflowConfig) -> "StateStore":
        return cls(
            state_directory=config.state_directory,
            audit_directory=config.audit_directory,
        )

    @property
    def state_directory(self) -> Path:
        return self._state_directory

    @property
    def audit_directory(self) -> Path:
        return self._audit_directory

    def _transitions_path(self, workflow_id: str) -> Path:
        return self._state_directory / _safe_workflow_id(workflow_id) / _TRANSITIONS_FILENAME

    def _commands_path(self, workflow_id: str) -> Path:
        return self._audit_directory / _safe_workflow_id(workflow_id) / _COMMANDS_FILENAME

    def record_transition(self, record: StateTransitionRecord) -> None:
        _append_jsonl_line(
            self._state_directory,
            _safe_workflow_id(record.workflow_id),
            _TRANSITIONS_FILENAME,
            record.model_dump_json(),
            timestamp_field="timestamp",
            new_timestamp=record.timestamp,
        )

    def record_command_execution(self, workflow_id: str, record: CommandExecutionRecord) -> None:
        _append_jsonl_line(
            self._audit_directory,
            _safe_workflow_id(workflow_id),
            _COMMANDS_FILENAME,
            record.model_dump_json(),
            # Command histories are ordered by `completion_time`, matching exactly what
            # `read_command_executions` enforces on read — the two must never diverge.
            timestamp_field="completion_time",
            new_timestamp=record.completion_time,
        )

    def list_workflow_ids(self) -> list[str]:
        """Every workflow that actually has a persisted transition history, sorted.

        Read-only and creation-free by construction (AUTO-009): a missing `state_directory` is an
        empty result, never a directory this call brings into existence, so listing a repository
        that has never run a workflow cannot manufacture the storage that makes it look as though
        it had. Membership is decided by opening `<workflow_id>/transitions.jsonl` through the same
        `_confined_record_fd` walk every other read uses (`write=False`, so nothing is created):
        a directory with no history file is not a workflow, which is what keeps this from inventing
        entries out of stray directories.

        A name that is not a legal `workflow_id` is skipped rather than reported — it was never
        writable through this API, so it is not a workflow this store owns. A *symlinked* workflow
        directory or history file is deliberately not skipped: `_confined_record_fd` raises
        `StateStorePathConfinementError` and fails the whole listing, because a symlink where a
        record path belongs is evidence of tampering (module docstring), and quietly omitting the
        affected workflow would present a short list as a complete one.
        """
        try:
            names = os.listdir(self._state_directory.resolve())
        except FileNotFoundError:
            return []
        found: list[str] = []
        for name in sorted(names):
            if not _WORKFLOW_ID_RE.fullmatch(name):
                continue
            with _confined_record_fd(
                self._state_directory, name, _TRANSITIONS_FILENAME, write=False
            ) as (fd, _):
                if fd is not None:
                    found.append(name)
        return found

    def read_transitions(self, workflow_id: str) -> list[StateTransitionRecord]:
        path = self._transitions_path(workflow_id)
        records = _read_jsonl(
            self._state_directory,
            _safe_workflow_id(workflow_id),
            _TRANSITIONS_FILENAME,
            StateTransitionRecord,
        )
        for record in records:
            if record.workflow_id != workflow_id:
                raise StateStoreCorruptionError(
                    f"Corrupt record file {path}: a record claims workflow_id "
                    f"{record.workflow_id!r}, but was read as part of workflow "
                    f"{workflow_id!r}'s persisted history."
                )
        _require_monotonic_order(path, records, timestamp_of=lambda record: record.timestamp)
        return records

    def read_command_executions(self, workflow_id: str) -> list[CommandExecutionRecord]:
        path = self._commands_path(workflow_id)
        records = _read_jsonl(
            self._audit_directory,
            _safe_workflow_id(workflow_id),
            _COMMANDS_FILENAME,
            CommandExecutionRecord,
        )
        _require_monotonic_order(path, records, timestamp_of=lambda record: record.completion_time)
        return records

    def current_state(self, workflow_id: str) -> str | None:
        """The `to_state` of the most recently persisted transition, or `None` if the workflow
        has no persisted transitions yet. Faithful reconstruction by replay, not by a separate
        mutable snapshot — see the module docstring.
        """
        transitions = self.read_transitions(workflow_id)
        if not transitions:
            return None
        return transitions[-1].to_state
