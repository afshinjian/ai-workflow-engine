"""Strict schemas for non-interactive agent output (Milestone 3, task T-303).

An agent is handed a governed prompt on stdin and must emit exactly one JSON object matching
:class:`AgentReport`. The strict models here reject unknown fields and malformed values so an
agent cannot smuggle unstructured output past the engine. The binding cross-checks against the
governing prompt (task/stage/prompt-id equality, mode-specific ``changed_paths`` rules) and the
independent claim verification are the runner's job (T-304/T-305), not these models'. See
``docs/milestone-3-plan.md``.
"""

import re
from typing import Literal

from pydantic import field_validator

from ai_workflow_engine.models import StrictModel, WorkflowStage
from ai_workflow_engine.workflow.events import Verdict

_HEX16_RE = re.compile(r"[0-9a-f]{16}")


class AgentFinding(StrictModel):
    code: str
    message: str
    severity: Literal["blocking", "non-blocking"]
    path: str | None

    @field_validator("code")
    @classmethod
    def _code_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("finding code must be non-empty")
        return value


class AgentReport(StrictModel):
    schema_version: Literal["1.0"]
    task_id: str
    stage: WorkflowStage
    prompt_id: str
    verdict: Verdict | None
    summary: str
    findings: list[AgentFinding]
    changed_paths: list[str]
    verification_commands_run: list[str]
    blockers: list[str]

    @field_validator("prompt_id")
    @classmethod
    def _validate_prompt_id(cls, value: str) -> str:
        if not _HEX16_RE.fullmatch(value):
            raise ValueError("prompt_id must be 16 lowercase hex characters")
        return value

    @field_validator("changed_paths")
    @classmethod
    def _changed_paths_sorted_unique(cls, value: list[str]) -> list[str]:
        if any(not path for path in value):
            raise ValueError("changed_paths must not contain empty strings")
        if value != sorted(value):
            raise ValueError("changed_paths must be sorted")
        if len(set(value)) != len(value):
            raise ValueError("changed_paths must be unique")
        return value
