import pytest
from pydantic import ValidationError

from ai_workflow_engine.agents.models import AgentFinding, AgentReport


def make_report(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "1.0",
        "task_id": "T-1",
        "stage": "implementation-review",
        "prompt_id": "0123456789abcdef",
        "verdict": "APPROVED",
        "summary": "looks good",
        "findings": [],
        "changed_paths": [],
        "verification_commands_run": ["pytest"],
        "blockers": [],
    }
    base.update(overrides)
    return base


def test_valid_verdict_report() -> None:
    report = AgentReport.model_validate(make_report())
    assert report.verdict == "APPROVED"
    assert report.stage == "implementation-review"


def test_valid_scoped_write_report() -> None:
    report = AgentReport.model_validate(
        make_report(
            stage="implementation",
            verdict=None,
            changed_paths=["src/a.py", "src/b.py"],
        )
    )
    assert report.changed_paths == ["src/a.py", "src/b.py"]


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(make_report(unexpected="x"))


@pytest.mark.parametrize("prompt_id", ["ABCDEF0123456789", "abc", "0123456789abcde", ""])
def test_bad_prompt_id_rejected(prompt_id: str) -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(make_report(prompt_id=prompt_id))


def test_changed_paths_must_be_sorted() -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(
            make_report(stage="implementation", verdict=None, changed_paths=["b", "a"])
        )


def test_changed_paths_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(
            make_report(stage="implementation", verdict=None, changed_paths=["a", "a"])
        )


def test_changed_paths_no_empty_string() -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(
            make_report(stage="implementation", verdict=None, changed_paths=[""])
        )


def test_bad_schema_version_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(make_report(schema_version="1.1"))


def test_bad_stage_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentReport.model_validate(make_report(stage="not-a-stage"))


def test_finding_severity_literal_enforced() -> None:
    with pytest.raises(ValidationError):
        AgentFinding.model_validate(
            {"code": "x", "message": "m", "severity": "critical", "path": None}
        )


def test_finding_code_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        AgentFinding.model_validate(
            {"code": "   ", "message": "m", "severity": "blocking", "path": None}
        )


def test_valid_finding_in_report() -> None:
    report = AgentReport.model_validate(
        make_report(
            findings=[
                {"code": "bug", "message": "boom", "severity": "blocking", "path": "src/a.py"}
            ]
        )
    )
    assert report.findings[0].severity == "blocking"
