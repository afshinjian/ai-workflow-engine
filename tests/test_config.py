from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ai_workflow_engine.config import load_config
from ai_workflow_engine.exceptions import InvalidConfigurationError, NotGitRepositoryError
from ai_workflow_engine.models import AgentSettings, EngineConfig


def make_agent(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "reviewer",
        "executable": "/usr/bin/true",
        "args": [],
        "mode": "read-only",
        "timeout_seconds": 60,
        "stages": ["plan-review"],
    }
    base.update(overrides)
    return base


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


def test_loads_valid_conda_environment(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    config = load_config(path)
    assert config.project.conda_environment == "ai-workflow-engine"


def test_rejects_missing_conda_environment(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    del raw["project"]["conda_environment"]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="Invalid configuration"):
        load_config(path)


def test_rejects_empty_conda_environment(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["project"]["conda_environment"] = ""
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="Invalid configuration"):
        load_config(path)


def test_rejects_whitespace_only_conda_environment(
    repository: Path, config_factory: object
) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["project"]["conda_environment"] = "   \t  "
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="Invalid configuration"):
        load_config(path)


# ---- AgentSettings (Milestone 3, task T-303) -----------------------------------


def test_agents_default_to_empty(repository: Path, config_factory: object) -> None:
    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert config.agents == []


def test_valid_read_only_agent() -> None:
    agent = AgentSettings.model_validate(make_agent(stages=["plan-review", "governance-review"]))
    assert agent.mode == "read-only"


def test_valid_scoped_write_agent() -> None:
    agent = AgentSettings.model_validate(
        make_agent(name="writer", mode="scoped-write", stages=["implementation", "remediation"])
    )
    assert agent.stages == ["implementation", "remediation"]


def test_relative_executable_rejected() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        AgentSettings.model_validate(make_agent(executable="bin/agent"))


@pytest.mark.parametrize("name", ["1bad", "-bad", "has space", "", "x" * 65])
def test_bad_agent_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        AgentSettings.model_validate(make_agent(name=name))


@pytest.mark.parametrize("timeout", [0, -1, 86401])
def test_timeout_out_of_bounds_rejected(timeout: int) -> None:
    with pytest.raises(ValidationError):
        AgentSettings.model_validate(make_agent(timeout_seconds=timeout))


@pytest.mark.parametrize("timeout", [1, 86400])
def test_timeout_bounds_accepted(timeout: int) -> None:
    agent = AgentSettings.model_validate(make_agent(timeout_seconds=timeout))
    assert agent.timeout_seconds == timeout


def test_empty_stages_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentSettings.model_validate(make_agent(stages=[]))


def test_duplicate_stages_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        AgentSettings.model_validate(make_agent(stages=["plan-review", "plan-review"]))


def test_read_only_agent_rejects_write_stage() -> None:
    with pytest.raises(ValidationError, match="not permitted"):
        AgentSettings.model_validate(make_agent(mode="read-only", stages=["implementation"]))


def test_scoped_write_agent_rejects_review_stage() -> None:
    with pytest.raises(ValidationError, match="not permitted"):
        AgentSettings.model_validate(
            make_agent(name="w", mode="scoped-write", stages=["plan-review"])
        )


@pytest.mark.parametrize("mode", ["read-only", "scoped-write"])
def test_push_stage_forbidden_for_every_agent(mode: str) -> None:
    with pytest.raises(ValidationError, match="not permitted"):
        AgentSettings.model_validate(make_agent(name="p", mode=mode, stages=["push"]))


def test_duplicate_agent_names_rejected(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["agents"] = [make_agent(name="dup"), make_agent(name="dup")]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="Invalid configuration"):
        load_config(path)


def test_agents_round_trip_through_load_config(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["agents"] = [
        make_agent(name="reviewer", stages=["plan-review"]),
        make_agent(name="writer", mode="scoped-write", stages=["implementation"]),
    ]
    path.write_text(yaml.safe_dump(raw))
    config = load_config(path)
    assert isinstance(config, EngineConfig)
    assert [agent.name for agent in config.agents] == ["reviewer", "writer"]
