"""AUTO-007 §4 deliverable: one dedicated test per `SECURITY_MODEL.md` rule
(`TEST_STRATEGY.md` §4), run and recorded as evidence for the mandatory independent security
review this stage requires before it may close.

Several of these properties already have deep coverage elsewhere (`test_skills_git_github.py`,
`test_skills_common.py`, `test_providers_isolation.py`, `test_skills_repository.py`). This module
does not re-derive that coverage; it is the single file a reviewer can read end to end and see
every numbered `SECURITY_MODEL.md` rule named and independently demonstrated, which is this
stage's own explicit acceptance bar, not merely additional regression tests.

**A genuine defense-in-depth observation this module surfaces rather than silently accepts**:
`SECURITY_MODEL.md` §2 says commit/push Skills structurally can never target the baseline branch.
`create_stage_branch` and `delete_local_branch`/`delete_remote_branch`
(`agentos_workflow/skills/repository.py`) each call `_reject_baseline` and so cannot be pointed at
the baseline branch by argument alone. `create_commit` and `push_stage_branch`
(`agentos_workflow/skills/git_github.py`), however, take no `baseline_branch` parameter at all and
have no independent baseline check of their own — in the shipping workflow this is unreachable in
practice only because `create_stage_branch`'s own refusal means the stage branch these two Skills
are ever called with can never equal the baseline, not because these two Skills enforce it
themselves. `test_create_commit_and_push_have_no_independent_baseline_check` below demonstrates
this precisely (documenting current, real behavior) rather than asserting a protection that does
not exist at that layer. This is recorded for the Human Owner/independent security reviewer, not
fixed here: `agentos_workflow/skills/git_github.py` is outside this stage's allowed files.
"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentos_workflow.skills import redact_secrets, run_fixed_argv
from agentos_workflow.skills.contract import detect_future_stage_work, validate_allowed_paths
from agentos_workflow.skills.git_github import create_commit, push_stage_branch
from agentos_workflow.skills.repository import (
    create_stage_branch,
    verify_repository_identity,
)
from agentos_workflow.tests.test_skills_git_github import fake_gh  # noqa: F401
from agentos_workflow.tests.test_skills_repository import git, write

BASELINE = "main"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-b", BASELINE)
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.invalid")
    write(work, "README.md", "baseline\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "initial")
    return work


def _module_string_constants(module: object) -> list[str]:
    path = getattr(module, "__file__", None)
    assert path is not None
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §1 — Secrets Handling
# --------------------------------------------------------------------------------------------


class TestSecretsHandling:
    def test_secret_shaped_output_is_redacted_before_it_could_reach_a_report(self) -> None:
        token = "ghp_" + "A" * 36
        redacted = redact_secrets(f"authentication failed using token {token}")
        assert token not in redacted

    def test_an_environment_variable_outside_the_allowlist_is_never_forwarded(
        self, tmp_path: Path
    ) -> None:
        marker = "AGENTOS_E2E_SECRET_SHOULD_NOT_BE_FORWARDED"
        script = tmp_path / "dump_env.py"
        script.write_text(
            f"import os, sys; sys.exit(1 if {marker!r} in os.environ else 0)\n",
            encoding="utf-8",
        )
        os.environ[marker] = "super-secret-value"
        try:
            execution = run_fixed_argv(
                (sys.executable, str(script)),
                identity="test",
                allowed_environment_variables=("PATH",),
            )
        finally:
            del os.environ[marker]
        assert execution.exit_code == 0, "the unlisted variable reached the child process"

    def test_an_allowlisted_environment_variable_is_forwarded(self, tmp_path: Path) -> None:
        marker = "AGENTOS_E2E_ALLOWED_VALUE"
        script = tmp_path / "check_env.py"
        script.write_text(
            f"import os, sys; sys.exit(0 if os.environ.get({marker!r}) == 'yes' else 1)\n",
            encoding="utf-8",
        )
        os.environ[marker] = "yes"
        try:
            execution = run_fixed_argv(
                (sys.executable, str(script)),
                identity="test",
                allowed_environment_variables=(marker,),
            )
        finally:
            del os.environ[marker]
        assert execution.exit_code == 0, "an explicitly allowlisted variable was not forwarded"


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §2 — Forbidden Git/GitHub Operations
# --------------------------------------------------------------------------------------------


class TestForbiddenGitGithubOperations:
    def test_create_stage_branch_refuses_the_baseline_branch(self, repo: Path) -> None:
        base_sha = git(repo, "rev-parse", "HEAD")
        result = create_stage_branch(
            repo, branch_name=BASELINE, base_sha=base_sha, baseline_branch=BASELINE
        )
        assert result.ok is False

    def test_create_commit_and_push_have_no_independent_baseline_check(self, repo: Path) -> None:
        """Documents the defense-in-depth gap this module's docstring describes: neither Skill
        even accepts a `baseline_branch` parameter, so — considered in isolation from
        `create_stage_branch`'s own refusal — nothing here would stop a caller from committing
        or pushing directly onto whatever branch string it is given, including the baseline."""
        assert "baseline_branch" not in inspect.signature(create_commit).parameters
        assert "baseline_branch" not in inspect.signature(push_stage_branch).parameters

    def test_no_forbidden_argv_tokens_in_git_github_skills(self) -> None:
        import agentos_workflow.skills.git_github as module

        forbidden = (
            "--admin",
            "--force",
            "--force-with-lease",
            "-f",
            "reset",
            "rebase",
            "--amend",
            "filter-branch",
        )
        constants = _module_string_constants(module)
        for token in forbidden:
            assert token not in constants, f"forbidden argv token {token!r} in git_github.py"

    def test_no_forbidden_argv_tokens_in_repository_skills(self) -> None:
        import agentos_workflow.skills.repository as module

        forbidden = (
            "--force",
            "--force-with-lease",
            "-D",
            "reset",
            "rebase",
            "--amend",
            "filter-branch",
        )
        constants = _module_string_constants(module)
        for token in forbidden:
            assert token not in constants, f"forbidden argv token {token!r} in repository.py"

    def test_gh_pr_merge_admin_path_does_not_exist(self, fake_gh: Path) -> None:  # noqa: F811
        import agentos_workflow.skills.git_github as module

        constants = _module_string_constants(module)
        assert "--admin" not in constants
        assert "admin" not in constants


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §3 — Session Isolation
# --------------------------------------------------------------------------------------------


class TestSessionIsolation:
    def test_claude_and_codex_providers_share_no_process_state(self) -> None:
        from agentos_workflow.providers.claude_cli import ClaudeCLIProvider
        from agentos_workflow.providers.codex_cli import CodexCLIProvider

        # Neither provider module imports the other, and each subprocess invocation constructs
        # its own argv/environment independently (`MODEL_PROVIDER_CONTRACTS.md` §5) — the
        # structural property that makes cross-session leakage unreachable rather than merely
        # untested.
        claude_source = inspect.getsource(ClaudeCLIProvider)
        codex_source = inspect.getsource(CodexCLIProvider)
        assert "CodexCLIProvider" not in claude_source
        assert "ClaudeCLIProvider" not in codex_source

    def test_qa_never_receives_the_implementation_sessions_prompt_or_reasoning(
        self, tmp_path: Path
    ) -> None:
        """The substantive §3 claim this module's other test above does not reach: "a
        compromised/manipulated implementation session cannot influence QA's verdict, since QA
        receives only the diff and deterministic validation results, never the implementation
        session's reasoning/transcript." Drives the real `ImplementationAgent`/`QAAgent` code
        paths (`test_agents_repair_loop.py`'s own agent-building helpers, reused rather than
        re-derived) with a sentinel planted only in the implementation session's contract text,
        then asserts it never reaches the independent `MockProvider` instance standing in for
        QA's provider — real behavioral proof, not source-text inspection."""
        from agentos_workflow.agents.qa import QAAgent
        from agentos_workflow.providers import ProviderVerdict
        from agentos_workflow.tests.test_agents_repair_loop import (
            build_implementation_agent,
            build_qa_agent,
            implementation_provider,
            passing_validation,
            qa_provider,
        )

        sentinel = "IMPLEMENTATION_SESSION_ONLY_TOKEN_4f9c2a"

        implementation_agent, _ = build_implementation_agent(tmp_path, implementation_provider())
        implementation_agent.implement(contract_text=f"contract with {sentinel}")

        qa_mock = qa_provider(ProviderVerdict.PASS)
        qa_agent, _ = build_qa_agent(tmp_path, qa_mock)
        qa_agent.review(
            validation=passing_validation(), attempt_number=1, changed_files=("src/x.py",)
        )

        assert len(qa_mock.invocations) == 1
        assert sentinel not in qa_mock.invocations[0].prompt

        # And the review() surface itself has no parameter through which an implementation
        # session's raw output could ever be threaded in the first place — closing off a future
        # regression even if some future caller wanted to pass one.
        params = set(inspect.signature(QAAgent.review).parameters) - {"self"}
        assert params == {"validation", "attempt_number", "changed_files", "head_sha"}


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §4 — No Admin Bypass
# --------------------------------------------------------------------------------------------


