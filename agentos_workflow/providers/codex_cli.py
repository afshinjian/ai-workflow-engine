"""`CodexCLIProvider` — the local Codex CLI adapter (`MODEL_PROVIDER_CONTRACTS.md` §3).

Role: default **independent QA** provider (invoked by `QAAgent`). Its input is the implementation
diff, the deterministic validation results, and the stage contract — never Claude's session state
or reasoning, only the resulting artifacts.

That independence is the point of the whole arrangement (`SECURITY_MODEL.md` §3): an
implementation session that has been manipulated — say by a prompt-injection attempt planted in
target-repository content — must not be able to reach the session that judges its work. This
adapter enforces its half structurally: it has no reference to the implementation provider, no
shared state with it, and its own isolated session directory per invocation. What crosses the
boundary is assembled by the Orchestrator/Agents from validated artifacts alone.
"""

from __future__ import annotations

from pathlib import Path

from agentos_workflow.config.policy import CodexSandboxMode
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import (
    CLIProvider,
    ProviderKind,
    strict_json_loads,
    unfenced,
)

__all__ = ["LAST_MESSAGE_FILENAME", "CodexCLIProvider", "CodexSandboxMode"]

#: Where the engine tells Codex to write the agent's final message. Lives inside this invocation's
#: own session directory, so two concurrent invocations can never read each other's answer.
LAST_MESSAGE_FILENAME = "codex-last-message.txt"


class CodexCLIProvider(CLIProvider):
    """Wraps the configured Codex CLI executable.

    As with the Claude adapter, argv is a fixed provider-owned constant plus one configured mode,
    and the prompt travels on stdin.

    **The flags below are verified against the installed CLI in AUTO-010**, not assumed from
    documentation. `codex exec --help` (codex-cli 0.146.0) documents: the subcommand itself as "Run
    Codex non-interactively"; `[PROMPT]` as "If not provided as an argument (or if `-` is used),
    instructions are read from stdin"; `--json` as "Print events to stdout as JSONL";
    `-s/--sandbox` with the three values above; and `-o/--output-last-message <FILE>` as
    "Specifies file where the last message from the agent should be written". A live invocation
    confirmed the event grammar (`thread.started`, `turn.started`, `error`, `turn.failed`), that
    the prompt is in fact read from stdin, and that a failed turn exits 1 rather than waiting.

    `codex exec` has no `--ask-for-approval` flag at all — approval prompting belongs to the
    interactive `codex` command — so non-interactivity is a property of the subcommand rather than
    something this adapter has to switch off. The explicit `approval_policy="never"` override is
    kept anyway as defence in depth: it costs nothing, and it means a future default that
    reintroduces prompting cannot silently reach this engine.
    """

    _ARGV_SUFFIX = ("exec", "--json")

    def __init__(
        self,
        *,
        executable: Path,
        timeout_seconds: int,
        allowed_environment_variables: tuple[str, ...] = (),
        sandbox_mode: CodexSandboxMode = CodexSandboxMode.READ_ONLY,
    ) -> None:
        super().__init__(
            executable=executable,
            timeout_seconds=timeout_seconds,
            allowed_environment_variables=allowed_environment_variables,
        )
        self._sandbox_mode = sandbox_mode

    @property
    def sandbox_mode(self) -> CodexSandboxMode:
        return self._sandbox_mode

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.CODEX_CLI

    def _argv_suffix(self, session_directory: Path) -> tuple[str, ...]:
        """Non-interactive exec, JSONL events, an explicit sandbox, and an engine-named answer file.

        Every element is a provider-owned constant, a value from `CodexSandboxMode`, or a path this
        engine constructed. Nothing here is caller-supplied, and the `-c` override carries a single
        fixed key/value pair rather than being a general configuration channel.
        """
        return (
            *self._ARGV_SUFFIX,
            "--sandbox",
            self._sandbox_mode.value,
            "-c",
            'approval_policy="never"',
            "--output-last-message",
            str(session_directory / LAST_MESSAGE_FILENAME),
        )

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> CodexCLIProvider:
        """Build the provider from a target repository's configuration.

        Reads the `codex_cli_*` fields, never the `claude_cli_*` ones — each provider is bound to
        its own executable, its own timeout, and its own policy, so a slow QA CLI cannot borrow the
        implementation CLI's budget and neither can borrow the other's permissions.
        """
        return cls(
            executable=Path(config.codex_cli_executable),
            timeout_seconds=config.codex_cli_timeout_seconds,
            allowed_environment_variables=tuple(config.allowed_environment_variables),
            sandbox_mode=config.codex_cli_sandbox_mode,
        )

    def _extract_report_payload(self, stdout: str, session_directory: Path) -> object:
        """Read the report from the agent's final message.

        **The engine-named answer file is the primary channel.** `--output-last-message` makes the
        CLI write its final message to a path this engine chose, which is decisively better than
        recovering that message from the event stream: the stream's envelope schema is the CLI's
        own and may change between versions, whereas "the last message, in this file" is a
        documented promise about content. Reading it also cannot mistake a progress event for the
        answer.

        The JSONL fallback exists for the case where the file is absent or empty but the stream did
        carry a final agent message. It is deliberately narrow — it accepts only an event whose
        `item` is an `agent_message` — and it is **not verified against a successful live run**
        (AUTO-010 could not authenticate the installed Codex CLI; see the completion report's
        deferred item). It never guesses: an stdout with no such event and no answer file is an
        error, never an assumed pass.
        """
        answer = _read_answer_file(session_directory / LAST_MESSAGE_FILENAME)
        if answer is None:
            answer = _last_agent_message(stdout)
        if answer is None:
            raise ValueError(
                "codex produced neither an answer file nor a final agent message on stdout"
            )
        return strict_json_loads(unfenced(answer))


def _read_answer_file(path: Path) -> str | None:
    """The final message Codex was told to write, or `None` if it wrote nothing there."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # Absent or unreadable. Not fatal on its own: the stream fallback may still hold the
        # answer, and if it does not, the caller raises with that fact rather than this one.
        return None
    return text if text.strip() else None


def _last_agent_message(stdout: str) -> str | None:
    """The text of the last `agent_message` item in a JSONL event stream, if there is one.

    Lines that do not decode are skipped rather than fatal — a CLI is entitled to write
    human-readable progress alongside its events — and non-message events are ignored rather than
    treated as candidates, which is what keeps a progress event from being read as the verdict.
    """
    latest: str | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = strict_json_loads(stripped)
        except ValueError:
            continue
        if not isinstance(decoded, dict):
            continue
        item = decoded.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            latest = text
    return latest
