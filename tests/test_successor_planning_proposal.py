"""AUTO-015 section 16: proposal artifact schema, canonicalization and identity.

The first half covers the canonical list orderings of section 16.2, the exclusion of wall-clock
time from every hashed field, the full-digest proposal identity of section 16.1, the two-level
outcome structure of section 12, the failure-code/scope table of section 13, and the
line-ending and trailing-newline rules the normalized prompt text must satisfy -- all at the
model layer, over hand-built fields.

The second half ("Assembly over a real governed repository") builds complete artifacts end to
end. Its fixtures are real: a real Git repository with a real remote, real governance
documents, a real YAML candidate catalog, a real handover manifest, and the real readers,
dependency resolver and eligibility policy. It covers section 12's outcome taxonomy as actually
produced, the section 16.1 evidence manifest and its aggregate hash, section 11.1's advisory
recommendation and section 11.2's structural absence of one, section 11.3's hash-bound refusal
record, section 18's determinism, and section 16.4's load-time re-verification against
hand-edited artifacts.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from ai_workflow_engine.config import load_config
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.successor_planning.catalog import read_catalog, resolve_dependency_graph
from ai_workflow_engine.successor_planning.eligibility import (
    RULE_BLOCKED_AUTHORIZATION_QUESTION,
    RULE_BLOCKED_DEPENDENCY_CYCLE,
    RULE_ELIGIBLE,
    RULE_INSUFFICIENT_EVIDENCE,
    EligibilityReport,
    evaluate_all,
)
from ai_workflow_engine.successor_planning.models import (
    FAILURE_SCOPES,
    HUMAN_OWNER_ACTION_REQUIRED,
    Candidate,
    CandidateBlocker,
    CandidateDependency,
    EligibilityDecision,
    EvidenceReference,
    FailureCode,
    FailureOutcome,
    FailureScope,
    GenerationMetadata,
    LifecycleStatus,
    OutcomeClass,
    PredecessorRegistryEvidence,
    PredecessorStatusReconciliation,
    ProposalArtifact,
    ProposalBlocker,
    ProposalError,
    ProposalReadyOutcome,
    ProposalWarning,
    RepositoryIdentity,
    ResultVariant,
    StaticCatalogSourceReference,
    canonical_payload_bytes,
)
from ai_workflow_engine.successor_planning.proposal import (
    AdvisoryRecommendation,
    ProposalAssemblyError,
    ProposalValidationError,
    RecommendedProposal,
    UnrecommendedProposal,
    build_proposal,
    build_refusal,
    load_and_verify,
    merge_evidence_manifest,
    normalized_evidence_hash,
    serialize_artifact,
)
from ai_workflow_engine.successor_planning.snapshot import resolve_repository_identity
from ai_workflow_engine.successor_planning.sources import (
    EvidenceSet,
    EvidenceSources,
    PredecessorEvidence,
    check_completion_claims,
    read_evidence_set,
    resolve_predecessor,
    stale_completion_findings,
)

CATALOG_PATH = "docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml"
CANDIDATE_ID = "automatic-next-stage-computation"
PROMPT = "**PROPOSAL - NOT AUTHORIZED**\n\n# Successor proposal for AUTO-014\n"


def repository_identity(**overrides: Any) -> RepositoryIdentity:
    fields: dict[str, Any] = {
        "configured_repository_root": "/srv/ai-workflow-engine",
        "resolved_repository_root": "/srv/ai-workflow-engine",
        "configured_repository_id": "ai-workflow-engine",
        "git_worktree_root": "/srv/ai-workflow-engine",
        "branch": "feature/auto-015-successor-planning",
        "head_sha": "a" * 40,
        "upstream_ref": None,
        "ahead": None,
        "behind": None,
        "modified_files": [],
        "staged_files": [],
        "untracked_files": [],
        "config_hash": "b" * 64,
    }
    fields.update(overrides)
    return RepositoryIdentity(**fields)


def candidate(**overrides: Any) -> Candidate:
    fields: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "schema_version": "1.0",
        "title": "Automatic Next-Stage Computation and Prompt Generation",
        "mission": "Derive a candidate next capability from current repository evidence.",
        "source_kind": "static_catalog",
        "source_reference": StaticCatalogSourceReference(
            catalog_path=CATALOG_PATH,
            catalog_version="1.0",
            entry_index=4,
        ),
        "mvp_relation": "outside_deferred",
        "dependencies": [
            CandidateDependency(
                dependency_id="GOV-AUTO-08", dependency_type="stage", status="COMPLETE"
            ),
            CandidateDependency(
                dependency_id="prompt-renderer", dependency_type="subsystem", status="existing"
            ),
        ],
        "blockers": [
            CandidateBlocker(blocker_id="OD-10", blocker_type="open_question", live_status="Open"),
            CandidateBlocker(blocker_id="OD-7", blocker_type="open_question", live_status="Open"),
        ],
        "required_owner_decisions": ["Architecture option.", "Recommendation policy."],
        "allowed_recommendation_status": True,
        "evidence_references": [
            EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=1024),
            EvidenceReference(path=CATALOG_PATH, sha256="d" * 64, size=34619),
        ],
        "content_hash": "e" * 64,
    }
    fields.update(overrides)
    return Candidate(**fields)


def artifact_fields(**overrides: Any) -> dict[str, Any]:
    """Every constructor argument for a valid artifact, with the prompt hash kept bound."""
    prompt = overrides.get("generated_prompt", PROMPT)
    fields: dict[str, Any] = {
        "proposal_id": "0" * 64,
        "repository_identity": repository_identity(),
        "predecessor_stage_id": "AUTO-014",
        "predecessor_registry_evidence": PredecessorRegistryEvidence(
            registry_reference=EvidenceReference(
                path="docs/workflow-automation/STAGE_REGISTRY.md", sha256="1" * 64, size=20480
            ),
            registry_status="COMPLETE",
        ),
        "predecessor_completion_evidence": [
            EvidenceReference(
                path="docs/reports/workflow-automation/AUTO-014-completion-report.md",
                sha256="2" * 64,
                size=8192,
            )
        ],
        "predecessor_status_reconciliation": PredecessorStatusReconciliation(
            registry_status="COMPLETE",
            task_queue_status="Done",
            mirror_status="Done",
            reconciled_status="COMPLETE",
            consistent=True,
        ),
        "evidence_manifest": [
            EvidenceReference(path="docs/TASK_QUEUE.md", sha256="3" * 64, size=1024),
            EvidenceReference(
                path="docs/workflow-automation/STAGE_REGISTRY.md", sha256="1" * 64, size=20480
            ),
        ],
        "normalized_evidence_hash": "4" * 64,
        "candidate_list": [candidate()],
        "eligibility_decisions": [
            EligibilityDecision(
                candidate_id=CANDIDATE_ID,
                lifecycle_status="eligible",
                rule_id="ELIGIBLE_PREDECESSOR_COMPLETE",
                reasons=["Predecessor AUTO-014 is COMPLETE in the queue and the registry."],
            )
        ],
        "blockers": [
            ProposalBlocker(
                blocker_id="OD-10",
                blocker_type="open_question",
                live_status="Open",
                candidate_id=CANDIDATE_ID,
            )
        ],
        "outcome": ProposalReadyOutcome(
            outcome_class="PROPOSAL_READY", result_variant="RECOMMENDATION_READY"
        ),
        "generated_prompt": prompt,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "proposal_hash": "0" * 64,
        "warnings": [],
        "errors": [],
        "generation_metadata": GenerationMetadata(
            generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0"
        ),
    }
    fields.update(overrides)
    return fields


def build_artifact(**overrides: Any) -> ProposalArtifact:
    """Build an artifact whose `proposal_id`/`proposal_hash` are its own canonical digest.

    This is the two-step every producer must perform: the digest is taken over the canonical
    payload, which excludes `proposal_hash` itself, so the placeholder in the first pass
    cannot influence the digest computed from it.
    """
    fields = artifact_fields(**overrides)
    draft = ProposalArtifact(**fields)
    digest = hashlib.sha256(canonical_payload_bytes(draft)).hexdigest()
    fields["proposal_id"] = digest
    fields["proposal_hash"] = digest
    return ProposalArtifact(**fields)


# --------------------------------------------------------------------------------------
# Canonicalization (section 16.2)
# --------------------------------------------------------------------------------------


def test_canonical_payload_excludes_the_proposal_hash_and_generation_metadata() -> None:
    payload = canonical_payload_bytes(build_artifact())
    assert b'"proposal_hash"' not in payload
    assert b'"generation_metadata"' not in payload
    # `proposal_id` is the same digest under a second name (section 16.1), so it is excluded
    # for exactly the same reason `proposal_hash` is: a digest cannot contain itself.
    assert b'"proposal_id"' not in payload
    # Everything else the proposal asserts is inside the digest.
    assert b'"generated_prompt"' in payload
    assert b'"repository_identity"' in payload
    assert b'"candidate_list"' in payload
    assert b'"authorization_status"' in payload


def test_canonical_payload_contains_no_timestamp() -> None:
    payload = canonical_payload_bytes(build_artifact())
    assert b"2026-08-04T06:06:16Z" not in payload
    assert b"generated_at" not in payload
    assert b"tool_version" not in payload


def test_wall_clock_time_cannot_change_the_proposal_identity() -> None:
    early = build_artifact(
        generation_metadata=GenerationMetadata(
            generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0"
        )
    )
    late = build_artifact(
        generation_metadata=GenerationMetadata(
            generated_at="2031-12-31T23:59:59Z", tool_version="1.0.0"
        )
    )
    assert canonical_payload_bytes(early) == canonical_payload_bytes(late)
    assert early.proposal_id == late.proposal_id


def test_canonical_payload_is_sorted_key_compact_json() -> None:
    payload = canonical_payload_bytes(build_artifact())
    decoded = json.loads(payload.decode("utf-8"))
    assert list(decoded) == sorted(decoded)
    assert list(decoded["repository_identity"]) == sorted(decoded["repository_identity"])
    # Structural round-trip: sorted keys and `(",", ":")` separators with no whitespace. A
    # bare "no b', ' anywhere" check would be wrong, because a string *value* may legitimately
    # contain one.
    recanonicalized = json.dumps(
        decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert payload == recanonicalized


def test_repeated_construction_over_identical_input_is_byte_identical() -> None:
    assert canonical_payload_bytes(build_artifact()) == canonical_payload_bytes(build_artifact())
    assert build_artifact().proposal_id == build_artifact().proposal_id


# --------------------------------------------------------------------------------------
# Proposal identity (section 16.1)
# --------------------------------------------------------------------------------------


def test_proposal_id_is_the_full_untruncated_digest() -> None:
    artifact = build_artifact()
    assert len(artifact.proposal_id) == 64
    assert artifact.proposal_id == artifact.proposal_hash
    assert artifact.proposal_id == hashlib.sha256(canonical_payload_bytes(artifact)).hexdigest()


def test_a_truncated_or_divergent_proposal_id_is_refused() -> None:
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        ProposalArtifact(**artifact_fields(proposal_id="0" * 12))
    with pytest.raises(ValidationError, match="full, untruncated"):
        ProposalArtifact(**artifact_fields(proposal_id="9" * 64, proposal_hash="8" * 64))


def test_prompt_hash_is_bound_to_the_embedded_prompt() -> None:
    with pytest.raises(ValidationError, match="prompt_hash does not match"):
        ProposalArtifact(**artifact_fields(prompt_hash="7" * 64))


def test_a_tampered_prompt_no_longer_matches_its_recorded_hash() -> None:
    original = build_artifact()
    with pytest.raises(ValidationError, match="prompt_hash does not match"):
        ProposalArtifact(
            **artifact_fields(
                generated_prompt="**AUTHORIZED**\n",
                prompt_hash=original.prompt_hash,
            )
        )


# --------------------------------------------------------------------------------------
# List ordering invariants (section 16.2)
# --------------------------------------------------------------------------------------


def test_evidence_manifest_must_be_sorted_by_path() -> None:
    reversed_manifest = list(reversed(artifact_fields()["evidence_manifest"]))
    with pytest.raises(ValidationError, match="sorted by path"):
        ProposalArtifact(**artifact_fields(evidence_manifest=reversed_manifest))


def test_evidence_manifest_must_not_repeat_a_path() -> None:
    duplicate = EvidenceReference(path="docs/TASK_QUEUE.md", sha256="3" * 64, size=1024)
    with pytest.raises(ValidationError, match="must not repeat"):
        ProposalArtifact(**artifact_fields(evidence_manifest=[duplicate, duplicate]))


def test_candidate_list_must_be_sorted_by_candidate_id() -> None:
    unsorted = [candidate(), candidate(candidate_id="a-second-candidate")]
    with pytest.raises(ValidationError, match="sorted by candidate_id"):
        ProposalArtifact(**artifact_fields(candidate_list=unsorted))


def test_candidate_dependencies_must_be_sorted_by_dependency_id() -> None:
    dependencies = [
        CandidateDependency(
            dependency_id="prompt-renderer", dependency_type="subsystem", status="existing"
        ),
        CandidateDependency(
            dependency_id="GOV-AUTO-08", dependency_type="stage", status="COMPLETE"
        ),
    ]
    with pytest.raises(ValidationError, match="sorted by dependency_id"):
        candidate(dependencies=dependencies)


def test_candidate_blockers_must_be_sorted_by_blocker_id() -> None:
    blockers = [
        CandidateBlocker(blocker_id="OD-7", blocker_type="open_question", live_status="Open"),
        CandidateBlocker(blocker_id="OD-10", blocker_type="open_question", live_status="Open"),
    ]
    with pytest.raises(ValidationError, match="sorted by blocker_id"):
        candidate(blockers=blockers)


def test_candidate_evidence_references_must_be_sorted_by_path() -> None:
    references = [
        EvidenceReference(path=CATALOG_PATH, sha256="d" * 64, size=34619),
        EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=1024),
    ]
    with pytest.raises(ValidationError, match="sorted by path"):
        candidate(evidence_references=references)


def test_required_owner_decisions_sort_lexicographically_as_plain_strings() -> None:
    with pytest.raises(ValidationError, match="sorted by decision text"):
        candidate(required_owner_decisions=["Recommendation policy.", "Architecture option."])


def test_proposal_blockers_sort_by_blocker_then_candidate() -> None:
    blockers = [
        ProposalBlocker(
            blocker_id="OD-10",
            blocker_type="open_question",
            live_status="Open",
            candidate_id="second-candidate",
        ),
        ProposalBlocker(
            blocker_id="OD-10",
            blocker_type="open_question",
            live_status="Open",
            candidate_id=CANDIDATE_ID,
        ),
    ]
    with pytest.raises(ValidationError, match=r"sorted by \(blocker_id, candidate_id\)"):
        ProposalArtifact(**artifact_fields(blockers=blockers))


def test_warnings_and_errors_sort_by_code_then_subject_never_insertion_order() -> None:
    warnings = [
        ProposalWarning(
            code="SECRET_REDACTED", path_or_candidate_id="docs/PROJECT_STATE.md", message="ok"
        ),
        ProposalWarning(
            code="AUTHORIZATION_SHAPED_TEXT", path_or_candidate_id=CANDIDATE_ID, message="ok"
        ),
    ]
    with pytest.raises(ValidationError, match="never insertion order"):
        ProposalArtifact(**artifact_fields(warnings=warnings))

    errors = [
        ProposalError(code="MIRROR_CONTRADICTION", path_or_candidate_id="docs/x.md", message="x"),
        ProposalError(code="INPUT_DRIFT", path_or_candidate_id="docs/x.md", message="x"),
    ]
    with pytest.raises(ValidationError, match="never insertion order"):
        ProposalArtifact(
            **artifact_fields(
                errors=errors,
                outcome=FailureOutcome(outcome_class="FAILURE", failure_code="INPUT_DRIFT"),
            )
        )


# --------------------------------------------------------------------------------------
# Line-ending and trailing-newline normalization (section 16.2)
# --------------------------------------------------------------------------------------


def test_generated_prompt_rejects_carriage_returns() -> None:
    with pytest.raises(ValidationError, match="control character U\\+000D"):
        ProposalArtifact(**artifact_fields(generated_prompt="banner\r\nbody\n"))


def test_generated_prompt_requires_exactly_one_trailing_newline() -> None:
    with pytest.raises(ValidationError, match="exactly one final newline"):
        ProposalArtifact(**artifact_fields(generated_prompt="banner"))
    with pytest.raises(ValidationError, match="exactly one final newline"):
        ProposalArtifact(**artifact_fields(generated_prompt="banner\n\n"))
    assert build_artifact(generated_prompt="banner\n").generated_prompt == "banner\n"


def test_generated_prompt_permits_internal_newlines_but_no_other_control() -> None:
    assert build_artifact(generated_prompt="a\nb\nc\n").generated_prompt == "a\nb\nc\n"
    with pytest.raises(ValidationError, match="control character U\\+0007"):
        ProposalArtifact(**artifact_fields(generated_prompt="a\ab\n"))


# --------------------------------------------------------------------------------------
# Outcome and failure taxonomy (sections 12 and 13)
# --------------------------------------------------------------------------------------


def test_outcome_is_two_level_never_a_flat_string() -> None:
    artifact = build_artifact()
    dumped = artifact.model_dump()["outcome"]
    assert dumped == {
        "outcome_class": "PROPOSAL_READY",
        "result_variant": "RECOMMENDATION_READY",
    }
    with pytest.raises(ValidationError):
        ProposalArtifact(**artifact_fields(outcome="PROPOSAL_READY"))


def test_the_two_outcome_branches_cannot_borrow_each_others_field() -> None:
    with pytest.raises(ValidationError):
        FailureOutcome(
            outcome_class="FAILURE",
            result_variant="RECOMMENDATION_READY",  # type: ignore[call-arg]
            failure_code="INPUT_DRIFT",
        )
    with pytest.raises(ValidationError):
        ProposalReadyOutcome(
            outcome_class="PROPOSAL_READY",
            result_variant="RECOMMENDATION_READY",
            failure_code="INPUT_DRIFT",  # type: ignore[call-arg]
        )


def test_outcome_enums_match_the_contract_exactly() -> None:
    assert get_args(OutcomeClass) == ("PROPOSAL_READY", "FAILURE")
    assert set(get_args(ResultVariant)) == {
        "NO_ELIGIBLE_CANDIDATE",
        "RECOMMENDATION_READY",
        "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION",
        "INSUFFICIENT_EVIDENCE",
    }
    assert set(get_args(LifecycleStatus)) == {
        "eligible",
        "blocked",
        "deferred",
        "insufficient_evidence",
        "unknown",
    }


def test_every_failure_code_exists_exactly_once_with_exactly_one_scope() -> None:
    codes = get_args(FailureCode)
    assert len(codes) == len(set(codes))
    assert set(codes) == set(FAILURE_SCOPES)
    assert len(FAILURE_SCOPES) == len(codes)
    assert set(FAILURE_SCOPES.values()) <= set(get_args(FailureScope))


def test_the_per_candidate_scope_is_exactly_the_contract_table() -> None:
    per_candidate = {code for code, scope in FAILURE_SCOPES.items() if scope == "per_candidate"}
    assert per_candidate == {
        "MALFORMED_CANDIDATE",
        "DUPLICATE_CANDIDATE_CONFLICT",
        "UNKNOWN_CANDIDATE_TYPE",
        "DEPENDENCY_CYCLE",
        "STALE_COMPLETION_EVIDENCE",
    }


def test_errors_are_populated_only_on_the_failure_branch() -> None:
    error = ProposalError(
        code="INPUT_DRIFT", path_or_candidate_id="docs/TASK_QUEUE.md", message="drifted"
    )
    with pytest.raises(ValidationError, match="only on the FAILURE branch"):
        ProposalArtifact(**artifact_fields(errors=[error]))
    failure = build_artifact(
        errors=[error],
        outcome=FailureOutcome(outcome_class="FAILURE", failure_code="INPUT_DRIFT"),
    )
    assert failure.outcome.outcome_class == "FAILURE"


# --------------------------------------------------------------------------------------
# Authority confinement (section 22 invariants 5 and 9)
# --------------------------------------------------------------------------------------


def test_authorization_status_is_fixed_and_no_input_can_change_it() -> None:
    assert build_artifact().authorization_status == "NOT_AUTHORIZED"
    for injected in ("AUTHORIZED", "not_authorized", "", "NOT_AUTHORIZED "):
        with pytest.raises(ValidationError):
            ProposalArtifact(**artifact_fields(authorization_status=injected))


def test_human_owner_action_required_cannot_be_overridden() -> None:
    assert build_artifact().human_owner_action_required == HUMAN_OWNER_ACTION_REQUIRED
    with pytest.raises(ValidationError, match="fixed and cannot be overridden"):
        ProposalArtifact(
            **artifact_fields(human_owner_action_required="This proposal is authorized.")
        )


def test_every_model_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProposalArtifact(**artifact_fields(recommendation_is_binding=True))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        candidate(authorized=True)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        repository_identity(remote_url="git@example.invalid:owner/repo.git")


def test_lifecycle_status_is_declared_but_never_author_set_here() -> None:
    assert candidate().lifecycle_status is None


# --------------------------------------------------------------------------------------
# Numeric discipline (section 16.2)
# --------------------------------------------------------------------------------------


def test_floats_are_rejected_and_never_coerced() -> None:
    with pytest.raises(ValidationError):
        EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=1024.0)
    with pytest.raises(ValidationError):
        StaticCatalogSourceReference(
            catalog_path=CATALOG_PATH, catalog_version="1.0", entry_index=4.0
        )


def test_integers_are_int64_range_checked() -> None:
    with pytest.raises(ValidationError, match="signed 64-bit range"):
        EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=2**63)
    with pytest.raises(ValidationError, match="must not be negative"):
        EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=-1)
    assert (
        EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=2**63 - 1).size
        == 2**63 - 1
    )


# --------------------------------------------------------------------------------------
# Repository identity (section 7.1)
# --------------------------------------------------------------------------------------


def test_repository_identity_couples_ahead_behind_to_the_upstream() -> None:
    with pytest.raises(ValidationError, match="absent when no upstream"):
        repository_identity(upstream_ref=None, ahead=0, behind=0)
    with pytest.raises(ValidationError, match="both be present or both be absent"):
        repository_identity(upstream_ref="origin/main", ahead=1, behind=None)
    assert repository_identity(upstream_ref="origin/main", ahead=1, behind=2).behind == 2


def test_repository_identity_requires_absolute_resolved_roots() -> None:
    with pytest.raises(ValidationError, match="absolute POSIX path"):
        repository_identity(resolved_repository_root="relative/path")
    with pytest.raises(ValidationError, match="absolute POSIX path"):
        repository_identity(git_worktree_root="relative/path")


def test_repository_identity_working_tree_lists_are_sorted_relative_paths() -> None:
    with pytest.raises(ValidationError, match="sorted by path"):
        repository_identity(modified_files=["src/b.py", "src/a.py"])
    with pytest.raises(ValidationError, match="repository-relative"):
        repository_identity(untracked_files=["/etc/passwd"])
    with pytest.raises(ValidationError, match=r"'\.\.' path segment"):
        repository_identity(staged_files=["../outside.py"])


# ======================================================================================
# Assembly over a real governed repository (sections 11, 12, 16.1, 16.4, 18)
# ======================================================================================

FIXTURE_CATALOG = "docs/catalog.yaml"
FIXTURE_REGISTRY = "docs/STAGE_REGISTRY.md"
FIXTURE_DECISION_LOG = "docs/DECISION_LOG.md"
FIXTURE_OPEN_QUESTIONS = "docs/OPEN_QUESTIONS.md"
FIXTURE_REPORTS = "docs/reports"

TASK_QUEUE = """# Task Queue

