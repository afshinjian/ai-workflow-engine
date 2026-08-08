"""The machine-result grammar and its fail-closed parsers (AUTO-016 section 18).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 18 (the
grammar and every parsing rule), section 19 (the semantic rules a verdict and a closure ruling
must satisfy), section 22 invariants 14, 15 and 18, and section 6 defects P-2 (an uncaught
`KeyError` in a caller) and P-8's sibling rule that a rejection destroys no evidence.

What a parser here is, and what it is not
-----------------------------------------
It is the boundary between untrusted provider text and the typed values the rest of the runner
reasons about. Nothing downstream of a parser reads a raw mapping: every field is required or
explicitly defaulted **here**, and the complete result is validated before the parser returns.
That is defect P-2 stated as a design rule -- the prototype's `parse_milestone_result` neither
required nor defaulted `milestone`, and two callers indexed `result["milestone"]` and produced a
traceback with no `stop_reason` recorded.

It is not an accountant. No parser increments a counter, consumes a budget, opens or closes a
finding, or transitions anything (section 19 keeps all of that in one shared helper elsewhere).
It runs no process, reads no file and writes nothing.

Fail-closed, in every direction
-------------------------------
* The body is parsed with `yaml.safe_load`, so no arbitrary object is ever constructed -- an
  unsafe construct raises at the loader rather than being built and then rejected.
* Each role has its own start/end sentinel pair, so a block produced for one role cannot be read
  as a result for another; a sentinel from another role's grammar anywhere in the text is a
  rejection.
* Exactly one optional Markdown fence is tolerated around the block -- the empirically observed
  case (section 6) -- and it weakens nothing else: the fence is stripped and the body still has to
  satisfy every rule. Two fences, a partial fence, text after the end sentinel, more than one
  block and a missing sentinel are each rejected.
* A semantic contradiction is malformed, not something to interpret: a `BLOCKED` verdict with no
  blockers, an `APPROVED` verdict carrying blockers, a blocker that is not Critical or High, more
  blockers than the configured `max_blockers`, and a closure ruling naming an unknown finding id.

Evidence survives every rejection
---------------------------------
:class:`MalformedResult` carries the transcript references it was given and deletes nothing. The
prompt, stdout and stderr transcripts were written by the provider boundary before any of this ran
(section 17a), and no code path here removes, rewrites or truncates one -- so a human can read
exactly what the provider said, from a stop record that names the files (invariant 15).
"""

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Final, TypeVar

import yaml
from pydantic import Field, ValidationError, field_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.models import (
    BLOCKING_SEVERITIES,
    DEFERRED_SEVERITIES,
    MAX_TEXT_CHARS,
    Finding,
    FindingSeverity,
    FindingStatus,
    MilestoneRunnerModel,
    ProviderRole,
    ProviderRunRecord,
    ReviewVerdict,
    normalize_repository_path,
)
from ai_workflow_engine.milestone_runner.prompts import RESULT_SENTINELS

#: The largest block body this module will parse. A result block is a small typed record; a body
#: beyond this is not one, and bounding it keeps an enormous provider output from becoming an
#: enormous YAML parse.
MAX_RESULT_BLOCK_CHARS: Final = 200_000

#: The most entries any list in a result may carry. Section 19 bounds blockers explicitly; every
#: other list is bounded here so no single field can be unbounded provider input.
MAX_RESULT_LIST_ITEMS: Final = 200

#: A Markdown fence line: three or more backticks, optionally followed by an info string on the
#: opening line. Matched on the whole stripped line, so a fence inside a YAML scalar is not one.
_FENCE_RE = re.compile(r"`{3,}[A-Za-z0-9_+-]*")

#: Every sentinel in section 18's grammar, whichever role it belongs to. A sentinel outside the
#: expected pair means the text is not the single block the caller asked for.
ALL_SENTINELS: Final[frozenset[str]] = frozenset(
    value for pair in RESULT_SENTINELS.values() for value in (pair.start, pair.end)
)

