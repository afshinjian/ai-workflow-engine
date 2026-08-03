"""`CloseoutAgent` — cleanup, baseline restoration, and closeout reporting
(`AGENT_CONTRACTS.md` §7).

Drives `MERGED → CLOSING → DONE`.

**The hard rule, made structural.** §7 and `FAILURE_RECOVERY.md` §4 forbid destructive cleanup
without an independently verified merge. Three properties enforce that here:

1. `close_out` takes `merge_confirmation` as a **required, non-defaulted** parameter of type
   `MergeConfirmation` — the token `MergeAgent.confirm_merge` produces from
   `verify_merge_completion`, and the only thing AUTO-003's deletion Skills accept. "Delete without
   a confirmation" is not expressible.
2. Before any deletion, this Agent re-verifies the confirmation binds to *this* stage branch and
   carries a real merge commit. A token for another branch is refused rather than used.
3. Deletion is ordered last, after `checkout_baseline` and `fast_forward_pull` have succeeded. If
   the baseline cannot be restored, no branch is deleted at all — the failure leaves the merged
   work reachable from its branch rather than deleting the last local reference to it.

`FAILURE_RECOVERY.md` §4 also requires a closeout failure to record which steps already completed
safely, so every step's outcome is reported even when a later one fails.
"""

from __future__ import annotations

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
from agentos_workflow.skills import MergeConfirmation

__all__ = ["CloseoutAgent"]

_SHA_MIN_LENGTH = 7


