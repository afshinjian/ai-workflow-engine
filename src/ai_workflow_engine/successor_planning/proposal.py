"""Hash-bound proposal assembly, refusal records and load-time re-verification (AUTO-015).

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 11.1/11.2
(DEC-004's advisory recommendation and DEC-005's recommend-none), 11.3 (never auto-select,
always advisory, refusal semantics), 12 (the two-level outcome), 13 (failure scope), 16.1 (the
proposal artifact schema), 16.2 (canonicalization), 16.4 (load-time re-verification), 18
(idempotency and determinism), 20 (state ownership) and 22 invariants 5-8.

This module assembles; it never publishes. It performs no filesystem or Git access, spawns no
provider, and owns no task, Registry or workflow state. Section 17's atomic, no-clobber
publication is a separate concern, and :func:`serialize_artifact` here is only the encoding
:func:`load_and_verify` accepts -- it writes nothing.

Why the recommendation is not a field on the artifact
-----------------------------------------------------
Section 16.1's schema table has no `recommendation` member, and section 11.2 requires that with
more than one eligible candidate the recommendation be *structurally absent, never null-valued*.
Both are satisfied here by shape rather than by a nullable field: :class:`RecommendedProposal`
has a `recommendation`, :class:`UnrecommendedProposal` has no such field at all, and the two are
discriminated on `recommendation_presence`. Because both models are closed (`extra="forbid"`),
an `UnrecommendedProposal` cannot be handed one and a `RecommendedProposal` cannot omit it.

The recommendation itself carries no independent content. Every one of its fields is re-derived
from the artifact's own hash-bound data -- the single `eligible` decision, its section 11 rule
citation and reasons, and that candidate's title -- and a model validator re-asserts the
agreement on every construction, including every load. So the recommendation is bound to the
proposal digest transitively: it cannot be altered without altering the artifact it is derived
from, and :func:`load_and_verify` reconstructs it from the verified artifact rather than reading
it from the document.

What a refusal record is
------------------------
Section 11.3 requires whole-evidence-set inconsistency to produce a labelled, hash-bound refusal
record rather than a bare exception, and to produce no candidate list at all.
:func:`build_refusal` is that path: same schema, same canonicalization, same full-digest
identity, with `candidate_list`, `eligibility_decisions` and `blockers` empty and `errors`
carrying the section 13 code. Because section 16.1 makes the predecessor fields mandatory, a
refusal record requires resolved predecessor evidence; a failure raised *before* the predecessor
resolves has nothing to bind an artifact to and is therefore not representable as one under this
schema.

Determinism
-----------
`proposal_id` is the full 64-character digest of the canonical payload and nothing else. Wall
clock time reaches no hashed field: it lives only in `generation_metadata`, which
`canonical_payload_bytes` excludes. Every list is placed in its section 16.2 canonical order
before the digest is taken, so repeating an assembly over identical evidence reproduces
byte-identical payload bytes and an identical identity.
"""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from ai_workflow_engine import __version__
from ai_workflow_engine.config import load_config
from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.successor_planning.catalog import (
    CandidateFinding,
    CandidateRedaction,
    CatalogError,
    candidate_content_hash,
    read_catalog,
    resolve_dependency_graph,
    safe_message,
)
from ai_workflow_engine.successor_planning.eligibility import (
    RECOMMENDATION_POLICY,
    SECTION_11_RULES,
    EligibilityReport,
    evaluate_all,
)
from ai_workflow_engine.successor_planning.models import (
    FAILURE_SCOPES,
    MAX_MESSAGE_CHARS,
    MAX_PATH_CHARS,
    MAX_ROOT_PATH_CHARS,
    MAX_TITLE_CHARS,
    Candidate,
    EvidenceReference,
    FailureCode,
    FailureOutcome,
    GenerationMetadata,
    ProposalArtifact,
    ProposalError,
    ProposalReadyOutcome,
    ProposalWarning,
    RepositoryIdentity,
    SuccessorPlanningModel,
    _hex64,
    _require_sorted_unique,
    _scalar,
    canonical_payload_bytes,
)
from ai_workflow_engine.successor_planning.prompt import (
    SECRET_REDACTED_WARNING,
    PromptSecretError,
    PromptSecurityError,
    PromptValidationError,
    RenderedPrompt,
    render_prompt,
    validate_prompt_structure,
)
from ai_workflow_engine.successor_planning.snapshot import (
    EvidenceSnapshot,
    RepositoryIdentityMismatchError,
    SnapshotError,
    _resolve_configured_root,
    canonical_repository_id,
    compare_snapshots,
    normalize_evidence_text,
    read_evidence_bytes,
    take_snapshot,
)
from ai_workflow_engine.successor_planning.sources import (
    EvidenceSet,
    EvidenceSources,
    PredecessorError,
    PredecessorEvidence,
    UnauthorizedSuccessorError,
    check_completion_claims,
    check_no_unauthorized_successor,
    read_evidence_set,
    reconcile_mirrors,
    resolve_predecessor,
    run_required_governance_checks,
    stale_completion_findings,
)

#: Section 20's own small, non-authoritative status for the proposal artifact itself. It is
#: `DRAFT` at generation and never anything else here: the artifact is immutable once persisted,
#: and a new proposal over new evidence is a new, distinctly addressed artifact rather than an
#: edit of this one. It carries no authority over the stage-lifecycle or runtime-workflow state
#: machines and is deliberately outside the hashed payload.
PROPOSAL_LIFECYCLE_STATUS = "DRAFT"


class ProposalAssemblyError(WorkflowEngineError):
    """The inputs handed to an assembly function do not describe one coherent proposal.

    Section 13's `INVALID_INVOCATION` covers a caller supplying invalid inputs, which is exactly
    this: a verdict set that does not match the candidate set, a manifest that records two
    different digests for one path, a refusal carrying a per-candidate code. None of these is an
    evidence finding to be reported inside an artifact -- there is no coherent artifact to report
    it in -- so it is raised rather than embedded.
    """

    code: ClassVar[FailureCode] = "INVALID_INVOCATION"


class ProposalValidationError(WorkflowEngineError):
    """A persisted artifact failed section 16.4's re-derivation and is refused.

    Section 13 gives this `PROMPT_VALIDATION_FAILURE`, whole-proposal. Every path into it is a
    refusal: no value is ever coerced to a nearest-known one, and no partially valid artifact is
    returned.
    """

    code: ClassVar[FailureCode] = "PROMPT_VALIDATION_FAILURE"


# --------------------------------------------------------------------------------------
# Section 16.1 -- the evidence manifest and its hash
# --------------------------------------------------------------------------------------


