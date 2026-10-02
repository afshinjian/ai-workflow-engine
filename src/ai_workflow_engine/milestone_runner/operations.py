"""Deterministic operation identity and the immutable phase-ladder evidence (AUTO-018 section 8).

Contract: `docs/workflow-automation/stage-prompts/AUTO-018.md` section 8 (operation identity, the
seven ordered facts, prospective paths versus durable evidence), section 7.1 (the run-local
operation layout) and section 11 (this module's sole permitted change: closed operation and phase
records, deterministic identities and journal coordination -- no workflow decisions and no
filesystem-write primitive).

What an operation is here
-------------------------
One effectful provider step the application asked for, addressed by the Master Plan derivation
fixed in section 8.1: SHA-256 of UTF-8 `run_id|step_kind|cycle_no|role|slot`. Only the provider
step kind exists in ST-02; a later stage extends the closed vocabulary through its own contract.
The identity is a pure function of durable facts -- the run, the role and, for implementation,
the milestone and its count of durable reopening entries -- and never of a clock, a transcript
sequence or the number of times resume was called.

Evidence is immutable and content-addressed. Every artifact below is a closed, strict model with
schema version 1 and the full run pins, serialized with the timestamp-inclusive integrity
serializer, and published exclusively by `state.py` through the single redaction boundary. The
request deliberately carries no clock reading, so a retried request under the same identity is a
byte-identical duplicate rather than a conflict; every per-attempt artifact carries its own.

:class:`OperationRecord` is a typed *view* derived by the lifecycle fold from events and verified
artifacts. It is not another mutable authoritative file, and nothing here decides what happens
next: :class:`OperationJournal` only records what the application already did or observed.
"""

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from ai_workflow_engine.milestone_runner.models import (
    MILESTONE_ID_RE,
    MilestoneRunnerModel,
    ProviderFailureClass,
    ProviderRole,
    RunRecord,
    RunStatus,
)
from ai_workflow_engine.milestone_runner.results import (
    ClosureResult,
    CorrectionResult,
    MilestoneResult,
    ReviewResult,
)
from ai_workflow_engine.successor_planning.redaction import RedactionFinding, redact_text

if TYPE_CHECKING:  # pragma: no cover - import only for annotations; events imports this module
    from ai_workflow_engine.milestone_runner.events import (
        ChainEntry,
        DurableEvidenceReference,
        EventStore,
        LifecycleEvent,
    )

#: Section 8: every operation artifact is its own closed schema, independently versioned.
OPERATION_SCHEMA_VERSION: Final = 1

#: Section 8.1: attempts retain the existing `MAX_SPAWN_RETRY_ATTEMPTS = 3` bound. Restated rather
#: than imported, because the provider layer imports the durable-state layer that imports this
#: module; a test asserts the two constants agree, so they cannot drift.
MAX_OPERATION_ATTEMPTS: Final = 3

#: Section 7.1's run-local layout, read and written by exact name only.
OPERATIONS_DIRECTORY: Final = "operations"
ATTEMPTS_DIRECTORY: Final = "attempts"
REQUEST_FILE_NAME: Final = "request.json"
DISPATCH_INTENT_FILE_NAME: Final = "dispatch-intent.json"
DISPATCH_RECEIPT_FILE_NAME: Final = "dispatch-receipt.json"
PRE_SPAWN_FAILED_FILE_NAME: Final = "pre-spawn-failed.json"
RAW_RESULT_FILE_NAME: Final = "result.raw"
VALIDATED_RESULT_FILE_NAME: Final = "result.validated.json"
APPLIED_FILE_NAME: Final = "applied.json"

#: Bounded diagnostics on a verdict: a few short lines, never a transcript.
MAX_DIAGNOSTICS: Final = 8
MAX_DIAGNOSTIC_CHARS: Final = 2_000

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_PROVIDER_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ADAPTER_TYPE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,255}")


def _sha256(value: str, field: str) -> str:
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be exactly 64 lowercase hexadecimal characters")
    return value


def _timestamp(value: str, field: str) -> str:
    if _UTC_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a UTC timestamp YYYY-MM-DDThh:mm:ssZ")
    return value


# --------------------------------------------------------------------------------------
# Section 8.1 -- identity
# --------------------------------------------------------------------------------------


class OperationStepKind(StrEnum):
    """The closed step-kind vocabulary. ST-02 records provider steps only."""

    PROVIDER = "provider"


