"""Core runtime workflow state machine (WORKFLOW_STATES.md §2-4) and human-authorization
binding for the sole human gate, `CREATED -> AUTHORIZED` (HUMAN_AUTHORIZATION_MODEL.md).

The state-machine section defines the 19-state model and the complete, closed set of allowed
transitions (§3). Every pair not in that set is rejected as forbidden (§4) by construction:
`ALLOWED_TRANSITIONS` is the sole source of truth, so a skipped intermediate state, a
transition back to `CREATED`/`AUTHORIZED` from any later state, and any transition out of a
terminal state are all simply absent from it rather than checked by separate forbidden-
transition logic.

The authorization section adds nothing to `ALLOWED_TRANSITIONS` — it only gates the one existing
`CREATED -> AUTHORIZED` edge behind an explicit, scoped `AuthorizationRecord` match before
calling the same `WorkflowStateMachine.transition_to` used everywhere else.

The resume section (§6) reconstructs a `WorkflowStateMachine` purely by replaying a workflow's
persisted `StateTransitionRecord` history — read verbatim through the already-existing
`StateStore.read_transitions` API — back through the same transition-table validation
`transition_to` itself uses, so resume can never accept a transition Step 5A's table would
reject. It adds no new state and no new transition. Crossing the one `CREATED -> AUTHORIZED` edge
during replay is never taken on the strength of the replayed `StateTransitionRecord` alone (that
record is just a caller-fabricable from/to/timestamp/actor tuple): `_replay_history` requires a
`StateStore` and independently loads and validates the persisted `AuthorizationRecord` for that
exact workflow from it before ever mutating state — a caller possessing only an in-memory list of
`StateTransitionRecord`s, with no real `StateStore` backing an `authorization.json` for that
workflow, cannot reach `AUTHORIZED` this way (`HUMAN_AUTHORIZATION_MODEL.md` §1).

The retry/reconciliation section (§5, §5a) is pure decision logic: given persisted history (via
the same `_load_and_validate_history`/`_replay_history` helpers `resume_workflow` itself uses —
there is no second, weaker replay path) and, where the policy requires it, caller-supplied
evidence, it computes what the Orchestrator is permitted to do next — retry, enter `REPAIRING`,
advance, or fail — and returns that as a typed
result. It never executes a command, Skill, Provider, or Git/GitHub operation itself; it never
performs the transition it recommends; and every recommended transition is checked against
`ALLOWED_TRANSITIONS` before being returned, so it can never surface an undocumented one.

AUTO-002 additionally owns one narrow resume-only observation boundary: fixed read-only local
Git queries, confined contract reads, and runtime-version observation. It performs no mutation,
network/GitHub access, arbitrary command execution, branch creation, Agent, Skill, or Provider
invocation (DD-14; WORKFLOW_STATES.md §6a).
"""

import fcntl
import fnmatch
import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from weakref import WeakKeyDictionary

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from agentos_workflow.config.schema import (
    WorkflowConfig,
    canonical_repository_relative_path,
)
from agentos_workflow.observation import (
    LocalEvidenceObservationError,
    LocalEvidenceObserver,
    LocalResumeObserver,
    ResumeObservation,
    ResumeObservationError,
    ResumeObserver,
    canonical_repository_identity,
    read_evidence_artifact,
)
from agentos_workflow.orchestrator.lock import (
    LockContentionError,
    RepositoryLock,
    canonical_lock_path,
)
from agentos_workflow.orchestrator.state_store import (
    StateStore,
    StateStoreCorruptionError,
    StateStoreError,
    StateStorePathConfinementError,
    StateTransitionRecord,
    _confined_record_fd,
    _confined_workflow_directory_fd,
    _DuplicateJSONKeyError,
    _loads_rejecting_duplicate_keys,
    _safe_workflow_id,  # whitebox reuse: the same workflow-ID path confinement StateStore uses
    _validate_confined_regular_file,
    _write_all,
)


class WorkflowState(StrEnum):
    """WORKFLOW_STATES.md §2 — the complete, closed set of 19 states."""

    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    PRECONDITIONS_CHECKED = "PRECONDITIONS_CHECKED"
    BRANCH_CREATED = "BRANCH_CREATED"
    IMPLEMENTING = "IMPLEMENTING"
    VALIDATING = "VALIDATING"
    QA_RUNNING = "QA_RUNNING"
    REPAIRING = "REPAIRING"
    READY_TO_COMMIT = "READY_TO_COMMIT"
    COMMITTED = "COMMITTED"
    PUSHED = "PUSHED"
    PR_OPEN = "PR_OPEN"
    AUTO_MERGE_ENABLED = "AUTO_MERGE_ENABLED"
    WAITING_FOR_CHECKS = "WAITING_FOR_CHECKS"
    MERGED = "MERGED"
    CLOSING = "CLOSING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# WORKFLOW_STATES.md §8: no outgoing transition at all.
TERMINAL_STATES: frozenset[WorkflowState] = frozenset(
    {WorkflowState.DONE, WorkflowState.FAILED, WorkflowState.CANCELLED}
)

# WORKFLOW_STATES.md §3's transition table, transcribed exactly (37 edges): the forward-progress
# chain, every "-> FAILED" row (machine-gate failure, interruption/resume drift, or
# initial-execution-failure exhaustion — §3's three failure reasons, all sharing the same edge
# per state), the VALIDATING/QA_RUNNING <-> REPAIRING repair cycle, and the pre-IMPLEMENTING
# {CREATED, AUTHORIZED, PRECONDITIONS_CHECKED, BRANCH_CREATED} -> CANCELLED operator-abort set.
ALLOWED_TRANSITIONS: frozenset[tuple[WorkflowState, WorkflowState]] = frozenset(
    {
        (WorkflowState.CREATED, WorkflowState.AUTHORIZED),
        (WorkflowState.AUTHORIZED, WorkflowState.PRECONDITIONS_CHECKED),
        (WorkflowState.AUTHORIZED, WorkflowState.FAILED),
        (WorkflowState.PRECONDITIONS_CHECKED, WorkflowState.BRANCH_CREATED),
        (WorkflowState.PRECONDITIONS_CHECKED, WorkflowState.FAILED),
        (WorkflowState.BRANCH_CREATED, WorkflowState.IMPLEMENTING),
        (WorkflowState.BRANCH_CREATED, WorkflowState.FAILED),
        (WorkflowState.IMPLEMENTING, WorkflowState.VALIDATING),
        (WorkflowState.IMPLEMENTING, WorkflowState.FAILED),
        (WorkflowState.VALIDATING, WorkflowState.QA_RUNNING),
        (WorkflowState.VALIDATING, WorkflowState.REPAIRING),
        (WorkflowState.VALIDATING, WorkflowState.FAILED),
        (WorkflowState.QA_RUNNING, WorkflowState.READY_TO_COMMIT),
        (WorkflowState.QA_RUNNING, WorkflowState.REPAIRING),
        (WorkflowState.QA_RUNNING, WorkflowState.FAILED),
        (WorkflowState.REPAIRING, WorkflowState.VALIDATING),
        (WorkflowState.REPAIRING, WorkflowState.FAILED),
        (WorkflowState.READY_TO_COMMIT, WorkflowState.COMMITTED),
        (WorkflowState.READY_TO_COMMIT, WorkflowState.FAILED),
        (WorkflowState.COMMITTED, WorkflowState.PUSHED),
        (WorkflowState.COMMITTED, WorkflowState.FAILED),
        (WorkflowState.PUSHED, WorkflowState.PR_OPEN),
        (WorkflowState.PUSHED, WorkflowState.FAILED),
        (WorkflowState.PR_OPEN, WorkflowState.AUTO_MERGE_ENABLED),
        (WorkflowState.PR_OPEN, WorkflowState.FAILED),
        (WorkflowState.AUTO_MERGE_ENABLED, WorkflowState.WAITING_FOR_CHECKS),
        (WorkflowState.AUTO_MERGE_ENABLED, WorkflowState.FAILED),
        (WorkflowState.WAITING_FOR_CHECKS, WorkflowState.MERGED),
        (WorkflowState.WAITING_FOR_CHECKS, WorkflowState.FAILED),
        (WorkflowState.MERGED, WorkflowState.CLOSING),
        (WorkflowState.MERGED, WorkflowState.FAILED),
        (WorkflowState.CLOSING, WorkflowState.DONE),
        (WorkflowState.CLOSING, WorkflowState.FAILED),
        (WorkflowState.CREATED, WorkflowState.CANCELLED),
        (WorkflowState.AUTHORIZED, WorkflowState.CANCELLED),
        (WorkflowState.PRECONDITIONS_CHECKED, WorkflowState.CANCELLED),
        (WorkflowState.BRANCH_CREATED, WorkflowState.CANCELLED),
    }
)


class InvalidTransitionError(Exception):
    """Raised when a transition is not one of `ALLOWED_TRANSITIONS` (WORKFLOW_STATES.md §3-4)."""

    def __init__(self, from_state: WorkflowState, to_state: WorkflowState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Transition {from_state} -> {to_state} is not allowed: absent from "
            "WORKFLOW_STATES.md §3's complete, closed transition set, and therefore "
            "forbidden by §4."
        )


_HUMAN_PERMITTED_EDGES: frozenset[tuple[WorkflowState, WorkflowState]] = frozenset(
    {(WorkflowState.CREATED, WorkflowState.AUTHORIZED)}
    | {
        (from_state, WorkflowState.CANCELLED)
        for from_state in (
            WorkflowState.CREATED,
            WorkflowState.AUTHORIZED,
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.BRANCH_CREATED,
        )
    }
)
"""AUDIT_MODEL.md §3: `actor` is `"human"` "(authorization/cancellation only)" — the complete set
of edges a `StateTransitionRecord` may legally record with `actor="human"`: the one human gate
(`CREATED -> AUTHORIZED`) and the four pre-`IMPLEMENTING` operator-abort edges (`WORKFLOW_STATES.md`
§3's `{CREATED, AUTHORIZED, PRECONDITIONS_CHECKED, BRANCH_CREATED} -> CANCELLED` set). Every other
edge in `ALLOWED_TRANSITIONS` is machine/orchestrator-driven and must never be recorded as
`actor="human"`.
"""


class InvalidActorForTransitionError(Exception):
    """Raised when a transition record's `actor` is `"human"` for an edge other than the
    contractually permitted authorization or cancellation edges (`_HUMAN_PERMITTED_EDGES`).

    `"human"` is reserved evidence of an actual human gate having been passed
    (`HUMAN_AUTHORIZATION_MODEL.md` §1) or an operator abort — never a label a machine-driven
    transition (precondition checks, implementation, validation, QA, commit/push/PR/merge
    automation) may claim for itself, on append or on replay of previously persisted history.
    """

    def __init__(self, from_state: WorkflowState, to_state: WorkflowState, actor: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.actor = actor
        super().__init__(
            f"actor {actor!r} is not permitted for transition {from_state} -> {to_state}: "
            "'human' is reserved for CREATED -> AUTHORIZED and the operator-cancellation edges "
            "(AUDIT_MODEL.md §3); every other edge is machine/orchestrator-driven."
        )


def validate_actor_for_transition(
    from_state: WorkflowState, to_state: WorkflowState, actor: str
) -> None:
    """Raise `InvalidActorForTransitionError` unless `actor` is legal for `from_state -> to_state`.

    Only rejects an inappropriate `"human"` — `"orchestrator"` and `"agent:<Name>"` remain legal
    on every edge, including the human-permitted ones (an automated abort is still a legitimate
    `-> CANCELLED`, just never claiming to be a human action if it is not one).
    """
    if actor == "human" and (from_state, to_state) not in _HUMAN_PERMITTED_EDGES:
        raise InvalidActorForTransitionError(from_state, to_state, actor)


class AuthorizationBypassError(Exception):
    """Raised when `AUTHORIZED` is reached any way other than through `authorize()` or a
    validated replay of persisted history, or when a `WorkflowStateMachine` is constructed
    directly at a state other than `CREATED` without the internal construction token.

    HUMAN_AUTHORIZATION_MODEL.md §1: "the only human gate in this system is the
    CREATED -> AUTHORIZED transition." Reconstructing an already-authorized workflow from
    persisted history (resume) is legitimate and does not raise this — it never constructs
    directly at `AUTHORIZED`; it replays from `CREATED`, and the one step that crosses
    `AUTHORIZED` (`_apply_validated_authorization`) independently loads and validates a real,
    persisted `AuthorizationRecord` from a `StateStore` before mutating state, rather than
    trusting *which function* is calling.
    """


class _InternalConstructionToken:
    """Capability object gating construction of a `WorkflowStateMachine` anywhere other than
    `CREATED` — a leading underscore alone does not gate this, since Python does not enforce it;
    a caller must additionally possess a reference to the single module-private instance
    (`_INTERNAL_TOKEN`). This governs only the *ordinary, lower-sensitivity* test-convenience
    surface (fabricating a machine at, say, `VALIDATING` or `FAILED` for isolated unit tests).

    It does **not** govern reaching `AUTHORIZED` specifically, and never has: reaching
    `AUTHORIZED` is never gated by presenting *any* value (a token, a flag, or a claim of being a
    particular caller) — every path that reaches it (`authorize()`, and the replay section's
    `_apply_validated_authorization`) independently loads and validates real, persisted
    authorization evidence from a `StateStore` in the same breath it mutates state, so possessing
    an importable capability object proves nothing and grants nothing here (see the adversarial
    tests in `test_engine_authorization.py::TestStructuralNonBypassability`).
    """

    __slots__ = ()


_INTERNAL_TOKEN = _InternalConstructionToken()


def _make_machine_state_storage() -> tuple[
    Callable[["WorkflowStateMachine", WorkflowState], None],
    Callable[["WorkflowStateMachine"], WorkflowState],
    Callable[["WorkflowStateMachine", WorkflowState], None],
    Callable[["WorkflowStateMachine", StateTransitionRecord, StateStore], None],
]:
    """Create closure-owned authoritative state storage.

    No raw setter capable of writing `AUTHORIZED` is returned. The only returned operation that
    can write that value first invokes the complete persisted-authorization validator. Keeping
    the storage itself in this closure also means instance attribute APIs — including
    `object.__setattr__` and `__dict__` injection — cannot alter authoritative state.
    """
    states: WeakKeyDictionary[object, WorkflowState] = WeakKeyDictionary()

    def initialize(machine: "WorkflowStateMachine", state: WorkflowState) -> None:
        if state is WorkflowState.AUTHORIZED:
            raise AuthorizationBypassError(
                "Authoritative state storage cannot be initialized directly at AUTHORIZED."
            )
        states[machine] = state

    def get(machine: "WorkflowStateMachine") -> WorkflowState:
        return states[machine]

    def set_non_authorized(machine: "WorkflowStateMachine", state: WorkflowState) -> None:
        if state is WorkflowState.AUTHORIZED:
            raise AuthorizationBypassError(
                "The generic state-storage mutator can never set AUTHORIZED."
            )
        states[machine] = state

    def commit_validated_authorized(
        machine: "WorkflowStateMachine",
        record: StateTransitionRecord,
        state_store: StateStore,
    ) -> None:
        _validate_persisted_authorization_evidence(machine, record=record, state_store=state_store)
        states[machine] = WorkflowState.AUTHORIZED

    return initialize, get, set_non_authorized, commit_validated_authorized


(
    _initialize_machine_state,
    _get_machine_state,
    _set_non_authorized_machine_state,
    _commit_validated_authorized_machine_state,
) = _make_machine_state_storage()


def is_transition_allowed(from_state: WorkflowState, to_state: WorkflowState) -> bool:
    """Whether `from_state -> to_state` is a legal edge (§3).

    Every case WORKFLOW_STATES.md §4 names as forbidden is, by construction, absent from
    `ALLOWED_TRANSITIONS`: a skipped intermediate state has no direct edge; every state but
    `CREATED` has no edge targeting `AUTHORIZED`, and only `CREATED` has an edge targeting it in
    the first place, so no later state can return to either; and the terminal states
    (`DONE`/`FAILED`/`CANCELLED`) contribute no outgoing edges at all.
    """
    return (from_state, to_state) in ALLOWED_TRANSITIONS


def validate_transition(from_state: WorkflowState, to_state: WorkflowState) -> None:
    """Raise `InvalidTransitionError` if the transition is not allowed."""
    if not is_transition_allowed(from_state, to_state):
        raise InvalidTransitionError(from_state, to_state)


class WorkflowStateMachine:
    """Tracks one workflow's current state in memory and enforces `ALLOWED_TRANSITIONS`.

    Not the Orchestrator: no persistence, no Agent/Skill/Provider invocation. A rejected
    `transition_to` call always leaves `.state` exactly as it was — validation happens before
    any mutation, never after.
    """

    __slots__ = ("__weakref__",)

    def __init__(
        self,
        initial_state: WorkflowState = WorkflowState.CREATED,
        *,
        _token: _InternalConstructionToken | None = None,
    ) -> None:
        if initial_state is WorkflowState.AUTHORIZED:
            # No bypass here at all, ever, for any caller: nothing in this module legitimately
            # constructs a machine directly at AUTHORIZED — authorize() always constructs at
            # CREATED and applies the transition, and _replay_history always starts at CREATED
            # and walks forward. A token check here would be exactly the reusable,
            # import-and-replay capability that was found unsafe (see
            # `_InternalConstructionToken`'s docstring) — so this case takes no token at all.
            raise AuthorizationBypassError(
                "WorkflowStateMachine may not be constructed directly at AUTHORIZED under any "
                "circumstances; the only legitimate paths to AUTHORIZED are authorize() (a "
                "fresh, scope-validated authorization) and resume_workflow() (replaying "
                "already-persisted, already-validated history from CREATED)."
            )
        if initial_state is not WorkflowState.CREATED and _token is not _INTERNAL_TOKEN:
            raise AuthorizationBypassError(
                f"WorkflowStateMachine may not be constructed directly at "
                f"{initial_state.value!r}; ordinary construction always starts at CREATED. "
                "Every later state is reached only by the real transition path (authorize(), "
                "then transition_to()) or, for replay, the internal capability token — never by "
                "fabricating a machine already at that state."
            )
        _initialize_machine_state(self, initial_state)

    @property
    def _state(self) -> WorkflowState:
        """Read-only compatibility view of the closure-owned authoritative state."""
        return _get_machine_state(self)

    @_state.setter
    def _state(self, value: object) -> None:
        raise AuthorizationBypassError(
            "The authoritative workflow state is not instance-writable. Use authorize(), "
            "resume_workflow(), or a validated state-machine transition."
        )

    @property
    def state(self) -> WorkflowState:
        return _get_machine_state(self)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def can_transition_to(self, to_state: WorkflowState) -> bool:
        return is_transition_allowed(self.state, to_state)

    def transition_to(self, to_state: WorkflowState) -> WorkflowState:
        """Validate then apply the transition; return the new current state.

        Raises `InvalidTransitionError` without mutating `.state` if the transition is illegal.
        Raises `AuthorizationBypassError` — never mutating `.state` — if `to_state` is
        `AUTHORIZED`: that transition is never reachable through this generic method, under any
        circumstances or from any caller — call `authorize()` instead.
        """
        if to_state is WorkflowState.AUTHORIZED:
            raise AuthorizationBypassError(
                "transition_to(AUTHORIZED) is never permitted directly; call authorize() "
                "instead (HUMAN_AUTHORIZATION_MODEL.md §1: 'the only human gate')."
            )
        return self._apply_transition(to_state)

    def _apply_transition(self, to_state: WorkflowState) -> WorkflowState:
        """Validate then apply the transition. Never applies `AUTHORIZED` — unconditionally, for
        every caller, with no exception for any function's identity, and with no separate
        AUTHORIZED-only mutator method anywhere on this class either: there is no callable on
        `WorkflowStateMachine`, public or private, that sets `.state` to `AUTHORIZED` given zero
        evidence. The two legitimate paths that reach `AUTHORIZED` (`authorize()`, and the replay
        section's `_apply_validated_authorization`) each independently validate real, persisted
        authorization evidence through the closure-owned committer. That committer exposes no raw
        authorized-state setter: every call re-runs the persisted-evidence validator immediately
        before mutation.
        """
        if to_state is WorkflowState.AUTHORIZED:
            raise AuthorizationBypassError(
                "_apply_transition(AUTHORIZED) is never permitted, from any caller: reaching "
                "AUTHORIZED always requires independently validating real, persisted "
                "authorization evidence in the same call that mutates state — see authorize() "
                "and _apply_validated_authorization() (HUMAN_AUTHORIZATION_MODEL.md §1). No "
                "other method on this class applies AUTHORIZED either."
            )
        validate_transition(self.state, to_state)
        _set_non_authorized_machine_state(self, to_state)
        return self.state


# --------------------------------------------------------------------------------------------
# Human-authorization binding (HUMAN_AUTHORIZATION_MODEL.md).
#
# "The only human gate in this system is the CREATED -> AUTHORIZED transition" (§1). Everything
# below gates that one existing edge; it adds no new state and no new transition to
# `ALLOWED_TRANSITIONS`.
# --------------------------------------------------------------------------------------------


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_iso8601(value: str) -> str:
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"must be an ISO-8601 timestamp: {value!r}") from exc
    return value


_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _validate_git_sha(value: str) -> str:
    if not _GIT_SHA_RE.fullmatch(value):
        raise ValueError(f"must be a 40-character lowercase hex git SHA: {value!r}")
    return value


def _validate_remote_ref(value: str) -> str:
    if not value.startswith("refs/"):
        raise ValueError(f"must be a ref of the form 'refs/...': {value!r}")
    return value


class AuthorizationRecord(_StrictModel):
    """One captured authorization, bound to every field HUMAN_AUTHORIZATION_MODEL.md §2 names.

    This is data only: it records what the Human Owner authorized at authorization time. It
    never re-verifies any bound value against live repository, Git, or contract-file state —
    that is the Precondition Gate's job (`MACHINE_GATES.md` §2), explicitly out of this step's
    scope (no precondition checking is implemented here). `authorize()` below checks only the
    subset of these fields that identify *what is being authorized* (workflow, repository,
    stage, planned branch, baseline branch) — the remaining fields (`repository_path`,
    `stage_contract_path`, `stage_contract_hash`, `baseline_commit_sha`, `engine_version`) are
    captured verbatim for later drift-detection by the (not-yet-implemented) Precondition Gate
    and resume logic, per §4's invalidation conditions, but are not matched against anything
    live by this module.
    """

    workflow_id: str = Field(min_length=1)
    repository_identity: str = Field(min_length=1)
    repository_path: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    stage_contract_path: str = Field(min_length=1)
    stage_contract_hash: str = Field(min_length=1)
    baseline_branch: str = Field(min_length=1)
    baseline_commit_sha: str = Field(min_length=1)
    planned_stage_branch: str = Field(min_length=1)
    authorized_at: str
    authorized_by: str | None = None
    engine_version: str = Field(min_length=1)

    _validate_authorized_at = field_validator("authorized_at")(_validate_iso8601)

    @field_validator("authorized_by")
    @classmethod
    def _authorized_by_not_blank(cls, value: str | None) -> str | None:
        # "Authorizing human identity, when available" (§2 item 10) — absence (None) is legal;
        # a present-but-blank value is not, since that would be a malformed record pretending
        # to carry an identity it doesn't.
        if value is not None and value.strip() == "":
            raise ValueError("authorized_by must not be blank when provided")
        return value


class AuthorizationContext(_StrictModel):
    """The identity a specific workflow instance requires any authorization record to match.

    Constructed independently of any `AuthorizationRecord` — from the Orchestrator's own
    knowledge of the workflow it is about to authorize, never derived from the record itself —
    so a record cannot silently redefine what it is authorizing. This is what makes
    authorization scoped (requirement: authorization for one workflow, repository, stage, or
    branch must never authorize another).
    """

    workflow_id: str = Field(min_length=1)
    repository_identity: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    planned_stage_branch: str = Field(min_length=1)
    baseline_branch: str = Field(min_length=1)


