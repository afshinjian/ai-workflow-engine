from pathlib import Path

import pytest

from ai_workflow_engine.agents import runner as runner_module
from ai_workflow_engine.agents.runner import run_agent
from ai_workflow_engine.agents.verification import verify_run
from ai_workflow_engine.models import AgentSettings, EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.renderer import render_prompt
from ai_workflow_engine.prompt.store import save
from ai_workflow_engine.result import Status


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _cheap_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["true"]])


def _make_prompt(engine_config: EngineConfig, stage: str, task_id: str, allowed=()):
    context = build_prompt_context(
        engine_config, stage=stage, task_id=task_id, allowed_paths=list(allowed)
    )
    rendered = render_prompt(context)
    save(rendered)
    return rendered


def _report(rendered, *, verdict, changed=()) -> dict[str, object]:
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


def _stub(tmp_path: Path, name: str, *, report=None, create_files=(), fail_verify=False) -> Path:
    body = ["#!/usr/bin/env python3", "import sys, json", "sys.stdin.buffer.read()"]
    for relative in create_files:
        body.append(f"import os; os.makedirs(os.path.dirname({relative!r}) or '.', exist_ok=True)")
        body.append(f"open({relative!r}, 'w').write('x')")
    import json as _json

    if report is not None:
        body.append(f"sys.stdout.write({_json.dumps(_json.dumps(report))})")
    path = tmp_path / name
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _agent(executable: Path, *, mode: str, stages: list[str]) -> AgentSettings:
    return AgentSettings(
        name="agent", executable=executable, args=[], mode=mode, timeout_seconds=30, stages=stages
    )


def _run(engine_config, agent, rendered, stage="plan-review"):
    return run_agent(engine_config, agent, task_id="T-1", stage=stage, prompt_id=rendered.prompt_id)


def test_honest_read_only_run_verifies_pass(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "ok", report=_report(rendered, verdict="APPROVED"))
    obs = _run(engine_config, _agent(stub, mode="read-only", stages=["plan-review"]), rendered)
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.PASS
    assert result.evidence["verdict"] == "APPROVED"


def test_honest_scoped_write_run_verifies_pass(engine_config: EngineConfig, tmp_path: Path) -> None:
    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=["newfile.txt"])
    stub = _stub(
        tmp_path,
        "w",
        report=_report(rendered, verdict=None, changed=["newfile.txt"]),
        create_files=["newfile.txt"],
    )
    obs = _run(
        engine_config,
        _agent(stub, mode="scoped-write", stages=["implementation"]),
        rendered,
        stage="implementation",
    )
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.PASS, [f.code for f in result.findings]


def test_under_claim_is_caught(engine_config: EngineConfig, tmp_path: Path) -> None:
    # Agent changes a file but claims no changes.
    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=["newfile.txt"])
    stub = _stub(
        tmp_path,
        "under",
        report=_report(rendered, verdict=None, changed=[]),
        create_files=["newfile.txt"],
    )
    obs = _run(
        engine_config,
        _agent(stub, mode="scoped-write", stages=["implementation"]),
        rendered,
        stage="implementation",
    )
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert "claim_mismatch" in {f.code for f in result.findings}


def test_over_claim_is_caught(engine_config: EngineConfig, tmp_path: Path) -> None:
    # Agent claims a change it did not make.
    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=["newfile.txt"])
    stub = _stub(tmp_path, "over", report=_report(rendered, verdict=None, changed=["newfile.txt"]))
    obs = _run(
        engine_config,
        _agent(stub, mode="scoped-write", stages=["implementation"]),
        rendered,
        stage="implementation",
    )
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert "claim_mismatch" in {f.code for f in result.findings}


