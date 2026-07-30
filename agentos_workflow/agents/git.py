"""`GitAgent` — commit, push, and pull-request creation (`AGENT_CONTRACTS.md` §5).

Drives `READY_TO_COMMIT → COMMITTED → PUSHED → PR_OPEN`. All three side-effecting Skills are
subject to `WORKFLOW_STATES.md` §5a's initial-execution retry/reconciliation policy, and this
Agent implements exactly its half of that: it returns the typed Skill result **with the Skill's
own retry classification preserved**, and decides nothing about retry, reconciliation, or the
resulting transition. There is no retry loop anywhere in this module — an Agent that retried a
push on its own would be making precisely the decision §5a reserves for the Orchestrator, and
would do it without the reconciliation step that makes a retry safe.

`REPAIRING` is unreachable from this phase (§5a item 4), so nothing here produces a repair report.

**Skill availability.** All five Git/GitHub Skills this Agent uses are delivered
(`skills/git_github.py`, AUTO-006) and bound in `default_skill_registry()` (GOV-AUTO-06), so this
Agent runs against the production registry. Between those two stages they were delivered but not
bound, and every method here returned `SKILL_UNAVAILABLE` against the default registry — the call
shapes below were written as AUTO-006's contract and never needed changing when it landed, which
is exactly why the omission went unnoticed.
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
from agentos_workflow.skills import SkillResult

__all__ = ["GitAgent"]


class GitAgent(Agent):
    """Creates the commit, pushes the stage branch, and opens the pull request."""

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
        return AgentKind.GIT

    def create_commit(self, *, message: str, expected_head_sha: str) -> AgentResult:
        """Create the stage commit.

        Expected Skill shape (AUTO-006): `create_commit(repository_path, *, branch, message,
        expected_head_sha) -> SkillResult[<has .commit_sha>]`. `expected_head_sha` is passed so the
        Skill can refuse to commit onto a branch that moved since validation — the Agent supplies
        the expectation, the Skill enforces it.
        """
        action = "create_commit"
        result = self._broker.invoke_skill(
            "create_commit",
            repository_path=self._repository_path,
            branch=self._stage_branch,
            message=message,
            expected_head_sha=expected_head_sha,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        return self._report(
            action,
            "create_commit",
            result,
            lambda value: {
                "commit_sha": getattr(value, "commit_sha", None),
                "stage_branch": self._stage_branch,
            },
        )

    def push_stage_branch(self, *, expected_head_sha: str) -> AgentResult:
        """Push the stage branch to its remote.

        Expected Skill shape (AUTO-006): `push_stage_branch(repository_path, *, branch, remote,
        expected_head_sha, allowed_environment_variables) -> SkillResult[<has .head_sha,
        .remote_ref>]`. A failure here is the canonical `POSSIBLE_SIDE_EFFECT` case — the remote
        may have accepted the push before the connection dropped — and the classification is
        forwarded untouched so the Orchestrator reconciles rather than blindly retrying.
        """
        action = "push_stage_branch"
        result = self._broker.invoke_skill(
            "push_stage_branch",
            repository_path=self._repository_path,
            branch=self._stage_branch,
            remote=self._remote_name,
            expected_head_sha=expected_head_sha,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        return self._report(
            action,
            "push_stage_branch",
            result,
            lambda value: {
                "remote_ref": getattr(value, "remote_ref", None),
                "head_sha": getattr(value, "head_sha", None),
                "stage_branch": self._stage_branch,
            },
        )

    def create_pull_request(self, *, title: str, body: str, head_sha: str) -> AgentResult:
        """Open the pull request and record the head SHA it was opened at.

        That recorded SHA is the input to `MACHINE_GATES.md` §5's merge-safety check: the merge is
        allowed only if the PR's current head still equals it. Recording it here, at the moment the
        PR is opened, is what makes the later comparison meaningful — a SHA re-read at merge time
        would compare a value to itself.
        """
        action = "create_pull_request"
        result = self._broker.invoke_skill(
            "create_pull_request",
            repository_path=self._repository_path,
            branch=self._stage_branch,
            baseline_branch=self._baseline_branch,
            title=title,
            body=body,
            head_sha=head_sha,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        return self._report(
            action,
            "create_pull_request",
            result,
            lambda value: {
                "pull_request_number": getattr(value, "number", None),
                "pull_request_url": getattr(value, "url", None),
                "recorded_head_sha": getattr(value, "head_sha", head_sha),
                "stage_branch": self._stage_branch,
            },
        )

    def read_pull_request_state(self, *, pull_request_number: int) -> AgentResult:
        """Read the pull request's current state.

        This is the read half of `WORKFLOW_STATES.md` §5a's reconciliation: when
        `create_pull_request` fails ambiguously, the Orchestrator asks this Agent what actually
        exists rather than opening a second pull request.
        """
        action = "read_pull_request_state"
        result = self._broker.invoke_skill(
            "read_pull_request_state",
            repository_path=self._repository_path,
            pull_request_number=pull_request_number,
            allowed_environment_variables=self._allowed_environment_variables,
        )
        return self._report(
            action,
            "read_pull_request_state",
            result,
            lambda value: {
                "pull_request_number": pull_request_number,
                "state": getattr(value, "state", None),
                "head_sha": getattr(value, "head_sha", None),
                "merged": getattr(value, "merged", None),
            },
        )

    def verify_head_sha(self, *, expected_head_sha: str) -> AgentResult:
        """Confirm the stage branch's head is still what was validated."""
        action = "verify_head_sha"
        result = self._broker.invoke_skill(
            "verify_head_sha",
            repository_path=self._repository_path,
            branch=self._stage_branch,
            expected_head_sha=expected_head_sha,
        )
        return self._report(
            action,
            "verify_head_sha",
            result,
            lambda value: {
                "matches": bool(value),
                "expected_head_sha": expected_head_sha,
                "stage_branch": self._stage_branch,
            },
        )

    def _report(
        self,
        action: str,
        skill: str,
        result: SkillResult[Any],
        evidence_of: Any,
    ) -> AgentResult:
        """Turn one Skill result into an Agent result, preserving retry classification."""
        if not result.ok or result.value is None:
            self._audit(
                {"action": action, "passed": False},
                audit_root=self._audit_root,
                workflow_id=self._workflow_id,
            )
            return agent_failure(
                self.kind,
                action,
                (
                    AgentFailureKind.SKILL_UNAVAILABLE
                    if _is_unbound(result, skill)
                    else AgentFailureKind.SKILL_FAILED
                ),
                str(result.error) if result.error is not None else f"{skill} returned no value",
                retry_classification=retry_classification_of(result),
                source=skill,
                evidence={"stage_branch": self._stage_branch, "stage_id": self._stage_id},
            )
        evidence = dict(evidence_of(result.value))
        evidence.setdefault("stage_id", self._stage_id)
        self._audit(
            {"action": action, "passed": True},
            audit_root=self._audit_root,
            workflow_id=self._workflow_id,
        )
        return agent_success(self.kind, action, evidence)


