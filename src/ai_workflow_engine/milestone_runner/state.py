"""Durable run state: the artifact root, atomic publication, redaction and resume (AUTO-016).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 11 (the
durable state model, atomicity, schema versioning, append-only ledgers and transcript naming),
section 13 (idempotent resume), section 17a (sanitization before persistence -- the single
enforced write boundary), section 22 invariants 2, 7, 8, 9 and 10, and section 6 defects P-6 (an
unlocked state write) and P-9 (transcript collisions).

Where run state lives, and why it is not negotiable
---------------------------------------------------
`~/.ai-workflow-engine/milestone-runs/<repository-id>/<run-id>/`. A runner that wrote its own
state inside the worktree would pollute the diff it is guarding, so the root is verified to
resolve **outside** the repository and a configured root that would land inside is **refused,
never relocated** (invariant 7). Every path component is opened or checked no-follow; a symlinked
component is rejected rather than followed (invariant 8). `<repository-id>` is the one derivation
section 11 fixes, re-exported here as :func:`canonical_repository_id` so the state root, the plan
root (`plan.py`) and the run lock (`lock.py`) are all addressed by the same value.

`plan.py` carries its own containment and no-follow checks for the plan root, which is a sibling
of the run directories under this same root. The two are deliberately kept in agreement rather
than merged: `plan.py` is complete as M02 delivered it and outside this milestone's writable
surface, so the agreement is asserted by test -- `artifact_root_for` and
`plan.repository_scoped_root` must return the same path, and the two containment checks must
admit and refuse the same roots -- rather than asserted in a comment.

The single write boundary (section 17a)
---------------------------------------
`SECURITY_MODEL.md` section 1 requires command output to be sanitized before it is referenced in
an audit record, and `AUDIT_MODEL.md` section 2 goes further: never a raw credential, "even in a
referenced file". Referencing rather than inlining is necessary but not sufficient. So:

    every byte the runner persists -- provider stdout, provider stderr, a rendered prompt, a
    verification command's output, the state document itself -- goes through
    :func:`write_redacted_artifact`, and :func:`publish_atomically` is called from nowhere else.

There is no bypass parameter, and an AST test asserts that no other module in the package holds a
filesystem-write primitive at all. Redaction reuses
`successor_planning.redaction.redact_text` unmodified (DEC-016-008): an intra-package import
inside `src/ai_workflow_engine/`, so `ARCHITECTURE.md` section 4 is not engaged, and duplicating
a security primitive would only produce two redactors that drift.

Redaction is never silent. :func:`RunStateStore.record_redaction_findings` turns every pattern
that fired into a counted, deferred :class:`~ai_workflow_engine.milestone_runner.models.Finding`
on the run record, which is section 17a's "counted, visible finding" verbatim. Redaction remains
defense in depth, not a guarantee: it recognizes a bounded set of secret shapes and a novel one
may survive it. The primary control is that the runner never handles a credential at all.

Atomicity, and the crash points it is defined against
-----------------------------------------------------
Publication is `namespaced temp file in the same directory -> write -> fsync -> os.replace ->
fsync parent`. A crash before the rename leaves the canonical path holding exactly its previous
contents, never a torn document; a crash after it leaves the new document complete. An orphan
temp file is dot-prefixed and namespaced so it can never be mistaken for state, because nothing
reads a run directory by pattern -- `state.json` and `plan.json` are read by exact name and
transcripts by a closed grammar the temp prefix cannot satisfy.

Loading fails closed. Duplicate JSON keys are rejected at any nesting depth before validation,
because last-key-wins gives a tampered record two readings and no correct one; and an unknown
`schema_version` is :class:`StateSchemaUnknown` (`STATE_SCHEMA_UNKNOWN`), checked ahead of model
validation so it is a hard refusal rather than a best-effort read that happens to fail.

Resume, and why a changed-path name is not enough
-------------------------------------------------
Section 13 lets an interrupted provider invocation be repeated only when repeating it repeats
nothing. Deciding that by comparing the *set of changed path names* against the one the record
holds is unsound in one direction that matters: a provider whose first act is to rewrite a file
the record already lists as changed leaves the name set identical, so the comparison reports "no
change" and the effectful call is repeated on work that already landed.

So the evidence is content. Immediately before a process exists,
:meth:`RunStateStore.record_provider_intent` publishes `provider-intent.json`: the invocation's
identity plus a :class:`RepositoryFingerprint` -- one SHA-256 per relevant path, with missing,
unreadable and regular-file states kept distinct -- of the repository the invocation has not yet
touched. At resume the fingerprint is recomputed over the union of both key sets and compared, so
a new path, a vanished path and a rewritten path are all visible, and only a fingerprint that
still matches byte for byte permits `REINVOKE_PROVIDER`. No fingerprint bound to the invocation
is not a pass: absence of evidence fails closed here, like everything else in this module.

Only digests and metadata are persisted -- never a byte of any file's contents -- so
fingerprinting a repository that happens to contain a credential records that credential's digest
and its path, and nothing more.

Defect P-6, structurally
------------------------
Section 12 requires every state-mutating command to hold the run lock, including `abort`. Rather
than restate that as a rule for callers to remember, :meth:`RunStateStore.publish` and every
other writer here take a :class:`~ai_workflow_engine.milestone_runner.lock.RunLock` and refuse
unless it is currently held for this run's repository. An unlocked state write is not something a
call site can forget to avoid; there is no signature that expresses one. Read-only callers use
:meth:`RunStateStore.load`, which takes no lock and is safe against a torn read because
publication is atomic.

Defect P-9, structurally
------------------------
Transcript names carry a monotonic per-run sequence number, `<NNNN>-<UTC>-<label>.<kind>`. The
prototype's second-granularity `<stamp>-<role>` naming plus `Path.with_suffix` could silently
overwrite an earlier transcript when two invocations of one role landed in the same second.
:func:`next_transcript_sequence` reads the highest sequence already on disk, so the counter
survives a crash and a resume without being carried in memory, and two transcripts written in one
second are two files.
"""

import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Final

from pydantic import Field, ValidationError, field_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.git_inspect import (
    RepositoryDrift,
    RepositoryEvidence,
    derive_repository_identity,
)
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    STATE_SCHEMA_VERSION,
    UNREADABLE_DIGEST,
    Finding,
    FindingSeverity,
    FindingStatus,
    MilestoneRunnerModel,
    ProviderRole,
    ProviderRunRecord,
    RunRecord,
    RunStatus,
    StopReason,
    canonical_digest,
    normalize_repository_path,
)
from ai_workflow_engine.successor_planning.redaction import RedactionFinding, redact_text

#: Section 11's external artifact root, shared with the plan root `plan.py` derives.
ARTIFACT_ROOT_DIRECTORY: Final = ".ai-workflow-engine"
MILESTONE_RUNS_DIRECTORY: Final = "milestone-runs"

#: Section 11's per-run layout. Every one of these is read and written by exact name.
STATE_FILE_NAME: Final = "state.json"
PLAN_SNAPSHOT_FILE_NAME: Final = "plan.json"
TRANSCRIPTS_DIRECTORY: Final = "transcripts"

