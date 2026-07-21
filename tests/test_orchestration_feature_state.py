"""Tests for ORCH-001's durable feature-state validator (scripts/orchestration_feature_state.py).

Uses isolated temporary files only; never reads or writes the real
docs/implementation/orchestration/implementation-state.yaml except via one
read-only regression check that the actual committed file validates cleanly.
"""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "orchestration_feature_state.py"
REPO_ROOT = MODULE_PATH.parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location("orchestration_feature_state", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ofs = _load_module()


# --------------------------------------------------------------------------
# Fixtures: a small, self-consistent two-stage state document
# --------------------------------------------------------------------------


def make_blocker(code="B_TEST", resolution=None):
    return {
        "code": code,
        "summary": "test blocker",
        "owner": "tester",
        "introduced_at": "2026-07-21T00:00:00Z",
        "resolution": resolution,
    }


def make_stage(
    title="Test stage",
    status="NOT_STARTED",
    prerequisites=None,
    expected_base_head=None,
    implementation_commit=None,
    implementer=None,
    review_status="NOT_REQUESTED",
    reviewer=None,
    verification_status="NOT_RUN",
    evidence=None,
    review_evidence=None,
    handoff=None,
    blockers=None,
):
    return {
        "title": title,
        "status": status,
        "prerequisites": prerequisites or [],
        "expected_base_head": expected_base_head,
        "implementation_commit": implementation_commit,
        "implementer": implementer,
        "review_status": review_status,
        "reviewer": reviewer,
        "verification_status": verification_status,
        "evidence": evidence or [],
        "review_evidence": review_evidence or [],
        "handoff": handoff,
        "blockers": blockers or [],
    }


def make_state():
    sha_a = "a" * 40
    return {
        "schema_name": "orchestration-implementation-state",
        "schema_version": "1.0.0",
        "feature_id": "ORCH",
        "architecture_version": "3.0.0",
        "plan_version": "1.1.0",
        "repository": {
            "project_id": "test-project",
            "canonical_root": "/tmp/test-project",
            "branch": "main",
            "expected_base_head": sha_a,
            "package_commit": sha_a,
            "working_tree_policy": "CLEAN_REQUIRED",
        },
        "package_status": "PUBLISHED",
        "current_stage": "ORCH-000",
        "next_eligible_stage": "ORCH-000",
        "candidate_next_stage": "ORCH-000",
        "delivery_order": ["ORCH-000", "ORCH-001"],
        "stages": {
            "ORCH-000": make_stage(
                status="NOT_STARTED",
            ),
            "ORCH-001": make_stage(
                title="Second stage",
                status="NOT_STARTED",
                prerequisites=["ORCH-000"],
            ),
        },
        "blockers": [],
        "schema_versions": {"implementation-state": "1.0.0"},
        "migrations": {"required": [], "completed": [], "blocked": []},
        "unresolved_risks": [],
        "history": [],
        "last_updated": {
            "at": "2026-07-21T00:00:00Z",
            "by": "tester",
            "role": "HUMAN_OWNER",
            "reason": "initial fixture",
        },
    }


def approve_stage(state, stage_id, implementer="impl-1", reviewer="rev-1", commit=None):
    stage = state["stages"][stage_id]
    stage["status"] = "REVIEW_APPROVED"
    stage["implementer"] = implementer
    stage["reviewer"] = reviewer
    stage["review_status"] = "APPROVED"
    stage["verification_status"] = "PASSED"
    stage["evidence"] = ["evidence/x.yaml"]
    stage["review_evidence"] = ["reviews/x.yaml"]
    stage["implementation_commit"] = commit or ("c" * 40)
    stage["expected_base_head"] = "a" * 40
    state["history"].append(
        {
            "sequence": len(state["history"]) + 1,
            "at": "2026-07-21T00:00:00Z",
            "actor": implementer,
            "role": "IMPLEMENTER",
            "action": f"IMPLEMENTED_{stage_id}",
            "from": "NOT_STARTED",
            "to": "VERIFIED",
            "evidence": [],
        }
    )
    state["history"].append(
        {
            "sequence": len(state["history"]) + 1,
            "at": "2026-07-21T00:00:00Z",
            "actor": reviewer,
            "role": "REVIEWER",
            "action": f"REVIEW_APPROVED_{stage_id}",
            "from": "VERIFIED",
            "to": "REVIEW_APPROVED",
            "evidence": [],
        }
    )
    return state


# --------------------------------------------------------------------------
# Schema / structural validation
# --------------------------------------------------------------------------


class TestSchemaValidation:
    def test_minimal_state_passes(self):
        result = ofs.validate_state(make_state())
        assert result.passed, result.errors

    def test_missing_required_top_level_field_fails(self):
        state = make_state()
        del state["package_status"]
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("package_status" in e for e in result.errors)

    def test_unknown_top_level_field_fails(self):
        state = make_state()
        state["bogus_field"] = 1
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("bogus_field" in e for e in result.errors)

    def test_bad_const_fields_fail(self):
        state = make_state()
        state["architecture_version"] = "9.9.9"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("architecture_version" in e for e in result.errors)

    def test_bad_stage_status_enum_fails(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "WEIRD"
        result = ofs.validate_state(state)
        assert not result.passed

    def test_bad_sha_pattern_fails(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "IN_PROGRESS"
        state["stages"]["ORCH-000"]["expected_base_head"] = "not-a-sha"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("expected_base_head" in e for e in result.errors)

    def test_unknown_stage_field_fails(self):
        state = make_state()
        state["stages"]["ORCH-000"]["extra"] = True
        result = ofs.validate_state(state)
        assert not result.passed

    def test_duplicate_evidence_entries_fail(self):
        state = make_state()
        state["stages"]["ORCH-000"]["evidence"] = ["a.yaml", "a.yaml"]
        result = ofs.validate_state(state)
        assert not result.passed


# --------------------------------------------------------------------------
# Semantic rules
# --------------------------------------------------------------------------


class TestSemanticValidation:
    def test_prerequisite_cycle_detected(self):
        state = make_state()
        state["stages"]["ORCH-000"]["prerequisites"] = ["ORCH-001"]
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("cycle" in e for e in result.errors)

    def test_unknown_prerequisite_reference_detected(self):
        state = make_state()
        state["stages"]["ORCH-001"]["prerequisites"] = ["ORCH-999"]
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("unknown stage" in e for e in result.errors)

    def test_delivery_order_missing_stage_detected(self):
        state = make_state()
        state["delivery_order"] = ["ORCH-000"]
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("delivery_order" in e for e in result.errors)

    def test_next_eligible_stage_mismatch_detected(self):
        state = make_state()
        state["next_eligible_stage"] = "ORCH-001"
        state["candidate_next_stage"] = "ORCH-001"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("next_eligible_stage" in e for e in result.errors)

    def test_candidate_next_stage_mismatch_detected(self):
        state = make_state()
        state["candidate_next_stage"] = "ORCH-001"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("candidate_next_stage" in e for e in result.errors)

    def test_open_global_blocker_forces_next_eligible_null(self):
        state = make_state()
        state["blockers"] = [make_blocker()]
        state["next_eligible_stage"] = None
        state["candidate_next_stage"] = None
        result = ofs.validate_state(state)
        assert result.passed, result.errors
        assert ofs.recompute_next_eligible(state) is None

    def test_reviewer_equals_implementer_on_approval_detected(self):
        state = make_state()
        approve_stage(state, "ORCH-000", implementer="same-actor", reviewer="same-actor")
        state["next_eligible_stage"] = "ORCH-001"
        state["candidate_next_stage"] = "ORCH-001"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("reviewer must differ from implementer" in e for e in result.errors)

    def test_review_approved_requires_implementation_commit(self):
        state = make_state()
        approve_stage(state, "ORCH-000")
        state["stages"]["ORCH-000"]["implementation_commit"] = None
        state["next_eligible_stage"] = "ORCH-001"
        state["candidate_next_stage"] = "ORCH-001"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("implementation_commit" in e for e in result.errors)

    def test_verified_requires_passed_verification_and_evidence(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "VERIFIED"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("verification_status" in e or "evidence" in e for e in result.errors)

    def test_non_reviewer_role_on_verified_to_review_approved_history_detected(self):
        state = make_state()
        approve_stage(state, "ORCH-000")
        state["history"][-1]["role"] = "IMPLEMENTER"
        state["next_eligible_stage"] = "ORCH-001"
        state["candidate_next_stage"] = "ORCH-001"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("requires role REVIEWER" in e for e in result.errors)

    def test_non_contiguous_history_sequence_detected(self):
        state = make_state()
        state["history"] = [
            {
                "sequence": 1,
                "at": "2026-07-21T00:00:00Z",
                "actor": "a",
                "role": "HUMAN_OWNER",
                "action": "X",
                "from": None,
                "to": "Y",
                "evidence": [],
            },
            {
                "sequence": 3,
                "at": "2026-07-21T00:00:00Z",
                "actor": "a",
                "role": "HUMAN_OWNER",
                "action": "X",
                "from": "Y",
                "to": "Z",
                "evidence": [],
            },
        ]
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("contiguous" in e for e in result.errors)

    def test_expected_base_head_required_once_started(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "IN_PROGRESS"
        result = ofs.validate_state(state)
        assert not result.passed
        assert any("expected_base_head" in e for e in result.errors)

    def test_plan_stage_id_cross_check(self, tmp_path):
        state = make_state()
        plan_text = (
            "## 3. Ordered stage graph\n\n"
            "| ID | Title | Prerequisites | Principal output |\n"
            "|---|---|---|---|\n"
            "| ORCH-000 | A | none | x |\n"
            "| ORCH-001 | B | 000 | y |\n"
        )
        assert ofs.extract_plan_stage_ids(plan_text) == {"ORCH-000", "ORCH-001"}
        result = ofs.validate_state(state, plan_text=plan_text)
        assert result.passed, result.errors

    def test_plan_stage_id_cross_check_detects_missing_stage(self):
        state = make_state()
        plan_text = (
            "| ORCH-000 | A | none | x |\n| ORCH-001 | B | 000 | y |\n| ORCH-002 | C | 001 | z |\n"
        )
        result = ofs.validate_state(state, plan_text=plan_text)
        assert not result.passed
        assert any("missing stage keys" in e for e in result.errors)

    def test_history_append_only_cross_version_detects_rewrite(self):
        previous = make_state()
        previous["history"] = [
            {
                "sequence": 1,
                "at": "2026-07-21T00:00:00Z",
                "actor": "a",
                "role": "HUMAN_OWNER",
                "action": "X",
                "from": None,
                "to": "Y",
                "evidence": [],
            }
        ]
        current = copy.deepcopy(previous)
        current["history"][0]["action"] = "REWRITTEN"
        errors = ofs.validate_history_append_only(previous["history"], current["history"])
        assert any("differs from the previously committed entry" in e for e in errors)

    def test_history_append_only_cross_version_accepts_pure_append(self):
        previous_entry = {
            "sequence": 1,
            "at": "2026-07-21T00:00:00Z",
            "actor": "a",
            "role": "HUMAN_OWNER",
            "action": "X",
            "from": None,
            "to": "Y",
            "evidence": [],
        }
        previous_history = [previous_entry]
        current_history = [previous_entry, dict(previous_entry, sequence=2, action="Z")]
        assert ofs.validate_history_append_only(previous_history, current_history) == []

    def test_history_append_only_cross_version_detects_truncation(self):
        entry = {
            "sequence": 1,
            "at": "2026-07-21T00:00:00Z",
            "actor": "a",
            "role": "HUMAN_OWNER",
            "action": "X",
            "from": None,
            "to": "Y",
            "evidence": [],
        }
        errors = ofs.validate_history_append_only([entry, dict(entry, sequence=2)], [entry])
        assert any("shorter" in e for e in errors)


# --------------------------------------------------------------------------
# Legal transition table
# --------------------------------------------------------------------------


class TestTransitionLegality:
    @pytest.mark.parametrize(
        "from_status,to_status,role",
        [
            ("NOT_STARTED", "IN_PROGRESS", "IMPLEMENTER"),
            ("IN_PROGRESS", "IMPLEMENTED", "IMPLEMENTER"),
            ("IMPLEMENTED", "VERIFIED", "IMPLEMENTER"),
            ("VERIFIED", "REVIEW_APPROVED", "REVIEWER"),
            ("VERIFIED", "REVIEW_REJECTED", "REVIEWER"),
            ("REVIEW_REJECTED", "IN_PROGRESS", "REMEDIATOR"),
            ("BLOCKED", "IN_PROGRESS", "IMPLEMENTER"),
            ("IN_PROGRESS", "BLOCKED", "REMEDIATOR"),
            ("NOT_STARTED", "SUPERSEDED", "HUMAN_OWNER"),
            ("REVIEW_REJECTED", "SUPERSEDED", "ARCHITECT"),
        ],
    )
    def test_legal_edges_accepted(self, from_status, to_status, role):
        assert ofs.check_transition_legal(from_status, to_status, role) is None

    @pytest.mark.parametrize(
        "from_status,to_status,role",
        [
            ("NOT_STARTED", "VERIFIED", "IMPLEMENTER"),
            ("VERIFIED", "IMPLEMENTED", "IMPLEMENTER"),
            ("IMPLEMENTED", "REVIEW_APPROVED", "REVIEWER"),
            ("REVIEW_APPROVED", "IN_PROGRESS", "REMEDIATOR"),
        ],
    )
    def test_illegal_edges_rejected(self, from_status, to_status, role):
        reason = ofs.check_transition_legal(from_status, to_status, role)
        assert reason is not None
        assert "ILLEGAL_TRANSITION" in reason

    @pytest.mark.parametrize(
        "from_status,to_status,role",
        [
            ("NOT_STARTED", "IN_PROGRESS", "REVIEWER"),
            ("VERIFIED", "REVIEW_APPROVED", "IMPLEMENTER"),
            ("REVIEW_REJECTED", "IN_PROGRESS", "IMPLEMENTER"),
            ("NOT_STARTED", "SUPERSEDED", "IMPLEMENTER"),
        ],
    )
    def test_wrong_role_rejected(self, from_status, to_status, role):
        reason = ofs.check_transition_legal(from_status, to_status, role)
        assert reason is not None
        assert "ROLE_NOT_AUTHORIZED" in reason


# --------------------------------------------------------------------------
# apply_transition (pure function)
# --------------------------------------------------------------------------


class TestApplyTransition:
    def test_start_stage_requires_unique_eligibility(self):
        state = make_state()
        with pytest.raises(ofs.TransitionError, match="NOT_UNIQUELY_ELIGIBLE"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-001",  # ORCH-000 is the sole eligible stage, not ORCH-001
                to_status="IN_PROGRESS",
                actor="impl-1",
                role="IMPLEMENTER",
                action="START",
                reason="test",
                at="2026-07-21T00:00:00Z",
                expected_base_head="a" * 40,
            )

    def test_start_stage_requires_expected_base_head(self):
        state = make_state()
        with pytest.raises(ofs.TransitionError, match="MISSING_EXPECTED_BASE_HEAD"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-000",
                to_status="IN_PROGRESS",
                actor="impl-1",
                role="IMPLEMENTER",
                action="START",
                reason="test",
                at="2026-07-21T00:00:00Z",
            )

    def test_start_stage_success_appends_history_and_sets_fields(self):
        state = make_state()
        new_state = ofs.apply_transition(
            state,
            stage_id="ORCH-000",
            to_status="IN_PROGRESS",
            actor="impl-1",
            role="IMPLEMENTER",
            action="STARTED_ORCH_000",
            reason="starting",
            at="2026-07-21T00:00:00Z",
            expected_base_head="a" * 40,
            evidence=["evidence/ORCH-000/x.yaml"],
        )
        assert new_state["stages"]["ORCH-000"]["status"] == "IN_PROGRESS"
        assert new_state["stages"]["ORCH-000"]["implementer"] == "impl-1"
        assert new_state["stages"]["ORCH-000"]["expected_base_head"] == "a" * 40
        assert len(new_state["history"]) == 1
        assert new_state["history"][0] == {
            "sequence": 1,
            "at": "2026-07-21T00:00:00Z",
            "actor": "impl-1",
            "role": "IMPLEMENTER",
            "action": "STARTED_ORCH_000",
            "from": "NOT_STARTED",
            "to": "IN_PROGRESS",
            "evidence": ["evidence/ORCH-000/x.yaml"],
        }
        # original state must be untouched (pure function)
        assert state["stages"]["ORCH-000"]["status"] == "NOT_STARTED"
        assert state["history"] == []

    def test_reviewer_equals_implementer_rejected(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "VERIFIED"
        state["stages"]["ORCH-000"]["implementer"] = "same-actor"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-000"]["verification_status"] = "PASSED"
        state["stages"]["ORCH-000"]["evidence"] = ["e.yaml"]
        with pytest.raises(ofs.TransitionError, match="REVIEWER_EQUALS_IMPLEMENTER"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-000",
                to_status="REVIEW_APPROVED",
                actor="same-actor",
                role="REVIEWER",
                action="APPROVE",
                reason="test",
                at="2026-07-21T00:00:00Z",
                implementation_commit="c" * 40,
                add_review_evidence=["reviews/x.yaml"],
            )

    def test_review_approved_requires_implementation_commit(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "VERIFIED"
        state["stages"]["ORCH-000"]["implementer"] = "impl-1"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-000"]["verification_status"] = "PASSED"
        state["stages"]["ORCH-000"]["evidence"] = ["e.yaml"]
        with pytest.raises(ofs.TransitionError, match="MISSING_IMPLEMENTATION_COMMIT"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-000",
                to_status="REVIEW_APPROVED",
                actor="rev-1",
                role="REVIEWER",
                action="APPROVE",
                reason="test",
                at="2026-07-21T00:00:00Z",
                add_review_evidence=["reviews/x.yaml"],
            )

    def test_review_approved_success_recomputes_next_eligible(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "VERIFIED"
        state["stages"]["ORCH-000"]["implementer"] = "impl-1"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-000"]["verification_status"] = "PASSED"
        state["stages"]["ORCH-000"]["evidence"] = ["e.yaml"]
        new_state = ofs.apply_transition(
            state,
            stage_id="ORCH-000",
            to_status="REVIEW_APPROVED",
            actor="rev-1",
            role="REVIEWER",
            action="APPROVE",
            reason="test",
            at="2026-07-21T00:00:00Z",
            implementation_commit="c" * 40,
            add_review_evidence=["reviews/x.yaml"],
        )
        assert new_state["stages"]["ORCH-000"]["status"] == "REVIEW_APPROVED"
        assert new_state["stages"]["ORCH-000"]["review_status"] == "APPROVED"
        assert new_state["stages"]["ORCH-000"]["reviewer"] == "rev-1"
        assert new_state["next_eligible_stage"] == "ORCH-001"
        assert new_state["candidate_next_stage"] == "ORCH-001"
        assert new_state["current_stage"] == "ORCH-001"
        result = ofs.validate_state(new_state)
        assert result.passed, result.errors

    def test_blocked_requires_a_blocker(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "IN_PROGRESS"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        with pytest.raises(ofs.TransitionError, match="MISSING_BLOCKER"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-000",
                to_status="BLOCKED",
                actor="impl-1",
                role="IMPLEMENTER",
                action="BLOCK",
                reason="test",
                at="2026-07-21T00:00:00Z",
            )

    def test_blocked_with_blocker_succeeds_and_resolve_reopens(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "IN_PROGRESS"
        state["stages"]["ORCH-000"]["implementer"] = "impl-1"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        blocked_state = ofs.apply_transition(
            state,
            stage_id="ORCH-000",
            to_status="BLOCKED",
            actor="impl-1",
            role="IMPLEMENTER",
            action="BLOCK",
            reason="test",
            at="2026-07-21T00:00:00Z",
            add_blockers=[make_blocker(code="B_ISSUE")],
        )
        assert blocked_state["stages"]["ORCH-000"]["status"] == "BLOCKED"
        assert blocked_state["stages"]["ORCH-000"]["blockers"][0]["resolution"] is None

        resumed_state = ofs.apply_transition(
            blocked_state,
            stage_id="ORCH-000",
            to_status="IN_PROGRESS",
            actor="impl-1",
            role="IMPLEMENTER",
            action="RESUME",
            reason="unblocked",
            at="2026-07-21T00:01:00Z",
            resolve_blockers={"B_ISSUE": "fixed"},
        )
        assert resumed_state["stages"]["ORCH-000"]["status"] == "IN_PROGRESS"
        assert resumed_state["stages"]["ORCH-000"]["blockers"][0]["resolution"] == "fixed"

    def test_blocked_resume_rejected_with_unresolved_blocker(self):
        # F-1 regression: BLOCKED -> IN_PROGRESS must fail while any blocker
        # remains unresolved, even though the transition table lists no role
        # restriction for this edge.
        state = make_state()
        approve_stage(state, "ORCH-000")
        state["stages"]["ORCH-001"]["status"] = "BLOCKED"
        state["stages"]["ORCH-001"]["implementer"] = "impl-1"
        state["stages"]["ORCH-001"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-001"]["blockers"] = [make_blocker(code="B_ISSUE")]
        with pytest.raises(ofs.TransitionError, match="UNRESOLVED_BLOCKER"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-001",
                to_status="IN_PROGRESS",
                actor="impl-1",
                role="IMPLEMENTER",
                action="RESUME",
                reason="test",
                at="2026-07-21T00:00:00Z",
            )

    def test_blocked_resume_rejected_with_unapproved_prerequisite(self):
        # F-1 regression: BLOCKED -> IN_PROGRESS must fail unless every
        # prerequisite still recomputes as REVIEW_APPROVED, even when the
        # stage's own blockers are all resolved by this same call.
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "IN_PROGRESS"
        state["stages"]["ORCH-000"]["implementer"] = "impl-1"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-001"]["status"] = "BLOCKED"
        state["stages"]["ORCH-001"]["implementer"] = "impl-1"
        state["stages"]["ORCH-001"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-001"]["blockers"] = [make_blocker(code="B_ISSUE")]
        with pytest.raises(ofs.TransitionError, match="PREREQUISITE_NOT_APPROVED"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-001",
                to_status="IN_PROGRESS",
                actor="impl-1",
                role="IMPLEMENTER",
                action="RESUME",
                reason="test",
                at="2026-07-21T00:00:00Z",
                resolve_blockers={"B_ISSUE": "fixed"},
            )

    def test_blocked_resume_succeeds_when_blockers_resolved_and_prerequisite_approved(self):
        # F-1 regression, positive case: the transition succeeds exactly when
        # both conditions from session-protocol.md's BLOCKED row hold.
        state = make_state()
        approve_stage(state, "ORCH-000")
        state["stages"]["ORCH-001"]["status"] = "BLOCKED"
        state["stages"]["ORCH-001"]["implementer"] = "impl-1"
        state["stages"]["ORCH-001"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-001"]["blockers"] = [make_blocker(code="B_ISSUE")]
        new_state = ofs.apply_transition(
            state,
            stage_id="ORCH-001",
            to_status="IN_PROGRESS",
            actor="impl-1",
            role="IMPLEMENTER",
            action="RESUME",
            reason="test",
            at="2026-07-21T00:00:00Z",
            resolve_blockers={"B_ISSUE": "fixed"},
        )
        assert new_state["stages"]["ORCH-001"]["status"] == "IN_PROGRESS"
        assert new_state["stages"]["ORCH-001"]["blockers"][0]["resolution"] == "fixed"
        result = ofs.validate_state(new_state)
        assert result.passed, result.errors

    def test_blocked_resume_succeeds_with_already_resolved_blocker_not_reresolved(self):
        # A blocker resolved by a prior call (resolution already set) must
        # not force a caller to re-supply resolve_blockers for it.
        state = make_state()
        approve_stage(state, "ORCH-000")
        state["stages"]["ORCH-001"]["status"] = "BLOCKED"
        state["stages"]["ORCH-001"]["implementer"] = "impl-1"
        state["stages"]["ORCH-001"]["expected_base_head"] = "a" * 40
        state["stages"]["ORCH-001"]["blockers"] = [
            make_blocker(code="B_ISSUE", resolution="already fixed")
        ]
        new_state = ofs.apply_transition(
            state,
            stage_id="ORCH-001",
            to_status="IN_PROGRESS",
            actor="impl-1",
            role="IMPLEMENTER",
            action="RESUME",
            reason="test",
            at="2026-07-21T00:00:00Z",
        )
        assert new_state["stages"]["ORCH-001"]["status"] == "IN_PROGRESS"
        result = ofs.validate_state(new_state)
        assert result.passed, result.errors

    def test_global_blocker_forces_next_eligible_none(self):
        state = make_state()
        state["stages"]["ORCH-000"]["status"] = "IN_PROGRESS"
        state["stages"]["ORCH-000"]["implementer"] = "impl-1"
        state["stages"]["ORCH-000"]["expected_base_head"] = "a" * 40
        new_state = ofs.apply_transition(
            state,
            stage_id="ORCH-000",
            to_status="BLOCKED",
            actor="impl-1",
            role="IMPLEMENTER",
            action="BLOCK",
            reason="test",
            at="2026-07-21T00:00:00Z",
            add_blockers=[make_blocker(code="B_LOCAL")],
            add_global_blockers=[make_blocker(code="B_GLOBAL")],
        )
        assert new_state["next_eligible_stage"] is None
        assert new_state["candidate_next_stage"] is None

    def test_apply_transition_never_mutates_input_state(self):
        state = make_state()
        before = copy.deepcopy(state)
        ofs.apply_transition(
            state,
            stage_id="ORCH-000",
            to_status="IN_PROGRESS",
            actor="impl-1",
            role="IMPLEMENTER",
            action="START",
            reason="test",
            at="2026-07-21T00:00:00Z",
            expected_base_head="a" * 40,
        )
        assert state == before

    def test_unknown_stage_rejected(self):
        state = make_state()
        with pytest.raises(ofs.TransitionError, match="UNKNOWN_STAGE"):
            ofs.apply_transition(
                state,
                stage_id="ORCH-999",
                to_status="IN_PROGRESS",
                actor="impl-1",
                role="IMPLEMENTER",
                action="START",
                reason="test",
                at="2026-07-21T00:00:00Z",
                expected_base_head="a" * 40,
            )


# --------------------------------------------------------------------------
# CAS digest and atomic write (fault/concurrency)
# --------------------------------------------------------------------------


class TestDigestAndAtomicWrite:
    def test_digest_is_deterministic_and_content_sensitive(self):
        d1 = ofs.compute_digest(b"hello")
        d2 = ofs.compute_digest(b"hello")
        d3 = ofs.compute_digest(b"hello!")
        assert d1 == d2
        assert d1 != d3
        assert d1.startswith("sha256:")

    def test_write_state_atomic_leaves_no_temp_file_on_success(self, tmp_path):
        target = tmp_path / "state.yaml"
        target.write_text("placeholder\n", encoding="utf-8")
        ofs.write_state_atomic(target, make_state())
        remaining = list(tmp_path.iterdir())
        assert remaining == [target]
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded["schema_name"] == "orchestration-implementation-state"

    def test_write_state_atomic_leaves_original_untouched_on_replace_failure(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "state.yaml"
        original_bytes = yaml.safe_dump(make_state()).encode("utf-8")
        target.write_bytes(original_bytes)

        def boom(*args, **kwargs):
            raise OSError("simulated crash during replace")

        monkeypatch.setattr(ofs.os, "replace", boom)
        with pytest.raises(OSError, match="simulated crash"):
            ofs.write_state_atomic(target, make_state())

        assert target.read_bytes() == original_bytes
        leftover_tmp_files = [p for p in tmp_path.iterdir() if p != target]
        assert leftover_tmp_files == []

    def test_cas_mismatch_detected_by_digest_comparison(self, tmp_path):
        target = tmp_path / "state.yaml"
        target.write_bytes(yaml.safe_dump(make_state()).encode("utf-8"))
        stale_digest = ofs.compute_digest(target.read_bytes())

        # Simulate a concurrent writer changing the file after the digest was read.
        mutated = make_state()
        mutated["last_updated"]["reason"] = "concurrent session wrote first"
        target.write_bytes(yaml.safe_dump(mutated).encode("utf-8"))

        fresh_digest = ofs.compute_digest(target.read_bytes())
        assert fresh_digest != stale_digest


# --------------------------------------------------------------------------
# status report
# --------------------------------------------------------------------------


class TestStatus:
    def test_status_reports_prerequisite_closure_and_eligibility(self):
        state = make_state()
        report = ofs.compute_status(state)
        assert report["current_stage"] == "ORCH-000"
        assert report["recomputed_next_eligible_stage"] == "ORCH-000"
        assert report["next_eligible_matches_declared"] is True
        assert report["stages"]["ORCH-000"]["prerequisites_closed"] is True
        assert report["stages"]["ORCH-000"]["eligible_now"] is True
        assert report["stages"]["ORCH-001"]["prerequisites_closed"] is False
        assert report["stages"]["ORCH-001"]["eligible_now"] is False

    def test_status_after_approval_advances_frontier(self):
        state = make_state()
        approve_stage(state, "ORCH-000")
        report = ofs.compute_status(state)
        assert report["recomputed_next_eligible_stage"] == "ORCH-001"
        assert report["stages"]["ORCH-001"]["eligible_now"] is True


# --------------------------------------------------------------------------
# Regression: the real, committed governance state file must validate
# --------------------------------------------------------------------------


class TestRealRepositoryState:
    def test_committed_implementation_state_validates(self):
        state_path = REPO_ROOT / "docs/implementation/orchestration/implementation-state.yaml"
        plan_path = REPO_ROOT / "docs/implementation/orchestration/implementation-plan.md"
        state, _, _ = ofs.load_state_file(state_path)
        plan_text = plan_path.read_text(encoding="utf-8")
        result = ofs.validate_state(state, plan_text=plan_text)
        assert result.passed, result.errors

    def test_committed_state_next_eligible_stage_is_orch_001(self):
        state_path = REPO_ROOT / "docs/implementation/orchestration/implementation-state.yaml"
        state, _, _ = ofs.load_state_file(state_path)
        assert ofs.recompute_next_eligible(state) == "ORCH-001"


# --------------------------------------------------------------------------
# CLI golden tests (subprocess, isolated temp files only)
# --------------------------------------------------------------------------


class TestCli:
    def _write_state(self, tmp_path, state):
        path = tmp_path / "state.yaml"
        path.write_text(yaml.safe_dump(state, sort_keys=False), encoding="utf-8")
        return path

    def test_cli_validate_pass(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "validate",
                "--state",
                str(path),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["status"] == "PASS"
        assert payload["errors"] == []
        assert payload["state_digest"].startswith("sha256:")

    def test_cli_validate_fail_exit_code(self, tmp_path):
        state = make_state()
        del state["package_status"]
        path = self._write_state(tmp_path, state)
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "validate",
                "--state",
                str(path),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["status"] == "FAIL"
        assert payload["errors"]

    def test_cli_status(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "status", "--state", str(path), "--output", "json"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["recomputed_next_eligible_stage"] == "ORCH-000"

    def test_cli_digest(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "digest", "--state", str(path)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip().startswith("sha256:")

    def test_cli_transition_dry_run_does_not_modify_file(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        before = path.read_bytes()
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "transition",
                "--state",
                str(path),
                "--stage",
                "ORCH-000",
                "--to",
                "IN_PROGRESS",
                "--actor",
                "impl-1",
                "--role",
                "IMPLEMENTER",
                "--reason",
                "cli dry run",
                "--expected-base-head",
                "a" * 40,
                "--dry-run",
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["status"] == "DRY_RUN"
        assert path.read_bytes() == before

    def test_cli_transition_writes_and_is_idempotent_reread(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "transition",
                "--state",
                str(path),
                "--stage",
                "ORCH-000",
                "--to",
                "IN_PROGRESS",
                "--actor",
                "impl-1",
                "--role",
                "IMPLEMENTER",
                "--reason",
                "cli write",
                "--expected-base-head",
                "a" * 40,
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["status"] == "APPLIED"

        new_state = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert new_state["stages"]["ORCH-000"]["status"] == "IN_PROGRESS"
        assert len(new_state["history"]) == 1

        # Re-validate the file the CLI just wrote.
        proc2 = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "validate",
                "--state",
                str(path),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc2.returncode == 0, proc2.stderr

    def test_cli_transition_illegal_edge_rejected_and_file_untouched(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        before = path.read_bytes()
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "transition",
                "--state",
                str(path),
                "--stage",
                "ORCH-000",
                "--to",
                "VERIFIED",
                "--actor",
                "impl-1",
                "--role",
                "IMPLEMENTER",
                "--reason",
                "illegal",
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["status"] == "REJECTED"
        assert "ILLEGAL_TRANSITION" in payload["error"]
        assert path.read_bytes() == before

    def test_cli_transition_cas_mismatch_rejected(self, tmp_path):
        path = self._write_state(tmp_path, make_state())
        stale_digest = ofs.compute_digest(path.read_bytes())
        # A concurrent session writes first.
        mutated = make_state()
        mutated["last_updated"]["reason"] = "a concurrent writer got here first"
        path.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
        before = path.read_bytes()

        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "transition",
                "--state",
                str(path),
                "--stage",
                "ORCH-000",
                "--to",
                "IN_PROGRESS",
                "--actor",
                "impl-1",
                "--role",
                "IMPLEMENTER",
                "--reason",
                "stale writer",
                "--expected-base-head",
                "a" * 40,
                "--expected-digest",
                stale_digest,
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["error"] == "CAS_MISMATCH"
        assert path.read_bytes() == before
