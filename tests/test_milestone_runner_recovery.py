"""AUTO-016 section 13: the four recovery commands, their guards, ledgers and budget effects.

Everything here is driven the way the runner drives it. The run directory is a real
:class:`RunStateStore` pinned under a redirected `HOME`, the transcripts are real files written
through section 17a's production write boundary under a real `flock` hold, and the branch and
`HEAD` a ledger entry records come from a real `git init` repository read by the production
inspector. Nothing is mocked: the hash match `reconcile-milestone` turns on is computed over bytes
that are actually on disk, and the "prior transcripts are preserved" assertion compares the
transcript directory's real contents before and after.

The named classes the milestone requires are all present:
`TestReconcileRequiresHashMatch`, `TestReopenPreservesBudgetsAndTranscripts`,
`TestReopenScopeRulingRecorded`, `TestRecoverFailedReviewRestoresExactlyOne`,
`TestRecoverFailedReviewRefusedOnCompletedReview`, `TestRevalidateLeavesBudgetsUntouched`,
`TestRecoveryCannotCloseBlocker`, `TestRecoveryCannotReachCommitApproval` and
`TestRecoveryLedgersAppendOnly`, alongside `TestRecoveryNeverOpensPrototypeState` (DEC-016-006),
`TestNoProviderInvokedByRecovery` and `TestP10FailureClassRecordedNotRegrepped`.

One fixture note. `RunRecord` requires a `stop_reason` at `HUMAN_INTERVENTION_REQUIRED`, and the
contract names no stop code for a malformed provider result or a provider authentication failure --
`models.StopReason` transcribes only the twelve codes the contract writes in backticks. The
fixtures therefore pin `OUT_OF_MILESTONE_SCOPE`, which is a real code the vocabulary has, and
nothing in `recovery.py` turns on which code a stopped run recorded: every command clears the stop
rather than reading it.
"""

import ast
import builtins
import hashlib
import io
import json
import os
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_workflow_engine.milestone_runner.git_inspect import (
    GitReadOnlyInspector,
    RepositoryEvidence,
)
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    PLAN_SCHEMA_VERSION,
    RUN_COUNTER_FIELDS,
    STATE_SCHEMA_VERSION,
    Finding,
    FindingSeverity,
    FindingStatus,
    MilestoneSpec,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
    RecoveryCommand,
    RecoveryLedgerEntry,
    RunRecord,
    RunStatus,
    StopReason,
)
from ai_workflow_engine.milestone_runner.plan import MilestonePlan
from ai_workflow_engine.milestone_runner.recovery import (
    FORBIDDEN_RECOVERY_POST_STATES,
    RECONSTRUCTED_FROM_VERIFIED_EVIDENCE,
    RECOVERY_COMMANDS,
    RECOVERY_ENTRY_STATES,
    RECOVERY_LEDGER_FIELDS,
    RECOVERY_POST_STATES,
    RecoveryContext,
    RecoveryCoordinator,
    RecoveryOutcome,
    RecoveryRefused,
    append_recovery_ledger_entry,
    digest_of_file,
    reconcile_milestone,
    recover_failed_review,
    reject_forbidden_recovery_effect,
    reject_ledger_rewrite,
    reopen_milestone,
    revalidate_correction,
)
from ai_workflow_engine.milestone_runner.state import (
    TRANSCRIPTS_DIRECTORY,
    RunStateStore,
    TranscriptKind,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_SOURCE = (
    REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner" / "recovery.py"
)

#: The same disposable repository the M03-M06 suites pin, so every suite in this package addresses
#: one artifact root rather than inventing its own.
REMOTE = "https://github.com/example/demo-repo.git"
IDENTITY = "demo-repo--2059e82cffa9"
RUN_ID = "auto016-20260805T213855Z-7fea75fc"

MILESTONE = "AUTO-016-M07"
EARLIER_MILESTONE = "AUTO-016-M06"

MOMENT = datetime(2026, 8, 6, 9, 15, 30, tzinfo=UTC)
RECORDED_AT = "2026-08-06T09:15:30Z"

#: The result a provider actually emitted for the milestone being reconciled -- the recorded real
#: run's case, "semantically valid but wrapped in a Markdown code fence" (section 6).
FENCED_RESULT = (
    "I finished the milestone.\n"
    "```yaml\n"
    "AUTO016_MILESTONE_RESULT\n"
    "milestone: AUTO-016-M07\n"
    "status: COMPLETE\n"
    "END_AUTO016_MILESTONE_RESULT\n"
    "```\n"
)

#: A stderr transcript whose text carries every substring the prototype's recovery re-grepped for
#: (defect P-10). Nothing in `recovery.py` may consult it.
MISLEADING_STDERR = (
    "The reviewer noted that a 401 response, a websocket upgrade and a dropped connection are "
    "each worth handling explicitly in the retry path.\n"
)


def code_string_literals() -> list[str]:
    """Every string literal in `recovery.py` that is not a docstring.

    Docstrings are excluded by node identity rather than by value: `ast.get_docstring` dedents
    what it returns, so comparing values would silently keep every docstring in the set and make
    the assertions below vacuous.
    """
    tree = ast.parse(RECOVERY_SOURCE.read_text(encoding="utf-8"))
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    ]


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


# --------------------------------------------------------------------------------------
# Fixtures: a real repository, a real run directory, real transcripts
# --------------------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `Path.home()` at a disposable directory, so no test writes into the real one."""
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
    git(repository, "remote", "add", "origin", REMOTE)
    (repository / "kept.txt").write_text("kept\n", encoding="utf-8")
    git(repository, "add", "kept.txt")
    git(repository, "commit", "-m", "initial")
    return repository


@pytest.fixture
def evidence(worktree: Path) -> RepositoryEvidence:
    """One independent observation, taken by the production read-only inspector."""
    return GitReadOnlyInspector(worktree).evidence()


@pytest.fixture
def context(evidence: RepositoryEvidence) -> RecoveryContext:
    return RecoveryContext.observed(evidence, MOMENT)


@pytest.fixture
def store(isolated_home: Path, worktree: Path) -> RunStateStore:
    return RunStateStore.pin(repository_id=IDENTITY, run_id=RUN_ID, repository_root=worktree)


@pytest.fixture
def held_lock(store: RunStateStore) -> Iterator[RunLock]:
    lock = RunLock(
        run_id=store.run_id,
        repository_identity=store.repository_id,
        artifact_root=store.artifact_root,
    )
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


@pytest.fixture
def coordinator(store: RunStateStore) -> RecoveryCoordinator:
    return RecoveryCoordinator(store)


