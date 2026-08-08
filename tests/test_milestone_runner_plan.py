"""AUTO-016 sections 14 and 21: milestone plan loading, plan location, and configuration.

Three subjects, one file, because the contract binds them together: section 21's configuration is
what names a plan location, section 14's loader is what may act on that name, and DEC-016-005's
three rules are the only thing standing between "the runner reads its input" and "a file the
runner is supposed to be guarding decides what the runner may change".

Everything here runs against real artifacts -- real YAML on a real filesystem, a real external
plan root under a redirected `HOME`, real symbolic links, and a real repository directory. No mock
stands in for the behaviour under test.

Two proofs are structural rather than behavioural:

* `TestNoPlanDiscoveryInWorktree` parses every module of the package and asserts that no
  directory-walking, globbing or scanning call exists anywhere in it, and that the single
  directory listing that does exist is the one that reads the provably-external plan root
  (invariant 19). It then shows behaviourally that a plan file sitting in the worktree is never
  found and no directory inside the worktree is ever listed.
* `TestCapabilityModeUnrepresentable` asserts the two capability enums by their whole member set,
  so `bypassPermissions` and `danger-full-access` are absent rather than rejected (invariant 17).
"""

import ast
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_workflow_engine.milestone_runner.config import (
    ClaudePermissionMode,
    CodexSandboxMode,
    InvalidRunnerConfiguration,
    RunnerConfig,
    load_runner_config,
)
from ai_workflow_engine.milestone_runner.git_inspect import derive_repository_identity
from ai_workflow_engine.milestone_runner.models import MilestoneSpec, StopReason
from ai_workflow_engine.milestone_runner.plan import (
    MilestonePlanLoader,
    PlanCoverageMismatch,
    PlanDependencyCycle,
    PlanPathNotAllowlisted,
    PlanValidationError,
    default_plan_root,
    repository_scoped_root,
    resolve_plan_root,
)

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src" / "ai_workflow_engine" / "milestone_runner"
)

#: The remote this suite's configured identity is derived from, so the identity in a configuration
#: payload and the identity `git_inspect` would derive from a live worktree are the same value
#: rather than two hand-written constants that could drift apart.
REMOTE_URL = "https://github.com/example/demo-repo.git"
REPOSITORY_IDENTITY = derive_repository_identity(REMOTE_URL)

#: The thirteen required fields of section 14, transcribed from the contract rather than read off
#: the model, so the schema and this list are two independent witnesses to one count.
REQUIRED_MILESTONE_FIELDS = (
    "schema_version",
    "milestone_id",
    "title",
    "objective",
    "depends_on",
    "contract_sections",
    "allowed_files",
    "forbidden_files",
    "required_symbols",
    "explicit_exclusions",
    "acceptance_criteria",
    "focused_verification",
    "completion_evidence",
)

#: The two optional fields of section 14.
OPTIONAL_MILESTONE_FIELDS = ("additive_reuse_justification", "human_owner_scope_ruling")

#: Every call that would enumerate a directory tree. Invariant 19 forbids all of them anywhere in
#: the package; `os.listdir` is admitted once, against the external root, and is checked separately.
DISCOVERY_CALL_NAMES = (
    "walk",
    "glob",
    "iglob",
    "rglob",
    "scandir",
    "iterdir",
    "fwalk",
)


# --------------------------------------------------------------------------------------
# Fixtures and payload builders
# --------------------------------------------------------------------------------------


def milestone_payload(**overrides: Any) -> dict[str, Any]:
    """A complete, valid milestone document (section 14's thirteen required fields)."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "milestone_id": "AUTO-016-M01",
        "title": "Typed run state and the milestone vocabulary",
        "objective": "Deliver the typed models the rest of the runner is built from.",
        "depends_on": [],
        "contract_sections": ["section 10 run state machine"],
        "allowed_files": ["src/ai_workflow_engine/milestone_runner/models.py"],
        "forbidden_files": ["agentos_workflow/**"],
        "required_symbols": ["milestone_runner.models.RunStatus"],
        "explicit_exclusions": ["No provider invocation."],
        "acceptance_criteria": ["The transition set is a closed frozenset."],
        "focused_verification": [{"command": ["pytest", "-q"], "purpose": "model tests"}],
        "completion_evidence": ["All focused verification commands PASS."],
    }
    payload.update(overrides)
    return payload


def runner_config_payload(repository_root: Path, **overrides: Any) -> dict[str, Any]:
    """A complete, valid section 21 configuration bound to `repository_root`.

    Written out here rather than imported from a shared fixture module: a fixtures module is not
    part of this milestone's surface, and a configuration a reader can see in full is worth more
    in a test that is largely about what the configuration may and may not say.
    """
    payload: dict[str, Any] = {
        "schema_version": 1,
        "repository": {
            "root": str(repository_root),
            "identity": REPOSITORY_IDENTITY,
            "expected_branch": "feature/auto-016-milestone-runner",
            "baseline_sha": "4fa9212ff47171c162ddf863360413a90e0ee79f",
            "conda_environment": "ai-workflow-engine",
        },
        "stage": {
            "stage_id": "AUTO-016",
            "contract_path": "docs/workflow-automation/stage-prompts/AUTO-016.md",
            "contract_sha256": "0" * 64,
        },
        "allowlist": {
            "allowed_paths": ["src/ai_workflow_engine/milestone_runner/**"],
            "forbidden_paths": ["agentos_workflow/**", "self-governance.yaml"],
            "required_coverage": ["src/ai_workflow_engine/milestone_runner/models.py"],
        },
        "review_policy": {
            "max_full_reviews": 1,
            "max_correction_rounds": 1,
            "max_closure_reviews": 1,
            "max_blockers": 3,
            "blocking_severities": ["CRITICAL", "HIGH"],
            "defer_severities": ["MEDIUM", "LOW"],
        },
        "providers": {
            "claude": {"executable": "claude", "arguments": ["-p"], "timeout_seconds": 3600},
            "codex": {"executable": "codex", "arguments": ["exec"], "timeout_seconds": 1800},
            "allowed_environment_variables": ["HOME", "PATH"],
        },
        "verification": {
            "focused": [],
            "final": [{"command": ["pytest", "-q"], "timeout_seconds": 1800}],
        },
    }
    for section, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(section), dict):
            payload[section] = {**payload[section], **value}
        else:
            payload[section] = value
    return payload


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A directory standing in for the target worktree, disposable with `tmp_path`."""
    root = tmp_path / "repository"
    root.mkdir()
    return root


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A redirected `HOME`, so the external artifact root of section 11 is a real directory.

    Redirecting the environment rather than patching `Path.home` keeps the production derivation
    -- which is what section 11 fixes -- exactly as it ships.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("USERPROFILE", raising=False)
    return fake_home


