from pydantic import BaseModel, ConfigDict


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_tasks: list[str]
    done_tasks: list[str]
    planned_tasks: list[str]
