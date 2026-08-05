"""The DEC-003 static authoritative candidate catalog reader (AUTO-015).

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 8 item 7
(the catalog is authoritative for *which candidates exist and their declared, catalog-frozen
fields*, never for a candidate's live eligibility), 9 (Candidate Source Policy resolved to
Option 1), 10.1 (the typed schema, parsing side), 10.2 (the fail-closed rules), 13 (the
failure taxonomy) and 16.2 (canonicalization and hashing).

Every candidate this module returns came from exactly one hand-authored, versioned catalog
file. Nothing here derives a candidate from prose, headings, comments, completion reports or
any historical document: DEC-003 fixes the policy to Option 1 and puts section 9's Option 2
bounded derivation outside the AUTO-015 MVP, so no second candidate source exists to read.
`AUTO-015-CANDIDATES.md` is the historical narrative decision-support document this catalog
was transcribed from and is never read at runtime.

Three fields the catalog file may appear to offer are deliberately not trusted:

* `lifecycle_status` is never read. Section 10.1 defines it as computed by section 11 at read
  time, never author-set, so an entry that declares it at all is `MALFORMED_CANDIDATE` rather
  than an entry whose declaration is quietly ignored.
* `blockers[].live_status` is carried verbatim as declared data only. Section 10.1 requires it
  to be re-resolved live against `OPEN_QUESTIONS.md` and completion-report status; this module
  never treats the frozen text as an answer.
* `content_hash` is re-derived from the entry's own canonical fields and compared before the
  entry is accepted (section 22 invariant 7: no hash is trusted at rest).

Scope of a failure follows section 13 exactly. A catalog that cannot be parsed as a *file* --
unreadable, not YAML, not a mapping, an unrecognized file-level `schema_version`, a header
field missing or unrecognized -- is `AUTHORITATIVE_SOURCE_MISSING`, whole-proposal, because
the catalog is itself a required authoritative source (section 8 item 7) and there is no safe
partial reading of it. Everything an individual entry can get wrong is per-candidate: that
entry is excluded with its reason recorded and every other entry is still evaluated.

This module computes no eligibility verdict and assigns no `lifecycle_status`. Section 10.2
states that a candidate participating in a dependency cycle, or naming an unmet dependency, is
marked `blocked`; that marking is section 11's computation over live evidence and is not made
here. :func:`resolve_dependency_graph` reports the cycle and the unmet dependency as typed
findings for that computation to consume.
"""

import hashlib
import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal, get_args

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.successor_planning.models import (
    _BIDIRECTIONAL_CONTROLS,
    FAILURE_SCOPES,
    MAX_MESSAGE_CHARS,
    MAX_STATUS_CHARS,
    BlockerType,
    Candidate,
    DependencyType,
    EvidenceReference,
    FailureCode,
    SourceKind,
    SuccessorPlanningModel,
    _relative_path,
    _require_sorted_unique,
    _scalar,
)
from ai_workflow_engine.successor_planning.redaction import redact_text
from ai_workflow_engine.successor_planning.snapshot import (
    InvalidInvocationError,
    _confine,
    normalize_evidence_text,
    read_evidence_bytes,
)

# --------------------------------------------------------------------------------------
# Supported versions and ceilings
# --------------------------------------------------------------------------------------

#: The one file-level catalog schema version this reader understands (section 10.2).
CATALOG_SCHEMA_VERSION = 1

#: The entry-level schema versions this reader understands (section 10.1).
#:
#: Section 16.2 allows a reader meeting a higher minor version to attempt a best-effort read
#: "for display purposes only", never as an authoritative input to eligibility. This module
#: produces only authoritative input, so the narrower half of that rule is the whole of it
#: here: an unrecognized entry version is `MALFORMED_CANDIDATE` and the entry is excluded. No
#: display-only reading is invented, because nothing in this milestone renders anything.
SUPPORTED_ENTRY_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})

#: Section 22 invariant 14: an explicit parse-complexity ceiling. A catalog naming more than
#: this many candidates fails the read rather than being parsed unboundedly.
MAX_CATALOG_ENTRIES = 512

KNOWN_SOURCE_KINDS: frozenset[str] = frozenset(get_args(SourceKind))
KNOWN_DEPENDENCY_TYPES: frozenset[str] = frozenset(get_args(DependencyType))
KNOWN_BLOCKER_TYPES: frozenset[str] = frozenset(get_args(BlockerType))

