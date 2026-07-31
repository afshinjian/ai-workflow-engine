"""Tests for the Reporting Skills (`SKILL_CONTRACTS.md` §6): audit-root confinement, symlink
rejection, content-hash idempotency, and append-only audit semantics."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.skills import FailureKind, RetryClassification
from agentos_workflow.skills.reporting import (
    append_audit_event,
    generate_closeout_report,
    generate_failure_report,
    generate_qa_report,
    generate_stage_report,
    read_reports,
    write_sanitized_output,
)

WORKFLOW = "wf001"


@pytest.fixture
def audit_root(tmp_path: Path) -> Path:
    root = tmp_path / "audit"
    root.mkdir()
    return root


GENERATORS: list[tuple[Callable[..., Any], str, str]] = [
    (generate_stage_report, "stage", "results"),
    (generate_qa_report, "qa", "results"),
    (generate_failure_report, "failure", "context"),
    (generate_closeout_report, "closeout", "results"),
]


# ---------------------------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("generator,kind,kwarg", GENERATORS)
def test_report_is_written_inside_the_audit_root(
    audit_root: Path, generator: Callable[..., Any], kind: str, kwarg: str
) -> None:
    result = generator(audit_root=audit_root, workflow_id=WORKFLOW, **{kwarg: {"summary": "ok"}})
    artifact = result.unwrap()
    assert artifact.path == audit_root / WORKFLOW / "reports" / f"{kind}.json"
    assert artifact.path.is_file()
    payload = json.loads(artifact.path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == kind
    assert payload["workflow_id"] == WORKFLOW
    assert "generated_at" in payload


def test_identical_regeneration_is_an_idempotent_no_op(audit_root: Path) -> None:
    results = {"summary": "ok", "generated_at": "2026-07-27T00:00:00+00:00"}
    first = generate_stage_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results=results
    ).unwrap()
    second = generate_stage_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results=results
    ).unwrap()
    assert first.sha256 == second.sha256
    assert first.already_present is False
    assert second.already_present is True


def test_differing_content_refuses_to_overwrite(audit_root: Path) -> None:
    """Another workflow may already reference the existing report."""
    generate_stage_report(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        results={"summary": "first", "generated_at": "2026-07-27T00:00:00+00:00"},
    ).unwrap()
    result = generate_stage_report(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        results={"summary": "second", "generated_at": "2026-07-27T00:00:00+00:00"},
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE
    stored = json.loads((audit_root / WORKFLOW / "reports" / "stage.json").read_text())
    assert stored["summary"] == "first"


@pytest.mark.parametrize("generator,kind,kwarg", GENERATORS)
def test_a_sequence_names_the_artifact_inside_the_same_workflow_directory(
    audit_root: Path, generator: Callable[..., Any], kind: str, kwarg: str
) -> None:
    """GOV-3: several genuinely different reports of one kind belong to one workflow."""
    artifact = generator(
        audit_root=audit_root, workflow_id=WORKFLOW, sequence=2, **{kwarg: {"summary": "ok"}}
    ).unwrap()
    assert artifact.path == audit_root / WORKFLOW / "reports" / f"{kind}.2.json"
    payload = json.loads(artifact.path.read_text(encoding="utf-8"))
    assert payload["report_sequence"] == 2
    assert payload["workflow_id"] == WORKFLOW


def test_successive_rounds_do_not_collide(audit_root: Path) -> None:
    """The defect GOV-3 fixes: round two failed on the artifact, not on the code under review."""
    written = [
        generate_qa_report(
            audit_root=audit_root,
            workflow_id=WORKFLOW,
            results={"verdict": "REJECTED", "attempt_number": round_number},
            sequence=round_number,
        ).unwrap()
        for round_number in (1, 2, 3)
    ]
    assert [artifact.path.name for artifact in written] == ["qa.1.json", "qa.2.json", "qa.3.json"]
    assert all(artifact.already_present is False for artifact in written)
    assert sorted(path.name for path in (audit_root / WORKFLOW / "reports").iterdir()) == [
        "qa.1.json",
        "qa.2.json",
        "qa.3.json",
    ]


def test_an_omitted_sequence_keeps_the_unsequenced_name(audit_root: Path) -> None:
    """Every existing caller passes no sequence and must be unaffected."""
    artifact = generate_qa_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results={"summary": "ok"}
    ).unwrap()
    assert artifact.path.name == "qa.json"
    assert "report_sequence" not in json.loads(artifact.path.read_text(encoding="utf-8"))


def test_the_same_sequence_still_refuses_differing_content(audit_root: Path) -> None:
    """Sequencing distinguishes rounds; it never relaxes the append-only refusal within one."""
    generate_qa_report(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        results={"summary": "first", "generated_at": "2026-07-29T00:00:00+00:00"},
        sequence=1,
    ).unwrap()
    result = generate_qa_report(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        results={"summary": "second", "generated_at": "2026-07-29T00:00:00+00:00"},
        sequence=1,
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE
    stored = json.loads((audit_root / WORKFLOW / "reports" / "qa.1.json").read_text())
    assert stored["summary"] == "first"


def test_an_identical_sequenced_regeneration_is_idempotent(audit_root: Path) -> None:
    results = {"summary": "ok", "generated_at": "2026-07-29T00:00:00+00:00"}
    first = generate_qa_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results=results, sequence=1
    ).unwrap()
    second = generate_qa_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results=results, sequence=1
    ).unwrap()
    assert first.sha256 == second.sha256
    assert (first.already_present, second.already_present) == (False, True)


@pytest.mark.parametrize("hostile", [0, -1, 10000, "1", 1.0, True, "../escape"])
def test_unsafe_sequences_are_rejected(audit_root: Path, hostile: Any) -> None:
    """A sequence is a validated integer, so nothing a caller passes can widen the filename."""
    result = generate_qa_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results={"a": 1}, sequence=hostile
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE
    assert not (audit_root / WORKFLOW / "reports").exists(), "nothing may be written"


def test_report_content_is_redacted(audit_root: Path) -> None:
    secret = "ghp_" + "A" * 36
    artifact = generate_failure_report(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        context={"stderr": f"auth failed for {secret}", "nested": {"deep": [secret]}},
    ).unwrap()
    text = artifact.path.read_text(encoding="utf-8")
    assert secret not in text
    assert "REDACTED" in text


def test_report_json_is_canonical(audit_root: Path) -> None:
    """Sorted keys are what make the idempotency hash stable rather than accidental."""
    artifact = generate_stage_report(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        results={"zebra": 1, "alpha": 2, "generated_at": "2026-07-27T00:00:00+00:00"},
    ).unwrap()
    text = artifact.path.read_text(encoding="utf-8")
    assert text.index('"alpha"') < text.index('"zebra"')


@pytest.mark.parametrize(
    "hostile", ["../escape", "a/b", "/abs", "", ".hidden", "-flag", "x" * 200, "wf\x00"]
)
def test_unsafe_workflow_ids_are_rejected(audit_root: Path, hostile: str) -> None:
    result = generate_stage_report(audit_root=audit_root, workflow_id=hostile, results={})
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE


def test_relative_audit_root_is_rejected(tmp_path: Path) -> None:
    result = generate_stage_report(audit_root=Path("relative"), workflow_id=WORKFLOW, results={})
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_symlinked_workflow_directory_is_refused(audit_root: Path, tmp_path: Path) -> None:
    """A component swapped for a symlink must abort the walk, not redirect the write."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (audit_root / WORKFLOW).symlink_to(outside)
    result = generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={"a": 1})
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.IO_ERROR
    assert not any(outside.rglob("*.json")), "nothing may be written outside the audit root"


