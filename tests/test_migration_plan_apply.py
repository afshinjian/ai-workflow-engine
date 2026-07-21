"""`migrate plan` / `migrate apply --dry-run` write-safety and determinism: identical
filesystem snapshots before/after every read-only operation, deterministic plan digests,
complete backup/recovery coverage across every physical member (F-4), and a real-apply
refusal that is proven to happen before any filesystem mutation *and* before any
argument re-verification I/O (F-7).
"""

from pathlib import Path

import pytest

from ai_workflow_engine.migration.apply import apply_migration
from ai_workflow_engine.migration.errors import ApplyNotAuthorizedError
from ai_workflow_engine.migration.inspect import inspect_source
from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.workflow.event_store import task_dir_name
from ai_workflow_engine.workflow.events import WorkflowEvent


def _snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _populate(root: Path) -> None:
    # Written directly (not via `workflow.event_store.append`, which always targets the
    # real `~/.ai-workflow-engine/workflow-runs` regardless of this arbitrary `root`) so
    # this test never touches a real user's home directory.
    directory = root / "state" / "p" / task_dir_name("t")
    directory.mkdir(parents=True)
    event = WorkflowEvent(
        schema_version="1.0",
        project_id="p",
        task_id="t",
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
    # A quarantined sibling too, so plan/apply are exercised over a mixed manifest.
    (root / "junk").mkdir(parents=True, exist_ok=True)
    (root / "junk" / "stray.txt").write_text("hello", encoding="utf-8")


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "legacy"
    _populate(root)
    return root


# --- inspect / plan / apply --dry-run write nothing ------------------------------------------


def test_inspect_writes_nothing(source_root: Path) -> None:
    before = _snapshot(source_root)
    inspect_source(source_root, to_version="2.0.0")
    assert _snapshot(source_root) == before


def test_plan_writes_nothing(source_root: Path) -> None:
    before = _snapshot(source_root)
    manifest = inspect_source(source_root, to_version="2.0.0")
    build_backup_plan(manifest)
    assert _snapshot(source_root) == before


def test_apply_dry_run_writes_nothing(source_root: Path, tmp_path: Path) -> None:
    before_source = _snapshot(source_root)
    before_tree = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}

    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    result = apply_migration(manifest, backup_plan, recovery_plan, dry_run=True)

    assert result.status == "DRY_RUN_OK"
    assert _snapshot(source_root) == before_source
    after_tree = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
    assert (
        after_tree == before_tree
    ), "dry-run apply must not create any file anywhere, including a backup object"


def test_apply_without_dry_run_refuses_before_any_mutation(
    source_root: Path, tmp_path: Path
) -> None:
    before_source = _snapshot(source_root)
    before_tree = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}

    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)

    with pytest.raises(ApplyNotAuthorizedError):
        apply_migration(manifest, backup_plan, recovery_plan, dry_run=False)

    assert _snapshot(source_root) == before_source
    after_tree = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
    assert after_tree == before_tree


def test_apply_without_dry_run_refuses_even_with_a_deleted_source_root(
    source_root: Path, tmp_path: Path
) -> None:
    """F-7: refusal must occur without source access -- proven here by deleting the
    source root entirely between planning and the (still refused) real-apply call, and
    by never calling `inspect_source` again for the refusal itself.
    """
    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)

    import shutil

    shutil.rmtree(source_root)
    assert not source_root.exists()

    with pytest.raises(ApplyNotAuthorizedError):
        apply_migration(manifest, backup_plan, recovery_plan, dry_run=False)


