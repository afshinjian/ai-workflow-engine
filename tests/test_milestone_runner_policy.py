"""AUTO-017 §16.1: closed schemas, deterministic resolution and frozen authority.

The test docstrings name contract IDs; persistence and application behavior are exercised in
those suites. Unknown role identities deliberately have no runtime meaning here.
"""

import ast
import copy
import hashlib
import itertools
import json
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from test_milestone_runner_plan import runner_config_payload

from ai_workflow_engine.milestone_runner import policy
from ai_workflow_engine.milestone_runner.config import (
    MAX_TIMEOUT_SECONDS,
    InvalidRunnerConfiguration,
    RunnerConfig,
    StageSettingsV2,
    load_runner_config,
)
from ai_workflow_engine.milestone_runner.models import (
    LEGACY_MILESTONE_ID_RE,
    LEGACY_STAGE_ID_RE,
    MILESTONE_ID_RE,
    STAGE_ID_RE,
    FindingSeverity,
    ProviderRole,
    StopReason,
    canonical_digest,
    canonical_json_bytes,
)
from ai_workflow_engine.milestone_runner.policy import (
    CapabilityMode,
    ContractExecutionCeilings,
    EffectiveStageExecutionPolicy,
    OnRetryExhausted,
    ProgramRole,
    ProjectExecutionDefaults,
    RegistryAuthorityContext,
    StageContractBinding,
    StageExecutionOverrides,
    StageStartAuthorization,
    StageStartBinding,
    StageStartPointer,
    StartPrincipal,
    authority_digest,
    authority_json_bytes,
    logical_authorization_payload,
    resolve_policy,
    stage_start_key,
)
from ai_workflow_engine.milestone_runner.prompts import PromptContext
from ai_workflow_engine.milestone_runner.state import _loads_rejecting_duplicate_keys

POSITIVE_STAGE_IDS = (
    "AUTO-017",
    "ST-07",
    "AWE-AUTO-ST-01",
    "PROJ1-STAGE-2",
    "A",
    "ST-M001",
    "A" * 16 + "-" + "B" * 16 + "-" + "C" * 16 + "-" + "D" * 13,
)
NEGATIVE_STAGE_IDS = (
    "auto-017",
    "ST_07",
    "-ST",
    "ST-",
    "ST--07",
    "ST-M01",
    "M01",
    "A" * 16 + "-" + "B" * 16 + "-" + "C" * 16 + "-" + "D" * 14,
    "AUTO-017 ",
    "ÄUTO-1",
    "ST/07",
    "ST\n",
    "ST\x00",
    "ST\u202e07",
    "",
    "A" * 17,
    "A-B-C-D-E-F",
)


def selection(
    provider: str = "unknown-provider", model: str = "unknown/model:v1", **updates: Any
) -> dict[str, Any]:
    return dict(provider_id=provider, model_id=model, timeout_seconds=60, **updates)


def role_payloads() -> dict[str, Any]:
    return {role.value: selection() for role in ProviderRole}


def binding_payload() -> dict[str, Any]:
    return dict(
        repository_identity="example--0123456789ab",
        stage_id="ST-07",
        contract_path="docs/contract.md",
        contract_sha256="a" * 64,
        ceilings=dict(max_remediation_cycles=3, max_blockers=3),
        registry_context=dict(kind="NO_GOVERNED_REGISTRY", path=None),
    )


def policy_inputs() -> (
    tuple[ProjectExecutionDefaults, StageExecutionOverrides, StageContractBinding]
):
    return (
        ProjectExecutionDefaults.model_validate(dict(schema_version=2, roles=role_payloads())),
        StageExecutionOverrides(schema_version=2),
        StageContractBinding.model_validate(binding_payload()),
    )


def resolved(**overrides: Any) -> EffectiveStageExecutionPolicy:
    defaults, _, contract = policy_inputs()
    return resolve_policy(
        defaults,
        StageExecutionOverrides.model_validate(dict(schema_version=2, **overrides)),
        contract,
        project_defaults_digest=None,
    )


def authorization_payload(
    effective: EffectiveStageExecutionPolicy | None = None,
    overrides: StageExecutionOverrides | None = None,
    created_at: str = "2026-09-29T01:02:03Z",
) -> dict[str, Any]:
    effective = effective or resolved()
    overrides = overrides or StageExecutionOverrides(schema_version=2)
    payload = dict(
        schema_version=2,
        principal="LOCAL_CLI",
        **{
            key: getattr(effective, key)
            for key in ("repository_identity", "stage_id", "contract_path", "contract_sha256")
        },
        registry_context=effective.registry_context.model_dump(mode="json"),
        contract_ceilings=effective.contract_ceilings.model_dump(mode="json"),
        stage_overrides=overrides.model_dump(mode="json"),
        effective_policy=effective.model_dump(mode="json"),
        effective_policy_digest=effective.digest,
        created_at=created_at,
    )
    payload["stage_start_key"] = stage_start_key(
        effective.repository_identity, effective.stage_id, effective.contract_sha256
    )
    payload["stage_start_id"] = authority_digest(logical_authorization_payload(payload))
    payload["authorization_digest"] = authority_digest(payload)
    return payload


def v2_config_payload(repository: Path) -> dict[str, Any]:
    payload = runner_config_payload(repository)
    payload["schema_version"] = 2
    payload.pop("review_policy")
    payload["stage"].update(
        stage_id="ST-07",
        registry_path=None,
        execution_ceilings=dict(max_remediation_cycles=3, max_blockers=3),
    )
    return payload


def load_payload(tmp_path: Path, payload: dict[str, Any]) -> RunnerConfig:
    path = tmp_path / "runner.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return load_runner_config(path)


