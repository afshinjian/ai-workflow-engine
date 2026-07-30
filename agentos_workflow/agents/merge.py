"""`MergeAgent` — safe automatic squash merge (`AGENT_CONTRACTS.md` §6).

Drives `PR_OPEN → AUTO_MERGE_ENABLED → WAITING_FOR_CHECKS → MERGED`.

Two hard rules shape this module, and both are enforced by control flow rather than by comment:

**Head-SHA equality precedes enabling the merge** (`MACHINE_GATES.md` §5). `enable_auto_merge`
calls `verify_head_sha` first and returns without ever reaching
`enable_automatic_squash_merge` when the head differs. The engine never merges a diff it did not
validate, so the ordering — not a later check — is the guarantee.

**No admin-bypass path exists** (`AGENT_CONTRACTS.md` §6, `MACHINE_GATES.md` §5,
`SECURITY_MODEL.md` §4). This module never names an admin flag, never passes a force or bypass
argument, and has exactly one merge-enabling call site. `test_agents_git_merge.py` asserts the
absence over this module's own source, so a future edit that added one would fail a test rather
than merely contradict a docstring.

**Provisional Skills.** All four Skills here are delivered by AUTO-006 and are unbound today; see
`agents.PROVISIONAL_SKILL_NAMES` and `git.py`'s module docstring.
"""

from __future__ import annotations

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

__all__ = ["MergeAgent"]


