"""Review policy, the findings ledger and the one shared budget helper (AUTO-016 section 19).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 19 (the
default policy, its ceilings, the three separate durable counters and closure verification's
limitation to already-open blocker ids), section 18 (semantic contradictions are malformed, which
this module consumes rather than re-decides), section 22 invariant 11 (budget integrity), and
section 6 defects P-3 (inconsistent budget accounting) and P-4 (an unreachable retry constant).

One helper owns every counter
-----------------------------
:func:`consume_round` is the only function in this package that consumes a round budget, and it
cannot be called without an already-parsed result: its `result` parameter is one of the three typed
results `results.py` returns, and each of those exists only after the complete section 18 grammar
held. "A round is consumed only after a well-formed result parses" is therefore a property of the
signature rather than an ordering someone has to remember -- which is exactly defect P-3, where the
prototype incremented `correction_round` and `closure_round` ahead of their exit-code checks while
the review counter, three functions earlier, did not.

The round kind is derived from the result's own type (:func:`round_kind_of`), so a correction
result cannot be accounted against the review budget even by mistake.

Three counters that never conflate
----------------------------------
`review_attempts` counts invocations, `successful_review_rounds` counts reviews that returned a
well-formed verdict, and `provider_failure_count` counts failures. They are three distinct fields
of one frozen model moved by three distinct derivations, and each derivation builds a **new**
ledger rather than mutating one -- so no call site can alias one counter onto another. A provider
failure (authentication expiry, timeout, spawn failure, unparseable output) moves only the failure
counter; the recorded real run consumed a review budget to a `token_expired` failure and needed an
explicit recovery act to get it back (section 6), which is why this separation is a type-level
property here rather than a convention.

No ceiling this module cannot reach, and none it can raise
----------------------------------------------------------
Every limit :class:`ReviewPolicy` carries is consulted by :func:`consume_round` on the round it
bounds, so there is no vestigial constant of the `MAX_REVIEW_ATTEMPTS = 3` kind defect P-4 names --
a limit the prototype declared and no code path could ever reach. Attempts are counted and never
capped, so no unreachable attempt ceiling is introduced in its place. In the other direction the
policy is frozen and its bounds are `config.py`'s ceilings: no runtime path raises a configured
ceiling because no runtime path can write one (section 21 -- the ceilings exist for explicitness
and auditability, not as knobs).

What this module never does
---------------------------
It invokes no provider, runs no command, opens no file and writes no state. It transitions
nothing: every method returns a typed :class:`RoundDecision` carrying the new ledgers, and
`MilestoneRunnerApplication` remains the sole transition authority (section 10). It never marks a
blocker closed on a provider's say-so -- a correction result's `findings_addressed` is a claim, and
only a closure ruling on an already-open blocker id moves a finding's status.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.config import ReviewPolicySettings
from ai_workflow_engine.milestone_runner.models import (
    BLOCKING_SEVERITIES,
    DEFERRED_SEVERITIES,
    Finding,
    FindingSeverity,
    FindingStatus,
    MilestoneRunnerModel,
    ProviderFailureClass,
    ProviderRole,
    ReviewVerdict,
    RunRecord,
)
from ai_workflow_engine.milestone_runner.results import (
    ClosureResult,
    CorrectionResult,
    MalformedResult,
    MilestoneReportStatus,
    ReviewResult,
)

#: Section 19's default policy, stated once as the defaults of :class:`ReviewPolicy`. The matching
#: ceilings are `config.py`'s `MAX_*_CEILING` constants and are deliberately not restated here: a
#: second copy of a ceiling is a second thing to drift.
DEFAULT_MAX_FULL_REVIEWS: Final = 1
DEFAULT_MAX_CORRECTION_ROUNDS: Final = 1
DEFAULT_MAX_CLOSURE_REVIEWS: Final = 1
DEFAULT_MAX_BLOCKERS: Final = 3

#: Section 19's default severity split, ordered severest first so a rendered policy reads the way
#: the contract writes it. Which severities may appear in each list is `models.py`'s
#: `BLOCKING_SEVERITIES`/`DEFERRED_SEVERITIES`, so the split has one definition in the package.
DEFAULT_BLOCKING_SEVERITIES: Final[tuple[FindingSeverity, ...]] = (
    FindingSeverity.CRITICAL,
    FindingSeverity.HIGH,
)
DEFAULT_DEFER_SEVERITIES: Final[tuple[FindingSeverity, ...]] = (
    FindingSeverity.MEDIUM,
    FindingSeverity.LOW,
)


class _Immutable(MilestoneRunnerModel):
    """A closed, strict and **frozen** model.

    Frozen is the point: a ledger that cannot be written in place is a ledger no coordinator, no
    adapter and no caller can quietly adjust. Every derivation below constructs a new value, which
    is what makes "the three counters never alias" a demonstrable property rather than a claim.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# --------------------------------------------------------------------------------------
