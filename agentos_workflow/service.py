"""The public application-service boundary for the workflow engine (AUTO-009).

The engine has had a state machine, append-only persistence, Skills, Model Providers, and Agents
since AUTO-002..AUTO-006, but no boundary at which any of it could be *observed* by something
outside the package. This module is that boundary's first half; `agentos_workflow.cli_auto` is the
second::

    workflowctl auto  ->  WorkflowService  ->  agentos_workflow read-only state,
                                               audit, report, and configuration APIs

`WorkflowService` exposes four **read-only** operations — `status`, `list`, `audit`, `report` — and
since AUTO-010 exactly one operation that executes anything, `invoke_provider`. The read-only four
are unchanged and remain read-only; the new one is discussed at the end of this docstring.

**`continue_implementation_to_done` (AUTO-014).** The second lifecycle-advancing operation this
class gains, after `invoke_provider`. Resumes a persisted implementation workflow from `PR_OPEN`
(or a later AUTO-014-owned state) through `DONE` by constructing exactly one
`MergeCloseoutModeDriver` and running it — the same "the entire body is a delegation" discipline
`invoke_provider`'s own docstring describes applies here too: this method decides nothing about
merge policy, check polling, branch retention, or closeout, and adds no lifecycle logic of its
own. It is still not `merge`, `close`, or `finalize` in disguise — it names a continuation, not a
lower-level Git/GitHub verb, the same distinction `invoke_provider` draws for "it names a provider
and a task, not a stage lifecycle step".

The read-only property of the four is structural, not a convention this module asks callers to
respect:

* it holds a `StateStore`, never a `RepositoryLock` and never a `WorkflowSession`, so there is no
  object here through which a write lock could be acquired or a transition recorded;
* every store call it makes is a documented reader (`read_transitions`, `read_command_executions`,
  `current_state`, `list_workflow_ids`), each of which opens its file `O_RDONLY` through the
  descriptor-relative `O_NOFOLLOW` walk `state_store.py` owns;
* report retrieval goes through `skills.reporting.read_reports`, the read counterpart of the four
  generators, which creates no directory, creates no file, and never regenerates or rewrites an
  artifact;
* nothing here runs an Agent, spawns a subprocess, touches Git or GitHub, prompts, or formats for
  a terminal.

It also owns no persistence, parsing, validation, or confinement logic of its own. Every rule that
governs where a record may live, whether a history is replayable, and what a malformed record
means is enforced by the components below it and surfaces through this façade unchanged: a
`StateStoreCorruptionError`, `StateStorePathConfinementError`, `ConfigurationNotFoundError`, or
`ConfigurationRepositoryMismatchError` raised down there is raised out of here, not translated
into something weaker. The two errors this module adds (`WorkflowNotFoundError`,
`ReportNotFoundError`) exist only because no pre-existing error means "this read-only lookup found
nothing" — the closest candidates, `MissingPersistedStateError` and its siblings, are `ResumeError`
subclasses whose meaning is bound to resuming a workflow, which is not what happened here.

Results are typed models rather than dictionaries so that the CLI's JSON contract is a projection
of a checked shape instead of a hand-assembled one, and so a caller that is not a CLI gets
something it can hold onto.

**`invoke_provider` (AUTO-010).** The engine gained the ability to actually run Claude and Codex
non-interactively, and that capability needs a public entry point. It is deliberately one narrow
operation that delegates::

    WorkflowService.invoke_provider -> ProviderRuntime.invoke -> the CLI adapters

and it is bounded in three ways worth stating explicitly, because a service that can execute a
model CLI is a much larger thing than one that can only read:

* **It executes; it does not advance anything.** Invoking a provider records no transition,
  acquires no lock, and touches neither Git nor GitHub. The four reads above are still the only
  things that can observe workflow state, and nothing here can change it — `WorkflowService` still
  holds no `RepositoryLock` and no `WorkflowSession`, so a provider run cannot transition workflow
  state by itself. Deciding what a provider's result *means* for a workflow belongs to the
  Orchestrator and to stages after this one.
* **It adds no workflow verb.** There is still no `start`, `authorize`, `approve`, `reject`,
  `resume`, `cancel`, `prepare`, `review`, `implement`, `commit`, `push`, or `merge`, and this
  method is none of them in disguise: it names a provider and a task, not a stage lifecycle step.
* **It knows nothing about CLIs.** No flag, no executable path, no permission or sandbox mode, no
  subprocess call, and no provider internals appear in this module — it imports exactly three
  names from `providers.runtime` and calls one of them. A caller cannot reach a CLI through this
  boundary except in the shape the runtime allows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentos_workflow.approvals import (
    ApprovalChannel,
    ApprovalChecksums,
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalService,
)
from agentos_workflow.config.loader import load_config
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.merge_closeout import (
    MergeCloseoutModeDriver,
    MergeCloseoutRunOutcome,
    MergeCloseoutTask,
)
from agentos_workflow.orchestrator.engine import TERMINAL_STATES
from agentos_workflow.orchestrator.state_store import (
    CommandExecutionRecord,
    StateStore,
    StateTransitionRecord,
)
from agentos_workflow.providers.runtime import (
    ProviderRunRequest,
    ProviderRunResult,
    ProviderRuntime,
)
from agentos_workflow.skills import SkillFailure
from agentos_workflow.skills.reporting import PersistedReport, read_reports

__all__ = [
    "ApprovalChannel",
    "ApprovalChecksums",
    "ApprovalDecision",
    "ApprovalPolicy",
    "ApprovalRequest",
    "AuditResult",
    "MergeCloseoutRunOutcome",
    "MergeCloseoutTask",
    "ProviderRunRequest",
    "ProviderRunResult",
    "ReportArtifactView",
    "ReportNotFoundError",
    "ReportResult",
    "RepositoryContext",
    "StatusResult",
    "WorkflowListResult",
    "WorkflowNotFoundError",
    "WorkflowService",
    "WorkflowServiceError",
    "WorkflowStatus",
    "WorkflowSummary",
    "open_workflow_service",
]


class WorkflowServiceError(Exception):
    """Base error for the read-only service boundary.

    Deliberately not a subclass of `StateStoreError`, `ConfigurationError`, or `ResumeError`: those
    taxonomies say something about persistence, configuration, or resumption respectively, and a
    lookup that simply found nothing is none of the three. Errors raised by those components pass
    through this façade unchanged rather than being rewrapped in this one.

    `skill_failure` is the one exception to that pass-through rule, and it is a shape difference
    rather than a translation: Skills never raise (`SKILL_CONTRACTS.md` §7), they return a typed
    `SkillFailure`, so a Skill-level problem reaching a boundary whose contract *is* to raise has
    to change form. It changes form without losing anything — the original `skill`, `kind`, and
    `detail` are carried here intact and are still branchable by a caller that wants them.
    """

    def __init__(self, message: str, *, skill_failure: SkillFailure | None = None) -> None:
        super().__init__(message)
        self.skill_failure = skill_failure


class WorkflowNotFoundError(WorkflowServiceError):
    """Raised when a workflow has no persisted transition history under the configured storage.

    Never an empty or invented result: a workflow the engine has not recorded is absent, and
    reporting it as, say, a workflow in state `CREATED` would fabricate a fact the audit trail does
    not contain.
    """


class ReportNotFoundError(WorkflowServiceError):
    """Raised when a specifically requested report kind has no persisted artifact.

    Only raised when the caller named a `report_kind`. Asking for *all* of a workflow's reports and
    finding none is an empty result, not an error — a workflow that has not reached a reporting
    stage legitimately has nothing to show.
    """


class _ServiceModel(BaseModel):
    """`extra="forbid"`, matching every other record model in this package."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RepositoryContext(_ServiceModel):
    """The configured target-repository context, as loaded and validated by the strict schema.

    A projection of `WorkflowConfig`, not a re-parse of it: the fields below are the ones that
    identify *which* repository and *which* storage a read was served from, so a caller can tell
    two configurations apart. The command/executable/timeout/allowlist fields are deliberately
    absent — they describe how the engine would *execute*, which no read-only operation does.
    """

    repository_identity: str
    repository_path: str
    baseline_branch: str
    remote_name: str
    stage_contract_directory: str
    state_directory: str
    audit_directory: str

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> RepositoryContext:
        return cls(
            repository_identity=config.repository_identity,
            repository_path=str(config.repository_path),
            baseline_branch=config.baseline_branch,
            remote_name=config.remote_name,
            stage_contract_directory=str(config.stage_contract_directory),
            state_directory=str(config.state_directory),
            audit_directory=str(config.audit_directory),
        )


