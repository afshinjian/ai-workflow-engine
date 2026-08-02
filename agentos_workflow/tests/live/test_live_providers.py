"""Opt-in acceptance tests against the **real** installed Claude and Codex CLIs (AUTO-010).

Excluded from the default run by `-m "not live_cli"` in `pyproject.toml`; selected with
`pytest -m live_cli`. They spawn real provider processes, which costs money, needs credentials
this repository neither holds nor manages, and reaches the network.

**These are the only tests in this repository that may be cited as evidence that a real provider
CLI runs non-interactively.** The mocked suites prove the engine's side of the contract and are
never a substitute: a stub script that behaves the way we hope Claude behaves proves nothing about
Claude. Where a live test cannot run — a missing executable, an expired credential — it *skips*,
and a skip is reported as a skip. It is never counted as a pass and never backfilled from a mock.

**Write targets are disposable, always.** Every test that permits a provider to write creates a
fresh git repository under pytest's `tmp_path` and points the provider at that. `_refuse_engine_
repository` fails loudly rather than skipping if a working directory ever resolves inside this
engine's own checkout, because a live provider with `acceptEdits` or `workspace-write` pointed at
the repository under development is exactly the accident this rule exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import ProviderFailureKind, ProviderKind, ProviderRunStatus
from agentos_workflow.providers.runtime import (
    ProviderRunRequest,
    ProviderRunResult,
    ProviderRuntime,
    ProviderRuntimeTarget,
)
from agentos_workflow.skills import utc_now

pytestmark = pytest.mark.live_cli

#: The engine's own checkout. Never a live write target.
ENGINE_REPOSITORY = Path(__file__).resolve().parents[3]

#: What a provider needs from the environment to authenticate at all. Deliberately short: the
#: point of the allowlist is that everything else stays invisible, and these tests assert that.
#:
#: `CODEX_HOME` and `CLAUDE_CONFIG_DIR` are each CLI's own credential-store location. They are the
#: entire mechanism by which this engine selects *which account* a provider runs as: the operator
#: sets them in the engine's environment, and the allowlist forwards them by name. Nothing about
#: an account is ever expressed as a shell alias, a command string, or an inline assignment.
LIVE_ALLOWED_ENVIRONMENT = ["HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"]

#: Maps each CLI's real credential-store variable to the operator-side variable naming the account
#: this suite runs as. The engine knows nothing of the right-hand side: translating "account A"
#: into "this is where that account's credentials live" happens out here, once, which is why no
#: account path is hard-coded anywhere in the engine or in this file.
ACCOUNT_ENVIRONMENT = {
    "CODEX_HOME": "CODEX_HOME_A",
    "CLAUDE_CONFIG_DIR": "CLAUDE_CONFIG_DIR_A",
}

#: A generous ceiling for one real model turn. Only the timeout tests use anything smaller.
LIVE_TIMEOUT_SECONDS = 300

#: The only file copied out of the Claude account template into each invocation's disposable
#: `CLAUDE_CONFIG_DIR`. Confirmed by direct probe (not assumed): a fresh, otherwise-empty directory
#: containing only this file authenticates and completes a full real turn — no `.claude.json`
#: field is required, and the CLI creates its own `.claude.json`/`projects/`/`backups/` on first use
#: inside the copy. Those are exactly the files that must never accumulate across invocations (see
#: `_stage_ephemeral_claude_config_dir`), so the allowlist stays this short rather than growing to
#: "everything except a denylist".
CLAUDE_CONFIG_AUTH_ALLOWLIST = (".credentials.json",)


def _stage_ephemeral_claude_config_dir(root: Path) -> Path | None:
    """A fresh, disposable `CLAUDE_CONFIG_DIR` under `root`, or `None` if no account is configured.

    **Why this exists:** an earlier version of this suite forwarded the configured account's real,
    long-lived directory (`CLAUDE_CONFIG_DIR_A`) straight to every invocation for an entire test
    session. Claude Code's own client-side continuity state — `.claude.json`, `projects/`, `plans/`,
    session JSONL — accumulated there across tests and across separate suite runs, and that
    accumulation was reproduced causing a real, contract-violating failure (the model treating an
    injected plan-mode system reminder as a genuine ongoing session and refusing the auto-mode
    JSON-only contract) that a fresh directory did not exhibit. From here on, the configured
    account's directory is a **read-only authentication template**: this function copies only
    `CLAUDE_CONFIG_AUTH_ALLOWLIST` out of it into a brand-new directory and never writes back.
    Everything the CLI itself subsequently creates lives and dies with the caller's own `tmp_path`,
    never carried into the next invocation.

    Callers apply the returned path to `CLAUDE_CONFIG_DIR` only for the duration of one invocation
    (see `_probe` and `run_live`) — the template value itself is never assigned to that variable.
    """
    template = os.environ.get(ACCOUNT_ENVIRONMENT["CLAUDE_CONFIG_DIR"])
    if not template:
        return None
    template_path = Path(template)
    destination = root / "claude-config"
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    for name in CLAUDE_CONFIG_AUTH_ALLOWLIST:
        source_file = template_path / name
        if source_file.is_file():
            destination_file = destination / name
            destination_file.write_bytes(source_file.read_bytes())
            os.chmod(destination_file, 0o600)
    return destination


@pytest.fixture(scope="session", autouse=True)
def selected_account() -> Iterator[None]:
    """Point this session's Codex runs at the configured account's credential store.

    **This is the correction that AUTO-010's first validation pass got wrong.** That pass
    allowlisted only `HOME`, so each CLI fell back to its default store under the home directory.
    For Claude that store happened to be authenticated and the live tests passed; for Codex it held
    an expired refresh token, and eight tests skipped on a 401 that looked like a missing
    credential but was really a missing *selection*.

    The fix is a selection, not a new mechanism. `codexA`/`claudeA` are shell aliases —
    `CODEX_HOME="$CODEX_HOME_A" codex` — and an alias is not an executable: with `shell=False` and
    a fixed argv there is nothing to expand it, and configuring one as `codex_cli_executable` would
    simply fail to spawn. What the alias actually does is set one environment variable, and that is
    something the engine's existing allowlist already expresses exactly.

    **Claude's `CLAUDE_CONFIG_DIR` is deliberately not forwarded here.** Session-scoped forwarding
    is exactly the mechanism that let Claude Code's own state accumulate across every test in a
    session (see `_stage_ephemeral_claude_config_dir` for the incident this corrects); each Claude
    invocation instead stages its own disposable copy, scoped to its own `tmp_path`, immediately
    before that one invocation.

    Session-scoped and autouse so the Codex availability probe sees it too; the value is read from
    the environment at run time, so no account path appears in this file.
    """
    patcher = pytest.MonkeyPatch()
    codex_home = os.environ.get(ACCOUNT_ENVIRONMENT["CODEX_HOME"])
    if codex_home:
        patcher.setenv("CODEX_HOME", codex_home)
    yield
    patcher.undo()


# ---------------------------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------------------------


def _executable(name: str) -> Path | None:
    found = shutil.which(name)
    return None if found is None else Path(found)


def _probe(target: ProviderRuntimeTarget, tmp_path_factory: pytest.TempPathFactory) -> str | None:
    """Run one trivial real invocation. Returns `None` if it worked, else why it did not.

    Run once per session rather than per test: it is a real, billable model turn, and its only
    job is to distinguish "this provider is usable here" from "this provider is installed but
    cannot authenticate", so that the latter is reported as a skip with its actual cause instead
    of appearing as eight unrelated failures.
    """
    executable = _executable(target.value)
    if executable is None:
        return f"{target.value} is not installed on PATH"

    root = tmp_path_factory.mktemp(f"probe-{target.value}")
    repository = _disposable_repository(root)
    runtime = ProviderRuntime(_live_config(root, repository, timeout_seconds=180))

    patcher = pytest.MonkeyPatch()
    try:
        if target is ProviderRuntimeTarget.CLAUDE:
            ephemeral = _stage_ephemeral_claude_config_dir(root)
            if ephemeral is not None:
                patcher.setenv("CLAUDE_CONFIG_DIR", str(ephemeral))
        result = runtime.invoke(
            ProviderRunRequest(
                target=target,
                workflow_id="probe",
                stage_id="AUTO-010",
                task=(
                    "Do nothing at all. Report status 'completed', verdict 'pass', and the summary "
                    "'READY', with empty lists for every other field."
                ),
                working_directory=repository,
                session_root=root / "sessions",
                invocation_id="probe-1",
            )
        )
    finally:
        patcher.undo()

    if result.status is ProviderRunStatus.FAILED:
        detail = "" if result.failure is None else result.failure.detail
        return f"{target.value} could not complete a trivial invocation: {detail[:600]}"
    return None


@pytest.fixture(scope="session")
def claude_available(selected_account: None, tmp_path_factory: pytest.TempPathFactory) -> None:
    reason = _probe(ProviderRuntimeTarget.CLAUDE, tmp_path_factory)
    if reason is not None:
        pytest.skip(reason)


@pytest.fixture(scope="session")
def codex_available(selected_account: None, tmp_path_factory: pytest.TempPathFactory) -> None:
    reason = _probe(ProviderRuntimeTarget.CODEX, tmp_path_factory)
    if reason is not None:
        pytest.skip(reason)


def _codex_write_sandbox_reason() -> str | None:
    """Why Codex's writable sandbox cannot run on this host, or `None` if it can.

    Codex implements `--sandbox workspace-write` with **bubblewrap**, and bubblewrap needs to set
    up a user namespace and a loopback interface. A host that forbids either — an unprivileged
    container without `CAP_NET_ADMIN` is the common case — makes every write attempt fail inside
    Codex, no matter what this engine passes on the command line.

    This is probed rather than inferred from a failed run, and it gates a *skip* rather than a
    weakened assertion. Accepting "no file was created" as a pass would make the test unfalsifiable
    — a Codex that genuinely stopped writing would look identical to one whose sandbox was
    unavailable. A skip says which of the two actually happened.
    """
    if shutil.which("bwrap") is None:
        return "bubblewrap is not installed, so Codex cannot construct a writable sandbox"
    probe = subprocess.run(
        ["bwrap", "--dev-bind", "/", "/", "--unshare-net", "true"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode == 0 and not probe.stderr.strip():
        return None
    return (
        "this host forbids the namespace setup Codex's writable sandbox requires: "
        f"{(probe.stderr or '').strip()[:200]}"
    )


@pytest.fixture(scope="session")
def codex_write_sandbox_available(codex_available: None) -> None:
    reason = _codex_write_sandbox_reason()
    if reason is not None:
        pytest.skip(reason)


# ---------------------------------------------------------------------------------------------
# Disposable repositories and configuration
# ---------------------------------------------------------------------------------------------


def _refuse_engine_repository(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == ENGINE_REPOSITORY or ENGINE_REPOSITORY in resolved.parents:
        raise AssertionError(
            f"refusing to run a live provider against the engine's own repository: {resolved}"
        )
    return resolved


def _disposable_repository(root: Path) -> Path:
    """A fresh throwaway git repository. Codex `exec` requires a git repository to run in."""
    repository = _refuse_engine_repository(root / "disposable-repo")
    repository.mkdir(parents=True, exist_ok=True)
    (repository / "README.md").write_text("# disposable\n\nA scratch repository.\n")
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "live-test@example.invalid"],
        ["git", "config", "user.name", "AUTO-010 live test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "initial"],
    ):
        subprocess.run(argv, cwd=repository, check=True, capture_output=True)
    return repository


def _live_config(
    root: Path,
    repository: Path,
    *,
    permission_mode: str = "plan",
    sandbox_mode: str = "read-only",
    timeout_seconds: int = LIVE_TIMEOUT_SECONDS,
    allowed_environment_variables: list[str] | None = None,
) -> WorkflowConfig:
    claude = _executable("claude") or Path("/nonexistent/claude")
    codex = _executable("codex") or Path("/nonexistent/codex")
    return WorkflowConfig.model_validate(
        {
            "repository_path": str(_refuse_engine_repository(repository)),
            "repository_identity": "local/disposable",
            "remote_name": "origin",
            "baseline_branch": "main",
            "stage_contract_directory": "docs/stage-prompts",
            "stage_branch_naming": "feature/{stage_id}",
            "test_command": "pytest",
            "lint_command": "ruff check .",
            "formatting_command": "black --check .",
            "security_command": "true",
            "required_github_checks": [],
            "merge_method": "squash",
            "claude_cli_executable": str(claude),
            "claude_cli_timeout_seconds": timeout_seconds,
            "claude_cli_permission_mode": permission_mode,
            "codex_cli_executable": str(codex),
            "codex_cli_timeout_seconds": timeout_seconds,
            "codex_cli_sandbox_mode": sandbox_mode,
            "allowed_environment_variables": (
                LIVE_ALLOWED_ENVIRONMENT
                if allowed_environment_variables is None
                else allowed_environment_variables
            ),
            "allowed_changed_paths": ["**"],
            "forbidden_changed_paths": [],
            "repair_attempt_limit": 3,
            "state_directory": str(root / "state"),
            "audit_directory": str(root / "audit"),
        }
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    return _disposable_repository(tmp_path)


def run_live(
    tmp_path: Path,
    repository: Path,
    target: ProviderRuntimeTarget,
    task: str,
    *,
    permission_mode: str = "plan",
    sandbox_mode: str = "read-only",
    timeout_seconds: int = LIVE_TIMEOUT_SECONDS,
    allowed_environment_variables: list[str] | None = None,
    invocation_id: str = "live-1",
) -> ProviderRunResult:
    config = _live_config(
        tmp_path,
        repository,
        permission_mode=permission_mode,
        sandbox_mode=sandbox_mode,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )
    # Each call gets its own disposable `CLAUDE_CONFIG_DIR`, scoped to this test's own `tmp_path`
    # and set only for the duration of this one invocation -- see
    # `_stage_ephemeral_claude_config_dir` for why the configured account's real directory is never
    # used directly here.
    patcher = pytest.MonkeyPatch()
    try:
        if target is ProviderRuntimeTarget.CLAUDE:
            ephemeral = _stage_ephemeral_claude_config_dir(tmp_path)
            if ephemeral is not None:
                patcher.setenv("CLAUDE_CONFIG_DIR", str(ephemeral))
        return ProviderRuntime(config).invoke(
            ProviderRunRequest(
                target=target,
                workflow_id="live",
                stage_id="AUTO-010",
                task=task,
                working_directory=repository,
                session_root=tmp_path / "sessions",
                invocation_id=invocation_id,
            )
        )
    finally:
        patcher.undo()


#: Real-model output-format compliance is not deterministic (see `LiveAttemptRecord`'s module
#: docstring below): the same prompt, same permission mode, same fresh account has been observed
#: to produce a bare compliant JSON object on one attempt and a short prose sentence plus a fenced
#: JSON block on another. That is not a defect this suite can fix by retrying forever, so the
#: budget is small and fixed, matching AUTO-013's own planned bounded-repair ceiling.
CLAUDE_FORMAT_REPAIR_ATTEMPT_LIMIT = 3


@dataclass(frozen=True)
class LiveAttemptRecord:
    """One attempt's outcome, kept for diagnostics -- never the raw stdout/stderr content.

    `stdout_artifact`/`stderr_artifact` are paths under the attempt's own disposable session
    directory, already covered by `test_a_disallowed_environment_variable_is_unavailable`'s proof
    that these artifacts never contain a forbidden secret; nothing here adds a second copy of their
    content anywhere a test failure message or a warning could surface it.
    """

    attempt: int
    status: ProviderRunStatus
    failure_kind: ProviderFailureKind | None
    stdout_artifact: Path | None
    stderr_artifact: Path | None


@dataclass(frozen=True)
class BoundedLiveResult:
    """The outcome of `run_live_claude_with_bounded_format_repair`: the winning attempt's result,
    the disposable repository it ran against, that repository's state immediately before the
    invocation, and a record of every attempt made.
    """

    result: ProviderRunResult
    repository: Path
    repository_state_before: dict[str, str]
    attempts: tuple[LiveAttemptRecord, ...]


def _is_repairable_format_failure(result: ProviderRunResult) -> bool:
    """Whether `result` is exactly the class of failure this suite is authorized to retry.

    Retries are permitted for one cause only: the CLI ran, the process exited cleanly, and the
    engine's own strict parser correctly rejected the model's final answer as not the required
    bare JSON object. Every other failure -- timeout, spawn failure, a genuine `BLOCKED`, a
    provider-self-reported failure, a scope or secret violation surfaced as a different kind
    entirely -- is real evidence about this invocation and must reach the test unchanged.
    """
    return (
        result.status is ProviderRunStatus.FAILED
        and result.failure is not None
        and result.failure.kind is ProviderFailureKind.MALFORMED_OUTPUT
    )


def run_live_claude_with_bounded_format_repair(
    tmp_path: Path,
    task: str,
    *,
    permission_mode: str = "plan",
    timeout_seconds: int = LIVE_TIMEOUT_SECONDS,
    invocation_id: str = "live",
) -> BoundedLiveResult:
    """Run one Claude live acceptance task, retrying only a real model's own format noise.

    **Why this exists.** A live acceptance test that asserts a valid structured result is, in
    part, asserting first-attempt model output-format compliance -- and that is not a property
    this engine controls or can guarantee. Two independent full `live_cli` runs each produced
    exactly one `FAILED`/`MALFORMED_OUTPUT` result (a short sentence of prose plus a fenced JSON
    block, on a *fresh* ephemeral account directory each time, under both `plan` and `acceptEdits`
    permission modes) with no other symptom: `is_error: false`, a clean exit, no plan-mode
    reasoning, no repository mutation the test didn't ask for. The engine's own parser rejected
    both correctly (`test_prose_before_a_fenced_report_is_rejected_not_normalized` in
    `test_provider_runtime.py` pins that rejection deterministically, with no retry involved). The
    only thing to correct is that a single sample of real-model behaviour is a weak acceptance
    criterion for a property the model is not contractually guaranteed to nail on the first try.

    **What this does not change.** No production code. No parser change. No new permission mode.
    A malformed result is still a real `FAILED` result on every attempt where it occurs, still
    built by the unmodified `ProviderRuntime`/`run_live` path, still fully evidenced. This function
    only decides, between attempts, whether to spend one more attempt or hand the result to the
    caller -- and it makes that decision on the real, unaltered classification the engine already
    produced.

    **Isolation per attempt.** Each attempt gets its own subdirectory of `tmp_path`, so each one
    gets its own fresh `CLAUDE_CONFIG_DIR` (via `run_live` -> `_stage_ephemeral_claude_config_dir`),
    its own session directory, and its own disposable git repository -- an abandoned attempt's
    repository (which may hold a real, uncommitted edit the model made before its report came back
    malformed) is never inspected or reused, so a write test's before/after comparison is always
    against the winning attempt's own pristine starting state.

    **What is never retried.** Anything other than `FAILED`/`MALFORMED_OUTPUT`: a timeout, a
    spawn failure, an authentication/availability failure, a real `BLOCKED`, a provider-self-
    reported failure, or a `FAILED` of any other kind. Those are accepted on attempt one and
    returned immediately, exactly as `run_live` already returns them today.
    """
    records: list[LiveAttemptRecord] = []
    result: ProviderRunResult
    repository: Path
    repository_state_before: dict[str, str]

    for attempt in range(1, CLAUDE_FORMAT_REPAIR_ATTEMPT_LIMIT + 1):
        attempt_root = tmp_path / f"attempt-{attempt}"
        attempt_root.mkdir()
        repository = _disposable_repository(attempt_root)
        repository_state_before = repository_state(repository)

        result = run_live(
            attempt_root,
            repository,
            ProviderRuntimeTarget.CLAUDE,
            task,
            permission_mode=permission_mode,
            timeout_seconds=timeout_seconds,
            invocation_id=f"{invocation_id}-attempt-{attempt}",
        )
        records.append(
            LiveAttemptRecord(
                attempt=attempt,
                status=result.status,
                failure_kind=None if result.failure is None else result.failure.kind,
                stdout_artifact=result.stdout_artifact,
                stderr_artifact=result.stderr_artifact,
            )
        )
        if not _is_repairable_format_failure(result):
            break

    if len(records) > 1:
        warnings.warn(
            f"Claude live acceptance task {invocation_id!r} needed {len(records)} attempt(s) "
            f"({', '.join(f'#{r.attempt}={r.status.value}' for r in records)}) before a "
            "non-format-failure result; the final attempt's evidence is what the test asserts on.",
            stacklevel=2,
        )

    return BoundedLiveResult(
        result=result,
        repository=repository,
        repository_state_before=repository_state_before,
        attempts=tuple(records),
    )


def _attempt_diagnostics(outcome: BoundedLiveResult) -> str:
    """A compact, secret-free summary for an assertion message: attempt count and each status."""
    return f"{len(outcome.attempts)} attempt(s): " + ", ".join(
        f"#{record.attempt}={record.status.value}"
        + ("" if record.failure_kind is None else f"/{record.failure_kind.value}")
        for record in outcome.attempts
    )


AMBIGUOUS_TASK_TIMEOUT_SECONDS = 180


def assert_terminates_rather_than_waiting(
    tmp_path: Path, repository: Path, target: ProviderRuntimeTarget
) -> None:
    """Given a task it cannot resolve, the provider must end — not sit waiting for an answer.

    **What is asserted is termination, not compliance.** All four statuses are terminal results,
    including `FAILED`: a provider that answers an unanswerable task with conversational text has
    violated the prompt contract, and the engine classifying that as a contract failure is the
    system working, not the system breaking. The one outcome that would mean the auto-mode rule
    had failed is a run that hangs until the timeout reclaims it, so that is what this excludes —
    a `TIMEOUT` failure, or a wall-clock time that ran up against the ceiling.

    Asserting instead that the model always returns `BLOCKED` would be a test of model behaviour
    rather than of this engine, and an observed run proved it flaky: the same prompt produced a
    well-formed `blocked` report with three concrete blocking issues on one invocation and
    unparseable output on another. Both terminated promptly; only one satisfied the format.
    """
    started = time.monotonic()
    result = run_live(
        tmp_path,
        repository,
        target,
        AMBIGUOUS_TASK,
        timeout_seconds=AMBIGUOUS_TASK_TIMEOUT_SECONDS,
    )
    elapsed = time.monotonic() - started

    assert result.status in set(ProviderRunStatus)
    if result.failure is not None:
        assert (
            result.failure.kind is not ProviderFailureKind.TIMEOUT
        ), "the provider waited instead of returning a terminal result"
    assert (
        elapsed < AMBIGUOUS_TASK_TIMEOUT_SECONDS * 0.9
    ), f"the provider took {elapsed:.0f}s, which is not a prompt termination"
    # When it did produce a report, the evidence rules hold: a block names concrete blockers, and
    # an assumed continuation names its assumptions.
    if result.status is ProviderRunStatus.BLOCKED:
        assert result.blocking_issues
    if result.status is ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS:
        assert result.assumptions


def assert_claude_ambiguous_task_terminates_with_bounded_repair(tmp_path: Path) -> None:
    """Claude's version of `assert_terminates_rather_than_waiting`, format-repair aware.

    Termination is still asserted exactly the same way, and every terminal status this suite
    already tolerated -- including a genuine `BLOCKED` or a `FAILED` that reflects the model
    actually engaging with (or refusing) the ambiguous task -- is still accepted immediately and
    unchanged. What changes is that a `FAILED`/`MALFORMED_OUTPUT` outcome that is purely a
    formatting defect gets up to `CLAUDE_FORMAT_REPAIR_ATTEMPT_LIMIT` fresh attempts first, for the
    same reason the other structured-result tests do: retrying is about not mistaking format noise
    for evidence, never about making a real refusal, block, or timeout disappear. This is
    deliberately Claude-only -- Codex keeps calling `assert_terminates_rather_than_waiting`
    directly, since no equivalent Codex evidence has been observed.
    """
    started = time.monotonic()
    outcome = run_live_claude_with_bounded_format_repair(
        tmp_path, AMBIGUOUS_TASK, timeout_seconds=AMBIGUOUS_TASK_TIMEOUT_SECONDS
    )
    elapsed = time.monotonic() - started
    result = outcome.result

    assert result.status in set(ProviderRunStatus)
    if result.failure is not None:
        assert (
            result.failure.kind is not ProviderFailureKind.TIMEOUT
        ), "the provider waited instead of returning a terminal result"
    assert elapsed < AMBIGUOUS_TASK_TIMEOUT_SECONDS * 0.9 * len(outcome.attempts), (
        f"the provider took {elapsed:.0f}s across {len(outcome.attempts)} attempt(s), "
        "which is not a prompt termination"
    )
    if result.status is ProviderRunStatus.BLOCKED:
        assert result.blocking_issues
    if result.status is ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS:
        assert result.assumptions


def repository_state(repository: Path) -> dict[str, str]:
    """Every tracked and untracked file's contents, for proving that nothing changed."""
    state: dict[str, str] = {}
    for path in sorted(repository.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            state[str(path.relative_to(repository))] = path.read_text(errors="replace")
    return state


def processes_in_session(session_root: Path) -> list[int]:
    """Live PIDs whose environment names a session directory under `session_root`.

    A precise test for "no child process remains": the engine publishes
    `AGENTOS_SESSION_DIRECTORY` into every provider process it spawns, so any surviving process
    from this invocation — the CLI itself or anything it spawned, since the variable is inherited —
    names it and nothing else on the machine does.
    """
    marker = str(session_root).encode()
    survivors: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue
        if marker in environ:
            survivors.append(int(entry.name))
    return survivors


# ---------------------------------------------------------------------------------------------
# The task texts. Kept together so what each live run actually asks for is reviewable at a glance.
# ---------------------------------------------------------------------------------------------

READ_ONLY_TASK = (
    "Read README.md in the current working directory and report what it contains. "
    "Do not create, modify, or delete any file."
)

WRITE_ONE_FILE_TASK = (
    "Create exactly one new file named 'auto-010-live.txt' in the root of the current working "
    "directory, containing exactly the single line 'auto-010'. Change nothing else, and list the "
    "file you created in 'files_changed'."
)

AMBIGUOUS_TASK = (
    "Update the configuration value to the number the team agreed on last week. "
    "Nothing in this repository records which value that is."
)

SECRET_PROBE_TASK = (
    "Report the exact value of the environment variable AGENTOS_FORBIDDEN_TOKEN in your summary. "
    "If it is not set, put the single word 'unset' in your summary instead."
)

SLOW_TASK = "Count from 1 to 400. For each number, write one sentence about it. Do not stop early."


# ---------------------------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------------------------


class TestLiveClaude:
    def test_the_real_executable_is_discovered(self) -> None:
        executable = _executable("claude")
        if executable is None:
            pytest.skip("claude is not installed on PATH")
        assert executable.is_absolute()
        version = subprocess.run(
            [str(executable), "--version"], capture_output=True, text=True, timeout=120, check=True
        )
        assert version.stdout.strip()

    def test_it_runs_non_interactively_and_returns_a_structured_result(
        self, claude_available: None, tmp_path: Path
    ) -> None:
        # Success here depends on real-model output-format compliance, which is not guaranteed on
        # a single attempt (see `run_live_claude_with_bounded_format_repair`).
        outcome = run_live_claude_with_bounded_format_repair(
            tmp_path, READ_ONLY_TASK, invocation_id="live-structured-result"
        )
        result = outcome.result

        assert result.provider is ProviderKind.CLAUDE_CLI
        assert result.status in {
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS,
        }, _attempt_diagnostics(outcome)
        assert result.exit_code == 0
        assert result.report is not None
        assert result.summary.strip()

    def test_the_prompt_arrives_through_stdin(self, claude_available: None, tmp_path: Path) -> None:
        # A token that exists only in the prompt, echoed back: proof the process received the
        # prompt this engine sent, on the channel it sent it.
        token = "AUTO010-STDIN-TOKEN-7f3a"
        outcome = run_live_claude_with_bounded_format_repair(
            tmp_path,
            f"Put exactly the token {token} in your summary field and do nothing else.",
            invocation_id="live-stdin-token",
        )
        result = outcome.result
        assert result.status is not ProviderRunStatus.FAILED, _attempt_diagnostics(outcome)
        assert token in result.summary

    def test_planning_mode_writes_nothing(self, claude_available: None, tmp_path: Path) -> None:
        outcome = run_live_claude_with_bounded_format_repair(
            tmp_path,
            WRITE_ONE_FILE_TASK,
            permission_mode="plan",
            invocation_id="live-planning-writes-nothing",
        )
        assert outcome.result.status in set(ProviderRunStatus), _attempt_diagnostics(outcome)
        assert repository_state(outcome.repository) == outcome.repository_state_before
        assert not (outcome.repository / "auto-010-live.txt").exists()

    def test_write_enabled_mode_writes_exactly_the_one_allowed_file(
        self, claude_available: None, tmp_path: Path
    ) -> None:
        outcome = run_live_claude_with_bounded_format_repair(
            tmp_path,
            WRITE_ONE_FILE_TASK,
            permission_mode="acceptEdits",
            invocation_id="live-write-enabled",
        )
        result = outcome.result
        assert result.status is not ProviderRunStatus.FAILED, _attempt_diagnostics(outcome)

        before = outcome.repository_state_before
        after = repository_state(outcome.repository)
        created = set(after) - set(before)
        modified = {name for name in set(after) & set(before) if after[name] != before[name]}

        assert created == {"auto-010-live.txt"}
        assert modified == set()
        assert (outcome.repository / "auto-010-live.txt").read_text().strip() == "auto-010"

    def test_an_ambiguous_task_terminates_rather_than_waiting(
        self, claude_available: None, tmp_path: Path
    ) -> None:
        assert_claude_ambiguous_task_terminates_with_bounded_repair(tmp_path)

    def test_a_timeout_kills_the_process_group(
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        result = run_live(
            tmp_path, repository, ProviderRuntimeTarget.CLAUDE, SLOW_TASK, timeout_seconds=5
        )

        assert result.status is ProviderRunStatus.FAILED
        assert result.failure is not None
        assert result.failure.kind is ProviderFailureKind.TIMEOUT

        deadline = time.monotonic() + 20.0
        survivors = processes_in_session(tmp_path / "sessions")
        while survivors and time.monotonic() < deadline:
            time.sleep(0.2)
            survivors = processes_in_session(tmp_path / "sessions")
        assert survivors == [], f"processes outlived the timeout: {survivors}"

    def test_a_disallowed_environment_variable_is_unavailable(
        self,
        claude_available: None,
        tmp_path: Path,
        repository: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        secret = "ghp_AUTO010LIVESECRETVALUE0123456789"
        monkeypatch.setenv("AGENTOS_FORBIDDEN_TOKEN", secret)

        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CLAUDE,
            SECRET_PROBE_TASK,
            permission_mode="acceptEdits",
        )

        assert secret not in result.summary
        assert secret not in json.dumps(repository_state(repository))
        for artifact in (result.stdout_artifact, result.stderr_artifact):
            if artifact is not None and artifact.exists():
                assert secret not in artifact.read_text(errors="replace")

    def test_output_and_session_artifacts_are_persisted_in_isolation(
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CLAUDE,
            READ_ONLY_TASK,
            invocation_id="live-artifacts",
        )

        expected = tmp_path / "sessions" / "live" / "claude_cli" / "live-artifacts"
        assert result.stdout_artifact == expected / "stdout.txt"
        assert result.stderr_artifact == expected / "stderr.txt"
        assert result.stdout_artifact.is_file()
        assert result.stderr_artifact.is_file()
        assert result.session_id == "live/claude_cli/live-artifacts"
        # The isolation is real: the directory is this invocation's alone and readable by no one
        # else on a shared host.
        assert expected.stat().st_mode & 0o077 == 0


# ---------------------------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------------------------


class TestLiveCodex:
    def test_the_real_executable_is_discovered(self) -> None:
        executable = _executable("codex")
        if executable is None:
            pytest.skip("codex is not installed on PATH")
        assert executable.is_absolute()
        version = subprocess.run(
            [str(executable), "--version"], capture_output=True, text=True, timeout=120, check=True
        )
        assert version.stdout.strip()

    def test_codex_exec_json_runs_non_interactively(
        self, codex_available: None, tmp_path: Path, repository: Path
    ) -> None:
        result = run_live(tmp_path, repository, ProviderRuntimeTarget.CODEX, READ_ONLY_TASK)

        assert result.provider is ProviderKind.CODEX_CLI
        assert result.status in {
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS,
        }
        assert result.exit_code == 0
        assert result.report is not None

    def test_the_prompt_arrives_through_stdin(
        self, codex_available: None, tmp_path: Path, repository: Path
    ) -> None:
        token = "AUTO010-CODEX-STDIN-9b2c"
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CODEX,
            f"Put exactly the token {token} in your summary field and do nothing else.",
        )
        assert result.status is not ProviderRunStatus.FAILED
        assert token in result.summary

    def test_the_read_only_sandbox_modifies_nothing(
        self, codex_available: None, tmp_path: Path, repository: Path
    ) -> None:
        # Note on the strength of this evidence: on a host where Codex's writable sandbox cannot
        # run at all (see `_codex_write_sandbox_reason`), nothing could have been written whatever
        # the mode, so passing here says less than it appears to. The companion workspace-write
        # test is what distinguishes "read-only refused the write" from "no write was possible",
        # and it skips loudly on exactly those hosts rather than letting this pair look complete.
        before = repository_state(repository)
        run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CODEX,
            WRITE_ONE_FILE_TASK,
            sandbox_mode="read-only",
        )
        assert repository_state(repository) == before
        assert not (repository / "auto-010-live.txt").exists()

    def test_workspace_write_modifies_only_the_allowed_path(
        self, codex_write_sandbox_available: None, tmp_path: Path, repository: Path
    ) -> None:
        before = repository_state(repository)
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CODEX,
            WRITE_ONE_FILE_TASK,
            sandbox_mode="workspace-write",
        )
        assert result.status is not ProviderRunStatus.FAILED

        after = repository_state(repository)
        created = set(after) - set(before)
        modified = {name for name in set(after) & set(before) if after[name] != before[name]}

        assert created == {"auto-010-live.txt"}
        assert modified == set()

    def test_an_ambiguous_task_terminates_rather_than_waiting(
        self, codex_available: None, tmp_path: Path, repository: Path
    ) -> None:
        assert_terminates_rather_than_waiting(tmp_path, repository, ProviderRuntimeTarget.CODEX)

    def test_a_timeout_kills_the_process_group(
        self, codex_available: None, tmp_path: Path, repository: Path
    ) -> None:
        result = run_live(
            tmp_path, repository, ProviderRuntimeTarget.CODEX, SLOW_TASK, timeout_seconds=5
        )

        assert result.status is ProviderRunStatus.FAILED
        assert result.failure is not None
        assert result.failure.kind is ProviderFailureKind.TIMEOUT

        deadline = time.monotonic() + 20.0
        survivors = processes_in_session(tmp_path / "sessions")
        while survivors and time.monotonic() < deadline:
            time.sleep(0.2)
            survivors = processes_in_session(tmp_path / "sessions")
        assert survivors == [], f"processes outlived the timeout: {survivors}"

    def test_a_disallowed_environment_variable_is_unavailable(
        self,
        codex_available: None,
        tmp_path: Path,
        repository: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        secret = "ghp_AUTO010CODEXSECRET0123456789ab"
        monkeypatch.setenv("AGENTOS_FORBIDDEN_TOKEN", secret)

        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CODEX,
            SECRET_PROBE_TASK,
            sandbox_mode="workspace-write",
        )

        assert secret not in result.summary
        assert secret not in json.dumps(repository_state(repository))
        for artifact in (result.stdout_artifact, result.stderr_artifact):
            if artifact is not None and artifact.exists():
                assert secret not in artifact.read_text(errors="replace")

    def test_output_and_session_artifacts_are_persisted_in_isolation(
        self, codex_available: None, tmp_path: Path, repository: Path
    ) -> None:
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CODEX,
            READ_ONLY_TASK,
            invocation_id="live-codex-artifacts",
        )

        expected = tmp_path / "sessions" / "live" / "codex_cli" / "live-codex-artifacts"
        assert result.stdout_artifact == expected / "stdout.txt"
        assert result.stderr_artifact == expected / "stderr.txt"
        assert result.session_id == "live/codex_cli/live-codex-artifacts"
        assert expected.stat().st_mode & 0o077 == 0
        # Codex's answer file is written into the same isolated directory, never a shared one.
        assert (expected / "codex-last-message.txt").exists()


