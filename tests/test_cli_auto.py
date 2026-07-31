"""AUTO-009: the additive, read-only `workflowctl auto` sub-application.

Covers the four commands' registration, human and JSON output under both contract versions, exit
codes, stdout/stderr separation, the structural absence of every write-capable verb, and the
compatibility guarantee that registering the sub-app changes nothing about the commands that
already existed.

The out-of-process helper (`_run_cli`) is what proves the stdout/stderr and exit-code claims:
`CliRunner` merges streams and swallows `SystemExit`, so a byte-discipline assertion made through
it would be about the runner, not about `workflowctl`.
"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from agentos_workflow.cli_auto import OutputFormat as AutoOutputFormat
from agentos_workflow.cli_auto import auto_app
from agentos_workflow.orchestrator.state_store import (
    CommandExecutionRecord,
    StateStore,
    StateTransitionRecord,
)
from agentos_workflow.skills.reporting import generate_qa_report, generate_stage_report
from ai_workflow_engine.cli import OutputFormat as EngineOutputFormat
from ai_workflow_engine.cli import app

runner = CliRunner()

AUTO_COMMANDS = ("status", "list", "audit", "report")

# The verbs AUTO-009 is forbidden to expose. Asserted against the real registered command names,
# so a future stage cannot add one of them to this group without this failing first.
FORBIDDEN_COMMANDS = (
    "start",
    "authorize",
    "approve",
    "reject",
    "resume",
    "cancel",
    "prepare",
    "review",
    "implement",
    "commit",
    "push",
    "merge",
)


def _config_dict(repository: Path, state: Path, audit: Path) -> dict[str, object]:
    return {
        "repository_path": str(repository),
        "repository_identity": "github.com/org/demo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/stage-prompts",
        "stage_branch_naming": "feature/{stage_id}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests"],
        "merge_method": "squash",
        "claude_cli_executable": "/usr/local/bin/claude",
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": "/usr/local/bin/codex",
        "codex_cli_timeout_seconds": 1800,
        "allowed_environment_variables": ["PATH"],
        "allowed_changed_paths": ["docs/**"],
        "forbidden_changed_paths": ["src/**"],
        "repair_attempt_limit": 3,
        "state_directory": str(state),
        "audit_directory": str(audit),
    }


@pytest.fixture
def target_repo(tmp_path: Path) -> Path:
    """A target repository with a valid AgentOS configuration and one persisted workflow."""
    repository = tmp_path / "repo"
    (repository / ".agentos").mkdir(parents=True)
    state = tmp_path / "state"
    audit = tmp_path / "audit"
    (repository / ".agentos" / "workflow.yaml").write_text(
        yaml.safe_dump(_config_dict(repository, state, audit)), encoding="utf-8"
    )
    store = StateStore(state_directory=state, audit_directory=audit)
    base = datetime(2026, 7, 31, 9, 0, tzinfo=UTC)
    for index, (from_state, to_state, actor) in enumerate(
        [
            ("CREATED", "AUTHORIZED", "human"),
            ("AUTHORIZED", "PRECONDITIONS_CHECKED", "orchestrator"),
        ]
    ):
        store.record_transition(
            StateTransitionRecord(
                workflow_id="wf-1",
                target_repository="github.com/org/demo",
                repository_path=str(repository),
                stage_id="STAGE-1",
                from_state=from_state,
                to_state=to_state,
                timestamp=(base + timedelta(minutes=index)).isoformat(),
                actor=actor,
                gate_evidence_ref="evidence/authorization.json" if index == 0 else None,
            )
        )
    store.record_command_execution(
        "wf-1",
        CommandExecutionRecord(
            normalized_command_identity="run_tests(<argv>)",
            start_time=base.isoformat(),
            completion_time=(base + timedelta(minutes=1)).isoformat(),
            exit_code=0,
            timeout_status=False,
            stdout_ref="wf-1/output/op-1/stdout.txt",
            stderr_ref="wf-1/output/op-1/stderr.txt",
        ),
    )
    assert generate_stage_report(
        audit_root=audit, workflow_id="wf-1", results={"verdict": "PASS"}
    ).ok
    assert generate_qa_report(
        audit_root=audit, workflow_id="wf-1", results={"verdict": "PASS"}, sequence=2
    ).ok
    return repository


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke the real CLI out of process, so stdout, stderr, and the exit code are the real ones.

    `CliRunner` merges the two streams and swallows `SystemExit`, so it cannot witness either.
    """
    return subprocess.run(
        [sys.executable, "-m", "ai_workflow_engine", *args],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        check=False,
    )


# ------------------------------------------------------------------------------------------
# Registration and scope
# ------------------------------------------------------------------------------------------