class CurrentAuthorizationBinding(_StrictModel):
    """Deprecated lower-level compatibility shape for authorization-bound fields.
    (`HUMAN_AUTHORIZATION_MODEL.md` §2) that `AuthorizationContext` does not already carry —
    items 2, 4, 5, 7, and 11: repository path, stage contract path, stage contract hash,
    baseline commit SHA, and engine version.

    Production `WorkflowSession.resume` never treats this model as live evidence: it constructs
    the DD-14 local observer internally and the Orchestrator compares those raw observations.
    The model remains accepted only by the module-level white-box compatibility path used by
    accumulated lower-level tests; new production callers must use `WorkflowSession.resume`.

    Two other §2 fields have no live counterpart to compare against and are deliberately not
    part of this model: authorization timestamp (item 9) and authorizing human identity (item
    10) are facts about the authorization *event*, not properties of present repository state —
    nothing in `HUMAN_AUTHORIZATION_MODEL.md` defines a "current" value either could drift from.
    They are still validated for well-formedness, at load time, by `AuthorizationRecord`'s own
    field validators.
    """

    repository_path: str = Field(min_length=1)
    stage_contract_path: str = Field(min_length=1)
    stage_contract_hash: str = Field(min_length=1)
    baseline_commit_sha: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)


class AuthorizationError(Exception):
    """Base error for authorization binding/validation failures."""


class MissingAuthorizationError(AuthorizationError):
    """Raised when no authorization record is supplied. Absence is never approval."""


class AuthorizationRecordError(AuthorizationError):
    """Raised when a candidate authorization record is malformed (fails schema validation)."""


class AuthorizationScopeMismatchError(AuthorizationError):
    """Raised when a supplied record's bound value does not match the requesting context."""

    def __init__(self, field: str, expected: str, actual: str) -> None:
        self.field = field
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Authorization scope mismatch on {field!r}: context requires {expected!r}, "
            f"record is bound to {actual!r}. This authorization does not cover this workflow."
        )


class AuthorizationBindingDriftError(AuthorizationError):
    """Raised on resume when an authorization-bound value no longer matches its independently
    supplied current value (`HUMAN_AUTHORIZATION_MODEL.md` §4; `WORKFLOW_STATES.md` §6 item 3).

    Distinct from `AuthorizationScopeMismatchError`: that error rejects a *fresh* authorization
    request (`authorize()`) or an obviously-wrong resume target, neither of which ever mutates an
    in-progress workflow. This error means a workflow that *was* validly authorized has since
    drifted — `resume_workflow` durably records the required `-> FAILED` transition before this
    error propagates, so the failure is never just reported to the caller and then forgotten.

    Argument convention (GOV-AUTO-07, resolving AUTO-008's F-1) — binding at **every** raise site
    of this error in this module, and on any new one:

    * `expected` is the **reference** the check enforces: the authorization-bound value where the
      comparison has one, otherwise the invariant/required value the check demands.
    * `actual` is the **value under judgement**: the current runtime, repository, live observation,
      or caller/disk-supplied value that was found in the reference's place.

    Where a persisted `AuthorizationRecord` (or a value derived from it) is one side of the
    comparison, that side is always `expected` — the human authorization is the root of trust, so
    it is never the side reported as "found". Where no authorization binding is involved at all
    (e.g. `working_tree_forbidden_paths`, `resume_state_policy`), `expected` carries the required
    invariant and `actual` carries what violated it. The single exception in spirit, not in rule,
    is a *containment* check such as `stage_contract_path` "inside <root>": there the reference is
    the containment requirement and the record-derived path is the value being judged, so the
    record-derived path is correctly `actual`.

    Before GOV-AUTO-07 the two authorization-drift call paths were mutually inverted:
    `_detect_authorization_binding_drift` passed the independently-supplied current value as
    `expected` and the persisted record as `actual`, while `_validate_live_resume_observation` /
    `_live_drift` passed the persisted record as `expected` and the live observation as `actual`.
    `.expected` and `.actual` therefore meant opposite things depending on which safety path
    raised. AUTO-008 could only neutralize the rendered message, because no fixed "bound value X /
    current value Y" wording is correct at both.
    """

    def __init__(self, field: str, expected: str, actual: str) -> None:
        self.field = field
        self.expected = expected
        self.actual = actual
        # The wording stays "expected ... found ..." rather than the "bound value ... current
        # value ..." labelling AUTO-008 removed. With the convention above now uniform, naming the
        # binding explicitly would finally be correct on the bound-vs-current paths -- but not at
        # the raise sites where neither side is a binding ("bound value ()" for
        # `working_tree_forbidden_paths` would be a new falsehood in place of the old one).
        # "expected"/"found" is exact at every site: `expected` is the reference, `actual` is what
        # was found in its place. `field` tells the reader which binding drifted, and callers that
        # need the sides distinguished read `.expected`/`.actual`, which now carry one meaning.
        super().__init__(
            f"Authorization binding drift on {field!r}: expected {expected!r}, found {actual!r}. "
            "Per HUMAN_AUTHORIZATION_MODEL.md §4, this authorization is invalid; the workflow "
            "moves to FAILED and must be re-authorized from CREATED."
        )


class MissingAuthorizationRecordError(AuthorizationError):
    """Raised when a resumable workflow's persisted `AuthorizationRecord` cannot be found.

    Any non-terminal workflow must have passed through `authorize()` to reach `AUTHORIZED` in
    the first place (`CREATED`'s only non-terminal outgoing edge), and `authorize()` always
    persists the complete record before it mutates in-memory state — so a missing file here
    means the persisted evidence trail is incomplete, not merely that authorization is pending.
    """


class CorruptedAuthorizationRecordError(AuthorizationError):
    """Raised when a persisted `AuthorizationRecord` file exists but fails to parse or validate.

    Never silently ignored and never treated as "absent" — a record this module cannot make
    sense of is corruption, not the same as no record ever having been written.
    """


def parse_authorization_record(raw: object) -> AuthorizationRecord:
    """Parse and validate a candidate authorization record from raw (e.g. JSON-decoded) input.

    Raises `AuthorizationRecordError` — never returns a partially-valid record — if `raw` is
    malformed: missing a required field, has the wrong type, carries an unknown field (the
    schema is strict), or fails a field validator (e.g. a non-ISO-8601 timestamp).
    """
    try:
        return AuthorizationRecord.model_validate(raw)
    except ValidationError as exc:
        raise AuthorizationRecordError(f"Malformed authorization record: {exc}") from exc


# The scoped fields checked by `validate_authorization_scope`. Both models use identical
# attribute names for each, so one name list suffices for the paired lookup.
_SCOPE_FIELDS: tuple[str, ...] = (
    "workflow_id",
    "repository_identity",
    "stage_id",
    "planned_stage_branch",
    "baseline_branch",
)


def validate_authorization_scope(
    context: AuthorizationContext, record: AuthorizationRecord | None
) -> None:
    """Raise unless `record` is present and exactly matches `context` on every scoped field.

    `record=None` always raises `MissingAuthorizationError` — absence of an authorization
    record is never interpreted as approval. Every field in `_SCOPE_FIELDS` is compared in a
    fixed order; the first mismatch raises `AuthorizationScopeMismatchError` naming the field
    and both values. Passing (no exception) is the only path that indicates a match.
    """
    if record is None:
        raise MissingAuthorizationError(
            "No authorization record supplied; absence of a record is never interpreted as "
            "approval (HUMAN_AUTHORIZATION_MODEL.md §1: the human gate must be explicit)."
        )
    for field in _SCOPE_FIELDS:
        expected = getattr(context, field)
        actual = getattr(record, field)
        if expected != actual:
            raise AuthorizationScopeMismatchError(field, expected, actual)


_AUTHORIZATION_RECORD_FILENAME = "authorization.json"


class AuthorizationAlreadyPersistedError(AuthorizationError):
    """Raised when persisting an `AuthorizationRecord` would overwrite an already-persisted
    record for the same `workflow_id` whose content differs.

    An authorization record is write-once per workflow: identical repeated writes (the exact
    same content, e.g. a retried `authorize()` call after a transient failure) are a safe,
    silent no-op, but a *different* record for a workflow_id that already has one is always
    rejected — it is never silently replaced, which would destroy evidence of what was actually
    authorized.
    """


class AuthorizationPersistenceStateError(AuthorizationError):
    """Raised when authorization artifacts form an impossible or incomplete combination that
    cannot be safely completed without inventing or overwriting evidence.

    The sole recoverable partial state is one valid, matching `authorization.json` with no
    transition bytes at all: a retry of the exact same authorization completes its missing
    `CREATED -> AUTHORIZED` append while holding the same transaction lock. A transition without
    authorization, malformed/torn history, mismatched authorization, or completed history is
    never adopted as a fresh authorization.
    """


def _authorization_record_path(state_store: StateStore, workflow_id: str) -> Path:
    # Reuses the exact same workflow-ID confinement StateStore itself applies before building a
    # path from a workflow_id (`_safe_workflow_id`) — an unsafe workflow_id (e.g. containing
    # `..` or a path separator) is rejected here before it can ever become a path component, the
    # same way it already is for `transitions.jsonl`/`commands.jsonl`.
    safe_workflow_id = _safe_workflow_id(workflow_id)
    return state_store.state_directory / safe_workflow_id / _AUTHORIZATION_RECORD_FILENAME


def _authorization_lock_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.lock")


def _cleanup_authorization_temp_files(directory_fd: int, path: Path) -> None:
    removed = False
    prefix = f"{path.name}."
    for name in os.listdir(directory_fd):
        if name.startswith(prefix) and name.endswith(".tmp"):
            os.unlink(name, dir_fd=directory_fd)
            removed = True
    if removed:
        os.fsync(directory_fd)