## AUTO-013 — Foreground implementer mode

Status: Done

## AUTO-014 — Merge closeout

Status: Done

## AUTO-016 — A planned successor

Status: Planned
"""

CURRENT_TASK = """# Current Task

No task is currently active.
"""

REMAINING_TASKS = """# Remaining Tasks

## AUTO-016 — A planned successor

Status: Planned
"""

PROJECT_STATE = """# Project State

Version: 1.0.0

Prose about this repository's condition. A mirror, never an independent status source.
"""

STAGE_REGISTRY = """# Stage Registry

## 4. Registry

| Stage | State | Notes |
|---|---|---|
| AUTO-013 | COMPLETE | done |
| AUTO-014 | COMPLETE | done |
| AUTO-016 | NOT_STARTED | planned |
"""

DECISION_LOG = """# Decision Log

Append-only. Newest first.

## 2026-08-02 — Human Owner closed AUTO-014

Rationale for the closure.
"""

OPEN_QUESTIONS = """# Open Questions

## Open

### OD-30 — A question that gates an authorization

- **Question:** Something unresolved.
- **Disposition:** Open. Blocks AUTO-016's authorization until it is answered.

### OD-31 — A question that only affects implementation

- **Question:** Something narrower.
- **Disposition:** Open. Blocks nothing's authorization; affects AUTO-016's implementation.
"""

AUTO_013_REPORT = """# AUTO-013 — Completion Report

