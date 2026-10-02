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

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Final, TypeVar

from pydantic import Field, ValidationError, field_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.events import (
    EVENTS_DIRECTORY,
    MAX_LIFECYCLE_DOCUMENT_BYTES,
    PUBLICATION_WITNESS_FILE_NAME,
    ChainEntry,
    DurableEvidenceReference,
    EventChainBroken,
    EventConflict,
    EventPins,
    EventStore,
    EvidenceKind,
    EvidenceRoot,
    FoldState,
    LifecycleEvent,
    LifecycleSchemaUnknown,
    OperationRecordConflict,
    OperationRecordInvalid,
    ProjectionStatus,
    StoredChain,
    check_operation_artifact,
    check_witness,
    classify_run_evidence_path,
    fold_step,
    model_bytes,
    parse_event_bytes,
    parse_event_file_name,
    parse_witness_bytes,
    projection_bytes,
    projection_status,
    stage_start_reference_path,
    strict_json_loads,
)
from ai_workflow_engine.milestone_runner.git_inspect import (
    RepositoryDrift,
    RepositoryEvidence,
    derive_repository_identity,
)
from ai_workflow_engine.milestone_runner.lock import RUN_LOCK_FILE_NAME, RunLock
from ai_workflow_engine.milestone_runner.models import (
    EVENT_BACKED_STATE_SCHEMA_VERSION,
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
from ai_workflow_engine.milestone_runner.operations import (
    APPLIED_FILE_NAME,
    ARTIFACT_MODELS,
    OPERATION_ARTIFACT_PATH_RE,
    OperationPins,
    applied_receipt,
    operation_artifact_path,
)
from ai_workflow_engine.milestone_runner.policy import (
    MAX_POLICY_INPUT_BYTES,
    MAX_STAGE_START_BYTES,
    MAX_STAGE_START_REFERENCE_BYTES,
    EffectiveStageExecutionPolicy,
    StageStartAuthorization,
    StageStartBinding,
    StageStartConsumptionWitness,
    StageStartPointer,
    authority_json_bytes,
)
from ai_workflow_engine.successor_planning.redaction import RedactionFinding, redact_text

#: Section 11's external artifact root, shared with the plan root `plan.py` derives.
ARTIFACT_ROOT_DIRECTORY: Final = ".ai-workflow-engine"
MILESTONE_RUNS_DIRECTORY: Final = "milestone-runs"

#: Section 11's per-run layout. Every one of these is read and written by exact name.
STATE_FILE_NAME: Final = "state.json"
POLICY_FILE_NAME: Final = "policy.json"
STAGE_STARTS_DIRECTORY: Final = "stage-starts"
_AUTHORITY_ID_RE = re.compile(r"[0-9a-f]{64}")
_PolicyModel = TypeVar("_PolicyModel", bound=MilestoneRunnerModel)
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


class PolicyDigestMismatch(StateError):
    """A frozen policy is absent, malformed or differs from its exact-byte pin."""

    stop_reason: StopReason | None = StopReason.POLICY_DIGEST_MISMATCH


class PolicyBindingMismatch(StateError):
    """A governed record belongs to a different run directory."""

    stop_reason: StopReason | None = StopReason.POLICY_BINDING_MISMATCH


class AuthorityArtifactInvalid(StateError):
    """Untrusted authority could not be read or validated; no raw input is exposed."""


class ExclusivePublicationConflict(StatePublicationFailure):
    """An immutable artifact already exists with different or untrusted bytes."""


class ExclusiveOutcome(StrEnum):
    CREATED = "CREATED"
    IDENTICAL_EXISTS = "IDENTICAL_EXISTS"


class PublicationOutcome(StrEnum):
    """AUTO-018 section 7.5's typed publication outcomes.

    `CREATED` and `IDENTICAL_EXISTS` describe content placement; neither is a durability verdict.
    `DURABLE` is returned only once the file and directory barriers succeeded on the verified
    descriptors. `NOT_PUBLISHED` requires proof that no canonical publication occurred, and is
    what :class:`StatePublicationFailure` means. Anything else is `UNCERTAIN`.
    """

    NOT_PUBLISHED = "NOT_PUBLISHED"
    DURABLE = "DURABLE"
    UNCERTAIN = "UNCERTAIN"


class PublicationUncertain(StateError):
    """Canonical bytes may be visible, but a required durability barrier failed (section 7.5).

    Never a no-effect write failure: it is deliberately not a :class:`StatePublicationFailure`,
    whose meaning is that nothing reached a canonical path. It carries what is known about the
    artifact without needing another durable write to report it.
    """

    stop_reason: StopReason | None = StopReason.PUBLICATION_UNCERTAIN

    def __init__(
        self,
        message: str,
        *,
        address: str,
        expected_sha256: str | None = None,
        barrier: str,
    ) -> None:
        super().__init__(message)
        self.address = address
        self.expected_sha256 = expected_sha256
        self.barrier = barrier


class EvidenceUnavailable(StateError):
    """A relied-upon durable artifact is missing, unreadable or differs from its digest."""


class LifecycleReadContention(StateError):
    """An unlocked reader could not obtain a consistent view while a writer was active.

    Retryable. No write or workflow action follows it; a mutating command establishes its final
    integrity verdict under the held lock (AUTO-018 section 6).
    """

    stop_reason: StopReason | None = StopReason.LOCK_CONTENTION


class LifecycleAuthorityMismatch(AuthorityArtifactInvalid):
    """An authority artifact an event bound no longer matches its digest. Events never heal it."""

    def __init__(self, message: str, *, stop_reason: StopReason) -> None:
        super().__init__(message)
        self.stop_reason = stop_reason


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


@dataclass(frozen=True, slots=True)
class DurableTarget:
    """Where one governed publication lands, addressed through a verified hold (AUTO-018 7.4).

    `parts` are the directories below the repository-scoped storage root, in order, and `name`
    the canonical file name. Every descriptor a publication uses is derived from the lock's
    retained storage-root descriptor, never from an independently reopened pathname, and
    :meth:`guard` re-verifies the hold's ownership -- and that every opened child directory is
    still the canonical directory at its name -- before creating a directory, opening a write
    target, linking or replacing a canonical file, and around every durability barrier.

    `create_parents` is false for a writer whose directories already exist by construction (the
    baseline run-directory writers): a missing directory stays a refusal there, exactly as before,
    rather than being recreated.
    """

    lock: RunLock
    storage_root: Path
    repository_root: Path | None
    parts: tuple[str, ...]
    name: str
    create_parents: bool = True

    @property
    def address(self) -> str:
        return "/".join((*self.parts, self.name))

    def guard(self, descriptors: Sequence[int] = ()) -> None:
        """Re-verify the hold and the namespace binding of every child descriptor opened so far.

        A renamed-away or replaced child directory means the write would land in a detached
        directory; that is a lost ownership context (section 7.4), never a success.
        """
        self.lock.verify_ownership(
            storage_root=self.storage_root, repository_root=self.repository_root
        )
        if descriptors:
            self.lock.verify_descriptor_ancestry(
                storage_root=self.storage_root,
                names=self.parts[: len(descriptors)],
                descriptors=descriptors,
            )

    def open_parent(self, *, create: bool = True) -> tuple[list[int], int]:
        """Walk `parts` no-follow from the retained root, creating (and fsyncing) as needed.

        Returns the descriptors to close and the parent descriptor, which is the root's own
        retained descriptor -- never closed by a caller -- when `parts` is empty. A directory
        found already present is *not* assumed durable: whether an earlier creation's parent
        fsync succeeded is unknowable from its visibility (section 7.5), so every publication
        re-establishes the whole ancestry with :func:`_fsync_ancestry` before it succeeds.
        """
        create = create and self.create_parents
        self.guard()
        current = self.lock.storage_root_descriptor(storage_root=self.storage_root)
        descriptors: list[int] = []
        try:
            for part in self.parts:
                try:
                    opened = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    self.guard(descriptors)
                    try:
                        os.mkdir(part, DIRECTORY_MODE, dir_fd=current)
                    except FileExistsError:
                        pass
                    opened = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                    )
                    # A new directory entry is not durable until its parent is fsynced.
                    os.fsync(current)
                descriptors.append(opened)
                current = opened
                self.guard(descriptors)
        except BaseException:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            raise
        return descriptors, current

    def ancestry_descriptors(self, descriptors: Sequence[int]) -> list[int]:
        """The parent and every ancestor up to the storage root, nearest first."""
        root = self.lock.storage_root_descriptor(storage_root=self.storage_root)
        return [*reversed(descriptors), root]


def _fsync_ancestry(target: DurableTarget, descriptors: Sequence[int]) -> None:
    """Fsync the parent and every ancestor up to the storage root, then re-verify the binding.

    Section 7.5 / R04: a directory left visible by an earlier publication whose parent fsync
    failed is indistinguishable from a durable one, so no publication or confirmation succeeds
    until the whole addressed ancestry has passed its barrier on the verified descriptors.
    """
    for directory in target.ancestry_descriptors(descriptors):
        os.fsync(directory)
    target.guard(descriptors)


