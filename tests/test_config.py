from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ai_workflow_engine.config import load_config
from ai_workflow_engine.exceptions import InvalidConfigurationError, NotGitRepositoryError
from ai_workflow_engine.models import (
    _READ_ONLY_STAGES,
    _SCOPED_WRITE_STAGES,
    AgentSettings,
    EngineConfig,
    VerificationBundleSettings,
    VerificationSettings,
)


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


# ---- Verification bundles (T-307) ---------------------------------------------


def make_bundle(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "quality",
        "commands": [["pytest", "-q"], ["git", "diff", "--check"]],
        "timeout_seconds": 3600,
    }
    base.update(overrides)
    return base


def test_verification_defaults_to_no_bundles(repository: Path, config_factory: object) -> None:
    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert config.verification.bundles == []


def test_absent_verification_section_is_the_pre_existing_behaviour(
    repository: Path, config_factory: object
) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    assert "verification" not in yaml.safe_load(path.read_text())
    config = load_config(path)
    assert config.verification == VerificationSettings()


def test_valid_bundle() -> None:
    bundle = VerificationBundleSettings.model_validate(make_bundle())
    assert bundle.name == "quality"
    assert bundle.commands == [["pytest", "-q"], ["git", "diff", "--check"]]


def test_timeout_defaults_to_the_runners_existing_verification_timeout() -> None:
    payload = make_bundle()
    del payload["timeout_seconds"]
    assert VerificationBundleSettings.model_validate(payload).timeout_seconds == 3600


@pytest.mark.parametrize("name", ["1bad", "-bad", "has space", "", "x" * 65, ".dot"])
def test_bad_bundle_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(name=name))


def test_empty_commands_rejected() -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(commands=[]))


def test_empty_argv_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one token"):
        VerificationBundleSettings.model_validate(make_bundle(commands=[[]]))


def test_empty_token_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        VerificationBundleSettings.model_validate(make_bundle(commands=[["pytest", ""]]))


@pytest.mark.parametrize("token", ["with\x00nul", "with\nnewline", "with\rreturn"])
def test_token_with_forbidden_control_character_rejected(token: str) -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(commands=[[token]]))


def test_token_with_surrogate_code_point_rejected() -> None:
    with pytest.raises(ValidationError, match="surrogate"):
        VerificationBundleSettings.model_validate(make_bundle(commands=[["\ud800"]]))


@pytest.mark.parametrize("token", [1, None, True, ["nested"]])
def test_non_string_token_rejected(token: object) -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(commands=[[token]]))


def test_commands_must_be_a_list_of_argv_lists() -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(commands=["pytest -q"]))


@pytest.mark.parametrize("timeout", [0, -1, 86401])
def test_bundle_timeout_out_of_bounds_rejected(timeout: int) -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(timeout_seconds=timeout))


@pytest.mark.parametrize("timeout", [1, 86400])
def test_bundle_timeout_bounds_accepted(timeout: int) -> None:
    bundle = VerificationBundleSettings.model_validate(make_bundle(timeout_seconds=timeout))
    assert bundle.timeout_seconds == timeout


def test_unknown_bundle_key_rejected() -> None:
    with pytest.raises(ValidationError):
        VerificationBundleSettings.model_validate(make_bundle(surprise=True))


def test_duplicate_bundle_names_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        VerificationSettings.model_validate(
            {"bundles": [make_bundle(name="dup"), make_bundle(name="dup")]}
        )


def test_bundles_round_trip_through_load_config(repository: Path, config_factory: object) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["verification"] = {
        "bundles": [make_bundle(name="zeta"), make_bundle(name="alpha")],
    }
    path.write_text(yaml.safe_dump(raw))
    config = load_config(path)
    # Configured order is preserved: it is the execution order, and sorting it would misreport
    # what ran.
    assert [bundle.name for bundle in config.verification.bundles] == ["zeta", "alpha"]


def test_duplicate_bundle_names_rejected_through_load_config(
    repository: Path, config_factory: object
) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["verification"] = {"bundles": [make_bundle(name="dup"), make_bundle(name="dup")]}
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(InvalidConfigurationError, match="Invalid configuration"):
        load_config(path)


# ---- Reviewer immutability (§4.1, AC9) ----------------------------------------


def test_a_bundle_carries_no_mode_or_stage_surface() -> None:
    """A bundle cannot promote anything: it has no field that names a mode or a stage."""
    assert set(VerificationBundleSettings.model_fields) == {
        "name",
        "commands",
        "timeout_seconds",
    }
    assert set(VerificationSettings.model_fields) == {"bundles"}


def test_the_agent_stage_permission_sets_are_unchanged() -> None:
    assert _READ_ONLY_STAGES == frozenset(
        {"plan-review", "implementation-review", "governance-closeout", "governance-review"}
    )
    assert _SCOPED_WRITE_STAGES == frozenset({"implementation", "remediation"})


def test_configuring_bundles_cannot_promote_a_review_agent(
    repository: Path, config_factory: object
) -> None:
    path = config_factory(repository)  # type: ignore[operator]
    raw = yaml.safe_load(path.read_text())
    raw["agents"] = [make_agent(name="reviewer", mode="read-only", stages=["plan-review"])]
    raw["verification"] = {"bundles": [make_bundle()]}
    path.write_text(yaml.safe_dump(raw))
    config = load_config(path)
    assert config.agents[0].mode == "read-only"
    assert config.verification.bundles[0].name == "quality"
