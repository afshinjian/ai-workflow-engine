"""AUTO-015 sections 11 and 12: deterministic eligibility and the recommendation policy.

Every fixture here is real. The candidates come from a real YAML catalog file on disk, parsed
by the real :func:`read_catalog` with its real content-hash re-derivation; the blockers are
re-resolved against a real `OPEN_QUESTIONS.md` parsed by the real :func:`read_open_questions`;
the cycles and unmet dependencies come from the real :func:`resolve_dependency_graph`; and the
stale-completion findings come from the real :func:`stale_completion_findings`. Nothing that
this module's behaviour depends on is mocked -- a blocked-by-OD test really writes a register
entry that blocks an authorization, and a cycle test really writes two candidates that depend
on each other.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.successor_planning.catalog import (
    CandidateFinding,
    read_catalog,
    resolve_dependency_graph,
)
from ai_workflow_engine.successor_planning.eligibility import (
    ADVISORY_RECOMMENDATION_NOTICE,
    LIVE_STATUS_AFFECTS_IMPLEMENTATION,
    LIVE_STATUS_BLOCKS_AUTHORIZATION,
    LIVE_STATUS_RESOLVED,
    LIVE_STATUS_UNRECORDED,
    RECOMMENDATION_POLICY,
    RULE_BLOCKED_AUTHORIZATION_QUESTION,
    RULE_BLOCKED_DEPENDENCY_CYCLE,
    RULE_BLOCKED_UNMET_DEPENDENCY,
    RULE_DEFERRED,
    RULE_ELIGIBLE,
    RULE_INSUFFICIENT_EVIDENCE,
    SECTION_11_RULES,
    EligibilityReport,
    EligibilityVerdict,
    evaluate_all,
    evaluate_candidate,
    result_variant_for,
)
from ai_workflow_engine.successor_planning.models import Candidate, ProposalBlocker
from ai_workflow_engine.successor_planning.sources import (
    CompletionClaim,
    OpenQuestionsDocument,
    read_open_questions,
    stale_completion_findings,
)

CATALOG_PATH = "docs/catalog.yaml"
OPEN_QUESTIONS_PATH = "docs/OPEN_QUESTIONS.md"

# Two authorization gates, one implementation-only question, one already resolved. The
# distinction between OD-30 and OD-31 is the exact line section 11 draws.
OPEN_QUESTIONS = """# Open Questions

## Format

Each entry states its own disposition; the section heading is never the answer.

## Open

### OD-30 — A question that gates an authorization

- **Question:** Something unresolved.
- **Disposition:** Open. Blocks AUTO-016's authorization until it is answered.

### OD-31 — A question that only affects implementation

- **Question:** Something narrower.
- **Disposition:** Open. Blocks nothing's authorization; affects AUTO-016's implementation.

### OD-32 — A question already answered in place

- **Question:** Something settled.
- **Disposition:** Resolved 2026-07-01, as an implementation decision.

### D-40 — A deferred defect carried as history

- **Question:** A defect deferred by a prior stage.
- **Disposition:** Open. Blocks AUTO-016's authorization until it is answered.
"""


# --------------------------------------------------------------------------------------
# Fixture construction -- real files, real readers
# --------------------------------------------------------------------------------------


def content_hash(entry: dict[str, Any]) -> str:
    """Recompute one entry's section 10.1 digest independently of the catalog reader."""
    payload = {
        key: value
        for key, value in entry.items()
        if key not in {"content_hash", "lifecycle_status"}
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def entry(candidate_id: str, **overrides: Any) -> dict[str, Any]:
    """One schema-valid catalog entry whose digest covers its own final fields."""
    record: dict[str, Any] = {
        "candidate_id": candidate_id,
        "schema_version": "1.0",
        "title": f"Candidate {candidate_id}",
        "mission": "A bounded, plain-text mission carried as data and never as directive text.",
        "source_kind": "static_catalog",
        "source_reference": {
            "catalog_path": CATALOG_PATH,
            "catalog_version": "1.0",
            "entry_index": 0,
        },
        "mvp_relation": "inside",
        "dependencies": [],
        "blockers": [],
        "required_owner_decisions": [],
        "allowed_recommendation_status": True,
        "evidence_references": [],
    }
    record.update(overrides)
    record.setdefault("content_hash", content_hash(record))
    return record


def blocker(
    blocker_id: str, blocker_type: str = "open_question", **overrides: Any
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "blocker_id": blocker_id,
        "blocker_type": blocker_type,
        "live_status": "Open",
    }
    record.update(overrides)
    return record


def dependency(
    dependency_id: str, dependency_type: str = "stage", status: str = "COMPLETE"
) -> dict[str, Any]:
    return {
        "dependency_id": dependency_id,
        "dependency_type": dependency_type,
        "status": status,
    }


def write_catalog(root: Path, entries: Sequence[dict[str, Any]]) -> None:
    document = {
        "schema_version": 1,
        "catalog_id": "eligibility-test-catalog",
        "authorization_status": "NOT_AUTHORIZED",
        "source_decision": "GOV-AUTO-08",
        "historical_source": "docs/history.md",
        "candidates": list(entries),
    }
    target = root / CATALOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=4096),
        encoding="utf-8",
    )