#: Every result model this module validates a block against, so one helper can carry the
#: "validate completely, then return a typed value" discipline for all four roles.
_ResultModelT = TypeVar("_ResultModelT", bound=MilestoneRunnerModel)


# --------------------------------------------------------------------------------------
# The typed rejection, and the evidence it carries
# --------------------------------------------------------------------------------------


class ResultTranscripts(MilestoneRunnerModel):
    """The run-relative transcript references a rejection has to keep pointing at (section 18).

    Paths, never content. The files themselves were written by the provider boundary before any
    parsing happened, and nothing in this module opens, rewrites or removes one.
    """

    prompt_path: str
    stdout_path: str
    stderr_path: str

    @classmethod
    def of(cls, record: ProviderRunRecord) -> "ResultTranscripts":
        """The transcript triple of one recorded provider invocation."""
        return cls(
            prompt_path=record.prompt_path,
            stdout_path=record.stdout_path,
            stderr_path=record.stderr_path,
        )


class MalformedResult(WorkflowEngineError):
    """A provider result does not satisfy section 18, in any of the ways section 18 names.

    One error class for the whole grammar, because a caller's response to every one of them is
    identical: stop, record the reason, and reference the transcripts. The reason travels as the
    message and the evidence travels as :attr:`transcripts`, so the stop record can name the exact
    files a human should read (invariant 15). Nothing here is a `KeyError`, an `AttributeError` or
    a `ValidationError` reaching a caller (defect P-2).
    """

    def __init__(
        self,
        message: str,
        *,
        role: ProviderRole | None = None,
        transcripts: ResultTranscripts | None = None,
    ) -> None:
        super().__init__(message)
        self.role = role
        self.transcripts = transcripts


# --------------------------------------------------------------------------------------
# Section 18 -- the grammar
# --------------------------------------------------------------------------------------


class MachineResultGrammar(MilestoneRunnerModel):
    """One role's start/end sentinel pair, and the rules for finding the block between them.

    The sentinels are read from `prompts.RESULT_SENTINELS` rather than restated, so the module
    that tells a provider which block to emit and the module that parses it cannot drift apart.
    """

    role: ProviderRole
    start: str
    end: str

    @classmethod
    def for_role(cls, role: ProviderRole) -> "MachineResultGrammar":
        pair = RESULT_SENTINELS[role]
        return cls(role=role, start=pair.start, end=pair.end)

    @property
    def foreign_sentinels(self) -> frozenset[str]:
        """Every sentinel that must not appear in a block emitted for this role."""
        return ALL_SENTINELS - {self.start, self.end}


def _is_fence(line: str) -> bool:
    return _FENCE_RE.fullmatch(line.strip()) is not None


def _sentinel_lines(lines: Sequence[str], sentinel: str) -> list[int]:
    """Indices of every line that *is* the sentinel, ignoring surrounding whitespace.

    Line-oriented on purpose. `END_AUTO016_MILESTONE_RESULT` contains
    `AUTO016_MILESTONE_RESULT` as a substring, so a substring search would count one end sentinel
    as a second start sentinel and reject every well-formed block.
    """
    return [index for index, line in enumerate(lines) if line.strip() == sentinel]