| Field | Value |
|---|---|
| Status | Complete |

## Verdict

AUTO-013 is complete.
"""

AUTO_014_REPORT = """# AUTO-014 — Completion Report

| Field | Value |
|---|---|
| Stage | AUTO-014 |
| Status | Committed and pushed; fully validated; governance-closed |

## Verdict

AUTO-014 is complete.
"""


def write_document(repository: Path, relative: str, text: str) -> None:
    target = repository / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def entry_content_hash(entry: dict[str, Any]) -> str:
    """Recompute a catalog entry's section 10.1 digest independently of the reader."""
    payload = {
        key: value
        for key, value in entry.items()
        if key not in {"content_hash", "lifecycle_status"}
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def catalog_entry(candidate_id: str, **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "candidate_id": candidate_id,
        "schema_version": "1.0",
        "title": f"Candidate {candidate_id}",
        "mission": "A bounded, plain-text mission carried as data and never as directive text.",
        "source_kind": "static_catalog",
        "source_reference": {
            "catalog_path": FIXTURE_CATALOG,
            "catalog_version": "1.0",
            "entry_index": 0,
        },
        "mvp_relation": "inside",
        "dependencies": [
            {"dependency_id": "AUTO-014", "dependency_type": "stage", "status": "COMPLETE"}
        ],
        "blockers": [],
        "required_owner_decisions": [],
        "allowed_recommendation_status": True,
        "evidence_references": [],
    }
    record.update(overrides)
    record.setdefault("content_hash", entry_content_hash(record))
    return record


def write_catalog(repository: Path, entries: Sequence[dict[str, Any]]) -> None:
    document = {
        "schema_version": 1,
        "catalog_id": "proposal-test-catalog",
        "authorization_status": "NOT_AUTHORIZED",
        "source_decision": "GOV-AUTO-08",
        "historical_source": "docs/history.md",
        "candidates": list(entries),
    }
    write_document(
        repository,
        FIXTURE_CATALOG,
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=4096),
    )


