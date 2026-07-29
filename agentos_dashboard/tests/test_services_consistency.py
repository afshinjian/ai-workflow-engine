"""TC-01/TC-02/TC-08/TC-14 — the consistency engine v1 (`services.consistency`).

Every rule is exercised against a real, controlled temporary Git repository
(`TEST_STRATEGY.md` §3: mock only time/subprocess-timeouts/clipboard), plus the two fixture
scenarios `DASH-003.md`'s Acceptance section names explicitly: a deliberate
PROJECT_STATE-vs-TASK_QUEUE contradiction, and a tampered handover manifest. A final test proves
checksum recomputation against the real `ai-workflow-engine` repository itself.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.parsing.handover import parse_checksum_manifest
from agentos_dashboard.services.consistency import (
    ConsistencySeverity,
    run_consistency_checks,
)

from .conftest import git, write

PYPROJECT = 'version = "9.9.9"\n'

TASK_QUEUE = """\
# Task Queue

## FAKE-001 — First task

Status: Current

## FAKE-002 — Second task

Status: Done
"""

CURRENT_TASK = """\
# Current Task

## FAKE-001

Status: Current
"""

REMAINING_TASKS = """\
# Remaining Work

| Task | Status |
|---|---|
| FAKE-001 | Current |
"""

PROJECT_STATE = """\
Current Version: 9.9.9

## Summary

Fixture project.

## Completed
- FAKE-002 (closed 2026-01-01): done.

## Blockers

None.
"""

DECISION_LOG_PREFIX = "# Decision Log\n\n"
DECISION_LOG_DEFAULT_BODY = "## 2026-07-29 — Fixture entry\n\nNo commit referenced here.\n"

IMPLEMENTATION_STATE = """\
schema_name: orchestration-implementation-state
feature_id: ORCH
current_stage: ORCH-001
next_eligible_stage: ORCH-002
delivery_order: [ORCH-000, ORCH-001, ORCH-002]
stages:
  ORCH-000:
    title: Bootstrap
    status: REVIEW_APPROVED
    prerequisites: []
    blockers: []
    evidence: []
  ORCH-001:
    title: Validator
    status: VERIFIED
    prerequisites: [ORCH-000]
    blockers: []
    evidence: []
  ORCH-002:
    title: Registry
    status: NOT_STARTED
    prerequisites: [ORCH-001]
    blockers: []
    evidence: []
