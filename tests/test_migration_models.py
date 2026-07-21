"""Unit tests for the ORCH-003 migration manifest/backup-plan/recovery-plan models:
classification-consistency invariants, entry-type-aware backup/recovery invariants,
digest-seal enforcement (F-5: every digest is recomputed and verified, not merely
format-checked, on every construction path including schema-registry dispatch), and
schema-registry round-tripping.
"""

import pytest
from pydantic import ValidationError

from ai_workflow_engine.migration.apply import apply_migration
from ai_workflow_engine.migration.errors import ApplyNotAuthorizedError
from ai_workflow_engine.migration.models import (
    ApplyResult,
    BackupPlan,
    BackupPlanEntry,
    LegacyArtifactRecord,
    MigrationManifest,
    RecoveryPlan,
    RecoveryStep,
    build_manifest,
    content_digest,
)
from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan
from ai_workflow_engine.schema.migration import MIGRATION_SCHEMA_REGISTRY

_HEX = "a" * 64


def _known(path: str, kind: str = "workflow-event") -> LegacyArtifactRecord:
    return LegacyArtifactRecord(
        relative_path=path,
        entry_type="file",
        classification="KNOWN",
        kind=kind,
        schema_name=kind,
        schema_version="1.0",
        sha256=_HEX,
        size_bytes=10,
        quarantine_reason=None,
        quarantine_detail="",
    )


def _quarantined(
    path: str, *, entry_type: str = "file", reason: str = "NOT_VALID_JSON"
) -> LegacyArtifactRecord:
    return LegacyArtifactRecord(
        relative_path=path,
        entry_type=entry_type,  # type: ignore[arg-type]
        classification="QUARANTINED",
        kind=None,
        schema_name=None,
        schema_version=None,
        sha256=_HEX,
        size_bytes=5,
        quarantine_reason=reason,  # type: ignore[arg-type]
        quarantine_detail="boom",
    )


# --- LegacyArtifactRecord classification-consistency invariant ----------------------------


def test_known_record_without_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="file",
            classification="KNOWN",
            kind=None,
            schema_name=None,
            schema_version=None,
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason=None,
            quarantine_detail="",
        )


def test_known_record_with_quarantine_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="file",
            classification="KNOWN",
            kind="workflow-event",
            schema_name="workflow-event",
            schema_version="1.0",
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason="NOT_VALID_JSON",
            quarantine_detail="",
        )


def test_known_record_requires_entry_type_file() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="symlink",
            classification="KNOWN",
            kind="workflow-event",
            schema_name="workflow-event",
            schema_version="1.0",
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason=None,
            quarantine_detail="",
        )


def test_quarantined_record_without_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="file",
            classification="QUARANTINED",
            kind=None,
            schema_name=None,
            schema_version=None,
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason=None,
            quarantine_detail="",
        )


def test_quarantined_record_with_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="file",
            classification="QUARANTINED",
            kind="workflow-event",
            schema_name=None,
            schema_version=None,
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason="NOT_VALID_JSON",
            quarantine_detail="",
        )


def test_symlink_not_allowed_requires_entry_type_symlink() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="file",
            classification="QUARANTINED",
            kind=None,
            schema_name=None,
            schema_version=None,
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason="SYMLINK_NOT_ALLOWED",
            quarantine_detail="x",
        )


def test_file_unreadable_requires_entry_type_unreadable() -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path="state/a.json",
            entry_type="file",
            classification="QUARANTINED",
            kind=None,
            schema_name=None,
            schema_version=None,
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason="FILE_UNREADABLE",
            quarantine_detail="x",
        )


