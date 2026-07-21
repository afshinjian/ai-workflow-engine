#!/usr/bin/env python3
"""Independent, disposable-fixture adversarial demonstration for the ORCH-003
remediation findings F-8 and F-9 -- not part of the pytest suite. Everything runs
against disposable tempdirs; nothing here touches a real $HOME or this repository's own
governance files.
"""

import hashlib
import os
import sys
import tempfile
import threading
from pathlib import Path


def _run_with_daemon_timeout(fn, timeout=5.0):
    result = {}
    error = {}

    def target():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            error["value"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise AssertionError(f"did not complete within {timeout}s -- likely blocked on open()")
    if "value" in error:
        raise error["value"]
    return result["value"]


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(repo_root / "src"))

    from ai_workflow_engine.migration.inspect import inspect_source
    from ai_workflow_engine.migration.legacy_readers import discover_legacy_artifacts
    from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan
    from ai_workflow_engine.prompt.renderer import canonical_json
    from ai_workflow_engine.workflow.events import WorkflowEvent

    checks = []

    # -- F-8: FIFO is quarantined, never opened, never blocks -------------------------------
    with tempfile.TemporaryDirectory(prefix="orch003-f8-fifo-") as tmp:
        tmp_path = Path(tmp)
        directory = tmp_path / "state" / "p" / "t"
        directory.mkdir(parents=True)
        fifo_path = directory / "00000001.json"
        os.mkfifo(fifo_path)  # no writer will ever connect

        records = _run_with_daemon_timeout(lambda: discover_legacy_artifacts(tmp_path))
        assert len(records) == 1
        assert records[0].classification == "QUARANTINED"
        assert records[0].quarantine_reason == "UNSUPPORTED_ENTRY_TYPE"
        assert records[0].entry_type == "unsupported"
    checks.append("CHECK_F8_FIFO_QUARANTINED_NEVER_OPENED_NEVER_BLOCKED: PASS")

    # -- F-8: backup/recovery completeness reporting -----------------------------------------
    with tempfile.TemporaryDirectory(prefix="orch003-f8-backup-") as tmp:
        tmp_path = Path(tmp)
        directory = tmp_path / "state" / "p" / "t"
        directory.mkdir(parents=True)
        os.mkfifo(directory / "00000001.json")

        manifest = _run_with_daemon_timeout(
            lambda: inspect_source(tmp_path, to_version="2.0.0")
        )
        backup_plan = build_backup_plan(manifest)
        recovery_plan = build_recovery_plan(manifest, backup_plan)
        assert backup_plan.entries == []
        assert backup_plan.incomplete_paths == [manifest.artifacts[0].relative_path]
        assert backup_plan.complete is False
        assert recovery_plan.complete is False
        assert all(step.action != "restore_file" for step in recovery_plan.steps)
    checks.append("CHECK_F8_BACKUP_RECOVERY_REPORT_INCOMPLETE_NO_RESTORE_FILE: PASS")

    # -- F-9: same-filename content mutation during inspection is detected ------------------
    with tempfile.TemporaryDirectory(prefix="orch003-f9-") as tmp:
        tmp_path = Path(tmp)
        directory = tmp_path / "state" / "proj" / "task-x"
        # task_dir_name("task") not needed here since we bypass the real writer and
        # construct the directory name ourselves matching the address-check convention.
        from ai_workflow_engine.workflow.event_store import task_dir_name

        directory = tmp_path / "state" / "proj" / task_dir_name("task")
        directory.mkdir(parents=True)
        event = WorkflowEvent(
            schema_version="1.0", project_id="proj", task_id="task", sequence=1,
            parent_digest=None, stage="plan-review", action="verdict", verdict="APPROVED",
            prompt_id=None, agent_run_id=None, head="a" * 40, note="",
        )
        event_path = directory / "00000001.json"
        original_bytes = canonical_json(event.model_dump(mode="json")) + b"\n"
        event_path.write_bytes(original_bytes)

        # Monkeypatch the shared safe-read primitive to mutate the file immediately after
        # its first successful read -- deterministically reproducing a same-path,
        # same-filename race between the initial read and the later F-9 verification read.
        import ai_workflow_engine.migration.legacy_readers as lr

        original_read = lr._read_or_none
        state = {"triggered": False}

        def racy_read(path):
            result = original_read(path)
            if not state["triggered"] and path == event_path:
                state["triggered"] = True
                event_path.write_bytes(original_bytes + b"tampered")
            return result

        lr._read_or_none = racy_read
        try:
            records = discover_legacy_artifacts(tmp_path)
        finally:
            lr._read_or_none = original_read

        assert len(records) == 1
        assert records[0].classification == "QUARANTINED", "F-9 FAILED: mutated content was not detected"
        assert records[0].quarantine_reason == "SOURCE_MUTATED_DURING_SCAN"
        assert event_path.read_bytes() != original_bytes
    checks.append("CHECK_F9_SAME_FILENAME_CONTENT_MUTATION_DETECTED: PASS")

    # -- F-9: stable input is still deterministic and byte-accurate -------------------------
    with tempfile.TemporaryDirectory(prefix="orch003-f9-stable-") as tmp:
        tmp_path = Path(tmp)
        from ai_workflow_engine.workflow.event_store import task_dir_name

        directory = tmp_path / "state" / "proj" / task_dir_name("task")
        directory.mkdir(parents=True)
        event = WorkflowEvent(
            schema_version="1.0", project_id="proj", task_id="task", sequence=1,
            parent_digest=None, stage="plan-review", action="verdict", verdict="APPROVED",
            prompt_id=None, agent_run_id=None, head="a" * 40, note="",
        )
        stable_bytes = canonical_json(event.model_dump(mode="json")) + b"\n"
        (directory / "00000001.json").write_bytes(stable_bytes)

        first = discover_legacy_artifacts(tmp_path)
        second = discover_legacy_artifacts(tmp_path)
        assert first == second
        assert first[0].classification == "KNOWN"
        assert first[0].sha256 == hashlib.sha256(stable_bytes).hexdigest()
    checks.append("CHECK_F9_STABLE_INPUT_DETERMINISTIC_DIGEST_ACCURATE: PASS")

    print("\n".join(checks))
    print("ORCH003_F8_F9_DEMO: ALL_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
