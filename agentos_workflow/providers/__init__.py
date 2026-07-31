"""Model Providers (`MODEL_PROVIDER_CONTRACTS.md`) and the non-interactive Provider Runtime.

A Provider wraps exactly one local CLI executable, is invoked as a subprocess with a bounded
timeout, and returns a structured report to the calling Agent. It never authorizes a workflow,
never decides a machine-gate outcome, and never invokes a Skill (§1) — this package imports
neither the Skill families nor the Orchestrator, so those are unrepresentable rather than merely
forbidden. The interface, the shared subprocess primitive, and the report schema live in `base`;
each adapter contributes only its CLI's identity, argv shape, and stdout transport; the closed
permission and sandbox enums live in `config.policy`, where the configuration schema can reach
them without importing this package.

`runtime` (AUTO-010) is the public boundary above all of it::

    WorkflowService -> ProviderRuntime.invoke(...) -> ClaudeCLIProvider / CodexCLIProvider

`selection` holds the live role-to-provider registry that keeps `MockProvider` structurally out of
real workflows; both it and the runtime are re-exported here, so the package's public surface is
unchanged for callers that import from `agentos_workflow.providers` directly.
"""

from __future__ import annotations

from agentos_workflow.config.policy import ClaudePermissionMode, CodexSandboxMode
from agentos_workflow.providers.base import (
    MAX_PROVIDER_STDERR_BYTES,
    MAX_PROVIDER_STDOUT_BYTES,
    PROVEN_PRE_SIDE_EFFECT_RETRY_LIMIT,
    CLIProvider,
    Provider,
    ProviderExecution,
    ProviderFailure,
    ProviderFailureKind,
    ProviderInvocation,
    ProviderKind,
    ProviderReport,
    ProviderResult,
    ProviderRole,
    ProviderRunStatus,
    ProviderVerdict,
    build_provider_environment,
    provider_failure,
    provider_success,
    run_provider_process,
    strict_json_loads,
    unfenced,
)
from agentos_workflow.providers.claude_cli import ClaudeCLIProvider
from agentos_workflow.providers.codex_cli import CodexCLIProvider
from agentos_workflow.providers.runtime import (
    AUTO_MODE_PROMPT_CONTRACT,
    ProviderRunRequest,
    ProviderRunResult,
    ProviderRuntime,
    ProviderRuntimeTarget,
    build_provider_prompt,
)
from agentos_workflow.providers.selection import live_provider_roles, select_live_provider

__all__ = [
    "AUTO_MODE_PROMPT_CONTRACT",
    "MAX_PROVIDER_STDERR_BYTES",
    "MAX_PROVIDER_STDOUT_BYTES",
    "PROVEN_PRE_SIDE_EFFECT_RETRY_LIMIT",
    "CLIProvider",
    "ClaudeCLIProvider",
    "ClaudePermissionMode",
    "CodexCLIProvider",
    "CodexSandboxMode",
    "Provider",
    "ProviderExecution",
    "ProviderFailure",
    "ProviderFailureKind",
    "ProviderInvocation",
    "ProviderKind",
    "ProviderReport",
    "ProviderResult",
    "ProviderRole",
    "ProviderRunRequest",
    "ProviderRunResult",
    "ProviderRunStatus",
    "ProviderRuntime",
    "ProviderRuntimeTarget",
    "ProviderVerdict",
    "build_provider_environment",
    "build_provider_prompt",
    "live_provider_roles",
    "provider_failure",
    "provider_success",
    "run_provider_process",
    "select_live_provider",
    "strict_json_loads",
    "unfenced",
]