def test_symlinked_report_file_is_refused(audit_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "target.json"
    outside.write_text("{}", encoding="utf-8")
    reports = audit_root / WORKFLOW / "reports"
    reports.mkdir(parents=True)
    (reports / "stage.json").symlink_to(outside)
    result = generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={"a": 1})
    assert not result.ok and result.error is not None
    assert outside.read_text(encoding="utf-8") == "{}", "the symlink target must be untouched"


def test_report_files_are_owner_only(audit_root: Path) -> None:
    artifact = generate_stage_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results={"a": 1}
    ).unwrap()
    assert (artifact.path.stat().st_mode & 0o077) == 0


# ---------------------------------------------------------------------------------------------
# write_sanitized_output
# ---------------------------------------------------------------------------------------------


def test_sanitized_output_is_written_and_redacted(audit_root: Path) -> None:
    secret = "ghp_" + "D" * 36
    artifact = write_sanitized_output(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        operation_id="op1",
        stream="stdout",
        content=f"before {secret} after",
    ).unwrap()
    assert artifact.path == audit_root / WORKFLOW / "output" / "op1" / "stdout.txt"
    text = artifact.path.read_text(encoding="utf-8")
    assert secret not in text
    assert "before" in text and "after" in text


def test_sanitized_output_rejects_an_unknown_stream(audit_root: Path) -> None:
    result = write_sanitized_output(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        operation_id="op1",
        stream="../../etc/passwd",
        content="x",
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_sanitized_output_rejects_an_unsafe_operation_id(audit_root: Path) -> None:
    result = write_sanitized_output(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        operation_id="../escape",
        stream="stdout",
        content="x",
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_stdout_and_stderr_are_separate_references(audit_root: Path) -> None:
    out = write_sanitized_output(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        operation_id="op1",
        stream="stdout",
        content="out",
    ).unwrap()
    err = write_sanitized_output(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        operation_id="op1",
        stream="stderr",
        content="err",
    ).unwrap()
    assert out.path != err.path
    assert out.path.read_text() == "out"
    assert err.path.read_text() == "err"


# ---------------------------------------------------------------------------------------------
# append_audit_event
# ---------------------------------------------------------------------------------------------


def read_log(audit_root: Path) -> list[dict[str, Any]]:
    path = audit_root / WORKFLOW / "audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_append_audit_event_appends_one_line(audit_root: Path) -> None:
    result = append_audit_event(
        audit_root=audit_root, workflow_id=WORKFLOW, event={"kind": "state_transition"}
    ).unwrap()
    assert result.appended is True
    records = read_log(audit_root)
    assert len(records) == 1
    assert records[0]["kind"] == "state_transition"
    assert records[0]["workflow_id"] == WORKFLOW
    assert records[0]["event_id"] == result.event_id


def test_appending_the_same_event_twice_is_suppressed(audit_root: Path) -> None:
    """`SKILL_CONTRACTS.md` §6: a duplicate is detectable via event ID and suppressed."""
    event = {"kind": "gate", "recorded_at": "2026-07-27T00:00:00+00:00"}
    first = append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event=dict(event))
    second = append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event=dict(event))
    assert first.unwrap().appended is True
    assert second.unwrap().appended is False
    assert second.unwrap().event_id == first.unwrap().event_id
    assert len(read_log(audit_root)) == 1


