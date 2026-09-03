"""Mechanical structural validation tests: headings, fragments, spans, consistency."""

import hashlib
import sys

import pytest

from ai_workflow_engine.models import (
    EngineConfig,
    VerificationBundleSettings,
    VerificationSettings,
)
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.renderer import (
    canonical_json,
    canonical_payload_bytes,
    compute_prompt_id,
    render_markdown,
    render_prompt,
)
from ai_workflow_engine.prompt.templates import get_template
from ai_workflow_engine.prompt.validator import validate_prompt
from ai_workflow_engine.result import Status

STAGE_KWARGS = {
    "plan-review": {},
    "implementation": {"allowed_paths": ["src/a.py"]},
    "implementation-review": {},
    "remediation": {"allowed_paths": ["src/a.py"], "remediation_findings": ["Fix the bug"]},
    "governance-closeout": {},
    "governance-review": {},
    "push": {},
}

REVIEW_STAGES = {"plan-review", "implementation-review", "governance-review"}


@pytest.mark.parametrize("stage", sorted(STAGE_KWARGS))
def test_validate_prompt_passes_for_a_correctly_rendered_prompt(
    engine_config: EngineConfig, stage: str
) -> None:
    context = build_prompt_context(engine_config, stage=stage, task_id="T-1", **STAGE_KWARGS[stage])
    rendered = render_prompt(context)
    result = validate_prompt(rendered)
    assert result.status == Status.PASS
    assert result.findings == []
    assert result.check_name == "prompt"


def _rendered(engine_config: EngineConfig, stage: str = "plan-review"):
    context = build_prompt_context(engine_config, stage=stage, task_id="T-1", **STAGE_KWARGS[stage])
    return render_prompt(context)


def _with_replaced_check(rendered, check_name: str, **updates):
    checks = rendered.context.checks
    index = next(i for i, check in enumerate(checks) if check.check_name == check_name)
    replaced = checks[index].model_copy(update=updates)
    mutated_context = rendered.context.model_copy(
        update={"checks": [*checks[:index], replaced, *checks[index + 1 :]]}
    )
    return rendered.model_copy(update={"context": mutated_context})


