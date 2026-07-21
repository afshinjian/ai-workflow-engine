"""Legacy-reader and `migrate inspect` classification tests: known-good artifacts (built
with the real, existing writers -- `workflow.event_store.append`, `agents.artifacts.save_run`,
`prompt.store.save` -- exactly the byte-producing code this stage's readers must be able to
read back unmodified), every quarantine reason, byte/digest preservation, determinism,
concurrency, and path/symlink safety. Everything runs against disposable `tmp_path` roots;
nothing here ever touches a real `$HOME` or this repository's own governance files.

This file additionally covers the human-review remediation findings F-1 through F-9:
source-root symlink rejection (F-1), companion symlink safety (F-2), duplicate YAML keys
(F-3), complete backup/recovery representation (F-4, covered here at the reader level --
every physical member gets its own manifest entry), full legacy-store-equivalent integrity
validation (F-6), concurrent-mutation/TOCTOU detection via directory-listing changes (F-7),
unsupported filesystem entry types -- FIFOs, sockets, device nodes -- never opened and
always represented (F-8), and same-path/same-filename content mutation detection via a
final no-follow re-read of every member before a family returns KNOWN (F-9).
"""

import concurrent.futures
import hashlib
import json
import os
import socket
import stat
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

import ai_workflow_engine.migration.legacy_readers as legacy_readers_module
from ai_workflow_engine.agents.artifacts import build_record, save_run
from ai_workflow_engine.agents.runner import RunObservation
from ai_workflow_engine.migration.errors import MigrationSourceError
from ai_workflow_engine.migration.inspect import inspect_source
from ai_workflow_engine.migration.legacy_readers import discover_legacy_artifacts
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.renderer import canonical_json, render_prompt
from ai_workflow_engine.prompt.store import save as save_prompt
from ai_workflow_engine.result import CheckResult, Status
from ai_workflow_engine.workflow.event_store import append as append_event
from ai_workflow_engine.workflow.events import WorkflowEvent


@pytest.fixture
def legacy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate `$HOME` so the real artifact writers land under a disposable directory;
    returns the resulting legacy-artifact source root (`~/.ai-workflow-engine/workflow-runs`).
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home / ".ai-workflow-engine" / "workflow-runs"


def _repo_stub(tmp_path: Path) -> Path:
    """A directory distinct from the artifact root, only used for the writers' own
    repository-containment check -- it need not be a real git repository.
    """
    stub = tmp_path / "not-the-repo"
    stub.mkdir(exist_ok=True)
    return stub


def _write_known_workflow_history(
    tmp_path: Path, *, project_id: str = "proj", task_id: str = "task-1", events: int = 2
) -> None:
    """A valid, chained history starting at plan-review/APPROVED, matching the real
    transition table (`workflow.transitions`), exactly as `record_outcome` would produce.
    """
    repository = str(_repo_stub(tmp_path))
    previous_raw: bytes | None = None
    stage_sequence = [("plan-review", "verdict", "APPROVED")] + [
        ("implementation", "completed", None) for _ in range(max(0, events - 1))
    ]
    for index, (stage, action, verdict) in enumerate(stage_sequence[:events], start=1):
        parent_digest = None if previous_raw is None else hashlib.sha256(previous_raw).hexdigest()
        event = WorkflowEvent(
            schema_version="1.0",
            project_id=project_id,
            task_id=task_id,
            sequence=index,
            parent_digest=parent_digest,
            stage=stage,  # type: ignore[arg-type]
            action=action,  # type: ignore[arg-type]
            verdict=verdict,  # type: ignore[arg-type]
            prompt_id=None,
            agent_run_id=None,
            head="a" * 40,
            note="",
        )
        append_event(event, repository=repository)
        previous_raw = canonical_json(event.model_dump(mode="json")) + b"\n"


def _write_known_agent_run(tmp_path: Path, *, project_id: str = "proj") -> str:
    observation = RunObservation(
        agent_name="stub",
        agent_mode="read-only",
        agent_executable="/bin/true",
        agent_args=[],
        timeout_seconds=60,
        task_id="task-1",
        stage="plan-review",
        prompt_id="deadbeefdeadbeef",
        repository_head="b" * 40,
        ok=True,
        failure_code=None,
        report=None,
        exit_code=0,
        stdout=b"",
        stderr=b"",
        patch=b"diff --git a/x b/x\n+hello\n",
    )
    verification = CheckResult(
        check_name="agent-run",
        status=Status.PASS,
        summary="ok",
        findings=[],
        evidence={},
        affected_paths=[],
        remediation_hint=None,
    )
    record, patch = build_record(observation, verification, project_id=project_id)
    save_run(record, patch, repository=str(_repo_stub(tmp_path)))
    return record.run_id


def _write_known_prompt_metadata(repository: Path, config_factory: Callable[[Path], Path]) -> None:
    from ai_workflow_engine.config import load_config

    config_path = config_factory(repository)
    settings = load_config(config_path)
    context = build_prompt_context(
        settings, stage="plan-review", task_id="T-1", allowed_paths=[], remediation_findings=[]
    )
    rendered = render_prompt(context)
    save_prompt(rendered)


def _write_known_approval(root: Path, name: str, *, kind: str = "commit") -> None:
    (root / "approvals").mkdir(parents=True, exist_ok=True)
    if kind == "commit":
        content = {
            "kind": "commit",
            "task_id": "T-1",
            "branch": "main",
            "head": "c" * 40,
            "allowed_paths": ["src/x.py"],
            "message": "msg",
            "approved_by": "a@b.c",
        }
    else:
        content = {
            "kind": "push",
            "task_id": "T-1",
            "branch": "main",
            "head": "c" * 40,
            "upstream": "origin/main",
            "approved_by": "a@b.c",
        }
    (root / "approvals" / name).write_text(yaml.safe_dump(content), encoding="utf-8")


