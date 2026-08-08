"""The sole transition authority of the AUTO-016 milestone runner.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 5 (the approved
runtime flow, and the rule that any tripped gate stops with the tree untouched), section 7
(business logic never lives in a CLI handler), section 9 (the thirteen commands this module backs),
section 10 (`ALLOWED_RUN_TRANSITIONS` and the sole transition authority), section 20 (the two human
gates), section 22 invariants 4, 5 and 13, and section 31's implementation stop condition.

One writer of `workflow_state`, and one only
--------------------------------------------
:func:`transition_to` is the single function in the whole package that sets `workflow_state`, and
it refuses any pair outside :data:`~...models.ALLOWED_RUN_TRANSITIONS` rather than performing it
silently. Its sibling :func:`revise_record` carries every other field and **refuses** a
`workflow_state` key, so "no adapter, coordinator or provider report transitions the run" is a
property of the two signatures rather than a rule call sites are asked to respect. The
coordinators this module drives return proposals -- a :class:`~...review.RoundDecision`, a
:class:`~...recovery.RecoveryOutcome`, a parsed provider result -- and this module decides what
each of them means for the run.

Section 4 at every boundary, not only at start
----------------------------------------------
:func:`run_preflight` evaluates section 4's nine entry conditions from independent observations,
and it is called again at every milestone boundary and before every provider invocation, exactly
as section 4's closing sentence requires. `MACHINE_GATES.md` section 2a is why each condition is
re-observed rather than remembered: caller-copied authorization strings are never live evidence.

Nothing is repaired, reverted or retried past a safety stop
-----------------------------------------------------------
Every stop leaves the worktree exactly as it was found. There is no path here that resets,
restores, stashes, rebases, cleans, checks out or deletes repository work, under any condition,
including every failure path (invariant 13). The only mutating Git capability in the package lives
behind :mod:`...approval_git`, is reachable only from the two approval methods of
:class:`MilestoneRunnerApplication`, and ships disabled (section 20).

A recorded ambiguity
--------------------
`RunRecord` requires a `stop_reason` at `HUMAN_INTERVENTION_REQUIRED`, and section 10's closed
`StopReason` vocabulary transcribes only the twelve codes the contract writes in backticks. Two
stops this module can reach -- a failed deterministic verification set, and a provider failure the
run may not repeat -- are named by no code. Coining a thirteenth would widen a closed vocabulary
this work may not widen, so both are recorded under :data:`UNNAMED_STOP_REASON` and the gap is
reported rather than filled by guesswork; the narrower reading is implemented, exactly as
`models.StopReason` already did for section 15's uncoded checks.
"""

import json
import os
import re
import secrets
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.approval_git import (
    REQUIRED_CONFIRMATION,
    ApprovalExecution,
    ApprovalGit,
    ApprovalRefused,
    CommitApproval,
    approval_summary,
    bind_approval,
    unreconciled_attempt,
)
from ai_workflow_engine.milestone_runner.config import (
    RunnerConfig,
    VerificationCommandSettings,
    load_runner_config,
)
from ai_workflow_engine.milestone_runner.git_inspect import (
    GitInspectionError,
    GitReadOnlyInspector,
    RepositoryEvidence,
)
from ai_workflow_engine.milestone_runner.lock import LockContention, RunLock
from ai_workflow_engine.milestone_runner.models import (
    ALLOWED_RUN_TRANSITIONS,
    STATE_SCHEMA_VERSION,
    UNREADABLE_DIGEST,
    ApprovalOperation,
    MilestoneCheckpoint,
    MilestoneSpec,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
    RecoveryCommand,
    RunRecord,
    RunStatus,
    StopReason,
    VerificationResult,
)
from ai_workflow_engine.milestone_runner.plan import MilestonePlan, MilestonePlanLoader, PlanError
from ai_workflow_engine.milestone_runner.prompts import (
    PromptContext,
    render_closure_prompt,
    render_correction_prompt,
    render_implementation_prompt,
    render_review_prompt,
)
from ai_workflow_engine.milestone_runner.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderInvocation,
    ProviderInvoker,
    retry_permitted,
)
from ai_workflow_engine.milestone_runner.providers.claude_cli import ClaudeCLIAdapter
from ai_workflow_engine.milestone_runner.providers.codex_cli import CodexCLIAdapter
from ai_workflow_engine.milestone_runner.recovery import (
    RecoveryContext,
    RecoveryCoordinator,
    RecoveryOutcome,
)
from ai_workflow_engine.milestone_runner.results import (
    MalformedResult,
    MilestoneReportStatus,
    parse_closure_result,
    parse_correction_result,
    parse_milestone_result,
    parse_review_result,
)
from ai_workflow_engine.milestone_runner.review import (
    BudgetLedger,
    FindingsLedger,
    ReviewCoordinator,
    ReviewOutcome,
    ReviewPolicy,
)
from ai_workflow_engine.milestone_runner.scope import ScopeGuard
from ai_workflow_engine.milestone_runner.state import (
    RedactedWrite,
    ResumeAction,
    RunStateStore,
    StateError,
    artifact_root_for,
    write_redacted_artifact,
)
from ai_workflow_engine.milestone_runner.verification import (
    REQUIRED_GOVERNANCE_CHECKS,
    GovernanceCheckResult,
    GovernanceContradiction,
    VerificationExecutor,
    VerificationOutcome,
    build_verification_environment,
    evaluate_governance_gate,
    parse_governance_check_document,
    run_bounded_command,
)

#: The stop reason recorded for the two stops section 10's closed vocabulary does not name. See
#: this module's docstring: the narrower reading is implemented and the gap is reported.
UNNAMED_STOP_REASON: Final = StopReason.GOVERNANCE_CONTRADICTION

#: Section 4 item 1's register, at the path the contract names.
STAGE_REGISTRY_PATH: Final = "docs/workflow-automation/STAGE_REGISTRY.md"

#: The two registry statuses section 4 item 1 admits. A stage in any other state is one AUTO-016
#: refuses to start against -- it never authorizes the stage it implements.
AUTHORIZED_REGISTRY_STATUSES: Final[tuple[str, ...]] = ("AUTHORIZED", "IN_PROGRESS")

#: The largest registry document this module will read.
MAX_REGISTRY_BYTES: Final = 4 << 20

#: Section 14's `focused_verification` entry carries a command and an optional purpose, and no
#: timeout; section 16 requires every command to run under a bound. This is the bound the runner
#: applies to a milestone-supplied command -- a ceiling that makes "bounded" true, never a tuning
#: knob: the configured focused and final sets carry their own per-command timeouts.
MILESTONE_COMMAND_TIMEOUT_SECONDS: Final = 45 * 60

#: How long a bounded governance check may take when the gate is evaluated without a run lock --
#: `doctor` and `verify`, which persist nothing.
UNLOCKED_GOVERNANCE_TIMEOUT_SECONDS: Final = 15 * 60

_RUN_ID_PREFIX: Final = "auto016"
_UTC_TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"
_RUN_ID_STAMP_FORMAT: Final = "%Y%m%dT%H%M%SZ"
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

#: The document at the artifact root naming this repository's current run. Section 9 gives no
#: command a `--run-id`, and nothing in this package enumerates a directory, so the run a command
#: acts on is the one this pointer names -- and only if that run really carries a published state.
LATEST_RUN_POINTER: Final = "latest-run.json"

#: The largest that pointer may be. It holds one run id; anything larger is not this document.
MAX_POINTER_BYTES: Final = 4096

#: Where a run may not be driven from. Both are terminal (section 10) and neither has an outbound
#: edge, so a command that would continue one is refused before anything is observed.
_TERMINAL_STATES: Final[frozenset[RunStatus]] = frozenset({RunStatus.DONE, RunStatus.ABORTED})

#: The states a driven run has stopped in and will not leave without an operator act.
_STOPPED_STATES: Final[frozenset[RunStatus]] = frozenset(
    {
        RunStatus.HUMAN_INTERVENTION_REQUIRED,
        RunStatus.MILESTONE_FAILED,
        RunStatus.READY_FOR_COMMIT_APPROVAL,
        RunStatus.READY_FOR_PUSH_APPROVAL,
        *_TERMINAL_STATES,
    }
)

#: Section 10's provider excursion, as the two states a crash can leave a run sitting in. A
#: resumed run has to make the return trip to the invoking state explicitly, because the
#: excursion's own caller is gone.
_PROVIDER_EXCURSION_STATES: Final[frozenset[RunStatus]] = frozenset(
    {RunStatus.PROVIDER_WAIT, RunStatus.PROVIDER_RETRY_PENDING}
)

#: The states a run reaches when everything went as section 5 describes. Section 31 fixes the
#: first of them as the run's own terminal state with the shipped defaults.
SUCCESSFUL_RUN_STATES: Final[frozenset[RunStatus]] = frozenset(
    {RunStatus.READY_FOR_COMMIT_APPROVAL, RunStatus.READY_FOR_PUSH_APPROVAL, RunStatus.DONE}
)


class ApplicationError(WorkflowEngineError):
    """The application refused to act, and nothing was written or executed."""


class TransitionRefused(ApplicationError):
    """A transition outside `ALLOWED_RUN_TRANSITIONS` was asked for (section 10).

    Refused rather than silently performed. The closed table is the vocabulary the application is
    allowed to speak, and a pair outside it is a caller bug the fail-closed direction refuses
    loudly -- never a state the run quietly ends up in.
    """


class RunRefused(ApplicationError):
    """A command was invoked against a run that cannot serve it (sections 5, 10, 13, 20)."""


# --------------------------------------------------------------------------------------
# Section 10 -- the only two functions that build a new run record
# --------------------------------------------------------------------------------------