@contextmanager
def _authorization_persistence_lock(
    state_store: StateStore, workflow_id: str
) -> Iterator[tuple[Path, int]]:
    """Hold the never-renamed per-workflow lock across the complete two-artifact transaction."""
    path = _authorization_record_path(state_store, workflow_id)
    with _confined_workflow_directory_fd(
        state_store.state_directory, workflow_id, create=True
    ) as directory_fd:
        if directory_fd is None:  # pragma: no cover - create=True always returns or raises
            raise StateStoreError("Failed to create authorization workflow directory.")
        lock_name = _authorization_lock_path(path).name
        lock_fd = os.open(
            lock_name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
        )
        try:
            _validate_confined_regular_file(lock_fd, display_path=path.with_name(lock_name))
            os.fsync(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            _cleanup_authorization_temp_files(directory_fd, path)
            yield path, directory_fd
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def _read_authorization_record_path(
    path: Path, workflow_id: str, *, directory_fd: int
) -> AuthorizationRecord | None:
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StateStorePathConfinementError(
            f"Refusing to read authorization record {path}: unsafe file component."
        ) from exc
    try:
        _validate_confined_regular_file(fd, display_path=path)
        chunks: list[bytes] = []
        while chunk := os.read(fd, 65536):
            chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8")
    finally:
        os.close(fd)
    if not raw.strip():
        raise CorruptedAuthorizationRecordError(
            f"Persisted authorization record for workflow {workflow_id!r} is empty."
        )
    try:
        payload = _loads_rejecting_duplicate_keys(raw)
        return AuthorizationRecord.model_validate(payload)
    except (_DuplicateJSONKeyError, ValidationError, ValueError) as exc:
        raise CorruptedAuthorizationRecordError(
            f"Persisted authorization record for workflow {workflow_id!r} is corrupted: {exc}"
        ) from exc


def _publish_authorization_record(path: Path, payload: bytes, *, directory_fd: int) -> None:
    """Write, fsync, and publish `payload` without any overwrite-capable operation."""
    tmp_name = f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    fd = os.open(
        tmp_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        # Same-directory hard-link publication is atomic and fails with FileExistsError instead
        # of replacing a winner that appeared after the existing-record check.
        os.link(
            tmp_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(tmp_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.fsync(directory_fd)


def _ensure_authorization_record_locked(
    path: Path, record: AuthorizationRecord, *, directory_fd: int
) -> bool:
    """Ensure `record` exists under the held transaction lock; return whether it was created."""
    existing = _read_authorization_record_path(path, record.workflow_id, directory_fd=directory_fd)
    if existing is not None:
        if existing == record:
            return False
        raise AuthorizationAlreadyPersistedError(
            f"A different authorization record already exists for workflow "
            f"{record.workflow_id!r}; it is never overwritten."
        )
    try:
        _publish_authorization_record(
            path, record.model_dump_json().encode("utf-8"), directory_fd=directory_fd
        )
        return True
    except FileExistsError:
        # A non-cooperating publisher raced the no-replace link. Never overwrite it; inspect the
        # winner and accept only byte-equivalent authorization content.
        existing = _read_authorization_record_path(
            path, record.workflow_id, directory_fd=directory_fd
        )
        if existing == record:
            return False
        raise AuthorizationAlreadyPersistedError(
            f"Authorization publication for workflow {record.workflow_id!r} lost a race to an "
            "existing record; the existing bytes were preserved."
        ) from None


def _persist_authorization_record(state_store: StateStore, record: AuthorizationRecord) -> None:
    """Durably publish one write-once authorization record.

    Identical repeats are byte-preserving no-ops; differing records are rejected. Temporary
    files use `O_EXCL`, are file-fsynced before atomic no-replace publication, and are cleaned on
    every ordinary failure. Directory entries are fsynced after creation, publication, and
    cleanup. `authorize()` uses the wider `_persist_authorization_transaction` below so this same
    lock spans both the authorization record and its transition.
    """
    with _authorization_persistence_lock(state_store, record.workflow_id) as (
        path,
        directory_fd,
    ):
        _ensure_authorization_record_locked(path, record, directory_fd=directory_fd)


def _persist_authorization_transaction(
    state_store: StateStore,
    authorization_record: AuthorizationRecord,
    transition_record: StateTransitionRecord,
) -> None:
    """Persist the authorization/transition pair under one per-workflow transaction lock.

    Detectable phases:

    * neither artifact: publish authorization, then append transition;
    * matching authorization with zero transition records: complete the interrupted append;
    * matching authorization plus the exact transition: completed transaction, reject duplicate;
    * every other combination: reject as corruption/inconsistent persistence.

    The machine is mutated only after this function returns. Therefore an append failure leaves
    the caller in `CREATED`; a crash after a durable append leaves a completed persisted
    authorization that must be resumed, never authorized a second time.
    """
    # Reject obvious reuse/corruption read-only, before creating or opening the transaction lock.
    # The same inspection repeats under the lock when this precheck is empty, closing the race.
    preexisting_transitions = state_store.read_transitions(authorization_record.workflow_id)
    if preexisting_transitions:
        preexisting_authorization = _load_authorization_record(
            state_store, authorization_record.workflow_id
        )
        if preexisting_authorization is None:
            raise AuthorizationPersistenceStateError(
                f"Workflow {authorization_record.workflow_id!r} has transition history but no "
                "authorization record; it cannot be adopted as a fresh authorization."
            )
        if preexisting_authorization != authorization_record:
            raise AuthorizationAlreadyPersistedError(
                f"A different authorization record already exists for workflow "
                f"{authorization_record.workflow_id!r}; it is never overwritten."
            )
        if transition_record in preexisting_transitions:
            raise AuthorizationAlreadyPersistedError(
                f"Workflow {authorization_record.workflow_id!r} already has a completed "
                "authorization transition; authorization is single-use."
            )
        raise AuthorizationPersistenceStateError(
            f"Workflow {authorization_record.workflow_id!r} has persisted history that does not "
            "contain the expected authorization transition; no new transition was appended."
        )

    with _authorization_persistence_lock(state_store, authorization_record.workflow_id) as (
        path,
        directory_fd,
    ):
        existing_authorization = _read_authorization_record_path(
            path, authorization_record.workflow_id, directory_fd=directory_fd
        )
        transitions = state_store.read_transitions(authorization_record.workflow_id)

        if transitions:
            if existing_authorization is None:
                raise AuthorizationPersistenceStateError(
                    f"Workflow {authorization_record.workflow_id!r} has transition history but "
                    "no authorization record; it cannot be adopted as a fresh authorization."
                )
            if existing_authorization != authorization_record:
                raise AuthorizationAlreadyPersistedError(
                    f"A different authorization record already exists for workflow "
                    f"{authorization_record.workflow_id!r}; it is never overwritten."
                )
            if transition_record in transitions:
                raise AuthorizationAlreadyPersistedError(
                    f"Workflow {authorization_record.workflow_id!r} already has a completed "
                    "authorization transition; authorization is single-use."
                )
            raise AuthorizationPersistenceStateError(
                f"Workflow {authorization_record.workflow_id!r} has persisted history that does "
                "not contain the expected authorization transition; no new transition was "
                "appended."
            )

        if existing_authorization is None:
            _ensure_authorization_record_locked(
                path, authorization_record, directory_fd=directory_fd
            )
        elif existing_authorization != authorization_record:
            raise AuthorizationAlreadyPersistedError(
                f"A different authorization record already exists for workflow "
                f"{authorization_record.workflow_id!r}; it is never overwritten."
            )
        # The only existing-artifact case reaching this line is the explicitly recoverable
        # orphan: the exact authorization record exists and transition history is empty.
        state_store.record_transition(transition_record)


def _load_authorization_record(
    state_store: StateStore, workflow_id: str
) -> AuthorizationRecord | None:
    """Load the persisted `AuthorizationRecord` for `workflow_id`, or `None` if none exists.

    Raises `CorruptedAuthorizationRecordError` — never returns a partial or best-effort record —
    if the file exists but fails to parse or validate. Read-only: never mutates or repairs
    whatever is on disk, even when it is corrupt.
    """
    path = _authorization_record_path(state_store, workflow_id)
    with _confined_workflow_directory_fd(
        state_store.state_directory, workflow_id, create=False
    ) as directory_fd:
        if directory_fd is None:
            return None
        return _read_authorization_record_path(path, workflow_id, directory_fd=directory_fd)


def authorize(
    machine: WorkflowStateMachine,
    context: AuthorizationContext,
    record: AuthorizationRecord | None,
    *,
    state_store: StateStore,
) -> AuthorizationRecord:
    """Validate `record` against `context`'s scope, durably persist it, then apply
    `CREATED -> AUTHORIZED`.

    This is the sole path through this module intended to reach `AUTHORIZED` from a *fresh*
    authorization (HUMAN_AUTHORIZATION_MODEL.md §1: "the only human gate");
    `WorkflowStateMachine.transition_to` and `_apply_transition` both reject `AUTHORIZED`
    unconditionally, for every caller, and no other method on the machine applies it either —
    this function reaches it only by validating `record` against `context` right here, then
    persisting both authorization artifacts and invoking the closure-owned committer, which
    independently validates those persisted artifacts before mutating authoritative state. The
    only other legitimate path is the replay section's `_apply_validated_authorization`, which
    invokes the same evidence-validating committer against persisted history.

    `state_store` is required, not optional — an authorization that is never durably persisted
    is not a real authorization; requirement: "authorization must require a state store; absence
    of persistence must fail before mutation." A caller with no store has no legitimate way to
    call this function at all (a missing argument fails before any of this function's own logic
    runs, let alone before any mutation).

    On any validation failure (`MissingAuthorizationError` or
    `AuthorizationScopeMismatchError`), `machine.state` is left completely unchanged — the same
    validate-before-mutate guarantee `WorkflowStateMachine.transition_to` itself provides, now
    extended to cover the authorization check that precedes it.

    `validate_transition(machine.state, AUTHORIZED)` runs *first*, before
    `validate_authorization_scope` and before `_persist_authorization_transaction` — not merely
    applied afterward as a final gate before mutation. If `machine` is not currently in `CREATED`
    (e.g. re-running `authorize()` a second time against an already-`AUTHORIZED` machine),
    `InvalidTransitionError` is raised before persistence is entered. A fresh reconstructed
    machine cannot evade single-use semantics: the transaction independently rejects an existing
    completed authorization pair before appending anything. Both rejection paths leave every
    existing persisted byte untouched.

    Persistence happens *before* the in-memory transition is applied. The complete
    `AuthorizationRecord` and audited `StateTransitionRecord` are handled by one per-workflow
    transaction lock. A matching authorization with zero transitions is the sole recoverable
    interrupted phase; a complete pair is single-use and rejects a second authorization. If
    persistence raises, `machine.state` remains `CREATED`. If a crash occurs after the transition
    is durable but before memory mutation, restart must resume that completed persisted workflow,
    never append a duplicate authorization edge.
    """
    validate_transition(machine.state, WorkflowState.AUTHORIZED)
    validate_authorization_scope(context, record)
    assert record is not None  # validate_authorization_scope raises above otherwise
    transition_record = StateTransitionRecord(
        workflow_id=context.workflow_id,
        target_repository=context.repository_identity,
        repository_path=str(Path(record.repository_path).resolve()),
        stage_id=context.stage_id,
        from_state=WorkflowState.CREATED.value,
        to_state=WorkflowState.AUTHORIZED.value,
        timestamp=record.authorized_at,
        actor="human",
        gate_evidence_ref=None,
    )
    _persist_authorization_transaction(state_store, record, transition_record)
    _commit_validated_authorized_machine_state(machine, transition_record, state_store)
    return record


# --------------------------------------------------------------------------------------------
# Resume and recovery (WORKFLOW_STATES.md §6).
#
# On restart, the Orchestrator "loads the persisted state for the target repository's active
# workflow" (§6 item 1) and "resumes... as if no interruption had occurred" (§6 item 4) only if
# preconditions still hold. This module implements the loading, validation, and replay of that
# persisted history — never the live-repository precondition re-verification itself (§6 item 2;
# `MACHINE_GATES.md` §2), which remains a separate, later concern.
# --------------------------------------------------------------------------------------------


class ResumeError(Exception):
    """Base error for resume/recovery failures. A rejected resume never mutates anything: no
    persisted record is altered, and the repository lock (if briefly acquired) is always
    released before the error propagates.
    """


class MissingPersistedStateError(ResumeError):
    """Raised when no persisted transition history exists for the requested workflow.

    A workflow with zero persisted transitions was never authorized (Step 5B's `authorize()` is
    the only path that writes the first record) — there is nothing to resume.
    """


class CorruptedHistoryError(ResumeError):
    """Raised when persisted history cannot be parsed or fails schema validation.

    Wraps `StateStoreCorruptionError` from the already-implemented `StateStore` — this module
    adds no parsing of its own and never attempts to repair or skip the corrupt record.
    """


class InconsistentHistoryError(ResumeError):
    """Raised when persisted history is internally inconsistent, or reconstructing it would
    require a transition absent from `ALLOWED_TRANSITIONS`.

    Covers: a record whose own `workflow_id` disagrees with the file it was read from; history
    that does not begin at `CREATED`; a gap where one record's `from_state` does not match the
    previous record's `to_state`; more than one target repository or stage id referenced across
    the same workflow's history; a terminal state reached more than once, or followed by any
    further transition; and any individual recorded transition that
    `WorkflowStateMachine.transition_to` itself rejects. Resume never invents a missing
    transition to bridge a gap, and never silently drops or repairs an inconsistent record — it
    always refuses instead.
    """


class WorkflowAlreadyTerminalError(ResumeError):
    """Raised when the reconstructed workflow is already in `DONE`, `FAILED`, or `CANCELLED`.

    Terminal states have no outgoing transitions (§8); there is nothing to resume.
    """


class RepositoryLockUnavailableError(ResumeError):
    """Raised when the repository lock cannot be acquired before exposing a resumable workflow.

    Wraps `LockContentionError` from the already-implemented `RepositoryLock` — this module adds
    no new locking mechanism, only a required acquisition step before resume can succeed.
    """


class RepositoryLockIdentityMismatchError(ResumeError):
    """Raised when the acquired lock's own bound identity (`RepositoryLock`'s
    `workflow_id`/`repository_identity`, read back via `read_metadata()` immediately after
    acquisition) does not match the workflow/repository resume was requested for.

    A `RepositoryLock` instance is constructed by the caller, ahead of time, bound to whatever
    identity the caller supplied at construction — nothing about `resume_workflow` otherwise
    verifies that the *specific lock object* passed in actually belongs to the repository being
    resumed. Without this check, a caller could accidentally (or a compromised caller could
    deliberately) pass a lock constructed for a *different* repository, defeating the mutual
    exclusion the lock exists to provide.
    """


class ResumeReconciliationRequiredError(ResumeError):
    """Live state is a contract-defined uncertain side-effect boundary, not proven drift.

    No transition is appended: the workflow remains in its persisted state until the applicable
    reconciliation entry point records authoritative evidence.
    """

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail
        super().__init__(f"Resume reconciliation required for {field!r}: {detail}")


@dataclass(frozen=True)
class ResumedWorkflow:
    """A successfully resumed workflow: a replayed, validated `WorkflowStateMachine`, the full
    persisted history that produced it, the `StateStore` to durably append further transitions
    to, and the `RepositoryLock` acquired to expose it.

    The lock is returned still held — resuming callers are expected to continue operating on the
    workflow under its exclusion, then call `.lock.release()` themselves when finished (not
    `.lock.acquire()`/context-manager entry again, which would raise `LockStateError` since this
    lock is already held by this same instance). For a caller that wants the lock's release
    *guaranteed* regardless of how it stops operating on the workflow — including an unhandled
    exception in its own code — `ResumedWorkflow` is also usable as a context manager:
    `with resume_workflow(...) as resumed:` always releases `resumed.lock` on exit, exception or
    not (ARCHITECTURE.md §5 / stage contract requirement 9: "exception exits must always release
    the repository lock").

    `.transition_to(...)` is the sole sanctioned runtime path for advancing the workflow beyond
    its current state: it validates, durably persists, and only then applies the transition, and
    automatically releases `.lock` on reaching a terminal state — closing the gap where in-memory
    transition and durable append were separable operations a caller could apply out of step with
    each other. `.machine.transition_to(...)` remains directly reachable (this module does not
    forbid it — WorkflowStateMachine has no notion of "who owns the durable record for this
    machine" to check against, unlike the single, structurally-enforceable `AUTHORIZED` gate);
    this class's own `.transition_to(...)` is the answer to "how does a caller who wants durable,
    lock-enforced runtime behavior get it," not a lockdown of the lower-level primitive.
    """

    machine: WorkflowStateMachine
    transitions: list[StateTransitionRecord]
    lock: RepositoryLock
    state_store: StateStore
    repository_path: str

    def __enter__(self) -> "ResumedWorkflow":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.lock.release()

    def release_lock_if_terminal(self) -> bool:
        """Release `self.lock` if and only if `self.machine` has reached a terminal state
        (`DONE`, `FAILED`, `CANCELLED`) — ARCHITECTURE.md §5: the lock is released "only when a
        workflow reaches DONE, FAILED, or CANCELLED." A no-op (returns `False`) while the
        workflow is still in progress, so an in-flight workflow's exclusivity is never
        accidentally given up. Idempotent — safe to call more than once (`RepositoryLock.release`
        already tolerates a release when nothing is held).
        """
        if not self.machine.is_terminal:
            return False
        self.lock.release()
        return True

    def transition_to(
        self,
        to_state: WorkflowState,
        *,
        actor: str,
        gate_evidence_ref: str | None = None,
    ) -> WorkflowState:
        """Validate, durably persist, then apply `to_state` — never the reverse order.

        Requirement: "the runtime orchestration API must validate and durably append a
        transition before exposing the new state." `self.machine.state` is read *before* any
        persistence is attempted; if `validate_transition` rejects the edge, or if
        `self.state_store.record_transition` raises (disk full, permission error, etc.),
        `self.machine.state` is left completely unchanged — a caller can retry or fail closed
        without ever observing a state that was never durably recorded. Only after persistence
        succeeds is `self.machine.transition_to` called to apply the same, already-validated
        edge in memory (its own transition-table check is inherently redundant here, but doing
        the validation twice is cheap and this method still runs entirely through the machine's
        own real validation path rather than mutating `._state` directly).

        `actor` has no default: `AUDIT_MODEL.md`'s three legal values carry different meaning
        (`"human"` is reserved for authorization/cancellation) and this method applies to any
        edge, so the caller must state which kind of actor is driving this specific transition
        rather than have one silently assumed for all of them.

        On reaching a terminal state (`DONE`, `FAILED`, `CANCELLED`), `self.lock` is released
        automatically (`self.release_lock_if_terminal()`) — a caller advancing a workflow to
        completion through this method can never forget the manual release step. A non-terminal
        `to_state` leaves the lock held, unchanged.

        AUTO002-F10: `to_state is AUTHORIZED` is rejected here, before `from_state` is even read
        — never merely left to `self.machine.transition_to`'s own rejection at the very end of
        this method. `(CREATED, AUTHORIZED)` is a legal edge in `ALLOWED_TRANSITIONS`, so
        `validate_transition`/`validate_actor_for_transition` below would both pass for a
        `ResumedWorkflow` whose `.machine` happens to be a caller-supplied, never-actually-
        replayed `WorkflowStateMachine()` still at `CREATED` (this dataclass has no construction
        guard — its own docstring says so — so nothing prevents a caller from building one
        directly, bypassing `resume_workflow()`'s replay, evidence, and reuse checks entirely).
        Without this guard, `self.state_store.record_transition(new_record)` a few lines below
        would durably append a fabricated `CREATED -> AUTHORIZED` record with no
        `AuthorizationRecord` ever validated — the caller would still see `AuthorizationBypassError`
        (raised later by `self.machine.transition_to`), but only *after* the corrupting write
        already landed, defeating `WorkflowIdReuseError`'s single-use invariant at a layer no
        `WorkflowSession`-facade check ever runs at.
        """
        if to_state is WorkflowState.AUTHORIZED:
            raise AuthorizationBypassError(
                "transition_to(AUTHORIZED) is never permitted through ResumedWorkflow, before "
                "any persistence is attempted: call authorize() instead "
                "(HUMAN_AUTHORIZATION_MODEL.md §1: 'the only human gate')."
            )
        from_state = self.machine.state
        validate_transition(from_state, to_state)
        validate_actor_for_transition(from_state, to_state, actor)
        representative = self.transitions[-1]
        new_record = StateTransitionRecord(
            workflow_id=representative.workflow_id,
            target_repository=representative.target_repository,
            repository_path=self.repository_path,
            stage_id=representative.stage_id,
            from_state=from_state.value,
            to_state=to_state.value,
            timestamp=datetime.now(UTC).isoformat(),
            actor=actor,
            gate_evidence_ref=gate_evidence_ref,
        )
        self.state_store.record_transition(new_record)
        new_state = self.machine.transition_to(to_state)
        # self.transitions is a plain list, not frozen by @dataclass(frozen=True) (only
        # attribute *reassignment* is blocked) — kept in sync so a caller reading
        # .transitions after a successful transition_to() sees the complete, current history,
        # not a stale snapshot from whenever resume_workflow() first replayed it.
        self.transitions.append(new_record)
        self.release_lock_if_terminal()
        return new_state


_TERMINAL_STATE_VALUES: frozenset[str] = frozenset(state.value for state in TERMINAL_STATES)


def _validate_history_consistency(workflow_id: str, records: list[StateTransitionRecord]) -> None:
    """Raise `InconsistentHistoryError` unless `records` forms one unbroken, single-workflow,
    single-repository, single-stage chain starting at `CREATED` with at most one terminal
    transition, which if present is the last record. Never repairs or reorders `records`.
    """
    for record in records:
        if record.workflow_id != workflow_id:
            raise InconsistentHistoryError(
                f"Persisted record claims workflow_id {record.workflow_id!r}, but was read as "
                f"part of workflow {workflow_id!r}'s history."
            )

    first = records[0]
    if first.from_state != WorkflowState.CREATED.value:
        raise InconsistentHistoryError(
            f"Persisted history for {workflow_id!r} does not begin at CREATED "
            f"(first recorded from_state: {first.from_state!r})."
        )

    repository_identities = {record.target_repository for record in records}
    if len(repository_identities) > 1:
        raise InconsistentHistoryError(
            f"Persisted history for {workflow_id!r} references multiple target repositories: "
            f"{sorted(repository_identities)!r}."
        )

    repository_paths = {record.repository_path for record in records}
    if len(repository_paths) > 1:
        raise InconsistentHistoryError(
            f"Persisted history for {workflow_id!r} references multiple repository paths: "
            f"{sorted(repository_paths)!r}."
        )

    stage_ids = {record.stage_id for record in records}
    if len(stage_ids) > 1:
        raise InconsistentHistoryError(
            f"Persisted history for {workflow_id!r} references multiple stage ids: "
            f"{sorted(stage_ids)!r}."
        )

    for previous, current in pairwise(records):
        if current.from_state != previous.to_state:
            raise InconsistentHistoryError(
                f"Persisted history for {workflow_id!r} has a gap: a transition recorded as "
                f"starting from {current.from_state!r} does not follow the prior transition's "
                f"end state {previous.to_state!r}."
            )

    terminal_positions = [
        index for index, record in enumerate(records) if record.to_state in _TERMINAL_STATE_VALUES
    ]
    if len(terminal_positions) > 1:
        raise InconsistentHistoryError(
            f"Persisted history for {workflow_id!r} reaches a terminal state more than once."
        )
    if terminal_positions and terminal_positions[0] != len(records) - 1:
        raise InconsistentHistoryError(
            f"Persisted history for {workflow_id!r} contains a transition after a terminal "
            "state; terminal states have no outgoing transitions (WORKFLOW_STATES.md §8)."
        )


def _validate_persisted_authorization_evidence(
    machine: WorkflowStateMachine, *, record: StateTransitionRecord, state_store: StateStore
) -> None:
    """Validate the one `CREATED -> AUTHORIZED` step encountered in persisted history.

    This validation backs both fresh authorization's final in-memory commit and replay. The
    closure-owned authoritative-state committer always invokes it immediately before writing
    `AUTHORIZED`; no raw authorized-state setter exists.

    This is the *only* replay validation path this module has: there is no second, weaker helper
    anywhere
    that skips this check (a prior version of this fix had one, `_replay_history_state_only`,
    used by the retry/reconciliation section without any authorization-evidence check at all —
    removed; see `_replay_history` below, now the sole reconstruction primitive for every caller).

    Never trusts the `StateTransitionRecord` being replayed to prove authorization by itself: a
    `StateTransitionRecord` is only a `workflow_id`/`target_repository`/`stage_id`/`from_state`/
    `to_state`/`timestamp`/`actor` tuple, trivially constructed by any caller holding the
    `StateTransitionRecord` class — exactly what the reported bypass did. Instead, this function:

    1. Confirms `record.from_state == "CREATED"` and `record.actor == "human"` — the required
       shape of the one legitimate `CREATED -> AUTHORIZED` edge (`AUDIT_MODEL.md` §3: `actor` is
       `"human"` for authorization/cancellation only; `WORKFLOW_STATES.md` §3: "human action").
    2. Independently loads the persisted `AuthorizationRecord` for `record.workflow_id` from
       `state_store` itself — `state_store` is a required keyword-only parameter with no default,
       so a caller holding only an in-memory records list and no real `StateStore` cannot reach
       this code path — and requires that a record actually exists there and parses
       (`MissingAuthorizationRecordError` / `CorruptedAuthorizationRecordError`, both raised by
       `_load_authorization_record` itself).
    2a. Independently re-reads `state_store.read_transitions(record.workflow_id)` and requires
        this exact transition to be a member of that persisted history. Every load-bearing field
        must match, with only `repository_path` compared canonically so a symlink alias of the
        same repository remains equivalent under the repository-path binding contract. A
        different persisted authorization edge is never evidence that this caller-supplied edge
        was persisted.
    3. Validates the loaded record's `workflow_id`, `repository_identity`, `repository_path`, and
       `stage_id` against the *replayed history's own* `record.workflow_id` /
       `record.target_repository` / `record.repository_path` / `record.stage_id` — every identity
       and path field a `StateTransitionRecord` carries (`AUDIT_MODEL.md` §3). An authorization
       record that exists and parses but was persisted for a *different* workflow, repository, path,
       or stage is rejected exactly the same as a missing one: presence at a filesystem location
       keyed by `workflow_id` is not, by itself, proof the record actually belongs there.

       `repository_path` is compared canonically (`Path.resolve()` on both sides), not as raw
       strings: `record.repository_path` is always already resolved by the code path that writes
       it (`authorize()` persists `str(Path(record.repository_path).resolve())` for the paired
       transition it appends — `record` here refers to the `AuthorizationRecord` passed into
       `authorize()`, unresolved, whose raw path becomes `authorization_record.repository_path`
       below), so resolving `authorization_record.repository_path` a second time collapses any
       symlink alias between the two without ever weakening the check for a *genuinely* different
       path. This closes the gap where a transition history could consistently claim one
       repository path throughout (satisfying `_validate_history_consistency`'s single-path
       uniformity check) while the persisted `AuthorizationRecord` — the actual evidence of what a
       human authorized — names a different one entirely: every replayed transition is bound to
       the *same* canonical path the authorization itself is bound to, not merely internally
       consistent with the other transitions sitting next to it in the same file. This check runs
       once, here, for the sole `CREATED -> AUTHORIZED` record every persisted history contains
       (`_validate_history_consistency` already guarantees every other record shares that same
       `repository_path` before replay ever reaches this function), so it transitively binds the
       *entire* replayed history, not just this one record. It is not redundant with
       `resume_workflow`'s own `_detect_authorization_binding_drift`
       (`current_binding.repository_path`): that check instead binds the persisted
       `AuthorizationRecord` to the caller's independently-supplied *current, live* value (plus the
       fuller `HUMAN_AUTHORIZATION_MODEL.md` §2 binding set this function has no way to validate on
       its own — contract hash, baseline SHA, engine version), and only `resume_workflow` performs
       it; this step instead guards every caller of `_replay_history` (including retry/
       reconciliation, which never even has a `current_binding` to check against) against the
       persisted *history* itself disagreeing with the persisted *authorization*.

    Raises `AuthorizationBindingDriftError` — the same type `resume_workflow`'s own drift
    detection already uses — on any mismatch found in steps 1 or 3, so a caller layered on top of
    `_replay_history` (like `resume_workflow`) can uniformly treat "the persisted record doesn't
    match the persisted history" as the drift condition it already is, without a second, redundant
    error type for the same underlying problem. The transition-table check runs *first*, before
    any disk access, so an out-of-place `AUTHORIZED` target (which cannot legally occur except
    immediately after `CREATED`) still raises the ordinary `InvalidTransitionError` any other
    illegal edge would. Never appends a transition or mutates `machine` on any rejection — the
    caller (`_replay_history`, and transitively `resume_workflow`) never advances past this point
    when this function raises, so a resume rejected here never returns a resumable session.
    """
    validate_transition(machine.state, WorkflowState.AUTHORIZED)
    if record.from_state != WorkflowState.CREATED.value:
        raise AuthorizationBindingDriftError(
            "from_state", WorkflowState.CREATED.value, record.from_state
        )
    if record.to_state != WorkflowState.AUTHORIZED.value:
        raise AuthorizationBindingDriftError(
            "to_state", WorkflowState.AUTHORIZED.value, record.to_state
        )
    if record.actor != "human":
        raise AuthorizationBindingDriftError("actor", "human", record.actor)
    authorization_record = _load_authorization_record(state_store, record.workflow_id)
    if authorization_record is None:
        raise MissingAuthorizationRecordError(
            f"No persisted authorization record found for workflow {record.workflow_id!r}; "
            "replaying a CREATED -> AUTHORIZED transition requires one to actually exist on "
            "disk — an in-memory StateTransitionRecord alone is never sufficient "
            "(HUMAN_AUTHORIZATION_MODEL.md §1)."
        )
    persisted_transitions = state_store.read_transitions(record.workflow_id)
    if not any(
        _replay_record_comparison_key(persisted) == _replay_record_comparison_key(record)
        for persisted in persisted_transitions
    ):
        raise AuthorizationBindingDriftError(
            "transition_history",
            "the exact CREATED -> AUTHORIZED transition durably recorded in the state store",
            (
                "no transitions found in persisted history"
                if not persisted_transitions
                else "the supplied authorization transition is not an exact persisted member"
            ),
        )
    # The four checks below compare the persisted `AuthorizationRecord` against the transition
    # record being replayed. The authorization is the root of trust here — the whole point of this
    # step is that a transition history must be bound to what the human actually authorized, not
    # merely internally consistent — so the authorization record is `expected` and the transition
    # record is the value under judgement (GOV-AUTO-07). The three checks above have no
    # authorization record on either side; there the required constant is `expected`.
    if authorization_record.workflow_id != record.workflow_id:
        raise AuthorizationBindingDriftError(
            "workflow_id", authorization_record.workflow_id, record.workflow_id
        )
    if authorization_record.repository_identity != record.target_repository:
        raise AuthorizationBindingDriftError(
            "repository_identity",
            authorization_record.repository_identity,
            record.target_repository,
        )
    if (
        Path(authorization_record.repository_path).resolve()
        != Path(record.repository_path).resolve()
    ):
        raise AuthorizationBindingDriftError(
            "repository_path", authorization_record.repository_path, record.repository_path
        )
    if authorization_record.stage_id != record.stage_id:
        raise AuthorizationBindingDriftError(
            "stage_id", authorization_record.stage_id, record.stage_id
        )


def _apply_validated_authorization(
    machine: WorkflowStateMachine, *, record: StateTransitionRecord, state_store: StateStore
) -> None:
    """Apply authorization only through the evidence-validating closure-owned committer."""
    _commit_validated_authorized_machine_state(machine, record, state_store)


def _replay_record_comparison_key(
    record: StateTransitionRecord,
) -> tuple[str, str, str, str, str, str, str, str, str | None]:
    """Return every load-bearing transition field in persisted order-comparison form.

    Repository paths are canonicalized because the existing binding contract treats symlink
    aliases of the same physical repository as equal. No other field is normalized.
    """
    return (
        record.workflow_id,
        record.target_repository,
        str(Path(record.repository_path).resolve()),
        record.stage_id,
        record.from_state,
        record.to_state,
        record.actor,
        record.timestamp,
        record.gate_evidence_ref,
    )


def _require_exact_persisted_history(
    supplied_records: list[StateTransitionRecord],
    persisted_records: list[StateTransitionRecord],
) -> None:
    supplied_keys = [_replay_record_comparison_key(record) for record in supplied_records]
    persisted_keys = [_replay_record_comparison_key(record) for record in persisted_records]
    if supplied_keys != persisted_keys:
        raise AuthorizationBindingDriftError(
            "transition_history",
            f"exact persisted sequence of {len(persisted_records)} transition record(s)",
            f"non-matching supplied sequence of {len(supplied_records)} transition record(s)",
        )


def _replay_history(
    records: list[StateTransitionRecord],
    *,
    state_store: StateStore,
    workflow_id: str,
) -> WorkflowStateMachine:
    """Reconstruct from an independently loaded, validated persisted history.

    `records` remains only as a compatibility/integrity assertion: before a machine is
    constructed, this function independently loads the complete history for `workflow_id` from
    `state_store`, validates it, and requires exact field/order/length equality. It then replays
    only the independently loaded objects. A caller-supplied record is never authoritative.

    `workflow_id` is mandatory and never inferred from caller records, so history from another
    workflow cannot choose which persisted sequence is treated as authoritative.
    """
    try:
        persisted_records = _load_and_validate_history(workflow_id, state_store)
    except MissingPersistedStateError as exc:
        raise AuthorizationBindingDriftError(
            "transition_history",
            f"persisted transition history for workflow {workflow_id!r}",
            "no persisted transition history",
        ) from exc
    _require_exact_persisted_history(records, persisted_records)

    # Construction deliberately occurs only after persisted loading, validation, and exact
    # comparison all succeed. No rejected caller can retain a partially replayed machine.
    machine = WorkflowStateMachine()
    for record in persisted_records:
        try:
            to_state = WorkflowState(record.to_state)
        except ValueError as exc:
            raise InconsistentHistoryError(
                f"Persisted transition targets an unrecognized state: {record.to_state!r}."
            ) from exc
        if to_state is WorkflowState.AUTHORIZED:
            try:
                _apply_validated_authorization(machine, record=record, state_store=state_store)
            except InvalidTransitionError as exc:
                raise InconsistentHistoryError(
                    f"Persisted transition {record.from_state} -> {record.to_state} is not a "
                    "legal edge in WORKFLOW_STATES.md §3."
                ) from exc
            continue
        from_state = machine.state
        try:
            validate_actor_for_transition(from_state, to_state, record.actor)
        except InvalidActorForTransitionError as exc:
            raise InconsistentHistoryError(
                f"Persisted transition {record.from_state} -> {record.to_state} records actor "
                f"{record.actor!r}, which is not permitted for that edge (AUDIT_MODEL.md §3)."
            ) from exc
        try:
            machine._apply_transition(to_state)
        except InvalidTransitionError as exc:
            raise InconsistentHistoryError(
                f"Persisted transition {record.from_state} -> {record.to_state} is not a legal "
                "edge in WORKFLOW_STATES.md §3."
            ) from exc
    return machine


def _load_and_validate_history(
    workflow_id: str, state_store: StateStore
) -> list[StateTransitionRecord]:
    try:
        records = state_store.read_transitions(workflow_id)
    except StateStoreCorruptionError as exc:
        raise CorruptedHistoryError(
            f"Persisted history for workflow {workflow_id!r} is corrupted: {exc}"
        ) from exc
    if not records:
        raise MissingPersistedStateError(
            f"No persisted state found for workflow {workflow_id!r}; it was never authorized."
        )
    _validate_history_consistency(workflow_id, records)
    return records


def _check_identity_matches_context(
    context: AuthorizationContext, records: list[StateTransitionRecord]
) -> None:
    """Raise `AuthorizationScopeMismatchError` (the same type `authorize()` uses) unless the
    persisted history's identity fields agree with `context`.

    Checks `repository_identity` and `stage_id` — the identity fields `StateTransitionRecord`
    (`AUDIT_MODEL.md` §3) carries beyond `workflow_id`. `workflow_id` itself is never checked
    here because it cannot mismatch by the time this function runs: `records` was loaded using
    `context.workflow_id` as the lookup key (`_load_and_validate_history`), and
    `_validate_history_consistency` has already confirmed every record's own `workflow_id` field
    agrees with that same key — a caller-supplied `context.workflow_id` that doesn't match any
    persisted history instead raises `MissingPersistedStateError` before reaching this point.

    `context.planned_stage_branch` and `context.baseline_branch` are not checked against
    `records` here — `StateTransitionRecord` (`AUDIT_MODEL.md` §3) does not even carry those
    fields. They, and every other `HUMAN_AUTHORIZATION_MODEL.md` §2 binding, are independently
    validated against the persisted `AuthorizationRecord` itself by
    `_detect_authorization_binding_drift`, later in `resume_workflow`. The same
    `AuthorizationContext` type from Step 5B is reused unchanged rather than a resume-specific
    alternative, so a resuming caller supplies exactly the identity it originally authorized
    against.
    """
    representative = records[-1]
    if representative.target_repository != context.repository_identity:
        raise AuthorizationScopeMismatchError(
            "repository_identity",
            context.repository_identity,
            representative.target_repository,
        )
    if representative.stage_id != context.stage_id:
        raise AuthorizationScopeMismatchError("stage_id", context.stage_id, representative.stage_id)


# The complete set of HUMAN_AUTHORIZATION_MODEL.md §2 bindings that have a live "current" value
# to drift-check against, in §2's own numbered order. `workflow_id` is included even though §2
# does not number it separately, for the same disk-tampering defense-in-depth reason
# `_validate_history_consistency` checks it for `StateTransitionRecord`: `AuthorizationRecord` is
# loaded by path (keyed on `context.workflow_id`), and nothing else would catch a persisted
# record whose own `workflow_id` field disagrees with the file it was found in. Authorization
# timestamp (item 9) and authorizing human identity (item 10) are intentionally absent — see
# `CurrentAuthorizationBinding`'s docstring for why.
_BINDING_DRIFT_FIELDS: tuple[str, ...] = (
    "workflow_id",
    "repository_identity",
    "repository_path",
    "stage_id",
    "stage_contract_path",
    "stage_contract_hash",
    "baseline_branch",
    "baseline_commit_sha",
    "planned_stage_branch",
    "engine_version",
)


def _detect_authorization_binding_drift(
    context: AuthorizationContext,
    current_binding: CurrentAuthorizationBinding,
    record: AuthorizationRecord,
) -> None:
    """Raise `AuthorizationBindingDriftError` on the first field, in `_BINDING_DRIFT_FIELDS`
    order, whose independently-supplied current value no longer matches `record`'s bound value.

    `workflow_id`, `repository_identity`, `stage_id`, `baseline_branch`, and
    `planned_stage_branch` are sourced from `context` (mirroring `validate_authorization_scope`'s
    own fields, now applied to resume with drift-appropriate consequences instead of a bare
    scope-mismatch rejection); `repository_path`, `stage_contract_path`, `stage_contract_hash`,
    `baseline_commit_sha`, and `engine_version` — the fields `AuthorizationContext` does not
    carry — are sourced from `current_binding`. Every comparison value comes from one of those
    two independently-constructed inputs, never from `record` itself, so this can never validate
    a persisted field by comparing it to a copy of that same persisted field.

    Engine-version policy (`HUMAN_AUTHORIZATION_MODEL.md` §4: "when that mismatch is judged
    relevant (exact policy: AUTO-002)"): this implementation treats *any* string inequality as
    relevant drift, matching the fail-closed default every other binding in this function already
    uses, since no compatibility/semver-range policy is defined anywhere in this document set. A
    looser policy (e.g. treating a patch-version bump as non-drifting) is undefined and would be
    a new Human Owner-approved policy, not something this fix invents.

    Argument convention (GOV-AUTO-07): the bound value from `record` is reported as `expected` and
    the independently-supplied current value as `actual`, per
    `AuthorizationBindingDriftError`'s documented convention. This is the inversion F-1 named: this
    function previously passed the current value as `expected` and the persisted record as
    `actual`, the opposite of what `_validate_live_resume_observation` did, so a reader was told
    the live value was the bound one and the drifted record was what had been found. Only the
    reported sides changed; the comparison itself is symmetric, so which fields drift and in what
    order is unaffected.
    """
    current_values: dict[str, str] = {
        "workflow_id": context.workflow_id,
        "repository_identity": context.repository_identity,
        "repository_path": current_binding.repository_path,
        "stage_id": context.stage_id,
        "stage_contract_path": current_binding.stage_contract_path,
        "stage_contract_hash": current_binding.stage_contract_hash,
        "baseline_branch": context.baseline_branch,
        "baseline_commit_sha": current_binding.baseline_commit_sha,
        "planned_stage_branch": context.planned_stage_branch,
        "engine_version": current_binding.engine_version,
    }
    for field in _BINDING_DRIFT_FIELDS:
        bound = str(getattr(record, field))
        current = current_values[field]
        if bound != current:
            raise AuthorizationBindingDriftError(field, bound, current)


@dataclass(frozen=True)
class _WorktreeClassification:
    control_paths: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    unexpected_paths: tuple[str, ...]

    @property
    def application_paths(self) -> tuple[str, ...]:
        return self.allowed_paths + self.forbidden_paths + self.unexpected_paths


def _matches_any(path: str, patterns: list[str]) -> bool:
    """`path` must already be canonical (`canonical_repository_relative_path`); configured
    patterns are canonical by construction (schema strict rejection, AUTO002-IR-03), so both
    sides of every comparison are in one deterministic representation.
    """
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _configured_control_prefixes(config: WorkflowConfig) -> tuple[str, ...]:
    repository = config.repository_path.resolve()
    prefixes = [".agentos/workflow.lock", ".agentos/workflow.yaml"]
    for root in (config.state_directory.resolve(), config.audit_directory.resolve()):
        if root.is_relative_to(repository):
            prefixes.append(root.relative_to(repository).as_posix().rstrip("/") + "/")
    return tuple(prefixes)


def _classify_worktree(
    observation: ResumeObservation, config: WorkflowConfig
) -> _WorktreeClassification:
    control_prefixes = _configured_control_prefixes(config)
    control: set[str] = set()
    allowed: set[str] = set()
    forbidden: set[str] = set()
    unexpected: set[str] = set()
    for change in observation.worktree_changes:
        paths = (
            (change.path,) if change.original_path is None else (change.path, change.original_path)
        )
        for path in paths:
            # Authorization decisions are made on the canonical representation (AUTO002-IR-03) so
            # that no spelling difference between an observed path and a configured pattern can
            # make a forbidden rule silently inert; the *reported* path stays exactly as observed.
            match_path = canonical_repository_relative_path(path)
            is_control = any(
                match_path == prefix or (prefix.endswith("/") and match_path.startswith(prefix))
                for prefix in control_prefixes
            )
            if is_control:
                control.add(path)
            elif _matches_any(match_path, config.forbidden_changed_paths):
                forbidden.add(path)
            elif _matches_any(match_path, config.allowed_changed_paths):
                allowed.add(path)
            else:
                unexpected.add(path)
    return _WorktreeClassification(
        tuple(sorted(control)),
        tuple(sorted(allowed)),
        tuple(sorted(forbidden)),
        tuple(sorted(unexpected)),
    )


def _live_drift(field: str, expected: object, actual: object) -> None:
    """Raise binding drift from the live-observation path.

    `expected` is the reference (the value `record` binds, or the invariant this check requires)
    and `actual` is the live/current value judged against it — `AuthorizationBindingDriftError`'s
    convention, which every call below follows (GOV-AUTO-07).
    """
    raise AuthorizationBindingDriftError(field, str(expected), str(actual))


def _validate_live_resume_observation(
    *,
    context: AuthorizationContext,
    record: AuthorizationRecord,
    machine: WorkflowStateMachine,
    observation: ResumeObservation,
    config: WorkflowConfig,
    state_store: StateStore,
) -> None:
    """Apply DD-14/WORKFLOW_STATES §6a to independently observed raw facts."""

    expected_repository = config.repository_path.resolve()
    if observation.canonical_repository_path != str(expected_repository):
        _live_drift(
            "repository_path", str(expected_repository), observation.canonical_repository_path
        )
    if Path(record.repository_path).resolve() != expected_repository:
        # Bound record vs. the current run's configured repository: the binding is the reference,
        # so it is `expected` and the configured path is what was found (GOV-AUTO-07). The check
        # immediately above has no binding on either side, so there the configured path is itself
        # the reference and the live observation is what was found.
        _live_drift("repository_path", record.repository_path, str(expected_repository))
    if not observation.repository_exists:
        _live_drift("repository_exists", True, False)
    if not observation.is_git_repository:
        _live_drift("git_repository", True, False)
    if observation.observed_repository_identity is None:
        _live_drift("repository_identity", record.repository_identity, None)
    observed_identity = canonical_repository_identity(
        observation.observed_repository_identity or ""
    )
    configured_identity = canonical_repository_identity(config.repository_identity)
    bound_identity = canonical_repository_identity(record.repository_identity)
    if configured_identity != bound_identity:
        # Both of these compare against the binding, so the binding is `expected` in both
        # (GOV-AUTO-07). Before that, these two adjacent raises on the same field put the bound
        # identity on opposite sides of each other.
        _live_drift("repository_identity", bound_identity, configured_identity)
    if observed_identity != bound_identity:
        _live_drift("repository_identity", bound_identity, observed_identity)

    expected_contract = (expected_repository / record.stage_contract_path).resolve()
    contract_root = (expected_repository / config.stage_contract_directory).resolve()
    if not expected_contract.is_relative_to(contract_root):
        _live_drift("stage_contract_path", f"inside {contract_root}", expected_contract)
    if observation.canonical_contract_path != str(expected_contract):
        _live_drift(
            "stage_contract_path", str(expected_contract), observation.canonical_contract_path
        )
    if not observation.contract_exists:
        _live_drift("stage_contract_exists", True, False)
    if observation.contract_hash != record.stage_contract_hash:
        _live_drift("stage_contract_hash", record.stage_contract_hash, observation.contract_hash)
    if observation.engine_version != record.engine_version:
        _live_drift("engine_version", record.engine_version, observation.engine_version)

    state = machine.state
    before_merge = state not in {WorkflowState.MERGED, WorkflowState.CLOSING}
    if before_merge and observation.baseline_sha != record.baseline_commit_sha:
        _live_drift("baseline_commit_sha", record.baseline_commit_sha, observation.baseline_sha)

    classification = _classify_worktree(observation, config)
    if classification.forbidden_paths:
        _live_drift("working_tree_forbidden_paths", (), classification.forbidden_paths)
    if classification.unexpected_paths:
        _live_drift("working_tree_unexpected_paths", (), classification.unexpected_paths)

    branch_boundary_states = {
        WorkflowState.AUTHORIZED,
        WorkflowState.PRECONDITIONS_CHECKED,
    }
    if state in branch_boundary_states:
        if classification.application_paths:
            _live_drift("working_tree", "clean application tree", classification.application_paths)
        if observation.planned_branch_sha is None:
            if observation.current_branch != record.baseline_branch:
                _live_drift("current_branch", record.baseline_branch, observation.current_branch)
            return
        if observation.planned_branch_sha != record.baseline_commit_sha:
            _live_drift(
                "planned_branch_sha",
                record.baseline_commit_sha,
                observation.planned_branch_sha,
            )
        if observation.current_branch not in {
            record.baseline_branch,
            record.planned_stage_branch,
        }:
            _live_drift(
                "current_branch",
                f"{record.baseline_branch} or {record.planned_stage_branch}",
                observation.current_branch,
            )
        raise ResumeReconciliationRequiredError(
            "branch_creation",
            "planned branch exists at the authorized baseline but BRANCH_CREATED is not "
            "persisted",
        )

    planned_required = state not in {WorkflowState.MERGED, WorkflowState.CLOSING}
    if planned_required:
        if observation.planned_branch_sha is None:
            _live_drift("planned_branch_exists", True, False)
        if observation.baseline_is_ancestor_of_planned is not True:
            _live_drift(
                "planned_branch_ancestry",
                True,
                observation.baseline_is_ancestor_of_planned,
            )
        if observation.current_branch != record.planned_stage_branch:
            _live_drift("current_branch", record.planned_stage_branch, observation.current_branch)

    clean_states = {
        WorkflowState.BRANCH_CREATED,
        WorkflowState.COMMITTED,
        WorkflowState.PUSHED,
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
        WorkflowState.MERGED,
        WorkflowState.CLOSING,
    }
    if state in clean_states and classification.application_paths:
        _live_drift("working_tree", "clean application tree", classification.application_paths)

    attempts = _read_persisted_attempts(state_store, context.workflow_id)
    if state is WorkflowState.BRANCH_CREATED:
        implementation_attempts = [
            item
            for item in attempts
            if item.kind is AttemptKind.INITIAL_EXECUTION
            and item.state is WorkflowState.IMPLEMENTING
        ]
        if implementation_attempts:
            raise ResumeReconciliationRequiredError(
                "implementation_attempt",
                "implementation attempt evidence exists while state remains BRANCH_CREATED",
            )
        if observation.planned_branch_sha != record.baseline_commit_sha:
            _live_drift(
                "planned_branch_sha",
                record.baseline_commit_sha,
                observation.planned_branch_sha,
            )

    dirty_permitted_states = {
        WorkflowState.IMPLEMENTING,
        WorkflowState.REPAIRING,
        WorkflowState.VALIDATING,
        WorkflowState.QA_RUNNING,
        WorkflowState.READY_TO_COMMIT,
    }
    if state not in clean_states | dirty_permitted_states | branch_boundary_states:
        _live_drift("resume_state_policy", "supported state policy", state.value)

    if state is WorkflowState.IMPLEMENTING and classification.application_paths:
        implementing_attempts = [
            item
            for item in attempts
            if item.kind is AttemptKind.INITIAL_EXECUTION
            and item.state is WorkflowState.IMPLEMENTING
        ]
        if not implementing_attempts:
            _live_drift(
                "implementation_attempt_evidence",
                "persisted attempt for dirty implementation tree",
                "absent",
            )
        phase = implementing_attempts[-1].phase.value
        raise ResumeReconciliationRequiredError(
            "implementation_attempt",
            f"dirty implementation tree has persisted {phase} attempt evidence but no "
            "persisted diff identity that can authorize it",
        )

    if state is WorkflowState.REPAIRING and classification.application_paths:
        repair_attempts = [item for item in attempts if item.kind is AttemptKind.REPAIR]
        if not repair_attempts:
            _live_drift(
                "repair_attempt_evidence", "persisted repair attempt for dirty tree", "absent"
            )
        phase = repair_attempts[-1].phase.value
        raise ResumeReconciliationRequiredError(
            "repair_attempt",
            f"dirty repair tree has persisted {phase} attempt evidence but no persisted diff "
            "identity that can authorize it",
        )

    if state is WorkflowState.READY_TO_COMMIT and not classification.application_paths:
        raise ResumeReconciliationRequiredError(
            "commit_boundary",
            "READY_TO_COMMIT has a clean tree; possible commit completion requires persisted "
            "commit evidence and reconciliation",
        )

    if state in {
        WorkflowState.COMMITTED,
        WorkflowState.PUSHED,
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
    }:
        raise ResumeReconciliationRequiredError(
            "commit_evidence",
            "this persisted state requires expected commit/ref evidence not represented by "
            "transition history alone",
        )
    if state in {WorkflowState.MERGED, WorkflowState.CLOSING}:
        if observation.current_branch not in {
            record.baseline_branch,
            record.planned_stage_branch,
        }:
            _live_drift(
                "current_branch",
                f"{record.baseline_branch} or {record.planned_stage_branch}",
                observation.current_branch,
            )
        raise ResumeReconciliationRequiredError(
            "merge_closeout_evidence",
            "merged/closeout state requires persisted merge and closeout-operation evidence",
        )


def _persist_binding_drift_failure(
    state_store: StateStore,
    context: AuthorizationContext,
    machine: WorkflowStateMachine,
    *,
    repository_path: str,
) -> None:
    """Durably record the required `-> FAILED` transition for a workflow whose authorization
    binding has drifted (`WORKFLOW_STATES.md` §6 item 3), then apply it in memory.

    Validates the edge *before* persisting anything (`validate_transition`, raising without
    writing if, unexpectedly, `FAILED` is not reachable from the current state) — the same
    validate-before-mutate discipline used everywhere else in this module. Every non-terminal
    state reachable here has a `-> FAILED` edge in `ALLOWED_TRANSITIONS` (`WORKFLOW_STATES.md`
    §3), so this is not expected to ever raise in practice; it is a defensive check, not a
    reachable-in-normal-operation branch. Writes exactly one `StateTransitionRecord` — no other
    artifact is touched — matching the finding's "no additional transition or artifact mutation
    after rejection" requirement.
    """
    from_state = machine.state
    validate_transition(from_state, WorkflowState.FAILED)
    state_store.record_transition(
        StateTransitionRecord(
            workflow_id=context.workflow_id,
            target_repository=context.repository_identity,
            repository_path=repository_path,
            stage_id=context.stage_id,
            from_state=from_state.value,
            to_state=WorkflowState.FAILED.value,
            timestamp=datetime.now(UTC).isoformat(),
            actor="orchestrator",
            gate_evidence_ref=None,
        )
    )
    machine.transition_to(WorkflowState.FAILED)


def resume_workflow(
    context: AuthorizationContext,
    *,
    state_store: StateStore,
    lock: RepositoryLock,
    current_binding: CurrentAuthorizationBinding | None = None,
    config: WorkflowConfig | None = None,
    _observer: ResumeObserver | None = None,
) -> ResumedWorkflow:
    """Resume `context.workflow_id`'s persisted workflow, or raise a typed `ResumeError`.

    Order of operations, each of which can reject the resume attempt without mutating anything
    beyond what step 8a itself durably records:

    1. Acquire `lock` (`RepositoryLockUnavailableError` on contention) — required *before* any
       workflow is exposed as resumable, so two processes can never simultaneously believe they
       resumed the same workflow (WORKFLOW_STATES.md §6 item 5).
    2. Verify the acquired lock two ways (`RepositoryLockIdentityMismatchError` on either
       failure) — the lock object is caller-constructed, so nothing else confirms it belongs to
       the repository being resumed: (a) `lock.lock_path`, resolved, must equal
       `canonical_lock_path(current_binding.repository_path)` — the one deterministic location
       for that repository's lock, never an arbitrary caller-selected path (`lock.py`); (b) the
       metadata read via `lock.read_metadata()` must match `context.workflow_id`,
       `context.repository_identity`, and `current_binding.repository_path`.
    3. Load persisted history via `state_store.read_transitions` (`MissingPersistedStateError` if
       empty; `CorruptedHistoryError` if the store itself detects corruption).
    4. Validate the history is internally consistent (`InconsistentHistoryError`) — checked in
       full *before* replay, never partially.
    5. Replay it through a fresh `WorkflowStateMachine` using its own transition-table validation
       (`InconsistentHistoryError` if any recorded edge is illegal) — this is the only step that
       actually reconstructs workflow state, and it never bypasses Step 5A's transition table.
       Crossing `CREATED -> AUTHORIZED` during this replay additionally requires (via
       `_apply_validated_authorization`, inside `_replay_history`) a persisted
       `AuthorizationRecord` that actually exists and is bound to *this* workflow/repository/
       stage (`MissingAuthorizationRecordError` / `CorruptedAuthorizationRecordError` /
       `AuthorizationBindingDriftError`) — the coarsest, StateTransitionRecord-scoped half of
       step 8a's binding check, performed unconditionally by `_replay_history` itself rather than
       deferred to this function.
    6. Reject a workflow already in a terminal state (`WorkflowAlreadyTerminalError`) — nothing
       to resume.
    7. Confirm the `StateTransitionRecord` history's identity matches `context`
       (`AuthorizationScopeMismatchError`) — a coarse, StateTransitionRecord-level sanity check
       that this is even the workflow the caller thinks it is.
    8. Load the persisted `AuthorizationRecord` (`MissingAuthorizationRecordError` if absent —
       every non-terminal, resumable workflow must have one, since `CREATED`'s only non-terminal
       edge is `AUTHORIZED`, which only `authorize()` ever produces).
       8a. Production resume obtains typed live repository/Git/contract/runtime observations
           internally and evaluates the state/evidence matrix in `WORKFLOW_STATES.md` §6a. On
           drift it durably persists the legal `-> FAILED` edge before raising. A contract-defined
           uncertain side-effect boundary raises `ResumeReconciliationRequiredError` without
           changing history and must reconcile before repetition.

    If any of steps 2-8 fails, `lock` is released before the exception propagates — a rejected
    resume never leaves the lock held. Only a fully successful resume returns with the lock still
    acquired, bundled into the returned `ResumedWorkflow`.

    When `config` is supplied (always by production `WorkflowSession.resume`), this function
    constructs the DD-14 local observer unless a raw-observation test adapter is injected. The
    legacy `current_binding`-only path is retained solely for accumulated lower-level white-box
    compatibility and is not the production authority.
    """
    if config is not None:
        resume_repository_path = str(config.repository_path.resolve())
    elif current_binding is not None:
        # Deprecated white-box compatibility path. Production WorkflowSession.resume always
        # supplies config and therefore performs live observation below.
        resume_repository_path = str(Path(current_binding.repository_path).resolve())
    else:
        raise ResumeError(
            "resume_workflow requires config for live production observation; the legacy "
            "current_binding input is retained only for lower-level white-box compatibility."
        )

    try:
        lock.acquire()
    except LockContentionError as exc:
        raise RepositoryLockUnavailableError(
            f"Repository lock unavailable for workflow {context.workflow_id!r}: {exc}"
        ) from exc

    try:
        # The lock's own physical path must *be* the one canonical location for the repository
        # current_binding independently names — never merely a path the caller happened to
        # choose (`canonical_lock_path`'s docstring; Finding 4: "Resume must not accept an
        # arbitrary caller-selected lock path"). Checked before metadata content: a caller could
        # otherwise construct a `RepositoryLock` at any path they like and write metadata that
        # simply repeats the identity resume expects.
        expected_lock_path = canonical_lock_path(Path(resume_repository_path))
        lock_metadata = lock.read_metadata()
        if (
            lock.lock_path.resolve() != expected_lock_path
            or lock_metadata is None
            or lock_metadata.workflow_id != context.workflow_id
            or lock_metadata.repository_identity != context.repository_identity
            # Resolved, not a raw string comparison: canonical_lock_path above already collapses
            # symlink aliases for the lock *path* itself, so this metadata-level check must
            # tolerate the same aliasing — otherwise a legitimate resume through a symlinked
            # repository_path would be wrongly rejected even though the lock path check passed.
            or Path(lock_metadata.repository_path).resolve()
            != Path(resume_repository_path).resolve()
        ):
            lock_workflow_id = lock_metadata.workflow_id if lock_metadata else None
            lock_repository_identity = lock_metadata.repository_identity if lock_metadata else None
            lock_repository_path = lock_metadata.repository_path if lock_metadata else None
            raise RepositoryLockIdentityMismatchError(
                f"Lock at {lock.lock_path!r} (canonical path for this repository: "
                f"{str(expected_lock_path)!r}) is bound to workflow_id={lock_workflow_id!r}, "
                f"repository_identity={lock_repository_identity!r}, "
                f"repository_path={lock_repository_path!r}, but resume was requested for "
                f"workflow_id={context.workflow_id!r}, "
                f"repository_identity={context.repository_identity!r}, "
                f"repository_path={resume_repository_path!r}."
            )

        records = _load_and_validate_history(context.workflow_id, state_store)
        # `_replay_history` can itself raise `AuthorizationBindingDriftError` while crossing
        # CREATED -> AUTHORIZED (the persisted AuthorizationRecord doesn't bind to the persisted
        # history: wrong workflow/repository/stage, or a malformed record). Unlike step 8a's
        # drift check below, this is never followed by a durable `-> FAILED` persist: `CREATED`
        # has no `-> FAILED` edge in `ALLOWED_TRANSITIONS` (WORKFLOW_STATES.md §3 — "nothing is
        # yet bound to drift before authorization"), since the workflow was never actually
        # authorized in the first place. It propagates exactly like
        # `MissingAuthorizationRecordError` or `MissingPersistedStateError` already do from this
        # same position — reported, not
        # recorded as a state transition — and the outer `except Exception` below still releases
        # the lock either way.
        machine = _replay_history(records, state_store=state_store, workflow_id=context.workflow_id)
        if machine.is_terminal:
            raise WorkflowAlreadyTerminalError(
                f"Workflow {context.workflow_id!r} is already in terminal state "
                f"{machine.state.value!r}; there is nothing to resume."
            )
        _check_identity_matches_context(context, records)

        authorization_record = _load_authorization_record(state_store, context.workflow_id)
        if authorization_record is None:
            raise MissingAuthorizationRecordError(
                f"No persisted authorization record found for workflow {context.workflow_id!r}; "
                "a resumable (non-terminal) workflow must have one, since CREATED's only "
                "non-terminal edge is AUTHORIZED, which only authorize() ever produces."
            )
        if config is not None:
            observer = _observer if _observer is not None else LocalResumeObserver(config)
            try:
                observation = observer.observe(
                    stage_contract_path=authorization_record.stage_contract_path,
                    baseline_branch=authorization_record.baseline_branch,
                    planned_branch=authorization_record.planned_stage_branch,
                )
                _validate_live_resume_observation(
                    context=context,
                    record=authorization_record,
                    machine=machine,
                    observation=observation,
                    config=config,
                    state_store=state_store,
                )
            except ResumeObservationError as exc:
                drift = AuthorizationBindingDriftError(
                    exc.field, "independently observable live value", exc.detail
                )
                _persist_binding_drift_failure(
                    state_store,
                    context,
                    machine,
                    repository_path=resume_repository_path,
                )
                raise drift from exc
            except AuthorizationBindingDriftError:
                _persist_binding_drift_failure(
                    state_store,
                    context,
                    machine,
                    repository_path=resume_repository_path,
                )
                raise
        else:
            assert current_binding is not None
            try:
                _detect_authorization_binding_drift(context, current_binding, authorization_record)
            except AuthorizationBindingDriftError:
                _persist_binding_drift_failure(
                    state_store,
                    context,
                    machine,
                    repository_path=resume_repository_path,
                )
                raise
    except Exception:
        lock.release()
        raise

    return ResumedWorkflow(
        machine=machine,
        transitions=records,
        lock=lock,
        state_store=state_store,
        repository_path=resume_repository_path,
    )


# --------------------------------------------------------------------------------------------
# Retry and reconciliation policy (WORKFLOW_STATES.md §5, §5a; FAILURE_RECOVERY.md §1, §1a).
#
# Decision logic only. Every function here reads persisted history through the already-existing
# `StateStore` API (reusing `_load_and_validate_history`/`_replay_history` from the resume section
# above for full-history consistency and authorization-evidence checking — the same primitives,
# not a weaker variant) and returns a typed recommendation; none of them execute a command, Skill,
# Provider, or Git/GitHub operation, and none of them perform the transition they recommend.
# `RepositoryLock` is deliberately not required here: unlike
# `resume_workflow` (which establishes exclusive access from a cold start), these functions are
# called mid-flight by an Orchestrator that already holds the lock for the workflow's entire
# active lifetime — re-acquiring it here would be redundant, not an omission.
# --------------------------------------------------------------------------------------------


class RetryError(Exception):
    """Base error for retry/reconciliation decision failures.

    `evaluate_repair_attempt` and `evaluate_initial_execution_failure` can also raise the
    resume-section's own `ResumeError`/`AuthorizationError` subtypes (`MissingPersistedStateError`,
    `CorruptedHistoryError`, `InconsistentHistoryError`, `MissingAuthorizationRecordError`,
    `CorruptedAuthorizationRecordError`, `AuthorizationBindingDriftError`) unwrapped, since both
    reuse `_load_and_validate_history`/`_replay_history` directly rather than re-implementing
    history or authorization validation — "reject retry when persisted history is corrupt,
    inconsistent, or unauthorized" is satisfied by that reuse, not by new logic.
    """


class NotRetryableStateError(RetryError):
    """Raised when evaluation is requested for a state outside the documented retryable set
    (`RETRYABLE_STATES`) — not every non-terminal state carries retry/reconciliation semantics.
    """


class UnexpectedWorkflowStateError(RetryError):
    """Raised when the persisted, reconstructed workflow state disagrees with the state the
    caller asked to evaluate."""


class WorkflowStageMismatchError(RetryError):
    """Raised when the caller-supplied `stage_id` disagrees with the persisted workflow's own
    (already internally-uniform, per `_validate_history_consistency`) `stage_id`."""


class MissingReconciliationEvidenceError(RetryError):
    """Raised when a possible-side-effect failure is evaluated without supplying `evidence` —
    WORKFLOW_STATES.md §5a item 2: a side-effecting operation is "never retried blindly" once a
    side effect may have occurred."""


class EvidenceScopeMismatchError(RetryError):
    """Raised when a confirmed `ReconciliationEvidence`'s binding fields (`workflow_id`,
    `repository_identity`, `repository_path`, `stage_id`) disagree with the scope
    `evaluate_initial_execution_failure` was actually called for.

    Mirrors `AuthorizationScopeMismatchError`'s field/expected/actual shape: a string label
    alone must never authorize advancement, and evidence collected for one workflow, repository,
    or stage must never be silently accepted for another.
    """

    def __init__(self, field: str, expected: str, actual: str) -> None:
        self.field = field
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Reconciliation evidence scope mismatch on {field!r}: this evaluation requires "
            f"{expected!r}, but the supplied evidence is bound to {actual!r}."
        )


class EvidenceOperationMismatchError(RetryError):
    """Raised when a confirmed `ReconciliationEvidence`'s typed `evidence` does not match the
    operation-specific evidence type required for the `state` being evaluated (e.g.
    `CommitEvidence` supplied for a `PUSHED` — a `push_stage_branch` — evaluation, which
    requires `RemoteRefEvidence`).
    """


class EvidenceConsistencyError(RetryError):
    """Raised when a confirmed `ReconciliationEvidence`'s claimed `side_effect_succeeded` boolean
    contradicts its own typed evidence's expected/observed comparison — e.g. claiming success
    while the observed SHA does not match the expected one. A caller controls the boolean claim
    and the evidence fields independently; this is the structural check that the two are at
    least internally consistent with each other (never a live re-verification of either against
    actual repository state, which remains out of this module's scope).
    """


class ReconciliationVerifierUnavailableError(RetryError):
    """Raised when confirmed reconciliation evidence cannot be independently verified: either the
    evidence type describes remote/GitHub state (`RemoteRefEvidence`, `PullRequestEvidence`) that
    AUTO-002 has no authorized network-reaching observer for, or the locally-verifiable evidence
    type's local Git observation itself failed (the repository is missing, is not a Git
    repository, or a Git invocation failed/timed out) rather than producing a definite answer.

    AUTO002-F07, Human Owner decision 2026-07-27: a caller's success claim is never itself proof.
    Lack of an authorized verifier must never be interpreted as successful evidence — this error
    is the fail-closed result, never a silent pass-through of the caller's claim. Distinct from
    `LocalEvidenceVerificationFailedError`, which means verification *ran* and *disagreed* with
    the caller's claim; this means verification could not run (for remote/PR evidence) or could
    not reach a conclusive local answer at all.
    """


class LocalEvidenceVerificationFailedError(RetryError):
    """Raised when independent local Git or filesystem observation actively disagrees with, or
    cannot substantiate, confirmed evidence's specific claim — a referenced commit does not exist
    locally, is not reachable from the claimed stage branch, an independently recomputed tree SHA
    disagrees with the caller-supplied one, or a referenced completion-report artifact does not
    resolve to an existing, confined, regular file. A caller-supplied SHA, branch label, or
    artifact reference is never itself proof (AUTO002-F07, Human Owner decision 2026-07-27).
    """


class CorruptedAttemptRecordError(RetryError):
    """Raised when a persisted line in `attempts.jsonl` fails to parse into a valid
    `RetryAttemptRecord` (e.g. a negative or zero attempt number, a missing field, or a blank
    line) — or when a `COMPLETED` record has no matching `STARTED` reservation. Never silently
    dropped or skipped: a record that is broken is corruption, not "some other data," so it is
    never treated as absent.
    """


class InconsistentAttemptHistoryError(RetryError):
    """Raised when a decoded retry-attempt record disagrees with the workflow/stage it was read
    as part of, or when supplied reconciliation evidence is internally contradictory for the
    state it was given against (e.g. `recoverable` set for a state where FAILURE_RECOVERY.md §1a
    says that condition never applies)."""


class DuplicateAttemptNumberError(RetryError):
    """Raised when two persisted attempt records claim the same `attempt_number`, or a new
    attempt is recorded with a number that already exists."""


class SkippedAttemptNumberError(RetryError):
    """Raised when persisted attempt numbers are not contiguous starting at 1, or a new attempt
    is recorded with a number that would leave a gap."""


class InvalidAttemptNumberError(RetryError):
    """Raised when an attempt number is not a positive integer (attempts are one-based)."""


class AttemptLimitExceededError(RetryError):
    """Raised when persisted history already shows more attempts than the configured limit
    permits, or a new attempt would exceed it — evidence the limit was violated somewhere, since
    this module never permits crossing it going forward."""


class UnreconciledAttemptError(RetryError):
    """Raised when `evaluate_initial_execution_failure` is asked to evaluate a
    `PROVEN_NO_SIDE_EFFECT` (blind, same-state retry) failure, but persisted evidence shows the
    latest attempt for this scope was started and never recorded as completed.

    That claim is definitionally contradicted by the evidence: "proven no side effect" requires
    the operation never reached a point where a side effect could occur, but a `STARTED` record
    means it did at least begin. Requirement 6: "no operation may be re-executed without
    reconciliation after uncertain execution" — the caller must instead evaluate this scope with
    `failure_kind=POSSIBLE_SIDE_EFFECT` and real evidence.
    """


class AttemptKind(StrEnum):
    """Distinguishes the two retry mechanisms WORKFLOW_STATES.md defines, per requirement 21/22
    of this stage's contract — they are never conflated into one counter."""

    INITIAL_EXECUTION = "initial_execution"
    """WORKFLOW_STATES.md §5a: a same-state bounded retry of a side-effecting operation's own
    first-time execution, before any side effect is known to have occurred."""

    REPAIR = "repair"
    """WORKFLOW_STATES.md §5 / FAILURE_RECOVERY.md §1: the VALIDATING/QA_RUNNING <-> REPAIRING
    code-fix cycle, bounded to 3 attempts per workflow."""


# The authoritative retryable-state set, defined strictly from WORKFLOW_STATES.md — not every
# non-terminal state (10 of the 16 non-terminal states carry no retry/reconciliation semantics
# at all: CREATED, AUTHORIZED, PRECONDITIONS_CHECKED, BRANCH_CREATED, REPAIRING itself, PR_OPEN,
# AUTO_MERGE_ENABLED, WAITING_FOR_CHECKS, MERGED, CLOSING).
REPAIR_RETRYABLE_STATES: frozenset[WorkflowState] = frozenset(
    {WorkflowState.VALIDATING, WorkflowState.QA_RUNNING}
)
INITIAL_EXECUTION_RETRYABLE_STATES: frozenset[WorkflowState] = frozenset(
    {
        WorkflowState.IMPLEMENTING,
        WorkflowState.READY_TO_COMMIT,
        WorkflowState.COMMITTED,
        WorkflowState.PUSHED,
    }
)
RETRYABLE_STATES: frozenset[WorkflowState] = (
    REPAIR_RETRYABLE_STATES | INITIAL_EXECUTION_RETRYABLE_STATES
)

_RETRYABLE_STATES_BY_KIND: dict[AttemptKind, frozenset[WorkflowState]] = {
    AttemptKind.REPAIR: REPAIR_RETRYABLE_STATES,
    AttemptKind.INITIAL_EXECUTION: INITIAL_EXECUTION_RETRYABLE_STATES,
}

# WORKFLOW_STATES.md §5a item 3: the ordinary forward edge reconciliation success advances to —
# already in ALLOWED_TRANSITIONS, gaining "or reconciliation confirms success" as an additional
# reason, never a new edge.
_FORWARD_EDGE_AFTER_RECONCILIATION: dict[WorkflowState, WorkflowState] = {
    WorkflowState.IMPLEMENTING: WorkflowState.VALIDATING,
    WorkflowState.READY_TO_COMMIT: WorkflowState.COMMITTED,
    WorkflowState.COMMITTED: WorkflowState.PUSHED,
    WorkflowState.PUSHED: WorkflowState.PR_OPEN,
}


class InitialExecutionFailureKind(StrEnum):
    """WORKFLOW_STATES.md §5a items 1-2: how a first-time side-effecting operation's failure is
    classified before this policy applies. Classification is never performed by this module —
    "explicit and deterministic, recorded in SKILL_CONTRACTS.md... not left to runtime judgment"
    (§5a item 1) — it is always supplied as an input by the (not yet implemented) Skill/Provider
    layer that actually observed the failure.
    """

    PROVEN_NO_SIDE_EFFECT = "proven_no_side_effect"
    """§5a item 1: the operation never reached the point where a side effect could occur."""

    POSSIBLE_SIDE_EFFECT = "possible_side_effect"
    """§5a item 2: any failure surfaced by an already-invoked git/gh subprocess or an
    already-started provider process — reconciliation, never a blind retry, applies."""


class RetryOutcome(StrEnum):
    """The complete, closed set of outcomes this policy can reach (stage contract requirement
    6). `NO_RETRY_REQUIRED` and `RETRY_ALLOWED` both permit proceeding and recommend the same
    next action — they differ only in whether this is the first attempt (nothing has failed
    before) or a genuine retry (a prior attempt already failed); FAILURE_RECOVERY.md and
    WORKFLOW_STATES.md draw no behavioral distinction between the two, only this module's result
    reporting does, for clearer audit narration.
    """

    NO_RETRY_REQUIRED = "no_retry_required"
    RETRY_ALLOWED = "retry_allowed"
    RETRY_LIMIT_EXHAUSTED = "retry_limit_exhausted"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    RECONCILIATION_SUCCESSFUL = "reconciliation_successful"
    RECONCILIATION_FAILED = "reconciliation_failed"
    UNRECOVERABLE_FAILURE = "unrecoverable_failure"


_CONSISTENT_BY_OUTCOME: dict[RetryOutcome, bool] = {
    RetryOutcome.NO_RETRY_REQUIRED: True,
    RetryOutcome.RETRY_ALLOWED: True,
    RetryOutcome.RETRY_LIMIT_EXHAUSTED: True,
    RetryOutcome.RECONCILIATION_REQUIRED: False,
    RetryOutcome.RECONCILIATION_SUCCESSFUL: True,
    RetryOutcome.RECONCILIATION_FAILED: False,
    RetryOutcome.UNRECOVERABLE_FAILURE: False,
}
_RETRY_ALLOWED_BY_OUTCOME: dict[RetryOutcome, bool] = {
    RetryOutcome.NO_RETRY_REQUIRED: True,
    RetryOutcome.RETRY_ALLOWED: True,
    RetryOutcome.RETRY_LIMIT_EXHAUSTED: False,
    RetryOutcome.RECONCILIATION_REQUIRED: False,
    RetryOutcome.RECONCILIATION_SUCCESSFUL: False,
    RetryOutcome.RECONCILIATION_FAILED: False,
    RetryOutcome.UNRECOVERABLE_FAILURE: False,
}


class AttemptPhase(StrEnum):
    """Whether a persisted initial-execution attempt record represents the operation merely
    *starting* (outcome not yet known — recorded durably before invocation, so a crash mid-
    attempt is detectable on restart) or actually *completing* (outcome known and recorded).
    Requirement 6: "no operation may be re-executed without reconciliation after uncertain
    execution" — a `STARTED` entry with no matching `COMPLETED` entry is exactly that signature.
    """

    STARTED = "started"
    COMPLETED = "completed"


class RetryAttemptRecord(_StrictModel):
    """One retry attempt's scope (stage contract requirement 11): the workflow, stage, failed
    state, kind, and attempt number it belongs to. For `AttemptKind.INITIAL_EXECUTION`, persisted
    as its own dedicated, append-only event — one JSON line per record in
    `<workflow_id>/attempts.jsonl` (`_persist_attempt_record`) — never encoded into a
    `CommandExecutionRecord`, whose fields describe an actual Skill/provider command execution
    (`AUDIT_MODEL.md` §2) and are never repurposed for retry bookkeeping. For `AttemptKind.REPAIR`,
    attempts are still counted directly from `StateTransitionRecord` history and never
    individually materialized as this type.
    """

    workflow_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    state: WorkflowState
    kind: AttemptKind
    attempt_number: int = Field(ge=1)
    phase: AttemptPhase = AttemptPhase.COMPLETED
    timestamp: str

    _validate_timestamp = field_validator("timestamp")(_validate_iso8601)


class ImplementationDiffEvidence(_StrictModel):
    """Operation-specific evidence for `IMPLEMENTING` (the implementation-provider attempt):
    SKILL_CONTRACTS.md/MODEL_PROVIDER_CONTRACTS.md's own idempotency check is "inspecting the
    stage branch's actual diff against what the provider was asked to produce." Identifies
    exactly which commit's diff was inspected — a string label alone is never sufficient.
    """

    stage_branch: str = Field(min_length=1)
    observed_head_sha: str
    attempt_number: int = Field(default=1, ge=1)
    changed_paths: tuple[str, ...] = ()
    completion_report_reference: str = Field(min_length=1)
    """A reference to the ImplementationAgent's own persisted completion report
    (`AGENT_CONTRACTS.md`) — "reference an existing persisted evidence artifact," never a bare
    claim with nothing backing it."""

    _validate_observed_head_sha = field_validator("observed_head_sha")(_validate_git_sha)

    @field_validator("changed_paths")
    @classmethod
    def _changed_paths_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("changed_paths must be sorted and unique")
        for path in value:
            if not path or canonical_repository_relative_path(path) != path:
                raise ValueError(
                    f"changed path is not canonical repository-relative form: {path!r}"
                )
        return value


class _ImplementationCompletionReport(_StrictModel):
    """The minimal persisted report binding required for reconciliation evidence."""

    workflow_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    stage_branch: str = Field(min_length=1)
    observed_head_sha: str
    changed_paths: tuple[str, ...]

    _validate_observed_head_sha = field_validator("observed_head_sha")(_validate_git_sha)

    @field_validator("changed_paths")
    @classmethod
    def _report_changed_paths_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return ImplementationDiffEvidence._changed_paths_canonical(value)


class CommitEvidence(_StrictModel):
    """Operation-specific evidence for `READY_TO_COMMIT` (`create_commit`): "does the tree
    already match the expected committed diff." `expected_tree_sha`/`observed_tree_sha` are
    compared for consistency with the parent record's `side_effect_succeeded` claim
    (`ReconciliationEvidence._validate_shape`)."""

    commit_sha: str
    expected_tree_sha: str
    observed_tree_sha: str

    _validate_commit_sha = field_validator("commit_sha")(_validate_git_sha)
    _validate_expected_tree_sha = field_validator("expected_tree_sha")(_validate_git_sha)
    _validate_observed_tree_sha = field_validator("observed_tree_sha")(_validate_git_sha)


class RemoteRefEvidence(_StrictModel):
    """Operation-specific evidence for `COMMITTED` (`push_stage_branch`): "does the remote ref
    already match.\" """

    remote_ref: str
    expected_sha: str
    observed_sha: str

    _validate_remote_ref = field_validator("remote_ref")(_validate_remote_ref)
    _validate_expected_sha = field_validator("expected_sha")(_validate_git_sha)
    _validate_observed_sha = field_validator("observed_sha")(_validate_git_sha)


class PullRequestEvidence(_StrictModel):
    """Operation-specific evidence for `PUSHED` (`create_pull_request`): "does an open PR
    already exist for the branch," matching the expected head."""

    pr_number: int = Field(ge=1)
    head_branch: str = Field(min_length=1)
    base_branch: str = Field(min_length=1)
    expected_head_sha: str
    observed_head_sha: str

    _validate_expected_head_sha = field_validator("expected_head_sha")(_validate_git_sha)
    _validate_observed_head_sha = field_validator("observed_head_sha")(_validate_git_sha)


_OperationEvidence = (
    ImplementationDiffEvidence | CommitEvidence | RemoteRefEvidence | PullRequestEvidence
)

# Which typed evidence variant is legal for which initial-execution-retryable state — the
# binding between "operation" and "evidence shape" `evaluate_initial_execution_failure` enforces
# (`EvidenceOperationMismatchError` otherwise).
_EVIDENCE_TYPE_BY_STATE: dict[WorkflowState, type[_OperationEvidence]] = {
    WorkflowState.IMPLEMENTING: ImplementationDiffEvidence,
    WorkflowState.READY_TO_COMMIT: CommitEvidence,
    WorkflowState.COMMITTED: RemoteRefEvidence,
    WorkflowState.PUSHED: PullRequestEvidence,
}

# (expected_field, observed_field) pairs whose equality must agree with the parent record's
# side_effect_succeeded claim (`ReconciliationEvidence._validate_shape`) — evidence types with no
# single natural expected/observed comparison (`ImplementationDiffEvidence`) are absent here and
# are not cross-checked this way.
_EVIDENCE_COMPARISON_FIELDS: dict[type[_OperationEvidence], tuple[str, str]] = {
    CommitEvidence: ("expected_tree_sha", "observed_tree_sha"),
    RemoteRefEvidence: ("expected_sha", "observed_sha"),
    PullRequestEvidence: ("expected_head_sha", "observed_head_sha"),
}


class ReconciliationEvidence(_StrictModel):
    """Caller-supplied evidence about a side-effecting operation's real-world outcome, produced
    by a (not yet implemented) Skill's own idempotency check (WORKFLOW_STATES.md §7) — this
    module interprets but never collects it. Before accepting confirmed evidence, the
    Orchestrator independently re-verifies every locally observable binding against Git,
    filesystem, authorization, attempt-history, and path-policy state; remote/GitHub-only
    evidence fails closed until an authorized observer exists.

    Bound to the exact scope it was collected for (`workflow_id`, `repository_identity`,
    `repository_path`, `stage_id`) — checked by `evaluate_initial_execution_failure` against the
    scope it was actually called for (`EvidenceScopeMismatchError` on mismatch), the same
    non-circularity discipline `AuthorizationContext` already applies to authorization itself:
    evidence collected for one workflow/repository/stage can never be silently accepted for
    another.

    Once `side_effect_confirmed` is `True`, `evidence` must be present and be the one typed,
    operation-specific evidence variant appropriate to the state being evaluated
    (`ImplementationDiffEvidence`, `CommitEvidence`, `RemoteRefEvidence`, or
    `PullRequestEvidence`) — a bare string label is never sufficient. For the three variants with
    a natural expected/observed comparison, that comparison's equality must agree with
    `side_effect_succeeded`: claiming success while the observed value disagrees with the
    expected one (or vice versa) is an internally-contradictory claim
    (`EvidenceConsistencyError`), even though this module still cannot confirm either value is
    *actually* true of the live repository.
    """

    workflow_id: str = Field(min_length=1)
    repository_identity: str = Field(min_length=1)
    repository_path: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)

    side_effect_confirmed: bool
    """§5a item 2: whether the side effect's occurrence has been confirmed one way or the
    other. `False` means still unknown — reconciliation has not yet produced an answer."""

    side_effect_succeeded: bool | None = None
    """Meaningful only once `side_effect_confirmed` is `True`: whether the side effect
    completed correctly (§5a item 3) or is inconsistent (§5a item 4/5)."""

    evidence: _OperationEvidence | None = None
    """The operation-specific typed evidence, required once `side_effect_confirmed` is `True`.
    Never required — and expected `None` — while unconfirmed, since there is nothing yet to cite.
    """

    recoverable: bool | None = None
    """Meaningful only when `side_effect_succeeded` is `False`: whether the inconsistency is
    safely repairable under the existing recovery model (§5a item 4). FAILURE_RECOVERY.md §1a
    states this condition is reachable only from `IMPLEMENTING` — checked separately by the
    caller of this evidence, not by this model."""

    description: str = ""

    @model_validator(mode="after")
    def _validate_shape(self) -> "ReconciliationEvidence":
        if not self.side_effect_confirmed:
            if self.side_effect_succeeded is not None or self.recoverable is not None:
                raise ValueError(
                    "side_effect_succeeded/recoverable are only meaningful once "
                    "side_effect_confirmed is True."
                )
            if self.evidence is not None:
                raise ValueError(
                    "evidence must be absent while side_effect_confirmed is False — there is "
                    "nothing yet to cite."
                )
        else:
            if self.side_effect_succeeded is None:
                raise ValueError(
                    "side_effect_succeeded is required once side_effect_confirmed is True."
                )
            if self.evidence is None:
                raise ValueError(
                    "evidence is required once side_effect_confirmed is True — a bare boolean "
                    "claim is not sufficient; supply the typed, operation-specific evidence "
                    "(commit SHA/tree identity, remote ref and expected SHA, or PR identity, "
                    "head/base branch, and expected head)."
                )
            if self.side_effect_succeeded and self.recoverable is not None:
                raise ValueError(
                    "recoverable is only meaningful when side_effect_succeeded is False."
                )
        return self


def _check_evidence_internal_consistency(evidence: ReconciliationEvidence) -> None:
    """Raise `EvidenceConsistencyError` if a confirmed `evidence`'s claimed
    `side_effect_succeeded` boolean contradicts its own typed evidence's expected/observed
    comparison (e.g. claiming success while the observed SHA does not match the expected one).

    Deliberately not part of `ReconciliationEvidence`'s own pydantic validation: a `ValueError`
    raised inside a `@model_validator` is always re-wrapped into `pydantic.ValidationError` by
    pydantic itself, which would make the specific `EvidenceConsistencyError` type unreachable —
    this runs as a separate, plain check so the typed error actually propagates to callers.
    """
    if evidence.evidence is None:
        return  # unconfirmed; ReconciliationEvidence's own validation already covers this shape
    comparison_fields = _EVIDENCE_COMPARISON_FIELDS.get(type(evidence.evidence))
    if comparison_fields is None:
        return
    expected_field, observed_field = comparison_fields
    matches = getattr(evidence.evidence, expected_field) == getattr(
        evidence.evidence, observed_field
    )
    if evidence.side_effect_succeeded and not matches:
        raise EvidenceConsistencyError(
            f"side_effect_succeeded=True but evidence.{expected_field} does not match "
            f"evidence.{observed_field} — a caller may not claim success while its own supplied "
            "evidence disagrees."
        )
    if not evidence.side_effect_succeeded and matches:
        raise EvidenceConsistencyError(
            f"side_effect_succeeded=False but evidence.{expected_field} matches "
            f"evidence.{observed_field} — an inconsistency claim requires the evidence to "
            "actually show a mismatch."
        )


def _verify_evidence_locally(
    typed_evidence: _OperationEvidence,
    *,
    repository_path: Path,
    audit_directory: Path,
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    authorization_record: AuthorizationRecord,
    expected_attempt_number: int,
    allowed_changed_paths: list[str] | None,
    forbidden_changed_paths: list[str] | None,
) -> None:
    """Independently verify `typed_evidence` against locally-observable Git and filesystem
    facts before it is ever trusted — AUTO002-F07, Human Owner decision 2026-07-27: "reconciliation
    evidence must never be accepted merely because the caller supplies a success Boolean; fields
    are internally self-consistent; a reference string is nonblank."

    `RemoteRefEvidence`/`PullRequestEvidence` describe remote/GitHub facts this module has no
    authorized, network-reaching observer for; those always fail closed here
    (`ReconciliationVerifierUnavailableError`) — remote and PR evidence remain pending future
    authorized Skill/GitHub observation work, never silently accepted on the caller's word alone.

    For `ImplementationDiffEvidence`/`CommitEvidence` (locally verifiable), every claimed fact is
    independently re-derived from local Git state — never merely echoed back from the caller —
    and the referenced completion-report artifact (`ImplementationDiffEvidence` only) is read
    through a descriptor-relative, no-symlink walk under
    `<audit_directory>/<workflow_id>/evidence/<state.value>/...`. A caller supplies only the
    artifact's bare filename, never a path, so the artifact cannot be claimed from another
    workflow or operation.
    """
    if isinstance(typed_evidence, (RemoteRefEvidence, PullRequestEvidence)):
        raise ReconciliationVerifierUnavailableError(
            f"{type(typed_evidence).__name__} describes remote/GitHub state that AUTO-002 has "
            "no authorized local verifier for; a caller's claim alone can never confirm it "
            "(Human Owner decision 2026-07-27, AUTO002-F07). Reconciliation for this state "
            "remains pending future authorized Skill/GitHub observation work."
        )

    observer = LocalEvidenceObserver(repository_path)

    if isinstance(typed_evidence, ImplementationDiffEvidence):
        if allowed_changed_paths is None or forbidden_changed_paths is None:
            raise ReconciliationVerifierUnavailableError(
                "IMPLEMENTING reconciliation requires the configured allowed/forbidden changed-"
                "path policy; absent policy is never treated as authorization."
            )
        if typed_evidence.stage_branch != authorization_record.planned_stage_branch:
            raise LocalEvidenceVerificationFailedError(
                f"stage_branch {typed_evidence.stage_branch!r} does not match the authorized "
                f"planned branch {authorization_record.planned_stage_branch!r}."
            )
        if typed_evidence.attempt_number != expected_attempt_number:
            raise LocalEvidenceVerificationFailedError(
                f"attempt_number {typed_evidence.attempt_number} does not match the latest "
                f"persisted attempt {expected_attempt_number}."
            )
        try:
            exists = observer.commit_exists(typed_evidence.observed_head_sha)
        except LocalEvidenceObservationError as exc:
            raise ReconciliationVerifierUnavailableError(
                f"Unable to independently observe {exc.field}: {exc.detail}"
            ) from exc
        if not exists:
            raise LocalEvidenceVerificationFailedError(
                f"observed_head_sha {typed_evidence.observed_head_sha!r} does not exist in the "
                f"local repository at {repository_path} — the caller's claim is unverifiable "
                "locally and is rejected rather than trusted (AUTO002-F07)."
            )
        try:
            branch_tip = observer.branch_tip(typed_evidence.stage_branch)
        except LocalEvidenceObservationError as exc:
            raise ReconciliationVerifierUnavailableError(
                f"Unable to independently observe {exc.field}: {exc.detail}"
            ) from exc
        if branch_tip != typed_evidence.observed_head_sha:
            raise LocalEvidenceVerificationFailedError(
                f"observed_head_sha {typed_evidence.observed_head_sha!r} is not the exact tip "
                f"{branch_tip!r} of authorized branch {typed_evidence.stage_branch!r}."
            )
        try:
            actual_changed_paths = observer.changed_paths(
                baseline_sha=authorization_record.baseline_commit_sha,
                head_sha=typed_evidence.observed_head_sha,
            )
        except LocalEvidenceObservationError as exc:
            raise ReconciliationVerifierUnavailableError(
                f"Unable to independently observe {exc.field}: {exc.detail}"
            ) from exc
        if actual_changed_paths != typed_evidence.changed_paths:
            raise LocalEvidenceVerificationFailedError(
                f"changed_paths {typed_evidence.changed_paths!r} do not match independently "
                f"observed paths {actual_changed_paths!r}."
            )
        forbidden = tuple(
            path for path in actual_changed_paths if _matches_any(path, forbidden_changed_paths)
        )
        unexpected = tuple(
            path
            for path in actual_changed_paths
            if not _matches_any(path, forbidden_changed_paths)
            and not _matches_any(path, allowed_changed_paths)
        )
        if forbidden or unexpected:
            raise LocalEvidenceVerificationFailedError(
                f"implementation diff violates configured path scope; forbidden={forbidden!r}, "
                f"unexpected={unexpected!r}."
            )
        try:
            artifact_bytes = read_evidence_artifact(
                audit_root=audit_directory,
                workflow_id=workflow_id,
                operation_id=state.value,
                artifact_name=typed_evidence.completion_report_reference,
            )
        except LocalEvidenceObservationError as exc:
            raise LocalEvidenceVerificationFailedError(
                f"completion_report_reference {typed_evidence.completion_report_reference!r} "
                f"could not be independently verified: {exc.detail}"
            ) from exc
        if not artifact_bytes:
            raise LocalEvidenceVerificationFailedError(
                "completion report is empty; file existence alone is not evidence."
            )
        try:
            report_payload = _loads_rejecting_duplicate_keys(artifact_bytes.decode("utf-8"))
            report = _ImplementationCompletionReport.model_validate(report_payload)
        except (UnicodeDecodeError, _DuplicateJSONKeyError, ValidationError, ValueError) as exc:
            raise LocalEvidenceVerificationFailedError(
                f"completion report is malformed or ambiguous: {exc}"
            ) from exc
        expected_report = _ImplementationCompletionReport(
            workflow_id=workflow_id,
            stage_id=stage_id,
            attempt_number=typed_evidence.attempt_number,
            stage_branch=typed_evidence.stage_branch,
            observed_head_sha=typed_evidence.observed_head_sha,
            changed_paths=typed_evidence.changed_paths,
        )
        if report != expected_report:
            raise LocalEvidenceVerificationFailedError(
                "completion report bindings do not exactly match the workflow, stage, attempt, "
                "authorized branch, observed head, and changed paths."
            )
        return

    if isinstance(typed_evidence, CommitEvidence):
        try:
            exists = observer.commit_exists(typed_evidence.commit_sha)
        except LocalEvidenceObservationError as exc:
            raise ReconciliationVerifierUnavailableError(
                f"Unable to independently observe {exc.field}: {exc.detail}"
            ) from exc
        if not exists:
            raise LocalEvidenceVerificationFailedError(
                f"commit_sha {typed_evidence.commit_sha!r} does not exist in the local "
                f"repository at {repository_path} — the caller's claim is unverifiable locally "
                "and is rejected rather than trusted (AUTO002-F07)."
            )
        try:
            actual_tree_sha = observer.tree_sha(typed_evidence.commit_sha)
        except LocalEvidenceObservationError as exc:
            raise ReconciliationVerifierUnavailableError(
                f"Unable to independently observe {exc.field}: {exc.detail}"
            ) from exc
        if actual_tree_sha != typed_evidence.observed_tree_sha:
            raise LocalEvidenceVerificationFailedError(
                f"observed_tree_sha {typed_evidence.observed_tree_sha!r} does not match the "
                f"independently observed tree {actual_tree_sha!r} of commit "
                f"{typed_evidence.commit_sha!r} — the caller's claim disagrees with "
                "independently observed local Git state (AUTO002-F07)."
            )
        return

    raise AssertionError(f"unreachable: unhandled evidence type {type(typed_evidence)!r}")


class RetryReconciliationResult(_StrictModel):
    """The typed result of a retry/reconciliation decision (stage contract requirement 20).

    Never itself a transition, a command execution, or a persisted-state mutation — a
    recommendation and an explanation only. `next_allowed_state`, when not `None`, is always a
    legal edge from `current_state` per `ALLOWED_TRANSITIONS` (enforced by `_build_result`,
    every result's sole construction path).
    """

    outcome: RetryOutcome
    current_state: WorkflowState
    expected_state_or_operation: str
    observed_evidence: str
    consistent: bool
    attempt_count: int = Field(ge=0)
    attempt_limit: int = Field(ge=1)
    retry_allowed: bool
    next_allowed_state: WorkflowState | None
    reason: str


def _build_result(
    *,
    outcome: RetryOutcome,
    current_state: WorkflowState,
    expected_state_or_operation: str,
    observed_evidence: str,
    attempt_count: int,
    attempt_limit: int,
    next_allowed_state: WorkflowState | None,
    reason: str,
) -> RetryReconciliationResult:
    """The sole construction path for `RetryReconciliationResult` — enforces, as an invariant
    rather than a per-branch discipline, that a recommended transition is always one
    `ALLOWED_TRANSITIONS` already contains (stage contract requirement 17).
    """
    if next_allowed_state is not None and not is_transition_allowed(
        current_state, next_allowed_state
    ):
        raise AssertionError(
            "Internal error: refusing to recommend an undocumented transition "
            f"{current_state.value} -> {next_allowed_state.value}."
        )
    return RetryReconciliationResult(
        outcome=outcome,
        current_state=current_state,
        expected_state_or_operation=expected_state_or_operation,
        observed_evidence=observed_evidence,
        consistent=_CONSISTENT_BY_OUTCOME[outcome],
        attempt_count=attempt_count,
        attempt_limit=attempt_limit,
        retry_allowed=_RETRY_ALLOWED_BY_OUTCOME[outcome],
        next_allowed_state=next_allowed_state,
        reason=reason,
    )


def _classify_bounded_attempt(attempt_count: int, attempt_limit: int) -> RetryOutcome:
    if attempt_count == 0:
        return RetryOutcome.NO_RETRY_REQUIRED
    if attempt_count < attempt_limit:
        return RetryOutcome.RETRY_ALLOWED
    return RetryOutcome.RETRY_LIMIT_EXHAUSTED


def _evaluate_bounded_attempt(
    *,
    state: WorkflowState,
    attempt_count: int,
    attempt_limit: int,
    next_state_if_allowed: WorkflowState | None,
    operation_label: str,
) -> RetryReconciliationResult:
    outcome = _classify_bounded_attempt(attempt_count, attempt_limit)
    if outcome is RetryOutcome.RETRY_LIMIT_EXHAUSTED:
        return _build_result(
            outcome=outcome,
            current_state=state,
            expected_state_or_operation=operation_label,
            observed_evidence=f"{attempt_count} of {attempt_limit} attempts already recorded.",
            attempt_count=attempt_count,
            attempt_limit=attempt_limit,
            next_allowed_state=WorkflowState.FAILED,
            reason=(
                f"{attempt_count} of {attempt_limit} attempts already used; no further attempts "
                "are permitted."
            ),
        )
    next_attempt_number = attempt_count + 1
    ordinal = (
        "first attempt"
        if outcome is RetryOutcome.NO_RETRY_REQUIRED
        else f"attempt {next_attempt_number}"
    )
    return _build_result(
        outcome=outcome,
        current_state=state,
        expected_state_or_operation=f"{operation_label} ({ordinal})",
        observed_evidence=f"{attempt_count} of {attempt_limit} attempts recorded so far.",
        attempt_count=attempt_count,
        attempt_limit=attempt_limit,
        next_allowed_state=next_state_if_allowed,
        reason=f"{attempt_count} of {attempt_limit} attempts used; {ordinal} is permitted.",
    )


def _verify_stage_scope(records: list[StateTransitionRecord], stage_id: str) -> None:
    # `_validate_history_consistency` (resume section) already confirmed every record shares
    # exactly one stage_id; only the last record needs consulting to learn what it is.
    persisted_stage_id = records[-1].stage_id
    if persisted_stage_id != stage_id:
        raise WorkflowStageMismatchError(
            f"Requested evaluation for stage {stage_id!r}, but this workflow's persisted "
            f"history belongs to stage {persisted_stage_id!r}."
        )


def _reconstruct_workflow_for_evaluation(
    workflow_id: str, stage_id: str, state: WorkflowState, state_store: StateStore
) -> list[StateTransitionRecord]:
    """Shared preflight for both `evaluate_repair_attempt` and
    `evaluate_initial_execution_failure`: reload and replay history (reusing the resume
    section's own helpers — never bypassing transition validation, requirement 13), reject a
    terminal workflow, and confirm the requested `state`/`stage_id` match persisted reality.

    Uses the same authorization-gated `_replay_history` `resume_workflow` uses — there is no
    weaker variant: a workflow whose persisted history is missing, malformed, or bound to an
    `AuthorizationRecord` for another workflow/repository/stage is rejected here exactly as it
    would be on resume, not silently accepted because this call site never checked.
    """
    records = _load_and_validate_history(workflow_id, state_store)
    machine = _replay_history(records, state_store=state_store, workflow_id=workflow_id)
    if machine.is_terminal:
        raise WorkflowAlreadyTerminalError(
            f"Workflow {workflow_id!r} is already in terminal state {machine.state.value!r}; "
            "retry/reconciliation cannot be evaluated for a terminal workflow."
        )
    if machine.state != state:
        raise UnexpectedWorkflowStateError(
            f"Persisted state for workflow {workflow_id!r} is {machine.state.value!r}, not the "
            f"requested {state.value!r}."
        )
    _verify_stage_scope(records, stage_id)
    return records


def _reconstruct_workflow_expecting_repairing(
    workflow_id: str, stage_id: str, state_store: StateStore
) -> None:
    """Preflight for `record_repair_attempt_started`/`record_repair_attempt`.

    Unlike `_reconstruct_workflow_for_evaluation` (used by `evaluate_repair_attempt`, which
    validates against the `VALIDATING`/`QA_RUNNING` gate a *decision* is being evaluated from),
    recording an actual repair-provider attempt only ever makes sense while the workflow is
    durably in `REPAIRING` — that is when the repair provider actually runs. The caller-supplied
    `state` argument to those two functions identifies which gate originally *triggered* this
    `REPAIRING` cycle (needed for the aggregate, per-workflow counting `FAILURE_RECOVERY.md` §1
    requires), not the workflow's current position, so it is validated against
    `REPAIR_RETRYABLE_STATES` by the caller directly rather than against `machine.state` here.
    """
    records = _load_and_validate_history(workflow_id, state_store)
    machine = _replay_history(records, state_store=state_store, workflow_id=workflow_id)
    if machine.is_terminal:
        raise WorkflowAlreadyTerminalError(
            f"Workflow {workflow_id!r} is already in terminal state {machine.state.value!r}; "
            "a repair attempt cannot be recorded for a terminal workflow."
        )
    if machine.state is not WorkflowState.REPAIRING:
        raise UnexpectedWorkflowStateError(
            f"Persisted state for workflow {workflow_id!r} is {machine.state.value!r}, not "
            "REPAIRING — a repair attempt can only be recorded while the workflow is actually "
            "in the REPAIRING state (the repair provider only ever runs there)."
        )
    _verify_stage_scope(records, stage_id)


def evaluate_repair_attempt(
    *,
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    attempt_limit: int,
    state_store: StateStore,
) -> RetryReconciliationResult:
    """Decide whether another repair attempt is permitted from `state` (`VALIDATING` or
    `QA_RUNNING`), or whether the 3-attempt (or as configured) repair-attempt limit is exhausted
    (WORKFLOW_STATES.md §5; FAILURE_RECOVERY.md §1).

    `attempt_limit` must be supplied by the caller from `WorkflowConfig.repair_attempt_limit` —
    this function never assumes or defaults a limit (requirement 9/10). The attempt count is
    reconstructed, every call, from `workflow_id`'s dedicated, durable repair-attempt events
    (`reconstruct_repair_attempts`) — never inferred from `StateTransitionRecord` history, which
    could only ever see a repair that *completed* (returned to `VALIDATING`) and had no way to
    distinguish "no repair ran" from "a repair ran and crashed before completion," nor any
    reservation step to detect that crash in the first place
    (`has_unreconciled_repair_attempt`, checked first — an unreconciled repair attempt refuses
    this evaluation outright, `UnreconciledAttemptError`, since `FAILURE_RECOVERY.md` §1 treats
    an unrecoverable repair-provider crash as `REPAIRING -> FAILED`, never a blind retry). The
    repair-attempt limit is "per workflow" (FAILURE_RECOVERY.md §1), never per-gate, so completed
    repairs following either a `VALIDATING`- or a `QA_RUNNING`-triggered `REPAIRING` entry count
    against the same total — `reconstruct_repair_attempts`/`has_unreconciled_repair_attempt`
    aggregate across both states themselves, never scoped to just this call's `state`.
    """
    if state not in REPAIR_RETRYABLE_STATES:
        raise NotRetryableStateError(
            f"{state.value!r} is not a repair-retryable state; only "
            f"{sorted(s.value for s in REPAIR_RETRYABLE_STATES)} support the REPAIRING cycle "
            "(WORKFLOW_STATES.md §3; FAILURE_RECOVERY.md §1)."
        )
    if attempt_limit < 1:
        raise ValueError("attempt_limit must be at least 1.")

    _reconstruct_workflow_for_evaluation(workflow_id, stage_id, state, state_store)

    if has_unreconciled_repair_attempt(workflow_id, stage_id, state_store):
        raise UnreconciledAttemptError(
            f"A repair attempt for workflow {workflow_id!r} was started but never recorded as "
            "completed; FAILURE_RECOVERY.md §1 treats an unrecoverable repair-provider crash as "
            "REPAIRING -> FAILED, so a further repair attempt is never permitted here."
        )
    attempts = reconstruct_repair_attempts(workflow_id, stage_id, attempt_limit, state_store)
    attempt_count = len(attempts)

    return _evaluate_bounded_attempt(
        state=state,
        attempt_count=attempt_count,
        attempt_limit=attempt_limit,
        next_state_if_allowed=WorkflowState.REPAIRING,
        operation_label="repair attempt",
    )


INITIAL_EXECUTION_ATTEMPT_LIMIT: int = 3
"""`SKILL_CONTRACTS.md` §3 / `MODEL_PROVIDER_CONTRACTS.md` §2: "3 attempts... counted
independently of the repair-attempt counter." Fixed by this module, never a caller-suppliable
parameter: unlike `evaluate_repair_attempt`'s `attempt_limit` (sourced from
`WorkflowConfig.repair_attempt_limit: Literal[3]` — schema-anchored even though it is itself a
plain function parameter), no `CONFIGURATION_MODEL.md` field exists for this limit at all, since
it is not meant to vary per target repository. With no schema to anchor it, hardcoding it here
is what actually enforces "the fixed policy," rather than trusting every caller to pass 3.
"""

_ATTEMPTS_FILENAME = "attempts.jsonl"


class MissingAttemptReservationError(RetryError):
    """Raised when a *completed* attempt record is requested for an `attempt_number` that has no
    matching `STARTED` reservation already persisted.

    Requirement: "every initial side-effecting operation must durably reserve/start its attempt
    before execution... no execution API may proceed without that reservation." A completed
    record can never be the first record this module has ever seen for its own attempt_number.
    """


def _attempts_path(state_store: StateStore, workflow_id: str) -> Path:
    safe_workflow_id = _safe_workflow_id(workflow_id)
    return state_store.state_directory / safe_workflow_id / _ATTEMPTS_FILENAME


def _read_persisted_attempts(state_store: StateStore, workflow_id: str) -> list[RetryAttemptRecord]:
    """Read every persisted attempt record (any `kind`, any `phase`) for `workflow_id` from its
    dedicated `attempts.jsonl` — never from `CommandExecutionRecord`, which records only genuine
    Skill/provider command executions (`AUDIT_MODEL.md` §2), never retry bookkeeping. Read-only;
    never repairs, reorders, or silently skips what it finds — a blank or malformed line is
    corruption, not an absent record, the same discipline already applied to authorization
    records and transition history.

    AUTO002-F06: also rejects a file missing its terminal newline (`state_store.py`'s own
    `_read_jsonl` check, applied here too). A crash mid-`_write_all` can leave the JSON content
    of the final record fully written but its trailing newline byte lost — content that would
    otherwise parse as perfectly valid JSON and be silently accepted as a genuine, durable
    record, even though it was never confirmed complete. Without this check, that exact crash
    window would defeat the `STARTED`-reservation crash-detection guarantee this file exists to
    provide.
    """
    with _confined_record_fd(
        state_store.state_directory, workflow_id, _ATTEMPTS_FILENAME, write=False
    ) as (fd, _):
        if fd is None:
            return []
        chunks: list[bytes] = []
        while chunk := os.read(fd, 65536):
            chunks.append(chunk)
        raw_bytes = b"".join(chunks)
    if raw_bytes and not raw_bytes.endswith(b"\n"):
        raise CorruptedAttemptRecordError(
            f"Persisted attempts file for workflow {workflow_id!r} is missing its terminal "
            "newline (possible torn append)."
        )
    records: list[RetryAttemptRecord] = []
    for line in raw_bytes.decode("utf-8").splitlines():
        if not line.strip():
            raise CorruptedAttemptRecordError(
                f"Persisted attempts file for workflow {workflow_id!r} contains a blank line."
            )
        try:
            payload = _loads_rejecting_duplicate_keys(line)
            records.append(RetryAttemptRecord.model_validate(payload))
        except (_DuplicateJSONKeyError, ValidationError, ValueError) as exc:
            raise CorruptedAttemptRecordError(
                f"Persisted attempt record for workflow {workflow_id!r} is malformed: {line!r}: "
                f"{exc}"
            ) from exc
    return records


def _append_attempt_record_unlocked(
    state_store: StateStore, workflow_id: str, record: RetryAttemptRecord
) -> None:
    """Append one line to `workflow_id`'s `attempts.jsonl`. Never called without the caller
    already holding `_held_attempts_lock` for the whole read-validate-append sequence — this
    function alone provides no mutual exclusion of its own.

    AUTO002-F06: an earlier revision wrote via plain buffered `Path.open("a").write(...)`, with
    no `fsync` of the file or its containing directory — unlike every other durable append in
    this codebase (`state_store.py`'s own `_append_jsonl_line`, and this module's own
    authorization persistence), a crash immediately after this call returned could lose the
    just-written `STARTED`/`COMPLETED` attempt record from the OS page cache, silently
    reintroducing the exact "attempt with no durable trace" hazard the `STARTED` reservation
    exists to prevent. Now uses the same durable primitives (`_write_all`, `os.fsync`,
    `_fsync_directory`) already imported and used elsewhere in this module.
    """
    payload = (record.model_dump_json() + "\n").encode("utf-8")
    with _confined_record_fd(
        state_store.state_directory, workflow_id, _ATTEMPTS_FILENAME, write=True
    ) as (fd, directory_fd):
        if fd is None or directory_fd is None:  # pragma: no cover
            raise StateStoreError("Failed to open attempts history for append.")
        _write_all(fd, payload)
        os.fsync(fd)
        os.fsync(directory_fd)


@contextmanager
def _held_attempts_lock(state_store: StateStore, workflow_id: str) -> Iterator[None]:
    """Hold a blocking, OS-level advisory lock (`fcntl.flock(LOCK_EX)`) on a separate, never-
    renamed lock file for the duration of the `with` block — the same pattern
    `_persist_authorization_record` uses (see `lock.py`'s own module docstring for why the lock
    file must never be the data file being read/written). Everything inside the block —
    reconstructing existing attempts, validating the next attempt number, appending the new
    record — runs as one atomic unit: two concurrent callers can never both observe the same
    "next" attempt number as free (requirement: "attempt numbering must be atomic").
    """
    lock_filename = f"{_ATTEMPTS_FILENAME}.lock"
    with _confined_record_fd(
        state_store.state_directory, workflow_id, lock_filename, write=True
    ) as (lock_fd, directory_fd):
        if lock_fd is None or directory_fd is None:  # pragma: no cover
            raise StateStoreError("Failed to open attempts lock.")
        os.fsync(directory_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _validate_attempt_sequence(numbers: list[int]) -> None:
    """Raise unless `numbers` are exactly `{1, 2, ..., len(numbers)}` — monotonic, contiguous,
    no duplicates, no gaps (requirement 12/13). Never reorders or repairs `numbers`.
    """
    seen: set[int] = set()
    for number in numbers:
        if number in seen:
            raise DuplicateAttemptNumberError(
                f"Attempt number {number} is recorded more than once."
            )
        seen.add(number)
    expected = set(range(1, len(numbers) + 1))
    if seen != expected:
        raise SkippedAttemptNumberError(
            f"Attempt numbers must be contiguous starting at 1; found {sorted(seen)}."
        )


def _scoped_attempts(
    workflow_id: str,
    stage_id: str,
    kind: AttemptKind,
    state_store: StateStore,
    *,
    states: frozenset[WorkflowState],
) -> list[RetryAttemptRecord]:
    """All persisted attempt records for exactly `(workflow_id, stage_id, kind)` whose own
    `state` field is one of `states` — the caller decides whether that means one specific state
    (`AttemptKind.INITIAL_EXECUTION`'s four states each have their own fully independent
    counter — the caller passes a singleton) or every state sharing one counter
    (`AttemptKind.REPAIR`'s is explicitly "per workflow, never per-gate," `FAILURE_RECOVERY.md`
    §1 — a completed repair following either a `VALIDATING`- or a `QA_RUNNING`-triggered
    `REPAIRING` entry counts against the same total, so the caller passes both).

    Validated for internal consistency before being returned: no `(attempt_number, phase)` pair
    repeated (a real duplicate — reading never silently collapses one via a `set`, unlike the
    design this replaces), no cross-workflow/stage contamination, the *distinct* attempt numbers
    present contiguous from 1, and no `COMPLETED` record for an attempt_number that has no
    matching `STARTED` reservation (`MissingAttemptReservationError` — defense in depth: normal
    writes already refuse to create this shape, but a read must still refuse to trust it if it's
    ever found on disk).
    """
    scoped: list[RetryAttemptRecord] = []
    seen_pairs: set[tuple[int, AttemptPhase]] = set()
    for record in _read_persisted_attempts(state_store, workflow_id):
        # AUTO002-F06: ownership is checked for *every* record in this workflow's own
        # attempts.jsonl before the kind/state filter below, never after. An earlier revision
        # filtered by kind/state first (`continue`-ing away any non-matching record) and only
        # then checked workflow_id/stage_id — so a foreign-workflow_id record whose kind or
        # state simply didn't match this particular query would be silently skipped and never
        # detected as corruption, even though its mere presence in this workflow's dedicated file
        # is itself evidence of cross-contamination regardless of which query happens to be
        # running right now.
        if record.workflow_id != workflow_id:
            raise InconsistentAttemptHistoryError(
                f"A persisted attempt record claims workflow_id {record.workflow_id!r}, but was "
                f"read as part of workflow {workflow_id!r}'s history."
            )
        if record.stage_id != stage_id:
            raise InconsistentAttemptHistoryError(
                f"A persisted attempt record for workflow {workflow_id!r} claims stage_id "
                f"{record.stage_id!r}, expected {stage_id!r}."
            )
        if record.kind is not kind or record.state not in states:
            continue
        pair = (record.attempt_number, record.phase)
        if pair in seen_pairs:
            raise DuplicateAttemptNumberError(
                f"{kind.value} attempt {record.attempt_number} {record.phase.value} is "
                f"recorded more than once for workflow {workflow_id!r}."
            )
        seen_pairs.add(pair)
        scoped.append(record)

    distinct_numbers = sorted({record.attempt_number for record in scoped})
    _validate_attempt_sequence(distinct_numbers)
    for number in distinct_numbers:
        phases = {record.phase for record in scoped if record.attempt_number == number}
        if phases == {AttemptPhase.COMPLETED}:
            raise MissingAttemptReservationError(
                f"{kind.value} attempt {number} (workflow {workflow_id!r}) has a COMPLETED "
                "record with no matching STARTED reservation."
            )
    return scoped


def has_unreconciled_initial_execution_attempt(
    workflow_id: str, stage_id: str, state: WorkflowState, state_store: StateStore
) -> bool:
    """Whether the latest initial-execution attempt for this scope was recorded as `STARTED`
    with no matching `COMPLETED` entry at the same `attempt_number` — the durable signature of a
    crash during execution, whose real-world outcome is unknown.

    Requirement 6: "no operation may be re-executed without reconciliation after uncertain
    execution." `evaluate_initial_execution_failure` refuses a `PROVEN_NO_SIDE_EFFECT` (blind,
    same-state retry) evaluation while this is `True` — that claim is definitionally
    contradicted by an attempt having actually started.
    """
    if state not in INITIAL_EXECUTION_RETRYABLE_STATES:
        raise NotRetryableStateError(
            f"{state.value!r} is not an initial-execution-retryable state."
        )
    scoped = _scoped_attempts(
        workflow_id,
        stage_id,
        AttemptKind.INITIAL_EXECUTION,
        state_store,
        states=frozenset({state}),
    )
    started = {a.attempt_number for a in scoped if a.phase is AttemptPhase.STARTED}
    completed = {a.attempt_number for a in scoped if a.phase is AttemptPhase.COMPLETED}
    return bool(started - completed)


def reconstruct_initial_execution_attempts(
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    state_store: StateStore,
) -> list[RetryAttemptRecord]:
    """Reconstruct every persisted, *completed* initial-execution attempt for
    `(workflow_id, stage_id, state)` from `workflow_id`'s dedicated `attempts.jsonl` — the sole
    source of truth; no in-memory counter exists anywhere in this module (requirement 7/8).
    Deterministic and idempotent: calling this twice against the same persisted history always
    returns the same result, including across a process restart with a freshly-constructed
    `StateStore`. `STARTED`-phase records (an attempt that began but has no recorded outcome
    yet) are excluded here — see `has_unreconciled_initial_execution_attempt` for that signal —
    so attempt-number contiguity/uniqueness is validated only across genuinely completed
    attempts, unaffected by an attempt still in flight. Always checked against
    `INITIAL_EXECUTION_ATTEMPT_LIMIT` — the fixed policy, never a caller-suppliable value.
    """
    if state not in INITIAL_EXECUTION_RETRYABLE_STATES:
        raise NotRetryableStateError(
            f"{state.value!r} is not an initial-execution-retryable state."
        )
    scoped = _scoped_attempts(
        workflow_id,
        stage_id,
        AttemptKind.INITIAL_EXECUTION,
        state_store,
        states=frozenset({state}),
    )
    attempts = sorted(
        (a for a in scoped if a.phase is AttemptPhase.COMPLETED),
        key=lambda attempt: attempt.attempt_number,
    )
    if len(attempts) > INITIAL_EXECUTION_ATTEMPT_LIMIT:
        raise AttemptLimitExceededError(
            f"Persisted history for workflow {workflow_id!r} already shows {len(attempts)} "
            f"{state.value} attempts, exceeding the fixed limit of "
            f"{INITIAL_EXECUTION_ATTEMPT_LIMIT}."
        )
    return attempts


def record_initial_execution_attempt_started(
    *,
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    attempt_number: int,
    state_store: StateStore,
    start_time: str,
) -> None:
    """Durably record that initial-execution attempt `attempt_number` has *begun* — before the
    operation's outcome is known — as its own dedicated `RetryAttemptRecord` event, appended to
    `workflow_id`'s `attempts.jsonl` under `_held_attempts_lock`.

    This is what makes an in-flight attempt detectable after a crash
    (`has_unreconciled_initial_execution_attempt`) instead of leaving no trace at all: without a
    durable "started" marker, a process that crashes mid-attempt (after any possible side effect,
    before recording the outcome) would look, on restart, exactly like an attempt that never
    happened — inviting a second, possibly-duplicate execution with no reconciliation
    (requirement 6). Calling this before `record_initial_execution_attempt` is now *required*,
    not merely recommended: `record_initial_execution_attempt` refuses to accept a completed
    outcome for an `attempt_number` that was never reserved here first
    (`MissingAttemptReservationError`) — "no execution API may proceed without that reservation."

    Rejects a duplicate `STARTED` for an already-reserved `attempt_number`
    (`DuplicateAttemptNumberError`), a number that would skip ahead
    (`SkippedAttemptNumberError`), a number requested while an *earlier* attempt for this scope
    is still unreconciled (`UnreconciledAttemptError` — a second attempt may not begin while a
    prior one's real-world outcome is unknown), and a number beyond
    `INITIAL_EXECUTION_ATTEMPT_LIMIT` (`AttemptLimitExceededError`). Bookkeeping only — performs
    no execution of its own, and records no command-execution detail (exit code, stdout/stderr) —
    a caller that also wants a genuine command-execution audit trail persists that separately via
    `state_store.record_command_execution` with the operation's own real command identity, never
    conflated with this reservation.
    """
    if state not in INITIAL_EXECUTION_RETRYABLE_STATES:
        raise NotRetryableStateError(
            f"{state.value!r} is not an initial-execution-retryable state."
        )
    if attempt_number < 1:
        raise InvalidAttemptNumberError(f"Attempt numbers are one-based; got {attempt_number}.")
    _reconstruct_workflow_for_evaluation(workflow_id, stage_id, state, state_store)

    with _held_attempts_lock(state_store, workflow_id):
        scoped = _scoped_attempts(
            workflow_id,
            stage_id,
            AttemptKind.INITIAL_EXECUTION,
            state_store,
            states=frozenset({state}),
        )
        started_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.STARTED}
        completed_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.COMPLETED}
        if attempt_number in started_numbers:
            # Checked before the general unreconciled-attempt guard below: re-reserving the
            # *same* attempt_number is a more specific, more diagnosable problem (an exact
            # duplicate) than the general "an earlier attempt is unreconciled" case, even though
            # an unreserved-and-unreconciled attempt_number is also technically true here.
            raise DuplicateAttemptNumberError(
                f"Attempt {attempt_number} STARTED was already recorded for {state.value} "
                f"(workflow {workflow_id!r})."
            )
        unreconciled = started_numbers - completed_numbers
        if unreconciled:
            raise UnreconciledAttemptError(
                f"Cannot start attempt {attempt_number} for {state.value}: attempt(s) "
                f"{sorted(unreconciled)} were started but never completed; reconciliation is "
                "required before another attempt may begin."
            )
        expected_next = len(completed_numbers) + 1
        if attempt_number > expected_next:
            raise SkippedAttemptNumberError(
                f"Attempt {attempt_number} would skip attempt {expected_next}; attempts must be "
                "recorded contiguously starting at 1."
            )
        if attempt_number > INITIAL_EXECUTION_ATTEMPT_LIMIT:
            raise AttemptLimitExceededError(
                f"Attempt {attempt_number} would exceed the fixed limit of "
                f"{INITIAL_EXECUTION_ATTEMPT_LIMIT}."
            )
        _append_attempt_record_unlocked(
            state_store,
            workflow_id,
            RetryAttemptRecord(
                workflow_id=workflow_id,
                stage_id=stage_id,
                state=state,
                kind=AttemptKind.INITIAL_EXECUTION,
                attempt_number=attempt_number,
                phase=AttemptPhase.STARTED,
                timestamp=start_time,
            ),
        )


def record_initial_execution_attempt(
    *,
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    attempt_number: int,
    state_store: StateStore,
    completion_time: str,
) -> None:
    """Persist one *completed* initial-execution attempt event, as its own dedicated
    `RetryAttemptRecord`, appended to `workflow_id`'s `attempts.jsonl` under
    `_held_attempts_lock`.

    Bookkeeping only — this function performs no execution of its own; the attempted operation
    happens entirely outside this module (a future `ImplementationAgent`/Skill/Provider,
    AUTO-003+). Requires a matching `STARTED` reservation for this exact `attempt_number` to
    already be persisted (`MissingAttemptReservationError` otherwise) and refuses a duplicate
    completion for an already-completed `attempt_number` (`DuplicateAttemptNumberError`) —
    numbering itself was already fixed at reservation time, so this call only ever finalizes an
    attempt that reservation already validated, never allocates a new number.
    """
    if state not in INITIAL_EXECUTION_RETRYABLE_STATES:
        raise NotRetryableStateError(
            f"{state.value!r} is not an initial-execution-retryable state."
        )
    _reconstruct_workflow_for_evaluation(workflow_id, stage_id, state, state_store)

    with _held_attempts_lock(state_store, workflow_id):
        scoped = _scoped_attempts(
            workflow_id,
            stage_id,
            AttemptKind.INITIAL_EXECUTION,
            state_store,
            states=frozenset({state}),
        )
        started_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.STARTED}
        completed_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.COMPLETED}
        if attempt_number not in started_numbers:
            raise MissingAttemptReservationError(
                f"Attempt {attempt_number} for {state.value} (workflow {workflow_id!r}) has no "
                "STARTED reservation; call record_initial_execution_attempt_started first."
            )
        if attempt_number in completed_numbers:
            raise DuplicateAttemptNumberError(
                f"Attempt {attempt_number} was already recorded as completed for {state.value} "
                f"(workflow {workflow_id!r})."
            )
        _append_attempt_record_unlocked(
            state_store,
            workflow_id,
            RetryAttemptRecord(
                workflow_id=workflow_id,
                stage_id=stage_id,
                state=state,
                kind=AttemptKind.INITIAL_EXECUTION,
                attempt_number=attempt_number,
                phase=AttemptPhase.COMPLETED,
                timestamp=completion_time,
            ),
        )


