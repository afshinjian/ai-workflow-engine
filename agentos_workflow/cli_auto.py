"""The additive ``workflowctl auto`` sub-application (AUTO-009, extended by AUTO-014).

The second half of the boundary `agentos_workflow.service` opens::

    workflowctl auto  ->  WorkflowService  ->  agentos_workflow state, audit, report, and
                                               continuation APIs

Five commands — ``status``, ``list``, ``audit``, ``report``, ``continue`` — each of which does
nothing but parse options, call the matching `WorkflowService` operation, and render the typed
result it gets back. There is no business logic here and none in the service's caller: the CLI
decides presentation, the service decides everything else. Nothing in this module can start,
authorize, approve, reject, resume, cancel, commit, push, or merge anything, because the object it
holds has no such method.

**``continue`` (AUTO-014).** The first command in this module that advances a workflow rather than
only reading it. It parses the same caller-supplied identity `MergeCloseoutTask` already requires
(`ImplementationTask`'s own discipline — nothing is recovered from persisted state, see
`merge_closeout`'s module docstring) and calls exactly one `WorkflowService` operation,
`continue_implementation_to_done`. No merge policy, polling, branch, or closeout decision is made
here; a `MergeCloseoutRunOutcome` — success, still-pending, or failure — is rendered exactly as
returned.

**Why the `ai_workflow_engine` imports below are deferred into function bodies.**
`src/ai_workflow_engine/cli.py` imports this module to register `auto_app`. A module-level import
back into `ai_workflow_engine.cli` would therefore be a circular import that breaks whichever of
the two is imported first — and importing this module directly is exactly what its own tests do.
Deferring the import to call time removes the cycle entirely (by then both modules are fully
initialised) while still letting all four commands reuse the *existing* output, error-envelope,
exit-code, and stderr helpers verbatim. That reuse is the point: re-implementing `_protected`'s
v1-stderr / v2-envelope split, or `_write_stdout`'s Rich-bypassing exact-bytes discipline, would
create a second copy of the CLI contract that could drift from the first, which is precisely the
failure this stage was told to avoid.

Option and exit-code conventions follow this repository's existing CLI rather than
`docs/workflow-automation/CLI_SPEC.md` §3-4 where the two differ (`--output human|json` rather
than `text|json`; the engine's 0/1/2 exit codes rather than the future `agentos workflow`
namespace's 0/1/2/3). CLI_SPEC governs the not-yet-built `agentos workflow` namespace; this is
`workflowctl`, and a sub-application that spelled its own options differently from every other
`workflowctl` command would be the larger inconsistency. `--target-repo`/`--config` keep CLI_SPEC's
names and meanings, since those name AgentOS concepts the engine CLI has none of.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, TypeVar, cast

import typer

from agentos_workflow.merge_closeout import (
    MergeCloseoutRunOutcome,
    MergeCloseoutStepOutcome,
    MergeCloseoutTask,
)
from agentos_workflow.service import (
    AuditResult,
    ReportResult,
    StatusResult,
    WorkflowListResult,
    WorkflowService,
    open_workflow_service,
)

if TYPE_CHECKING:  # never imported at runtime: see the module docstring's cycle note
    from ai_workflow_engine.cli import OutputFormat as _EngineOutputFormat

__all__ = ["OutputFormat", "auto_app"]

T = TypeVar("T")

auto_app = typer.Typer(
    help=(
        "Inspection of persisted AgentOS workflow state, audit trails, and reports, plus one "
        "continuation command. Every command but `continue` only reads; `continue` resumes an "
        "already-authorized workflow from PR_OPEN through DONE and touches no repository beyond "
        "what MergeCloseoutModeDriver itself does. No command starts, authorizes, approves, "
        "rejects, or cancels a workflow."
    )
)


class OutputFormat(StrEnum):
    """A structural mirror of `ai_workflow_engine.cli.OutputFormat`.

    Restated rather than imported because Typer needs the enum at decoration time, which is the one
    moment the cycle described in the module docstring cannot be deferred past. The member names
    and values are identical and pinned by a test, so `--output` accepts exactly the same words
    here as everywhere else in `workflowctl`, and the `cast` in `_protected` below stays honest —
    both are `StrEnum`s whose members *are* the strings `"human"` and `"json"`.
    """

    HUMAN = "human"
    JSON = "json"


TargetRepoOption = Annotated[
    Path,
    typer.Option(
        "--target-repo",
        help="Target repository whose AgentOS configuration and persisted state to read.",
        # Existence and readability are checked by `config.loader`, never by Click's argument
        # parsing, so a missing or unreadable path is reported through the stable JSON/stderr
        # contract instead of bypassing it -- the same reason `migrate`'s `--source` does this.
        exists=False,
        readable=False,
        file_okay=False,
    ),
]
ConfigOverrideOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help="Override the default <target-repo>/.agentos/workflow.yaml discovery.",
        dir_okay=False,
        exists=False,
        readable=False,
    ),
]
WorkflowIdOption = Annotated[str, typer.Option("--workflow-id")]
OptionalWorkflowIdOption = Annotated[
    str | None,
    typer.Option("--workflow-id", help="Report one workflow instead of the repository context."),
]
ReportKindOption = Annotated[
    str | None,
    typer.Option(
        "--report-kind",
        help="Only this report kind (e.g. stage, qa, failure, closeout). Default: all.",
    ),
]
OutputOption = Annotated[OutputFormat, typer.Option("--output")]
StageIdOption = Annotated[str, typer.Option("--stage-id")]
StageBranchOption = Annotated[str, typer.Option("--stage-branch")]
PullRequestNumberOption = Annotated[int, typer.Option("--pull-request-number")]
ExpectedHeadShaOption = Annotated[str, typer.Option("--expected-head-sha")]
IndependentQaRequiredOption = Annotated[
    bool,
    typer.Option(
        "--independent-qa-required/--no-independent-qa-required",
        help="Whether a real independent QA verdict is required before merge eligibility "
        "(default: required).",
    ),
]


# ------------------------------------------------------------------------------------------
# Emission: the engine CLI's own helpers, reached at call time (see the module docstring).
# ------------------------------------------------------------------------------------------


def _protected(operation: Callable[[], T], *, output: OutputFormat, command: str) -> T:
    """`ai_workflow_engine.cli._protected`, unchanged: v1/human writes `ERROR: ...` to stderr and
    exits 2; v2 JSON writes one error envelope to stdout and exits 1; `--debug` prints the
    traceback. The `cast` crosses the two identical `OutputFormat` mirrors described above.
    """
    from ai_workflow_engine.cli import _protected as engine_protected

    return engine_protected(operation, output=cast("_EngineOutputFormat", output), command=command)


def _emit(command: str, payload: dict[str, object], output: OutputFormat, lines: list[str]) -> None:
    """Render one successful result under whichever contract version is in force.

    Mirrors what `state`, `agent run`, and `migrate` already do: contract v2 wraps the payload in
    the stable success envelope; contract v1 writes canonical JSON as exact bytes; human output
    writes rendered lines. Machine output never goes through Rich, so `FORCE_COLOR` cannot inject
    escape sequences into it.
    """
    from ai_workflow_engine.cli import _contract_v2_success, _contract_version, _write_stdout
    from ai_workflow_engine.prompt.renderer import canonical_json

    if output == OutputFormat.JSON:
        if _contract_version == "2.0.0":
            _write_stdout(_contract_v2_success(command, payload))
            return
        sys.stdout.buffer.write(canonical_json(payload) + b"\n")
        sys.stdout.buffer.flush()
        return
    _write_stdout("\n".join(lines))


def _service_for(
    target_repo: Path, config: Path | None, *, output: OutputFormat, command: str
) -> WorkflowService:
    """Load the target repository's configuration and open a read-only service on it.

    Routed through `_protected` so a missing, unreadable, invalid, or wrong-repository
    configuration is reported through the same contract as any other command failure rather than
    escaping as a traceback.
    """
    return _protected(
        lambda: open_workflow_service(target_repo, config), output=output, command=command
    )


# ------------------------------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------------------------------


def _status_lines(result: StatusResult) -> list[str]:
    lines = [
        f"Repository: {result.repository.repository_identity}",
        f"Path: {result.repository.repository_path}",
        f"Baseline branch: {result.repository.baseline_branch}",
        f"State directory: {result.repository.state_directory}",
        f"Audit directory: {result.repository.audit_directory}",
        f"Persisted workflows: {result.workflow_count}",
    ]
    if result.workflow is None:
        return lines
    workflow = result.workflow
    lines.extend(
        [
            "",
            f"Workflow: {workflow.workflow_id}",
            f"Stage: {workflow.stage_id}",
            f"State: {workflow.current_state}" + (" (terminal)" if workflow.terminal else ""),
            f"Transitions: {workflow.transition_count}",
            f"First transition: {workflow.first_transition_at}",
            f"Last transition: {workflow.last_transition_at}",
        ]
    )
    return lines


@auto_app.command("status")
def auto_status(
    target_repo: TargetRepoOption,
    config: ConfigOverrideOption = None,
    workflow_id: OptionalWorkflowIdOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Report the persisted state of one workflow, or the configured target-repository context."""
    command = "auto-status"
    service = _service_for(target_repo, config, output=output, command=command)
    result = _protected(lambda: service.status(workflow_id), output=output, command=command)
    _emit(command, result.model_dump(mode="json"), output, _status_lines(result))


