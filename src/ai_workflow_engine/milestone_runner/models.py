"""Typed vocabulary for the AUTO-016 integrated milestone runner.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) sections 7
(relationship to the canonical state machine), 8 (package and module surface), 10 (run state
machine), 11 (durable state model), 14 (milestone plan format), 17 (provider failure taxonomy),
19 (the five independent counters and four append-only recovery ledgers) and 22 (invariants 11,
12 and 18).

This module is pure typed data plus pure functions. It opens no file, spawns no process,
resolves no path against the filesystem and touches no network; every value it validates is
handed to it by a caller that already read it. It imports no provider, no `subprocess`, no Git
primitive and nothing from `agentos_workflow` (section 22 invariant 6).

**No `WorkflowState` is defined, extended or referenced here.** Section 7 is explicit that
AUTO-016 owns no runtime workflow state: :class:`RunStatus` is a runner-local `StrEnum`, exactly
as `ApprovalStatus`, `ImplementerPhase` and `MergeCloseoutPhase` already are, and neither
`WorkflowState`'s nineteen members nor `ALLOWED_TRANSITIONS`' thirty-seven edges gain anything
from this package.

Every model inherits :class:`MilestoneRunnerModel`, which mirrors the discipline
`successor_planning/models.py` established: `extra="forbid"` plus `strict=True`, declared once
because `model_config` does not cascade into nested models in Pydantic v2. An unrecognized field
in a plan, a state document or a parsed provider result is therefore a schema error rather than
silently ignored input (section 11).

Several invariants are enforced by making their violation unrepresentable rather than by a
runtime check somewhere downstream (section 22):

* invariant 11 (budget integrity) -- the five counters of section 19 are five distinct
  non-negative integer fields on :class:`RunRecord`; no code path can alias one onto another,
  and a recovery ledger entry may only name a counter that actually exists;
* invariant 12 (scope integrity) -- every path-shaped field is normalized through
  :func:`normalize_repository_path`, which refuses an absolute or traversal-shaped value outright
  instead of resolving it;
* invariant 18 (no fabricated success) -- :class:`VerificationResult` recomputes its own
  ``passed`` flag from the exit code and the timeout flag, so a record claiming a pass after a
  timeout or a non-zero exit cannot be constructed at all.
"""

import hashlib
import json
import re
import unicodedata
from enum import Enum, StrEnum
from typing import Any, cast

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from ai_workflow_engine.models import StrictModel


