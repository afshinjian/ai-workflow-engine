"""Tests for `ImplementerModeDriver` (AUTO-013: `AUTHORIZED -> PR_OPEN`).

Follows the process-boundary-mocking conventions already established in this suite:
`claude`/`codex` are substituted with small stub scripts speaking each CLI's real transport
(`test_provider_runtime.py`), and `gh` is substituted with a fake executable placed first on
`PATH` (`test_skills_git_github.py`). `git` runs for real against a disposable repository with a
local bare remote under `tmp_path`. Nothing here reaches a real Claude, Codex, or GitHub.
"""

from __future__ import annotations

import ast
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.approvals import (
    ApprovalChannel,
    ApprovalDecision,
    ApprovalPolicyOverlay,
    ApprovalService,
    TimeoutAction,
)
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.implementer import (
    ApprovalPolicyOverlays,
    ImplementationTask,
    ImplementerModeDriver,
    ImplementerModeError,
    ImplementerPhase,
    ImplementerPolicyError,
    ImplementerPolicyOverlay,
    ImplementerPolicyOverlays,
    resolve_implementer_policy,
)
from agentos_workflow.orchestrator.engine import WorkflowState
from agentos_workflow.orchestrator.state_store import StateStore

BASELINE = "main"
STAGE_BRANCH = "feature/auto-999-example"


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
def repo(tmp_path: Path) -> Path:
    """A disposable target repository on `main`, with a local bare `origin` remote."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", BASELINE, str(origin)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-b", BASELINE)
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.invalid")
    (work / "app.py").write_text("x = 1\n", encoding="utf-8")
    (work / "test_app.py").write_text(
        "from app import x\n\n\ndef test_x() -> None:\n    assert x == 2\n", encoding="utf-8"
    )
    (work / "docs" / "stage-prompts").mkdir(parents=True)
    (work / "docs" / "stage-prompts" / "AUTO-999.md").write_text(
        "# AUTO-999 -- Example\n", encoding="utf-8"
    )
    # The engine's own `RepositoryLock` creates `.agentos/workflow.lock` inside the target
    # repository the moment a `WorkflowSession` is started or resumed, before any application work
    # happens — every real target repository configured for this engine gitignores it for exactly
    # this reason (`orchestrator/lock.py`).
    (work / ".gitignore").write_text(
        ".agentos/\n__pycache__/\n*.pyc\n.pytest_cache/\n", encoding="utf-8"
    )
    git(work, "add", "app.py", "test_app.py", ".gitignore", "docs")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-u", "origin", BASELINE)
    return work


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
    entry = responses.get(
        args[0] if args else "", {"exit_code": 1, "stdout": "", "stderr": "no fixture for " + key}
    )

log_path = os.environ.get("FAKE_GH_LOG")
if log_path:
    with open(log_path, "a") as handle:
        handle.write(json.dumps(args) + "\\n")

sys.stdout.write(entry.get("stdout", ""))
sys.stderr.write(entry.get("stderr", ""))
sys.exit(entry.get("exit_code", 0))
"""


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "gh"
    script.write_text(FAKE_GH_SCRIPT, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    state_path = tmp_path / "gh-state.json"
    pr_number = 42
    responses = {
        "pr list": {"exit_code": 0, "stdout": "[]"},
        "pr create": {
            "exit_code": 0,
            "stdout": f"https://github.com/org/target/pull/{pr_number}\n",
        },
        "pr view": {
            "exit_code": 0,
            "stdout": json.dumps(
                {
                    "number": pr_number,
                    "url": f"https://github.com/org/target/pull/{pr_number}",
                    "headRefOid": "0" * 40,
                    "state": "OPEN",
                }
            ),
        },
    }
    state_path.write_text(json.dumps(responses), encoding="utf-8")
    monkeypatch.setenv("FAKE_GH_STATE", str(state_path))
    monkeypatch.setenv("FAKE_GH_LOG", str(tmp_path / "gh-calls.jsonl"))
    return state_path


def _stub(tmp_path: Path, name: str, body: str) -> Path:
    script = tmp_path / name
    script.write_text(f"#!{sys.executable}\nimport json, os, sys\n{body}\n")
    script.chmod(0o755)
    return script


def claude_fix_stub(tmp_path: Path, *, repo: Path, fail_first: int = 0) -> Path:
    """A Claude stub that edits `app.py` to `x = 2` (the fix) and reports a completed envelope.

    `fail_first` counts how many leading invocations should instead leave the bug in place
    (`x = 1`, still claiming a completed status) — modelling an implementation attempt that
    reports success but did not actually fix anything, which deterministic validation must catch
    and route to repair.
    """
    counter_file = tmp_path / "claude_invocations"
    report_json = json.dumps(
        {
            "status": "completed",
            "verdict": "pass",
            "summary": "updated app.py",
            "assumptions": [],
            "blocking_issues": [],
            "files_changed": ["app.py"],
            "validation_performed": [],
            "findings": [],
        }
    )
    body = (
        "sys.stdin.read()\n"
        f"counter_path = {str(counter_file)!r}\n"
        "count = 1\n"
        "if os.path.exists(counter_path):\n"
        "    count = int(open(counter_path).read().strip()) + 1\n"
        'open(counter_path, "w").write(str(count))\n'
        f"app_path = {str(repo / 'app.py')!r}\n"
        f"if count <= {fail_first}:\n"
        '    open(app_path, "w").write("x = 1\\n")\n'
        "else:\n"
        '    open(app_path, "w").write("x = 2\\n")\n'
        f"envelope = {{'type': 'result', 'subtype': 'success', 'result': {report_json!r}}}\n"
        "print(json.dumps(envelope))\n"
    )
    return _stub(tmp_path, "claude", body)


def codex_qa_stub(tmp_path: Path, *, verdict: str = "pass") -> Path:
    report = {
        "status": "completed",
        "verdict": verdict,
        "summary": "reviewed the diff",
        "assumptions": [],
        "blocking_issues": [] if verdict == "pass" else ["not correct"],
        "files_changed": [],
        "validation_performed": ["manual review"],
        "findings": [] if verdict == "pass" else ["issue found"],
    }
    body = (
        "sys.stdin.read()\n"
        "answer = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
        f"open(answer, 'w').write(json.dumps({report!r}))\n"
    )
    return _stub(tmp_path, "codex", body)


def config_for(tmp_path: Path, repo: Path, *, claude: Path, codex: Path) -> WorkflowConfig:
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "audit").mkdir(exist_ok=True)
    return WorkflowConfig.model_validate(
        {
            "repository_path": str(repo),
            "repository_identity": _remote_identity(repo),
            "remote_name": "origin",
            "baseline_branch": BASELINE,
            "stage_contract_directory": "docs/stage-prompts",
            "stage_branch_naming": "feature/{stage_id}",
            "test_command": f"{sys.executable} -m pytest test_app.py -q",
            "lint_command": f"{sys.executable} -c pass",
            "formatting_command": f"{sys.executable} -c pass",
            "security_command": f"{sys.executable} -c pass",
            "required_github_checks": [],
            "merge_method": "squash",
            "claude_cli_executable": str(claude),
            "claude_cli_timeout_seconds": 30,
            "codex_cli_executable": str(codex),
            "codex_cli_timeout_seconds": 30,
            "allowed_environment_variables": ["PATH", "HOME", "FAKE_GH_STATE", "FAKE_GH_LOG"],
            "allowed_changed_paths": ["app.py", "test_app.py"],
            "forbidden_changed_paths": ["secrets/**"],
            "repair_attempt_limit": 3,
            "state_directory": str(tmp_path / "state"),
            "audit_directory": str(tmp_path / "audit"),
        }
    )