@pytest.mark.parametrize(
    "bad_path", ["/abs/path.json", "a/../b.json", "a/./b.json", "", "a//b.json"]
)
def test_relative_path_rejects_traversal_and_unclean_forms(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        LegacyArtifactRecord(
            relative_path=bad_path,
            entry_type="file",
            classification="QUARANTINED",
            kind=None,
            schema_name=None,
            schema_version=None,
            sha256=_HEX,
            size_bytes=1,
            quarantine_reason="NOT_VALID_JSON",
            quarantine_detail="",
        )


def test_backup_plan_entry_rejects_traversal_path() -> None:
    with pytest.raises(ValidationError):
        BackupPlanEntry(
            relative_path="../escape.json",
            entry_type="file",
            sha256=_HEX,
            size_bytes=1,
            backup_relative_path="objects/aa/" + _HEX,
        )


def test_backup_plan_entry_rejects_unreadable_entry_type() -> None:
    with pytest.raises(ValidationError):
        BackupPlanEntry(
            relative_path="state/a.json",
            entry_type="unreadable",
            sha256=_HEX,
            size_bytes=1,
            backup_relative_path="objects/aa/" + _HEX,
        )


# --- MigrationManifest sorted/unique/count invariants --------------------------------------


def test_manifest_rejects_unsorted_artifacts() -> None:
    with pytest.raises(ValidationError):
        MigrationManifest(
            schema_name="migration-manifest",
            schema_version="1.0.0",
            source_root="/src",
            to_version="2.0.0",
            artifact_count=2,
            known_count=2,
            quarantined_count=0,
            artifacts=[_known("state/b.json"), _known("state/a.json")],
            manifest_digest=_HEX,
        )


def test_manifest_rejects_duplicate_paths() -> None:
    with pytest.raises(ValidationError):
        MigrationManifest(
            schema_name="migration-manifest",
            schema_version="1.0.0",
            source_root="/src",
            to_version="2.0.0",
            artifact_count=2,
            known_count=2,
            quarantined_count=0,
            artifacts=[_known("state/a.json"), _known("state/a.json")],
            manifest_digest=_HEX,
        )


def test_manifest_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValidationError):
        MigrationManifest(
            schema_name="migration-manifest",
            schema_version="1.0.0",
            source_root="/src",
            to_version="2.0.0",
            artifact_count=1,
            known_count=0,  # wrong: the one artifact is KNOWN
            quarantined_count=1,
            artifacts=[_known("state/a.json")],
            manifest_digest=_HEX,
        )


def test_build_manifest_sorts_and_seals_digest() -> None:
    manifest = build_manifest(
        source_root="/src",
        to_version="2.0.0",
        artifacts=[_known("state/b.json"), _quarantined("state/a.json")],
    )
    assert [a.relative_path for a in manifest.artifacts] == ["state/a.json", "state/b.json"]
    assert manifest.known_count == 1
    assert manifest.quarantined_count == 1
    recomputed = content_digest(manifest.model_dump(mode="json"), exclude_key="manifest_digest")
    assert manifest.manifest_digest == recomputed


def test_build_manifest_is_deterministic_across_calls() -> None:
    artifacts = [_known("state/b.json"), _quarantined("state/a.json")]
    first = build_manifest(source_root="/src", to_version="2.0.0", artifacts=list(artifacts))
    second = build_manifest(source_root="/src", to_version="2.0.0", artifacts=list(artifacts))
    assert first.manifest_digest == second.manifest_digest
    assert first == second


# --- F-5: digest seals are recomputed and verified, not merely format-checked --------------


def test_manifest_rejects_tampered_manifest_digest() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    payload = manifest.model_dump(mode="json")
    payload["manifest_digest"] = "f" * 64  # well-formed hex64, but wrong content
    with pytest.raises(ValidationError, match="manifest_digest does not match"):
        MigrationManifest.model_validate(payload)