# Section 10.1's `content_hash`: SHA-256 over the candidate's own canonical fields, excluding
# `lifecycle_status` (computed, not part of the candidate's identity) and excluding the hash
# field itself (which cannot contain itself).
CANONICAL_CANDIDATE_FIELDS: frozenset[str] = frozenset({"lifecycle_status", "content_hash"})

_CATALOG_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


def _is_rejected_codepoint(code: int) -> bool:
    """Whether section 14.2 rejects this codepoint in a repository-sourced scalar.

    The bidirectional-control set is imported from this package's typed foundation rather than
    restated, so a second copy cannot drift away from the set the artifact models enforce.
    """
    return (
        code in _BIDIRECTIONAL_CONTROLS
        or code < 0x20
        or code == 0x7F
        or 0x80 <= code <= 0x9F
        or 0xD800 <= code <= 0xDFFF
    )


def safe_message(value: object) -> str:
    """Return `value` as one bounded, single-line, control-free diagnostic string.

    Findings quote repository-sourced text -- a rejected field's value, a parser's complaint
    about it -- and that text is untrusted (section 14.2). Every character class section 14.2
    rejects is replaced with `?` rather than dropped, so a payload cannot silently vanish from
    the record a Human Owner reads, and the result is bounded and NFC-normalized so it can be
    carried in a typed field at all.

    Truncation is acceptable here and only here: a finding message is a diagnostic, not a
    candidate field, so the section 14.2 "refuse rather than truncate" rule (which exists
    because a truncated *candidate* fragment could itself be attacker-shaped and would then be
    hashed and rendered as data) does not apply to the sentence describing the refusal.
    """
    collapsed = " ".join(str(value).split())
    # Section 22 invariant 2: a diagnostic that quotes a rejected field quotes repository-sourced
    # text, and this string is embedded in a persisted `warnings`/`errors` message. It therefore
    # passes through the redaction utility like every other document-sourced string. The
    # `[REDACTED:<pattern>]` marker left behind is itself the visible record of the event, so
    # nothing is dropped silently.
    redacted, _ = redact_text(collapsed)
    cleaned = "".join(
        "?" if _is_rejected_codepoint(ord(character)) else character for character in redacted
    )
    normalized = unicodedata.normalize("NFC", cleaned)[:MAX_MESSAGE_CHARS].strip()
    return normalized or "unspecified"


# --------------------------------------------------------------------------------------
# Typed, fail-closed errors (section 13 codes)
# --------------------------------------------------------------------------------------


class CatalogError(WorkflowEngineError):
    """Base whole-proposal catalog failure, tagged with its section 13 failure code."""

    code: ClassVar[FailureCode]


class CatalogSchemaError(CatalogError):
    """Section 10.2: the catalog cannot be safely parsed as a file at all.

    Section 13 gives `AUTHORITATIVE_SOURCE_MISSING` the meaning "a required document is
    absent, unreadable, or (for the candidate catalog specifically) fails file-level schema
    parsing", which is exactly this class of failure. Per-entry failures never reach here.

    The read failures below this level -- an absent file, an oversized file, a symlinked file,
    a path escaping the repository -- are raised by the snapshot module's own typed errors and
    deliberately propagate unwrapped, so one code is not re-derived from two places.
    """

    code: ClassVar[FailureCode] = "AUTHORITATIVE_SOURCE_MISSING"


class CatalogSecretError(CatalogError):
    """Section 13's `SECRET_DETECTED`: a secret shape redaction could not safely neutralize.

    Section 13 makes ordinary redaction a *warning* and reserves this failure for the case
    where neutralization does not succeed. That case is reachable here in exactly one way: the
    redacted form of a bounded section 10.1 field is no longer representable under that field's
    own typed contract -- a replacement marker pushing the value past its length ceiling, or two
    `required_owner_decisions` collapsing onto the same text. Section 14.2 forbids recovering by
    truncating or by quietly merging, so the invocation refuses instead.
    """

    code: ClassVar[FailureCode] = "SECRET_DETECTED"


# --------------------------------------------------------------------------------------
# Section 10.2 -- per-candidate findings
# --------------------------------------------------------------------------------------


