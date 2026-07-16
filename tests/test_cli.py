import json
from pathlib import Path

from typer.testing import CliRunner

from ai_workflow_engine.cli import app

runner = CliRunner()


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
