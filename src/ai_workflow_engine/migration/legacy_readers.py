"""Byte-preserving legacy-artifact discovery and classification (architecture-v3.md
section 14/18: "Legacy terminal artifacts remain byte-preserved, readable and auditable
... Unknown/corrupt artifacts are quarantined").

A legacy-artifact source root mirrors the union of this engine's existing on-disk stores
(`prompt/store.py`, `agents/artifacts.py`, `workflow/event_store.py`, plus an
`approvals/` convention for archived `git/approval.py` YAML files): top-level
directories ``state/``, ``agent-runs/``, ``prompts/``, ``approvals/``. Classification
never guesses: a file's family is determined solely by its position in this fixed,
documented convention plus the *same* integrity checks the corresponding real, existing
store applies at load time (`WorkflowEvent`/`load_history`, `AgentRunRecord`/`load_run`,
`PromptMetadata`/`load`, `CommitApproval`/`PushApproval`) -- never by content sniffing,
trial-and-error across families, or a weaker subset of checks. Anything that does not
fit is quarantined with a stable, specific reason; nothing is ever rewritten, repaired,
or deleted.

Safety invariants enforced throughout this module:

* The source root itself is rejected outright if it is a symlink -- its target is never
  resolved or scanned (F-1).
* No byte of any file is ever read without first proving, via a no-follow ``open()``
  (``O_NOFOLLOW`` where supported) plus an ``fstat`` of the resulting descriptor, that
  the opened object is a genuine regular file -- including every companion (``.patch``/
  ``.md``) read, which never uses a plain ``Path.read_bytes()`` (F-2, F-7). This closes
  the discovery-to-open TOCTOU window: the kernel refuses the open atomically if the
  final path component is a symlink at that instant, and ``fstat`` re-confirms the type
  of the descriptor actually obtained, not a separately lstat'd path.
* A workflow-event history is validated and classified as one unit: a corrupt or
  inconsistent member quarantines every member of that task's history, never just the
  one bad file (F-6). The directory listing is re-taken after reading every member and
  compared to the pre-read snapshot; a mismatch quarantines the whole group rather than
  returning a result assembled across two inconsistent filesystem states (F-7).
* Every filesystem entry reachable from the source root is represented in the result --
  a FIFO, Unix socket, block/character device, or other unsupported node is quarantined
  ``UNSUPPORTED_ENTRY_TYPE`` by identity alone (a no-follow ``lstat``) and is never
  opened, so it can never block this scan or have its "content" read (F-8).
* Every family that reaches a ``KNOWN`` classification performs one final, no-follow
  re-read of each of its members immediately before returning, and compares the fresh
  bytes to what was actually used to build the record; any difference -- content changed,
  the path vanished, or it raced into becoming a symlink -- quarantines the affected
  member(s) ``SOURCE_MUTATED_DURING_SCAN`` instead of returning a possibly-stale ``KNOWN``
  result (F-9). This complements F-7's directory-listing check: a same-path,
  same-filename content mutation is caught even when the set of filenames never changes.
"""

import base64
import binascii
import errno
import hashlib
import json
import os
import stat
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError

from ai_workflow_engine.agents.artifacts import AgentRunRecord, compute_run_id
from ai_workflow_engine.git.approval import CommitApproval, PushApproval
from ai_workflow_engine.migration.errors import MigrationSourceError
from ai_workflow_engine.migration.models import EntryType, LegacyArtifactRecord, QuarantineReason
from ai_workflow_engine.prompt.models import PromptMetadata
from ai_workflow_engine.prompt.renderer import TemplateRenderError, canonical_json, render_prompt
from ai_workflow_engine.workflow.event_store import task_dir_name
from ai_workflow_engine.workflow.events import WorkflowEvent
from ai_workflow_engine.workflow.transitions import expected_stage

_KNOWN_TOP_LEVEL: frozenset[str] = frozenset({"state", "agent-runs", "prompts", "approvals"})
_AGENT_RUN_SCHEMA_VERSION = "1.0"
_WORKFLOW_EVENT_SCHEMA_VERSION = "1.0"
_PROMPT_METADATA_SCHEMA_VERSION = "1.1"


class _DuplicateJsonKeyError(ValueError):
    pass


class _DuplicateYamlKeyError(ValueError):
    pass


class _SymlinkEncounteredError(OSError):
    """Raised when a no-follow open refuses a symlink, or a post-open fstat finds the
    opened descriptor is not a regular file -- i.e., the entry is (or just became, via a
    discovery-to-open race) something other than the safe regular file it was believed
    to be."""