# --- known legacy artifact inspection (built by the real, existing writers) ----------------


def test_known_workflow_history_is_classified_known(legacy_home: Path, tmp_path: Path) -> None:
    _write_known_workflow_history(tmp_path, events=2)
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "KNOWN" and r.kind == "workflow-event" for r in records)
    assert all(r.schema_version == "1.0" for r in records)


def test_known_agent_run_pair_is_classified_known_with_both_members(
    legacy_home: Path, tmp_path: Path
) -> None:
    run_id = _write_known_agent_run(tmp_path)
    records = discover_legacy_artifacts(legacy_home)
    # F-4: both physical members (the .json primary and the .patch companion) are their
    # own manifest entries now -- neither is folded away invisibly.
    assert len(records) == 2
    by_kind = {r.kind: r for r in records}
    assert by_kind["agent-run-record"].classification == "KNOWN"
    assert by_kind["agent-run-record"].relative_path.endswith(f"{run_id}.json")
    assert by_kind["agent-run-patch"].classification == "KNOWN"
    assert by_kind["agent-run-patch"].relative_path.endswith(f"{run_id}.patch")


def test_known_prompt_pair_is_classified_known_with_both_members(
    legacy_home: Path, repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    by_kind = {r.kind: r for r in records}
    assert by_kind["prompt-metadata"].classification == "KNOWN"
    assert by_kind["prompt-metadata"].schema_version == "1.1"
    assert by_kind["prompt-markdown"].classification == "KNOWN"
    assert by_kind["prompt-markdown"].schema_version == "1.1"


def test_known_commit_and_push_approvals_are_classified_known(legacy_home: Path) -> None:
    legacy_home.mkdir(parents=True)
    _write_known_approval(legacy_home, "a.yaml", kind="commit")
    _write_known_approval(legacy_home, "b.yaml", kind="push")
    records = discover_legacy_artifacts(legacy_home)
    kinds = sorted((r.relative_path, r.kind) for r in records)
    assert kinds == [("approvals/a.yaml", "commit-approval"), ("approvals/b.yaml", "push-approval")]
    assert all(r.classification == "KNOWN" for r in records)


# --- exact byte and SHA-256 preservation ----------------------------------------------------


def test_inspect_preserves_legacy_bytes_and_digest_exactly(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_workflow_history(tmp_path, events=1)
    [target] = list(legacy_home.rglob("*.json"))
    before_bytes = target.read_bytes()
    before_digest = hashlib.sha256(before_bytes).hexdigest()

    manifest = inspect_source(legacy_home, to_version="2.0.0")

    after_bytes = target.read_bytes()
    assert after_bytes == before_bytes, "inspect must never rewrite a legacy artifact"
    [record] = manifest.artifacts
    assert record.sha256 == before_digest
    assert record.sha256 == hashlib.sha256(after_bytes).hexdigest()


# --- unsupported schema name/version --------------------------------------------------------


def test_unsupported_migration_target_fails_closed(legacy_home: Path) -> None:
    legacy_home.mkdir(parents=True)
    from ai_workflow_engine.migration.errors import UnsupportedMigrationTargetError

    with pytest.raises(UnsupportedMigrationTargetError):
        inspect_source(legacy_home, to_version="9.9.9")


def test_artifact_with_unsupported_embedded_schema_version_is_quarantined(
    legacy_home: Path,
) -> None:
    directory = legacy_home / "state" / "proj" / "task"
    directory.mkdir(parents=True)
    payload = {
        "schema_version": "0.9",  # not the supported "1.0"
        "project_id": "proj",
        "task_id": "task",
        "sequence": 1,
        "parent_digest": None,
        "stage": "plan-review",
        "action": "verdict",
        "verdict": "APPROVED",
        "prompt_id": None,
        "agent_run_id": None,
        "head": "a" * 40,
        "note": "",
    }
    (directory / "00000001.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "UNSUPPORTED_SCHEMA_VERSION"


# --- mixed-version input rejected/quarantined (independent histories classified separately) -


def test_mixed_version_siblings_are_individually_classified(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_workflow_history(tmp_path, task_id="task-good", events=1)
    bad_dir = legacy_home / "state" / "proj" / "task-bad"
    bad_dir.mkdir(parents=True)
    payload = {
        "schema_version": "2.0",
        "project_id": "proj",
        "task_id": "task-bad",
        "sequence": 1,
        "parent_digest": None,
        "stage": "plan-review",
        "action": "verdict",
        "verdict": "APPROVED",
        "prompt_id": None,
        "agent_run_id": None,
        "head": "a" * 40,
        "note": "",
    }
    (bad_dir / "00000001.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    manifest = inspect_source(legacy_home, to_version="2.0.0")
    assert manifest.known_count == 1
    assert manifest.quarantined_count == 1
    reasons = {a.relative_path: a.quarantine_reason for a in manifest.artifacts}
    assert reasons["state/proj/task-bad/00000001.json"] == "UNSUPPORTED_SCHEMA_VERSION"


# --- malformed and corrupt artifact quarantine ----------------------------------------------


def test_invalid_utf8_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "00000001.json").write_bytes(b"\xff\xfe\x00\x01\n")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "NOT_VALID_UTF8"


def test_invalid_json_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "00000001.json").write_text("not json at all\n", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "NOT_VALID_JSON"


def test_duplicate_json_key_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "00000001.json").write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}\n', encoding="utf-8"
    )
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "DUPLICATE_JSON_KEY"


def test_schema_validation_failure_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    # Valid JSON, correct schema_version, but missing every other required field.
    (directory / "00000001.json").write_text('{"schema_version":"1.0"}\n', encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "SCHEMA_VALIDATION_FAILED"


def test_non_object_json_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "00000001.json").write_text("[1, 2, 3]\n", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "SCHEMA_VALIDATION_FAILED"


def test_missing_terminal_newline_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "00000001.json").write_text('{"schema_version":"1.0"}', encoding="utf-8")  # no \n
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "CANONICAL_FORM_MISMATCH"


def test_non_canonical_bytes_quarantine_the_whole_history(
    legacy_home: Path, tmp_path: Path
) -> None:
    """F-6: canonical-form is verified byte-for-byte, not just schema-validity."""
    _write_known_workflow_history(tmp_path, events=2)
    [target] = sorted(legacy_home.rglob("00000001.json"))
    # Same content, different (still valid) JSON formatting -- not canonical.
    parsed = json.loads(target.read_bytes())
    target.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "CANONICAL_FORM_MISMATCH" for r in records)


