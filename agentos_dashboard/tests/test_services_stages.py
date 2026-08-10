"""`services.stages`: the stage-registry loader, coded-schema cross-check, and precondition
engine (DASH-007.md Build section)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA, STAGE_SCHEMA_BY_ID
from agentos_dashboard.services.stages import (
    OPEN_QUESTIONS_PATH,
    STAGE_REGISTRY_PATH,
    build_stage_registry_view,
    evaluate_preconditions,
)
from agentos_dashboard.tests.conftest import git, write

_TARGET = STAGE_SCHEMA[1]  # DASH-002; has a real predecessor (DASH-001) to test against.
_PREDECESSOR = STAGE_SCHEMA[0]


def _registry_row(schema, state: str) -> str:
    return (
        f"| {schema.stage_id} | {schema.title} | {schema.role} | {state} | "
        f"`{schema.branch}` | `{schema.prompt_path}` |"
    )


def _registry_text(
    states: dict[str, str], *, drop: set[str] = frozenset(), extra_row: str = ""
) -> str:
    lines = [
        "## 3. Registry",
        "",
        "| Stage | Title | Role | State | Branch | Prompt |",
        "|---|---|---|---|---|---|",
    ]
    for schema in STAGE_SCHEMA:
        if schema.stage_id in drop:
            continue
        lines.append(_registry_row(schema, states.get(schema.stage_id, "NOT_STARTED")))
    if extra_row:
        lines.append(extra_row)
    lines.append("")
    lines.append("## 4. Authorization Log")
    lines.append("")
    for schema in STAGE_SCHEMA:
        lines.append(
            f'| 2026-01-01 | {schema.stage_id} | Human Owner: "I authorize '
            f'{schema.stage_id}." | Human Owner |'
        )
    lines.append("")
    lines.append("## 5. Stage map")
    return "\n".join(lines)


def _task_queue_text(stage_id: str, status: str) -> str:
    return f"## {stage_id} — Test stage\n\nStatus: {status}\n\nSome recorded detail.\n"


def _open_questions_text(body: str = "None currently open.") -> str:
    return f"## Open\n\n{body}\n\n## Resolved\n\nNone.\n"


def _seed(
    repo: Path,
    *,
    states: dict[str, str],
    task_stage_id: str,
    task_status: str,
    open_body: str = "None currently open.",
    drop: set[str] = frozenset(),
) -> None:
    write(repo, STAGE_REGISTRY_PATH, _registry_text(states, drop=drop))
    task_text = _task_queue_text(task_stage_id, task_status)
    write(repo, "docs/TASK_QUEUE.md", task_text)
    write(repo, "docs/current_task.md", task_text)
    write(repo, "docs/remaining_tasks.md", task_text)
    write(repo, OPEN_QUESTIONS_PATH, _open_questions_text(open_body))
    write(
        repo,
        "docs/agentos-dashboard/stage-prompts/README.md",
        "## Standard Stage Protocol (SSP)\n\nFollow the protocol.\n\n## Usage\n",
    )
    write(
        repo,
        (
            f"docs/agentos-dashboard/{STAGE_SCHEMA_BY_ID[task_stage_id].prompt_path}"
            if task_stage_id in STAGE_SCHEMA_BY_ID
            else "docs/agentos-dashboard/stage-prompts/DASH-999.md"
        ),
        "## Canonical Prompt\n\nDo the work.\n",
    )


def test_build_stage_registry_view_well_formed_has_no_findings(git_repo: Path) -> None:
    _seed(
        git_repo,
        states={s.stage_id: "COMPLETE" for s in STAGE_SCHEMA},
        task_stage_id="DASH-999",
        task_status="Current",
    )
    root = RepositoryRoot.from_path(git_repo)
    view = build_stage_registry_view(root)
    assert len(view.rows) == len(STAGE_SCHEMA)
    assert view.findings == ()


def test_build_stage_registry_view_reports_schema_mismatch(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    bad_row = (
        "| DASH-002 | Wrong Title | Dashboard implementation session | AUTHORIZED | "
        "`feature/dash-002-repo-adapter` | `stage-prompts/DASH-002.md` |"
    )
    text = _registry_text(states, drop={"DASH-002"}, extra_row=bad_row)
    write(git_repo, STAGE_REGISTRY_PATH, text)
    root = RepositoryRoot.from_path(git_repo)
    view = build_stage_registry_view(root)
    mismatches = [f for f in view.findings if f.rule == "stage_schema_mismatch"]
    assert any("title" in f.message for f in mismatches)


def test_build_stage_registry_view_reports_missing_row(git_repo: Path) -> None:
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text({}, drop={"DASH-005"}))
    root = RepositoryRoot.from_path(git_repo)
    view = build_stage_registry_view(root)
    assert any(
        f.rule == "stage_schema_missing_row" and "DASH-005" in f.message for f in view.findings
    )


def test_build_stage_registry_view_reports_unknown_row(git_repo: Path) -> None:
    unknown_row = (
        "| DASH-099 | Made up | Dashboard implementation session | NOT_STARTED | "
        "`feature/dash-099-x` | `stage-prompts/DASH-099.md` |"
    )
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text({}, extra_row=unknown_row))
    root = RepositoryRoot.from_path(git_repo)
    view = build_stage_registry_view(root)
    assert any(f.rule == "stage_registry_unknown_row" for f in view.findings)


def test_build_stage_registry_view_reports_duplicate_row(git_repo: Path) -> None:
    duplicate = _registry_row(_TARGET, "AUTHORIZED")
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text({}, extra_row=duplicate))
    view = build_stage_registry_view(RepositoryRoot.from_path(git_repo))
    assert any(f.rule == "stage_registry_duplicate_row" for f in view.findings)


def test_build_stage_registry_view_reports_malformed_row(git_repo: Path) -> None:
    malformed = "| DASH-099 | missing | required | cells |"
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text({}, extra_row=malformed))
    view = build_stage_registry_view(RepositoryRoot.from_path(git_repo))
    assert any(f.rule == "stage_registry_malformed_row" for f in view.findings)


def test_build_stage_registry_view_missing_document(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    view = build_stage_registry_view(root)
    assert view.rows == ()
    assert any(f.rule == "document_missing" for f in view.findings)


def test_evaluate_preconditions_unknown_stage_returns_none(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    assert evaluate_preconditions(snapshot, "NOT-A-STAGE") is None


def test_evaluate_preconditions_all_pass(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed registry")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    assert report.all_passed, report.results
    assert report.unmet == ()


def test_evaluate_preconditions_fails_without_owner_authorization(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Planned")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "owner_authorization_recorded")
    assert result.passed is False
    assert not report.all_passed


def test_evaluate_preconditions_fails_closed_on_registry_schema_divergence(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    registry = (git_repo / STAGE_REGISTRY_PATH).read_text(encoding="utf-8")
    write(git_repo, STAGE_REGISTRY_PATH, registry.replace(_TARGET.title, "Diverged title", 1))
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    report = evaluate_preconditions(
        build_snapshot(RepositoryRoot.from_path(git_repo)), _TARGET.stage_id
    )
    assert report is not None
    integrity = next(r for r in report.results if r.name == "registry_schema_consistent")
    assert integrity.passed is False
    assert not report.all_passed


def test_evaluate_preconditions_fails_when_authorization_log_is_missing(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    registry = (git_repo / STAGE_REGISTRY_PATH).read_text(encoding="utf-8")
    authorization_row = (
        f'| 2026-01-01 | {_TARGET.stage_id} | Human Owner: "I authorize '
        f'{_TARGET.stage_id}." | Human Owner |\n'
    )
    registry = registry.replace(
        authorization_row,
        "",
    )
    write(git_repo, STAGE_REGISTRY_PATH, registry)
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    report = evaluate_preconditions(
        build_snapshot(RepositoryRoot.from_path(git_repo)), _TARGET.stage_id
    )
    assert report is not None
    authorization = next(r for r in report.results if r.name == "owner_authorization_recorded")
    assert authorization.passed is False


def test_evaluate_preconditions_refuses_registry_blocked_stage(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "BLOCKED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    report = evaluate_preconditions(
        build_snapshot(RepositoryRoot.from_path(git_repo)), _TARGET.stage_id
    )
    assert report is not None
    authorization = next(r for r in report.results if r.name == "owner_authorization_recorded")
    assert authorization.passed is False
    assert "registry_state=BLOCKED" in authorization.detail


def test_evaluate_preconditions_fails_closed_on_duplicate_task_record(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    queue_path = git_repo / "docs/TASK_QUEUE.md"
    queue = queue_path.read_text(encoding="utf-8")
    write(git_repo, "docs/TASK_QUEUE.md", queue + "\n" + queue)
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    report = evaluate_preconditions(
        build_snapshot(RepositoryRoot.from_path(git_repo)), _TARGET.stage_id
    )
    assert report is not None
    authorization = next(r for r in report.results if r.name == "owner_authorization_recorded")
    assert authorization.passed is False
    assert "queue_stage_unambiguous=False" in authorization.detail


def test_evaluate_preconditions_fails_when_predecessor_not_complete(git_repo: Path) -> None:
    states = {s.stage_id: "NOT_STARTED" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "predecessor_complete")
    assert result.passed is False
    assert _PREDECESSOR.stage_id in result.detail


def test_evaluate_preconditions_fails_when_predecessor_was_superseded(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_PREDECESSOR.stage_id] = "SUPERSEDED"
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    report = evaluate_preconditions(
        build_snapshot(RepositoryRoot.from_path(git_repo)), _TARGET.stage_id
    )
    assert report is not None
    predecessor = next(r for r in report.results if r.name == "predecessor_complete")
    assert predecessor.passed is False
    assert "SUPERSEDED" in predecessor.detail


def test_evaluate_preconditions_fails_on_wrong_branch(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    # Stay on `main` instead of checking out `_TARGET.branch`.

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "correct_branch")
    assert result.passed is False


def test_evaluate_preconditions_fails_on_dirty_tree(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(git_repo, states=states, task_stage_id=_TARGET.stage_id, task_status="Current")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)
    write(git_repo, "dirty.txt", "uncommitted\n")

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "clean_tree")
    assert result.passed is False


def test_evaluate_preconditions_fails_when_open_question_blocks_the_stage(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    _seed(
        git_repo,
        states=states,
        task_stage_id=_TARGET.stage_id,
        task_status="Current",
        open_body=f"### OD-D99 — A blocker\n- **Question:** x\n- **Blocked:** {_TARGET.stage_id}",
    )
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "blocking_open_questions_resolved")
    assert result.passed is False


def test_evaluate_preconditions_passes_when_open_question_blocks_a_different_stage(
    git_repo: Path,
) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    other_stage = STAGE_SCHEMA[-1].stage_id
    _seed(
        git_repo,
        states=states,
        task_stage_id=_TARGET.stage_id,
        task_status="Current",
        open_body=f"### OD-D99 — A blocker\n- **Question:** x\n- **Blocked:** {other_stage}",
    )
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "blocking_open_questions_resolved")
    assert result.passed is True


def test_evaluate_preconditions_fails_when_open_questions_missing_entirely(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text(states))
    write(git_repo, "docs/TASK_QUEUE.md", _task_queue_text(_TARGET.stage_id, "Current"))
    # No OPEN_QUESTIONS.md at all: fail-closed.
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "blocking_open_questions_resolved")
    assert result.passed is False


def test_evaluate_preconditions_fails_on_sole_active_invariant(git_repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text(states))
    write(
        git_repo,
        "docs/TASK_QUEUE.md",
        _task_queue_text(_TARGET.stage_id, "Current") + "\n" + _task_queue_text("GOV-1", "Current"),
    )
    write(git_repo, OPEN_QUESTIONS_PATH, _open_questions_text())
    write(git_repo, "docs/current_task.md", _task_queue_text(_TARGET.stage_id, "Current"))
    write(
        git_repo,
        "docs/remaining_tasks.md",
        _task_queue_text(_TARGET.stage_id, "Current") + "\n" + _task_queue_text("GOV-1", "Current"),
    )
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "--quiet", "-m", "seed")
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    report = evaluate_preconditions(snapshot, _TARGET.stage_id)
    assert report is not None
    result = next(r for r in report.results if r.name == "sole_active_invariant")
    assert result.passed is False
