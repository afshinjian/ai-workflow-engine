"""Event-sourced workflow-state models (Milestone 3, task T-302).

A workflow's state for one task is an append-only sequence of :class:`WorkflowEvent`s. Replaying
the sequence is the only source of truth; there is no separate mutable "current state" record.
See ``docs/milestone-3-plan.md`` for the normative contract.
"""

import re
import unicodedata
from typing import Literal

from pydantic import field_validator, model_validator

from ai_workflow_engine.models import StrictModel
from ai_workflow_engine.prompt.context import normalize_text
from ai_workflow_engine.prompt.models import WorkflowStage

StateAction = Literal["completed", "verdict"]
Verdict = Literal["APPROVED", "REJECTED"]

# The three stages that carry an APPROVED/REJECTED review verdict; every other stage is
# recorded as "completed". This mirrors the review-verdict template set in Milestone 2.
VERDICT_STAGES: frozenset[WorkflowStage] = frozenset(
    {"plan-review", "implementation-review", "governance-review"}
)

_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_HEX16_RE = re.compile(r"[0-9a-f]{16}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_HEAD_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def normalize_note(value: str) -> str:
    """Like the Milestone 2 text normalization, but an empty result is allowed.

    A note is optional free text; ``normalize_text`` rejects an empty result, so notes use this
    variant which applies the same NFC + whitespace-collapse + strip and simply permits ``""``.
    """
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("note must not contain a surrogate code point")
    normalized = unicodedata.normalize("NFC", value)
    collapsed: list[str] = []
    in_run = False
    for character in normalized:
        if character.isspace():
            if not in_run:
                collapsed.append(" ")
                in_run = True
        else:
            collapsed.append(character)
            in_run = False
    return "".join(collapsed).strip(" ")


class WorkflowEvent(StrictModel):
    schema_version: Literal["1.0"]
    project_id: str
    task_id: str
    sequence: int
    parent_digest: str | None
    stage: WorkflowStage
    action: StateAction
    verdict: Verdict | None
    prompt_id: str | None
    agent_run_id: str | None
    head: str
    note: str

    @field_validator("project_id")
    @classmethod
    def _validate_project_id(cls, value: str) -> str:
        if not _PROJECT_ID_RE.fullmatch(value):
            raise ValueError(f"project_id must match [A-Za-z0-9][A-Za-z0-9._-]*: {value!r}")
        return value

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, value: str) -> str:
        if normalize_text(value) != value:
            raise ValueError("task_id must already be in normalized form")
        return value

    @field_validator("sequence")
    @classmethod
    def _validate_sequence(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sequence must be a 1-based positive integer")
        return value

    @field_validator("parent_digest")
    @classmethod
    def _validate_parent_digest(cls, value: str | None) -> str | None:
        if value is not None and not _HEX64_RE.fullmatch(value):
            raise ValueError("parent_digest must be 64 lowercase hex characters or null")
        return value

    @field_validator("prompt_id", "agent_run_id")
    @classmethod
    def _validate_hex16(cls, value: str | None) -> str | None:
        if value is not None and not _HEX16_RE.fullmatch(value):
            raise ValueError("id must be 16 lowercase hex characters or null")
        return value

    @field_validator("head")
    @classmethod
    def _validate_head(cls, value: str) -> str:
        if not _HEAD_RE.fullmatch(value):
            raise ValueError("head must be a 40- or 64-character lowercase hex commit hash")
        return value

    @field_validator("note")
    @classmethod
    def _validate_note(cls, value: str) -> str:
        if normalize_note(value) != value:
            raise ValueError("note must already be in normalized form")
        return value

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "WorkflowEvent":
        is_verdict_stage = self.stage in VERDICT_STAGES
        if is_verdict_stage:
            if self.action != "verdict":
                raise ValueError(f"stage {self.stage!r} requires action 'verdict'")
            if self.verdict is None:
                raise ValueError(f"stage {self.stage!r} requires a non-null verdict")
        else:
            if self.action != "completed":
                raise ValueError(f"stage {self.stage!r} requires action 'completed'")
            if self.verdict is not None:
                raise ValueError(f"stage {self.stage!r} must not carry a verdict")
        if (self.parent_digest is None) != (self.sequence == 1):
            raise ValueError("parent_digest is null exactly when sequence == 1")
        return self


class WorkflowState(StrictModel):
    """Derived state: the full replayed history plus the computed next stage."""

    project_id: str
    task_id: str
    events: list[WorkflowEvent]
    next_stage: WorkflowStage | None
    terminal: bool