def test_invalid_yaml_approval_is_quarantined(legacy_home: Path) -> None:
    (legacy_home / "approvals").mkdir(parents=True)
    (legacy_home / "approvals" / "broken.yaml").write_text("kind: [unterminated", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "NOT_VALID_YAML"


def test_unknown_approval_kind_is_quarantined_not_guessed(legacy_home: Path) -> None:
    (legacy_home / "approvals").mkdir(parents=True)
    (legacy_home / "approvals" / "weird.yaml").write_text(
        "kind: rollback\nfoo: bar\n", encoding="utf-8"
    )
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "UNKNOWN_APPROVAL_KIND"


def test_unknown_top_level_directory_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "mystery"
    directory.mkdir(parents=True)
    (directory / "file.json").write_text("{}", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "UNKNOWN_TOP_LEVEL_DIRECTORY"


def test_unknown_file_extension_under_known_directory_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("hello", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "UNKNOWN_FILE_EXTENSION"


def test_unexpected_agent_run_path_depth_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "agent-runs" / "p"  # missing task_dir/stage components
    directory.mkdir(parents=True)
    (directory / "x.json").write_text("{}", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "UNEXPECTED_PATH_STRUCTURE"


def test_orphan_patch_companion_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "agent-runs" / "p" / "t" / "plan-review"
    directory.mkdir(parents=True)
    (directory / "deadbeefdeadbeef.patch").write_bytes(b"diff\n")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "ORPHAN_COMPANION_FILE"


def test_orphan_markdown_companion_is_quarantined(legacy_home: Path) -> None:
    directory = legacy_home / "prompts" / "p" / "plan-review"
    directory.mkdir(parents=True)
    (directory / "deadbeefdeadbeef.md").write_text("# hi", encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "ORPHAN_COMPANION_FILE"


def test_missing_patch_companion_downgrades_primary_to_quarantined(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_agent_run(tmp_path)
    [patch_path] = list(legacy_home.rglob("*.patch"))
    patch_path.unlink()
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "MISSING_COMPANION_MEMBER"


def test_patch_digest_mismatch_quarantines_both_members(legacy_home: Path, tmp_path: Path) -> None:
    _write_known_agent_run(tmp_path)
    [patch_path] = list(legacy_home.rglob("*.patch"))
    patch_path.write_bytes(b"corrupted, does not match patch_sha256\n")
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "COMPANION_DIGEST_MISMATCH" for r in records)


def test_missing_markdown_companion_downgrades_prompt_to_quarantined(
    legacy_home: Path, repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    [markdown_path] = list(legacy_home.rglob("*.md"))
    markdown_path.unlink()
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "MISSING_COMPANION_MEMBER"


# --- F-6: full legacy-store-equivalent integrity validation --------------------------------


def test_agent_run_relocated_to_a_different_stage_directory_is_address_mismatch(
    legacy_home: Path, tmp_path: Path
) -> None:
    """The record's own content (and therefore its content-hash-derived run_id) is left
    completely untouched; only its physical location changes -- isolating an address
    mismatch from a content-hash mismatch.
    """
    _write_known_agent_run(tmp_path)
    [json_path] = list(legacy_home.rglob("*.json"))
    [patch_path] = list(legacy_home.rglob("*.patch"))
    new_dir = json_path.parent.parent / "governance-review"
    new_dir.mkdir()
    new_json = new_dir / json_path.name
    new_patch = new_dir / patch_path.name
    new_json.write_bytes(json_path.read_bytes())
    new_patch.write_bytes(patch_path.read_bytes())
    json_path.unlink()
    patch_path.unlink()

    records = [
        r for r in discover_legacy_artifacts(legacy_home) if r.relative_path.endswith(".json")
    ]
    [record] = records
    assert record.quarantine_reason == "ADDRESS_MISMATCH"


def test_agent_run_with_tampered_run_id_is_content_hash_mismatch(
    legacy_home: Path, tmp_path: Path
) -> None:
    """Renaming both members to a run_id that no longer matches the record's own content
    hash must be caught -- run_id is a content hash, not just a filename label.
    """
    _write_known_agent_run(tmp_path)
    [json_path] = list(legacy_home.rglob("*.json"))
    [patch_path] = list(legacy_home.rglob("*.patch"))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    fake_run_id = ("f" * 16) if payload["run_id"][0] != "f" else ("e" * 16)
    payload["run_id"] = fake_run_id
    from ai_workflow_engine.prompt.renderer import canonical_json as _cj

    new_json = json_path.parent / f"{fake_run_id}.json"
    new_patch = json_path.parent / f"{fake_run_id}.patch"
    new_json.write_bytes(_cj(payload) + b"\n")
    new_patch.write_bytes(patch_path.read_bytes())
    json_path.unlink()
    patch_path.unlink()
    records = discover_legacy_artifacts(legacy_home)
    json_record = next(r for r in records if r.relative_path.endswith(".json"))
    assert json_record.quarantine_reason == "CONTENT_HASH_MISMATCH"


def test_agent_run_stdout_digest_mismatch_is_content_hash_mismatch(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_agent_run(tmp_path)
    [json_path] = list(legacy_home.rglob("*.json"))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["stdout_sha256"] = "0" * 64  # no longer matches decoded stdout_b64
    from ai_workflow_engine.prompt.renderer import canonical_json as _cj

    json_path.write_bytes(_cj(payload) + b"\n")
    [record] = [
        r for r in discover_legacy_artifacts(legacy_home) if r.relative_path.endswith(".json")
    ]
    assert record.quarantine_reason == "CONTENT_HASH_MISMATCH"


def test_prompt_metadata_with_wrong_prompt_id_path_is_address_mismatch(
    legacy_home: Path, repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    [json_path] = list(legacy_home.rglob("*.json"))
    new_json = json_path.parent / ("0" * 16 + ".json")
    json_path.rename(new_json)
    [record] = [
        r for r in discover_legacy_artifacts(legacy_home) if r.relative_path.endswith(".json")
    ]
    assert record.quarantine_reason == "ADDRESS_MISMATCH"


def test_prompt_markdown_altered_from_deterministic_rendering_is_digest_mismatch(
    legacy_home: Path, repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    [md_path] = list(legacy_home.rglob("*.md"))
    md_path.write_text(md_path.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
    records = discover_legacy_artifacts(legacy_home)
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "COMPANION_DIGEST_MISMATCH" for r in records)


def test_workflow_history_with_wrong_stage_order_quarantines_whole_history(
    legacy_home: Path, tmp_path: Path
) -> None:
    """A single corrupt member must quarantine every member of the history, never just
    the offending one, even when the other members look independently valid (F-6).
    """
    _write_known_workflow_history(tmp_path, events=2)
    [second] = sorted(legacy_home.rglob("00000002.json"))
    payload = json.loads(second.read_bytes())
    payload["stage"] = "governance-review"  # not the expected next stage after event 1
    payload["action"] = "verdict"
    payload["verdict"] = "APPROVED"
    from ai_workflow_engine.prompt.renderer import canonical_json as _cj

    second.write_bytes(_cj(payload) + b"\n")
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "WORKFLOW_HISTORY_INTEGRITY_FAILED" for r in records)
    # The first event, read in isolation, is perfectly valid -- it is only quarantined
    # because it shares a history with the corrupt second event.
    first_detail = next(r for r in records if r.relative_path.endswith("00000001.json"))
    assert "00000002.json" in first_detail.quarantine_detail


def test_workflow_history_with_broken_parent_digest_chain_quarantines_whole_history(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_workflow_history(tmp_path, events=2)
    [second] = sorted(legacy_home.rglob("00000002.json"))
    payload = json.loads(second.read_bytes())
    payload["parent_digest"] = "0" * 64
    from ai_workflow_engine.prompt.renderer import canonical_json as _cj

    second.write_bytes(_cj(payload) + b"\n")
    records = discover_legacy_artifacts(legacy_home)
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "WORKFLOW_HISTORY_INTEGRITY_FAILED" for r in records)


def test_workflow_history_non_contiguous_filenames_quarantines_whole_history(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_workflow_history(tmp_path, events=2)
    [second] = sorted(legacy_home.rglob("00000002.json"))
    second.rename(second.parent / "00000009.json")
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "WORKFLOW_HISTORY_INTEGRITY_FAILED" for r in records)


def test_workflow_history_task_dir_hash_mismatch_is_address_mismatch(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "proj" / "not-the-real-hash-suffix"
    directory.mkdir(parents=True)
    event = WorkflowEvent(
        schema_version="1.0",
        project_id="proj",
        task_id="task-1",
        sequence=1,
        parent_digest=None,
        stage="plan-review",
        action="verdict",
        verdict="APPROVED",
        prompt_id=None,
        agent_run_id=None,
        head="a" * 40,
        note="",
    )
    (directory / "00000001.json").write_bytes(canonical_json(event.model_dump(mode="json")) + b"\n")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "ADDRESS_MISMATCH"


# --- symlink and external-path safety (F-1, F-2) ---------------------------------------------


def test_symlink_is_quarantined_and_never_followed(legacy_home: Path, tmp_path: Path) -> None:
    secret = tmp_path / "outside-root-secret.txt"
    secret.write_text("do not read me", encoding="utf-8")
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    link = directory / "00000001.json"
    link.symlink_to(secret)

    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "SYMLINK_NOT_ALLOWED"
    assert record.entry_type == "symlink"
    # The digest is of the symlink's target string, never of the pointed-to file's content.
    assert record.sha256 != hashlib.sha256(secret.read_bytes()).hexdigest()
    assert "do not read me" not in record.quarantine_detail


def test_symlinked_directory_is_quarantined_and_never_descended(
    legacy_home: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (outside / "secret.json").write_text("{}", encoding="utf-8")
    legacy_home.mkdir(parents=True)
    (legacy_home / "state").symlink_to(outside)

    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 1
    assert records[0].quarantine_reason == "SYMLINK_NOT_ALLOWED"
    assert records[0].relative_path == "state"


def test_source_root_itself_a_symlink_is_rejected_without_scanning_target(
    legacy_home: Path, tmp_path: Path
) -> None:
    """F-1: a symlinked source root is refused outright -- its target directory is never
    listed. Proven by monkeypatching `os.scandir` to raise if it is ever invoked.
    """
    secret_target = tmp_path / "secret-target"
    secret_target.mkdir()
    (secret_target / "state").mkdir()
    (secret_target / "state" / "secret.json").write_text("do not read", encoding="utf-8")

    link_root = tmp_path / "legacy-symlink-root"
    link_root.symlink_to(secret_target)

    import os as os_module

    original_scandir = os_module.scandir

    def _guard(*args: object, **kwargs: object) -> object:
        raise AssertionError("os.scandir must never be called for a symlink source root")

    os_module.scandir = _guard  # type: ignore[assignment]
    try:
        with pytest.raises(MigrationSourceError, match="symlink"):
            discover_legacy_artifacts(link_root)
    finally:
        os_module.scandir = original_scandir


def test_source_root_symlink_via_cli_inspect_never_reads_target(tmp_path: Path) -> None:
    import os as os_module
    import subprocess
    import sys

    secret_target = tmp_path / "secret-target"
    secret_target.mkdir()
    (secret_target / "state").mkdir()
    (secret_target / "state" / "leak.json").write_text("SECRET_MARKER_VALUE", encoding="utf-8")
    link_root = tmp_path / "legacy-link"
    link_root.symlink_to(secret_target)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_workflow_engine",
            "migrate",
            "inspect",
            "--to",
            "2.0.0",
            "--source",
            str(link_root),
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        env=dict(os_module.environ),
        check=False,
    )
    assert result.returncode != 0
    assert "SECRET_MARKER_VALUE" not in result.stdout
    assert "SECRET_MARKER_VALUE" not in result.stderr


def test_companion_symlink_quarantines_complete_pair_and_never_reads_target(
    legacy_home: Path, tmp_path: Path
) -> None:
    """F-2: a symlinked `.patch` companion quarantines the complete pair (both the
    primary record and the companion's own record); the target is never read.
    """
    _write_known_agent_run(tmp_path)
    [json_path] = list(legacy_home.rglob("*.json"))
    [patch_path] = list(legacy_home.rglob("*.patch"))

    secret = tmp_path / "outside-secret.patch"
    secret.write_bytes(b"SECRET PATCH CONTENT THAT MUST NEVER BE READ\n")
    patch_path.unlink()
    patch_path.symlink_to(secret)

    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    json_record = next(r for r in records if r.relative_path.endswith(".json"))
    patch_record = next(r for r in records if r.relative_path.endswith(".patch"))
    assert json_record.quarantine_reason == "COMPANION_SYMLINK_NOT_ALLOWED"
    assert patch_record.quarantine_reason == "SYMLINK_NOT_ALLOWED"
    assert patch_record.entry_type == "symlink"
    for record in records:
        assert "SECRET PATCH CONTENT" not in record.quarantine_detail
    _ = json_path


def test_companion_symlink_prompt_markdown_quarantines_complete_pair(
    legacy_home: Path, repository: Path, config_factory: Callable[[Path], Path]
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    [md_path] = list(legacy_home.rglob("*.md"))
    secret = repository / ".." / "outside-secret.md"
    secret = secret.resolve()
    secret.write_text("SECRET MARKDOWN CONTENT", encoding="utf-8")
    md_path.unlink()
    md_path.symlink_to(secret)

    records = discover_legacy_artifacts(legacy_home)
    assert all(r.classification == "QUARANTINED" for r in records)
    json_record = next(r for r in records if r.relative_path.endswith(".json"))
    md_record = next(r for r in records if r.relative_path.endswith(".md"))
    assert json_record.quarantine_reason == "COMPANION_SYMLINK_NOT_ALLOWED"
    assert md_record.quarantine_reason == "SYMLINK_NOT_ALLOWED"
    for record in records:
        assert "SECRET MARKDOWN" not in record.quarantine_detail


def test_relative_path_never_escapes_root_via_backup_plan(
    legacy_home: Path, tmp_path: Path
) -> None:
    """Defense in depth: every reported relative_path, even for a quarantined entry,
    stays clean/relative (enforced by the model layer; see test_migration_models.py's
    path-traversal rejection tests for the direct model-level proof).
    """
    _write_known_workflow_history(tmp_path, events=1)
    manifest = inspect_source(legacy_home, to_version="2.0.0")
    for artifact in manifest.artifacts:
        assert not artifact.relative_path.startswith("/")
        assert ".." not in artifact.relative_path.split("/")


# --- F-3: duplicate YAML keys ------------------------------------------------------------------


def test_duplicate_top_level_yaml_key_is_quarantined(legacy_home: Path) -> None:
    (legacy_home / "approvals").mkdir(parents=True)
    text = (
        "kind: commit\ntask_id: T-1\nbranch: main\nhead: " + "a" * 40 + "\n"
        "allowed_paths: [x.py]\nmessage: m\napproved_by: a@b.c\nkind: push\n"
    )
    (legacy_home / "approvals" / "dup.yaml").write_text(text, encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "DUPLICATE_YAML_KEY"


def test_duplicate_yaml_key_never_selects_the_last_value_as_kind(legacy_home: Path) -> None:
    """`kind: commit` then `kind: push` must never be silently resolved to "push" by
    last-key-wins -- the file must be quarantined, not classified as either family.
    """
    (legacy_home / "approvals").mkdir(parents=True)
    text = "kind: commit\ntask_id: T-1\nbranch: main\nhead: " + "a" * 40 + "\nkind: push\n"
    (legacy_home / "approvals" / "dup.yaml").write_text(text, encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "DUPLICATE_YAML_KEY"
    assert record.kind is None


def test_nested_duplicate_yaml_key_is_quarantined(legacy_home: Path) -> None:
    (legacy_home / "approvals").mkdir(parents=True)
    text = (
        "kind: commit\n"
        "task_id: T-1\n"
        "branch: main\n"
        "head: " + "a" * 40 + "\n"
        "allowed_paths:\n"
        "  nested: {a: 1, a: 2}\n"
        "message: m\n"
        "approved_by: a@b.c\n"
    )
    (legacy_home / "approvals" / "nested-dup.yaml").write_text(text, encoding="utf-8")
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.quarantine_reason == "DUPLICATE_YAML_KEY"


# --- empty input -----------------------------------------------------------------------------


def test_empty_source_root_yields_empty_manifest(legacy_home: Path) -> None:
    legacy_home.mkdir(parents=True)
    manifest = inspect_source(legacy_home, to_version="2.0.0")
    assert manifest.artifacts == []
    assert manifest.artifact_count == 0
    assert manifest.known_count == 0
    assert manifest.quarantined_count == 0


def test_never_created_source_root_is_treated_as_empty(tmp_path: Path) -> None:
    assert discover_legacy_artifacts(tmp_path / "does-not-exist") == []


def test_source_root_that_is_a_file_fails_closed(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "im-a-file"
    not_a_directory.write_text("oops", encoding="utf-8")
    with pytest.raises(MigrationSourceError):
        discover_legacy_artifacts(not_a_directory)


# --- deterministic repeated inspection -------------------------------------------------------


def test_repeated_inspection_is_byte_for_byte_deterministic(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_workflow_history(tmp_path, events=2)
    _write_known_agent_run(tmp_path)
    _write_known_approval(legacy_home, "a.yaml")

    first = inspect_source(legacy_home, to_version="2.0.0")
    second = inspect_source(legacy_home, to_version="2.0.0")
    assert first.manifest_digest == second.manifest_digest
    assert first == second


# --- concurrency: parallel inspects of the same unchanged root agree and mutate nothing ------


def test_concurrent_inspects_are_consistent_and_read_only(
    legacy_home: Path, tmp_path: Path
) -> None:

    _write_known_workflow_history(tmp_path, events=2)
    _write_known_agent_run(tmp_path)

    before = {p: p.read_bytes() for p in legacy_home.rglob("*") if p.is_file()}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(inspect_source, legacy_home, to_version="2.0.0") for _ in range(8)]
        manifests = [future.result() for future in futures]

    digests = {manifest.manifest_digest for manifest in manifests}
    assert len(digests) == 1, "concurrent inspects of unchanged input must agree exactly"

    after = {p: p.read_bytes() for p in legacy_home.rglob("*") if p.is_file()}
    assert before == after, "concurrent inspect must not mutate any legacy artifact"


# --- F-7: fault injection / TOCTOU: a mutation mid-scan is detected, not silently trusted ----


def test_unreadable_file_is_quarantined_not_fatal(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    target = directory / "00000001.json"
    target.write_text('{"schema_version":"1.0"}\n', encoding="utf-8")
    original_mode = target.stat().st_mode
    target.chmod(0o000)
    try:
        [record] = discover_legacy_artifacts(legacy_home)
        assert record.quarantine_reason == "FILE_UNREADABLE"
        assert record.entry_type == "unreadable"
    finally:
        target.chmod(stat.S_IMODE(original_mode) | stat.S_IWUSR | stat.S_IRUSR)


def test_directory_mutated_after_history_read_quarantines_the_group(
    legacy_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-7: simulate a concurrent writer adding a new event file to a task's directory
    after this session has already read every member it originally listed. The
    post-read re-listing check must catch the mismatch and quarantine the whole group,
    rather than silently returning a KNOWN result assembled across two filesystem states.
    """
    _write_known_workflow_history(tmp_path, events=2)
    [task_dir] = sorted({p.parent for p in legacy_home.rglob("00000001.json")})

    real_scandir = os.scandir
    calls = {"count": 0}

    def _racy_scandir(path: object = ".") -> object:
        calls["count"] += 1
        # The very first call for this exact task directory is the initial top-level
        # walk (via _iter_entries_safe) that discovers the two files. The group
        # validator's own post-read re-list is a *later* call for the same directory --
        # inject an extra file just before that one fires.
        if str(path) == str(task_dir) and calls["count"] > 4:
            extra = task_dir / "00000003.json"
            if not extra.exists():
                extra.write_bytes(b'{"schema_version":"1.0"}\n')
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", _racy_scandir)
    records = discover_legacy_artifacts(legacy_home)
    monkeypatch.undo()

    state_records = [r for r in records if r.relative_path.startswith("state/")]
    assert len(state_records) >= 2
    assert all(r.classification == "QUARANTINED" for r in state_records[:2])
    assert any(r.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN" for r in state_records)


# --- F-8: unsupported filesystem entry types (FIFO, socket, device node) --------------------


def _run_with_daemon_timeout(fn, *args, timeout: float = 5.0):
    """Run `fn(*args)` on a daemon thread and require it to finish within `timeout`
    seconds. A daemon thread never blocks interpreter/test-process exit even if `fn`
    hangs, so a regression that opens a FIFO/socket (which would block waiting for a
    peer) fails this assertion instead of hanging the whole test run.
    """
    import threading

    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def target() -> None:
        try:
            result["value"] = fn(*args)
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise AssertionError(
            f"{fn} did not complete within {timeout}s -- likely blocked opening an "
            "unsupported filesystem entry (FIFO/socket)"
        )
    if "value" in error:
        raise error["value"]
    return result["value"]


def test_fifo_is_quarantined_without_being_opened_or_blocking(legacy_home: Path) -> None:
    directory = legacy_home / "state" / "p" / "t"
    directory.mkdir(parents=True)
    fifo_path = directory / "00000001.json"
    os.mkfifo(fifo_path)  # no writer ever connects; opening for read would block forever

    records = _run_with_daemon_timeout(discover_legacy_artifacts, legacy_home)

    assert len(records) == 1
    [record] = records
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "UNSUPPORTED_ENTRY_TYPE"
    assert record.entry_type == "unsupported"
    assert "FIFO" in record.quarantine_detail


def test_unix_socket_is_quarantined_without_connection_or_read(legacy_home: Path) -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX sockets are not supported on this platform")
    directory = legacy_home / "approvals"
    directory.mkdir(parents=True)
    socket_path = directory / "weird.yaml"
    # AF_UNIX bind() paths are limited to ~108 bytes on Linux, far shorter than pytest's
    # nested tmp_path; bind in a short-path scratch dir, then move the resulting socket
    # special file into place (os.rename preserves its socket-ness).
    import tempfile

    short_dir = tempfile.mkdtemp(prefix="sk")
    try:
        short_socket_path = Path(short_dir) / "s"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(short_socket_path))
            os.rename(short_socket_path, socket_path)
            records = _run_with_daemon_timeout(discover_legacy_artifacts, legacy_home)
        finally:
            sock.close()
    finally:
        import shutil

        shutil.rmtree(short_dir, ignore_errors=True)

    assert len(records) == 1
    [record] = records
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "UNSUPPORTED_ENTRY_TYPE"
    assert record.entry_type == "unsupported"
    assert "socket" in record.quarantine_detail.lower()


def test_unsupported_entry_appears_in_manifest_and_backup_incomplete_paths(
    legacy_home: Path, tmp_path: Path
) -> None:
    _write_known_workflow_history(tmp_path, events=1)  # a KNOWN sibling, for contrast
    fifo_dir = legacy_home / "state" / "p2" / "t2"
    fifo_dir.mkdir(parents=True)
    os.mkfifo(fifo_dir / "00000001.json")

    manifest = _run_with_daemon_timeout(lambda: inspect_source(legacy_home, to_version="2.0.0"))
    unsupported = [a for a in manifest.artifacts if a.entry_type == "unsupported"]
    assert len(unsupported) == 1
    assert unsupported[0].quarantine_reason == "UNSUPPORTED_ENTRY_TYPE"
    assert manifest.known_count >= 1  # the sibling workflow-event history is unaffected

    from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan

    backup_plan = build_backup_plan(manifest)
    assert unsupported[0].relative_path in backup_plan.incomplete_paths
    assert backup_plan.complete is False
    assert all(e.relative_path != unsupported[0].relative_path for e in backup_plan.entries)

    recovery_plan = build_recovery_plan(manifest, backup_plan)
    assert recovery_plan.complete is False
    assert all(step.relative_path != unsupported[0].relative_path for step in recovery_plan.steps)
    assert all(
        step.action != "restore_file" or step.entry_type == "file" for step in recovery_plan.steps
    )


def test_regular_file_and_symlink_behavior_unchanged_alongside_unsupported_entry(
    legacy_home: Path, tmp_path: Path
) -> None:
    """F-8 must not perturb pre-existing regular-file/symlink classification."""
    _write_known_workflow_history(tmp_path, events=1)
    secret = tmp_path / "outside.txt"
    secret.write_text("nope", encoding="utf-8")
    (legacy_home / "state" / "extra-link").symlink_to(secret)
    fifo_dir = legacy_home / "state" / "p2" / "t2"
    fifo_dir.mkdir(parents=True)
    os.mkfifo(fifo_dir / "00000001.json")

    records = _run_with_daemon_timeout(discover_legacy_artifacts, legacy_home)
    by_path = {r.relative_path: r for r in records}
    assert by_path["state/extra-link"].quarantine_reason == "SYMLINK_NOT_ALLOWED"
    assert by_path["state/extra-link"].entry_type == "symlink"
    known = [r for r in records if r.classification == "KNOWN"]
    assert len(known) == 1
    assert known[0].kind == "workflow-event"


# --- F-9: same-path/same-filename content mutation during inspection is detected -----------


def _inject_mutation_after_first_read(
    monkeypatch: pytest.MonkeyPatch, target_path: Path, mutate: "Callable[[], None]"
) -> None:
    """Monkeypatch the shared safe-read primitive so that, immediately after the *first*
    successful read of `target_path` returns, `mutate()` is applied to the real file on
    disk. This deterministically reproduces a same-path race between this module's
    initial read and its later F-9 verification re-read, without any threading, and
    without special-casing any one call site: every family's final-consistency check
    goes through the same `_read_or_none` primitive.
    """
    original = legacy_readers_module._read_or_none
    state = {"triggered": False}

    def wrapper(path: Path) -> tuple[bytes | None, str | None]:
        result = original(path)
        if not state["triggered"] and path == target_path:
            state["triggered"] = True
            mutate()
        return result

    monkeypatch.setattr(legacy_readers_module, "_read_or_none", wrapper)


def test_workflow_event_content_change_without_filename_change_quarantines_history(
    legacy_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_known_workflow_history(tmp_path, events=2)
    [event_path] = sorted(legacy_home.rglob("00000001.json"))
    original_bytes = event_path.read_bytes()

    _inject_mutation_after_first_read(
        monkeypatch, event_path, lambda: event_path.write_bytes(original_bytes + b"tampered")
    )
    records = discover_legacy_artifacts(legacy_home)

    state_records = [r for r in records if r.relative_path.startswith("state/")]
    assert len(state_records) == 2
    assert all(r.classification == "QUARANTINED" for r in state_records)
    assert all(r.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN" for r in state_records)
    # The digest on the (now-mutated) file no longer matches what any KNOWN record would
    # have reported -- proving this is not merely a stale, silently-accepted classification.
    assert event_path.read_bytes() != original_bytes


def test_agent_run_primary_change_during_inspection_quarantines_pair(
    legacy_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_known_agent_run(tmp_path)
    [json_path] = list(legacy_home.rglob("*.json"))
    original_bytes = json_path.read_bytes()

    _inject_mutation_after_first_read(
        monkeypatch, json_path, lambda: json_path.write_bytes(original_bytes + b"tampered")
    )
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN" for r in records)


def test_agent_run_companion_change_during_inspection_quarantines_pair(
    legacy_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_known_agent_run(tmp_path)
    [patch_path] = list(legacy_home.rglob("*.patch"))
    original_bytes = patch_path.read_bytes()

    _inject_mutation_after_first_read(
        monkeypatch, patch_path, lambda: patch_path.write_bytes(original_bytes + b"tampered")
    )
    records = discover_legacy_artifacts(legacy_home)
    assert len(records) == 2
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN" for r in records)


def test_prompt_primary_change_during_inspection_quarantines_pair(
    legacy_home: Path,
    repository: Path,
    config_factory: Callable[[Path], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    [json_path] = list(legacy_home.rglob("*.json"))
    original_bytes = json_path.read_bytes()

    _inject_mutation_after_first_read(
        monkeypatch, json_path, lambda: json_path.write_bytes(original_bytes + b"tampered")
    )
    records = discover_legacy_artifacts(legacy_home)
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN" for r in records)


def test_prompt_companion_change_during_inspection_quarantines_pair(
    legacy_home: Path,
    repository: Path,
    config_factory: Callable[[Path], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_known_prompt_metadata(repository, config_factory)
    [md_path] = list(legacy_home.rglob("*.md"))
    original_bytes = md_path.read_bytes()

    _inject_mutation_after_first_read(
        monkeypatch, md_path, lambda: md_path.write_bytes(original_bytes + b"tampered")
    )
    records = discover_legacy_artifacts(legacy_home)
    assert all(r.classification == "QUARANTINED" for r in records)
    assert all(r.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN" for r in records)


def test_approval_content_change_during_inspection_is_quarantined(
    legacy_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_home.mkdir(parents=True)
    _write_known_approval(legacy_home, "a.yaml")
    approval_path = legacy_home / "approvals" / "a.yaml"
    original_bytes = approval_path.read_bytes()

    _inject_mutation_after_first_read(
        monkeypatch,
        approval_path,
        lambda: approval_path.write_bytes(original_bytes + b"\n# tampered\n"),
    )
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN"


def test_regular_file_replaced_by_symlink_during_inspection_is_quarantined(
    legacy_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_home.mkdir(parents=True)
    _write_known_approval(legacy_home, "a.yaml")
    approval_path = legacy_home / "approvals" / "a.yaml"
    secret = tmp_path / "outside-secret.yaml"
    secret.write_text("kind: commit\n", encoding="utf-8")

    def _replace_with_symlink() -> None:
        approval_path.unlink()
        approval_path.symlink_to(secret)

    _inject_mutation_after_first_read(monkeypatch, approval_path, _replace_with_symlink)
    [record] = discover_legacy_artifacts(legacy_home)
    assert record.classification == "QUARANTINED"
    assert record.quarantine_reason == "SOURCE_MUTATED_DURING_SCAN"
    # The symlink's target was never opened/read as part of detecting the mutation.
    assert "kind: commit" not in record.quarantine_detail


def test_unchanged_inputs_still_classify_known_deterministically_with_matching_digest(
    legacy_home: Path, tmp_path: Path
) -> None:
    """F-9's final verification pass must not perturb the stable, non-racing case: the
    same KNOWN classification, the same digest, on every repeated inspection.
    """
    _write_known_workflow_history(tmp_path, events=1)
    [event_path] = list(legacy_home.rglob("*.json"))
    stable_bytes = event_path.read_bytes()

    first = discover_legacy_artifacts(legacy_home)
    second = discover_legacy_artifacts(legacy_home)
    assert first == second
    [record] = first
    assert record.classification == "KNOWN"
    assert record.sha256 == hashlib.sha256(stable_bytes).hexdigest()
    assert event_path.read_bytes() == stable_bytes  # inspection itself never wrote anything