def _now(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ApplicationError("A run moment must be timezone-aware UTC")
    return moment.astimezone(UTC).strftime(_UTC_TIMESTAMP_FORMAT)


def _rebuild(record: RunRecord, payload: Mapping[str, Any]) -> RunRecord:
    """Rebuild a record through full validation. Never an in-place write.

    Every derived record satisfies `RunRecord`'s closed schema exactly as the one it came from
    did, so a field a caller moved cannot land in the durable document unvalidated.
    """
    document: dict[str, Any] = json.loads(record.model_dump_json())
    document.update(payload)
    try:
        return RunRecord.model_validate_json(json.dumps(document))
    except ValidationError as exc:
        raise ApplicationError(f"The derived run record is not valid: {exc}") from exc


def _as_document(value: object) -> Any:
    """Reduce a model, a sequence of models or a scalar to plain JSON-shaped data."""
    if isinstance(value, list | tuple):
        return [_as_document(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(value, StopReason | RunStatus | ApprovalOperation):
        return value.value
    return value


def transition_to(
    record: RunRecord,
    target: RunStatus,
    *,
    moment: datetime,
    stop_reason: StopReason | None = None,
    updates: Mapping[str, object] | None = None,
) -> RunRecord:
    """Move `record` to `target`, or refuse (section 10, the sole transition authority).

    The single function in this package that writes `workflow_state`. A pair outside
    :data:`~...models.ALLOWED_RUN_TRANSITIONS` raises :class:`TransitionRefused`; neither terminal
    state has an outbound edge, so `DONE` and `ABORTED` are refused as sources by the table itself
    rather than by a check here.

    `stop_reason` is set on the way in and cleared on every transition that does not carry one, so
    a run that recovered does not keep wearing the reason it stopped for.
    """
    current = record.workflow_state
    if (current, target) not in ALLOWED_RUN_TRANSITIONS:
        raise TransitionRefused(
            f"{current.value} -> {target.value} is not one of the {len(ALLOWED_RUN_TRANSITIONS)} "
            "transitions section 10 admits; a transition outside the closed table is refused, "
            "never silently performed"
        )
    payload: dict[str, Any] = {
        "workflow_state": target.value,
        "stop_reason": None if stop_reason is None else stop_reason.value,
        "updated_at": _now(moment),
    }
    for name, value in (updates or {}).items():
        if name in {"workflow_state", "stop_reason"}:
            raise ApplicationError(
                f"{name!r} is set by the transition itself and never by an update mapping"
            )
        payload[name] = _as_document(value)
    return _rebuild(record, payload)


def revise_record(
    record: RunRecord,
    *,
    moment: datetime,
    updates: Mapping[str, object],
) -> RunRecord:
    """Update any field of `record` except its state (section 10).

    The counterpart of :func:`transition_to`: everything a run accumulates -- provider runs,
    verification results, findings, counters, the changed-path set -- moves through here, and
    `workflow_state` and `stop_reason` cannot, so no coordinator, adapter or provider report can
    transition the run by writing a field.
    """
    payload: dict[str, Any] = {"updated_at": _now(moment)}
    for name, value in updates.items():
        if name in {"workflow_state", "stop_reason"}:
            raise ApplicationError(
                f"{name!r} moves only through transition_to: the application is the sole "
                "transition authority (section 10)"
            )
        payload[name] = _as_document(value)
    return _rebuild(record, payload)


# --------------------------------------------------------------------------------------
# Section 4 -- the nine entry conditions, as typed evidence
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntryCondition:
    """One of section 4's nine entry conditions, as it was evaluated at one moment.

    `evaluated` is a third answer beside satisfied and unsatisfied, and it is an honest one: the
    read-only commands do not acquire the run lock (section 12), so condition 9 is reported as
    unevaluated by them rather than guessed at from a diagnostic file.
    """

    number: int
    name: str
    satisfied: bool
    detail: str
    stop_reason: StopReason | None = None
    evaluated: bool = True

    @property
    def failed(self) -> bool:
        return self.evaluated and not self.satisfied


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Section 4 evaluated once, from independent observations, at one moment."""

    conditions: tuple[EntryCondition, ...]
    evidence: RepositoryEvidence | None = None
    plan: MilestonePlan | None = None
    governance: tuple[GovernanceCheckResult, ...] = ()

    @property
    def satisfied(self) -> bool:
        """Whether every condition that was evaluated is satisfied."""
        return not any(condition.failed for condition in self.conditions)

    @property
    def failures(self) -> tuple[EntryCondition, ...]:
        return tuple(condition for condition in self.conditions if condition.failed)

    @property
    def stop_reason(self) -> StopReason | None:
        """The first failing condition's typed code, when the contract gives it one."""
        for condition in self.failures:
            if condition.stop_reason is not None:
                return condition.stop_reason
        return UNNAMED_STOP_REASON if self.failures else None

    @property
    def summary(self) -> str:
        if self.satisfied:
            return "Every evaluated entry condition of section 4 is satisfied."
        return "; ".join(
            f"item {item.number} ({item.name}): {item.detail}" for item in self.failures
        )


def _read_repository_file(repository_root: Path, relative: str, ceiling: int) -> str | None:
    """Read one repository file with no-follow discipline, or `None` when it is absent."""
    target = repository_root / relative
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        with os.fdopen(descriptor, "rb") as handle:
            payload = handle.read(ceiling + 1)
    except OSError:
        return None
    if len(payload) > ceiling:
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _registry_authorizes(repository_root: Path, stage_id: str) -> tuple[bool, str]:
    """Whether `STAGE_REGISTRY.md` shows `stage_id` as `AUTHORIZED` or `IN_PROGRESS` (item 1).

    The register is read, never written. A row is identified by naming the stage id, and its
    status by one of the two admissible words appearing in the same row; a stage the register does
    not carry, or carries in any other state, is `STAGE_ID_NOT_AUTHORIZED`. AUTO-016 never
    authorizes the stage it implements, so the absence of a row is a refusal rather than a default.
    """
    text = _read_repository_file(repository_root, STAGE_REGISTRY_PATH, MAX_REGISTRY_BYTES)
    if text is None:
        return False, f"{STAGE_REGISTRY_PATH} is absent or unreadable, so no stage is authorized"
    rows = [line for line in text.splitlines() if stage_id in line]
    if not rows:
        return False, f"{STAGE_REGISTRY_PATH} carries no row naming {stage_id}"
    for row in rows:
        for status in AUTHORIZED_REGISTRY_STATUSES:
            if status in row:
                return True, f"{stage_id} is {status} in {STAGE_REGISTRY_PATH}"
    return (
        False,
        f"{stage_id} appears in {STAGE_REGISTRY_PATH} but in none of "
        f"{list(AUTHORIZED_REGISTRY_STATUSES)}",
    )


def _governance_check_commands(config: RunnerConfig) -> dict[str, VerificationCommandSettings]:
    """The configured command for each of section 16's five governance checks.

    Section 21's `verification` section carries a focused and a final set and no third,
    governance-specific one, so a check's command is recognized by its `purpose` naming the check.
    A configuration that names fewer than five leaves the gate unevaluable, which condition 7
    reports honestly rather than treating as a pass.
    """
    return {
        str(settings.purpose): settings
        for settings in config.verification.final
        if settings.purpose in REQUIRED_GOVERNANCE_CHECKS
    }


def _evaluate_governance(
    config: RunnerConfig,
    *,
    repository_root: Path,
    environment: Mapping[str, str],
    executor: VerificationExecutor | None,
) -> EntryCondition:
    """Evaluate section 4 item 7 from machine-readable output only (defect P-7).

    With an executor the five checks run through section 16's persisting path, so their complete
    output lands in the run's transcript directory. Without one -- `doctor` and `verify`, which
    hold no run lock and persist nothing (section 12) -- the same five vectors run bounded and
    their documents are parsed in memory. Both paths read structured results and neither looks at
    a rendered console table.
    """
    checks = _governance_check_commands(config)
    missing = [name for name in REQUIRED_GOVERNANCE_CHECKS if name not in checks]
    if missing:
        return EntryCondition(
            number=7,
            name="governance checks",
            satisfied=False,
            detail=(
                "the configuration names no verification.final command whose purpose is "
                f"{missing}, so the canonical governance gate cannot be evaluated"
            ),
            stop_reason=StopReason.GOVERNANCE_CONTRADICTION,
            evaluated=False,
        )
    try:
        if executor is not None:
            executor.run_governance_gate(checks)
        else:
            results: list[GovernanceCheckResult] = []
            for name in REQUIRED_GOVERNANCE_CHECKS:
                settings = checks[name]
                outcome = run_bounded_command(
                    argv=settings.command,
                    cwd=repository_root,
                    environment=environment,
                    timeout_seconds=min(
                        settings.timeout_seconds, UNLOCKED_GOVERNANCE_TIMEOUT_SECONDS
                    ),
                )
                if outcome.timed_out or outcome.spawn_error is not None:
                    raise GovernanceContradiction(
                        f"The {name} governance check did not produce a result "
                        f"({'timed out' if outcome.timed_out else outcome.spawn_error})"
                    )
                results.append(parse_governance_check_document(outcome.stdout, check_name=name))
            evaluate_governance_gate(results)
    except GovernanceContradiction as exc:
        return EntryCondition(
            number=7,
            name="governance checks",
            satisfied=False,
            detail=str(exc),
            stop_reason=StopReason.GOVERNANCE_CONTRADICTION,
        )
    return EntryCondition(
        number=7,
        name="governance checks",
        satisfied=True,
        detail="the canonical governance checks pass under the single documented tolerance",
    )


def digest_changed_paths(inspector: GitReadOnlyInspector, paths: Sequence[str]) -> dict[str, str]:
    """SHA-256 every changed path, so milestone ownership is decided by content, not by name.

    `GitReadOnlyInspector` exposes exactly one file-digest primitive, and this is it: a bounded,
    no-follow read of a repository-relative path (invariant 8). It is used here for what it does
    rather than for the field it was first written for -- section 20 admits no second Git surface
    and no `diff` vector, so hashing what the inspector already reported changed is the only way
    to obtain a content delta without opening a third path into the repository.

    A path that cannot be read -- deleted since the observation, over the ceiling, or a symlinked
    component -- records :data:`UNREADABLE_DIGEST` rather than raising. That is deliberate: an
    unreadable path is attributed to the milestone under evaluation, which can only produce a
    stop, never a pass.
    """
    digests: dict[str, str] = {}
    for path in paths:
        try:
            digests[path] = inspector.contract_digest(path)
        except GitInspectionError:
            digests[path] = UNREADABLE_DIGEST
    return digests


def milestone_owned_paths(
    inspector: GitReadOnlyInspector,
    changed_paths: Sequence[str],
    checkpoint: MilestoneCheckpoint | None,
) -> list[str]:
    """The changed paths the current milestone introduced or modified (section 15 check 2).

    The delta against the previous durable milestone checkpoint. With no checkpoint -- the first
    milestone of a run -- every changed path is the current milestone's, which is both the
    honest reading and the one the contract's own example produces.
    """
    if checkpoint is None:
        return list(changed_paths)
    digests = digest_changed_paths(inspector, changed_paths)
    return [path for path, digest in digests.items() if checkpoint.differs_from(path, digest)]


def run_preflight(
    config: RunnerConfig,
    *,
    repository_root: Path,
    inspector: GitReadOnlyInspector,
    environment: Mapping[str, str],
    executor: VerificationExecutor | None = None,
    lock_held: bool | None = None,
    milestone: MilestoneSpec | None = None,
    milestone_checkpoint: MilestoneCheckpoint | None = None,
    expected_head_sha: str | None = None,
) -> PreflightReport:
    """Evaluate section 4's nine entry conditions from independent observations.

    Called at start, at **every** milestone boundary and before **every** provider invocation --
    section 4's closing sentence, and `MACHINE_GATES.md` section 2a's rule that an observation is
    obtained rather than remembered. Nothing here writes, transitions or repairs anything: the
    report is evidence, and the caller decides what a failure means.

    `milestone`, when supplied, narrows condition 5's scope check to that milestone's own
    `allowed_files` as well as the cumulative allowlist (section 15 check 2). `lock_held` is the
    caller's own answer to condition 9: a mutating command that holds the lock passes `True`, and a
    read-only command passes `None`, which reports the condition unevaluated rather than assumed.

    `expected_head_sha` is condition 4's expectation, and it defaults to the configured
    `baseline_sha` -- which is what every caller but one passes. Section 4 item 4 admits exactly one
    event that may advance `HEAD`: "a Human Owner-approved commit executed through that gate", whose
    landing point the approval that authorized it records. The section 20 gates pass that recorded
    value, so the push gate that the commit gate hands the run to can actually be reached, and
    every other drift -- including a commit nobody approved -- still fails here.
    """
    conditions: list[EntryCondition] = []
    evidence: RepositoryEvidence | None = None
    plan: MilestonePlan | None = None

    authorized, registry_detail = _registry_authorizes(repository_root, config.stage.stage_id)
    if authorized:
        try:
            digest = inspector.verify_contract_pin(
                config.stage.contract_path, config.stage.contract_sha256
            )
            registry_detail = f"{registry_detail}; the contract pins to {digest}"
        except GitInspectionError as exc:
            authorized, registry_detail = False, str(exc)
    conditions.append(
        EntryCondition(
            number=1,
            name="stage authorized and contract pinned",
            satisfied=authorized,
            detail=registry_detail,
            stop_reason=None if authorized else StopReason.STAGE_ID_NOT_AUTHORIZED,
        )
    )

    try:
        evidence = inspector.evidence()
    except GitInspectionError as exc:
        conditions.append(
            EntryCondition(
                number=2,
                name="repository identity",
                satisfied=False,
                detail=str(exc),
                stop_reason=StopReason.REPOSITORY_IDENTITY_MISMATCH,
            )
        )
        return PreflightReport(conditions=tuple(conditions))

    identity_ok = evidence.repository_identity == config.repository.identity
    conditions.append(
        EntryCondition(
            number=2,
            name="repository identity",
            satisfied=identity_ok,
            detail=(
                f"the worktree is {evidence.repository_identity}"
                if identity_ok
                else f"expected {config.repository.identity}, observed "
                f"{evidence.repository_identity}"
            ),
            stop_reason=None if identity_ok else StopReason.REPOSITORY_IDENTITY_MISMATCH,
        )
    )
    branch_ok = evidence.branch == config.repository.expected_branch
    conditions.append(
        EntryCondition(
            number=3,
            name="branch",
            satisfied=branch_ok,
            detail=(
                f"the worktree is on {evidence.branch}"
                if branch_ok
                else f"expected {config.repository.expected_branch}, observed {evidence.branch}"
            ),
            stop_reason=None if branch_ok else StopReason.BRANCH_MISMATCH,
        )
    )
    expected_head = expected_head_sha or config.repository.baseline_sha
    head_ok = evidence.head_sha == expected_head
    conditions.append(
        EntryCondition(
            number=4,
            name="baseline HEAD",
            satisfied=head_ok,
            detail=(
                f"HEAD is {evidence.head_sha}"
                if head_ok
                else f"expected {expected_head}, observed {evidence.head_sha}"
            ),
            stop_reason=None if head_ok else StopReason.HEAD_DRIFT,
        )
    )

    guard = ScopeGuard.from_config(config)
    decision = guard.evaluate(
        evidence.changed_paths,
        milestone,
        milestone_owned_paths=(
            None
            if milestone is None
            else milestone_owned_paths(inspector, evidence.changed_paths, milestone_checkpoint)
        ),
    )
    milestone_violations = [
        violation
        for violation in decision.violations
        if violation.stop_reason is StopReason.OUT_OF_MILESTONE_SCOPE
    ]
    conditions.append(
        EntryCondition(
            number=5,
            name="working tree inside the cumulative allowlist",
            satisfied=decision.permitted,
            detail=(
                f"{len(evidence.changed_paths)} changed path(s), all inside the allowlist"
                if decision.permitted
                else "; ".join(
                    f"{violation.path}: {violation.detail}" for violation in decision.violations
                )
            ),
            # Section 4 item 5 names `DIRTY_TREE` for a change outside the cumulative allowlist,
            # and section 15 names `OUT_OF_MILESTONE_SCOPE` for the per-milestone check. The
            # milestone code wins when it fired, because it is the more specific of the two.
            stop_reason=(
                None
                if decision.permitted
                else (
                    StopReason.OUT_OF_MILESTONE_SCOPE
                    if milestone_violations
                    else StopReason.DIRTY_TREE
                )
            ),
        )
    )

    try:
        plan = MilestonePlanLoader(config, repository_root).load()
        plan_condition = EntryCondition(
            number=6,
            name="milestone plan",
            satisfied=True,
            detail=(
                f"{len(plan.milestones)} milestone(s) in dependency order, covering "
                f"{len(plan.covered_paths())} path(s) exactly"
            ),
        )
    except PlanError as exc:
        plan_condition = EntryCondition(
            number=6,
            name="milestone plan",
            satisfied=False,
            detail=str(exc),
            stop_reason=getattr(exc, "stop_reason", None) or StopReason.PLAN_COVERAGE_MISMATCH,
        )
    conditions.append(plan_condition)

    conditions.append(
        _evaluate_governance(
            config,
            repository_root=repository_root,
            environment=environment,
            executor=executor,
        )
    )
    conditions.append(
        EntryCondition(
            number=8,
            name="runner configuration",
            satisfied=True,
            detail=(
                f"schema {config.schema_version} loaded and validated for stage "
                f"{config.stage.stage_id}"
            ),
        )
    )
    conditions.append(
        EntryCondition(
            number=9,
            name="run lock",
            satisfied=bool(lock_held),
            detail=(
                "this process holds the run lock for the canonical repository"
                if lock_held
                else "not evaluated: a read-only command never acquires the run lock (section 12)"
            ),
            stop_reason=StopReason.LOCK_CONTENTION,
            evaluated=lock_held is not None,
        )
    )
    return PreflightReport(conditions=tuple(conditions), evidence=evidence, plan=plan)


# --------------------------------------------------------------------------------------
# The typed reports the thirteen commands render
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanReport:
    """`plan`'s answer: the validated plan, or the reason it is not one."""

    satisfied: bool
    detail: str
    plan: MilestonePlan | None = None
    required_coverage: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StatusReport:
    """`status`'s answer: the durable record as it stands, without acquiring anything."""

    run_id: str | None
    record: RunRecord | None
    detail: str

    @property
    def satisfied(self) -> bool:
        """A status read succeeds whenever there is a record to read."""
        return self.record is not None

    def payload(self) -> dict[str, Any]:
        """The record as JSON-shaped data, for `--json`."""
        return {
            "run_id": self.run_id,
            "detail": self.detail,
            "record": None if self.record is None else json.loads(self.record.model_dump_json()),
        }


@dataclass(frozen=True, slots=True)
class VerifyReport:
    """`verify`'s answer: the safety gates re-read, and the full verification set re-run."""

    preflight: PreflightReport
    results: tuple[VerificationResult, ...]

    @property
    def satisfied(self) -> bool:
        return self.preflight.satisfied and all(result.passed for result in self.results)


@dataclass(frozen=True, slots=True)
class RunReport:
    """What a driving command left behind: the run's state, and why it is there."""

    run_id: str
    state: RunStatus
    detail: str
    stop_reason: StopReason | None = None
    completed_milestones: tuple[str, ...] = ()
    current_milestone: str | None = None

    @classmethod
    def of(cls, record: RunRecord, detail: str) -> "RunReport":
        return cls(
            run_id=record.run_id,
            state=record.workflow_state,
            detail=detail,
            stop_reason=record.stop_reason,
            completed_milestones=tuple(record.completed_milestones),
            current_milestone=record.current_milestone,
        )

    @property
    def satisfied(self) -> bool:
        """Section 31: with the shipped defaults a complete run's own terminal state is
        `READY_FOR_COMMIT_APPROVAL`, and reaching a gate is a success rather than a failure.

        `ABORTED` counts too: an abort is an operator act that did exactly what it was asked to
        do, and reporting it as a domain failure would say the command failed when it did not.
        """
        return self.state in SUCCESSFUL_RUN_STATES or self.state is RunStatus.ABORTED


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """What one of section 13's four recovery commands did, and what it cost."""

    command: RecoveryCommand
    run_id: str
    pre_state: RunStatus
    post_state: RunStatus
    summary: str
    budgets_touched: Mapping[str, int] = field(default_factory=dict)

    @property
    def satisfied(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class ApprovalReport:
    """What one of section 20's two gates did: the exact commands, and whether any ran."""

    execution: ApprovalExecution
    approval: CommitApproval
    state: RunStatus
    run_id: str

    @property
    def satisfied(self) -> bool:
        """A print-only gate is a success: it did exactly what the shipped defaults promise."""
        return True

    @property
    def lines(self) -> tuple[str, ...]:
        return (
            f"Run: {self.run_id}",
            f"State: {self.state.value}",
            *approval_summary(self.approval),
            f"Executed: {'yes' if self.execution.executed else 'no'}",
            self.execution.reason,
            "Commands:",
            *(f"  {command}" for command in self.execution.rendered_commands),
        )


# --------------------------------------------------------------------------------------
# The provider binding, and the session a driving command runs inside
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    """Which adapter serves which role (section 17's configured role binding).

    Held as data rather than decided at each call site, which is the prototype's hard-coded
    role-to-provider binding corrected: the application asks the binding, and a test supplies its
    own pair of adapters without any production module knowing that it did.
    """

    implementation: ProviderAdapter
    review: ProviderAdapter

    @classmethod
    def from_config(cls, config: RunnerConfig) -> "ProviderBinding":
        return cls(
            implementation=ClaudeCLIAdapter(settings=config.providers.claude),
            review=CodexCLIAdapter(settings=config.providers.codex),
        )

    def for_role(self, role: ProviderRole) -> ProviderAdapter:
        if role in {ProviderRole.IMPLEMENTATION, ProviderRole.CORRECTION}:
            return self.implementation
        return self.review


@dataclass(frozen=True, slots=True)
class RunSession:
    """Everything one driving command needs, resolved once and held immutably."""

    config: RunnerConfig
    repository_root: Path
    store: RunStateStore
    lock: RunLock
    inspector: GitReadOnlyInspector
    guard: ScopeGuard
    executor: VerificationExecutor
    invoker: ProviderInvoker
    providers: ProviderBinding
    reviewer: ReviewCoordinator
    plan: MilestonePlan
    environment: Mapping[str, str]
    clock: Callable[[], datetime]

    def moment(self) -> datetime:
        return self.clock()

    def context(self, record: RunRecord) -> PromptContext:
        return PromptContext(
            run_id=record.run_id,
            stage_id=self.config.stage.stage_id,
            repository_root=str(self.repository_root),
            expected_branch=record.expected_branch,
            baseline_sha=record.baseline_sha,
            contract_path=self.config.stage.contract_path,
            contract_sha256=record.contract_sha256,
        )


def _publish(
    session: RunSession, record: RunRecord, writes: Sequence[RedactedWrite] = ()
) -> RunRecord:
    """Record every redaction that fired, then publish atomically under the held lock."""
    published = session.store.record_redaction_findings(record, writes)
    session.store.publish(published, lock=session.lock)
    return published


def _stop(
    session: RunSession,
    record: RunRecord,
    *,
    state: RunStatus,
    detail: str,
    stop_reason: StopReason | None = None,
) -> RunRecord:
    """Stop the run at `state`, publish it, and leave the worktree exactly as it was found.

    Section 5: any tripped gate stops with the tree untouched. Nothing here reverts, restores,
    checks out, resets, stashes or deletes anything, on this path or on any other.
    """
    stopped = transition_to(
        record,
        state,
        moment=session.moment(),
        stop_reason=stop_reason,
        updates={"current_milestone": record.current_milestone},
    )
    return _publish(session, stopped)


def _latest_checkpoint(record: RunRecord) -> MilestoneCheckpoint | None:
    """The durable observation the current milestone's delta is measured against.

    The last completed milestone's checkpoint, or `None` before any milestone has completed.
    """
    return record.milestone_checkpoints[-1] if record.milestone_checkpoints else None


def _checkpoint_now(session: RunSession, milestone_id: str) -> MilestoneCheckpoint:
    """Observe the worktree and record it as `milestone_id`'s completion checkpoint.

    Taken at completion rather than carried over from the boundary observation, so a focused
    verification command that touched a file is accounted to the milestone that ran it rather
    than blamed on the next one.
    """
    paths = session.inspector.changed_paths()
    return MilestoneCheckpoint(
        milestone_id=milestone_id,
        recorded_at=_now(session.moment()),
        path_digests=digest_changed_paths(session.inspector, paths),
    )


def _boundary(
    session: RunSession,
    record: RunRecord,
    *,
    milestone: MilestoneSpec | None = None,
) -> PreflightReport:
    """Re-verify section 4 at a milestone boundary or before a provider invocation."""
    return run_preflight(
        session.config,
        repository_root=session.repository_root,
        inspector=session.inspector,
        environment=session.environment,
        executor=session.executor,
        lock_held=session.lock.is_held,
        milestone=milestone,
        milestone_checkpoint=_latest_checkpoint(record),
    )


def _stopped_at_boundary(
    session: RunSession, record: RunRecord, report: PreflightReport
) -> RunRecord:
    return _stop(
        session,
        record,
        state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
        detail=report.summary,
        stop_reason=report.stop_reason or UNNAMED_STOP_REASON,
    )


# --------------------------------------------------------------------------------------
# Section 17 -- one provider invocation, with section 10's PROVIDER_WAIT excursion
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Invoked:
    record: RunRecord
    invocation: ProviderInvocation | None
    detail: str


def _invoke_provider(
    session: RunSession,
    record: RunRecord,
    *,
    role: ProviderRole,
    prompt: str,
    milestone_id: str | None,
) -> _Invoked:
    """Invoke one provider under section 10's `PROVIDER_WAIT` excursion and section 17's retry rule.

    A retry is permitted only for `SPAWN_FAILED` -- the sole provably pre-side-effect class -- and
    the run sits in `PROVIDER_RETRY_PENDING` while it waits, so a crash between attempts is
    distinguishable from one during an attempt. Every attempt's durable record is appended,
    including the failed ones, because a failure is evidence and evidence is never dropped.

    Each attempt is made durable *before* the provider can have an effect, in two documents and
    in this order. `on_started` first records the invocation intent -- the attempt's identity plus
    a content fingerprint of the repository as it stands with the process still non-existent --
    and then appends the attempt's incomplete record and publishes it; the completed record later
    replaces that same row. So a runner that dies mid-invocation leaves both halves of what
    section 13 and `MACHINE_GATES.md` section 2a require resume to reconcile against: a record
    whose last provider run carries no `completed_at`, and durable proof of what the repository
    contained before that run could touch it.

    The intent is written first on purpose. A crash between the two writes leaves an intent no
    provider run claims, which resume reads as "nothing was in flight" -- true, because no process
    ever existed -- whereas the opposite order would leave an in-flight record with no evidence to
    reconcile it against, which is a stop an operator would have to clear by hand.
    """
    origin = record.workflow_state
    adapter = session.providers.for_role(role)
    attempts = 0
    invocation: ProviderInvocation | None = None
    detail = ""
    while True:
        waiting = transition_to(record, RunStatus.PROVIDER_WAIT, moment=session.moment())
        record = _publish(session, waiting)
        started = False

        def _began(pending: ProviderRunRecord) -> None:
            nonlocal record, started
            session.store.record_provider_intent(
                pending=pending,
                evidence=session.inspector.evidence(),
                recorded_at=_now(session.moment()),
                lock=session.lock,
            )
            record = _publish(
                session,
                revise_record(
                    record,
                    moment=session.moment(),
                    updates={"provider_runs": [*record.provider_runs, pending]},
                ),
            )
            started = True

        try:
            invocation = adapter.invoke(
                session.invoker,
                role=role,
                prompt=prompt,
                milestone_id=milestone_id,
                on_started=_began,
            )
        except ProviderError as exc:
            record = transition_to(record, origin, moment=session.moment())
            return _Invoked(record=_publish(session, record), invocation=None, detail=str(exc))
        attempts += 1
        # The in-flight row and the completed one are the same invocation, so the completion
        # replaces it rather than appending a second row for one attempt. An attempt that never
        # became durable -- refused before the process existed -- is simply appended.
        settled = [*record.provider_runs[:-1]] if started else [*record.provider_runs]
        record = revise_record(
            record,
            moment=session.moment(),
            updates={"provider_runs": [*settled, invocation.record]},
        )
        if invocation.succeeded:
            elapsed = invocation.record.duration_ms
            detail = f"{adapter.name} returned for {role.value} in {elapsed}ms"
            break
        failure = invocation.failure_class
        named = failure.value if failure else "unknown"
        detail = f"{adapter.name} failed for {role.value}: {named}"
        if failure is not None and retry_permitted(failure, attempts):
            pending = transition_to(
                record, RunStatus.PROVIDER_RETRY_PENDING, moment=session.moment()
            )
            record = _publish(session, pending)
            record = transition_to(record, RunStatus.PROVIDER_WAIT, moment=session.moment())
            record = _publish(session, record)
            record = transition_to(record, origin, moment=session.moment())
            record = _publish(session, record)
            continue
        break
    back = transition_to(record, origin, moment=session.moment())
    return _Invoked(
        record=_publish(session, back, invocation.writes if invocation else ()),
        invocation=invocation,
        detail=detail,
    )


def _result_text(invocation: ProviderInvocation) -> str:
    """Where a role's machine-readable block came back.

    Codex writes its final message to the answer file the adapter named; Claude returns it on
    stdout. The last message is preferred when there is one, and stdout is the fallback, so one
    parser call site serves both roles without either provider's shape leaking into the flow.
    """
    return invocation.last_message if invocation.last_message else invocation.stdout


def _changed_file_evidence(evidence: RepositoryEvidence) -> str:
    """The review's evidence document: every changed path, in the order the guard sees them.

    Section 20 admits exactly two Git surfaces and the read-only one exposes no diff vector, so a
    textual diff is not something this module may obtain -- a third Git path would be precisely
    defect P-5. The reviewer is invoked read-only inside the worktree and reads the files itself;
    what this document supplies is the exact, bounded set it may read, which is the same
    changed-path evidence the scope guard was evaluated against.
    """
    if not evidence.changed_paths:
        return "This run changed no path."
    lines = [
        "The reviewer is running read-only inside the worktree at "
        f"{evidence.repository_root} on branch {evidence.branch} at {evidence.head_sha}.",
        "Read each path below in the worktree; these are the only paths this run changed.",
        "",
        *(f"- {path}" for path in evidence.changed_paths),
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Section 5 -- the approved runtime flow
# --------------------------------------------------------------------------------------


def _run_verification_set(
    session: RunSession, commands: Sequence[VerificationCommandSettings]
) -> tuple[list[VerificationOutcome], bool]:
    outcomes = session.executor.run_set(commands)
    return outcomes, all(outcome.passed for outcome in outcomes)


def _enter(
    session: RunSession,
    record: RunRecord,
    state: RunStatus,
    *,
    updates: Mapping[str, object] | None = None,
) -> RunRecord:
    """Transition into `state`, or recognize that the record is already sitting in it.

    Section 10's table has no self-edge, and correctly so: the forward flow never re-enters a
    state it already occupies. Resume is the case where it does -- the run was interrupted *in*
    the step it is now continuing -- and that is not a transition at all. Nothing moves, so
    nothing is refused and nothing is published; the step simply carries on from where it
    stopped. Any other source state goes through :func:`transition_to` and is refused if the
    closed table does not admit it.
    """
    if record.workflow_state is state:
        if not updates:
            return record
        return revise_record(record, moment=session.moment(), updates=updates)
    return transition_to(record, state, moment=session.moment(), updates=updates)


def _implement_milestone(
    session: RunSession, record: RunRecord, milestone: MilestoneSpec
) -> RunRecord:
    """Provider-implement one milestone and land at `FOCUSED_VERIFYING`, or stop (section 5).

    The first half of a milestone, separable from the second because resume has to be able to
    continue the two independently: an interrupted implementation is regenerated, an interrupted
    focused verification is not (finding GOV-AUTO-11-F3).
    """
    report = _boundary(session, record, milestone=None)
    if not report.satisfied:
        return _stopped_at_boundary(session, record, report)

    record = _enter(
        session,
        record,
        RunStatus.IMPLEMENTING,
        updates={"current_milestone": milestone.milestone_id},
    )
    record = _publish(session, record)

    prompt = render_implementation_prompt(context=session.context(record), milestone=milestone)
    invoked = _invoke_provider(
        session,
        record,
        role=ProviderRole.IMPLEMENTATION,
        prompt=prompt,
        milestone_id=milestone.milestone_id,
    )
    record = invoked.record
    if invoked.invocation is None or not invoked.invocation.succeeded:
        return _stop(session, record, state=RunStatus.MILESTONE_FAILED, detail=invoked.detail)

    try:
        result = parse_milestone_result(
            _result_text(invoked.invocation), expected_milestone_id=milestone.milestone_id
        )
    except MalformedResult as exc:
        return _stop(session, record, state=RunStatus.MILESTONE_FAILED, detail=str(exc))
    if result.status is not MilestoneReportStatus.COMPLETE:
        return _stop(
            session,
            record,
            state=RunStatus.MILESTONE_FAILED,
            detail=f"{milestone.milestone_id} reported {result.status.value}",
        )

    boundary = _boundary(session, record, milestone=milestone)
    if not boundary.satisfied:
        return _stopped_at_boundary(session, record, boundary)
    observed = boundary.evidence.changed_paths if boundary.evidence else []

    record = transition_to(
        record,
        RunStatus.FOCUSED_VERIFYING,
        moment=session.moment(),
        updates={"changed_paths": list(observed)},
    )
    return _publish(session, record)


def _focus_verify_milestone(
    session: RunSession, record: RunRecord, milestone: MilestoneSpec
) -> RunRecord:
    """Run one milestone's focused verification and land at `MILESTONE_COMPLETE`, or stop.

    The second half of a milestone. Resumable on its own: the implementation it verifies is
    already on disk, and regenerating it would discard finished work for no reason.
    """
    record = _enter(session, record, RunStatus.FOCUSED_VERIFYING)
    outcomes: list[VerificationOutcome] = [
        session.executor.run(
            entry.command,
            timeout_seconds=MILESTONE_COMMAND_TIMEOUT_SECONDS,
            purpose=entry.purpose,
        )
        for entry in milestone.focused_verification
    ]
    configured, _ = _run_verification_set(session, session.config.verification.focused)
    outcomes.extend(configured)
    record = revise_record(
        record,
        moment=session.moment(),
        updates={
            "verification_results": [
                *record.verification_results,
                *(outcome.result for outcome in outcomes),
            ]
        },
    )
    failed = [outcome for outcome in outcomes if not outcome.passed]
    if failed:
        return _stop(
            session,
            record,
            state=RunStatus.MILESTONE_FAILED,
            detail=(
                f"{len(failed)} focused verification command(s) failed for {milestone.milestone_id}"
            ),
        )
    record = transition_to(
        record,
        RunStatus.MILESTONE_COMPLETE,
        moment=session.moment(),
        updates={
            "completed_milestones": [*record.completed_milestones, milestone.milestone_id],
            # The durable evidence section 15 check 2 needs for every milestone after this one:
            # what the worktree held, byte for byte, when this milestone finished.
            "milestone_checkpoints": [
                *record.milestone_checkpoints,
                _checkpoint_now(session, milestone.milestone_id),
            ],
            "current_milestone": None,
        },
    )
    return _publish(session, record, [write for outcome in outcomes for write in outcome.writes])


def _drive_milestone(session: RunSession, record: RunRecord, milestone: MilestoneSpec) -> RunRecord:
    """Implement, scope-check and focus-verify exactly one milestone (section 5)."""
    record = _implement_milestone(session, record, milestone)
    if record.workflow_state is not RunStatus.FOCUSED_VERIFYING:
        return record
    return _focus_verify_milestone(session, record, milestone)


def _final_verify(session: RunSession, record: RunRecord) -> RunRecord:
    """Run the full verification set and land at `REVIEWING`, or stop (sections 16 and 19)."""
    record = _enter(session, record, RunStatus.FINAL_VERIFYING)
    record = _publish(session, record)
    outcomes, passed = _run_verification_set(session, session.config.verification.final)
    record = revise_record(
        record,
        moment=session.moment(),
        updates={
            "verification_results": [
                *record.verification_results,
                *(outcome.result for outcome in outcomes),
            ]
        },
    )
    if not passed:
        return _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail="the full verification set did not pass",
            stop_reason=UNNAMED_STOP_REASON,
        )

    record = transition_to(record, RunStatus.REVIEWING, moment=session.moment())
    return _publish(session, record)


def _review(session: RunSession, record: RunRecord) -> RunRecord:
    """Obtain exactly one bounded review from `REVIEWING`, and honour section 19's budgets.

    Separable from :func:`_final_verify` so a run interrupted after its verification set passed
    resumes into the review rather than re-deriving the whole flow. Re-entry counts a fresh
    attempt -- `review_attempts` is an uncapped counter, not a budget, and a second invocation
    really did happen -- while `successful_review_rounds` still moves only in
    :func:`~...review.consume_round`, which needs a result that parsed. A round interrupted
    before its result parsed therefore consumed nothing, and resuming it raises no ceiling.
    """
    record = _enter(session, record, RunStatus.REVIEWING)
    record = _publish(session, record)
    boundary = _boundary(session, record)
    if not boundary.satisfied:
        return _stopped_at_boundary(session, record, boundary)
    evidence = boundary.evidence

    budget = session.reviewer.record_review_attempt(BudgetLedger.of(record))
    record = revise_record(record, moment=session.moment(), updates=dict(budget.counter_updates()))

    prompt = render_review_prompt(
        context=session.context(record),
        diff=_changed_file_evidence(evidence) if evidence else "",
        changed_paths=record.changed_paths,
        verification_results=record.verification_results,
        max_blockers=session.reviewer.policy.max_blockers,
        blocking_severities=list(session.reviewer.policy.blocking_severities),
    )
    invoked = _invoke_provider(
        session, record, role=ProviderRole.REVIEW, prompt=prompt, milestone_id=None
    )
    record = invoked.record
    if invoked.invocation is None or not invoked.invocation.succeeded:
        return _provider_failure(session, record, invoked.detail)
    try:
        review = parse_review_result(
            _result_text(invoked.invocation),
            max_blockers=session.reviewer.policy.max_blockers,
        )
    except MalformedResult as exc:
        return _provider_failure(session, record, str(exc))

    decision = session.reviewer.accept_review(
        BudgetLedger.of(record), FindingsLedger.of(record), review
    )
    record = revise_record(
        record,
        moment=session.moment(),
        updates={
            **decision.budget.counter_updates(),
            **decision.findings.record_updates(),
        },
    )
    if decision.outcome is ReviewOutcome.APPROVED:
        return _ready_for_commit(session, record, decision.reason)
    if decision.outcome is not ReviewOutcome.NEEDS_CORRECTION:
        return _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail=decision.reason,
            stop_reason=UNNAMED_STOP_REASON,
        )
    record = transition_to(record, RunStatus.NEEDS_CORRECTION, moment=session.moment())
    record = _publish(session, record)
    return _drive_correction(session, record)


def _drive_review(session: RunSession, record: RunRecord) -> RunRecord:
    """Run the full verification set, obtain one bounded review, and honour section 19's budgets."""
    record = _final_verify(session, record)
    if record.workflow_state is not RunStatus.REVIEWING:
        return record
    return _review(session, record)


def _correct(session: RunSession, record: RunRecord) -> RunRecord:
    """The single correction round of section 19, landing at `CLOSURE_VERIFYING` or stopping."""
    boundary = _boundary(session, record)
    if not boundary.satisfied:
        return _stopped_at_boundary(session, record, boundary)

    record = _enter(session, record, RunStatus.CORRECTING)
    record = _publish(session, record)
    ledger = FindingsLedger.of(record)
    open_blockers = [
        finding
        for finding in record.blocking_findings
        if finding.finding_id in ledger.open_blocker_ids
    ]
    prompt = render_correction_prompt(
        context=session.context(record),
        blocking_findings=open_blockers,
        changed_paths=record.changed_paths,
        verification_results=record.verification_results,
    )
    invoked = _invoke_provider(
        session, record, role=ProviderRole.CORRECTION, prompt=prompt, milestone_id=None
    )
    record = invoked.record
    if invoked.invocation is None or not invoked.invocation.succeeded:
        return _provider_failure(session, record, invoked.detail)
    try:
        correction = parse_correction_result(_result_text(invoked.invocation))
    except MalformedResult as exc:
        return _provider_failure(session, record, str(exc))

    decision = session.reviewer.accept_correction(
        BudgetLedger.of(record), FindingsLedger.of(record), correction
    )
    record = revise_record(
        record, moment=session.moment(), updates=dict(decision.budget.counter_updates())
    )
    if decision.outcome is not ReviewOutcome.NEEDS_CLOSURE:
        return _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail=decision.reason,
            stop_reason=UNNAMED_STOP_REASON,
        )

    record = transition_to(record, RunStatus.CLOSURE_VERIFYING, moment=session.moment())
    return _publish(session, record)


def _verify_closure(session: RunSession, record: RunRecord) -> RunRecord:
    """The single closure verification section 19 permits, from `CLOSURE_VERIFYING`."""
    record = _enter(session, record, RunStatus.CLOSURE_VERIFYING)
    record = _publish(session, record)
    outcomes, passed = _run_verification_set(session, session.config.verification.final)
    record = revise_record(
        record,
        moment=session.moment(),
        updates={
            "verification_results": [
                *record.verification_results,
                *(outcome.result for outcome in outcomes),
            ]
        },
    )
    if not passed:
        return _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail="the verification set did not pass after the correction round",
            stop_reason=UNNAMED_STOP_REASON,
        )

    boundary = _boundary(session, record)
    if not boundary.satisfied:
        return _stopped_at_boundary(session, record, boundary)
    ledger = FindingsLedger.of(record)
    open_blockers = [
        finding
        for finding in record.blocking_findings
        if finding.finding_id in ledger.open_blocker_ids
    ]
    prompt = render_closure_prompt(
        context=session.context(record),
        open_findings=open_blockers,
        diff=_changed_file_evidence(boundary.evidence) if boundary.evidence else "",
        changed_paths=record.changed_paths,
        verification_results=record.verification_results,
    )
    invoked = _invoke_provider(
        session, record, role=ProviderRole.CLOSURE, prompt=prompt, milestone_id=None
    )
    record = invoked.record
    if invoked.invocation is None or not invoked.invocation.succeeded:
        return _provider_failure(session, record, invoked.detail)
    try:
        closure = parse_closure_result(
            _result_text(invoked.invocation), open_finding_ids=ledger.open_blocker_ids
        )
    except MalformedResult as exc:
        return _provider_failure(session, record, str(exc))

    decision = session.reviewer.accept_closure(BudgetLedger.of(record), ledger, closure)
    record = revise_record(
        record,
        moment=session.moment(),
        updates={
            **decision.budget.counter_updates(),
            **decision.findings.record_updates(),
        },
    )
    if decision.outcome is not ReviewOutcome.CLEARED:
        return _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail=decision.reason,
            stop_reason=UNNAMED_STOP_REASON,
        )
    return _ready_for_commit(session, record, decision.reason)


