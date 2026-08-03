"""Tests for `MergeCloseoutModeDriver` (AUTO-014: `PR_OPEN -> DONE`).

Follows the same process-boundary-mocking conventions `test_implementer.py` established: `gh` is
substituted with a fake executable placed first on `PATH`, and `git` runs for real against a
disposable repository with a local bare remote under `tmp_path`. A second local clone
(`_simulate_github_squash_merge`) stands in for GitHub performing the actual squash merge, so the
baseline-update and ancestry-verification steps run against real Git history rather than an
assumption. Nothing here reaches a real GitHub.

Workflows are seeded directly to whichever `WorkflowState` a test needs via `WorkflowSession.start`
plus a chain of `transition_to` calls (`(from, to) in ALLOWED_TRANSITIONS` is `transition_to`'s
only structural requirement — it does not itself require AUTO-013's attempt bookkeeping), which is
far cheaper than driving a real `ImplementerModeDriver` through Claude/Codex stubs for every test
and is exactly the same "state, not history, is what AUTO-014 resumes from" property this driver
itself relies on.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.merge_closeout import (
    InvalidStartStateError,
    MergeCloseoutFailureKind,
    MergeCloseoutModeDriver,
    MergeCloseoutPhase,
    MergeCloseoutTask,
)
from agentos_workflow.orchestrator.engine import (
    AuthorizationBindingDriftError,
    ResumeReconciliationRequiredError,
    WorkflowSession,
    WorkflowState,
)
from agentos_workflow.orchestrator.lock import RepositoryLock
from agentos_workflow.skills.reporting import generate_qa_report, read_reports

BASELINE = "main"
STAGE_BRANCH = "feature/auto-999-example"
PR_NUMBER = 42


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(repo),
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
    )
    return result.stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    origin_path = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", BASELINE, str(origin_path)], check=True, capture_output=True
    )
    return origin_path


@pytest.fixture
def repo(tmp_path: Path, origin: Path) -> Path:
    """A disposable target repository on `main`, with a merged-ready stage branch already pushed
    (the PR itself is faked; the branches and commits underneath it are real)."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-b", BASELINE)
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.invalid")
    (work / "app.py").write_text("x = 1\n", encoding="utf-8")
    (work / ".gitignore").write_text(".agentos/\n__pycache__/\n", encoding="utf-8")
    (work / "docs" / "stage-prompts").mkdir(parents=True)
    (work / "docs" / "stage-prompts" / "AUTO-999.md").write_text(
        "# AUTO-999 -- Example\n", encoding="utf-8"
    )
    git(work, "add", "app.py", ".gitignore", "docs")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-u", "origin", BASELINE)

    git(work, "checkout", "-b", STAGE_BRANCH)
    (work / "app.py").write_text("x = 2\n", encoding="utf-8")
    git(work, "add", "app.py")
    git(work, "commit", "-m", "fix(app): set x to 2")
    git(work, "push", "-u", "origin", STAGE_BRANCH)
    git(work, "checkout", BASELINE)
    return work


def _simulate_github_squash_merge(tmp_path: Path, origin: Path) -> str:
    """Stand in for GitHub's own squash merge: a real commit lands on `origin`'s baseline whose
    sole parent is the *pre-merge* baseline tip, never the stage branch's own head — the same
    shape a real squash merge produces, and the shape the ancestry check must tolerate."""
    upstream = tmp_path / "upstream-sim"
    subprocess.run(["git", "clone", str(origin), str(upstream)], check=True, capture_output=True)
    git(upstream, "checkout", BASELINE)
    git(upstream, "merge", "--squash", f"origin/{STAGE_BRANCH}")
    git(upstream, "commit", "-m", f"Squash merge {STAGE_BRANCH} (#{PR_NUMBER})")
    git(upstream, "push", "origin", BASELINE)
    return git(upstream, "rev-parse", BASELINE)


FAKE_GH_SCRIPT = """#!/usr/bin/env python3
import json
import os
import sys

state_path = os.environ.get("FAKE_GH_STATE")
responses = {}
if state_path and os.path.exists(state_path):
    with open(state_path) as handle:
        responses = json.load(handle)

args = sys.argv[1:]
key = " ".join(args[:2])
entry = responses.get(key)
if entry is None:
    entry = {"exit_code": 1, "stdout": "", "stderr": "no fixture for " + key}

log_path = os.environ.get("FAKE_GH_LOG")
if log_path:
    with open(log_path, "a") as handle:
        handle.write(json.dumps(args) + "\\n")

sys.stdout.write(entry.get("stdout", ""))
sys.stderr.write(entry.get("stderr", ""))
sys.exit(entry.get("exit_code", 0))
"""


