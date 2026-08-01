"""Tests for the canonical run-result contract (AUTO-011).

Three things are proved here, and they are deliberately separate.

*The model is a contract.* Every status invariant, every rejected combination, immutability,
timezone-aware and correctly ordered timestamps, a duration that cannot disagree with its own
interval, deterministic serialization, strict round-trip parsing, and secret redaction.

*The adapter preserves AUTO-010.* Real `ProviderRunResult`s — produced by the real Provider Runtime
against stub executables, not hand-built — project into the canonical result without losing a
classification and without inventing one. The harness is imported from `test_provider_runtime` on
purpose: these tests must observe whatever AUTO-010 actually produces, so a change there is a
failure here rather than something a private copy of the fixtures would hide.

*Nothing gained authority.* `recommended_next_state` is advisory, and this module proves it over
the parsed syntax tree of the engine's own transition machinery rather than by assertion in prose.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from agentos_workflow.agents import AgentKind
from agentos_workflow.orchestrator import engine as engine_module
from agentos_workflow.orchestrator.engine import WorkflowState
from agentos_workflow.providers.base import (
    MAX_PROVIDER_STDERR_BYTES,
    MAX_PROVIDER_STDOUT_BYTES,
    ProviderFailure,
    ProviderFailureKind,
    ProviderKind,
    ProviderReport,
    ProviderRole,
    ProviderRunStatus,
    ProviderVerdict,
)
from agentos_workflow.providers.runtime import (
    ProviderRunResult,
    ProviderRuntime,
    ProviderRuntimeTarget,
)
from agentos_workflow.results import (
    AgentRunResult,
    ArtifactKind,
    ArtifactReference,
    ExecutionMode,
    RunFailure,
    RunStatus,
    agent_run_result_from_provider_run,
)
from agentos_workflow.skills import CommandExecution, CommandOutcome, RetryClassification
from agentos_workflow.tests.test_provider_runtime import (
    COMPLETED_REPORT,
    claude_stub,
    codex_stub,
    config_for,
    request_for,
    stub,
)

START = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
FINISH = START + timedelta(seconds=2, microseconds=500000)


def result(**overrides: Any) -> AgentRunResult:
    """A minimal valid canonical result, with every field a test cares about overridable."""
    fields: dict[str, Any] = {
        "workflow_id": "wf-1",
        "session_id": "wf-1/claude_cli/inv-1",
        "mode": ExecutionMode.PROVIDER_INVOCATION,
        "provider": ProviderKind.CLAUDE_CLI,
        "agent": None,
        "status": RunStatus.COMPLETED,
        "summary": "did the thing",
        "started_at": START,
        "completed_at": FINISH,
    }
    return AgentRunResult(**{**fields, **overrides})


def failure(**overrides: Any) -> RunFailure:
    fields: dict[str, Any] = {
        "kind": ProviderFailureKind.COMMAND_FAILED,
        "detail": "claude_cli exited 1",
        "retry_classification": RetryClassification.POSSIBLE_SIDE_EFFECT,
    }
    return RunFailure(**{**fields, **overrides})


# ---------------------------------------------------------------------------------------------
# Reuse rather than duplication
# ---------------------------------------------------------------------------------------------


class TestReuseNotDuplication:
    """The unified contract must not introduce a second vocabulary for anything that already has
    one; a parallel enum plus a mapping between two of them is the drift this stage exists to
    prevent."""

    def test_run_status_is_the_provider_run_status_enum_itself(self) -> None:
        assert RunStatus is ProviderRunStatus

    def test_exactly_the_four_terminal_statuses(self) -> None:
        assert [member.value for member in RunStatus] == [
            "completed",
            "completed_with_assumptions",
            "blocked",
            "failed",
        ]

    def test_canonical_result_reuses_existing_enums_for_every_shared_axis(self) -> None:
        annotations = AgentRunResult.model_fields
        assert annotations["status"].annotation is ProviderRunStatus
        assert annotations["provider"].annotation == ProviderKind | None
        assert annotations["agent"].annotation == AgentKind | None
        assert annotations["final_verdict"].annotation == ProviderVerdict | None
        assert annotations["recommended_next_state"].annotation == WorkflowState | None
        assert RunFailure.model_fields["kind"].annotation is ProviderFailureKind
        assert RunFailure.model_fields["retry_classification"].annotation is RetryClassification

    def test_no_second_status_or_verdict_enum_is_declared(self) -> None:
        source = Path("agentos_workflow/results.py").read_text(encoding="utf-8")
        declared = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ClassDef)
            and any(_dotted(base) in {"StrEnum", "Enum"} for base in node.bases)
        }
        # Only the two vocabularies nothing in the repository already had.
        assert declared == {"ExecutionMode", "ArtifactKind"}

    def test_every_required_canonical_field_is_present(self) -> None:
        required = {
            "workflow_id",
            "mode",
            "agent",
            "provider",
            "status",
            "summary",
            "assumptions",
            "blocking_issues",
            "changed_files",
            "artifacts",
            "tests_run",
            "started_at",
            "completed_at",
            "duration_seconds",
            "exit_code",
            "failure",
            "final_verdict",
            "recommended_next_state",
        }
        assert required <= set(AgentRunResult.model_fields)


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# ---------------------------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------------------------


class TestStatusInvariants:
    def test_completed_with_assumptions_requires_an_assumption(self) -> None:
        with pytest.raises(ValidationError, match="at least one assumption"):
            result(status=RunStatus.COMPLETED_WITH_ASSUMPTIONS, assumptions=())

    def test_completed_with_assumptions_accepts_one(self) -> None:
        built = result(
            status=RunStatus.COMPLETED_WITH_ASSUMPTIONS,
            assumptions=("assumed docs/ is the target",),
        )
        assert built.assumptions == ("assumed docs/ is the target",)

    def test_blocked_requires_a_blocking_issue(self) -> None:
        with pytest.raises(ValidationError, match="at least one blocking issue"):
            result(status=RunStatus.BLOCKED, blocking_issues=())

    def test_failed_requires_a_typed_failure(self) -> None:
        with pytest.raises(ValidationError, match="requires a typed failure"):
            result(status=RunStatus.FAILED, failure=None)

    def test_completed_rejects_a_failure(self) -> None:
        with pytest.raises(ValidationError, match="must carry no failure"):
            result(status=RunStatus.COMPLETED, failure=failure())

    def test_completed_rejects_blocking_issues(self) -> None:
        with pytest.raises(ValidationError, match="no blocking issues"):
            result(status=RunStatus.COMPLETED, blocking_issues=("something stopped me",))

    def test_blocked_rejects_a_failure_too(self) -> None:
        with pytest.raises(ValidationError, match="must carry no failure"):
            result(status=RunStatus.BLOCKED, blocking_issues=("no contract",), failure=failure())

    def test_unknown_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            result(status="partially_completed")

    def test_a_result_must_name_a_producer(self) -> None:
        with pytest.raises(ValidationError, match="must name a producer"):
            result(provider=None, agent=None)

    def test_an_agent_alone_is_a_valid_producer(self) -> None:
        assert result(provider=None, agent=AgentKind.QA).agent is AgentKind.QA

    def test_unknown_provider_and_agent_identities_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            result(provider="gemini_cli")
        with pytest.raises(ValidationError):
            result(agent="architect")

    def test_succeeded_matches_the_provider_runtime_definition(self) -> None:
        assert result(status=RunStatus.COMPLETED).succeeded
        assert result(status=RunStatus.COMPLETED_WITH_ASSUMPTIONS, assumptions=("a",)).succeeded
        assert not result(status=RunStatus.BLOCKED, blocking_issues=("b",)).succeeded
        assert not result(status=RunStatus.FAILED, failure=failure()).succeeded


class TestTimestampsAndDuration:
    def test_naive_timestamps_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            result(started_at=datetime(2026, 8, 1, 12, 0, 0))
        with pytest.raises(ValidationError, match="timezone-aware"):
            result(completed_at=datetime(2026, 8, 1, 12, 0, 0))

    def test_completion_before_start_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not precede"):
            result(started_at=FINISH, completed_at=START)

    def test_duration_is_derived_when_omitted(self) -> None:
        assert result().duration_seconds == 2.5

    def test_duration_is_deterministic_for_the_same_interval(self) -> None:
        assert result().duration_seconds == result().duration_seconds

    def test_a_supplied_duration_that_contradicts_the_interval_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="contradicts the interval"):
            result(duration_seconds=99.0)

    def test_a_supplied_duration_that_agrees_is_accepted(self) -> None:
        assert result(duration_seconds=2.5).duration_seconds == 2.5

    def test_a_negative_duration_cannot_be_expressed(self) -> None:
        # Reachable only by contradicting the interval, which is refused first; the guard below it
        # exists so the invariant holds even if that ordering ever changes.
        with pytest.raises(ValidationError):
            result(duration_seconds=-1.0)

    def test_zero_duration_is_legal(self) -> None:
        assert result(started_at=START, completed_at=START).duration_seconds == 0.0


class TestStrictnessAndImmutability:
    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            result(recommended_commit_message="feat: something")

    def test_the_result_is_frozen(self) -> None:
        built = result()
        with pytest.raises(ValidationError):
            built.status = RunStatus.FAILED  # type: ignore[misc]
        with pytest.raises(ValidationError):
            built.summary = "rewritten"  # type: ignore[misc]

    def test_nested_models_are_frozen_too(self) -> None:
        reference = ArtifactReference(kind=ArtifactKind.STDOUT, path="/tmp/s/stdout.txt")
        with pytest.raises(ValidationError):
            reference.path = "/etc/passwd"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            failure().detail = "rewritten"  # type: ignore[misc]

    def test_artifact_references_reject_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactReference(kind=ArtifactKind.STDOUT, path="/tmp/a", content="...")


class TestArtifactReferences:
    def test_a_traversal_segment_is_refused(self) -> None:
        with pytest.raises(ValidationError, match=r"\.\."):
            ArtifactReference(kind=ArtifactKind.STDOUT, path="/tmp/sessions/../../etc/shadow")

    def test_an_empty_path_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            ArtifactReference(kind=ArtifactKind.STDOUT, path="")

    def test_a_nul_byte_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="NUL"):
            ArtifactReference(kind=ArtifactKind.STDOUT, path="/tmp/a\x00.txt")

    def test_a_credential_shaped_path_is_redacted(self) -> None:
        reference = ArtifactReference(
            kind=ArtifactKind.SESSION_DIRECTORY,
            path="/tmp/ghp_aaaaaaaaaaaaaaaaaaaaaaaa/session",
        )
        assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaa" not in reference.path
        assert "REDACTED" in reference.path

    def test_a_relative_evidence_path_is_accepted(self) -> None:
        reference = ArtifactReference(
            kind=ArtifactKind.TEST_RESULT_EVIDENCE, path="reports/qa.json"
        )
        assert reference.path == "reports/qa.json"

    def test_every_artifact_kind_the_contract_names_exists(self) -> None:
        assert {member.value for member in ArtifactKind} == {
            "stdout",
            "stderr",
            "provider_report",
            "session_directory",
            "changed_file_evidence",
            "test_result_evidence",
        }

    def test_no_field_carries_artifact_content(self) -> None:
        assert set(ArtifactReference.model_fields) == {"kind", "path"}


class TestSecretRedaction:
    def test_the_summary_is_redacted(self) -> None:
        built = result(summary="used token ghp_aaaaaaaaaaaaaaaaaaaaaaaa to push")
        assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaa" not in built.summary
        assert "REDACTED" in built.summary

    @pytest.mark.parametrize(
        "field", ["assumptions", "blocking_issues", "tests_run", "changed_files"]
    )
    def test_every_string_sequence_is_redacted(self, field: str) -> None:
        status_extra: dict[str, Any] = {}
        if field == "blocking_issues":
            status_extra = {"status": RunStatus.BLOCKED}
        if field == "assumptions":
            status_extra = {"status": RunStatus.COMPLETED_WITH_ASSUMPTIONS}
        built = result(**{field: ("ghp_aaaaaaaaaaaaaaaaaaaaaaaa",), **status_extra})
        assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaa" not in getattr(built, field)[0]

    def test_the_failure_detail_is_redacted(self) -> None:
        built = failure(detail="auth failed with ghp_aaaaaaaaaaaaaaaaaaaaaaaa")
        assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaa" not in built.detail

    def test_redaction_is_idempotent_so_round_tripping_is_stable(self) -> None:
        built = result(summary="token ghp_aaaaaaaaaaaaaaaaaaaaaaaa")
        assert AgentRunResult.from_canonical_json(built.to_canonical_json()) == built

    def test_no_secret_survives_into_the_serialized_form(self) -> None:
        built = result(
            summary="ghp_aaaaaaaaaaaaaaaaaaaaaaaa",
            status=RunStatus.FAILED,
            failure=failure(detail="ghp_bbbbbbbbbbbbbbbbbbbbbbbb"),
            artifacts=(
                ArtifactReference(
                    kind=ArtifactKind.STDOUT, path="/tmp/ghp_cccccccccccccccccccccccc/out.txt"
                ),
            ),
        )
        serialized = built.to_canonical_json()
        assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaa" not in serialized
        assert "ghp_bbbbbbbbbbbbbbbbbbbbbbbb" not in serialized
        assert "ghp_cccccccccccccccccccccccc" not in serialized


class TestChangedFileNormalization:
    def test_changed_files_are_sorted_and_deduplicated(self) -> None:
        assert result(changed_files=("b.py", "a.py", "b.py")).changed_files == ("a.py", "b.py")

    def test_normalization_is_idempotent(self) -> None:
        once = result(changed_files=("b.py", "a.py"))
        assert result(changed_files=once.changed_files).changed_files == once.changed_files

    def test_tests_run_order_is_preserved_because_order_is_information(self) -> None:
        assert result(tests_run=("ruff", "pytest", "black")).tests_run == (
            "ruff",
            "pytest",
            "black",
        )

    def test_assumption_order_is_preserved(self) -> None:
        built = result(status=RunStatus.COMPLETED_WITH_ASSUMPTIONS, assumptions=("second", "first"))
        assert built.assumptions == ("second", "first")


# ---------------------------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------------------------


class TestSerialization:
    def test_round_trip_preserves_equality(self) -> None:
        built = result(
            status=RunStatus.FAILED,
            failure=failure(timed_out=False, provider=ProviderKind.CLAUDE_CLI),
            assumptions=("a",),
            blocking_issues=("b",),
            changed_files=("docs/a.md",),
            tests_run=("pytest",),
            artifacts=(ArtifactReference(kind=ArtifactKind.STDOUT, path="/tmp/s/stdout.txt"),),
            exit_code=1,
            final_verdict=ProviderVerdict.FAIL,
            recommended_next_state=WorkflowState.REPAIRING,
        )
        assert AgentRunResult.from_canonical_json(built.to_canonical_json()) == built

    def test_serialization_is_byte_stable_across_repeated_calls(self) -> None:
        built = result()
        assert built.to_canonical_json() == built.to_canonical_json()

    def test_serialization_is_byte_stable_across_a_round_trip(self) -> None:
        text = result(changed_files=("b.py", "a.py")).to_canonical_json()
        assert AgentRunResult.from_canonical_json(text).to_canonical_json() == text

    def test_keys_are_sorted_so_the_bytes_do_not_depend_on_field_order(self) -> None:
        keys = list(json.loads(result().to_canonical_json()))
        assert keys == sorted(keys)

    def test_timestamps_serialize_with_their_offset(self) -> None:
        payload = json.loads(result().to_canonical_json())
        assert payload["started_at"].endswith("Z")
        assert AgentRunResult.from_canonical_json(result().to_canonical_json()).started_at == START

    def test_enums_serialize_as_their_string_values(self) -> None:
        payload = json.loads(result(agent=AgentKind.QA).to_canonical_json())
        assert payload["status"] == "completed"
        assert payload["provider"] == "claude_cli"
        assert payload["agent"] == "qa"
        assert payload["mode"] == "provider_invocation"

    def test_duplicate_keys_are_rejected_rather_than_silently_resolved(self) -> None:
        text = result().to_canonical_json()
        doubled = text.replace('"summary":"did the thing"', '"summary":"a","summary":"b"', 1)
        with pytest.raises(ValueError, match="duplicate key"):
            AgentRunResult.from_canonical_json(doubled)

    def test_unknown_fields_are_rejected_on_parse(self) -> None:
        payload = json.loads(result().to_canonical_json())
        payload["authorized"] = True
        with pytest.raises(ValidationError):
            AgentRunResult.from_canonical_json(json.dumps(payload))

    def test_invariants_are_re_checked_on_parse(self) -> None:
        payload = json.loads(result().to_canonical_json())
        payload["status"] = "blocked"
        with pytest.raises(ValidationError, match="at least one blocking issue"):
            AgentRunResult.from_canonical_json(json.dumps(payload))

    def test_a_tampered_duration_does_not_load(self) -> None:
        payload = json.loads(result().to_canonical_json())
        payload["duration_seconds"] = 0.1
        with pytest.raises(ValidationError, match="contradicts the interval"):
            AgentRunResult.from_canonical_json(json.dumps(payload))

    def test_nested_artifact_references_round_trip(self) -> None:
        built = result(
            artifacts=(
                ArtifactReference(kind=ArtifactKind.STDOUT, path="/tmp/s/stdout.txt"),
                ArtifactReference(kind=ArtifactKind.STDERR, path="/tmp/s/stderr.txt"),
            )
        )
        parsed = AgentRunResult.from_canonical_json(built.to_canonical_json())
        assert [(a.kind, a.path) for a in parsed.artifacts] == [
            (ArtifactKind.STDOUT, "/tmp/s/stdout.txt"),
            (ArtifactKind.STDERR, "/tmp/s/stderr.txt"),
        ]


# ---------------------------------------------------------------------------------------------
# Failure preservation
# ---------------------------------------------------------------------------------------------


class TestFailurePreservation:
    @pytest.mark.parametrize("kind", list(ProviderFailureKind))
    def test_every_provider_failure_kind_survives_unchanged(
        self, kind: ProviderFailureKind
    ) -> None:
        projected = RunFailure.from_provider_failure(
            ProviderFailure(
                provider=ProviderKind.CODEX_CLI,
                kind=kind,
                detail="something went wrong",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
            )
        )
        assert projected.kind is kind
        assert projected.provider is ProviderKind.CODEX_CLI

    @pytest.mark.parametrize("classification", list(RetryClassification))
    def test_retryability_and_side_effect_certainty_survive(
        self, classification: RetryClassification
    ) -> None:
        projected = RunFailure.from_provider_failure(
            ProviderFailure(
                provider=ProviderKind.CLAUDE_CLI,
                kind=ProviderFailureKind.COMMAND_FAILED,
                detail="exited 1",
                retry_classification=classification,
            )
        )
        assert projected.retry_classification is classification

    def test_a_failure_is_never_flattened_into_a_string(self) -> None:
        assert AgentRunResult.model_fields["failure"].annotation == RunFailure | None

    def test_timeout_is_classified_from_the_kind(self) -> None:
        projected = RunFailure.from_provider_failure(
            ProviderFailure(
                provider=ProviderKind.CLAUDE_CLI,
                kind=ProviderFailureKind.TIMEOUT,
                detail="claude_cli exceeded its 5s timeout",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
            )
        )
        assert projected.timed_out

    def test_timeout_is_classified_from_the_execution_record_too(self) -> None:
        execution = CommandExecution(
            normalized_command_identity="claude_cli",
            start_time=START,
            completion_time=FINISH,
            exit_code=None,
            timeout_status=True,
            outcome=CommandOutcome.TIMED_OUT,
            stdout="",
            stderr="",
        )
        projected = RunFailure.from_provider_failure(
            ProviderFailure(
                provider=ProviderKind.CLAUDE_CLI,
                kind=ProviderFailureKind.COMMAND_FAILED,
                detail="terminated",
                execution=execution,
            )
        )
        assert projected.timed_out

    def test_a_timeout_failure_claiming_it_did_not_time_out_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must record timed_out"):
            RunFailure(
                kind=ProviderFailureKind.TIMEOUT,
                detail="x",
                retry_classification=RetryClassification.NON_RETRYABLE,
                timed_out=False,
            )

    def test_an_ordinary_failure_is_not_marked_as_an_output_limit_breach(self) -> None:
        assert not RunFailure.from_provider_failure(
            ProviderFailure(
                provider=ProviderKind.CLAUDE_CLI,
                kind=ProviderFailureKind.MALFORMED_OUTPUT,
                detail="report was not valid JSON",
            )
        ).output_limit_exceeded

    def test_the_failure_carries_no_captured_output(self) -> None:
        """The classification survives; the bytes do not. Embedding an execution record would put
        unbounded captured output inside a result meant to be stored and compared."""
        assert set(RunFailure.model_fields) == {
            "kind",
            "detail",
            "retry_classification",
            "provider",
            "timed_out",
            "output_limit_exceeded",
        }


# ---------------------------------------------------------------------------------------------
# Compatibility with the AUTO-010 Provider Runtime
# ---------------------------------------------------------------------------------------------


def run(tmp_path: Path, **config_kwargs: Any) -> ProviderRunResult:
    runtime = ProviderRuntime(config_for(tmp_path, **config_kwargs))
    return runtime.invoke(request_for(tmp_path))


def run_codex(tmp_path: Path, **config_kwargs: Any) -> ProviderRunResult:
    runtime = ProviderRuntime(config_for(tmp_path, **config_kwargs))
    return runtime.invoke(request_for(tmp_path, target=ProviderRuntimeTarget.CODEX))


def adapted(provider_result: ProviderRunResult, **kwargs: Any) -> AgentRunResult:
    return agent_run_result_from_provider_run(provider_result, workflow_id="wf-1", **kwargs)


class TestProviderAdapterCompatibility:
    def test_a_completed_claude_run_maps_field_for_field(self, tmp_path: Path) -> None:
        provider_result = run(tmp_path, claude=claude_stub(tmp_path, COMPLETED_REPORT))
        canonical = adapted(provider_result)

        assert canonical.status is provider_result.status is RunStatus.COMPLETED
        assert canonical.summary == provider_result.summary == "did the thing"
        assert canonical.provider is ProviderKind.CLAUDE_CLI
        assert canonical.session_id == provider_result.session_id
        assert canonical.started_at == provider_result.started_at
        assert canonical.completed_at == provider_result.completed_at
        assert canonical.exit_code == provider_result.exit_code
        assert canonical.changed_files == ("docs/a.md",)
        assert canonical.tests_run == ("pytest",)
        assert canonical.final_verdict is ProviderVerdict.PASS
        assert canonical.workflow_id == "wf-1"
        assert canonical.mode is ExecutionMode.PROVIDER_INVOCATION

    def test_a_completed_codex_run_maps_field_for_field(self, tmp_path: Path) -> None:
        codex_result = run_codex(tmp_path, codex=codex_stub(tmp_path, COMPLETED_REPORT))
        canonical = adapted(codex_result)

        assert canonical.provider is ProviderKind.CODEX_CLI
        assert canonical.status is codex_result.status is RunStatus.COMPLETED
        assert canonical.summary == codex_result.summary
        assert canonical.session_id == codex_result.session_id
        assert canonical.final_verdict is ProviderVerdict.PASS
        assert canonical.changed_files == ("docs/a.md",)
        assert canonical.tests_run == ("pytest",)

    def test_a_blocked_run_keeps_its_blocking_issues(self, tmp_path: Path) -> None:
        report = {
            **COMPLETED_REPORT,
            "status": "blocked",
            "verdict": "fail",
            "summary": "cannot proceed",
            "blocking_issues": ["no stage contract at the configured path"],
        }
        canonical = adapted(run(tmp_path, claude=claude_stub(tmp_path, report)))

        assert canonical.status is RunStatus.BLOCKED
        assert canonical.blocking_issues == ("no stage contract at the configured path",)
        assert canonical.failure is None
        assert not canonical.succeeded

    def test_a_completed_with_assumptions_run_keeps_its_assumptions(self, tmp_path: Path) -> None:
        report = {
            **COMPLETED_REPORT,
            "status": "completed_with_assumptions",
            "assumptions": ["assumed docs/ was the intended target"],
        }
        canonical = adapted(run(tmp_path, claude=claude_stub(tmp_path, report)))

        assert canonical.status is RunStatus.COMPLETED_WITH_ASSUMPTIONS
        assert canonical.assumptions == ("assumed docs/ was the intended target",)
        assert canonical.succeeded

    def test_a_provider_reported_failure_keeps_its_typed_kind(self, tmp_path: Path) -> None:
        report = {**COMPLETED_REPORT, "status": "failed", "verdict": "fail", "summary": "broke"}
        provider_result = run(tmp_path, claude=claude_stub(tmp_path, report))
        canonical = adapted(provider_result)

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.kind is ProviderFailureKind.PROVIDER_REPORTED
        assert provider_result.failure is not None
        assert canonical.failure.kind is provider_result.failure.kind

    def test_a_spawn_failure_maps_with_its_classification(self, tmp_path: Path) -> None:
        provider_result = run(tmp_path, claude=tmp_path / "does-not-exist")
        canonical = adapted(provider_result)

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.kind is ProviderFailureKind.SPAWN_FAILED
        assert canonical.exit_code is None
        # AUTO-010 still records an execution for a failed spawn, so the empty stdout/stderr it
        # persisted are referenced here. The adapter reports what the runtime produced rather than
        # deciding for itself that a spawn failure has no evidence worth pointing at.
        assert {artifact.kind for artifact in canonical.artifacts} == {
            ArtifactKind.STDOUT,
            ArtifactKind.STDERR,
        }

    def test_a_malformed_report_maps_as_a_contract_violation(self, tmp_path: Path) -> None:
        provider_result = run(tmp_path, claude=claude_stub(tmp_path, "not json at all"))
        canonical = adapted(provider_result)

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.kind is ProviderFailureKind.MALFORMED_OUTPUT

    def test_a_report_omitting_status_maps_as_failed(self, tmp_path: Path) -> None:
        report = {k: v for k, v in COMPLETED_REPORT.items() if k != "status"}
        canonical = adapted(run(tmp_path, claude=claude_stub(tmp_path, report)))

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.kind is ProviderFailureKind.MALFORMED_OUTPUT

    def test_a_timeout_maps_with_timed_out_recorded(self, tmp_path: Path) -> None:
        slow = stub(tmp_path, "claude", "sys.stdin.read()\nimport time\ntime.sleep(30)")
        canonical = adapted(run(tmp_path, claude=slow, timeout_seconds=1))

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.kind is ProviderFailureKind.TIMEOUT
        assert canonical.failure.timed_out
        assert canonical.exit_code is None

    def test_an_oversized_stdout_breach_is_classified_as_an_output_limit(
        self, tmp_path: Path
    ) -> None:
        """Provoked through the real process runner, so this pins the canonical classification
        against whatever `providers/base.py` actually reports rather than against a copy of its
        wording rebuilt here."""
        noisy = stub(
            tmp_path,
            "claude",
            "sys.stdin.read()\n"
            f"sys.stdout.buffer.write(b' ' * ({MAX_PROVIDER_STDOUT_BYTES} + 1))\n"
            "sys.stdout.buffer.flush()\n",
        )
        canonical = adapted(run(tmp_path, claude=noisy, timeout_seconds=30))

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.output_limit_exceeded

    def test_an_oversized_stderr_breach_is_classified_as_an_output_limit(
        self, tmp_path: Path
    ) -> None:
        noisy = stub(
            tmp_path,
            "claude",
            "sys.stdin.read()\n"
            f"sys.stderr.buffer.write(b'x' * ({MAX_PROVIDER_STDERR_BYTES} + 1))\n"
            "sys.stderr.buffer.flush()\n"
            "print(json.dumps({'result': json.dumps("
            "{'status': 'completed', 'verdict': 'pass', 'summary': 'ok'})}))",
        )
        canonical = adapted(run(tmp_path, claude=noisy, timeout_seconds=30))

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.output_limit_exceeded

    def test_persisted_output_becomes_artifact_references(self, tmp_path: Path) -> None:
        provider_result = run(tmp_path, claude=claude_stub(tmp_path, COMPLETED_REPORT))
        canonical = adapted(provider_result, session_directory=Path(tmp_path / "sessions"))

        by_kind = {artifact.kind: artifact.path for artifact in canonical.artifacts}
        assert by_kind[ArtifactKind.STDOUT] == str(provider_result.stdout_artifact)
        assert by_kind[ArtifactKind.STDERR] == str(provider_result.stderr_artifact)
        assert by_kind[ArtifactKind.SESSION_DIRECTORY] == str(tmp_path / "sessions")

    def test_the_adapter_never_infers_a_next_state(self, tmp_path: Path) -> None:
        for report in (
            COMPLETED_REPORT,
            {**COMPLETED_REPORT, "status": "blocked", "blocking_issues": ["x"]},
            {**COMPLETED_REPORT, "status": "failed"},
        ):
            canonical = adapted(run(tmp_path, claude=claude_stub(tmp_path, report)))
            assert canonical.recommended_next_state is None

    def test_absent_report_claims_stay_absent_rather_than_becoming_empty_claims(
        self, tmp_path: Path
    ) -> None:
        provider_result = run(tmp_path, claude=tmp_path / "does-not-exist")
        canonical = adapted(provider_result)

        assert provider_result.report is None
        assert canonical.changed_files == ()
        assert canonical.tests_run == ()
        assert canonical.final_verdict is None

    def test_the_mode_and_agent_are_the_callers_to_state(self, tmp_path: Path) -> None:
        canonical = adapted(
            run(tmp_path, claude=claude_stub(tmp_path, COMPLETED_REPORT)),
            mode=ExecutionMode.REVIEW,
            agent=AgentKind.QA,
        )
        assert canonical.mode is ExecutionMode.REVIEW
        assert canonical.agent is AgentKind.QA

    def test_every_adapted_result_serializes_and_round_trips(self, tmp_path: Path) -> None:
        for name, report in (
            ("completed", COMPLETED_REPORT),
            ("blocked", {**COMPLETED_REPORT, "status": "blocked", "blocking_issues": ["x"]}),
            ("failed", {**COMPLETED_REPORT, "status": "failed"}),
            (
                "assumed",
                {**COMPLETED_REPORT, "status": "completed_with_assumptions", "assumptions": ["a"]},
            ),
        ):
            canonical = adapted(run(tmp_path, claude=claude_stub(tmp_path, report, name=name)))
            assert AgentRunResult.from_canonical_json(canonical.to_canonical_json()) == canonical

    def test_a_contradictory_completed_result_is_recorded_not_silently_dropped(self) -> None:
        """AUTO-010 permits `COMPLETED` alongside blocking issues (deferred finding D-8); the
        canonical contract does not. The adapter records the contradiction as the output-contract
        violation it is, and loses neither the summary nor the blockers."""
        contradictory = ProviderRunResult(
            provider=ProviderKind.CLAUDE_CLI,
            status=ProviderRunStatus.COMPLETED,
            summary="finished",
            session_id="wf-1/claude_cli/inv-1",
            started_at=START,
            completed_at=FINISH,
            exit_code=0,
            stdout_artifact=None,
            stderr_artifact=None,
            assumptions=(),
            blocking_issues=("but something stopped me",),
            failure=None,
        )
        canonical = adapted(contradictory)

        assert canonical.status is RunStatus.FAILED
        assert canonical.failure is not None
        assert canonical.failure.kind is ProviderFailureKind.MALFORMED_OUTPUT
        assert "but something stopped me" in canonical.failure.detail
        assert canonical.blocking_issues == ("but something stopped me",)
        assert canonical.summary == "finished"


class TestLiveShapedOutputsMap:
    """The exact report payloads the live Claude and Codex suites assert against, mapped through
    the real runtime and the adapter. Not a live test — it proves the canonical projection handles
    the shapes real CLIs were observed to produce."""

    CLAUDE_LIVE: ClassVar[dict[str, Any]] = {
        "status": "completed",
        "verdict": "pass",
        "summary": "Created the requested file.",
        "assumptions": [],
        "blocking_issues": [],
        "files_changed": ["auto-010-live.txt"],
        "validation_performed": ["ls"],
        "findings": [],
    }
    CODEX_LIVE: ClassVar[dict[str, Any]] = {
        "status": "blocked",
        "verdict": "fail",
        "summary": "Attempted to create the file but every write was rejected.",
        "assumptions": [],
        "blocking_issues": ["Three apply_patch attempts failed; the sandbox rejected each write."],
        "files_changed": [],
        "validation_performed": ["git status"],
        "findings": [],
    }

    def test_a_real_shaped_claude_report_maps(self, tmp_path: Path) -> None:
        canonical = adapted(run(tmp_path, claude=claude_stub(tmp_path, self.CLAUDE_LIVE)))
        assert canonical.status is RunStatus.COMPLETED
        assert canonical.changed_files == ("auto-010-live.txt",)
        assert canonical.tests_run == ("ls",)
        assert canonical.final_verdict is ProviderVerdict.PASS

    def test_a_real_shaped_codex_blocked_report_maps(self, tmp_path: Path) -> None:
        canonical = adapted(run_codex(tmp_path, codex=codex_stub(tmp_path, self.CODEX_LIVE)))

        assert canonical.status is RunStatus.BLOCKED
        assert canonical.blocking_issues == (
            "Three apply_patch attempts failed; the sandbox rejected each write.",
        )
        assert canonical.final_verdict is ProviderVerdict.FAIL
        assert not canonical.succeeded


# ---------------------------------------------------------------------------------------------
# Authority boundaries
# ---------------------------------------------------------------------------------------------


class TestAuthorityBoundaries:
    """`recommended_next_state` is advisory. These tests are the proof, and they are deliberately
    structural: a comment saying a field is advisory is worth nothing if some transition path reads
    it."""

    def test_the_engine_never_reads_recommended_next_state(self) -> None:
        source = Path("agentos_workflow/orchestrator/engine.py").read_text(encoding="utf-8")
        assert "recommended_next_state" not in source

    def test_no_module_outside_the_result_contract_reads_the_field(self) -> None:
        offenders = [
            path
            for path in Path("agentos_workflow").rglob("*.py")
            if "tests" not in path.parts
            and path.name != "results.py"
            and "recommended_next_state" in path.read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_the_result_module_imports_no_transition_machinery(self) -> None:
        """It may name `WorkflowState` — a vocabulary — but must not hold anything that can append
        a transition, take a lock, or run a workflow."""
        tree = ast.parse(Path("agentos_workflow/results.py").read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        forbidden = {
            "StateStore",
            "RepositoryLock",
            "WorkflowSession",
            "WorkflowStateMachine",
            "ResumedWorkflow",
            "AuthorizationRecord",
            "StateTransitionRecord",
        }
        assert imported & forbidden == set()
        assert "WorkflowState" in imported

    def test_the_result_module_spawns_nothing_and_touches_no_repository(self) -> None:
        tree = ast.parse(Path("agentos_workflow/results.py").read_text(encoding="utf-8"))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        forbidden = {
            "Popen",
            "run",
            "call",
            "check_output",
            "spawn",
            "system",
            "write_text",
            "write_bytes",
            "mkdir",
            "unlink",
            "rename",
            "append_transition",
            "invoke",
        }
        assert called & forbidden == set()

    def test_constructing_a_result_transitions_nothing(self, tmp_path: Path) -> None:
        """A result naming a next state is inert: building it and serializing it produces no
        persisted state anywhere."""
        state_directory = tmp_path / "state"
        built = result(recommended_next_state=WorkflowState.READY_TO_COMMIT)
        built.to_canonical_json()
        AgentRunResult.from_canonical_json(built.to_canonical_json())

        assert built.recommended_next_state is WorkflowState.READY_TO_COMMIT
        assert not state_directory.exists()

    def test_a_result_cannot_grant_authorization(self) -> None:
        """`AUTHORIZED` is expressible as advice — refusing to let a producer *say* it would be a
        different, weaker claim — but nothing consumes it, which is the property that matters."""
        built = result(recommended_next_state=WorkflowState.AUTHORIZED)
        assert built.recommended_next_state is WorkflowState.AUTHORIZED
        assert not hasattr(built, "authorize")
        assert not any(
            name in dir(built) for name in ("transition", "apply", "commit", "advance", "approve")
        )

    def test_the_result_exposes_no_callable_that_acts(self) -> None:
        """Everything this type adds is serialization. The inherited Pydantic API is excluded
        because it is Pydantic's surface, not this contract's — what matters is that nothing here
        executes, transitions, or approves anything."""
        own = {
            name
            for name, value in vars(AgentRunResult).items()
            if not name.startswith("_") and callable(getattr(value, "__func__", value))
        }
        assert own == {"from_canonical_json", "to_canonical_json"}

        forbidden = {
            "authorize",
            "approve",
            "reject",
            "transition",
            "transition_to",
            "advance",
            "apply",
            "commit",
            "push",
            "merge",
            "start",
            "resume",
            "cancel",
            "invoke",
            "run",
            "execute",
        }
        assert forbidden & set(dir(AgentRunResult)) == set()

    def test_no_result_can_invoke_a_skill_or_provider(self) -> None:
        """Asserted over the parsed syntax tree, not the source text: this module's docstring
        discusses the Provider Runtime at length, and prose about an executor is not an executor —
        the same distinction AUTO-010 had to make about subprocesses."""
        tree = ast.parse(Path("agentos_workflow/results.py").read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        executors = {"ProviderRuntime", "select_live_provider", "SkillResult", "CLIProvider"}
        assert (names | imported) & executors == set()

    def test_the_advisory_field_is_not_required_and_defaults_to_absent(self) -> None:
        assert result().recommended_next_state is None
        assert AgentRunResult.model_fields["recommended_next_state"].default is None

    def test_state_transitions_still_come_only_from_the_allowed_transition_table(self) -> None:
        """The transition table is what decides a move, and it is untouched by this stage: it names
        pairs of states and knows nothing about results."""
        transitions = engine_module.ALLOWED_TRANSITIONS
        assert (WorkflowState.CREATED, WorkflowState.AUTHORIZED) in transitions
        assert len(transitions) == 37
        for source_state, target_state in transitions:
            assert isinstance(source_state, WorkflowState)
            assert isinstance(target_state, WorkflowState)


# ---------------------------------------------------------------------------------------------
# Nothing existing changed
# ---------------------------------------------------------------------------------------------


class TestExistingBehaviourUnchanged:
    def test_provider_run_result_keeps_its_own_invariants(self) -> None:
        """AUTO-010's boundary type is untouched: same fields, same rules."""
        common: dict[str, Any] = {
            "provider": ProviderKind.CLAUDE_CLI,
            "summary": "s",
            "session_id": "wf/claude_cli/inv",
            "started_at": START,
            "completed_at": FINISH,
            "exit_code": 0,
            "stdout_artifact": None,
            "stderr_artifact": None,
        }
        with pytest.raises(ValueError, match="blocking issue"):
            ProviderRunResult(
                status=ProviderRunStatus.BLOCKED,
                assumptions=(),
                blocking_issues=(),
                failure=None,
                **common,
            )
        assert ProviderRunResult(
            status=ProviderRunStatus.COMPLETED,
            assumptions=(),
            blocking_issues=(),
            failure=None,
            **common,
        ).succeeded

    def test_provider_report_still_carries_both_outcome_axes(self) -> None:
        """Deferred finding D-3 is deferred, not resolved: `verdict` and `status` both remain on
        `ProviderReport`, and this stage removed neither."""
        report = ProviderReport(
            provider=ProviderKind.CLAUDE_CLI,
            role=ProviderRole.IMPLEMENTATION,
            verdict=ProviderVerdict.PASS,
            summary="s",
            status=ProviderRunStatus.COMPLETED,
        )
        assert report.verdict is ProviderVerdict.PASS
        assert report.status is ProviderRunStatus.COMPLETED

    def test_the_legacy_agent_report_is_untouched(self) -> None:
        from ai_workflow_engine.agents.models import AgentReport

        assert set(AgentReport.model_fields) == {
            "schema_version",
            "task_id",
            "stage",
            "prompt_id",
            "verdict",
            "summary",
            "findings",
            "changed_paths",
            "verification_commands_run",
            "blockers",
        }

    def test_the_workflow_service_surface_did_not_grow(self) -> None:
        from agentos_workflow.service import WorkflowService

        public = {name for name in vars(WorkflowService) if not name.startswith("_")}
        assert public == {"status", "list", "audit", "report", "invoke_provider"}

    def test_the_canonical_module_adds_no_cli_command(self) -> None:
        source = Path("agentos_workflow/cli_auto.py").read_text(encoding="utf-8")
        assert "results" not in source
        assert "AgentRunResult" not in source