class MilestoneRunnerModel(StrictModel):
    """Base for every milestone-runner model: closed schema plus exact-type fields.

    `extra="forbid"` comes from `StrictModel` unchanged; this base never modifies
    `StrictModel` itself, which is shared with unrelated configuration models.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


# --------------------------------------------------------------------------------------
# Section 11 / section 14 -- schema versions
# --------------------------------------------------------------------------------------

#: Section 11: `state.json` carries a `schema_version`, and an unknown version is a hard
#: refusal (`STATE_SCHEMA_UNKNOWN`), never a best-effort read.
STATE_SCHEMA_VERSION = 1

#: Section 14: the milestone plan is a versioned schema whose unknown versions are rejected.
PLAN_SCHEMA_VERSION = 1


# --------------------------------------------------------------------------------------
# Section 10 -- the run state machine
# --------------------------------------------------------------------------------------


class RunStatus(StrEnum):
    """The eighteen runner-local states of section 10 -- never a `WorkflowState`.

    The fifteen states the Human Owner's direction names are present verbatim. The three
    additions each carry section 10's recorded justification: `MILESTONE_FAILED` separates a
    milestone whose focused verification failed (recoverable through `reopen-milestone`) from a
    global safety stop; `PROVIDER_WAIT` is the durable state during a long provider invocation,
    so a crash mid-invocation can be told apart from one where the provider never started; and
    `PROVIDER_RETRY_PENDING` is the bounded-retry state, reachable only from a proven
    pre-side-effect spawn failure.
    """

    IDLE = "IDLE"
    PREFLIGHT = "PREFLIGHT"
    IMPLEMENTING = "IMPLEMENTING"
    FOCUSED_VERIFYING = "FOCUSED_VERIFYING"
    MILESTONE_FAILED = "MILESTONE_FAILED"
    MILESTONE_COMPLETE = "MILESTONE_COMPLETE"
    FINAL_VERIFYING = "FINAL_VERIFYING"
    REVIEWING = "REVIEWING"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    CORRECTING = "CORRECTING"
    CLOSURE_VERIFYING = "CLOSURE_VERIFYING"
    PROVIDER_WAIT = "PROVIDER_WAIT"
    PROVIDER_RETRY_PENDING = "PROVIDER_RETRY_PENDING"
    READY_FOR_COMMIT_APPROVAL = "READY_FOR_COMMIT_APPROVAL"
    READY_FOR_PUSH_APPROVAL = "READY_FOR_PUSH_APPROVAL"
    HUMAN_INTERVENTION_REQUIRED = "HUMAN_INTERVENTION_REQUIRED"
    DONE = "DONE"
    ABORTED = "ABORTED"


#: Section 10: the two terminal states. Neither has an outbound edge in
#: :data:`ALLOWED_RUN_TRANSITIONS`, which is asserted member-by-member by test.
TERMINAL_RUN_STATES: frozenset[RunStatus] = frozenset({RunStatus.DONE, RunStatus.ABORTED})

# Every state a run can be sitting in when a safety gate trips or an operator aborts: the whole
# enum minus `IDLE` (nothing has started yet -- a preflight refusal happens in `PREFLIGHT`) and
# minus the two terminal states.
_LIVE_RUN_STATES: frozenset[RunStatus] = frozenset(
    {
        RunStatus.PREFLIGHT,
        RunStatus.IMPLEMENTING,
        RunStatus.FOCUSED_VERIFYING,
        RunStatus.MILESTONE_FAILED,
        RunStatus.MILESTONE_COMPLETE,
        RunStatus.FINAL_VERIFYING,
        RunStatus.REVIEWING,
        RunStatus.NEEDS_CORRECTION,
        RunStatus.CORRECTING,
        RunStatus.CLOSURE_VERIFYING,
        RunStatus.PROVIDER_WAIT,
        RunStatus.PROVIDER_RETRY_PENDING,
        RunStatus.READY_FOR_COMMIT_APPROVAL,
        RunStatus.READY_FOR_PUSH_APPROVAL,
    }
)

#: Section 10's closed transition set, transcribed as an explicit frozenset and asserted
#: member-by-member by test. `MilestoneRunnerApplication` is the sole transition authority; this
#: table is the vocabulary it is allowed to speak, not a suggestion. Neither `DONE` nor
#: `ABORTED` appears on the left of any pair.
ALLOWED_RUN_TRANSITIONS: frozenset[tuple[RunStatus, RunStatus]] = frozenset(
    {
        # -- section 5's approved runtime flow ------------------------------------------
        (RunStatus.IDLE, RunStatus.PREFLIGHT),
        (RunStatus.PREFLIGHT, RunStatus.IMPLEMENTING),
        (RunStatus.IMPLEMENTING, RunStatus.FOCUSED_VERIFYING),
        (RunStatus.FOCUSED_VERIFYING, RunStatus.MILESTONE_COMPLETE),
        (RunStatus.FOCUSED_VERIFYING, RunStatus.MILESTONE_FAILED),
        (RunStatus.MILESTONE_COMPLETE, RunStatus.IMPLEMENTING),
        (RunStatus.MILESTONE_COMPLETE, RunStatus.FINAL_VERIFYING),
        (RunStatus.FINAL_VERIFYING, RunStatus.REVIEWING),
        (RunStatus.REVIEWING, RunStatus.NEEDS_CORRECTION),
        (RunStatus.REVIEWING, RunStatus.READY_FOR_COMMIT_APPROVAL),
        (RunStatus.NEEDS_CORRECTION, RunStatus.CORRECTING),
        (RunStatus.CORRECTING, RunStatus.CLOSURE_VERIFYING),
        (RunStatus.CLOSURE_VERIFYING, RunStatus.READY_FOR_COMMIT_APPROVAL),
        (RunStatus.READY_FOR_COMMIT_APPROVAL, RunStatus.READY_FOR_PUSH_APPROVAL),
        (RunStatus.READY_FOR_PUSH_APPROVAL, RunStatus.DONE),
        # -- section 10's provider excursion --------------------------------------------
        # A provider is invoked from exactly four states (Claude drives implementation and
        # correction, Codex drives review and closure -- section 17). `PROVIDER_WAIT` is an
        # excursion out of and back into the invoking state, which keeps section 5's own edges
        # -- `IMPLEMENTING -> FOCUSED_VERIFYING` and the rest -- verbatim rather than rerouting
        # them through the wait state.
        (RunStatus.IMPLEMENTING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.IMPLEMENTING),
        (RunStatus.REVIEWING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.REVIEWING),
        (RunStatus.CORRECTING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.CORRECTING),
        (RunStatus.CLOSURE_VERIFYING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.CLOSURE_VERIFYING),
        (RunStatus.PROVIDER_WAIT, RunStatus.PROVIDER_RETRY_PENDING),
        (RunStatus.PROVIDER_RETRY_PENDING, RunStatus.PROVIDER_WAIT),
        # -- section 13's recovery commands ---------------------------------------------
        # `HUMAN_INTERVENTION_REQUIRED` exits only through one of the four recovery commands
        # (or through `abort`), never automatically, and none of them targets
        # `READY_FOR_COMMIT_APPROVAL` -- section 13's explicit prohibition, enforced here by
        # the absence of that pair rather than by a downstream check.
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.FOCUSED_VERIFYING),  # reconcile
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.IMPLEMENTING),  # reopen-milestone
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.REVIEWING),  # recover-failed-review
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.CLOSURE_VERIFYING),  # revalidate
        # `reopen-milestone` also clears a milestone that failed its own focused verification,
        # which is the distinction `MILESTONE_FAILED` exists to draw (section 10).
        (RunStatus.MILESTONE_FAILED, RunStatus.IMPLEMENTING),
        # -- section 18's "no fabricated success", as a state rather than an exception --------
        # A provider that fails, returns no parseable result block, or returns one whose status
        # is not COMPLETE is a *failed milestone*, and the run is sitting in `IMPLEMENTING` when
        # that is discovered: `PROVIDER_WAIT` is an excursion that always returns to its invoking
        # state, so the invalid result is read from `IMPLEMENTING`, never from the wait state.
        # Without this edge the sole transition authority raises instead of publishing, which
        # leaves the run wedged in `IMPLEMENTING` -- a state no recovery command admits -- and
        # turns a deterministic, recoverable stop into an uncaught exception. The edge is the
        # `IMPLEMENTING` peer of `FOCUSED_VERIFYING -> MILESTONE_FAILED` above and admits nothing
        # else: `MILESTONE_FAILED` still exits only through `reopen-milestone`, `abort`, or the
        # safety stop.
        (RunStatus.IMPLEMENTING, RunStatus.MILESTONE_FAILED),
        # -- section 5's safety stop, reachable from every live state -------------------
        *((state, RunStatus.HUMAN_INTERVENTION_REQUIRED) for state in _LIVE_RUN_STATES),
        # -- the `abort` command, reachable from every non-terminal started state --------
        *((state, RunStatus.ABORTED) for state in _LIVE_RUN_STATES),
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.ABORTED),
    }
)


# --------------------------------------------------------------------------------------
# Section 17 -- provider failure taxonomy; section 13 -- stop reasons
# --------------------------------------------------------------------------------------


class ProviderFailureClass(StrEnum):
    """Section 17's seven failure classes, determined at invocation time and persisted.

    Classification turns on **when** the failure occurred, never on error text alone
    (`MODEL_PROVIDER_CONTRACTS.md` section 2). Recovery consults the recorded class and never
    re-greps stderr -- prototype defect P-10, where recovery matched substrings such as `"401"`,
    `"websocket"` and `"connection"` against output a model may itself have authored.

    Only `SPAWN_FAILED` is provably pre-side-effect and therefore the only class section 17
    permits a bounded retry for; every other class requires reconciliation before any repetition.
    """

    SPAWN_FAILED = "SPAWN_FAILED"
    TIMEOUT = "TIMEOUT"
    COMMAND_FAILED = "COMMAND_FAILED"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    AUTH_FAILED = "AUTH_FAILED"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"
    PROVIDER_REPORTED = "PROVIDER_REPORTED"


#: Section 17: the single class a bounded retry is permitted for, because it is the only one
#: proven to have occurred before any side effect. Named here so no call site has to restate it.
RETRYABLE_PROVIDER_FAILURE_CLASSES: frozenset[ProviderFailureClass] = frozenset(
    {ProviderFailureClass.SPAWN_FAILED}
)


class StopReason(StrEnum):
    """The typed reason a run stopped -- exactly the codes the contract names verbatim.

    Sections 4, 11, 12, 14 and 15 each name a code in backticks; those twelve are transcribed
    here and nothing is invented alongside them. Section 15's cumulative-allowlist and
    forbidden-path checks are described as stops but are given no code name by the contract, so
    none is coined here: the narrower reading is implemented and the gap is reported rather than
    filled by guesswork.
    """

    STAGE_ID_NOT_AUTHORIZED = "STAGE_ID_NOT_AUTHORIZED"
    REPOSITORY_IDENTITY_MISMATCH = "REPOSITORY_IDENTITY_MISMATCH"
    BRANCH_MISMATCH = "BRANCH_MISMATCH"
    HEAD_DRIFT = "HEAD_DRIFT"
    DIRTY_TREE = "DIRTY_TREE"
    PLAN_COVERAGE_MISMATCH = "PLAN_COVERAGE_MISMATCH"
    PLAN_PATH_NOT_ALLOWLISTED = "PLAN_PATH_NOT_ALLOWLISTED"
    GOVERNANCE_CONTRADICTION = "GOVERNANCE_CONTRADICTION"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    LOCK_CONTENTION = "LOCK_CONTENTION"
    STATE_SCHEMA_UNKNOWN = "STATE_SCHEMA_UNKNOWN"
    OUT_OF_MILESTONE_SCOPE = "OUT_OF_MILESTONE_SCOPE"


class ProviderRole(StrEnum):
    """The four provider roles of section 18's machine-result grammar.

    Claude drives `IMPLEMENTATION` and `CORRECTION`; Codex drives `REVIEW` and `CLOSURE` and is
    fixed read-only (section 17). The binding itself is configuration, not this enum.
    """

    IMPLEMENTATION = "IMPLEMENTATION"
    CORRECTION = "CORRECTION"
    REVIEW = "REVIEW"
    CLOSURE = "CLOSURE"


class FindingSeverity(StrEnum):
    """Section 19's four severities: `CRITICAL`/`HIGH` block, `MEDIUM`/`LOW` are deferred."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