@pytest.fixture
def register(tmp_path: Path) -> OpenQuestionsDocument:
    """The live owner-decision register, read from a real file by the real reader."""
    target = tmp_path / OPEN_QUESTIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(OPEN_QUESTIONS, encoding="utf-8")
    return read_open_questions(tmp_path, OPEN_QUESTIONS_PATH)


def catalog_candidates(root: Path, entries: Sequence[dict[str, Any]]) -> list[Candidate]:
    write_catalog(root, entries)
    document = read_catalog(root, CATALOG_PATH)
    assert document.findings == [], f"fixture entries failed to parse: {document.findings}"
    return list(document.candidates)


# --------------------------------------------------------------------------------------
# Section 11 -- per-candidate verdicts
# --------------------------------------------------------------------------------------


def test_a_candidate_with_no_gate_is_eligible(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    (candidate,) = catalog_candidates(tmp_path, [entry("alpha-candidate")])
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "eligible"
    assert verdict.rule_id == RULE_ELIGIBLE
    assert verdict.reasons


def test_an_open_authorization_blocking_question_blocks_the_candidate(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", blockers=[blocker("OD-30")])]
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "blocked"
    assert verdict.rule_id == RULE_BLOCKED_AUTHORIZATION_QUESTION
    assert any("OD-30" in reason and "blocks authorization" in reason for reason in verdict.reasons)
    assert verdict.blockers == [
        ProposalBlocker(
            blocker_id="OD-30",
            blocker_type="open_question",
            live_status=LIVE_STATUS_BLOCKS_AUTHORIZATION,
            candidate_id="alpha-candidate",
        )
    ]


def test_an_open_implementation_only_question_does_not_block(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    """The register's own blocks-authorization vs affects-implementation distinction, exactly."""
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", blockers=[blocker("OD-31")])]
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "eligible"
    assert verdict.blockers[0].live_status == LIVE_STATUS_AFFECTS_IMPLEMENTATION


def test_a_resolved_question_does_not_block(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", blockers=[blocker("OD-32")])]
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "eligible"
    assert verdict.blockers[0].live_status == LIVE_STATUS_RESOLVED


def test_the_catalogs_frozen_live_status_is_never_the_answer(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    """A catalog claiming a gating blocker is Resolved does not make it resolved."""
    (candidate,) = catalog_candidates(
        tmp_path,
        [entry("alpha-candidate", blockers=[blocker("OD-30", live_status="Resolved")])],
    )
    assert candidate.blockers[0].live_status == "Resolved"
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "blocked"
    assert verdict.blockers[0].live_status == LIVE_STATUS_BLOCKS_AUTHORIZATION

    # And the reverse: a catalog claiming a resolved question is Open does not reopen it.
    (other,) = catalog_candidates(
        tmp_path, [entry("beta-candidate", blockers=[blocker("OD-32", live_status="Open")])]
    )
    assert evaluate_candidate(other, open_questions=register).lifecycle_status == "eligible"


def test_a_blocker_the_register_does_not_record_is_insufficient_evidence(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    """Fail-closed: an unresolvable blocker is never assumed harmless."""
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", blockers=[blocker("OD-99")])]
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "insufficient_evidence"
    assert verdict.rule_id == RULE_INSUFFICIENT_EVIDENCE
    assert verdict.blockers[0].live_status == LIVE_STATUS_UNRECORDED


def test_a_deferred_defect_never_gates_but_is_still_re_resolved(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    """Only authorization-blocking OD-# items gate; a D-# is carried as visible evidence."""
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", blockers=[blocker("D-40", "deferred_defect")])]
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "eligible"
    assert verdict.blockers == [
        ProposalBlocker(
            blocker_id="D-40",
            blocker_type="deferred_defect",
            live_status=LIVE_STATUS_BLOCKS_AUTHORIZATION,
            candidate_id="alpha-candidate",
        )
    ]


def test_every_declared_blocker_is_carried_live_resolved_not_only_the_gating_one(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    (candidate,) = catalog_candidates(
        tmp_path,
        [entry("alpha-candidate", blockers=[blocker("OD-30"), blocker("OD-31"), blocker("OD-32")])],
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert [(item.blocker_id, item.live_status) for item in verdict.blockers] == [
        ("OD-30", LIVE_STATUS_BLOCKS_AUTHORIZATION),
        ("OD-31", LIVE_STATUS_AFFECTS_IMPLEMENTATION),
        ("OD-32", LIVE_STATUS_RESOLVED),
    ]


def test_a_dependency_cycle_blocks_every_participant_with_the_cycle_named(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [
            entry("alpha-candidate", dependencies=[dependency("beta-candidate", "capability")]),
            entry("beta-candidate", dependencies=[dependency("alpha-candidate", "capability")]),
        ],
    )
    resolution = resolve_dependency_graph(candidates)
    assert resolution.cycles == [["alpha-candidate", "beta-candidate"]]

    report = evaluate_all(
        candidates,
        open_questions=register,
        findings=resolution.findings,
        unmet_dependencies=resolution.unmet,
    )
    for verdict in report.verdicts:
        assert verdict.lifecycle_status == "blocked"
        assert verdict.rule_id == RULE_BLOCKED_DEPENDENCY_CYCLE
        assert any(
            "alpha-candidate, beta-candidate" in reason for reason in verdict.reasons
        ), verdict.reasons


def test_an_unmet_dependency_blocks_with_the_dependency_named(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path, [entry("alpha-candidate", dependencies=[dependency("AUTO-099")])]
    )
    resolution = resolve_dependency_graph(candidates, known_stages=["AUTO-014"])
    assert [item.dependency_id for item in resolution.unmet] == ["AUTO-099"]

    verdict = evaluate_candidate(
        candidates[0],
        open_questions=register,
        findings=resolution.findings,
        unmet_dependencies=resolution.unmet,
    )
    assert verdict.lifecycle_status == "blocked"
    assert verdict.rule_id == RULE_BLOCKED_UNMET_DEPENDENCY
    assert any("AUTO-099" in reason for reason in verdict.reasons)


def test_a_satisfied_stage_dependency_leaves_the_candidate_eligible(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path, [entry("alpha-candidate", dependencies=[dependency("AUTO-014")])]
    )
    resolution = resolve_dependency_graph(candidates, known_stages=["AUTO-014"])
    assert resolution.unmet == []
    verdict = evaluate_candidate(
        candidates[0],
        open_questions=register,
        findings=resolution.findings,
        unmet_dependencies=resolution.unmet,
    )
    assert verdict.lifecycle_status == "eligible"


def test_stale_completion_evidence_is_per_candidate_insufficient_evidence(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", dependencies=[dependency("AUTO-013")])]
    )
    findings = stale_completion_findings(
        [
            CompletionClaim(
                candidate_id="alpha-candidate",
                stage_id="AUTO-013",
                declared_status="COMPLETE",
                report=None,
                code="STALE_COMPLETION_EVIDENCE",
            )
        ]
    )
    verdict = evaluate_candidate(
        candidate,
        open_questions=register,
        findings=findings,
        unmet_dependencies=[],
    )
    assert verdict.lifecycle_status == "insufficient_evidence"
    assert verdict.rule_id == RULE_INSUFFICIENT_EVIDENCE
    assert any("AUTO-013" in reason for reason in verdict.reasons)


def test_insufficient_evidence_wins_over_a_definite_blocked_verdict(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    """A candidate whose supporting evidence is incomplete never claims a definite verdict.

    Every blocking fact is still recorded in `reasons`; only the status is the narrower one.
    """
    (candidate,) = catalog_candidates(
        tmp_path,
        [
            entry(
                "alpha-candidate",
                blockers=[blocker("OD-30")],
                dependencies=[dependency("AUTO-099")],
            )
        ],
    )
    resolution = resolve_dependency_graph([candidate])
    findings = stale_completion_findings(
        [
            CompletionClaim(
                candidate_id="alpha-candidate",
                stage_id="AUTO-099",
                declared_status="COMPLETE",
                report=None,
                code="STALE_COMPLETION_EVIDENCE",
            )
        ]
    )
    verdict = evaluate_candidate(
        candidate,
        open_questions=register,
        findings=findings,
        unmet_dependencies=resolution.unmet,
    )
    assert verdict.lifecycle_status == "insufficient_evidence"
    assert any("OD-30" in reason for reason in verdict.reasons)
    assert any("AUTO-099" in reason for reason in verdict.reasons)


def test_an_explicitly_deferred_candidate_is_deferred_not_blocked(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    (candidate,) = catalog_candidates(
        tmp_path, [entry("alpha-candidate", mvp_relation="outside_deferred")]
    )
    verdict = evaluate_candidate(candidate, open_questions=register)
    assert verdict.lifecycle_status == "deferred"
    assert verdict.rule_id == RULE_DEFERRED
    assert any("informational history" in reason for reason in verdict.reasons)


def test_a_gate_outranks_a_deferral(tmp_path: Path, register: OpenQuestionsDocument) -> None:
    (candidate,) = catalog_candidates(
        tmp_path,
        [entry("alpha-candidate", mvp_relation="outside_deferred", blockers=[blocker("OD-30")])],
    )
    assert evaluate_candidate(candidate, open_questions=register).lifecycle_status == "blocked"


def test_every_verdict_cites_exactly_one_section_11_rule(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [
            entry("alpha-candidate"),
            entry("beta-candidate", blockers=[blocker("OD-30")]),
            entry("delta-candidate", blockers=[blocker("OD-99")]),
            entry("gamma-candidate", mvp_relation="outside_deferred"),
        ],
    )
    report = evaluate_all(candidates, open_questions=register)
    assert {verdict.rule_id for verdict in report.verdicts} <= SECTION_11_RULES
    assert [verdict.rule_id for verdict in report.verdicts] == [
        RULE_ELIGIBLE,
        RULE_BLOCKED_AUTHORIZATION_QUESTION,
        RULE_INSUFFICIENT_EVIDENCE,
        RULE_DEFERRED,
    ]


def test_the_unknown_lifecycle_status_is_never_produced(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path, [entry("alpha-candidate"), entry("beta-candidate", blockers=[blocker("OD-99")])]
    )
    report = evaluate_all(candidates, open_questions=register)
    assert "unknown" not in {verdict.lifecycle_status for verdict in report.verdicts}
    with pytest.raises(ValidationError):
        EligibilityVerdict(
            candidate_id="alpha-candidate",
            lifecycle_status="unknown",  # type: ignore[arg-type]
            rule_id=RULE_ELIGIBLE,
            reasons=["x"],
            blockers=[],
        )


def test_a_verdict_must_cite_a_known_rule_and_at_least_one_reason() -> None:
    with pytest.raises(ValidationError, match="not a section 11 rule identifier"):
        EligibilityVerdict(
            candidate_id="alpha-candidate",
            lifecycle_status="eligible",
            rule_id="RULE_INVENTED",
            reasons=["x"],
            blockers=[],
        )
    with pytest.raises(ValidationError, match="at least one reason"):
        EligibilityVerdict(
            candidate_id="alpha-candidate",
            lifecycle_status="eligible",
            rule_id=RULE_ELIGIBLE,
            reasons=[],
            blockers=[],
        )


# --------------------------------------------------------------------------------------
# Sections 11.1, 11.2 and 12 -- the whole-proposal result
# --------------------------------------------------------------------------------------


def test_exactly_one_eligible_candidate_is_recommendation_ready(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [entry("alpha-candidate"), entry("beta-candidate", blockers=[blocker("OD-30")])],
    )
    report = evaluate_all(candidates, open_questions=register)
    assert report.result_variant == "RECOMMENDATION_READY"
    assert report.eligible_candidate_ids == ["alpha-candidate"]
    assert report.recommended_candidate_id() == "alpha-candidate"


def test_multiple_eligible_candidates_recommend_none_and_are_never_ranked(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [entry("alpha-candidate"), entry("beta-candidate"), entry("gamma-candidate")],
    )
    report = evaluate_all(candidates, open_questions=register)
    assert report.result_variant == "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION"
    assert report.eligible_candidate_ids == [
        "alpha-candidate",
        "beta-candidate",
        "gamma-candidate",
    ]
    assert report.recommended_candidate_id() is None


def test_zero_eligible_with_a_definite_verdict_is_no_eligible_candidate(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [
            entry("alpha-candidate", blockers=[blocker("OD-30")]),
            entry("beta-candidate", mvp_relation="outside_deferred"),
            entry("gamma-candidate", blockers=[blocker("OD-99")]),
        ],
    )
    report = evaluate_all(candidates, open_questions=register)
    assert report.result_variant == "NO_ELIGIBLE_CANDIDATE"
    assert report.eligible_candidate_ids == []


def test_all_candidates_insufficient_is_the_distinct_whole_proposal_variant(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [
            entry("alpha-candidate", blockers=[blocker("OD-98")]),
            entry("beta-candidate", blockers=[blocker("OD-99")]),
        ],
    )
    report = evaluate_all(candidates, open_questions=register)
    assert {verdict.lifecycle_status for verdict in report.verdicts} == {"insufficient_evidence"}
    assert report.result_variant == "INSUFFICIENT_EVIDENCE"


def test_a_conflict_finding_alone_still_yields_no_eligible_candidate(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    """Section 10.2 excludes a conflicting entry from the candidate list; it is still definite."""
    del tmp_path
    finding = CandidateFinding(
        code="DUPLICATE_CANDIDATE_CONFLICT",
        candidate_id="alpha-candidate",
        message="two definitions disagree",
    )
    report = evaluate_all([], open_questions=register, findings=[finding])
    assert report.verdicts == []
    assert report.result_variant == "NO_ELIGIBLE_CANDIDATE"


def test_an_empty_catalog_is_insufficient_evidence_not_no_eligible_candidate(
    register: OpenQuestionsDocument,
) -> None:
    report = evaluate_all([], open_questions=register)
    assert report.result_variant == "INSUFFICIENT_EVIDENCE"


def test_result_variant_selection_is_exhaustive_over_the_section_12_enum() -> None:
    def verdict(candidate_id: str, status: str) -> EligibilityVerdict:
        return EligibilityVerdict(
            candidate_id=candidate_id,
            lifecycle_status=status,  # type: ignore[arg-type]
            rule_id=RULE_ELIGIBLE if status == "eligible" else RULE_INSUFFICIENT_EVIDENCE,
            reasons=["a stated reason"],
            blockers=[],
        )

    assert result_variant_for([verdict("a-one", "eligible")]) == "RECOMMENDATION_READY"
    assert (
        result_variant_for([verdict("a-one", "eligible"), verdict("b-two", "eligible")])
        == "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION"
    )
    assert result_variant_for([verdict("a-one", "blocked")]) == "NO_ELIGIBLE_CANDIDATE"
    assert result_variant_for([verdict("a-one", "deferred")]) == "NO_ELIGIBLE_CANDIDATE"
    assert (
        result_variant_for([verdict("a-one", "insufficient_evidence")]) == "INSUFFICIENT_EVIDENCE"
    )
    assert (
        result_variant_for([verdict("a-one", "insufficient_evidence"), verdict("b-two", "blocked")])
        == "NO_ELIGIBLE_CANDIDATE"
    )


# --------------------------------------------------------------------------------------
# Section 11.1 / 11.2 -- the fixed recommendation policy
# --------------------------------------------------------------------------------------


def test_the_recommendation_policy_is_dec_004_and_dec_005_verbatim() -> None:
    assert RECOMMENDATION_POLICY.exactly_one_eligible == "ADVISORY_RECOMMENDATION"
    assert RECOMMENDATION_POLICY.multiple_eligible == "RECOMMEND_NONE"
    assert RECOMMENDATION_POLICY.zero_eligible == "RECOMMEND_NONE"
    assert RECOMMENDATION_POLICY.ranking_permitted is False
    assert RECOMMENDATION_POLICY.auto_selection_permitted is False
    assert RECOMMENDATION_POLICY.decision_references == ("DEC-004", "DEC-005")
    assert RECOMMENDATION_POLICY.advisory_notice == ADVISORY_RECOMMENDATION_NOTICE
    assert "never authority" in ADVISORY_RECOMMENDATION_NOTICE


def test_the_recommendation_policy_cannot_be_relaxed_at_runtime() -> None:
    with pytest.raises(ValidationError):
        RECOMMENDATION_POLICY.ranking_permitted = True  # type: ignore[misc]
    with pytest.raises(ValidationError):
        type(RECOMMENDATION_POLICY)(
            exactly_one_eligible="ADVISORY_RECOMMENDATION",
            multiple_eligible="RECOMMEND_NONE",
            zero_eligible="RECOMMEND_NONE",
            ranking_permitted=True,  # type: ignore[arg-type]
            auto_selection_permitted=False,
            advisory_notice=ADVISORY_RECOMMENDATION_NOTICE,
            decision_references=("DEC-004",),
        )


# --------------------------------------------------------------------------------------
# Sections 16.2 and 18 -- ordering and determinism
# --------------------------------------------------------------------------------------


def test_the_report_carries_every_canonical_ordering(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    candidates = catalog_candidates(
        tmp_path,
        [
            entry("gamma-candidate", blockers=[blocker("OD-30"), blocker("OD-31")]),
            entry("alpha-candidate", blockers=[blocker("OD-30")]),
        ],
    )
    report = evaluate_all(candidates, open_questions=register)
    assert [verdict.candidate_id for verdict in report.verdicts] == [
        "alpha-candidate",
        "gamma-candidate",
    ]
    assert [(item.blocker_id, item.candidate_id) for item in report.blockers] == [
        ("OD-30", "alpha-candidate"),
        ("OD-30", "gamma-candidate"),
        ("OD-31", "gamma-candidate"),
    ]
    assert [decision.candidate_id for decision in report.decisions()] == [
        "alpha-candidate",
        "gamma-candidate",
    ]


def test_the_report_refuses_an_eligible_list_that_disagrees_with_its_verdicts() -> None:
    verdict = EligibilityVerdict(
        candidate_id="alpha-candidate",
        lifecycle_status="blocked",
        rule_id=RULE_BLOCKED_AUTHORIZATION_QUESTION,
        reasons=["OD-30 blocks authorization"],
        blockers=[],
    )
    with pytest.raises(ValidationError, match="exactly the eligible verdicts"):
        EligibilityReport(
            verdicts=[verdict],
            eligible_candidate_ids=["alpha-candidate"],
            blockers=[],
            result_variant="RECOMMENDATION_READY",
        )


def test_a_verdicts_blockers_must_name_that_verdicts_candidate() -> None:
    with pytest.raises(ValidationError, match="must name that verdict's candidate"):
        EligibilityVerdict(
            candidate_id="alpha-candidate",
            lifecycle_status="eligible",
            rule_id=RULE_ELIGIBLE,
            reasons=["no gate applies"],
            blockers=[
                ProposalBlocker(
                    blocker_id="OD-30",
                    blocker_type="open_question",
                    live_status=LIVE_STATUS_RESOLVED,
                    candidate_id="beta-candidate",
                )
            ],
        )


def test_repeated_evaluation_over_identical_inputs_is_byte_identical(
    tmp_path: Path, register: OpenQuestionsDocument
) -> None:
    entries = [
        entry("gamma-candidate", mvp_relation="outside_deferred"),
        entry("alpha-candidate"),
        entry("beta-candidate", blockers=[blocker("OD-30"), blocker("OD-32")]),
        entry("delta-candidate", blockers=[blocker("OD-99")]),
    ]
    candidates = catalog_candidates(tmp_path, entries)
    first = evaluate_all(candidates, open_questions=register)
    # A second, independently re-read pass over the same file, with the input order reversed:
    # the report must not depend on the order the reader happened to visit the entries in.
    second = evaluate_all(list(reversed(candidates)), open_questions=register)
    assert canonical_json(first.model_dump()) == canonical_json(second.model_dump())
    assert first.result_variant == second.result_variant == "RECOMMENDATION_READY"