def _remote_identity(repo: Path) -> str:
    url = git(repo, "remote", "get-url", "origin")
    return url


def task_for(repo: Path, *, workflow_id: str = "wf-1") -> ImplementationTask:
    import hashlib

    head_sha = git(repo, "rev-parse", "HEAD")
    contract_bytes = (repo / "docs" / "stage-prompts" / "AUTO-999.md").read_bytes()
    return ImplementationTask(
        workflow_id=workflow_id,
        stage_id="AUTO-999",
        stage_contract_path="docs/stage-prompts/AUTO-999.md",
        stage_contract_hash="sha256:" + hashlib.sha256(contract_bytes).hexdigest(),
        planned_stage_branch=STAGE_BRANCH,
        baseline_commit_sha=head_sha,
        authorized_at="2026-08-02T00:00:00+00:00",
        engine_version="0.1.0",
        authorized_by="Human Owner",
        task_description="Set x to 2 in app.py",
        commit_message="fix(app): set x to 2",
        pull_request_title="Set x to 2",
        pull_request_body="Fixes the value of x.",
    )


AUTO_APPROVE_RUN_OVERLAY = ApprovalPolicyOverlay(
    timeout_seconds=1,
    timeout_action=TimeoutAction.AUTO_APPROVE,
    channels=(ApprovalChannel.CLI,),
)


