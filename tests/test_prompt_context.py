"""Textual normalization, allowed-path validation, and context-construction tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import (
    build_prompt_context,
    normalize_allowed_path,
    normalize_text,
)
from ai_workflow_engine.prompt.models import (
    CanonicalCheckResult,
    CanonicalFactRule,
    CanonicalFinding,
    CanonicalGitStatus,
    CanonicalGovernanceSettings,
    CanonicalHandoverSettings,
    CanonicalProjectSettings,
    CanonicalProtectedPathsSettings,
    CanonicalTaskRecord,
    CanonicalTaskSnapshot,
    CanonicalWorkflowSettings,
)
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.result import CheckResult, Status

# --- Task ID / finding textual normalization ------------------------------------


def test_normalize_text_ordinary_value_is_unchanged() -> None:
    assert normalize_text("T-1") == "T-1"


def test_normalize_text_collapses_whitespace_runs_to_one_space() -> None:
    assert normalize_text("a   b\t\tc") == "a b c"


def test_normalize_text_strips_leading_and_trailing_ascii_spaces() -> None:
    assert normalize_text("  a b  ") == "a b"


def test_normalize_text_collapses_unicode_whitespace() -> None:
    # U+00A0 NO-BREAK SPACE and U+3000 IDEOGRAPHIC SPACE both satisfy str.isspace().
    assert normalize_text("a\u00a0\u3000b") == "a b"


def test_normalize_text_applies_nfc() -> None:
    decomposed = "é"  # "e" + combining acute accent
    assert normalize_text(decomposed) == "é"


def test_normalize_text_rejects_empty() -> None:
    with pytest.raises(ValueError):
        normalize_text("")


def test_normalize_text_rejects_whitespace_only() -> None:
    with pytest.raises(ValueError):
        normalize_text("   \t\n  ")


def test_normalize_text_rejects_surrogate() -> None:
    with pytest.raises(ValueError):
        normalize_text("\ud800")


def test_normalize_text_does_not_change_case_or_punctuation() -> None:
    assert normalize_text("Fix Bug #42!") == "Fix Bug #42!"


# --- Allowed-path normalization ---------------------------------------------------


def test_normalize_allowed_path_ordinary_relative_path(repository: Path) -> None:
    assert normalize_allowed_path("src/foo.py", repository=repository) == "src/foo.py"


def test_normalize_allowed_path_normalizes_dot_components(repository: Path) -> None:
    assert normalize_allowed_path("a/./b/../c", repository=repository) == "a/c"


@pytest.mark.parametrize("raw", ["", ".", "..", "../x", "../../x"])
def test_normalize_allowed_path_rejects_empty_root_and_escape(raw: str, repository: Path) -> None:
    with pytest.raises(ValueError):
        normalize_allowed_path(raw, repository=repository)


def test_normalize_allowed_path_rejects_whitespace(repository: Path) -> None:
    with pytest.raises(ValueError):
        normalize_allowed_path("a b", repository=repository)
    with pytest.raises(ValueError):
        normalize_allowed_path("a\tb", repository=repository)


def test_normalize_allowed_path_rejects_backslash(repository: Path) -> None:
    with pytest.raises(ValueError):
        normalize_allowed_path("a\\b", repository=repository)


@pytest.mark.parametrize(
    "raw",
    [
        "/etc/passwd",
        "//server/share",
        "C:/x",
        "C:x",
        "\\\\server\\share",
    ],
)
def test_normalize_allowed_path_rejects_rooted_drive_and_unc_spellings(
    raw: str, repository: Path
) -> None:
    with pytest.raises(ValueError):
        normalize_allowed_path(raw, repository=repository)


def test_normalize_allowed_path_rejects_existing_symlink_escape(repository: Path) -> None:
    outside = repository.parent / "outside"
    outside.mkdir()
    link = repository / "escape"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        normalize_allowed_path("escape/secret.txt", repository=repository)


def test_normalize_allowed_path_allows_nonexistent_final_component(repository: Path) -> None:
    # Only the repository root itself must exist; the candidate file need not.
    assert (
        normalize_allowed_path("src/does_not_exist_yet.py", repository=repository)
        == "src/does_not_exist_yet.py"
    )


# --- build_prompt_context: cardinality and normalization end-to-end --------------


def test_build_prompt_context_plan_review_has_no_allowed_paths_or_findings(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    assert context.allowed_paths == []
    assert context.remediation_findings == []
    assert context.task_id == "T-1"
    assert context.stage == "plan-review"
    assert context.schema_version == "1.0"


def test_build_prompt_context_implementation_requires_allowed_paths(
    engine_config: EngineConfig,
) -> None:
    with pytest.raises(ValueError):
        build_prompt_context(engine_config, stage="implementation", task_id="T-1")


def test_build_prompt_context_non_implementation_rejects_allowed_paths(
    engine_config: EngineConfig,
) -> None:
    with pytest.raises(ValueError):
        build_prompt_context(
            engine_config, stage="plan-review", task_id="T-1", allowed_paths=["src/x.py"]
        )


def test_build_prompt_context_remediation_requires_findings(engine_config: EngineConfig) -> None:
    with pytest.raises(ValueError):
        build_prompt_context(
            engine_config,
            stage="remediation",
            task_id="T-1",
            allowed_paths=["src/x.py"],
        )


def test_build_prompt_context_non_remediation_rejects_findings(
    engine_config: EngineConfig,
) -> None:
    with pytest.raises(ValueError):
        build_prompt_context(
            engine_config, stage="plan-review", task_id="T-1", remediation_findings=["Fix it"]
        )


def test_build_prompt_context_allowed_paths_deduplicated_and_sorted(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(
        engine_config,
        stage="implementation",
        task_id="T-1",
        allowed_paths=["b/y.py", "a/x.py", "a/x.py"],
    )
    assert context.allowed_paths == ["a/x.py", "b/y.py"]


def test_build_prompt_context_remediation_findings_preserve_cli_order_and_duplicates(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(
        engine_config,
        stage="remediation",
        task_id="T-1",
        allowed_paths=["a.py"],
        remediation_findings=["Second thing", "First thing", "First thing"],
    )
    assert context.remediation_findings == ["Second thing", "First thing", "First thing"]


def test_build_prompt_context_checks_are_in_fixed_order(engine_config: EngineConfig) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    assert [check.check_name for check in context.checks] == [
        "git",
        "task-state",
        "governance",
        "handover",
    ]


def test_build_prompt_context_git_evidence_has_exactly_eight_fields(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    git_check = context.checks[0]
    assert set(git_check.evidence) == {
        "branch",
        "head",
        "upstream",
        "ahead",
        "behind",
        "modified_files",
        "staged_files",
        "untracked_files",
    }


def test_build_prompt_context_task_state_evidence_has_counts(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    task_state_check = context.checks[1]
    assert "current_count" in task_state_check.evidence
    assert "maximum_current_tasks" in task_state_check.evidence
    assert task_state_check.evidence["maximum_current_tasks"] == 1


def test_build_prompt_context_governance_evidence_shape(engine_config: EngineConfig) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    governance_check = context.checks[2]
    assert set(governance_check.evidence) == {"facts"}
    assert "version" in governance_check.evidence["facts"]


def test_build_prompt_context_handover_evidence_shape(engine_config: EngineConfig) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    handover_check = context.checks[3]
    assert set(handover_check.evidence) == {"source", "commit", "records"}


def test_build_prompt_context_repository_serialized_as_posix(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    assert context.config.project.repository == engine_config.project.repository.as_posix()


def test_build_prompt_context_governance_facts_sorted_and_normalized(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    names = [rule.name for rule in context.config.governance.facts]
    assert names == sorted(names)
    for rule in context.config.governance.facts:
        assert rule.paths == sorted(set(rule.paths))


def test_build_prompt_context_repeat_calls_are_deterministic(
    engine_config: EngineConfig,
) -> None:
    first = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    second = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    assert canonical_json(first.model_dump(mode="json")) == canonical_json(
        second.model_dump(mode="json")
    )


def test_check_result_timestamp_is_never_part_of_canonical_payload() -> None:
    from ai_workflow_engine.prompt.context import _canonicalize_check_result

    base = CheckResult(check_name="git", status=Status.PASS, summary="ok", evidence={})
    later = base.model_copy(update={"timestamp": base.timestamp.replace(year=2099)})
    canonical_base = _canonicalize_check_result(base)
    canonical_later = _canonicalize_check_result(later)
    assert canonical_base == canonical_later
    assert "timestamp" not in type(canonical_base).model_fields


# --- Exact per-check evidence schema enforcement (context construction) ----------


def _check_result(check_name: str, evidence: dict) -> CheckResult:
    return CheckResult(check_name=check_name, status=Status.PASS, summary="s", evidence=evidence)


def _canonicalize(check_name: str, evidence: dict):
    from ai_workflow_engine.prompt.context import _canonicalize_check_result

    return _canonicalize_check_result(_check_result(check_name, evidence))


_VALID_GIT_EVIDENCE = {
    "branch": "main",
    "head": "a" * 40,
    "upstream": None,
    "ahead": 0,
    "behind": 0,
    "modified_files": [],
    "staged_files": [],
    "untracked_files": [],
}


def test_git_evidence_exact_valid_shape_is_accepted() -> None:
    result = _canonicalize("git", _VALID_GIT_EVIDENCE)
    assert set(result.evidence) == set(_VALID_GIT_EVIDENCE)


def test_git_evidence_rejects_missing_key() -> None:
    evidence = dict(_VALID_GIT_EVIDENCE)
    del evidence["ahead"]
    with pytest.raises(ValueError):
        _canonicalize("git", evidence)


def test_git_evidence_rejects_extra_key() -> None:
    evidence = {**_VALID_GIT_EVIDENCE, "extra": "x"}
    with pytest.raises(ValueError):
        _canonicalize("git", evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("branch", 1),
        ("head", None),
        ("upstream", 1),
        ("ahead", "0"),
        ("ahead", True),
        ("behind", 1.5),
        ("modified_files", "not-a-list"),
        ("modified_files", [1]),
        ("staged_files", None),
    ],
)
def test_git_evidence_rejects_wrong_type(field: str, value: object) -> None:
    evidence = {**_VALID_GIT_EVIDENCE, field: value}
    with pytest.raises(ValueError):
        _canonicalize("git", evidence)


_VALID_TASK_RECORD = {
    "task_id": "T-1",
    "status": "Current",
    "source": "docs/TASK_QUEUE.md",
    "line": 3,
}
_VALID_TASK_STATE_EVIDENCE = {
    "by_source": {"docs/TASK_QUEUE.md": [_VALID_TASK_RECORD]},
    "current": ["T-1"],
    "done": [],
    "planned": [],
    "current_count": 1,
    "maximum_current_tasks": 1,
}


def test_task_state_evidence_exact_valid_shape_is_accepted() -> None:
    result = _canonicalize("task-state", _VALID_TASK_STATE_EVIDENCE)
    assert set(result.evidence) == set(_VALID_TASK_STATE_EVIDENCE)


def test_task_state_evidence_rejects_missing_key() -> None:
    evidence = dict(_VALID_TASK_STATE_EVIDENCE)
    del evidence["current_count"]
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


def test_task_state_evidence_rejects_extra_key() -> None:
    evidence = {**_VALID_TASK_STATE_EVIDENCE, "extra": 1}
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current_count", "1"),
        ("current_count", True),
        ("maximum_current_tasks", 1.0),
        ("current", "T-1"),
        ("by_source", []),
    ],
)
def test_task_state_evidence_rejects_wrong_type(field: str, value: object) -> None:
    evidence = {**_VALID_TASK_STATE_EVIDENCE, field: value}
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


def test_task_state_evidence_rejects_record_missing_key() -> None:
    bad_record = {k: v for k, v in _VALID_TASK_RECORD.items() if k != "line"}
    evidence = {
        **_VALID_TASK_STATE_EVIDENCE,
        "by_source": {"docs/TASK_QUEUE.md": [bad_record]},
    }
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


def test_task_state_evidence_rejects_record_extra_key() -> None:
    bad_record = {**_VALID_TASK_RECORD, "extra": "x"}
    evidence = {
        **_VALID_TASK_STATE_EVIDENCE,
        "by_source": {"docs/TASK_QUEUE.md": [bad_record]},
    }
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


def test_task_state_evidence_rejects_invalid_record_status() -> None:
    bad_record = {**_VALID_TASK_RECORD, "status": "Unknown"}
    evidence = {
        **_VALID_TASK_STATE_EVIDENCE,
        "by_source": {"docs/TASK_QUEUE.md": [bad_record]},
    }
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


def test_task_state_evidence_rejects_record_wrong_type() -> None:
    bad_record = {**_VALID_TASK_RECORD, "line": "3"}
    evidence = {
        **_VALID_TASK_STATE_EVIDENCE,
        "by_source": {"docs/TASK_QUEUE.md": [bad_record]},
    }
    with pytest.raises(ValueError):
        _canonicalize("task-state", evidence)


_VALID_GOVERNANCE_EVIDENCE = {
    "facts": {"version": {"docs/PROJECT_STATE.md": "1.0.0", "docs/CHATGPT_CONTEXT.md": None}}
}


def test_governance_evidence_exact_valid_shape_is_accepted() -> None:
    result = _canonicalize("governance", _VALID_GOVERNANCE_EVIDENCE)
    assert set(result.evidence) == {"facts"}


def test_governance_evidence_rejects_missing_facts_key() -> None:
    with pytest.raises(ValueError):
        _canonicalize("governance", {"other": {}})


def test_governance_evidence_rejects_extra_key() -> None:
    evidence = {**_VALID_GOVERNANCE_EVIDENCE, "extra": 1}
    with pytest.raises(ValueError):
        _canonicalize("governance", evidence)


def test_governance_evidence_rejects_non_dict_fact_values() -> None:
    with pytest.raises(ValueError):
        _canonicalize("governance", {"facts": {"version": "not-a-dict"}})


def test_governance_evidence_rejects_invalid_leaf_value_type() -> None:
    with pytest.raises(ValueError):
        _canonicalize("governance", {"facts": {"version": {"docs/x.md": 1}}})


_VALID_HANDOVER_ERROR_EVIDENCE = {"source": "working-tree", "commit": "HEAD"}
_VALID_HANDOVER_FULL_EVIDENCE = {
    "source": "working-tree",
    "commit": "HEAD",
    "records": [
        {
            "path": "handover/x.md",
            "expected_size": 9,
            "actual_size": 9,
            "expected_digest": "abcd",
            "actual_digest": "abcd",
        }
    ],
}


def test_handover_evidence_early_error_shape_is_accepted() -> None:
    result = _canonicalize("handover", _VALID_HANDOVER_ERROR_EVIDENCE)
    assert set(result.evidence) == {"source", "commit"}


def test_handover_evidence_full_shape_is_accepted() -> None:
    result = _canonicalize("handover", _VALID_HANDOVER_FULL_EVIDENCE)
    assert set(result.evidence) == {"source", "commit", "records"}


def test_handover_evidence_rejects_missing_commit() -> None:
    with pytest.raises(ValueError):
        _canonicalize("handover", {"source": "working-tree"})


def test_handover_evidence_rejects_extra_key_beside_records() -> None:
    evidence = {**_VALID_HANDOVER_FULL_EVIDENCE, "extra": 1}
    with pytest.raises(ValueError):
        _canonicalize("handover", evidence)


def test_handover_evidence_rejects_record_missing_key() -> None:
    bad_record = {
        k: v for k, v in _VALID_HANDOVER_FULL_EVIDENCE["records"][0].items() if k != "actual_size"
    }
    evidence = {**_VALID_HANDOVER_FULL_EVIDENCE, "records": [bad_record]}
    with pytest.raises(ValueError):
        _canonicalize("handover", evidence)


def test_handover_evidence_rejects_record_extra_key() -> None:
    bad_record = {**_VALID_HANDOVER_FULL_EVIDENCE["records"][0], "extra": "x"}
    evidence = {**_VALID_HANDOVER_FULL_EVIDENCE, "records": [bad_record]}
    with pytest.raises(ValueError):
        _canonicalize("handover", evidence)


def test_handover_evidence_rejects_record_wrong_type() -> None:
    bad_record = {**_VALID_HANDOVER_FULL_EVIDENCE["records"][0], "expected_size": "9"}
    evidence = {**_VALID_HANDOVER_FULL_EVIDENCE, "records": [bad_record]}
    with pytest.raises(ValueError):
        _canonicalize("handover", evidence)


@pytest.mark.parametrize("check_name", ["git", "task-state", "governance", "handover"])
def test_empty_evidence_is_always_accepted_as_the_exception_fallback_shape(
    check_name: str,
) -> None:
    result = _canonicalize(check_name, {})
    assert result.evidence == {}


def test_check_name_without_a_defined_evidence_schema_is_rejected() -> None:
    with pytest.raises(ValueError):
        _canonicalize("not-a-real-check", {"a": 1})


# --- Strict, exact-type field enforcement across the Canonical* prompt models ----


def test_canonical_git_status_rejects_wrong_types() -> None:
    valid = dict(_VALID_GIT_EVIDENCE)
    with pytest.raises(ValidationError):
        CanonicalGitStatus(**{**valid, "branch": 1})
    with pytest.raises(ValidationError):
        CanonicalGitStatus(**{**valid, "ahead": "0"})
    with pytest.raises(ValidationError):
        CanonicalGitStatus(**{**valid, "ahead": True})
    with pytest.raises(ValidationError):
        CanonicalGitStatus(**{**valid, "modified_files": "not-a-list"})


def test_canonical_task_record_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalTaskRecord(task_id=1, status="Current", source="s", line=1)
    with pytest.raises(ValidationError):
        CanonicalTaskRecord(task_id="T", status="Current", source="s", line="1")
    with pytest.raises(ValidationError):
        CanonicalTaskRecord(task_id="T", status="Current", source="s", line=True)


def test_canonical_task_snapshot_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalTaskSnapshot(by_source=[], current=[], done=[], planned=[])
    with pytest.raises(ValidationError):
        CanonicalTaskSnapshot(by_source={}, current="T-1", done=[], planned=[])


def test_canonical_finding_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalFinding(code=1, message="m", severity="error", path=None)
    with pytest.raises(ValidationError):
        CanonicalFinding(code="c", message="m", severity="error", path=1)


def test_canonical_check_result_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalCheckResult(
            check_name="git",
            status="PASS",
            summary="s",
            findings=[],
            evidence=[],
            affected_paths=[],
            remediation_hint=None,
        )
    with pytest.raises(ValidationError):
        CanonicalCheckResult(
            check_name="git",
            status=1,
            summary="s",
            findings=[],
            evidence={},
            affected_paths=[],
            remediation_hint=None,
        )


def test_canonical_project_settings_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalProjectSettings(
            id="p",
            repository="r",
            default_branch="b",
            timezone="t",
            require_upstream=1,
            conda_environment="c",
        )
    with pytest.raises(ValidationError):
        CanonicalProjectSettings(
            id="p",
            repository="r",
            default_branch="b",
            timezone="t",
            require_upstream=False,
            conda_environment=1,
        )


def test_canonical_fact_rule_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalFactRule(name="n", paths=["a"], pattern="p", group=1, required="yes")
    with pytest.raises(ValidationError):
        CanonicalFactRule(name="n", paths="a", pattern="p", group=1, required=True)


def test_canonical_governance_settings_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalGovernanceSettings(
            project_state="a",
            task_queue="b",
            current_task="c",
            remaining_tasks="d",
            context="e",
            pyproject="f",
            facts={},
        )


def test_canonical_handover_settings_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalHandoverSettings(manifest="m", files="not-a-list")


def test_canonical_protected_paths_settings_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalProtectedPathsSettings(never_stage="a", never_commit=[])


def test_canonical_workflow_settings_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        CanonicalWorkflowSettings(
            maximum_current_tasks="1",
            require_designer_approval_for_promotion=True,
            allow_automatic_commit=False,
            allow_automatic_push=False,
        )
    with pytest.raises(ValidationError):
        CanonicalWorkflowSettings(
            maximum_current_tasks=1,
            require_designer_approval_for_promotion=1,
            allow_automatic_commit=False,
            allow_automatic_push=False,
        )


def test_canonical_engine_config_rejects_wrong_nested_type(
    engine_config: EngineConfig,
) -> None:
    from ai_workflow_engine.prompt.context import _canonicalize_config

    canonical = _canonicalize_config(engine_config)
    with pytest.raises(ValidationError):
        type(canonical)(**{**canonical.model_dump(), "project": "not-a-project"})