def _parse_json_no_duplicate_keys(text: str) -> Any:
    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJsonKeyError(f"Duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    pass


def _no_duplicate_construct_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise _DuplicateYamlKeyError(f"Duplicate YAML mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_construct_mapping
)


def _parse_yaml_no_duplicate_keys(text: str) -> object:
    """Reject a duplicate key at *every* mapping level (top-level and nested) -- PyYAML's
    default ``SafeLoader`` silently applies last-key-wins, which must never be allowed to
    choose an approval family or any other field.
    """
    return yaml.load(text, Loader=_NoDuplicateKeySafeLoader)


def _digest(data: bytes) -> tuple[str, int]:
    return hashlib.sha256(data).hexdigest(), len(data)


# --- safe, no-follow file I/O (F-2, F-7) ----------------------------------------------------


def _open_regular_nofollow(path: Path) -> int:
    """Open ``path`` for reading, refusing to follow a symlink at the final path
    component, and verify the opened descriptor is a regular file. Both checks are
    performed on the actual open/opened descriptor -- never on a separate, racy
    ``lstat``/``is_symlink()`` of the path taken before the open -- so a symlink swapped
    in between an earlier directory listing and this call is still caught.
    """
    flags = os.O_RDONLY
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags |= nofollow
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if nofollow and exc.errno == errno.ELOOP:
            raise _SymlinkEncounteredError(f"{path} is a symlink (refused via O_NOFOLLOW)") from exc
        raise
    try:
        file_stat = os.fstat(fd)
    except BaseException:
        os.close(fd)
        raise
    if not stat.S_ISREG(file_stat.st_mode):
        os.close(fd)
        raise _SymlinkEncounteredError(
            f"{path} opened but is not a regular file (mode={oct(file_stat.st_mode)})"
        )
    return fd


def _read_regular_nofollow(path: Path) -> bytes:
    fd = _open_regular_nofollow(path)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _read_or_none(path: Path) -> tuple[bytes | None, str | None]:
    """Safely read ``path``. Returns ``(data, None)`` on success, or ``(None, "symlink")``
    if the entry is (or raced into becoming) a symlink/non-regular-file, or
    ``(None, "unreadable")`` for any other read failure (vanished, permission denied, ...).
    """
    try:
        return _read_regular_nofollow(path), None
    except _SymlinkEncounteredError:
        return None, "symlink"
    except OSError:
        return None, "unreadable"


def _verify_unchanged(path: Path, expected: bytes) -> bool:
    """F-9: re-read ``path`` via the same safe no-follow reader used for the original
    read, and confirm the bytes are still byte-for-byte ``expected``. Called once more,
    immediately before a family returns a ``KNOWN`` classification, so a same-path
    content mutation -- or a race into becoming a symlink, or the path vanishing --
    occurring anywhere within the read/parse/validate window is detected even though the
    directory's filename set never changed. Never follows a symlink; a mutation into one
    is reported as "changed" (``expected`` never matches ``None``), not silently ignored.
    """
    verify_data, _failure = _read_or_none(path)
    return verify_data == expected


def _safe_digest_best_effort(path: Path) -> tuple[str, int, EntryType]:
    """Best-effort digest for a record that is already being quarantined for another
    reason: attempts a safe read for an accurate SHA-256/size, and reports the entry_type
    actually observed, without ever raising or following a symlink.
    """
    data, failure = _read_or_none(path)
    if data is None:
        return "0" * 64, 0, ("symlink" if failure == "symlink" else "unreadable")
    sha256, size = _digest(data)
    return sha256, size, "file"


def _known(
    posix_rel: str, sha256: str, size: int, *, kind: str, schema_version: str
) -> LegacyArtifactRecord:
    return LegacyArtifactRecord(
        relative_path=posix_rel,
        entry_type="file",
        classification="KNOWN",
        kind=kind,  # type: ignore[arg-type]
        schema_name=kind,
        schema_version=schema_version,
        sha256=sha256,
        size_bytes=size,
        quarantine_reason=None,
        quarantine_detail="",
    )


def _quarantined(
    posix_rel: str,
    sha256: str,
    size: int,
    reason: QuarantineReason,
    detail: str,
    *,
    entry_type: EntryType = "file",
) -> LegacyArtifactRecord:
    return LegacyArtifactRecord(
        relative_path=posix_rel,
        entry_type=entry_type,
        classification="QUARANTINED",
        kind=None,
        schema_name=None,
        schema_version=None,
        sha256=sha256,
        size_bytes=size,
        quarantine_reason=reason,
        quarantine_detail=detail[:2000],
    )


# --- source-root and directory-tree discovery (F-1) -----------------------------------------


def _reject_symlink_root(source_root: Path) -> None:
    """F-1: a source root that is itself a symlink is refused outright. Its target is
    never resolved, listed, or read -- ``Path.is_symlink()`` is an ``lstat`` of the exact
    given path, performed before any ``resolve()``/``exists()``/scan of any kind.
    """
    if source_root.is_symlink():
        raise MigrationSourceError(
            f"Source root must not be a symlink (its target is never scanned): {source_root}"
        )


_EntryKind = str  # one of "file", "symlink", "unsupported"


def _iter_entries_safe(root: Path) -> Iterator[tuple[PurePosixPath, Path, _EntryKind]]:
    """Yield ``(relative_path, absolute_path, kind)`` for every entry reachable from
    ``root`` without ever following a symlink or opening a non-regular-file node. ``kind``
    is one of ``"file"``, ``"symlink"``, ``"unsupported"``. A symlinked or unsupported
    directory is yielded once, as itself, and never descended into.

    F-8: every physical entry must be represented or cause an explicit safe failure -- a
    FIFO, Unix socket, block/character device, or any other non-regular, non-directory,
    non-symlink node is yielded as ``"unsupported"`` rather than silently dropped. Its
    type is determined solely from ``os.DirEntry.stat(follow_symlinks=False)`` (a pure
    ``lstat``, cached by ``os.scandir`` on most platforms); it is never opened, so a FIFO
    can never block this scan waiting for a writer and a device node is never read.
    """
    stack: list[tuple[Path, PurePosixPath]] = [(root, PurePosixPath())]
    while stack:
        current_dir, rel_dir = stack.pop()
        try:
            entries = sorted(os.scandir(current_dir), key=lambda entry: entry.name)
        except OSError as exc:
            raise MigrationSourceError(f"Cannot list directory {current_dir}: {exc}") from exc
        for entry in entries:
            rel = rel_dir / entry.name
            abs_path = Path(entry.path)
            if entry.is_symlink():
                yield rel, abs_path, "symlink"
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append((abs_path, rel))
                continue
            if entry.is_file(follow_symlinks=False):
                yield rel, abs_path, "file"
                continue
            yield rel, abs_path, "unsupported"


def _describe_unsupported_entry(abs_path: Path) -> str:
    """A human-readable type name for an unsupported entry, derived solely from a
    no-follow ``lstat`` -- never from opening the entry.
    """
    try:
        mode = os.lstat(abs_path).st_mode
    except OSError as exc:
        return f"could not stat: {exc}"
    if stat.S_ISFIFO(mode):
        return "FIFO"
    if stat.S_ISSOCK(mode):
        return "Unix domain socket"
    if stat.S_ISBLK(mode):
        return "block device"
    if stat.S_ISCHR(mode):
        return "character device"
    return f"unknown non-regular entry (mode={oct(mode)})"


def _classify_unsupported(rel: PurePosixPath, abs_path: Path) -> LegacyArtifactRecord:
    """F-8: an unsupported filesystem node (FIFO/socket/device/...) is quarantined by
    identity alone -- it is never opened, so it has no genuine content bytes; its
    ``sha256``/``size_bytes`` are the fixed all-zero sentinel already used elsewhere in
    this module for entries with no real content (e.g. an unreadable file), which can
    never collide with a real SHA-256 digest.
    """
    description = _describe_unsupported_entry(abs_path)
    return _quarantined(
        rel.as_posix(),
        "0" * 64,
        0,
        "UNSUPPORTED_ENTRY_TYPE",
        f"unsupported filesystem entry, never opened or read: {description}",
        entry_type="unsupported",
    )


def _classify_symlink(rel: PurePosixPath, abs_path: Path) -> LegacyArtifactRecord:
    posix_rel = rel.as_posix()
    try:
        target = os.readlink(abs_path)
    except OSError as exc:
        return _quarantined(
            posix_rel, "0" * 64, 0, "FILE_UNREADABLE", str(exc), entry_type="unreadable"
        )
    target_bytes = target.encode("utf-8", "surrogateescape")
    sha256, size = _digest(target_bytes)
    return _quarantined(
        posix_rel,
        sha256,
        size,
        "SYMLINK_NOT_ALLOWED",
        f"symlink target (never followed): {target!r}",
        entry_type="symlink",
    )


def _structural_quarantine(
    rel: PurePosixPath, abs_path: Path, reason: QuarantineReason, detail: str
) -> LegacyArtifactRecord:
    sha256, size, entry_type = _safe_digest_best_effort(abs_path)
    if entry_type == "symlink":
        # A race: this entry was a regular file at listing time (it reached this
        # structural check at all) but became a symlink before this best-effort read.
        return _quarantined(
            rel.as_posix(), sha256, size, "SYMLINK_NOT_ALLOWED", detail, entry_type="symlink"
        )
    return _quarantined(rel.as_posix(), sha256, size, reason, detail, entry_type=entry_type)


# --- JSON-artifact integrity chains (F-6) ----------------------------------------------------


def _validate_workflow_event_bytes(
    data: bytes, *, expected_version: str
) -> tuple[WorkflowEvent | None, QuarantineReason | None, str]:
    if not data.endswith(b"\n") or data.count(b"\n") != 1:
        return None, "CANONICAL_FORM_MISMATCH", "must have exactly one terminal newline"
    try:
        text = data[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return None, "NOT_VALID_UTF8", str(exc)
    try:
        parsed = _parse_json_no_duplicate_keys(text)
    except _DuplicateJsonKeyError as exc:
        return None, "DUPLICATE_JSON_KEY", str(exc)
    except json.JSONDecodeError as exc:
        return None, "NOT_VALID_JSON", str(exc)
    if not isinstance(parsed, dict):
        return None, "SCHEMA_VALIDATION_FAILED", "artifact is not a JSON object"
    found_version = parsed.get("schema_version")
    if found_version is not None and found_version != expected_version:
        return (
            None,
            "UNSUPPORTED_SCHEMA_VERSION",
            f"found schema_version {found_version!r}, expected {expected_version!r}",
        )
    try:
        event = WorkflowEvent.model_validate(parsed)
    except ValidationError as exc:
        return None, "SCHEMA_VALIDATION_FAILED", str(exc)
    if canonical_json(event.model_dump(mode="json")) + b"\n" != data:
        return (
            None,
            "CANONICAL_FORM_MISMATCH",
            "stored bytes are not the canonical serialization of the event",
        )
    return event, None, ""


def _classify_workflow_history_group(
    root: Path, project_id: str, task_dir: str, members: list[tuple[PurePosixPath, Path]]
) -> list[LegacyArtifactRecord]:
    """F-6/F-7: validate one task's entire event history as a single unit. A corrupt or
    inconsistent member -- including a mid-scan directory mutation detected by re-listing
    after every member is read -- quarantines every member, never just the offending one.
    """
    dir_abs = root / "state" / project_id / task_dir
    ordered = sorted(members, key=lambda member: member[0].name)
    initial_names = [rel.name for rel, _ in ordered]

    expected_names = [f"{index:08d}.json" for index in range(1, len(ordered) + 1)]
    failure: tuple[QuarantineReason, str] | None = None
    if initial_names != expected_names:
        failure = (
            "WORKFLOW_HISTORY_INTEGRITY_FAILED",
            f"filenames are not the contiguous set {expected_names}, found {initial_names}",
        )

    events: list[WorkflowEvent] = []
    raws: list[bytes] = []
    if failure is None:
        for index, (rel, abs_path) in enumerate(ordered, start=1):
            data, read_failure = _read_or_none(abs_path)
            if data is None:
                reason: QuarantineReason = (
                    "SYMLINK_NOT_ALLOWED" if read_failure == "symlink" else "FILE_UNREADABLE"
                )
                failure = (reason, f"{rel.name}: became {read_failure} during scan")
                break
            event, reason_or_none, detail = _validate_workflow_event_bytes(
                data, expected_version=_WORKFLOW_EVENT_SCHEMA_VERSION
            )
            if event is None:
                assert reason_or_none is not None
                failure = (reason_or_none, f"{rel.name}: {detail}")
                break
            if event.project_id != project_id or task_dir_name(event.task_id) != task_dir:
                failure = (
                    "ADDRESS_MISMATCH",
                    f"{rel.name}: identity (project_id={event.project_id!r}, "
                    f"task_id={event.task_id!r}) does not match its path "
                    f"(state/{project_id}/{task_dir}/)",
                )
                break
            if event.sequence != index:
                failure = (
                    "WORKFLOW_HISTORY_INTEGRITY_FAILED",
                    f"{rel.name}: sequence {event.sequence} does not match position {index}",
                )
                break
            expected_parent = None if index == 1 else hashlib.sha256(raws[-1]).hexdigest()
            if event.parent_digest != expected_parent:
                failure = (
                    "WORKFLOW_HISTORY_INTEGRITY_FAILED",
                    f"{rel.name}: parent-digest chain is broken",
                )
                break
            if event.stage != expected_stage(events):
                failure = (
                    "WORKFLOW_HISTORY_INTEGRITY_FAILED",
                    f"{rel.name}: stage {event.stage!r} violates the transition table",
                )
                break
            events.append(event)
            raws.append(data)

    if failure is None:
        # F-7: re-list the directory after reading every member. If the name set changed
        # since the pre-read snapshot, this history may have been assembled from two
        # different filesystem epochs -- refuse to trust it rather than silently
        # returning a KNOWN result.
        try:
            final_names = sorted(
                entry.name
                for entry in os.scandir(dir_abs)
                if entry.name.endswith(".json") and not entry.is_symlink()
            )
        except OSError as exc:
            failure = (
                "SOURCE_MUTATED_DURING_SCAN",
                f"could not re-list {dir_abs} after reading: {exc}",
            )
        else:
            if final_names != initial_names:
                failure = (
                    "SOURCE_MUTATED_DURING_SCAN",
                    f"directory listing changed during scan: "
                    f"before={initial_names}, after={final_names}",
                )

    if failure is None:
        # F-9: the filename set is unchanged, but a same-path, same-filename content
        # mutation would not be caught by the listing check above. Re-read every member
        # one final time and confirm the bytes still match exactly what was used to
        # build the events above.
        for index, (rel, abs_path) in enumerate(ordered):
            if not _verify_unchanged(abs_path, raws[index]):
                failure = (
                    "SOURCE_MUTATED_DURING_SCAN",
                    f"{rel.name}: content changed during scan",
                )
                break

    if failure is not None:
        reason, detail = failure
        records: list[LegacyArtifactRecord] = []
        for index, (rel, abs_path) in enumerate(ordered):
            if index < len(raws):
                sha256, size = _digest(raws[index])
                entry_type: EntryType = "file"
            else:
                sha256, size, entry_type = _safe_digest_best_effort(abs_path)
            actual_reason = "SYMLINK_NOT_ALLOWED" if entry_type == "symlink" else reason
            records.append(
                _quarantined(
                    rel.as_posix(), sha256, size, actual_reason, detail, entry_type=entry_type
                )
            )
        return records

    return [
        _known(
            rel.as_posix(),
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            kind="workflow-event",
            schema_version="1.0",
        )
        for (rel, _abs_path), raw in zip(ordered, raws, strict=True)
    ]


def _classify_state_files(
    root: Path, files: list[tuple[PurePosixPath, Path]]
) -> list[LegacyArtifactRecord]:
    groups: dict[tuple[str, str], list[tuple[PurePosixPath, Path]]] = {}
    standalone: list[LegacyArtifactRecord] = []
    for rel, abs_path in files:
        parts = rel.parts
        if len(parts) != 4:
            standalone.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNEXPECTED_PATH_STRUCTURE",
                    f"expected state/<project>/<task_dir>/<file>.json, got {rel.as_posix()!r}",
                )
            )
            continue
        if rel.suffix != ".json":
            standalone.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNKNOWN_FILE_EXTENSION",
                    f"unexpected extension {rel.suffix!r} under state/",
                )
            )
            continue
        _, project_id, task_dir, _ = parts
        groups.setdefault((project_id, task_dir), []).append((rel, abs_path))

    records = list(standalone)
    for (project_id, task_dir), members in sorted(groups.items()):
        records.extend(_classify_workflow_history_group(root, project_id, task_dir, members))
    return records


