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
    # Stage registries (e.g. each program's STAGE_REGISTRY.md) whose per-stage lifecycle State
    # is cross-checked against the task queue by `check-registries`. Empty by default: a governed
    # repository with no stage registries simply has nothing for that check to do.
    registries: list[str] = Field(default_factory=list)

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


# Argv tokens are recorded verbatim as governed evidence and are executed with `shell=False`, so
# a token must survive a faithful round-trip through that record. NUL and newline cannot (they are
# the delimiters every line- or NUL-oriented consumer relies on), and a lone surrogate cannot be
# UTF-8 encoded at all. Rejecting them at configuration time keeps the failure deterministic and
# early rather than at execution or serialization time.
_FORBIDDEN_ARGV_CHARACTERS = {"\x00": "NUL", "\n": "newline", "\r": "newline"}


def _validate_argv_token(token: str, *, position: str) -> None:
    if token == "":
        raise ValueError(f"verification command token {position} must not be empty")
    for character, label in _FORBIDDEN_ARGV_CHARACTERS.items():
        if character in token:
            raise ValueError(f"verification command token {position} must not contain a {label}")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in token):
        raise ValueError(
            f"verification command token {position} must not contain a surrogate code point"
        )


class VerificationBundleSettings(StrictModel):
    """One named bundle of verification commands the engine may execute (T-307).

    Modelled on :class:`AgentSettings`: a named, strictly validated entry rather than a bare
    mapping. Commands are argv lists only — never shell strings — so no quoting or word splitting
    is ever involved and each token passes to the executed process exactly as configured.
    """

    name: str
    commands: list[list[str]] = Field(min_length=1)
    # Defaults to the runner's long-standing per-command verification timeout, so a bundle that
    # does not state one behaves like the existing hardcoded verification path.
    timeout_seconds: int = Field(ge=1, le=86400, default=3600)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        # Deliberately the same shape as an agent name, reusing the one compiled pattern so the
        # two configured-entity name rules cannot drift apart.
        if not _AGENT_NAME_RE.fullmatch(value):
            raise ValueError("verification bundle name must match [A-Za-z][A-Za-z0-9._-]{0,63}")
        return value

    @field_validator("commands")
    @classmethod
    def _validate_commands(cls, value: list[list[str]]) -> list[list[str]]:
        for command_index, argv in enumerate(value):
            if not argv:
                raise ValueError(
                    f"verification command {command_index} must have at least one token"
                )
            for token_index, token in enumerate(argv):
                _validate_argv_token(token, position=f"{command_index}.{token_index}")
        return value


class VerificationSettings(StrictModel):
    """The optional `verification` configuration section (T-307).

    An absent section, or a present section with no bundles, means no bundle can be selected —
    which is exactly the pre-T-307 behaviour.
    """

    bundles: list[VerificationBundleSettings] = Field(default_factory=list)

    @field_validator("bundles")
    @classmethod
    def _unique_bundle_names(
        cls, value: list[VerificationBundleSettings]
    ) -> list[VerificationBundleSettings]:
        names = [bundle.name for bundle in value]
        if len(set(names)) != len(names):
            raise ValueError("verification bundle names must be unique across the bundles list")
        return value


class EngineConfig(StrictModel):
    project: ProjectSettings
    governance: GovernanceSettings
    handover: HandoverSettings
    protected_paths: ProtectedPathsSettings = Field(default_factory=ProtectedPathsSettings)
    workflow: WorkflowSettings = Field(default_factory=WorkflowSettings)
    agents: list[AgentSettings] = Field(default_factory=list)
    # Optional and empty by default: a configuration with no `verification` section selects no
    # bundles and renders exactly the prompts it rendered before T-307.
    verification: VerificationSettings = Field(default_factory=VerificationSettings)

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
