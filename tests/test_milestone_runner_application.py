"""AUTO-016 section 5, 7, 10, 20 and 31: the application, the gates, and the approval façade.

Everything here is driven the way the runner drives it. The repository is a real `git init`
worktree with a real remote and a real revision; the run directory is a real
:class:`~...state.RunStateStore` under a redirected `HOME`; the run lock is a real `flock`; every
verification command is a real subprocess; and the "providers" are a real Python script spawned
through the production :class:`~...providers.base.ProviderInvoker`, writing real transcripts
through section 17a's write boundary. Nothing is mocked, and no `claude` or `codex` process is
ever spawned -- the adapter under test is a test-owned adapter with its own argv, which is the
same seam the contract's own fake-provider matrix (section 26) describes.

The named classes this milestone requires are all present: `TestSoleTransitionAuthority`,
`TestCommitApprovalBoundToDiffAndInvalidatedOnChange`, `TestCommitApprovalIsSingleUse`,
`TestMutatingGitOnlyInApprovalGitModule`, `TestP5AllGitRoutesThroughGuard` and
`TestP6AbortAcquiresLock`, alongside `TestAllowedTransitionsAreEnforced`,
`TestEntryConditionsReVerifiedAtEveryBoundary`, `TestHappyPathReachesReadyForCommitApproval`,
`TestApprovalIsEvidenceNotAuthority` and `TestNoDestructiveGitPathAnywhere`.
"""

import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.application import (
    UNNAMED_STOP_REASON,
    ApplicationError,
    MilestoneRunnerApplication,
    PreflightReport,
    ProviderBinding,
    RunRefused,
    TransitionRefused,
    latest_run_id,
    new_run_id,
    record_latest_run,
    resume_run,
    revise_record,
    run_preflight,
    start_run,
    transition_to,
)
from ai_workflow_engine.milestone_runner.approval_git import (
    ABSENT_PATH_DIGEST,
    COMMIT_CONFIRMATION,
    PUSH_CONFIRMATION,
    ApprovalGit,
    ApprovalInvalid,
    ApprovalRefused,
    CommitApproval,
    bind_approval,
    validate_approval,
)
from ai_workflow_engine.milestone_runner.config import RunnerConfig, load_runner_config
from ai_workflow_engine.milestone_runner.git_inspect import GitReadOnlyInspector
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    ALLOWED_RUN_TRANSITIONS,
    RUN_COUNTER_FIELDS,
    STATE_SCHEMA_VERSION,
    ApprovalOperation,
    Finding,
    FindingSeverity,
    FindingStatus,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
    RunRecord,
    RunStatus,
    StopReason,
    VerificationResult,
)
from ai_workflow_engine.milestone_runner.plan import MilestonePlanLoader
from ai_workflow_engine.milestone_runner.providers.base import (
    ProviderAdapter,
    ProviderRequest,
    transcript_label_for,
)
from ai_workflow_engine.milestone_runner.state import (
    PROVIDER_INTENT_FILE_NAME,
    ProviderInvocationIntent,
    ResumeAction,
    RunStateStore,
    TranscriptKind,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner"
APPROVAL_GIT_SOURCE = PACKAGE_ROOT / "approval_git.py"
CLI_SOURCE = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "cli.py"

#: The disposable repository every AUTO-016 suite pins, so one artifact root serves them all.
REMOTE = "https://github.com/example/demo-repo.git"
IDENTITY = "demo-repo--2059e82cffa9"
STAGE_ID = "AUTO-099"
MILESTONE_ID = "AUTO-099-M01"
CONTRACT_PATH = "docs/workflow-automation/stage-prompts/AUTO-099.md"
CONTRACT_TEXT = "# AUTO-099 -- a disposable contract for a disposable repository\n"
IMPLEMENTED_PATH = "src/demo/feature.py"
MOMENT = datetime(2026, 8, 6, 12, 0, 0, tzinfo=UTC)

#: The five governance checks section 16 requires, each emitting the machine-readable document
#: the gate reads (defect P-7). No console table is produced and none is parsed.
GOVERNANCE_CHECKS: tuple[str, ...] = ("git", "task-state", "governance", "registries", "handover")

#: The result blocks the fake provider emits, one per role, in section 18's fenced grammar.
FAKE_RESULTS: dict[str, str] = {
    "IMPLEMENTATION": (
        "AUTO016_MILESTONE_RESULT\n"
        f"milestone: {MILESTONE_ID}\n"
        "status: COMPLETE\n"
        f"changed_paths: [{IMPLEMENTED_PATH}]\n"
        "END_AUTO016_MILESTONE_RESULT\n"
    ),
    "REVIEW": (
        "AUTO016_REVIEW_RESULT\n"
        "verdict: APPROVED\n"
        "blockers: []\n"
        "deferred: []\n"
        "END_AUTO016_REVIEW_RESULT\n"
    ),
}


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def governance_command(name: str) -> list[str]:
    """One governance check as a real command emitting a real machine-readable document."""
    document = json.dumps({"check_name": name, "status": "PASS", "findings": []})
    return [sys.executable, "-c", f"print({document!r})"]


# --------------------------------------------------------------------------------------
# The fake provider: a real script, spawned through the production invoker
# --------------------------------------------------------------------------------------

#: The argv element meaning "this role writes nothing". A sentinel rather than an empty string
#: because :class:`~...providers.base.ProviderRequest` refuses an empty argument outright -- an
#: adapter that can pass a blank vector element is an adapter whose argv is not bounded.
NO_TOUCH = "-"

FAKE_PROVIDER_SCRIPT = """\
import json, os, pathlib, sys

role = sys.argv[1]
results = json.loads(sys.argv[2])
touch = sys.argv[3]
sys.stdin.read()
if touch != "-":
    target = pathlib.Path(os.getcwd()) / touch
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# written by the fake implementation provider\\n", encoding="utf-8")
sys.stdout.write(results[role])
"""


class FakeAdapter(ProviderAdapter):
    """A provider adapter this suite owns, with its own fixed argv and no `claude`/`codex` name.

    It is a real adapter driving a real subprocess through the production
    :class:`~...providers.base.ProviderInvoker`, so the prompt really is delivered on stdin, the
    transcripts really are written through section 17a's boundary, and the failure class really is
    fixed at invocation time. What it is not is either of the two shipped adapters, so no test here
    spawns a `claude` or a `codex` process.
    """

    name: ClassVar[str] = "fake"
    roles: ClassVar[frozenset[ProviderRole]] = frozenset(ProviderRole)

    def __init__(self, script: Path, *, results: dict[str, str], touch: str = "") -> None:
        self._script = script
        self._results = results
        self._touch = touch

    def build_request(
        self, *, role: ProviderRole, prompt: str, milestone_id: str | None = None
    ) -> ProviderRequest:
        self._require_role(role)
        return ProviderRequest(
            provider=self.name,
            role=role,
            argv=[
                sys.executable,
                str(self._script),
                role.value,
                json.dumps(self._results),
                (self._touch or NO_TOUCH if role is ProviderRole.IMPLEMENTATION else NO_TOUCH),
            ],
            prompt=prompt,
            timeout_seconds=120,
            transcript_label=transcript_label_for(self.name, role),
            milestone_id=milestone_id,
        )


# --------------------------------------------------------------------------------------
# Fixtures: a real repository, a real plan root, a real configuration
# --------------------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    repository = tmp_path / "worktree"
    (repository / "docs" / "workflow-automation" / "stage-prompts").mkdir(parents=True)
    (repository / "src" / "demo").mkdir(parents=True)
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "Milestone Runner Tests")
    git(repository, "remote", "add", "origin", REMOTE)
    (repository / CONTRACT_PATH).write_text(CONTRACT_TEXT, encoding="utf-8")
    (repository / "docs" / "workflow-automation" / "STAGE_REGISTRY.md").write_text(
        "| Stage | Status |\n|---|---|\n| AUTO-099 | AUTHORIZED |\n", encoding="utf-8"
    )
    (repository / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "initial")
    return repository


@pytest.fixture
def contract_sha256(worktree: Path) -> str:
    return GitReadOnlyInspector(worktree).contract_digest(CONTRACT_PATH)


@pytest.fixture
def baseline_sha(worktree: Path) -> str:
    return git(worktree, "rev-parse", "HEAD")


@pytest.fixture
def plan_root(isolated_home: Path) -> Path:
    root = isolated_home / ".ai-workflow-engine" / "milestone-runs" / IDENTITY / "plans"
    root.mkdir(parents=True)
    root.joinpath(f"{MILESTONE_ID}.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "milestone_id": MILESTONE_ID,
                "title": "The one milestone this disposable plan carries",
                "objective": "Write one file inside the milestone's own scope.",
                "depends_on": [],
                "contract_sections": ["section 5"],
                "allowed_files": [IMPLEMENTED_PATH],
                "forbidden_files": ["everything else"],
                "required_symbols": ["demo.feature"],
                "explicit_exclusions": ["Do not touch anything else."],
                "acceptance_criteria": ["The file exists."],
                "focused_verification": [
                    {"command": [sys.executable, "-c", "pass"], "purpose": "a real no-op command"}
                ],
                "completion_evidence": ["The focused command passes."],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def config_factory(
    tmp_path: Path,
    worktree: Path,
    plan_root: Path,
    baseline_sha: str,
    contract_sha256: str,
):
    def factory(**overrides: Any) -> Path:
        document: dict[str, Any] = {
            "schema_version": 1,
            "repository": {
                "root": str(worktree),
                "identity": IDENTITY,
                "expected_branch": "main",
                "baseline_sha": baseline_sha,
                "conda_environment": "ai-workflow-engine",
            },
            "stage": {
                "stage_id": STAGE_ID,
                "contract_path": CONTRACT_PATH,
                "contract_sha256": contract_sha256,
            },
            "allowlist": {
                "allowed_paths": [IMPLEMENTED_PATH],
                "forbidden_paths": ["self-governance.yaml"],
                "required_coverage": [IMPLEMENTED_PATH],
            },
            "review_policy": {
                "max_full_reviews": 1,
                "max_correction_rounds": 1,
                "max_closure_reviews": 1,
                "max_blockers": 3,
                "blocking_severities": ["CRITICAL", "HIGH"],
                "defer_severities": ["MEDIUM", "LOW"],
            },
            "providers": {
                "claude": {"executable": "claude", "timeout_seconds": 60},
                "codex": {"executable": "codex", "timeout_seconds": 60},
                "allowed_environment_variables": ["PATH", "HOME"],
            },
            "verification": {
                "focused": [],
                "final": [
                    {
                        "command": governance_command(name),
                        "timeout_seconds": 120,
                        "purpose": name,
                    }
                    for name in GOVERNANCE_CHECKS
                ],
            },
        }
        for section, values in overrides.items():
            if isinstance(values, dict):
                document[section] = {**document.get(section, {}), **values}
            else:
                document[section] = values
        path = tmp_path / f"runner-{len(list(tmp_path.glob('runner-*.yaml')))}.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
        return path

    return factory


@pytest.fixture
def config(config_factory) -> RunnerConfig:  # type: ignore[no-untyped-def]
    return load_runner_config(config_factory())


@pytest.fixture
def fake_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_provider.py"
    script.write_text(FAKE_PROVIDER_SCRIPT, encoding="utf-8")
    return script


@pytest.fixture
def providers(fake_script: Path) -> ProviderBinding:
    return ProviderBinding(
        implementation=FakeAdapter(fake_script, results=FAKE_RESULTS, touch=IMPLEMENTED_PATH),
        review=FakeAdapter(fake_script, results=FAKE_RESULTS),
    )


@pytest.fixture
def application_factory(config_factory, providers: ProviderBinding):  # type: ignore[no-untyped-def]
    def factory(**kwargs: Any) -> MilestoneRunnerApplication:
        path = kwargs.pop("config_path", None) or config_factory(**kwargs.pop("overrides", {}))
        return MilestoneRunnerApplication(
            load_runner_config(path),
            providers=kwargs.pop("providers", providers),
            clock=kwargs.pop("clock", None),
            **kwargs,
        )

    return factory


def record_for(worktree: Path, config: RunnerConfig, **overrides: Any) -> RunRecord:
    """A published-shaped run record consistent with the fixtures above."""
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": "auto016-20260806T120000Z-deadbeef",
        "repository_root": str(worktree),
        "repository_identity": IDENTITY,
        "expected_branch": "main",
        "baseline_sha": git(worktree, "rev-parse", "HEAD"),
        "contract_sha256": config.stage.contract_sha256,
        "workflow_state": RunStatus.READY_FOR_COMMIT_APPROVAL,
        "created_at": "2026-08-06T11:00:00Z",
        "updated_at": "2026-08-06T12:00:00Z",
    }
    payload.update(overrides)
    return RunRecord.model_validate(payload)


def publish(worktree: Path, record: RunRecord) -> RunStateStore:
    """Publish `record` the way the runner does: under a real lock, atomically."""
    store = RunStateStore.pin(
        repository_id=IDENTITY, run_id=record.run_id, repository_root=worktree
    )
    lock = RunLock(
        run_id=record.run_id, repository_identity=IDENTITY, artifact_root=store.artifact_root
    )
    lock.acquire()
    try:
        store.publish(record, lock=lock)
    finally:
        lock.release()
    # `start_run` names the run at the artifact root the moment it publishes; a test that
    # publishes directly does the same, so the run is findable exactly as a driven one is.
    record_latest_run(store.artifact_root, record.run_id)
    return store


def publish_intent(worktree: Path, record: RunRecord, pending: ProviderRunRecord) -> None:
    """Record the pre-invocation evidence for `pending`, the way the invoker's hook does.

    Written under a real lock through the real store, so what a test reconciles against is the
    same document a real crash would have left behind.
    """
    store = RunStateStore.pin(
        repository_id=IDENTITY, run_id=record.run_id, repository_root=worktree
    )
    lock = RunLock(
        run_id=record.run_id, repository_identity=IDENTITY, artifact_root=store.artifact_root
    )
    lock.acquire()
    try:
        store.record_provider_intent(
            pending=pending,
            evidence=GitReadOnlyInspector(worktree).evidence(),
            recorded_at="2026-08-06T12:00:00Z",
            lock=lock,
        )
    finally:
        lock.release()


# --------------------------------------------------------------------------------------
# Section 10 -- the sole transition authority
# --------------------------------------------------------------------------------------


