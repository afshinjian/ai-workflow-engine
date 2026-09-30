"""AUTO-017: pure, strict policy resolution and immutable Stage Start authority.

Selections describe identities only. They confer no adapter dispatch or runtime budget.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Never, TypeVar

from pydantic import (
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from ai_workflow_engine.milestone_runner.models import (
    STAGE_ID_RE,
    FindingSeverity,
    MilestoneRunnerModel,
    ProviderRole,
    StopReason,
    _utc_timestamp,
    canonical_digest,
    canonical_json_bytes,
    normalize_repository_path,
)

POLICY_SCHEMA_VERSION = 2
MIN_REMEDIATION_CYCLES = 1
MAX_REMEDIATION_CYCLES = 3
BUILTIN_MAX_REMEDIATION_CYCLES = 1
MIN_BLOCKERS = 1
MAX_BLOCKERS = 3
BUILTIN_MAX_BLOCKERS = 3
MAX_OWNER_EXTENSIONS = 2
POLICY_BLOCKING_SEVERITIES = (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
POLICY_DEFER_SEVERITIES = (FindingSeverity.MEDIUM, FindingSeverity.LOW)
MAX_ROLE_TIMEOUT_SECONDS = 43200
MAX_POLICY_INPUT_BYTES = 65536
MAX_STAGE_START_BYTES = 65536
MAX_STAGE_START_REFERENCE_BYTES = 4096

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_REPOSITORY_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*--[0-9a-f]{12}")
_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class CapabilityMode(StrEnum):
    READ_ONLY = "READ_ONLY"
    WORKSPACE_WRITE = "WORKSPACE_WRITE"


class OnRetryExhausted(StrEnum):
    ASK_OWNER_AND_FREEZE = "ask_owner_and_freeze"


class ProgramRole(StrEnum):
    IMPLEMENTER = "IMPLEMENTER"
    DISCOVERY_REVIEWER = "DISCOVERY_REVIEWER"
    REMEDIATOR = "REMEDIATOR"
    CLOSURE_VERIFIER = "CLOSURE_VERIFIER"


class StartPrincipal(StrEnum):
    LOCAL_CLI = "LOCAL_CLI"


class RegistryAuthorityKind(StrEnum):
    NO_GOVERNED_REGISTRY = "NO_GOVERNED_REGISTRY"
    GOVERNED_REGISTRY = "GOVERNED_REGISTRY"


BUILTIN_ON_RETRY_EXHAUSTED = OnRetryExhausted.ASK_OWNER_AND_FREEZE
PROGRAM_ROLE_TO_PROVIDER_ROLE: Mapping[ProgramRole, ProviderRole] = MappingProxyType(
    {
        ProgramRole.IMPLEMENTER: ProviderRole.IMPLEMENTATION,
        ProgramRole.DISCOVERY_REVIEWER: ProviderRole.REVIEW,
        ProgramRole.REMEDIATOR: ProviderRole.CORRECTION,
        ProgramRole.CLOSURE_VERIFIER: ProviderRole.CLOSURE,
    }
)
READ_ONLY_PROVIDER_ROLES = frozenset({ProviderRole.REVIEW, ProviderRole.CLOSURE})

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class InvalidPolicyConfiguration(ValueError):
    """A pure resolver refusal, translated at the application's operational boundary."""

    stop_reason: ClassVar[StopReason] = StopReason.INVALID_CONFIGURATION


def _immutable(*args: Any, **kwargs: Any) -> Never:
    raise TypeError("frozen policy values cannot be changed")


class _FrozenList(list[T]):
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _immutable
    append = clear = extend = insert = pop = remove = reverse = sort = _immutable


class _FrozenDict(dict[K, V]):
    __setitem__ = __delitem__ = __ior__ = _immutable
    clear = pop = popitem = setdefault = update = _immutable


class FrozenPolicyModel(MilestoneRunnerModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @model_validator(mode="after")
    def _freeze_containers(self) -> "FrozenPolicyModel":
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, dict):
                object.__setattr__(self, name, _FrozenDict(value))
            elif isinstance(value, list):
                object.__setattr__(self, name, _FrozenList(value))
        return self


class VersionedPolicyModel(FrozenPolicyModel):
    schema_version: int

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: int) -> int:
        if type(value) is not int or value != POLICY_SCHEMA_VERSION:
            raise ValueError("policy schema_version must be exactly 2")
        return value