def test_manifest_rejects_tampered_artifact_field() -> None:
    """Tampering with a nested artifact's sha256 after sealing must be caught, not just a
    change to the top-level digest field itself."""
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    payload = manifest.model_dump(mode="json")
    payload["artifacts"][0]["sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="manifest_digest does not match"):
        MigrationManifest.model_validate(payload)


def test_manifest_rejects_injected_artifact() -> None:
    manifest = build_manifest(
        source_root="/src",
        to_version="2.0.0",
        artifacts=[_known("state/a.json"), _known("state/b.json")],
    )
    payload = manifest.model_dump(mode="json")
    payload["artifacts"].append(_known("state/c.json").model_dump(mode="json"))
    payload["artifact_count"] = 3
    payload["known_count"] = 3
    with pytest.raises(ValidationError, match="manifest_digest does not match"):
        MigrationManifest.model_validate(payload)


def test_backup_plan_rejects_tampered_plan_digest() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    payload = backup_plan.model_dump(mode="json")
    payload["plan_digest"] = "f" * 64
    with pytest.raises(ValidationError, match="plan_digest does not match"):
        BackupPlan.model_validate(payload)


def test_backup_plan_rejects_tampered_entry() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    payload = backup_plan.model_dump(mode="json")
    payload["entries"][0]["sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="plan_digest does not match"):
        BackupPlan.model_validate(payload)


def test_recovery_plan_rejects_tampered_step() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    payload = recovery_plan.model_dump(mode="json")
    payload["steps"][0]["sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="plan_digest does not match"):
        RecoveryPlan.model_validate(payload)


def test_models_are_frozen() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    with pytest.raises(ValidationError):
        manifest.manifest_digest = "f" * 64  # type: ignore[misc]


# --- RecoveryPlan contiguous-sequence invariant ---------------------------------------------


def test_recovery_plan_rejects_non_contiguous_sequence() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    payload = recovery_plan.model_dump(mode="json")
    payload["steps"] = [{**step, "sequence": step["sequence"] + 1} for step in payload["steps"]]
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(payload)


def test_recovery_step_action_must_match_entry_type() -> None:
    with pytest.raises(ValidationError):
        RecoveryStep(
            sequence=1,
            action="restore_file",
            relative_path="state/a.json",
            entry_type="symlink",
            sha256=_HEX,
        )
    with pytest.raises(ValidationError):
        RecoveryStep(
            sequence=1,
            action="refuse_unsupported_entry_type",
            relative_path="state/a.json",
            entry_type="file",
            sha256=_HEX,
        )


# --- entry_type-aware backup/recovery completeness (F-4) -----------------------------------


def test_backup_plan_completeness_flags_and_overlap_guard() -> None:
    with pytest.raises(ValidationError):
        BackupPlan(
            schema_name="migration-backup-plan",
            schema_version="1.0.0",
            source_root="/src",
            to_version="2.0.0",
            manifest_digest=_HEX,
            entries=[],
            incomplete_paths=["state/a.json"],
            complete=True,  # wrong: incomplete_paths is non-empty
            plan_digest=_HEX,
        )


def test_backup_plan_rejects_path_both_backed_up_and_incomplete() -> None:
    entry = BackupPlanEntry(
        relative_path="state/a.json",
        entry_type="file",
        sha256=_HEX,
        size_bytes=1,
        backup_relative_path="objects/aa/" + _HEX,
    )
    with pytest.raises(ValidationError, match="both backed up and incomplete"):
        BackupPlan(
            schema_name="migration-backup-plan",
            schema_version="1.0.0",
            source_root="/src",
            to_version="2.0.0",
            manifest_digest=_HEX,
            entries=[entry],
            incomplete_paths=["state/a.json"],
            complete=False,
            plan_digest=_HEX,
        )


# --- ApplyResult structurally pins dry_run=True ---------------------------------------------


def test_apply_result_cannot_be_constructed_with_dry_run_false() -> None:
    with pytest.raises(ValidationError):
        ApplyResult(
            schema_name="migration-apply-result",
            schema_version="1.0.0",
            dry_run=False,  # type: ignore[arg-type]
            source_root="/src",
            to_version="2.0.0",
            manifest_digest=_HEX,
            backup_plan_digest=_HEX,
            recovery_plan_digest=_HEX,
            backup_complete=True,
            planned_backup_object_count=0,
            planned_recovery_step_count=0,
            status="DRY_RUN_OK",
        )


def test_apply_migration_cross_checks_mismatched_plan_triples() -> None:
    manifest_a = build_manifest(
        source_root="/a", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    manifest_b = build_manifest(
        source_root="/b", to_version="2.0.0", artifacts=[_known("state/z.json")]
    )
    backup_a = build_backup_plan(manifest_a)
    recovery_a = build_recovery_plan(manifest_a, backup_a)

    with pytest.raises(ApplyNotAuthorizedError):
        apply_migration(manifest_b, backup_a, recovery_a, dry_run=True)


def test_apply_migration_refuses_without_dry_run_before_touching_arguments() -> None:
    """F-7: the very first thing `apply_migration` does is check `dry_run`; nothing else
    -- not even the manifest -- is inspected first. A garbage/incompatible manifest still
    only produces the refusal, never a different, argument-dependent error.
    """
    manifest = build_manifest(
        source_root="/a", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    with pytest.raises(ApplyNotAuthorizedError, match="not authorized"):
        apply_migration(manifest, backup_plan, recovery_plan, dry_run=False)


def test_apply_migration_detects_tampered_manifest_via_full_reverification() -> None:
    """F-5: apply must independently re-verify the sealed records, not merely compare
    caller-supplied digest strings -- a manifest built via `model_construct` (bypassing
    validation) still gets caught because `apply_migration` forces a full
    `model_validate` round trip.
    """
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)

    tampered_fields = manifest.model_dump(mode="json")
    tampered_fields["known_count"] = 999  # inconsistent, but model_construct skips validation
    tampered_fields["artifacts"] = [
        LegacyArtifactRecord.model_validate(artifact) for artifact in tampered_fields["artifacts"]
    ]
    tampered_manifest = MigrationManifest.model_construct(**tampered_fields)
    # The tampered object's own digest still matches its *stated* manifest_digest field
    # (unchanged), so a naive string comparison against backup_plan.manifest_digest would
    # still "pass" -- only a full re-validation catches the inconsistency.
    with pytest.raises(ApplyNotAuthorizedError, match="re-verification"):
        apply_migration(tampered_manifest, backup_plan, recovery_plan, dry_run=True)


# --- Schema-registry round trip: proves the guard applies through model_validate, not ------
# --- just direct Python construction (same rationale as test_schema_registry.py's Finding C) -


def test_migration_schemas_are_registered_at_1_0_0() -> None:
    assert MIGRATION_SCHEMA_REGISTRY.versions("migration-manifest") == ("1.0.0",)
    assert MIGRATION_SCHEMA_REGISTRY.versions("migration-backup-plan") == ("1.0.0",)
    assert MIGRATION_SCHEMA_REGISTRY.versions("migration-recovery-plan") == ("1.0.0",)


def test_manifest_round_trips_through_registry_dispatch() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    dispatched = MIGRATION_SCHEMA_REGISTRY.dispatch(
        "migration-manifest", "1.0.0", manifest.model_dump(mode="json")
    )
    assert dispatched == manifest


def test_registry_dispatch_rejects_tampered_manifest() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    payload = manifest.model_dump(mode="json")
    payload["source_root"] = "/tampered"
    from pydantic import ValidationError as PydanticValidationError

    from ai_workflow_engine.exceptions import SchemaDispatchError

    with pytest.raises((PydanticValidationError, SchemaDispatchError)):
        MIGRATION_SCHEMA_REGISTRY.dispatch("migration-manifest", "1.0.0", payload)


def test_backup_and_recovery_plan_round_trip_through_registry_dispatch() -> None:
    manifest = build_manifest(
        source_root="/src", to_version="2.0.0", artifacts=[_known("state/a.json")]
    )
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)

    dispatched_backup = MIGRATION_SCHEMA_REGISTRY.dispatch(
        "migration-backup-plan", "1.0.0", backup_plan.model_dump(mode="json")
    )
    assert dispatched_backup == backup_plan

    dispatched_recovery = MIGRATION_SCHEMA_REGISTRY.dispatch(
        "migration-recovery-plan", "1.0.0", recovery_plan.model_dump(mode="json")
    )
    assert dispatched_recovery == recovery_plan


def test_registry_rejects_unknown_migration_schema_version() -> None:
    from ai_workflow_engine.exceptions import UnsupportedSchemaVersionError

    with pytest.raises(UnsupportedSchemaVersionError):
        MIGRATION_SCHEMA_REGISTRY.get("migration-manifest", "9.9.9")


def test_registry_rejects_unknown_migration_schema_name() -> None:
    from ai_workflow_engine.exceptions import UnknownSchemaNameError

    with pytest.raises(UnknownSchemaNameError):
        MIGRATION_SCHEMA_REGISTRY.get("migration-unicorn", "1.0.0")
