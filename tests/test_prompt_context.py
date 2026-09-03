"""Textual normalization, allowed-path validation, and context-construction tests."""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_workflow_engine import provenance as provenance_module
from ai_workflow_engine.models import EngineConfig, VerificationBundleSettings, VerificationSettings
from ai_workflow_engine.prompt import context as context_module
from ai_workflow_engine.prompt.context import (
    DirtyTargetWorktree,
    TargetStateDrift,
    VerificationBundleSelectionError,
    build_prompt_context,
    normalize_allowed_path,
    normalize_text,
)
from ai_workflow_engine.prompt.models import (
    CanonicalCheckResult,
    CanonicalEngineProvenance,
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
from ai_workflow_engine.provenance import EngineProvenanceError
from ai_workflow_engine.result import CheckResult, Status
from ai_workflow_engine.verification_bundles import BundleCommandObservation

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
    assert context.schema_version == "1.2"


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


def test_agents_config_changes_prompt_id(engine_config: EngineConfig) -> None:
    # Adding an agent to the config must change the prompt identity, since `agents` is part of
    # the canonical payload (Milestone 3, task T-303). The rendered Markdown body changes only
    # via the prompt-id line.
    from ai_workflow_engine.models import AgentSettings
    from ai_workflow_engine.prompt.renderer import render_prompt

    agent = AgentSettings(
        name="reviewer",
        executable=Path("/usr/bin/true"),
        args=[],
        mode="read-only",
        timeout_seconds=60,
        stages=["plan-review"],
    )
    with_agent = engine_config.model_copy(update={"agents": [agent]})
    without = render_prompt(build_prompt_context(engine_config, stage="plan-review", task_id="T-1"))
    withx = render_prompt(build_prompt_context(with_agent, stage="plan-review", task_id="T-1"))
    assert without.prompt_id != withx.prompt_id
    assert without.context.config.agents == []
    assert withx.context.config.agents[0].name == "reviewer"


# --- T-307: engine provenance and verification-bundle wiring -------------------


def _ok_bundle(name: str = "quality") -> VerificationBundleSettings:
    return VerificationBundleSettings(
        name=name, commands=[[sys.executable, "-c", "raise SystemExit(0)"]]
    )


def _with_bundles(
    engine_config: EngineConfig, *bundles: VerificationBundleSettings
) -> EngineConfig:
    return engine_config.model_copy(
        update={"verification": VerificationSettings(bundles=list(bundles))}
    )


def _git(repository: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    )


def test_engine_provenance_is_always_present_with_no_bundle_selected(
    engine_config: EngineConfig,
) -> None:
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    assert isinstance(context.engine_provenance, CanonicalEngineProvenance)
    assert context.verification_evidence is None


def test_no_bundle_selected_never_calls_the_executor(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(**_kwargs: object) -> list[BundleCommandObservation]:
        raise AssertionError("run_verification_bundles must not be called with no selection")

    monkeypatch.setattr(context_module, "run_verification_bundles", _fail)
    context = build_prompt_context(engine_config, stage="plan-review", task_id="T-1")
    assert context.verification_evidence is None


def test_unknown_bundle_name_is_refused_before_any_execution(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(**_kwargs: object) -> list[BundleCommandObservation]:
        raise AssertionError("must not execute when selection is invalid")

    monkeypatch.setattr(context_module, "run_verification_bundles", _fail)
    with pytest.raises(VerificationBundleSelectionError) as excinfo:
        build_prompt_context(
            engine_config,
            stage="plan-review",
            task_id="T-1",
            verification_bundles=["absent"],
        )
    assert excinfo.value.code == "unknown_verification_bundle"


def test_duplicate_bundle_selection_is_refused_before_any_execution(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle("quality"))

    def _fail(**_kwargs: object) -> list[BundleCommandObservation]:
        raise AssertionError("must not execute when selection is invalid")

    monkeypatch.setattr(context_module, "run_verification_bundles", _fail)
    with pytest.raises(VerificationBundleSelectionError) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality", "quality"]
        )
    assert excinfo.value.code == "duplicate_verification_bundle"


def test_only_configured_bundles_are_selectable(engine_config: EngineConfig) -> None:
    config = _with_bundles(engine_config, _ok_bundle("zeta"), _ok_bundle("alpha"))
    context = build_prompt_context(
        config, stage="plan-review", task_id="T-1", verification_bundles=["zeta"]
    )
    assert context.verification_evidence is not None
    assert context.verification_evidence.bundles == ["zeta"]


def test_selection_order_is_execution_order_and_evidence_is_bound_to_target_head(
    engine_config: EngineConfig,
) -> None:
    config = _with_bundles(engine_config, _ok_bundle("zeta"), _ok_bundle("alpha"))
    context = build_prompt_context(
        config, stage="plan-review", task_id="T-1", verification_bundles=["alpha", "zeta"]
    )
    evidence = context.verification_evidence
    assert evidence is not None
    assert evidence.bundles == ["alpha", "zeta"]
    assert [observation.bundle for observation in evidence.observations] == ["alpha", "zeta"]
    assert [observation.index for observation in evidence.observations] == [0, 1]
    assert evidence.target_head == context.git_status.head


def test_dirty_target_worktree_is_refused_before_any_bundle_executes(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle())
    (config.project.repository / "untracked.txt").write_text("dirt\n", encoding="utf-8")

    def _fail(**_kwargs: object) -> list[BundleCommandObservation]:
        raise AssertionError("must not execute against a dirty target")

    monkeypatch.setattr(context_module, "run_verification_bundles", _fail)
    with pytest.raises(DirtyTargetWorktree):
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
        )


def test_a_bundle_never_mutates_the_target_repository(engine_config: EngineConfig) -> None:
    repository = engine_config.project.repository
    before_head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    before_status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    writing = VerificationBundleSettings(
        name="writer",
        commands=[
            [
                sys.executable,
                "-c",
                "import pathlib; pathlib.Path('intruder.txt').write_text('x\\n')",
            ]
        ],
    )
    config = _with_bundles(engine_config, writing)
    context = build_prompt_context(
        config, stage="plan-review", task_id="T-1", verification_bundles=["writer"]
    )
    assert context.verification_evidence is not None
    assert context.verification_evidence.observations[0].exit_code == 0

    after_head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    after_status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert after_head == before_head
    assert after_status == before_status
    assert not (repository / "intruder.txt").exists()


def test_external_target_head_drift_during_verification_fails_closed(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle())

    def _external_actor(
        *, repository: Path, repository_head: str, bundles: list[VerificationBundleSettings]
    ) -> list[BundleCommandObservation]:
        # The external actor commits to the *target*, standing in for a concurrent writer; the
        # stub never touches the sandbox and is not the bundle executor under test.
        _git(repository, "commit", "--allow-empty", "-m", "external mutation")
        return [
            BundleCommandObservation(
                bundle=bundles[0].name,
                index=0,
                argv=bundles[0].commands[0],
                exit_code=0,
                timed_out=False,
            )
        ]

    monkeypatch.setattr(context_module, "run_verification_bundles", _external_actor)
    with pytest.raises(TargetStateDrift) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
        )
    assert excinfo.value.code == "target_head_drift_during_verification"


