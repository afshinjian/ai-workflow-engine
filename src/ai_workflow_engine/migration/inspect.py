"""``workflowctl migrate inspect``: deterministic, read-only legacy-artifact classification
(architecture-v3.md section 14: ``workflowctl migrate inspect|plan|apply --to VERSION``).
"""

from pathlib import Path

from ai_workflow_engine.migration.errors import UnsupportedMigrationTargetError
from ai_workflow_engine.migration.legacy_readers import discover_legacy_artifacts
from ai_workflow_engine.migration.models import MigrationManifest, build_manifest

# The only migration target this stage recognizes (architecture-v3.md section 14's target
# schema versions for the legacy families this reader covers: WorkflowEvent/AgentRunRecord
# -> 2.0.0, PromptContext/PromptMetadata -> 2.0.0, ApprovalEnvelope -> 2.0.0). Any other
# value fails closed rather than silently accepting an unplanned target.
SUPPORTED_MIGRATION_TARGETS: tuple[str, ...] = ("2.0.0",)


def resolve_migration_target(value: str) -> str:
    if value not in SUPPORTED_MIGRATION_TARGETS:
        raise UnsupportedMigrationTargetError(
            f"Unsupported migration target {value!r}; supported: "
            f"{', '.join(SUPPORTED_MIGRATION_TARGETS)}"
        )
    return value


def default_migration_source() -> Path:
    """The real, on-disk union of this engine's existing legacy artifact stores."""
    return Path("~/.ai-workflow-engine/workflow-runs").expanduser()


def inspect_source(source_root: Path, *, to_version: str) -> MigrationManifest:
    """Read-only: classify every legacy artifact under ``source_root``. Writes nothing."""
    resolved_target = resolve_migration_target(to_version)
    artifacts = discover_legacy_artifacts(source_root)
    return build_manifest(
        source_root=str(source_root), to_version=resolved_target, artifacts=artifacts
    )