def has_unreconciled_repair_attempt(
    workflow_id: str, stage_id: str, state_store: StateStore
) -> bool:
    """Whether the latest repair attempt for this workflow was recorded as `STARTED` with no
    matching `COMPLETED` entry at the same `attempt_number` — the durable signature of a crash
    during a repair-provider invocation. Aggregated across both `VALIDATING` and `QA_RUNNING`
    (`FAILURE_RECOVERY.md` §1: "per workflow, never per-gate") — there is deliberately no
    per-state variant, since the repair counter this checks against is not per-state either.

    Unlike `AttemptKind.INITIAL_EXECUTION`, repair has no analogous "possible side effect, retry
    after reconciliation" sub-procedure: `FAILURE_RECOVERY.md` §1 states an unrecoverable
    repair-provider crash goes straight to `REPAIRING -> FAILED`, never a blind retry loop. This
    function exists so a caller — and `evaluate_repair_attempt` itself — can detect that
    condition before a further repair attempt is ever considered permitted.
    """
    scoped = _scoped_attempts(
        workflow_id, stage_id, AttemptKind.REPAIR, state_store, states=REPAIR_RETRYABLE_STATES
    )
    started = {a.attempt_number for a in scoped if a.phase is AttemptPhase.STARTED}
    completed = {a.attempt_number for a in scoped if a.phase is AttemptPhase.COMPLETED}
    return bool(started - completed)