#: Section 13's durable pre-invocation evidence, read and written by exact name like the rest of
#: the layout. It is a separate document rather than a field on the run record because it is
#: written at a different moment, for a different reader, and must survive the crash that leaves
#: the record itself describing an invocation whose outcome nobody observed.
PROVIDER_INTENT_FILE_NAME: Final = "provider-intent.json"

#: The durable per-run transcript sequence counter (defect P-9). Dot-prefixed, so it can never be
#: confused with a transcript, and read by exact name, so allocating a sequence enumerates nothing.
TRANSCRIPT_SEQUENCE_FILE_NAME: Final = ".sequence"

#: The namespace every temporary file carries. Dot-prefixed so a directory listing hides it, and
#: distinctive enough that it can never satisfy the canonical or transcript grammars.
TEMP_FILE_PREFIX: Final = ".milestone-runner-tmp-"

#: Modes for anything this module creates. Run state records what a provider was asked and what
#: it said; it is nobody else's business.
DIRECTORY_MODE: Final = 0o700
ARTIFACT_MODE: Final = 0o600

#: Ceilings applied before anything is pulled into memory. The state document is a small current
#: -state record by design (section 11); a transcript is provider output and is larger.
MAX_STATE_BYTES: Final = 8 << 20
MAX_ARTIFACT_BYTES: Final = 64 << 20

#: The sequence counter holds one decimal integer and a newline; anything larger is corrupt.
MAX_SEQUENCE_FILE_BYTES: Final = 64

#: The ceiling on one file a fingerprint digests, and the block it is read in. A path above the
#: ceiling is recorded :data:`UNREADABLE_DIGEST`, which never compares equal, so an oversized
#: file can only cause a stop -- never a pass.
MAX_FINGERPRINT_FILE_BYTES: Final = 64 << 20
_FINGERPRINT_CHUNK_BYTES: Final = 1 << 20

#: The highest transcript sequence this naming scheme admits. Reaching it would need a hundred
#: million invocations in one run; the ceiling exists so the name stays bounded, not as a budget.
MAX_TRANSCRIPT_SEQUENCE: Final = 99_999_999

_REPOSITORY_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*--[0-9a-f]{12}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_TRANSCRIPT_LABEL_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_TRANSCRIPT_STAMP_FORMAT: Final = "%Y%m%dT%H%M%SZ"


class TranscriptKind(StrEnum):
    """The transcript triple of section 17, plus Codex's last-message file.

    The member *value* is the file-name suffix, so the naming grammar has exactly one definition
    and a reader can enumerate the closed set of suffixes a transcript may carry.
    """

    PROMPT = "prompt.md"
    STDOUT = "stdout.txt"
    STDERR = "stderr.txt"
    LAST_MESSAGE = "last-message.md"


_TRANSCRIPT_NAME_RE = re.compile(
    r"(?P<sequence>[0-9]{4,8})-[0-9]{8}T[0-9]{6}Z-[a-z0-9-]+\."
    + r"(?:"
    + "|".join(re.escape(kind.value) for kind in TranscriptKind)
    + r")"
)


# --------------------------------------------------------------------------------------
# Typed failures. Every one is fail-closed; none has a best-effort branch.
# --------------------------------------------------------------------------------------


class StateError(WorkflowEngineError):
    """Base durable-state failure.

    `stop_reason` is a plain class attribute rather than a `ClassVar` because
    :class:`ResumeRefused` sets it per instance -- resume can refuse for any of three distinct
    section 4 reasons and the code has to travel with the refusal, not with its class.
    """

    stop_reason: StopReason | None = None


class StateRootRefused(StateError):
    """The artifact root is unusable: inside the repository, symlinked, or malformed.

    Section 11 refuses such a root outright. It is never relocated to somewhere acceptable --
    silently moving a guarded boundary is how a guard talks itself into permitting an escape.
    """


class StatePublicationFailure(StateError):
    """A durable write could not be completed. Nothing partial is left at a canonical path."""


class StateCorrupted(StateError):
    """The persisted document is unreadable, ambiguous, or fails the closed schema."""


class StateSchemaUnknown(StateError):
    """`state.json` carries a `schema_version` this build does not understand (section 11).

    A hard refusal, checked before model validation, never a best-effort read: a record written
    by a different schema has no correct reading here, and guessing one would put unvalidated
    data into a safety-critical path.
    """

    stop_reason: StopReason | None = StopReason.STATE_SCHEMA_UNKNOWN


class ResumeRefused(StateError):
    """Resume cannot continue: the repository is not where the run left it (sections 4, 13).

    Carries every drift observed in one pass, so an operator sees the whole picture rather than
    fixing one aspect at a time, and takes its `stop_reason` from the first aspect in section 4's
    own order -- identity, then branch, then `HEAD`.
    """

    def __init__(self, message: str, *, drift: Sequence[RepositoryDrift]) -> None:
        super().__init__(message)
        self.drift: tuple[RepositoryDrift, ...] = tuple(drift)
        self.stop_reason = drift[0].stop_reason if drift else None


# --------------------------------------------------------------------------------------
# Section 11 -- identity, the artifact root, and the two boundary checks
# --------------------------------------------------------------------------------------


def canonical_repository_id(primary_remote_url: str) -> str:
    """Return the canonical `<repository-id>` the artifact root and the run lock are keyed by.

    Section 11 fixes one derivation -- the normalized repository name plus the first twelve hex
    characters of SHA-256 over the canonical, credential-free primary remote identity -- and
    `git_inspect.derive_repository_identity` is it. Naming it here gives the durable-state layer
    the vocabulary without a second implementation: two derivations of one identity would let two
    runners against one repository address two roots and two locks.
    """
    return derive_repository_identity(primary_remote_url)


def artifact_root_for(repository_id: str) -> Path:
    """Return `~/.ai-workflow-engine/milestone-runs/<repository-id>/` (section 11).

    A pure derivation: nothing is created, resolved or verified here, and a malformed identity is
    refused before it can reach the filesystem. This is the same path `plan.repository_scoped_root`
    returns -- run output and plan input are siblings under one root by design, so one containment
    check and one no-follow discipline govern both -- and a test asserts the two agree.
    """
    if _REPOSITORY_ID_RE.fullmatch(repository_id) is None:
        raise StateRootRefused(
            f"{repository_id!r} is not a canonical repository identity, so it cannot address an "
            "artifact root"
        )
    return Path.home() / ARTIFACT_ROOT_DIRECTORY / MILESTONE_RUNS_DIRECTORY / repository_id


def reject_repository_containment(root: Path, repository_root: Path) -> None:
    """Refuse `root` if it resolves inside `repository_root` (invariant 7).

    Both sides are fully realized before the comparison, so a symlink pointing back into the
    worktree cannot dress an inside path up as an outside one. The refusal is the whole remedy:
    a root that would land inside is never quietly moved somewhere acceptable, because a runner
    that can relocate its own state boundary is not guarding one.
    """
    real_repository = os.path.realpath(repository_root)
    real_root = os.path.realpath(root)
    if real_root == real_repository or real_root.startswith(real_repository + os.sep):
        raise StateRootRefused(
            f"The state root {real_root} must not be inside the repository {real_repository}: "
            "section 11 fixes an external, repository-scoped root that is never part of Git"
        )