def write_attempt(
    store: RunStateStore,
    lock: RunLock,
    *,
    sequence: int,
    milestone_id: str,
    stdout: str,
    stderr: str = "",
) -> ProviderRunRecord:
    """Write one implementation attempt's real transcript triple and record it.

    The transcripts go through `state.py`'s production boundary under a held lock, exactly as a
    real invocation would write them, so what the reconciliation hashes is a file the runner wrote.
    """
    written: dict[TranscriptKind, str] = {}
    for kind, text in (
        (TranscriptKind.PROMPT, f"The prompt for {milestone_id}.\n"),
        (TranscriptKind.STDOUT, stdout),
        (TranscriptKind.STDERR, stderr),
    ):
        result = store.write_transcript(
            sequence=sequence,
            label="implementation",
            kind=kind,
            text=text,
            moment=MOMENT,
            lock=lock,
        )
        assert result.relative_path is not None
        written[kind] = result.relative_path
    return ProviderRunRecord(
        sequence=sequence,
        role=ProviderRole.IMPLEMENTATION,
        provider="claude",
        milestone_id=milestone_id,
        started_at="2026-08-06T09:00:00Z",
        completed_at="2026-08-06T09:14:00Z",
        duration_ms=840_000,
        exit_code=0,
        prompt_path=written[TranscriptKind.PROMPT],
        stdout_path=written[TranscriptKind.STDOUT],
        stderr_path=written[TranscriptKind.STDERR],
    )


def review_attempt(
    *,
    sequence: int,
    failure_class: ProviderFailureClass | None,
) -> ProviderRunRecord:
    """One review invocation, with or without a failure class persisted at invocation time."""
    return ProviderRunRecord(
        sequence=sequence,
        role=ProviderRole.REVIEW,
        provider="codex",
        started_at="2026-08-06T09:10:00Z",
        completed_at="2026-08-06T09:11:00Z",
        duration_ms=60_000,
        exit_code=0 if failure_class is None else 1,
        failure_class=failure_class,
        prompt_path=f"transcripts/{sequence:04d}-20260806T091000Z-review.prompt.md",
        stdout_path=f"transcripts/{sequence:04d}-20260806T091000Z-review.stdout.txt",
        stderr_path=f"transcripts/{sequence:04d}-20260806T091000Z-review.stderr.txt",
    )


def blocker(finding_id: str = "R-1") -> Finding:
    return Finding(
        finding_id=finding_id,
        severity=FindingSeverity.HIGH,
        title=f"Blocker {finding_id}",
        summary=f"The reviewer's account of {finding_id}.",
        status=FindingStatus.OPEN,
    )


def deferred(finding_id: str = "R-2") -> Finding:
    return Finding(
        finding_id=finding_id,
        severity=FindingSeverity.LOW,
        title=f"Deferred {finding_id}",
        summary=f"The reviewer's account of {finding_id}.",
        status=FindingStatus.DEFERRED,
    )


def stopped_record(worktree: Path, head_sha: str, **overrides: Any) -> RunRecord:
    """A run stopped at `HUMAN_INTERVENTION_REQUIRED`, consistent with the `store` fixture."""
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": RUN_ID,
        "repository_root": str(worktree),
        "repository_identity": IDENTITY,
        "expected_branch": "main",
        "baseline_sha": head_sha,
        "contract_sha256": "56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e",
        "workflow_state": RunStatus.HUMAN_INTERVENTION_REQUIRED,
        "stop_reason": StopReason.OUT_OF_MILESTONE_SCOPE,
        "created_at": "2026-08-06T08:00:00Z",
        "updated_at": "2026-08-06T09:14:05Z",
        "current_milestone": MILESTONE,
        "completed_milestones": [EARLIER_MILESTONE],
    }
    payload.update(overrides)
    return RunRecord(**payload)


def counters(record: RunRecord) -> dict[str, int]:
    """The full counter set of section 19, as one comparable mapping."""
    return {name: int(getattr(record, name)) for name in sorted(RUN_COUNTER_FIELDS)}


def ledgers(record: RunRecord) -> dict[str, list[dict[str, Any]]]:
    """All four append-only ledgers, as plain JSON, so equality is byte-level."""
    payload = json.loads(record.model_dump_json())
    return {field: payload[field] for field in sorted(RECOVERY_LEDGER_FIELDS.values())}