class CandidateFinding(SuccessorPlanningModel):
    """One per-candidate section 10.2 finding, naming the candidate it excludes or gates.

    `candidate_id` carries the entry's own declared identifier where that identifier is usable
    text at all; an entry whose `candidate_id` is missing, non-textual or control-bearing is
    identified by its position instead (`entry[3]`), because a finding that cannot name its
    subject is not a finding a Human Owner can act on. The value is therefore validated as a
    bounded scalar rather than against the section 10.1 identifier grammar -- naming a
    grammar-violating identifier is precisely what some of these findings exist to do.
    """

    code: FailureCode
    candidate_id: str
    message: str
    entry_indices: list[int] = Field(default_factory=list)
    definitions: list[Candidate] = Field(default_factory=list)
    cycle: list[str] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _validate_scope(cls, value: FailureCode) -> FailureCode:
        # Section 13: every code has exactly one scope, and only a per-candidate code can be
        # attached to a candidate. A whole-proposal code arriving here would be a scope error
        # that silently downgraded a refusal into an exclusion.
        if FAILURE_SCOPES[value] != "per_candidate":
            raise ValueError(f"{value} is a whole-proposal code and is never a candidate finding")
        return value

    @field_validator("candidate_id")
    @classmethod
    def _validate_subject(cls, value: str) -> str:
        return _scalar(value, "finding candidate_id", MAX_STATUS_CHARS)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _scalar(value, "finding message", MAX_MESSAGE_CHARS)

    @field_validator("entry_indices")
    @classmethod
    def _validate_indices(cls, value: list[int]) -> list[int]:
        if any(index < 0 for index in value):
            raise ValueError("entry_indices must not be negative")
        if value != sorted(value):
            raise ValueError("entry_indices must be ascending")
        return value

    @field_validator("cycle")
    @classmethod
    def _validate_cycle(cls, value: list[str]) -> list[str]:
        for member in value:
            _scalar(member, "cycle member", MAX_STATUS_CHARS)
        _require_sorted_unique(value, "cycle", "candidate_id")
        return value


def _finding_keys(findings: Sequence[CandidateFinding]) -> list[tuple[bytes, bytes]]:
    return [
        (finding.code.encode("utf-8"), finding.candidate_id.encode("utf-8")) for finding in findings
    ]


def _sorted_findings(findings: Sequence[CandidateFinding]) -> list[CandidateFinding]:
    """Section 16.2 warning/error ordering: `(code, subject)`, never insertion order."""
    return sorted(
        findings,
        key=lambda finding: (finding.code.encode("utf-8"), finding.candidate_id.encode("utf-8")),
    )


# --------------------------------------------------------------------------------------
# Section 10.1 -- content hashing
# --------------------------------------------------------------------------------------


def candidate_content_hash(candidate: Candidate) -> str:
    """Re-derive one candidate's section 10.1 `content_hash` from its own canonical fields.

    `lifecycle_status` is excluded because section 10.1 excludes it: it is computed, never part
    of the candidate's own identity. `content_hash` is excluded because it is the digest of
    these very bytes. Serialization is `canonical_json` reused verbatim from the prompt package
    (NFC, sorted keys, `(",", ":")` separators, integers only), so the digest is reproducible
    from the catalog file's own text by anyone holding that primitive.
    """
    payload = candidate.model_dump(exclude=set(CANONICAL_CANDIDATE_FIELDS))
    return hashlib.sha256(canonical_json(payload)).hexdigest()


# --------------------------------------------------------------------------------------
# Section 22 invariant 2 -- secret redaction before a candidate leaves this module
# --------------------------------------------------------------------------------------

#: The placeholder a redacted candidate is built with before its own digest is re-derived. It
#: is never persisted: `candidate_content_hash` excludes `content_hash` from its own input, so
#: the placeholder cannot influence the digest computed over the redacted definition.
_PLACEHOLDER_CONTENT_HASH = "0" * 64


class CandidateRedaction(SuccessorPlanningModel):
    """One secret shape redacted out of one candidate, reported without carrying the secret.

    Section 22 invariant 2 requires a redaction event to be a visible finding rather than a
    silent substitution, and section 13 makes an ordinary, successful redaction a *warning*.
    Only the candidate, the pattern name and the number of occurrences are recorded, so this
    record is safe to embed in the persisted artifact.
    """

    candidate_id: str
    pattern_name: str
    occurrences: int

    @field_validator("candidate_id", "pattern_name")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        return _scalar(value, "redaction identifier", MAX_STATUS_CHARS)

    @field_validator("occurrences")
    @classmethod
    def _validate_occurrences(cls, value: int) -> int:
        if value < 1:
            raise ValueError("a recorded redaction has at least one occurrence")
        return value