def merge_evidence_manifest(*groups: Sequence[EvidenceReference]) -> list[EvidenceReference]:
    """Merge evidence references into one section 16.2-ordered, path-unique manifest.

    Two references to the same path must agree on both digest and size. They are two readings of
    one document, so a disagreement is a torn read rather than something to resolve by keeping
    whichever arrived first -- it is refused.
    """
    merged: dict[str, EvidenceReference] = {}
    for group in groups:
        for reference in group:
            existing = merged.get(reference.path)
            if existing is None:
                merged[reference.path] = reference
                continue
            if existing.sha256 != reference.sha256 or existing.size != reference.size:
                raise ProposalAssemblyError(
                    f"The evidence manifest records two different readings of "
                    f"{reference.path!r}: {existing.sha256} and {reference.sha256}"
                )
    return [merged[path] for path in sorted(merged, key=lambda path: path.encode("utf-8"))]


def normalized_evidence_hash(manifest: Sequence[EvidenceReference]) -> str:
    """Hash the whole sorted evidence manifest into section 16.1's single digest.

    Taken over the manifest already in section 16.2 evidence order, through `canonical_json`, so
    the digest depends on the set of documents read and their content -- never on the order the
    reader happened to visit them in.
    """
    ordered = [reference.model_dump() for reference in manifest]
    _require_sorted_unique(
        [str(reference["path"]) for reference in ordered], "evidence manifest", "path"
    )
    return hashlib.sha256(canonical_json(ordered)).hexdigest()


# --------------------------------------------------------------------------------------
# Section 11.1 -- the advisory recommendation and its two record shapes
# --------------------------------------------------------------------------------------


class AdvisoryRecommendation(SuccessorPlanningModel):
    """DEC-004's advisory recommendation for the one eligible candidate.

    Every field is a re-statement of hash-bound artifact data, and `advisory_notice` is fixed
    program text checked byte-for-byte against the policy constant -- no candidate, document or
    configuration value can substitute for it, shorten it, or append to it. Section 11.1 makes
    the recommendation informational: it is never selection, registration, authorization,
    implementation permission or Human Owner approval.
    """

    candidate_id: str
    title: str
    rule_id: str
    reasons: list[str]
    advisory_notice: str = RECOMMENDATION_POLICY.advisory_notice

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "recommendation title", MAX_TITLE_CHARS)

    @field_validator("rule_id")
    @classmethod
    def _validate_rule_id(cls, value: str) -> str:
        if value not in SECTION_11_RULES:
            raise ValueError(f"{value!r} is not a section 11 rule identifier")
        return value

    @field_validator("reasons")
    @classmethod
    def _validate_reasons(cls, value: list[str]) -> list[str]:
        for reason in value:
            _scalar(reason, "recommendation reason", MAX_MESSAGE_CHARS)
        _require_sorted_unique(value, "reasons", "reason text", bytewise=False)
        return value

    @field_validator("advisory_notice")
    @classmethod
    def _validate_notice(cls, value: str) -> str:
        if value != RECOMMENDATION_POLICY.advisory_notice:
            raise ValueError("advisory_notice is fixed program text and cannot be overridden")
        return value


def _eligible_decision_ids(artifact: ProposalArtifact) -> list[str]:
    return [
        decision.candidate_id
        for decision in artifact.eligibility_decisions
        if decision.lifecycle_status == "eligible"
    ]


class RecommendedProposal(SuccessorPlanningModel):
    """The DEC-004 branch: exactly one eligible candidate, recommended advisorily.

    The recommendation is re-checked against the artifact on every construction, so a hand-built
    or hand-edited pairing whose recommendation does not follow from the hashed artifact is
    refused rather than reported.
    """

    recommendation_presence: Literal["PRESENT"] = "PRESENT"
    proposal_lifecycle_status: Literal["DRAFT"] = "DRAFT"
    artifact: ProposalArtifact
    recommendation: AdvisoryRecommendation

    @model_validator(mode="after")
    def _validate_agreement(self) -> "RecommendedProposal":
        outcome = self.artifact.outcome
        if outcome.outcome_class != "PROPOSAL_READY":
            raise ValueError("a recommendation exists only on the PROPOSAL_READY branch")
        if outcome.result_variant != "RECOMMENDATION_READY":
            raise ValueError(
                f"a recommendation exists only in the RECOMMENDATION_READY variant, not "
                f"{outcome.result_variant}"
            )
        eligible = _eligible_decision_ids(self.artifact)
        if eligible != [self.recommendation.candidate_id]:
            raise ValueError(
                "the recommendation must name the single eligible candidate, but the artifact "
                f"records {eligible}"
            )
        decision = next(
            decision
            for decision in self.artifact.eligibility_decisions
            if decision.candidate_id == self.recommendation.candidate_id
        )
        if decision.rule_id != self.recommendation.rule_id:
            raise ValueError("the recommendation must cite the rule the artifact's verdict cited")
        if decision.reasons != self.recommendation.reasons:
            raise ValueError("the recommendation must carry the artifact's own verdict reasons")
        titles = {
            candidate.candidate_id: candidate.title for candidate in self.artifact.candidate_list
        }
        if titles.get(self.recommendation.candidate_id) != self.recommendation.title:
            raise ValueError("the recommendation's title must be the candidate's own title")
        return self


class UnrecommendedProposal(SuccessorPlanningModel):
    """Every other outcome: no `recommendation` field exists on this record at all.

    This is section 11.2's "structurally absent, not null-valued" made literal. It covers
    `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION` (DEC-005 -- all eligible candidates listed, none
    recommended, none ranked), `NO_ELIGIBLE_CANDIDATE`, the whole-proposal `INSUFFICIENT_EVIDENCE`
    variant, and every section 13 refusal.
    """

    recommendation_presence: Literal["ABSENT"] = "ABSENT"
    proposal_lifecycle_status: Literal["DRAFT"] = "DRAFT"
    artifact: ProposalArtifact

    @model_validator(mode="after")
    def _validate_absence(self) -> "UnrecommendedProposal":
        outcome = self.artifact.outcome
        if outcome.outcome_class == "PROPOSAL_READY":
            if outcome.result_variant == "RECOMMENDATION_READY":
                raise ValueError(
                    "RECOMMENDATION_READY requires the recommendation to be present (DEC-004)"
                )
            if _eligible_decision_ids(self.artifact) and outcome.result_variant != (
                "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION"
            ):
                raise ValueError(
                    f"{outcome.result_variant} must record no eligible candidate, but the "
                    "artifact records at least one"
                )
        return self


