"""Tests for the two CLI adapters and live provider selection
(`MODEL_PROVIDER_CONTRACTS.md` §2, §3, §8).

Each adapter contributes only its CLI's identity, argv shape, and stdout transport; everything
else is the shared `CLIProvider` behavior covered in `test_providers_base.py`. These tests
therefore concentrate on exactly those three things, plus the role→provider assignment that
`select_live_provider` owns.
"""

from __future__ import annotations

import json
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


SESSION_DIRECTORY = Path("/sessions/wf-1/provider/inv-1")


def codex_event_stream(report: dict[str, Any], *, progress: list[str] | None = None) -> list[str]:
    """A Codex `--json` event stream ending in the agent's final message.

    Shaped after the event grammar a live `codex exec --json` invocation actually emitted
    (`thread.started`, `turn.started`, ..., recorded in AUTO-010), with the final answer carried
    by an `item.completed` event whose item is an `agent_message`.
    """
    return [
        json.dumps({"type": "thread.started", "thread_id": "t-1"}),
        json.dumps({"type": "turn.started"}),
        *(progress or []),
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(report)},
            }
        ),
        json.dumps({"type": "turn.completed"}),
    ]


class TestClaudeCLIProvider:
    def test_kind_and_fixed_argv(self) -> None:
        provider = ClaudeCLIProvider(executable=Path("/usr/local/bin/claude"), timeout_seconds=60)
        assert provider.kind is ProviderKind.CLAUDE_CLI
        # Verified against `claude --help` (2.1.220) in AUTO-010. The permission mode is always
        # present and always explicit -- never left to the operator's own settings file.
        assert list(provider.argv(SESSION_DIRECTORY)) == [
            "/usr/local/bin/claude",
            "--print",
            "--output-format",
            "json",
            "--permission-mode",
            "plan",
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
    def test_kind_and_fixed_argv(self) -> None:
        provider = CodexCLIProvider(executable=Path("/usr/local/bin/codex"), timeout_seconds=60)
        assert provider.kind is ProviderKind.CODEX_CLI
        # Verified against `codex exec --help` (codex-cli 0.146.0) in AUTO-010.
        assert list(provider.argv(SESSION_DIRECTORY)) == [
            "/usr/local/bin/codex",
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "-c",
            'approval_policy="never"',
            "--output-last-message",
            str(SESSION_DIRECTORY / "codex-last-message.txt"),
        ]

    def test_from_config_binds_the_codex_fields_and_its_own_timeout(self, tmp_path: Path) -> None:
        config = valid_config(tmp_path)
        provider = CodexCLIProvider.from_config(config)

        assert provider.executable == Path("/usr/local/bin/codex")
        # Its own budget, not the implementation CLI's.
        assert provider.timeout_seconds == 900
        assert provider.timeout_seconds != config.claude_cli_timeout_seconds

    def test_the_answer_file_is_the_primary_channel(self, workdir: Path, sessions: Path) -> None:
        # `--output-last-message` names the file; the adapter reads the answer from there rather
        # than reconstructing it from the CLI's own event envelope.
        report = {"verdict": "fail", "summary": "from the answer file", "findings": ["defect"]}
        body = (
            "sys.stdin.read()\n"
            "answer = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
            f"open(answer, 'w').write({json.dumps(report)!r})\n"
        )
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        parsed = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert parsed.verdict is ProviderVerdict.FAIL
        assert parsed.summary == "from the answer file"
        assert parsed.findings == ("defect",)

    def test_the_answer_file_is_written_inside_this_invocations_session_directory(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = (
            "sys.stdin.read()\n"
            "answer = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
            'open(answer, \'w\').write(\'{"verdict": "pass", "summary": "ok"}\')\n'
        )
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        provider.invoke(invocation(workdir, sessions, invocation_id="inv-7")).unwrap()

        expected = sessions / "wf-1" / "codex_cli" / "inv-7" / "codex-last-message.txt"
        assert expected.is_file()

    def test_final_agent_message_in_the_event_stream_is_the_fallback(
        self, workdir: Path, sessions: Path
    ) -> None:
        # When no answer file was written, the last `agent_message` item -- never a progress
        # event -- carries the report. Reading a progress event as the verdict would report on an
        # unfinished run.
        lines = codex_event_stream(
            {"verdict": "fail", "summary": "final", "findings": ["defect"]},
            progress=[json.dumps({"type": "item.completed", "item": {"type": "reasoning"}})],
        )
        body = "sys.stdin.read()\n" + "".join(f"print({line!r})\n" for line in lines)
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        report = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert report.verdict is ProviderVerdict.FAIL
        assert report.summary == "final"
        assert report.findings == ("defect",)

    def test_the_answer_file_wins_over_the_event_stream(
        self, workdir: Path, sessions: Path
    ) -> None:
        lines = codex_event_stream({"verdict": "pass", "summary": "from the stream"})
        body = (
            "sys.stdin.read()\n"
            + "".join(f"print({line!r})\n" for line in lines)
            + "answer = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
            'open(answer, \'w\').write(\'{"verdict": "pass", "summary": "from the file"}\')\n'
        )
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        assert provider.invoke(invocation(workdir, sessions)).unwrap().summary == "from the file"

    def test_non_json_progress_lines_are_skipped(self, workdir: Path, sessions: Path) -> None:
        lines = codex_event_stream({"verdict": "pass", "summary": "done"})
        body = (
            "sys.stdin.read()\n"
            "print('thinking...')\n"
            "print('still working')\n" + "".join(f"print({line!r})\n" for line in lines)
        )
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        assert provider.invoke(invocation(workdir, sessions)).unwrap().summary == "done"

    def test_the_fallback_is_pinned_to_real_captured_codex_output(
        self, workdir: Path, sessions: Path
    ) -> None:
        """Verbatim event lines from a real authenticated `codex exec --json` run (0.146.0).

        Captured during AUTO-010 live validation and reproduced here byte-for-byte except for the
        agent message's own text, which carries the report. This is what turns the JSONL fallback
        from a plausible reading of the CLI's schema into a pinned one.

        It also demonstrates the defect this adapter was rewritten to fix: the **last** JSON object
        on stdout is `turn.completed`, not the report. AUTO-004's "take the last decodable object"
        parser would have handed that envelope to the report validator on every real run.
        """
        report = {"verdict": "pass", "summary": "captured", "findings": []}
        captured = [
            '{"type":"thread.started","thread_id":"019fb95d-453d-7552-81aa-9848affac44e"}',
            '{"type":"turn.started"}',
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "agent_message", "text": json.dumps(report)},
                }
            ),
            '{"type":"turn.completed","usage":{"input_tokens":13933,"cached_input_tokens":11008,'
            '"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}',
        ]
        assert json.loads(captured[-1])["type"] == "turn.completed"

        body = "sys.stdin.read()\n" + "".join(f"print({line!r})\n" for line in captured)
        provider = CodexCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        parsed = provider.invoke(invocation(workdir, sessions, role=ProviderRole.QA)).unwrap()

        assert parsed.verdict is ProviderVerdict.PASS
        assert parsed.summary == "captured"

    def test_stdout_with_no_agent_message_is_malformed_never_an_assumed_pass(
        self, workdir: Path, sessions: Path
    ) -> None:
        # Neither an answer file nor a final agent message: an error, never an assumed pass.
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