def redact_candidate(candidate: Candidate) -> tuple[Candidate, list[CandidateRedaction]]:
    """Redact every repository-sourced free-text field of one candidate (section 22 invariant 2).

    Section 22 invariant 2 requires every string sourced from a governance document to pass
    through the redaction utility "before being embedded in any rendered span **or persisted
    field**". The catalog is such a document (section 8 item 7), and section 16.1 persists each
    candidate verbatim in `candidate_list`, so redaction has to happen here -- before a
    candidate leaves this module -- rather than only while rendering the prompt.

    Only the free-text fields can carry a secret at all: `title`, `mission`, each
    `required_owner_decisions` entry, and the two declared status strings. Every other field is
    a closed enum, a grammar-checked identifier, a repository-relative path, a digest or an
    integer, none of which can hold a credential the redaction patterns recognize.

    The redacted definition's `content_hash` is re-derived from its own canonical fields, so
    section 16.4's load-time re-derivation still succeeds and section 22 invariant 7 still holds
    over what was actually persisted. A candidate carrying no recognized secret shape is
    returned unchanged and keeps the digest the catalog file itself declared.
    """
    counts: dict[str, int] = {}

    def scrub(value: str) -> str:
        redacted, findings = redact_text(value)
        for finding in findings:
            counts[finding.pattern_name] = counts.get(finding.pattern_name, 0) + finding.occurrences
        return redacted

    payload: dict[str, Any] = candidate.model_dump()
    payload["title"] = scrub(str(payload["title"]))
    payload["mission"] = scrub(str(payload["mission"]))
    # Section 16.2 sorts `required_owner_decisions` lexicographically as plain strings, and the
    # sort key *is* the value, so the list is re-sorted after substitution rather than left in
    # an order the model would now refuse.
    payload["required_owner_decisions"] = sorted(
        scrub(str(decision)) for decision in payload["required_owner_decisions"]
    )
    for dependency in payload["dependencies"]:
        dependency["status"] = scrub(str(dependency["status"]))
    for blocker in payload["blockers"]:
        blocker["live_status"] = scrub(str(blocker["live_status"]))

    if not counts:
        return candidate, []

    payload["content_hash"] = _PLACEHOLDER_CONTENT_HASH
    try:
        draft = Candidate.model_validate(payload)
    except ValidationError as exc:
        raise CatalogSecretError(
            f"Redacting candidate {candidate.candidate_id} produced a definition section 10.1 "
            f"cannot represent, so the secret shape could not be safely neutralized: "
            f"{safe_message(exc)}"
        ) from exc
    redacted = draft.model_copy(update={"content_hash": candidate_content_hash(draft)})
    return redacted, [
        CandidateRedaction(
            candidate_id=candidate.candidate_id,
            pattern_name=name,
            occurrences=counts[name],
        )
        for name in sorted(counts)
    ]


# --------------------------------------------------------------------------------------
# Section 10.1 -- the catalog document
# --------------------------------------------------------------------------------------


class _CatalogHeader(SuccessorPlanningModel):
    """The catalog file's own header, closed to unrecognized fields.

    `authorization_status` is a fixed literal for the same reason the proposal artifact's is
    (section 22 invariant 9): a catalog that claimed to authorize anything would be authority
    confusion, and the fail-closed answer is to refuse the file rather than to read the claim
    and discard it.
    """

    schema_version: int
    catalog_id: str
    authorization_status: Literal["NOT_AUTHORIZED"]
    source_decision: str
    historical_source: str

    @field_validator("catalog_id")
    @classmethod
    def _validate_catalog_id(cls, value: str) -> str:
        _scalar(value, "catalog_id", MAX_STATUS_CHARS)
        if _CATALOG_ID_RE.fullmatch(value) is None:
            raise ValueError(f"catalog_id must match the grammar {_CATALOG_ID_RE.pattern!r}")
        return value

    @field_validator("source_decision")
    @classmethod
    def _validate_source_decision(cls, value: str) -> str:
        return _scalar(value, "source_decision", MAX_STATUS_CHARS)

    @field_validator("historical_source")
    @classmethod
    def _validate_historical_source(cls, value: str) -> str:
        return _relative_path(value, "historical_source")