def _list_lines(result: WorkflowListResult) -> list[str]:
    if not result.workflows:
        return [f"No persisted workflows under {result.repository.state_directory}"]
    lines = [f"Persisted workflows: {len(result.workflows)}"]
    for workflow in result.workflows:
        terminal = " (terminal)" if workflow.terminal else ""
        lines.append(
            f"  {workflow.workflow_id} — {workflow.stage_id} — {workflow.current_state}{terminal} "
            f"— {workflow.transition_count} transition(s) — {workflow.last_transition_at}"
        )
    return lines


@auto_app.command("list")
def auto_list(
    target_repo: TargetRepoOption,
    config: ConfigOverrideOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """List the workflows that have persisted history in the configured AgentOS state storage."""
    command = "auto-list"
    service = _service_for(target_repo, config, output=output, command=command)
    result = _protected(service.list, output=output, command=command)
    _emit(command, result.model_dump(mode="json"), output, _list_lines(result))


def _audit_lines(result: AuditResult) -> list[str]:
    lines = [
        f"Workflow: {result.workflow_id}",
        f"State transitions: {len(result.transitions)}",
    ]
    for index, transition in enumerate(result.transitions, start=1):
        evidence = transition.gate_evidence_ref or "(none)"
        lines.append(
            f"  {index:>3}. {transition.timestamp} {transition.from_state} -> "
            f"{transition.to_state} by {transition.actor} [evidence: {evidence}]"
        )
    lines.append(f"Command executions: {len(result.command_executions)}")
    for index, execution in enumerate(result.command_executions, start=1):
        exit_code = "timeout" if execution.exit_code is None else str(execution.exit_code)
        lines.append(
            f"  {index:>3}. {execution.completion_time} "
            f"{execution.normalized_command_identity} exit={exit_code} "
            f"[stdout: {execution.stdout_ref}] [stderr: {execution.stderr_ref}]"
        )
    return lines


@auto_app.command("audit")
def auto_audit(
    target_repo: TargetRepoOption,
    workflow_id: WorkflowIdOption,
    config: ConfigOverrideOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Print the persisted append-only audit trail for one workflow, in recorded order."""
    command = "auto-audit"
    service = _service_for(target_repo, config, output=output, command=command)
    result = _protected(lambda: service.audit(workflow_id), output=output, command=command)
    _emit(command, result.model_dump(mode="json"), output, _audit_lines(result))


def _report_lines(result: ReportResult) -> list[str]:
    if not result.reports:
        return [f"No persisted reports for workflow {result.workflow_id}"]
    lines = [f"Workflow: {result.workflow_id}", f"Reports: {len(result.reports)}"]
    for report in result.reports:
        sequence = "" if report.sequence is None else f".{report.sequence}"
        lines.append(
            f"  {report.report_kind}{sequence} — {report.size_bytes} byte(s) — "
            f"sha256 {report.sha256} — {report.path}"
        )
    return lines


@auto_app.command("report")
def auto_report(
    target_repo: TargetRepoOption,
    workflow_id: WorkflowIdOption,
    config: ConfigOverrideOption = None,
    report_kind: ReportKindOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Print the persisted report artifacts for one workflow. Generates nothing."""
    command = "auto-report"
    service = _service_for(target_repo, config, output=output, command=command)
    result = _protected(
        lambda: service.report(workflow_id, report_kind=report_kind),
        output=output,
        command=command,
    )
    _emit(command, result.model_dump(mode="json"), output, _report_lines(result))


def _step_payload(step: MergeCloseoutStepOutcome) -> dict[str, object]:
    return {
        "from_state": step.from_state.value,
        "to_state": step.to_state.value if step.to_state is not None else None,
        "phase": step.phase.value,
        "detail": step.detail,
    }


def _continue_payload(result: MergeCloseoutRunOutcome) -> dict[str, object]:
    return {
        "workflow_id": result.workflow_id,
        "final_state": result.final_state.value,
        "reached_done": result.reached_done,
        "steps": [_step_payload(step) for step in result.steps],
    }


def _continue_lines(result: MergeCloseoutRunOutcome) -> list[str]:
    lines = [
        f"Workflow: {result.workflow_id}",
        f"Final state: {result.final_state.value}" + (" (DONE)" if result.reached_done else ""),
        f"Steps: {len(result.steps)}",
    ]
    for index, step in enumerate(result.steps, start=1):
        to_state = step.to_state.value if step.to_state is not None else "(unchanged)"
        lines.append(
            f"  {index:>3}. {step.from_state.value} -> {to_state} [{step.phase.value}] "
            f"{step.detail}"
        )
    return lines


@auto_app.command("continue")
def auto_continue(
    target_repo: TargetRepoOption,
    workflow_id: WorkflowIdOption,
    stage_id: StageIdOption,
    stage_branch: StageBranchOption,
    pull_request_number: PullRequestNumberOption,
    expected_head_sha: ExpectedHeadShaOption,
    independent_qa_required: IndependentQaRequiredOption = True,
    config: ConfigOverrideOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Resume a persisted implementation workflow from PR_OPEN (or a later AUTO-014-owned state)
    through DONE (AUTO-014). Parses options and renders the result; every merge-policy, polling,
    branch-retention, and closeout decision belongs to `WorkflowService` and the driver it calls.
    """
    command = "auto-continue"
    service = _service_for(target_repo, config, output=output, command=command)
    task = MergeCloseoutTask(
        workflow_id=workflow_id,
        stage_id=stage_id,
        planned_stage_branch=stage_branch,
        pull_request_number=pull_request_number,
        expected_head_sha=expected_head_sha,
        independent_qa_required=independent_qa_required,
    )
    result = _protected(
        lambda: service.continue_implementation_to_done(task), output=output, command=command
    )
    _emit(command, _continue_payload(result), output, _continue_lines(result))
