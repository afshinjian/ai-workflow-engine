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

import json
from pathlib import Path

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import CLIProvider, ProviderKind

__all__ = ["CodexCLIProvider"]


class CodexCLIProvider(CLIProvider):
    """Wraps the configured Codex CLI executable.

    As with the Claude adapter, argv is a fixed provider-owned constant and the prompt travels on
    stdin. **The exact flags are confirmed against a live CLI in AUTO-007, not here.**
    """

    _ARGV_SUFFIX = ("exec", "--json")

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.CODEX_CLI

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> CodexCLIProvider:
        """Build the provider from a target repository's configuration.

        Reads the `codex_cli_*` fields, never the `claude_cli_*` ones — each provider is bound to
        its own executable and its own timeout, so a slow QA CLI cannot borrow the implementation
        CLI's budget.
        """
        return cls(
            executable=Path(config.codex_cli_executable),
            timeout_seconds=config.codex_cli_timeout_seconds,
            allowed_environment_variables=tuple(config.allowed_environment_variables),
        )

    def _extract_report_payload(self, stdout: str) -> object:
        """Read the report from a single JSON object or from a JSON Lines event stream.

        `--json` emits one JSON object per line as the run progresses, the last of which carries
        the final answer; a single-object stdout is the degenerate one-line case of the same
        thing. Taking the **last** decodable object is what makes this correct in both shapes:
        earlier lines are progress events, and treating one of those as the verdict would report
        on an unfinished run.

        Lines that do not decode are skipped rather than fatal — a CLI is entitled to write
        human-readable progress alongside its events — but an stdout with no decodable object at
        all is an error, never an assumed pass.
        """
        candidate: object | None = None
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                candidate = decoded
        if candidate is None:
            raise ValueError("stdout contained no JSON object")
        return candidate