def test_external_target_dirtiness_during_verification_fails_closed(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle())

    def _external_actor(
        *, repository: Path, repository_head: str, bundles: list[VerificationBundleSettings]
    ) -> list[BundleCommandObservation]:
        (repository / "external.txt").write_text("mutated\n", encoding="utf-8")
        return [
            BundleCommandObservation(
                bundle=bundles[0].name,
                index=0,
                argv=bundles[0].commands[0],
                exit_code=0,
                timed_out=False,
            )
        ]

    monkeypatch.setattr(context_module, "run_verification_bundles", _external_actor)
    with pytest.raises(TargetStateDrift) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
        )
    assert excinfo.value.code == "target_dirty_during_verification"


def _stub_provenance_sequence(
    monkeypatch: pytest.MonkeyPatch, values: list[CanonicalEngineProvenance]
) -> None:
    iterator = iter(values)
    monkeypatch.setattr(context_module, "resolve_engine_provenance", lambda: next(iterator))


def test_engine_head_drift_during_verification_fails_closed(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle())
    before = CanonicalEngineProvenance(
        engine_version="0.0.0-test",
        engine_head="a" * 40,
        engine_worktree_clean=True,
        engine_install_mode="source",
        engine_package_path="/nonexistent/engine",
    )
    after = before.model_copy(update={"engine_head": "b" * 40})
    _stub_provenance_sequence(monkeypatch, [before, after])
    with pytest.raises(EngineProvenanceError) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
        )
    assert excinfo.value.code == "engine_head_drift_during_verification"


def test_engine_dirtiness_during_verification_fails_closed(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle())
    before = CanonicalEngineProvenance(
        engine_version="0.0.0-test",
        engine_head="a" * 40,
        engine_worktree_clean=True,
        engine_install_mode="source",
        engine_package_path="/nonexistent/engine",
    )
    after = before.model_copy(update={"engine_worktree_clean": False})
    _stub_provenance_sequence(monkeypatch, [before, after])
    with pytest.raises(EngineProvenanceError) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
        )
    assert excinfo.value.code == "engine_dirty_during_verification"


def test_engine_becoming_unresolvable_during_verification_fails_closed(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bundles(engine_config, _ok_bundle())
    before = CanonicalEngineProvenance(
        engine_version="0.0.0-test",
        engine_head="a" * 40,
        engine_worktree_clean=True,
        engine_install_mode="source",
        engine_package_path="/nonexistent/engine",
    )
    calls = iter(
        [
            before,
            provenance_module.EngineProvenanceError(
                "engine vanished mid-run", code="engine_head_unresolvable"
            ),
        ]
    )

    def _sequence() -> CanonicalEngineProvenance:
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(context_module, "resolve_engine_provenance", _sequence)
    with pytest.raises(EngineProvenanceError) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=["quality"]
        )
    assert excinfo.value.code == "engine_drift_during_verification"


@pytest.mark.parametrize("select_a_bundle", [False, True])
def test_editable_dirty_engine_is_refused_at_context_construction(
    select_a_bundle: bool, engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC7: proves the wiring -- `build_prompt_context` calls the resolver first and propagates
    its refusal, **both** with a bundle selected and with none selected. The resolver's own OD-1
    logic (editable+clean permitted, non-editable/source unaffected by dirt) is exhaustively
    covered in `tests/test_engine_provenance.py`."""

    def _refuse() -> CanonicalEngineProvenance:
        raise EngineProvenanceError("dirty editable engine", code="engine_editable_worktree_dirty")

    monkeypatch.setattr(context_module, "resolve_engine_provenance", _refuse)

    def _fail_if_bundles_are_resolved(
        config: EngineConfig, selected: object
    ) -> list[VerificationBundleSettings]:
        raise AssertionError("bundle resolution must not run before the OD-1 gate")

    monkeypatch.setattr(context_module, "_resolve_selected_bundles", _fail_if_bundles_are_resolved)

    config = _with_bundles(engine_config, _ok_bundle()) if select_a_bundle else engine_config
    selection = ["quality"] if select_a_bundle else []
    with pytest.raises(EngineProvenanceError) as excinfo:
        build_prompt_context(
            config, stage="plan-review", task_id="T-1", verification_bundles=selection
        )
    assert excinfo.value.code == "engine_editable_worktree_dirty"
