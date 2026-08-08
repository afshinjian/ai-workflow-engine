"""workflowctl command-line interface."""

import json
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeVar, cast

import typer
from rich.console import Console

from ai_workflow_engine import __version__
from ai_workflow_engine.agents.artifacts import build_record, save_run
from ai_workflow_engine.agents.runner import RunnerError, run_agent
from ai_workflow_engine.agents.verification import verify_run
from ai_workflow_engine.commit.gates import (
    run_apply_patch_gate,
    run_commit_gate,
    run_push_gate,
)
from ai_workflow_engine.config import load_config
from ai_workflow_engine.exceptions import UnsupportedSchemaVersionError, WorkflowEngineError
from ai_workflow_engine.git.approval import load_commit_approval, load_push_approval
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.validators import check_git, matching_paths
from ai_workflow_engine.governance.validators import (
    check_governance,
    check_registries,
    check_task_state,
)
from ai_workflow_engine.handover.validators import HandoverSource, check_handover
from ai_workflow_engine.migration.apply import apply_migration
from ai_workflow_engine.migration.errors import ApplyNotAuthorizedError
from ai_workflow_engine.migration.inspect import default_migration_source, inspect_source
from ai_workflow_engine.migration.plan import build_backup_plan, build_recovery_plan
from ai_workflow_engine.milestone_runner.application import (
    ApprovalReport,
    MilestoneRunnerApplication,
    PlanReport,
    PreflightReport,
    RecoveryReport,
    RunReport,
    StatusReport,
    VerifyReport,
)
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.models import (
    PromptSuccess,
    RenderedPrompt,
    WorkflowStage,
    is_workflow_stage,
)
from ai_workflow_engine.prompt.renderer import canonical_json, render_prompt
from ai_workflow_engine.prompt.store import load, save
from ai_workflow_engine.prompt.validator import validate_prompt
from ai_workflow_engine.reporting.console import print_check, print_report
from ai_workflow_engine.reporting.json_report import render_contract_json, render_json
from ai_workflow_engine.result import (
    CheckResult,
    Finding,
    Status,
    VerificationReport,
    combined_status,
)
from ai_workflow_engine.schema.contract import (
    error_envelope,
    resolve_contract_version,
    success_envelope,
)
from ai_workflow_engine.successor_planning.proposal import ProposalRun, propose_successor
from ai_workflow_engine.workflow.event_store import derive_state, record_outcome
from ai_workflow_engine.workflow.events import Verdict, WorkflowEvent
from ai_workflow_engine.workflow.invariants import summarize_workflow
from ai_workflow_engine.workflow.transitions import WorkflowStateError

app = typer.Typer(help="Read-only deterministic governance gates for AI-assisted development.")
console = Console()
_debug = False
_contract_version = "1.0.0"


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"


ConfigOption = Annotated[Path, typer.Option("--config", dir_okay=False)]
OutputOption = Annotated[OutputFormat, typer.Option("--output")]
T = TypeVar("T")


@app.callback()
def callback(
    debug: Annotated[bool, typer.Option("--debug", help="Show tracebacks.")] = False,
    contract_version: Annotated[
        str,
        typer.Option(
            "--contract-version",
            help="CLI JSON contract version: '1' (legacy, default) or '2' (stable envelope).",
        ),
    ] = "1",
) -> None:
    global _debug, _contract_version
    _debug = debug
    try:
        _contract_version = resolve_contract_version(contract_version)
    except UnsupportedSchemaVersionError as exc:
        # Deliberately NOT the v2 error envelope, even under --output json: until a
        # contract version resolves, there is no way to know which envelope shape
        # (v1's none, or v2's) would even apply -- selecting v2 here would silently
        # assume the very thing that failed to validate. So this one case always uses
        # the same fail-closed shape as `_protected`'s v1 path: exact-bytes stderr, no
        # stdout, exit 2 -- raised here in the callback, before any command body runs,
        # so an unknown/unsupported contract version never reaches JSON emission at
        # all. See test_nonsense_contract_version_still_uses_stderr_not_v2_envelope
        # and test_unknown_contract_version_fails_closed_with_no_stdout.
        if _debug:
            traceback.print_exc()
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.stderr.flush()
        raise typer.Exit(code=2) from exc


def _write_stdout(text: str) -> None:
    """Write machine-readable output as exact bytes, bypassing Rich.

    Rich's ``Console`` injects ANSI color codes whenever the environment sets ``FORCE_COLOR``
    (and in other terminal-detection cases), which corrupts the stable 1.0 JSON contract and the
    ``version`` string into unparseable output. Machine output therefore never goes through Rich
    — the same reason ``_protected`` writes raw bytes to stderr (see docs/DECISION_LOG.md).
    """
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.stdout.flush()


def _emit(result: CheckResult, output: OutputFormat) -> None:
    if output == OutputFormat.JSON:
        _write_stdout(
            render_contract_json(
                command=result.check_name,
                contract_version=_contract_version,
                model=result,
                status=result.status,
                summary=result.summary,
                findings=result.findings,
            )
        )
    else:
        print_check(result, console)
    if result.status != Status.PASS:
        raise typer.Exit(code=1)


def _safe_check(name: str, operation: Callable[[], CheckResult]) -> CheckResult:
    try:
        return operation()
    except Exception as exc:  # converted into stable ERROR; --debug prints details
        if _debug:
            traceback.print_exc()
        return CheckResult(
            check_name=name,
            status=Status.ERROR,
            summary=str(exc),
            findings=[Finding(code="check_error", message=str(exc))],
            remediation_hint="Re-run with --debug for diagnostic details.",
        )


def _contract_v2_success(command: str, data: Mapping[str, object]) -> str:
    return render_json(success_envelope(command=command, data=dict(data)))