@pytest.fixture
def external_plan_root(home: Path) -> Path:
    """The DEC-016-005 rule 1 default plan root, created empty."""
    root = default_plan_root(REPOSITORY_IDENTITY)
    root.mkdir(parents=True)
    return root


def write_milestone(directory: Path, **overrides: Any) -> Path:
    """Write one milestone document, named for the milestone it defines."""
    payload = milestone_payload(**overrides)
    path = directory / f"{payload['milestone_id']}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return path


def loader(repository: Path, **config_overrides: Any) -> MilestonePlanLoader:
    config = RunnerConfig.model_validate(runner_config_payload(repository, **config_overrides))
    return MilestonePlanLoader(config, repository)


def package_modules() -> Iterator[Path]:
    """Every Python module of the package, so a structural proof covers all of it."""
    yield from sorted(PACKAGE_ROOT.rglob("*.py"))


# --------------------------------------------------------------------------------------
# Section 14 -- the milestone schema
# --------------------------------------------------------------------------------------


class TestPlanSchema:
    """Thirteen required fields, two optional, and fail-closed validation."""

    def test_a_complete_milestone_validates(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root)
        plan = loader(repository).load()
        assert plan.milestone_ids == ("AUTO-016-M01",)

    @pytest.mark.parametrize("field", REQUIRED_MILESTONE_FIELDS)
    def test_every_required_field_is_required(
        self, repository: Path, external_plan_root: Path, field: str
    ) -> None:
        payload = milestone_payload()
        del payload[field]
        (external_plan_root / "AUTO-016-M01.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=True), encoding="utf-8"
        )
        with pytest.raises(PlanValidationError):
            loader(repository).load()

    @pytest.mark.parametrize("field", OPTIONAL_MILESTONE_FIELDS)
    def test_the_two_optional_fields_may_be_omitted(self, field: str) -> None:
        milestone = MilestoneSpec.model_validate(milestone_payload())
        assert getattr(milestone, field) is None

    def test_the_schema_has_exactly_the_contract_s_fields(self) -> None:
        assert set(MilestoneSpec.model_fields) == set(REQUIRED_MILESTONE_FIELDS) | set(
            OPTIONAL_MILESTONE_FIELDS
        )

    def test_an_unknown_field_is_rejected(self, repository: Path, external_plan_root: Path) -> None:
        write_milestone(external_plan_root, unexpected_key="whatever")
        with pytest.raises(PlanValidationError, match="not a valid milestone"):
            loader(repository).load()

    def test_an_unknown_schema_version_is_rejected(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root, schema_version=2)
        with pytest.raises(PlanValidationError, match="schema_version"):
            loader(repository).load()

    def test_a_non_mapping_document_is_rejected(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        (external_plan_root / "AUTO-016-M01.yaml").write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(PlanValidationError, match="YAML mapping"):
            loader(repository).load()

    def test_unparseable_yaml_is_rejected(self, repository: Path, external_plan_root: Path) -> None:
        (external_plan_root / "AUTO-016-M01.yaml").write_text("a: [1,\n", encoding="utf-8")
        with pytest.raises(PlanValidationError, match="not valid YAML"):
            loader(repository).load()

    def test_a_file_whose_name_disagrees_with_its_milestone_is_rejected(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        payload = milestone_payload(milestone_id="AUTO-016-M02")
        (external_plan_root / "AUTO-016-M01.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=True), encoding="utf-8"
        )
        with pytest.raises(PlanValidationError, match="which its name does not name"):
            loader(repository).load()

    def test_an_empty_plan_root_is_a_refusal_not_an_empty_plan(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        with pytest.raises(PlanValidationError, match="no milestone file"):
            loader(repository).load()

    def test_a_symlinked_plan_file_is_never_followed(
        self, repository: Path, external_plan_root: Path, tmp_path: Path
    ) -> None:
        elsewhere = write_milestone(tmp_path)
        (external_plan_root / "AUTO-016-M01.yaml").symlink_to(elsewhere)
        with pytest.raises(PlanValidationError, match="symbolic link"):
            loader(repository).load()


class TestPlanDependencyOrder:
    """Dependencies decide the order, and one plan always yields one order."""

    def test_a_dependency_comes_before_its_dependant(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root)
        write_milestone(
            external_plan_root,
            milestone_id="AUTO-016-M02",
            depends_on=["AUTO-016-M01"],
            allowed_files=["src/ai_workflow_engine/milestone_runner/plan.py"],
        )
        plan = loader(
            repository,
            allowlist={
                "required_coverage": [
                    "src/ai_workflow_engine/milestone_runner/models.py",
                    "src/ai_workflow_engine/milestone_runner/plan.py",
                ]
            },
        ).load()
        assert plan.milestone_ids == ("AUTO-016-M01", "AUTO-016-M02")

    def test_independent_milestones_are_ordered_deterministically(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root, milestone_id="AUTO-016-M02")
        write_milestone(
            external_plan_root,
            milestone_id="AUTO-016-M01",
            allowed_files=["src/ai_workflow_engine/milestone_runner/models.py"],
        )
        write_milestone(
            external_plan_root,
            milestone_id="AUTO-016-M03",
            allowed_files=["src/ai_workflow_engine/milestone_runner/models.py"],
        )
        plan = loader(repository).load()
        assert plan.milestone_ids == ("AUTO-016-M01", "AUTO-016-M02", "AUTO-016-M03")

    def test_a_dependency_outside_the_plan_is_rejected(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root, depends_on=["AUTO-016-M09"])
        with pytest.raises(PlanValidationError, match="which this plan does not define"):
            loader(repository).load()


class TestPlanDependencyCycle:
    """A cycle is rejected, and the message names the whole cycle rather than one member."""

    def test_a_two_milestone_cycle_is_rejected_naming_the_full_cycle(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root, depends_on=["AUTO-016-M02"])
        write_milestone(
            external_plan_root,
            milestone_id="AUTO-016-M02",
            depends_on=["AUTO-016-M01"],
            allowed_files=["src/ai_workflow_engine/milestone_runner/models.py"],
        )
        with pytest.raises(PlanDependencyCycle) as raised:
            loader(repository).load()
        assert "AUTO-016-M01 -> AUTO-016-M02 -> AUTO-016-M01" in str(raised.value)

    def test_a_three_milestone_cycle_names_every_member(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        for current, dependency in (
            ("AUTO-016-M01", "AUTO-016-M03"),
            ("AUTO-016-M02", "AUTO-016-M01"),
            ("AUTO-016-M03", "AUTO-016-M02"),
        ):
            write_milestone(
                external_plan_root,
                milestone_id=current,
                depends_on=[dependency],
                allowed_files=["src/ai_workflow_engine/milestone_runner/models.py"],
            )
        with pytest.raises(PlanDependencyCycle) as raised:
            loader(repository).load()
        message = str(raised.value)
        for milestone_id in ("AUTO-016-M01", "AUTO-016-M02", "AUTO-016-M03"):
            assert milestone_id in message

    def test_a_self_dependency_is_rejected_by_the_schema(self) -> None:
        with pytest.raises(ValueError, match="must not depend on itself"):
            MilestoneSpec.model_validate(milestone_payload(depends_on=["AUTO-016-M01"]))


class TestPlanDuplicateMilestone:
    """One `milestone_id` may be defined once, and the file naming rule makes that structural."""

    def test_the_file_naming_rule_makes_a_duplicate_unreachable_through_the_plan_root(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(external_plan_root)
        paths = loader(repository).plan_paths()
        assert [path.name for path in paths] == ["AUTO-016-M01.yaml"]
        assert len({path.name for path in paths}) == len(paths)

    def test_a_repeated_milestone_is_rejected_rather_than_last_one_wins(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        """The defence-in-depth branch, exercised through a real file named twice.

        Both supported enumerations -- one directory listing filtered to a closed filename
        grammar, and an allowlist of exact paths -- already make a repeated `milestone_id`
        unreachable, which is why the source set is substituted here rather than the loader's
        validation. The file, its contents and every rule applied to them are real.
        """
        path = write_milestone(external_plan_root)

        class RepeatingLoader(MilestonePlanLoader):
            def plan_paths(self) -> tuple[Path, ...]:
                return (path, path)

        config = RunnerConfig.model_validate(runner_config_payload(repository))
        with pytest.raises(PlanValidationError, match="defined more than once"):
            RepeatingLoader(config, repository).load()


class TestPlanCoverageMismatch:
    """Section 4 item 6: the union of every `allowed_files` equals `required_coverage` exactly."""

    def test_an_exact_match_is_accepted(self, repository: Path, external_plan_root: Path) -> None:
        write_milestone(external_plan_root)
        plan = loader(repository).load()
        assert plan.covered_paths() == ("src/ai_workflow_engine/milestone_runner/models.py",)

    def test_a_gap_is_detected(self, repository: Path, external_plan_root: Path) -> None:
        write_milestone(external_plan_root)
        with pytest.raises(PlanCoverageMismatch) as raised:
            loader(
                repository,
                allowlist={
                    "required_coverage": [
                        "src/ai_workflow_engine/milestone_runner/models.py",
                        "src/ai_workflow_engine/milestone_runner/plan.py",
                    ]
                },
            ).load()
        assert raised.value.missing == ("src/ai_workflow_engine/milestone_runner/plan.py",)
        assert raised.value.unexpected == ()

    def test_an_extra_is_detected(self, repository: Path, external_plan_root: Path) -> None:
        write_milestone(
            external_plan_root,
            allowed_files=[
                "src/ai_workflow_engine/milestone_runner/models.py",
                "src/ai_workflow_engine/milestone_runner/scope.py",
            ],
        )
        with pytest.raises(PlanCoverageMismatch) as raised:
            loader(repository).load()
        assert raised.value.missing == ()
        assert raised.value.unexpected == ("src/ai_workflow_engine/milestone_runner/scope.py",)

    def test_a_gap_and_an_extra_are_detected_independently(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        write_milestone(
            external_plan_root, allowed_files=["src/ai_workflow_engine/milestone_runner/scope.py"]
        )
        with pytest.raises(PlanCoverageMismatch) as raised:
            loader(repository).load()
        assert raised.value.missing == ("src/ai_workflow_engine/milestone_runner/models.py",)
        assert raised.value.unexpected == ("src/ai_workflow_engine/milestone_runner/scope.py",)

    def test_the_mismatch_carries_the_contract_s_stop_reason(self) -> None:
        assert PlanCoverageMismatch.stop_reason is StopReason.PLAN_COVERAGE_MISMATCH


# --------------------------------------------------------------------------------------
# DEC-016-005 -- where a plan may come from, and nowhere else
# --------------------------------------------------------------------------------------


class TestDefaultPlanRootIsExternal:
    """Rule 1: with no `stage.plan_directory`, the plan root is outside the worktree."""

    def test_the_default_root_is_the_contract_s_path(self, repository: Path, home: Path) -> None:
        root = resolve_plan_root(
            RunnerConfig.model_validate(runner_config_payload(repository)), repository
        )
        assert (
            root.path
            == home / ".ai-workflow-engine" / "milestone-runs" / (REPOSITORY_IDENTITY) / "plans"
        )
        assert root.is_repository_local is False

    def test_the_default_root_is_outside_the_worktree(
        self, repository: Path, external_plan_root: Path
    ) -> None:
        root = loader(repository).plan_root()
        assert not str(os.path.realpath(root.path)).startswith(
            str(os.path.realpath(repository)) + os.sep
        )

    def test_nothing_inside_the_worktree_is_opened(
        self, repository: Path, external_plan_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A decoy plan inside the worktree is neither listed nor read."""
        decoy_directory = repository / "docs" / "plans"
        decoy_directory.mkdir(parents=True)
        write_milestone(decoy_directory, milestone_id="AUTO-016-M09")
        write_milestone(external_plan_root)

        listed: list[str] = []
        real_listdir = os.listdir

        def recording_listdir(path: Any = ".") -> Any:
            listed.append(str(path))
            return real_listdir(path)

        monkeypatch.setattr(os, "listdir", recording_listdir)
        plan = loader(repository).load()

        assert plan.milestone_ids == ("AUTO-016-M01",)
        assert all(not str(entry).startswith(str(repository)) for entry in listed)
        assert all(not path.startswith(str(repository)) for path in plan.source_paths)

    def test_a_plan_root_that_would_land_inside_the_repository_is_refused(
        self, repository: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(repository))
        with pytest.raises(PlanValidationError, match="must not be inside the repository"):
            resolve_plan_root(
                RunnerConfig.model_validate(runner_config_payload(repository)), repository
            )


class TestPlanRootSharesRepositoryIdentityDerivation:
    """Section 11: the plan root and the run root share one identity and one containment check."""

    def test_the_plan_root_is_a_sibling_of_the_run_directories(self, home: Path) -> None:
        scoped = repository_scoped_root(REPOSITORY_IDENTITY)
        assert default_plan_root(REPOSITORY_IDENTITY).parent == scoped
        assert default_plan_root(REPOSITORY_IDENTITY).name == "plans"

    def test_the_identity_is_the_one_git_inspect_derives(self, home: Path) -> None:
        derived = derive_repository_identity(REMOTE_URL)
        assert repository_scoped_root(derived).name == derived
        assert derived in str(default_plan_root(derived))

    def test_two_spellings_of_one_remote_yield_one_plan_root(self, home: Path) -> None:
        first = derive_repository_identity("https://github.com/example/demo-repo.git")
        second = derive_repository_identity("git@github.com:example/demo-repo")
        assert default_plan_root(first) == default_plan_root(second)

    def test_an_unusable_identity_is_refused_rather_than_joined(self, home: Path) -> None:
        for identity in ("", "..", "a/b"):
            with pytest.raises(PlanValidationError, match="not a usable repository identity"):
                repository_scoped_root(identity)


class TestRepositoryLocalPlanRefusedWhenNotAllowlisted:
    """Rule 2: a repository-local plan the governing contract does not list is refused."""

    def test_it_is_refused_with_the_contract_s_stop_reason(
        self, repository: Path, home: Path
    ) -> None:
        plan_directory = repository / "docs" / "plans"
        plan_directory.mkdir(parents=True)
        write_milestone(plan_directory)
        with pytest.raises(PlanPathNotAllowlisted) as raised:
            loader(repository, stage={"plan_directory": "docs/plans"}).load()
        assert raised.value.stop_reason is StopReason.PLAN_PATH_NOT_ALLOWLISTED

    def test_the_file_is_never_opened(self, repository: Path, home: Path) -> None:
        """The refusal happens before the read, so an unreadable plan refuses identically."""
        plan_directory = repository / "docs" / "plans"
        plan_directory.mkdir(parents=True)
        (plan_directory / "AUTO-016-M01.yaml").write_text(": not yaml at all\n", encoding="utf-8")
        with pytest.raises(PlanPathNotAllowlisted):
            loader(repository, stage={"plan_directory": "docs/plans"}).load()

    def test_an_allowlist_entry_for_a_different_directory_does_not_qualify(
        self, repository: Path, home: Path
    ) -> None:
        plan_directory = repository / "docs" / "plans"
        plan_directory.mkdir(parents=True)
        write_milestone(plan_directory)
        with pytest.raises(PlanPathNotAllowlisted):
            loader(
                repository,
                stage={"plan_directory": "docs/plans"},
                allowlist={
                    "allowed_paths": [
                        "src/ai_workflow_engine/milestone_runner/**",
                        "docs/other/AUTO-016-M01.yaml",
                    ]
                },
            ).load()


class TestRepositoryLocalPlanAcceptedOnlyOnExactAllowlistedPath:
    """Rule 2: not a directory, not a glob, not a prefix -- the exact path or nothing."""

    @pytest.fixture
    def plan_directory(self, repository: Path) -> Path:
        directory = repository / "docs" / "plans"
        directory.mkdir(parents=True)
        write_milestone(directory)
        return directory

    def _load(self, repository: Path, entry: str) -> Any:
        return loader(
            repository,
            stage={"plan_directory": "docs/plans"},
            allowlist={"allowed_paths": ["src/ai_workflow_engine/milestone_runner/**", entry]},
        ).load()

    def test_the_verbatim_path_is_accepted(
        self, repository: Path, home: Path, plan_directory: Path
    ) -> None:
        plan = self._load(repository, "docs/plans/AUTO-016-M01.yaml")
        assert plan.milestone_ids == ("AUTO-016-M01",)
        assert plan.source_paths == (str(repository / "docs" / "plans" / "AUTO-016-M01.yaml"),)

    @pytest.mark.parametrize(
        "entry",
        [
            pytest.param("docs/plans", id="a-directory-entry"),
            pytest.param("docs/plans/*.yaml", id="a-glob"),
            pytest.param("docs/plans/**", id="a-recursive-glob"),
            pytest.param("docs/plans/AUTO-016-M0?.yaml", id="a-single-character-glob"),
            pytest.param("docs/plans/AUTO-016-M01", id="a-prefix-without-the-suffix"),
            pytest.param("docs", id="a-parent-directory"),
        ],
    )
    def test_anything_that_is_not_the_exact_path_is_refused(
        self, repository: Path, home: Path, plan_directory: Path, entry: str
    ) -> None:
        with pytest.raises(PlanPathNotAllowlisted):
            self._load(repository, entry)

    def test_an_allowlisted_path_in_a_subdirectory_of_the_plan_root_does_not_qualify(
        self, repository: Path, home: Path, plan_directory: Path
    ) -> None:
        nested = plan_directory / "nested"
        nested.mkdir()
        write_milestone(nested, milestone_id="AUTO-016-M02")
        with pytest.raises(PlanPathNotAllowlisted):
            self._load(repository, "docs/plans/nested/AUTO-016-M02.yaml")

    def test_an_allowlisted_path_that_does_not_exist_is_a_refusal_not_a_silent_skip(
        self, repository: Path, home: Path
    ) -> None:
        (repository / "docs" / "plans").mkdir(parents=True)
        with pytest.raises(PlanValidationError, match="not a regular file"):
            self._load(repository, "docs/plans/AUTO-016-M01.yaml")


class TestNoPlanDiscoveryInWorktree:
    """Invariant 19: no search, walk, glob, default scan, or `nearest plan wins` behaviour."""

    @staticmethod
    def _called_attribute_names(tree: ast.Module) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Attribute):
                    names.add(function.attr)
                elif isinstance(function, ast.Name):
                    names.add(function.id)
        return names

    @pytest.mark.parametrize("call_name", DISCOVERY_CALL_NAMES)
    def test_no_module_in_the_package_enumerates_a_tree(self, call_name: str) -> None:
        for module in package_modules():
            tree = ast.parse(module.read_text(encoding="utf-8"))
            assert call_name not in self._called_attribute_names(
                tree
            ), f"{module.name} calls {call_name}(), which would be plan discovery"

    def test_the_only_directory_listing_reads_the_external_plan_root(self) -> None:
        listing_functions: list[tuple[str, str]] = []
        for module in package_modules():
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if "listdir" in self._called_attribute_names(
                    ast.Module(body=node.body, type_ignores=[])
                ):
                    listing_functions.append((module.name, node.name))
        assert listing_functions == [("plan.py", "_external_plan_paths")]

    def test_a_plan_beside_the_configured_one_is_not_picked_up(
        self, repository: Path, home: Path
    ) -> None:
        plan_directory = repository / "docs" / "plans"
        plan_directory.mkdir(parents=True)
        write_milestone(plan_directory)
        write_milestone(plan_directory, milestone_id="AUTO-016-M02")
        plan = loader(
            repository,
            stage={"plan_directory": "docs/plans"},
            allowlist={
                "allowed_paths": [
                    "src/ai_workflow_engine/milestone_runner/**",
                    "docs/plans/AUTO-016-M01.yaml",
                ]
            },
        ).load()
        assert plan.milestone_ids == ("AUTO-016-M01",)

    def test_no_directory_inside_the_worktree_is_ever_listed(
        self, repository: Path, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plan_directory = repository / "docs" / "plans"
        plan_directory.mkdir(parents=True)
        write_milestone(plan_directory)

        listed: list[str] = []
        real_listdir = os.listdir

        def recording_listdir(path: Any = ".") -> Any:
            listed.append(str(path))
            return real_listdir(path)

        monkeypatch.setattr(os, "listdir", recording_listdir)
        loader(
            repository,
            stage={"plan_directory": "docs/plans"},
            allowlist={
                "allowed_paths": [
                    "src/ai_workflow_engine/milestone_runner/**",
                    "docs/plans/AUTO-016-M01.yaml",
                ]
            },
        ).load()
        assert all(not entry.startswith(str(repository)) for entry in listed)

    def test_no_configuration_key_enables_discovery(self) -> None:
        plan_related = {
            name for name in RunnerConfig.model_fields if "plan" in name or "discover" in name
        }
        assert plan_related == set()
        stage_fields = RunnerConfig.model_fields["stage"].annotation
        assert stage_fields is not None
        assert {
            name for name in stage_fields.model_fields if "plan" in name or "discover" in name
        } == {"plan_directory"}


class TestPlanRootSymlinkEscapeRejected:
    """Invariant 8: a symlinked plan-root component is rejected, never followed."""

    def test_a_symlinked_default_root_component_is_rejected(
        self, repository: Path, home: Path, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (home / ".ai-workflow-engine").symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(PlanValidationError, match="symbolic link"):
            resolve_plan_root(
                RunnerConfig.model_validate(runner_config_payload(repository)), repository
            )

    def test_a_symlinked_plans_directory_is_rejected(
        self, repository: Path, home: Path, tmp_path: Path
    ) -> None:
        scoped = repository_scoped_root(REPOSITORY_IDENTITY)
        scoped.mkdir(parents=True)
        elsewhere = tmp_path / "elsewhere-plans"
        elsewhere.mkdir()
        (scoped / "plans").symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(PlanValidationError, match="symbolic link"):
            resolve_plan_root(
                RunnerConfig.model_validate(runner_config_payload(repository)), repository
            )

    def test_a_symlinked_repository_local_plan_component_is_rejected(
        self, repository: Path, home: Path
    ) -> None:
        real_directory = repository / "docs" / "real-plans"
        real_directory.mkdir(parents=True)
        write_milestone(real_directory)
        (repository / "docs" / "plans").symlink_to(real_directory, target_is_directory=True)
        with pytest.raises(PlanValidationError, match="symbolic link"):
            loader(repository, stage={"plan_directory": "docs/plans"}).plan_paths()

    def test_a_plan_directory_symlinked_out_of_the_repository_is_refused_as_external(
        self, repository: Path, home: Path, tmp_path: Path
    ) -> None:
        """A link out of the worktree does not become an admissible external root by being one."""
        elsewhere = tmp_path / "elsewhere-docs"
        elsewhere.mkdir()
        (repository / "docs").symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(PlanValidationError, match="artifact root"):
            loader(repository, stage={"plan_directory": "docs/plans"}).plan_paths()

    def test_a_symlink_pointing_back_into_the_repository_is_still_outside_only_in_name(
        self, repository: Path, home: Path
    ) -> None:
        """Containment is decided on the realized path, so a link cannot launder an inside root."""
        inside = repository / "smuggled-plans"
        inside.mkdir()
        (home / ".ai-workflow-engine").mkdir()
        (home / ".ai-workflow-engine" / "milestone-runs").mkdir()
        scoped = repository_scoped_root(REPOSITORY_IDENTITY)
        scoped.mkdir()
        (scoped / "plans").symlink_to(inside, target_is_directory=True)
        with pytest.raises(PlanValidationError, match="must not be inside the repository"):
            resolve_plan_root(
                RunnerConfig.model_validate(runner_config_payload(repository)), repository
            )


class TestConfiguredExternalPlanDirectory:
    """Section 21: an external plan location is admitted only under the artifact root."""

    def test_a_directory_under_the_artifact_root_is_accepted(
        self, repository: Path, home: Path
    ) -> None:
        scoped = repository_scoped_root(REPOSITORY_IDENTITY)
        configured = scoped / "plans-v2"
        configured.mkdir(parents=True)
        write_milestone(configured)
        plan = loader(repository, stage={"plan_directory": str(configured)}).load()
        assert plan.milestone_ids == ("AUTO-016-M01",)

    def test_an_arbitrary_external_directory_is_refused(
        self, repository: Path, home: Path, tmp_path: Path
    ) -> None:
        outside = tmp_path / "anywhere"
        outside.mkdir()
        write_milestone(outside)
        with pytest.raises(PlanValidationError, match="artifact root"):
            loader(repository, stage={"plan_directory": str(outside)}).plan_paths()


# --------------------------------------------------------------------------------------
# Section 21 -- the configuration model
# --------------------------------------------------------------------------------------


class TestConfigValidation:
    """Every section 21 rule, at load, with no fallback anywhere."""

    def _write(self, tmp_path: Path, payload: Any) -> Path:
        path = tmp_path / "runner.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
        return path

    def test_a_complete_configuration_loads(self, tmp_path: Path, repository: Path) -> None:
        config = load_runner_config(self._write(tmp_path, runner_config_payload(repository)))
        assert config.stage.stage_id == "AUTO-016"
        assert config.stage.plan_directory is None

    def test_a_missing_configuration_is_invalid_configuration_not_a_default(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(InvalidRunnerConfiguration, match="Cannot read"):
            load_runner_config(tmp_path / "absent.yaml")

    def test_the_failure_carries_the_contract_s_stop_reason(self) -> None:
        assert InvalidRunnerConfiguration.stop_reason is StopReason.INVALID_CONFIGURATION

    def test_unparseable_yaml_is_invalid_configuration(self, tmp_path: Path) -> None:
        path = tmp_path / "runner.yaml"
        path.write_text("a: [1,\n", encoding="utf-8")
        with pytest.raises(InvalidRunnerConfiguration, match="not valid YAML"):
            load_runner_config(path)

    def test_a_non_mapping_root_is_invalid_configuration(self, tmp_path: Path) -> None:
        path = tmp_path / "runner.yaml"
        path.write_text("- a\n", encoding="utf-8")
        with pytest.raises(InvalidRunnerConfiguration, match="YAML mapping"):
            load_runner_config(path)

    def test_an_oversized_configuration_is_refused_before_it_is_parsed(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "runner.yaml"
        path.write_text("#" + "x" * (1 << 20), encoding="utf-8")
        with pytest.raises(InvalidRunnerConfiguration, match="exceeds"):
            load_runner_config(path)

    def test_an_unknown_schema_version_is_refused(self, tmp_path: Path, repository: Path) -> None:
        payload = runner_config_payload(repository, schema_version=2)
        with pytest.raises(InvalidRunnerConfiguration, match="schema_version"):
            load_runner_config(self._write(tmp_path, payload))

    def test_an_unknown_field_is_refused(self, tmp_path: Path, repository: Path) -> None:
        payload = runner_config_payload(repository)
        payload["unexpected_section"] = {}
        with pytest.raises(InvalidRunnerConfiguration, match="unexpected_section"):
            load_runner_config(self._write(tmp_path, payload))

    @pytest.mark.parametrize(
        "section",
        ["repository", "stage", "allowlist", "review_policy", "providers", "verification"],
    )
    def test_every_required_section_is_required(
        self, tmp_path: Path, repository: Path, section: str
    ) -> None:
        payload = runner_config_payload(repository)
        del payload[section]
        with pytest.raises(InvalidRunnerConfiguration, match=section):
            load_runner_config(self._write(tmp_path, payload))

    def test_a_relative_repository_root_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="absolute POSIX path"):
            RunnerConfig.model_validate(
                runner_config_payload(repository, repository={"root": "relative/repo"})
            )

    def test_a_repository_identity_of_the_wrong_shape_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match=r"repository\.identity"):
            RunnerConfig.model_validate(
                runner_config_payload(repository, repository={"identity": "not-an-identity"})
            )

    def test_a_baseline_that_is_not_an_object_id_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="baseline_sha"):
            RunnerConfig.model_validate(
                runner_config_payload(repository, repository={"baseline_sha": "HEAD"})
            )

    def test_no_branch_has_a_built_in_default(self, repository: Path) -> None:
        payload = runner_config_payload(repository)
        del payload["repository"]["expected_branch"]
        with pytest.raises(ValueError, match="expected_branch"):
            RunnerConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "value", ["/etc/passwd", "../escape.md", "docs/../../escape.md", "docs\\windows.md"]
    )
    def test_a_path_field_outside_the_repository_is_refused(
        self, repository: Path, value: str
    ) -> None:
        with pytest.raises(ValueError, match="contract_path"):
            RunnerConfig.model_validate(
                runner_config_payload(repository, stage={"contract_path": value})
            )

    def test_the_governing_contract_may_not_also_be_writable_surface(
        self, repository: Path
    ) -> None:
        with pytest.raises(ValueError, match="never writable surface"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository,
                    allowlist={
                        "allowed_paths": [
                            "src/ai_workflow_engine/milestone_runner/**",
                            "docs/workflow-automation/stage-prompts/AUTO-016.md",
                        ]
                    },
                )
            )

    def test_a_contract_digest_of_the_wrong_shape_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="contract_sha256"):
            RunnerConfig.model_validate(
                runner_config_payload(repository, stage={"contract_sha256": "abc"})
            )

    def test_a_duplicate_allowlist_entry_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository,
                    allowlist={
                        "allowed_paths": [
                            "src/ai_workflow_engine/milestone_runner/**",
                            "src/ai_workflow_engine/milestone_runner/**",
                        ]
                    },
                )
            )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("max_full_reviews", 2),
            ("max_correction_rounds", 2),
            ("max_closure_reviews", 2),
            ("max_blockers", 4),
        ],
    )
    def test_a_budget_above_its_ceiling_is_refused_at_load(
        self, repository: Path, field: str, value: int
    ) -> None:
        with pytest.raises(ValueError, match=field):
            RunnerConfig.model_validate(
                runner_config_payload(repository, review_policy={field: value})
            )

    def test_a_budget_below_its_ceiling_is_accepted(self, repository: Path) -> None:
        config = RunnerConfig.model_validate(
            runner_config_payload(repository, review_policy={"max_blockers": 1})
        )
        assert config.review_policy.max_blockers == 1

    def test_a_blocking_severity_may_not_be_demoted(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="may never demote"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository,
                    review_policy={
                        "blocking_severities": ["CRITICAL"],
                        "defer_severities": ["HIGH", "MEDIUM", "LOW"],
                    },
                )
            )

    def test_every_severity_must_be_classified(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="unclassified"):
            RunnerConfig.model_validate(
                runner_config_payload(repository, review_policy={"defer_severities": ["MEDIUM"]})
            )

    def test_a_severity_may_not_both_block_and_defer(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="cannot both block and be deferred"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository,
                    review_policy={
                        "blocking_severities": ["CRITICAL", "HIGH", "MEDIUM"],
                        "defer_severities": ["MEDIUM", "LOW"],
                    },
                )
            )

    def test_both_git_flags_default_to_false(self, repository: Path) -> None:
        config = RunnerConfig.model_validate(runner_config_payload(repository))
        assert config.git.execute_commit is False
        assert config.git.execute_push is False

    def test_a_provider_timeout_is_required_with_no_default(self, repository: Path) -> None:
        payload = runner_config_payload(repository)
        del payload["providers"]["claude"]["timeout_seconds"]
        with pytest.raises(ValueError, match="timeout_seconds"):
            RunnerConfig.model_validate(payload)

    def test_an_unbounded_provider_timeout_is_refused(self, repository: Path) -> None:
        payload = runner_config_payload(repository)
        payload["providers"]["claude"]["timeout_seconds"] = 10**9
        with pytest.raises(ValueError, match="timeout_seconds"):
            RunnerConfig.model_validate(payload)

    def test_a_verification_command_is_an_argv_list_not_a_shell_string(
        self, repository: Path
    ) -> None:
        payload = runner_config_payload(repository)
        payload["verification"]["final"] = [
            {"command": "pytest -q && ruff check .", "timeout_seconds": 60}
        ]
        with pytest.raises(ValueError, match="command"):
            RunnerConfig.model_validate(payload)

    def test_the_final_verification_set_may_not_be_empty(self, repository: Path) -> None:
        payload = runner_config_payload(repository)
        payload["verification"]["final"] = []
        with pytest.raises(ValueError, match="final"):
            RunnerConfig.model_validate(payload)

    def test_an_absent_focused_key_is_refused_rather_than_assumed_empty(
        self, repository: Path
    ) -> None:
        payload = runner_config_payload(repository)
        del payload["verification"]["focused"]
        with pytest.raises(ValueError, match="focused"):
            RunnerConfig.model_validate(payload)


class TestConfigRejectsWildcardEnvironment:
    """Section 17: `allowed_environment_variables` accepts no wildcard and has no bypass value."""

    @pytest.mark.parametrize(
        "name", ["*", "**", "PATH*", "*PATH", "AWS_*", "?", "[A-Z]*", "PATH HOME", ""]
    )
    def test_a_wildcard_shaped_entry_is_refused(self, repository: Path, name: str) -> None:
        with pytest.raises(ValueError, match="allowed_environment_variables"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository, providers={"allowed_environment_variables": [name]}
                )
            )

    def test_an_ordinary_variable_name_is_accepted(self, repository: Path) -> None:
        config = RunnerConfig.model_validate(
            runner_config_payload(
                repository, providers={"allowed_environment_variables": ["PATH", "HOME", "_X1"]}
            )
        )
        assert config.providers.allowed_environment_variables == ["PATH", "HOME", "_X1"]

    def test_there_is_no_bypass_value(self, repository: Path) -> None:
        """A suggestive name is an ordinary variable name, never a "forward everything" switch."""
        config = RunnerConfig.model_validate(
            runner_config_payload(repository, providers={"allowed_environment_variables": ["ALL"]})
        )
        assert config.providers.allowed_environment_variables == ["ALL"]

    def test_an_empty_allowlist_forwards_nothing_and_is_valid(self, repository: Path) -> None:
        config = RunnerConfig.model_validate(
            runner_config_payload(repository, providers={"allowed_environment_variables": []})
        )
        assert config.providers.allowed_environment_variables == []

    def test_a_duplicate_entry_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository, providers={"allowed_environment_variables": ["PATH", "PATH"]}
                )
            )

    def test_the_grammar_admits_no_metacharacter_at_all(self) -> None:
        """The refusal is a property of the grammar, not a special case someone must remember."""
        for metacharacter in "*?[]{}!$ \t\n/\\":
            with pytest.raises(ValueError):
                RunnerConfig.model_validate(
                    runner_config_payload(
                        Path("/srv/repo"),
                        providers={"allowed_environment_variables": [f"PATH{metacharacter}"]},
                    )
                )


class TestCapabilityModeUnrepresentable:
    """Invariant 17: the dangerous modes are absent from the type, not rejected by a check."""

    def test_claude_s_permission_modes_are_exactly_the_three_safe_members(self) -> None:
        assert {mode.value for mode in ClaudePermissionMode} == {
            "plan",
            "default",
            "acceptEdits",
        }

    def test_codex_s_sandbox_modes_are_exactly_the_two_safe_members(self) -> None:
        assert {mode.value for mode in CodexSandboxMode} == {"read-only", "workspace-write"}

    def test_bypass_permissions_is_not_a_member(self) -> None:
        assert not hasattr(ClaudePermissionMode, "BYPASS_PERMISSIONS")
        with pytest.raises(ValueError):
            ClaudePermissionMode("bypassPermissions")

    def test_danger_full_access_is_not_a_member(self) -> None:
        assert not hasattr(CodexSandboxMode, "DANGER_FULL_ACCESS")
        with pytest.raises(ValueError):
            CodexSandboxMode("danger-full-access")

    def test_a_configuration_naming_bypass_permissions_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="bypassPermissions"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository,
                    providers={
                        "claude": {
                            "executable": "claude",
                            "arguments": ["-p"],
                            "timeout_seconds": 3600,
                            "permission_mode": "bypassPermissions",
                        }
                    },
                )
            )

    def test_a_configuration_naming_danger_full_access_is_refused(self, repository: Path) -> None:
        with pytest.raises(ValueError, match="danger-full-access"):
            RunnerConfig.model_validate(
                runner_config_payload(
                    repository,
                    providers={
                        "codex": {
                            "executable": "codex",
                            "arguments": ["exec"],
                            "timeout_seconds": 1800,
                            "sandbox_mode": "danger-full-access",
                        }
                    },
                )
            )

    def test_both_modes_default_to_the_least_capable_member(self, repository: Path) -> None:
        config = RunnerConfig.model_validate(runner_config_payload(repository))
        assert config.providers.claude.permission_mode is ClaudePermissionMode.PLAN
        assert config.providers.codex.sandbox_mode is CodexSandboxMode.READ_ONLY

    def test_neither_mode_is_expressible_as_a_value_anywhere_in_the_package(self) -> None:
        """No module names either mode outside a docstring -- so none can pass one on.

        Docstrings are excluded deliberately: `config.py` explains at length *why* the two modes
        are absent, and prose about an absence is not the absence being violated. Everything a
        module could act on -- an enum member, a default, a literal in an argument vector -- is a
        non-docstring constant, and this asserts there is none.
        """
        for module in package_modules():
            tree = ast.parse(module.read_text(encoding="utf-8"))
            docstring_values = {
                ast.get_docstring(node, clean=False)
                for node in ast.walk(tree)
                if isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                )
            }
            assert ast.get_docstring(tree) is not None
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if node.value in docstring_values:
                    continue
                for forbidden in ("bypassPermissions", "danger-full-access"):
                    assert (
                        forbidden not in node.value
                    ), f"{module.name} carries {forbidden!r} in an actionable string constant"
