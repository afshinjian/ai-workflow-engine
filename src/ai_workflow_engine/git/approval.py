"""Human approval artifacts for controlled commit and push (Milestone 4, task T-402).

A commit or push is authorized by a strict YAML file a human writes and passes with
``--approval``. The artifact pins exactly what is authorized (branch, HEAD, path set, message);
there is no signature/crypto — it is a local-operator control, and the gate records the file's
SHA-256 and ``approved_by`` in its audit trail. See ``docs/milestone-4-plan.md``.
"""

import hashlib
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError, field_validator

from ai_workflow_engine.models import StrictModel

_HEX_REF_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class ApprovalError(ValueError):
    """A malformed, unreadable, or protected-path-violating approval artifact."""

    code = "approval_error"


class CommitApproval(StrictModel):
    kind: Literal["commit"]
    task_id: str
    branch: str
    head: str
    allowed_paths: list[str]
    message: str
    approved_by: str

    @field_validator("head")
    @classmethod
    def _validate_head(cls, value: str) -> str:
        if not _HEX_REF_RE.fullmatch(value):
            raise ValueError("head must be a 40- or 64-character lowercase hex commit hash")
        return value

    @field_validator("branch", "task_id", "approved_by")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be non-empty")
        return value


class PushApproval(StrictModel):
    kind: Literal["push"]
    task_id: str
    branch: str
    head: str
    upstream: str
    approved_by: str

    @field_validator("head")
    @classmethod
    def _validate_head(cls, value: str) -> str:
        if not _HEX_REF_RE.fullmatch(value):
            raise ValueError("head must be a 40- or 64-character lowercase hex commit hash")
        return value

    @field_validator("branch", "task_id", "upstream", "approved_by")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be non-empty")
        return value


def approval_digest(path: Path) -> str:
    """The SHA-256 of the approval file's exact bytes, for the audit trail."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_raw(path: Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ApprovalError(f"Cannot read approval artifact {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ApprovalError("Approval artifact must be a YAML mapping")
    return raw


def load_commit_approval(path: Path) -> CommitApproval:
    raw = _load_raw(path)
    if raw.get("kind") != "commit":
        raise ApprovalError(f"Expected a commit approval, got kind={raw.get('kind')!r}")
    try:
        return CommitApproval.model_validate(raw)
    except ValidationError as exc:
        raise ApprovalError(f"Invalid commit approval: {exc}") from exc


def load_push_approval(path: Path) -> PushApproval:
    raw = _load_raw(path)
    if raw.get("kind") != "push":
        raise ApprovalError(f"Expected a push approval, got kind={raw.get('kind')!r}")
    try:
        return PushApproval.model_validate(raw)
    except ValidationError as exc:
        raise ApprovalError(f"Invalid push approval: {exc}") from exc
