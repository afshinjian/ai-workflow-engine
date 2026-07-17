"""Canonical JSON, tokenizer/substitution, and rendering algorithm tests."""

import hashlib
import math

import pytest
from pydantic import ValidationError

from ai_workflow_engine.prompt.models import (
    CanonicalFactRule,
    CanonicalFinding,
    CanonicalTaskRecord,
    PromptContext,
    PromptMetadata,
    canonicalize_json_value,
)
from ai_workflow_engine.prompt.renderer import (
    ALLOWED_PLACEHOLDER_NAMES,
    TemplateRenderError,
    apply_mapping,
    canonical_json,
    canonical_payload_bytes,
    compute_prompt_id,
    render_prompt,
    tokenize_template,
    validate_placeholder_counts,
)
from ai_workflow_engine.prompt.templates import get_expected_placeholder_counts, get_template


def test_normative_canonical_json_golden_vector() -> None:
    value = {"z": "é", "a": ["line\n", 0, True, None, {"beta": "\t"}]}
    data = canonical_json(value)
    assert data == b'{"a":["line\\n",0,true,null,{"beta":"\\t"}],"z":"\xc3\xa9"}'
    assert data.hex() == (
        "7b2261223a5b226c696e655c6e222c302c747275652c6e756c6c2c7b2262657461223a225c74227d5d2c"
        "227a223a22c3a9227d"
    )
    assert hashlib.sha256(data).hexdigest() == (
        "4f382bf736997a397b150feccf86a3d3f288010c86c33b40c2e184cd088db364"
    )


def test_canonical_json_object_keys_sorted_by_codepoint_shorter_prefix_first() -> None:
    data = canonical_json({"b": 1, "a": 1, "ab": 1})
    assert data == b'{"a":1,"ab":1,"b":1}'


def test_canonical_json_arrays_never_reordered() -> None:
    data = canonical_json([3, 1, 2])
    assert data == b"[3,1,2]"


def test_canonical_json_rejects_float() -> None:
    with pytest.raises(ValueError):
        canonicalize_json_value(1.5)


def test_canonical_json_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        canonicalize_json_value(math.nan)
    with pytest.raises(ValueError):
        canonicalize_json_value(math.inf)


def test_canonical_json_rejects_out_of_range_integer() -> None:
    with pytest.raises(ValueError):
        canonicalize_json_value(2**63)
    with pytest.raises(ValueError):
        canonicalize_json_value(-(2**63) - 1)
    assert canonicalize_json_value(2**63 - 1) == 2**63 - 1
    assert canonicalize_json_value(-(2**63)) == -(2**63)


def test_canonical_json_rejects_non_string_key() -> None:
    with pytest.raises(ValueError):
        canonicalize_json_value({1: "a"})


def test_canonical_json_rejects_surrogate() -> None:
    with pytest.raises(ValueError):
        canonicalize_json_value("\ud800")
    with pytest.raises(ValueError):
        canonicalize_json_value({"\ud800": "a"})


def test_canonical_json_rejects_nfc_key_collision() -> None:
    # "é" (decomposed) and "é" (precomposed) both NFC-normalize to the same key.
    with pytest.raises(ValueError):
        canonicalize_json_value({"é": 1, "é": 2})


def test_canonical_json_escapes_and_utf8() -> None:
    data = canonical_json({"q": '"\t\n\r', "slash": "a/b", "u": "é中"})
    text = data.decode("utf-8")
    assert '\\"' in text
    assert "\\t" in text and "\\n" in text and "\\r" in text
    assert "a/b" in text  # solidus is never escaped
    assert "é" in text and "中" in text


def test_canonical_json_escapes_backslash() -> None:
    data = canonical_json({"q": "a\\b"})
    assert data == b'{"q":"a\\\\b"}'


def test_canonical_json_bool_before_int_type_check() -> None:
    assert canonical_json(True) == b"true"
    assert canonical_json(False) == b"false"
    assert canonical_json(1) == b"1"


def test_canonical_json_no_bom_no_trailing_newline() -> None:
    data = canonical_json({"a": 1})
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")


# --- Tokenizer -----------------------------------------------------------------