def reconstruct_repair_attempts(
    workflow_id: str,
    stage_id: str,
    attempt_limit: int,
    state_store: StateStore,
) -> list[RetryAttemptRecord]:
    """Reconstruct every persisted, *completed* repair attempt for `(workflow_id, stage_id)` —
    aggregated across both `VALIDATING` and `QA_RUNNING` (no per-state variant; see
    `has_unreconciled_repair_attempt`) — from `workflow_id`'s dedicated `attempts.jsonl`, the
    sole source of truth (requirement 7/8), replacing the previous `StateTransitionRecord`-
    inferred count (counting `REPAIRING -> VALIDATING` transitions could not distinguish "no
    repair ran" from "a repair ran and crashed before returning to VALIDATING," and had no
    reservation step at all). `attempt_limit` remains caller-supplied, from
    `WorkflowConfig.repair_attempt_limit: Literal[3]` — unlike `INITIAL_EXECUTION_ATTEMPT_LIMIT`,
    this limit already has a config-schema anchor, so Finding 6's "hardcode it, there is nothing
    to anchor against" fix does not apply here.
    """
    scoped = _scoped_attempts(
        workflow_id, stage_id, AttemptKind.REPAIR, state_store, states=REPAIR_RETRYABLE_STATES
    )
    attempts = sorted(
        (a for a in scoped if a.phase is AttemptPhase.COMPLETED),
        key=lambda attempt: attempt.attempt_number,
    )
    if len(attempts) > attempt_limit:
        raise AttemptLimitExceededError(
            f"Persisted history for workflow {workflow_id!r} already shows {len(attempts)} "
            f"repair attempts, exceeding the configured limit of {attempt_limit}."
        )
    return attempts