def _validate_agent_run_bytes(
    data: bytes, *, project_id: str, task_dir: str, stage: str, run_id_from_path: str
) -> tuple[AgentRunRecord | None, QuarantineReason | None, str]:
    if not data.endswith(b"\n") or data.count(b"\n") != 1:
        return None, "CANONICAL_FORM_MISMATCH", "must have exactly one terminal newline"
    try:
        text = data[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return None, "NOT_VALID_UTF8", str(exc)
    try:
        parsed = _parse_json_no_duplicate_keys(text)
    except _DuplicateJsonKeyError as exc:
        return None, "DUPLICATE_JSON_KEY", str(exc)
    except json.JSONDecodeError as exc:
        return None, "NOT_VALID_JSON", str(exc)
    if not isinstance(parsed, dict):
        return None, "SCHEMA_VALIDATION_FAILED", "artifact is not a JSON object"
    found_version = parsed.get("schema_version")
    if found_version is not None and found_version != _AGENT_RUN_SCHEMA_VERSION:
        return (
            None,
            "UNSUPPORTED_SCHEMA_VERSION",
            f"found schema_version {found_version!r}, expected {_AGENT_RUN_SCHEMA_VERSION!r}",
        )
    try:
        record = AgentRunRecord.model_validate(parsed)
    except ValidationError as exc:
        return None, "SCHEMA_VALIDATION_FAILED", str(exc)
    if canonical_json(record.model_dump(mode="json")) + b"\n" != data:
        return (
            None,
            "CANONICAL_FORM_MISMATCH",
            "stored bytes are not the canonical serialization of the record",
        )
    if compute_run_id(record) != record.run_id:
        return None, "CONTENT_HASH_MISMATCH", "run_id does not match the record's own content hash"
    if (
        record.run_id != run_id_from_path
        or record.project_id != project_id
        or record.stage != stage
        or task_dir_name(record.task_id) != task_dir
    ):
        return (
            None,
            "ADDRESS_MISMATCH",
            f"record identity (run_id={record.run_id!r}, project_id={record.project_id!r}, "
            f"stage={record.stage!r}, task_id={record.task_id!r}) does not match its path "
            f"(agent-runs/{project_id}/{task_dir}/{stage}/{run_id_from_path}.json)",
        )
    try:
        stdout_bytes = base64.b64decode(record.stdout_b64, validate=True)
        stderr_bytes = base64.b64decode(record.stderr_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        return None, "CONTENT_HASH_MISMATCH", f"invalid base64 in stdout_b64/stderr_b64: {exc}"
    if hashlib.sha256(stdout_bytes).hexdigest() != record.stdout_sha256:
        return None, "CONTENT_HASH_MISMATCH", "stdout_sha256 does not match the decoded stdout_b64"
    if hashlib.sha256(stderr_bytes).hexdigest() != record.stderr_sha256:
        return None, "CONTENT_HASH_MISMATCH", "stderr_sha256 does not match the decoded stderr_b64"
    return record, None, ""


def _classify_agent_run_pair(
    root: Path,
    dir_rel: PurePosixPath,
    json_entry: tuple[PurePosixPath, Path] | None,
    patch_entry: tuple[PurePosixPath, Path] | None,
    *,
    companion_is_symlink: bool = False,
) -> list[LegacyArtifactRecord]:
    _, project_id, task_dir, stage = dir_rel.parts

    if json_entry is None:
        assert patch_entry is not None
        patch_rel, patch_abs = patch_entry
        sha256, size, entry_type = _safe_digest_best_effort(patch_abs)
        if entry_type != "file":
            return [
                _quarantined(
                    patch_rel.as_posix(),
                    sha256,
                    size,
                    "SYMLINK_NOT_ALLOWED",
                    "raced into a symlink",
                    entry_type=entry_type,
                )
            ]
        return [
            _quarantined(
                patch_rel.as_posix(),
                sha256,
                size,
                "ORPHAN_COMPANION_FILE",
                "agent-run .patch has no sibling .json record",
            )
        ]

    json_rel, json_abs = json_entry
    json_data, json_failure = _read_or_none(json_abs)
    if json_data is None:
        reason: QuarantineReason = (
            "SYMLINK_NOT_ALLOWED" if json_failure == "symlink" else "FILE_UNREADABLE"
        )
        json_entry_type: EntryType = "symlink" if json_failure == "symlink" else "unreadable"
        records = [
            _quarantined(
                json_rel.as_posix(),
                "0" * 64,
                0,
                reason,
                f"became {json_failure} during scan",
                entry_type=json_entry_type,
            )
        ]
        if patch_entry is not None:
            patch_rel, patch_abs = patch_entry
            psha, psize, pentry = _safe_digest_best_effort(patch_abs)
            records.append(
                _quarantined(
                    patch_rel.as_posix(),
                    psha,
                    psize,
                    "PRIMARY_INVALID",
                    f"primary {json_rel.as_posix()} became unreadable",
                    entry_type=pentry if pentry != "file" else "file",
                )
            )
        return records

    record, invalid_reason, invalid_detail = _validate_agent_run_bytes(
        json_data,
        project_id=project_id,
        task_dir=task_dir,
        stage=stage,
        run_id_from_path=json_rel.stem,
    )
    json_sha256, json_size = _digest(json_data)

    if record is None:
        assert invalid_reason is not None
        records = [
            _quarantined(
                json_rel.as_posix(), json_sha256, json_size, invalid_reason, invalid_detail
            )
        ]
        if patch_entry is not None:
            patch_rel, patch_abs = patch_entry
            psha, psize, pentry = _safe_digest_best_effort(patch_abs)
            if pentry == "symlink":
                records.append(
                    _quarantined(
                        patch_rel.as_posix(),
                        psha,
                        psize,
                        "COMPANION_SYMLINK_NOT_ALLOWED",
                        "companion is a symlink; primary is also invalid",
                        entry_type="symlink",
                    )
                )
            else:
                records.append(
                    _quarantined(
                        patch_rel.as_posix(),
                        psha,
                        psize,
                        "PRIMARY_INVALID",
                        f"primary {json_rel.as_posix()} failed validation: {invalid_reason}",
                        entry_type=pentry,
                    )
                )
        return records

    if patch_entry is None:
        if companion_is_symlink:
            return [
                _quarantined(
                    json_rel.as_posix(),
                    json_sha256,
                    json_size,
                    "COMPANION_SYMLINK_NOT_ALLOWED",
                    "companion .patch is a symlink; its target was never read",
                )
            ]
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "MISSING_COMPANION_MEMBER",
                "missing companion .patch",
            )
        ]

    patch_rel, patch_abs = patch_entry
    patch_data, patch_failure = _read_or_none(patch_abs)
    if patch_failure == "symlink":
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "COMPANION_SYMLINK_NOT_ALLOWED",
                "companion .patch is a symlink; its target was never read",
            ),
            _quarantined(
                patch_rel.as_posix(),
                "0" * 64,
                0,
                "SYMLINK_NOT_ALLOWED",
                "companion is a symlink (never followed)",
                entry_type="symlink",
            ),
        ]
    if patch_data is None:
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "MISSING_COMPANION_MEMBER",
                "companion .patch became unreadable during scan",
            ),
            _quarantined(
                patch_rel.as_posix(),
                "0" * 64,
                0,
                "FILE_UNREADABLE",
                "became unreadable during scan",
                entry_type="unreadable",
            ),
        ]
    if hashlib.sha256(patch_data).hexdigest() != record.patch_sha256:
        patch_sha256, patch_size = _digest(patch_data)
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "COMPANION_DIGEST_MISMATCH",
                "companion .patch bytes do not match patch_sha256",
            ),
            _quarantined(
                patch_rel.as_posix(),
                patch_sha256,
                patch_size,
                "COMPANION_DIGEST_MISMATCH",
                "does not match the primary record's patch_sha256",
            ),
        ]

    patch_sha256, patch_size = _digest(patch_data)
    if not _verify_unchanged(json_abs, json_data) or not _verify_unchanged(patch_abs, patch_data):
        # F-9: a same-path content mutation during the validation window above -- caught
        # even though neither filename changed and both reads individually succeeded.
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "SOURCE_MUTATED_DURING_SCAN",
                "content changed during scan",
            ),
            _quarantined(
                patch_rel.as_posix(),
                patch_sha256,
                patch_size,
                "SOURCE_MUTATED_DURING_SCAN",
                "content changed during scan",
            ),
        ]
    return [
        _known(
            json_rel.as_posix(),
            json_sha256,
            json_size,
            kind="agent-run-record",
            schema_version="1.0",
        ),
        _known(
            patch_rel.as_posix(),
            patch_sha256,
            patch_size,
            kind="agent-run-patch",
            schema_version="1.0",
        ),
    ]


