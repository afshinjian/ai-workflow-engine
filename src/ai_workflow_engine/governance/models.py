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