class WorkflowStatus(_ServiceModel):
    """One workflow's current persisted state, derived by replay (never a stored snapshot).

    `current_state` is the last transition's `to_state` exactly as persisted, as a plain string
    rather than a `WorkflowState`: a state the enum does not know is a fact about the audit trail
    that must still be reportable, and coercing it would either hide it or fail the whole read.
    `terminal` answers the enum's question about that string honestly — an unrecognized state is
    not terminal, because nothing in `WORKFLOW_STATES.md` says it is.
    """

    workflow_id: str
    current_state: str
    terminal: bool
    stage_id: str
    target_repository: str
    repository_path: str
    transition_count: int
    first_transition_at: str
    last_transition_at: str

    @classmethod
    def from_transitions(
        cls, workflow_id: str, transitions: list[StateTransitionRecord]
    ) -> WorkflowStatus:
        latest = transitions[-1]
        return cls(
            workflow_id=workflow_id,
            current_state=latest.to_state,
            terminal=latest.to_state in {state.value for state in TERMINAL_STATES},
            stage_id=latest.stage_id,
            target_repository=latest.target_repository,
            repository_path=latest.repository_path,
            transition_count=len(transitions),
            first_transition_at=transitions[0].timestamp,
            last_transition_at=latest.timestamp,
        )


