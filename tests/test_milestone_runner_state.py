"""AUTO-016 sections 10, 11, 14, 17, 19 and 22: the run state machine and the typed vocabulary.

The state-machine half asserts `ALLOWED_RUN_TRANSITIONS` member-by-member against a table
transcribed independently below, so an accidental widening of the production frozenset fails
here rather than being ratified by a test that imports the very thing it checks. The model half
asserts that each contract invariant this milestone owns is unrepresentable rather than merely
unlikely: an unknown field raises, a fabricated pass cannot be constructed, a traversal-shaped
path is refused instead of resolved, and the five counters of section 19 are five distinct
fields.

Section 7's promise -- that AUTO-016 adds no `WorkflowState` member and no `ALLOWED_TRANSITIONS`
edge -- is checked by parsing `agentos_workflow/orchestrator/engine.py` rather than importing it.
Reading the authoritative source proves the same 19/37 counts while honouring this milestone's
own rule that `agentos_workflow` is never imported from AUTO-016's work.
"""

import ast
import hashlib
import itertools
import json
import os
import re
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_workflow_engine.milestone_runner import plan as plan_module
from ai_workflow_engine.milestone_runner.git_inspect import (
    GitReadOnlyInspector,
    RepositoryEvidence,
    derive_repository_identity,
)
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    ALLOWED_RUN_TRANSITIONS,
    BLOCKING_SEVERITIES,
    DEFERRED_SEVERITIES,
    DIGEST_EXCLUDED_FIELDS,
    PLAN_SCHEMA_VERSION,
    RETRYABLE_PROVIDER_FAILURE_CLASSES,
    RUN_COUNTER_FIELDS,
    STATE_SCHEMA_VERSION,
    TERMINAL_RUN_STATES,
    UNREADABLE_DIGEST,
    ApprovalOperation,
    ApprovalRecord,
    Finding,
    FindingSeverity,
    FindingStatus,
    FocusedVerificationCommand,
    MilestoneCheckpoint,
    MilestoneSpec,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
    RecoveryCommand,
    RecoveryLedgerEntry,
    ReviewVerdict,
    RunRecord,
    RunStatus,
    StopReason,
    VerificationResult,
    canonical_digest,
    normalize_repository_path,
)
from ai_workflow_engine.milestone_runner.state import (
    ABSENT_DIGEST,
    MAX_TRANSCRIPT_SEQUENCE,
    PROVIDER_INTENT_FILE_NAME,
    STATE_FILE_NAME,
    TEMP_FILE_PREFIX,
    TRANSCRIPT_SEQUENCE_FILE_NAME,
    TRANSCRIPTS_DIRECTORY,
    ProviderInvocationIntent,
    RedactedWrite,
    RepositoryFingerprint,
    ResumeAction,
    ResumeRefused,
    RunStateStore,
    StateCorrupted,
    StatePublicationFailure,
    StateRootRefused,
    StateSchemaUnknown,
    TranscriptKind,
    artifact_root_for,
    canonical_repository_id,
    digest_repository_path,
    fingerprint_delta,
    fingerprint_repository,
    next_transcript_sequence,
    publish_atomically,
    reject_repository_containment,
    reject_symlink_components,
    transcript_name,
    write_redacted_artifact,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODELS_SOURCE = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner" / "models.py"
PACKAGE_INIT = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner" / "__init__.py"
CANONICAL_ENGINE_SOURCE = REPOSITORY_ROOT / "agentos_workflow" / "orchestrator" / "engine.py"


# --------------------------------------------------------------------------------------
# Fixtures: real, fully-populated records -- no mock stands in for a model under test
# --------------------------------------------------------------------------------------

VALID_MILESTONE: dict[str, Any] = {
    "schema_version": PLAN_SCHEMA_VERSION,
    "milestone_id": "AUTO-016-M01",
    "title": "Package marker, typed models, run-state machine",
    "objective": "Establish the package root and the typed vocabulary later milestones need.",
    "depends_on": [],
    "contract_sections": ["section 8 package and module surface"],
    "allowed_files": ["src/ai_workflow_engine/milestone_runner/models.py"],
    "forbidden_files": ["agentos_workflow/**"],
    "required_symbols": ["milestone_runner.models.RunStatus"],
    "explicit_exclusions": ["No I/O of any kind."],
    "acceptance_criteria": ["RunStatus contains exactly the eighteen section 10 states."],
    "focused_verification": [{"command": ["pytest", "-q"], "purpose": "state machine tests"}],
    "completion_evidence": ["All focused verification commands PASS."],
}

REQUIRED_MILESTONE_FIELDS = frozenset(
    {
        "schema_version",
        "milestone_id",
        "title",
        "objective",
        "depends_on",
        "contract_sections",
        "allowed_files",
        "forbidden_files",
        "required_symbols",
        "explicit_exclusions",
        "acceptance_criteria",
        "focused_verification",
        "completion_evidence",
    }
)

OPTIONAL_MILESTONE_FIELDS = frozenset({"additive_reuse_justification", "human_owner_scope_ruling"})


def provider_run(sequence: int = 1) -> ProviderRunRecord:
    return ProviderRunRecord(
        sequence=sequence,
        role=ProviderRole.IMPLEMENTATION,
        provider="claude",
        milestone_id="AUTO-016-M01",
        started_at="2026-08-05T21:00:00Z",
        completed_at="2026-08-05T21:17:02Z",
        duration_ms=1_022_000,
        exit_code=0,
        prompt_path=f"transcripts/{sequence:04d}-implementation.prompt.md",
        stdout_path=f"transcripts/{sequence:04d}-implementation.stdout.txt",
        stderr_path=f"transcripts/{sequence:04d}-implementation.stderr.txt",
    )


def passing_verification() -> VerificationResult:
    return VerificationResult(
        command=["pytest", "-q", "tests/test_milestone_runner_state.py"],
        exit_code=0,
        timed_out=False,
        passed=True,
        duration_ms=4_210,
        stdout_path="verification/0001.stdout.txt",
        stderr_path="verification/0001.stderr.txt",
    )


def run_record(**overrides: Any) -> RunRecord:
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": "auto016-20260805T213855Z-7fea75fc",
        "repository_root": "/home/owner/ai-workflow-engine",
        "repository_identity": "ai-workflow-engine-0123456789ab",
        "expected_branch": "feature/auto-016-milestone-runner",
        "baseline_sha": "4fa9212ff47171c162ddf863360413a90e0ee79f",
        "contract_sha256": "56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e",
        "workflow_state": RunStatus.IMPLEMENTING,
        "created_at": "2026-08-05T21:38:55Z",
        "updated_at": "2026-08-05T21:40:01Z",
        "current_milestone": "AUTO-016-M01",
    }
    payload.update(overrides)
    return RunRecord(**payload)


def approval(**overrides: Any) -> ApprovalRecord:
    payload: dict[str, Any] = {
        "operation": ApprovalOperation.COMMIT,
        "granted_at": "2026-08-05T22:00:00Z",
        "repository_identity": "ai-workflow-engine-0123456789ab",
        "branch": "feature/auto-016-milestone-runner",
        "baseline_sha": "4fa9212ff47171c162ddf863360413a90e0ee79f",
        "head_sha": "4fa9212ff47171c162ddf863360413a90e0ee79f",
        "changed_paths": ["src/ai_workflow_engine/milestone_runner/models.py"],
        "changed_path_digests": {
            "src/ai_workflow_engine/milestone_runner/models.py": "0" * 64,
        },
        "verification_digest": "1" * 64,
        "review_verdict": ReviewVerdict.APPROVED,
        "finding_ids": [],
        "human_confirmation_supplied": True,
    }
    payload.update(overrides)
    return ApprovalRecord(**payload)


# --------------------------------------------------------------------------------------
# Section 10 -- the run state machine
# --------------------------------------------------------------------------------------

# Transcribed independently from contract sections 5, 10 and 13 rather than derived from the
# production frozenset, so this table and `ALLOWED_RUN_TRANSITIONS` are two witnesses to one
# claim. The same discipline `agentos_workflow/tests/test_engine.py` applies to
# `ALLOWED_TRANSITIONS`.
LIVE_STATES = (
    RunStatus.PREFLIGHT,
    RunStatus.IMPLEMENTING,
    RunStatus.FOCUSED_VERIFYING,
    RunStatus.MILESTONE_FAILED,
    RunStatus.MILESTONE_COMPLETE,
    RunStatus.FINAL_VERIFYING,
    RunStatus.REVIEWING,
    RunStatus.NEEDS_CORRECTION,
    RunStatus.CORRECTING,
    RunStatus.CLOSURE_VERIFYING,
    RunStatus.PROVIDER_WAIT,
    RunStatus.PROVIDER_RETRY_PENDING,
    RunStatus.READY_FOR_COMMIT_APPROVAL,
    RunStatus.READY_FOR_PUSH_APPROVAL,
)

EXPECTED_RUN_TRANSITIONS: frozenset[tuple[RunStatus, RunStatus]] = frozenset(
    {
        (RunStatus.IDLE, RunStatus.PREFLIGHT),
        (RunStatus.PREFLIGHT, RunStatus.IMPLEMENTING),
        (RunStatus.IMPLEMENTING, RunStatus.FOCUSED_VERIFYING),
        (RunStatus.FOCUSED_VERIFYING, RunStatus.MILESTONE_COMPLETE),
        (RunStatus.FOCUSED_VERIFYING, RunStatus.MILESTONE_FAILED),
        (RunStatus.MILESTONE_COMPLETE, RunStatus.IMPLEMENTING),
        (RunStatus.MILESTONE_COMPLETE, RunStatus.FINAL_VERIFYING),
        (RunStatus.FINAL_VERIFYING, RunStatus.REVIEWING),
        (RunStatus.REVIEWING, RunStatus.NEEDS_CORRECTION),
        (RunStatus.REVIEWING, RunStatus.READY_FOR_COMMIT_APPROVAL),
        (RunStatus.NEEDS_CORRECTION, RunStatus.CORRECTING),
        (RunStatus.CORRECTING, RunStatus.CLOSURE_VERIFYING),
        (RunStatus.CLOSURE_VERIFYING, RunStatus.READY_FOR_COMMIT_APPROVAL),
        (RunStatus.READY_FOR_COMMIT_APPROVAL, RunStatus.READY_FOR_PUSH_APPROVAL),
        (RunStatus.READY_FOR_PUSH_APPROVAL, RunStatus.DONE),
        (RunStatus.IMPLEMENTING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.IMPLEMENTING),
        (RunStatus.REVIEWING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.REVIEWING),
        (RunStatus.CORRECTING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.CORRECTING),
        (RunStatus.CLOSURE_VERIFYING, RunStatus.PROVIDER_WAIT),
        (RunStatus.PROVIDER_WAIT, RunStatus.CLOSURE_VERIFYING),
        (RunStatus.PROVIDER_WAIT, RunStatus.PROVIDER_RETRY_PENDING),
        (RunStatus.PROVIDER_RETRY_PENDING, RunStatus.PROVIDER_WAIT),
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.FOCUSED_VERIFYING),
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.IMPLEMENTING),
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.REVIEWING),
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.CLOSURE_VERIFYING),
        (RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.ABORTED),
        (RunStatus.MILESTONE_FAILED, RunStatus.IMPLEMENTING),
        (RunStatus.IMPLEMENTING, RunStatus.MILESTONE_FAILED),
        *((state, RunStatus.HUMAN_INTERVENTION_REQUIRED) for state in LIVE_STATES),
        *((state, RunStatus.ABORTED) for state in LIVE_STATES),
    }
)


class TestRunStatusVocabulary:
    def test_exactly_the_eighteen_section_ten_states(self) -> None:
        assert [member.value for member in RunStatus] == [
            "IDLE",
            "PREFLIGHT",
            "IMPLEMENTING",
            "FOCUSED_VERIFYING",
            "MILESTONE_FAILED",
            "MILESTONE_COMPLETE",
            "FINAL_VERIFYING",
            "REVIEWING",
            "NEEDS_CORRECTION",
            "CORRECTING",
            "CLOSURE_VERIFYING",
            "PROVIDER_WAIT",
            "PROVIDER_RETRY_PENDING",
            "READY_FOR_COMMIT_APPROVAL",
            "READY_FOR_PUSH_APPROVAL",
            "HUMAN_INTERVENTION_REQUIRED",
            "DONE",
            "ABORTED",
        ]

    def test_the_three_justified_additions_are_present(self) -> None:
        """Section 10's three additions beyond the fifteen the Human Owner's direction names."""
        assert RunStatus.MILESTONE_FAILED in RunStatus
        assert RunStatus.PROVIDER_WAIT in RunStatus
        assert RunStatus.PROVIDER_RETRY_PENDING in RunStatus

    def test_every_member_is_its_own_name(self) -> None:
        for member in RunStatus:
            assert member.value == member.name


