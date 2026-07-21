"""``workflowctl migrate apply``: real apply is not authorized in ORCH-003
(implementation-plan.md section 6: "ORCH-003 builds only safe inspection/planning/backup
machinery ... No production governance document is migrated in an earlier stage").

`apply_migration` performs no filesystem write under any argument combination: the
``dry_run`` path is pure computation over already-validated models, and the non-dry-run
path raises before doing anything else at all -- including before re-verifying its
arguments, so a real-apply refusal never depends on (and is never delayed by) the
integrity of what was passed in.

Before trusting ``manifest``/``backup_plan``/``recovery_plan``, each is independently
re-verified via a full ``model_validate`` round trip (not merely a caller-supplied
digest-string comparison): this forces every one of that model's validators -- including
the digest-seal check in ``migration.models`` -- to run again against the object's
*current* field values, so any tampering that occurred after the object was first
constructed (a hand-edited field, a swapped-in ``model_construct``-built object, or a
value that bypassed the seal some other way) is caught here, not merely trusted because
an earlier construction happened to validate.
"""

from ai_workflow_engine.migration.errors import ApplyNotAuthorizedError
from ai_workflow_engine.migration.models import (
    ApplyResult,
    BackupPlan,
    MigrationManifest,
    RecoveryPlan,
)


def apply_migration(
    manifest: MigrationManifest,
    backup_plan: BackupPlan,
    recovery_plan: RecoveryPlan,
    *,
    dry_run: bool,
) -> ApplyResult:
    """Refuse before any write, and before touching any argument at all, unless
    ``dry_run`` is True. Even the dry-run path performs zero filesystem I/O of its own.
    """
    if not dry_run:
        raise ApplyNotAuthorizedError(
            "Real (non-dry-run) migration apply is not authorized in ORCH-003; pass --dry-run. "
            "Live application is deferred to a dedicated migration session "
            "(implementation-plan.md section 6, stage ORCH-026)."
        )

    try:
        verified_manifest = MigrationManifest.model_validate(manifest.model_dump(mode="json"))
        verified_backup = BackupPlan.model_validate(backup_plan.model_dump(mode="json"))
        verified_recovery = RecoveryPlan.model_validate(recovery_plan.model_dump(mode="json"))
    except Exception as exc:  # pydantic.ValidationError, or any digest-seal ValueError it wraps
        raise ApplyNotAuthorizedError(
            f"manifest/backup_plan/recovery_plan failed independent re-verification: {exc}"
        ) from exc

    if verified_backup.manifest_digest != verified_manifest.manifest_digest:
        raise ApplyNotAuthorizedError("backup_plan does not match the given manifest")
    if verified_recovery.manifest_digest != verified_manifest.manifest_digest:
        raise ApplyNotAuthorizedError("recovery_plan does not match the given manifest")
    if verified_recovery.backup_plan_digest != verified_backup.plan_digest:
        raise ApplyNotAuthorizedError("recovery_plan does not match the given backup_plan")

    return ApplyResult(
        schema_name="migration-apply-result",
        schema_version="1.0.0",
        dry_run=True,
        source_root=verified_manifest.source_root,
        to_version=verified_manifest.to_version,
        manifest_digest=verified_manifest.manifest_digest,
        backup_plan_digest=verified_backup.plan_digest,
        recovery_plan_digest=verified_recovery.plan_digest,
        backup_complete=verified_backup.complete,
        planned_backup_object_count=len(verified_backup.entries),
        planned_recovery_step_count=len(verified_recovery.steps),
        status="DRY_RUN_OK",
    )