#: Section 8.1's fixed slots for the three single-shot roles.
DISCOVERY_SLOT: Final = "discovery"
CORRECTION_SLOT: Final = "correction"
CLOSURE_SLOT: Final = "closure"
_IMPLEMENTATION_SLOT_RE = re.compile(r"(?P<milestone>[^:|]+):(?P<reopening>0|[1-9][0-9]*)")


class OperationStep(MilestoneRunnerModel):
    """The logical-step tuple an operation identity is derived from (section 8.1).

    Role wire values are the existing four; program role names are aliases, never new values.
    Each role has exactly one admissible cycle number and slot shape, so no tuple can express a
    cycle or retry entitlement the baseline flow does not already have.
    """

    step_kind: OperationStepKind
    cycle_no: int = Field(ge=0)
    role: ProviderRole
    slot: str

    @model_validator(mode="after")
    def _validate_tuple(self) -> "OperationStep":
        if "|" in self.slot:
            raise ValueError("an identity component must not contain '|'")
        if self.role is ProviderRole.IMPLEMENTATION:
            match = _IMPLEMENTATION_SLOT_RE.fullmatch(self.slot)
            if self.cycle_no != 0 or match is None:
                raise ValueError("implementation is cycle 0, slot <milestone-id>:<reopening-count>")
            if MILESTONE_ID_RE.fullmatch(match.group("milestone")) is None:
                raise ValueError("an implementation slot must name a milestone id")
        else:
            expected = {
                ProviderRole.REVIEW: (0, DISCOVERY_SLOT),
                ProviderRole.CORRECTION: (1, CORRECTION_SLOT),
                ProviderRole.CLOSURE: (1, CLOSURE_SLOT),
            }[self.role]
            if (self.cycle_no, self.slot) != expected:
                raise ValueError(
                    f"{self.role.value} is cycle {expected[0]}, slot {expected[1]!r}, "
                    f"not cycle {self.cycle_no}, slot {self.slot!r}"
                )
        return self

    @property
    def milestone_id(self) -> str | None:
        if self.role is not ProviderRole.IMPLEMENTATION:
            return None
        return self.slot.rsplit(":", 1)[0]


def reopening_count(record: RunRecord, milestone_id: str) -> int:
    """How many durable `reopen-milestone` entries name `milestone_id` (section 8.1)."""
    return sum(1 for entry in record.reopenings if entry.milestone_id == milestone_id)


def provider_step(record: RunRecord, role: ProviderRole, milestone_id: str | None) -> OperationStep:
    """The step tuple for the existing provider invocation of `role` on `record`."""
    if role is ProviderRole.IMPLEMENTATION:
        if milestone_id is None:
            raise ValueError("an implementation step names its milestone")
        slot = f"{milestone_id}:{reopening_count(record, milestone_id)}"
        return OperationStep(step_kind=OperationStepKind.PROVIDER, cycle_no=0, role=role, slot=slot)
    cycle, slot = {
        ProviderRole.REVIEW: (0, DISCOVERY_SLOT),
        ProviderRole.CORRECTION: (1, CORRECTION_SLOT),
        ProviderRole.CLOSURE: (1, CLOSURE_SLOT),
    }[role]
    return OperationStep(step_kind=OperationStepKind.PROVIDER, cycle_no=cycle, role=role, slot=slot)