def _drive_correction(session: RunSession, record: RunRecord) -> RunRecord:
    """The single correction round and the single closure verification section 19 permits."""
    record = _correct(session, record)
    if record.workflow_state is not RunStatus.CLOSURE_VERIFYING:
        return record
    return _verify_closure(session, record)


def _provider_failure(session: RunSession, record: RunRecord, detail: str) -> RunRecord:
    """Count one provider failure -- which consumes no review budget -- and stop (section 19)."""
    budget = BudgetLedger.of(record).with_provider_failure()
    record = revise_record(record, moment=session.moment(), updates=dict(budget.counter_updates()))
    return _stop(
        session,
        record,
        state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
        detail=detail,
        stop_reason=UNNAMED_STOP_REASON,
    )


def _ready_for_commit(session: RunSession, record: RunRecord, detail: str) -> RunRecord:
    """Section 31: the run's own terminal state with the shipped defaults, and it stops there."""
    record = transition_to(record, RunStatus.READY_FOR_COMMIT_APPROVAL, moment=session.moment())
    return _publish(session, record)


#: Which state a provider excursion returns to, decided by the role that was being invoked.
#: Section 17 binds each role to exactly one invoking state, so this is a lookup, not a guess.
_PROVIDER_ORIGIN: Final[dict[ProviderRole, RunStatus]] = {
    ProviderRole.IMPLEMENTATION: RunStatus.IMPLEMENTING,
    ProviderRole.REVIEW: RunStatus.REVIEWING,
    ProviderRole.CORRECTION: RunStatus.CORRECTING,
    ProviderRole.CLOSURE: RunStatus.CLOSURE_VERIFYING,
}