#: Section 19's default `blocking_severities`. A finding outside this set can never be filed as
#: a blocker (:class:`RunRecord` enforces the split), which is section 18's rule that "a blocker
#: whose severity is not Critical or High" is a malformed result, stated as a type constraint.
BLOCKING_SEVERITIES: frozenset[FindingSeverity] = frozenset(
    {FindingSeverity.CRITICAL, FindingSeverity.HIGH}
)

#: Section 19's default `defer_severities`. These never block.
DEFERRED_SEVERITIES: frozenset[FindingSeverity] = frozenset(
    {FindingSeverity.MEDIUM, FindingSeverity.LOW}
)


class FindingStatus(StrEnum):
    """A finding's lifecycle: closure verification may move an `OPEN` blocker to `CLOSED`."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    DEFERRED = "DEFERRED"


class ReviewVerdict(StrEnum):
    """Section 18's two verdicts. A `BLOCKED` verdict with no blockers, or an `APPROVED` verdict
    carrying blockers, is a semantic contradiction and therefore malformed."""

    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


class ApprovalOperation(StrEnum):
    """Section 20: an approval authorizes exactly one operation -- commit or push, never both,
    never a substitute."""

    COMMIT = "COMMIT"
    PUSH = "PUSH"


class RecoveryCommand(StrEnum):
    """Section 13's four recovery commands, each writing one append-only ledger entry."""

    RECONCILE_MILESTONE = "RECONCILE_MILESTONE"
    REOPEN_MILESTONE = "REOPEN_MILESTONE"
    RECOVER_FAILED_REVIEW = "RECOVER_FAILED_REVIEW"
    REVALIDATE_CORRECTION = "REVALIDATE_CORRECTION"


#: Section 19's five independent counters, named once so a recovery ledger entry cannot claim to
#: have touched a budget that does not exist. `provider_failure_count` is deliberately a peer of
#: `successful_review_rounds`, never a contributor to it (section 22 invariant 11).
RUN_COUNTER_FIELDS: frozenset[str] = frozenset(
    {
        "review_attempts",
        "successful_review_rounds",
        "provider_failure_count",
        "correction_round",
        "closure_round",
    }
)


# --------------------------------------------------------------------------------------
# Scalar grammar primitives
# --------------------------------------------------------------------------------------

MAX_IDENTIFIER_CHARS = 128
MAX_TITLE_CHARS = 200
MAX_TEXT_CHARS = 8_000
MAX_PATH_CHARS = 512
MAX_ROOT_PATH_CHARS = 4_096
MAX_ARGUMENT_CHARS = 4_096

_MILESTONE_ID_RE = re.compile(r"AUTO-[0-9]{3}-M[0-9]{2}")
_FINDING_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

# Unicode bidirectional formatting controls: every one is a documented visual-spoofing and
# prompt-injection vector and none has a legitimate use in any field defined here, so they are
# rejected rather than stripped. Provider output reaches several of these fields (section 18),
# which is exactly why the rejection is at the model boundary.
_BIDIRECTIONAL_CONTROLS: frozenset[int] = frozenset(
    {0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
)


def _reject_forbidden_codepoints(value: str, field: str, *, allow_newline: bool) -> None:
    """Reject surrogates, control characters and bidirectional controls outright.

    Nothing is stripped or repaired: a repaired value no longer matches what a reviewer actually
    read, which is precisely what section 18's fail-closed parsing forbids. CR is a C0 control
    and therefore rejected here too, which is also the LF-only line-ending rule.
    """
    for character in value:
        code = ord(character)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError(f"{field} must not contain a surrogate code point")
        if code in _BIDIRECTIONAL_CONTROLS:
            raise ValueError(f"{field} must not contain a Unicode bidirectional control")
        if character == "\n" and allow_newline:
            continue
        if code < 0x20 or code == 0x7F or 0x80 <= code <= 0x9F:
            raise ValueError(f"{field} must not contain a control character (U+{code:04X})")


def _scalar(value: str, field: str, maximum: int) -> str:
    """Validate one bounded, single-line, NFC-normalized scalar."""
    if not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters, got {len(value)}")
    _reject_forbidden_codepoints(value, field, allow_newline=False)
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{field} must already be NFC-normalized")
    if value.strip() != value:
        raise ValueError(f"{field} must not have leading or trailing whitespace")
    return value


def _text(value: str, field: str, maximum: int = MAX_TEXT_CHARS) -> str:
    """Validate one bounded, possibly multi-line, NFC-normalized text field."""
    if not value.strip():
        raise ValueError(f"{field} must not be empty or whitespace-only")
    if len(value) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters, got {len(value)}")
    _reject_forbidden_codepoints(value, field, allow_newline=True)
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{field} must already be NFC-normalized")
    return value


def _identifier(value: str, field: str, pattern: re.Pattern[str]) -> str:
    _scalar(value, field, MAX_IDENTIFIER_CHARS)
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{field} must match the grammar {pattern.pattern!r}")
    return value


def _sha256_hex(value: str, field: str) -> str:
    if _SHA256_HEX_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be exactly 64 lowercase hexadecimal characters")
    return value


def _git_object_id(value: str, field: str) -> str:
    if _GIT_OBJECT_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a 40- or 64-character lowercase Git object id")
    return value


def _utc_timestamp(value: str, field: str) -> str:
    """Require a second-precision, explicitly-`Z` UTC timestamp -- never local, never naive."""
    if _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field} must be an ISO-8601 UTC timestamp of the form YYYY-MM-DDThh:mm:ssZ"
        )
    return value