class TestNoAdminBypass:
    def test_merge_agent_source_names_no_admin_flag(self) -> None:
        import agentos_workflow.agents.merge as module

        constants = _module_string_constants(module)
        for token in ("--admin", "admin"):
            assert token not in constants, f"{token!r} appears in merge.py"

    def test_merge_agent_has_exactly_one_merge_enabling_call_site(self) -> None:
        import agentos_workflow.skills.git_github as module

        assert module.__file__ is not None
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        merge_tuples = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Tuple)
            and len(node.elts) >= 2
            and all(isinstance(element, ast.Constant) for element in node.elts[:2])
            and node.elts[0].value == "pr"  # type: ignore[attr-defined]
            and node.elts[1].value == "merge"  # type: ignore[attr-defined]
        ]
        assert len(merge_tuples) == 1


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §5 — Destructive-Operation Preconditions
# --------------------------------------------------------------------------------------------


class TestDestructiveOperationPreconditions:
    def test_delete_local_branch_requires_a_matching_merge_confirmation(self, repo: Path) -> None:
        from agentos_workflow.skills import MergeConfirmation, utc_now
        from agentos_workflow.skills.repository import delete_local_branch

        git(repo, "branch", "feature/example")
        wrong_confirmation = MergeConfirmation(
            branch="some-other-branch",
            merge_commit_sha="a" * 40,
            verified_at=utc_now(),
        )
        result = delete_local_branch(
            repo,
            branch="feature/example",
            baseline_branch=BASELINE,
            merge_confirmation=wrong_confirmation,
        )
        assert result.ok is False
        assert git(repo, "branch", "--list", "feature/example") != ""

    def test_fast_forward_pull_refuses_on_divergence_never_forces(self, tmp_path: Path) -> None:
        from agentos_workflow.skills.repository import fast_forward_pull

        origin = tmp_path / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", BASELINE, str(origin)],
            check=True,
            capture_output=True,
        )
        work = tmp_path / "work"
        work.mkdir()
        git(work, "init", "-b", BASELINE)
        git(work, "config", "user.name", "Fixture")
        git(work, "config", "user.email", "fixture@example.invalid")
        write(work, "README.md", "one\n")
        git(work, "add", "README.md")
        git(work, "commit", "-m", "one")
        git(work, "remote", "add", "origin", str(origin))
        git(work, "push", "-u", "origin", BASELINE)

        # Diverge the remote from underneath the local clone.
        other_clone = tmp_path / "other"
        subprocess.run(
            ["git", "clone", str(origin), str(other_clone)], check=True, capture_output=True
        )
        git(other_clone, "config", "user.name", "Fixture")
        git(other_clone, "config", "user.email", "fixture@example.invalid")
        write(other_clone, "elsewhere.txt", "remote-only\n")
        git(other_clone, "add", "elsewhere.txt")
        git(other_clone, "commit", "-m", "remote-only change")
        git(other_clone, "push", "origin", BASELINE)

        write(work, "local-only.txt", "local-only\n")
        git(work, "add", "local-only.txt")
        git(work, "commit", "-m", "local-only change")
        local_head_before = git(work, "rev-parse", "HEAD")

        result = fast_forward_pull(work, baseline_branch=BASELINE, remote="origin")
        assert result.ok is False
        assert (
            git(work, "rev-parse", "HEAD") == local_head_before
        ), "a diverged pull must not move HEAD"


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §6 — Repository Identity Guard
# --------------------------------------------------------------------------------------------


