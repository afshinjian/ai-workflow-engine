"""Tests for GOV-AUTO-01's Human-gated task runner (`scripts/workflow-next.sh`,
`scripts/workflow-approve.sh`).

Every test runs against a disposable temporary Git repository built by the `sandbox` fixture; the
real repository is never committed to, never staged, and never stashed. The scripts under test are
copied into each sandbox, so `git rev-parse --show-toplevel` from the script's own location
resolves to the sandbox — which is exactly the "expected repository" property being tested.

Agent launches are intercepted with a PATH stub rather than a production flag: a test-only code
path in the script would itself be an injection surface, and stubbing PATH exercises the real
launch code end to end.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NEXT_SCRIPT = REPO_ROOT / "scripts" / "workflow-next.sh"
APPROVE_SCRIPT = REPO_ROOT / "scripts" / "workflow-approve.sh"
PROMPT_FILE = REPO_ROOT / "scripts" / "prompts" / "implement-next-task.md"
BRANCH_PREPARE_LIB = REPO_ROOT / "scripts" / "lib" / "branch_prepare.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "LC_ALL": "C",
}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
    )
    return result.stdout.strip()


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A disposable repository containing copies of both scripts and the prompt."""
    repo = tmp_path / "sandbox repo"  # deliberate space: paths with spaces must work
    (repo / "scripts" / "prompts").mkdir(parents=True)
    (repo / "scripts" / "lib").mkdir(parents=True)
    shutil.copy2(NEXT_SCRIPT, repo / "scripts" / "workflow-next.sh")
    shutil.copy2(APPROVE_SCRIPT, repo / "scripts" / "workflow-approve.sh")
    shutil.copy2(PROMPT_FILE, repo / "scripts" / "prompts" / "implement-next-task.md")
    shutil.copy2(BRANCH_PREPARE_LIB, repo / "scripts" / "lib" / "branch_prepare.sh")
    # The governance marker the runner uses to confirm it is in the expected repository.
    (repo / "self-governance.yaml").write_text("project:\n  id: sandbox\n", encoding="utf-8")
    (repo / "README.md").write_text("sandbox\n", encoding="utf-8")

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: sandbox baseline")
    return repo


def make_agent_stub(directory: Path, name: str, *, exit_code: int = 0) -> Path:
    """A fake agent CLI that records its argv and exits with `exit_code`."""
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / f"{name}.log"
    stub = directory / name
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$0" >> {str(log)!r}\n'
        f'printf "ARGC=%s\\n" "$#" >> {str(log)!r}\n'
        f'printf "PROMPT<<%s>>\\n" "$1" >> {str(log)!r}\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return log


def run_next(
    repo: Path, *args: str, stub_dir: Path | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **GIT_ENV}
    if stub_dir is not None:
        env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [str(repo / "scripts" / "workflow-next.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
        # Deliberately not the repository root: the script must resolve its own root.
        cwd=str(cwd if cwd is not None else Path(os.sep)),
    )


def run_approve(
    repo: Path, *args: str, stdin: str = "", cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "scripts" / "workflow-approve.sh"), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        cwd=str(cwd if cwd is not None else Path(os.sep)),
    )


def commit_count(repo: Path) -> int:
    return int(git(repo, "rev-list", "--count", "HEAD"))


# =============================================================================================
# workflow-next.sh
# =============================================================================================


def test_executable_bits_are_set() -> None:
    assert os.access(NEXT_SCRIPT, os.X_OK)
    assert os.access(APPROVE_SCRIPT, os.X_OK)


