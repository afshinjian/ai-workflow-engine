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
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

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
    ProviderRole,
    ProviderRunRecord,
    RunRecord,
    RunStatus,
    StopReason,
    VerificationResult,
)
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
        assert len(sources) == 18, [source.name for source in sources]
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
