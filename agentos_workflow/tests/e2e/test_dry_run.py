"""AUTO-007 §5 deliverable: the full end-to-end dry run (`TEST_STRATEGY.md` §5,
`MVP_SCOPE.md` §4's acceptance demonstration).

One workflow, driven through every real Agent and every real deterministic Skill against a real,
disposable local Git repository (`MockProvider` standing in for the two Model Provider roles per
`MVP_SCOPE.md`/`MODEL_PROVIDER_CONTRACTS.md` §4 — no real Claude/Codex CLI or real GitHub call is
ever made), exercising: one automatic repair cycle, one interruption/resume cycle, and the full
`commit -> push -> PR -> auto-merge-enable -> checks-wait -> merge -> closeout` path, against a
stage-contract file shaped exactly like `docs/agentos-dashboard/stage-prompts/` (read for shape
only; never modified) — demonstrating the engine can read an independently-authored stage
contract without any change to that contract's format.

**A second, previously undiscovered defect this dry run surfaces.** `PMOAgent.check_preconditions`
(`agentos_workflow/agents/pmo.py:201`) compares `calculate_contract_hash`'s bare-hex
`ContractHash.sha256` directly against `authorization.stage_contract_hash` with no prefix. But
`LocalResumeObserver` (`agentos_workflow/observation/local.py:315`, the live observer
`resume_workflow` uses whenever a real `config` is supplied — the production path) computes and
compares a `"sha256:<hex>"`-*prefixed* value for the exact same semantic field. No
`AuthorizationRecord` value can satisfy both: a bare-hex `stage_contract_hash` passes
`PRECONDITIONS_CHECKED` but any later real resume raises a false-positive
`AuthorizationBindingDriftError`; a prefixed one would fail `PRECONDITIONS_CHECKED` instead.
`test_agents_pmo.py` and `test_engine_resume.py` each unit-
test their own side against a hand-built `AuthorizationRecord` in their own module's convention
(bare and prefixed respectively) and so never caught this — exactly the gap an end-to-end dry run
exists to find. `_prefixed_contract_hash` below is a test-only `calculate_contract_hash` wrapper
that reconciles the two formats for this dry run without touching either production file (both
outside this stage's allowed paths); this finding is reported in full in this stage's completion
report and belongs as a new `OPEN_QUESTIONS.md`/bug entry, not a silent fix here.

**A genuine, already-known gap this dry run must route around rather than paper over.**
`GitAgent.create_pull_request`/`read_pull_request_state` and every `MergeAgent` method
(`agentos_workflow/agents/git.py`, `agentos_workflow/agents/merge.py`) invoke their five
GitHub-facing Skills without ever forwarding `allowed_environment_variables` — the exact
`agentos_workflow/agents/**` gap AUTO-006 self-reported and recorded as OD-10/DD-38 (also stated
in `handover/PROJECT_HANDOVER.md`'s "Known open items"). Fixing it means editing
`agentos_workflow/agents/**`, outside this stage's allowed files
(`agentos_workflow/tests/e2e/**`, `agentos_workflow/tests/recovery/**` only). `_gh_env_forwarding`
below is a test-only `CapabilityBroker` skill-binding wrapper — production code is never
touched — that supplies the fake `gh`'s environment the way a real, fixed `allowed_environment_
variables` config value eventually will, so this dry run can still exercise the real
GitHub-facing Skills end to end. This is reported here, not fixed, exactly as the stage contract
requires ("a genuine gap ... is recorded as a new OPEN_QUESTIONS.md entry rather than silently
implemented beyond this stage's scope").
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.agents import (
    VALIDATION_GATE_CHECKS,
    AgentKind,
    CapabilityBroker,
    ValidationCheck,
    ValidationOutcome,
    default_skill_registry,
    run_repair_loop,
)
from agentos_workflow.agents.closeout import CloseoutAgent
from agentos_workflow.agents.git import GitAgent
from agentos_workflow.agents.implementation import ImplementationAgent
from agentos_workflow.agents.merge import MergeAgent
from agentos_workflow.agents.pmo import PMOAgent
from agentos_workflow.agents.qa import QAAgent
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator.engine import WorkflowSession, WorkflowState
from agentos_workflow.providers import ProviderRole, ProviderVerdict, provider_success
from agentos_workflow.providers.mock import MockProvider, canned_report
from agentos_workflow.skills.git_github import (
    create_pull_request,
    enable_automatic_squash_merge,
    read_pull_request_state,
    read_required_checks,
    verify_head_sha,
    verify_merge_completion,
)
from agentos_workflow.skills.repository import _normalize_remote_url
from agentos_workflow.tests.test_agents_repair_loop import implementation_skills
from agentos_workflow.tests.test_skills_git_github import (
    fake_gh,  # noqa: F401 (reused fixture)
    gh_calls,
    set_gh_responses,
)

BASELINE = "main"
REMOTE = "origin"
STAGE_ID = "EX-100"
STAGE_BRANCH = "feature/ex-100-dry-run-example"
WORKFLOW_ID = "wf-e2e-dry-run"
GH_ENV = ("FAKE_GH_STATE", "FAKE_GH_LOG")

# The exact shape of docs/agentos-dashboard/stage-prompts/*.md — a metadata table followed by a
# "## Canonical Prompt" section — reproduced here as a disposable fixture contract so this test
# never reads or writes anything under the real docs/agentos-dashboard/ tree.
CONTRACT_TEMPLATE = """# {stage_id} — Dry-run example stage

