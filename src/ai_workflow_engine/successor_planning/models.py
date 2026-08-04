"""Typed foundation for AUTO-015 successor planning.

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 7.1
(RepositoryIdentity), 10.1/10.2 (Candidate model and its fail-closed rules), 12 (outcome
taxonomy), 13 (failure taxonomy), 14.2 (typed field grammar), 16.1 (proposal artifact),
16.2 (canonicalization) and 16.3 (`generation_metadata`).

This module is pure typed data plus pure functions. It performs no I/O, no Git access, no
filesystem traversal and no rendering; every value it validates is handed to it by a caller
that already read it.

Every model inherits :class:`SuccessorPlanningModel`, which mirrors the prompt package's
existing `PromptStrictModel` discipline (`extra="forbid"` plus `strict=True`), so an
unrecognized field in a repository-sourced document is a schema error rather than silently
ignored input. Every repository-sourced scalar additionally passes the section 14.2 field
grammar, enforced by rejection and never by repair:

* a bounded maximum length -- an over-long value is refused, never truncated, because a
  truncated fragment can itself be attacker-shaped;
* C0/C1 control characters (which includes CR) and Unicode bidirectional controls are
  rejected outright, never stripped;
* NFC is asserted, never silently re-applied, so a homoglyph payload can never slip through
  under a "corrected" hash that no longer matches what a reviewer actually read;
* surrogate code points are rejected, matching `canonicalize_json_value`.

Identifiers match closed grammars; free text is never accepted where an identifier is
expected. Every list-valued field carries its section 16.2 sortedness invariant, enforced
here at the model layer because `canonical_json` does not infer ordering on its own.
"""

import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from ai_workflow_engine.models import StrictModel
from ai_workflow_engine.prompt.renderer import canonical_json