def test_distinct_events_both_append(audit_root: Path) -> None:
    append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event={"kind": "a"}).unwrap()
    append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event={"kind": "b"}).unwrap()
    assert len(read_log(audit_root)) == 2


def test_explicit_event_id_is_honoured_and_deduplicated(audit_root: Path) -> None:
    append_audit_event(
        audit_root=audit_root, workflow_id=WORKFLOW, event={"event_id": "evt1", "kind": "a"}
    ).unwrap()
    second = append_audit_event(
        audit_root=audit_root, workflow_id=WORKFLOW, event={"event_id": "evt1", "kind": "b"}
    ).unwrap()
    assert second.appended is False
    assert len(read_log(audit_root)) == 1


def test_unsafe_event_id_is_rejected(audit_root: Path) -> None:
    result = append_audit_event(
        audit_root=audit_root, workflow_id=WORKFLOW, event={"event_id": "../escape"}
    )
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_audit_event_content_is_redacted(audit_root: Path) -> None:
    secret = "ghp_" + "E" * 36
    append_audit_event(
        audit_root=audit_root, workflow_id=WORKFLOW, event={"detail": f"used {secret}"}
    ).unwrap()
    raw = (audit_root / WORKFLOW / "audit.jsonl").read_text(encoding="utf-8")
    assert secret not in raw
    assert "REDACTED" in raw