def _is_unbound(result: SkillResult[Any], skill: str) -> bool:
    """Whether this failure is the broker's "provisional Skill not bound" answer.

    Distinguishing it from a real Skill failure matters to an operator: "the Skill does not exist
    yet" and "the push was rejected" are the same shape of failure but call for entirely different
    responses — hence the separate `SKILL_UNAVAILABLE` classification.

    GOV-AUTO-06 widened this from the provisional case to *both* of the broker's no-binding
    answers. It previously required membership in `PROVISIONAL_SKILL_NAMES` and the literal string
    `AUTO-006`; with that set now empty, the narrow form would have silently reclassified every
    missing binding as an ordinary `SKILL_FAILED`, losing the `SKILL_UNAVAILABLE` distinction this
    Agent has always drawn. That would be a behaviour change well beyond binding the Skills, so the
    distinction is preserved: from this Agent's side "the Skill is not available to me" is the same
    situation whether nothing implements it yet or this registry simply does not bind it.

    Both phrasings are matched because the broker chooses between them, and neither is inferable
    from `SkillFailure` alone without adding a field to it. The coupling is deliberate and guarded:
    `test_agents_capabilities.py` asserts both exact detail strings, so changing either wording
    fails there rather than silently degrading this classification.
    """
    error = result.error
    if error is None or error.skill != skill:
        return False
    return "is not yet implemented" in error.detail or "is not bound in this registry" in (
        error.detail
    )
