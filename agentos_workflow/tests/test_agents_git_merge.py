"""`GitAgent` and `MergeAgent` (`AGENT_CONTRACTS.md` §5-6, `MACHINE_GATES.md` §5-6).

The five Git/GitHub Skills these Agents call are delivered by AUTO-006 and unbound today, so they
are exercised against recording fakes with the call shapes `git.py`/`merge.py` document. That is
the stage contract's own instruction ("this stage may use fixtures/mocks for those Skills if
AUTO-006 has not yet landed, clearly marked as provisional"), and it lets the merge-safety
ordering — the property that actually matters — be tested now rather than after AUTO-006 lands.

The headline test is `test_merge_is_refused_when_head_sha_differs`: the Agent must not merely
report the mismatch, it must never reach `enable_automatic_squash_merge` at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.agents import (
    AgentFailureKind,
    AgentKind,
    CapabilityBroker,
)
from agentos_workflow.agents.git import GitAgent
from agentos_workflow.agents.merge import MergeAgent
from agentos_workflow.skills import (
    FailureKind,
    MergeConfirmation,
    RetryClassification,
    SkillFailure,
    SkillResult,
    success,
    utc_now,
)

WORKFLOW_ID = "wf-git"
STAGE_ID = "AUTO-999"
STAGE_BRANCH = "feature/auto-999-example"
BASELINE = "main"
HEAD_SHA = "b" * 40
OTHER_SHA = "c" * 40
PR_NUMBER = 42


class Recorder:
    """Records every Skill call so a test can assert what was — and was not — invoked."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def binding(self, name: str, result: Any) -> Any:
        def call(**kwargs: Any) -> SkillResult[Any]:
            self.calls.append((name, kwargs))
            produced = result() if callable(result) else result
            assert isinstance(produced, SkillResult)
            return produced

        return call

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


class Commit:
    commit_sha = "d" * 40


class Push:
    remote_ref = f"refs/heads/{STAGE_BRANCH}"
    head_sha = HEAD_SHA


class PullRequest:
    number = PR_NUMBER
    url = "https://example.invalid/pr/42"
    head_sha = HEAD_SHA


class PullRequestState:
    state = "open"
    head_sha = HEAD_SHA
    merged = False


class Checks:
    def __init__(self, all_passed: bool, pending: tuple[str, ...], failed: tuple[str, ...]) -> None:
        self.all_passed = all_passed
        self.pending = pending
        self.failed = failed


class Appended:
    event_id = "e"
    appended = True
    path = Path("/dev/null")


def audit_binding(recorder: Recorder) -> Any:
    return recorder.binding("append_audit_event", success(Appended()))


def git_agent(tmp_path: Path, recorder: Recorder, skills: dict[str, Any]) -> GitAgent:
    bindings = dict(skills)
    bindings.setdefault("append_audit_event", audit_binding(recorder))
    return GitAgent(
        CapabilityBroker(AgentKind.GIT, skills=bindings),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        baseline_branch=BASELINE,
        remote_name="origin",
        repository_path=tmp_path,
        audit_root=tmp_path / "audit",
    )


def merge_agent(
    tmp_path: Path,
    recorder: Recorder,
    skills: dict[str, Any],
    *,
    recorded_head_sha: str = HEAD_SHA,
) -> MergeAgent:
    bindings = dict(skills)
    bindings.setdefault("append_audit_event", audit_binding(recorder))
    return MergeAgent(
        CapabilityBroker(AgentKind.MERGE, skills=bindings),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        repository_path=tmp_path,
        audit_root=tmp_path / "audit",
        pull_request_number=PR_NUMBER,
        recorded_head_sha=recorded_head_sha,
    )


