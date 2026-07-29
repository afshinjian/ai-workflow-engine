"""Read-only file adapter (`ARCHITECTURE.md` §3; SC-06..SC-08, SC-34, SC-35).

The only code in the dashboard permitted to open a repository file. Every entry point takes a
repository-relative path, resolves it through `RepositoryRoot` (root confinement, symlink
rejection, deny-list), and reads with a byte cap. There is no write path here — not a guarded
one, not a private one: the module contains no `open(..., "w")`, no `Path.write_*`, and no
`shutil` copy, so `TR-08`'s "zero repository writes exist" is a property of the source rather
than a promise about behavior.

Decoding is deliberately lossy: repository content is untrusted input (`SECURITY_MODEL.md`
§1), and a non-UTF-8 governance document must degrade to a readable, flagged view rather than
raise (SC-34). Every result therefore carries `decoded_with_replacement` and `truncated` flags
so a caller can surface the degradation instead of hiding it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agentos_dashboard.core import DEFAULT_HEAD_TAIL_BYTES, DEFAULT_MAX_READ_BYTES, DashboardError
from agentos_dashboard.core.paths import RepositoryRoot

__all__ = [
    "FileAccessError",
    "FileFacts",
    "FileRead",
    "FileRefusal",
    "HeadTailRead",
    "digest_file",
    "read_head_tail",
    "read_text",
    "stat_file",
]

_DIGEST_CHUNK_BYTES = 64 * 1024


class FileRefusal(StrEnum):
    """Why a resolved path could not be read."""

    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    IO_ERROR = "io_error"
    INVALID_LIMIT = "invalid_limit"


class FileAccessError(DashboardError):
    """A path resolved inside the root but could not be read as a file."""

    def __init__(self, relative: str, refusal: FileRefusal, detail: str) -> None:
        super().__init__(f"{refusal.value}: {detail} ({relative!r})")
        self.relative = relative
        self.refusal = refusal
        self.detail = detail


@dataclass(frozen=True)
class FileFacts:
    """EN-03 metadata for one repository file. Cheap: one `stat`, no read."""

    path: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class FileRead:
    """A capped, error-tolerant text read of one repository file."""

    path: str
    text: str
    size_bytes: int
    read_bytes: int
    truncated: bool
    decoded_with_replacement: bool


@dataclass(frozen=True)
class HeadTailRead:
    """The head and tail of a file too large to display whole (SC-35)."""

    path: str
    head: str
    tail: str
    size_bytes: int
    omitted_bytes: int
    decoded_with_replacement: bool

    @property
    def truncated(self) -> bool:
        return self.omitted_bytes > 0


def _require_positive(relative: str, name: str, value: int) -> None:
    if value <= 0:
        raise FileAccessError(relative, FileRefusal.INVALID_LIMIT, f"{name} must be positive")


def _resolve_file(root: RepositoryRoot, relative: str) -> Path:
    """Resolve `relative` and prove it is a regular file, with typed refusals throughout."""
    resolved = root.resolve(relative)
    try:
        stat_result = resolved.stat()
    except FileNotFoundError as exc:
        raise FileAccessError(relative, FileRefusal.NOT_FOUND, "no such file") from exc
    except OSError as exc:
        raise FileAccessError(relative, FileRefusal.IO_ERROR, str(exc)) from exc
    # `stat` follows symlinks, and `resolve` already proved the target is inside the root, so a
    # directory, FIFO, device, or socket is the only thing left to exclude here.
    if not resolved.is_file():
        raise FileAccessError(
            relative, FileRefusal.NOT_A_FILE, f"not a regular file (mode {stat_result.st_mode:o})"
        )
    return resolved


def _decode(payload: bytes) -> tuple[str, bool]:
    """Decode UTF-8 tolerantly, reporting whether any byte had to be replaced."""
    try:
        return payload.decode("utf-8"), False
    except UnicodeDecodeError:
        return payload.decode("utf-8", errors="replace"), True


def stat_file(root: RepositoryRoot, relative: str) -> FileFacts:
    """Size and modification time of one repository file."""
    resolved = _resolve_file(root, relative)
    try:
        stat_result = resolved.stat()
    except OSError as exc:  # pragma: no cover - raced away between resolve and stat
        raise FileAccessError(relative, FileRefusal.IO_ERROR, str(exc)) from exc
    return FileFacts(
        path=root.relative_of(resolved),
        size_bytes=stat_result.st_size,
        mtime_ns=stat_result.st_mtime_ns,
    )


def read_text(
    root: RepositoryRoot,
    relative: str,
    *,
    max_bytes: int = DEFAULT_MAX_READ_BYTES,
) -> FileRead:
    """Read at most `max_bytes` bytes of a file as tolerantly-decoded UTF-8 text.

    Exceeding the cap is not an error: the read is truncated and flagged, because refusing to
    show a large governance document outright would hide state from the operator, which is the
    failure mode `SOURCE_OF_TRUTH.md` TR-04 exists to prevent.
    """
    _require_positive(relative, "max_bytes", max_bytes)
    resolved = _resolve_file(root, relative)
    try:
        size_bytes = resolved.stat().st_size
        with resolved.open("rb") as handle:
            payload = handle.read(max_bytes)
    except OSError as exc:
        raise FileAccessError(relative, FileRefusal.IO_ERROR, str(exc)) from exc

    text, replaced = _decode(payload)
    return FileRead(
        path=root.relative_of(resolved),
        text=text,
        size_bytes=size_bytes,
        read_bytes=len(payload),
        # The cap is what the caller asked for, so `size_bytes > max_bytes` is not the test:
        # a file that grew between the `stat` and the read would report truncation it did not
        # suffer. What was actually read is what decides.
        truncated=len(payload) < size_bytes,
        decoded_with_replacement=replaced,
    )


def read_head_tail(
    root: RepositoryRoot,
    relative: str,
    *,
    head_bytes: int = DEFAULT_HEAD_TAIL_BYTES,
    tail_bytes: int = DEFAULT_HEAD_TAIL_BYTES,
) -> HeadTailRead:
    """Read the first `head_bytes` and last `tail_bytes` bytes of a file (SC-35).

    When the file is small enough that the two windows would overlap, the head holds the whole
    file, the tail is empty, and `omitted_bytes` is zero — so a caller can render the result
    without special-casing small files.
    """
    _require_positive(relative, "head_bytes", head_bytes)
    _require_positive(relative, "tail_bytes", tail_bytes)
    resolved = _resolve_file(root, relative)
    try:
        with resolved.open("rb") as handle:
            head_payload = handle.read(head_bytes)
            size_bytes = handle.seek(0, 2)
            if size_bytes <= head_bytes + tail_bytes:
                handle.seek(0)
                head_payload = handle.read()
                tail_payload = b""
                omitted = 0
            else:
                handle.seek(size_bytes - tail_bytes)
                tail_payload = handle.read(tail_bytes)
                omitted = size_bytes - head_bytes - tail_bytes
    except OSError as exc:
        raise FileAccessError(relative, FileRefusal.IO_ERROR, str(exc)) from exc

    head_text, head_replaced = _decode(head_payload)
    tail_text, tail_replaced = _decode(tail_payload)
    return HeadTailRead(
        path=root.relative_of(resolved),
        head=head_text,
        tail=tail_text,
        size_bytes=size_bytes,
        omitted_bytes=omitted,
        decoded_with_replacement=head_replaced or tail_replaced,
    )


def digest_file(root: RepositoryRoot, relative: str) -> str:
    """The SHA-256 of a file's whole content, streamed so a large file needs no large buffer.

    Deliberately separate from `stat_file`: the snapshot fingerprint uses cheap `stat` facts,
    and nothing should pay to hash every watched file on every page render.
    """
    resolved = _resolve_file(root, relative)
    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as handle:
            while chunk := handle.read(_DIGEST_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise FileAccessError(relative, FileRefusal.IO_ERROR, str(exc)) from exc
    return digest.hexdigest()
