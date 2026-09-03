"""Engine-executed verification bundles (Milestone 3, task T-307).

Executes configured verification bundles against a disposable clone of one exact target HEAD, so
a read-only reviewer receives verification evidence the engine produced itself rather than
claims it cannot check. Every command runs inside the clone and nowhere else; the target
repository is never written.

What is captured per command is deliberately narrow: the bundle name, the global execution
index, the exact argv, the observed exit code, and whether it timed out. **stdout and stderr are
not captured at all** — they are routed to ``/dev/null`` rather than collected and discarded, so
command output cannot reach governed evidence even accidentally. Exit codes and argv are the
contracted observation, and command output may carry secrets while adding nothing the reviewer
needs.

A non-zero exit code is *evidence*, not an engine error: this module never raises because a
command failed. Only infrastructure failures propagate, and the sandbox is torn down
unconditionally either way.

The process-group timeout discipline here duplicates the runner's rather than importing it:
``agents.runner`` imports the prompt package, which consumes this module, so importing it back
would create a cycle. This module therefore depends only on ``agents.sandbox`` (which imports
only ``exceptions``) and on the configuration models.
"""

import os
import signal
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_workflow_engine.agents.sandbox import create_sandbox, teardown
from ai_workflow_engine.models import VerificationBundleSettings

# The exact environment a bundle command sees. Pinned as a tuple, and asserted by equality in the
# tests, because "which ambient variables leak into governed verification" is a property of the
# evidence, not an implementation detail. `TMPDIR` is deliberately absent: adding an ambient
# passthrough would reintroduce exactly the environment dependence this module removes.
SCRUBBED_KEYS: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL")

# Exit codes for outcomes the executed process never got to report itself. Identical to the
# runner's long-standing mapping, so both executors describe the same outcome the same way.
TIMEOUT_EXIT_CODE = 124
NOT_EXECUTABLE_EXIT_CODE = 127


@dataclass(frozen=True)
class BundleCommandObservation:
    """One executed verification command. Carries no captured output, by design."""

    bundle: str
    index: int
    argv: list[str]
    exit_code: int
    timed_out: bool


def _scrubbed_env() -> dict[str, str]:
    return {key: os.environ[key] for key in SCRUBBED_KEYS if key in os.environ}


def _run_with_group_timeout(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> tuple[int | None, bool]:
    """Run a command in its own session, killing the whole group on timeout.

    Returns ``(returncode, timed_out)``. A timed-out process group is SIGKILLed and reaped so no
    verification grandchildren are orphaned.
    """
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:  # pragma: no cover - race: already exited
            pass
        process.wait()
    return process.returncode, timed_out


def _execute_command(
    argv: Sequence[str], *, bundle: str, index: int, sandbox: Path, timeout: int
) -> BundleCommandObservation:
    command = list(argv)
    try:
        returncode, timed_out = _run_with_group_timeout(
            command, cwd=sandbox, env=_scrubbed_env(), timeout=timeout
        )
    except OSError:
        # The command could not be executed at all (absent, not executable, bad interpreter).
        exit_code, timed_out = NOT_EXECUTABLE_EXIT_CODE, False
    else:
        exit_code = (
            TIMEOUT_EXIT_CODE if timed_out else (returncode if returncode is not None else 1)
        )
    return BundleCommandObservation(
        bundle=bundle, index=index, argv=command, exit_code=exit_code, timed_out=timed_out
    )


def run_verification_bundles(
    *,
    repository: Path,
    repository_head: str,
    bundles: Sequence[VerificationBundleSettings],
) -> list[BundleCommandObservation]:
    """Run every command of every selected bundle in one clone of ``repository_head``.

    ``bundles`` is the caller's selection order, which is the execution order; observations carry
    a single global 0-based ``index`` across all bundles so the recorded order is unambiguous.
    """
    sandbox = create_sandbox(repository, repository_head)
    try:
        observations: list[BundleCommandObservation] = []
        for bundle in bundles:
            for argv in bundle.commands:
                observations.append(
                    _execute_command(
                        argv,
                        bundle=bundle.name,
                        index=len(observations),
                        sandbox=sandbox,
                        timeout=bundle.timeout_seconds,
                    )
                )
        return observations
    finally:
        teardown(sandbox)
