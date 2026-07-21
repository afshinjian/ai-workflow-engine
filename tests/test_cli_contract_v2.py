"""CLI contract v2 envelope tests: version dispatch, compatibility, and stdout purity.

These exercise `workflowctl`'s `--contract-version` option end to end (positive,
negative, compatibility, and stdout-purity), against isolated throwaway
repositories/configs from `conftest.py` — never the real project's governance
files.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ai_workflow_engine.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_prompt_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every command that stores prompts/agent-run artifacts writes under `$HOME` by
    default; isolate it per test so nothing here ever touches the real user's
    `~/.ai-workflow-engine/`.
    """
    home = tmp_path / "prompt-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_workflow_engine", *args],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        check=False,
    )


def _write_agent_report_stub(tmp_path: Path) -> Path:
    """A trivial fake agent binary that reports a fixed, always-approving verdict."""
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


def _config_with_stub_agent(repository: Path, config_factory: object, stub: Path) -> Path:
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


# --- positive: v1 remains available and byte-identical -----------------------------------


def test_v1_is_the_default_and_matches_the_pre_contract_shape(
    repository: Path, config_factory: object
) -> None:
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


def test_explicit_v1_alias_matches_the_default(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    default_result = runner.invoke(
        app, ["check-handover", "--config", str(config), "--output", "json"]
    )
    explicit_result = runner.invoke(
        app,
        ["--contract-version", "1", "check-handover", "--config", str(config), "--output", "json"],
    )
    default_payload = json.loads(default_result.stdout)
    explicit_payload = json.loads(explicit_result.stdout)
    del default_payload["timestamp"], explicit_payload["timestamp"]
    assert explicit_payload == default_payload
    assert explicit_result.exit_code == default_result.exit_code == 0


def test_v1_full_semver_alias_is_accepted(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "1.0.0",
            "check-handover",
            "--config",
            str(config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert list(json.loads(result.stdout)) == [
        "check_name",
        "status",
        "summary",
        "findings",
        "evidence",
        "affected_paths",
        "remediation_hint",
        "timestamp",
    ]


# --- positive: v2 envelope dispatches correctly --------------------------------------------


def test_v2_envelope_shape_for_a_passing_check(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        ["--contract-version", "2", "check-handover", "--config", str(config), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert list(payload) == ["contract_version", "command", "ok", "data", "error", "warnings"]
    assert payload["contract_version"] == "2.0.0"
    assert payload["command"] == "handover"
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["warnings"] == []
    assert payload["data"]["status"] == "PASS"
    assert payload["data"]["check_name"] == "handover"


def test_v2_full_semver_alias_is_accepted(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2.0.0",
            "check-handover",
            "--config",
            str(config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["contract_version"] == "2.0.0"


def test_v2_envelope_shape_for_a_failing_check(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "check-git",
            "--config",
            str(config),
            "--expected-branch",
            "definitely-wrong",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["contract_version"] == "2.0.0"
    assert payload["command"] == "git"
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "CHECK_FAIL"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"]["findings"][0]["code"] == "branch_mismatch"


def test_v2_envelope_for_verify_command(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app, ["--contract-version", "2", "verify", "--config", str(config), "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["contract_version"] == "2.0.0"
    assert payload["command"] == "verify"
    assert payload["ok"] is True
    assert payload["data"]["status"] == "PASS"
    assert len(payload["data"]["checks"]) == 4


def test_v2_envelope_for_verify_command_failure(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    (repository / "handover" / "PROJECT_HANDOVER.md").write_bytes(b"tampered\n")
    result = runner.invoke(
        app, ["--contract-version", "2", "verify", "--config", str(config), "--output", "json"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "CHECK_FAIL"
    assert "findings" in payload["error"]["details"]


# --- compatibility: v1 and v2 coexist for the exact same underlying state ------------------


def test_v1_and_v2_coexist_for_identical_underlying_state(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    v1 = json.loads(
        runner.invoke(app, ["check-handover", "--config", str(config), "--output", "json"]).stdout
    )
    v2 = json.loads(
        runner.invoke(
            app,
            [
                "--contract-version",
                "2",
                "check-handover",
                "--config",
                str(config),
                "--output",
                "json",
            ],
        ).stdout
    )
    assert v2["data"]["evidence"] == v1["evidence"]
    assert v2["data"]["status"] == v1["status"]
    assert v2["ok"] == (v1["status"] == "PASS")


# --- negative: unknown/unsupported schema versions fail closed ----------------------------


def test_unknown_contract_version_fails_closed_with_no_stdout(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "9.9.9",
            "check-handover",
            "--config",
            str(config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert result.stdout == ""


def test_unregistered_but_well_formed_version_fails_closed(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "3.0.0",
            "check-handover",
            "--config",
            str(config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert result.stdout == ""


def test_nonsense_contract_version_fails_closed(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "not-a-version",
            "check-handover",
            "--config",
            str(config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert result.stdout == ""


# --- stdout purity: exactly one JSON document, no ANSI/control contamination ---------------


def test_v2_output_is_exactly_one_json_document_and_uncolored(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    env = dict(os.environ)
    env["FORCE_COLOR"] = "3"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_workflow_engine",
            "--contract-version",
            "2",
            "verify",
            "--config",
            str(config),
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stdout
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(result.stdout.strip())
    assert end == len(result.stdout.strip()), "more than one JSON document on stdout"
    assert parsed["contract_version"] == "2.0.0"


def test_bad_contract_version_emits_no_json_at_all_on_stdout(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = _run_cli(
        [
            "--contract-version",
            "nope",
            "verify",
            "--config",
            str(config),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "ERROR" in result.stderr


def test_nonsense_contract_version_still_uses_stderr_not_v2_envelope(
    repository: Path, config_factory: object
) -> None:
    # Documents the deliberate exception (see cli.py's callback comment): an
    # unresolvable --contract-version can never select v2's envelope shape for its
    # own failure, because no contract has been chosen yet. It always uses the
    # v1/human fail-closed shape (stderr, exit 2, zero stdout), never a v2-looking
    # JSON error on stdout, regardless of --output.
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "not-a-version",
            "verify",
            "--config",
            str(config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert result.stdout == ""


# --- Finding A: every existing JSON-producing command honors --contract-version -----------


def test_inspect_v2_success(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app, ["--contract-version", "2", "inspect", "--config", str(config), "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert list(payload) == ["contract_version", "command", "ok", "data", "error", "warnings"]
    assert payload["command"] == "inspect"
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["project_id"] == "test-project"
    assert payload["data"]["git"]["branch"] == "main"


def test_inspect_v1_is_byte_compatible(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    default_result = runner.invoke(app, ["inspect", "--config", str(config), "--output", "json"])
    explicit_v1_result = runner.invoke(
        app, ["--contract-version", "1", "inspect", "--config", str(config), "--output", "json"]
    )
    assert explicit_v1_result.stdout == default_result.stdout
    payload = json.loads(default_result.stdout)
    # Unenveloped legacy shape: no contract_version/ok/data/error/warnings wrapper.
    # json.dumps(..., sort_keys=True) means the parsed key order is alphabetical.
    assert list(payload) == [
        "git",
        "project_id",
        "protected_path_violations",
        "repository",
        "schema_version",
        "workflow",
    ]


def test_prompt_v2_success_with_no_store(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
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
    assert list(payload) == ["contract_version", "command", "ok", "data", "error", "warnings"]
    assert payload["command"] == "plan-review"
    assert payload["ok"] is True
    assert payload["data"]["stored"] is False
    assert payload["data"]["prompt_artifact"] is None
    assert "Prompt ID" in payload["data"]["prompt"]


def test_prompt_v1_is_byte_compatible(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    args = [
        "prompt",
        "plan-review",
        "--config",
        str(config),
        "--task-id",
        "T-1",
        "--no-store",
        "--output",
        "json",
    ]
    default_result = runner.invoke(app, args)
    explicit_v1_result = runner.invoke(app, ["--contract-version", "1", *args])
    # Both renders are canonical-JSON of the same content except prompt_id/timestamps
    # embedded in the rendered prompt text are stable given identical inputs, so the
    # two invocations should be byte-identical.
    assert explicit_v1_result.stdout == default_result.stdout
    payload = json.loads(default_result.stdout)
    # canonical_json sorts keys, so the parsed order is alphabetical.
    assert list(payload) == [
        "metadata",
        "metadata_artifact",
        "prompt",
        "prompt_artifact",
        "schema_version",
        "stored",
    ]


def test_state_show_and_next_v2_isolated(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]

    next_result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "state",
            "next",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--output",
            "json",
        ],
    )
    assert next_result.exit_code == 0
    next_payload = json.loads(next_result.stdout)
    assert next_payload["command"] == "next"
    assert next_payload["ok"] is True
    assert next_payload["data"]["next_stage"] == "plan-review"

    record_result = runner.invoke(
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
    assert record_result.exit_code == 0

    show_result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "state",
            "show",
            "--config",
            str(config),
            "--task-id",
            "T-1",
            "--output",
            "json",
        ],
    )
    assert show_result.exit_code == 0
    show_payload = json.loads(show_result.stdout)
    assert show_payload["command"] == "show"
    assert show_payload["ok"] is True
    assert len(show_payload["data"]["events"]) == 1
    assert show_payload["data"]["next_stage"] == "implementation"


def test_state_record_v2_domain_failure_envelope(repository: Path, config_factory: object) -> None:
    # A transition-table violation (WorkflowStateError), caught inside build() and
    # returned as a {"status": "FAIL", ...} dict -- not an exception that reaches
    # _protected -- so this exercises _contract_v2_for_status_payload's FAIL branch.
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
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
    assert payload["command"] == "record"
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "transition_violation"


def test_state_v1_is_byte_compatible(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    args = ["state", "next", "--config", str(config), "--task-id", "T-1", "--output", "json"]
    default_result = runner.invoke(app, args)
    explicit_v1_result = runner.invoke(app, ["--contract-version", "1", *args])
    assert explicit_v1_result.stdout == default_result.stdout
    payload = json.loads(default_result.stdout)
    # canonical_json sorts keys, so the parsed order is alphabetical.
    assert list(payload) == ["command", "next_stage", "status"]


def test_agent_run_v2_isolated(
    repository: Path,
    config_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_workflow_engine.agents.runner as runner_module

    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["true"]])
    stub = _write_agent_report_stub(tmp_path)
    config = _config_with_stub_agent(repository, config_factory, stub)

    rendered = runner.invoke(
        app,
        ["prompt", "plan-review", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    )
    prompt_id = json.loads(rendered.stdout)["metadata"]["prompt_id"]

    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
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
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert list(payload) == ["contract_version", "command", "ok", "data", "error", "warnings"]
    assert payload["command"] == "agent-run"
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["run_id"] is not None
    assert payload["data"]["stage"] == "plan-review"
    assert payload["data"]["verification"]["status"] == "PASS"


def test_agent_run_v1_is_byte_compatible(
    repository: Path,
    config_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_workflow_engine.agents.runner as runner_module

    monkeypatch.setattr(runner_module, "verification_argv", lambda env: [["true"]])
    stub = _write_agent_report_stub(tmp_path)
    config = _config_with_stub_agent(repository, config_factory, stub)

    rendered = runner.invoke(
        app,
        ["prompt", "plan-review", "--config", str(config), "--task-id", "T-1", "--output", "json"],
    )
    prompt_id = json.loads(rendered.stdout)["metadata"]["prompt_id"]

    args = [
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
        "--no-store",
        "--output",
        "json",
    ]
    default_result = runner.invoke(app, args)
    explicit_v1_result = runner.invoke(app, ["--contract-version", "1", *args])
    default_payload = json.loads(default_result.stdout)
    explicit_payload = json.loads(explicit_v1_result.stdout)
    # Each invocation runs a fresh agent/verification pass, so the embedded
    # verification timestamp legitimately differs between the two calls; compare
    # everything else byte-for-byte (via equality of the parsed structures).
    del default_payload["verification"]["timestamp"], explicit_payload["verification"]["timestamp"]
    assert explicit_payload == default_payload
    # canonical_json sorts keys, so the parsed order is alphabetical.
    assert list(default_payload) == [
        "command",
        "patch_artifact",
        "record_artifact",
        "run_id",
        "stage",
        "status",
        "verification",
    ]


# --- one writable-gate refusal in v2, without ever performing the write -------------------


def test_commit_v2_refusal_performs_no_write(repository: Path, config_factory: object) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    head_before = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    approval = {
        "kind": "commit",
        "task_id": "T-1",
        "branch": "main",
        "head": "f" * 40,  # well-formed but wrong: guarantees a refusal, not a write.
        "allowed_paths": ["docs/PROJECT_STATE.md"],
        "message": "test",
        "approved_by": "tester@example.invalid",
    }
    approval_path = repository.parent / "commit-approval.yaml"
    approval_path.write_text(yaml.safe_dump(approval))

    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "commit",
            "--config",
            str(config),
            "--approval",
            str(approval_path),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["command"] == "commit"
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["details"]["findings"][0]["code"] == "head_mismatch"

    head_after = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head_after == head_before, "commit refusal must never advance HEAD"


# --- Finding B: operational/configuration failures emit the v2 error envelope --------------


def test_v2_configuration_failure_error_envelope(tmp_path: Path) -> None:
    missing_config = tmp_path / "does-not-exist.yaml"
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "check-handover",
            "--config",
            str(missing_config),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert list(payload) == ["contract_version", "command", "ok", "data", "error", "warnings"]
    assert payload["command"] == "handover"
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "InvalidConfigurationError"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {}
    assert "\x1b" not in result.stdout


def test_v1_configuration_failure_is_byte_compatible_stderr_only(tmp_path: Path) -> None:
    missing_config = tmp_path / "does-not-exist.yaml"
    default_result = runner.invoke(
        app, ["check-handover", "--config", str(missing_config), "--output", "json"]
    )
    explicit_v1_result = runner.invoke(
        app,
        [
            "--contract-version",
            "1",
            "check-handover",
            "--config",
            str(missing_config),
            "--output",
            "json",
        ],
    )
    assert default_result.exit_code == explicit_v1_result.exit_code == 2
    assert default_result.stdout == explicit_v1_result.stdout == ""


def test_v2_prompt_operational_failure_error_envelope(tmp_path: Path) -> None:
    missing_config = tmp_path / "does-not-exist.yaml"
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "prompt",
            "plan-review",
            "--config",
            str(missing_config),
            "--task-id",
            "T-1",
            "--no-store",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["command"] == "plan-review"
    assert payload["ok"] is False
    assert payload["error"]["code"] == "InvalidConfigurationError"


def test_v2_agent_run_bad_agent_name_error_envelope(
    repository: Path, config_factory: object
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    result = runner.invoke(
        app,
        [
            "--contract-version",
            "2",
            "agent",
            "run",
            "--config",
            str(config),
            "--agent",
            "does-not-exist",
            "--task-id",
            "T-1",
            "--stage",
            "plan-review",
            "--prompt-id",
            "deadbeefdeadbeef",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["command"] == "agent-run"
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BadParameter"


# --- exact single-document stdout for every tested command family, under FORCE_COLOR ------


@pytest.mark.parametrize(
    "extra_args",
    [
        ["inspect"],
        ["state", "next", "--task-id", "T-1"],
        ["check-handover"],
        ["verify"],
    ],
)
def test_v2_output_is_a_single_json_document_under_force_color(
    repository: Path, config_factory: object, extra_args: list[str]
) -> None:
    config = config_factory(repository)  # type: ignore[operator]
    env = dict(os.environ)
    env["FORCE_COLOR"] = "3"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_workflow_engine",
            "--contract-version",
            "2",
            *extra_args,
            "--config",
            str(config),
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stdout
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(result.stdout.strip())
    assert end == len(result.stdout.strip()), "more than one JSON document on stdout"
    assert parsed["contract_version"] == "2.0.0"


def test_v2_error_output_is_a_single_json_document_under_force_color(tmp_path: Path) -> None:
    missing_config = tmp_path / "does-not-exist.yaml"
    env = dict(os.environ)
    env["FORCE_COLOR"] = "3"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_workflow_engine",
            "--contract-version",
            "2",
            "check-handover",
            "--config",
            str(missing_config),
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1
    assert "\x1b" not in result.stdout
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(result.stdout.strip())
    assert end == len(result.stdout.strip())
    assert parsed["ok"] is False
