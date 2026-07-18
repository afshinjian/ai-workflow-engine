import subprocess
from pathlib import Path

import pytest

from ai_workflow_engine.commit.gates import run_commit_gate
from ai_workflow_engine.git.approval import CommitApproval
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.result import Status


def git(repo: object, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def committed_config(repository: Path, config_factory: object) -> EngineConfig:
    from ai_workflow_engine.config import load_config

    return load_config(config_factory(repository))  # type: ignore[operator]


def _approval(config: EngineConfig, **overrides: object) -> CommitApproval:
    head = GitClient(config.project.repository).head()
    base: dict[str, object] = {
        "kind": "commit",
        "task_id": "T-1",
        "branch": "main",
        "head": head,
        "allowed_paths": ["newfile.txt"],
        "message": "add newfile",
        "approved_by": "human",
    }
    base.update(overrides)
    return CommitApproval.model_validate(base)


def _ap_file(tmp_path: Path) -> Path:
    path = tmp_path / "approval.yaml"
    path.write_text("kind: commit\n", encoding="utf-8")
    return path


def test_happy_path_commits_exactly_the_approved_path(
    committed_config: EngineConfig, tmp_path: Path
) -> None:
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    result = run_commit_gate(committed_config, _approval(committed_config), _ap_file(tmp_path))
    assert result.status == Status.PASS, [f.code for f in result.findings]
    assert git(repo, "diff", "--name-only", "HEAD~1", "HEAD") == "newfile.txt"
    assert git(repo, "show", "--no-patch", "--format=%B", "HEAD").strip() == "add newfile"


def test_refusal_by_default_no_unapproved_change_slips_in(
    committed_config: EngineConfig, tmp_path: Path
) -> None:
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    (repo / "sneaky.txt").write_text("unapproved\n", encoding="utf-8")
    before = git(repo, "rev-parse", "HEAD")
    result = run_commit_gate(committed_config, _approval(committed_config), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "unapproved_change" in {f.code for f in result.findings}
    assert git(repo, "rev-parse", "HEAD") == before  # nothing committed


def test_nothing_to_stage(committed_config: EngineConfig, tmp_path: Path) -> None:
    # Approved path has no working-tree change.
    result = run_commit_gate(committed_config, _approval(committed_config), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "nothing_to_stage" in {f.code for f in result.findings}


def test_branch_mismatch(committed_config: EngineConfig, tmp_path: Path) -> None:
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    result = run_commit_gate(
        committed_config, _approval(committed_config, branch="not-main"), _ap_file(tmp_path)
    )
    assert result.status == Status.FAIL
    assert "branch_mismatch" in {f.code for f in result.findings}


def test_head_mismatch(committed_config: EngineConfig, tmp_path: Path) -> None:
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    result = run_commit_gate(
        committed_config, _approval(committed_config, head="b" * 40), _ap_file(tmp_path)
    )
    assert result.status == Status.FAIL
    assert "head_mismatch" in {f.code for f in result.findings}


def test_index_not_clean(committed_config: EngineConfig, tmp_path: Path) -> None:
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    (repo / "prestaged.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "prestaged.txt")  # dirty the index before the gate runs
    result = run_commit_gate(committed_config, _approval(committed_config), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "index_not_clean" in {f.code for f in result.findings}


def test_protected_path_in_approval_rejected(
    repository: Path, config_factory: object, tmp_path: Path
) -> None:
    import yaml

    from ai_workflow_engine.config import load_config

    # Add a protected pattern to the config and approve a matching path.
    cfg_path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(cfg_path.read_text())
    raw["protected_paths"] = {"never_commit": ["secret/*"]}
    cfg_path.write_text(yaml.safe_dump(raw))
    config = load_config(cfg_path)
    repo = config.project.repository
    (repo / "secret").mkdir()
    (repo / "secret" / "key.txt").write_text("s\n", encoding="utf-8")
    result = run_commit_gate(
        config, _approval(config, allowed_paths=["secret/key.txt"]), _ap_file(tmp_path)
    )
    assert result.status == Status.FAIL
    assert "protected_path_violation" in {f.code for f in result.findings}


def test_commit_of_a_deletion(committed_config: EngineConfig, tmp_path: Path) -> None:
    repo = committed_config.project.repository
    # Delete a tracked file and approve exactly that deletion.
    (repo / "pyproject.toml").unlink()
    result = run_commit_gate(
        committed_config,
        _approval(committed_config, allowed_paths=["pyproject.toml"], message="drop pyproject"),
        _ap_file(tmp_path),
    )
    assert result.status == Status.PASS, [f.code for f in result.findings]
    assert git(repo, "diff", "--name-only", "HEAD~1", "HEAD") == "pyproject.toml"


def test_audit_trail_records_approver_and_digest(
    committed_config: EngineConfig, tmp_path: Path
) -> None:
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    ap = _ap_file(tmp_path)
    result = run_commit_gate(committed_config, _approval(committed_config), ap)
    assert result.evidence["approved_by"] == "human"
    assert len(str(result.evidence["approval_sha256"])) == 64


def test_post_hoc_commit_mismatch_is_flagged(
    committed_config: EngineConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a race/bug where the committed path set diverges from the approval after the
    # commit: the defensive post-hoc check must FAIL loudly (commit exists but is flagged).
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")

    from ai_workflow_engine.git import client as client_module

    real = client_module.GitClient.commit_change_names
    calls = {"n": 0}

    def fake(self: object, parent: str, commit: str) -> list[str]:
        calls["n"] += 1
        return ["something_else.txt"]  # lie about what was committed

    monkeypatch.setattr(client_module.GitClient, "commit_change_names", fake)
    result = run_commit_gate(committed_config, _approval(committed_config), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "commit_mismatch" in {f.code for f in result.findings}
    assert "commit" in result.evidence  # the commit hash is recorded even on a flagged mismatch
    assert calls["n"] >= 1
    monkeypatch.setattr(client_module.GitClient, "commit_change_names", real)


def test_staged_set_mismatch_rolls_back(
    committed_config: EngineConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate the staged set diverging from the approval after staging: the gate must unstage
    # and FAIL without committing.
    repo = committed_config.project.repository
    (repo / "newfile.txt").write_text("hi\n", encoding="utf-8")
    before = _head_of(repo)

    from ai_workflow_engine.git import client as client_module

    monkeypatch.setattr(client_module.GitClient, "staged_names", lambda self: ["unexpected.txt"])
    result = run_commit_gate(committed_config, _approval(committed_config), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "staged_set_mismatch" in {f.code for f in result.findings}
    assert _head_of(repo) == before  # nothing committed


def _head_of(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")
