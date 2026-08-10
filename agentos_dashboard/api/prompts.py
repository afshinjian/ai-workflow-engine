"""EP-14/EP-21 (`API_SPEC.md` §2-3): gated prompt generation and export (PG-04)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from agentos_dashboard.api.stages import precondition_report_to_json
from agentos_dashboard.services.prompts import GeneratedPromptRecord
from agentos_dashboard.services.stages import PreconditionReport

__all__ = [
    "GeneratePromptRequest",
    "generated_prompt_to_json",
    "precondition_report_to_json",
    "unmet_precondition_message",
]


class GeneratePromptRequest(BaseModel):
    """`POST /dash/api/v1/prompts/generate`'s body (EP-21)."""

    stage_id: str = Field(min_length=1, max_length=32)
    client_token: UUID


def generated_prompt_to_json(record: GeneratedPromptRecord) -> dict[str, Any]:
    return {
        "prompt_uuid": record.prompt_uuid,
        "stage_id": record.stage_id,
        "template_version": record.template_version,
        "generated_at": record.generated_at,
        "sha256": record.sha256,
        "markdown": record.markdown,
        "filename": record.filename,
    }


def unmet_precondition_message(report: PreconditionReport) -> str:
    """The itemized unmet-precondition text `API_SPEC.md` §5 requires in a 422 body."""
    return "; ".join(f"{result.name}: {result.detail}" for result in report.unmet)
