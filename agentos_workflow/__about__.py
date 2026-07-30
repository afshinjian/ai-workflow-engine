"""The `agentos_workflow` engine's own version (AUTO-008).

This value is deliberately **not** derived from the `ai-workflow-engine` distribution version.
`HUMAN_AUTHORIZATION_MODEL.md` §2 item 11 binds the workflow engine version into every
authorization, and §4 makes a later mismatch an authorization invalidator that moves the workflow
to `FAILED`. Reading the *distribution* version made those two facts collide: `pyproject.toml`
declares one version for the whole repository, so bumping the legacy `src/ai_workflow_engine/`
engine — a package this one neither imports nor depends on — silently invalidated every
in-flight `agentos_workflow` authorization and forced a re-authorization from `CREATED`.

Two independently-versioned subsystems must not share one version number. This module is the
single source of truth for *this* engine's version; `observation.local.running_engine_version`
reads it and nothing else.

Bumping this value is therefore a deliberate act with a defined consequence: every persisted
authorization captured under the previous value becomes invalid on its next resume. That is the
intended `HUMAN_AUTHORIZATION_MODEL.md` §4 behaviour when the engine driving a workflow genuinely
changes — it is not something a release of an unrelated package should be able to trigger.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