# Section 19 -- the vocabulary
# --------------------------------------------------------------------------------------


class RoundKind(StrEnum):
    """The three rounds section 19 gives a budget: one review, one correction, one closure."""

    REVIEW = "REVIEW"
    CORRECTION = "CORRECTION"
    CLOSURE = "CLOSURE"


class SeverityDisposition(StrEnum):
    """What a severity does under the policy: it blocks, or it is deferred and never blocks."""

    BLOCKS = "BLOCKS"
    DEFERS = "DEFERS"


class ReviewOutcome(StrEnum):
    """The typed decision a round yields. The application maps it to a run state; this module
    does not, because it is not the transition authority (section 10).

    `STOP` is the single stop outcome for every exhausted-budget and still-blocked case, because
    section 19 gives all of them the same destination -- the run stops and a human decides -- and
    coining finer names here would invent vocabulary the contract does not have.
    """

    APPROVED = "APPROVED"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    NEEDS_CLOSURE = "NEEDS_CLOSURE"
    CLEARED = "CLEARED"
    STOP = "STOP"


#: Which durable counter each round consumes. `review_attempts` and `provider_failure_count` are
#: deliberately absent: neither is a budget, and a mapping that named them would be the first step
#: towards conflating them with one (invariant 11).
ROUND_COUNTER_FIELDS: Final[Mapping[RoundKind, str]] = MappingProxyType(
    {
        RoundKind.REVIEW: "successful_review_rounds",
        RoundKind.CORRECTION: "correction_round",
        RoundKind.CLOSURE: "closure_round",
    }
)


class BudgetExhausted(WorkflowEngineError):
    """A round was offered against a budget that is already spent (section 19).

    Raised rather than absorbed: asking for a second review under a `max_full_reviews` of one is a
    caller error, and the fail-closed direction is to refuse it loudly. The alternative -- silently
    returning the ledger unchanged -- would let a run consume rounds it never had.
    """

    def __init__(self, kind: RoundKind, *, consumed: int, limit: int) -> None:
        super().__init__(
            f"The {kind.value} budget is exhausted: {consumed} of {limit} consumed. "
            "A ceiling is never raised at runtime (section 21)."
        )
        self.kind = kind
        self.consumed = consumed
        self.limit = limit


# --------------------------------------------------------------------------------------
# Section 19 -- the policy
# --------------------------------------------------------------------------------------