class TestMergeSafetyGate:
    """`MACHINE_GATES.md` §5: the merge is enabled only behind three independent conditions."""

    def test_merge_is_refused_when_head_sha_differs(self, tmp_path: Path) -> None:
        """The stage contract's named test: a `verify_head_sha` mismatch stops the merge.

        Two assertions, and the second is the one that matters: the result is a failure *and*
        `enable_automatic_squash_merge` was never called. An Agent that enabled the merge and then
        reported a problem would satisfy the first assertion while merging a diff it never
        validated.
        """
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "verify_head_sha": recorder.binding("verify_head_sha", success(False)),
                "enable_automatic_squash_merge": recorder.binding(
                    "enable_automatic_squash_merge", success(True)
                ),
            },
        )
        result = agent.enable_auto_merge(deterministic_validation_passed=True, qa_passed=True)

        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.GATE_EVIDENCE
        assert "head SHA" in result.error.detail
        assert "enable_automatic_squash_merge" not in recorder.names
        assert result.evidence["head_sha_verified"] is False

    def test_merge_proceeds_when_every_condition_holds(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "verify_head_sha": recorder.binding("verify_head_sha", success(True)),
                "enable_automatic_squash_merge": recorder.binding(
                    "enable_automatic_squash_merge", success(True)
                ),
            },
        )
        result = agent.enable_auto_merge(deterministic_validation_passed=True, qa_passed=True)

        assert result.ok is True
        assert recorder.names.count("enable_automatic_squash_merge") == 1
        assert recorder.names.index("verify_head_sha") < recorder.names.index(
            "enable_automatic_squash_merge"
        ), "the head SHA must be verified before the merge is enabled, not after"
        assert result.evidence["merge_method"] == "squash"

    @pytest.mark.parametrize(
        ("validation_passed", "qa_passed"),
        [(False, True), (True, False), (False, False)],
    )
    def test_merge_is_refused_without_both_gates(
        self, tmp_path: Path, validation_passed: bool, qa_passed: bool
    ) -> None:
        """§5's first two conditions: deterministic validation and independent QA must both have
        passed. The head SHA is not even read when they have not."""
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "verify_head_sha": recorder.binding("verify_head_sha", success(True)),
                "enable_automatic_squash_merge": recorder.binding(
                    "enable_automatic_squash_merge", success(True)
                ),
            },
        )
        result = agent.enable_auto_merge(
            deterministic_validation_passed=validation_passed, qa_passed=qa_passed
        )
        assert result.ok is False
        assert "enable_automatic_squash_merge" not in recorder.names
        assert "verify_head_sha" not in recorder.names

    def test_a_head_sha_skill_failure_never_enables_the_merge(self, tmp_path: Path) -> None:
        """ "Could not check" is not "checked and matched"."""
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "verify_head_sha": recorder.binding(
                    "verify_head_sha",
                    SkillResult(
                        ok=False,
                        error=SkillFailure(
                            skill="verify_head_sha",
                            kind=FailureKind.COMMAND_FAILED,
                            detail="git exited 128",
                            retry_classification=RetryClassification.NON_RETRYABLE,
                        ),
                    ),
                ),
                "enable_automatic_squash_merge": recorder.binding(
                    "enable_automatic_squash_merge", success(True)
                ),
            },
        )
        result = agent.enable_auto_merge(deterministic_validation_passed=True, qa_passed=True)
        assert result.ok is False
        assert "enable_automatic_squash_merge" not in recorder.names


class TestChecksWaitGate:
    """`MACHINE_GATES.md` §6."""

    def test_a_failed_required_check_is_a_refusal(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "read_required_checks": recorder.binding(
                    "read_required_checks", success(Checks(False, (), ("ci/tests",)))
                )
            },
        )
        result = agent.await_required_checks()
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.GATE_EVIDENCE
        assert result.evidence["failed"] == ["ci/tests"]

    def test_pending_checks_are_not_a_failure_verdict(self, tmp_path: Path) -> None:
        """A check that has not finished is not a check that failed — `WAITING_FOR_CHECKS` is a
        state the workflow stays in, not one it fails from."""
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "read_required_checks": recorder.binding(
                    "read_required_checks", success(Checks(False, ("ci/tests",), ()))
                )
            },
        )
        result = agent.await_required_checks()
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.PRECONDITION
        assert result.evidence["pending"] == ["ci/tests"]

    def test_all_checks_passed(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "read_required_checks": recorder.binding(
                    "read_required_checks", success(Checks(True, (), ()))
                )
            },
        )
        assert agent.await_required_checks().ok is True