def test_v2_configuration_dispatch(tmp_path: Path) -> None:
    """T-CFG-V2-OK: full YAML load and binding serialization preserve v2 fields."""
    config = load_payload(tmp_path, v2_config_payload(tmp_path))
    assert config.schema_version == 2
    assert isinstance(config.stage, StageSettingsV2)
    binding = config.contract_binding()
    assert binding.stage_id == "ST-07"
    assert binding.registry_context.model_dump(mode="json") == {
        "kind": "NO_GOVERNED_REGISTRY",
        "path": None,
    }
    assert config.model_dump(mode="json")["stage"]["execution_ceilings"] == {
        "max_remediation_cycles": 3,
        "max_blockers": 3,
    }


@pytest.mark.parametrize(
    "case,accepted",
    [
        ("complete", True),
        ("git-defaults", True),
        ("legacy-other-stage", True),
        ("stricter-review", True),
        ("absent-review", False),
        ("null-review", False),
        ("v2-stage", False),
        ("registry-key", False),
        ("ceilings-key", False),
        ("policy-key", False),
        ("unknown-key", False),
        ("excess-review", False),
    ],
)
def test_v1_configuration_accept_refuse_matrix(tmp_path: Path, case: str, accepted: bool) -> None:
    """T-CFG-V1-UNCHANGED: a literal matrix supplements the unmodified v1 tests."""
    payload = runner_config_payload(tmp_path)
    if case == "git-defaults":
        payload["git"] = {}
    elif case == "legacy-other-stage":
        payload["stage"]["stage_id"] = "AUTO-999"
    elif case == "stricter-review":
        payload["review_policy"].update(
            blocking_severities=["CRITICAL", "HIGH", "MEDIUM"], defer_severities=["LOW"]
        )
    elif case == "absent-review":
        payload.pop("review_policy")
    elif case == "null-review":
        payload["review_policy"] = None
    elif case == "v2-stage":
        payload["stage"]["stage_id"] = "ST-07"
    elif case == "registry-key":
        payload["stage"]["registry_path"] = None
    elif case == "ceilings-key":
        payload["stage"]["execution_ceilings"] = dict(max_remediation_cycles=1, max_blockers=3)
    elif case == "policy-key":
        payload["max_remediation_cycles"] = 1
    elif case == "unknown-key":
        payload["unknown"] = True
    elif case == "excess-review":
        payload["review_policy"]["max_full_reviews"] = 2
    if accepted:
        config = load_payload(tmp_path, payload)
        assert config.schema_version == 1
        assert config.review_policy is not None
        assert not isinstance(config.stage, StageSettingsV2)
        with pytest.raises(InvalidRunnerConfiguration):
            config.contract_binding()
    else:
        with pytest.raises(InvalidRunnerConfiguration) as error:
            load_payload(tmp_path, payload)
        assert error.value.stop_reason is StopReason.INVALID_CONFIGURATION


@pytest.mark.parametrize("version", [0, 3, "2", 2.0, True, None, "missing"])
def test_configuration_version_is_exact_before_validation(tmp_path: Path, version: Any) -> None:
    """T-CFG-VERSION: even an otherwise broken document cannot bypass exact dispatch."""
    payload = {} if version == "missing" else {"schema_version": version}
    with pytest.raises(InvalidRunnerConfiguration, match="exact integer") as error:
        load_payload(tmp_path, payload)
    assert error.value.stop_reason is StopReason.INVALID_CONFIGURATION
    with pytest.raises(ValidationError):
        RunnerConfig.model_validate(payload)


@pytest.mark.parametrize(
    "review", [None, {}, [], "", {"blocking_severities": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}]
)
def test_v2_review_policy_is_forbidden_whatever_content(tmp_path: Path, review: Any) -> None:
    """T-CFG-V2-REVIEW-POLICY: no second source of review parameters."""
    payload = v2_config_payload(tmp_path)
    payload["review_policy"] = review
    with pytest.raises(InvalidRunnerConfiguration, match="review_policy is forbidden"):
        load_payload(tmp_path, payload)


@pytest.mark.parametrize("required", ["registry_path", "execution_ceilings"])
def test_v2_stage_requires_explicit_authority_keys(tmp_path: Path, required: str) -> None:
    """T-CFG-V2-REGISTRY-KEY: omission cannot declare no registry."""
    payload = v2_config_payload(tmp_path)
    payload["stage"].pop(required)
    with pytest.raises(InvalidRunnerConfiguration):
        load_payload(tmp_path, payload)


def test_registry_configuration_normalizes_and_protects_paths(tmp_path: Path) -> None:
    """T-CFG-V2-REGISTRY-KEY: normalize input; freeze exact canonical authority."""
    payload = v2_config_payload(tmp_path)
    payload["stage"]["registry_path"] = "docs//./registry.md"
    config = load_payload(tmp_path, payload)
    assert config.contract_binding().registry_context.model_dump(mode="json") == {
        "kind": "GOVERNED_REGISTRY",
        "path": "docs/registry.md",
    }
    for field in ("registry_path", "contract_path"):
        forbidden = copy.deepcopy(payload)
        forbidden["allowlist"]["allowed_paths"].append(forbidden["stage"][field])
        with pytest.raises(InvalidRunnerConfiguration):
            load_payload(tmp_path, forbidden)


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "..",
        "../registry.md",
        "/registry.md",
        "C:/registry.md",
        "docs/../registry.md",
        "docs\\registry.md",
        "docs/registry\x00.md",
        "docs/registry\n.md",
        "docs/\u202eregistry.md",
        "docs/ registry.md",
        "a" * 513,
    ],
)
def test_registry_paths_refuse_hostile_input(tmp_path: Path, path: str) -> None:
    """T-CFG-V2-REGISTRY-KEY: hostile paths fail both input and persisted schemas."""
    payload = v2_config_payload(tmp_path)
    payload["stage"]["registry_path"] = path
    with pytest.raises(InvalidRunnerConfiguration):
        load_payload(tmp_path, payload)
    with pytest.raises(ValidationError):
        RegistryAuthorityContext(kind="GOVERNED_REGISTRY", path=path)


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"kind": "NO_GOVERNED_REGISTRY"},
        {"path": None},
        {"kind": "NO_GOVERNED_REGISTRY", "path": "docs/registry.md"},
        {"kind": "GOVERNED_REGISTRY", "path": None},
        {"kind": "UNKNOWN", "path": None},
        {"kind": "GOVERNED_REGISTRY", "path": "docs//registry.md"},
        {"kind": "NO_GOVERNED_REGISTRY", "path": None, "unknown": 1},
    ],
)
def test_registry_context_is_closed_explicit_and_canonical(context: dict[str, Any]) -> None:
    """T-CFG-V2-REGISTRY-KEY / T-REGISTRY-CONTEXT-DIGEST."""
    with pytest.raises(ValidationError):
        RegistryAuthorityContext.model_validate(context)


