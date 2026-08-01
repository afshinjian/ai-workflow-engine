"""The configurable approval subsystem (AUTO-012).

One service, one job: decide whether a named gate in a named workflow has a valid, still-binding
human (or policy-derived) approval, and persist every step of that decision durably::

    WorkflowService
        -> ApprovalService
            -> policy resolution
            -> request persistence  (approvals.jsonl, via the existing StateStore discipline)
            -> manual decisions
            -> timeout decisions
            -> checksum binding
            -> invalidation

**What this module is not.** It implements no workflow mode — no Preparation, no Reviewer, no
Implementer. It executes no provider, runs no agent, touches no Git or GitHub, opens no network
connection, and starts no thread, timer, or scheduler. Nothing here decides *when* a gate should
be approved or what an approval means for a workflow; it decides only whether one exists, is still
bound to the state it was granted against, and has not already been spent. Consuming that answer
belongs to the Orchestrator and to stages after this one.

**Why events rather than a mutable record.** An approval is persisted as an append-only sequence of
`ApprovalEvent`s and the current `ApprovalRequest` is *derived by replay*, never stored as a
snapshot that is later edited. That is the same discipline `StateStore` already applies to workflow
transitions, and it is what makes "no decision is ever overwritten" a property of the file format
rather than a promise: there is no code path that rewrites a line, because the only write is an
append.

**Timeouts without a timer.** A deadline is an absolute, timezone-aware UTC instant written into
the request event. Nothing sleeps, no thread waits, and no scheduler state lives in this process:
the deadline is evaluated lazily, whenever someone reads or acts on the approval, by comparing it
against the clock. A deadline therefore survives a process restart, a machine restart, and a
migration to a different host, because it is a fact on disk rather than a pending callback in
memory. A future daemon may evaluate the same fact eagerly; that changes nothing here.

**`AUTO_APPROVE` is opt-in at the point of use.** A timeout that silently approves is the one
policy value that can convert an absent human into a granted permission, so it may only be selected
by the gate itself or by an explicit per-run override. A broad built-in or project-wide default
naming it is a configuration error and is refused, not inherited (`_require_explicit_auto_approve`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator.state_store import StateStore
from agentos_workflow.results import AgentRunResult
from agentos_workflow.skills import utc_now

__all__ = [
    "APPROVALS_FILENAME",
    "CHECKSUM_ALGORITHM_PREFIX",
    "ApprovalChannel",
    "ApprovalChecksums",
    "ApprovalDecision",
    "ApprovalError",
    "ApprovalEvent",
    "ApprovalEventKind",
    "ApprovalNotFoundError",
    "ApprovalPolicy",
    "ApprovalPolicyError",
    "ApprovalPolicyOverlay",
    "ApprovalRequest",
    "ApprovalService",
    "ApprovalStateError",
    "ApprovalStatus",
    "ChecksumKind",
    "DecisionOrigin",
    "PolicyLayer",
    "TimeoutAction",
    "checksum_of_agent_result",
    "checksum_of_mapping",
    "checksum_of_text",
    "resolve_approval_policy",
]

#: The per-workflow approval history, alongside `transitions.jsonl` under the state directory.
APPROVALS_FILENAME = "approvals.jsonl"

#: Every checksum this module produces is labelled with the algorithm that produced it, matching
#: `skills.contract.CONTRACT_HASH_ALGORITHM_PREFIX`. A bare hex string is indistinguishable from a
#: hex string produced by a different algorithm, and a bound value whose algorithm is implicit
#: cannot be migrated later without ambiguity.
CHECKSUM_ALGORITHM_PREFIX = "sha256:"


class _ApprovalModel(BaseModel):
    """`extra="forbid"`, `frozen=True` — the convention every record model in this package uses."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# -------------------------------------------------------------------------------------------
# Errors
# -------------------------------------------------------------------------------------------


class ApprovalError(Exception):
    """Base class for every approval-subsystem error."""


class ApprovalPolicyError(ApprovalError):
    """A policy is internally inconsistent, or selects a value it is not permitted to select."""


class ApprovalNotFoundError(ApprovalError):
    """No approval with the given identifier exists for the given workflow."""


class ApprovalStateError(ApprovalError):
    """An operation was attempted against an approval whose current status forbids it."""


# -------------------------------------------------------------------------------------------
# Vocabulary
# -------------------------------------------------------------------------------------------


class PolicyLayer(StrEnum):
    """Where a resolved policy value came from, in increasing precedence.

    Carried into the snapshot rather than discarded after resolution, because one value's
    provenance is security-relevant: `AUTO_APPROVE` is legitimate from `GATE` or `RUN` and is a
    configuration error from `BUILT_IN` or `PROJECT`.
    """

    BUILT_IN = "built_in"
    PROJECT = "project"
    GATE = "gate"
    RUN = "run"