class StatusResult(_ServiceModel):
    """`status()`'s result: the repository context, plus one workflow's state when one was named.

    Both halves are always present in shape so a JSON consumer never has to branch on which keys
    exist; `workflow` is `null` when the caller asked only for the target-repository context.
    """

    repository: RepositoryContext
    workflow: WorkflowStatus | None
    workflow_count: int


class WorkflowSummary(_ServiceModel):
    """One row of `list()`. Every field is read from persisted records, never inferred."""

    workflow_id: str
    current_state: str
    terminal: bool
    stage_id: str
    transition_count: int
    last_transition_at: str


class WorkflowListResult(_ServiceModel):
    repository: RepositoryContext
    workflows: list[WorkflowSummary]


class AuditResult(_ServiceModel):
    """`audit()`'s result: both persisted audit histories `AUDIT_MODEL.md` defines, in file order.

    The records are the store's own `StateTransitionRecord`/`CommandExecutionRecord` models, not a
    projection of them, so every field the schema names — including the `gate_evidence_ref`,
    `stdout_ref`, and `stderr_ref` evidence references — survives this boundary intact. Ordering is
    on-disk append order, which the store has already proven non-decreasing in timestamp
    (`_require_monotonic_order`) as part of the same read; a history that is not is corruption and
    raises rather than being silently reordered into something presentable.
    """

    workflow_id: str
    transitions: list[StateTransitionRecord]
    command_executions: list[CommandExecutionRecord]


class ReportArtifactView(_ServiceModel):
    """One persisted report artifact and its content, as read.

    `sha256` is computed over the exact bytes read, so a caller can check that what it received is
    what is on disk without re-reading the file itself.
    """

    report_kind: str
    sequence: int | None
    path: str
    sha256: str
    size_bytes: int
    content: dict[str, Any]

    @classmethod
    def from_persisted(cls, report: PersistedReport) -> ReportArtifactView:
        return cls(
            report_kind=report.report_kind,
            sequence=report.sequence,
            path=str(report.path),
            sha256=report.sha256,
            size_bytes=report.size_bytes,
            content=report.content,
        )


