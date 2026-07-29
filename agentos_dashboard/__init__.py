"""AgentOS Dashboard — a local, read-only-first governance dashboard.

A separate top-level package (`docs/agentos-dashboard/ARCHITECTURE.md` §1, DD-01 Option 2): it
lives beside the `ai-workflow-engine` engine package but imports nothing from it and changes
nothing in it. The engine's own audited test collection (`pytest` with `testpaths=["tests"]`)
must stay provably unchanged, so dashboard tests live in `agentos_dashboard/tests/` and run
under an explicit path (`TEST_STRATEGY.md` §1).

DASH-002 delivers only the two repository adapters and the snapshot builder
(`agentos_dashboard/core/`). HTTP, parsing semantics, and persistence belong to later stages.
"""

from __future__ import annotations

__all__ = ["__version__"]

# The dashboard versions independently of the engine's `pyproject.toml` version fact, which
# `workflowctl check-governance` owns; nothing here participates in that check.
__version__ = "0.1.0"