def _absolute_path(value: str, field: str) -> str:
    _scalar(value, field, MAX_ROOT_PATH_CHARS)
    if not value.startswith("/"):
        raise ValueError(f"{field} must be an absolute POSIX path")
    return value


def _sorted_unique(values: list[str], field: str) -> list[str]:
    """Enforce a stable, duplicate-free ordering so a digest never depends on input order."""
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain a duplicate entry")
    if values != sorted(values, key=lambda item: item.encode("utf-8")):
        raise ValueError(f"{field} must be sorted ascending by UTF-8 byte order")
    return values


def _unique(values: list[str], field: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain a duplicate entry")
    return values


# --------------------------------------------------------------------------------------
# Canonicalization (section 11 atomic publication, section 15 scope matching, section 20
# approval binding -- all three reuse these two helpers)
# --------------------------------------------------------------------------------------


def _normalize_relative_posix_path(value: str, field: str) -> str:
    """Normalize one relative POSIX path; refuse anything that could escape its root.

    Redundant separators, `.` segments and a trailing separator are *normalized away* -- that is
    what makes two spellings of one path compare equal in a scope check. An absolute path, a
    Windows drive-letter path, a backslash separator and any `..` segment are *refused*, never
    resolved: resolving traversal is how a guard talks itself into permitting an escape.
    """
    if not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > MAX_PATH_CHARS:
        raise ValueError(f"{field} must be at most {MAX_PATH_CHARS} characters, got {len(value)}")
    _reject_forbidden_codepoints(value, field, allow_newline=False)
    normalized = unicodedata.normalize("NFC", value)
    if "\\" in normalized:
        raise ValueError(f"{field} must use POSIX separators only, not a backslash")
    if normalized.startswith("/"):
        raise ValueError(f"{field} must be repository-relative, not absolute")
    if re.fullmatch(r"[A-Za-z]:.*", normalized) is not None:
        raise ValueError(f"{field} must be repository-relative, not a drive-letter path")
    segments = [segment for segment in normalized.split("/") if segment not in {"", "."}]
    if any(segment == ".." for segment in segments):
        raise ValueError(f"{field} must not contain a '..' path segment")
    if not segments:
        raise ValueError(f"{field} must name a path, not the root itself")
    for segment in segments:
        if segment.strip() != segment:
            raise ValueError(f"{field} must not have a path segment with surrounding whitespace")
    return "/".join(segments)


def normalize_repository_path(value: str, field: str = "path") -> str:
    """Return `value` as a normalized, repository-relative, dot-segment-free POSIX path.

    This is the single canonicalization the scope guard (section 15), the durable state record
    (section 11) and the approval binding (section 20) all reuse, so a path recorded by one is
    byte-comparable with a path matched by another. Matching is defined on normalized,
    repository-relative POSIX paths, and normalizing in one place is what makes that definition
    true rather than aspirational.

    Absolute, drive-letter, backslash-separated and traversal-shaped inputs raise `ValueError`.
    """
    return _normalize_relative_posix_path(value, field)


#: Fields excluded from :func:`canonical_digest`. Every one is wall-clock evidence: a timestamp
#: or a measured duration. A digest that included them would differ between two runs that
#: produced byte-identical work, which would make an approval binding (section 20) unsatisfiable
#: rather than merely noisy.
DIGEST_EXCLUDED_FIELDS: frozenset[str] = frozenset(
    {
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "recorded_at",
        "granted_at",
        "consumed_at",
        "duration_ms",
    }
)


def _canonicalize(value: object, field: str) -> Any:
    """Recursively accept only `None`, exact `bool`, `int`, `str`, `list` and `dict`.

    `StrEnum` and `IntEnum` members are accepted and reduced to their value, because this
    package's own vocabulary is enum-typed and a caller should not have to pre-serialize a model
    dump to hash it. Anything else -- a float, a tuple, a set, a `Path`, a `datetime` -- is a
    caller bug: floats in particular have no canonical decimal form, so admitting one would make
    the digest platform-dependent.
    """
    if isinstance(value, Enum):
        member: object = value.value
        if not isinstance(member, str | int) or isinstance(member, bool):
            raise ValueError(f"{field}: only a str- or int-valued Enum can be canonicalized")
        value = member
    if value is None:
        return None
    value_type = type(value)
    if value_type is bool:
        return value
    if value_type is int:
        return value
    if value_type is str:
        text = cast(str, value)
        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise ValueError(f"{field} must not contain a surrogate code point")
        return unicodedata.normalize("NFC", text)
    if isinstance(value, list):
        items: list[object] = list(value)
        return [_canonicalize(item, f"{field}[{index}]") for index, item in enumerate(items)]
    if isinstance(value, dict):
        mapping: dict[object, object] = dict(value)
        normalized: dict[str, Any] = {}
        for key, item in mapping.items():
            if isinstance(key, Enum):
                key = key.value
            if not isinstance(key, str):
                raise ValueError(f"{field}: a mapping key must be a string, got {type(key)!r}")
            if key in DIGEST_EXCLUDED_FIELDS:
                continue
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError(f"{field}: NFC-normalized key collision on {normalized_key!r}")
            normalized[normalized_key] = _canonicalize(item, f"{field}.{normalized_key}")
        return normalized
    raise ValueError(f"{field}: unsupported value type {value_type!r}")


def canonical_digest(payload: object) -> str:
    """SHA-256 over the deterministic canonical serialization of `payload`.

    Deterministic means three things, each of which a caller depends on. Keys are sorted, so a
    mapping built in a different order digests identically. Wall-clock fields named in
    :data:`DIGEST_EXCLUDED_FIELDS` are dropped at every nesting depth, so re-deriving a digest
    over the same work at a later moment reproduces it -- section 20's approval binding is only
    checkable because of this. And the serialization itself is fixed: UTF-8, NFC-normalized,
    `sort_keys=True`, `(",", ":")` separators, integers only, floats refused outright.

    List order is significant and preserved; a caller that wants order-independence sorts before
    hashing (`_sorted_unique` enforces exactly that on every list-of-paths field here).
    """
    canonical = _canonicalize(payload, "payload")
    text = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        check_circular=True,
    )
    return hashlib.sha256(text.encode("utf-8", errors="strict")).hexdigest()