class SuccessorPlanningModel(StrictModel):
    """Base for every successor-planning model: closed schema plus exact-type fields.

    `model_config` does not cascade into nested models in Pydantic v2, so `strict=True` is
    declared once here and inherited by every model in this package rather than repeated at
    each nesting level. `extra="forbid"` comes from `StrictModel` unchanged; this base never
    modifies `StrictModel` itself, which is shared with unrelated configuration models.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


# --------------------------------------------------------------------------------------
# Section 14.2 scalar grammar primitives
# --------------------------------------------------------------------------------------

_INT64_MIN = -9223372036854775808
_INT64_MAX = 9223372036854775807

# Unicode bidirectional formatting controls. None has a legitimate use in any field this
# schema defines, and every one of them is a documented visual-spoofing / prompt-injection
# vector, so they are rejected rather than flagged (section 14.2).
_BIDIRECTIONAL_CONTROLS: frozenset[int] = frozenset(
    {
        0x061C,  # ARABIC LETTER MARK
        0x200E,  # LEFT-TO-RIGHT MARK
        0x200F,  # RIGHT-TO-LEFT MARK
        0x202A,  # LEFT-TO-RIGHT EMBEDDING
        0x202B,  # RIGHT-TO-LEFT EMBEDDING
        0x202C,  # POP DIRECTIONAL FORMATTING
        0x202D,  # LEFT-TO-RIGHT OVERRIDE
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0x2067,  # RIGHT-TO-LEFT ISOLATE
        0x2068,  # FIRST STRONG ISOLATE
        0x2069,  # POP DIRECTIONAL ISOLATE
    }
)

MAX_TITLE_CHARS = 120
MAX_MISSION_CHARS = 2_000
MAX_OWNER_DECISION_CHARS = 200
MAX_PATH_CHARS = 512
MAX_STATUS_CHARS = 64
MAX_MESSAGE_CHARS = 1_000
MAX_ROOT_PATH_CHARS = 4_096
MAX_REFERENCE_CHARS = 255
# Section 22 invariant 14: an explicit ceiling on the one genuinely large text field, so a
# degenerate rendering can never be persisted or re-parsed unboundedly.
MAX_GENERATED_PROMPT_CHARS = 262_144

_CANDIDATE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
# Section 10.1 states `dependency_id: str` without a regex, while section 14.2 requires that
# `candidate_id`, `dependency_id` and `blocker_id` all match a closed grammar and that free
# text is never accepted where an identifier is expected. This is the narrowest closed
# grammar that admits every identifier form the authoritative catalog actually uses
# (`AUTO-014`, `GOV-AUTO-08`, `prompt-renderer`): dash-joined alphanumeric segments only.
_DEPENDENCY_ID_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_BLOCKER_ID_RE = re.compile(r"(?:OD|D)-[0-9]+")
_STAGE_ID_RE = re.compile(r"AUTO-[0-9]{3}")
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_SCHEMA_VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
_FINDING_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]*")
# Section 16.2 timezone policy: UTC, ISO-8601, explicit `Z` suffix, never local or naive.
_UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

MIN_CANDIDATE_ID_CHARS = 3
MAX_CANDIDATE_ID_CHARS = 64


def _reject_forbidden_codepoints(value: str, field: str, *, allow_newline: bool) -> None:
    """Reject surrogates, control characters and bidirectional controls outright.

    Nothing is stripped or repaired: a "best-effort recovery" is exactly what this
    contract's fail-closed principle forbids (section 14.2, invariant 15). CR is a C0
    control and therefore rejected here, which is also the section 16.2 line-ending rule.
    """
    for character in value:
        code = ord(character)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError(f"{field} must not contain a surrogate code point")
        if code in _BIDIRECTIONAL_CONTROLS:
            raise ValueError(
                f"{field} must not contain the Unicode bidirectional control U+{code:04X}"
            )
        if code < 0x20 or code == 0x7F or 0x80 <= code <= 0x9F:
            if allow_newline and character == "\n":
                continue
            raise ValueError(f"{field} must not contain the control character U+{code:04X}")


def _scalar(value: str, field: str, maximum: int) -> str:
    """Validate one bounded, single-line, repository-sourced scalar (section 14.2)."""
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


def _text_block(value: str, field: str, maximum: int) -> str:
    """Validate one bounded, multi-line normalized text field (section 16.2).

    LF-only line endings, NFC, and exactly one final newline -- the same trailing-newline
    rule `prompt/models.py` already applies to template content.
    """
    if not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters, got {len(value)}")
    _reject_forbidden_codepoints(value, field, allow_newline=True)
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{field} must already be NFC-normalized")
    if not value.endswith("\n") or value.endswith("\n\n"):
        raise ValueError(f"{field} must end with exactly one final newline")
    return value


def _identifier(value: str, field: str, pattern: re.Pattern[str], maximum: int) -> str:
    _scalar(value, field, maximum)
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{field} must match the grammar {pattern.pattern!r}")
    return value


def _hex64(value: str, field: str) -> str:
    if _SHA256_HEX_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be exactly 64 lowercase hexadecimal characters")
    return value


def _int64(value: int, field: str) -> int:
    if not (_INT64_MIN <= value <= _INT64_MAX):
        raise ValueError(f"{field} must be inside the signed 64-bit range")
    return value


def _relative_path(value: str, field: str) -> str:
    """Validate one repository-relative POSIX path (section 16.2 path normalization).

    Absolute paths are refused so the evidence manifest -- and therefore the proposal hash --
    stays independent of where the repository happens to be checked out.
    """
    _scalar(value, field, MAX_PATH_CHARS)
    if value.startswith("/") or re.fullmatch(r"[A-Za-z]:.*", value) is not None:
        raise ValueError(f"{field} must be repository-relative, not absolute")
    if "\\" in value:
        raise ValueError(f"{field} must use POSIX separators only")
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError(f"{field} must not contain an empty, '.' or '..' path segment")
    return value


def _absolute_path(value: str, field: str) -> str:
    _scalar(value, field, MAX_ROOT_PATH_CHARS)
    if not value.startswith("/"):
        raise ValueError(f"{field} must be an absolute POSIX path")
    return value


def _require_sorted_unique(
    keys: list[str],
    field: str,
    key_name: str,
    *,
    bytewise: bool = True,
) -> None:
    """Enforce one named section 16.2 sortedness invariant.

    `bytewise` selects the section 16.2 ordering rule that applies: paths and identifiers
    sort byte-wise on their UTF-8 encoding, while `required_owner_decisions` -- the one list
    with no identifier key -- sorts lexicographically as plain strings.
    """
    ordered = sorted(keys, key=lambda key: key.encode("utf-8")) if bytewise else sorted(keys)
    if keys != ordered:
        raise ValueError(f"{field} must be sorted by {key_name}, ascending")
    if len(set(keys)) != len(keys):
        raise ValueError(f"{field} must not repeat a {key_name}")


# --------------------------------------------------------------------------------------
# Section 7.1 -- repository identity
# --------------------------------------------------------------------------------------


class RepositoryIdentity(SuccessorPlanningModel):
    """The typed repository binding captured at invocation start and before publication.

    Reuses the existing `CanonicalGitStatus` field shape for its Git half rather than
    inventing a second one. Every field is captured verbatim, hashed into the proposal, and
    re-verified before publication, because a branch or HEAD change between read and publish
    is exactly the drift the section 7.3 protocol exists to catch.
    """

    configured_repository_root: str
    resolved_repository_root: str
    configured_repository_id: str
    git_worktree_root: str
    branch: str
    head_sha: str
    upstream_ref: str | None
    ahead: int | None
    behind: int | None
    modified_files: list[str]
    staged_files: list[str]
    untracked_files: list[str]
    config_hash: str

    @field_validator("configured_repository_root")
    @classmethod
    def _validate_configured_root(cls, value: str) -> str:
        return _scalar(value, "configured_repository_root", MAX_ROOT_PATH_CHARS)

    @field_validator("resolved_repository_root")
    @classmethod
    def _validate_resolved_root(cls, value: str) -> str:
        return _absolute_path(value, "resolved_repository_root")

    @field_validator("git_worktree_root")
    @classmethod
    def _validate_worktree_root(cls, value: str) -> str:
        return _absolute_path(value, "git_worktree_root")

    @field_validator("configured_repository_id")
    @classmethod
    def _validate_repository_id(cls, value: str) -> str:
        return _scalar(value, "configured_repository_id", MAX_REFERENCE_CHARS)

    @field_validator("branch")
    @classmethod
    def _validate_branch(cls, value: str) -> str:
        return _scalar(value, "branch", MAX_REFERENCE_CHARS)

    @field_validator("head_sha")
    @classmethod
    def _validate_head(cls, value: str) -> str:
        if _GIT_OBJECT_ID_RE.fullmatch(value) is None:
            raise ValueError("head_sha must be a 40- or 64-character lowercase Git object id")
        return value

    @field_validator("upstream_ref")
    @classmethod
    def _validate_upstream(cls, value: str | None) -> str | None:
        return None if value is None else _scalar(value, "upstream_ref", MAX_REFERENCE_CHARS)

    @field_validator("ahead", "behind")
    @classmethod
    def _validate_counts(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 0:
            raise ValueError("ahead/behind counts must not be negative")
        return _int64(value, "ahead/behind")

    @field_validator("modified_files", "staged_files", "untracked_files")
    @classmethod
    def _validate_worktree_paths(cls, value: list[str]) -> list[str]:
        for path in value:
            _relative_path(path, "working-tree path")
        _require_sorted_unique(value, "working-tree file list", "path")
        return value

    @field_validator("config_hash")
    @classmethod
    def _validate_config_hash(cls, value: str) -> str:
        return _hex64(value, "config_hash")

    @model_validator(mode="after")
    def _validate_upstream_coupling(self) -> "RepositoryIdentity":
        if self.upstream_ref is None and (self.ahead is not None or self.behind is not None):
            raise ValueError("ahead/behind must be absent when no upstream is configured")
        if (self.ahead is None) != (self.behind is None):
            raise ValueError("ahead and behind must both be present or both be absent")
        return self


# --------------------------------------------------------------------------------------
# Section 10.1 -- the candidate model
# --------------------------------------------------------------------------------------

LifecycleStatus = Literal[
    "eligible",
    "blocked",
    "deferred",
    "insufficient_evidence",
    "unknown",
]

MvpRelation = Literal["inside", "adjacent", "outside_deferred", "unknown"]
DependencyType = Literal["stage", "subsystem", "capability"]
BlockerType = Literal["open_question", "deferred_defect"]
SourceKind = Literal["static_catalog"]


class CandidateDependency(SuccessorPlanningModel):
    """One typed dependency of a candidate -- never a bare string."""

    dependency_id: str
    dependency_type: DependencyType
    status: str

    @field_validator("dependency_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _identifier(value, "dependency_id", _DEPENDENCY_ID_RE, MAX_CANDIDATE_ID_CHARS)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return _scalar(value, "dependency status", MAX_STATUS_CHARS)


class CandidateBlocker(SuccessorPlanningModel):
    """One typed blocker of a candidate.

    `live_status` is carried as declared data only. Section 10.1 requires it to be
    re-resolved live against the current `OPEN_QUESTIONS.md`/completion-report status at read
    time; the catalog's frozen text is never trusted, so nothing here treats this value as
    authoritative.
    """

    blocker_id: str
    blocker_type: BlockerType
    live_status: str

    @field_validator("blocker_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _identifier(value, "blocker_id", _BLOCKER_ID_RE, MAX_CANDIDATE_ID_CHARS)

    @field_validator("live_status")
    @classmethod
    def _validate_live_status(cls, value: str) -> str:
        return _scalar(value, "live_status", MAX_STATUS_CHARS)


class EvidenceReference(SuccessorPlanningModel):
    """One `{path, sha256, size}` evidence record, path repository-relative."""

    path: str
    sha256: str
    size: int

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _relative_path(value, "evidence path")

    @field_validator("sha256")
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        return _hex64(value, "evidence sha256")

    @field_validator("size")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        if value < 0:
            raise ValueError("evidence size must not be negative")
        return _int64(value, "evidence size")


class StaticCatalogSourceReference(SuccessorPlanningModel):
    """Provenance for a `static_catalog` candidate (DEC-003's only source kind).

    Section 10.1 also sketches a `bounded_derived` variant; DEC-003 puts bounded derivation
    outside the AUTO-015 MVP entirely, so the narrower reading applies and only this variant
    exists.
    """

    catalog_path: str
    catalog_version: str
    entry_index: int

    @field_validator("catalog_path")
    @classmethod
    def _validate_catalog_path(cls, value: str) -> str:
        return _relative_path(value, "catalog_path")

    @field_validator("catalog_version")
    @classmethod
    def _validate_catalog_version(cls, value: str) -> str:
        _scalar(value, "catalog_version", MAX_STATUS_CHARS)
        if _SCHEMA_VERSION_RE.fullmatch(value) is None:
            raise ValueError("catalog_version must be an additive MAJOR.MINOR version string")
        return value

    @field_validator("entry_index")
    @classmethod
    def _validate_entry_index(cls, value: int) -> int:
        if value < 0:
            raise ValueError("entry_index must not be negative")
        return _int64(value, "entry_index")


class Candidate(SuccessorPlanningModel):
    """One successor candidate, exactly as section 10.1 declares it.

    `lifecycle_status` is declared here but is never author-set and is never assigned by this
    module: section 11 computes it at read time from live evidence. It defaults to `None` so
    a catalog entry that omits it -- as the authoritative catalog deliberately does -- parses,
    while a catalog entry that tries to assert it is still rejected by the catalog reader
    rather than by this schema.
    """

    candidate_id: str
    schema_version: str
    title: str
    mission: str
    source_kind: SourceKind
    source_reference: StaticCatalogSourceReference
    lifecycle_status: LifecycleStatus | None = None
    mvp_relation: MvpRelation
    dependencies: list[CandidateDependency]
    blockers: list[CandidateBlocker]
    required_owner_decisions: list[str]
    allowed_recommendation_status: bool
    evidence_references: list[EvidenceReference]
    content_hash: str

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, value: str) -> str:
        _identifier(value, "candidate_id", _CANDIDATE_ID_RE, MAX_CANDIDATE_ID_CHARS)
        if len(value) < MIN_CANDIDATE_ID_CHARS:
            raise ValueError(f"candidate_id must be at least {MIN_CANDIDATE_ID_CHARS} characters")
        return value

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        _scalar(value, "schema_version", MAX_STATUS_CHARS)
        if _SCHEMA_VERSION_RE.fullmatch(value) is None:
            raise ValueError("schema_version must be an additive MAJOR.MINOR version string")
        return value

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "title", MAX_TITLE_CHARS)

    @field_validator("mission")
    @classmethod
    def _validate_mission(cls, value: str) -> str:
        return _scalar(value, "mission", MAX_MISSION_CHARS)

    @field_validator("dependencies")
    @classmethod
    def _validate_dependencies(cls, value: list[CandidateDependency]) -> list[CandidateDependency]:
        _require_sorted_unique(
            [dependency.dependency_id for dependency in value], "dependencies", "dependency_id"
        )
        return value

    @field_validator("blockers")
    @classmethod
    def _validate_blockers(cls, value: list[CandidateBlocker]) -> list[CandidateBlocker]:
        _require_sorted_unique([blocker.blocker_id for blocker in value], "blockers", "blocker_id")
        return value

    @field_validator("required_owner_decisions")
    @classmethod
    def _validate_owner_decisions(cls, value: list[str]) -> list[str]:
        for decision in value:
            _scalar(decision, "required_owner_decisions entry", MAX_OWNER_DECISION_CHARS)
        _require_sorted_unique(value, "required_owner_decisions", "decision text", bytewise=False)
        return value

    @field_validator("evidence_references")
    @classmethod
    def _validate_evidence(cls, value: list[EvidenceReference]) -> list[EvidenceReference]:
        _require_sorted_unique(
            [reference.path for reference in value], "evidence_references", "path"
        )
        return value

    @field_validator("content_hash")
    @classmethod
    def _validate_content_hash(cls, value: str) -> str:
        return _hex64(value, "content_hash")


# --------------------------------------------------------------------------------------
# Section 13 -- the failure taxonomy
#
# Declared before section 12's outcome structure because the `FAILURE` branch is typed
# directly on `FailureCode`; keeping the order faithful to the dependency avoids a forward
# reference that would leave the model unresolved until first use.
# --------------------------------------------------------------------------------------

FailureScope = Literal["whole_proposal", "per_candidate"]

FailureCode = Literal[
    "INVALID_INVOCATION",
    "MISSING_PREDECESSOR",
    "INVALID_PREDECESSOR_ID",
    "PREDECESSOR_NOT_REGISTERED",
    "PREDECESSOR_NOT_COMPLETE",
    "PREDECESSOR_STATUS_CONTRADICTION",
    "PREDECESSOR_COMPLETION_EVIDENCE_MISSING",
    "PREDECESSOR_EVIDENCE_INVALID",
    "PREDECESSOR_REPOSITORY_MISMATCH",
    "PREDECESSOR_BASELINE_MISMATCH",
    "PREDECESSOR_INCOMPLETE",
    "CONFLICTING_CURRENT_TASK",
    "UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED",
    "REPOSITORY_IDENTITY_MISMATCH",
    "DIRTY_BASELINE",
    "UPSTREAM_POLICY_FAILURE",
    "AUTHORITATIVE_SOURCE_MISSING",
    "MIRROR_CONTRADICTION",
    "MALFORMED_CANDIDATE",
    "DUPLICATE_CANDIDATE_CONFLICT",
    "UNKNOWN_CANDIDATE_TYPE",
    "DEPENDENCY_CYCLE",
    "STALE_COMPLETION_EVIDENCE",
    "INPUT_DRIFT",
    "PROMPT_VALIDATION_FAILURE",
    "SECRET_DETECTED",
    "PATH_ESCAPE",
    "SYMLINK_POLICY_VIOLATION",
    "PUBLICATION_CONFLICT",
    "PUBLICATION_FAILURE",
    "SECURITY_POLICY_FAILURE",
]

# Section 13's table verbatim: every code appears exactly once with exactly one scope. A dict
# literal is the enforcement mechanism -- a repeated key cannot carry two scopes -- and the
# test suite asserts this mapping's keys are exactly `FailureCode`'s members, so a code added
# to one and not the other fails loudly rather than silently defaulting to a scope.
FAILURE_SCOPES: dict[FailureCode, FailureScope] = {
    "INVALID_INVOCATION": "whole_proposal",
    "MISSING_PREDECESSOR": "whole_proposal",
    "INVALID_PREDECESSOR_ID": "whole_proposal",
    "PREDECESSOR_NOT_REGISTERED": "whole_proposal",
    "PREDECESSOR_NOT_COMPLETE": "whole_proposal",
    "PREDECESSOR_STATUS_CONTRADICTION": "whole_proposal",
    "PREDECESSOR_COMPLETION_EVIDENCE_MISSING": "whole_proposal",
    "PREDECESSOR_EVIDENCE_INVALID": "whole_proposal",
    "PREDECESSOR_REPOSITORY_MISMATCH": "whole_proposal",
    "PREDECESSOR_BASELINE_MISMATCH": "whole_proposal",
    "PREDECESSOR_INCOMPLETE": "whole_proposal",
    "CONFLICTING_CURRENT_TASK": "whole_proposal",
    "UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED": "whole_proposal",
    "REPOSITORY_IDENTITY_MISMATCH": "whole_proposal",
    "DIRTY_BASELINE": "whole_proposal",
    "UPSTREAM_POLICY_FAILURE": "whole_proposal",
    "AUTHORITATIVE_SOURCE_MISSING": "whole_proposal",
    "MIRROR_CONTRADICTION": "whole_proposal",
    "MALFORMED_CANDIDATE": "per_candidate",
    "DUPLICATE_CANDIDATE_CONFLICT": "per_candidate",
    "UNKNOWN_CANDIDATE_TYPE": "per_candidate",
    "DEPENDENCY_CYCLE": "per_candidate",
    "STALE_COMPLETION_EVIDENCE": "per_candidate",
    "INPUT_DRIFT": "whole_proposal",
    "PROMPT_VALIDATION_FAILURE": "whole_proposal",
    "SECRET_DETECTED": "whole_proposal",
    "PATH_ESCAPE": "whole_proposal",
    "SYMLINK_POLICY_VIOLATION": "whole_proposal",
    "PUBLICATION_CONFLICT": "whole_proposal",
    "PUBLICATION_FAILURE": "whole_proposal",
    "SECURITY_POLICY_FAILURE": "whole_proposal",
}


# --------------------------------------------------------------------------------------
# Section 12 -- the two-level outcome structure
# --------------------------------------------------------------------------------------

OutcomeClass = Literal["PROPOSAL_READY", "FAILURE"]

ResultVariant = Literal[
    "NO_ELIGIBLE_CANDIDATE",
    "RECOMMENDATION_READY",
    "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION",
    "INSUFFICIENT_EVIDENCE",
]


class ProposalReadyOutcome(SuccessorPlanningModel):
    """Generation succeeded; `result_variant` says what kind of success it was."""

    outcome_class: Literal["PROPOSAL_READY"]
    result_variant: ResultVariant


class FailureOutcome(SuccessorPlanningModel):
    """Generation failed closed; no proposal body beyond the refusal record."""

    outcome_class: Literal["FAILURE"]
    failure_code: FailureCode


# `PROPOSAL_READY` is not a peer of the four result variants -- it is the outer wrapper -- so
# the outcome is discriminated on `outcome_class` and never flattened into one string.
# `extra="forbid"` on both members is what makes the discrimination total: a `FAILURE`
# carrying a `result_variant`, or a `PROPOSAL_READY` carrying a `failure_code`, is rejected.
Outcome = Annotated[
    ProposalReadyOutcome | FailureOutcome,
    Field(discriminator="outcome_class"),
]


# --------------------------------------------------------------------------------------
# Section 16.1 -- the proposal artifact
# --------------------------------------------------------------------------------------

# Section 16.1: a fixed, non-templated string. No candidate, evidence source or configuration
# value can substitute for, append to or suppress it -- the model validator below re-asserts
# it byte-for-byte on every construction, including every load.
HUMAN_OWNER_ACTION_REQUIRED = (
    "Review this proposal as evidence only. It selects, registers and authorizes nothing. "
    "Any successor stage must be separately registered and authorized by the Human Owner "
    "through its own stage contract."
)


class PredecessorRegistryEvidence(SuccessorPlanningModel):
    """Registry reference, hash and status proving the predecessor exists and is COMPLETE."""

    registry_reference: EvidenceReference
    registry_status: str

    @field_validator("registry_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return _scalar(value, "registry_status", MAX_STATUS_CHARS)


class PredecessorStatusReconciliation(SuccessorPlanningModel):
    """The typed reconciliation across Registry, Task Queue and mirrors.

    `consistent` is recorded alongside the reconciled status so a disagreement is carried into
    the artifact as an explicit finding rather than silently resolved by trusting the
    higher-precedence source and discarding the disagreement (section 8).
    """

    registry_status: str
    task_queue_status: str
    mirror_status: str
    reconciled_status: str
    consistent: bool

    @field_validator("registry_status", "task_queue_status", "mirror_status", "reconciled_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return _scalar(value, "reconciliation status", MAX_STATUS_CHARS)


class EligibilityDecision(SuccessorPlanningModel):
    """One candidate's verdict plus the exact section 11 rule that produced it."""

    candidate_id: str
    lifecycle_status: LifecycleStatus
    rule_id: str
    reasons: list[str]

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, value: str) -> str:
        return _identifier(value, "candidate_id", _CANDIDATE_ID_RE, MAX_CANDIDATE_ID_CHARS)

    @field_validator("rule_id")
    @classmethod
    def _validate_rule_id(cls, value: str) -> str:
        return _identifier(value, "rule_id", _FINDING_CODE_RE, MAX_STATUS_CHARS)

    @field_validator("reasons")
    @classmethod
    def _validate_reasons(cls, value: list[str]) -> list[str]:
        for reason in value:
            _scalar(reason, "eligibility reason", MAX_MESSAGE_CHARS)
        _require_sorted_unique(value, "reasons", "reason text", bytewise=False)
        return value