def _digest(value: str) -> str:
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError("expected a lowercase SHA-256 digest")
    return value


def _canonical_path(value: str) -> str:
    if normalize_repository_path(value, "authority path") != value:
        raise ValueError("persisted authority paths must already be normalized")
    return value


class RoleSelection(FrozenPolicyModel):
    provider_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
    )
    model_id: str = Field(min_length=1, max_length=128)
    capability_mode: CapabilityMode = CapabilityMode.READ_ONLY
    timeout_seconds: int = Field(ge=1, le=MAX_ROLE_TIMEOUT_SECONDS)

    @field_validator("provider_id", "model_id")
    @classmethod
    def _identity(cls, value: str, info: ValidationInfo) -> str:
        pattern = (
            r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
            if info.field_name == "provider_id"
            else r"[A-Za-z0-9][A-Za-z0-9._:@/+-]*"
        )
        if re.fullmatch(pattern, value) is None or ".." in value:
            raise ValueError("invalid provider/model identifier syntax")
        return value

    @field_validator("capability_mode", mode="before")
    @classmethod
    def _capability(cls, value: Any) -> Any:
        return CapabilityMode(value) if isinstance(value, str) else value


class ProjectExecutionDefaults(VersionedPolicyModel):
    max_remediation_cycles: int | None = Field(default=None, ge=1, le=3)
    max_blockers: int | None = Field(default=None, ge=1, le=3)
    on_retry_exhausted: OnRetryExhausted | None = None
    roles: dict[ProviderRole, RoleSelection] = Field(default_factory=dict)

    @field_validator("on_retry_exhausted", mode="before")
    @classmethod
    def _retry(cls, value: Any) -> Any:
        return OnRetryExhausted(value) if isinstance(value, str) else value

    @field_validator("roles", mode="before")
    @classmethod
    def _roles(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {ProviderRole(k) if isinstance(k, str) else k: v for k, v in value.items()}
        return value


class StageExecutionOverrides(ProjectExecutionDefaults):
    """A whole-role replacement, with the same closed input vocabulary as defaults."""


class ContractExecutionCeilings(FrozenPolicyModel):
    max_remediation_cycles: int = Field(ge=1, le=3)
    max_blockers: int = Field(ge=1, le=3)


class RegistryAuthorityContext(FrozenPolicyModel):
    kind: RegistryAuthorityKind
    path: str | None

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> Any:
        return RegistryAuthorityKind(value) if isinstance(value, str) else value

    @field_validator("path")
    @classmethod
    def _path(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_path(value)

    @model_validator(mode="after")
    def _pair(self) -> "RegistryAuthorityContext":
        if (self.kind is RegistryAuthorityKind.NO_GOVERNED_REGISTRY) != (self.path is None):
            raise ValueError("registry declaration and path disagree")
        return self


class _BindingFields(FrozenPolicyModel):
    repository_identity: str
    stage_id: str
    contract_path: str
    contract_sha256: str
    registry_context: RegistryAuthorityContext

    @field_validator("repository_identity")
    @classmethod
    def _repository(cls, value: str) -> str:
        if _REPOSITORY_RE.fullmatch(value) is None:
            raise ValueError("invalid canonical repository identity")
        return value

    @field_validator("stage_id")
    @classmethod
    def _stage(cls, value: str) -> str:
        if STAGE_ID_RE.fullmatch(value) is None:
            raise ValueError("invalid Stage ID")
        return value

    @field_validator("contract_path")
    @classmethod
    def _path(cls, value: str) -> str:
        return _canonical_path(value)

    @field_validator("contract_sha256")
    @classmethod
    def _sha(cls, value: str) -> str:
        return _digest(value)


class StageContractBinding(_BindingFields):
    ceilings: ContractExecutionCeilings


class EffectiveStageExecutionPolicy(_BindingFields, VersionedPolicyModel):
    contract_ceilings: ContractExecutionCeilings
    max_remediation_cycles: int = Field(ge=1, le=3)
    on_retry_exhausted: OnRetryExhausted
    max_blockers: int = Field(ge=1, le=3)
    blocking_severities: list[FindingSeverity]
    defer_severities: list[FindingSeverity]
    max_owner_extensions: int
    roles: dict[ProviderRole, RoleSelection]
    project_defaults_digest: str | None
    stage_overrides_digest: str

    @field_validator("roles", mode="before")
    @classmethod
    def _roles(cls, value: Any) -> Any:
        return ProjectExecutionDefaults._roles(value)

    @field_validator("on_retry_exhausted", mode="before")
    @classmethod
    def _retry(cls, value: Any) -> Any:
        return ProjectExecutionDefaults._retry(value)

    @field_validator("blocking_severities", "defer_severities", mode="before")
    @classmethod
    def _severities(cls, value: Any) -> Any:
        return (
            [FindingSeverity(v) if isinstance(v, str) else v for v in value]
            if isinstance(value, list)
            else value
        )

    @field_validator("project_defaults_digest", "stage_overrides_digest")
    @classmethod
    def _input_digest(cls, value: str | None) -> str | None:
        return None if value is None else _digest(value)

    @model_validator(mode="after")
    def _effective(self) -> "EffectiveStageExecutionPolicy":
        if (
            self.blocking_severities != list(POLICY_BLOCKING_SEVERITIES)
            or self.defer_severities != list(POLICY_DEFER_SEVERITIES)
            or self.max_owner_extensions != MAX_OWNER_EXTENSIONS
        ):
            raise ValueError("fixed policy values cannot be overridden")
        for name in ("max_remediation_cycles", "max_blockers"):
            if getattr(self, name) > getattr(self.contract_ceilings, name):
                raise ValueError("policy exceeds contract ceiling")
        if set(self.roles) != set(ProviderRole):
            raise ValueError("all four provider roles are required")
        if any(
            self.roles[r].capability_mode is not CapabilityMode.READ_ONLY
            for r in READ_ONLY_PROVIDER_ROLES
        ):
            raise ValueError("review and closure roles must be READ_ONLY")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


def authority_json_bytes(payload: object) -> bytes:
    """Integrity serialization: no timestamp or nested key is omitted."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8", errors="strict")


def authority_digest(payload: object) -> str:
    return hashlib.sha256(authority_json_bytes(payload)).hexdigest()


def stage_start_key(repository_identity: str, stage_id: str, contract_sha256: str) -> str:
    return canonical_digest(
        dict(
            repository_identity=repository_identity,
            stage_id=stage_id,
            contract_sha256=contract_sha256,
        )
    )


def logical_authorization_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in payload.items()
        if k not in {"stage_start_id", "authorization_digest", "created_at"}
    }


class StageStartAuthorization(_BindingFields, VersionedPolicyModel):
    stage_start_id: str
    authorization_digest: str
    stage_start_key: str
    principal: StartPrincipal
    contract_ceilings: ContractExecutionCeilings
    stage_overrides: StageExecutionOverrides
    effective_policy: EffectiveStageExecutionPolicy
    effective_policy_digest: str
    created_at: str

    @field_validator(
        "stage_start_id", "authorization_digest", "stage_start_key", "effective_policy_digest"
    )
    @classmethod
    def _digests(cls, value: str) -> str:
        return _digest(value)

    @field_validator("principal", mode="before")
    @classmethod
    def _principal(cls, value: Any) -> Any:
        return StartPrincipal(value) if isinstance(value, str) else value

    @field_validator("created_at")
    @classmethod
    def _timestamp(cls, value: str) -> str:
        _utc_timestamp(value, "created_at")
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return value

    @model_validator(mode="after")
    def _authority(self) -> "StageStartAuthorization":
        policy = self.effective_policy
        for name in (*_BindingFields.model_fields, "contract_ceilings"):
            if getattr(self, name) != getattr(policy, name):
                raise ValueError("authorization and embedded policy binding disagree")
        if self.effective_policy_digest != policy.digest:
            raise ValueError("embedded policy digest mismatch")
        if policy.stage_overrides_digest != canonical_digest(
            self.stage_overrides.model_dump(mode="json")
        ):
            raise ValueError("overrides digest mismatch")
        if self.stage_start_key != stage_start_key(
            self.repository_identity, self.stage_id, self.contract_sha256
        ):
            raise ValueError("Stage Start key mismatch")
        payload = self.model_dump(mode="json")
        if self.stage_start_id != authority_digest(logical_authorization_payload(payload)):
            raise ValueError("logical authorization digest mismatch")
        if self.authorization_digest != authority_digest(
            {k: v for k, v in payload.items() if k != "authorization_digest"}
        ):
            raise ValueError("full authorization digest mismatch")
        return self


class StageStartPointer(VersionedPolicyModel):
    stage_start_key: str
    stage_start_id: str
    authorization_digest: str

    @field_validator("stage_start_key", "stage_start_id", "authorization_digest")
    @classmethod
    def _identifiers(cls, value: str) -> str:
        return _digest(value)


class StageStartBinding(StageStartPointer):
    policy_digest: str
    run_id: str
    binding_digest: str

    @field_validator("policy_digest", "binding_digest")
    @classmethod
    def _pins(cls, value: str) -> str:
        return _digest(value)

    @field_validator("run_id")
    @classmethod
    def _run(cls, value: str) -> str:
        if _RUN_RE.fullmatch(value) is None:
            raise ValueError("invalid run ID")
        return value

    @model_validator(mode="after")
    def _integrity(self) -> "StageStartBinding":
        payload = self.model_dump(mode="json", exclude={"binding_digest"})
        if self.binding_digest != authority_digest(payload):
            raise ValueError("binding integrity mismatch")
        return self


class StageStartConsumptionWitness(StageStartPointer):
    """Immutable local evidence of the one run consuming this authorization."""

    stage_id: str
    contract_sha256: str
    policy_digest: str
    run_id: str
    binding_digest: str
    witness_digest: str

    @field_validator("contract_sha256", "policy_digest", "binding_digest", "witness_digest")
    @classmethod
    def _pins(cls, value: str) -> str:
        return _digest(value)

    @field_validator("stage_id")
    @classmethod
    def _stage(cls, value: str) -> str:
        if STAGE_ID_RE.fullmatch(value) is None:
            raise ValueError("invalid Stage ID")
        return value

    @field_validator("run_id")
    @classmethod
    def _run(cls, value: str) -> str:
        if _RUN_RE.fullmatch(value) is None:
            raise ValueError("invalid run ID")
        return value

    @model_validator(mode="after")
    def _integrity(self) -> "StageStartConsumptionWitness":
        if self.witness_digest != authority_digest(
            self.model_dump(mode="json", exclude={"witness_digest"})
        ):
            raise ValueError("witness integrity mismatch")
        return self


def resolve_policy(
    defaults: ProjectExecutionDefaults | None,
    overrides: StageExecutionOverrides,
    contract: StageContractBinding,
    *,
    project_defaults_digest: str | None,
) -> EffectiveStageExecutionPolicy:
    """Resolve in ceiling / explicit override / project default / built-in order.

    Invalid input raises a typed INVALID_CONFIGURATION without importing configuration or I/O.
    """
    scalars: dict[str, Any] = {}
    for name, builtin in (
        ("max_remediation_cycles", BUILTIN_MAX_REMEDIATION_CYCLES),
        ("max_blockers", BUILTIN_MAX_BLOCKERS),
    ):
        ceiling = getattr(contract.ceilings, name)
        override = getattr(overrides, name)
        default = getattr(defaults, name) if defaults is not None else None
        if override is not None and override > ceiling:
            raise InvalidPolicyConfiguration(
                f"{name} {override} exceeds contract ceiling {ceiling}"
            )
        scalars[name] = (
            override
            if override is not None
            else min(default if default is not None else builtin, ceiling)
        )
    retry = overrides.on_retry_exhausted
    if retry is None and defaults is not None:
        retry = defaults.on_retry_exhausted
    roles: dict[ProviderRole, RoleSelection] = {}
    for role in ProviderRole:
        chosen = overrides.roles.get(role)
        if chosen is None and defaults is not None:
            chosen = defaults.roles.get(role)
        if chosen is None:
            raise InvalidPolicyConfiguration(f"no selection for role {role.value}")
        roles[role] = chosen
    try:
        return EffectiveStageExecutionPolicy(
            schema_version=POLICY_SCHEMA_VERSION,
            **contract.model_dump(exclude={"ceilings"}),
            contract_ceilings=contract.ceilings,
            **scalars,
            on_retry_exhausted=retry or BUILTIN_ON_RETRY_EXHAUSTED,
            blocking_severities=list(POLICY_BLOCKING_SEVERITIES),
            defer_severities=list(POLICY_DEFER_SEVERITIES),
            max_owner_extensions=MAX_OWNER_EXTENSIONS,
            roles=roles,
            project_defaults_digest=project_defaults_digest,
            stage_overrides_digest=canonical_digest(overrides.model_dump(mode="json")),
        )
    except ValidationError as exc:
        raise InvalidPolicyConfiguration(f"invalid effective policy: {exc}") from exc
