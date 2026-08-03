"""CI, Merge, Repository Finalization, and Runtime Closeout (AUTO-014): `PR_OPEN -> DONE`.

The second half of the foreground runtime workflow AUTO-013 began, composed the same way that
stage's `ImplementerModeDriver` was::

    MergeCloseoutModeDriver
        -> WorkflowSession.resume()  (AUTO-002: state, lock, durable transition history)
        -> agents.merge.MergeAgent   (AUTO-005/006: enable-merge / await-checks / confirm-merge)
        -> agents.closeout.CloseoutAgent  (AUTO-005/006: baseline restore, branch policy, report)
        -> skills.git_github / skills.repository / skills.reporting  (direct, read-only reconciles)

This module implements no new workflow state (`PR_OPEN`, `AUTO_MERGE_ENABLED`,
`WAITING_FOR_CHECKS`, `MERGED`, `CLOSING`, `DONE` all already exist in `WorkflowState`, and every
edge this driver takes is already in `ALLOWED_TRANSITIONS`), no new provider, and no new
approval mechanism. It never constructs a `WorkflowService` and never calls `invoke_provider`:
`MergeAgent` and `CloseoutAgent` are both contracted (`AGENT_SKILL_CONTRACTS`,
`AGENT_PROVIDER_CONTRACTS`) with an *empty* provider-role set, so "no provider is invoked by
AUTO-014" is a structural property of the Agents this driver composes, not a rule this module has
to remember to obey.

**Only `.resume()` exists — there is no `.start()`.** AUTO-014 never creates a runtime
authorization or a workflow ID (`HUMAN_AUTHORIZATION_MODEL.md`); it always re-attaches to a
workflow AUTO-013 already authorized and drove to `PR_OPEN` (or further, on a resumed AUTO-014
run). `MergeCloseoutTask` mirrors `ImplementationTask`'s own discipline: every field is
caller-supplied and none is recovered from persisted state on resume, including
`pull_request_number` and `expected_head_sha` — AUTO-013 never persisted a queryable PR number
(only a human-readable step-outcome string), and reconstructing one from a partial read would be
exactly the second, weaker authority path `HUMAN_AUTHORIZATION_MODEL.md` forbids. The caller that
authorized and tracked this workflow already knows both, the same way it already knows
`ImplementationTask.baseline_commit_sha`. `independent_qa_required` is supplied the same way
AUTO-013's own `ImplementerPolicy` is — recomputed by the caller on every resume, never read back
from disk — because AUTO-013 persisted no typed QA-policy record either.

**Two engineering decisions worth stating plainly, both recorded again in the completion
report.**

1. GitHub performs the actual merge itself, asynchronously, once `enable_automatic_squash_merge`
   has been called and every required check has passed — there is no "click merge" Skill call in
   this codebase. `WAITING_FOR_CHECKS -> MERGED` is therefore reached by *observing* that GitHub
   has already merged (`MergeAgent.confirm_merge`), never by this driver performing the merge as
   its own action. "Merge" in the mission's runtime flow names GitHub's own automatic action; this
   driver's role is to enable it safely, wait for it, and independently confirm it.
2. `MergeCloseoutTask` supplies `independent_qa_required`; the actual QA *result* is read back
   from AUTO-013's own persisted `qa.<n>.json` report when one exists, and `deterministic_
   validation_passed` is derived from the persisted transition history itself (a `VALIDATING ->
   QA_RUNNING` edge structurally proves validation passed, since no other edge leaves
   `VALIDATING` on success) — both real, re-observed evidence rather than an assumption. A missing
   QA report while `independent_qa_required=True` is always a hard `merge_not_eligible` failure;
   it is never read as an implicit pass.

**Approval evidence in the closeout report is a reference, not a re-verification.** `PR_OPEN`
existing at all already proves AUTO-013's `READY_TO_COMMIT` approval gate was consumed (no
`READY_TO_COMMIT -> COMMITTED` edge exists without it) — closeout persistence therefore carries
the well-known approval identifier (`f"{workflow_id}-implementer-approval"`, AUTO-013's own naming
convention) as a reference rather than re-opening `ApprovalService`, which is out of AUTO-014's
architecture (`WorkflowSession`/`MergeAgent`/`CloseoutAgent`/`StateStore` only).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from agentos_workflow.agents import AgentFailureKind, AgentKind, AgentResult, CapabilityBroker
from agentos_workflow.agents.closeout import CloseoutAgent
from agentos_workflow.agents.merge import MergeAgent
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator.engine import (
    INITIAL_EXECUTION_ATTEMPT_LIMIT,
    WorkflowAlreadyTerminalError,
    WorkflowSession,
    WorkflowState,
    reconstruct_initial_execution_attempts,
)
from agentos_workflow.orchestrator.state_store import StateStore
from agentos_workflow.skills import MergeConfirmation, RetryClassification, utc_now
from agentos_workflow.skills import git_github as git_github_skills
from agentos_workflow.skills import reporting as reporting_skills
from agentos_workflow.skills import repository as repository_skills

__all__ = [
    "InvalidStartStateError",
    "MergeCloseoutFailureKind",
    "MergeCloseoutModeDriver",
    "MergeCloseoutModeError",
    "MergeCloseoutPhase",
    "MergeCloseoutRunOutcome",
    "MergeCloseoutStepOutcome",
    "MergeCloseoutTask",
]

#: The only states AUTO-014 may resume into (`ALLOWED_START_STATES`, mission §"Start condition").
#: Any AUTO-013-owned earlier state (`AUTHORIZED` through `PR_OPEN`'s own predecessors) is refused.
ALLOWED_START_STATES: frozenset[WorkflowState] = frozenset(
    {
        WorkflowState.PR_OPEN,
        WorkflowState.AUTO_MERGE_ENABLED,
        WorkflowState.WAITING_FOR_CHECKS,
        WorkflowState.MERGED,
        WorkflowState.CLOSING,
    }
)


class MergeCloseoutModeError(Exception):
    """Base error for this module. Every subsystem error it wraps (`WorkflowSessionError`,
    `ResumeError`) propagates unwrapped — this hierarchy is only for failures genuinely local to
    this driver."""


class InvalidStartStateError(MergeCloseoutModeError):
    """Raised by `.resume()` when the persisted state is not one of `ALLOWED_START_STATES`.

    Raised before any AUTO-014 side effect and with the session's lock already released (see
    `.resume()`), so a caller that mis-invokes `continue` against, say, a `VALIDATING` workflow
    gets a clean refusal rather than a `FAILED` transition recorded against a stage this driver
    does not own.
    """


class MergeCloseoutFailureKind(StrEnum):
    """The minimum typed AUTO-014 failure taxonomy the stage contract names."""

    INVALID_START_STATE = "invalid_start_state"
    PR_NOT_FOUND = "pr_not_found"
    PR_IDENTITY_MISMATCH = "pr_identity_mismatch"
    PR_HEAD_MISMATCH = "pr_head_mismatch"
    REQUIRED_CHECKS_FAILED = "required_checks_failed"
    REQUIRED_CHECKS_UNAVAILABLE = "required_checks_unavailable"
    MERGE_NOT_ELIGIBLE = "merge_not_eligible"
    MERGE_AMBIGUOUS = "merge_ambiguous"
    MERGE_FAILED = "merge_failed"
    MERGE_CONFIRMATION_MISMATCH = "merge_confirmation_mismatch"
    BASELINE_DIVERGED = "baseline_diverged"
    BASELINE_UPDATE_FAILED = "baseline_update_failed"
    BRANCH_CLEANUP_FAILED = "branch_cleanup_failed"
    CLOSEOUT_FAILED = "closeout_failed"
    REPOSITORY_DRIFT = "repository_drift"
    STATE_CORRUPTION = "state_corruption"


class MergeCloseoutTask(BaseModel):
    """The caller-supplied description of one AUTO-014 continuation. See the module docstring for
    why every field here is caller-supplied rather than recovered from persisted state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    planned_stage_branch: str = Field(min_length=1)
    pull_request_number: int = Field(gt=0)
    expected_head_sha: str = Field(min_length=40, max_length=40)
    independent_qa_required: bool = True