class ReviewPolicy(_Immutable):
    """Section 19's policy: three budgets, a blocker cap and the severity split.

    Constructed with no argument it **is** section 19's default policy -- `max_full_reviews` 1,
    `max_correction_rounds` 1, `max_closure_reviews` 1, `max_blockers` 3, Critical and High
    blocking, Medium and Low deferred.

    Validation is delegated to `config.ReviewPolicySettings` rather than restated: every value is
    round-tripped through the loader's own model, so a policy built in code is refused for exactly
    the reasons a configured one is -- a value above its ceiling, a severity in both lists, a
    severity in neither, a demoted blocking severity. One set of rules, one place to read them, and
    a runtime policy that can never be laxer than what the configuration loader would accept.
    """

    max_full_reviews: int = DEFAULT_MAX_FULL_REVIEWS
    max_correction_rounds: int = DEFAULT_MAX_CORRECTION_ROUNDS
    max_closure_reviews: int = DEFAULT_MAX_CLOSURE_REVIEWS
    max_blockers: int = DEFAULT_MAX_BLOCKERS
    blocking_severities: tuple[FindingSeverity, ...] = DEFAULT_BLOCKING_SEVERITIES
    defer_severities: tuple[FindingSeverity, ...] = DEFAULT_DEFER_SEVERITIES

    @field_validator("blocking_severities", "defer_severities", mode="before")
    @classmethod
    def _coerce_severities(cls, value: object) -> object:
        """Accept any sequence of severities and keep a tuple, because a frozen model holding a
        list is only half frozen."""
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_against_the_loader(self) -> "ReviewPolicy":
        try:
            ReviewPolicySettings(
                max_full_reviews=self.max_full_reviews,
                max_correction_rounds=self.max_correction_rounds,
                max_closure_reviews=self.max_closure_reviews,
                max_blockers=self.max_blockers,
                blocking_severities=list(self.blocking_severities),
                defer_severities=list(self.defer_severities),
            )
        except ValidationError as exc:
            raise ValueError(
                f"the review policy is not one the configuration allows: {exc}"
            ) from exc
        return self

    @classmethod
    def from_settings(cls, settings: ReviewPolicySettings) -> "ReviewPolicy":
        """The runtime policy for a validated configuration's `review_policy` section."""
        return cls(
            max_full_reviews=settings.max_full_reviews,
            max_correction_rounds=settings.max_correction_rounds,
            max_closure_reviews=settings.max_closure_reviews,
            max_blockers=settings.max_blockers,
            blocking_severities=tuple(settings.blocking_severities),
            defer_severities=tuple(settings.defer_severities),
        )

    def limit_for(self, kind: RoundKind) -> int:
        """How many rounds of `kind` this policy permits, in total, for the whole run."""
        if kind is RoundKind.REVIEW:
            return self.max_full_reviews
        if kind is RoundKind.CORRECTION:
            return self.max_correction_rounds
        return self.max_closure_reviews

    def disposition(self, severity: FindingSeverity) -> SeverityDisposition:
        """Whether `severity` blocks or is deferred under this policy."""
        if severity in self.blocking_severities:
            return SeverityDisposition.BLOCKS
        if severity in self.defer_severities:
            return SeverityDisposition.DEFERS
        # Unreachable while the split partitions every severity, which the loader's model
        # guarantees on construction. Kept as a refusal rather than a fallback: an unclassified
        # severity must never default to "does not block".
        raise ValueError(f"{severity.value} is classified neither blocking nor deferred")


#: Section 19's policy as written in the contract, for a caller that has no configuration in hand.
#: Used as the default of :func:`classify_severity`, :func:`consume_round` and
#: :class:`ReviewCoordinator`, so "the default policy" is one object rather than four restatements.
DEFAULT_REVIEW_POLICY: Final[ReviewPolicy] = ReviewPolicy()


def classify_severity(
    severity: FindingSeverity,
    *,
    policy: ReviewPolicy = DEFAULT_REVIEW_POLICY,
) -> SeverityDisposition:
    """Classify one severity as blocking or deferred (section 19).

    The single question the severity policy answers, asked in one place so no call site re-decides
    it. Medium and Low defer under every policy the loader accepts: `defer_severities` may only
    contain them, and `blocking_severities` may never drop Critical or High.
    """
    return policy.disposition(severity)


# --------------------------------------------------------------------------------------
# Section 19 -- the counters
# --------------------------------------------------------------------------------------