def reject_symlink_components(path: Path, label: str) -> None:
    """Refuse `path` if any component of it is a symbolic link (invariant 8).

    Walked from the filesystem root downwards with `lstat`, so no component is followed in order
    to decide whether it should have been followed. Every component is checked and not just the
    last: a symlinked *parent* redirects a write exactly as effectively as a symlinked final
    name, and the root sits under the operator's home directory where a swapped component is the
    cheapest available substitution. A component that does not exist yet is not a link; whatever
    opens the path afterwards reports its absence.
    """
    absolute = path if path.is_absolute() else Path(os.path.abspath(path))
    for component in [*reversed(absolute.parents), absolute]:
        if component.is_symlink():
            raise StateRootRefused(f"{label} component {component} is a symbolic link")


def _create_directory(directory: Path) -> None:
    """Create `directory` and every missing ancestor at :data:`DIRECTORY_MODE`.

    Each component this call creates is created restricted directly, so no window exists in which
    a broader mode is visible. An ancestor that already exists is left alone: the
    `~/.ai-workflow-engine` directory is shared with the prompt store and the successor-planning
    artifact store, and its mode is the operator's choice.
    """
    try:
        os.makedirs(directory, mode=DIRECTORY_MODE, exist_ok=True)
    except OSError as exc:
        raise StatePublicationFailure(f"{directory} could not be created: {exc}") from exc


# --------------------------------------------------------------------------------------
# Section 11 -- atomic publication
# --------------------------------------------------------------------------------------


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write every byte of `payload`; POSIX permits `os.write` to make a short write."""
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError(f"os.write made no progress with {len(view)} bytes remaining")
        view = view[written:]


def _fsync_directory(directory: Path) -> None:
    """Fsync `directory` where the platform supports it (section 11's parent-directory fsync).

    A platform that refuses to open or fsync a directory is not an error: the rename is already
    atomic, and this only shortens the window in which a completed rename is not yet durable
    across a power loss.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def publish_atomically(path: Path, payload: bytes) -> None:
    """Publish `payload` at `path` so no crash point leaves a torn document (invariant 9).

    The protocol is section 11's, exactly: a namespaced temporary file **in the same directory**
    -- so the rename is always same-filesystem and therefore atomic -- written in full, fsynced,
    `os.replace`d onto the canonical name, and the parent directory fsynced. Before the rename
    the canonical path still holds precisely its previous contents; after it, the complete new
    document. There is no moment at which a reader sees half of either.

    The temporary file is created `O_EXCL | O_NOFOLLOW`, so it is always a fresh, real file this
    call owns, and it is removed on every failure path this process can observe. A hard kill
    leaves it behind, which is harmless: its name is dot-prefixed and namespaced and matches no
    grammar any reader here consults.

    This is the mechanism, not the boundary. Section 17a's boundary is
    :func:`write_redacted_artifact`, which is the only caller of this function in the package.
    """
    directory = path.parent
    temporary = directory / f"{TEMP_FILE_PREFIX}{uuid.uuid4().hex}"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            ARTIFACT_MODE,
        )
    except OSError as exc:
        raise StatePublicationFailure(
            f"The temporary file for {path} could not be created: {exc}"
        ) from exc
    try:
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    except BaseException as exc:
        # Nothing reached the canonical name, so the previous document -- or its absence -- is
        # still exactly what a reader will find.
        try:
            os.unlink(temporary)
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise StatePublicationFailure(f"{path} could not be published: {exc}") from exc
        raise
    _fsync_directory(directory)


# --------------------------------------------------------------------------------------
# Section 17a -- the single enforced redaction write boundary
# --------------------------------------------------------------------------------------


class RedactedWrite(MilestoneRunnerModel):
    """What one pass through the section 17a boundary wrote, and what it neutralized.

    `findings` is empty on the ordinary path. When it is not, section 17a requires the event to
    be counted and visible rather than silent, which
    :meth:`RunStateStore.record_redaction_findings` does by turning each entry into a deferred
    finding on the run record. A :class:`RedactionFinding` carries only the pattern name, the
    occurrence count and the first offset -- never anything that narrows what the value was -- so
    it is safe to persist and to render.
    """

    path: str
    relative_path: str | None = None
    byte_count: int = Field(ge=0)
    findings: list[RedactionFinding] = Field(default_factory=list)

    @property
    def redacted(self) -> bool:
        """Whether any pattern fired on the way to disk."""
        return bool(self.findings)


def write_redacted_artifact(
    path: Path, text: str, *, relative_path: str | None = None
) -> RedactedWrite:
    """Redact `text`, then publish it atomically at `path` -- the only way bytes reach disk.

    Section 17a: no byte reaches a transcript, a verification-output file or a state file before
    passing through redaction, so referencing rather than inlining is backed by the referenced
    file itself being clean. There is no parameter that skips redaction and no second path to
    :func:`publish_atomically`; `relative_path` is a label carried onto the result for the
    record's benefit and changes nothing about what is written.

    Redaction is lossy and non-reversible: a match is replaced by a fixed `[REDACTED:<pattern>]`
    marker and the original bytes are discarded, not encoded. It is defense in depth and not a
    proof of cleanliness -- it recognizes a bounded set of well-known secret shapes, and a novel
    format may survive it.
    """
    reject_symlink_components(path, "The artifact")
    redacted, findings = redact_text(text)
    payload = redacted.encode("utf-8")
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise StatePublicationFailure(
            f"{path} would be {len(payload)} bytes, above the {MAX_ARTIFACT_BYTES}-byte ceiling"
        )
    publish_atomically(path, payload)
    return RedactedWrite(
        path=str(path),
        relative_path=relative_path,
        byte_count=len(payload),
        findings=list(findings),
    )


# --------------------------------------------------------------------------------------
# Section 11 -- transcript naming, and defect P-9
# --------------------------------------------------------------------------------------


