"""Foreground Implementer Mode (AUTO-013): `AUTHORIZED -> PR_OPEN`.

The first real foreground workflow this engine runs end to end, composed entirely from already-
delivered subsystems rather than a new framework::

    ImplementerModeDriver
        -> WorkflowSession       (AUTO-002: state, lock, durable attempt bookkeeping)
        -> WorkflowService       (AUTO-009/010/012: invoke_provider, the five approval operations)
        -> agents.run_deterministic_validation  (AUTO-003/005: the VALIDATING gate, unmodified)
        -> skills.repository / skills.git_github / skills.reporting  (AUTO-003/006, additive only)

This module implements no new workflow state, no new Skill family, no new provider, and no new
approval mechanism. `WorkflowState`'s 19 members and 37 edges, `ProviderRuntime`, both CLI
providers, `ProviderResult`, `AgentRunResult`, and `ApprovalService` are all reused exactly as
AUTO-002/010/011/012 left them. The one deliberately additive change outside this module is
`skills.repository.checkout_stage_branch` — `checkout_baseline` only ever targets the baseline, and
nothing before AUTO-013 needed to check out an arbitrary already-created stage branch.

**Where this stage ends.** `run_to_pr_open` never calls `transition_to` on any edge leaving
`PR_OPEN` (`AUTO_MERGE_ENABLED`, `WAITING_FOR_CHECKS`, `MERGED`, `CLOSING`, `DONE` have no handler
here at all), so CI waiting, merge, merge confirmation, baseline update, branch cleanup, and
runtime closeout are not merely "not called" but structurally absent from this module.

**The guarded `independent_qa_required` opt-in.** Mirrors AUTO-012's `_require_explicit_opt_in`
rule exactly, as its own closed policy (`ImplementerPolicy`) rather than a change to
`ApprovalPolicy` itself, which AUTO-012's stage contract closed to further edits. `False` may only
be resolved from the `GATE` or `RUN` layer, never `BUILT_IN` or `PROJECT` — an inherited default can
never silently disable independent QA. When it is `False`, `QA_RUNNING` never fabricates a QA
verdict: no QA report is generated, no `verdict` field is ever written, and the fact that QA did not
run is itself part of the `gate_result` checksum the approval gate binds to (`qa_performed=False`),
so an approval granted under a QA skip is auditably distinguishable from one granted after a real
QA pass.

**Two engineering decisions worth stating plainly, both recorded again in the completion report.**

1. AUTO-002's `evaluate_initial_execution_failure` has a fully working local verifier for
   `CommitEvidence`/`ImplementationDiffEvidence` but *no* authorized verifier at all for
   `RemoteRefEvidence`/`PullRequestEvidence` (`_verify_evidence_locally` raises
   `ReconciliationVerifierUnavailableError` for both, unconditionally, by design — "remote and PR
   evidence remain pending future authorized Skill/GitHub observation work"). Since `COMMITTED`
   (`push_stage_branch`) and `PUSHED` (`create_pull_request`) evidence is exactly those two types,
   this driver does not attempt the typed-evidence reconciliation path for any of
   `READY_TO_COMMIT`/`COMMITTED`/`PUSHED`. Instead it leans on a property every one of
   `create_commit`/`push_stage_branch`/`create_pull_request` already has by construction —
   idempotency — re-invoking the same Skill as the reconciliation action itself, bounded by the
   session's own durable initial-execution-attempt counter (fixed at 3). This is not a blind retry:
   each Skill's first action is to re-verify its own precondition against live repository/GitHub
   state before doing anything, which *is* the reconciliation. Using the full typed-evidence path
   for `READY_TO_COMMIT` alone (where a local verifier exists) was considered and rejected in favor
   of one uniform rule across all three commit/push/PR states.
2. AUTO-002's `ImplementationDiffEvidence` verification assumes the implementation attempt already
   produced a commit (`observed_head_sha` is checked as the *tip* of the stage branch, and
   `changed_paths` is derived from `baseline...observed_head_sha`). AUTO-013's approved runtime flow
   commits only once, at `READY_TO_COMMIT`, after validation, QA, and approval all pass — so at
   `IMPLEMENTING` time nothing is ever committed yet and that evidence shape does not fit. Rather
   than force an early commit (which the approved flow does not describe) or modify AUTO-002's
   verifier (out of scope and explicitly forbidden by "do not redesign"), a crash detected while
   resuming into `IMPLEMENTING` is handled directly: an empty working tree is treated as proven-no-
   side-effect (bounded retry via `evaluate_initial_execution_failure`, which needs no typed
   evidence for that classification); a non-empty one is carried forward to `VALIDATING` under
   `WORKFLOW_STATES.md` §5a item 4's own documented rule for a recoverable `IMPLEMENTING`
   inconsistency ("proceeds forward via the existing `IMPLEMENTING -> VALIDATING` edge... no new
   edge is added") — deterministic validation is what actually judges whatever was left behind.

Neither decision touches `orchestrator/engine.py`. Both are recorded as deferred/limitation notes in
the AUTO-013 completion report, not silently designed around.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from agentos_workflow.agents import ValidationOutcome, run_deterministic_validation
from agentos_workflow.approvals import (
    ApprovalChecksums,
    ApprovalNotFoundError,
    ApprovalPolicyOverlay,
    ApprovalRequest,
    ApprovalStatus,
    checksum_of_agent_result,
    checksum_of_mapping,
    checksum_of_text,
    resolve_approval_policy,
)
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator.engine import (
    INITIAL_EXECUTION_ATTEMPT_LIMIT,
    InitialExecutionFailureKind,
    RetryOutcome,
    RetryReconciliationResult,
    WorkflowSession,
    WorkflowState,
)
from agentos_workflow.providers.runtime import (
    ProviderRunRequest,
    ProviderRunResult,
    ProviderRuntimeTarget,
)
from agentos_workflow.results import (
    AgentRunResult,
    ExecutionMode,
    agent_run_result_from_provider_run,
)
from agentos_workflow.service import WorkflowService
from agentos_workflow.skills import SkillResult, utc_now
from agentos_workflow.skills import git_github as git_github_skills
from agentos_workflow.skills import reporting as reporting_skills
from agentos_workflow.skills import repository as repository_skills

__all__ = [
    "ApprovalPolicyOverlays",
    "ImplementationTask",
    "ImplementerModeDriver",
    "ImplementerModeError",
    "ImplementerPhase",
    "ImplementerPolicy",
    "ImplementerPolicyError",
    "ImplementerPolicyLayer",
    "ImplementerPolicyOverlay",
    "ImplementerPolicyOverlays",
    "ImplementerRunOutcome",
    "ImplementerStepOutcome",
    "resolve_implementer_policy",
]


class ImplementerModeError(Exception):
    """Base error for this module. Every subsystem error it wraps (`WorkflowSessionError`,
    `ResumeError`, `RetryError`, `ApprovalError`, `WorkflowServiceError`) propagates unwrapped —
    this hierarchy is only for failures genuinely local to this driver."""


class ImplementerPolicyError(ImplementerModeError):
    """A guarded implementer-mode policy value was selected from a layer not permitted to select
    it — see `resolve_implementer_policy`."""


# -------------------------------------------------------------------------------------------
# Guarded QA policy — mirrors approvals.py's PolicyLayer / _require_explicit_opt_in exactly, as
# its own closed model. `ApprovalPolicy` itself is AUTO-012's closed contract and is not extended.
# -------------------------------------------------------------------------------------------


class ImplementerPolicyLayer(StrEnum):
    BUILT_IN = "built_in"
    PROJECT = "project"
    GATE = "gate"
    RUN = "run"


_LAYER_ORDER: tuple[ImplementerPolicyLayer, ...] = (
    ImplementerPolicyLayer.BUILT_IN,
    ImplementerPolicyLayer.PROJECT,
    ImplementerPolicyLayer.GATE,
    ImplementerPolicyLayer.RUN,
)

#: Only the gate itself or an explicit per-run override may disable independent QA. An inherited
#: built-in or project-wide default can never silently turn it off — the same discipline
#: `approvals.py._EXPLICIT_OPT_IN_LAYERS` applies to `TimeoutAction.AUTO_APPROVE`.
_EXPLICIT_QA_OPT_OUT_LAYERS: frozenset[ImplementerPolicyLayer] = frozenset(
    {ImplementerPolicyLayer.GATE, ImplementerPolicyLayer.RUN}
)


class ImplementerPolicyOverlay(BaseModel):
    """One configuration layer for the guarded QA knob. Absent means "defer to the layer below" —
    the same absent-vs-false distinction `ApprovalPolicyOverlay` draws for the same reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    independent_qa_required: bool | None = None


