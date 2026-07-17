"""workflowctl command-line interface."""

import sys
import traceback
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from rich.console import Console

from ai_workflow_engine import __version__
from ai_workflow_engine.config import load_config
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.validators import check_git, matching_paths
from ai_workflow_engine.governance.validators import check_governance, check_task_state
from ai_workflow_engine.handover.validators import HandoverSource, check_handover
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.models import PromptSuccess, RenderedPrompt, WorkflowStage
from ai_workflow_engine.prompt.renderer import canonical_json, render_prompt
from ai_workflow_engine.prompt.store import save
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
from ai_workflow_engine.workflow.invariants import summarize_workflow

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


def _emit(result: CheckResult, output: OutputFormat) -> None:
    if output == OutputFormat.JSON:
        console.print_json(render_json(result))
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
    console.print(__version__)


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

        console.print_json(json.dumps(payload, sort_keys=True))
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
        console.print_json(render_json(report))
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
        schema_version="1.0",
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


def main() -> None:
    app()
