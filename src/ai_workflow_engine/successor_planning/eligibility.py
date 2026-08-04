"""Deterministic eligibility and recommendation policy for AUTO-015.

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 11
(eligibility rules), 11.1 (DEC-004, exactly one eligible candidate), 11.2 (DEC-005, multiple
eligible candidates), 11.3 (general rules), 12 (the outcome taxonomy this module selects the
`PROPOSAL_READY` variant of), 13 (failure scopes), 18 (determinism) and 20 (state ownership).

This module is pure computation over already-read evidence. It performs no I/O, opens no
document, invokes no provider, and mutates no task, Registry or workflow state. Everything it
reads was handed to it: the parsed candidates, the live open-questions register, the
per-candidate findings section 10.2 produced, and the unmet dependencies the dependency graph
reported.

The line section 11 draws, exactly
----------------------------------
A blocker gates *authorization* only when the live register says so. `OPEN_QUESTIONS.md`
distinguishes an entry that "blocks stage X's authorization" from one that merely
"blocks/affects ... implementation", and section 11 draws its eligibility line on exactly that
distinction: an `Open` entry with no authorization-blocking statement does not make a candidate
ineligible. The catalog's own frozen `live_status` text is never the answer -- every blocker is
re-resolved against the register that was actually read this invocation, and a blocker the
register does not record at all is unresolvable rather than assumed harmless.

Only `open_question` blockers gate. Section 11 names "an authorization-blocking OD-# ... cited
against this candidate", and the typed `blocker_type` enum is what distinguishes those from the
`deferred_defect` (`D-#`) entries, which section 28 already reviewed and confirmed non-blocking
as a class. A deferred defect is still re-resolved and still carried into the artifact as
visible evidence; it simply never produces a verdict on its own.

Verdict precedence, and why it is ordered this way
--------------------------------------------------
A candidate can present more than one condition at once, so the precedence is fixed rather than
incidental:

1. `insufficient_evidence` -- a document this candidate's determination depends on is missing.
   This wins over every definite verdict because section 12 makes `NO_ELIGIBLE_CANDIDATE` mean
   "the evidence was sufficient to reach a definite verdict"; asserting `blocked` for a
   candidate whose supporting evidence is incomplete would claim more than the evidence
   supports. Claiming less is the narrower and the fail-closed direction.
2. `blocked` -- a dependency cycle, then an unmet dependency, then a live authorization-blocking
   `Open` question.
3. `deferred` -- structurally sound, but previously and explicitly dispositioned out of scope.
4. `eligible`.

`reasons` always carries every observed condition, not only the decisive one, so a verdict never
silently discards a fact; `rule_id` cites the single section 11 rule that produced the status.

The `unknown` lifecycle status is never produced here. Section 10.1 reserves it for a load-time
value outside the enum -- a validation failure, section 16.4 -- and a computed verdict is never
that.

What this module never does
---------------------------
It never ranks candidates, never selects one, never authorizes, registers or defers anything,
and never writes. Section 11.2 is implemented as its own explicit branch precisely so no
ordering of the eligible set can be mistaken for a preference: with more than one eligible
candidate the answer is "all of them, and no recommendation".
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, field_validator, model_validator

from ai_workflow_engine.successor_planning.catalog import (
    CandidateFinding,
    UnmetDependency,
    safe_message,
)
from ai_workflow_engine.successor_planning.models import (
    MAX_MESSAGE_CHARS,
    MAX_STATUS_CHARS,
    Candidate,
    EligibilityDecision,
    ProposalBlocker,
    ResultVariant,
    SuccessorPlanningModel,
    _require_sorted_unique,
    _scalar,
)
from ai_workflow_engine.successor_planning.sources import OpenQuestionsDocument

# --------------------------------------------------------------------------------------
# Section 11 rule identifiers
#
# Each is the exact rule a verdict cites. The grammar is the artifact's own `rule_id` grammar
# (`^[A-Z][A-Z0-9_]*$`), so a verdict converts into an `EligibilityDecision` without any
# reshaping that could lose the citation.
# --------------------------------------------------------------------------------------

RULE_ELIGIBLE = "RULE_11_ELIGIBLE"
RULE_BLOCKED_AUTHORIZATION_QUESTION = "RULE_11_BLOCKED_AUTHORIZATION_QUESTION"
RULE_BLOCKED_DEPENDENCY_CYCLE = "RULE_11_BLOCKED_DEPENDENCY_CYCLE"
RULE_BLOCKED_UNMET_DEPENDENCY = "RULE_11_BLOCKED_UNMET_DEPENDENCY"
RULE_DEFERRED = "RULE_11_DEFERRED"
RULE_INSUFFICIENT_EVIDENCE = "RULE_11_INSUFFICIENT_EVIDENCE"

#: Every rule identifier this module can cite, for tests and for the prompt renderer.
SECTION_11_RULES: frozenset[str] = frozenset(
    {
        RULE_ELIGIBLE,
        RULE_BLOCKED_AUTHORIZATION_QUESTION,
        RULE_BLOCKED_DEPENDENCY_CYCLE,
        RULE_BLOCKED_UNMET_DEPENDENCY,
        RULE_DEFERRED,
        RULE_INSUFFICIENT_EVIDENCE,
    }
)

# --------------------------------------------------------------------------------------
# Live blocker statuses
#
# These are the re-resolved values, never the catalog's frozen text. The two `Open` forms are
# kept distinct because the register itself keeps them distinct and section 11's eligibility
# line runs exactly between them.
# --------------------------------------------------------------------------------------

LIVE_STATUS_BLOCKS_AUTHORIZATION = "Open (blocks authorization)"
LIVE_STATUS_AFFECTS_IMPLEMENTATION = "Open (affects implementation)"
LIVE_STATUS_RESOLVED = "Resolved"
LIVE_STATUS_UNRECORDED = "unrecorded"

#: Section 10.1's declared out-of-scope relation, and the only signal this module reads as the
#: Human Owner's own prior, explicit deferral of a candidate.
DEFERRED_MVP_RELATION = "outside_deferred"

# Section 10.2 findings that exclude a candidate before it can be evaluated at all. They never
# reach a verdict, because the catalog reader keeps such an entry out of its candidate list, but
# section 12 still counts them as definite "conflict" statuses when it picks a result variant.
CONFLICT_FINDING_CODES: frozenset[str] = frozenset(
    {"DUPLICATE_CANDIDATE_CONFLICT", "UNKNOWN_CANDIDATE_TYPE", "MALFORMED_CANDIDATE"}
)


# --------------------------------------------------------------------------------------
# Section 11.1 / 11.2 -- the fixed recommendation policy
# --------------------------------------------------------------------------------------

ADVISORY_RECOMMENDATION_NOTICE = (
    "Advisory only. This recommendation is evidence, never authority: it is not selection, "
    "registration, authorization, implementation permission, or Human Owner approval "
    "(DEC-004, section 11.1)."
)


class RecommendationPolicy(SuccessorPlanningModel):
    """The recommendation policy DEC-004 and DEC-005 fixed, as typed, frozen data.

    Frozen because it is a policy, not a setting: section 11.3 makes it a property of the
    contract that the tool never auto-selects and never ranks, so no caller may reach in and
    relax either. `ranking_permitted` and `auto_selection_permitted` are `Literal[False]`
    rather than plain booleans for the same reason `authorization_status` is a fixed literal on
    the artifact -- the type, not a convention, is what forbids the other value.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    exactly_one_eligible: Literal["ADVISORY_RECOMMENDATION"]
    multiple_eligible: Literal["RECOMMEND_NONE"]
    zero_eligible: Literal["RECOMMEND_NONE"]
    ranking_permitted: Literal[False]
    auto_selection_permitted: Literal[False]
    advisory_notice: str
    decision_references: tuple[str, ...]

    @field_validator("advisory_notice")
    @classmethod
    def _validate_notice(cls, value: str) -> str:
        return _scalar(value, "advisory_notice", MAX_MESSAGE_CHARS)


