"""Tests for the shared Skill primitives: redaction (OD-2), the subprocess boundary, and the
typed result/failure surface (`SKILL_CONTRACTS.md` §7)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from agentos_workflow.skills import (
    CommandOutcome,
    FailureKind,
    RetryClassification,
    SkillResult,
    failure,
    redact_secrets,
    run_fixed_argv,
    success,
)

SECRET_SAMPLES = [
    ("ghp_" + "A" * 36, "github-token"),
    ("github_pat_" + "B" * 30, "github-pat"),
    ("AKIA" + "C" * 16, "aws-access-key-id"),
    ("ASIA" + "D" * 16, "aws-access-key-id"),
    ("xoxb-" + "1" * 20, "slack-token"),
    ("sk_live_" + "e" * 24, "stripe-key"),
    ("AIza" + "f" * 35, "google-api-key"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop", "jwt"),
]


@pytest.mark.parametrize("secret,kind", SECRET_SAMPLES)
def test_known_secret_shapes_are_redacted(secret: str, kind: str) -> None:
    redacted = redact_secrets(f"leaked value {secret} in output")
    assert secret not in redacted
    assert f"[REDACTED:{kind}]" in redacted


@pytest.mark.parametrize("secret,_kind", SECRET_SAMPLES)
def test_redaction_is_idempotent(secret: str, _kind: str) -> None:
    """Re-redacting already-redacted text must not corrupt the marker or leak a fragment."""
    once = redact_secrets(f"value: {secret}")
    assert redact_secrets(once) == once


def test_private_key_block_is_redacted_in_full() -> None:
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAsecretbodyline\n"
        "anotherlineofkeymaterial\n"
        "-----END RSA PRIVATE KEY-----"
    )
    redacted = redact_secrets(f"before\n{block}\nafter")
    assert "secretbodyline" not in redacted
    assert "anotherlineofkeymaterial" not in redacted
    assert "before" in redacted and "after" in redacted


def test_url_credentials_are_redacted_but_host_is_kept() -> None:
    redacted = redact_secrets("remote https://octocat:ghs_tokenvalue@github.com/o/r.git")
    assert "octocat" not in redacted
    assert "ghs_tokenvalue" not in redacted
    # The host must survive: repository identity diagnostics are useless without it.
    assert "github.com/o/r" in redacted


def test_labelled_secrets_are_redacted() -> None:
    for line in ("password=hunter2value", "api_key: abcdefghijkl", 'SECRET_TOKEN = "zzzzzzzz"'):
        assert "[REDACTED:labelled-secret]" in redact_secrets(line)


def test_authorization_header_is_redacted() -> None:
    assert "tokenvalue" not in redact_secrets("Authorization: Bearer tokenvalue12345")


def test_ordinary_output_is_not_redacted() -> None:
    """A redactor that fires on normal output trains operators to ignore it."""
    benign = (
        "1982 passed in 41.20s\n"
        "commit 87a50627742c18d273e504f5f803cb1a98b95bef\n"
        "sha256 b992e56bbcfad34b0011223344556677\n"
        "docs/workflow-automation/SKILL_CONTRACTS.md | 12 +++---\n"
    )
    assert redact_secrets(benign) == benign


def test_redaction_handles_empty_and_large_input() -> None:
    assert redact_secrets("") == ""
    # Linear-time patterns: a long adversarial line must not hang the redactor.
    assert redact_secrets("a" * 200_000).count("a") == 200_000


def test_run_fixed_argv_captures_success() -> None:
    execution = run_fixed_argv(
        (sys.executable, "-c", "print('hello')"), identity="test:python(2 args)"
    )
    assert execution.succeeded
    assert execution.outcome is CommandOutcome.COMPLETED
    assert execution.exit_code == 0
    assert "hello" in execution.stdout
    assert execution.timeout_status is False
    assert execution.completion_time >= execution.start_time


def test_run_fixed_argv_records_nonzero_exit_without_raising() -> None:
    execution = run_fixed_argv((sys.executable, "-c", "raise SystemExit(3)"), identity="test")
    assert execution.exit_code == 3
    assert not execution.succeeded
    assert execution.outcome is CommandOutcome.COMPLETED


def test_run_fixed_argv_records_timeout_without_raising() -> None:
    execution = run_fixed_argv(
        (sys.executable, "-c", "import time; time.sleep(30)"), identity="test", timeout_seconds=1
    )
    assert execution.outcome is CommandOutcome.TIMED_OUT
    assert execution.timeout_status is True
    assert execution.exit_code is None


def test_run_fixed_argv_records_spawn_failure_without_raising() -> None:
    execution = run_fixed_argv(("/nonexistent/binary/xyzzy",), identity="test")
    assert execution.outcome is CommandOutcome.SPAWN_FAILED
    assert execution.exit_code is None


def test_run_fixed_argv_redacts_captured_output() -> None:
    """Output is redacted at the boundary, so no caller can log a raw credential by mistake."""
    execution = run_fixed_argv(
        (sys.executable, "-c", "print('token=' + 'ghp_' + 'A'*36)"), identity="test"
    )
    assert "ghp_" not in execution.stdout
    assert "[REDACTED:github-token]" in execution.stdout


def test_environment_is_an_allowlist_not_an_inheritance(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SECURITY_MODEL.md` §1: only named variables reach a subprocess."""
    monkeypatch.setenv("AGENTOS_TEST_SECRET", "must-not-propagate")
    monkeypatch.setenv("AGENTOS_TEST_ALLOWED", "propagates")
    script = "import os; print(os.environ.get('AGENTOS_TEST_SECRET', 'ABSENT'))"
    execution = run_fixed_argv((sys.executable, "-c", script), identity="test")
    assert "ABSENT" in execution.stdout
    assert "must-not-propagate" not in execution.stdout

    allowed_script = "import os; print(os.environ.get('AGENTOS_TEST_ALLOWED', 'ABSENT'))"
    allowed = run_fixed_argv(
        (sys.executable, "-c", allowed_script),
        identity="test",
        allowed_environment_variables=("AGENTOS_TEST_ALLOWED",),
    )
    assert "propagates" in allowed.stdout