def test_audit_log_stays_one_record_per_line(audit_root: Path) -> None:
    """A torn or multi-line record is indistinguishable from tampering."""
    append_audit_event(
        audit_root=audit_root,
        workflow_id=WORKFLOW,
        event={"detail": "line one\nline two\nline three"},
    ).unwrap()
    text = (audit_root / WORKFLOW / "audit.jsonl").read_text(encoding="utf-8")
    assert text.count("\n") == 1
    assert json.loads(text)["detail"] == "line one\nline two\nline three"


def test_audit_log_is_append_only_across_calls(audit_root: Path) -> None:
    for index in range(5):
        append_audit_event(
            audit_root=audit_root, workflow_id=WORKFLOW, event={"sequence": index}
        ).unwrap()
    records = read_log(audit_root)
    assert [record["sequence"] for record in records] == [0, 1, 2, 3, 4]


def test_corrupt_historical_line_does_not_cause_a_duplicate(audit_root: Path) -> None:
    """A corrupt line is not this Skill's to repair, but must not defeat deduplication."""
    event = {"event_id": "evt1", "kind": "a"}
    append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event=dict(event)).unwrap()
    log = audit_root / WORKFLOW / "audit.jsonl"
    with log.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    second = append_audit_event(
        audit_root=audit_root, workflow_id=WORKFLOW, event=dict(event)
    ).unwrap()
    assert second.appended is False


def test_symlinked_audit_log_is_refused(audit_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text("", encoding="utf-8")
    (audit_root / WORKFLOW).mkdir(parents=True)
    (audit_root / WORKFLOW / "audit.jsonl").symlink_to(outside)
    result = append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event={"kind": "a"})
    assert not result.ok and result.error is not None
    assert outside.read_text(encoding="utf-8") == "", "the symlink target must be untouched"


def test_audit_log_is_owner_only(audit_root: Path) -> None:
    append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event={"kind": "a"}).unwrap()
    mode = (audit_root / WORKFLOW / "audit.jsonl").stat().st_mode
    assert (mode & 0o077) == 0


def test_audit_directories_are_owner_only(audit_root: Path) -> None:
    append_audit_event(audit_root=audit_root, workflow_id=WORKFLOW, event={"kind": "a"}).unwrap()
    assert (os.stat(audit_root / WORKFLOW).st_mode & 0o077) == 0


def test_unsafe_workflow_id_is_rejected_for_audit_append(audit_root: Path) -> None:
    result = append_audit_event(audit_root=audit_root, workflow_id="../escape", event={"kind": "a"})
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


# ---------------------------------------------------------------------------------------------
# Reading back persisted reports (AUTO-009)
# ---------------------------------------------------------------------------------------------


def test_read_reports_returns_every_artifact_with_its_content(audit_root: Path) -> None:
    generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={"verdict": "PASS"})
    generate_qa_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results={"verdict": "PASS"}, sequence=2
    )
    reports = read_reports(audit_root=audit_root, workflow_id=WORKFLOW).unwrap()
    assert [(report.report_kind, report.sequence) for report in reports] == [
        ("qa", 2),
        ("stage", None),
    ]
    assert reports[1].content["verdict"] == "PASS"
    assert reports[1].content["workflow_id"] == WORKFLOW
    assert reports[1].size_bytes == reports[1].path.stat().st_size


def test_read_reports_orders_a_kind_unsequenced_first_then_by_sequence(audit_root: Path) -> None:
    generate_qa_report(audit_root=audit_root, workflow_id=WORKFLOW, results={"round": 0})
    for sequence in (3, 1, 2):
        generate_qa_report(
            audit_root=audit_root,
            workflow_id=WORKFLOW,
            results={"round": sequence},
            sequence=sequence,
        )
    reports = read_reports(audit_root=audit_root, workflow_id=WORKFLOW).unwrap()
    assert [report.sequence for report in reports] == [None, 1, 2, 3]


def test_read_reports_filters_by_kind(audit_root: Path) -> None:
    generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={})
    generate_qa_report(audit_root=audit_root, workflow_id=WORKFLOW, results={})
    reports = read_reports(audit_root=audit_root, workflow_id=WORKFLOW, report_kind="qa").unwrap()
    assert [report.report_kind for report in reports] == ["qa"]


def test_read_reports_on_a_workflow_with_no_reports_is_an_empty_success(audit_root: Path) -> None:
    result = read_reports(audit_root=audit_root, workflow_id=WORKFLOW)
    assert result.ok
    assert result.unwrap() == []


