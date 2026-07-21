"""Schema-registry adapters for the ORCH-003 migration models (architecture-v3.md section
14: "Add migration manifest, backup-plan, and recovery-plan schema models version 1.0.0").

Registering these closed-dispatch models alongside `schema.contract`'s ``cli-contract``
proves the guard applies uniformly through `SchemaRegistry.dispatch` (external/schema
input, e.g. `model_validate` from a stored or transmitted payload), not just through
direct Python construction -- the same rationale as `cli-contract`'s registration.
"""

from ai_workflow_engine.migration.models import BackupPlan, MigrationManifest, RecoveryPlan
from ai_workflow_engine.schema.registry import SchemaRegistry

MIGRATION_MANIFEST_SCHEMA_NAME = "migration-manifest"
MIGRATION_BACKUP_PLAN_SCHEMA_NAME = "migration-backup-plan"
MIGRATION_RECOVERY_PLAN_SCHEMA_NAME = "migration-recovery-plan"

MIGRATION_SCHEMA_REGISTRY = SchemaRegistry()
MIGRATION_SCHEMA_REGISTRY.register(MIGRATION_MANIFEST_SCHEMA_NAME, "1.0.0", MigrationManifest)
MIGRATION_SCHEMA_REGISTRY.register(MIGRATION_BACKUP_PLAN_SCHEMA_NAME, "1.0.0", BackupPlan)
MIGRATION_SCHEMA_REGISTRY.register(MIGRATION_RECOVERY_PLAN_SCHEMA_NAME, "1.0.0", RecoveryPlan)
