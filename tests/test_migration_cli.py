"""`workflowctl migrate inspect|plan|apply` end to end: v1/v2 CLI contract behavior,
single-JSON-document stdout purity under `FORCE_COLOR`, the apply refusal path (including
its F-7 refuse-before-any-source-access property), F-1 source-root-symlink safety at the
CLI layer, and proof that no real governance/repository file is ever touched by any
`migrate` invocation.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.workflow.event_store import task_dir_name
from ai_workflow_engine.workflow.events import WorkflowEvent

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every `migrate` command defaults `--source` to `$HOME/.ai-workflow-engine/workflow-runs`;
    isolate `$HOME` per test so nothing here ever touches a real user's directory.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _run_cli(
    args: list[str], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_workflow_engine", *args],
        capture_output=True,
        text=True,
        env=env if env is not None else dict(os.environ),
        check=False,
    )


def _populate_source(source: Path) -> None:
    # Written directly (not via `workflow.event_store.append`, which always targets the
    # real `~/.ai-workflow-engine/workflow-runs` regardless of this explicit `--source`
    # path) so passing an arbitrary `--source` in these tests never touches a real
    # user's home directory. A single, valid plan-review/APPROVED event: the first event
    # of any history must be `plan-review` per the real transition table.
    directory = source / "state" / "p" / task_dir_name("t")
    directory.mkdir(parents=True)
    event = WorkflowEvent(
        schema_version="1.0",
        project_id="p",
        task_id="t",
        sequence=1,
        parent_digest=None,
        stage="plan-review",
        action="verdict",
        verdict="APPROVED",
        prompt_id=None,
        agent_run_id=None,
        head="a" * 40,
        note="",
    )
    (directory / "00000001.json").write_bytes(canonical_json(event.model_dump(mode="json")) + b"\n")


# --- inspect: v1 (unenveloped) and v2 (stable envelope) --------------------------------------


def test_inspect_v1_default_contract_is_unenveloped(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    result = _run_cli(
        ["migrate", "inspect", "--to", "2.0.0", "--source", str(source), "--output", "json"]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_name"] == "migration-manifest"
    assert "contract_version" not in payload
    assert payload["known_count"] == 1
    assert payload["artifacts"][0]["entry_type"] == "file"


def test_inspect_v2_is_enveloped(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "inspect",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["contract_version"] == "2.0.0"
    assert payload["command"] == "migrate-inspect"
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["schema_name"] == "migration-manifest"
    assert payload["data"]["known_count"] == 1


def test_inspect_v1_and_v2_data_are_field_compatible(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    v1 = json.loads(
        _run_cli(
            ["migrate", "inspect", "--to", "2.0.0", "--source", str(source), "--output", "json"]
        ).stdout
    )
    v2 = json.loads(
        _run_cli(
            [
                "--contract-version",
                "2",
                "migrate",
                "inspect",
                "--to",
                "2.0.0",
                "--source",
                str(source),
                "--output",
                "json",
            ]
        ).stdout
    )
    assert v2["data"] == v1


# --- plan --------------------------------------------------------------------------------------


def test_plan_v2_success_envelope(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "plan",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["backup_plan"]["schema_name"] == "migration-backup-plan"
    assert payload["data"]["backup_plan"]["complete"] is True
    assert payload["data"]["recovery_plan"]["schema_name"] == "migration-recovery-plan"


# --- apply: dry-run succeeds, real apply refuses before any write or source access ------------


def test_apply_dry_run_succeeds(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    result = _run_cli(
        [
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--dry-run",
            "--output",
            "json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["status"] == "DRY_RUN_OK"
    assert payload["backup_complete"] is True
    after = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert before == after


def test_apply_without_dry_run_refuses_with_v2_error_envelope(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ApplyNotAuthorizedError"
    after = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert before == after


def test_apply_without_dry_run_refuses_with_v1_stderr(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    result = _run_cli(
        ["migrate", "apply", "--to", "2.0.0", "--source", str(source), "--output", "json"]
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "ApplyNotAuthorizedError" in result.stderr or "not authorized" in result.stderr


def test_apply_no_dry_run_flag_also_refuses(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    result = _run_cli(
        [
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--no-dry-run",
            "--output",
            "json",
        ]
    )
    assert result.returncode == 2


def test_apply_without_dry_run_refuses_with_nonexistent_source(tmp_path: Path) -> None:
    """F-7: real-apply refusal must occur before the source tree is read at all -- proven
    here by pointing --source at a path that does not exist. If the CLI read the source
    tree before checking --dry-run, this would instead succeed with an empty manifest (an
    empty source root is a legitimate state) or otherwise behave differently; it must
    always be the exact same ApplyNotAuthorizedError refusal.
    """
    missing_source = tmp_path / "does-not-exist-at-all"
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(missing_source),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ApplyNotAuthorizedError"


def test_apply_without_dry_run_refuses_with_unreadable_source(tmp_path: Path) -> None:
    """F-7: same property, proven with a source root that exists but cannot be listed."""
    unreadable_source = tmp_path / "unreadable-legacy"
    unreadable_source.mkdir()
    original_mode = unreadable_source.stat().st_mode
    unreadable_source.chmod(0o000)
    try:
        result = _run_cli(
            [
                "--contract-version",
                "2",
                "migrate",
                "apply",
                "--to",
                "2.0.0",
                "--source",
                str(unreadable_source),
                "--output",
                "json",
            ]
        )
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "ApplyNotAuthorizedError"
    finally:
        import stat

        unreadable_source.chmod(
            stat.S_IMODE(original_mode) | stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR
        )


def test_apply_without_dry_run_refuses_even_with_unsupported_to_version(tmp_path: Path) -> None:
    """F-7: the refusal happens before `--to` is even validated -- an invalid --to value
    still produces the same ApplyNotAuthorizedError, not an UnsupportedMigrationTargetError.
    """
    source = tmp_path / "legacy"
    _populate_source(source)
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "apply",
            "--to",
            "9.9.9",
            "--source",
            str(source),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "ApplyNotAuthorizedError"


# --- F-1: source-root symlink rejection at the CLI layer --------------------------------------


def test_migrate_inspect_rejects_symlink_source_root(tmp_path: Path) -> None:
    secret_target = tmp_path / "secret-target"
    secret_target.mkdir()
    (secret_target / "state").mkdir()
    (secret_target / "state" / "leak.json").write_text("SECRET_MARKER_VALUE", encoding="utf-8")
    link_root = tmp_path / "legacy-link"
    link_root.symlink_to(secret_target)

    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "inspect",
            "--to",
            "2.0.0",
            "--source",
            str(link_root),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "MigrationSourceError"
    assert "SECRET_MARKER_VALUE" not in result.stdout
    assert "SECRET_MARKER_VALUE" not in result.stderr


# --- unsupported --to version fails closed with a stable error --------------------------------


def test_unsupported_to_version_v2_error_envelope(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir(parents=True)
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "inspect",
            "--to",
            "9.9.9",
            "--source",
            str(source),
            "--output",
            "json",
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UnsupportedMigrationTargetError"


# --- empty source via CLI ------------------------------------------------------------------


def test_empty_source_via_cli(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir(parents=True)
    result = _run_cli(
        ["migrate", "inspect", "--to", "2.0.0", "--source", str(source), "--output", "json"]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["artifact_count"] == 0


# --- default --source resolves under $HOME, isolated from the real user directory -------------


def test_default_source_is_isolated_home(tmp_path: Path, _isolated_home: Path) -> None:
    result = _run_cli(["migrate", "inspect", "--to", "2.0.0", "--output", "json"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["source_root"] == str(_isolated_home / ".ai-workflow-engine" / "workflow-runs")
    assert payload["artifact_count"] == 0


# --- exactly one JSON stdout document under FORCE_COLOR, no ANSI contamination ----------------


@pytest.mark.parametrize("extra_args", [["inspect"], ["plan"], ["apply", "--dry-run"]])
def test_v2_output_is_a_single_json_document_under_force_color(
    tmp_path: Path, extra_args: list[str]
) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    env = dict(os.environ)
    env["FORCE_COLOR"] = "3"
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            *extra_args,
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--output",
            "json",
        ],
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stdout
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(result.stdout.strip())
    assert end == len(result.stdout.strip()), "more than one JSON document on stdout"
    assert parsed["contract_version"] == "2.0.0"


def test_v1_output_is_a_single_json_document_under_force_color(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    env = dict(os.environ)
    env["FORCE_COLOR"] = "3"
    result = _run_cli(
        ["migrate", "inspect", "--to", "2.0.0", "--source", str(source), "--output", "json"],
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stdout
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(result.stdout.strip())
    assert end == len(result.stdout.strip())
    assert parsed["schema_name"] == "migration-manifest"


def test_v2_error_output_is_a_single_json_document_under_force_color(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    _populate_source(source)
    env = dict(os.environ)
    env["FORCE_COLOR"] = "3"
    result = _run_cli(
        [
            "--contract-version",
            "2",
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--output",
            "json",
        ],
        env=env,
    )
    assert result.returncode == 1
    assert "\x1b" not in result.stdout
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(result.stdout.strip())
    assert end == len(result.stdout.strip())
    assert parsed["ok"] is False


# --- real governance and repository files remain unchanged -----------------------------------


def test_real_governance_files_are_never_touched(tmp_path: Path) -> None:
    watched = [
        REPO_ROOT / "self-governance.yaml",
        REPO_ROOT / "docs" / "implementation" / "orchestration" / "implementation-state.yaml",
        REPO_ROOT / "docs" / "implementation" / "orchestration" / "migration-registry.yaml",
    ]
    before = {path: path.read_bytes() for path in watched}

    source = tmp_path / "legacy"
    _populate_source(source)
    for args in (
        ["migrate", "inspect", "--to", "2.0.0", "--source", str(source), "--output", "json"],
        ["migrate", "plan", "--to", "2.0.0", "--source", str(source), "--output", "json"],
        [
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--dry-run",
            "--output",
            "json",
        ],
        [
            "migrate",
            "apply",
            "--to",
            "2.0.0",
            "--source",
            str(source),
            "--output",
            "json",
        ],  # refused
    ):
        _run_cli(args)

    after = {path: path.read_bytes() for path in watched}
    assert before == after