@pytest.fixture
def governed(
    repository_with_remote: Path, config_factory: Callable[[Path], Path]
) -> tuple[Path, Path, EngineConfig]:
    """A real, governed, pushed Git repository carrying every section 8 document."""
    repository = repository_with_remote
    write_document(repository, "docs/TASK_QUEUE.md", TASK_QUEUE)
    write_document(repository, "docs/current_task.md", CURRENT_TASK)
    write_document(repository, "docs/remain_task.md", REMAINING_TASKS)
    write_document(repository, "docs/PROJECT_STATE.md", PROJECT_STATE)
    write_document(repository, FIXTURE_REGISTRY, STAGE_REGISTRY)
    write_document(repository, FIXTURE_DECISION_LOG, DECISION_LOG)
    write_document(repository, FIXTURE_OPEN_QUESTIONS, OPEN_QUESTIONS)
    write_document(repository, f"{FIXTURE_REPORTS}/AUTO-013-completion-report.md", AUTO_013_REPORT)
    write_document(repository, f"{FIXTURE_REPORTS}/AUTO-014-completion-report.md", AUTO_014_REPORT)

    config_path = config_factory(repository)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw["governance"]["registries"] = [FIXTURE_REGISTRY]
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return repository, config_path, load_config(config_path)


@pytest.fixture
def live_identity(governed: tuple[Path, Path, EngineConfig]) -> RepositoryIdentity:
    _, config_path, config = governed
    return resolve_repository_identity(config, config_path)