@pytest.mark.parametrize("value", [1, 2, 3])
@pytest.mark.parametrize("field", ["max_remediation_cycles", "max_blockers"])
def test_integer_fields_accept_each_permitted_value(value: int, field: str) -> None:
    """T-MRC-1 / T-MRC-2 / T-MRC-3 / T-BLOCKERS: same exact range everywhere."""
    for model in (ProjectExecutionDefaults, StageExecutionOverrides):
        assert (
            getattr(model.model_validate(dict(schema_version=2, **{field: value})), field) == value
        )
    ceilings = ContractExecutionCeilings.model_validate(
        {**dict(max_remediation_cycles=3, max_blockers=3), field: value}
    )
    assert getattr(ceilings, field) == value
    effective = resolved(**{field: value})
    assert getattr(effective, field) == value
    assert (
        EffectiveStageExecutionPolicy.model_validate_json(effective.canonical_bytes()) == effective
    )


@pytest.mark.parametrize("value", [0, 4, -1, "2", 2.0, True, [], {}])
@pytest.mark.parametrize("field", ["max_remediation_cycles", "max_blockers"])
def test_integer_fields_reject_non_exact_values(value: Any, field: str) -> None:
    """T-MRC-REJECT / T-BLOCKERS: rejected in inputs, ceilings and persisted policy."""
    for model in (ProjectExecutionDefaults, StageExecutionOverrides):
        with pytest.raises(ValidationError):
            model.model_validate(dict(schema_version=2, **{field: value}))
    with pytest.raises(ValidationError):
        ContractExecutionCeilings.model_validate(
            {**dict(max_remediation_cycles=3, max_blockers=3), field: value}
        )
    payload = resolved().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        EffectiveStageExecutionPolicy.model_validate(payload)


@pytest.mark.parametrize("field", ["max_remediation_cycles", "max_blockers"])
def test_null_means_unset_only_for_input_scalars(field: str) -> None:
    for model in (ProjectExecutionDefaults, StageExecutionOverrides):
        assert getattr(model.model_validate(dict(schema_version=2, **{field: None})), field) is None
    for model, payload in (
        (ContractExecutionCeilings, dict(max_remediation_cycles=3, max_blockers=3)),
        (EffectiveStageExecutionPolicy, resolved().model_dump(mode="json")),
    ):
        with pytest.raises(ValidationError):
            model.model_validate({**payload, field: None})


@pytest.mark.parametrize("value", ["ASK_OWNER_AND_FREEZE", "abort", "retry", "", 1, True])
def test_retry_exhaustion_is_closed(value: Any) -> None:
    """T-ORE: the sole spelling is persisted, without an alternate retry behavior."""
    assert list(OnRetryExhausted) == [OnRetryExhausted.ASK_OWNER_AND_FREEZE]
    for model in (ProjectExecutionDefaults, StageExecutionOverrides):
        with pytest.raises(ValidationError):
            model(schema_version=2, on_retry_exhausted=value)
    with pytest.raises(ValidationError):
        EffectiveStageExecutionPolicy.model_validate(
            {**resolved().model_dump(mode="json"), "on_retry_exhausted": value}
        )


def test_resolution_fixed_fields_and_unknown_identifiers() -> None:
    """T-EXT / T-SEVERITY / T-BLOCKERS / T-ROLE-UNKNOWN / T-ACCEPTED."""
    effective = resolved()
    assert (
        effective.max_remediation_cycles,
        effective.max_blockers,
        effective.max_owner_extensions,
    ) == (1, 3, 2)
    assert effective.on_retry_exhausted == "ask_owner_and_freeze"
    assert effective.blocking_severities == ["CRITICAL", "HIGH"]
    assert effective.defer_severities == ["MEDIUM", "LOW"]
    assert all(role.provider_id == "unknown-provider" for role in effective.roles.values())
    assert policy.MAX_ROLE_TIMEOUT_SECONDS == MAX_TIMEOUT_SECONDS == 43200
    assert hashlib.sha256(effective.canonical_bytes()).hexdigest() == effective.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_owner_extensions", 2),
        ("blocking_severities", ["CRITICAL", "HIGH"]),
        ("defer_severities", ["MEDIUM", "LOW"]),
        ("max_full_reviews", 1),
        ("max_discovery_reviews", 1),
        ("max_correction_rounds", 1),
        ("max_closure_reviews", 1),
        ("auto_commit", False),
        ("auto_push", False),
        ("git", {}),
        ("telegram", {}),
        ("hermes", {}),
        ("attestation", None),
        ("expiry", None),
        ("independence", False),
    ],
)
def test_fixed_and_future_fields_are_unrepresentable_inputs(field: str, value: Any) -> None:
    """T-EXT / T-SEVERITY / T-OPEN: even matching fixed values are forbidden keys."""
    for model in (ProjectExecutionDefaults, StageExecutionOverrides):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            model.model_validate(dict(schema_version=2, **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_owner_extensions", 1),
        ("max_owner_extensions", 3),
        ("max_owner_extensions", True),
        ("max_owner_extensions", "2"),
        ("max_owner_extensions", 2.0),
        ("blocking_severities", ["HIGH", "CRITICAL"]),
        ("blocking_severities", ["CRITICAL", "HIGH", "MEDIUM"]),
        ("blocking_severities", ["HIGH"]),
        ("blocking_severities", ["CRITICAL", "HIGH", "HIGH"]),
        ("defer_severities", ["LOW", "MEDIUM"]),
        ("defer_severities", ["LOW"]),
    ],
)
def test_policy_fixed_values_reject_mutation(field: str, value: Any) -> None:
    """T-EXT / T-SEVERITY."""
    with pytest.raises(ValidationError):
        EffectiveStageExecutionPolicy.model_validate(
            {**resolved().model_dump(mode="json"), field: value}
        )