class MergeAgent(Agent):
    """Enables the squash merge only behind the merge-safety gate, and confirms it independently."""

    def __init__(
        self,
        broker: CapabilityBroker,
        *,
        workflow_id: str,
        stage_id: str,
        stage_branch: str,
        repository_path: Path,
        audit_root: Path,
        pull_request_number: int,
        recorded_head_sha: str,
        allowed_environment_variables: tuple[str, ...] = (),
    ) -> None:
        super().__init__(broker)
        self._workflow_id = workflow_id
        self._stage_id = stage_id
        self._stage_branch = stage_branch
        self._repository_path = repository_path
        self._audit_root = audit_root
        self._pull_request_number = pull_request_number
        self._recorded_head_sha = recorded_head_sha
        # OD-10: every `gh`-facing Skill this Agent invokes takes an environment allowlist, but
        # this Agent had no way to supply one, so `gh` ran with an empty environment and could not
        # see its own credential/config variables. Defaulted to `()` to match `GitAgent`, so an
        # omitted value is an explicitly empty allowlist rather than an inherited environment.
        self._allowed_environment_variables = allowed_environment_variables

    @property
    def kind(self) -> AgentKind:
        return AgentKind.MERGE

    def enable_auto_merge(
        self, *, deterministic_validation_passed: bool, qa_passed: bool
    ) -> AgentResult:
        """Enable automatic squash merge, but only if every §5 condition independently holds.

        The two gate results are parameters rather than something this Agent re-derives: they are
        the Orchestrator's own findings from `MACHINE_GATES.md` §3 and §4, and an Agent
        recomputing them would be a second opinion on a gate that has already spoken. What this
        Agent adds is the third condition — the head SHA — which only it is positioned to check
        immediately before enabling the merge.
        """
        action = "enable_auto_merge"
        if not deterministic_validation_passed or not qa_passed:
            return self._refuse(
                action,
                "refusing to enable automatic merge: "
                f"deterministic_validation_passed={deterministic_validation_passed}, "
                f"qa_passed={qa_passed}",
                evidence={
                    "deterministic_validation_passed": deterministic_validation_passed,
                    "qa_passed": qa_passed,
                    "head_sha_verified": False,
                },
            )

        verified = self._broker.invoke_skill(
            "verify_head_sha",
            repository_path=self._repository_path,
            branch=self._stage_branch,
            expected_head_sha=self._recorded_head_sha,
        )
        if not verified.ok:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"head SHA could not be verified: {verified.error}",
                retry_classification=retry_classification_of(verified),
                source="verify_head_sha",
                evidence={
                    "expected_head_sha": self._recorded_head_sha,
                    "head_sha_verified": False,
                },
            )
        if not bool(verified.value):
            # `MACHINE_GATES.md` §5: a differing head means `FAILED`, never a merge of a diff that
            # was never validated. Returning here — before any merge-enabling call — is the
            # enforcement; the Orchestrator turns this failure into the terminal state.
            return self._refuse(
                action,
                "pull request head SHA no longer matches the SHA recorded when it was opened",
                evidence={
                    "expected_head_sha": self._recorded_head_sha,
                    "head_sha_verified": False,
                    "pull_request_number": self._pull_request_number,
                },
            )

        enabled = self._broker.invoke_skill(
            "enable_automatic_squash_merge",
            repository_path=self._repository_path,
            pull_request_number=self._pull_request_number,
            expected_head_sha=self._recorded_head_sha,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        if not enabled.ok:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"automatic squash merge could not be enabled: {enabled.error}",
                retry_classification=retry_classification_of(enabled),
                source="enable_automatic_squash_merge",
                evidence={"head_sha_verified": True},
            )
        evidence = {
            "pull_request_number": self._pull_request_number,
            "expected_head_sha": self._recorded_head_sha,
            "head_sha_verified": True,
            "merge_method": "squash",
        }
        self._audit(
            {"action": action, "passed": True, "pull_request": self._pull_request_number},
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_success(self.kind, action, evidence)

    def await_required_checks(self) -> AgentResult:
        """Report whether every required check has completed successfully
        (`MACHINE_GATES.md` §6).

        Reports rather than waits: a blocking sleep inside an Agent would hide the workflow's
        progress from the persisted state machine and make an interrupted wait indistinguishable
        from a hung one. The Orchestrator decides when to ask again.
        """
        action = "await_required_checks"
        checks = self._broker.invoke_skill(
            "read_required_checks",
            repository_path=self._repository_path,
            pull_request_number=self._pull_request_number,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        if not checks.ok or checks.value is None:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"required checks could not be read: {checks.error}",
                retry_classification=retry_classification_of(checks),
                source="read_required_checks",
            )
        value = checks.value
        all_passed = bool(getattr(value, "all_passed", False))
        pending = [str(check) for check in getattr(value, "pending", ())]
        failed = [str(check) for check in getattr(value, "failed", ())]
        evidence: dict[str, Any] = {
            "pull_request_number": self._pull_request_number,
            "all_passed": all_passed,
            "pending": pending,
            "failed": failed,
        }
        if failed:
            return self._refuse(
                action,
                f"required check(s) failed: {', '.join(failed)}",
                evidence=evidence,
            )
        if not all_passed:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.PRECONDITION,
                f"required check(s) still pending: {', '.join(pending)}",
                evidence=evidence,
            )
        return agent_success(self.kind, action, evidence)

    def confirm_merge(self) -> AgentResult:
        """Confirm the merge with GitHub itself, and return the confirmation token.

        `MACHINE_GATES.md` §6: closeout never begins on local Git evidence alone. The successful
        result carries the `MergeConfirmation` that `CloseoutAgent`'s branch-deletion Skills
        require and cannot be run without — so the independence requirement travels as a value
        through the workflow rather than as an instruction someone has to remember.
        """
        action = "confirm_merge"
        confirmed = self._broker.invoke_skill(
            "verify_merge_completion",
            repository_path=self._repository_path,
            pull_request_number=self._pull_request_number,
            branch=self._stage_branch,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        if not confirmed.ok or confirmed.value is None:
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                f"merge could not be independently confirmed: {confirmed.error}",
                retry_classification=retry_classification_of(confirmed),
                source="verify_merge_completion",
                evidence={"pull_request_number": self._pull_request_number},
            )
        confirmation = confirmed.value
        evidence: dict[str, Any] = {
            "pull_request_number": self._pull_request_number,
            "merge_confirmation": confirmation,
            "merge_commit_sha": getattr(confirmation, "merge_commit_sha", None),
            "stage_branch": self._stage_branch,
        }
        self._audit(
            {
                "action": action,
                "passed": True,
                "merge_commit_sha": getattr(confirmation, "merge_commit_sha", None),
            },
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_success(self.kind, action, evidence)

    def _refuse(self, action: str, detail: str, *, evidence: dict[str, Any]) -> AgentResult:
        """Record and return a gate refusal."""
        self._audit(
            {"action": action, "passed": False, "reason": detail},
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_failure(
            self.kind,
            action,
            AgentFailureKind.GATE_EVIDENCE,
            detail,
            evidence=evidence,
        )
