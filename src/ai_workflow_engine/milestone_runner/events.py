"""Durable lifecycle events, their integrity serialization and the pure fold (AUTO-018).

Contract: `docs/workflow-automation/stage-prompts/AUTO-018.md` sections 4 (the invariants), 5 (the
closed event schema, identity and ordering), 6 and 6.1 (fold, transition authority and complete
logical-mutation evidence), 7.2 (the ordered append protocol), 8.2 (the operation phase ladder
as events), 9 (replay and failure semantics) and 11 (this module's sole permitted change: closed
events and payloads, complete mutation declarations and incomplete-prefix evidence, integrity
serialization, EventStore coordination and the pure fold -- with no filesystem-write primitive).

What this module is, and what it is not
---------------------------------------
It is the vocabulary and the arithmetic of the event chain. :func:`fold` is deterministic
validation and reconstruction: the first event establishes the run-record body, every later
event applies only its own typed effect, and every step re-checks the closed transition table,
the authority pins, the old values, the ledger prefixes, the operation dependencies and the
before/after body digests. A valid hash over an illegal semantic update is still refused.

It is not a transition authority. :class:`EventStore` persists and folds facts through a storage
object `state.py` provides; it never selects a target state, retries anything, reviews anything or
knows what comes next. `STATE_TRANSITIONED` is appended only through
:meth:`EventStore.append_transition`, which only `application.py` calls (INV-018-01), and which
accepts the application's already-validated before/after records and verifies them.

Integrity serialization
-----------------------
`models.canonical_json_bytes` deliberately drops wall-clock fields; that is right for approval
bindings and wrong here, where a timestamp is part of what an event asserts. Every
digest-bearing document is therefore serialized by :func:`integrity_bytes`: the timestamp-
inclusive `policy.authority_json_bytes` serializer, after a strict check that refuses floats,
non-string keys and surrogate code points rather than silently normalizing or dropping anything.
Existing `canonical_digest`, policy digests and approval bindings are untouched.
"""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, Protocol

from pydantic import Field, ValidationError, field_validator, model_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.models import (
    ALLOWED_RUN_TRANSITIONS,
    MAX_STATE_VERSION,
    STAGE_ID_RE,
    ApprovalRecord,
    Finding,
    MilestoneCheckpoint,
    MilestoneRunnerModel,
    ProviderRunRecord,
    RecoveryCommand,
    RecoveryLedgerEntry,
    RunRecord,
    RunStatus,
    StopReason,
    VerificationResult,
    event_backed_state_document,
)
from ai_workflow_engine.milestone_runner.operations import (
    APPLIED_FILE_NAME,
    DISPATCH_INTENT_FILE_NAME,
    DISPATCH_RECEIPT_FILE_NAME,
    MAX_OPERATION_ATTEMPTS,
    OPERATION_ARTIFACT_PATH_RE,
    PRE_SPAWN_FAILED_FILE_NAME,
    RAW_RESULT_FILE_NAME,
    REQUEST_FILE_NAME,
    VALIDATED_RESULT_FILE_NAME,
    AdapterIdentity,
    AttemptRecord,
    DispatchIntent,
    DispatchReceipt,
    ExecutionOutcome,
    OperationJournal,
    OperationPhase,
    OperationPins,
    OperationRecord,
    OperationRequest,
    OperationStep,
    PersistenceKind,
    PreSpawnFailure,
    ValidatedResult,
    ValidationVerdict,
    operation_artifact_path,
    operation_id,
)
from ai_workflow_engine.milestone_runner.policy import authority_json_bytes
from ai_workflow_engine.successor_planning.redaction import RedactionFinding, redact_text

#: Section 5.1: the event schema is versioned independently of state and configuration.
LIFECYCLE_SCHEMA_VERSION: Final = 1

#: Section 5.1: sequence range; exhaustion refuses rather than wrapping.
MAX_EVENT_SEQUENCE: Final = MAX_STATE_VERSION

#: Section 7.3: each event, witness, request and validated-result document is at most 16 MiB.
MAX_LIFECYCLE_DOCUMENT_BYTES: Final = 16 << 20

#: Typed bounds on list-shaped payload fields, in addition to the byte ceiling.
MAX_MANIFEST_CONSTITUENTS: Final = 16
MAX_EVENT_REFERENCES: Final = 8

#: Section 7.1: the run-local names this module addresses.
EVENTS_DIRECTORY: Final = "events"
PUBLICATION_WITNESS_FILE_NAME: Final = "event-publication.json"
STATE_PROJECTION_FILE_NAME: Final = "state.json"
POLICY_REFERENCE_PATH: Final = "policy.json"
STAGE_STARTS_REFERENCE_DIRECTORY: Final = "stage-starts"

#: Section 6: `state_version` and `last_event_id` are projection-managed and excluded from the
#: record-body digest; the body is the closed `RunRecord`, which carries neither.

_SHA256_CHARS: Final = frozenset("0123456789abcdef")


def _sha256(value: str, field_name: str) -> str:
    if len(value) != 64 or not set(value) <= _SHA256_CHARS:
        raise ValueError(f"{field_name} must be exactly 64 lowercase hexadecimal characters")
    return value


_UTC_RE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def _utc(value: str, field_name: str) -> str:
    if _UTC_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a UTC timestamp YYYY-MM-DDThh:mm:ssZ")
    return value


# --------------------------------------------------------------------------------------
# Section 9 -- typed refusals
# --------------------------------------------------------------------------------------


class LifecycleError(WorkflowEngineError):
    """Base lifecycle storage refusal.

    Every subclass is a storage refusal, never an OWNER decision kind. `effective_state` is what
    application reporting exposes independently of an untrusted record (section 9): the safety
    stop, without appending a stop to suspect storage and without adding any transition edge.
    """

    stop_reason: StopReason | None = StopReason.EVENT_CHAIN_BROKEN
    effective_state: RunStatus = RunStatus.HUMAN_INTERVENTION_REQUIRED


class EventChainBroken(LifecycleError):
    """Missing, reordered, edited, duplicate or foreign events, a broken link or a lost tail."""

    stop_reason: StopReason | None = StopReason.EVENT_CHAIN_BROKEN


class EventConflict(LifecycleError):
    """A reused event identity or sequence with different content, or a stale expected tip."""

    stop_reason: StopReason | None = StopReason.EVENT_CONFLICT


class OperationRecordInvalid(LifecycleError):
    """Missing or malformed operation evidence, a pin conflict or an impossible phase order."""

    stop_reason: StopReason | None = StopReason.OPERATION_RECORD_INVALID


class OperationRecordConflict(LifecycleError):
    """A reused operation identity or attempt with different content, or a rewritten operation."""

    stop_reason: StopReason | None = StopReason.OPERATION_RECORD_CONFLICT


class LifecycleSchemaUnknown(LifecycleError):
    """An event or lifecycle document carries a schema version this build does not know."""

    stop_reason: StopReason | None = StopReason.LIFECYCLE_SCHEMA_UNKNOWN


class ApplicationMutationIncomplete(LifecycleError):
    """A durable declaration has only a proper constituent prefix (section 6.1).

    ST-02 refuses execution here. It never completes, rolls back, reinterprets or chooses a
    recovery for the mutation; that belongs to AUTO-019.
    """

    stop_reason: StopReason | None = StopReason.APPLICATION_MUTATION_INCOMPLETE

    def __init__(self, message: str, *, mutation: "IncompleteApplicationMutation") -> None:
        super().__init__(message)
        self.mutation = mutation


# --------------------------------------------------------------------------------------
# Integrity serialization
# --------------------------------------------------------------------------------------