def record_repair_attempt_started(
    *,
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    attempt_number: int,
    attempt_limit: int,
    state_store: StateStore,
    start_time: str,
) -> None:
    """Durably record that repair attempt `attempt_number` has *begun* — before the repair
    provider's outcome is known — as its own dedicated `RetryAttemptRecord` event, appended to
    `workflow_id`'s `attempts.jsonl` under `_held_attempts_lock`.

    Structurally identical to `record_initial_execution_attempt_started`, with a distinct
    `AttemptKind.REPAIR` counter kept fully independent of `AttemptKind.INITIAL_EXECUTION`'s
    (`_scoped_attempts` filters by `kind`, never conflating the two). `attempt_limit` is
    caller-supplied (`WorkflowConfig.repair_attempt_limit`), unlike the initial-execution
    function's fixed constant.
    """
    if state not in REPAIR_RETRYABLE_STATES:
        raise NotRetryableStateError(f"{state.value!r} is not a repair-retryable state.")
    if attempt_number < 1:
        raise InvalidAttemptNumberError(f"Attempt numbers are one-based; got {attempt_number}.")
    _reconstruct_workflow_expecting_repairing(workflow_id, stage_id, state_store)

    with _held_attempts_lock(state_store, workflow_id):
        scoped = _scoped_attempts(
            workflow_id, stage_id, AttemptKind.REPAIR, state_store, states=REPAIR_RETRYABLE_STATES
        )
        started_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.STARTED}
        completed_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.COMPLETED}
        if attempt_number in started_numbers:
            raise DuplicateAttemptNumberError(
                f"Repair attempt {attempt_number} STARTED was already recorded for "
                f"{state.value} (workflow {workflow_id!r})."
            )
        unreconciled = started_numbers - completed_numbers
        if unreconciled:
            raise UnreconciledAttemptError(
                f"Cannot start repair attempt {attempt_number} for {state.value}: attempt(s) "
                f"{sorted(unreconciled)} were started but never completed. FAILURE_RECOVERY.md "
                "§1 treats an unrecoverable repair-provider crash as REPAIRING -> FAILED; a "
                "blind further repair attempt is never permitted."
            )
        expected_next = len(completed_numbers) + 1
        if attempt_number > expected_next:
            raise SkippedAttemptNumberError(
                f"Repair attempt {attempt_number} would skip attempt {expected_next}; attempts "
                "must be recorded contiguously starting at 1."
            )
        if attempt_number > attempt_limit:
            raise AttemptLimitExceededError(
                f"Repair attempt {attempt_number} would exceed the configured limit of "
                f"{attempt_limit}."
            )
        _append_attempt_record_unlocked(
            state_store,
            workflow_id,
            RetryAttemptRecord(
                workflow_id=workflow_id,
                stage_id=stage_id,
                state=state,
                kind=AttemptKind.REPAIR,
                attempt_number=attempt_number,
                phase=AttemptPhase.STARTED,
                timestamp=start_time,
            ),
        )


