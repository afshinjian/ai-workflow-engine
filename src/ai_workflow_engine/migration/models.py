"""Migration manifest, backup-plan, and recovery-plan models, version ``1.0.0``
(architecture-v3.md section 14: "Add migration manifest ... backup ... recovery journal").

Every model here is produced by reading existing legacy artifacts; none is ever written
back to a source tree. `manifest_digest`/`plan_digest` are content identities — SHA-256 of
the RFC-8785-flavoured canonical JSON of the record with the digest field itself excluded
(the same self-referential-hash technique as `agents/artifacts.py`'s `run_id`) — so they
depend only on the classified content, never on wall-clock time or the generating machine.
No model in this module carries a timestamp field.

Every digest-bearing model (`MigrationManifest`, `BackupPlan`, `RecoveryPlan`) carries a
``model_validator(mode="after")`` that *recomputes* its own digest from its own current
field values and rejects construction if it disagrees — on every construction path,
including ``model_validate`` (schema-registry dispatch, a stored/transmitted payload).
Tampering with any identity-bearing field after the fact (a hand-edited SHA-256, an
injected artifact, a reordered step) is therefore rejected the moment the tampered data
is validated, not merely flagged by a caller who happens to compare digest strings. Every
model here is additionally ``frozen=True``: there is no supported way to mutate a
validated instance in place and have the mutation silently escape re-validation.
"""

import hashlib
import re
from typing import Literal

from pydantic import ConfigDict, field_validator, model_validator

from ai_workflow_engine.models import StrictModel
from ai_workflow_engine.prompt.renderer import canonical_json

LegacyArtifactKind = Literal[
    "workflow-event",
    "agent-run-record",
    "agent-run-patch",
    "prompt-metadata",
    "prompt-markdown",
    "commit-approval",
    "push-approval",
]

ArtifactClassification = Literal["KNOWN", "QUARANTINED"]

# The physical filesystem nature of an entry, independent of whether it validated. A
# symlink's "content" (its target string) is never a restorable file's bytes (F-4); an
# unreadable entry has no bytes at all, so it can never be included in a backup; an
# "unsupported" entry (FIFO, socket, device node, ...) is never opened/read at all (F-8)
# and likewise has no genuine bytes.
EntryType = Literal["file", "symlink", "unreadable", "unsupported"]

QuarantineReason = Literal[
    "UNKNOWN_TOP_LEVEL_DIRECTORY",
    "UNKNOWN_FILE_EXTENSION",
    "UNEXPECTED_PATH_STRUCTURE",
    "ORPHAN_COMPANION_FILE",
    "SYMLINK_NOT_ALLOWED",
    "COMPANION_SYMLINK_NOT_ALLOWED",
    "UNSUPPORTED_ENTRY_TYPE",
    "NOT_VALID_UTF8",
    "NOT_VALID_JSON",
    "NOT_VALID_YAML",
    "DUPLICATE_JSON_KEY",
    "DUPLICATE_YAML_KEY",
    "SCHEMA_VALIDATION_FAILED",
    "UNSUPPORTED_SCHEMA_VERSION",
    "UNKNOWN_APPROVAL_KIND",
    "MISSING_COMPANION_MEMBER",
    "COMPANION_DIGEST_MISMATCH",
    "PRIMARY_INVALID",
    "ADDRESS_MISMATCH",
    "CANONICAL_FORM_MISMATCH",
    "CONTENT_HASH_MISMATCH",
    "WORKFLOW_HISTORY_INTEGRITY_FAILED",
    "SOURCE_MUTATED_DURING_SCAN",
    "FILE_UNREADABLE",
]

RecoveryAction = Literal["verify_backup_digest", "restore_file", "refuse_unsupported_entry_type"]

_HEX64_RE = re.compile(r"[0-9a-f]{64}")

_SEALED_CONFIG = ConfigDict(extra="forbid", frozen=True)