def _require_integrity_value(value: object, where: str) -> None:
    """Accept only `None`, exact `bool`/`int`/`str`, lists and string-keyed mappings."""
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        text: str = value
        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise ValueError(f"{where} carries a surrogate code point")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_integrity_value(item, f"{where}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError(f"{where} carries a non-string key")
            _require_integrity_value(item, f"{where}.{key}")
        return
    raise ValueError(f"{where} carries an unsupported value of type {type(value).__name__}")


def integrity_bytes(document: object) -> bytes:
    """Timestamp-inclusive canonical bytes: no key dropped, no value normalized (section 5.1)."""
    _require_integrity_value(document, "document")
    return authority_json_bytes(document)


def integrity_digest(document: object) -> str:
    return hashlib.sha256(integrity_bytes(document)).hexdigest()


def model_bytes(model: MilestoneRunnerModel) -> bytes:
    """The integrity bytes of a strict model's JSON dump."""
    return integrity_bytes(model.model_dump(mode="json"))


def body_digest(record: RunRecord) -> str:
    """The record-body digest. Every field is included, timestamps too (section 6)."""
    return hashlib.sha256(model_bytes(record)).hexdigest()


def projection_bytes(record: RunRecord, *, state_version: int, last_event_id: str) -> bytes:
    """The one serializer for folded bytes and for `state.json` (section 6)."""
    return integrity_bytes(
        event_backed_state_document(
            record, state_version=state_version, last_event_id=last_event_id
        )
    )


class _DuplicateKey(ValueError):
    pass


def strict_json_loads(payload: bytes) -> object:
    """Strict UTF-8 JSON with duplicate keys refused at every depth."""

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKey(key)
            result[key] = value
        return result

    def refuse_constant(value: str) -> object:
        raise ValueError(f"non-finite number {value}")

    text = payload.decode("utf-8", errors="strict")
    return json.loads(text, object_pairs_hook=hook, parse_constant=refuse_constant)


# --------------------------------------------------------------------------------------
# Section 5.2 -- the closed vocabulary
# --------------------------------------------------------------------------------------


class LifecycleEventType(StrEnum):
    """The closed ST-02 event vocabulary. New members need a later contract (section 5.2)."""

    RUN_INITIALIZED = "RUN_INITIALIZED"
    RUN_BASELINED = "RUN_BASELINED"
    STAGE_START_BOUND = "STAGE_START_BOUND"
    POLICY_PUBLISHED = "POLICY_PUBLISHED"
    APPLICATION_MUTATION_DECLARED = "APPLICATION_MUTATION_DECLARED"
    RUN_RECORD_UPDATED = "RUN_RECORD_UPDATED"
    RECOVERY_LEDGER_APPENDED = "RECOVERY_LEDGER_APPENDED"
    OPERATION_REQUEST_CREATED = "OPERATION_REQUEST_CREATED"
    OPERATION_DISPATCH_INTENT = "OPERATION_DISPATCH_INTENT"
    OPERATION_DISPATCH_RECEIVED = "OPERATION_DISPATCH_RECEIVED"
    OPERATION_PRE_SPAWN_FAILED = "OPERATION_PRE_SPAWN_FAILED"
    OPERATION_RESULT_RECEIVED = "OPERATION_RESULT_RECEIVED"
    OPERATION_RESULT_VALIDATED = "OPERATION_RESULT_VALIDATED"
    OPERATION_RESULT_ACCEPTED = "OPERATION_RESULT_ACCEPTED"
    OPERATION_RESULT_REJECTED = "OPERATION_RESULT_REJECTED"
    STATE_TRANSITIONED = "STATE_TRANSITIONED"


_GENESIS_TYPES: Final = frozenset(
    {LifecycleEventType.RUN_INITIALIZED, LifecycleEventType.RUN_BASELINED}
)

#: The event types that may be constituents of a declared mutation: every body-changing type.
CONSTITUENT_TYPES: Final = frozenset(
    {
        LifecycleEventType.RUN_RECORD_UPDATED,
        LifecycleEventType.RECOVERY_LEDGER_APPENDED,
        LifecycleEventType.OPERATION_RESULT_ACCEPTED,
        LifecycleEventType.OPERATION_RESULT_REJECTED,
        LifecycleEventType.STATE_TRANSITIONED,
    }
)

#: Types that exist only as constituents of a complete durable declaration (section 6.1).
_DECLARED_ONLY_TYPES: Final = frozenset(
    {
        LifecycleEventType.RECOVERY_LEDGER_APPENDED,
        LifecycleEventType.OPERATION_RESULT_ACCEPTED,
        LifecycleEventType.OPERATION_RESULT_REJECTED,
    }
)


def event_file_name(sequence: int, event_type: LifecycleEventType) -> str:
    """`events/<sequence:08d>-<event_type>.json` without the directory (section 5.1)."""
    if not 1 <= sequence <= MAX_EVENT_SEQUENCE:
        raise EventConflict(f"sequence {sequence} is outside 1..{MAX_EVENT_SEQUENCE}")
    return f"{sequence:08d}-{event_type.value}.json"


def parse_event_file_name(name: str) -> tuple[int, LifecycleEventType] | None:
    """The sequence and type a canonical event file name claims, or `None` for anything else."""
    if len(name) < 15 or name[8] != "-" or not name.endswith(".json"):
        return None
    digits = name[:8]
    if not (digits.isascii() and digits.isdigit()):
        return None
    try:
        event_type = LifecycleEventType(name[9:-5])
    except ValueError:
        return None
    sequence = int(digits)
    if not 1 <= sequence <= MAX_EVENT_SEQUENCE:
        return None
    return sequence, event_type


# --------------------------------------------------------------------------------------
# Section 8.3 -- digest-bound durable evidence references
# --------------------------------------------------------------------------------------


class EvidenceKind(StrEnum):
    """What a digest-bound reference asserts is published evidence (section 8.3)."""

    TRANSCRIPT = "TRANSCRIPT"
    OPERATION_REQUEST = "OPERATION_REQUEST"
    DISPATCH_INTENT = "DISPATCH_INTENT"
    DISPATCH_RECEIPT = "DISPATCH_RECEIPT"
    PRE_SPAWN_FAILURE = "PRE_SPAWN_FAILURE"
    RAW_RESULT = "RAW_RESULT"
    VALIDATED_RESULT = "VALIDATED_RESULT"
    #: `applied.json`: a receipt of an already-committed transition. No event asserts it.
    APPLIED_RECEIPT = "APPLIED_RECEIPT"
    POLICY = "POLICY"
    STAGE_START_AUTHORIZATION = "STAGE_START_AUTHORIZATION"
    STAGE_START_BINDING = "STAGE_START_BINDING"
    STAGE_START_WITNESS = "STAGE_START_WITNESS"


class EvidenceRoot(StrEnum):
    """Which directory a reference path is relative to: this run's, or the repository-scoped
    root the Stage Start authority lives under. Never the worktree."""

    RUN = "RUN"
    REPOSITORY = "REPOSITORY"


_OPERATION_KIND_BY_NAME: Final[dict[str, EvidenceKind]] = {
    REQUEST_FILE_NAME: EvidenceKind.OPERATION_REQUEST,
    DISPATCH_INTENT_FILE_NAME: EvidenceKind.DISPATCH_INTENT,
    DISPATCH_RECEIPT_FILE_NAME: EvidenceKind.DISPATCH_RECEIPT,
    PRE_SPAWN_FAILED_FILE_NAME: EvidenceKind.PRE_SPAWN_FAILURE,
    RAW_RESULT_FILE_NAME: EvidenceKind.RAW_RESULT,
    VALIDATED_RESULT_FILE_NAME: EvidenceKind.VALIDATED_RESULT,
    APPLIED_FILE_NAME: EvidenceKind.APPLIED_RECEIPT,
}

_TRANSCRIPT_SUFFIXES: Final = ("prompt.md", "stdout.txt", "stderr.txt", "last-message.md")


def is_transcript_path(path: str) -> bool:
    """The closed `transcripts/<NNNN>-<UTC>-<label>.<kind>` grammar, restated for events."""
    if not path.startswith("transcripts/") or path.count("/") != 1:
        return False
    name = path.split("/", 1)[1]
    head, _, rest = name.partition("-")
    if not (4 <= len(head) <= 8 and head.isascii() and head.isdigit()):
        return False
    stamp, _, tail = rest.partition("-")
    if len(stamp) != 16 or stamp[8] != "T" or stamp[15] != "Z":
        return False
    if not (stamp[:8] + stamp[9:15]).isdigit():
        return False
    label, dot, suffix = tail.partition(".")
    if not dot or suffix not in _TRANSCRIPT_SUFFIXES:
        return False
    return bool(label) and all(part.isalnum() and part.islower() for part in label.split("-"))


def classify_run_evidence_path(path: str) -> EvidenceKind | None:
    """The evidence kind a run-relative path may carry, from its exact grammar alone."""
    if path == POLICY_REFERENCE_PATH:
        return EvidenceKind.POLICY
    if is_transcript_path(path):
        return EvidenceKind.TRANSCRIPT
    match = OPERATION_ARTIFACT_PATH_RE.fullmatch(path)
    if match is None:
        return None
    name = match.group("top") or match.group("name")
    return _OPERATION_KIND_BY_NAME.get(name)


class DurableEvidenceReference(MilestoneRunnerModel):
    """A typed assertion that exact bytes were published (section 8.3, reference type 2).

    The artifact must exist, be safely readable and match `sha256` before the asserting event is
    accepted and on every later verified read or fold. It is never downgraded to a prospective
    path declaration, and its absence never triggers a redispatch.
    """

    kind: EvidenceKind
    root: EvidenceRoot
    path: str
    sha256: str
    byte_count: int = Field(ge=0)

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        return _sha256(value, "sha256")

    @model_validator(mode="after")
    def _validate_path(self) -> "DurableEvidenceReference":
        stage_kinds = {
            EvidenceKind.STAGE_START_AUTHORIZATION: ".json",
            EvidenceKind.STAGE_START_BINDING: ".binding.json",
            EvidenceKind.STAGE_START_WITNESS: ".consumed.json",
        }
        if self.kind in stage_kinds:
            prefix = f"{STAGE_STARTS_REFERENCE_DIRECTORY}/"
            suffix = stage_kinds[self.kind]
            identifier = self.path[len(prefix) : len(self.path) - len(suffix)]
            if (
                self.root is not EvidenceRoot.REPOSITORY
                or not self.path.startswith(prefix)
                or not self.path.endswith(suffix)
                or len(identifier) != 64
                or not set(identifier) <= _SHA256_CHARS
            ):
                raise ValueError(f"{self.path!r} is not a {self.kind.value} reference")
            return self
        if (
            self.root is not EvidenceRoot.RUN
            or classify_run_evidence_path(self.path) is not self.kind
        ):
            raise ValueError(f"{self.path!r} is not a run-local {self.kind.value} reference")
        return self

    @property
    def operation_id(self) -> str | None:
        match = OPERATION_ARTIFACT_PATH_RE.fullmatch(self.path)
        return None if match is None else match.group("operation")

    @property
    def attempt(self) -> int | None:
        match = OPERATION_ARTIFACT_PATH_RE.fullmatch(self.path)
        if match is None or match.group("attempt") is None:
            return None
        return int(match.group("attempt"))


def stage_start_reference_path(kind: EvidenceKind, stage_start_id: str) -> str:
    suffix = {
        EvidenceKind.STAGE_START_AUTHORIZATION: ".json",
        EvidenceKind.STAGE_START_BINDING: ".binding.json",
        EvidenceKind.STAGE_START_WITNESS: ".consumed.json",
    }[kind]
    return f"{STAGE_STARTS_REFERENCE_DIRECTORY}/{stage_start_id}{suffix}"


# --------------------------------------------------------------------------------------
# Typed record updates -- never an arbitrary update dictionary (section 5.2)
# --------------------------------------------------------------------------------------


class RecordField(StrEnum):
    """The baseline `RunRecord` fields an event may replace. Pins, state, the creation stamp
    and the four recovery ledgers are deliberately absent."""

    UPDATED_AT = "updated_at"
    STOP_REASON = "stop_reason"
    CURRENT_MILESTONE = "current_milestone"
    COMPLETED_MILESTONES = "completed_milestones"
    MILESTONE_CHECKPOINTS = "milestone_checkpoints"
    CHANGED_PATHS = "changed_paths"
    PROVIDER_RUNS = "provider_runs"
    VERIFICATION_RESULTS = "verification_results"
    BLOCKING_FINDINGS = "blocking_findings"
    DEFERRED_FINDINGS = "deferred_findings"
    APPROVALS = "approvals"
    REVIEW_ATTEMPTS = "review_attempts"
    SUCCESSFUL_REVIEW_ROUNDS = "successful_review_rounds"
    PROVIDER_FAILURE_COUNT = "provider_failure_count"
    CORRECTION_ROUND = "correction_round"
    CLOSURE_ROUND = "closure_round"


_NULLABLE_FIELDS: Final = frozenset({RecordField.STOP_REASON, RecordField.CURRENT_MILESTONE})
_COUNTER_FIELDS: Final = frozenset(
    {
        RecordField.REVIEW_ATTEMPTS,
        RecordField.SUCCESSFUL_REVIEW_ROUNDS,
        RecordField.PROVIDER_FAILURE_COUNT,
        RecordField.CORRECTION_ROUND,
        RecordField.CLOSURE_ROUND,
    }
)

#: Which fields each body-changing event may replace. The four recovery ledgers move only through
#: `RECOVERY_LEDGER_APPENDED`, and accepted findings and round counters only through
#: `OPERATION_RESULT_ACCEPTED` -- never through a second route.
_RECORD_UPDATE_FIELDS: Final = frozenset(RecordField) - {
    RecordField.BLOCKING_FINDINGS,
    RecordField.SUCCESSFUL_REVIEW_ROUNDS,
    RecordField.CORRECTION_ROUND,
    RecordField.CLOSURE_ROUND,
    RecordField.PROVIDER_FAILURE_COUNT,
}
_TRANSITION_UPDATE_FIELDS: Final = frozenset(
    {
        RecordField.UPDATED_AT,
        RecordField.CURRENT_MILESTONE,
        RecordField.CHANGED_PATHS,
        RecordField.COMPLETED_MILESTONES,
        RecordField.MILESTONE_CHECKPOINTS,
    }
)
_ACCEPTED_FIELDS: Final = frozenset(
    {
        RecordField.UPDATED_AT,
        RecordField.SUCCESSFUL_REVIEW_ROUNDS,
        RecordField.CORRECTION_ROUND,
        RecordField.CLOSURE_ROUND,
        RecordField.BLOCKING_FINDINGS,
        RecordField.DEFERRED_FINDINGS,
    }
)
_REJECTED_FIELDS: Final = frozenset({RecordField.UPDATED_AT, RecordField.PROVIDER_FAILURE_COUNT})


class RecordUpdates(MilestoneRunnerModel):
    """Typed replacement values for named baseline fields.

    `assigned` names exactly which fields are replaced, sorted and unique; every other value is
    `None`. The values are typed by the baseline record's own models, and the result of applying
    them is revalidated by the closed `RunRecord` schema.
    """

    assigned: list[RecordField] = Field(default_factory=list)
    updated_at: str | None = None
    stop_reason: StopReason | None = None
    current_milestone: str | None = None
    completed_milestones: list[str] | None = None
    milestone_checkpoints: list[MilestoneCheckpoint] | None = None
    changed_paths: list[str] | None = None
    provider_runs: list[ProviderRunRecord] | None = None
    verification_results: list[VerificationResult] | None = None
    blocking_findings: list[Finding] | None = None
    deferred_findings: list[Finding] | None = None
    approvals: list[ApprovalRecord] | None = None
    review_attempts: int | None = None
    successful_review_rounds: int | None = None
    provider_failure_count: int | None = None
    correction_round: int | None = None
    closure_round: int | None = None

    @model_validator(mode="after")
    def _validate_assignment(self) -> "RecordUpdates":
        names = [member.value for member in self.assigned]
        if names != sorted(set(names)):
            raise ValueError("assigned fields must be sorted and unique")
        for member in RecordField:
            value = getattr(self, member.value)
            if member not in self.assigned and value is not None:
                raise ValueError(f"{member.value} carries a value it does not assign")
            if member in self.assigned and value is None and member not in _NULLABLE_FIELDS:
                raise ValueError(f"{member.value} is assigned without a value")
        return self


def record_updates(before: RunRecord, after: RunRecord) -> RecordUpdates:
    """The typed difference of two records over the replaceable fields."""
    left = json.loads(before.model_dump_json())
    right = json.loads(after.model_dump_json())
    for fixed in (
        "schema_version",
        "run_id",
        "repository_root",
        "repository_identity",
        "expected_branch",
        "baseline_sha",
        "contract_sha256",
        "created_at",
        "policy_digest",
        "stage_start_id",
        "reconciliations",
        "reopenings",
        "review_recoveries",
        "revalidations",
        "workflow_state",
    ):
        if left[fixed] != right[fixed]:
            if fixed == "workflow_state":
                continue
            raise ValueError(f"{fixed} cannot change through a record update")
    changed = sorted(
        (member for member in RecordField if left[member.value] != right[member.value]),
        key=lambda member: member.value,
    )
    document: dict[str, Any] = {"assigned": [member.value for member in changed]}
    for member in changed:
        document[member.value] = right[member.value]
    return RecordUpdates.model_validate_json(json.dumps(document))


def _apply_updates(record: RunRecord, updates: RecordUpdates, **state: Any) -> RunRecord:
    document: dict[str, Any] = json.loads(record.model_dump_json())
    values = json.loads(updates.model_dump_json())
    for member in updates.assigned:
        document[member.value] = values[member.value]
    for name, value in state.items():
        document[name] = value
    try:
        return RunRecord.model_validate_json(json.dumps(document))
    except ValidationError as exc:
        raise EventChainBroken(
            f"an event's typed update produces an invalid record: {exc}"
        ) from None


# --------------------------------------------------------------------------------------
# Payloads
# --------------------------------------------------------------------------------------


class EventPins(OperationPins):
    """Section 5.1's pins. Every event binds all six; none is ever null."""

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str) -> str:
        if STAGE_ID_RE.fullmatch(value) is None:
            raise ValueError("stage_id has an invalid grammar")
        return value


class _BodyChange(MilestoneRunnerModel):
    before_body_digest: str
    after_body_digest: str

    @field_validator("before_body_digest", "after_body_digest")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "body digest")


class RunInitializedPayload(MilestoneRunnerModel):
    event_type: Literal["RUN_INITIALIZED"]
    origin: Literal["EVENT_BACKED_START"]
    record: RunRecord


class RunBaselinedPayload(MilestoneRunnerModel):
    """Section 10.1's compatibility bridge: one known historical governed snapshot, nothing
    synthesized about the history before it."""

    event_type: Literal["RUN_BASELINED"]
    origin: Literal["HISTORICAL_SNAPSHOT_BRIDGE"]
    record: RunRecord
    source_schema_version: int
    source_sha256: str
    source_byte_count: int = Field(ge=1)

    @field_validator("source_schema_version")
    @classmethod
    def _validate_source(cls, value: int) -> int:
        if value != 2:
            raise ValueError("only a state wire version 2 governed snapshot is bridged")
        return value

    @field_validator("source_sha256")
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        return _sha256(value, "source_sha256")


class StageStartBoundPayload(MilestoneRunnerModel):
    """Evidence only: the exact-name authority artifacts the run is bound to, with digests."""

    event_type: Literal["STAGE_START_BOUND"]
    authorization: DurableEvidenceReference
    binding: DurableEvidenceReference
    witness: DurableEvidenceReference


class PolicyPublishedPayload(MilestoneRunnerModel):
    """Evidence only: `policy.json` and its exact-byte digest. It never resolves policy."""

    event_type: Literal["POLICY_PUBLISHED"]
    policy: DurableEvidenceReference


class RunRecordUpdatedPayload(_BodyChange):
    event_type: Literal["RUN_RECORD_UPDATED"]
    updates: RecordUpdates
    evidence: list[DurableEvidenceReference] = Field(
        default_factory=list, max_length=MAX_EVENT_REFERENCES
    )


class RecoveryLedgerName(StrEnum):
    RECONCILIATIONS = "reconciliations"
    REOPENINGS = "reopenings"
    REVIEW_RECOVERIES = "review_recoveries"
    REVALIDATIONS = "revalidations"


LEDGER_BY_COMMAND: Final[dict[RecoveryCommand, RecoveryLedgerName]] = {
    RecoveryCommand.RECONCILE_MILESTONE: RecoveryLedgerName.RECONCILIATIONS,
    RecoveryCommand.REOPEN_MILESTONE: RecoveryLedgerName.REOPENINGS,
    RecoveryCommand.RECOVER_FAILED_REVIEW: RecoveryLedgerName.REVIEW_RECOVERIES,
    RecoveryCommand.REVALIDATE_CORRECTION: RecoveryLedgerName.REVALIDATIONS,
}


