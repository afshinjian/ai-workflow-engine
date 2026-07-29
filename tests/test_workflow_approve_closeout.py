"""Tests for GOV-AUTO-03's automatic task closeout in `scripts/workflow-approve.sh`.

The closeout transaction only activates when the repository carries the stable
`project.id: ai-workflow-engine` marker in `self-governance.yaml` *and* the full governance file
set exists (mirroring the same marker `scripts/workflow-authorize.sh` already uses). Every test
here builds a disposable temporary Git repository with that marker and a minimal-but-structurally
faithful governance document set, so the real repository is never touched, and the pre-existing
GOV-AUTO-01 sandbox (which uses `project.id: sandbox` and has no governance files) keeps taking the
unchanged legacy path exercised by `tests/test_workflow_runner_scripts.py`.
"""

from __future__ import annotations

import hashlib
import os
import select
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APPROVE_SCRIPT = REPO_ROOT / "scripts" / "workflow-approve.sh"

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


def commit_count(repo: Path) -> int:
    return int(git(repo, "rev-list", "--count", "HEAD"))


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


PROJECT_STATE = """# Project State

Current Version: 1.0.0

## Summary

Sandbox project state for GOV-AUTO-03 closeout tests.

## Completed

- Baseline (test fixture).

## In progress

No task is in progress.

## Planned

None beyond the sandbox task.

## Blockers

None.
"""

PYPROJECT = """[project]
name = "sandbox"
version = "1.0.0"
"""

CONTEXT = """# Context

Sandbox context document. No task-shaped content here.
"""

DECISION_LOG = """# Decision Log

## 2026-01-01 — Baseline

Initial decision log entry for the sandbox.
"""

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- Baseline.
"""

HANDOVER = """# Project Handover

## Where things stand

Sandbox handover baseline.
"""


def _governance_yaml(repo: Path) -> str:
    return f"""project:
  id: ai-workflow-engine
  repository: "{repo}"
  default_branch: main
  timezone: UTC
  require_upstream: false
  conda_environment: ai-workflow-engine

governance:
  project_state: docs/PROJECT_STATE.md
  task_queue: docs/TASK_QUEUE.md
  current_task: docs/current_task.md
  remaining_tasks: docs/remaining_tasks.md
  context: docs/CONTEXT.md
  pyproject: pyproject.toml
  facts:
    - name: version
      paths: [docs/PROJECT_STATE.md, pyproject.toml]
      pattern: '(?:Current Version[^\\n]*?|^version\\s*=\\s*")[^0-9]*(\\d+\\.\\d+\\.\\d+)'
      required: true

handover:
  manifest: handover/PROJECT_CHECKSUM.md
  files:
    - handover/PROJECT_HANDOVER.md

protected_paths:
  never_stage: []
  never_commit: []

workflow:
  maximum_current_tasks: 1
  require_designer_approval_for_promotion: true
  allow_automatic_commit: false
  allow_automatic_push: false