def test_locale_is_pinned_for_determinism() -> None:
    execution = run_fixed_argv(
        (sys.executable, "-c", "import os; print(os.environ['LC_ALL'], os.environ['LANG'])"),
        identity="test",
    )
    assert "C C" in execution.stdout


def test_interactive_credential_prompts_are_disabled() -> None:
    execution = run_fixed_argv(
        (sys.executable, "-c", "import os; print(os.environ['GIT_TERMINAL_PROMPT'])"),
        identity="test",
    )
    assert execution.stdout.strip() == "0"


def test_subprocess_stdin_is_closed() -> None:
    """A command that reads stdin must get EOF, not block until its timeout."""
    execution = run_fixed_argv(
        (sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"),
        identity="test",
        timeout_seconds=10,
    )
    assert execution.succeeded
    assert execution.stdout.strip() == "0"


def test_argv_is_never_shell_interpreted(tmp_path: Path) -> None:
    """Shell metacharacters in an argument are inert data, not syntax."""
    marker = tmp_path / "pwned"
    execution = run_fixed_argv(
        (sys.executable, "-c", "import sys; print(sys.argv[1])", f"; touch {marker}"),
        identity="test",
    )
    assert execution.succeeded
    assert not marker.exists()


def test_invalid_utf8_output_does_not_raise() -> None:
    execution = run_fixed_argv(
        (sys.executable, "-c", r"import sys; sys.stdout.buffer.write(b'\xff\xfe bad')"),
        identity="test",
    )
    assert execution.succeeded
    assert "bad" in execution.stdout


def test_failure_detail_is_redacted() -> None:
    result: SkillResult[None] = failure(
        "some_skill", FailureKind.COMMAND_FAILED, "failed with token=ghp_" + "A" * 36
    )
    assert result.ok is False
    assert result.error is not None
    assert "ghp_" not in result.error.detail
    assert result.error.retry_classification is RetryClassification.NOT_APPLICABLE


def test_success_and_unwrap() -> None:
    assert success(42).unwrap() == 42
    with pytest.raises(AssertionError):
        failure("s", FailureKind.NOT_FOUND, "missing").unwrap()


def test_audit_directory_is_not_polluted_by_running_commands(tmp_path: Path) -> None:
    """The subprocess primitive writes nothing on its own; only Reporting Skills write files."""
    before = set(os.listdir(tmp_path))
    run_fixed_argv((sys.executable, "-c", "pass"), identity="test", cwd=str(tmp_path))
    assert set(os.listdir(tmp_path)) == before