def test_defaults_and_whole_role_overrides_follow_precedence() -> None:
    """T-RES-DEFAULTS / T-RES-OVERRIDE / T-RES-PARTIAL: no field-level role merge."""
    default_payload = dict(
        schema_version=2,
        max_remediation_cycles=2,
        max_blockers=2,
        on_retry_exhausted="ask_owner_and_freeze",
        roles=role_payloads(),
    )
    default_payload["roles"]["IMPLEMENTATION"] = selection(
        "default-provider", "Default:V2", capability_mode="WORKSPACE_WRITE"
    )
    defaults = ProjectExecutionDefaults.model_validate(default_payload)
    contract = StageContractBinding.model_validate(binding_payload())
    base = resolve_policy(
        defaults,
        StageExecutionOverrides(schema_version=2),
        contract,
        project_defaults_digest="b" * 64,
    )
    assert (base.max_remediation_cycles, base.max_blockers) == (2, 2)
    override = StageExecutionOverrides.model_validate(
        dict(
            schema_version=2,
            max_remediation_cycles=3,
            roles={"IMPLEMENTATION": selection("replacement", "new/Model+V1")},
        )
    )
    changed = resolve_policy(defaults, override, contract, project_defaults_digest="b" * 64)
    assert (changed.max_remediation_cycles, changed.max_blockers) == (3, 2)
    assert changed.roles[ProviderRole.IMPLEMENTATION].capability_mode is CapabilityMode.READ_ONLY
    for role in ProviderRole:
        assert changed.roles[role] == (
            override.roles[role] if role in override.roles else defaults.roles[role]
        )
    assert changed.project_defaults_digest == "b" * 64
    assert changed.stage_overrides_digest == canonical_digest(override.model_dump(mode="json"))
    for missing in ("provider_id", "model_id", "timeout_seconds"):
        incomplete = selection()
        incomplete.pop(missing)
        with pytest.raises(ValidationError):
            StageExecutionOverrides.model_validate(
                dict(schema_version=2, roles={"REVIEW": incomplete})
            )
    all_overrides = StageExecutionOverrides.model_validate(
        dict(
            schema_version=2,
            max_remediation_cycles=1,
            max_blockers=1,
            on_retry_exhausted="ask_owner_and_freeze",
            roles={role.value: selection("override", role.value) for role in ProviderRole},
        )
    )
    all_changed = resolve_policy(defaults, all_overrides, contract, project_defaults_digest=None)
    assert (all_changed.max_remediation_cycles, all_changed.max_blockers) == (1, 1)
    assert all_changed.roles == all_overrides.roles


@pytest.mark.parametrize("field", ["max_remediation_cycles", "max_blockers"])
def test_explicit_override_refuses_ceiling_while_defaults_are_capped(field: str) -> None:
    """T-RES-CEILING / T-BLOCKERS: named exact refusal, never silent override reduction."""
    payload = binding_payload()
    payload["ceilings"][field] = 2
    contract = StageContractBinding.model_validate(payload)
    defaults = ProjectExecutionDefaults.model_validate(
        dict(schema_version=2, roles=role_payloads(), **{field: 3})
    )
    effective = resolve_policy(
        defaults, StageExecutionOverrides(schema_version=2), contract, project_defaults_digest=None
    )
    assert getattr(effective, field) == 2
    with pytest.raises(ValueError, match=rf"{field} 3.*ceiling 2") as error:
        resolve_policy(
            defaults,
            StageExecutionOverrides.model_validate(dict(schema_version=2, **{field: 3})),
            contract,
            project_defaults_digest=None,
        )
    assert error.value.stop_reason is StopReason.INVALID_CONFIGURATION


def test_builtins_are_used_without_default_file_and_missing_roles_refuse() -> None:
    """T-RES-BUILTIN / T-RES-CEILING: no implicit provider or model exists."""
    _, empty, contract = policy_inputs()
    with pytest.raises(ValueError, match="no selection for role IMPLEMENTATION") as error:
        resolve_policy(None, empty, contract, project_defaults_digest=None)
    assert error.value.stop_reason is StopReason.INVALID_CONFIGURATION
    roles_only = StageExecutionOverrides.model_validate(
        dict(schema_version=2, roles=role_payloads())
    )
    result = resolve_policy(None, roles_only, contract, project_defaults_digest=None)
    assert (result.max_remediation_cycles, result.max_blockers, result.on_retry_exhausted) == (
        1,
        3,
        "ask_owner_and_freeze",
    )
    payload = binding_payload()
    payload["ceilings"]["max_blockers"] = 2
    capped = resolve_policy(
        None, roles_only, StageContractBinding.model_validate(payload), project_defaults_digest=None
    )
    assert capped.max_blockers == 2


