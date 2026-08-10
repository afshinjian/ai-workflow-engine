"""EP-15/EP-22 (`API_SPEC.md` §2-3): run records (PG-05)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agentos_dashboard.services.runs import (
    StageRunView,
    ValidationEntry,
    ValidationEntryInput,
    ValidationResult,
)

__all__ = [
    "CreateRunRequest",
    "ValidationEntryRequest",
    "run_view_to_json",
    "validation_entry_to_json",
]


class ValidationEntryRequest(BaseModel):
    """One `POST /runs` validation-matrix line (DR-070)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    command: str = Field(min_length=1, max_length=500)
    result: ValidationResult
    origin: str = Field(min_length=1, max_length=100)
    counts: dict[str, int] | None = None

    def to_input(self) -> ValidationEntryInput:
        return ValidationEntryInput(
            command=self.command, result=self.result, origin=self.origin, counts=self.counts
        )


class CreateRunRequest(BaseModel):
    """`POST /dash/api/v1/runs`'s body (EP-22)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_token: UUID
    stage_id: str = Field(min_length=1, max_length=32)
    tool: str = Field(min_length=1, max_length=100)
    started_at: str = Field(min_length=1, max_length=64)
    reported_result: str = Field(min_length=1, max_length=2000)
    ended_at: str | None = Field(default=None, max_length=64)
    prompt_hash: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    report_path: str | None = Field(default=None, max_length=1000)
    validation: list[ValidationEntryRequest] = Field(default_factory=list, max_length=200)
    validation_summary: str | None = Field(default=None, max_length=5000)
    findings_text: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)
    external_reference: str | None = Field(default=None, max_length=500)


def validation_entry_to_json(entry: ValidationEntry) -> dict[str, Any]:
    return {
        "uuid": entry.uuid,
        "run_uuid": entry.run_uuid,
        "command": entry.command,
        "result": entry.result.value,
        "origin": entry.origin,
        "counts": entry.counts,
        "recorded_at": entry.recorded_at,
    }


def run_view_to_json(view: StageRunView) -> dict[str, Any]:
    return {
        "uuid": view.uuid,
        "stage_id": view.stage_id,
        "prompt_hash": view.prompt_hash,
        "tool": view.tool,
        "started_at": view.started_at,
        "ended_at": view.ended_at,
        "reported_result": view.reported_result,
        "report_path": view.report_path,
        "report_path_verified": view.report_path_verified,
        "report_size_bytes": view.report_size_bytes,
        "report_sha256": view.report_sha256,
        "report_hash_verified": view.report_hash_verified,
        "validation_summary": view.validation_summary,
        "findings_text": view.findings_text,
        "notes": view.notes,
        "external_reference": view.external_reference,
        "created_at": view.created_at,
        "validation_entries": [validation_entry_to_json(e) for e in view.validation_entries],
    }
