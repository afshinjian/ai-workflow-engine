"""`CloseoutAgent` (`AGENT_CONTRACTS.md` §7, `MACHINE_GATES.md` §7, `FAILURE_RECOVERY.md` §4).

The stage contract's named test is here: **`CloseoutAgent` refuses branch deletion without an
independently confirmed merge.** It is asserted three ways — no deletion Skill is invoked, the
refusal happens before any Skill at all runs, and the branch still exists in a real repository
afterwards — because "returned a failure" alone would not prove nothing was deleted.

The happy path runs against a real temporary Git repository with a real `file://` remote, so
`checkout_baseline`, `fast_forward_pull`, and both deletion Skills are the shipping
implementations rather than fakes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.agents import (
    AgentFailureKind,
    AgentKind,
    CapabilityBroker,
    default_skill_registry,
)
from agentos_workflow.agents.closeout import CloseoutAgent
from agentos_workflow.skills import MergeConfirmation, SkillResult, success, utc_now
from agentos_workflow.tests.test_skills_repository import git, write

WORKFLOW_ID = "wf-closeout"
STAGE_ID = "AUTO-999"
STAGE_BRANCH = "feature/auto-999-example"
BASELINE = "main"

CLOSEOUT_SKILLS = (
    "checkout_baseline",
    "fast_forward_pull",
    "delete_local_branch",
    "delete_remote_branch",
    "verify_final_repository_state",
    "generate_closeout_report",
    "append_audit_event",
)
DESTRUCTIVE_SKILLS = ("delete_local_branch", "delete_remote_branch")


class Recorder:
    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.calls: list[str] = []
        self._results = results or {}

    def bindings(self) -> dict[str, Any]:
        def make(name: str) -> Any:
            def call(**_: Any) -> SkillResult[Any]:
                self.calls.append(name)
                produced = self._results.get(name, success(True))
                assert isinstance(produced, SkillResult)
                return produced

            return call

        return {name: make(name) for name in CLOSEOUT_SKILLS}

    @property
    def workflow_calls(self) -> list[str]:
        """Calls excluding `append_audit_event`, which records rather than acts.

        Auditing a refusal is *required* (`AUDIT_MODEL.md`), so counting it as "a Skill ran" would
        make the correct behaviour indistinguishable from touching the repository.
        """
        return [name for name in self.calls if name != "append_audit_event"]


@pytest.fixture
def merged_repo(tmp_path: Path) -> Path:
    """A repository whose stage branch has really been merged into `main`, with a real remote."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", BASELINE, str(origin)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-b", BASELINE)
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.invalid")
    write(work, "README.md", "baseline\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-u", "origin", BASELINE)

    git(work, "checkout", "-b", STAGE_BRANCH)
    write(work, "src/x.py", "value = 1\n")
    git(work, "add", "src/x.py")
    git(work, "commit", "-m", "feat: add x")
    git(work, "push", "-u", "origin", STAGE_BRANCH)
    git(work, "checkout", BASELINE)
    git(work, "merge", "--no-ff", STAGE_BRANCH, "-m", "merge stage branch")
    git(work, "push", "origin", BASELINE)
    git(work, "checkout", STAGE_BRANCH)
    return work


def confirmation(branch: str = STAGE_BRANCH, sha: str = "f" * 40) -> MergeConfirmation:
    return MergeConfirmation(branch=branch, merge_commit_sha=sha, verified_at=utc_now())


def agent_for(repository: Path, skills: dict[str, Any], audit_root: Path) -> CloseoutAgent:
    audit_root.mkdir(parents=True, exist_ok=True)
    return CloseoutAgent(
        CapabilityBroker(AgentKind.CLOSEOUT, skills=skills),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        baseline_branch=BASELINE,
        remote_name="origin",
        repository_path=repository,
        audit_root=audit_root,
    )