class TestAllowedRunTransitions:
    """Section 10: `ALLOWED_RUN_TRANSITIONS` is an explicit, closed frozenset."""

    def test_matches_the_independently_transcribed_table_exactly(self) -> None:
        unexpected = ALLOWED_RUN_TRANSITIONS - EXPECTED_RUN_TRANSITIONS
        missing = EXPECTED_RUN_TRANSITIONS - ALLOWED_RUN_TRANSITIONS
        assert not unexpected, f"undocumented edge(s): {sorted(unexpected)}"
        assert not missing, f"missing edge(s): {sorted(missing)}"

    def test_every_pair_of_states_is_decided_member_by_member(self) -> None:
        """18 x 18 = 324 ordered pairs; every one is either in the table or provably absent."""
        decided = 0
        for source in RunStatus:
            for target in RunStatus:
                expected = (source, target) in EXPECTED_RUN_TRANSITIONS
                assert (
                    (source, target) in ALLOWED_RUN_TRANSITIONS
                ) is expected, f"{source} -> {target}"
                decided += 1
        assert decided == 324

    def test_the_table_is_closed_over_the_enum(self) -> None:
        for source, target in ALLOWED_RUN_TRANSITIONS:
            assert isinstance(source, RunStatus)
            assert isinstance(target, RunStatus)

    def test_no_state_transitions_to_itself(self) -> None:
        for source, target in ALLOWED_RUN_TRANSITIONS:
            assert source is not target, f"{source} has a self-edge"

    def test_the_frozenset_is_immutable(self) -> None:
        assert isinstance(ALLOWED_RUN_TRANSITIONS, frozenset)
        assert isinstance(TERMINAL_RUN_STATES, frozenset)

    def test_section_five_happy_path_is_walkable_end_to_end(self) -> None:
        """The approved runtime flow of section 5, walked edge by edge with no gaps."""
        path = [
            RunStatus.IDLE,
            RunStatus.PREFLIGHT,
            RunStatus.IMPLEMENTING,
            RunStatus.FOCUSED_VERIFYING,
            RunStatus.MILESTONE_COMPLETE,
            RunStatus.FINAL_VERIFYING,
            RunStatus.REVIEWING,
            RunStatus.NEEDS_CORRECTION,
            RunStatus.CORRECTING,
            RunStatus.CLOSURE_VERIFYING,
            RunStatus.READY_FOR_COMMIT_APPROVAL,
            RunStatus.READY_FOR_PUSH_APPROVAL,
            RunStatus.DONE,
        ]
        for source, target in itertools.pairwise(path):
            assert (source, target) in ALLOWED_RUN_TRANSITIONS, f"{source} -> {target}"

    def test_no_edge_skips_the_commit_gate(self) -> None:
        """Nothing reaches `DONE` without passing through both approval gates in order."""
        into_done = {
            source for source, target in ALLOWED_RUN_TRANSITIONS if target is RunStatus.DONE
        }
        assert into_done == {RunStatus.READY_FOR_PUSH_APPROVAL}
        into_push = {
            source
            for source, target in ALLOWED_RUN_TRANSITIONS
            if target is RunStatus.READY_FOR_PUSH_APPROVAL
        }
        assert into_push == {RunStatus.READY_FOR_COMMIT_APPROVAL}

    def test_provider_retry_is_reachable_only_from_the_wait_state(self) -> None:
        """Section 10: retry is entered only on a proven pre-side-effect spawn failure."""
        into_retry = {
            source
            for source, target in ALLOWED_RUN_TRANSITIONS
            if target is RunStatus.PROVIDER_RETRY_PENDING
        }
        assert into_retry == {RunStatus.PROVIDER_WAIT}
        assert RETRYABLE_PROVIDER_FAILURE_CLASSES == frozenset({ProviderFailureClass.SPAWN_FAILED})

    def test_a_failed_milestone_is_reachable_from_both_states_that_can_discover_one(self) -> None:
        """Finding GOV-AUTO-11-F2: an invalid implementation result is read from `IMPLEMENTING`.

        `PROVIDER_WAIT` is an excursion that always returns to its invoking state, so a provider
        failure, an unparseable result block, or a result whose status is not `COMPLETE` is
        discovered while the run sits in `IMPLEMENTING` -- and section 18 says none of those is a
        pass. Without this edge the sole transition authority raises instead of publishing, and a
        deterministic stop becomes an uncaught exception over a run wedged in a state no recovery
        command admits.
        """
        into_failed = {
            source
            for source, target in ALLOWED_RUN_TRANSITIONS
            if target is RunStatus.MILESTONE_FAILED
        }
        assert into_failed == {RunStatus.IMPLEMENTING, RunStatus.FOCUSED_VERIFYING}

    def test_the_new_edge_widens_nothing_else(self) -> None:
        """`MILESTONE_FAILED` still exits only through reopen, the safety stop, or abort."""
        outbound = {
            target
            for source, target in ALLOWED_RUN_TRANSITIONS
            if source is RunStatus.MILESTONE_FAILED
        }
        assert outbound == {
            RunStatus.IMPLEMENTING,
            RunStatus.HUMAN_INTERVENTION_REQUIRED,
            RunStatus.ABORTED,
        }
        assert (RunStatus.MILESTONE_FAILED, RunStatus.MILESTONE_COMPLETE) not in (
            ALLOWED_RUN_TRANSITIONS
        )
        assert (RunStatus.MILESTONE_FAILED, RunStatus.FOCUSED_VERIFYING) not in (
            ALLOWED_RUN_TRANSITIONS
        )


class TestTerminalStatesHaveNoExit:
    """Section 10: terminal states are `DONE` and `ABORTED`; neither has an outbound edge."""

    def test_the_terminal_set_is_exactly_done_and_aborted(self) -> None:
        assert TERMINAL_RUN_STATES == frozenset({RunStatus.DONE, RunStatus.ABORTED})

    @pytest.mark.parametrize("terminal", sorted(TERMINAL_RUN_STATES))
    def test_no_outbound_edge(self, terminal: RunStatus) -> None:
        outbound = [pair for pair in ALLOWED_RUN_TRANSITIONS if pair[0] is terminal]
        assert outbound == [], f"{terminal} must be terminal, found {outbound}"

    @pytest.mark.parametrize("terminal", sorted(TERMINAL_RUN_STATES))
    def test_no_terminal_state_is_reachable_from_itself(self, terminal: RunStatus) -> None:
        assert (terminal, terminal) not in ALLOWED_RUN_TRANSITIONS

    def test_every_other_state_has_at_least_one_outbound_edge(self) -> None:
        sources = {source for source, _ in ALLOWED_RUN_TRANSITIONS}
        assert sources == set(RunStatus) - TERMINAL_RUN_STATES


class TestHumanInterventionExitsOnlyViaRecovery:
    """Section 10: `HUMAN_INTERVENTION_REQUIRED` never exits automatically."""

    def test_outbound_edges_are_exactly_the_recovery_targets_plus_abort(self) -> None:
        outbound = {
            target
            for source, target in ALLOWED_RUN_TRANSITIONS
            if source is RunStatus.HUMAN_INTERVENTION_REQUIRED
        }
        assert outbound == {
            RunStatus.FOCUSED_VERIFYING,  # reconcile-milestone
            RunStatus.IMPLEMENTING,  # reopen-milestone
            RunStatus.REVIEWING,  # recover-failed-review
            RunStatus.CLOSURE_VERIFYING,  # revalidate-correction
            RunStatus.ABORTED,  # abort
        }

    def test_recovery_never_reaches_a_commit_or_push_gate_directly(self) -> None:
        """Section 13: no recovery command may move the run to `READY_FOR_COMMIT_APPROVAL`."""
        assert (
            RunStatus.HUMAN_INTERVENTION_REQUIRED,
            RunStatus.READY_FOR_COMMIT_APPROVAL,
        ) not in ALLOWED_RUN_TRANSITIONS
        assert (
            RunStatus.HUMAN_INTERVENTION_REQUIRED,
            RunStatus.READY_FOR_PUSH_APPROVAL,
        ) not in ALLOWED_RUN_TRANSITIONS
        assert (
            RunStatus.HUMAN_INTERVENTION_REQUIRED,
            RunStatus.DONE,
        ) not in ALLOWED_RUN_TRANSITIONS

    def test_every_live_state_can_reach_the_safety_stop(self) -> None:
        """Section 5: any tripped gate moves the run to `HUMAN_INTERVENTION_REQUIRED`."""
        for state in LIVE_STATES:
            assert (state, RunStatus.HUMAN_INTERVENTION_REQUIRED) in ALLOWED_RUN_TRANSITIONS

    def test_idle_cannot_stop_before_it_has_started(self) -> None:
        stop = (RunStatus.IDLE, RunStatus.HUMAN_INTERVENTION_REQUIRED)
        assert stop not in ALLOWED_RUN_TRANSITIONS
        assert (RunStatus.IDLE, RunStatus.ABORTED) not in ALLOWED_RUN_TRANSITIONS

    def test_a_recovery_ledger_entry_cannot_record_an_illegal_transition(self) -> None:
        with pytest.raises(ValidationError, match="not an allowed run transition"):
            RecoveryLedgerEntry(
                command=RecoveryCommand.RECOVER_FAILED_REVIEW,
                reason="restore the budget a token expiry consumed",
                recorded_at="2026-08-05T22:00:00Z",
                pre_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                post_state=RunStatus.READY_FOR_COMMIT_APPROVAL,
                branch="feature/auto-016-milestone-runner",
                head_sha="4fa9212ff47171c162ddf863360413a90e0ee79f",
            )


class TestNoWorkflowStateExtension:
    """Section 7: no `WorkflowState` member and no `ALLOWED_TRANSITIONS` edge is added.

    The canonical engine module is *parsed*, never imported: this milestone's own boundary keeps
    `agentos_workflow` out of AUTO-016's work entirely, and reading the authoritative source
    proves the counts just as well.
    """

    def canonical_tree(self) -> ast.Module:
        return ast.parse(CANONICAL_ENGINE_SOURCE.read_text(encoding="utf-8"))

    def test_workflow_state_still_has_nineteen_members(self) -> None:
        tree = self.canonical_tree()
        classes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "WorkflowState"
        ]
        assert len(classes) == 1
        members = [
            statement
            for statement in classes[0].body
            if isinstance(statement, ast.Assign | ast.AnnAssign)
        ]
        assert len(members) == 19

    def test_allowed_transitions_still_has_thirty_seven_edges(self) -> None:
        tree = self.canonical_tree()
        edges: list[ast.expr] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign):
                continue
            target = node.target
            if not isinstance(target, ast.Name) or target.id != "ALLOWED_TRANSITIONS":
                continue
            call = node.value
            assert isinstance(call, ast.Call)
            assert isinstance(call.args[0], ast.Set)
            edges = list(call.args[0].elts)
        assert len(edges) == 37
        assert all(isinstance(edge, ast.Tuple) for edge in edges)

    def test_the_runner_defines_no_workflow_state_of_its_own(self) -> None:
        source = MODELS_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        assert "WorkflowState" not in class_names
        assigned = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign | ast.Assign)
            for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
            if isinstance(target, ast.Name)
        }
        assert "ALLOWED_TRANSITIONS" not in assigned
        assert "WORKFLOW_STATES" not in assigned

    def test_the_two_state_vocabularies_share_no_identity(self) -> None:
        """`RunStatus` is a runner-local status, so overlapping *names* are coincidence only."""
        assert RunStatus.__module__ == "ai_workflow_engine.milestone_runner.models"


# --------------------------------------------------------------------------------------
# Section 17 -- the provider failure taxonomy
# --------------------------------------------------------------------------------------


class TestProviderFailureTaxonomy:
    def test_exactly_the_seven_section_seventeen_classes(self) -> None:
        assert {member.value for member in ProviderFailureClass} == {
            "SPAWN_FAILED",
            "TIMEOUT",
            "COMMAND_FAILED",
            "MALFORMED_OUTPUT",
            "AUTH_FAILED",
            "TRANSPORT_FAILED",
            "PROVIDER_REPORTED",
        }
        assert len(ProviderFailureClass) == 7

    def test_only_spawn_failure_is_retryable(self) -> None:
        """Any failure after the process started requires reconciliation, never a blind retry."""
        assert RETRYABLE_PROVIDER_FAILURE_CLASSES == frozenset({ProviderFailureClass.SPAWN_FAILED})
        for member in ProviderFailureClass:
            if member is not ProviderFailureClass.SPAWN_FAILED:
                assert member not in RETRYABLE_PROVIDER_FAILURE_CLASSES

    def test_a_timed_out_invocation_must_be_classified_as_a_timeout(self) -> None:
        with pytest.raises(ValidationError, match="classified TIMEOUT"):
            ProviderRunRecord(
                sequence=1,
                role=ProviderRole.REVIEW,
                provider="codex",
                started_at="2026-08-05T21:00:00Z",
                duration_ms=1,
                timed_out=True,
                failure_class=ProviderFailureClass.COMMAND_FAILED,
                prompt_path="transcripts/0001-review.prompt.md",
                stdout_path="transcripts/0001-review.stdout.txt",
                stderr_path="transcripts/0001-review.stderr.txt",
            )

    def test_stop_reasons_are_exactly_the_codes_the_contract_names(self) -> None:
        assert {member.value for member in StopReason} == {
            "STAGE_ID_NOT_AUTHORIZED",
            "REPOSITORY_IDENTITY_MISMATCH",
            "BRANCH_MISMATCH",
            "HEAD_DRIFT",
            "DIRTY_TREE",
            "PLAN_COVERAGE_MISMATCH",
            "PLAN_PATH_NOT_ALLOWLISTED",
            "GOVERNANCE_CONTRADICTION",
            "INVALID_CONFIGURATION",
            "LOCK_CONTENTION",
            "STATE_SCHEMA_UNKNOWN",
            "OUT_OF_MILESTONE_SCOPE",
        }


# --------------------------------------------------------------------------------------
# Section 14 -- the milestone plan format
# --------------------------------------------------------------------------------------


class TestMilestoneSpec:
    def test_the_valid_milestone_loads(self) -> None:
        spec = MilestoneSpec.model_validate(VALID_MILESTONE)
        assert spec.milestone_id == "AUTO-016-M01"
        assert spec.depends_on == []
        assert spec.focused_verification[0].command == ["pytest", "-q"]

    def test_thirteen_required_fields_and_exactly_two_optional(self) -> None:
        fields = set(MilestoneSpec.model_fields)
        assert fields == REQUIRED_MILESTONE_FIELDS | OPTIONAL_MILESTONE_FIELDS
        assert len(REQUIRED_MILESTONE_FIELDS) == 13
        assert len(OPTIONAL_MILESTONE_FIELDS) == 2
        for name in REQUIRED_MILESTONE_FIELDS:
            assert MilestoneSpec.model_fields[name].is_required(), name
        for name in OPTIONAL_MILESTONE_FIELDS:
            assert not MilestoneSpec.model_fields[name].is_required(), name

    @pytest.mark.parametrize("missing", sorted(REQUIRED_MILESTONE_FIELDS))
    def test_each_required_field_is_actually_required(self, missing: str) -> None:
        payload = {key: value for key, value in VALID_MILESTONE.items() if key != missing}
        with pytest.raises(ValidationError):
            MilestoneSpec.model_validate(payload)

    def test_the_two_optional_fields_are_accepted_when_present(self) -> None:
        spec = MilestoneSpec.model_validate(
            {
                **VALID_MILESTONE,
                "additive_reuse_justification": "Reuses the existing redaction primitive.",
                "human_owner_scope_ruling": "Scope corrected by the Human Owner on 2026-08-05.",
            }
        )
        assert spec.additive_reuse_justification is not None
        assert spec.human_owner_scope_ruling is not None

    def test_an_unknown_field_raises_rather_than_being_ignored(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            MilestoneSpec.model_validate({**VALID_MILESTONE, "allowed_commands": ["rm"]})

    def test_an_unknown_schema_version_is_a_hard_refusal(self) -> None:
        with pytest.raises(ValidationError, match="is unknown"):
            MilestoneSpec.model_validate({**VALID_MILESTONE, "schema_version": 2})

    @pytest.mark.parametrize(
        "identifier",
        ["AUTO-16-M01", "AUTO-016-M1", "auto-016-m01", "AUTO-016", "AUTO-016-M01 ", ""],
    )
    def test_the_milestone_id_grammar_is_closed(self, identifier: str) -> None:
        with pytest.raises(ValidationError):
            MilestoneSpec.model_validate({**VALID_MILESTONE, "milestone_id": identifier})

    def test_a_milestone_cannot_depend_on_itself(self) -> None:
        with pytest.raises(ValidationError, match="must not depend on itself"):
            MilestoneSpec.model_validate({**VALID_MILESTONE, "depends_on": ["AUTO-016-M01"]})

    def test_a_duplicate_dependency_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            MilestoneSpec.model_validate(
                {**VALID_MILESTONE, "depends_on": ["AUTO-016-M02", "AUTO-016-M02"]}
            )

    def test_a_verification_command_is_an_argv_list_never_a_shell_string(self) -> None:
        with pytest.raises(ValidationError):
            MilestoneSpec.model_validate(
                {**VALID_MILESTONE, "focused_verification": [{"command": "pytest -q | tee log"}]}
            )

    def test_an_empty_verification_command_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FocusedVerificationCommand(command=[])

    def test_purpose_is_optional(self) -> None:
        command = FocusedVerificationCommand(command=["git", "diff", "--check"])
        assert command.purpose is None

    def test_a_control_character_in_free_text_is_rejected_not_stripped(self) -> None:
        with pytest.raises(ValidationError, match="control character"):
            MilestoneSpec.model_validate({**VALID_MILESTONE, "objective": "drop\rtable"})

    def test_a_bidirectional_control_in_free_text_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="bidirectional control"):
            MilestoneSpec.model_validate({**VALID_MILESTONE, "title": "harmless\u202etxt.exe"})


