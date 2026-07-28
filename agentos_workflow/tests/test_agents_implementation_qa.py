"""`ImplementationAgent` and `QAAgent` (`AGENT_CONTRACTS.md` §3-4, `MACHINE_GATES.md` §3-4).

Two properties dominate this file:

**A provider's self-report is a claim, not evidence.** `ImplementationAgent` derives the changed
paths from Git independently and records whether the model's claim matched — the same discipline
this repository's Milestone 3 claim verification already established for its own agent runner.

**QA is independently derived and cannot override a machine gate.** A QA pass on a diff whose
deterministic validation failed is contradictory evidence and is reported as a failed review, not
as a pass that quietly outranks `MACHINE_GATES.md` §3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.agents import (
    AgentFailureKind,
    AgentKind,
    CapabilityBroker,
    ValidationCheck,
    ValidationOutcome,
    default_skill_registry,
)
from agentos_workflow.agents.implementation import ImplementationAgent
from agentos_workflow.providers import (
    ProviderFailureKind,
    ProviderKind,
    ProviderRole,
    ProviderVerdict,
    provider_failure,
    provider_success,
)
from agentos_workflow.providers.mock import MockProvider, canned_report
from agentos_workflow.skills import RetryClassification, success
from agentos_workflow.tests.test_agents_repair_loop import (
    _ScopeVerdict,
    build_implementation_agent,
    build_qa_agent,
    failing_validation,
    implementation_skills,
    passing_validation,
    qa_provider,
)

WORKFLOW_ID = "wf-repair"
STAGE_BRANCH = "feature/auto-999-example"


class TestImplementationAgentVerifiesItsOwnProvidersClaim:
    def test_a_matching_claim_is_recorded_as_matching(self, tmp_path: Path) -> None:
        provider = MockProvider(
            [
                provider_success(
                    canned_report(
                        role=ProviderRole.IMPLEMENTATION,
                        summary="done",
                        files_changed=("src/x.py",),
                        recommended_commit_message="feat: x",
                    )
                )
            ]
        )
        agent, _ = build_implementation_agent(tmp_path, provider)
        result = agent.implement(contract_text="contract")

        assert result.ok is True
        assert result.evidence["observed_changed_paths"] == ["src/x.py"]
        assert result.evidence["claim_matches_observation"] is True
        assert result.evidence["recommended_commit_message"] == "feat: x"

    def test_an_overstated_claim_is_recorded_as_a_mismatch(self, tmp_path: Path) -> None:
        """The model claims three files; Git says one. The Agent reports both, and never
        substitutes the claim for the observation."""
        provider = MockProvider(
            [
                provider_success(
                    canned_report(
                        role=ProviderRole.IMPLEMENTATION,
                        summary="done",
                        files_changed=("src/x.py", "src/y.py", "docs/z.md"),
                    )
                )
            ]
        )
        agent, _ = build_implementation_agent(tmp_path, provider)
        result = agent.implement(contract_text="contract")

        assert result.ok is True, "a mismatch is evidence for the gate, not an Agent-level verdict"
        assert result.evidence["observed_changed_paths"] == ["src/x.py"]
        assert result.evidence["claimed_changed_paths"] == ["src/x.py", "src/y.py", "docs/z.md"]
        assert result.evidence["claim_matches_observation"] is False

    def test_scope_violations_are_reported_not_judged(self, tmp_path: Path) -> None:
        """`run_scope_validation` in the Orchestrator-owned gate is the authority; a second rule
        engine in the Agent could disagree with it."""

        class Violation:
            path = "src/forbidden.py"
            reason = "outside allowed paths"

        skills = implementation_skills()
        skills["validate_allowed_paths"] = lambda **_: success(_ScopeVerdict(False, (Violation(),)))
        broker = CapabilityBroker(
            AgentKind.IMPLEMENTATION,
            skills=skills,
            providers=lambda role: MockProvider(
                [provider_success(canned_report(role=ProviderRole.IMPLEMENTATION))]
            ),
        )
        agent = ImplementationAgent(
            broker,
            workflow_id=WORKFLOW_ID,
            stage_id="AUTO-999",
            stage_branch=STAGE_BRANCH,
            repository_path=tmp_path,
            baseline_commit_sha="a" * 40,
            session_root=tmp_path / "sessions",
            audit_root=tmp_path / "audit",
        )
        result = agent.implement(contract_text="contract")
        assert result.ok is True
        assert result.evidence["scope_passed"] is False
        assert result.evidence["scope_violations"] == [
            {"path": "src/forbidden.py", "reason": "outside allowed paths"}
        ]

    def test_a_provider_failure_preserves_its_retry_classification(self, tmp_path: Path) -> None:
        """`WORKFLOW_STATES.md` §5a: only the Orchestrator decides retry vs. reconcile, and it can
        only do so from the classification the provider produced."""
        provider = MockProvider(
            [
                provider_failure(
                    ProviderKind.CLAUDE_CLI,
                    ProviderFailureKind.TIMEOUT,
                    "the session timed out",
                    retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                )
            ]
        )
        agent, _ = build_implementation_agent(tmp_path, provider)
        result = agent.implement(contract_text="contract")

        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.PROVIDER_FAILED
        assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT

    def test_each_attempt_gets_its_own_session_scope(self, tmp_path: Path) -> None:
        """`MODEL_PROVIDER_CONTRACTS.md` §5: invocations do not share working state."""
        provider = MockProvider(
            [
                provider_success(canned_report(role=ProviderRole.IMPLEMENTATION)),
                provider_success(canned_report(role=ProviderRole.REPAIR)),
                provider_success(canned_report(role=ProviderRole.REPAIR)),
            ]
        )
        agent, _ = build_implementation_agent(tmp_path, provider)
        agent.implement(contract_text="contract")
        agent.repair(failure_report={"source": "x"}, attempt_number=1)
        agent.repair(failure_report={"source": "y"}, attempt_number=2)

        identifiers = [invocation.invocation_id for invocation in provider.invocations]
        assert identifiers == ["implement-1", "repair-1", "repair-2"]
        assert len(set(identifiers)) == len(identifiers)

    def test_a_malformed_completion_report_is_gate_evidence(self, tmp_path: Path) -> None:
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"stage_id": "AUTO-999"}), encoding="utf-8")
        registry = default_skill_registry()
        broker = CapabilityBroker(
            AgentKind.IMPLEMENTATION,
            skills={"validate_completion_report": registry["validate_completion_report"]},
        )
        agent = ImplementationAgent(
            broker,
            workflow_id=WORKFLOW_ID,
            stage_id="AUTO-999",
            stage_branch=STAGE_BRANCH,
            repository_path=tmp_path,
            baseline_commit_sha="a" * 40,
            session_root=tmp_path / "sessions",
            audit_root=tmp_path / "audit",
        )
        result = agent.validate_own_report(report_path=report)
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.GATE_EVIDENCE
        assert result.evidence["schema_errors"]


class TestQAIndependence:
    def test_qa_cannot_approve_a_diff_whose_validation_failed(self, tmp_path: Path) -> None:
        """`MACHINE_GATES.md` §4's consistency requirement, in its most consequential form."""
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))
        result = qa.review(validation=failing_validation("run_tests"), attempt_number=1)

        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.GATE_EVIDENCE
        assert result.evidence["consistent_with_deterministic_validation"] is False
        assert result.evidence["verdict"] == "APPROVED"
        assert "run_tests" in result.error.detail

    def test_a_rejected_verdict_fails_the_review(self, tmp_path: Path) -> None:
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.FAIL))
        result = qa.review(validation=passing_validation(), attempt_number=1)

        assert result.ok is False
        assert result.evidence["verdict"] == "REJECTED"
        assert result.evidence["findings"] == ["finding: broken"]
        assert result.evidence["schema_passed"] is True

    def test_an_approved_verdict_on_a_passing_diff_succeeds(self, tmp_path: Path) -> None:
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))
        result = qa.review(validation=passing_validation(), attempt_number=1)

        assert result.ok is True
        assert result.evidence["verdict"] == "APPROVED"
        assert result.evidence["consistent_with_deterministic_validation"] is True

    def test_the_validated_artifact_is_the_stored_artifact(self, tmp_path: Path) -> None:
        """The report is written, then read back from disk and validated — not judged in memory
        and stored separately, which would let the two diverge."""
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))
        result = qa.review(validation=passing_validation(), attempt_number=1)

        stored = Path(result.evidence["report_path"])
        assert stored.is_file()
        payload = json.loads(stored.read_text(encoding="utf-8"))
        assert payload["verdict"] == "APPROVED"
        assert payload["deterministic_validation_passed"] is True

    def test_the_qa_prompt_carries_the_deterministic_results(self, tmp_path: Path) -> None:
        """A reviewer that cannot see the deterministic results cannot be consistent with them."""
        provider = qa_provider(ProviderVerdict.FAIL)
        qa, _ = build_qa_agent(tmp_path, provider)
        qa.review(validation=failing_validation("run_lint"), attempt_number=1)

        prompt = provider.invocations[0].prompt
        assert "Deterministic validation results" in prompt
        assert "run_lint" in prompt
        assert "do not defer to" in prompt

    def test_each_qa_round_writes_its_own_artifact(self, tmp_path: Path) -> None:
        """A repair loop runs several QA rounds; each keeps its own report rather than colliding
        with, or silently overwriting, the previous round's."""
        qa, _ = build_qa_agent(
            tmp_path, qa_provider(ProviderVerdict.FAIL, ProviderVerdict.FAIL, ProviderVerdict.PASS)
        )
        paths = [
            qa.review(validation=passing_validation(), attempt_number=attempt).evidence[
                "report_path"
            ]
            for attempt in (1, 2, 3)
        ]
        assert len(set(paths)) == 3
        for path in paths:
            assert Path(path).is_file()

    def test_qa_provider_failure_is_reported_not_raised(self, tmp_path: Path) -> None:
        provider = MockProvider(
            [
                provider_failure(
                    ProviderKind.CODEX_CLI,
                    ProviderFailureKind.MALFORMED_OUTPUT,
                    "no JSON object in the stream",
                )
            ]
        )
        qa, _ = build_qa_agent(tmp_path, provider)
        result = qa.review(validation=passing_validation(), attempt_number=1)

        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.PROVIDER_FAILED


