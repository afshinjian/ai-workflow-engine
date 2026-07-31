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

from pathlib import Path

from agentos_workflow.config.policy import ClaudePermissionMode
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import (
    CLIProvider,
    ProviderKind,
    strict_json_loads,
    unfenced,
)

__all__ = ["ClaudeCLIProvider", "ClaudePermissionMode"]


class ClaudeCLIProvider(CLIProvider):
    """Wraps the configured Claude Code CLI executable.

    The argv shape is fixed and provider-owned: non-interactive print mode, JSON output, and one
    explicit permission mode drawn from `ClaudePermissionMode`. No call site can add a flag, so no
    Agent can quietly widen the CLI's permissions or turn off the structured output this adapter
    depends on. The prompt travels on stdin (`base.run_provider_process`), never in argv.

    **The flags below are verified against the installed CLI in AUTO-010**, not assumed from
    documentation: `claude --help` for version 2.1.220 documents `-p, --print` ("Print response and
    exit"), `--output-format` with choice `json` ("only works with --print"), and
    `--permission-mode` with exactly the six choices the enum above selects from.
    """

    _ARGV_SUFFIX = ("--print", "--output-format", "json")

    def __init__(
        self,
        *,
        executable: Path,
        timeout_seconds: int,
        allowed_environment_variables: tuple[str, ...] = (),
        permission_mode: ClaudePermissionMode = ClaudePermissionMode.PLAN,
    ) -> None:
        super().__init__(
            executable=executable,
            timeout_seconds=timeout_seconds,
            allowed_environment_variables=allowed_environment_variables,
        )
        self._permission_mode = permission_mode

    @property
    def permission_mode(self) -> ClaudePermissionMode:
        return self._permission_mode

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.CLAUDE_CLI

    def _argv_suffix(self, session_directory: Path) -> tuple[str, ...]:
        """Print mode, JSON output, and an explicit permission mode — nothing else.

        The mode is passed on every invocation rather than left to the CLI's default. A default is
        whatever the operator's own settings file happens to say, which is exactly the kind of
        ambient state an audited engine must not execute under: the recorded argv has to state the
        policy the run actually used.
        """
        return (*self._ARGV_SUFFIX, "--permission-mode", self._permission_mode.value)

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> ClaudeCLIProvider:
        """Build the provider from a target repository's configuration (`CONFIGURATION_MODEL.md`).

        The executable path, the timeout, the environment allowlist, and the permission mode all
        come from the target repository's own configuration. None has a global default here: a
        missing or wrong value is a configuration error the loader already rejects, never
        something this adapter fills in.
        """
        return cls(
            executable=Path(config.claude_cli_executable),
            timeout_seconds=config.claude_cli_timeout_seconds,
            allowed_environment_variables=tuple(config.allowed_environment_variables),
            permission_mode=config.claude_cli_permission_mode,
        )

    def _extract_report_payload(self, stdout: str, session_directory: Path) -> object:
        """Unwrap the CLI's result envelope, then read the report from it.

        `--output-format json` emits an envelope object describing the session, with the model's
        actual answer in a string `result` field; the report we want is that answer. Handling the
        envelope here rather than in the shared parser keeps the report schema itself identical
        across providers — this hook adapts one CLI's transport, not the contract.

        A bare report object (no envelope) is accepted unchanged, so the adapter still works
        against the plain stdout protocol `base` documents.
        """
        payload = strict_json_loads(stdout)
        if isinstance(payload, dict) and isinstance(payload.get("result"), str):
            return strict_json_loads(unfenced(payload["result"]))
        return payload
