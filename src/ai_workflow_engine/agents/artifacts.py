"""Tamper-evident storage of agent-run records (Milestone 3, task T-305).

Every completed run — PASS or FAIL — is stored as a closed :class:`AgentRunRecord` sidecar plus a
``.patch`` member, using the Milestone 2 atomic no-clobber protocol. The exact captured
stdout/stderr bytes are stored base64-encoded so every digest in the record is recomputable at
load time; ``run_id`` is the content hash of the record with its own ``run_id`` excluded. See
``docs/milestone-3-plan.md``.
"""

import base64
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Literal

from pydantic import ValidationError, field_validator

from ai_workflow_engine.agents.runner import RunObservation
from ai_workflow_engine.models import StrictModel, WorkflowStage
from ai_workflow_engine.prompt.models import (
    WORKFLOW_STAGES,
    CanonicalFinding,
    JsonValue,
    canonicalize_json_value,
)
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.result import CheckResult
from ai_workflow_engine.workflow.event_store import task_dir_name

_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_HEX16_RE = re.compile(r"[0-9a-f]{16}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")


class ArtifactError(ValueError):
    code = "artifact_error"


class StoredVerification(StrictModel):
    """A timestamp-free, canonical snapshot of an agent-run verification ``CheckResult``.

    ``CanonicalCheckResult`` fixes ``check_name`` to the four inspection checks, so the
    ``agent-run`` verification needs its own closed, deterministic (no-timestamp) shape.
    """

    check_name: Literal["agent-run"]
    status: Literal["PASS", "FAIL", "ERROR"]
    summary: str
    findings: list[CanonicalFinding]
    evidence: dict[str, JsonValue]
    affected_paths: list[str]
    remediation_hint: str | None


class AgentRunRecord(StrictModel):
    schema_version: Literal["1.0"]
    run_id: str
    project_id: str
    task_id: str
    stage: WorkflowStage
    prompt_id: str
    repository_head: str
    agent_name: str
    agent_mode: Literal["read-only", "scoped-write"]
    agent_executable: str
    agent_args: list[str]
    timeout_seconds: int
    ok: bool
    failure_code: str | None
    exit_code: int | None
    stdout_b64: str
    stdout_sha256: str
    stderr_b64: str
    stderr_sha256: str
    patch_sha256: str
    verification: StoredVerification

    @field_validator("run_id")
    @classmethod
    def _validate_run_id(cls, value: str) -> str:
        if not _HEX16_RE.fullmatch(value):
            raise ValueError("run_id must be 16 lowercase hex characters")
        return value

    @field_validator("stdout_sha256", "stderr_sha256", "patch_sha256")
    @classmethod
    def _validate_hex64(cls, value: str) -> str:
        if not _HEX64_RE.fullmatch(value):
            raise ValueError("digest must be 64 lowercase hex characters")
        return value


def _artifact_root() -> Path:
    return Path("~/.ai-workflow-engine/workflow-runs/agent-runs").expanduser()


def _canonical_check(result: CheckResult) -> StoredVerification:
    payload = result.model_dump(mode="json")
    payload.pop("timestamp", None)
    payload["evidence"] = canonicalize_json_value(payload.get("evidence", {}))
    return StoredVerification.model_validate(payload)


def _record_hash_payload(record: AgentRunRecord) -> bytes:
    payload = record.model_dump(mode="json")
    payload.pop("run_id")
    return canonical_json(payload)


def compute_run_id(record: AgentRunRecord) -> str:
    return hashlib.sha256(_record_hash_payload(record)).hexdigest()[:16]


def build_record(
    observation: RunObservation, verification: CheckResult, *, project_id: str
) -> tuple[AgentRunRecord, bytes]:
    """Assemble the closed record (computed ``run_id``) and return it with the patch bytes."""
    patch = observation.patch
    draft = AgentRunRecord(
        schema_version="1.0",
        run_id="0" * 16,  # placeholder; replaced by the content hash below
        project_id=project_id,
        task_id=observation.task_id,
        stage=observation.stage,
        prompt_id=observation.prompt_id,
        repository_head=observation.repository_head,
        agent_name=observation.agent_name,
        agent_mode=observation.agent_mode,  # type: ignore[arg-type]
        agent_executable=observation.agent_executable,
        agent_args=list(observation.agent_args),
        timeout_seconds=observation.timeout_seconds,
        ok=observation.ok,
        failure_code=observation.failure_code,
        exit_code=observation.exit_code,
        stdout_b64=base64.b64encode(observation.stdout).decode("ascii"),
        stdout_sha256=hashlib.sha256(observation.stdout).hexdigest(),
        stderr_b64=base64.b64encode(observation.stderr).decode("ascii"),
        stderr_sha256=hashlib.sha256(observation.stderr).hexdigest(),
        patch_sha256=hashlib.sha256(patch).hexdigest(),
        verification=_canonical_check(verification),
    )
    run_id = compute_run_id(draft)
    record = draft.model_copy(update={"run_id": run_id})
    return record, patch


def _record_bytes(record: AgentRunRecord) -> bytes:
    return canonical_json(record.model_dump(mode="json")) + b"\n"


