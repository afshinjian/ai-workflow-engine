"""Non-interactive agent runner (Milestone 3, task T-304).

Runs one configured agent against one stored, verified prompt inside a throwaway sandbox, with a
hard timeout, a scrubbed environment, and a before/after fingerprint of the target repository.
The runner only *observes* — it captures the agent's output, the raw change set it produced in
the sandbox, and the exit codes of re-running the prompt's verification commands. Judging those
observations (claim equality, scope/protected containment) is T-305's job. The runner never
writes the target repository. See ``docs/milestone-3-plan.md``.
"""

import json
import os
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ai_workflow_engine.agents.models import AgentReport
from ai_workflow_engine.agents.sandbox import SandboxGit, create_sandbox, teardown
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.models import GitStatus
from ai_workflow_engine.models import AgentSettings, EngineConfig
from ai_workflow_engine.prompt.context import normalize_text
from ai_workflow_engine.prompt.models import WorkflowStage
from ai_workflow_engine.prompt.store import load
from ai_workflow_engine.workflow.events import VERDICT_STAGES

_SCRUBBED_KEYS = ("PATH", "HOME", "LANG", "LC_ALL")
_VERIFICATION_TIMEOUT = 3600


class RunnerError(ValueError):
    """A pre-run gating or infrastructure failure (as opposed to an agent-output failure)."""

    code = "runner_error"


class StageNotAllowed(RunnerError):
    code = "stage_not_allowed"


class DirtyWorktree(RunnerError):
    code = "dirty_worktree"


class HeadDrift(RunnerError):
    code = "head_drift"


@dataclass
class VerificationCommandResult:
    argv: list[str]
    exit_code: int


@dataclass
class RunObservation:
    agent_name: str
    agent_mode: str
    agent_executable: str
    agent_args: list[str]
    timeout_seconds: int
    task_id: str
    stage: WorkflowStage
    prompt_id: str
    repository_head: str
    ok: bool
    failure_code: str | None
    report: AgentReport | None
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    actual_changed_paths: list[str] = field(default_factory=list)
    patch: bytes = b""
    verification_results: list[VerificationCommandResult] = field(default_factory=list)
    sandbox_path: Path | None = None


def verification_argv(conda_environment: str) -> list[list[str]]:
    """The single source of truth for the verification commands the runner re-executes.

    Returned as argv lists run with ``shell=False`` — no shell quoting is ever involved, so the
    ``conda_environment`` value passes as one exact token. A test pins that these, rendered
    through the Milestone 2 shell escaper and template grammar, reproduce the prompt template's
    ``## Verification commands`` lines byte-for-byte.
    """
    return [
        ["conda", "run", "-n", conda_environment, "git", "status", "--short", "--branch"],
        ["conda", "run", "-n", conda_environment, "git", "diff", "--check"],
        ["conda", "run", "-n", conda_environment, "pytest", "-p", "no:cacheprovider"],
    ]


def _scrubbed_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _SCRUBBED_KEYS if key in os.environ}


