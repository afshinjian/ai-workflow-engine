"""Unit tests for the schema registry and the `cli-contract` schema it hosts."""

import pytest
from pydantic import BaseModel, ValidationError

from ai_workflow_engine.exceptions import UnknownSchemaNameError, UnsupportedSchemaVersionError
from ai_workflow_engine.schema.contract import (
    CLI_CONTRACT_REGISTRY,
    CLI_CONTRACT_SCHEMA_NAME,
    CliContractV1,
    ContractEnvelopeV2,
    ContractErrorV2,
    error_envelope,
    resolve_contract_version,
    success_envelope,
)
from ai_workflow_engine.schema.registry import SchemaRegistry


class Widget(BaseModel):
    name: str
    count: int


class WidgetV2(BaseModel):
    label: str


def test_register_and_get_returns_the_registered_model() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    assert registry.get("widget", "1.0.0") is Widget


def test_dispatch_validates_payload_against_the_registered_model() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    instance = registry.dispatch("widget", "1.0.0", {"name": "gear", "count": 3})
    assert isinstance(instance, Widget)
    assert instance.name == "gear"
    assert instance.count == 3


def test_dispatch_rejects_a_payload_that_fails_model_validation() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    with pytest.raises(ValidationError):
        registry.dispatch("widget", "1.0.0", {"name": "gear"})


def test_unknown_schema_name_fails_closed() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    with pytest.raises(UnknownSchemaNameError):
        registry.get("gadget", "1.0.0")
    with pytest.raises(UnknownSchemaNameError):
        registry.dispatch("gadget", "1.0.0", {})
    with pytest.raises(UnknownSchemaNameError):
        registry.versions("gadget")


def test_unsupported_schema_version_fails_closed() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    with pytest.raises(UnsupportedSchemaVersionError):
        registry.get("widget", "9.9.9")
    with pytest.raises(UnsupportedSchemaVersionError):
        registry.dispatch("widget", "9.9.9", {"name": "gear", "count": 1})


def test_duplicate_registration_is_rejected() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("widget", "1.0.0", Widget)


def test_multiple_versions_of_the_same_name_coexist() -> None:
    registry = SchemaRegistry()
    registry.register("widget", "1.0.0", Widget)
    registry.register("widget", "2.0.0", WidgetV2)
    assert registry.versions("widget") == ("1.0.0", "2.0.0")
    assert registry.get("widget", "1.0.0") is Widget
    assert registry.get("widget", "2.0.0") is WidgetV2


def test_names_and_versions_report_only_registered_entries() -> None:
    registry = SchemaRegistry()
    assert registry.names() == ()
    registry.register("widget", "1.0.0", Widget)
    registry.register("gadget", "3.0.0", WidgetV2)
    assert registry.names() == ("gadget", "widget")
    assert registry.versions("gadget") == ("3.0.0",)


def test_cli_contract_schema_has_exactly_v1_and_v2_registered() -> None:
    assert CLI_CONTRACT_REGISTRY.versions(CLI_CONTRACT_SCHEMA_NAME) == ("1.0.0", "2.0.0")
    assert CLI_CONTRACT_REGISTRY.get(CLI_CONTRACT_SCHEMA_NAME, "1.0.0") is CliContractV1
    assert CLI_CONTRACT_REGISTRY.get(CLI_CONTRACT_SCHEMA_NAME, "2.0.0") is ContractEnvelopeV2


def test_cli_contract_v1_accepts_any_open_shaped_payload() -> None:
    # The legacy shape is intentionally unenveloped and command-specific; the schema
    # accepts arbitrary fields rather than enforcing a single cross-command shape.
    instance = CLI_CONTRACT_REGISTRY.dispatch(
        CLI_CONTRACT_SCHEMA_NAME, "1.0.0", {"check_name": "git", "status": "PASS", "extra": 1}
    )
    assert isinstance(instance, CliContractV1)