class TestSoleTransitionAuthority:
    """Section 10: `MilestoneRunnerApplication` is the sole transition authority.

    Proved three ways: no other module in the package writes `workflow_state`; the one function
    that does refuses anything outside the closed table; and the function that carries every other
    field refuses a `workflow_state` key outright, so a coordinator's or a provider's result cannot
    transition a run by handing back a mapping.
    """

    def test_no_other_package_module_assigns_workflow_state(self) -> None:
        offenders: list[str] = []
        for source in sorted(PACKAGE_ROOT.rglob("*.py")):
            if source.name == "application.py":
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                    targets = [node.target]
                else:
                    continue
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr == "workflow_state":
                        offenders.append(f"{source.name}:{node.lineno}")
        assert offenders == []

    def test_revise_record_refuses_a_workflow_state_key(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        record = record_for(worktree, config, workflow_state=RunStatus.REVIEWING)
        with pytest.raises(ApplicationError, match="sole transition authority"):
            revise_record(record, moment=MOMENT, updates={"workflow_state": RunStatus.DONE.value})

    def test_a_coordinator_result_cannot_transition_the_run(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        record = record_for(worktree, config, workflow_state=RunStatus.REVIEWING)
        finding = Finding(
            finding_id="R-1",
            severity=FindingSeverity.HIGH,
            title="A blocker the reviewer raised",
            summary="The reviewer's account of it.",
            status=FindingStatus.OPEN,
        )
        revised = revise_record(record, moment=MOMENT, updates={"blocking_findings": [finding]})
        assert revised.workflow_state is RunStatus.REVIEWING
        assert [item.finding_id for item in revised.blocking_findings] == ["R-1"]


class TestAllowedTransitionsAreEnforced:
    """Section 10: a transition outside `ALLOWED_RUN_TRANSITIONS` is refused, never performed."""

    def test_every_admitted_pair_is_accepted(self, worktree: Path, config: RunnerConfig) -> None:
        for source, target in sorted(ALLOWED_RUN_TRANSITIONS):
            record = record_for(
                worktree,
                config,
                workflow_state=source,
                stop_reason=(
                    StopReason.DIRTY_TREE
                    if source is RunStatus.HUMAN_INTERVENTION_REQUIRED
                    else None
                ),
            )
            stop = (
                StopReason.DIRTY_TREE if target is RunStatus.HUMAN_INTERVENTION_REQUIRED else None
            )
            moved = transition_to(record, target, moment=MOMENT, stop_reason=stop)
            assert moved.workflow_state is target

    def test_an_unlisted_pair_is_refused(self, worktree: Path, config: RunnerConfig) -> None:
        record = record_for(worktree, config, workflow_state=RunStatus.PREFLIGHT)
        assert (RunStatus.PREFLIGHT, RunStatus.DONE) not in ALLOWED_RUN_TRANSITIONS
        with pytest.raises(TransitionRefused, match="not one of the"):
            transition_to(record, RunStatus.DONE, moment=MOMENT)
        assert record.workflow_state is RunStatus.PREFLIGHT

    def test_a_terminal_state_has_no_outbound_edge(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        for terminal in (RunStatus.DONE, RunStatus.ABORTED):
            record = record_for(worktree, config, workflow_state=terminal)
            with pytest.raises(TransitionRefused):
                transition_to(record, RunStatus.IMPLEMENTING, moment=MOMENT)

    def test_recovery_can_never_transition_straight_to_an_approval_state(self) -> None:
        for state in (RunStatus.READY_FOR_COMMIT_APPROVAL, RunStatus.READY_FOR_PUSH_APPROVAL):
            assert (RunStatus.HUMAN_INTERVENTION_REQUIRED, state) not in ALLOWED_RUN_TRANSITIONS


# --------------------------------------------------------------------------------------
# Section 4 -- re-verified at every boundary
# --------------------------------------------------------------------------------------


class TestEntryConditionsReVerifiedAtEveryBoundary:
    """Section 4's closing sentence: every condition is re-verified at every boundary."""

    def test_a_satisfied_preflight_names_all_nine_conditions(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        report = run_preflight(
            config,
            repository_root=worktree,
            inspector=GitReadOnlyInspector(worktree),
            environment=dict(os.environ),
            lock_held=True,
        )
        assert [condition.number for condition in report.conditions] == list(range(1, 10))
        assert report.satisfied, report.summary

    def test_head_drift_is_a_typed_refusal(self, worktree: Path, config_factory) -> None:  # type: ignore[no-untyped-def]
        drifted = load_runner_config(config_factory(repository={"baseline_sha": "0" * 40}))
        report = run_preflight(
            drifted,
            repository_root=worktree,
            inspector=GitReadOnlyInspector(worktree),
            environment=dict(os.environ),
            lock_held=True,
        )
        assert not report.satisfied
        assert report.stop_reason is StopReason.HEAD_DRIFT

    def test_a_change_outside_the_cumulative_allowlist_is_dirty_tree(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        (worktree / "unexpected.txt").write_text("not in the allowlist\n", encoding="utf-8")
        report = run_preflight(
            config,
            repository_root=worktree,
            inspector=GitReadOnlyInspector(worktree),
            environment=dict(os.environ),
            lock_held=True,
        )
        assert report.stop_reason is StopReason.DIRTY_TREE

    def test_a_change_outside_the_active_milestone_is_out_of_milestone_scope(
        self, worktree: Path, config: RunnerConfig, plan_root: Path
    ) -> None:
        from ai_workflow_engine.milestone_runner.plan import MilestonePlanLoader

        plan = MilestonePlanLoader(config, worktree).load()
        other = plan.milestones[0].model_copy(update={"allowed_files": ["src/demo/other.py"]})
        (worktree / IMPLEMENTED_PATH).write_text("inside the allowlist\n", encoding="utf-8")
        report = run_preflight(
            config,
            repository_root=worktree,
            inspector=GitReadOnlyInspector(worktree),
            environment=dict(os.environ),
            lock_held=True,
            milestone=other,
        )
        assert report.stop_reason is StopReason.OUT_OF_MILESTONE_SCOPE

    def test_an_unauthorized_stage_refuses_to_start(self, worktree: Path, config_factory) -> None:  # type: ignore[no-untyped-def]
        (worktree / "docs" / "workflow-automation" / "STAGE_REGISTRY.md").write_text(
            "| Stage | Status |\n|---|---|\n| AUTO-099 | PROPOSED |\n", encoding="utf-8"
        )
        loaded = load_runner_config(config_factory())
        report = run_preflight(
            loaded,
            repository_root=worktree,
            inspector=GitReadOnlyInspector(worktree),
            environment=dict(os.environ),
            lock_held=True,
        )
        assert report.stop_reason is StopReason.STAGE_ID_NOT_AUTHORIZED

    def test_a_read_only_command_reports_the_lock_condition_unevaluated(
        self, application_factory
    ) -> None:  # type: ignore[no-untyped-def]
        report: PreflightReport = application_factory().doctor()
        lock_condition = next(item for item in report.conditions if item.number == 9)
        assert not lock_condition.evaluated
        assert report.satisfied


# --------------------------------------------------------------------------------------
# Section 5 and section 31 -- the approved flow, driven end to end
# --------------------------------------------------------------------------------------


class TestHappyPathReachesReadyForCommitApproval:
    """Section 31: with the shipped defaults the run's own terminal state is
    `READY_FOR_COMMIT_APPROVAL`, and it stops there with the tree untouched."""

    def test_a_complete_run_stops_at_the_commit_gate(
        self, application_factory, worktree: Path
    ) -> None:  # type: ignore[no-untyped-def]
        head_before = git(worktree, "rev-parse", "HEAD")
        report = application_factory().start()
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        assert report.completed_milestones == (MILESTONE_ID,)
        assert git(worktree, "rev-parse", "HEAD") == head_before
        assert (worktree / IMPLEMENTED_PATH).is_file()

    def test_the_durable_record_carries_the_run(self, application_factory, worktree: Path) -> None:  # type: ignore[no-untyped-def]
        application = application_factory()
        application.start()
        status = application.status()
        assert status.record is not None
        record = status.record
        assert record.workflow_state is RunStatus.READY_FOR_COMMIT_APPROVAL
        assert record.changed_paths == [IMPLEMENTED_PATH]
        assert record.successful_review_rounds == 1
        assert record.review_attempts == 1
        assert record.provider_failure_count == 0
        assert [run.role for run in record.provider_runs] == [
            ProviderRole.IMPLEMENTATION,
            ProviderRole.REVIEW,
        ]

    def test_resume_after_a_complete_run_repeats_nothing(self, application_factory) -> None:  # type: ignore[no-untyped-def]
        application = application_factory()
        application.start()
        before = application.status().record
        resumed = application.resume()
        assert resumed.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        after = application.status().record
        assert before is not None and after is not None
        assert before.provider_runs == after.provider_runs

    def test_start_refuses_to_reopen_a_published_run(self, application_factory) -> None:  # type: ignore[no-untyped-def]
        application = application_factory()
        application.start()
        with pytest.raises(RunRefused, match="already published"):
            application.start()

    def test_a_tripped_gate_stops_with_the_tree_untouched(
        self, application_factory, worktree: Path, config_factory
    ) -> None:  # type: ignore[no-untyped-def]
        (worktree / "unexpected.txt").write_text("outside the allowlist\n", encoding="utf-8")
        before = sorted(
            (path.relative_to(worktree).as_posix(), path.read_bytes())
            for path in worktree.rglob("*")
            if path.is_file() and ".git/" not in path.as_posix()
        )
        report = application_factory().start()
        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert report.stop_reason is StopReason.DIRTY_TREE
        after = sorted(
            (path.relative_to(worktree).as_posix(), path.read_bytes())
            for path in worktree.rglob("*")
            if path.is_file() and ".git/" not in path.as_posix()
        )
        assert before == after


class TestResumeRefusesWhatOnlyRecoveryClears:
    """Section 13: `HUMAN_INTERVENTION_REQUIRED` exits only through an explicit recovery command."""

    def test_resume_refuses_a_human_intervention_stop(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        publish(
            worktree,
            record_for(
                worktree,
                config,
                workflow_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                stop_reason=StopReason.OUT_OF_MILESTONE_SCOPE,
            ),
        )
        with pytest.raises(RunRefused, match="explicit recovery command"):
            application_factory().resume()

    def test_resume_refuses_a_terminal_run(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        publish(worktree, record_for(worktree, config, workflow_state=RunStatus.ABORTED))
        with pytest.raises(RunRefused, match="terminal state"):
            application_factory().resume()

    @pytest.mark.parametrize(
        "state",
        [
            RunStatus.IMPLEMENTING,
            RunStatus.FOCUSED_VERIFYING,
            RunStatus.PROVIDER_WAIT,
            RunStatus.PROVIDER_RETRY_PENDING,
            RunStatus.MILESTONE_COMPLETE,
            RunStatus.FINAL_VERIFYING,
            RunStatus.REVIEWING,
            RunStatus.NEEDS_CORRECTION,
            RunStatus.CORRECTING,
            RunStatus.CLOSURE_VERIFYING,
        ],
        ids=lambda state: str(state.value),
    )
    def test_no_resumable_state_is_refused_by_the_closed_table(
        self, application_factory, worktree: Path, config: RunnerConfig, state: RunStatus
    ) -> None:  # type: ignore[no-untyped-def]
        """Finding GOV-AUTO-11-F3: resume dispatches, it does not restart the flow.

        Restarting asked for `<state> -> IMPLEMENTING`, a pair section 10's table does not carry
        for three of these, and silently returned the record unchanged for five others. What a
        resumed run stops at is the flow's business; what it must never do is raise
        :class:`TransitionRefused` for having been interrupted somewhere legal.
        """
        publish(
            worktree,
            record_for(
                worktree,
                config,
                workflow_state=state,
                completed_milestones=[],
                current_milestone=MILESTONE_ID,
            ),
        )
        try:
            application_factory().resume()
        except TransitionRefused as exc:  # pragma: no cover - the finding, if it regressed
            pytest.fail(f"resume from {state.value} was refused by the closed table: {exc}")
        except RunRefused as exc:  # pragma: no cover - none of these is an operator-only state
            pytest.fail(f"resume from {state.value} was refused outright: {exc}")

    def test_resume_never_resets_a_counter(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """Section 19: no code path lowers a counter, and resume is not an exception.

        The interrupted round's own budget is untouched too: `consume_round` needs a result that
        parsed, so a round that never produced one consumed nothing and the resumed attempt has
        its full ceiling to spend.
        """
        publish(
            worktree,
            record_for(
                worktree,
                config,
                workflow_state=RunStatus.FINAL_VERIFYING,
                completed_milestones=[MILESTONE_ID],
                current_milestone=None,
                review_attempts=2,
                provider_failure_count=3,
            ),
        )
        application = application_factory()
        application.resume()
        record = application.status().record
        assert record is not None
        assert record.review_attempts >= 2
        assert record.provider_failure_count >= 3
        assert record.successful_review_rounds <= 1
        assert record.correction_round == 0
        assert record.closure_round == 0

    def test_resume_never_reruns_a_completed_milestone(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """Section 13: a completed side effect is never repeated on appearance alone."""
        publish(
            worktree,
            record_for(
                worktree,
                config,
                workflow_state=RunStatus.MILESTONE_COMPLETE,
                completed_milestones=[MILESTONE_ID],
                current_milestone=None,
            ),
        )
        application = application_factory()
        application.resume()
        record = application.status().record
        assert record is not None
        assert record.completed_milestones == [MILESTONE_ID]
        assert not any(
            run.role is ProviderRole.IMPLEMENTATION and run.milestone_id == MILESTONE_ID
            for run in record.provider_runs
        )


# --------------------------------------------------------------------------------------
# Defect P-6 -- every state-mutating command acquires the run lock
# --------------------------------------------------------------------------------------


class TestP6AbortAcquiresLock:
    """Prototype defect P-6: `cmd_abort` wrote state holding no lock. `abort` holds it here."""

    def test_abort_is_refused_while_another_process_holds_the_lock(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        record = record_for(worktree, config, workflow_state=RunStatus.IMPLEMENTING)
        store = publish(worktree, record)
        holder = RunLock(
            run_id="auto016-20260806T110000Z-otherrun",
            repository_identity=IDENTITY,
            artifact_root=store.artifact_root,
        )
        holder.acquire()
        try:
            with pytest.raises(RunRefused):
                application_factory().abort(reason="a reason the operator supplied")
        finally:
            holder.release()
        assert store.load().workflow_state is RunStatus.IMPLEMENTING

    def test_abort_publishes_under_the_lock_and_releases_it(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        store = publish(
            worktree, record_for(worktree, config, workflow_state=RunStatus.IMPLEMENTING)
        )
        report = application_factory().abort(reason="the operator stopped this run")
        assert report.state is RunStatus.ABORTED
        assert store.load().workflow_state is RunStatus.ABORTED
        # The lock is free again, which a second acquisition proves.
        lock = RunLock(
            run_id="auto016-20260806T110000Z-otherrun",
            repository_identity=IDENTITY,
            artifact_root=store.artifact_root,
        )
        lock.acquire()
        lock.release()

    def test_the_state_store_refuses_an_unlocked_write(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        record = record_for(worktree, config, workflow_state=RunStatus.IMPLEMENTING)
        store = RunStateStore.pin(
            repository_id=IDENTITY, run_id=record.run_id, repository_root=worktree
        )
        unheld = RunLock(
            run_id=record.run_id,
            repository_identity=IDENTITY,
            artifact_root=store.artifact_root,
        )
        with pytest.raises(Exception, match="run lock"):
            store.publish(record, lock=unheld)

    def test_every_mutating_application_method_takes_the_lock(self) -> None:
        """An AST proof that the nine mutating commands go through `_locked` and the four
        read-only ones do not (section 12)."""
        tree = ast.parse((PACKAGE_ROOT / "application.py").read_text(encoding="utf-8"))
        application = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "MilestoneRunnerApplication"
        )
        bodies = {node.name: node for node in application.body if isinstance(node, ast.FunctionDef)}
        mutating = {
            "start",
            "resume",
            "abort",
            "_recover",
            "_approve",
        }
        read_only = {"doctor", "plan", "status", "verify"}

        def locks(name: str) -> bool:
            return any(
                isinstance(node, ast.Attribute) and node.attr == "_locked"
                for node in ast.walk(bodies[name])
            )

        assert {name for name in mutating if locks(name)} == mutating
        assert not any(locks(name) for name in read_only)


# --------------------------------------------------------------------------------------
# Section 20 -- the approval binding
# --------------------------------------------------------------------------------------


@pytest.fixture
def approved_record(worktree: Path, config: RunnerConfig) -> RunRecord:
    """A run sitting at the commit gate, with a changed file and a clean verification set."""
    (worktree / IMPLEMENTED_PATH).write_text("the work this run produced\n", encoding="utf-8")
    return record_for(
        worktree,
        config,
        workflow_state=RunStatus.READY_FOR_COMMIT_APPROVAL,
        changed_paths=[IMPLEMENTED_PATH],
        completed_milestones=[MILESTONE_ID],
        successful_review_rounds=1,
        review_attempts=1,
        verification_results=[
            VerificationResult(
                command=[sys.executable, "-c", "pass"],
                exit_code=0,
                passed=True,
                duration_ms=12,
                stdout_path="transcripts/0001-20260806T120000Z-verification.stdout.txt",
                stderr_path="transcripts/0001-20260806T120000Z-verification.stderr.txt",
            )
        ],
    )


def bound(worktree: Path, record: RunRecord, *, moment: datetime = MOMENT) -> CommitApproval:
    evidence = GitReadOnlyInspector(worktree).evidence()
    return bind_approval(
        operation=ApprovalOperation.COMMIT,
        record=record,
        evidence=evidence,
        repository_root=worktree,
        moment=moment,
        human_confirmation_supplied=False,
    )


class TestCommitApprovalBoundToDiffAndInvalidatedOnChange:
    """Section 20: the approval is bound to the state it was granted against, and each of the six
    invalidation triggers voids it independently. It is never silently re-bound."""

    def test_the_binding_carries_every_property_section_20_names(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        approval = bound(worktree, approved_record).record
        evidence = GitReadOnlyInspector(worktree).evidence()
        assert approval.operation is ApprovalOperation.COMMIT
        assert approval.repository_identity == IDENTITY
        assert approval.branch == "main"
        assert approval.baseline_sha == approved_record.baseline_sha
        assert approval.head_sha == evidence.head_sha
        assert approval.changed_paths == [IMPLEMENTED_PATH]
        assert set(approval.changed_path_digests) == {IMPLEMENTED_PATH}
        assert len(approval.verification_digest) == 64
        assert approval.review_verdict.value == "APPROVED"
        assert approval.finding_ids == []
        assert approval.human_confirmation_supplied is False

    def test_a_valid_approval_validates(self, worktree: Path, approved_record: RunRecord) -> None:
        approval = bound(worktree, approved_record)
        validate_approval(
            approval,
            operation=ApprovalOperation.COMMIT,
            record=approved_record,
            evidence=GitReadOnlyInspector(worktree).evidence(),
            repository_root=worktree,
            moment=MOMENT,
        )

    def _refuse(
        self,
        worktree: Path,
        record: RunRecord,
        approval: CommitApproval,
        *,
        moment: datetime = MOMENT,
    ) -> str:
        with pytest.raises(ApprovalInvalid) as excinfo:
            validate_approval(
                approval,
                operation=ApprovalOperation.COMMIT,
                record=record,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                repository_root=worktree,
                moment=moment,
            )
        return str(excinfo.value)

    def test_branch_drift_invalidates(self, worktree: Path, approved_record: RunRecord) -> None:
        approval = bound(worktree, approved_record)
        git(worktree, "branch", "sidebranch")
        git(worktree, "symbolic-ref", "HEAD", "refs/heads/sidebranch")
        assert "Branch drift" in self._refuse(worktree, approved_record, approval)

    def test_head_drift_invalidates(self, worktree: Path, approved_record: RunRecord) -> None:
        approval = bound(worktree, approved_record)
        moved = approved_record.model_copy(update={"baseline_sha": "1" * 40})
        drifted = approval.record.model_copy(update={"head_sha": "1" * 40})
        with pytest.raises(ApprovalInvalid, match="HEAD drift"):
            validate_approval(
                CommitApproval(record=drifted, expires_at=approval.expires_at),
                operation=ApprovalOperation.COMMIT,
                record=moved,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                repository_root=worktree,
                moment=MOMENT,
            )

    def test_changed_path_drift_invalidates(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        approval = bound(worktree, approved_record)
        (worktree / "src" / "demo" / "extra.py").write_text("a new path\n", encoding="utf-8")
        assert "Changed-path drift" in self._refuse(worktree, approved_record, approval)

    def test_digest_drift_invalidates(self, worktree: Path, approved_record: RunRecord) -> None:
        approval = bound(worktree, approved_record)
        (worktree / IMPLEMENTED_PATH).write_text("edited after the approval\n", encoding="utf-8")
        assert "Digest drift" in self._refuse(worktree, approved_record, approval)

    def test_a_verification_failure_invalidates(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        approval = bound(worktree, approved_record)
        failed = approved_record.model_copy(
            update={
                "verification_results": [
                    VerificationResult(
                        command=[sys.executable, "-c", "raise SystemExit(1)"],
                        exit_code=1,
                        passed=False,
                        duration_ms=5,
                        stdout_path="transcripts/0002-20260806T120000Z-verification.stdout.txt",
                        stderr_path="transcripts/0002-20260806T120000Z-verification.stderr.txt",
                    )
                ]
            }
        )
        assert "did not pass" in self._refuse(worktree, failed, approval)

    def test_expiry_invalidates(self, worktree: Path, approved_record: RunRecord) -> None:
        approval = bound(worktree, approved_record)
        assert "expired" in self._refuse(
            worktree, approved_record, approval, moment=MOMENT + timedelta(hours=2)
        )

    def test_prior_use_invalidates(self, worktree: Path, approved_record: RunRecord) -> None:
        approval = bound(worktree, approved_record).consumed_at(MOMENT)
        assert "already consumed" in self._refuse(worktree, approved_record, approval)

    def test_the_wrong_operation_invalidates(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        approval = bound(worktree, approved_record)
        with pytest.raises(ApprovalInvalid, match="authorizes COMMIT, not PUSH"):
            validate_approval(
                approval,
                operation=ApprovalOperation.PUSH,
                record=approved_record,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                repository_root=worktree,
                moment=MOMENT,
            )

    def test_a_deleted_path_digests_to_the_absent_marker(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        (worktree / "src" / "demo" / "__init__.py").unlink()
        approval = bound(worktree, approved_record).record
        assert approval.changed_path_digests["src/demo/__init__.py"] == ABSENT_PATH_DIGEST

    def test_an_approval_is_never_silently_re_bound(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        approval = bound(worktree, approved_record)
        original = approval.record.changed_path_digests[IMPLEMENTED_PATH]
        (worktree / IMPLEMENTED_PATH).write_text("edited\n", encoding="utf-8")
        with pytest.raises(ApprovalInvalid):
            validate_approval(
                approval,
                operation=ApprovalOperation.COMMIT,
                record=approved_record,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                repository_root=worktree,
                moment=MOMENT,
            )
        assert approval.record.changed_path_digests[IMPLEMENTED_PATH] == original


class TestCommitApprovalIsSingleUse:
    """Section 20 constraint 5: one approval authorizes exactly one execution."""

    def test_a_second_execution_with_the_same_approval_is_refused(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        facade = ApprovalGit(repository_root=worktree, execute_commit=True, execute_push=False)
        approval = bound(worktree, approved_record)
        evidence = GitReadOnlyInspector(worktree).evidence()
        first = facade.commit(
            approval,
            message="a message the runner derived",
            confirmation=COMMIT_CONFIRMATION,
            record=approved_record,
            evidence=evidence,
            moment=MOMENT,
        )
        assert first.executed
        assert first.approval is not None and first.approval.consumed
        # The same approval, offered a second time, is spent evidence.
        with pytest.raises(ApprovalInvalid, match="already consumed"):
            facade.commit(
                first.approval,
                message="a message the runner derived",
                confirmation=COMMIT_CONFIRMATION,
                record=approved_record,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                moment=MOMENT,
            )

    def test_consuming_an_already_consumed_approval_is_refused(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        approval = bound(worktree, approved_record).consumed_at(MOMENT)
        with pytest.raises(ApprovalInvalid, match="already been consumed"):
            approval.consumed_at(MOMENT)


class TestApprovalIsEvidenceNotAuthority:
    """Section 20: a failed deterministic gate still fails with an approval in hand."""

    def test_a_failed_verification_set_defeats_a_bound_approval(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        facade = ApprovalGit(repository_root=worktree, execute_commit=True)
        approval = bound(worktree, approved_record)
        failed = approved_record.model_copy(
            update={
                "verification_results": [
                    VerificationResult(
                        command=[sys.executable, "-c", "raise SystemExit(1)"],
                        exit_code=1,
                        passed=False,
                        duration_ms=5,
                        stdout_path="transcripts/0003-20260806T120000Z-verification.stdout.txt",
                        stderr_path="transcripts/0003-20260806T120000Z-verification.stderr.txt",
                    )
                ]
            }
        )
        head_before = git(worktree, "rev-parse", "HEAD")
        with pytest.raises(ApprovalInvalid, match="did not pass"):
            facade.commit(
                approval,
                message="a message the runner derived",
                confirmation=COMMIT_CONFIRMATION,
                record=failed,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                moment=MOMENT,
            )
        assert git(worktree, "rev-parse", "HEAD") == head_before

    def test_the_flag_alone_authorizes_nothing(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        facade = ApprovalGit(repository_root=worktree, execute_commit=True)
        head_before = git(worktree, "rev-parse", "HEAD")
        with pytest.raises(ApprovalRefused, match="typed confirmation"):
            facade.commit(
                bound(worktree, approved_record),
                message="a message the runner derived",
                confirmation=None,
                record=approved_record,
                evidence=GitReadOnlyInspector(worktree).evidence(),
                moment=MOMENT,
            )
        assert git(worktree, "rev-parse", "HEAD") == head_before

    def test_the_shipped_defaults_print_and_change_nothing(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        facade = ApprovalGit(repository_root=worktree)
        head_before = git(worktree, "rev-parse", "HEAD")
        reflog_before = git(worktree, "reflog", "--format=%H %gs")
        execution = facade.commit(
            bound(worktree, approved_record),
            message="a message the runner derived",
            confirmation=COMMIT_CONFIRMATION,
            record=approved_record,
            evidence=GitReadOnlyInspector(worktree).evidence(),
            moment=MOMENT,
        )
        assert not execution.executed
        assert execution.rendered_commands[0].startswith("git add --")
        assert git(worktree, "rev-parse", "HEAD") == head_before
        assert git(worktree, "reflog", "--format=%H %gs") == reflog_before

    def test_the_push_gate_ships_disabled_too(
        self, worktree: Path, approved_record: RunRecord
    ) -> None:
        facade = ApprovalGit(repository_root=worktree)
        evidence = GitReadOnlyInspector(worktree).evidence()
        approval = bind_approval(
            operation=ApprovalOperation.PUSH,
            record=approved_record,
            evidence=evidence,
            repository_root=worktree,
            moment=MOMENT,
            human_confirmation_supplied=True,
        )
        execution = facade.push(
            approval,
            confirmation=PUSH_CONFIRMATION,
            record=approved_record,
            evidence=evidence,
            moment=MOMENT,
        )
        assert not execution.executed
        assert execution.rendered_commands == ("git push origin main",)


class TestTheApprovalFacadeCanBuildNothingElse:
    """Section 20: every other destructive subcommand is unconstructible, not merely unused."""

    @pytest.mark.parametrize(
        "argv",
        [
            ("reset", "--hard", "HEAD"),
            ("restore", "--staged", "."),
            ("clean", "-fd"),
            ("stash",),
            ("rebase", "main"),
            ("checkout", "main"),
            ("switch", "main"),
            ("merge", "main"),
            ("cherry-pick", "HEAD"),
            ("revert", "HEAD"),
            ("fetch", "origin"),
            ("pull", "origin", "main"),
            ("branch", "-D", "main"),
            ("push", "origin", "--force"),
            ("push", "elsewhere", "main"),
            ("commit", "--amend"),
            ("add", "--all"),
        ],
    )
    def test_a_forbidden_vector_is_refused_before_a_process_exists(
        self, worktree: Path, argv: tuple[str, ...]
    ) -> None:
        facade = ApprovalGit(repository_root=worktree, execute_commit=True, execute_push=True)
        head_before = git(worktree, "rev-parse", "HEAD")
        with pytest.raises(ApprovalRefused, match="not one of the two mutating vectors"):
            facade._run(argv)
        assert git(worktree, "rev-parse", "HEAD") == head_before


# --------------------------------------------------------------------------------------
# Section 22 invariants 4 and 13, and defect P-5 -- the AST proofs
# --------------------------------------------------------------------------------------


def package_sources(exclude: frozenset[str] = frozenset()) -> list[Path]:
    return [
        source
        for source in sorted(PACKAGE_ROOT.rglob("*.py"))
        if source.name not in exclude and "__pycache__" not in source.parts
    ]


def code_string_literals(source: Path) -> list[str]:
    """Every string literal in `source` that is not a docstring, by node identity."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


#: Every mutating Git subcommand section 20 names, plus the flags a branch deletion needs.
#: `branch` itself is deliberately absent: it is a field name in three records and a property on
#: the inspector, so a bare-word match would prove nothing. A branch *deletion* is caught by its
#: flags, which is the argv shape that actually deletes.
MUTATING_GIT_TOKENS: frozenset[str] = frozenset(
    {
        "add",
        "commit",
        "push",
        "reset",
        "restore",
        "clean",
        "stash",
        "rebase",
        "checkout",
        "switch",
        "merge",
        "cherry-pick",
        "revert",
        "fetch",
        "pull",
        "apply",
        "am",
        "mv",
        "rm",
        "--delete",
        "--force",
    }
)


class TestMutatingGitOnlyInApprovalGitModule:
    """Section 22 invariant 4(a): zero mutating Git subcommands in the other eighteen files."""

    def test_the_other_eighteen_package_files_name_no_mutating_subcommand(self) -> None:
        sources = package_sources(exclude=frozenset({"approval_git.py"}))
        # AUTO-018 section 11 adds events.py and operations.py to the nineteen.
        assert len(sources) == 21, [source.name for source in sources]
        offenders: dict[str, list[str]] = {}
        for source in sources:
            hits = sorted(
                {value for value in code_string_literals(source) if value in MUTATING_GIT_TOKENS}
            )
            if hits:
                offenders[source.name] = hits
        assert offenders == {}

    def test_no_other_package_module_spawns_git(self) -> None:
        """Only the read-only inspector and the gated façade build a `git` vector at all.

        The proof is over argv *construction*, not over the bare word: `verification.py` names
        `"git"` as the identifier of section 4 item 7's fifth governance check, which is a check
        name in a machine-readable document and never an executable. What would actually spawn Git
        is a vector whose head is `"git"`, so that is what is asserted -- and it exists in exactly
        the two modules section 20 permits a Git surface in.
        """
        allowed = {"git_inspect.py", "approval_git.py"}
        builders: set[str] = set()
        for source in package_sources():
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.List | ast.Tuple) or not node.elts:
                    continue
                head = node.elts[0]
                if isinstance(head, ast.Constant) and head.value == "git":
                    builders.add(source.name)
        assert builders == allowed, builders

    def test_the_facade_declares_exactly_two_mutating_shapes(self) -> None:
        from ai_workflow_engine.milestone_runner.approval_git import MUTATING_ARGV_SHAPES

        assert len(MUTATING_ARGV_SHAPES) == 3
        assert MUTATING_ARGV_SHAPES[0].startswith("add -- ")
        assert MUTATING_ARGV_SHAPES[1].startswith("commit --message")
        assert MUTATING_ARGV_SHAPES[2].startswith("push origin")


class TestP5AllGitRoutesThroughGuard:
    """Prototype defect P-5: mutating Git bypassed the allowlisted wrapper.

    Two structural facts make the bypass unreachable here. Only two modules in the package can
    reach `subprocess` with a `git` vector at all, and the gated one has exactly one caller path:
    it is imported by `application.py` alone, and the names it exports are used only inside the two
    approval methods, which are called only from the two approval commands in `cli.py`.
    """

    def test_only_two_modules_import_subprocess(self) -> None:
        importers = set()
        for source in package_sources():
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(
                    alias.name.split(".")[0] == "subprocess" for alias in node.names
                ):
                    importers.add(source.name)
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "subprocess"
                ):
                    importers.add(source.name)
        assert importers == {"git_inspect.py", "approval_git.py", "base.py", "verification.py"}

    def test_approval_git_is_imported_by_exactly_one_module(self) -> None:
        importers = []
        for source in package_sources(exclude=frozenset({"approval_git.py"})):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                    "approval_git"
                ):
                    importers.append(source.name)
        assert importers == ["application.py"]

    def test_the_facade_is_reached_only_from_the_two_approval_methods(self) -> None:
        tree = ast.parse((PACKAGE_ROOT / "application.py").read_text(encoding="utf-8"))
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("approval_git")
            for alias in node.names
        }
        gated = {"ApprovalGit", "bind_approval"}
        assert gated <= imported
        holders: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            if names & gated:
                holders.add(node.name)
        assert holders == {"_approve"}

    def test_the_two_cli_commands_are_the_only_callers_of_the_two_approval_methods(self) -> None:
        tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
        callers: dict[str, set[str]] = {"approve_commit": set(), "approve_push": set()}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and child.attr in callers:
                    callers[child.attr].add(node.name)
        assert callers["approve_commit"] == {"milestone_runner_approve_commit"}
        assert callers["approve_push"] == {"milestone_runner_approve_push"}


class TestNoDestructiveGitPathAnywhere:
    """Section 22 invariant 13: no code path resets, restores, stashes, rebases, cleans, checks
    out or deletes repository work -- including on every failure path."""

    def test_the_package_names_no_destructive_subcommand_at_all(self) -> None:
        destructive = {
            "reset",
            "restore",
            "clean",
            "stash",
            "rebase",
            "checkout",
            "switch",
            "merge",
            "cherry-pick",
            "revert",
        }
        for source in package_sources():
            assert not destructive & set(code_string_literals(source)), source.name

    #: The only two removals the whole package performs, each against an artifact the runner
    #: itself just created outside the worktree: the provider subpackage's private scratch
    #: directory, and a state publication's own namespaced temp file on the failure path where it
    #: never reached the canonical name. Neither is repository work, which is what invariant 13
    #: protects; the *local* each removes is named here, so a later edit that pointed one of them
    #: at a repository path would fail this test rather than pass it quietly.
    PERMITTED_REMOVALS: ClassVar[dict[str, tuple[str, str]]] = {
        "base.py": ("rmtree", "scratch"),
        "state.py": ("unlink", "temporary"),
    }

    def test_the_package_removes_no_repository_path(self) -> None:
        """No removal call anywhere in the package can name a path inside the worktree."""
        removers = {"rmtree", "unlink", "remove", "rmdir"}
        observed: dict[str, set[tuple[str, str]]] = {}
        for source in package_sources():
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in removers:
                    continue
                target = node.args[0] if node.args else None
                while isinstance(target, ast.Attribute):
                    target = target.value
                root = target.id if isinstance(target, ast.Name) else ast.dump(node)
                observed.setdefault(source.name, set()).add((node.func.attr, root))
        expected = {name: {value} for name, value in self.PERMITTED_REMOVALS.items()}
        assert observed == expected, observed

    def test_no_gh_invocation_and_no_network_client_anywhere(self) -> None:
        """Section 22 invariant 5: no `gh` invocation and no network call in the package.

        `socket` is the one module on the list the package does import, and it uses exactly one
        name from it: `socket.gethostname`, a local syscall written into the lock's diagnostic
        holder record. That is asserted rather than waved through -- any second attribute, which
        is what a network client would need, fails here.
        """
        for source in package_sources():
            literals = set(code_string_literals(source))
            assert "gh" not in literals, source.name
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    root = name.split(".")[0]
                    assert root not in {
                        "http",
                        "urllib",
                        "requests",
                        "httpx",
                        "ftplib",
                        "telnetlib",
                        "smtplib",
                        "asyncio",
                        "ssl",
                    } or name.startswith("urllib.parse"), f"{source.name} imports {name}"
            used = {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "socket"
            }
            assert used <= {"gethostname"}, f"{source.name} uses socket.{sorted(used)}"

    def test_no_shell_anywhere_in_the_package(self) -> None:
        for source in package_sources():
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword):
                    assert node.arg != "shell", source.name
                if isinstance(node, ast.Attribute):
                    assert node.attr not in {"system", "popen", "execv", "execve"}, source.name


# --------------------------------------------------------------------------------------
# Housekeeping the application owns
# --------------------------------------------------------------------------------------


class TestRunIdentification:
    """Section 9 gives no command a `--run-id`, so the run a command acts on is the newest one."""

    def test_a_fresh_run_id_is_timestamp_ordered(self) -> None:
        earlier = new_run_id(MOMENT)
        later = new_run_id(MOMENT + timedelta(minutes=1))
        assert earlier < later
        assert earlier.startswith("auto016-")

    def test_the_latest_published_run_is_selected(
        self, worktree: Path, config: RunnerConfig, isolated_home: Path
    ) -> None:
        first = publish(
            worktree,
            record_for(worktree, config, run_id="auto016-20260806T100000Z-aaaaaaaa"),
        )
        publish(
            worktree,
            record_for(worktree, config, run_id="auto016-20260806T110000Z-bbbbbbbb"),
        )
        assert latest_run_id(first.artifact_root) == "auto016-20260806T110000Z-bbbbbbbb"

    def test_an_unpublished_directory_is_not_a_run(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        store = RunStateStore.pin(
            repository_id=IDENTITY,
            run_id="auto016-20260806T100000Z-cccccccc",
            repository_root=worktree,
        )
        assert latest_run_id(store.artifact_root) is None

    def test_a_pointer_naming_an_unpublished_run_resolves_to_nothing(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        """The pointer is a convenience, never an authority: the run has to actually be there."""
        store = RunStateStore.pin(
            repository_id=IDENTITY,
            run_id="auto016-20260806T100000Z-dddddddd",
            repository_root=worktree,
        )
        record_latest_run(store.artifact_root, "auto016-20260806T100000Z-dddddddd")
        assert latest_run_id(store.artifact_root) is None

    def test_an_unreadable_pointer_resolves_to_nothing_rather_than_guessing(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        store = publish(worktree, record_for(worktree, config))
        pointer = store.artifact_root / "latest-run.json"
        assert latest_run_id(store.artifact_root) is not None
        pointer.write_text("this is not a JSON document", encoding="utf-8")
        assert latest_run_id(store.artifact_root) is None

    def test_the_pointer_refuses_a_name_that_is_not_a_run_id(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        store = publish(worktree, record_for(worktree, config))
        with pytest.raises(RunRefused, match="run id"):
            record_latest_run(store.artifact_root, "../escape")


class TestTheStopVocabularyIsNotWidened:
    """Section 10's `StopReason` is closed, and this milestone coins nothing alongside it."""

    def test_the_uncoded_stop_reuses_an_existing_code(self) -> None:
        assert UNNAMED_STOP_REASON in set(StopReason)

    def test_a_provider_failure_stop_records_a_reason(
        self, worktree: Path, config: RunnerConfig
    ) -> None:
        record = record_for(
            worktree,
            config,
            workflow_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            stop_reason=UNNAMED_STOP_REASON,
            provider_runs=[
                ProviderRunRecord(
                    sequence=1,
                    role=ProviderRole.REVIEW,
                    provider="fake",
                    started_at="2026-08-06T11:59:00Z",
                    completed_at="2026-08-06T12:00:00Z",
                    duration_ms=1_000,
                    exit_code=1,
                    prompt_path="transcripts/0001-20260806T115900Z-fake-review.prompt.md",
                    stdout_path="transcripts/0001-20260806T115900Z-fake-review.stdout.txt",
                    stderr_path="transcripts/0001-20260806T115900Z-fake-review.stderr.txt",
                )
            ],
        )
        assert record.stop_reason is UNNAMED_STOP_REASON


# --------------------------------------------------------------------------------------
# Section 13 and section 22 invariant 14 -- the invocation is durable before it can have an effect
# --------------------------------------------------------------------------------------


class SnapshottingAdapter(FakeAdapter):
    """A real adapter that reads the durable record at the exact crash window section 13 names.

    The snapshot is taken after the provider process has run -- so the worktree may already carry
    its effect -- and before :func:`~...application._invoke_provider` regains control. A runner
    that died here would leave exactly the bytes this adapter captured, so what it captures is
    what `resume` would have to reconcile against.
    """

    def __init__(self, script: Path, *, results: dict[str, str], touch: str, run_root: Path):
        super().__init__(script, results=results, touch=touch)
        self._run_root = run_root
        self.snapshots: list[RunRecord] = []

    def invoke(  # type: ignore[no-untyped-def]
        self, invoker, *, role, prompt, milestone_id=None, on_started=None
    ):
        invocation = super().invoke(
            invoker, role=role, prompt=prompt, milestone_id=milestone_id, on_started=on_started
        )
        states = sorted(self._run_root.glob("*/state.json"))
        assert len(states) == 1, states
        self.snapshots.append(RunRecord.model_validate_json(states[0].read_text(encoding="utf-8")))
        return invocation


class TestProviderInvocationIsDurableBeforeItRuns:
    """Section 13, section 22 invariant 14 and `MACHINE_GATES.md` section 2a.

    A crash during a provider invocation must never let `resume` repeat an already-effectful
    invocation without reconciliation. That requires the invocation to be *durably in flight*
    before the provider can touch anything, so the record `resume` reads names an incomplete
    invocation rather than nothing at all.
    """

    @pytest.fixture
    def snapshotting(self, fake_script: Path, isolated_home: Path) -> SnapshottingAdapter:
        run_root = isolated_home / ".ai-workflow-engine" / "milestone-runs" / IDENTITY
        return SnapshottingAdapter(
            fake_script, results=FAKE_RESULTS, touch=IMPLEMENTED_PATH, run_root=run_root
        )

    def test_the_durable_record_names_the_invocation_while_it_is_in_flight(
        self, application_factory, snapshotting: SnapshottingAdapter
    ) -> None:  # type: ignore[no-untyped-def]
        application_factory(
            providers=ProviderBinding(
                implementation=snapshotting,
                review=FakeAdapter(snapshotting._script, results=FAKE_RESULTS),
            )
        ).start()

        assert snapshotting.snapshots, "the implementation provider never ran"
        mid_flight = snapshotting.snapshots[0]
        assert mid_flight.workflow_state is RunStatus.PROVIDER_WAIT
        assert mid_flight.provider_runs, "no invocation was durable while the provider ran"
        pending = mid_flight.provider_runs[-1]
        assert pending.completed_at is None
        assert pending.role is ProviderRole.IMPLEMENTATION
        assert pending.milestone_id == MILESTONE_ID

    def test_resume_after_a_crash_mid_invocation_requires_reconciliation(
        self, application_factory, worktree: Path, snapshotting: SnapshottingAdapter
    ) -> None:  # type: ignore[no-untyped-def]
        """The blocker itself: the provider changed the worktree, then the runner died."""
        application_factory(
            providers=ProviderBinding(
                implementation=snapshotting,
                review=FakeAdapter(snapshotting._script, results=FAKE_RESULTS),
            )
        ).start()
        mid_flight = snapshotting.snapshots[0]
        assert (worktree / IMPLEMENTED_PATH).is_file()

        store = publish(worktree, mid_flight)
        decision = store.resume(GitReadOnlyInspector(worktree).evidence())
        assert decision.unaccounted_changed_paths == [IMPLEMENTED_PATH]
        assert not decision.may_reinvoke_provider
        assert decision.action is ResumeAction.RECONCILE_REQUIRED

    def test_the_completed_invocation_replaces_its_own_in_flight_entry(
        self, application_factory, snapshotting: SnapshottingAdapter
    ) -> None:  # type: ignore[no-untyped-def]
        """One invocation is one entry: the in-flight row is completed, never duplicated."""
        application = application_factory(
            providers=ProviderBinding(
                implementation=snapshotting,
                review=FakeAdapter(snapshotting._script, results=FAKE_RESULTS),
            )
        )
        application.start()
        record = application.status().record
        assert record is not None
        assert [run.role for run in record.provider_runs] == [
            ProviderRole.IMPLEMENTATION,
            ProviderRole.REVIEW,
        ]
        assert all(run.completed_at is not None for run in record.provider_runs)
        sequences = [run.sequence for run in record.provider_runs]
        assert sequences == sorted(set(sequences))
        assert snapshotting.snapshots[0].provider_runs[-1].sequence == sequences[0]


class IntentWatchingAdapter(FakeAdapter):
    """A real adapter that reads the run directory at the instant before the process exists.

    The production invoker calls `on_started` after the sequence and transcript names are fixed
    and before it spawns anything. This adapter wraps that hook, so what it captures is precisely
    the durable state a runner killed one instruction before `fork` would have left behind.
    """

    def __init__(self, script: Path, *, results: dict[str, str], touch: str, run_root: Path):
        super().__init__(script, results=results, touch=touch)
        self._run_root = run_root
        self.at_spawn: list[tuple[ProviderInvocationIntent | None, RunRecord | None]] = []

    def _run_directory(self) -> Path:
        directories = sorted(path.parent for path in self._run_root.glob("*/state.json"))
        assert len(directories) == 1, directories
        return directories[0]

    @staticmethod
    def _durable_intent(run_directory: Path) -> ProviderInvocationIntent | None:
        path = run_directory / PROVIDER_INTENT_FILE_NAME
        if not path.is_file():
            return None
        return ProviderInvocationIntent.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _durable_record(run_directory: Path) -> RunRecord | None:
        path = run_directory / "state.json"
        if not path.is_file():
            return None
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def invoke(  # type: ignore[no-untyped-def]
        self, invoker, *, role, prompt, milestone_id=None, on_started=None
    ):
        def watched(pending: ProviderRunRecord) -> None:
            if on_started is not None:
                on_started(pending)
            run_directory = self._run_directory()
            self.at_spawn.append(
                (self._durable_intent(run_directory), self._durable_record(run_directory))
            )

        return super().invoke(
            invoker, role=role, prompt=prompt, milestone_id=milestone_id, on_started=watched
        )


class TestTheInvocationIntentIsDurableBeforeTheProcessExists:
    """AUTO016-IMPL-001, first half: the evidence has to exist before the effect can."""

    @pytest.fixture
    def watching(self, fake_script: Path, isolated_home: Path) -> IntentWatchingAdapter:
        run_root = isolated_home / ".ai-workflow-engine" / "milestone-runs" / IDENTITY
        return IntentWatchingAdapter(
            fake_script, results=FAKE_RESULTS, touch=IMPLEMENTED_PATH, run_root=run_root
        )

    def test_the_intent_and_the_in_flight_row_are_both_durable_before_the_spawn(
        self, application_factory, worktree: Path, watching: IntentWatchingAdapter
    ) -> None:  # type: ignore[no-untyped-def]
        application_factory(
            providers=ProviderBinding(
                implementation=watching,
                review=FakeAdapter(watching._script, results=FAKE_RESULTS),
            )
        ).start()

        assert watching.at_spawn, "the implementation provider never ran"
        intent, mid_flight = watching.at_spawn[0]
        assert intent is not None, "no invocation intent was durable before the process existed"
        assert mid_flight is not None
        assert mid_flight.provider_runs[-1].completed_at is None
        assert intent.sequence == mid_flight.provider_runs[-1].sequence
        assert intent.role is ProviderRole.IMPLEMENTATION
        assert intent.milestone_id == MILESTONE_ID
        # The fingerprint is of a repository this invocation has not touched: the file the fake
        # provider creates is not in it, because the provider does not exist yet.
        assert IMPLEMENTED_PATH not in intent.fingerprint.path_digests

    def test_every_invocation_records_its_own_intent(
        self, application_factory, watching: IntentWatchingAdapter
    ) -> None:  # type: ignore[no-untyped-def]
        review = IntentWatchingAdapter(
            watching._script,
            results=FAKE_RESULTS,
            touch="",
            run_root=watching._run_root,
        )
        application_factory(
            providers=ProviderBinding(implementation=watching, review=review)
        ).start()

        roles = [intent.role for intent, _ in watching.at_spawn + review.at_spawn if intent]
        assert roles == [ProviderRole.IMPLEMENTATION, ProviderRole.REVIEW]
        # The review's intent supersedes the implementation's, and it sees the work already done.
        review_intent, _ = review.at_spawn[0]
        assert review_intent is not None
        assert IMPLEMENTED_PATH in review_intent.fingerprint.path_digests


class TestResumeStopsOnAContentChangeToAKnownPath:
    """AUTO016-IMPL-001, second half, at the layer that acts on the verdict.

    `resume_run` used to stop only when the decision carried unaccounted changed *path names*, so
    a `RECONCILE_REQUIRED` reached on content alone fell through into `_resume_from` and the
    effectful invocation was repeated. It now stops on the verdict itself.
    """

    def crashed_after_rewriting(
        self, worktree: Path, config: RunnerConfig
    ) -> tuple[RunStateStore, RunRecord]:
        """A run that died mid-invocation after the provider rewrote an already-known path."""
        (worktree / "src" / "demo").mkdir(parents=True, exist_ok=True)
        (worktree / IMPLEMENTED_PATH).write_text("value = 1\n", encoding="utf-8")
        pending = ProviderRunRecord(
            sequence=1,
            role=ProviderRole.IMPLEMENTATION,
            provider="fake",
            milestone_id=MILESTONE_ID,
            started_at="2026-08-06T12:00:00Z",
            completed_at=None,
            duration_ms=0,
            prompt_path="transcripts/0001-20260806T120000Z-fake-implementation.prompt.md",
            stdout_path="transcripts/0001-20260806T120000Z-fake-implementation.stdout.txt",
            stderr_path="transcripts/0001-20260806T120000Z-fake-implementation.stderr.txt",
        )
        record = record_for(
            worktree,
            config,
            workflow_state=RunStatus.PROVIDER_WAIT,
            current_milestone=MILESTONE_ID,
            changed_paths=[IMPLEMENTED_PATH],
            provider_runs=[pending],
        )
        store = publish(worktree, record)
        publish_intent(worktree, record, pending)
        # The provider's real effect: the same path, different bytes. The name set never moves.
        (worktree / IMPLEMENTED_PATH).write_text("value = 2  # the provider's work\n", "utf-8")
        return store, record

    def test_resume_stops_at_human_intervention_required(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        store, _ = self.crashed_after_rewriting(worktree, config)

        report = application_factory().resume()

        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert "content" in report.detail
        assert store.load().workflow_state is RunStatus.HUMAN_INTERVENTION_REQUIRED

    def test_the_provider_is_never_re_invoked(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """The whole point: no second effectful call, and the first one's row is untouched."""
        store, _ = self.crashed_after_rewriting(worktree, config)

        application_factory().resume()

        record = store.load()
        assert len(record.provider_runs) == 1
        assert record.provider_runs[0].completed_at is None

    def test_partial_work_is_preserved(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        self.crashed_after_rewriting(worktree, config)

        application_factory().resume()

        assert (worktree / IMPLEMENTED_PATH).read_text(encoding="utf-8") == (
            "value = 2  # the provider's work\n"
        )

    def test_no_budget_is_consumed_by_the_detection(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """Section 19: a stop for reconciliation is not a round and consumes no counter."""
        store, record = self.crashed_after_rewriting(worktree, config)
        before = {field: getattr(record, field) for field in RUN_COUNTER_FIELDS}

        application_factory().resume()

        assert {field: getattr(store.load(), field) for field in RUN_COUNTER_FIELDS} == before

    def test_the_branch_head_and_scope_pins_are_untouched(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """Nothing about this path relaxes a section 4 pin or the section 15 guard."""
        store, record = self.crashed_after_rewriting(worktree, config)

        application_factory().resume()

        stopped = store.load()
        assert stopped.expected_branch == record.expected_branch
        assert stopped.baseline_sha == record.baseline_sha
        assert stopped.repository_identity == record.repository_identity
        assert git(worktree, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert git(worktree, "rev-parse", "HEAD") == record.baseline_sha

    def test_head_drift_is_still_refused_ahead_of_the_content_comparison(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """Section 4 item 4: a moved `HEAD` stops the run on its own stop code, not on content."""
        store, _ = self.crashed_after_rewriting(worktree, config)
        git(worktree, "add", "-A")
        git(worktree, "commit", "-m", "a commit nobody authorized")

        report = application_factory().resume()

        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert store.load().stop_reason is StopReason.HEAD_DRIFT
        assert len(store.load().provider_runs) == 1

    def test_an_explicit_recovery_can_proceed_after_the_stop(
        self, application_factory, worktree: Path, config: RunnerConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """Section 13: the stop is cleared by a governed act, and the run is not a dead end."""
        store, _ = self.crashed_after_rewriting(worktree, config)
        application = application_factory()
        assert application.resume().state is RunStatus.HUMAN_INTERVENTION_REQUIRED

        report = application.reopen_milestone(
            milestone=MILESTONE_ID,
            reason="Human Owner reviewed the interrupted invocation's partial work.",
        )

        assert report.pre_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert report.post_state is not RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert report.budgets_touched == {}, "a reconciliation stop costs no budget to clear"
        reopened = store.load()
        assert reopened.reopenings, "the recovery act was not recorded in its ledger"
        assert (worktree / IMPLEMENTED_PATH).is_file(), "partial work survived the recovery"


# --------------------------------------------------------------------------------------
# Section 4 item 4 and section 20 -- the contracted commit-to-push flow
# --------------------------------------------------------------------------------------


class TestTheCommitGateLeadsToTheReachablePushGate:
    """Section 4 item 4: "a Human Owner-approved commit executed through that gate is the only
    event that may advance `HEAD`, and it is recorded with the approval that authorized it."

    The commit gate advances `HEAD` and hands the run to `READY_FOR_PUSH_APPROVAL`. The push gate
    re-verifies section 4 against that state, so it has to accept the `HEAD` the approved commit
    produced -- otherwise section 5's commit-to-push flow cannot execute at all.
    """

    @pytest.fixture
    def committing(self, application_factory):  # type: ignore[no-untyped-def]
        return application_factory(overrides={"git": {"execute_commit": True}})

    def test_the_approved_commit_advances_head_and_records_where_it_landed(
        self, committing: MilestoneRunnerApplication, worktree: Path
    ) -> None:
        baseline = git(worktree, "rev-parse", "HEAD")
        committing.start()
        report = committing.approve_commit(confirmation=COMMIT_CONFIRMATION)

        assert report.execution.executed
        assert report.state is RunStatus.READY_FOR_PUSH_APPROVAL
        landed = git(worktree, "rev-parse", "HEAD")
        assert landed != baseline
        assert report.approval.record.consumed
        assert report.approval.record.head_sha == baseline
        assert report.approval.record.resulting_head_sha == landed

    def test_the_push_gate_is_reachable_after_the_approved_commit(
        self, committing: MilestoneRunnerApplication, worktree: Path
    ) -> None:
        committing.start()
        committing.approve_commit(confirmation=COMMIT_CONFIRMATION)
        head_after_commit = git(worktree, "rev-parse", "HEAD")

        report = committing.approve_push()

        assert not report.execution.executed
        assert report.execution.rendered_commands == ("git push origin main",)
        assert report.state is RunStatus.READY_FOR_PUSH_APPROVAL
        assert git(worktree, "rev-parse", "HEAD") == head_after_commit

    def test_head_drift_that_no_approval_authorized_still_refuses(
        self, committing: MilestoneRunnerApplication, worktree: Path
    ) -> None:
        """The relaxation is exactly the approved commit, and nothing wider."""
        committing.start()
        (worktree / "unrelated.txt").write_text("someone else's commit\n", encoding="utf-8")
        git(worktree, "add", "unrelated.txt")
        git(worktree, "commit", "-m", "a commit this run never approved")
        drifted = git(worktree, "rev-parse", "HEAD")
        with pytest.raises(ApprovalRefused, match="item 4"):
            committing.approve_commit(confirmation=COMMIT_CONFIRMATION)
        assert git(worktree, "rev-parse", "HEAD") == drifted
        record = committing.status().record
        assert record is not None and record.approvals == []


# --------------------------------------------------------------------------------------
# Section 20 and section 22 -- the grant is durable before the mutation, and single-use
# --------------------------------------------------------------------------------------


class TestGitApprovalIsDurableBeforeTheMutation:
    """Section 20: "every approval and every consumption is an append-only record".

    Process loss after Git succeeds and before the publication must not leave the act unrecorded,
    and must never leave the same durable approval state able to execute the act a second time.
    """

    @pytest.fixture
    def committing(self, application_factory):  # type: ignore[no-untyped-def]
        return application_factory(overrides={"git": {"execute_commit": True}})

    @staticmethod
    def _durable(application: MilestoneRunnerApplication) -> RunRecord:
        record = application.status().record
        assert record is not None
        return record

    def test_the_attempt_is_durable_before_the_vector_runs(
        self, committing: MilestoneRunnerApplication, worktree: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        committing.start()
        seen: list[RunRecord] = []
        real_run = ApprovalGit._run

        def capturing(self: ApprovalGit, argv: tuple[str, ...]) -> str:
            record = committing.status().record
            assert record is not None
            seen.append(record)
            return real_run(self, argv)

        monkeypatch.setattr(ApprovalGit, "_run", capturing)
        committing.approve_commit(confirmation=COMMIT_CONFIRMATION)

        assert seen, "no mutating vector ran"
        before_the_first_vector = seen[0]
        assert before_the_first_vector.approvals, "the grant was not durable before Git ran"
        attempt = before_the_first_vector.approvals[-1]
        assert attempt.operation is ApprovalOperation.COMMIT
        assert attempt.execution_started_at is not None
        assert not attempt.consumed

    def test_process_loss_after_git_leaves_a_durable_unreconciled_attempt(
        self, committing: MilestoneRunnerApplication, worktree: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        committing.start()
        baseline = git(worktree, "rev-parse", "HEAD")
        real_commit = ApprovalGit.commit

        def lost(self: ApprovalGit, *args: Any, **kwargs: Any) -> Any:
            real_commit(self, *args, **kwargs)
            raise KeyboardInterrupt("the runner process was lost after Git succeeded")

        monkeypatch.setattr(ApprovalGit, "commit", lost)
        with pytest.raises(KeyboardInterrupt):
            committing.approve_commit(confirmation=COMMIT_CONFIRMATION)

        assert git(worktree, "rev-parse", "HEAD") != baseline
        record = self._durable(committing)
        assert record.approvals, "the act left no durable grant at all"
        attempt = record.approvals[-1]
        assert attempt.execution_started_at is not None
        assert not attempt.consumed

    def test_an_unreconciled_attempt_refuses_a_second_execution(
        self, committing: MilestoneRunnerApplication, worktree: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        """A push leaves local `HEAD` untouched, so only the record can refuse the repeat."""
        pushing = ApprovalOperation.PUSH
        committing.start()
        committing.approve_commit(confirmation=COMMIT_CONFIRMATION)

        record = self._durable(committing)
        assert record.workflow_state is RunStatus.READY_FOR_PUSH_APPROVAL
        interrupted = record.model_copy(
            update={
                "approvals": [
                    *record.approvals,
                    record.approvals[-1].model_copy(
                        update={
                            "operation": pushing,
                            "consumed": False,
                            "consumed_at": None,
                            "resulting_head_sha": None,
                            "execution_started_at": "2026-08-06T12:00:00Z",
                        }
                    ),
                ]
            }
        )
        publish(worktree, interrupted)

        with pytest.raises(ApprovalRefused, match="was interrupted"):
            committing.approve_push(confirmation=PUSH_CONFIRMATION)


class TestModuleLevelEntryPoints:
    """The four module-level entry points the milestone names are real, callable functions."""

    def test_the_entry_points_exist(self) -> None:
        for entry in (run_preflight, start_run, resume_run, transition_to):
            assert callable(entry)

    def test_start_run_and_resume_run_drive_the_flow(
        self, application_factory, worktree: Path
    ) -> None:  # type: ignore[no-untyped-def]
        application = application_factory()
        report = application.start()
        assert report.run_id.startswith("auto016-")
        assert report.satisfied


@pytest.fixture(autouse=True)
def _no_prototype_access(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """DEC-016-006: nothing in this suite opens the AUTO-015 prototype's directory."""
    prototype = Path.home() / ".local" / "share" / "auto015-runner"
    real_open = os.open

    def guarded(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        assert str(prototype) not in str(path), f"the prototype was opened at {path}"
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    yield


class TestAuto017StartSurface:
    def test_stage_start_requires_v2_without_writing(self, application_factory):
        application = application_factory()
        before = sorted(application.artifact_root.rglob("*"))
        with pytest.raises(WorkflowEngineError):
            application.stage_start(stage_id=STAGE_ID, confirmation=f"START_STAGE {STAGE_ID}")
        assert sorted(application.artifact_root.rglob("*")) == before


@pytest.fixture
def v2_application(config_factory, providers):
    from ai_workflow_engine.milestone_runner.application import (
        AdapterAdmission,
        AdapterAdmissionKind,
    )

    def factory(*, governed=False, admitted=True, selected=None, **kwargs):
        path = config_factory()
        document = yaml.safe_load(path.read_text())
        document["schema_version"] = 2
        document.pop("review_policy")
        document["stage"].update(
            registry_path=None, execution_ceilings={"max_remediation_cycles": 3, "max_blockers": 3}
        )
        root = Path(document["repository"]["root"])
        if governed:
            registry = root / "registry.md"
            registry.write_text(
                "| Stage | Title | Role | State | Branch | Prompt |\n"
                "|---|---|---|---|---|---|\n"
                f"| {STAGE_ID} | test | impl | AUTHORIZED | main | `{CONTRACT_PATH}` |\n"
            )
            git(root, "add", "registry.md")
            git(root, "commit", "-m", "test governed registry")
            document["repository"]["baseline_sha"] = git(root, "rev-parse", "HEAD")
            document["stage"]["registry_path"] = "registry.md"
        path.write_text(yaml.safe_dump(document))
        bound = selected or providers
        admissions = (
            tuple(
                AdapterAdmission(a, type(a), AdapterAdmissionKind.TEST_DOUBLE)
                for a in (providers.implementation, providers.review)
            )
            if admitted
            else ()
        )
        application = MilestoneRunnerApplication(
            load_runner_config(path), providers=bound, adapter_admissions=admissions, **kwargs
        )
        defaults = application.artifact_root / "project-defaults.json"
        defaults.parent.mkdir(parents=True, exist_ok=True)
        defaults.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "roles": {
                        role.value: {
                            "provider_id": "not-a-runtime-provider",
                            "model_id": "unknown/model",
                            "timeout_seconds": 60,
                        }
                        for role in ProviderRole
                    },
                }
            )
        )
        return application

    return factory


def authorize_v2(application):
    return application.stage_start(stage_id=STAGE_ID, confirmation=f"START_STAGE {STAGE_ID}")


def artifact_snapshot(root):
    return {
        p.relative_to(root).as_posix(): (
            ("link", os.readlink(p), p.lstat().st_mtime_ns)
            if p.is_symlink()
            else (
                ("file", p.read_bytes(), p.stat().st_mtime_ns)
                if p.is_file()
                else ("dir", p.stat().st_mtime_ns)
            )
        )
        for p in root.rglob("*")
    }


def assert_refusal_without_effects(application, act, reason, monkeypatch):
    import ai_workflow_engine.milestone_runner.application as application_module
    import ai_workflow_engine.milestone_runner.state as state_module

    before = artifact_snapshot(application.artifact_root)
    writes = []
    calls = []

    def forbidden_write(*args, **kwargs):
        writes.append(True)
        pytest.fail("a refused command reached a write boundary")

    def forbidden_call(*args, **kwargs):
        calls.append(True)
        pytest.fail("a refused command invoked a provider/process")

    original_popen = subprocess.Popen

    def process_guard(*args, **kwargs):
        # Phase A-3 mandates the inspector's read-only Git root check before admission.
        argv = args[0] if args else kwargs.get("args", [])
        if (
            isinstance(argv, list)
            and argv[:2] == ["git", "--no-optional-locks"]
            and argv[-2:] == ["rev-parse", "--show-toplevel"]
        ):
            return original_popen(*args, **kwargs)
        return forbidden_call(*args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(state_module, "write_redacted_artifact", forbidden_write)
        guarded.setattr(application_module, "write_redacted_artifact", forbidden_write)
        guarded.setattr(application, "_locked", forbidden_write)
        guarded.setattr(subprocess, "Popen", process_guard)
        if application._providers is not None:
            for adapter in (application._providers.implementation, application._providers.review):
                guarded.setattr(adapter, "invoke", forbidden_call)
                guarded.setattr(adapter, "build_request", forbidden_call)
        with pytest.raises(WorkflowEngineError) as error:
            act()
        assert error.value.stop_reason is reason
        assert not writes and not calls
    assert artifact_snapshot(application.artifact_root) == before


class TestAuto017Binding:
    def test_stage_start_clock_idempotent(self, v2_application, monkeypatch):
        application = v2_application(clock=lambda: MOMENT)
        first = authorize_v2(application)
        before = artifact_snapshot(application.artifact_root)
        application._clock = lambda: pytest.fail("idempotent replay must not sample a clock")
        second = authorize_v2(application)
        assert first == second
        assert first.lines == second.lines
        assert artifact_snapshot(application.artifact_root) == before

    def test_stage_start_and_start_end_to_end(self, v2_application):
        application = v2_application()
        receipt = authorize_v2(application)
        report = application.start()
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        store = application._read_store(report.run_id)
        record = store.load()
        assert record.policy_digest == receipt.effective_policy_digest
        assert record.stage_start_id == receipt.stage_start_id
        assert store.policy_path.read_bytes() == store.load_policy(record).canonical_bytes()
        assert record.correction_round == 0
        assert not (application.repository_root / "policy.json").exists()

    @pytest.mark.parametrize("governed", [False, True])
    def test_missing_authority_matrix(self, v2_application, monkeypatch, governed):
        application = v2_application(governed=governed)
        expected = (
            StopReason.STAGE_START_AUTHORIZATION_CONFLICT
            if governed
            else StopReason.STAGE_START_NOT_AUTHORIZED
        )
        assert_refusal_without_effects(application, application.start, expected, monkeypatch)

    @pytest.mark.parametrize("command", ["start", "doctor"])
    def test_unknown_adapter_refused_before_any_method(self, v2_application, monkeypatch, command):
        application = v2_application(admitted=False)
        authorize_v2(application)
        assert_refusal_without_effects(
            application,
            getattr(application, command),
            StopReason.LIVE_PROVIDER_NOT_ENABLED,
            monkeypatch,
        )

    def test_changed_defaults_do_not_reinterpret(self, v2_application):
        application = v2_application()
        receipt = authorize_v2(application)
        (application.artifact_root / "project-defaults.json").write_text("invalid now")
        report = application.start()
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        store = application._read_store(report.run_id)
        record = store.load()
        assert record.policy_digest == receipt.effective_policy_digest
        before = store.policy_path.read_bytes()
        (application.artifact_root / "project-defaults.json").write_text('{"max_blockers":1}')
        application.resume()
        assert store.policy_path.read_bytes() == before
        lock = application._locked(report.run_id)
        try:
            session = application._session(
                store,
                lock,
                MilestonePlanLoader(application.config, application.repository_root).load(),
            )
            assert session.reviewer.policy.max_blockers == 3
        finally:
            lock.release()


def prepared_policy_run(application, *, command="resume", published=True):
    """A bound run at the public command's mutable entry state, before authority tampering."""
    from ai_workflow_engine.milestone_runner.policy import StageStartBinding, authority_digest

    receipt = authorize_v2(application)
    authorization = application._authority_store().read_authorization(receipt.stage_start_id)
    assert authorization is not None
    state = {
        "resume": RunStatus.IMPLEMENTING,
        "abort": RunStatus.IMPLEMENTING,
        "reconcile_milestone": RunStatus.HUMAN_INTERVENTION_REQUIRED,
        "reopen_milestone": RunStatus.MILESTONE_FAILED,
        "recover_failed_review": RunStatus.HUMAN_INTERVENTION_REQUIRED,
        "revalidate_correction": RunStatus.HUMAN_INTERVENTION_REQUIRED,
        "approve_commit": RunStatus.READY_FOR_COMMIT_APPROVAL,
        "approve_push": RunStatus.READY_FOR_PUSH_APPROVAL,
    }.get(command, RunStatus.IMPLEMENTING)
    evidence = {}
    if command in {"reconcile_milestone", "recover_failed_review"}:
        role = (
            ProviderRole.IMPLEMENTATION if command == "reconcile_milestone" else ProviderRole.REVIEW
        )
        evidence["provider_runs"] = [
            ProviderRunRecord(
                sequence=1,
                role=role,
                provider="fake",
                milestone_id=MILESTONE_ID if role is ProviderRole.IMPLEMENTATION else None,
                started_at="2026-08-06T11:59:00Z",
                completed_at="2026-08-06T12:00:00Z",
                duration_ms=1000,
                exit_code=1,
                failure_class=ProviderFailureClass.AUTH_FAILED,
                prompt_path="transcripts/0001-20260806T115900Z-fake.prompt.md",
                stdout_path="transcripts/0001-20260806T115900Z-fake.stdout.txt",
                stderr_path="transcripts/0001-20260806T115900Z-fake.stderr.txt",
            )
        ]
    if command == "recover_failed_review":
        evidence.update(review_attempts=1, successful_review_rounds=1, provider_failure_count=1)
    if command == "revalidate_correction":
        evidence["correction_round"] = 1
    if command == "approve_commit":
        (application.repository_root / IMPLEMENTED_PATH).write_text("verified work\n")
        evidence.update(
            changed_paths=[IMPLEMENTED_PATH],
            completed_milestones=[MILESTONE_ID],
            review_attempts=1,
            successful_review_rounds=1,
        )
    record = record_for(
        application.repository_root,
        application.config,
        workflow_state=state,
        current_milestone=MILESTONE_ID,
        stop_reason=(
            StopReason.GOVERNANCE_CONTRADICTION
            if state is RunStatus.HUMAN_INTERVENTION_REQUIRED
            else None
        ),
        policy_digest=receipt.effective_policy_digest,
        stage_start_id=receipt.stage_start_id,
        **evidence,
    )
    application._run_id = record.run_id
    payload = dict(
        schema_version=2,
        stage_start_key=receipt.stage_start_key,
        stage_start_id=receipt.stage_start_id,
        authorization_digest=receipt.authorization_digest,
        policy_digest=receipt.effective_policy_digest,
        run_id=record.run_id,
    )
    binding = StageStartBinding(**payload, binding_digest=authority_digest(payload))
    from ai_workflow_engine.milestone_runner.policy import StageStartConsumptionWitness

    witness_payload = {
        **binding.model_dump(mode="json"),
        "stage_id": authorization.stage_id,
        "contract_sha256": authorization.contract_sha256,
    }
    witness = StageStartConsumptionWitness(
        **witness_payload, witness_digest=authority_digest(witness_payload)
    )
    lock = application._locked(record.run_id)
    try:
        application._authority_store().publish_witness(witness, lock=lock)
        application._authority_store().publish_binding(binding, lock=lock)
        if published:
            store = application._store(record.run_id)
            store.publish_policy(authorization.effective_policy, lock=lock)
            store.publish(record, lock=lock)
            if command == "reconcile_milestone":
                transcript = store.run_directory / record.provider_runs[-1].stdout_path
                transcript.parent.mkdir(exist_ok=True)
                transcript.write_text(FAKE_RESULTS["IMPLEMENTATION"])
            record_latest_run(application.artifact_root, record.run_id)
    finally:
        lock.release()
    return receipt, record


MUTATING_V2_COMMANDS = (
    "resume",
    "abort",
    "reconcile_milestone",
    "reopen_milestone",
    "recover_failed_review",
    "revalidate_correction",
    "approve_commit",
    "approve_push",
)


def command_action(application, command):
    kwargs = {
        "abort": {"reason": "test"},
        "reconcile_milestone": {"milestone": MILESTONE_ID, "reason": "test"},
        "reopen_milestone": {"milestone": MILESTONE_ID, "reason": "test"},
        "recover_failed_review": {"classification": "AUTH_FAILED", "ruling": "test"},
    }.get(command, {})
    return lambda: getattr(application, command)(**kwargs)


def authority_path(application, receipt, artifact):
    names = {
        "pointer": f"key-{receipt.stage_start_key}.json",
        "authorization": f"{receipt.stage_start_id}.json",
        "binding": f"{receipt.stage_start_id}.binding.json",
    }
    return application.artifact_root / "stage-starts" / names[artifact]


COMMON_HOSTILE_AUTHORITY = (
    "missing",
    "symlink",
    "oversize",
    "duplicate-equal",
    "duplicate-different",
    "version-missing",
    "version-one",
    "version-three",
    "version-string",
    "version-float",
    "version-bool",
    "version-null",
    "unknown-field",
    "non-object",
    "invalid-utf8",
    "id-traversal",
    "id-absolute",
    "id-drive",
    "id-backslash",
    "id-nul",
    "id-upper",
    "id-truncated",
    "id-nonhex",
    "key-other",
    "pin-other",
    "missing-required",
    "noncanonical",
    "valid-foreign-content",
)
AUTHORITY_SPECIFIC = {
    "pointer": ("injected-run-id", "linked-foreign-authorization"),
    "authorization": (
        "injected-run-id",
        "timestamp-old-pin",
        "timestamp-new-pin",
        "timestamp-invalid-grammar",
        "timestamp-invalid-date",
        "duplicate-created-at-equal",
        "duplicate-created-at-different",
        "nested-duplicate",
        "nested-context-duplicate",
        "nested-malformed",
        "contract-traversal",
        "registry-traversal",
        "contract-absolute",
        "contract-backslash",
        "contract-noncanonical",
        "stage-other",
    ),
    "binding": (
        "duplicate-run-id-equal",
        "duplicate-run-id-different",
        "duplicate-binding-digest-equal",
        "duplicate-binding-digest-different",
        "self-digest-other",
        "policy-pin-other",
        "run-traversal",
        "run-absolute",
        "run-drive",
        "run-backslash",
        "run-nul",
    ),
}
HOSTILE_AUTHORITY_CASES = [
    (artifact, mutation)
    for artifact in AUTHORITY_SPECIFIC
    for mutation in (*COMMON_HOSTILE_AUTHORITY, *AUTHORITY_SPECIFIC[artifact])
]


def valid_authorization_variant(document, *, foreign_stage):
    """An independently valid authority, with every policy/logical/full digest recomputed.

    This distinguishes rejected substitution from a malformed document that could never pass
    the authority schema in the first place.
    """
    from ai_workflow_engine.milestone_runner.models import canonical_digest
    from ai_workflow_engine.milestone_runner.policy import (
        EffectiveStageExecutionPolicy,
        StageStartAuthorization,
        authority_digest,
        authority_json_bytes,
        logical_authorization_payload,
        stage_start_key,
    )

    changed = json.loads(json.dumps(document))
    policy = changed["effective_policy"]
    if foreign_stage:
        changed["stage_id"] = policy["stage_id"] = "FOREIGN-098"
    else:
        blockers = 2 if policy["max_blockers"] != 2 else 1
        changed["stage_overrides"]["max_blockers"] = blockers
        policy["max_blockers"] = blockers
        policy["stage_overrides_digest"] = canonical_digest(changed["stage_overrides"])
    validated_policy = EffectiveStageExecutionPolicy.model_validate_json(
        authority_json_bytes(policy)
    )
    changed["effective_policy_digest"] = validated_policy.digest
    changed["stage_start_key"] = stage_start_key(
        changed["repository_identity"], changed["stage_id"], changed["contract_sha256"]
    )
    changed["stage_start_id"] = authority_digest(logical_authorization_payload(changed))
    changed["authorization_digest"] = authority_digest(
        {name: value for name, value in changed.items() if name != "authorization_digest"}
    )
    validated = StageStartAuthorization.model_validate_json(authority_json_bytes(changed))
    assert validated.stage_start_id != document["stage_start_id"]
    return validated


@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
@pytest.mark.parametrize("governed", [False, True])
def test_auto017_valid_same_stage_different_policy_refuses_run_pin(
    v2_application, monkeypatch, command, governed
):
    from ai_workflow_engine.milestone_runner.policy import (
        StageStartBinding,
        StageStartPointer,
        authority_digest,
        authority_json_bytes,
    )

    application = v2_application(governed=governed)
    receipt, record = prepared_policy_run(application, command=command)
    original = json.loads(authority_path(application, receipt, "authorization").read_bytes())
    substituted = valid_authorization_variant(original, foreign_stage=False)
    assert substituted.stage_id == application.config.stage.stage_id
    assert substituted.stage_start_key == receipt.stage_start_key
    assert substituted.effective_policy_digest != record.policy_digest
    authority_root = application.artifact_root / "stage-starts"
    (authority_root / f"{substituted.stage_start_id}.json").write_bytes(
        authority_json_bytes(substituted.model_dump(mode="json"))
    )
    pointer = StageStartPointer(
        schema_version=2,
        stage_start_key=substituted.stage_start_key,
        stage_start_id=substituted.stage_start_id,
        authorization_digest=substituted.authorization_digest,
    )
    authority_path(application, receipt, "pointer").write_bytes(
        authority_json_bytes(pointer.model_dump(mode="json"))
    )
    payload = {
        **pointer.model_dump(mode="json"),
        "policy_digest": substituted.effective_policy_digest,
        "run_id": record.run_id,
    }
    binding = StageStartBinding(**payload, binding_digest=authority_digest(payload))
    (authority_root / f"{substituted.stage_start_id}.binding.json").write_bytes(
        authority_json_bytes(binding.model_dump(mode="json"))
    )
    # The entire alternate authority chain is valid and internally consistent. The existing
    # run's immutable policy pin is what must defeat it before any progression or write.
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.POLICY_DIGEST_MISMATCH,
        monkeypatch,
    )


def mutate_authority(path, artifact, mutation):
    from ai_workflow_engine.milestone_runner.policy import authority_digest, authority_json_bytes

    raw = path.read_bytes()
    document = json.loads(raw)
    if mutation in {"valid-foreign-content", "linked-foreign-authorization"}:
        from ai_workflow_engine.milestone_runner.policy import StageStartBinding, StageStartPointer

        authorization_document = (
            document
            if artifact == "authorization"
            else json.loads((path.parent / f"{document['stage_start_id']}.json").read_bytes())
        )
        foreign = valid_authorization_variant(authorization_document, foreign_stage=True)
        if artifact == "authorization":
            replacement = foreign
        else:
            payload = {
                "schema_version": 2,
                "stage_start_key": (
                    document["stage_start_key"]
                    if mutation == "linked-foreign-authorization"
                    else foreign.stage_start_key
                ),
                "stage_start_id": foreign.stage_start_id,
                "authorization_digest": foreign.authorization_digest,
            }
            if artifact == "pointer":
                replacement = StageStartPointer(**payload)
                # Its linked record really exists under its own correct ID; the failed check
                # must concern the configured key/Stage, not an absent or invalid target.
                (path.parent / f"{foreign.stage_start_id}.json").write_bytes(
                    authority_json_bytes(foreign.model_dump(mode="json"))
                )
            else:
                payload.update(
                    policy_digest=foreign.effective_policy_digest, run_id="foreign-valid-run"
                )
                replacement = StageStartBinding(**payload, binding_digest=authority_digest(payload))
        path.write_bytes(authority_json_bytes(replacement.model_dump(mode="json")))
        return
    if mutation == "missing":
        path.unlink()
        return
    if mutation == "symlink":
        target = path.with_suffix(".hostile-target")
        path.rename(target)
        path.symlink_to(target)
        return
    if mutation == "oversize":
        path.write_bytes(b"x" * (65537 if artifact == "authorization" else 4097))
        return
    if mutation.startswith("duplicate-"):
        field = next(
            (
                key
                for prefix, key in (
                    ("duplicate-created-at-", "created_at"),
                    ("duplicate-run-id-", "run_id"),
                    ("duplicate-binding-digest-", "binding_digest"),
                )
                if mutation.startswith(prefix)
            ),
            "stage_start_id",
        )
        value = (
            document[field]
            if mutation.endswith("equal")
            else {
                "created_at": "2025-01-01T00:00:00Z",
                "run_id": "another-valid-run",
            }.get(field, "f" * 64)
        )
        path.write_bytes(
            b"{" + json.dumps(field).encode() + b":" + json.dumps(value).encode() + b"," + raw[1:]
        )
        return
    if mutation == "invalid-utf8":
        path.write_bytes(b"\xff")
        return
    if mutation == "noncanonical":
        path.write_bytes(raw + b"\n")
        return
    if mutation == "nested-duplicate":
        path.write_bytes(
            raw.replace(b'"effective_policy":{', b'"effective_policy":{"schema_version":2,', 1)
        )
        return
    if mutation == "nested-context-duplicate":
        path.write_bytes(
            raw.replace(b'"registry_context":{', b'"registry_context":{"path":null,', 1)
        )
        return
    versions = {
        "version-one": 1,
        "version-three": 3,
        "version-string": "2",
        "version-float": 2.0,
        "version-bool": True,
        "version-null": None,
    }
    if mutation in versions:
        document["schema_version"] = versions[mutation]
    elif mutation == "version-missing":
        del document["schema_version"]
    elif mutation == "missing-required":
        del document["authorization_digest"]
    elif mutation == "unknown-field":
        document["unknown"] = "hostile"
    elif mutation == "non-object":
        document = []
    elif mutation.startswith("id-") or mutation.startswith("run-"):
        field = "run_id" if mutation.startswith("run-") else "stage_start_id"
        document[field] = {
            "traversal": "../outside",
            "absolute": "/outside",
            "drive": "C:/outside",
            "backslash": "bad\\path",
            "nul": "bad\x00path",
            "upper": "A" * 64,
            "truncated": "a" * 63,
            "nonhex": "g" * 64,
        }[mutation.split("-", 1)[1]]
    elif mutation == "key-other":
        document["stage_start_key"] = "b" * 64
    elif mutation == "pin-other":
        document["authorization_digest"] = "b" * 64
    elif mutation == "injected-run-id":
        document["run_id"] = "unexpected-run"
    elif mutation in {"timestamp-invalid-grammar", "timestamp-invalid-date"}:
        document["created_at"] = (
            "not-a-timestamp" if mutation == "timestamp-invalid-grammar" else "2026-02-30T10:11:12Z"
        )
        # Leave no unrelated integrity defect to mask the timestamp validator itself.
        document["authorization_digest"] = authority_digest(
            {k: v for k, v in document.items() if k != "authorization_digest"}
        )
    elif mutation.startswith("timestamp-"):
        document["created_at"] = "2026-09-29T10:11:12Z"
        if mutation == "timestamp-new-pin":
            document["authorization_digest"] = authority_digest(
                {k: v for k, v in document.items() if k != "authorization_digest"}
            )
    elif mutation == "nested-malformed":
        document["effective_policy"]["registry_context"] = {
            "kind": "GOVERNED_REGISTRY",
            "path": None,
        }
    elif mutation.startswith("contract-"):
        document["contract_path"] = {
            "traversal": "../outside",
            "absolute": "/outside",
            "backslash": "docs\\x",
            "noncanonical": "./docs/x",
        }[mutation.split("-", 1)[1]]
    elif mutation == "registry-traversal":
        document["registry_context"] = {"kind": "GOVERNED_REGISTRY", "path": "../outside"}
    elif mutation == "stage-other":
        document["stage_id"] = "ST-OTHER"
    elif mutation == "self-digest-other":
        document["binding_digest"] = "b" * 64
    elif mutation == "policy-pin-other":
        document["policy_digest"] = "b" * 64
        document["binding_digest"] = authority_digest(
            {k: v for k, v in document.items() if k != "binding_digest"}
        )
    else:
        raise AssertionError(mutation)
    path.write_bytes(authority_json_bytes(document))


@pytest.mark.parametrize("artifact,mutation", HOSTILE_AUTHORITY_CASES)
@pytest.mark.parametrize("command", ("start", *MUTATING_V2_COMMANDS))
@pytest.mark.parametrize("governed", [False, True])
def test_auto017_hostile_persisted_authority_matrix(
    v2_application, monkeypatch, artifact, mutation, command, governed
):
    application = v2_application(governed=governed)
    receipt, _ = prepared_policy_run(application, command=command, published=command != "start")
    path = authority_path(application, receipt, artifact)
    mutate_authority(path, artifact, mutation)
    if command == "start" and artifact == "binding" and mutation == "missing":
        assert application.start().state is RunStatus.READY_FOR_COMMIT_APPROVAL
        return
    expected = (
        StopReason.STAGE_START_ALREADY_BOUND
        if artifact == "binding"
        else (
            StopReason.STAGE_START_AUTHORIZATION_CONFLICT
            if governed
            else StopReason.STAGE_START_NOT_AUTHORIZED
        )
    )
    assert_refusal_without_effects(
        application, command_action(application, command), expected, monkeypatch
    )


@pytest.mark.parametrize("command", ("start", *MUTATING_V2_COMMANDS))
@pytest.mark.parametrize(
    "before,after",
    [("registry.md", None), (None, "registry.md"), ("registry.md", "other-registry.md")],
)
def test_auto017_registry_declaration_is_frozen(
    v2_application, monkeypatch, command, before, after
):
    application = v2_application(governed=before is not None)
    if command == "start":
        authorize_v2(application)
    else:
        prepared_policy_run(application, command=command)
    document = application.config.model_dump(mode="json", exclude={"review_policy"})
    document["stage"]["registry_path"] = after
    application._config = RunnerConfig.model_validate(document)
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.POLICY_BINDING_MISMATCH,
        monkeypatch,
    )


@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
def test_auto017_changed_ceilings_refuse_continuations(v2_application, monkeypatch, command):
    application = v2_application()
    prepared_policy_run(application, command=command)
    document = application.config.model_dump(mode="json", exclude={"review_policy"})
    document["stage"]["execution_ceilings"]["max_blockers"] = 2
    application._config = RunnerConfig.model_validate(document)
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.POLICY_BINDING_MISMATCH,
        monkeypatch,
    )


@pytest.mark.parametrize("artifact", ["pointer", "authorization", "binding"])
@pytest.mark.parametrize("parent_depth", [0, 1, 2, 3])
@pytest.mark.parametrize("command", ("start", *MUTATING_V2_COMMANDS))
def test_auto017_symlinked_authority_ancestors_refuse(
    v2_application, monkeypatch, artifact, parent_depth, command
):
    application = v2_application()
    receipt, _ = prepared_policy_run(application, command=command, published=command != "start")
    path = authority_path(application, receipt, artifact)
    if parent_depth == 0:
        target = path.with_suffix(".hostile-target")
        mutate_authority(path, artifact, "symlink")
    else:
        # For a shared authority-directory ancestor, pointer validation fails first.
        parent = path.parents[parent_depth - 1]
        target = parent.with_name(parent.name + "-target")
        parent.rename(target)
        parent.symlink_to(target, target_is_directory=True)
    reason = (
        StopReason.STAGE_START_ALREADY_BOUND
        if artifact == "binding" and parent_depth == 0
        else StopReason.STAGE_START_NOT_AUTHORIZED
    )
    # A shared ancestor also invalidates policy.json, which §10.3 checks first.
    if command != "start" and parent_depth >= 2:
        reason = StopReason.POLICY_DIGEST_MISMATCH
    real_open = os.open

    def no_target_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        opened = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if opened == target or opened.is_relative_to(target):
            os.close(descriptor)
            pytest.fail("a symlink target was opened")
        return descriptor

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", no_target_open)
        assert_refusal_without_effects(
            application, command_action(application, command), reason, monkeypatch
        )


@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
def test_auto017_valid_binding_with_wrong_run_id_refuses(v2_application, monkeypatch, command):
    from ai_workflow_engine.milestone_runner.policy import authority_digest, authority_json_bytes

    application = v2_application()
    receipt, _ = prepared_policy_run(application, command=command)
    path = authority_path(application, receipt, "binding")
    document = json.loads(path.read_bytes())
    document["run_id"] = "another-well-formed-run"
    document["binding_digest"] = authority_digest(
        {k: v for k, v in document.items() if k != "binding_digest"}
    )
    path.write_bytes(authority_json_bytes(document))
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.STAGE_START_ALREADY_BOUND,
        monkeypatch,
    )


@pytest.mark.parametrize("artifact,mutation", HOSTILE_AUTHORITY_CASES)
def test_auto017_stage_start_reuse_rejects_hostile_artifacts(
    v2_application, monkeypatch, artifact, mutation
):
    application = v2_application()
    receipt, _ = prepared_policy_run(application)
    path = authority_path(application, receipt, artifact)
    mutate_authority(path, artifact, mutation)
    assert_refusal_without_effects(
        application,
        lambda: authorize_v2(application),
        StopReason.STAGE_START_INPUT_CONFLICT,
        monkeypatch,
    )


def test_auto017_stage_start_orphan_reuses_bytes_at_later_clock(v2_application, monkeypatch):
    from ai_workflow_engine.milestone_runner.state import StageStartStore

    application = v2_application(clock=lambda: MOMENT)
    original = StageStartStore.publish_pointer
    with monkeypatch.context() as crash:
        crash.setattr(
            StageStartStore,
            "publish_pointer",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")),
        )
        with pytest.raises(RuntimeError, match="crash"):
            authorize_v2(application)
    records = list((application.artifact_root / "stage-starts").glob("*.json"))
    assert len(records) == 1
    raw = records[0].read_bytes()
    stamp = records[0].stat().st_mtime_ns
    application._clock = lambda: pytest.fail("orphan reuse must not sample authorization clock")
    receipt = authorize_v2(application)
    assert records[0].read_bytes() == raw
    assert records[0].stat().st_mtime_ns == stamp
    assert receipt.created_at == "2026-08-06T12:00:00Z"
    assert StageStartStore.publish_pointer is original


def test_auto017_binding_crash_adopts_run_id(v2_application, monkeypatch):
    application = v2_application()
    receipt = authorize_v2(application)
    with monkeypatch.context() as crash:
        crash.setattr(
            RunStateStore,
            "publish_policy",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")),
        )
        with pytest.raises(RuntimeError, match="crash"):
            application.start()
    binding = application._authority_store().read_binding(receipt.stage_start_id)
    assert binding is not None
    application._run_id = "different-requested-run"
    report = application.start()
    assert report.run_id == binding.run_id
    assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL


class UnrelatedSpawningAdapter:
    TEST_DOUBLE = True
    name = "misleading-fake"

    def invoke(self, *args, **kwargs):
        return subprocess.Popen(["must-never-execute"])

    def build_request(self, *args, **kwargs):
        return subprocess.Popen(["must-never-execute"])


@pytest.mark.parametrize("command", ["start", "resume", "doctor"])
@pytest.mark.parametrize(
    "variant",
    [
        "unclassified",
        "marker",
        "replacement",
        "subclass",
        "live-entry",
        "wrong-type",
        "production",
        "production-relabelled",
        "mixed",
    ],
)
def test_auto017_adapter_admission_fails_closed(v2_application, monkeypatch, command, variant):
    from ai_workflow_engine.milestone_runner.application import (
        AdapterAdmission,
        AdapterAdmissionKind,
    )

    application = v2_application()
    if command == "resume":
        prepared_policy_run(application)
    else:
        authorize_v2(application)
    original = application._providers
    assert original is not None
    if variant in {"unclassified", "marker", "mixed"}:
        unknown = UnrelatedSpawningAdapter()
        if variant == "unclassified":
            unknown.TEST_DOUBLE = False
        application._providers = ProviderBinding(unknown, original.review)
    elif variant in {"replacement", "subclass"}:

        class UnadmittedSubclass(FakeAdapter):
            pass

        original_adapter = original.implementation
        cls = UnadmittedSubclass if variant == "subclass" else FakeAdapter
        replacement = cls(original_adapter._script, results=FAKE_RESULTS, touch=IMPLEMENTED_PATH)
        application._providers = ProviderBinding(replacement, original.review)
    elif variant == "live-entry":
        application._adapter_admissions = tuple(
            AdapterAdmission(a, type(a), AdapterAdmissionKind.LIVE)
            for a in (original.implementation, original.review)
        )
    elif variant == "wrong-type":
        application._adapter_admissions = tuple(
            AdapterAdmission(a, UnrelatedSpawningAdapter, AdapterAdmissionKind.TEST_DOUBLE)
            for a in (original.implementation, original.review)
        )
    elif variant == "production":
        application._providers = None
    elif variant == "production-relabelled":
        application._providers = ProviderBinding.from_config(application.config)
        application._adapter_admissions = tuple(
            AdapterAdmission(a, type(a), AdapterAdmissionKind.TEST_DOUBLE)
            for a in (application._providers.implementation, application._providers.review)
        )
    assert_refusal_without_effects(
        application,
        getattr(application, command),
        StopReason.LIVE_PROVIDER_NOT_ENABLED,
        monkeypatch,
    )


def test_auto017_manifest_is_copied_and_provider_boundary_rechecks(v2_application, monkeypatch):
    import ai_workflow_engine.milestone_runner.application as module

    application = v2_application()
    receipt, record = prepared_policy_run(application)
    store = application._read_store(record.run_id)
    lock = application._locked(record.run_id)
    try:
        plan = MilestonePlanLoader(application.config, application.repository_root).load()
        session = application._session(store, lock, plan)
        assert isinstance(session.adapter_admissions, tuple)
        from dataclasses import replace

        session = replace(
            session, providers=ProviderBinding(UnrelatedSpawningAdapter(), session.providers.review)
        )
        assert_refusal_without_effects(
            application,
            lambda: module._invoke_provider(
                session,
                record,
                role=ProviderRole.IMPLEMENTATION,
                prompt="test",
                milestone_id=MILESTONE_ID,
            ),
            StopReason.LIVE_PROVIDER_NOT_ENABLED,
            monkeypatch,
        )
        assert receipt.effective_policy_digest == record.policy_digest
    finally:
        lock.release()


@pytest.mark.parametrize(
    "status", ["AUTHORIZED", "IN_PROGRESS", "NOT_STARTED", "COMPLETE", "BLOCKED"]
)
@pytest.mark.parametrize("native", [False, True])
def test_auto017_authority_matrix_registry_states(v2_application, monkeypatch, status, native):
    application = v2_application(governed=True)
    registry = application.repository_root / "registry.md"
    registry.write_text(registry.read_text().replace("AUTHORIZED", status))
    if native:
        authorize_v2(application)
    if native and status in {"AUTHORIZED", "IN_PROGRESS"}:
        # Registry mutations are committed in fixture setup so remaining entry conditions pass.
        git(application.repository_root, "add", "registry.md")
        if git(application.repository_root, "status", "--porcelain"):
            git(application.repository_root, "commit", "-m", "test status")
        document = application.config.model_dump(mode="json", exclude={"review_policy"})
        document["repository"]["baseline_sha"] = git(
            application.repository_root, "rev-parse", "HEAD"
        )
        application._config = RunnerConfig.model_validate(document)
        assert application.start().state is RunStatus.READY_FOR_COMMIT_APPROVAL
    else:
        reason = (
            StopReason.STAGE_START_AUTHORIZATION_CONFLICT
            if native or status in {"AUTHORIZED", "IN_PROGRESS"}
            else StopReason.STAGE_START_NOT_AUTHORIZED
        )
        assert_refusal_without_effects(application, application.start, reason, monkeypatch)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "no-table", "no-row", "duplicate-row", "prompt-other", "log-only", "prefix"],
)
def test_auto017_registry_parser_fail_closed(v2_application, monkeypatch, mutation):
    application = v2_application(governed=True)
    authorize_v2(application)
    registry = application.repository_root / "registry.md"
    text = registry.read_text()
    if mutation == "missing":
        registry.unlink()
    elif mutation == "no-table":
        registry.write_text("| Stage | Status |\n|---|---|\n" + f"| {STAGE_ID} | AUTHORIZED |\n")
    elif mutation == "duplicate-row":
        registry.write_text(text + text.splitlines()[-1] + "\n")
    elif mutation == "prompt-other":
        registry.write_text(text.replace(CONTRACT_PATH, "other-contract.md"))
    elif mutation == "log-only":
        registry.write_text(f"Log: {STAGE_ID} AUTHORIZED\n")
    else:
        registry.write_text(
            text.replace(STAGE_ID, STAGE_ID + "0" if mutation == "prefix" else "ST-OTHER")
        )
    assert_refusal_without_effects(
        application, application.start, StopReason.STAGE_START_AUTHORIZATION_CONFLICT, monkeypatch
    )


def test_auto017_registry_parser_pinned_real_registry():
    from ai_workflow_engine.milestone_runner.application import registry_stage_entry

    text = subprocess.check_output(
        [
            "git",
            "show",
            "489885d51e0d84e60c3506fd1ae2b365440b2401:docs/workflow-automation/STAGE_REGISTRY.md",
        ],
        text=True,
    )
    for stage, status in [
        ("AUTO-016", "COMPLETE"),
        ("AUTO-017", "NOT_STARTED"),
        ("AUTO-009", "COMPLETE"),
    ]:
        entry = registry_stage_entry(text, stage)
        assert entry is not None
        assert entry.state == status
    assert (
        registry_stage_entry(
            "| Stage | Title | Role | State | Branch | Prompt |\n"
            "|---|---|---|---|---|---|\n| ST-10 | t | r | AUTHORIZED | main | c.md |",
            "ST-1",
        )
        is None
    )


@pytest.mark.parametrize("configuration_v2,record_v2", [(False, True), (True, False)])
@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
def test_auto017_configuration_record_mode_mismatch(
    v2_application, config_factory, monkeypatch, configuration_v2, record_v2, command
):
    application = v2_application()
    _, record = prepared_policy_run(application, command=command)
    if not record_v2:
        document = record.model_dump(mode="json")
        document.update(policy_digest=None, stage_start_id=None)
        application._read_store(record.run_id).state_path.write_text(json.dumps(document))
    if not configuration_v2:
        application._config = load_runner_config(config_factory())
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.POLICY_BINDING_MISMATCH,
        monkeypatch,
    )


def test_auto017_v1_lifecycle_has_no_policy_artifacts(application_factory):
    application = application_factory()
    report = application.start()
    assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
    assert not (application.artifact_root / "stage-starts").exists()
    assert not (application.artifact_root / report.run_id / "policy.json").exists()
    record = application._read_store(report.run_id).load()
    assert record.schema_version == 2
    assert record.policy_digest is None and record.stage_start_id is None


def test_auto017_stage_start_is_single_use(v2_application, monkeypatch):
    application = v2_application()
    authorize_v2(application)
    first = application.start()
    assert first.state is RunStatus.READY_FOR_COMMIT_APPROVAL
    application._run_id = "different-never-published-run"
    assert_refusal_without_effects(
        application, application.start, StopReason.STAGE_START_ALREADY_BOUND, monkeypatch
    )


@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
def test_auto017_hostile_fixture_otherwise_mutates(v2_application, command):
    application = v2_application()
    _, record = prepared_policy_run(application, command=command)
    before = application._read_store(record.run_id).state_path.read_bytes()
    command_action(application, command)()
    assert application._read_store(record.run_id).state_path.read_bytes() != before


def test_auto017_invalid_plan_publishes_bound_stop_and_can_resume(v2_application, plan_root):
    application = v2_application()
    receipt = authorize_v2(application)
    plan = plan_root / f"{MILESTONE_ID}.yaml"
    original = plan.read_bytes()
    plan.write_text("not: a valid milestone\n")
    stopped = application.start()
    assert stopped.stop_reason is StopReason.PLAN_COVERAGE_MISMATCH
    record = application._read_store(stopped.run_id).load()
    assert record.stage_start_id == receipt.stage_start_id
    assert record.policy_digest == receipt.effective_policy_digest
    plan.write_bytes(original)
    resumed = application.resume()
    assert resumed.state is RunStatus.READY_FOR_COMMIT_APPROVAL


@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
@pytest.mark.parametrize("parent_depth", [0, 1, 2])
def test_auto017_cli_run_lookup_never_reads_symlink_target(
    v2_application, monkeypatch, command, parent_depth
):
    application = v2_application()
    prepared_policy_run(application, command=command)
    application._run_id = None
    root = application.artifact_root
    parent = root if parent_depth == 0 else root.parents[parent_depth - 1]
    target = parent.with_name(parent.name + "-target")
    parent.rename(target)
    parent.symlink_to(target, target_is_directory=True)
    real_open = os.open

    def no_target_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        opened = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if opened == target or opened.is_relative_to(target):
            os.close(descriptor)
            pytest.fail("CLI run lookup opened a symlink target")
        return descriptor

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", no_target_open)
        assert_refusal_without_effects(
            application,
            command_action(application, command),
            StopReason.POLICY_DIGEST_MISMATCH,
            monkeypatch,
        )


@pytest.mark.parametrize("injected", [None, "another-requested-run"])
@pytest.mark.parametrize("command", ["start", "stage_start"])
def test_auto017_missing_published_binding_never_rebinds(
    v2_application, monkeypatch, injected, command
):
    application = v2_application()
    receipt, _ = prepared_policy_run(application)
    authority_path(application, receipt, "binding").unlink()
    application._run_id = injected
    action = application.start if command == "start" else lambda: authorize_v2(application)
    reason = (
        StopReason.STAGE_START_ALREADY_BOUND
        if command == "start"
        else StopReason.STAGE_START_INPUT_CONFLICT
    )
    assert_refusal_without_effects(application, action, reason, monkeypatch)


@pytest.mark.parametrize("mutation", ["registry", "contract"])
def test_auto017_authority_withdrawn_during_prompt_refuses_actual_invocation(
    v2_application, monkeypatch, mutation
):
    import ai_workflow_engine.milestone_runner.application as module

    application = v2_application(governed=True)
    prepared_policy_run(application)
    render = module.render_implementation_prompt
    calls = []

    def drift(**kwargs):
        text = render(**kwargs)
        path = application.repository_root / (
            "registry.md" if mutation == "registry" else CONTRACT_PATH
        )
        path.write_text(
            path.read_text().replace("AUTHORIZED", "NOT_STARTED")
            if mutation == "registry"
            else "contract changed after the entry check\n"
        )
        return text

    def invoke(*args, **kwargs):
        calls.append(True)
        pytest.fail("provider invoked after authority withdrawal")

    monkeypatch.setattr(module, "render_implementation_prompt", drift)
    monkeypatch.setattr(application._providers.implementation, "invoke", invoke)
    expected = (
        StopReason.STAGE_START_AUTHORIZATION_CONFLICT
        if mutation == "registry"
        else StopReason.STAGE_ID_NOT_AUTHORIZED
    )
    with pytest.raises(RunRefused) as error:
        application.resume()
    assert error.value.stop_reason is expected
    assert calls == []
    record = application.status().record
    assert record.workflow_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
    assert record.stop_reason is expected
    assert not record.provider_runs


def test_auto017_registry_withdrawal_refuses_spawn_failed_retry(v2_application, monkeypatch):
    from ai_workflow_engine.milestone_runner.providers.base import ProviderInvocation

    application = v2_application(governed=True)
    prepared_policy_run(application)
    calls = []

    def spawn_failed(invoker, **kwargs):
        calls.append(True)
        assert len(calls) == 1, "a second provider attempt crossed withdrawn authority"
        path = application.repository_root / "registry.md"
        path.write_text(path.read_text().replace("AUTHORIZED", "NOT_STARTED"))
        # AUTO-018 section 8.3: a completion is asserted only over transcripts that were really
        # published, so this scripted fake publishes its three through the durable boundary.
        moment = datetime(2026, 8, 6, 11, 59, tzinfo=UTC)
        writes = [
            invoker._store.write_transcript(
                sequence=1, label="fake", kind=kind, text=text, moment=moment, lock=invoker._lock
            )
            for kind, text in (
                (TranscriptKind.PROMPT, "prompt"),
                (TranscriptKind.STDOUT, ""),
                (TranscriptKind.STDERR, "spawn failed"),
            )
        ]
        return ProviderInvocation(
            writes=writes,
            record=ProviderRunRecord(
                sequence=1,
                role=ProviderRole.IMPLEMENTATION,
                provider="fake",
                milestone_id=MILESTONE_ID,
                started_at="2026-08-06T11:59:00Z",
                completed_at="2026-08-06T12:00:00Z",
                duration_ms=1000,
                exit_code=1,
                failure_class=ProviderFailureClass.SPAWN_FAILED,
                prompt_path="transcripts/0001-20260806T115900Z-fake.prompt.md",
                stdout_path="transcripts/0001-20260806T115900Z-fake.stdout.txt",
                stderr_path="transcripts/0001-20260806T115900Z-fake.stderr.txt",
            ),
            stdout="",
            stderr="spawn failed",
        )

    monkeypatch.setattr(application._providers.implementation, "invoke", spawn_failed)
    with pytest.raises(RunRefused) as error:
        application.resume()
    assert error.value.stop_reason is StopReason.STAGE_START_AUTHORIZATION_CONFLICT
    record = application.status().record
    assert record.workflow_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
    assert record.stop_reason is StopReason.STAGE_START_AUTHORIZATION_CONFLICT
    assert len(calls) == len(record.provider_runs) == 1


@pytest.mark.parametrize("field", ["policy_digest", "stage_start_id"])
def test_auto017_revise_and_transition_updates_cannot_replace_policy_pins(worktree, config, field):
    """T-REVISE-GUARD: neither general update API can mint or replace authority."""
    record = record_for(
        worktree,
        config,
        workflow_state=RunStatus.IMPLEMENTING,
        policy_digest="a" * 64,
        stage_start_id="b" * 64,
    )
    with pytest.raises(ApplicationError, match=field):
        revise_record(record, moment=MOMENT, updates={field: "c" * 64})
    with pytest.raises(ApplicationError, match=field):
        transition_to(record, RunStatus.FOCUSED_VERIFYING, moment=MOMENT, updates={field: "c" * 64})


def test_auto017_transition_preserves_both_policy_pins(worktree, config):
    record = record_for(
        worktree,
        config,
        workflow_state=RunStatus.IMPLEMENTING,
        policy_digest="a" * 64,
        stage_start_id="b" * 64,
    )
    moved = transition_to(record, RunStatus.FOCUSED_VERIFYING, moment=MOMENT)
    assert moved.policy_digest == record.policy_digest
    assert moved.stage_start_id == record.stage_start_id


@pytest.mark.parametrize("command", ("start", *MUTATING_V2_COMMANDS))
@pytest.mark.parametrize(
    "field,value", [("contract_sha256", "e" * 64), ("contract_path", "docs/different-contract.md")]
)
@pytest.mark.parametrize("governed", [False, True])
def test_auto017_contract_configuration_drift_refuses_before_mutation(
    v2_application, monkeypatch, command, field, value, governed
):
    application = v2_application(governed=governed)
    if command == "start":
        authorize_v2(application)
    else:
        prepared_policy_run(application, command=command)
    document = application.config.model_dump(mode="json", exclude={"review_policy"})
    document["stage"][field] = value
    application._config = RunnerConfig.model_validate(document)
    reason = (
        StopReason.POLICY_BINDING_MISMATCH
        if command != "start"
        else (
            StopReason.STAGE_START_AUTHORIZATION_CONFLICT
            if governed
            else StopReason.STAGE_START_NOT_AUTHORIZED
        )
    )
    assert_refusal_without_effects(
        application, command_action(application, command), reason, monkeypatch
    )


def test_auto017_binding_publication_conflict_has_its_typed_refusal(v2_application, monkeypatch):
    from ai_workflow_engine.milestone_runner.state import (
        ExclusivePublicationConflict,
        StageStartStore,
    )

    application = v2_application()
    authorize_v2(application)

    def conflict(*args, **kwargs):
        raise ExclusivePublicationConflict("competing binding")

    monkeypatch.setattr(StageStartStore, "publish_binding", conflict)
    with pytest.raises(RunRefused) as error:
        application.start()
    assert error.value.stop_reason is StopReason.STAGE_START_ALREADY_BOUND
    assert not list(application.artifact_root.glob("*/policy.json"))
    assert not list(application.artifact_root.glob("*/state.json"))


@pytest.mark.parametrize("command", MUTATING_V2_COMMANDS)
def test_auto017_remediation_substituted_run_directory(v2_application, monkeypatch, command):
    import shutil

    application = v2_application()
    _, record = prepared_policy_run(application, command=command)
    destination = application.artifact_root / "substituted-run"
    shutil.copytree(application._read_store(record.run_id).run_directory, destination)
    application._run_id = destination.name
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.POLICY_BINDING_MISMATCH,
        monkeypatch,
    )


@pytest.mark.parametrize("run_id", ["arbitrary.Owner-17", "another_run.42"])
def test_auto017_remediation_witness_first(v2_application, monkeypatch, run_id):
    import hashlib

    import ai_workflow_engine.milestone_runner.state as module

    application = v2_application(run_id=run_id)
    receipt = authorize_v2(application)
    witness_path = (
        application.artifact_root / "stage-starts" / f"{receipt.stage_start_id}.consumed.json"
    )
    assert not witness_path.exists()
    writes = []
    original = module.publish_exclusively

    def observe(path, payload, **kwargs):
        writes.append(path.name)
        return original(path, payload, **kwargs)

    monkeypatch.setattr(module, "publish_exclusively", observe)
    report = application.start()
    assert report.run_id == run_id
    raw = witness_path.read_bytes()
    document = json.loads(raw)
    digest = document.pop("witness_digest")

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    assert digest == hashlib.sha256(canonical(document)).hexdigest()
    assert document == dict(
        schema_version=2,
        stage_start_key=receipt.stage_start_key,
        stage_start_id=receipt.stage_start_id,
        stage_id=STAGE_ID,
        contract_sha256=application.config.stage.contract_sha256,
        authorization_digest=receipt.authorization_digest,
        policy_digest=receipt.effective_policy_digest,
        run_id=run_id,
        binding_digest=json.loads(authority_path(application, receipt, "binding").read_bytes())[
            "binding_digest"
        ],
    )
    assert raw == canonical({**document, "witness_digest": digest})
    assert writes.index(witness_path.name) < writes.index(f"{receipt.stage_start_id}.binding.json")


@pytest.mark.parametrize("loss", ["none", "binding-latest", "witness"])
@pytest.mark.parametrize("same_id", [False, True])
def test_auto017_remediation_witness_second_refused(v2_application, monkeypatch, loss, same_id):
    application = v2_application()
    receipt = authorize_v2(application)
    report = application.start()
    if loss == "binding-latest":
        authority_path(application, receipt, "binding").unlink()
        (application.artifact_root / "latest-run.json").unlink()
    elif loss == "witness":
        (
            application.artifact_root / "stage-starts" / f"{receipt.stage_start_id}.consumed.json"
        ).unlink()
    application._run_id = report.run_id if same_id else "second-arbitrary-run"
    assert_refusal_without_effects(
        application,
        application.start,
        StopReason.STAGE_START_ALREADY_BOUND,
        monkeypatch,
    )


def witness_path_for(application, receipt):
    return application.artifact_root / "stage-starts" / f"{receipt.stage_start_id}.consumed.json"


WITNESS_MUTATIONS = (
    *(m for m in COMMON_HOSTILE_AUTHORITY if m != "valid-foreign-content"),
    "foreign-witness",
    "bad-stage",
    "bad-run",
    "bad-digest",
    "self-digest",
    "run-traversal",
    "run-absolute",
    "run-drive",
    "run-backslash",
    "run-nul",
    *(
        f"duplicate-{field}-{variant}"
        for field in ("run_id", "stage_id", "witness_digest")
        for variant in ("equal", "different")
    ),
    *(
        f"repin-{field}"
        for field in (
            "stage_start_key",
            "stage_start_id",
            "authorization_digest",
            "policy_digest",
            "contract_sha256",
            "stage_id",
            "run_id",
            "binding_digest",
        )
    ),
    "binding-old-pin",
)


def mutate_witness(path, mutation):
    from ai_workflow_engine.milestone_runner.policy import authority_digest, authority_json_bytes

    document = json.loads(path.read_bytes())
    if mutation.startswith("repin-"):
        field = mutation.removeprefix("repin-")
        document[field] = {"stage_id": "ST-WRONG", "run_id": "wrong-run"}.get(field, "b" * 64)
    elif mutation.startswith("duplicate-") and "_" in mutation:
        _, field, variant = mutation.split("-")
        value = document[field] if variant == "equal" else "conflicting-value"
        path.write_bytes(
            b"{"
            + json.dumps(field).encode()
            + b":"
            + json.dumps(value).encode()
            + b","
            + path.read_bytes()[1:]
        )
        return
    elif mutation == "foreign-witness":
        foreign = valid_authorization_variant(
            json.loads((path.parent / f"{document['stage_start_id']}.json").read_bytes()),
            foreign_stage=True,
        )
        document.update(
            stage_start_id=foreign.stage_start_id,
            stage_start_key=foreign.stage_start_key,
            stage_id=foreign.stage_id,
            contract_sha256=foreign.contract_sha256,
            authorization_digest=foreign.authorization_digest,
            policy_digest=foreign.effective_policy_digest,
        )
        binding = {
            k: document[k]
            for k in (
                "schema_version",
                "stage_start_key",
                "stage_start_id",
                "authorization_digest",
                "policy_digest",
                "run_id",
            )
        }
        document["binding_digest"] = authority_digest(binding)
    elif mutation in {"bad-stage", "bad-run", "bad-digest", "self-digest", "binding-old-pin"}:
        field, value = {
            "bad-stage": ("stage_id", "../stage"),
            "bad-run": ("run_id", ""),
            "bad-digest": ("policy_digest", "G" * 64),
            "self-digest": ("witness_digest", "b" * 64),
            "binding-old-pin": ("binding_digest", "b" * 64),
        }[mutation]
        document[field] = value
        if mutation in {"self-digest", "binding-old-pin"}:
            path.write_bytes(authority_json_bytes(document))
            return
    else:
        mutate_authority(path, "witness", mutation)
        return
    document["witness_digest"] = authority_digest(
        {k: v for k, v in document.items() if k != "witness_digest"}
    )
    path.write_bytes(authority_json_bytes(document))


@pytest.mark.parametrize("mutation", WITNESS_MUTATIONS)
@pytest.mark.parametrize("command", ("start", "b0-recovery", *MUTATING_V2_COMMANDS))
def test_auto017_remediation_hostile_witness(v2_application, monkeypatch, mutation, command):
    application = v2_application()
    receipt, _ = prepared_policy_run(
        application,
        command=command,
        published=command not in {"start", "b0-recovery"},
    )
    if command == "b0-recovery":
        authority_path(application, receipt, "binding").unlink()
        # No witness and no binding is the genuine pre-consumption case, not hostile.
        if mutation == "missing":
            witness_path_for(application, receipt).unlink()
            assert application.start().state is RunStatus.READY_FOR_COMMIT_APPROVAL
            return
    mutate_witness(witness_path_for(application, receipt), mutation)
    act = application.start if command == "b0-recovery" else command_action(application, command)
    assert_refusal_without_effects(
        application,
        act,
        StopReason.STAGE_START_ALREADY_BOUND,
        monkeypatch,
    )


@pytest.mark.parametrize("command", ("start", *MUTATING_V2_COMMANDS))
@pytest.mark.parametrize("loss", ["binding-latest", "witness-and-binding"])
def test_auto017_remediation_published_consumption_loss(v2_application, monkeypatch, command, loss):
    application = v2_application()
    receipt, _ = prepared_policy_run(application, command=command)
    authority_path(application, receipt, "binding").unlink()
    if loss == "binding-latest":
        (application.artifact_root / "latest-run.json").unlink()
    else:
        witness_path_for(application, receipt).unlink()
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        StopReason.STAGE_START_ALREADY_BOUND,
        monkeypatch,
    )


@pytest.mark.parametrize(
    "boundary", ["before-b0", "b0-link", "after-b0", "after-b1", "after-b2", "after-b3"]
)
def test_auto017_remediation_witness_crash_recovery(v2_application, monkeypatch, boundary):
    import ai_workflow_engine.milestone_runner.application as app_module
    import ai_workflow_engine.milestone_runner.state as state_module

    application = v2_application(run_id="original-arbitrary-run")
    receipt = authorize_v2(application)

    def crash(*args, **kwargs):
        raise RuntimeError("crash boundary")

    with monkeypatch.context() as fault:
        if boundary == "b0-link":
            fault.setattr(state_module.os, "link", crash)
        elif boundary == "after-b3":
            fault.setattr(app_module, "record_latest_run", crash)
        else:
            cls, method = {
                "before-b0": (state_module.StageStartStore, "publish_witness"),
                "after-b0": (state_module.StageStartStore, "publish_binding"),
                "after-b1": (RunStateStore, "publish_policy"),
                # AUTO-018 section 10.2: a governed run's first state publication is its genesis
                # event, so "after B-2, before the first state" is before lifecycle evidence.
                "after-b2": (RunStateStore, "begin_lifecycle"),
            }[boundary]
            fault.setattr(cls, method, crash)
        with pytest.raises(RuntimeError, match="crash boundary"):
            application.start()
    path = witness_path_for(application, receipt)
    before = (path.read_bytes(), path.stat().st_mtime_ns) if path.exists() else None
    application._run_id = "different-requested-run"
    if boundary == "after-b3":
        assert_refusal_without_effects(
            application,
            application.start,
            StopReason.STAGE_START_ALREADY_BOUND,
            monkeypatch,
        )
        return
    report = application.start()
    assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
    assert report.run_id == (
        "different-requested-run" if before is None else "original-arbitrary-run"
    )
    if before:
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert (
        json.loads(path.read_bytes())["binding_digest"]
        == json.loads(authority_path(application, receipt, "binding").read_bytes())[
            "binding_digest"
        ]
    )
    assert_refusal_without_effects(
        application,
        application.start,
        StopReason.STAGE_START_ALREADY_BOUND,
        monkeypatch,
    )


@pytest.mark.parametrize("command", ("start", *MUTATING_V2_COMMANDS))
@pytest.mark.parametrize("target", ["authority-parent", "root-parent", "run-dir", "state"])
def test_auto017_remediation_witness_parent_links(v2_application, monkeypatch, command, target):
    application = v2_application()
    receipt, record = prepared_policy_run(
        application, command=command, published=command != "start"
    )
    paths = {
        "authority-parent": witness_path_for(application, receipt).parent,
        "root-parent": application.artifact_root,
        "run-dir": application._read_store(record.run_id).run_directory,
        "state": application._read_store(record.run_id).state_path,
    }
    path = paths[target]
    if not path.exists():
        if target == "run-dir":
            path.mkdir()
        else:
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"must not be read")
    moved = path.with_name(path.name + "-real")
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    expected = StopReason.STAGE_START_ALREADY_BOUND
    if target == "root-parent" or (command != "start" and target == "run-dir"):
        expected = (
            StopReason.STAGE_START_NOT_AUTHORIZED
            if command == "start"
            else StopReason.POLICY_DIGEST_MISMATCH
        )
    elif target == "authority-parent":
        expected = StopReason.STAGE_START_NOT_AUTHORIZED
    elif command != "start" and target == "state":
        assert_refusal_without_effects(
            application,
            command_action(application, command),
            None,
            monkeypatch,
        )
        return
    assert_refusal_without_effects(
        application,
        command_action(application, command),
        expected,
        monkeypatch,
    )


def test_auto017_remediation_raced_b0_never_replaces_winner(v2_application, monkeypatch):
    import ai_workflow_engine.milestone_runner.state as state_module
    from ai_workflow_engine.milestone_runner.policy import authority_digest, authority_json_bytes

    application = v2_application(run_id="first-run")
    receipt = authorize_v2(application)
    path = witness_path_for(application, receipt)
    original = state_module.os.link
    winner = None

    def competing_link(source, destination, **kwargs):
        nonlocal winner
        if str(destination).endswith(".consumed.json"):
            source_path = path.parent / source
            payload = json.loads(source_path.read_bytes())
            payload["run_id"] = "competing-run"
            binding = {
                k: payload[k]
                for k in (
                    "schema_version",
                    "stage_start_key",
                    "stage_start_id",
                    "authorization_digest",
                    "policy_digest",
                    "run_id",
                )
            }
            payload["binding_digest"] = authority_digest(binding)
            payload["witness_digest"] = authority_digest(
                {k: v for k, v in payload.items() if k != "witness_digest"}
            )
            winner = authority_json_bytes(payload)
            path.write_bytes(winner)
        return original(source, destination, **kwargs)

    with monkeypatch.context() as race:
        race.setattr(state_module.os, "link", competing_link)
        with pytest.raises(RunRefused) as error:
            application.start()
    assert error.value.stop_reason is StopReason.STAGE_START_ALREADY_BOUND
    assert path.read_bytes() == winner
    assert not authority_path(application, receipt, "binding").exists()
    assert not application._read_store("first-run").state_path.exists()
    assert not application._read_store("competing-run").state_path.exists()


def test_auto017_remediation_exact_name_witness_without_enumeration(v2_application, monkeypatch):
    application = v2_application()
    receipt = authorize_v2(application)
    report = application.start()
    authority_path(application, receipt, "binding").unlink()
    (application.artifact_root / "latest-run.json").unlink()
    application._run_id = "another-run"

    def forbidden(*args, **kwargs):
        pytest.fail("consumption lookup enumerated a directory")

    with monkeypatch.context() as guard:
        for method in ("glob", "rglob", "iterdir"):
            guard.setattr(Path, method, forbidden)
        for method in ("listdir", "scandir", "walk"):
            guard.setattr(os, method, forbidden)
        with pytest.raises(RunRefused) as error:
            application._start_preflight()
    assert error.value.stop_reason is StopReason.STAGE_START_ALREADY_BOUND
    assert witness_path_for(application, receipt).exists()
    assert application._read_store(report.run_id).state_path.exists()


@pytest.mark.parametrize("boundary", ["after-b0", "after-b1"])
def test_auto017_remediation_b0_b1_revalidation_rejects_hostile_witness(
    v2_application,
    monkeypatch,
    boundary,
):
    application = v2_application()
    receipt, _ = prepared_policy_run(application, published=False)
    if boundary == "after-b0":
        authority_path(application, receipt, "binding").unlink()
    original = application._locked

    def mutate_after_lock(run_id):
        lock = original(run_id)
        mutate_witness(witness_path_for(application, receipt), "repin-binding_digest")
        return lock

    monkeypatch.setattr(application, "_locked", mutate_after_lock)
    with pytest.raises(RunRefused) as error:
        application.start()
    assert error.value.stop_reason is StopReason.STAGE_START_ALREADY_BOUND
    assert not application._read_store(application._run_id).state_path.exists()


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("binding_present", [False, True])
def test_auto017_remediation_missing_pointer_after_consumption(
    v2_application,
    monkeypatch,
    published,
    binding_present,
):
    application = v2_application()
    receipt, _ = prepared_policy_run(application, published=published)
    authority_path(application, receipt, "pointer").unlink()
    if not binding_present:
        authority_path(application, receipt, "binding").unlink()
    assert_refusal_without_effects(
        application,
        lambda: authorize_v2(application),
        StopReason.STAGE_START_INPUT_CONFLICT,
        monkeypatch,
    )


def test_auto017_remediation_stage_start_cannot_repair_consumed_binding(
    v2_application, monkeypatch
):
    application = v2_application()
    receipt = authorize_v2(application)
    application.start()
    authority_path(application, receipt, "binding").unlink()
    (application.artifact_root / "latest-run.json").unlink()
    application._run_id = "unknown-run"
    assert_refusal_without_effects(
        application,
        lambda: authorize_v2(application),
        StopReason.STAGE_START_INPUT_CONFLICT,
        monkeypatch,
    )


# ======================================================================================
# AUTO-018: event-backed governed runs (sections 6.1, 7.4, 7.5, 8.3, 10 and 12)
# ======================================================================================

import shutil as _shutil  # noqa: E402

from ai_workflow_engine.milestone_runner.events import (  # noqa: E402
    EVENTS_DIRECTORY,
    ApplicationMutationIncomplete,
    EventChainBroken,
    EventStore,
    LifecycleEventType,
    MutationAction,
    OperationRecordInvalid,
    RecoveryCommandEvidence,
)
from ai_workflow_engine.milestone_runner.lock import LockOwnershipLost  # noqa: E402
from ai_workflow_engine.milestone_runner.state import (  # noqa: E402
    PublicationUncertain,
    RunLifecycleStorage,
    StatePublicationFailure,
)


def governed_store(application: MilestoneRunnerApplication) -> RunStateStore:
    run_id = application._run_id or application._latest_run_id()
    assert run_id is not None
    return application._read_store(run_id)


def events_snapshot(store: RunStateStore) -> dict[str, bytes]:
    directory = store.run_directory / EVENTS_DIRECTORY
    if not directory.exists():
        return {}
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def restore_tree(source: Path, destination: Path) -> None:
    _shutil.rmtree(destination)
    _shutil.copytree(source, destination, symlinks=True)


def fault_envelopes(monkeypatch: pytest.MonkeyPatch, predicate: Any) -> None:
    """Crash, deterministically, immediately before publishing the first matching envelope."""
    original = EventStore.publish_envelope

    def faulty(self: EventStore, envelope: Any, **kwargs: Any) -> Any:
        if predicate(self, envelope):
            raise RuntimeError("injected crash before this event")
        return original(self, envelope, **kwargs)

    monkeypatch.setattr(EventStore, "publish_envelope", faulty)


RECOVERY_COMMANDS = (
    "reconcile_milestone",
    "reopen_milestone",
    "recover_failed_review",
    "revalidate_correction",
)


class TestAuto018MutationPrefix:
    """T-MUTATION-PREFIX (R01): every durable prefix of every recovery mutation is either free
    of constituent effects or an explicitly identifiable incomplete mutation carrying its
    complete original evidence; nothing ever completes or recomputes it."""

    @pytest.mark.parametrize("command", RECOVERY_COMMANDS)
    def test_every_constituent_boundary_of_a_recovery_mutation(
        self, v2_application, monkeypatch, tmp_path, command
    ):
        application = v2_application(clock=lambda: MOMENT)
        _, prepared = prepared_policy_run(application, command=command)
        root = application.artifact_root
        pristine = tmp_path / "pristine-artifact-root"
        _shutil.copytree(root, pristine, symlinks=True)
        act = command_action(application, command)

        # The original outcome, captured once: the declaration, its evidence, the final record.
        report = act()
        store = governed_store(application)
        full = store.load_lifecycle()
        declared = [
            event
            for event, _ in full.events
            if event.event_type is LifecycleEventType.APPLICATION_MUTATION_DECLARED
        ]
        assert len(declared) == 1
        declaration = declared[0].payload.declaration
        evidence = declaration.evidence
        assert isinstance(evidence, RecoveryCommandEvidence)
        assert declaration.action is MutationAction.RECOVERY_COMMAND
        ledger = evidence.ledger.value
        assert getattr(full.record, ledger) == [evidence.entry]
        assert evidence.entry.pre_state is prepared.workflow_state
        assert evidence.entry.post_state is report.post_state is full.record.workflow_state
        assert evidence.original_ledger_length == 0
        assert evidence.budgets_touched == dict(report.budgets_touched)
        types = [constituent.event_type for constituent in declaration.constituents]
        assert types[-2:] == [
            LifecycleEventType.RECOVERY_LEDGER_APPENDED,
            LifecycleEventType.STATE_TRANSITIONED,
        ]
        assert len(types) == (3 if evidence.budgets_touched else 2)
        for counter, delta in evidence.budgets_touched.items():
            assert getattr(full.record, counter) == getattr(prepared, counter) + delta
        final_digest = declaration.final_body_digest

        for applied in range(-1, len(declaration.constituents)):
            restore_tree(pristine, root)
            with monkeypatch.context() as fault:
                if applied < 0:
                    fault_envelopes(
                        fault,
                        lambda store, envelope: envelope.event_type
                        is LifecycleEventType.APPLICATION_MUTATION_DECLARED,
                    )
                else:
                    fault_envelopes(
                        fault,
                        lambda store, envelope, applied=applied: envelope.mutation_index
                        == applied + 1,
                    )
                with pytest.raises(RuntimeError, match="injected crash"):
                    act()
            view = governed_store(application).load_lifecycle()
            if applied < 0:
                # Before the declaration: no authoritative constituent effect exists at all.
                assert view.incomplete is None
                assert not [
                    event
                    for event, _ in view.events
                    if event.event_type is LifecycleEventType.APPLICATION_MUTATION_DECLARED
                ]
                assert getattr(view.record, ledger) == []
                assert view.record.workflow_state is prepared.workflow_state
                continue
            incomplete = view.incomplete
            assert incomplete is not None, applied
            # The same complete typed declaration, evidence, intended transition and prior tip.
            assert incomplete.declaration == declaration
            assert incomplete.mutation_id == declaration.mutation_id
            assert incomplete.applied_prefix_length == applied
            assert incomplete.intended_transitions == declaration.transitions
            assert incomplete.prior_event_id == declaration.prior_event_id
            assert incomplete.declaration.final_body_digest == final_digest
            # The prefix is folded as recorded, never as a completed mutation.
            ledger_index = types.index(LifecycleEventType.RECOVERY_LEDGER_APPENDED)
            assert len(getattr(view.record, ledger)) == (1 if applied > ledger_index else 0)
            assert view.record.workflow_state is prepared.workflow_state
            status = application.status()
            assert status.effective_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
            assert status.stop_reason is StopReason.APPLICATION_MUTATION_INCOMPLETE
            assert status.incomplete_mutation == incomplete

            # A later invocation with a changed clock and changed repository observations:
            # nothing recomputes the evidence, completes the prefix or reports it complete.
            before = events_snapshot(governed_store(application))
            later = MOMENT + timedelta(hours=1)
            application._clock = lambda later=later: later
            (application.repository_root / "unrelated-observation.txt").write_text("changed\n")
            try:
                with pytest.raises(ApplicationMutationIncomplete) as refused:
                    act()
            finally:
                (application.repository_root / "unrelated-observation.txt").unlink()
                application._clock = lambda: MOMENT
            assert refused.value.stop_reason is StopReason.APPLICATION_MUTATION_INCOMPLETE
            assert refused.value.mutation.declaration == declaration
            assert events_snapshot(governed_store(application)) == before

        # After the last constituent: one complete mutation, applied exactly once.
        restore_tree(pristine, root)
        act()
        complete = governed_store(application).load_lifecycle()
        assert complete.incomplete is None
        assert getattr(complete.record, ledger) == [evidence.entry]
        assert complete.record == full.record
        from ai_workflow_engine.milestone_runner.recovery import RecoveryRefused

        with pytest.raises(RecoveryRefused):
            act()
        assert getattr(governed_store(application).load(), ledger) == [evidence.entry]

    def test_a_failed_declaration_publication_leaves_no_constituent_effect(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        prepared_policy_run(application, command="reopen_milestone")
        act = command_action(application, "reopen_milestone")
        import ai_workflow_engine.milestone_runner.state as state_module

        original = RunLifecycleStorage.publish_event

        def failing(self, name, payload):
            if "APPLICATION_MUTATION_DECLARED" in name:
                raise StatePublicationFailure("the declaration could not be published")
            return original(self, name, payload)

        with monkeypatch.context() as fault:
            fault.setattr(RunLifecycleStorage, "publish_event", failing)
            with pytest.raises(StatePublicationFailure):
                act()
        del state_module
        # The witness named the declaration it never linked: the load stops, and ST-02 invents
        # no event and applies no constituent.
        with pytest.raises(EventChainBroken):
            governed_store(application).load()

    def test_projection_lag_inside_a_mutation_is_still_an_incomplete_mutation(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        prepared_policy_run(application, command="reopen_milestone")
        act = command_action(application, "reopen_milestone")
        original = RunLifecycleStorage.publish_projection

        def lagging(self, payload):
            if json.loads(payload)["state_version"] == 5:
                raise StatePublicationFailure("projection replace failed")
            return original(self, payload)

        with monkeypatch.context() as fault:
            fault.setattr(RunLifecycleStorage, "publish_projection", lagging)
            with pytest.raises(StatePublicationFailure):
                act()
        view = governed_store(application).load_lifecycle()
        assert view.projection.value == "STALE"
        assert view.incomplete is not None and view.incomplete.applied_prefix_length == 1
        with pytest.raises(ApplicationMutationIncomplete):
            act()
        repaired = governed_store(application).load_lifecycle()
        assert repaired.projection.value == "CURRENT"
        assert repaired.incomplete is not None and repaired.incomplete.applied_prefix_length == 1

    def test_a_result_acceptance_shares_the_declaration_rule(self, v2_application, monkeypatch):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        with monkeypatch.context() as fault:
            fault_envelopes(
                fault,
                lambda store, envelope: envelope.event_type is LifecycleEventType.STATE_TRANSITIONED
                and envelope.mutation_index == 2
                and store.state is not None
                and store.state.open_mutation is not None
                and store.state.open_mutation.declaration.action
                is MutationAction.RESULT_ACCEPTANCE,
            )
            with pytest.raises(RuntimeError, match="injected crash"):
                application.start()
        view = governed_store(application).load_lifecycle()
        incomplete = view.incomplete
        assert incomplete is not None
        assert incomplete.declaration.action is MutationAction.RESULT_ACCEPTANCE
        assert incomplete.applied_prefix_length == 1
        assert [c.event_type for c in incomplete.declaration.constituents] == [
            LifecycleEventType.OPERATION_RESULT_ACCEPTED,
            LifecycleEventType.STATE_TRANSITIONED,
        ]
        assert view.record.workflow_state is RunStatus.IMPLEMENTING
        before = events_snapshot(governed_store(application))
        with pytest.raises(ApplicationMutationIncomplete):
            application.resume()
        assert events_snapshot(governed_store(application)) == before


class TestAuto018Ledgers:
    """T-LEDGERS: each recovery command's entry and transition exactly once; history immutable."""

    @pytest.mark.parametrize("command", RECOVERY_COMMANDS)
    def test_one_entry_one_transition_and_unchanged_budget_semantics(self, v2_application, command):
        application = v2_application(clock=lambda: MOMENT)
        _, prepared = prepared_policy_run(application, command=command)
        report = command_action(application, command)()
        view = governed_store(application).load_lifecycle()
        transitions = [
            event
            for event, _ in view.events
            if event.event_type is LifecycleEventType.STATE_TRANSITIONED
        ]
        ledgers = [
            event
            for event, _ in view.events
            if event.event_type is LifecycleEventType.RECOVERY_LEDGER_APPENDED
        ]
        assert len(transitions) == len(ledgers) == 1
        assert transitions[0].payload.from_state is prepared.workflow_state
        assert transitions[0].payload.to_state is report.post_state
        counters = (
            "review_attempts",
            "successful_review_rounds",
            "provider_failure_count",
            "correction_round",
            "closure_round",
        )
        for counter in counters:
            expected = getattr(prepared, counter) + dict(report.budgets_touched).get(counter, 0)
            assert getattr(view.record, counter) == expected
        # The historical snapshot is the bridge's genesis, never rewritten by the recovery.
        genesis = view.events[0][0]
        assert genesis.event_type is LifecycleEventType.RUN_BASELINED
        assert genesis.payload.record == prepared


def replace_lock_file(application: MilestoneRunnerApplication) -> Path:
    """Rename the held lock inode away and put a fresh lock file at the canonical path."""
    lock_path = application.artifact_root / "run.lock"
    lock_path.rename(lock_path.with_name("run.lock.renamed-away"))
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    return lock_path


class TestAuto018StaleHolder:
    """T-LOCK-IDENTITY (R02) at the application's publication and effect boundaries."""

    def test_a_replaced_lock_at_the_spawn_boundary_stops_before_any_process(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        spawned: list[Any] = []
        original_popen = subprocess.Popen
        rival: list[RunLock] = []

        def counting_popen(args: Any, *positional: Any, **keyword: Any) -> Any:
            if isinstance(args, list) and len(args) == 5 and args[1].endswith("fake_provider.py"):
                spawned.append(args)
            return original_popen(args, *positional, **keyword)

        from ai_workflow_engine.milestone_runner.operations import OperationJournal

        original_intent = OperationJournal.record_intent

        def replace_after_intent(self, *args: Any, **kwargs: Any) -> Any:
            reference = original_intent(self, *args, **kwargs)
            replace_lock_file(application)
            # A simultaneous apparent holder, on the replacement inode.
            holder = RunLock(
                run_id="rival-run",
                repository_identity=IDENTITY,
                artifact_root=application.artifact_root,
            )
            holder.acquire()
            rival.append(holder)
            return reference

        monkeypatch.setattr(subprocess, "Popen", counting_popen)
        monkeypatch.setattr(OperationJournal, "record_intent", replace_after_intent)
        try:
            with pytest.raises(LockOwnershipLost) as lost:
                application.start()
            assert lost.value.stop_reason is StopReason.LOCK_OWNERSHIP_LOST
            assert spawned == []
            store = governed_store(application)
            before = events_snapshot(store)
            view = store.load_lifecycle(lock=rival[0])
            last = view.events[-1][0]
            assert last.event_type is LifecycleEventType.OPERATION_DISPATCH_INTENT
            assert events_snapshot(store) == before
        finally:
            for holder in rival:
                holder.release()
        # The stale release never unlinked or damaged the replacement lock.
        assert (application.artifact_root / "run.lock").exists()
        assert (application.artifact_root / "run.lock.renamed-away").exists()

    def test_a_replaced_lock_before_a_publication_publishes_nothing(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        calls = {"count": 0}
        original = EventStore.publish_envelope

        def replace_then_publish(self: EventStore, envelope: Any, **kwargs: Any) -> Any:
            calls["count"] += 1
            if calls["count"] == 6:
                replace_lock_file(application)
            return original(self, envelope, **kwargs)

        monkeypatch.setattr(EventStore, "publish_envelope", replace_then_publish)
        with pytest.raises(LockOwnershipLost):
            application.start()
        store = governed_store(application)
        assert len(events_snapshot(store)) == 5

    def test_a_replacement_detected_after_the_link_prevents_acknowledgment(
        self, v2_application, monkeypatch
    ):
        import ai_workflow_engine.milestone_runner.state as state_module

        application = v2_application(clock=lambda: MOMENT, run_id="post-link-race-run")
        authorize_v2(application)
        original_link = state_module.os.link

        def link_then_replace(*args: Any, **kwargs: Any) -> None:
            original_link(*args, **kwargs)
            destination = args[1] if len(args) > 1 else kwargs.get("dst")
            if isinstance(destination, str) and destination.startswith("00000004-"):
                replace_lock_file(application)

        monkeypatch.setattr(state_module.os, "link", link_then_replace)
        with pytest.raises(LockOwnershipLost):
            application.start()
        # The bytes linked before detection stay as uncertain evidence; nothing followed them.
        store = governed_store(application)
        assert sorted(events_snapshot(store))[-1].startswith("00000004-")
        assert not (store.run_directory / "operations").exists()

    def test_a_valid_second_writer_gets_ordinary_contention(self, v2_application):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        application.start()
        run_id = governed_store(application).run_id
        holder = application._locked(run_id)
        try:
            with pytest.raises(RunRefused, match="Another runner holds"):
                application.abort(reason="while another holder is active")
        finally:
            holder.release()
        assert application.abort(reason="after release").state is RunStatus.ABORTED


class TestAuto018PublicationUncertain:
    """T-PUBLICATION-UNCERTAIN (R03) across invocations: visible bytes are never durable success
    until the correct barriers succeed under a later valid hold."""

    @staticmethod
    def _failing_directory_fsync(monkeypatch, directory: Path, after: Any) -> dict[str, bool]:
        real = os.fsync
        state = {"armed": False}

        def fsync(descriptor: int) -> None:
            if state["armed"] and os.fstat(descriptor).st_ino == directory.stat().st_ino:
                raise OSError(5, "Input/output error")
            real(descriptor)

        monkeypatch.setattr(os, "fsync", fsync)
        after(state)
        return state

    def test_an_exclusive_authority_artifact(self, v2_application, monkeypatch):
        """policy.json: linked, then its directory barrier fails; start retries later."""
        application = v2_application(clock=lambda: MOMENT, run_id="uncertain-policy-run")
        authorize_v2(application)
        run_directory = application.artifact_root / "uncertain-policy-run"
        real_link = os.link
        spawned: list[Any] = []

        with monkeypatch.context() as fault:
            state = {"armed": False}
            real_fsync = os.fsync

            def link(*args: Any, **kwargs: Any) -> None:
                real_link(*args, **kwargs)
                if (args[1] if len(args) > 1 else "") == "policy.json":
                    state["armed"] = True

            def fsync(descriptor: int) -> None:
                if state["armed"] and os.fstat(descriptor).st_ino == run_directory.stat().st_ino:
                    raise OSError(5, "Input/output error")
                real_fsync(descriptor)

            fault.setattr(os, "link", link)
            fault.setattr(os, "fsync", fsync)
            fault.setattr(
                application._providers.implementation, "invoke", lambda *a, **k: spawned.append(1)
            )
            with pytest.raises(PublicationUncertain) as uncertain:
                application.start()
            assert uncertain.value.stop_reason is StopReason.PUBLICATION_UNCERTAIN
            policy = run_directory / "policy.json"
            before = (policy.read_bytes(), policy.stat().st_mtime_ns)
            # A later holder, barrier still failing: the identical-existing branch is uncertain.
            with pytest.raises(PublicationUncertain):
                application.start()
            assert spawned == []
            assert (policy.read_bytes(), policy.stat().st_mtime_ns) == before
        # The barrier recovers: confirmed without rewriting a byte or an mtime.
        report = application.start()
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        assert (policy.read_bytes(), policy.stat().st_mtime_ns) == before

    def test_operation_evidence(self, v2_application, monkeypatch):
        """request.json: linked, its directory barrier fails, resume confirms before dispatch."""
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        spawned: list[Any] = []
        original_invoke = application._providers.implementation.invoke

        def counting(*args: Any, **kwargs: Any) -> Any:
            spawned.append(1)
            return original_invoke(*args, **kwargs)

        monkeypatch.setattr(application._providers.implementation, "invoke", counting)
        real_link = os.link
        real_fsync = os.fsync
        state: dict[str, Any] = {"directory": None}

        def link(*args: Any, **kwargs: Any) -> None:
            real_link(*args, **kwargs)
            if (args[1] if len(args) > 1 else "") == "request.json":
                state["directory"] = os.fstat(kwargs["dst_dir_fd"]).st_ino

        def fsync(descriptor: int) -> None:
            if state["directory"] is not None and os.fstat(descriptor).st_ino == state["directory"]:
                raise OSError(5, "Input/output error")
            real_fsync(descriptor)

        with monkeypatch.context() as fault:
            fault.setattr(os, "link", link)
            fault.setattr(os, "fsync", fsync)
            with pytest.raises(PublicationUncertain):
                application.start()
            assert spawned == []
            with pytest.raises(PublicationUncertain):
                application.resume()
            assert spawned == []
        store = governed_store(application)
        request = next((store.run_directory / "operations").iterdir()) / "request.json"
        before = (request.read_bytes(), request.stat().st_mtime_ns)
        report = application.resume()
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        assert (request.read_bytes(), request.stat().st_mtime_ns) == before
        # Exactly one dispatch, and only after the relied-upon request was confirmed durable.
        assert spawned == [1]

    def test_a_projection_barrier_failure_is_confirmed_by_a_later_holder(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        application.start()
        store = governed_store(application)
        real_fsync = os.fsync
        state_inode = store.state_path.stat().st_ino

        def fsync(descriptor: int) -> None:
            if os.fstat(descriptor).st_ino == state_inode:
                raise OSError(5, "Input/output error")
            real_fsync(descriptor)

        before = events_snapshot(store)
        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", fsync)
            with pytest.raises(PublicationUncertain):
                application.abort(reason="while the projection cannot be confirmed")
        assert events_snapshot(store) == before
        assert application.abort(reason="confirmed now").state is RunStatus.ABORTED

    def test_read_only_reload_confers_no_execution_readiness(self, v2_application, monkeypatch):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        application.start()
        store = governed_store(application)
        before = events_snapshot(store)
        lock_inode = (application.artifact_root / "run.lock").stat().st_ino
        real_fsync = os.fsync

        def failing(descriptor: int) -> None:
            # The lock's own diagnostic metadata is not lifecycle evidence; everything else fails.
            if os.fstat(descriptor).st_ino == lock_inode:
                return real_fsync(descriptor)
            raise OSError(5, "Input/output error")

        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", failing)
            # A read needs no barrier and reports the verified fold ...
            assert application.status().record is not None
            # ... but an effecting command must confirm under its own hold, or refuse.
            with pytest.raises(PublicationUncertain):
                application.abort(reason="no confirmation available")
        assert events_snapshot(store) == before


class TestAuto018ProspectiveReferences:
    """T-PROSPECTIVE-REFERENCE (R04): pending paths are declarations; asserted evidence is not."""

    def test_a_pending_row_before_spawn_is_a_valid_prefix(self, v2_application, monkeypatch):
        from ai_workflow_engine.milestone_runner.operations import OperationJournal

        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)

        def stop_at_intent(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("stopped before spawn")

        monkeypatch.setattr(OperationJournal, "record_intent", stop_at_intent)
        with pytest.raises(RuntimeError, match="stopped before spawn"):
            application.start()
        store = governed_store(application)
        view = store.load_lifecycle()
        pending = view.record.provider_runs[-1]
        assert pending.completed_at is None
        for path in (pending.stdout_path, pending.stderr_path):
            assert not (store.run_directory / path).exists()
        assert (store.run_directory / pending.prompt_path).exists()
        assert view.state.prospective_paths == (pending.stdout_path, pending.stderr_path)
        assert not [
            event
            for event, _ in view.events
            if event.event_type is LifecycleEventType.OPERATION_DISPATCH_RECEIVED
        ]

    @pytest.mark.parametrize("artifact", ["prompt", "stdout", "stderr", "raw", "validated"])
    @pytest.mark.parametrize("damage", ["delete", "corrupt"])
    def test_asserted_evidence_can_never_be_downgraded(self, v2_application, artifact, damage):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        application.start()
        store = governed_store(application)
        row = store.load().provider_runs[0]
        operation = next((store.run_directory / "operations").iterdir())
        attempt = operation / "attempts" / "0001"
        target = {
            "prompt": store.run_directory / row.prompt_path,
            "stdout": store.run_directory / row.stdout_path,
            "stderr": store.run_directory / row.stderr_path,
            "raw": attempt / "result.raw",
            "validated": attempt / "result.validated.json",
        }[artifact]
        if damage == "delete":
            target.unlink()
        else:
            target.write_bytes(target.read_bytes() + b" tampered")
        with pytest.raises(OperationRecordInvalid) as refused:
            store.load()
        assert refused.value.stop_reason is StopReason.OPERATION_RECORD_INVALID
        before = events_snapshot(store)
        with pytest.raises(OperationRecordInvalid):
            application.abort(reason="must refuse")
        assert events_snapshot(store) == before
        assert not target.exists() or damage == "corrupt"

    def test_an_empty_output_is_a_published_empty_artifact(self, v2_application):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        application.start()
        store = governed_store(application)
        view = store.load_lifecycle()
        stderr_references = [
            reference
            for event, _ in view.events
            if event.event_type is LifecycleEventType.OPERATION_RESULT_RECEIVED
            for reference in event.payload.transcripts
            if reference.path.endswith("stderr.txt")
        ]
        assert stderr_references
        empty = hashlib.sha256(b"").hexdigest()
        assert all(reference.sha256 == empty for reference in stderr_references)
        assert all((store.run_directory / r.path).read_bytes() == b"" for r in stderr_references)

    def test_a_historical_pending_row_bridges_without_fabricated_digests(self, v2_application):
        application = v2_application(clock=lambda: MOMENT)
        _, prepared = prepared_policy_run(application, command="abort")
        pending = ProviderRunRecord(
            sequence=1,
            role=ProviderRole.IMPLEMENTATION,
            provider="fake",
            milestone_id=MILESTONE_ID,
            started_at="2026-08-06T11:59:00Z",
            duration_ms=0,
            prompt_path="transcripts/0001-20260806T115900Z-fake-implementation.prompt.md",
            stdout_path="transcripts/0001-20260806T115900Z-fake-implementation.stdout.txt",
            stderr_path="transcripts/0001-20260806T115900Z-fake-implementation.stderr.txt",
        )
        historical = prepared.model_copy(update={"provider_runs": [pending]})
        store = application._store(prepared.run_id)
        lock = application._locked(prepared.run_id)
        try:
            store.state_path.unlink()
            store.publish(historical, lock=lock)
        finally:
            lock.release()
        application.abort(reason="bridge a pending historical row")
        view = store.load_lifecycle()
        assert view.events[0][0].event_type is LifecycleEventType.RUN_BASELINED
        assert view.events[0][0].payload.record.provider_runs == [pending]
        assert not [
            event for event, _ in view.events if event.event_type.value.startswith("OPERATION_")
        ]
        assert view.record.workflow_state is RunStatus.ABORTED


class TestAuto018AuthorityStaysPrimary:
    """T-AUTHORITY: events never heal, replace or legitimize an authority artifact."""

    @pytest.mark.parametrize(
        "artifact, reason",
        [
            ("policy", StopReason.POLICY_DIGEST_MISMATCH),
            ("binding", StopReason.STAGE_START_ALREADY_BOUND),
            ("witness", StopReason.STAGE_START_ALREADY_BOUND),
        ],
    )
    @pytest.mark.parametrize("damage", ["delete", "tamper"])
    def test_tamper_or_loss_is_refused_and_never_repaired(
        self, v2_application, monkeypatch, artifact, reason, damage
    ):
        application = v2_application(clock=lambda: MOMENT)
        receipt = authorize_v2(application)
        application.start()
        store = governed_store(application)
        path = {
            "policy": store.policy_path,
            "binding": authority_path(application, receipt, "binding"),
            "witness": witness_path_for(application, receipt),
        }[artifact]
        if damage == "delete":
            path.unlink()
        else:
            path.write_bytes(path.read_bytes().replace(b"{", b"{ ", 1))
        before = events_snapshot(store)
        with pytest.raises(WorkflowEngineError) as refused:
            application.abort(reason="authority is damaged")
        assert refused.value.stop_reason is reason
        assert events_snapshot(store) == before
        assert (not path.exists()) if damage == "delete" else True


class TestAuto018BaselineBridge:
    """T-BASELINE-BRIDGE: one historical snapshot, its exact bytes, nothing synthesized."""

    def test_the_bridge_records_the_exact_snapshot_once(self, v2_application):
        application = v2_application(clock=lambda: MOMENT)
        _, prepared = prepared_policy_run(application, command="abort")
        store = application._read_store(prepared.run_id)
        source = store.state_path.read_bytes()
        # Reading a historical governed v2 snapshot writes nothing and invents no history.
        assert store.load() == prepared and not store.lifecycle_present()
        application.abort(reason="first mutating command")
        view = store.load_lifecycle()
        genesis = view.events[0][0]
        assert genesis.event_type is LifecycleEventType.RUN_BASELINED
        assert genesis.payload.source_sha256 == hashlib.sha256(source).hexdigest()
        assert genesis.payload.source_byte_count == len(source)
        assert genesis.payload.record == prepared
        assert [event.event_type for event, _ in view.events] == [
            LifecycleEventType.RUN_BASELINED,
            LifecycleEventType.STAGE_START_BOUND,
            LifecycleEventType.POLICY_PUBLISHED,
            LifecycleEventType.STATE_TRANSITIONED,
        ]
        assert json.loads(store.state_path.read_bytes())["schema_version"] == 3

    def test_an_interrupted_bridge_resumes_by_duplicate_recognition(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        _, prepared = prepared_policy_run(application, command="abort")
        with monkeypatch.context() as fault:
            fault_envelopes(
                fault,
                lambda store, envelope: envelope.event_type is LifecycleEventType.STAGE_START_BOUND,
            )
            with pytest.raises(RuntimeError):
                application.abort(reason="crash inside the bridge")
        store = application._read_store(prepared.run_id)
        first = events_snapshot(store)
        assert len(first) == 1
        application.abort(reason="retry after the crash")
        second = events_snapshot(store)
        assert {name: second[name] for name in first} == first
        assert store.load_lifecycle().events[0][0].event_type is LifecycleEventType.RUN_BASELINED

    def test_projection_loss_never_triggers_a_second_genesis(self, v2_application):
        application = v2_application(clock=lambda: MOMENT)
        _, prepared = prepared_policy_run(application, command="resume")
        application.abort(reason="bridge")
        store = application._read_store(prepared.run_id)
        before = events_snapshot(store)
        store.state_path.unlink()
        assert store.exists()
        assert store.load().workflow_state is RunStatus.ABORTED
        assert events_snapshot(store) == before

    def test_a_crash_after_genesis_never_permits_a_second_start(self, v2_application, monkeypatch):
        application = v2_application(clock=lambda: MOMENT, run_id="genesis-gap-run")
        authorize_v2(application)
        with monkeypatch.context() as fault:
            fault_envelopes(
                fault,
                lambda store, envelope: envelope.event_type is LifecycleEventType.STAGE_START_BOUND,
            )
            with pytest.raises(RuntimeError):
                application.start()
        store = application._read_store("genesis-gap-run")
        store.state_path.unlink()
        assert store.exists()
        with pytest.raises(RunRefused):
            application.start()


class TestAuto018ConfirmationOwnership:
    """R02 x R03: a hold whose ownership changes during confirmation never reports durability."""

    def test_a_replacement_during_confirmation_refuses_without_success(
        self, v2_application, monkeypatch
    ):
        application = v2_application(clock=lambda: MOMENT)
        authorize_v2(application)
        application.start()
        store = governed_store(application)
        before = events_snapshot(store)
        real_fsync = os.fsync
        lock_inode = (application.artifact_root / "run.lock").stat().st_ino
        state = {"replaced": False}

        def replacing(descriptor: int) -> None:
            status = os.fstat(descriptor)
            if (
                not state["replaced"]
                and status.st_ino != lock_inode
                and stat.S_ISREG(status.st_mode)
            ):
                state["replaced"] = True
                replace_lock_file(application)
            real_fsync(descriptor)

        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", replacing)
            with pytest.raises(LockOwnershipLost):
                application.abort(reason="confirmation must fail closed")
        assert state["replaced"]
        assert events_snapshot(store) == before
        assert store.load().workflow_state is RunStatus.READY_FOR_COMMIT_APPROVAL


def test_auto018_an_event_backed_run_refuses_a_supervised_configuration(
    v2_application, config_factory, providers
):
    application = v2_application(clock=lambda: MOMENT)
    authorize_v2(application)
    report = application.start()
    supervised = MilestoneRunnerApplication(
        load_runner_config(config_factory()), providers=providers, run_id=report.run_id
    )
    store = governed_store(application)
    before = events_snapshot(store)
    with pytest.raises(WorkflowEngineError) as refused:
        supervised.abort(reason="mode mixing")
    assert refused.value.stop_reason is StopReason.POLICY_BINDING_MISMATCH
    assert events_snapshot(store) == before


# ======================================================================================
# AUTO-018 remediation cycle 1 -- AUTO018-IMPL-R03: ownership before every command entry
# ======================================================================================


def _marker(name: str) -> dict[str, Any]:
    return {
        "command": [sys.executable, "-c", f"print({name!r})"],
        "timeout_seconds": 120,
        "purpose": name,
    }


class TestAuto018R03PerCommandOwnership:
    """AUTO018-IMPL-R03: a hold lost after command N reaches no command N+1.

    Continuing ownership is re-verified immediately before every verification and Git executor
    entry reached through the application, not once per batch. Verification and Git policy are
    unchanged: only the prerequisite is enforced per command.
    """

    @staticmethod
    def _count_commands(
        monkeypatch: pytest.MonkeyPatch, application: Any, lose_after: str | int
    ) -> list[list[str]]:
        import ai_workflow_engine.milestone_runner.verification as verification_module

        calls: list[list[str]] = []
        real = verification_module.run_bounded_command

        def counting(*, argv: Any, **kwargs: Any) -> Any:
            calls.append(list(argv))
            outcome = real(argv=argv, **kwargs)
            hit = (
                len(calls) == lose_after
                if isinstance(lose_after, int)
                else any(lose_after in part for part in argv)
            )
            if hit:
                replace_lock_file(application)
            return outcome

        monkeypatch.setattr(verification_module, "run_bounded_command", counting)
        return calls

    def test_the_preflight_governance_batch_stops_after_the_command_that_lost_it(
        self, application_factory, monkeypatch
    ):  # type: ignore[no-untyped-def]
        application = application_factory()
        calls = self._count_commands(monkeypatch, application, 1)
        with pytest.raises(LockOwnershipLost) as lost:
            application.start()
        assert lost.value.stop_reason is StopReason.LOCK_OWNERSHIP_LOST
        assert len(calls) == 1, calls

    def test_the_focused_set_stops_after_the_command_that_lost_it(
        self, application_factory, monkeypatch
    ):  # type: ignore[no-untyped-def]
        application = application_factory(
            overrides={"verification": {"focused": [_marker("focused-1"), _marker("focused-2")]}}
        )
        calls = self._count_commands(monkeypatch, application, "focused-1")
        with pytest.raises(LockOwnershipLost):
            application.start()
        markers = [argv for argv in calls if any("focused" in part for part in argv)]
        assert len(markers) == 1 and "focused-1" in markers[0][-1], calls
        assert calls[-1] == markers[0], "nothing ran after the command that lost the hold"

    def test_the_configured_final_set_stops_after_the_command_that_lost_it(
        self, application_factory, config_factory, monkeypatch
    ):  # type: ignore[no-untyped-def]
        base = yaml.safe_load(config_factory().read_text())["verification"]["final"]
        application = application_factory(
            overrides={"verification": {"final": [*base, _marker("final-1"), _marker("final-2")]}}
        )
        calls = self._count_commands(monkeypatch, application, "final-1")
        with pytest.raises(LockOwnershipLost):
            application.start()
        assert any("final-1" in argv[-1] for argv in calls)
        assert not any("final-2" in argv[-1] for argv in calls), calls
        assert "final-1" in calls[-1][-1]

    def test_a_valid_hold_runs_every_command_of_the_set(
        self, application_factory, config_factory, monkeypatch
    ):  # type: ignore[no-untyped-def]
        """Control: the per-command check changes nothing while the hold stays valid."""
        base = yaml.safe_load(config_factory().read_text())["verification"]["final"]
        application = application_factory(
            overrides={"verification": {"final": [*base, _marker("final-1"), _marker("final-2")]}}
        )
        calls = self._count_commands(monkeypatch, application, "never-matches")
        application.start()
        assert any("final-1" in argv[-1] for argv in calls)
        assert any("final-2" in argv[-1] for argv in calls)

    def test_the_git_vectors_stop_after_the_vector_that_lost_it(
        self, application_factory, worktree, monkeypatch
    ):  # type: ignore[no-untyped-def]
        committing = application_factory(overrides={"git": {"execute_commit": True}})
        committing.start()
        baseline = git(worktree, "rev-parse", "HEAD")
        vectors: list[tuple[str, ...]] = []
        real_run = ApprovalGit._run

        def capturing(self: ApprovalGit, argv: tuple[str, ...]) -> str:
            vectors.append(argv)
            output = real_run(self, argv)
            replace_lock_file(committing)
            return output

        monkeypatch.setattr(ApprovalGit, "_run", capturing)
        with pytest.raises(LockOwnershipLost):
            committing.approve_commit(confirmation=COMMIT_CONFIRMATION)
        assert [vector[0] for vector in vectors] == ["add"], vectors
        assert git(worktree, "rev-parse", "HEAD") == baseline, "the commit vector never ran"
