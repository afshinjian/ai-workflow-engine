import json
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
    assert result.stdout.strip() == "0.1.0"


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
    assert payload["schema_version"] == "1.0"
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
        schema_version="1.0",
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