def _classify_agent_run_files(
    root: Path,
    files: list[tuple[PurePosixPath, Path]],
    symlinked_paths: frozenset[PurePosixPath],
) -> list[LegacyArtifactRecord]:
    json_by_dir: dict[PurePosixPath, dict[str, tuple[PurePosixPath, Path]]] = {}
    patch_by_dir: dict[PurePosixPath, dict[str, tuple[PurePosixPath, Path]]] = {}
    standalone: list[LegacyArtifactRecord] = []
    for rel, abs_path in files:
        parts = rel.parts
        if len(parts) != 5:
            standalone.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNEXPECTED_PATH_STRUCTURE",
                    f"expected agent-runs/<project>/<task_dir>/<stage>/<run_id>.json, "
                    f"got {rel.as_posix()!r}",
                )
            )
            continue
        if rel.suffix == ".json":
            json_by_dir.setdefault(rel.parent, {})[rel.stem] = (rel, abs_path)
        elif rel.suffix == ".patch":
            patch_by_dir.setdefault(rel.parent, {})[rel.stem] = (rel, abs_path)
        else:
            standalone.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNKNOWN_FILE_EXTENSION",
                    f"unexpected extension {rel.suffix!r} under agent-runs/",
                )
            )

    records = list(standalone)
    for dir_rel in sorted(set(json_by_dir) | set(patch_by_dir), key=lambda p: p.as_posix()):
        json_map = json_by_dir.get(dir_rel, {})
        patch_map = patch_by_dir.get(dir_rel, {})
        for stem in sorted(set(json_map) | set(patch_map)):
            companion_is_symlink = (dir_rel / f"{stem}.patch") in symlinked_paths
            records.extend(
                _classify_agent_run_pair(
                    root,
                    dir_rel,
                    json_map.get(stem),
                    patch_map.get(stem),
                    companion_is_symlink=companion_is_symlink,
                )
            )
    return records