#: Section 11.1 (DEC-004) and section 11.2 (DEC-005), stated once.
RECOMMENDATION_POLICY = RecommendationPolicy(
    exactly_one_eligible="ADVISORY_RECOMMENDATION",
    multiple_eligible="RECOMMEND_NONE",
    zero_eligible="RECOMMEND_NONE",
    ranking_permitted=False,
    auto_selection_permitted=False,
    advisory_notice=ADVISORY_RECOMMENDATION_NOTICE,
    decision_references=("DEC-004", "DEC-005"),
)


# --------------------------------------------------------------------------------------
# Section 11 -- one candidate's verdict
# --------------------------------------------------------------------------------------

#: The four statuses a computation can produce. `unknown` is deliberately absent: section 10.1
#: reserves it for a load-time value outside the enum, which is a validation failure and never a
#: verdict.
VerdictStatus = Literal["eligible", "blocked", "deferred", "insufficient_evidence"]


class EligibilityVerdict(SuccessorPlanningModel):
    """One candidate's computed section 11 verdict, with its rule citation and live blockers.

    `blockers` holds every blocker the candidate declares, each re-resolved against the register
    read this invocation -- including the ones that turned out not to gate anything, because
    section 16.1 requires the artifact's blocker list to be the live-resolved set rather than
    only the subset that happened to be decisive.
    """

    candidate_id: str
    lifecycle_status: VerdictStatus
    rule_id: str
    reasons: list[str]
    blockers: list[ProposalBlocker]

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, value: str) -> str:
        return _scalar(value, "verdict candidate_id", MAX_STATUS_CHARS)

    @field_validator("rule_id")
    @classmethod
    def _validate_rule_id(cls, value: str) -> str:
        if value not in SECTION_11_RULES:
            raise ValueError(f"{value!r} is not a section 11 rule identifier")
        return value

    @field_validator("reasons")
    @classmethod
    def _validate_reasons(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("a verdict must cite at least one reason")
        for reason in value:
            _scalar(reason, "verdict reason", MAX_MESSAGE_CHARS)
        _require_sorted_unique(value, "reasons", "reason text", bytewise=False)
        return value

    @field_validator("blockers")
    @classmethod
    def _validate_blockers(cls, value: list[ProposalBlocker]) -> list[ProposalBlocker]:
        _require_sorted_unique(
            [blocker.blocker_id for blocker in value], "verdict blockers", "blocker_id"
        )
        return value

    @model_validator(mode="after")
    def _validate_attribution(self) -> "EligibilityVerdict":
        for blocker in self.blockers:
            if blocker.candidate_id != self.candidate_id:
                raise ValueError("every blocker on a verdict must name that verdict's candidate")
        return self

    def decision(self) -> EligibilityDecision:
        """This verdict as the artifact's own per-candidate decision record (section 16.1)."""
        return EligibilityDecision(
            candidate_id=self.candidate_id,
            lifecycle_status=self.lifecycle_status,
            rule_id=self.rule_id,
            reasons=list(self.reasons),
        )


def _live_blocker_status(blocker_id: str, open_questions: OpenQuestionsDocument) -> str:
    """Re-resolve one declared blocker against the register actually read (section 10.1)."""
    question = open_questions.question(blocker_id)
    if question is None:
        return LIVE_STATUS_UNRECORDED
    if question.status == "Resolved":
        return LIVE_STATUS_RESOLVED
    if question.blocks_authorization_of:
        return LIVE_STATUS_BLOCKS_AUTHORIZATION
    return LIVE_STATUS_AFFECTS_IMPLEMENTATION


def evaluate_candidate(
    candidate: Candidate,
    *,
    open_questions: OpenQuestionsDocument,
    findings: Sequence[CandidateFinding] = (),
    unmet_dependencies: Sequence[UnmetDependency] = (),
) -> EligibilityVerdict:
    """Compute one candidate's section 11 verdict from live evidence.

    `findings` and `unmet_dependencies` may cover the whole catalog; only the entries naming
    this candidate are consulted, so a caller never has to pre-filter and cannot pre-filter
    incorrectly.

    Nothing the catalog declared about a blocker's status is trusted: every blocker is
    re-resolved through :func:`_live_blocker_status` against `open_questions`, and a blocker the
    register does not record is `insufficient_evidence` rather than a blocker assumed harmless.
    """
    blockers: list[ProposalBlocker] = []
    gating: list[str] = []
    unresolvable: list[str] = []
    for declared in candidate.blockers:
        live_status = _live_blocker_status(declared.blocker_id, open_questions)
        blockers.append(
            ProposalBlocker(
                blocker_id=declared.blocker_id,
                blocker_type=declared.blocker_type,
                live_status=live_status,
                candidate_id=candidate.candidate_id,
            )
        )
        if declared.blocker_type != "open_question":
            continue
        if live_status == LIVE_STATUS_UNRECORDED:
            unresolvable.append(declared.blocker_id)
        elif live_status == LIVE_STATUS_BLOCKS_AUTHORIZATION:
            gating.append(declared.blocker_id)

    mine = [finding for finding in findings if finding.candidate_id == candidate.candidate_id]
    cycles = [finding for finding in mine if finding.code == "DEPENDENCY_CYCLE"]
    stale = [finding for finding in mine if finding.code == "STALE_COMPLETION_EVIDENCE"]
    unmet = [entry for entry in unmet_dependencies if entry.candidate_id == candidate.candidate_id]

    reasons: set[str] = set()
    for finding in stale:
        reasons.add(safe_message(f"Insufficient completion evidence: {finding.message}"))
    for blocker_id in unresolvable:
        reasons.add(
            safe_message(
                f"Blocker {blocker_id} is cited by this candidate but is not recorded in "
                f"{open_questions.reference.path}, so its live status cannot be resolved"
            )
        )
    for finding in cycles:
        reasons.add(
            safe_message(
                f"Dependency cycle over {', '.join(finding.cycle)} (section 10.2): "
                f"{finding.message}"
            )
        )
    for entry in unmet:
        reasons.add(
            safe_message(
                f"Unmet {entry.dependency_type} dependency {entry.dependency_id}, declared "
                f"{entry.declared_status}, resolves to no known stage, subsystem or capability"
            )
        )
    for blocker_id in gating:
        reasons.add(
            safe_message(
                f"Open question {blocker_id} is Open and blocks authorization per "
                f"{open_questions.reference.path}"
            )
        )

    status: VerdictStatus
    if stale or unresolvable:
        status, rule_id = "insufficient_evidence", RULE_INSUFFICIENT_EVIDENCE
    elif cycles:
        status, rule_id = "blocked", RULE_BLOCKED_DEPENDENCY_CYCLE
    elif unmet:
        status, rule_id = "blocked", RULE_BLOCKED_UNMET_DEPENDENCY
    elif gating:
        status, rule_id = "blocked", RULE_BLOCKED_AUTHORIZATION_QUESTION
    elif candidate.mvp_relation == DEFERRED_MVP_RELATION:
        status, rule_id = "deferred", RULE_DEFERRED
        reasons.add(
            safe_message(
                f"Declared mvp_relation {DEFERRED_MVP_RELATION}: the Human Owner previously and "
                "explicitly placed this candidate outside the current scope; carried forward as "
                "informational history, not a hard gate"
            )
        )
    else:
        status, rule_id = "eligible", RULE_ELIGIBLE
        reasons.add(
            safe_message(
                "No unresolved evidence gap, no dependency cycle, no unmet dependency and no "
                "authorization-blocking open question applies to this candidate"
            )
        )

    return EligibilityVerdict(
        candidate_id=candidate.candidate_id,
        lifecycle_status=status,
        rule_id=rule_id,
        reasons=sorted(reasons),
        blockers=sorted(blockers, key=lambda blocker: blocker.blocker_id.encode("utf-8")),
    )


# --------------------------------------------------------------------------------------
# Section 11.1 / 11.2 / 12 -- the whole-proposal result
# --------------------------------------------------------------------------------------


def result_variant_for(
    verdicts: Sequence[EligibilityVerdict], findings: Sequence[CandidateFinding] = ()
) -> ResultVariant:
    """Select section 12's `PROPOSAL_READY` variant from the computed verdicts.

    Exactly one eligible candidate is `RECOMMENDATION_READY` (DEC-004); more than one is
    `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION` (DEC-005), with no ranking applied to break the tie
    because no ranking policy is authorized anywhere.

    With none eligible, section 12's two remaining variants are deliberately distinguished:
    `NO_ELIGIBLE_CANDIDATE` requires at least one definite `blocked`/`deferred`/conflict status,
    where a "conflict" is a section 10.2 finding that excluded an entry from the candidate list
    before it could be evaluated at all. Everything else -- every candidate individually
    `insufficient_evidence`, or a catalog that yielded neither a candidate nor a conflict -- is
    the whole-proposal `INSUFFICIENT_EVIDENCE` variant, so a reader can tell "we know none of
    these are ready" from "we do not have enough evidence to know".
    """
    eligible = [verdict for verdict in verdicts if verdict.lifecycle_status == "eligible"]
    if len(eligible) == 1:
        return "RECOMMENDATION_READY"
    if len(eligible) > 1:
        return "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION"
    definite = any(
        verdict.lifecycle_status in {"blocked", "deferred"} for verdict in verdicts
    ) or any(finding.code in CONFLICT_FINDING_CODES for finding in findings)
    return "NO_ELIGIBLE_CANDIDATE" if definite else "INSUFFICIENT_EVIDENCE"


class EligibilityReport(SuccessorPlanningModel):
    """Every candidate's verdict plus the section 12 variant they select, in canonical order.

    `eligible_candidate_ids` is an ascending identifier list and carries no preference: section
    11.2 forbids ranking, so the order here is the same byte-wise candidate order every other
    list in the artifact uses and must never be read as "best first".
    """

    verdicts: list[EligibilityVerdict]
    eligible_candidate_ids: list[str]
    blockers: list[ProposalBlocker]
    result_variant: ResultVariant

    @model_validator(mode="after")
    def _validate_ordering(self) -> "EligibilityReport":
        _require_sorted_unique(
            [verdict.candidate_id for verdict in self.verdicts], "verdicts", "candidate_id"
        )
        _require_sorted_unique(
            self.eligible_candidate_ids, "eligible_candidate_ids", "candidate_id"
        )
        keys = [
            (blocker.blocker_id.encode("utf-8"), blocker.candidate_id.encode("utf-8"))
            for blocker in self.blockers
        ]
        if keys != sorted(keys):
            raise ValueError("blockers must be sorted by (blocker_id, candidate_id), ascending")
        if len(set(keys)) != len(keys):
            raise ValueError("blockers must not repeat a (blocker_id, candidate_id) pair")
        computed = {
            verdict.candidate_id
            for verdict in self.verdicts
            if verdict.lifecycle_status == "eligible"
        }
        if computed != set(self.eligible_candidate_ids):
            raise ValueError("eligible_candidate_ids must be exactly the eligible verdicts")
        return self

    def decisions(self) -> list[EligibilityDecision]:
        """Every verdict as the artifact's per-candidate decision record, in candidate order."""
        return [verdict.decision() for verdict in self.verdicts]

    def recommended_candidate_id(self) -> str | None:
        """The one candidate DEC-004 permits recommending, or `None` when policy permits none.

        `None` here is the *computation's* answer, not a field on any persisted record: section
        11.2 requires the recommendation to be structurally absent rather than null-valued, and
        the proposal assembler expresses that by choosing a record shape that has no
        `recommendation` field at all.
        """
        if self.result_variant != "RECOMMENDATION_READY":
            return None
        return self.eligible_candidate_ids[0]


def evaluate_all(
    candidates: Sequence[Candidate],
    *,
    open_questions: OpenQuestionsDocument,
    findings: Sequence[CandidateFinding] = (),
    unmet_dependencies: Sequence[UnmetDependency] = (),
) -> EligibilityReport:
    """Evaluate every candidate and select the section 12 result variant they produce.

    Deterministic by construction: the candidates are evaluated in ascending `candidate_id`
    order, every verdict depends only on its own candidate and the live evidence, and every list
    in the returned report carries its section 16.2 ordering. Repeating this call over identical
    inputs therefore produces an identical report, which is what makes the proposal hash
    content-derived rather than order-derived.
    """
    ordered = sorted(candidates, key=lambda candidate: candidate.candidate_id.encode("utf-8"))
    verdicts = [
        evaluate_candidate(
            candidate,
            open_questions=open_questions,
            findings=findings,
            unmet_dependencies=unmet_dependencies,
        )
        for candidate in ordered
    ]
    blockers = sorted(
        (blocker for verdict in verdicts for blocker in verdict.blockers),
        key=lambda blocker: (
            blocker.blocker_id.encode("utf-8"),
            blocker.candidate_id.encode("utf-8"),
        ),
    )
    return EligibilityReport(
        verdicts=verdicts,
        eligible_candidate_ids=[
            verdict.candidate_id for verdict in verdicts if verdict.lifecycle_status == "eligible"
        ],
        blockers=blockers,
        result_variant=result_variant_for(verdicts, findings),
    )