def operation_id(run_id: str, step: OperationStep) -> str:
    """SHA-256 of UTF-8 `run_id|step_kind|cycle_no|role|slot` (Master Plan section 2.4)."""
    if _RUN_ID_RE.fullmatch(run_id) is None or "|" in run_id:
        raise ValueError(f"{run_id!r} is not a run id an operation identity can be derived from")
    material = "|".join(
        (run_id, step.step_kind.value, str(step.cycle_no), step.role.value, step.slot)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def attempt_directory_name(attempt: int) -> str:
    """`0001`..`0003`. The name grants no retry permission; the bound does."""
    if not 1 <= attempt <= MAX_OPERATION_ATTEMPTS:
        raise ValueError(f"attempt {attempt} is outside 1..{MAX_OPERATION_ATTEMPTS}")
    return f"{attempt:04d}"


def operation_artifact_path(identifier: str, name: str, *, attempt: int | None = None) -> str:
    """The run-relative path of one operation artifact, derived from a validated identity."""
    _sha256(identifier, "operation_id")
    if attempt is None:
        if name not in {REQUEST_FILE_NAME, APPLIED_FILE_NAME}:
            raise ValueError(f"{name!r} is not an operation-level artifact")
        return f"{OPERATIONS_DIRECTORY}/{identifier}/{name}"
    if name not in {
        DISPATCH_INTENT_FILE_NAME,
        DISPATCH_RECEIPT_FILE_NAME,
        PRE_SPAWN_FAILED_FILE_NAME,
        RAW_RESULT_FILE_NAME,
        VALIDATED_RESULT_FILE_NAME,
    }:
        raise ValueError(f"{name!r} is not an attempt artifact")
    return (
        f"{OPERATIONS_DIRECTORY}/{identifier}/{ATTEMPTS_DIRECTORY}/"
        f"{attempt_directory_name(attempt)}/{name}"
    )


OPERATION_ARTIFACT_PATH_RE: Final = re.compile(
    rf"{OPERATIONS_DIRECTORY}/(?P<operation>[0-9a-f]{{64}})/"
    rf"(?:(?P<top>{re.escape(REQUEST_FILE_NAME)}|{re.escape(APPLIED_FILE_NAME)})"
    rf"|{ATTEMPTS_DIRECTORY}/(?P<attempt>000[1-3])/(?P<name>"
    + "|".join(
        re.escape(name)
        for name in (
            DISPATCH_INTENT_FILE_NAME,
            DISPATCH_RECEIPT_FILE_NAME,
            PRE_SPAWN_FAILED_FILE_NAME,
            RAW_RESULT_FILE_NAME,
            VALIDATED_RESULT_FILE_NAME,
        )
    )
    + r"))"
)


# --------------------------------------------------------------------------------------
# Section 8 -- the closed artifacts
# --------------------------------------------------------------------------------------


class OperationPins(MilestoneRunnerModel):
    """The full run pins every operation artifact carries (INV-018-06)."""

    repository_identity: str
    stage_id: str
    run_id: str
    contract_sha256: str
    policy_digest: str
    stage_start_id: str

    @field_validator("contract_sha256", "policy_digest", "stage_start_id")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "pin")

    @field_validator("run_id")
    @classmethod
    def _validate_run_id(cls, value: str) -> str:
        if _RUN_ID_RE.fullmatch(value) is None:
            raise ValueError("run_id has an invalid grammar")
        return value


class AdapterIdentity(MilestoneRunnerModel):
    """The actual baseline adapter serving the role. Frozen `roles` selections stay audit-only."""

    provider: str
    adapter_type: str

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        if _PROVIDER_NAME_RE.fullmatch(value) is None:
            raise ValueError("provider must be a lowercase adapter name")
        return value

    @field_validator("adapter_type")
    @classmethod
    def _validate_adapter_type(cls, value: str) -> str:
        if _ADAPTER_TYPE_RE.fullmatch(value) is None:
            raise ValueError("adapter_type must be a dotted Python type name")
        return value


class OperationRequest(MilestoneRunnerModel):
    """`request.json`: what AWE requested before any dispatch (section 8.2 `REQUEST_CREATED`).

    The existing prompt is carried inline -- already through the redaction boundary -- beside the
    execution constraints the application owns. There is deliberately no timestamp, so a request
    re-derived for the same identity is byte-identical or it is a conflict.
    """

    schema_version: int
    pins: OperationPins
    operation_id: str
    step: OperationStep
    role: ProviderRole
    milestone_id: str | None = None
    adapter: AdapterIdentity
    invoking_state: RunStatus
    repository_root: str
    allowed_environment_variables: list[str]
    prompt: str
    prompt_sha256: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        return _operation_version(value)

    @field_validator("operation_id", "prompt_sha256")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @model_validator(mode="after")
    def _validate_binding(self) -> "OperationRequest":
        if operation_id(self.pins.run_id, self.step) != self.operation_id:
            raise ValueError("operation_id is not the identity derived from the step tuple")
        if self.role is not self.step.role or self.milestone_id != self.step.milestone_id:
            raise ValueError("role and milestone must be the step's own")
        if hashlib.sha256(self.prompt.encode("utf-8")).hexdigest() != self.prompt_sha256:
            raise ValueError("prompt_sha256 does not digest the carried prompt")
        return self