# --------------------------------------------------------------------------------------
# Section 14 -- the milestone plan
# --------------------------------------------------------------------------------------


class FocusedVerificationCommand(MilestoneRunnerModel):
    """One focused-verification entry: `command` plus an optional `purpose` (section 14).

    `command` is an argv **list**, never a shell string -- section 16 admits no `shell=True` path
    anywhere in the package, and a list-typed field is how that becomes unrepresentable rather
    than merely discouraged.
    """

    command: list[str] = Field(min_length=1)
    purpose: str | None = None

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: list[str]) -> list[str]:
        for index, argument in enumerate(value):
            _scalar(argument, f"focused_verification.command[{index}]", MAX_ARGUMENT_CHARS)
        return value

    @field_validator("purpose")
    @classmethod
    def _validate_purpose(cls, value: str | None) -> str | None:
        return None if value is None else _text(value, "focused_verification.purpose")


class MilestoneSpec(MilestoneRunnerModel):
    """One milestone: section 14's thirteen required fields and exactly two optional ones.

    `extra="forbid"` is what makes the count enforceable in both directions -- an unknown field
    is rejected, matching the prototype's `additionalProperties: false` and section 14's
    fail-closed validation. A `schema_version` this build does not know is a hard refusal, never
    a best-effort read.

    Cross-milestone rules -- the acyclic dependency graph, duplicate `milestone_id` rejection and
    the `required_coverage` reconciliation -- are plan-level, not milestone-level, and belong to
    the loader rather than to this model.
    """

    schema_version: int
    milestone_id: str
    title: str
    objective: str
    depends_on: list[str]
    contract_sections: list[str]
    allowed_files: list[str]
    forbidden_files: list[str]
    required_symbols: list[str]
    explicit_exclusions: list[str]
    acceptance_criteria: list[str]
    focused_verification: list[FocusedVerificationCommand]
    completion_evidence: list[str]
    # The two optional fields. `human_owner_scope_ruling` is written only by `reopen-milestone`
    # (section 13); `additive_reuse_justification` is required by convention when a milestone
    # reuses an existing primitive, which is a reviewer's judgement and not a schema rule.
    additive_reuse_justification: str | None = None
    human_owner_scope_ruling: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"milestone schema_version {value} is unknown; this build understands "
                f"only {PLAN_SCHEMA_VERSION}"
            )
        return value

    @field_validator("milestone_id")
    @classmethod
    def _validate_milestone_id(cls, value: str) -> str:
        return _identifier(value, "milestone_id", _MILESTONE_ID_RE)

    @field_validator("depends_on")
    @classmethod
    def _validate_depends_on(cls, value: list[str]) -> list[str]:
        for index, dependency in enumerate(value):
            _identifier(dependency, f"depends_on[{index}]", _MILESTONE_ID_RE)
        return _unique(value, "depends_on")

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "title", MAX_TITLE_CHARS)

    @field_validator(
        "objective",
        "contract_sections",
        "explicit_exclusions",
        "acceptance_criteria",
        "completion_evidence",
        "forbidden_files",
        "required_symbols",
    )
    @classmethod
    def _validate_text_fields(cls, value: str | list[str], info: ValidationInfo) -> str | list[str]:
        field = str(info.field_name)
        if isinstance(value, str):
            return _text(value, field)
        for index, item in enumerate(value):
            _text(item, f"{field}[{index}]")
        return value

    @field_validator("allowed_files")
    @classmethod
    def _validate_allowed_files(cls, value: list[str]) -> list[str]:
        for index, pattern in enumerate(value):
            _scalar(pattern, f"allowed_files[{index}]", MAX_PATH_CHARS)
        return _unique(value, "allowed_files")

    @field_validator("additive_reuse_justification", "human_owner_scope_ruling")
    @classmethod
    def _validate_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        return None if value is None else _text(value, str(info.field_name))

    @model_validator(mode="after")
    def _validate_no_self_dependency(self) -> "MilestoneSpec":
        if self.milestone_id in self.depends_on:
            raise ValueError(f"{self.milestone_id} must not depend on itself")
        return self


# --------------------------------------------------------------------------------------
# Section 11 -- the durable run record and the records it carries
# --------------------------------------------------------------------------------------


class ProviderRunRecord(MilestoneRunnerModel):
    """One provider invocation's durable evidence (sections 11, 16 and 17).

    Transcripts are referenced by path and never inlined (`AUDIT_MODEL.md` section 2). The
    `sequence` field is the monotonic per-run counter that makes two invocations of the same role
    within one second impossible to conflate -- prototype defect P-9, where second-granularity
    naming could silently overwrite an earlier transcript.

    `failure_class` is recorded at invocation time, so recovery reads a decision that was made
    with the facts in hand instead of re-deriving one from text a model may have authored
    (defect P-10).
    """

    sequence: int = Field(ge=1)
    role: ProviderRole
    provider: str
    milestone_id: str | None = None
    started_at: str
    completed_at: str | None = None
    duration_ms: int = Field(ge=0)
    exit_code: int | None = None
    timed_out: bool = False
    failure_class: ProviderFailureClass | None = None
    prompt_path: str
    stdout_path: str
    stderr_path: str

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        return _scalar(value, "provider", MAX_IDENTIFIER_CHARS)

    @field_validator("milestone_id")
    @classmethod
    def _validate_milestone_id(cls, value: str | None) -> str | None:
        return None if value is None else _identifier(value, "milestone_id", _MILESTONE_ID_RE)

    @field_validator("started_at", "completed_at")
    @classmethod
    def _validate_timestamps(cls, value: str | None, info: ValidationInfo) -> str | None:
        return None if value is None else _utc_timestamp(value, str(info.field_name))

    @field_validator("prompt_path", "stdout_path", "stderr_path")
    @classmethod
    def _validate_transcript_paths(cls, value: str, info: ValidationInfo) -> str:
        return _normalize_relative_posix_path(value, str(info.field_name))

    @model_validator(mode="after")
    def _validate_timeout_consistency(self) -> "ProviderRunRecord":
        if self.timed_out and self.failure_class is not ProviderFailureClass.TIMEOUT:
            raise ValueError("a timed-out invocation must be classified TIMEOUT")
        return self