#: Precedence order, lowest first. The single source of truth for both resolution and the
#: explicit-opt-in check, so the two cannot disagree about which layers are "broad".
_LAYER_ORDER: tuple[PolicyLayer, ...] = (
    PolicyLayer.BUILT_IN,
    PolicyLayer.PROJECT,
    PolicyLayer.GATE,
    PolicyLayer.RUN,
)

#: The only layers that may select `AUTO_APPROVE`: the gate itself, or an explicit per-run
#: override. Everything below is an inherited default and is deliberately not enough.
_EXPLICIT_OPT_IN_LAYERS: frozenset[PolicyLayer] = frozenset({PolicyLayer.GATE, PolicyLayer.RUN})


class ApprovalChannel(StrEnum):
    """Where an approval may be requested and a decision may arrive from.

    `TELEGRAM` is a policy value only in this stage. No transport, bot, handler, or network call
    exists anywhere in this engine, and naming a channel here implements none of them — it lets a
    policy be written and validated today so the stage that builds a transport has a contract to
    satisfy rather than one to invent.
    """

    CLI = "cli"
    TELEGRAM = "telegram"


class TimeoutAction(StrEnum):
    """What happens when a deadline passes with the approval still pending."""

    AUTO_APPROVE = "auto_approve"
    PAUSE = "pause"
    FAIL = "fail"
    CANCEL = "cancel"
    ESCALATE = "escalate"


class ApprovalDecision(StrEnum):
    """A decision about the work, distinct from *how* the decision was reached."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class DecisionOrigin(StrEnum):
    """Whether a human decided, or a policy did. Never inferred from anything else."""

    MANUAL = "manual"
    AUTO = "auto"


class ApprovalStatus(StrEnum):
    """An approval's current position, derived by replay and never stored as a snapshot.

    `HUMAN_INTERVENTION_REQUIRED` is deliberately **not terminal**: a `PAUSE` timeout means nobody
    answered in time, not that the answer is no, so a later manual decision is still accepted and
    moves the approval on. `INVALIDATED` and `CONSUMED` are terminal, for opposite reasons — the
    first because the state it was granted against no longer exists, the second because it has
    already been spent and an approval that can be spent twice is not a gate.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"
    ESCALATED = "escalated"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INVALIDATED = "invalidated"
    CONSUMED = "consumed"


#: Statuses from which no further progress is possible. `HUMAN_INTERVENTION_REQUIRED` and
#: `ESCALATED` are absent on purpose: both are still awaiting an answer.
_TERMINAL_STATUSES: frozenset[ApprovalStatus] = frozenset(
    {
        ApprovalStatus.REJECTED,
        ApprovalStatus.CHANGES_REQUESTED,
        ApprovalStatus.FAILED,
        ApprovalStatus.CANCELLED,
        ApprovalStatus.INVALIDATED,
        ApprovalStatus.CONSUMED,
    }
)

#: Statuses whose deadline may still fire. A decided approval's deadline is irrelevant.
_TIMEOUT_ELIGIBLE_STATUSES: frozenset[ApprovalStatus] = frozenset(
    {ApprovalStatus.PENDING, ApprovalStatus.ESCALATED}
)

#: How a decision maps onto a status. One mapping, so no branch can invent a different answer.
_STATUS_FOR_DECISION: Mapping[ApprovalDecision, ApprovalStatus] = {
    ApprovalDecision.APPROVE: ApprovalStatus.APPROVED,
    ApprovalDecision.REJECT: ApprovalStatus.REJECTED,
    ApprovalDecision.REQUEST_CHANGES: ApprovalStatus.CHANGES_REQUESTED,
}


class ChecksumKind(StrEnum):
    """Which of the four bindings a comparison found changed."""

    REPO_STATE = "repo_state"
    DIFF = "diff"
    AGENT_RESULT = "agent_result"
    GATE_RESULT = "gate_result"


class ApprovalEventKind(StrEnum):
    """The append-only vocabulary of `approvals.jsonl`."""

    REQUESTED = "requested"
    DECIDED = "decided"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"
    EXTENDED = "extended"
    INVALIDATED = "invalidated"
    CONSUMED = "consumed"


# -------------------------------------------------------------------------------------------
# Checksums
# -------------------------------------------------------------------------------------------


def _digest(payload: bytes) -> str:
    return f"{CHECKSUM_ALGORITHM_PREFIX}{hashlib.sha256(payload).hexdigest()}"


def checksum_of_text(text: str) -> str:
    """Hash arbitrary text (a diff, a `git status` rendering, a HEAD SHA) as UTF-8 bytes.

    Raw bytes, never normalized: a change that alters only line endings or trailing whitespace is
    still a change to the state that was approved, exactly as `calculate_contract_hash` argues for
    the contract binding.
    """
    return _digest(text.encode("utf-8"))