def extract_result_block(
    text: str,
    grammar: MachineResultGrammar,
    *,
    transcripts: ResultTranscripts | None = None,
) -> str:
    """Return the body between `grammar`'s sentinels, or raise :class:`MalformedResult`.

    The rules, in the order they are checked and exactly as section 18 states them:

    1. No sentinel from another role's grammar appears anywhere in the text.
    2. The start sentinel appears exactly once and the end sentinel appears exactly once, in that
       order -- so a missing sentinel, a mismatched pair and a second block are each a rejection.
    3. Nothing but blank lines follows the end sentinel, except at most one closing Markdown
       fence.
    4. A fence is tolerated only as a matched pair immediately wrapping the block, and only one
       such pair: an opening fence with no closing fence, a closing fence with no opening fence,
       and a doubled fence on either side are all rejections.

    Text *before* the block is not restricted: a provider narrating before its result block is the
    ordinary case, and section 18 restricts what follows the end sentinel rather than what
    precedes the start of the block.
    """

    def reject(reason: str) -> MalformedResult:
        return MalformedResult(reason, role=grammar.role, transcripts=transcripts)

    lines = text.splitlines()
    for foreign in sorted(grammar.foreign_sentinels):
        if _sentinel_lines(lines, foreign):
            raise reject(
                f"The text carries {foreign}, which belongs to another role's grammar; a "
                f"{grammar.role.value} result is delimited by {grammar.start} and {grammar.end} "
                "and by nothing else"
            )

    starts = _sentinel_lines(lines, grammar.start)
    ends = _sentinel_lines(lines, grammar.end)
    if not starts:
        raise reject(f"No {grammar.start} sentinel is present")
    if not ends:
        raise reject(f"No {grammar.end} sentinel is present")
    if len(starts) > 1 or len(ends) > 1:
        raise reject(
            f"Exactly one result block is admissible; found {len(starts)} start and "
            f"{len(ends)} end sentinel(s)"
        )
    start, end = starts[0], ends[0]
    if end < start:
        raise reject(f"{grammar.end} appears before {grammar.start}")

    before = [index for index in range(start) if lines[index].strip()]
    after = [index for index in range(end + 1, len(lines)) if lines[index].strip()]
    if len(after) > 1:
        raise reject(
            f"{len(after)} non-empty lines follow {grammar.end}; nothing but one optional closing "
            "fence may follow the end sentinel"
        )
    if after and not _is_fence(lines[after[0]]):
        raise reject(f"Text follows {grammar.end}: {lines[after[0]].strip()!r}")

    # Exactly one optional fence means exactly two fence lines in the whole text, and they must be
    # the two immediately around the block. Counting every fence line is what makes a partial
    # fence (an odd count) and a second fence anywhere (a count above two) each a rejection,
    # rather than only the two shapes that happen to sit adjacent to the sentinels.
    fences = [index for index, line in enumerate(lines) if _is_fence(line)]
    if fences:
        if len(fences) != 2:
            raise reject(
                "A Markdown fence is tolerated only as one matched pair around the block; this "
                f"text carries {len(fences)} fence lines"
            )
        opening, closing = fences
        if not before or before[-1] != opening or not after or after[0] != closing:
            raise reject(
                "A Markdown fence is tolerated only as a matched pair immediately around the "
                "block; this text's fence does not wrap it"
            )

    body = "\n".join(lines[start + 1 : end])
    if len(body) > MAX_RESULT_BLOCK_CHARS:
        raise reject(
            f"The result block is {len(body)} characters, above the "
            f"{MAX_RESULT_BLOCK_CHARS}-character ceiling"
        )
    return body


def _load_block(
    text: str, grammar: MachineResultGrammar, transcripts: ResultTranscripts | None
) -> dict[str, Any]:
    """Extract the block and load its body with a **safe** YAML loader.

    `yaml.safe_load` refuses an unsafe construct at the loader: a `!!python/object/apply` tag
    raises rather than being constructed and then found unacceptable, so nothing a provider writes
    is ever executed on the way to being rejected.
    """
    body = extract_result_block(text, grammar, transcripts=transcripts)
    try:
        document: Any = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise MalformedResult(
            f"The {grammar.role.value} result block is not valid YAML for a safe loader: {exc}",
            role=grammar.role,
            transcripts=transcripts,
        ) from exc
    if not isinstance(document, dict):
        raise MalformedResult(
            f"The {grammar.role.value} result block must be a YAML mapping at its root",
            role=grammar.role,
            transcripts=transcripts,
        )
    mapping: dict[str, Any] = document
    for key in mapping:
        if not isinstance(key, str):
            raise MalformedResult(
                f"The {grammar.role.value} result block has a non-string key {key!r}",
                role=grammar.role,
                transcripts=transcripts,
            )
    return mapping


