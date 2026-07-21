"""``workflowctl migrate plan``: deterministic backup/recovery planning from a fresh
inspection manifest (architecture-v3.md section 14: "content-addressed external backup
and recovery journal"). Planning only reads a `MigrationManifest` already held in memory
and performs no filesystem I/O of its own.
"""

from ai_workflow_engine.migration.models import (
    BackupPlan,
    BackupPlanEntry,
    MigrationManifest,
    RecoveryAction,
    RecoveryPlan,
    RecoveryStep,
    content_digest,
)


def _backup_relative_path(sha256: str) -> str:
    """Content-addressed, dedup-friendly layout: ``objects/<first-2-hex>/<sha256>``."""
    return f"objects/{sha256[:2]}/{sha256}"


def build_backup_plan(manifest: MigrationManifest) -> BackupPlan:
    """Plan one content-addressed backup object per *readable* manifest artifact (known
    or quarantined alike -- a backup preserves legacy evidence, it does not judge it).

    An artifact with ``entry_type`` ``"unreadable"`` or ``"unsupported"`` (a FIFO,
    socket, device node, or other non-regular/non-directory/non-symlink entry -- never
    opened or read at all, F-8) has no genuine bytes and is therefore never represented
    by a fabricated :class:`BackupPlanEntry`; its path is recorded in
    ``incomplete_paths`` instead, and ``complete`` is ``False`` whenever any such path
    exists (F-4).
    """
    entries: list[BackupPlanEntry] = []
    incomplete_paths: list[str] = []
    for artifact in manifest.artifacts:
        if artifact.entry_type in ("unreadable", "unsupported"):
            incomplete_paths.append(artifact.relative_path)
            continue
        entries.append(
            BackupPlanEntry(
                relative_path=artifact.relative_path,
                entry_type=artifact.entry_type,
                sha256=artifact.sha256,
                size_bytes=artifact.size_bytes,
                backup_relative_path=_backup_relative_path(artifact.sha256),
            )
        )
    entries.sort(key=lambda entry: entry.relative_path)
    incomplete_paths.sort()

    fields: dict[str, object] = {
        "schema_name": "migration-backup-plan",
        "schema_version": "1.0.0",
        "source_root": manifest.source_root,
        "to_version": manifest.to_version,
        "manifest_digest": manifest.manifest_digest,
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "incomplete_paths": incomplete_paths,
        "complete": len(incomplete_paths) == 0,
    }
    digest = content_digest(fields, exclude_key="plan_digest")
    return BackupPlan(
        schema_name="migration-backup-plan",
        schema_version="1.0.0",
        source_root=manifest.source_root,
        to_version=manifest.to_version,
        manifest_digest=manifest.manifest_digest,
        entries=entries,
        incomplete_paths=incomplete_paths,
        complete=len(incomplete_paths) == 0,
        plan_digest=digest,
    )


def _recovery_action_for(entry_type: str) -> RecoveryAction:
    return "restore_file" if entry_type == "file" else "refuse_unsupported_entry_type"


def build_recovery_plan(manifest: MigrationManifest, backup_plan: BackupPlan) -> RecoveryPlan:
    """Plan a verify-then-(restore|refuse) step pair per backed-up artifact, in path
    order. The second step is type-aware (F-4): a ``"file"`` entry gets ``restore_file``;
    any other backed-up entry type (currently only ``"symlink"``, since ``"unreadable"``
    entries are never backed up at all) gets ``refuse_unsupported_entry_type`` -- a
    symlink's backed-up bytes are its target *string*, never a regular file's content,
    and must never be restored as though they were.
    """
    steps: list[RecoveryStep] = []
    sequence = 1
    for entry in backup_plan.entries:
        steps.append(
            RecoveryStep(
                sequence=sequence,
                action="verify_backup_digest",
                relative_path=entry.relative_path,
                entry_type=entry.entry_type,
                sha256=entry.sha256,
            )
        )
        sequence += 1
        steps.append(
            RecoveryStep(
                sequence=sequence,
                action=_recovery_action_for(entry.entry_type),
                relative_path=entry.relative_path,
                entry_type=entry.entry_type,
                sha256=entry.sha256,
            )
        )
        sequence += 1

    fields: dict[str, object] = {
        "schema_name": "migration-recovery-plan",
        "schema_version": "1.0.0",
        "source_root": manifest.source_root,
        "to_version": manifest.to_version,
        "manifest_digest": manifest.manifest_digest,
        "backup_plan_digest": backup_plan.plan_digest,
        "steps": [step.model_dump(mode="json") for step in steps],
        "incomplete_paths": backup_plan.incomplete_paths,
        "complete": backup_plan.complete,
    }
    digest = content_digest(fields, exclude_key="plan_digest")
    return RecoveryPlan(
        schema_name="migration-recovery-plan",
        schema_version="1.0.0",
        source_root=manifest.source_root,
        to_version=manifest.to_version,
        manifest_digest=manifest.manifest_digest,
        backup_plan_digest=backup_plan.plan_digest,
        steps=steps,
        incomplete_paths=backup_plan.incomplete_paths,
        complete=backup_plan.complete,
        plan_digest=digest,
    )