class DispatchIntent(MilestoneRunnerModel):
    """`dispatch-intent.json`: durable before process creation (section 8.2 `DISPATCH_INTENT`).

    Binds the attempt to the request, to the exact adapter-built request vector and its bounds, to
    the actual adapter and to the pre-invocation repository fingerprint. Intent is never receipt.
    """

    schema_version: int
    pins: OperationPins
    operation_id: str
    attempt: int
    request_sha256: str
    provider_request_sha256: str
    argv_sha256: str
    timeout_seconds: int = Field(ge=1)
    transcript_label: str
    transcript_sequence: int = Field(ge=1)
    adapter: AdapterIdentity
    fingerprint_sha256: str
    recorded_at: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        return _operation_version(value)

    @field_validator("attempt")
    @classmethod
    def _validate_attempt(cls, value: int) -> int:
        attempt_directory_name(value)
        return value

    @field_validator(
        "operation_id",
        "request_sha256",
        "provider_request_sha256",
        "argv_sha256",
        "fingerprint_sha256",
    )
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @field_validator("recorded_at")
    @classmethod
    def _validate_recorded_at(cls, value: str) -> str:
        return _timestamp(value, "recorded_at")


class ReceiptKind(StrEnum):
    """What observed process creation. Intention, completion and validation are not receipts."""

    #: A local child process the invoker observed immediately after `Popen` returned.
    LOCAL_PROCESS = "LOCAL_PROCESS"
    #: An explicitly typed acknowledgment by a scripted test fake that creates no OS process. It
    #: carries no process id: a fake never invents one.
    SCRIPTED_FAKE_ACKNOWLEDGMENT = "SCRIPTED_FAKE_ACKNOWLEDGMENT"


class DispatchReceipt(MilestoneRunnerModel):
    """`dispatch-receipt.json`: observed process creation (section 8.2 `DISPATCH_RECEIPT`)."""

    schema_version: int
    pins: OperationPins
    operation_id: str
    attempt: int
    intent_sha256: str
    kind: ReceiptKind
    process_id: int | None = None
    observed_started_at: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        return _operation_version(value)

    @field_validator("attempt")
    @classmethod
    def _validate_attempt(cls, value: int) -> int:
        attempt_directory_name(value)
        return value

    @field_validator("operation_id", "intent_sha256")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @field_validator("observed_started_at")
    @classmethod
    def _validate_started(cls, value: str) -> str:
        return _timestamp(value, "observed_started_at")

    @model_validator(mode="after")
    def _validate_kind(self) -> "DispatchReceipt":
        if self.kind is ReceiptKind.LOCAL_PROCESS:
            if self.process_id is None or self.process_id < 1:
                raise ValueError("a local process receipt records the observed process id")
        elif self.process_id is not None:
            raise ValueError("a scripted-fake acknowledgment never carries an invented process id")
        return self


class PreSpawnFailure(MilestoneRunnerModel):
    """`pre-spawn-failed.json`: the OS positively refused process creation (section 8.2).

    A terminal attempt outcome distinct from every other failure: timeout, cancellation, non-zero
    exit, receipt-publication failure and an unknown outcome are never this.
    """

    schema_version: int
    pins: OperationPins
    operation_id: str
    attempt: int
    intent_sha256: str
    verdict: Literal["NO_PROCESS_CREATED"]
    detail: str
    recorded_at: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        return _operation_version(value)

    @field_validator("attempt")
    @classmethod
    def _validate_attempt(cls, value: int) -> int:
        attempt_directory_name(value)
        return value

    @field_validator("operation_id", "intent_sha256")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @field_validator("detail")
    @classmethod
    def _validate_detail(cls, value: str) -> str:
        return _diagnostic(value)

    @field_validator("recorded_at")
    @classmethod
    def _validate_recorded_at(cls, value: str) -> str:
        return _timestamp(value, "recorded_at")


class ExecutionOutcome(MilestoneRunnerModel):
    """Execution metadata of a received result. Never an acceptance claim."""

    exit_code: int | None = None
    timed_out: bool
    failure_class: ProviderFailureClass | None = None
    duration_ms: int = Field(ge=0)
    stdout_truncated: bool
    stderr_truncated: bool