#: The assembled proposal, discriminated on whether a recommendation exists at all.
SuccessorProposal = Annotated[
    RecommendedProposal | UnrecommendedProposal,
    Field(discriminator="recommendation_presence"),
]


# --------------------------------------------------------------------------------------
# Section 16.1 -- assembly
# --------------------------------------------------------------------------------------

_PLACEHOLDER_DIGEST = "0" * 64


def _warnings_from_findings(findings: Sequence[CandidateFinding]) -> list[ProposalWarning]:
    """Carry every per-candidate section 10.2/13 finding into the artifact as a warning.

    A per-candidate finding excludes or gates one candidate; it does not fail the proposal, and
    section 16.1 populates `errors` only on the `FAILURE` branch. So a finding is surfaced as a
    visible warning rather than silently dropped -- section 10.2 requires every excluded entry to
    be accounted for.
    """
    return [
        ProposalWarning(
            code=finding.code,
            path_or_candidate_id=finding.candidate_id,
            message=finding.message,
        )
        for finding in findings
    ]


def _warnings_from_redactions(redactions: Sequence[CandidateRedaction]) -> list[ProposalWarning]:
    """Surface every catalog redaction as the visible warning section 22 invariant 2 requires.

    The catalog reader redacts a candidate's repository-sourced text before that candidate can
    reach `candidate_list` (section 16.1). Section 22 invariant 2 makes the redaction event
    itself a recorded finding rather than a silent substitution, and section 13 classes a
    successful redaction as a warning, not a failure.
    """
    return [
        ProposalWarning(
            code=SECRET_REDACTED_WARNING,
            path_or_candidate_id=redaction.candidate_id,
            message=(
                f"{redaction.occurrences} secret-shaped value(s) matching "
                f"{redaction.pattern_name} were redacted from this candidate's catalog "
                "definition before it was rendered or persisted; the original bytes were "
                "discarded, not encoded."
            ),
        )
        for redaction in redactions
    ]


def _ordered_warnings(warnings: Sequence[ProposalWarning]) -> list[ProposalWarning]:
    """Section 16.2 warning order, made total so equal keys cannot depend on read timing."""
    unique = {
        (warning.code, warning.path_or_candidate_id, warning.message): warning
        for warning in warnings
    }
    return [unique[key] for key in sorted(unique)]


def _ordered_errors(errors: Sequence[ProposalError]) -> list[ProposalError]:
    unique = {(error.code, error.path_or_candidate_id, error.message): error for error in errors}
    return [unique[key] for key in sorted(unique)]


def _finalize(fields: dict[str, Any]) -> ProposalArtifact:
    """Bind the artifact to its own canonical digest (section 16.1's full-digest identity).

    Two passes, and they are not interchangeable: the digest is taken over the canonical payload,
    which excludes `proposal_hash` and `proposal_id` precisely so the placeholder used in the
    first pass cannot influence the digest computed from it.
    """
    draft = ProposalArtifact(
        **{**fields, "proposal_id": _PLACEHOLDER_DIGEST, "proposal_hash": _PLACEHOLDER_DIGEST}
    )
    digest = hashlib.sha256(canonical_payload_bytes(draft)).hexdigest()
    return ProposalArtifact(**{**fields, "proposal_id": digest, "proposal_hash": digest})


def build_proposal(
    *,
    identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
    evidence_manifest: Sequence[EvidenceReference],
    candidates: Sequence[Candidate],
    report: EligibilityReport,
    generated_prompt: str,
    generation_metadata: GenerationMetadata,
    findings: Sequence[CandidateFinding] = (),
    warnings: Sequence[ProposalWarning] = (),
) -> RecommendedProposal | UnrecommendedProposal:
    """Assemble the section 16.1 hash-bound proposal artifact from evaluated evidence.

    `report` must cover exactly `candidates`: a verdict without a candidate, or a candidate
    without a verdict, is an incoherent proposal rather than one to publish with a gap in it.
    Each candidate is placed in `candidate_list` carrying the `lifecycle_status` section 11
    computed for it -- the one place that field is ever set, and never by the catalog.

    `generated_prompt` is supplied by the caller. This module does not render Markdown; the
    governed-prompt renderer is a separate concern, and the prompt is embedded and hashed here
    exactly as given.

    The returned record is a :class:`RecommendedProposal` only when section 11.1's exactly-one-
    eligible condition holds; every other variant returns an :class:`UnrecommendedProposal`,
    whose shape has no `recommendation` field. No ranking is applied in any branch.
    """
    ordered = sorted(candidates, key=lambda candidate: candidate.candidate_id.encode("utf-8"))
    verdict_ids = [verdict.candidate_id for verdict in report.verdicts]
    if verdict_ids != [candidate.candidate_id for candidate in ordered]:
        raise ProposalAssemblyError(
            "The eligibility report must cover exactly the candidate set: it records "
            f"{verdict_ids} against candidates "
            f"{[candidate.candidate_id for candidate in ordered]}"
        )

    statuses = {verdict.candidate_id: verdict.lifecycle_status for verdict in report.verdicts}
    evaluated = [
        candidate.model_copy(update={"lifecycle_status": statuses[candidate.candidate_id]})
        for candidate in ordered
    ]
    manifest = merge_evidence_manifest(evidence_manifest)

    fields: dict[str, Any] = {
        "repository_identity": identity,
        "predecessor_stage_id": predecessor.stage_id,
        "predecessor_registry_evidence": predecessor.registry_evidence,
        "predecessor_completion_evidence": list(predecessor.completion_evidence),
        "predecessor_status_reconciliation": predecessor.reconciliation,
        "evidence_manifest": manifest,
        "normalized_evidence_hash": normalized_evidence_hash(manifest),
        "candidate_list": evaluated,
        "eligibility_decisions": report.decisions(),
        "blockers": list(report.blockers),
        "outcome": ProposalReadyOutcome(
            outcome_class="PROPOSAL_READY", result_variant=report.result_variant
        ),
        "generated_prompt": generated_prompt,
        "prompt_hash": hashlib.sha256(generated_prompt.encode("utf-8")).hexdigest(),
        "warnings": _ordered_warnings([*warnings, *_warnings_from_findings(findings)]),
        "errors": [],
        "generation_metadata": generation_metadata,
    }
    artifact = _finalize(fields)

    recommended = report.recommended_candidate_id()
    if recommended is None:
        return UnrecommendedProposal(artifact=artifact)
    decision = next(
        item for item in artifact.eligibility_decisions if item.candidate_id == recommended
    )
    title = next(item.title for item in artifact.candidate_list if item.candidate_id == recommended)
    return RecommendedProposal(
        artifact=artifact,
        recommendation=AdvisoryRecommendation(
            candidate_id=recommended,
            title=title,
            rule_id=decision.rule_id,
            reasons=list(decision.reasons),
        ),
    )