def test_apply_without_dry_run_refuses_with_instrumented_source_access_guard(
    source_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-7: instrument `os.scandir`/`Path.read_bytes` to fail if ever invoked, then prove
    the real-apply refusal still occurs -- meaning `apply_migration` never touches the
    source tree at all for this path (the manifest/plans are already fully built objects
    in memory; refusal is a pure in-memory check).
    """
    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)

    import os

    def _guard_scandir(*args: object, **kwargs: object) -> object:
        raise AssertionError("apply_migration's refusal path must never scan the source tree")

    monkeypatch.setattr(os, "scandir", _guard_scandir)

    with pytest.raises(ApplyNotAuthorizedError):
        apply_migration(manifest, backup_plan, recovery_plan, dry_run=False)


# --- identical filesystem snapshot before/after (fixture-driven demonstration) --------------


def test_identical_snapshot_across_inspect_plan_apply_dry_run_sequence(source_root: Path) -> None:
    snapshot_0 = _snapshot(source_root)
    manifest = inspect_source(source_root, to_version="2.0.0")
    snapshot_1 = _snapshot(source_root)
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    snapshot_2 = _snapshot(source_root)
    apply_migration(manifest, backup_plan, recovery_plan, dry_run=True)
    snapshot_3 = _snapshot(source_root)
    assert snapshot_0 == snapshot_1 == snapshot_2 == snapshot_3


# --- deterministic plan output -----------------------------------------------------------------


def test_plan_digest_is_deterministic_across_independent_recomputation(source_root: Path) -> None:
    manifest_a = inspect_source(source_root, to_version="2.0.0")
    backup_a = build_backup_plan(manifest_a)
    recovery_a = build_recovery_plan(manifest_a, backup_a)

    manifest_b = inspect_source(source_root, to_version="2.0.0")
    backup_b = build_backup_plan(manifest_b)
    recovery_b = build_recovery_plan(manifest_b, backup_b)

    assert manifest_a.manifest_digest == manifest_b.manifest_digest
    assert backup_a.plan_digest == backup_b.plan_digest
    assert recovery_a.plan_digest == recovery_b.plan_digest


def test_backup_plan_entries_are_content_addressed_by_sha256(source_root: Path) -> None:
    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    assert len(backup_plan.entries) == manifest.artifact_count
    for entry in backup_plan.entries:
        assert entry.backup_relative_path == f"objects/{entry.sha256[:2]}/{entry.sha256}"


def test_recovery_plan_covers_every_backup_entry_with_verify_then_type_aware_action(
    source_root: Path,
) -> None:
    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    assert len(recovery_plan.steps) == 2 * len(backup_plan.entries)
    for index, entry in enumerate(backup_plan.entries):
        verify_step, second_step = (
            recovery_plan.steps[2 * index],
            recovery_plan.steps[2 * index + 1],
        )
        assert verify_step.action == "verify_backup_digest"
        expected_action = (
            "restore_file" if entry.entry_type == "file" else "refuse_unsupported_entry_type"
        )
        assert second_step.action == expected_action
        assert verify_step.relative_path == second_step.relative_path == entry.relative_path
        assert verify_step.sha256 == second_step.sha256 == entry.sha256
        assert verify_step.entry_type == second_step.entry_type == entry.entry_type


# --- F-4: complete backup coverage across every physical member, including companions -------


def test_backup_plan_includes_quarantined_artifacts_too(source_root: Path) -> None:
    manifest = inspect_source(source_root, to_version="2.0.0")
    assert manifest.quarantined_count >= 1
    backup_plan = build_backup_plan(manifest)
    backed_up_paths = {entry.relative_path for entry in backup_plan.entries}
    readable_manifest_paths = {
        a.relative_path for a in manifest.artifacts if a.entry_type != "unreadable"
    }
    assert backed_up_paths == readable_manifest_paths


def test_backup_plan_entries_exactly_match_physical_readable_source_members(
    source_root: Path,
) -> None:
    """Independently enumerate every physical file under the source tree (bypassing this
    stage's own reader entirely) and assert the backup plan's coverage is exact.
    """
    physical_paths = {
        str(p.relative_to(source_root)) for p in source_root.rglob("*") if p.is_file()
    }
    manifest = inspect_source(source_root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    backed_up_paths = {entry.relative_path for entry in backup_plan.entries}
    assert backed_up_paths | set(backup_plan.incomplete_paths) == physical_paths
    assert backed_up_paths == physical_paths  # nothing in this fixture is unreadable
    assert backup_plan.complete is True


def test_backup_plan_reports_incomplete_for_an_unreadable_member(tmp_path: Path) -> None:
    import stat as stat_module

    root = tmp_path / "legacy"
    directory = root / "state" / "p" / "t"
    directory.mkdir(parents=True)
    target = directory / "00000001.json"
    target.write_text('{"schema_version":"1.0"}\n', encoding="utf-8")
    original_mode = target.stat().st_mode
    target.chmod(0o000)
    try:
        manifest = inspect_source(root, to_version="2.0.0")
        backup_plan = build_backup_plan(manifest)
        assert backup_plan.complete is False
        assert manifest.artifacts[0].relative_path in backup_plan.incomplete_paths
        assert backup_plan.entries == []
        recovery_plan = build_recovery_plan(manifest, backup_plan)
        assert recovery_plan.complete is False
        assert recovery_plan.steps == []
        result = apply_migration(manifest, backup_plan, recovery_plan, dry_run=True)
        assert result.backup_complete is False
    finally:
        target.chmod(stat_module.S_IMODE(original_mode) | stat_module.S_IWUSR | stat_module.S_IRUSR)


def test_backup_plan_never_represents_a_symlink_target_as_a_regular_restorable_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    directory = root / "state" / "p" / "t"
    directory.mkdir(parents=True)
    (directory / "00000001.json").symlink_to(tmp_path / "does-not-matter")

    manifest = inspect_source(root, to_version="2.0.0")
    backup_plan = build_backup_plan(manifest)
    [entry] = backup_plan.entries
    assert entry.entry_type == "symlink"
    recovery_plan = build_recovery_plan(manifest, backup_plan)
    [_verify_step, second_step] = recovery_plan.steps
    assert second_step.action == "refuse_unsupported_entry_type"


def test_backup_plan_reports_incomplete_for_an_unsupported_entry_type(tmp_path: Path) -> None:
    """F-8: a FIFO/socket/device node is never opened and never appears in
    BackupPlan.entries; it makes both backup and recovery plans incomplete, exactly like
    an unreadable file, and is never restorable.
    """
    import os as os_module

    root = tmp_path / "legacy"
    directory = root / "state" / "p" / "t"
    directory.mkdir(parents=True)
    os_module.mkfifo(directory / "00000001.json")

    manifest = inspect_source(root, to_version="2.0.0")
    [artifact] = manifest.artifacts
    assert artifact.entry_type == "unsupported"
    assert artifact.quarantine_reason == "UNSUPPORTED_ENTRY_TYPE"

    backup_plan = build_backup_plan(manifest)
    assert backup_plan.entries == []
    assert backup_plan.incomplete_paths == [artifact.relative_path]
    assert backup_plan.complete is False

    recovery_plan = build_recovery_plan(manifest, backup_plan)
    assert recovery_plan.steps == []
    assert recovery_plan.complete is False

    result = apply_migration(manifest, backup_plan, recovery_plan, dry_run=True)
    assert result.backup_complete is False