def test_tokenize_recognizes_placeholder() -> None:
    tokens = tokenize_template("a{{STAGE_SCALAR}}b")
    assert tokens == [
        ("literal", "a"),
        ("placeholder", "STAGE_SCALAR"),
        ("literal", "b"),
    ]


def test_tokenize_no_placeholders_is_single_literal() -> None:
    assert tokenize_template("plain text") == [("literal", "plain text")]


def test_tokenize_empty_string() -> None:
    assert tokenize_template("") == []


@pytest.mark.parametrize(
    "content",
    [
        "{{",
        "}}",
        "{{lowercase}}",
        "{{1STARTSWITHDIGIT}}",
        "{{HAS SPACE}}",
        "text{{unterminated",
        "{{}}",
    ],
)
def test_tokenize_rejects_malformed_delimiters(content: str) -> None:
    with pytest.raises(TemplateRenderError):
        tokenize_template(content)


def test_tokenize_placeholder_looking_text_inside_a_resolved_value_is_inert() -> None:
    # Once tokenized+substituted, inserted text must never be rescanned for markers.
    tokens = tokenize_template("{{STAGE_SCALAR}}")
    mapping = {"STAGE_SCALAR": "{{TASK_ID_SCALAR}}"}
    result = apply_mapping(tokens, mapping)
    assert result == "{{TASK_ID_SCALAR}}"


def test_apply_mapping_rejects_unknown_name() -> None:
    tokens = tokenize_template("{{TOTALLY_UNKNOWN}}")
    with pytest.raises(TemplateRenderError, match="Unknown placeholder name"):
        apply_mapping(tokens, {})


def test_apply_mapping_rejects_missing_mapping_value() -> None:
    tokens = tokenize_template("{{STAGE_SCALAR}}")
    with pytest.raises(TemplateRenderError, match="No mapping value"):
        apply_mapping(tokens, {})


def test_apply_mapping_substitutes_every_occurrence_simultaneously() -> None:
    tokens = tokenize_template("{{STAGE_SCALAR}}-{{STAGE_SCALAR}}")
    result = apply_mapping(tokens, {"STAGE_SCALAR": "X"})
    assert result == "X-X"


def test_allowed_placeholder_names_is_the_closed_eighteen_name_set() -> None:
    assert ALLOWED_PLACEHOLDER_NAMES == frozenset(
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


# --- Shell escaping and scalar formatting --------------------------------------


def test_shell_escape_golden_example() -> None:
    from ai_workflow_engine.prompt.renderer import _shell_escape

    assert _shell_escape("a b'") == "$'\\x61\\x20\\x62\\x27'"


def test_shell_escape_never_emits_raw_control_or_non_ascii_bytes() -> None:
    from ai_workflow_engine.prompt.renderer import _shell_escape

    escaped = _shell_escape("é\n\t")
    assert escaped == "$'\\xc3\\xa9\\x0a\\x09'"
    body = escaped[2:-1]
    assert all(b < 0x80 for b in body.encode("ascii"))


def test_scalar_formatting_none_bool_int() -> None:
    from ai_workflow_engine.prompt.renderer import _scalar

    assert _scalar(None) == "null"
    assert _scalar(True) == "true"
    assert _scalar(False) == "false"
    assert _scalar(0) == "0"
    assert _scalar(-3) == "-3"
    assert _scalar(42) == "42"


def test_list_block_formatter_empty_is_none_marker() -> None:
    from ai_workflow_engine.prompt.renderer import _list_block

    assert _list_block([]) == "- (none)"


def test_list_block_formatter_non_empty_preserves_order() -> None:
    from ai_workflow_engine.prompt.renderer import _list_block

    assert _list_block(["b", "a"]) == '- "b"\n- "a"'


# --- Expected runtime-placeholder occurrence counts -----------------------------


def test_validate_placeholder_counts_accepts_exact_match() -> None:
    tokens = tokenize_template("{{STAGE_SCALAR}}-{{STAGE_SCALAR}}")
    validate_placeholder_counts(tokens, {"STAGE_SCALAR": 2})


def test_validate_placeholder_counts_rejects_missing_marker() -> None:
    tokens = tokenize_template("plain text")
    with pytest.raises(TemplateRenderError, match=r"occurred 0 time\(s\); expected exactly 1"):
        validate_placeholder_counts(tokens, {"STAGE_SCALAR": 1})


def test_validate_placeholder_counts_rejects_duplicate_marker() -> None:
    tokens = tokenize_template("{{STAGE_SCALAR}}{{STAGE_SCALAR}}")
    with pytest.raises(TemplateRenderError, match=r"occurred 2 time\(s\); expected exactly 1"):
        validate_placeholder_counts(tokens, {"STAGE_SCALAR": 1})


def test_validate_placeholder_counts_rejects_marker_from_the_wrong_stage() -> None:
    # GIT_BRANCH_SCALAR is a globally allowed name but expected zero times outside `push`.
    tokens = tokenize_template("{{GIT_BRANCH_SCALAR}}")
    with pytest.raises(TemplateRenderError, match=r"expected exactly 0"):
        validate_placeholder_counts(tokens, {})


def test_get_expected_placeholder_counts_matches_verification_command_repetition() -> None:
    assert get_expected_placeholder_counts("plan-review")["CONDA_ENVIRONMENT_SHELL"] == 3
    assert get_expected_placeholder_counts("push")["CONDA_ENVIRONMENT_SHELL"] == 7
    assert get_expected_placeholder_counts("push")["GIT_BRANCH_SCALAR"] == 1
    assert "GIT_BRANCH_SCALAR" not in get_expected_placeholder_counts("plan-review")
    assert "GIT_BRANCH_SCALAR" not in get_expected_placeholder_counts("implementation")


def test_get_expected_placeholder_counts_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match="No expected placeholder counts"):
        get_expected_placeholder_counts("not-a-stage")  # type: ignore[arg-type]