def test_cli_contract_v2_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CLI_CONTRACT_REGISTRY.dispatch(
            CLI_CONTRACT_SCHEMA_NAME,
            "2.0.0",
            {
                "contract_version": "2.0.0",
                "command": "verify",
                "ok": True,
                "data": {},
                "error": None,
                "warnings": [],
                "unexpected": "field",
            },
        )


@pytest.mark.parametrize("alias", ["1", "1.0.0"])
def test_resolve_contract_version_accepts_v1_aliases(alias: str) -> None:
    assert resolve_contract_version(alias) == "1.0.0"


@pytest.mark.parametrize("alias", ["2", "2.0.0"])
def test_resolve_contract_version_accepts_v2_aliases(alias: str) -> None:
    assert resolve_contract_version(alias) == "2.0.0"


@pytest.mark.parametrize("value", ["3", "3.0.0", "v2", "", "2.0.1"])
def test_resolve_contract_version_fails_closed_on_unsupported_input(value: str) -> None:
    with pytest.raises(UnsupportedSchemaVersionError):
        resolve_contract_version(value)


def test_success_envelope_shape() -> None:
    envelope = success_envelope(command="verify", data={"status": "PASS"})
    assert envelope.contract_version == "2.0.0"
    assert envelope.command == "verify"
    assert envelope.ok is True
    assert envelope.data == {"status": "PASS"}
    assert envelope.error is None
    assert envelope.warnings == []


def test_error_envelope_shape() -> None:
    envelope = error_envelope(
        command="check-git",
        code="CHECK_FAIL",
        message="branch mismatch",
        retryable=False,
        details={"findings": []},
    )
    assert envelope.ok is False
    assert envelope.data is None
    assert isinstance(envelope.error, ContractErrorV2)
    assert envelope.error.code == "CHECK_FAIL"
    assert envelope.error.message == "branch mismatch"
    assert envelope.error.retryable is False
    assert envelope.error.details == {"findings": []}


# --- Finding C: contradictory ok/data/error combinations are rejected ----------------------


def test_ok_true_with_null_data_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ok=true"):
        ContractEnvelopeV2(command="x", ok=True, data=None, error=None)


def test_ok_true_with_an_error_present_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ok=true"):
        ContractEnvelopeV2(
            command="x",
            ok=True,
            data={"a": 1},
            error=ContractErrorV2(code="C", message="m"),
        )


def test_ok_false_with_data_present_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ok=false"):
        ContractEnvelopeV2(command="x", ok=False, data={"a": 1}, error=None)


def test_ok_false_with_null_error_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ok=false"):
        ContractEnvelopeV2(command="x", ok=False, data=None, error=None)


def test_ok_true_with_data_and_no_error_is_accepted() -> None:
    envelope = ContractEnvelopeV2(command="x", ok=True, data={"a": 1}, error=None)
    assert envelope.ok is True


def test_ok_false_with_error_and_no_data_is_accepted() -> None:
    envelope = ContractEnvelopeV2(
        command="x", ok=False, data=None, error=ContractErrorV2(code="C", message="m")
    )
    assert envelope.ok is False


def test_contradictory_combination_rejected_via_registry_dispatch() -> None:
    # The same guard applies when the envelope is constructed by model_validate
    # through the schema registry (e.g. external/untrusted input), not just via the
    # success_envelope/error_envelope builders.
    with pytest.raises(ValidationError, match="ok=true"):
        CLI_CONTRACT_REGISTRY.dispatch(
            CLI_CONTRACT_SCHEMA_NAME,
            "2.0.0",
            {
                "contract_version": "2.0.0",
                "command": "x",
                "ok": True,
                "data": None,
                "error": None,
                "warnings": [],
            },
        )


def test_success_and_error_envelope_builders_always_satisfy_the_invariant() -> None:
    # success_envelope/error_envelope never construct a contradictory shape, so this
    # is a regression guard rather than a new behavior.
    assert success_envelope(command="x", data={}).ok is True
    assert error_envelope(command="x", code="C", message="m").ok is False
