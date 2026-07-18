import subprocess
from pathlib import Path

import pytest

from ai_workflow_engine.agents.artifacts import AgentRunRecord, build_record, save_run
from ai_workflow_engine.agents.runner import RunObservation, VerificationCommandResult
from ai_workflow_engine.commit.gates import run_apply_patch_gate
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.result import CheckResult, Status


def git(repo: object, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def apply_config(repository: Path, config_factory: object) -> EngineConfig:
    from ai_workflow_engine.config import load_config

    return load_config(config_factory(repository))  # type: ignore[operator]


def _patch_for(repo: Path, relative: str, content: str) -> bytes:
    """Produce a patch that creates ``relative`` with ``content``, without leaving it staged."""
    (repo / relative).write_text(content, encoding="utf-8")
    git(repo, "add", relative)
    patch = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--binary"],
        check=True,
        capture_output=True,
    ).stdout
    git(repo, "reset", "--hard")
    return patch


def _store_run(
    config: EngineConfig,
    *,
    patch: bytes,
    verification_status: Status = Status.PASS,
    mode: str = "scoped-write",
    head: str | None = None,
) -> AgentRunRecord:
    client = GitClient(config.project.repository)
    observation = RunObservation(
        agent_name="w",
        agent_mode=mode,
        agent_executable="/usr/bin/true",
        agent_args=[],
        timeout_seconds=30,
        task_id="T-1",
        stage="implementation",
        prompt_id="0123456789abcdef",
        repository_head=head or client.head(),
        ok=True,
        failure_code=None,
        report=None,
        exit_code=0,
        stdout=b"",
        stderr=b"",
        actual_changed_paths=["applied.txt"],
        patch=patch,
        verification_results=[VerificationCommandResult(argv=["true"], exit_code=0)],
    )
    verification = CheckResult(
        check_name="agent-run",
        status=verification_status,
        summary="v",
        findings=[],
        evidence={},
        affected_paths=[],
        remediation_hint=None,
    )
    record, patch_bytes = build_record(observation, verification, project_id=config.project.id)
    save_run(record, patch_bytes, repository=str(config.project.repository))
    return record


def test_happy_path_applies_to_working_tree(apply_config: EngineConfig) -> None:
    repo = apply_config.project.repository
    patch = _patch_for(repo, "applied.txt", "content\n")
    record = _store_run(apply_config, patch=patch)
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.PASS, [f.code for f in result.findings]
    assert (repo / "applied.txt").read_text(encoding="utf-8") == "content\n"
    # Index untouched (worktree only): the new file is untracked, not staged.
    assert (repo / "applied.txt").name in git(repo, "status", "--porcelain")


def test_missing_run_refused(apply_config: EngineConfig) -> None:
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id="0" * 16
    )
    assert result.status == Status.FAIL
    assert "run_unavailable" in {f.code for f in result.findings}


def test_unverified_run_refused(apply_config: EngineConfig) -> None:
    repo = apply_config.project.repository
    patch = _patch_for(repo, "applied.txt", "content\n")
    record = _store_run(apply_config, patch=patch, verification_status=Status.FAIL)
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.FAIL
    assert "run_not_verified" in {f.code for f in result.findings}


def test_read_only_run_refused(apply_config: EngineConfig) -> None:
    repo = apply_config.project.repository
    patch = _patch_for(repo, "applied.txt", "content\n")
    record = _store_run(apply_config, patch=patch, mode="read-only")
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.FAIL
    assert "run_not_scoped_write" in {f.code for f in result.findings}


def test_head_drift_refused(apply_config: EngineConfig) -> None:
    repo = apply_config.project.repository
    patch = _patch_for(repo, "applied.txt", "content\n")
    record = _store_run(apply_config, patch=patch, head="a" * 40)
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.FAIL
    assert "head_drift" in {f.code for f in result.findings}


def test_dirty_tree_refused(apply_config: EngineConfig) -> None:
    repo = apply_config.project.repository
    patch = _patch_for(repo, "applied.txt", "content\n")
    record = _store_run(apply_config, patch=patch)
    (repo / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.FAIL
    assert "dirty_overlap" in {f.code for f in result.findings}
    assert not (repo / "applied.txt").exists()  # nothing applied


def test_apply_check_failure_refused(apply_config: EngineConfig) -> None:
    repo = apply_config.project.repository
    # Commit a conflicting version of applied.txt FIRST, then store the run at that same HEAD so
    # head_drift cannot fire — the only remaining failure is apply_check (the add-file patch
    # conflicts with the now-existing committed file), proving that branch independently.
    (repo / "applied.txt").write_text("already here\n", encoding="utf-8")
    git(repo, "add", "applied.txt")
    git(repo, "commit", "-m", "pre-existing applied.txt")
    # Build an add-file patch for applied.txt from a throwaway state, then reset to the committed
    # version so the patch conflicts.
    patch = _patch_for(repo, "conflict_marker_only.txt", "x\n")  # get a clean tree baseline
    # Craft an add patch for a path that already exists (will fail apply --check).
    import subprocess

    (repo / "applied2.txt").write_text("fresh\n", encoding="utf-8")
    git(repo, "add", "applied2.txt")
    add_patch = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--binary"], check=True, capture_output=True
    ).stdout
    git(repo, "reset", "--hard")
    # Rewrite the add patch to target the already-committed applied.txt so it conflicts.
    conflicting = add_patch.replace(b"applied2.txt", b"applied.txt")
    record = _store_run(apply_config, patch=conflicting)  # stored at the current (unchanged) HEAD
    assert patch  # keep the baseline reference
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.FAIL
    assert "apply_check_failed" in {f.code for f in result.findings}
    assert "head_drift" not in {f.code for f in result.findings}  # HEAD did not move


def test_patch_digest_mismatch_refused(apply_config: EngineConfig) -> None:
    # If the stored .patch member is tampered between load-time verification and the gate's
    # re-read, the gate must refuse (defence against a TOCTOU on the local artifact store).
    repo = apply_config.project.repository
    patch = _patch_for(repo, "applied.txt", "content\n")
    record = _store_run(apply_config, patch=patch)
    from ai_workflow_engine.agents.artifacts import run_patch_path

    # Corrupt the stored patch member in place after it was created/verified.
    pp = run_patch_path(apply_config.project.id, "T-1", "implementation", record.run_id)
    pp.write_bytes(b"tampered\n")
    result = run_apply_patch_gate(
        apply_config, task_id="T-1", stage="implementation", run_id=record.run_id
    )
    assert result.status == Status.FAIL
    # load_run itself re-verifies the member first, so this surfaces as run_unavailable OR the
    # gate's own digest re-check — either way it refuses with no write.
    codes = {f.code for f in result.findings}
    assert codes & {"run_unavailable", "patch_digest_mismatch"}
    assert not (repo / "applied.txt").exists()
