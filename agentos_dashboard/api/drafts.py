"""EP-23 (`API_SPEC.md` §3): local drafts — approvals, findings, notes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agentos_dashboard.services.approvals import Approval, ApprovalLayer, ApprovalVerdict
from agentos_dashboard.services.findings import Finding, FindingSeverity
from agentos_dashboard.services.notes import UserNote

__all__ = [
    "CreateApprovalRequest",
    "CreateFindingRequest",
    "CreateNoteRequest",
    "approval_to_json",
    "finding_to_json",
    "note_to_json",
]


class CreateApprovalRequest(BaseModel):
    """`POST /dash/api/v1/approvals`'s body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_token: UUID
    layer: ApprovalLayer
    verdict: ApprovalVerdict
    run_uuid: UUID | None = None
    target_hash: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    target_commit: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=5000)


class CreateFindingRequest(BaseModel):
    """`POST /dash/api/v1/findings`'s body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_token: UUID
    severity: FindingSeverity
    text: str = Field(min_length=1, max_length=5000)
    run_uuid: UUID | None = None
    disposition: str | None = Field(default=None, max_length=500)


class CreateNoteRequest(BaseModel):
    """`POST /dash/api/v1/notes`'s body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_token: UUID
    target_ref: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=5000)


def approval_to_json(approval: Approval) -> dict[str, Any]:
    return {
        "uuid": approval.uuid,
        "run_uuid": approval.run_uuid,
        "layer": approval.layer.value,
        "verdict": approval.verdict.value,
        "target_hash": approval.target_hash,
        "target_commit": approval.target_commit,
        "target_commit_resolved": approval.target_commit_resolved,
        "reconciled": approval.reconciled,
        "reconciliation_scope": "LOCAL draft; no authoritative approval inferred",
        "notes": approval.notes,
        "created_at": approval.created_at,
    }


def finding_to_json(finding: Finding) -> dict[str, Any]:
    return {
        "uuid": finding.uuid,
        "run_uuid": finding.run_uuid,
        "severity": finding.severity.value,
        "text": finding.text,
        "disposition": finding.disposition,
        "created_at": finding.created_at,
    }


def note_to_json(note: UserNote) -> dict[str, Any]:
    return {
        "uuid": note.uuid,
        "target_ref": note.target_ref,
        "text": note.text,
        "created_at": note.created_at,
    }
