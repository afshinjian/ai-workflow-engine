from pydantic import BaseModel, ConfigDict, Field


class GitStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: str
    head: str
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    modified_files: list[str] = Field(default_factory=list)
    staged_files: list[str] = Field(default_factory=list)
    untracked_files: list[str] = Field(default_factory=list)