class CloseoutAgent(Agent):
    """Restores the baseline, deletes the merged stage branch, and writes the closeout report."""

    def __init__(
        self,
        broker: CapabilityBroker,
        *,
        workflow_id: str,
        stage_id: str,
        stage_branch: str,
        baseline_branch: str,
        remote_name: str,
        repository_path: Path,
        audit_root: Path,
        allowed_environment_variables: tuple[str, ...] = (),
    ) -> None:
        super().__init__(broker)
        self._workflow_id = workflow_id
        self._stage_id = stage_id
        self._stage_branch = stage_branch
        self._baseline_branch = baseline_branch
        self._remote_name = remote_name
        self._repository_path = repository_path
        self._audit_root = audit_root
        self._allowed_environment_variables = allowed_environment_variables

    @property
    def kind(self) -> AgentKind:
        return AgentKind.CLOSEOUT

    def close_out(
        self,
        *,
        merge_confirmation: MergeConfirmation,
        delete_branches: bool = True,
        extra_report_fields: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        """Run the closeout sequence. Refuses entirely without a valid, matching confirmation.

        `delete_branches` (AUTO-014, additive, default `True` to preserve this method's original
        behavior for every caller that predates the flag): when `False`, the branch-deletion
        Skills are never invoked and the merged stage branch is retained, both locally and on the
        remote — the safe-default retention policy a target repository's own configuration
        selects. `extra_report_fields` (also AUTO-014, additive) lets a caller fold additional,
        already-computed evidence (workflow/task identity, validation and QA evidence, approval
        evidence, provider/agent-result references) into the one closeout report this Agent
        writes, so a caller never has to write — and thereby duplicate — a second closeout report
        of its own.
        """
        action = "close_out"
        steps: list[dict[str, Any]] = []

        refusal = self._validate_confirmation(action, merge_confirmation)
        if refusal is not None:
            return refusal

        checked_out = self._broker.invoke_skill(
            "checkout_baseline",
            repository_path=self._repository_path,
            baseline_branch=self._baseline_branch,
        )
        steps.append({"step": "checkout_baseline", "ok": bool(checked_out.ok)})
        if not checked_out.ok:
            return self._stop(
                action,
                f"baseline could not be checked out: {checked_out.error}",
                skill="checkout_baseline",
                steps=steps,
                retry=retry_classification_of(checked_out),
            )

        pulled = self._broker.invoke_skill(
            "fast_forward_pull",
            repository_path=self._repository_path,
            baseline_branch=self._baseline_branch,
            remote=self._remote_name,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        steps.append({"step": "fast_forward_pull", "ok": bool(pulled.ok)})
        if not pulled.ok:
            # Deliberately stops before deletion. `MACHINE_GATES.md` §7 requires the baseline to be
            # fast-forwarded to the merged commit; deleting the branch first and failing here would
            # leave the local repository with neither the branch nor the merge.
            return self._stop(
                action,
                f"baseline could not be fast-forwarded: {pulled.error}",
                skill="fast_forward_pull",
                steps=steps,
                retry=retry_classification_of(pulled),
            )

        if delete_branches:
            local_deleted = self._broker.invoke_skill(
                "delete_local_branch",
                repository_path=self._repository_path,
                branch=self._stage_branch,
                baseline_branch=self._baseline_branch,
                merge_confirmation=merge_confirmation,
            )
            steps.append({"step": "delete_local_branch", "ok": bool(local_deleted.ok)})
            if not local_deleted.ok:
                return self._stop(
                    action,
                    f"local stage branch could not be deleted: {local_deleted.error}",
                    skill="delete_local_branch",
                    steps=steps,
                    retry=retry_classification_of(local_deleted),
                )

            remote_deleted = self._broker.invoke_skill(
                "delete_remote_branch",
                repository_path=self._repository_path,
                branch=self._stage_branch,
                baseline_branch=self._baseline_branch,
                remote=self._remote_name,
                merge_confirmation=merge_confirmation,
                allowed_environment_variables=self._allowed_environment_variables,
            )
            steps.append({"step": "delete_remote_branch", "ok": bool(remote_deleted.ok)})
            if not remote_deleted.ok:
                return self._stop(
                    action,
                    f"remote stage branch could not be deleted: {remote_deleted.error}",
                    skill="delete_remote_branch",
                    steps=steps,
                    retry=retry_classification_of(remote_deleted),
                )
        else:
            # Safe-default retention (`WorkflowConfig.delete_branch_after_merge=False`): neither
            # deletion Skill is invoked at all, so a target repository that has not opted into
            # deletion can never lose its merged stage branch to this Agent.
            steps.append({"step": "delete_local_branch", "ok": True, "retained": True})
            steps.append({"step": "delete_remote_branch", "ok": True, "retained": True})

        final_state = self._broker.invoke_skill(
            "verify_final_repository_state",
            repository_path=self._repository_path,
            baseline_branch=self._baseline_branch,
        )
        steps.append({"step": "verify_final_repository_state", "ok": bool(final_state.ok)})
        if not final_state.ok or final_state.value is None:
            return self._stop(
                action,
                f"final repository state is not as required: {final_state.error}",
                skill="verify_final_repository_state",
                steps=steps,
                retry=retry_classification_of(final_state),
            )

        results: dict[str, Any] = {
            "stage_id": self._stage_id,
            "stage_branch": self._stage_branch,
            "baseline_branch": self._baseline_branch,
            "merge_commit_sha": merge_confirmation.merge_commit_sha,
            "final_head_sha": final_state.value.head_sha,
            "branches_deleted": delete_branches,
            "steps": steps,
            **(extra_report_fields or {}),
        }
        written = self._broker.invoke_skill(
            "generate_closeout_report",
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
            results=results,
        )
        steps.append({"step": "generate_closeout_report", "ok": bool(written.ok)})
        if not written.ok or written.value is None:
            return self._stop(
                action,
                f"closeout report could not be written: {written.error}",
                skill="generate_closeout_report",
                steps=steps,
                retry=retry_classification_of(written),
            )

        evidence = {**results, "closeout_report_path": str(written.value.path), "steps": steps}
        self._audit(
            {"action": action, "passed": True, "steps": steps},
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_success(self.kind, action, evidence)

    def _validate_confirmation(
        self, action: str, merge_confirmation: MergeConfirmation
    ) -> AgentResult | None:
        """Re-verify the merge confirmation immediately before any destructive step.

        `FAILURE_RECOVERY.md` §4's "never performs destructive cleanup without first re-verifying
        the merge" is why this runs here rather than trusting that whoever constructed the Agent
        already checked. A token bound to a different branch, or carrying no merge commit, is
        refused — and because this returns before the first Skill call, nothing has been touched.
        """
        if merge_confirmation.branch != self._stage_branch:
            return self._refuse(
                action,
                f"merge confirmation is for {merge_confirmation.branch!r}, not the stage branch "
                f"{self._stage_branch!r}",
            )
        if len(merge_confirmation.merge_commit_sha.strip()) < _SHA_MIN_LENGTH:
            return self._refuse(
                action,
                "merge confirmation carries no usable merge commit SHA",
            )
        return None

    def _refuse(self, action: str, detail: str) -> AgentResult:
        self._audit(
            {"action": action, "passed": False, "reason": detail, "destructive_steps_run": 0},
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_failure(
            self.kind,
            action,
            AgentFailureKind.PRECONDITION,
            detail,
            evidence={"steps": [], "stage_branch": self._stage_branch},
        )

    def _stop(
        self,
        action: str,
        detail: str,
        *,
        skill: str,
        steps: list[dict[str, Any]],
        retry: Any,
    ) -> AgentResult:
        """Fail the closeout, recording exactly which steps already completed safely."""
        self._audit(
            {"action": action, "passed": False, "reason": detail, "steps": steps},
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_failure(
            self.kind,
            action,
            AgentFailureKind.SKILL_FAILED,
            detail,
            retry_classification=retry,
            source=skill,
            evidence={"steps": steps, "stage_branch": self._stage_branch},
        )