class RecoveryLedgerAppendedPayload(_BodyChange):
    """Precisely one append to one closed ledger; no historical entry is rewritten."""

    event_type: Literal["RECOVERY_LEDGER_APPENDED"]
    ledger: RecoveryLedgerName
    entry: RecoveryLedgerEntry
    previous_length: int = Field(ge=0)
    entry_digest: str


class OperationRequestCreatedPayload(MilestoneRunnerModel):
    event_type: Literal["OPERATION_REQUEST_CREATED"]
    operation_id: str
    step: OperationStep
    adapter: AdapterIdentity
    request: DurableEvidenceReference


class _AttemptPayload(MilestoneRunnerModel):
    operation_id: str
    attempt: int = Field(ge=1, le=MAX_OPERATION_ATTEMPTS)


class OperationDispatchIntentPayload(_AttemptPayload):
    event_type: Literal["OPERATION_DISPATCH_INTENT"]
    intent: DurableEvidenceReference


class OperationDispatchReceivedPayload(_AttemptPayload):
    event_type: Literal["OPERATION_DISPATCH_RECEIVED"]
    receipt: DurableEvidenceReference


class OperationPreSpawnFailedPayload(_AttemptPayload):
    event_type: Literal["OPERATION_PRE_SPAWN_FAILED"]
    verdict: DurableEvidenceReference


class OperationResultReceivedPayload(_AttemptPayload):
    """Receipt of a result: raw bytes and execution metadata. No acceptance implication."""

    event_type: Literal["OPERATION_RESULT_RECEIVED"]
    raw_result: DurableEvidenceReference
    outcome: ExecutionOutcome
    transcripts: list[DurableEvidenceReference] = Field(
        default_factory=list, max_length=MAX_EVENT_REFERENCES
    )


class OperationResultValidatedPayload(_AttemptPayload):
    event_type: Literal["OPERATION_RESULT_VALIDATED"]
    verdict: ValidationVerdict
    validated: DurableEvidenceReference


class OperationResultAcceptedPayload(_BodyChange):
    """Commits the existing accepted-result effects. Only a `VALID` verdict is accepted."""

    event_type: Literal["OPERATION_RESULT_ACCEPTED"]
    operation_id: str
    accepted_result_sha256: str
    updates: RecordUpdates


class RejectionSource(StrEnum):
    """What the rejection accounting rests on."""

    #: The terminal validation verdict of the attempt that reached a result.
    VALIDATION = "VALIDATION"
    #: The last attempt's positive no-process-created verdict (the bounded retries ran out).
    PRE_SPAWN_FAILURE = "PRE_SPAWN_FAILURE"
    #: The runner refused the dispatch itself before spawn entry was reached, so no process was
    #: created; no verdict artifact exists, and `diagnostic` says why.
    DISPATCH_REFUSED = "DISPATCH_REFUSED"


class OperationResultRejectedPayload(_BodyChange):
    """An invalid or failed result, with the existing failure accounting and nothing else."""

    event_type: Literal["OPERATION_RESULT_REJECTED"]
    operation_id: str
    source: RejectionSource
    verdict_sha256: str | None = None
    diagnostic: str | None = None
    updates: RecordUpdates

    @model_validator(mode="after")
    def _validate_source(self) -> "OperationResultRejectedPayload":
        if (self.source is RejectionSource.DISPATCH_REFUSED) != (self.verdict_sha256 is None):
            raise ValueError("a verdict digest is carried exactly when a verdict artifact exists")
        if self.diagnostic is not None and not 1 <= len(self.diagnostic) <= 2_000:
            raise ValueError("diagnostic is bounded")
        return self


class StateTransitionedPayload(_BodyChange):
    """One application-approved transition. The store verifies it; it never selects it."""

    event_type: Literal["STATE_TRANSITIONED"]
    from_state: RunStatus
    to_state: RunStatus
    stop_reason: StopReason | None = None
    updates: RecordUpdates
    operation_id: str | None = None


ConstituentPayload = Annotated[
    RunRecordUpdatedPayload
    | RecoveryLedgerAppendedPayload
    | OperationResultAcceptedPayload
    | OperationResultRejectedPayload
    | StateTransitionedPayload,
    Field(discriminator="event_type"),
]


# --------------------------------------------------------------------------------------
# Section 6.1 -- complete logical-mutation declarations
# --------------------------------------------------------------------------------------


class MutationAction(StrEnum):
    RECOVERY_COMMAND = "RECOVERY_COMMAND"
    RESULT_ACCEPTANCE = "RESULT_ACCEPTANCE"
    RESULT_REJECTION = "RESULT_REJECTION"
    APPLICATION_STEP = "APPLICATION_STEP"


class MutationCommand(StrEnum):
    """The existing command that initiated the mutation. No new command is represented."""

    START = "START"
    RESUME = "RESUME"
    ABORT = "ABORT"
    RECONCILE_MILESTONE = "RECONCILE_MILESTONE"
    REOPEN_MILESTONE = "REOPEN_MILESTONE"
    RECOVER_FAILED_REVIEW = "RECOVER_FAILED_REVIEW"
    REVALIDATE_CORRECTION = "REVALIDATE_CORRECTION"
    APPROVE_COMMIT = "APPROVE_COMMIT"
    APPROVE_PUSH = "APPROVE_PUSH"


class RecoveryCommandEvidence(MilestoneRunnerModel):
    """The original, validated recovery outcome, recorded before any of its effects."""

    kind: Literal["RECOVERY_COMMAND"]
    command: RecoveryCommand
    ledger: RecoveryLedgerName
    entry: RecoveryLedgerEntry
    original_ledger_length: int = Field(ge=0)
    budgets_touched: dict[str, int] = Field(default_factory=dict)
    summary: str
    reconstructed_from_verified_evidence: bool = False
    evidence_digest: str | None = None


class ResultEvidence(MilestoneRunnerModel):
    """The original validated-result evidence of a result acceptance or rejection."""

    kind: Literal["RESULT"]
    operation_id: str
    disposition: PersistenceKind
    verdict: DurableEvidenceReference | None = None


class ApplicationStepEvidence(MilestoneRunnerModel):
    """An existing multi-effect application step with no command evidence beyond its manifest."""

    kind: Literal["APPLICATION_STEP"]
    description: str


MutationEvidence = Annotated[
    RecoveryCommandEvidence | ResultEvidence | ApplicationStepEvidence,
    Field(discriminator="kind"),
]


class ManifestConstituent(MilestoneRunnerModel):
    """One constituent's complete semantic content, fixed before any constituent is emitted."""

    index: int = Field(ge=1)
    event_type: LifecycleEventType
    sequence: int = Field(ge=2, le=MAX_EVENT_SEQUENCE)
    state_version: int = Field(ge=2, le=MAX_EVENT_SEQUENCE)
    recorded_at: str
    before_body_digest: str
    after_body_digest: str
    payload: ConstituentPayload


class IntendedTransition(MilestoneRunnerModel):
    """A transition the mutation contains, at its exact manifest position."""

    index: int = Field(ge=1)
    from_state: RunStatus
    to_state: RunStatus
    stop_reason: StopReason | None = None
    updates: RecordUpdates


class MutationDeclaration(MilestoneRunnerModel):
    """Section 6.1's complete durable declaration of one existing logical mutation.

    Its identity is content-addressed over everything below except `mutation_id`, including the
    starting tip, so a different mutation at a later tip can never reuse it. It applies none of
    its listed effects; only its constituents do, in order.
    """

    schema_version: int
    mutation_id: str
    pins: EventPins
    prior_event_id: str
    prior_sequence: int = Field(ge=1)
    prior_state_version: int = Field(ge=1)
    prior_body_digest: str
    action: MutationAction
    command: MutationCommand
    initiated_at: str
    evidence: MutationEvidence
    constituents: list[ManifestConstituent] = Field(
        min_length=2, max_length=MAX_MANIFEST_CONSTITUENTS
    )
    transitions: list[IntendedTransition] = Field(default_factory=list)
    final_body_digest: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        if value != LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unknown declaration schema version")
        return value

    @model_validator(mode="after")
    def _validate_manifest(self) -> "MutationDeclaration":
        if self.prior_state_version != self.prior_sequence:
            raise ValueError("state version equals sequence")
        if mutation_identity(self) != self.mutation_id:
            raise ValueError("mutation_id is not the declaration's content address")
        previous = self.prior_body_digest
        for position, constituent in enumerate(self.constituents, start=1):
            if constituent.index != position:
                raise ValueError("constituent indices must be 1..n in order")
            if constituent.sequence != self.prior_sequence + 1 + position:
                raise ValueError("constituent sequences follow the declaration contiguously")
            if constituent.state_version != constituent.sequence:
                raise ValueError("state version equals sequence")
            if constituent.event_type.value != constituent.payload.event_type:
                raise ValueError("a constituent's type is its payload's type")
            if (
                constituent.before_body_digest != constituent.payload.before_body_digest
                or constituent.after_body_digest != constituent.payload.after_body_digest
                or constituent.before_body_digest != previous
            ):
                raise ValueError("constituent body digests must chain from the prior body")
            _utc(constituent.recorded_at, "recorded_at")
            previous = constituent.after_body_digest
        if previous != self.final_body_digest:
            raise ValueError("final_body_digest is the last constituent's after digest")
        declared = [
            (constituent.index, constituent.payload)
            for constituent in self.constituents
            if isinstance(constituent.payload, StateTransitionedPayload)
        ]
        if [item.index for item in self.transitions] != [index for index, _ in declared]:
            raise ValueError("every transition is declared at its exact manifest position")
        for intended, (_, payload) in zip(self.transitions, declared, strict=True):
            if (
                intended.from_state is not payload.from_state
                or intended.to_state is not payload.to_state
                or intended.stop_reason != payload.stop_reason
                or intended.updates != payload.updates
            ):
                raise ValueError("an intended transition differs from its constituent")
        return self


def mutation_identity(declaration: MutationDeclaration) -> str:
    document = declaration.model_dump(mode="json")
    document.pop("mutation_id")
    return integrity_digest(document)


class ApplicationMutationDeclaredPayload(MilestoneRunnerModel):
    event_type: Literal["APPLICATION_MUTATION_DECLARED"]
    declaration: MutationDeclaration


EventPayload = Annotated[
    RunInitializedPayload
    | RunBaselinedPayload
    | StageStartBoundPayload
    | PolicyPublishedPayload
    | ApplicationMutationDeclaredPayload
    | RunRecordUpdatedPayload
    | RecoveryLedgerAppendedPayload
    | OperationRequestCreatedPayload
    | OperationDispatchIntentPayload
    | OperationDispatchReceivedPayload
    | OperationPreSpawnFailedPayload
    | OperationResultReceivedPayload
    | OperationResultValidatedPayload
    | OperationResultAcceptedPayload
    | OperationResultRejectedPayload
    | StateTransitionedPayload,
    Field(discriminator="event_type"),
]


class IncompleteApplicationMutation(MilestoneRunnerModel):
    """A durable declaration with only a proper applied prefix (section 6.1).

    Carries the complete original manifest and evidence, the intended transitions and how many
    constituents are durable. It is never presented as an ordinary completed mutation, and
    completeness is derived from the chain -- there is no mutable completion flag.
    """

    mutation_id: str
    declaration_sequence: int
    declaration: MutationDeclaration
    intended_transitions: list[IntendedTransition]
    prior_event_id: str
    applied_prefix_length: int


# --------------------------------------------------------------------------------------
# Section 5.1 -- the event envelope
# --------------------------------------------------------------------------------------


class LifecycleEvent(MilestoneRunnerModel):
    """One immutable lifecycle event (section 5.1).

    `event_id` is the SHA-256 of the canonical event omitting only `event_id`; the next event
    chains to the *full-file* digest, which is a different value. Both, and the payload digest,
    are verified on every read.
    """

    schema_version: int
    repository_identity: str
    stage_id: str
    run_id: str
    contract_sha256: str
    policy_digest: str
    stage_start_id: str
    sequence: int
    state_version: int
    event_type: LifecycleEventType
    recorded_at: str
    mutation_id: str | None
    mutation_index: int | None
    payload: EventPayload
    payload_digest: str
    prev_event_digest: str | None
    event_id: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        if value != LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unknown lifecycle event schema version")
        return value

    @field_validator("sequence", "state_version")
    @classmethod
    def _validate_sequence(cls, value: int) -> int:
        if not 1 <= value <= MAX_EVENT_SEQUENCE:
            raise ValueError(f"sequence must be within 1..{MAX_EVENT_SEQUENCE}")
        return value

    @field_validator(
        "contract_sha256", "policy_digest", "stage_start_id", "payload_digest", "event_id"
    )
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @field_validator("recorded_at")
    @classmethod
    def _validate_recorded_at(cls, value: str) -> str:
        return _utc(value, "recorded_at")

    @model_validator(mode="after")
    def _validate_envelope(self) -> "LifecycleEvent":
        EventPins.model_validate(self.pins.model_dump())
        if self.state_version != self.sequence:
            raise ValueError("state_version equals sequence for an event-backed run")
        if (self.prev_event_digest is None) != (self.sequence == 1):
            raise ValueError("only sequence 1 has no predecessor digest")
        if self.prev_event_digest is not None:
            _sha256(self.prev_event_digest, "prev_event_digest")
        if (self.mutation_id is None) != (self.mutation_index is None):
            raise ValueError("mutation_id and mutation_index are set together")
        if self.mutation_id is not None:
            _sha256(self.mutation_id, "mutation_id")
            if self.mutation_index is None or self.mutation_index < 1:
                raise ValueError("mutation_index is 1-based")
        if self.payload.event_type != self.event_type.value:
            raise ValueError("the payload is the event type's own")
        return self

    @property
    def pins(self) -> EventPins:
        return EventPins.model_construct(
            repository_identity=self.repository_identity,
            stage_id=self.stage_id,
            run_id=self.run_id,
            contract_sha256=self.contract_sha256,
            policy_digest=self.policy_digest,
            stage_start_id=self.stage_start_id,
        )

    def canonical_bytes(self) -> bytes:
        return model_bytes(self)

    @property
    def file_name(self) -> str:
        return event_file_name(self.sequence, self.event_type)


def _event_identity(document: dict[str, Any]) -> str:
    material = dict(document)
    material.pop("event_id", None)
    return integrity_digest(material)