class VerificationResult(MilestoneRunnerModel):
    """One verification command's outcome (section 16).

    The record carries only the exit code, the duration, the timeout flag and the references;
    the full output lives in the transcript directory, sanitized before it is written, rather
    than being truncated to a tail -- prototype defect P-8.

    Section 22 invariant 18 is enforced structurally: `passed` is recomputed from `exit_code` and
    `timed_out`, so a record that reports success for a timeout or a non-zero exit cannot be
    constructed. `WORKFLOW_STATES.md` section 5a item 6 -- "a workflow never reports success
    solely because a command timed out" -- is therefore true by type, not by convention.
    """

    command: list[str] = Field(min_length=1)
    exit_code: int | None = None
    timed_out: bool = False
    passed: bool
    duration_ms: int = Field(ge=0)
    stdout_path: str
    stderr_path: str

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: list[str]) -> list[str]:
        for index, argument in enumerate(value):
            _scalar(argument, f"command[{index}]", MAX_ARGUMENT_CHARS)
        return value

    @field_validator("stdout_path", "stderr_path")
    @classmethod
    def _validate_output_paths(cls, value: str, info: ValidationInfo) -> str:
        return _normalize_relative_posix_path(value, str(info.field_name))

    @model_validator(mode="after")
    def _validate_no_fabricated_success(self) -> "VerificationResult":
        expected = self.exit_code == 0 and not self.timed_out
        if self.passed != expected:
            raise ValueError(
                "passed must be exactly `exit_code == 0 and not timed_out`: exit code "
                f"{self.exit_code!r} with timed_out={self.timed_out} is "
                f"{'a PASS' if expected else 'a FAIL'}"
            )
        return self


class Finding(MilestoneRunnerModel):
    """One review finding (sections 18 and 19).

    Whether a finding blocks is decided by its severity and enforced by :class:`RunRecord`, which
    keeps blockers and deferred findings in two lists and refuses a Medium or Low blocker. A
    provider cannot promote its own finding by filing it in the other list.
    """

    finding_id: str
    severity: FindingSeverity
    title: str
    summary: str
    status: FindingStatus = FindingStatus.OPEN

    @field_validator("finding_id")
    @classmethod
    def _validate_finding_id(cls, value: str) -> str:
        return _identifier(value, "finding_id", _FINDING_ID_RE)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "title", MAX_TITLE_CHARS)

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        return _text(value, "summary")