class ReportResult(_ServiceModel):
    workflow_id: str
    report_kind: str | None
    reports: list[ReportArtifactView]


class WorkflowService:
    """One target repository's persisted workflow state and its non-interactive Provider Runtime.

    Constructed from an already-loaded, already-validated `WorkflowConfig` so that configuration
    discovery stays in `config.loader` (where the repository-identity mismatch check lives) and is
    not re-implemented here; `open_workflow_service` below is the convenience that does both.

    The public surface is `APPROVED_OPERATIONS` in `test_service.py`, checked structurally rather
    than merely asserted in prose: four reads (`status`, `list`, `audit`, `report`), one execution
    (`invoke_provider`, AUTO-010), the five approval operations (AUTO-012), and one continuation
    (`continue_implementation_to_done`, AUTO-014). There is deliberately no `start`, `authorize`,
    `reject`, `resume`, `cancel`, `prepare`, `review`, `implement`, `commit`, `push`, or bare
    `merge`/`close`/`finalize` verb, and no accessor that would hand a caller the `StateStore`
    (and through it the append path) back out.
    """

    def __init__(self, config: WorkflowConfig) -> None:
        self._config = config
        self._store = StateStore.for_config(config)
        # Built once and held, because it is stateless and holding it is what makes the
        # delegation checkable: there is exactly one object in this service through which a
        # provider can be reached, and it is not a subprocess API.
        self._provider_runtime = ProviderRuntime(config)
        # AUTO-012. Shares this service's `StateStore`, so an approval and the transition history
        # it will one day gate live under one storage root and one confinement walk. It cannot
        # widen what this service can do: `ApprovalService` holds no provider, no lock, and no
        # workflow session, so reaching it grants no ability to execute or transition anything.
        self._approvals = ApprovalService(self._store)

    # -- status ---------------------------------------------------------------------------

    def status(self, workflow_id: str | None = None) -> StatusResult:
        """The persisted state of one workflow, or the configured target-repository context.

        Acquires no lock and records no transition: the current state is derived by replaying the
        append-only transition history and taking the last record's `to_state`, exactly as
        `StateStore.current_state` documents, so reading a workflow that another process is
        actively advancing observes a consistent prefix rather than blocking it.

        With no `workflow_id`, reports the repository context and how many workflows have persisted
        history. With one, additionally reports that workflow's state, and raises
        `WorkflowNotFoundError` if it has none.
        """
        repository = RepositoryContext.from_config(self._config)
        workflow_count = len(self._store.list_workflow_ids())
        if workflow_id is None:
            return StatusResult(repository=repository, workflow=None, workflow_count=workflow_count)
        transitions = self._store.read_transitions(workflow_id)
        if not transitions:
            raise WorkflowNotFoundError(
                f"No persisted workflow state for workflow_id {workflow_id!r} under "
                f"{self._config.state_directory}."
            )
        return StatusResult(
            repository=repository,
            workflow=WorkflowStatus.from_transitions(workflow_id, transitions),
            workflow_count=workflow_count,
        )

    # -- list -----------------------------------------------------------------------------

    def list(self) -> WorkflowListResult:
        """Every workflow with persisted history under the configured state storage.

        Enumeration and summary come from the same source: a workflow appears here only because
        `<state_directory>/<workflow_id>/transitions.jsonl` exists and replayed, so no row is
        inferred and no storage is created for a repository that has never run one.
        """
        workflows: list[WorkflowSummary] = []
        for workflow_id in self._store.list_workflow_ids():
            transitions = self._store.read_transitions(workflow_id)
            if not transitions:
                # A history file that exists but is empty: real, but it names no state. Omitted
                # rather than reported with an invented one.
                continue
            status = WorkflowStatus.from_transitions(workflow_id, transitions)
            workflows.append(
                WorkflowSummary(
                    workflow_id=status.workflow_id,
                    current_state=status.current_state,
                    terminal=status.terminal,
                    stage_id=status.stage_id,
                    transition_count=status.transition_count,
                    last_transition_at=status.last_transition_at,
                )
            )
        return WorkflowListResult(
            repository=RepositoryContext.from_config(self._config), workflows=workflows
        )

    # -- audit ----------------------------------------------------------------------------

    def audit(self, workflow_id: str) -> AuditResult:
        """The persisted append-only audit trail for one workflow (`AUDIT_MODEL.md` §2-3).

        Both record types are returned, in on-disk append order, with every evidence reference
        intact. A workflow with transitions but no recorded command executions returns an empty
        `command_executions` list — that is a true statement about the trail, not a missing read.
        """
        transitions = self._store.read_transitions(workflow_id)
        commands = self._store.read_command_executions(workflow_id)
        if not transitions and not commands:
            raise WorkflowNotFoundError(
                f"No persisted audit trail for workflow_id {workflow_id!r} under "
                f"{self._config.state_directory} or {self._config.audit_directory}."
            )
        return AuditResult(
            workflow_id=workflow_id, transitions=transitions, command_executions=commands
        )

    # -- report ---------------------------------------------------------------------------

    def report(self, workflow_id: str, *, report_kind: str | None = None) -> ReportResult:
        """The already-persisted report artifacts for one workflow.

        Retrieval only. Nothing on this path generates an implementation, QA, closeout, or
        remediation report, and nothing rewrites or repairs one: a report that is not valid JSON is
        surfaced as a failure, not replaced.
        """
        result = read_reports(
            audit_root=self._config.audit_directory,
            workflow_id=workflow_id,
            report_kind=report_kind,
        )
        if not result.ok or result.value is None:
            raise WorkflowServiceError(str(result.error), skill_failure=result.error)
        if report_kind is not None and not result.value:
            raise ReportNotFoundError(
                f"No persisted {report_kind!r} report for workflow_id {workflow_id!r} under "
                f"{self._config.audit_directory}."
            )
        return ReportResult(
            workflow_id=workflow_id,
            report_kind=report_kind,
            reports=[ReportArtifactView.from_persisted(report) for report in result.value],
        )

    # -- provider runtime -----------------------------------------------------------------

    def invoke_provider(self, request: ProviderRunRequest) -> ProviderRunResult:
        """Run one provider non-interactively and return its typed terminal result (AUTO-010).

        The entire body is a delegation, and that is the design rather than an accident of a thin
        first version. Every decision this operation could plausibly make — which executable, which
        flags, which permission or sandbox mode, what the prompt must say, how long to wait, what
        counts as a result — belongs to a layer that already owns it, and re-deciding any of them
        here would create a second answer that could disagree with the first. What this method
        adds is reach: a caller holding a `WorkflowService` can now execute a provider without
        being handed provider internals to do it with.

        Never raises for a provider outcome. A spawn failure, a timeout, output that violates the
        auto-mode contract, and a provider that reported its own failure all come back as a
        `ProviderRunResult` with status `FAILED` and a typed cause, because a caller has to be able
        to branch on those rather than catch them.
        """
        return self._provider_runtime.invoke(request)

    # -- approvals (AUTO-012) ---------------------------------------------------------------

    def request_approval(
        self,
        *,
        workflow_id: str,
        gate: str,
        approval_id: str,
        checksums: ApprovalChecksums,
        policy: ApprovalPolicy,
        now: datetime | None = None,
    ) -> ApprovalRequest:
        """Open one approval for a named gate, bound to four checksums (AUTO-012).

        Delegates entirely, for the same reason `invoke_provider` does: policy resolution, the
        immutable snapshot, the durable append, and the deadline arithmetic all belong to
        `ApprovalService`, and re-deciding any of them here would create a second answer that could
        disagree with the first.
        """
        return self._approvals.request_approval(
            workflow_id=workflow_id,
            gate=gate,
            approval_id=approval_id,
            checksums=checksums,
            policy=policy,
            now=now,
        )

    def get_approval(self, *, workflow_id: str, approval_id: str) -> ApprovalRequest:
        """Replay one approval exactly as persisted. Evaluates no deadline and writes nothing."""
        return self._approvals.get_approval(workflow_id=workflow_id, approval_id=approval_id)

    def evaluate_approval(
        self, *, workflow_id: str, approval_id: str, now: datetime | None = None
    ) -> ApprovalRequest:
        """Apply the policy's timeout action if the persisted deadline has passed.

        This is the lazy evaluation the foreground engine relies on: no timer, no thread, no
        scheduler. A deadline takes effect the first time anyone looks after it has passed, which
        is why it survives a process or machine restart.
        """
        return self._approvals.evaluate_approval(
            workflow_id=workflow_id, approval_id=approval_id, now=now
        )

    def decide_approval(
        self,
        *,
        workflow_id: str,
        approval_id: str,
        decision: ApprovalDecision,
        approver: str,
        source: ApprovalChannel,
        now: datetime | None = None,
    ) -> ApprovalRequest:
        """Record one manual decision, with its approver, channel, and timestamp."""
        return self._approvals.decide_approval(
            workflow_id=workflow_id,
            approval_id=approval_id,
            decision=decision,
            approver=approver,
            source=source,
            now=now,
        )

    def consume_approval(
        self,
        *,
        workflow_id: str,
        approval_id: str,
        checksums: ApprovalChecksums,
        now: datetime | None = None,
    ) -> ApprovalRequest:
        """Spend one approval, re-checking its checksum binding immediately beforehand.

        Any difference invalidates rather than proceeds. An approval is permission to act on one
        specific state of the world, and this is the moment that claim is verified rather than
        assumed.
        """
        return self._approvals.consume_approval(
            workflow_id=workflow_id, approval_id=approval_id, checksums=checksums, now=now
        )

    # -- merge/closeout continuation (AUTO-014) ---------------------------------------------

    def continue_implementation_to_done(
        self,
        task: MergeCloseoutTask,
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> MergeCloseoutRunOutcome:
        """Resume a persisted implementation workflow from `PR_OPEN` (or a later AUTO-014-owned
        state) through `DONE` (AUTO-014).

        The entire body is a delegation, for the same reason `invoke_provider` is: sequencing,
        transition selection, PR reconciliation, merge eligibility, bounded check polling, merge
        confirmation, baseline update, branch retention, and runtime closeout all belong to
        `MergeCloseoutModeDriver`, and re-deciding any of them here would create a second answer
        that could disagree with the first. This method constructs no `WorkflowSession`,
        `RepositoryLock`, `MergeAgent`, or `CloseoutAgent` of its own — it builds exactly one
        `MergeCloseoutModeDriver` and returns what running it produces.

        Never raises for a workflow-level failure or a still-pending observation: both come back
        as a typed `MergeCloseoutRunOutcome` a caller can branch on. `InvalidStartStateError` (a
        resume against a state AUTO-014 does not own) and every `WorkflowSessionError`/
        `ResumeError` subtype the driver's own `.resume()` can raise still propagate — they are
        refusals to begin, not workflow outcomes to report.
        """
        driver = MergeCloseoutModeDriver.resume(self._config, task=task, sleep=sleep)
        return driver.run_to_done()


def open_workflow_service(
    repository_path: Path, config_path_override: Path | None = None
) -> WorkflowService:
    """Discover and load a target repository's configuration, then open a read-only service on it.

    A module-level function rather than a `WorkflowService` classmethod so that the class's public
    surface stays exactly the four read-only operations and nothing else — a structural claim a
    test can assert, which a constructor hanging off the class would quietly weaken.

    Configuration handling is entirely `config.loader.load_config`'s, including the strict schema
    and the fail-closed repository-identity check that refuses a configuration declaring a
    different target repository than the one asked for.
    """
    return WorkflowService(load_config(repository_path, config_path_override))