class CatalogDocument(SuccessorPlanningModel):
    """One parsed static authoritative catalog: its header, its accepted candidates, findings.

    `candidates` holds only entries that parsed, validated, re-derived their own
    `content_hash`, and survived duplicate-conflict detection, in section 16.2 candidate order.
    `findings` holds one per-candidate record for every entry that did not, in section 16.2
    warning/error order. The two lists together account for every entry in the file: nothing is
    dropped without a record.
    """

    reference: EvidenceReference
    schema_version: int
    catalog_id: str
    authorization_status: Literal["NOT_AUTHORIZED"]
    source_decision: str
    historical_source: str
    entry_count: int
    candidates: list[Candidate]
    findings: list[CandidateFinding]
    redactions: list[CandidateRedaction] = Field(default_factory=list)

    @field_validator("entry_count")
    @classmethod
    def _validate_entry_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("entry_count must not be negative")
        return value

    @model_validator(mode="after")
    def _validate_ordering(self) -> "CatalogDocument":
        _require_sorted_unique(
            [candidate.candidate_id for candidate in self.candidates], "candidates", "candidate_id"
        )
        keys = _finding_keys(self.findings)
        if keys != sorted(keys):
            raise ValueError("findings must be sorted by (code, candidate_id), ascending")
        return self


# --------------------------------------------------------------------------------------
# Section 10.2 -- per-entry parsing
# --------------------------------------------------------------------------------------


def _entry_subject(entry: object, index: int) -> str:
    """Name the entry a finding is about, falling back to its position in the file."""
    if isinstance(entry, Mapping):
        declared = entry.get("candidate_id")
        if isinstance(declared, str):
            try:
                return _scalar(declared, "candidate_id", MAX_STATUS_CHARS)
            except ValueError:
                pass
    return f"entry[{index}]"


def _unknown_type_finding(
    entry: Mapping[str, Any], subject: str, index: int
) -> CandidateFinding | None:
    """Section 10.2: an unrecognized `source_kind`/`dependency_type`/`blocker_type`.

    Checked before full schema validation, because the typed schema would report an
    unrecognized enum member as an ordinary validation error and section 10.2 gives this case
    its own code and its own reason: a candidate whose dependency or blocker kind this reader
    does not understand cannot have its eligibility soundly computed, so it is excluded rather
    than evaluated with the unknown entry ignored.
    """
    source_kind = entry.get("source_kind")
    if isinstance(source_kind, str) and source_kind not in KNOWN_SOURCE_KINDS:
        return CandidateFinding(
            code="UNKNOWN_CANDIDATE_TYPE",
            candidate_id=subject,
            message=safe_message(f"unrecognized source_kind {source_kind!r}"),
            entry_indices=[index],
        )
    for field, type_key, known in (
        ("dependencies", "dependency_type", KNOWN_DEPENDENCY_TYPES),
        ("blockers", "blocker_type", KNOWN_BLOCKER_TYPES),
    ):
        items = entry.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            declared = item.get(type_key)
            if isinstance(declared, str) and declared not in known:
                return CandidateFinding(
                    code="UNKNOWN_CANDIDATE_TYPE",
                    candidate_id=subject,
                    message=safe_message(f"unrecognized {type_key} {declared!r}"),
                    entry_indices=[index],
                )
    return None


def parse_catalog_entry(entry: object, index: int) -> Candidate | CandidateFinding:
    """Parse one catalog entry into a candidate, or into the finding that excludes it.

    The checks run in the order section 10.2 distinguishes their codes: unknown *type* first
    (its own code), then everything else the typed schema refuses (`MALFORMED_CANDIDATE`),
    then the entry's own content hash.
    """
    subject = _entry_subject(entry, index)
    if not isinstance(entry, Mapping):
        return CandidateFinding(
            code="MALFORMED_CANDIDATE",
            candidate_id=subject,
            message=safe_message(f"catalog entry {index} is not a mapping"),
            entry_indices=[index],
        )
    if "lifecycle_status" in entry:
        # Section 10.1: computed by section 11, never author-set. An entry that declares it is
        # refused rather than read-and-ignored, so the file can never appear to have decided a
        # verdict that only live evidence decides.
        return CandidateFinding(
            code="MALFORMED_CANDIDATE",
            candidate_id=subject,
            message=safe_message("lifecycle_status is computed at read time and is never authored"),
            entry_indices=[index],
        )
    declared_version = entry.get("schema_version")
    if not isinstance(declared_version, str) or declared_version not in (
        SUPPORTED_ENTRY_SCHEMA_VERSIONS
    ):
        return CandidateFinding(
            code="MALFORMED_CANDIDATE",
            candidate_id=subject,
            message=safe_message(f"unsupported entry schema_version {declared_version!r}"),
            entry_indices=[index],
        )
    unknown_type = _unknown_type_finding(entry, subject, index)
    if unknown_type is not None:
        return unknown_type
    try:
        candidate = Candidate.model_validate(dict(entry))
    except ValidationError as exc:
        return CandidateFinding(
            code="MALFORMED_CANDIDATE",
            candidate_id=subject,
            message=safe_message(exc),
            entry_indices=[index],
        )
    derived = candidate_content_hash(candidate)
    if derived != candidate.content_hash:
        # Section 22 invariant 7: no hash is trusted at rest. An entry whose declared identity
        # does not match its own content is not a candidate whose definition can be relied on.
        return CandidateFinding(
            code="MALFORMED_CANDIDATE",
            candidate_id=subject,
            message=safe_message(
                f"content_hash {candidate.content_hash} does not match the re-derived {derived}"
            ),
            entry_indices=[index],
        )
    return candidate