@pytest.mark.parametrize(
    "default_cycles,override_cycles,ceiling,blockers,role_source",
    itertools.product(
        (None, 1, 2, 3),
        (None, 1, 2, 3),
        (1, 2, 3),
        (None, 1, 2, 3),
        ("defaults", "overrides", "mixed"),
    ),
)
def test_resolution_is_exhaustively_deterministic(
    default_cycles: int | None,
    override_cycles: int | None,
    ceiling: int,
    blockers: int | None,
    role_source: str,
) -> None:
    """T-RES-DET: 4 x 4 x 3 x 4 x 3 = 576 independently reconstructed pairs."""
    default_roles, override_roles = {}, {}
    for index, role in enumerate(ProviderRole):
        target = (
            default_roles
            if role_source == "defaults" or (role_source == "mixed" and index % 2 == 0)
            else override_roles
        )
        target[role.value] = selection("unknown-" + str(index), "Model/" + role.value)
    d = dict(
        schema_version=2,
        max_remediation_cycles=default_cycles,
        max_blockers=blockers,
        roles=default_roles,
    )
    o = dict(schema_version=2, max_remediation_cycles=override_cycles, roles=override_roles)
    c = binding_payload()
    c["ceilings"] = dict(max_remediation_cycles=ceiling, max_blockers=ceiling)
    outcomes = []
    for _ in range(2):
        defaults = ProjectExecutionDefaults.model_validate(copy.deepcopy(d))
        overrides = StageExecutionOverrides.model_validate(copy.deepcopy(o))
        contract = StageContractBinding.model_validate(copy.deepcopy(c))
        if override_cycles is not None and override_cycles > ceiling:
            with pytest.raises(ValueError) as error:
                resolve_policy(defaults, overrides, contract, project_defaults_digest="b" * 64)
            assert error.value.stop_reason is StopReason.INVALID_CONFIGURATION
            outcomes.append((type(error.value), str(error.value), error.value.stop_reason))
        else:
            result = resolve_policy(defaults, overrides, contract, project_defaults_digest="b" * 64)
            assert result.max_remediation_cycles == (
                override_cycles
                if override_cycles is not None
                else min(default_cycles or 1, ceiling)
            )
            assert result.max_blockers == min(blockers or 3, ceiling)
            assert list(result.roles) == list(ProviderRole)
            assert result.max_owner_extensions == 2
            outcomes.append((result, result.digest, result.canonical_bytes()))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize(
    "role",
    ["IMPLEMENTER", "DISCOVERY_REVIEWER", "REMEDIATOR", "CLOSURE_VERIFIER", "unknown", "review", 1],
)
def test_role_keys_use_only_persisted_provider_vocabulary(role: Any) -> None:
    """T-ROLE-KEYS: program aliases never cross the persisted vocabulary boundary."""
    for model in (ProjectExecutionDefaults, StageExecutionOverrides):
        with pytest.raises(ValidationError):
            model.model_validate(dict(schema_version=2, roles={role: selection()}))
    payload = resolved().model_dump(mode="json")
    payload["roles"][role] = selection()
    with pytest.raises(ValidationError):
        EffectiveStageExecutionPolicy.model_validate(payload)


def test_role_keys_accept_any_subset_and_reject_duplicate_json_keys() -> None:
    """T-ROLE-KEYS: duplicate document members are caught before dict construction."""
    for count in range(5):
        roles = {role: selection() for role in list(ProviderRole)[:count]}
        for model in (ProjectExecutionDefaults, StageExecutionOverrides):
            assert set(model.model_validate(dict(schema_version=2, roles=roles)).roles) == set(
                roles
            )
    duplicate = '{"schema_version":2,"roles":{"REVIEW":' + json.dumps(selection())
    duplicate += ',"REVIEW":' + json.dumps(selection("second")) + "}}"
    with pytest.raises(ValueError, match="duplicate"):
        _loads_rejecting_duplicate_keys(duplicate)


def test_role_alias_is_exact_immutable_bijection() -> None:
    """T-ROLE-ALIAS."""
    assert dict(policy.PROGRAM_ROLE_TO_PROVIDER_ROLE) == {
        ProgramRole.IMPLEMENTER: ProviderRole.IMPLEMENTATION,
        ProgramRole.DISCOVERY_REVIEWER: ProviderRole.REVIEW,
        ProgramRole.REMEDIATOR: ProviderRole.CORRECTION,
        ProgramRole.CLOSURE_VERIFIER: ProviderRole.CLOSURE,
    }
    assert set(policy.PROGRAM_ROLE_TO_PROVIDER_ROLE.values()) == set(ProviderRole)
    with pytest.raises(TypeError):
        policy.PROGRAM_ROLE_TO_PROVIDER_ROLE[ProgramRole.IMPLEMENTER] = ProviderRole.REVIEW


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_id", "UPPER"),
        ("provider_id", "has space"),
        ("provider_id", "a..b"),
        ("provider_id", "a\n"),
        ("provider_id", "a\u202e"),
        ("provider_id", "a" * 65),
        ("provider_id", ""),
        ("provider_id", "a--b"),
        ("provider_id", "a_b"),
        ("model_id", "has space"),
        ("model_id", "a..b"),
        ("model_id", "a\x00b"),
        ("model_id", "a\u2066b"),
        ("model_id", "a\nb"),
        ("model_id", "a" * 129),
        ("model_id", ""),
        ("model_id", "/model"),
        ("model_id", "Ä-model"),
        ("timeout_seconds", 0),
        ("timeout_seconds", 43201),
        ("timeout_seconds", -1),
        ("timeout_seconds", "60"),
        ("timeout_seconds", 60.0),
        ("timeout_seconds", True),
        ("timeout_seconds", None),
        ("capability_mode", "FULL_ACCESS"),
        ("capability_mode", "READ_only"),
        ("capability_mode", 1),
    ],
)
def test_role_identity_grammar_and_timeout_are_strict(field: str, value: Any) -> None:
    """T-ROLE-GRAMMAR: ASCII grammar excludes whitespace, controls and bidi codepoints."""
    with pytest.raises(ValidationError):
        policy.RoleSelection.model_validate({**selection(), field: value})


def test_role_timeout_is_required_and_identity_boundaries_are_accepted() -> None:
    payload = selection()
    payload.pop("timeout_seconds")
    with pytest.raises(ValidationError):
        policy.RoleSelection.model_validate(payload)
    for timeout in (1, 43200):
        role = policy.RoleSelection(
            provider_id="a" * 64, model_id="A" * 128, timeout_seconds=timeout
        )
        assert role.capability_mode is CapabilityMode.READ_ONLY


