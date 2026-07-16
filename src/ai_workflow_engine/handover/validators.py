import hashlib
from enum import StrEnum

from ai_workflow_engine.config import normalize_repository_path, repository_path
from ai_workflow_engine.exceptions import (
    GitCommandError,
    InvalidConfigurationError,
    ManifestParseError,
)
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.handover.manifest import parse_manifest
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.result import CheckResult, Finding, Status


class HandoverSource(StrEnum):
    WORKING_TREE = "working-tree"
    STAGED = "staged"
    COMMIT = "commit"


def _read(
    config: EngineConfig, client: GitClient, source: HandoverSource, path: str, commit: str
) -> bytes:
    # Validate containment even for Git object paths; never allow repository escape syntax.
    path = normalize_repository_path(path)
    repository_path(
        config.project.repository, path, must_exist=source == HandoverSource.WORKING_TREE
    )
    if source == HandoverSource.WORKING_TREE:
        return (config.project.repository / path).read_bytes()
    if source == HandoverSource.STAGED:
        return client.read_index_blob(path)
    return client.read_commit_blob(commit, path)


def check_handover(
    config: EngineConfig,
    *,
    source: HandoverSource = HandoverSource.WORKING_TREE,
    commit: str = "HEAD",
) -> CheckResult:
    client = GitClient(config.project.repository)
    findings: list[Finding] = []
    verified: list[dict[str, object]] = []
    if source == HandoverSource.COMMIT:
        try:
            commit = client.resolve_commit(commit)
        except GitCommandError as exc:
            return CheckResult(
                check_name="handover",
                status=Status.ERROR,
                summary=f"Unable to resolve commit: {exc}",
                findings=[Finding(code="commit_error", message=str(exc))],
                remediation_hint="Select an existing commit or ref.",
                evidence={"source": source, "commit": commit},
            )
    try:
        manifest_data = _read(config, client, source, config.handover.manifest, commit)
        records = parse_manifest(manifest_data)
    except (OSError, GitCommandError, InvalidConfigurationError, ManifestParseError) as exc:
        return CheckResult(
            check_name="handover",
            status=Status.ERROR,
            summary=f"Unable to read checksum manifest: {exc}",
            findings=[
                Finding(code="manifest_error", message=str(exc), path=config.handover.manifest)
            ],
            affected_paths=[config.handover.manifest],
            remediation_hint="Regenerate a valid checksum manifest for the selected source.",
            evidence={"source": source, "commit": commit},
        )
    for record in records:
        try:
            data = _read(config, client, source, record.path, commit)
        except (OSError, GitCommandError, InvalidConfigurationError) as exc:
            findings.append(
                Finding(code="manifest_file_missing", message=str(exc), path=record.path)
            )
            continue
        actual_digest = hashlib.sha256(data).hexdigest()
        verified.append(
            {
                "path": record.path,
                "expected_size": record.size,
                "actual_size": len(data),
                "expected_digest": record.digest,
                "actual_digest": actual_digest,
            }
        )
        if len(data) != record.size:
            findings.append(
                Finding(
                    code="size_mismatch",
                    message=f"Expected {record.size} bytes, got {len(data)}",
                    path=record.path,
                )
            )
        if not actual_digest.startswith(record.digest):
            findings.append(
                Finding(
                    code="checksum_mismatch",
                    message="SHA-256 digest does not match",
                    path=record.path,
                )
            )
    return CheckResult(
        check_name="handover",
        status=Status.FAIL if findings else Status.PASS,
        summary=f"Verified {len(verified)} manifest record(s) from {source}",
        findings=findings,
        evidence={"source": source, "commit": commit, "records": verified},
        affected_paths=sorted({finding.path for finding in findings if finding.path}),
        remediation_hint=(
            "Regenerate the manifest from the same Git source being verified." if findings else None
        ),
    )