class ImplementerPolicy(BaseModel):
    """The resolved, immutable guarded-QA policy bound into one workflow's `QA_RUNNING` visit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    independent_qa_required: bool
    independent_qa_required_source: ImplementerPolicyLayer


#: The conservative floor: independent QA is required unless explicitly, narrowly opted out.
_BUILT_IN_DEFAULT = ImplementerPolicyOverlay(independent_qa_required=True)


@dataclass(frozen=True)
class ImplementerPolicyOverlays:
    """The three overlays a caller may supply to `ImplementerModeDriver.start`/`.resume`."""

    project: ImplementerPolicyOverlay | None = None
    gate: ImplementerPolicyOverlay | None = None
    run: ImplementerPolicyOverlay | None = None


def resolve_implementer_policy(overlays: ImplementerPolicyOverlays) -> ImplementerPolicy:
    """Resolve `independent_qa_required` through `BUILT_IN -> PROJECT -> GATE -> RUN`, refusing a
    `False` value that was not explicitly selected at the `GATE` or `RUN` layer."""
    layered: list[tuple[ImplementerPolicyLayer, ImplementerPolicyOverlay]] = [
        (ImplementerPolicyLayer.BUILT_IN, _BUILT_IN_DEFAULT)
    ]
    for layer, overlay in (
        (ImplementerPolicyLayer.PROJECT, overlays.project),
        (ImplementerPolicyLayer.GATE, overlays.gate),
        (ImplementerPolicyLayer.RUN, overlays.run),
    ):
        if overlay is not None:
            layered.append((layer, overlay))
    ordered = [layer for layer, _ in layered]
    assert ordered == [layer for layer in _LAYER_ORDER if layer in set(ordered)], ordered

    value = True
    source = ImplementerPolicyLayer.BUILT_IN
    for layer, overlay in layered:
        if overlay.independent_qa_required is not None:
            value, source = overlay.independent_qa_required, layer
    if value is False and source not in _EXPLICIT_QA_OPT_OUT_LAYERS:
        raise ImplementerPolicyError(
            f"independent_qa_required=False requires explicit opt-in at the gate or per-run "
            f"override; it was inherited from the {source.value!r} layer. QA is never disabled "
            "by inheritance."
        )
    return ImplementerPolicy(independent_qa_required=value, independent_qa_required_source=source)


@dataclass(frozen=True)
class ApprovalPolicyOverlays:
    """The three `ApprovalPolicyOverlay` layers passed through, unmodified, to
    `approvals.resolve_approval_policy` for this workflow's one implementer-mode approval gate."""

    project: ApprovalPolicyOverlay | None = None
    gate: ApprovalPolicyOverlay | None = None
    run: ApprovalPolicyOverlay | None = None


# -------------------------------------------------------------------------------------------
# ImplementationTask — everything specific to one run that WorkflowSession does not persist for
# a caller to read back. Supplied to `.start()`; re-supplied identically to `.resume()`.
# -------------------------------------------------------------------------------------------


