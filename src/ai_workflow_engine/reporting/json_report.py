from pydantic import BaseModel

from ai_workflow_engine.result import Finding, Status
from ai_workflow_engine.schema.contract import error_envelope, success_envelope


def render_json(model: BaseModel) -> str:
    """Stable field order and formatting for CI consumers."""
    return model.model_dump_json(indent=2, exclude_none=False)


def render_contract_json(
    *,
    command: str,
    contract_version: str,
    model: BaseModel,
    status: Status,
    summary: str,
    findings: list[Finding],
) -> str:
    """Render ``model`` as exactly one JSON document, in the requested contract version.

    Contract ``1.0.0`` preserves the pre-existing, unenveloped shape byte-for-byte.
    Contract ``2.0.0`` wraps it in the stable envelope described by
    architecture-v3.md section 14. The caller must resolve ``contract_version``
    against the schema registry first (see
    ``schema.contract.resolve_contract_version``), so an unknown/unsupported
    version fails closed before this function ever runs.
    """
    if contract_version == "1.0.0":
        return render_json(model)
    if status == Status.PASS:
        envelope = success_envelope(command=command, data=model.model_dump(mode="json"))
    else:
        envelope = error_envelope(
            command=command,
            code=f"CHECK_{status.value}",
            message=summary,
            retryable=status == Status.ERROR,
            details={"findings": [finding.model_dump(mode="json") for finding in findings]},
        )
    return render_json(envelope)