class ProposalBlocker(SuccessorPlanningModel):
    """One live-re-resolved blocker, attributed to the candidate it gates."""

    blocker_id: str
    blocker_type: BlockerType
    live_status: str
    candidate_id: str

    @field_validator("blocker_id")
    @classmethod
    def _validate_blocker_id(cls, value: str) -> str:
        return _identifier(value, "blocker_id", _BLOCKER_ID_RE, MAX_CANDIDATE_ID_CHARS)

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, value: str) -> str:
        return _identifier(value, "candidate_id", _CANDIDATE_ID_RE, MAX_CANDIDATE_ID_CHARS)

    @field_validator("live_status")
    @classmethod
    def _validate_live_status(cls, value: str) -> str:
        return _scalar(value, "live_status", MAX_STATUS_CHARS)


class ProposalWarning(SuccessorPlanningModel):
    """A visible, non-fatal finding -- a redaction event, an authorization-shaped span."""

    code: str
    path_or_candidate_id: str
    message: str

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: str) -> str:
        return _identifier(value, "warning code", _FINDING_CODE_RE, MAX_STATUS_CHARS)

    @field_validator("path_or_candidate_id")
    @classmethod
    def _validate_subject(cls, value: str) -> str:
        return _scalar(value, "path_or_candidate_id", MAX_PATH_CHARS)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _scalar(value, "warning message", MAX_MESSAGE_CHARS)