def build_event(
    *,
    pins: EventPins,
    sequence: int,
    event_type: LifecycleEventType,
    recorded_at: str,
    payload: MilestoneRunnerModel,
    prev_event_digest: str | None,
    mutation_id: str | None = None,
    mutation_index: int | None = None,
) -> LifecycleEvent:
    """Compute the payload digest and event identity for a new envelope."""
    payload_document = payload.model_dump(mode="json")
    document: dict[str, Any] = {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        **pins.model_dump(mode="json"),
        "sequence": sequence,
        "state_version": sequence,
        "event_type": event_type.value,
        "recorded_at": recorded_at,
        "mutation_id": mutation_id,
        "mutation_index": mutation_index,
        "payload": payload_document,
        "payload_digest": integrity_digest(payload_document),
        "prev_event_digest": prev_event_digest,
    }
    document["event_id"] = _event_identity(document)
    try:
        event = LifecycleEvent.model_validate_json(integrity_bytes(document))
    except ValidationError as exc:
        raise EventConflict(f"the event envelope is invalid: {exc}") from None
    if len(event.canonical_bytes()) > MAX_LIFECYCLE_DOCUMENT_BYTES:
        raise EventConflict("the event exceeds the lifecycle document ceiling")
    return event


def parse_event_bytes(name: str, payload: bytes) -> tuple[LifecycleEvent, str]:
    """Strictly parse one event file: grammar, version, schema, canonical bytes, digests."""
    claimed = parse_event_file_name(name)
    if claimed is None:
        raise EventChainBroken(f"{name!r} is not a canonical event file name")
    if len(payload) > MAX_LIFECYCLE_DOCUMENT_BYTES:
        raise EventChainBroken(f"{name} exceeds the lifecycle document ceiling")
    try:
        document = strict_json_loads(payload)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise EventChainBroken(f"{name} is not strict UTF-8 JSON without duplicate keys") from None
    if not isinstance(document, dict):
        raise EventChainBroken(f"{name} is not a JSON object")
    version = document.get("schema_version")
    if type(version) is not int or version != LIFECYCLE_SCHEMA_VERSION:
        raise LifecycleSchemaUnknown(
            f"{name} carries lifecycle schema_version {version!r}; this build knows only "
            f"{LIFECYCLE_SCHEMA_VERSION}"
        )
    try:
        event = LifecycleEvent.model_validate_json(payload)
    except ValidationError as exc:
        raise EventChainBroken(f"{name} is not a valid lifecycle event: {exc}") from None
    if event.canonical_bytes() != payload:
        raise EventChainBroken(f"{name} is not in canonical integrity serialization")
    if integrity_digest(event.payload.model_dump(mode="json")) != event.payload_digest:
        raise EventChainBroken(f"{name} payload digest does not verify")
    if _event_identity(event.model_dump(mode="json")) != event.event_id:
        raise EventChainBroken(f"{name} event_id does not verify")
    if (event.sequence, event.event_type) != claimed:
        raise EventChainBroken(f"{name} does not match the sequence and type it carries")
    return event, hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------------------
# Section 7.1 -- the publication witness
# --------------------------------------------------------------------------------------


class PublicationWitness(MilestoneRunnerModel):
    """`event-publication.json`: the latest publication intent, and nothing else.

    It is not an alternate source of workflow data. It exists to detect loss of the chain's tail,
    which a hash chain alone cannot see when its whole last suffix is deleted.
    """

    schema_version: int
    pins: EventPins
    sequence: int = Field(ge=1, le=MAX_EVENT_SEQUENCE)
    event_id: str
    event_sha256: str
    prev_event_digest: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        if value != LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unknown witness schema version")
        return value

    @field_validator("event_id", "event_sha256")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @model_validator(mode="after")
    def _validate_predecessor(self) -> "PublicationWitness":
        """R10: the predecessor is null exactly for the genesis event, otherwise a full digest."""
        if (self.prev_event_digest is None) != (self.sequence == 1):
            raise ValueError("only a witness of sequence 1 names no predecessor digest")
        if self.prev_event_digest is not None:
            _sha256(self.prev_event_digest, "prev_event_digest")
        return self


def parse_witness_bytes(payload: bytes) -> PublicationWitness:
    if len(payload) > MAX_LIFECYCLE_DOCUMENT_BYTES:
        raise EventChainBroken("the publication witness exceeds its ceiling")
    try:
        document = strict_json_loads(payload)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise EventChainBroken("the publication witness is not strict JSON") from None
    if not isinstance(document, dict):
        raise EventChainBroken("the publication witness is not a JSON object")
    version = document.get("schema_version")
    if type(version) is not int or version != LIFECYCLE_SCHEMA_VERSION:
        raise LifecycleSchemaUnknown(f"the publication witness carries version {version!r}")
    try:
        witness = PublicationWitness.model_validate_json(payload)
    except ValidationError as exc:
        raise EventChainBroken(f"the publication witness is invalid: {exc}") from None
    if model_bytes(witness) != payload:
        raise EventChainBroken("the publication witness is not canonical")
    return witness


def witness_for(event: LifecycleEvent, event_sha256: str) -> PublicationWitness:
    return PublicationWitness(
        schema_version=LIFECYCLE_SCHEMA_VERSION,
        pins=event.pins,
        sequence=event.sequence,
        event_id=event.event_id,
        event_sha256=event_sha256,
        prev_event_digest=event.prev_event_digest,
    )


# --------------------------------------------------------------------------------------
# Section 6 -- the pure fold
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _OpenMutation:
    declaration: MutationDeclaration
    declaration_sequence: int
    applied: int


@dataclass(frozen=True, slots=True)
class FoldState:
    """Everything the chain proves after its last folded event. Immutable; each step copies."""

    pins: EventPins
    record: RunRecord
    body_digest: str
    sequence: int
    event_id: str
    event_sha256: str
    genesis: LifecycleEventType
    #: The tip event's own `prev_event_digest` (None only at genesis), which the witness must name.
    prev_event_digest: str | None = None
    stage_start_bound: bool = False
    policy_published: bool = False
    open_mutation: _OpenMutation | None = None
    operations: Mapping[str, OperationRecord] = field(default_factory=dict)
    references: tuple[DurableEvidenceReference, ...] = ()
    prospective_paths: tuple[str, ...] = ()
    causative_events: Mapping[str, tuple[str, int, str]] = field(default_factory=dict)

    @property
    def bootstrapped(self) -> bool:
        return self.stage_start_bound and self.policy_published

    @property
    def incomplete(self) -> IncompleteApplicationMutation | None:
        open_mutation = self.open_mutation
        if open_mutation is None:
            return None
        declaration = open_mutation.declaration
        return IncompleteApplicationMutation(
            mutation_id=declaration.mutation_id,
            declaration_sequence=open_mutation.declaration_sequence,
            declaration=declaration,
            intended_transitions=list(declaration.transitions),
            prior_event_id=declaration.prior_event_id,
            applied_prefix_length=open_mutation.applied,
        )


def _broken(detail: str) -> EventChainBroken:
    return EventChainBroken(detail)


def _require_prefix(before: Sequence[Any], after: Sequence[Any], name: str) -> None:
    if len(after) < len(before) or list(after[: len(before)]) != list(before):
        raise _broken(f"{name} is append-only and an event rewrote it")


def _row_identity(row: ProviderRunRecord) -> tuple[Any, ...]:
    return (
        row.sequence,
        row.role,
        row.provider,
        row.milestone_id,
        row.started_at,
        row.prompt_path,
        row.stdout_path,
        row.stderr_path,
    )


def _completed_row(
    before: list[ProviderRunRecord], after: list[ProviderRunRecord]
) -> ProviderRunRecord | None:
    """Enforce the single-row provider completion rule; return a newly completed row, if any."""
    if len(after) == len(before) + 1 and after[: len(before)] == before:
        new = after[-1]
        if before and new.sequence <= before[-1].sequence:
            raise _broken("a provider row must carry a new, higher sequence")
        return new if new.completed_at is not None else None
    if (
        before
        and len(after) == len(before)
        and after[:-1] == before[:-1]
        and before[-1].completed_at is None
        and after[-1].completed_at is not None
        and _row_identity(after[-1]) == _row_identity(before[-1])
    ):
        return after[-1]
    raise _broken("provider_runs changes only by one append or one in-place completion")


def _stem(path: str) -> str:
    return path.rsplit(".", 2)[0] if path.count(".") >= 2 else path


def _check_provider_completion(
    row: ProviderRunRecord, evidence: Sequence[DurableEvidenceReference]
) -> None:
    """Section 8.3: a published completion carries digest-bound transcript references."""
    required = {row.prompt_path, row.stdout_path, row.stderr_path}
    paths = [reference.path for reference in evidence]
    if len(set(paths)) != len(paths):
        raise _broken("a completion names one transcript at most once")
    if any(reference.kind is not EvidenceKind.TRANSCRIPT for reference in evidence):
        raise _broken("a completion's evidence is its transcripts")
    extra = set(paths) - required
    stem = row.prompt_path[: -len("prompt.md")]
    if not required <= set(paths) or any(item != f"{stem}last-message.md" for item in extra):
        raise _broken(
            "a provider completion must carry digest-bound references to its published prompt, "
            "stdout and stderr (and any collected last message)"
        )


def _apply_record_update(
    state: FoldState, payload: RunRecordUpdatedPayload, declaration: MutationDeclaration | None
) -> tuple[RunRecord, tuple[str, ...]]:
    record = state.record
    updates = payload.updates
    if not updates.assigned:
        raise _broken("a record update assigns at least one field")
    illegal = set(updates.assigned) - _RECORD_UPDATE_FIELDS
    recovery = (
        declaration.evidence
        if declaration is not None and isinstance(declaration.evidence, RecoveryCommandEvidence)
        else None
    )
    if recovery is not None:
        illegal -= {RecordField(name) for name in recovery.budgets_touched}
    if illegal:
        raise _broken(f"a record update cannot assign {sorted(member.value for member in illegal)}")
    if (
        RecordField.STOP_REASON in updates.assigned
        and record.workflow_state is not RunStatus.PREFLIGHT
    ):
        raise _broken("only a bound PREFLIGHT refusal records a stop reason without a transition")
    after = _apply_updates(record, updates)
    for member in _COUNTER_FIELDS & set(updates.assigned):
        old = int(getattr(record, member.value))
        new = int(getattr(after, member.value))
        if recovery is not None and member.value in recovery.budgets_touched:
            if new != old + recovery.budgets_touched[member.value]:
                raise _broken("a recovery counter change differs from its declared budget delta")
        elif member is RecordField.REVIEW_ATTEMPTS:
            if new != old + 1:
                raise _broken("review_attempts counts exactly one invocation per update")
        else:
            raise _broken(f"{member.value} does not move through a record update")
    for name in (
        "completed_milestones",
        "milestone_checkpoints",
        "verification_results",
        "deferred_findings",
    ):
        _require_prefix(getattr(record, name), getattr(after, name), name)
    if after.approvals != record.approvals:
        before_rows, after_rows = record.approvals, after.approvals
        appended = len(after_rows) == len(before_rows) + 1 and after_rows[:-1] == before_rows
        settled = (
            before_rows
            and len(after_rows) == len(before_rows)
            and after_rows[:-1] == before_rows[:-1]
            and after_rows[-1].operation is before_rows[-1].operation
            and after_rows[-1].granted_at == before_rows[-1].granted_at
        )
        if not (appended or settled):
            raise _broken("approvals change only by one append or one settlement of the last row")
    prospective: tuple[str, ...] = ()
    completed: ProviderRunRecord | None = None
    if after.provider_runs != record.provider_runs:
        completed = _completed_row(record.provider_runs, after.provider_runs)
        last = after.provider_runs[-1]
        for path in (last.prompt_path, last.stdout_path, last.stderr_path):
            if not is_transcript_path(path):
                raise _broken(f"{path!r} is not a run-contained transcript path declaration")
        if last.completed_at is None:
            prospective = (last.stdout_path, last.stderr_path)
    if completed is not None:
        _check_provider_completion(completed, payload.evidence)
    elif payload.evidence:
        raise _broken("durable evidence is asserted only for a provider completion")
    return after, prospective


def _apply_transition(state: FoldState, payload: StateTransitionedPayload) -> RunRecord:
    record = state.record
    if payload.from_state is not record.workflow_state:
        raise _broken(
            f"the transition leaves {payload.from_state.value}, but the run is at "
            f"{record.workflow_state.value}"
        )
    if (payload.from_state, payload.to_state) not in ALLOWED_RUN_TRANSITIONS:
        raise _broken(f"{payload.from_state.value} -> {payload.to_state.value} is not allowed")
    illegal = set(payload.updates.assigned) - _TRANSITION_UPDATE_FIELDS
    if illegal:
        raise _broken(f"a transition cannot assign {sorted(member.value for member in illegal)}")
    after = _apply_updates(
        record,
        payload.updates,
        workflow_state=payload.to_state.value,
        stop_reason=None if payload.stop_reason is None else payload.stop_reason.value,
    )
    for name in ("completed_milestones", "milestone_checkpoints"):
        _require_prefix(getattr(record, name), getattr(after, name), name)
    if payload.operation_id is not None:
        view = state.operations.get(payload.operation_id)
        if view is None or view.persisted is None:
            raise OperationRecordInvalid("a causative transition names an unpersisted operation")
        if payload.operation_id in state.causative_events:
            raise OperationRecordConflict("an operation's transition is applied exactly once")
    return after


def _apply_ledger(
    state: FoldState,
    payload: RecoveryLedgerAppendedPayload,
    declaration: MutationDeclaration | None,
) -> RunRecord:
    evidence = None if declaration is None else declaration.evidence
    if not isinstance(evidence, RecoveryCommandEvidence):
        raise _broken("a recovery ledger append is a constituent of a declared recovery")
    if payload.entry != evidence.entry or payload.ledger is not evidence.ledger:
        raise _broken("the appended ledger entry is not the declared original entry")
    if LEDGER_BY_COMMAND[payload.entry.command] is not payload.ledger:
        raise _broken("an entry is filed under the ledger its command owns")
    if integrity_digest(payload.entry.model_dump(mode="json")) != payload.entry_digest:
        raise _broken("the ledger entry digest does not verify")
    current = list(getattr(state.record, payload.ledger.value))
    if payload.previous_length != len(current) or evidence.original_ledger_length != len(current):
        raise _broken("the ledger append names a previous length the chain does not have")
    if payload.entry in current:
        raise _broken("a ledger entry is never replayed")
    document: dict[str, Any] = json.loads(state.record.model_dump_json())
    document[payload.ledger.value] = [
        *document[payload.ledger.value],
        json.loads(payload.entry.model_dump_json()),
    ]
    try:
        return RunRecord.model_validate_json(json.dumps(document))
    except ValidationError as exc:
        raise _broken(f"the ledger append produces an invalid record: {exc}") from None