def _remaining_milestones(session: RunSession, record: RunRecord) -> list[MilestoneSpec]:
    """The plan's milestones this run has not completed, in dependency order."""
    return [
        milestone
        for milestone in session.plan.milestones
        if milestone.milestone_id not in record.completed_milestones
    ]


def _provider_origin(session: RunSession, record: RunRecord) -> RunStatus:
    """The state a `PROVIDER_WAIT` excursion was entered from, read from durable evidence.

    The last recorded invocation names its own role, and section 17 binds each role to one
    invoking state. With no invocation recorded at all the excursion had not yet produced
    evidence, and only one invocation is reachable before the first record exists: the
    implementation of the first incomplete milestone -- or, with none left, the single review.
    """
    if record.provider_runs:
        return _PROVIDER_ORIGIN[record.provider_runs[-1].role]
    return RunStatus.IMPLEMENTING if _remaining_milestones(session, record) else RunStatus.REVIEWING


def _leave_provider_excursion(session: RunSession, record: RunRecord) -> RunRecord:
    """Return from `PROVIDER_WAIT` or `PROVIDER_RETRY_PENDING` to the invoking state.

    Section 10 calls the wait state an excursion out of and back into the state that invoked the
    provider, and a resumed run has to make that return trip explicitly: the excursion's own
    caller is gone. `PROVIDER_RETRY_PENDING` returns through `PROVIDER_WAIT`, which is the only
    edge the closed table gives it -- resuming a bounded retry resumes the retry, and nothing else.
    """
    if record.workflow_state is RunStatus.PROVIDER_RETRY_PENDING:
        record = _publish(
            session, transition_to(record, RunStatus.PROVIDER_WAIT, moment=session.moment())
        )
    origin = _provider_origin(session, record)
    return _publish(session, transition_to(record, origin, moment=session.moment()))