def build_refusal(
    *,
    identity: RepositoryIdentity,
    predecessor: PredecessorEvidence,
    evidence_manifest: Sequence[EvidenceReference],
    failure_code: FailureCode,
    errors: Sequence[ProposalError],
    generated_prompt: str,
    generation_metadata: GenerationMetadata,
    warnings: Sequence[ProposalWarning] = (),
) -> UnrecommendedProposal:
    """Assemble section 11.3's labelled, hash-bound refusal record.

    Whole-evidence-set inconsistency -- disagreeing mirrors, a failed governance check, an
    unconfirmable predecessor completion, a repository-identity mismatch, input drift -- produces
    no candidate list and no recommendation at all, only this record. It is never a bare
    exception and never a partial list: `candidate_list`, `eligibility_decisions` and `blockers`
    are empty by construction rather than by the caller's discipline.

    `failure_code` must be a whole-proposal code and must be named by at least one of `errors`.
    A per-candidate code arriving here would silently promote a candidate exclusion into a
    refusal, which section 13's one-code-one-scope table forbids.
    """
    if FAILURE_SCOPES[failure_code] != "whole_proposal":
        raise ProposalAssemblyError(
            f"{failure_code} is a per-candidate code and never refuses a whole proposal"
        )
    ordered_errors = _ordered_errors(errors)
    if not any(error.code == failure_code for error in ordered_errors):
        raise ProposalAssemblyError(
            f"A {failure_code} refusal must record at least one error carrying that code"
        )

    manifest = merge_evidence_manifest(evidence_manifest)
    fields: dict[str, Any] = {
        "repository_identity": identity,
        "predecessor_stage_id": predecessor.stage_id,
        "predecessor_registry_evidence": predecessor.registry_evidence,
        "predecessor_completion_evidence": list(predecessor.completion_evidence),
        "predecessor_status_reconciliation": predecessor.reconciliation,
        "evidence_manifest": manifest,
        "normalized_evidence_hash": normalized_evidence_hash(manifest),
        "candidate_list": [],
        "eligibility_decisions": [],
        "blockers": [],
        "outcome": FailureOutcome(outcome_class="FAILURE", failure_code=failure_code),
        "generated_prompt": generated_prompt,
        "prompt_hash": hashlib.sha256(generated_prompt.encode("utf-8")).hexdigest(),
        "warnings": _ordered_warnings(warnings),
        "errors": ordered_errors,
        "generation_metadata": generation_metadata,
    }
    return UnrecommendedProposal(artifact=_finalize(fields))


# --------------------------------------------------------------------------------------
# Section 16.4 -- load-time re-verification
# --------------------------------------------------------------------------------------


def serialize_artifact(artifact: ProposalArtifact) -> bytes:
    """Encode a whole artifact, including its identity and metadata, as canonical JSON.

    This is the encoding :func:`load_and_verify` accepts, and nothing more: it opens no file and
    publishes nothing. It differs from `canonical_payload_bytes` deliberately -- that function
    produces the *hashed* payload, which excludes the digest fields and `generation_metadata`,
    while a stored document must carry all three.
    """
    return canonical_json(artifact.model_dump())