def _validate_relative_posix_path(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("relative_path must be non-empty and untrimmed-clean")
    if value.startswith("/") or value.startswith("./") or value.startswith("../"):
        raise ValueError(f"relative_path must be a clean relative POSIX path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"relative_path must not contain '.', '..', or empty segments: {value!r}")
    return value


def _validate_hex64(value: str) -> str:
    if not _HEX64_RE.fullmatch(value):
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def content_digest(payload: dict[str, object], *, exclude_key: str) -> str:
    """SHA-256 of the canonical JSON of ``payload`` with ``exclude_key`` removed.

    Used identically by a builder (whose ``payload`` never contains ``exclude_key`` at
    all -- the filter is then a no-op) and by a model's own recompute-and-verify
    validator (whose ``payload`` is ``self.model_dump(mode="json")`` and does contain the
    field being verified), so both sides compute the exact same digest for the exact same
    logical content.
    """
    trimmed = {key: value for key, value in payload.items() if key != exclude_key}
    return hashlib.sha256(canonical_json(trimmed)).hexdigest()


class LegacyArtifactRecord(StrictModel):
    """One classified filesystem entry under a legacy-artifact source root."""

    model_config = _SEALED_CONFIG

    relative_path: str
    entry_type: EntryType
    classification: ArtifactClassification
    kind: LegacyArtifactKind | None
    schema_name: str | None
    schema_version: str | None
    sha256: str
    size_bytes: int
    quarantine_reason: QuarantineReason | None
    quarantine_detail: str

    @field_validator("relative_path")
    @classmethod
    def _relative_path_valid(cls, value: str) -> str:
        return _validate_relative_posix_path(value)

    @field_validator("sha256")
    @classmethod
    def _sha256_valid(cls, value: str) -> str:
        return _validate_hex64(value)

    @field_validator("size_bytes")
    @classmethod
    def _size_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("size_bytes must be non-negative")
        return value

    @model_validator(mode="after")
    def _classification_consistent(self) -> "LegacyArtifactRecord":
        if self.classification == "KNOWN":
            if self.kind is None or self.schema_name is None or self.schema_version is None:
                raise ValueError("a KNOWN artifact requires kind, schema_name, and schema_version")
            if self.quarantine_reason is not None or self.quarantine_detail != "":
                raise ValueError("a KNOWN artifact must not carry quarantine fields")
            if self.entry_type != "file":
                raise ValueError("a KNOWN artifact must have entry_type 'file'")
        else:
            if self.quarantine_reason is None:
                raise ValueError("a QUARANTINED artifact requires quarantine_reason")
            if (
                self.kind is not None
                or self.schema_name is not None
                or self.schema_version is not None
            ):
                raise ValueError("a QUARANTINED artifact must not carry kind/schema fields")
            if self.quarantine_reason == "SYMLINK_NOT_ALLOWED" and self.entry_type != "symlink":
                raise ValueError("SYMLINK_NOT_ALLOWED requires entry_type 'symlink'")
            if self.quarantine_reason == "FILE_UNREADABLE" and self.entry_type != "unreadable":
                raise ValueError("FILE_UNREADABLE requires entry_type 'unreadable'")
            if (
                self.quarantine_reason == "UNSUPPORTED_ENTRY_TYPE"
                and self.entry_type != "unsupported"
            ):
                raise ValueError("UNSUPPORTED_ENTRY_TYPE requires entry_type 'unsupported'")
        return self


class MigrationManifest(StrictModel):
    """The deterministic result of ``workflowctl migrate inspect``."""

    model_config = _SEALED_CONFIG

    schema_name: Literal["migration-manifest"]
    schema_version: Literal["1.0.0"]
    source_root: str
    to_version: str
    artifact_count: int
    known_count: int
    quarantined_count: int
    artifacts: list[LegacyArtifactRecord]
    manifest_digest: str

    @field_validator("manifest_digest")
    @classmethod
    def _digest_valid(cls, value: str) -> str:
        return _validate_hex64(value)

    @field_validator("artifacts")
    @classmethod
    def _artifacts_sorted_unique(
        cls, value: list[LegacyArtifactRecord]
    ) -> list[LegacyArtifactRecord]:
        paths = [artifact.relative_path for artifact in value]
        if len(set(paths)) != len(paths):
            raise ValueError("manifest artifacts must have unique relative_path values")
        if paths != sorted(paths):
            raise ValueError("manifest artifacts must be sorted by relative_path")
        return value

    @model_validator(mode="after")
    def _counts_consistent(self) -> "MigrationManifest":
        if self.artifact_count != len(self.artifacts):
            raise ValueError("artifact_count must equal len(artifacts)")
        known = sum(1 for artifact in self.artifacts if artifact.classification == "KNOWN")
        if known != self.known_count or (self.artifact_count - known) != self.quarantined_count:
            raise ValueError("known_count/quarantined_count do not match artifacts")
        return self

    @model_validator(mode="after")
    def _digest_seal(self) -> "MigrationManifest":
        payload = self.model_dump(mode="json")
        recomputed = content_digest(payload, exclude_key="manifest_digest")
        if recomputed != self.manifest_digest:
            raise ValueError(
                "manifest_digest does not match the recomputed content digest "
                f"(stored {self.manifest_digest}, recomputed {recomputed}): the manifest "
                "was tampered with, or was not sealed by build_manifest()"
            )
        return self


def build_manifest(
    *, source_root: str, to_version: str, artifacts: list[LegacyArtifactRecord]
) -> MigrationManifest:
    """Assemble a closed, self-consistent, digest-sealed :class:`MigrationManifest`.

    The digest is computed from a plain dict of already-JSON-safe field values -- never
    from an intermediate model constructed with a placeholder digest -- and the final
    model is constructed exactly once, with its real digest already in place, so the new
    ``_digest_seal`` validator runs against genuine sealed content on every build, not a
    value that briefly held a fake placeholder.
    """
    ordered = sorted(artifacts, key=lambda artifact: artifact.relative_path)
    known = sum(1 for artifact in ordered if artifact.classification == "KNOWN")
    fields: dict[str, object] = {
        "schema_name": "migration-manifest",
        "schema_version": "1.0.0",
        "source_root": source_root,
        "to_version": to_version,
        "artifact_count": len(ordered),
        "known_count": known,
        "quarantined_count": len(ordered) - known,
        "artifacts": [artifact.model_dump(mode="json") for artifact in ordered],
    }
    digest = content_digest(fields, exclude_key="manifest_digest")
    return MigrationManifest(
        schema_name="migration-manifest",
        schema_version="1.0.0",
        source_root=source_root,
        to_version=to_version,
        artifact_count=len(ordered),
        known_count=known,
        quarantined_count=len(ordered) - known,
        artifacts=ordered,
        manifest_digest=digest,
    )


class BackupPlanEntry(StrictModel):
    """One planned, content-addressed backup object. Planning only; nothing is copied.

    ``entry_type`` is carried through from the source :class:`LegacyArtifactRecord` so a
    consumer never mistakes a symlink's target-string digest for a regular file's bytes.
    """

    model_config = _SEALED_CONFIG

    relative_path: str
    entry_type: EntryType
    sha256: str
    size_bytes: int
    backup_relative_path: str

    @field_validator("relative_path", "backup_relative_path")
    @classmethod
    def _paths_valid(cls, value: str) -> str:
        return _validate_relative_posix_path(value)

    @field_validator("sha256")
    @classmethod
    def _sha256_valid(cls, value: str) -> str:
        return _validate_hex64(value)

    @field_validator("size_bytes")
    @classmethod
    def _size_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("size_bytes must be non-negative")
        return value

    @model_validator(mode="after")
    def _entry_type_readable(self) -> "BackupPlanEntry":
        if self.entry_type in ("unreadable", "unsupported"):
            raise ValueError(
                f"an {self.entry_type!r} entry has no genuine bytes and must never appear "
                "in a backup plan's entries (see BackupPlan.incomplete_paths instead)"
            )
        return self


class BackupPlan(StrictModel):
    """The deterministic backup plan produced by ``workflowctl migrate plan``.

    ``complete`` is ``False`` whenever any discovered legacy artifact could not be
    genuinely captured (``entry_type`` ``"unreadable"`` or ``"unsupported"``); such
    paths are listed in ``incomplete_paths`` and are never represented by a fabricated
    ``BackupPlanEntry``.
    """

    model_config = _SEALED_CONFIG

    schema_name: Literal["migration-backup-plan"]
    schema_version: Literal["1.0.0"]
    source_root: str
    to_version: str
    manifest_digest: str
    entries: list[BackupPlanEntry]
    incomplete_paths: list[str]
    complete: bool
    plan_digest: str

    @field_validator("manifest_digest", "plan_digest")
    @classmethod
    def _digests_valid(cls, value: str) -> str:
        return _validate_hex64(value)

    @field_validator("entries")
    @classmethod
    def _entries_sorted_unique(cls, value: list[BackupPlanEntry]) -> list[BackupPlanEntry]:
        paths = [entry.relative_path for entry in value]
        if len(set(paths)) != len(paths):
            raise ValueError("backup plan entries must have unique relative_path values")
        if paths != sorted(paths):
            raise ValueError("backup plan entries must be sorted by relative_path")
        return value

    @field_validator("incomplete_paths")
    @classmethod
    def _incomplete_paths_sorted_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("incomplete_paths must not contain duplicates")
        if value != sorted(value):
            raise ValueError("incomplete_paths must be sorted")
        return value

    @model_validator(mode="after")
    def _completeness_consistent(self) -> "BackupPlan":
        if self.complete != (len(self.incomplete_paths) == 0):
            raise ValueError("complete must equal (len(incomplete_paths) == 0)")
        overlap = {e.relative_path for e in self.entries} & set(self.incomplete_paths)
        if overlap:
            raise ValueError(f"paths cannot be both backed up and incomplete: {sorted(overlap)}")
        return self

    @model_validator(mode="after")
    def _digest_seal(self) -> "BackupPlan":
        payload = self.model_dump(mode="json")
        recomputed = content_digest(payload, exclude_key="plan_digest")
        if recomputed != self.plan_digest:
            raise ValueError(
                "plan_digest does not match the recomputed content digest "
                f"(stored {self.plan_digest}, recomputed {recomputed}): the backup plan "
                "was tampered with, or was not sealed by build_backup_plan()"
            )
        return self


class RecoveryStep(StrictModel):
    """One deterministic, descriptive recovery-plan step. Never executed by this stage.

    ``action`` is type-aware: only a ``"file"`` entry ever gets ``restore_file``; a
    ``"symlink"`` entry (whose backed-up bytes are its target *string*, never a regular
    file's content) gets ``refuse_unsupported_entry_type`` instead, so a recovery plan
    can never be misread as "restore this symlink's target string as a regular file".
    """

    model_config = _SEALED_CONFIG

    sequence: int
    action: RecoveryAction
    relative_path: str
    entry_type: EntryType
    sha256: str

    @field_validator("sequence")
    @classmethod
    def _sequence_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sequence must be a 1-based positive integer")
        return value

    @field_validator("relative_path")
    @classmethod
    def _relative_path_valid(cls, value: str) -> str:
        return _validate_relative_posix_path(value)

    @field_validator("sha256")
    @classmethod
    def _sha256_valid(cls, value: str) -> str:
        return _validate_hex64(value)

    @model_validator(mode="after")
    def _action_matches_entry_type(self) -> "RecoveryStep":
        if self.action == "restore_file" and self.entry_type != "file":
            raise ValueError("restore_file is only valid for entry_type 'file'")
        if self.action == "refuse_unsupported_entry_type" and self.entry_type == "file":
            raise ValueError("refuse_unsupported_entry_type must not be used for entry_type 'file'")
        return self


class RecoveryPlan(StrictModel):
    """The deterministic recovery plan produced by ``workflowctl migrate plan``."""

    model_config = _SEALED_CONFIG

    schema_name: Literal["migration-recovery-plan"]
    schema_version: Literal["1.0.0"]
    source_root: str
    to_version: str
    manifest_digest: str
    backup_plan_digest: str
    steps: list[RecoveryStep]
    incomplete_paths: list[str]
    complete: bool
    plan_digest: str

    @field_validator("manifest_digest", "backup_plan_digest", "plan_digest")
    @classmethod
    def _digests_valid(cls, value: str) -> str:
        return _validate_hex64(value)

    @field_validator("incomplete_paths")
    @classmethod
    def _incomplete_paths_sorted_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("incomplete_paths must not contain duplicates")
        if value != sorted(value):
            raise ValueError("incomplete_paths must be sorted")
        return value

    @model_validator(mode="after")
    def _completeness_consistent(self) -> "RecoveryPlan":
        if self.complete != (len(self.incomplete_paths) == 0):
            raise ValueError("complete must equal (len(incomplete_paths) == 0)")
        return self

    @model_validator(mode="after")
    def _steps_contiguous(self) -> "RecoveryPlan":
        expected = list(range(1, len(self.steps) + 1))
        if [step.sequence for step in self.steps] != expected:
            raise ValueError("recovery plan steps must have contiguous 1-based sequence numbers")
        return self

    @model_validator(mode="after")
    def _digest_seal(self) -> "RecoveryPlan":
        payload = self.model_dump(mode="json")
        recomputed = content_digest(payload, exclude_key="plan_digest")
        if recomputed != self.plan_digest:
            raise ValueError(
                "plan_digest does not match the recomputed content digest "
                f"(stored {self.plan_digest}, recomputed {recomputed}): the recovery plan "
                "was tampered with, or was not sealed by build_recovery_plan()"
            )
        return self


class ApplyResult(StrictModel):
    """The result of ``workflowctl migrate apply``. ``dry_run`` is pinned to ``True``:

    there is no way to construct this model with ``dry_run=False`` -- a real apply is
    refused by `migration.apply.apply_migration` before any such value could be built,
    so this is a structural guarantee, not merely a tested one.
    """

    model_config = _SEALED_CONFIG

    schema_name: Literal["migration-apply-result"]
    schema_version: Literal["1.0.0"]
    dry_run: Literal[True]
    source_root: str
    to_version: str
    manifest_digest: str
    backup_plan_digest: str
    recovery_plan_digest: str
    backup_complete: bool
    planned_backup_object_count: int
    planned_recovery_step_count: int
    status: Literal["DRY_RUN_OK"]

    @field_validator("manifest_digest", "backup_plan_digest", "recovery_plan_digest")
    @classmethod
    def _digests_valid(cls, value: str) -> str:
        return _validate_hex64(value)
