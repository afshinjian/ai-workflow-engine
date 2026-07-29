"""Tests for GOV-AUTO-04's completion-report discovery extension in
`scripts/workflow-approve.sh`.

Resolves OD-D11 (`docs/agentos-dashboard/OPEN_QUESTIONS.md`): the Dashboard program's own naming
convention for a stage's completion report is
`docs/reports/agentos-dashboard/STAGE-XX-completion.md`
(`docs/agentos-dashboard/STAGE_REGISTRY.md` §3), but the approval gate previously only accepted
`<TASK_ID>-completion-report.md`, so every DASH closeout needed a manual duplicate copy. These
tests build disposable, self-contained `ai-workflow-engine`-shaped sandboxes (never the real
repository) with a DASH-family Current task and a matching `agentos-dashboard` stage registry row,
and drive `scripts/workflow-approve.sh` end to end.
"""

from __future__ import annotations

import hashlib
import os
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import IO

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

APPROVE_TWICE = "APPROVE\nAPPROVE\n"


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


def _dash_registry_row(task_id: str, branch: str, state: str = "IN_PROGRESS") -> str:
    return (
        "# AgentOS Dashboard — Stage Registry\n\n"
        "## 3. Registry\n\n"
        "Report paths: `docs/reports/agentos-dashboard/STAGE-XX-completion.md`.\n\n"
        "| Stage | Title | Role | State | Branch | Prompt |\n"
        "|---|---|---|---|---|---|\n"
        f"| {task_id} | Sandbox stage | role | {state} | `{branch}` | `p.md` |\n\n"
        "## 4. Authorization Log\n\n"
        "| Date | Stage | Authorization record | Recorded by |\n"
        "|---|---|---|---|\n\n"
        "## 5. Decision References\n\nNone.\n"
    )


