"""`QAAgent` — independent QA via the QA provider (`AGENT_CONTRACTS.md` §4).

Drives `QA_RUNNING → READY_TO_COMMIT` / `REPAIRING` / `FAILED` by reporting a verdict the
Orchestrator acts on. Two properties matter more than anything else in this module:

**Independence.** The verdict comes from `CodexCLIProvider`'s own report, never from
`ImplementationAgent`'s self-report (`MACHINE_GATES.md` §4). This Agent has no access to the
implementation report at all — its capability set does not include `validate_completion_report`,
and its provider role is `QA` only — so "QA copied the implementer's verdict" is not something a
future edit can quietly introduce.

**Consistency with the deterministic gate.** `MACHINE_GATES.md` §4 requires the QA report to be
"internally consistent with the deterministic validation results it was given". A QA pass on a
diff whose deterministic validation failed is contradictory evidence, and this Agent reports it as
a failed review rather than letting a model's optimism override a machine gate that already said
no.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentos_workflow.agents import (
    Agent,
    AgentFailureKind,
    AgentKind,
    AgentResult,
    CapabilityBroker,
    ValidationOutcome,
    agent_failure,
    agent_success,
    retry_classification_of,
)
from agentos_workflow.providers import ProviderInvocation, ProviderRole, ProviderVerdict
from agentos_workflow.skills import RetryClassification

__all__ = ["QAAgent"]


class QAAgent(Agent):
    """Runs independent QA over the implementation diff and the deterministic results."""

    def __init__(
        self,
        broker: CapabilityBroker,
        *,
        workflow_id: str,
        stage_id: str,
        stage_branch: str,
        repository_path: Path,
        session_root: Path,
        audit_root: Path,
        contract_text: str = "",
    ) -> None:
        super().__init__(broker)
        self._workflow_id = workflow_id
        self._stage_id = stage_id
        self._stage_branch = stage_branch
        self._repository_path = repository_path
        self._session_root = session_root
        self._audit_root = audit_root
        self._contract_text = contract_text

    @property
    def kind(self) -> AgentKind:
        return AgentKind.QA

    def _report_scope(self, attempt_number: int) -> str:
        """The audit scope this attempt's QA report artifact is written under.

        **Known limitation, deliberately visible rather than worked around silently.**
        `generate_qa_report` (AUTO-003) writes exactly one `reports/qa.json` per workflow
        identifier and refuses to overwrite it with differing content — correct behaviour for an
        append-only audit model, but it means a workflow cannot hold more than one QA report. A
        repair loop runs up to four QA rounds (`FAILURE_RECOVERY.md` §1), each producing a
        genuinely different report, so the second round would fail on the artifact rather than on
        the code under review.

        AUTO-005 cannot fix the Skill — `agentos_workflow/skills/**` is outside this stage's
        allowed paths — so each round is written under a per-attempt scope derived from the
        workflow identifier. Every artifact stays inside the audit root, and the workflow's own
        audit *log* still uses the real, undecorated workflow identifier, so the rounds remain
        joined to their workflow. The proper fix is an attempt-aware filename in the reporting
        Skills, which belongs to whichever stage next owns `skills/reporting.py`; it is recorded in
        this stage's completion report rather than left as a surprise.
        """
        return f"{self._workflow_id}.qa{attempt_number}"

    def review(
        self,
        *,
        validation: ValidationOutcome,
        attempt_number: int,
        changed_files: tuple[str, ...] = (),
        head_sha: str = "",
    ) -> AgentResult:
        """Run one independent QA pass and report its verdict.

        The report the provider returns is written through `generate_qa_report` and then read back
        through `validate_qa_report`. Round-tripping it through the artifact rather than judging
        the in-memory object is deliberate: the artifact is what the audit trail keeps and what a
        later reviewer reads, so the thing validated is the thing stored, not a parallel copy that
        could differ from it.
        """
        action = "review"
        provider = self._broker.provider(ProviderRole.QA)
        result = provider.invoke(
            ProviderInvocation(
                workflow_id=self._workflow_id,
                stage_id=self._stage_id,
                role=ProviderRole.QA,
                prompt=_qa_prompt(
                    stage_id=self._stage_id,
                    stage_branch=self._stage_branch,
                    validation=validation,
                    changed_files=changed_files,
                    contract_text=self._contract_text,
                ),
                working_directory=self._repository_path,
                session_root=self._session_root,
                invocation_id=f"qa-{attempt_number}",
            )
        )
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
                str(error) if error is not None else "QA provider returned no report",
                retry_classification=(
                    error.retry_classification
                    if error is not None
                    else RetryClassification.NON_RETRYABLE
                ),
                source=ProviderRole.QA.value,
                evidence={"attempt_number": attempt_number},
            )

        report = result.value
        verdict_token = "APPROVED" if report.verdict is ProviderVerdict.PASS else "REJECTED"
        payload: dict[str, Any] = {
            "stage_id": self._stage_id,
            "branch": self._stage_branch,
            "head_sha": head_sha or "unknown",
            "summary": report.summary,
            "verdict": verdict_token,
            "findings": list(report.findings),
            "attempt_number": attempt_number,
            "deterministic_validation_passed": validation.passed,
            "deterministic_failed_checks": [check.name for check in validation.failed_checks],
            "provider": report.provider.value,
        }
        written = self._broker.invoke_skill(
            "generate_qa_report",
            audit_root=self._audit_root,
            workflow_id=self._report_scope(attempt_number),
            results=payload,
        )
        if not written.ok or written.value is None:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"QA report could not be written: {written.error}",
                retry_classification=retry_classification_of(written),
                source="generate_qa_report",
                evidence={"attempt_number": attempt_number},
            )
        report_path = written.value.path

        validated = self._broker.invoke_skill("validate_qa_report", report_path=report_path)
        if not validated.ok or validated.value is None:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"QA report could not be validated: {validated.error}",
                retry_classification=retry_classification_of(validated),
                source="validate_qa_report",
                evidence={"attempt_number": attempt_number, "report_path": str(report_path)},
            )
        schema = validated.value

        consistent = not (verdict_token == "APPROVED" and not validation.passed)
        evidence: dict[str, Any] = {
            "attempt_number": attempt_number,
            "verdict": verdict_token,
            "findings": list(report.findings),
            "report_path": str(report_path),
            "schema_passed": schema.passed,
            "schema_errors": list(schema.schema_errors),
            "consistent_with_deterministic_validation": consistent,
            "deterministic_validation_passed": validation.passed,
            "provider": report.provider.value,
        }
        self._audit(
            {
                "action": action,
                "attempt_number": attempt_number,
                "verdict": verdict_token,
                "schema_passed": schema.passed,
            },
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )

        if not schema.passed:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.GATE_EVIDENCE,
                "QA report is schema-invalid: " + "; ".join(schema.schema_errors),
                evidence=evidence,
            )
        if not consistent:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.GATE_EVIDENCE,
                "QA approved a diff whose deterministic validation failed: "
                + ", ".join(check.name for check in validation.failed_checks),
                evidence=evidence,
            )
        if verdict_token != "APPROVED":
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.GATE_EVIDENCE,
                "QA verdict is REJECTED",
                evidence=evidence,
            )
        return agent_success(self.kind, action, evidence)


def _qa_prompt(
    *,
    stage_id: str,
    stage_branch: str,
    validation: ValidationOutcome,
    changed_files: tuple[str, ...],
    contract_text: str,
) -> str:
    """Build the QA prompt from the diff, the deterministic results, and the stage contract.

    The deterministic results are included because `MACHINE_GATES.md` §4 requires the QA verdict
    to be consistent with them — a reviewer that cannot see them cannot be consistent with them.
    They are given as data the reviewer must account for, never as a verdict to agree with.
    """
    results = json.dumps(
        {
            "passed": validation.passed,
            "checks": [
                {"check": check.name, "passed": check.passed, "detail": check.detail}
                for check in validation.checks
            ],
        },
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )
    return (
        f"Stage: {stage_id}\n"
        f"Stage branch: {stage_branch}\n"
        "Task: independently review this stage's diff. Derive your own verdict; do not defer to "
        "the implementer's self-report.\n\n"
        f"Changed files:\n{chr(10).join(changed_files) or '(none observed)'}\n\n"
        f"Deterministic validation results:\n{results}\n\n"
        f"Stage contract:\n{contract_text}\n"
    )