@pytest.fixture
def evidence(
    governed: tuple[Path, Path, EngineConfig], live_identity: RepositoryIdentity
) -> EvidenceSet:
    _, _, config = governed
    return read_evidence_set(
        config,
        live_identity,
        EvidenceSources(
            decision_log=FIXTURE_DECISION_LOG,
            open_questions=FIXTURE_OPEN_QUESTIONS,
            completion_reports=FIXTURE_REPORTS,
        ),
    )


@pytest.fixture
def predecessor(evidence: EvidenceSet, live_identity: RepositoryIdentity) -> PredecessorEvidence:
    return resolve_predecessor(evidence, "AUTO-014", identity=live_identity)


def evaluate_catalog(
    repository: Path, evidence: EvidenceSet, entries: Sequence[dict[str, Any]]
) -> tuple[list[Candidate], EligibilityReport, list[Any], EvidenceReference]:
    """Run the real catalog, dependency, completion-claim and eligibility pipeline."""
    write_catalog(repository, entries)
    catalog = read_catalog(repository, FIXTURE_CATALOG)
    resolution = resolve_dependency_graph(
        catalog.candidates,
        known_stages=evidence.known_stage_ids(),
        known_subsystems=("prompt-renderer",),
    )
    findings = [
        *catalog.findings,
        *resolution.findings,
        *stale_completion_findings(check_completion_claims(evidence, catalog.candidates)),
    ]
    report = evaluate_all(
        catalog.candidates,
        open_questions=evidence.open_questions,
        findings=findings,
        unmet_dependencies=resolution.unmet,
    )
    return list(catalog.candidates), report, findings, catalog.reference


def assemble(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
    entries: Sequence[dict[str, Any]],
    *,
    generated_at: str = "2026-08-04T06:06:16Z",
    prompt: str = PROMPT,
) -> RecommendedProposal | UnrecommendedProposal:
    repository, _, _ = governed
    candidates, report, findings, catalog_reference = evaluate_catalog(
        repository, evidence, entries
    )
    return build_proposal(
        identity=live_identity,
        predecessor=predecessor,
        evidence_manifest=[*evidence.manifest, catalog_reference],
        candidates=candidates,
        report=report,
        generated_prompt=prompt,
        generation_metadata=GenerationMetadata(generated_at=generated_at, tool_version="1.0.0"),
        findings=findings,
    )


# --------------------------------------------------------------------------------------
# Section 12 outcome taxonomy, as actually produced
# --------------------------------------------------------------------------------------


def test_exactly_one_eligible_candidate_yields_an_advisory_recommendation(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [
            catalog_entry("alpha-candidate"),
            catalog_entry(
                "beta-candidate",
                blockers=[
                    {
                        "blocker_id": "OD-30",
                        "blocker_type": "open_question",
                        "live_status": "Open",
                    }
                ],
            ),
        ],
    )
    assert isinstance(proposal, RecommendedProposal)
    assert proposal.artifact.outcome.model_dump() == {
        "outcome_class": "PROPOSAL_READY",
        "result_variant": "RECOMMENDATION_READY",
    }
    assert proposal.recommendation.candidate_id == "alpha-candidate"
    assert proposal.recommendation.title == "Candidate alpha-candidate"
    assert proposal.recommendation.rule_id == RULE_ELIGIBLE
    # DEC-004: advisory, and explicitly non-authoritative in the record itself.
    assert "never authority" in proposal.recommendation.advisory_notice
    assert "not selection, registration, authorization" in proposal.recommendation.advisory_notice
    assert proposal.artifact.authorization_status == "NOT_AUTHORIZED"
    assert proposal.artifact.human_owner_action_required == HUMAN_OWNER_ACTION_REQUIRED


