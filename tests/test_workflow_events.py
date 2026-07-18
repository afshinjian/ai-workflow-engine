import pytest
from pydantic import ValidationError

from ai_workflow_engine.workflow.events import (
    VERDICT_STAGES,
    WorkflowEvent,
    normalize_note,
)

_HEAD = "a" * 40


def make_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "1.0",
        "project_id": "proj",
        "task_id": "T-1",
        "sequence": 1,
        "parent_digest": None,
        "stage": "implementation",
        "action": "completed",
        "verdict": None,
        "prompt_id": None,
        "agent_run_id": None,
        "head": _HEAD,
        "note": "",
    }
    base.update(overrides)
    return base


def test_valid_completed_event() -> None:
    event = WorkflowEvent.model_validate(make_kwargs())
    assert event.stage == "implementation"
    assert event.action == "completed"
    assert event.verdict is None


def test_valid_verdict_event() -> None:
    event = WorkflowEvent.model_validate(
        make_kwargs(stage="plan-review", action="verdict", verdict="APPROVED")
    )
    assert event.verdict == "APPROVED"


@pytest.mark.parametrize("stage", sorted(VERDICT_STAGES))
def test_verdict_stage_requires_verdict_action(stage: str) -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(stage=stage, action="completed", verdict=None))


@pytest.mark.parametrize("stage", sorted(VERDICT_STAGES))
def test_verdict_stage_requires_non_null_verdict(stage: str) -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(stage=stage, action="verdict", verdict=None))


@pytest.mark.parametrize("stage", ["implementation", "remediation", "governance-closeout", "push"])
def test_non_verdict_stage_forbids_verdict(stage: str) -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(stage=stage, action="verdict", verdict="APPROVED"))


@pytest.mark.parametrize("stage", ["implementation", "remediation", "governance-closeout", "push"])
def test_non_verdict_stage_requires_completed_action(stage: str) -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(stage=stage, action="verdict", verdict=None))


def test_parent_digest_null_only_when_sequence_one() -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(sequence=2, parent_digest=None))
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(sequence=1, parent_digest="b" * 64))


def test_valid_chained_event() -> None:
    event = WorkflowEvent.model_validate(make_kwargs(sequence=2, parent_digest="b" * 64))
    assert event.sequence == 2


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(make_kwargs(unexpected="x"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", "-bad"),
        ("project_id", "has space"),
        ("task_id", "  untrimmed  "),
        ("sequence", 0),
        ("head", "xyz"),
        ("head", "a" * 39),
        ("prompt_id", "ABCDEF0123456789"),
        ("prompt_id", "abc"),
        ("agent_run_id", "nothex0000000000"),
        ("parent_digest", "short"),
        ("note", "  untrimmed note  "),
        ("schema_version", "1.1"),
    ],
)
def test_field_validation_rejections(field: str, value: object) -> None:
    kwargs = make_kwargs(**{field: value})
    if field == "parent_digest":
        kwargs["sequence"] = 2
    with pytest.raises(ValidationError):
        WorkflowEvent.model_validate(kwargs)


def test_normalize_note_collapses_whitespace_and_allows_empty() -> None:
    assert normalize_note("  a\t\n b  ") == "a b"
    assert normalize_note("   ") == ""
    assert normalize_note("") == ""


def test_normalize_note_rejects_surrogate() -> None:
    with pytest.raises(ValueError):
        normalize_note("bad\ud800surrogate")


def test_head_accepts_64_hex() -> None:
    event = WorkflowEvent.model_validate(make_kwargs(head="c" * 64))
    assert event.head == "c" * 64
