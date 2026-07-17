"""Canonical JSON, prompt identity, and the normative Markdown rendering algorithm."""

import hashlib
import json
import re
import unicodedata
from typing import Literal

from ai_workflow_engine.prompt.models import (
    PromptContext,
    PromptMetadata,
    RenderedPrompt,
    canonicalize_json_value,
)
from ai_workflow_engine.prompt.templates import get_expected_placeholder_counts


class TemplateRenderError(ValueError):
    """The normative tokenization/substitution algorithm rejected a template."""


ALLOWED_PLACEHOLDER_NAMES: frozenset[str] = frozenset(
    {
        "ALLOWED_PATHS_LIST",
        "CHECKS_JSON",
        "CONDA_ENVIRONMENT_SCALAR",
        "CONDA_ENVIRONMENT_SHELL",
        "DEFAULT_BRANCH_SCALAR",
        "GIT_AHEAD_SCALAR",
        "GIT_BEHIND_SCALAR",
        "GIT_BRANCH_SCALAR",
        "GIT_HEAD_SCALAR",
        "GIT_STATUS_JSON",
        "GIT_UPSTREAM_SCALAR",
        "PROMPT_ID_SCALAR",
        "PROTECTED_PATH_VIOLATIONS_LIST",
        "REMEDIATION_FINDINGS_LIST",
        "REPOSITORY_PATH_SCALAR",
        "STAGE_SCALAR",
        "TASK_ID_SCALAR",
        "TASK_SNAPSHOT_JSON",
    }
)

Token = tuple[Literal["literal", "placeholder"], str]

_TOKEN_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}|\{\{|\}\}")


def tokenize_template(content: str) -> list[Token]:
    """Single left-to-right tokenizer for the runtime `{{NAME}}` placeholder grammar."""
    tokens: list[Token] = []
    position = 0
    for match in _TOKEN_RE.finditer(content):
        if match.start() > position:
            tokens.append(("literal", content[position : match.start()]))
        name = match.group(1)
        if name is None:
            raise TemplateRenderError(
                f"Malformed placeholder delimiter at offset {match.start()}: {match.group()!r}"
            )
        tokens.append(("placeholder", name))
        position = match.end()
    if position < len(content):
        tokens.append(("literal", content[position:]))
    return tokens


def canonical_json(value: object) -> bytes:
    """Deterministic, NFC-normalized, sorted-key, compact JSON serialization."""
    normalized = canonicalize_json_value(value)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        check_circular=True,
    )
    return text.encode("utf-8", errors="strict")


def _scalar(value: object) -> str:
    return canonical_json(value).decode("utf-8")


def _shell_escape(value: str) -> str:
    """One Bash ANSI-C-quoted word: every UTF-8 byte emitted as \\xHH, no exceptions."""
    data = value.encode("utf-8", errors="strict")
    body = "".join(f"\\x{byte:02x}" for byte in data)
    return f"$'{body}'"


def _list_block(values: list[str]) -> str:
    if not values:
        return "- (none)"
    return "\n".join(f"- {_scalar(value)}" for value in values)


def _json_block(value: object) -> str:
    return f"```json\n{canonical_json(value).decode('utf-8')}\n```"


def build_placeholder_mapping(context: PromptContext, prompt_id: str) -> dict[str, str]:
    """The closed, fully-populated runtime placeholder mapping for one render."""
    project = context.config.project
    git = context.git_status
    return {
        "PROMPT_ID_SCALAR": _scalar(prompt_id),
        "STAGE_SCALAR": _scalar(context.stage),
        "TASK_ID_SCALAR": _scalar(context.task_id),
        "REPOSITORY_PATH_SCALAR": _scalar(project.repository),
        "DEFAULT_BRANCH_SCALAR": _scalar(project.default_branch),
        "CONDA_ENVIRONMENT_SCALAR": _scalar(project.conda_environment),
        "CONDA_ENVIRONMENT_SHELL": _shell_escape(project.conda_environment),
        "GIT_BRANCH_SCALAR": _scalar(git.branch),
        "GIT_HEAD_SCALAR": _scalar(git.head),
        "GIT_UPSTREAM_SCALAR": _scalar(git.upstream),
        "GIT_AHEAD_SCALAR": _scalar(git.ahead),
        "GIT_BEHIND_SCALAR": _scalar(git.behind),
        "ALLOWED_PATHS_LIST": _list_block(context.allowed_paths),
        "PROTECTED_PATH_VIOLATIONS_LIST": _list_block(context.protected_path_violations),
        "REMEDIATION_FINDINGS_LIST": _list_block(context.remediation_findings),
        "GIT_STATUS_JSON": _json_block(git.model_dump(mode="json")),
        "TASK_SNAPSHOT_JSON": _json_block(context.task_snapshot.model_dump(mode="json")),
        "CHECKS_JSON": _json_block([check.model_dump(mode="json") for check in context.checks]),
    }


