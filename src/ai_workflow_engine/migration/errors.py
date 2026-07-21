"""Typed, fail-closed migration errors (mirrors ArtifactError/PromptStorageError/ApprovalError:
a local `ValueError` subclass per package, not `WorkflowEngineError` — see
`agents/artifacts.py`, `prompt/store.py`, `git/approval.py`).
"""


class MigrationError(ValueError):
    """Base error for the migration framework."""

    code = "migration_error"


class MigrationSourceError(MigrationError):
    """The legacy-artifact source root is missing, not a directory, or unreadable."""

    code = "migration_source_error"


class UnsupportedMigrationTargetError(MigrationError):
    """`--to VERSION` names a target this stage does not support."""

    code = "unsupported_migration_target"


class ApplyNotAuthorizedError(MigrationError):
    """Real (non-dry-run) apply, or an internally inconsistent plan triple, was refused."""

    code = "apply_not_authorized"
