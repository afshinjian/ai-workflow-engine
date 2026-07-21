#!/usr/bin/env python3
"""Independent, disposable-fixture demonstration for ORCH-003 (not part of the pytest
suite): proves, outside any test framework, that:

1. legacy bytes/digest are identical before and after `migrate inspect`;
2. the filesystem snapshot is identical before and after `migrate plan`;
3. the filesystem snapshot is identical before and after `migrate apply --dry-run`;
4. `migrate apply` without `--dry-run` fails before any mutation;
5. unknown/corrupt input produces a quarantine classification;
6. ORCH-004 was not started (implementation-state.yaml is read-only-inspected, unchanged).

Everything runs against a disposable tempdir; nothing here touches a real $HOME or this
repository's own governance files (the state-file read at the end is read-only).
"""

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[0]  # overwritten below once repo root is known


def hash_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(repo_root / "src"))

    from ai_workflow_engine.migration.apply import apply_migration
    from ai_workflow_engine.migration.errors import ApplyNotAuthorizedError
    from ai_workflow_engine.migration.inspect import inspect_source
    from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan
    from ai_workflow_engine.prompt.renderer import canonical_json
    from ai_workflow_engine.workflow.events import WorkflowEvent

    checks: list[str] = []

    with tempfile.TemporaryDirectory(prefix="orch003-demo-") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "legacy"

        # A known-good workflow-event artifact.
        good_dir = source / "state" / "proj" / "task"
        good_dir.mkdir(parents=True)
        event = WorkflowEvent(
            schema_version="1.0", project_id="proj", task_id="task", sequence=1,
            parent_digest=None, stage="implementation", action="completed", verdict=None,
            prompt_id=None, agent_run_id=None, head="a" * 40, note="",
        )
        good_bytes = canonical_json(event.model_dump(mode="json")) + b"\n"
        (good_dir / "00000001.json").write_bytes(good_bytes)

        # A corrupt / unknown-shape artifact in the same known directory.
        (good_dir / "00000002.json").write_text("this is not json", encoding="utf-8")

        # -- 1. identical legacy bytes/digest before and after inspect -----------------------
        before_bytes = (good_dir / "00000001.json").read_bytes()
        before_digest = hashlib.sha256(before_bytes).hexdigest()
        manifest = inspect_source(source, to_version="2.0.0")
        after_bytes = (good_dir / "00000001.json").read_bytes()
        after_digest = hashlib.sha256(after_bytes).hexdigest()
        assert before_bytes == after_bytes, "legacy bytes changed across inspect"
        assert before_digest == after_digest
        good_record = next(a for a in manifest.artifacts if a.relative_path.endswith("00000001.json"))
        assert good_record.classification == "KNOWN"
        assert good_record.sha256 == before_digest
        checks.append(f"CHECK_1_BYTES_DIGEST_PRESERVED: PASS ({before_digest})")

        # -- 5. unknown/corrupt input produces quarantine classification ---------------------
        bad_record = next(a for a in manifest.artifacts if a.relative_path.endswith("00000002.json"))
        assert bad_record.classification == "QUARANTINED"
        assert bad_record.quarantine_reason == "NOT_VALID_JSON"
        checks.append(f"CHECK_5_QUARANTINE_CLASSIFICATION: PASS ({bad_record.quarantine_reason})")

        # -- 2. identical filesystem snapshot before/after plan -------------------------------
        snapshot_before_plan = hash_tree(source)
        backup_plan = build_backup_plan(manifest)
        recovery_plan = build_recovery_plan(manifest, backup_plan)
        snapshot_after_plan = hash_tree(source)
        assert snapshot_before_plan == snapshot_after_plan
        checks.append(f"CHECK_2_PLAN_WRITES_NOTHING: PASS ({len(snapshot_before_plan)} files unchanged)")

        # -- 3. identical filesystem snapshot before/after apply --dry-run -------------------
        outer_snapshot_before = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
        snapshot_before_apply = hash_tree(source)
        result = apply_migration(manifest, backup_plan, recovery_plan, dry_run=True)
        assert result.status == "DRY_RUN_OK"
        snapshot_after_apply = hash_tree(source)
        outer_snapshot_after = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
        assert snapshot_before_apply == snapshot_after_apply
        assert outer_snapshot_before == outer_snapshot_after, "dry-run apply created a file somewhere"
        checks.append("CHECK_3_APPLY_DRY_RUN_WRITES_NOTHING: PASS")

        # -- 4. apply without --dry-run fails before any mutation -----------------------------
        snapshot_before_refusal = hash_tree(source)
        try:
            apply_migration(manifest, backup_plan, recovery_plan, dry_run=False)
            raise AssertionError("apply_migration must refuse without dry_run=True")
        except ApplyNotAuthorizedError:
            pass
        snapshot_after_refusal = hash_tree(source)
        assert snapshot_before_refusal == snapshot_after_refusal
        checks.append("CHECK_4_APPLY_WITHOUT_DRY_RUN_REFUSES: PASS")

    # -- 6. ORCH-004 was not started (read-only inspection of the real state file) ------------
    import yaml

    state_path = repo_root / "docs/implementation/orchestration/implementation-state.yaml"
    state_before = state_path.read_bytes()
    state = yaml.safe_load(state_before)
    orch_004 = state["stages"]["ORCH-004"]
    assert orch_004["status"] == "NOT_STARTED", orch_004["status"]
    assert orch_004["implementer"] is None
    state_after = state_path.read_bytes()
    assert state_before == state_after, "reading the state file must never modify it"
    checks.append("CHECK_6_ORCH_004_NOT_STARTED: PASS")

    print("\n".join(checks))
    print("ORCH003_DEMO: ALL_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