# --------------------------------------------------------------------------------------
# Section 11 / section 19 -- the durable run record
# --------------------------------------------------------------------------------------


class TestMilestoneCheckpoint:
    """Finding GOV-AUTO-11-F1: the durable evidence section 15 check 2 is measured against."""

    DIGEST = "a" * 64
    OTHER = "b" * 64
    PATH = "src/ai_workflow_engine/milestone_runner/models.py"

    def checkpoint(self, **overrides: Any) -> MilestoneCheckpoint:
        payload: dict[str, Any] = {
            "milestone_id": "AUTO-016-M01",
            "recorded_at": "2026-08-06T12:00:00Z",
            "path_digests": {self.PATH: self.DIGEST},
        }
        payload.update(overrides)
        return MilestoneCheckpoint(**payload)

    def test_an_unchanged_path_does_not_differ(self) -> None:
        assert self.checkpoint().differs_from(self.PATH, self.DIGEST) is False

    def test_a_modified_path_differs(self) -> None:
        assert self.checkpoint().differs_from(self.PATH, self.OTHER) is True

    def test_a_path_the_checkpoint_never_saw_differs(self) -> None:
        assert self.checkpoint().differs_from("tests/test_cli.py", self.DIGEST) is True

    def test_an_unreadable_observation_is_never_evidence_of_sameness(self) -> None:
        """The conservative direction: unreadable can only produce a stop, never a pass."""
        subject = self.checkpoint(path_digests={self.PATH: UNREADABLE_DIGEST})
        assert subject.differs_from(self.PATH, UNREADABLE_DIGEST) is True
        assert subject.differs_from(self.PATH, self.DIGEST) is True
        assert self.checkpoint().differs_from(self.PATH, UNREADABLE_DIGEST) is True

    def test_the_sentinel_is_not_a_digest(self) -> None:
        assert len(UNREADABLE_DIGEST) != 64

    def test_a_digest_that_is_neither_sha256_nor_the_sentinel_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
            self.checkpoint(path_digests={self.PATH: "nope"})

    def test_paths_are_normalized_and_traversal_is_refused(self) -> None:
        assert self.checkpoint(path_digests={f"./{self.PATH}": self.DIGEST}).path_digests == {
            self.PATH: self.DIGEST
        }
        with pytest.raises(ValidationError):
            self.checkpoint(path_digests={"../escape.py": self.DIGEST})

    def test_an_unknown_field_raises(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            self.checkpoint(changed_paths=[])

    def test_a_record_refuses_two_checkpoints_for_one_milestone(self) -> None:
        with pytest.raises(ValidationError, match="milestone_checkpoints"):
            run_record(milestone_checkpoints=[self.checkpoint(), self.checkpoint()])

    def test_a_record_keeps_them_in_completion_order(self) -> None:
        second = self.checkpoint(milestone_id="AUTO-016-M02", path_digests={})
        record = run_record(milestone_checkpoints=[self.checkpoint(), second])
        assert [entry.milestone_id for entry in record.milestone_checkpoints] == [
            "AUTO-016-M01",
            "AUTO-016-M02",
        ]


class TestRunRecord:
    def test_a_minimal_record_loads(self) -> None:
        record = run_record()
        assert record.workflow_state is RunStatus.IMPLEMENTING
        assert record.stop_reason is None
        assert record.completed_milestones == []

    def test_every_section_eleven_field_is_present(self) -> None:
        # `milestone_checkpoints` is the one field beyond section 11's recorded set, and it is
        # there because section 15 check 2 is not computable without it: a run that makes no
        # commit until its end accumulates every milestone's work in one worktree diff, so
        # "the paths this milestone changed" has to be recorded when the milestone finishes or
        # it is lost (finding GOV-AUTO-11-F1). It is an append-only ledger like the four of
        # section 19, carries no counter, and no code path reads it as authority for anything
        # but check 2's input set.
        expected = {
            "schema_version",
            "milestone_checkpoints",
            "run_id",
            "repository_root",
            "repository_identity",
            "expected_branch",
            "baseline_sha",
            "contract_sha256",
            "workflow_state",
            "stop_reason",
            "created_at",
            "updated_at",
            "current_milestone",
            "completed_milestones",
            "changed_paths",
            "provider_runs",
            "verification_results",
            "blocking_findings",
            "deferred_findings",
            "approvals",
            "review_attempts",
            "successful_review_rounds",
            "provider_failure_count",
            "correction_round",
            "closure_round",
            "reconciliations",
            "reopenings",
            "review_recoveries",
            "revalidations",
        }
        assert set(RunRecord.model_fields) == expected

    def test_an_unknown_field_raises_rather_than_being_ignored(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            run_record(allow_automatic_commit=True)

    def test_an_unknown_state_schema_version_is_a_hard_refusal(self) -> None:
        with pytest.raises(ValidationError, match="is unknown"):
            run_record(schema_version=STATE_SCHEMA_VERSION + 1)

    def test_a_full_record_round_trips_through_json_unchanged(self) -> None:
        record = run_record(
            provider_runs=[provider_run(1), provider_run(2)],
            verification_results=[passing_verification()],
            blocking_findings=[
                Finding(
                    finding_id="AUTO016-REV-001",
                    severity=FindingSeverity.HIGH,
                    title="Internal contradiction",
                    summary="Two sections disagree about Git authority.",
                )
            ],
            deferred_findings=[
                Finding(
                    finding_id="AUTO016-REV-009",
                    severity=FindingSeverity.LOW,
                    title="Wording nit",
                    summary="A sentence reads awkwardly.",
                    status=FindingStatus.DEFERRED,
                )
            ],
            approvals=[approval()],
            changed_paths=["src/ai_workflow_engine/milestone_runner/models.py"],
        )
        assert RunRecord.model_validate_json(record.model_dump_json()) == record

    def test_a_safety_stop_must_record_a_reason(self) -> None:
        with pytest.raises(ValidationError, match="must record a stop_reason"):
            run_record(workflow_state=RunStatus.HUMAN_INTERVENTION_REQUIRED)
        stopped = run_record(
            workflow_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            stop_reason=StopReason.OUT_OF_MILESTONE_SCOPE,
        )
        assert stopped.stop_reason is StopReason.OUT_OF_MILESTONE_SCOPE

    def test_a_completed_run_carries_no_stop_reason(self) -> None:
        with pytest.raises(ValidationError, match="must not record a stop_reason"):
            run_record(workflow_state=RunStatus.DONE, stop_reason=StopReason.HEAD_DRIFT)

    def test_changed_paths_are_normalized_sorted_and_unique(self) -> None:
        record = run_record(changed_paths=["./a/b.py", "a/c.py"])
        assert record.changed_paths == ["a/b.py", "a/c.py"]
        with pytest.raises(ValidationError, match="sorted"):
            run_record(changed_paths=["b.py", "a.py"])
        with pytest.raises(ValidationError, match="duplicate"):
            run_record(changed_paths=["a.py", "./a.py"])

    def test_a_traversal_shaped_changed_path_is_refused(self) -> None:
        with pytest.raises(ValidationError, match=r"'\.\.' path segment"):
            run_record(changed_paths=["../../etc/passwd"])

    def test_transcript_sequence_numbers_must_be_strictly_increasing(self) -> None:
        """Section 11 / defect P-9: two invocations cannot silently share one slot."""
        with pytest.raises(ValidationError, match="strictly increasing"):
            run_record(provider_runs=[provider_run(1), provider_run(1)])
        with pytest.raises(ValidationError, match="strictly increasing"):
            run_record(provider_runs=[provider_run(2), provider_run(1)])


class TestFiveIndependentCounters:
    """Section 19 / section 22 invariant 11: five counters that cannot alias."""

    def test_the_five_counters_are_five_distinct_fields(self) -> None:
        assert RUN_COUNTER_FIELDS == {
            "review_attempts",
            "successful_review_rounds",
            "provider_failure_count",
            "correction_round",
            "closure_round",
        }
        assert len(RUN_COUNTER_FIELDS) == 5
        for name in RUN_COUNTER_FIELDS:
            assert name in RunRecord.model_fields

    def test_each_counter_defaults_to_zero_and_moves_alone(self) -> None:
        record = run_record()
        for name in sorted(RUN_COUNTER_FIELDS):
            assert getattr(record, name) == 0
        bumped = run_record(provider_failure_count=1)
        assert bumped.provider_failure_count == 1
        for name in sorted(RUN_COUNTER_FIELDS - {"provider_failure_count"}):
            assert getattr(bumped, name) == 0, f"{name} aliased provider_failure_count"

    def test_a_provider_failure_does_not_consume_a_successful_review_round(self) -> None:
        """The recorded real run's `token_expired` case, expressed as a type-level fact."""
        record = run_record(review_attempts=1, provider_failure_count=1)
        assert record.successful_review_rounds == 0

    @pytest.mark.parametrize("counter", sorted(RUN_COUNTER_FIELDS))
    def test_no_counter_can_go_negative(self, counter: str) -> None:
        with pytest.raises(ValidationError):
            run_record(**{counter: -1})

    def test_a_ledger_entry_cannot_name_a_counter_that_does_not_exist(self) -> None:
        with pytest.raises(ValidationError, match="not one of the five counters"):
            RecoveryLedgerEntry(
                command=RecoveryCommand.RECOVER_FAILED_REVIEW,
                reason="restore one review budget",
                recorded_at="2026-08-05T22:00:00Z",
                pre_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                post_state=RunStatus.REVIEWING,
                branch="feature/auto-016-milestone-runner",
                head_sha="4fa9212ff47171c162ddf863360413a90e0ee79f",
                budgets_touched={"max_full_reviews": 1},
            )


class TestRecoveryLedgers:
    """Section 19: four append-only ledgers, one per recovery command."""

    def test_the_record_carries_exactly_four_ledgers(self) -> None:
        for ledger in ("reconciliations", "reopenings", "review_recoveries", "revalidations"):
            assert ledger in RunRecord.model_fields
            assert run_record().__getattribute__(ledger) == []

    def test_a_ledger_rejects_an_entry_from_a_different_command(self) -> None:
        entry = RecoveryLedgerEntry(
            command=RecoveryCommand.REOPEN_MILESTONE,
            reason="milestone result was not parseable YAML",
            recorded_at="2026-08-05T22:00:00Z",
            pre_state=RunStatus.MILESTONE_FAILED,
            post_state=RunStatus.IMPLEMENTING,
            branch="feature/auto-016-milestone-runner",
            head_sha="4fa9212ff47171c162ddf863360413a90e0ee79f",
            milestone_id="AUTO-016-M01",
        )
        assert run_record(reopenings=[entry]).reopenings == [entry]
        with pytest.raises(ValidationError, match="must contain only"):
            run_record(revalidations=[entry])

    def test_a_reason_is_required_on_every_entry(self) -> None:
        with pytest.raises(ValidationError):
            RecoveryLedgerEntry(
                command=RecoveryCommand.REVALIDATE_CORRECTION,
                recorded_at="2026-08-05T22:00:00Z",
                pre_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                post_state=RunStatus.CLOSURE_VERIFYING,
                branch="feature/auto-016-milestone-runner",
                head_sha="4fa9212ff47171c162ddf863360413a90e0ee79f",
            )


class TestVerificationResult:
    """Section 22 invariant 18: no fabricated success."""

    def test_a_timeout_can_never_be_recorded_as_a_pass(self) -> None:
        with pytest.raises(ValidationError, match="passed must be exactly"):
            VerificationResult(
                command=["pytest", "-q"],
                exit_code=None,
                timed_out=True,
                passed=True,
                duration_ms=900_000,
                stdout_path="verification/0001.stdout.txt",
                stderr_path="verification/0001.stderr.txt",
            )

    def test_a_non_zero_exit_can_never_be_recorded_as_a_pass(self) -> None:
        with pytest.raises(ValidationError, match="passed must be exactly"):
            VerificationResult(
                command=["ruff", "check", "."],
                exit_code=1,
                passed=True,
                duration_ms=100,
                stdout_path="verification/0002.stdout.txt",
                stderr_path="verification/0002.stderr.txt",
            )

    def test_a_clean_exit_can_never_be_recorded_as_a_failure(self) -> None:
        with pytest.raises(ValidationError, match="passed must be exactly"):
            VerificationResult(
                command=["black", "--check", "."],
                exit_code=0,
                passed=False,
                duration_ms=100,
                stdout_path="verification/0003.stdout.txt",
                stderr_path="verification/0003.stderr.txt",
            )

    def test_a_genuine_pass_is_accepted(self) -> None:
        assert passing_verification().passed is True

    def test_output_is_referenced_by_path_never_inlined(self) -> None:
        """`AUDIT_MODEL.md` section 2: the record holds references, not captured bytes."""
        fields = set(VerificationResult.model_fields)
        assert "stdout" not in fields and "stderr" not in fields
        assert {"stdout_path", "stderr_path"} <= fields


class TestFindingSeveritySplit:
    """Section 19: Critical/High block, Medium/Low are deferred and never block."""

    def test_the_two_severity_sets_partition_the_enum(self) -> None:
        assert BLOCKING_SEVERITIES == {FindingSeverity.CRITICAL, FindingSeverity.HIGH}
        assert DEFERRED_SEVERITIES == {FindingSeverity.MEDIUM, FindingSeverity.LOW}
        assert BLOCKING_SEVERITIES | DEFERRED_SEVERITIES == set(FindingSeverity)
        assert not BLOCKING_SEVERITIES & DEFERRED_SEVERITIES

    def test_a_low_severity_finding_cannot_be_filed_as_a_blocker(self) -> None:
        low = Finding(
            finding_id="F-2",
            severity=FindingSeverity.LOW,
            title="nit",
            summary="A wording nit.",
        )
        with pytest.raises(ValidationError, match="must not carry"):
            run_record(blocking_findings=[low])

    def test_a_critical_finding_cannot_be_filed_as_deferred(self) -> None:
        critical = Finding(
            finding_id="F-3",
            severity=FindingSeverity.CRITICAL,
            title="credential leak",
            summary="A secret reached a transcript.",
        )
        with pytest.raises(ValidationError, match="must not carry"):
            run_record(deferred_findings=[critical])

    def test_a_finding_id_cannot_appear_in_both_ledgers(self) -> None:
        blocker = Finding(
            finding_id="F-4",
            severity=FindingSeverity.HIGH,
            title="scope creep",
            summary="A changed path fell outside the milestone.",
        )
        deferred = Finding(
            finding_id="F-4",
            severity=FindingSeverity.MEDIUM,
            title="scope creep",
            summary="A changed path fell outside the milestone.",
        )
        with pytest.raises(ValidationError, match="duplicate"):
            run_record(blocking_findings=[blocker], deferred_findings=[deferred])


class TestApprovalRecord:
    """Section 20: bound to the state it was granted against, and single-use."""

    def test_a_valid_approval_loads(self) -> None:
        record = approval()
        assert record.operation is ApprovalOperation.COMMIT
        assert record.consumed is False
        assert record.consumed_at is None

    def test_the_binding_covers_every_section_twenty_element(self) -> None:
        fields = set(ApprovalRecord.model_fields)
        assert {
            "repository_identity",
            "branch",
            "baseline_sha",
            "head_sha",
            "changed_paths",
            "changed_path_digests",
            "verification_digest",
            "review_verdict",
            "finding_ids",
            "operation",
        } <= fields

    def test_a_digest_is_required_for_every_changed_path(self) -> None:
        with pytest.raises(ValidationError, match="exactly every changed path"):
            approval(changed_path_digests={})

    def test_an_extra_digest_for_an_unlisted_path_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exactly every changed path"):
            approval(
                changed_path_digests={
                    "src/ai_workflow_engine/milestone_runner/models.py": "0" * 64,
                    "src/ai_workflow_engine/cli.py": "1" * 64,
                }
            )

    def test_consumption_is_single_use_and_recorded(self) -> None:
        with pytest.raises(ValidationError, match="single-use"):
            approval(consumed=True, execution_started_at="2026-08-05T22:04:00Z")
        with pytest.raises(ValidationError, match="single-use"):
            approval(consumed_at="2026-08-05T22:05:00Z")
        consumed = approval(
            consumed=True,
            consumed_at="2026-08-05T22:05:00Z",
            execution_started_at="2026-08-05T22:04:00Z",
        )
        assert consumed.consumed is True

    def test_a_consumption_without_a_recorded_attempt_describes_no_act(self) -> None:
        """Section 20: the attempt is durable before the act, so a consumption implies one."""
        with pytest.raises(ValidationError, match="when its execution was attempted"):
            approval(consumed=True, consumed_at="2026-08-05T22:05:00Z")

    def test_only_a_consumed_approval_names_where_it_landed_head(self) -> None:
        """Section 4 item 4: the landing point belongs to the commit that actually executed."""
        with pytest.raises(ValidationError, match="landed HEAD"):
            approval(resulting_head_sha="4fa9212ff47171c162ddf863360413a90e0ee79f")
        landed = approval(
            consumed=True,
            consumed_at="2026-08-05T22:05:00Z",
            execution_started_at="2026-08-05T22:04:00Z",
            resulting_head_sha="4fa9212ff47171c162ddf863360413a90e0ee79f",
        )
        assert landed.resulting_head_sha == "4fa9212ff47171c162ddf863360413a90e0ee79f"

    def test_an_approval_authorizes_exactly_one_operation(self) -> None:
        assert {member.value for member in ApprovalOperation} == {"COMMIT", "PUSH"}

    def test_a_naive_or_local_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="ISO-8601 UTC"):
            approval(granted_at="2026-08-05 22:00:00")


# --------------------------------------------------------------------------------------
# Canonicalization -- the helpers scope, state and approval binding all reuse
# --------------------------------------------------------------------------------------


class TestNormalizeRepositoryPath:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("src/a.py", "src/a.py"),
            ("./src/a.py", "src/a.py"),
            ("src//a.py", "src/a.py"),
            ("src/./a.py", "src/a.py"),
            ("src/a.py/", "src/a.py"),
            ("./././src/nested/a.py", "src/nested/a.py"),
            ("a.py", "a.py"),
        ],
    )
    def test_normalizes_to_a_dot_segment_free_posix_path(self, raw: str, expected: str) -> None:
        assert normalize_repository_path(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "/etc/passwd",
            "/src/a.py",
            "C:/Windows/system32",
            "src\\a.py",
            "../outside.py",
            "src/../../outside.py",
            "src/..",
            "..",
            "",
            ".",
            "./",
            "//",
        ],
    )
    def test_refuses_an_absolute_or_traversal_shaped_input(self, raw: str) -> None:
        with pytest.raises(ValueError):
            normalize_repository_path(raw)

    def test_traversal_is_refused_not_resolved(self) -> None:
        """Resolving `..` is how a guard talks itself into permitting an escape."""
        with pytest.raises(ValueError, match=r"'\.\.' path segment"):
            normalize_repository_path("src/sub/../a.py")

    def test_a_control_character_in_a_path_is_refused(self) -> None:
        with pytest.raises(ValueError, match="control character"):
            normalize_repository_path("src/a\n.py")

    def test_an_over_long_path_is_refused_never_truncated(self) -> None:
        with pytest.raises(ValueError, match="at most"):
            normalize_repository_path("a" * 513)

    def test_normalization_is_idempotent(self) -> None:
        once = normalize_repository_path("./src//nested/./a.py")
        assert normalize_repository_path(once) == once

    def test_two_spellings_of_one_path_compare_equal(self) -> None:
        """This is the property section 15's scope matching depends on."""
        assert normalize_repository_path("./src/a.py") == normalize_repository_path("src//a.py")


