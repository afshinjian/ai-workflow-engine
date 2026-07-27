"""Adversarial AUTO002-F07 local reconciliation-evidence verification tests.

Human Owner decision 2026-07-27 ("AUTO002-F07 evidence verification scope"): reconciliation
evidence must never be accepted merely because a caller supplies a success Boolean, internally
self-consistent fields, or a nonblank reference string. This file exercises the independent local
verifiers (`agentos_workflow.observation.evidence.LocalEvidenceObserver`,
`resolve_evidence_artifact`) directly against real, temporary local Git repositories, and exercises
`evaluate_initial_execution_failure`'s wiring of them end to end. Never mocks Git or the
filesystem — every "real"/"exists"/"reachable" claim below is backed by an actual local repository
or file on disk, and every rejection is produced by a genuine mismatch, not a stub.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from agentos_workflow.observation import (
    LocalEvidenceObservationError,
    LocalEvidenceObserver,
    resolve_evidence_artifact,
)
from agentos_workflow.orchestrator.engine import (
    CommitEvidence,
    ImplementationDiffEvidence,
    InitialExecutionFailureKind,
    LocalEvidenceVerificationFailedError,
    PullRequestEvidence,
    ReconciliationEvidence,
    ReconciliationVerifierUnavailableError,
    RemoteRefEvidence,
    RetryOutcome,
    WorkflowState,
    evaluate_initial_execution_failure,
)
from agentos_workflow.orchestrator.state_store import StateStore, StateTransitionRecord

_STAGE_BRANCH = "feature/auto-002-orchestrator-state-machine"
_OTHER_BRANCH = "feature/unrelated-work"
_MALFORMED_SHA = "not-a-sha"
_WELLFORMED_NONEXISTENT_SHA = "d" * 40


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=check, text=True, capture_output=True
    )


def _init_repository(directory: Path, *, branch: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _git(directory, "init", "-b", branch)
    _git(directory, "config", "user.name", "F07 Test")
    _git(directory, "config", "user.email", "f07@example.invalid")


class _Repo:
    """A real local Git repository with a documented, independently-inspectable shape:

    - `branch_head_sha`/`branch_tree_sha`: the tip of `_STAGE_BRANCH`, reachable from it.
    - `unmerged_sha`: a real commit that exists in this repository but is *not* reachable from
      `_STAGE_BRANCH` (committed to a divergent branch that was never merged) — exercises "existing
      commit outside expected branch ancestry."
    """

    def __init__(
        self,
        path: Path,
        baseline_sha: str,
        branch_head_sha: str,
        branch_tree_sha: str,
        unmerged_sha: str,
    ):
        self.path = path
        self.baseline_sha = baseline_sha
        self.branch_head_sha = branch_head_sha
        self.branch_tree_sha = branch_tree_sha
        self.unmerged_sha = unmerged_sha


@pytest.fixture
def repo(tmp_path: Path) -> _Repo:
    directory = tmp_path / "repo"
    _init_repository(directory, branch=_STAGE_BRANCH)
    (directory / "README.md").write_text("base\n", encoding="utf-8")
    _git(directory, "add", "README.md")
    _git(directory, "commit", "-m", "base commit")
    base_sha = _git(directory, "rev-parse", "HEAD").stdout.strip()

    (directory / "impl.txt").write_text("implementation\n", encoding="utf-8")
    _git(directory, "add", "impl.txt")
    _git(directory, "commit", "-m", "implementation commit")
    branch_head_sha = _git(directory, "rev-parse", "HEAD").stdout.strip()
    branch_tree_sha = _git(directory, "rev-parse", f"{branch_head_sha}^{{tree}}").stdout.strip()

    _git(directory, "checkout", "-b", _OTHER_BRANCH, base_sha)
    (directory / "unmerged.txt").write_text("never merged\n", encoding="utf-8")
    _git(directory, "add", "unmerged.txt")
    _git(directory, "commit", "-m", "unmerged commit")
    unmerged_sha = _git(directory, "rev-parse", "HEAD").stdout.strip()
    _git(directory, "checkout", _STAGE_BRANCH)

    return _Repo(directory, base_sha, branch_head_sha, branch_tree_sha, unmerged_sha)


@pytest.fixture
def unrelated_repo(tmp_path: Path) -> _Repo:
    directory = tmp_path / "unrelated-repo"
    _init_repository(directory, branch=_STAGE_BRANCH)
    (directory / "other.txt").write_text("unrelated\n", encoding="utf-8")
    _git(directory, "add", "other.txt")
    _git(directory, "commit", "-m", "unrelated repository's own commit")
    head_sha = _git(directory, "rev-parse", "HEAD").stdout.strip()
    tree_sha = _git(directory, "rev-parse", f"{head_sha}^{{tree}}").stdout.strip()
    return _Repo(directory, head_sha, head_sha, tree_sha, head_sha)


# -------------------------------------------------------------------------------------------
# LocalEvidenceObserver.commit_exists
# -------------------------------------------------------------------------------------------


class TestCommitExists:
    def test_real_commit_exists(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert observer.commit_exists(repo.branch_head_sha) is True

    def test_malformed_sha_is_false_not_an_error(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert observer.commit_exists(_MALFORMED_SHA) is False

    def test_wellformed_but_nonexistent_sha_is_false(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert observer.commit_exists(_WELLFORMED_NONEXISTENT_SHA) is False

    def test_commit_from_unrelated_repository_does_not_exist_here(
        self, repo: _Repo, unrelated_repo: _Repo
    ) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert observer.commit_exists(unrelated_repo.branch_head_sha) is False

    def test_missing_repository_raises_observation_error(self, tmp_path: Path) -> None:
        observer = LocalEvidenceObserver(tmp_path / "does-not-exist")
        with pytest.raises(LocalEvidenceObservationError):
            observer.commit_exists("a" * 40)


# -------------------------------------------------------------------------------------------
# LocalEvidenceObserver.tree_sha
# -------------------------------------------------------------------------------------------


class TestTreeSha:
    def test_recomputes_real_tree_never_echoes_caller_value(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert observer.tree_sha(repo.branch_head_sha) == repo.branch_tree_sha

    def test_nonexistent_commit_returns_none(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert observer.tree_sha(_WELLFORMED_NONEXISTENT_SHA) is None


# -------------------------------------------------------------------------------------------
# LocalEvidenceObserver.commit_reachable_from_branch
# -------------------------------------------------------------------------------------------


class TestCommitReachableFromBranch:
    def test_branch_tip_is_reachable_from_itself(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert (
            observer.commit_reachable_from_branch(
                commit_sha=repo.branch_head_sha, branch=_STAGE_BRANCH
            )
            is True
        )

    def test_commit_outside_expected_branch_ancestry_is_not_reachable(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert (
            observer.commit_reachable_from_branch(
                commit_sha=repo.unmerged_sha, branch=_STAGE_BRANCH
            )
            is False
        )

    def test_commit_from_unrelated_repository_is_not_reachable(
        self, repo: _Repo, unrelated_repo: _Repo
    ) -> None:
        observer = LocalEvidenceObserver(repo.path)
        assert (
            observer.commit_reachable_from_branch(
                commit_sha=unrelated_repo.branch_head_sha, branch=_STAGE_BRANCH
            )
            is False
        )

    def test_nonexistent_branch_is_not_reachable(self, repo: _Repo) -> None:
        # `git merge-base --is-ancestor` against a ref that does not exist exits 128 (an allowed
        # returncode here), yielding a definite `False` rather than an observation error — a
        # caller-supplied branch that was never created is correctly treated as "not reachable,"
        # the same fail-closed outcome as any other ancestry mismatch.
        observer = LocalEvidenceObserver(repo.path)
        assert (
            observer.commit_reachable_from_branch(
                commit_sha=repo.branch_head_sha, branch="feature/never-created"
            )
            is False
        )

    def test_unsafe_branch_name_rejected_before_any_git_invocation(self, repo: _Repo) -> None:
        observer = LocalEvidenceObserver(repo.path)
        with pytest.raises(LocalEvidenceObservationError):
            observer.commit_reachable_from_branch(commit_sha=repo.branch_head_sha, branch="../etc")


# -------------------------------------------------------------------------------------------
# resolve_evidence_artifact — path confinement (arbitrary reference / traversal / symlink escape)
# -------------------------------------------------------------------------------------------


class TestResolveEvidenceArtifact:
    def _seed(self, tmp_path: Path, *, workflow_id: str, operation_id: str, name: str) -> Path:
        directory = tmp_path / "audit" / workflow_id / "evidence" / operation_id
        directory.mkdir(parents=True)
        artifact = directory / name
        artifact.write_text("{}\n", encoding="utf-8")
        return artifact

    def test_valid_artifact_resolves(self, tmp_path: Path) -> None:
        expected = self._seed(
            tmp_path, workflow_id="wf-1", operation_id="IMPLEMENTING", name="a.json"
        )
        resolved = resolve_evidence_artifact(
            audit_root=tmp_path / "audit",
            workflow_id="wf-1",
            operation_id="IMPLEMENTING",
            artifact_name="a.json",
        )
        assert resolved == expected

    def test_arbitrary_nonblank_reference_to_nonexistent_artifact_rejected(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "audit").mkdir()
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-1",
                operation_id="IMPLEMENTING",
                artifact_name="nonexistent-report.json",
            )

    def test_absolute_artifact_path_rejected(self, tmp_path: Path) -> None:
        self._seed(tmp_path, workflow_id="wf-1", operation_id="IMPLEMENTING", name="a.json")
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-1",
                operation_id="IMPLEMENTING",
                artifact_name="/etc/passwd",
            )

    def test_parent_traversal_rejected(self, tmp_path: Path) -> None:
        secret = tmp_path / "secret.json"
        secret.write_text("{}\n", encoding="utf-8")
        self._seed(tmp_path, workflow_id="wf-1", operation_id="IMPLEMENTING", name="a.json")
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-1",
                operation_id="IMPLEMENTING",
                artifact_name="../../../secret.json",
            )

    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        secret = tmp_path / "secret.json"
        secret.write_text("{}\n", encoding="utf-8")
        directory = tmp_path / "audit" / "wf-1" / "evidence" / "IMPLEMENTING"
        directory.mkdir(parents=True)
        (directory / "escape.json").symlink_to(secret)
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-1",
                operation_id="IMPLEMENTING",
                artifact_name="escape.json",
            )

    def test_artifact_belonging_to_another_workflow_rejected(self, tmp_path: Path) -> None:
        self._seed(tmp_path, workflow_id="wf-1", operation_id="IMPLEMENTING", name="a.json")
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-other",
                operation_id="IMPLEMENTING",
                artifact_name="a.json",
            )

    def test_artifact_belonging_to_another_operation_rejected(self, tmp_path: Path) -> None:
        self._seed(tmp_path, workflow_id="wf-1", operation_id="IMPLEMENTING", name="a.json")
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-1",
                operation_id="READY_TO_COMMIT",
                artifact_name="a.json",
            )

    def test_directory_is_not_a_regular_file_rejected(self, tmp_path: Path) -> None:
        directory = tmp_path / "audit" / "wf-1" / "evidence" / "IMPLEMENTING" / "a.json"
        directory.mkdir(parents=True)
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="wf-1",
                operation_id="IMPLEMENTING",
                artifact_name="a.json",
            )

    def test_unsafe_workflow_id_rejected_before_path_construction(self, tmp_path: Path) -> None:
        (tmp_path / "audit").mkdir()
        with pytest.raises(LocalEvidenceObservationError):
            resolve_evidence_artifact(
                audit_root=tmp_path / "audit",
                workflow_id="../escape",
                operation_id="IMPLEMENTING",
                artifact_name="a.json",
            )


# -------------------------------------------------------------------------------------------
# No unauthorized Git mutation or network command — evidence.py is fixed-argv, read-only, local.
# -------------------------------------------------------------------------------------------


class TestEvidenceModuleHasNoMutationOrNetworkCapability:
    def test_only_allowlisted_read_only_git_subcommands_appear(self) -> None:
        import agentos_workflow.observation.evidence as evidence_module

        allowed_git_subcommands = {"cat-file", "rev-parse", "merge-base"}
        source = evidence_module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=source)
        found_subcommands: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple):
                elements = [element for element in node.elts if isinstance(element, ast.Constant)]
                for element in elements:
                    if isinstance(element.value, str) and element.value in allowed_git_subcommands:
                        found_subcommands.add(element.value)
                    elif isinstance(element.value, str) and element.value in {
                        "push",
                        "commit",
                        "checkout",
                        "reset",
                        "clean",
                        "fetch",
                        "pull",
                        "clone",
                        "merge",
                        "rebase",
                    }:
                        pytest.fail(
                            f"mutating/network git subcommand literal found: {element.value!r}"
                        )
        assert found_subcommands, "expected to find the allowlisted read-only subcommands"

    def test_no_network_or_subprocess_imports_beyond_subprocess_itself(self) -> None:
        import agentos_workflow.observation.evidence as evidence_module

        source = evidence_module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=source)
        forbidden_modules = {"socket", "http", "urllib", "requests", "httpx", "aiohttp", "ftplib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_modules, alias.name
            elif isinstance(node, ast.ImportFrom):
                assert node.module is None or node.module.split(".")[0] not in forbidden_modules


# -------------------------------------------------------------------------------------------
# Engine-level integration: evaluate_initial_execution_failure wiring of _verify_evidence_locally
# -------------------------------------------------------------------------------------------

_WORKFLOW_ID = "wf-1"
_STAGE_ID = "AUTO-002"
_REPOSITORY_IDENTITY = "github.com/org/repo"


def _store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def _transition(
    *,
    from_state: str,
    to_state: str,
    repository_path: str,
    timestamp: str = "2026-07-24T10:00:00+00:00",
) -> StateTransitionRecord:
    return StateTransitionRecord(
        workflow_id=_WORKFLOW_ID,
        target_repository=_REPOSITORY_IDENTITY,
        repository_path=repository_path,
        stage_id=_STAGE_ID,
        from_state=from_state,
        to_state=to_state,
        timestamp=timestamp,
        actor="orchestrator",
        gate_evidence_ref=None,
    )


def _seed_to_implementing(store: StateStore, *, repository_path: str, baseline_sha: str) -> None:
    from agentos_workflow.orchestrator.engine import (
        AuthorizationContext,
        AuthorizationRecord,
        WorkflowStateMachine,
        authorize,
        record_initial_execution_attempt_started,
    )

    record = AuthorizationRecord.model_validate(
        {
            "workflow_id": _WORKFLOW_ID,
            "repository_identity": _REPOSITORY_IDENTITY,
            "repository_path": repository_path,
            "stage_id": _STAGE_ID,
            "stage_contract_path": "docs/workflow-automation/stage-prompts/AUTO-002.md",
            "stage_contract_hash": "sha256:deadbeef",
            "baseline_branch": "main",
            "baseline_commit_sha": baseline_sha,
            "planned_stage_branch": _STAGE_BRANCH,
            "authorized_at": "2026-07-24T10:00:00+00:00",
            "authorized_by": "human-owner",
            "engine_version": "0.1.0",
        }
    )
    context = AuthorizationContext(
        workflow_id=record.workflow_id,
        repository_identity=record.repository_identity,
        stage_id=record.stage_id,
        planned_stage_branch=record.planned_stage_branch,
        baseline_branch=record.baseline_branch,
    )
    authorize(WorkflowStateMachine(), context, record, state_store=store)
    for from_state, to_state in [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
    ]:
        store.record_transition(
            _transition(from_state=from_state, to_state=to_state, repository_path=repository_path)
        )
    record_initial_execution_attempt_started(
        workflow_id=_WORKFLOW_ID,
        stage_id=_STAGE_ID,
        state=WorkflowState.IMPLEMENTING,
        attempt_number=1,
        state_store=store,
        start_time="2026-07-24T10:00:01+00:00",
    )


def _evaluate(
    *, state: WorkflowState, state_store: StateStore, evidence: ReconciliationEvidence
) -> object:
    return evaluate_initial_execution_failure(
        workflow_id=_WORKFLOW_ID,
        repository_identity=_REPOSITORY_IDENTITY,
        repository_path=str(evidence.repository_path),
        stage_id=_STAGE_ID,
        state=state,
        state_store=state_store,
        failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
        evidence=evidence,
        allowed_changed_paths=["**"],
        forbidden_changed_paths=[],
    )


def _confirmed_evidence(
    *, repository_path: str, evidence: object, succeeded: bool = True
) -> ReconciliationEvidence:
    return ReconciliationEvidence.model_validate(
        {
            "workflow_id": _WORKFLOW_ID,
            "repository_identity": _REPOSITORY_IDENTITY,
            "repository_path": repository_path,
            "stage_id": _STAGE_ID,
            "side_effect_confirmed": True,
            "side_effect_succeeded": succeeded,
            "evidence": evidence,
        }
    )


def _bound_implementation_evidence(
    repo: _Repo, *, attempt_number: int = 1
) -> ImplementationDiffEvidence:
    return ImplementationDiffEvidence(
        stage_branch=_STAGE_BRANCH,
        observed_head_sha=repo.branch_head_sha,
        attempt_number=attempt_number,
        changed_paths=("impl.txt",),
        completion_report_reference="report.json",
    )


def _write_bound_report(store: StateStore, repo: _Repo, *, content: str | None = None) -> Path:
    artifact = store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING" / "report.json"
    artifact.parent.mkdir(parents=True)
    if content is None:
        content = json.dumps(
            {
                "workflow_id": _WORKFLOW_ID,
                "stage_id": _STAGE_ID,
                "attempt_number": 1,
                "stage_branch": _STAGE_BRANCH,
                "observed_head_sha": repo.branch_head_sha,
                "changed_paths": ["impl.txt"],
            }
        )
    artifact.write_text(content, encoding="utf-8")
    return artifact


class TestEngineWiringAdversarial:
    def test_valid_local_implementation_evidence_advances(
        self, tmp_path: Path, repo: _Repo
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        artifact_dir = store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING"
        artifact_dir.mkdir(parents=True)
        changed_paths = ("impl.txt",)
        (artifact_dir / "report.json").write_text(
            json.dumps(
                {
                    "workflow_id": _WORKFLOW_ID,
                    "stage_id": _STAGE_ID,
                    "attempt_number": 1,
                    "stage_branch": _STAGE_BRANCH,
                    "observed_head_sha": repo.branch_head_sha,
                    "changed_paths": list(changed_paths),
                }
            ),
            encoding="utf-8",
        )
        result = _evaluate(
            state=WorkflowState.IMPLEMENTING,
            state_store=store,
            evidence=_confirmed_evidence(
                repository_path=str(repo.path),
                evidence=ImplementationDiffEvidence(
                    stage_branch=_STAGE_BRANCH,
                    observed_head_sha=repo.branch_head_sha,
                    attempt_number=1,
                    changed_paths=changed_paths,
                    completion_report_reference="report.json",
                ),
            ),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_SUCCESSFUL  # type: ignore[attr-defined]

    def test_stale_ancestor_on_authorized_branch_is_rejected(
        self, tmp_path: Path, repo: _Repo
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        with pytest.raises(LocalEvidenceVerificationFailedError, match="exact tip"):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=ImplementationDiffEvidence(
                        stage_branch=_STAGE_BRANCH,
                        observed_head_sha=repo.baseline_sha,
                        attempt_number=1,
                        changed_paths=(),
                        completion_report_reference="report.json",
                    ),
                ),
            )

    def test_unbound_branch_is_rejected(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        with pytest.raises(LocalEvidenceVerificationFailedError, match="authorized planned branch"):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=ImplementationDiffEvidence(
                        stage_branch=_OTHER_BRANCH,
                        observed_head_sha=repo.unmerged_sha,
                        attempt_number=1,
                        changed_paths=("unmerged.txt",),
                        completion_report_reference="report.json",
                    ),
                ),
            )

    @pytest.mark.parametrize("content", ["", "{}", '{"workflow_id":"other"}'])
    def test_empty_or_mismatched_report_is_rejected(
        self, tmp_path: Path, repo: _Repo, content: str
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        _write_bound_report(store, repo, content=content)
        with pytest.raises(LocalEvidenceVerificationFailedError):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=_bound_implementation_evidence(repo),
                ),
            )

    def test_evidence_for_different_attempt_is_rejected(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        with pytest.raises(LocalEvidenceVerificationFailedError, match="latest persisted attempt"):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=_bound_implementation_evidence(repo, attempt_number=2),
                ),
            )

    def test_cross_workflow_symlink_report_is_rejected(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        other = store.audit_directory / "other" / "report.json"
        other.parent.mkdir(parents=True)
        other.write_text("{}", encoding="utf-8")
        artifact = (
            store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING" / "report.json"
        )
        artifact.parent.mkdir(parents=True)
        artifact.symlink_to(other)
        with pytest.raises(LocalEvidenceVerificationFailedError):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=_bound_implementation_evidence(repo),
                ),
            )

    def test_changed_path_scope_violation_is_rejected(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        _write_bound_report(store, repo)
        evidence = _confirmed_evidence(
            repository_path=str(repo.path),
            evidence=_bound_implementation_evidence(repo),
        )
        with pytest.raises(LocalEvidenceVerificationFailedError, match="path scope"):
            evaluate_initial_execution_failure(
                workflow_id=_WORKFLOW_ID,
                repository_identity=_REPOSITORY_IDENTITY,
                repository_path=str(repo.path),
                stage_id=_STAGE_ID,
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                failure_kind=InitialExecutionFailureKind.POSSIBLE_SIDE_EFFECT,
                evidence=evidence,
                allowed_changed_paths=["docs/**"],
                forbidden_changed_paths=["impl.txt"],
            )

    def test_valid_local_commit_evidence_advances(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        store.record_transition(
            _transition(
                from_state="IMPLEMENTING", to_state="VALIDATING", repository_path=str(repo.path)
            )
        )
        store.record_transition(
            _transition(
                from_state="VALIDATING", to_state="QA_RUNNING", repository_path=str(repo.path)
            )
        )
        store.record_transition(
            _transition(
                from_state="QA_RUNNING", to_state="READY_TO_COMMIT", repository_path=str(repo.path)
            )
        )
        result = _evaluate(
            state=WorkflowState.READY_TO_COMMIT,
            state_store=store,
            evidence=_confirmed_evidence(
                repository_path=str(repo.path),
                evidence=CommitEvidence(
                    commit_sha=repo.branch_head_sha,
                    expected_tree_sha=repo.branch_tree_sha,
                    observed_tree_sha=repo.branch_tree_sha,
                ),
            ),
        )
        assert result.outcome is RetryOutcome.RECONCILIATION_SUCCESSFUL  # type: ignore[attr-defined]

    def test_caller_claimed_commit_sha_that_does_not_exist_locally_rejected(
        self, tmp_path: Path, repo: _Repo
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        artifact_dir = store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "report.json").write_text('{"ok": true}\n', encoding="utf-8")
        with pytest.raises(LocalEvidenceVerificationFailedError):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=ImplementationDiffEvidence(
                        stage_branch=_STAGE_BRANCH,
                        observed_head_sha=_WELLFORMED_NONEXISTENT_SHA,
                        completion_report_reference="report.json",
                    ),
                ),
            )

    def test_commit_outside_branch_ancestry_rejected(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        artifact_dir = store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "report.json").write_text('{"ok": true}\n', encoding="utf-8")
        with pytest.raises(LocalEvidenceVerificationFailedError):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=ImplementationDiffEvidence(
                        stage_branch=_STAGE_BRANCH,
                        observed_head_sha=repo.unmerged_sha,
                        completion_report_reference="report.json",
                    ),
                ),
            )

    def test_referenced_artifact_missing_rejected(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        with pytest.raises(LocalEvidenceVerificationFailedError):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=ImplementationDiffEvidence(
                        stage_branch=_STAGE_BRANCH,
                        observed_head_sha=repo.branch_head_sha,
                        completion_report_reference="never-written.json",
                    ),
                ),
            )

    def test_remote_ref_evidence_never_authorizes_advancement_on_caller_word_alone(
        self, tmp_path: Path, repo: _Repo
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        for from_state, to_state in [
            ("IMPLEMENTING", "VALIDATING"),
            ("VALIDATING", "QA_RUNNING"),
            ("QA_RUNNING", "READY_TO_COMMIT"),
            ("READY_TO_COMMIT", "COMMITTED"),
        ]:
            store.record_transition(
                _transition(
                    from_state=from_state,
                    to_state=to_state,
                    repository_path=str(repo.path),
                )
            )
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate(
                state=WorkflowState.COMMITTED,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=RemoteRefEvidence(
                        remote_ref=f"refs/heads/{_STAGE_BRANCH}",
                        expected_sha=repo.branch_head_sha,
                        observed_sha=repo.branch_head_sha,
                    ),
                ),
            )

    def test_pull_request_evidence_never_authorizes_advancement_on_caller_word_alone(
        self, tmp_path: Path, repo: _Repo
    ) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        for from_state, to_state in [
            ("IMPLEMENTING", "VALIDATING"),
            ("VALIDATING", "QA_RUNNING"),
            ("QA_RUNNING", "READY_TO_COMMIT"),
            ("READY_TO_COMMIT", "COMMITTED"),
            ("COMMITTED", "PUSHED"),
        ]:
            store.record_transition(
                _transition(
                    from_state=from_state,
                    to_state=to_state,
                    repository_path=str(repo.path),
                )
            )
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate(
                state=WorkflowState.PUSHED,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(repo.path),
                    evidence=PullRequestEvidence(
                        pr_number=1,
                        head_branch=_STAGE_BRANCH,
                        base_branch="main",
                        expected_head_sha=repo.branch_head_sha,
                        observed_head_sha=repo.branch_head_sha,
                    ),
                ),
            )

    def test_deterministic_repeated_rejection(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        artifact_dir = store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "report.json").write_text('{"ok": true}\n', encoding="utf-8")
        evidence = _confirmed_evidence(
            repository_path=str(repo.path),
            evidence=ImplementationDiffEvidence(
                stage_branch=_STAGE_BRANCH,
                observed_head_sha=_WELLFORMED_NONEXISTENT_SHA,
                completion_report_reference="report.json",
            ),
        )
        for _ in range(3):
            with pytest.raises(LocalEvidenceVerificationFailedError):
                _evaluate(state=WorkflowState.IMPLEMENTING, state_store=store, evidence=evidence)

    def test_persisted_bytes_unchanged_after_rejection(self, tmp_path: Path, repo: _Repo) -> None:
        store = _store(tmp_path)
        _seed_to_implementing(store, repository_path=str(repo.path), baseline_sha=repo.baseline_sha)
        transitions_path = store.state_directory / _WORKFLOW_ID / "transitions.jsonl"
        before = transitions_path.read_bytes()
        evidence = _confirmed_evidence(
            repository_path=str(repo.path),
            evidence=ImplementationDiffEvidence(
                stage_branch=_STAGE_BRANCH,
                observed_head_sha=_WELLFORMED_NONEXISTENT_SHA,
                completion_report_reference="never-written.json",
            ),
        )
        with pytest.raises(LocalEvidenceVerificationFailedError):
            _evaluate(state=WorkflowState.IMPLEMENTING, state_store=store, evidence=evidence)
        assert transitions_path.read_bytes() == before

    def test_repository_missing_locally_fails_closed_as_verifier_unavailable(
        self, tmp_path: Path, repo: _Repo
    ) -> None:
        # The repository the evidence claims to be about does not exist at all: a caller cannot
        # substitute an unverifiable repository path and still be trusted.
        store = _store(tmp_path)
        _seed_to_implementing(
            store,
            repository_path=str(tmp_path / "missing-repo"),
            baseline_sha=repo.baseline_sha,
        )
        artifact_dir = store.audit_directory / _WORKFLOW_ID / "evidence" / "IMPLEMENTING"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "report.json").write_text('{"ok": true}\n', encoding="utf-8")
        with pytest.raises(ReconciliationVerifierUnavailableError):
            _evaluate(
                state=WorkflowState.IMPLEMENTING,
                state_store=store,
                evidence=_confirmed_evidence(
                    repository_path=str(tmp_path / "missing-repo"),
                    evidence=ImplementationDiffEvidence(
                        stage_branch=_STAGE_BRANCH,
                        observed_head_sha=repo.branch_head_sha,
                        completion_report_reference="report.json",
                    ),
                ),
            )