def _validate_prompt_metadata_bytes(
    data: bytes, *, project_id: str, stage: str, prompt_id_from_path: str
) -> tuple[PromptMetadata | None, Any, QuarantineReason | None, str]:
    if not data.endswith(b"\n") or data.count(b"\n") != 1:
        return None, None, "CANONICAL_FORM_MISMATCH", "must have exactly one terminal newline"
    try:
        text = data[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return None, None, "NOT_VALID_UTF8", str(exc)
    try:
        parsed = _parse_json_no_duplicate_keys(text)
    except _DuplicateJsonKeyError as exc:
        return None, None, "DUPLICATE_JSON_KEY", str(exc)
    except json.JSONDecodeError as exc:
        return None, None, "NOT_VALID_JSON", str(exc)
    if not isinstance(parsed, dict):
        return None, None, "SCHEMA_VALIDATION_FAILED", "artifact is not a JSON object"
    found_version = parsed.get("schema_version")
    if found_version is not None and found_version != _PROMPT_METADATA_SCHEMA_VERSION:
        return (
            None,
            None,
            "UNSUPPORTED_SCHEMA_VERSION",
            f"found schema_version {found_version!r}, expected {_PROMPT_METADATA_SCHEMA_VERSION!r}",
        )
    try:
        metadata = PromptMetadata.model_validate(parsed)
    except ValidationError as exc:
        return None, None, "SCHEMA_VALIDATION_FAILED", str(exc)
    if (
        metadata.project_id != project_id
        or metadata.stage != stage
        or metadata.prompt_id != prompt_id_from_path
    ):
        return (
            None,
            None,
            "ADDRESS_MISMATCH",
            f"metadata identity (project_id={metadata.project_id!r}, stage={metadata.stage!r}, "
            f"prompt_id={metadata.prompt_id!r}) does not match its path "
            f"(prompts/{project_id}/{stage}/{prompt_id_from_path}.json)",
        )
    try:
        rendered = render_prompt(metadata.payload)
    except TemplateRenderError as exc:
        return None, None, "CANONICAL_FORM_MISMATCH", f"deterministic re-render failed: {exc}"
    if rendered.metadata != metadata:
        return (
            None,
            None,
            "CANONICAL_FORM_MISMATCH",
            "recomputed metadata does not match the stored metadata",
        )
    if rendered.metadata_bytes != data:
        return (
            None,
            None,
            "CANONICAL_FORM_MISMATCH",
            "stored bytes are not the canonical serialization of the metadata",
        )
    if rendered.prompt_id != prompt_id_from_path:
        return None, None, "CONTENT_HASH_MISMATCH", "recomputed prompt_id does not match its path"
    return metadata, rendered, None, ""


def _classify_prompt_pair(
    root: Path,
    dir_rel: PurePosixPath,
    json_entry: tuple[PurePosixPath, Path] | None,
    md_entry: tuple[PurePosixPath, Path] | None,
    *,
    companion_is_symlink: bool = False,
) -> list[LegacyArtifactRecord]:
    _, project_id, stage = dir_rel.parts

    if json_entry is None:
        assert md_entry is not None
        md_rel, md_abs = md_entry
        sha256, size, entry_type = _safe_digest_best_effort(md_abs)
        if entry_type != "file":
            return [
                _quarantined(
                    md_rel.as_posix(),
                    sha256,
                    size,
                    "SYMLINK_NOT_ALLOWED",
                    "raced into a symlink",
                    entry_type=entry_type,
                )
            ]
        return [
            _quarantined(
                md_rel.as_posix(),
                sha256,
                size,
                "ORPHAN_COMPANION_FILE",
                "prompt .md has no sibling .json record",
            )
        ]

    json_rel, json_abs = json_entry
    json_data, json_failure = _read_or_none(json_abs)
    if json_data is None:
        reason: QuarantineReason = (
            "SYMLINK_NOT_ALLOWED" if json_failure == "symlink" else "FILE_UNREADABLE"
        )
        json_entry_type: EntryType = "symlink" if json_failure == "symlink" else "unreadable"
        records = [
            _quarantined(
                json_rel.as_posix(),
                "0" * 64,
                0,
                reason,
                f"became {json_failure} during scan",
                entry_type=json_entry_type,
            )
        ]
        if md_entry is not None:
            md_rel, md_abs = md_entry
            msha, msize, mentry = _safe_digest_best_effort(md_abs)
            records.append(
                _quarantined(
                    md_rel.as_posix(),
                    msha,
                    msize,
                    "PRIMARY_INVALID",
                    f"primary {json_rel.as_posix()} became unreadable",
                    entry_type=mentry,
                )
            )
        return records

    metadata, rendered, invalid_reason, invalid_detail = _validate_prompt_metadata_bytes(
        json_data, project_id=project_id, stage=stage, prompt_id_from_path=json_rel.stem
    )
    json_sha256, json_size = _digest(json_data)

    if metadata is None:
        assert invalid_reason is not None
        records = [
            _quarantined(
                json_rel.as_posix(), json_sha256, json_size, invalid_reason, invalid_detail
            )
        ]
        if md_entry is not None:
            md_rel, md_abs = md_entry
            msha, msize, mentry = _safe_digest_best_effort(md_abs)
            if mentry == "symlink":
                records.append(
                    _quarantined(
                        md_rel.as_posix(),
                        msha,
                        msize,
                        "COMPANION_SYMLINK_NOT_ALLOWED",
                        "companion is a symlink; primary is also invalid",
                        entry_type="symlink",
                    )
                )
            else:
                records.append(
                    _quarantined(
                        md_rel.as_posix(),
                        msha,
                        msize,
                        "PRIMARY_INVALID",
                        f"primary {json_rel.as_posix()} failed validation: {invalid_reason}",
                        entry_type=mentry,
                    )
                )
        return records

    if md_entry is None:
        if companion_is_symlink:
            return [
                _quarantined(
                    json_rel.as_posix(),
                    json_sha256,
                    json_size,
                    "COMPANION_SYMLINK_NOT_ALLOWED",
                    "companion .md is a symlink; its target was never read",
                )
            ]
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "MISSING_COMPANION_MEMBER",
                "missing companion .md",
            )
        ]

    md_rel, md_abs = md_entry
    md_data, md_failure = _read_or_none(md_abs)
    if md_failure == "symlink":
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "COMPANION_SYMLINK_NOT_ALLOWED",
                "companion .md is a symlink; its target was never read",
            ),
            _quarantined(
                md_rel.as_posix(),
                "0" * 64,
                0,
                "SYMLINK_NOT_ALLOWED",
                "companion is a symlink (never followed)",
                entry_type="symlink",
            ),
        ]
    if md_data is None:
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "MISSING_COMPANION_MEMBER",
                "companion .md became unreadable during scan",
            ),
            _quarantined(
                md_rel.as_posix(),
                "0" * 64,
                0,
                "FILE_UNREADABLE",
                "became unreadable during scan",
                entry_type="unreadable",
            ),
        ]
    assert rendered is not None
    if (
        md_data != rendered.markdown.encode("utf-8", errors="strict")
        or hashlib.sha256(md_data).hexdigest() != metadata.markdown_sha256
    ):
        md_sha256, md_size = _digest(md_data)
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "COMPANION_DIGEST_MISMATCH",
                "companion .md does not equal the deterministic rendering / markdown_sha256",
            ),
            _quarantined(
                md_rel.as_posix(),
                md_sha256,
                md_size,
                "COMPANION_DIGEST_MISMATCH",
                "does not equal the primary's deterministic rendering / markdown_sha256",
            ),
        ]

    md_sha256, md_size = _digest(md_data)
    if not _verify_unchanged(json_abs, json_data) or not _verify_unchanged(md_abs, md_data):
        # F-9: a same-path content mutation during the validation window above -- caught
        # even though neither filename changed and both reads individually succeeded.
        return [
            _quarantined(
                json_rel.as_posix(),
                json_sha256,
                json_size,
                "SOURCE_MUTATED_DURING_SCAN",
                "content changed during scan",
            ),
            _quarantined(
                md_rel.as_posix(),
                md_sha256,
                md_size,
                "SOURCE_MUTATED_DURING_SCAN",
                "content changed during scan",
            ),
        ]
    return [
        _known(
            json_rel.as_posix(),
            json_sha256,
            json_size,
            kind="prompt-metadata",
            schema_version="1.1",
        ),
        _known(md_rel.as_posix(), md_sha256, md_size, kind="prompt-markdown", schema_version="1.1"),
    ]