def _run_directory(project_id: str, task_id: str, stage: str) -> Path:
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise ArtifactError(f"Invalid project_id for artifact addressing: {project_id!r}")
    if stage not in WORKFLOW_STAGES:
        raise ArtifactError(f"Invalid stage for artifact addressing: {stage!r}")
    root = _artifact_root().resolve(strict=False)
    directory = (root / project_id / task_dir_name(task_id) / stage).resolve(strict=False)
    if not directory.is_relative_to(root):
        raise ArtifactError("Artifact directory escapes the artifact root")
    return directory


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written == 0:
            raise OSError("os.write made zero progress while writing an artifact temporary file")
        view = view[written:]


def _create_temp(directory: Path, suffix: str, data: bytes) -> Path:
    while True:
        candidate = directory / f".{uuid.uuid4().hex}{suffix}"
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        break
    try:
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        candidate.unlink(missing_ok=True)
        raise
    return candidate


def _link_no_clobber(temp: Path, final: Path, expected: bytes, kind: str) -> None:
    try:
        os.link(temp, final)
    except FileExistsError:
        if final.read_bytes() != expected:
            raise ArtifactError(f"{kind} collision at {final}: existing bytes differ") from None
    if final.read_bytes() != expected:
        raise ArtifactError(f"{kind} final does not match after publication: {final}")


def save_run(record: AgentRunRecord, patch: bytes, *, repository: str) -> tuple[Path, Path]:
    """Publish the record + patch pair atomically. Returns (record_path, patch_path)."""
    if compute_run_id(record) != record.run_id:
        raise ArtifactError("run_id does not match the record's content hash")
    if hashlib.sha256(patch).hexdigest() != record.patch_sha256:
        raise ArtifactError("patch bytes do not match the record's patch_sha256")

    directory = _run_directory(record.project_id, record.task_id, record.stage)
    repository_root = Path(repository).resolve(strict=False)
    if directory == repository_root or directory.is_relative_to(repository_root):
        raise ArtifactError("Artifact directory must not be inside the target repository")
    record_final = directory / f"{record.run_id}.json"
    patch_final = directory / f"{record.run_id}.patch"
    record_data = _record_bytes(record)
    directory.mkdir(parents=True, exist_ok=True)

    record_temp: Path | None = None
    patch_temp: Path | None = None
    try:
        record_temp = _create_temp(directory, ".json.tmp", record_data)
        patch_temp = _create_temp(directory, ".patch.tmp", patch)
        _link_no_clobber(record_temp, record_final, record_data, "Record")
        _link_no_clobber(patch_temp, patch_final, patch, "Patch")
    finally:
        if record_temp is not None:
            record_temp.unlink(missing_ok=True)
        if patch_temp is not None:
            patch_temp.unlink(missing_ok=True)
    return record_final, patch_final


def _parse_json_no_duplicate_keys(text: str) -> object:
    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ArtifactError(f"Duplicate JSON key in agent-run record: {key!r}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


def run_patch_path(project_id: str, task_id: str, stage: WorkflowStage, run_id: str) -> Path:
    """The resolved path of a stored run's ``.patch`` member (addressing only; no verification)."""
    if not _HEX16_RE.fullmatch(run_id):
        raise ArtifactError(f"Invalid run_id: {run_id!r}")
    return _run_directory(project_id, task_id, stage) / f"{run_id}.patch"


def load_run(project_id: str, task_id: str, stage: WorkflowStage, run_id: str) -> AgentRunRecord:
    """Load and fully re-verify a stored agent-run record."""
    if not _HEX16_RE.fullmatch(run_id):
        raise ArtifactError(f"Invalid run_id: {run_id!r}")
    directory = _run_directory(project_id, task_id, stage)
    record_final = directory / f"{run_id}.json"
    patch_final = directory / f"{run_id}.patch"
    if not record_final.exists() or not patch_final.exists():
        raise ArtifactError("Incomplete agent-run artifact: missing member")

    raw = record_final.read_bytes()
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise ArtifactError("Stored record must have exactly one terminal newline")
    parsed = _parse_json_no_duplicate_keys(raw[:-1].decode("utf-8"))
    try:
        record = AgentRunRecord.model_validate(parsed)
    except ValidationError as exc:
        raise ArtifactError(f"Stored record is not a valid AgentRunRecord: {exc}") from exc
    if _record_bytes(record) != raw:
        raise ArtifactError("Stored record is not in canonical form")
    if record.run_id != run_id:
        raise ArtifactError("Stored record run_id does not match its address")
    if compute_run_id(record) != record.run_id:
        raise ArtifactError("Stored record run_id does not match its content hash")

    patch = patch_final.read_bytes()
    if hashlib.sha256(patch).hexdigest() != record.patch_sha256:
        raise ArtifactError("Stored patch does not match the record's patch_sha256")
    if hashlib.sha256(base64.b64decode(record.stdout_b64)).hexdigest() != record.stdout_sha256:
        raise ArtifactError("Stored stdout digest mismatch")
    if hashlib.sha256(base64.b64decode(record.stderr_b64)).hexdigest() != record.stderr_sha256:
        raise ArtifactError("Stored stderr digest mismatch")
    return record
