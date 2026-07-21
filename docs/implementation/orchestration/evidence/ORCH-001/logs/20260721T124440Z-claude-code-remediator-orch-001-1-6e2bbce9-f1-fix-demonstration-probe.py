#!/usr/bin/env python3
"""Demonstration that F-1 is fixed: BLOCKED -> IN_PROGRESS now requires both
blocker resolution and prerequisite REVIEW_APPROVED closure."""
import sys
sys.path.insert(0, "scripts")
import orchestration_feature_state as ofs


def make_blocker(code, resolution=None):
    return {"code": code, "summary": "s", "owner": "o", "introduced_at": "2026-07-21T00:00:00Z", "resolution": resolution}


def base_state(orch000_status):
    orch000 = {"title": "t", "status": orch000_status, "prerequisites": [],
               "expected_base_head": "a" * 40, "implementer": "impl-1",
               "review_status": "NOT_REQUESTED", "reviewer": None,
               "verification_status": "NOT_RUN", "evidence": [], "review_evidence": [],
               "handoff": None, "blockers": [], "implementation_commit": None}
    if orch000_status == "REVIEW_APPROVED":
        orch000.update(implementation_commit="c" * 40, review_status="APPROVED",
                        reviewer="rev-1", verification_status="PASSED",
                        evidence=["e.yaml"], review_evidence=["r.yaml"])
    return {
        "schema_name": "orchestration-implementation-state",
        "schema_version": "1.0.0",
        "feature_id": "ORCH",
        "architecture_version": "3.0.0",
        "plan_version": "1.1.0",
        "repository": {"project_id": "p", "canonical_root": "/x", "branch": "main",
                        "expected_base_head": "a" * 40, "package_commit": "a" * 40,
                        "working_tree_policy": "CLEAN_REQUIRED"},
        "package_status": "PUBLISHED",
        "current_stage": "ORCH-000",
        "next_eligible_stage": "ORCH-000",
        "candidate_next_stage": "ORCH-000",
        "delivery_order": ["ORCH-000", "ORCH-001"],
        "stages": {
            "ORCH-000": orch000,
            "ORCH-001": {"title": "t2", "status": "BLOCKED", "prerequisites": ["ORCH-000"],
                         "expected_base_head": "a" * 40, "implementation_commit": None,
                         "implementer": "impl-1", "review_status": "NOT_REQUESTED", "reviewer": None,
                         "verification_status": "NOT_RUN", "evidence": [], "review_evidence": [],
                         "handoff": None, "blockers": [make_blocker("B1")]},
        },
        "blockers": [],
        "schema_versions": {},
        "migrations": {"required": [], "completed": [], "blocked": []},
        "history": [],
        "last_updated": {"at": "2026-07-21T00:00:00Z", "by": "x", "role": "IMPLEMENTER", "reason": "r"},
    }


def transition(state, **kwargs):
    return ofs.apply_transition(
        state, stage_id="ORCH-001", to_status="IN_PROGRESS", actor="impl-1",
        role="IMPLEMENTER", action="RESUME", reason="test", at="2026-07-21T00:01:00Z", **kwargs,
    )


# Scenario 1: unresolved blocker -> must fail.
try:
    transition(base_state("REVIEW_APPROVED"))
    print("SCENARIO 1 FAIL: expected TransitionError, none raised")
except ofs.TransitionError as e:
    print(f"SCENARIO 1 PASS: rejected with {e}")

# Scenario 2: blocker resolved but prerequisite not REVIEW_APPROVED -> must fail.
try:
    transition(base_state("IN_PROGRESS"), resolve_blockers={"B1": "fixed"})
    print("SCENARIO 2 FAIL: expected TransitionError, none raised")
except ofs.TransitionError as e:
    print(f"SCENARIO 2 PASS: rejected with {e}")

# Scenario 3: blocker resolved AND prerequisite REVIEW_APPROVED -> must succeed.
result = transition(base_state("REVIEW_APPROVED"), resolve_blockers={"B1": "fixed"})
assert result["stages"]["ORCH-001"]["status"] == "IN_PROGRESS"
validation = ofs.validate_state(result)
print(f"SCENARIO 3 PASS: transition succeeded, status=IN_PROGRESS, validate_state.passed={validation.passed} errors={validation.errors}")
