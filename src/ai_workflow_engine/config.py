"""YAML configuration loading and repository-bound path validation."""

import posixpath
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError

from ai_workflow_engine.exceptions import (
    GitCommandError,
    InvalidConfigurationError,
    NotGitRepositoryError,
    RepositoryNotFoundError,
)
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig


def normalize_repository_path(relative: str) -> str:
    """Return a normalized repository-relative POSIX path."""
    candidate = PurePosixPath(relative)
    if candidate.is_absolute():
        raise InvalidConfigurationError(f"Project path must be relative: {relative}")
    normalized = posixpath.normpath(relative)
    if normalized in {"", "."}:
        raise InvalidConfigurationError(f"Project path must name a file: {relative}")
    if normalized == ".." or normalized.startswith("../"):
        raise InvalidConfigurationError(f"Project path escapes repository: {relative}")
    return normalized


def repository_path(repository: Path, relative: str, *, must_exist: bool = True) -> Path:
    normalized = normalize_repository_path(relative)
    root = repository.resolve()
    resolved = (root / Path(normalized)).resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise InvalidConfigurationError(f"Project path escapes repository: {relative}")
    if must_exist and not resolved.exists():
        raise InvalidConfigurationError(f"Required project path does not exist: {relative}")
    return resolved


def load_config(path: Path) -> EngineConfig:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidConfigurationError(f"Cannot read configuration {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidConfigurationError("Configuration root must be a YAML mapping")
    try:
        config = EngineConfig.model_validate(raw)
    except ValidationError as exc:
        raise InvalidConfigurationError(f"Invalid configuration: {exc}") from exc

    repository = config.project.repository.expanduser()
    if not repository.exists() or not repository.is_dir():
        raise RepositoryNotFoundError(f"Repository not found: {repository}")
    repository = repository.resolve()
    if not (repository / ".git").exists():
        # Worktrees have a .git file, ordinary repositories have a directory.
        raise NotGitRepositoryError(f"Not a Git worktree: {repository}")
    try:
        if not GitClient(repository).is_worktree():
            raise NotGitRepositoryError(f"Not a Git worktree: {repository}")
    except GitCommandError as exc:
        raise NotGitRepositoryError(f"Not a usable Git worktree: {repository}: {exc}") from exc
    config.project.repository = repository

    paths = [
        *config.governance.document_paths(),
        config.governance.pyproject,
        config.handover.manifest,
        *config.handover.files,
    ]
    for relative in dict.fromkeys(paths):
        repository_path(repository, relative, must_exist=False)
    for rule in config.governance.facts:
        for relative in rule.paths:
            repository_path(repository, relative, must_exist=False)
    return config
