"""AUTO-016 section 19: review policy, the findings ledger and the shared budget helper.

Everything here is driven the way the runner drives it. A result never arrives as a hand-built
model: each test writes the exact block text section 18 asks a provider for, hands it to the real
parser in `results.py`, and gives the coordinator what comes back -- so "a round is consumed only
after a well-formed result parses" is exercised across the real parse boundary rather than asserted
about a fixture. The ceiling refusal is proved against a real configuration file on disk read by
the production loader, not against a model constructed in memory.

The named classes the milestone requires are all present:
`TestProviderFailureDoesNotConsumeReviewBudget`, `TestSuccessfulReviewConsumesExactlyOne`,
`TestBudgetCeilingRefusedAtLoad`, `TestClosureLimitedToOpenBlockerIds`,
`TestClosureCannotIntroduceNewFinding`, `TestMediumLowDeferredNeverBlock`,
`TestThreeCountersNeverConflated`, plus the two prototype-defect regressions
`TestP3RoundConsumedOnlyAfterResultParses` (correction and closure, not just review) and
`TestP4NoUnreachableRetryCeiling`.
"""

import ast
import typing
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from ai_workflow_engine.milestone_runner.config import (
    MAX_BLOCKERS_CEILING,
    MAX_CLOSURE_REVIEWS_CEILING,
    MAX_CORRECTION_ROUNDS_CEILING,
    MAX_FULL_REVIEWS_CEILING,
    InvalidRunnerConfiguration,
    load_runner_config,
)
from ai_workflow_engine.milestone_runner.models import (
    RUN_COUNTER_FIELDS,
    Finding,
    FindingSeverity,
    FindingStatus,
    ProviderFailureClass,
    ProviderRole,
    ReviewVerdict,
)
from ai_workflow_engine.milestone_runner.prompts import RESULT_SENTINELS
from ai_workflow_engine.milestone_runner.results import (
    ClosureResult,
    ClosureRuling,
    CorrectionResult,
    MalformedResult,
    ReviewResult,
    parse_closure_result,
    parse_correction_result,
    parse_review_result,
)
from ai_workflow_engine.milestone_runner.review import (
    DEFAULT_REVIEW_POLICY,
    ROUND_COUNTER_FIELDS,
    BudgetExhausted,
    BudgetLedger,
    FindingsLedger,
    ReviewCoordinator,
    ReviewOutcome,
    ReviewPolicy,
    RoundDecision,
    RoundKind,
    SeverityDisposition,
    classify_severity,
    consume_round,
    remaining_rounds,
    round_kind_of,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REVIEW_SOURCE = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner" / "review.py"

#: The same disposable repository identity the M02-M05 suites pin, so every suite in this package
#: addresses one artifact root rather than inventing its own.
REPOSITORY_IDENTITY = "demo-repo--0123456789ab"


# --------------------------------------------------------------------------------------
# Real provider blocks, parsed by the real parsers
# --------------------------------------------------------------------------------------


def block(role: ProviderRole, body: str) -> str:
    """One well-formed result block for `role`, exactly as `prompts.py` asks for it."""
    sentinels = RESULT_SENTINELS[role]
    return f"{sentinels.start}\n{body}{sentinels.end}\n"


def review_text(
    *,
    verdict: ReviewVerdict,
    blockers: Sequence[tuple[str, FindingSeverity]] = (),
    deferred: Sequence[tuple[str, FindingSeverity]] = (),
) -> str:
    """The review block a Codex review would emit for these findings."""
    lines = [f"verdict: {verdict.value}"]
    for name, findings in (("blockers", blockers), ("deferred", deferred)):
        lines.append(f"{name}:")
        for identifier, severity in findings:
            lines.extend(
                [
                    f"  - id: {identifier}",
                    f"    severity: {severity.value}",
                    f"    title: Finding {identifier}",
                    f"    summary: The reviewer's account of {identifier}.",
                ]
            )
    return "\n".join(lines) + "\n"


def correction_text(
    *,
    status: str = "COMPLETE",
    addressed: Sequence[str] = ("R-1",),
) -> str:
    """The correction block a Claude correction round would emit."""
    lines = [f"status: {status}", "findings_addressed:"]
    for identifier in addressed:
        lines.extend([f"  - id: {identifier}", f"    resolution: {identifier} is addressed."])
    lines.extend(["changed_paths:", "  - src/ai_workflow_engine/milestone_runner/review.py"])
    return "\n".join(lines) + "\n"


def closure_text(rulings: Sequence[tuple[str, FindingStatus]]) -> str:
    """The closure block a Codex closure verification would emit."""
    lines = ["findings:"]
    for identifier, status in rulings:
        lines.extend(
            [
                f"  - id: {identifier}",
                f"    status: {status.value}",
                f"    reason: The closure verdict on {identifier}.",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_review(
    *,
    verdict: ReviewVerdict,
    blockers: Sequence[tuple[str, FindingSeverity]] = (),
    deferred: Sequence[tuple[str, FindingSeverity]] = (),
    max_blockers: int = 3,
) -> ReviewResult:
    body = review_text(verdict=verdict, blockers=blockers, deferred=deferred)
    return parse_review_result(block(ProviderRole.REVIEW, body), max_blockers=max_blockers)


def parse_correction(
    *, status: str = "COMPLETE", addressed: Sequence[str] = ("R-1",)
) -> CorrectionResult:
    return parse_correction_result(
        block(ProviderRole.CORRECTION, correction_text(status=status, addressed=addressed))
    )


def parse_closure(
    rulings: Sequence[tuple[str, FindingStatus]], *, open_ids: Sequence[str]
) -> ClosureResult:
    return parse_closure_result(
        block(ProviderRole.CLOSURE, closure_text(rulings)), open_finding_ids=open_ids
    )


BLOCKED_REVIEW_TEXT = block(
    ProviderRole.REVIEW,
    review_text(
        verdict=ReviewVerdict.BLOCKED,
        blockers=[("R-1", FindingSeverity.CRITICAL)],
        deferred=[("R-2", FindingSeverity.LOW)],
    ),
)


@pytest.fixture
def coordinator() -> ReviewCoordinator:
    """The coordinator under section 19's default policy -- the shipped configuration."""
    return ReviewCoordinator()


@pytest.fixture
def empty() -> tuple[BudgetLedger, FindingsLedger]:
    """A run that has reviewed nothing yet."""
    return BudgetLedger(), FindingsLedger()


@pytest.fixture
def blocked(
    coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
) -> RoundDecision:
    """One consumed review that left `R-1` open and deferred `R-2`."""
    budget, findings = empty
    return coordinator.accept_review(
        budget,
        findings,
        parse_review(
            verdict=ReviewVerdict.BLOCKED,
            blockers=[("R-1", FindingSeverity.CRITICAL)],
            deferred=[("R-2", FindingSeverity.LOW)],
        ),
    )


# --------------------------------------------------------------------------------------
# A real configuration file, read by the production loader
# --------------------------------------------------------------------------------------


def runner_config_payload(repository_root: Path, **review_policy: Any) -> dict[str, Any]:
    """A complete, valid section 21 configuration whose `review_policy` the caller may bend.

    Written out in full rather than imported from a shared fixture module, matching the M02-M05
    suites: a configuration a reader can see whole is worth more in a test about what a
    configuration may and may not say.
    """
    policy: dict[str, Any] = {
        "max_full_reviews": 1,
        "max_correction_rounds": 1,
        "max_closure_reviews": 1,
        "max_blockers": 3,
        "blocking_severities": ["CRITICAL", "HIGH"],
        "defer_severities": ["MEDIUM", "LOW"],
    }
    policy.update(review_policy)
    return {
        "schema_version": 1,
        "repository": {
            "root": str(repository_root),
            "identity": REPOSITORY_IDENTITY,
            "expected_branch": "feature/auto-016-milestone-runner",
            "baseline_sha": "4fa9212ff47171c162ddf863360413a90e0ee79f",
            "conda_environment": "ai-workflow-engine",
        },
        "stage": {
            "stage_id": "AUTO-016",
            "contract_path": "docs/workflow-automation/stage-prompts/AUTO-016.md",
            "contract_sha256": "0" * 64,
        },
        "allowlist": {
            "allowed_paths": ["src/ai_workflow_engine/milestone_runner/**"],
            "forbidden_paths": ["agentos_workflow/**", "self-governance.yaml"],
            "required_coverage": ["src/ai_workflow_engine/milestone_runner/review.py"],
        },
        "review_policy": policy,
        "providers": {
            "claude": {"executable": "claude", "arguments": ["-p"], "timeout_seconds": 3600},
            "codex": {"executable": "codex", "arguments": ["exec"], "timeout_seconds": 1800},
            "allowed_environment_variables": ["HOME", "PATH"],
        },
        "verification": {
            "focused": [],
            "final": [{"command": ["pytest", "-q"], "timeout_seconds": 1800}],
        },
    }


def write_config(tmp_path: Path, payload: dict[str, Any]) -> Path:
    """Write a real configuration file the production loader will read from disk."""
    repository = tmp_path / "repository"
    repository.mkdir(exist_ok=True)
    path = tmp_path / "runner.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------
# The policy
# --------------------------------------------------------------------------------------


class TestDefaultReviewPolicy:
    """Section 19's defaults, verbatim: one review, one correction, one closure, three blockers."""

    def test_the_defaults_are_the_contract_s(self) -> None:
        policy = ReviewPolicy()
        assert policy.max_full_reviews == 1
        assert policy.max_correction_rounds == 1
        assert policy.max_closure_reviews == 1
        assert policy.max_blockers == 3
        assert policy.blocking_severities == (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
        assert policy.defer_severities == (FindingSeverity.MEDIUM, FindingSeverity.LOW)

    def test_the_module_default_is_that_policy(self) -> None:
        assert DEFAULT_REVIEW_POLICY == ReviewPolicy()

    def test_each_round_limit_is_reported_for_its_own_kind(self) -> None:
        policy = ReviewPolicy(max_correction_rounds=0)
        assert policy.limit_for(RoundKind.REVIEW) == 1
        assert policy.limit_for(RoundKind.CORRECTION) == 0
        assert policy.limit_for(RoundKind.CLOSURE) == 1

    def test_a_configured_policy_becomes_the_runtime_policy(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, runner_config_payload(tmp_path / "repository"))
        config = load_runner_config(path)
        assert ReviewPolicy.from_settings(config.review_policy) == ReviewPolicy()

    def test_a_stricter_configured_policy_is_carried_through(self, tmp_path: Path) -> None:
        payload = runner_config_payload(
            tmp_path / "repository", max_correction_rounds=0, max_blockers=1
        )
        config = load_runner_config(write_config(tmp_path, payload))
        policy = ReviewPolicy.from_settings(config.review_policy)
        assert (policy.max_correction_rounds, policy.max_blockers) == (0, 1)


class TestSeverityPolicy:
    """Critical and High block; Medium and Low defer. One classification, one place."""

    @pytest.mark.parametrize(
        ("severity", "disposition"),
        [
            (FindingSeverity.CRITICAL, SeverityDisposition.BLOCKS),
            (FindingSeverity.HIGH, SeverityDisposition.BLOCKS),
            (FindingSeverity.MEDIUM, SeverityDisposition.DEFERS),
            (FindingSeverity.LOW, SeverityDisposition.DEFERS),
        ],
    )
    def test_each_severity_is_classified_as_section_19_says(
        self, severity: FindingSeverity, disposition: SeverityDisposition
    ) -> None:
        assert classify_severity(severity) is disposition

    def test_a_configuration_may_not_demote_a_blocking_severity(self) -> None:
        with pytest.raises(ValidationError, match="never demote"):
            ReviewPolicy(
                blocking_severities=(FindingSeverity.CRITICAL,),
                defer_severities=(
                    FindingSeverity.HIGH,
                    FindingSeverity.MEDIUM,
                    FindingSeverity.LOW,
                ),
            )

    def test_a_stricter_policy_may_promote_a_deferred_severity(self) -> None:
        policy = ReviewPolicy(
            blocking_severities=(
                FindingSeverity.CRITICAL,
                FindingSeverity.HIGH,
                FindingSeverity.MEDIUM,
            ),
            defer_severities=(FindingSeverity.LOW,),
        )
        disposition = classify_severity(FindingSeverity.MEDIUM, policy=policy)
        assert disposition is SeverityDisposition.BLOCKS

    def test_every_severity_must_be_classified(self) -> None:
        with pytest.raises(ValidationError, match="unclassified"):
            ReviewPolicy(
                blocking_severities=(FindingSeverity.CRITICAL, FindingSeverity.HIGH),
                defer_severities=(FindingSeverity.MEDIUM,),
            )


class TestBudgetCeilingRefusedAtLoad:
    """Section 19: a value above its ceiling is refused at load and the runner does not start."""

    @pytest.mark.parametrize(
        ("field", "ceiling"),
        [
            ("max_full_reviews", MAX_FULL_REVIEWS_CEILING),
            ("max_correction_rounds", MAX_CORRECTION_ROUNDS_CEILING),
            ("max_closure_reviews", MAX_CLOSURE_REVIEWS_CEILING),
            ("max_blockers", MAX_BLOCKERS_CEILING),
        ],
    )
    def test_a_configuration_above_a_ceiling_never_loads(
        self, tmp_path: Path, field: str, ceiling: int
    ) -> None:
        payload = runner_config_payload(tmp_path / "repository", **{field: ceiling + 1})
        path = write_config(tmp_path, payload)
        with pytest.raises(InvalidRunnerConfiguration, match=field):
            load_runner_config(path)

    @pytest.mark.parametrize(
        ("field", "ceiling"),
        [
            ("max_full_reviews", MAX_FULL_REVIEWS_CEILING),
            ("max_correction_rounds", MAX_CORRECTION_ROUNDS_CEILING),
            ("max_closure_reviews", MAX_CLOSURE_REVIEWS_CEILING),
            ("max_blockers", MAX_BLOCKERS_CEILING),
        ],
    )
    def test_a_policy_built_in_code_is_refused_for_the_same_reason(
        self, field: str, ceiling: int
    ) -> None:
        """A policy constructed without a configuration file cannot be laxer than one with it."""
        with pytest.raises(ValidationError, match="configuration allows"):
            ReviewPolicy(**{field: ceiling + 1})

    def test_the_refusal_happens_before_any_coordinator_exists(self, tmp_path: Path) -> None:
        """The stop is at load: there is no consumed round, no ledger and no partial run."""
        payload = runner_config_payload(tmp_path / "repository", max_full_reviews=2)
        with pytest.raises(InvalidRunnerConfiguration):
            load_runner_config(write_config(tmp_path, payload))

    def test_the_ceilings_are_section_19_s_defaults(self) -> None:
        assert (
            MAX_FULL_REVIEWS_CEILING,
            MAX_CORRECTION_ROUNDS_CEILING,
            MAX_CLOSURE_REVIEWS_CEILING,
            MAX_BLOCKERS_CEILING,
        ) == (1, 1, 1, 3)

    def test_a_ceiling_is_never_raised_at_runtime(self) -> None:
        """Section 21: the ceilings exist for auditability, not as knobs. The policy is frozen."""
        policy = ReviewPolicy()
        with pytest.raises(ValidationError):
            policy.max_full_reviews = 5  # type: ignore[misc]
        assert policy.max_full_reviews == 1

    def test_no_module_path_assigns_a_policy_limit(self) -> None:
        """AST: nothing in `review.py` writes a limit onto a policy."""
        tree = ast.parse(REVIEW_SOURCE.read_text(encoding="utf-8"))
        limits = set(ReviewPolicy.model_fields)
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AugAssign | ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute):
                    assert target.attr not in limits, f"review.py assigns {target.attr}"


# --------------------------------------------------------------------------------------
# The counters
# --------------------------------------------------------------------------------------


class TestSuccessfulReviewConsumesExactlyOne:
    """Section 19: exactly one successful review consumes exactly one review budget."""

    def test_one_parsed_review_consumes_one_budget(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        result = parse_review_result(BLOCKED_REVIEW_TEXT, max_blockers=3)
        decision = coordinator.accept_review(budget, findings, result)
        assert decision.budget.successful_review_rounds == 1
        assert decision.budget.counter_updates() == {
            "review_attempts": 0,
            "successful_review_rounds": 1,
            "provider_failure_count": 0,
            "correction_round": 0,
            "closure_round": 0,
        }

    def test_the_input_ledger_is_left_exactly_as_it_was(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        result = parse_review_result(BLOCKED_REVIEW_TEXT, max_blockers=3)
        coordinator.accept_review(budget, findings, result)
        assert budget == BudgetLedger()
        assert findings == FindingsLedger()

    def test_a_second_review_finds_the_budget_spent(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        with pytest.raises(BudgetExhausted) as raised:
            consume_round(blocked.budget, parse_review(verdict=ReviewVerdict.APPROVED))
        assert raised.value.kind is RoundKind.REVIEW
        assert (raised.value.consumed, raised.value.limit) == (1, 1)

    def test_an_approved_review_consumes_its_one_budget_too(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        decision = coordinator.accept_review(
            budget, findings, parse_review(verdict=ReviewVerdict.APPROVED)
        )
        assert decision.outcome is ReviewOutcome.APPROVED
        assert decision.budget.successful_review_rounds == 1


class TestProviderFailureDoesNotConsumeReviewBudget:
    """Section 19: a failure moves the failure counter and never the consumed-review counter."""

    @pytest.mark.parametrize("failure_class", list(ProviderFailureClass))
    def test_every_failure_class_leaves_the_review_budget_intact(
        self, coordinator: ReviewCoordinator, failure_class: ProviderFailureClass
    ) -> None:
        budget = coordinator.record_review_attempt(BudgetLedger())
        after = coordinator.record_provider_failure(budget, failure_class)
        assert after.counter_updates() == {
            "review_attempts": 1,
            "successful_review_rounds": 0,
            "provider_failure_count": 1,
            "correction_round": 0,
            "closure_round": 0,
        }

    @pytest.mark.parametrize(
        "failure_class",
        [
            ProviderFailureClass.AUTH_FAILED,
            ProviderFailureClass.TIMEOUT,
            ProviderFailureClass.SPAWN_FAILED,
            ProviderFailureClass.MALFORMED_OUTPUT,
        ],
    )
    def test_the_review_the_failure_cost_is_still_available(
        self,
        coordinator: ReviewCoordinator,
        empty: tuple[BudgetLedger, FindingsLedger],
        failure_class: ProviderFailureClass,
    ) -> None:
        """The recorded real run lost a review to `token_expired`; here it does not."""
        budget, findings = empty
        budget = coordinator.record_review_attempt(budget)
        budget = coordinator.record_provider_failure(budget, failure_class)
        budget = coordinator.record_review_attempt(budget)
        decision = coordinator.accept_review(
            budget, findings, parse_review(verdict=ReviewVerdict.APPROVED)
        )
        assert decision.outcome is ReviewOutcome.APPROVED
        assert decision.budget.successful_review_rounds == 1
        assert decision.budget.provider_failure_count == 1

    def test_attempts_and_consumed_reviews_diverge_under_failure(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        """`review_attempts` counts invocations; `successful_review_rounds` counts verdicts."""
        budget, findings = empty
        for failure_class in (ProviderFailureClass.AUTH_FAILED, ProviderFailureClass.TIMEOUT):
            budget = coordinator.record_review_attempt(budget)
            budget = coordinator.record_provider_failure(budget, failure_class)
        budget = coordinator.record_review_attempt(budget)
        decision = coordinator.accept_review(
            budget, findings, parse_review(verdict=ReviewVerdict.APPROVED)
        )
        assert decision.budget.review_attempts == 3
        assert decision.budget.successful_review_rounds == 1
        assert decision.budget.provider_failure_count == 2
        assert decision.budget.review_attempts != decision.budget.successful_review_rounds


class TestThreeCountersNeverConflated:
    """Section 22 invariant 11: three durable counters, and no derivation moves a second one."""

    def test_counting_an_attempt_moves_nothing_else(self) -> None:
        before = BudgetLedger()
        after = before.with_attempt()
        assert after.review_attempts == 1
        assert after.successful_review_rounds == before.successful_review_rounds
        assert after.provider_failure_count == before.provider_failure_count

    def test_counting_a_failure_moves_nothing_else(self) -> None:
        before = BudgetLedger()
        after = before.with_provider_failure()
        assert after.provider_failure_count == 1
        assert after.review_attempts == before.review_attempts
        assert after.successful_review_rounds == before.successful_review_rounds

    def test_consuming_a_review_moves_nothing_else(self) -> None:
        before = BudgetLedger()
        after = consume_round(before, parse_review(verdict=ReviewVerdict.APPROVED))
        assert after.successful_review_rounds == 1
        assert after.review_attempts == before.review_attempts
        assert after.provider_failure_count == before.provider_failure_count

    def test_each_of_the_five_counters_is_moved_alone(self) -> None:
        """Every counter, mutated one at a time, with the other four asserted unchanged."""
        moves = {
            "review_attempts": lambda ledger: ledger.with_attempt(),
            "provider_failure_count": lambda ledger: ledger.with_provider_failure(),
            "successful_review_rounds": lambda ledger: consume_round(
                ledger, parse_review(verdict=ReviewVerdict.APPROVED)
            ),
            "correction_round": lambda ledger: consume_round(ledger, parse_correction()),
            "closure_round": lambda ledger: consume_round(
                ledger, parse_closure([("R-1", FindingStatus.CLOSED)], open_ids=["R-1"])
            ),
        }
        for moved, move in moves.items():
            before = BudgetLedger()
            after = move(before)
            for name in before.counter_updates():
                expected = 1 if name == moved else 0
                assert getattr(after, name) == expected, f"{move} moved {name}"

    def test_the_ledger_carries_exactly_the_run_record_s_counters(self) -> None:
        """The five names are `RunRecord`'s, so a ledger needs no translation to be published."""
        assert set(BudgetLedger.model_fields) == RUN_COUNTER_FIELDS

    def test_neither_attempts_nor_failures_is_a_round_budget(self) -> None:
        """A budget mapping that named them would be the first step towards conflating them."""
        assert set(ROUND_COUNTER_FIELDS.values()) == {
            "successful_review_rounds",
            "correction_round",
            "closure_round",
        }
        assert "review_attempts" not in ROUND_COUNTER_FIELDS.values()
        assert "provider_failure_count" not in ROUND_COUNTER_FIELDS.values()

    def test_a_ledger_cannot_be_written_in_place(self) -> None:
        ledger = BudgetLedger()
        with pytest.raises(ValidationError):
            ledger.successful_review_rounds = 3  # type: ignore[misc]
        assert ledger.successful_review_rounds == 0


# --------------------------------------------------------------------------------------
# The findings ledger
# --------------------------------------------------------------------------------------


class TestMediumLowDeferredNeverBlock:
    """Section 19: Medium and Low findings go to the deferred ledger and never block."""

    def test_a_review_of_only_deferred_findings_approves(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        decision = coordinator.accept_review(
            budget,
            findings,
            parse_review(
                verdict=ReviewVerdict.APPROVED,
                deferred=[("R-9", FindingSeverity.MEDIUM), ("R-10", FindingSeverity.LOW)],
            ),
        )
        assert decision.outcome is ReviewOutcome.APPROVED
        assert decision.findings.deferred_ids == ("R-9", "R-10")
        assert decision.findings.open_blocker_ids == ()
        assert decision.findings.has_open_blockers is False

    def test_a_deferred_finding_stays_deferred_beside_an_open_blocker(
        self, blocked: RoundDecision
    ) -> None:
        assert blocked.findings.open_blocker_ids == ("R-1",)
        assert blocked.findings.deferred_ids == ("R-2",)
        assert [finding.status for finding in blocked.findings.deferred] == [FindingStatus.DEFERRED]

    def test_a_deferred_severity_cannot_be_filed_as_a_blocker(self) -> None:
        with pytest.raises(ValidationError, match="only"):
            FindingsLedger(
                blocking=(
                    Finding(
                        finding_id="R-3",
                        severity=FindingSeverity.MEDIUM,
                        title="A medium finding",
                        summary="Filed where it cannot go.",
                    ),
                ),
            )

    def test_a_blocking_severity_cannot_be_filed_as_deferred(self) -> None:
        with pytest.raises(ValidationError, match="only"):
            FindingsLedger(
                deferred=(
                    Finding(
                        finding_id="R-4",
                        severity=FindingSeverity.HIGH,
                        title="A high finding",
                        summary="Filed where it cannot go.",
                        status=FindingStatus.DEFERRED,
                    ),
                ),
            )

    def test_a_deferred_finding_is_never_an_open_blocker(self, blocked: RoundDecision) -> None:
        """Closure is limited to open blockers, so a deferred id is outside the set it rules on."""
        assert "R-2" not in blocked.findings.open_blocker_ids


class TestClosureLimitedToOpenBlockerIds:
    """Section 19: closure verification is strictly limited to the already-open blocker ids."""

    def test_the_open_set_is_exactly_the_open_blockers(self, blocked: RoundDecision) -> None:
        assert blocked.findings.open_blocker_ids == ("R-1",)

    def test_a_ruling_on_a_deferred_finding_is_rejected(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        result = ClosureResult(
            findings=[ClosureRuling(id="R-2", status=FindingStatus.CLOSED, reason="Not open.")]
        )
        with pytest.raises(MalformedResult, match="not one of the open blockers"):
            coordinator.accept_closure(blocked.budget, blocked.findings, result)

    def test_a_ruling_on_an_id_the_run_never_saw_is_rejected(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        result = ClosureResult(
            findings=[ClosureRuling(id="R-99", status=FindingStatus.CLOSED, reason="Invented.")]
        )
        with pytest.raises(MalformedResult, match="R-99"):
            coordinator.accept_closure(blocked.budget, blocked.findings, result)

    def test_the_parser_is_given_the_open_set_and_refuses_anything_else(
        self, blocked: RoundDecision
    ) -> None:
        """The same limit at the parse boundary: a real closure block naming `R-2` never parses."""
        with pytest.raises(MalformedResult, match="may not introduce a finding"):
            parse_closure(
                [("R-2", FindingStatus.CLOSED)], open_ids=blocked.findings.open_blocker_ids
            )

    def test_a_ruling_may_leave_a_blocker_open(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        result = parse_closure(
            [("R-1", FindingStatus.OPEN)], open_ids=blocked.findings.open_blocker_ids
        )
        decision = coordinator.accept_closure(blocked.budget, blocked.findings, result)
        assert decision.outcome is ReviewOutcome.STOP
        assert decision.findings.open_blocker_ids == ("R-1",)

    def test_a_closed_blocker_is_no_longer_in_the_open_set(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        result = parse_closure(
            [("R-1", FindingStatus.CLOSED)], open_ids=blocked.findings.open_blocker_ids
        )
        decision = coordinator.accept_closure(blocked.budget, blocked.findings, result)
        assert decision.outcome is ReviewOutcome.CLEARED
        assert decision.findings.open_blocker_ids == ()
        assert decision.findings.closed_blocker_ids == ("R-1",)

    def test_silence_leaves_a_blocker_open(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        review = coordinator.accept_review(
            budget,
            findings,
            parse_review(
                verdict=ReviewVerdict.BLOCKED,
                blockers=[("R-1", FindingSeverity.CRITICAL), ("R-2", FindingSeverity.HIGH)],
            ),
        )
        result = parse_closure(
            [("R-1", FindingStatus.CLOSED)], open_ids=review.findings.open_blocker_ids
        )
        decision = coordinator.accept_closure(review.budget, review.findings, result)
        assert decision.outcome is ReviewOutcome.STOP
        assert decision.findings.open_blocker_ids == ("R-2",)


class TestClosureCannotIntroduceNewFinding:
    """Section 19: closure may mark an open blocker CLOSED or leave it open, and nothing else."""

    def test_a_new_finding_id_is_rejected_at_the_ledger(self, blocked: RoundDecision) -> None:
        """Even a `ClosureResult` built outside the parser cannot introduce one."""
        result = ClosureResult(
            findings=[ClosureRuling(id="NEW-1", status=FindingStatus.OPEN, reason="Introduced.")]
        )
        with pytest.raises(MalformedResult, match="may not introduce a finding"):
            blocked.findings.apply_closure(result)

    def test_a_new_finding_id_is_rejected_at_the_parser(self, blocked: RoundDecision) -> None:
        with pytest.raises(MalformedResult, match="NEW-1"):
            parse_closure(
                [("NEW-1", FindingStatus.CLOSED)], open_ids=blocked.findings.open_blocker_ids
            )

    def test_a_closure_never_adds_a_deferred_finding(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        result = parse_closure(
            [("R-1", FindingStatus.CLOSED)], open_ids=blocked.findings.open_blocker_ids
        )
        decision = coordinator.accept_closure(blocked.budget, blocked.findings, result)
        assert decision.findings.deferred_ids == blocked.findings.deferred_ids
        assert len(decision.findings.blocking) == len(blocked.findings.blocking)

    def test_a_closure_may_not_demote_a_blocker_to_deferred(self, blocked: RoundDecision) -> None:
        result = ClosureResult(
            findings=[ClosureRuling(id="R-1", status=FindingStatus.DEFERRED, reason="Demoted.")]
        )
        with pytest.raises(MalformedResult, match="CLOSED or OPEN"):
            blocked.findings.apply_closure(result)

    def test_a_review_may_not_restate_an_existing_finding_id(self, blocked: RoundDecision) -> None:
        with pytest.raises(MalformedResult, match="already records"):
            blocked.findings.record_review(
                parse_review(
                    verdict=ReviewVerdict.BLOCKED, blockers=[("R-1", FindingSeverity.HIGH)]
                )
            )


# --------------------------------------------------------------------------------------
# The coordinator's decisions
# --------------------------------------------------------------------------------------


class TestCoordinatorDecisions:
    """One review, one correction, one closure -- and a stop wherever the contract puts one."""

    def test_a_blocked_review_asks_for_the_one_correction_round(
        self, blocked: RoundDecision
    ) -> None:
        assert blocked.kind is RoundKind.REVIEW
        assert blocked.outcome is ReviewOutcome.NEEDS_CORRECTION
        assert "R-1" in blocked.reason

    def test_a_correction_round_closes_nothing(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        """The coordinator never marks a blocker closed on a provider's say-so."""
        decision = coordinator.accept_correction(
            blocked.budget, blocked.findings, parse_correction(addressed=["R-1"])
        )
        assert decision.outcome is ReviewOutcome.NEEDS_CLOSURE
        assert decision.findings.open_blocker_ids == ("R-1",)
        assert decision.findings.closed_blocker_ids == ()

    def test_a_failed_correction_stops_the_run(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        decision = coordinator.accept_correction(
            blocked.budget, blocked.findings, parse_correction(status="FAILED")
        )
        assert decision.outcome is ReviewOutcome.STOP
        assert decision.budget.correction_round == 1

    def test_a_blocker_open_after_the_correction_round_is_a_stop_not_another_round(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        corrected = coordinator.accept_correction(
            blocked.budget, blocked.findings, parse_correction()
        )
        closed = coordinator.accept_closure(
            corrected.budget,
            corrected.findings,
            parse_closure(
                [("R-1", FindingStatus.OPEN)], open_ids=corrected.findings.open_blocker_ids
            ),
        )
        assert closed.outcome is ReviewOutcome.STOP
        with pytest.raises(BudgetExhausted) as raised:
            coordinator.accept_correction(closed.budget, closed.findings, parse_correction())
        assert raised.value.kind is RoundKind.CORRECTION

    def test_a_policy_with_no_correction_round_stops_at_the_review(
        self, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        coordinator = ReviewCoordinator(policy=ReviewPolicy(max_correction_rounds=0))
        decision = coordinator.accept_review(
            budget,
            findings,
            parse_review(
                verdict=ReviewVerdict.BLOCKED, blockers=[("R-1", FindingSeverity.CRITICAL)]
            ),
        )
        assert decision.outcome is ReviewOutcome.STOP
        assert "no correction round remains" in decision.reason

    def test_a_policy_with_no_closure_stops_after_the_correction(
        self, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        coordinator = ReviewCoordinator(policy=ReviewPolicy(max_closure_reviews=0))
        review = coordinator.accept_review(
            budget,
            findings,
            parse_review(
                verdict=ReviewVerdict.BLOCKED, blockers=[("R-1", FindingSeverity.CRITICAL)]
            ),
        )
        decision = coordinator.accept_correction(review.budget, review.findings, parse_correction())
        assert decision.outcome is ReviewOutcome.STOP
        assert "no closure verification remains" in decision.reason

    def test_a_correction_presupposes_an_open_blocker(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        with pytest.raises(ValueError, match="presupposes"):
            coordinator.accept_correction(budget, findings, parse_correction())

    def test_the_full_one_round_flow_clears(
        self, coordinator: ReviewCoordinator, empty: tuple[BudgetLedger, FindingsLedger]
    ) -> None:
        budget, findings = empty
        budget = coordinator.record_review_attempt(budget)
        review = coordinator.accept_review(
            budget, findings, parse_review_result(BLOCKED_REVIEW_TEXT, max_blockers=3)
        )
        corrected = coordinator.accept_correction(
            review.budget, review.findings, parse_correction()
        )
        closed = coordinator.accept_closure(
            corrected.budget,
            corrected.findings,
            parse_closure(
                [("R-1", FindingStatus.CLOSED)], open_ids=corrected.findings.open_blocker_ids
            ),
        )
        assert closed.outcome is ReviewOutcome.CLEARED
        assert closed.budget.counter_updates() == {
            "review_attempts": 1,
            "successful_review_rounds": 1,
            "provider_failure_count": 0,
            "correction_round": 1,
            "closure_round": 1,
        }
        assert closed.findings.record_updates()["deferred_findings"][0].finding_id == "R-2"

    def test_the_coordinator_returns_a_decision_and_transitions_nothing(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        """No run state, no store, no publication -- a typed decision the application acts on."""
        assert isinstance(blocked, RoundDecision)
        assert set(RoundDecision.model_fields) == {
            "kind",
            "outcome",
            "budget",
            "findings",
            "reason",
        }
        source = REVIEW_SOURCE.read_text(encoding="utf-8")
        for forbidden in ("RunStatus", "RunStateStore", "subprocess", "providers", "open("):
            assert forbidden not in source, f"review.py reaches for {forbidden}"


# --------------------------------------------------------------------------------------
# Prototype-defect regressions
# --------------------------------------------------------------------------------------


class TestP3RoundConsumedOnlyAfterResultParses:
    """Defect P-3: correction and closure incremented before their exit-code checks.

    Covered for all three round types, because the prototype's inconsistency was that review was
    accounted one way and the other two another.
    """

    @pytest.mark.parametrize("kind", list(RoundKind))
    def test_a_malformed_result_consumes_no_round(
        self, coordinator: ReviewCoordinator, kind: RoundKind
    ) -> None:
        """The provider answered; the answer did not parse; no counter moved."""
        budget, findings = BudgetLedger(), FindingsLedger()
        if kind is not RoundKind.REVIEW:
            review = coordinator.accept_review(
                budget, findings, parse_review_result(BLOCKED_REVIEW_TEXT, max_blockers=3)
            )
            budget, findings = review.budget, review.findings
        before = budget.counter_updates()

        garbage = {
            RoundKind.REVIEW: (
                ProviderRole.REVIEW,
                "verdict: BLOCKED\nblockers: []\n",
            ),
            RoundKind.CORRECTION: (
                ProviderRole.CORRECTION,
                "status: NOT-A-STATUS\n",
            ),
            RoundKind.CLOSURE: (
                ProviderRole.CLOSURE,
                "findings:\n  - id: NEW-1\n    status: CLOSED\n    reason: Introduced.\n",
            ),
        }[kind]
        text = block(*garbage)
        with pytest.raises(MalformedResult):
            if kind is RoundKind.REVIEW:
                parse_review_result(text, max_blockers=3)
            elif kind is RoundKind.CORRECTION:
                parse_correction_result(text)
            else:
                parse_closure_result(text, open_finding_ids=findings.open_blocker_ids)

        failed = coordinator.record_provider_failure(budget, ProviderFailureClass.MALFORMED_OUTPUT)
        assert failed.consumed(kind) == before[ROUND_COUNTER_FIELDS[kind]]
        assert failed.provider_failure_count == 1

    @pytest.mark.parametrize("kind", list(RoundKind))
    def test_a_parsed_result_consumes_exactly_its_own_round(
        self, coordinator: ReviewCoordinator, kind: RoundKind
    ) -> None:
        """The same helper, the same rule, for review, correction and closure."""
        results = {
            RoundKind.REVIEW: parse_review(verdict=ReviewVerdict.APPROVED),
            RoundKind.CORRECTION: parse_correction(),
            RoundKind.CLOSURE: parse_closure([("R-1", FindingStatus.CLOSED)], open_ids=["R-1"]),
        }
        after = consume_round(BudgetLedger(), results[kind])
        assert after.consumed(kind) == 1
        assert sum(after.counter_updates().values()) == 1

    def test_a_correction_that_fails_after_parsing_still_consumed_its_round(
        self, coordinator: ReviewCoordinator, blocked: RoundDecision
    ) -> None:
        """The rule is "after the result parses", not "after the run succeeds"."""
        decision = coordinator.accept_correction(
            blocked.budget, blocked.findings, parse_correction(status="BLOCKED")
        )
        assert decision.budget.correction_round == 1
        assert decision.outcome is ReviewOutcome.STOP

    def test_the_helper_cannot_be_handed_anything_but_a_parsed_result(self) -> None:
        """The signature is the guarantee: there is no ordering in which text reaches a counter."""
        hints = typing.get_type_hints(consume_round)
        assert set(typing.get_args(hints["result"])) == {
            ReviewResult,
            CorrectionResult,
            ClosureResult,
        }

    @pytest.mark.parametrize(
        ("result", "kind"),
        [
            (parse_review(verdict=ReviewVerdict.APPROVED), RoundKind.REVIEW),
            (parse_correction(), RoundKind.CORRECTION),
            (parse_closure([("R-1", FindingStatus.CLOSED)], open_ids=["R-1"]), RoundKind.CLOSURE),
        ],
    )
    def test_the_round_kind_comes_from_the_result_s_own_type(
        self, result: ReviewResult | CorrectionResult | ClosureResult, kind: RoundKind
    ) -> None:
        assert round_kind_of(result) is kind

    def test_every_accepted_round_goes_through_the_one_helper(self) -> None:
        """AST: each `accept_*` method calls `consume_round`, so there is one accounting rule."""
        tree = ast.parse(REVIEW_SOURCE.read_text(encoding="utf-8"))
        helpers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "consume_round"
        ]
        assert len(helpers) == 1, "there is exactly one budget-accounting helper"
        coordinator_class = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "ReviewCoordinator"
        )
        accepted = [
            node
            for node in coordinator_class.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("accept_")
        ]
        assert {node.name for node in accepted} == {
            "accept_review",
            "accept_correction",
            "accept_closure",
        }
        for node in accepted:
            called = {
                inner.func.id
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            }
            assert "consume_round" in called, f"{node.name} does its own accounting"


class TestP4NoUnreachableRetryCeiling:
    """Defect P-4: `MAX_REVIEW_ATTEMPTS = 3`, a limit no code path could ever reach."""

    @pytest.mark.parametrize("kind", list(RoundKind))
    def test_every_limit_is_reached_and_then_enforced(self, kind: RoundKind) -> None:
        results = {
            RoundKind.REVIEW: parse_review(verdict=ReviewVerdict.APPROVED),
            RoundKind.CORRECTION: parse_correction(),
            RoundKind.CLOSURE: parse_closure([("R-1", FindingStatus.CLOSED)], open_ids=["R-1"]),
        }
        policy = ReviewPolicy()
        ledger = BudgetLedger()
        for _ in range(policy.limit_for(kind)):
            ledger = consume_round(ledger, results[kind], policy=policy)
        assert ledger.consumed(kind) == policy.limit_for(kind)
        assert remaining_rounds(ledger, kind, policy=policy) == 0
        with pytest.raises(BudgetExhausted):
            consume_round(ledger, results[kind], policy=policy)

    def test_a_zero_limit_refuses_the_first_round(self) -> None:
        policy = ReviewPolicy(max_correction_rounds=0)
        with pytest.raises(BudgetExhausted):
            consume_round(BudgetLedger(), parse_correction(), policy=policy)

    def test_attempts_are_counted_and_never_capped(self, coordinator: ReviewCoordinator) -> None:
        """No attempt ceiling is introduced in the vestigial one's place."""
        ledger = BudgetLedger()
        for _ in range(10):
            ledger = coordinator.record_review_attempt(ledger)
        assert ledger.review_attempts == 10

    def test_the_module_declares_no_attempt_or_retry_ceiling(self) -> None:
        import ai_workflow_engine.milestone_runner.review as review_module

        for name in dir(review_module):
            assert "MAX_REVIEW_ATTEMPTS" not in name
            assert not name.startswith("MAX_RETR")

    def test_every_constant_the_module_declares_is_read_by_the_module(self) -> None:
        """AST: a module-level constant no code path loads is exactly a vestigial limit."""
        tree = ast.parse(REVIEW_SOURCE.read_text(encoding="utf-8"))
        declared: set[str] = set()
        for node in tree.body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    declared.add(target.id)
        loaded = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        assert declared, "the module declares constants"
        assert declared <= loaded, f"unread constants: {sorted(declared - loaded)}"

    def test_every_policy_limit_is_consulted_by_the_helper(self) -> None:
        """A limit the accounting never asks about would be the same defect under a new name."""
        for kind in RoundKind:
            assert ReviewPolicy().limit_for(kind) >= 0
            assert ROUND_COUNTER_FIELDS[kind] in RUN_COUNTER_FIELDS


# --------------------------------------------------------------------------------------
# The ledgers a run record carries
# --------------------------------------------------------------------------------------


class TestLedgersAndTheRunRecord:
    """The ledgers read from and publish to the durable record without translating anything."""

    def test_a_budget_ledger_round_trips_through_a_record_s_counters(self) -> None:
        ledger = BudgetLedger(
            review_attempts=3,
            successful_review_rounds=1,
            provider_failure_count=2,
            correction_round=1,
            closure_round=1,
        )
        assert ledger.counter_updates() == {
            "closure_round": 1,
            "correction_round": 1,
            "provider_failure_count": 2,
            "review_attempts": 3,
            "successful_review_rounds": 1,
        }

    def test_a_findings_ledger_publishes_the_two_record_lists(self, blocked: RoundDecision) -> None:
        updates = blocked.findings.record_updates()
        assert [finding.finding_id for finding in updates["blocking_findings"]] == ["R-1"]
        assert [finding.finding_id for finding in updates["deferred_findings"]] == ["R-2"]

    def test_a_findings_ledger_cannot_be_written_in_place(self, blocked: RoundDecision) -> None:
        with pytest.raises(ValidationError):
            blocked.findings.blocking = ()  # type: ignore[misc]

    def test_a_finding_id_cannot_appear_twice(self) -> None:
        finding = Finding(
            finding_id="R-1",
            severity=FindingSeverity.CRITICAL,
            title="A finding",
            summary="Filed twice.",
        )
        with pytest.raises(ValidationError, match="twice"):
            FindingsLedger(blocking=(finding, finding))