def _parse_document(document: bytes | str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(document, Mapping):
        return document
    if isinstance(document, bytes):
        try:
            document = document.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProposalValidationError(
                f"The persisted proposal is not valid UTF-8: {safe_message(exc)}"
            ) from exc
    try:
        parsed: Any = json.loads(document)
    except ValueError as exc:
        raise ProposalValidationError(
            f"The persisted proposal is not parsable JSON: {safe_message(exc)}"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise ProposalValidationError("The persisted proposal must be a JSON object")
    return parsed


def load_and_verify(
    document: bytes | str | Mapping[str, Any],
) -> RecommendedProposal | UnrecommendedProposal:
    """Re-derive every embedded hash before treating a persisted artifact as valid (section 16.4).

    Nothing is trusted at rest. In order: the document is parsed and validated against the closed
    section 16.1 schema, so a `lifecycle_status`, `outcome_class`, `result_variant` or
    `failure_code` outside its declared enum is a validation failure and is never coerced to a
    nearest-known value; each candidate's `content_hash` is recomputed from its own canonical
    fields; the evidence manifest's aggregate hash is recomputed; the embedded prompt is
    re-hashed; and the full canonical payload is re-digested and compared against both
    `proposal_hash` and `proposal_id`. Any mismatch refuses the artifact outright -- a
    hand-edited document cannot pass.

    The recommendation is reconstructed from the verified artifact rather than read from the
    document, so section 11.1's advisory record is exactly as trustworthy as the digest that
    covers the data it is derived from, and section 11.2's structural absence cannot be forged.
    """
    payload = _parse_document(document)
    try:
        artifact = ProposalArtifact.model_validate(dict(payload))
    except ValidationError as exc:
        raise ProposalValidationError(
            f"The persisted proposal failed schema validation: {safe_message(exc)}"
        ) from exc

    for candidate in artifact.candidate_list:
        recomputed = candidate_content_hash(candidate)
        if recomputed != candidate.content_hash:
            raise ProposalValidationError(
                f"Candidate {candidate.candidate_id}'s content_hash is "
                f"{candidate.content_hash} but re-derives to {recomputed}"
            )

    evidence_digest = normalized_evidence_hash(artifact.evidence_manifest)
    if evidence_digest != artifact.normalized_evidence_hash:
        raise ProposalValidationError(
            f"normalized_evidence_hash is {artifact.normalized_evidence_hash} but the embedded "
            f"evidence manifest re-derives to {evidence_digest}"
        )

    prompt_digest = hashlib.sha256(artifact.generated_prompt.encode("utf-8")).hexdigest()
    if prompt_digest != artifact.prompt_hash:
        raise ProposalValidationError(
            f"prompt_hash is {artifact.prompt_hash} but the embedded prompt re-derives to "
            f"{prompt_digest}"
        )

    proposal_digest = hashlib.sha256(canonical_payload_bytes(artifact)).hexdigest()
    if proposal_digest != artifact.proposal_hash or proposal_digest != artifact.proposal_id:
        raise ProposalValidationError(
            f"proposal_hash is {artifact.proposal_hash} but the canonical payload re-derives to "
            f"{proposal_digest}"
        )

    eligible = _eligible_decision_ids(artifact)
    outcome = artifact.outcome
    if outcome.outcome_class == "PROPOSAL_READY" and outcome.result_variant == (
        "RECOMMENDATION_READY"
    ):
        if len(eligible) != 1:
            raise ProposalValidationError(
                f"RECOMMENDATION_READY requires exactly one eligible candidate, found {eligible}"
            )
        decision = next(
            item for item in artifact.eligibility_decisions if item.candidate_id == eligible[0]
        )
        titles = {item.candidate_id: item.title for item in artifact.candidate_list}
        if eligible[0] not in titles:
            raise ProposalValidationError(
                f"The eligible candidate {eligible[0]} has no entry in the candidate list"
            )
        try:
            return RecommendedProposal(
                artifact=artifact,
                recommendation=AdvisoryRecommendation(
                    candidate_id=eligible[0],
                    title=titles[eligible[0]],
                    rule_id=decision.rule_id,
                    reasons=list(decision.reasons),
                ),
            )
        except ValidationError as exc:
            raise ProposalValidationError(
                f"The persisted proposal's recommendation cannot be re-derived from its own "
                f"verified data: {safe_message(exc)}"
            ) from exc
    try:
        return UnrecommendedProposal(artifact=artifact)
    except ValidationError as exc:
        raise ProposalValidationError(
            f"The persisted proposal's outcome and eligibility decisions disagree: "
            f"{safe_message(exc)}"
        ) from exc


# --------------------------------------------------------------------------------------
# Sections 4, 5 and 23.2 -- the flow-composing application entry point
# --------------------------------------------------------------------------------------
#
# Section 23.2 fixes the CLI as a thin adapter that delegates *entirely* to this module with no
# business logic of its own, so the operation composing section 5's flow has to live here: the
# adapter may not host it, and no other module in this package is the whole flow's owner.
# Everything above this line stays exactly what it was -- the assembly primitives -- and nothing
# below rewrites them; this section only calls them in section 5's order.
#
# Where the non-`EngineConfig` inputs come from
# ---------------------------------------------
# DEC-011 states that policy and identity inputs come only from validated configuration and this
# contract, and section 23.4 confirms `self-governance.yaml` needs no new field. The active
# `EngineConfig` therefore supplies every location it already defines (task queue, its two
# mirrors, the project state, the stage registries, the handover manifest and files), and the
# four locations it does not define are fixed here as contract constants naming exactly the
# documents sections 8, 9 and 23.6 name. They are constants rather than new configuration fields
# precisely because widening the configuration surface would broaden a contract this stage may
# only implement.


#: Section 8 item 7 / section 9: the one static authoritative catalog DEC-003 fixes. No candidate
#: is ever read from any other file, and none is derived from prose.
CATALOG_PATH = "docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml"

#: Section 8 item 4.
DECISION_LOG_PATH = "docs/DECISION_LOG.md"

#: Section 7.3 step 9 / section 11: the live blocker register eligibility is re-resolved against.
OPEN_QUESTIONS_PATH = "docs/workflow-automation/OPEN_QUESTIONS.md"

#: Section 8 item 3: the completion-report directory, read one level deep.
COMPLETION_REPORTS_PATH = "docs/reports/workflow-automation"

#: The three section 8 locations `EngineConfig` does not itself define, bound once.
EVIDENCE_SOURCES = EvidenceSources(
    decision_log=DECISION_LOG_PATH,
    open_questions=OPEN_QUESTIONS_PATH,
    completion_reports=COMPLETION_REPORTS_PATH,
)

#: Section 23.2's `--output console|json`. It selects a rendering, never a behaviour: this module
#: records the requested mode so the adapter can act on it and formats nothing itself.
OutputMode = Literal["console", "json"]

#: The subject recorded on a failure that concerns the invocation as a whole rather than one
#: document or candidate. `ProposalError.path_or_candidate_id` is mandatory, and inventing a
#: plausible-looking path for a failure that has none would be worse than naming it plainly.
INVOCATION_SUBJECT = "(invocation)"


class PublicationRecord(SuccessorPlanningModel):
    """Where one invocation's artifact ended up, and whether this run is what put it there.

    `created` is `False` on section 17.2's idempotent path: an identical artifact was already at
    this content address, so nothing was written and that is a success, not a conflict.
    """

    artifact_path: str
    proposal_id: str
    created: bool

    @field_validator("artifact_path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _scalar(value, "artifact_path", MAX_ROOT_PATH_CHARS)

    @field_validator("proposal_id")
    @classmethod
    def _validate_proposal_id(cls, value: str) -> str:
        return _hex64(value, "proposal_id")


class ProposalRun(SuccessorPlanningModel):
    """One invocation's typed application result, suitable for console or JSON rendering.

    Three shapes are representable, and they are deliberately distinguishable:

    * **A ready proposal** -- `outcome_class` is `PROPOSAL_READY`, `proposal` carries the
      assembled record (whose own shape says whether DEC-004's advisory recommendation exists),
      no error is recorded, and `publication` is present unless this was a dry run.
    * **A refusal** -- `outcome_class` is `FAILURE`, `failure_code` names the section 13 code,
      and `proposal` carries section 11.3's hash-bound refusal *record* when the failure was
      reached late enough for one to exist at all. A refusal is published like any other
      outcome, so `publication` may be present here too.
    * **A bare failure** -- `outcome_class` is `FAILURE` and `proposal` is `None`, because the
      failure happened before the predecessor resolved and section 16.1 makes the predecessor
      fields mandatory: there is nothing to bind an artifact to yet.

    A publication failure is the one case where `proposal` carries a `PROPOSAL_READY` artifact
    while `failure_code` is set: the proposal really was assembled and validated, and only the
    write failed. Collapsing that into a bare failure would discard the artifact the operator
    can still inspect.
    """

    outcome_class: Literal["PROPOSAL_READY", "FAILURE"]
    predecessor_stage_id: str | None
    output: OutputMode
    dry_run: bool
    proposal: RecommendedProposal | UnrecommendedProposal | None
    publication: PublicationRecord | None
    failure_code: FailureCode | None
    errors: list[ProposalError]

    @model_validator(mode="after")
    def _validate_coherence(self) -> "ProposalRun":
        if self.outcome_class == "PROPOSAL_READY":
            if self.failure_code is not None or self.errors:
                raise ValueError("a PROPOSAL_READY run records no failure code and no error")
            if self.proposal is None:
                raise ValueError("a PROPOSAL_READY run carries the proposal it assembled")
            if self.proposal.artifact.outcome.outcome_class != "PROPOSAL_READY":
                raise ValueError("the run and its artifact must agree on the outcome class")
        else:
            if self.failure_code is None:
                raise ValueError("a FAILURE run names the section 13 code that produced it")
            if FAILURE_SCOPES[self.failure_code] != "whole_proposal":
                raise ValueError(
                    f"{self.failure_code} is a per-candidate code and never fails a whole run"
                )
            if not any(error.code == self.failure_code for error in self.errors):
                raise ValueError("a FAILURE run records at least one error carrying its code")
        if self.dry_run and self.publication is not None:
            raise ValueError("--dry-run publishes nothing, so it records no publication")
        return self

    @property
    def artifact(self) -> ProposalArtifact | None:
        """The hash-bound artifact this run produced, when it produced one."""
        return None if self.proposal is None else self.proposal.artifact

    @property
    def recommendation(self) -> AdvisoryRecommendation | None:
        """DEC-004's advisory recommendation, or `None` when policy permits none.

        `None` here is the absence of a *record shape*, not a null field on one: section 11.2's
        structural absence is preserved by :class:`UnrecommendedProposal` having no
        `recommendation` member at all.
        """
        if isinstance(self.proposal, RecommendedProposal):
            return self.proposal.recommendation
        return None


@dataclass(frozen=True)
class _Bound:
    """Everything resolved before candidate evaluation, threaded through the later steps.

    Bundled rather than passed field by field so the flow below reads as section 5's sequence
    instead of as parameter plumbing. It is immutable: no step may rewrite what an earlier step
    observed, which is what makes the pre-publication drift comparison meaningful.
    """

    config: EngineConfig
    config_path: Path
    identity: RepositoryIdentity
    predecessor: PredecessorEvidence
    initial: EvidenceSnapshot
    manifest: tuple[EvidenceReference, ...]
    metadata: GenerationMetadata
    output: OutputMode
    dry_run: bool


def _generation_metadata() -> GenerationMetadata:
    """Section 16.3's unhashed envelope: UTC wall clock, and this package's own version.

    This is the only place a timestamp enters an invocation at all, and
    `canonical_payload_bytes` excludes the whole envelope, so no hash and no identity can ever
    depend on when the tool ran.
    """
    return GenerationMetadata(
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tool_version=__version__,
    )


def _snapshot_inputs(config: EngineConfig) -> list[str]:
    """Every section 8 authoritative source, as repository-relative snapshot inputs.

    The handover manifest and its files are deliberately absent: :func:`take_snapshot` adds them
    unconditionally, because section 8 item 10 makes handover evidence required rather than
    optional. The active configuration is bound through `RepositoryIdentity.config_hash` and Git
    evidence through the rest of that record, so neither appears here either.
    """
    return [
        config.governance.task_queue,
        config.governance.current_task,
        config.governance.remaining_tasks,
        config.governance.project_state,
        *config.governance.registries,
        DECISION_LOG_PATH,
        OPEN_QUESTIONS_PATH,
        COMPLETION_REPORTS_PATH,
        CATALOG_PATH,
    ]


def _error(code: FailureCode, subject: str, message: object) -> ProposalError:
    return ProposalError(
        code=code,
        path_or_candidate_id=_scalar(subject, "error subject", MAX_PATH_CHARS),
        message=safe_message(message),
    )


def _bare_failure(
    code: FailureCode,
    subject: str,
    message: object,
    *,
    output: OutputMode,
    dry_run: bool,
    predecessor_stage_id: str | None = None,
) -> ProposalRun:
    """A failure reached before any artifact could be bound to a resolved predecessor."""
    return ProposalRun(
        outcome_class="FAILURE",
        predecessor_stage_id=predecessor_stage_id,
        output=output,
        dry_run=dry_run,
        proposal=None,
        publication=None,
        failure_code=code,
        errors=[_error(code, subject, message)],
    )


# --------------------------------------------------------------------------------------
# Section 7.1a / DEC-010 -- the primary remote identity behind the artifact root
# --------------------------------------------------------------------------------------

_GIT_CONFIG_RELATIVE = ".git/config"
_REMOTE_SECTION_RE = re.compile(r'^\[remote\s+"(?P<name>[^"\]]+)"\]$')
_ANY_SECTION_RE = re.compile(r"^\[")
_REMOTE_URL_RE = re.compile(r"^url\s*=\s*(?P<url>\S.*)$")


def _declared_remotes(text: str) -> dict[str, str]:
    """Return every `remote.<name>.url` the Git configuration text declares.

    A deliberately small, explicit parser rather than `configparser`: Git indents its entries
    with a tab, which `configparser` reads as a continuation of the preceding value, so the
    stdlib reader would silently mis-associate exactly the field this function exists to read.
    Git's own last-value-wins rule for a single-valued key is preserved.
    """
    remotes: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if _ANY_SECTION_RE.match(stripped):
            section = _REMOTE_SECTION_RE.match(stripped)
            current = section.group("name") if section is not None else None
            continue
        if current is None:
            continue
        entry = _REMOTE_URL_RE.match(stripped)
        if entry is not None:
            remotes[current] = entry.group("url").strip()
    return remotes


def _primary_remote_url(identity: RepositoryIdentity) -> str:
    """Resolve the one primary remote URL DEC-010 derives the repository ID from.

    Section 7.1a requires the configured identity, the Git worktree, the primary remote and the
    upstream identity to reconcile *unambiguously* or the invocation to fail closed, so the
    upstream this invocation actually observed selects the remote whenever one exists; `origin`
    is used only when there is no upstream, and a lone remote only when there is no `origin`.
    Nothing is guessed: zero remotes, or several with no upstream and no `origin`, is a refusal.

    The URL is read from the repository's own Git configuration file as ordinary bytes, through
    the same bounded, no-follow read discipline every other file read in this package uses. It
    is not a Git *command*: `GitClient.READ_ONLY_FORMS` admits neither `git remote` nor
    `git config`, and widening that allowlist would open exactly the new, independently-audited
    Git access path section 7.1 forbids. The file is not a section 8 authoritative source and
    therefore never enters the evidence manifest or the proposal hash -- it identifies where the
    artifact is published, nothing more.
    """
    path = Path(identity.resolved_repository_root) / _GIT_CONFIG_RELATIVE
    label = f"The Git configuration {_GIT_CONFIG_RELATIVE!r}"
    try:
        data, _ = read_evidence_bytes(path, label)
        text = normalize_evidence_text(data, label)
    except SnapshotError as exc:
        raise RepositoryIdentityMismatchError(
            f"{label} could not be read, so the primary remote identity DEC-010 derives the "
            f"artifact root from cannot be established: {safe_message(exc)}"
        ) from exc

    remotes = _declared_remotes(text)
    upstream = identity.upstream_ref
    if upstream is not None and "/" in upstream:
        name = upstream.split("/", 1)[0]
        if name not in remotes:
            raise RepositoryIdentityMismatchError(
                f"The upstream {upstream!r} names the remote {name!r}, which declares no URL in "
                f"{_GIT_CONFIG_RELATIVE!r}"
            )
        return remotes[name]
    if "origin" in remotes:
        return remotes["origin"]
    if len(remotes) == 1:
        return next(iter(remotes.values()))
    raise RepositoryIdentityMismatchError(
        f"{_GIT_CONFIG_RELATIVE!r} declares {len(remotes)} remote URLs and this invocation has "
        "no upstream and no 'origin', so the primary remote identity is ambiguous"
    )


def repository_id_for(identity: RepositoryIdentity) -> str:
    """The DEC-010 canonical repository ID this invocation publishes under."""
    return canonical_repository_id(_primary_remote_url(identity))


# --------------------------------------------------------------------------------------
# Section 5 -- the composed flow
# --------------------------------------------------------------------------------------


def _empty_report() -> EligibilityReport:
    """The report a refusal renders against: no candidate was evaluated at all (section 11.3)."""
    return EligibilityReport(
        verdicts=[],
        eligible_candidate_ids=[],
        blockers=[],
        result_variant="INSUFFICIENT_EVIDENCE",
    )


def _render(
    bound: _Bound, candidates: Sequence[Candidate], report: EligibilityReport
) -> RenderedPrompt:
    return render_prompt(
        identity=bound.identity,
        predecessor=bound.predecessor,
        evidence_manifest=list(bound.manifest),
        candidates=candidates,
        report=report,
    )


def _run_record(
    bound: _Bound,
    proposal: RecommendedProposal | UnrecommendedProposal,
    *,
    failure_code: FailureCode | None,
    errors: Sequence[ProposalError],
    publication: PublicationRecord | None,
) -> ProposalRun:
    return ProposalRun(
        outcome_class="FAILURE" if failure_code is not None else "PROPOSAL_READY",
        predecessor_stage_id=bound.predecessor.stage_id,
        output=bound.output,
        dry_run=bound.dry_run,
        proposal=proposal,
        publication=publication,
        failure_code=failure_code,
        errors=_ordered_errors(errors),
    )


def _refuse(
    bound: _Bound,
    code: FailureCode,
    errors: Sequence[ProposalError],
    *,
    recheck: bool = True,
) -> ProposalRun:
    """Build section 11.3's labelled, hash-bound refusal record and finish the invocation.

    A refusal carries no candidate list, no eligibility decision and no recommendation -- that
    is `build_refusal`'s own construction, not this function's discipline -- and its prompt is
    rendered against an empty evaluation so the artifact is still a complete, validated,
    hash-bound document rather than a stub.
    """
    try:
        prompt = _render(bound, (), _empty_report())
    except (PromptValidationError, PromptSecurityError, PromptSecretError) as exc:
        # The refusal itself cannot be rendered, so there is no artifact to publish. The
        # original code is kept as the reported failure and the rendering failure is recorded
        # beside it, because losing either one would misdescribe what happened.
        return ProposalRun(
            outcome_class="FAILURE",
            predecessor_stage_id=bound.predecessor.stage_id,
            output=bound.output,
            dry_run=bound.dry_run,
            proposal=None,
            publication=None,
            failure_code=code,
            errors=_ordered_errors(
                [*errors, _error(exc.code, INVOCATION_SUBJECT, f"the refusal record: {exc}")]
            ),
        )
    record = build_refusal(
        identity=bound.identity,
        predecessor=bound.predecessor,
        evidence_manifest=list(bound.manifest),
        failure_code=code,
        errors=errors,
        generated_prompt=prompt.markdown,
        generation_metadata=bound.metadata,
        warnings=prompt.warnings,
    )
    return _finish(bound, record, failure_code=code, errors=errors, recheck=recheck)


def _finish(
    bound: _Bound,
    record: RecommendedProposal | UnrecommendedProposal,
    *,
    failure_code: FailureCode | None,
    errors: Sequence[ProposalError],
    recheck: bool = True,
) -> ProposalRun:
    """Section 7.3 steps 11-13, then section 17.2's publication.

    The re-snapshot runs on the dry-run path too: it is a read, and section 23.2 makes
    `--dry-run` perform complete inspection and validation while publishing nothing. `recheck`
    is `False` only when this call *is* the drift refusal, which would otherwise re-detect the
    same drift forever.
    """
    if recheck:
        try:
            compare_snapshots(
                bound.initial,
                take_snapshot(
                    bound.config, bound.config_path, inputs=_snapshot_inputs(bound.config)
                ),
            )
        except SnapshotError as exc:
            return _refuse(
                bound,
                exc.code,
                [_error(exc.code, INVOCATION_SUBJECT, exc)],
                recheck=False,
            )

    if bound.dry_run:
        return _run_record(
            bound, record, failure_code=failure_code, errors=errors, publication=None
        )

    # Imported here rather than at module scope: `store` imports this module's
    # `serialize_artifact`, so a module-level import in this direction would be circular. The
    # dependency is genuinely one-directional at every other level -- assembly knows nothing
    # about publication -- and only this flow-composing operation needs both.
    from ai_workflow_engine.successor_planning.store import PublicationError, publish

    try:
        published = publish(record.artifact, repository_id_for(bound.identity))
    except (PublicationError, SnapshotError) as exc:
        return _run_record(
            bound,
            record,
            failure_code=exc.code,
            errors=[*errors, _error(exc.code, INVOCATION_SUBJECT, exc)],
            publication=None,
        )
    return _run_record(
        bound,
        record,
        failure_code=failure_code,
        errors=errors,
        publication=PublicationRecord(
            artifact_path=str(published.path),
            proposal_id=published.proposal_id,
            created=published.created,
        ),
    )


def _evaluate(bound: _Bound, evidence: EvidenceSet) -> ProposalRun:
    """Sections 9-12 and 14-17: candidates, verdicts, prompt, artifact, publication."""
    root = Path(bound.identity.resolved_repository_root)
    try:
        catalog = read_catalog(root, CATALOG_PATH)
    except (CatalogError, SnapshotError) as exc:
        return _refuse(bound, exc.code, [_error(exc.code, CATALOG_PATH, exc)])

    dependencies = resolve_dependency_graph(
        catalog.candidates, known_stages=evidence.known_stage_ids()
    )
    findings: list[CandidateFinding] = [
        *catalog.findings,
        *dependencies.findings,
        *stale_completion_findings(check_completion_claims(evidence, catalog.candidates)),
    ]
    report = evaluate_all(
        catalog.candidates,
        open_questions=evidence.open_questions,
        findings=findings,
        unmet_dependencies=dependencies.unmet,
    )

    try:
        prompt = _render(bound, catalog.candidates, report)
    except (PromptValidationError, PromptSecurityError, PromptSecretError) as exc:
        return _refuse(bound, exc.code, [_error(exc.code, CATALOG_PATH, exc)])

    try:
        record = build_proposal(
            identity=bound.identity,
            predecessor=bound.predecessor,
            evidence_manifest=list(bound.manifest),
            candidates=catalog.candidates,
            report=report,
            generated_prompt=prompt.markdown,
            generation_metadata=bound.metadata,
            findings=findings,
            warnings=[*prompt.warnings, *_warnings_from_redactions(catalog.redactions)],
        )
    except (ProposalAssemblyError, ValidationError) as exc:
        return _refuse(
            bound,
            "INVALID_INVOCATION",
            [_error("INVALID_INVOCATION", INVOCATION_SUBJECT, exc)],
        )

    # Section 15: the prompt is re-derived and re-checked against the assembled artifact before
    # anything may be persisted, so a prompt that drifted from its hash between rendering and
    # assembly refuses publication rather than reaching the artifact root.
    try:
        validate_prompt_structure(
            record.artifact.generated_prompt, expected_hash=record.artifact.prompt_hash
        )
    except PromptValidationError as exc:
        return _refuse(bound, exc.code, [_error(exc.code, CATALOG_PATH, exc)])

    return _finish(bound, record, failure_code=None, errors=())


def propose_successor(
    config_path: Path,
    *,
    predecessor: str | None,
    output: OutputMode = "console",
    dry_run: bool = False,
) -> ProposalRun:
    """Run section 5's flow once and return its typed result (sections 4, 5, 23.2).

    This is the whole `workflowctl successor-planning propose` operation, in section 5's order:
    resolve the repository identity and Git baseline and take the initial evidence snapshot;
    read every section 8 authoritative source; validate the required predecessor; reconcile the
    task queue against its mirrors and registries; load and validate the static authoritative
    catalog; evaluate candidates, dependencies and live blockers; apply DEC-004/DEC-005's
    recommendation policy; render and structurally validate the governed prompt; assemble the
    hash-bound artifact; re-snapshot and compare; and publish once, atomically, unless
    `dry_run`.

    It authorizes nothing, registers nothing, invokes no provider, and mutates no Git, task,
    Registry, workflow or governance state. Its one and only side effect is the artifact write,
    into an external repository-scoped root outside this repository entirely (section 17.2), and
    `dry_run` removes even that while still performing every inspection and validation.

    Nothing here raises for a contract failure. Every section 13 outcome is returned as a typed
    :class:`ProposalRun` -- as section 11.3's hash-bound refusal record once a predecessor has
    resolved, and as a bare failure before that, since section 16.1 makes the predecessor fields
    mandatory and an artifact with nothing to bind to is not representable.
    """
    metadata = _generation_metadata()

    try:
        config = load_config(config_path)
    except WorkflowEngineError as exc:
        return _bare_failure(
            "INVALID_INVOCATION", str(config_path), exc, output=output, dry_run=dry_run
        )

    # Section 4 item 6: the unauthorized-successor-implementation preflight runs before the
    # evidence-snapshot pass begins, so a repository already carrying unrecognized successor
    # state never reaches candidate evaluation. It resolves the configured root through the same
    # rules section 7.2 applies, so a root failure here reports the code it would report there.
    try:
        check_no_unauthorized_successor(config, _resolve_configured_root(config))
    except UnauthorizedSuccessorError as exc:
        return _bare_failure(exc.code, INVOCATION_SUBJECT, exc, output=output, dry_run=dry_run)
    except SnapshotError as exc:
        return _bare_failure(exc.code, str(config_path), exc, output=output, dry_run=dry_run)

    try:
        initial = take_snapshot(config, config_path, inputs=_snapshot_inputs(config))
        identity = initial.identity
        evidence = read_evidence_set(config, identity, EVIDENCE_SOURCES)
    except SnapshotError as exc:
        return _bare_failure(exc.code, str(config_path), exc, output=output, dry_run=dry_run)

    try:
        resolved = resolve_predecessor(evidence, predecessor, identity=identity)
    except PredecessorError as exc:
        return _bare_failure(exc.code, INVOCATION_SUBJECT, exc, output=output, dry_run=dry_run)

    try:
        manifest = merge_evidence_manifest(initial.evidence_manifest(), evidence.manifest)
    except ProposalAssemblyError as exc:
        return _bare_failure(
            exc.code,
            INVOCATION_SUBJECT,
            exc,
            output=output,
            dry_run=dry_run,
            predecessor_stage_id=resolved.stage_id,
        )

    bound = _Bound(
        config=config,
        config_path=config_path,
        identity=identity,
        predecessor=resolved,
        initial=initial,
        manifest=tuple(manifest),
        metadata=metadata,
        output=output,
        dry_run=dry_run,
    )

    # Section 4 item 4: `task-state`, `governance`, `registries` and `handover` must all pass
    # unconditionally. The `git` check ran during identity resolution, where section 7.2 rule 4's
    # one documented `upstream_missing` tolerance applies to it; these four have no tolerance.
    governance_failures = run_required_governance_checks(config)
    if governance_failures:
        return _refuse(
            bound,
            governance_failures[0].failure_code,
            [
                _error(failure.failure_code, failure.path, failure.message)
                for failure in governance_failures
            ],
        )

    reconciliation = reconcile_mirrors(evidence)
    if reconciliation.failure_code is not None:
        return _refuse(
            bound,
            reconciliation.failure_code,
            [
                _error(reconciliation.failure_code, disagreement.path, disagreement.message)
                for disagreement in [
                    *reconciliation.mirror_disagreements,
                    *reconciliation.registry_disagreements,
                ]
            ],
        )
    if reconciliation.current_tasks:
        return _refuse(
            bound,
            "CONFLICTING_CURRENT_TASK",
            [
                _error(
                    "CONFLICTING_CURRENT_TASK",
                    reconciliation.task_queue_path,
                    f"{', '.join(reconciliation.current_tasks)} is Current at invocation time; "
                    "this tool never runs during another stage's active work",
                )
            ],
        )

    return _evaluate(bound, evidence)