def test_clean_worktree_passes_preflight_and_launches_agent(sandbox: Path, tmp_path: Path) -> None:
    log = make_agent_stub(tmp_path / "stub", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 0, result.stderr
    assert "Worktree         : clean" in result.stdout
    assert "git diff --check : clean" in result.stdout
    assert "WORKFLOW_NEXT_COMPLETE agent=claude status=0" in result.stdout
    assert log.exists(), "the agent must have been launched"


def test_dirty_worktree_is_rejected(sandbox: Path, tmp_path: Path) -> None:
    (sandbox / "uncommitted.txt").write_text("work in progress\n", encoding="utf-8")
    log = make_agent_stub(tmp_path / "stub", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 4
    assert "worktree is not clean" in result.stderr
    assert not log.exists(), "no agent may be launched on a dirty worktree"


def test_dirty_worktree_from_modified_tracked_file_is_rejected(sandbox: Path) -> None:
    (sandbox / "README.md").write_text("modified\n", encoding="utf-8")
    result = run_next(sandbox, "claude")
    assert result.returncode == 4


def test_missing_prompt_file_is_rejected(sandbox: Path, tmp_path: Path) -> None:
    prompt = sandbox / "scripts" / "prompts" / "implement-next-task.md"
    prompt.unlink()
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-m", "chore: drop prompt")
    log = make_agent_stub(tmp_path / "stub", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 5
    assert "missing implementation prompt" in result.stderr
    assert not log.exists()


def test_empty_prompt_file_is_rejected(sandbox: Path) -> None:
    prompt = sandbox / "scripts" / "prompts" / "implement-next-task.md"
    prompt.write_text("", encoding="utf-8")
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-m", "chore: empty prompt")
    result = run_next(sandbox, "claude")
    assert result.returncode == 5


@pytest.mark.parametrize(
    "bad_agent", ["gemini", "CLAUDE", "claude codex", "", "--force", "; rm -rf /", "sh"]
)
def test_unsupported_agent_fails_closed(sandbox: Path, bad_agent: str) -> None:
    result = run_next(sandbox, bad_agent)
    assert result.returncode == 2
    assert "unsupported agent" in result.stderr or "exactly one agent" in result.stderr


def test_no_argument_fails_closed(sandbox: Path) -> None:
    assert run_next(sandbox).returncode == 2


def test_too_many_arguments_fail_closed(sandbox: Path) -> None:
    assert run_next(sandbox, "claude", "codex").returncode == 2


def test_claude_command_selection_is_correct(sandbox: Path, tmp_path: Path) -> None:
    log = make_agent_stub(tmp_path / "stub", "claude")
    make_agent_stub(tmp_path / "stub", "codex")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 0
    contents = log.read_text(encoding="utf-8")
    assert "ARGC=1" in contents, "the prompt must be exactly one argv element"
    assert "Standard Implementation Prompt" in contents
    assert not (tmp_path / "stub" / "codex.log").exists(), "only one agent may be launched"


def test_codex_command_selection_is_correct(sandbox: Path, tmp_path: Path) -> None:
    make_agent_stub(tmp_path / "stub", "claude")
    log = make_agent_stub(tmp_path / "stub", "codex")
    result = run_next(sandbox, "codex", stub_dir=tmp_path / "stub")
    assert result.returncode == 0
    assert "ARGC=1" in log.read_text(encoding="utf-8")
    assert not (tmp_path / "stub" / "claude.log").exists()


def test_only_one_agent_session_is_launched(sandbox: Path, tmp_path: Path) -> None:
    log = make_agent_stub(tmp_path / "stub", "claude")
    run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert log.read_text(encoding="utf-8").count("ARGC=") == 1


def test_full_prompt_content_is_supplied(sandbox: Path, tmp_path: Path) -> None:
    log = make_agent_stub(tmp_path / "stub", "claude")
    run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    delivered = log.read_text(encoding="utf-8")
    for marker in (
        "NO_AUTHORISED_NEXT_TASK",
        "READY_FOR_HUMAN_OWNER_APPROVAL",
        "Independent review is not mandatory",
    ):
        assert marker in delivered, f"prompt is missing: {marker}"


def test_agent_failure_exit_code_is_propagated(sandbox: Path, tmp_path: Path) -> None:
    make_agent_stub(tmp_path / "stub", "claude", exit_code=42)
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 42
    assert "status=42" in result.stdout


def test_paths_containing_spaces_are_handled(sandbox: Path, tmp_path: Path) -> None:
    """The sandbox fixture root deliberately contains a space."""
    assert " " in str(sandbox)
    make_agent_stub(tmp_path / "stub dir", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub dir")
    assert result.returncode == 0
    assert str(sandbox) in result.stdout


def test_works_when_invoked_from_outside_the_repository(sandbox: Path, tmp_path: Path) -> None:
    make_agent_stub(tmp_path / "stub", "claude")
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub", cwd=elsewhere)
    assert result.returncode == 0
    assert str(sandbox) in result.stdout


def test_missing_governance_marker_is_rejected(sandbox: Path) -> None:
    (sandbox / "self-governance.yaml").unlink()
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-m", "chore: drop marker")
    result = run_next(sandbox, "claude")
    assert result.returncode == 3
    assert "not the expected repository" in result.stderr


def test_no_git_mutation_occurs_during_preflight(sandbox: Path, tmp_path: Path) -> None:
    head_before = git(sandbox, "rev-parse", "HEAD")
    branch_before = git(sandbox, "rev-parse", "--abbrev-ref", "HEAD")
    stashes_before = git(sandbox, "stash", "list")
    reflog_before = git(sandbox, "reflog", "--format=%H")

    make_agent_stub(tmp_path / "stub", "claude")
    run_next(sandbox, "claude", stub_dir=tmp_path / "stub")

    assert git(sandbox, "rev-parse", "HEAD") == head_before
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert git(sandbox, "stash", "list") == stashes_before
    assert git(sandbox, "reflog", "--format=%H") == reflog_before
    assert commit_count(sandbox) == 1


def test_preflight_leaves_existing_stashes_untouched(sandbox: Path, tmp_path: Path) -> None:
    (sandbox / "README.md").write_text("stashable\n", encoding="utf-8")
    git(sandbox, "stash", "push", "-m", "precious")
    before = git(sandbox, "stash", "list")
    assert "precious" in before

    make_agent_stub(tmp_path / "stub", "claude")
    run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert git(sandbox, "stash", "list") == before


def _add_registry_governed_current_task(repo: Path, task_id: str, branch: str) -> None:
    """Commit a TASK_QUEUE.md + workflow-automation registry row naming `task_id` Current with
    the given registered `branch`, onto whatever branch the repo is currently on."""
    (repo / "docs" / "workflow-automation").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "TASK_QUEUE.md").write_text(
        f"# Task Queue\n\n## {task_id} — sandbox stage\n\nStatus: Current\n",
        encoding="utf-8",
    )
    (repo / "docs" / "workflow-automation" / "STAGE_REGISTRY.md").write_text(
        "# Registry\n\n## 4. Registry\n\n"
        "| Stage | Title | Role | State | Branch | Prompt |\n"
        "|---|---|---|---|---|---|\n"
        f"| {task_id} | sandbox stage | role | IN_PROGRESS | `{branch}` | `p.md` |\n",
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "test: add registry-governed current task")


def test_branch_precondition_blocks_launch_on_branch_mismatch(
    sandbox: Path, tmp_path: Path
) -> None:
    _add_registry_governed_current_task(sandbox, "AUTO-002", "feature/auto-002")
    log = make_agent_stub(tmp_path / "stub", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 8
    assert "AUTO-002" in result.stderr
    assert "feature/auto-002" in result.stderr
    assert not log.exists(), "no agent may be launched when the branch precondition fails"


def test_branch_precondition_passes_when_branch_matches(sandbox: Path, tmp_path: Path) -> None:
    git(sandbox, "checkout", "-b", "feature/auto-002")
    _add_registry_governed_current_task(sandbox, "AUTO-002", "feature/auto-002")
    log = make_agent_stub(tmp_path / "stub", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 0, result.stderr
    assert "Branch precondition for AUTO-002 : satisfied" in result.stdout
    assert log.exists()


def test_branch_precondition_skipped_for_task_without_registry_row(
    sandbox: Path, tmp_path: Path
) -> None:
    _add_registry_governed_current_task(sandbox, "GOV-3", "")
    # A task with no registered branch (the row above still has an empty Branch cell) must never
    # block launch on the default branch.
    log = make_agent_stub(tmp_path / "stub", "claude")
    result = run_next(sandbox, "claude", stub_dir=tmp_path / "stub")
    assert result.returncode == 0, result.stderr
    assert log.exists()


def test_script_contains_no_eval(sandbox: Path) -> None:
    for script in (NEXT_SCRIPT, APPROVE_SCRIPT):
        body = script.read_text(encoding="utf-8")
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith("eval "), f"{script.name} uses eval: {line}"


def test_scripts_never_push_merge_or_mutate_stashes() -> None:
    """The forbidden Git verbs must be absent from both scripts' executable lines.

    Matched with a regex that tolerates the `-C <path>` the scripts always pass, because a naive
    substring check for "git stash" would never fire against `git -C "$repo_root" stash push` and
    would give false confidence. Read-only `stash list` is explicitly permitted; every mutating
    stash subcommand is not.
    """
    mutating = re.compile(
        r"\bgit\b(?:\s+-C\s+\S+|\s+--\S+)*\s+"
        r"(push|merge|rebase|reset|checkout|switch|cherry-pick|revert|tag|clone|fetch|pull)\b"
    )
    stash_mutation = re.compile(
        r"\bgit\b(?:\s+-C\s+\S+|\s+--\S+)*\s+stash\s+(push|pop|drop|apply|clear|save|create|store)\b"
    )
    dangerous_flags = re.compile(r"--(force|amend|hard)\b")

    for script in (NEXT_SCRIPT, APPROVE_SCRIPT):
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert not mutating.search(stripped), f"{script.name}:{number} mutates Git: {line}"
            assert not stash_mutation.search(
                stripped
            ), f"{script.name}:{number} mutates stashes: {line}"
            assert not dangerous_flags.search(
                stripped
            ), f"{script.name}:{number} uses a dangerous flag: {line}"


def test_forbidden_verb_regex_actually_detects_violations() -> None:
    """Guard the guard: the patterns above must fire on the shapes the scripts actually use."""
    mutating = re.compile(
        r"\bgit\b(?:\s+-C\s+\S+|\s+--\S+)*\s+"
        r"(push|merge|rebase|reset|checkout|switch|cherry-pick|revert|tag|clone|fetch|pull)\b"
    )
    stash_mutation = re.compile(
        r"\bgit\b(?:\s+-C\s+\S+|\s+--\S+)*\s+stash\s+(push|pop|drop|apply|clear|save|create|store)\b"
    )
    assert mutating.search('git -C "$repo_root" push origin main')
    assert mutating.search("git merge feature")
    assert stash_mutation.search('git -C "$repo_root" stash push -m x')
    assert stash_mutation.search("git stash pop")
    # Read-only forms must NOT trip the guard.
    assert not stash_mutation.search('git -C "$repo_root" stash list')
    assert not mutating.search('git -C "$repo_root" status --porcelain')


# =============================================================================================
# workflow-approve.sh
# =============================================================================================


def dirty(sandbox: Path, name: str = "change.txt", content: str = "new content\n") -> None:
    (sandbox / name).write_text(content, encoding="utf-8")


def test_clean_worktree_with_no_changes_is_rejected(sandbox: Path) -> None:
    result = run_approve(sandbox, stdin="APPROVE\n")
    assert result.returncode == 4
    assert "nothing to approve or commit" in result.stderr
    assert commit_count(sandbox) == 1


@pytest.mark.parametrize("answer", ["approve", "Approve", "yes", "y", "APPROVED", "", "APPROVE "])
def test_approval_other_than_exact_token_is_rejected(sandbox: Path, answer: str) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", "feat(x): add a thing", stdin=f"{answer}\n")
    assert result.returncode == 7
    assert "Approval not granted" in result.stdout
    assert commit_count(sandbox) == 1
    assert (sandbox / "change.txt").exists(), "working-tree content must survive a decline"


def test_second_confirmation_is_required(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", "feat(x): add a thing", stdin="APPROVE\nno\n")
    assert result.returncode == 7
    assert "Commit declined" in result.stdout
    assert commit_count(sandbox) == 1
    assert not git(sandbox, "diff", "--cached", "--name-only"), "nothing may remain staged"


@pytest.mark.parametrize(
    "message",
    ["", "   ", "fixed stuff", "WIP", "feat: x", "update", "chore", "feat(x) missing colon"],
)
def test_invalid_commit_messages_are_rejected(sandbox: Path, message: str) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, stdin=f"APPROVE\n{message}\n")
    assert result.returncode == 8
    assert commit_count(sandbox) == 1


def test_valid_conventional_commit_message_is_accepted(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", "feat(runner): add the thing", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0, result.stderr
    assert git(sandbox, "log", "-1", "--format=%s") == "feat(runner): add the thing"


def test_staged_file_list_matches_the_displayed_list(sandbox: Path) -> None:
    dirty(sandbox, "one.txt")
    dirty(sandbox, "two.txt")
    (sandbox / "README.md").write_text("modified\n", encoding="utf-8")
    result = run_approve(sandbox, "-m", "feat(x): stage exactly these", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0, result.stderr

    committed = set(git(sandbox, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert committed == {"one.txt", "two.txt", "README.md"}
    for name in committed:
        assert name in result.stdout, "every committed file must have been displayed"


def test_commit_creates_exactly_one_commit(sandbox: Path) -> None:
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", "feat(x): exactly one", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    assert commit_count(sandbox) == before + 1


def test_successful_commit_leaves_a_clean_worktree(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", "feat(x): leaves clean tree", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    assert git(sandbox, "status", "--porcelain") == ""
    assert "COMMIT_COMPLETE_READY_FOR_NEXT_TASK" in result.stdout


def test_commit_reports_hash_message_files_and_status(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", "feat(x): report everything", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    assert git(sandbox, "rev-parse", "HEAD") in result.stdout
    assert "feat(x): report everything" in result.stdout
    assert "change.txt" in result.stdout
    assert "Final Git status:" in result.stdout


def test_no_push_or_merge_occurs(sandbox: Path, tmp_path: Path) -> None:
    """A remote is configured; the script must never contact it."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(sandbox, "remote", "add", "origin", str(origin))
    dirty(sandbox)

    result = run_approve(sandbox, "-m", "feat(x): never pushes", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    remote_refs = subprocess.run(
        ["git", "-C", str(origin), "for-each-ref"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert remote_refs == "", "nothing may have been pushed to the remote"


def test_branch_is_never_changed(sandbox: Path) -> None:
    git(sandbox, "branch", "other")
    before = git(sandbox, "rev-parse", "--abbrev-ref", "HEAD")
    dirty(sandbox)
    run_approve(sandbox, "-m", "feat(x): stays on branch", stdin="APPROVE\nAPPROVE\n")
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD") == before


def test_stashes_remain_unchanged(sandbox: Path) -> None:
    (sandbox / "README.md").write_text("stash me\n", encoding="utf-8")
    git(sandbox, "stash", "push", "-m", "precious")
    before = git(sandbox, "stash", "list")

    dirty(sandbox)
    result = run_approve(sandbox, "-m", "feat(x): leaves stashes alone", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    assert git(sandbox, "stash", "list") == before
    assert "precious" in git(sandbox, "stash", "list")


def test_unresolved_conflicts_are_rejected(sandbox: Path) -> None:
    git(sandbox, "checkout", "-b", "feature")
    (sandbox / "conflict.txt").write_text("feature side\n", encoding="utf-8")
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-m", "feat: feature side")
    git(sandbox, "checkout", "main")
    (sandbox / "conflict.txt").write_text("main side\n", encoding="utf-8")
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-m", "feat: main side")
    merge = subprocess.run(
        ["git", "-C", str(sandbox), "merge", "feature"],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
    )
    assert merge.returncode != 0, "the fixture must actually produce a conflict"

    result = run_approve(sandbox, "-m", "feat(x): should not commit", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 6
    assert "conflict" in result.stderr.lower()


def test_failure_after_staging_unstages_without_discarding_working_tree(sandbox: Path) -> None:
    """A rejecting pre-commit hook fails the commit *after* staging has already happened.

    This is the exact window the script's EXIT trap exists for: the index must be restored, but
    no working-tree content may be touched. A read-only `.git` was rejected as the trigger
    because `git add` would fail first, never reaching the post-staging path under test.
    """
    hook = sandbox / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    dirty(sandbox, "precious.txt", "irreplaceable content\n")
    result = run_approve(sandbox, "-m", "feat(x): will fail", stdin="APPROVE\nAPPROVE\n")

    assert result.returncode != 0
    # The commit did not happen...
    assert commit_count(sandbox) == 1
    # ...the index was restored by the trap...
    assert git(sandbox, "diff", "--cached", "--name-only") == ""
    # ...and the working-tree content is completely intact.
    assert (sandbox / "precious.txt").read_text(encoding="utf-8") == "irreplaceable content\n"
    assert "Working-tree content is NOT modified" in result.stderr


def test_untracked_files_are_included_and_displayed(sandbox: Path) -> None:
    (sandbox / "brand_new.txt").write_text("new file\n", encoding="utf-8")
    result = run_approve(sandbox, "-m", "feat(x): include untracked", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    assert "brand_new.txt" in result.stdout
    assert "brand_new.txt" in git(sandbox, "show", "--name-only", "--format=", "HEAD")


def test_paths_with_spaces_are_committed_correctly(sandbox: Path) -> None:
    (sandbox / "a file with spaces.txt").write_text("x\n", encoding="utf-8")
    result = run_approve(sandbox, "-m", "feat(x): handles spaces", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 0
    assert "a file with spaces.txt" in git(sandbox, "show", "--name-only", "--format=", "HEAD")
    assert git(sandbox, "status", "--porcelain") == ""


def test_approve_works_when_invoked_from_outside_the_repository(
    sandbox: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    dirty(sandbox)
    result = run_approve(
        sandbox, "-m", "feat(x): resolves own root", stdin="APPROVE\nAPPROVE\n", cwd=elsewhere
    )
    assert result.returncode == 0
    assert commit_count(sandbox) == 2


def test_unrecognised_argument_fails_closed(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "--push", stdin="APPROVE\nAPPROVE\n")
    assert result.returncode == 2
    assert commit_count(sandbox) == 1