# --------------------------------------------------------------------------------------
# Section 10.2 -- duplicates and conflicts
# --------------------------------------------------------------------------------------


class DuplicateResolution(SuccessorPlanningModel):
    """The outcome of section 10.2's duplicate rules over one candidate list."""

    candidates: list[Candidate]
    findings: list[CandidateFinding]

    @model_validator(mode="after")
    def _validate_ordering(self) -> "DuplicateResolution":
        _require_sorted_unique(
            [candidate.candidate_id for candidate in self.candidates], "candidates", "candidate_id"
        )
        keys = _finding_keys(self.findings)
        if keys != sorted(keys):
            raise ValueError("findings must be sorted by (code, candidate_id), ascending")
        return self


def detect_duplicate_conflicts(candidates: Sequence[Candidate]) -> DuplicateResolution:
    """Apply section 10.2's two duplicate rules.

    Same `candidate_id`, same `content_hash`: the same definition listed twice is deduplicated
    to one entry silently -- not an error and not a conflict. Because `content_hash` covers
    every canonical field and is re-derived before a candidate reaches here, equal hashes
    guarantee equal definitions, so deduplication cannot quietly discard a difference.

    Same `candidate_id`, different `content_hash`: `DUPLICATE_CANDIDATE_CONFLICT`,
    per-candidate. That identifier is excluded from eligibility entirely, both conflicting
    definitions are carried verbatim on the finding, and every other candidate continues to be
    evaluated. The conflict is never resolved by picking one definition.
    """
    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.candidate_id, []).append(candidate)

    accepted: list[Candidate] = []
    findings: list[CandidateFinding] = []
    for candidate_id, definitions in grouped.items():
        hashes = {definition.content_hash for definition in definitions}
        if len(hashes) == 1:
            accepted.append(definitions[0])
            continue
        findings.append(
            CandidateFinding(
                code="DUPLICATE_CANDIDATE_CONFLICT",
                candidate_id=candidate_id,
                message=safe_message(
                    f"{len(definitions)} definitions of {candidate_id} disagree: "
                    + ", ".join(sorted(hashes))
                ),
                definitions=list(definitions),
            )
        )
    return DuplicateResolution(
        candidates=sorted(accepted, key=lambda item: item.candidate_id.encode("utf-8")),
        findings=_sorted_findings(findings),
    )


# --------------------------------------------------------------------------------------
# Section 10.2 -- the dependency graph
# --------------------------------------------------------------------------------------


class DependencyEdge(SuccessorPlanningModel):
    """One candidate-to-candidate dependency edge, kept so no edge is silently dropped."""

    candidate_id: str
    depends_on: str

    @field_validator("candidate_id", "depends_on")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        return _scalar(value, "dependency edge endpoint", MAX_STATUS_CHARS)