def _validate(
    model: type["_ResultModelT"],
    mapping: dict[str, Any],
    grammar: MachineResultGrammar,
    transcripts: ResultTranscripts | None,
) -> "_ResultModelT":
    """Validate the whole mapping against a closed model, before any caller reads a field."""
    try:
        return model.model_validate(mapping)
    except ValidationError as exc:
        raise MalformedResult(
            f"The {grammar.role.value} result block is not a valid {model.__name__}: {exc}",
            role=grammar.role,
            transcripts=transcripts,
        ) from exc


# --------------------------------------------------------------------------------------
# Shared field grammar
# --------------------------------------------------------------------------------------


def _as_enum(value: Any, enum_class: type[StrEnum]) -> Any:
    """Resolve a YAML scalar to a closed-enum member before strict validation sees it.

    A result block holds strings, and naming a closed enum's member by its value is a lookup
    rather than a coercion. An unknown value raises here, which is the fail-closed direction.
    """
    if isinstance(value, str):
        return enum_class(value)
    return value


def _as_list(value: Any) -> Any:
    """Read an explicit YAML null for a list field as the empty list.

    `blockers:` with nothing beneath it is how a provider spells an empty sequence in practice,
    and YAML gives that as `None`. Reading it as `[]` is a normalization of an *explicitly
    present* field, not a tolerance of a missing one: an absent key is still governed by the
    model's own required-or-defaulted rule, and no semantic check is weakened -- a `BLOCKED`
    verdict whose `blockers:` is null is still a contradiction and still rejected.
    """
    return [] if value is None else value


def _bounded_list(value: list[Any], field: str) -> list[Any]:
    if len(value) > MAX_RESULT_LIST_ITEMS:
        raise ValueError(
            f"{field} carries {len(value)} entries, above the {MAX_RESULT_LIST_ITEMS} ceiling"
        )
    return value


def _bounded_text(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} must not be empty or whitespace-only")
    if len(value) > MAX_TEXT_CHARS:
        raise ValueError(f"{field} must be at most {MAX_TEXT_CHARS} characters")
    return value


class MilestoneReportStatus(StrEnum):
    """The three statuses an implementation or correction result may report."""

    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ReportedVerificationStatus(StrEnum):
    """What a provider says one verification command did. Evidence, never authority.

    The runner re-runs every command itself (section 16); this value records what the provider
    claimed, so a claim that disagrees with the runner's own observation is visible.
    """

    PASS = "PASS"
    FAIL = "FAIL"


class ReportedVerification(MilestoneRunnerModel):
    """One `command` / `result` pair as a provider reported it."""

    command: str
    result: ReportedVerificationStatus

    @field_validator("result", mode="before")
    @classmethod
    def _coerce_result(cls, value: Any) -> Any:
        return _as_enum(value, ReportedVerificationStatus)

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: str) -> str:
        return _bounded_text(value, "verification.command")


class AddressedFinding(MilestoneRunnerModel):
    """One finding a correction round says it addressed, and how."""

    id: str
    resolution: str

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _bounded_text(value, "findings_addressed.id")

    @field_validator("resolution")
    @classmethod
    def _validate_resolution(cls, value: str) -> str:
        return _bounded_text(value, "findings_addressed.resolution")


class ReportedFinding(MilestoneRunnerModel):
    """One finding as a review reported it, in the block's own field names.

    Converted to a :class:`~ai_workflow_engine.milestone_runner.models.Finding` inside the parser,
    before it is returned, so no caller ever holds a half-validated finding.
    """

    id: str
    severity: FindingSeverity
    title: str
    summary: str

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, value: Any) -> Any:
        return _as_enum(value, FindingSeverity)

    def as_finding(self, status: FindingStatus) -> Finding:
        """Build the canonical typed finding, which validates the id, title and summary."""
        return Finding(
            finding_id=self.id,
            severity=self.severity,
            title=self.title,
            summary=self.summary,
            status=status,
        )


class ClosureRuling(MilestoneRunnerModel):
    """One closure decision: an already-open finding id, its new status, and why."""

    id: str
    status: FindingStatus
    reason: str

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value: Any) -> Any:
        return _as_enum(value, FindingStatus)

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        return _bounded_text(value, "findings.reason")


