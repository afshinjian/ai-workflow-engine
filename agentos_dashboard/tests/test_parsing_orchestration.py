"""TC-01/TC-02 — `parsing.orchestration`: safe YAML loading with duplicate-key rejection
(TR-09)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.parsing.models import Confidence
from agentos_dashboard.parsing.orchestration import parse_implementation_state

FIXTURES = Path(__file__).parent / "fixtures" / "malformed"

WELL_FORMED = """\
schema_name: orchestration-implementation-state
feature_id: ORCH
current_stage: ORCH-001
next_eligible_stage: ORCH-002
delivery_order: [ORCH-000, ORCH-001, ORCH-002]
stages:
  ORCH-000:
    title: Bootstrap
    status: REVIEW_APPROVED
    prerequisites: []
    blockers: []
    evidence: [e1.yaml]
  ORCH-001:
    title: Validator
    status: VERIFIED
    prerequisites: [ORCH-000]
    blockers: [{code: X, summary: some blocker}]
    evidence: []
  ORCH-002:
    title: Registry
    status: NOT_STARTED
    prerequisites: [ORCH-001]
    blockers: []
    evidence: []
"""


def test_well_formed_document_parses_at_high_confidence() -> None:
    parsed = parse_implementation_state(WELL_FORMED, "implementation-state.yaml")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert parsed.value.feature_id == "ORCH"
    assert parsed.value.current_stage == "ORCH-001"
    assert parsed.value.delivery_order == ("ORCH-000", "ORCH-001", "ORCH-002")
    stages = {stage.stage_id: stage for stage in parsed.value.stages}
    assert stages["ORCH-000"].title == "Bootstrap"
    assert stages["ORCH-001"].prerequisites == ("ORCH-000",)
    assert stages["ORCH-001"].blockers == ("some blocker",)


def test_duplicate_top_level_key_is_rejected() -> None:
    text = (FIXTURES / "implementation_state_duplicate_key.yaml").read_text(encoding="utf-8")
    parsed = parse_implementation_state(text, "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None
    assert any("duplicate key" in note for note in parsed.notes)


def test_invalid_yaml_syntax_degrades_to_raw_text() -> None:
    text = (FIXTURES / "implementation_state_invalid_syntax.yaml").read_text(encoding="utf-8")
    parsed = parse_implementation_state(text, "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None
    assert parsed.raw_text == text


def test_non_mapping_document_root_degrades_to_raw_text() -> None:
    parsed = parse_implementation_state("- just\n- a\n- list\n", "fixture")
    assert parsed.confidence is Confidence.NONE
    assert parsed.value is None


def test_missing_stages_key_is_low_confidence_not_a_crash() -> None:
    parsed = parse_implementation_state("feature_id: ORCH\n", "fixture")
    assert parsed.confidence is Confidence.LOW
    assert parsed.value is not None
    assert parsed.value.stages == ()


def test_real_implementation_state_parses_at_high_confidence() -> None:
    real_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "implementation"
        / "orchestration"
        / "implementation-state.yaml"
    )
    text = real_path.read_text(encoding="utf-8")
    parsed = parse_implementation_state(text, "implementation-state.yaml")
    assert parsed.confidence is Confidence.HIGH
    assert parsed.value is not None
    assert parsed.value.feature_id == "ORCH"
    assert len(parsed.value.stages) > 20