def validate_placeholder_counts(tokens: list[Token], expected_counts: dict[str, int]) -> None:
    """Require every allowed placeholder to occur exactly its stage-fixed expected count.

    A name missing from `expected_counts` has an expected count of zero. Comparing the
    union of observed and expected names catches a missing marker (observed 0, expected
    > 0), a duplicate marker (observed > expected), and a marker misplaced into the wrong
    stage's template (observed > 0, expected 0) with one uniform rule.
    """
    actual_counts: dict[str, int] = {}
    for kind, value in tokens:
        if kind == "placeholder":
            actual_counts[value] = actual_counts.get(value, 0) + 1
    for name in sorted(set(actual_counts) | set(expected_counts)):
        expected = expected_counts.get(name, 0)
        actual = actual_counts.get(name, 0)
        if actual != expected:
            raise TemplateRenderError(
                f"Placeholder {{{{{name}}}}} occurred {actual} time(s); expected exactly "
                f"{expected} for this stage"
            )


def apply_mapping(tokens: list[Token], mapping: dict[str, str]) -> str:
    """Simultaneously substitute every placeholder token; inserted text is never rescanned."""
    parts: list[str] = []
    for kind, value in tokens:
        if kind == "literal":
            parts.append(value)
            continue
        if value not in ALLOWED_PLACEHOLDER_NAMES:
            raise TemplateRenderError(f"Unknown placeholder name: {value}")
        replacement = mapping.get(value)
        if replacement is None:
            raise TemplateRenderError(f"No mapping value for placeholder: {value}")
        parts.append(replacement)
    return "".join(parts)


def render_markdown(template_content: str, context: PromptContext, prompt_id: str) -> str:
    """Apply the normative tokenization, mapping, formatting, and substitution algorithm."""
    tokens = tokenize_template(template_content)
    expected_counts = get_expected_placeholder_counts(context.stage)
    validate_placeholder_counts(tokens, expected_counts)
    mapping = build_placeholder_mapping(context, prompt_id)
    markdown = apply_mapping(tokens, mapping)
    if any(0xD800 <= ord(character) <= 0xDFFF for character in markdown):
        raise TemplateRenderError("Rendered Markdown must not contain a surrogate code point")
    if "\r" in markdown:
        raise TemplateRenderError("Rendered Markdown must use LF line endings only")
    if unicodedata.normalize("NFC", markdown) != markdown:
        raise TemplateRenderError("Rendered Markdown must be NFC-normalized")
    if not markdown.endswith("\n") or markdown.endswith("\n\n"):
        raise TemplateRenderError("Rendered Markdown must end with exactly one terminal newline")
    return markdown


def canonical_payload_bytes(context: PromptContext) -> bytes:
    return canonical_json(context.model_dump(mode="json"))


def compute_prompt_id(payload_bytes: bytes) -> tuple[str, str]:
    """Return (payload_sha256, prompt_id)."""
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    return payload_sha256, payload_sha256[:16]


def render_prompt(context: PromptContext) -> RenderedPrompt:
    """Deterministically render, hash, and address one prompt from its context."""
    payload_bytes = canonical_payload_bytes(context)
    payload_sha256, prompt_id = compute_prompt_id(payload_bytes)
    markdown = render_markdown(context.template.content, context, prompt_id)
    markdown_bytes = markdown.encode("utf-8", errors="strict")
    markdown_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
    metadata = PromptMetadata(
        schema_version="1.0",
        prompt_id=prompt_id,
        project_id=context.config.project.id,
        task_id=context.task_id,
        stage=context.stage,
        template_version=context.template.version,
        template_sha256=context.template.sha256,
        repository_head=context.git_status.head,
        allowed_paths=context.allowed_paths,
        remediation_findings=context.remediation_findings,
        payload_sha256=payload_sha256,
        markdown_sha256=markdown_sha256,
        payload=context,
    )
    metadata_bytes = canonical_json(metadata.model_dump(mode="json")) + b"\n"
    return RenderedPrompt(
        context=context,
        canonical_payload_bytes=payload_bytes,
        prompt_id=prompt_id,
        markdown=markdown,
        metadata=metadata,
        metadata_bytes=metadata_bytes,
    )