def test_validate_prompt_detects_git_evidence_field_set_mismatch(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    git_check = next(c for c in rendered.context.checks if c.check_name == "git")
    mutated = _with_replaced_check(
        rendered, "git", evidence={**git_check.evidence, "extra_key": True}
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "git_evidence_field_set" in codes


def test_validate_prompt_git_evidence_check_allows_the_exception_fallback_shape(
    engine_config: EngineConfig,
) -> None:
    # `evidence == {}` is the universal `_safe_check` exception shape, not a violation
    # of the eight-field Git evidence schema, so this specific finding must not appear
    # even though the tampered check now disagrees with the already-rendered Markdown.
    rendered = _rendered(engine_config)
    mutated = _with_replaced_check(rendered, "git", status="ERROR", evidence={})
    result = validate_prompt(mutated)
    codes = {finding.code for finding in result.findings}
    assert "git_evidence_field_set" not in codes


def test_validate_prompt_detects_git_evidence_missing_key(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    git_check = next(c for c in rendered.context.checks if c.check_name == "git")
    evidence = dict(git_check.evidence)
    del evidence["ahead"]
    mutated = _with_replaced_check(rendered, "git", evidence=evidence)
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "git_evidence_field_set" in codes


def test_validate_prompt_detects_heading_text_mutation(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    mutated = rendered.model_copy(
        update={"markdown": rendered.markdown.replace("## Role\n", "## Rolez\n")}
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "heading_sequence_mismatch" in codes


def test_validate_prompt_detects_role_fragment_mutation(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    mutated = rendered.model_copy(
        update={
            "markdown": rendered.markdown.replace(
                "Act as the read-only planning reviewer for the requested task.",
                "Act as a read-only planning reviewer for the requested task.",
            )
        }
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "fragment_mismatch" in codes
    assert "markdown_mismatch" in codes


def test_validate_prompt_detects_verification_command_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    mutated = rendered.model_copy(
        update={"markdown": rendered.markdown.replace("git diff --check", "git diff --checked")}
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "fragment_mismatch" in codes


def test_validate_prompt_detects_verdict_instruction_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "plan-review")
    mutated = rendered.model_copy(
        update={
            "markdown": rendered.markdown.replace(
                "Return exactly one final verdict token: APPROVED or REJECTED.",
                "Return exactly one final verdict token: APPROVED, REJECTED, or MAYBE.",
            )
        }
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "verdict_instruction_mismatch" in codes


def test_validate_prompt_detects_no_verdict_instruction_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "implementation")
    mutated = rendered.model_copy(
        update={
            "markdown": rendered.markdown.replace(
                "No APPROVED or REJECTED verdict is requested for this stage.",
                "No verdict at all is requested for this stage.",
            )
        }
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "verdict_instruction_mismatch" in codes


def test_validate_prompt_detects_allowed_paths_list_span_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "implementation")
    mutated = rendered.model_copy(
        update={"markdown": rendered.markdown.replace('- "src/a.py"', '- "src/b.py"')}
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "rendered_span_mismatch" in codes


def test_validate_prompt_detects_stage_mismatch_between_context_and_template(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "plan-review")
    wrong_template = get_template("implementation")
    mutated_context = rendered.context.model_copy(update={"template": wrong_template})
    mutated = rendered.model_copy(update={"context": mutated_context})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "template_content_mismatch" in codes


def test_validate_prompt_detects_allowed_paths_cardinality_violation(
    engine_config: EngineConfig,
) -> None:
    implementation_rendered = _rendered(engine_config, "implementation")
    plan_review_template = get_template("plan-review")
    swapped_context = implementation_rendered.context.model_copy(
        update={"stage": "plan-review", "template": plan_review_template}
    )
    swapped = render_prompt(swapped_context)
    result = validate_prompt(swapped)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "allowed_paths_cardinality" in codes


def test_validate_prompt_detects_remediation_findings_cardinality_violation(
    engine_config: EngineConfig,
) -> None:
    remediation_rendered = _rendered(engine_config, "remediation")
    implementation_template = get_template("implementation")
    swapped_context = remediation_rendered.context.model_copy(
        update={"stage": "implementation", "template": implementation_template}
    )
    swapped = render_prompt(swapped_context)
    result = validate_prompt(swapped)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "remediation_findings_cardinality" in codes


def test_validate_prompt_detects_metadata_payload_tamper(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    other_rendered = _rendered(engine_config, "implementation")
    tampered_metadata = rendered.metadata.model_copy(update={"payload": other_rendered.context})
    mutated = rendered.model_copy(update={"metadata": tampered_metadata})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "metadata_payload_mismatch" in codes


def test_validate_prompt_detects_metadata_bytes_tamper(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    mutated = rendered.model_copy(update={"metadata_bytes": rendered.metadata_bytes + b" "})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "metadata_bytes_mismatch" in codes


def test_validate_prompt_detects_prompt_id_tamper(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    tampered = "f" * 16
    mutated = rendered.model_copy(update={"prompt_id": tampered})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "prompt_id_mismatch" in codes or "metadata_prompt_id_mismatch" in codes


# --- One-byte-class mutations across every remaining literal and dynamic section -----
#
# Inserting one extra, non-heading line immediately after a heading corrupts exactly the
# content span between that heading and the next one, without disturbing the heading
# sequence itself (the inserted line is not itself an ATX heading). This is a uniform way
# to exercise every remaining `_FRAGMENT_SPAN_HEADINGS`/`_LIST_SPAN_HEADINGS` entry that
# the existing role/verification/verdict/allowed-path tests above do not already cover.

_SPAN_MUTATIONS: list[tuple[str, str, str]] = [
    ("scope_fragment", "## Scope and allowed operations", "fragment_mismatch"),
    ("prohibited_fragment", "## Prohibited operations", "fragment_mismatch"),
    ("stop_fragment", "## Stop condition", "fragment_mismatch"),
    ("git_status_json_block", "### Git status", "rendered_span_mismatch"),
    ("task_snapshot_json_block", "### Task snapshot", "rendered_span_mismatch"),
    ("protected_path_violations_list", "### Protected-path violations", "rendered_span_mismatch"),
    ("checks_json_block", "### Validation checks", "rendered_span_mismatch"),
    ("remediation_findings_list", "## Remediation findings", "rendered_span_mismatch"),
    ("verification_evidence_json_block", "## Verification evidence", "rendered_span_mismatch"),
]


@pytest.mark.parametrize(
    ("label", "heading", "expected_code"),
    _SPAN_MUTATIONS,
    ids=[label for label, _, _ in _SPAN_MUTATIONS],
)
def test_validate_prompt_detects_span_mutation(
    engine_config: EngineConfig, label: str, heading: str, expected_code: str
) -> None:
    rendered = _rendered(engine_config)
    lines = rendered.markdown.split("\n")
    index = lines.index(heading)
    lines.insert(index + 1, "MUTATED-INJECTED-LINE")
    mutated = rendered.model_copy(update={"markdown": "\n".join(lines)})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert expected_code in codes, f"expected {expected_code!r} in {codes!r} for {label}"


def test_validate_prompt_detects_template_version_registry_mismatch(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    mutated_template = rendered.context.template.model_copy(update={"version": "9.9.9"})
    mutated_context = rendered.context.model_copy(update={"template": mutated_template})
    mutated = rendered.model_copy(update={"context": mutated_context})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "template_version_mismatch" in codes
    assert "template_content_mismatch" not in codes


def test_validate_prompt_detects_template_sha256_registry_mismatch(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    mutated_template = rendered.context.template.model_copy(update={"sha256": "0" * 64})
    mutated_context = rendered.context.model_copy(update={"template": mutated_template})
    mutated = rendered.model_copy(update={"context": mutated_context})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "template_sha256_mismatch" in codes
    assert "template_content_mismatch" not in codes


# --- Push-specific fragment mutations (branch/HEAD/count wording, commit-chain check,
# single push command; the other six stages share no content with these) -------------


def test_validate_prompt_detects_push_scope_authorized_branch_wording_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "push")
    mutated = rendered.model_copy(
        update={
            "markdown": rendered.markdown.replace(
                "The only permitted state-changing operation is one `git push` "
                "after every verification below passes.",
                "The only permitted state-changing operation is a `git push` "
                "after every verification below passes.",
            )
        }
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "fragment_mismatch" in codes


def test_validate_prompt_detects_push_commit_chain_command_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "push")
    mutated = rendered.model_copy(
        update={
            "markdown": rendered.markdown.replace(
                "git rev-list --left-right --count", "git rev-list --left-right --counts"
            )
        }
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "fragment_mismatch" in codes


def test_validate_prompt_detects_push_single_push_command_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "push")
    assert " git push\n" in rendered.markdown
    mutated = rendered.model_copy(
        update={"markdown": rendered.markdown.replace(" git push\n", " git push --force\n")}
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "fragment_mismatch" in codes


def test_validate_prompt_detects_push_stop_condition_mutation(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config, "push")
    mutated = rendered.model_copy(
        update={
            "markdown": rendered.markdown.replace(
                "Stop without pushing on any mismatch",
                "Stop without pushing only on some mismatch",
            )
        }
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "fragment_mismatch" in codes


# --- AC12: mechanically malformed verification evidence -----------------------


def test_validate_prompt_detects_verification_evidence_section_absent(
    engine_config: EngineConfig,
) -> None:
    """An entirely missing `## Verification evidence` heading is caught by the same heading-
    sequence check every other required heading already relies on."""
    rendered = _rendered(engine_config)
    mutated = rendered.model_copy(
        update={"markdown": rendered.markdown.replace("## Verification evidence\n", "", 1)}
    )
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "heading_sequence_mismatch" in codes


def test_validate_prompt_detects_verification_evidence_non_json_block(
    engine_config: EngineConfig,
) -> None:
    """The fenced block's content must be exactly the re-derived canonical JSON; replacing it
    with non-JSON text is caught the same way every other JSON span is."""
    rendered = _rendered(engine_config)
    body = rendered.markdown
    section = body.split("## Verification evidence\n", 1)[1].split("\n## Stop condition", 1)[0]
    mutated_markdown = body.replace(
        "## Verification evidence\n" + section, "## Verification evidence\n```json\nnot json\n```"
    )
    assert mutated_markdown != body
    mutated = rendered.model_copy(update={"markdown": mutated_markdown})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "rendered_span_mismatch" in codes


def test_validate_prompt_detects_verification_evidence_not_reserializable(
    engine_config: EngineConfig,
) -> None:
    """AC12's 'not re-serializable from the payload' case: the markdown is internally
    well-formed JSON, but it no longer equals what `render_markdown` would recompute from the
    stored context -- caught by the full rerender check, independent of the span check."""
    rendered = _rendered(engine_config)
    body = rendered.markdown
    section = body.split("## Verification evidence\n", 1)[1].split("\n## Stop condition", 1)[0]
    replaced = '```json\n{"engine_provenance":null,"verification_evidence":null}\n```'
    mutated_markdown = body.replace("## Verification evidence\n" + section, replaced)
    assert mutated_markdown != body
    mutated = rendered.model_copy(update={"markdown": mutated_markdown})
    result = validate_prompt(mutated)
    assert result.status == Status.FAIL
    codes = {finding.code for finding in result.findings}
    assert "markdown_mismatch" in codes or "rendered_span_mismatch" in codes


# --- T-307 / PR-006: independent semantic validation of verification evidence --


def _bundle_rendered(engine_config: EngineConfig):
    bundle = VerificationBundleSettings(
        name="quality",
        commands=[
            [sys.executable, "-c", "raise SystemExit(0)"],
            [sys.executable, "-c", "raise SystemExit(0)"],
        ],
    )
    config = engine_config.model_copy(
        update={"verification": VerificationSettings(bundles=[bundle])}
    )
    context = build_prompt_context(
        config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
    )
    return render_prompt(context)


def _re_rendered_from_tampered_context(
    base_rendered,
    tampered_context,
    *,
    sync_metadata_evidence: bool = True,
    sync_metadata_provenance: bool = True,
):
    """Fully regenerate every derived field from a tampered context, exactly as `render_prompt`
    would. This is the adversarial case PR-006 targets: the tampered payload renders and
    re-renders consistently (every existing mechanical check passes), so only an independent
    semantic check on the evidence's own content can catch it.
    """
    payload_bytes = canonical_payload_bytes(tampered_context)
    payload_sha256, prompt_id = compute_prompt_id(payload_bytes)
    markdown = render_markdown(tampered_context.template.content, tampered_context, prompt_id)
    markdown_sha256 = hashlib.sha256(markdown.encode("utf-8", errors="strict")).hexdigest()

    metadata_updates: dict[str, object] = {
        "prompt_id": prompt_id,
        "payload_sha256": payload_sha256,
        "markdown_sha256": markdown_sha256,
        "payload": tampered_context,
    }
    if sync_metadata_evidence:
        metadata_updates["verification_evidence"] = tampered_context.verification_evidence
    if sync_metadata_provenance:
        metadata_updates["engine_provenance"] = tampered_context.engine_provenance
    metadata = base_rendered.metadata.model_copy(update=metadata_updates)

    return base_rendered.model_copy(
        update={
            "context": tampered_context,
            "canonical_payload_bytes": payload_bytes,
            "prompt_id": prompt_id,
            "markdown": markdown,
            "metadata": metadata,
            "metadata_bytes": canonical_json(metadata.model_dump(mode="json")) + b"\n",
        }
    )


def _codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_semantic_check_index_gap(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    observations = evidence.observations
    gapped = observations[1].model_copy(update={"index": 2})
    tampered_evidence = evidence.model_copy(update={"observations": [observations[0], gapped]})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_index_gap" in _codes(result)


def test_semantic_check_index_order(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    reordered = list(reversed(evidence.observations))
    tampered_evidence = evidence.model_copy(update={"observations": reordered})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_index_order" in _codes(result)


def test_semantic_check_index_duplicate(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    duplicated = [evidence.observations[0], evidence.observations[0]]
    tampered_evidence = evidence.model_copy(update={"observations": duplicated})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_index_duplicate" in _codes(result)


def test_semantic_check_unselected_bundle(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    ghost = evidence.observations[0].model_copy(update={"bundle": "ghost"})
    tampered_evidence = evidence.model_copy(
        update={"observations": [ghost, evidence.observations[1]]}
    )
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_unselected_bundle" in _codes(result)


def test_semantic_check_duplicate_selected_bundle(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    tampered_evidence = evidence.model_copy(update={"bundles": ["quality", "quality"]})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_duplicate_bundle" in _codes(result)


def test_semantic_check_empty_observations(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    tampered_evidence = evidence.model_copy(update={"observations": []})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_empty_observations" in _codes(result)


def test_semantic_check_target_head_mismatch(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    tampered_evidence = evidence.model_copy(update={"target_head": "0" * 40})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_target_head_mismatch" in _codes(result)


def test_semantic_check_metadata_evidence_mismatch(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    tampered_evidence = evidence.model_copy(update={"target_head": "0" * 40})
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(
        _re_rendered_from_tampered_context(rendered, tampered_context, sync_metadata_evidence=False)
    )
    assert result.status == Status.FAIL
    assert "metadata_verification_evidence_mismatch" in _codes(result)


def test_semantic_check_metadata_provenance_mismatch(engine_config: EngineConfig) -> None:
    rendered = _bundle_rendered(engine_config)
    provenance = rendered.context.engine_provenance
    tampered_provenance = provenance.model_copy(update={"engine_head": "f" * 40})
    tampered_context = rendered.context.model_copy(
        update={"engine_provenance": tampered_provenance}
    )
    result = validate_prompt(
        _re_rendered_from_tampered_context(
            rendered, tampered_context, sync_metadata_provenance=False
        )
    )
    assert result.status == Status.FAIL
    assert "metadata_engine_provenance_mismatch" in _codes(result)


def test_semantic_check_never_raises_on_a_malformed_index_type(
    engine_config: EngineConfig,
) -> None:
    """The defensive `_check_verification_evidence` wrapper converts even a type defect that
    would otherwise raise (a non-int index, bypassed past the observation model's own strict
    typing via `model_copy`) into a Finding, never an exception."""
    rendered = _bundle_rendered(engine_config)
    evidence = rendered.context.verification_evidence
    assert evidence is not None
    malformed = evidence.observations[0].model_copy(update={"index": "not-an-int"})
    tampered_evidence = evidence.model_copy(
        update={"observations": [malformed, evidence.observations[1]]}
    )
    tampered_context = rendered.context.model_copy(
        update={"verification_evidence": tampered_evidence}
    )
    result = validate_prompt(_re_rendered_from_tampered_context(rendered, tampered_context))
    assert result.status == Status.FAIL
    assert "verification_evidence_unreadable" in _codes(result)


def test_no_verification_evidence_findings_when_none_selected(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    result = validate_prompt(rendered)
    assert result.status == Status.PASS
    assert not any(finding.code.startswith("verification_evidence_") for finding in result.findings)