def test_multiple_eligible_candidates_have_no_recommendation_field_at_all(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [catalog_entry("alpha-candidate"), catalog_entry("beta-candidate")],
    )
    assert isinstance(proposal, UnrecommendedProposal)
    assert proposal.artifact.outcome.model_dump()["result_variant"] == (
        "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION"
    )
    # DEC-005: structurally absent, not null-valued -- the field does not exist on this shape,
    # and the closed schema refuses one being supplied.
    assert "recommendation" not in UnrecommendedProposal.model_fields
    assert proposal.model_dump().get("recommendation") is None
    assert "recommendation" not in proposal.model_dump()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        UnrecommendedProposal(
            artifact=proposal.artifact,
            recommendation=AdvisoryRecommendation(  # type: ignore[call-arg]
                candidate_id="alpha-candidate",
                title="Candidate alpha-candidate",
                rule_id=RULE_ELIGIBLE,
                reasons=["x"],
            ),
        )
    # Both eligible candidates are listed; neither is singled out or ordered by preference.
    assert [candidate.candidate_id for candidate in proposal.artifact.candidate_list] == [
        "alpha-candidate",
        "beta-candidate",
    ]


def test_no_eligible_candidate_when_every_verdict_is_definite(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [
            catalog_entry(
                "alpha-candidate",
                blockers=[
                    {
                        "blocker_id": "OD-30",
                        "blocker_type": "open_question",
                        "live_status": "Open",
                    }
                ],
            ),
            catalog_entry("beta-candidate", mvp_relation="outside_deferred"),
        ],
    )
    assert isinstance(proposal, UnrecommendedProposal)
    assert proposal.artifact.outcome.model_dump()["result_variant"] == "NO_ELIGIBLE_CANDIDATE"
    statuses = {
        candidate.candidate_id: candidate.lifecycle_status
        for candidate in proposal.artifact.candidate_list
    }
    assert statuses == {"alpha-candidate": "blocked", "beta-candidate": "deferred"}


def test_all_insufficient_evidence_is_the_distinct_whole_proposal_variant(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    """Stale completion evidence for every candidate, really read from a real report set."""
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [
            catalog_entry(
                "alpha-candidate",
                dependencies=[
                    {
                        "dependency_id": "AUTO-016",
                        "dependency_type": "stage",
                        "status": "COMPLETE",
                    }
                ],
            ),
            catalog_entry(
                "beta-candidate",
                dependencies=[
                    {
                        "dependency_id": "AUTO-016",
                        "dependency_type": "stage",
                        "status": "COMPLETE",
                    }
                ],
            ),
        ],
    )
    assert isinstance(proposal, UnrecommendedProposal)
    assert proposal.artifact.outcome.model_dump()["result_variant"] == "INSUFFICIENT_EVIDENCE"
    assert {candidate.lifecycle_status for candidate in proposal.artifact.candidate_list} == {
        "insufficient_evidence"
    }
    assert {decision.rule_id for decision in proposal.artifact.eligibility_decisions} == {
        RULE_INSUFFICIENT_EVIDENCE
    }
    # Section 13 keeps this per-candidate: it is surfaced as a visible warning, never as an
    # error, because the proposal itself succeeded.
    assert {warning.code for warning in proposal.artifact.warnings} == {"STALE_COMPLETION_EVIDENCE"}
    assert proposal.artifact.errors == []


def test_a_dependency_cycle_blocks_every_participant_end_to_end(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [
            catalog_entry(
                "alpha-candidate",
                dependencies=[
                    {
                        "dependency_id": "beta-candidate",
                        "dependency_type": "capability",
                        "status": "pending",
                    }
                ],
            ),
            catalog_entry(
                "beta-candidate",
                dependencies=[
                    {
                        "dependency_id": "alpha-candidate",
                        "dependency_type": "capability",
                        "status": "pending",
                    }
                ],
            ),
        ],
    )
    assert proposal.artifact.outcome.model_dump()["result_variant"] == "NO_ELIGIBLE_CANDIDATE"
    assert {decision.rule_id for decision in proposal.artifact.eligibility_decisions} == {
        RULE_BLOCKED_DEPENDENCY_CYCLE
    }
    assert {warning.code for warning in proposal.artifact.warnings} == {"DEPENDENCY_CYCLE"}


def test_every_candidate_carries_its_computed_status_and_its_rule_citation(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [
            catalog_entry("alpha-candidate"),
            catalog_entry(
                "beta-candidate",
                blockers=[
                    {
                        "blocker_id": "OD-30",
                        "blocker_type": "open_question",
                        "live_status": "Resolved",
                    }
                ],
            ),
        ],
    )
    decisions = {
        decision.candidate_id: decision for decision in proposal.artifact.eligibility_decisions
    }
    assert decisions["alpha-candidate"].rule_id == RULE_ELIGIBLE
    assert decisions["beta-candidate"].rule_id == RULE_BLOCKED_AUTHORIZATION_QUESTION
    assert all(decision.reasons for decision in decisions.values())
    # The catalog declared `Resolved`; the live register says otherwise, and the artifact
    # records the live answer.
    assert [
        (blocker.blocker_id, blocker.live_status, blocker.candidate_id)
        for blocker in proposal.artifact.blockers
    ] == [("OD-30", "Open (blocks authorization)", "beta-candidate")]
    # `lifecycle_status` is set by section 11 and by nothing else: the catalog never carries it.
    assert [candidate.lifecycle_status for candidate in proposal.artifact.candidate_list] == [
        "eligible",
        "blocked",
    ]


# --------------------------------------------------------------------------------------
# Section 16.1 evidence manifest, section 11.3 refusal
# --------------------------------------------------------------------------------------