def test_read_reports_creates_nothing(audit_root: Path) -> None:
    """The read counterpart must not bring the directory the writers create into existence."""
    before = sorted(audit_root.rglob("*"))
    assert read_reports(audit_root=audit_root, workflow_id=WORKFLOW).ok
    assert sorted(audit_root.rglob("*")) == before


def test_read_reports_does_not_rewrite_what_it_reads(audit_root: Path) -> None:
    generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={"verdict": "PASS"})
    artifact = audit_root / WORKFLOW / "reports" / "stage.json"
    before = (artifact.read_bytes(), artifact.stat().st_mtime_ns, artifact.stat().st_mode)
    assert read_reports(audit_root=audit_root, workflow_id=WORKFLOW).ok
    assert (artifact.read_bytes(), artifact.stat().st_mtime_ns, artifact.stat().st_mode) == before


def test_read_reports_reports_the_hash_of_the_bytes_on_disk(audit_root: Path) -> None:
    written = generate_stage_report(
        audit_root=audit_root, workflow_id=WORKFLOW, results={"verdict": "PASS"}
    ).unwrap()
    read = read_reports(audit_root=audit_root, workflow_id=WORKFLOW).unwrap()[0]
    assert read.sha256 == written.sha256
    assert read.size_bytes == written.size_bytes


def test_read_reports_ignores_a_file_that_is_not_a_report_artifact(audit_root: Path) -> None:
    generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={})
    (audit_root / WORKFLOW / "reports" / "notes.txt").write_text("scratch", encoding="utf-8")
    reports = read_reports(audit_root=audit_root, workflow_id=WORKFLOW).unwrap()
    assert [report.report_kind for report in reports] == ["stage"]


def test_read_reports_surfaces_malformed_json_rather_than_repairing_it(audit_root: Path) -> None:
    generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={})
    artifact = audit_root / WORKFLOW / "reports" / "stage.json"
    artifact.write_text("{ not json", encoding="utf-8")
    result = read_reports(audit_root=audit_root, workflow_id=WORKFLOW)
    assert not result.ok
    assert result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT
    assert artifact.read_text(encoding="utf-8") == "{ not json"


@pytest.mark.parametrize("hostile", ["../escape", "/absolute", "", "wf/../..", ".hidden"])
def test_read_reports_rejects_an_unsafe_workflow_id(audit_root: Path, hostile: str) -> None:
    result = read_reports(audit_root=audit_root, workflow_id=hostile)
    assert not result.ok
    assert result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE


@pytest.mark.parametrize("hostile", ["../escape", "/absolute", ""])
def test_read_reports_rejects_an_unsafe_report_kind(audit_root: Path, hostile: str) -> None:
    result = read_reports(audit_root=audit_root, workflow_id=WORKFLOW, report_kind=hostile)
    assert not result.ok
    assert result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_read_reports_rejects_a_relative_audit_root(tmp_path: Path) -> None:
    result = read_reports(audit_root=Path("relative/audit"), workflow_id=WORKFLOW)
    assert not result.ok
    assert result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_read_reports_refuses_a_symlinked_workflow_directory(
    audit_root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside" / "reports"
    outside.mkdir(parents=True)
    (outside / "stage.json").write_text('{"stolen": true}', encoding="utf-8")
    os.symlink(outside.parent, audit_root / WORKFLOW)
    result = read_reports(audit_root=audit_root, workflow_id=WORKFLOW)
    assert not result.ok
    assert result.error is not None
    assert result.error.kind is FailureKind.IO_ERROR


def test_read_reports_refuses_a_symlinked_report_file(audit_root: Path, tmp_path: Path) -> None:
    generate_stage_report(audit_root=audit_root, workflow_id=WORKFLOW, results={})
    secret = tmp_path / "secret.json"
    secret.write_text('{"stolen": true}', encoding="utf-8")
    os.symlink(secret, audit_root / WORKFLOW / "reports" / "qa.json")
    result = read_reports(audit_root=audit_root, workflow_id=WORKFLOW)
    assert not result.ok
    assert result.error is not None
    assert result.error.kind is FailureKind.IO_ERROR