class ValidationVerdict(StrEnum):
    """Section 8.2's three terminal validation verdicts."""

    VALID = "VALID"
    INVALID = "INVALID"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class ValidatedResult(MilestoneRunnerModel):
    """`result.validated.json`: the typed result and its verdict (section 8.2).

    Exactly one typed result field is set, for the step's own role, when the verdict is `VALID`;
    an invalid or failed result carries none, only bounded diagnostics. Nothing here can present
    an invalid result as a successful one.
    """

    schema_version: int
    pins: OperationPins
    operation_id: str
    attempt: int
    role: ProviderRole
    raw_result_sha256: str
    verdict: ValidationVerdict
    milestone_result: MilestoneResult | None = None
    review_result: ReviewResult | None = None
    correction_result: CorrectionResult | None = None
    closure_result: ClosureResult | None = None
    diagnostics: list[str] = Field(default_factory=list, max_length=MAX_DIAGNOSTICS)
    recorded_at: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        return _operation_version(value)

    @field_validator("attempt")
    @classmethod
    def _validate_attempt(cls, value: int) -> int:
        attempt_directory_name(value)
        return value

    @field_validator("operation_id", "raw_result_sha256")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")

    @field_validator("diagnostics")
    @classmethod
    def _validate_diagnostics(cls, value: list[str]) -> list[str]:
        return [_diagnostic(item) for item in value]

    @field_validator("recorded_at")
    @classmethod
    def _validate_recorded_at(cls, value: str) -> str:
        return _timestamp(value, "recorded_at")

    @model_validator(mode="after")
    def _validate_result(self) -> "ValidatedResult":
        present = {
            ProviderRole.IMPLEMENTATION: self.milestone_result,
            ProviderRole.REVIEW: self.review_result,
            ProviderRole.CORRECTION: self.correction_result,
            ProviderRole.CLOSURE: self.closure_result,
        }
        others = [value for role, value in present.items() if role is not self.role]
        if any(value is not None for value in others):
            raise ValueError("a validated result carries only its own role's typed result")
        own = present[self.role]
        if self.verdict is ValidationVerdict.VALID and own is None:
            raise ValueError("a VALID verdict carries its typed result")
        if self.verdict is not ValidationVerdict.VALID and own is not None:
            raise ValueError("an invalid or failed result never carries a typed result")
        return self


class AppliedReceipt(MilestoneRunnerModel):
    """`applied.json`: written only after the causative transition is durable (section 8.2).

    A receipt of an already-committed event, rebuildable byte-identically from that event, and
    never authority to apply the transition again.
    """

    schema_version: int
    pins: OperationPins
    operation_id: str
    event_id: str
    state_version: int = Field(ge=1)
    event_sha256: str

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        return _operation_version(value)

    @field_validator("operation_id", "event_id", "event_sha256")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _sha256(value, "digest")


def _operation_version(value: int) -> int:
    if value != OPERATION_SCHEMA_VERSION:
        raise ValueError(f"operation schema_version {value} is unknown")
    return value


def _diagnostic(value: str) -> str:
    if not value or len(value) > MAX_DIAGNOSTIC_CHARS:
        raise ValueError(f"a diagnostic is 1..{MAX_DIAGNOSTIC_CHARS} characters")
    return value


#: The free-text fields of the four typed results (section 7.3, R09). Everything else in a typed
#: result -- milestone and finding ids, statuses, severities, verdicts, changed paths -- is
#: identity-bearing structure and is never rewritten here; a secret-shaped value there is still
#: refused by the mandatory final structural redaction pass rather than silently changed.
TYPED_RESULT_FREE_TEXT_FIELDS: Final = frozenset(
    {"title", "summary", "reason", "resolution", "blockers", "command"}
)


def redact_typed_result(result: Any) -> tuple[Any, list[RedactionFinding]]:
    """Redact a typed result's free text before validation and content addressing (R09).

    Returns the result, revalidated by its own closed model with its structure preserved, and the
    redaction findings that fired, so they stay counted and visible. A result with nothing to
    redact is returned unchanged. Redaction that would make the typed result invalid fails closed.
    """
    findings: list[RedactionFinding] = []

    def visit(value: Any, free: bool) -> Any:
        if isinstance(value, str):
            if not free:
                return value
            text, fired = redact_text(value)
            findings.extend(fired)
            return text
        if isinstance(value, list):
            return [visit(item, free) for item in value]
        if isinstance(value, dict):
            return {
                key: visit(item, key in TYPED_RESULT_FREE_TEXT_FIELDS)
                for key, item in value.items()
            }
        return value

    document = visit(result.model_dump(mode="json"), False)
    if not findings:
        return result, []
    try:
        return type(result).model_validate_json(json.dumps(document)), findings
    except ValidationError as exc:
        from ai_workflow_engine.milestone_runner.events import OperationRecordInvalid

        raise OperationRecordInvalid(
            f"redacting the typed result's free text would make it invalid, so it is refused: {exc}"
        ) from None


