"""Stable structured results returned by every check."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    severity: str = "error"
    path: str | None = None


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_name: str
    status: Status
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    affected_paths: list[str] = Field(default_factory=list)
    remediation_hint: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    project_id: str
    status: Status
    checks: list[CheckResult]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


def combined_status(results: list[CheckResult]) -> Status:
    if any(result.status == Status.ERROR for result in results):
        return Status.ERROR
    if any(result.status == Status.FAIL for result in results):
        return Status.FAIL
    return Status.PASS