def build_dash_sandbox(
    tmp_path: Path,
    *,
    task_id: str = "DASH-002",
    branch: str = "feature/dash-002-repo-adapter",
    checkout_branch: str | None = None,
) -> Path:
    """A disposable `ai-workflow-engine`-shaped repository with a single DASH-family Current
    task, a matching `docs/agentos-dashboard/STAGE_REGISTRY.md` row, and the working tree already
    on `checkout_branch` (defaults to `branch`) — the registry-governed branch precondition
    `workflow-approve.sh` enforces before any report is even looked up.
    """
    repo = tmp_path / "dash sandbox"  # deliberate space: paths with spaces must work
    (repo / "scripts").mkdir(parents=True)
    (repo / "docs" / "reports" / "agentos-dashboard").mkdir(parents=True)
    (repo / "docs" / "agentos-dashboard").mkdir(parents=True)
    (repo / "handover").mkdir(parents=True)

    shutil.copy2(APPROVE_SCRIPT, repo / "scripts" / "workflow-approve.sh")
    (repo / "scripts" / "workflow-approve.sh").chmod(0o755)

    (repo / "self-governance.yaml").write_text(_governance_yaml(repo), encoding="utf-8")
    (repo / "docs" / "PROJECT_STATE.md").write_text(PROJECT_STATE, encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (repo / "docs" / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
    (repo / "docs" / "DECISION_LOG.md").write_text(DECISION_LOG, encoding="utf-8")
    (repo / "docs" / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (repo / "docs" / "TASK_QUEUE.md").write_text(
        f"# Task Queue\n\n## {task_id} — Sandbox stage\n\nStatus: Current\n\nTest fixture task.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "current_task.md").write_text(
        f"# Current Task\n\n## {task_id}\n\nStatus: Current\n", encoding="utf-8"
    )
    (repo / "docs" / "remaining_tasks.md").write_text(
        "# Remaining Work\n\n| Task | Title | Status |\n|---|---|---|\n"
        f"| {task_id} | Sandbox stage | Current |\n",
        encoding="utf-8",
    )
    (repo / "docs" / "agentos-dashboard" / "STAGE_REGISTRY.md").write_text(
        _dash_registry_row(task_id, branch), encoding="utf-8"
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

    target_branch = checkout_branch if checkout_branch is not None else branch
    if target_branch and target_branch != "main":
        git(repo, "checkout", "-b", target_branch)
    return repo


def dirty(repo: Path, name: str = "src_change.txt", content: str = "implementation\n") -> None:
    (repo / name).write_text(content, encoding="utf-8")


def _read_until(stream: IO[str], marker: str, timeout: float = 15.0) -> str:
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


# =================================================================================================
# Canonical STAGE-XX-completion.md discovery
# =================================================================================================


def test_canonical_stage_report_is_discovered_directly(tmp_path: Path) -> None:
    repo = build_dash_sandbox(tmp_path)
    report = repo / "docs" / "reports" / "agentos-dashboard" / "STAGE-02-completion.md"
    report.write_text("# STAGE-02 Completion Report\n\nBody.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: add canonical report")
    dirty(repo)

    before = commit_count(repo)
    result = run_approve(
        repo, "-m", "feat(dashboard): sandbox stage (DASH-002)", stdin=APPROVE_TWICE
    )
    assert result.returncode == 0, result.stderr
    assert commit_count(repo) == before + 1
    assert "Addendum — Human Owner approval and closure" in report.read_text(encoding="utf-8")
    duplicate = repo / "docs" / "reports" / "agentos-dashboard" / "DASH-002-completion-report.md"
    assert not duplicate.exists(), "no duplicate report copy should ever be created"
    committed = git(repo, "show", "--format=", "--name-only", "HEAD").splitlines()
    assert "docs/reports/agentos-dashboard/STAGE-02-completion.md" in committed


def test_identical_duplicate_report_is_accepted(tmp_path: Path) -> None:
    repo = build_dash_sandbox(tmp_path)
    body = "# STAGE-02 Completion Report\n\nBody.\n"
    canonical = repo / "docs" / "reports" / "agentos-dashboard" / "STAGE-02-completion.md"
    duplicate = repo / "docs" / "reports" / "agentos-dashboard" / "DASH-002-completion-report.md"
    canonical.write_text(body, encoding="utf-8")
    duplicate.write_text(body, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: add both identical reports")
    dirty(repo)

    result = run_approve(
        repo, "-m", "feat(dashboard): sandbox stage (DASH-002)", stdin=APPROVE_TWICE
    )
    assert result.returncode == 0, result.stderr
    # Only the name-matched report (found first) receives the addendum; the canonical one is left
    # exactly as it already was, since the two were byte-identical duplicates, not a conflict.
    assert "Addendum" in duplicate.read_text(encoding="utf-8")
    assert canonical.read_text(encoding="utf-8") == body


def test_conflicting_reports_are_rejected_without_mutation(tmp_path: Path) -> None:
    repo = build_dash_sandbox(tmp_path)
    canonical = repo / "docs" / "reports" / "agentos-dashboard" / "STAGE-02-completion.md"
    duplicate = repo / "docs" / "reports" / "agentos-dashboard" / "DASH-002-completion-report.md"
    canonical.write_text("# STAGE-02 Completion Report\n\nCanonical body.\n", encoding="utf-8")
    duplicate.write_text("# STAGE-02 Completion Report\n\nDifferent body!\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: add conflicting reports")
    dirty(repo)

    before = commit_count(repo)
    canonical_before = canonical.read_text(encoding="utf-8")
    duplicate_before = duplicate.read_text(encoding="utf-8")
    result = run_approve(
        repo, "-m", "feat(dashboard): sandbox stage (DASH-002)", stdin=APPROVE_TWICE
    )
    assert result.returncode == 18
    assert "conflicting completion reports" in result.stderr
    assert commit_count(repo) == before
    assert canonical.read_text(encoding="utf-8") == canonical_before
    assert duplicate.read_text(encoding="utf-8") == duplicate_before
    assert git(repo, "status", "--porcelain").strip() != ""  # only the untracked dirty() file


def test_malformed_registry_branch_disables_canonical_lookup(tmp_path: Path) -> None:
    # The registry's Branch cell does not encode DASH-002's own stage number: this session must
    # never guess, so the canonical STAGE-02-completion.md is never even considered, and — with no
    # exact-name report present either — the closeout refuses with no mutation.
    repo = build_dash_sandbox(tmp_path, branch="feature/dash-999-mismatch")
    canonical = repo / "docs" / "reports" / "agentos-dashboard" / "STAGE-02-completion.md"
    canonical.write_text("# STAGE-02 Completion Report\n\nBody.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: add canonical report only, malformed registry branch")
    dirty(repo)

    before = commit_count(repo)
    result = run_approve(
        repo, "-m", "feat(dashboard): sandbox stage (DASH-002)", stdin=APPROVE_TWICE
    )
    assert result.returncode == 14
    assert "no completion report found" in result.stderr
    assert commit_count(repo) == before


def test_missing_report_is_still_rejected_for_dash_task(tmp_path: Path) -> None:
    repo = build_dash_sandbox(tmp_path)
    dirty(repo)
    before = commit_count(repo)
    result = run_approve(
        repo, "-m", "feat(dashboard): sandbox stage (DASH-002)", stdin=APPROVE_TWICE
    )
    assert result.returncode == 14
    assert "no completion report found" in result.stderr
    assert commit_count(repo) == before


def test_auto_task_report_discovery_is_unaffected(tmp_path: Path) -> None:
    # Regression guard: a non-DASH (AUTO-family) registry-governed task must keep using only the
    # existing exact-name convention; the new canonical-lookup block must never fire for it.
    repo = tmp_path / "auto sandbox"
    (repo / "scripts").mkdir(parents=True)
    (repo / "docs" / "reports" / "workflow-automation").mkdir(parents=True)
    (repo / "docs" / "workflow-automation").mkdir(parents=True)
    (repo / "handover").mkdir(parents=True)
    shutil.copy2(APPROVE_SCRIPT, repo / "scripts" / "workflow-approve.sh")
    (repo / "scripts" / "workflow-approve.sh").chmod(0o755)

    (repo / "self-governance.yaml").write_text(_governance_yaml(repo), encoding="utf-8")
    (repo / "docs" / "PROJECT_STATE.md").write_text(PROJECT_STATE, encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (repo / "docs" / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
    (repo / "docs" / "DECISION_LOG.md").write_text(DECISION_LOG, encoding="utf-8")
    (repo / "docs" / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (repo / "docs" / "TASK_QUEUE.md").write_text(
        "# Task Queue\n\n## AUTO-002 — Sandbox stage\n\nStatus: Current\n", encoding="utf-8"
    )
    (repo / "docs" / "current_task.md").write_text(
        "# Current Task\n\n## AUTO-002\n\nStatus: Current\n", encoding="utf-8"
    )
    (repo / "docs" / "remaining_tasks.md").write_text(
        "# Remaining Work\n\n| Task | Title | Status |\n|---|---|---|\n"
        "| AUTO-002 | Sandbox stage | Current |\n",
        encoding="utf-8",
    )
    (repo / "docs" / "workflow-automation" / "STAGE_REGISTRY.md").write_text(
        "# Registry\n\n## 4. Registry\n\n"
        "| Stage | Title | Role | State | Branch | Prompt |\n"
        "|---|---|---|---|---|---|\n"
        "| AUTO-002 | Sandbox stage | role | IN_PROGRESS | `feature/auto-002` | `p.md` |\n\n"
        "## 5. Authorization Log\n\n"
        "| Date | Stage | Authorization record | Recorded by |\n"
        "|---|---|---|---|\n\n"
        "## 6. Decision References\n\nNone.\n",
        encoding="utf-8",
    )
    auto_report = (
        repo / "docs" / "reports" / "workflow-automation" / "AUTO-002-completion-report.md"
    )
    auto_report.write_text("# AUTO-002 Completion Report\n\nBody.\n", encoding="utf-8")
    (repo / "handover").mkdir(exist_ok=True)
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
    git(repo, "checkout", "-b", "feature/auto-002")

    dirty(repo)
    result = run_approve(
        repo, "-m", "feat(workflow): sandbox stage (AUTO-002)", stdin=APPROVE_TWICE
    )
    assert result.returncode == 0, result.stderr
    report = (
        repo / "docs" / "reports" / "workflow-automation" / "AUTO-002-completion-report.md"
    ).read_text(encoding="utf-8")
    assert "Addendum — Human Owner approval and closure" in report