class TestAgentsReportRatherThanDecide:
    """`AGENT_CONTRACTS.md` §1: the Orchestrator decides the resulting transition."""

    @pytest.mark.parametrize("attempt", [1, 2, 3])
    def test_no_result_carries_a_state(self, tmp_path: Path, attempt: int) -> None:
        agent, _ = build_implementation_agent(
            tmp_path,
            MockProvider([provider_success(canned_report(role=ProviderRole.IMPLEMENTATION))]),
        )
        result = agent.implement(contract_text="contract", attempt_number=attempt)
        for forbidden in ("next_state", "resulting_state", "transition", "verdict"):
            assert not hasattr(result, forbidden)
        assert set(result.evidence) & {"next_state", "transition"} == set()

    def test_qa_evidence_names_no_transition(self, tmp_path: Path) -> None:
        qa, _ = build_qa_agent(tmp_path, qa_provider(ProviderVerdict.PASS))
        result = qa.review(validation=passing_validation(), attempt_number=1)
        assert set(result.evidence) & {"next_state", "transition", "resulting_state"} == set()


def test_validation_outcome_reports_every_check(tmp_path: Path) -> None:
    outcome = ValidationOutcome(
        passed=False,
        checks=(
            ValidationCheck(name="run_tests", passed=False, detail="1 failed"),
            ValidationCheck(name="run_lint", passed=True),
        ),
    )
    assert [check.name for check in outcome.failed_checks] == ["run_tests"]
    assert outcome.failure_report()["failed_checks"] == [
        {"check": "run_tests", "detail": "1 failed"}
    ]


