"""Mechanical, exact-byte structural validation of a rendered governed prompt.

No fuzzy keyword or prose search is performed. Every result is defined by a template
marker, a model invariant, or exact rendered bytes, per the Milestone 2 plan's
"Validation and CLI output" section.
"""

import hashlib

from ai_workflow_engine.prompt.models import CanonicalGitStatus, PromptContext, RenderedPrompt
from ai_workflow_engine.prompt.renderer import (
    ALLOWED_PLACEHOLDER_NAMES,
    apply_mapping,
    build_placeholder_mapping,
    canonical_json,
    canonical_payload_bytes,
    compute_prompt_id,
    render_markdown,
    tokenize_template,
)
from ai_workflow_engine.prompt.templates import MARKER_ORDER, get_fragments, get_template
from ai_workflow_engine.result import CheckResult, Finding, Status

CHECK_NAME = "prompt"

_GIT_EVIDENCE_FIELDS = frozenset(CanonicalGitStatus.model_fields)

REQUIRED_HEADINGS: tuple[str, ...] = (
    "# Governed Workflow Prompt",
    "## Identity",
    "## Role",
    "## Scope and allowed operations",
    "## Allowed paths",
    "## Prohibited operations",
    "## Repository inspection evidence",
    "### Git status",
    "### Task snapshot",
    "### Protected-path violations",
    "### Validation checks",
    "## Remediation findings",
    "## Verification commands",
    "## Stop condition",
    "## Verdict instruction",
)

_REVIEW_STAGES = frozenset({"plan-review", "implementation-review", "governance-review"})
_ALLOWED_PATH_STAGES = frozenset({"implementation", "remediation"})
_FINDING_STAGES = frozenset({"remediation"})

_FRAGMENT_SPAN_HEADINGS: dict[str, tuple[str, str | None]] = {
    "ROLE": ("## Role", "## Scope and allowed operations"),
    "SCOPE": ("## Scope and allowed operations", "## Allowed paths"),
    "PROHIBITED": ("## Prohibited operations", "## Repository inspection evidence"),
    "VERIFICATION": ("## Verification commands", "## Stop condition"),
    "STOP": ("## Stop condition", "## Verdict instruction"),
    "VERDICT": ("## Verdict instruction", None),
}

_LIST_SPAN_HEADINGS: dict[str, tuple[str, str]] = {
    "ALLOWED_PATHS_LIST": ("## Allowed paths", "## Prohibited operations"),
    "GIT_STATUS_JSON": ("### Git status", "### Task snapshot"),
    "TASK_SNAPSHOT_JSON": ("### Task snapshot", "### Protected-path violations"),
    "PROTECTED_PATH_VIOLATIONS_LIST": ("### Protected-path violations", "### Validation checks"),
    "CHECKS_JSON": ("### Validation checks", "## Remediation findings"),
    "REMEDIATION_FINDINGS_LIST": ("## Remediation findings", "## Verification commands"),
}


def _is_atx_heading(line: str) -> bool:
    hashes = len(line) - len(line.lstrip("#"))
    return 1 <= hashes <= 6 and len(line) > hashes and line[hashes] == " "


def _content_between(lines: list[str], start_index: int, end_index: int) -> str:
    segment = lines[start_index + 1 : end_index]
    if segment and segment[-1] == "":
        segment = segment[:-1]
    return "\n".join(segment)


def _check_tokenization(context: PromptContext) -> list[Finding]:
    findings: list[Finding] = []
    try:
        tokens = tokenize_template(context.template.content)
    except Exception as exc:
        return [Finding(code="template_malformed_delimiter", message=str(exc))]
    for kind, value in tokens:
        if kind != "placeholder":
            continue
        if value not in ALLOWED_PLACEHOLDER_NAMES:
            findings.append(
                Finding(code="unknown_placeholder", message=f"Unknown placeholder name: {value}")
            )
    return findings


def _check_rerender(rendered: RenderedPrompt) -> list[Finding]:
    context = rendered.context
    try:
        recomputed = render_markdown(context.template.content, context, rendered.prompt_id)
    except Exception as exc:
        return [Finding(code="render_error", message=f"Re-render failed: {exc}")]
    findings: list[Finding] = []
    if recomputed != rendered.markdown:
        findings.append(
            Finding(
                code="markdown_mismatch",
                message="Re-rendered Markdown string differs from rendered.markdown",
            )
        )
    if recomputed.encode("utf-8", errors="strict") != rendered.markdown.encode(
        "utf-8", errors="strict"
    ):
        findings.append(
            Finding(
                code="markdown_byte_mismatch",
                message="Re-rendered Markdown UTF-8 bytes differ from rendered.markdown",
            )
        )
    return findings


def _check_git_evidence(context: PromptContext) -> list[Finding]:
    git_check = next((check for check in context.checks if check.check_name == "git"), None)
    if git_check is None:
        return [Finding(code="git_check_missing", message="No 'git' check present in checks")]
    if git_check.evidence == {}:
        # The universal `_safe_check` exception fallback; not an evidence-shape violation.
        return []
    fields = frozenset(git_check.evidence)
    if fields != _GIT_EVIDENCE_FIELDS:
        return [
            Finding(
                code="git_evidence_field_set",
                message=(
                    f"Expected Git evidence fields {sorted(_GIT_EVIDENCE_FIELDS)}, "
                    f"got {sorted(fields)}"
                ),
            )
        ]
    return []