class BudgetLedger(_Immutable):
    """The five durable counters of section 19, as five separate non-negative fields.

    The field names are `RunRecord`'s, so a ledger and the run record it came from are the same
    five numbers under the same five names, and :meth:`counter_updates` needs no translation table.

    Nothing here is a budget on its own: :class:`ReviewPolicy` holds the limits and
    :func:`consume_round` is the only function that spends one. `review_attempts` has no limit at
    all -- attempts are counted so a failure is visible next to the budget it did not consume, and
    a cap no code path could reach is precisely defect P-4.
    """

    review_attempts: int = Field(default=0, ge=0)
    successful_review_rounds: int = Field(default=0, ge=0)
    provider_failure_count: int = Field(default=0, ge=0)
    correction_round: int = Field(default=0, ge=0)
    closure_round: int = Field(default=0, ge=0)

    @classmethod
    def of(cls, record: RunRecord) -> "BudgetLedger":
        """The five counters a durable run record already carries."""
        return cls(
            review_attempts=record.review_attempts,
            successful_review_rounds=record.successful_review_rounds,
            provider_failure_count=record.provider_failure_count,
            correction_round=record.correction_round,
            closure_round=record.closure_round,
        )

    def counter_updates(self) -> dict[str, int]:
        """The five counters as a mapping the application may publish. Data, never a transition."""
        return {name: int(getattr(self, name)) for name in sorted(type(self).model_fields)}

    def consumed(self, kind: RoundKind) -> int:
        """How many rounds of `kind` this ledger has already consumed."""
        return int(getattr(self, ROUND_COUNTER_FIELDS[kind]))

    def with_attempt(self) -> "BudgetLedger":
        """Count one provider invocation. Consumes no budget: an attempt is not a round."""
        return self._incremented("review_attempts")

    def with_provider_failure(self) -> "BudgetLedger":
        """Count one provider failure, whatever its class, and consume nothing.

        Section 19 names authentication expiry, timeout, spawn failure and unparseable output; all
        seven classes of `ProviderFailureClass` land here, because none of them returned the
        well-formed verdict a review budget pays for.
        """
        return self._incremented("provider_failure_count")

    def _incremented(self, field: str) -> "BudgetLedger":
        """Derive a new ledger with exactly one counter one higher.

        A fresh, revalidated model rather than an in-place write: the four other counters are
        copied by value, so a derivation cannot move a counter it did not name (invariant 11).
        """
        values = self.model_dump()
        values[field] = int(values[field]) + 1
        return BudgetLedger(**values)


def round_kind_of(result: ReviewResult | CorrectionResult | ClosureResult) -> RoundKind:
    """Which round a parsed result belongs to, decided by its type.

    The binding is the type rather than a caller-supplied label, so a correction result can never
    be accounted against the review budget and no call site has to be trusted to pass the right
    kind alongside the right result.
    """
    if isinstance(result, ReviewResult):
        return RoundKind.REVIEW
    if isinstance(result, CorrectionResult):
        return RoundKind.CORRECTION
    return RoundKind.CLOSURE


def remaining_rounds(
    ledger: BudgetLedger,
    kind: RoundKind,
    *,
    policy: ReviewPolicy = DEFAULT_REVIEW_POLICY,
) -> int:
    """How many rounds of `kind` remain. Never negative, and never raises a ceiling."""
    return max(policy.limit_for(kind) - ledger.consumed(kind), 0)


def consume_round(
    ledger: BudgetLedger,
    result: ReviewResult | CorrectionResult | ClosureResult,
    *,
    policy: ReviewPolicy = DEFAULT_REVIEW_POLICY,
) -> BudgetLedger:
    """Consume exactly one round budget for an already-parsed result (section 19, defect P-3).

    The one shared budget-accounting helper. It takes a *parsed* result -- a value that exists only
    because the section 18 grammar and every semantic rule already held -- so there is no ordering
    in which a counter moves before a result parses. A provider failure never reaches this function
    at all: it has no parsed result to bring, and :meth:`BudgetLedger.with_provider_failure` is
    where it goes instead.

    Exactly one counter moves, by exactly one, chosen from the result's own type. Raises
    :class:`BudgetExhausted` when the round's budget is already spent; no path here raises the
    ceiling to make room.
    """
    kind = round_kind_of(result)
    limit = policy.limit_for(kind)
    consumed = ledger.consumed(kind)
    if consumed >= limit:
        raise BudgetExhausted(kind, consumed=consumed, limit=limit)
    return ledger._incremented(ROUND_COUNTER_FIELDS[kind])


# --------------------------------------------------------------------------------------
# Section 19 -- the findings ledger
# --------------------------------------------------------------------------------------


