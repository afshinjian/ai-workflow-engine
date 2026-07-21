#!/usr/bin/env python3
"""Adversarial probe for ORCH-001 review: does apply_transition enforce
session-protocol.md section 2's row "BLOCKED | IN_PROGRESS | appropriate
role; blocker resolution is evidenced and prerequisites still approved"?

Constructs a minimal, schema-shaped state with ORCH-000 BLOCKED by an
unresolved stage-level blocker, then attempts BLOCKED -> IN_PROGRESS with
no resolve_blockers argument at all. If this succeeds and the resulting
state still validates cleanly under the tool's own validate_state, the
validator is authorizing an illegal transition per the exact row it is
supposed to enforce.
"""
import sys

sys.path.insert(0, "scripts")
import orchestration_feature_state as ofs


def make_blocker(code):
    return {
        "code": code,
        "summary": "s",
        "owner": "o",
        "introduced_at": "2026-07-21T00:00:00Z",
        "resolution": None,
    }


state = {
    "schema_name": "orchestration-implementation-state",
    "schema_version": "1.0.0",
    "feature_id": "ORCH",
    "architecture_version": "3.0.0",
    "plan_version": "1.1.0",
    "repository": {
        "project_id": "p",
        "canonical_root": "/x",
        "branch": "main",
        "expected_base_head": "a" * 40,
        "package_commit": "a" * 40,
        "working_tree_policy": "CLEAN_REQUIRED",
    },
    "package_status": "PUBLISHED",
    "current_stage": "ORCH-000",
    "next_eligible_stage": "ORCH-000",
    "candidate_next_stage": "ORCH-000",
    "delivery_order": ["ORCH-000", "ORCH-001"],
    "stages": {
        "ORCH-000": {
            "title": "t",
            "status": "IN_PROGRESS",
            "prerequisites": [],
            "expected_base_head": "a" * 40,
            "implementation_commit": None,
            "implementer": "impl-1",
            "review_status": "NOT_REQUESTED",
            "reviewer": None,
            "verification_status": "NOT_RUN",
            "evidence": [],
            "review_evidence": [],
            "handoff": None,
            "blockers": [],
        },
        "ORCH-001": {
            "title": "t2",
            "status": "NOT_STARTED",
            "prerequisites": ["ORCH-000"],
            "expected_base_head": None,
            "implementation_commit": None,
            "implementer": None,
            "review_status": "NOT_REQUESTED",
            "reviewer": None,
            "verification_status": "NOT_RUN",
            "evidence": [],
            "review_evidence": [],
            "handoff": None,
            "blockers": [],
        },
    },
    "blockers": [],
    "schema_versions": {},
    "migrations": {"required": [], "completed": [], "blocked": []},
    "history": [],
    "last_updated": {
        "at": "2026-07-21T00:00:00Z",
        "by": "x",
        "role": "IMPLEMENTER",
        "reason": "r",
    },
}

blocked = ofs.apply_transition(
    state,
    stage_id="ORCH-000",
    to_status="BLOCKED",
    actor="impl-1",
    role="IMPLEMENTER",
    action="BLOCK",
    reason="test",
    at="2026-07-21T00:00:00Z",
    add_blockers=[make_blocker("B1")],
)
print("after BLOCK: status=%r blocker.resolution=%r" % (
    blocked["stages"]["ORCH-000"]["status"],
    blocked["stages"]["ORCH-000"]["blockers"][0]["resolution"],
))

# Resume WITHOUT resolving the blocker and WITHOUT re-checking prerequisites.
resumed = ofs.apply_transition(
    blocked,
    stage_id="ORCH-000",
    to_status="IN_PROGRESS",
    actor="impl-1",
    role="IMPLEMENTER",
    action="RESUME",
    reason="test",
    at="2026-07-21T00:01:00Z",
)
print("after RESUME (no resolve_blockers passed): status=%r" % (
    resumed["stages"]["ORCH-000"]["status"],
))
print("blocker still unresolved: %r" % (
    resumed["stages"]["ORCH-000"]["blockers"][0]["resolution"],
))
result = ofs.validate_state(resumed)
print("validate_state(resumed).passed = %r, errors = %r" % (result.passed, result.errors))

assert resumed["stages"]["ORCH-000"]["status"] == "IN_PROGRESS", "expected resume to succeed (this is the defect)"
assert resumed["stages"]["ORCH-000"]["blockers"][0]["resolution"] is None, "expected blocker to remain unresolved"
assert result.passed, "expected validate_state to report no error (this is the defect: an illegal-per-protocol state passes validation)"
print("CONFIRMED: apply_transition allows BLOCKED -> IN_PROGRESS with an unresolved stage blocker, "
      "and validate_state raises no error on the result.")