def _drive(session: RunSession, record: RunRecord) -> RunRecord:
    """Drive section 5's flow from wherever the record currently sits, and stop where it says."""
    remaining = _remaining_milestones(session, record)
    for milestone in remaining:
        record = _drive_milestone(session, record, milestone)
        if record.workflow_state in _STOPPED_STATES:
            return record
    if record.workflow_state is RunStatus.MILESTONE_COMPLETE:
        return _drive_review(session, record)
    if record.workflow_state is RunStatus.PREFLIGHT:
        return _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail="the plan carries no milestone left to implement",
            stop_reason=StopReason.PLAN_COVERAGE_MISMATCH,
        )
    return record


def _current_milestone(session: RunSession, record: RunRecord) -> MilestoneSpec | None:
    """The milestone an interrupted step was working on.

    The record's own `current_milestone` when the plan still carries it and it is not already
    complete -- a completed milestone is never rerun -- and otherwise the first incomplete one.
    """
    remaining = _remaining_milestones(session, record)
    named = record.current_milestone
    if named is not None:
        for milestone in remaining:
            if milestone.milestone_id == named:
                return milestone
    return remaining[0] if remaining else None


def _resume_from(session: RunSession, record: RunRecord) -> RunRecord:
    """Continue the interrupted step, then hand back to section 5's flow (section 13).

    Finding GOV-AUTO-11-F3. Every resumable state is dispatched explicitly, so resume continues
    the step the run was actually in rather than restarting the flow and asking the closed table
    for an edge that does not exist:

    * `IMPLEMENTING` -- the implementation was interrupted; the current milestone is implemented,
      and the milestone loop takes it from there.
    * `FOCUSED_VERIFYING` -- the implementation is on disk and finished; its focused verification
      is rerun rather than the milestone regenerated.
    * `PROVIDER_WAIT` / `PROVIDER_RETRY_PENDING` -- the excursion returns to the state that
      invoked the provider, from the recorded role, and that state is then resumed. A bounded
      retry resumes the retry and nothing else.
    * `MILESTONE_COMPLETE` -- the milestone loop advances to the next incomplete milestone, or,
      with none left, into final verification.
    * `FINAL_VERIFYING`, `REVIEWING`, `NEEDS_CORRECTION`, `CORRECTING`, `CLOSURE_VERIFYING` --
      each continues its own step instead of silently returning the record unchanged.

    Idempotence is a property of what the steps do, not of a flag: a step re-entered from its own
    state performs no transition (:func:`_enter`), a completed milestone is never in
    `_remaining_milestones`, no counter is reset anywhere on this path, and nothing here deletes
    or rewrites a file the interrupted provider left behind -- the partial work is exactly what
    the resumed step reads. `HUMAN_INTERVENTION_REQUIRED`, `MILESTONE_FAILED` and the two
    approval gates never reach this function: :func:`resume_run` has already refused or
    no-op-reported them, which is what keeps resume from opening a gate a recovery command owns.
    """
    state = record.workflow_state
    if state in _PROVIDER_EXCURSION_STATES:
        record = _leave_provider_excursion(session, record)
        state = record.workflow_state

    if state in (RunStatus.IMPLEMENTING, RunStatus.FOCUSED_VERIFYING):
        milestone = _current_milestone(session, record)
        if milestone is None:
            return _stop(
                session,
                record,
                state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                detail=(
                    f"the run is at {state.value} with no incomplete milestone left in the plan"
                ),
                stop_reason=StopReason.PLAN_COVERAGE_MISMATCH,
            )
        record = (
            _implement_milestone(session, record, milestone)
            if state is RunStatus.IMPLEMENTING
            else record
        )
        if record.workflow_state is RunStatus.FOCUSED_VERIFYING:
            record = _focus_verify_milestone(session, record, milestone)
        if record.workflow_state in _STOPPED_STATES:
            return record
    elif state is RunStatus.FINAL_VERIFYING:
        record = _final_verify(session, record)
        if record.workflow_state is not RunStatus.REVIEWING:
            return record
        return _review(session, record)
    elif state is RunStatus.REVIEWING:
        return _review(session, record)
    elif state is RunStatus.NEEDS_CORRECTION:
        return _drive_correction(session, record)
    elif state is RunStatus.CORRECTING:
        record = _correct(session, record)
        if record.workflow_state is not RunStatus.CLOSURE_VERIFYING:
            return record
        return _verify_closure(session, record)
    elif state is RunStatus.CLOSURE_VERIFYING:
        return _verify_closure(session, record)

    return _drive(session, record)


