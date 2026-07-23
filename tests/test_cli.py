import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_workflow_engine.cli import app
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.models import PromptSuccess
from ai_workflow_engine.prompt.renderer import canonical_json, render_prompt

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_prompt_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "prompt-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "1.0.0"


def test_json_output_schema(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(app, ["check-handover", "--config", str(config), "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert list(payload) == [
        "check_name",
        "status",
        "summary",
        "findings",
        "evidence",
        "affected_paths",
        "remediation_hint",
        "timestamp",
    ]
    assert payload["status"] == "PASS"


def test_failed_check_has_nonzero_exit(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app, ["check-git", "--config", str(config), "--expected-branch", "definitely-wrong"]
    )
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


def test_verify_json_wrapper(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(app, ["verify", "--config", str(config), "--output", "json"])
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "1.0"
    assert payload["project_id"] == "test-project"
    assert len(payload["checks"]) == 4


def _run_cli(args: list[str], *, force_color: bool) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if force_color:
        env["FORCE_COLOR"] = "3"
    else:
        env.pop("FORCE_COLOR", None)
    return subprocess.run(
        [sys.executable, "-m", "ai_workflow_engine", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize("force_color", [False, True])
def test_machine_output_is_uncolored_and_valid_under_force_color(
    repository: Path, config_factory: object, force_color: bool
) -> None:
    # Regression (T-104): machine-readable output must never contain ANSI escapes, even when
    # FORCE_COLOR is set in the environment, or the stable 1.0 JSON contract becomes unparseable.
    config = config_factory(repository)  # type: ignore[operator]

    version = _run_cli(["version"], force_color=force_color)
    assert version.returncode == 0
    assert version.stdout.strip() == "1.0.0"
    assert "\x1b" not in version.stdout

    for command in (
        ["verify", "--config", str(config), "--output", "json"],
        ["check-handover", "--config", str(config), "--output", "json"],
        ["inspect", "--config", str(config), "--output", "json"],
        ["state", "next", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    ):
        result = _run_cli(command, force_color=force_color)
        assert result.returncode == 0, result.stderr
        assert "\x1b" not in result.stdout, f"ANSI escape leaked into {command[0]} JSON output"
        json.loads(result.stdout)  # raises if the color codes corrupted the JSON


def test_state_next_empty_history(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(app, ["state", "next", "--config", str(config), "--task-id", "T-1"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "plan-review"


def test_state_record_and_show_json(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    record = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--verdict",
            "APPROVED",
            "--output",
            "json",
        ],
    )
    assert record.exit_code == 0
    payload = json.loads(record.stdout)
    assert payload["status"] == "PASS"
    assert payload["event"]["stage"] == "plan-review"
    assert payload["event"]["verdict"] == "APPROVED"
    assert payload["next_stage"] == "implementation"

    show = runner.invoke(
        app,
        ["state", "show", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    )
    assert show.exit_code == 0
    shown = json.loads(show.stdout)
    assert len(shown["events"]) == 1
    assert shown["next_stage"] == "implementation"
    assert shown["terminal"] is False


def test_state_record_transition_violation_exits_one(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "implementation",
            "--completed",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert payload["finding"]["code"] == "transition_violation"


def test_state_record_verdict_forbidden(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--verdict",
            "APPROVED",
        ],
    )
    result = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "implementation",
            "--verdict",
            "APPROVED",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["finding"]["code"] == "verdict_forbidden"


def test_state_record_requires_exactly_one_outcome(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        ["state", "record", "--config", str(config), "--task-id", "T-1", "--stage", "plan-review"],
    )
    assert result.exit_code == 2
    assert "ERROR:" in result.output


def test_inspect_error_is_concise_and_nonzero() -> None:
    result = runner.invoke(app, ["inspect", "--config", "/nonexistent/config.yaml"])
    assert result.exit_code != 0
    assert "ERROR:" in result.output
    assert "Traceback (most recent call last)" not in result.output


def test_debug_inspect_error_includes_traceback() -> None:
    result = runner.invoke(app, ["--debug", "inspect", "--config", "/nonexistent/config.yaml"])
    assert result.exit_code != 0
    assert "ERROR:" in result.output
    assert "Traceback (most recent call last)" in result.output


# --- workflowctl prompt ------------------------------------------------------------

PROMPT_STAGES = [
    ("plan-review", []),
    ("implementation", ["--allowed-path", "src/a.py"]),
    ("implementation-review", []),
    ("remediation", ["--allowed-path", "src/a.py", "--finding", "Fix the bug"]),
    ("governance-closeout", []),
    ("governance-review", []),
    ("push", []),
]


@pytest.mark.parametrize(("stage", "extra_args"), PROMPT_STAGES)
def test_prompt_human_success(
    repository: Path, config_factory: object, stage: str, extra_args: list[str]
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app, ["prompt", stage, "--config", str(config), "--task-id", "T-1", *extra_args]
    )
    assert result.exit_code == 0, result.output
    lines = result.stdout.split("\n")
    assert lines[0].startswith("Prompt ID: ")
    assert lines[1] == f"Stage: {stage}"
    assert lines[2] == "Stored: yes"
    assert lines[3].startswith("Prompt artifact: ")
    assert lines[4].startswith("Metadata artifact: ")
    assert lines[5] == ""
    assert "# Governed Workflow Prompt" in result.stdout
    prompt_artifact = lines[3].removeprefix("Prompt artifact: ")
    assert Path(prompt_artifact).exists()


@pytest.mark.parametrize(("stage", "extra_args"), PROMPT_STAGES)
def test_prompt_json_success_schema_and_exit_code(
    repository: Path, config_factory: object, stage: str, extra_args: list[str]
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            stage,
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--output",
            "json",
            *extra_args,
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert list(payload) == [
        "metadata",
        "metadata_artifact",
        "prompt",
        "prompt_artifact",
        "schema_version",
        "stored",
    ]
    assert payload["schema_version"] == "1.1"
    assert payload["stored"] is True
    assert payload["prompt_artifact"] is not None
    assert payload["metadata_artifact"] is not None
    assert payload["metadata"]["stage"] == stage
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1


def test_prompt_no_store_writes_nothing(
    repository: Path, config_factory: object, tmp_path: Path
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            "plan-review",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--no-store",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["stored"] is False
    assert payload["prompt_artifact"] is None
    assert payload["metadata_artifact"] is None
    prompts_root = Path.home() / ".ai-workflow-engine" / "workflow-runs" / "prompts"
    assert not prompts_root.exists()


def test_prompt_allowed_path_rejected_on_non_implementation_remediation_commands(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    for stage in [
        "plan-review",
        "implementation-review",
        "governance-closeout",
        "governance-review",
        "push",
    ]:
        result = runner.invoke(
            app,
            [
                "prompt",
                stage,
                "--config",
                str(config),
                "--task-id",
                "T-1",
                "--allowed-path",
                "src/a.py",
            ],
        )
        assert result.exit_code != 0, stage
        assert "no such option" in result.output.lower()


def test_prompt_finding_rejected_on_non_remediation_commands(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    for stage, extra_args in [
        ("plan-review", []),
        ("implementation", ["--allowed-path", "src/a.py"]),
        ("implementation-review", []),
        ("governance-closeout", []),
        ("governance-review", []),
        ("push", []),
    ]:
        result = runner.invoke(
            app,
            [
                "prompt",
                stage,
                "--config",
                str(config),
                "--task-id",
                "T-1",
                *extra_args,
                "--finding",
                "Fix it",
            ],
        )
        assert result.exit_code != 0, stage
        assert "no such option" in result.output.lower()


def test_prompt_implementation_requires_at_least_one_allowed_path(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app, ["prompt", "implementation", "--config", str(config), "--task-id", "T-1"]
    )
    assert result.exit_code != 0


def test_prompt_remediation_requires_at_least_one_finding(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            "remediation",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--allowed-path",
            "src/a.py",
        ],
    )
    assert result.exit_code != 0


def test_prompt_missing_task_id_is_usage_error(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(app, ["prompt", "plan-review", "--config", str(config)])
    assert result.exit_code != 0


def test_prompt_whitespace_only_task_id_is_protected_error(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app, ["prompt", "plan-review", "--config", str(config), "--task-id", "   "]
    )
    assert result.exit_code == 2
    assert "ERROR:" in result.output


def test_prompt_task_id_whitespace_is_collapsed_and_trimmed(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            "plan-review",
            "--config",
            str(config),
            "--task-id",
            "  T-1   is\t\tit  ",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["metadata"]["task_id"] == "T-1 is it"


def test_prompt_bad_config_is_protected_error_exit_2(repository: Path) -> None:
    result = runner.invoke(
        app,
        ["prompt", "plan-review", "--config", "/nonexistent/config.yaml", "--task-id", "T-1"],
    )
    assert result.exit_code == 2
    assert result.output.startswith("ERROR:")
    assert "Traceback (most recent call last)" not in result.output


def test_prompt_bad_config_json_mode_still_writes_error_to_stderr(
    repository: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "prompt",
            "plan-review",
            "--config",
            "/nonexistent/config.yaml",
            "--task-id",
            "T-1",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert result.output.startswith("ERROR:")
    assert result.stdout == ""


def test_prompt_disallowed_allowed_path_is_protected_error(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            "implementation",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--allowed-path",
            "../escape",
        ],
    )
    assert result.exit_code == 2
    assert "ERROR:" in result.output
    prompts_root = Path.home() / ".ai-workflow-engine" / "workflow-runs" / "prompts"
    assert not prompts_root.exists()


def test_prompt_protected_error_preserves_bracketed_text_verbatim(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            "implementation",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--allowed-path",
            "../[bad]",
        ],
    )
    assert result.exit_code == 2
    assert result.output == "ERROR: Allowed path must not escape the repository: '../[bad]'\n"


def _direct_prompt_success(
    config: EngineConfig, *, stage: str, task_id: str, allowed_paths=(), remediation_findings=()
) -> PromptSuccess:
    # Mirrors cli.py's own pipeline exactly, so a byte-exact comparison against the CLI's
    # actual stdout is a genuine golden test, not a hand-pinned literal that would be
    # invalidated by every fresh commit hash the `repository` fixture happens to produce.
    context = build_prompt_context(
        config,
        stage=stage,  # type: ignore[arg-type]
        task_id=task_id,
        allowed_paths=allowed_paths,
        remediation_findings=remediation_findings,
    )
    rendered = render_prompt(context)
    return PromptSuccess(
        schema_version="1.1",
        stored=False,
        prompt_artifact=None,
        metadata_artifact=None,
        prompt=rendered.markdown,
        metadata=rendered.metadata,
    )


@pytest.mark.parametrize(("stage", "extra_args"), PROMPT_STAGES)
def test_prompt_json_output_is_byte_exact_with_direct_render(
    repository: Path, config_factory: object, stage: str, extra_args: list[str]
) -> None:
    from ai_workflow_engine.config import load_config

    config_path = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            stage,
            "--config",
            str(config_path),
            "--task-id",
            "T-1",
            "--output",
            "json",
            "--no-store",
            *extra_args,
        ],
    )
    assert result.exit_code == 0, result.output

    allowed_paths = []
    if "--allowed-path" in extra_args:
        allowed_paths = [extra_args[extra_args.index("--allowed-path") + 1]]
    remediation_findings = []
    if "--finding" in extra_args:
        remediation_findings = [extra_args[extra_args.index("--finding") + 1]]

    expected_success = _direct_prompt_success(
        load_config(config_path),
        stage=stage,
        task_id="T-1",
        allowed_paths=allowed_paths,
        remediation_findings=remediation_findings,
    )
    expected_bytes = canonical_json(expected_success.model_dump(mode="json")) + b"\n"
    assert result.stdout.encode("utf-8") == expected_bytes


@pytest.mark.parametrize(("stage", "extra_args"), PROMPT_STAGES)
def test_prompt_human_output_is_byte_exact_with_direct_render(
    repository: Path, config_factory: object, stage: str, extra_args: list[str]
) -> None:
    from ai_workflow_engine.config import load_config

    config_path = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "prompt",
            stage,
            "--config",
            str(config_path),
            "--task-id",
            "T-1",
            "--no-store",
            *extra_args,
        ],
    )
    assert result.exit_code == 0, result.output

    allowed_paths = []
    if "--allowed-path" in extra_args:
        allowed_paths = [extra_args[extra_args.index("--allowed-path") + 1]]
    remediation_findings = []
    if "--finding" in extra_args:
        remediation_findings = [extra_args[extra_args.index("--finding") + 1]]

    expected_success = _direct_prompt_success(
        load_config(config_path),
        stage=stage,
        task_id="T-1",
        allowed_paths=allowed_paths,
        remediation_findings=remediation_findings,
    )
    expected_block = "\n".join(
        [
            f"Prompt ID: {expected_success.metadata.prompt_id}",
            f"Stage: {stage}",
            "Stored: no",
            "Prompt artifact: (not stored)",
            "Metadata artifact: (not stored)",
        ]
    )
    expected_output = expected_block + "\n\n" + expected_success.prompt
    assert result.stdout == expected_output


def test_prompt_protected_error_is_not_soft_wrapped_when_long(
    repository: Path, config_factory: object
) -> None:
    # A message at or beyond Rich's default 80-column console width must still be
    # written as a single unbroken line; Rich's Console.print soft-wraps by default
    # even with markup and highlighting both disabled.
    config = config_factory(repository)  # type: ignore[operator]
    long_raw_path = "../" + ("a" * 60)
    result = runner.invoke(
        app,
        [
            "prompt",
            "implementation",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--allowed-path",
            long_raw_path,
        ],
    )
    assert result.exit_code == 2
    expected = f"ERROR: Allowed path must not escape the repository: {long_raw_path!r}\n"
    assert len(expected) > 80
    assert result.output == expected
    assert result.output.count("\n") == 1


# ---- agent run + state --agent-run binding (T-305) -----------------------------


def _agent_config_with_stub(repository: Path, config_factory: object, stub: Path) -> Path:
    import yaml

    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["agents"] = [
        {
            "name": "rev",
            "executable": str(stub),
            "args": [],
            "mode": "read-only",
            "stages": ["plan-review"],
            "timeout_seconds": 30,
        }
    ]
    path.write_text(yaml.safe_dump(raw))
    return path


def _write_report_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "revstub"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "data = sys.stdin.read()\n"
        "pid = data.split('Prompt ID: \"')[1].split('\"')[0]\n"
        "print(json.dumps({\n"
        '  "schema_version": "1.0", "task_id": "T-1", "stage": "plan-review",\n'
        '  "prompt_id": pid, "verdict": "APPROVED", "summary": "ok", "findings": [],\n'
        '  "changed_paths": [], "verification_commands_run": [], "blockers": []}))\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def test_agent_run_and_state_binding(
    repository: Path, config_factory: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Neutralize the heavy conda-pytest verification with a trivial always-pass command.
    import ai_workflow_engine.agents.runner as runner_module

    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["true"]])

    stub = _write_report_stub(tmp_path)
    config = _agent_config_with_stub(repository, config_factory, stub)

    # Render + store the prompt, capture its id.
    rendered = runner.invoke(
        app,
        ["prompt", "plan-review", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    )
    prompt_id = json.loads(rendered.stdout)["metadata"]["prompt_id"]

    # Run the agent; verification PASS, artifact stored.
    run = runner.invoke(
        app,
        [
            "agent",
            "run",
            "--config",
            str(config),
            "--agent",
            "rev",
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--prompt-id",
            prompt_id,
            "--output",
            "json",
        ],
    )
    assert run.exit_code == 0, run.stdout + run.stderr
    run_payload = json.loads(run.stdout)
    assert run_payload["status"] == "PASS"
    run_id = run_payload["run_id"]
    assert run_id is not None

    # Record the plan-review verdict citing that run as evidence.
    record = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--verdict",
            "APPROVED",
            "--agent-run",
            run_id,
            "--output",
            "json",
        ],
    )
    assert record.exit_code == 0, record.stdout
    assert json.loads(record.stdout)["status"] == "PASS"


def test_state_record_rejects_mismatched_verdict_evidence(
    repository: Path, config_factory: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_workflow_engine.agents.runner as runner_module

    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["true"]])
    stub = _write_report_stub(tmp_path)
    config = _agent_config_with_stub(repository, config_factory, stub)
    rendered = runner.invoke(
        app,
        ["prompt", "plan-review", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    )
    prompt_id = json.loads(rendered.stdout)["metadata"]["prompt_id"]
    run = runner.invoke(
        app,
        [
            "agent",
            "run",
            "--config",
            str(config),
            "--agent",
            "rev",
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--prompt-id",
            prompt_id,
            "--output",
            "json",
        ],
    )
    run_id = json.loads(run.stdout)["run_id"]
    # The run's verdict is APPROVED; recording REJECTED with it as evidence must fail.
    record = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--verdict",
            "REJECTED",
            "--agent-run",
            run_id,
            "--output",
            "json",
        ],
    )
    assert record.exit_code == 1
    assert json.loads(record.stdout)["finding"]["code"] == "verdict_evidence_mismatch"


def test_state_record_rejects_unknown_agent_run(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--verdict",
            "APPROVED",
            "--agent-run",
            "0" * 16,
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["finding"]["code"] == "agent_run_unavailable"


def test_agent_run_verification_fail_stores_artifact_and_exits_one(
    repository: Path, config_factory: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai_workflow_engine.agents.runner as runner_module

    # A verification command that always fails -> verification FAIL, but the artifact is stored.
    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["false"]])
    stub = _write_report_stub(tmp_path)
    config = _agent_config_with_stub(repository, config_factory, stub)
    rendered = runner.invoke(
        app,
        ["prompt", "plan-review", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    )
    prompt_id = json.loads(rendered.stdout)["metadata"]["prompt_id"]
    run = runner.invoke(
        app,
        [
            "agent",
            "run",
            "--config",
            str(config),
            "--agent",
            "rev",
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--prompt-id",
            prompt_id,
            "--output",
            "json",
        ],
    )
    assert run.exit_code == 1
    payload = json.loads(run.stdout)
    assert payload["status"] == "FAIL"
    # Artifact still stored despite the FAIL, so the failure is auditable.
    assert payload["run_id"] is not None
    assert payload["record_artifact"] is not None
    assert Path(payload["record_artifact"]).exists()


# ---- workflowctl commit (T-402) ------------------------------------------------


def _commit_approval_file(tmp_path: Path, repository: Path, **overrides: object) -> Path:
    import subprocess

    import yaml

    head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    data: dict[str, object] = {
        "kind": "commit",
        "task_id": "T-1",
        "branch": "main",
        "head": head,
        "allowed_paths": ["newfile.txt"],
        "message": "add newfile",
        "approved_by": "human",
    }
    data.update(overrides)
    path = tmp_path / "approval.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_commit_requires_approval_option(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(app, ["commit", "--config", str(config)])
    assert result.exit_code == 2  # missing required --approval


def test_commit_happy_path_cli(repository: Path, config_factory: object, tmp_path: Path) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    (repository / "newfile.txt").write_text("hi\n", encoding="utf-8")
    approval = _commit_approval_file(tmp_path, repository)
    result = runner.invoke(
        app,
        ["commit", "--config", str(config), "--approval", str(approval), "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["check_name"] == "commit"


def test_commit_refusal_exits_one(repository: Path, config_factory: object, tmp_path: Path) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    (repository / "newfile.txt").write_text("hi\n", encoding="utf-8")
    (repository / "sneaky.txt").write_text("x\n", encoding="utf-8")
    approval = _commit_approval_file(tmp_path, repository)
    result = runner.invoke(
        app,
        ["commit", "--config", str(config), "--approval", str(approval), "--output", "json"],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "FAIL"


def test_commit_bad_approval_exits_two(
    repository: Path, config_factory: object, tmp_path: Path
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    bad = tmp_path / "bad.yaml"
    bad.write_text("kind: push\n", encoding="utf-8")  # wrong kind for `commit`
    result = runner.invoke(app, ["commit", "--config", str(config), "--approval", str(bad)])
    assert result.exit_code == 2
    assert "ERROR:" in result.output


# ---- workflowctl push / apply-patch (T-403) ------------------------------------


def test_push_requires_approval_option(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(app, ["push", "--config", str(config)])
    assert result.exit_code == 2  # missing required --approval


def test_push_happy_path_cli(
    repository_with_remote: Path, config_factory: object, tmp_path: Path
) -> None:
    import subprocess

    import yaml

    repo = repository_with_remote
    config = config_factory(repo)  # type: ignore[operator]
    (repo / "extra.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "extra.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "c"], check=True, capture_output=True)

    def rev(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    approval = tmp_path / "push.yaml"
    approval.write_text(
        yaml.safe_dump(
            {
                "kind": "push",
                "task_id": "T-1",
                "branch": "main",
                "head": rev("rev-parse", "HEAD"),
                "upstream": rev("rev-parse", "--abbrev-ref", "@{upstream}"),
                "approved_by": "human",
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["push", "--config", str(config), "--approval", str(approval), "--output", "json"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"
    assert rev("rev-parse", "origin/main") == rev("rev-parse", "HEAD")


def test_apply_patch_unknown_stage_exits_two(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "apply-patch",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "not-a-stage",
            "--run-id",
            "0" * 16,
        ],
    )
    assert result.exit_code == 2
    assert "ERROR:" in result.output


def test_apply_patch_missing_run_exits_one(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "apply-patch",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "implementation",
            "--run-id",
            "0" * 16,
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["findings"][0]["code"] == "run_unavailable"


def test_state_record_unknown_stage_exits_two(repository: Path, config_factory: object) -> None:
    """`state record` refuses an unsupported stage instead of recording it."""
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "state",
            "record",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--stage",
            "not-a-stage",
            "--completed",
        ],
    )
    assert result.exit_code == 2
    assert "Unknown stage: 'not-a-stage'" in result.output


def test_agent_run_unknown_stage_exits_two(repository: Path, config_factory: object) -> None:
    """`agent run` refuses an unsupported stage before dispatching any agent."""
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "agent",
            "run",
            "--config",
            str(config),
            "--agent",
            "reviewer",
            "--task-id",
            "T-1",
            "--stage",
            "not-a-stage",
            "--prompt-id",
            "0" * 16,
        ],
    )
    assert result.exit_code == 2
    assert "Unknown stage: 'not-a-stage'" in result.output