def checksum_of_mapping(payload: Mapping[str, Any]) -> str:
    """Hash a structured payload through one canonical serialization.

    Sorted keys and tight separators, so two callers that build the same mapping in different
    orders produce the same digest and a digest means "this content" rather than "this content,
    written this way".
    """
    return _digest(
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )


def checksum_of_agent_result(result: AgentRunResult) -> str:
    """Hash the canonical AUTO-011 result through *its own* deterministic serialization.

    Deliberately not a second serialization of the same object: `AgentRunResult` already defines
    what its canonical bytes are, and a checksum computed over anything else would drift from the
    contract it is supposed to bind.
    """
    return _digest(result.to_canonical_json().encode("utf-8"))


class ApprovalChecksums(_ApprovalModel):
    """The four bindings an approval is granted against.

    An approval is permission to act on *a specific state of the world*. These four values are that
    state, reduced to digests: what the repository looked like, what the change was, what the agent
    reported, and what the deterministic gates concluded. Storing digests rather than the material
    is both a size and a secrets decision — a digest of a diff that contained a credential leaks
    nothing, while the diff itself would be stored forever in an append-only file.
    """

    repo_state: str
    diff: str
    agent_result: str
    gate_result: str

    @field_validator("repo_state", "diff", "agent_result", "gate_result")
    @classmethod
    def _validate_shape(cls, value: str) -> str:
        if not value.startswith(CHECKSUM_ALGORITHM_PREFIX):
            raise ValueError(f"checksum must be prefixed {CHECKSUM_ALGORITHM_PREFIX!r}: {value!r}")
        hex_digits = value[len(CHECKSUM_ALGORITHM_PREFIX) :]
        if len(hex_digits) != 64 or any(c not in "0123456789abcdef" for c in hex_digits):
            raise ValueError(f"checksum must be 64 lowercase hex characters: {value!r}")
        return value

    def differences(self, other: ApprovalChecksums) -> tuple[ChecksumKind, ...]:
        """Which bindings differ, in a fixed order so the answer is deterministic.

        Returns every difference rather than the first: an operator investigating an invalidation
        needs to know whether the repository moved, the diff changed, the agent re-ran, or the
        gates concluded something new — and "one of these four" is a much weaker answer.
        """
        pairs = (
            (ChecksumKind.REPO_STATE, self.repo_state, other.repo_state),
            (ChecksumKind.DIFF, self.diff, other.diff),
            (ChecksumKind.AGENT_RESULT, self.agent_result, other.agent_result),
            (ChecksumKind.GATE_RESULT, self.gate_result, other.gate_result),
        )
        return tuple(kind for kind, mine, theirs in pairs if mine != theirs)


# -------------------------------------------------------------------------------------------
# Policy
# -------------------------------------------------------------------------------------------


class ApprovalPolicyOverlay(_ApprovalModel):
    """One configuration layer. Every field is optional; an absent field defers to the layer below.

    Separate from `ApprovalPolicy` because "unset" and "set to the default value" must be
    distinguishable: a gate that explicitly selects `PAUSE` and a gate that says nothing look
    identical if both are represented by a fully-populated model, and the difference is exactly
    what the `AUTO_APPROVE` opt-in rule turns on.
    """

    required: bool | None = None
    timeout_seconds: int | None = None
    timeout_action: TimeoutAction | None = None
    channels: tuple[ApprovalChannel, ...] | None = None
    approvers: tuple[str, ...] | None = None
    escalate_to: tuple[str, ...] | None = None
    escalation_extension_seconds: int | None = None
    escalation_fallback_action: TimeoutAction | None = None

    @field_validator("timeout_seconds", "escalation_extension_seconds")
    @classmethod
    def _positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("a duration in seconds must be positive")
        return value


class ApprovalPolicy(_ApprovalModel):
    """The resolved, immutable policy snapshot bound into one approval request.

    Snapshotted rather than referenced so that editing configuration after a request exists cannot
    retroactively change what that request was governed by. An operator who widens a timeout, adds
    an approver, or switches a timeout action affects the *next* request; the pending one keeps the
    rules it was created under, which is the only version a human could have been told about.

    `timeout_action_source` is part of the snapshot because it is what makes the `AUTO_APPROVE`
    rule auditable after the fact: a reader can see not only that a run auto-approved but that the
    permission to do so came from the gate or the run rather than from an inherited default.
    """

    required: bool
    timeout_seconds: int | None
    timeout_action: TimeoutAction
    channels: tuple[ApprovalChannel, ...]
    approvers: tuple[str, ...]
    escalate_to: tuple[str, ...]
    escalation_extension_seconds: int | None
    escalation_fallback_action: TimeoutAction
    timeout_action_source: PolicyLayer
    escalation_fallback_source: PolicyLayer

    @model_validator(mode="after")
    def _validate_policy(self) -> Self:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when set")
        if self.escalation_extension_seconds is not None and self.escalation_extension_seconds <= 0:
            raise ValueError("escalation_extension_seconds must be positive when set")
        if not self.channels:
            raise ValueError("a policy must permit at least one channel")
        if self.escalation_fallback_action is TimeoutAction.ESCALATE:
            # The bound on escalation. Escalating to an escalation is the unbounded loop this
            # subsystem is required not to have, and refusing it here means no configuration,
            # however assembled, can express one.
            raise ValueError("escalation_fallback_action must not be ESCALATE")
        if self.timeout_action is TimeoutAction.ESCALATE and not self.escalate_to:
            raise ValueError("a policy whose timeout action is ESCALATE must name escalate_to")
        return self


