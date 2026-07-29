from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TaskStatus(StrEnum):
    CURRENT = "Current"
    DONE = "Done"
    PLANNED = "Planned"


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    status: TaskStatus
    source: str
    line: int


class TaskSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    by_source: dict[str, list[TaskRecord]]
    current: list[str]
    done: list[str]
    planned: list[str]


class RegistryState(StrEnum):
    """The ten stage-lifecycle states both program stage registries share (their §State Model)."""

    NOT_STARTED = "NOT_STARTED"
    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    IN_PROGRESS = "IN_PROGRESS"
    SELF_REVIEW = "SELF_REVIEW"
    REVIEW = "REVIEW"
    APPROVAL = "APPROVAL"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"


class RegistryRow(BaseModel):
    """One structural row of a stage registry's Registry table. The raw State cell is kept
    verbatim; recognizing it as a `RegistryState` and applying the state→task-status mapping is
    the validator's policy, not the parser's, mirroring how `parse_tasks` stays structural."""

    model_config = ConfigDict(extra="forbid")
    stage_id: str
    raw_state: str
    source: str
    line: int


class RegistryParse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    table_found: bool
    rows: list[RegistryRow]