def _counter_delta_ok(
    before: RunRecord, after: RunRecord, member: RecordField, allowed: set[int]
) -> bool:
    return int(getattr(after, member.value)) - int(getattr(before, member.value)) in allowed


def _apply_persistence(
    state: FoldState,
    payload: OperationResultAcceptedPayload | OperationResultRejectedPayload,
    declaration: MutationDeclaration | None,
) -> tuple[RunRecord, Mapping[str, OperationRecord]]:
    evidence = None if declaration is None else declaration.evidence
    if not isinstance(evidence, ResultEvidence) or evidence.operation_id != payload.operation_id:
        raise _broken("a result persistence is a constituent of that result's declaration")
    view = state.operations.get(payload.operation_id)
    if view is None:
        raise OperationRecordInvalid("a result is persisted for an unknown operation")
    if view.persisted is not None:
        raise OperationRecordConflict("an operation's result is persisted exactly once")
    last = view.attempts[-1] if view.attempts else None
    record = state.record
    if isinstance(payload, OperationResultAcceptedPayload):
        if evidence.disposition is not PersistenceKind.ACCEPTED:
            raise _broken("the declaration disposes of this result differently")
        if last is None or last.verdict is not ValidationVerdict.VALID:
            raise OperationRecordInvalid("only a VALID verdict is ever accepted")
        if last.validated_sha256 != payload.accepted_result_sha256:
            raise OperationRecordInvalid("the accepted digest is not the attempt's verdict")
        illegal = set(payload.updates.assigned) - _ACCEPTED_FIELDS
        kind = PersistenceKind.ACCEPTED
        verdict_sha: str | None = payload.accepted_result_sha256
    else:
        if evidence.disposition is not PersistenceKind.REJECTED:
            raise _broken("the declaration disposes of this result differently")
        if payload.source is RejectionSource.VALIDATION:
            if (
                last is None
                or last.validated_sha256 is None
                or last.validated_sha256 != payload.verdict_sha256
            ):
                raise OperationRecordInvalid("a rejection names the attempt's terminal verdict")
        elif payload.source is RejectionSource.PRE_SPAWN_FAILURE:
            if last is None or last.pre_spawn_failure_sha256 != payload.verdict_sha256:
                raise OperationRecordInvalid("a rejection names the last pre-spawn verdict")
        elif last is not None and (
            last.receipt_sha256 is not None
            or last.pre_spawn_failure_sha256 is not None
            or last.raw_result_sha256 is not None
        ):
            raise OperationRecordInvalid("a dispatch refusal precedes any spawn evidence")
        illegal = set(payload.updates.assigned) - _REJECTED_FIELDS
        kind = PersistenceKind.REJECTED
        verdict_sha = payload.verdict_sha256
    if illegal:
        raise _broken(f"a result persistence cannot assign {sorted(m.value for m in illegal)}")
    after = _apply_updates(record, payload.updates)
    for member in _COUNTER_FIELDS & set(payload.updates.assigned):
        if not _counter_delta_ok(record, after, member, {1}):
            raise _broken(f"{member.value} moves by exactly one when a result is persisted")
    if isinstance(payload, OperationResultRejectedPayload):
        if after.successful_review_rounds != record.successful_review_rounds:
            raise _broken("a rejected result consumes no round")
    operations = dict(state.operations)
    operations[payload.operation_id] = view.model_copy(
        update={
            "persisted": kind,
            "persisted_verdict_sha256": verdict_sha,
            "highest_phase": OperationPhase.RESULT_PERSISTED,
        }
    )
    return after, operations


def _require_reference(reference: DurableEvidenceReference, kind: EvidenceKind, path: str) -> None:
    if reference.kind is not kind or reference.path != path:
        raise OperationRecordInvalid(f"{reference.path} is not the expected {kind.value} artifact")


def _apply_operation(
    state: FoldState, event: LifecycleEvent
) -> tuple[Mapping[str, OperationRecord], tuple[DurableEvidenceReference, ...]]:
    payload = event.payload
    operations = dict(state.operations)
    if isinstance(payload, OperationRequestCreatedPayload):
        if operation_id(state.pins.run_id, payload.step) != payload.operation_id:
            raise OperationRecordInvalid("the operation id is not derived from its step tuple")
        if payload.operation_id in operations:
            raise OperationRecordConflict("an operation identity is created exactly once")
        _require_reference(
            payload.request,
            EvidenceKind.OPERATION_REQUEST,
            operation_artifact_path(payload.operation_id, REQUEST_FILE_NAME),
        )
        operations[payload.operation_id] = OperationRecord(
            operation_id=payload.operation_id,
            step=payload.step,
            request_sha256=payload.request.sha256,
            adapter=payload.adapter,
            role=payload.step.role,
            milestone_id=payload.step.milestone_id,
        )
        return operations, (payload.request,)
    assert isinstance(
        payload,
        OperationDispatchIntentPayload
        | OperationDispatchReceivedPayload
        | OperationPreSpawnFailedPayload
        | OperationResultReceivedPayload
        | OperationResultValidatedPayload,
    )
    view = operations.get(payload.operation_id)
    if view is None:
        raise OperationRecordInvalid("an attempt event names an operation with no request")
    if view.persisted is not None:
        raise OperationRecordConflict("a persisted operation's evidence is never extended")
    attempts = list(view.attempts)
    attempt = payload.attempt
    last = attempts[-1] if attempts else None
    phase = view.highest_phase
    references: tuple[DurableEvidenceReference, ...]
    if isinstance(payload, OperationDispatchIntentPayload):
        if attempt != len(attempts) + 1:
            raise OperationRecordConflict("attempt numbers are gap-free and never reused")
        if last is not None and last.pre_spawn_failure_sha256 is None:
            raise OperationRecordConflict(
                "a new attempt follows only a positive pre-spawn failure of the previous one"
            )
        _require_reference(
            payload.intent,
            EvidenceKind.DISPATCH_INTENT,
            operation_artifact_path(
                payload.operation_id, DISPATCH_INTENT_FILE_NAME, attempt=attempt
            ),
        )
        attempts.append(AttemptRecord(attempt=attempt, intent_sha256=payload.intent.sha256))
        phase = OperationPhase.DISPATCH_INTENT
        references = (payload.intent,)
    else:
        if last is None or last.attempt != attempt:
            raise OperationRecordInvalid("attempt evidence follows that attempt's own intent")
        if isinstance(payload, OperationDispatchReceivedPayload):
            if last.receipt_sha256 is not None or last.pre_spawn_failure_sha256 is not None:
                raise OperationRecordConflict(
                    "one attempt holds one receipt and no pre-spawn failure"
                )
            _require_reference(
                payload.receipt,
                EvidenceKind.DISPATCH_RECEIPT,
                operation_artifact_path(
                    payload.operation_id, DISPATCH_RECEIPT_FILE_NAME, attempt=attempt
                ),
            )
            attempts[-1] = last.model_copy(update={"receipt_sha256": payload.receipt.sha256})
            phase = OperationPhase.DISPATCH_RECEIPT
            references = (payload.receipt,)
        elif isinstance(payload, OperationPreSpawnFailedPayload):
            if last.receipt_sha256 is not None or last.pre_spawn_failure_sha256 is not None:
                raise OperationRecordConflict(
                    "one attempt holds one receipt and no pre-spawn failure"
                )
            _require_reference(
                payload.verdict,
                EvidenceKind.PRE_SPAWN_FAILURE,
                operation_artifact_path(
                    payload.operation_id, PRE_SPAWN_FAILED_FILE_NAME, attempt=attempt
                ),
            )
            attempts[-1] = last.model_copy(
                update={"pre_spawn_failure_sha256": payload.verdict.sha256}
            )
            references = (payload.verdict,)
        elif isinstance(payload, OperationResultReceivedPayload):
            if last.receipt_sha256 is None or last.raw_result_sha256 is not None:
                raise OperationRecordInvalid("a result follows its attempt's receipt, once")
            _require_reference(
                payload.raw_result,
                EvidenceKind.RAW_RESULT,
                operation_artifact_path(
                    payload.operation_id, RAW_RESULT_FILE_NAME, attempt=attempt
                ),
            )
            if any(
                reference.kind is not EvidenceKind.TRANSCRIPT for reference in payload.transcripts
            ):
                raise OperationRecordInvalid("a received result's references are its transcripts")
            attempts[-1] = last.model_copy(update={"raw_result_sha256": payload.raw_result.sha256})
            phase = OperationPhase.RESULT_RECEIVED
            references = (payload.raw_result, *payload.transcripts)
        else:
            if last.raw_result_sha256 is None or last.validated_sha256 is not None:
                raise OperationRecordInvalid(
                    "a verdict follows its attempt's received result, once"
                )
            _require_reference(
                payload.validated,
                EvidenceKind.VALIDATED_RESULT,
                operation_artifact_path(
                    payload.operation_id, VALIDATED_RESULT_FILE_NAME, attempt=attempt
                ),
            )
            attempts[-1] = last.model_copy(
                update={"validated_sha256": payload.validated.sha256, "verdict": payload.verdict}
            )
            phase = OperationPhase.RESULT_VALIDATED
            references = (payload.validated,)
    operations[payload.operation_id] = view.model_copy(
        update={"attempts": attempts, "highest_phase": phase}
    )
    return operations, references


def _validate_declaration(
    state: FoldState, event: LifecycleEvent, declaration: MutationDeclaration
) -> None:
    if declaration.pins != state.pins:
        raise _broken("a declaration binds the run's own pins")
    if (
        declaration.prior_event_id != state.event_id
        or declaration.prior_sequence != state.sequence
        or declaration.prior_body_digest != state.body_digest
    ):
        raise _broken("a declaration names the exact tip it was computed at")
    if declaration.initiated_at != event.recorded_at:
        raise _broken("a declaration is recorded at its original command timestamp")
    types = [constituent.event_type for constituent in declaration.constituents]
    if any(member not in CONSTITUENT_TYPES for member in types):
        raise _broken("only body-changing events are declared constituents")
    evidence = declaration.evidence
    ledgers = types.count(LifecycleEventType.RECOVERY_LEDGER_APPENDED)
    persisted = [
        constituent.payload
        for constituent in declaration.constituents
        if isinstance(
            constituent.payload, OperationResultAcceptedPayload | OperationResultRejectedPayload
        )
    ]
    if isinstance(evidence, RecoveryCommandEvidence):
        if declaration.action is not MutationAction.RECOVERY_COMMAND or ledgers != 1 or persisted:
            raise _broken("a recovery declaration carries exactly one ledger append")
        if (
            evidence.entry.command is not evidence.command
            or LEDGER_BY_COMMAND[evidence.command] is not evidence.ledger
        ):
            raise _broken("the recovery evidence names its own command's ledger")
        if evidence.budgets_touched != evidence.entry.budgets_touched:
            raise _broken("the declared budget deltas are the entry's own")
        if len(declaration.transitions) != 1 or (
            declaration.transitions[0].from_state,
            declaration.transitions[0].to_state,
        ) != (evidence.entry.pre_state, evidence.entry.post_state):
            raise _broken("a recovery declares exactly its entry's transition")
        _validate_budget_effects(state.record, declaration, evidence)
    elif isinstance(evidence, ResultEvidence):
        expected = (
            MutationAction.RESULT_ACCEPTANCE
            if evidence.disposition is PersistenceKind.ACCEPTED
            else MutationAction.RESULT_REJECTION
        )
        if declaration.action is not expected or ledgers or len(persisted) != 1:
            raise _broken("a result declaration persists exactly its one result")
        if persisted[0].operation_id != evidence.operation_id:
            raise _broken("the persisted result is the declared operation's")
        _validate_result_evidence(state, evidence, persisted[0])
    else:
        if declaration.action is not MutationAction.APPLICATION_STEP or ledgers or persisted:
            raise _broken("an application step carries no ledger append or result persistence")
    if len(integrity_bytes(event.model_dump(mode="json"))) > MAX_LIFECYCLE_DOCUMENT_BYTES:
        raise _broken("a declaration exceeds the lifecycle document ceiling")


def _counter_assignments(payload: Any) -> RecordUpdates | None:
    """The typed updates a constituent payload assigns, if it assigns any."""
    updates = getattr(payload, "updates", None)
    return updates if isinstance(updates, RecordUpdates) else None


def _validate_budget_effects(
    prior: RunRecord, declaration: MutationDeclaration, evidence: RecoveryCommandEvidence
) -> None:
    """R06: a recovery's declared budget deltas apply exactly once across the whole manifest.

    Validated on the declaration itself -- so before it is published (the store pre-folds it) and
    again on every verified load -- not merely per constituent: each of section 19's five
    counters may be assigned by at most one constituent, the net effect from the declared prior
    body to the manifest's end must be exactly the declared delta (zero for an unbudgeted
    counter), and an unbudgeted counter is never assigned at all. A repeated, omitted or altered
    delta, or before/final values that do not compose to it, refuses.
    """
    names = {member.value for member in _COUNTER_FIELDS}
    unknown = sorted(set(evidence.budgets_touched) - names)
    if unknown:
        raise _broken(f"a recovery declares budget deltas for non-counters {unknown}")
    values = {member: int(getattr(prior, member.value)) for member in _COUNTER_FIELDS}
    initial = dict(values)
    assigned: dict[RecordField, int] = dict.fromkeys(_COUNTER_FIELDS, 0)
    for constituent in declaration.constituents:
        updates = _counter_assignments(constituent.payload)
        if updates is None:
            continue
        for member in _COUNTER_FIELDS & set(updates.assigned):
            assigned[member] += 1
            value = getattr(updates, member.value)
            assert isinstance(value, int)
            values[member] = value
    for member in _COUNTER_FIELDS:
        delta = evidence.budgets_touched.get(member.value, 0)
        if assigned[member] > 1:
            raise _broken(f"the declared {member.value} delta is applied more than once")
        if delta == 0 and assigned[member]:
            raise _broken(f"{member.value} moves although the recovery budgets no change to it")
        if delta != 0 and not assigned[member]:
            raise _broken(f"the declared {member.value} delta is never applied")
        if values[member] != initial[member] + delta:
            raise _broken(
                f"{member.value} goes from {initial[member]} to {values[member]}, not by the "
                f"declared delta {delta}"
            )


