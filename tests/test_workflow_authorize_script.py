"""Focused GOV-AUTO-02 tests using disposable Git repositories."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORIZE_SCRIPT = REPO_ROOT / "scripts" / "workflow-authorize.sh"
BRANCH_PREPARE_LIB = REPO_ROOT / "scripts" / "lib" / "branch_prepare.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "LC_ALL": "C",
}


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
    )
    return result.stdout.strip()


def checksum_row(path: Path) -> str:
    data = path.read_bytes()
    return (
        f"| handover/PROJECT_HANDOVER.md | {len(data)} | 2026-07-28 | "
        f"{hashlib.sha256(data).hexdigest()} |"
    )


@pytest.fixture
def authorization_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "authorization repo"
    (repo / "scripts" / "lib").mkdir(parents=True)
    (repo / "docs" / "workflow-automation").mkdir(parents=True)
    (repo / "docs" / "agentos-dashboard").mkdir(parents=True)
    (repo / "handover").mkdir()
    (repo / "bin").mkdir()
    shutil.copy2(AUTHORIZE_SCRIPT, repo / "scripts" / "workflow-authorize.sh")
    shutil.copy2(BRANCH_PREPARE_LIB, repo / "scripts" / "lib" / "branch_prepare.sh")

    (repo / "scripts" / "workflow-next.sh").write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$1" > "${WORKFLOW_RUNNER_LOG:?}"\n'
        'exit "${WORKFLOW_RUNNER_STATUS:-0}"\n',
        encoding="utf-8",
    )
    (repo / "scripts" / "workflow-next.sh").chmod(0o755)

    (repo / "self-governance.yaml").write_text(
        "project:\n"
        "  id: ai-workflow-engine\n"
        "  default_branch: main\n"
        "  conda_environment: ai-workflow-engine\n",
        encoding="utf-8",
    )
    (repo / "docs" / "TASK_QUEUE.md").write_text(
        "# Task Queue\n\n"
        "## AUTO-001 — predecessor\n\nStatus: Done\n\n"
        "## AUTO-002 — planned work\n\nStatus: Planned\n\n"
        "## AUTO-003 — later work\n\nStatus: Planned\n\n"
        "## GOV-3 — ordinary work\n\nStatus: Planned\n\n"
        "## GOV-4 — finished work\n\nStatus: Done\n\n"
        "## GOV-5 — blocked work\n\nStatus: Planned\n\nBlocked on an owner decision.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "current_task.md").write_text(
        "# Current Task\n\nNo task is active.\n", encoding="utf-8"
    )
    (repo / "docs" / "remaining_tasks.md").write_text(
        "# Remaining\n\n"
        "| Task | Title | Status |\n|---|---|---|\n"
        "| AUTO-002 | planned work | Planned |\n"
        "| AUTO-003 | later work | Planned |\n"
        "| GOV-3 | ordinary work | Planned |\n"
        "| GOV-5 | blocked work | Planned |\n",
        encoding="utf-8",
    )
    (repo / "docs" / "PROJECT_STATE.md").write_text(
        "# Project State\n\nCurrent Version: 1.0.0\n", encoding="utf-8"
    )
    (repo / "docs" / "DECISION_LOG.md").write_text(
        "# Decision Log\n\nIntro.\n\n## 2026-07-01 — baseline\n\nBaseline.\n", encoding="utf-8"
    )
    (repo / "docs" / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Baseline.\n", encoding="utf-8"
    )
    (repo / "docs" / "workflow-automation" / "STAGE_REGISTRY.md").write_text(
        "# Registry\n\n"
        "## 4. Registry\n\n"
        "| Stage | Title | Role | State | Branch | Prompt |\n"
        "|---|---|---|---|---|---|\n"
        "| AUTO-001 | predecessor | role | COMPLETE | `feature/auto-001` | `one.md` |\n"
        "| AUTO-002 | planned work | role | NOT_STARTED | `feature/auto-002` | `two.md` |\n"
        "| AUTO-003 | later work | role | NOT_STARTED | `feature/auto-003` | `three.md` |\n\n"
        "## 5. Authorization Log (append-only)\n\n"
        "| Date | Stage | Authorization record | Recorded by |\n"
        "|---|---|---|---|\n"
        "| 2026-07-01 | AUTO-001 | old | Human Owner |\n\n"
        "## 6. Decisions\n",
        encoding="utf-8",
    )
    (repo / "docs" / "workflow-automation" / "OPEN_QUESTIONS.md").write_text(
        "# Open Questions\n\nNone.\n", encoding="utf-8"
    )
    (repo / "docs" / "workflow-automation" / "CHANGELOG.md").write_text(
        "# Program changelog\n", encoding="utf-8"
    )
    (repo / "docs" / "agentos-dashboard" / "STAGE_REGISTRY.md").write_text(
        "# Dashboard registry\n", encoding="utf-8"
    )
    (repo / "handover" / "PROJECT_HANDOVER.md").write_text(
        "# Project Handover\n\nNo task is active.\n", encoding="utf-8"
    )
    handover = repo / "handover" / "PROJECT_HANDOVER.md"
    (repo / "handover" / "PROJECT_CHECKSUM.md").write_text(
        "# Checksum\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"{checksum_row(handover)}\n",
        encoding="utf-8",
    )

    # The production script uses the configured conda invocation. This PATH stub represents the
    # three validators and can deliberately reject the post-transition state.
    (repo / "bin" / "conda").write_text(
        "#!/usr/bin/env bash\n"
        'queue="${WORKFLOW_TEST_REPO:?}/docs/TASK_QUEUE.md"\n'
        'if [ "${WORKFLOW_VALIDATION_FAIL_AFTER:-0}" = 1 ] && '
        'grep -q "Status: Current" "$queue"; then exit 81; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    (repo / "bin" / "conda").chmod(0o755)

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: baseline")
    return repo


def run_authorize(
    repo: Path,
    *args: str,
    stdin: str = "",
    extra_env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        **GIT_ENV,
        "PATH": f"{repo / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "WORKFLOW_TEST_REPO": str(repo),
        "WORKFLOW_AUTHORIZE_DATE": "2026-07-28",
        "WORKFLOW_RUNNER_LOG": str(repo / "runner.log"),
        **(extra_env or {}),
    }
    return subprocess.run(
        [str(repo / "scripts" / "workflow-authorize.sh"), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd or repo.parent),
        env=env,
    )


def commit_count(repo: Path) -> int:
    return int(git(repo, "rev-list", "--count", "HEAD"))


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("AUTO-002", "claude", "extra"),
        ("AUTO-002", "gemini"),
        ("auto-002",),
    ],
)
def test_invalid_usage_fails_closed(authorization_repo: Path, args: tuple[str, ...]) -> None:
    result = run_authorize(authorization_repo, *args)
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    assert commit_count(authorization_repo) == 1


@pytest.mark.parametrize("agent", [None, "claude", "codex"])
def test_valid_task_modes(authorization_repo: Path, agent: str | None) -> None:
    args = ("AUTO-002",) if agent is None else ("AUTO-002", agent)
    result = run_authorize(authorization_repo, *args, stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 0, result.stderr
    assert commit_count(authorization_repo) == 2
    if agent is None:
        assert not (authorization_repo / "runner.log").exists()
        assert "scripts/workflow-next.sh claude" in result.stdout
    else:
        assert (authorization_repo / "runner.log").read_text().strip() == agent


def test_works_outside_repository(authorization_repo: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = run_authorize(
        authorization_repo,
        "AUTO-002",
        stdin="AUTHORIZE\nAUTHORIZE\n",
        cwd=elsewhere,
    )
    assert result.returncode == 0, result.stderr


def test_dirty_worktree_is_rejected(authorization_repo: Path) -> None:
    (authorization_repo / "dirty.txt").write_text("dirty\n")
    result = run_authorize(authorization_repo, "AUTO-002")
    assert result.returncode == 4
    assert commit_count(authorization_repo) == 1


def test_unresolved_conflict_is_rejected(authorization_repo: Path) -> None:
    git(authorization_repo, "checkout", "-b", "conflict-side")
    (authorization_repo / "conflict").write_text("side\n")
    git(authorization_repo, "add", "conflict")
    git(authorization_repo, "commit", "-m", "test: side")
    git(authorization_repo, "checkout", "main")
    (authorization_repo / "conflict").write_text("main\n")
    git(authorization_repo, "add", "conflict")
    git(authorization_repo, "commit", "-m", "test: main")
    git(authorization_repo, "merge", "conflict-side", check=False)
    result = run_authorize(authorization_repo, "AUTO-002")
    assert result.returncode == 4
    assert "clean worktree" in result.stderr or "conflict" in result.stderr


def test_existing_current_task_is_rejected(authorization_repo: Path) -> None:
    queue = authorization_repo / "docs" / "TASK_QUEUE.md"
    queue.write_text(queue.read_text().replace("Status: Planned", "Status: Current", 1))
    git(authorization_repo, "add", "docs/TASK_QUEUE.md")
    git(authorization_repo, "commit", "-m", "test: active task")
    result = run_authorize(authorization_repo, "GOV-3")
    assert result.returncode == 6
    assert "ACTIVE_TASK_MUST_BE_CLOSED_FIRST" in result.stderr


@pytest.mark.parametrize(
    ("task", "message"),
    [("UNKNOWN-99", "unknown task"), ("GOV-4", "already Done"), ("GOV-5", "blocked")],
)
def test_invalid_task_state_is_rejected(authorization_repo: Path, task: str, message: str) -> None:
    result = run_authorize(authorization_repo, task)
    assert result.returncode != 0
    assert message.lower() in result.stderr.lower()
    assert commit_count(authorization_repo) == 1


def test_unmet_predecessor_is_rejected(authorization_repo: Path) -> None:
    result = run_authorize(authorization_repo, "AUTO-003")
    assert result.returncode == 6
    assert "AUTO-002 is not COMPLETE" in result.stderr


def test_unresolved_owner_decision_is_rejected(authorization_repo: Path) -> None:
    questions = authorization_repo / "docs" / "workflow-automation" / "OPEN_QUESTIONS.md"
    questions.write_text(
        "# Open Questions\n\nOD-9 must be resolved before AUTO-002 authorization.\n"
    )
    git(authorization_repo, "add", str(questions.relative_to(authorization_repo)))
    git(authorization_repo, "commit", "-m", "test: unresolved decision")
    result = run_authorize(authorization_repo, "AUTO-002")
    assert result.returncode == 6
    assert "unresolved Human Owner decision" in result.stderr


def test_wrong_branch_baseline_is_rejected(authorization_repo: Path) -> None:
    git(authorization_repo, "checkout", "-b", "feature/wrong")
    result = run_authorize(authorization_repo, "AUTO-002")
    assert result.returncode == 6
    assert "branch baseline not met" in result.stderr


def test_required_upstream_baseline_is_rejected_when_missing(
    authorization_repo: Path,
) -> None:
    config = authorization_repo / "self-governance.yaml"
    config.write_text(config.read_text() + "  require_upstream: true\n")
    git(authorization_repo, "add", "self-governance.yaml")
    git(authorization_repo, "commit", "-m", "test: require upstream")
    result = run_authorize(authorization_repo, "AUTO-002")
    assert result.returncode == 6
    assert "has no upstream" in result.stderr


@pytest.mark.parametrize("answer", ["", "authorize", "APPROVE", "AUTHORIZE "])
def test_first_gate_requires_exact_authorize(authorization_repo: Path, answer: str) -> None:
    before = git(authorization_repo, "status", "--porcelain")
    result = run_authorize(authorization_repo, "AUTO-002", stdin=f"{answer}\n")
    assert result.returncode == 7
    assert git(authorization_repo, "status", "--porcelain") == before
    assert commit_count(authorization_repo) == 1


def test_second_confirmation_is_required_and_non_mutating(authorization_repo: Path) -> None:
    result = run_authorize(authorization_repo, "AUTO-002", stdin="AUTHORIZE\nno\n")
    assert result.returncode == 7
    assert git(authorization_repo, "status", "--porcelain") == ""
    assert commit_count(authorization_repo) == 1


def test_governance_transition_and_commit_are_consistent(
    authorization_repo: Path,
) -> None:
    before_branch = git(authorization_repo, "branch", "--show-current")
    before_upstream = git(
        authorization_repo, "rev-parse", "--abbrev-ref", "@{upstream}", check=False
    )
    before_stashes = git(authorization_repo, "stash", "list")
    result = run_authorize(authorization_repo, "AUTO-002", stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 0, result.stderr

    queue = (authorization_repo / "docs" / "TASK_QUEUE.md").read_text()
    current = (authorization_repo / "docs" / "current_task.md").read_text()
    remaining = (authorization_repo / "docs" / "remaining_tasks.md").read_text()
    registry = (
        authorization_repo / "docs" / "workflow-automation" / "STAGE_REGISTRY.md"
    ).read_text()
    assert queue.count("Status: Current") == 1
    assert "## AUTO-002" in current and "Status: Current" in current
    assert "| AUTO-002 | planned work | Current |" in remaining
    assert "| AUTO-002 | planned work | role | AUTHORIZED |" in registry
    assert registry.count("Human Owner supplied both exact `AUTHORIZE`") == 1

    handover = authorization_repo / "handover" / "PROJECT_HANDOVER.md"
    manifest = (authorization_repo / "handover" / "PROJECT_CHECKSUM.md").read_text()
    assert hashlib.sha256(handover.read_bytes()).hexdigest() in manifest
    assert f"| {handover.stat().st_size} |" in manifest

    assert commit_count(authorization_repo) == 2
    assert git(authorization_repo, "log", "-1", "--format=%s") == (
        "docs(governance): authorize AUTO-002"
    )
    committed = set(
        git(authorization_repo, "show", "--format=", "--name-only", "HEAD").splitlines()
    )
    assert "scripts/workflow-authorize.sh" not in committed
    assert "tests/test_workflow_authorize_script.py" not in committed
    assert all(path.startswith(("docs/", "handover/")) for path in committed), committed
    # AUTO-002 is registry-governed with a registered branch different from `main` (GOV-AUTO-04):
    # the gate creates and switches to it, from the authorization commit, immediately afterwards.
    assert before_branch == "main"
    assert git(authorization_repo, "branch", "--show-current") == "feature/auto-002"
    assert git(authorization_repo, "rev-parse", "main") == git(
        authorization_repo, "rev-parse", "feature/auto-002"
    )
    assert (
        git(authorization_repo, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
        == before_upstream
    )
    assert git(authorization_repo, "stash", "list") == before_stashes


def test_authorize_reports_working_branch(authorization_repo: Path) -> None:
    result = run_authorize(authorization_repo, "AUTO-002", stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 0, result.stderr
    assert "Working branch        : feature/auto-002" in result.stdout


def test_gov_family_task_stays_on_default_branch(authorization_repo: Path) -> None:
    # GOV-3 has no stage-registry row in the fixture, so its required branch equals the default
    # branch (GOV-AUTO-04): the gate must leave the working tree exactly on `main`, unlike a
    # registry-governed AUTO/DASH stage.
    result = run_authorize(authorization_repo, "GOV-3", stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 0, result.stderr
    assert git(authorization_repo, "branch", "--show-current") == "main"
    assert "Working branch        : main" in result.stdout


def test_branch_preparation_failure_after_commit_is_reported_distinctly(
    authorization_repo: Path,
) -> None:
    # A branch named exactly like the registered one already exists but points somewhere other
    # than where the authorization commit is about to land (an unrelated, pre-existing branch).
    # Preparation must refuse rather than guess, while the already-created authorization commit
    # is not rolled back — only publication/switching failed, not authorization itself.
    git(authorization_repo, "branch", "feature/auto-002")
    (authorization_repo / "docs" / "workflow-automation" / "extra.md").write_text(
        "unrelated\n", encoding="utf-8"
    )
    git(authorization_repo, "checkout", "feature/auto-002")
    git(authorization_repo, "add", "-A")
    git(authorization_repo, "commit", "-m", "test: unrelated divergent commit")
    git(authorization_repo, "checkout", "main")

    result = run_authorize(authorization_repo, "AUTO-002", stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 10
    assert "could not be prepared automatically" in result.stderr
    assert commit_count(authorization_repo) == 2, "the authorization commit itself must stand"
    assert git(authorization_repo, "branch", "--show-current") == "main"
    assert "Status: Current" in (authorization_repo / "docs" / "TASK_QUEUE.md").read_text()


def test_validation_failure_prevents_commit(authorization_repo: Path) -> None:
    result = run_authorize(
        authorization_repo,
        "AUTO-002",
        stdin="AUTHORIZE\nAUTHORIZE\n",
        extra_env={"WORKFLOW_VALIDATION_FAIL_AFTER": "1"},
    )
    assert result.returncode == 8
    assert commit_count(authorization_repo) == 1
    assert "Status: Current" in (authorization_repo / "docs" / "TASK_QUEUE.md").read_text()


def test_runner_status_is_propagated(authorization_repo: Path) -> None:
    result = run_authorize(
        authorization_repo,
        "AUTO-002",
        "codex",
        stdin="AUTHORIZE\nAUTHORIZE\n",
        extra_env={"WORKFLOW_RUNNER_STATUS": "37"},
    )
    assert result.returncode == 37
    assert commit_count(authorization_repo) == 2
    assert (authorization_repo / "runner.log").read_text().strip() == "codex"
    committed = git(authorization_repo, "show", "--format=", "--name-only", "HEAD").splitlines()
    assert "runner.log" not in committed


def test_no_push_and_stashes_unchanged(authorization_repo: Path, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )
    git(authorization_repo, "remote", "add", "origin", str(origin))
    readme = authorization_repo / "README.md"
    readme.write_text("stash this\n")
    git(authorization_repo, "add", "README.md")
    git(authorization_repo, "commit", "-m", "test: add readme")
    readme.write_text("precious stash\n")
    git(authorization_repo, "stash", "push", "-m", "precious")
    stashes_before = git(authorization_repo, "stash", "list")

    result = run_authorize(authorization_repo, "AUTO-002", stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 0, result.stderr
    assert git(authorization_repo, "stash", "list") == stashes_before
    remote_refs = subprocess.run(
        ["git", "-C", str(origin), "for-each-ref"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert remote_refs == ""


def test_commit_failure_restores_index_but_keeps_worktree(
    authorization_repo: Path,
) -> None:
    hook = authorization_repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/usr/bin/env bash\nexit 1\n")
    hook.chmod(0o755)
    result = run_authorize(authorization_repo, "AUTO-002", stdin="AUTHORIZE\nAUTHORIZE\n")
    assert result.returncode == 9
    assert commit_count(authorization_repo) == 1
    assert git(authorization_repo, "diff", "--cached", "--name-only") == ""
    assert "Status: Current" in (authorization_repo / "docs" / "TASK_QUEUE.md").read_text()
    assert "working-tree governance content was not discarded" in result.stderr


def test_script_is_executable_and_contains_no_eval_push_or_merge() -> None:
    assert os.access(AUTHORIZE_SCRIPT, os.X_OK)
    body = AUTHORIZE_SCRIPT.read_text()
    executable = "\n".join(
        line for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )
    assert "eval " not in executable
    assert " git push" not in executable
    assert " git merge" not in executable
