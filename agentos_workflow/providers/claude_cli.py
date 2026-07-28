"""`ClaudeCLIProvider` — the local Claude Code CLI adapter (`MODEL_PROVIDER_CONTRACTS.md` §2).

Role: default **implementation** provider (invoked by `ImplementationAgent` for the initial stage
implementation) and default **repair** provider (invoked during `REPAIRING`, given the latest
structured QA report). Both roles are the same adapter — the difference is entirely in the prompt
the Agent assembles, which is why this class has no role-specific branch.

Nothing here decides whether an implementation is acceptable. The report this adapter returns is
evidence for the Orchestrator's own deterministic validation, never a substitute for it
(`MODEL_PROVIDER_CONTRACTS.md` §1).
"""

from __future__ import annotations

import json
from pathlib import Path

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import CLIProvider, ProviderKind

__all__ = ["ClaudeCLIProvider"]


class ClaudeCLIProvider(CLIProvider):
    """Wraps the configured Claude Code CLI executable.

    The argv shape is fixed and provider-owned: non-interactive print mode with JSON output. No
    call site can add a flag, so no Agent can quietly widen the CLI's permissions or turn off the
    structured output this adapter depends on. The prompt travels on stdin
    (`base.run_provider_process`), never in argv.

    **The exact flags are confirmed against a live CLI in AUTO-007, not here.** This stage's tests
    mock the process boundary by contract, so they prove the adapter's behavior — timeout,
    environment allowlist, isolation, parsing, classification — without asserting that any
    particular real executable accepts these arguments.
    """

    _ARGV_SUFFIX = ("--print", "--output-format", "json")

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.CLAUDE_CLI

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> ClaudeCLIProvider:
        """Build the provider from a target repository's configuration (`CONFIGURATION_MODEL.md`).

        The executable path, the timeout, and the environment allowlist all come from the target
        repository's own configuration. None of the three has a global default here: a missing or
        wrong value is a configuration error the loader already rejects, never something this
        adapter fills in.
        """
        return cls(
            executable=Path(config.claude_cli_executable),
            timeout_seconds=config.claude_cli_timeout_seconds,
            allowed_environment_variables=tuple(config.allowed_environment_variables),
        )

    def _extract_report_payload(self, stdout: str) -> object:
        """Unwrap the CLI's result envelope, then read the report from it.

        `--output-format json` emits an envelope object describing the session, with the model's
        actual answer in a string `result` field; the report we want is that answer. Handling the
        envelope here rather than in the shared parser keeps the report schema itself identical
        across providers — this hook adapts one CLI's transport, not the contract.

        A bare report object (no envelope) is accepted unchanged, so the adapter still works
        against the plain stdout protocol `base` documents.
        """
        payload = json.loads(stdout)
        if isinstance(payload, dict) and isinstance(payload.get("result"), str):
            return json.loads(payload["result"])
        return payload