def _validate_result_evidence(
    state: FoldState,
    evidence: ResultEvidence,
    persisted: OperationResultAcceptedPayload | OperationResultRejectedPayload,
) -> None:
    """R05: a result declaration's verdict evidence is the operation's own, consistently.

    The declared verdict reference must be the exact artifact and digest the persistence payload
    rests on, and that digest must be the one the chain recorded for the operation's last
    attempt; an acceptance rests only on a `VALID` verdict.
    """
    view = state.operations.get(evidence.operation_id)
    if view is None:
        raise OperationRecordInvalid("a result is declared for an operation with no request")
    last = view.attempts[-1] if view.attempts else None
    reference = evidence.verdict
    if isinstance(persisted, OperationResultAcceptedPayload):
        if (
            reference is None
            or last is None
            or reference.kind is not EvidenceKind.VALIDATED_RESULT
            or reference.path
            != operation_artifact_path(
                evidence.operation_id, VALIDATED_RESULT_FILE_NAME, attempt=last.attempt
            )
            or reference.sha256 != persisted.accepted_result_sha256
            or reference.sha256 != last.validated_sha256
            or last.verdict is not ValidationVerdict.VALID
        ):
            raise OperationRecordInvalid(
                "an acceptance is declared on exactly the last attempt's VALID verdict"
            )
        return
    if persisted.source is RejectionSource.DISPATCH_REFUSED:
        if reference is not None:
            raise OperationRecordInvalid("a dispatch refusal declares no verdict artifact")
        return
    if persisted.source is RejectionSource.VALIDATION:
        kind, name = EvidenceKind.VALIDATED_RESULT, VALIDATED_RESULT_FILE_NAME
        digest = None if last is None else last.validated_sha256
    else:
        kind, name = EvidenceKind.PRE_SPAWN_FAILURE, PRE_SPAWN_FAILED_FILE_NAME
        digest = None if last is None else last.pre_spawn_failure_sha256
    if (
        reference is None
        or last is None
        or reference.kind is not kind
        or reference.path
        != operation_artifact_path(evidence.operation_id, name, attempt=last.attempt)
        or reference.sha256 != persisted.verdict_sha256
        or reference.sha256 != digest
    ):
        raise OperationRecordInvalid(
            "a rejection is declared on exactly the last attempt's terminal verdict"
        )


def _genesis(event: LifecycleEvent, event_sha256: str, expected: EventPins | None) -> FoldState:
    if event.sequence != 1 or event.event_type not in _GENESIS_TYPES:
        raise _broken("a chain begins at sequence 1 with RUN_INITIALIZED or RUN_BASELINED")
    if event.mutation_id is not None:
        raise _broken("a genesis event is never a constituent")
    payload = event.payload
    assert isinstance(payload, RunInitializedPayload | RunBaselinedPayload)
    record = payload.record
    pins = event.pins
    if expected is not None and pins != expected:
        raise _broken("the chain belongs to another run, stage, contract or policy")
    if (
        record.run_id != pins.run_id
        or record.repository_identity != pins.repository_identity
        or record.contract_sha256 != pins.contract_sha256
        or record.policy_digest != pins.policy_digest
        or record.stage_start_id != pins.stage_start_id
    ):
        raise _broken("the genesis record disagrees with the event pins")
    if isinstance(payload, RunInitializedPayload) and record.workflow_state is not RunStatus.IDLE:
        raise _broken("a new run is initialized at IDLE")
    return FoldState(
        pins=pins,
        record=record,
        body_digest=body_digest(record),
        sequence=1,
        event_id=event.event_id,
        event_sha256=event_sha256,
        genesis=event.event_type,
    )


def fold_step(
    state: FoldState | None,
    event: LifecycleEvent,
    event_sha256: str,
    *,
    expected: EventPins | None = None,
) -> FoldState:
    """Fold one verified event onto `state`, validating every semantic rule (section 6)."""
    if state is None:
        return _genesis(event, event_sha256, expected)
    if event.pins != state.pins:
        raise _broken("an event carries pins foreign to this chain")
    if event.sequence != state.sequence + 1:
        raise _broken(f"sequence {event.sequence} does not follow {state.sequence}")
    if event.prev_event_digest != state.event_sha256:
        raise _broken(f"event {event.sequence} does not chain to its predecessor's digest")
    if event.event_type in _GENESIS_TYPES:
        raise _broken("a genesis event appears only once, first")
    payload = event.payload
    declaration: MutationDeclaration | None = None
    open_mutation = state.open_mutation
    if open_mutation is not None:
        declaration = open_mutation.declaration
        constituent = declaration.constituents[open_mutation.applied]
        if (
            event.mutation_id != declaration.mutation_id
            or event.mutation_index != constituent.index
            or event.event_type is not constituent.event_type
            or event.recorded_at != constituent.recorded_at
            or event.sequence != constituent.sequence
            or payload.model_dump(mode="json") != constituent.payload.model_dump(mode="json")
        ):
            raise _broken(
                "an incomplete declared mutation is followed only by its next declared "
                "constituent, exactly as declared"
            )
    elif event.mutation_id is not None:
        raise _broken("a constituent event appears without its durable declaration")
    if not state.bootstrapped:
        expected_type = (
            LifecycleEventType.STAGE_START_BOUND
            if not state.stage_start_bound
            else LifecycleEventType.POLICY_PUBLISHED
        )
        if event.event_type is not expected_type:
            raise _broken("Stage Start binding and policy evidence precede every other event")
    if event.event_type in _DECLARED_ONLY_TYPES and declaration is None:
        raise _broken(f"{event.event_type.value} exists only inside a declared mutation")

    record = state.record
    operations = state.operations
    references = state.references
    prospective = state.prospective_paths
    causative = state.causative_events
    changes: dict[str, Any] = {}
    body_change: _BodyChange | None = None

    if isinstance(payload, StageStartBoundPayload):
        if state.stage_start_bound:
            raise _broken("Stage Start binding evidence is recorded once")
        for reference, kind in (
            (payload.authorization, EvidenceKind.STAGE_START_AUTHORIZATION),
            (payload.binding, EvidenceKind.STAGE_START_BINDING),
            (payload.witness, EvidenceKind.STAGE_START_WITNESS),
        ):
            if reference.kind is not kind or reference.path != stage_start_reference_path(
                kind, state.pins.stage_start_id
            ):
                raise _broken("Stage Start evidence names the run's own exact-name artifacts")
        references = (*references, payload.authorization, payload.binding, payload.witness)
        changes["stage_start_bound"] = True
    elif isinstance(payload, PolicyPublishedPayload):
        if state.policy_published or payload.policy.kind is not EvidenceKind.POLICY:
            raise _broken("policy evidence is recorded once, for policy.json")
        references = (*references, payload.policy)
        changes["policy_published"] = True
    elif isinstance(payload, ApplicationMutationDeclaredPayload):
        if open_mutation is not None:
            raise _broken("mutations are never interleaved")
        _validate_declaration(state, event, payload.declaration)
        changes["open_mutation"] = _OpenMutation(
            declaration=payload.declaration, declaration_sequence=event.sequence, applied=0
        )
    elif isinstance(payload, RunRecordUpdatedPayload):
        record, prospective_new = _apply_record_update(state, payload, declaration)
        references = (*references, *payload.evidence)
        prospective = prospective_new
        body_change = payload
    elif isinstance(payload, RecoveryLedgerAppendedPayload):
        record = _apply_ledger(state, payload, declaration)
        body_change = payload
    elif isinstance(payload, OperationResultAcceptedPayload | OperationResultRejectedPayload):
        record, operations = _apply_persistence(state, payload, declaration)
        body_change = payload
    elif isinstance(payload, StateTransitionedPayload):
        record = _apply_transition(state, payload)
        body_change = payload
        if payload.operation_id is not None:
            view = operations[payload.operation_id]
            operations = dict(operations)
            operations[payload.operation_id] = view.model_copy(
                update={
                    "transition_event_id": event.event_id,
                    "transition_state_version": event.state_version,
                    "highest_phase": OperationPhase.TRANSITION_APPLIED,
                }
            )
            causative = dict(causative)
            causative[payload.operation_id] = (event.event_id, event.state_version, event_sha256)
    else:
        operations, new_references = _apply_operation(state, event)
        references = (*references, *new_references)

    digest = state.body_digest
    if body_change is not None:
        if body_change.before_body_digest != state.body_digest:
            raise _broken(
                f"event {event.sequence} names a before-body digest the chain does not have"
            )
        digest = body_digest(record)
        if body_change.after_body_digest != digest:
            raise _broken(
                f"event {event.sequence} names an after-body digest its update does not produce"
            )

    if open_mutation is not None:
        applied = open_mutation.applied + 1
        changes["open_mutation"] = (
            None
            if applied == len(open_mutation.declaration.constituents)
            else replace(open_mutation, applied=applied)
        )
    return replace(
        state,
        record=record,
        body_digest=digest,
        sequence=event.sequence,
        event_id=event.event_id,
        event_sha256=event_sha256,
        prev_event_digest=event.prev_event_digest,
        operations=operations,
        references=references,
        prospective_paths=prospective,
        causative_events=causative,
        **changes,
    )


def fold(
    events: Iterable[tuple[LifecycleEvent, str]], *, expected: EventPins | None = None
) -> FoldState:
    """Deterministically validate and reconstruct a chain.

    Pure: it reads, writes and runs nothing.
    """
    state: FoldState | None = None
    for event, digest in events:
        state = fold_step(state, event, digest, expected=expected)
    if state is None:
        raise _broken("an event-backed run has no events")
    return state


def check_witness(state: FoldState, witness: PublicationWitness | None) -> None:
    """The witness must name exactly the chain's final event (section 7.1)."""
    if witness is None:
        raise _broken("the publication witness is mandatory once genesis publication began")
    if witness.pins != state.pins:
        raise _broken("the publication witness belongs to another run")
    if witness.sequence == state.sequence + 1:
        raise _broken(
            f"the publication witness names event {witness.sequence}, which is missing: the "
            "chain's tail was lost or its publication never completed"
        )
    if (
        witness.sequence != state.sequence
        or witness.event_id != state.event_id
        or witness.event_sha256 != state.event_sha256
    ):
        raise _broken("the publication witness does not name the chain's final event")
    if witness.prev_event_digest != state.prev_event_digest:
        # R10: the witnessed event's actual predecessor, not merely a well-formed digest.
        raise _broken("the publication witness names a predecessor its event does not chain to")


def check_operation_artifact(
    state: FoldState, reference: DurableEvidenceReference, artifact: MilestoneRunnerModel
) -> None:
    """R05: an immutable operation artifact agrees with the chain's facts about it.

    `state` is the fold *after* the event asserting `reference`. Digest and canonical bytes are
    already verified, so a consistently rehashed chain can still carry an artifact whose content
    contradicts the events: a request for another step or adapter, an intent for another request
    or adapter, a receipt or pre-spawn verdict for another intent, a verdict for another raw
    result, role or milestone, or a verdict the event does not report. Each refuses
    `OPERATION_RECORD_INVALID`; an INVALID artifact is never accepted on a VALID event fact.
    """
    values = artifact.model_dump(mode="json")
    identifier = values.get("operation_id")
    view = state.operations.get(identifier) if isinstance(identifier, str) else None
    if view is None:
        raise OperationRecordInvalid(f"{reference.path} names an operation the chain lacks")
    if isinstance(artifact, OperationRequest):
        if (
            reference.sha256 != view.request_sha256
            or artifact.step != view.step
            or artifact.adapter != view.adapter
            or artifact.role is not view.role
            or artifact.milestone_id != view.milestone_id
        ):
            raise OperationRecordInvalid(f"{reference.path} contradicts its REQUEST_CREATED fact")
        return
    number = values.get("attempt")
    attempt = next((item for item in view.attempts if item.attempt == number), None)
    if attempt is None:
        raise OperationRecordInvalid(f"{reference.path} names an attempt the chain lacks")
    if isinstance(artifact, DispatchIntent):
        consistent = (
            reference.sha256 == attempt.intent_sha256
            and artifact.request_sha256 == view.request_sha256
            and artifact.adapter == view.adapter
        )
    elif isinstance(artifact, DispatchReceipt):
        consistent = (
            reference.sha256 == attempt.receipt_sha256
            and artifact.intent_sha256 == attempt.intent_sha256
        )
    elif isinstance(artifact, PreSpawnFailure):
        consistent = (
            reference.sha256 == attempt.pre_spawn_failure_sha256
            and artifact.intent_sha256 == attempt.intent_sha256
        )
    elif isinstance(artifact, ValidatedResult):
        consistent = (
            reference.sha256 == attempt.validated_sha256
            and artifact.role is view.role
            and artifact.raw_result_sha256 == attempt.raw_result_sha256
            and artifact.verdict is attempt.verdict
            and (
                artifact.milestone_result is None
                or artifact.milestone_result.milestone == view.milestone_id
            )
        )
    else:
        raise OperationRecordInvalid(f"{reference.path} is not an asserted operation artifact")
    if not consistent:
        raise OperationRecordInvalid(f"{reference.path} contradicts the chain's facts about it")


class ProjectionStatus(StrEnum):
    CURRENT = "CURRENT"
    MISSING = "MISSING"
    STALE = "STALE"
    DAMAGED = "DAMAGED"


def projection_status(state: FoldState, payload: bytes | None) -> ProjectionStatus:
    """Compare `state.json` with the fold. A projection ahead of the chain is refused."""
    expected = projection_bytes(
        state.record, state_version=state.sequence, last_event_id=state.event_id
    )
    if payload is None:
        return ProjectionStatus.MISSING
    if payload == expected:
        return ProjectionStatus.CURRENT
    try:
        document = strict_json_loads(payload)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return ProjectionStatus.DAMAGED
    if not isinstance(document, dict):
        return ProjectionStatus.DAMAGED
    version = document.get("state_version")
    if document.get("schema_version") == 3 and type(version) is int and version > state.sequence:
        raise _broken(
            f"state.json claims version {version}, later than the verified chain's "
            f"{state.sequence}; state is never rolled backward silently"
        )
    if document.get("schema_version") == 3 and type(version) is int and version < state.sequence:
        return ProjectionStatus.STALE
    return ProjectionStatus.DAMAGED