# --------------------------------------------------------------------------------------
# The four result models
# --------------------------------------------------------------------------------------


class MilestoneResult(MilestoneRunnerModel):
    """An implementation result (section 18's `AUTO016_MILESTONE_RESULT` block).

    `milestone` is **required**. That single word is defect P-2's whole correction: the prototype
    left it neither required nor defaulted, and a caller indexing `result["milestone"]` produced
    an uncaught `KeyError` with no `stop_reason` recorded. Here the absence is a typed rejection
    raised by the parser, before any caller reads anything.
    """

    milestone: str
    status: MilestoneReportStatus
    changed_paths: list[str] = Field(default_factory=list)
    verification: list[ReportedVerification] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value: Any) -> Any:
        return _as_enum(value, MilestoneReportStatus)

    @field_validator("changed_paths", "verification", "blockers", mode="before")
    @classmethod
    def _coerce_lists(cls, value: Any) -> Any:
        return _as_list(value)

    @field_validator("changed_paths")
    @classmethod
    def _validate_changed_paths(cls, value: list[str]) -> list[str]:
        _bounded_list(value, "changed_paths")
        return [
            normalize_repository_path(item, f"changed_paths[{index}]")
            for index, item in enumerate(value)
        ]

    @field_validator("verification", "blockers")
    @classmethod
    def _validate_lists(cls, value: list[Any]) -> list[Any]:
        return _bounded_list(value, "verification/blockers")

    @field_validator("blockers")
    @classmethod
    def _validate_blockers(cls, value: list[str]) -> list[str]:
        for index, item in enumerate(value):
            _bounded_text(item, f"blockers[{index}]")
        return value


class CorrectionResult(MilestoneRunnerModel):
    """A correction result (section 18's `AUTO016_CORRECTION_RESULT` block)."""

    status: MilestoneReportStatus
    findings_addressed: list[AddressedFinding] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    verification: list[ReportedVerification] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value: Any) -> Any:
        return _as_enum(value, MilestoneReportStatus)

    @field_validator("findings_addressed", "changed_paths", "verification", mode="before")
    @classmethod
    def _coerce_lists(cls, value: Any) -> Any:
        return _as_list(value)

    @field_validator("changed_paths")
    @classmethod
    def _validate_changed_paths(cls, value: list[str]) -> list[str]:
        _bounded_list(value, "changed_paths")
        return [
            normalize_repository_path(item, f"changed_paths[{index}]")
            for index, item in enumerate(value)
        ]

    @field_validator("findings_addressed", "verification")
    @classmethod
    def _validate_lists(cls, value: list[Any]) -> list[Any]:
        return _bounded_list(value, "findings_addressed/verification")


class ReviewResult(MilestoneRunnerModel):
    """A review result (section 18's `AUTO016_REVIEW_RESULT` block), already reconciled.

    The findings are canonical :class:`~ai_workflow_engine.milestone_runner.models.Finding`
    values, blockers `OPEN` and deferred `DEFERRED`, built inside the parser after every semantic
    rule of sections 18 and 19 held.
    """

    verdict: ReviewVerdict
    blockers: list[Finding] = Field(default_factory=list)
    deferred: list[Finding] = Field(default_factory=list)


class ClosureResult(MilestoneRunnerModel):
    """A closure result (section 18's `AUTO016_CLOSURE_RESULT` block).

    Strictly limited to the already-open blocker ids the caller supplied: a ruling naming anything
    else is malformed, which is section 19's "closure may not introduce a new finding" enforced at
    the parser rather than trusted to the reviewer.
    """

    findings: list[ClosureRuling] = Field(default_factory=list)

    @property
    def closed_ids(self) -> tuple[str, ...]:
        return tuple(ruling.id for ruling in self.findings if ruling.status is FindingStatus.CLOSED)

    @property
    def open_ids(self) -> tuple[str, ...]:
        return tuple(ruling.id for ruling in self.findings if ruling.status is FindingStatus.OPEN)