def record_repair_attempt(
    *,
    workflow_id: str,
    stage_id: str,
    state: WorkflowState,
    attempt_number: int,
    state_store: StateStore,
    completion_time: str,
) -> None:
    """Persist one *completed* repair attempt event, as its own dedicated `RetryAttemptRecord`,
    appended to `workflow_id`'s `attempts.jsonl` under `_held_attempts_lock`.

    Structurally identical to `record_initial_execution_attempt`: requires a matching `STARTED`
    reservation for this exact `attempt_number` (`MissingAttemptReservationError` otherwise) and
    refuses a duplicate completion (`DuplicateAttemptNumberError`).
    """
    if state not in REPAIR_RETRYABLE_STATES:
        raise NotRetryableStateError(f"{state.value!r} is not a repair-retryable state.")
    _reconstruct_workflow_expecting_repairing(workflow_id, stage_id, state_store)

    with _held_attempts_lock(state_store, workflow_id):
        scoped = _scoped_attempts(
            workflow_id, stage_id, AttemptKind.REPAIR, state_store, states=REPAIR_RETRYABLE_STATES
        )
        started_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.STARTED}
        completed_numbers = {a.attempt_number for a in scoped if a.phase is AttemptPhase.COMPLETED}
        if attempt_number not in started_numbers:
            raise MissingAttemptReservationError(
                f"Repair attempt {attempt_number} for {state.value} (workflow {workflow_id!r}) "
                "has no STARTED reservation; call record_repair_attempt_started first."
            )
        if attempt_number in completed_numbers:
            raise DuplicateAttemptNumberError(
                f"Repair attempt {attempt_number} was already recorded as completed for "
                f"{state.value} (workflow {workflow_id!r})."
            )
        _append_attempt_record_unlocked(
            state_store,
            workflow_id,
            RetryAttemptRecord(
                workflow_id=workflow_id,
                stage_id=stage_id,
                state=state,
                kind=AttemptKind.REPAIR,
                attempt_number=attempt_number,
                phase=AttemptPhase.COMPLETED,
                timestamp=completion_time,
            ),
        )


def _check_evidence_scope(
    evidence: ReconciliationEvidence,
    *,
    workflow_id: str,
    repository_identity: str,
    repository_path: str,
    stage_id: str,
) -> None:
    """Raise `EvidenceScopeMismatchError` unless `evidence`'s own binding fields exactly match
    the scope this evaluation was actually called for — evidence collected for one workflow,
    repository, or stage may never be silently accepted for another.
    """
    for field, expected in (
        ("workflow_id", workflow_id),
        ("repository_identity", repository_identity),
        ("repository_path", repository_path),
        ("stage_id", stage_id),
    ):
        actual = getattr(evidence, field)
        if actual != expected:
            raise EvidenceScopeMismatchError(field, expected, actual)


