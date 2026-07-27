"""Configuration discovery and loading (CONFIGURATION_MODEL.md §2)."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentos_workflow.config.schema import WorkflowConfig

DEFAULT_CONFIG_RELATIVE_PATH = Path(".agentos/workflow.yaml")


class ConfigurationError(Exception):
    """Base error for configuration discovery and loading failures."""


class ConfigurationNotFoundError(ConfigurationError):
    """Raised when no configuration file exists at the discovered or overridden path."""


class InvalidConfigurationError(ConfigurationError):
    """Raised when a configuration file exists but fails schema validation."""


class ConfigurationRepositoryMismatchError(ConfigurationError):
    """Raised when a loaded configuration's own `repository_path` does not canonically identify
    the same repository the caller actually requested — for either the default
    `.agentos/workflow.yaml` discovery path or an explicit override.

    Without this check, a caller could be pointed (by a wrong working directory, a misconfigured
    override, or a symlink farm) at a configuration file that declares an entirely different
    target repository, and every subsequent operation (locking, state/audit storage, git
    operations) would silently proceed against that wrong repository instead of the one the
    caller actually asked for. A canonical symlink alias to the *same* underlying repository is
    still accepted — this rejects a genuinely different repository, not a different path spelling
    of the same one.
    """


def discover_config_path(repository_path: Path, config_path_override: Path | None = None) -> Path:
    """Resolve the configuration path: an explicit override, else the per-repository default.

    Never guesses or defaults `baseline_branch` or any other field when the file is absent —
    that is `load_config`'s job to reject outright (CONFIGURATION_MODEL.md §2).
    """
    if config_path_override is not None:
        return config_path_override
    return repository_path / DEFAULT_CONFIG_RELATIVE_PATH


def load_config(repository_path: Path, config_path_override: Path | None = None) -> WorkflowConfig:
    """Discover, parse, and validate the target repository's configuration.

    Fails closed (`ConfigurationRepositoryMismatchError`) unless the loaded configuration's own
    `repository_path` canonically identifies (`Path.resolve()`) the same repository as the
    `repository_path` argument this function was actually called with — for both the default
    `.agentos/workflow.yaml` discovery path and an explicit `config_path_override`. A canonical
    symlink alias to the same underlying repository resolves identically and is accepted; a
    configuration declaring a genuinely different repository is rejected before it is ever
    returned to a caller, so nothing downstream (locking, state/audit storage, git operations) can
    be silently redirected to the wrong target.
    """
    config_path = discover_config_path(repository_path, config_path_override)
    if not config_path.is_file():
        raise ConfigurationNotFoundError(
            f"No workflow configuration found at {config_path}; a missing configuration is a "
            "precondition failure, never an assumed default"
        )
    try:
        raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidConfigurationError(f"Cannot read configuration {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidConfigurationError(f"Configuration root must be a YAML mapping: {config_path}")
    try:
        config = WorkflowConfig.model_validate(raw)
    except ValidationError as exc:
        raise InvalidConfigurationError(f"Invalid configuration {config_path}: {exc}") from exc

    requested_canonical = repository_path.resolve()
    loaded_canonical = config.repository_path.resolve()
    if loaded_canonical != requested_canonical:
        raise ConfigurationRepositoryMismatchError(
            f"Configuration {config_path} declares repository_path "
            f"{str(config.repository_path)!r} (canonical: {loaded_canonical}), which does not "
            f"identify the requested repository {str(repository_path)!r} (canonical: "
            f"{requested_canonical}). Refusing to load a configuration for a different target "
            "repository."
        )
    return config
