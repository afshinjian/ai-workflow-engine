"""Typed errors which are safe to show without a traceback."""


class WorkflowEngineError(Exception):
    """Base expected application error."""


class InvalidConfigurationError(WorkflowEngineError):
    pass


class RepositoryNotFoundError(InvalidConfigurationError):
    pass


class NotGitRepositoryError(InvalidConfigurationError):
    pass


class GitCommandError(WorkflowEngineError):
    pass


class ManifestParseError(WorkflowEngineError):
    pass


class ChecksumMismatchError(WorkflowEngineError):
    pass


class GovernanceInconsistencyError(WorkflowEngineError):
    pass


class ProtectedPathViolationError(WorkflowEngineError):
    pass