class ImplementationTask(BaseModel):
    """The caller-supplied description of one AUTO-013 run.

    None of these fields are recovered from persisted state on resume — a resuming caller (in
    production, whatever registered and authorized this run in the first place) must already know
    them. This is deliberate: `WorkflowSession` itself already refuses to reveal the persisted
    `AuthorizationRecord` to a generic caller, and reconstructing one from a partial read would be
    exactly the kind of second, weaker authority path `HUMAN_AUTHORIZATION_MODEL.md` forbids.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    stage_contract_path: str = Field(min_length=1)
    stage_contract_hash: str = Field(min_length=1)
    planned_stage_branch: str = Field(min_length=1)
    baseline_commit_sha: str = Field(min_length=1)
    authorized_at: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    authorized_by: str | None = None
    task_description: str = Field(min_length=1)
    commit_message: str = Field(min_length=1)
    pull_request_title: str = Field(min_length=1)
    pull_request_body: str = ""


# -------------------------------------------------------------------------------------------
# Outcomes
# -------------------------------------------------------------------------------------------


class ImplementerPhase(StrEnum):
    """What one `step()` call actually did."""

    ADVANCED = "advanced"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class ImplementerStepOutcome:
    from_state: WorkflowState
    to_state: WorkflowState | None
    phase: ImplementerPhase
    detail: str


@dataclass(frozen=True)
class ImplementerRunOutcome:
    workflow_id: str
    final_state: WorkflowState
    reached_pr_open: bool
    steps: tuple[ImplementerStepOutcome, ...] = field(default_factory=tuple)


# -------------------------------------------------------------------------------------------
# Small local helpers
# -------------------------------------------------------------------------------------------


def _iso_now() -> str:
    return utc_now().isoformat()


_NON_REPAIRABLE_CHECKS: frozenset[str] = frozenset(
    {"run_scope_validation", "run_secret_detection", "run_security_checks"}
)
"""`MACHINE_GATES.md` §3's full check list always runs, but a failure here must never be repaired
automatically — a scope violation, a forbidden path, a committed secret, or a security finding is
never something a bounded Claude repair attempt is trusted to resolve on its own."""


class ImplementerModeDriver:
    """Composes `WorkflowSession` (state/lock/attempts), `WorkflowService` (provider invocation and
    the five approval operations), and the existing Skills to drive one workflow from `AUTHORIZED`
    to `PR_OPEN`.

    Construct only via `.start()` (a fresh authorization) or `.resume()` (re-attaching to an
    in-flight workflow) — matching the discipline `WorkflowSession` itself already enforces one
    layer below.
    """

    def __init__(
        self,
        *,
        config: WorkflowConfig,
        session: WorkflowSession,
        task: ImplementationTask,
        qa_policy: ImplementerPolicy,
        approval_overlays: ApprovalPolicyOverlays,
    ) -> None:
        self._config = config
        self._session = session
        self._task = task
        self._qa_policy = qa_policy
        self._approval_overlays = approval_overlays
        self._service = WorkflowService(config)
        self._repository_path = config.repository_path

    # -- Construction -----------------------------------------------------------------------

    @classmethod
    def start(
        cls,
        config: WorkflowConfig,
        *,
        task: ImplementationTask,
        qa_policy_overlays: ImplementerPolicyOverlays | None = None,
        approval_overlays: ApprovalPolicyOverlays | None = None,
    ) -> Self:
        session = WorkflowSession.start(
            config,
            workflow_id=task.workflow_id,
            stage_id=task.stage_id,
            stage_contract_path=task.stage_contract_path,
            stage_contract_hash=task.stage_contract_hash,
            planned_stage_branch=task.planned_stage_branch,
            baseline_commit_sha=task.baseline_commit_sha,
            authorized_at=task.authorized_at,
            engine_version=task.engine_version,
            authorized_by=task.authorized_by,
        )
        return cls(
            config=config,
            session=session,
            task=task,
            qa_policy=resolve_implementer_policy(qa_policy_overlays or ImplementerPolicyOverlays()),
            approval_overlays=approval_overlays or ApprovalPolicyOverlays(),
        )

    @classmethod
    def resume(
        cls,
        config: WorkflowConfig,
        *,
        task: ImplementationTask,
        qa_policy_overlays: ImplementerPolicyOverlays | None = None,
        approval_overlays: ApprovalPolicyOverlays | None = None,
    ) -> Self:
        session = WorkflowSession.resume(
            config,
            workflow_id=task.workflow_id,
            stage_id=task.stage_id,
            planned_stage_branch=task.planned_stage_branch,
        )
        return cls(
            config=config,
            session=session,
            task=task,
            qa_policy=resolve_implementer_policy(qa_policy_overlays or ImplementerPolicyOverlays()),
            approval_overlays=approval_overlays or ApprovalPolicyOverlays(),
        )

    # -- Observation --------------------------------------------------------------------------

    @property
    def workflow_id(self) -> str:
        return self._session.workflow_id

    @property
    def state(self) -> WorkflowState:
        return self._session.state

    @property
    def is_terminal(self) -> bool:
        return self._session.is_terminal

    # -- Driving loop -------------------------------------------------------------------------

    def run_to_pr_open(self, *, max_steps: int = 32) -> ImplementerRunOutcome:
        """Call `step()` until `PR_OPEN`, a pause (awaiting human approval), or a terminal state.

        `max_steps` is a defensive ceiling against a bug in this driver looping forever — every
        legitimate path is bounded by the session's own attempt limits (3) well before this many
        steps, so reaching it is itself a defect to investigate, not a real outcome to plan around.
        """
        steps: list[ImplementerStepOutcome] = []
        for _ in range(max_steps):
            if self._session.state is WorkflowState.PR_OPEN or self._session.is_terminal:
                break
            outcome = self.step()
            steps.append(outcome)
            if outcome.phase in (ImplementerPhase.AWAITING_APPROVAL, ImplementerPhase.FAILED):
                break
        return ImplementerRunOutcome(
            workflow_id=self._session.workflow_id,
            final_state=self._session.state,
            reached_pr_open=self._session.state is WorkflowState.PR_OPEN,
            steps=tuple(steps),
        )

    def step(self) -> ImplementerStepOutcome:
        """Advance exactly one logical unit of work from the session's current, re-observed state.

        Never assumes what happened last time — every handler starts by asking the session (never
        an in-memory field) what is already durably true, which is what makes calling `step()` from
        a brand-new `ImplementerModeDriver.resume(...)` after a process restart identical in
        behavior to calling it on the instance that was running before the restart.
        """
        handlers: Mapping[WorkflowState, Callable[[], ImplementerStepOutcome]] = {
            WorkflowState.AUTHORIZED: self._handle_authorized,
            WorkflowState.PRECONDITIONS_CHECKED: self._handle_preconditions_checked,
            WorkflowState.BRANCH_CREATED: self._handle_branch_created,
            WorkflowState.IMPLEMENTING: self._handle_implementing,
            WorkflowState.VALIDATING: self._handle_validating,
            WorkflowState.QA_RUNNING: self._handle_qa_running,
            WorkflowState.REPAIRING: self._handle_repairing,
            WorkflowState.READY_TO_COMMIT: self._handle_ready_to_commit,
            WorkflowState.COMMITTED: self._handle_committed,
            WorkflowState.PUSHED: self._handle_pushed,
        }
        state = self._session.state
        handler = handlers.get(state)
        if handler is None:
            raise ImplementerModeError(
                f"ImplementerModeDriver has no handler for {state.value!r}; AUTO-013 covers "
                "AUTHORIZED through PR_OPEN only, and PR_OPEN itself has no outgoing handler by "
                "design (this stage stops there)."
            )
        return handler()

    # -- AUTHORIZED -> PRECONDITIONS_CHECKED (no retry semantics; re-observe every visit) ------

    def _handle_preconditions(self) -> tuple[bool, str]:
        identity = repository_skills.verify_repository_identity(
            self._repository_path,
            expected_identity=self._config.repository_identity,
            remote_name=self._config.remote_name,
        )
        if not identity.ok:
            return False, f"repository identity check failed: {identity.error}"
        tree = repository_skills.inspect_working_tree(self._repository_path)
        if not tree.ok or tree.value is None:
            return False, f"could not inspect working tree: {tree.error}"
        if not tree.value.clean:
            return False, f"working tree is not clean: {len(tree.value.entries)} changed path(s)"
        ancestry = repository_skills.verify_baseline_ancestry(
            self._repository_path, baseline_branch=self._config.baseline_branch
        )
        if not ancestry.ok:
            return False, f"baseline ancestry check failed: {ancestry.error}"
        return True, "repository identity, clean tree, and baseline ancestry all confirmed"

    def _handle_authorized(self) -> ImplementerStepOutcome:
        ok, detail = self._handle_preconditions()
        if not ok:
            return self._fail(WorkflowState.AUTHORIZED, detail, context={"gate": "preconditions"})
        self._session.transition_to(WorkflowState.PRECONDITIONS_CHECKED, actor="orchestrator")
        return ImplementerStepOutcome(
            WorkflowState.AUTHORIZED,
            WorkflowState.PRECONDITIONS_CHECKED,
            ImplementerPhase.ADVANCED,
            detail,
        )

    # -- PRECONDITIONS_CHECKED -> BRANCH_CREATED (idempotent Skills; no retry semantics) --------

    def _handle_preconditions_checked(self) -> ImplementerStepOutcome:
        created = repository_skills.create_stage_branch(
            self._repository_path,
            branch_name=self._task.planned_stage_branch,
            base_sha=self._task.baseline_commit_sha,
            baseline_branch=self._config.baseline_branch,
        )
        if not created.ok:
            return self._fail(
                WorkflowState.PRECONDITIONS_CHECKED,
                f"could not create stage branch: {created.error}",
                context={"gate": "branch_preparation"},
            )
        checked_out = repository_skills.checkout_stage_branch(
            self._repository_path,
            branch=self._task.planned_stage_branch,
            baseline_branch=self._config.baseline_branch,
        )
        if not checked_out.ok:
            return self._fail(
                WorkflowState.PRECONDITIONS_CHECKED,
                f"could not check out stage branch: {checked_out.error}",
                context={"gate": "branch_preparation"},
            )
        self._session.transition_to(WorkflowState.BRANCH_CREATED, actor="orchestrator")
        return ImplementerStepOutcome(
            WorkflowState.PRECONDITIONS_CHECKED,
            WorkflowState.BRANCH_CREATED,
            ImplementerPhase.ADVANCED,
            f"stage branch {self._task.planned_stage_branch!r} created and checked out",
        )

    # -- BRANCH_CREATED -> IMPLEMENTING (nothing to do here but hand off to the Claude call) ----

    def _handle_branch_created(self) -> ImplementerStepOutcome:
        self._session.transition_to(WorkflowState.IMPLEMENTING, actor="orchestrator")
        return ImplementerStepOutcome(
            WorkflowState.BRANCH_CREATED,
            WorkflowState.IMPLEMENTING,
            ImplementerPhase.ADVANCED,
            "handing off to Claude implementation",
        )

    # -- IMPLEMENTING -> VALIDATING (initial-execution-retryable; see module docstring §2) ------

    def _handle_implementing(self) -> ImplementerStepOutcome:
        state = WorkflowState.IMPLEMENTING
        if self._session.has_unreconciled_initial_execution_attempt(state):
            # Close the crashed attempt's still-open STARTED reservation first: a
            # PROVEN_NO_SIDE_EFFECT evaluation is refused outright while one remains open
            # (`UnreconciledAttemptError`) — its outcome must be resolved before it can be asked
            # about at all, which is exactly what this COMPLETED record now records.
            attempt_number = len(self._session.reconstruct_initial_execution_attempts(state)) + 1
            self._session.record_initial_execution_attempt(
                state, attempt_number=attempt_number, completion_time=_iso_now()
            )
            if self._working_tree_paths():
                self._session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
                return ImplementerStepOutcome(
                    state,
                    WorkflowState.VALIDATING,
                    ImplementerPhase.ADVANCED,
                    "resumed after a crash with an in-progress implementation diff already in the "
                    "working tree; proceeding to VALIDATING to judge it "
                    "(WORKFLOW_STATES.md §5a item 4)",
                )
            result = self._session.evaluate_initial_execution_failure(
                state, failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT
            )
            return self._apply_bare_retry(state, result, self._attempt_implementation)
        return self._attempt_implementation()

    def _attempt_implementation(self) -> ImplementerStepOutcome:
        state = WorkflowState.IMPLEMENTING
        attempt_number = len(self._session.reconstruct_initial_execution_attempts(state)) + 1
        self._session.record_initial_execution_attempt_started(
            state, attempt_number=attempt_number, start_time=_iso_now()
        )
        run_result = self._invoke_claude(
            role_label="implementation",
            task=self._task.task_description,
            invocation_id=f"{self._task.workflow_id}-implementing-{attempt_number}",
        )
        self._session.record_initial_execution_attempt(
            state, attempt_number=attempt_number, completion_time=_iso_now()
        )

        if run_result.succeeded:
            self._write_stage_report(run_result, sequence=None)
            self._session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
            return ImplementerStepOutcome(
                state,
                WorkflowState.VALIDATING,
                ImplementerPhase.ADVANCED,
                f"implementation attempt {attempt_number} completed ({run_result.status.value})",
            )

        if self._working_tree_paths():
            self._write_stage_report(run_result, sequence=None)
            self._session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
            return ImplementerStepOutcome(
                state,
                WorkflowState.VALIDATING,
                ImplementerPhase.ADVANCED,
                f"implementation attempt {attempt_number} did not fully succeed "
                f"({run_result.status.value}) but left a diff; proceeding to VALIDATING to judge "
                "it (WORKFLOW_STATES.md §5a item 4)",
            )

        result = self._session.evaluate_initial_execution_failure(
            state, failure_kind=InitialExecutionFailureKind.PROVEN_NO_SIDE_EFFECT
        )
        return self._apply_bare_retry(state, result, self._attempt_implementation)

    def _apply_bare_retry(
        self,
        state: WorkflowState,
        result: RetryReconciliationResult,
        retry_action: Callable[[], ImplementerStepOutcome],
    ) -> ImplementerStepOutcome:
        if result.outcome in (RetryOutcome.RETRY_ALLOWED, RetryOutcome.NO_RETRY_REQUIRED):
            return retry_action()
        return self._fail(
            state,
            result.reason,
            context={"outcome": result.outcome.value, "attempt_count": result.attempt_count},
        )

    # -- VALIDATING <-> REPAIRING -> QA_RUNNING --------------------------------------------------

    def _handle_validating(self) -> ImplementerStepOutcome:
        state = WorkflowState.VALIDATING
        outcome = self._run_validation()
        if outcome.passed:
            self._session.transition_to(WorkflowState.QA_RUNNING, actor="orchestrator")
            return ImplementerStepOutcome(
                state, WorkflowState.QA_RUNNING, ImplementerPhase.ADVANCED, "validation passed"
            )
        non_repairable = [
            check.name for check in outcome.failed_checks if check.name in _NON_REPAIRABLE_CHECKS
        ]
        if non_repairable:
            return self._fail(
                state,
                f"deterministic validation found a non-repairable defect in "
                f"{', '.join(sorted(non_repairable))}; automatic repair is never attempted for "
                "scope, forbidden-path, or secret/security findings",
                context={"failed_checks": [check.name for check in outcome.failed_checks]},
            )
        return self._enter_repair_or_fail(state, failure_report=outcome.failure_report())

    def _run_validation(self) -> ValidationOutcome:
        changed_files = self._working_tree_paths()
        report_path = self._latest_stage_report_path()
        return run_deterministic_validation(
            config=self._config,
            changed_files=changed_files,
            completion_report_path=report_path,
        )

    def _enter_repair_or_fail(
        self, state: WorkflowState, *, failure_report: Mapping[str, Any]
    ) -> ImplementerStepOutcome:
        result = self._session.evaluate_repair_attempt(state)
        if result.next_allowed_state is WorkflowState.REPAIRING:
            reporting_skills.generate_failure_report(
                audit_root=self._config.audit_directory,
                workflow_id=self._task.workflow_id,
                context=dict(failure_report),
                sequence=result.attempt_count + 1,
            )
            self._session.transition_to(WorkflowState.REPAIRING, actor="orchestrator")
            return ImplementerStepOutcome(
                state, WorkflowState.REPAIRING, ImplementerPhase.ADVANCED, result.reason
            )
        assert result.next_allowed_state is WorkflowState.FAILED
        return self._fail(state, result.reason, context=dict(failure_report))

    # -- REPAIRING -> VALIDATING (bounded to config.repair_attempt_limit, fixed at 3) -----------

    def _triggering_gate_state(self) -> WorkflowState:
        for transition in reversed(self._session.transitions):
            if transition.to_state == WorkflowState.REPAIRING.value:
                return WorkflowState(transition.from_state)
        raise ImplementerModeError(
            "REPAIRING has no persisted transition into it; cannot determine which gate "
            "(VALIDATING or QA_RUNNING) triggered this repair cycle."
        )

    def _handle_repairing(self) -> ImplementerStepOutcome:
        state = WorkflowState.REPAIRING
        if self._session.has_unreconciled_repair_attempt():
            return self._fail(
                state,
                "a repair-provider attempt was started but never recorded as completed; "
                "FAILURE_RECOVERY.md §1 treats an unrecoverable repair-provider crash as "
                "REPAIRING -> FAILED, never a blind retry",
                context={"reason": "unreconciled_repair_attempt"},
            )
        triggering_state = self._triggering_gate_state()
        attempt_number = len(self._session.reconstruct_repair_attempts()) + 1
        failure_report = self._read_failure_report(sequence=attempt_number)

        self._session.record_repair_attempt_started(
            triggering_state, attempt_number=attempt_number, start_time=_iso_now()
        )
        repair_result = self._invoke_claude(
            role_label="repair",
            task=self._build_repair_task(failure_report),
            invocation_id=f"{self._task.workflow_id}-repairing-{attempt_number}",
        )
        self._session.record_repair_attempt(
            triggering_state, attempt_number=attempt_number, completion_time=_iso_now()
        )

        if not repair_result.succeeded:
            return self._fail(
                state,
                f"repair attempt {attempt_number} produced no usable result "
                f"({repair_result.status.value}): {repair_result.summary}",
                context={"attempt_number": attempt_number},
            )
        self._write_stage_report(repair_result, sequence=attempt_number)
        self._session.transition_to(WorkflowState.VALIDATING, actor="orchestrator")
        return ImplementerStepOutcome(
            state,
            WorkflowState.VALIDATING,
            ImplementerPhase.ADVANCED,
            f"repair attempt {attempt_number} completed",
        )

    def _build_repair_task(self, failure_report: Mapping[str, Any]) -> str:
        return (
            f"{self._task.task_description}\n\n"
            "The previous attempt did not pass deterministic validation or independent QA. Fix "
            f"exactly the following reported defects and nothing else:\n{failure_report}"
        )

    def _read_failure_report(self, *, sequence: int) -> Mapping[str, Any]:
        result = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="failure",
        )
        if not result.ok or result.value is None:
            raise ImplementerModeError(f"could not read failure reports: {result.error}")
        matching = [report for report in result.value if report.sequence == sequence]
        if not matching:
            raise ImplementerModeError(
                f"no persisted failure report with sequence {sequence} for workflow "
                f"{self._task.workflow_id!r}; REPAIRING cannot proceed without the report the "
                "gate that entered it wrote"
            )
        return matching[-1].content

    # -- QA_RUNNING -> READY_TO_COMMIT (guarded QA skip only; the approval gate lives at
    # READY_TO_COMMIT itself — see _handle_ready_to_commit) -------------------------------------

    def _handle_qa_running(self) -> ImplementerStepOutcome:
        """Re-observes before ever invoking Codex again.

        A crash resuming into `QA_RUNNING` (or a `step()` racing an earlier one) must not
        re-invoke Codex under the same `invocation_id` — the Provider Runtime refuses that
        outright as a session-directory collision (`ProviderFailureKind.PRECONDITION`), which is
        exactly the "never re-execute without reconciliation" discipline `WORKFLOW_STATES.md` §5a
        already applies to `IMPLEMENTING`/commit/push/PR. The persisted `qa.<round>.json` report
        *is* the reconciliation: if one already exists for this repair round, its verdict is read
        back rather than the review being repeated.
        """
        state = WorkflowState.QA_RUNNING
        qa_round = len(self._session.reconstruct_repair_attempts()) + 1
        qa_performed = self._qa_policy.independent_qa_required

        if qa_performed:
            qa_result, qa_verdict = self._get_or_run_qa(qa_round)
            if not qa_result:
                return self._enter_repair_or_fail(
                    state,
                    failure_report={
                        "source": "independent_qa",
                        "verdict": qa_verdict,
                        "detail": "independent QA rejected the change",
                    },
                )
        else:
            # `append_audit_event` is itself idempotent (a stable, content-derived `event_id` when
            # the caller omits one), so re-appending this on a resumed revisit is a safe no-op,
            # never a duplicate record.
            reporting_skills.append_audit_event(
                audit_root=self._config.audit_directory,
                workflow_id=self._task.workflow_id,
                event={
                    "event": "qa_skipped",
                    "reason": "independent_qa_required=False "
                    f"(explicit {self._qa_policy.independent_qa_required_source.value} opt-in)",
                },
            )

        self._session.transition_to(WorkflowState.READY_TO_COMMIT, actor="orchestrator")
        return ImplementerStepOutcome(
            state,
            WorkflowState.READY_TO_COMMIT,
            ImplementerPhase.ADVANCED,
            "validation and QA passed; ready to commit pending approval",
        )

    def _get_or_run_qa(self, sequence: int) -> tuple[bool, str]:
        """Re-observe first: reuse an already-persisted verdict for this repair round rather than
        invoking Codex again (see `_handle_qa_running`'s docstring)."""
        existing = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="qa",
        )
        if existing.ok and existing.value:
            matching = [report for report in existing.value if report.sequence == sequence]
            if matching:
                verdict = str(matching[-1].content.get("verdict", "REJECTED")).lower()
                return verdict == "approved", verdict
        return self._run_qa(sequence)

    def _run_qa(self, sequence: int) -> tuple[bool, str]:
        run_result = self._invoke_provider(
            target=ProviderRuntimeTarget.CODEX,
            task=self._build_qa_task(),
            invocation_id=f"{self._task.workflow_id}-qa-{sequence}",
            mode=ExecutionMode.REVIEW,
        )
        verdict = (
            "approved"
            if run_result.succeeded
            and run_result.final_verdict is not None
            and (run_result.final_verdict.value == "pass")
            else "rejected"
        )
        report_context: dict[str, Any] = {
            "stage_id": self._task.stage_id,
            "branch": self._task.planned_stage_branch,
            "head_sha": self._current_head_sha(),
            "summary": run_result.summary,
            "verdict": verdict.upper(),
            "findings": list(run_result.blocking_issues) if verdict == "rejected" else [],
        }
        reporting_skills.generate_qa_report(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            results=report_context,
            sequence=sequence,
        )
        return (verdict == "approved"), verdict

    def _build_qa_task(self) -> str:
        return (
            "Independently review the uncommitted working-tree diff on branch "
            f"{self._task.planned_stage_branch!r} against baseline "
            f"{self._config.baseline_branch!r}. Report verdict 'pass' only if the change is "
            "correct, in scope, and safe; otherwise 'fail' with concrete findings.\n\n"
            f"Original task:\n{self._task.task_description}"
        )

    # -- Approval gate (ApprovalService, via WorkflowService) -----------------------------------

    def _run_approval_gate(self, *, qa_performed: bool, qa_verdict: str | None) -> ApprovalRequest:
        approval_id = f"{self._task.workflow_id}-implementer-approval"
        gate = "auto-013-implementer-approval"
        checksums = self._current_approval_checksums(
            qa_performed=qa_performed, qa_verdict=qa_verdict
        )
        try:
            self._service.get_approval(workflow_id=self._task.workflow_id, approval_id=approval_id)
        except ApprovalNotFoundError:
            policy = resolve_approval_policy(
                project=self._approval_overlays.project,
                gate=self._approval_overlays.gate,
                run=self._approval_overlays.run,
            )
            self._service.request_approval(
                workflow_id=self._task.workflow_id,
                gate=gate,
                approval_id=approval_id,
                checksums=checksums,
                policy=policy,
            )
        request = self._service.evaluate_approval(
            workflow_id=self._task.workflow_id, approval_id=approval_id
        )
        if request.approved:
            return self._service.consume_approval(
                workflow_id=self._task.workflow_id,
                approval_id=approval_id,
                checksums=checksums,
            )
        return request

    def _current_approval_checksums(
        self, *, qa_performed: bool, qa_verdict: str | None
    ) -> ApprovalChecksums:
        branch_state = repository_skills.inspect_current_branch(self._repository_path).unwrap()
        latest = self._latest_implementation_result()
        return ApprovalChecksums(
            repo_state=checksum_of_text(
                f"branch={branch_state.branch};head_sha={branch_state.head_sha}"
            ),
            diff=checksum_of_mapping({"changed_paths": sorted(self._working_tree_paths())}),
            agent_result=checksum_of_agent_result(latest),
            gate_result=checksum_of_mapping(
                {
                    "validation_passed": True,
                    "qa_performed": qa_performed,
                    "qa_verdict": qa_verdict,
                }
            ),
        )

    def _qa_status_for_checksums(self, qa_round: int) -> tuple[bool, str | None]:
        """Re-derive what `QA_RUNNING` already decided, from its own persisted report — never an
        in-memory field — so the approval gate's `gate_result` checksum is stable across every
        revisit to `READY_TO_COMMIT`, including after a process restart."""
        if not self._qa_policy.independent_qa_required:
            return False, None
        existing = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="qa",
        )
        if existing.ok and existing.value:
            matching = [report for report in existing.value if report.sequence == qa_round]
            if matching:
                return True, str(matching[-1].content.get("verdict", "REJECTED")).lower()
        return True, None  # pragma: no cover - defensive; QA_RUNNING always persists one first

    # -- READY_TO_COMMIT / COMMITTED / PUSHED (idempotent Skills; see module docstring §1) ------

    def _handle_ready_to_commit(self) -> ImplementerStepOutcome:
        """The approval gate lives here, immediately before the one commit this workflow ever
        makes — not at `QA_RUNNING` — matching `READY_TO_COMMIT`'s own name: implementation,
        validation, and QA are all already done; only the human gate stands between here and
        `create_commit`. Revisited by every `step()` call while a human decides, potentially for a
        long time, so the checksums are recomputed fresh on every visit and the commit itself is
        never attempted until the approval is actually consumed.
        """
        state = WorkflowState.READY_TO_COMMIT
        qa_round = len(self._session.reconstruct_repair_attempts()) + 1
        qa_performed, qa_verdict = self._qa_status_for_checksums(qa_round)

        approval = self._run_approval_gate(qa_performed=qa_performed, qa_verdict=qa_verdict)
        if approval.status in (
            ApprovalStatus.PENDING,
            ApprovalStatus.HUMAN_INTERVENTION_REQUIRED,
            ApprovalStatus.ESCALATED,
        ):
            return ImplementerStepOutcome(
                state,
                None,
                ImplementerPhase.AWAITING_APPROVAL,
                f"awaiting approval decision: {approval.status.value}",
            )
        if approval.status is not ApprovalStatus.CONSUMED:
            # REJECTED, CHANGES_REQUESTED, FAILED, CANCELLED, or INVALIDATED. No edge from
            # READY_TO_COMMIT reaches REPAIRING (ALLOWED_TRANSITIONS permits only ->COMMITTED and
            # ->FAILED from here) — a human veto at the final gate is a harder stop than a QA
            # rejection earlier in the pipeline, not a repairable defect, so this fails directly
            # rather than looping back.
            return self._fail(
                state,
                f"approval {approval.approval_id!r} is {approval.status.value}",
                context={"approval_id": approval.approval_id, "status": approval.status.value},
            )

        branch = self._task.planned_stage_branch

        def action() -> SkillResult[Any]:
            head = repository_skills.inspect_current_branch(self._repository_path).unwrap()
            return git_github_skills.create_commit(
                self._repository_path,
                branch=branch,
                message=self._task.commit_message,
                expected_head_sha=head.head_sha,
            )

        return self._run_idempotent_side_effect(
            state,
            action=action,
            forward_state=WorkflowState.COMMITTED,
            describe_success=lambda value: f"commit {value.commit_sha} created on {branch!r}",
        )

    def _handle_committed(self) -> ImplementerStepOutcome:
        branch = self._task.planned_stage_branch

        def action() -> SkillResult[Any]:
            head = repository_skills.inspect_current_branch(self._repository_path).unwrap()
            return git_github_skills.push_stage_branch(
                self._repository_path,
                branch=branch,
                remote=self._config.remote_name,
                expected_head_sha=head.head_sha,
                allowed_environment_variables=tuple(self._config.allowed_environment_variables),
            )

        return self._run_idempotent_side_effect(
            WorkflowState.COMMITTED,
            action=action,
            forward_state=WorkflowState.PUSHED,
            describe_success=lambda value: f"pushed {value.remote_ref} at {value.head_sha}",
        )

    def _handle_pushed(self) -> ImplementerStepOutcome:
        branch = self._task.planned_stage_branch

        def action() -> SkillResult[Any]:
            head = repository_skills.inspect_current_branch(self._repository_path).unwrap()
            return git_github_skills.create_pull_request(
                self._repository_path,
                branch=branch,
                baseline_branch=self._config.baseline_branch,
                title=self._task.pull_request_title,
                body=self._task.pull_request_body,
                head_sha=head.head_sha,
                allowed_environment_variables=tuple(self._config.allowed_environment_variables),
            )

        return self._run_idempotent_side_effect(
            WorkflowState.PUSHED,
            action=action,
            forward_state=WorkflowState.PR_OPEN,
            describe_success=lambda value: f"pull request #{value.number} open at {value.url}",
        )

    def _run_idempotent_side_effect(
        self,
        state: WorkflowState,
        *,
        action: Callable[[], SkillResult[Any]],
        forward_state: WorkflowState,
        describe_success: Callable[[Any], str],
    ) -> ImplementerStepOutcome:
        """One bounded attempt at an already-idempotent Git/GitHub Skill.

        Whether this call is a fresh first attempt, an ordinary bounded retry, or the
        reconciliation of a crash detected via `has_unreconciled_initial_execution_attempt`, the
        action taken is identical: invoke the Skill again. Each of `create_commit`/
        `push_stage_branch`/`create_pull_request` independently re-verifies its own precondition
        against live repository/GitHub state before doing anything, which *is* the reconciliation
        (see the module docstring's engineering-decision note §1) — there is no separate "just
        observe, don't act" branch here because observing *is* what the Skill's own first action
        already does.
        """
        attempts = self._session.reconstruct_initial_execution_attempts(state)
        attempt_number = len(attempts) + 1
        if attempt_number > INITIAL_EXECUTION_ATTEMPT_LIMIT:
            return self._fail(
                state,
                f"{attempt_number - 1} of {INITIAL_EXECUTION_ATTEMPT_LIMIT} attempts already "
                "used; no further attempts are permitted",
                context={"attempt_count": attempt_number - 1},
            )
        self._session.record_initial_execution_attempt_started(
            state, attempt_number=attempt_number, start_time=_iso_now()
        )
        result = action()
        self._session.record_initial_execution_attempt(
            state, attempt_number=attempt_number, completion_time=_iso_now()
        )
        if result.ok:
            self._session.transition_to(forward_state, actor="orchestrator")
            return ImplementerStepOutcome(
                state, forward_state, ImplementerPhase.ADVANCED, describe_success(result.value)
            )
        if attempt_number >= INITIAL_EXECUTION_ATTEMPT_LIMIT:
            return self._fail(
                state,
                f"{attempt_number} of {INITIAL_EXECUTION_ATTEMPT_LIMIT} attempts exhausted: "
                f"{result.error}",
                context={"attempt_count": attempt_number},
            )
        return self._run_idempotent_side_effect(
            state, action=action, forward_state=forward_state, describe_success=describe_success
        )

    # -- Shared plumbing ------------------------------------------------------------------------

    def _fail(
        self, state: WorkflowState, reason: str, *, context: Mapping[str, Any]
    ) -> ImplementerStepOutcome:
        reporting_skills.generate_failure_report(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            context={"reason": reason, "state": state.value, **context},
        )
        self._session.transition_to(WorkflowState.FAILED, actor="orchestrator")
        return ImplementerStepOutcome(state, WorkflowState.FAILED, ImplementerPhase.FAILED, reason)

    def _working_tree_paths(self) -> tuple[str, ...]:
        tree = repository_skills.inspect_working_tree(self._repository_path)
        if not tree.ok or tree.value is None:
            raise ImplementerModeError(f"could not inspect working tree: {tree.error}")
        return tree.value.paths

    def _current_head_sha(self) -> str:
        return repository_skills.inspect_current_branch(self._repository_path).unwrap().head_sha

    def _session_root(self) -> Path:
        return Path(self._config.state_directory) / "sessions"

    def _invoke_provider(
        self,
        *,
        target: ProviderRuntimeTarget,
        task: str,
        invocation_id: str,
        mode: ExecutionMode,
    ) -> AgentRunResult:
        request = ProviderRunRequest(
            target=target,
            workflow_id=self._task.workflow_id,
            stage_id=self._task.stage_id,
            task=task,
            working_directory=self._repository_path,
            session_root=self._session_root(),
            invocation_id=invocation_id,
        )
        run_result: ProviderRunResult = self._service.invoke_provider(request)
        session_directory = (
            run_result.stdout_artifact.parent if run_result.stdout_artifact is not None else None
        )
        return agent_run_result_from_provider_run(
            run_result,
            workflow_id=self._task.workflow_id,
            mode=mode,
            agent=None,
            session_directory=session_directory,
        )

    def _invoke_claude(self, *, role_label: str, task: str, invocation_id: str) -> AgentRunResult:
        return self._invoke_provider(
            target=ProviderRuntimeTarget.CLAUDE,
            task=task,
            invocation_id=invocation_id,
            mode=ExecutionMode.IMPLEMENTATION,
        )

    def _latest_implementation_result(self) -> AgentRunResult:
        """Re-derive the canonical `AgentRunResult` an approval is bound to, from persisted stage
        reports — never an in-memory field, so re-observing this after a process restart produces
        the identical checksum a fresh, uninterrupted run would have."""
        reports = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="stage",
        )
        if not reports.ok or reports.value is None or not reports.value:
            raise ImplementerModeError("no persisted stage report to bind an approval against")
        latest = reports.value[-1]
        return AgentRunResult.model_validate(latest.content["agent_run_result"])

    def _write_stage_report(self, run_result: AgentRunResult, *, sequence: int | None) -> Path:
        created, modified, deleted = self._classify_working_tree_changes()
        payload: dict[str, Any] = {
            "stage_id": self._task.stage_id,
            "branch": self._task.planned_stage_branch,
            "head_sha": self._current_head_sha(),
            "summary": run_result.summary,
            "commit_message": self._task.commit_message,
            "created_files": created,
            "modified_files": modified,
            "deleted_files": deleted,
            "tests_added": list(run_result.tests_run),
            "final_status": "COMPLETE" if run_result.succeeded else "BLOCKED",
            "agent_run_result": run_result.model_dump(mode="json"),
        }
        artifact = reporting_skills.generate_stage_report(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            results=payload,
            sequence=sequence,
        )
        if not artifact.ok or artifact.value is None:
            raise ImplementerModeError(
                f"could not write the stage completion report: {artifact.error}"
            )
        return artifact.value.path

    def _latest_stage_report_path(self) -> Path:
        reports = reporting_skills.read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=self._task.workflow_id,
            report_kind="stage",
        )
        if not reports.ok or reports.value is None or not reports.value:
            raise ImplementerModeError("no persisted stage completion report to validate")
        return reports.value[-1].path

    def _classify_working_tree_changes(self) -> tuple[list[str], list[str], list[str]]:
        tree = repository_skills.inspect_working_tree(self._repository_path)
        if not tree.ok or tree.value is None:
            raise ImplementerModeError(f"could not inspect working tree: {tree.error}")
        created: list[str] = []
        modified: list[str] = []
        deleted: list[str] = []
        for entry in tree.value.entries:
            if entry.is_untracked or entry.index_status == "A":
                created.append(entry.path)
            elif entry.index_status == "D" or entry.worktree_status == "D":
                deleted.append(entry.path)
            else:
                modified.append(entry.path)
        return sorted(created), sorted(modified), sorted(deleted)
