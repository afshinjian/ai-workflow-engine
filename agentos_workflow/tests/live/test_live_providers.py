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

import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
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


@pytest.fixture(scope="session", autouse=True)
def selected_account() -> Iterator[None]:
    """Point this session's provider runs at the configured account's credential stores.

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

    Session-scoped and autouse so the availability probes see it too; values are read from the
    environment at run time, so no account path appears in this file.
    """
    patcher = pytest.MonkeyPatch()
    for target, source in ACCOUNT_ENVIRONMENT.items():
        value = os.environ.get(source)
        if value:
            patcher.setenv(target, value)
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
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        result = run_live(tmp_path, repository, ProviderRuntimeTarget.CLAUDE, READ_ONLY_TASK)

        assert result.provider is ProviderKind.CLAUDE_CLI
        assert result.status in {
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS,
        }
        assert result.exit_code == 0
        assert result.report is not None
        assert result.summary.strip()

    def test_the_prompt_arrives_through_stdin(
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        # A token that exists only in the prompt, echoed back: proof the process received the
        # prompt this engine sent, on the channel it sent it.
        token = "AUTO010-STDIN-TOKEN-7f3a"
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CLAUDE,
            f"Put exactly the token {token} in your summary field and do nothing else.",
        )
        assert result.status is not ProviderRunStatus.FAILED
        assert token in result.summary

    def test_planning_mode_writes_nothing(
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        before = repository_state(repository)
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CLAUDE,
            WRITE_ONE_FILE_TASK,
            permission_mode="plan",
        )
        assert result.status in set(ProviderRunStatus)
        assert repository_state(repository) == before
        assert not (repository / "auto-010-live.txt").exists()

    def test_write_enabled_mode_writes_exactly_the_one_allowed_file(
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        before = repository_state(repository)
        result = run_live(
            tmp_path,
            repository,
            ProviderRuntimeTarget.CLAUDE,
            WRITE_ONE_FILE_TASK,
            permission_mode="acceptEdits",
        )
        assert result.status is not ProviderRunStatus.FAILED

        after = repository_state(repository)
        created = set(after) - set(before)
        modified = {name for name in set(after) & set(before) if after[name] != before[name]}

        assert created == {"auto-010-live.txt"}
        assert modified == set()
        assert (repository / "auto-010-live.txt").read_text().strip() == "auto-010"

    def test_an_ambiguous_task_terminates_rather_than_waiting(
        self, claude_available: None, tmp_path: Path, repository: Path
    ) -> None:
        assert_terminates_rather_than_waiting(tmp_path, repository, ProviderRuntimeTarget.CLAUDE)

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
        # The selection actually took effect in this process, which is what the allowlist then
        # forwards. Only presence is asserted -- the value is a filesystem location and is not
        # echoed into the assertion message.
        for target, source in ACCOUNT_ENVIRONMENT.items():
            if os.environ.get(source):
                assert os.environ.get(target) == os.environ[source]


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