def _mutated_template_context(engine_config, stage: str, mutate):
    import hashlib

    from ai_workflow_engine.prompt.context import build_prompt_context

    context = build_prompt_context(engine_config, stage=stage, task_id="T-1")
    broken_content = mutate(context.template.content)
    broken_template = context.template.model_copy(
        update={
            "content": broken_content,
            "sha256": hashlib.sha256(broken_content.encode("utf-8")).hexdigest(),
        }
    )
    return context.model_copy(update={"template": broken_template})


def test_render_prompt_succeeds_for_an_unmodified_registry_template(engine_config) -> None:
    from ai_workflow_engine.prompt.context import build_prompt_context

    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    rendered = render_prompt(context)
    assert rendered.markdown.startswith("# Governed Workflow Prompt\n")


def test_render_prompt_rejects_a_missing_expected_placeholder(engine_config) -> None:
    mutated_context = _mutated_template_context(
        engine_config,
        "plan-review",
        lambda content: content.replace("{{PROMPT_ID_SCALAR}}", "PROMPT_ID_SCALAR", 1),
    )
    with pytest.raises(TemplateRenderError, match=r"PROMPT_ID_SCALAR.*occurred 0"):
        render_prompt(mutated_context)


def test_render_prompt_rejects_a_duplicated_expected_placeholder(engine_config) -> None:
    mutated_context = _mutated_template_context(
        engine_config,
        "plan-review",
        lambda content: content.replace("{{STAGE_SCALAR}}", "{{STAGE_SCALAR}}{{STAGE_SCALAR}}", 1),
    )
    with pytest.raises(TemplateRenderError, match=r"STAGE_SCALAR.*occurred 2"):
        render_prompt(mutated_context)


def test_render_prompt_rejects_a_marker_belonging_to_a_different_stage(engine_config) -> None:
    mutated_context = _mutated_template_context(
        engine_config,
        "plan-review",
        lambda content: content.replace("## Identity\n", "## Identity\n{{GIT_BRANCH_SCALAR}}\n", 1),
    )
    with pytest.raises(TemplateRenderError, match=r"GIT_BRANCH_SCALAR.*expected exactly 0"):
        render_prompt(mutated_context)


