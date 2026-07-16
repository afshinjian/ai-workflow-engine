from pathlib import Path

import pytest
import yaml

from ai_workflow_engine.config import load_config
from ai_workflow_engine.exceptions import InvalidConfigurationError, NotGitRepositoryError


def test_loads_valid_configuration(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    config = load_config(path)
    assert config.project.repository == repository.resolve()
    assert config.project.id == "test-project"


def test_prevents_path_traversal(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["governance"]["project_state"] = "../outside.md"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="escapes repository"):
        load_config(path)


def test_configuration_allows_absent_repository_bounded_handover_paths(
    repository: Path, config_factory: object
) -> None:
    (repository / "handover/PROJECT_HANDOVER.md").unlink()
    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert config.handover.files[0] == "handover/PROJECT_HANDOVER.md"


def test_rejects_non_git_repository(tmp_path: Path, config_factory: object) -> None:
    repository = tmp_path / "ordinary"
    repository.mkdir()
    path = config_factory(repository)  # type: ignore[operator]
    with pytest.raises(NotGitRepositoryError):
        load_config(path)


def test_rejects_unknown_configuration_key(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["surprise"] = True
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="Invalid configuration"):
        load_config(path)
