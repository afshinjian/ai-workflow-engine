"""AUTO-016 sections 15 and 20: the segment-aware scope guard and read-only Git evidence.

Two subjects, one file, because they are two halves of one boundary: the guard decides whether a
changed-path set is in scope, and the inspector is the only thing allowed to say what changed.

Everything here runs against real artifacts. The Git tests build actual repositories with `git
init`, make actual changes, and read them back through the production inspector; no mock stands
in for the behaviour under test, matching the discipline the repository's existing Git tests
already follow.

Two proofs are structural rather than behavioural, and both are named by the milestone:

* `TestP1GlobDoesNotCrossPathSeparator` pins prototype defect P-1 in both directions -- the
  negative case `fnmatch` got wrong, and the `**` positive case that must keep working.
* `TestNoMutatingGitSubcommandInInspector` parses `git_inspect.py` and asserts that no
  state-changing Git subcommand appears anywhere in it -- not in an argument vector, not in a
  constant, not in a docstring. Section 20 requires argv shapes that cannot express those
  operations; a source-level absence is the strongest available witness that none is one edit
  away.
"""

import ast
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from ai_workflow_engine.milestone_runner.config import RunnerConfig
from ai_workflow_engine.milestone_runner.git_inspect import (
    READ_ONLY_GIT_SUBCOMMANDS,
    ContractPinMismatch,
    GitInspectionError,
    GitReadOnlyInspector,
    RepositoryEvidence,
    RepositoryIdentityError,
    canonical_remote_identity,
    derive_repository_identity,
)
from ai_workflow_engine.milestone_runner.models import MilestoneSpec, StopReason
from ai_workflow_engine.milestone_runner.scope import (
    ScopeCheck,
    ScopeGuard,
    ScopeViolation,
    path_matches,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GIT_INSPECT_SOURCE = (
    REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner" / "git_inspect.py"
)

#: The thirteen state-changing subcommands section 20 names, transcribed from the contract rather
#: than derived from the module under test, so this list and `git_inspect.py` are two independent
#: witnesses to one claim.
MUTATING_GIT_SUBCOMMANDS = (
    "checkout",
    "switch",
    "reset",
    "clean",
    "stash",
    "rebase",
    "merge",
    "cherry-pick",
    "revert",
    "fetch",
    "pull",
    "commit",
    "push",
)

REMOTE_URL = "https://github.com/example/demo-repo.git"


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """A real, disposable repository with one initial revision and a primary remote."""
    repository = tmp_path / "worktree"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "Milestone Runner Tests")
    git(repository, "remote", "add", "origin", REMOTE_URL)
    (repository / "kept.txt").write_text("kept\n", encoding="utf-8")
    git(repository, "add", "kept.txt")
    git(repository, "commit", "-m", "initial")
    return repository


def milestone(**overrides: Any) -> MilestoneSpec:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "milestone_id": "AUTO-016-M02",
        "title": "Configuration, plan loading, scope guard, read-only Git evidence",
        "objective": "Implement the run's entire input and boundary surface.",
        "depends_on": ["AUTO-016-M01"],
        "contract_sections": ["section 15 scope guard"],
        "allowed_files": [
            "src/ai_workflow_engine/milestone_runner/scope.py",
            "tests/test_milestone_runner_scope.py",
        ],
        "forbidden_files": ["agentos_workflow/**"],
        "required_symbols": ["milestone_runner.scope.ScopeGuard"],
        "explicit_exclusions": ["No state persistence."],
        "acceptance_criteria": ["`*` never crosses a path separator."],
        "focused_verification": [{"command": ["pytest", "-q"], "purpose": "scope tests"}],
        "completion_evidence": ["All focused verification commands PASS."],
    }
    payload.update(overrides)
    return MilestoneSpec.model_validate(payload)