class TestCanonicalDigest:
    def test_is_stable_under_key_reordering(self) -> None:
        first = {"alpha": 1, "beta": ["x", "y"], "gamma": {"inner": True}}
        second = {"gamma": {"inner": True}, "beta": ["x", "y"], "alpha": 1}
        assert canonical_digest(first) == canonical_digest(second)

    def test_excludes_wall_clock_timestamps(self) -> None:
        base = {"run_id": "r", "created_at": "2026-08-05T21:00:00Z"}
        later = {"run_id": "r", "created_at": "2026-08-05T23:59:59Z"}
        assert canonical_digest(base) == canonical_digest(later)

    def test_excludes_timestamps_at_every_nesting_depth(self) -> None:
        first = {"runs": [{"sequence": 1, "started_at": "2026-08-05T21:00:00Z"}]}
        second = {"runs": [{"sequence": 1, "started_at": "2026-08-06T09:30:00Z"}]}
        assert canonical_digest(first) == canonical_digest(second)

    def test_the_excluded_field_set_is_exactly_the_wall_clock_fields(self) -> None:
        assert DIGEST_EXCLUDED_FIELDS == {
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "recorded_at",
            "granted_at",
            "consumed_at",
            "duration_ms",
        }

    def test_a_substantive_change_does_change_the_digest(self) -> None:
        assert canonical_digest({"run_id": "a"}) != canonical_digest({"run_id": "b"})

    def test_list_order_is_significant(self) -> None:
        assert canonical_digest({"paths": ["a", "b"]}) != canonical_digest({"paths": ["b", "a"]})

    def test_returns_a_lowercase_sha256_hex_digest(self) -> None:
        digest = canonical_digest({"a": 1})
        assert re.fullmatch(r"[0-9a-f]{64}", digest)

    def test_accepts_this_packages_own_enum_typed_vocabulary(self) -> None:
        assert canonical_digest({"state": RunStatus.IMPLEMENTING}) == canonical_digest(
            {"state": "IMPLEMENTING"}
        )

    def test_a_float_is_refused_outright(self) -> None:
        """A float has no canonical decimal form, so admitting one makes a digest unstable."""
        with pytest.raises(ValueError, match="unsupported value type"):
            canonical_digest({"duration": 1.5})

    def test_an_unsupported_container_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unsupported value type"):
            canonical_digest({"paths": ("a", "b")})

    def test_a_non_string_mapping_key_is_refused(self) -> None:
        with pytest.raises(ValueError, match="mapping key must be a string"):
            canonical_digest({1: "a"})

    def test_a_run_record_digest_survives_a_state_republication(self) -> None:
        """Section 20's binding is only checkable because re-derivation reproduces the digest."""
        record = run_record(changed_paths=["src/ai_workflow_engine/milestone_runner/models.py"])
        republished = record.model_copy(update={"updated_at": "2026-08-06T09:00:00Z"})
        assert canonical_digest(record.model_dump()) == canonical_digest(republished.model_dump())

    def test_a_run_record_digest_changes_when_the_work_changes(self) -> None:
        record = run_record()
        moved = record.model_copy(update={"workflow_state": RunStatus.FOCUSED_VERIFYING})
        assert canonical_digest(record.model_dump()) != canonical_digest(moved.model_dump())


# --------------------------------------------------------------------------------------
# Section 8 / section 22 -- the module's own boundary, proved at AST level
# --------------------------------------------------------------------------------------


def models_tree() -> ast.Module:
    return ast.parse(MODELS_SOURCE.read_text(encoding="utf-8"))


def imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


class TestModelsModuleBoundary:
    """Section 22 invariants 3, 5, 6 and 20, and this milestone's own no-I/O exclusion."""

    def test_imports_no_subprocess_socket_or_agentos_package(self) -> None:
        for name in imported_module_names(models_tree()):
            root = name.split(".")[0]
            assert root != "subprocess", f"models.py imports {name}"
            assert root != "socket", f"models.py imports {name}"
            assert root != "urllib", f"models.py imports {name}"
            assert root != "http", f"models.py imports {name}"
            assert not name.startswith("agentos_workflow"), f"models.py imports {name}"
            assert not name.startswith("agentos_dashboard"), f"models.py imports {name}"

    def test_reaches_no_process_spawning_or_shell_attribute(self) -> None:
        for node in ast.walk(models_tree()):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "system",
                    "popen",
                    "Popen",
                    "run",
                    "call",
                    "execv",
                    "execve",
                    "spawnv",
                    "fork",
                }, f"models.py reaches {node.attr}"
            if isinstance(node, ast.keyword):
                assert node.arg != "shell", "models.py passes a shell= keyword"

    def test_performs_no_file_or_network_io(self) -> None:
        """This milestone's explicit exclusion: models.py opens no file and touches no network."""
        banned_calls = {"open", "input", "eval", "exec", "compile", "__import__"}
        for node in ast.walk(models_tree()):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, f"models.py calls {node.func.id}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "read_text",
                    "write_text",
                    "read_bytes",
                    "write_bytes",
                    "unlink",
                    "mkdir",
                    "replace",
                    "rename",
                }, f"models.py reaches {node.attr}"

    def test_names_no_mutating_git_subcommand(self) -> None:
        """Section 20: no module but `approval_git.py` may construct a mutating Git argv."""
        source = MODELS_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef):
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))
        code_strings = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ]
        forbidden = {
            "commit",
            "push",
            "checkout",
            "switch",
            "reset",
            "restore",
            "stash",
            "clean",
            "rebase",
            "merge",
            "cherry-pick",
            "revert",
            "fetch",
            "pull",
            "gh",
        }
        for text in code_strings:
            assert text not in forbidden, f"models.py names the Git subcommand {text!r}"


class TestPackageMarker:
    """Section 8: `__init__.py` is docstring-only and re-exports nothing."""

    def test_the_marker_contains_only_a_docstring(self) -> None:
        tree = ast.parse(PACKAGE_INIT.read_text(encoding="utf-8"))
        assert len(tree.body) == 1
        statement = tree.body[0]
        assert isinstance(statement, ast.Expr)
        assert isinstance(statement.value, ast.Constant)
        assert isinstance(statement.value.value, str)

    def test_the_marker_defines_no_dunder_all(self) -> None:
        """No `__all__`, and no import statement at all -- importing one submodule drags in none.

        `hasattr(package, "models")` is deliberately not asserted: the import machinery binds a
        submodule onto its package once anything imports it, which is a property of Python and
        not evidence about this file. The AST check above is the real proof.
        """
        import ai_workflow_engine.milestone_runner as package

        assert not hasattr(package, "__all__")
        tree = ast.parse(PACKAGE_INIT.read_text(encoding="utf-8"))
        assert not [
            node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)
        ]
        assert package.__doc__ is not None


# ======================================================================================
# AUTO-016-M03 -- the durable state store, the redaction boundary, the lock precondition
# and idempotent resume (sections 11, 12, 13, 17a; invariants 2, 7, 8, 9, 10; defects
# P-6 and P-9).
#
# Appended to this module rather than given its own file because section 23.3 allocates
# exactly one state test module and both halves are state. Nothing above this banner is
# edited, renamed, reordered or removed by this milestone; M01's assertions run unchanged
# as part of M03's own focused verification.
#
# Everything below runs against real artifacts: real `git init` repositories, real files
# under `tmp_path`, the real redactor and the real `fcntl.flock`. The only place a
# monkeypatch appears is where a crash has to be injected at a specific instruction --
# `os.replace` -- because there is no other way to observe the window between the
# temporary write and the rename, and that window is precisely what section 11 defines
# atomicity against.
# ======================================================================================

PACKAGE_DIRECTORY = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner"
STATE_SOURCE = PACKAGE_DIRECTORY / "state.py"

M03_REMOTE = "https://github.com/example/demo-repo.git"
M03_IDENTITY = "demo-repo--2059e82cffa9"
M03_RUN_ID = "auto016-20260805T213855Z-7fea75fc"
OTHER_IDENTITY = "other-repo--001122334455"

#: A GitHub token, an AWS access key id and a bearer token, none of which may survive a trip
#: through the section 17a boundary. Spelled out here rather than generated so a reader can see
#: exactly what is being searched for on disk afterwards.
SECRET_STDOUT = (
    "Running the milestone...\n"
    "export GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwx\n"
    "aws_key AKIAIOSFODNN7EXAMPLE\n"
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789\n"
    "done.\n"
)
SECRET_LITERALS = (
    "ghp_0123456789abcdefghijklmnopqrstuvwx",
    "AKIAIOSFODNN7EXAMPLE",
    "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
)


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `Path.home()` at a disposable directory.

    `artifact_root_for` derives the root from the operator's home directory, so a test that did
    not redirect it would write into the developer's real one. Redirecting `HOME` rather than
    patching `Path.home` keeps the production derivation itself under test.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """A real, disposable repository with one revision and the primary remote M03 keys on."""
    repository = tmp_path / "worktree"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "Milestone Runner Tests")
    git(repository, "remote", "add", "origin", M03_REMOTE)
    (repository / "kept.txt").write_text("kept\n", encoding="utf-8")
    git(repository, "add", "kept.txt")
    git(repository, "commit", "-m", "initial")
    return repository