class FindingsLedger(_Immutable):
    """The blocking and deferred findings of a run, and the only place a status moves.

    The two lists are separated by severity as a schema rule, exactly as `RunRecord` separates
    them: a Medium or Low finding cannot be filed as a blocker and a Critical or High one cannot be
    filed as deferred, so "Medium and Low never block" holds because the other arrangement is
    unrepresentable rather than because a check somewhere rejected it.

    A deferred finding is `DEFERRED` and stays that way. Only :meth:`apply_closure` moves a status,
    only from `OPEN` to `CLOSED`, and only for an id that is already an open blocker.
    """

    blocking: tuple[Finding, ...] = ()
    deferred: tuple[Finding, ...] = ()

    @field_validator("blocking", "deferred", mode="before")
    @classmethod
    def _coerce_findings(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_ledger(self) -> "FindingsLedger":
        for finding in self.blocking:
            if finding.severity not in BLOCKING_SEVERITIES:
                raise ValueError(
                    f"blocking must not carry the {finding.severity.value} finding "
                    f"{finding.finding_id!r}; only "
                    f"{sorted(severity.value for severity in BLOCKING_SEVERITIES)} block"
                )
            if finding.status is FindingStatus.DEFERRED:
                raise ValueError(
                    f"the blocker {finding.finding_id!r} is DEFERRED; a blocking severity is "
                    "never deferred"
                )
        for finding in self.deferred:
            if finding.severity not in DEFERRED_SEVERITIES:
                raise ValueError(
                    f"deferred must not carry the {finding.severity.value} finding "
                    f"{finding.finding_id!r}; only "
                    f"{sorted(severity.value for severity in DEFERRED_SEVERITIES)} are deferred"
                )
            if finding.status is not FindingStatus.DEFERRED:
                raise ValueError(
                    f"the deferred finding {finding.finding_id!r} is {finding.status.value}; a "
                    "deferred finding is DEFERRED and never blocks"
                )
        identifiers = [finding.finding_id for finding in (*self.blocking, *self.deferred)]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("a finding id appears twice across blocking and deferred")
        return self

    @classmethod
    def of(cls, record: RunRecord) -> "FindingsLedger":
        """The two finding lists a durable run record already carries."""
        return cls(
            blocking=tuple(record.blocking_findings),
            deferred=tuple(record.deferred_findings),
        )

    @property
    def open_blocker_ids(self) -> tuple[str, ...]:
        """The already-open blocker ids -- the exact set closure verification is limited to."""
        return tuple(
            finding.finding_id for finding in self.blocking if finding.status is FindingStatus.OPEN
        )

    @property
    def closed_blocker_ids(self) -> tuple[str, ...]:
        return tuple(
            finding.finding_id
            for finding in self.blocking
            if finding.status is FindingStatus.CLOSED
        )

    @property
    def deferred_ids(self) -> tuple[str, ...]:
        return tuple(finding.finding_id for finding in self.deferred)

    @property
    def has_open_blockers(self) -> bool:
        return bool(self.open_blocker_ids)

    def record_updates(self) -> dict[str, list[Finding]]:
        """The two lists as a mapping the application may publish. Data, never a transition."""
        return {
            "blocking_findings": list(self.blocking),
            "deferred_findings": list(self.deferred),
        }

    def record_review(self, result: ReviewResult) -> "FindingsLedger":
        """File a parsed review's findings: blockers open, deferred findings deferred.

        The severity split is the parser's and this model's, never the reviewer's: a finding
        arrives in the list its severity permits, and filing it in the other one is not a value
        this ledger can hold.
        """
        known = set(self.open_blocker_ids) | set(self.closed_blocker_ids) | set(self.deferred_ids)
        for finding in (*result.blockers, *result.deferred):
            if finding.finding_id in known:
                raise MalformedResult(
                    f"The review reports {finding.finding_id!r}, which the run already records; "
                    "a review may not restate an existing finding id",
                    role=ProviderRole.REVIEW,
                )
        return FindingsLedger(
            blocking=(*self.blocking, *result.blockers),
            deferred=(*self.deferred, *result.deferred),
        )

    def apply_closure(self, result: ClosureResult) -> "FindingsLedger":
        """Apply a parsed closure result, strictly within the already-open blocker ids (section 19).

        A ruling on anything else -- a deferred finding, a blocker already closed, an id the run
        never saw -- is a rejection, because closure verification "may not introduce a new finding"
        and may not report on an id outside the open set. Silence is not a ruling: an open blocker
        the result does not mention stays open, which is what makes a partial closure a stop rather
        than a pass.
        """
        open_ids = set(self.open_blocker_ids)
        closing: set[str] = set()
        for ruling in result.findings:
            if ruling.id not in open_ids:
                raise MalformedResult(
                    f"The closure result rules on {ruling.id!r}, which is not one of the open "
                    f"blockers {sorted(open_ids)}; closure may not introduce a finding",
                    role=ProviderRole.CLOSURE,
                )
            if ruling.status is FindingStatus.CLOSED:
                closing.add(ruling.id)
            elif ruling.status is not FindingStatus.OPEN:
                raise MalformedResult(
                    f"The closure ruling on {ruling.id!r} is {ruling.status.value}; a closure "
                    "outcome is CLOSED or OPEN",
                    role=ProviderRole.CLOSURE,
                )
        updated = tuple(
            (
                finding.model_copy(update={"status": FindingStatus.CLOSED})
                if finding.finding_id in closing
                else finding
            )
            for finding in self.blocking
        )
        return FindingsLedger(blocking=updated, deferred=self.deferred)


# --------------------------------------------------------------------------------------
# Section 19 -- the coordinator
# --------------------------------------------------------------------------------------


class RoundDecision(_Immutable):
    """What one accepted round means, and the two ledgers it leaves behind.

    A decision, never a transition: the application reads `outcome`, decides which run state it
    implies and publishes `budget` and `findings`. Nothing here writes anything.
    """

    kind: RoundKind
    outcome: ReviewOutcome
    budget: BudgetLedger
    findings: FindingsLedger
    reason: str = Field(min_length=1)


class ReviewCoordinator:
    """Section 19's coordinator: the findings ledger, the severity policy and the round budgets.

    It consumes results that are already parsed and already validated -- it invokes no provider and
    re-decides nothing section 18 settled. Every accounting decision goes through
    :func:`consume_round`, so review, correction and closure are consumed by one rule.

    Three things it will not do, each an explicit exclusion of this milestone:

    * mark a blocker closed on a provider's say-so -- only a closure ruling on an already-open
      blocker id moves a status, and a correction round's `findings_addressed` moves nothing;
    * accept a second correction round -- if a blocker is still open once the correction budget is
      spent, the outcome is `STOP`;
    * transition anything -- it returns a :class:`RoundDecision` and the application decides.
    """

    def __init__(self, *, policy: ReviewPolicy = DEFAULT_REVIEW_POLICY) -> None:
        self._policy = policy

    @property
    def policy(self) -> ReviewPolicy:
        """The frozen policy this coordinator applies. No path here rewrites a limit."""
        return self._policy

    def record_review_attempt(self, budget: BudgetLedger) -> BudgetLedger:
        """Count one review invocation, before its result is known.

        `review_attempts` counts invocations and consumes nothing. It is the counter that diverges
        from `successful_review_rounds` under failure, which is the whole point of keeping them
        separate.
        """
        return budget.with_attempt()

    def record_provider_failure(
        self,
        budget: BudgetLedger,
        failure_class: ProviderFailureClass,
    ) -> BudgetLedger:
        """Count one provider failure. Consumes no review budget, whatever the class.

        `failure_class` is taken and not re-derived: section 17 fixes the class at invocation time
        and persists it, and defect P-10 is what re-deriving one from output text costs. It is
        recorded by the caller with the run; nothing about the accounting turns on which class it
        is, because none of the seven returned the verdict a review budget pays for.
        """
        return budget.with_provider_failure()

    def accept_review(
        self,
        budget: BudgetLedger,
        findings: FindingsLedger,
        result: ReviewResult,
    ) -> RoundDecision:
        """Account one well-formed review and decide what it means.

        Blockers open, Medium and Low findings deferred and never blocking. An approved review
        with no open blocker is `APPROVED`; a blocked one is `NEEDS_CORRECTION` while a correction
        round remains and `STOP` once it does not.
        """
        spent = consume_round(budget, result, policy=self._policy)
        filed = findings.record_review(result)
        if not filed.has_open_blockers:
            return RoundDecision(
                kind=RoundKind.REVIEW,
                outcome=ReviewOutcome.APPROVED,
                budget=spent,
                findings=filed,
                reason=(
                    f"The review returned {ReviewVerdict.APPROVED.value} with no open blocker; "
                    f"{len(filed.deferred)} deferred finding(s) do not block."
                ),
            )
        if remaining_rounds(spent, RoundKind.CORRECTION, policy=self._policy) > 0:
            return RoundDecision(
                kind=RoundKind.REVIEW,
                outcome=ReviewOutcome.NEEDS_CORRECTION,
                budget=spent,
                findings=filed,
                reason=(
                    f"The review left {len(filed.open_blocker_ids)} blocker(s) open: "
                    f"{list(filed.open_blocker_ids)}."
                ),
            )
        return RoundDecision(
            kind=RoundKind.REVIEW,
            outcome=ReviewOutcome.STOP,
            budget=spent,
            findings=filed,
            reason=(
                f"{len(filed.open_blocker_ids)} blocker(s) are open and no correction round "
                "remains."
            ),
        )

    def accept_correction(
        self,
        budget: BudgetLedger,
        findings: FindingsLedger,
        result: CorrectionResult,
    ) -> RoundDecision:
        """Account one well-formed correction round. It closes nothing.

        A correction result's `findings_addressed` is a claim about work done, not a verdict: every
        blocker stays exactly as open as it was, and only a closure verification may close one. The
        round is consumed because a well-formed result parsed -- a correction reporting `FAILED` is
        still a consumed round, and it stops the run rather than buying another one.
        """
        if not findings.has_open_blockers:
            raise ValueError(
                "a correction round presupposes at least one open blocker; this ledger has none"
            )
        spent = consume_round(budget, result, policy=self._policy)
        if result.status is not MilestoneReportStatus.COMPLETE:
            return RoundDecision(
                kind=RoundKind.CORRECTION,
                outcome=ReviewOutcome.STOP,
                budget=spent,
                findings=findings,
                reason=f"The correction round reported {result.status.value}.",
            )
        if remaining_rounds(spent, RoundKind.CLOSURE, policy=self._policy) > 0:
            return RoundDecision(
                kind=RoundKind.CORRECTION,
                outcome=ReviewOutcome.NEEDS_CLOSURE,
                budget=spent,
                findings=findings,
                reason=(
                    f"The correction round claims {len(result.findings_addressed)} finding(s) "
                    f"addressed; {list(findings.open_blocker_ids)} stay open until closure "
                    "verification rules on them."
                ),
            )
        return RoundDecision(
            kind=RoundKind.CORRECTION,
            outcome=ReviewOutcome.STOP,
            budget=spent,
            findings=findings,
            reason=(
                f"{len(findings.open_blocker_ids)} blocker(s) are open and no closure "
                "verification remains."
            ),
        )

    def accept_closure(
        self,
        budget: BudgetLedger,
        findings: FindingsLedger,
        result: ClosureResult,
    ) -> RoundDecision:
        """Account one well-formed closure verification, limited to the open blocker ids.

        A ruling outside the open set raises :class:`MalformedResult` and no decision is returned,
        so the caller's ledgers stay exactly as they were and the rejection is recorded the way
        every other malformed result is -- as a provider failure, never as a consumed round. The
        parser rejects such a result first; this is the same limit at the ledger, for a result
        built against some other run's open set.
        """
        spent = consume_round(budget, result, policy=self._policy)
        ruled = findings.apply_closure(result)
        if ruled.has_open_blockers:
            return RoundDecision(
                kind=RoundKind.CLOSURE,
                outcome=ReviewOutcome.STOP,
                budget=spent,
                findings=ruled,
                reason=(
                    f"Closure verification left {list(ruled.open_blocker_ids)} open; a blocker "
                    "still open after the correction round is a stop, not another round."
                ),
            )
        return RoundDecision(
            kind=RoundKind.CLOSURE,
            outcome=ReviewOutcome.CLEARED,
            budget=spent,
            findings=ruled,
            reason=(
                f"Closure verification closed {list(ruled.closed_blocker_ids)}; no blocker "
                "remains open."
            ),
        )