def test_render_prompt_missing_placeholder_produces_no_rendered_prompt(engine_config) -> None:
    mutated_context = _mutated_template_context(
        engine_config,
        "plan-review",
        lambda content: content.replace("{{TASK_ID_SCALAR}}", "TASK_ID_SCALAR", 1),
    )
    try:
        render_prompt(mutated_context)
    except TemplateRenderError:
        pass
    else:  # pragma: no cover - defensive; the line above must always raise
        pytest.fail("render_prompt must raise before producing a RenderedPrompt")


# --- Strict, exact-type field enforcement on the top-level payload models --------


def test_prompt_context_rejects_wrong_type(engine_config) -> None:
    from ai_workflow_engine.prompt.context import build_prompt_context

    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    dumped = context.model_dump()
    with pytest.raises(ValidationError):
        PromptContext(**{**dumped, "stage": 1})
    with pytest.raises(ValidationError):
        PromptContext(**{**dumped, "task_id": 1})
    with pytest.raises(ValidationError):
        PromptContext(**{**dumped, "allowed_paths": "not-a-list"})


def test_prompt_metadata_rejects_wrong_type(engine_config) -> None:
    from ai_workflow_engine.prompt.context import build_prompt_context

    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    rendered = render_prompt(context)
    dumped = rendered.metadata.model_dump()
    with pytest.raises(ValidationError):
        PromptMetadata(**{**dumped, "allowed_paths": "not-a-list"})
    with pytest.raises(ValidationError):
        PromptMetadata(**{**dumped, "payload": "not-a-payload"})
    with pytest.raises(ValidationError):
        PromptMetadata(**{**dumped, "prompt_id": 1})


def test_rendered_prompt_rejects_wrong_type(engine_config) -> None:
    from ai_workflow_engine.prompt.context import build_prompt_context
    from ai_workflow_engine.prompt.models import RenderedPrompt

    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    rendered = render_prompt(context)
    dumped = rendered.model_dump()
    with pytest.raises(ValidationError):
        RenderedPrompt(**{**dumped, "canonical_payload_bytes": "not-bytes"})
    with pytest.raises(ValidationError):
        RenderedPrompt(**{**dumped, "markdown": 1})


def test_render_markdown_enforces_counts_for_every_registry_stage() -> None:
    for stage in (
        "plan-review",
        "implementation",
        "implementation-review",
        "remediation",
        "governance-closeout",
        "governance-review",
        "push",
    ):
        template = get_template(stage)  # type: ignore[arg-type]
        tokens = tokenize_template(template.content)
        expected = get_expected_placeholder_counts(stage)  # type: ignore[arg-type]
        # Must not raise: the pinned registry content satisfies its own expected counts.
        validate_placeholder_counts(tokens, expected)


# --- Per-field identity sensitivity ---------------------------------------------
#
# The plan requires a separate identity sensitivity test for every declared material
# input: changing it alone, with everything else held fixed, must change the payload
# hash / prompt ID. `test_check_result_timestamp_is_never_part_of_canonical_payload`
# in tests/test_prompt_context.py is the complementary negative case (a non-material
# field that must NOT move the hash).


def _baseline_context(engine_config):
    from ai_workflow_engine.prompt.context import build_prompt_context

    return build_prompt_context(engine_config, stage="plan-review", task_id="T-1")


def _prompt_id(context: PromptContext) -> str:
    return compute_prompt_id(canonical_payload_bytes(context))[1]


def _mutate(context: PromptContext, path: tuple[str, ...], transform):
    def recurse(obj, remaining: tuple[str, ...]):
        head, *rest = remaining
        if not rest:
            return obj.model_copy(update={head: transform(getattr(obj, head))})
        return obj.model_copy(update={head: recurse(getattr(obj, head), tuple(rest))})

    return recurse(context, path)


def _suffix(old: str) -> str:
    return old + "-MUTATED"


def _bump_nullable_int(old: int | None) -> int:
    return 999 if old is None else old + 1000


def _flip(old: bool) -> bool:
    return not old


def _append_str(old: list[str]) -> list[str]:
    return [*old, "zzz-mutated-entry"]


def _append_fact(old: list[CanonicalFactRule]) -> list[CanonicalFactRule]:
    return [
        *old,
        CanonicalFactRule(name="zzz-mutated", paths=["zzz"], pattern="p", group=0, required=False),
    ]


