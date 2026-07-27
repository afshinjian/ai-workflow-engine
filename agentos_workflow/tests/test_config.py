"""Tests for agentos_workflow.config (CONFIGURATION_MODEL.md)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agentos_workflow.config.loader import (
    ConfigurationNotFoundError,
    ConfigurationRepositoryMismatchError,
    InvalidConfigurationError,
    discover_config_path,
    load_config,
)
from agentos_workflow.config.schema import (
    WorkflowConfig,
    canonical_repository_relative_path,
)


def _valid_config_dict(repository_path: Path) -> dict[str, object]:
    return {
        "repository_path": str(repository_path),
        "repository_identity": "github.com/org/some-other-repo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/some-program/stage-prompts",
        "stage_branch_naming": "governance/{stage_id}-{slug}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests", "ci/lint"],
        "merge_method": "squash",
        "claude_cli_executable": "/usr/local/bin/claude",
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": "/usr/local/bin/codex",
        "codex_cli_timeout_seconds": 1800,
        "allowed_environment_variables": ["PATH", "HOME", "LANG"],
        "allowed_changed_paths": ["docs/some-program/**"],
        "forbidden_changed_paths": ["src/**", "tests/**", ".github/**"],
        "repair_attempt_limit": 3,
        "state_directory": "/home/user/.agentos/state/some-other-repo",
        "audit_directory": "/home/user/.agentos/audit/some-other-repo",
    }


class TestWorkflowConfigSchema:
    def test_valid_config_parses(self, tmp_path: Path) -> None:
        config = WorkflowConfig.model_validate(_valid_config_dict(tmp_path))
        assert config.baseline_branch == "main"
        assert config.merge_method == "squash"
        assert config.repair_attempt_limit == 3

    def test_missing_required_field_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        del raw["baseline_branch"]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_extra_field_forbidden(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["unexpected_field"] = "nope"
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_baseline_branch_has_no_default(self, tmp_path: Path) -> None:
        # No field in this schema is ever hard-coded globally (CONFIGURATION_MODEL.md §1);
        # omitting it must fail, never silently fall back to "main".
        raw = _valid_config_dict(tmp_path)
        del raw["baseline_branch"]
        with pytest.raises(ValidationError, match="baseline_branch"):
            WorkflowConfig.model_validate(raw)

    def test_merge_method_fixed_to_squash(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["merge_method"] = "merge"
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_repair_attempt_limit_fixed_to_three(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["repair_attempt_limit"] = 5
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_repository_path_must_be_absolute(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["repository_path"] = "relative/path"
        with pytest.raises(ValidationError, match="absolute"):
            WorkflowConfig.model_validate(raw)

    def test_cli_executables_must_be_absolute(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["claude_cli_executable"] = "claude"
        with pytest.raises(ValidationError, match="absolute"):
            WorkflowConfig.model_validate(raw)

    def test_state_and_audit_directories_must_be_absolute(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["state_directory"] = "relative/state"
        with pytest.raises(ValidationError, match="absolute"):
            WorkflowConfig.model_validate(raw)

    def test_stage_contract_directory_must_be_relative(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["stage_contract_directory"] = "/absolute/stage/contracts"
        with pytest.raises(ValidationError, match="relative"):
            WorkflowConfig.model_validate(raw)

    def test_stage_contract_directory_must_stay_confined(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["stage_contract_directory"] = "../escape"
        with pytest.raises(ValidationError, match="repository_path"):
            WorkflowConfig.model_validate(raw)

    def test_allowed_environment_variables_rejects_wildcard(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["allowed_environment_variables"] = ["PATH", "*"]
        with pytest.raises(ValidationError, match="wildcard"):
            WorkflowConfig.model_validate(raw)


# ---------------------------------------------------------------------------------------------
# AUTO002-F09: `allowed_changed_paths`/`forbidden_changed_paths` are glob patterns matched
# (`fnmatch.fnmatchcase`, `engine.py`'s `_matches_any`) against repository-*relative* changed-file
# paths — an absolute pattern or one containing a `..` segment can never match a real changed
# path at all. Previously accepted with no validation; for `forbidden_changed_paths` specifically,
# an inert pattern is worse than doing nothing — it looks like a protection that was never
# actually in effect (CONFIGURATION_MODEL.md §4: "no path may resolve outside the intended
# boundary").
# ---------------------------------------------------------------------------------------------


class TestF09ChangedPathPatternConfinement:
    def test_absolute_allowed_pattern_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["allowed_changed_paths"] = ["/etc/**"]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_absolute_forbidden_pattern_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = ["/etc/**"]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_leading_parent_traversal_pattern_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = ["../../outside/**"]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_bare_parent_traversal_pattern_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = [".."]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_embedded_parent_traversal_segment_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["allowed_changed_paths"] = ["docs/foo/../bar/**"]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_blank_pattern_rejected(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = [""]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_legitimate_patterns_still_accepted(self, tmp_path: Path) -> None:
        config = WorkflowConfig.model_validate(_valid_config_dict(tmp_path))
        assert config.allowed_changed_paths == ["docs/some-program/**"]
        assert config.forbidden_changed_paths == ["src/**", "tests/**", ".github/**"]

    def test_dotfile_pattern_not_mistaken_for_traversal(self, tmp_path: Path) -> None:
        # ".github/**" (a real, legitimate pattern already in the default fixture) must never be
        # rejected by the ".." check — it starts with a single dot, not a parent-traversal token.
        raw = _valid_config_dict(tmp_path)
        raw["allowed_changed_paths"] = [".github/workflows/**"]
        config = WorkflowConfig.model_validate(raw)
        assert config.allowed_changed_paths == [".github/workflows/**"]


class TestConfigDiscovery:
    def test_discover_default_path(self, tmp_path: Path) -> None:
        resolved = discover_config_path(tmp_path)
        assert resolved == tmp_path / ".agentos" / "workflow.yaml"

    def test_discover_explicit_override(self, tmp_path: Path) -> None:
        override = tmp_path / "custom" / "config.yaml"
        resolved = discover_config_path(tmp_path, config_path_override=override)
        assert resolved == override


class TestLoadConfig:
    def test_missing_configuration_is_a_precondition_failure(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationNotFoundError):
            load_config(tmp_path)

    def test_loads_valid_configuration_from_default_path(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".agentos"
        config_dir.mkdir()
        (config_dir / "workflow.yaml").write_text(
            yaml.safe_dump(_valid_config_dict(tmp_path)), encoding="utf-8"
        )
        config = load_config(tmp_path)
        assert isinstance(config, WorkflowConfig)
        assert config.remote_name == "origin"

    def test_loads_valid_configuration_from_explicit_override(self, tmp_path: Path) -> None:
        override = tmp_path / "elsewhere" / "workflow.yaml"
        override.parent.mkdir(parents=True)
        override.write_text(yaml.safe_dump(_valid_config_dict(tmp_path)), encoding="utf-8")
        config = load_config(tmp_path, config_path_override=override)
        assert config.repository_identity == "github.com/org/some-other-repo"

    def test_non_mapping_yaml_root_is_invalid(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".agentos"
        config_dir.mkdir()
        (config_dir / "workflow.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(InvalidConfigurationError, match="mapping"):
            load_config(tmp_path)

    def test_schema_violation_is_invalid_configuration(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".agentos"
        config_dir.mkdir()
        raw = _valid_config_dict(tmp_path)
        del raw["baseline_branch"]
        (config_dir / "workflow.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(InvalidConfigurationError):
            load_config(tmp_path)


class TestConfigRepositoryBinding:
    """Release-gate finding: `load_config(repository_path, ...)` must fail closed unless the
    loaded configuration's own canonical `repository_path` identifies the same repository the
    caller actually requested — for both default `.agentos/workflow.yaml` discovery and an
    explicit override. A canonical symlink alias to the same repository is still accepted.
    """

    def test_default_discovery_rejects_configuration_declaring_a_different_repository(
        self, tmp_path: Path
    ) -> None:
        repository_a = tmp_path / "repo-a"
        repository_b = tmp_path / "repo-b"
        repository_a.mkdir()
        repository_b.mkdir()
        config_dir = repository_a / ".agentos"
        config_dir.mkdir()
        # repo-a's own config file declares repo-b as the target repository.
        (config_dir / "workflow.yaml").write_text(
            yaml.safe_dump(_valid_config_dict(repository_b)), encoding="utf-8"
        )
        with pytest.raises(ConfigurationRepositoryMismatchError):
            load_config(repository_a)

    def test_explicit_override_declaring_a_different_repository_is_rejected(
        self, tmp_path: Path
    ) -> None:
        repository_a = tmp_path / "repo-a"
        repository_b = tmp_path / "repo-b"
        repository_a.mkdir()
        repository_b.mkdir()
        override = tmp_path / "elsewhere" / "workflow.yaml"
        override.parent.mkdir(parents=True)
        override.write_text(yaml.safe_dump(_valid_config_dict(repository_b)), encoding="utf-8")
        with pytest.raises(ConfigurationRepositoryMismatchError):
            load_config(repository_a, config_path_override=override)

    def test_symlink_alias_resolving_to_the_same_repository_is_accepted(
        self, tmp_path: Path
    ) -> None:
        real_repository = tmp_path / "real-repo"
        real_repository.mkdir()
        config_dir = real_repository / ".agentos"
        config_dir.mkdir()
        (config_dir / "workflow.yaml").write_text(
            yaml.safe_dump(_valid_config_dict(real_repository)), encoding="utf-8"
        )
        alias = tmp_path / "alias-repo"
        alias.symlink_to(real_repository)

        config = load_config(alias)
        assert config.repository_path.resolve() == real_repository.resolve()

    def test_state_and_audit_directory_values_cannot_redirect_the_target_repository(
        self, tmp_path: Path
    ) -> None:
        """Even a configuration whose `state_directory`/`audit_directory` happen to point at the
        requested repository's own storage locations must still be rejected if its
        `repository_path` names a different repository — those fields are not consulted for this
        check at all; only the canonical `repository_path` binding is authoritative.
        """
        repository_a = tmp_path / "repo-a"
        repository_b = tmp_path / "repo-b"
        repository_a.mkdir()
        repository_b.mkdir()
        config_dir = repository_a / ".agentos"
        config_dir.mkdir()
        raw = _valid_config_dict(repository_b)
        raw["state_directory"] = str(tmp_path / "state" / "repo-a")
        raw["audit_directory"] = str(tmp_path / "audit" / "repo-a")
        (config_dir / "workflow.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(ConfigurationRepositoryMismatchError):
            load_config(repository_a)


# ---------------------------------------------------------------------------------------------
# AUTO002-IR-03: F09 only rejected absolute and `..` patterns. An independent review reproduced
# *noncanonical but non-traversing* patterns (`docs/./secret/**`, `docs//secret/**`, backslash and
# Windows-drive forms) being accepted and passed raw into `fnmatch`. Git reports the changed file
# as the canonical `docs/secret/x`, which none of those spellings match — so a `forbidden`
# pattern stayed inert and a broader `allowed` pattern won, i.e. a configuration that reads as
# forbidding a path while actually allowing it. Design: strict rejection of every noncanonical
# spelling (DD-23), never partial normalization.
# ---------------------------------------------------------------------------------------------


_NONCANONICAL_PATTERNS = [
    "docs/./secret/**",
    "docs//secret/**",
    "docs\\secret\\**",
    "./docs/secret/**",
    "docs/x/../secret/**",
    "/docs/secret/**",
    "C:\\docs\\secret\\**",
    "C:/docs/secret/**",
    "\\\\server\\share\\**",
]


class TestAUTO002IR03NoncanonicalChangedPathPatternsRejected:
    @pytest.mark.parametrize("pattern", _NONCANONICAL_PATTERNS)
    def test_noncanonical_forbidden_pattern_rejected(self, tmp_path: Path, pattern: str) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = [pattern]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    @pytest.mark.parametrize("pattern", _NONCANONICAL_PATTERNS)
    def test_noncanonical_allowed_pattern_rejected(self, tmp_path: Path, pattern: str) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["allowed_changed_paths"] = [pattern]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    @pytest.mark.parametrize("pattern", ["", "   ", "\t", "docs/", "docs/secret//"])
    def test_blank_and_empty_segment_patterns_rejected(self, tmp_path: Path, pattern: str) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = [pattern]
        with pytest.raises(ValidationError):
            WorkflowConfig.model_validate(raw)

    def test_error_message_identifies_the_rejected_pattern(self, tmp_path: Path) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["forbidden_changed_paths"] = ["src/**", "docs/./secret/**"]
        with pytest.raises(ValidationError) as caught:
            WorkflowConfig.model_validate(raw)
        message = str(caught.value)
        assert "docs/./secret/**" in message
        assert "current-directory segment" in message

    @pytest.mark.parametrize(
        "pattern",
        [
            "docs/secret/**",
            "src/**",
            ".github/workflows/**",
            "docs/*.md",
            "docs/?.md",
            "docs/[abc]/**",
            "docs/**/notes.md",
            "a",
        ],
    )
    def test_canonical_patterns_including_glob_tokens_still_accepted(
        self, tmp_path: Path, pattern: str
    ) -> None:
        raw = _valid_config_dict(tmp_path)
        raw["allowed_changed_paths"] = [pattern]
        config = WorkflowConfig.model_validate(raw)
        # Strict rejection stores the pattern verbatim — no rewriting step that could
        # reinterpret a glob token.
        assert config.allowed_changed_paths == [pattern]


class TestAUTO002IR03ObservedPathCanonicalisation:
    @pytest.mark.parametrize(
        ("observed", "expected"),
        [
            ("docs/secret/x.md", "docs/secret/x.md"),
            ("docs/./secret/x.md", "docs/secret/x.md"),
            ("docs//secret/x.md", "docs/secret/x.md"),
            ("./docs/secret/x.md", "docs/secret/x.md"),
            ("docs/x/../secret/x.md", "docs/secret/x.md"),
        ],
    )
    def test_observed_paths_reduce_to_one_representation(
        self, observed: str, expected: str
    ) -> None:
        assert canonical_repository_relative_path(observed) == expected

    def test_backslash_is_preserved_as_a_legal_posix_filename_character(self) -> None:
        # Rewriting '\' to '/' would silently reinterpret a legitimate POSIX filename, so
        # canonicalisation leaves it alone; configuration patterns reject it outright instead.
        assert canonical_repository_relative_path("docs/a\\b.md") == "docs/a\\b.md"

    def test_canonical_path_is_a_fixed_point(self) -> None:
        once = canonical_repository_relative_path("docs/./a//b/../c.md")
        assert canonical_repository_relative_path(once) == once
