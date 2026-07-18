"""workflowctl command-line interface."""

import sys
import traceback
from collections.abc import Callable
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
from ai_workflow_engine.git.approval import load_commit_approval, load_push_approval
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.validators import check_git, matching_paths
from ai_workflow_engine.governance.validators import check_governance, check_task_state
from ai_workflow_engine.handover.validators import HandoverSource, check_handover
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.models import (
    WORKFLOW_STAGES,
    PromptSuccess,
    RenderedPrompt,
    WorkflowStage,
)
from ai_workflow_engine.prompt.renderer import canonical_json, render_prompt
from ai_workflow_engine.prompt.store import load, save
from ai_workflow_engine.prompt.validator import validate_prompt
from ai_workflow_engine.reporting.console import print_check, print_report
from ai_workflow_engine.reporting.json_report import render_json
from ai_workflow_engine.result import (
    CheckResult,
    Finding,
    Status,
    VerificationReport,
    combined_status,
)
from ai_workflow_engine.workflow.event_store import derive_state, record_outcome
from ai_workflow_engine.workflow.events import Verdict, WorkflowEvent
from ai_workflow_engine.workflow.invariants import summarize_workflow
from ai_workflow_engine.workflow.transitions import WorkflowStateError

app = typer.Typer(help="Read-only deterministic governance gates for AI-assisted development.")
console = Console()
_debug = False


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"


ConfigOption = Annotated[Path, typer.Option("--config", dir_okay=False)]
OutputOption = Annotated[OutputFormat, typer.Option("--output")]
T = TypeVar("T")


@app.callback()
def callback(
    debug: Annotated[bool, typer.Option("--debug", help="Show tracebacks.")] = False,
) -> None:
    global _debug
    _debug = debug


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
        _write_stdout(render_json(result))
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


def _protected(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except Exception as exc:
        if _debug:
            traceback.print_exc()
        # Rich's Console.print (even with markup/highlight disabled) still soft-wraps
        # text to the console width, corrupting the exact-bytes stderr contract. Write
        # directly to stderr instead.
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.stderr.flush()
        raise typer.Exit(code=2) from exc


def _config(path: Path) -> EngineConfig:
    return _protected(lambda: load_config(path))


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
        )
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
    settings = _config(config)
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
    settings = _config(config)
    _emit(_safe_check("task-state", lambda: check_task_state(settings)), output)


@app.command("check-governance")
def check_governance_command(
    config: ConfigOption, output: OutputOption = OutputFormat.HUMAN
) -> None:
    settings = _config(config)
    _emit(_safe_check("governance", lambda: check_governance(settings)), output)


@app.command("check-handover")
def check_handover_command(
    config: ConfigOption,
    source: Annotated[HandoverSource, typer.Option("--source")] = HandoverSource.WORKING_TREE,
    commit: Annotated[str, typer.Option("--commit")] = "HEAD",
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    settings = _config(config)
    _emit(
        _safe_check("handover", lambda: check_handover(settings, source=source, commit=commit)),
        output,
    )


@app.command()
def verify(config: ConfigOption, output: OutputOption = OutputFormat.HUMAN) -> None:
    """Run all Milestone 1 deterministic checks."""
    settings = _config(config)
    checks = [
        _safe_check("git", lambda: check_git(settings)),
        _safe_check("task-state", lambda: check_task_state(settings)),
        _safe_check("governance", lambda: check_governance(settings)),
        _safe_check("handover", lambda: check_handover(settings)),
    ]
    report = VerificationReport(
        project_id=settings.project.id, status=combined_status(checks), checks=checks
    )
    if output == OutputFormat.JSON:
        _write_stdout(render_json(report))
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
        )
    )
    rendered = _protected(lambda: render_prompt(context))

    check_result = _safe_check(PROMPT_CHECK_NAME, lambda: validate_prompt(rendered))
    if check_result.status != Status.PASS:
        _emit(check_result, output)
        return

    stored = False
    prompt_artifact: str | None = None
    metadata_artifact: str | None = None
    if store:
        paths = _protected(lambda: save(rendered))
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
    stage: str,
    verdict: str | None,
    run_id: str,
) -> dict[str, object] | None:
    """Return a FAIL payload if a cited agent-run artifact does not back this event, else None."""
    from ai_workflow_engine.agents.artifacts import ArtifactError, load_run
    from ai_workflow_engine.prompt.context import normalize_text

    normalized_task = normalize_text(task_id)
    try:
        record = load_run(settings.project.id, normalized_task, stage, run_id)  # type: ignore[arg-type]
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


def _emit_state(payload: dict[str, object], output: OutputFormat, human_lines: list[str]) -> None:
    if output == OutputFormat.JSON:
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

    payload = _protected(build)
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

    payload = _protected(build)
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
        if stage not in WORKFLOW_STAGES:
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

    payload = _protected(build)
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
        if stage not in WORKFLOW_STAGES:
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

    payload = _protected(build)
    status = payload["status"]
    if output == OutputFormat.JSON:
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
    settings = _config(config)
    loaded_approval = _protected(lambda: load_commit_approval(approval))
    result = _safe_check("commit", lambda: run_commit_gate(settings, loaded_approval, approval))
    _emit(result, output)


@app.command()
def push(
    config: ConfigOption,
    approval: Annotated[Path, typer.Option("--approval", dir_okay=False)],
    output: OutputOption = OutputFormat.HUMAN,
) -> None:
    """Verify the push preconditions against live Git and push once, or refuse."""
    settings = _config(config)
    loaded_approval = _protected(lambda: load_push_approval(approval))
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
    settings = _config(config)

    def gate() -> object:
        if stage not in WORKFLOW_STAGES:
            raise typer.BadParameter(f"Unknown stage: {stage!r}", param_hint="--stage")
        return None

    _protected(gate)
    result = _safe_check(
        "apply-patch",
        lambda: run_apply_patch_gate(
            settings, task_id=task_id, stage=cast(WorkflowStage, stage), run_id=run_id
        ),
    )
    _emit(result, output)


def main() -> None:
    app()