def _classify_prompt_files(
    root: Path,
    files: list[tuple[PurePosixPath, Path]],
    symlinked_paths: frozenset[PurePosixPath],
) -> list[LegacyArtifactRecord]:
    json_by_dir: dict[PurePosixPath, dict[str, tuple[PurePosixPath, Path]]] = {}
    md_by_dir: dict[PurePosixPath, dict[str, tuple[PurePosixPath, Path]]] = {}
    standalone: list[LegacyArtifactRecord] = []
    for rel, abs_path in files:
        parts = rel.parts
        if len(parts) != 4:
            standalone.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNEXPECTED_PATH_STRUCTURE",
                    f"expected prompts/<project>/<stage>/<prompt_id>.json, got {rel.as_posix()!r}",
                )
            )
            continue
        if rel.suffix == ".json":
            json_by_dir.setdefault(rel.parent, {})[rel.stem] = (rel, abs_path)
        elif rel.suffix == ".md":
            md_by_dir.setdefault(rel.parent, {})[rel.stem] = (rel, abs_path)
        else:
            standalone.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNKNOWN_FILE_EXTENSION",
                    f"unexpected extension {rel.suffix!r} under prompts/",
                )
            )

    records = list(standalone)
    for dir_rel in sorted(set(json_by_dir) | set(md_by_dir), key=lambda p: p.as_posix()):
        json_map = json_by_dir.get(dir_rel, {})
        md_map = md_by_dir.get(dir_rel, {})
        for stem in sorted(set(json_map) | set(md_map)):
            companion_is_symlink = (dir_rel / f"{stem}.md") in symlinked_paths
            records.extend(
                _classify_prompt_pair(
                    root,
                    dir_rel,
                    json_map.get(stem),
                    md_map.get(stem),
                    companion_is_symlink=companion_is_symlink,
                )
            )
    return records