class _RawReviewBlock(MilestoneRunnerModel):
    """The review block exactly as written, before its findings become canonical ones."""

    verdict: ReviewVerdict
    blockers: list[ReportedFinding] = Field(default_factory=list)
    deferred: list[ReportedFinding] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, value: Any) -> Any:
        return _as_enum(value, ReviewVerdict)

    @field_validator("blockers", "deferred", mode="before")
    @classmethod
    def _coerce_lists(cls, value: Any) -> Any:
        return _as_list(value)

    @field_validator("blockers", "deferred")
    @classmethod
    def _validate_lists(cls, value: list[ReportedFinding]) -> list[ReportedFinding]:
        return _bounded_list(value, "blockers/deferred")


class _RawClosureBlock(MilestoneRunnerModel):
    """The closure block exactly as written, before its ids are checked against the open set."""

    findings: list[ClosureRuling] = Field(default_factory=list)

    @field_validator("findings", mode="before")
    @classmethod
    def _coerce_findings(cls, value: Any) -> Any:
        return _as_list(value)

    @field_validator("findings")
    @classmethod
    def _validate_findings(cls, value: list[ClosureRuling]) -> list[ClosureRuling]:
        return _bounded_list(value, "findings")


# --------------------------------------------------------------------------------------
# The four parsers
# --------------------------------------------------------------------------------------


def parse_milestone_result(
    text: str,
    *,
    expected_milestone_id: str | None = None,
    transcripts: ResultTranscripts | None = None,
) -> MilestoneResult:
    """Parse an implementation result, completely, before any caller reads a field.

    `expected_milestone_id`, when supplied, is checked: a result reporting on a different
    milestone than the one that was requested is malformed, because accepting it would let one
    milestone's evidence close another's.

    The section 18 contradiction rule is applied to the two fields that carry it here as well: a
    `BLOCKED` status with no blockers, and a `COMPLETE` status carrying blockers, are the same
    contradiction the contract names for a verdict, and are rejected the same way. This is the
    stricter reading of an ambiguity, never a broader tolerance.
    """
    grammar = MachineResultGrammar.for_role(ProviderRole.IMPLEMENTATION)
    mapping = _load_block(text, grammar, transcripts)
    result = _validate(MilestoneResult, mapping, grammar, transcripts)
    if expected_milestone_id is not None and result.milestone != expected_milestone_id:
        raise MalformedResult(
            f"The result reports on {result.milestone!r}, not on the requested "
            f"{expected_milestone_id!r}",
            role=grammar.role,
            transcripts=transcripts,
        )
    if result.status is MilestoneReportStatus.BLOCKED and not result.blockers:
        raise MalformedResult(
            "A BLOCKED milestone result must name at least one blocker",
            role=grammar.role,
            transcripts=transcripts,
        )
    if result.status is MilestoneReportStatus.COMPLETE and result.blockers:
        raise MalformedResult(
            "A COMPLETE milestone result must carry no blocker",
            role=grammar.role,
            transcripts=transcripts,
        )
    return result


def parse_correction_result(
    text: str, *, transcripts: ResultTranscripts | None = None
) -> CorrectionResult:
    """Parse a correction result, completely, before any caller reads a field."""
    grammar = MachineResultGrammar.for_role(ProviderRole.CORRECTION)
    mapping = _load_block(text, grammar, transcripts)
    result = _validate(CorrectionResult, mapping, grammar, transcripts)
    identifiers = [addressed.id for addressed in result.findings_addressed]
    if len(set(identifiers)) != len(identifiers):
        raise MalformedResult(
            "A correction result must not address the same finding twice",
            role=grammar.role,
            transcripts=transcripts,
        )
    return result