class ProposalError(SuccessorPlanningModel):
    """One section 13 failure, attributed to the path or candidate it concerns."""

    code: FailureCode
    path_or_candidate_id: str
    message: str

    @field_validator("path_or_candidate_id")
    @classmethod
    def _validate_subject(cls, value: str) -> str:
        return _scalar(value, "path_or_candidate_id", MAX_PATH_CHARS)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _scalar(value, "error message", MAX_MESSAGE_CHARS)


class GenerationMetadata(SuccessorPlanningModel):
    """The separate, explicitly non-canonical envelope of section 16.3.

    Nothing in here may ever be read back into an eligibility, hashing or identity decision:
    it is excluded from `canonical_payload_bytes` precisely so wall-clock time can never
    reach a hash, and it exists for human and operational convenience only.
    """

    generated_at: str
    tool_version: str

    @field_validator("generated_at")
    @classmethod
    def _validate_generated_at(cls, value: str) -> str:
        if _UTC_TIMESTAMP_RE.fullmatch(value) is None:
            raise ValueError("generated_at must be a UTC ISO-8601 timestamp with a 'Z' suffix")
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError(f"generated_at is not a real UTC timestamp: {exc}") from exc
        return value

    @field_validator("tool_version")
    @classmethod
    def _validate_tool_version(cls, value: str) -> str:
        return _scalar(value, "tool_version", MAX_STATUS_CHARS)


