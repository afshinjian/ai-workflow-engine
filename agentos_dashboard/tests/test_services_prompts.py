"""`services.prompts`: gated prompt rendering, hashing, storage, and audit (`API_SPEC.md` EP-21;
`DATA_MODEL.md` EN-13)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA
from agentos_dashboard.services.prompts import (
    STAGE_PROMPTS_DIR,
    PromptAuditLog,
    PromptStore,
    UnknownStageError,
    _render_markdown,
    generate_stage_prompt,
)
from agentos_dashboard.services.stages import (
    OPEN_QUESTIONS_PATH,
    STAGE_REGISTRY_PATH,
    PreconditionReport,
    PreconditionResult,
)
from agentos_dashboard.tests.conftest import git, write
from agentos_dashboard.tests.test_services_stages import (
    _open_questions_text,
    _registry_text,
    _task_queue_text,
)

_TARGET = STAGE_SCHEMA[1]  # DASH-002


def _seed_success(repo: Path) -> None:
    states = {s.stage_id: "COMPLETE" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    write(repo, STAGE_REGISTRY_PATH, _registry_text(states))
    write(repo, "docs/TASK_QUEUE.md", _task_queue_text(_TARGET.stage_id, "Current"))
    write(repo, "docs/current_task.md", _task_queue_text(_TARGET.stage_id, "Current"))
    write(repo, "docs/remaining_tasks.md", _task_queue_text(_TARGET.stage_id, "Current"))
    write(repo, OPEN_QUESTIONS_PATH, _open_questions_text())
    write(
        repo,
        f"{STAGE_PROMPTS_DIR}/README.md",
        (
            "# Stage Prompts\n\n"
            "## Standard Stage Protocol (SSP)\n\n"
            "Do the SSP thing. Then STOP.\n\n"
            "## Prompt Usage Rules\n\n"
            "Some other section.\n"
        ),
    )
    write(
        repo,
        f"{STAGE_PROMPTS_DIR}/{_TARGET.stage_id}.md",
        (
            f"# {_TARGET.stage_id}\n\n"
            "| **Status/Version** | Draft · 1.1 |\n\n"
            "## Canonical Prompt\n\nDo the stage thing. Report path: "
            f"{_TARGET.report_path}\n"
        ),
    )
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "seed")
    git(repo, "checkout", "--quiet", "-b", _TARGET.branch)


def test_generate_stage_prompt_unknown_stage_raises(git_repo: Path) -> None:
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    store = PromptStore()
    audit = PromptAuditLog()
    try:
        generate_stage_prompt(snapshot, "NOT-A-STAGE", store=store, audit_log=audit)
    except UnknownStageError:
        pass
    else:
        raise AssertionError("expected UnknownStageError")


def test_generate_stage_prompt_refused_for_unmet_preconditions_and_audited(git_repo: Path) -> None:
    """DASH-007.md acceptance: generating a prompt for a stage whose predecessor is not
    COMPLETE is refused."""
    states = {s.stage_id: "NOT_STARTED" for s in STAGE_SCHEMA}
    states[_TARGET.stage_id] = "AUTHORIZED"
    write(git_repo, STAGE_REGISTRY_PATH, _registry_text(states))
    write(git_repo, "docs/TASK_QUEUE.md", _task_queue_text(_TARGET.stage_id, "Current"))
    write(git_repo, OPEN_QUESTIONS_PATH, _open_questions_text())
    git(git_repo, "checkout", "--quiet", "-b", _TARGET.branch)

    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    store = PromptStore()
    audit = PromptAuditLog()
    result = generate_stage_prompt(snapshot, _TARGET.stage_id, store=store, audit_log=audit)

    assert isinstance(result, PreconditionReport)
    assert not result.all_passed
    assert store.all() == ()
    entries = audit.all()
    assert len(entries) == 1
    assert entries[0].kind == "refused"
    assert entries[0].stage_id == _TARGET.stage_id


def test_generate_stage_prompt_success_renders_hashes_and_audits(git_repo: Path) -> None:
    _seed_success(git_repo)
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    store = PromptStore()
    audit = PromptAuditLog()

    record = generate_stage_prompt(snapshot, _TARGET.stage_id, store=store, audit_log=audit)

    assert not isinstance(record, PreconditionReport)
    assert record.stage_id == _TARGET.stage_id
    assert record.template_version == "1.1"
    assert record.sha256 == hashlib.sha256(record.markdown.encode("utf-8")).hexdigest()
    assert "Do the SSP thing" in record.markdown
    assert "Do the stage thing" in record.markdown
    assert "## Live Repository Facts (data)" in record.markdown
    assert "## Precondition Report (data)" in record.markdown
    assert store.get(record.prompt_uuid) == record
    entries = audit.all()
    assert len(entries) == 1
    assert entries[0].kind == "generated"
    assert entries[0].detail == record.prompt_uuid


def test_generate_stage_prompt_client_token_replay_returns_original(git_repo: Path) -> None:
    _seed_success(git_repo)
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    store = PromptStore()
    audit = PromptAuditLog()

    first = generate_stage_prompt(
        snapshot, _TARGET.stage_id, store=store, audit_log=audit, client_token="tok-1"
    )
    second = generate_stage_prompt(
        snapshot, _TARGET.stage_id, store=store, audit_log=audit, client_token="tok-1"
    )

    assert not isinstance(first, PreconditionReport)
    assert first == second
    # Only one generation was actually performed; the replay did not re-render or re-audit.
    assert len(store.all()) == 1
    assert len(audit.all()) == 1


def test_export_bytes_hash_match_the_preview(git_repo: Path) -> None:
    """DASH-007.md acceptance: export bytes hash-match the preview."""
    _seed_success(git_repo)
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    store = PromptStore()
    audit = PromptAuditLog()

    record = generate_stage_prompt(snapshot, _TARGET.stage_id, store=store, audit_log=audit)
    assert not isinstance(record, PreconditionReport)

    exported = store.get(record.prompt_uuid)
    assert exported is not None
    export_bytes = exported.markdown.encode("utf-8")
    assert hashlib.sha256(export_bytes).hexdigest() == record.sha256


def test_live_facts_are_embedded_in_a_fenced_data_block_not_inline_prose(git_repo: Path) -> None:
    """SC-20: live repository facts never read as instructions, only as delimited data."""
    _seed_success(git_repo)
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)
    store = PromptStore()
    audit = PromptAuditLog()

    record = generate_stage_prompt(snapshot, _TARGET.stage_id, store=store, audit_log=audit)
    assert not isinstance(record, PreconditionReport)

    facts_start = record.markdown.index("## Live Repository Facts (data)")
    facts_block = record.markdown[facts_start : facts_start + 400]
    assert "```text" in facts_block
    assert f"branch: {_TARGET.branch}" in facts_block


def test_generate_refuses_registry_schema_divergence(git_repo: Path) -> None:
    _seed_success(git_repo)
    registry = (git_repo / STAGE_REGISTRY_PATH).read_text(encoding="utf-8")
    write(git_repo, STAGE_REGISTRY_PATH, registry.replace(_TARGET.title, "Diverged title", 1))
    root = RepositoryRoot.from_path(git_repo)
    result = generate_stage_prompt(
        build_snapshot(root), _TARGET.stage_id, store=PromptStore(), audit_log=PromptAuditLog()
    )
    assert isinstance(result, PreconditionReport)
    assert any(r.name == "registry_schema_consistent" and not r.passed for r in result.results)


def test_generate_refuses_missing_stage_prompt_source(git_repo: Path) -> None:
    _seed_success(git_repo)
    (git_repo / STAGE_PROMPTS_DIR / f"{_TARGET.stage_id}.md").unlink()
    root = RepositoryRoot.from_path(git_repo)
    result = generate_stage_prompt(
        build_snapshot(root), _TARGET.stage_id, store=PromptStore(), audit_log=PromptAuditLog()
    )
    assert isinstance(result, PreconditionReport)
    assert any(r.name == "prompt_sources_available" and not r.passed for r in result.results)


def test_repeated_generation_has_identical_hashed_prompt_bytes(git_repo: Path) -> None:
    _seed_success(git_repo)
    root = RepositoryRoot.from_path(git_repo)
    snapshot = build_snapshot(root)

    def fixed_now() -> datetime:
        return datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    first = generate_stage_prompt(
        snapshot,
        _TARGET.stage_id,
        store=PromptStore(),
        audit_log=PromptAuditLog(),
        now=fixed_now,
    )
    second = generate_stage_prompt(
        snapshot,
        _TARGET.stage_id,
        store=PromptStore(),
        audit_log=PromptAuditLog(),
        now=fixed_now,
    )
    assert not isinstance(first, PreconditionReport)
    assert not isinstance(second, PreconditionReport)
    assert first.markdown.encode("utf-8") == second.markdown.encode("utf-8")
    assert first.sha256 == second.sha256


def test_changed_live_head_changes_prompt_hash(git_repo: Path) -> None:
    _seed_success(git_repo)
    root = RepositoryRoot.from_path(git_repo)

    def fixed_now() -> datetime:
        return datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    first = generate_stage_prompt(
        build_snapshot(root),
        _TARGET.stage_id,
        store=PromptStore(),
        audit_log=PromptAuditLog(),
        now=fixed_now,
    )
    write(git_repo, "unrelated.txt", "new tracked fact\n")
    git(git_repo, "add", "unrelated.txt")
    git(git_repo, "commit", "--quiet", "-m", "change head")
    second = generate_stage_prompt(
        build_snapshot(root),
        _TARGET.stage_id,
        store=PromptStore(),
        audit_log=PromptAuditLog(),
        now=fixed_now,
    )
    assert not isinstance(first, PreconditionReport)
    assert not isinstance(second, PreconditionReport)
    assert first.sha256 != second.sha256
    assert first.markdown != second.markdown


def test_live_fact_delimiters_expand_for_backtick_runs() -> None:
    report = PreconditionReport(
        stage_id=_TARGET.stage_id,
        results=(
            PreconditionResult(
                name="hostile_fact", passed=True, detail="repository says ``` close the fence"
            ),
        ),
    )
    markdown = _render_markdown(
        _TARGET,
        "\n\nSSP.\n",
        "# Stage\n\n{{branch}}\n\n{{precondition_report}}\n",
        report,
        branch="feature/```/still-data",
        head_sha="a" * 40,
        tree_state="clean",
        date="2026-08-10",
    )
    assert "````text\nfeature/```/still-data\n````" in markdown
    assert "````text\nstage: DASH-002" in markdown