def _check_headings(lines: list[str]) -> tuple[list[Finding], dict[str, int]]:
    headings = [line for line in lines if _is_atx_heading(line)]
    if headings != list(REQUIRED_HEADINGS):
        return (
            [
                Finding(
                    code="heading_sequence_mismatch",
                    message=(
                        f"Expected ATX heading sequence {list(REQUIRED_HEADINGS)}, got {headings}"
                    ),
                )
            ],
            {},
        )
    positions = {heading: lines.index(heading) for heading in REQUIRED_HEADINGS}
    return [], positions


def _check_list_and_json_spans(
    context: PromptContext, prompt_id: str, lines: list[str], positions: dict[str, int]
) -> list[Finding]:
    mapping = build_placeholder_mapping(context, prompt_id)
    findings: list[Finding] = []
    for name, (start_heading, end_heading) in _LIST_SPAN_HEADINGS.items():
        span = _content_between(lines, positions[start_heading], positions[end_heading])
        if span != mapping[name]:
            findings.append(
                Finding(
                    code="rendered_span_mismatch",
                    message=f"Rendered span for {name} does not equal its formatter output",
                )
            )
    return findings


def _check_cardinality(
    context: PromptContext, lines: list[str], positions: dict[str, int]
) -> list[Finding]:
    findings: list[Finding] = []
    requires_allowed_paths = context.stage in _ALLOWED_PATH_STAGES
    if requires_allowed_paths and not context.allowed_paths:
        findings.append(
            Finding(
                code="allowed_paths_cardinality",
                message=f"Stage {context.stage!r} requires at least one allowed path",
            )
        )
    if not requires_allowed_paths and context.allowed_paths:
        findings.append(
            Finding(
                code="allowed_paths_cardinality",
                message=f"Stage {context.stage!r} must not carry allowed paths",
            )
        )
    requires_findings = context.stage in _FINDING_STAGES
    if requires_findings and not context.remediation_findings:
        findings.append(
            Finding(
                code="remediation_findings_cardinality",
                message=f"Stage {context.stage!r} requires at least one remediation finding",
            )
        )
    if not requires_findings and context.remediation_findings:
        findings.append(
            Finding(
                code="remediation_findings_cardinality",
                message=f"Stage {context.stage!r} must not carry remediation findings",
            )
        )
    start, end = _LIST_SPAN_HEADINGS["ALLOWED_PATHS_LIST"]
    span = _content_between(lines, positions[start], positions[end])
    if not context.allowed_paths and span != "- (none)":
        findings.append(
            Finding(
                code="allowed_paths_list_span",
                message="Empty allowed-path list must render exactly '- (none)'",
            )
        )
    start, end = _LIST_SPAN_HEADINGS["REMEDIATION_FINDINGS_LIST"]
    span = _content_between(lines, positions[start], positions[end])
    if not context.remediation_findings and span != "- (none)":
        findings.append(
            Finding(
                code="remediation_findings_list_span",
                message="Empty remediation-finding list must render exactly '- (none)'",
            )
        )
    return findings


def _check_fragments(
    context: PromptContext, prompt_id: str, lines: list[str], positions: dict[str, int]
) -> list[Finding]:
    findings: list[Finding] = []
    try:
        fragments = get_fragments(context.stage)
    except ValueError as exc:
        return [Finding(code="unknown_stage", message=str(exc))]

    mapping = build_placeholder_mapping(context, prompt_id)

    for name in MARKER_ORDER:
        start_heading, end_heading = _FRAGMENT_SPAN_HEADINGS[name]
        end_index = positions[end_heading] if end_heading is not None else len(lines) - 1
        span = _content_between(lines, positions[start_heading], end_index)
        expected = apply_mapping(tokenize_template(fragments[name]), mapping)
        if span != expected:
            findings.append(
                Finding(
                    code="fragment_mismatch",
                    message=f"Rendered {name} fragment does not equal the {context.stage} fragment",
                )
            )

    verdict_span_end = len(lines) - 1
    verdict_span = _content_between(lines, positions["## Verdict instruction"], verdict_span_end)
    if context.stage in _REVIEW_STAGES:
        expected_verdict = "Return exactly one final verdict token: APPROVED or REJECTED."
        if verdict_span != expected_verdict:
            findings.append(
                Finding(
                    code="verdict_instruction_mismatch",
                    message="Review stage must render the exact APPROVED/REJECTED verdict text",
                )
            )
    else:
        expected_verdict = "No APPROVED or REJECTED verdict is requested for this stage."
        if verdict_span != expected_verdict:
            findings.append(
                Finding(
                    code="verdict_instruction_mismatch",
                    message="Non-review stage must render the exact no-verdict instruction",
                )
            )
    return findings