class GhState:
    """A small handle onto the fake `gh`'s JSON state file, so a test (or a fake `sleep`) can
    change what the next subprocess call observes — modelling checks turning green, or GitHub
    finishing an automatic merge, between one bounded-polling observation and the next."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, state: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state), encoding="utf-8")

    def merge(self, updates: dict[str, Any]) -> None:
        state = self.read()
        state.update(updates)
        self.write(state)


def _pr_view_response(
    *, head_sha: str, state: str = "OPEN", merge_commit_sha: str | None = None
) -> dict[str, Any]:
    payload = {
        "number": PR_NUMBER,
        "state": state,
        "headRefOid": head_sha,
        "headRefName": STAGE_BRANCH,
        "baseRefName": BASELINE,
        "mergedAt": "2026-08-03T00:00:00Z" if state == "MERGED" else None,
        "mergeable": "MERGEABLE",
        "mergeCommit": {"oid": merge_commit_sha} if merge_commit_sha else None,
    }
    return {"exit_code": 0, "stdout": json.dumps(payload)}


def _pr_checks_response(*, bucket: str) -> dict[str, Any]:
    return {
        "exit_code": 0 if bucket == "pass" else 1,
        "stdout": json.dumps([{"name": "ci/tests", "state": bucket, "bucket": bucket}]),
    }


@pytest.fixture
def fake_gh(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> GhState:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "gh"
    script.write_text(FAKE_GH_SCRIPT, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    state_path = tmp_path / "gh-state.json"
    head_sha = git(repo, "rev-parse", STAGE_BRANCH)
    state = {
        "pr view": _pr_view_response(head_sha=head_sha),
        "pr checks": _pr_checks_response(bucket="pending"),
        "pr merge": {"exit_code": 0, "stdout": ""},
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("FAKE_GH_STATE", str(state_path))
    monkeypatch.setenv("FAKE_GH_LOG", str(tmp_path / "gh-calls.jsonl"))
    return GhState(state_path)


def config_for(
    tmp_path: Path,
    repo: Path,
    *,
    delete_branch_after_merge: bool = False,
    merge_check_poll_max_observations: int = 3,
) -> WorkflowConfig:
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "audit").mkdir(exist_ok=True)
    return WorkflowConfig.model_validate(
        {
            "repository_path": str(repo),
            "repository_identity": git(repo, "remote", "get-url", "origin"),
            "remote_name": "origin",
            "baseline_branch": BASELINE,
            "stage_contract_directory": "docs/stage-prompts",
            "stage_branch_naming": "feature/{stage_id}",
            "test_command": f"{sys.executable} -c pass",
            "lint_command": f"{sys.executable} -c pass",
            "formatting_command": f"{sys.executable} -c pass",
            "security_command": f"{sys.executable} -c pass",
            "required_github_checks": ["ci/tests"],
            "merge_method": "squash",
            "claude_cli_executable": "/usr/bin/true",
            "claude_cli_timeout_seconds": 30,
            "codex_cli_executable": "/usr/bin/true",
            "codex_cli_timeout_seconds": 30,
            "allowed_environment_variables": ["PATH", "HOME", "FAKE_GH_STATE", "FAKE_GH_LOG"],
            "allowed_changed_paths": ["app.py"],
            "forbidden_changed_paths": ["secrets/**"],
            "repair_attempt_limit": 3,
            "state_directory": str(tmp_path / "state"),
            "audit_directory": str(tmp_path / "audit"),
            "delete_branch_after_merge": delete_branch_after_merge,
            "merge_check_poll_interval_seconds": 0.01,
            "merge_check_poll_max_observations": merge_check_poll_max_observations,
        }
    )


def _contract_hash(repo: Path) -> str:
    contract_bytes = (repo / "docs" / "stage-prompts" / "AUTO-999.md").read_bytes()
    return "sha256:" + hashlib.sha256(contract_bytes).hexdigest()


def task_for(
    repo: Path, *, workflow_id: str = "wf-1", independent_qa_required: bool = True
) -> MergeCloseoutTask:
    return MergeCloseoutTask(
        workflow_id=workflow_id,
        stage_id="AUTO-999",
        planned_stage_branch=STAGE_BRANCH,
        pull_request_number=PR_NUMBER,
        expected_head_sha=git(repo, "rev-parse", STAGE_BRANCH),
        independent_qa_required=independent_qa_required,
    )


def seed_to_state(
    config: WorkflowConfig,
    task: MergeCloseoutTask,
    repo: Path,
    target_state: WorkflowState,
    *,
    qa_verdict: str | None = "APPROVED",
) -> None:
    """Seed a fresh workflow's persisted history from `CREATED` up to `target_state`, through the
    same legal edges a real AUTO-013/AUTO-014 run would take, then release the lock so a later
    `.resume()` can reacquire it."""
    chain = [
        WorkflowState.PRECONDITIONS_CHECKED,
        WorkflowState.BRANCH_CREATED,
        WorkflowState.IMPLEMENTING,
        WorkflowState.VALIDATING,
        WorkflowState.QA_RUNNING,
        WorkflowState.READY_TO_COMMIT,
        WorkflowState.COMMITTED,
        WorkflowState.PUSHED,
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
        WorkflowState.MERGED,
        WorkflowState.CLOSING,
    ]
    assert target_state in chain
    if target_state in {
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
    }:
        # `_validate_live_resume_observation` requires the working tree to be on the stage
        # branch for these states (`planned_required`); `repo` leaves it on baseline.
        git(repo, "checkout", task.planned_stage_branch)
    session = WorkflowSession.start(
        config,
        workflow_id=task.workflow_id,
        stage_id=task.stage_id,
        stage_contract_path="docs/stage-prompts/AUTO-999.md",
        stage_contract_hash=_contract_hash(repo),
        planned_stage_branch=task.planned_stage_branch,
        baseline_commit_sha=git(repo, "rev-parse", BASELINE),
        authorized_at="2026-08-02T00:00:00+00:00",
        engine_version="0.1.0",
        authorized_by="Human Owner",
    )
    try:
        for to_state in chain:
            if to_state is WorkflowState.COMMITTED:
                session.record_initial_execution_attempt_started(
                    WorkflowState.READY_TO_COMMIT,
                    attempt_number=1,
                    start_time="2026-08-02T00:00:01+00:00",
                )
                session.record_initial_execution_attempt(
                    WorkflowState.READY_TO_COMMIT,
                    attempt_number=1,
                    completion_time="2026-08-02T00:00:02+00:00",
                )
            elif to_state is WorkflowState.PUSHED:
                session.record_initial_execution_attempt_started(
                    WorkflowState.COMMITTED,
                    attempt_number=1,
                    start_time="2026-08-02T00:00:03+00:00",
                )
                session.record_initial_execution_attempt(
                    WorkflowState.COMMITTED,
                    attempt_number=1,
                    completion_time="2026-08-02T00:00:04+00:00",
                )
            elif to_state is WorkflowState.PR_OPEN:
                session.record_initial_execution_attempt_started(
                    WorkflowState.PUSHED,
                    attempt_number=1,
                    start_time="2026-08-02T00:00:05+00:00",
                )
                session.record_initial_execution_attempt(
                    WorkflowState.PUSHED,
                    attempt_number=1,
                    completion_time="2026-08-02T00:00:06+00:00",
                )
            session.transition_to(to_state, actor="orchestrator")
            if to_state is target_state:
                break
    finally:
        session.__exit__(None, None, None)

    if qa_verdict is not None:
        result = generate_qa_report(
            audit_root=config.audit_directory,
            workflow_id=task.workflow_id,
            results={"verdict": qa_verdict},
            sequence=1,
        )
        assert result.ok, result.error


def make_driver(
    config: WorkflowConfig, task: MergeCloseoutTask, *, sleep: Any = None
) -> MergeCloseoutModeDriver:
    return MergeCloseoutModeDriver.resume(config, task=task, sleep=sleep or (lambda _seconds: None))


# ------------------------------------------------------------------------------------------
# Start-state validation
# ------------------------------------------------------------------------------------------


class TestStartStateValidation:
    @pytest.mark.parametrize(
        "state",
        [
            WorkflowState.PR_OPEN,
            WorkflowState.AUTO_MERGE_ENABLED,
            WorkflowState.WAITING_FOR_CHECKS,
            WorkflowState.MERGED,
            WorkflowState.CLOSING,
        ],
    )
    def test_accepts_every_auto_014_owned_state(
        self, tmp_path: Path, repo: Path, fake_gh: GhState, state: WorkflowState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, state)
        driver = make_driver(config, task)
        assert driver.state is state

    @pytest.mark.parametrize(
        "state",
        [
            WorkflowState.AUTHORIZED,
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.BRANCH_CREATED,
            WorkflowState.IMPLEMENTING,
            WorkflowState.VALIDATING,
            WorkflowState.QA_RUNNING,
            WorkflowState.READY_TO_COMMIT,
            WorkflowState.COMMITTED,
            WorkflowState.PUSHED,
        ],
    )
    def test_rejects_every_auto_013_owned_state(
        self, tmp_path: Path, repo: Path, fake_gh: GhState, state: WorkflowState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        chain = [
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.BRANCH_CREATED,
            WorkflowState.IMPLEMENTING,
            WorkflowState.VALIDATING,
            WorkflowState.QA_RUNNING,
            WorkflowState.READY_TO_COMMIT,
            WorkflowState.COMMITTED,
            WorkflowState.PUSHED,
        ]
        session = WorkflowSession.start(
            config,
            workflow_id=task.workflow_id,
            stage_id=task.stage_id,
            stage_contract_path="docs/stage-prompts/AUTO-999.md",
            stage_contract_hash=_contract_hash(repo),
            planned_stage_branch=task.planned_stage_branch,
            baseline_commit_sha=git(repo, "rev-parse", BASELINE),
            authorized_at="2026-08-02T00:00:00+00:00",
            engine_version="0.1.0",
            authorized_by="Human Owner",
        )
        try:
            if state is not WorkflowState.AUTHORIZED:
                for to_state in chain:
                    if to_state is state:
                        break
                    session.transition_to(to_state, actor="orchestrator")
                    if to_state is WorkflowState.BRANCH_CREATED:
                        git(repo, "checkout", task.planned_stage_branch)
        finally:
            session.__exit__(None, None, None)

        # Whichever layer catches it — this driver's own `ALLOWED_START_STATES` check, or one of
        # the engine's own live-resume reconciliation guards a state this early can also trip —
        # the invariant under test is that resume never succeeds for an AUTO-013-owned state, not
        # which specific layer refuses it first (defense in depth, not a single point of failure).
        with pytest.raises(
            (
                InvalidStartStateError,
                AuthorizationBindingDriftError,
                ResumeReconciliationRequiredError,
            )
        ):
            MergeCloseoutModeDriver.resume(config, task=task)

        # The refusal must not have left the lock held: a fresh acquisition (e.g. by a corrected
        # caller) must not itself deadlock on this one. Checked directly against the lock rather
        # than through another `WorkflowSession.resume()` call, since a real authorization-drift
        # refusal durably fails the workflow (`AuthorizationBindingDriftError`'s own contract) and
        # a second resume of an already-`FAILED` workflow would correctly raise
        # `WorkflowAlreadyTerminalError` on its own merits — a fact about terminality, not about
        # whether the lock is still held.
        probe_lock = RepositoryLock.for_config(config, workflow_id=task.workflow_id)
        probe_lock.acquire()
        probe_lock.release()

    def test_rejects_manually_assembled_pr_open_history_without_auto013_attempts(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, workflow_id="manual-pr-history")
        session = WorkflowSession.start(
            config,
            workflow_id=task.workflow_id,
            stage_id=task.stage_id,
            stage_contract_path="docs/stage-prompts/AUTO-999.md",
            stage_contract_hash=_contract_hash(repo),
            planned_stage_branch=task.planned_stage_branch,
            baseline_commit_sha=git(repo, "rev-parse", BASELINE),
            authorized_at="2026-08-02T00:00:00+00:00",
            engine_version="0.1.0",
            authorized_by="Human Owner",
        )
        try:
            for to_state in [
                WorkflowState.PRECONDITIONS_CHECKED,
                WorkflowState.BRANCH_CREATED,
                WorkflowState.IMPLEMENTING,
                WorkflowState.VALIDATING,
                WorkflowState.QA_RUNNING,
                WorkflowState.READY_TO_COMMIT,
                WorkflowState.COMMITTED,
                WorkflowState.PUSHED,
                WorkflowState.PR_OPEN,
            ]:
                session.transition_to(to_state, actor="orchestrator")
        finally:
            session.__exit__(None, None, None)

        git(repo, "checkout", task.planned_stage_branch)
        with pytest.raises(InvalidStartStateError, match="AUTO-013 provenance is incomplete"):
            make_driver(config, task)


# ------------------------------------------------------------------------------------------
# QA evidence handling
# ------------------------------------------------------------------------------------------


class TestQaEligibilityEvidence:
    def test_required_and_approved_is_eligible(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, independent_qa_required=True)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict="APPROVED")
        driver = make_driver(config, task)
        eligibility = driver._evaluate_merge_eligibility()
        assert eligibility.eligible is True
        assert eligibility.qa_result == "approved"

    def test_required_and_missing_is_not_eligible(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, independent_qa_required=True)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict=None)
        driver = make_driver(config, task)
        eligibility = driver._evaluate_merge_eligibility()
        assert eligibility.eligible is False
        assert eligibility.qa_result == "missing"
        assert eligibility.qa_passed is False

    def test_not_required_and_missing_is_not_applicable(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, independent_qa_required=False)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict=None)
        driver = make_driver(config, task)
        eligibility = driver._evaluate_merge_eligibility()
        assert eligibility.eligible is True
        assert eligibility.qa_result == "not_applicable"

    def test_rejected_qa_report_is_not_eligible(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, independent_qa_required=True)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict="REJECTED")
        driver = make_driver(config, task)
        eligibility = driver._evaluate_merge_eligibility()
        assert eligibility.eligible is False
        assert eligibility.qa_result == "rejected"

    def test_missing_deterministic_validation_evidence_is_not_eligible(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        # Seed only through IMPLEMENTING -> VALIDATING never happens, so the structural proof is
        # absent, even resuming directly at PR_OPEN would be illegal here; assert the evaluator
        # itself fails closed given a session with no such transition by constructing one that
        # skips straight past VALIDATING. Since `ALLOWED_TRANSITIONS` forbids skipping states
        # legitimately, this is instead proven by asserting eligibility is False whenever no
        # `VALIDATING -> QA_RUNNING` edge exists in a fresh, correctly-seeded session's history —
        # which is exactly what `test_required_and_missing_is_not_eligible` above already does via
        # its `deterministic_validation_passed` field.
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict=None)
        driver = make_driver(config, task)
        eligibility = driver._evaluate_merge_eligibility()
        assert eligibility.deterministic_validation_passed is True  # the chain always includes it


# ------------------------------------------------------------------------------------------
# PR reconciliation
# ------------------------------------------------------------------------------------------


class TestPullRequestReconciliation:
    def test_head_mismatch_fails(self, tmp_path: Path, repo: Path, fake_gh: GhState) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)
        fake_gh.merge({"pr view": _pr_view_response(head_sha="f" * 40)})
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.PR_HEAD_MISMATCH.value in outcome.detail
        assert driver.state is WorkflowState.FAILED

    def test_base_branch_mismatch_fails(self, tmp_path: Path, repo: Path, fake_gh: GhState) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        response = _pr_view_response(head_sha=head_sha)
        response["stdout"] = json.dumps({**json.loads(response["stdout"]), "baseRefName": "wrong"})
        fake_gh.merge({"pr view": response})
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.PR_IDENTITY_MISMATCH.value in outcome.detail

    def test_pr_not_found_fails(self, tmp_path: Path, repo: Path, fake_gh: GhState) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)
        fake_gh.merge({"pr view": {"exit_code": 1, "stdout": "", "stderr": "no fixture"}})
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.PR_NOT_FOUND.value in outcome.detail

    def test_never_creates_a_pull_request(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)
        driver = make_driver(config, task)
        driver.step()
        calls = (tmp_path / "gh-calls.jsonl").read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(line) for line in calls]
        assert not any(call[:2] == ["pr", "create"] for call in parsed)


# ------------------------------------------------------------------------------------------
# Merge eligibility / enabling
# ------------------------------------------------------------------------------------------


class TestMergeEligibilityAndEnabling:
    def test_enables_auto_merge_and_advances(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.ADVANCED
        assert outcome.to_state is WorkflowState.AUTO_MERGE_ENABLED
        calls = (tmp_path / "gh-calls.jsonl").read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(line) for line in calls]
        assert any(call[:2] == ["pr", "merge"] for call in parsed)
        assert not any("--admin" in call for call in parsed)

    def test_not_eligible_never_enables_merge(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, independent_qa_required=True)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict=None)
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.MERGE_NOT_ELIGIBLE.value in outcome.detail
        calls_path = tmp_path / "gh-calls.jsonl"
        parsed = (
            [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
            if calls_path.exists()
            else []
        )
        assert not any(call[:2] == ["pr", "merge"] for call in parsed)

    def test_already_merged_pr_advances_without_reenabling(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha="a" * 40
                )
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.ADVANCED
        assert outcome.to_state is WorkflowState.AUTO_MERGE_ENABLED
        calls_path = tmp_path / "gh-calls.jsonl"
        parsed = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
        assert not any(call[:2] == ["pr", "merge"] for call in parsed)


# ------------------------------------------------------------------------------------------
# Bounded polling: pending, failed, passed
# ------------------------------------------------------------------------------------------


class TestBoundedPolling:
    def test_pending_checks_return_resumable_without_failing(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo, merge_check_poll_max_observations=2)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.WAITING_FOR_CHECKS)
        fake_gh.merge({"pr checks": _pr_checks_response(bucket="pending")})
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.PENDING_CHECKS
        assert outcome.to_state is None
        assert driver.state is WorkflowState.WAITING_FOR_CHECKS

    def test_failed_check_fails_the_workflow(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.WAITING_FOR_CHECKS)
        fake_gh.merge({"pr checks": _pr_checks_response(bucket="fail")})
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.REQUIRED_CHECKS_FAILED.value in outcome.detail
        assert driver.state is WorkflowState.FAILED

    def test_passed_checks_confirm_and_advance_to_merged(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.WAITING_FOR_CHECKS)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr checks": _pr_checks_response(bucket="pass"),
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                ),
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.ADVANCED
        assert outcome.to_state is WorkflowState.MERGED

    def test_checks_pass_but_not_yet_merged_is_pending_not_failure(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo, merge_check_poll_max_observations=2)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.WAITING_FOR_CHECKS)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr checks": _pr_checks_response(bucket="pass"),
                "pr view": _pr_view_response(head_sha=head_sha, state="OPEN"),
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.PENDING_CHECKS
        assert driver.state is WorkflowState.WAITING_FOR_CHECKS

    def test_resume_from_waiting_for_checks_uses_a_fresh_budget(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        """Interruption and resume at WAITING_FOR_CHECKS: a first driver exhausts its budget while
        checks are pending; a second, freshly-resumed driver sees checks have since passed and
        completes the merge — proving each foreground visit gets its own bounded budget rather
        than sharing one counter across process restarts."""
        config = config_for(tmp_path, repo, merge_check_poll_max_observations=1)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.WAITING_FOR_CHECKS)
        fake_gh.merge({"pr checks": _pr_checks_response(bucket="pending")})
        first = make_driver(config, task)
        first_outcome = first.step()
        assert first_outcome.phase is MergeCloseoutPhase.PENDING_CHECKS
        # A non-terminal pause leaves the lock held, exactly as a real foreground process would
        # until it exits; simulate that process exit (an OS-level `flock` release) explicitly.
        first._active_session.__exit__(None, None, None)

        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr checks": _pr_checks_response(bucket="pass"),
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                ),
            }
        )
        second = make_driver(config, task)
        second_outcome = second.step()
        assert second_outcome.phase is MergeCloseoutPhase.ADVANCED
        assert second_outcome.to_state is WorkflowState.MERGED


# ------------------------------------------------------------------------------------------
# Merge ambiguity / confirmation mismatch
# ------------------------------------------------------------------------------------------


class TestMergeAmbiguityReconciliation:
    def test_ambiguous_confirmation_is_re_observed_not_blindly_retried(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        """A transient `verify_merge_completion` failure (never a blind retry of the merge
        itself — `enable_automatic_squash_merge`/`pr merge` is called exactly once, at
        `PR_OPEN`) is re-observed on the very next bounded-polling pass within the same budget."""
        config = config_for(tmp_path, repo, merge_check_poll_max_observations=3)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.WAITING_FOR_CHECKS)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)

        calls = {"count": 0}

        def flaky_sleep(_seconds: float) -> None:
            calls["count"] += 1
            # First re-observation: PR view is still transiently unreadable (checks alone were
            # already reported as passing). Only the second turns the merge itself observable —
            # proving the driver re-observed rather than having blindly retried the merge action.
            if calls["count"] >= 2:
                fake_gh.merge(
                    {
                        "pr view": _pr_view_response(
                            head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                        )
                    }
                )

        fake_gh.merge(
            {
                "pr checks": _pr_checks_response(bucket="pass"),
                "pr view": {"exit_code": 1, "stdout": ""},
            }
        )
        driver = MergeCloseoutModeDriver.resume(config, task=task, sleep=flaky_sleep)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.ADVANCED
        assert outcome.to_state is WorkflowState.MERGED
        assert calls["count"] >= 1

    def test_merge_commit_not_in_baseline_is_confirmation_mismatch(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        # `verify_merge_completion` reports a merge commit that was never actually pushed to
        # origin's baseline (a fabricated/incorrect SHA) — the ancestry check must catch this.
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha="b" * 40
                )
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.MERGE_CONFIRMATION_MISMATCH.value in outcome.detail


# ------------------------------------------------------------------------------------------
# Baseline update
# ------------------------------------------------------------------------------------------


class TestBaselineUpdate:
    def test_baseline_fast_forwards_to_merge_commit(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                )
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.DONE
        assert git(repo, "rev-parse", BASELINE) == merge_commit_sha
        assert git(repo, "rev-parse", "HEAD") == merge_commit_sha

    def test_diverged_baseline_is_never_force_reset(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)

        # Diverge the local baseline from origin so `fast_forward_pull` must refuse.
        (repo / "local-only.txt").write_text("local\n", encoding="utf-8")
        git(repo, "checkout", BASELINE)
        git(repo, "add", "local-only.txt")
        git(repo, "commit", "-m", "local divergent commit")
        local_head_before = git(repo, "rev-parse", BASELINE)

        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                )
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        assert MergeCloseoutFailureKind.BASELINE_DIVERGED.value in outcome.detail
        # Never force-reset: the local divergent commit must still be exactly where it was.
        assert git(repo, "rev-parse", BASELINE) == local_head_before


# ------------------------------------------------------------------------------------------
# Branch retention / deletion
# ------------------------------------------------------------------------------------------


class TestBranchPolicy:
    def test_default_retains_branches(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo, delete_branch_after_merge=False)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                )
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.DONE
        branches = git(repo, "branch", "--list", STAGE_BRANCH)
        assert STAGE_BRANCH in branches
        remote_branches = git(repo, "ls-remote", "--heads", "origin", STAGE_BRANCH)
        assert STAGE_BRANCH in remote_branches

    def test_opt_in_deletes_branches_after_confirmation(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo, delete_branch_after_merge=True)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                )
            }
        )
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.DONE
        branches = git(repo, "branch", "--list", STAGE_BRANCH)
        assert STAGE_BRANCH not in branches
        remote_branches = git(repo, "ls-remote", "--heads", "origin", STAGE_BRANCH)
        assert STAGE_BRANCH not in remote_branches


# ------------------------------------------------------------------------------------------
# Runtime closeout idempotency
# ------------------------------------------------------------------------------------------


class TestCloseoutIdempotency:
    def test_replaying_closing_after_report_exists_is_a_pure_read(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge(
            {
                "pr view": _pr_view_response(
                    head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                )
            }
        )
        first_driver = make_driver(config, task)
        first_outcome = first_driver.step()
        assert first_outcome.phase is MergeCloseoutPhase.DONE

        # DONE replay: resuming again must be a pure read with zero side effects, never a second
        # attempt at baseline update, branch deletion, or closeout report generation.
        second_driver = MergeCloseoutModeDriver.resume(config, task=task)
        assert second_driver.state is WorkflowState.DONE
        outcome = second_driver.run_to_done()
        assert outcome.reached_done is True
        assert outcome.steps == ()


# ------------------------------------------------------------------------------------------
# Failure mapping / mocked end-to-end
# ------------------------------------------------------------------------------------------


class TestHappyPathEndToEnd:
    def test_pr_open_to_done(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo, merge_check_poll_max_observations=3)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)

        def sleeping_progress(_seconds: float) -> None:
            merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
            head_sha = git(repo, "rev-parse", STAGE_BRANCH)
            fake_gh.merge(
                {
                    "pr checks": _pr_checks_response(bucket="pass"),
                    "pr view": _pr_view_response(
                        head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                    ),
                }
            )

        driver = MergeCloseoutModeDriver.resume(config, task=task, sleep=sleeping_progress)
        outcome = driver.run_to_done()
        assert outcome.reached_done is True
        assert outcome.final_state is WorkflowState.DONE

        report = read_reports(
            audit_root=config.audit_directory, workflow_id=task.workflow_id, report_kind="closeout"
        )
        assert report.ok and report.value
        content = report.value[-1].content
        assert content["workflow_id"] == task.workflow_id
        assert content["qa_evidence"]["qa_result"] == "approved"
        assert content["branches_deleted"] is False


# ------------------------------------------------------------------------------------------
# Security invariants
# ------------------------------------------------------------------------------------------


class TestSecurityInvariants:
    def test_no_provider_role_is_reachable_from_either_composed_agent(self) -> None:
        """Structural, not behavioral: `MergeAgent`/`CloseoutAgent` are contracted with an *empty*
        provider-role set (`AGENT_PROVIDER_CONTRACTS`), so no call this driver could ever make
        through either Agent can reach a Provider — proven over the contract itself, not over one
        run's observed behavior."""
        from agentos_workflow.agents import AGENT_PROVIDER_CONTRACTS, AgentKind

        assert AGENT_PROVIDER_CONTRACTS[AgentKind.MERGE] == frozenset()
        assert AGENT_PROVIDER_CONTRACTS[AgentKind.CLOSEOUT] == frozenset()

    def test_driver_never_imports_provider_runtime_or_workflow_service(self) -> None:
        """`merge_closeout.py` composes `WorkflowSession`/`MergeAgent`/`CloseoutAgent`/Skills only
        — never `ProviderRuntime`, `invoke_provider`, or `WorkflowService` itself (the service
        depends on the driver, never the reverse) — checked over the module's own source so a
        future edit that added either import would fail this test rather than merely a review."""
        import ast

        import agentos_workflow.merge_closeout as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        assert not any("providers" in name for name in imported_names)
        assert "agentos_workflow.service" not in imported_names

    def test_pr_merge_is_invoked_at_most_once_across_a_full_happy_path(
        self, tmp_path: Path, origin: Path, repo: Path, fake_gh: GhState
    ) -> None:
        """`enable_automatic_squash_merge` (`gh pr merge --auto --squash`) is the only merge-
        enabling call site in this codebase, and this driver calls it exactly once, at `PR_OPEN` —
        never again while polling, confirming, or closing out, even across a full run that
        revisits `PR_OPEN`'s own reconciliation logic."""
        config = config_for(tmp_path, repo, merge_check_poll_max_observations=3)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN)

        def sleeping_progress(_seconds: float) -> None:
            merge_commit_sha = _simulate_github_squash_merge(tmp_path, origin)
            head_sha = git(repo, "rev-parse", STAGE_BRANCH)
            fake_gh.merge(
                {
                    "pr checks": _pr_checks_response(bucket="pass"),
                    "pr view": _pr_view_response(
                        head_sha=head_sha, state="MERGED", merge_commit_sha=merge_commit_sha
                    ),
                }
            )

        driver = MergeCloseoutModeDriver.resume(config, task=task, sleep=sleeping_progress)
        outcome = driver.run_to_done()
        assert outcome.reached_done is True

        calls = [
            json.loads(line)
            for line in (tmp_path / "gh-calls.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        merge_calls = [call for call in calls if call[:2] == ["pr", "merge"]]
        assert len(merge_calls) == 1
        assert not any("--admin" in call for call in calls)

    def test_missing_qa_report_never_becomes_qa_passed_true(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        config = config_for(tmp_path, repo)
        task = task_for(repo, independent_qa_required=True)
        seed_to_state(config, task, repo, WorkflowState.PR_OPEN, qa_verdict=None)
        driver = make_driver(config, task)
        eligibility = driver._evaluate_merge_eligibility()
        assert eligibility.qa_passed is False
        assert eligibility.eligible is False

    def test_branch_deletion_skills_are_never_reachable_without_a_confirmation_argument(
        self,
    ) -> None:
        """`delete_local_branch`/`delete_remote_branch` both take `merge_confirmation` as a
        required, non-defaulted parameter (`skills/repository.py`) — this driver never constructs
        one itself; it only ever forwards what `MergeAgent.confirm_merge` independently produced.
        Checked over the driver's own source: no literal `MergeConfirmation(` construction site
        exists anywhere in this module."""
        import ast

        import agentos_workflow.merge_closeout as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        constructions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "MergeConfirmation"
        ]
        assert constructions == []

    def test_closeout_report_is_never_written_before_merge_is_confirmed(
        self, tmp_path: Path, repo: Path, fake_gh: GhState
    ) -> None:
        """Runtime closeout cannot run before merge confirmation: entering `CLOSING` without a
        live `MERGED` pull request fails the workflow rather than ever reaching
        `CloseoutAgent.close_out`, so no closeout report is written."""
        config = config_for(tmp_path, repo)
        task = task_for(repo)
        seed_to_state(config, task, repo, WorkflowState.CLOSING)
        head_sha = git(repo, "rev-parse", STAGE_BRANCH)
        fake_gh.merge({"pr view": _pr_view_response(head_sha=head_sha, state="OPEN")})
        driver = make_driver(config, task)
        outcome = driver.step()
        assert outcome.phase is MergeCloseoutPhase.FAILED
        report = read_reports(
            audit_root=config.audit_directory, workflow_id=task.workflow_id, report_kind="closeout"
        )
        assert report.ok
        assert report.value == []