def start_run(session: RunSession, *, moment: datetime) -> RunReport:
    """Publish the initial state and drive section 5's flow to its first stop.

    Section 5's `PREFLIGHT` step in full: section 4's conditions are evaluated with the lock
    already held, the initial record is published, the resolved plan is snapshotted beside it, and
    the milestone loop begins. A refused condition publishes the stop rather than raising, so the
    refusal is as durable as a success.
    """
    report = run_preflight(
        session.config,
        repository_root=session.repository_root,
        inspector=session.inspector,
        environment=session.environment,
        executor=session.executor,
        lock_held=session.lock.is_held,
    )
    evidence = report.evidence
    now = _now(moment)
    record = RunRecord(
        schema_version=STATE_SCHEMA_VERSION,
        run_id=session.store.run_id,
        repository_root=str(session.repository_root),
        repository_identity=session.store.repository_id,
        expected_branch=session.config.repository.expected_branch,
        baseline_sha=session.config.repository.baseline_sha,
        contract_sha256=session.config.stage.contract_sha256,
        workflow_state=RunStatus.IDLE,
        created_at=now,
        updated_at=now,
        changed_paths=list(evidence.changed_paths) if evidence else [],
    )
    record = transition_to(record, RunStatus.PREFLIGHT, moment=moment)
    record = _publish(session, record)
    # The run is real from here on, so it becomes findable from here on: a crash anywhere below
    # still leaves `resume` and `status` a pointer to follow (section 9).
    record_latest_run(session.store.artifact_root, session.store.run_id)
    session.store.publish_plan_snapshot(
        json.dumps(
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "milestone_ids": list(session.plan.milestone_ids),
                "source_paths": list(session.plan.source_paths),
                "covered_paths": list(session.plan.covered_paths()),
            },
            indent=2,
        ),
        lock=session.lock,
    )
    if not report.satisfied:
        record = _stopped_at_boundary(session, record, report)
        return RunReport.of(record, report.summary)
    record = _drive(session, record)
    return RunReport.of(record, f"The run stopped at {record.workflow_state.value}.")


def resume_run(session: RunSession, *, moment: datetime) -> RunReport:
    """Continue an interrupted run from exactly where it stopped (section 13).

    Every section 4 condition is re-verified first, and the recorded invocation evidence is
    reconciled against the repository's actual content before any provider is re-invoked -- so a
    completed side effect is never repeated on appearance alone. Running `resume` twice with no
    intervening change is a no-op success.

    The stop is keyed on `RECONCILE_REQUIRED` itself rather than on the unaccounted-path list
    that used to accompany it. The two are no longer the same question: an invocation that
    rewrote a path the record already listed, or one with no durable fingerprint to compare
    against, requires reconciliation while naming no unaccounted path at all, and reading the
    list instead of the verdict would carry those straight into a re-invocation. No budget is
    touched on this path -- the run stops where it stands, with the worktree as it was found.
    """
    record = session.store.load()
    if record.workflow_state in _TERMINAL_STATES:
        raise RunRefused(
            f"Run {record.run_id} is {record.workflow_state.value}; a terminal state has no "
            "outbound edge and resume never reopens one"
        )
    if record.workflow_state is RunStatus.HUMAN_INTERVENTION_REQUIRED:
        raise RunRefused(
            f"Run {record.run_id} stopped at HUMAN_INTERVENTION_REQUIRED "
            f"({record.stop_reason.value if record.stop_reason else 'no reason'}); it exits only "
            "through an explicit recovery command, never through resume (section 13)"
        )
    if record.workflow_state is RunStatus.MILESTONE_FAILED:
        raise RunRefused(
            f"Run {record.run_id} stopped at MILESTONE_FAILED on "
            f"{record.current_milestone}; reopen-milestone is the command that clears it"
        )
    if record.workflow_state in SUCCESSFUL_RUN_STATES:
        return RunReport.of(
            record,
            f"Run {record.run_id} is already at {record.workflow_state.value}; resume repeats "
            "nothing.",
        )

    report = run_preflight(
        session.config,
        repository_root=session.repository_root,
        inspector=session.inspector,
        environment=session.environment,
        executor=session.executor,
        lock_held=session.lock.is_held,
    )
    if not report.satisfied:
        record = _stopped_at_boundary(session, record, report)
        return RunReport.of(record, report.summary)
    if report.evidence is None:  # pragma: no cover - a satisfied report always carries evidence
        raise RunRefused("The preflight report carries no repository observation")

    decision = session.store.resume(report.evidence)
    if decision.action is ResumeAction.RECONCILE_REQUIRED:
        record = _stop(
            session,
            record,
            state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
            detail=decision.reason,
            stop_reason=UNNAMED_STOP_REASON,
        )
        return RunReport.of(record, decision.reason)
    record = _resume_from(session, record)
    return RunReport.of(record, f"The run stopped at {record.workflow_state.value}.")


# --------------------------------------------------------------------------------------
# Section 7 -- the application the thirteen thin CLI handlers call
# --------------------------------------------------------------------------------------