# --- approvals (F-3) --------------------------------------------------------------------------


def _classify_approval_entry(rel: PurePosixPath, abs_path: Path) -> LegacyArtifactRecord:
    posix_rel = rel.as_posix()
    data, failure = _read_or_none(abs_path)
    if data is None:
        reason: QuarantineReason = (
            "SYMLINK_NOT_ALLOWED" if failure == "symlink" else "FILE_UNREADABLE"
        )
        entry_type: EntryType = "symlink" if failure == "symlink" else "unreadable"
        return _quarantined(
            posix_rel, "0" * 64, 0, reason, f"became {failure} during scan", entry_type=entry_type
        )
    sha256, size = _digest(data)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return _quarantined(posix_rel, sha256, size, "NOT_VALID_UTF8", str(exc))
    try:
        raw = _parse_yaml_no_duplicate_keys(text)
    except _DuplicateYamlKeyError as exc:
        return _quarantined(posix_rel, sha256, size, "DUPLICATE_YAML_KEY", str(exc))
    except yaml.YAMLError as exc:
        return _quarantined(posix_rel, sha256, size, "NOT_VALID_YAML", str(exc))
    if not isinstance(raw, dict):
        return _quarantined(
            posix_rel, sha256, size, "SCHEMA_VALIDATION_FAILED", "artifact is not a YAML mapping"
        )
    kind_field = raw.get("kind")
    model_cls: type[CommitApproval] | type[PushApproval]
    if kind_field == "commit":
        model_cls, kind, schema_version = CommitApproval, "commit-approval", "1.x"
    elif kind_field == "push":
        model_cls, kind, schema_version = PushApproval, "push-approval", "1.x"
    else:
        # Never guess which approval family an unlabelled/foreign file belongs to; the
        # duplicate-free parse above guarantees this `kind` was never chosen by
        # last-key-wins behavior.
        return _quarantined(
            posix_rel, sha256, size, "UNKNOWN_APPROVAL_KIND", f"kind={kind_field!r}"
        )
    try:
        model_cls.model_validate(raw)
    except ValidationError as exc:
        return _quarantined(posix_rel, sha256, size, "SCHEMA_VALIDATION_FAILED", str(exc))
    if not _verify_unchanged(abs_path, data):  # F-9: final same-path mutation check
        return _quarantined(
            posix_rel, sha256, size, "SOURCE_MUTATED_DURING_SCAN", "content changed during scan"
        )
    return _known(posix_rel, sha256, size, kind=kind, schema_version=schema_version)