def parse_review_result(
    text: str,
    *,
    max_blockers: int,
    transcripts: ResultTranscripts | None = None,
) -> ReviewResult:
    """Parse a review result and reject every semantic contradiction sections 18 and 19 name.

    Four rejections, each a contradiction rather than a judgement call: a `BLOCKED` verdict with
    no blockers, an `APPROVED` verdict carrying blockers, a blocker whose severity is not Critical
    or High, and more blockers than the configured `max_blockers`. A deferred finding whose
    severity blocks is rejected for the same reason in the other direction -- a provider may not
    move a Critical finding out of the blocking list by filing it elsewhere.
    """
    if max_blockers < 1:
        raise ValueError("max_blockers must be at least 1")
    grammar = MachineResultGrammar.for_role(ProviderRole.REVIEW)
    mapping = _load_block(text, grammar, transcripts)
    raw = _validate(_RawReviewBlock, mapping, grammar, transcripts)

    def reject(reason: str) -> MalformedResult:
        return MalformedResult(reason, role=grammar.role, transcripts=transcripts)

    for blocker in raw.blockers:
        if blocker.severity not in BLOCKING_SEVERITIES:
            raise reject(
                f"Blocker {blocker.id!r} is {blocker.severity.value}; only "
                f"{sorted(severity.value for severity in BLOCKING_SEVERITIES)} block"
            )
    for entry in raw.deferred:
        if entry.severity not in DEFERRED_SEVERITIES:
            raise reject(
                f"Deferred finding {entry.id!r} is {entry.severity.value}, which blocks; a "
                "blocking severity cannot be filed as deferred"
            )
    if len(raw.blockers) > max_blockers:
        raise reject(
            f"The review reports {len(raw.blockers)} blockers, above the configured "
            f"maximum of {max_blockers}"
        )
    if raw.verdict is ReviewVerdict.BLOCKED and not raw.blockers:
        raise reject("A BLOCKED verdict must carry at least one blocker")
    if raw.verdict is ReviewVerdict.APPROVED and raw.blockers:
        raise reject("An APPROVED verdict must carry no blocker")

    identifiers = [finding.id for finding in (*raw.blockers, *raw.deferred)]
    if len(set(identifiers)) != len(identifiers):
        raise reject("A review must not report the same finding id twice")
    try:
        blockers = [blocker.as_finding(FindingStatus.OPEN) for blocker in raw.blockers]
        deferred = [entry.as_finding(FindingStatus.DEFERRED) for entry in raw.deferred]
    except ValidationError as exc:
        raise reject(f"A reported finding is not a valid finding: {exc}") from exc
    return ReviewResult(verdict=raw.verdict, blockers=blockers, deferred=deferred)


def parse_closure_result(
    text: str,
    *,
    open_finding_ids: Sequence[str],
    transcripts: ResultTranscripts | None = None,
) -> ClosureResult:
    """Parse a closure result, limited to the already-open blocker ids (section 19).

    A ruling naming an id outside `open_finding_ids` is malformed -- closure verification may mark
    an open blocker `CLOSED` or leave it open, and may not introduce a finding. A ruling with a
    status other than `CLOSED` or `OPEN` is malformed for the same reason: `DEFERRED` is a review
    judgement, not a closure outcome.

    Silence is not a ruling: an open id the result does not mention simply stays open, which is
    the caller's accounting and not this parser's to change.
    """
    grammar = MachineResultGrammar.for_role(ProviderRole.CLOSURE)
    mapping = _load_block(text, grammar, transcripts)
    raw = _validate(_RawClosureBlock, mapping, grammar, transcripts)

    def reject(reason: str) -> MalformedResult:
        return MalformedResult(reason, role=grammar.role, transcripts=transcripts)

    known = set(open_finding_ids)
    seen: set[str] = set()
    for ruling in raw.findings:
        if ruling.id not in known:
            raise reject(
                f"The closure result rules on {ruling.id!r}, which is not one of the open "
                f"findings {sorted(known)}; closure may not introduce a finding"
            )
        if ruling.id in seen:
            raise reject(f"The closure result rules on {ruling.id!r} twice")
        seen.add(ruling.id)
        if ruling.status is FindingStatus.DEFERRED:
            raise reject(
                f"The closure ruling on {ruling.id!r} is DEFERRED; a closure outcome is CLOSED "
                "or OPEN"
            )
    return ClosureResult(findings=list(raw.findings))
