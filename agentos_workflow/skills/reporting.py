"""Reporting Skills (`SKILL_CONTRACTS.md` §6).

These are the only Skills in this stage that write files. Every write is confined to the
configured audit directory by the same descriptor-relative `O_NOFOLLOW` discipline AUTO-002
established for state and audit records (DD-21/DD-22/DD-29): each path component is validated as
a single safe component before it is used, every directory is opened relative to the previous
descriptor, and a symlink anywhere on the walk aborts the write. A caller-supplied identifier can
therefore never redirect a report outside the audit root, even if the audit root itself sits
inside a directory an attacker can create symlinks in.

Report generation is idempotent through a content hash (`SKILL_CONTRACTS.md` §6): writing the
same content twice is a no-op, and writing *different* content to an existing report is refused
rather than silently overwriting a record another workflow may already have referenced.

A single workflow legitimately produces several genuinely different reports of the same kind —
the bounded repair loop (`FAILURE_RECOVERY.md` §1) runs one implementation attempt and one QA
round per repair, each with its own verdict, findings, and diff. Each generator therefore takes
an optional `sequence`, which names the artifact `<kind>.<sequence>.json` inside that workflow's
own directory instead of the single `<kind>.json`. The refusal above is deliberately kept
per-artifact: two different reports of the same kind and sequence still collide, because that
means the caller reused a sequence number, not that the audit model needs relaxing.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentos_workflow.skills import (
    FailureKind,
    RetryClassification,
    SkillResult,
    failure,
    redact_secrets,
    success,
    utc_now,
)

__all__ = [
    "AuditAppendResult",
    "PersistedReport",
    "ReportArtifact",
    "append_audit_event",
    "generate_closeout_report",
    "generate_failure_report",
    "generate_qa_report",
    "generate_stage_report",
    "read_reports",
    "write_sanitized_output",
]

_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_AUDIT_LOG_NAME = "audit.jsonl"
# Well above any bound the workflow itself imposes (the repair loop stops at 3 attempts,
# `FAILURE_RECOVERY.md` §1) and low enough that the sequence can never dominate the filename.
_MAX_REPORT_SEQUENCE = 9999


@dataclass(frozen=True)
class ReportArtifact:
    path: Path
    sha256: str
    size_bytes: int
    already_present: bool


@dataclass(frozen=True)
class PersistedReport:
    """One already-written report artifact, read back exactly as it sits on disk (AUTO-009).

    Deliberately not a `ReportArtifact`: that type carries `already_present`, which answers a
    question only a *write* can ask. Reading is not a degenerate write, and giving a read result a
    field about idempotent re-generation would invite exactly the confusion this surface exists to
    prevent — nothing on this path generates, regenerates, or rewrites a report.
    """

    report_kind: str
    sequence: int | None
    path: Path
    sha256: str
    size_bytes: int
    content: dict[str, Any]


@dataclass(frozen=True)
class AuditAppendResult:
    event_id: str
    appended: bool
    path: Path


def _validate_component(skill: str, field: str, value: str) -> SkillResult[Any] | None:
    """Reject anything that is not a single safe path component.

    Enforced before the value is joined to a path at all, so `../` and an absolute path are
    rejected as malformed identifiers rather than normalized into a traversal. The leading
    character class also excludes `.` and `-`, which keeps a component from becoming a dotfile
    or being read as an option by anything downstream.
    """
    if not _COMPONENT_RE.fullmatch(value):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"{field}={value!r} is not a safe single path component",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


def _validate_sequence(skill: str, sequence: int | None) -> SkillResult[Any] | None:
    """Reject anything that is not a small positive integer.

    The sequence is a validated integer rather than a caller-supplied string precisely so that it
    cannot widen what may end up in a filename: everything `_validate_component` refuses for an
    identifier is unreachable here by construction. `bool` is excluded explicitly because it is a
    subclass of `int` and would otherwise name an artifact `qa.True.json`.
    """
    if sequence is None:
        return None
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"sequence={sequence!r} is not an integer",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if not 1 <= sequence <= _MAX_REPORT_SEQUENCE:
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"sequence={sequence!r} is outside 1..{_MAX_REPORT_SEQUENCE}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


def _open_confined_directory(
    skill: str,
    audit_root: Path,
    components: tuple[str, ...],
    *,
    create: bool,
    missing_ok: bool = False,
) -> tuple[int | None, SkillResult[Any] | None]:
    """Walk `components` below `audit_root`, one `O_NOFOLLOW` descriptor at a time.

    Returns an open directory descriptor the caller must close. Opening each component relative
    to the previous descriptor — rather than resolving a joined path once — is what makes the
    walk resistant to a component being swapped for a symlink *between* the check and the open.

    `missing_ok` (AUTO-009, read paths only) separates "this directory does not exist" from
    "this directory exists but is unsafe", which the single `IO_ERROR` below otherwise conflates.
    A writer never needs the distinction because it creates what is missing; a *reader* does,
    because "no reports have been written yet" is an ordinary empty result while a symlinked
    component on the same walk is still a hard refusal. It returns `(None, None)` — no descriptor
    and no failure — for the absent case only, and never suppresses any other error.
    """
    try:
        current_fd = os.open(audit_root, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError as exc:
        if missing_ok:
            return None, None
        return None, failure(skill, FailureKind.IO_ERROR, f"audit root unusable: {exc}")
    except OSError as exc:
        return None, failure(skill, FailureKind.IO_ERROR, f"audit root unusable: {exc}")
    for component in components:
        try:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
            next_fd = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current_fd
            )
        except FileNotFoundError as exc:
            os.close(current_fd)
            if missing_ok:
                return None, None
            return None, failure(
                skill,
                FailureKind.IO_ERROR,
                f"unsafe or missing audit directory component {component!r}: {exc}",
            )
        except OSError as exc:
            os.close(current_fd)
            return None, failure(
                skill,
                FailureKind.IO_ERROR,
                f"unsafe or missing audit directory component {component!r}: {exc}",
            )
        os.close(current_fd)
        current_fd = next_fd
    return current_fd, None


def _write_confined_file(
    skill: str,
    *,
    audit_root: Path,
    components: tuple[str, ...],
    filename: str,
    payload: bytes,
) -> SkillResult[ReportArtifact]:
    """Write one file inside the audit root, idempotently and without following a symlink."""
    directory_fd, error = _open_confined_directory(skill, audit_root, components, create=True)
    if error is not None or directory_fd is None:
        return error if error is not None else failure(skill, FailureKind.IO_ERROR, "audit root")
    digest = sha256(payload).hexdigest()
    try:
        try:
            existing_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            existing_fd = None
        except OSError as exc:
            return failure(
                skill, FailureKind.IO_ERROR, f"existing report {filename!r} is unsafe: {exc}"
            )
        if existing_fd is not None:
            try:
                status = os.fstat(existing_fd)
                if not stat.S_ISREG(status.st_mode):
                    return failure(
                        skill,
                        FailureKind.IO_ERROR,
                        f"{filename!r} exists and is not a regular file",
                    )
                chunks: list[bytes] = []
                while chunk := os.read(existing_fd, 65536):
                    chunks.append(chunk)
                existing = b"".join(chunks)
            finally:
                os.close(existing_fd)
            if sha256(existing).hexdigest() == digest:
                # Idempotent re-generation: identical content is a no-op success.
                return success(
                    ReportArtifact(
                        path=audit_root.joinpath(*components, filename),
                        sha256=digest,
                        size_bytes=len(payload),
                        already_present=True,
                    )
                )
            return failure(
                skill,
                FailureKind.PRECONDITION,
                f"{filename!r} already exists with different content; refusing to overwrite a "
                "report another workflow may already reference",
                retry_classification=RetryClassification.NON_RETRYABLE,
            )
        try:
            # `O_EXCL` closes the race between the existence check above and this create.
            fd = os.open(
                filename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            return failure(skill, FailureKind.IO_ERROR, f"could not create {filename!r}: {exc}")
        try:
            os.write(fd, payload)
            # Durability before the caller is told the artifact exists: a report referenced by an
            # audit record must survive a crash that happens immediately after.
            os.fsync(fd)
        except OSError as exc:
            return failure(skill, FailureKind.IO_ERROR, f"could not write {filename!r}: {exc}")
        finally:
            os.close(fd)
        try:
            os.fsync(directory_fd)
        except OSError:
            # The file itself is already durable; a directory fsync failure is not worth
            # failing the report over on filesystems that do not support it.
            pass
        return success(
            ReportArtifact(
                path=audit_root.joinpath(*components, filename),
                sha256=digest,
                size_bytes=len(payload),
                already_present=False,
            )
        )
    finally:
        os.close(directory_fd)


def _serialize(payload: dict[str, Any]) -> bytes:
    """Canonical JSON: sorted keys, no incidental whitespace, redacted values.

    Sorted keys make the content hash stable across runs, which is what makes the idempotency
    check above meaningful rather than accidental.
    """
    return (
        json.dumps(_redact_payload(payload), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _redact_payload(value: Any) -> Any:
    """Redact every string in a report before it is serialized.

    Applied to the whole structure rather than to named fields: a report is assembled from
    command output and model text, and enumerating which fields *might* carry a secret would be
    a list that goes stale the first time a field is added.
    """
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {key: _redact_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_payload(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _generate_report(
    skill: str,
    *,
    audit_root: Path,
    workflow_id: str,
    report_kind: str,
    payload: dict[str, Any],
    sequence: int | None = None,
) -> SkillResult[ReportArtifact]:
    for field, value in (("workflow_id", workflow_id), ("report_kind", report_kind)):
        if problem := _validate_component(skill, field, value):
            return problem
    if problem := _validate_sequence(skill, sequence):
        return problem
    if not audit_root.is_absolute():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            "audit_root must be an absolute path",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    document = dict(payload)
    document.setdefault("report_kind", report_kind)
    document.setdefault("workflow_id", workflow_id)
    if sequence is not None:
        # Recorded in the artifact as well as in its name, so a report read on its own still
        # says which round of the repair loop produced it.
        document.setdefault("report_sequence", sequence)
    document.setdefault("generated_at", utc_now().isoformat())
    return _write_confined_file(
        skill,
        audit_root=audit_root,
        components=(workflow_id, "reports"),
        filename=f"{report_kind}.json" if sequence is None else f"{report_kind}.{sequence}.json",
        payload=_serialize(document),
    )


def generate_stage_report(
    *,
    audit_root: Path,
    workflow_id: str,
    results: dict[str, Any],
    sequence: int | None = None,
) -> SkillResult[ReportArtifact]:
    """Write the implementation stage report artifact.

    Pass `sequence` — the repair attempt number — when a workflow writes more than one.
    """
    return _generate_report(
        "generate_stage_report",
        audit_root=audit_root,
        workflow_id=workflow_id,
        report_kind="stage",
        payload=results,
        sequence=sequence,
    )


def generate_qa_report(
    *,
    audit_root: Path,
    workflow_id: str,
    results: dict[str, Any],
    sequence: int | None = None,
) -> SkillResult[ReportArtifact]:
    """Write the independent QA report artifact.

    Pass `sequence` — the QA round number — when a workflow writes more than one.
    """
    return _generate_report(
        "generate_qa_report",
        audit_root=audit_root,
        workflow_id=workflow_id,
        report_kind="qa",
        payload=results,
        sequence=sequence,
    )


def generate_failure_report(
    *,
    audit_root: Path,
    workflow_id: str,
    context: dict[str, Any],
    sequence: int | None = None,
) -> SkillResult[ReportArtifact]:
    """Write the failure report artifact.

    Pass `sequence` when a workflow reports more than one distinct failure.
    """
    return _generate_report(
        "generate_failure_report",
        audit_root=audit_root,
        workflow_id=workflow_id,
        report_kind="failure",
        payload=context,
        sequence=sequence,
    )


def generate_closeout_report(
    *,
    audit_root: Path,
    workflow_id: str,
    results: dict[str, Any],
    sequence: int | None = None,
) -> SkillResult[ReportArtifact]:
    """Write the closeout report artifact.

    `sequence` exists for symmetry with the other three generators; a workflow closes out once.
    """
    return _generate_report(
        "generate_closeout_report",
        audit_root=audit_root,
        workflow_id=workflow_id,
        report_kind="closeout",
        payload=results,
        sequence=sequence,
    )


def _parse_report_filename(filename: str) -> tuple[str, int | None] | None:
    """Split a stored report's name back into `(report_kind, sequence)`, or `None` if it is not one.

    The inverse of `_generate_report`'s own naming rule, kept beside it so the two cannot drift.
    `<kind>.json` and `<kind>.<sequence>.json` are ambiguous in general, because `_COMPONENT_RE`
    permits a `.` inside a kind: `qa.3.json` could be kind `qa` sequence 3, or kind `qa.3`. It is
    read as the sequenced form whenever the trailing segment is an in-range sequence, which is the
    only one of the two spellings this module can actually produce for such a name — the sequence
    argument is a validated integer in `1..9999`, so nothing here ever wrote a kind ending in
    `.<digits>`.
    """
    if not filename.endswith(".json"):
        return None
    stem = filename[: -len(".json")]
    kind, separator, tail = stem.rpartition(".")
    if separator and tail.isdigit() and not tail.startswith("0"):
        sequence = int(tail)
        if 1 <= sequence <= _MAX_REPORT_SEQUENCE and _COMPONENT_RE.fullmatch(kind):
            return kind, sequence
    if _COMPONENT_RE.fullmatch(stem):
        return stem, None
    return None


def _read_confined_report(
    skill: str, directory_fd: int, filename: str, directory: Path
) -> tuple[PersistedReport | None, SkillResult[Any] | None]:
    """Read one report file through an already-confined directory descriptor."""
    parsed = _parse_report_filename(filename)
    if parsed is None:
        return None, None  # not a report artifact this module ever wrote; ignored, not an error
    report_kind, sequence = parsed
    try:
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as exc:
        return None, failure(skill, FailureKind.IO_ERROR, f"report {filename!r} is unsafe: {exc}")
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None, failure(skill, FailureKind.IO_ERROR, f"{filename!r} is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 65536):
            chunks.append(chunk)
    except OSError as exc:
        return None, failure(skill, FailureKind.IO_ERROR, f"could not read {filename!r}: {exc}")
    finally:
        os.close(fd)
    payload = b"".join(chunks)
    try:
        content = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, failure(
            skill, FailureKind.MALFORMED_OUTPUT, f"{filename!r} is not valid JSON: {exc}"
        )
    if not isinstance(content, dict):
        return None, failure(
            skill, FailureKind.MALFORMED_OUTPUT, f"{filename!r} is not a JSON object"
        )
    return (
        PersistedReport(
            report_kind=report_kind,
            sequence=sequence,
            path=directory / filename,
            sha256=sha256(payload).hexdigest(),
            size_bytes=len(payload),
            content=content,
        ),
        None,
    )


def read_reports(
    *, audit_root: Path, workflow_id: str, report_kind: str | None = None
) -> SkillResult[list[PersistedReport]]:
    """Read back one workflow's already-persisted report artifacts. Writes nothing (AUTO-009).

    The read counterpart of the four generators above, and deliberately the *only* one: every
    generator is a write, so a caller that merely wants to look at a report has, until now, had no
    way to do so that did not go through a function whose contract is to create one. This opens
    each file `O_RDONLY | O_NOFOLLOW` through the same descriptor-relative walk the writers use,
    creates no directory and no file, and never regenerates, rewrites, or repairs an artifact —
    a malformed report is reported as malformed, not fixed.

    A workflow with no reports directory yet is an empty list, not a failure; filtering to a
    `report_kind` that produced no artifact is likewise an empty list, so the caller decides
    whether "none" is an error in its context. Results are ordered by `(report_kind, sequence)`
    with the unsequenced `<kind>.json` first within a kind, so repeated reads are byte-identical.
    """
    skill = "read_reports"
    if problem := _validate_component(skill, "workflow_id", workflow_id):
        return problem
    if report_kind is not None and (
        problem := _validate_component(skill, "report_kind", report_kind)
    ):
        return problem
    if not audit_root.is_absolute():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            "audit_root must be an absolute path",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    components = (workflow_id, "reports")
    directory_fd, error = _open_confined_directory(
        skill, audit_root, components, create=False, missing_ok=True
    )
    if error is not None:
        return error
    if directory_fd is None:
        return success([])
    directory = audit_root.joinpath(*components)
    reports: list[PersistedReport] = []
    try:
        try:
            filenames = sorted(os.listdir(directory_fd))
        except OSError as exc:
            return failure(skill, FailureKind.IO_ERROR, f"could not list {directory}: {exc}")
        for filename in filenames:
            report, read_error = _read_confined_report(skill, directory_fd, filename, directory)
            if read_error is not None:
                return read_error
            if report is None or (report_kind is not None and report.report_kind != report_kind):
                continue
            reports.append(report)
    finally:
        os.close(directory_fd)
    # `sequence is None` sorts before any real sequence: `<kind>.json` is the artifact a workflow
    # that never entered the repair loop wrote, so it reads as that kind's first round.
    reports.sort(
        key=lambda report: (report.report_kind, report.sequence is not None, report.sequence or 0)
    )
    return success(reports)


def write_sanitized_output(
    *, audit_root: Path, workflow_id: str, operation_id: str, stream: str, content: str
) -> SkillResult[ReportArtifact]:
    """Write redacted command output and return the reference `AUDIT_MODEL.md` §2 names.

    This is the *only* path that produces a `stdout_ref`/`stderr_ref`. The schema requires raw
    output to be stored as a file reference and never inlined into a record, and routing every
    such write through one function is what makes that property checkable rather than a
    convention each call site has to remember.
    """
    skill = "write_sanitized_output"
    if stream not in ("stdout", "stderr"):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"stream must be 'stdout' or 'stderr', not {stream!r}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    for field, value in (("workflow_id", workflow_id), ("operation_id", operation_id)):
        if problem := _validate_component(skill, field, value):
            return problem
    return _write_confined_file(
        skill,
        audit_root=audit_root,
        components=(workflow_id, "output", operation_id),
        filename=f"{stream}.txt",
        payload=redact_secrets(content).encode("utf-8", errors="replace"),
    )


def append_audit_event(
    *, audit_root: Path, workflow_id: str, event: dict[str, Any]
) -> SkillResult[AuditAppendResult]:
    """Append one event to the workflow's append-only audit log.

    Idempotent per `SKILL_CONTRACTS.md` §6: an event carries a stable `event_id` derived from its
    own content when the caller does not supply one, and re-appending an event whose ID is
    already present is detected and suppressed rather than duplicated.

    The append is a single `O_APPEND` write of one complete line. On a local filesystem an
    `O_APPEND` write below the pipe-buffer size is atomic with respect to other appenders, so a
    concurrent writer cannot interleave a partial record — which matters because a torn line in
    an append-only log is indistinguishable from tampering.
    """
    skill = "append_audit_event"
    if problem := _validate_component(skill, "workflow_id", workflow_id):
        return problem
    if not audit_root.is_absolute():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            "audit_root must be an absolute path",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    record = _redact_payload(dict(event))
    if not isinstance(record, dict):  # pragma: no cover - defensive, `event` is typed as a dict
        return failure(skill, FailureKind.UNSAFE_INPUT, "event must be a JSON object")
    record.setdefault("workflow_id", workflow_id)
    record.setdefault("recorded_at", utc_now().isoformat())
    supplied_id = record.get("event_id")
    if supplied_id is None:
        identity = json.dumps(record, sort_keys=True, ensure_ascii=False)
        record["event_id"] = sha256(identity.encode("utf-8")).hexdigest()
    elif not isinstance(supplied_id, str) or not _COMPONENT_RE.fullmatch(supplied_id):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"event_id={supplied_id!r} is not a safe identifier",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    event_id = str(record["event_id"])
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    if "\n" in line[:-1]:  # pragma: no cover - `json.dumps` escapes newlines
        return failure(skill, FailureKind.UNSAFE_INPUT, "event serializes to more than one line")

    directory_fd, error = _open_confined_directory(skill, audit_root, (workflow_id,), create=True)
    if error is not None or directory_fd is None:
        return error if error is not None else failure(skill, FailureKind.IO_ERROR, "audit root")
    try:
        try:
            log_fd = os.open(
                _AUDIT_LOG_NAME,
                os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            return failure(skill, FailureKind.IO_ERROR, f"could not open the audit log: {exc}")
        try:
            chunks: list[bytes] = []
            while chunk := os.read(log_fd, 65536):
                chunks.append(chunk)
            existing = b"".join(chunks).decode("utf-8", errors="replace")
            for existing_line in existing.splitlines():
                if not existing_line.strip():
                    continue
                try:
                    parsed = json.loads(existing_line)
                except json.JSONDecodeError:
                    # A corrupt historical line is not this Skill's to repair; it must not,
                    # however, cause a duplicate to be appended, so scanning continues.
                    continue
                if isinstance(parsed, dict) and parsed.get("event_id") == event_id:
                    return success(
                        AuditAppendResult(
                            event_id=event_id,
                            appended=False,
                            path=audit_root / workflow_id / _AUDIT_LOG_NAME,
                        )
                    )
            os.write(log_fd, line.encode("utf-8"))
            os.fsync(log_fd)
        except OSError as exc:
            return failure(skill, FailureKind.IO_ERROR, f"could not append to the audit log: {exc}")
        finally:
            os.close(log_fd)
        return success(
            AuditAppendResult(
                event_id=event_id,
                appended=True,
                path=audit_root / workflow_id / _AUDIT_LOG_NAME,
            )
        )
    finally:
        os.close(directory_fd)
