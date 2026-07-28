"""`ImplementationAgent` — stage implementation and automatic repair
(`AGENT_CONTRACTS.md` §3).

Drives `BRANCH_CREATED → IMPLEMENTING → VALIDATING` and `REPAIRING → VALIDATING` by returning
typed results. It never decides whether a failed provider invocation means retry, reconciled
success, `REPAIRING`, or `FAILED` — `WORKFLOW_STATES.md` §5a's initial-execution policy is the
Orchestrator's, and this Agent's job is to hand it the evidence with the Skill's own retry
classification intact.

`implement` and `repair` are the same shape deliberately: a repair is an implementation attempt
that additionally receives the latest failure report (`FAILURE_RECOVERY.md` §2). They differ in
provider role (`IMPLEMENTATION` vs `REPAIR`) and in what goes into the prompt, not in what the
Orchestrator gets back.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentos_workflow.agents import (
    Agent,
    AgentFailureKind,
    AgentKind,
    AgentResult,
    CapabilityBroker,
    agent_failure,
    agent_success,
    retry_classification_of,
)
from agentos_workflow.providers import ProviderInvocation, ProviderRole
from agentos_workflow.skills import RetryClassification

__all__ = ["ImplementationAgent"]


class ImplementationAgent(Agent):
    """Implements the stage contract, and repairs it when the Orchestrator directs a repair."""

    def __init__(
        self,
        broker: CapabilityBroker,
        *,
        workflow_id: str,
        stage_id: str,
        stage_branch: str,
        repository_path: Path,
        baseline_commit_sha: str,
        session_root: Path,
        audit_root: Path,
        allowed_paths: tuple[str, ...] = (),
        forbidden_paths: tuple[str, ...] = (),
    ) -> None:
        super().__init__(broker)
        self._workflow_id = workflow_id
        self._stage_id = stage_id
        self._stage_branch = stage_branch
        self._repository_path = repository_path
        self._baseline_commit_sha = baseline_commit_sha
        self._session_root = session_root
        self._audit_root = audit_root
        self._allowed_paths = allowed_paths
        self._forbidden_paths = forbidden_paths

    @property
    def kind(self) -> AgentKind:
        return AgentKind.IMPLEMENTATION

    def implement(self, *, contract_text: str, attempt_number: int = 1) -> AgentResult:
        """Invoke the implementation provider once, then observe what it actually changed."""
        return self._attempt(
            action="implement",
            role=ProviderRole.IMPLEMENTATION,
            prompt=_implementation_prompt(
                stage_id=self._stage_id,
                stage_branch=self._stage_branch,
                contract_text=contract_text,
            ),
            attempt_number=attempt_number,
        )

    def repair(self, *, failure_report: Mapping[str, Any], attempt_number: int) -> AgentResult:
        """Invoke the repair provider with the **latest** failure report.

        `failure_report` is whatever the gate that just rejected the diff produced — a QA report or
        a deterministic-validation failure detail. It is passed straight through rather than
        accumulated across attempts: `FAILURE_RECOVERY.md` §1 requires the latest report and §2
        deliberately withholds full prior-attempt history, so a repair session works from the
        current state of the diff rather than re-litigating earlier rounds.
        """
        return self._attempt(
            action="repair",
            role=ProviderRole.REPAIR,
            prompt=_repair_prompt(
                stage_id=self._stage_id,
                stage_branch=self._stage_branch,
                failure_report=failure_report,
                attempt_number=attempt_number,
            ),
            attempt_number=attempt_number,
        )

    def _attempt(
        self, *, action: str, role: ProviderRole, prompt: str, attempt_number: int
    ) -> AgentResult:
        provider = self._broker.provider(role)
        invocation = ProviderInvocation(
            workflow_id=self._workflow_id,
            stage_id=self._stage_id,
            role=role,
            prompt=prompt,
            working_directory=self._repository_path,
            session_root=self._session_root,
            invocation_id=f"{action}-{attempt_number}",
        )
        result = provider.invoke(invocation)
        if not result.ok or result.value is None:
            error = result.error
            self._audit(
                {"action": action, "attempt_number": attempt_number, "passed": False},
                audit_root=self._audit_root,
                workflow_id=self._workflow_id,
            )
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.PROVIDER_FAILED,
                str(error) if error is not None else "provider returned no report",
                retry_classification=(
                    error.retry_classification
                    if error is not None
                    else RetryClassification.NON_RETRYABLE
                ),
                source=role.value,
                evidence={"attempt_number": attempt_number, "stage_branch": self._stage_branch},
            )

        report = result.value
        # The provider's own `files_changed` is a *claim*. What the Orchestrator's gates read is
        # the observed diff, derived independently from Git — the same principle the engine's
        # Milestone 3 claim verification already established: an agent's self-report is never
        # evidence for itself.
        observed = self._broker.invoke_skill(
            "list_changed_files",
            repository_path=self._repository_path,
            base=self._baseline_commit_sha,
            branch=self._stage_branch,
        )
        if not observed.ok or observed.value is None:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"could not observe the stage-branch diff: {observed.error}",
                retry_classification=retry_classification_of(observed),
                source="list_changed_files",
                evidence={"attempt_number": attempt_number},
            )
        changed_paths: tuple[str, ...] = tuple(observed.value)

        diff = self._broker.invoke_skill(
            "inspect_diff",
            repository_path=self._repository_path,
            base=self._baseline_commit_sha,
            branch=self._stage_branch,
        )
        scope = self._broker.invoke_skill(
            "validate_allowed_paths",
            changed_files=changed_paths,
            allowed_paths=self._allowed_paths,
            forbidden_paths=self._forbidden_paths,
        )
        scope_passed = bool(scope.ok and scope.value is not None and scope.value.passed)

        evidence: dict[str, Any] = {
            "attempt_number": attempt_number,
            "stage_branch": self._stage_branch,
            "observed_changed_paths": list(changed_paths),
            "claimed_changed_paths": list(report.files_changed),
            "claim_matches_observation": sorted(report.files_changed) == sorted(changed_paths),
            "scope_passed": scope_passed,
            "scope_violations": (
                [
                    {"path": violation.path, "reason": violation.reason}
                    for violation in scope.value.violations
                ]
                if scope.ok and scope.value is not None
                else []
            ),
            "files_changed_count": (
                diff.value.files_changed if diff.ok and diff.value is not None else None
            ),
            "recommended_commit_message": report.recommended_commit_message,
            "provider": report.provider.value,
            "provider_verdict": report.verdict.value,
            "summary": report.summary,
        }
        self._audit(
            {
                "action": action,
                "attempt_number": attempt_number,
                "passed": True,
                "changed_path_count": len(changed_paths),
            },
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        # A scope violation is reported, not judged: `MACHINE_GATES.md` §3 runs
        # `run_scope_validation` as part of the deterministic gate, and having the Agent also fail
        # the attempt here would create a second, competing rule engine for the same question.
        return agent_success(self.kind, action, evidence)

    def validate_own_report(self, *, report_path: Path) -> AgentResult:
        """Check the stage completion report artifact is well-formed before the gate reads it.

        This is `validate_completion_report` used as the Agent's own pre-flight, not as the gate:
        the gate runs the same Skill again in the Orchestrator-owned `VALIDATING` sequence
        (`MACHINE_GATES.md` §3). Running it here too costs one file read and turns "the report the
        model wrote is malformed" into a fact recorded against the attempt that produced it.
        """
        action = "validate_own_report"
        result = self._broker.invoke_skill("validate_completion_report", report_path=report_path)
        if not result.ok or result.value is None:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"completion report could not be read: {result.error}",
                retry_classification=retry_classification_of(result),
                source="validate_completion_report",
            )
        validation = result.value
        evidence = {
            "passed": validation.passed,
            "schema_errors": list(validation.schema_errors),
            "report_path": str(report_path),
        }
        if not validation.passed:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.GATE_EVIDENCE,
                "completion report is schema-invalid: " + "; ".join(validation.schema_errors),
                evidence=evidence,
            )
        return agent_success(self.kind, action, evidence)


def _implementation_prompt(*, stage_id: str, stage_branch: str, contract_text: str) -> str:
    return (
        f"Stage: {stage_id}\n"
        f"Stage branch: {stage_branch}\n"
        "Task: implement this stage contract exactly, and no other work.\n\n"
        "Stage contract:\n"
        f"{contract_text}\n"
    )


def _repair_prompt(
    *,
    stage_id: str,
    stage_branch: str,
    failure_report: Mapping[str, Any],
    attempt_number: int,
) -> str:
    """Build the repair prompt from the latest failure report only.

    The report is serialized as canonical JSON rather than prose: it is machine-produced evidence,
    and re-narrating it in the prompt would be one more place for the failure detail to drift from
    what the gate actually reported.
    """
    serialized = json.dumps(dict(failure_report), sort_keys=True, indent=2, ensure_ascii=False)
    return (
        f"Stage: {stage_id}\n"
        f"Stage branch: {stage_branch}\n"
        f"Repair attempt: {attempt_number}\n"
        "Task: fix exactly the failures reported below. Change nothing else.\n\n"
        "Latest failure report:\n"
        f"{serialized}\n"
    )
