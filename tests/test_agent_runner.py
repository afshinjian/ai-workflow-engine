import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai_workflow_engine.agents import runner as runner_module
from ai_workflow_engine.agents.runner import (
    DirtyWorktree,
    HeadDrift,
    StageNotAllowed,
    run_agent,
    verification_argv,
)
from ai_workflow_engine.models import AgentSettings, EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.renderer import render_prompt
from ai_workflow_engine.prompt.store import save
from ai_workflow_engine.prompt.templates import get_template


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _cheap_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real verification re-runs `conda run ... pytest` in the sandbox — far too heavy and
    # environment-specific for a unit test. Swap in a trivial always-passing command; the
    # correspondence between verification_argv and the template is tested separately.
    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["true"]])


def _stub(
    tmp_path: Path,
    name: str,
    *,
    report: dict[str, object] | None = None,
    exit_code: int = 0,
    sleep: float = 0.0,
    raw_stdout: bytes | None = None,
    create_files: Sequence[str] = (),
    mutate_path: str | None = None,
) -> Path:
    body = ["#!/usr/bin/env python3", "import sys, time, json", "sys.stdin.buffer.read()"]
    if sleep:
        body.append(f"time.sleep({sleep})")
    for relative in create_files:
        body.append(f"open({relative!r}, 'w').write('x')")
    if mutate_path is not None:
        body.append(f"open({mutate_path!r}, 'w').write('mutated')")
    if raw_stdout is not None:
        body.append(f"sys.stdout.buffer.write({raw_stdout!r})")
    elif report is not None:
        body.append(f"sys.stdout.write(json.dumps({report!r}))")
    body.append(f"sys.exit({exit_code})")
    path = tmp_path / name
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _make_prompt(
    engine_config: EngineConfig, stage: str, task_id: str, allowed: Sequence[str] = ()
):
    context = build_prompt_context(
        engine_config, stage=stage, task_id=task_id, allowed_paths=list(allowed)
    )
    rendered = render_prompt(context)
    save(rendered)
    return rendered


def _report(rendered, *, verdict: str | None, changed: Sequence[str] = ()) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": rendered.context.task_id,
        "stage": rendered.context.stage,
        "prompt_id": rendered.prompt_id,
        "verdict": verdict,
        "summary": "done",
        "findings": [],
        "changed_paths": sorted(changed),
        "verification_commands_run": ["true"],
        "blockers": [],
    }


def _agent(executable: Path, *, mode: str, stages: list[str], timeout: int = 30) -> AgentSettings:
    return AgentSettings(
        name="agent",
        executable=executable,
        args=[],
        mode=mode,
        timeout_seconds=timeout,
        stages=stages,
    )


# ---- happy paths ---------------------------------------------------------------


def test_honest_read_only_agent_succeeds(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "reviewer", report=_report(rendered, verdict="APPROVED"))
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.ok
    assert obs.failure_code is None
    assert obs.report is not None and obs.report.verdict == "APPROVED"
    assert obs.actual_changed_paths == []
    assert [r.exit_code for r in obs.verification_results] == [0]
    assert obs.sandbox_path is None  # torn down


