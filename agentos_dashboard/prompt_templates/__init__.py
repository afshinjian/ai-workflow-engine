"""EN-12 `PromptTemplate` support: the coded DASH stage schema and the runtime placeholder
grammar (`DASH-007.md`), independent of and never importing the engine's own prompt subsystem
(`src/ai_workflow_engine/prompt/`), which renders the *engine's* seven workflow-stage prompts for
a governed target repository — a different subsystem for a different document set entirely.
"""

from __future__ import annotations

from agentos_dashboard.prompt_templates.placeholders import PLACEHOLDER_NAMES, substitute
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA, STAGE_SCHEMA_BY_ID, StageSchema

__all__ = [
    "PLACEHOLDER_NAMES",
    "STAGE_SCHEMA",
    "STAGE_SCHEMA_BY_ID",
    "StageSchema",
    "substitute",
]
