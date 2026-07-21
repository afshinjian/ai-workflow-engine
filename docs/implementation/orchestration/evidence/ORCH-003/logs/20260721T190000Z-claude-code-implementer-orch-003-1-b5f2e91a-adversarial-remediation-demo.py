#!/usr/bin/env python3
"""Independent, disposable-fixture adversarial demonstration for the ORCH-003 remediation
(F-1 through F-7) -- not part of the pytest suite. Everything runs against disposable
tempdirs; nothing here touches a real $HOME or this repository's own governance files.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(repo_root / "src"))

    from ai_workflow_engine.migration.apply import apply_migration
    from ai_workflow_engine.migration.errors import ApplyNotAuthorizedError, MigrationSourceError
    from ai_workflow_engine.migration.inspect import inspect_source
    from ai_workflow_engine.migration.legacy_readers import discover_legacy_artifacts
    from ai_workflow_engine.migration.models import MigrationManifest
    from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan
    from ai_workflow_engine.prompt.renderer import canonical_json
    from ai_workflow_engine.workflow.event_store import task_dir_name
    from ai_workflow_engine.workflow.events import WorkflowEvent

    checks: list[str] = []

    # -- F-1: source root itself a symlink is refused; target directory never scanned ------
    with tempfile.TemporaryDirectory(prefix="orch003-f1-") as tmp:
        tmp_path = Path(tmp)
        secret_target = tmp_path / "secret-target"
        secret_target.mkdir()
        (secret_target / "state").mkdir()
        (secret_target / "state" / "leak.json").write_text("SECRET_F1_MARKER", encoding="utf-8")
        link_root = tmp_path / "legacy-link"
        link_root.symlink_to(secret_target)

        original_scandir = os.scandir

        def _guard_scandir(*args: object, **kwargs: object) -> object:
            raise AssertionError("os.scandir must never be called for a symlink source root")

        os.scandir = _guard_scandir  # type: ignore[assignment]
        try:
            try:
                discover_legacy_artifacts(link_root)
                raise AssertionError("F-1 FAILED: no exception raised for symlink source root")
            except MigrationSourceError:
                pass
        finally:
            os.scandir = original_scandir
    checks.append("CHECK_F1_SYMLINK_ROOT_REJECTED_TARGET_NEVER_SCANNED: PASS")

    # -- F-2: symlinked .patch companion quarantines the complete pair; target never read ---
    with tempfile.TemporaryDirectory(prefix="orch003-f2-") as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / "home"
        home.mkdir()
        os.environ["HOME"] = str(home)
        from ai_workflow_engine.agents.artifacts import build_record, save_run
        from ai_workflow_engine.agents.runner import RunObservation
        from ai_workflow_engine.result import CheckResult, Status

        observation = RunObservation(
            agent_name="stub", agent_mode="read-only", agent_executable="/bin/true",
            agent_args=[], timeout_seconds=60, task_id="task-1", stage="plan-review",
            prompt_id="deadbeefdeadbeef", repository_head="b" * 40, ok=True,
            failure_code=None, report=None, exit_code=0, stdout=b"", stderr=b"",
            patch=b"diff --git a/x b/x\n+hi\n",
        )
        verification = CheckResult(
            check_name="agent-run", status=Status.PASS, summary="ok", findings=[],
            evidence={}, affected_paths=[], remediation_hint=None,
        )
        record, patch = build_record(observation, verification, project_id="proj")
        save_run(record, patch, repository=str(tmp_path / "not-the-repo"))

        legacy_root = home / ".ai-workflow-engine" / "workflow-runs"
        [patch_path] = list(legacy_root.rglob("*.patch"))
        secret = tmp_path / "outside-secret.patch"
        secret.write_bytes(b"SECRET_F2_PATCH_CONTENT\n")
        patch_path.unlink()
        patch_path.symlink_to(secret)

        records = discover_legacy_artifacts(legacy_root)
        assert all(r.classification == "QUARANTINED" for r in records), "F-2 FAILED: pair not fully quarantined"
        assert any(r.quarantine_reason == "COMPANION_SYMLINK_NOT_ALLOWED" for r in records)
        assert any(r.quarantine_reason == "SYMLINK_NOT_ALLOWED" for r in records)
        for r in records:
            assert "SECRET_F2_PATCH_CONTENT" not in r.quarantine_detail, "F-2 FAILED: target content leaked"
    checks.append("CHECK_F2_COMPANION_SYMLINK_QUARANTINES_PAIR_TARGET_NEVER_READ: PASS")

    # -- F-3: duplicate YAML key never selects a family via last-key-wins -------------------
    with tempfile.TemporaryDirectory(prefix="orch003-f3-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "approvals").mkdir()
        text = "kind: commit\ntask_id: T-1\nbranch: main\nhead: " + "a" * 40 + "\nkind: push\n"
        (tmp_path / "approvals" / "dup.yaml").write_text(text, encoding="utf-8")
        [record] = discover_legacy_artifacts(tmp_path)
        assert record.classification == "QUARANTINED"
        assert record.quarantine_reason == "DUPLICATE_YAML_KEY"
        assert record.kind is None, "F-3 FAILED: a family was chosen despite duplicate keys"
    checks.append("CHECK_F3_DUPLICATE_YAML_KEY_NEVER_SELECTS_FAMILY: PASS")

    # -- F-4/F-6/F-7 combined scenario, and F-5 tamper/reverification -----------------------
    with tempfile.TemporaryDirectory(prefix="orch003-f4f5f6f7-") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "legacy"
        good_dir = source / "state" / "proj" / task_dir_name("task")
        good_dir.mkdir(parents=True)
        e1 = WorkflowEvent(
            schema_version="1.0", project_id="proj", task_id="task", sequence=1,
            parent_digest=None, stage="plan-review", action="verdict", verdict="APPROVED",
            prompt_id=None, agent_run_id=None, head="a" * 40, note="",
        )
        raw1 = canonical_json(e1.model_dump(mode="json")) + b"\n"
        (good_dir / "00000001.json").write_bytes(raw1)
        e2 = WorkflowEvent(
            schema_version="1.0", project_id="proj", task_id="task", sequence=2,
            parent_digest=hashlib.sha256(raw1).hexdigest(), stage="implementation",
            action="completed", verdict=None, prompt_id=None, agent_run_id=None,
            head="a" * 40, note="",
        )
        (good_dir / "00000002.json").write_bytes(canonical_json(e2.model_dump(mode="json")) + b"\n")

        # F-6: corrupt the second (otherwise independently-valid-looking) event's stage.
        payload2 = json.loads((good_dir / "00000002.json").read_bytes())
        payload2["stage"] = "governance-review"
        payload2["action"] = "verdict"
        payload2["verdict"] = "APPROVED"
        (good_dir / "00000002.json").write_bytes(canonical_json(payload2) + b"\n")

        manifest = inspect_source(source, to_version="2.0.0")
        history_records = [a for a in manifest.artifacts if a.relative_path.startswith("state/")]
        assert len(history_records) == 2
        assert all(a.classification == "QUARANTINED" for a in history_records), (
            "F-6 FAILED: a corrupt member did not quarantine the whole history"
        )
        first = next(a for a in history_records if a.relative_path.endswith("00000001.json"))
        assert "00000002.json" in first.quarantine_detail, (
            "F-6 FAILED: the independently-valid-looking first event was not quarantined "
            "for the second event's corruption"
        )
        checks.append("CHECK_F6_CORRUPT_MEMBER_QUARANTINES_WHOLE_HISTORY: PASS")

        # F-4: backup coverage exactly matches every physical readable member.
        backup_plan = build_backup_plan(manifest)
        recovery_plan = build_recovery_plan(manifest, backup_plan)
        physical_paths = {str(p.relative_to(source)) for p in source.rglob("*") if p.is_file()}
        backed_up_paths = {e.relative_path for e in backup_plan.entries}
        assert backed_up_paths == physical_paths, "F-4 FAILED: backup coverage incomplete"
        assert backup_plan.complete is True
        checks.append("CHECK_F4_BACKUP_COVERAGE_EXACTLY_MATCHES_PHYSICAL_MEMBERS: PASS")

        # F-5: tampering with a sealed record after the fact is rejected on re-validation.
        tampered = manifest.model_dump(mode="json")
        tampered["artifacts"][0]["sha256"] = "f" * 64
        try:
            MigrationManifest.model_validate(tampered)
            raise AssertionError("F-5 FAILED: tampered manifest was accepted")
        except Exception as exc:
            assert "manifest_digest does not match" in str(exc)
        checks.append("CHECK_F5_TAMPERED_MANIFEST_REJECTED_ON_VALIDATE: PASS")

        # F-5 (apply side): a model_construct-bypassed object is still caught by apply's
        # independent re-verification, not merely a digest-string comparison.
        from ai_workflow_engine.migration.models import LegacyArtifactRecord

        bad_fields = manifest.model_dump(mode="json")
        bad_fields["known_count"] = 999
        bad_fields["artifacts"] = [LegacyArtifactRecord.model_validate(a) for a in bad_fields["artifacts"]]
        bad_manifest = MigrationManifest.model_construct(**bad_fields)
        try:
            apply_migration(bad_manifest, backup_plan, recovery_plan, dry_run=True)
            raise AssertionError("F-5 FAILED: apply accepted a bypassed-validation manifest")
        except ApplyNotAuthorizedError as exc:
            assert "re-verification" in str(exc)
        checks.append("CHECK_F5_APPLY_REVERIFIES_NOT_JUST_DIGEST_STRINGS: PASS")

        # F-7: apply refuses before any source access when --dry-run is absent, even after
        # the source tree has been deleted entirely.
        shutil.rmtree(source)
        try:
            apply_migration(manifest, backup_plan, recovery_plan, dry_run=False)
            raise AssertionError("F-7 FAILED: apply did not refuse")
        except ApplyNotAuthorizedError:
            pass
        checks.append("CHECK_F7_APPLY_REFUSES_WITHOUT_DRY_RUN_EVEN_WITH_DELETED_SOURCE: PASS")

    print("\n".join(checks))
    print("ORCH003_REMEDIATION_DEMO: ALL_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