def tree_snapshot(root: Path) -> dict[str, str]:
    """Every file under `root`, by relative path and SHA-256 -- the transcripts included."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def milestone_spec(milestone_id: str, allowed_files: Sequence[str]) -> MilestoneSpec:
    return MilestoneSpec(
        schema_version=PLAN_SCHEMA_VERSION,
        milestone_id=milestone_id,
        title=f"Milestone {milestone_id}",
        objective=f"Deliver {milestone_id}.",
        depends_on=[],
        contract_sections=["section 13 idempotent resume and recovery"],
        allowed_files=list(allowed_files),
        forbidden_files=["agentos_workflow/**"],
        required_symbols=["milestone_runner.recovery.RecoveryCoordinator"],
        explicit_exclusions=["No provider is invoked by any recovery command."],
        acceptance_criteria=["reconcile-milestone touches no budget."],
        focused_verification=[
            {"command": ["pytest", "-q", "tests/test_milestone_runner_recovery.py"]}
        ],
        completion_evidence=["All focused verification commands PASS."],
    )


RECOVERY_PATH = "src/ai_workflow_engine/milestone_runner/recovery.py"
TEST_PATH = "tests/test_milestone_runner_recovery.py"
COVERAGE = (RECOVERY_PATH, TEST_PATH)


def plan_of(*specs: MilestoneSpec) -> MilestonePlan:
    return MilestonePlan(
        milestones=specs,
        source_paths=tuple(f"/plans/{spec.milestone_id}.yaml" for spec in specs),
    )


@pytest.fixture
def reconcilable(
    store: RunStateStore, held_lock: RunLock, worktree: Path, evidence: RepositoryEvidence
) -> tuple[RunRecord, Path]:
    """A stopped run whose milestone attempt left a real, non-conforming transcript on disk."""
    attempt = write_attempt(
        store, held_lock, sequence=1, milestone_id=MILESTONE, stdout=FENCED_RESULT
    )
    record = stopped_record(worktree, evidence.head_sha, provider_runs=[attempt])
    return record, store.run_directory / attempt.stdout_path


def result_file(tmp_path: Path, text: str) -> Path:
    """The result file an operator hands to `reconcile-milestone`."""
    path = tmp_path / "operator-result.txt"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------
# Section 13 -- reconcile-milestone
# --------------------------------------------------------------------------------------


class TestReconcileRequiresHashMatch:
    """The result must be byte-identical to the transcript the run itself persisted."""

    def test_matching_digest_reconciles_and_records_the_evidence_honestly(
        self,
        coordinator: RecoveryCoordinator,
        reconcilable: tuple[RunRecord, Path],
        context: RecoveryContext,
        tmp_path: Path,
    ) -> None:
        record, transcript = reconcilable
        offered = result_file(tmp_path, transcript.read_text(encoding="utf-8"))

        outcome = coordinator.reconcile_milestone(
            record,
            milestone_id=MILESTONE,
            reason="The result was semantically valid but wrapped in a Markdown code fence.",
            result_path=offered,
            context=context,
        )

        assert outcome.reconstructed_from_verified_evidence is True
        assert outcome.evidence_digest == digest_of_file(transcript)
        assert outcome.record.workflow_state is RunStatus.FOCUSED_VERIFYING
        assert outcome.record.stop_reason is None
        entry = outcome.record.reconciliations[-1]
        assert entry.command is RecoveryCommand.RECONCILE_MILESTONE
        assert RECONSTRUCTED_FROM_VERIFIED_EVIDENCE in entry.reason
        assert outcome.evidence_digest in entry.reason

    def test_the_record_says_reconstructed_rather_than_complete(
        self,
        coordinator: RecoveryCoordinator,
        reconcilable: tuple[RunRecord, Path],
        context: RecoveryContext,
        tmp_path: Path,
    ) -> None:
        """An honest reconciliation is not an unqualified success (section 13).

        The milestone is not moved into `completed_milestones` and the run does not land in
        `MILESTONE_COMPLETE`: it returns to `FOCUSED_VERIFYING`, where the deterministic commands
        decide whether the milestone passed.
        """
        record, transcript = reconcilable
        outcome = coordinator.reconcile_milestone(
            record,
            milestone_id=MILESTONE,
            reason="A fenced but semantically valid result.",
            result_path=result_file(tmp_path, transcript.read_text(encoding="utf-8")),
            context=context,
        )
        assert MILESTONE not in outcome.record.completed_milestones
        assert outcome.record.completed_milestones == record.completed_milestones
        assert outcome.record.workflow_state is not RunStatus.MILESTONE_COMPLETE
        assert "no milestone is claimed to have passed" in outcome.record.reconciliations[-1].reason

    def test_one_differing_byte_is_refused_and_leaves_the_run_exactly_as_it_was(
        self,
        coordinator: RecoveryCoordinator,
        reconcilable: tuple[RunRecord, Path],
        context: RecoveryContext,
        tmp_path: Path,
    ) -> None:
        record, transcript = reconcilable
        tampered = transcript.read_text(encoding="utf-8").replace("COMPLETE", "COMPLETE ")
        before = record.model_dump_json()

        with pytest.raises(RecoveryRefused, match="digests to"):
            coordinator.reconcile_milestone(
                record,
                milestone_id=MILESTONE,
                reason="A result somebody re-authored afterwards.",
                result_path=result_file(tmp_path, tampered),
                context=context,
            )

        assert record.model_dump_json() == before
        assert record.reconciliations == []

    def test_a_milestone_with_no_recorded_attempt_has_nothing_to_match(
        self,
        coordinator: RecoveryCoordinator,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
        tmp_path: Path,
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha)
        with pytest.raises(RecoveryRefused, match="no implementation invocation"):
            coordinator.reconcile_milestone(
                record,
                milestone_id=MILESTONE,
                reason="Nothing was ever invoked for this milestone.",
                result_path=result_file(tmp_path, FENCED_RESULT),
                context=context,
            )

    def test_another_milestone_than_the_one_the_run_stopped_on_is_refused(
        self,
        reconcilable: tuple[RunRecord, Path],
        context: RecoveryContext,
    ) -> None:
        record, _ = reconcilable
        with pytest.raises(RecoveryRefused, match="not the milestone this run stopped on"):
            reconcile_milestone(
                record,
                milestone_id=EARLIER_MILESTONE,
                reason="Reconciling some other milestone.",
                result_digest="a" * 64,
                transcript_digest="a" * 64,
                context=context,
            )

    def test_reconcile_touches_no_budget(
        self,
        coordinator: RecoveryCoordinator,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
        tmp_path: Path,
    ) -> None:
        """Section 13's budget effect for `reconcile-milestone` is "None"."""
        attempt = write_attempt(
            store, held_lock, sequence=1, milestone_id=MILESTONE, stdout=FENCED_RESULT
        )
        record = stopped_record(
            worktree,
            evidence.head_sha,
            provider_runs=[attempt],
            review_attempts=2,
            successful_review_rounds=1,
            provider_failure_count=1,
            correction_round=1,
            closure_round=1,
        )
        transcript = store.run_directory / attempt.stdout_path

        outcome = coordinator.reconcile_milestone(
            record,
            milestone_id=MILESTONE,
            reason="A fenced but semantically valid result.",
            result_path=result_file(tmp_path, transcript.read_text(encoding="utf-8")),
            context=context,
        )

        assert counters(outcome.record) == counters(record)
        assert dict(outcome.budgets_touched) == {}
        assert outcome.record.reconciliations[-1].budgets_touched == {}

    def test_a_symlinked_result_file_is_refused_rather_than_followed(
        self,
        reconcilable: tuple[RunRecord, Path],
        tmp_path: Path,
    ) -> None:
        target = result_file(tmp_path, FENCED_RESULT)
        link = tmp_path / "linked-result.txt"
        link.symlink_to(target)
        with pytest.raises(RecoveryRefused, match="could not be read"):
            digest_of_file(link)


# --------------------------------------------------------------------------------------
# Section 13 -- reopen-milestone
# --------------------------------------------------------------------------------------


