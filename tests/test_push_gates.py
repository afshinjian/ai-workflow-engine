import subprocess
from pathlib import Path

import pytest

from ai_workflow_engine.commit.gates import run_push_gate
from ai_workflow_engine.git.approval import PushApproval
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.result import Status


def git(repo: object, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def push_config(repository_with_remote: Path, config_factory: object) -> EngineConfig:
    from ai_workflow_engine.config import load_config

    return load_config(config_factory(repository_with_remote))  # type: ignore[operator]


def _approval(config: EngineConfig, **overrides: object) -> PushApproval:
    client = GitClient(config.project.repository)
    base: dict[str, object] = {
        "kind": "push",
        "task_id": "T-1",
        "branch": "main",
        "head": client.head(),
        "upstream": client.upstream(),
        "approved_by": "human",
    }
    base.update(overrides)
    return PushApproval.model_validate(base)


def _ap_file(tmp_path: Path) -> Path:
    path = tmp_path / "push.yaml"
    path.write_text("kind: push\n", encoding="utf-8")
    return path


def _make_local_commit(repo: Path) -> str:
    (repo / "extra.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "extra.txt")
    git(repo, "commit", "-m", "local work")
    return git(repo, "rev-parse", "HEAD")


def test_happy_path_pushes_once(push_config: EngineConfig, tmp_path: Path) -> None:
    repo = push_config.project.repository
    head = _make_local_commit(repo)
    before = git(repo, "rev-parse", "origin/main")
    result = run_push_gate(push_config, _approval(push_config, head=head), _ap_file(tmp_path))
    assert result.status == Status.PASS, [f.code for f in result.findings]
    after = git(repo, "rev-parse", "origin/main")
    assert after != before
    assert after == head  # the remote now points at our local HEAD


def test_nothing_to_push(push_config: EngineConfig, tmp_path: Path) -> None:
    repo = push_config.project.repository
    before = git(repo, "rev-parse", "origin/main")
    result = run_push_gate(push_config, _approval(push_config), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "nothing_to_push" in {f.code for f in result.findings}
    assert git(repo, "rev-parse", "origin/main") == before  # no push happened


def test_branch_mismatch(push_config: EngineConfig, tmp_path: Path) -> None:
    repo = push_config.project.repository
    head = _make_local_commit(repo)
    result = run_push_gate(
        push_config, _approval(push_config, head=head, branch="wrong"), _ap_file(tmp_path)
    )
    assert result.status == Status.FAIL
    assert "branch_mismatch" in {f.code for f in result.findings}


def test_head_mismatch(push_config: EngineConfig, tmp_path: Path) -> None:
    _make_local_commit(push_config.project.repository)
    result = run_push_gate(push_config, _approval(push_config, head="a" * 40), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "head_mismatch" in {f.code for f in result.findings}


def test_upstream_mismatch(push_config: EngineConfig, tmp_path: Path) -> None:
    repo = push_config.project.repository
    head = _make_local_commit(repo)
    result = run_push_gate(
        push_config, _approval(push_config, head=head, upstream="origin/other"), _ap_file(tmp_path)
    )
    assert result.status == Status.FAIL
    assert "upstream_mismatch" in {f.code for f in result.findings}


def test_dirty_worktree_refused(push_config: EngineConfig, tmp_path: Path) -> None:
    repo = push_config.project.repository
    head = _make_local_commit(repo)
    (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")  # untracked => dirty
    before = git(repo, "rev-parse", "origin/main")
    result = run_push_gate(push_config, _approval(push_config, head=head), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "dirty_worktree" in {f.code for f in result.findings}
    assert git(repo, "rev-parse", "origin/main") == before  # no push happened


def test_behind_remote_refused(push_config: EngineConfig, tmp_path: Path) -> None:
    # Advance the remote beyond the local branch so the local is behind (fast-forward impossible).
    repo = push_config.project.repository
    # Clone the remote elsewhere, add a commit, push it, so origin/main is ahead of our local.
    other = tmp_path / "other"
    remote_url = git(repo, "remote", "get-url", "origin")
    subprocess.run(["git", "clone", remote_url, str(other)], check=True, capture_output=True)
    git(other, "config", "user.email", "o@o")
    git(other, "config", "user.name", "o")
    (other / "remote_only.txt").write_text("r\n", encoding="utf-8")
    git(other, "add", "remote_only.txt")
    git(other, "commit", "-m", "remote work")
    git(other, "push", "origin", "main")
    # Now make a divergent local commit and fetch so origin/main is known-ahead.
    head = _make_local_commit(repo)
    git(repo, "fetch", "origin")
    before = git(repo, "rev-parse", "origin/main")
    result = run_push_gate(push_config, _approval(push_config, head=head), _ap_file(tmp_path))
    assert result.status == Status.FAIL
    assert "behind_remote" in {f.code for f in result.findings}
    assert git(repo, "rev-parse", "origin/main") == before  # no push happened