class TestIndependentMergeConfirmation:
    """`MACHINE_GATES.md` §6: closeout never begins on local Git evidence alone."""

    def test_confirmation_carries_the_token_closeout_requires(self, tmp_path: Path) -> None:
        recorder = Recorder()
        confirmation = MergeConfirmation(
            branch=STAGE_BRANCH, merge_commit_sha="e" * 40, verified_at=utc_now()
        )
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "verify_merge_completion": recorder.binding(
                    "verify_merge_completion", success(confirmation)
                )
            },
        )
        result = agent.confirm_merge()
        assert result.ok is True
        assert result.evidence["merge_confirmation"] is confirmation
        assert result.evidence["merge_commit_sha"] == "e" * 40

    def test_an_unconfirmed_merge_produces_no_token(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = merge_agent(
            tmp_path,
            recorder,
            {
                "verify_merge_completion": recorder.binding(
                    "verify_merge_completion",
                    SkillResult(
                        ok=False,
                        error=SkillFailure(
                            skill="verify_merge_completion",
                            kind=FailureKind.PRECONDITION,
                            detail="GitHub reports the pull request as open",
                        ),
                    ),
                )
            },
        )
        result = agent.confirm_merge()
        assert result.ok is False
        assert "merge_confirmation" not in result.evidence


class TestGitAgent:
    """`AGENT_CONTRACTS.md` §5 — reports, never decides."""

    def test_commit_push_and_pull_request(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = git_agent(
            tmp_path,
            recorder,
            {
                "create_commit": recorder.binding("create_commit", success(Commit())),
                "push_stage_branch": recorder.binding("push_stage_branch", success(Push())),
                "create_pull_request": recorder.binding(
                    "create_pull_request", success(PullRequest())
                ),
            },
        )
        committed = agent.create_commit(message="feat: x", expected_head_sha=HEAD_SHA)
        assert committed.ok and committed.evidence["commit_sha"] == "d" * 40

        pushed = agent.push_stage_branch(expected_head_sha=HEAD_SHA)
        assert pushed.ok and pushed.evidence["head_sha"] == HEAD_SHA

        opened = agent.create_pull_request(title="t", body="b", head_sha=HEAD_SHA)
        assert opened.ok
        assert opened.evidence["pull_request_number"] == PR_NUMBER
        assert opened.evidence["recorded_head_sha"] == HEAD_SHA

    def test_push_failure_preserves_the_skills_retry_classification(self, tmp_path: Path) -> None:
        """`WORKFLOW_STATES.md` §5a: the Orchestrator decides retry vs. reconcile, and can only do
        so if the Agent forwards the Skill's own classification instead of inventing one."""
        recorder = Recorder()
        agent = git_agent(
            tmp_path,
            recorder,
            {
                "push_stage_branch": recorder.binding(
                    "push_stage_branch",
                    SkillResult(
                        ok=False,
                        error=SkillFailure(
                            skill="push_stage_branch",
                            kind=FailureKind.COMMAND_FAILED,
                            detail="connection reset",
                            retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                        ),
                    ),
                )
            },
        )
        result = agent.push_stage_branch(expected_head_sha=HEAD_SHA)
        assert result.ok is False
        assert result.error is not None
        assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT

    def test_reconciliation_read_reports_what_actually_exists(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = git_agent(
            tmp_path,
            recorder,
            {
                "read_pull_request_state": recorder.binding(
                    "read_pull_request_state", success(PullRequestState())
                )
            },
        )
        result = agent.read_pull_request_state(pull_request_number=PR_NUMBER)
        assert result.ok is True
        assert result.evidence["state"] == "open"
        assert result.evidence["merged"] is False


class TestUnboundSkillsAreHonestlyUnavailable:
    """Given a registry that binds nothing, every Git/GitHub action fails loudly and specifically.

    Unchanged in substance since AUTO-005; only the reason a Skill can be missing has changed.
    These Agents are constructed with `skills={}`, never the production registry, so the property
    under test is the Agent's handling of an absent binding — not whether the real registry has
    one. `test_agents_capabilities.py` covers the production registry, and since GOV-AUTO-06 it
    proves all eight are bound there.
    """

    @pytest.mark.parametrize(
        ("method", "kwargs"),
        [
            ("create_commit", {"message": "m", "expected_head_sha": HEAD_SHA}),
            ("push_stage_branch", {"expected_head_sha": HEAD_SHA}),
            ("create_pull_request", {"title": "t", "body": "b", "head_sha": HEAD_SHA}),
            ("read_pull_request_state", {"pull_request_number": PR_NUMBER}),
            ("verify_head_sha", {"expected_head_sha": HEAD_SHA}),
        ],
    )
    def test_unbound_skill_reports_unavailable(
        self, tmp_path: Path, method: str, kwargs: dict[str, Any]
    ) -> None:
        agent = GitAgent(
            CapabilityBroker(AgentKind.GIT, skills={}),
            workflow_id=WORKFLOW_ID,
            stage_id=STAGE_ID,
            stage_branch=STAGE_BRANCH,
            baseline_branch=BASELINE,
            remote_name="origin",
            repository_path=tmp_path,
            audit_root=tmp_path / "audit",
        )
        result = getattr(agent, method)(**kwargs)
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.SKILL_UNAVAILABLE
        # GOV-AUTO-06: the detail no longer names AUTO-006. That stage has shipped, so a message
        # blaming it for the absence would be false; with nothing classified provisional, an absent
        # binding is a registry gap. The `SKILL_UNAVAILABLE` classification above is deliberately
        # unchanged — from this Agent's side the situation is identical either way, and letting it
        # decay to `SKILL_FAILED` would have been a behaviour change beyond binding the Skills.
        assert "is not bound in this registry" in result.error.detail
        assert "AUTO-006" not in result.error.detail

    def test_an_unbound_skill_never_looks_like_success(self, tmp_path: Path) -> None:
        """The failure mode a stub would have introduced: a machine gate reading a fabricated
        pass."""
        agent = MergeAgent(
            CapabilityBroker(AgentKind.MERGE, skills={}),
            workflow_id=WORKFLOW_ID,
            stage_id=STAGE_ID,
            stage_branch=STAGE_BRANCH,
            repository_path=tmp_path,
            audit_root=tmp_path / "audit",
            pull_request_number=PR_NUMBER,
            recorded_head_sha=HEAD_SHA,
        )
        assert (
            agent.enable_auto_merge(deterministic_validation_passed=True, qa_passed=True).ok
            is False
        )
        assert agent.await_required_checks().ok is False
        assert agent.confirm_merge().ok is False