@pytest.mark.parametrize("role", list(ProviderRole))
def test_reviewer_capability_is_read_only(role: ProviderRole) -> None:
    """T-ROLE-REVIEWER-RO: only implementation and correction admit workspace writes."""
    selection_override = {role.value: selection(capability_mode="WORKSPACE_WRITE")}
    if role in (ProviderRole.REVIEW, ProviderRole.CLOSURE):
        with pytest.raises(ValueError, match="READ_ONLY") as error:
            resolved(roles=selection_override)
        assert error.value.stop_reason is StopReason.INVALID_CONFIGURATION
    else:
        assert (
            resolved(roles=selection_override).roles[role].capability_mode
            is CapabilityMode.WORKSPACE_WRITE
        )


def test_role_identity_is_retained_through_authorization_and_policy_json(tmp_path: Path) -> None:
    """T-ROLE-IDENTITY / T-ROLE-UNKNOWN: well-formed unknown IDs stay verbatim."""
    overrides = StageExecutionOverrides.model_validate(
        dict(
            schema_version=2,
            roles={
                role.value: selection("new-provider-v999", "Unknown.Model_1:@/+-V2")
                for role in ProviderRole
            },
        )
    )
    _, _, contract = policy_inputs()
    effective = resolve_policy(None, overrides, contract, project_defaults_digest=None)
    auth = StageStartAuthorization.model_validate(authorization_payload(effective, overrides))
    path = tmp_path / "policy.json"
    path.write_bytes(auth.effective_policy.canonical_bytes())
    loaded = EffectiveStageExecutionPolicy.model_validate_json(path.read_bytes())
    assert loaded == effective
    assert all(
        role.provider_id == "new-provider-v999" and role.model_id == "Unknown.Model_1:@/+-V2"
        for role in loaded.roles.values()
    )


def test_policy_module_is_pure_and_no_catalog_symbol_exists() -> None:
    """T-ROLE-UNKNOWN: identity structure cannot acquire dispatch or catalog meaning."""
    root = Path(policy.__file__).parent
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Name, ast.Attribute, ast.FunctionDef, ast.ClassDef)):
                name = (
                    node.id
                    if isinstance(node, ast.Name)
                    else (node.attr if isinstance(node, ast.Attribute) else node.name)
                )
                assert "catalog" not in name.lower(), (path, name)
    tree = ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module == "ai_workflow_engine.milestone_runner.models" or not (
                node.module or ""
            ).startswith("ai_workflow_engine")
        if isinstance(node, ast.Import):
            assert not any(
                alias.name in {"os", "pathlib", "subprocess", "time"} for alias in node.names
            )


@pytest.mark.parametrize("field", list(authorization_payload()))
def test_authorization_every_persisted_field_is_integrity_bound(field: str) -> None:
    """T-AUTH-SELF: no persisted-field mutation is silently excluded from integrity."""
    original = authorization_payload()
    assert StageStartAuthorization.model_validate(original)
    payload = copy.deepcopy(original)
    value = payload[field]
    if isinstance(value, dict):
        if field == "effective_policy":
            value["max_blockers"] = 2
        elif field == "stage_overrides":
            value["max_blockers"] = 2
        elif field == "contract_ceilings":
            value["max_blockers"] = 2
        else:
            value.update(kind="GOVERNED_REGISTRY", path="docs/registry.md")
    elif field == "schema_version":
        payload[field] = 1
    elif field == "created_at":
        payload[field] = "2026-09-30T01:02:03Z"
    else:
        payload[field] = "b" * 64 if len(value) == 64 else value + "-CHANGED"
    with pytest.raises(ValidationError):
        StageStartAuthorization.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository_identity", "other--0123456789ab"),
        ("stage_id", "ST-08"),
        ("contract_path", "docs/other.md"),
        ("contract_sha256", "b" * 64),
        ("contract_ceilings", dict(max_remediation_cycles=2, max_blockers=3)),
        ("registry_context", dict(kind="GOVERNED_REGISTRY", path="docs/registry.md")),
    ],
)
def test_authorization_binding_mismatch_refuses_even_with_fresh_self_digests(
    field: str, value: Any
) -> None:
    """T-AUTH-SELF: the self hash cannot legitimize disagreement with the embedded policy."""
    payload = authorization_payload()
    payload[field] = value
    payload["stage_start_key"] = stage_start_key(
        payload["repository_identity"], payload["stage_id"], payload["contract_sha256"]
    )
    payload["stage_start_id"] = authority_digest(logical_authorization_payload(payload))
    payload["authorization_digest"] = authority_digest(
        {k: v for k, v in payload.items() if k != "authorization_digest"}
    )
    with pytest.raises(ValidationError, match="binding disagree"):
        StageStartAuthorization.model_validate(payload)


def test_authorization_logical_id_is_stable_but_full_digest_binds_clock() -> None:
    """T-AUTH-SELF: only top-level derived IDs and creation time leave the logical payload."""
    earlier = authorization_payload()
    later = authorization_payload(created_at="2026-09-30T01:02:03Z")
    assert earlier["stage_start_id"] == later["stage_start_id"]
    assert earlier["authorization_digest"] != later["authorization_digest"]
    assert StageStartAuthorization.model_validate(earlier)
    assert StageStartAuthorization.model_validate(later)
    assert canonical_digest({"created_at": "a"}) == canonical_digest({"created_at": "b"})
    assert authority_digest({"created_at": "a"}) != authority_digest({"created_at": "b"})
    assert authority_digest({"nested": {"created_at": "a"}}) != authority_digest(
        {"nested": {"created_at": "b"}}
    )
    assert authority_json_bytes({"b": "é", "a": {"created_at": "x"}}) == (
        '{"a":{"created_at":"x"},"b":"é"}'.encode()
    )
    for bad in (float("nan"), float("inf"), "\ud800"):
        with pytest.raises((ValueError, UnicodeError)):
            authority_json_bytes({"bad": bad})


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-02-30T01:02:03Z",
        "2026-13-01T01:02:03Z",
        "2026-09-29T25:02:03Z",
        "2026-09-29T01:02:60Z",
        "2026-09-29T01:02:03+00:00",
        "2026-09-29T01:02:03",
    ],
)
def test_authorization_requires_valid_utc_calendar_timestamp(timestamp: str) -> None:
    with pytest.raises(ValidationError):
        StageStartAuthorization.model_validate(authorization_payload(created_at=timestamp))