# --------------------------------------------------------------------------------------
# Redaction before digest construction (section 7.3)
# --------------------------------------------------------------------------------------


def redact_value(value: Any) -> tuple[Any, list[RedactionFinding]]:
    """Redact every string of a JSON-shaped value, returning the findings that fired."""
    findings: list[RedactionFinding] = []

    def visit(item: Any) -> Any:
        if isinstance(item, str):
            text, fired = redact_text(item)
            findings.extend(fired)
            return text
        if isinstance(item, list):
            return [visit(element) for element in item]
        if isinstance(item, dict):
            return {key: visit(element) for key, element in item.items()}
        return item

    return visit(value), findings


def redact_record(record: RunRecord) -> tuple[RunRecord, list[RedactionFinding]]:
    """The record with free text redacted before any digest is computed over it."""
    document, findings = redact_value(json.loads(record.model_dump_json()))
    if not findings:
        return record, []
    try:
        return RunRecord.model_validate_json(json.dumps(document)), findings
    except ValidationError as exc:
        raise EventConflict(
            f"redaction would change the record's structure, so it is not published: {exc}"
        ) from None


# --------------------------------------------------------------------------------------
# EventStore coordination
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChainEntry:
    """The bounded metadata retained for one verified event (section 7.3, R12).

    A verified load and a held event store keep only this per event -- never the event body.
    Each body is parsed, hash-verified and folded as the chain is consumed and then dropped; the
    fold state carries everything later steps need, and these identities let durability be
    confirmed and duplicates recognized without the bytes.
    """

    sequence: int
    event_type: LifecycleEventType
    event_id: str
    state_version: int
    recorded_at: str
    sha256: str
    references: tuple[DurableEvidenceReference, ...]

    @classmethod
    def of(cls, event: LifecycleEvent, sha256: str) -> "ChainEntry":
        return cls(
            sequence=event.sequence,
            event_type=event.event_type,
            event_id=event.event_id,
            state_version=event.state_version,
            recorded_at=event.recorded_at,
            sha256=sha256,
            references=_payload_references(event),
        )

    @property
    def file_name(self) -> str:
        return event_file_name(self.sequence, self.event_type)


@dataclass(frozen=True, slots=True)
class StoredChain:
    """What one bounded diagnostic read of the run directory returned, before semantic checks.

    The verified load does not use this: it streams (R12). It remains for explicit diagnostic
    reads that ask for every event body.
    """

    events: tuple[tuple[LifecycleEvent, str], ...]
    witness: PublicationWitness | None
    projection: bytes | None


