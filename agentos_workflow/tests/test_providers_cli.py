"""Tests for the two CLI adapters and live provider selection
(`MODEL_PROVIDER_CONTRACTS.md` §2, §3, §8).

Each adapter contributes only its CLI's identity, argv shape, and stdout transport; everything
else is the shared `CLIProvider` behavior covered in `test_providers_base.py`. These tests
therefore concentrate on exactly those three things, plus the role→provider assignment that
`select_live_provider` owns.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers import (
    ClaudeCLIProvider,
    CodexCLIProvider,
    ProviderRole,
    live_provider_roles,
    select_live_provider,
)
from agentos_workflow.providers.base import ProviderFailureKind, ProviderKind, ProviderVerdict
from agentos_workflow.tests.test_providers_base import invocation, stub_cli


def valid_config(repository_path: Path, **overrides: object) -> WorkflowConfig:
    raw: dict[str, object] = {
        "repository_path": str(repository_path),
        "repository_identity": "github.com/org/some-other-repo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/some-program/stage-prompts",
        "stage_branch_naming": "governance/{stage_id}-{slug}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests"],
        "merge_method": "squash",
        "claude_cli_executable": "/usr/local/bin/claude",
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": "/usr/local/bin/codex",
        "codex_cli_timeout_seconds": 900,
        "allowed_environment_variables": ["PATH", "HOME"],
        "allowed_changed_paths": ["docs/some-program/**"],
        "forbidden_changed_paths": ["src/**"],
        "repair_attempt_limit": 3,
        "state_directory": "/home/user/.agentos/state/x",
        "audit_directory": "/home/user/.agentos/audit/x",
    }
    raw.update(overrides)
    return WorkflowConfig.model_validate(raw)


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    directory = tmp_path / "repo"
    directory.mkdir()
    return directory


@pytest.fixture
def sessions(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


def captured_argv(
    provider: Any, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    seen: list[str] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.extend(argv)
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"verdict": "pass", "summary": "s"}).encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider.invoke(invocation(workdir, sessions))
    return seen


class TestClaudeCLIProvider:
    def test_kind_and_fixed_argv(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = ClaudeCLIProvider(executable=Path("/usr/local/bin/claude"), timeout_seconds=60)
        assert provider.kind is ProviderKind.CLAUDE_CLI
        assert captured_argv(provider, workdir, sessions, monkeypatch) == [
            "/usr/local/bin/claude",
            "--print",
            "--output-format",
            "json",
        ]

    def test_from_config_binds_the_claude_fields(self, tmp_path: Path) -> None:
        config = valid_config(tmp_path)
        provider = ClaudeCLIProvider.from_config(config)

        assert provider.executable == Path("/usr/local/bin/claude")
        assert provider.timeout_seconds == 1800
        assert provider.allowed_environment_variables == ("PATH", "HOME")

    def test_result_envelope_is_unwrapped(self, workdir: Path, sessions: Path) -> None:
        # `--output-format json` wraps the model's answer in a session envelope.
        envelope = {
            "type": "result",
            "subtype": "success",
            "result": json.dumps({"verdict": "pass", "summary": "from the envelope"}),
        }
        body = f"sys.stdin.read()\nprint(json.dumps({json.dumps(envelope)}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        report = provider.invoke(invocation(workdir, sessions)).unwrap()
        assert report.summary == "from the envelope"

    def test_bare_report_without_an_envelope_is_still_accepted(
        self, workdir: Path, sessions: Path
    ) -> None:
        report = {"verdict": "fail", "summary": "no envelope here"}
        body = f"sys.stdin.read()\nprint(json.dumps({json.dumps(report)}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions)).unwrap()
        assert result.verdict is ProviderVerdict.FAIL
        assert result.summary == "no envelope here"

    def test_envelope_with_unparseable_result_is_malformed(
        self, workdir: Path, sessions: Path
    ) -> None:
        envelope = {"type": "result", "result": "I could not produce a report."}
        body = f"sys.stdin.read()\nprint(json.dumps({json.dumps(envelope)}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.MALFORMED_OUTPUT


class TestCodexCLIProvider:
    def test_kind_and_fixed_argv(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = CodexCLIProvider(executable=Path("/usr/local/bin/codex"), timeout_seconds=60)
        assert provider.kind is ProviderKind.CODEX_CLI
        assert captured_argv(provider, workdir, sessions, monkeypatch) == [
            "/usr/local/bin/codex",
            "exec",
            "--json",
        ]

    def test_from_config_binds_the_codex_fields_and_its_own_timeout(self, tmp_path: Path) -> None:
        config = valid_config(tmp_path)
        provider = CodexCLIProvider.from_config(config)

        assert provider.executable == Path("/usr/local/bin/codex")
        # Its own budget, not the implementation CLI's.
        assert provider.timeout_seconds == 900
        assert provider.timeout_seconds != config.claude_cli_timeout_seconds

    def test_last_json_object_in_an_event_stream_wins(self, workdir: Path, sessions: Path) -> None:
        # Earlier lines are progress events; treating one as the verdict would report on an
        # unfinished run.
        lines = [
            json.dumps({"type": "started"}),
            json.dumps({"verdict": "pass", "summary": "intermediate"}),
            json.dumps({"verdict": "fail", "summary": "final", "findings": ["defect"]}),
        ]
        body = "sys.stdin.read()\n" + "".join(f"print({line!r})\n" for line in lines)
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        report = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert report.verdict is ProviderVerdict.FAIL
        assert report.summary == "final"
        assert report.findings == ("defect",)

    def test_non_json_progress_lines_are_skipped(self, workdir: Path, sessions: Path) -> None:
        body = (
            "sys.stdin.read()\n"
            "print('thinking...')\n"
            "print('still working')\n"
            f"print({json.dumps({'verdict': 'pass', 'summary': 'done'})!r})\n"
        )
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        assert provider.invoke(invocation(workdir, sessions)).unwrap().summary == "done"

    def test_stdout_with_no_json_object_is_malformed_never_an_assumed_pass(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = "sys.stdin.read()\nprint('no structured output at all')"
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        result = provider.invoke(invocation(workdir, sessions))

        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.MALFORMED_OUTPUT
        assert result.value is None


class TestLiveProviderSelection:
    @pytest.mark.parametrize(
        "role,expected",
        [
            (ProviderRole.IMPLEMENTATION, ClaudeCLIProvider),
            (ProviderRole.REPAIR, ClaudeCLIProvider),
            (ProviderRole.QA, CodexCLIProvider),
        ],
    )
    def test_default_role_assignment(
        self, role: ProviderRole, expected: type, tmp_path: Path
    ) -> None:
        # §2/§3: Claude is implementation and repair, Codex is independent QA.
        assert isinstance(select_live_provider(role, valid_config(tmp_path)), expected)

    def test_every_role_is_mapped(self, tmp_path: Path) -> None:
        for role in ProviderRole:
            assert role in live_provider_roles()
            select_live_provider(role, valid_config(tmp_path))

    def test_each_selection_returns_a_fresh_instance(self, tmp_path: Path) -> None:
        # §5: two invocations in one workflow must not share an in-process object.
        config = valid_config(tmp_path)
        first = select_live_provider(ProviderRole.IMPLEMENTATION, config)
        second = select_live_provider(ProviderRole.IMPLEMENTATION, config)
        assert first is not second

    def test_unknown_role_raises_rather_than_selecting_a_default(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError):
            select_live_provider("not-a-role", valid_config(tmp_path))  # type: ignore[arg-type]

    def test_selection_honors_the_target_repositorys_own_configuration(
        self, tmp_path: Path
    ) -> None:
        config = valid_config(
            tmp_path,
            claude_cli_executable="/opt/custom/claude",
            claude_cli_timeout_seconds=42,
            allowed_environment_variables=["PATH"],
        )
        provider = select_live_provider(ProviderRole.IMPLEMENTATION, config)

        assert provider.executable == Path("/opt/custom/claude")
        assert provider.timeout_seconds == 42
        assert provider.allowed_environment_variables == ("PATH",)
