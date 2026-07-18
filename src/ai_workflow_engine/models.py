"""Shared configuration models."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The seven fixed workflow stages. Defined here (the foundational module) so both the
# configuration models below and the prompt package can share one definition without a circular
# import; `ai_workflow_engine.prompt.models` re-exports it.
WorkflowStage = Literal[
    "plan-review",
    "implementation",
    "implementation-review",
    "remediation",
    "governance-closeout",
    "governance-review",
    "push",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectSettings(StrictModel):
    id: str = Field(min_length=1)
    repository: Path
    default_branch: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    require_upstream: bool = False
    conda_environment: str = Field(min_length=1)

    @field_validator("conda_environment")
    @classmethod
    def conda_environment_not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("project.conda_environment must not be empty or whitespace-only")
        return value


class FactRule(StrictModel):
    name: str = Field(min_length=1)
    paths: list[str] = Field(min_length=2)
    pattern: str = Field(min_length=1)
    group: int | str = 1
    required: bool = False


class GovernanceSettings(StrictModel):
    project_state: str
    task_queue: str
    current_task: str
    remaining_tasks: str
    context: str
    pyproject: str
    facts: list[FactRule] = Field(default_factory=list)

    def document_paths(self) -> list[str]:
        return [
            self.project_state,
            self.task_queue,
            self.current_task,
            self.remaining_tasks,
            self.context,
        ]


class HandoverSettings(StrictModel):
    manifest: str
    files: list[str] = Field(min_length=1)


class ProtectedPathsSettings(StrictModel):
    never_stage: list[str] = Field(default_factory=list)
    never_commit: list[str] = Field(default_factory=list)


class WorkflowSettings(StrictModel):
    maximum_current_tasks: int = Field(ge=0, default=1)
    require_designer_approval_for_promotion: bool = True
    allow_automatic_commit: bool = False
    allow_automatic_push: bool = False


_AGENT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,63}")

# Which stages each agent mode may be assigned. `push` is intentionally in neither set, so no
# agent of any mode can be bound to it (agent execution of `push` is forbidden in Milestone 3).
_READ_ONLY_STAGES: frozenset[str] = frozenset(
    {"plan-review", "implementation-review", "governance-closeout", "governance-review"}
)
_SCOPED_WRITE_STAGES: frozenset[str] = frozenset({"implementation", "remediation"})


class AgentSettings(StrictModel):
    """One configured non-interactive agent (Milestone 3). Execution is added in a later task."""

    name: str
    executable: Path
    args: list[str] = Field(default_factory=list)
    mode: Literal["read-only", "scoped-write"]
    timeout_seconds: int = Field(ge=1, le=86400)
    stages: list[WorkflowStage] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _AGENT_NAME_RE.fullmatch(value):
            raise ValueError("agent name must match [A-Za-z][A-Za-z0-9._-]{0,63}")
        return value

    @field_validator("executable")
    @classmethod
    def _validate_executable_absolute(cls, value: Path) -> Path:
        # Existence is a run-time concern; the config only requires an absolute path (no PATH
        # lookup), matching how repository paths defer existence checks to use time.
        if not value.is_absolute():
            raise ValueError("agent executable must be an absolute path")
        return value

    @model_validator(mode="after")
    def _validate_stages(self) -> "AgentSettings":
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("agent stages must be unique")
        allowed = _READ_ONLY_STAGES if self.mode == "read-only" else _SCOPED_WRITE_STAGES
        invalid = [stage for stage in self.stages if stage not in allowed]
        if invalid:
            raise ValueError(f"stages {invalid} are not permitted for a {self.mode} agent")
        return self


class EngineConfig(StrictModel):
    project: ProjectSettings
    governance: GovernanceSettings
    handover: HandoverSettings
    protected_paths: ProtectedPathsSettings = Field(default_factory=ProtectedPathsSettings)
    workflow: WorkflowSettings = Field(default_factory=WorkflowSettings)
    agents: list[AgentSettings] = Field(default_factory=list)

    @field_validator("workflow")
    @classmethod
    def no_automatic_commit_or_push(cls, value: WorkflowSettings) -> WorkflowSettings:
        if value.allow_automatic_commit or value.allow_automatic_push:
            raise ValueError(
                "config-level automatic commit and push are forbidden; commits and pushes go "
                "only through the approval-gated Milestone 4 commands"
            )
        return value

    @field_validator("agents")
    @classmethod
    def _unique_agent_names(cls, value: list[AgentSettings]) -> list[AgentSettings]:
        names = [agent.name for agent in value]
        if len(set(names)) != len(names):
            raise ValueError("agent names must be unique across the agents list")
        return value