def runner_config_payload() -> dict[str, Any]:
    """A minimal valid section 21 configuration, written out rather than imported.

    The guard only reads `allowlist`, but a `RunnerConfig` validates as a whole, so every
    required section is present. Spelling it here keeps this file self-contained: a shared
    fixture module is not part of this milestone's surface.
    """
    return {
        "schema_version": 1,
        "repository": {
            "root": "/srv/repo",
            "identity": "demo-repo--0123456789ab",
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
            "allowed_paths": [
                "src/ai_workflow_engine/milestone_runner/**",
                "tests/test_milestone_runner_*.py",
            ],
            "forbidden_paths": ["agentos_workflow/**", "self-governance.yaml"],
            "required_coverage": ["src/ai_workflow_engine/milestone_runner/scope.py"],
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


def guard() -> ScopeGuard:
    return ScopeGuard(
        allowed_paths=(
            "src/ai_workflow_engine/milestone_runner/**",
            "tests/test_milestone_runner_*.py",
        ),
        forbidden_paths=("agentos_workflow/**", "self-governance.yaml"),
    )


# --------------------------------------------------------------------------------------
# Section 6 defect P-1 -- the regression this guard exists to prevent
# --------------------------------------------------------------------------------------


class TestP1GlobDoesNotCrossPathSeparator:
    """`fnmatch`'s `*` crosses `/`; this matcher's does not (section 6 defect P-1)."""

    def test_star_does_not_match_across_a_separator(self) -> None:
        # The exact prototype case: `tests/test_*.py` silently admitted an entire subtree.
        assert path_matches("tests/test_pkg/inner.py", ["tests/test_*.py"]) is False

    def test_double_star_is_the_only_segment_spanning_construct(self) -> None:
        assert path_matches("tests/test_pkg/inner.py", ["tests/**"]) is True

    def test_star_still_matches_within_one_segment(self) -> None:
        assert path_matches("tests/test_milestone_runner_scope.py", ["tests/test_*.py"]) is True

    def test_star_does_not_span_a_middle_segment(self) -> None:
        assert path_matches("src/a/b/models.py", ["src/*/models.py"]) is False
        assert path_matches("src/a/models.py", ["src/*/models.py"]) is True

    def test_double_star_spans_any_number_of_segments(self) -> None:
        pattern = ["src/ai_workflow_engine/milestone_runner/**"]
        assert path_matches("src/ai_workflow_engine/milestone_runner/scope.py", pattern) is True
        assert path_matches("src/ai_workflow_engine/milestone_runner/a/b/c.py", pattern) is True
        assert path_matches("src/ai_workflow_engine/successor_planning/store.py", pattern) is False

    def test_a_directory_pattern_is_not_an_implicit_prefix(self) -> None:
        # A pattern names what it names; nothing is silently expanded into a subtree.
        assert path_matches("src/pkg/module.py", ["src/pkg"]) is False
        assert path_matches("src/pkg", ["src/pkg"]) is True


class TestPathMatchingNormalization:
    """Matching happens on normalized, repository-relative POSIX paths (section 15)."""

    def test_two_spellings_of_one_path_compare_equal(self) -> None:
        assert path_matches("./src/./pkg/module.py", ["src/pkg/module.py"]) is True

    def test_an_absolute_path_is_refused_rather_than_resolved(self) -> None:
        with pytest.raises(ValueError, match="repository-relative"):
            path_matches("/etc/passwd", ["**"])

    def test_a_traversal_shaped_path_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"'\.\.'"):
            path_matches("../outside.py", ["**"])

    def test_an_empty_pattern_set_matches_nothing(self) -> None:
        assert path_matches("src/pkg/module.py", []) is False


# --------------------------------------------------------------------------------------
# Section 15 -- the three independent checks
# --------------------------------------------------------------------------------------


class TestForbiddenBeatsAllowed:
    """Invariant 12: a forbidden path always loses to nothing."""

    def test_forbidden_wins_over_an_allowlist_entry_that_also_matches(self) -> None:
        both = ScopeGuard(allowed_paths=("docs/**",), forbidden_paths=("docs/TASK_QUEUE.md",))
        decision = both.evaluate(["docs/TASK_QUEUE.md"])
        assert decision.permitted is False
        assert [violation.check for violation in decision.violations] == [ScopeCheck.FORBIDDEN_PATH]

    def test_a_forbidden_path_is_reported_once_and_not_also_as_out_of_scope(self) -> None:
        both = ScopeGuard(allowed_paths=("docs/**",), forbidden_paths=("docs/TASK_QUEUE.md",))
        decision = both.evaluate(["docs/TASK_QUEUE.md"], milestone())
        assert len(decision.violations) == 1
        assert decision.violations[0].check is ScopeCheck.FORBIDDEN_PATH


class TestForbiddenPathStop:
    def test_a_forbidden_path_is_a_violation(self) -> None:
        decision = guard().evaluate(["agentos_workflow/service.py"])
        assert decision.permitted is False
        assert decision.violations[0].check is ScopeCheck.FORBIDDEN_PATH


class TestOutsideCumulativeAllowlistStop:
    def test_a_path_outside_the_cumulative_allowlist_is_a_violation(self) -> None:
        decision = guard().evaluate(["src/ai_workflow_engine/cli.py"])
        assert decision.permitted is False
        assert decision.violations[0].check is ScopeCheck.CUMULATIVE_ALLOWLIST

    def test_an_allowlisted_path_passes_when_no_milestone_is_active(self) -> None:
        decision = guard().evaluate(["src/ai_workflow_engine/milestone_runner/scope.py"])
        assert decision.permitted is True
        assert decision.violations == []


class TestOutOfMilestoneScopeStop:
    """Check 2: inside the cumulative allowlist, outside the active milestone, is a stop."""

    def test_it_is_out_of_milestone_scope_and_not_a_warning(self) -> None:
        decision = guard().evaluate(
            ["src/ai_workflow_engine/milestone_runner/state.py"], milestone()
        )
        assert decision.permitted is False
        violation = decision.violations[0]
        assert violation.check is ScopeCheck.MILESTONE_SCOPE
        assert violation.stop_reason is StopReason.OUT_OF_MILESTONE_SCOPE
        assert decision.stop_reasons == (StopReason.OUT_OF_MILESTONE_SCOPE,)

    def test_a_path_inside_the_active_milestone_passes_both_checks(self) -> None:
        decision = guard().evaluate(
            ["src/ai_workflow_engine/milestone_runner/scope.py"], milestone()
        )
        assert decision.permitted is True

    def test_every_violating_path_is_reported_not_only_the_first(self) -> None:
        decision = guard().evaluate(
            [
                "agentos_workflow/service.py",
                "src/ai_workflow_engine/cli.py",
                "src/ai_workflow_engine/milestone_runner/state.py",
            ],
            milestone(),
        )
        assert [violation.check for violation in decision.violations] == [
            ScopeCheck.FORBIDDEN_PATH,
            ScopeCheck.CUMULATIVE_ALLOWLIST,
            ScopeCheck.MILESTONE_SCOPE,
        ]


class TestCheckTwoIsMilestoneLocalAndChecksOneAndThreeAreNot:
    """Finding GOV-AUTO-11-F1: check 2 answers for the current milestone's delta, nothing else.

    A run that makes no commit until its end accumulates every milestone's work in one worktree
    diff, so evaluating check 2 against every changed path stops a later milestone with
    `OUT_OF_MILESTONE_SCOPE` for the sole reason that an earlier, completed milestone changed its
    own authorized files. `milestone_owned_paths` carries the delta the caller has durable
    checkpoint evidence for; checks 1 and 3 keep seeing everything.
    """

    STATE = "src/ai_workflow_engine/milestone_runner/state.py"
    SCOPE = "src/ai_workflow_engine/milestone_runner/scope.py"

    def test_a_completed_milestones_untouched_file_is_not_a_current_violation(self) -> None:
        decision = guard().evaluate(
            [self.STATE, self.SCOPE], milestone(), milestone_owned_paths=[self.SCOPE]
        )
        assert decision.permitted is True
        assert decision.changed_paths == [self.STATE, self.SCOPE]

    def test_a_path_the_current_milestone_did_touch_still_stops(self) -> None:
        """No milestone acquires another's paths by editing them: the delta decides, not names."""
        decision = guard().evaluate(
            [self.STATE, self.SCOPE], milestone(), milestone_owned_paths=[self.STATE, self.SCOPE]
        )
        assert decision.permitted is False
        assert [violation.path for violation in decision.violations] == [self.STATE]
        assert decision.stop_reasons == (StopReason.OUT_OF_MILESTONE_SCOPE,)

    def test_a_forbidden_path_stays_forbidden_however_narrow_the_delta_is(self) -> None:
        decision = guard().evaluate(
            ["agentos_workflow/service.py"], milestone(), milestone_owned_paths=[]
        )
        assert decision.permitted is False
        assert decision.violations[0].check is ScopeCheck.FORBIDDEN_PATH

    def test_the_cumulative_allowlist_stays_cumulative_however_narrow_the_delta_is(self) -> None:
        decision = guard().evaluate(
            ["src/ai_workflow_engine/successor_planning/models.py"],
            milestone(),
            milestone_owned_paths=[],
        )
        assert decision.permitted is False
        assert decision.violations[0].check is ScopeCheck.CUMULATIVE_ALLOWLIST

    def test_omitting_the_delta_evaluates_every_path_which_is_the_first_milestones_case(
        self,
    ) -> None:
        """With no checkpoint yet, the whole diff really is the current milestone's."""
        assert guard().evaluate([self.STATE], milestone()).permitted is False
        assert guard().evaluate([self.SCOPE], milestone()).permitted is True

    def test_an_empty_delta_is_not_the_same_as_no_delta(self) -> None:
        assert guard().evaluate([self.STATE], milestone(), milestone_owned_paths=[]).permitted
        assert not guard().evaluate([self.STATE], milestone()).permitted

    def test_the_delta_is_normalized_the_same_way_the_changed_paths_are(self) -> None:
        decision = guard().evaluate(
            [f"./{self.STATE}"], milestone(), milestone_owned_paths=[f"./{self.STATE}"]
        )
        assert decision.permitted is False
        assert decision.violations[0].path == self.STATE

    def test_the_delta_never_widens_the_milestones_allowed_files(self) -> None:
        """A path in the delta and outside `allowed_files` stops; the delta only ever narrows."""
        subject = guard()
        before = (subject.allowed_paths, subject.forbidden_paths)
        decision = subject.evaluate(
            [self.STATE], milestone(allowed_files=[self.SCOPE]), milestone_owned_paths=[self.STATE]
        )
        assert decision.permitted is False
        assert (subject.allowed_paths, subject.forbidden_paths) == before

    def test_check_two_is_skipped_entirely_when_no_milestone_is_active(self) -> None:
        assert guard().evaluate([self.STATE], None, milestone_owned_paths=[self.STATE]).permitted


class TestNoRuntimeAllowlistWidening:
    """Invariant 12: no runtime path widens the allowlist or a milestone's `allowed_files`."""

    def test_the_guard_is_frozen(self) -> None:
        subject = guard()
        with pytest.raises(FrozenInstanceError):
            subject.allowed_paths = ("**",)  # type: ignore[misc]

    def test_the_guard_holds_tuples_and_exposes_no_widening_method(self) -> None:
        subject = guard()
        assert isinstance(subject.allowed_paths, tuple)
        assert isinstance(subject.forbidden_paths, tuple)
        for name in ("add", "extend", "append", "update", "widen", "allow"):
            assert not hasattr(subject, name)

    def test_evaluating_does_not_change_the_guard(self) -> None:
        subject = guard()
        before = (subject.allowed_paths, subject.forbidden_paths)
        subject.evaluate(["src/ai_workflow_engine/cli.py"], milestone())
        assert (subject.allowed_paths, subject.forbidden_paths) == before


class TestScopeViolationRecord:
    def test_a_violation_normalizes_its_path(self) -> None:
        violation = ScopeViolation(
            path="./src/pkg/module.py", check=ScopeCheck.FORBIDDEN_PATH, detail="because"
        )
        assert violation.path == "src/pkg/module.py"

    def test_a_violation_rejects_an_unknown_field(self) -> None:
        with pytest.raises(ValueError, match="Extra inputs"):
            ScopeViolation.model_validate(
                {
                    "path": "src/pkg/module.py",
                    "check": ScopeCheck.FORBIDDEN_PATH,
                    "detail": "because",
                    "severity": "warning",
                }
            )


# --------------------------------------------------------------------------------------
# Section 20 surface 1 -- the read-only inspector
# --------------------------------------------------------------------------------------


class TestReadOnlyGitSubcommandAllowlist:
    """Section 20: the state-changing subcommands are argv shapes this module cannot build."""

    @pytest.mark.parametrize("subcommand", MUTATING_GIT_SUBCOMMANDS)
    def test_the_subcommand_is_not_on_the_read_only_allowlist(self, subcommand: str) -> None:
        assert subcommand not in READ_ONLY_GIT_SUBCOMMANDS

    @pytest.mark.parametrize("subcommand", MUTATING_GIT_SUBCOMMANDS)
    def test_the_inspector_refuses_to_run_it(self, subcommand: str, worktree: Path) -> None:
        inspector = GitReadOnlyInspector(worktree)
        with pytest.raises(GitInspectionError, match="declared read-only vectors"):
            inspector._run((subcommand, "--any-argument"))

    def test_even_a_read_only_subcommand_refuses_an_undeclared_vector(self, worktree: Path) -> None:
        # Membership in the subcommand allowlist is necessary and never sufficient: the whole
        # vector must be one this module declared.
        inspector = GitReadOnlyInspector(worktree)
        with pytest.raises(GitInspectionError, match="declared read-only vectors"):
            inspector._run(("config", "user.email", "someone@example.invalid"))

    def test_the_allowlist_holds_only_reading_subcommands(self) -> None:
        assert READ_ONLY_GIT_SUBCOMMANDS == frozenset(
            {"rev-parse", "symbolic-ref", "status", "config"}
        )


class TestNoMutatingGitSubcommandInInspector:
    """An AST proof that no state-changing subcommand string exists in `git_inspect.py`."""

    @staticmethod
    def _string_constants_and_names(tree: ast.Module) -> list[str]:
        found: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.append(node.value)
            elif isinstance(node, ast.Name):
                found.append(node.id)
            elif isinstance(node, ast.Attribute):
                found.append(node.attr)
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                found.append(node.name)
            elif isinstance(node, ast.arg):
                found.append(node.arg)
        return found

    @pytest.mark.parametrize("subcommand", MUTATING_GIT_SUBCOMMANDS)
    def test_no_string_or_identifier_in_the_module_contains_it(self, subcommand: str) -> None:
        tree = ast.parse(GIT_INSPECT_SOURCE.read_text(encoding="utf-8"))
        offenders = [
            text for text in self._string_constants_and_names(tree) if subcommand in text.casefold()
        ]
        assert offenders == [], f"{subcommand!r} appears in git_inspect.py: {offenders}"

    @pytest.mark.parametrize("subcommand", MUTATING_GIT_SUBCOMMANDS)
    def test_it_is_absent_from_the_raw_source_including_comments(self, subcommand: str) -> None:
        # The AST discards comments, so the raw text is checked too: a comment-shaped string is
        # exactly the place a forbidden operation would hide from an AST-only proof.
        source = GIT_INSPECT_SOURCE.read_text(encoding="utf-8").casefold()
        assert subcommand not in source

    def test_the_module_never_calls_a_shell(self) -> None:
        source = GIT_INSPECT_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                pytest.fail("git_inspect.py passes a `shell` keyword to a subprocess call")
        assert "os.system" not in source


class TestRepositoryIdentityDerivation:
    """Section 11 / DEC-010: one identity, derived from the remote and never from a local path."""

    def test_two_spellings_of_one_remote_yield_one_identity(self) -> None:
        https = derive_repository_identity("https://github.com/example/demo-repo.git")
        scp = derive_repository_identity("git@github.com:example/demo-repo.git")
        assert https == scp

    def test_credentials_never_participate(self) -> None:
        plain = derive_repository_identity("https://github.com/example/demo-repo.git")
        with_credentials = derive_repository_identity(
            "https://user:token@github.com/example/demo-repo.git"
        )
        assert plain == with_credentials

    def test_the_identity_has_the_dec_010_shape(self) -> None:
        identity = derive_repository_identity(REMOTE_URL)
        name, separator, digest = identity.rpartition("--")
        assert separator == "--"
        assert name == "demo-repo"
        assert len(digest) == 12
        assert set(digest) <= set("0123456789abcdef")

    def test_a_scheme_default_port_is_dropped(self) -> None:
        assert canonical_remote_identity(
            "https://github.com:443/example/demo-repo.git"
        ) == canonical_remote_identity("https://github.com/example/demo-repo.git")

    def test_a_local_path_remote_is_refused(self) -> None:
        with pytest.raises(RepositoryIdentityError):
            derive_repository_identity("/srv/git/demo-repo.git")

    def test_a_file_url_remote_is_refused(self) -> None:
        with pytest.raises(RepositoryIdentityError, match="file://"):
            derive_repository_identity("file:///srv/git/demo-repo.git")

    def test_a_worktree_with_no_primary_remote_has_no_identity(self, tmp_path: Path) -> None:
        bare = tmp_path / "no-remote"
        bare.mkdir()
        git(bare, "init", "-b", "main")
        with pytest.raises((RepositoryIdentityError, GitInspectionError)):
            GitReadOnlyInspector(bare).repository_identity()


class TestChangedPaths:
    """Section 15: untracked files count, and a rename contributes both sides."""

    def test_an_untracked_file_counts_as_a_changed_path(self, worktree: Path) -> None:
        (worktree / "new.txt").write_text("new\n", encoding="utf-8")
        assert GitReadOnlyInspector(worktree).changed_paths() == ["new.txt"]

    def test_an_untracked_file_in_a_new_directory_is_listed_individually(
        self, worktree: Path
    ) -> None:
        nested = worktree / "pkg" / "deep"
        nested.mkdir(parents=True)
        (nested / "module.py").write_text("x = 1\n", encoding="utf-8")
        assert GitReadOnlyInspector(worktree).changed_paths() == ["pkg/deep/module.py"]

    def test_a_modified_tracked_file_counts(self, worktree: Path) -> None:
        (worktree / "kept.txt").write_text("changed\n", encoding="utf-8")
        assert GitReadOnlyInspector(worktree).changed_paths() == ["kept.txt"]

    def test_a_rename_contributes_both_sides(self, worktree: Path) -> None:
        git(worktree, "mv", "kept.txt", "moved.txt")
        assert GitReadOnlyInspector(worktree).changed_paths() == ["kept.txt", "moved.txt"]

    def test_an_unchanged_worktree_reports_no_changed_path(self, worktree: Path) -> None:
        assert GitReadOnlyInspector(worktree).changed_paths() == []

    def test_changed_paths_feed_the_guard_directly(self, worktree: Path) -> None:
        (worktree / "agentos_workflow").mkdir()
        (worktree / "agentos_workflow" / "service.py").write_text("x = 1\n", encoding="utf-8")
        decision = guard().evaluate(GitReadOnlyInspector(worktree).changed_paths())
        assert decision.permitted is False
        assert decision.violations[0].check is ScopeCheck.FORBIDDEN_PATH


class TestRepositoryEvidence:
    def test_evidence_reports_the_live_worktree(self, worktree: Path) -> None:
        evidence = GitReadOnlyInspector(worktree).evidence()
        assert isinstance(evidence, RepositoryEvidence)
        assert Path(evidence.repository_root).resolve() == worktree.resolve()
        assert evidence.branch == "main"
        assert evidence.head_sha == git(worktree, "rev-parse", "HEAD")
        assert evidence.repository_identity == derive_repository_identity(REMOTE_URL)
        assert evidence.changed_paths == []

    def test_taking_evidence_changes_nothing(self, worktree: Path) -> None:
        before_head = git(worktree, "rev-parse", "HEAD")
        before_status = git(worktree, "status", "--porcelain")
        GitReadOnlyInspector(worktree).evidence()
        assert git(worktree, "rev-parse", "HEAD") == before_head
        assert git(worktree, "status", "--porcelain") == before_status

    def test_a_directory_that_is_not_a_worktree_is_reported_as_such(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        assert GitReadOnlyInspector(plain).is_worktree() is False


class TestDriftDetection:
    """Section 4 items 2-4: identity, branch and HEAD drift are three distinct typed failures."""

    def _expectations(self, worktree: Path) -> dict[str, str]:
        return {
            "expected_identity": derive_repository_identity(REMOTE_URL),
            "expected_branch": "main",
            "expected_head_sha": git(worktree, "rev-parse", "HEAD"),
        }

    def test_no_drift_when_nothing_moved(self, worktree: Path) -> None:
        inspector = GitReadOnlyInspector(worktree)
        assert inspector.detect_drift(**self._expectations(worktree)) == ()

    def test_branch_drift_is_reported_as_branch_mismatch(self, worktree: Path) -> None:
        expectations = self._expectations(worktree)
        expectations["expected_branch"] = "feature/somewhere-else"
        drifts = GitReadOnlyInspector(worktree).detect_drift(**expectations)
        assert [drift.stop_reason for drift in drifts] == [StopReason.BRANCH_MISMATCH]
        assert drifts[0].observed == "main"

    def test_head_drift_is_reported_as_head_drift(self, worktree: Path) -> None:
        expectations = self._expectations(worktree)
        expectations["expected_head_sha"] = "0" * 40
        drifts = GitReadOnlyInspector(worktree).detect_drift(**expectations)
        assert [drift.stop_reason for drift in drifts] == [StopReason.HEAD_DRIFT]

    def test_identity_drift_is_reported_as_repository_identity_mismatch(
        self, worktree: Path
    ) -> None:
        expectations = self._expectations(worktree)
        expectations["expected_identity"] = derive_repository_identity(
            "https://github.com/example/other-repo.git"
        )
        drifts = GitReadOnlyInspector(worktree).detect_drift(**expectations)
        assert [drift.stop_reason for drift in drifts] == [StopReason.REPOSITORY_IDENTITY_MISMATCH]

    def test_three_simultaneous_drifts_are_three_distinct_findings(self, worktree: Path) -> None:
        drifts = GitReadOnlyInspector(worktree).detect_drift(
            expected_identity=derive_repository_identity("https://github.com/example/other.git"),
            expected_branch="feature/somewhere-else",
            expected_head_sha="0" * 40,
        )
        assert {drift.stop_reason for drift in drifts} == {
            StopReason.REPOSITORY_IDENTITY_MISMATCH,
            StopReason.BRANCH_MISMATCH,
            StopReason.HEAD_DRIFT,
        }
        assert {drift.aspect for drift in drifts} == {
            "repository_identity",
            "branch",
            "head_sha",
        }

    def test_drift_is_observed_afresh_rather_than_remembered(self, worktree: Path) -> None:
        inspector = GitReadOnlyInspector(worktree)
        expectations = self._expectations(worktree)
        assert inspector.detect_drift(**expectations) == ()
        git(worktree, "checkout", "-b", "feature/moved")
        drifts = inspector.detect_drift(**expectations)
        assert [drift.stop_reason for drift in drifts] == [StopReason.BRANCH_MISMATCH]


class TestContractPinning:
    """Section 4 item 1: the governing contract is pinned by SHA-256."""

    def _write_contract(self, worktree: Path, body: str) -> str:
        directory = worktree / "docs" / "stage-prompts"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "AUTO-999.md").write_text(body, encoding="utf-8")
        import hashlib

        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def test_a_matching_digest_verifies(self, worktree: Path) -> None:
        digest = self._write_contract(worktree, "# AUTO-999\n")
        inspector = GitReadOnlyInspector(worktree)
        assert inspector.verify_contract_pin("docs/stage-prompts/AUTO-999.md", digest) == digest

    def test_a_changed_contract_is_refused(self, worktree: Path) -> None:
        digest = self._write_contract(worktree, "# AUTO-999\n")
        self._write_contract(worktree, "# AUTO-999 (edited)\n")
        inspector = GitReadOnlyInspector(worktree)
        with pytest.raises(ContractPinMismatch):
            inspector.verify_contract_pin("docs/stage-prompts/AUTO-999.md", digest)

    def test_a_symlinked_contract_component_is_refused(
        self, worktree: Path, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "AUTO-999.md").write_text("# elsewhere\n", encoding="utf-8")
        (worktree / "docs").mkdir(exist_ok=True)
        (worktree / "docs" / "stage-prompts").symlink_to(outside, target_is_directory=True)
        inspector = GitReadOnlyInspector(worktree)
        with pytest.raises(GitInspectionError, match="symbolic link"):
            inspector.contract_digest("docs/stage-prompts/AUTO-999.md")

    def test_an_expected_digest_of_the_wrong_shape_is_refused(self, worktree: Path) -> None:
        self._write_contract(worktree, "# AUTO-999\n")
        inspector = GitReadOnlyInspector(worktree)
        with pytest.raises(GitInspectionError, match="64 lowercase hexadecimal"):
            inspector.verify_contract_pin("docs/stage-prompts/AUTO-999.md", "not-a-digest")


class TestScopeGuardFromConfig:
    """The guard is built from the validated configuration's `allowlist` section."""

    def test_from_config_carries_both_path_sets(self) -> None:
        config = RunnerConfig.model_validate(runner_config_payload())
        subject = ScopeGuard.from_config(config)
        assert subject.allowed_paths == tuple(config.allowlist.allowed_paths)
        assert subject.forbidden_paths == tuple(config.allowlist.forbidden_paths)