def run_past_auto_approve(driver: ImplementerModeDriver) -> Any:
    """Drive `driver` to completion, waiting out `AUTO_APPROVE_RUN_OVERLAY`'s 1-second deadline.

    `evaluate_approval` is lazy (`approvals.py`'s whole design: no timer, no thread) — a deadline
    only takes effect once something looks *after* it has passed, so a test using a real 1-second
    timeout has to let real time pass before asking again, exactly as a resumed production driver
    would after being invoked again later.
    """
    import dataclasses
    import time

    outcome = driver.run_to_pr_open()
    all_steps = list(outcome.steps)
    for _ in range(5):
        if outcome.reached_pr_open or outcome.final_state.value == "FAILED":
            break
        if outcome.steps and outcome.steps[-1].phase is ImplementerPhase.AWAITING_APPROVAL:
            time.sleep(1.2)
            outcome = driver.run_to_pr_open()
            all_steps.extend(outcome.steps)
        else:
            break
    return dataclasses.replace(outcome, steps=tuple(all_steps))


class TestHappyPath:
    def test_reaches_pr_open_with_qa_and_auto_approval(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo)

        driver = ImplementerModeDriver.start(
            config,
            task=task,
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        outcome = run_past_auto_approve(driver)

        assert outcome.reached_pr_open, [s.detail for s in outcome.steps]
        assert outcome.final_state is WorkflowState.PR_OPEN
        state_names = [s.from_state.value for s in outcome.steps]
        assert "REPAIRING" not in state_names

    def test_guarded_qa_skip_never_fabricates_a_verdict(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-qa-skip")

        driver = ImplementerModeDriver.start(
            config,
            task=task,
            qa_policy_overlays=ImplementerPolicyOverlays(
                gate=ImplementerPolicyOverlay(independent_qa_required=False)
            ),
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        outcome = run_past_auto_approve(driver)

        assert outcome.reached_pr_open, [s.detail for s in outcome.steps]
        from agentos_workflow.skills.reporting import read_reports

        qa_reports = read_reports(
            audit_root=config.audit_directory, workflow_id=task.workflow_id, report_kind="qa"
        ).unwrap()
        assert qa_reports == []


class TestGuardedQaPolicy:
    def test_default_requires_qa(self) -> None:
        policy = resolve_implementer_policy(ImplementerPolicyOverlays())
        assert policy.independent_qa_required is True

    def test_project_layer_cannot_disable_qa(self) -> None:
        with pytest.raises(ImplementerPolicyError):
            resolve_implementer_policy(
                ImplementerPolicyOverlays(
                    project=ImplementerPolicyOverlay(independent_qa_required=False)
                )
            )

    def test_gate_layer_may_disable_qa(self) -> None:
        policy = resolve_implementer_policy(
            ImplementerPolicyOverlays(gate=ImplementerPolicyOverlay(independent_qa_required=False))
        )
        assert policy.independent_qa_required is False

    def test_run_layer_may_disable_qa(self) -> None:
        policy = resolve_implementer_policy(
            ImplementerPolicyOverlays(run=ImplementerPolicyOverlay(independent_qa_required=False))
        )
        assert policy.independent_qa_required is False


class TestBoundedRepair:
    def test_repairs_a_failing_implementation_within_the_attempt_limit(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo, fail_first=1)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-repair")

        driver = ImplementerModeDriver.start(
            config,
            task=task,
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        outcome = run_past_auto_approve(driver)

        assert outcome.reached_pr_open, [s.detail for s in outcome.steps]
        state_names = [s.from_state for s in outcome.steps]
        assert WorkflowState.REPAIRING in state_names

    def test_exhausts_repair_attempts_and_fails(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo, fail_first=999)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-repair-exhausted")

        driver = ImplementerModeDriver.start(
            config,
            task=task,
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        outcome = run_past_auto_approve(driver)

        assert not outcome.reached_pr_open
        assert outcome.final_state is WorkflowState.FAILED
        repair_visits = [s for s in outcome.steps if s.from_state is WorkflowState.REPAIRING]
        assert len(repair_visits) == 3


class TestNonRepairableFindings:
    def test_forbidden_path_change_fails_without_ever_entering_repair(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        leak_path = repo / "secrets" / "leak.txt"
        report_json = json.dumps(
            {
                "status": "completed",
                "verdict": "pass",
                "summary": "done",
                "assumptions": [],
                "blocking_issues": [],
                "files_changed": ["app.py", "secrets/leak.txt"],
                "validation_performed": [],
                "findings": [],
            }
        )
        forbidden_body = (
            "sys.stdin.read()\n"
            f"os.makedirs({str(leak_path.parent)!r}, exist_ok=True)\n"
            f"open({str(leak_path)!r}, 'w').write('oops')\n"
            f"open({str(repo / 'app.py')!r}, 'w').write('x = 2\\n')\n"
            f"envelope = {{'type': 'result', 'subtype': 'success', 'result': {report_json!r}}}\n"
            "print(json.dumps(envelope))\n"
        )
        claude = _stub(tmp_path, "claude", forbidden_body)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-forbidden")

        driver = ImplementerModeDriver.start(
            config,
            task=task,
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        outcome = run_past_auto_approve(driver)

        assert not outcome.reached_pr_open
        assert outcome.final_state is WorkflowState.FAILED
        assert all(s.from_state is not WorkflowState.REPAIRING for s in outcome.steps)


class TestResume:
    def test_resumes_after_a_simulated_crash_mid_implementation(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-resume-implementing")

        first = ImplementerModeDriver.start(config, task=task)
        assert first.step().to_state is WorkflowState.PRECONDITIONS_CHECKED
        assert first.step().to_state is WorkflowState.BRANCH_CREATED
        assert first.step().to_state is WorkflowState.IMPLEMENTING

        # Simulate a crash: an initial-execution attempt was durably reserved (STARTED) but the
        # process died before Claude ever ran, so no COMPLETED record and no working-tree change
        # exist. `first._session` is the same private facade a fresh `.resume()` would build.
        first._session.record_initial_execution_attempt_started(
            WorkflowState.IMPLEMENTING, attempt_number=1, start_time="2026-08-02T00:00:00+00:00"
        )
        # A real crash would take the OS-level `flock` with it; simulate that by releasing the
        # lock this same in-process object still holds, so `.resume()` below can reacquire it.
        first._session._resumed.lock.release()

        resumed = ImplementerModeDriver.resume(
            config,
            task=task,
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        assert resumed.state is WorkflowState.IMPLEMENTING
        outcome = run_past_auto_approve(resumed)

        assert outcome.reached_pr_open, [s.detail for s in outcome.steps]

    def test_pauses_for_a_pending_approval_then_resumes_after_manual_decision(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-manual-approval")

        driver = ImplementerModeDriver.start(config, task=task)
        outcome = driver.run_to_pr_open()

        assert not outcome.reached_pr_open
        assert outcome.steps[-1].phase is ImplementerPhase.AWAITING_APPROVAL
        assert driver.state is WorkflowState.READY_TO_COMMIT

        approvals = ApprovalService(StateStore.for_config(config))
        approval_id = f"{task.workflow_id}-implementer-approval"
        approvals.decide_approval(
            workflow_id=task.workflow_id,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="human-owner",
            source=ApprovalChannel.CLI,
        )
        driver._session._resumed.lock.release()

        resumed = ImplementerModeDriver.resume(config, task=task)
        final_outcome = resumed.run_to_pr_open()
        assert final_outcome.reached_pr_open, [s.detail for s in final_outcome.steps]


class TestStopsAtPrOpen:
    def test_step_has_no_handler_beyond_pr_open(
        self, tmp_path: Path, repo: Path, fake_gh: Path
    ) -> None:
        claude = claude_fix_stub(tmp_path, repo=repo)
        codex = codex_qa_stub(tmp_path, verdict="pass")
        config = config_for(tmp_path, repo, claude=claude, codex=codex)
        task = task_for(repo, workflow_id="wf-stop-at-pr-open")

        driver = ImplementerModeDriver.start(
            config,
            task=task,
            approval_overlays=ApprovalPolicyOverlays(run=AUTO_APPROVE_RUN_OVERLAY),
        )
        outcome = run_past_auto_approve(driver)
        assert outcome.reached_pr_open

        with pytest.raises(ImplementerModeError):
            driver.step()


class TestStructuralSecurityProperties:
    """Mirrors `test_skills_git_github.py::TestStructuralSecurityProperties`: asserted over this
    module's own source rather than trusted from review."""

    def _source(self) -> str:
        import agentos_workflow.implementer as module

        return Path(module.__file__).read_text(encoding="utf-8")

    def test_no_shell_true(self) -> None:
        assert "shell=True" not in self._source()

    def test_no_direct_subprocess_or_os_system_call(self) -> None:
        tree = ast.parse(self._source())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Attribute):
                    owner = target.value
                    if isinstance(owner, ast.Name) and owner.id in ("subprocess", "os"):
                        assert target.attr not in ("run", "Popen", "call", "system"), (
                            f"direct {owner.id}.{target.attr} call found; every side effect must "
                            "go through the existing Skills layer"
                        )
