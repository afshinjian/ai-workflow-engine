"""`PMOAgent` — the Precondition Gate (`AGENT_CONTRACTS.md` §2, `MACHINE_GATES.md` §2).

Run against a real temporary Git repository and real stage-contract/registry files, because the
gate's whole job is to compare live repository state against what was authorized: fakes would be
asserting that the Agent calls the Skills, not that the checks actually detect drift.

The check that carries the most weight is `stage_contract_hash`: it is the one that catches a
stage contract edited *after* the Human Owner authorized it, which would otherwise let a workflow
implement something other than what was approved.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from agentos_workflow.agents import (
    AgentFailureKind,
    AgentKind,
    AgentResult,
    CapabilityBroker,
    default_skill_registry,
)
from agentos_workflow.agents.pmo import PMOAgent
from agentos_workflow.tests.test_skills_repository import git, write

BASELINE = "main"
STAGE_ID = "AUTO-999"
STAGE_BRANCH = "feature/auto-999-example"
IDENTITY = "example.invalid/org/target"

PMO_SKILLS = (
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

CONTRACT_TEMPLATE = """# {stage_id} — Example stage

| Field | Value |
|---|---|
| **Stage** | {stage_id} · Role: Engine implementation session |
| **Branch** | `{branch}` |
| **Commit message** | `feat(example): do the thing ({stage_id})` |
| **Report** | `docs/reports/example/{stage_id}-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

## Canonical Prompt

Implement the example stage.
"""

REGISTRY_TEMPLATE = """# Example — Stage Registry

## 4. Registry

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| AUTO-998 | Predecessor | Engine implementation session | {predecessor_state} | `x` | `y` |
| {stage_id} | Example stage | Engine implementation session | AUTHORIZED | `{branch}` | `z` |
"""


@dataclass(frozen=True)
class Authorization:
    """A stand-in for the Orchestrator's `AuthorizationRecord`, satisfying `BoundAuthorization`.

    A plain frozen dataclass rather than the real record: `PMOAgent` accepts the Protocol, and
    building the real pydantic model here would couple this test to the Orchestrator's schema for
    no added coverage of the Agent.
    """

    workflow_id: str
    stage_id: str
    repository_identity: str
    stage_contract_hash: str
    baseline_branch: str
    baseline_commit_sha: str
    planned_stage_branch: str


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """A clean repository on `main` with an `origin` remote matching `IDENTITY`."""
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
    git(work, "remote", "add", "origin", f"https://{IDENTITY}.git")
    return work


@pytest.fixture
def contract_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "contracts"
    directory.mkdir()
    (directory / f"{STAGE_ID}.md").write_text(
        CONTRACT_TEMPLATE.format(stage_id=STAGE_ID, branch=STAGE_BRANCH), encoding="utf-8"
    )
    return directory


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "STAGE_REGISTRY.md"
    path.write_text(
        REGISTRY_TEMPLATE.format(
            stage_id=STAGE_ID, branch=STAGE_BRANCH, predecessor_state="COMPLETE"
        ),
        encoding="utf-8",
    )
    return path


def contract_hash(contract_directory: Path) -> str:
    """The contract digest in the canonical `AuthorizationRecord` format.

    Algorithm-prefixed (OD-11, fixed in AUTO-008). This helper previously returned bare hex,
    which is exactly how this module missed the defect: the Precondition Gate compared bare hex
    and `LocalResumeObserver` compared the prefixed form, so each side's tests agreed with their
    own side's convention and no test compared the two. A workflow that passed this gate was then
    guaranteed a false-positive `AuthorizationBindingDriftError` on its first real resume.

    The cross-module agreement itself is pinned by `test_skills_contract.py`'s
    `test_authorization_value_matches_the_resume_observer_format`.
    """
    digest = hashlib.sha256((contract_directory / f"{STAGE_ID}.md").read_bytes()).hexdigest()
    return f"sha256:{digest}"


def authorization(target: Path, contract_directory: Path, **overrides: object) -> Authorization:
    fields: dict[str, object] = {
        "workflow_id": "wf-pmo",
        "stage_id": STAGE_ID,
        "repository_identity": IDENTITY,
        "stage_contract_hash": contract_hash(contract_directory),
        "baseline_branch": BASELINE,
        "baseline_commit_sha": git(target, "rev-parse", "HEAD"),
        "planned_stage_branch": STAGE_BRANCH,
    }
    fields.update(overrides)
    return Authorization(**fields)  # type: ignore[arg-type]


def pmo_agent(audit_root: Path) -> PMOAgent:
    audit_root.mkdir(parents=True, exist_ok=True)
    registry = default_skill_registry()
    return PMOAgent(
        CapabilityBroker(
            AgentKind.PMO, skills={name: registry[name] for name in PMO_SKILLS if name in registry}
        )
    )


def check_map(result: AgentResult) -> dict[str, bool]:
    evidence = result.evidence
    return {entry["check"]: entry["passed"] for entry in evidence["checks"]}


class TestPreconditionGate:
    def test_every_precondition_passes_on_a_clean_authorized_repository(
        self, tmp_path: Path, target: Path, contract_directory: Path, registry_file: Path
    ) -> None:
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=authorization(target, contract_directory),
            repository_path=target,
            remote_name="origin",
            contract_directory=contract_directory,
            stage_registry=registry_file,
            audit_root=tmp_path / "audit",
        )
        assert result.ok is True, result.error
        assert all(check_map(result).values())
        assert result.evidence["stage_metadata_branch"] == STAGE_BRANCH

    def test_a_contract_edited_after_authorization_is_detected(
        self, tmp_path: Path, target: Path, contract_directory: Path, registry_file: Path
    ) -> None:
        """The check that matters most: implementing an edited contract would be implementing
        something the Human Owner never approved."""
        bound = authorization(target, contract_directory)
        (contract_directory / f"{STAGE_ID}.md").write_text(
            CONTRACT_TEMPLATE.format(stage_id=STAGE_ID, branch=STAGE_BRANCH) + "\nExtra scope.\n",
            encoding="utf-8",
        )
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=bound,
            repository_path=target,
            remote_name="origin",
            contract_directory=contract_directory,
            stage_registry=registry_file,
            audit_root=tmp_path / "audit",
        )
        assert result.ok is False
        checks = check_map(result)
        assert checks["stage_contract_hash"] is False
        assert checks["stage_contract_located"] is True, "the file is present; only its bytes moved"
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.PRECONDITION

    def test_a_dirty_working_tree_fails_the_gate(
        self, tmp_path: Path, target: Path, contract_directory: Path, registry_file: Path
    ) -> None:
        write(target, "scratch.txt", "uncommitted\n")
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=authorization(target, contract_directory),
            repository_path=target,
            remote_name="origin",
            contract_directory=contract_directory,
            stage_registry=registry_file,
            audit_root=tmp_path / "audit",
        )
        assert result.ok is False
        assert check_map(result)["working_tree_clean"] is False

    def test_a_wrong_remote_identity_fails_the_gate(
        self, tmp_path: Path, target: Path, contract_directory: Path, registry_file: Path
    ) -> None:
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=authorization(
                target, contract_directory, repository_identity="example.invalid/org/other"
            ),
            repository_path=target,
            remote_name="origin",
            contract_directory=contract_directory,
            stage_registry=registry_file,
            audit_root=tmp_path / "audit",
        )
        assert result.ok is False
        assert check_map(result)["repository_identity"] is False

    def test_an_unfinished_predecessor_fails_stage_ordering(
        self, tmp_path: Path, target: Path, contract_directory: Path
    ) -> None:
        registry = tmp_path / "REGISTRY.md"
        registry.write_text(
            REGISTRY_TEMPLATE.format(
                stage_id=STAGE_ID, branch=STAGE_BRANCH, predecessor_state="IN_PROGRESS"
            ),
            encoding="utf-8",
        )
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=authorization(target, contract_directory),
            repository_path=target,
            remote_name="origin",
            contract_directory=contract_directory,
            stage_registry=registry,
            audit_root=tmp_path / "audit",
        )
        assert result.ok is False
        assert check_map(result)["stage_ordering"] is False

    def test_every_check_runs_even_after_the_first_failure(
        self, tmp_path: Path, target: Path, contract_directory: Path, registry_file: Path
    ) -> None:
        """One gate run should tell an operator everything that is wrong, not the first thing."""
        write(target, "scratch.txt", "uncommitted\n")
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=authorization(
                target, contract_directory, repository_identity="example.invalid/org/other"
            ),
            repository_path=target,
            remote_name="origin",
            contract_directory=contract_directory,
            stage_registry=registry_file,
            audit_root=tmp_path / "audit",
        )
        checks = check_map(result)
        assert len(checks) == 9
        assert checks["repository_identity"] is False
        assert checks["working_tree_clean"] is False
        assert checks["stage_contract_hash"] is True, "later checks still ran"

    def test_a_missing_contract_does_not_crash_the_gate(
        self, tmp_path: Path, target: Path, registry_file: Path
    ) -> None:
        empty = tmp_path / "empty-contracts"
        empty.mkdir()
        result = pmo_agent(tmp_path / "audit").check_preconditions(
            authorization=Authorization(
                workflow_id="wf-pmo",
                stage_id=STAGE_ID,
                repository_identity=IDENTITY,
                # Well-formed canonical value that is simply wrong, so the gate fails on a hash
                # *mismatch* rather than incidentally on a malformed (unprefixed) value.
                stage_contract_hash=f"sha256:{'0' * 64}",
                baseline_branch=BASELINE,
                baseline_commit_sha=git(target, "rev-parse", "HEAD"),
                planned_stage_branch=STAGE_BRANCH,
            ),
            repository_path=target,
            remote_name="origin",
            contract_directory=empty,
            stage_registry=registry_file,
            audit_root=tmp_path / "audit",
        )
        assert result.ok is False
        checks = check_map(result)
        assert checks["stage_contract_located"] is False
        assert checks["stage_contract_parsed"] is False
        assert checks["stage_contract_hash"] is False


class TestStageBranchCreation:
    def test_the_branch_is_created_at_the_authorized_baseline_commit(
        self, tmp_path: Path, target: Path, contract_directory: Path
    ) -> None:
        bound = authorization(target, contract_directory)
        result = pmo_agent(tmp_path / "audit").create_branch(
            authorization=bound, repository_path=target, audit_root=tmp_path / "audit"
        )
        assert result.ok is True, result.error
        assert result.evidence["stage_branch"] == STAGE_BRANCH
        assert result.evidence["base_commit_sha"] == bound.baseline_commit_sha
        assert git(target, "rev-parse", STAGE_BRANCH) == bound.baseline_commit_sha

    def test_creating_the_same_branch_twice_is_idempotent(
        self, tmp_path: Path, target: Path, contract_directory: Path
    ) -> None:
        bound = authorization(target, contract_directory)
        agent = pmo_agent(tmp_path / "audit")
        first = agent.create_branch(
            authorization=bound, repository_path=target, audit_root=tmp_path / "audit"
        )
        second = agent.create_branch(
            authorization=bound, repository_path=target, audit_root=tmp_path / "audit"
        )
        assert first.ok and second.ok
        assert second.evidence["base_commit_sha"] == bound.baseline_commit_sha

    def test_a_branch_that_already_exists_elsewhere_is_a_failure_not_a_move(
        self, tmp_path: Path, target: Path, contract_directory: Path
    ) -> None:
        """Moving it would rewrite the stage's baseline, which `SECURITY_MODEL.md` §2 forbids."""
        write(target, "later.txt", "later\n")
        git(target, "add", "later.txt")
        git(target, "commit", "-m", "later")
        later_sha = git(target, "rev-parse", "HEAD")
        git(target, "branch", STAGE_BRANCH, later_sha)
        git(target, "checkout", BASELINE)

        bound = authorization(
            target, contract_directory, baseline_commit_sha=git(target, "rev-parse", "HEAD~1")
        )
        result = pmo_agent(tmp_path / "audit").create_branch(
            authorization=bound, repository_path=target, audit_root=tmp_path / "audit"
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is AgentFailureKind.SKILL_FAILED
        assert git(target, "rev-parse", STAGE_BRANCH) == later_sha, "the branch was not moved"

    def test_the_branch_name_comes_from_the_authorization_not_the_contract(
        self, tmp_path: Path, target: Path, contract_directory: Path
    ) -> None:
        """A contract edit must not be able to redirect the work onto a different branch."""
        bound = authorization(
            target, contract_directory, planned_stage_branch="feature/authorized-name"
        )
        result = pmo_agent(tmp_path / "audit").create_branch(
            authorization=bound, repository_path=target, audit_root=tmp_path / "audit"
        )
        assert result.ok is True
        assert result.evidence["stage_branch"] == "feature/authorized-name"
        assert git(target, "branch", "--list", STAGE_BRANCH) == ""
