"""The `{{name}}` runtime placeholder grammar (`stage-prompts/README.md`)."""

from __future__ import annotations

from agentos_dashboard.prompt_templates.placeholders import PLACEHOLDER_NAMES, substitute


def test_placeholder_names_match_the_documented_grammar() -> None:
    assert PLACEHOLDER_NAMES == {"branch", "head_sha", "tree_state", "date", "precondition_report"}


def test_substitute_replaces_every_named_placeholder() -> None:
    text = "branch={{branch}} head={{head_sha}} date={{date}}"
    result = substitute(text, {"branch": "main", "head_sha": "abc123", "date": "2026-08-10"})
    assert result == "branch=main head=abc123 date=2026-08-10"


def test_substitute_leaves_unmapped_placeholder_untouched() -> None:
    assert substitute("{{tree_state}}", {}) == "{{tree_state}}"


def test_substitute_leaves_unknown_token_untouched() -> None:
    assert substitute("{{not_a_real_placeholder}}", {"branch": "x"}) == "{{not_a_real_placeholder}}"


def test_substitute_is_single_pass_not_recursive() -> None:
    """A value that itself contains `{{...}}` text must not be rescanned."""
    result = substitute("{{branch}}", {"branch": "{{head_sha}}"})
    assert result == "{{head_sha}}"


def test_substitute_is_a_no_op_on_text_without_placeholders() -> None:
    text = "This document has no placeholders at all."
    assert substitute(text, {"branch": "main"}) == text