def bounded_diagnostics(lines: Sequence[str]) -> list[str]:
    """Trim free-text diagnostics to the verdict's bounds without inventing any."""
    kept = [line[:MAX_DIAGNOSTIC_CHARS] for line in lines if line]
    return kept[:MAX_DIAGNOSTICS]


#: The closed artifact model for each operation file name.
ARTIFACT_MODELS: Final[dict[str, type[MilestoneRunnerModel]]] = {
    REQUEST_FILE_NAME: OperationRequest,
    DISPATCH_INTENT_FILE_NAME: DispatchIntent,
    DISPATCH_RECEIPT_FILE_NAME: DispatchReceipt,
    PRE_SPAWN_FAILED_FILE_NAME: PreSpawnFailure,
    VALIDATED_RESULT_FILE_NAME: ValidatedResult,
    APPLIED_FILE_NAME: AppliedReceipt,
}


# --------------------------------------------------------------------------------------
# Section 8.2 -- the derived view
# --------------------------------------------------------------------------------------


class OperationPhase(StrEnum):
    """The seven ordered facts, as the highest one an operation has durable evidence for."""

    REQUEST_CREATED = "REQUEST_CREATED"
    DISPATCH_INTENT = "DISPATCH_INTENT"
    DISPATCH_RECEIPT = "DISPATCH_RECEIPT"
    RESULT_RECEIVED = "RESULT_RECEIVED"
    RESULT_VALIDATED = "RESULT_VALIDATED"
    RESULT_PERSISTED = "RESULT_PERSISTED"
    TRANSITION_APPLIED = "TRANSITION_APPLIED"


class AttemptRecord(MilestoneRunnerModel):
    """One attempt's evidence digests, in order. At most one of receipt and pre-spawn failure."""

    attempt: int
    intent_sha256: str
    receipt_sha256: str | None = None
    pre_spawn_failure_sha256: str | None = None
    raw_result_sha256: str | None = None
    validated_sha256: str | None = None
    verdict: ValidationVerdict | None = None