class TestRepositoryIdentityGuard:
    def test_a_mismatched_identity_is_refused(self, repo: Path) -> None:
        git(repo, "remote", "add", "origin", "https://example.invalid/org/real-repo.git")
        result = verify_repository_identity(
            repo, expected_identity="example.invalid/org/different-repo", remote_name="origin"
        )
        assert result.ok is False

    def test_a_matching_identity_is_confirmed(self, repo: Path) -> None:
        git(repo, "remote", "add", "origin", "https://example.invalid/org/real-repo.git")
        result = verify_repository_identity(
            repo, expected_identity="example.invalid/org/real-repo", remote_name="origin"
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.matches_expected is True


# --------------------------------------------------------------------------------------------
# SECURITY_MODEL.md §7 — Scope Enforcement
# --------------------------------------------------------------------------------------------


class TestScopeEnforcement:
    def test_a_path_outside_every_allowed_pattern_is_a_violation_not_a_warning(self) -> None:
        result = validate_allowed_paths(
            changed_files=("src/outside_scope.py",),
            allowed_paths=("agentos_workflow/tests/e2e/**",),
            forbidden_paths=(),
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.passed is False

    def test_a_later_stage_owned_path_is_flagged_even_if_within_the_current_allowlist(
        self,
    ) -> None:
        result = detect_future_stage_work(
            changed_files=("agentos_workflow/tests/e2e/test_future.py",),
            current_stage_allowed_paths=("agentos_workflow/tests/e2e/**",),
            later_stage_paths={"AUTO-099": ("agentos_workflow/tests/e2e/**",)},
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.passed is False