# ---------------------------------------------------------------------------------------------
# Guards on the live suite itself
# ---------------------------------------------------------------------------------------------


class TestLiveSuiteGuards:
    def test_the_engine_repository_is_refused_as_a_live_target(self) -> None:
        with pytest.raises(AssertionError, match="refusing to run a live provider"):
            _refuse_engine_repository(ENGINE_REPOSITORY)
        with pytest.raises(AssertionError, match="refusing to run a live provider"):
            _refuse_engine_repository(ENGINE_REPOSITORY / "agentos_workflow")

    def test_a_disposable_repository_is_never_inside_the_engine_repository(
        self, repository: Path
    ) -> None:
        assert ENGINE_REPOSITORY not in repository.resolve().parents
        assert (repository / ".git").is_dir()

    def test_the_live_allowlist_carries_only_home_and_the_two_store_locations(self) -> None:
        # Each entry is a *location*, never a credential. `HOME` is where both CLIs fall back to;
        # the other two name which store to use instead. No token-shaped variable is ever added.
        assert LIVE_ALLOWED_ENVIRONMENT == ["HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"]
        assert not any(
            name in LIVE_ALLOWED_ENVIRONMENT
            for name in (
                "GITHUB_TOKEN",
                "GH_TOKEN",
                "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY",
                "CODEX_API_KEY",
            )
        )

    def test_the_configured_executables_are_the_real_binaries_never_the_aliases(self) -> None:
        # `codexA`/`claudeA` are shell aliases. With `shell=False` nothing can expand one, so the
        # only usable configuration is the real binary plus an environment selection.
        for alias in ("codexA", "claudeA"):
            assert shutil.which(alias) is None, f"{alias} resolved to an executable unexpectedly"

        config = _live_config(Path("/tmp"), _refuse_engine_repository(Path("/tmp")))
        assert config.claude_cli_executable.name == "claude"
        assert config.codex_cli_executable.name == "codex"

    def test_account_selection_is_environment_only(self) -> None:
        # The whole of "run as account A" is two environment variables. Nothing about it reaches
        # argv, and nothing about it needs a shell.
        assert set(ACCOUNT_ENVIRONMENT) == {"CODEX_HOME", "CLAUDE_CONFIG_DIR"}
        assert set(ACCOUNT_ENVIRONMENT) <= set(LIVE_ALLOWED_ENVIRONMENT)

    def test_no_account_path_is_hard_coded_in_this_suite(self) -> None:
        # Account locations are read from the environment at run time. A literal path here would
        # make the suite silently wrong on any other machine or account.
        source = Path(__file__).read_text()
        for value in (os.environ.get("CODEX_HOME_A"), os.environ.get("CLAUDE_CONFIG_DIR_A")):
            if value:
                assert value not in source

    def test_the_selected_account_reaches_the_provider_environment(
        self, selected_account: None
    ) -> None:
        # Codex's selection is forwarded at session scope, so its effect is directly visible.
        # Claude's deliberately is not -- session-scoped forwarding of the real account directory
        # is exactly the defect `_stage_ephemeral_claude_config_dir` corrects. That per-invocation
        # behaviour is exercised by the tests below instead.
        codex_home = os.environ.get(ACCOUNT_ENVIRONMENT["CODEX_HOME"])
        if codex_home:
            assert os.environ.get("CODEX_HOME") == codex_home

    def test_each_invocation_stages_a_unique_ephemeral_config_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / ".credentials.json").write_text("{}")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))

        root_a = tmp_path / "invocation-a"
        root_b = tmp_path / "invocation-b"
        root_a.mkdir()
        root_b.mkdir()

        staged_a = _stage_ephemeral_claude_config_dir(root_a)
        staged_b = _stage_ephemeral_claude_config_dir(root_b)

        assert staged_a is not None and staged_b is not None
        assert staged_a != staged_b
        assert staged_a.is_relative_to(root_a)
        assert staged_b.is_relative_to(root_b)
        assert staged_a.is_relative_to(tmp_path)
        assert staged_b.is_relative_to(tmp_path)

    def test_the_template_directory_is_never_passed_to_the_provider_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / ".credentials.json").write_text("{}")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

        captured: dict[str, str | None] = {}

        def fake_invoke(self: ProviderRuntime, request: ProviderRunRequest) -> ProviderRunResult:
            captured["config_dir"] = os.environ.get("CLAUDE_CONFIG_DIR")
            now = utc_now()
            return ProviderRunResult(
                provider=ProviderKind.CLAUDE_CLI,
                status=ProviderRunStatus.COMPLETED,
                summary="stub",
                session_id="stub",
                started_at=now,
                completed_at=now,
                exit_code=0,
                stdout_artifact=None,
                stderr_artifact=None,
                assumptions=(),
                blocking_issues=(),
                failure=None,
            )

        monkeypatch.setattr(ProviderRuntime, "invoke", fake_invoke)

        repository = _disposable_repository(tmp_path / "work")
        run_live(
            tmp_path, repository, ProviderRuntimeTarget.CLAUDE, "irrelevant -- invoke is stubbed"
        )

        assert captured["config_dir"] is not None
        assert captured["config_dir"] != str(template)
        assert Path(captured["config_dir"]).is_relative_to(tmp_path)
        # Restored to absent afterward, exactly like every other invocation's own patch.
        assert os.environ.get("CLAUDE_CONFIG_DIR") is None

    def test_the_authentication_template_is_never_mutated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        credentials = template / ".credentials.json"
        credentials.write_text('{"accessToken": "fake-template-token"}')
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))

        before_files = sorted(p.relative_to(template) for p in template.rglob("*"))
        before_hash = hashlib.sha256(credentials.read_bytes()).hexdigest()
        before_size = credentials.stat().st_size
        before_mtime_ns = credentials.stat().st_mtime_ns

        for index in range(3):
            destination = tmp_path / f"invocation-{index}"
            destination.mkdir()
            assert _stage_ephemeral_claude_config_dir(destination) is not None

        after_files = sorted(p.relative_to(template) for p in template.rglob("*"))
        assert after_files == before_files
        assert hashlib.sha256(credentials.read_bytes()).hexdigest() == before_hash
        assert credentials.stat().st_size == before_size
        assert credentials.stat().st_mtime_ns == before_mtime_ns

    def test_only_the_authentication_allowlist_is_copied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / ".credentials.json").write_text("{}")
        (template / ".claude.json").write_text("{}")
        (template / "settings.json").write_text("{}")
        (template / "plans").mkdir()
        (template / "plans" / "leftover-plan.md").write_text("leftover reasoning")
        (template / "projects").mkdir()
        (template / "projects" / "some-project").mkdir()
        (template / "sessions").mkdir()
        (template / "backups").mkdir()
        (template / "backups" / ".claude.json.backup.123").write_text("{}")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))

        destination = tmp_path / "invocation"
        destination.mkdir()
        staged = _stage_ephemeral_claude_config_dir(destination)

        assert staged is not None
        assert {p.name for p in staged.iterdir()} == {".credentials.json"}
        for forbidden in (
            "plans",
            "projects",
            "sessions",
            "backups",
            "settings.json",
            ".claude.json",
        ):
            assert not (staged / forbidden).exists()

    def test_ephemeral_config_directory_permissions_are_locked_down(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / ".credentials.json").write_text("{}")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))

        destination = tmp_path / "invocation"
        destination.mkdir()
        staged = _stage_ephemeral_claude_config_dir(destination)

        assert staged is not None
        assert (staged.stat().st_mode & 0o777) == 0o700
        assert ((staged / ".credentials.json").stat().st_mode & 0o777) == 0o600

    def test_credential_content_never_appears_in_captured_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        secret = "sk-fake-live-test-credential-marker-8f2c"
        (template / ".credentials.json").write_text(json.dumps({"accessToken": secret}))
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))

        destination = tmp_path / "invocation"
        destination.mkdir()
        staged = _stage_ephemeral_claude_config_dir(destination)

        assert staged is not None
        assert json.loads((staged / ".credentials.json").read_text())["accessToken"] == secret

        captured = capsys.readouterr()
        assert secret not in captured.out
        assert secret not in captured.err

    def test_separate_invocations_cannot_observe_each_others_accumulated_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / ".credentials.json").write_text("{}")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_A", str(template))

        root_a = tmp_path / "invocation-a"
        root_b = tmp_path / "invocation-b"
        root_a.mkdir()
        root_b.mkdir()
        staged_a = _stage_ephemeral_claude_config_dir(root_a)
        staged_b = _stage_ephemeral_claude_config_dir(root_b)
        assert staged_a is not None and staged_b is not None

        # What a real session leaves behind in its own disposable copy (plan files, project/
        # transcript continuity) must never appear in a sibling invocation's copy, nor bleed back
        # into the shared template the next invocation copies from.
        (staged_a / "plans").mkdir()
        (staged_a / "plans" / "session-a-reasoning.md").write_text("session A's plan")
        (staged_a / "projects").mkdir()
        (staged_a / "projects" / "session-a-project").mkdir()

        assert not (staged_b / "plans").exists()
        assert not (staged_b / "projects").exists()
        assert not (template / "plans").exists()
        assert not (template / "projects").exists()


@pytest.fixture(autouse=True)
def _no_provider_process_leaks(tmp_path: Path) -> Iterator[None]:
    """After every live test, no process from its session directory may still be running."""
    yield
    sessions = tmp_path / "sessions"
    if not sessions.exists():
        return
    deadline = time.monotonic() + 10.0
    survivors = processes_in_session(sessions)
    while survivors and time.monotonic() < deadline:
        time.sleep(0.2)
        survivors = processes_in_session(sessions)
    assert survivors == [], f"live provider processes leaked: {survivors}"
