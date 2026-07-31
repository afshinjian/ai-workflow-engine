"""The live provider-selection registry (`MODEL_PROVIDER_CONTRACTS.md` §4, §8).

**Live selection is the boundary that keeps `MockProvider` out of real workflows**
(`MVP_SCOPE.md` §3). `select_live_provider` maps a *role* to a provider and is typed to return a
`CLIProvider`; `MockProvider` subclasses `Provider` directly and is absent from the registry below,
so obtaining one from this path is type-impossible rather than merely unlikely. `mock` is imported
nowhere in this module or in `base`/`claude_cli`/`codex_cli` — only by tests and dry-run code that
construct one explicitly, by hand.

The default role assignment (Claude = implementation and repair, Codex = QA) lives in exactly one
place, the registry below, so §8's "adding a provider is additive" holds literally: a third CLI is
a new `CLIProvider` subclass plus one registry entry.

Extracted from this package's `__init__` in AUTO-010 so that `runtime` can select a provider
without importing the package that re-exports `runtime`. The registry, its typing, and its
behaviour are unchanged by the move.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import CLIProvider, ProviderRole
from agentos_workflow.providers.claude_cli import ClaudeCLIProvider
from agentos_workflow.providers.codex_cli import CodexCLIProvider

__all__ = ["live_provider_roles", "select_live_provider"]

# The complete set of providers reachable by a real authorized workflow. Typed to `CLIProvider`,
# which is what makes the `MockProvider` exclusion structural: adding a mock entry here would not
# type-check.
_LIVE_PROVIDER_FACTORIES: Mapping[ProviderRole, Callable[[WorkflowConfig], CLIProvider]] = (
    MappingProxyType(
        {
            ProviderRole.IMPLEMENTATION: ClaudeCLIProvider.from_config,
            ProviderRole.REPAIR: ClaudeCLIProvider.from_config,
            ProviderRole.QA: CodexCLIProvider.from_config,
        }
    )
)


def live_provider_roles() -> tuple[ProviderRole, ...]:
    """Every role a real authorized workflow can select a provider for."""
    return tuple(_LIVE_PROVIDER_FACTORIES)


def select_live_provider(role: ProviderRole, config: WorkflowConfig) -> CLIProvider:
    """Return the provider a real authorized workflow uses for `role`.

    A fresh instance per call, never a cached or shared one: two invocations in the same workflow
    must not share an in-process object (`MODEL_PROVIDER_CONTRACTS.md` §5). The instances are
    stateless anyway, so this costs nothing and removes the possibility that a future field on a
    provider quietly becomes cross-invocation state.

    Raises `KeyError` for an unknown role. That is deliberate and is the one place this package
    raises: an unmapped role is a programming error in the Orchestrator, not a workflow outcome a
    machine gate could sensibly branch on, and returning a typed failure would let it be logged
    and stepped over instead of fixed.
    """
    return _LIVE_PROVIDER_FACTORIES[role](config)