def test_the_evidence_manifest_binds_every_document_read_including_the_catalog(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    paths = [reference.path for reference in proposal.artifact.evidence_manifest]
    assert paths == sorted(paths)
    assert set(paths) >= {
        "docs/TASK_QUEUE.md",
        "docs/current_task.md",
        "docs/remain_task.md",
        "docs/PROJECT_STATE.md",
        FIXTURE_REGISTRY,
        FIXTURE_DECISION_LOG,
        FIXTURE_OPEN_QUESTIONS,
        FIXTURE_CATALOG,
        f"{FIXTURE_REPORTS}/AUTO-013-completion-report.md",
        f"{FIXTURE_REPORTS}/AUTO-014-completion-report.md",
    }
    assert proposal.artifact.normalized_evidence_hash == normalized_evidence_hash(
        proposal.artifact.evidence_manifest
    )


def test_the_manifest_hash_depends_on_content_not_on_read_order(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    del governed, live_identity, predecessor
    forward = list(evidence.manifest)
    assert normalized_evidence_hash(forward) == normalized_evidence_hash(
        merge_evidence_manifest(list(reversed(forward)))
    )


def test_merging_two_disagreeing_readings_of_one_path_is_refused() -> None:
    first = EvidenceReference(path="docs/TASK_QUEUE.md", sha256="a" * 64, size=10)
    second = EvidenceReference(path="docs/TASK_QUEUE.md", sha256="b" * 64, size=10)
    with pytest.raises(ProposalAssemblyError, match="two different readings"):
        merge_evidence_manifest([first], [second])
    assert merge_evidence_manifest([first], [first]) == [first]


def test_a_refusal_is_labelled_hash_bound_and_lists_no_candidates(
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    refusal = build_refusal(
        identity=live_identity,
        predecessor=predecessor,
        evidence_manifest=evidence.manifest,
        failure_code="MIRROR_CONTRADICTION",
        errors=[
            ProposalError(
                code="MIRROR_CONTRADICTION",
                path_or_candidate_id="docs/current_task.md",
                message="the mirror disagrees with the authoritative task queue",
            )
        ],
        generated_prompt=PROMPT,
        generation_metadata=GenerationMetadata(
            generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0"
        ),
    )
    assert isinstance(refusal, UnrecommendedProposal)
    assert refusal.artifact.outcome.model_dump() == {
        "outcome_class": "FAILURE",
        "failure_code": "MIRROR_CONTRADICTION",
    }
    assert refusal.artifact.candidate_list == []
    assert refusal.artifact.eligibility_decisions == []
    assert refusal.artifact.blockers == []
    assert [error.code for error in refusal.artifact.errors] == ["MIRROR_CONTRADICTION"]
    assert refusal.artifact.authorization_status == "NOT_AUTHORIZED"
    # Hash-bound like any other outcome: the identity is the full digest of its own payload.
    assert (
        refusal.artifact.proposal_id
        == hashlib.sha256(canonical_payload_bytes(refusal.artifact)).hexdigest()
    )
    assert load_and_verify(serialize_artifact(refusal.artifact)).artifact == refusal.artifact


def test_a_refusal_refuses_a_per_candidate_code_and_an_unnamed_failure(
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    metadata = GenerationMetadata(generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0")
    with pytest.raises(ProposalAssemblyError, match="never refuses a whole proposal"):
        build_refusal(
            identity=live_identity,
            predecessor=predecessor,
            evidence_manifest=evidence.manifest,
            failure_code="DEPENDENCY_CYCLE",
            errors=[
                ProposalError(
                    code="DEPENDENCY_CYCLE", path_or_candidate_id="alpha-candidate", message="x"
                )
            ],
            generated_prompt=PROMPT,
            generation_metadata=metadata,
        )
    with pytest.raises(ProposalAssemblyError, match="at least one error carrying that code"):
        build_refusal(
            identity=live_identity,
            predecessor=predecessor,
            evidence_manifest=evidence.manifest,
            failure_code="INPUT_DRIFT",
            errors=[
                ProposalError(
                    code="MIRROR_CONTRADICTION", path_or_candidate_id="docs/x.md", message="x"
                )
            ],
            generated_prompt=PROMPT,
            generation_metadata=metadata,
        )


def test_build_proposal_refuses_a_report_that_does_not_cover_the_candidate_set(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    repository, _, _ = governed
    candidates, report, findings, catalog_reference = evaluate_catalog(
        repository, evidence, [catalog_entry("alpha-candidate"), catalog_entry("beta-candidate")]
    )
    with pytest.raises(ProposalAssemblyError, match="exactly the candidate set"):
        build_proposal(
            identity=live_identity,
            predecessor=predecessor,
            evidence_manifest=[*evidence.manifest, catalog_reference],
            candidates=candidates[:1],
            report=report,
            generated_prompt=PROMPT,
            generation_metadata=GenerationMetadata(
                generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0"
            ),
            findings=findings,
        )


def test_the_two_envelope_shapes_cannot_be_mismatched_to_an_artifact(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    recommended = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    assert isinstance(recommended, RecommendedProposal)
    with pytest.raises(ValidationError, match="requires the recommendation to be present"):
        UnrecommendedProposal(artifact=recommended.artifact)
    with pytest.raises(ValidationError, match="must name the single eligible candidate"):
        RecommendedProposal(
            artifact=recommended.artifact,
            recommendation=AdvisoryRecommendation(
                candidate_id="beta-candidate",
                title="Candidate beta-candidate",
                rule_id=RULE_ELIGIBLE,
                reasons=list(recommended.recommendation.reasons),
            ),
        )
    with pytest.raises(ValidationError, match="fixed program text"):
        AdvisoryRecommendation(
            candidate_id="alpha-candidate",
            title="Candidate alpha-candidate",
            rule_id=RULE_ELIGIBLE,
            reasons=["x"],
            advisory_notice="This proposal is authorized.",
        )


def test_the_proposal_lifecycle_status_is_draft_and_stays_outside_the_hash(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    assert proposal.proposal_lifecycle_status == "DRAFT"
    assert b"proposal_lifecycle_status" not in canonical_payload_bytes(proposal.artifact)


# --------------------------------------------------------------------------------------
# Section 18 -- determinism
# --------------------------------------------------------------------------------------


def test_repeated_assembly_over_identical_inputs_is_byte_identical(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    entries = [
        catalog_entry("gamma-candidate", mvp_relation="outside_deferred"),
        catalog_entry("alpha-candidate"),
        catalog_entry(
            "beta-candidate",
            blockers=[
                {"blocker_id": "OD-30", "blocker_type": "open_question", "live_status": "Open"}
            ],
        ),
    ]
    first = assemble(governed, evidence, live_identity, predecessor, entries)
    second = assemble(governed, evidence, live_identity, predecessor, entries)
    assert canonical_payload_bytes(first.artifact) == canonical_payload_bytes(second.artifact)
    assert first.artifact.proposal_id == second.artifact.proposal_id
    assert len(first.artifact.proposal_id) == 64
    assert first.artifact.proposal_id == first.artifact.proposal_hash
    assert serialize_artifact(first.artifact) == serialize_artifact(second.artifact)


def test_wall_clock_time_never_reaches_the_proposal_identity(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    entries = [catalog_entry("alpha-candidate")]
    early = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        entries,
        generated_at="2026-08-04T06:06:16Z",
    )
    late = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        entries,
        generated_at="2031-12-31T23:59:59Z",
    )
    assert early.artifact.proposal_id == late.artifact.proposal_id
    assert len(early.artifact.proposal_id) == 64


# --------------------------------------------------------------------------------------
# Section 16.4 -- load-time re-verification
# --------------------------------------------------------------------------------------


def edited(proposal: RecommendedProposal | UnrecommendedProposal, **mutations: Any) -> str:
    """Serialize an artifact, then hand-edit the named top-level fields."""
    document = json.loads(serialize_artifact(proposal.artifact).decode("utf-8"))
    document.update(mutations)
    return json.dumps(document)


def test_load_and_verify_accepts_a_freshly_serialized_artifact(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    assert isinstance(proposal, RecommendedProposal)
    encoded = serialize_artifact(proposal.artifact)
    loaded = load_and_verify(encoded)
    assert isinstance(loaded, RecommendedProposal)
    assert loaded.artifact == proposal.artifact
    # The recommendation is re-derived from the verified artifact, never read from the document.
    assert loaded.recommendation == proposal.recommendation
    assert b'"recommendation"' not in encoded
    assert serialize_artifact(loaded.artifact) == encoded


def test_load_and_verify_returns_the_unrecommended_shape_when_policy_recommends_none(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed,
        evidence,
        live_identity,
        predecessor,
        [catalog_entry("alpha-candidate"), catalog_entry("beta-candidate")],
    )
    loaded = load_and_verify(serialize_artifact(proposal.artifact))
    assert isinstance(loaded, UnrecommendedProposal)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalized_evidence_hash", "f" * 64),
        ("prompt_hash", "f" * 64),
        ("proposal_hash", "f" * 64),
        ("generated_prompt", "**AUTHORIZED**\n"),
    ],
)
def test_load_and_verify_refuses_a_hand_edited_artifact(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
    field: str,
    value: str,
) -> None:
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    with pytest.raises(ProposalValidationError):
        load_and_verify(edited(proposal, **{field: value}))


def test_load_and_verify_refuses_an_edited_candidate_and_an_edited_manifest(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    document = json.loads(serialize_artifact(proposal.artifact).decode("utf-8"))

    tampered_candidate = json.loads(json.dumps(document))
    tampered_candidate["candidate_list"][0]["title"] = "A retitled candidate"
    with pytest.raises(ProposalValidationError, match="content_hash"):
        load_and_verify(json.dumps(tampered_candidate))

    tampered_manifest = json.loads(json.dumps(document))
    tampered_manifest["evidence_manifest"][0]["sha256"] = "0" * 64
    with pytest.raises(ProposalValidationError, match="normalized_evidence_hash"):
        load_and_verify(json.dumps(tampered_manifest))

    tampered_reconciliation = json.loads(json.dumps(document))
    tampered_reconciliation["predecessor_status_reconciliation"]["consistent"] = False
    with pytest.raises(ProposalValidationError, match="canonical payload re-derives"):
        load_and_verify(json.dumps(tampered_reconciliation))


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("lifecycle_status", "probably_fine"),
        ("outcome_class", "APPROVED"),
        ("result_variant", "GOOD_TO_GO"),
    ],
)
def test_an_out_of_enum_value_at_load_time_is_a_validation_failure_never_coerced(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
    pointer: str,
    value: str,
) -> None:
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    document = json.loads(serialize_artifact(proposal.artifact).decode("utf-8"))
    if pointer == "lifecycle_status":
        document["candidate_list"][0]["lifecycle_status"] = value
    else:
        document["outcome"][pointer] = value
    with pytest.raises(ProposalValidationError, match="schema validation"):
        load_and_verify(json.dumps(document))


def test_an_out_of_enum_failure_code_at_load_time_is_a_validation_failure(
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    refusal = build_refusal(
        identity=live_identity,
        predecessor=predecessor,
        evidence_manifest=evidence.manifest,
        failure_code="INPUT_DRIFT",
        errors=[
            ProposalError(
                code="INPUT_DRIFT",
                path_or_candidate_id="docs/TASK_QUEUE.md",
                message="the final snapshot disagrees with the initial snapshot",
            )
        ],
        generated_prompt=PROMPT,
        generation_metadata=GenerationMetadata(
            generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0"
        ),
    )
    document = json.loads(serialize_artifact(refusal.artifact).decode("utf-8"))
    document["outcome"]["failure_code"] = "EVERYTHING_IS_FINE"
    with pytest.raises(ProposalValidationError, match="schema validation"):
        load_and_verify(json.dumps(document))


def test_an_in_enum_but_unearned_lifecycle_status_still_fails_the_digest(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    """`unknown` parses, but the payload digest still refuses the edit."""
    proposal = assemble(
        governed, evidence, live_identity, predecessor, [catalog_entry("alpha-candidate")]
    )
    document = json.loads(serialize_artifact(proposal.artifact).decode("utf-8"))
    document["candidate_list"][0]["lifecycle_status"] = "unknown"
    with pytest.raises(ProposalValidationError, match="canonical payload re-derives"):
        load_and_verify(json.dumps(document))


def test_load_and_verify_refuses_malformed_input_outright(
    governed: tuple[Path, Path, EngineConfig],
    evidence: EvidenceSet,
    live_identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
) -> None:
    del governed, evidence, live_identity, predecessor
    with pytest.raises(ProposalValidationError, match="not parsable JSON"):
        load_and_verify(b"{not json")
    with pytest.raises(ProposalValidationError, match="must be a JSON object"):
        load_and_verify(b"[]")
    with pytest.raises(ProposalValidationError, match="not valid UTF-8"):
        load_and_verify(b"\xff\xfe")