# --- top-level orchestration ------------------------------------------------------------------


def discover_legacy_artifacts(source_root: Path) -> list[LegacyArtifactRecord]:
    """Read-only: classify every entry under ``source_root``. Never writes; never follows
    a symlink anywhere (including the root itself); deterministic (sorted by
    ``relative_path``) for a fixed filesystem state.
    """
    _reject_symlink_root(source_root)  # F-1, before any resolve/exists/scan
    resolved_root = source_root.resolve(strict=False)
    if not resolved_root.exists():
        # A source root that has simply never been created yet (e.g. a fresh machine
        # that has never produced a legacy artifact) is a legitimate empty state, not a
        # corruption signal -- unlike a path that exists but is not a directory, below.
        return []
    if not resolved_root.is_dir():
        raise MigrationSourceError(f"Source root exists but is not a directory: {source_root}")

    entries = list(_iter_entries_safe(resolved_root))

    records: list[LegacyArtifactRecord] = []
    state_files: list[tuple[PurePosixPath, Path]] = []
    agent_run_files: list[tuple[PurePosixPath, Path]] = []
    prompt_files: list[tuple[PurePosixPath, Path]] = []
    approval_files: list[tuple[PurePosixPath, Path]] = []
    symlinked_paths: set[PurePosixPath] = set()

    for rel, abs_path, kind in entries:
        if kind == "symlink":
            records.append(_classify_symlink(rel, abs_path))
            symlinked_paths.add(rel)
            continue
        if kind == "unsupported":
            records.append(_classify_unsupported(rel, abs_path))
            continue
        top = rel.parts[0] if rel.parts else ""
        if top not in _KNOWN_TOP_LEVEL:
            records.append(
                _structural_quarantine(
                    rel,
                    abs_path,
                    "UNKNOWN_TOP_LEVEL_DIRECTORY",
                    f"unrecognized top-level directory {top!r}",
                )
            )
        elif top == "state":
            state_files.append((rel, abs_path))
        elif top == "agent-runs":
            agent_run_files.append((rel, abs_path))
        elif top == "prompts":
            prompt_files.append((rel, abs_path))
        else:  # top == "approvals"
            approval_files.append((rel, abs_path))

    frozen_symlinked_paths = frozenset(symlinked_paths)
    records.extend(_classify_state_files(resolved_root, state_files))
    records.extend(
        _classify_agent_run_files(resolved_root, agent_run_files, frozen_symlinked_paths)
    )
    records.extend(_classify_prompt_files(resolved_root, prompt_files, frozen_symlinked_paths))
    for rel, abs_path in approval_files:
        records.append(_classify_approval_entry(rel, abs_path))

    records.sort(key=lambda record: record.relative_path)
    return records