def test_out_of_scope_write_is_caught(engine_config: EngineConfig, tmp_path: Path) -> None:
    # Allowed path is a.txt but the agent writes b.txt.
    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=["a.txt"])
    stub = _stub(
        tmp_path,
        "scope",
        report=_report(rendered, verdict=None, changed=["b.txt"]),
        create_files=["b.txt"],
    )
    obs = _run(
        engine_config,
        _agent(stub, mode="scoped-write", stages=["implementation"]),
        rendered,
        stage="implementation",
    )
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert "scope_violation" in {f.code for f in result.findings}


def test_verification_command_failure_is_caught(
    engine_config: EngineConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["false"]])
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(tmp_path, "vf", report=_report(rendered, verdict="APPROVED"))
    obs = _run(engine_config, _agent(stub, mode="read-only", stages=["plan-review"]), rendered)
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert "verification_command_failed" in {f.code for f in result.findings}


def test_runner_failure_surfaces_in_verification(
    engine_config: EngineConfig, tmp_path: Path
) -> None:
    # An agent whose report is invalid: runner marks not-ok, verification reports the failure code.
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = tmp_path / "bad"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdin.buffer.read()\n"
        "sys.stdout.write('not json')\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    obs = _run(engine_config, _agent(stub, mode="read-only", stages=["plan-review"]), rendered)
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert result.findings[0].code == "agent_report_invalid"


def test_protected_path_write_is_caught(engine_config: EngineConfig, tmp_path: Path) -> None:
    # A path that is inside allowed_paths (scope passes) but matches a protected pattern.
    protected_rel = "docs/planning/plans/x_plan_recovery_y.md"
    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=[protected_rel])
    stub = _stub(
        tmp_path,
        "prot",
        report=_report(rendered, verdict=None, changed=[protected_rel]),
        create_files=[protected_rel],
    )
    obs = _run(
        engine_config,
        _agent(stub, mode="scoped-write", stages=["implementation"]),
        rendered,
        stage="implementation",
    )
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    codes = {f.code for f in result.findings}
    assert "protected_path_violation" in codes
    assert "scope_violation" not in codes  # it WAS within scope; only the protected rule fails


def test_read_only_agent_that_physically_writes_is_caught(
    engine_config: EngineConfig, tmp_path: Path
) -> None:
    # A read-only agent that writes a file but honestly reports changed_paths=[] (so the runner's
    # read-only binding passes) is still caught by verify_run: actual != claimed.
    rendered = _make_prompt(engine_config, "plan-review", "T-1")
    stub = _stub(
        tmp_path,
        "rowrite",
        report=_report(rendered, verdict="APPROVED", changed=[]),
        create_files=["sneaky.txt"],
    )
    obs = _run(engine_config, _agent(stub, mode="read-only", stages=["plan-review"]), rendered)
    assert obs.ok  # runner binding passed (claim was empty, as read-only requires)
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert "claim_mismatch" in {f.code for f in result.findings}


def test_malformed_changed_path_is_caught(engine_config: EngineConfig) -> None:
    # Defensive: a synthetic observation carrying a non-repo-relative path must be flagged.
    from ai_workflow_engine.agents.models import AgentReport
    from ai_workflow_engine.agents.runner import RunObservation

    rendered = _make_prompt(engine_config, "implementation", "T-1", allowed=["a.txt"])
    report = AgentReport.model_validate(_report(rendered, verdict=None, changed=[]))
    obs = RunObservation(
        agent_name="a",
        agent_mode="scoped-write",
        agent_executable="/usr/bin/true",
        agent_args=[],
        timeout_seconds=30,
        task_id="T-1",
        stage="implementation",
        prompt_id=rendered.prompt_id,
        repository_head=rendered.metadata.repository_head,
        ok=True,
        failure_code=None,
        report=report.model_copy(update={"changed_paths": ["/abs/escape"]}),
        exit_code=0,
        stdout=b"",
        stderr=b"",
        actual_changed_paths=["/abs/escape"],
        patch=b"",
        verification_results=[],
    )
    result = verify_run(engine_config, rendered, obs)
    assert result.status == Status.FAIL
    assert "malformed_changed_path" in {f.code for f in result.findings}