def test_registry_context_changes_policy_and_logical_authority_identity() -> None:
    """T-REGISTRY-CONTEXT-DIGEST: null/path A/path B are three different authorities."""
    policies, ids = [], []
    defaults, overrides, _ = policy_inputs()
    for path in (None, "docs/registry-a.md", "docs/registry-b.md"):
        payload = binding_payload()
        payload["registry_context"] = dict(
            kind="NO_GOVERNED_REGISTRY" if path is None else "GOVERNED_REGISTRY", path=path
        )
        effective = resolve_policy(
            defaults,
            overrides,
            StageContractBinding.model_validate(payload),
            project_defaults_digest=None,
        )
        auth = StageStartAuthorization.model_validate(authorization_payload(effective))
        policies.append(effective)
        ids.append(auth.stage_start_id)
        for model, document in (
            (EffectiveStageExecutionPolicy, effective.model_dump(mode="json")),
            (StageStartAuthorization, auth.model_dump(mode="json")),
        ):
            document.pop("registry_context")
            with pytest.raises(ValidationError):
                model.model_validate(document)
    assert len({item.digest for item in policies}) == len(set(ids)) == 3


def all_policy_documents() -> list[tuple[type[policy.FrozenPolicyModel], dict[str, Any]]]:
    effective = resolved()
    authorization = authorization_payload(effective)
    pointer = {
        key: authorization[key]
        for key in ("schema_version", "stage_start_key", "stage_start_id", "authorization_digest")
    }
    binding = dict(**pointer, policy_digest=effective.digest, run_id="example-run")
    binding["binding_digest"] = authority_digest(binding)
    return [
        (policy.RoleSelection, selection()),
        (ProjectExecutionDefaults, dict(schema_version=2, roles=role_payloads())),
        (StageExecutionOverrides, dict(schema_version=2, roles=role_payloads())),
        (ContractExecutionCeilings, dict(max_remediation_cycles=3, max_blockers=3)),
        (RegistryAuthorityContext, dict(kind="NO_GOVERNED_REGISTRY", path=None)),
        (StageContractBinding, binding_payload()),
        (EffectiveStageExecutionPolicy, effective.model_dump(mode="json")),
        (StageStartAuthorization, authorization),
        (StageStartPointer, pointer),
        (StageStartBinding, binding),
    ]


@pytest.mark.parametrize("version", [0, 1, 3, "2", 2.0, True, None, "missing"])
def test_every_versioned_policy_document_requires_exact_two(version: Any) -> None:
    for model, payload in all_policy_documents():
        if "schema_version" not in payload:
            continue
        if version == "missing":
            payload.pop("schema_version")
        else:
            payload["schema_version"] = version
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_every_policy_schema_is_closed_and_frozen() -> None:
    for model, payload in all_policy_documents():
        with pytest.raises(ValidationError, match="extra_forbidden"):
            model.model_validate({**payload, "unknown": 1})
        value = model.model_validate(payload)
        name = next(iter(model.model_fields))
        with pytest.raises(ValidationError, match="frozen_instance"):
            setattr(value, name, getattr(value, name))
        assert model.model_config["strict"] is True
        assert model.model_config["extra"] == "forbid"


def test_effective_policy_is_deeply_immutable() -> None:
    """INV-017-1 / INV-017-15: ordinary nested mutators cannot change frozen evidence."""
    effective = resolved()
    original = effective.canonical_bytes()
    with pytest.raises(ValidationError):
        effective.max_blockers = 1
    for mutate in (
        lambda: effective.roles.clear(),
        lambda: effective.roles.pop(ProviderRole.REVIEW),
        lambda: effective.roles.update(
            {ProviderRole.REVIEW: effective.roles[ProviderRole.CLOSURE]}
        ),
        lambda: effective.roles.__setitem__(
            ProviderRole.REVIEW, effective.roles[ProviderRole.CLOSURE]
        ),
        lambda: effective.roles.__delitem__(ProviderRole.REVIEW),
        lambda: effective.roles.__ior__(
            {ProviderRole.REVIEW: effective.roles[ProviderRole.CLOSURE]}
        ),
        lambda: effective.blocking_severities.append(FindingSeverity.LOW),
        lambda: effective.blocking_severities.reverse(),
        lambda: effective.blocking_severities.__setitem__(0, FindingSeverity.LOW),
        lambda: effective.blocking_severities.__iadd__([FindingSeverity.LOW]),
        lambda: effective.blocking_severities.__imul__(2),
    ):
        with pytest.raises(TypeError):
            mutate()
    for nested, field, value in (
        (effective.roles[ProviderRole.REVIEW], "model_id", "changed"),
        (effective.contract_ceilings, "max_blockers", 1),
        (effective.registry_context, "path", "docs/registry.md"),
    ):
        with pytest.raises(ValidationError):
            setattr(nested, field, value)
    exported = effective.model_dump(mode="json")
    exported["roles"].clear()
    assert effective.canonical_bytes() == original
    auth = StageStartAuthorization.model_validate(authorization_payload())
    with pytest.raises(TypeError):
        auth.stage_overrides.roles.clear()