def _check_content_identity(context: PromptContext) -> list[Finding]:
    try:
        reference = get_template(context.stage)
    except ValueError as exc:
        return [Finding(code="unknown_stage", message=str(exc))]
    findings: list[Finding] = []
    if context.template.content != reference.content:
        findings.append(
            Finding(
                code="template_content_mismatch",
                message=f"template.content does not equal the {context.stage} registry content",
            )
        )
    if context.template.version != reference.version:
        findings.append(
            Finding(
                code="template_version_mismatch",
                message=f"template.version does not equal the {context.stage} registry version",
            )
        )
    if context.template.sha256 != reference.sha256:
        findings.append(
            Finding(
                code="template_sha256_mismatch",
                message=f"template.sha256 does not equal the {context.stage} registry digest",
            )
        )
    return findings


def _check_full_consistency(rendered: RenderedPrompt) -> list[Finding]:
    context = rendered.context
    findings: list[Finding] = []

    payload_bytes = canonical_payload_bytes(context)
    if payload_bytes != rendered.canonical_payload_bytes:
        findings.append(
            Finding(
                code="payload_bytes_mismatch", message="canonical_payload_bytes is not reproducible"
            )
        )
    payload_sha256, prompt_id = compute_prompt_id(payload_bytes)
    if prompt_id != rendered.prompt_id:
        findings.append(Finding(code="prompt_id_mismatch", message="prompt_id is not reproducible"))

    metadata = rendered.metadata
    if metadata.prompt_id != rendered.prompt_id:
        findings.append(
            Finding(code="metadata_prompt_id_mismatch", message="metadata.prompt_id differs")
        )
    if metadata.project_id != context.config.project.id:
        findings.append(
            Finding(code="metadata_project_id_mismatch", message="metadata.project_id differs")
        )
    if metadata.task_id != context.task_id:
        findings.append(
            Finding(code="metadata_task_id_mismatch", message="metadata.task_id differs")
        )
    if metadata.stage != context.stage:
        findings.append(Finding(code="metadata_stage_mismatch", message="metadata.stage differs"))
    if metadata.template_version != context.template.version:
        findings.append(
            Finding(
                code="metadata_template_version_mismatch",
                message="metadata.template_version differs",
            )
        )
    if metadata.template_sha256 != context.template.sha256:
        findings.append(
            Finding(
                code="metadata_template_sha256_mismatch", message="metadata.template_sha256 differs"
            )
        )
    if metadata.repository_head != context.git_status.head:
        findings.append(
            Finding(
                code="metadata_repository_head_mismatch", message="metadata.repository_head differs"
            )
        )
    if metadata.allowed_paths != context.allowed_paths:
        findings.append(
            Finding(
                code="metadata_allowed_paths_mismatch", message="metadata.allowed_paths differs"
            )
        )
    if metadata.remediation_findings != context.remediation_findings:
        findings.append(
            Finding(
                code="metadata_remediation_findings_mismatch",
                message="metadata.remediation_findings differs",
            )
        )
    if metadata.payload_sha256 != payload_sha256:
        findings.append(
            Finding(
                code="metadata_payload_sha256_mismatch", message="metadata.payload_sha256 differs"
            )
        )
    if metadata.payload != context:
        findings.append(
            Finding(code="metadata_payload_mismatch", message="metadata.payload differs")
        )

    markdown_bytes = rendered.markdown.encode("utf-8", errors="strict")
    markdown_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
    if metadata.markdown_sha256 != markdown_sha256:
        findings.append(
            Finding(
                code="metadata_markdown_sha256_mismatch", message="metadata.markdown_sha256 differs"
            )
        )

    expected_metadata_bytes = canonical_json(metadata.model_dump(mode="json")) + b"\n"
    if expected_metadata_bytes != rendered.metadata_bytes:
        findings.append(
            Finding(code="metadata_bytes_mismatch", message="metadata_bytes is not reproducible")
        )

    return findings


def validate_prompt(rendered: RenderedPrompt) -> CheckResult:
    """Mechanically validate one rendered prompt; never raises for expected content defects."""
    context = rendered.context
    findings: list[Finding] = []

    findings.extend(_check_tokenization(context))
    findings.extend(_check_rerender(rendered))
    findings.extend(_check_git_evidence(context))
    findings.extend(_check_content_identity(context))

    lines = rendered.markdown.split("\n")
    heading_findings, positions = _check_headings(lines)
    findings.extend(heading_findings)
    if positions:
        findings.extend(_check_list_and_json_spans(context, rendered.prompt_id, lines, positions))
        findings.extend(_check_cardinality(context, lines, positions))
        findings.extend(_check_fragments(context, rendered.prompt_id, lines, positions))

    findings.extend(_check_full_consistency(rendered))

    status = Status.FAIL if findings else Status.PASS
    return CheckResult(
        check_name=CHECK_NAME,
        status=status,
        summary=(
            "Rendered prompt is structurally and byte-exactly consistent"
            if not findings
            else f"Prompt validation found {len(findings)} violation(s)"
        ),
        findings=findings,
        evidence={},
        affected_paths=[],
        remediation_hint=(
            None
            if not findings
            else "Re-render the prompt from its context; do not hand-edit generated Markdown."
        ),
    )
