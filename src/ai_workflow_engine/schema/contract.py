"""The `workflowctl` CLI JSON contract, registered as schema ``cli-contract``.

Version ``1.0.0`` is the pre-existing, unenveloped, command-specific JSON shape
(``CheckResult``, ``VerificationReport``, and so on): kept available unchanged so
existing consumers never need to migrate. Version ``2.0.0`` is the stable envelope
from architecture-v3.md section 14: ``{contract_version, command, ok, data, error,
warnings}``, with errors carrying a stable ``code``/``message``/``retryable``/
``details``. Requesting any other version fails closed via the schema registry.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_workflow_engine.schema.registry import SchemaRegistry

CLI_CONTRACT_SCHEMA_NAME = "cli-contract"


class CliContractV1(BaseModel):
    """The legacy, pre-contract CLI JSON shape: an open, command-specific object."""

    model_config = ConfigDict(extra="allow")


class ContractErrorV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ContractEnvelopeV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2.0.0"] = "2.0.0"
    command: str
    ok: bool
    data: dict[str, Any] | None = None
    error: ContractErrorV2 | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ok_matches_data_and_error(self) -> Self:
        """Reject the contradictory combinations regardless of how the envelope is built.

        This runs on every construction path, including ``model_validate`` of
        external input (e.g. schema-registry dispatch) — not just the
        ``success_envelope``/``error_envelope`` builders below.
        """
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("ok=true requires data is not None and error is None")
        if not self.ok and (self.data is not None or self.error is None):
            raise ValueError("ok=false requires data is None and error is not None")
        return self


CLI_CONTRACT_REGISTRY = SchemaRegistry()
CLI_CONTRACT_REGISTRY.register(CLI_CONTRACT_SCHEMA_NAME, "1.0.0", CliContractV1)
CLI_CONTRACT_REGISTRY.register(CLI_CONTRACT_SCHEMA_NAME, "2.0.0", ContractEnvelopeV2)

_CONTRACT_VERSION_ALIASES = {"1": "1.0.0", "2": "2.0.0", "1.0.0": "1.0.0", "2.0.0": "2.0.0"}


def resolve_contract_version(value: str) -> str:
    """Resolve a user-supplied contract-version token to a registered schema version.

    Accepts the short aliases ``"1"``/``"2"`` and the full semver strings. Any other
    value — including a well-formed but unregistered version such as ``"3.0.0"`` —
    fails closed via the schema registry rather than silently defaulting.
    """
    version = _CONTRACT_VERSION_ALIASES.get(value, value)
    CLI_CONTRACT_REGISTRY.get(CLI_CONTRACT_SCHEMA_NAME, version)
    return version


def success_envelope(
    *, command: str, data: dict[str, Any], warnings: list[str] | None = None
) -> ContractEnvelopeV2:
    return ContractEnvelopeV2(
        command=command, ok=True, data=data, error=None, warnings=warnings or []
    )


def error_envelope(
    *,
    command: str,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> ContractEnvelopeV2:
    return ContractEnvelopeV2(
        command=command,
        ok=False,
        data=None,
        error=ContractErrorV2(
            code=code, message=message, retryable=retryable, details=details or {}
        ),
        warnings=warnings or [],
    )