#: The built-in floor. Deliberately the most conservative policy expressible: approval is required,
#: nothing times out on its own, and the timeout action -- if a layer above adds a deadline without
#: naming one -- pauses for a human rather than deciding anything.
_BUILT_IN_DEFAULTS = ApprovalPolicyOverlay(
    required=True,
    timeout_seconds=None,
    timeout_action=TimeoutAction.PAUSE,
    channels=(ApprovalChannel.CLI,),
    approvers=(),
    escalate_to=(),
    escalation_extension_seconds=None,
    escalation_fallback_action=TimeoutAction.PAUSE,
)


def _resolve_field(
    field: str, overlays: Sequence[tuple[PolicyLayer, ApprovalPolicyOverlay]]
) -> tuple[Any, PolicyLayer]:
    """Take the highest-precedence layer that set `field`, and report which one that was."""
    value: Any = None
    source = PolicyLayer.BUILT_IN
    for layer, overlay in overlays:
        candidate = getattr(overlay, field)
        if candidate is not None:
            value, source = candidate, layer
    return value, source


def _require_explicit_opt_in(action: TimeoutAction, source: PolicyLayer, field: str) -> None:
    """`AUTO_APPROVE` may only be selected by the gate or by a per-run override.

    This is the subsystem's single most security-sensitive rule, so it fails closed and loudly
    rather than silently downgrading to something safer. A downgrade would leave a project
    configuration that *says* `auto_approve` behaving as `pause`, which is a trap: the operator
    would believe automation is enabled, discover it is not only when a deadline passes, and have
    nothing in the record explaining why. Refusing makes the misconfiguration visible at the moment
    it is written.
    """
    if action is TimeoutAction.AUTO_APPROVE and source not in _EXPLICIT_OPT_IN_LAYERS:
        raise ApprovalPolicyError(
            f"{field} AUTO_APPROVE requires explicit opt-in at the gate or per-run override; it "
            f"was inherited from the {source.value!r} layer. Automatic approval is never acquired "
            "by inheritance."
        )


def resolve_approval_policy(
    *,
    project: ApprovalPolicyOverlay | None = None,
    gate: ApprovalPolicyOverlay | None = None,
    run: ApprovalPolicyOverlay | None = None,
) -> ApprovalPolicy:
    """Resolve built-in defaults, then project, then per-gate, then per-run configuration.

    Each layer overrides only the fields it actually sets, so a project that widens a timeout does
    not also silently reset the channels a gate chose. The result is a frozen snapshot; nothing
    retains a reference to the overlays it came from.
    """
    overlays: list[tuple[PolicyLayer, ApprovalPolicyOverlay]] = [
        (PolicyLayer.BUILT_IN, _BUILT_IN_DEFAULTS)
    ]
    for layer, overlay in (
        (PolicyLayer.PROJECT, project),
        (PolicyLayer.GATE, gate),
        (PolicyLayer.RUN, run),
    ):
        if overlay is not None:
            overlays.append((layer, overlay))
    # Precedence is positional; asserting it here keeps the ordering honest if a layer is ever
    # inserted in the wrong place.
    ordered = [layer for layer, _ in overlays]
    assert ordered == [layer for layer in _LAYER_ORDER if layer in set(ordered)], ordered

    timeout_action, timeout_source = _resolve_field("timeout_action", overlays)
    fallback_action, fallback_source = _resolve_field("escalation_fallback_action", overlays)
    _require_explicit_opt_in(timeout_action, timeout_source, "timeout_action")
    _require_explicit_opt_in(fallback_action, fallback_source, "escalation_fallback_action")

    try:
        return ApprovalPolicy(
            required=_resolve_field("required", overlays)[0],
            timeout_seconds=_resolve_field("timeout_seconds", overlays)[0],
            timeout_action=timeout_action,
            channels=_resolve_field("channels", overlays)[0],
            approvers=_resolve_field("approvers", overlays)[0],
            escalate_to=_resolve_field("escalate_to", overlays)[0],
            escalation_extension_seconds=_resolve_field("escalation_extension_seconds", overlays)[
                0
            ],
            escalation_fallback_action=fallback_action,
            timeout_action_source=timeout_source,
            escalation_fallback_source=fallback_source,
        )
    except ValueError as exc:
        raise ApprovalPolicyError(str(exc)) from exc