@pytest.fixture
def inspector(worktree: Path) -> GitReadOnlyInspector:
    return GitReadOnlyInspector(worktree)


@pytest.fixture
def store(isolated_home: Path, worktree: Path) -> RunStateStore:
    return RunStateStore.pin(
        repository_id=M03_IDENTITY, run_id=M03_RUN_ID, repository_root=worktree
    )


def lock_for_store(store: RunStateStore) -> RunLock:
    return RunLock(
        run_id=store.run_id,
        repository_identity=store.repository_id,
        artifact_root=store.artifact_root,
    )


@pytest.fixture
def held_lock(store: RunStateStore) -> Iterator[RunLock]:
    lock = lock_for_store(store)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


def durable_record(worktree: Path, head_sha: str, **overrides: Any) -> RunRecord:
    """A run record consistent with the `store` fixture: same run, same repository, same pin."""
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": M03_RUN_ID,
        "repository_root": str(worktree),
        "repository_identity": M03_IDENTITY,
        "expected_branch": "main",
        "baseline_sha": head_sha,
        "contract_sha256": "56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e",
        "workflow_state": RunStatus.PREFLIGHT,
        "created_at": "2026-08-05T21:38:55Z",
        "updated_at": "2026-08-05T21:40:01Z",
    }
    payload.update(overrides)
    return RunRecord(**payload)


def in_flight_provider_run(sequence: int = 1) -> ProviderRunRecord:
    """One invocation that started and never recorded a completion -- a crash mid-provider."""
    return ProviderRunRecord(
        sequence=sequence,
        role=ProviderRole.IMPLEMENTATION,
        provider="claude",
        milestone_id="AUTO-016-M03",
        started_at="2026-08-05T21:39:00Z",
        completed_at=None,
        duration_ms=0,
        prompt_path=f"transcripts/{sequence:04d}-implementation.prompt.md",
        stdout_path=f"transcripts/{sequence:04d}-implementation.stdout.txt",
        stderr_path=f"transcripts/{sequence:04d}-implementation.stderr.txt",
    )


def record_intent(
    store: RunStateStore,
    lock: RunLock,
    inspector: GitReadOnlyInspector,
    *,
    sequence: int = 1,
) -> ProviderInvocationIntent:
    """Make the pre-invocation evidence durable, exactly as the invoker's hook does.

    A crash mid-provider always leaves this document behind, because production writes it before
    the process it describes can exist. A test that omits it is testing a state the runner cannot
    reach -- which is itself worth asserting, and is asserted separately.
    """
    return store.record_provider_intent(
        pending=in_flight_provider_run(sequence),
        evidence=inspector.evidence(),
        recorded_at="2026-08-05T21:39:00Z",
        lock=lock,
    )


def every_byte_under(root: Path) -> str:
    """Concatenate every file under `root`, so an assertion can search the whole tree at once."""
    return "".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


class TestArtifactRootIsTheOneRepositoryScopedRoot:
    """Section 11: one identity derivation and one root, shared with the plan root.

    The agreement with `plan.py` is asserted rather than assumed. `plan.py` is complete as M02
    delivered it and outside this milestone's writable surface, so the two modules necessarily
    carry sibling derivations; a test is the only way to keep "one root, one derivation" a fact
    instead of a comment that can quietly stop being true.
    """

    def test_the_root_is_the_documented_external_location(self, isolated_home: Path) -> None:
        assert artifact_root_for(M03_IDENTITY) == (
            isolated_home / ".ai-workflow-engine" / "milestone-runs" / M03_IDENTITY
        )

    def test_it_is_the_same_root_the_plan_loader_derives(self, isolated_home: Path) -> None:
        assert artifact_root_for(M03_IDENTITY) == plan_module.repository_scoped_root(M03_IDENTITY)

    def test_the_plan_root_is_a_sibling_of_the_run_directories(self, isolated_home: Path) -> None:
        assert plan_module.default_plan_root(M03_IDENTITY).parent == artifact_root_for(M03_IDENTITY)

    def test_canonical_repository_id_is_the_one_section_11_derivation(self) -> None:
        assert canonical_repository_id(M03_REMOTE) == derive_repository_identity(M03_REMOTE)
        assert canonical_repository_id(M03_REMOTE) == M03_IDENTITY

    def test_the_identity_a_real_repository_reports_addresses_this_root(
        self, isolated_home: Path, inspector: GitReadOnlyInspector
    ) -> None:
        observed = inspector.repository_identity()
        assert observed == canonical_repository_id(M03_REMOTE)
        assert artifact_root_for(observed).name == observed

    def test_the_run_directory_follows_section_11_s_layout(
        self, store: RunStateStore, isolated_home: Path
    ) -> None:
        assert store.run_directory == artifact_root_for(M03_IDENTITY) / M03_RUN_ID
        assert store.state_path.name == STATE_FILE_NAME
        assert store.transcripts_directory.name == TRANSCRIPTS_DIRECTORY
        assert store.transcripts_directory.is_dir()

    @pytest.mark.parametrize(
        "identity",
        ["", "..", "not-canonical", "demo--XYZ", "demo/repo--0123456789ab", "-x--0123456789ab"],
    )
    def test_a_malformed_identity_never_reaches_the_filesystem(
        self, isolated_home: Path, identity: str
    ) -> None:
        with pytest.raises(StateRootRefused):
            artifact_root_for(identity)


