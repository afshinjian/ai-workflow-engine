"""Adversarial AUTO002-F03 production-resume tests against real local Git repositories."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.observation import (
    LocalResumeObserver,
    ResumeObservation,
    WorktreeChange,
    running_engine_version,
)
from agentos_workflow.orchestrator.engine import (
    AuthorizationBindingDriftError,
    CurrentAuthorizationBinding,
    ResumeReconciliationRequiredError,
    WorkflowAlreadyTerminalError,
    WorkflowSession,
    WorkflowState,
)
from agentos_workflow.orchestrator.lock import RepositoryLock
from agentos_workflow.orchestrator.state_store import StateStore

_WORKFLOW_ID = "wf-f03"
_STAGE_ID = "AUTO-002"
_PLANNED = "feature/auto-002"
_CONTRACT_RELATIVE = Path("docs/contracts/AUTO-002.md")


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=check,
        text=True,
        capture_output=True,
    )


def _config(tmp_path: Path, *, repository_path: Path | None = None) -> WorkflowConfig:
    repository = repository_path or tmp_path / "repo"
    if repository_path is None:
        repository.mkdir()
        contract = repository / _CONTRACT_RELATIVE
        contract.parent.mkdir(parents=True)
        contract.write_text("authoritative contract\n", encoding="utf-8")
        _git(repository, "init", "-b", "main")
        _git(repository, "config", "user.name", "F03 Test")
        _git(repository, "config", "user.email", "f03@example.invalid")
        _git(repository, "add", _CONTRACT_RELATIVE.as_posix())
        _git(repository, "commit", "-m", "baseline")
        _git(repository, "remote", "add", "origin", "github.com/org/repo")
    return WorkflowConfig.model_validate(
        {
            "repository_path": repository,
            "repository_identity": "github.com/org/repo",
            "remote_name": "origin",
            "baseline_branch": "main",
            "stage_contract_directory": "docs/contracts",
            "stage_branch_naming": "feature/{stage_id}",
            "test_command": "pytest",
            "lint_command": "ruff check .",
            "formatting_command": "black --check .",
            "security_command": "true",
            "required_github_checks": [],
            "merge_method": "squash",
            "claude_cli_executable": Path("/bin/true"),
            "claude_cli_timeout_seconds": 1,
            "codex_cli_executable": Path("/bin/true"),
            "codex_cli_timeout_seconds": 1,
            "allowed_environment_variables": [],
            "allowed_changed_paths": ["docs/work/**"],
            "forbidden_changed_paths": ["src/**"],
            "repair_attempt_limit": 3,
            "state_directory": tmp_path / "state",
            "audit_directory": tmp_path / "audit",
        }
    )


def _baseline(repository: Path) -> str:
    return _git(repository, "rev-parse", "refs/heads/main").stdout.strip()


def _contract_hash(repository: Path) -> str:
    return f"sha256:{sha256((repository / _CONTRACT_RELATIVE).read_bytes()).hexdigest()}"


def _start(config: WorkflowConfig) -> WorkflowSession:
    return WorkflowSession.start(
        config,
        workflow_id=_WORKFLOW_ID,
        stage_id=_STAGE_ID,
        stage_contract_path=_CONTRACT_RELATIVE.as_posix(),
        stage_contract_hash=_contract_hash(config.repository_path.resolve()),
        planned_stage_branch=_PLANNED,
        baseline_commit_sha=_baseline(config.repository_path.resolve()),
        authorized_at="2026-07-27T10:00:00+00:00",
        engine_version=running_engine_version(),
        authorized_by="human-owner",
    )


_FORWARD: tuple[WorkflowState, ...] = (
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
)


def _persist_state(session: WorkflowSession, target: WorkflowState) -> None:
    if target is WorkflowState.REPAIRING:
        for state in _FORWARD[:4]:
            session.transition_to(state, actor="orchestrator")
        session.transition_to(WorkflowState.REPAIRING, actor="orchestrator")
        return
    for state in _FORWARD:
        session.transition_to(state, actor="orchestrator")
        if state is target:
            return


def _prepare(config: WorkflowConfig, target: WorkflowState) -> None:
    session = _start(config)
    if target is not WorkflowState.AUTHORIZED:
        _persist_state(session, target)
    session._resumed.lock.release()
    branch_states = {
        WorkflowState.BRANCH_CREATED,
        WorkflowState.IMPLEMENTING,
        WorkflowState.REPAIRING,
        WorkflowState.VALIDATING,
        WorkflowState.QA_RUNNING,
        WorkflowState.READY_TO_COMMIT,
        WorkflowState.COMMITTED,
        # AUTO-014: PUSHED/PR_OPEN/AUTO_MERGE_ENABLED/WAITING_FOR_CHECKS all still require
        # `current_branch == planned_stage_branch` (`_validate_live_resume_observation`'s
        # `planned_required` block, unchanged by AUTO-014) — MERGED/CLOSING deliberately do not,
        # since AUTO-014's own baseline-restoration work is what moves the repository back to the
        # baseline branch after those two.
        WorkflowState.PUSHED,
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
    }
    if target in branch_states:
        repository = config.repository_path.resolve()
        _git(repository, "branch", _PLANNED, _baseline(repository))
        _git(repository, "switch", _PLANNED)


def _resume(
    config: WorkflowConfig,
    *,
    current_binding: CurrentAuthorizationBinding | None = None,
    observer: object | None = None,
) -> WorkflowSession:
    kwargs: dict[str, object] = {}
    if observer is not None:
        kwargs["_observer"] = observer
    return WorkflowSession.resume(
        config,
        workflow_id=_WORKFLOW_ID,
        stage_id=_STAGE_ID,
        planned_stage_branch=_PLANNED,
        current_binding=current_binding,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "state",
    [
        WorkflowState.AUTHORIZED,
        WorkflowState.PRECONDITIONS_CHECKED,
        WorkflowState.BRANCH_CREATED,
        WorkflowState.IMPLEMENTING,
        WorkflowState.REPAIRING,
        WorkflowState.VALIDATING,
        WorkflowState.QA_RUNNING,
    ],
)
def test_supported_clean_state_categories_resume_from_real_observations(
    tmp_path: Path, state: WorkflowState
) -> None:
    config = _config(tmp_path)
    _prepare(config, state)
    with _resume(config) as resumed:
        assert resumed.state is state


@pytest.mark.parametrize(
    ("state", "field"),
    [
        (WorkflowState.READY_TO_COMMIT, "commit_boundary"),
        (WorkflowState.COMMITTED, "commit_evidence"),
    ],
)
def test_evidence_dependent_states_fail_closed_to_reconciliation(
    tmp_path: Path, state: WorkflowState, field: str
) -> None:
    config = _config(tmp_path)
    _prepare(config, state)
    before = StateStore.for_config(config).read_transitions(_WORKFLOW_ID)
    with pytest.raises(ResumeReconciliationRequiredError) as exc_info:
        _resume(config)
    assert exc_info.value.field == field
    assert StateStore.for_config(config).read_transitions(_WORKFLOW_ID) == before


@pytest.mark.parametrize(
    "state",
    [
        WorkflowState.PUSHED,
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
    ],
)
def test_pushed_and_later_states_no_longer_fail_closed_to_generic_reconciliation(
    tmp_path: Path, state: WorkflowState
) -> None:
    """AUTO-014: `PUSHED`/`PR_OPEN`/`AUTO_MERGE_ENABLED`/`WAITING_FOR_CHECKS` used to fall into
    the same unconditional `commit_evidence` `ResumeReconciliationRequiredError` `COMMITTED` still
    raises above — a placeholder AUTO-013 left in place on purpose (its own module docstring:
    "remote and PR evidence remain pending future authorized Skill/GitHub observation work"), since
    no stage before AUTO-014 ever needed to resume *into* a post-`COMMITTED` state.

    `PUSHED` itself is untouched (still owned by AUTO-013, still raises — asserted separately
    below); the three AUTO-014-owned states now resume successfully instead, because
    `MergeCloseoutModeDriver` performs the authorized remote observation this generic function has
    no verifier for immediately afterward (`skills.git_github.read_pull_request_state`).
    """
    config = _config(tmp_path)
    _prepare(config, state)
    if state is WorkflowState.PUSHED:
        with pytest.raises(ResumeReconciliationRequiredError) as exc_info:
            _resume(config)
        assert exc_info.value.field == "commit_evidence"
        return
    with _resume(config) as resumed:
        assert resumed.state is state


@pytest.mark.parametrize("state", [WorkflowState.MERGED, WorkflowState.CLOSING])
def test_merged_and_closing_no_longer_fail_closed_to_generic_reconciliation(
    tmp_path: Path, state: WorkflowState
) -> None:
    """AUTO-014: same relaxation as `PR_OPEN`/`AUTO_MERGE_ENABLED`/`WAITING_FOR_CHECKS` above, for
    the same reason — `MergeCloseoutModeDriver` re-derives a fresh `MergeConfirmation` via
    `MergeAgent.confirm_merge()` immediately after resuming into either state rather than trusting
    anything carried across a process restart, which is the authorized merge/closeout evidence
    this function's own placeholder raise previously had no verifier for.
    """
    config = _config(tmp_path)
    _prepare(config, state)
    with _resume(config) as resumed:
        assert resumed.state is state


def test_agentos_owned_lock_is_excluded_but_arbitrary_agentos_file_is_not(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    assert (config.repository_path / ".agentos" / "workflow.lock").is_file()
    with _resume(config) as resumed:
        assert resumed.state is WorkflowState.AUTHORIZED

    (config.repository_path / ".agentos" / "user-file.txt").write_text(
        "not engine owned\n", encoding="utf-8"
    )
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config)
    assert exc_info.value.field == "working_tree_unexpected_paths"


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("outside.txt", "working_tree_unexpected_paths"),
        ("src/forbidden.py", "working_tree_forbidden_paths"),
    ],
)
def test_unexplained_or_forbidden_untracked_file_fails_closed(
    tmp_path: Path, path: str, field: str
) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    target = config.repository_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("unsafe\n", encoding="utf-8")
    authorization = (config.state_directory / _WORKFLOW_ID / "authorization.json").read_bytes()
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config)
    assert exc_info.value.field == field
    assert (
        config.state_directory / _WORKFLOW_ID / "authorization.json"
    ).read_bytes() == authorization


def test_uncertain_branch_creation_boundary_is_deterministic_and_releases_lock(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    _git(config.repository_path, "branch", _PLANNED, _baseline(config.repository_path))
    store = StateStore.for_config(config)
    before = store.read_transitions(_WORKFLOW_ID)
    for _ in range(2):
        with pytest.raises(ResumeReconciliationRequiredError) as exc_info:
            _resume(config)
        assert exc_info.value.field == "branch_creation"
        assert store.read_transitions(_WORKFLOW_ID) == before
    probe = RepositoryLock.for_config(config, workflow_id="probe")
    probe.acquire()
    probe.release()


@pytest.mark.parametrize(
    ("state", "field"),
    [
        (WorkflowState.IMPLEMENTING, "implementation_attempt"),
        (WorkflowState.REPAIRING, "repair_attempt"),
    ],
)
def test_dirty_provider_boundary_requires_reconciliation(
    tmp_path: Path, state: WorkflowState, field: str
) -> None:
    config = _config(tmp_path)
    session = _start(config)
    _persist_state(session, state)
    if state is WorkflowState.IMPLEMENTING:
        session.record_initial_execution_attempt_started(
            WorkflowState.IMPLEMENTING,
            attempt_number=1,
            start_time="2026-07-27T10:01:00+00:00",
        )
    else:
        session.record_repair_attempt_started(
            WorkflowState.VALIDATING,
            attempt_number=1,
            start_time="2026-07-27T10:01:00+00:00",
        )
    session._resumed.lock.release()
    repository = config.repository_path
    _git(repository, "branch", _PLANNED, _baseline(repository))
    _git(repository, "switch", _PLANNED)
    changed = repository / "docs/work/change.py"
    changed.parent.mkdir(parents=True)
    changed.write_text("expected provider output\n", encoding="utf-8")
    before = StateStore.for_config(config).read_transitions(_WORKFLOW_ID)
    with pytest.raises(ResumeReconciliationRequiredError) as exc_info:
        _resume(config)
    assert exc_info.value.field == field
    assert StateStore.for_config(config).read_transitions(_WORKFLOW_ID) == before


def test_planned_branch_unrelated_history_is_drift(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.BRANCH_CREATED)
    repository = config.repository_path
    _git(repository, "switch", "--orphan", "unrelated")
    contract = repository / _CONTRACT_RELATIVE
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text("authoritative contract\n", encoding="utf-8")
    (repository / "orphan.txt").write_text("orphan\n", encoding="utf-8")
    _git(repository, "add", _CONTRACT_RELATIVE.as_posix(), "orphan.txt")
    _git(repository, "commit", "-m", "unrelated")
    unrelated = _git(repository, "rev-parse", "HEAD").stdout.strip()
    _git(repository, "branch", "-f", _PLANNED, unrelated)
    _git(repository, "switch", _PLANNED)
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config)
    assert exc_info.value.field == "planned_branch_ancestry"


def test_baseline_drift_is_observed_even_when_caller_copies_old_values(tmp_path: Path) -> None:
    config = _config(tmp_path)
    session = _start(config)
    session._resumed.lock.release()
    authorization_path = config.state_directory / _WORKFLOW_ID / "authorization.json"
    persisted = json.loads(authorization_path.read_text(encoding="utf-8"))
    copied = CurrentAuthorizationBinding.model_validate(
        {
            field: persisted[field]
            for field in (
                "repository_path",
                "stage_contract_path",
                "stage_contract_hash",
                "baseline_commit_sha",
                "engine_version",
            )
        }
    )
    (config.repository_path / "baseline.txt").write_text("advance\n", encoding="utf-8")
    _git(config.repository_path, "add", "baseline.txt")
    _git(config.repository_path, "commit", "-m", "drift baseline")
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config, current_binding=copied)
    assert exc_info.value.field == "baseline_commit_sha"


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("wrong_remote", "repository_identity"),
        ("missing_contract", "stage_contract_exists"),
        ("changed_contract", "stage_contract_hash"),
    ],
)
def test_live_repository_and_contract_drift(tmp_path: Path, mutation: str, field: str) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    if mutation == "wrong_remote":
        _git(config.repository_path, "remote", "set-url", "origin", "github.com/attacker/repo")
    elif mutation == "missing_contract":
        (config.repository_path / _CONTRACT_RELATIVE).unlink()
    else:
        (config.repository_path / _CONTRACT_RELATIVE).write_text(
            "changed contract\n", encoding="utf-8"
        )
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config)
    assert exc_info.value.field == field


def test_repository_move_is_detected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    config.repository_path.rename(tmp_path / "moved-repo")
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config)
    assert exc_info.value.field == "git_repository"


def test_current_branch_drift_and_missing_planned_branch(tmp_path: Path) -> None:
    config = _config(tmp_path)
    session = _start(config)
    _persist_state(session, WorkflowState.BRANCH_CREATED)
    session._resumed.lock.release()
    with pytest.raises(AuthorizationBindingDriftError) as missing:
        _resume(config)
    assert missing.value.field == "planned_branch_exists"

    # Use a fresh workflow because drift legally terminalized the first.
    second = tmp_path / "second"
    second.mkdir()
    config2 = _config(second)
    session2 = _start(config2)
    _persist_state(session2, WorkflowState.BRANCH_CREATED)
    session2._resumed.lock.release()
    _git(config2.repository_path, "branch", _PLANNED, _baseline(config2.repository_path))
    with pytest.raises(AuthorizationBindingDriftError) as branch:
        _resume(config2)
    assert branch.value.field == "current_branch"


class _EngineDriftObserver:
    def __init__(self, config: WorkflowConfig) -> None:
        repository = config.repository_path.resolve()
        baseline = _baseline(repository)
        self.value = ResumeObservation(
            canonical_repository_path=str(repository),
            repository_exists=True,
            is_git_repository=True,
            observed_repository_identity=config.repository_identity,
            current_branch="main",
            head_sha=baseline,
            baseline_sha=baseline,
            planned_branch_sha=None,
            baseline_is_ancestor_of_planned=None,
            worktree_changes=(WorktreeChange("?", "?", ".agentos/workflow.lock"),),
            canonical_contract_path=str((repository / _CONTRACT_RELATIVE).resolve()),
            contract_exists=True,
            contract_hash=_contract_hash(repository),
            engine_version="999.0.0",
        )

    def observe(self, **_: str) -> ResumeObservation:
        return self.value


def test_running_engine_version_is_not_caller_authority(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    copied = CurrentAuthorizationBinding(
        repository_path=str(config.repository_path),
        stage_contract_path=_CONTRACT_RELATIVE.as_posix(),
        stage_contract_hash=_contract_hash(config.repository_path),
        baseline_commit_sha=_baseline(config.repository_path),
        engine_version=running_engine_version(),
    )
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config, current_binding=copied, observer=_EngineDriftObserver(config))
    assert exc_info.value.field == "engine_version"


def test_symlink_equivalent_repository_path_resumes(tmp_path: Path) -> None:
    real_config = _config(tmp_path)
    alias = tmp_path / "repo-alias"
    alias.symlink_to(real_config.repository_path)
    config = _config(tmp_path, repository_path=alias)
    _prepare(config, WorkflowState.AUTHORIZED)
    with _resume(config) as resumed:
        assert resumed.state is WorkflowState.AUTHORIZED


def test_observer_executes_only_fixed_read_only_local_git_forms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    _prepare(config, WorkflowState.AUTHORIZED)
    original_run = subprocess.run
    observed_argv: list[list[str]] = []

    def recording_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        observed_argv.append(argv)
        assert kwargs.get("shell") is not True
        assert argv[:3] == ["git", "--no-optional-locks", "-C"]
        assert argv[3] == str(config.repository_path.resolve())
        return cast(subprocess.CompletedProcess[bytes], original_run(argv, **kwargs))

    monkeypatch.setattr("agentos_workflow.observation.local.subprocess.run", recording_run)
    with _resume(config):
        pass
    assert observed_argv
    assert {argv[4] for argv in observed_argv} <= {
        "rev-parse",
        "config",
        "symbolic-ref",
        "show-ref",
        "merge-base",
        "status",
    }


def test_contract_path_must_remain_inside_configured_contract_directory(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    outside = config.repository_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    session = WorkflowSession.start(
        config,
        workflow_id=_WORKFLOW_ID,
        stage_id=_STAGE_ID,
        stage_contract_path="outside.md",
        stage_contract_hash=f"sha256:{sha256(outside.read_bytes()).hexdigest()}",
        planned_stage_branch=_PLANNED,
        baseline_commit_sha=_baseline(config.repository_path),
        authorized_at="2026-07-27T10:00:00+00:00",
        engine_version=running_engine_version(),
    )
    session._resumed.lock.release()
    with pytest.raises(AuthorizationBindingDriftError) as exc_info:
        _resume(config)
    assert exc_info.value.field == "stage_contract_path"


def test_local_observer_has_no_arbitrary_command_method() -> None:
    public = {name for name in dir(LocalResumeObserver) if not name.startswith("_")}
    assert public == {"observe"}


@pytest.mark.parametrize(
    "terminal",
    [WorkflowState.DONE, WorkflowState.FAILED, WorkflowState.CANCELLED],
)
def test_terminal_states_never_resume(tmp_path: Path, terminal: WorkflowState) -> None:
    config = _config(tmp_path)
    session = _start(config)
    if terminal is WorkflowState.CANCELLED:
        session.transition_to(terminal, actor="human")
    elif terminal is WorkflowState.FAILED:
        session.transition_to(terminal, actor="orchestrator")
    else:
        for state in _FORWARD:
            session.transition_to(state, actor="orchestrator")
        session.transition_to(WorkflowState.DONE, actor="orchestrator")
    with pytest.raises(WorkflowAlreadyTerminalError):
        _resume(config)


def test_running_engine_version_is_independent_of_the_distribution_version() -> None:
    """This engine's version comes from `__about__`, never from installed distribution metadata.

    AUTO-008. `running_engine_version` previously returned
    `importlib.metadata.version("ai-workflow-engine")` — the version of the whole repository's
    distribution, which also covers the entirely separate legacy `src/ai_workflow_engine/` engine
    that this package neither imports nor depends on.

    Because `HUMAN_AUTHORIZATION_MODEL.md` §2 item 11 binds the engine version into every
    authorization and §4 makes a later mismatch an authorization invalidator, that coupling meant a
    release of the legacy engine silently invalidated every in-flight `agentos_workflow`
    authorization and forced re-authorization from `CREATED`. It is also what made the AUTO-007
    end-to-end dry run fail once `pyproject.toml` moved to 1.0.0.

    Two independently-versioned subsystems must not share one version number.
    """
    import ast

    from agentos_workflow.__about__ import __version__ as declared
    from agentos_workflow.observation import local

    assert local.running_engine_version() == declared

    # The decisive check, and the reason it is structural rather than a value comparison: asserting
    # the engine version merely *differs* from the distribution version would pass today (0.1.0 vs
    # 1.0.0) and then silently start passing for the wrong reason the day the two happen to agree.
    # Asserting the module never reads distribution metadata at all pins the decoupling itself.
    #
    # Parsed rather than string-searched: this module's own docstring quotes the
    # `importlib.metadata.version(...)` call it no longer makes, so a substring scan would match the
    # prose explaining the fix and fail for the wrong reason. The AST sees only real imports.
    tree = ast.parse(Path(local.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    assert not any(
        name == "importlib.metadata" or name.startswith("importlib.metadata.") for name in imported
    ), f"observation.local must not read distribution metadata; imports were {sorted(imported)}"
    assert "importlib" not in imported