class MergeCloseoutPhase(StrEnum):
    """What one `step()` call actually did."""

    ADVANCED = "advanced"
    PENDING_CHECKS = "pending_checks"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class MergeCloseoutStepOutcome:
    from_state: WorkflowState
    to_state: WorkflowState | None
    phase: MergeCloseoutPhase
    detail: str


@dataclass(frozen=True)
class MergeCloseoutRunOutcome:
    workflow_id: str
    final_state: WorkflowState
    reached_done: bool
    steps: tuple[MergeCloseoutStepOutcome, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _MergeEligibility:
    """Re-derived from persisted evidence only — never an in-memory assumption."""

    eligible: bool
    deterministic_validation_passed: bool
    qa_passed: bool
    qa_result: str  # "approved" | "rejected" | "not_applicable" | "missing"
    reason: str


def _iso_now() -> str:
    return utc_now().isoformat()


class MergeCloseoutModeDriver:
    """Composes `WorkflowSession`, `MergeAgent`, `CloseoutAgent`, and read-only Git/GitHub/
    reporting Skills to drive one already-authorized workflow from `PR_OPEN` to `DONE`.

    Construct only via `.resume()` — there is no `.start()` (see the module docstring).
    """

    def __init__(
        self,
        *,
        config: WorkflowConfig,
        session: WorkflowSession | None,
        task: MergeCloseoutTask,
        sleep: Callable[[float], None] | None = None,
        done_replay: bool = False,
    ) -> None:
        self._config = config
        self._session = session
        self._task = task
        self._repository_path = config.repository_path
        self._sleep = sleep if sleep is not None else time.sleep
        # `DONE` replay (see `.resume()`): this driver holds no `WorkflowSession` at all, because
        # `WorkflowSession.resume()` itself refuses to resume *any* terminal workflow
        # (`WorkflowAlreadyTerminalError`) — correct in general, but AUTO-014 must still support a
        # zero-side-effect `DONE` replay (mission "Resume and reconciliation" §DONE). `run_to_done`
        # short-circuits on `self.is_terminal` before ever touching `self._session`.
        self._done_replay = done_replay

    # -- Construction -----------------------------------------------------------------------

    @classmethod
    def resume(
        cls,
        config: WorkflowConfig,
        *,
        task: MergeCloseoutTask,
        sleep: Callable[[float], None] | None = None,
    ) -> Self:
        try:
            session = WorkflowSession.resume(
                config,
                workflow_id=task.workflow_id,
                stage_id=task.stage_id,
                planned_stage_branch=task.planned_stage_branch,
            )
        except WorkflowAlreadyTerminalError:
            # Re-read (never re-derive) which terminal state this actually is: `WorkflowSession.
            # resume()` already released its lock before this propagated, so a plain read-only
            # `StateStore` lookup — no lock, no session — is all a `DONE` replay needs. Any other
            # terminal state (`FAILED`/`CANCELLED`) is genuinely nothing for this driver to
            # resume, so it re-raises unchanged rather than fabricating a replay for it.
            transitions = StateStore.for_config(config).read_transitions(task.workflow_id)
            if transitions and transitions[-1].to_state == WorkflowState.DONE.value:
                return cls(config=config, session=None, task=task, sleep=sleep, done_replay=True)
            raise
        if session.state not in ALLOWED_START_STATES:
            state = session.state
            # `__exit__` unconditionally releases the held lock (`ARCHITECTURE.md` §5) — used
            # directly here, outside a `with` block, because this driver must keep the session
            # alive across many `step()` calls and cannot scope its whole lifetime to one `with`.
            session.__exit__(None, None, None)
            raise InvalidStartStateError(
                f"workflow {task.workflow_id!r} is at {state.value!r}, which AUTO-014 does not "
                f"own; only {sorted(s.value for s in ALLOWED_START_STATES)} may be resumed here."
            )
        try:
            cls._require_auto013_provenance(config, session)
        except MergeCloseoutModeError:
            session.__exit__(None, None, None)
            raise
        return cls(config=config, session=session, task=task, sleep=sleep)

    @staticmethod
    def _require_auto013_provenance(config: WorkflowConfig, session: WorkflowSession) -> None:
        """Refuse histories that did not pass through AUTO-013's persisted runtime path.

        A legal-looking transition chain is not sufficient provenance: a caller could otherwise
        manufacture a workflow record at (or before) ``PR_OPEN`` and attach a pre-existing PR by
        supplying its number and head SHA. AUTO-013 durably reserves and completes one
        initial-execution attempt for each of its three external lifecycle operations. Requiring
        those records makes the resume boundary depend on evidence produced by that runtime, not
        on the caller's claims. The attempt records are read through the engine's canonical
        validator, so malformed, foreign, skipped, duplicate, or over-limit history fails closed.
        """
        required = (
            WorkflowState.READY_TO_COMMIT,
            WorkflowState.COMMITTED,
            WorkflowState.PUSHED,
        )
        missing: list[str] = []
        for state in required:
            attempts = reconstruct_initial_execution_attempts(
                session.workflow_id,
                session.stage_id,
                state,
                StateStore.for_config(config),
            )
            if not attempts:
                missing.append(state.value)
        if missing:
            raise InvalidStartStateError(
                f"workflow {session.workflow_id!r} cannot be resumed by AUTO-014: persisted "
                "AUTO-013 provenance is incomplete; missing completed initial-execution attempt "
                f"records for {', '.join(missing)} (required states: "
                f"{', '.join(state.value for state in required)}; maximum attempts per state: "
                f"{INITIAL_EXECUTION_ATTEMPT_LIMIT})."
            )

    # -- Observation --------------------------------------------------------------------------

    @property
    def workflow_id(self) -> str:
        return self._task.workflow_id

    @property
    def state(self) -> WorkflowState:
        if self._done_replay:
            return WorkflowState.DONE
        assert self._session is not None
        return self._session.state

    @property
    def is_terminal(self) -> bool:
        if self._done_replay:
            return True
        assert self._session is not None
        return self._session.is_terminal

    @property
    def _active_session(self) -> WorkflowSession:
        """The live session every handler operates on. Only ever called from `step()` or a method
        it transitively calls, and `step()` itself refuses to run at all for a `DONE` replay
        driver — so by the time any handler reaches this, `self._session` is never `None`."""
        assert self._session is not None, "handler invoked without an active WorkflowSession"
        return self._session

    # -- Driving loop -------------------------------------------------------------------------

    def run_to_done(self, *, max_steps: int = 16) -> MergeCloseoutRunOutcome:
        """Call `step()` until `DONE`, a resumable pause (checks still pending), or a terminal
        state. `max_steps` is a defensive ceiling, not a real bound any legitimate path reaches."""
        steps: list[MergeCloseoutStepOutcome] = []
        for _ in range(max_steps):
            if self.state is WorkflowState.DONE or self.is_terminal:
                break
            outcome = self.step()
            steps.append(outcome)
            if outcome.phase in (MergeCloseoutPhase.PENDING_CHECKS, MergeCloseoutPhase.FAILED):
                break
        return MergeCloseoutRunOutcome(
            workflow_id=self.workflow_id,
            final_state=self.state,
            reached_done=self.state is WorkflowState.DONE,
            steps=tuple(steps),
        )

    def step(self) -> MergeCloseoutStepOutcome:
        """Advance exactly one logical unit of work from the session's current, re-observed state.
        Never assumes what happened last time — every handler re-reads live PR/repository state
        before acting, so calling `step()` from a brand-new `.resume(...)` after a process restart
        behaves identically to calling it on the instance that was running before the restart."""
        if self._done_replay or self._session is None:
            raise MergeCloseoutModeError(
                "step() called on a DONE replay driver; run_to_done() already short-circuits to "
                "a zero-side-effect result for a workflow already at DONE."
            )
        handlers: Mapping[WorkflowState, Callable[[], MergeCloseoutStepOutcome]] = {
            WorkflowState.PR_OPEN: self._handle_pr_open,
            WorkflowState.AUTO_MERGE_ENABLED: self._handle_auto_merge_enabled,
            WorkflowState.WAITING_FOR_CHECKS: self._handle_waiting_for_checks,
            WorkflowState.MERGED: self._handle_merged,
            WorkflowState.CLOSING: self._handle_closing,
        }
        state = self._active_session.state
        handler = handlers.get(state)
        if handler is None:
            raise MergeCloseoutModeError(
                f"MergeCloseoutModeDriver has no handler for {state.value!r}; AUTO-014 covers "
                "PR_OPEN through DONE only."
            )
        return handler()

    # -- PR reconciliation (used at PR_OPEN, AUTO_MERGE_ENABLED, and every WAITING_FOR_CHECKS
    # observation) --------------------------------------------------------------------------

    def _reconcile_pull_request(
        self,
    ) -> tuple[
        git_github_skills.PullRequestState | None,
        MergeCloseoutFailureKind | None,
        str,
        RetryClassification,
    ]:
        """Read and cross-check the live pull request against `self._task`'s persisted identity.

        The returned `RetryClassification` distinguishes two very different situations a caller
        polling this repeatedly (`_handle_waiting_for_checks`) must not conflate: the read itself
        failing (transient — GitHub, the network, `gh` — and worth another observation within
        budget) versus the read *succeeding* but disagreeing with what was authorized (a real head/
        base/branch mismatch, never retried, always a hard failure regardless of how many
        observations remain). Only the former ever carries anything other than `NOT_APPLICABLE`.
        """
        result = git_github_skills.read_pull_request_state(
            self._repository_path,
            pull_request_number=self._task.pull_request_number,
            allowed_environment_variables=tuple(self._config.allowed_environment_variables),
        )
        self._persist_observation(
            "pull_request_observed",
            {"pull_request_number": self._task.pull_request_number, "ok": bool(result.ok)},
        )
        if not result.ok or result.value is None:
            error = result.error
            detail = str(error) if error is not None else "no result"
            default_retry = RetryClassification.NOT_APPLICABLE
            retry = error.retry_classification if error is not None else default_retry
            return None, MergeCloseoutFailureKind.PR_NOT_FOUND, detail, retry
        pr = result.value
        not_applicable = RetryClassification.NOT_APPLICABLE
        if pr.head_sha and pr.head_sha != self._task.expected_head_sha:
            return (
                pr,
                MergeCloseoutFailureKind.PR_HEAD_MISMATCH,
                f"pull request #{pr.number} head is {pr.head_sha}, expected "
                f"{self._task.expected_head_sha}",
                not_applicable,
            )
        if pr.base_branch and pr.base_branch != self._config.baseline_branch:
            return (
                pr,
                MergeCloseoutFailureKind.PR_IDENTITY_MISMATCH,
                f"pull request #{pr.number} base is {pr.base_branch!r}, expected "
                f"{self._config.baseline_branch!r}",
                not_applicable,
            )
        if pr.head_branch and pr.head_branch != self._task.planned_stage_branch:
            return (
                pr,
                MergeCloseoutFailureKind.PR_IDENTITY_MISMATCH,
                f"pull request #{pr.number} head branch is {pr.head_branch!r}, expected "
                f"{self._task.planned_stage_branch!r}",
                not_applicable,
            )
        if not pr.merged and pr.state not in ("open",):
            return (
                pr,
                MergeCloseoutFailureKind.PR_IDENTITY_MISMATCH,
                f"pull request #{pr.number} is {pr.state!r} without being merged",
                not_applicable,
            )
        detail = "pull request identity, base, head, and head SHA all confirmed"
        return pr, None, detail, not_applicable

    def _persist_observation(self, event: str, payload: Mapping[str, Any]) -> None:
        reporting_skills.append_audit_event(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            event={"event": event, **payload},
        )

    # -- Merge eligibility (deterministic validation + QA evidence, from persisted facts only) --

    def _evaluate_merge_eligibility(self) -> _MergeEligibility:
        deterministic_validation_passed = any(
            transition.from_state == WorkflowState.VALIDATING.value
            and transition.to_state == WorkflowState.QA_RUNNING.value
            for transition in self._active_session.transitions
        )
        if not deterministic_validation_passed:
            return _MergeEligibility(
                eligible=False,
                deterministic_validation_passed=False,
                qa_passed=False,
                qa_result="missing",
                reason="no persisted VALIDATING -> QA_RUNNING transition; deterministic "
                "validation evidence is missing or incomplete",
            )

        qa_reports = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="qa",
        )
        if qa_reports.ok and qa_reports.value:
            latest = qa_reports.value[-1]
            verdict = str(latest.content.get("verdict", "REJECTED")).lower()
            qa_passed = verdict == "approved"
            return _MergeEligibility(
                eligible=qa_passed,
                deterministic_validation_passed=True,
                qa_passed=qa_passed,
                qa_result=verdict,
                reason=(
                    "persisted QA report evaluated"
                    if qa_passed
                    else "persisted QA report is " f"{verdict!r}, not approved"
                ),
            )

        if self._task.independent_qa_required:
            return _MergeEligibility(
                eligible=False,
                deterministic_validation_passed=True,
                qa_passed=False,
                qa_result="missing",
                reason="independent_qa_required=True but no persisted QA report exists; missing "
                "QA evidence is never treated as a pass",
            )
        return _MergeEligibility(
            eligible=True,
            deterministic_validation_passed=True,
            qa_passed=True,
            qa_result="not_applicable",
            reason="independent_qa_required=False and no QA report exists (guarded skip)",
        )

    # -- PR_OPEN -> AUTO_MERGE_ENABLED ---------------------------------------------------------

    def _handle_pr_open(self) -> MergeCloseoutStepOutcome:
        state = WorkflowState.PR_OPEN
        pr, failure_kind, detail, _retry = self._reconcile_pull_request()
        if failure_kind is not None:
            return self._fail(state, failure_kind, detail)
        assert pr is not None

        eligibility = self._evaluate_merge_eligibility()
        if not eligibility.eligible:
            return self._fail(
                state, MergeCloseoutFailureKind.MERGE_NOT_ELIGIBLE, eligibility.reason
            )

        if pr.merged:
            # A crash between GitHub's automatic merge and this driver observing it. Enabling
            # auto-merge on an already-merged PR is moot (and `gh pr merge --auto` on one would
            # simply error) — re-observation already proves the outcome this state exists to
            # reach, so this step advances straight past it.
            self._active_session.transition_to(
                WorkflowState.AUTO_MERGE_ENABLED, actor="orchestrator"
            )
            return MergeCloseoutStepOutcome(
                state,
                WorkflowState.AUTO_MERGE_ENABLED,
                MergeCloseoutPhase.ADVANCED,
                f"pull request #{pr.number} is already merged; advancing without re-enabling",
            )

        if pr.mergeable == "CONFLICTING":
            return self._fail(
                state,
                MergeCloseoutFailureKind.MERGE_NOT_ELIGIBLE,
                f"pull request #{pr.number} is not mergeable (mergeable={pr.mergeable!r})",
            )

        result = self._merge_agent().enable_auto_merge(
            deterministic_validation_passed=eligibility.deterministic_validation_passed,
            qa_passed=eligibility.qa_passed,
        )
        if not result.ok:
            return self._fail(
                state, self._classify_merge_agent_failure(result), self._agent_error_detail(result)
            )
        self._active_session.transition_to(WorkflowState.AUTO_MERGE_ENABLED, actor="orchestrator")
        return MergeCloseoutStepOutcome(
            state,
            WorkflowState.AUTO_MERGE_ENABLED,
            MergeCloseoutPhase.ADVANCED,
            f"automatic squash merge enabled for pull request #{pr.number}",
        )

    def _classify_merge_agent_failure(self, result: AgentResult) -> MergeCloseoutFailureKind:
        evidence = result.evidence
        if "deterministic_validation_passed" in evidence:
            return MergeCloseoutFailureKind.MERGE_NOT_ELIGIBLE
        if evidence.get("head_sha_verified") is False:
            return MergeCloseoutFailureKind.PR_HEAD_MISMATCH
        return MergeCloseoutFailureKind.MERGE_FAILED

    def _agent_error_detail(self, result: AgentResult) -> str:
        return str(result.error) if result.error is not None else "agent action failed"

    # -- AUTO_MERGE_ENABLED -> WAITING_FOR_CHECKS (re-observe, then pass through) --------------

    def _handle_auto_merge_enabled(self) -> MergeCloseoutStepOutcome:
        state = WorkflowState.AUTO_MERGE_ENABLED
        _pr, failure_kind, detail, _retry = self._reconcile_pull_request()
        if failure_kind is not None:
            return self._fail(state, failure_kind, detail)
        self._active_session.transition_to(WorkflowState.WAITING_FOR_CHECKS, actor="orchestrator")
        return MergeCloseoutStepOutcome(
            state,
            WorkflowState.WAITING_FOR_CHECKS,
            MergeCloseoutPhase.ADVANCED,
            "merge configuration re-observed; awaiting required checks",
        )

    # -- WAITING_FOR_CHECKS -> MERGED (bounded polling; never an unbounded loop) ---------------

    def _handle_waiting_for_checks(self) -> MergeCloseoutStepOutcome:
        state = WorkflowState.WAITING_FOR_CHECKS
        max_observations = self._config.merge_check_poll_max_observations
        interval = self._config.merge_check_poll_interval_seconds
        merge_agent = self._merge_agent()

        for observation in range(max_observations):
            pr, failure_kind, detail, retry = self._reconcile_pull_request()
            if failure_kind is not None:
                if pr is None and retry is not RetryClassification.NON_RETRYABLE:
                    # The read itself failed transiently (network/GitHub), never a real identity
                    # mismatch (those only arise once a read has actually succeeded, `pr is not
                    # None`) — re-observe next round rather than failing on a momentary blip.
                    if observation + 1 < max_observations:
                        self._sleep(interval)
                    continue
                return self._fail(state, failure_kind, detail)

            checks_result = merge_agent.await_required_checks()
            self._persist_observation(
                "required_checks_observed",
                {"observation": observation, **dict(checks_result.evidence)},
            )
            if not checks_result.ok:
                checks_error = checks_result.error
                if checks_error is not None and checks_error.kind is AgentFailureKind.GATE_EVIDENCE:
                    return self._fail(
                        state,
                        MergeCloseoutFailureKind.REQUIRED_CHECKS_FAILED,
                        self._agent_error_detail(checks_result),
                    )
                retry = retry_classification_of_agent(checks_result)
                if retry is RetryClassification.NON_RETRYABLE:
                    return self._fail(
                        state,
                        MergeCloseoutFailureKind.REQUIRED_CHECKS_UNAVAILABLE,
                        self._agent_error_detail(checks_result),
                    )
                # Pending, or a transient observation failure: fall through to the sleep/continue
                # below rather than failing on a still-in-progress CI run.
                if observation + 1 < max_observations:
                    self._sleep(interval)
                continue

            confirm_result = merge_agent.confirm_merge()
            self._persist_observation(
                "merge_confirmation_observed", {"observation": observation, "ok": confirm_result.ok}
            )
            if confirm_result.ok:
                self._active_session.transition_to(WorkflowState.MERGED, actor="orchestrator")
                return MergeCloseoutStepOutcome(
                    state,
                    WorkflowState.MERGED,
                    MergeCloseoutPhase.ADVANCED,
                    "required checks passed and merge independently confirmed",
                )
            detail = self._agent_error_detail(confirm_result)
            if "not merged" in detail.lower():
                # Checks just turned green; GitHub has not finished the automatic merge yet.
                # Pending, never a failure — see MACHINE_GATES.md §6.
                if observation + 1 < max_observations:
                    self._sleep(interval)
                continue
            retry = retry_classification_of_agent(confirm_result)
            if retry is RetryClassification.NON_RETRYABLE:
                return self._fail(state, MergeCloseoutFailureKind.MERGE_AMBIGUOUS, detail)
            if observation + 1 < max_observations:
                self._sleep(interval)

        return MergeCloseoutStepOutcome(
            state,
            None,
            MergeCloseoutPhase.PENDING_CHECKS,
            f"required checks still pending after {max_observations} observation(s); resumable",
        )

    # -- MERGED -> CLOSING (trivial pass-through; all real work happens in CLOSING, which is
    # itself safely re-enterable) --------------------------------------------------------------

    def _handle_merged(self) -> MergeCloseoutStepOutcome:
        state = WorkflowState.MERGED
        self._active_session.transition_to(WorkflowState.CLOSING, actor="orchestrator")
        return MergeCloseoutStepOutcome(
            state, WorkflowState.CLOSING, MergeCloseoutPhase.ADVANCED, "handing off to closeout"
        )

    # -- CLOSING -> DONE ------------------------------------------------------------------------

    def _handle_closing(self) -> MergeCloseoutStepOutcome:
        state = WorkflowState.CLOSING

        existing = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="closeout",
        )
        if existing.ok and existing.value:
            # Idempotent replay: closeout already ran to completion on an earlier visit (or an
            # earlier process before a crash/restart); DONE is a pure read from here.
            self._active_session.transition_to(WorkflowState.DONE, actor="orchestrator")
            return MergeCloseoutStepOutcome(
                state, WorkflowState.DONE, MergeCloseoutPhase.DONE, "closeout report already exists"
            )

        confirmation = self._reconfirm_merge()
        if isinstance(confirmation, MergeCloseoutStepOutcome):
            return confirmation

        identity = repository_skills.verify_repository_identity(
            self._repository_path,
            expected_identity=self._config.repository_identity,
            remote_name=self._config.remote_name,
        )
        if not identity.ok:
            return self._fail(
                state,
                MergeCloseoutFailureKind.REPOSITORY_DRIFT,
                f"repository identity: {identity.error}",
            )

        checked_out = repository_skills.checkout_baseline(
            self._repository_path, baseline_branch=self._config.baseline_branch
        )
        if not checked_out.ok:
            return self._fail(
                state,
                MergeCloseoutFailureKind.BASELINE_UPDATE_FAILED,
                f"could not check out baseline: {checked_out.error}",
            )
        pulled = repository_skills.fast_forward_pull(
            self._repository_path,
            baseline_branch=self._config.baseline_branch,
            remote=self._config.remote_name,
            allowed_environment_variables=tuple(self._config.allowed_environment_variables),
        )
        if not pulled.ok:
            kind = (
                MergeCloseoutFailureKind.BASELINE_DIVERGED
                if pulled.error is not None and pulled.error.kind.value == "command_failed"
                else MergeCloseoutFailureKind.BASELINE_UPDATE_FAILED
            )
            return self._fail(state, kind, f"could not fast-forward baseline: {pulled.error}")

        # Ancestry is checked against the *merge commit*, not `expected_head_sha`: a squash merge
        # (the only merge method this runtime supports) lands a brand-new commit on the baseline
        # whose sole parent is the pre-merge baseline tip, never the feature branch's own head —
        # so the validated head SHA is never an ancestor of a real squash-merge commit, and
        # checking for it would refuse every legitimate merge. What the fetched, fast-forwarded
        # local baseline must actually contain is the specific commit GitHub reported as merged.
        ancestry = repository_skills.verify_baseline_ancestry(
            self._repository_path,
            baseline_branch=confirmation.merge_commit_sha,
            branch=self._config.baseline_branch,
        )
        if not ancestry.ok:
            return self._fail(
                state,
                MergeCloseoutFailureKind.MERGE_CONFIRMATION_MISMATCH,
                f"merge commit {confirmation.merge_commit_sha} is not part of the updated "
                f"baseline: {ancestry.error}",
            )

        eligibility = self._evaluate_merge_eligibility()
        closeout_result = self._closeout_agent().close_out(
            merge_confirmation=confirmation,
            delete_branches=self._config.delete_branch_after_merge,
            extra_report_fields=self._closeout_extra_fields(confirmation, eligibility),
        )
        if not closeout_result.ok:
            return self._fail(
                state,
                self._classify_closeout_failure(closeout_result),
                self._agent_error_detail(closeout_result),
            )
        self._active_session.transition_to(WorkflowState.DONE, actor="orchestrator")
        return MergeCloseoutStepOutcome(
            state, WorkflowState.DONE, MergeCloseoutPhase.DONE, "runtime closeout complete"
        )

    def _reconfirm_merge(self) -> MergeConfirmation | MergeCloseoutStepOutcome:
        """Re-derive the `MergeConfirmation` from GitHub, never trust one carried in memory across
        a possible process restart (`WORKFLOW_STATES.md` §5a: re-observe before any repeated
        possible side effect)."""
        result = self._merge_agent().confirm_merge()
        if not result.ok:
            return self._fail(
                WorkflowState.CLOSING,
                MergeCloseoutFailureKind.MERGE_CONFIRMATION_MISMATCH,
                self._agent_error_detail(result),
            )
        confirmation = result.evidence.get("merge_confirmation")
        if not isinstance(confirmation, MergeConfirmation):
            return self._fail(
                WorkflowState.CLOSING,
                MergeCloseoutFailureKind.STATE_CORRUPTION,
                "confirm_merge succeeded but returned no MergeConfirmation evidence",
            )
        return confirmation

    def _classify_closeout_failure(self, result: AgentResult) -> MergeCloseoutFailureKind:
        source = result.error.source if result.error is not None else None
        if source in ("checkout_baseline", "fast_forward_pull"):
            return MergeCloseoutFailureKind.BASELINE_UPDATE_FAILED
        if source in ("delete_local_branch", "delete_remote_branch"):
            return MergeCloseoutFailureKind.BRANCH_CLEANUP_FAILED
        return MergeCloseoutFailureKind.CLOSEOUT_FAILED

    def _closeout_extra_fields(
        self, confirmation: MergeConfirmation, eligibility: _MergeEligibility
    ) -> Mapping[str, Any]:
        return {
            "workflow_id": self._task.workflow_id,
            "task_id": self._task.stage_id,
            "pull_request_number": self._task.pull_request_number,
            "expected_head_sha": self._task.expected_head_sha,
            "validation_evidence": {
                "deterministic_validation_passed": eligibility.deterministic_validation_passed
            },
            "qa_evidence": {
                "independent_qa_required": self._task.independent_qa_required,
                "qa_passed": eligibility.qa_passed,
                "qa_result": eligibility.qa_result,
            },
            "approval_evidence": {
                "approval_id": f"{self._task.workflow_id}-implementer-approval",
                "note": "consumed during AUTO-013 READY_TO_COMMIT; PR_OPEN is unreachable without "
                "it, so AUTO-014 references it rather than re-deriving it",
            },
            "merge_confirmation": {
                "branch": confirmation.branch,
                "merge_commit_sha": confirmation.merge_commit_sha,
                "verified_at": confirmation.verified_at.isoformat(),
            },
        }

    # -- Shared plumbing ------------------------------------------------------------------------

    def _merge_agent(self) -> MergeAgent:
        return MergeAgent(
            CapabilityBroker(AgentKind.MERGE),
            workflow_id=self._task.workflow_id,
            stage_id=self._task.stage_id,
            stage_branch=self._task.planned_stage_branch,
            repository_path=self._repository_path,
            audit_root=self._config.audit_directory,
            pull_request_number=self._task.pull_request_number,
            recorded_head_sha=self._task.expected_head_sha,
            allowed_environment_variables=tuple(self._config.allowed_environment_variables),
        )

    def _closeout_agent(self) -> CloseoutAgent:
        return CloseoutAgent(
            CapabilityBroker(AgentKind.CLOSEOUT),
            workflow_id=self._task.workflow_id,
            stage_id=self._task.stage_id,
            stage_branch=self._task.planned_stage_branch,
            baseline_branch=self._config.baseline_branch,
            remote_name=self._config.remote_name,
            repository_path=self._repository_path,
            audit_root=self._config.audit_directory,
            allowed_environment_variables=tuple(self._config.allowed_environment_variables),
        )

    def _fail(
        self, state: WorkflowState, kind: MergeCloseoutFailureKind, detail: str
    ) -> MergeCloseoutStepOutcome:
        reporting_skills.generate_failure_report(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            context={"reason": detail, "state": state.value, "failure_kind": kind.value},
        )
        self._active_session.transition_to(WorkflowState.FAILED, actor="orchestrator")
        return MergeCloseoutStepOutcome(
            state, WorkflowState.FAILED, MergeCloseoutPhase.FAILED, f"{kind.value}: {detail}"
        )


def retry_classification_of_agent(result: AgentResult) -> RetryClassification:
    """`agents.retry_classification_of` operates on a `SkillResult`; this is its `AgentResult`
    counterpart, reading the same field one layer up."""
    return (
        result.error.retry_classification
        if result.error is not None
        else RetryClassification.NOT_APPLICABLE
    )