# -------------------------------------------------------------------------------------------
# Persisted events
# -------------------------------------------------------------------------------------------


def _validate_aware_iso8601(value: str) -> str:
    """Every persisted timestamp is timezone-aware, for the same reason the state store requires
    it: a naive value cannot be compared against an aware one without raising, which would defeat
    both the monotonic-ordering check and every deadline comparison in this module."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"must be an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"must be timezone-aware: {value!r}")
    return value


class ApprovalEvent(_ApprovalModel):
    """One line of `approvals.jsonl`. Append-only; never edited, never removed.

    Every field beyond the first five is optional because one vocabulary serves seven event kinds,
    and a `REQUESTED` event has no approver just as a `CONSUMED` event has no policy. The
    combinations that are actually legal are enforced in `_validate_event_shape`, so an event whose
    kind and payload disagree cannot be written or read back.
    """

    approval_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    gate: str = Field(min_length=1)
    kind: ApprovalEventKind
    timestamp: str

    policy: ApprovalPolicy | None = None
    deadline: str | None = None
    checksums: ApprovalChecksums | None = None

    decision: ApprovalDecision | None = None
    approver: str | None = None
    source: ApprovalChannel | None = None
    origin: DecisionOrigin | None = None
    timeout_action_applied: TimeoutAction | None = None
    invalidated_checksums: tuple[ChecksumKind, ...] = ()
    observed_checksums: ApprovalChecksums | None = None

    @field_validator("timestamp", "deadline")
    @classmethod
    def _timestamps_are_aware(cls, value: str | None) -> str | None:
        return None if value is None else _validate_aware_iso8601(value)

    @model_validator(mode="after")
    def _validate_event_shape(self) -> Self:
        if self.kind is ApprovalEventKind.REQUESTED:
            if self.policy is None or self.checksums is None:
                raise ValueError("a REQUESTED event must carry its policy snapshot and checksums")
        if self.kind is ApprovalEventKind.DECIDED:
            if self.decision is None or self.origin is None:
                raise ValueError("a DECIDED event must carry a decision and an origin")
            if self.origin is DecisionOrigin.MANUAL and not self.approver:
                raise ValueError("a manual decision must name its approver")
            if self.origin is DecisionOrigin.AUTO and self.timeout_action_applied is None:
                raise ValueError("an automatic decision must record the timeout action applied")
        if self.kind is ApprovalEventKind.TIMED_OUT and self.timeout_action_applied is None:
            raise ValueError("a TIMED_OUT event must record the timeout action applied")
        if self.kind is ApprovalEventKind.INVALIDATED and not self.invalidated_checksums:
            raise ValueError("an INVALIDATED event must record which checksums changed")
        if self.kind is ApprovalEventKind.EXTENDED and self.deadline is None:
            raise ValueError("an EXTENDED event must carry the new deadline")
        return self


# -------------------------------------------------------------------------------------------
# Derived request view
# -------------------------------------------------------------------------------------------


class ApprovalRequest(_ApprovalModel):
    """One approval's complete current state, replayed from its events.

    Derived, never stored: reading this type always replays the file, so it cannot disagree with
    the durable record and there is no snapshot to keep in sync. `channels` and `approvers` are
    carried at the top level because the record contract names them there, and cross-checked
    against the snapshot so the two can never drift apart.
    """

    approval_id: str
    workflow_id: str
    gate: str
    requested_at: datetime
    deadline: datetime | None
    policy_snapshot: ApprovalPolicy
    channels: tuple[ApprovalChannel, ...]
    approvers: tuple[str, ...]
    checksums: ApprovalChecksums
    status: ApprovalStatus

    source: ApprovalChannel | None = None
    approver: str | None = None
    decision: ApprovalDecision | None = None
    decided_at: datetime | None = None
    manual_or_auto: DecisionOrigin | None = None
    timeout_action_applied: TimeoutAction | None = None

    escalated_at: datetime | None = None
    extension_granted: bool = False
    invalidated_checksums: tuple[ChecksumKind, ...] = ()

    @model_validator(mode="after")
    def _validate_request(self) -> Self:
        if self.channels != self.policy_snapshot.channels:
            raise ValueError("channels must equal the policy snapshot's channels")
        if self.approvers != self.policy_snapshot.approvers:
            raise ValueError("approvers must equal the policy snapshot's approvers")
        if self.decision is not None and self.manual_or_auto is None:
            raise ValueError("a decided request must record whether the decision was manual")
        if self.status is ApprovalStatus.INVALIDATED and not self.invalidated_checksums:
            raise ValueError("an invalidated request must record which checksums changed")
        return self

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    @property
    def approved(self) -> bool:
        """Approved and not yet spent. `CONSUMED` is deliberately excluded: an approval that has
        already been used is not an approval that can be used again."""
        return self.status is ApprovalStatus.APPROVED


# -------------------------------------------------------------------------------------------
# The service
# -------------------------------------------------------------------------------------------


class ApprovalService:
    """Durable, configurable approvals for future workflow gates.

    Holds a `StateStore` and nothing else. There is no provider, no agent, no Skill, no Git or
    GitHub client, and no network client reachable from here, so an approval cannot cause work to
    happen — it can only record that permission was asked for, given, withheld, expired, or spent.

    Every method is total with respect to the clock: `now` is a parameter (defaulting to the
    engine's single timestamp source) so that deadline behaviour is testable without sleeping and
    so nothing in this module depends on wall-clock progression inside a running process.
    """

    def __init__(self, store: StateStore) -> None:
        self._store = store

    @classmethod
    def for_config(cls, config: WorkflowConfig) -> ApprovalService:
        return cls(StateStore.for_config(config))

    # -- creation ---------------------------------------------------------------------------

    def request_approval(
        self,
        *,
        workflow_id: str,
        gate: str,
        approval_id: str,
        checksums: ApprovalChecksums,
        policy: ApprovalPolicy,
        now: datetime | None = None,
    ) -> ApprovalRequest:
        """Open one approval, bound to the four checksums and governed by a frozen policy snapshot.

        The policy is resolved by the caller (`resolve_approval_policy`) and snapshotted here, so
        the service never reads live configuration while an approval is open — which is what makes
        "configuration changes do not retroactively change an existing request" structural rather
        than a convention.
        """
        if not policy.required:
            raise ApprovalPolicyError(
                f"gate {gate!r} does not require approval (policy.required is False); requesting "
                "one would create a gate the configuration says should not exist"
            )
        if self._events(workflow_id, approval_id):
            raise ApprovalStateError(
                f"approval {approval_id!r} already exists for workflow {workflow_id!r}; an "
                "approval identifier is never reused"
            )
        requested_at = now or utc_now()
        deadline = (
            None
            if policy.timeout_seconds is None
            else requested_at + timedelta(seconds=policy.timeout_seconds)
        )
        self._append(
            ApprovalEvent(
                approval_id=approval_id,
                workflow_id=workflow_id,
                gate=gate,
                kind=ApprovalEventKind.REQUESTED,
                timestamp=requested_at.isoformat(),
                policy=policy,
                deadline=None if deadline is None else deadline.isoformat(),
                checksums=checksums,
            )
        )
        return self.get_approval(workflow_id=workflow_id, approval_id=approval_id)

    # -- reads ------------------------------------------------------------------------------

    def get_approval(self, *, workflow_id: str, approval_id: str) -> ApprovalRequest:
        """Replay one approval exactly as persisted. Evaluates no deadline and writes nothing.

        Separate from `evaluate_approval` because a pure read must stay a pure read: a caller
        inspecting history — an audit view, a report, a test — must be able to observe that an
        approval is `PENDING` past its deadline without that observation itself deciding the
        outcome.
        """
        events = self._events(workflow_id, approval_id)
        if not events:
            raise ApprovalNotFoundError(
                f"No approval {approval_id!r} for workflow {workflow_id!r}."
            )
        return _replay(events)

    def list_approvals(self, *, workflow_id: str) -> list[ApprovalRequest]:
        """Every approval for one workflow, in the order they were first requested."""
        grouped: dict[str, list[ApprovalEvent]] = {}
        for event in self._all_events(workflow_id):
            grouped.setdefault(event.approval_id, []).append(event)
        return [_replay(events) for events in grouped.values()]

    # -- decisions --------------------------------------------------------------------------

    def decide_approval(
        self,
        *,
        workflow_id: str,
        approval_id: str,
        decision: ApprovalDecision,
        approver: str,
        source: ApprovalChannel,
        now: datetime | None = None,
    ) -> ApprovalRequest:
        """Record one manual decision.

        The deadline is evaluated first, so a decision that arrives after a `FAIL` or `CANCEL`
        timeout has already fired is refused rather than silently overwriting the timeout's
        outcome. A `PAUSE` timeout is different by design: it leaves the approval awaiting a human,
        and this is that human.
        """
        current = self.evaluate_approval(workflow_id=workflow_id, approval_id=approval_id, now=now)
        if current.terminal:
            raise ApprovalStateError(
                f"approval {approval_id!r} is {current.status.value}; a decision cannot change a "
                "settled approval"
            )
        if source not in current.channels:
            raise ApprovalStateError(
                f"channel {source.value!r} is not permitted for approval {approval_id!r}: "
                f"{[channel.value for channel in current.channels]}"
            )
        if current.approvers and approver not in current.approvers:
            raise ApprovalStateError(
                f"approver {approver!r} is not on approval {approval_id!r}'s allowlist"
            )
        self._append(
            ApprovalEvent(
                approval_id=approval_id,
                workflow_id=workflow_id,
                gate=current.gate,
                kind=ApprovalEventKind.DECIDED,
                timestamp=(now or utc_now()).isoformat(),
                decision=decision,
                approver=approver,
                source=source,
                origin=DecisionOrigin.MANUAL,
            )
        )
        return self.get_approval(workflow_id=workflow_id, approval_id=approval_id)

    # -- lazy timeout evaluation ------------------------------------------------------------

    def evaluate_approval(
        self, *, workflow_id: str, approval_id: str, now: datetime | None = None
    ) -> ApprovalRequest:
        """Apply the policy's timeout action if the deadline has passed. Lazy, idempotent.

        This is the whole of the timeout mechanism. There is no thread, no timer, no scheduler and
        no sleep anywhere in this module: a deadline is an instant written to disk, and it takes
        effect the first time anyone looks after it passes. That is why it survives a restart —
        nothing about it lives in this process.

        Idempotent because each action appends a terminal-or-waiting event and the resulting status
        is no longer timeout-eligible; calling it again observes the same answer rather than
        applying the action twice.
        """
        moment = now or utc_now()
        current = self.get_approval(workflow_id=workflow_id, approval_id=approval_id)
        if current.status not in _TIMEOUT_ELIGIBLE_STATUSES:
            return current
        if current.deadline is None or moment < current.deadline:
            return current

        policy = current.policy_snapshot
        action = (
            policy.escalation_fallback_action
            if current.status is ApprovalStatus.ESCALATED
            else policy.timeout_action
        )
        self._apply_timeout(current, action, moment)
        return self.get_approval(workflow_id=workflow_id, approval_id=approval_id)

    def _apply_timeout(
        self, current: ApprovalRequest, action: TimeoutAction, moment: datetime
    ) -> None:
        """Write the events one expired deadline produces. One branch per action, no fallthrough."""
        common: dict[str, Any] = {
            "approval_id": current.approval_id,
            "workflow_id": current.workflow_id,
            "gate": current.gate,
            "timestamp": moment.isoformat(),
        }
        if action is TimeoutAction.AUTO_APPROVE:
            # The only path that grants permission without a human. It is reachable only because
            # the gate or the run explicitly asked for it (`_require_explicit_opt_in`), and the
            # resulting approval is still bound to the checksums captured at request time -- so it
            # authorizes the state that was pending, never whatever the repository became.
            self._append(
                ApprovalEvent(
                    **common,
                    kind=ApprovalEventKind.DECIDED,
                    decision=ApprovalDecision.APPROVE,
                    origin=DecisionOrigin.AUTO,
                    timeout_action_applied=TimeoutAction.AUTO_APPROVE,
                )
            )
            return
        if action is TimeoutAction.ESCALATE:
            self._append(
                ApprovalEvent(
                    **common,
                    kind=ApprovalEventKind.ESCALATED,
                    timeout_action_applied=TimeoutAction.ESCALATE,
                )
            )
            extension = current.policy_snapshot.escalation_extension_seconds
            if extension is not None and not current.extension_granted:
                # At most one extension, ever. `extension_granted` is replayed from the event
                # history rather than counted in memory, so a restart cannot hand out a second one.
                self._append(
                    ApprovalEvent(
                        **common,
                        kind=ApprovalEventKind.EXTENDED,
                        deadline=(moment + timedelta(seconds=extension)).isoformat(),
                    )
                )
            return
        self._append(
            ApprovalEvent(**common, kind=ApprovalEventKind.TIMED_OUT, timeout_action_applied=action)
        )

    # -- consumption ------------------------------------------------------------------------

    def consume_approval(
        self,
        *,
        workflow_id: str,
        approval_id: str,
        checksums: ApprovalChecksums,
        now: datetime | None = None,
    ) -> ApprovalRequest:
        """Spend one approval, but only if it still binds the state it was granted against.

        The checksums are recomputed by the caller and compared here *immediately before* the
        approval is spent, which is the point of the whole binding: an approval granted against one
        repository state must not authorize a different one, however little time has passed and
        whoever granted it. Any difference invalidates — the approval is not silently re-requested,
        not re-approved, and not usable again.
        """
        moment = now or utc_now()
        current = self.evaluate_approval(
            workflow_id=workflow_id, approval_id=approval_id, now=moment
        )
        if not current.approved:
            raise ApprovalStateError(
                f"approval {approval_id!r} is {current.status.value}, not approved; it cannot be "
                "consumed"
            )
        changed = current.checksums.differences(checksums)
        if changed:
            self._append(
                ApprovalEvent(
                    approval_id=approval_id,
                    workflow_id=workflow_id,
                    gate=current.gate,
                    kind=ApprovalEventKind.INVALIDATED,
                    timestamp=moment.isoformat(),
                    invalidated_checksums=changed,
                    observed_checksums=checksums,
                )
            )
            return self.get_approval(workflow_id=workflow_id, approval_id=approval_id)
        self._append(
            ApprovalEvent(
                approval_id=approval_id,
                workflow_id=workflow_id,
                gate=current.gate,
                kind=ApprovalEventKind.CONSUMED,
                timestamp=moment.isoformat(),
            )
        )
        return self.get_approval(workflow_id=workflow_id, approval_id=approval_id)

    # -- persistence ------------------------------------------------------------------------

    def _append(self, event: ApprovalEvent) -> None:
        self._store.record_approval(event.workflow_id, event, timestamp=event.timestamp)

    def _all_events(self, workflow_id: str) -> list[ApprovalEvent]:
        return self._store.read_approvals(
            workflow_id, ApprovalEvent, timestamp_of=lambda event: event.timestamp
        )

    def _events(self, workflow_id: str, approval_id: str) -> list[ApprovalEvent]:
        """One approval's events. Filtered from the shared file rather than stored separately, so
        every approval in a workflow shares one append-ordered history and one lock."""
        return [
            event for event in self._all_events(workflow_id) if event.approval_id == approval_id
        ]


def _replay(events: Sequence[ApprovalEvent]) -> ApprovalRequest:
    """Fold one approval's event history into its current state.

    The first event must be the request; everything after it refines the answer. Nothing here
    consults a clock — replay is a pure function of what is on disk, which is what makes a restart
    observe exactly the state the previous process left behind.
    """
    first = events[0]
    if first.kind is not ApprovalEventKind.REQUESTED or first.policy is None:
        raise ApprovalStateError(
            f"approval {first.approval_id!r} does not begin with a REQUESTED event; its history "
            "is not replayable"
        )
    if first.checksums is None:  # pragma: no cover - guaranteed by `_validate_event_shape`
        raise ApprovalStateError(f"approval {first.approval_id!r} has no bound checksums")

    state: dict[str, Any] = {
        "approval_id": first.approval_id,
        "workflow_id": first.workflow_id,
        "gate": first.gate,
        "requested_at": datetime.fromisoformat(first.timestamp),
        "deadline": None if first.deadline is None else datetime.fromisoformat(first.deadline),
        "policy_snapshot": first.policy,
        "channels": first.policy.channels,
        "approvers": first.policy.approvers,
        "checksums": first.checksums,
        "status": ApprovalStatus.PENDING,
    }

    for event in events[1:]:
        moment = datetime.fromisoformat(event.timestamp)
        if event.kind is ApprovalEventKind.DECIDED and event.decision is not None:
            state.update(
                status=_STATUS_FOR_DECISION[event.decision],
                decision=event.decision,
                approver=event.approver,
                source=event.source,
                decided_at=moment,
                manual_or_auto=event.origin,
                timeout_action_applied=event.timeout_action_applied,
            )
        elif event.kind is ApprovalEventKind.TIMED_OUT:
            state.update(
                status=_STATUS_FOR_TIMEOUT[_require_action(event)],
                timeout_action_applied=event.timeout_action_applied,
            )
        elif event.kind is ApprovalEventKind.ESCALATED:
            state.update(
                status=ApprovalStatus.ESCALATED,
                escalated_at=moment,
                timeout_action_applied=TimeoutAction.ESCALATE,
            )
        elif event.kind is ApprovalEventKind.EXTENDED and event.deadline is not None:
            state.update(deadline=datetime.fromisoformat(event.deadline), extension_granted=True)
        elif event.kind is ApprovalEventKind.INVALIDATED:
            state.update(
                status=ApprovalStatus.INVALIDATED, invalidated_checksums=event.invalidated_checksums
            )
        elif event.kind is ApprovalEventKind.CONSUMED:
            state.update(status=ApprovalStatus.CONSUMED)

    return ApprovalRequest(**state)


def _require_action(event: ApprovalEvent) -> TimeoutAction:
    if event.timeout_action_applied is None:  # pragma: no cover - `_validate_event_shape` enforces
        raise ApprovalStateError("a TIMED_OUT event without a timeout action is not replayable")
    return event.timeout_action_applied


#: What a fired timeout leaves the approval as. `PAUSE` maps to a *non-terminal* status on purpose:
#: nobody answered in time, which is not the same as an answer, so the approval stays resumable.
_STATUS_FOR_TIMEOUT: Mapping[TimeoutAction, ApprovalStatus] = {
    TimeoutAction.PAUSE: ApprovalStatus.HUMAN_INTERVENTION_REQUIRED,
    TimeoutAction.FAIL: ApprovalStatus.FAILED,
    TimeoutAction.CANCEL: ApprovalStatus.CANCELLED,
    TimeoutAction.AUTO_APPROVE: ApprovalStatus.APPROVED,
    TimeoutAction.ESCALATE: ApprovalStatus.ESCALATED,
}


def _utc(moment: datetime) -> datetime:  # pragma: no cover - convenience for callers and tests
    return moment.astimezone(UTC)
