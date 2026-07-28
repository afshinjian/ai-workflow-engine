"""Tests for the common Provider interface (`MODEL_PROVIDER_CONTRACTS.md` §1).

The process boundary is mocked by *substituting the executable*, not by patching `subprocess`:
each test points the provider at a small stub script that reads the prompt on stdin and writes a
report on stdout. That makes the environment-allowlist and timeout tests meaningful — they
observe what a real child process actually received and how the real timeout actually fires —
while still requiring no Claude or Codex CLI to be installed. Tests that need to assert on argv
itself patch `subprocess.run` directly, since argv is not observable any other way.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.providers.base import (
    MAX_PROVIDER_STDOUT_BYTES,
    PROVEN_PRE_SIDE_EFFECT_RETRY_LIMIT,
    CLIProvider,
    Provider,
    ProviderFailureKind,
    ProviderInvocation,
    ProviderKind,
    ProviderResult,
    ProviderRole,
    ProviderVerdict,
    build_provider_environment,
)
from agentos_workflow.providers.claude_cli import ClaudeCLIProvider
from agentos_workflow.skills import CommandOutcome, RetryClassification

REPORT = {
    "verdict": "pass",
    "summary": "implemented the stage",
    "files_changed": ["docs/a.md"],
    "validation_performed": ["pytest"],
    "recommended_commit_message": "feat(x): do the thing",
}


def stub_cli(tmp_path: Path, body: str, *, name: str = "stub-cli") -> Path:
    """Write an executable stub standing in for a model CLI."""
    script = tmp_path / name
    script.write_text(f"#!{sys.executable}\nimport json, os, sys\n{body}\n")
    script.chmod(0o755)
    return script


def echo_report_cli(tmp_path: Path, payload: dict[str, Any] | None = None, **kwargs: Any) -> Path:
    """A stub that consumes stdin and prints a fixed report."""
    body = f"sys.stdin.read()\nprint(json.dumps({json.dumps(payload or REPORT)}))"
    return stub_cli(tmp_path, body, **kwargs)


class _StubProvider(CLIProvider):
    """A minimal `CLIProvider` used to test the shared behavior on its own."""

    _ARGV_SUFFIX = ("--stub",)

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.CLAUDE_CLI


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    directory = tmp_path / "repo"
    directory.mkdir()
    return directory


@pytest.fixture
def sessions(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


def invocation(
    workdir: Path,
    sessions: Path,
    *,
    role: ProviderRole = ProviderRole.IMPLEMENTATION,
    prompt: str = "implement AUTO-999",
    workflow_id: str = "wf-1",
    invocation_id: str = "inv-1",
) -> ProviderInvocation:
    return ProviderInvocation(
        workflow_id=workflow_id,
        stage_id="AUTO-999",
        role=role,
        prompt=prompt,
        working_directory=workdir,
        session_root=sessions,
        invocation_id=invocation_id,
    )


# ---------------------------------------------------------------------------------------------
# Interface shape (§1)
# ---------------------------------------------------------------------------------------------


class TestInterface:
    def test_provider_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            Provider()  # type: ignore[abstract]

    def test_every_provider_exposes_exactly_invoke_and_kind(self) -> None:
        # §1: "All Providers implement the same abstract interface". A subclass that added a
        # second entry point would let one provider be driven in a way another could not be,
        # which is exactly what makes MockProvider a drop-in substitute impossible.
        assert set(Provider.__abstractmethods__) == {"invoke", "kind"}

    def test_successful_invocation_returns_a_report(self, workdir: Path, sessions: Path) -> None:
        provider = _StubProvider(executable=echo_report_cli(workdir.parent), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))
        report = result.unwrap()
        assert report.verdict is ProviderVerdict.PASS
        assert report.summary == "implemented the stage"
        assert report.files_changed == ("docs/a.md",)
        assert report.validation_performed == ("pytest",)
        assert report.recommended_commit_message == "feat(x): do the thing"
        assert report.role is ProviderRole.IMPLEMENTATION

    def test_prompt_is_delivered_on_stdin(self, workdir: Path, sessions: Path) -> None:
        # The prompt must never travel in argv, where /proc and `ps` expose it to any local user.
        body = (
            "received = sys.stdin.read()\n"
            "print(json.dumps({'verdict': 'pass', 'summary': received}))"
        )
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions, prompt="the exact prompt"))
        assert result.unwrap().summary == "the exact prompt"

    def test_argv_is_provider_owned_and_excludes_the_prompt(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            seen["argv"] = argv
            seen["input"] = kwargs["input"]
            return subprocess.CompletedProcess(argv, 0, json.dumps(REPORT).encode(), b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        executable = workdir.parent / "claude"
        provider = _StubProvider(executable=executable, timeout_seconds=30)
        provider.invoke(invocation(workdir, sessions, prompt="secret-ish prompt"))

        assert seen["argv"] == [str(executable), "--stub"]
        assert "secret-ish prompt" not in " ".join(seen["argv"])
        assert seen["input"] == b"secret-ish prompt"

    def test_working_directory_is_the_target_repository(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = "sys.stdin.read()\nprint(json.dumps({'verdict': 'pass', 'summary': os.getcwd()}))"
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))
        assert Path(result.unwrap().summary).resolve() == workdir.resolve()


# ---------------------------------------------------------------------------------------------
# Environment allowlist (§1, SECURITY_MODEL.md §1)
# ---------------------------------------------------------------------------------------------


class TestEnvironmentAllowlist:
    def test_only_allowlisted_variables_reach_the_process(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_ONE", "yes")
        monkeypatch.setenv("SECRET_TOKEN_NOT_ALLOWED", "ghp_aaaaaaaaaaaaaaaaaaaa")
        monkeypatch.setenv("ALSO_NOT_ALLOWED", "nope")

        body = (
            "sys.stdin.read()\n"
            "print(json.dumps({'verdict': 'pass', 'summary': 'env',"
            " 'files_changed': sorted(os.environ)}))"
        )
        provider = _StubProvider(
            executable=stub_cli(workdir.parent, body),
            timeout_seconds=30,
            allowed_environment_variables=("ALLOWED_ONE",),
        )
        forwarded = set(provider.invoke(invocation(workdir, sessions)).unwrap().files_changed)

        assert "ALLOWED_ONE" in forwarded
        assert "SECRET_TOKEN_NOT_ALLOWED" not in forwarded
        assert "ALSO_NOT_ALLOWED" not in forwarded
        # Nothing beyond the allowlist and the engine-set entries the builder documents.
        assert forwarded <= {
            "ALLOWED_ONE",
            "PATH",
            "LC_ALL",
            "LANG",
            "TMPDIR",
            "AGENTOS_SESSION_DIRECTORY",
        }

    def test_home_is_never_forwarded_implicitly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A CLI that needs its credential store must have HOME named by the operator. Forwarding
        # it "because the CLI probably needs it" would hand every provider the whole directory.
        monkeypatch.setenv("HOME", "/home/someone")
        assert "HOME" not in build_provider_environment(())
        assert build_provider_environment(("HOME",))["HOME"] == "/home/someone"

    def test_locale_is_pinned_for_determinism(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
        environment = build_provider_environment(())
        assert environment["LC_ALL"] == "C"
        assert environment["LANG"] == "C"

    def test_allowlisted_but_unset_variable_is_not_invented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEFINITELY_UNSET", raising=False)
        assert "DEFINITELY_UNSET" not in build_provider_environment(("DEFINITELY_UNSET",))

    def test_path_is_always_present_so_the_executable_can_be_found(self) -> None:
        assert build_provider_environment(())["PATH"] == os.environ.get("PATH", "")

    def test_scratch_space_is_redirected_into_the_session_directory(self, tmp_path: Path) -> None:
        # Without this the per-invocation directory would be an empty directory nothing uses, and
        # two sessions would still share /tmp.
        environment = build_provider_environment((), session_directory=tmp_path / "s")
        assert environment["TMPDIR"] == str(tmp_path / "s")
        assert environment["AGENTOS_SESSION_DIRECTORY"] == str(tmp_path / "s")

    def test_an_allowlisted_tmpdir_cannot_redirect_scratch_out_of_the_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The engine-set values are applied last and unconditionally, so allowlisting TMPDIR
        # cannot be used to break a provider out of its own session directory.
        monkeypatch.setenv("TMPDIR", "/somewhere/else")
        environment = build_provider_environment(("TMPDIR",), session_directory=tmp_path / "s")
        assert environment["TMPDIR"] == str(tmp_path / "s")

    def test_no_session_directory_means_no_scratch_variables(self) -> None:
        environment = build_provider_environment(())
        assert "TMPDIR" not in environment
        assert "AGENTOS_SESSION_DIRECTORY" not in environment

    def test_the_process_receives_its_own_session_directory(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = (
            "sys.stdin.read()\n"
            "print(json.dumps({'verdict': 'pass',"
            " 'summary': os.environ.get('AGENTOS_SESSION_DIRECTORY', '')}))"
        )
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        report = provider.invoke(invocation(workdir, sessions, invocation_id="inv-9")).unwrap()

        assert Path(report.summary) == sessions / "wf-1" / "claude_cli" / "inv-9"
        assert Path(report.summary).is_dir()


# ---------------------------------------------------------------------------------------------
# Timeout and failure classification (§2)
# ---------------------------------------------------------------------------------------------


class TestTimeoutAndClassification:
    def test_timeout_is_enforced_and_typed(self, workdir: Path, sessions: Path) -> None:
        body = "import time\nsys.stdin.read()\ntime.sleep(30)"
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=1)
        result = provider.invoke(invocation(workdir, sessions))

        assert not result.ok
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.TIMEOUT
        assert "1s timeout" in result.error.detail
        assert result.error.execution is not None
        assert result.error.execution.timeout_status is True
        assert result.error.execution.outcome is CommandOutcome.TIMED_OUT

    def test_timeout_is_possible_side_effect_never_a_blind_retry(
        self, workdir: Path, sessions: Path
    ) -> None:
        # §2: a timeout is never, by itself, proof the provider had not already written files.
        body = "import time\nsys.stdin.read()\ntime.sleep(30)"
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=1)
        result = provider.invoke(invocation(workdir, sessions))
        assert result.error is not None
        assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT

    def test_spawn_failure_is_the_one_proven_pre_side_effect_case(
        self, workdir: Path, sessions: Path
    ) -> None:
        provider = _StubProvider(executable=workdir / "does-not-exist", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))

        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.SPAWN_FAILED
        assert result.error.retry_classification is RetryClassification.PROVEN_PRE_SIDE_EFFECT

    def test_nonzero_exit_after_starting_is_possible_side_effect(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = "sys.stdin.read()\nsys.stderr.write('boom')\nraise SystemExit(3)"
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))

        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.COMMAND_FAILED
        assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT
        assert "exited 3" in result.error.detail

    def test_retry_limit_matches_the_documented_policy(self) -> None:
        assert PROVEN_PRE_SIDE_EFFECT_RETRY_LIMIT == 3

    def test_no_failure_path_raises(self, workdir: Path, sessions: Path) -> None:
        # The never-raise contract: each of these returns a typed result rather than an exception.
        exits = stub_cli(workdir.parent, "raise SystemExit(9)")
        for provider in (
            _StubProvider(executable=workdir / "missing", timeout_seconds=30),
            _StubProvider(executable=exits, timeout_seconds=30),
        ):
            result = provider.invoke(invocation(workdir, sessions))
            assert isinstance(result, ProviderResult)
            assert not result.ok


# ---------------------------------------------------------------------------------------------
# Report parsing (§1, §2, §3)
# ---------------------------------------------------------------------------------------------


class TestReportParsing:
    @pytest.mark.parametrize(
        "stdout",
        [
            "not json at all",
            "[]",
            '"a string"',
            "{}",
            '{"summary": "no verdict"}',
            '{"verdict": "maybe", "summary": "bad verdict"}',
            '{"verdict": "pass"}',
            '{"verdict": "pass", "summary": 7}',
            '{"verdict": "pass", "summary": "s", "files_changed": "not-a-list"}',
            '{"verdict": "pass", "summary": "s", "files_changed": [1, 2]}',
            '{"verdict": "pass", "summary": "s", "recommended_commit_message": 5}',
        ],
    )
    def test_malformed_output_is_rejected_never_defaulted(
        self, stdout: str, workdir: Path, sessions: Path
    ) -> None:
        body = f"sys.stdin.read()\nsys.stdout.write({stdout!r})"
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))

        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.MALFORMED_OUTPUT
        # The process ran to completion and may already have written a diff.
        assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT

    def test_optional_fields_default_to_empty_not_to_a_claim(
        self, workdir: Path, sessions: Path
    ) -> None:
        provider = _StubProvider(
            executable=echo_report_cli(workdir.parent, {"verdict": "fail", "summary": "nope"}),
            timeout_seconds=30,
        )
        report = provider.invoke(invocation(workdir, sessions)).unwrap()

        assert report.verdict is ProviderVerdict.FAIL
        assert report.files_changed == ()
        assert report.validation_performed == ()
        assert report.findings == ()
        assert report.recommended_commit_message is None

    def test_qa_shaped_report_carries_findings(self, workdir: Path, sessions: Path) -> None:
        payload = {"verdict": "fail", "summary": "two defects", "findings": ["a", "b"]}
        provider = _StubProvider(
            executable=echo_report_cli(workdir.parent, payload), timeout_seconds=30
        )
        report = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert report.role is ProviderRole.QA
        assert report.findings == ("a", "b")

    def test_oversized_stdout_is_refused_rather_than_parsed(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oversized = json.dumps(REPORT).encode() + b" " * (MAX_PROVIDER_STDOUT_BYTES + 1)

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(argv, 0, oversized, b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        provider = _StubProvider(executable=workdir / "cli", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))

        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.MALFORMED_OUTPUT
        assert "exceeds" in result.error.detail

    def test_invalid_utf8_output_does_not_raise(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(argv, 0, b"\xff\xfe not utf-8", b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        provider = _StubProvider(executable=workdir / "cli", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.MALFORMED_OUTPUT


# ---------------------------------------------------------------------------------------------
# Secret handling (SECURITY_MODEL.md §1)
# ---------------------------------------------------------------------------------------------


class TestSecretsNeverSurface:
    def test_secret_shaped_command_output_is_redacted_in_the_failure(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = (
            "sys.stdin.read()\n"
            "sys.stderr.write('auth failed for ghp_abcdefghijklmnopqrstuvwxyz012345')\n"
            "raise SystemExit(1)"
        )
        provider = _StubProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))

        assert result.error is not None
        assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in result.error.detail
        assert "[REDACTED:github-token]" in result.error.detail
        assert result.error.execution is not None
        assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in result.error.execution.stderr

    def test_secret_shaped_report_content_is_redacted(self, workdir: Path, sessions: Path) -> None:
        payload = {
            "verdict": "pass",
            "summary": "used token ghp_abcdefghijklmnopqrstuvwxyz012345",
            "files_changed": ["AKIAIOSFODNN7EXAMPLE"],
            "findings": ["password = hunter2hunter2"],
        }
        provider = _StubProvider(
            executable=echo_report_cli(workdir.parent, payload), timeout_seconds=30
        )
        report = provider.invoke(invocation(workdir, sessions)).unwrap()

        assert "[REDACTED:github-token]" in report.summary
        assert report.files_changed == ("[REDACTED:aws-access-key-id]",)
        assert "hunter2hunter2" not in report.findings[0]

    def test_redaction_never_corrupts_the_report_structure(
        self, workdir: Path, sessions: Path
    ) -> None:
        """Regression: redacting stdout *before* parsing destroyed valid reports.

        Redaction rewrites arbitrary spans, so a finding containing `password = hunter2` had its
        closing quote swallowed by the marker and the whole report became `MALFORMED_OUTPUT` —
        silently discarding exactly the QA findings an operator most needs. Parsing now reads the
        raw stdout and redacts each extracted value, so both properties must hold at once: the
        report parses, *and* nothing unredacted survives in either the report or the audit record.
        """
        payload = {
            "verdict": "fail",
            "summary": "credential found",
            "findings": ["password = hunter2hunter2", "second finding survives too"],
        }
        provider = _StubProvider(
            executable=echo_report_cli(workdir.parent, payload), timeout_seconds=30
        )
        report = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert len(report.findings) == 2
        assert report.findings[1] == "second finding survives too"
        assert "hunter2hunter2" not in report.findings[0]
        assert report.execution is not None
        assert "hunter2hunter2" not in report.execution.stdout

    def test_audit_identity_is_a_shape_never_argv(self, workdir: Path, sessions: Path) -> None:
        # argv can carry a configured path that is itself sensitive, and this record is written
        # to the audit log.
        provider = _StubProvider(
            executable=echo_report_cli(workdir.parent, name="secret-named-cli"), timeout_seconds=30
        )
        report = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert report.execution is not None
        assert report.execution.normalized_command_identity == "claude_cli:qa"
        assert "secret-named-cli" not in report.execution.normalized_command_identity


# ---------------------------------------------------------------------------------------------
# Invocation validation
# ---------------------------------------------------------------------------------------------


class TestInvocationValidation:
    @pytest.mark.parametrize(
        "bad_id", ["../escape", "a/b", "..", ".", "", "with space", "x" * 65, "-leading"]
    )
    def test_unsafe_invocation_id_is_refused_before_any_process_runs(
        self, bad_id: str, workdir: Path, sessions: Path
    ) -> None:
        provider = _StubProvider(executable=workdir / "never-spawned", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions, invocation_id=bad_id))

        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.UNSAFE_INPUT
        # Refused before spawning: no execution record exists at all.
        assert result.error.execution is None

    def test_unsafe_workflow_id_is_refused(self, workdir: Path, sessions: Path) -> None:
        provider = _StubProvider(executable=workdir / "never-spawned", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions, workflow_id="../../etc"))
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.UNSAFE_INPUT

    def test_empty_prompt_is_refused(self, workdir: Path, sessions: Path) -> None:
        provider = _StubProvider(executable=workdir / "never-spawned", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions, prompt="   \n "))
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.UNSAFE_INPUT

    def test_relative_session_root_is_refused(self, workdir: Path) -> None:
        provider = _StubProvider(executable=workdir / "never-spawned", timeout_seconds=30)
        result = provider.invoke(invocation(workdir, Path("relative/sessions")))
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.PRECONDITION

    def test_missing_working_directory_is_refused(self, tmp_path: Path, sessions: Path) -> None:
        provider = _StubProvider(executable=tmp_path / "never-spawned", timeout_seconds=30)
        result = provider.invoke(invocation(tmp_path / "gone", sessions))
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.PRECONDITION


# ---------------------------------------------------------------------------------------------
# Configuration binding (CONFIGURATION_MODEL.md)
# ---------------------------------------------------------------------------------------------


class TestConfigurationBinding:
    def test_timeout_comes_from_configuration_not_a_default(self, workdir: Path) -> None:
        provider = _StubProvider(executable=workdir / "cli", timeout_seconds=77)
        assert provider.timeout_seconds == 77

    def test_claude_provider_reads_only_its_own_configuration_fields(self, tmp_path: Path) -> None:
        from agentos_workflow.tests.test_providers_cli import valid_config

        config = valid_config(tmp_path)
        provider = ClaudeCLIProvider.from_config(config)

        assert provider.executable == Path(config.claude_cli_executable)
        assert provider.timeout_seconds == config.claude_cli_timeout_seconds
        assert provider.timeout_seconds != config.codex_cli_timeout_seconds