def test_qa_agent_cannot_read_the_implementation_report(tmp_path: Path) -> None:
    """Independence is structural: `validate_completion_report` is not in QA's capability set."""
    from agentos_workflow.agents import AGENT_SKILL_CONTRACTS, CapabilityViolation

    assert "validate_completion_report" not in AGENT_SKILL_CONTRACTS[AgentKind.QA]
    broker = CapabilityBroker(AgentKind.QA)
    with pytest.raises(CapabilityViolation):
        broker.invoke_skill("validate_completion_report", report_path=tmp_path / "r.json")


def test_implementation_agent_cannot_reach_the_qa_provider(tmp_path: Path) -> None:
    from agentos_workflow.agents import CapabilityViolation

    broker = CapabilityBroker(AgentKind.IMPLEMENTATION, providers=lambda role: MockProvider())
    with pytest.raises(CapabilityViolation):
        broker.provider(ProviderRole.QA)


def test_qa_agent_cannot_reach_the_implementation_provider(tmp_path: Path) -> None:
    from agentos_workflow.agents import CapabilityViolation

    broker = CapabilityBroker(AgentKind.QA, providers=lambda role: MockProvider())
    for role in (ProviderRole.IMPLEMENTATION, ProviderRole.REPAIR):
        with pytest.raises(CapabilityViolation):
            broker.provider(role)


def test_agents_module_never_imports_the_mock_provider() -> None:
    """`MVP_SCOPE.md` §3: `MockProvider` stays structurally out of the live path.

    Checked over executable source: the package docstrings explain *why* the mock is excluded, and
    a raw-text check would punish that explanation.
    """
    from agentos_workflow.tests.test_agents_capabilities import _executable_source

    package = Path(__file__).resolve().parent.parent / "agents"
    for path in sorted(package.glob("*.py")):
        assert "MockProvider" not in _executable_source(path), path.name
        assert "providers.mock" not in _executable_source(path), path.name


def test_default_gateway_uses_live_selection(tmp_path: Path) -> None:
    """The gateway a real workflow gets is typed to `CLIProvider`, so it cannot yield a mock."""
    from agentos_workflow.agents import live_provider_gateway
    from agentos_workflow.providers import CLIProvider
    from agentos_workflow.tests.test_providers_cli import valid_config

    gateway = live_provider_gateway(valid_config(tmp_path))
    for role in ProviderRole:
        provider: Any = gateway(role)
        assert isinstance(provider, CLIProvider)
        assert provider.kind is not ProviderKind.MOCK