def _new_task_source(
    old: dict[str, list[CanonicalTaskRecord]],
) -> dict[str, list[CanonicalTaskRecord]]:
    return {
        **old,
        "zzz-mutated-source.md": [
            CanonicalTaskRecord(
                task_id="T-ZZZ", status="Planned", source="zzz-mutated-source.md", line=1
            )
        ],
    }


_SINGLE_FIELD_MUTATIONS: list[tuple[str, tuple[str, ...], object]] = [
    ("stage", ("stage",), lambda _: "governance-review"),
    ("task_id", ("task_id",), _suffix),
    ("template.version", ("template", "version"), _suffix),
    ("template.content", ("template", "content"), lambda old: old + "mutated\n"),
    ("git_status.branch", ("git_status", "branch"), _suffix),
    (
        "git_status.head",
        ("git_status", "head"),
        lambda old: ("f" if old[:1] != "f" else "e") + old[1:],
    ),
    (
        "git_status.upstream",
        ("git_status", "upstream"),
        lambda old: "origin/mutated" if old is None else _suffix(old),
    ),
    ("git_status.ahead", ("git_status", "ahead"), _bump_nullable_int),
    ("git_status.behind", ("git_status", "behind"), _bump_nullable_int),
    ("git_status.modified_files", ("git_status", "modified_files"), _append_str),
    ("git_status.staged_files", ("git_status", "staged_files"), _append_str),
    ("git_status.untracked_files", ("git_status", "untracked_files"), _append_str),
    ("task_snapshot.current", ("task_snapshot", "current"), _append_str),
    ("task_snapshot.done", ("task_snapshot", "done"), _append_str),
    ("task_snapshot.planned", ("task_snapshot", "planned"), _append_str),
    ("task_snapshot.by_source", ("task_snapshot", "by_source"), _new_task_source),
    ("protected_path_violations", ("protected_path_violations",), _append_str),
    ("remediation_findings", ("remediation_findings",), _append_str),
    ("allowed_paths", ("allowed_paths",), _append_str),
    ("config.project.id", ("config", "project", "id"), _suffix),
    ("config.project.repository", ("config", "project", "repository"), _suffix),
    ("config.project.default_branch", ("config", "project", "default_branch"), _suffix),
    ("config.project.timezone", ("config", "project", "timezone"), _suffix),
    ("config.project.require_upstream", ("config", "project", "require_upstream"), _flip),
    ("config.project.conda_environment", ("config", "project", "conda_environment"), _suffix),
    ("config.governance.project_state", ("config", "governance", "project_state"), _suffix),
    ("config.governance.task_queue", ("config", "governance", "task_queue"), _suffix),
    ("config.governance.current_task", ("config", "governance", "current_task"), _suffix),
    ("config.governance.remaining_tasks", ("config", "governance", "remaining_tasks"), _suffix),
    ("config.governance.context", ("config", "governance", "context"), _suffix),
    ("config.governance.pyproject", ("config", "governance", "pyproject"), _suffix),
    ("config.governance.facts", ("config", "governance", "facts"), _append_fact),
    ("config.handover.manifest", ("config", "handover", "manifest"), _suffix),
    ("config.handover.files", ("config", "handover", "files"), _append_str),
    (
        "config.protected_paths.never_stage",
        ("config", "protected_paths", "never_stage"),
        _append_str,
    ),
    (
        "config.protected_paths.never_commit",
        ("config", "protected_paths", "never_commit"),
        _append_str,
    ),
    (
        "config.workflow.maximum_current_tasks",
        ("config", "workflow", "maximum_current_tasks"),
        lambda old: old + 1,
    ),
    (
        "config.workflow.require_designer_approval_for_promotion",
        ("config", "workflow", "require_designer_approval_for_promotion"),
        _flip,
    ),
    (
        "config.workflow.allow_automatic_commit",
        ("config", "workflow", "allow_automatic_commit"),
        _flip,
    ),
    ("config.workflow.allow_automatic_push", ("config", "workflow", "allow_automatic_push"), _flip),
]


