"""`MockProvider` — the deterministic, offline provider substitute
(`MODEL_PROVIDER_CONTRACTS.md` §4).

Purpose: let every Orchestrator state transition and machine gate be exercised without invoking a
real model CLI or making a network call — in the engine's own test suite (`TEST_STRATEGY.md`) and
in dry runs.

**Structurally excluded from real workflows** (`MVP_SCOPE.md` §3, `MODEL_PROVIDER_CONTRACTS.md`
§4). Three independent properties enforce that, none of them a comment asking a caller to behave:

1. It subclasses `Provider` directly, **not** `CLIProvider`. Live selection
   (`providers.select_live_provider`) is typed to return a `CLIProvider`, so returning a
   `MockProvider` from it is a type error, not a policy violation — mypy rejects it before any
   test runs.
2. It is absent from the live selection registry entirely, so there is no role, no configuration
   value, and no string a target repository could set that would cause one to be constructed.
3. Neither this module nor the live registry is imported by `base`, `claude_cli`, or `codex_cli`,
   so no live code path can even name it. `test_providers_isolation.py` asserts this over the
   modules' own source.

It also has no `from_config` constructor, unlike the two CLI providers: a `MockProvider` cannot be
built from a target repository's configuration at all. Every instance is constructed explicitly,
in test or dry-run code, with its canned answers passed in by hand.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from agentos_workflow.providers.base import (
    Provider,
    ProviderInvocation,
    ProviderKind,
    ProviderReport,
    ProviderResult,
    ProviderRole,
    ProviderVerdict,
    provider_success,
)

__all__ = ["MockProvider", "canned_report"]


def canned_report(
    *,
    role: ProviderRole,
    verdict: ProviderVerdict = ProviderVerdict.PASS,
    summary: str = "canned report",
    files_changed: Iterable[str] = (),
    validation_performed: Iterable[str] = (),
    recommended_commit_message: str | None = None,
    findings: Iterable[str] = (),
) -> ProviderReport:
    """Build a canned `ProviderReport` attributed to `MockProvider`.

    The `provider` field is always `ProviderKind.MOCK` and cannot be overridden: a canned report
    that claimed to come from a real CLI would let a mocked run be mistaken for a real one in an
    audit record, which is the one thing a test double must never be able to do.
    """
    return ProviderReport(
        provider=ProviderKind.MOCK,
        role=role,
        verdict=verdict,
        summary=summary,
        files_changed=tuple(files_changed),
        validation_performed=tuple(validation_performed),
        recommended_commit_message=recommended_commit_message,
        findings=tuple(findings),
    )


class MockProvider(Provider):
    """A `Provider` that returns configured results instead of running anything.

    Drop-in for either CLI provider: a caller typed against `Provider` sees the identical
    `invoke(invocation) -> ProviderResult` surface, so the same Orchestrator code path drives a
    mocked run and a real one. It spawns no process, reads no environment, and creates no
    directory — there is no subprocess call anywhere in this module.

    Results are returned in order and the last one repeats once the queue is exhausted, which is
    what makes a repair loop testable: queue a `fail` then a `pass` to drive exactly one repair
    cycle, or queue a single `fail` to drive the loop to its attempt limit.
    """

    def __init__(self, results: Iterable[ProviderResult] | None = None) -> None:
        queued = list(results or ())
        if not queued:
            queued = [provider_success(canned_report(role=ProviderRole.IMPLEMENTATION))]
        self._results: deque[ProviderResult] = deque(queued)
        self._invocations: list[ProviderInvocation] = []

    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.MOCK

    @property
    def invocations(self) -> tuple[ProviderInvocation, ...]:
        """Every invocation this instance received, in order — for test assertions.

        Per-instance, never shared or class-level: two `MockProvider`s in one workflow record
        their own invocations and can never observe each other's, matching the isolation the CLI
        providers get from separate processes (`MODEL_PROVIDER_CONTRACTS.md` §5).
        """
        return tuple(self._invocations)

    def invoke(self, invocation: ProviderInvocation) -> ProviderResult:
        """Return the next configured result. Never raises, exactly like a real Provider."""
        self._invocations.append(invocation)
        if len(self._results) > 1:
            return self._results.popleft()
        return self._results[0]