agents: []
"""


def _checksum_manifest(repo: Path) -> str:
    handover_path = repo / "handover" / "PROJECT_HANDOVER.md"
    data = handover_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return (
        "# Project Checksum Manifest\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(data)} | 2026-01-01 | {digest} |\n"
    )


def _write_queue(current_tasks: list[str], other: str = "") -> str:
    body = ["# Task Queue", ""]
    for task_id in current_tasks:
        body.append(f"## {task_id} — Sandbox task")
        body.append("")
        body.append("Status: Current")
        body.append("")
        body.append("Test task for GOV-AUTO-03 closeout testing.")
        body.append("")
    body.append(other)
    return "\n".join(body)


def _write_current_mirror(task_ids: list[str]) -> str:
    if not task_ids:
        return "# Current Task\n\nNo task is currently active.\n"
    parts = ["# Current Task", ""]
    for task_id in task_ids:
        parts += [f"## {task_id}", "", "Status: Current", ""]
    return "\n".join(parts)


def _write_remaining_mirror(rows: list[tuple[str, str, str]]) -> str:
    lines = [
        "# Remaining Work",
        "",
        "| Task | Title | Status |",
        "|---|---|---|",
    ]
    for task_id, title, status in rows:
        lines.append(f"| {task_id} | {title} | {status} |")
    return "\n".join(lines) + "\n"


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A disposable ai-workflow-engine-shaped repository with a single Current task, GOV-TEST-1."""
    repo = tmp_path / "gov sandbox"  # deliberate space: paths with spaces must work
    task_id = "GOV-TEST-1"

    (repo / "scripts").mkdir(parents=True)
    (repo / "docs" / "reports").mkdir(parents=True)
    (repo / "handover").mkdir(parents=True)

    import shutil

    shutil.copy2(APPROVE_SCRIPT, repo / "scripts" / "workflow-approve.sh")
    (repo / "scripts" / "workflow-approve.sh").chmod(0o755)

    (repo / "self-governance.yaml").write_text(_governance_yaml(repo), encoding="utf-8")
    (repo / "docs" / "PROJECT_STATE.md").write_text(PROJECT_STATE, encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (repo / "docs" / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
    (repo / "docs" / "DECISION_LOG.md").write_text(DECISION_LOG, encoding="utf-8")
    (repo / "docs" / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (repo / "docs" / "TASK_QUEUE.md").write_text(_write_queue([task_id]), encoding="utf-8")
    (repo / "docs" / "current_task.md").write_text(
        _write_current_mirror([task_id]), encoding="utf-8"
    )
    (repo / "docs" / "remaining_tasks.md").write_text(
        _write_remaining_mirror([(task_id, "Sandbox task", "Current")]), encoding="utf-8"
    )
    (repo / "docs" / "reports" / f"{task_id}-completion-report.md").write_text(
        f"# {task_id} Completion Report\n\n## Result\n\nIMPLEMENTED_PENDING_HUMAN_APPROVAL\n",
        encoding="utf-8",
    )
    (repo / "handover" / "PROJECT_HANDOVER.md").write_text(HANDOVER, encoding="utf-8")
    (repo / "handover" / "PROJECT_CHECKSUM.md").write_text(
        _checksum_manifest(repo), encoding="utf-8"
    )
    (repo / "README.md").write_text("sandbox\n", encoding="utf-8")

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: sandbox baseline")
    return repo


def dirty(repo: Path, name: str = "src_change.txt", content: str = "implementation\n") -> None:
    (repo / name).write_text(content, encoding="utf-8")


def dirty_dir(repo: Path, relative_dir: str, filenames: list[str]) -> list[str]:
    """Create a brand-new, entirely-untracked nested directory containing the given files.

    Returns the repo-relative path of each created file. Used to reproduce the scope-checker bug:
    `git status`'s *default* untracked mode collapses a brand-new directory into one
    directory-summary path (e.g. `agentos_workflow/tests/e2e/`) instead of listing the files
    inside it — even when that directory holds only a single file.
    """
    target = repo / relative_dir
    target.mkdir(parents=True, exist_ok=True)
    created = []
    for name in filenames:
        (target / name).write_text(f"{name} content\n", encoding="utf-8")
        created.append(f"{relative_dir}/{name}")
    return created


APPROVE_TWICE = "APPROVE\nAPPROVE\n"
GOOD_MESSAGE = "feat(sandbox): implement the thing (GOV-TEST-1)"


def _read_until(stream: IO[str], marker: str, timeout: float = 15.0) -> str:
    """Read from `stream` until `marker` appears in the accumulated output, or raise on timeout.

    Necessary because `workflow-approve.sh`'s prompts (`Approval: `, `Confirm commit: `) are
    printed with no trailing newline, so `readline()` would block forever waiting for one that
    never comes.
    """
    buf = ""
    fd = stream.fileno()
    deadline = time.monotonic() + timeout
    while marker not in buf:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {marker!r}; got so far: {buf!r}")
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            continue
        chunk = os.read(fd, 4096).decode("utf-8", errors="replace")
        if not chunk:
            break
        buf += chunk
    return buf


def approve_with_injection_before_second_confirmation(
    sandbox: Path, inject: Callable[[], None]
) -> subprocess.CompletedProcess[str]:
    """Drive `workflow-approve.sh` through its first confirmation (the point at which the
    implementation file list has already been captured from `git status` and displayed to the
    Human Owner), call `inject()` — simulating a file that was never shown to and never approved
    by the Human Owner — and then answer the second (commit) confirmation.

    This is the only way to construct a file that is genuinely absent from `impl_files` (captured
    once, at script start, before any prompt) while still being present in the working tree by the
    time the post-closeout scope check re-reads `git status`.
    """
    proc = subprocess.Popen(
        [str(sandbox / "scripts" / "workflow-approve.sh"), "-m", GOOD_MESSAGE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **GIT_ENV},
        cwd=str(Path(os.sep)),
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    collected_stdout = ""
    try:
        collected_stdout += _read_until(proc.stdout, "Approval: ")
        proc.stdin.write("APPROVE\n")
        proc.stdin.flush()
        collected_stdout += _read_until(proc.stdout, "Confirm commit: ")
        inject()
        proc.stdin.write("APPROVE\n")
        proc.stdin.flush()
        rest_stdout, stderr = proc.communicate(timeout=30)
        collected_stdout += rest_stdout
        returncode = proc.returncode
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert returncode is not None
    return subprocess.CompletedProcess(proc.args, returncode, collected_stdout, stderr)


# =============================================================================================
# Task discovery and state
# =============================================================================================


def test_single_current_task_is_accepted_and_closed(sandbox: Path) -> None:
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert commit_count(sandbox) == before + 1
    queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    assert "Status: Done" in queue
    current_mirror = (sandbox / "docs" / "current_task.md").read_text(encoding="utf-8")
    assert "GOV-TEST-1" not in current_mirror.split("No task is currently active")[0]
    assert "No task is currently active" in current_mirror
    remaining = (sandbox / "docs" / "remaining_tasks.md").read_text(encoding="utf-8")
    assert "GOV-TEST-1" not in remaining
    assert git(sandbox, "status", "--porcelain") == ""


def test_zero_current_tasks_is_rejected(sandbox: Path) -> None:
    (sandbox / "docs" / "TASK_QUEUE.md").write_text(
        _write_queue([]) + "\n## GOV-TEST-1 — Sandbox task\n\nStatus: Done\n", encoding="utf-8"
    )
    git(sandbox, "commit", "-am", "chore: no current task")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 10
    assert "no Current task" in result.stderr
    assert commit_count(sandbox) == before


def test_multiple_current_tasks_is_rejected(sandbox: Path) -> None:
    queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    queue += "\n## GOV-TEST-2 — Second sandbox task\n\nStatus: Current\n"
    (sandbox / "docs" / "TASK_QUEUE.md").write_text(queue, encoding="utf-8")
    git(sandbox, "commit", "-am", "chore: two current tasks")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 11
    assert "more than one Current task" in result.stderr
    assert commit_count(sandbox) == before


def test_current_task_mirror_mismatch_is_rejected(sandbox: Path) -> None:
    (sandbox / "docs" / "current_task.md").write_text(
        _write_current_mirror(["GOV-TEST-9"]), encoding="utf-8"
    )
    git(sandbox, "commit", "-am", "chore: break current mirror")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 12
    assert "disagrees" in result.stderr
    assert commit_count(sandbox) == before


def test_remaining_mirror_mismatch_is_rejected(sandbox: Path) -> None:
    (sandbox / "docs" / "remaining_tasks.md").write_text(
        _write_remaining_mirror([("GOV-TEST-1", "Sandbox task", "Planned")]), encoding="utf-8"
    )
    git(sandbox, "commit", "-am", "chore: break remaining mirror")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 12
    assert commit_count(sandbox) == before


def test_duplicate_task_heading_is_rejected(sandbox: Path) -> None:
    queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    queue += "\n## GOV-TEST-1 — Duplicate heading\n\nStatus: Planned\n"
    (sandbox / "docs" / "TASK_QUEUE.md").write_text(queue, encoding="utf-8")
    git(sandbox, "commit", "-am", "chore: duplicate heading")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 12
    assert "headings for GOV-TEST-1" in result.stderr
    assert commit_count(sandbox) == before


def test_blocked_task_is_rejected(sandbox: Path) -> None:
    (sandbox / "docs" / "TASK_QUEUE.md").write_text(
        "# Task Queue\n\n## GOV-TEST-1 — Sandbox task\n\nStatus: Current\n\n"
        "Blocked on an external dependency.\n",
        encoding="utf-8",
    )
    git(sandbox, "commit", "-am", "chore: block task")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 13
    assert "not closeable" in result.stderr
    assert commit_count(sandbox) == before


def test_missing_completion_report_is_rejected(sandbox: Path) -> None:
    (sandbox / "docs" / "reports" / "GOV-TEST-1-completion-report.md").unlink()
    git(sandbox, "commit", "-am", "chore: drop completion report")
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 14
    assert "no completion report found" in result.stderr
    assert commit_count(sandbox) == before


# =============================================================================================
# Approval gates
# =============================================================================================


def test_first_confirmation_decline_changes_nothing(sandbox: Path) -> None:
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin="no\n")
    assert result.returncode == 7
    assert commit_count(sandbox) == before
    assert (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8").count(
        "Status: Current"
    ) == 1
    assert git(sandbox, "diff", "--cached", "--name-only") == ""


def test_second_confirmation_decline_changes_nothing(sandbox: Path) -> None:
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin="APPROVE\nno\n")
    assert result.returncode == 7
    assert commit_count(sandbox) == before
    assert "Status: Done" not in (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    assert git(sandbox, "diff", "--cached", "--name-only") == ""


@pytest.mark.parametrize("answer", ["approve", "Approve", "yes", "", "APPROVE "])
def test_exact_approve_token_is_required(sandbox: Path, answer: str) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=f"{answer}\n")
    assert result.returncode == 7


def test_invalid_commit_message_shape_is_rejected(sandbox: Path) -> None:
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, stdin="not conventional (GOV-TEST-1)\n")
    assert result.returncode == 8
    assert commit_count(sandbox) == before


def test_commit_message_not_naming_current_task_is_rejected(sandbox: Path) -> None:
    dirty(sandbox)
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", "feat(sandbox): implement the thing", stdin=APPROVE_TWICE)
    assert result.returncode == 15
    assert "does not name" in result.stderr
    assert commit_count(sandbox) == before


def test_no_closeout_happens_before_human_confirmation(sandbox: Path) -> None:
    dirty(sandbox)
    run_approve(sandbox, "-m", GOOD_MESSAGE, stdin="no\n")
    queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    assert "Status: Current" in queue
    assert "Status: Done" not in queue
    checksum_before = (sandbox / "handover" / "PROJECT_CHECKSUM.md").read_text(encoding="utf-8")
    assert "2026-01-01" in checksum_before


# =============================================================================================
# Closeout and commit behaviour
# =============================================================================================


def test_closeout_updates_decision_log_changelog_handover_checksum(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr

    decision_log = (sandbox / "docs" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert "Human Owner approved and closed GOV-TEST-1" in decision_log

    changelog = (sandbox / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "GOV-TEST-1" in changelog and "closed" in changelog

    report = (sandbox / "docs" / "reports" / "GOV-TEST-1-completion-report.md").read_text(
        encoding="utf-8"
    )
    assert "Addendum — Human Owner approval and closure" in report
    assert "IMPLEMENTED_PENDING_HUMAN_APPROVAL" in report  # original content preserved

    handover = (sandbox / "handover" / "PROJECT_HANDOVER.md").read_text(encoding="utf-8")
    assert "Closure update" in handover
    assert "GOV-TEST-1 was approved and closed" in handover

    checksum = (sandbox / "handover" / "PROJECT_CHECKSUM.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(handover.encode("utf-8")).hexdigest()
    assert digest in checksum
    assert str(len(handover.encode("utf-8"))) in checksum


def test_implementation_and_closeout_land_in_exactly_one_commit(sandbox: Path) -> None:
    dirty(sandbox, "one.txt")
    dirty(sandbox, "two.txt")
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert commit_count(sandbox) == before + 1

    committed = set(git(sandbox, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert {"one.txt", "two.txt"} <= committed
    assert "docs/TASK_QUEUE.md" in committed
    assert "docs/current_task.md" in committed
    assert "docs/remaining_tasks.md" in committed
    assert "docs/DECISION_LOG.md" in committed
    assert "docs/CHANGELOG.md" in committed
    assert "handover/PROJECT_HANDOVER.md" in committed
    assert "handover/PROJECT_CHECKSUM.md" in committed
    assert "docs/reports/GOV-TEST-1-completion-report.md" in committed


def test_commit_subject_matches_approved_message(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert git(sandbox, "log", "-1", "--format=%s") == GOOD_MESSAGE


def test_final_working_tree_is_clean_and_task_is_done(sandbox: Path) -> None:
    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert git(sandbox, "status", "--porcelain") == ""
    assert "COMMIT_COMPLETE_READY_FOR_NEXT_TASK" in result.stdout
    assert "Task closed    : GOV-TEST-1" in result.stdout


def test_next_planned_task_is_reported_but_not_authorized(sandbox: Path) -> None:
    queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    queue += "\n## GOV-TEST-2 — Next up\n\nStatus: Planned\n"
    (sandbox / "docs" / "TASK_QUEUE.md").write_text(queue, encoding="utf-8")
    git(sandbox, "commit", "-am", "chore: add planned successor")
    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert "Next Planned (unauthorized) task: GOV-TEST-2" in result.stdout
    final_queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    assert "GOV-TEST-2" in final_queue
    section = final_queue.split("GOV-TEST-2")[1]
    assert "Status: Planned" in section


# =============================================================================================
# Failure atomicity
# =============================================================================================


def test_closeout_validation_failure_restores_governance_and_preserves_implementation(
    sandbox: Path,
) -> None:
    """Break the version fact so `check-governance` fails only after closeout has mutated files."""
    (sandbox / "pyproject.toml").write_text(
        '[project]\nname = "sandbox"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    git(sandbox, "commit", "-am", "chore: mismatched version fact")

    decision_log_before = (sandbox / "docs" / "DECISION_LOG.md").read_text(encoding="utf-8")
    changelog_before = (sandbox / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    queue_before = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")

    dirty(sandbox, "precious.txt", "irreplaceable implementation content\n")
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)

    assert result.returncode == 16
    assert commit_count(sandbox) == before
    assert (sandbox / "docs" / "DECISION_LOG.md").read_text(encoding="utf-8") == decision_log_before
    assert (sandbox / "docs" / "CHANGELOG.md").read_text(encoding="utf-8") == changelog_before
    assert (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8") == queue_before
    assert (sandbox / "precious.txt").read_text(encoding="utf-8") == (
        "irreplaceable implementation content\n"
    )
    assert git(sandbox, "diff", "--cached", "--name-only") == ""
    assert "restored" in (result.stderr + result.stdout).lower()


# =============================================================================================
# Git safety
# =============================================================================================


def test_no_push_merge_branch_or_stash_mutation(sandbox: Path, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(sandbox, "remote", "add", "origin", str(origin))
    git(sandbox, "branch", "other")
    (sandbox / "README.md").write_text("stash me\n", encoding="utf-8")
    git(sandbox, "stash", "push", "-m", "precious")
    stash_before = git(sandbox, "stash", "list")
    branch_before = git(sandbox, "rev-parse", "--abbrev-ref", "HEAD")

    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr

    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert git(sandbox, "stash", "list") == stash_before
    assert "precious" in git(sandbox, "stash", "list")
    remote_refs = subprocess.run(
        ["git", "-C", str(origin), "for-each-ref"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert remote_refs == ""


def test_no_successor_task_is_authorized(sandbox: Path) -> None:
    queue = (sandbox / "docs" / "TASK_QUEUE.md").read_text(encoding="utf-8")
    queue += "\n## GOV-TEST-2 — Next up\n\nStatus: Planned\n"
    (sandbox / "docs" / "TASK_QUEUE.md").write_text(queue, encoding="utf-8")
    git(sandbox, "commit", "-am", "chore: add planned successor")
    dirty(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    final_current = (sandbox / "docs" / "current_task.md").read_text(encoding="utf-8")
    assert "GOV-TEST-2" not in final_current


# =============================================================================================
# Untracked directory scope resolution (regression: AUTO-007 commit-attempt false rejection)
#
# `git status`'s *default* untracked mode collapses a brand-new, entirely-untracked directory into
# one directory-summary path (e.g. `agentos_workflow/tests/e2e/`) instead of listing the files
# inside it. The implementation file list (`impl_files`) has always used `--untracked-files=all` to
# avoid this, but the final post-closeout scope check re-read `git status` without that flag, so it
# saw the collapsed directory path while `impl_files` held the individual file paths underneath it
# — the two could never string-compare equal, and the closeout died with "unexpected change outside
# the approved+closeout set: <dir>/" even though every file in that directory was, in fact, exactly
# what had been approved. Fixed by resolving both call sites through one shared helper that always
# uses `--untracked-files=all`.
# =============================================================================================


def test_one_untracked_nested_directory_is_approved(sandbox: Path) -> None:
    dirty_dir(sandbox, "src/pkg/sub", ["new_module.py"])
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert commit_count(sandbox) == before + 1
    committed = set(git(sandbox, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert "src/pkg/sub/new_module.py" in committed
    assert git(sandbox, "status", "--porcelain") == ""


def test_multiple_untracked_nested_directories_are_all_approved(sandbox: Path) -> None:
    e2e_files = dirty_dir(sandbox, "agentos_workflow/tests/e2e", ["__init__.py", "test_dry_run.py"])
    recovery_files = dirty_dir(
        sandbox, "agentos_workflow/tests/recovery", ["__init__.py", "test_matrix.py"]
    )
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert commit_count(sandbox) == before + 1
    committed = set(git(sandbox, "show", "--name-only", "--format=", "HEAD").splitlines())
    for path in e2e_files + recovery_files:
        assert path in committed
    assert git(sandbox, "status", "--porcelain") == ""


def test_mixed_tracked_and_untracked_changes_are_approved(sandbox: Path) -> None:
    dirty(sandbox, "README.md", "modified tracked content\n")
    new_files = dirty_dir(sandbox, "docs/notes/sub", ["note.md"])
    before = commit_count(sandbox)
    result = run_approve(sandbox, "-m", GOOD_MESSAGE, stdin=APPROVE_TWICE)
    assert result.returncode == 0, result.stderr
    assert commit_count(sandbox) == before + 1
    committed = set(git(sandbox, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert "README.md" in committed
    for path in new_files:
        assert path in committed
    assert git(sandbox, "status", "--porcelain") == ""


def test_unauthorized_file_appearing_inside_an_approved_directory_is_rejected(
    sandbox: Path,
) -> None:
    """The directory-expansion fix must not create a loophole where approving one file in a
    directory silently approves every other file that later appears in that same directory. A file
    written into an otherwise-approved directory *after* the implementation file list was captured
    and shown to the Human Owner, but before the second (commit) confirmation, must still be caught
    as an unexpected change."""
    approved_dir = sandbox / "agentos_workflow" / "tests" / "e2e"
    approved_dir.mkdir(parents=True)
    (approved_dir / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

    def inject() -> None:
        (approved_dir / "unauthorized_extra.py").write_text(
            "# never shown to the Human Owner\n", encoding="utf-8"
        )

    before = commit_count(sandbox)
    result = approve_with_injection_before_second_confirmation(sandbox, inject)
    combined = result.stdout + result.stderr
    assert result.returncode == 16, combined  # EXIT_CLOSEOUT_FAILED
    assert "unexpected change outside the approved+closeout set" in combined
    assert "unauthorized_extra.py" in combined
    assert commit_count(sandbox) == before
    assert (approved_dir / "test_a.py").read_text(encoding="utf-8") == "def test_a(): pass\n"


def test_unauthorized_unrelated_top_level_file_is_still_rejected(sandbox: Path) -> None:
    """Same boundary, unrelated location: a file appearing outside any approved directory at all
    must also still be rejected — confirms the directory-expansion fix narrows nothing about the
    pre-existing approved-file boundary; it only stops a directory's own approved files from being
    falsely rejected."""
    dirty(sandbox)

    def inject() -> None:
        (sandbox / "sneaky_unrelated.txt").write_text("never approved\n", encoding="utf-8")

    before = commit_count(sandbox)
    result = approve_with_injection_before_second_confirmation(sandbox, inject)
    combined = result.stdout + result.stderr
    assert result.returncode == 16, combined
    assert "unexpected change outside the approved+closeout set" in combined
    assert "sneaky_unrelated.txt" in combined
    assert commit_count(sandbox) == before