| Field | Value |
|---|---|
| **Stage** | {stage_id} · Role: Engine implementation session |
| **Branch** | `{branch}` |
| **Commit message** | `feat(example): add the dry-run example file ({stage_id})` |
| **Report** | `docs/reports/example/{stage_id}-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

## Canonical Prompt

Add `docs/example/hello.txt` containing a friendly greeting. Nothing else.
"""

REGISTRY_TEMPLATE = """# Example — Stage Registry

## 4. Registry

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| EX-099 | Predecessor | Engine implementation session | COMPLETE | `x` | `y` |
| {stage_id} | Dry-run example | Engine implementation session | AUTHORIZED | `{branch}` | `z` |
"""


def _gh_env_forwarding(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Test-only wrapper: injects the fake `gh`'s environment allowlist for the five Skill call
    sites `agents/git.py`/`agents/merge.py` never forward it from (module docstring, OD-10)."""

    def wrapped(**kwargs: Any) -> Any:
        kwargs.setdefault("allowed_environment_variables", GH_ENV)
        return fn(**kwargs)

    return wrapped


def _prefixed_contract_hash(**kwargs: Any) -> Any:
    """Test-only `calculate_contract_hash` wrapper reconciling the bare-hex/`"sha256:"`-prefixed
    inconsistency this dry run discovered (module docstring, "A second, previously undiscovered
    defect")."""
    import dataclasses

    from agentos_workflow.skills.contract import calculate_contract_hash

    result = calculate_contract_hash(**kwargs)
    if not result.ok or result.value is None:
        return result
    return type(result)(
        ok=True,
        value=dataclasses.replace(result.value, sha256=f"sha256:{result.value.sha256}"),
        error=None,
    )


@dataclass(frozen=True)
class _Authorization:
    """Stand-in for the Orchestrator's `AuthorizationRecord`, satisfying `PMOAgent`'s
    `BoundAuthorization` Protocol — the same technique `test_agents_pmo.py` uses."""

    workflow_id: str
    stage_id: str
    repository_identity: str
    stage_contract_hash: str
    baseline_branch: str
    baseline_commit_sha: str
    planned_stage_branch: str


@pytest.fixture
def target_repository(tmp_path: Path) -> tuple[Path, Path]:
    """A real target repository with a real `origin` remote, matching `test_agents_pmo.py`'s and
    `test_skills_git_github.py`'s fixture conventions (never a synthetic path)."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", BASELINE, str(origin)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", BASELINE)
    _git(work, "config", "user.name", "Dry Run Fixture")
    _git(work, "config", "user.email", "dry-run-fixture@example.invalid")
    _write(work, "README.md", "baseline\n")
    # A real target repository onboarded to this engine is expected to gitignore its own control
    # directory (`CONFIGURATION_MODEL.md`) — without it, the lock file `WorkflowSession` writes at
    # `<repository_path>/.agentos/workflow.lock` would show up as an untracked, dirty path to
    # `inspect_working_tree`, which has no special-case exclusion of its own (unlike the resume
    # observer's `_configured_control_prefixes`, `orchestrator/engine.py`).
    _write(work, ".gitignore", ".agentos/\n")
    _git(work, "add", "README.md", ".gitignore")
    _git(work, "commit", "-m", "initial")
    _git(work, "remote", "add", REMOTE, str(origin))
    _git(work, "push", "-u", REMOTE, BASELINE)
    return work, origin


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(repo),
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Dry Run Fixture",
            "GIT_AUTHOR_EMAIL": "dry-run-fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Dry Run Fixture",
            "GIT_COMMITTER_EMAIL": "dry-run-fixture@example.invalid",
        },
    )
    return result.stdout.strip()


def _write(repo: Path, relative: str, content: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _config(*, repository_path: Path, repository_identity: str, state_root: Path) -> WorkflowConfig:
    return WorkflowConfig.model_validate(
        {
            "repository_path": repository_path,
            "repository_identity": repository_identity,
            "remote_name": REMOTE,
            "baseline_branch": BASELINE,
            "stage_contract_directory": "docs/example/stage-prompts",
            "stage_branch_naming": "feature/{stage_id}-{slug}",
            "test_command": "true",
            "lint_command": "true",
            "formatting_command": "true",
            "security_command": "true",
            "required_github_checks": ["ci/tests"],
            "merge_method": "squash",
            "claude_cli_executable": Path("/usr/local/bin/claude"),
            "claude_cli_timeout_seconds": 60,
            "codex_cli_executable": Path("/usr/local/bin/codex"),
            "codex_cli_timeout_seconds": 60,
            "allowed_environment_variables": list(GH_ENV),
            "allowed_changed_paths": ["docs/example/**"],
            "forbidden_changed_paths": [],
            "repair_attempt_limit": 3,
            "state_directory": state_root / "state",
            "audit_directory": state_root / "audit",
        }
    )


def _pmo_broker(audit_root: Path) -> CapabilityBroker:
    registry = default_skill_registry()
    pmo_skills = (
        "verify_repository_identity",
        "inspect_working_tree",
        "inspect_current_branch",
        "verify_baseline_ancestry",
        "locate_stage_contract",
        "parse_stage_metadata",
        "calculate_contract_hash",
        "validate_stage_ordering",
        "detect_future_stage_work",
        "create_stage_branch",
        "append_audit_event",
    )
    skills = {name: registry[name] for name in pmo_skills if name in registry}
    skills["calculate_contract_hash"] = _prefixed_contract_hash
    return CapabilityBroker(AgentKind.PMO, skills=skills)


def _git_broker() -> CapabilityBroker:
    registry = dict(default_skill_registry())
    from agentos_workflow.skills.git_github import create_commit, push_stage_branch

    registry["create_commit"] = create_commit
    registry["push_stage_branch"] = push_stage_branch
    registry["create_pull_request"] = _gh_env_forwarding(create_pull_request)
    registry["read_pull_request_state"] = _gh_env_forwarding(read_pull_request_state)
    registry["verify_head_sha"] = verify_head_sha
    return CapabilityBroker(AgentKind.GIT, skills=registry)


def _merge_broker() -> CapabilityBroker:
    registry = dict(default_skill_registry())
    registry["verify_head_sha"] = verify_head_sha
    registry["read_required_checks"] = _gh_env_forwarding(read_required_checks)
    registry["enable_automatic_squash_merge"] = _gh_env_forwarding(enable_automatic_squash_merge)
    registry["verify_merge_completion"] = _gh_env_forwarding(verify_merge_completion)
    return CapabilityBroker(AgentKind.MERGE, skills=registry)


def _closeout_broker() -> CapabilityBroker:
    return CapabilityBroker(AgentKind.CLOSEOUT, skills=default_skill_registry())


def _qa_broker(provider: MockProvider) -> CapabilityBroker:
    registry = dict(default_skill_registry())
    qa_skills = {"generate_qa_report", "validate_qa_report", "append_audit_event"}
    return CapabilityBroker(
        AgentKind.QA,
        skills={name: registry[name] for name in registry if name in qa_skills},
        providers=lambda role: provider,
    )


def _passing_validation() -> ValidationOutcome:
    return ValidationOutcome(
        passed=True,
        checks=tuple(ValidationCheck(name=name, passed=True) for name in VALIDATION_GATE_CHECKS),
    )


def test_full_workflow_created_to_done_with_one_repair_and_one_interruption(
    tmp_path: Path, target_repository: tuple[Path, Path], fake_gh: Path  # noqa: F811
) -> None:
    work, origin = target_repository
    repository_identity = _normalize_remote_url(str(origin))

    # -- A DASH-family-shaped stage contract and registry, written into the disposable target
    # repository only (docs/agentos-dashboard/** itself is never read or touched). -------------
    contract_directory = work / "docs" / "example" / "stage-prompts"
    contract_directory.mkdir(parents=True)
    contract_path = contract_directory / f"{STAGE_ID}.md"
    contract_path.write_text(
        CONTRACT_TEMPLATE.format(stage_id=STAGE_ID, branch=STAGE_BRANCH), encoding="utf-8"
    )
    registry_path = work / "docs" / "example" / "STAGE_REGISTRY.md"
    registry_path.write_text(
        REGISTRY_TEMPLATE.format(stage_id=STAGE_ID, branch=STAGE_BRANCH), encoding="utf-8"
    )
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "add example stage contract and registry")
    _git(work, "push", REMOTE, BASELINE)
    baseline_sha = _git(work, "rev-parse", "HEAD")
    # "sha256:"-prefixed to match `LocalResumeObserver`'s format (module docstring); PMOAgent's
    # own `calculate_contract_hash` binding is wrapped to match via `_prefixed_contract_hash`.
    contract_hash = f"sha256:{hashlib.sha256(contract_path.read_bytes()).hexdigest()}"

    config = _config(
        repository_path=work,
        repository_identity=repository_identity,
        state_root=tmp_path / "engine",
    )
    audit_root = config.audit_directory
    audit_root.mkdir(parents=True, exist_ok=True)
    config.state_directory.mkdir(parents=True, exist_ok=True)

    session = WorkflowSession.start(
        config,
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_contract_path=str(contract_path.relative_to(work)),
        stage_contract_hash=contract_hash,
        planned_stage_branch=STAGE_BRANCH,
        baseline_commit_sha=baseline_sha,
        authorized_at="2026-07-28T10:00:00+00:00",
        authorized_by="human-owner",
        engine_version="0.1.0",
    )
    authorization = _Authorization(
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        repository_identity=config.repository_identity,
        stage_contract_hash=contract_hash,
        baseline_branch=BASELINE,
        baseline_commit_sha=baseline_sha,
        planned_stage_branch=STAGE_BRANCH,
    )

    # -- PRECONDITIONS_CHECKED: the real Precondition Gate against the real repository. --------
    pmo = PMOAgent(_pmo_broker(audit_root))
    preconditions = pmo.check_preconditions(
        authorization=authorization,
        repository_path=work,
        remote_name=REMOTE,
        contract_directory=contract_directory,
        stage_registry=registry_path,
        audit_root=audit_root,
    )
    assert preconditions.ok is True, preconditions.error
    session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")

    # -- BRANCH_CREATED: the real stage branch, created at the authorized baseline commit. -----
    branch_created = pmo.create_branch(
        authorization=authorization, repository_path=work, audit_root=audit_root
    )
    assert branch_created.ok is True, branch_created.error
    session.transition_to(WorkflowState.BRANCH_CREATED, actor="orchestrator")
    _git(work, "checkout", STAGE_BRANCH)

    # -- Interruption/resume cycle (TEST_STRATEGY.md §5): the process is torn down and a fresh
    # WorkflowSession re-attaches from persisted state alone, re-verifying live repository
    # observation (WORKFLOW_STATES.md §6/§6a) rather than trusting anything held in memory.
    # BRANCH_CREATED is chosen deliberately: WORKFLOW_STATES.md §6a's policy for this state is a
    # plain live-fact comparison (planned branch checked out at the bound baseline, no
    # implementation-attempt evidence yet) with no reconciliation-evidence requirement — unlike
    # every state from IMPLEMENTING onward, which §6a documents as needing persisted attempt/
    # commit evidence a bare `WorkflowSession.resume()` call does not supply on its own. ---------
    session.release_lock_if_terminal()  # a no-op (not terminal yet)
    session._resumed.lock.release()  # simulate the original process exiting mid-workflow, the
    # same technique test_workflow_session.py's own TestResumeLifecycle uses — a real crash
    # releases the OS-level lock without ever reaching a graceful shutdown path.
    del session
    resumed_session = WorkflowSession.resume(
        config,
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        planned_stage_branch=STAGE_BRANCH,
    )
    assert resumed_session.state is WorkflowState.BRANCH_CREATED
    assert resumed_session.lock_is_held
    session = resumed_session

    # -- IMPLEMENTING: MockProvider "writes" the file; the working tree is left uncommitted,
    # exactly as GitAgent.create_commit later expects to find it. Diff-observation Skills are
    # faked here (matching test_agents_repair_loop.py's own established convention) because the
    # real inspect_diff/list_changed_files compare *committed* refs, and nothing on the stage
    # branch is committed until GitAgent runs. -------------------------------------------------
    session.transition_to(WorkflowState.IMPLEMENTING, actor="orchestrator")
    _write(work, "docs/example/hello.txt", "wrong content on the first attempt\n")

    implementation_provider = MockProvider(
        [
            provider_success(
                canned_report(
                    role=ProviderRole.IMPLEMENTATION,
                    summary="added the greeting file",
                    files_changed=("docs/example/hello.txt",),
                    recommended_commit_message="feat(example): add the dry-run example file",
                )
            ),
            provider_success(
                canned_report(
                    role=ProviderRole.REPAIR,
                    summary="fixed the greeting file's content",
                    files_changed=("docs/example/hello.txt",),
                    recommended_commit_message="fix(example): correct the greeting file",
                )
            ),
        ]
    )
    implementation = ImplementationAgent(
        CapabilityBroker(
            AgentKind.IMPLEMENTATION,
            skills=implementation_skills(changed=("docs/example/hello.txt",)),
            providers=lambda role: implementation_provider,
        ),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        repository_path=work,
        baseline_commit_sha=baseline_sha,
        session_root=tmp_path / "sessions",
        audit_root=audit_root,
        allowed_paths=("docs/example/**",),
        forbidden_paths=(),
    )
    initial = implementation.implement(contract_text=contract_path.read_text(encoding="utf-8"))
    assert initial.ok is True, initial.error

    # -- VALIDATING (first pass) -> QA_RUNNING: QA independently rejects the first attempt,
    # driving one automatic repair cycle (FAILURE_RECOVERY.md §1). -----------------------------
    session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
    qa_provider = MockProvider(
        [
            provider_success(
                canned_report(
                    role=ProviderRole.QA,
                    verdict=ProviderVerdict.FAIL,
                    summary="the greeting is wrong",
                    findings=("hello.txt content does not match the contract",),
                )
            ),
            provider_success(
                canned_report(
                    role=ProviderRole.QA,
                    verdict=ProviderVerdict.PASS,
                    summary="the greeting is correct",
                )
            ),
        ]
    )
    qa = QAAgent(
        _qa_broker(qa_provider),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        repository_path=work,
        session_root=tmp_path / "sessions",
        audit_root=audit_root,
    )
    pre_loop_qa = qa.review(validation=_passing_validation(), attempt_number=1)
    assert pre_loop_qa.ok is False, "the first QA round must reject, or there is nothing to repair"
    session.transition_to(WorkflowState.REPAIRING, actor="orchestrator")

    def _validate() -> ValidationOutcome:
        # Applies the model's repair as this dry run's stand-in for "the Claude CLI session
        # rewrote the file" — MockProvider only returns a canned report, never real file edits.
        _write(work, "docs/example/hello.txt", "hello from the AUTO-007 dry run\n")
        return _passing_validation()

    repair_outcome = run_repair_loop(
        implementation=implementation,
        qa=qa,
        validate=_validate,
        initial_failure_report={
            "source": "independent_qa",
            "findings": ["hello.txt content does not match the contract"],
        },
        attempt_limit=config.repair_attempt_limit,
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
    )
    assert repair_outcome.repaired is True
    # Note (recorded as OD-12, `docs/workflow-automation/OPEN_QUESTIONS.md`): the pre-loop QA
    # round and the repair loop's own first internal round both use `attempt_number=1`, so they
    # collide on the same `reports/qa.1.json` artifact — attempt 1 here fails on that collision,
    # not on a genuine QA re-rejection, so repair actually completes on the *second* loop
    # iteration even though only one QA verdict was ever configured to fail. GOV-3 gave the
    # rounds attempt-aware artifact names inside the workflow's own directory; it did not change
    # who assigns the round numbers, which is what this collision is really about.
    assert repair_outcome.repair_attempts_used == 2
    session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
    session.transition_to(WorkflowState.QA_RUNNING, actor="orchestrator")
    session.transition_to(WorkflowState.READY_TO_COMMIT, actor="orchestrator")
    assert (work / "docs" / "example" / "hello.txt").read_text(
        encoding="utf-8"
    ) == "hello from the AUTO-007 dry run\n"

    # -- COMMITTED: the real create_commit Skill, against the real repository. -----------------
    git_agent = GitAgent(
        _git_broker(),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        baseline_branch=BASELINE,
        remote_name=REMOTE,
        repository_path=work,
        audit_root=audit_root,
        allowed_environment_variables=GH_ENV,
    )
    head_before_commit = _git(work, "rev-parse", "HEAD")
    committed = git_agent.create_commit(
        message="feat(example): add the dry-run example file",
        expected_head_sha=head_before_commit,
    )
    assert committed.ok is True, committed.error
    commit_sha = committed.evidence["commit_sha"]
    session.transition_to(WorkflowState.COMMITTED, actor="orchestrator")

    # -- PUSHED: the real push_stage_branch Skill, against the real local `origin` remote. -----
    pushed = git_agent.push_stage_branch(expected_head_sha=commit_sha)
    assert pushed.ok is True, pushed.error
    session.transition_to(WorkflowState.PUSHED, actor="orchestrator")
    assert _git(work, "ls-remote", REMOTE, f"refs/heads/{STAGE_BRANCH}").split()[0] == commit_sha

    # -- PR_OPEN: the real create_pull_request Skill, against the faked `gh`. ------------------
    set_gh_responses(
        fake_gh,
        {
            "pr list": {"exit_code": 0, "stdout": "[]"},
            "pr create": {
                "exit_code": 0,
                "stdout": "https://github.invalid/example/dry-run/pull/7\n",
            },
            "pr view": {
                "exit_code": 0,
                "stdout": json.dumps(
                    {
                        "number": 7,
                        "url": "https://github.invalid/example/dry-run/pull/7",
                        "headRefOid": commit_sha,
                    }
                ),
            },
        },
    )
    pr_opened = git_agent.create_pull_request(
        title=f"{STAGE_ID}: dry-run example stage",
        body="Opened by the AUTO-007 end-to-end dry run.",
        head_sha=commit_sha,
    )
    assert pr_opened.ok is True, pr_opened.error
    pr_number = pr_opened.evidence["pull_request_number"]
    assert pr_number == 7
    session.transition_to(WorkflowState.PR_OPEN, actor="orchestrator")

    # -- AUTO_MERGE_ENABLED: the real Merge Safety Gate — head SHA verified before the merge is
    # ever enabled (MACHINE_GATES.md §5). -------------------------------------------------------
    merge_agent = MergeAgent(
        _merge_broker(),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        repository_path=work,
        audit_root=audit_root,
        pull_request_number=pr_number,
        recorded_head_sha=commit_sha,
    )
    set_gh_responses(
        fake_gh,
        {
            "pr view": {
                "exit_code": 0,
                "stdout": json.dumps({"headRefOid": commit_sha, "state": "OPEN"}),
            },
            "pr merge": {"exit_code": 0, "stdout": "auto-merge enabled\n"},
        },
    )
    enabled = merge_agent.enable_auto_merge(deterministic_validation_passed=True, qa_passed=True)
    assert enabled.ok is True, enabled.error
    merge_calls = [call[:2] for call in gh_calls(fake_gh)]
    assert ["pr", "merge"] in merge_calls
    assert all(call[:2] != ["pr", "merge"] or "--admin" not in call for call in gh_calls(fake_gh))
    session.transition_to(WorkflowState.AUTO_MERGE_ENABLED, actor="orchestrator")

    # -- WAITING_FOR_CHECKS -> MERGED: required checks pass, then GitHub independently confirms
    # the merge (never inferred from local Git state alone, MACHINE_GATES.md §6). --------------
    set_gh_responses(
        fake_gh,
        {
            "pr checks": {
                "exit_code": 0,
                "stdout": json.dumps([{"name": "ci/tests", "state": "SUCCESS", "bucket": "pass"}]),
            }
        },
    )
    checks = merge_agent.await_required_checks()
    assert checks.ok is True, checks.error
    assert checks.evidence["all_passed"] is True
    session.transition_to(WorkflowState.WAITING_FOR_CHECKS, actor="orchestrator")

    merge_commit_sha = "f" * 40
    set_gh_responses(
        fake_gh,
        {
            "pr view": {
                "exit_code": 0,
                "stdout": json.dumps(
                    {
                        "state": "MERGED",
                        "headRefName": STAGE_BRANCH,
                        "mergeCommit": {"oid": merge_commit_sha},
                    }
                ),
            }
        },
    )
    confirmed = merge_agent.confirm_merge()
    assert confirmed.ok is True, confirmed.error
    merge_confirmation = confirmed.evidence["merge_confirmation"]
    session.transition_to(WorkflowState.MERGED, actor="orchestrator")

    # -- CLOSING -> DONE: baseline restored, branches deleted only after the independently
    # verified merge, closeout report written. --------------------------------------------------
    # The merge is only simulated against the fake `gh`; the real local Git baseline never
    # actually received the squash commit, so it is fast-forwarded here to what the merge
    # confirmation says landed, exactly as a real `git fetch`/`merge --ff-only` would after a
    # real GitHub squash merge.
    _git(work, "checkout", BASELINE)
    _git(work, "merge", "--no-ff", "-m", "squash merge (dry run)", STAGE_BRANCH)
    _git(work, "push", REMOTE, BASELINE)
    _git(work, "checkout", STAGE_BRANCH)

    session.transition_to(WorkflowState.CLOSING, actor="orchestrator")
    closeout_agent = CloseoutAgent(
        _closeout_broker(),
        workflow_id=WORKFLOW_ID,
        stage_id=STAGE_ID,
        stage_branch=STAGE_BRANCH,
        baseline_branch=BASELINE,
        remote_name=REMOTE,
        repository_path=work,
        audit_root=audit_root,
    )
    closed_out = closeout_agent.close_out(merge_confirmation=merge_confirmation)
    assert closed_out.ok is True, closed_out.error
    session.transition_to(WorkflowState.DONE, actor="orchestrator")

    assert session.is_terminal
    assert not session.lock_is_held, "reaching DONE must release the repository lock"
    assert _git(work, "branch", "--list", STAGE_BRANCH) == "", "the merged stage branch was deleted"
    assert (work / "docs" / "example" / "hello.txt").read_text(
        encoding="utf-8"
    ) == "hello from the AUTO-007 dry run\n"

    closeout_report_path = Path(closed_out.evidence["closeout_report_path"])
    assert closeout_report_path.is_file()
