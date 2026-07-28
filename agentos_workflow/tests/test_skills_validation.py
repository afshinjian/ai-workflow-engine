"""Tests for the Validation Skills (`SKILL_CONTRACTS.md` §4), including the secret-shaped output
redaction OD-2 requires and the strict report-artifact schemas."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.skills import FailureKind, RetryClassification
from agentos_workflow.skills.validation import (
    run_formatting_checks,
    run_lint,
    run_scope_validation,
    run_secret_detection,
    run_security_checks,
    run_tests,
    validate_completion_report,
    validate_qa_report,
)

PASSING = f"{sys.executable} -c pass"
FAILING = f'{sys.executable} -c "raise SystemExit(1)"'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------------------------
# Configured-command Skills
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skill,kwarg",
    [
        (run_tests, "test_command"),
        (run_lint, "lint_command"),
        (run_formatting_checks, "formatting_command"),
        (run_security_checks, "security_command"),
    ],
)
def test_configured_command_passes(skill: Callable[..., Any], kwarg: str, repo: Path) -> None:
    result = skill(repo, **{kwarg: PASSING})
    assert result.ok and result.value is not None
    assert result.value.passed is True
    assert result.value.exit_code == 0


@pytest.mark.parametrize(
    "skill,kwarg",
    [
        (run_tests, "test_command"),
        (run_lint, "lint_command"),
        (run_formatting_checks, "formatting_command"),
        (run_security_checks, "security_command"),
    ],
)
def test_a_failing_check_is_a_result_not_a_skill_failure(
    skill: Callable[..., Any], kwarg: str, repo: Path
) -> None:
    """A failing check must route to repair, so it is `passed=False`, not a Skill error."""
    result = skill(repo, **{kwarg: FAILING})
    assert result.ok, "the Skill ran successfully; the *check* failed"
    assert result.value is not None
    assert result.value.passed is False
    assert result.value.exit_code == 1


def test_blank_command_is_rejected(repo: Path) -> None:
    result = run_tests(repo, test_command="   ")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_unparseable_command_is_rejected(repo: Path) -> None:
    result = run_tests(repo, test_command='pytest --k "unterminated')
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_missing_executable_is_a_proven_pre_side_effect_failure(repo: Path) -> None:
    result = run_tests(repo, test_command="/nonexistent/binary/xyzzy --run")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.SPAWN_FAILED
    assert result.error.retry_classification is RetryClassification.PROVEN_PRE_SIDE_EFFECT


def test_command_is_never_shell_interpreted(repo: Path) -> None:
    """Shell metacharacters in configured commands are inert data, not a second command."""
    marker = repo / "pwned"
    result = run_tests(repo, test_command=f"{sys.executable} -c pass ; touch {marker}")
    assert result.ok
    assert not marker.exists()


def test_command_runs_inside_the_target_repository(repo: Path) -> None:
    result = run_tests(repo, test_command=f'{sys.executable} -c "import os;print(os.getcwd())"')
    assert result.ok and result.value is not None
    assert str(repo.resolve()) in result.value.execution.stdout


def test_timeout_is_recorded_as_a_failed_check(repo: Path) -> None:
    result = run_tests(
        repo,
        test_command=f'{sys.executable} -c "import time;time.sleep(30)"',
        timeout_seconds=1,
    )
    assert result.ok and result.value is not None
    assert result.value.passed is False
    assert result.value.execution.timeout_status is True


def test_command_output_is_redacted_in_the_audit_record(repo: Path) -> None:
    script = "print('leaked ghp_' + 'A'*36)"
    result = run_tests(repo, test_command=f'{sys.executable} -c "{script}"')
    assert result.ok and result.value is not None
    assert "ghp_" not in result.value.execution.stdout
    assert "[REDACTED:github-token]" in result.value.execution.stdout


def test_command_identity_never_contains_raw_argv(repo: Path) -> None:
    """`AUDIT_MODEL.md` §2: the identity is a shape, never argv that could carry a credential."""
    result = run_tests(repo, test_command=f"{sys.executable} -c pass --token=ghp_secretvalue")
    assert result.ok and result.value is not None
    identity = result.value.execution.normalized_command_identity
    assert "ghp_secretvalue" not in identity
    assert identity.startswith("run_tests:")


def test_missing_repository_is_reported(tmp_path: Path) -> None:
    result = run_tests(tmp_path / "absent", test_command=PASSING)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.NOT_FOUND


# ---------------------------------------------------------------------------------------------
# run_scope_validation
# ---------------------------------------------------------------------------------------------


def test_run_scope_validation_delegates_to_one_rule_engine() -> None:
    result = run_scope_validation(
        changed_files=("src/secret.py",),
        allowed_paths=("agentos_workflow/**",),
        forbidden_paths=("src/**",),
    )
    verdict = result.unwrap()
    assert verdict.passed is False
    assert verdict.violations[0].reason == "matches a forbidden path pattern"


# ---------------------------------------------------------------------------------------------
# run_secret_detection
# ---------------------------------------------------------------------------------------------


def test_secret_detection_finds_a_committed_token(repo: Path) -> None:
    (repo / "config.py").write_text(f"API_TOKEN = 'ghp_{'A' * 36}'\n", encoding="utf-8")
    result = run_secret_detection(changed_files=("config.py",), repository_path=repo)
    scan = result.unwrap()
    assert scan.passed is False
    assert scan.findings[0].path == "config.py"
    assert scan.findings[0].line_number == 1


def test_secret_detection_findings_never_carry_the_secret(repo: Path) -> None:
    """A finding is written to an audit record; reproducing the secret would defeat the check."""
    secret = "ghp_" + "B" * 36
    (repo / "leak.py").write_text(f"token = '{secret}'\n", encoding="utf-8")
    scan = run_secret_detection(changed_files=("leak.py",), repository_path=repo).unwrap()
    assert scan.findings
    for finding in scan.findings:
        assert secret not in finding.redacted_line
        assert "REDACTED" in finding.redacted_line


def test_secret_detection_ignores_placeholders(repo: Path) -> None:
    """Firing on every example config would make the gate noise operators learn to override."""
    (repo / "example.env").write_text(
        "password=changeme\napi_key=your_api_key_here\ntoken=<YOUR_TOKEN>\nsecret=${VAR}\n",
        encoding="utf-8",
    )
    scan = run_secret_detection(changed_files=("example.env",), repository_path=repo).unwrap()
    assert scan.passed is True, f"unexpected findings: {scan.findings}"


def test_secret_detection_passes_on_clean_files(repo: Path) -> None:
    (repo / "clean.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    assert run_secret_detection(changed_files=("clean.py",), repository_path=repo).unwrap().passed


def test_secret_detection_skips_binary_and_oversized_files(repo: Path) -> None:
    (repo / "blob.bin").write_bytes(b"\x00\x01ghp_" + b"A" * 36)
    (repo / "big.txt").write_text("x" * 5000, encoding="utf-8")
    scan = run_secret_detection(
        changed_files=("blob.bin", "big.txt"), repository_path=repo, max_file_bytes=1000
    ).unwrap()
    assert scan.passed is True


def test_secret_detection_skips_deleted_paths(repo: Path) -> None:
    """A diff is a historical record; a path in it need not still exist."""
    scan = run_secret_detection(changed_files=("deleted.py",), repository_path=repo).unwrap()
    assert scan.passed is True


@pytest.mark.parametrize("hostile", ["../escape.py", "/etc/passwd", "a/../../b"])
def test_secret_detection_rejects_unsafe_paths(repo: Path, hostile: str) -> None:
    result = run_secret_detection(changed_files=(hostile,), repository_path=repo)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_secret_detection_refuses_a_symlink_escaping_the_repository(
    repo: Path, tmp_path: Path
) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("ghp_" + "C" * 36, encoding="utf-8")
    (repo / "link.txt").symlink_to(outside)
    scan = run_secret_detection(changed_files=("link.txt",), repository_path=repo)
    # Either refused outright or skipped — never scanned and reported from outside the root.
    if scan.ok and scan.value is not None:
        assert scan.value.passed is True
    else:
        assert scan.error is not None


def test_secret_detection_reports_correct_line_numbers(repo: Path) -> None:
    (repo / "multi.py").write_text(
        "line one\nline two\nAKIA" + "Z" * 16 + "\nline four\n", encoding="utf-8"
    )
    scan = run_secret_detection(changed_files=("multi.py",), repository_path=repo).unwrap()
    assert scan.findings[0].line_number == 3
    assert scan.findings[0].kind == "aws-access-key-id"


# ---------------------------------------------------------------------------------------------
# Report-artifact Skills
# ---------------------------------------------------------------------------------------------


def valid_completion() -> dict[str, object]:
    return {
        "stage_id": "AUTO-003",
        "branch": "feature/auto-003-repository-validation-skills",
        "head_sha": "a" * 40,
        "summary": "Implemented the skill families.",
        "commit_message": "feat(workflow): add skills (AUTO-003)",
        "created_files": ["agentos_workflow/skills/repository.py"],
        "modified_files": [],
        "deleted_files": [],
        "tests_added": ["test_skills_repository.py"],
        "final_status": "COMPLETE",
    }


def valid_qa() -> dict[str, object]:
    return {
        "stage_id": "AUTO-003",
        "branch": "feature/auto-003-repository-validation-skills",
        "head_sha": "b" * 40,
        "summary": "Independent review.",
        "verdict": "APPROVED",
        "findings": [],
    }


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_completion_report_passes(tmp_path: Path) -> None:
    report = write_json(tmp_path / "r.json", valid_completion())
    validation = validate_completion_report(report).unwrap()
    assert validation.passed is True
    assert validation.schema_errors == ()
    assert validation.report is not None


def test_completion_report_reports_every_schema_error_at_once(tmp_path: Path) -> None:
    """One repair pass should be able to fix everything."""
    payload = valid_completion()
    del payload["stage_id"]
    payload["created_files"] = "not-a-list"
    payload["final_status"] = "MAYBE"
    report = write_json(tmp_path / "r.json", payload)
    validation = validate_completion_report(report).unwrap()
    assert validation.passed is False
    assert len(validation.schema_errors) == 3
    assert validation.report is None


def test_valid_qa_report_passes(tmp_path: Path) -> None:
    report = write_json(tmp_path / "qa.json", valid_qa())
    assert validate_qa_report(report).unwrap().passed is True


@pytest.mark.parametrize("verdict", ["approved", "PASS", "APPROVED_WITH_NOTES", "", "REJECTED?"])
def test_qa_verdict_is_exactly_two_tokens(tmp_path: Path, verdict: str) -> None:
    """`docs/AGENT_PROTOCOL.md`: a verdict is one token, never partial or hedged."""
    payload = valid_qa()
    payload["verdict"] = verdict
    report = write_json(tmp_path / "qa.json", payload)
    validation = validate_qa_report(report).unwrap()
    assert validation.passed is False
    assert validation.report is None


def test_rejected_qa_report_requires_findings(tmp_path: Path) -> None:
    """A rejection with no findings gives the repair loop nothing to act on."""
    payload = valid_qa()
    payload["verdict"] = "REJECTED"
    payload["findings"] = []
    report = write_json(tmp_path / "qa.json", payload)
    validation = validate_qa_report(report).unwrap()
    assert validation.passed is False
    assert any("findings" in error for error in validation.schema_errors)


def test_rejected_qa_report_with_findings_passes(tmp_path: Path) -> None:
    payload = valid_qa()
    payload["verdict"] = "REJECTED"
    payload["findings"] = ["scope violation in src/"]
    report = write_json(tmp_path / "qa.json", payload)
    assert validate_qa_report(report).unwrap().passed is True


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    """Last-key-wins would let a tampered report be judged as whichever value the parser kept."""
    report = tmp_path / "qa.json"
    report.write_text(
        '{"stage_id":"AUTO-003","branch":"b","head_sha":"c","summary":"s",'
        '"findings":[],"verdict":"REJECTED","verdict":"APPROVED"}',
        encoding="utf-8",
    )
    result = validate_qa_report(report)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT
    assert "duplicate" in result.error.detail


def test_nested_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    report.write_text('{"a": {"x": 1, "x": 2}}', encoding="utf-8")
    result = validate_completion_report(report)
    assert not result.ok and result.error is not None
    assert "duplicate" in result.error.detail


def test_malformed_json_is_a_skill_failure(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    report.write_text("{not json", encoding="utf-8")
    result = validate_completion_report(report)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT


def test_non_object_json_is_rejected(tmp_path: Path) -> None:
    report = write_json(tmp_path / "r.json", ["a", "list"])
    result = validate_completion_report(report)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT


def test_missing_report_is_a_skill_failure(tmp_path: Path) -> None:
    result = validate_completion_report(tmp_path / "absent.json")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.NOT_FOUND


def test_report_symlink_is_rejected(tmp_path: Path) -> None:
    real = write_json(tmp_path / "real.json", valid_qa())
    link = tmp_path / "link.json"
    link.symlink_to(real)
    result = validate_qa_report(link)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_blank_required_strings_are_rejected(tmp_path: Path) -> None:
    payload = valid_completion()
    payload["summary"] = "   "
    report = write_json(tmp_path / "r.json", payload)
    assert validate_completion_report(report).unwrap().passed is False