def evaluate_initial_execution_failure(
    *,
    workflow_id: str,
    repository_identity: str,
    repository_path: str,
    stage_id: str,
    state: WorkflowState,
    state_store: StateStore,
    failure_kind: InitialExecutionFailureKind,
    evidence: ReconciliationEvidence | None = None,
    allowed_changed_paths: list[str] | None = None,
    forbidden_changed_paths: list[str] | None = None,
) -> RetryReconciliationResult:
    """Decide the outcome of a first-time side-effecting operation's failure at `state`
    (`IMPLEMENTING`, `READY_TO_COMMIT`, `COMMITTED`, or `PUSHED`) — WORKFLOW_STATES.md §5a.

    `failure_kind=PROVEN_NO_SIDE_EFFECT` (item 1): a bounded, same-state retry decision,
    identical in shape to `evaluate_repair_attempt`'s but never producing a `REPAIRING`
    recommendation (`next_allowed_state=None` — item 1 is explicitly "not a workflow-state
    transition").

    `failure_kind=POSSIBLE_SIDE_EFFECT` (items 2-6): requires `evidence`
    (`MissingReconciliationEvidenceError` otherwise — never retried blindly), bound to exactly
    this call's `workflow_id`/`repository_identity`/`repository_path`/`stage_id`
    (`EvidenceScopeMismatchError` otherwise) and, once confirmed, carrying the one typed
    evidence variant this specific `state` requires (`EvidenceOperationMismatchError`
    otherwise — `ReconciliationEvidence` itself already enforces internal expected/observed
    consistency against the claimed `side_effect_succeeded`). Unconfirmed evidence yields
    `RECONCILIATION_REQUIRED`; confirmed success yields `RECONCILIATION_SUCCESSFUL` advancing to
    the documented forward edge; a confirmed, recoverable inconsistency (`IMPLEMENTING` only, per
    FAILURE_RECOVERY.md §1a) yields `RECONCILIATION_FAILED` recommending `VALIDATING` — item 4
    explicitly adds no new `IMPLEMENTING -> REPAIRING` edge, so validation's own existing
    `VALIDATING -> REPAIRING` gate is what actually engages repair, not this function; everything
    else yields `UNRECOVERABLE_FAILURE` recommending `FAILED`.

    If the latest attempt for this scope was recorded as started but never completed
    (`has_unreconciled_initial_execution_attempt`), a `PROVEN_NO_SIDE_EFFECT` evaluation is
    refused outright (`UnreconciledAttemptError`) — that claim is contradicted by the evidence
    that an attempt actually began; `POSSIBLE_SIDE_EFFECT` remains available and is the correct
    path for this scope (requirement 6).
    """
    if state not in INITIAL_EXECUTION_RETRYABLE_STATES:
        raise NotRetryableStateError(
            f"{state.value!r} is not an initial-execution-retryable state; only "
            f"{sorted(s.value for s in INITIAL_EXECUTION_RETRYABLE_STATES)} carry the §5a "
            "same-state retry/reconciliation policy."
        )
    _reconstruct_workflow_for_evaluation(workflow_id, stage_id, state, state_store)
    attempts = reconstruct_initial_execution_attempts(workflow_id, stage_id, state, state_store)
    attempt_count = len(attempts)

    if failure_kind is InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT:
        if has_unreconciled_initial_execution_attempt(workflow_id, stage_id, state, state_store):
            raise UnreconciledAttemptError(
                f"An initial-execution attempt for {state.value} was started but never recorded "
                "as completed; its outcome is unknown, so a blind retry (PROVEN_NO_SIDE_EFFECT) "
                "is refused until reconciliation resolves it (WORKFLOW_STATES.md §5a item 2)."
            )
        return _evaluate_bounded_attempt(
            state=state,
            attempt_count=attempt_count,
            attempt_limit=INITIAL_EXECUTION_ATTEMPT_LIMIT,
            next_state_if_allowed=None,
            operation_label=f"{state.value} same-state retry",
        )

    if evidence is None:
        raise MissingReconciliationEvidenceError(
            f"Reconciliation evidence is required for {state.value} once a side effect may have "
            "occurred (WORKFLOW_STATES.md §5a item 2); it is never retried blindly."
        )
    _check_evidence_scope(
        evidence,
        workflow_id=workflow_id,
        repository_identity=repository_identity,
        repository_path=repository_path,
        stage_id=stage_id,
    )
    if evidence.side_effect_confirmed:
        expected_evidence_type = _EVIDENCE_TYPE_BY_STATE[state]
        if type(evidence.evidence) is not expected_evidence_type:
            raise EvidenceOperationMismatchError(
                f"{state.value} requires {expected_evidence_type.__name__} evidence, got "
                f"{type(evidence.evidence).__name__}."
            )
        _check_evidence_internal_consistency(evidence)
        assert evidence.evidence is not None  # enforced by ReconciliationEvidence._validate_shape
        authorization_record = _load_authorization_record(state_store, workflow_id)
        if authorization_record is None:
            raise MissingAuthorizationRecordError(
                f"Workflow {workflow_id!r} has no authorization record for evidence binding."
            )
        expected_attempt_number = 0
        if state is WorkflowState.IMPLEMENTING:
            scoped_attempts = _scoped_attempts(
                workflow_id,
                stage_id,
                AttemptKind.INITIAL_EXECUTION,
                state_store,
                states=frozenset({WorkflowState.IMPLEMENTING}),
            )
            if not scoped_attempts:
                raise LocalEvidenceVerificationFailedError(
                    "IMPLEMENTING reconciliation has no persisted attempt reservation to bind."
                )
            expected_attempt_number = max(item.attempt_number for item in scoped_attempts)
        _verify_evidence_locally(
            evidence.evidence,
            repository_path=Path(repository_path),
            audit_directory=state_store.audit_directory,
            workflow_id=workflow_id,
            stage_id=stage_id,
            state=state,
            authorization_record=authorization_record,
            expected_attempt_number=expected_attempt_number,
            allowed_changed_paths=allowed_changed_paths,
            forbidden_changed_paths=forbidden_changed_paths,
        )

    if not evidence.side_effect_confirmed:
        return _build_result(
            outcome=RetryOutcome.RECONCILIATION_REQUIRED,
            current_state=state,
            expected_state_or_operation=f"confirm {state.value} side effect",
            observed_evidence="Side effect outcome is not yet confirmed.",
            attempt_count=attempt_count,
            attempt_limit=INITIAL_EXECUTION_ATTEMPT_LIMIT,
            next_allowed_state=None,
            reason="Never retried blindly once a side effect may have occurred (§5a item 2).",
        )

    if evidence.side_effect_succeeded:
        forward_state = _FORWARD_EDGE_AFTER_RECONCILIATION[state]
        return _build_result(
            outcome=RetryOutcome.RECONCILIATION_SUCCESSFUL,
            current_state=state,
            expected_state_or_operation=f"advance to {forward_state.value}",
            observed_evidence="Reconciliation confirmed the side effect already succeeded.",
            attempt_count=attempt_count,
            attempt_limit=INITIAL_EXECUTION_ATTEMPT_LIMIT,
            next_allowed_state=forward_state,
            reason="Side effect already succeeded; advancing without duplicating it (§5a item 3).",
        )

    if evidence.recoverable and state is not WorkflowState.IMPLEMENTING:
        raise InconsistentAttemptHistoryError(
            "'recoverable' evidence only ever applies to IMPLEMENTING (FAILURE_RECOVERY.md §1a: "
            f"'this condition does not apply' to {state.value}), but was set here."
        )

    if state is WorkflowState.IMPLEMENTING and evidence.recoverable:
        # WORKFLOW_STATES.md §5a item 4, verbatim: "no new IMPLEMENTING -> REPAIRING edge is
        # added — it proceeds forward via the existing IMPLEMENTING -> VALIDATING edge, and
        # deterministic validation's own existing VALIDATING -> REPAIRING edge is what actually
        # engages the repair cycle if a real problem is found." The recommended next state is
        # therefore VALIDATING, not REPAIRING — identical to the confirmed-success case, since
        # letting validation itself judge correctness *is* the recovery mechanism here.
        return _build_result(
            outcome=RetryOutcome.RECONCILIATION_FAILED,
            current_state=state,
            expected_state_or_operation="advance to VALIDATING (repair engages there if needed)",
            observed_evidence="Reconciliation found an inconsistency judged safely repairable.",
            attempt_count=attempt_count,
            attempt_limit=INITIAL_EXECUTION_ATTEMPT_LIMIT,
            next_allowed_state=WorkflowState.VALIDATING,
            reason=(
                "A recoverable IMPLEMENTING inconsistency proceeds forward via the existing "
                "IMPLEMENTING -> VALIDATING edge; no new IMPLEMENTING -> REPAIRING edge exists "
                "(WORKFLOW_STATES.md §5a item 4)."
            ),
        )

    return _build_result(
        outcome=RetryOutcome.UNRECOVERABLE_FAILURE,
        current_state=state,
        expected_state_or_operation="terminate",
        observed_evidence=(
            "Reconciliation found the side effect did not succeed and is not safely repairable."
        ),
        attempt_count=attempt_count,
        attempt_limit=INITIAL_EXECUTION_ATTEMPT_LIMIT,
        next_allowed_state=WorkflowState.FAILED,
        reason="Unrecoverable or indeterminate failure (§5a item 5).",
    )


# --------------------------------------------------------------------------------------------
# WorkflowSession — the single orchestrator-owned runtime facade (ARCHITECTURE.md §2, §5).
#
# Every other public name in this module (WorkflowStateMachine, RepositoryLock, StateStore,
# authorize(), resume_workflow(), evaluate_repair_attempt(), record_*_attempt*(),
# evaluate_initial_execution_failure(), ...) remains a real, independently-testable primitive —
# this section adds nothing to their behavior and deprecates none of them; a lower-level caller
# (including this module's own test suite) may still use them directly. WorkflowSession is the
# one *composed* object an external caller (the not-yet-implemented Orchestrator/CLI layer,
# AUTO-003+) is meant to hold instead: the only public entry point that owns a workflow's
# RepositoryLock, StateStore, and WorkflowStateMachine together, for that workflow's entire active
# lifetime, so a caller never separately assembles those three and can never hold one without the
# other two already correctly wired alongside it.
#
# WorkflowSession never exposes its held WorkflowStateMachine, RepositoryLock, or StateStore as a
# public attribute, property, or return value — a caller can observe *state* (`.state`,
# `.is_terminal`, `.transitions`, `.lock_is_held`) but can never reach a mutable runtime object and
# bypass this class's own validate-persist-apply-release discipline. Every mutating operation this
# module offers elsewhere as a free function taking `state_store=`/`lock=`/`machine=` directly is
# available here as a same-named instance method that supplies its own held state instead.
# --------------------------------------------------------------------------------------------


class WorkflowSessionError(Exception):
    """Base error for `WorkflowSession` construction/lifecycle failures not already covered by a
    more specific error re-raised, unwrapped, from the primitive a given method wraps
    (`AuthorizationError`, `ResumeError`, `RetryError`, and `LockError`/`StateStoreError`
    subclasses all still propagate directly — WorkflowSession adds no second, redundant error
    hierarchy on top of them).
    """


class WorkflowIdReuseError(WorkflowSessionError):
    """Raised by `WorkflowSession.start()` when durable transition history already exists for the
    requested `workflow_id`.

    A `workflow_id` is single-use for a *complete* first authorization attempt: once
    `transitions.jsonl` holds even one record — successful authorization, a subsequent forward
    transition, or a terminal `FAILED`/`CANCELLED` — that identity is retired, whatever state it
    reached. Restarting the same stage after failure or cancellation always requires a fresh
    `workflow_id` and fresh human authorization (`WORKFLOW_STATES.md` §8), never a second
    `CREATED -> AUTHORIZED` record appended to the same history. The one narrow exception this
    error does *not* cover is a genuinely incomplete first authorization transaction — a crash
    between persisting the `AuthorizationRecord` and appending its `StateTransitionRecord` — which
    has zero persisted transitions and is recovered by `authorize()`'s own idempotent-identical-
    record handling, not by this check (this check only ever fires when at least one transition is
    already durably recorded).
    """


class WorkflowSession:
    """The single, orchestrator-owned runtime facade for one workflow instance.

    Construct only via `WorkflowSession.start(...)` (a fresh authorization) or
    `WorkflowSession.resume(...)` (re-attaching to an in-flight, persisted workflow) — never by
    calling `WorkflowSession(...)` directly, which raises `WorkflowSessionError`
    unconditionally, the same "no bare construction" discipline `WorkflowStateMachine` already
    applies to `AUTHORIZED`.
    """

    def __init__(
        self,
        *,
        resumed: ResumedWorkflow,
        repository_path: str,
        repair_attempt_limit: int,
        allowed_changed_paths: list[str] | None = None,
        forbidden_changed_paths: list[str] | None = None,
        _token: _InternalConstructionToken | None = None,
    ) -> None:
        if _token is not _INTERNAL_TOKEN:
            raise WorkflowSessionError(
                "WorkflowSession may not be constructed directly; use WorkflowSession.start(...) "
                "for a fresh authorization or WorkflowSession.resume(...) to re-attach to an "
                "in-flight, persisted workflow."
            )
        self._resumed = resumed
        self._repository_path = repository_path
        # Bound once, at construction, from `WorkflowConfig.repair_attempt_limit` (schema-fixed
        # `Literal[3]`) — never a caller-suppliable method parameter. This is what actually closes
        # the finding: every repair-attempt method below reads this stored value instead of
        # accepting an `attempt_limit` argument, so no caller of the supported `WorkflowSession`
        # facade can request evaluation, reservation, or completion against any other limit.
        self._repair_attempt_limit = repair_attempt_limit
        self._allowed_changed_paths = list(allowed_changed_paths or [])
        self._forbidden_changed_paths = list(forbidden_changed_paths or [])

    # -- Construction -------------------------------------------------------------------------

    @classmethod
    def start(
        cls,
        config: WorkflowConfig,
        *,
        workflow_id: str,
        stage_id: str,
        stage_contract_path: str,
        stage_contract_hash: str,
        planned_stage_branch: str,
        baseline_commit_sha: str,
        authorized_at: str,
        engine_version: str,
        authorized_by: str | None = None,
    ) -> "WorkflowSession":
        """Acquire the per-target-repository lock *first*, then capture and persist a fresh
        authorization (`authorize()`) — in that order, never the reverse.

        `ARCHITECTURE.md` §5: "A second `authorize` call against a locked target repository is
        refused by the Orchestrator before any target-repository mutation occurs." `authorize()`
        itself has no notion of a repository lock (it only needs a `StateStore`), so this ordering
        is what actually makes that guarantee true for `WorkflowSession`: two concurrent
        `WorkflowSession.start()` calls for the same repository (necessarily different
        `workflow_id`s, since a repeat of the same `workflow_id` would instead hit `authorize()`'s
        own single-use `InvalidTransitionError`) must never both succeed in persisting an
        `AuthorizationRecord` — acquiring the lock before calling `authorize()` means the loser of
        the race fails on `LockContentionError` before writing anything at all, never after.

        Every `HUMAN_AUTHORIZATION_MODEL.md` §2 binding field is sourced from either `config`
        (repository identity/path, baseline branch) or a caller-supplied parameter — this method
        builds the `AuthorizationContext`/`AuthorizationRecord` itself so a caller of
        `WorkflowSession` never constructs either directly, and never touches a `StateStore` or
        `RepositoryLock` at all: both are built here, from `config` alone, via the same
        `StateStore.for_config`/`RepositoryLock.for_config` constructors a lower-level caller
        would otherwise have to invoke itself.

        Before authorizing, durable transition history for `workflow_id` is inspected
        (`WorkflowIdReuseError` if any already exists): a `workflow_id` is single-use for a
        complete first authorization, whatever state it reached (`AUTHORIZED`, any later forward
        state, or terminal `FAILED`/`CANCELLED`) — restarting a stage after failure or
        cancellation always requires a fresh `workflow_id` and fresh human authorization
        (`WORKFLOW_STATES.md` §8), never a second `CREATED -> AUTHORIZED` record appended to
        existing history. The one case this does *not* reject is a genuinely incomplete first
        authorization transaction (a crash between persisting the `AuthorizationRecord` and
        appending its `StateTransitionRecord`, leaving zero persisted transitions) — `authorize()`
        itself already recovers that safely via its own idempotent-identical-record handling.

        This inspection happens *twice*, never once:

        1. A read-only precheck runs before `lock.acquire()` is ever called. `read_transitions`
           only reads `transitions.jsonl`; it never touches the lock file. A clearly reused
           `workflow_id` — the overwhelmingly common case, since history for it was necessarily
           written by some earlier, already-completed `start()` — is therefore rejected without
           ever acquiring, truncating, or rewriting `.agentos/workflow.lock`: every existing
           authorization, transition, audit, and lock byte is left completely untouched. (Every
           `RepositoryLock.acquire()` call unconditionally `ftruncate`s and rewrites the lock
           file's metadata, even when the calling process already knows — or is about to
           discover — that it has no legitimate reason to hold the lock; skipping `acquire()`
           entirely for an already-known reuse is what actually prevents that rewrite, not
           anything `acquire()` itself does differently.)
        2. Only if the precheck finds nothing is the lock acquired at all. History is then
           re-read a second time, now while holding the lock and strictly before `authorize()`
           ever persists anything — closing the race where a concurrent `start()` for the same
           `workflow_id` completes its own authorization in the window between this call's
           precheck and its lock acquisition. If the recheck now finds history (it was written by
           that concurrent winner), this call releases the lock and rejects exactly as the
           precheck would have, and — because this happens before `authorize()` is ever
           called — still writes nothing of its own.

        Either rejection leaves `state_store.read_transitions(workflow_id)` and every persisted
        byte for this `workflow_id` exactly as the reuse rejection found it; only the recheck path
        (having acquired the lock to reach that point) needs `lock.release()`, which happens
        before `WorkflowIdReuseError` propagates.

        On any failure — lock contention, workflow-id reuse, authorization scope mismatch, or
        persistence failure — no `WorkflowSession` is returned and no lock is left held: a failed
        `lock.acquire()` never held it in the first place, and any failure after that (inside the
        `try` below) releases the lock before propagating — `authorize()` itself separately
        guarantees `machine.state` is left unchanged on its own failure.
        """
        context = AuthorizationContext(
            workflow_id=workflow_id,
            repository_identity=config.repository_identity,
            stage_id=stage_id,
            planned_stage_branch=planned_stage_branch,
            baseline_branch=config.baseline_branch,
        )
        record = AuthorizationRecord(
            workflow_id=workflow_id,
            repository_identity=config.repository_identity,
            repository_path=str(config.repository_path),
            stage_id=stage_id,
            stage_contract_path=stage_contract_path,
            stage_contract_hash=stage_contract_hash,
            baseline_branch=config.baseline_branch,
            baseline_commit_sha=baseline_commit_sha,
            planned_stage_branch=planned_stage_branch,
            authorized_at=authorized_at,
            authorized_by=authorized_by,
            engine_version=engine_version,
        )
        state_store = StateStore.for_config(config)
        lock = RepositoryLock.for_config(config, workflow_id=workflow_id)

        def _reuse_error() -> WorkflowIdReuseError:
            return WorkflowIdReuseError(
                f"workflow_id {workflow_id!r} already has persisted transition history; a "
                "workflow_id is single-use for a complete first authorization. Restart this "
                "stage with a fresh workflow_id and fresh human authorization."
            )

        # Step 1: read-only precheck, strictly before lock.acquire() — see docstring above.
        if state_store.read_transitions(workflow_id):
            raise _reuse_error()

        lock.acquire()
        try:
            # Step 2: recheck while holding the lock, before authorize() persists anything —
            # closes the race window between the precheck above and this acquisition.
            if state_store.read_transitions(workflow_id):
                raise _reuse_error()
            machine = WorkflowStateMachine()
            authorize(machine, context, record, state_store=state_store)
            transitions = state_store.read_transitions(workflow_id)
        except BaseException:
            lock.release()
            raise
        resumed = ResumedWorkflow(
            machine=machine,
            transitions=transitions,
            lock=lock,
            state_store=state_store,
            repository_path=str(config.repository_path.resolve()),
        )
        return cls(
            resumed=resumed,
            repository_path=str(config.repository_path),
            repair_attempt_limit=config.repair_attempt_limit,
            allowed_changed_paths=config.allowed_changed_paths,
            forbidden_changed_paths=config.forbidden_changed_paths,
            _token=_INTERNAL_TOKEN,
        )

    @classmethod
    def resume(
        cls,
        config: WorkflowConfig,
        *,
        workflow_id: str,
        stage_id: str,
        planned_stage_branch: str,
        current_binding: CurrentAuthorizationBinding | None = None,
        _observer: ResumeObserver | None = None,
    ) -> "WorkflowSession":
        """Re-attach to an already-authorized, in-flight workflow (`resume_workflow`).

        Builds the same `AuthorizationContext` shape `start()` does, and the same
        `StateStore`/`RepositoryLock` pair from `config` alone — a caller of `WorkflowSession`
        never constructs a `StateStore` or `RepositoryLock` directly for resume either. Every
        `ResumeError`/`AuthorizationError` subtype `resume_workflow` itself can raise propagates
        unwrapped (`RepositoryLockUnavailableError`, `RepositoryLockIdentityMismatchError`,
        `MissingPersistedStateError`, `CorruptedHistoryError`, `InconsistentHistoryError`,
        `WorkflowAlreadyTerminalError`, `AuthorizationScopeMismatchError`,
        `MissingAuthorizationRecordError`, `AuthorizationBindingDriftError`) — `resume_workflow`
        already guarantees the lock is released before any of these propagate.

        `current_binding` is a deprecated, ignored compatibility parameter. Live authority comes
        from the internally constructed `LocalResumeObserver`; `_observer` is an underscore-
        prefixed raw-facts seam for tests and cannot return an authorization verdict.
        """
        context = AuthorizationContext(
            workflow_id=workflow_id,
            repository_identity=config.repository_identity,
            stage_id=stage_id,
            planned_stage_branch=planned_stage_branch,
            baseline_branch=config.baseline_branch,
        )
        state_store = StateStore.for_config(config)
        lock = RepositoryLock.for_config(config, workflow_id=workflow_id)
        resumed = resume_workflow(
            context,
            state_store=state_store,
            lock=lock,
            current_binding=None,
            config=config,
            _observer=_observer,
        )
        return cls(
            resumed=resumed,
            repository_path=str(config.repository_path.resolve()),
            repair_attempt_limit=config.repair_attempt_limit,
            allowed_changed_paths=config.allowed_changed_paths,
            forbidden_changed_paths=config.forbidden_changed_paths,
            _token=_INTERNAL_TOKEN,
        )

    # -- Observation only: no method or property here ever returns a mutable runtime object ---

    @property
    def workflow_id(self) -> str:
        return self._resumed.transitions[-1].workflow_id

    @property
    def stage_id(self) -> str:
        return self._resumed.transitions[-1].stage_id

    @property
    def repository_identity(self) -> str:
        return self._resumed.transitions[-1].target_repository

    @property
    def state(self) -> WorkflowState:
        return self._resumed.machine.state

    @property
    def is_terminal(self) -> bool:
        return self._resumed.machine.is_terminal

    @property
    def transitions(self) -> tuple[StateTransitionRecord, ...]:
        """A read-only snapshot of this workflow's complete transition history so far — a tuple,
        never the internal list `ResumedWorkflow` itself appends to in place, so a caller can
        inspect history but can never mutate the session's own held record of it through this
        property.
        """
        return tuple(self._resumed.transitions)

    @property
    def lock_is_held(self) -> bool:
        """Diagnostic only (mirrors `RepositoryLock.is_held`) — never returns the lock object
        itself, so a caller can check exclusivity without ever being handed something that could
        release it directly.
        """
        return self._resumed.lock.is_held

    # -- Mutating operations: each delegates to the same module-level primitive already defined
    # above, supplying this session's own held workflow_id/stage_id/repository identity/
    # state_store automatically — a caller of WorkflowSession never passes any of those itself. --

    def transition_to(
        self, to_state: WorkflowState, *, actor: str, gate_evidence_ref: str | None = None
    ) -> WorkflowState:
        """See `ResumedWorkflow.transition_to`: validates, durably persists, then applies —
        never the reverse order — and releases the held lock automatically on reaching a
        terminal state.
        """
        return self._resumed.transition_to(
            to_state, actor=actor, gate_evidence_ref=gate_evidence_ref
        )

    def release_lock_if_terminal(self) -> bool:
        return self._resumed.release_lock_if_terminal()

    def evaluate_repair_attempt(self, state: WorkflowState) -> RetryReconciliationResult:
        """Evaluate against this session's own fixed `repair_attempt_limit`
        (`WorkflowConfig.repair_attempt_limit: Literal[3]`, bound once at construction) — this
        method accepts no `attempt_limit` argument, so no caller of the supported
        `WorkflowSession` facade can request evaluation against any other limit.
        """
        return evaluate_repair_attempt(
            workflow_id=self.workflow_id,
            stage_id=self.stage_id,
            state=state,
            attempt_limit=self._repair_attempt_limit,
            state_store=self._resumed.state_store,
        )

    def has_unreconciled_repair_attempt(self) -> bool:
        return has_unreconciled_repair_attempt(
            self.workflow_id, self.stage_id, self._resumed.state_store
        )

    def reconstruct_repair_attempts(self) -> list[RetryAttemptRecord]:
        """Reconstruct against this session's own fixed `repair_attempt_limit` — see
        `evaluate_repair_attempt`; no `attempt_limit` argument is accepted here either.
        """
        return reconstruct_repair_attempts(
            self.workflow_id, self.stage_id, self._repair_attempt_limit, self._resumed.state_store
        )

    def record_repair_attempt_started(
        self, state: WorkflowState, *, attempt_number: int, start_time: str
    ) -> None:
        """Reserve against this session's own fixed `repair_attempt_limit` — see
        `evaluate_repair_attempt`; no `attempt_limit` argument is accepted here either, so a
        caller can never reserve, and therefore never later complete, a fourth repair attempt.
        """
        record_repair_attempt_started(
            workflow_id=self.workflow_id,
            stage_id=self.stage_id,
            state=state,
            attempt_number=attempt_number,
            attempt_limit=self._repair_attempt_limit,
            state_store=self._resumed.state_store,
            start_time=start_time,
        )

    def record_repair_attempt(
        self, state: WorkflowState, *, attempt_number: int, completion_time: str
    ) -> None:
        record_repair_attempt(
            workflow_id=self.workflow_id,
            stage_id=self.stage_id,
            state=state,
            attempt_number=attempt_number,
            state_store=self._resumed.state_store,
            completion_time=completion_time,
        )

    def has_unreconciled_initial_execution_attempt(self, state: WorkflowState) -> bool:
        return has_unreconciled_initial_execution_attempt(
            self.workflow_id, self.stage_id, state, self._resumed.state_store
        )

    def reconstruct_initial_execution_attempts(
        self, state: WorkflowState
    ) -> list[RetryAttemptRecord]:
        return reconstruct_initial_execution_attempts(
            self.workflow_id, self.stage_id, state, self._resumed.state_store
        )

    def record_initial_execution_attempt_started(
        self, state: WorkflowState, *, attempt_number: int, start_time: str
    ) -> None:
        record_initial_execution_attempt_started(
            workflow_id=self.workflow_id,
            stage_id=self.stage_id,
            state=state,
            attempt_number=attempt_number,
            state_store=self._resumed.state_store,
            start_time=start_time,
        )

    def record_initial_execution_attempt(
        self, state: WorkflowState, *, attempt_number: int, completion_time: str
    ) -> None:
        record_initial_execution_attempt(
            workflow_id=self.workflow_id,
            stage_id=self.stage_id,
            state=state,
            attempt_number=attempt_number,
            state_store=self._resumed.state_store,
            completion_time=completion_time,
        )

    def evaluate_initial_execution_failure(
        self,
        state: WorkflowState,
        *,
        failure_kind: InitialExecutionFailureKind,
        evidence: ReconciliationEvidence | None = None,
    ) -> RetryReconciliationResult:
        return evaluate_initial_execution_failure(
            workflow_id=self.workflow_id,
            repository_identity=self.repository_identity,
            repository_path=self._repository_path,
            stage_id=self.stage_id,
            state=state,
            state_store=self._resumed.state_store,
            failure_kind=failure_kind,
            evidence=evidence,
            allowed_changed_paths=self._allowed_changed_paths,
            forbidden_changed_paths=self._forbidden_changed_paths,
        )

    # -- Guaranteed lock release on exit, exception or not (ARCHITECTURE.md §5) ---------------

    def __enter__(self) -> "WorkflowSession":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self._resumed.lock.release()