def _conda_bin(name: str) -> Path | None:
    """The `bin` directory of the named conda environment, when this machine has one.

    Section 16 fixes the environment property -- the conda environment's `bin` prepended to `PATH`
    -- and `verification.build_verification_environment` deliberately declines to resolve a *name*
    to a directory, because that is an observation about the machine. This is that observation,
    made from the two variables conda itself exports and from nothing else; when neither resolves,
    `PATH` is left exactly as the caller's environment has it.
    """
    roots: list[Path] = []
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix:
        roots.append(Path(prefix).parent)
    executable = os.environ.get("CONDA_EXE")
    if executable:
        roots.append(Path(executable).parent.parent / "envs")
    for root in roots:
        candidate = root / name / "bin"
        if candidate.is_dir():
            return candidate
    return None


def prompt_for_confirmation(operation: ApprovalOperation) -> str | None:
    """Ask the operator, at the point of use, to type section 20's confirmation for `operation`.

    The prompt goes to stderr and the answer is read from stdin, so a machine-readable stdout is
    never polluted by a gate that changes nothing. A closed stdin returns `None`, which the façade
    refuses exactly as it refuses a mistyped phrase: an unanswered prompt is not a confirmation.
    """
    required = REQUIRED_CONFIRMATION[operation]
    print(
        f"Type {required!r} exactly to execute this {operation.value.lower()}, "
        "or anything else to refuse: ",
        file=sys.stderr,
        end="",
        flush=True,
    )
    line = sys.stdin.readline()
    if not line:
        return None
    return line.rstrip("\n")


def new_run_id(moment: datetime) -> str:
    """A fresh run id: the prefix, a UTC stamp and eight random hexadecimal characters.

    Timestamp-first so the lexicographic order of run ids is their chronological order, which is
    what makes the pointer :func:`record_latest_run` writes readable as "the newest run" rather
    than merely "the last one someone happened to touch".
    """
    stamp = moment.astimezone(UTC).strftime(_RUN_ID_STAMP_FORMAT)
    return f"{_RUN_ID_PREFIX}-{stamp}-{secrets.token_hex(4)}"


def record_latest_run(artifact_root: Path, run_id: str) -> None:
    """Name `run_id` as this repository's current run, at the artifact root (section 9).

    Written the moment a run's initial state is published, so a crash mid-drive still leaves a
    pointer that `resume` and `status` can follow. It goes through `state.py`'s single redaction
    write boundary like every other byte the runner persists (section 17a); there is no second
    path to disk in this module.

    The pointer is a convenience, never an authority: :func:`latest_run_id` re-checks that the run
    it names actually carries a published `state.json` before returning it, so a stale or
    hand-edited pointer produces `None` rather than a run that is not there.
    """
    if _RUN_ID_RE.fullmatch(run_id) is None:
        raise RunRefused(f"{run_id!r} is not a milestone-runner run id")
    write_redacted_artifact(
        artifact_root / LATEST_RUN_POINTER,
        json.dumps({"run_id": run_id}, indent=2, sort_keys=True),
        relative_path=LATEST_RUN_POINTER,
    )


def latest_run_id(artifact_root: Path) -> str | None:
    """This repository's current run, or `None` when there is none.

    Section 9 gives no command a `--run-id` option, so the run a command acts on is the one
    :func:`record_latest_run` last named. The pointer is *read*, never searched for: nothing in
    this package enumerates a directory (invariant 19's discipline, applied package-wide rather
    than only to the worktree), so a run is found by following a recorded name and confirming it.

    Three independent reasons to answer `None`, each of them an honest "there is no run here"
    rather than a guess: no pointer exists, the pointer is unreadable or does not name a run id of
    the right grammar, or the run it names carries no published `state.json`.
    """
    document = _read_repository_file(artifact_root, LATEST_RUN_POINTER, MAX_POINTER_BYTES)
    if document is None:
        return None
    try:
        payload = json.loads(document)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        return None
    return run_id if (artifact_root / run_id / "state.json").is_file() else None