def publish_atomically(path: Path, payload: bytes, *, target: DurableTarget | None = None) -> None:
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

    With a :class:`DurableTarget` (AUTO-018 sections 7.4 and 7.5) every step runs on descriptors
    derived from the verified hold, ownership is re-verified before and after the replace, and a
    failed barrier after the replace is :class:`PublicationUncertain` -- never swallowed and never
    reported as a no-effect failure.

    This is the mechanism, not the boundary. Section 17a's boundary is
    :func:`write_redacted_artifact`, which is the only caller of this function in the package.
    """
    if target is not None:
        descriptors: list[int] = []
        temporary = Path(f"{TEMP_FILE_PREFIX}{uuid.uuid4().hex}")
        replaced = False
        created = False
        parent = -1
        try:
            descriptors, parent = target.open_parent()
            target.guard(descriptors)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                ARTIFACT_MODE,
                dir_fd=parent,
            )
            created = True
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
                inode = os.fstat(descriptor).st_ino
            finally:
                os.close(descriptor)
            target.guard(descriptors)
            os.replace(temporary, target.name, src_dir_fd=parent, dst_dir_fd=parent)
            replaced = True
            target.guard(descriptors)
            _fsync_ancestry(target, descriptors)
            if os.stat(target.name, dir_fd=parent, follow_symlinks=False).st_ino != inode:
                raise PublicationUncertain(
                    f"{target.address} no longer names the replaced file",
                    address=target.address,
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                    barrier="canonical_inode_recheck",
                )
            return
        except OSError as exc:
            if replaced:
                raise PublicationUncertain(
                    f"{target.address} was replaced but its directory barrier failed: "
                    f"{exc.strerror}",
                    address=target.address,
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                    barrier="directory_fsync",
                ) from None
            raise StatePublicationFailure(
                f"{target.address} could not be published: {exc.strerror}"
            ) from None
        finally:
            if created and not replaced and parent >= 0:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except OSError:
                    pass
            for opened in reversed(descriptors):
                os.close(opened)

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


def publish_exclusively(
    path: Path, payload: bytes, *, target: DurableTarget | None = None
) -> ExclusiveOutcome:
    """Publish without replacement; unlink the private temporary in every outcome.

    Only the redaction boundary calls this primitive. A hard-link creation is the
    atomic absence check: there is no check-then-replace window.

    With a :class:`DurableTarget`, the parent descriptor is derived from the verified hold,
    ownership is re-verified around the link, and success means `DURABLE`: the file and every
    directory barrier succeeded. The identical-existing branch is not durable merely because the
    bytes compare equal -- its file and directory are fsynced too, or it is
    :class:`PublicationUncertain`. A barrier failing after the link made the bytes visible is
    `UNCERTAIN`, never a no-effect failure.
    """
    descriptors: list[int] = []
    temporary = f"{TEMP_FILE_PREFIX}{uuid.uuid4().hex}"
    created = False
    visible = False
    parent = -1
    name = path.name if target is None else target.name
    try:
        if target is None:
            absolute = path if path.is_absolute() else Path.cwd() / path
            parent = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(parent)
            for part in absolute.parts[1:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                descriptors.append(parent)
        else:
            descriptors, parent = target.open_parent()
            target.guard(descriptors)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            ARTIFACT_MODE,
            dir_fd=parent,
        )
        created = True
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
            inode = os.fstat(descriptor).st_ino
        finally:
            os.close(descriptor)
        if target is not None:
            target.guard(descriptors)
        try:
            os.link(
                temporary,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except FileExistsError:
            try:
                descriptor = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
                )
                try:
                    existing = _read_authority_descriptor(descriptor, MAX_ARTIFACT_BYTES)
                finally:
                    os.close(descriptor)
            except (OSError, StateError):
                raise ExclusivePublicationConflict(
                    "Existing immutable artifact is invalid"
                ) from None
            if existing != payload:
                raise ExclusivePublicationConflict("Existing immutable artifact differs") from None
            if target is not None:
                _confirm_identical_existing(target, descriptors, parent, name, payload)
            return ExclusiveOutcome.IDENTICAL_EXISTS
        visible = True
        if target is not None:
            target.guard(descriptors)
            _fsync_ancestry(target, descriptors)
        else:
            os.fsync(parent)
        if target is not None:
            if os.stat(name, dir_fd=parent, follow_symlinks=False).st_ino != inode:
                raise PublicationUncertain(
                    f"{target.address} no longer names the linked file",
                    address=target.address,
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                    barrier="canonical_inode_recheck",
                )
        return ExclusiveOutcome.CREATED
    except OSError as exc:
        if visible and target is not None:
            raise PublicationUncertain(
                f"{target.address} was linked but its directory barrier failed: {exc.strerror}",
                address=target.address,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                barrier="directory_fsync",
            ) from None
        raise StatePublicationFailure("Exclusive publication failed") from None
    finally:
        if created:
            try:
                os.unlink(temporary, dir_fd=parent)
            except OSError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _confirm_identical_existing(
    target: DurableTarget, descriptors: Sequence[int], parent: int, name: str, payload: bytes
) -> None:
    """Section 7.5: an identical existing artifact is durable only after its own barriers.

    The file, its parent and every ancestor up to the storage root: the artifact's visibility
    says nothing about whether the publication that made it visible ever confirmed them.
    """
    try:
        target.guard(descriptors)
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_ancestry(target, descriptors)
    except OSError as exc:
        raise PublicationUncertain(
            f"{target.address} exists with identical bytes, but its durability could not be "
            f"confirmed: {exc.strerror}",
            address=target.address,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            barrier="identical_existing_fsync",
        ) from None


def confirm_durable(
    target: DurableTarget, *, expected_sha256: str, ceiling: int = MAX_ARTIFACT_BYTES
) -> None:
    """Confirm existing bytes durable under the current verified hold (AUTO-018 section 7.5).

    Reopens through the descriptor context, strictly checks the bytes against their digest,
    fsyncs the exact regular-file descriptor, its parent and every ancestor up to the storage
    root, and rechecks the canonical inode before reporting success. It rewrites nothing:
    content, identity and modification times are untouched. A missing or conflicting file keeps
    its typed refusal (:class:`EvidenceUnavailable`); a failed barrier is
    :class:`PublicationUncertain`, and nothing reports success from byte equality alone.
    """
    descriptors: list[int] = []
    try:
        try:
            descriptors, parent = target.open_parent(create=False)
            descriptor = os.open(
                target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
        except FileNotFoundError:
            raise EvidenceUnavailable(f"{target.address} is missing") from None
        except OSError as exc:
            raise EvidenceUnavailable(
                f"{target.address} cannot be reopened safely: {exc.strerror}"
            ) from None
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode) or status.st_size > ceiling:
                raise EvidenceUnavailable(f"{target.address} is not a bounded regular file")
            digest = hashlib.sha256()
            remaining = ceiling + 1
            while remaining:
                chunk = os.read(descriptor, min(remaining, _FINGERPRINT_CHUNK_BYTES))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
            if remaining == 0 or digest.hexdigest() != expected_sha256:
                raise EvidenceUnavailable(f"{target.address} differs from its recorded digest")
            try:
                target.guard(descriptors)
                os.fsync(descriptor)
                _fsync_ancestry(target, descriptors)
                current = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
            except OSError as exc:
                raise PublicationUncertain(
                    f"{target.address} is intact but its durability could not be confirmed: "
                    f"{exc.strerror}",
                    address=target.address,
                    expected_sha256=expected_sha256,
                    barrier="confirmation_fsync",
                ) from None
            if (current.st_dev, current.st_ino) != (status.st_dev, status.st_ino):
                raise PublicationUncertain(
                    f"{target.address} was replaced during confirmation",
                    address=target.address,
                    expected_sha256=expected_sha256,
                    barrier="canonical_inode_recheck",
                )
        finally:
            os.close(descriptor)
    finally:
        for opened in reversed(descriptors):
            os.close(opened)


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
    exclusive_outcome: ExclusiveOutcome | None = None
    #: AUTO-018: the SHA-256 of the final redacted bytes, and -- for a descriptor-bound governed
    #: publication only -- the durability verdict, which is always `DURABLE` when set.
    sha256: str | None = None
    durability: PublicationOutcome | None = None

    @property
    def redacted(self) -> bool:
        """Whether any pattern fired on the way to disk."""
        return bool(self.findings)


def write_redacted_artifact(
    path: Path,
    text: str,
    *,
    relative_path: str | None = None,
    exclusive: bool = False,
    target: DurableTarget | None = None,
    refuse_redaction: bool = False,
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

    `target` makes the publication descriptor-bound and durable (AUTO-018 sections 7.4, 7.5).
    `refuse_redaction` is for integrity-serialized documents whose free text was redacted before
    their digests were computed: if this mandatory final pass would still change a byte, the
    structure or identity would change, so nothing is published.
    """
    reject_symlink_components(path, "The artifact")
    redacted, findings = redact_text(text)
    if refuse_redaction and (findings or redacted != text):
        raise StatePublicationFailure(
            f"{path.name}: the final redaction pass would change integrity-bound bytes, so the "
            "document is refused rather than published with a different identity"
        )
    payload = redacted.encode("utf-8")
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise StatePublicationFailure(
            f"{path} would be {len(payload)} bytes, above the {MAX_ARTIFACT_BYTES}-byte ceiling"
        )
    outcome = None
    if exclusive:
        # Authorization bytes must still validate after the mandatory, lossy redactor.
        if path.parent.name == STAGE_STARTS_DIRECTORY:
            _validate_stage_start_payload(path, payload)
        outcome = publish_exclusively(path, payload, target=target)
    else:
        publish_atomically(path, payload, target=target)
    return RedactedWrite(
        path=str(path),
        relative_path=relative_path,
        byte_count=len(payload),
        findings=list(findings),
        exclusive_outcome=outcome,
        sha256=hashlib.sha256(payload).hexdigest(),
        durability=None if target is None else PublicationOutcome.DURABLE,
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


def next_transcript_sequence(
    transcripts_directory: Path, *, target: "DurableTarget | None" = None
) -> int:
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
    so two allocations never interleave, and passes the hold's `target` so the counter is
    published through the verified ownership context (AUTO-018 section 7.4).
    """
    counter = transcripts_directory / TRANSCRIPT_SEQUENCE_FILE_NAME
    allocated = _read_transcript_sequence(counter) + 1
    if allocated > MAX_TRANSCRIPT_SEQUENCE:
        raise StatePublicationFailure(
            f"{transcripts_directory} has reached the {MAX_TRANSCRIPT_SEQUENCE} transcript ceiling"
        )
    write_redacted_artifact(counter, f"{allocated}\n", target=target)
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


def _read_authority_descriptor(descriptor: int, ceiling: int) -> bytes:
    """Read from an already anchored no-follow file descriptor."""
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode) or status.st_size > ceiling:
        raise AuthorityArtifactInvalid("Authority artifact is not a bounded regular file")
    chunks: list[bytes] = []
    remaining = ceiling + 1
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) > ceiling:
        raise AuthorityArtifactInvalid("Authority artifact exceeds its byte limit")
    return payload


def read_authority_bytes(path: Path, ceiling: int, *, optional: bool = False) -> bytes | None:
    """Read bounded regular-file bytes with each component opened relative and no-follow.

    O_NONBLOCK avoids hanging on a substituted FIFO before the regular-file check.
    Optional means ENOENT only; links, directories and unreadable input always refuse.
    Diagnostics deliberately carry neither the path nor an underlying hostile error.
    """
    descriptors: list[int] = []
    try:
        absolute = path if path.is_absolute() else Path.cwd() / path
        descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        for part in absolute.parts[1:-1]:
            descriptor = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            descriptors.append(descriptor)
        descriptor = os.open(
            absolute.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
        )
        descriptors.append(descriptor)
        return _read_authority_descriptor(descriptor, ceiling)
    except FileNotFoundError:
        if optional:
            return None
        raise AuthorityArtifactInvalid("Required authority artifact is absent") from None
    except (OSError, ValueError):
        raise AuthorityArtifactInvalid("Authority artifact cannot be read safely") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _validate_authority_payload(
    payload: bytes, model: type[_PolicyModel], *, canonical: bool = True
) -> _PolicyModel:
    """Validate hostile JSON before exposing a model or a value usable as a path."""
    try:
        document = _loads_rejecting_duplicate_keys(payload.decode("utf-8", errors="strict"))
        if not isinstance(document, dict):
            raise ValueError("object required")
        if type(document.get("schema_version")) is not int or document["schema_version"] != 2:
            raise ValueError("schema version invalid")
        result = model.model_validate_json(payload)
        if canonical and authority_json_bytes(result.model_dump(mode="json")) != payload:
            raise ValueError("canonical bytes required")
        return result
    except (ValueError, RecursionError):
        raise AuthorityArtifactInvalid(
            "Authority artifact has invalid content or integrity"
        ) from None


def load_policy_input(
    path: Path, model: type[_PolicyModel], *, optional: bool = False
) -> tuple[_PolicyModel | None, str | None]:
    """Read OWNER-authored inputs, pinning exact bytes rather than normalized JSON."""
    payload = read_authority_bytes(path, MAX_POLICY_INPUT_BYTES, optional=optional)
    if payload is None:
        return None, None
    return (
        _validate_authority_payload(payload, model, canonical=False),
        hashlib.sha256(payload).hexdigest(),
    )


def _validate_stage_start_payload(path: Path, payload: bytes) -> MilestoneRunnerModel:
    """Validate the closed exact-name Stage Start layout, including its filename pin."""
    if path.name.startswith("key-") and path.name.endswith(".json"):
        if len(payload) > MAX_STAGE_START_REFERENCE_BYTES:
            raise AuthorityArtifactInvalid("Stage Start pointer exceeds its byte limit")
        pointer = _validate_authority_payload(payload, StageStartPointer)
        if path.name != f"key-{pointer.stage_start_key}.json":
            raise AuthorityArtifactInvalid("Stage Start pointer filename mismatch")
        return pointer
    if path.name.endswith(".consumed.json"):
        if len(payload) > MAX_STAGE_START_REFERENCE_BYTES:
            raise AuthorityArtifactInvalid("Stage Start witness exceeds its byte limit")
        witness = _validate_authority_payload(payload, StageStartConsumptionWitness)
        if path.name != f"{witness.stage_start_id}.consumed.json":
            raise AuthorityArtifactInvalid("Stage Start witness filename mismatch")
        return witness
    if path.name.endswith(".binding.json"):
        if len(payload) > MAX_STAGE_START_REFERENCE_BYTES:
            raise AuthorityArtifactInvalid("Stage Start binding exceeds its byte limit")
        binding = _validate_authority_payload(payload, StageStartBinding)
        if path.name != f"{binding.stage_start_id}.binding.json":
            raise AuthorityArtifactInvalid("Stage Start binding filename mismatch")
        return binding
    if len(payload) > MAX_STAGE_START_BYTES:
        raise AuthorityArtifactInvalid("Stage Start authorization exceeds its byte limit")
    authorization = _validate_authority_payload(payload, StageStartAuthorization)
    if path.name != f"{authorization.stage_start_id}.json":
        raise AuthorityArtifactInvalid("Stage Start authorization filename mismatch")
    return authorization


class StageStartStore:
    """Exact-name immutable Stage Start artifacts under a repository-scoped root.

    Construction is inert. Read methods make all hostile-input checks themselves so
    the application can select the applicable authority-matrix refusal.
    """

    def __init__(self, artifact_root: Path, repository_root: Path) -> None:
        self.artifact_root = artifact_root
        self.repository_root = repository_root

    @property
    def directory(self) -> Path:
        return self.artifact_root / STAGE_STARTS_DIRECTORY

    def _path(
        self,
        identifier: str,
        *,
        pointer: bool = False,
        binding: bool = False,
        witness: bool = False,
    ) -> Path:
        if _AUTHORITY_ID_RE.fullmatch(identifier) is None:
            raise AuthorityArtifactInvalid("Stage Start identifier is invalid")
        try:
            reject_repository_containment(self.artifact_root, self.repository_root)
        except StateError:
            raise AuthorityArtifactInvalid("Stage Start root is invalid") from None
        name = (
            f"key-{identifier}.json"
            if pointer
            else (
                f"{identifier}.binding.json"
                if binding
                else f"{identifier}.consumed.json" if witness else f"{identifier}.json"
            )
        )
        return self.directory / name

    def read_pointer(self, key: str) -> StageStartPointer | None:
        path = self._path(key, pointer=True)
        payload = read_authority_bytes(path, MAX_STAGE_START_REFERENCE_BYTES, optional=True)
        if payload is None:
            return None
        result = _validate_authority_payload(payload, StageStartPointer)
        if result.stage_start_key != key:
            raise AuthorityArtifactInvalid("Stage Start pointer key mismatch")
        return result

    def read_authorization(self, identifier: str) -> StageStartAuthorization | None:
        path = self._path(identifier)
        payload = read_authority_bytes(path, MAX_STAGE_START_BYTES, optional=True)
        if payload is None:
            return None
        result = _validate_authority_payload(payload, StageStartAuthorization)
        if result.stage_start_id != identifier:
            raise AuthorityArtifactInvalid("Stage Start authorization ID mismatch")
        return result

    def read_binding(self, identifier: str) -> StageStartBinding | None:
        path = self._path(identifier, binding=True)
        payload = read_authority_bytes(path, MAX_STAGE_START_REFERENCE_BYTES, optional=True)
        if payload is None:
            return None
        result = _validate_authority_payload(payload, StageStartBinding)
        if result.stage_start_id != identifier:
            raise AuthorityArtifactInvalid("Stage Start binding ID mismatch")
        return result

    def read_witness(self, identifier: str) -> StageStartConsumptionWitness | None:
        path = self._path(identifier, witness=True)
        payload = read_authority_bytes(path, MAX_STAGE_START_REFERENCE_BYTES, optional=True)
        if payload is None:
            return None
        result = _validate_authority_payload(payload, StageStartConsumptionWitness)
        if result.stage_start_id != identifier:
            raise AuthorityArtifactInvalid("Stage Start witness ID mismatch")
        return result

    def publish_witness(
        self, witness: StageStartConsumptionWitness, *, lock: RunLock
    ) -> RedactedWrite:
        return self._publish(self._path(witness.stage_start_id, witness=True), witness, lock=lock)

    def _publish(
        self, path: Path, document: MilestoneRunnerModel, *, lock: RunLock
    ) -> RedactedWrite:
        if (
            not lock.is_held
            or lock.artifact_root != self.artifact_root
            or lock.repository_identity != self.artifact_root.name
        ):
            raise StatePublicationFailure(
                "Stage Start publication requires the repository run lock"
            )
        reject_symlink_components(path, "The Stage Start artifact")
        reject_repository_containment(self.artifact_root, self.repository_root)
        payload = authority_json_bytes(document.model_dump(mode="json"))
        _validate_stage_start_payload(path, payload)
        _create_directory(self.directory)
        reject_symlink_components(path, "The Stage Start artifact")
        # AUTO-018 section 7.4: a governed authority write is descriptor-bound to the verified
        # hold, and section 7.5: it returns only once durable.
        target = DurableTarget(
            lock=lock,
            storage_root=self.artifact_root,
            repository_root=self.repository_root,
            parts=(STAGE_STARTS_DIRECTORY,),
            name=path.name,
        )
        return write_redacted_artifact(path, payload.decode("utf-8"), exclusive=True, target=target)

    def publish_authorization(
        self, authorization: StageStartAuthorization, *, lock: RunLock
    ) -> RedactedWrite:
        return self._publish(self._path(authorization.stage_start_id), authorization, lock=lock)

    def publish_pointer(self, pointer: StageStartPointer, *, lock: RunLock) -> RedactedWrite:
        return self._publish(self._path(pointer.stage_start_key, pointer=True), pointer, lock=lock)

    def publish_binding(self, binding: StageStartBinding, *, lock: RunLock) -> RedactedWrite:
        return self._publish(self._path(binding.stage_start_id, binding=True), binding, lock=lock)


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
    def policy_path(self) -> Path:
        return self._run_directory / POLICY_FILE_NAME

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
        # AUTO-018 section 7.4 (R01): `is_held` and an equal identity string are necessary, not
        # sufficient. The hold must still own this store's canonical storage root (and, when it
        # binds one, the target repository root); a lock at another root, a released or replaced
        # hold, or a replaced root refuses here, before any byte is written.
        lock.verify_ownership(
            storage_root=self.artifact_root, repository_root=self._repository_root
        )

    def _held_target(self, lock: RunLock, name: str, *directories: str) -> DurableTarget:
        """A descriptor-bound target in this run's existing directory, through `lock`'s hold.

        Every shared run-directory writer publishes through this, so its parent descriptors come
        from the verified ownership context and its success is re-verified after publication.
        The directories exist by construction (:meth:`pin`), so a missing one stays a refusal.
        """
        return DurableTarget(
            lock=lock,
            storage_root=self.artifact_root,
            repository_root=self._repository_root,
            parts=(self._run_id, *directories),
            name=name,
            create_parents=False,
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
        if self.lifecycle_present():
            # INV-018-05: an event-backed run's state.json is a cache of verified events; no
            # state-only write may advance it.
            raise StatePublicationFailure(
                f"Run {self._run_id} is event-backed; only a verified folded projection is "
                "published for it"
            )
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
            target=self._held_target(lock, STATE_FILE_NAME),
        )

    def publish_policy(
        self, policy: EffectiveStageExecutionPolicy, *, lock: RunLock
    ) -> RedactedWrite:
        """Freeze canonical policy bytes exclusively, under the repository run lock."""
        self._require_lock(lock)
        if policy.repository_identity != self.repository_id:
            raise PolicyDigestMismatch("Policy repository does not match the run store")
        target = DurableTarget(
            lock=lock,
            storage_root=self.artifact_root,
            repository_root=self._repository_root,
            parts=(self._run_id,),
            name=POLICY_FILE_NAME,
        )
        try:
            return write_redacted_artifact(
                self.policy_path,
                policy.canonical_bytes().decode("utf-8"),
                relative_path=POLICY_FILE_NAME,
                exclusive=True,
                target=target,
            )
        except ExclusivePublicationConflict:
            raise PolicyDigestMismatch(
                "Frozen policy publication conflicts with existing bytes"
            ) from None

    def load_policy(self, record: RunRecord) -> EffectiveStageExecutionPolicy:
        """Verify exact-byte pin, strict schema and canonical policy on every governed load."""
        try:
            payload = read_authority_bytes(self.policy_path, MAX_STAGE_START_BYTES)
            if payload is None or hashlib.sha256(payload).hexdigest() != record.policy_digest:
                raise AuthorityArtifactInvalid("Policy pin mismatch")
            policy = _validate_authority_payload(payload, EffectiveStageExecutionPolicy)
            if policy.canonical_bytes() != payload:
                raise AuthorityArtifactInvalid("Policy serialization mismatch")
            return policy
        except StateError:
            raise PolicyDigestMismatch(
                "Frozen policy is absent, invalid or differs from its pin"
            ) from None

    def publish_plan_snapshot(self, document: str, *, lock: RunLock) -> RedactedWrite:
        """Publish the resolved plan snapshot (section 11) at `plan.json`.

        A snapshot of what this run resolved, never a source plan and never a path any loader
        reads back as input -- `plan.py` refuses to discover a plan at all, and this file is
        under the artifact root rather than the plan root.
        """
        self._require_lock(lock)
        return write_redacted_artifact(
            self.plan_snapshot_path,
            document,
            relative_path=PLAN_SNAPSHOT_FILE_NAME,
            target=self._held_target(lock, PLAN_SNAPSHOT_FILE_NAME),
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
            target=self._held_target(lock, PROVIDER_INTENT_FILE_NAME),
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
        return next_transcript_sequence(
            self.transcripts_directory,
            target=self._held_target(lock, TRANSCRIPT_SEQUENCE_FILE_NAME, TRANSCRIPTS_DIRECTORY),
        )

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
        name = transcript_name(sequence, moment, label, kind)
        return write_redacted_artifact(
            self.transcripts_directory / name,
            text,
            relative_path=reference,
            target=self._held_target(lock, name, TRANSCRIPTS_DIRECTORY),
        )

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
        """Whether a published run is present. An orphan temp file is not one.

        AUTO-018 section 10.2: an event-backed run is present once its publication witness or its
        event directory exists, even while `state.json` is absent, so `start` can never create a
        second run or consume an authorization again in that gap.
        """
        return self.state_path.is_file() or self.lifecycle_present()

    @property
    def witness_path(self) -> Path:
        return self._run_directory / PUBLICATION_WITNESS_FILE_NAME

    @property
    def events_directory(self) -> Path:
        return self._run_directory / EVENTS_DIRECTORY

    def lifecycle_present(self) -> bool:
        """Whether this run has begun event-backed publication (section 7.1)."""
        return os.path.lexists(self.witness_path) or os.path.lexists(self.events_directory)

    def load(self, *, verify_authority: bool = True) -> RunRecord:
        """Read the authoritative record without a lock (AUTO-016 section 11, AUTO-018 section 6).

        An event-backed run returns the verified fold of its chain and writes nothing; a legacy
        run is read exactly as before.
        """
        if self.lifecycle_present():
            return self.load_lifecycle(verify_authority=verify_authority).record
        return self._load_legacy()

    def load_held(self, lock: RunLock, *, verify_authority: bool = True) -> RunRecord:
        """:meth:`load` for a caller already holding the run lock: descriptor-bound, final."""
        if self.lifecycle_present():
            return self.load_lifecycle(lock=lock, verify_authority=verify_authority).record
        return self._load_legacy()

    def _load_legacy(self) -> RunRecord:
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
        if type(version) is int and version == EVENT_BACKED_STATE_SCHEMA_VERSION:
            # Section 9: complete loss of the event directory for a version-3 record is detected,
            # never read as a state-only run.
            raise EventChainBroken(
                f"{self.state_path} is an event-backed record, but neither its events nor its "
                "publication witness exist"
            )
        if type(version) is not int or version not in {1, STATE_SCHEMA_VERSION}:
            raise StateSchemaUnknown(
                f"{self.state_path} carries schema_version {version!r}; this build understands "
                f"only {STATE_SCHEMA_VERSION}, and an unknown version is a hard refusal rather "
                "than a best-effort read"
            )
        try:
            if version == 1:
                if "policy_digest" in document or "stage_start_id" in document:
                    raise StateCorrupted("A schema-v1 record cannot carry policy fields")
                document.update(
                    schema_version=STATE_SCHEMA_VERSION, policy_digest=None, stage_start_id=None
                )
                text = json.dumps(document)
            record = RunRecord.model_validate_json(text)
        except ValidationError as exc:
            raise StateCorrupted(f"{self.state_path} is not a valid run record: {exc}") from exc
        if record.is_policy_governed:
            if record.run_id != self.run_id:
                raise PolicyBindingMismatch("Governed record does not belong to this run")
            self.load_policy(record)
        return record

    # -- AUTO-018: the event-backed lifecycle -------------------------------------------

    def _open_run_directory(self, lock: RunLock | None) -> tuple[int, int]:
        """Descriptors for this run's directory and its repository-scoped root, never followed.

        Under a held lock both are derived from the hold's retained, verified root descriptor;
        otherwise every component from `/` is opened no-follow, exactly as authority reads are.
        The caller closes both.
        """
        if lock is not None:
            lock.verify_ownership(
                storage_root=self.artifact_root, repository_root=self._repository_root
            )
            root = os.dup(lock.storage_root_descriptor(storage_root=self.artifact_root))
        else:
            root = _open_directory_nofollow(self.artifact_root)
        try:
            run = os.open(self._run_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        except OSError:
            os.close(root)
            raise EventChainBroken(
                f"the run directory of {self._run_id} cannot be opened safely"
            ) from None
        return run, root

    def _read_snapshot(self, run: int) -> StoredChain:
        """One bounded read: the ordered events, the witness and the projection bytes."""
        events: list[tuple[LifecycleEvent, str]] = []
        try:
            directory = os.open(
                EVENTS_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run
            )
        except FileNotFoundError:
            directory = -1
        except OSError:
            raise EventChainBroken("the events directory is not a real directory") from None
        if directory >= 0:
            try:
                for _sequence, _event_type, name in _bounded_event_names(directory):
                    try:
                        payload = _read_named(directory, name, MAX_LIFECYCLE_DOCUMENT_BYTES)
                    except EvidenceUnavailable:
                        raise EventChainBroken(f"event {name} cannot be read safely") from None
                    assert payload is not None
                    events.append(parse_event_bytes(name, payload))
            finally:
                os.close(directory)
        try:
            raw_witness = _read_named(
                run, PUBLICATION_WITNESS_FILE_NAME, MAX_LIFECYCLE_DOCUMENT_BYTES, optional=True
            )
        except EvidenceUnavailable:
            raise EventChainBroken("the publication witness cannot be read safely") from None
        try:
            projection = _read_named(run, STATE_FILE_NAME, MAX_STATE_BYTES, optional=True)
        except EvidenceUnavailable:
            projection = b""
        return StoredChain(
            events=tuple(events),
            witness=None if raw_witness is None else parse_witness_bytes(raw_witness),
            projection=projection,
        )

    def _writer_active(self) -> bool:
        """Whether another hold is active on this repository's run lock (read-side probe only).

        A non-blocking shared `flock` on the existing lock file, released at once. It creates
        nothing and is consulted only after an unlocked reader already saw an inconsistent view.
        """
        try:
            descriptor = os.open(
                self.artifact_root / RUN_LOCK_FILE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )
        except OSError:
            return False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
        finally:
            os.close(descriptor)

    def load_lifecycle(
        self, *, lock: RunLock | None = None, verify_authority: bool = True
    ) -> "LifecycleView":
        """Verify the whole chain and return its fold, writing nothing (sections 6, 7.3, 8.3).

        The chain is streamed (R12): each event file is size-checked before it is read, then
        parsed, hash-verified, folded and cross-checked against its referenced artifacts as it is
        consumed, and its body is dropped; only bounded :class:`ChainEntry` metadata and the fold
        state are retained, and the first invalid event stops the read before any later file is
        opened. Without a lock the read is repeated while the publication witness changes
        underneath it; an inconsistency seen while a writer holds the lock, or while the witness
        moved, is a retryable contention refusal, not a corruption verdict. With the lock the
        verdict is final.
        """
        attempts = 1 if lock is not None else 3
        last: Exception | None = None
        for _ in range(attempts):
            run, root = self._open_run_directory(lock)
            try:
                before = _read_named_or_none(run, PUBLICATION_WITNESS_FILE_NAME)
                try:
                    view = self._stream_verified(run, root, verify_authority=verify_authority)
                except (EventChainBroken, OperationRecordInvalid) as exc:
                    if (
                        lock is None
                        and _read_named_or_none(run, PUBLICATION_WITNESS_FILE_NAME) != before
                    ):
                        last = LifecycleReadContention(
                            f"run {self._run_id}'s publication witness changed during the read"
                        )
                        continue
                    if lock is None and self._writer_active():
                        raise LifecycleReadContention(
                            f"run {self._run_id} is being written; retry the read ({exc})"
                        ) from None
                    raise
                after = _read_named_or_none(run, PUBLICATION_WITNESS_FILE_NAME)
                if lock is None and before != after:
                    last = LifecycleReadContention(
                        f"run {self._run_id}'s publication witness changed during the read"
                    )
                    continue
                return view
            finally:
                os.close(run)
                os.close(root)
        assert last is not None
        raise last

    def _stream_verified(self, run: int, root: int, *, verify_authority: bool) -> "LifecycleView":
        """Stream, verify and fold the chain under `run`, retaining only bounded metadata (R12)."""
        try:
            directory = os.open(
                EVENTS_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run
            )
        except FileNotFoundError:
            raise EventChainBroken(
                f"run {self._run_id} has begun event-backed publication, but no event survives"
            ) from None
        except OSError:
            raise EventChainBroken("the events directory is not a real directory") from None
        state: FoldState | None = None
        entries: list[ChainEntry] = []
        try:
            for _sequence, _event_type, name in _bounded_event_names(directory):
                try:
                    # Bounded: the size is checked on the descriptor before anything is read.
                    payload = _read_named(directory, name, MAX_LIFECYCLE_DOCUMENT_BYTES)
                except EvidenceUnavailable:
                    raise EventChainBroken(f"event {name} cannot be read safely") from None
                assert payload is not None
                event, digest = parse_event_bytes(name, payload)
                del payload
                state = fold_step(state, event, digest)
                if (
                    state.pins.run_id != self._run_id
                    or state.pins.repository_identity != self._repository_id
                ):
                    raise EventChainBroken("the event chain belongs to another run or repository")
                entry = ChainEntry.of(event, digest)
                del event
                for reference in entry.references:
                    if reference.root is EvidenceRoot.REPOSITORY and not verify_authority:
                        continue
                    artifact = self._verify_reference(reference, run, root, state.pins)
                    if artifact is not None:
                        check_operation_artifact(state, reference, artifact)
                entries.append(entry)
        finally:
            os.close(directory)
        if state is None:
            raise EventChainBroken(
                f"run {self._run_id} has begun event-backed publication, but no event survives"
            )
        try:
            raw_witness = _read_named(
                run, PUBLICATION_WITNESS_FILE_NAME, MAX_LIFECYCLE_DOCUMENT_BYTES, optional=True
            )
        except EvidenceUnavailable:
            raise EventChainBroken("the publication witness cannot be read safely") from None
        check_witness(state, None if raw_witness is None else parse_witness_bytes(raw_witness))
        try:
            projection = _read_named(run, STATE_FILE_NAME, MAX_STATE_BYTES, optional=True)
        except EvidenceUnavailable:
            projection = b""
        status = projection_status(state, projection)
        for path in state.prospective_paths:
            _check_prospective_path(run, path)
        missing: list[str] = []
        pins = OperationPins.model_validate(state.pins.model_dump())
        for identifier, (event_id, version, event_sha) in state.causative_events.items():
            causative = entries[version - 1]
            if causative.event_id != event_id:
                raise EventChainBroken("a causative transition is not where the chain says")
            expected = model_bytes(applied_receipt(pins, identifier, causative, event_sha))
            try:
                present = _read_relative(
                    run,
                    operation_artifact_path(identifier, APPLIED_FILE_NAME),
                    MAX_LIFECYCLE_DOCUMENT_BYTES,
                    optional=True,
                )
            except EvidenceUnavailable:
                raise OperationRecordInvalid(
                    f"operation {identifier}'s applied receipt cannot be read"
                ) from None
            if present is None:
                missing.append(identifier)
            elif present != expected:
                raise OperationRecordConflict(
                    f"operation {identifier}'s applied receipt contradicts its causative transition"
                )
        chain = tuple(entries)
        return LifecycleView(
            record=state.record,
            state=state,
            chain=chain,
            projection=status,
            missing_applied=tuple(missing),
            reader=lambda: self._reread_events(chain),
        )

    def _reread_events(self, chain: Sequence[ChainEntry]) -> tuple[tuple[LifecycleEvent, str], ...]:
        """Diagnostic only: re-read the bodies of an already verified chain, digest-checked.

        No load, fold, append or confirmation uses this; it exists for inspection and tests.
        """
        run, root = self._open_run_directory(None)
        try:
            directory = os.open(
                EVENTS_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run
            )
            try:
                events: list[tuple[LifecycleEvent, str]] = []
                for entry in chain:
                    try:
                        payload = _read_named(
                            directory, entry.file_name, MAX_LIFECYCLE_DOCUMENT_BYTES
                        )
                    except EvidenceUnavailable:
                        raise EventChainBroken(f"event {entry.file_name} is unreadable") from None
                    assert payload is not None
                    event, digest = parse_event_bytes(entry.file_name, payload)
                    if digest != entry.sha256:
                        raise EventChainBroken(f"event {entry.file_name} changed since verified")
                    events.append((event, digest))
                return tuple(events)
            finally:
                os.close(directory)
        finally:
            os.close(run)
            os.close(root)

    def _verify_reference(
        self, reference: DurableEvidenceReference, run: int, root: int, pins: EventPins
    ) -> MilestoneRunnerModel | None:
        """Section 8.3: an asserted artifact exists, is safely readable and matches its digest.

        Returns the strictly parsed operation artifact, if the reference names one, so the caller
        can cross-check its content against the chain's facts (R05).
        """
        ceiling = (
            MAX_ARTIFACT_BYTES
            if reference.kind in {EvidenceKind.TRANSCRIPT, EvidenceKind.RAW_RESULT}
            else MAX_LIFECYCLE_DOCUMENT_BYTES
        )
        base = run if reference.root is EvidenceRoot.RUN else root
        try:
            payload = _read_relative(base, reference.path, ceiling)
        except EvidenceUnavailable as exc:
            raise _reference_refusal(
                reference, f"{reference.path} is missing or unreadable ({exc})"
            ) from None
        assert payload is not None
        if (
            len(payload) != reference.byte_count
            or hashlib.sha256(payload).hexdigest() != reference.sha256
        ):
            raise _reference_refusal(
                reference, f"{reference.path} differs from its asserted digest"
            )
        match = OPERATION_ARTIFACT_PATH_RE.fullmatch(reference.path)
        if match is None or reference.kind is EvidenceKind.RAW_RESULT:
            return None
        name = match.group("top") or match.group("name")
        model = ARTIFACT_MODELS[name]
        try:
            document = strict_json_loads(payload)
            if not isinstance(document, dict) or type(document.get("schema_version")) is not int:
                raise ValueError("not a versioned object")
            if document["schema_version"] != 1:
                raise LifecycleSchemaUnknown(f"{reference.path} carries an unknown schema version")
            artifact = model.model_validate_json(payload)
        except (UnicodeDecodeError, ValueError, ValidationError, RecursionError):
            raise OperationRecordInvalid(
                f"{reference.path} is not a valid operation artifact"
            ) from None
        if model_bytes(artifact) != payload:
            raise OperationRecordInvalid(f"{reference.path} is not canonical")
        values = artifact.model_dump(mode="json")
        if values.get("pins") != pins.model_dump(mode="json") or values.get(
            "operation_id"
        ) != match.group("operation"):
            raise OperationRecordInvalid(
                f"{reference.path} carries foreign pins or another operation id"
            )
        if match.group("attempt") is not None and values.get("attempt") != int(
            match.group("attempt")
        ):
            raise OperationRecordInvalid(f"{reference.path} names another attempt")
        return artifact

    def open_lifecycle(self, lock: RunLock) -> tuple[EventStore, "LifecycleView"]:
        """Open an event-backed run for a mutating command, under the held lock (section 7.5).

        Verifies the whole chain with a final verdict, confirms the durability of every relied-
        upon event, the witness and every referenced artifact on the current verified
        descriptors, repairs a missing, stale or damaged projection from the verified fold, and
        rebuilds any missing applied receipt from its already-durable causative transition. It
        executes nothing and never appends an event.
        """
        view = self.load_lifecycle(lock=lock)
        storage = RunLifecycleStorage(self, lock, view.state.pins)
        storage.prime(view)
        events = EventStore(storage, pins=view.state.pins)
        events.adopt(view.chain, view.state)
        storage.confirm_all(view)
        if view.projection is not ProjectionStatus.CURRENT:
            storage.publish_projection(
                projection_bytes(
                    view.state.record,
                    state_version=view.state.sequence,
                    last_event_id=view.state.event_id,
                )
            )
        for identifier in view.missing_applied:
            event_id, version, event_sha = view.state.causative_events[identifier]
            entry = view.chain[version - 1]
            assert entry.event_id == event_id
            events.journal.write_applied(identifier, entry, event_sha)
        return events, view

    def begin_lifecycle(self, lock: RunLock, pins: EventPins) -> EventStore:
        """An event store for a run with no chain yet: a new start or a legacy snapshot bridge."""
        if self.lifecycle_present():
            raise EventConflict(f"run {self._run_id} already has lifecycle evidence")
        lock.verify_ownership(
            storage_root=self.artifact_root, repository_root=self._repository_root
        )
        storage = RunLifecycleStorage(self, lock, pins)
        return EventStore(storage, pins=pins)

    def authority_reference(
        self, kind: EvidenceKind, stage_start_id: str
    ) -> DurableEvidenceReference:
        """A digest-bound reference to one immutable AUTO-017 authority artifact, read no-follow."""
        if kind is EvidenceKind.POLICY:
            path, root, target = POLICY_FILE_NAME, EvidenceRoot.RUN, self.policy_path
        else:
            path = stage_start_reference_path(kind, stage_start_id)
            root, target = EvidenceRoot.REPOSITORY, self.artifact_root / path
        payload = read_authority_bytes(target, MAX_STAGE_START_BYTES)
        assert payload is not None
        return DurableEvidenceReference(
            kind=kind,
            root=root,
            path=path,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
        )

    def record_bootstrap_evidence(self, events: EventStore, recorded_at: str) -> None:
        """Append whichever of `STAGE_START_BOUND` / `POLICY_PUBLISHED` the chain still lacks.

        Deterministic in content and timestamp, so an interrupted bootstrap resumes by
        recognizing exact duplicates rather than by inventing history (sections 7.2, 10.2).
        """
        state = events.require_state()
        identifier = state.pins.stage_start_id
        if not state.stage_start_bound:
            events.bind_stage_start(
                authorization=self.authority_reference(
                    EvidenceKind.STAGE_START_AUTHORIZATION, identifier
                ),
                binding=self.authority_reference(EvidenceKind.STAGE_START_BINDING, identifier),
                witness=self.authority_reference(EvidenceKind.STAGE_START_WITNESS, identifier),
                recorded_at=recorded_at,
            )
        if not events.require_state().policy_published:
            events.record_policy(
                self.authority_reference(EvidenceKind.POLICY, identifier), recorded_at
            )

    def bridge_snapshot(self, events: EventStore) -> RunRecord:
        """Import a validated governed v2 snapshot as `RUN_BASELINED` (section 10.1).

        Called under the lock, after every existing authority check, before the first new state
        of an explicitly requested mutating command. It records only the known snapshot and its
        exact source-byte digest; it synthesizes no request, receipt, validation or history, and
        a missing or corrupt snapshot is a refusal, never a fabricated genesis. Its events carry
        the snapshot's own `updated_at`, so an interrupted bridge is idempotent by run and
        first-event identity, never by the current time.
        """
        raw = read_authority_bytes(self.state_path, MAX_STATE_BYTES)
        assert raw is not None
        record = self._load_legacy()
        document = strict_json_loads(raw)
        if not isinstance(document, dict) or document.get("schema_version") != STATE_SCHEMA_VERSION:
            raise StateCorrupted("only a state wire version 2 snapshot is bridged")
        if not record.is_policy_governed:
            raise StateCorrupted("only a policy-governed snapshot is bridged")
        events.baseline(
            record,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            source_byte_count=len(raw),
            recorded_at=record.updated_at,
        )
        self.record_bootstrap_evidence(events, record.updated_at)
        return events.record

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


# --------------------------------------------------------------------------------------
# AUTO-018 -- bounded, no-follow lifecycle reads
# --------------------------------------------------------------------------------------

#: A bound on one enumeration of the explicitly addressed events directory (section 7.3).
MAX_EVENT_FILES: Final = 1_000_000


def _open_directory_nofollow(path: Path) -> int:
    """Open `path` as a directory with every component opened relative and no-follow."""
    absolute = path if path.is_absolute() else Path.cwd() / path
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError:
        os.close(descriptor)
        raise EventChainBroken(f"{path} cannot be opened as a no-follow directory") from None
    return descriptor


def _read_named(directory: int, name: str, ceiling: int, *, optional: bool = False) -> bytes | None:
    """Read one bounded regular file by exact name inside `directory`, no-follow."""
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        if optional:
            return None
        raise EvidenceUnavailable(f"{name} is absent") from None
    except OSError as exc:
        raise EvidenceUnavailable(f"{name} cannot be opened safely: {exc.strerror}") from None
    try:
        return _read_authority_descriptor(descriptor, ceiling)
    except (AuthorityArtifactInvalid, OSError):
        raise EvidenceUnavailable(f"{name} is not a bounded regular file") from None
    finally:
        os.close(descriptor)


def _read_named_or_none(directory: int, name: str) -> bytes | None:
    try:
        return _read_named(directory, name, MAX_LIFECYCLE_DOCUMENT_BYTES, optional=True)
    except EvidenceUnavailable:
        return b""


def _read_relative(
    base: int, relative: str, ceiling: int, *, optional: bool = False
) -> bytes | None:
    """Read a run- or root-relative path, walking every directory component no-follow."""
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise EvidenceUnavailable(f"{relative!r} is not a contained relative path")
    descriptors: list[int] = []
    current = base
    try:
        for part in parts[:-1]:
            try:
                current = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                )
            except FileNotFoundError:
                if optional:
                    return None
                raise EvidenceUnavailable(f"{relative} is absent") from None
            except OSError as exc:
                raise EvidenceUnavailable(
                    f"{relative} has an unsafe component: {exc.strerror}"
                ) from None
            descriptors.append(current)
        return _read_named(current, parts[-1], ceiling, optional=optional)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _bounded_event_names(directory: int) -> list[tuple[int, Any, str]]:
    """The one bounded, non-recursive enumeration of an explicitly addressed `events/` directory.

    AUTO-018 section 7.3 admits exactly this listing in the package besides `plan.py`'s. Names
    are validated and sorted by sequence, then every event is read by exact name. Only owned
    namespaced temporary files are ignored; any other entry, a gap, or two files for one sequence
    fails closed. Nothing is cleaned up, truncated or compacted.
    """
    names = os.listdir(directory)
    if len(names) > MAX_EVENT_FILES:
        raise EventChainBroken("the events directory exceeds its bounded size")
    claimed: list[tuple[int, Any, str]] = []
    for name in names:
        if name.startswith(TEMP_FILE_PREFIX):
            continue
        parsed = parse_event_file_name(name)
        if parsed is None:
            raise EventChainBroken(f"the events directory holds an unknown entry {name!r}")
        claimed.append((parsed[0], parsed[1], name))
    claimed.sort(key=lambda item: item[0])
    sequences = [item[0] for item in claimed]
    if len(set(sequences)) != len(sequences):
        raise EventChainBroken("two event files claim one sequence")
    if sequences != list(range(1, len(sequences) + 1)):
        raise EventChainBroken("the event sequence has a gap or does not begin at 1")
    return claimed


def _check_prospective_path(run: int, path: str) -> None:
    """Section 8.3 type 1: a pending transcript path is a declaration, not an assertion.

    Its absence is valid. If it is present it must be reachable no-follow and be a regular file;
    its presence alone proves nothing about execution or completion.
    """
    parts = path.split("/")
    descriptors: list[int] = []
    current = run
    try:
        for part in parts[:-1]:
            try:
                current = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                )
            except FileNotFoundError:
                return
            except OSError:
                raise OperationRecordInvalid(f"{path} has an unsafe component") from None
            descriptors.append(current)
        try:
            status = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(status.st_mode):
            raise OperationRecordInvalid(f"{path} is present but not a regular file")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _reference_refusal(reference: DurableEvidenceReference, detail: str) -> StateError | Exception:
    """The typed refusal for a missing or altered asserted artifact (sections 8.3, 9)."""
    if reference.kind is EvidenceKind.POLICY:
        return PolicyDigestMismatch(detail)
    if reference.kind in {
        EvidenceKind.STAGE_START_AUTHORIZATION,
        EvidenceKind.STAGE_START_BINDING,
        EvidenceKind.STAGE_START_WITNESS,
    }:
        return LifecycleAuthorityMismatch(detail, stop_reason=StopReason.STAGE_START_ALREADY_BOUND)
    return OperationRecordInvalid(detail)


@dataclass(frozen=True, slots=True)
class LifecycleView:
    """What a verified read of an event-backed run established.

    It retains bounded per-event metadata (`chain`), never the event bodies (R12); `events`
    re-reads them, digest-checked, for diagnostics only.
    """

    record: RunRecord
    state: FoldState
    chain: tuple[ChainEntry, ...]
    projection: ProjectionStatus
    missing_applied: tuple[str, ...] = ()
    reader: Callable[[], tuple[tuple[LifecycleEvent, str], ...]] | None = None

    @property
    def events(self) -> tuple[tuple[LifecycleEvent, str], ...]:
        if self.reader is None:
            raise EventChainBroken("this view retains no reader for its event bodies")
        return self.reader()

    @property
    def incomplete(self) -> Any:
        return self.state.incomplete


def _cache_identity(status: os.stat_result) -> tuple[int, ...]:
    """What a process-local confirmation is keyed on: identity plus change stamps (R07).

    An in-place rewrite keeps the inode but moves the change time, so a confirmed file that was
    altered afterwards is never acknowledged from the cache.
    """
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)


#: A canonical walk's result: the bound directory identities, then the leaf's cache identity.
_NamespaceBinding = tuple[tuple[tuple[int, int], ...], tuple[int, ...] | None]


class RunLifecycleStorage:
    """Section 7's durable I/O for one run under one verified hold (`events.LifecycleStorage`).

    Every write is descriptor-bound to the hold (section 7.4), goes through
    :func:`write_redacted_artifact` (section 7.3), and returns only once durable (section 7.5).
    Confirmations performed under this hold are cached process-locally, keyed by exact address,
    digest and inode, and never outlive the storage object.

    R02 / R07: every governed directory below the storage root is bound to the identity this hold
    first reached it at, through a no-follow walk from the retained root descriptor. A cached
    confirmation is honoured only after the current canonical walk reaches those same
    directories and the same file, so a parent renamed away and replaced -- by another directory,
    or by a symlink to the detached original -- is a lost ownership context, never a duplicate
    acknowledgment.
    """

    def __init__(self, store: "RunStateStore", lock: RunLock, pins: EventPins) -> None:
        self._store = store
        self._lock = lock
        self._pins = pins
        self._names: tuple[str, ...] = ()
        self._witness: bytes | None = None
        self._directories: dict[tuple[str, ...], tuple[int, int]] = {}
        self._confirmed: dict[tuple[str, str], _NamespaceBinding] = {}

    def _target(self, root: EvidenceRoot, relative: str) -> DurableTarget:
        parts = tuple(relative.split("/"))
        base: tuple[str, ...] = (self._store.run_id,) if root is EvidenceRoot.RUN else ()
        return DurableTarget(
            lock=self._lock,
            storage_root=self._store.artifact_root,
            repository_root=self._store.repository_root,
            parts=(*base, *parts[:-1]),
            name=parts[-1],
        )

    def _path(self, root: EvidenceRoot, relative: str) -> Path:
        base = self._store.run_directory if root is EvidenceRoot.RUN else self._store.artifact_root
        return base / relative

    def prime(self, view: LifecycleView) -> None:
        self._names = tuple(entry.file_name for entry in view.chain)
        run, root = self._store._open_run_directory(self._lock)
        try:
            self._witness = _read_named_or_none(run, PUBLICATION_WITNESS_FILE_NAME)
        finally:
            os.close(run)
            os.close(root)
        # R02: bind the verified run, events and referenced-artifact directories now, so a
        # directory swapped before its first confirmation is refused rather than adopted.
        bound: set[tuple[EvidenceRoot, str]] = set()
        addresses = [(EvidenceRoot.RUN, PUBLICATION_WITNESS_FILE_NAME)]
        for entry in view.chain:
            addresses.append((EvidenceRoot.RUN, f"{EVENTS_DIRECTORY}/{entry.file_name}"))
            addresses.extend((reference.root, reference.path) for reference in entry.references)
        for evidence_root, relative in addresses:
            parent = (evidence_root, relative.rpartition("/")[0])
            if parent in bound:
                continue
            bound.add(parent)
            try:
                self._bind(evidence_root, relative)
            except EvidenceUnavailable:
                continue  # never seen, so nothing is bound; confirmation refuses it later

    def _bind(self, root: EvidenceRoot, relative: str) -> _NamespaceBinding:
        """Walk the canonical namespace of `relative` no-follow and check it against the hold.

        Every directory is opened `O_NOFOLLOW` below the previous descriptor, starting at the
        hold's retained root descriptor, and must be the very directory this hold first bound at
        that canonical name; the leaf is stat'ed at its name without following. A directory this
        hold already bound that is now missing, a symlink, or another inode invalidates the hold
        (:class:`LockOwnershipLost`). One never bound and absent is :class:`EvidenceUnavailable`.
        """
        return self._walk(self._target(root, relative), leaf=True)

    def _bind_parents(self, target: DurableTarget) -> None:
        """Check the already-bound prefix of `target`'s directories; absent ones are created."""
        bound = 0
        while bound < len(target.parts) and target.parts[: bound + 1] in self._directories:
            bound += 1
        if bound:
            self._walk(
                DurableTarget(
                    lock=target.lock,
                    storage_root=target.storage_root,
                    repository_root=target.repository_root,
                    parts=target.parts[:bound],
                    name=".",
                ),
                leaf=False,
            )

    def _bind_directory(self, root: EvidenceRoot, relative: str) -> None:
        """:meth:`_bind` for a governed directory itself (`relative` empty: the run directory)."""
        self._walk(self._target(root, f"{relative}/." if relative else "."), leaf=False)

    def _walk(self, target: DurableTarget, *, leaf: bool) -> _NamespaceBinding:
        if any(part in {"", ".", ".."} for part in target.parts):
            raise EvidenceUnavailable(f"{target.address} is not a canonical governed address")
        target.guard()
        current = self._lock.storage_root_descriptor(storage_root=target.storage_root)
        descriptors: list[int] = []
        directories: list[tuple[int, int]] = []
        try:
            for index, part in enumerate(target.parts, start=1):
                prefix = target.parts[:index]
                try:
                    opened = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                    )
                except OSError as exc:
                    if prefix in self._directories:
                        raise self._lock.invalidate(
                            f"the addressed storage directory {'/'.join(prefix)!r} is no longer "
                            f"a directory at its canonical name ({exc.strerror})"
                        ) from None
                    raise EvidenceUnavailable(
                        f"{target.address} cannot be reopened safely: {exc.strerror}"
                    ) from None
                descriptors.append(opened)
                current = opened
                status = os.fstat(opened)
                directory = (status.st_dev, status.st_ino)
                if self._directories.setdefault(prefix, directory) != directory:
                    raise self._lock.invalidate(
                        f"the addressed storage directory {'/'.join(prefix)!r} was renamed away "
                        "or replaced since this hold bound it"
                    )
                directories.append(directory)
            identity: tuple[int, ...] | None = None
            if leaf:
                try:
                    identity = _cache_identity(
                        os.stat(target.name, dir_fd=current, follow_symlinks=False)
                    )
                except FileNotFoundError:
                    pass
            target.guard(descriptors)
        except OSError as exc:
            raise EvidenceUnavailable(
                f"{target.address} cannot be reopened safely: {exc.strerror}"
            ) from None
        finally:
            for opened in reversed(descriptors):
                os.close(opened)
        return tuple(directories), identity

    def read_chain(self) -> StoredChain:
        self._bind_directory(EvidenceRoot.RUN, EVENTS_DIRECTORY)
        run, root = self._store._open_run_directory(self._lock)
        try:
            chain = self._store._read_snapshot(run)
        finally:
            os.close(run)
            os.close(root)
        self._bind_directory(EvidenceRoot.RUN, EVENTS_DIRECTORY)
        return chain

    def check_tip(self, sequence: int, event_sha256: str) -> None:
        """Section 7.2 step 1: the chain and witness are exactly what this hold last verified.

        R02: the run and events directories read here are first, and again afterwards, proven to
        be the very ones this hold bound at their canonical names.
        """
        self._bind_directory(EvidenceRoot.RUN, EVENTS_DIRECTORY)
        run, root = self._store._open_run_directory(self._lock)
        try:
            witness = _read_named_or_none(run, PUBLICATION_WITNESS_FILE_NAME)
            try:
                directory = os.open(
                    EVENTS_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run
                )
            except OSError:
                raise EventChainBroken("the events directory changed under the hold") from None
            try:
                names = tuple(name for _, _, name in _bounded_event_names(directory))
            finally:
                os.close(directory)
        finally:
            os.close(run)
            os.close(root)
        self._bind_directory(EvidenceRoot.RUN, EVENTS_DIRECTORY)
        if names != self._names or len(names) != sequence or witness != self._witness:
            raise EventChainBroken(
                "the event chain or its witness changed outside this hold's own appends"
            )

    def _write(
        self,
        root: EvidenceRoot,
        relative: str,
        payload: bytes | str,
        *,
        exclusive: bool,
        structural: bool,
    ) -> RedactedWrite:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        target = self._target(root, relative)
        # R02: a governed directory this hold bound and that was since replaced -- even by an
        # empty one -- refuses before anything is written into the replacement.
        self._bind_parents(target)
        write = write_redacted_artifact(
            self._path(root, relative),
            text,
            relative_path=relative,
            exclusive=exclusive,
            target=target,
            refuse_redaction=structural,
        )
        assert write.sha256 is not None
        self._remember(root, relative, write.sha256)
        return write

    def _remember(self, root: EvidenceRoot, relative: str, sha256: str) -> None:
        binding = self._bind(root, relative)
        if binding[1] is not None:
            self._confirmed[(f"{root.value}:{relative}", sha256)] = binding

    def publish_evidence(
        self, path: str, text: str, *, structural: bool
    ) -> DurableEvidenceReference:
        kind = classify_run_evidence_path(path)
        if kind is None or OPERATION_ARTIFACT_PATH_RE.fullmatch(path) is None:
            raise OperationRecordInvalid(f"{path!r} is not an operation artifact path")
        try:
            write = self._write(EvidenceRoot.RUN, path, text, exclusive=True, structural=structural)
        except ExclusivePublicationConflict:
            raise OperationRecordConflict(
                f"{path} already holds different evidence; operation evidence is immutable"
            ) from None
        assert write.sha256 is not None
        return DurableEvidenceReference(
            kind=kind,
            root=EvidenceRoot.RUN,
            path=path,
            sha256=write.sha256,
            byte_count=write.byte_count,
        )

    def publish_witness(self, payload: bytes) -> None:
        self._write(
            EvidenceRoot.RUN,
            PUBLICATION_WITNESS_FILE_NAME,
            payload,
            exclusive=False,
            structural=True,
        )
        self._witness = payload

    def publish_event(self, name: str, payload: bytes) -> None:
        try:
            write = self._write(
                EvidenceRoot.RUN,
                f"{EVENTS_DIRECTORY}/{name}",
                payload,
                exclusive=True,
                structural=True,
            )
        except ExclusivePublicationConflict:
            raise EventConflict(f"{name} already exists with other bytes") from None
        if write.exclusive_outcome is ExclusiveOutcome.IDENTICAL_EXISTS:
            raise EventConflict(f"{name} already existed outside the verified chain")
        self._names = (*self._names, name)

    def publish_projection(self, payload: bytes) -> None:
        self._write(EvidenceRoot.RUN, STATE_FILE_NAME, payload, exclusive=False, structural=True)

    def witness_bytes(self) -> bytes | None:
        """The witness bytes this hold last verified or published (re-checked by `check_tip`)."""
        return self._witness

    def _confirm(self, root: EvidenceRoot, relative: str, sha256: str, ceiling: int) -> None:
        key = (f"{root.value}:{relative}", sha256)
        # R02 / R07: the current canonical namespace is proven first, on every path; a cached
        # confirmation is reused only while every directory and the file it depends on are the
        # very ones it was confirmed through.
        binding = self._bind(root, relative)
        if self._confirmed.get(key) == binding:
            return
        confirm_durable(self._target(root, relative), expected_sha256=sha256, ceiling=ceiling)
        self._remember(root, relative, sha256)

    def confirm_event(self, name: str, sha256: str) -> None:
        try:
            self._confirm(
                EvidenceRoot.RUN, f"{EVENTS_DIRECTORY}/{name}", sha256, MAX_LIFECYCLE_DOCUMENT_BYTES
            )
        except EvidenceUnavailable as exc:
            raise EventChainBroken(str(exc)) from None

    def confirm_witness(self, sha256: str) -> None:
        try:
            self._confirm(
                EvidenceRoot.RUN,
                PUBLICATION_WITNESS_FILE_NAME,
                sha256,
                MAX_LIFECYCLE_DOCUMENT_BYTES,
            )
        except EvidenceUnavailable as exc:
            raise EventChainBroken(str(exc)) from None

    def confirm_references(self, references: Sequence[DurableEvidenceReference]) -> None:
        for reference in references:
            ceiling = (
                MAX_ARTIFACT_BYTES
                if reference.kind in {EvidenceKind.TRANSCRIPT, EvidenceKind.RAW_RESULT}
                else MAX_LIFECYCLE_DOCUMENT_BYTES
            )
            try:
                self._confirm(reference.root, reference.path, reference.sha256, ceiling)
            except EvidenceUnavailable as exc:
                raise _reference_refusal(reference, str(exc)) from None

    def verify_references(
        self, references: Sequence[DurableEvidenceReference]
    ) -> list[tuple[DurableEvidenceReference, MilestoneRunnerModel]]:
        """Verify each asserted artifact; return the parsed operation artifacts (R05)."""
        if not references:
            return []
        artifacts: list[tuple[DurableEvidenceReference, MilestoneRunnerModel]] = []
        for reference in references:
            self._bind_directory(reference.root, reference.path.rpartition("/")[0])
        run, root = self._store._open_run_directory(self._lock)
        try:
            for reference in references:
                artifact = self._store._verify_reference(reference, run, root, self._pins)
                if artifact is not None:
                    artifacts.append((reference, artifact))
        finally:
            os.close(run)
            os.close(root)
        for reference in references:
            self._bind_directory(reference.root, reference.path.rpartition("/")[0])
        return artifacts

    def confirm_all(self, view: LifecycleView) -> None:
        """Section 7.5: confirm the whole relied-upon dependency set under this hold."""
        for entry in view.chain:
            self.confirm_event(entry.file_name, entry.sha256)
            self.confirm_references(entry.references)
        assert self._witness is not None
        self.confirm_witness(hashlib.sha256(self._witness).hexdigest())
        if view.projection is ProjectionStatus.CURRENT:
            # The relied-upon projection is confirmed too; a lagging one is republished instead.
            current = projection_bytes(
                view.state.record,
                state_version=view.state.sequence,
                last_event_id=view.state.event_id,
            )
            try:
                self._confirm(
                    EvidenceRoot.RUN,
                    STATE_FILE_NAME,
                    hashlib.sha256(current).hexdigest(),
                    MAX_STATE_BYTES,
                )
            except EvidenceUnavailable as exc:
                raise EventChainBroken(str(exc)) from None
