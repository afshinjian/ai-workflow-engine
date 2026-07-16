"""Shared configuration models."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectSettings(StrictModel):
    id: str = Field(min_length=1)
    repository: Path
    default_branch: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    require_upstream: bool = False


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


class EngineConfig(StrictModel):
    project: ProjectSettings
    governance: GovernanceSettings
    handover: HandoverSettings
    protected_paths: ProtectedPathsSettings = Field(default_factory=ProtectedPathsSettings)
    workflow: WorkflowSettings = Field(default_factory=WorkflowSettings)

    @field_validator("workflow")
    @classmethod
    def milestone_one_is_read_only(cls, value: WorkflowSettings) -> WorkflowSettings:
        if value.allow_automatic_commit or value.allow_automatic_push:
            raise ValueError("Milestone 1 forbids automatic commit and push")
        return value