class ProposalArtifact(SuccessorPlanningModel):
    """The single, versioned, hash-bound proposal artifact of section 16.1.

    Section 22 invariant 5 holds structurally rather than by convention: the schema has no
    field whose presence or value can be read as authorization, registration or task
    mutation. `authorization_status` is a fixed `Literal["NOT_AUTHORIZED"]` and
    `human_owner_action_required` is re-asserted against the module constant on every
    construction, so no document content can change either one.

    `proposal_hash` is format-checked here but deliberately not re-derived at the model layer:
    section 15's structural validation and section 16.4's load-time re-verification own that
    re-derivation, and both use `canonical_payload_bytes` below. `prompt_hash` and
    `proposal_id`, which have no such construction-order dependency, are bound here.
    """

    schema_version: Literal["1.0"] = "1.0"
    proposal_id: str
    repository_identity: RepositoryIdentity
    predecessor_stage_id: str
    predecessor_registry_evidence: PredecessorRegistryEvidence
    predecessor_completion_evidence: list[EvidenceReference]
    predecessor_status_reconciliation: PredecessorStatusReconciliation
    evidence_manifest: list[EvidenceReference]
    normalized_evidence_hash: str
    candidate_list: list[Candidate]
    eligibility_decisions: list[EligibilityDecision]
    blockers: list[ProposalBlocker]
    outcome: Outcome
    generated_prompt: str
    prompt_hash: str
    proposal_hash: str
    warnings: list[ProposalWarning]
    errors: list[ProposalError]
    authorization_status: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"
    human_owner_action_required: str = HUMAN_OWNER_ACTION_REQUIRED
    generation_metadata: GenerationMetadata

    @field_validator("proposal_id", "normalized_evidence_hash", "prompt_hash", "proposal_hash")
    @classmethod
    def _validate_digests(cls, value: str) -> str:
        return _hex64(value, "digest")

    @field_validator("predecessor_stage_id")
    @classmethod
    def _validate_predecessor(cls, value: str) -> str:
        return _identifier(value, "predecessor_stage_id", _STAGE_ID_RE, MAX_STATUS_CHARS)

    @field_validator("predecessor_completion_evidence", "evidence_manifest")
    @classmethod
    def _validate_evidence_order(cls, value: list[EvidenceReference]) -> list[EvidenceReference]:
        _require_sorted_unique([reference.path for reference in value], "evidence list", "path")
        return value

    @field_validator("candidate_list")
    @classmethod
    def _validate_candidate_order(cls, value: list[Candidate]) -> list[Candidate]:
        _require_sorted_unique(
            [candidate.candidate_id for candidate in value], "candidate_list", "candidate_id"
        )
        return value

    @field_validator("eligibility_decisions")
    @classmethod
    def _validate_decision_order(
        cls, value: list[EligibilityDecision]
    ) -> list[EligibilityDecision]:
        # Section 16.2 names the candidate ordering for every candidate-keyed list; the
        # per-candidate decisions are exactly such a list, so the same key applies.
        _require_sorted_unique(
            [decision.candidate_id for decision in value], "eligibility_decisions", "candidate_id"
        )
        return value

    @field_validator("blockers")
    @classmethod
    def _validate_blocker_order(cls, value: list[ProposalBlocker]) -> list[ProposalBlocker]:
        keys = [
            (blocker.blocker_id.encode("utf-8"), blocker.candidate_id.encode("utf-8"))
            for blocker in value
        ]
        if keys != sorted(keys):
            raise ValueError("blockers must be sorted by (blocker_id, candidate_id), ascending")
        if len(set(keys)) != len(keys):
            raise ValueError("blockers must not repeat a (blocker_id, candidate_id) pair")
        return value

    @field_validator("warnings")
    @classmethod
    def _validate_warning_order(cls, value: list[ProposalWarning]) -> list[ProposalWarning]:
        keys = [
            (warning.code.encode("utf-8"), warning.path_or_candidate_id.encode("utf-8"))
            for warning in value
        ]
        if keys != sorted(keys):
            raise ValueError(
                "warnings must be sorted by (code, path_or_candidate_id), never insertion order"
            )
        return value

    @field_validator("errors")
    @classmethod
    def _validate_error_order(cls, value: list[ProposalError]) -> list[ProposalError]:
        keys = [
            (error.code.encode("utf-8"), error.path_or_candidate_id.encode("utf-8"))
            for error in value
        ]
        if keys != sorted(keys):
            raise ValueError(
                "errors must be sorted by (code, path_or_candidate_id), never insertion order"
            )
        return value

    @field_validator("generated_prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        return _text_block(value, "generated_prompt", MAX_GENERATED_PROMPT_CHARS)

    @field_validator("human_owner_action_required")
    @classmethod
    def _validate_action_required(cls, value: str) -> str:
        if value != HUMAN_OWNER_ACTION_REQUIRED:
            raise ValueError("human_owner_action_required is fixed and cannot be overridden")
        return value

    @model_validator(mode="after")
    def _validate_bindings(self) -> "ProposalArtifact":
        if self.proposal_id != self.proposal_hash:
            raise ValueError("proposal_id must be the full, untruncated proposal_hash digest")
        digest = hashlib.sha256(self.generated_prompt.encode("utf-8")).hexdigest()
        if digest != self.prompt_hash:
            raise ValueError("prompt_hash does not match generated_prompt")
        if self.outcome.outcome_class == "PROPOSAL_READY" and self.errors:
            raise ValueError("errors are populated only on the FAILURE branch of the outcome")
        return self


def canonical_payload_bytes(artifact: ProposalArtifact) -> bytes:
    """Serialize the canonical, hash-bound proposal payload (section 16.2).

    Three fields are excluded. `proposal_hash` is the digest of these very bytes and cannot
    contain itself. `proposal_id` is excluded for the same reason and no other: section 16.1
    defines it as *the full `proposal_sha256` digest*, so it is that same digest under a
    second name, and including it would make the definition circular -- unsatisfiable rather
    than merely awkward. `generation_metadata` is excluded because it is the one place a
    wall-clock timestamp exists and section 16.2 excludes wall-clock time from every hashed
    field, full stop. Everything else -- including the embedded rendered prompt and the full
    repository identity -- is inside the digest.

    Serialization is `canonical_json` reused verbatim from the prompt package: UTF-8,
    NFC-normalized, `sort_keys=True`, `(",", ":")` separators, integers only with floats
    rejected outright. Identical inputs therefore always produce identical bytes, which is
    what makes `proposal_id` content-derived rather than clock- or order-derived.
    """
    payload = artifact.model_dump(exclude={"proposal_id", "proposal_hash", "generation_metadata"})
    return canonical_json(payload)