class UnmetDependency(SuccessorPlanningModel):
    """One declared dependency that resolves to no known stage, subsystem or capability.

    Section 10.2 makes this candidate `blocked` "with the unmet dependency named". Section 13
    defines no failure code for it, and this contract may not be broadened, so the unmet
    dependency is named here as typed data for section 11's computation to act on rather than
    given an invented code.
    """

    candidate_id: str
    dependency_id: str
    dependency_type: DependencyType
    declared_status: str

    @field_validator("candidate_id", "dependency_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        return _scalar(value, "unmet dependency identifier", MAX_STATUS_CHARS)

    @field_validator("declared_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return _scalar(value, "declared dependency status", MAX_STATUS_CHARS)


class DependencyResolution(SuccessorPlanningModel):
    """Section 10.2's dependency findings over one candidate set."""

    edges: list[DependencyEdge]
    cycles: list[list[str]]
    unmet: list[UnmetDependency]
    findings: list[CandidateFinding]

    @model_validator(mode="after")
    def _validate_ordering(self) -> "DependencyResolution":
        keys = _finding_keys(self.findings)
        if keys != sorted(keys):
            raise ValueError("findings must be sorted by (code, candidate_id), ascending")
        return self


def _strongly_connected_components(
    nodes: Sequence[str], successors: Mapping[str, list[str]]
) -> list[list[str]]:
    """Tarjan's algorithm, iteratively, over a deterministic node and edge order.

    Iterative rather than recursive because the recursion depth would otherwise be the
    candidate count, and a catalog is bounded by :data:`MAX_CATALOG_ENTRIES`, not by three.
    """
    index_of: dict[str, int] = {}
    low_of: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0

    for root in nodes:
        if root in index_of:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, position = work.pop()
            if position == 0:
                index_of[node] = counter
                low_of[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            children = successors.get(node, [])
            while position < len(children):
                child = children[position]
                position += 1
                if child not in index_of:
                    work.append((node, position))
                    work.append((child, 0))
                    recursed = True
                    break
                if child in on_stack:
                    low_of[node] = min(low_of[node], index_of[child])
            if recursed:
                continue
            if low_of[node] == index_of[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
            if work:
                parent = work[-1][0]
                low_of[parent] = min(low_of[parent], low_of[node])
    return components


def resolve_dependency_graph(
    candidates: Sequence[Candidate],
    *,
    known_stages: Collection[str] = (),
    known_subsystems: Collection[str] = (),
    known_capabilities: Collection[str] = (),
) -> DependencyResolution:
    """Resolve every declared dependency and detect every cycle (section 10.2).

    A dependency resolves when its `dependency_id` names another candidate in this catalog, or
    when it appears in the caller-supplied set of known identifiers *for its own declared
    type*. The known sets come from live evidence -- the Stage Registry and Task Queue for
    stages, the repository's own subsystems and capabilities otherwise -- and default to empty,
    which is the fail-closed direction: with nothing known, every non-candidate dependency is
    reported unmet rather than assumed satisfied.

    A dependency naming another candidate is an edge. Every edge is kept in `edges`, including
    both directions of a mutual dependency, so no edge is silently dropped. A cycle is reported
    as its full strongly-connected component: that component is exactly the maximal set of
    candidates that can all reach each other, so it names every participant and every edge
    involved, whereas naming one elementary cycle path would have to choose one of
    combinatorially many and would hide the rest. Every participant gets its own
    `DEPENDENCY_CYCLE` finding carrying the full component.

    No `lifecycle_status` is assigned here. Section 10.2 marks a cycle participant and a
    candidate with an unmet dependency `blocked`; that is section 11's computation, and this
    function produces the evidence for it.
    """
    known_by_type: dict[str, frozenset[str]] = {
        "stage": frozenset(known_stages),
        "subsystem": frozenset(known_subsystems),
        "capability": frozenset(known_capabilities),
    }
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    nodes = sorted(candidate_ids, key=lambda value: value.encode("utf-8"))

    edges: list[DependencyEdge] = []
    unmet: list[UnmetDependency] = []
    successors: dict[str, list[str]] = {node: [] for node in nodes}
    for candidate in sorted(candidates, key=lambda item: item.candidate_id.encode("utf-8")):
        for dependency in candidate.dependencies:
            if dependency.dependency_id in candidate_ids:
                edges.append(
                    DependencyEdge(
                        candidate_id=candidate.candidate_id, depends_on=dependency.dependency_id
                    )
                )
                successors[candidate.candidate_id].append(dependency.dependency_id)
                continue
            if dependency.dependency_id in known_by_type[dependency.dependency_type]:
                continue
            unmet.append(
                UnmetDependency(
                    candidate_id=candidate.candidate_id,
                    dependency_id=dependency.dependency_id,
                    dependency_type=dependency.dependency_type,
                    declared_status=dependency.status,
                )
            )

    cycles: list[list[str]] = []
    for component in _strongly_connected_components(nodes, successors):
        members = sorted(component, key=lambda value: value.encode("utf-8"))
        self_dependent = len(members) == 1 and members[0] in successors[members[0]]
        if len(members) > 1 or self_dependent:
            cycles.append(members)
    cycles.sort(key=lambda members: [member.encode("utf-8") for member in members])

    findings = [
        CandidateFinding(
            code="DEPENDENCY_CYCLE",
            candidate_id=member,
            message=safe_message("participates in a dependency cycle over " + ", ".join(members)),
            cycle=members,
        )
        for members in cycles
        for member in members
    ]
    return DependencyResolution(
        edges=edges, cycles=cycles, unmet=unmet, findings=_sorted_findings(findings)
    )


# --------------------------------------------------------------------------------------
# Section 9 / 10.1 -- reading the catalog file
# --------------------------------------------------------------------------------------


def read_catalog(root: Path, relative: str) -> CatalogDocument:
    """Read, validate and hash the one static authoritative catalog file (sections 9, 10).

    `relative` is the catalog location a validated configuration names (section 4 item 8); no
    default location is assumed, because a missing or invalid configuration is a precondition
    failure rather than an assumed default. The file is opened through the same no-follow,
    size-bounded, symlink-refusing read discipline every other authoritative source uses
    (section 7.3 steps 2-7), and its content is normalized and hashed before it is parsed.
    """
    try:
        _relative_path(relative, "catalog path")
    except ValueError as exc:
        raise InvalidInvocationError(
            f"The configured catalog path {relative!r} is not a usable repository-relative "
            f"path: {exc}"
        ) from exc
    label = f"The candidate catalog {relative!r}"
    data, metadata = read_evidence_bytes(_confine(root, relative), label)
    text = normalize_evidence_text(data, label)
    reference = EvidenceReference(
        path=relative,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        size=metadata.st_size,
    )

    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CatalogSchemaError(f"{label} is not parsable YAML: {safe_message(exc)}") from exc
    if not isinstance(raw, Mapping):
        raise CatalogSchemaError(f"{label} must be a YAML mapping")
    declared_version = raw.get("schema_version")
    if declared_version != CATALOG_SCHEMA_VERSION:
        # Section 10.2: an unrecognized file-level version means the catalog cannot be safely
        # parsed at all, and the catalog is a required authoritative source (section 8 item 7).
        raise CatalogSchemaError(
            f"{label} declares schema_version {safe_message(declared_version)}, which this "
            f"reader does not support (expected {CATALOG_SCHEMA_VERSION})"
        )
    try:
        header = _CatalogHeader.model_validate(
            {key: value for key, value in raw.items() if key != "candidates"}
        )
    except ValidationError as exc:
        raise CatalogSchemaError(f"{label} has an invalid header: {safe_message(exc)}") from exc

    entries = raw.get("candidates")
    if not isinstance(entries, list):
        raise CatalogSchemaError(f"{label} must declare a `candidates` list")
    if len(entries) > MAX_CATALOG_ENTRIES:
        raise CatalogSchemaError(
            f"{label} declares {len(entries)} candidates, over the "
            f"{MAX_CATALOG_ENTRIES}-entry ceiling"
        )

    parsed: list[Candidate] = []
    findings: list[CandidateFinding] = []
    for index, entry in enumerate(entries):
        result = parse_catalog_entry(entry, index)
        if isinstance(result, Candidate):
            parsed.append(result)
        else:
            findings.append(result)

    resolution = detect_duplicate_conflicts(parsed)
    # Section 22 invariant 2: no candidate leaves this module carrying an unredacted secret
    # shape, because section 16.1 persists each one verbatim in `candidate_list`. Redaction runs
    # after duplicate resolution so section 10.2's conflict rule still compares the definitions
    # as the catalog actually authored them.
    accepted: list[Candidate] = []
    redactions: list[CandidateRedaction] = []
    for definition in resolution.candidates:
        redacted, events = redact_candidate(definition)
        accepted.append(redacted)
        redactions.extend(events)

    return CatalogDocument(
        reference=reference,
        schema_version=header.schema_version,
        catalog_id=header.catalog_id,
        authorization_status=header.authorization_status,
        source_decision=header.source_decision,
        historical_source=header.historical_source,
        entry_count=len(entries),
        candidates=accepted,
        findings=_sorted_findings([*findings, *resolution.findings]),
        redactions=redactions,
    )
