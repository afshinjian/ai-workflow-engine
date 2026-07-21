#!/usr/bin/env python3
"""F-3 durability demonstration probe (ORCH-001 remediation, remediator-orch-001-2).

Independent of the pytest suite: proves, via the *real* CLI `transition`
subcommand driven against an isolated throwaway copy of the real committed
implementation-state.yaml, that

  (a) the NEW durable real-state regression (validate + the frontier invariant:
      recompute == declared next_eligible_stage; null-or-in-delivery_order;
      prerequisites all REVIEW_APPROVED) STILL PASSES after a correct
      ORCH-001 -> REVIEW_APPROVED transition, when the frontier legitimately
      becomes ORCH-002; and

  (b) the OLD, removed pinned assertion (`recompute_next_eligible(state) ==
      "ORCH-001"`) WOULD HAVE FAILED against that same post-approval state --
      i.e. exactly the F-3 defect this remediation removes.

The real governance document is never modified: the approval is applied only to
a throwaway temp copy. Run from the repository root:

    python3 docs/implementation/orchestration/evidence/ORCH-001/logs/\
20260721T141500Z-claude-code-remediator-orch-001-2-943a0e4c-f3-durability-probe.py
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
MODULE_PATH = REPO_ROOT / "scripts" / "orchestration_feature_state.py"
STATE_PATH = REPO_ROOT / "docs/implementation/orchestration/implementation-state.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("orchestration_feature_state", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ofs = _load_module()


def _assert_frontier_is_durable_invariant(state):
    frontier = ofs.recompute_next_eligible(state)
    assert frontier == state["next_eligible_stage"], (frontier, state["next_eligible_stage"])
    if frontier is None:
        return
    assert frontier in state["delivery_order"], frontier
    stages = state["stages"]
    assert stages[frontier]["status"] != "REVIEW_APPROVED", frontier
    for prereq in stages[frontier]["prerequisites"]:
        assert stages[prereq]["status"] == "REVIEW_APPROVED", (frontier, prereq)


def main() -> int:
    base, _, _ = ofs.load_state_file(STATE_PATH)

    # Sanity: today's real committed frontier is ORCH-001 (REVIEW_REJECTED).
    assert ofs.recompute_next_eligible(base) == "ORCH-001", "expected live frontier ORCH-001"
    print("LIVE: committed frontier is ORCH-001 (ORCH-001 status="
          f"{base['stages']['ORCH-001']['status']})")

    # Build the pre-approval precondition (ORCH-001 VERIFIED, review pending) on a
    # throwaway copy only.
    approvable = copy.deepcopy(base)
    s = approvable["stages"]["ORCH-001"]
    s["status"] = "VERIFIED"
    s["review_status"] = "PENDING"
    s["reviewer"] = None
    s["implementation_commit"] = None
    assert ofs.recompute_next_eligible(approvable) == "ORCH-001"
    _assert_frontier_is_durable_invariant(approvable)
    print("PRE-APPROVAL: durable invariant holds; frontier still ORCH-001")

    with tempfile.TemporaryDirectory() as td:
        tmp_state = Path(td) / "implementation-state.yaml"
        tmp_state.write_text(ofs.dump_state(approvable), encoding="utf-8")
        digest = ofs.compute_digest(tmp_state.read_bytes())

        proc = subprocess.run(
            [
                sys.executable, str(MODULE_PATH), "transition",
                "--state", str(tmp_state),
                "--stage", "ORCH-001",
                "--to", "REVIEW_APPROVED",
                "--actor", "sim-independent-reviewer",
                "--role", "REVIEWER",
                "--action", "SIMULATED_APPROVE_ORCH_001",
                "--reason", "F-3 durability probe",
                "--at", "2026-07-21T00:00:00Z",
                "--reviewer", "sim-independent-reviewer",
                "--implementation-commit", "b" * 40,
                "--add-review-evidence", "reviews/ORCH-001/simulated.yaml",
                "--expected-digest", digest,
                "--output", "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        payload = json.loads(proc.stdout)
        assert payload["status"] == "APPLIED", payload
        assert payload["new_next_eligible_stage"] == "ORCH-002", payload
        print("REAL CLI: ORCH-001 -> REVIEW_APPROVED APPLIED; "
              f"new_next_eligible_stage={payload['new_next_eligible_stage']}")

        approved, _, _ = ofs.load_state_file(tmp_state)

    # (a) NEW durable regression still passes on the post-approval state.
    assert ofs.validate_state(approved).passed, ofs.validate_state(approved).errors
    _assert_frontier_is_durable_invariant(approved)
    assert ofs.recompute_next_eligible(approved) == "ORCH-002"
    print("POST-APPROVAL: NEW durable regression PASSES "
          "(validate + frontier invariant; frontier now ORCH-002)")

    # (b) OLD pinned assertion would now FAIL -- this is the F-3 defect, removed.
    old_pinned_would_pass = ofs.recompute_next_eligible(approved) == "ORCH-001"
    assert not old_pinned_would_pass, "old pinned assertion unexpectedly still holds"
    print("POST-APPROVAL: OLD pinned assertion (== 'ORCH-001') WOULD FAIL "
          "(assert 'ORCH-002' == 'ORCH-001') -- F-3 fixed")

    # Real committed document is untouched.
    live, _, _ = ofs.load_state_file(STATE_PATH)
    assert ofs.recompute_next_eligible(live) == "ORCH-001"
    print("UNTOUCHED: real committed frontier still ORCH-001 after simulation")

    print("F3_DURABILITY_PROBE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