class TestReopenPreservesBudgetsAndTranscripts:
    """`completed_milestones`, every budget and every prior attempt transcript survive."""

    def test_every_budget_and_every_completed_milestone_are_preserved(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
    ) -> None:
        first = write_attempt(
            store, held_lock, sequence=1, milestone_id=MILESTONE, stdout="not: [parseable yaml\n"
        )
        second = write_attempt(
            store, held_lock, sequence=2, milestone_id=MILESTONE, stdout="still not parseable\n"
        )
        record = stopped_record(
            worktree,
            evidence.head_sha,
            provider_runs=[first, second],
            review_attempts=1,
            successful_review_rounds=1,
            provider_failure_count=1,
            correction_round=1,
            closure_round=0,
        )
        before = tree_snapshot(store.run_directory / TRANSCRIPTS_DIRECTORY)

        outcome = reopen_milestone(
            record,
            milestone_id=MILESTONE,
            reason="The milestone result was not parseable YAML.",
            human_owner_scope_ruling="The Human Owner rules the milestone plan is corrected.",
            context=context,
        )

        assert counters(outcome.record) == counters(record)
        assert outcome.record.completed_milestones == [EARLIER_MILESTONE]
        assert outcome.record.workflow_state is RunStatus.IMPLEMENTING
        assert outcome.record.current_milestone == MILESTONE
        assert outcome.record.stop_reason is None
        # Both prior attempts stay on the record, and both transcript triples stay on disk.
        assert [run.sequence for run in outcome.record.provider_runs] == [1, 2]
        assert tree_snapshot(store.run_directory / TRANSCRIPTS_DIRECTORY) == before
        assert len(before) == 6

    def test_reopen_is_also_reachable_from_a_failed_focused_verification(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        """`MILESTONE_FAILED` is the state section 10 added for exactly this recovery."""
        record = stopped_record(
            worktree,
            evidence.head_sha,
            workflow_state=RunStatus.MILESTONE_FAILED,
            stop_reason=None,
        )
        outcome = reopen_milestone(
            record,
            milestone_id=MILESTONE,
            reason="The focused verification failed and the milestone is reopened.",
            human_owner_scope_ruling="The Human Owner rules the milestone is reattempted.",
            context=context,
        )
        assert outcome.record.workflow_state is RunStatus.IMPLEMENTING
        assert outcome.record.reopenings[-1].pre_state is RunStatus.MILESTONE_FAILED

    def test_a_completed_milestone_is_not_reopened(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha)
        with pytest.raises(RecoveryRefused, match="recorded complete"):
            reopen_milestone(
                record,
                milestone_id=EARLIER_MILESTONE,
                reason="Reopening work the run already accepted.",
                human_owner_scope_ruling="A ruling that cannot authorize this.",
                context=context,
            )


class TestRecoveryClearsAReconciliationStop:
    """AUTO016-IMPL-001: the content-fingerprint stop is a stop like any other, not a dead end.

    Resume refuses to repeat a provider invocation whose durable pre-invocation fingerprint no
    longer describes the repository. That refusal has to be *clearable*, or a crash mid-milestone
    would end the run: section 13's whole design is that an automatic repetition is replaced by an
    explicit, governed act, not that the run stops forever. These assert the second half of that.
    """

    def interrupted(
        self, store: RunStateStore, held_lock: RunLock, worktree: Path, head_sha: str
    ) -> RunRecord:
        """A run stopped for reconciliation, with the invocation's evidence still on disk."""
        in_flight = ProviderRunRecord(
            sequence=1,
            role=ProviderRole.IMPLEMENTATION,
            provider="claude",
            milestone_id=MILESTONE,
            started_at="2026-08-06T09:00:00Z",
            completed_at=None,
            duration_ms=0,
            prompt_path="transcripts/0001-20260806T090000Z-implementation.prompt.md",
            stdout_path="transcripts/0001-20260806T090000Z-implementation.stdout.txt",
            stderr_path="transcripts/0001-20260806T090000Z-implementation.stderr.txt",
        )
        store.record_provider_intent(
            pending=in_flight,
            evidence=GitReadOnlyInspector(worktree).evidence(),
            recorded_at="2026-08-06T09:00:00Z",
            lock=held_lock,
        )
        return stopped_record(worktree, head_sha, provider_runs=[in_flight])

    def test_reopen_clears_the_stop_and_touches_no_budget(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
    ) -> None:
        record = self.interrupted(store, held_lock, worktree, evidence.head_sha)

        outcome = reopen_milestone(
            record,
            milestone_id=MILESTONE,
            reason="The interrupted invocation's partial work was reviewed by the Human Owner.",
            human_owner_scope_ruling="The Human Owner rules the milestone is reattempted.",
            context=context,
        )

        assert outcome.record.workflow_state is RunStatus.IMPLEMENTING
        assert outcome.record.stop_reason is None
        assert counters(outcome.record) == counters(record)
        assert outcome.record.reopenings[-1].budgets_touched == {}

    def test_the_interrupted_attempt_is_kept_as_evidence(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
    ) -> None:
        """Nothing is discarded: the incomplete row and the intent are both still there."""
        record = self.interrupted(store, held_lock, worktree, evidence.head_sha)
        intent_before = store.provider_intent_path.read_bytes()

        outcome = reopen_milestone(
            record,
            milestone_id=MILESTONE,
            reason="The interrupted invocation's partial work was reviewed by the Human Owner.",
            human_owner_scope_ruling="The Human Owner rules the milestone is reattempted.",
            context=context,
        )

        assert [run.sequence for run in outcome.record.provider_runs] == [1]
        assert outcome.record.provider_runs[0].completed_at is None
        assert store.provider_intent_path.read_bytes() == intent_before


class TestReopenScopeRulingRecorded:
    """The explicit Human Owner scope ruling is required and durably recorded."""

    def test_the_ruling_lands_on_the_ledger_entry(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        ruling = "The Human Owner rules that M07 owns recovery.py and its test module only."
        outcome = reopen_milestone(
            stopped_record(worktree, evidence.head_sha),
            milestone_id=MILESTONE,
            reason="milestone_plan_correction",
            human_owner_scope_ruling=ruling,
            context=context,
        )
        entry = outcome.record.reopenings[-1]
        assert entry.human_owner_ruling == ruling
        assert entry.milestone_id == MILESTONE
        assert entry.branch == evidence.branch
        assert entry.head_sha == evidence.head_sha
        assert entry.recorded_at == RECORDED_AT

    def test_the_ruling_lands_on_the_corrected_milestone(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        """Section 14 reserves `human_owner_scope_ruling` for exactly this command."""
        ruling = "The Human Owner rules the recovery test module moves to M07."
        plan = plan_of(
            milestone_spec(EARLIER_MILESTONE, [RECOVERY_PATH]),
            milestone_spec(MILESTONE, [TEST_PATH]),
        )
        outcome = reopen_milestone(
            stopped_record(worktree, evidence.head_sha),
            milestone_id=MILESTONE,
            reason="milestone_plan_correction",
            human_owner_scope_ruling=ruling,
            context=context,
            corrected_plan=plan,
            required_coverage=COVERAGE,
        )
        assert outcome.corrected_plan is not None
        corrected = {
            spec.milestone_id: spec.human_owner_scope_ruling
            for spec in outcome.corrected_plan.milestones
        }
        assert corrected == {MILESTONE: ruling, EARLIER_MILESTONE: None}

    def test_a_corrected_plan_that_widens_the_surface_is_refused(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        """Section 4 item 6 still has to hold exactly: an extra path is a widening."""
        plan = plan_of(
            milestone_spec(EARLIER_MILESTONE, [RECOVERY_PATH]),
            milestone_spec(MILESTONE, [TEST_PATH, "src/ai_workflow_engine/cli.py"]),
        )
        with pytest.raises(RecoveryRefused, match="no longer covers the authorized surface"):
            reopen_milestone(
                stopped_record(worktree, evidence.head_sha),
                milestone_id=MILESTONE,
                reason="milestone_plan_correction",
                human_owner_scope_ruling="A ruling that cannot widen an allowlist.",
                context=context,
                corrected_plan=plan,
                required_coverage=COVERAGE,
            )

    def test_a_corrected_plan_that_leaves_a_gap_is_refused(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        plan = plan_of(milestone_spec(MILESTONE, [TEST_PATH]))
        with pytest.raises(RecoveryRefused, match="required path"):
            reopen_milestone(
                stopped_record(worktree, evidence.head_sha),
                milestone_id=MILESTONE,
                reason="milestone_plan_correction",
                human_owner_scope_ruling="A ruling that cannot leave the surface uncovered.",
                context=context,
                corrected_plan=plan,
                required_coverage=COVERAGE,
            )

    def test_a_corrected_plan_without_coverage_to_check_against_is_refused(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        plan = plan_of(milestone_spec(MILESTONE, list(COVERAGE)))
        with pytest.raises(RecoveryRefused, match="required_coverage"):
            reopen_milestone(
                stopped_record(worktree, evidence.head_sha),
                milestone_id=MILESTONE,
                reason="milestone_plan_correction",
                human_owner_scope_ruling="A ruling with no coverage to re-prove.",
                context=context,
                corrected_plan=plan,
            )

    def test_an_empty_ruling_is_refused(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        with pytest.raises(RecoveryRefused, match="human_owner_scope_ruling"):
            reopen_milestone(
                stopped_record(worktree, evidence.head_sha),
                milestone_id=MILESTONE,
                reason="milestone_plan_correction",
                human_owner_scope_ruling="   ",
                context=context,
            )


# --------------------------------------------------------------------------------------
# Section 13 -- recover-failed-review
# --------------------------------------------------------------------------------------


@pytest.fixture
def failed_review(worktree: Path, evidence: RepositoryEvidence) -> RunRecord:
    """A run whose review budget was consumed and whose review recorded an auth failure."""
    return stopped_record(
        worktree,
        evidence.head_sha,
        current_milestone=None,
        provider_runs=[review_attempt(sequence=1, failure_class=ProviderFailureClass.AUTH_FAILED)],
        review_attempts=1,
        successful_review_rounds=1,
        provider_failure_count=1,
    )


class TestRecoverFailedReviewRestoresExactlyOne:
    """Exactly one review budget comes back, on a typed class and an explicit ruling."""

    def test_one_budget_is_restored_and_no_other_counter_moves(
        self, failed_review: RunRecord, context: RecoveryContext
    ) -> None:
        outcome = recover_failed_review(
            failed_review,
            classification=ProviderFailureClass.AUTH_FAILED,
            human_owner_ruling="The Human Owner rules the token expiry consumed no review.",
            reason="classification: token_expired",
            context=context,
        )

        before = counters(failed_review)
        after = counters(outcome.record)
        assert after["successful_review_rounds"] == before["successful_review_rounds"] - 1
        others = {name for name in RUN_COUNTER_FIELDS if name != "successful_review_rounds"}
        assert {name: after[name] for name in others} == {name: before[name] for name in others}
        assert dict(outcome.budgets_touched) == {"successful_review_rounds": -1}
        assert outcome.record.workflow_state is RunStatus.REVIEWING

    def test_the_entry_records_the_typed_class_and_the_ruling(
        self, failed_review: RunRecord, context: RecoveryContext
    ) -> None:
        ruling = "The Human Owner rules the authentication failure is not a consumed review."
        outcome = recover_failed_review(
            failed_review,
            classification=ProviderFailureClass.AUTH_FAILED,
            human_owner_ruling=ruling,
            reason="classification: token_expired",
            context=context,
        )
        entry = outcome.record.review_recoveries[-1]
        assert entry.classification is ProviderFailureClass.AUTH_FAILED
        assert entry.human_owner_ruling == ruling
        assert entry.budgets_touched == {"successful_review_rounds": -1}
        assert entry.pre_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert entry.post_state is RunStatus.REVIEWING

    def test_a_class_the_run_did_not_record_is_refused(
        self, failed_review: RunRecord, context: RecoveryContext
    ) -> None:
        with pytest.raises(RecoveryRefused, match="recorded AUTH_FAILED"):
            recover_failed_review(
                failed_review,
                classification=ProviderFailureClass.TRANSPORT_FAILED,
                human_owner_ruling="A ruling about a failure that did not happen.",
                reason="The operator named the wrong class.",
                context=context,
            )

    def test_an_unspent_review_budget_has_nothing_to_restore(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        record = stopped_record(
            worktree,
            evidence.head_sha,
            provider_runs=[
                review_attempt(sequence=1, failure_class=ProviderFailureClass.AUTH_FAILED)
            ],
            review_attempts=1,
            successful_review_rounds=0,
            provider_failure_count=1,
        )
        with pytest.raises(RecoveryRefused, match="No review budget is consumed"):
            recover_failed_review(
                record,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="A ruling with no budget to restore.",
                reason="Nothing was consumed.",
                context=context,
            )

    def test_an_empty_ruling_is_refused(
        self, failed_review: RunRecord, context: RecoveryContext
    ) -> None:
        with pytest.raises(RecoveryRefused, match="human_owner_ruling"):
            recover_failed_review(
                failed_review,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="",
                reason="A recovery with no explicit Human Owner ruling.",
                context=context,
            )

    def test_a_second_recovery_cannot_mint_a_budget_that_was_never_spent(
        self, failed_review: RunRecord, context: RecoveryContext
    ) -> None:
        """Restoring is a decrement, so repeating it runs out rather than granting a review."""
        first = recover_failed_review(
            failed_review,
            classification=ProviderFailureClass.AUTH_FAILED,
            human_owner_ruling="The Human Owner rules the token expiry consumed no review.",
            reason="classification: token_expired",
            context=context,
        )
        stopped_again = first.record.model_copy(
            update={
                "workflow_state": RunStatus.HUMAN_INTERVENTION_REQUIRED,
                "stop_reason": StopReason.OUT_OF_MILESTONE_SCOPE,
            }
        )
        with pytest.raises(RecoveryRefused, match="No review budget is consumed"):
            recover_failed_review(
                stopped_again,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="A second ruling on the same failure.",
                reason="Replaying the recovery.",
                context=context,
            )


class TestRecoverFailedReviewRefusedOnCompletedReview:
    """A review that returned a verdict recorded no failure class, and is unreachable."""

    def test_a_completed_review_is_refused(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        record = stopped_record(
            worktree,
            evidence.head_sha,
            current_milestone=None,
            provider_runs=[review_attempt(sequence=1, failure_class=None)],
            review_attempts=1,
            successful_review_rounds=1,
            blocking_findings=[blocker()],
        )
        before = record.model_dump_json()

        with pytest.raises(RecoveryRefused, match="completed and returned a verdict"):
            recover_failed_review(
                record,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="A ruling that cannot reach a completed review.",
                reason="Attempting to recover a review that actually ran.",
                context=context,
            )

        assert record.model_dump_json() == before
        assert record.review_recoveries == []

    def test_a_run_with_no_review_at_all_is_refused(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha, successful_review_rounds=1)
        with pytest.raises(RecoveryRefused, match="no review invocation"):
            recover_failed_review(
                record,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="A ruling about a review that never ran.",
                reason="No review invocation exists.",
                context=context,
            )


class TestP10FailureClassRecordedNotRegrepped:
    """Recovery consults the persisted class and never re-interprets provider output."""

    def test_the_recorded_class_decides_even_when_the_stderr_text_says_otherwise(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
    ) -> None:
        """A transcript full of `401`, `websocket` and `connection` changes nothing.

        The prototype re-grepped exactly those substrings out of stderr (defect P-10). Here the
        recorded class is `TRANSPORT_FAILED`, the operator's ruling names `AUTH_FAILED`, and the
        refusal follows the record rather than the text a model authored.
        """
        attempt = write_attempt(
            store,
            held_lock,
            sequence=1,
            milestone_id=MILESTONE,
            stdout="irrelevant\n",
            stderr=MISLEADING_STDERR,
        )
        misleading = (store.run_directory / attempt.stderr_path).read_text(encoding="utf-8")
        assert "401" in misleading and "websocket" in misleading

        record = stopped_record(
            worktree,
            evidence.head_sha,
            provider_runs=[
                attempt,
                review_attempt(sequence=2, failure_class=ProviderFailureClass.TRANSPORT_FAILED),
            ],
            successful_review_rounds=1,
        )

        with pytest.raises(RecoveryRefused, match="recorded TRANSPORT_FAILED"):
            recover_failed_review(
                record,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="A ruling derived from reading the stderr text.",
                reason="The stderr mentions a 401.",
                context=context,
            )

        outcome = recover_failed_review(
            record,
            classification=ProviderFailureClass.TRANSPORT_FAILED,
            human_owner_ruling="The Human Owner rules the transport failure consumed no review.",
            reason="The recorded class is TRANSPORT_FAILED.",
            context=context,
        )
        assert outcome.record.review_recoveries[-1].classification is (
            ProviderFailureClass.TRANSPORT_FAILED
        )

    def test_the_module_never_matches_a_failure_substring(self) -> None:
        for needle in ("401", "websocket", "connection"):
            offenders = [literal for literal in code_string_literals() if needle in literal]
            assert offenders == [], needle


# --------------------------------------------------------------------------------------
# Section 13 -- revalidate-correction
# --------------------------------------------------------------------------------------


@pytest.fixture
def post_correction(worktree: Path, evidence: RepositoryEvidence) -> RunRecord:
    """A run stopped on "tests failed after the correction round" (section 6)."""
    return stopped_record(
        worktree,
        evidence.head_sha,
        review_attempts=1,
        successful_review_rounds=1,
        provider_failure_count=0,
        correction_round=1,
        closure_round=0,
        blocking_findings=[blocker("R-1"), blocker("R-2")],
        deferred_findings=[deferred("R-3")],
    )


class TestRevalidateLeavesBudgetsUntouched:
    """Every counter comes out exactly as it went in -- the full set, compared as one."""

    def test_the_full_counter_set_is_identical_before_and_after(
        self, post_correction: RunRecord, context: RecoveryContext
    ) -> None:
        before = counters(post_correction)
        outcome = revalidate_correction(
            post_correction,
            reason="tests failed after the correction round",
            context=context,
        )
        after = counters(outcome.record)
        assert after == before
        assert set(after) == set(RUN_COUNTER_FIELDS)
        assert dict(outcome.budgets_touched) == {}
        assert outcome.record.revalidations[-1].budgets_touched == {}
        assert outcome.record.workflow_state is RunStatus.CLOSURE_VERIFYING
        assert outcome.record.stop_reason is None

    def test_the_already_open_blockers_are_the_limit(
        self, post_correction: RunRecord, context: RecoveryContext
    ) -> None:
        outcome = revalidate_correction(
            post_correction,
            reason="Revalidating the two open blockers.",
            context=context,
            blocker_ids=["R-1", "R-2"],
        )
        assert [finding.status for finding in outcome.record.blocking_findings] == [
            FindingStatus.OPEN,
            FindingStatus.OPEN,
        ]

    def test_an_unknown_blocker_id_cannot_be_introduced(
        self, post_correction: RunRecord, context: RecoveryContext
    ) -> None:
        with pytest.raises(RecoveryRefused, match="cannot introduce a finding"):
            revalidate_correction(
                post_correction,
                reason="Naming a finding the run never saw.",
                context=context,
                blocker_ids=["R-99"],
            )

    def test_a_deferred_finding_is_not_an_open_blocker(
        self, post_correction: RunRecord, context: RecoveryContext
    ) -> None:
        with pytest.raises(RecoveryRefused, match="open blockers"):
            revalidate_correction(
                post_correction,
                reason="Naming a deferred finding as a blocker.",
                context=context,
                blocker_ids=["R-3"],
            )

    def test_a_run_with_no_correction_round_has_nothing_to_revalidate(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha)
        with pytest.raises(RecoveryRefused, match="No correction round"):
            revalidate_correction(record, reason="There was no correction round.", context=context)


# --------------------------------------------------------------------------------------
# Section 13's closing constraint
# --------------------------------------------------------------------------------------


def every_outcome(
    coordinator: RecoveryCoordinator,
    store: RunStateStore,
    lock: RunLock,
    worktree: Path,
    evidence: RepositoryEvidence,
    context: RecoveryContext,
    tmp_path: Path,
) -> list[RecoveryOutcome]:
    """Run all four recovery commands, each against a run that genuinely admits it."""
    attempt = write_attempt(store, lock, sequence=1, milestone_id=MILESTONE, stdout=FENCED_RESULT)
    transcript = store.run_directory / attempt.stdout_path
    base: dict[str, Any] = {
        "blocking_findings": [blocker("R-1")],
        "deferred_findings": [deferred("R-9")],
        "review_attempts": 1,
        "successful_review_rounds": 1,
        "correction_round": 1,
    }
    reconcilable_record = stopped_record(
        worktree, evidence.head_sha, provider_runs=[attempt], **base
    )
    review_record = stopped_record(
        worktree,
        evidence.head_sha,
        provider_runs=[
            attempt,
            review_attempt(sequence=2, failure_class=ProviderFailureClass.AUTH_FAILED),
        ],
        **base,
    )
    return [
        coordinator.reconcile_milestone(
            reconcilable_record,
            milestone_id=MILESTONE,
            reason="A fenced but semantically valid result.",
            result_path=result_file(tmp_path, transcript.read_text(encoding="utf-8")),
            context=context,
        ),
        coordinator.reopen_milestone(
            reconcilable_record,
            milestone_id=MILESTONE,
            reason="milestone_plan_correction",
            human_owner_scope_ruling="The Human Owner rules the milestone is reopened.",
            context=context,
        ),
        coordinator.recover_failed_review(
            review_record,
            classification=ProviderFailureClass.AUTH_FAILED,
            human_owner_ruling="The Human Owner rules the token expiry consumed no review.",
            reason="classification: token_expired",
            context=context,
        ),
        coordinator.revalidate_correction(
            reconcilable_record,
            reason="tests failed after the correction round",
            context=context,
        ),
    ]


@pytest.fixture
def outcomes(
    coordinator: RecoveryCoordinator,
    store: RunStateStore,
    held_lock: RunLock,
    worktree: Path,
    evidence: RepositoryEvidence,
    context: RecoveryContext,
    tmp_path: Path,
) -> list[RecoveryOutcome]:
    return every_outcome(coordinator, store, held_lock, worktree, evidence, context, tmp_path)


class TestRecoveryCannotCloseBlocker:
    """No recovery path closes a blocker, and the attempt is refused."""

    def test_no_command_moves_a_finding(
        self, outcomes: list[RecoveryOutcome], worktree: Path, evidence: RepositoryEvidence
    ) -> None:
        for outcome in outcomes:
            findings = [
                (finding.finding_id, finding.status) for finding in outcome.record.blocking_findings
            ]
            assert findings == [("R-1", FindingStatus.OPEN)]
            assert [finding.finding_id for finding in outcome.record.deferred_findings] == ["R-9"]

    def test_closing_a_blocker_is_refused_by_the_guard(
        self, worktree: Path, evidence: RepositoryEvidence
    ) -> None:
        """The attempt has to be made through the guard, because no signature expresses it."""
        record = stopped_record(worktree, evidence.head_sha, blocking_findings=[blocker("R-1")])
        payload = json.loads(record.model_dump_json())
        payload["workflow_state"] = RunStatus.CLOSURE_VERIFYING.value
        payload["stop_reason"] = None
        payload["blocking_findings"][0]["status"] = FindingStatus.CLOSED.value
        closed = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="blocking_findings"):
            reject_forbidden_recovery_effect(record, closed)

    def test_introducing_a_finding_is_refused_by_the_guard(
        self, worktree: Path, evidence: RepositoryEvidence
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha, blocking_findings=[blocker("R-1")])
        payload = json.loads(record.model_dump_json())
        payload["workflow_state"] = RunStatus.IMPLEMENTING.value
        payload["stop_reason"] = None
        payload["blocking_findings"].append(json.loads(blocker("R-2").model_dump_json()))
        widened = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="blocking_findings"):
            reject_forbidden_recovery_effect(record, widened)

    def test_no_command_accepts_a_finding_a_status_or_a_severity(self) -> None:
        import inspect

        for name in RECOVERY_COMMANDS.values():
            function = globals()[name]
            parameters = set(inspect.signature(function).parameters)
            assert not parameters & {"finding", "findings", "status", "severity", "verdict"}, name


class TestRecoveryCannotReachCommitApproval:
    """No recovery path reaches an approval state, and the attempt is refused."""

    def test_no_command_targets_an_approval_state(self) -> None:
        assert RunStatus.READY_FOR_COMMIT_APPROVAL not in set(RECOVERY_POST_STATES.values())
        assert RunStatus.READY_FOR_PUSH_APPROVAL not in set(RECOVERY_POST_STATES.values())
        assert RunStatus.READY_FOR_COMMIT_APPROVAL in FORBIDDEN_RECOVERY_POST_STATES
        assert set(RECOVERY_POST_STATES) == set(RecoveryCommand)

    def test_every_outcome_lands_in_an_ordinary_working_state(
        self, outcomes: list[RecoveryOutcome]
    ) -> None:
        for outcome in outcomes:
            assert outcome.record.workflow_state not in FORBIDDEN_RECOVERY_POST_STATES
            assert outcome.record.approvals == []

    def test_reaching_commit_approval_is_refused_by_the_guard(
        self, worktree: Path, evidence: RepositoryEvidence
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha)
        payload = json.loads(record.model_dump_json())
        payload["workflow_state"] = RunStatus.READY_FOR_COMMIT_APPROVAL.value
        payload["stop_reason"] = None
        approved = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="READY_FOR_COMMIT_APPROVAL"):
            reject_forbidden_recovery_effect(record, approved)

    def test_a_ledger_entry_claiming_that_transition_cannot_be_built(
        self, evidence: RepositoryEvidence
    ) -> None:
        """`RecoveryLedgerEntry` validates its pair against the state machine's own table."""
        with pytest.raises(ValidationError, match="not an allowed run transition"):
            RecoveryLedgerEntry(
                command=RecoveryCommand.RECONCILE_MILESTONE,
                reason="A reconciliation that jumps straight to the commit gate.",
                recorded_at=RECORDED_AT,
                pre_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                post_state=RunStatus.READY_FOR_COMMIT_APPROVAL,
                branch=evidence.branch,
                head_sha=evidence.head_sha,
            )

    def test_raising_a_budget_is_refused_by_the_guard(
        self, worktree: Path, evidence: RepositoryEvidence
    ) -> None:
        record = stopped_record(worktree, evidence.head_sha, successful_review_rounds=0)
        payload = json.loads(record.model_dump_json())
        payload["workflow_state"] = RunStatus.REVIEWING.value
        payload["stop_reason"] = None
        payload["successful_review_rounds"] = 1
        raised = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="raised successful_review_rounds"):
            reject_forbidden_recovery_effect(record, raised)


class TestRecoveryEntryStates:
    """`HUMAN_INTERVENTION_REQUIRED` exits only through an explicit recovery command."""

    def test_every_command_refuses_a_running_state(
        self, worktree: Path, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        record = stopped_record(
            worktree,
            evidence.head_sha,
            workflow_state=RunStatus.IMPLEMENTING,
            stop_reason=None,
            correction_round=1,
            successful_review_rounds=1,
            provider_runs=[
                review_attempt(sequence=1, failure_class=ProviderFailureClass.AUTH_FAILED)
            ],
        )
        with pytest.raises(RecoveryRefused, match="clears a run stopped at"):
            reconcile_milestone(
                record,
                milestone_id=MILESTONE,
                reason="A reconciliation of a running milestone.",
                result_digest="a" * 64,
                transcript_digest="a" * 64,
                context=context,
            )
        with pytest.raises(RecoveryRefused, match="clears a run stopped at"):
            reopen_milestone(
                record,
                milestone_id=MILESTONE,
                reason="A reopen of a running milestone.",
                human_owner_scope_ruling="A ruling on a run that has not stopped.",
                context=context,
            )
        with pytest.raises(RecoveryRefused, match="clears a run stopped at"):
            recover_failed_review(
                record,
                classification=ProviderFailureClass.AUTH_FAILED,
                human_owner_ruling="A ruling on a run that has not stopped.",
                reason="A review recovery mid-run.",
                context=context,
            )
        with pytest.raises(RecoveryRefused, match="clears a run stopped at"):
            revalidate_correction(record, reason="A revalidation mid-run.", context=context)

    def test_the_entry_state_table_is_the_one_section_10_fixes(self) -> None:
        assert RECOVERY_ENTRY_STATES[RecoveryCommand.REOPEN_MILESTONE] == frozenset(
            {RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.MILESTONE_FAILED}
        )
        for command in (
            RecoveryCommand.RECONCILE_MILESTONE,
            RecoveryCommand.RECOVER_FAILED_REVIEW,
            RecoveryCommand.REVALIDATE_CORRECTION,
        ):
            assert RECOVERY_ENTRY_STATES[command] == frozenset(
                {RunStatus.HUMAN_INTERVENTION_REQUIRED}
            )


# --------------------------------------------------------------------------------------
# Section 11 -- the append-only ledgers
# --------------------------------------------------------------------------------------


class TestRecoveryLedgersAppendOnly:
    """Every recovery appends exactly one entry, and no entry is ever rewritten."""

    def test_each_command_writes_one_entry_to_its_own_ledger(
        self, outcomes: list[RecoveryOutcome]
    ) -> None:
        for outcome in outcomes:
            written = ledgers(outcome.record)
            assert len(written[outcome.ledger_field]) == 1
            for field, entries in written.items():
                if field != outcome.ledger_field:
                    assert entries == [], field

    def test_every_entry_carries_the_full_section_13_record(
        self, outcomes: list[RecoveryOutcome], evidence: RepositoryEvidence
    ) -> None:
        for outcome in outcomes:
            entry = outcome.entry
            assert entry.pre_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
            assert entry.post_state is outcome.record.workflow_state
            assert entry.branch == evidence.branch
            assert entry.head_sha == evidence.head_sha
            assert entry.recorded_at == RECORDED_AT
            assert entry.reason.strip()
            assert set(entry.budgets_touched) <= RUN_COUNTER_FIELDS

    def test_replaying_an_identical_entry_is_refused(self, outcomes: list[RecoveryOutcome]) -> None:
        for outcome in outcomes:
            with pytest.raises(RecoveryRefused, match="already carries this exact entry"):
                append_recovery_ledger_entry(outcome.record, outcome.entry)

    def test_a_second_recovery_appends_without_disturbing_the_first(
        self, outcomes: list[RecoveryOutcome], evidence: RepositoryEvidence
    ) -> None:
        first = outcomes[0]
        later = RecoveryLedgerEntry(
            command=RecoveryCommand.RECONCILE_MILESTONE,
            reason="A second, later reconciliation of the same run.",
            recorded_at="2026-08-06T10:00:00Z",
            pre_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            post_state=RunStatus.FOCUSED_VERIFYING,
            branch=evidence.branch,
            head_sha=evidence.head_sha,
        )
        updated = append_recovery_ledger_entry(first.record, later)
        assert updated.reconciliations[0] == first.entry
        assert updated.reconciliations[1] == later
        assert len(updated.reconciliations) == 2

    def test_an_altered_entry_is_refused(self, outcomes: list[RecoveryOutcome]) -> None:
        first = outcomes[0]
        payload = json.loads(first.record.model_dump_json())
        payload["reconciliations"][0]["reason"] = "A reason somebody edited afterwards."
        rewritten = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="is ever rewritten"):
            reject_ledger_rewrite(first.record, rewritten)

    def test_a_deleted_entry_is_refused(self, outcomes: list[RecoveryOutcome]) -> None:
        first = outcomes[0]
        payload = json.loads(first.record.model_dump_json())
        payload["reconciliations"] = []
        truncated = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="is ever deleted"):
            reject_ledger_rewrite(first.record, truncated)

    def test_two_entries_at_once_are_refused(
        self, outcomes: list[RecoveryOutcome], evidence: RepositoryEvidence
    ) -> None:
        first = outcomes[0]
        payload = json.loads(first.record.model_dump_json())
        extra = json.loads(first.entry.model_dump_json())
        extra["reason"] = "A third entry smuggled in with the second."
        payload["reconciliations"] = [*payload["reconciliations"], extra, dict(extra, reason="x y")]
        doubled = RunRecord.model_validate_json(json.dumps(payload))

        with pytest.raises(RecoveryRefused, match="appended at once"):
            reject_ledger_rewrite(first.record, doubled)

    def test_the_four_ledgers_are_the_four_the_record_carries(self) -> None:
        assert set(RECOVERY_LEDGER_FIELDS.values()) == {
            "reconciliations",
            "reopenings",
            "review_recoveries",
            "revalidations",
        }
        assert set(RECOVERY_LEDGER_FIELDS) == set(RecoveryCommand)
        assert set(RECOVERY_LEDGER_FIELDS.values()) <= set(RunRecord.model_fields)


# --------------------------------------------------------------------------------------
# DEC-016-006 and section 22 -- what recovery never touches
# --------------------------------------------------------------------------------------


class TestRecoveryNeverOpensPrototypeState:
    """No recovery path opens anything under `~/.local/share/auto015-runner/` (DEC-016-006)."""

    def test_no_recovery_command_opens_a_prototype_path(
        self,
        coordinator: RecoveryCoordinator,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        opened: list[str] = []
        real_os_open = os.open
        real_io_open = io.open

        def recording_os_open(path: Any, *args: Any, **kwargs: Any) -> int:
            opened.append(str(path))
            return real_os_open(path, *args, **kwargs)

        def recording_io_open(file: Any, *args: Any, **kwargs: Any) -> Any:
            opened.append(str(file))
            return real_io_open(file, *args, **kwargs)

        monkeypatch.setattr(os, "open", recording_os_open)
        monkeypatch.setattr(io, "open", recording_io_open)
        monkeypatch.setattr(builtins, "open", recording_io_open)
        try:
            results = every_outcome(
                coordinator, store, held_lock, worktree, evidence, context, tmp_path
            )
        finally:
            monkeypatch.undo()

        assert len(results) == len(RecoveryCommand)
        assert opened, "the recording hook never saw an open, so it proves nothing"
        assert not [path for path in opened if "auto015-runner" in path]
        assert not [path for path in opened if ".local/share" in path]

    def test_the_module_names_no_prototype_path(self) -> None:
        for literal in code_string_literals():
            assert "auto015" not in literal
            assert ".local/share" not in literal


class TestNoProviderInvokedByRecovery:
    """No recovery command invokes a provider, and none can (section 13)."""

    def test_the_module_imports_no_provider_and_no_subprocess(self) -> None:
        tree = ast.parse(RECOVERY_SOURCE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        assert not [name for name in imported if "providers" in name]
        assert not [name for name in imported if name.startswith("agentos_")]
        assert "subprocess" not in imported

    def test_no_subprocess_is_spawned_by_any_command(
        self,
        coordinator: RecoveryCoordinator,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def refuse(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a recovery command spawned a process")

        monkeypatch.setattr(subprocess, "run", refuse)
        monkeypatch.setattr(subprocess, "Popen", refuse)
        monkeypatch.setattr(os, "posix_spawn", refuse)

        results = every_outcome(
            coordinator, store, held_lock, worktree, evidence, context, tmp_path
        )
        assert len(results) == len(RecoveryCommand)


class TestRecoveryPublishesNothing:
    """The coordinator is not the transition authority and writes no durable state."""

    def test_no_state_document_is_published_by_a_recovery(
        self,
        coordinator: RecoveryCoordinator,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        evidence: RepositoryEvidence,
        context: RecoveryContext,
        tmp_path: Path,
    ) -> None:
        outcomes = every_outcome(
            coordinator, store, held_lock, worktree, evidence, context, tmp_path
        )
        assert outcomes
        assert not store.exists()

    def test_the_derived_record_leaves_the_original_untouched(
        self, post_correction: RunRecord, context: RecoveryContext
    ) -> None:
        before = post_correction.model_dump_json()
        outcome = revalidate_correction(
            post_correction, reason="tests failed after the correction round", context=context
        )
        assert post_correction.model_dump_json() == before
        assert outcome.record.model_dump_json() != before

    def test_a_naive_moment_is_refused(self, evidence: RepositoryEvidence) -> None:
        with pytest.raises(RecoveryRefused, match="timezone-aware UTC"):
            RecoveryContext.observed(evidence, datetime(2026, 8, 6, 9, 15, 30))

    def test_the_context_records_what_was_observed(
        self, evidence: RepositoryEvidence, context: RecoveryContext
    ) -> None:
        assert context.branch == evidence.branch
        assert context.head_sha == evidence.head_sha
        assert context.recorded_at == RECORDED_AT
        assert replace(context, branch="other").branch == "other"
