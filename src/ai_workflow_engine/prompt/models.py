"""Strict prompt models: canonical payload, identity, and storage shapes.

Every model here inherits :class:`ai_workflow_engine.models.StrictModel` (via the
:class:`PromptStrictModel` base defined in this module), so unknown fields are always
forbidden and every field additionally rejects a value whose type does not exactly
match its declaration.
"""

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Literal, cast

from pydantic import ConfigDict, field_validator, model_validator
from typing_extensions import TypeAliasType

from ai_workflow_engine.models import StrictModel
from ai_workflow_engine.models import WorkflowStage as WorkflowStage  # re-exported for the package


class PromptStrictModel(StrictModel):
    """Base for every prompt model: closed schema plus exact-type field validation.

    `model_config` does not cascade into nested models in Pydantic v2, so `strict=True`
    is declared again on every subclass (via this shared base) rather than once at the
    top of the prompt payload tree. This still "inherits from the existing StrictModel"
    (`extra="forbid"` is unchanged) without altering `StrictModel` itself, which remains
    shared with unrelated, non-prompt configuration models.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


WORKFLOW_STAGES: tuple[WorkflowStage, ...] = (
    "plan-review",
    "implementation",
    "implementation-review",
    "remediation",
    "governance-closeout",
    "governance-review",
    "push",
)

JsonScalar = None | bool | int | str
JsonValue = TypeAliasType("JsonValue", "JsonScalar | list[JsonValue] | dict[str, JsonValue]")

_INT64_MIN = -9223372036854775808
_INT64_MAX = 9223372036854775807

_SEMVER_PATTERN = (
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_PROMPT_ID_RE = re.compile(r"[0-9a-f]{16}")


def _has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def canonicalize_json_value(value: object) -> JsonValue:
    """Recursively accept only None, exact bool, exact 64-bit int, str, list, dict.

    Anything else (float, tuple, set, enum, bytes, datetime, ...) is a caller bug
    that must be converted by a typed builder before it ever reaches this function.
    """
    if value is None:
        return None
    value_type = type(value)
    if value_type is bool:
        return cast(bool, value)
    if value_type is int:
        integer = cast(int, value)
        if not (_INT64_MIN <= integer <= _INT64_MAX):
            raise ValueError(f"Integer {integer} is outside the signed 64-bit range")
        return integer
    if value_type is str:
        text = cast(str, value)
        if _has_surrogate(text):
            raise ValueError("Surrogate code point is not permitted in a JSON string")
        return unicodedata.normalize("NFC", text)
    if value_type is list:
        return [canonicalize_json_value(item) for item in cast(list[object], value)]
    if value_type is dict:
        normalized: dict[str, JsonValue] = {}
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise ValueError(f"JSON object key must be a string, got {type(key)!r}")
            key_text = key
            if _has_surrogate(key_text):
                raise ValueError("Surrogate code point is not permitted in a JSON object key")
            normalized_key = unicodedata.normalize("NFC", key_text)
            if normalized_key in normalized:
                raise ValueError(f"NFC-normalized object key collision: {normalized_key!r}")
            normalized[normalized_key] = canonicalize_json_value(item)
        return normalized
    raise ValueError(f"Unsupported JSON value type: {value_type!r}")


def _require_sorted_unique(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("collection must not contain duplicate paths")
    if values != sorted(values):
        raise ValueError("collection must be sorted by Unicode code point")
    return values


class PromptTemplate(PromptStrictModel):
    stage: WorkflowStage
    version: str
    content: str
    sha256: str

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if re.fullmatch(_SEMVER_PATTERN, value, flags=re.ASCII) is None:
            raise ValueError(f"version {value!r} is not a valid SemVer 2.0.0 string")
        return value

    @model_validator(mode="after")
    def _validate_content_and_digest(self) -> "PromptTemplate":
        if not _SHA256_HEX_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be exactly 64 lowercase hexadecimal characters")
        if _has_surrogate(self.content):
            raise ValueError("content must not contain a surrogate code point")
        if unicodedata.normalize("NFC", self.content) != self.content:
            raise ValueError("content must be NFC-normalized")
        if "\r" in self.content:
            raise ValueError("content must use LF line endings only")
        if not self.content.endswith("\n") or self.content.endswith("\n\n"):
            raise ValueError("content must end with exactly one final newline")
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if digest != self.sha256:
            raise ValueError("sha256 does not match content")
        return self


class CanonicalGitStatus(PromptStrictModel):
    branch: str
    head: str
    upstream: str | None
    ahead: int | None
    behind: int | None
    modified_files: list[str]
    staged_files: list[str]
    untracked_files: list[str]

    @field_validator("modified_files", "staged_files", "untracked_files")
    @classmethod
    def _sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)


class CanonicalTaskRecord(PromptStrictModel):
    task_id: str
    status: Literal["Current", "Done", "Planned"]
    source: str
    line: int


class CanonicalTaskSnapshot(PromptStrictModel):
    by_source: dict[str, list[CanonicalTaskRecord]]
    current: list[str]
    done: list[str]
    planned: list[str]

    @field_validator("current", "done", "planned")
    @classmethod
    def _sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)


class CanonicalFinding(PromptStrictModel):
    code: str
    message: str
    severity: str
    path: str | None


class CanonicalCheckResult(PromptStrictModel):
    check_name: Literal["git", "task-state", "governance", "handover"]
    status: Literal["PASS", "FAIL", "ERROR"]
    summary: str
    findings: list[CanonicalFinding]
    evidence: dict[str, JsonValue]
    affected_paths: list[str]
    remediation_hint: str | None

    @field_validator("findings")
    @classmethod
    def _findings_sorted(cls, value: list[CanonicalFinding]) -> list[CanonicalFinding]:
        def key(finding: CanonicalFinding) -> tuple[str, str, str, str]:
            return (finding.code, finding.path or "", finding.severity, finding.message)

        if value != sorted(value, key=key):
            raise ValueError("findings must be sorted by (code, path, severity, message)")
        return value

    @field_validator("affected_paths")
    @classmethod
    def _affected_paths_sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)

    @field_validator("evidence")
    @classmethod
    def _evidence_canonical(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        normalized = canonicalize_json_value(value)
        assert isinstance(normalized, dict)
        return normalized


class CanonicalProjectSettings(PromptStrictModel):
    id: str
    repository: str
    default_branch: str
    timezone: str
    require_upstream: bool
    conda_environment: str


class CanonicalFactRule(PromptStrictModel):
    name: str
    paths: list[str]
    pattern: str
    group: int | str
    required: bool

    @field_validator("paths")
    @classmethod
    def _paths_sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)


class CanonicalGovernanceSettings(PromptStrictModel):
    project_state: str
    task_queue: str
    current_task: str
    remaining_tasks: str
    context: str
    pyproject: str
    facts: list[CanonicalFactRule]


class CanonicalHandoverSettings(PromptStrictModel):
    manifest: str
    files: list[str]

    @field_validator("files")
    @classmethod
    def _files_sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)


class CanonicalProtectedPathsSettings(PromptStrictModel):
    never_stage: list[str]
    never_commit: list[str]

    @field_validator("never_stage", "never_commit")
    @classmethod
    def _sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)


class CanonicalWorkflowSettings(PromptStrictModel):
    maximum_current_tasks: int
    require_designer_approval_for_promotion: bool
    allow_automatic_commit: bool
    allow_automatic_push: bool


_STAGE_INDEX: dict[str, int] = {stage: index for index, stage in enumerate(WORKFLOW_STAGES)}


class CanonicalAgentSettings(PromptStrictModel):
    name: str
    executable: str
    args: list[str]
    mode: Literal["read-only", "scoped-write"]
    timeout_seconds: int
    stages: list[str]

    @field_validator("stages")
    @classmethod
    def _stages_valid_sorted_unique(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("agent stages must be non-empty")
        if any(stage not in _STAGE_INDEX for stage in value):
            raise ValueError("agent stages must be workflow stages")
        if len(set(value)) != len(value):
            raise ValueError("agent stages must be unique")
        if value != sorted(value, key=_STAGE_INDEX.__getitem__):
            raise ValueError("agent stages must be sorted by workflow-stage order")
        return value


class CanonicalEngineConfig(PromptStrictModel):
    project: CanonicalProjectSettings
    governance: CanonicalGovernanceSettings
    handover: CanonicalHandoverSettings
    protected_paths: CanonicalProtectedPathsSettings
    workflow: CanonicalWorkflowSettings
    agents: list[CanonicalAgentSettings]

    @field_validator("agents")
    @classmethod
    def _agents_sorted_unique_by_name(
        cls, value: list[CanonicalAgentSettings]
    ) -> list[CanonicalAgentSettings]:
        names = [agent.name for agent in value]
        if len(set(names)) != len(names):
            raise ValueError("agent names must be unique")
        if names != sorted(names):
            raise ValueError("agents must be sorted by name")
        return value


class PromptContext(PromptStrictModel):
    schema_version: Literal["1.1"]
    config: CanonicalEngineConfig
    stage: WorkflowStage
    task_id: str
    template: PromptTemplate
    git_status: CanonicalGitStatus
    task_snapshot: CanonicalTaskSnapshot
    protected_path_violations: list[str]
    checks: list[CanonicalCheckResult]
    remediation_findings: list[str]
    allowed_paths: list[str]

    @field_validator("protected_path_violations", "allowed_paths")
    @classmethod
    def _sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)

    @field_validator("checks")
    @classmethod
    def _checks_fixed_order(cls, value: list[CanonicalCheckResult]) -> list[CanonicalCheckResult]:
        expected = ("git", "task-state", "governance", "handover")
        if tuple(check.check_name for check in value) != expected:
            raise ValueError(f"checks must be in the fixed order {expected}")
        return value


class PromptMetadata(PromptStrictModel):
    schema_version: Literal["1.1"]
    prompt_id: str
    project_id: str
    task_id: str
    stage: WorkflowStage
    template_version: str
    template_sha256: str
    repository_head: str
    allowed_paths: list[str]
    remediation_findings: list[str]
    payload_sha256: str
    markdown_sha256: str
    payload: PromptContext

    @field_validator("prompt_id")
    @classmethod
    def _validate_prompt_id(cls, value: str) -> str:
        if not _PROMPT_ID_RE.fullmatch(value):
            raise ValueError("prompt_id must be exactly 16 lowercase hexadecimal characters")
        return value

    @field_validator("template_sha256", "payload_sha256", "markdown_sha256")
    @classmethod
    def _validate_hex64(cls, value: str) -> str:
        if not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
        return value

    @field_validator("allowed_paths")
    @classmethod
    def _allowed_paths_sorted_unique(cls, value: list[str]) -> list[str]:
        return _require_sorted_unique(value)


class RenderedPrompt(PromptStrictModel):
    context: PromptContext
    canonical_payload_bytes: bytes
    prompt_id: str
    markdown: str
    metadata: PromptMetadata
    metadata_bytes: bytes

    @field_validator("prompt_id")
    @classmethod
    def _validate_prompt_id(cls, value: str) -> str:
        if not _PROMPT_ID_RE.fullmatch(value):
            raise ValueError("prompt_id must be exactly 16 lowercase hexadecimal characters")
        return value


class StoredPromptPaths(PromptStrictModel):
    markdown: Path
    metadata: Path


class PromptSuccess(PromptStrictModel):
    schema_version: Literal["1.1"]
    stored: bool
    prompt_artifact: str | None
    metadata_artifact: str | None
    prompt: str
    metadata: PromptMetadata
