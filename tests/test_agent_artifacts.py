import base64
import hashlib
from pathlib import Path

import pytest

from ai_workflow_engine.agents.artifacts import (
    AgentRunRecord,
    ArtifactError,
    build_record,
    compute_run_id,
    load_run,
    save_run,
)
from ai_workflow_engine.agents.runner import RunObservation, VerificationCommandResult
from ai_workflow_engine.result import CheckResult, Status

_REPO = "/tmp/not-the-artifact-dir"


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _observation(**overrides: object) -> RunObservation:
    base = dict(
        agent_name="rev",
        agent_mode="read-only",
        agent_executable="/usr/bin/true",
        agent_args=[],
        timeout_seconds=30,
        task_id="T-1",
        stage="plan-review",
        prompt_id="0123456789abcdef",
        repository_head="a" * 40,
        ok=True,
        failure_code=None,
        report=None,
        exit_code=0,
        stdout=b'{"ok":true}',
        stderr=b"log line\n",
        actual_changed_paths=[],
        patch=b"",
        verification_results=[VerificationCommandResult(argv=["true"], exit_code=0)],
        sandbox_path=None,
    )
    base.update(overrides)
    return RunObservation(**base)  # type: ignore[arg-type]


def _verification(status: Status = Status.PASS) -> CheckResult:
    return CheckResult(
        check_name="agent-run",
        status=status,
        summary="ok",
        findings=[],
        evidence={"verdict": "APPROVED"},
        affected_paths=[],
        remediation_hint=None,
    )


def _built() -> tuple[AgentRunRecord, bytes]:
    return build_record(_observation(), _verification(), project_id="proj")


def test_build_record_computes_run_id() -> None:
    record, _patch = _built()
    assert compute_run_id(record) == record.run_id
    assert len(record.run_id) == 16


def test_run_id_is_deterministic() -> None:
    a, _ = _built()
    b, _ = _built()
    assert a.run_id == b.run_id


def test_stdout_stderr_digests_recompute_from_stored_b64() -> None:
    record, _ = _built()
    assert hashlib.sha256(base64.b64decode(record.stdout_b64)).hexdigest() == record.stdout_sha256
    assert hashlib.sha256(base64.b64decode(record.stderr_b64)).hexdigest() == record.stderr_sha256


def test_save_and_load_round_trip() -> None:
    record, patch = _built()
    rp, pp = save_run(record, patch, repository=_REPO)
    assert rp.exists() and pp.exists()
    loaded = load_run("proj", "T-1", "plan-review", record.run_id)
    assert loaded == record


def test_load_rejects_missing_patch_member() -> None:
    record, patch = _built()
    _rp, pp = save_run(record, patch, repository=_REPO)
    pp.unlink()
    with pytest.raises(ArtifactError, match="Incomplete"):
        load_run("proj", "T-1", "plan-review", record.run_id)


def test_load_rejects_tampered_record_field() -> None:
    record, patch = _built()
    rp, _ = save_run(record, patch, repository=_REPO)
    text = rp.read_text(encoding="utf-8")
    tampered = text.replace(
        '"repository_head":"' + "a" * 40 + '"', '"repository_head":"' + "b" * 40 + '"'
    )
    assert tampered != text
    rp.write_text(tampered, encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_run("proj", "T-1", "plan-review", record.run_id)


def test_load_rejects_tampered_patch() -> None:
    record, patch = _built()
    _, pp = save_run(record, patch, repository=_REPO)
    pp.write_bytes(b"corrupted patch bytes")
    with pytest.raises(ArtifactError, match="patch"):
        load_run("proj", "T-1", "plan-review", record.run_id)


def test_load_rejects_noncanonical_record() -> None:
    record, patch = _built()
    rp, _ = save_run(record, patch, repository=_REPO)
    body = rp.read_text(encoding="utf-8").rstrip("\n")
    rp.write_text("  " + body + "\n", encoding="utf-8")  # leading space => non-canonical
    with pytest.raises(ArtifactError):
        load_run("proj", "T-1", "plan-review", record.run_id)


def test_save_rejects_run_id_content_mismatch() -> None:
    record, patch = _built()
    forged = record.model_copy(update={"run_id": "f" * 16})
    with pytest.raises(ArtifactError, match="content hash"):
        save_run(forged, patch, repository=_REPO)


def test_identical_save_is_idempotent() -> None:
    record, patch = _built()
    first = save_run(record, patch, repository=_REPO)
    second = save_run(record, patch, repository=_REPO)
    assert first == second


def test_save_rejects_repository_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_workflow_engine.agents.artifacts as artifacts

    repo = tmp_path / "repo"
    (repo / ".awe").mkdir(parents=True)
    monkeypatch.setattr(artifacts, "_artifact_root", lambda: repo / ".awe" / "runs")
    record, patch = _built()
    with pytest.raises(ArtifactError, match="must not be inside"):
        save_run(record, patch, repository=str(repo))
