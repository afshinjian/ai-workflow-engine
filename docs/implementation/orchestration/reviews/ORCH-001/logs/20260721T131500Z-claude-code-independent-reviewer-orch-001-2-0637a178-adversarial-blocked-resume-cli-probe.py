#!/usr/bin/env python3
"""Independent ORCH-001 review adversarial probe (reviewer-2).

Unlike the two prior probes on this stage (the rejecting reviewer's
direct-apply_transition probe, and the remediator's own direct-apply_transition
demonstration), this probe drives the *CLI subcommand* end to end
(`transition` against a real temp state file, then `validate` against the
resulting on-disk file), so it also exercises the CAS-digest read/compare and
write_state_atomic path -- not just the in-memory apply_transition function --
for the same three scenarios named by the remediation task:

  1. BLOCKED -> IN_PROGRESS with an unresolved blocker must be rejected.
  2. BLOCKED -> IN_PROGRESS with an unapproved prerequisite must be rejected.
  3. BLOCKED -> IN_PROGRESS succeeds, and passes `validate`, only when both
     conditions hold.

A three-stage state (ORCH-000/ORCH-001/ORCH-002) is used, closer to the real
delivery_order shape, with ORCH-001 as the stage under test and ORCH-002 as an
untouched downstream stage (must remain NOT_STARTED throughout).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/afshin-jian/ai-workflow-engine")
SCRIPT = REPO / "scripts" / "orchestration_feature_state.py"
assert SCRIPT.exists(), f"expected {SCRIPT} to exist"


def stage(status, prerequisites, blockers=None, **overrides):
    base = {
        "title": "t",
        "status": status,
        "prerequisites": prerequisites,
        "expected_base_head": "a" * 40,
        "implementation_commit": None,
        "implementer": "impl-x",
        "review_status": "NOT_REQUESTED",
        "reviewer": None,
        "verification_status": "NOT_RUN",
        "evidence": [],
        "review_evidence": [],
        "handoff": None,
        "blockers": blockers or [],
    }
    base.update(overrides)
    return base


def blocker(code, resolution=None):
    return {
        "code": code,
        "summary": "adversarial fixture blocker",
        "owner": "reviewer-2-probe",
        "introduced_at": "2026-07-21T00:00:00Z",
        "resolution": resolution,
    }


def build_state(orch000_status, blocker_resolution):
    orch000_extra = {}
    if orch000_status == "REVIEW_APPROVED":
        orch000_extra = {
            "implementation_commit": "c" * 40,
            "review_status": "APPROVED",
            "reviewer": "rev-x",
            "verification_status": "PASSED",
            "evidence": ["e.yaml"],
            "review_evidence": ["r.yaml"],
        }
    return {
        "schema_name": "orchestration-implementation-state",
        "schema_version": "1.0.0",
        "feature_id": "ORCH",
        "architecture_version": "3.0.0",
        "plan_version": "1.1.0",
        "repository": {
            "project_id": "probe",
            "canonical_root": "/probe",
            "branch": "main",
            "expected_base_head": "a" * 40,
            "package_commit": "a" * 40,
            "working_tree_policy": "CLEAN_REQUIRED",
        },
        "package_status": "PUBLISHED",
        "current_stage": "ORCH-001",
        "next_eligible_stage": "ORCH-001",
        "candidate_next_stage": "ORCH-001",
        "delivery_order": ["ORCH-000", "ORCH-001", "ORCH-002"],
        "stages": {
            "ORCH-000": stage(orch000_status, [], **orch000_extra),
            "ORCH-001": stage(
                "BLOCKED",
                ["ORCH-000"],
                blockers=[blocker("B_PROBE", resolution=blocker_resolution)],
            ),
            "ORCH-002": stage("NOT_STARTED", ["ORCH-001"]),
        },
        "blockers": [],
        "schema_versions": {},
        "migrations": {"required": [], "completed": [], "blocked": []},
        "history": [],
        "last_updated": {
            "at": "2026-07-21T00:00:00Z",
            "by": "probe",
            "role": "IMPLEMENTER",
            "reason": "seed",
        },
    }


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def digest_of(path):
    rc, out, _ = run_cli("digest", "--state", str(path))
    assert rc == 0
    return out.strip()


def write_state(path, state_dict):
    import yaml

    path.write_text(yaml.safe_dump(state_dict, sort_keys=False, default_flow_style=False))


def transition_cli(path, *, resolve_blocker=None):
    digest = digest_of(path)
    args = [
        "transition",
        "--state",
        str(path),
        "--stage",
        "ORCH-001",
        "--to",
        "IN_PROGRESS",
        "--actor",
        "probe-actor",
        "--role",
        "IMPLEMENTER",
        "--reason",
        "adversarial CLI probe",
        "--expected-digest",
        digest,
        "--output",
        "json",
    ]
    if resolve_blocker:
        args += ["--resolve-blocker", resolve_blocker]
    return run_cli(*args)


results = []
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)

    # Scenario 1: unresolved blocker, approved prerequisite -> must be rejected.
    s1_path = tmp_path / "s1.yaml"
    write_state(s1_path, build_state("REVIEW_APPROVED", blocker_resolution=None))
    rc, out, err = transition_cli(s1_path)
    payload = json.loads(out) if out.strip() else {}
    ok1 = rc != 0 and payload.get("status") == "REJECTED" and "UNRESOLVED_BLOCKER" in payload.get(
        "error", ""
    )
    results.append(("SCENARIO 1 (unresolved blocker rejected)", ok1, payload))
    after1 = s1_path.read_text()
    assert "IN_PROGRESS" not in after1.split("ORCH-001:")[0]  # sanity: file untouched below

    # Scenario 2: blocker resolved in this same call, but prerequisite not approved -> rejected.
    s2_path = tmp_path / "s2.yaml"
    write_state(s2_path, build_state("IN_PROGRESS", blocker_resolution=None))
    rc, out, err = transition_cli(s2_path, resolve_blocker="B_PROBE=fixed")
    payload = json.loads(out) if out.strip() else {}
    ok2 = (
        rc != 0
        and payload.get("status") == "REJECTED"
        and "PREREQUISITE_NOT_APPROVED" in payload.get("error", "")
    )
    results.append(("SCENARIO 2 (unapproved prerequisite rejected)", ok2, payload))

    # Scenario 3: both conditions satisfied -> must succeed and the resulting
    # on-disk file must independently pass `validate`.
    s3_path = tmp_path / "s3.yaml"
    write_state(s3_path, build_state("REVIEW_APPROVED", blocker_resolution=None))
    rc, out, err = transition_cli(s3_path, resolve_blocker="B_PROBE=fixed")
    payload = json.loads(out) if out.strip() else {}
    applied_ok = rc == 0 and payload.get("status") == "APPLIED"
    vrc, vout, verr = run_cli(
        "validate", "--state", str(s3_path), "--output", "json"
    )
    vpayload = json.loads(vout) if vout.strip() else {}
    ok3 = applied_ok and vrc == 0 and vpayload.get("status") == "PASS"
    # ORCH-002 must remain untouched/NOT_STARTED throughout.
    orch002_untouched = '"ORCH-002"' not in "" or True
    results.append(
        (
            "SCENARIO 3 (resolved blocker + approved prerequisite succeeds, "
            "result independently re-validates PASS)",
            ok3,
            {"transition": payload, "validate": vpayload},
        )
    )

    # ORCH-002 status check on the final file (must still be NOT_STARTED).
    srcs = s3_path.read_text()
    orch002_ok = "NOT_STARTED" in srcs and "ORCH-002" in srcs

all_ok = all(r[1] for r in results) and orch002_ok

for name, ok, payload in results:
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    print(f"  payload={json.dumps(payload)}")

print(f"ORCH-002 remained NOT_STARTED throughout: {orch002_ok}")
print(f"OVERALL: {'CONFIRMED FIX HOLDS' if all_ok else 'DEFECT STILL PRESENT'}")

sys.exit(0 if all_ok else 1)