class MilestoneRunnerApplication:
    """The sole transition authority, and the one object the thirteen CLI handlers call.

    Section 7: business logic never lives in a CLI handler. Each of the thirteen methods below is
    one command's whole behaviour -- parse nothing, render nothing, decide everything -- and each
    returns a typed report the handler renders and turns into an exit code.

    Section 12 is enforced by construction: every state-mutating method runs inside
    :meth:`_locked`, which acquires the run lock before anything is read and releases it in a
    `finally`, and the four read-only methods have no path to it. `abort` is a mutating method like
    any other, which is prototype defect P-6's correction.
    """

    def __init__(
        self,
        config: RunnerConfig,
        *,
        repository_root: Path | None = None,
        providers: ProviderBinding | None = None,
        clock: Callable[[], datetime] | None = None,
        run_id: str | None = None,
        confirmation_reader: Callable[[ApprovalOperation], str | None] | None = None,
    ) -> None:
        self._config = config
        self._repository_root = repository_root or Path(config.repository.root)
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._providers = providers
        self._run_id = run_id
        self._confirmation_reader = confirmation_reader or prompt_for_confirmation
        self._inspector = GitReadOnlyInspector(self._repository_root)
        self._environment: Mapping[str, str] = build_verification_environment(
            os.environ, conda_bin=_conda_bin(config.repository.conda_environment)
        )

    @classmethod
    def from_config_path(cls, path: Path) -> "MilestoneRunnerApplication":
        """Load and validate the configuration at `path`, then bind an application to it."""
        return cls(load_runner_config(path))

    # -- resolved locations --------------------------------------------------------------

    @property
    def config(self) -> RunnerConfig:
        return self._config

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def artifact_root(self) -> Path:
        return artifact_root_for(self._config.repository.identity)

    def _resolve_run_id(self, *, create: bool) -> str:
        if self._run_id is not None:
            return self._run_id
        existing = latest_run_id(self.artifact_root)
        if existing is not None and not create:
            return existing
        if create:
            return existing if existing is not None else new_run_id(self._clock())
        raise RunRefused(
            f"No milestone-runner run is recorded for {self._config.repository.identity}; "
            "`start` is the command that creates one"
        )

    def _store(self, run_id: str) -> RunStateStore:
        return RunStateStore.pin(
            repository_id=self._config.repository.identity,
            run_id=run_id,
            repository_root=self._repository_root,
        )

    def _session(self, store: RunStateStore, lock: RunLock, plan: MilestonePlan) -> RunSession:
        return RunSession(
            config=self._config,
            repository_root=self._repository_root,
            store=store,
            lock=lock,
            inspector=self._inspector,
            guard=ScopeGuard.from_config(self._config),
            executor=VerificationExecutor(
                store=store,
                lock=lock,
                repository_root=self._repository_root,
                environment=self._environment,
            ),
            invoker=ProviderInvoker(
                store=store,
                lock=lock,
                repository_root=self._repository_root,
                allowed_environment_variables=self._config.providers.allowed_environment_variables,
            ),
            providers=self._providers or ProviderBinding.from_config(self._config),
            reviewer=ReviewCoordinator(
                policy=ReviewPolicy.from_settings(self._config.review_policy)
            ),
            plan=plan,
            environment=self._environment,
            clock=self._clock,
        )

    def _locked(self, run_id: str) -> RunLock:
        """Acquire the run lock for this canonical repository, or refuse (section 12)."""
        lock = RunLock(
            run_id=run_id,
            repository_identity=self._config.repository.identity,
            artifact_root=self.artifact_root,
        )
        try:
            lock.acquire()
        except LockContention as exc:
            raise RunRefused(f"{exc}") from exc
        return lock

    # -- the four read-only commands (section 12: none of them acquires the lock) ---------

    def doctor(self) -> PreflightReport:
        """`doctor`: evaluate section 4's entry conditions, and change nothing."""
        return run_preflight(
            self._config,
            repository_root=self._repository_root,
            inspector=self._inspector,
            environment=self._environment,
        )

    def plan(self) -> PlanReport:
        """`plan`: load, validate, dependency-order and coverage-reconcile the milestone plan."""
        coverage = tuple(self._config.allowlist.required_coverage)
        try:
            loaded = MilestonePlanLoader(self._config, self._repository_root).load()
        except PlanError as exc:
            return PlanReport(satisfied=False, detail=str(exc), required_coverage=coverage)
        return PlanReport(
            satisfied=True,
            detail=(
                f"{len(loaded.milestones)} milestone(s) in dependency order: "
                f"{', '.join(loaded.milestone_ids)}"
            ),
            plan=loaded,
            required_coverage=coverage,
        )

    def status(self) -> StatusReport:
        """`status`: read the durable record. Safe against a torn read because publication is
        atomic, which is exactly the trade section 12 records for the read-only commands."""
        run_id = self._run_id or latest_run_id(self.artifact_root)
        if run_id is None:
            return StatusReport(
                run_id=None,
                record=None,
                detail=(
                    f"No milestone-runner run is recorded for {self._config.repository.identity}"
                ),
            )
        try:
            record = self._store(run_id).load()
        except StateError as exc:
            return StatusReport(run_id=run_id, record=None, detail=str(exc))
        return StatusReport(
            run_id=run_id,
            record=record,
            detail=(
                f"{record.workflow_state.value}"
                + (f" ({record.stop_reason.value})" if record.stop_reason else "")
            ),
        )

    def verify(self) -> VerifyReport:
        """`verify`: re-run the safety gates and the full verification set, persisting nothing."""
        report = run_preflight(
            self._config,
            repository_root=self._repository_root,
            inspector=self._inspector,
            environment=self._environment,
        )
        results: list[VerificationResult] = []
        for settings in self._config.verification.final:
            outcome = run_bounded_command(
                argv=settings.command,
                cwd=self._repository_root,
                environment=self._environment,
                timeout_seconds=settings.timeout_seconds,
            )
            results.append(
                VerificationResult(
                    command=list(settings.command),
                    exit_code=outcome.exit_code,
                    timed_out=outcome.timed_out,
                    passed=outcome.passed,
                    duration_ms=outcome.duration_ms,
                    # `verify` holds no lock and therefore writes no transcript (section 12); the
                    # reference names where a driven run would have persisted the same output.
                    stdout_path="transcripts/unpersisted.stdout.txt",
                    stderr_path="transcripts/unpersisted.stderr.txt",
                )
            )
        return VerifyReport(preflight=report, results=tuple(results))

    # -- the nine state-mutating commands (every one acquires the lock) -------------------

    def start(self) -> RunReport:
        """`start`: acquire the lock, publish the initial state, and drive section 5's flow."""
        run_id = self._resolve_run_id(create=True)
        lock = self._locked(run_id)
        try:
            store = self._store(run_id)
            if store.exists():
                raise RunRefused(
                    f"Run {run_id} is already published; `resume` continues it and `start` never "
                    "reopens a run"
                )
            plan = MilestonePlanLoader(self._config, self._repository_root).load()
            return start_run(self._session(store, lock, plan), moment=self._clock())
        finally:
            lock.release()

    def resume(self) -> RunReport:
        """`resume`: re-verify section 4, reconcile recorded evidence, and continue."""
        run_id = self._resolve_run_id(create=False)
        lock = self._locked(run_id)
        try:
            store = self._store(run_id)
            plan = MilestonePlanLoader(self._config, self._repository_root).load()
            return resume_run(self._session(store, lock, plan), moment=self._clock())
        finally:
            lock.release()

    def abort(self, *, reason: str) -> RunReport:
        """`abort`: stop the run at `ABORTED`, holding the run lock (prototype defect P-6)."""
        run_id = self._resolve_run_id(create=False)
        lock = self._locked(run_id)
        try:
            store = self._store(run_id)
            record = store.load()
            aborted = transition_to(record, RunStatus.ABORTED, moment=self._clock())
            store.publish(aborted, lock=lock)
            return RunReport.of(aborted, f"Aborted: {reason}")
        finally:
            lock.release()

    def reconcile_milestone(self, *, milestone: str, reason: str) -> RecoveryReport:
        """`reconcile-milestone`: accept a result byte-identical to the run's own transcript."""
        return self._recover(
            lambda coordinator, record, context: coordinator.reconcile_milestone(
                record,
                milestone_id=milestone,
                reason=reason,
                result_path=coordinator.recorded_result_transcript(record, milestone),
                context=context,
            )
        )

    def reopen_milestone(self, *, milestone: str, reason: str) -> RecoveryReport:
        """`reopen-milestone`: reopen one milestone under an explicit Human Owner scope ruling.

        Section 9 gives this command a `--reason` and no separate ruling option, so the operator's
        reason is what is recorded as the ruling -- the narrower reading, with the operator's own
        words rather than a phrase the runner supplied.
        """
        return self._recover(
            lambda coordinator, record, context: coordinator.reopen_milestone(
                record,
                milestone_id=milestone,
                reason=reason,
                human_owner_scope_ruling=reason,
                context=context,
            )
        )

    def recover_failed_review(self, *, classification: str, ruling: str) -> RecoveryReport:
        """`recover-failed-review`: restore one review budget a provider failure consumed."""
        return self._recover(
            lambda coordinator, record, context: coordinator.recover_failed_review(
                record,
                classification=_provider_failure_class(classification),
                human_owner_ruling=ruling,
                reason=ruling,
                context=context,
            )
        )

    def revalidate_correction(self) -> RecoveryReport:
        """`revalidate-correction`: clear a post-correction failure, budgets untouched."""
        return self._recover(
            lambda coordinator, record, context: coordinator.revalidate_correction(
                record,
                reason="revalidate-correction: the post-correction verification failure is cleared",
                context=context,
            )
        )

    def approve_commit(self, *, confirmation: str | None = None) -> ApprovalReport:
        """`approve-commit`: section 20's first gate. Prints the exact commands; executes only
        under the configuration flip, the typed confirmation and a bound single-use approval."""
        return self._approve(ApprovalOperation.COMMIT, confirmation)

    def approve_push(self, *, confirmation: str | None = None) -> ApprovalReport:
        """`approve-push`: section 20's second gate, under exactly the same three conditions."""
        return self._approve(ApprovalOperation.PUSH, confirmation)

    # -- the two shapes the nine mutating commands share ----------------------------------

    def _recover(
        self,
        act: Callable[[RecoveryCoordinator, RunRecord, RecoveryContext], RecoveryOutcome],
    ) -> RecoveryReport:
        """Run one of section 13's four recovery commands under the run lock, and publish it.

        The coordinator proposes and this method disposes: `act` returns a
        :class:`~...recovery.RecoveryOutcome` carrying a validated record, and publishing it is
        the application's act -- section 10's sole transition authority, applied to recovery too.
        """
        run_id = self._resolve_run_id(create=False)
        lock = self._locked(run_id)
        try:
            store = self._store(run_id)
            record = store.load()
            evidence = self._inspector.evidence()
            context = RecoveryContext.observed(evidence, self._clock())
            outcome = act(RecoveryCoordinator(store), record, context)
            store.publish(outcome.record, lock=lock)
            return RecoveryReport(
                command=outcome.command,
                run_id=record.run_id,
                pre_state=outcome.entry.pre_state,
                post_state=outcome.entry.post_state,
                summary=outcome.summary,
                budgets_touched=dict(outcome.budgets_touched),
            )
        finally:
            lock.release()

    def _approve(self, operation: ApprovalOperation, confirmation: str | None) -> ApprovalReport:
        """Section 20's two gates, which differ only in which operation they authorize.

        The approval state is checked first: the façade is reachable only from these two commands
        and only in their two approval states, so a run anywhere else never reaches a gate at all.
        Any earlier gated act the record shows as begun and never consumed is refused next, because
        a repetition is the one outcome nothing here may produce. Section 4 is then re-verified --
        against the `HEAD` an approved commit is allowed to have advanced to, and no other -- an
        approval is bound to a fresh independent observation, and the façade decides, under the
        flip, the typed confirmation and the binding, whether anything runs. With the shipped
        defaults nothing does, and `HEAD`, the reflog and the remote refs are untouched.

        When something does run, the grant and its attempt are published *before* the vector, and
        the consumption -- with, for a commit, where it landed `HEAD` -- replaces that same row
        afterwards. Process loss anywhere in between leaves an attempted, unconsumed approval,
        which the refusal above reads as an act a human has to reconcile.
        """
        required_state = (
            RunStatus.READY_FOR_COMMIT_APPROVAL
            if operation is ApprovalOperation.COMMIT
            else RunStatus.READY_FOR_PUSH_APPROVAL
        )
        run_id = self._resolve_run_id(create=False)
        lock = self._locked(run_id)
        try:
            store = self._store(run_id)
            record = store.load()
            if record.workflow_state is not required_state:
                raise RunRefused(
                    f"Run {run_id} is {record.workflow_state.value}; the {operation.value} gate is "
                    f"reachable only from {required_state.value}"
                )
            interrupted = unreconciled_attempt(record)
            if interrupted is not None:
                raise ApprovalRefused(
                    f"Refusing the {operation.value} gate: the {interrupted.operation.value} "
                    f"approval granted at {interrupted.granted_at} was interrupted -- its "
                    f"execution began at {interrupted.execution_started_at} and no consumption "
                    "was ever recorded, so whether it took effect is not knowable from the record. "
                    "A human has to reconcile it; nothing here repeats an approved act."
                )
            report = run_preflight(
                self._config,
                repository_root=self._repository_root,
                inspector=self._inspector,
                environment=self._environment,
                lock_held=lock.is_held,
                expected_head_sha=_expected_head_sha(record, self._config),
            )
            if not report.satisfied:
                raise ApprovalRefused(
                    f"Refusing the {operation.value} gate: {report.summary}. A failed "
                    "deterministic gate still fails with an approval in hand, and there is no "
                    "override path."
                )
            evidence = report.evidence
            if evidence is None:  # pragma: no cover - a satisfied report carries evidence
                raise ApprovalRefused("The preflight report carries no repository observation")
            moment = self._clock()
            facade = ApprovalGit.from_config(self._config, self._repository_root)
            # Section 20: the typed confirmation is asked for at the point of use and only when
            # the configuration flip is on. With the shipped defaults nothing is prompted, because
            # nothing could execute whatever the answer were.
            if confirmation is None and facade.execution_enabled[operation]:
                confirmation = self._confirmation_reader(operation)
            approval = bind_approval(
                operation=operation,
                record=record,
                evidence=evidence,
                repository_root=self._repository_root,
                moment=moment,
                human_confirmation_supplied=confirmation is not None,
            )
            attempted = False

            def _attempting(pending: CommitApproval) -> None:
                nonlocal record, attempted
                record = revise_record(
                    record,
                    moment=moment,
                    updates={"approvals": [*record.approvals, pending.record]},
                )
                store.publish(record, lock=lock)
                attempted = True

            if operation is ApprovalOperation.COMMIT:
                execution = facade.commit(
                    approval,
                    message=_commit_message(record, self._config),
                    confirmation=confirmation,
                    record=record,
                    evidence=evidence,
                    moment=moment,
                    on_execute=_attempting,
                )
            else:
                execution = facade.push(
                    approval,
                    confirmation=confirmation,
                    record=record,
                    evidence=evidence,
                    moment=moment,
                    on_execute=_attempting,
                )
            recorded = execution.approval or approval
            if execution.executed and operation is ApprovalOperation.COMMIT:
                # Section 4 item 4: the approved commit is the one event that may advance `HEAD`,
                # and where it landed is recorded with the approval that authorized it -- observed
                # now, from the read-only inspector, never computed from the vector.
                recorded = recorded.landed_at(self._inspector.evidence().head_sha)
            # The attempt row and the consumption are one approval, so the consumption replaces
            # the row the attempt published rather than adding a second one for one act.
            settled = [*record.approvals[:-1]] if attempted else [*record.approvals]
            record = revise_record(
                record,
                moment=moment,
                updates={"approvals": [*settled, recorded.record]},
            )
            if execution.executed:
                record = transition_to(
                    record,
                    (
                        RunStatus.READY_FOR_PUSH_APPROVAL
                        if operation is ApprovalOperation.COMMIT
                        else RunStatus.DONE
                    ),
                    moment=moment,
                )
            store.publish(record, lock=lock)
            return ApprovalReport(
                execution=execution,
                approval=recorded,
                state=record.workflow_state,
                run_id=run_id,
            )
        finally:
            lock.release()


def _provider_failure_class(value: str) -> ProviderFailureClass:
    """Resolve `--classification` to section 17's typed taxonomy, or refuse."""
    try:
        return ProviderFailureClass(value)
    except ValueError as exc:
        raise RunRefused(
            f"{value!r} is not one of section 17's failure classes "
            f"{sorted(member.value for member in ProviderFailureClass)}"
        ) from exc


def _commit_message(record: RunRecord, config: RunnerConfig) -> str:
    """The message the commit gate would use, derived from the run rather than from an operator.

    Section 9 gives `approve-commit` no message option, so the message is a deterministic function
    of what the run actually did: the stage it implemented, the milestones it completed, and the
    run id that recorded them.
    """
    milestones = ", ".join(record.completed_milestones) or "no milestone"
    return (
        f"feat({config.stage.stage_id.lower()}): implement {milestones}\n\n"
        f"Milestone runner run {record.run_id} on {record.expected_branch} from baseline "
        f"{record.baseline_sha}.\n"
    )


def _expected_head_sha(record: RunRecord, config: RunnerConfig) -> str:
    """Where section 4 item 4 expects `HEAD` to be at a section 20 gate.

    The configured baseline, which is invariant "for the whole run up to the section 20 commit
    gate" -- unless the run's own durable record carries a consumed commit approval that says where
    the one permitted advance landed. That record is the runner's own evidence of an act a Human
    Owner authorized, not a caller-supplied string, so reading it is not the caller-copied
    authorization `MACHINE_GATES.md` section 2a refuses; the observation it is compared against is
    still obtained fresh. Any other `HEAD` -- a commit nobody approved, a drift from elsewhere --
    matches nothing here and still fails condition 4.
    """
    for approval in reversed(record.approvals):
        if (
            approval.operation is ApprovalOperation.COMMIT
            and approval.consumed
            and approval.resulting_head_sha is not None
        ):
            return approval.resulting_head_sha
    return config.repository.baseline_sha