def _read_transcript_sequence(counter: Path) -> int:
    """Read the last allocated sequence, or 0 when nothing has ever been allocated.

    A counter that exists but cannot be read as a bounded integer is a refusal, not a reason to
    start again at 1: restarting is precisely how defect P-9 overwrites an earlier transcript.
    """
    if not counter.is_file():
        return 0
    payload = _read_bounded(counter, MAX_SEQUENCE_FILE_BYTES)
    try:
        value = int(payload.decode("utf-8").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise StateCorrupted(
            f"{counter} does not hold a transcript sequence number; refusing to restart the "
            "numbering, which would risk overwriting an earlier transcript"
        ) from exc
    if not 0 <= value <= MAX_TRANSCRIPT_SEQUENCE:
        raise StateCorrupted(f"{counter} holds {value}, outside the allocatable sequence range")
    return value


def next_transcript_sequence(transcripts_directory: Path) -> int:
    """Allocate the next monotonic per-run transcript sequence number (defect P-9).

    The counter is a durable file rather than a directory listing, for two independent reasons.
    Invariant 19 admits exactly one directory enumeration in the whole package -- `plan.py`'s
    single non-recursive pass over the external plan root -- and a counter needs none. And an
    allocation that is recorded before the transcript it names is monotonic across a crash: the
    run that resumes reads the last allocated number rather than restarting at 1, which is the
    behaviour defect P-9 turns on. A crash between the allocation and the write leaves a number
    unused, which is harmless; a reused number would not be.

    Allocation is durable, so this call writes -- through the section 17a boundary like every
    other byte, where redaction is a no-op on an integer but the invariant stays literally true.
    The run lock is the serialization: :meth:`RunStateStore.next_transcript_sequence` demands one,
    so two allocations never interleave.
    """
    counter = transcripts_directory / TRANSCRIPT_SEQUENCE_FILE_NAME
    allocated = _read_transcript_sequence(counter) + 1
    if allocated > MAX_TRANSCRIPT_SEQUENCE:
        raise StatePublicationFailure(
            f"{transcripts_directory} has reached the {MAX_TRANSCRIPT_SEQUENCE} transcript ceiling"
        )
    write_redacted_artifact(counter, f"{allocated}\n")
    return allocated


def transcript_name(sequence: int, moment: datetime, label: str, kind: TranscriptKind) -> str:
    """Return section 11's `<NNNN>-<UTC>-<label>.<kind>` transcript name.

    The sequence leads the name so a directory listing sorts in invocation order, and it is what
    makes two invocations of one role within one second two files rather than one silently
    overwritten by the other (defect P-9). `label` is a lowercase slug -- a provider role, or
    `verification` for section 16's command output -- validated here so no caller can smuggle a
    separator or a traversal segment into a file name.
    """
    if not 1 <= sequence <= MAX_TRANSCRIPT_SEQUENCE:
        raise StatePublicationFailure(
            f"{sequence} is outside the 1..{MAX_TRANSCRIPT_SEQUENCE} transcript sequence range"
        )
    if _TRANSCRIPT_LABEL_RE.fullmatch(label) is None:
        raise StatePublicationFailure(
            f"{label!r} is not a usable transcript label; expected {_TRANSCRIPT_LABEL_RE.pattern!r}"
        )
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise StatePublicationFailure(
            "A transcript timestamp must be timezone-aware UTC; a naive or offset stamp would "
            "make two runs on two machines order differently in one directory listing"
        )
    name = f"{sequence:04d}-{moment.strftime(_TRANSCRIPT_STAMP_FORMAT)}-{label}.{kind.value}"
    if _TRANSCRIPT_NAME_RE.fullmatch(name) is None:
        raise StatePublicationFailure(
            f"{name!r} does not satisfy the transcript grammar {_TRANSCRIPT_NAME_RE.pattern!r}"
        )
    return name


def transcript_reference(sequence: int, moment: datetime, label: str, kind: TranscriptKind) -> str:
    """Return the run-relative POSIX path a record references one transcript by (section 11).

    The one definition of that reference, so a record written before a transcript exists and the
    write that later creates it cannot name it two different ways.
    """
    return f"{TRANSCRIPTS_DIRECTORY}/{transcript_name(sequence, moment, label, kind)}"


# --------------------------------------------------------------------------------------
# Section 13 -- the durable pre-invocation content fingerprint
# --------------------------------------------------------------------------------------

#: The digest recorded for a path that is simply not there. Unlike :data:`UNREADABLE_DIGEST` it
#: is a real observation and it *does* compare equal to itself: a tracked file staged as deleted
#: is absent both before and after an invocation that never ran, and calling that a change would
#: refuse every resume of a run whose diff contains a deletion. Absent-then-present and
#: present-then-absent both still differ, which is the pair that matters.
ABSENT_DIGEST: Final = "absent"


class RepositoryFingerprint(MilestoneRunnerModel):
    """What the repository's relevant content was at one moment, addressed by digest.

    Section 13 asks whether an interrupted provider invocation had an effect. The set of changed
    *path names* cannot answer that: a provider that rewrites a file the record already lists as
    changed leaves the name set identical, and a reconciliation that compares names alone reports
    "no change" and permits the effectful call to be repeated. So the evidence is content: one
    SHA-256 per relevant path, plus the three pins the observation was taken under.

    Four path states are distinguished, and the distinction is what keeps the comparison honest.
    A regular file digests to its bytes. A path that does not exist is :data:`ABSENT_DIGEST`,
    which compares equal to itself. A path that exists but cannot be safely read -- a symlinked
    component (invariant 8), a device or a directory where a file was, or a file above
    :data:`MAX_FINGERPRINT_FILE_BYTES` -- is :data:`UNREADABLE_DIGEST`, which never compares
    equal, not even to itself, because an unreadable observation is not evidence of sameness.

    Only digests and metadata are stored. No file's contents ever reach this record, so a
    fingerprint over a file holding a credential persists the credential's digest and its path
    and nothing else.
    """

    repository_identity: str
    branch: str
    head_sha: str
    path_digests: dict[str, str] = Field(default_factory=dict)

    @field_validator("path_digests")
    @classmethod
    def _validate_path_digests(cls, value: dict[str, str]) -> dict[str, str]:
        """Normalize every key and fix one canonical ordering for the whole mapping."""
        normalized = {
            normalize_repository_path(path, "path_digests"): digest
            for path, digest in value.items()
        }
        return {
            path: normalized[path]
            for path in sorted(normalized, key=lambda item: item.encode("utf-8"))
        }

    @property
    def digest(self) -> str:
        """One deterministic SHA-256 over the whole observation.

        Derived rather than stored, so it cannot disagree with the mapping it summarizes.
        :func:`~ai_workflow_engine.milestone_runner.models.canonical_digest` sorts keys and fixes
        the serialization, so two fingerprints taken over an unchanged repository -- in either
        order, on either machine -- digest identically.
        """
        return canonical_digest(
            {
                "repository_identity": self.repository_identity,
                "branch": self.branch,
                "head_sha": self.head_sha,
                "path_digests": dict(self.path_digests),
            }
        )


class ProviderInvocationIntent(MilestoneRunnerModel):
    """The intent to make one effectful provider call, made durable before the process exists.

    Written at `provider-intent.json` immediately before
    :meth:`~ai_workflow_engine.milestone_runner.providers.base.ProviderInvoker.invoke` spawns
    anything, so a runner that dies at any point afterwards leaves behind both halves of what
    section 13 needs: the record naming an invocation with no `completed_at`, and the repository
    as it stood before that invocation could touch it.

    `sequence` binds the intent to exactly one invocation. A document left over from an earlier,
    already-settled call is not evidence about the current one, so resume compares sequences and
    treats a mismatch as no evidence at all -- which fails closed, never open.
    """

    run_id: str
    sequence: int = Field(ge=1)
    role: ProviderRole
    provider: str
    milestone_id: str | None = None
    recorded_at: str
    fingerprint: RepositoryFingerprint


def digest_repository_path(repository_root: Path, relative_path: str) -> str:
    """SHA-256 the bytes at `relative_path` inside `repository_root`, or say why it could not.

    Reading stays inside the repository by construction:
    :func:`~ai_workflow_engine.milestone_runner.models.normalize_repository_path` refuses an
    absolute, drive-lettered, backslash-separated or traversal-shaped input outright, so the
    joined path can only descend. Every component below the root is checked with `lstat` before
    it is used and the file itself is opened `O_NOFOLLOW`, so a symlink is refused rather than
    followed (invariant 8) -- including one planted between the check and the open, which the
    open itself rejects.

    Nothing here raises. Every unreadable state collapses to :data:`UNREADABLE_DIGEST`, which
    never compares equal, so the conservative direction is the only one available: an
    un-digestible path can force a reconciliation, never permit a repetition.
    """
    try:
        normalized = normalize_repository_path(relative_path, "fingerprint path")
    except ValueError:
        return UNREADABLE_DIGEST
    target = repository_root
    for part in Path(normalized).parts:
        target = target / part
        try:
            if target.is_symlink():
                return UNREADABLE_DIGEST
        except OSError:
            return UNREADABLE_DIGEST
    try:
        status = os.lstat(target)
    except FileNotFoundError:
        return ABSENT_DIGEST
    except OSError:
        return UNREADABLE_DIGEST
    if not stat.S_ISREG(status.st_mode):
        return UNREADABLE_DIGEST
    if status.st_size > MAX_FINGERPRINT_FILE_BYTES:
        return UNREADABLE_DIGEST
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return ABSENT_DIGEST
    except OSError:
        return UNREADABLE_DIGEST
    running = hashlib.sha256()
    consumed = 0
    try:
        while True:
            chunk = os.read(descriptor, _FINGERPRINT_CHUNK_BYTES)
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > MAX_FINGERPRINT_FILE_BYTES:
                return UNREADABLE_DIGEST
            running.update(chunk)
    except OSError:
        return UNREADABLE_DIGEST
    finally:
        os.close(descriptor)
    return running.hexdigest()


def fingerprint_repository(
    repository_root: Path, evidence: RepositoryEvidence, *, also: Iterable[str] = ()
) -> RepositoryFingerprint:
    """Fingerprint the repository state one observation says is relevant, plus `also`.

    The relevant state is the changed-path set the observation reported, which is what a provider
    invocation can be expected to move. `also` carries the paths an *earlier* fingerprint covered
    so that the two are always compared over the same key set: a path a provider deleted has left
    the current changed-path set entirely, and only its presence in `also` keeps its
    disappearance visible.
    """
    paths = {*evidence.changed_paths, *also}
    return RepositoryFingerprint(
        repository_identity=evidence.repository_identity,
        branch=evidence.branch,
        head_sha=evidence.head_sha,
        path_digests={path: digest_repository_path(repository_root, path) for path in paths},
    )


def fingerprint_delta(before: RepositoryFingerprint, after: RepositoryFingerprint) -> list[str]:
    """Every path whose content `after` does not prove identical to `before`.

    Compared over the union of both key sets, so all three shapes of effect are visible: a path
    only `after` knows is new, a path only `before` knows has gone unobserved, and a path both
    know whose digest moved. A path either side of which is unreadable is reported changed,
    because "we could not look" is not "nothing happened".
    """
    changed: list[str] = []
    for path in {*before.path_digests, *after.path_digests}:
        left = before.path_digests.get(path)
        right = after.path_digests.get(path)
        if left is None or right is None:
            changed.append(path)
        elif left == UNREADABLE_DIGEST or right == UNREADABLE_DIGEST:
            changed.append(path)
        elif left != right:
            changed.append(path)
    return sorted(changed, key=lambda item: item.encode("utf-8"))


# --------------------------------------------------------------------------------------
# Section 13 -- what resume decided
# --------------------------------------------------------------------------------------


class ResumeAction(StrEnum):
    """What resume concluded about repeating the run's last side effect (section 13).

    `MACHINE_GATES.md` section 2a is the rule being implemented: "a possible provider invocation
    effect is reconciled against its persisted operation evidence before repetition or
    transition; appearance alone never advances the workflow."
    """

    #: No side effect was in flight. The run continues from the state it recorded.
    CONTINUE = "CONTINUE"
    #: A provider invocation was in flight and the durable pre-invocation fingerprint proves it
    #: left the repository's content byte-identical, so repeating it repeats nothing. This is the
    #: only action that permits a re-invocation, and only proof -- never the absence of a
    #: contrary signal -- reaches it.
    REINVOKE_PROVIDER = "REINVOKE_PROVIDER"
    #: A provider invocation was in flight and its effect is either visible or unproven: the
    #: worktree carries a path the record does not account for, a fingerprinted path's content
    #: moved, or no durable pre-invocation fingerprint is available to compare against at all.
    #: Repeating it would be repeating a side effect on unreconciled evidence, so a human
    #: reconciliation (section 13) has to come first.
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"


class ResumeDecision(MilestoneRunnerModel):
    """The whole of what resume determined, computed without writing anything.

    Resume is read-only by construction, which is what makes section 13's "running `resume` twice
    with no intervening change is a no-op success" true rather than merely intended: the second
    call reads the same bytes and reaches the same conclusion, and neither call published a
    record, appended a ledger entry or invoked anything.

    `observed_changed_paths` is reported rather than judged. Whether a changed path is in scope is
    section 15's question and `scope.py`'s answer; this layer only says what it saw.

    `unaccounted_changed_paths` and `fingerprint_changed_paths` are two independent readings of
    the same question and neither subsumes the other: the first names paths the record had never
    heard of, the second names paths whose *content* moved since the invocation was made durable.
    A provider that rewrote a file the record already lists produces an empty first list and a
    non-empty second one, which is precisely the case a name-only comparison misses.
    """

    record: RunRecord
    action: ResumeAction
    reason: str
    observed_changed_paths: list[str] = Field(default_factory=list)
    unaccounted_changed_paths: list[str] = Field(default_factory=list)
    fingerprint_changed_paths: list[str] = Field(default_factory=list)

    @property
    def may_reinvoke_provider(self) -> bool:
        """Whether a provider may be re-invoked without a reconciliation act first."""
        return self.action is ResumeAction.REINVOKE_PROVIDER


#: The states in which a provider invocation may have been in flight when the run stopped.
#: `PROVIDER_WAIT` is the durable one section 10 added for exactly this purpose; the other three
#: are the invoking states a crash can also be observed in before the wait state is published.
_PROVIDER_IN_FLIGHT_STATES: Final[frozenset[RunStatus]] = frozenset(
    {
        RunStatus.PROVIDER_WAIT,
        RunStatus.IMPLEMENTING,
        RunStatus.CORRECTING,
        RunStatus.REVIEWING,
    }
)


# --------------------------------------------------------------------------------------
# Section 11 -- reading a persisted document, fail-closed
# --------------------------------------------------------------------------------------


class _DuplicateJSONKeyError(ValueError):
    """A JSON object repeated a key at some nesting depth."""

    def __init__(self, key: str) -> None:
        super().__init__(f"duplicate JSON object key {key!r}")
        self.key = key


def _loads_rejecting_duplicate_keys(text: str) -> object:
    """`json.loads`, but a repeated key in *any* object at *any* depth is an error.

    Standard JSON parsing silently applies last-key-wins, so a tampered record could carry two
    `workflow_state` or two `baseline_sha` values and be read as whichever the parser happened to
    keep. An ambiguous persisted record has no single correct reading, so it fails closed before
    validation rather than having one meaning chosen for it. `object_pairs_hook` sees the raw
    key/value pairs of every object before any dict collapses them, which is what makes a nested
    duplicate detectable at all.

    This is `agentos_workflow/orchestrator/state_store.py`'s documented discipline, adopted and
    re-implemented rather than imported -- section 22 invariant 6 forbids the import outright.
    """

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJSONKeyError(key)
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


def _read_bounded(path: Path, ceiling: int) -> bytes:
    """Read `path` no-follow, refusing anything that is not a bounded regular file."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise StateCorrupted(f"{path} could not be opened: {exc}") from exc
    try:
        status = os.fstat(descriptor)
        if status.st_size > ceiling:
            raise StateCorrupted(f"{path} is {status.st_size} bytes, above the {ceiling} ceiling")
        return os.read(descriptor, ceiling + 1)[:ceiling]
    finally:
        os.close(descriptor)


def _read_bounded_if_present(path: Path, ceiling: int) -> bytes | None:
    """:func:`_read_bounded`, except that a path which is simply not there reads as `None`.

    The one absence that is not corruption: a run that has never invoked a provider has no
    invocation-intent document. Everything else still fails closed -- a symlinked name reaches
    the no-follow open and is refused there, and an oversized or unreadable file is
    :class:`StateCorrupted` exactly as before.
    """
    if not path.is_file():
        return None
    return _read_bounded(path, ceiling)


# --------------------------------------------------------------------------------------
# Section 11 -- the store
# --------------------------------------------------------------------------------------


class RunStateStore:
    """One run's durable directory: publication, transcripts, loading and resume (section 11).

    Constructed through :meth:`pin`, which is where the boundary checks live: the artifact root
    is derived from the canonical repository identity, refused if it resolves inside the
    repository, refused if any component is a symlink, created restricted, and re-checked after
    creation because a component created between the check and now could have been created as a
    link by someone else.

    Every writer takes a :class:`RunLock` and refuses unless it is held for this repository
    (defect P-6). :meth:`load` takes none: a reader is safe against a torn document because
    publication is atomic, which is exactly the trade section 12 records for the read-only
    commands.
    """

    #: Present so a reader of this class does not have to go looking for what "the boundary"
    #: means: this is the one function through which its bytes reach the filesystem.
    write_boundary: ClassVar[str] = "milestone_runner.state.write_redacted_artifact"

    def __init__(
        self,
        *,
        run_directory: Path,
        repository_root: Path,
        repository_id: str,
        run_id: str,
    ) -> None:
        self._run_directory = run_directory
        self._repository_root = repository_root
        self._repository_id = repository_id
        self._run_id = run_id

    @classmethod
    def pin(cls, *, repository_id: str, run_id: str, repository_root: Path) -> "RunStateStore":
        """Resolve, verify and create this run's directory, then pin the store to it."""
        if _RUN_ID_RE.fullmatch(run_id) is None:
            raise StateRootRefused(f"{run_id!r} is not a usable run id for a state directory")
        root = artifact_root_for(repository_id)
        reject_symlink_components(root, "The artifact root")
        reject_repository_containment(root, repository_root)

        run_directory = root / run_id
        _create_directory(run_directory / TRANSCRIPTS_DIRECTORY)
        # Re-checked after creation: a component created between the check above and now could
        # have been created as a symbolic link by someone else.
        reject_symlink_components(run_directory / TRANSCRIPTS_DIRECTORY, "The run directory")
        reject_repository_containment(run_directory, repository_root)
        return cls(
            run_directory=run_directory,
            repository_root=repository_root,
            repository_id=repository_id,
            run_id=run_id,
        )

    # -- where things are ---------------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def repository_id(self) -> str:
        return self._repository_id

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def artifact_root(self) -> Path:
        """The repository-scoped root this run's directory sits under, shared with the lock."""
        return self._run_directory.parent

    @property
    def run_directory(self) -> Path:
        return self._run_directory

    @property
    def state_path(self) -> Path:
        return self._run_directory / STATE_FILE_NAME

    @property
    def provider_intent_path(self) -> Path:
        """Where this run's durable pre-invocation evidence lives (section 13)."""
        return self._run_directory / PROVIDER_INTENT_FILE_NAME

    @property
    def plan_snapshot_path(self) -> Path:
        """Section 11's resolved plan snapshot -- written by the runner, never a source plan."""
        return self._run_directory / PLAN_SNAPSHOT_FILE_NAME

    @property
    def transcripts_directory(self) -> Path:
        return self._run_directory / TRANSCRIPTS_DIRECTORY

    def relative_to_run(self, path: Path) -> str:
        """Return `path` as the run-relative POSIX path a record references it by."""
        return path.relative_to(self._run_directory).as_posix()

    # -- the lock precondition, defect P-6 ----------------------------------------------

    def _require_lock(self, lock: RunLock) -> None:
        """Refuse any write unless `lock` is currently held for this run's repository.

        Section 12 requires every state-mutating command to hold the run lock, `abort` included.
        Checking it at the writer rather than at the caller is what makes prototype defect P-6
        unreachable instead of merely documented: there is no writer signature here that does not
        demand a lock, and no argument that satisfies one without a live `flock`.
        """
        if not lock.is_held:
            raise StatePublicationFailure(
                f"Refusing to write under {self._run_directory}: the run lock at "
                f"{lock.lock_path} is not held (section 12, prototype defect P-6)"
            )
        if lock.repository_identity != self._repository_id:
            raise StatePublicationFailure(
                f"The held lock is for {lock.repository_identity}, not for this run's repository "
                f"{self._repository_id}"
            )

    # -- publication --------------------------------------------------------------------

    def publish(self, record: RunRecord, *, lock: RunLock) -> RedactedWrite:
        """Publish `record` atomically at `state.json`, through the redaction boundary.

        The state document is serialized to JSON and then passes through
        :func:`write_redacted_artifact` like every other byte, because section 17a's boundary
        covers "every transcript, verification-output **and state** file". Redaction cannot
        invalidate the document -- a `[REDACTED:<pattern>]` marker introduces no quote, no
        backslash and no structural character -- but it can, in principle, redact a field whose
        value is itself secret-shaped, in which case the next :meth:`load` refuses the record as
        corrupt. That is the fail-closed outcome, and it is preferred to persisting the secret.
        """
        self._require_lock(lock)
        if record.repository_identity != self._repository_id:
            raise StatePublicationFailure(
                f"The record names repository {record.repository_identity}, not this store's "
                f"{self._repository_id}"
            )
        if record.run_id != self._run_id:
            raise StatePublicationFailure(
                f"The record names run {record.run_id}, not this store's {self._run_id}"
            )
        return write_redacted_artifact(
            self.state_path,
            record.model_dump_json(indent=2),
            relative_path=STATE_FILE_NAME,
        )

    def publish_plan_snapshot(self, document: str, *, lock: RunLock) -> RedactedWrite:
        """Publish the resolved plan snapshot (section 11) at `plan.json`.

        A snapshot of what this run resolved, never a source plan and never a path any loader
        reads back as input -- `plan.py` refuses to discover a plan at all, and this file is
        under the artifact root rather than the plan root.
        """
        self._require_lock(lock)
        return write_redacted_artifact(
            self.plan_snapshot_path, document, relative_path=PLAN_SNAPSHOT_FILE_NAME
        )

    def record_provider_intent(
        self,
        *,
        pending: ProviderRunRecord,
        evidence: RepositoryEvidence,
        recorded_at: str,
        lock: RunLock,
    ) -> ProviderInvocationIntent:
        """Make the intent to invoke `pending` durable, with the repository as it stands now.

        Called after the invocation's sequence and transcript names are fixed and **before** the
        provider process exists, so the fingerprint it carries is by construction a picture of a
        repository the invocation has not touched. Publication is atomic like every other write
        here, so a crash leaves either the previous intent or this one, never half of either.

        The fingerprint covers the changed-path set `evidence` reported, extended by every path
        the run record already knew about, so a provider that deletes a known path cannot make
        the path's disappearance invisible by removing it from `git status` at the same time.
        """
        self._require_lock(lock)
        intent = ProviderInvocationIntent(
            run_id=self._run_id,
            sequence=pending.sequence,
            role=pending.role,
            provider=pending.provider,
            milestone_id=pending.milestone_id,
            recorded_at=recorded_at,
            fingerprint=fingerprint_repository(self._repository_root, evidence),
        )
        write_redacted_artifact(
            self.provider_intent_path,
            intent.model_dump_json(indent=2),
            relative_path=PROVIDER_INTENT_FILE_NAME,
        )
        return intent

    def load_provider_intent(self) -> ProviderInvocationIntent | None:
        """Read the durable pre-invocation evidence, or `None` when a run has never invoked.

        Fail-closed in the same four steps :meth:`load` uses -- bounded no-follow regular file,
        UTF-8, duplicate-key-free JSON, then model validation -- because an intent document that
        cannot be read unambiguously is not evidence, and a caller that treats "unreadable" as
        "unchanged" is exactly the mistake this whole mechanism exists to prevent.
        """
        payload = _read_bounded_if_present(self.provider_intent_path, MAX_STATE_BYTES)
        if payload is None:
            return None
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StateCorrupted(f"{self.provider_intent_path} is not valid UTF-8: {exc}") from exc
        try:
            document = _loads_rejecting_duplicate_keys(text)
        except _DuplicateJSONKeyError as exc:
            raise StateCorrupted(
                f"{self.provider_intent_path} carries a duplicate JSON object key {exc.key!r}; an "
                "ambiguous record has no single correct reading and is refused rather than "
                "guessed at"
            ) from exc
        except ValueError as exc:
            raise StateCorrupted(f"{self.provider_intent_path} is not valid JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise StateCorrupted(f"{self.provider_intent_path} is not a JSON object")
        try:
            return ProviderInvocationIntent.model_validate_json(text)
        except ValidationError as exc:
            raise StateCorrupted(
                f"{self.provider_intent_path} is not a valid invocation intent: {exc}"
            ) from exc

    def next_transcript_sequence(self, *, lock: RunLock) -> int:
        """Allocate this run's next monotonic transcript sequence number (defect P-9).

        A writer like every other on this store, and for the same reason: the allocation is
        durable, so the lock is what keeps two runners from allocating the same number.
        """
        self._require_lock(lock)
        return next_transcript_sequence(self.transcripts_directory)

    def write_transcript(
        self,
        *,
        sequence: int,
        label: str,
        kind: TranscriptKind,
        text: str,
        moment: datetime,
        lock: RunLock,
    ) -> RedactedWrite:
        """Write one transcript through the redaction boundary and return where it landed.

        `relative_path` on the result is the run-relative POSIX path a
        :class:`~ai_workflow_engine.milestone_runner.models.ProviderRunRecord` or
        :class:`~ai_workflow_engine.milestone_runner.models.VerificationResult` references the
        file by -- section 11 keeps transcripts referenced by path and never inlined.
        """
        self._require_lock(lock)
        reference = transcript_reference(sequence, moment, label, kind)
        path = self.transcripts_directory / transcript_name(sequence, moment, label, kind)
        return write_redacted_artifact(path, text, relative_path=reference)

    def record_redaction_findings(
        self, record: RunRecord, writes: Iterable[RedactedWrite]
    ) -> RunRecord:
        """Return `record` with one counted deferred finding per pattern that fired (section 17a).

        "Redaction events are recorded, never silent -- a redaction produces a counted, visible
        finding on the run record, so an operator can see that secret-shaped content was present
        and neutralized." A redaction never blocks, so the findings are `MEDIUM`/`DEFERRED`, and
        their ids carry a per-record ordinal so republishing a redacted document appends a new
        visible event instead of colliding with the previous one.

        The record is rebuilt through full validation rather than mutated: `RunRecord` is a closed
        schema and an appended finding has to satisfy it like any other.
        """
        payload = json.loads(record.model_dump_json())
        deferred: list[dict[str, Any]] = list(payload["deferred_findings"])
        ordinal = sum(
            1 for finding in record.deferred_findings if finding.finding_id.startswith("redaction-")
        )
        for write in writes:
            reference = write.relative_path or Path(write.path).name
            for redaction in write.findings:
                ordinal += 1
                finding = Finding(
                    finding_id=f"redaction-{ordinal:04d}-{redaction.pattern_name}",
                    severity=FindingSeverity.MEDIUM,
                    title="Secret-shaped content redacted before persistence",
                    summary=(
                        f"{redaction.occurrences} occurrence(s) of the "
                        f"{redaction.pattern_name} pattern were redacted from {reference} before "
                        "it was written; the original bytes were discarded, not encoded. "
                        "Redaction is defense in depth and not proof that the artifact is clean."
                    ),
                    status=FindingStatus.DEFERRED,
                )
                deferred.append(json.loads(finding.model_dump_json()))
        payload["deferred_findings"] = deferred
        try:
            return RunRecord.model_validate_json(json.dumps(payload))
        except ValidationError as exc:
            raise StateCorrupted(
                f"The redaction findings could not be recorded on run {record.run_id}: {exc}"
            ) from exc

    # -- reading ------------------------------------------------------------------------

    def exists(self) -> bool:
        """Whether a published `state.json` is present. An orphan temp file is not one."""
        return self.state_path.is_file()

    def load(self) -> RunRecord:
        """Read and validate `state.json`, fail-closed at every step (section 11).

        Four refusals in order, none of which has a best-effort branch: the file must be a
        bounded, no-follow-openable regular file; it must be UTF-8; it must be JSON with no
        duplicate key at any depth; and its `schema_version` must be one this build understands,
        checked **before** model validation so an unknown version is
        :class:`StateSchemaUnknown` rather than an incidental schema error.
        """
        payload = _read_bounded(self.state_path, MAX_STATE_BYTES)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StateCorrupted(f"{self.state_path} is not valid UTF-8: {exc}") from exc
        try:
            document = _loads_rejecting_duplicate_keys(text)
        except _DuplicateJSONKeyError as exc:
            raise StateCorrupted(
                f"{self.state_path} carries a duplicate JSON object key {exc.key!r}; an ambiguous "
                "record has no single correct reading and is refused rather than guessed at"
            ) from exc
        except ValueError as exc:
            raise StateCorrupted(f"{self.state_path} is not valid JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise StateCorrupted(f"{self.state_path} is not a JSON object")

        version = document.get("schema_version")
        if version != STATE_SCHEMA_VERSION:
            raise StateSchemaUnknown(
                f"{self.state_path} carries schema_version {version!r}; this build understands "
                f"only {STATE_SCHEMA_VERSION}, and an unknown version is a hard refusal rather "
                "than a best-effort read"
            )
        try:
            return RunRecord.model_validate_json(text)
        except ValidationError as exc:
            raise StateCorrupted(f"{self.state_path} is not a valid run record: {exc}") from exc

    # -- section 13 ---------------------------------------------------------------------

    def resume(self, evidence: RepositoryEvidence) -> ResumeDecision:
        """Decide how the run continues, reconciling recorded evidence before any repetition.

        Section 13's order is the order here. The durable record is read first, which is where an
        unknown schema version stops the run. Then the three section 4 pins that this layer can
        check against a single independent observation -- repository identity, branch and `HEAD`
        -- are re-verified and any drift is a refusal, not a re-binding. Only then is the
        question of repeating a side effect asked, and it is answered by reconciling what the
        record says was in flight against what the worktree actually shows.

        The remaining section 4 conditions -- stage authorization, the governance checks, plan
        coverage, the configuration and the run lock -- are re-verified by the application that
        owns each of them. This method deliberately does not restate their answers: it takes one
        observation it was handed and reads one file, and it invokes nothing.

        Nothing is written. Two consecutive calls with no intervening change return equal
        decisions and leave the run directory byte-identical, which is section 13's "running
        `resume` twice with no intervening change is a no-op success".
        """
        record = self.load()

        drifts: list[RepositoryDrift] = []
        if record.repository_identity != evidence.repository_identity:
            drifts.append(
                RepositoryDrift(
                    aspect="repository_identity",
                    stop_reason=StopReason.REPOSITORY_IDENTITY_MISMATCH,
                    expected=record.repository_identity,
                    observed=evidence.repository_identity,
                )
            )
        if record.expected_branch != evidence.branch:
            drifts.append(
                RepositoryDrift(
                    aspect="branch",
                    stop_reason=StopReason.BRANCH_MISMATCH,
                    expected=record.expected_branch,
                    observed=evidence.branch,
                )
            )
        if record.baseline_sha != evidence.head_sha:
            drifts.append(
                RepositoryDrift(
                    aspect="head_sha",
                    stop_reason=StopReason.HEAD_DRIFT,
                    expected=record.baseline_sha,
                    observed=evidence.head_sha,
                )
            )
        if drifts:
            described = ", ".join(
                f"{drift.aspect}: expected {drift.expected}, observed {drift.observed}"
                for drift in drifts
            )
            raise ResumeRefused(
                f"Run {record.run_id} cannot resume: the repository is not where the run left it "
                f"({described})",
                drift=drifts,
            )

        observed = list(evidence.changed_paths)
        unaccounted = sorted(set(observed) - set(record.changed_paths))
        action, reason, moved = self._reconcile(record, unaccounted, evidence)
        return ResumeDecision(
            record=record,
            action=action,
            reason=reason,
            observed_changed_paths=observed,
            unaccounted_changed_paths=unaccounted,
            fingerprint_changed_paths=moved,
        )

    def _reconcile(
        self, record: RunRecord, unaccounted: Sequence[str], evidence: RepositoryEvidence
    ) -> tuple[ResumeAction, str, list[str]]:
        """Reconcile the recorded invocation evidence against the repository (section 13).

        A provider invocation counts as in flight when the run stopped in one of the four states
        one can be observed in and the most recent provider run has no `completed_at`. That pair
        is the persisted operation evidence `MACHINE_GATES.md` section 2a requires be consulted
        before repetition; appearance alone -- being in `IMPLEMENTING`, say -- never decides it.

        If nothing was in flight the run simply continues, and nothing is fingerprinted: resume
        is read-only either way, and a run with no unresolved side effect has nothing to prove.

        If something was in flight, three questions are asked and every one of them must clear
        before the invocation may be repeated:

        1. does the worktree carry a changed path the record never knew about?
        2. is there a durable pre-invocation fingerprint bound to *this* invocation?
        3. does that fingerprint still describe the repository, byte for byte?

        Question 1 alone was the whole of the original reconciliation, and it is not sufficient:
        it compares path **names**, so a provider that rewrote the contents of a file the record
        already listed as changed produced an empty unaccounted set and the invocation was
        repeated on an effect that had already landed. Question 3 is what closes that: content
        digests see the rewrite, the deletion of a known path and the arrival of a new one alike.

        Question 2 fails closed on purpose. No fingerprint -- none written, one left over from an
        earlier invocation, or one that could not be read -- is *absence of evidence*, and this
        is the one decision in the module that may never treat that as evidence of absence. The
        conservative direction is cheap in the same asymmetry as before: a false
        `RECONCILE_REQUIRED` costs an operator one explicit command, a false `REINVOKE_PROVIDER`
        costs a duplicated side effect on evidence nobody checked.
        """
        in_flight = (
            record.workflow_state in _PROVIDER_IN_FLIGHT_STATES
            and bool(record.provider_runs)
            and record.provider_runs[-1].completed_at is None
        )
        if not in_flight:
            return (
                ResumeAction.CONTINUE,
                f"No provider invocation was in flight at {record.workflow_state}; the run "
                "continues from its recorded state without repeating anything.",
                [],
            )
        invocation = record.provider_runs[-1]
        intent = self.load_provider_intent()
        bound = intent if intent is not None and intent.sequence == invocation.sequence else None
        current = fingerprint_repository(
            self._repository_root,
            evidence,
            also=bound.fingerprint.path_digests if bound is not None else (),
        )
        moved = fingerprint_delta(bound.fingerprint, current) if bound is not None else []
        if unaccounted:
            return (
                ResumeAction.RECONCILE_REQUIRED,
                f"Provider invocation {invocation.sequence} ({invocation.role}) was in flight and "
                f"the worktree carries {len(unaccounted)} changed path(s) the record does not "
                "account for, so its effect must be reconciled before it is repeated.",
                moved,
            )
        if bound is None:
            return (
                ResumeAction.RECONCILE_REQUIRED,
                f"Provider invocation {invocation.sequence} ({invocation.role}) was in flight and "
                "no durable pre-invocation fingerprint is bound to it, so whether it had an "
                "effect cannot be proved either way and it must be reconciled before it is "
                "repeated.",
                moved,
            )
        if moved:
            return (
                ResumeAction.RECONCILE_REQUIRED,
                f"Provider invocation {invocation.sequence} ({invocation.role}) was in flight and "
                f"the content of {len(moved)} fingerprinted path(s) has changed since it was "
                "recorded, so its effect must be reconciled before it is repeated.",
                moved,
            )
        return (
            ResumeAction.REINVOKE_PROVIDER,
            f"Provider invocation {invocation.sequence} ({invocation.role}) was in flight and the "
            "durable pre-invocation fingerprint still describes the repository byte for byte, so "
            "repeating it repeats no effect.",
            moved,
        )
