"""Mechanical structural validation tests: headings, fragments, spans, consistency."""

import pytest

from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.renderer import render_prompt
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