class ApprovalRecord(MilestoneRunnerModel):
    """One Human Owner approval for exactly one commit or one push (section 20).

    `HUMAN_AUTHORIZATION_MODEL.md` section 5a's constraints are carried as fields rather than as
    prose: the approval is **bound** to the repository identity, the branch, the baseline and
    current HEAD, the canonical changed-path set with a digest per file, the verification result
    set, the review verdict and its finding IDs, and the exact operation; and it is **single-use**
    -- `consumed` and `consumed_at` move together, so a second execution needs a fresh approval.

    `execution_started_at` is what makes "durably recorded" survive a crash: it is stamped and
    published *before* the gated Git vector runs, so a process lost between the mutation and its
    consumption record leaves a grant that is visibly attempted and visibly unconsumed. A later
    gate reads that pair as an act nobody reconciled and refuses, rather than repeating it.

    `resulting_head_sha` is where an executed commit landed. Section 4 item 4 admits exactly one
    event that may advance `HEAD` -- a Human Owner-approved commit executed through the section 20
    gate -- "and it is recorded with the approval that authorized it", which is this field.

    The record is evidence, never authority: nothing here transitions a run. The application
    decides, and a failed deterministic gate still fails with an approval in hand.
    """

    operation: ApprovalOperation
    granted_at: str
    repository_identity: str
    branch: str
    baseline_sha: str
    head_sha: str
    changed_paths: list[str]
    changed_path_digests: dict[str, str]
    verification_digest: str
    review_verdict: ReviewVerdict
    finding_ids: list[str]
    human_confirmation_supplied: bool
    execution_started_at: str | None = None
    consumed: bool = False
    consumed_at: str | None = None
    resulting_head_sha: str | None = None

    @field_validator("granted_at", "consumed_at", "execution_started_at")
    @classmethod
    def _validate_timestamps(cls, value: str | None, info: ValidationInfo) -> str | None:
        return None if value is None else _utc_timestamp(value, str(info.field_name))

    @field_validator("resulting_head_sha")
    @classmethod
    def _validate_resulting_head_sha(cls, value: str | None) -> str | None:
        return None if value is None else _git_object_id(value, "resulting_head_sha")

    @field_validator("repository_identity", "branch")
    @classmethod
    def _validate_scalars(cls, value: str, info: ValidationInfo) -> str:
        return _scalar(value, str(info.field_name), MAX_IDENTIFIER_CHARS)

    @field_validator("baseline_sha", "head_sha")
    @classmethod
    def _validate_object_ids(cls, value: str, info: ValidationInfo) -> str:
        return _git_object_id(value, str(info.field_name))

    @field_validator("verification_digest")
    @classmethod
    def _validate_verification_digest(cls, value: str) -> str:
        return _sha256_hex(value, "verification_digest")

    @field_validator("changed_paths")
    @classmethod
    def _validate_changed_paths(cls, value: list[str]) -> list[str]:
        normalized = [
            normalize_repository_path(item, f"changed_paths[{index}]")
            for index, item in enumerate(value)
        ]
        return _sorted_unique(normalized, "changed_paths")

    @field_validator("finding_ids")
    @classmethod
    def _validate_finding_ids(cls, value: list[str]) -> list[str]:
        for index, item in enumerate(value):
            _identifier(item, f"finding_ids[{index}]", _FINDING_ID_RE)
        return _sorted_unique(value, "finding_ids")

    @field_validator("changed_path_digests")
    @classmethod
    def _validate_digests(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for path, digest in value.items():
            key = normalize_repository_path(path, "changed_path_digests key")
            _sha256_hex(digest, f"changed_path_digests[{key}]")
            if key in normalized:
                raise ValueError(f"changed_path_digests must not name {key} twice")
            normalized[key] = digest
        return normalized

    @model_validator(mode="after")
    def _validate_binding(self) -> "ApprovalRecord":
        if sorted(self.changed_path_digests) != self.changed_paths:
            raise ValueError(
                "changed_path_digests must carry a digest for exactly every changed path"
            )
        if self.consumed != (self.consumed_at is not None):
            raise ValueError(
                "consumed and consumed_at must be set together: an approval is single-use"
            )
        if self.consumed and self.execution_started_at is None:
            raise ValueError(
                "a consumed approval must record when its execution was attempted: the attempt is "
                "durable before the act, so a consumption without one describes no act at all"
            )
        if self.resulting_head_sha is not None and not self.consumed:
            raise ValueError("only a consumed approval can name where its execution landed HEAD")
        return self


class RecoveryLedgerEntry(MilestoneRunnerModel):
    """One append-only entry in one of section 13's four recovery ledgers.

    Each recovery command records its reason, the pre-state and post-state, the budgets it
    touched and the branch and HEAD observed at recovery time. The pre/post pair is validated
    against :data:`ALLOWED_RUN_TRANSITIONS`, so a ledger cannot claim a transition the state
    machine does not admit, and `budgets_touched` may only name one of the five counters that
    actually exists (section 22 invariant 11).
    """

    command: RecoveryCommand
    reason: str
    recorded_at: str
    pre_state: RunStatus
    post_state: RunStatus
    branch: str
    head_sha: str
    milestone_id: str | None = None
    budgets_touched: dict[str, int] = Field(default_factory=dict)
    classification: ProviderFailureClass | None = None
    human_owner_ruling: str | None = None

    @field_validator("reason", "human_owner_ruling")
    @classmethod
    def _validate_text_fields(cls, value: str | None, info: ValidationInfo) -> str | None:
        return None if value is None else _text(value, str(info.field_name))

    @field_validator("recorded_at")
    @classmethod
    def _validate_recorded_at(cls, value: str) -> str:
        return _utc_timestamp(value, "recorded_at")

    @field_validator("branch")
    @classmethod
    def _validate_branch(cls, value: str) -> str:
        return _scalar(value, "branch", MAX_IDENTIFIER_CHARS)

    @field_validator("head_sha")
    @classmethod
    def _validate_head_sha(cls, value: str) -> str:
        return _git_object_id(value, "head_sha")

    @field_validator("milestone_id")
    @classmethod
    def _validate_milestone_id(cls, value: str | None) -> str | None:
        return None if value is None else _identifier(value, "milestone_id", _MILESTONE_ID_RE)

    @field_validator("budgets_touched")
    @classmethod
    def _validate_budgets(cls, value: dict[str, int]) -> dict[str, int]:
        for name in value:
            if name not in RUN_COUNTER_FIELDS:
                raise ValueError(
                    f"budgets_touched names {name!r}, which is not one of the five counters "
                    f"{sorted(RUN_COUNTER_FIELDS)}"
                )
        return value

    @model_validator(mode="after")
    def _validate_transition(self) -> "RecoveryLedgerEntry":
        if (self.pre_state, self.post_state) not in ALLOWED_RUN_TRANSITIONS:
            raise ValueError(
                f"{self.pre_state} -> {self.post_state} is not an allowed run transition"
            )
        return self


#: The digest recorded for a changed path the inspector could not read: a deletion, a path that
#: exceeds the read ceiling, or a component that refused a no-follow open (invariant 8).
#:
#: It is deliberately not a hash, and it never compares equal to a real one -- not even to
#: itself, once :func:`MilestoneCheckpoint.differs_from` is asked. Two unreadable observations
#: are not evidence of unchanged content, so a path in this state is always attributed to the
#: milestone currently being evaluated rather than silently inheriting an earlier milestone's
#: ownership. The conservative direction is the safe one: it can only cause a stop, never a pass.
UNREADABLE_DIGEST: str = "unreadable"


class MilestoneCheckpoint(MilestoneRunnerModel):
    """The observed worktree at the moment one milestone completed (sections 11 and 15).

    Section 15 check 2 is per-milestone, and a run that makes no commit until its very end
    accumulates every earlier milestone's work in the same worktree diff. Without durable
    evidence of what each milestone actually changed, "the paths this milestone changed" is not
    computable, and check 2 degenerates into "every path this *run* changed" -- finding
    GOV-AUTO-11-F1, which stops a later milestone with `OUT_OF_MILESTONE_SCOPE` for the sole
    reason that an earlier, completed milestone changed its own authorized files.

    A checkpoint is content-addressed on purpose. Ownership is never inferred from a filename
    pattern: a path belongs to the milestone under evaluation when its bytes differ from the
    previous checkpoint, or when it appears in the worktree for the first time. That makes the
    two directions symmetric -- a later milestone cannot quietly acquire an earlier milestone's
    path by editing it, and an earlier milestone's untouched file is never reclassified as a
    current-milestone violation.

    Recorded once per completed milestone, appended and never rewritten (section 11).
    """

    milestone_id: str
    recorded_at: str
    path_digests: dict[str, str] = Field(default_factory=dict)

    @field_validator("milestone_id")
    @classmethod
    def _validate_milestone_id(cls, value: str) -> str:
        return _identifier(value, "milestone_id", _MILESTONE_ID_RE)

    @field_validator("recorded_at")
    @classmethod
    def _validate_recorded_at(cls, value: str) -> str:
        return _utc_timestamp(value, "recorded_at")

    @field_validator("path_digests")
    @classmethod
    def _validate_path_digests(cls, value: dict[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        for path, digest in value.items():
            normalized = normalize_repository_path(path, "path_digests")
            if digest != UNREADABLE_DIGEST:
                _sha256_hex(digest, f"path_digests[{normalized}]")
            validated[normalized] = digest
        return validated

    def differs_from(self, path: str, digest: str) -> bool:
        """Whether `path` at `digest` is this checkpoint's own content, byte for byte.

        A path the checkpoint never saw differs. A path either side of which is unreadable
        differs, because an unreadable observation is not evidence of sameness.
        """
        recorded = self.path_digests.get(path)
        if recorded is None:
            return True
        if recorded == UNREADABLE_DIGEST or digest == UNREADABLE_DIGEST:
            return True
        return recorded != digest


class RunRecord(MilestoneRunnerModel):
    """The durable run record of section 11 -- current state only, plus its append-only ledgers.

    `workflow_state` keeps the prototype's proven field name and is typed :class:`RunStatus`: a
    runner-local status, never a `WorkflowState` (section 7).

    The five counters of section 19 are five separate fields and are never derived from one
    another. `provider_failure_count` in particular is a peer of `successful_review_rounds`, not
    a contributor to it, because the recorded real run consumed a review budget to a
    `token_expired` provider failure and needed an explicit recovery act to get it back.
    """

    schema_version: int
    run_id: str
    repository_root: str
    repository_identity: str
    expected_branch: str
    baseline_sha: str
    contract_sha256: str
    workflow_state: RunStatus
    stop_reason: StopReason | None = None
    created_at: str
    updated_at: str
    current_milestone: str | None = None
    completed_milestones: list[str] = Field(default_factory=list)
    #: One content-addressed observation per completed milestone, in completion order. Section
    #: 15 check 2 is evaluated against the delta between the last of these and the worktree as
    #: it now stands, so a completed milestone's own authorized files are never reclassified as
    #: the current milestone's violations (finding GOV-AUTO-11-F1). Append-only, like every
    #: other ledger on this record.
    milestone_checkpoints: list[MilestoneCheckpoint] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    provider_runs: list[ProviderRunRecord] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    blocking_findings: list[Finding] = Field(default_factory=list)
    deferred_findings: list[Finding] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    # Section 19's five independent counters.
    review_attempts: int = Field(default=0, ge=0)
    successful_review_rounds: int = Field(default=0, ge=0)
    provider_failure_count: int = Field(default=0, ge=0)
    correction_round: int = Field(default=0, ge=0)
    closure_round: int = Field(default=0, ge=0)
    # Section 19's four append-only recovery ledgers.
    reconciliations: list[RecoveryLedgerEntry] = Field(default_factory=list)
    reopenings: list[RecoveryLedgerEntry] = Field(default_factory=list)
    review_recoveries: list[RecoveryLedgerEntry] = Field(default_factory=list)
    revalidations: list[RecoveryLedgerEntry] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != STATE_SCHEMA_VERSION:
            raise ValueError(
                f"state schema_version {value} is unknown; this build understands "
                f"only {STATE_SCHEMA_VERSION}"
            )
        return value

    @field_validator("run_id", "repository_identity", "expected_branch")
    @classmethod
    def _validate_scalars(cls, value: str, info: ValidationInfo) -> str:
        return _scalar(value, str(info.field_name), MAX_IDENTIFIER_CHARS)

    @field_validator("repository_root")
    @classmethod
    def _validate_repository_root(cls, value: str) -> str:
        return _absolute_path(value, "repository_root")

    @field_validator("baseline_sha")
    @classmethod
    def _validate_baseline_sha(cls, value: str) -> str:
        return _git_object_id(value, "baseline_sha")

    @field_validator("contract_sha256")
    @classmethod
    def _validate_contract_sha256(cls, value: str) -> str:
        return _sha256_hex(value, "contract_sha256")

    @field_validator("created_at", "updated_at")
    @classmethod
    def _validate_timestamps(cls, value: str, info: ValidationInfo) -> str:
        return _utc_timestamp(value, str(info.field_name))

    @field_validator("current_milestone")
    @classmethod
    def _validate_current_milestone(cls, value: str | None) -> str | None:
        return None if value is None else _identifier(value, "current_milestone", _MILESTONE_ID_RE)

    @field_validator("completed_milestones")
    @classmethod
    def _validate_completed_milestones(cls, value: list[str]) -> list[str]:
        # Dependency order is meaningful here, so uniqueness is required but sortedness is not.
        for index, item in enumerate(value):
            _identifier(item, f"completed_milestones[{index}]", _MILESTONE_ID_RE)
        return _unique(value, "completed_milestones")

    @field_validator("milestone_checkpoints")
    @classmethod
    def _validate_milestone_checkpoints(
        cls, value: list[MilestoneCheckpoint]
    ) -> list[MilestoneCheckpoint]:
        # Completion order is meaningful -- the last entry is the baseline the next milestone is
        # measured against -- so uniqueness is required and sortedness is not.
        _unique([entry.milestone_id for entry in value], "milestone_checkpoints milestone ids")
        return value

    @field_validator("changed_paths")
    @classmethod
    def _validate_changed_paths(cls, value: list[str]) -> list[str]:
        normalized = [
            normalize_repository_path(item, f"changed_paths[{index}]")
            for index, item in enumerate(value)
        ]
        return _sorted_unique(normalized, "changed_paths")

    @model_validator(mode="after")
    def _validate_record(self) -> "RunRecord":
        if (
            self.workflow_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
            and self.stop_reason is None
        ):
            raise ValueError(
                "a run stopped at HUMAN_INTERVENTION_REQUIRED must record a stop_reason"
            )
        if self.workflow_state is RunStatus.DONE and self.stop_reason is not None:
            raise ValueError("a completed run must not record a stop_reason")

        sequences = [record.sequence for record in self.provider_runs]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError(
                "provider_runs must carry strictly increasing, unique sequence numbers"
            )

        for finding in self.blocking_findings:
            if finding.severity not in BLOCKING_SEVERITIES:
                raise ValueError(
                    f"blocking_findings must not carry a {finding.severity} finding; "
                    f"only {sorted(BLOCKING_SEVERITIES)} block"
                )
        for finding in self.deferred_findings:
            if finding.severity not in DEFERRED_SEVERITIES:
                raise ValueError(
                    f"deferred_findings must not carry a {finding.severity} finding; "
                    f"only {sorted(DEFERRED_SEVERITIES)} are deferred"
                )
        finding_ids = [finding.finding_id for finding in self.blocking_findings] + [
            finding.finding_id for finding in self.deferred_findings
        ]
        _unique(finding_ids, "finding ids across blocking_findings and deferred_findings")

        for ledger_name, command in (
            ("reconciliations", RecoveryCommand.RECONCILE_MILESTONE),
            ("reopenings", RecoveryCommand.REOPEN_MILESTONE),
            ("review_recoveries", RecoveryCommand.RECOVER_FAILED_REVIEW),
            ("revalidations", RecoveryCommand.REVALIDATE_CORRECTION),
        ):
            entries: list[RecoveryLedgerEntry] = getattr(self, ledger_name)
            for entry in entries:
                if entry.command is not command:
                    raise ValueError(f"{ledger_name} must contain only {command} entries")
        return self