def _run_with_group_timeout(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    input_bytes: bytes | None = None,
) -> tuple[int | None, bytes, bytes, bool]:
    """Run a subprocess in its own session, killing the whole group on timeout.

    Returns ``(returncode, stdout, stderr, timed_out)``. A timed-out process group is
    SIGKILLed and reaped so no verification/agent grandchildren are orphaned.
    """
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=env,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(input=input_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:  # pragma: no cover - race: already exited
            pass
        stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr, timed_out


def _binding_failure(
    report: AgentReport, *, task_id: str, stage: WorkflowStage, prompt_id: str, mode: str
) -> bool:
    if report.task_id != task_id or report.stage != stage or report.prompt_id != prompt_id:
        return True
    is_verdict_stage = stage in VERDICT_STAGES
    if is_verdict_stage != (report.verdict is not None):
        return True
    if mode == "read-only" and report.changed_paths:
        return True
    return False


def _parse_report(stdout: bytes) -> tuple[AgentReport | None, str | None]:
    """Return (report, failure_code): utf-8 → JSON (no dup keys) → strict AgentReport."""
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None, "agent_stdout_not_utf8"

    def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in agent report: {key!r}")
            result[key] = value
        return result

    try:
        parsed = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError:
        return None, "agent_report_invalid"
    try:
        return AgentReport.model_validate(parsed), None
    except ValidationError:
        return None, "agent_report_invalid"


def _status_clean(status: GitStatus) -> bool:
    return not (status.modified_files or status.staged_files or status.untracked_files)


def run_agent(
    config: EngineConfig,
    agent: AgentSettings,
    *,
    task_id: str,
    stage: WorkflowStage,
    prompt_id: str,
    keep_sandbox: bool = False,
) -> RunObservation:
    """Execute one agent against one stored prompt and return the raw run observations."""
    if stage not in agent.stages:
        raise StageNotAllowed(f"agent {agent.name!r} is not configured for stage {stage!r}")

    normalized_task = normalize_text(task_id)
    rendered = load(config.project.id, stage, prompt_id)
    recorded_head = rendered.metadata.repository_head

    repository = config.project.repository
    before = GitClient(repository).status()
    if not _status_clean(before):
        raise DirtyWorktree("The target working tree must be clean before running an agent")
    if before.head != recorded_head:
        raise HeadDrift(
            f"Live HEAD {before.head} differs from the prompt's recorded head {recorded_head}"
        )

    def observe(
        *,
        ok: bool,
        failure_code: str | None,
        report: AgentReport | None,
        exit_code: int | None,
        stdout: bytes,
        stderr: bytes,
        changed: list[str],
        patch: bytes,
        verifications: list[VerificationCommandResult],
        sandbox_path: Path | None,
    ) -> RunObservation:
        return RunObservation(
            agent_name=agent.name,
            agent_mode=agent.mode,
            agent_executable=agent.executable.as_posix(),
            agent_args=list(agent.args),
            timeout_seconds=agent.timeout_seconds,
            task_id=normalized_task,
            stage=stage,
            prompt_id=prompt_id,
            repository_head=recorded_head,
            ok=ok,
            failure_code=failure_code,
            report=report,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            actual_changed_paths=changed,
            patch=patch,
            verification_results=verifications,
            sandbox_path=sandbox_path,
        )

    sandbox = create_sandbox(repository, recorded_head)
    kept = False
    try:
        markdown = rendered.markdown.encode("utf-8")
        exit_code, stdout, stderr, timed_out = _run_with_group_timeout(
            [str(agent.executable), *agent.args],
            cwd=sandbox,
            env=_scrubbed_env(),
            timeout=agent.timeout_seconds,
            input_bytes=markdown,
        )

        # Observe the raw change set the agent produced in the sandbox (evidence, not judgement).
        sandbox_git = SandboxGit(sandbox)
        sandbox_git.stage_all()
        changed = sandbox_git.changed_paths()
        patch = sandbox_git.diff_cached_binary()

        # Classify the agent-output outcome in the fixed order.
        report: AgentReport | None = None
        failure_code: str | None = None
        if timed_out:
            failure_code = "agent_timeout"
        elif exit_code != 0:
            failure_code = "agent_nonzero_exit"
        else:
            report, failure_code = _parse_report(stdout)
            if report is not None and _binding_failure(
                report,
                task_id=normalized_task,
                stage=stage,
                prompt_id=prompt_id,
                mode=agent.mode,
            ):
                report, failure_code = None, "agent_report_mismatch"

        verifications: list[VerificationCommandResult] = []
        if failure_code is None:
            verifications = _run_verification_commands(config, sandbox)

        # A run that changed the *target* repository fails regardless of everything else.
        after = GitClient(repository).status()
        if after != before:
            failure_code, report = "repository_mutated", None

        ok = failure_code is None
        if keep_sandbox:
            kept = True
        return observe(
            ok=ok,
            failure_code=failure_code,
            report=report,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            changed=changed,
            patch=patch,
            verifications=verifications,
            sandbox_path=sandbox if keep_sandbox else None,
        )
    finally:
        if not kept:
            teardown(sandbox)


def _run_verification_commands(
    config: EngineConfig, sandbox: Path
) -> list[VerificationCommandResult]:
    env = _scrubbed_env()
    env["PYTHONPATH"] = str((sandbox / "src").resolve())
    results: list[VerificationCommandResult] = []
    for argv in verification_argv(config.project.conda_environment):
        try:
            returncode, _out, _err, timed_out = _run_with_group_timeout(
                argv, cwd=sandbox, env=env, timeout=_VERIFICATION_TIMEOUT
            )
        except OSError:
            exit_code = 127
        else:
            exit_code = 124 if timed_out else (returncode if returncode is not None else 1)
        results.append(VerificationCommandResult(argv=argv, exit_code=exit_code))
    return results