class TestStateRootOutsideRepositoryEnforced:
    """Invariant 7: the root resolves outside the worktree; one that would not is refused."""

    def test_a_root_inside_the_repository_is_refused(self, worktree: Path) -> None:
        with pytest.raises(StateRootRefused, match="must not be inside the repository"):
            reject_repository_containment(worktree / "state", worktree)

    def test_the_repository_root_itself_is_refused(self, worktree: Path) -> None:
        with pytest.raises(StateRootRefused):
            reject_repository_containment(worktree, worktree)

    def test_a_symlink_pointing_back_into_the_repository_is_refused(
        self, worktree: Path, tmp_path: Path
    ) -> None:
        """Both sides are realized first, so an outside-looking path cannot hide an inside one."""
        disguise = tmp_path / "looks-outside"
        disguise.symlink_to(worktree, target_is_directory=True)
        with pytest.raises(StateRootRefused):
            reject_repository_containment(disguise / "state", worktree)

    def test_a_genuinely_external_root_is_admitted(self, worktree: Path, tmp_path: Path) -> None:
        reject_repository_containment(tmp_path / "outside", worktree)

    def test_a_sibling_whose_name_prefixes_the_repository_is_admitted(self, worktree: Path) -> None:
        """`worktree-runs` is not inside `worktree`; a bare string prefix test would say it is."""
        reject_repository_containment(worktree.parent / f"{worktree.name}-runs", worktree)

    def test_this_check_and_the_plan_loader_agree_on_every_case(
        self, worktree: Path, tmp_path: Path
    ) -> None:
        candidates = [
            worktree,
            worktree / "state",
            worktree / "docs" / "plans",
            tmp_path / "outside",
            worktree.parent / f"{worktree.name}-runs",
        ]
        for candidate in candidates:
            state_refused = False
            plan_refused = False
            try:
                reject_repository_containment(candidate, worktree)
            except StateRootRefused:
                state_refused = True
            try:
                plan_module.reject_repository_containment(candidate, worktree)
            except plan_module.PlanValidationError:
                plan_refused = True
            assert state_refused == plan_refused, f"{candidate} is judged differently"

    def test_pinning_a_store_whose_root_would_land_inside_the_repository_is_refused(
        self, worktree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal is the whole remedy: nothing is relocated to somewhere acceptable."""
        monkeypatch.setenv("HOME", str(worktree / "home"))
        with pytest.raises(StateRootRefused, match="must not be inside the repository"):
            RunStateStore.pin(
                repository_id=M03_IDENTITY, run_id=M03_RUN_ID, repository_root=worktree
            )
        assert not (worktree / "home" / ".ai-workflow-engine").exists()
        assert git(worktree, "status", "--porcelain") == ""

    def test_a_malformed_run_id_cannot_escape_the_run_directory(
        self, isolated_home: Path, worktree: Path
    ) -> None:
        with pytest.raises(StateRootRefused, match="not a usable run id"):
            RunStateStore.pin(
                repository_id=M03_IDENTITY, run_id="../../escape", repository_root=worktree
            )


class TestSymlinkComponentRejected:
    """Invariant 8: a symlinked component is rejected rather than followed."""

    def test_a_symlinked_artifact_root_component_is_refused(
        self, isolated_home: Path, worktree: Path, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (isolated_home / ".ai-workflow-engine").symlink_to(elsewhere, target_is_directory=True)

        with pytest.raises(StateRootRefused, match="symbolic link"):
            RunStateStore.pin(
                repository_id=M03_IDENTITY, run_id=M03_RUN_ID, repository_root=worktree
            )
        assert list(elsewhere.iterdir()) == []

    def test_a_symlinked_final_component_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target, target_is_directory=True)
        with pytest.raises(StateRootRefused, match="symbolic link"):
            reject_symlink_components(link, "The artifact root")

    def test_a_component_that_does_not_exist_yet_is_not_a_link(self, tmp_path: Path) -> None:
        reject_symlink_components(tmp_path / "absent" / "deeper", "The artifact root")

    def test_writing_through_a_symlinked_artifact_path_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("untouched\n", encoding="utf-8")
        link = tmp_path / "artifact.txt"
        link.symlink_to(outside)
        with pytest.raises(StateRootRefused, match="symbolic link"):
            write_redacted_artifact(link, "replacement")
        assert outside.read_text(encoding="utf-8") == "untouched\n"


class TestAtomicPublicationRoundTrip:
    """Section 11's publication protocol, exercised through the store it exists for."""

    def test_a_published_record_loads_back_equal(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        record = durable_record(worktree, "a" * 40)
        store.publish(record, lock=held_lock)
        assert store.exists()
        assert store.load() == record

    def test_the_state_document_is_created_restricted(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        assert store.state_path.stat().st_mode & 0o777 == 0o600

    def test_publication_leaves_no_temporary_file_behind(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        hidden = [path.name for path in store.run_directory.iterdir() if path.name.startswith(".")]
        assert hidden == []

    def test_republication_replaces_rather_than_appends(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        store.publish(
            durable_record(worktree, "a" * 40, workflow_state=RunStatus.IMPLEMENTING),
            lock=held_lock,
        )
        assert store.load().workflow_state is RunStatus.IMPLEMENTING

    def test_the_record_must_name_this_store_s_run_and_repository(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        with pytest.raises(StatePublicationFailure, match="names run"):
            store.publish(durable_record(worktree, "a" * 40, run_id="other-run"), lock=held_lock)

    def test_the_plan_snapshot_is_published_under_the_artifact_root(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        """A snapshot of what this run resolved -- never a source plan, never inside the tree."""
        store.publish_plan_snapshot('{"milestones": []}', lock=held_lock)
        assert store.plan_snapshot_path.is_file()
        assert store.repository_root not in store.plan_snapshot_path.parents


class TestEveryStateWriteRequiresTheRunLock:
    """Prototype defect P-6: `cmd_abort` wrote state holding no lock. Not expressible here."""

    def test_publishing_without_a_held_lock_is_refused(
        self, store: RunStateStore, worktree: Path
    ) -> None:
        with pytest.raises(StatePublicationFailure, match="run lock"):
            store.publish(durable_record(worktree, "a" * 40), lock=lock_for_store(store))
        assert not store.exists()

    def test_a_released_lock_no_longer_permits_a_write(
        self, store: RunStateStore, worktree: Path
    ) -> None:
        """The `abort` path is exactly this shape: a state write after the run has stopped."""
        lock = lock_for_store(store)
        lock.acquire()
        store.publish(durable_record(worktree, "a" * 40), lock=lock)
        lock.release()
        with pytest.raises(StatePublicationFailure, match="run lock"):
            store.publish(
                durable_record(worktree, "a" * 40, workflow_state=RunStatus.ABORTED), lock=lock
            )
        assert store.load().workflow_state is RunStatus.PREFLIGHT

    def test_a_lock_for_another_repository_does_not_satisfy_the_precondition(
        self, store: RunStateStore, worktree: Path
    ) -> None:
        foreign = RunLock(
            run_id=store.run_id,
            repository_identity=OTHER_IDENTITY,
            artifact_root=store.artifact_root.parent / OTHER_IDENTITY,
        )
        foreign.acquire()
        try:
            with pytest.raises(StatePublicationFailure, match="not for this run"):
                store.publish(durable_record(worktree, "a" * 40), lock=foreign)
        finally:
            foreign.release()

    def test_every_writer_on_the_store_demands_a_lock(self) -> None:
        """Stated structurally: no writer signature exists that omits the lock parameter."""
        import inspect

        writers = (
            "publish",
            "publish_plan_snapshot",
            "write_transcript",
            "next_transcript_sequence",
        )
        for name in writers:
            parameters = inspect.signature(getattr(RunStateStore, name)).parameters
            assert "lock" in parameters, f"{name} must take a run lock"

    def test_writing_a_transcript_without_a_lock_is_refused(self, store: RunStateStore) -> None:
        with pytest.raises(StatePublicationFailure, match="run lock"):
            store.write_transcript(
                sequence=1,
                label="implementation",
                kind=TranscriptKind.STDOUT,
                text="output",
                moment=datetime.now(UTC),
                lock=lock_for_store(store),
            )
        assert list(store.transcripts_directory.iterdir()) == []

    def test_reading_takes_no_lock_and_is_safe_against_a_torn_read(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        """Section 12's stated trade for the read-only commands: publication is atomic."""
        import inspect

        record = durable_record(worktree, "a" * 40)
        store.publish(record, lock=held_lock)
        assert "lock" not in inspect.signature(RunStateStore.load).parameters
        assert store.load() == record


class TestCrashBeforeRenameLeavesNoPartialState:
    """Invariant 9: no crash point leaves a partial or torn document at the canonical path.

    `os.replace` is monkeypatched to fail because the rename is the exact instruction atomicity
    is defined around, and there is no other way to stop a process inside that window. Everything
    the assertions look at afterwards -- the file, its bytes, the directory listing -- is real.
    """

    @staticmethod
    def _crash(source: Any, destination: Any) -> None:
        raise OSError("the machine lost power between the write and the rename")

    def test_a_crash_before_the_rename_leaves_the_previous_document_intact(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        before = store.state_path.read_bytes()

        monkeypatch.setattr(os, "replace", self._crash)
        with pytest.raises(StatePublicationFailure):
            store.publish(
                durable_record(worktree, "a" * 40, workflow_state=RunStatus.ABORTED),
                lock=held_lock,
            )
        monkeypatch.undo()

        assert store.state_path.read_bytes() == before
        assert store.load().workflow_state is RunStatus.PREFLIGHT

    def test_a_crash_before_the_first_rename_leaves_no_state_at_all(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(os, "replace", self._crash)
        with pytest.raises(StatePublicationFailure):
            store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        monkeypatch.undo()

        assert not store.state_path.exists()
        assert store.exists() is False

    def test_a_failed_publication_removes_its_own_temporary_file(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(os, "replace", self._crash)
        with pytest.raises(StatePublicationFailure):
            store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        monkeypatch.undo()

        leftovers = [
            path.name
            for path in store.run_directory.iterdir()
            if path.name.startswith(TEMP_FILE_PREFIX)
        ]
        assert leftovers == []

    def test_the_temporary_file_shares_the_destination_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cross-filesystem rename is not atomic, so the temp file is always a sibling."""
        seen: list[tuple[str, str]] = []
        real_replace = os.replace

        def record_and_replace(source: Any, destination: Any) -> None:
            seen.append((str(Path(source).parent), str(Path(destination).parent)))
            real_replace(source, destination)

        target = tmp_path / "nested" / "state.json"
        target.parent.mkdir()
        monkeypatch.setattr(os, "replace", record_and_replace)
        publish_atomically(target, b"{}")
        monkeypatch.undo()

        assert seen == [(str(target.parent), str(target.parent))]
        assert target.read_bytes() == b"{}"


class TestCrashAfterFsyncBeforeRenameRecoverable:
    """The same window from the other side: the run is still usable afterwards."""

    def test_a_retry_after_a_failed_rename_publishes_normally(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fsynced: list[int] = []
        real_fsync = os.fsync

        def counting_fsync(descriptor: int) -> None:
            fsynced.append(descriptor)
            real_fsync(descriptor)

        def crash(source: Any, destination: Any) -> None:
            raise OSError("power lost after the data was durable but before the rename")

        monkeypatch.setattr(os, "fsync", counting_fsync)
        monkeypatch.setattr(os, "replace", crash)
        with pytest.raises(StatePublicationFailure):
            store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        monkeypatch.undo()

        assert fsynced, "the payload must be fsynced before the rename is attempted"
        record = durable_record(worktree, "a" * 40, workflow_state=RunStatus.IMPLEMENTING)
        store.publish(record, lock=held_lock)
        assert store.load() == record


class TestOrphanTempFileNeverMistakenForState:
    """A namespaced orphan is inert: nothing reads a run directory by pattern."""

    def test_an_orphan_temp_file_does_not_become_state(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        (store.run_directory / f"{TEMP_FILE_PREFIX}deadbeef").write_bytes(b'{"schema_version": 1}')
        assert store.exists() is False

        record = durable_record(worktree, "a" * 40)
        store.publish(record, lock=held_lock)
        assert store.load() == record

    def test_an_orphan_temp_file_never_advances_the_transcript_sequence(
        self, store: RunStateStore
    ) -> None:
        orphan = f"{TEMP_FILE_PREFIX}0009-20260805T213855Z-implementation.stdout.txt"
        (store.transcripts_directory / orphan).write_text("9999", encoding="utf-8")
        assert next_transcript_sequence(store.transcripts_directory) == 1

    def test_the_temp_prefix_can_never_satisfy_a_canonical_name(self) -> None:
        assert TEMP_FILE_PREFIX.startswith(".")
        assert not STATE_FILE_NAME.startswith(TEMP_FILE_PREFIX)
        canonical = transcript_name(
            1,
            datetime(2026, 8, 5, 21, 38, 55, tzinfo=UTC),
            "implementation",
            TranscriptKind.STDOUT,
        )
        assert not canonical.startswith(TEMP_FILE_PREFIX)
        assert f"{TEMP_FILE_PREFIX}{canonical}" != canonical


class TestDuplicateJsonKeysRejected:
    """An ambiguous persisted record has no single correct reading, so it fails closed."""

    def test_a_duplicate_top_level_key_is_refused(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        document = store.state_path.read_text(encoding="utf-8")
        tampered = document.replace(
            '"workflow_state": "PREFLIGHT"',
            '"workflow_state": "PREFLIGHT",\n  "workflow_state": "DONE"',
            1,
        )
        assert tampered != document
        store.state_path.write_text(tampered, encoding="utf-8")
        with pytest.raises(StateCorrupted, match="duplicate JSON object key"):
            store.load()

    def test_a_nested_duplicate_key_is_refused_too(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        record = durable_record(
            worktree,
            "a" * 40,
            workflow_state=RunStatus.IMPLEMENTING,
            provider_runs=[provider_run(1)],
        )
        store.publish(record, lock=held_lock)
        document = store.state_path.read_text(encoding="utf-8")
        tampered = document.replace(
            '"provider": "claude"', '"provider": "claude",\n      "provider": "codex"', 1
        )
        assert tampered != document
        store.state_path.write_text(tampered, encoding="utf-8")
        with pytest.raises(StateCorrupted, match="duplicate JSON object key"):
            store.load()

    def test_the_same_document_without_the_duplicate_loads(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        document = store.state_path.read_text(encoding="utf-8")
        store.state_path.write_text(document, encoding="utf-8")
        assert store.load().workflow_state is RunStatus.PREFLIGHT

    def test_a_document_that_is_not_json_is_refused(self, store: RunStateStore) -> None:
        store.state_path.write_text("workflow_state: PREFLIGHT\n", encoding="utf-8")
        with pytest.raises(StateCorrupted, match="not valid JSON"):
            store.load()

    def test_a_json_document_that_is_not_an_object_is_refused(self, store: RunStateStore) -> None:
        store.state_path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(StateCorrupted, match="not a JSON object"):
            store.load()

    def test_a_symlinked_state_document_is_refused_rather_than_followed(
        self, store: RunStateStore, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere.json"
        elsewhere.write_text('{"schema_version": 1}', encoding="utf-8")
        store.state_path.symlink_to(elsewhere)
        with pytest.raises(StateCorrupted):
            store.load()


class TestStateSchemaUnknownIsAHardRefusal:
    """Section 11: an unknown `schema_version` is never a best-effort read."""

    def _tamper(self, store: RunStateStore, **changes: Any) -> None:
        document = json.loads(store.state_path.read_text(encoding="utf-8"))
        for key, value in changes.items():
            if value is None:
                del document[key]
            else:
                document[key] = value
        store.state_path.write_text(json.dumps(document), encoding="utf-8")

    def test_a_future_schema_version_is_refused_with_the_typed_code(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        self._tamper(store, schema_version=STATE_SCHEMA_VERSION + 1)

        with pytest.raises(StateSchemaUnknown) as refusal:
            store.load()
        assert refusal.value.stop_reason is StopReason.STATE_SCHEMA_UNKNOWN

    def test_a_missing_schema_version_is_refused_as_unknown(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        self._tamper(store, schema_version=None)
        with pytest.raises(StateSchemaUnknown):
            store.load()

    def test_a_string_schema_version_is_refused_rather_than_coerced(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        store.publish(durable_record(worktree, "a" * 40), lock=held_lock)
        self._tamper(store, schema_version=str(STATE_SCHEMA_VERSION))
        with pytest.raises(StateSchemaUnknown):
            store.load()

    def test_the_version_is_checked_before_the_rest_of_the_schema(
        self, store: RunStateStore
    ) -> None:
        """A future record whose other fields are unrecognizable is still `STATE_SCHEMA_UNKNOWN`.

        Checking the version first is what makes the refusal honest: the record was written by a
        schema this build does not know, which is a different fact from "these fields are wrong".
        """
        store.state_path.write_text(
            json.dumps({"schema_version": 99, "whatever": {"shape": [1, 2]}}), encoding="utf-8"
        )
        with pytest.raises(StateSchemaUnknown):
            store.load()

    def test_a_known_version_with_a_broken_body_is_a_different_failure(
        self, store: RunStateStore
    ) -> None:
        store.state_path.write_text(
            json.dumps({"schema_version": STATE_SCHEMA_VERSION, "unknown_field": 1}),
            encoding="utf-8",
        )
        with pytest.raises(StateCorrupted, match="not a valid run record"):
            store.load()


class TestSecretShapedProviderOutputNeverReachesDisk:
    """Invariant 2 and section 17a: the referenced file itself must be clean."""

    def test_a_secret_shaped_transcript_appears_nowhere_under_the_state_root(
        self, store: RunStateStore, held_lock: RunLock, isolated_home: Path
    ) -> None:
        store.write_transcript(
            sequence=store.next_transcript_sequence(lock=held_lock),
            label="implementation",
            kind=TranscriptKind.STDOUT,
            text=SECRET_STDOUT,
            moment=datetime.now(UTC),
            lock=held_lock,
        )
        on_disk = every_byte_under(isolated_home)
        for literal in SECRET_LITERALS:
            assert literal not in on_disk

    def test_the_surviving_text_carries_a_redaction_marker(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        write = store.write_transcript(
            sequence=1,
            label="implementation",
            kind=TranscriptKind.STDOUT,
            text=SECRET_STDOUT,
            moment=datetime.now(UTC),
            lock=held_lock,
        )
        text = (store.run_directory / str(write.relative_path)).read_text(encoding="utf-8")
        assert "[REDACTED:github_token]" in text
        assert "Running the milestone..." in text

    def test_a_secret_reaching_the_state_document_is_redacted_too(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        """Section 17a's boundary covers state bytes, not only transcript bytes."""
        record = durable_record(
            worktree,
            "a" * 40,
            deferred_findings=[
                Finding(
                    finding_id="finding-1",
                    severity=FindingSeverity.LOW,
                    title="A provider echoed a credential",
                    summary=f"The provider printed {SECRET_LITERALS[0]} in its summary.",
                )
            ],
        )
        store.publish(record, lock=held_lock)
        assert SECRET_LITERALS[0] not in store.state_path.read_text(encoding="utf-8")
        assert "[REDACTED:github_token]" in store.state_path.read_text(encoding="utf-8")

    def test_the_write_result_reports_what_it_neutralized(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        clean = store.write_transcript(
            sequence=1,
            label="implementation",
            kind=TranscriptKind.STDERR,
            text="no secrets here\n",
            moment=datetime.now(UTC),
            lock=held_lock,
        )
        assert isinstance(clean, RedactedWrite)
        assert clean.redacted is False
        assert clean.findings == []

    def test_the_boundary_has_no_parameter_that_skips_redaction(self) -> None:
        import inspect

        parameters = inspect.signature(write_redacted_artifact).parameters
        assert set(parameters) == {"path", "text", "relative_path"}


class TestRedactionEventIsRecordedNotSilent:
    """Section 17a: a redaction produces a counted, visible finding on the run record."""

    def _redacted_write(self, store: RunStateStore, lock: RunLock) -> RedactedWrite:
        return store.write_transcript(
            sequence=store.next_transcript_sequence(lock=lock),
            label="implementation",
            kind=TranscriptKind.STDOUT,
            text=SECRET_STDOUT,
            moment=datetime.now(UTC),
            lock=lock,
        )

    def test_a_redaction_becomes_a_counted_deferred_finding(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        write = self._redacted_write(store, held_lock)
        assert write.redacted is True

        record = store.record_redaction_findings(durable_record(worktree, "a" * 40), [write])
        assert record.deferred_findings
        for finding in record.deferred_findings:
            assert finding.finding_id.startswith("redaction-")
            assert finding.severity in DEFERRED_SEVERITIES
            assert finding.status is FindingStatus.DEFERRED
            assert str(write.relative_path) in finding.summary

    def test_the_finding_names_the_pattern_and_the_occurrence_count(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        write = self._redacted_write(store, held_lock)
        record = store.record_redaction_findings(durable_record(worktree, "a" * 40), [write])
        assert "github_token" in {finding.pattern_name for finding in write.findings}
        for redaction in write.findings:
            matching = [
                finding
                for finding in record.deferred_findings
                if finding.finding_id.endswith(redaction.pattern_name)
            ]
            assert matching, f"{redaction.pattern_name} produced no visible finding"
            assert f"{redaction.occurrences} occurrence(s)" in matching[0].summary

    def test_the_finding_never_carries_the_secret_itself(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        write = self._redacted_write(store, held_lock)
        record = store.record_redaction_findings(durable_record(worktree, "a" * 40), [write])
        rendered = record.model_dump_json()
        for literal in SECRET_LITERALS:
            assert literal not in rendered

    def test_a_clean_artifact_records_nothing(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        write = store.write_transcript(
            sequence=1,
            label="implementation",
            kind=TranscriptKind.STDOUT,
            text="nothing secret here\n",
            moment=datetime.now(UTC),
            lock=held_lock,
        )
        record = durable_record(worktree, "a" * 40)
        assert store.record_redaction_findings(record, [write]) == record

    def test_repeated_redactions_append_rather_than_collide(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        writes = [self._redacted_write(store, held_lock) for _ in range(2)]
        record = store.record_redaction_findings(durable_record(worktree, "a" * 40), writes)
        again = store.record_redaction_findings(record, writes)
        identifiers = [finding.finding_id for finding in again.deferred_findings]
        assert len(identifiers) == len(set(identifiers))
        assert len(identifiers) == 2 * len(record.deferred_findings)

    def test_the_visible_event_survives_publication(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        write = self._redacted_write(store, held_lock)
        record = store.record_redaction_findings(durable_record(worktree, "a" * 40), [write])
        store.publish(record, lock=held_lock)
        assert store.load().deferred_findings == record.deferred_findings


class TestAllStateWritesGoThroughTheRedactionBoundary:
    """Section 17a, asserted at the AST level over the whole package.

    Three claims, each checked independently. No module outside `state.py` and `lock.py` holds a
    filesystem-mutation primitive at all. Inside `state.py` every one of them sits in
    `publish_atomically` or its byte-loop helper. And `publish_atomically` has exactly one caller,
    `write_redacted_artifact`, which calls `redact_text` first -- so "every persisted byte passed
    redaction" is a call graph rather than a convention.

    `lock.py` is the one documented carve-out, bounded by its own test module: a flock's metadata
    must be written to the descriptor that holds it, and it carries no provider byte.
    """

    MUTATION_PRIMITIVES = frozenset(
        {
            "write",
            "replace",
            "rename",
            "ftruncate",
            "truncate",
            "unlink",
            "write_text",
            "write_bytes",
            "writelines",
        }
    )

    @staticmethod
    def _enclosing(tree: ast.Module) -> dict[ast.AST, str | None]:
        mapping: dict[ast.AST, str | None] = {}

        def visit(node: ast.AST, current: str | None) -> None:
            for child in ast.iter_child_nodes(node):
                name = (
                    child.name
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                    else current
                )
                mapping[child] = name
                visit(child, name)

        visit(tree, None)
        return mapping

    def _mutations(self, source: Path) -> list[tuple[str | None, str]]:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        enclosing = self._enclosing(tree)
        found: list[tuple[str | None, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if isinstance(target, ast.Attribute) and target.attr in self.MUTATION_PRIMITIVES:
                found.append((enclosing.get(node), target.attr))
            if isinstance(target, ast.Name) and target.id == "open":
                found.append((enclosing.get(node), "open"))
        return found

    def test_only_the_state_and_lock_modules_write_to_the_filesystem(self) -> None:
        offenders = {
            source.name: self._mutations(source)
            for source in sorted(PACKAGE_DIRECTORY.rglob("*.py"))
            if self._mutations(source)
        }
        assert set(offenders) <= {"state.py", "lock.py"}, offenders

    def test_every_write_in_state_py_sits_inside_the_publication_protocol(self) -> None:
        functions = {name for name, _ in self._mutations(STATE_SOURCE)}
        assert functions <= {"_write_all", "publish_atomically"}, functions

    def test_publish_atomically_has_exactly_one_caller_and_it_redacts_first(self) -> None:
        callers: list[str | None] = []
        for source in sorted(PACKAGE_DIRECTORY.rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            enclosing = self._enclosing(tree)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "publish_atomically"
                ):
                    callers.append(enclosing.get(node))
        assert callers == ["write_redacted_artifact"]

    def test_the_boundary_calls_the_shared_redactor(self) -> None:
        tree = ast.parse(STATE_SOURCE.read_text(encoding="utf-8"))
        boundary = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "write_redacted_artifact"
        )
        called = {
            node.func.id
            for node in ast.walk(boundary)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "redact_text" in called
        assert "publish_atomically" in called

    def test_the_redactor_is_the_shared_one_and_is_not_reimplemented(self) -> None:
        """DEC-016-008: reuse, never a second redactor that can drift from the first."""
        tree = ast.parse(STATE_SOURCE.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "ai_workflow_engine.successor_planning.redaction" in imported


class TestP9TranscriptSequenceNumberPreventsCollision:
    """Prototype defect P-9: second-granularity naming could silently overwrite a transcript."""

    def test_two_transcripts_of_one_role_in_one_second_are_two_files(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        moment = datetime(2026, 8, 5, 21, 38, 55, tzinfo=UTC)
        first = store.write_transcript(
            sequence=store.next_transcript_sequence(lock=held_lock),
            label="implementation",
            kind=TranscriptKind.STDOUT,
            text="first invocation\n",
            moment=moment,
            lock=held_lock,
        )
        second = store.write_transcript(
            sequence=store.next_transcript_sequence(lock=held_lock),
            label="implementation",
            kind=TranscriptKind.STDOUT,
            text="second invocation\n",
            moment=moment,
            lock=held_lock,
        )

        assert first.relative_path != second.relative_path
        first_text = (store.run_directory / str(first.relative_path)).read_text(encoding="utf-8")
        second_text = (store.run_directory / str(second.relative_path)).read_text(encoding="utf-8")
        assert first_text == "first invocation\n"
        assert second_text == "second invocation\n"
        transcripts = [
            path.name
            for path in store.transcripts_directory.iterdir()
            if not path.name.startswith(".")
        ]
        assert sorted(transcripts) == sorted(
            [Path(str(first.relative_path)).name, Path(str(second.relative_path)).name]
        )

    def test_the_sequence_leads_the_name_and_is_zero_padded(self) -> None:
        moment = datetime(2026, 8, 5, 21, 38, 55, tzinfo=UTC)
        assert (
            transcript_name(7, moment, "implementation", TranscriptKind.STDOUT)
            == "0007-20260805T213855Z-implementation.stdout.txt"
        )
        assert (
            transcript_name(7, moment, "review", TranscriptKind.PROMPT)
            == "0007-20260805T213855Z-review.prompt.md"
        )

    def test_the_counter_survives_a_crash_and_a_resume(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        """Recorded durably rather than held in memory, so a fresh process does not restart at 1."""
        moment = datetime.now(UTC)
        for _ in range(3):
            store.write_transcript(
                sequence=store.next_transcript_sequence(lock=held_lock),
                label="implementation",
                kind=TranscriptKind.STDOUT,
                text="output\n",
                moment=moment,
                lock=held_lock,
            )
        resumed = RunStateStore.pin(
            repository_id=M03_IDENTITY, run_id=M03_RUN_ID, repository_root=worktree
        )
        assert resumed.next_transcript_sequence(lock=held_lock) == 4

    def test_an_allocation_lost_to_a_crash_is_never_handed_out_twice(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        """A number allocated but never used is wasted, which is the safe side of the trade."""
        allocated = store.next_transcript_sequence(lock=held_lock)
        # The runner dies here, before the transcript that number was for is written.
        assert store.next_transcript_sequence(lock=held_lock) == allocated + 1

    def test_an_unreadable_counter_refuses_rather_than_restarting_the_numbering(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        store.next_transcript_sequence(lock=held_lock)
        (store.transcripts_directory / TRANSCRIPT_SEQUENCE_FILE_NAME).write_text(
            "not a number", encoding="utf-8"
        )
        with pytest.raises(StateCorrupted, match="transcript sequence"):
            store.next_transcript_sequence(lock=held_lock)

    def test_allocating_a_sequence_requires_the_run_lock(self, store: RunStateStore) -> None:
        with pytest.raises(StatePublicationFailure, match="run lock"):
            store.next_transcript_sequence(lock=lock_for_store(store))

    def test_the_counter_is_never_mistaken_for_a_transcript(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        store.next_transcript_sequence(lock=held_lock)
        counter = store.transcripts_directory / TRANSCRIPT_SEQUENCE_FILE_NAME
        assert counter.is_file()
        with pytest.raises(StatePublicationFailure, match="transcript label"):
            transcript_name(1, datetime.now(UTC), counter.name, TranscriptKind.STDOUT)

    def test_all_four_transcript_kinds_share_one_sequence(
        self, store: RunStateStore, held_lock: RunLock
    ) -> None:
        moment = datetime.now(UTC)
        sequence = store.next_transcript_sequence(lock=held_lock)
        written = [
            store.write_transcript(
                sequence=sequence,
                label="review",
                kind=kind,
                text="content\n",
                moment=moment,
                lock=held_lock,
            )
            for kind in TranscriptKind
        ]
        assert len({write.relative_path for write in written}) == len(TranscriptKind)
        assert store.next_transcript_sequence(lock=held_lock) == sequence + 1

    def test_a_transcript_label_cannot_smuggle_a_path_segment(self) -> None:
        moment = datetime.now(UTC)
        for label in ("../escape", "impl/ementation", "Implementation", "impl ementation"):
            with pytest.raises(StatePublicationFailure, match="usable transcript label"):
                transcript_name(1, moment, label, TranscriptKind.STDOUT)

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(StatePublicationFailure, match="UTC"):
            transcript_name(
                1, datetime(2026, 8, 5, 21, 38, 55), "implementation", TranscriptKind.STDOUT
            )

    def test_the_sequence_is_bounded(self) -> None:
        moment = datetime.now(UTC)
        for sequence in (0, -1, MAX_TRANSCRIPT_SEQUENCE + 1):
            with pytest.raises(StatePublicationFailure, match="sequence range"):
                transcript_name(sequence, moment, "implementation", TranscriptKind.STDOUT)

    def test_an_absent_transcript_directory_cannot_allocate_at_all(self, tmp_path: Path) -> None:
        """Fail closed: a missing directory is a broken run, not a run that starts again at 1."""
        with pytest.raises(StatePublicationFailure):
            next_transcript_sequence(tmp_path / "never-created")


class TestResumeIsIdempotent:
    """Section 13: running `resume` twice with no intervening change is a no-op success."""

    def test_two_consecutive_resumes_return_equal_decisions(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        head = inspector.head_sha()
        store.publish(
            durable_record(worktree, head, workflow_state=RunStatus.MILESTONE_COMPLETE),
            lock=held_lock,
        )
        first = store.resume(inspector.evidence())
        second = store.resume(inspector.evidence())
        assert first == second
        assert first.action is ResumeAction.CONTINUE

    def test_resume_writes_nothing(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(durable_record(worktree, inspector.head_sha()), lock=held_lock)
        before = {
            path: path.read_bytes()
            for path in sorted(store.run_directory.rglob("*"))
            if path.is_file()
        }
        store.resume(inspector.evidence())
        store.resume(inspector.evidence())
        after = {
            path: path.read_bytes()
            for path in sorted(store.run_directory.rglob("*"))
            if path.is_file()
        }
        assert after == before

    def test_resume_leaves_the_worktree_exactly_as_found(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        head = inspector.head_sha()
        store.publish(durable_record(worktree, head), lock=held_lock)
        store.resume(inspector.evidence())
        assert git(worktree, "status", "--porcelain") == ""
        assert git(worktree, "rev-parse", "HEAD") == head


class TestResumeReconcilesBeforeReinvoking:
    """`MACHINE_GATES.md` section 2a: reconcile persisted evidence before repeating an effect."""

    def test_an_invocation_that_left_no_trace_may_be_repeated(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.PROVIDER_WAIT,
                current_milestone="AUTO-016-M03",
                provider_runs=[in_flight_provider_run()],
            ),
            lock=held_lock,
        )
        record_intent(store, held_lock, inspector)

        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.REINVOKE_PROVIDER
        assert decision.may_reinvoke_provider is True
        assert decision.unaccounted_changed_paths == []
        assert decision.fingerprint_changed_paths == []

    def test_an_invocation_whose_effect_is_visible_requires_reconciliation_first(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.PROVIDER_WAIT,
                current_milestone="AUTO-016-M03",
                provider_runs=[in_flight_provider_run()],
            ),
            lock=held_lock,
        )
        record_intent(store, held_lock, inspector)
        # The provider really did write a file before the runner crashed.
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")

        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.RECONCILE_REQUIRED
        assert decision.may_reinvoke_provider is False
        assert decision.unaccounted_changed_paths == ["produced.py"]
        # Nothing is reverted, restored, checked out or deleted: the tree is left as found.
        assert (worktree / "produced.py").read_text(encoding="utf-8") == "value = 1\n"

    def test_a_diff_the_record_already_accounts_for_is_not_unaccounted(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.PROVIDER_WAIT,
                current_milestone="AUTO-016-M03",
                changed_paths=["produced.py"],
                provider_runs=[in_flight_provider_run()],
            ),
            lock=held_lock,
        )
        record_intent(store, held_lock, inspector)

        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.REINVOKE_PROVIDER

    def test_a_completed_invocation_is_never_repeated(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.MILESTONE_COMPLETE,
                current_milestone="AUTO-016-M03",
                provider_runs=[provider_run(1)],
            ),
            lock=held_lock,
        )
        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.CONTINUE

    def test_being_in_an_invoking_state_alone_never_decides_it(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """Appearance alone never advances the workflow; the persisted evidence decides."""
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.IMPLEMENTING,
                current_milestone="AUTO-016-M03",
            ),
            lock=held_lock,
        )
        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.CONTINUE
        assert "No provider invocation was in flight" in decision.reason


class TestPathDigestsDistinguishEveryRelevantState:
    """A fingerprint is only as honest as the four states its per-path digest can report."""

    def test_a_regular_file_digests_to_its_bytes(self, worktree: Path) -> None:
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        expected = hashlib.sha256(b"value = 1\n").hexdigest()
        assert digest_repository_path(worktree, "produced.py") == expected

    def test_a_missing_path_is_absent_and_not_unreadable(self, worktree: Path) -> None:
        """Absent is a real observation: a staged deletion is absent before *and* after."""
        assert digest_repository_path(worktree, "never-existed.py") == ABSENT_DIGEST

    def test_a_symlink_is_refused_rather_than_followed(self, worktree: Path) -> None:
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        (worktree / "link.py").symlink_to(worktree / "produced.py")
        assert digest_repository_path(worktree, "link.py") == UNREADABLE_DIGEST

    def test_a_symlinked_parent_component_is_refused_too(self, worktree: Path) -> None:
        (worktree / "real").mkdir()
        (worktree / "real" / "produced.py").write_text("value = 1\n", encoding="utf-8")
        (worktree / "linked").symlink_to(worktree / "real")
        assert digest_repository_path(worktree, "linked/produced.py") == UNREADABLE_DIGEST

    def test_a_directory_where_a_file_was_is_unreadable(self, worktree: Path) -> None:
        (worktree / "produced.py").mkdir()
        assert digest_repository_path(worktree, "produced.py") == UNREADABLE_DIGEST

    def test_nothing_outside_the_repository_is_ever_read(self, worktree: Path) -> None:
        """Traversal is refused at normalization, so the join can only ever descend."""
        outside = worktree.parent / "outside.py"
        outside.write_text("secret = 1\n", encoding="utf-8")
        for shape in ("../outside.py", "/etc/hostname", "a/../../outside.py"):
            assert digest_repository_path(worktree, shape) == UNREADABLE_DIGEST

    def test_an_unreadable_digest_never_compares_equal_even_to_itself(self) -> None:
        pinned = RepositoryFingerprint(
            repository_identity=M03_IDENTITY,
            branch="main",
            head_sha="a" * 40,
            path_digests={"produced.py": UNREADABLE_DIGEST},
        )
        assert fingerprint_delta(pinned, pinned) == ["produced.py"]

    def test_an_absent_digest_does_compare_equal_to_itself(self) -> None:
        """Otherwise a run whose diff carries a deletion could never resume at all."""
        pinned = RepositoryFingerprint(
            repository_identity=M03_IDENTITY,
            branch="main",
            head_sha="a" * 40,
            path_digests={"removed.py": ABSENT_DIGEST},
        )
        assert fingerprint_delta(pinned, pinned) == []


class TestFingerprintsAreDeterministic:
    """The whole mechanism rests on two observations of one repository digesting identically."""

    def test_two_fingerprints_of_an_unchanged_repository_are_equal(
        self, worktree: Path, inspector: GitReadOnlyInspector
    ) -> None:
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        first = fingerprint_repository(worktree, inspector.evidence())
        second = fingerprint_repository(worktree, inspector.evidence())
        assert first == second
        assert first.digest == second.digest
        assert fingerprint_delta(first, second) == []

    def test_the_digest_is_stable_across_key_insertion_order(self) -> None:
        forwards = RepositoryFingerprint(
            repository_identity=M03_IDENTITY,
            branch="main",
            head_sha="a" * 40,
            path_digests={"b.py": "0" * 64, "a.py": "1" * 64},
        )
        backwards = RepositoryFingerprint(
            repository_identity=M03_IDENTITY,
            branch="main",
            head_sha="a" * 40,
            path_digests={"a.py": "1" * 64, "b.py": "0" * 64},
        )
        assert forwards.digest == backwards.digest
        assert list(forwards.path_digests) == ["a.py", "b.py"]

    def test_a_content_change_moves_the_digest(
        self, worktree: Path, inspector: GitReadOnlyInspector
    ) -> None:
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        before = fingerprint_repository(worktree, inspector.evidence())
        (worktree / "produced.py").write_text("value = 2\n", encoding="utf-8")
        after = fingerprint_repository(worktree, inspector.evidence())
        assert before.digest != after.digest
        assert fingerprint_delta(before, after) == ["produced.py"]

    def test_a_rewrite_of_a_known_path_leaves_the_name_set_identical(
        self, worktree: Path, inspector: GitReadOnlyInspector
    ) -> None:
        """The blind spot itself, in isolation: names say nothing, digests say everything."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        before = fingerprint_repository(worktree, inspector.evidence())
        names_before = set(inspector.changed_paths())

        (worktree / "produced.py").write_text("value = 2\n", encoding="utf-8")
        after = fingerprint_repository(worktree, inspector.evidence())

        assert set(inspector.changed_paths()) == names_before
        assert fingerprint_delta(before, after) == ["produced.py"]

    def test_a_fingerprint_stores_digests_and_never_contents(
        self, worktree: Path, inspector: GitReadOnlyInspector
    ) -> None:
        secret = "ghp_0123456789abcdefghijklmnopqrstuvwxyzAB"
        (worktree / "produced.py").write_text(f'TOKEN = "{secret}"\n', encoding="utf-8")
        fingerprint = fingerprint_repository(worktree, inspector.evidence())
        assert secret not in fingerprint.model_dump_json()
        assert set(fingerprint.path_digests) == {"produced.py"}


class TestTheInvocationIntentIsDurableEvidence:
    """Section 13: the intent is published atomically, under the lock, outside the repository."""

    def test_the_intent_lands_at_its_exact_name_under_the_run_directory(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        intent = record_intent(store, held_lock, inspector)
        assert store.provider_intent_path.name == PROVIDER_INTENT_FILE_NAME
        assert store.provider_intent_path.parent == store.run_directory
        assert store.load_provider_intent() == intent
        # Invariant 7: the evidence never lands inside the repository it is evidence about.
        assert not str(store.provider_intent_path).startswith(str(worktree.resolve()) + os.sep)

    def test_an_unlocked_write_is_refused(
        self, store: RunStateStore, inspector: GitReadOnlyInspector
    ) -> None:
        """Defect P-6: the intent is a state write like any other and demands the run lock."""
        with pytest.raises(StatePublicationFailure, match="run lock"):
            store.record_provider_intent(
                pending=in_flight_provider_run(),
                evidence=inspector.evidence(),
                recorded_at="2026-08-05T21:39:00Z",
                lock=lock_for_store(store),
            )
        assert not store.provider_intent_path.exists()

    def test_a_run_that_never_invoked_has_no_intent(self, store: RunStateStore) -> None:
        assert store.load_provider_intent() is None

    def test_a_later_intent_replaces_the_earlier_one_atomically(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        record_intent(store, held_lock, inspector, sequence=1)
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        second = record_intent(store, held_lock, inspector, sequence=2)

        loaded = store.load_provider_intent()
        assert loaded == second
        assert loaded is not None and loaded.sequence == 2
        # Never a torn document, and never an orphan temp file left where a reader can see one.
        leftovers = [
            path.name
            for path in store.run_directory.iterdir()
            if path.name.startswith(TEMP_FILE_PREFIX)
        ]
        assert leftovers == []

    def test_a_torn_or_tampered_intent_is_refused_rather_than_guessed_at(
        self, store: RunStateStore, held_lock: RunLock, inspector: GitReadOnlyInspector
    ) -> None:
        record_intent(store, held_lock, inspector)
        payload = json.loads(store.provider_intent_path.read_text(encoding="utf-8"))
        publish_atomically(
            store.provider_intent_path,
            (json.dumps(payload)[:-1] + f', "sequence": {payload["sequence"]}}}').encode("utf-8"),
        )
        with pytest.raises(StateCorrupted, match="duplicate JSON object key"):
            store.load_provider_intent()


class TestResumeReconcilesOnContentNotOnPathNames:
    """AUTO016-IMPL-001: a rewrite of an already-known path must stop an automatic re-invocation.

    Persisting the invocation intent before the process exists is necessary and was already done;
    what was missing was the other half. Resume compared the observed changed-path *names*
    against the names the record held, so a provider whose effect was to rewrite a file already
    in that set produced an empty unaccounted list, and `REINVOKE_PROVIDER` repeated an effectful
    call over work that had already landed. Every case below is decided on content digests.
    """

    def crashed_mid_invocation(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
        *,
        changed_paths: list[str] | None = None,
    ) -> None:
        """Publish a run that died with one invocation in flight, evidence and all."""
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.PROVIDER_WAIT,
                current_milestone="AUTO-016-M03",
                changed_paths=changed_paths or [],
                provider_runs=[in_flight_provider_run()],
            ),
            lock=held_lock,
        )
        record_intent(store, held_lock, inspector)

    def test_a_crash_before_the_provider_touched_anything_permits_a_safe_retry(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """The one case that may be repeated, and it is proved rather than assumed."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        self.crashed_mid_invocation(
            store, held_lock, worktree, inspector, changed_paths=["produced.py"]
        )

        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.REINVOKE_PROVIDER
        assert decision.may_reinvoke_provider is True
        assert decision.fingerprint_changed_paths == []
        assert "byte for byte" in decision.reason

    def test_a_provider_that_created_a_new_file_then_crashed_is_not_retried(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        self.crashed_mid_invocation(store, held_lock, worktree, inspector)
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")

        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.RECONCILE_REQUIRED
        assert decision.may_reinvoke_provider is False
        assert decision.unaccounted_changed_paths == ["produced.py"]
        assert decision.fingerprint_changed_paths == ["produced.py"]

    def test_a_provider_that_rewrote_an_already_known_path_then_crashed_is_not_retried(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """The defect verbatim: the name set is unchanged and the content is not."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        self.crashed_mid_invocation(
            store, held_lock, worktree, inspector, changed_paths=["produced.py"]
        )
        (worktree / "produced.py").write_text("value = 2\n", encoding="utf-8")

        decision = store.resume(inspector.evidence())
        assert decision.observed_changed_paths == ["produced.py"]
        assert decision.unaccounted_changed_paths == [], "the name-only reading sees nothing"
        assert decision.fingerprint_changed_paths == ["produced.py"]
        assert decision.action is ResumeAction.RECONCILE_REQUIRED
        assert decision.may_reinvoke_provider is False

    def test_a_provider_that_deleted_an_already_known_path_then_crashed_is_not_retried(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """A deletion leaves the changed-path set *smaller*, which a difference of names misses."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        self.crashed_mid_invocation(
            store, held_lock, worktree, inspector, changed_paths=["produced.py"]
        )
        (worktree / "produced.py").unlink()

        decision = store.resume(inspector.evidence())
        assert decision.observed_changed_paths == []
        assert decision.unaccounted_changed_paths == []
        assert decision.fingerprint_changed_paths == ["produced.py"]
        assert decision.action is ResumeAction.RECONCILE_REQUIRED

    def test_an_invocation_with_no_fingerprint_bound_to_it_is_not_retried(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """Absence of evidence is never evidence of absence on the one path that repeats effects."""
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.PROVIDER_WAIT,
                current_milestone="AUTO-016-M03",
                provider_runs=[in_flight_provider_run()],
            ),
            lock=held_lock,
        )
        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.RECONCILE_REQUIRED
        assert "no durable pre-invocation fingerprint" in decision.reason

    def test_an_intent_from_an_earlier_invocation_is_not_evidence_about_this_one(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(
            durable_record(
                worktree,
                inspector.head_sha(),
                workflow_state=RunStatus.PROVIDER_WAIT,
                current_milestone="AUTO-016-M03",
                provider_runs=[in_flight_provider_run(7)],
            ),
            lock=held_lock,
        )
        record_intent(store, held_lock, inspector, sequence=3)

        decision = store.resume(inspector.evidence())
        assert decision.action is ResumeAction.RECONCILE_REQUIRED
        assert "no durable pre-invocation fingerprint" in decision.reason

    def test_partial_work_is_preserved_across_the_refusal(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """Section 5: a tripped gate stops with the tree untouched. Nothing is reverted or lost."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        self.crashed_mid_invocation(
            store, held_lock, worktree, inspector, changed_paths=["produced.py"]
        )
        (worktree / "produced.py").write_text("half a milestone of real work\n", encoding="utf-8")
        (worktree / "also-produced.py").write_text("more of it\n", encoding="utf-8")

        assert store.resume(inspector.evidence()).action is ResumeAction.RECONCILE_REQUIRED

        assert (worktree / "produced.py").read_text(encoding="utf-8") == (
            "half a milestone of real work\n"
        )
        assert (worktree / "also-produced.py").read_text(encoding="utf-8") == "more of it\n"
        assert git(worktree, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    def test_the_detection_writes_nothing_and_repeats_identically(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """Fingerprinting does not make resume a writer, and two calls still agree exactly."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        self.crashed_mid_invocation(
            store, held_lock, worktree, inspector, changed_paths=["produced.py"]
        )
        (worktree / "produced.py").write_text("value = 2\n", encoding="utf-8")

        before = {
            path: path.read_bytes()
            for path in sorted(store.run_directory.rglob("*"))
            if path.is_file()
        }
        first = store.resume(inspector.evidence())
        second = store.resume(inspector.evidence())
        after = {
            path: path.read_bytes()
            for path in sorted(store.run_directory.rglob("*"))
            if path.is_file()
        }
        assert first == second
        assert after == before

    def test_a_counter_is_never_touched_by_the_detection(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """Section 19: reconciling evidence is not a round, so it consumes no budget."""
        (worktree / "produced.py").write_text("value = 1\n", encoding="utf-8")
        self.crashed_mid_invocation(
            store, held_lock, worktree, inspector, changed_paths=["produced.py"]
        )
        (worktree / "produced.py").write_text("value = 2\n", encoding="utf-8")
        before = {field: getattr(store.load(), field) for field in RUN_COUNTER_FIELDS}

        decision = store.resume(inspector.evidence())

        assert decision.action is ResumeAction.RECONCILE_REQUIRED
        assert {field: getattr(decision.record, field) for field in RUN_COUNTER_FIELDS} == before
        assert {field: getattr(store.load(), field) for field in RUN_COUNTER_FIELDS} == before

    def test_branch_and_head_drift_still_refuse_ahead_of_any_fingerprinting(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        """Section 4 items 3 and 4 are unchanged and still come first: drift is never reconciled."""
        self.crashed_mid_invocation(store, held_lock, worktree, inspector)
        git(worktree, "checkout", "-b", "someone-elses-branch")

        with pytest.raises(ResumeRefused) as refusal:
            store.resume(inspector.evidence())
        assert refusal.value.stop_reason is StopReason.BRANCH_MISMATCH


class TestResumeRejectsBranchDrift:
    """Section 4 item 3: the branch is re-verified at every gate, and drift is a stop."""

    def test_a_different_branch_is_a_typed_refusal(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(durable_record(worktree, inspector.head_sha()), lock=held_lock)
        git(worktree, "checkout", "-b", "someone-elses-branch")

        with pytest.raises(ResumeRefused) as refusal:
            store.resume(inspector.evidence())
        assert refusal.value.stop_reason is StopReason.BRANCH_MISMATCH
        assert [drift.aspect for drift in refusal.value.drift] == ["branch"]

    def test_the_refusal_never_re_binds_the_run_to_the_new_branch(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(durable_record(worktree, inspector.head_sha()), lock=held_lock)
        git(worktree, "checkout", "-b", "someone-elses-branch")
        with pytest.raises(ResumeRefused):
            store.resume(inspector.evidence())
        assert store.load().expected_branch == "main"


class TestResumeRejectsHeadDrift:
    """Section 4 item 4: `HEAD` equals the pinned baseline at start and at every gate."""

    def test_a_new_commit_is_a_typed_refusal(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        head = inspector.head_sha()
        store.publish(durable_record(worktree, head), lock=held_lock)

        (worktree / "another.txt").write_text("another\n", encoding="utf-8")
        git(worktree, "add", "another.txt")
        git(worktree, "commit", "-m", "someone committed under the runner")

        with pytest.raises(ResumeRefused) as refusal:
            store.resume(inspector.evidence())
        assert refusal.value.stop_reason is StopReason.HEAD_DRIFT
        assert refusal.value.drift[0].expected == head

    def test_a_repository_identity_mismatch_takes_precedence(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path
    ) -> None:
        """Three aspects, one pass, and section 4's own order decides the reported code."""
        store.publish(durable_record(worktree, "b" * 40), lock=held_lock)
        evidence = RepositoryEvidence(
            repository_root=str(worktree),
            repository_identity=OTHER_IDENTITY,
            branch="not-main",
            head_sha="c" * 40,
        )
        with pytest.raises(ResumeRefused) as refusal:
            store.resume(evidence)
        assert refusal.value.stop_reason is StopReason.REPOSITORY_IDENTITY_MISMATCH
        assert [drift.aspect for drift in refusal.value.drift] == [
            "repository_identity",
            "branch",
            "head_sha",
        ]


class TestResumeRejectsSchemaVersionUnknown:
    """Section 13 reads the durable record first, so an unknown schema stops resume outright."""

    def test_resume_refuses_a_record_from_an_unknown_schema(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(durable_record(worktree, inspector.head_sha()), lock=held_lock)
        document = json.loads(store.state_path.read_text(encoding="utf-8"))
        document["schema_version"] = STATE_SCHEMA_VERSION + 7
        store.state_path.write_text(json.dumps(document), encoding="utf-8")

        with pytest.raises(StateSchemaUnknown) as refusal:
            store.resume(inspector.evidence())
        assert refusal.value.stop_reason is StopReason.STATE_SCHEMA_UNKNOWN

    def test_resume_refuses_an_ambiguous_record(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        inspector: GitReadOnlyInspector,
    ) -> None:
        store.publish(durable_record(worktree, inspector.head_sha()), lock=held_lock)
        document = store.state_path.read_text(encoding="utf-8")
        store.state_path.write_text(
            document.replace(
                '"expected_branch": "main"',
                '"expected_branch": "main",\n  "expected_branch": "other"',
                1,
            ),
            encoding="utf-8",
        )
        with pytest.raises(StateCorrupted):
            store.resume(inspector.evidence())


class TestStateModuleBoundary:
    """Section 22 invariant 6 and section 28: nothing forbidden is imported or referenced."""

    def test_no_agentos_import_exists_in_state_py(self) -> None:
        tree = ast.parse(STATE_SOURCE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        assert not [
            name
            for name in imported
            if name.split(".")[0] in {"agentos_workflow", "agentos_dashboard"}
        ]

    def test_the_prototype_is_never_referenced_by_path(self) -> None:
        """Section 28: the prototype's `state/` directory is not read, imported or named."""
        source = STATE_SOURCE.read_text(encoding="utf-8")
        assert "auto015-runner" not in source
        assert "auto015_runner" not in source

    def test_no_shell_is_reachable_from_the_durability_layer(self) -> None:
        tree = ast.parse(STATE_SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword):
                assert node.arg != "shell"
            if isinstance(node, ast.Attribute):
                assert node.attr != "system"