"""

HANDOVER_BODY = "# Project Handover\n\nFixture handover narrative.\n"


def _manifest_for(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    size = len(body.encode("utf-8"))
    return (
        "# Project Checksum Manifest\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {size} | 2026-07-29 | {digest} |\n"
    )


def _populate(
    repo: Path,
    *,
    task_queue: str = TASK_QUEUE,
    current_task: str = CURRENT_TASK,
    remaining_tasks: str = REMAINING_TASKS,
    project_state: str = PROJECT_STATE,
    decision_log_body: str = DECISION_LOG_DEFAULT_BODY,
    implementation_state: str = IMPLEMENTATION_STATE,
    handover_body: str = HANDOVER_BODY,
    manifest: str | None = None,
    pyproject: str = PYPROJECT,
) -> None:
    write(repo, "docs/TASK_QUEUE.md", task_queue)
    write(repo, "docs/current_task.md", current_task)
    write(repo, "docs/remaining_tasks.md", remaining_tasks)
    write(repo, "docs/PROJECT_STATE.md", project_state)
    write(repo, "docs/DECISION_LOG.md", DECISION_LOG_PREFIX + decision_log_body)
    write(repo, "docs/implementation/orchestration/implementation-state.yaml", implementation_state)
    write(repo, "handover/PROJECT_HANDOVER.md", handover_body)
    write(
        repo,
        "handover/PROJECT_CHECKSUM.md",
        manifest if manifest is not None else _manifest_for(handover_body),
    )
    write(repo, "pyproject.toml", pyproject)


@pytest.fixture
def consistency_repo(git_repo: Path) -> Path:
    _populate(git_repo)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "populate consistency fixture")
    return git_repo


@pytest.fixture
def consistency_root(consistency_repo: Path) -> RepositoryRoot:
    return RepositoryRoot.from_path(consistency_repo)


def test_well_formed_repository_has_no_findings(consistency_root: RepositoryRoot) -> None:
    report = run_consistency_checks(consistency_root)
    assert report.findings == ()


def test_current_task_mismatch_is_detected(git_repo: Path) -> None:
    _populate(git_repo, current_task=CURRENT_TASK.replace("Current", "Planned"))
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "mismatch")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    rules = {finding.rule for finding in report.findings}
    assert "current_task_mismatch" in rules


def test_task_state_mismatch_in_a_mirror_is_detected(git_repo: Path) -> None:
    _populate(
        git_repo,
        remaining_tasks=REMAINING_TASKS.replace("FAKE-001 | Current", "FAKE-001 | Planned"),
    )
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "mismatch")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    findings = [f for f in report.findings if f.rule == "task_state_mismatch"]
    assert len(findings) == 1
    assert "FAKE-001" in findings[0].message
    assert findings[0].severity is ConsistencySeverity.ERROR


def test_too_many_current_tasks_is_detected(git_repo: Path) -> None:
    two_current = TASK_QUEUE.replace(
        "## FAKE-002 — Second task\n\nStatus: Done",
        "## FAKE-002 — Second task\n\nStatus: Current",
    )
    _populate(git_repo, task_queue=two_current)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "two current")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    rules = {finding.rule for finding in report.findings}
    assert "too_many_current_tasks" in rules


def test_version_fact_mismatch_is_detected(git_repo: Path) -> None:
    _populate(git_repo, project_state=PROJECT_STATE.replace("9.9.9", "1.2.3", 1))
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "version drift")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    rules = {finding.rule for finding in report.findings}
    assert "version_fact_mismatch" in rules


def test_project_state_vs_task_queue_contradiction_fixture(git_repo: Path) -> None:
    """The `DASH-003.md` Acceptance fixture: PROJECT_STATE.md's `## Completed` section names a
    task that `docs/TASK_QUEUE.md` still calls `Current`, a deliberate contradiction."""
    contradicting_state = PROJECT_STATE.replace(
        "- FAKE-002 (closed 2026-01-01): done.",
        "- FAKE-001 (closed 2026-01-01): done.",
    )
    _populate(git_repo, project_state=contradicting_state)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "contradiction fixture")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    findings = [f for f in report.findings if f.rule == "project_state_task_queue_contradiction"]
    assert len(findings) == 1
    assert "FAKE-001" in findings[0].message
    assert findings[0].severity is ConsistencySeverity.ERROR


def test_commit_reference_that_exists_is_not_flagged(git_repo: Path) -> None:
    _populate(git_repo)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "populate")
    head = git(git_repo, "rev-parse", "HEAD")
    _populate(git_repo, decision_log_body=f"## 2026-07-29 — Noted\n\nSee commit `{head}`.\n")
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "add decision entry")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    rules = {finding.rule for finding in report.findings}
    assert "commit_reference_unresolvable" not in rules


def test_commit_reference_that_does_not_exist_is_flagged(consistency_repo: Path) -> None:
    fake_sha = "deadbeef" * 5
    _populate(
        consistency_repo,
        decision_log_body=f"## 2026-07-29 — Noted\n\nSee commit `{fake_sha}`.\n",
    )
    git(consistency_repo, "add", "--all")
    git(consistency_repo, "commit", "--quiet", "-m", "unresolvable reference")
    report = run_consistency_checks(RepositoryRoot.from_path(consistency_repo))
    findings = [f for f in report.findings if f.rule == "commit_reference_unresolvable"]
    assert len(findings) == 1
    assert findings[0].severity is ConsistencySeverity.WARNING


def test_tampered_handover_manifest_fixture(consistency_repo: Path) -> None:
    """The `DASH-003.md` Acceptance fixture: a tampered handover manifest must be flagged."""
    write(consistency_repo, "handover/PROJECT_HANDOVER.md", HANDOVER_BODY + "tampered content\n")
    git(consistency_repo, "add", "--all")
    git(consistency_repo, "commit", "--quiet", "-m", "tamper with the handover file")
    report = run_consistency_checks(RepositoryRoot.from_path(consistency_repo))
    rules = {finding.rule for finding in report.findings}
    assert "handover_checksum_mismatch" in rules
    assert "handover_size_mismatch" in rules


def test_handover_manifest_naming_a_missing_file_is_detected(git_repo: Path) -> None:
    _populate(
        git_repo,
        manifest=_manifest_for(HANDOVER_BODY).replace(
            "handover/PROJECT_HANDOVER.md", "handover/DOES_NOT_EXIST.md"
        ),
    )
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "manifest names a missing file")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    rules = {finding.rule for finding in report.findings}
    assert "handover_file_missing" in rules


def test_orchestration_schema_findings(git_repo: Path) -> None:
    broken = IMPLEMENTATION_STATE.replace(
        "delivery_order: [ORCH-000, ORCH-001, ORCH-002]",
        "delivery_order: [ORCH-000, ORCH-001, ORCH-002, ORCH-999]",
    ).replace("current_stage: ORCH-001", "current_stage: ORCH-404")
    _populate(git_repo, implementation_state=broken)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "broken orchestration state")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    rules = {finding.rule for finding in report.findings}
    assert "orchestration_delivery_order_unknown_stage" in rules
    assert "orchestration_current_stage_unknown" in rules


def test_missing_watched_document_is_a_finding_not_a_crash(consistency_repo: Path) -> None:
    (consistency_repo / "docs" / "DECISION_LOG.md").unlink()
    git(consistency_repo, "add", "--all")
    git(consistency_repo, "commit", "--quiet", "-m", "remove decision log")
    report = run_consistency_checks(RepositoryRoot.from_path(consistency_repo))
    findings = [f for f in report.findings if f.rule == "document_missing"]
    assert any(f.sources == ("docs/DECISION_LOG.md",) for f in findings)


def test_degraded_parse_produces_a_warning_finding(git_repo: Path) -> None:
    partial_state = "Current Version: 9.9.9\n\nno sections at all\n"
    _populate(git_repo, project_state=partial_state)
    git(git_repo, "add", "--all")
    git(git_repo, "commit", "--quiet", "-m", "degraded project state")
    report = run_consistency_checks(RepositoryRoot.from_path(git_repo))
    findings = [f for f in report.findings if f.rule == "parse_degraded"]
    assert any(f.sources == ("docs/PROJECT_STATE.md",) for f in findings)
    assert all(f.severity is ConsistencySeverity.WARNING for f in findings)


def test_real_repository_handover_checksum_recomputation_matches() -> None:
    """`DASH-003.md` Acceptance: checksum recomputation must match the manifest's digest for
    the real repository, not only fixtures."""
    from agentos_dashboard.core.files import digest_file, stat_file

    real_repo = Path(__file__).resolve().parents[2]
    root = RepositoryRoot.from_path(real_repo)
    manifest_text = (real_repo / "handover" / "PROJECT_CHECKSUM.md").read_text(encoding="utf-8")
    parsed = parse_checksum_manifest(manifest_text, "handover/PROJECT_CHECKSUM.md")
    assert parsed.value is not None
    assert len(parsed.value) > 0
    for record in parsed.value:
        facts = stat_file(root, record.path)
        actual_digest = digest_file(root, record.path)
        assert facts.size_bytes == record.size, record.path
        assert actual_digest.startswith(record.digest), record.path