@pytest.mark.parametrize(
    ("label", "path", "transform"),
    _SINGLE_FIELD_MUTATIONS,
    ids=[label for label, _, _ in _SINGLE_FIELD_MUTATIONS],
)
def test_material_input_changes_prompt_identity(
    engine_config, label: str, path: tuple[str, ...], transform
) -> None:
    baseline = _baseline_context(engine_config)
    mutated = _mutate(baseline, path, transform)
    message = f"Mutating {label} did not change the prompt identity"
    assert _prompt_id(mutated) != _prompt_id(baseline), message


def test_task_record_field_changes_prompt_identity(engine_config) -> None:
    baseline = _baseline_context(engine_config)
    source, records = next(iter(baseline.task_snapshot.by_source.items()))
    mutated_record = records[0].model_copy(update={"line": records[0].line + 1000})
    mutated_snapshot = baseline.task_snapshot.model_copy(
        update={
            "by_source": {
                **baseline.task_snapshot.by_source,
                source: [mutated_record, *records[1:]],
            }
        }
    )
    mutated = baseline.model_copy(update={"task_snapshot": mutated_snapshot})
    assert _prompt_id(mutated) != _prompt_id(baseline)


_CHECK_INDEX_BY_NAME = {"git": 0, "task-state": 1, "governance": 2, "handover": 3}


@pytest.mark.parametrize("check_name", ["git", "task-state", "governance", "handover"])
def test_check_status_changes_prompt_identity(engine_config, check_name: str) -> None:
    baseline = _baseline_context(engine_config)
    index = _CHECK_INDEX_BY_NAME[check_name]
    check = baseline.checks[index]
    new_status = "FAIL" if check.status != "FAIL" else "ERROR"
    mutated_check = check.model_copy(update={"status": new_status})
    mutated = baseline.model_copy(
        update={"checks": [*baseline.checks[:index], mutated_check, *baseline.checks[index + 1 :]]}
    )
    assert _prompt_id(mutated) != _prompt_id(baseline)


@pytest.mark.parametrize("check_name", ["git", "task-state", "governance", "handover"])
def test_check_summary_changes_prompt_identity(engine_config, check_name: str) -> None:
    baseline = _baseline_context(engine_config)
    index = _CHECK_INDEX_BY_NAME[check_name]
    check = baseline.checks[index]
    mutated_check = check.model_copy(update={"summary": _suffix(check.summary)})
    mutated = baseline.model_copy(
        update={"checks": [*baseline.checks[:index], mutated_check, *baseline.checks[index + 1 :]]}
    )
    assert _prompt_id(mutated) != _prompt_id(baseline)


@pytest.mark.parametrize("check_name", ["git", "task-state", "governance", "handover"])
def test_check_findings_changes_prompt_identity(engine_config, check_name: str) -> None:
    baseline = _baseline_context(engine_config)
    index = _CHECK_INDEX_BY_NAME[check_name]
    check = baseline.checks[index]
    new_finding = CanonicalFinding(code="zzz-mutated", message="m", severity="info", path=None)
    mutated_check = check.model_copy(update={"findings": [*check.findings, new_finding]})
    mutated = baseline.model_copy(
        update={"checks": [*baseline.checks[:index], mutated_check, *baseline.checks[index + 1 :]]}
    )
    assert _prompt_id(mutated) != _prompt_id(baseline)


@pytest.mark.parametrize("check_name", ["git", "task-state", "governance", "handover"])
def test_check_evidence_changes_prompt_identity(engine_config, check_name: str) -> None:
    # Governance facts and handover records live inside this evidence dict, so mutating
    # it here is also the identity sensitivity proof for those two nested shapes.
    baseline = _baseline_context(engine_config)
    index = _CHECK_INDEX_BY_NAME[check_name]
    check = baseline.checks[index]
    mutated_check = check.model_copy(update={"evidence": {**check.evidence, "zzz_mutated": True}})
    mutated = baseline.model_copy(
        update={"checks": [*baseline.checks[:index], mutated_check, *baseline.checks[index + 1 :]]}
    )
    assert _prompt_id(mutated) != _prompt_id(baseline)