def _contract_v2_error(
    command: str,
    *,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> str:
    return render_json(
        error_envelope(
            command=command,
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
    )


def _protected(
    operation: Callable[[], T],
    *,
    output: OutputFormat = OutputFormat.HUMAN,
    command: str = "command",
) -> T:
    try:
        return operation()
    except Exception as exc:
        if _debug:
            traceback.print_exc()
        if output == OutputFormat.JSON and _contract_version == "2.0.0":
            # Contract v2 always emits exactly one JSON envelope on stdout, even for
            # operational failures (config/approval loading, prompt rendering, gate
            # validation) that would otherwise bypass JSON entirely.
            # `type(exc).__name__` is a deterministic, stable code for a given
            # exception type; `retryable` is conservatively False since these are
            # input/environment errors (bad config, bad approval file, bad
            # parameter), not transient ones.
            _write_stdout(
                _contract_v2_error(
                    command,
                    code=type(exc).__name__,
                    message=str(exc),
                    retryable=False,
                )
            )
            raise typer.Exit(code=1) from exc
        # Contract v1 (and human output) keep the exact pre-existing behavior: Rich's
        # Console.print (even with markup/highlight disabled) still soft-wraps text to
        # the console width, corrupting the exact-bytes stderr contract, so write
        # directly to stderr instead.
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.stderr.flush()
        raise typer.Exit(code=2) from exc


def _config(
    path: Path, *, output: OutputFormat = OutputFormat.HUMAN, command: str = "config"
) -> EngineConfig:
    return _protected(lambda: load_config(path), output=output, command=command)


@app.command()
def version() -> None:
    """Print the engine version."""
    _write_stdout(__version__)


@app.command()
def inspect(
    config: ConfigOption,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Inspect repository, workflow summary, and protected paths."""
    settings, state, workflow = _protected(
        lambda: (
            (loaded := load_config(config)),
            GitClient(loaded.project.repository).status(),
            summarize_workflow(loaded),
        ),
        output=output,
        command="inspect",
    )
    protected = sorted(
        set(
            matching_paths(state.staged_files, settings.protected_paths.never_stage)
            + matching_paths(state.staged_files, settings.protected_paths.never_commit)
        )
    )
    payload = {
        "schema_version": "1.0",
        "project_id": settings.project.id,
        "repository": str(settings.project.repository),
        "git": state.model_dump(mode="json"),
        "workflow": workflow.model_dump(mode="json"),
        "protected_path_violations": protected,
    }
    if output == OutputFormat.JSON:
        if _contract_version == "2.0.0":
            _write_stdout(_contract_v2_success("inspect", payload))
            return
        import json

        _write_stdout(json.dumps(payload, sort_keys=True, indent=2))
        return
    console.print(f"Project: {settings.project.id}")
    console.print(f"Repository: {settings.project.repository}")
    console.print(f"Branch: {state.branch}")
    console.print(f"HEAD: {state.head}")
    console.print(f"Upstream: {state.upstream or '(none)'}")
    if state.upstream:
        console.print(f"Ahead/behind: {state.ahead}/{state.behind}")
    console.print(f"Modified: {', '.join(state.modified_files) or '(none)'}")
    console.print(f"Staged: {', '.join(state.staged_files) or '(none)'}")
    console.print(f"Untracked: {', '.join(state.untracked_files) or '(none)'}")
    console.print(f"Current tasks: {', '.join(workflow.current_tasks) or '(none)'}")
    console.print(
        f"Done tasks: {len(workflow.done_tasks)}; Planned tasks: {len(workflow.planned_tasks)}"
    )
    console.print(f"Protected violations: {', '.join(protected) or '(none)'}")


@app.command("check-git")
def check_git_command(
    config: ConfigOption,
    expected_branch: Annotated[str | None, typer.Option("--expected-branch")] = None,
    expected_head: Annotated[str | None, typer.Option("--expected-head")] = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    settings = _config(config, output=output, command="git")
    _emit(
        _safe_check(
            "git",
            lambda: check_git(
                settings, expected_branch=expected_branch, expected_head=expected_head
            ),
        ),
        output,
    )


@app.command("check-task-state")
def check_task_state_command(
    config: ConfigOption, output: OutputOption = OutputFormat.HUMAN
) -> None:
    settings = _config(config, output=output, command="task-state")
    _emit(_safe_check("task-state", lambda: check_task_state(settings)), output)


@app.command("check-governance")
def check_governance_command(
    config: ConfigOption, output: OutputOption = OutputFormat.HUMAN
) -> None:
    settings = _config(config, output=output, command="governance")
    _emit(_safe_check("governance", lambda: check_governance(settings)), output)


@app.command("check-registries")
def check_registries_command(
    config: ConfigOption, output: OutputOption = OutputFormat.HUMAN
) -> None:
    settings = _config(config, output=output, command="registries")
    _emit(_safe_check("registries", lambda: check_registries(settings)), output)


@app.command("check-handover")
def check_handover_command(
    config: ConfigOption,
    source: Annotated[HandoverSource, typer.Option("--source")] = HandoverSource.WORKING_TREE,
    commit: Annotated[str, typer.Option("--commit")] = "HEAD",
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    settings = _config(config, output=output, command="handover")
    _emit(
        _safe_check("handover", lambda: check_handover(settings, source=source, commit=commit)),
        output,
    )


@app.command()
def verify(config: ConfigOption, output: OutputOption = OutputFormat.HUMAN) -> None:
    """Run all deterministic governance checks."""
    settings = _config(config, output=output, command="verify")
    checks = [
        _safe_check("git", lambda: check_git(settings)),
        _safe_check("task-state", lambda: check_task_state(settings)),
        _safe_check("governance", lambda: check_governance(settings)),
        _safe_check("registries", lambda: check_registries(settings)),
        _safe_check("handover", lambda: check_handover(settings)),
    ]
    report = VerificationReport(
        project_id=settings.project.id, status=combined_status(checks), checks=checks
    )
    if output == OutputFormat.JSON:
        findings = [finding for check in checks for finding in check.findings]
        _write_stdout(
            render_contract_json(
                command="verify",
                contract_version=_contract_version,
                model=report,
                status=report.status,
                summary=f"{report.status.value}: {len(checks)} check(s) evaluated",
                findings=findings,
            )
        )
    else:
        print_report(report, console)
    if report.status != Status.PASS:
        raise typer.Exit(code=1)


prompt_app = typer.Typer(
    help="Deterministically render, validate, and optionally store one governed workflow prompt."
)
app.add_typer(prompt_app, name="prompt")

PROMPT_CHECK_NAME = "prompt"

TaskIdOption = Annotated[str, typer.Option("--task-id")]
StoreOption = Annotated[bool, typer.Option("--store/--no-store")]
AllowedPathOption = Annotated[list[str], typer.Option("--allowed-path")]
FindingOption = Annotated[list[str], typer.Option("--finding")]


def _emit_prompt_success(
    rendered: RenderedPrompt,
    *,
    stored: bool,
    prompt_artifact: str | None,
    metadata_artifact: str | None,
    output: OutputFormat,
) -> None:
    success = PromptSuccess(
        schema_version="1.1",
        stored=stored,
        prompt_artifact=prompt_artifact,
        metadata_artifact=metadata_artifact,
        prompt=rendered.markdown,
        metadata=rendered.metadata,
    )
    if output == OutputFormat.JSON:
        if _contract_version == "2.0.0":
            _write_stdout(
                _contract_v2_success(rendered.context.stage, success.model_dump(mode="json"))
            )
            return
        sys.stdout.buffer.write(canonical_json(success.model_dump(mode="json")) + b"\n")
        sys.stdout.buffer.flush()
        return
    label_block = "\n".join(
        [
            f"Prompt ID: {rendered.prompt_id}",
            f"Stage: {rendered.context.stage}",
            f"Stored: {'yes' if stored else 'no'}",
            f"Prompt artifact: "
            f"{prompt_artifact if prompt_artifact is not None else '(not stored)'}",
            f"Metadata artifact: "
            f"{metadata_artifact if metadata_artifact is not None else '(not stored)'}",
        ]
    )
    sys.stdout.write(label_block + "\n\n" + rendered.markdown)
    sys.stdout.flush()


def _run_prompt_command(
    stage: WorkflowStage,
    *,
    config: Path,
    task_id: str,
    output: OutputFormat,
    store: bool,
    allowed_paths: list[str],
    remediation_findings: list[str],
) -> None:
    context = _protected(
        lambda: build_prompt_context(
            load_config(config),
            stage=stage,
            task_id=task_id,
            allowed_paths=allowed_paths,
            remediation_findings=remediation_findings,
        ),
        output=output,
        command=stage,
    )
    rendered = _protected(lambda: render_prompt(context), output=output, command=stage)

    check_result = _safe_check(PROMPT_CHECK_NAME, lambda: validate_prompt(rendered))
    if check_result.status != Status.PASS:
        _emit(check_result, output)
        return

    stored = False
    prompt_artifact: str | None = None
    metadata_artifact: str | None = None
    if store:
        paths = _protected(lambda: save(rendered), output=output, command=stage)
        stored = True
        prompt_artifact = paths.markdown.as_posix()
        metadata_artifact = paths.metadata.as_posix()

    _emit_prompt_success(
        rendered,
        stored=stored,
        prompt_artifact=prompt_artifact,
        metadata_artifact=metadata_artifact,
        output=output,
    )


@prompt_app.command("plan-review")
def prompt_plan_review(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "plan-review",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=[],
        remediation_findings=[],
    )


@prompt_app.command("implementation")
def prompt_implementation(
    config: ConfigOption,
    task_id: TaskIdOption,
    allowed_path: AllowedPathOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "implementation",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=allowed_path,
        remediation_findings=[],
    )


@prompt_app.command("implementation-review")
def prompt_implementation_review(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "implementation-review",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=[],
        remediation_findings=[],
    )


@prompt_app.command("remediation")
def prompt_remediation(
    config: ConfigOption,
    task_id: TaskIdOption,
    allowed_path: AllowedPathOption,
    finding: FindingOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "remediation",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=allowed_path,
        remediation_findings=finding,
    )


@prompt_app.command("governance-closeout")
def prompt_governance_closeout(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "governance-closeout",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=[],
        remediation_findings=[],
    )


@prompt_app.command("governance-review")
def prompt_governance_review(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "governance-review",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=[],
        remediation_findings=[],
    )


@prompt_app.command("push")
def prompt_push(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
    store: StoreOption = True,
) -> None:
    _run_prompt_command(
        "push",
        config=config,
        task_id=task_id,
        output=output,
        store=store,
        allowed_paths=[],
        remediation_findings=[],
    )


state_app = typer.Typer(
    help="Inspect and advance the persisted, event-sourced per-task workflow state."
)
app.add_typer(state_app, name="state")


def _event_payload(event: WorkflowEvent) -> dict[str, object]:
    return event.model_dump(mode="json")


def _check_agent_run_evidence(
    settings: EngineConfig,
    *,
    task_id: str,
    stage: WorkflowStage,
    verdict: str | None,
    run_id: str,
) -> dict[str, object] | None:
    """Return a FAIL payload if a cited agent-run artifact does not back this event, else None."""
    from ai_workflow_engine.agents.artifacts import ArtifactError, load_run
    from ai_workflow_engine.prompt.context import normalize_text

    normalized_task = normalize_text(task_id)
    try:
        record = load_run(settings.project.id, normalized_task, stage, run_id)
    except ArtifactError as exc:
        return _agent_evidence_fail("agent_run_unavailable", str(exc))
    if record.task_id != normalized_task or record.stage != stage:
        return _agent_evidence_fail(
            "agent_run_target_mismatch",
            f"agent run {run_id} is for {record.task_id}/{record.stage}, "
            f"not {normalized_task}/{stage}",
        )
    if record.verification.status != "PASS":
        return _agent_evidence_fail(
            "agent_run_not_verified", f"agent run {run_id} did not pass verification"
        )
    if verdict is not None and record.verification.evidence.get("verdict") != verdict:
        return _agent_evidence_fail(
            "verdict_evidence_mismatch",
            f"recorded verdict {verdict} differs from agent run {run_id}'s verdict",
        )
    return None


def _agent_evidence_fail(code: str, message: str) -> dict[str, object]:
    return {"status": "FAIL", "command": "record", "finding": {"code": code, "message": message}}


def _contract_v2_for_status_payload(payload: dict[str, object]) -> str:
    """Wrap a legacy ``{status, command, ...}`` dict payload (state show/next/record)
    in the v2 envelope: ``status == "PASS"`` becomes ``ok=true`` with the rest of the
    payload as ``data``; anything else becomes ``ok=false`` with the payload's
    ``finding`` (``{code, message}``) driving the stable error.
    """
    command = str(payload.get("command", "state"))
    if payload["status"] == "PASS":
        data = {key: value for key, value in payload.items() if key != "status"}
        return _contract_v2_success(command, data)
    finding = payload.get("finding")
    if isinstance(finding, dict):
        code = str(finding.get("code", "STATE_COMMAND_FAILED"))
        message = str(finding.get("message", ""))
        details: dict[str, object] = {"finding": finding}
    else:
        code, message, details = "STATE_COMMAND_FAILED", str(payload["status"]), {}
    return _contract_v2_error(command, code=code, message=message, details=details)


def _emit_state(payload: dict[str, object], output: OutputFormat, human_lines: list[str]) -> None:
    if output == OutputFormat.JSON:
        if _contract_version == "2.0.0":
            _write_stdout(_contract_v2_for_status_payload(payload))
        else:
            sys.stdout.buffer.write(canonical_json(payload) + b"\n")
            sys.stdout.buffer.flush()
    else:
        _write_stdout("\n".join(human_lines))
    if payload["status"] != "PASS":
        raise typer.Exit(code=1)


def _stage_label(stage: object) -> str:
    return stage if isinstance(stage, str) else "(terminal)"


@state_app.command("show")
def state_show(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Show the full replayed event history and derived state for a task."""

    def build() -> dict[str, object]:
        settings = load_config(config)
        try:
            state = derive_state(settings.project.id, task_id)
        except WorkflowStateError as exc:
            return {
                "status": "FAIL",
                "command": "show",
                "finding": {"code": exc.code, "message": str(exc)},
            }
        return {
            "status": "PASS",
            "command": "show",
            "project_id": state.project_id,
            "task_id": state.task_id,
            "events": [_event_payload(event) for event in state.events],
            "next_stage": state.next_stage,
            "terminal": state.terminal,
        }

    payload = _protected(build, output=output, command="show")
    if payload["status"] != "PASS":
        finding = payload["finding"]
        assert isinstance(finding, dict)
        _emit_state(
            payload,
            output,
            [f"FAIL state: {finding['message']}", f"  - {finding['code']}: {finding['message']}"],
        )
        return
    events = payload["events"]
    assert isinstance(events, list)
    lines = [f"Task: {payload['task_id']}", f"Events: {len(events)}"]
    for event in events:
        assert isinstance(event, dict)
        outcome = event["verdict"] if event["action"] == "verdict" else "completed"
        lines.append(f"  {event['sequence']:>3}. {event['stage']} — {outcome}")
    lines.append(f"Next stage: {_stage_label(payload['next_stage'])}")
    _emit_state(payload, output, lines)


@state_app.command("next")
def state_next(
    config: ConfigOption,
    task_id: TaskIdOption,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Print the stage that may be recorded next for a task (or terminal)."""

    def build() -> dict[str, object]:
        settings = load_config(config)
        try:
            state = derive_state(settings.project.id, task_id)
        except WorkflowStateError as exc:
            return {
                "status": "FAIL",
                "command": "next",
                "finding": {"code": exc.code, "message": str(exc)},
            }
        return {"status": "PASS", "command": "next", "next_stage": state.next_stage}

    payload = _protected(build, output=output, command="next")
    if payload["status"] != "PASS":
        finding = payload["finding"]
        assert isinstance(finding, dict)
        _emit_state(
            payload,
            output,
            [f"FAIL state: {finding['message']}", f"  - {finding['code']}: {finding['message']}"],
        )
        return
    _emit_state(payload, output, [_stage_label(payload["next_stage"])])


@state_app.command("record")
def state_record(
    config: ConfigOption,
    task_id: TaskIdOption,
    stage: Annotated[str, typer.Option("--stage")],
    verdict: Annotated[str | None, typer.Option("--verdict")] = None,
    completed: Annotated[bool, typer.Option("--completed")] = False,
    prompt_id: Annotated[str | None, typer.Option("--prompt-id")] = None,
    agent_run: Annotated[str | None, typer.Option("--agent-run")] = None,
    note: Annotated[str, typer.Option("--note")] = "",
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Record one stage outcome, enforcing the transition table and verdict rules."""

    def build() -> dict[str, object]:
        settings = load_config(config)
        if not is_workflow_stage(stage):
            raise typer.BadParameter(f"Unknown stage: {stage!r}", param_hint="--stage")
        if (verdict is not None) == completed:
            raise typer.BadParameter(
                "Provide exactly one of --verdict or --completed",
                param_hint="--verdict/--completed",
            )
        if verdict is not None and verdict not in ("APPROVED", "REJECTED"):
            raise typer.BadParameter(
                "--verdict must be APPROVED or REJECTED", param_hint="--verdict"
            )
        if agent_run is not None:
            binding = _check_agent_run_evidence(
                settings, task_id=task_id, stage=stage, verdict=verdict, run_id=agent_run
            )
            if binding is not None:
                return binding
        try:
            event = record_outcome(
                settings,
                task_id,
                stage=stage,
                verdict=cast("Verdict | None", verdict),
                prompt_id=prompt_id,
                agent_run_id=agent_run,
                note=note,
            )
        except WorkflowStateError as exc:
            return {
                "status": "FAIL",
                "command": "record",
                "finding": {"code": exc.code, "message": str(exc)},
            }
        next_state = derive_state(settings.project.id, task_id)
        return {
            "status": "PASS",
            "command": "record",
            "event": _event_payload(event),
            "next_stage": next_state.next_stage,
        }

    payload = _protected(build, output=output, command="record")
    if payload["status"] != "PASS":
        finding = payload["finding"]
        assert isinstance(finding, dict)
        _emit_state(
            payload,
            output,
            [f"FAIL state: {finding['message']}", f"  - {finding['code']}: {finding['message']}"],
        )
        return
    event = payload["event"]
    assert isinstance(event, dict)
    outcome = event["verdict"] if event["action"] == "verdict" else "completed"
    summary_line = (
        f"Recorded event {event['sequence']}: {event['stage']} — {outcome} "
        f"(task {event['task_id']})"
    )
    lines = [summary_line, f"Next stage: {_stage_label(payload['next_stage'])}"]
    _emit_state(payload, output, lines)


def _contract_v2_for_agent_run_payload(payload: dict[str, object], *, status: object) -> str:
    """Wrap `agent run`'s legacy payload in the v2 envelope.

    A successful run (``status == "PASS"``) carries a ``verification``
    ``CheckResult`` dict alongside run identity/artifacts; a pre-verification
    failure (``RunnerError``) instead carries a plain ``finding``. Both are mapped
    to the same stable error shape when not PASS.
    """
    if status == "PASS":
        data = {
            "run_id": payload.get("run_id"),
            "stage": payload.get("stage"),
            "verification": payload.get("verification"),
            "record_artifact": payload.get("record_artifact"),
            "patch_artifact": payload.get("patch_artifact"),
        }
        return _contract_v2_success("agent-run", data)
    finding = payload.get("finding")
    verification = payload.get("verification")
    details: dict[str, object]
    if isinstance(finding, dict):
        code = str(finding.get("code", "AGENT_RUN_FAILED"))
        message = str(finding.get("message", ""))
        details = {"finding": finding}
    elif isinstance(verification, dict):
        findings = verification.get("findings") or []
        code = str(findings[0]["code"]) if findings else f"AGENT_RUN_{status}"
        message = str(verification.get("summary", ""))
        details = {"findings": findings}
    else:
        code, message, details = f"AGENT_RUN_{status}", "", {}
    return _contract_v2_error(
        "agent-run",
        code=code,
        message=message,
        retryable=(status == "ERROR"),
        details=details,
    )


agent_app = typer.Typer(help="Run a configured non-interactive agent against a governed prompt.")
app.add_typer(agent_app, name="agent")


@agent_app.command("run")
def agent_run(
    config: ConfigOption,
    agent_name: Annotated[str, typer.Option("--agent")],
    task_id: TaskIdOption,
    stage: Annotated[str, typer.Option("--stage")],
    prompt_id: Annotated[str, typer.Option("--prompt-id")],
    store: StoreOption = True,
    keep_sandbox: Annotated[bool, typer.Option("--keep-sandbox/--no-keep-sandbox")] = False,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Execute one agent in a sandbox, verify its claims, and store the run artifact."""

    def build() -> dict[str, object]:
        settings = load_config(config)
        if not is_workflow_stage(stage):
            raise typer.BadParameter(f"Unknown stage: {stage!r}", param_hint="--stage")
        agent = next((a for a in settings.agents if a.name == agent_name), None)
        if agent is None:
            raise typer.BadParameter(
                f"No configured agent named {agent_name!r}", param_hint="--agent"
            )
        rendered = load(settings.project.id, stage, prompt_id)
        try:
            observation = run_agent(
                settings,
                agent,
                task_id=task_id,
                stage=stage,
                prompt_id=prompt_id,
                keep_sandbox=keep_sandbox,
            )
        except RunnerError as exc:
            return {
                "status": "FAIL",
                "command": "agent-run",
                "finding": {"code": exc.code, "message": str(exc)},
            }
        verification = verify_run(settings, rendered, observation)
        stored_record: str | None = None
        stored_patch: str | None = None
        run_id: str | None = None
        if store:
            record, patch = build_record(observation, verification, project_id=settings.project.id)
            record_path, patch_path = save_run(
                record, patch, repository=str(settings.project.repository)
            )
            stored_record = record_path.as_posix()
            stored_patch = patch_path.as_posix()
            run_id = record.run_id
        return {
            "status": verification.status.value,
            "command": "agent-run",
            "run_id": run_id,
            "stage": stage,
            "verification": verification.model_dump(mode="json"),
            "record_artifact": stored_record,
            "patch_artifact": stored_patch,
        }

    payload = _protected(build, output=output, command="agent-run")
    status = payload["status"]
    if output == OutputFormat.JSON:
        if _contract_version == "2.0.0":
            _write_stdout(_contract_v2_for_agent_run_payload(payload, status=status))
        else:
            sys.stdout.buffer.write(canonical_json(payload) + b"\n")
            sys.stdout.buffer.flush()
    else:
        verification = payload.get("verification")
        summary = verification["summary"] if isinstance(verification, dict) else payload["finding"]
        _write_stdout(
            "\n".join(
                [
                    f"Status: {status}",
                    f"Run ID: {payload.get('run_id') or '(not stored)'}",
                    f"Stage: {payload.get('stage')}",
                    f"Record artifact: {payload.get('record_artifact') or '(not stored)'}",
                    f"Summary: {summary}",
                ]
            )
        )
    if status != "PASS":
        raise typer.Exit(code=1)


@app.command()
def commit(
    config: ConfigOption,
    approval: Annotated[Path, typer.Option("--approval", dir_okay=False)],
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Stage exactly the human-approved paths and create the approved commit, or refuse."""
    settings = _config(config, output=output, command="commit")
    loaded_approval = _protected(
        lambda: load_commit_approval(approval), output=output, command="commit"
    )
    result = _safe_check("commit", lambda: run_commit_gate(settings, loaded_approval, approval))
    _emit(result, output)


@app.command()
def push(
    config: ConfigOption,
    approval: Annotated[Path, typer.Option("--approval", dir_okay=False)],
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Verify the push preconditions against live Git and push once, or refuse."""
    settings = _config(config, output=output, command="push")
    loaded_approval = _protected(
        lambda: load_push_approval(approval), output=output, command="push"
    )
    result = _safe_check("push", lambda: run_push_gate(settings, loaded_approval, approval))
    _emit(result, output)


@app.command("apply-patch")
def apply_patch(
    config: ConfigOption,
    task_id: TaskIdOption,
    stage: Annotated[str, typer.Option("--stage")],
    run_id: Annotated[str, typer.Option("--run-id")],
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Apply a verified Milestone 3 patch to the working tree, gated, or refuse."""
    settings = _config(config, output=output, command="apply-patch")

    def gate() -> WorkflowStage:
        if not is_workflow_stage(stage):
            raise typer.BadParameter(f"Unknown stage: {stage!r}", param_hint="--stage")
        return stage

    # The gate returns the narrowed stage so the verified value itself flows into the
    # patch gate; nothing downstream has to re-assert the type it already proved.
    checked_stage = _protected(gate, output=output, command="apply-patch")
    result = _safe_check(
        "apply-patch",
        lambda: run_apply_patch_gate(settings, task_id=task_id, stage=checked_stage, run_id=run_id),
    )
    _emit(result, output)


migrate_app = typer.Typer(
    help="Read-only legacy-artifact inspection and dry-run migration planning "
    "(architecture-v3.md section 14/18). Real (non-dry-run) apply is not authorized."
)
app.add_typer(migrate_app, name="migrate")

SourceOption = Annotated[
    Path | None,
    typer.Option(
        "--source",
        help="Legacy-artifact source root (default: ~/.ai-workflow-engine/workflow-runs).",
        # Click's Path type checks `readable` (and would check `exists`) at argument-
        # parsing time by default, before any command body runs -- bypassing the JSON
        # contract entirely for a missing/permission-denied path (the same class of gap
        # ORCH-002's Finding B fixed for _protected-caught exceptions). All existence,
        # type, and readability handling for --source is deferred to
        # `migration.legacy_readers.discover_legacy_artifacts`/`apply_migration`, which
        # always emit through the stable v1/v2 contract.
        exists=False,
        readable=False,
    ),
]
ToVersionOption = Annotated[
    str, typer.Option("--to", help="Target migration version, e.g. '2.0.0'.")
]


def _resolve_migration_source(source: Path | None) -> Path:
    return source if source is not None else default_migration_source()


def _emit_migration_payload(command: str, payload: dict[str, object], output: OutputFormat) -> None:
    if output == OutputFormat.JSON:
        if _contract_version == "2.0.0":
            _write_stdout(_contract_v2_success(command, payload))
        else:
            sys.stdout.buffer.write(canonical_json(payload) + b"\n")
            sys.stdout.buffer.flush()
        return
    _write_stdout(json.dumps(payload, sort_keys=True, indent=2, default=str))


@migrate_app.command("inspect")
def migrate_inspect(
    to: ToVersionOption,
    source: SourceOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Classify every legacy artifact under --source. Read-only; writes nothing."""
    resolved_source = _resolve_migration_source(source)
    manifest = _protected(
        lambda: inspect_source(resolved_source, to_version=to),
        output=output,
        command="migrate-inspect",
    )
    _emit_migration_payload("migrate-inspect", manifest.model_dump(mode="json"), output)


@migrate_app.command("plan")
def migrate_plan(
    to: ToVersionOption,
    source: SourceOption = None,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Build a deterministic backup/recovery plan from a fresh inspection. Writes nothing."""
    resolved_source = _resolve_migration_source(source)

    def build() -> dict[str, object]:
        manifest = inspect_source(resolved_source, to_version=to)
        backup_plan = build_backup_plan(manifest)
        recovery_plan = build_recovery_plan(manifest, backup_plan)
        return {
            "manifest_digest": manifest.manifest_digest,
            "source_root": manifest.source_root,
            "to_version": manifest.to_version,
            "known_count": manifest.known_count,
            "quarantined_count": manifest.quarantined_count,
            "backup_plan": backup_plan.model_dump(mode="json"),
            "recovery_plan": recovery_plan.model_dump(mode="json"),
        }

    payload = _protected(build, output=output, command="migrate-plan")
    _emit_migration_payload("migrate-plan", payload, output)


@migrate_app.command("apply")
def migrate_apply_command(
    to: ToVersionOption,
    source: SourceOption = None,
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = False,
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Dry-run only: refuses before any write unless --dry-run is passed."""
    resolved_source = _resolve_migration_source(source)

    def build() -> dict[str, object]:
        # F-7: without --dry-run, refuse before inspecting or reading the source tree at
        # all. `apply_migration` itself also refuses first, but only after `inspect_source`
        # has already been called below it in the old ordering -- checking `dry_run` here,
        # before any inspection, means a real-apply refusal never accesses the source root.
        if not dry_run:
            raise ApplyNotAuthorizedError(
                "Real (non-dry-run) migration apply is not authorized in ORCH-003; pass "
                "--dry-run. Refused before reading the source tree."
            )
        manifest = inspect_source(resolved_source, to_version=to)
        backup_plan = build_backup_plan(manifest)
        recovery_plan = build_recovery_plan(manifest, backup_plan)
        result = apply_migration(manifest, backup_plan, recovery_plan, dry_run=dry_run)
        return result.model_dump(mode="json")

    payload = _protected(build, output=output, command="migrate-apply")
    _emit_migration_payload("migrate-apply", payload, output)


# AUTO-015: the additive, read-only `workflowctl successor-planning` sub-application, namespaced
# away from the `check-*` gates exactly as `prompt_app` already is. It is a thin adapter and
# nothing else: it validates command-line syntax, hands the four fixed inputs to
# `successor_planning.proposal.propose_successor`, and renders the typed result it gets back.
# No eligibility, repository, catalog, prompt, publication or authorization logic lives here, and
# no existing command changes.

successor_planning_app = typer.Typer(
    help=(
        "Read-only successor-stage planning: propose a next stage from this repository's own "
        "governance evidence. Selects, registers and authorizes nothing."
    )
)
app.add_typer(successor_planning_app, name="successor-planning")


class SuccessorPlanningOutput(StrEnum):
    """DEC-011 fixes this command's rendering choice as `console|json`, not the `human|json`
    every other command uses. The vocabularies are deliberately not merged: `OutputFormat` is
    the existing gates' contract and widening it would change commands this stage may not
    touch."""

    CONSOLE = "console"
    JSON = "json"


#: `--predecessor` is optional at the parser level and required by the contract. Typer would
#: reject an omitted required option with its own usage error, which would replace section 13's
#: `MISSING_PREDECESSOR` with an exit code that says nothing about the governance contract. The
#: classification therefore stays where section 4.1 puts it: in the planning service.
PredecessorOption = Annotated[str | None, typer.Option("--predecessor")]
SuccessorPlanningOutputOption = Annotated[SuccessorPlanningOutput, typer.Option("--output")]
DryRunOption = Annotated[bool, typer.Option("--dry-run")]


def _print_successor_planning(run: ProposalRun) -> None:
    """Render one `ProposalRun` for a human reader. Presentation only; nothing is computed."""
    artifact = run.artifact
    recommendation = run.recommendation
    lines = [f"Outcome: {run.outcome_class}"]
    if artifact is not None and artifact.outcome.outcome_class == "PROPOSAL_READY":
        lines.append(f"Result variant: {artifact.outcome.result_variant}")
    if run.failure_code is not None:
        lines.append(f"Failure code: {run.failure_code}")
    lines.append(f"Predecessor: {run.predecessor_stage_id or '(none)'}")
    if artifact is not None:
        lines += [
            f"Proposal ID: {artifact.proposal_id}",
            f"Authorization status: {artifact.authorization_status}",
            f"Candidates evaluated: {len(artifact.candidate_list)}",
            f"Warnings: {len(artifact.warnings)}",
        ]
    lines.append(
        "Recommendation: "
        + (
            f"{recommendation.candidate_id} — {recommendation.title}"
            if recommendation is not None
            else "(none)"
        )
    )
    lines.append(f"Dry run: {'yes' if run.dry_run else 'no'}")
    lines.append(
        f"Artifact: {run.publication.artifact_path} "
        f"({'written' if run.publication.created else 'already published'})"
        if run.publication is not None
        else "Artifact: (not published)"
    )
    lines += [
        f"Error [{error.code}] {error.path_or_candidate_id}: {error.message}"
        for error in run.errors
    ]
    # Written directly rather than through Rich for the same reason `_emit_prompt_success`'s
    # human block is: Rich soft-wraps to the console width and highlights numbers and paths,
    # which would silently corrupt a digest, an artifact path or a failure code.
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


@successor_planning_app.command("propose")
def successor_planning_propose(
    config: ConfigOption,
    predecessor: PredecessorOption = None,
    output: SuccessorPlanningOutputOption = SuccessorPlanningOutput.CONSOLE,
    dry_run: DryRunOption = False,
) -> None:
    """Propose a successor stage for --predecessor. Read-only; authorizes nothing.

    `--dry-run` performs the complete inspection, reconciliation, eligibility evaluation, prompt
    rendering and validation, and publishes nothing.
    """
    json_output = output == SuccessorPlanningOutput.JSON
    run = _protected(
        lambda: propose_successor(
            config, predecessor=predecessor, output=output.value, dry_run=dry_run
        ),
        output=OutputFormat.JSON if json_output else OutputFormat.HUMAN,
        command="successor-planning-propose",
    )
    if json_output:
        sys.stdout.buffer.write(canonical_json(run.model_dump(mode="json")) + b"\n")
        sys.stdout.buffer.flush()
    else:
        _print_successor_planning(run)
    if run.outcome_class != "PROPOSAL_READY":
        raise typer.Exit(code=1)


# AUTO-016: the additive `workflowctl milestone-runner` sub-application, registered exactly as
# `successor-planning` already is. Section 7 is binding here: business logic never lives in a CLI
# handler. Each of the thirteen functions below parses its options, calls exactly one
# `MilestoneRunnerApplication` method, renders the typed result it gets back and selects an exit
# code -- nothing decides anything. Every gate, every transition, every scope check and the whole
# of section 20's Git authority live in the application and in `milestone_runner/approval_git.py`.
# No existing command is moved, renamed or changed.

milestone_runner_app = typer.Typer(
    help=(
        "Drive an already-authorized stage as a bounded, resumable sequence of typed milestones. "
        "Authorizes nothing, registers nothing, and stops at a human commit gate that is "
        "disabled by default."
    )
)
app.add_typer(milestone_runner_app, name="milestone-runner")

#: Section 9's conventions: long-form `--kebab-case` options only, no short flags, module-level
#: `Annotated` aliases. `--config` names a validated runner configuration file, which is a
#: different document from `self-governance.yaml`.
MilestoneRunnerConfigOption = Annotated[Path, typer.Option("--config", dir_okay=False)]
MilestoneOption = Annotated[str, typer.Option("--milestone")]
ReasonOption = Annotated[str, typer.Option("--reason")]
ClassificationOption = Annotated[str, typer.Option("--classification")]
RulingOption = Annotated[str, typer.Option("--ruling")]
MilestoneRunnerJsonOption = Annotated[bool, typer.Option("--json")]


def _milestone_runner_application(config: Path) -> MilestoneRunnerApplication:
    """Load the validated runner configuration and bind an application to it.

    An unreadable or invalid configuration is an operational error, so it exits `2` through
    `_protected` rather than being reported as a domain failure -- section 4 item 8's rule that a
    missing configuration is a precondition failure, never an assumed default.
    """
    return _protected(
        lambda: MilestoneRunnerApplication.from_config_path(config),
        command="milestone-runner",
    )


def _milestone_runner_protected(operation: Callable[[], T], *, command: str) -> T:
    """Run one application method under section 9's exit-code contract.

    The split is by exception type, and it is the contract's own. A `WorkflowEngineError` is one of
    the package's typed refusals -- a tripped gate, a refused transition, a refused recovery, an
    approval that no longer binds -- and that is a **domain** failure, so it exits `1`. Anything
    else is unexpected, which is an **operational** error and exits `2` with the same exact-bytes
    stderr shape `_protected` uses. `--debug` prints the traceback for either.
    """
    try:
        return operation()
    except WorkflowEngineError as exc:
        if _debug:
            traceback.print_exc()
        sys.stderr.write(f"ERROR [{command}]: {exc}\n")
        sys.stderr.flush()
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        if _debug:
            traceback.print_exc()
        sys.stderr.write(f"ERROR [{command}]: {exc}\n")
        sys.stderr.flush()
        raise typer.Exit(code=2) from exc


def _print_milestone_runner(lines: Sequence[str]) -> None:
    """Render one typed report for a human reader. Presentation only; nothing is computed.

    Written directly rather than through Rich for the same reason `_print_successor_planning` is:
    Rich soft-wraps to the console width and highlights numbers and paths, which would silently
    corrupt a digest, an object id or a stop reason.
    """
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _milestone_runner_exit(satisfied: bool) -> None:
    """Section 9's exit-code contract: `0` success, `1` domain failure or tripped gate.

    `2` is `_protected`'s, and belongs to an operational error -- an unreadable configuration, an
    unusable repository, a refused lock -- which never reaches this function.
    """
    if not satisfied:
        raise typer.Exit(code=1)


def _preflight_lines(report: PreflightReport) -> list[str]:
    lines = [f"Entry conditions: {'satisfied' if report.satisfied else 'NOT satisfied'}"]
    for condition in report.conditions:
        if not condition.evaluated:
            mark = "SKIP"
        elif condition.satisfied:
            mark = "PASS"
        else:
            mark = "FAIL"
        lines.append(f"  [{mark}] {condition.number}. {condition.name}: {condition.detail}")
    return lines


def _plan_lines(report: PlanReport) -> list[str]:
    lines = [f"Plan: {'valid' if report.satisfied else 'INVALID'}", f"  {report.detail}"]
    if report.plan is not None:
        lines.append(f"  Source files: {len(report.plan.source_paths)}")
        lines.append(f"  Covered paths: {len(report.plan.covered_paths())}")
        lines.append(f"  Required coverage: {len(report.required_coverage)}")
    return lines


def _status_lines(report: StatusReport) -> list[str]:
    lines = [f"Run: {report.run_id or '(none)'}", f"Status: {report.detail}"]
    record = report.record
    if record is not None:
        lines += [
            f"Branch: {record.expected_branch}",
            f"Baseline: {record.baseline_sha}",
            f"Completed milestones: {', '.join(record.completed_milestones) or '(none)'}",
            f"Current milestone: {record.current_milestone or '(none)'}",
            f"Changed paths: {len(record.changed_paths)}",
            f"Provider runs: {len(record.provider_runs)}",
            f"Verification results: {len(record.verification_results)}",
            f"Blocking findings: {len(record.blocking_findings)}",
            f"Deferred findings: {len(record.deferred_findings)}",
            f"Approvals: {len(record.approvals)}",
        ]
    return lines


def _verify_lines(report: VerifyReport) -> list[str]:
    lines = _preflight_lines(report.preflight)
    lines.append(f"Verification set: {len(report.results)} command(s)")
    for result in report.results:
        lines.append(
            f"  [{'PASS' if result.passed else 'FAIL'}] {' '.join(result.command)} "
            f"(exit {result.exit_code}, {result.duration_ms}ms)"
        )
    return lines


def _run_lines(report: RunReport) -> list[str]:
    return [
        f"Run: {report.run_id}",
        f"State: {report.state.value}",
        f"Stop reason: {report.stop_reason.value if report.stop_reason else '(none)'}",
        f"Completed milestones: {', '.join(report.completed_milestones) or '(none)'}",
        f"Current milestone: {report.current_milestone or '(none)'}",
        report.detail,
    ]


def _recovery_lines(report: RecoveryReport) -> list[str]:
    budgets = ", ".join(
        f"{name}{delta:+d}" for name, delta in sorted(report.budgets_touched.items())
    )
    return [
        f"Run: {report.run_id}",
        f"Recovery: {report.command.value}",
        f"State: {report.pre_state.value} -> {report.post_state.value}",
        f"Budgets touched: {budgets or '(none)'}",
        report.summary,
    ]


def _approval_lines(report: ApprovalReport) -> list[str]:
    return list(report.lines)


def _emit_milestone_runner_status(report: StatusReport, json_output: bool) -> None:
    """Render `status` as either the human block or the exact JSON document."""
    if json_output:
        _write_stdout(json.dumps(report.payload(), indent=2, sort_keys=True))
    else:
        _print_milestone_runner(_status_lines(report))


@milestone_runner_app.command("doctor")
def milestone_runner_doctor(config: MilestoneRunnerConfigOption) -> None:
    """Evaluate every section 4 entry condition. Read-only; acquires no lock and writes nothing."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(application.doctor, command="milestone-runner-doctor")
    _print_milestone_runner(_preflight_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("plan")
def milestone_runner_plan(config: MilestoneRunnerConfigOption) -> None:
    """Load, validate, dependency-order and coverage-reconcile the milestone plan. Read-only."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(application.plan, command="milestone-runner-plan")
    _print_milestone_runner(_plan_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("start")
def milestone_runner_start(config: MilestoneRunnerConfigOption) -> None:
    """Start a run: acquire the lock, publish the initial state and drive the approved flow."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(application.start, command="milestone-runner-start")
    _print_milestone_runner(_run_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("resume")
def milestone_runner_resume(config: MilestoneRunnerConfigOption) -> None:
    """Continue an interrupted run from exactly where it stopped, re-verifying every condition."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(application.resume, command="milestone-runner-resume")
    _print_milestone_runner(_run_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("status")
def milestone_runner_status(
    config: MilestoneRunnerConfigOption,
    json_output: MilestoneRunnerJsonOption = False,
) -> None:
    """Print the durable run record. Read-only; acquires no lock."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(application.status, command="milestone-runner-status")
    _emit_milestone_runner_status(report, json_output)
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("verify")
def milestone_runner_verify(config: MilestoneRunnerConfigOption) -> None:
    """Re-run the safety gates and the full verification set. Read-only; persists nothing."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(application.verify, command="milestone-runner-verify")
    _print_milestone_runner(_verify_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("reconcile-milestone")
def milestone_runner_reconcile_milestone(
    config: MilestoneRunnerConfigOption,
    milestone: MilestoneOption,
    reason: ReasonOption,
) -> None:
    """Reconcile a milestone whose result was valid but non-conforming. Budgets untouched."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        lambda: application.reconcile_milestone(milestone=milestone, reason=reason),
        command="milestone-runner-reconcile-milestone",
    )
    _print_milestone_runner(_recovery_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("reopen-milestone")
def milestone_runner_reopen_milestone(
    config: MilestoneRunnerConfigOption,
    milestone: MilestoneOption,
    reason: ReasonOption,
) -> None:
    """Reopen one milestone under an explicit Human Owner scope ruling. Budgets preserved."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        lambda: application.reopen_milestone(milestone=milestone, reason=reason),
        command="milestone-runner-reopen-milestone",
    )
    _print_milestone_runner(_recovery_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("recover-failed-review")
def milestone_runner_recover_failed_review(
    config: MilestoneRunnerConfigOption,
    classification: ClassificationOption,
    ruling: RulingOption,
) -> None:
    """Restore exactly one review budget a recorded provider failure consumed."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        lambda: application.recover_failed_review(classification=classification, ruling=ruling),
        command="milestone-runner-recover-failed-review",
    )
    _print_milestone_runner(_recovery_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("revalidate-correction")
def milestone_runner_revalidate_correction(config: MilestoneRunnerConfigOption) -> None:
    """Clear a post-correction verification failure. Budgets explicitly untouched."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        application.revalidate_correction,
        command="milestone-runner-revalidate-correction",
    )
    _print_milestone_runner(_recovery_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("approve-commit")
def milestone_runner_approve_commit(config: MilestoneRunnerConfigOption) -> None:
    """Print the exact commit commands. Executes only under the configuration flip, the typed
    confirmation `APPROVE COMMIT` and a bound, unexpired, single-use approval."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        application.approve_commit, command="milestone-runner-approve-commit"
    )
    _print_milestone_runner(_approval_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("approve-push")
def milestone_runner_approve_push(config: MilestoneRunnerConfigOption) -> None:
    """Print the exact push command. Executes only under the configuration flip, the typed
    confirmation `APPROVE PUSH` and a bound, unexpired, single-use approval."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        application.approve_push, command="milestone-runner-approve-push"
    )
    _print_milestone_runner(_approval_lines(report))
    _milestone_runner_exit(report.satisfied)


@milestone_runner_app.command("abort")
def milestone_runner_abort(
    config: MilestoneRunnerConfigOption,
    reason: ReasonOption,
) -> None:
    """Abort the run, holding the run lock like every other state-mutating command (defect P-6)."""
    application = _milestone_runner_application(config)
    report = _milestone_runner_protected(
        lambda: application.abort(reason=reason), command="milestone-runner-abort"
    )
    _print_milestone_runner(_run_lines(report))
    _milestone_runner_exit(report.satisfied)


# AUTO-009: the additive, read-only `workflowctl auto` sub-application. This is the *only* place
# the engine CLI reaches into AgentOS, and it reaches exactly one name: `auto_app`. No AgentOS
# internal module is imported anywhere else in this file, so the dependency direction stays
# `workflowctl -> agentos_workflow.cli_auto -> agentos_workflow.service -> read-only APIs`.
#
# Registered here, at the bottom, rather than beside the other `add_typer` calls: `cli_auto`
# reuses this module's own `_protected`/`_write_stdout`/`_contract_v2_success` helpers (reached at
# call time, so the import is not circular), and registering it before those exist would rely on
# definition order this file has no reason to guarantee. No existing command is moved or changed.
from agentos_workflow.cli_auto import auto_app  # noqa: E402

app.add_typer(auto_app, name="auto")


def main() -> None:
    app()