@pytest.mark.parametrize("stage_id", POSITIVE_STAGE_IDS)
def test_generalized_stage_and_milestone_ids_are_accepted(stage_id: str) -> None:
    """T-STAGE-ID: project-scoped grammar, full bounds, no legacy-only dependency."""
    assert STAGE_ID_RE.fullmatch(stage_id)
    assert MILESTONE_ID_RE.fullmatch(stage_id + "-M01")
    StageContractBinding.model_validate({**binding_payload(), "stage_id": stage_id})
    assert bool(LEGACY_STAGE_ID_RE.fullmatch(stage_id)) == stage_id.startswith("AUTO-")
    assert bool(LEGACY_MILESTONE_ID_RE.fullmatch(stage_id + "-M01")) == stage_id.startswith("AUTO-")


@pytest.mark.parametrize("stage_id", NEGATIVE_STAGE_IDS)
def test_generalized_stage_and_milestone_ids_refuse_hostile_grammar(stage_id: str) -> None:
    """T-STAGE-ID: suffix ambiguity, length, separators, Unicode and controls refuse."""
    assert STAGE_ID_RE.fullmatch(stage_id) is None
    assert MILESTONE_ID_RE.fullmatch(stage_id + "-M01") is None
    with pytest.raises(ValidationError):
        StageContractBinding.model_validate({**binding_payload(), "stage_id": stage_id})


@pytest.mark.parametrize("stage_id", (*POSITIVE_STAGE_IDS, *NEGATIVE_STAGE_IDS))
def test_prompt_context_uses_same_generalized_stage_grammar(stage_id: str) -> None:
    """T-PROMPT-STAGE-ID: prompt construction cannot reject a valid v2 Stage."""
    payload = dict(
        run_id="run-1",
        stage_id=stage_id,
        repository_root="/repository",
        expected_branch="work",
        baseline_sha="a" * 40,
        contract_path="docs/contract.md",
        contract_sha256="b" * 64,
    )
    if stage_id in POSITIVE_STAGE_IDS:
        assert PromptContext.model_validate(payload).stage_id == stage_id
    else:
        with pytest.raises(ValidationError):
            PromptContext.model_validate(payload)


def test_open_owner_decisions_remain_structurally_unencoded() -> None:
    """T-OPEN: inspect every new §7 model and enum, and the complete StopReason enum."""
    forbidden = (
        "auto_commit",
        "auto_push",
        "commit",
        "push",
        "attest",
        "nonce",
        "expiry",
        "expires",
        "telegram",
        "hermes",
        "independen",
        "reported_model",
        "fallback",
        "retry_cycle",
        "post_remediation",
        "worktree",
        "carry_forward",
        "patch",
        "closure_scope",
        "owner_decision_required",
        "superseded",
        "extend",
    )
    names = [name for model, _ in all_policy_documents() for name in model.model_fields]
    for value in vars(policy).values():
        if isinstance(value, type) and issubclass(value, Enum):
            names.extend(member.name for member in value)
            names.extend(str(member.value) for member in value)
    names.extend(member.value for member in StopReason)
    for name in names:
        assert not any(token in name.lower() for token in forbidden), name
    assert list(StartPrincipal) == [StartPrincipal.LOCAL_CLI]
    assert list(OnRetryExhausted) == [OnRetryExhausted.ASK_OWNER_AND_FREEZE]


def test_canonical_v1_bytes_and_literal_digest_remain_unchanged() -> None:
    """T-CANONICAL-UNCHANGED: timestamps drop recursively; enum and Unicode stay stable."""
    payload = {
        "z": [1, True, None, "é"],
        "a": {"created_at": "old", "state": "IDLE"},
        "updated_at": "new",
    }
    expected = '{"a":{"state":"IDLE"},"z":[1,true,null,"é"]}'.encode()
    assert canonical_json_bytes(payload) == expected
    assert canonical_digest(payload) == hashlib.sha256(expected).hexdigest()
    assert (
        canonical_digest({"a": 1})
        == "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"
    )


def vector_policy(index: int) -> EffectiveStageExecutionPolicy:
    defaults, overrides, contract = policy_inputs()
    default_digest = None
    if index == 1:
        overrides = StageExecutionOverrides.model_validate(
            dict(
                schema_version=2,
                max_remediation_cycles=3,
                max_blockers=1,
                roles={
                    "IMPLEMENTATION": selection(
                        "another-provider",
                        "Vendor/Model:2026+v1",
                        capability_mode="WORKSPACE_WRITE",
                    )
                },
            )
        )
        payload = binding_payload()
        payload["registry_context"] = dict(kind="GOVERNED_REGISTRY", path="docs/registry-a.md")
        contract = StageContractBinding.model_validate(payload)
        default_digest = "b" * 64
    elif index == 2:
        defaults = ProjectExecutionDefaults.model_validate(
            dict(
                schema_version=2,
                max_remediation_cycles=3,
                max_blockers=3,
                roles={
                    role.value: selection("unlisted", role.value + "@model/v7")
                    for role in ProviderRole
                },
            )
        )
        payload = binding_payload()
        payload.update(
            stage_id="AWE-AUTO-ST-01",
            contract_sha256="c" * 64,
            ceilings=dict(max_remediation_cycles=2, max_blockers=2),
        )
        contract = StageContractBinding.model_validate(payload)
        default_digest = "d" * 64
    return resolve_policy(defaults, overrides, contract, project_defaults_digest=default_digest)


@pytest.mark.parametrize(
    "index,expected",
    [
        (0, "3b0286a4defb7183644183dcf1aabcfd15a449186050851199819a928dcb437b"),
        (1, "7193bd03e06429fca66146d7e923cbca94deac2f9184e315fa6e27e1e7e9ae07"),
        (2, "77d817cbacb32d3329d0f4c879dc631d8b574739d2d9f209523332a6e26bf099"),
    ],
)
def test_fixed_policy_digest_vectors(index: int, expected: str) -> None:
    """T-DIGEST-VECTORS: literal stable vectors, independent byte-level SHA-256 agreement."""
    effective = vector_policy(index)
    assert effective.digest == expected
    assert hashlib.sha256(effective.canonical_bytes()).hexdigest() == expected
    assert (
        EffectiveStageExecutionPolicy.model_validate_json(effective.canonical_bytes()) == effective
    )