class TestRegistration:
    def test_auto_group_is_registered_on_the_root_app(self) -> None:
        assert "auto" in {group.name for group in app.registered_groups}

    @pytest.mark.parametrize("command", AUTO_COMMANDS)
    def test_command_is_registered(self, command: str) -> None:
        assert command in {registered.name for registered in auto_app.registered_commands}

    def test_exactly_the_four_approved_commands_exist(self) -> None:
        assert {registered.name for registered in auto_app.registered_commands} == set(
            AUTO_COMMANDS
        )

    def test_no_sub_groups_are_registered(self) -> None:
        """Nothing is hidden one level down where the command-name assertion would not see it."""
        assert auto_app.registered_groups == []

    @pytest.mark.parametrize("forbidden", FORBIDDEN_COMMANDS)
    def test_forbidden_command_is_absent(self, forbidden: str) -> None:
        assert forbidden not in {registered.name for registered in auto_app.registered_commands}

    @pytest.mark.parametrize("forbidden", FORBIDDEN_COMMANDS)
    def test_forbidden_command_is_rejected_at_the_cli(
        self, forbidden: str, target_repo: Path
    ) -> None:
        result = _run_cli(["auto", forbidden, "--target-repo", str(target_repo)])
        assert result.returncode != 0
        assert "No such command" in result.stderr or "Usage" in result.stderr

    def test_help_lists_only_the_four_commands(self) -> None:
        result = _run_cli(["auto", "--help"])
        assert result.returncode == 0
        for command in AUTO_COMMANDS:
            assert command in result.stdout
        for forbidden in FORBIDDEN_COMMANDS:
            assert f" {forbidden} " not in result.stdout

    def test_output_format_mirrors_the_engine_enum(self) -> None:
        """The `cast` in `cli_auto._protected` is only honest while these two stay identical."""
        assert {member.name: member.value for member in AutoOutputFormat} == {
            member.name: member.value for member in EngineOutputFormat
        }


# ------------------------------------------------------------------------------------------
# Human output
# ------------------------------------------------------------------------------------------


class TestHumanOutput:
    def test_status_repository_context(self, target_repo: Path) -> None:
        result = _run_cli(["auto", "status", "--target-repo", str(target_repo)])
        assert result.returncode == 0
        assert "Repository: github.com/org/demo" in result.stdout
        assert "Persisted workflows: 1" in result.stdout
        assert result.stderr == ""

    def test_status_one_workflow(self, target_repo: Path) -> None:
        result = _run_cli(
            ["auto", "status", "--target-repo", str(target_repo), "--workflow-id", "wf-1"]
        )
        assert result.returncode == 0
        assert "Workflow: wf-1" in result.stdout
        assert "State: PRECONDITIONS_CHECKED" in result.stdout

    def test_list(self, target_repo: Path) -> None:
        result = _run_cli(["auto", "list", "--target-repo", str(target_repo)])
        assert result.returncode == 0
        assert "wf-1" in result.stdout
        assert "PRECONDITIONS_CHECKED" in result.stdout

    def test_audit_preserves_order_and_evidence(self, target_repo: Path) -> None:
        result = _run_cli(
            ["auto", "audit", "--target-repo", str(target_repo), "--workflow-id", "wf-1"]
        )
        assert result.returncode == 0
        authorized = result.stdout.index("CREATED -> AUTHORIZED")
        checked = result.stdout.index("AUTHORIZED -> PRECONDITIONS_CHECKED")
        assert authorized < checked
        assert "evidence/authorization.json" in result.stdout
        assert "wf-1/output/op-1/stdout.txt" in result.stdout

    def test_report(self, target_repo: Path) -> None:
        result = _run_cli(
            ["auto", "report", "--target-repo", str(target_repo), "--workflow-id", "wf-1"]
        )
        assert result.returncode == 0
        assert "stage" in result.stdout
        assert "qa.2" in result.stdout


# ------------------------------------------------------------------------------------------
# JSON output
# ------------------------------------------------------------------------------------------