def test_honest_scoped_write_agent_succeeds(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=["newfile.txt"])
    stub = _stub(
        tmp_path,
        "writer",
        report=_report(rendered, verdict=None, changed=["newfile.txt"]),
        create_files=["newfile.txt"],
    )
    agent = _agent(stub, mode="scoped-write", stages=["implementation"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="implementation", prompt_id=rendered.prompt_id
    )
    assert obs.ok, obs.failure_code
    assert obs.actual_changed_paths == ["newfile.txt"]
    assert b"newfile.txt" in obs.patch


# ---- failure taxonomy ----------------------------------------------------------


def test_stage_not_allowed(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "s", report=_report(rendered, verdict="APPROVED"))
    agent = _agent(stub, mode="read-only", stages=["governance-review"])
    with pytest.raises(StageNotAllowed):
        run_agent(
            engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
        )


def test_agent_timeout(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "slow", report=_report(rendered, verdict="APPROVED"), sleep=30)
    agent = _agent(stub, mode="read-only", stages=["plan-review"], timeout=1)
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_timeout"
    assert not obs.ok


def test_agent_nonzero_exit(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "boom", report=_report(rendered, verdict="APPROVED"), exit_code=3)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_nonzero_exit"
    assert obs.exit_code == 3


def test_agent_stdout_not_utf8(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "binary", raw_stdout=b"\xff\xfe\x00")
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_stdout_not_utf8"


def test_agent_report_invalid_malformed_json(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "bad", raw_stdout=b"{not json")
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_invalid"


def test_agent_report_invalid_extra_field(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    report = _report(rendered, verdict="APPROVED")
    report["unexpected"] = "x"
    stub = _stub(tmp_path, "extra", report=report)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_invalid"


def test_agent_report_invalid_duplicate_keys(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    good = json.dumps(_report(rendered, verdict="APPROVED"))
    duplicated = good[:-1] + ',"summary":"again"}'
    stub = _stub(tmp_path, "dup", raw_stdout=duplicated.encode("utf-8"))
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_invalid"


def test_agent_report_mismatch_wrong_prompt_id(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    report = _report(rendered, verdict="APPROVED")
    report["prompt_id"] = "0" * 16
    stub = _stub(tmp_path, "wrong", report=report)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_mismatch"


def test_agent_report_mismatch_wrong_task_id(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    report = _report(rendered, verdict="APPROVED")
    report["task_id"] = "T-999"
    stub = _stub(tmp_path, "wrongtask", report=report)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_mismatch"


def test_agent_report_mismatch_wrong_stage(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    report = _report(rendered, verdict="APPROVED")
    report["stage"] = "governance-review"  # a valid stage, but not this prompt's
    stub = _stub(tmp_path, "wrongstage", report=report)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_mismatch"


def test_verdict_stage_missing_verdict_is_mismatch(
    engine_config: EngineConfig, tmp_path: Path
) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    report = _report(rendered, verdict=None)  # plan-review requires a verdict
    stub = _stub(tmp_path, "noverdict", report=report)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_mismatch"


def test_read_only_agent_claiming_changes_is_mismatch(
    engine_config: EngineConfig, tmp_path: Path
) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    report = _report(rendered, verdict="APPROVED", changed=["x.py"])
    stub = _stub(tmp_path, "liar", report=report)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "agent_report_mismatch"


def test_repository_mutation_is_detected(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    mutate = engine_config.project.repository / "MUTATED.txt"
    stub = _stub(
        tmp_path, "hostile", report=_report(rendered, verdict="APPROVED"), mutate_path=str(mutate)
    )
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.failure_code == "repository_mutated"
    assert obs.report is None


# ---- precondition gate ---------------------------------------------------------


def test_dirty_worktree_rejected(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    (engine_config.project.repository / "dirty.txt").write_text("x", encoding="utf-8")
    stub = _stub(tmp_path, "s", report=_report(rendered, verdict="APPROVED"))
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    with pytest.raises(DirtyWorktree):
        run_agent(
            engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
        )


def test_head_drift_rejected(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    # Add a commit so the live HEAD no longer matches the prompt's recorded head.
    import subprocess

    repo = engine_config.project.repository
    (repo / "another.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "drift"], check=True, capture_output=True
    )
    stub = _stub(tmp_path, "s", report=_report(rendered, verdict="APPROVED"))
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    with pytest.raises(HeadDrift):
        run_agent(
            engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
        )


def test_keep_sandbox_retains_directory(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "s", report=_report(rendered, verdict="APPROVED"))
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config,
        agent,
        task_id="T-1",
        stage="plan-review",
        prompt_id=rendered.prompt_id,
        keep_sandbox=True,
    )
    assert obs.sandbox_path is not None and obs.sandbox_path.exists()
    from ai_workflow_engine.agents.sandbox import teardown

    teardown(obs.sandbox_path)


# ---- environment scrubbing & verification correspondence -----------------------


def test_environment_is_scrubbed(engine_config: EngineConfig, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_TOKEN", "should-not-leak")
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    # Stub emits the report only if SECRET_TOKEN is absent from its environment.
    body_report = _report(rendered, verdict="APPROVED")
    stub = tmp_path / "envcheck"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, json\n"
        "sys.stdin.buffer.read()\n"
        "assert 'SECRET_TOKEN' not in os.environ\n"
        f"sys.stdout.write(json.dumps({body_report!r}))\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    agent = _agent(stub, mode="read-only", stages=["plan-review"])
    obs = run_agent(
        engine_config, agent, task_id="T-1", stage="plan-review", prompt_id=rendered.prompt_id
    )
    assert obs.ok, obs.stderr


def test_verification_argv_matches_template(engine_config: EngineConfig) -> None:
    # Prove the executed argv equals the commands displayed in the rendered prompt.
    from ai_workflow_engine.prompt.renderer import _shell_escape

    env = engine_config.project.conda_environment
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    rendered = render_prompt(context)
    body = rendered.markdown
    section = body.split("## Verification commands\n", 1)[1].split("\n## Stop condition", 1)[0]
    displayed = section.strip("\n").split("\n")

    expected = []
    for argv in verification_argv(env):
        rendered_tokens = [_shell_escape(env) if token == env else token for token in argv]
        expected.append(" ".join(rendered_tokens))
    assert displayed == expected
    # And the template still uses the shell placeholder (sanity: no accidental template change).
    assert "{{CONDA_ENVIRONMENT_SHELL}}" in get_template("plan-review").content