class TestDeletionRequiresAnIndependentlyConfirmedMerge:
    """The stage contract's named refusal test."""

    def test_a_confirmation_for_another_branch_deletes_nothing(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = agent_for(tmp_path, recorder.bindings(), tmp_path / "audit")

        result = agent.close_out(merge_confirmation=confirmation(branch="some/other-branch"))

        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.PRECONDITION
        for skill in DESTRUCTIVE_SKILLS:
            assert skill not in recorder.calls
        # Stronger than "no deletion": the refusal precedes *every* Skill, so nothing was touched.
        assert (
            recorder.workflow_calls == []
        ), f"Skills ran before refusal: {recorder.workflow_calls}"

    def test_a_confirmation_without_a_merge_commit_deletes_nothing(self, tmp_path: Path) -> None:
        recorder = Recorder()
        agent = agent_for(tmp_path, recorder.bindings(), tmp_path / "audit")

        result = agent.close_out(merge_confirmation=confirmation(sha="   "))

        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.PRECONDITION
        assert recorder.workflow_calls == []

    def test_the_branch_still_exists_after_a_refusal(self, merged_repo: Path) -> None:
        """Asserted against real Git, not against a recorder: the branch is still there."""
        registry = default_skill_registry()
        skills = {name: registry[name] for name in CLOSEOUT_SKILLS if name in registry}
        agent = agent_for(merged_repo, skills, merged_repo.parent / "audit")

        result = agent.close_out(merge_confirmation=confirmation(branch="wrong/branch"))

        assert result.ok is False
        branches = git(merged_repo, "branch", "--list", STAGE_BRANCH)
        assert STAGE_BRANCH in branches
        remote = git(merged_repo, "ls-remote", "--heads", "origin", f"refs/heads/{STAGE_BRANCH}")
        assert STAGE_BRANCH in remote

    def test_close_out_cannot_be_called_without_a_confirmation(self, tmp_path: Path) -> None:
        """`merge_confirmation` is keyword-only with no default: omitting it is a `TypeError`,
        not a closeout that deletes on trust."""
        recorder = Recorder()
        agent = agent_for(tmp_path, recorder.bindings(), tmp_path / "audit")
        with pytest.raises(TypeError):
            agent.close_out()  # type: ignore[call-arg]
        assert recorder.workflow_calls == []


class TestBaselineRestorationPrecedesDeletion:
    """`MACHINE_GATES.md` §7 ordering, and `FAILURE_RECOVERY.md` §4's partial-completion record."""

    def test_a_failed_checkout_stops_before_any_deletion(self, tmp_path: Path) -> None:
        recorder = Recorder({"checkout_baseline": SkillResult(ok=False, error=None)})
        agent = agent_for(tmp_path, recorder.bindings(), tmp_path / "audit")

        result = agent.close_out(merge_confirmation=confirmation())

        assert result.ok is False
        assert recorder.workflow_calls == ["checkout_baseline"]
        for skill in DESTRUCTIVE_SKILLS:
            assert skill not in recorder.calls

    def test_a_failed_fast_forward_stops_before_any_deletion(self, tmp_path: Path) -> None:
        """Deleting the branch and then failing to update the baseline would leave the local
        repository with neither the branch nor the merge."""
        recorder = Recorder({"fast_forward_pull": SkillResult(ok=False, error=None)})
        agent = agent_for(tmp_path, recorder.bindings(), tmp_path / "audit")

        result = agent.close_out(merge_confirmation=confirmation())

        assert result.ok is False
        assert recorder.workflow_calls == ["checkout_baseline", "fast_forward_pull"]
        for skill in DESTRUCTIVE_SKILLS:
            assert skill not in recorder.calls

    def test_a_failure_records_which_steps_already_completed(self, tmp_path: Path) -> None:
        """`FAILURE_RECOVERY.md` §4: a closeout failure states what was already done safely."""
        recorder = Recorder({"delete_remote_branch": SkillResult(ok=False, error=None)})
        agent = agent_for(tmp_path, recorder.bindings(), tmp_path / "audit")

        result = agent.close_out(merge_confirmation=confirmation())

        assert result.ok is False
        steps = {entry["step"]: entry["ok"] for entry in result.evidence["steps"]}
        assert steps["checkout_baseline"] is True
        assert steps["fast_forward_pull"] is True
        assert steps["delete_local_branch"] is True
        assert steps["delete_remote_branch"] is False
        assert "verify_final_repository_state" not in steps


class TestCloseoutAgainstRealGit:
    def test_full_closeout_restores_the_baseline_and_removes_the_branch(
        self, merged_repo: Path
    ) -> None:
        registry = default_skill_registry()
        skills = {name: registry[name] for name in CLOSEOUT_SKILLS if name in registry}
        audit_root = merged_repo.parent / "audit"
        agent = agent_for(merged_repo, skills, audit_root)

        result = agent.close_out(merge_confirmation=confirmation())

        assert result.ok is True, result.error
        assert git(merged_repo, "rev-parse", "--abbrev-ref", "HEAD") == BASELINE
        assert git(merged_repo, "branch", "--list", STAGE_BRANCH) == ""
        assert git(merged_repo, "ls-remote", "--heads", "origin", STAGE_BRANCH) == ""
        assert git(merged_repo, "status", "--porcelain") == ""
        assert Path(result.evidence["closeout_report_path"]).is_file()
        assert result.evidence["merge_commit_sha"] == "f" * 40
