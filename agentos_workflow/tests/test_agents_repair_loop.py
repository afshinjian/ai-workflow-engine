"""The bounded automatic repair loop and the deterministic validation gate
(`FAILURE_RECOVERY.md` §1-2, `MACHINE_GATES.md` §3, `AGENT_CONTRACTS.md` §8).

Both sequences under test are **Orchestrator-owned**, not a seventh Agent. The loop is driven with
real `ImplementationAgent` and `QAAgent` instances over `MockProvider`, so the properties asserted
here — attempt bounding, full re-validation after every attempt, latest-report-not-stale — are
properties of the shipping code path rather than of a test harness written to agree with it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentos_workflow.agents import (
    VALIDATION_GATE_CHECKS,
    AgentKind,
    CapabilityBroker,
    ValidationCheck,
    ValidationOutcome,
    run_deterministic_validation,
    run_repair_loop,
)
from agentos_workflow.agents.implementation import ImplementationAgent
from agentos_workflow.agents.qa import QAAgent
from agentos_workflow.providers import ProviderRole, ProviderVerdict, provider_success
from agentos_workflow.providers.mock import MockProvider, canned_report
from agentos_workflow.skills import (
    FailureKind,
    RetryClassification,
    SkillFailure,
    SkillResult,
    success,
)
from agentos_workflow.skills.repository import DiffSummary
from agentos_workflow.tests.test_providers_cli import valid_config

WORKFLOW_ID = "wf-repair"
STAGE_ID = "AUTO-999"
STAGE_BRANCH = "feature/auto-999-example"
BASELINE_SHA = "a" * 40


def implementation_skills(changed: tuple[str, ...] = ("src/x.py",)) -> dict[str, Any]:
    """Fakes for the deterministic Skills `ImplementationAgent` observes the diff with.

    Faked rather than run against a real repository because this file is about the *loop*: what
    the diff-reading Skills do is already covered by `test_skills_repository.py`, and driving a
    real Git repository through three repair rounds would test Git, not the attempt bounding.
    """
    return {
        "list_changed_files": lambda **_: success(changed),
        "inspect_diff": lambda **_: success(
            DiffSummary(
                base=BASELINE_SHA,
                branch=STAGE_BRANCH,
                files_changed=len(changed),
                insertions=1,
                deletions=0,
                paths=changed,
            )
        ),
        "validate_allowed_paths": lambda **_: success(_ScopeVerdict(True, ())),
        "append_audit_event": lambda **_: success(_Appended()),
    }


class _ScopeVerdict:
    def __init__(self, passed: bool, violations: tuple[Any, ...]) -> None:
        self.passed = passed
        self.violations = violations


class _Appended:
    event_id = "e"
    appended = True
    path = Path("/dev/null")


def build_implementation_agent(
    tmp_path: Path, provider: MockProvider
) -> tuple[ImplementationAgent, CapabilityBroker]:
    broker = CapabilityBroker(
        AgentKind.IMPLEMENTATION,
        skills=implementation_skills(),
        providers=lambda role: provider,
    )
    agent = ImplementationAgent(
        broker,
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        repository_path=tmp_path / "repo",
        baseline_commit_sha=BASELINE_SHA,
        session_root=tmp_path / "sessions",
        audit_root=tmp_path / "audit",
        allowed_paths=("src/**",),
        forbidden_paths=(),
    )
    return agent, broker


def build_qa_agent(tmp_path: Path, provider: MockProvider) -> tuple[QAAgent, CapabilityBroker]:
    """A QA Agent whose reporting Skills are the *real* ones, writing into a temporary audit root.

    The QA report round-trip (write, then validate the written artifact) is part of what
    `MACHINE_GATES.md` §4 requires, so faking it would remove the behaviour under test.
    """
    from agentos_workflow.agents import default_skill_registry

    (tmp_path / "audit").mkdir(parents=True, exist_ok=True)
    registry = dict(default_skill_registry())
    broker = CapabilityBroker(
        AgentKind.QA,
        skills={name: registry[name] for name in registry if name in _QA_SKILLS},
        providers=lambda role: provider,
    )
    agent = QAAgent(
        broker,
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        repository_path=tmp_path / "repo",
        session_root=tmp_path / "sessions",
        audit_root=tmp_path / "audit",
    )
    return agent, broker


_QA_SKILLS = {"generate_qa_report", "validate_qa_report", "append_audit_event"}


def qa_provider(*verdicts: ProviderVerdict) -> MockProvider:
    return MockProvider(
        [
            provider_success(
                canned_report(
                    role=ProviderRole.QA,
                    verdict=verdict,
                    summary=f"qa round {index + 1}",
                    findings=() if verdict is ProviderVerdict.PASS else ("finding: broken",),
                )
            )
            for index, verdict in enumerate(verdicts)
        ]
    )


def implementation_provider(count: int = 8) -> MockProvider:
    return MockProvider(
        [
            provider_success(
                canned_report(
                    role=ProviderRole.REPAIR,
                    summary=f"repair {index + 1}",
                    files_changed=("src/x.py",),
                    recommended_commit_message="fix: repair",
                )
            )
            for index in range(count)
        ]
    )


def passing_validation() -> ValidationOutcome:
    return ValidationOutcome(
        passed=True,
        checks=tuple(ValidationCheck(name=name, passed=True) for name in VALIDATION_GATE_CHECKS),
    )


def failing_validation(failed: str = "run_tests") -> ValidationOutcome:
    return ValidationOutcome(
        passed=False,
        checks=tuple(
            ValidationCheck(
                name=name, passed=name != failed, detail="" if name != failed else "1 failed"
            )
            for name in VALIDATION_GATE_CHECKS
        ),
    )


class TestRepairLoopSucceedsWithinBudget:
    """`MockProvider` failing twice then passing: three total implementation attempts, and a full
    re-validation after every one of them."""

    def test_two_repairs_then_pass(self, tmp_path: Path) -> None:
        impl_provider = implementation_provider()
        qa_mock = qa_provider(
            ProviderVerdict.FAIL,  # the pre-loop QA round that sends the workflow to REPAIRING
            ProviderVerdict.FAIL,  # after repair attempt 1
            ProviderVerdict.PASS,  # after repair attempt 2
        )
        implementation, impl_broker = build_implementation_agent(tmp_path, impl_provider)
        qa, _ = build_qa_agent(tmp_path, qa_mock)

        validations: list[ValidationOutcome] = []

        def validate() -> ValidationOutcome:
            outcome = passing_validation()
            validations.append(outcome)
            return outcome

        # The initial implementation attempt, before the loop — exactly what the Orchestrator does
        # on `BRANCH_CREATED → IMPLEMENTING`.
        initial = implementation.implement(contract_text="stage contract")
        assert initial.ok
        pre_loop_qa = qa.review(validation=passing_validation(), attempt_number=1)
        assert not pre_loop_qa.ok, "the first QA round must reject, or there is nothing to repair"

        outcome = run_repair_loop(
            implementation=implementation,
            qa=qa,
            validate=validate,
            initial_failure_report={"source": "independent_qa", "findings": ["finding: broken"]},
            attempt_limit=3,
            workflow_id=WORKFLOW_ID,
            stage_id=STAGE_ID,
        )

        assert outcome.repaired is True
        assert outcome.exhausted is False
        assert outcome.repair_attempts_used == 2
        # The contract's headline assertion: three implementation attempts in total, never more.
        assert outcome.total_implementation_attempts == 3
        assert outcome.total_implementation_attempts <= 3

        # A full re-validation after every attempt (`FAILURE_RECOVERY.md` §1).
        assert len(validations) == outcome.repair_attempts_used
        for attempt in outcome.attempts:
            assert attempt.validation is not None, "validation must run after every attempt"
            assert attempt.qa is not None, "QA must run after every attempt"
            assert len(attempt.validation.checks) == len(VALIDATION_GATE_CHECKS)

        # Three provider invocations for the implementation role: one initial, two repairs.
        assert len(impl_provider.invocations) == 3
        assert [invocation.role for invocation in impl_provider.invocations] == [
            ProviderRole.IMPLEMENTATION,
            ProviderRole.REPAIR,
            ProviderRole.REPAIR,
        ]
        assert impl_broker.provider_calls.count(ProviderRole.REPAIR) == 2

    def test_each_repair_receives_the_latest_report_never_a_stale_one(self, tmp_path: Path) -> None:
        """`FAILURE_RECOVERY.md` §1: the *latest* QA/validation failure, never an earlier one."""
        impl_provider = implementation_provider()
        implementation, _ = build_implementation_agent(tmp_path, impl_provider)
        qa, _ = build_qa_agent(tmp_path, qa_provider(*(ProviderVerdict.FAIL,) * 6))

        sequence = iter([failing_validation("run_lint"), failing_validation("run_security_checks")])

        outcome = run_repair_loop(
            implementation=implementation,
            qa=qa,
            validate=lambda: next(sequence, failing_validation("run_tests")),
            initial_failure_report={"source": "seed", "failed_checks": [{"check": "run_tests"}]},
            attempt_limit=3,
        )
        assert outcome.exhausted is True

        prompts = [
            invocation.prompt
            for invocation in impl_provider.invocations
            if "Repair" in invocation.prompt
        ]
        assert len(prompts) == 3
        # Attempt 1 is told about the seed report; attempt 2 about attempt 1's lint failure;
        # attempt 3 about attempt 2's security failure. No prompt repeats an earlier round's.
        assert "seed" in prompts[0]
        assert "run_lint" in prompts[1] and "seed" not in prompts[1]
        assert "run_security_checks" in prompts[2] and "run_lint" not in prompts[2]

    def test_a_repair_prompt_is_canonical_json_of_the_report(self, tmp_path: Path) -> None:
        impl_provider = implementation_provider()
        implementation, _ = build_implementation_agent(tmp_path, impl_provider)
        result = implementation.repair(
            failure_report={"source": "deterministic_validation", "failed_checks": []},
            attempt_number=1,
        )
        assert result.ok
        prompt = impl_provider.invocations[0].prompt
        payload = prompt.split("Latest failure report:\n", 1)[1]
        assert json.loads(payload)["source"] == "deterministic_validation"


class TestRepairLoopExhaustion:
    """Three failed repair attempts and no fourth (`FAILURE_RECOVERY.md` §1)."""

    def test_exhaustion_reports_failure_with_evidence(self, tmp_path: Path) -> None:
        impl_provider = implementation_provider()
        implementation, _ = build_implementation_agent(tmp_path, impl_provider)
        qa, _ = build_qa_agent(tmp_path, qa_provider(*(ProviderVerdict.FAIL,) * 8))

        attempts_validated = 0

        def validate() -> ValidationOutcome:
            nonlocal attempts_validated
            attempts_validated += 1
            return failing_validation()

        outcome = run_repair_loop(
            implementation=implementation,
            qa=qa,
            validate=validate,
            initial_failure_report={"source": "independent_qa"},
            attempt_limit=3,
            workflow_id=WORKFLOW_ID,
            stage_id=STAGE_ID,
        )

        assert outcome.repaired is False
        assert outcome.exhausted is True
        assert outcome.repair_attempts_used == 3
        assert attempts_validated == 3, "every attempt is fully re-validated, including the last"
        assert len(impl_provider.invocations) == 3, "there is no fourth attempt"

        report = outcome.failure_report
        assert report is not None
        assert report["reason"] == "repair_attempts_exhausted"
        assert report["workflow_id"] == WORKFLOW_ID
        assert report["stage_id"] == STAGE_ID
        assert [entry["attempt_number"] for entry in report["attempts"]] == [1, 2, 3]
        assert all(entry["validation_passed"] is False for entry in report["attempts"])
        assert all("run_tests" in entry["failed_checks"] for entry in report["attempts"])

    def test_no_fourth_attempt_even_when_the_limit_is_raised_by_a_caller(
        self, tmp_path: Path
    ) -> None:
        """The limit is a parameter the Orchestrator supplies from `repair_attempt_limit`, which
        the configuration schema pins to `Literal[3]` — so a workflow cannot be configured into a
        larger budget. This test records that the loop honours the value it is given, and that the
        only value a real workflow can give it is 3."""
        config = valid_config(tmp_path)
        assert config.repair_attempt_limit == 3

        impl_provider = implementation_provider()
        implementation, _ = build_implementation_agent(tmp_path, impl_provider)
        qa, _ = build_qa_agent(tmp_path, qa_provider(*(ProviderVerdict.FAIL,) * 8))
        outcome = run_repair_loop(
            implementation=implementation,
            qa=qa,
            validate=failing_validation,
            initial_failure_report={},
            attempt_limit=config.repair_attempt_limit,
        )
        assert outcome.repair_attempts_used == 3
        assert len(impl_provider.invocations) == 3

    def test_an_unusable_repair_attempt_stops_without_revalidating(self, tmp_path: Path) -> None:
        """`FAILURE_RECOVERY.md` §1: a repair whose provider produced nothing usable does not loop
        back to `VALIDATING` with nothing to validate."""
        broken = MockProvider(
            [
                SkillResultLikeFailure().as_provider_result(),
            ]
        )
        implementation, _ = build_implementation_agent(tmp_path, broken)
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))

        validated = 0

        def validate() -> ValidationOutcome:
            nonlocal validated
            validated += 1
            return passing_validation()

        outcome = run_repair_loop(
            implementation=implementation,
            qa=qa,
            validate=validate,
            initial_failure_report={},
            attempt_limit=3,
        )
        assert outcome.repaired is False
        assert outcome.exhausted is False
        assert validated == 0
        assert outcome.failure_report is not None
        assert outcome.failure_report["reason"] == "repair_attempt_unusable"
        assert outcome.attempts[0].validation is None
        assert outcome.attempts[0].qa is None


class SkillResultLikeFailure:
    """A provider result that failed, for the unusable-attempt path."""

    def as_provider_result(self) -> Any:
        from agentos_workflow.providers import ProviderFailureKind, ProviderKind, provider_failure

        return provider_failure(
            ProviderKind.MOCK,
            ProviderFailureKind.TIMEOUT,
            "the repair session timed out",
            retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
        )


class TestDeterministicValidationGate:
    """`MACHINE_GATES.md` §3, run as an Orchestrator-owned sequence rather than a seventh Agent."""

    def test_every_named_check_runs_and_all_must_pass(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def record(name: str) -> Any:
            def binding(**_: object) -> SkillResult[Any]:
                calls.append(name)
                return success(_ScopeVerdict(True, ()))

            return binding

        outcome = run_deterministic_validation(
            config=valid_config(tmp_path),
            changed_files=("src/x.py",),
            completion_report_path=tmp_path / "report.json",
            skills={name: record(name) for name in VALIDATION_GATE_CHECKS},
        )
        assert outcome.passed is True
        assert calls == list(VALIDATION_GATE_CHECKS)
        assert len(outcome.checks) == 7

    def test_all_checks_run_even_after_the_first_failure(self, tmp_path: Path) -> None:
        """A repair attempt that only ever sees the first failure fixes one problem per attempt
        and exhausts the budget on a diff with three."""
        calls: list[str] = []

        def binding_for(name: str) -> Any:
            def binding(**_: object) -> SkillResult[Any]:
                calls.append(name)
                return success(_ScopeVerdict(name not in {"run_lint", "run_tests"}, ()))

            return binding

        outcome = run_deterministic_validation(
            config=valid_config(tmp_path),
            changed_files=("src/x.py",),
            completion_report_path=tmp_path / "report.json",
            skills={name: binding_for(name) for name in VALIDATION_GATE_CHECKS},
        )
        assert calls == list(VALIDATION_GATE_CHECKS)
        assert outcome.passed is False
        assert {check.name for check in outcome.failed_checks} == {"run_lint", "run_tests"}
        report = outcome.failure_report()
        assert report["source"] == "deterministic_validation"
        assert {entry["check"] for entry in report["failed_checks"]} == {"run_lint", "run_tests"}

    def test_a_skill_that_cannot_run_is_a_failed_check_not_an_exception(
        self, tmp_path: Path
    ) -> None:
        def unspawnable(**_: object) -> SkillResult[Any]:
            return SkillResult(
                ok=False,
                error=SkillFailure(
                    skill="run_tests",
                    kind=FailureKind.SPAWN_FAILED,
                    detail="No such file or directory: pytest",
                    retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
                ),
            )

        skills: dict[str, Any] = {
            name: (lambda **_: success(_ScopeVerdict(True, ()))) for name in VALIDATION_GATE_CHECKS
        }
        skills["run_tests"] = unspawnable
        outcome = run_deterministic_validation(
            config=valid_config(tmp_path),
            changed_files=(),
            completion_report_path=tmp_path / "report.json",
            skills=skills,
        )
        assert outcome.passed is False
        failed = {check.name: check.detail for check in outcome.failed_checks}
        assert "run_tests" in failed
        assert "spawn_failed" in failed["run_tests"]

    def test_an_unbound_skill_fails_the_gate_rather_than_being_skipped(
        self, tmp_path: Path
    ) -> None:
        """A gate with no third outcome (`MACHINE_GATES.md` §1) must never silently skip a check."""
        outcome = run_deterministic_validation(
            config=valid_config(tmp_path),
            changed_files=(),
            completion_report_path=tmp_path / "report.json",
            skills={},
        )
        assert outcome.passed is False
        assert len(outcome.failed_checks) == len(VALIDATION_GATE_CHECKS)


class TestValidationOutcomeIsEvidenceNotADecision:
    def test_outcome_carries_no_workflow_state(self) -> None:
        outcome = failing_validation()
        assert not hasattr(outcome, "next_state")
        assert not hasattr(outcome, "transition")

    def test_repair_outcome_carries_no_workflow_state(self, tmp_path: Path) -> None:
        implementation, _ = build_implementation_agent(tmp_path, implementation_provider())
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))
        outcome = run_repair_loop(
            implementation=implementation,
            qa=qa,
            validate=passing_validation,
            initial_failure_report={},
            attempt_limit=3,
        )
        assert outcome.repaired is True
        assert not hasattr(outcome, "next_state")
        assert not hasattr(outcome, "resulting_state")


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_the_loop_never_exceeds_its_attempt_limit(tmp_path: Path, limit: int) -> None:
    impl_provider = implementation_provider()
    implementation, _ = build_implementation_agent(tmp_path, impl_provider)
    qa, _ = build_qa_agent(tmp_path, qa_provider(*(ProviderVerdict.FAIL,) * 8))
    outcome = run_repair_loop(
        implementation=implementation,
        qa=qa,
        validate=failing_validation,
        initial_failure_report={},
        attempt_limit=limit,
    )
    assert outcome.repair_attempts_used == limit
    assert len(impl_provider.invocations) == limit
    assert outcome.exhausted is True


def test_config_pins_the_repair_attempt_limit_to_three(tmp_path: Path) -> None:
    """`FAILURE_RECOVERY.md` §9 makes changing the limit a MAJOR decision, so the configuration
    schema pins it rather than leaving it to an operator."""
    with pytest.raises(ValidationError):
        valid_config(tmp_path, repair_attempt_limit=4)


def test_mapping_of_initial_report_is_not_mutated(tmp_path: Path) -> None:
    """The caller's report object is copied, not adopted and rewritten by the loop."""
    implementation, _ = build_implementation_agent(tmp_path, implementation_provider())
    qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))
    seed: Mapping[str, Any] = {"source": "independent_qa"}
    run_repair_loop(
        implementation=implementation,
        qa=qa,
        validate=passing_validation,
        initial_failure_report=seed,
        attempt_limit=3,
    )
    assert seed == {"source": "independent_qa"}