class LifecycleStorage(Protocol):
    """The durable I/O `state.py` supplies. Every write is exclusive or atomic, descriptor-bound
    under the held and verified lock, through the redaction boundary, and durability-confirmed."""

    def read_chain(self) -> StoredChain: ...

    def publish_evidence(
        self, path: str, text: str, *, structural: bool
    ) -> DurableEvidenceReference: ...

    def publish_witness(self, payload: bytes) -> None: ...

    def publish_event(self, name: str, payload: bytes) -> None: ...

    def publish_projection(self, payload: bytes) -> None: ...

    def witness_bytes(self) -> bytes | None: ...

    def confirm_event(self, name: str, sha256: str) -> None: ...

    def confirm_witness(self, sha256: str) -> None: ...

    def confirm_references(self, references: Sequence[DurableEvidenceReference]) -> None: ...

    def verify_references(
        self, references: Sequence[DurableEvidenceReference]
    ) -> Sequence[tuple[DurableEvidenceReference, MilestoneRunnerModel]]: ...

    def check_tip(self, sequence: int, event_sha256: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AppendedEvent:
    event: LifecycleEvent
    sha256: str
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class PlannedChange:
    """One constituent the application already computed: its type and its before/after records.

    `STATE_TRANSITIONED` constituents are planned here too, so that the declaration carries their
    complete content; they are still appended only through :meth:`EventStore.append_transition`.
    """

    event_type: LifecycleEventType
    before: RunRecord
    after: RunRecord
    recorded_at: str
    operation_id: str | None = None
    evidence: tuple[DurableEvidenceReference, ...] = ()
    ledger_entry: RecoveryLedgerEntry | None = None
    accepted_result_sha256: str | None = None
    rejection_source: RejectionSource | None = None
    verdict_sha256: str | None = None
    diagnostic: str | None = None


class _AppendAuthority:
    """A private capability only :meth:`EventStore.append_transition` holds."""


_TRANSITION_AUTHORITY: Final = _AppendAuthority()


class EventStore:
    """Coordinates section 7.2's append protocol over a :class:`LifecycleStorage` (section 11).

    Holds the verified fold of the chain for the current hold. It records facts and verifies
    them; it chooses nothing. Every append validates the candidate by folding it onto the
    verified state *before* anything is published, so a conflicting reuse is a typed refusal
    ahead of any effect.
    """

    def __init__(self, storage: LifecycleStorage, *, pins: EventPins) -> None:
        self._storage = storage
        self._pins = pins
        self._state: FoldState | None = None
        self._entries: list[ChainEntry] = []
        self.journal = OperationJournal(self)

    # -- state ----------------------------------------------------------------------------

    @property
    def pins(self) -> EventPins:
        return self._pins

    @property
    def state(self) -> FoldState | None:
        return self._state

    @property
    def entries(self) -> tuple[ChainEntry, ...]:
        """The bounded per-event metadata this hold verified or appended (R12)."""
        return tuple(self._entries)

    @property
    def events(self) -> tuple[tuple[LifecycleEvent, str], ...]:
        """Diagnostic only: re-read the event bodies this store verified, digest-checked.

        Nothing in the append protocol or a verified load uses this; it never retains bodies.
        """
        chain = self._storage.read_chain().events[: len(self._entries)]
        if [digest for _, digest in chain] != [entry.sha256 for entry in self._entries]:
            raise _broken("the stored event bodies are not the chain this hold verified")
        return chain

    def adopt(self, chain: Sequence[ChainEntry], state: FoldState | None) -> None:
        """Adopt the metadata of a chain the storage verified under the held lock."""
        self._entries = list(chain)
        self._state = state

    def require_state(self) -> FoldState:
        if self._state is None:
            raise _broken("the event chain has not been opened or has no genesis")
        return self._state

    @property
    def record(self) -> RunRecord:
        return self.require_state().record

    def operation(self, identifier: str) -> OperationRecord:
        view = self.require_state().operations.get(identifier)
        if view is None:
            raise OperationRecordInvalid(f"operation {identifier} has no durable request")
        return view

    @staticmethod
    def redacted_text(text: str) -> str:
        return redact_text(text)[0]

    # -- the append protocol --------------------------------------------------------------

    def _envelope(
        self,
        event_type: LifecycleEventType,
        payload: MilestoneRunnerModel,
        recorded_at: str,
        *,
        mutation_id: str | None = None,
        mutation_index: int | None = None,
    ) -> LifecycleEvent:
        state = self._state
        sequence = 1 if state is None else state.sequence + 1
        if sequence > MAX_EVENT_SEQUENCE:
            raise EventConflict("the run's event sequence is exhausted")
        return build_event(
            pins=self._pins,
            sequence=sequence,
            event_type=event_type,
            recorded_at=recorded_at,
            payload=payload,
            prev_event_digest=None if state is None else state.event_sha256,
            mutation_id=mutation_id,
            mutation_index=mutation_index,
        )

    def publish_envelope(
        self, envelope: LifecycleEvent, *, _authority: _AppendAuthority | None = None
    ) -> AppendedEvent:
        """Publish one envelope, or recognize its exact duplicate (section 7.2).

        A duplicate is recognized before allocating another sequence or touching the witness, and
        is returned only after durability confirmation. The same sequence with other bytes, or
        a sequence that is not the next one, refuses.
        """
        payload = envelope.canonical_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        state = self._state
        tip = 0 if state is None else state.sequence
        if envelope.sequence <= tip:
            existing = self._entries[envelope.sequence - 1]
            if existing.sha256 != digest:
                raise EventConflict(f"sequence {envelope.sequence} already holds a different event")
            self.confirm_established()
            return AppendedEvent(event=envelope, sha256=digest, duplicate=True)
        if (
            envelope.event_type is LifecycleEventType.STATE_TRANSITIONED
            and _authority is not _TRANSITION_AUTHORITY
        ):
            raise EventConflict("a transition is appended only through append_transition")
        if envelope.sequence != tip + 1:
            raise EventConflict(
                f"the envelope was built for sequence {envelope.sequence}, but the verified tip "
                f"is {tip}: a stale expected tip refuses"
            )
        folded = fold_step(state, envelope, digest, expected=self._pins)
        if state is not None:
            self._storage.check_tip(state.sequence, state.event_sha256)
        references = _payload_references(envelope)
        for reference, artifact in self._storage.verify_references(references):
            check_operation_artifact(folded, reference, artifact)
        self._storage.confirm_references(references)
        self._storage.publish_witness(model_bytes(witness_for(envelope, digest)))
        self._storage.publish_event(envelope.file_name, payload)
        self._entries.append(ChainEntry.of(envelope, digest))
        self._state = folded
        self._storage.publish_projection(
            projection_bytes(
                folded.record, state_version=folded.sequence, last_event_id=folded.event_id
            )
        )
        return AppendedEvent(event=envelope, sha256=digest)

    def confirm_established(self) -> None:
        """R07: confirm everything an exact-duplicate acknowledgment relies on (section 7.5).

        Under the current hold: the on-disk chain and witness are exactly the verified ones (no
        lost, added or replaced event, no missing, corrupt or regressed witness); the witness
        names the verified tip with its actual predecessor; and the witness, every event of the
        established prefix (the duplicate's predecessors included) and every immutable artifact
        they reference pass their durability barriers. Any failure refuses the acknowledgment.
        """
        state = self.require_state()
        self._storage.check_tip(state.sequence, state.event_sha256)
        witness = self._storage.witness_bytes()
        check_witness(state, None if witness is None else parse_witness_bytes(witness))
        assert witness is not None
        self._storage.confirm_witness(hashlib.sha256(witness).hexdigest())
        for entry in self._entries:
            self._storage.confirm_event(entry.file_name, entry.sha256)
            self._storage.confirm_references(entry.references)

    def _append(
        self,
        event_type: LifecycleEventType,
        payload: MilestoneRunnerModel,
        recorded_at: str,
    ) -> AppendedEvent:
        if self._state is not None and self._state.open_mutation is not None:
            raise ApplicationMutationIncomplete(
                "a declared mutation is incomplete; nothing else is appended",
                mutation=self._state.incomplete,  # type: ignore[arg-type]
            )
        return self.publish_envelope(self._envelope(event_type, payload, recorded_at))

    # -- genesis and bootstrap ------------------------------------------------------------

    def initialize(self, record: RunRecord, recorded_at: str) -> AppendedEvent:
        payload = RunInitializedPayload(
            event_type="RUN_INITIALIZED", origin="EVENT_BACKED_START", record=record
        )
        return self._append(LifecycleEventType.RUN_INITIALIZED, payload, recorded_at)

    def baseline(
        self, record: RunRecord, *, source_sha256: str, source_byte_count: int, recorded_at: str
    ) -> AppendedEvent:
        payload = RunBaselinedPayload(
            event_type="RUN_BASELINED",
            origin="HISTORICAL_SNAPSHOT_BRIDGE",
            record=record,
            source_schema_version=2,
            source_sha256=source_sha256,
            source_byte_count=source_byte_count,
        )
        return self._append(LifecycleEventType.RUN_BASELINED, payload, recorded_at)

    def bind_stage_start(
        self,
        *,
        authorization: DurableEvidenceReference,
        binding: DurableEvidenceReference,
        witness: DurableEvidenceReference,
        recorded_at: str,
    ) -> AppendedEvent:
        payload = StageStartBoundPayload(
            event_type="STAGE_START_BOUND",
            authorization=authorization,
            binding=binding,
            witness=witness,
        )
        return self._append(LifecycleEventType.STAGE_START_BOUND, payload, recorded_at)

    def record_policy(self, policy: DurableEvidenceReference, recorded_at: str) -> AppendedEvent:
        payload = PolicyPublishedPayload(event_type="POLICY_PUBLISHED", policy=policy)
        return self._append(LifecycleEventType.POLICY_PUBLISHED, payload, recorded_at)

    # -- body events ----------------------------------------------------------------------

    def record_update(
        self,
        before: RunRecord,
        after: RunRecord,
        recorded_at: str,
        *,
        evidence: Sequence[DurableEvidenceReference] = (),
    ) -> AppendedEvent:
        self._require_current(before)
        payload = _record_updated_payload(before, after, evidence)
        return self._append(LifecycleEventType.RUN_RECORD_UPDATED, payload, recorded_at)

    def append_transition(
        self,
        before: RunRecord,
        after: RunRecord,
        recorded_at: str,
        *,
        operation_id: str | None = None,
        constituent: tuple[MutationDeclaration, int] | None = None,
    ) -> AppendedEvent:
        """Record one application-approved transition. Called only by `application.py`.

        The store verifies the typed before/after records against the closed table and the chain;
        it cannot select a target state and has no retry, recovery, review or successor logic.
        """
        payload = _transition_payload(before, after, operation_id)
        if constituent is not None:
            declaration, index = constituent
            return self._publish_constituent(
                declaration, index, payload, _authority=_TRANSITION_AUTHORITY
            )
        self._require_current(before)
        if self._state is not None and self._state.open_mutation is not None:
            raise ApplicationMutationIncomplete(
                "a declared mutation is incomplete; nothing else is appended",
                mutation=self._state.incomplete,  # type: ignore[arg-type]
            )
        return self.publish_envelope(
            self._envelope(LifecycleEventType.STATE_TRANSITIONED, payload, recorded_at),
            _authority=_TRANSITION_AUTHORITY,
        )

    def _require_current(self, before: RunRecord) -> None:
        state = self.require_state()
        if body_digest(before) != state.body_digest:
            raise EventConflict(
                "the application's record is not the verified tip; a stale record is never "
                "appended against"
            )

    # -- section 6.1 ------------------------------------------------------------------------

    def declare(
        self,
        *,
        action: MutationAction,
        command: MutationCommand,
        initiated_at: str,
        evidence: RecoveryCommandEvidence | ResultEvidence | ApplicationStepEvidence,
        changes: Sequence[PlannedChange],
    ) -> MutationDeclaration:
        """Durably declare one complete logical mutation before any constituent effect."""
        state = self.require_state()
        if state.open_mutation is not None:
            raise ApplicationMutationIncomplete(
                "a declared mutation is incomplete; nothing else is declared",
                mutation=state.incomplete,  # type: ignore[arg-type]
            )
        if len(changes) < 2:
            raise EventConflict("a declaration covers a mutation of two or more constituents")
        if body_digest(changes[0].before) != state.body_digest:
            raise EventConflict("the declared mutation does not start at the verified tip")
        constituents: list[ManifestConstituent] = []
        transitions: list[IntendedTransition] = []
        for index, change in enumerate(changes, start=1):
            if index > 1 and body_digest(change.before) != body_digest(changes[index - 2].after):
                raise EventConflict("declared constituents must chain record to record")
            payload = _planned_payload(change)
            sequence = state.sequence + 1 + index
            constituents.append(
                ManifestConstituent(
                    index=index,
                    event_type=change.event_type,
                    sequence=sequence,
                    state_version=sequence,
                    recorded_at=change.recorded_at,
                    before_body_digest=payload.before_body_digest,
                    after_body_digest=payload.after_body_digest,
                    payload=payload,  # type: ignore[arg-type]
                )
            )
            if isinstance(payload, StateTransitionedPayload):
                transitions.append(
                    IntendedTransition(
                        index=index,
                        from_state=payload.from_state,
                        to_state=payload.to_state,
                        stop_reason=payload.stop_reason,
                        updates=payload.updates,
                    )
                )
        document: dict[str, Any] = {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "pins": state.pins.model_dump(mode="json"),
            "prior_event_id": state.event_id,
            "prior_sequence": state.sequence,
            "prior_state_version": state.sequence,
            "prior_body_digest": state.body_digest,
            "action": action.value,
            "command": command.value,
            "initiated_at": initiated_at,
            "evidence": evidence.model_dump(mode="json"),
            "constituents": [item.model_dump(mode="json") for item in constituents],
            "transitions": [item.model_dump(mode="json") for item in transitions],
            "final_body_digest": body_digest(changes[-1].after),
        }
        document["mutation_id"] = integrity_digest(document)
        try:
            declaration = MutationDeclaration.model_validate_json(integrity_bytes(document))
        except ValidationError as exc:
            raise EventConflict(f"the mutation declaration is invalid: {exc}") from None
        declared = ApplicationMutationDeclaredPayload(
            event_type="APPLICATION_MUTATION_DECLARED", declaration=declaration
        )
        envelope = self._envelope(
            LifecycleEventType.APPLICATION_MUTATION_DECLARED, declared, initiated_at
        )
        if len(envelope.canonical_bytes()) > MAX_LIFECYCLE_DOCUMENT_BYTES:
            raise EventConflict("the declared manifest exceeds the event-size ceiling")
        # Every constituent must fold legally *before* the declaration exists: a manifest that
        # could never complete is refused with no byte published (sections 6.1 and 7.2).
        simulated = fold_step(
            state,
            envelope,
            hashlib.sha256(envelope.canonical_bytes()).hexdigest(),
            expected=self._pins,
        )
        for constituent in declaration.constituents:
            candidate = build_event(
                pins=self._pins,
                sequence=constituent.sequence,
                event_type=constituent.event_type,
                recorded_at=constituent.recorded_at,
                payload=constituent.payload,
                prev_event_digest=simulated.event_sha256,
                mutation_id=declaration.mutation_id,
                mutation_index=constituent.index,
            )
            simulated = fold_step(
                simulated,
                candidate,
                hashlib.sha256(candidate.canonical_bytes()).hexdigest(),
                expected=self._pins,
            )
        self.publish_envelope(envelope)
        return declaration

    def append_constituent(self, declaration: MutationDeclaration, index: int) -> AppendedEvent:
        """Emit the next predeclared non-transition constituent, exactly as declared."""
        constituent = declaration.constituents[index - 1]
        if constituent.event_type is LifecycleEventType.STATE_TRANSITIONED:
            raise EventConflict("a declared transition is appended only through append_transition")
        return self._publish_constituent(declaration, index, constituent.payload)

    def _publish_constituent(
        self,
        declaration: MutationDeclaration,
        index: int,
        payload: MilestoneRunnerModel,
        *,
        _authority: _AppendAuthority | None = None,
    ) -> AppendedEvent:
        constituent = declaration.constituents[index - 1]
        if payload.model_dump(mode="json") != constituent.payload.model_dump(mode="json"):
            raise EventConflict("a constituent is emitted exactly as its declaration fixed it")
        envelope = self._envelope(
            constituent.event_type,
            constituent.payload,
            constituent.recorded_at,
            mutation_id=declaration.mutation_id,
            mutation_index=index,
        )
        return self.publish_envelope(envelope, _authority=_authority)

    # -- the operation ladder (called by the journal) -------------------------------------

    def publish_operation_artifact(
        self, path: str, model: MilestoneRunnerModel
    ) -> DurableEvidenceReference:
        payload = model_bytes(model)
        if len(payload) > MAX_LIFECYCLE_DOCUMENT_BYTES:
            raise OperationRecordInvalid(f"{path} exceeds the lifecycle document ceiling")
        return self._storage.publish_evidence(path, payload.decode("utf-8"), structural=True)

    def publish_operation_text(self, path: str, text: str) -> DurableEvidenceReference:
        return self._storage.publish_evidence(path, text, structural=False)

    def record_operation_request(
        self,
        *,
        operation_id: str,
        step: OperationStep,
        adapter: AdapterIdentity,
        request: DurableEvidenceReference,
        recorded_at: str,
    ) -> AppendedEvent | None:
        existing = self.require_state().operations.get(operation_id)
        if existing is not None:
            if (
                existing.request_sha256 != request.sha256
                or existing.step != step
                or existing.adapter != adapter
            ):
                raise OperationRecordConflict(
                    f"operation {operation_id} already carries a different request"
                )
            # Section 7.5: the retained request is relied upon, so it is confirmed, not rewritten,
            # together with the established chain it was recorded on (R07).
            self.confirm_established()
            self._storage.confirm_references((request,))
            return None
        payload = OperationRequestCreatedPayload(
            event_type="OPERATION_REQUEST_CREATED",
            operation_id=operation_id,
            step=step,
            adapter=adapter,
            request=request,
        )
        return self._append(LifecycleEventType.OPERATION_REQUEST_CREATED, payload, recorded_at)

    def record_operation_attempt_event(
        self,
        event_type: str,
        *,
        operation_id: str,
        attempt: int,
        reference: DurableEvidenceReference,
        recorded_at: str,
    ) -> AppendedEvent:
        kind = LifecycleEventType(event_type)
        payload: MilestoneRunnerModel
        if kind is LifecycleEventType.OPERATION_DISPATCH_INTENT:
            payload = OperationDispatchIntentPayload(
                event_type="OPERATION_DISPATCH_INTENT",
                operation_id=operation_id,
                attempt=attempt,
                intent=reference,
            )
        elif kind is LifecycleEventType.OPERATION_DISPATCH_RECEIVED:
            payload = OperationDispatchReceivedPayload(
                event_type="OPERATION_DISPATCH_RECEIVED",
                operation_id=operation_id,
                attempt=attempt,
                receipt=reference,
            )
        elif kind is LifecycleEventType.OPERATION_PRE_SPAWN_FAILED:
            payload = OperationPreSpawnFailedPayload(
                event_type="OPERATION_PRE_SPAWN_FAILED",
                operation_id=operation_id,
                attempt=attempt,
                verdict=reference,
            )
        else:
            raise EventConflict(f"{event_type} is not an attempt evidence event")
        return self._append(kind, payload, recorded_at)

    def record_operation_result(
        self,
        *,
        operation_id: str,
        attempt: int,
        raw_result: DurableEvidenceReference,
        outcome: ExecutionOutcome,
        transcripts: Sequence[DurableEvidenceReference],
        recorded_at: str,
    ) -> AppendedEvent:
        payload = OperationResultReceivedPayload(
            event_type="OPERATION_RESULT_RECEIVED",
            operation_id=operation_id,
            attempt=attempt,
            raw_result=raw_result,
            outcome=outcome,
            transcripts=list(transcripts),
        )
        return self._append(LifecycleEventType.OPERATION_RESULT_RECEIVED, payload, recorded_at)

    def record_operation_validation(
        self,
        *,
        operation_id: str,
        attempt: int,
        verdict: ValidationVerdict,
        reference: DurableEvidenceReference,
        recorded_at: str,
    ) -> AppendedEvent:
        payload = OperationResultValidatedPayload(
            event_type="OPERATION_RESULT_VALIDATED",
            operation_id=operation_id,
            attempt=attempt,
            verdict=verdict,
            validated=reference,
        )
        return self._append(LifecycleEventType.OPERATION_RESULT_VALIDATED, payload, recorded_at)


def _payload_references(event: LifecycleEvent) -> tuple[DurableEvidenceReference, ...]:
    """Every digest-bound reference an event asserts, including through a declaration."""
    payload = event.payload
    found: list[DurableEvidenceReference] = []
    if isinstance(payload, StageStartBoundPayload):
        found.extend((payload.authorization, payload.binding, payload.witness))
    elif isinstance(payload, PolicyPublishedPayload):
        found.append(payload.policy)
    elif isinstance(payload, RunRecordUpdatedPayload):
        found.extend(payload.evidence)
    elif isinstance(payload, OperationRequestCreatedPayload):
        found.append(payload.request)
    elif isinstance(payload, OperationDispatchIntentPayload):
        found.append(payload.intent)
    elif isinstance(payload, OperationDispatchReceivedPayload):
        found.append(payload.receipt)
    elif isinstance(payload, OperationPreSpawnFailedPayload):
        found.append(payload.verdict)
    elif isinstance(payload, OperationResultReceivedPayload):
        found.extend((payload.raw_result, *payload.transcripts))
    elif isinstance(payload, OperationResultValidatedPayload):
        found.append(payload.validated)
    elif isinstance(payload, ApplicationMutationDeclaredPayload):
        evidence = payload.declaration.evidence
        if isinstance(evidence, ResultEvidence) and evidence.verdict is not None:
            found.append(evidence.verdict)
        for constituent in payload.declaration.constituents:
            if isinstance(constituent.payload, RunRecordUpdatedPayload):
                found.extend(constituent.payload.evidence)
    return tuple(found)


def event_references(event: LifecycleEvent) -> tuple[DurableEvidenceReference, ...]:
    """Public view of :func:`_payload_references` for the storage's verified reads."""
    return _payload_references(event)


def _record_updated_payload(
    before: RunRecord, after: RunRecord, evidence: Sequence[DurableEvidenceReference]
) -> RunRecordUpdatedPayload:
    if before.workflow_state is not after.workflow_state:
        raise EventConflict("a record update never changes workflow_state")
    return RunRecordUpdatedPayload(
        event_type="RUN_RECORD_UPDATED",
        before_body_digest=body_digest(before),
        after_body_digest=body_digest(after),
        updates=record_updates(before, after),
        evidence=list(evidence),
    )


def _transition_payload(
    before: RunRecord, after: RunRecord, operation: str | None
) -> StateTransitionedPayload:
    updates = record_updates(before, after)
    carried = [member for member in updates.assigned if member is not RecordField.STOP_REASON]
    document = json.loads(updates.model_dump_json())
    document["assigned"] = [member.value for member in carried]
    document["stop_reason"] = None
    return StateTransitionedPayload(
        event_type="STATE_TRANSITIONED",
        before_body_digest=body_digest(before),
        after_body_digest=body_digest(after),
        from_state=before.workflow_state,
        to_state=after.workflow_state,
        stop_reason=after.stop_reason,
        updates=RecordUpdates.model_validate_json(json.dumps(document)),
        operation_id=operation,
    )


def _planned_payload(change: PlannedChange) -> _BodyChange:
    kind = change.event_type
    before, after = change.before, change.after
    if kind is LifecycleEventType.STATE_TRANSITIONED:
        return _transition_payload(before, after, change.operation_id)
    if kind is LifecycleEventType.RUN_RECORD_UPDATED:
        return _record_updated_payload(before, after, change.evidence)
    if kind is LifecycleEventType.RECOVERY_LEDGER_APPENDED:
        entry = change.ledger_entry
        if entry is None:
            raise EventConflict("a ledger append names its entry")
        ledger = LEDGER_BY_COMMAND[entry.command]
        return RecoveryLedgerAppendedPayload(
            event_type="RECOVERY_LEDGER_APPENDED",
            before_body_digest=body_digest(before),
            after_body_digest=body_digest(after),
            ledger=ledger,
            entry=entry,
            previous_length=len(getattr(before, ledger.value)),
            entry_digest=integrity_digest(entry.model_dump(mode="json")),
        )
    if change.operation_id is None:
        raise EventConflict("a result persistence names its operation")
    if kind is LifecycleEventType.OPERATION_RESULT_ACCEPTED:
        if change.accepted_result_sha256 is None:
            raise EventConflict("an acceptance names the accepted verdict digest")
        return OperationResultAcceptedPayload(
            event_type="OPERATION_RESULT_ACCEPTED",
            before_body_digest=body_digest(before),
            after_body_digest=body_digest(after),
            operation_id=change.operation_id,
            accepted_result_sha256=change.accepted_result_sha256,
            updates=record_updates(before, after),
        )
    if kind is LifecycleEventType.OPERATION_RESULT_REJECTED:
        if change.rejection_source is None:
            raise EventConflict("a rejection names what it rests on")
        return OperationResultRejectedPayload(
            event_type="OPERATION_RESULT_REJECTED",
            before_body_digest=body_digest(before),
            after_body_digest=body_digest(after),
            operation_id=change.operation_id,
            source=change.rejection_source,
            verdict_sha256=change.verdict_sha256,
            diagnostic=change.diagnostic,
            updates=record_updates(before, after),
        )
    raise EventConflict(f"{kind.value} is not a constituent type")


#: Test and tooling seam: every exception class this module raises for a lifecycle refusal.
LIFECYCLE_ERRORS: Final[tuple[type[LifecycleError], ...]] = (
    EventChainBroken,
    EventConflict,
    OperationRecordInvalid,
    OperationRecordConflict,
    LifecycleSchemaUnknown,
    ApplicationMutationIncomplete,
)