class TestJsonOutput:
    @pytest.mark.parametrize(
        ("command", "extra"),
        [
            ("status", []),
            ("status", ["--workflow-id", "wf-1"]),
            ("list", []),
            ("audit", ["--workflow-id", "wf-1"]),
            ("report", ["--workflow-id", "wf-1"]),
        ],
    )
    def test_contract_v1_is_a_bare_json_object_on_stdout(
        self, target_repo: Path, command: str, extra: list[str]
    ) -> None:
        result = _run_cli(
            ["auto", command, "--target-repo", str(target_repo), *extra, "--output", "json"]
        )
        assert result.returncode == 0
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict)
        assert "contract_version" not in payload  # v1 is unenveloped, exactly as before

    @pytest.mark.parametrize(
        ("command", "extra", "expected"),
        [
            ("status", [], "auto-status"),
            ("list", [], "auto-list"),
            ("audit", ["--workflow-id", "wf-1"], "auto-audit"),
            ("report", ["--workflow-id", "wf-1"], "auto-report"),
        ],
    )
    def test_contract_v2_uses_the_stable_success_envelope(
        self, target_repo: Path, command: str, extra: list[str], expected: str
    ) -> None:
        result = _run_cli(
            [
                "--contract-version",
                "2",
                "auto",
                command,
                "--target-repo",
                str(target_repo),
                *extra,
                "--output",
                "json",
            ]
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["contract_version"] == "2.0.0"
        assert payload["command"] == expected
        assert payload["ok"] is True
        assert payload["error"] is None
        assert isinstance(payload["data"], dict)

    def test_json_output_is_exact_bytes_under_force_color(self, target_repo: Path) -> None:
        """Rich is bypassed for machine output, so colour forcing cannot corrupt the contract."""
        env = dict(os.environ, FORCE_COLOR="3")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ai_workflow_engine",
                "auto",
                "list",
                "--target-repo",
                str(target_repo),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert result.returncode == 0
        assert "\x1b[" not in result.stdout
        json.loads(result.stdout)

    def test_json_output_is_deterministic(self, target_repo: Path) -> None:
        args = [
            "auto",
            "audit",
            "--target-repo",
            str(target_repo),
            "--workflow-id",
            "wf-1",
            "--output",
            "json",
        ]
        assert _run_cli(args).stdout == _run_cli(args).stdout


# ------------------------------------------------------------------------------------------
# Errors, exit codes, and stream separation
# ------------------------------------------------------------------------------------------


class TestErrorContract:
    def test_missing_workflow_uses_stderr_and_exit_2_under_v1(self, target_repo: Path) -> None:
        result = _run_cli(
            ["auto", "status", "--target-repo", str(target_repo), "--workflow-id", "absent"]
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr.startswith("ERROR: ")

    def test_missing_workflow_uses_the_v2_error_envelope_and_exit_1(
        self, target_repo: Path
    ) -> None:
        result = _run_cli(
            [
                "--contract-version",
                "2",
                "auto",
                "audit",
                "--target-repo",
                str(target_repo),
                "--workflow-id",
                "absent",
                "--output",
                "json",
            ]
        )
        assert result.returncode == 1
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["data"] is None
        assert payload["error"]["code"] == "WorkflowNotFoundError"
        assert payload["error"]["retryable"] is False

    def test_missing_configuration_is_reported_through_the_contract(self, tmp_path: Path) -> None:
        result = _run_cli(["auto", "list", "--target-repo", str(tmp_path / "nowhere")])
        assert result.returncode == 2
        assert result.stdout == ""
        assert "No workflow configuration found" in result.stderr

    def test_missing_report_kind_exits_2_under_v1(self, target_repo: Path) -> None:
        result = _run_cli(
            [
                "auto",
                "report",
                "--target-repo",
                str(target_repo),
                "--workflow-id",
                "wf-1",
                "--report-kind",
                "closeout",
            ]
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert "No persisted 'closeout' report" in result.stderr

    def test_debug_adds_a_traceback_on_stderr_without_touching_stdout(
        self, target_repo: Path
    ) -> None:
        result = _run_cli(
            ["--debug", "auto", "status", "--target-repo", str(target_repo), "--workflow-id", "x"]
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert "Traceback" in result.stderr

    def test_unsafe_workflow_id_is_refused(self, target_repo: Path) -> None:
        result = _run_cli(
            ["auto", "status", "--target-repo", str(target_repo), "--workflow-id", "../escape"]
        )
        assert result.returncode == 2
        assert result.stdout == ""


# ------------------------------------------------------------------------------------------
# Compatibility with the pre-existing CLI
# ------------------------------------------------------------------------------------------


class TestCompatibility:
    def test_verify_still_passes_with_the_sub_app_registered(
        self, repository: Path, config_factory: object
    ) -> None:
        config = config_factory(repository)  # type: ignore[operator]
        result = runner.invoke(app, ["verify", "--config", str(config), "--output", "json"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)["status"] == "PASS"

    def test_version_output_is_unchanged(self) -> None:
        result = _run_cli(["version"])
        assert result.returncode == 0
        assert result.stdout == "1.0.0\n"
        assert result.stderr == ""

    def test_existing_top_level_commands_are_all_still_registered(self) -> None:
        # A bare `@app.command()` leaves `name` as None and Typer derives it from the function.
        names = {
            registered.name
            or (registered.callback.__name__.replace("_", "-") if registered.callback else "")
            for registered in app.registered_commands
        }
        assert {
            "version",
            "inspect",
            "check-git",
            "check-task-state",
            "check-governance",
            "check-registries",
            "check-handover",
            "verify",
            "commit",
            "push",
            "apply-patch",
        } <= names

    def test_existing_sub_apps_are_all_still_registered(self) -> None:
        assert {"prompt", "state", "agent", "migrate", "auto"} <= {
            group.name for group in app.registered_groups
        }

    def test_inspect_json_shape_is_unchanged(
        self, repository: Path, config_factory: object
    ) -> None:
        config = config_factory(repository)  # type: ignore[operator]
        result = runner.invoke(app, ["inspect", "--config", str(config), "--output", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "1.0"
        assert set(payload) == {
            "schema_version",
            "project_id",
            "repository",
            "git",
            "workflow",
            "protected_path_violations",
        }

    def test_root_help_still_documents_every_pre_existing_command(self) -> None:
        result = _run_cli(["--help"])
        assert result.returncode == 0
        for command in ("verify", "inspect", "commit", "push", "prompt", "state", "migrate"):
            assert command in result.stdout
        assert "auto" in result.stdout