class PersistenceKind(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class OperationRecord(MilestoneRunnerModel):
    """The typed operation view the fold derives (section 8.1). Never written to disk."""

    operation_id: str
    step: OperationStep
    request_sha256: str
    adapter: AdapterIdentity
    role: ProviderRole
    milestone_id: str | None = None
    attempts: list[AttemptRecord] = Field(default_factory=list)
    fingerprint_sha256: str | None = None
    persisted: PersistenceKind | None = None
    persisted_verdict_sha256: str | None = None
    transition_event_id: str | None = None
    transition_state_version: int | None = None
    highest_phase: OperationPhase = OperationPhase.REQUEST_CREATED


# --------------------------------------------------------------------------------------
# Journal coordination
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OperationHandle:
    """What the application holds for one operation while it drives it."""

    operation_id: str
    step: OperationStep
    request_sha256: str
    adapter: AdapterIdentity


class OperationJournal:
    """Records the phase ladder the application drives; decides nothing (section 11).

    Each method publishes one immutable artifact through the storage the event store is bound to
    -- exclusively, under the held and verified lock, through the redaction boundary -- and then
    appends the one evidence event naming it. The order is section 7.2's: the digest-bound
    evidence is durable before the event that asserts it. Nothing here selects a next step, and
    none of these events touches the run record.
    """

    def __init__(self, events: "EventStore") -> None:
        self._events = events

    @property
    def events(self) -> "EventStore":
        return self._events

    def pins(self) -> OperationPins:
        return OperationPins.model_validate(self._events.pins.model_dump())

    def create_request(
        self,
        *,
        step: OperationStep,
        adapter: AdapterIdentity,
        invoking_state: RunStatus,
        repository_root: str,
        allowed_environment_variables: Sequence[str],
        prompt: str,
        recorded_at: str,
    ) -> OperationHandle:
        """`REQUEST_CREATED`: publish `request.json` and its event, or recognize the duplicate."""
        pins = self.pins()
        identifier = operation_id(pins.run_id, step)
        stored_prompt = self._events.redacted_text(prompt)
        request = OperationRequest(
            schema_version=OPERATION_SCHEMA_VERSION,
            pins=pins,
            operation_id=identifier,
            step=step,
            role=step.role,
            milestone_id=step.milestone_id,
            adapter=adapter,
            invoking_state=invoking_state,
            repository_root=repository_root,
            allowed_environment_variables=list(allowed_environment_variables),
            prompt=stored_prompt,
            prompt_sha256=hashlib.sha256(stored_prompt.encode("utf-8")).hexdigest(),
        )
        reference = self._events.publish_operation_artifact(
            operation_artifact_path(identifier, REQUEST_FILE_NAME), request
        )
        self._events.record_operation_request(
            operation_id=identifier,
            step=step,
            adapter=adapter,
            request=reference,
            recorded_at=recorded_at,
        )
        return OperationHandle(
            operation_id=identifier, step=step, request_sha256=reference.sha256, adapter=adapter
        )

    def next_attempt(self, handle: OperationHandle) -> int:
        view = self._events.operation(handle.operation_id)
        return len(view.attempts) + 1

    def record_intent(
        self,
        handle: OperationHandle,
        *,
        attempt: int,
        provider_request_sha256: str,
        argv_sha256: str,
        timeout_seconds: int,
        transcript_label: str,
        transcript_sequence: int,
        fingerprint_sha256: str,
        recorded_at: str,
    ) -> "DurableEvidenceReference":
        intent = DispatchIntent(
            schema_version=OPERATION_SCHEMA_VERSION,
            pins=self.pins(),
            operation_id=handle.operation_id,
            attempt=attempt,
            request_sha256=handle.request_sha256,
            provider_request_sha256=provider_request_sha256,
            argv_sha256=argv_sha256,
            timeout_seconds=timeout_seconds,
            transcript_label=transcript_label,
            transcript_sequence=transcript_sequence,
            adapter=handle.adapter,
            fingerprint_sha256=fingerprint_sha256,
            recorded_at=recorded_at,
        )
        reference = self._events.publish_operation_artifact(
            operation_artifact_path(
                handle.operation_id, DISPATCH_INTENT_FILE_NAME, attempt=attempt
            ),
            intent,
        )
        self._events.record_operation_attempt_event(
            "OPERATION_DISPATCH_INTENT",
            operation_id=handle.operation_id,
            attempt=attempt,
            reference=reference,
            recorded_at=recorded_at,
        )
        return reference

    def record_receipt(
        self,
        handle: OperationHandle,
        *,
        attempt: int,
        intent_sha256: str,
        kind: ReceiptKind,
        process_id: int | None,
        observed_started_at: str,
    ) -> None:
        receipt = DispatchReceipt(
            schema_version=OPERATION_SCHEMA_VERSION,
            pins=self.pins(),
            operation_id=handle.operation_id,
            attempt=attempt,
            intent_sha256=intent_sha256,
            kind=kind,
            process_id=process_id,
            observed_started_at=observed_started_at,
        )
        reference = self._events.publish_operation_artifact(
            operation_artifact_path(
                handle.operation_id, DISPATCH_RECEIPT_FILE_NAME, attempt=attempt
            ),
            receipt,
        )
        self._events.record_operation_attempt_event(
            "OPERATION_DISPATCH_RECEIVED",
            operation_id=handle.operation_id,
            attempt=attempt,
            reference=reference,
            recorded_at=observed_started_at,
        )

    def record_pre_spawn_failure(
        self,
        handle: OperationHandle,
        *,
        attempt: int,
        intent_sha256: str,
        detail: str,
        recorded_at: str,
    ) -> "DurableEvidenceReference":
        failure = PreSpawnFailure(
            schema_version=OPERATION_SCHEMA_VERSION,
            pins=self.pins(),
            operation_id=handle.operation_id,
            attempt=attempt,
            intent_sha256=intent_sha256,
            verdict="NO_PROCESS_CREATED",
            detail=bounded_diagnostics([self._events.redacted_text(detail)])[0],
            recorded_at=recorded_at,
        )
        reference = self._events.publish_operation_artifact(
            operation_artifact_path(
                handle.operation_id, PRE_SPAWN_FAILED_FILE_NAME, attempt=attempt
            ),
            failure,
        )
        self._events.record_operation_attempt_event(
            "OPERATION_PRE_SPAWN_FAILED",
            operation_id=handle.operation_id,
            attempt=attempt,
            reference=reference,
            recorded_at=recorded_at,
        )
        return reference

    def record_result(
        self,
        handle: OperationHandle,
        *,
        attempt: int,
        raw_text: str,
        outcome: ExecutionOutcome,
        transcripts: Sequence["DurableEvidenceReference"],
        recorded_at: str,
    ) -> "DurableEvidenceReference":
        reference = self._events.publish_operation_text(
            operation_artifact_path(handle.operation_id, RAW_RESULT_FILE_NAME, attempt=attempt),
            raw_text,
        )
        self._events.record_operation_result(
            operation_id=handle.operation_id,
            attempt=attempt,
            raw_result=reference,
            outcome=outcome,
            transcripts=transcripts,
            recorded_at=recorded_at,
        )
        return reference

    def record_validation(
        self,
        handle: OperationHandle,
        *,
        attempt: int,
        raw_result_sha256: str,
        verdict: ValidationVerdict,
        result: Any,
        diagnostics: Sequence[str],
        recorded_at: str,
        on_redaction: Callable[[str, list[RedactionFinding]], None] | None = None,
    ) -> "DurableEvidenceReference":
        """`RESULT_VALIDATED`: the typed verdict, with free text redacted before its digest.

        Section 7.3 / R09: a valid result's free-text fields are redacted *before* the closed
        model is built and content-addressed, so an otherwise-valid result carrying secret-shaped
        prose is accepted with that prose neutralized, never refused by the final structural
        pass. `on_redaction` receives the artifact path and the findings that fired, so they stay
        counted and visible on the run record.
        """
        role = handle.step.role
        typed: dict[str, Any] = {}
        path = operation_artifact_path(
            handle.operation_id, VALIDATED_RESULT_FILE_NAME, attempt=attempt
        )
        fired: list[RedactionFinding] = []
        clean_diagnostics: list[str] = []
        for line in diagnostics:
            text, found = redact_text(line)
            clean_diagnostics.append(text)
            fired.extend(found)
        if verdict is ValidationVerdict.VALID:
            result, found = redact_typed_result(result)
            fired.extend(found)
            typed[
                {
                    ProviderRole.IMPLEMENTATION: "milestone_result",
                    ProviderRole.REVIEW: "review_result",
                    ProviderRole.CORRECTION: "correction_result",
                    ProviderRole.CLOSURE: "closure_result",
                }[role]
            ] = result
        validated = ValidatedResult(
            schema_version=OPERATION_SCHEMA_VERSION,
            pins=self.pins(),
            operation_id=handle.operation_id,
            attempt=attempt,
            role=role,
            raw_result_sha256=raw_result_sha256,
            verdict=verdict,
            diagnostics=bounded_diagnostics(clean_diagnostics),
            recorded_at=recorded_at,
            **typed,
        )
        reference = self._events.publish_operation_artifact(path, validated)
        if fired and on_redaction is not None:
            on_redaction(path, fired)
        self._events.record_operation_validation(
            operation_id=handle.operation_id,
            attempt=attempt,
            verdict=verdict,
            reference=reference,
            recorded_at=recorded_at,
        )
        return reference

    def write_applied(
        self, identifier: str, event: "LifecycleEvent | ChainEntry", event_sha256: str
    ) -> None:
        """`applied.json`, only after the causative transition is durable (section 8.2)."""
        receipt = applied_receipt(self.pins(), identifier, event, event_sha256)
        self._events.publish_operation_artifact(
            operation_artifact_path(identifier, APPLIED_FILE_NAME), receipt
        )


def applied_receipt(
    pins: OperationPins,
    identifier: str,
    event: "LifecycleEvent | ChainEntry",
    event_sha256: str,
) -> AppliedReceipt:
    """The deterministic receipt for a verified causative transition event.

    Only the event's identity and version are read, so the bounded :class:`ChainEntry` a
    streaming load retains (R12) serves as well as the full event.
    """
    return AppliedReceipt(
        schema_version=OPERATION_SCHEMA_VERSION,
        pins=pins,
        operation_id=identifier,
        event_id=event.event_id,
        state_version=event.state_version,
        event_sha256=event_sha256,
    )
