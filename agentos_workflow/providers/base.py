"""The common Provider interface and its shared primitives (`MODEL_PROVIDER_CONTRACTS.md` §1).

A Provider wraps exactly one local CLI executable and invokes it as a subprocess with a bounded
timeout. It **never authorizes a workflow**, never decides a machine-gate outcome, and never
invokes a Skill: it returns a structured `ProviderReport` to the calling Agent, which the
Orchestrator's machine gates then verify independently (§1). Nothing in this package imports the
Skill families or the Orchestrator, so "a Provider calls a Skill" is unrepresentable rather than
merely discouraged.

**Never raises.** Exactly like the Skill layer, every failure — including a spawn failure, a
timeout, and malformed CLI output — is returned as a typed `ProviderFailure` inside a
`ProviderResult`. An exception escaping into the Orchestrator would be an untyped control path
its state machine cannot branch on.

**Why this module has its own subprocess and environment primitives** rather than reusing
`agentos_workflow.skills.run_fixed_argv`: a Provider must deliver a prompt to the CLI on
**stdin**, and the Skill primitive deliberately binds stdin to `DEVNULL` so a stray interactive
command gets EOF instead of blocking. Passing a multi-kilobyte prompt through argv instead was
rejected — argv is world-readable in `/proc` and `ps` output on a shared host, and the prompt
carries the stage contract and the implementation diff. The allowlist rule enforced by
`build_provider_environment` is the same rule (`SECURITY_MODEL.md` §1) applied at a second
boundary, not a second policy: the two builders are deliberately independent so that neither
layer's hardening depends on the other's internals.

**Secrets.** No credential is ever constructed, stored, or logged here. The process environment
is built from an explicit allowlist, so an unlisted variable is never forwarded, and every string
this module emits — failure details and captured stdout/stderr alike — is redacted before it can
reach an audit record. The prompt's *content* is deliberately not rewritten: redacting a
implementation diff would corrupt the very artifact the provider exists to act on, and refusing
one that merely looks secret-shaped would block legitimate work on any repository whose tests
mention a password. Keeping secrets out of the prompt is the assembling Agent's obligation
(`MODEL_PROVIDER_CONTRACTS.md` §1, AUTO-005); keeping them out of everything the provider
*emits* is this module's, and is enforced here.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import IO, cast

from agentos_workflow.skills import (
    CommandExecution,
    CommandOutcome,
    RetryClassification,
    redact_secrets,
    utc_now,
)

__all__ = [
    "MAX_PROVIDER_STDERR_BYTES",
    "MAX_PROVIDER_STDOUT_BYTES",
    "PROVEN_PRE_SIDE_EFFECT_RETRY_LIMIT",
    "CLIProvider",
    "Provider",
    "ProviderExecution",
    "ProviderFailure",
    "ProviderFailureKind",
    "ProviderInvocation",
    "ProviderKind",
    "ProviderReport",
    "ProviderResult",
    "ProviderRole",
    "ProviderRunStatus",
    "ProviderVerdict",
    "build_provider_environment",
    "provider_failure",
    "provider_success",
    "run_provider_process",
    "strict_json_loads",
    "unfenced",
]

# `MODEL_PROVIDER_CONTRACTS.md` §2: the retry budget for the *proven* pre-side-effect case only,
# counted independently of the repair-attempt counter (`FAILURE_RECOVERY.md` §1, §1a). It is
# published here because the classification is made here, but the counting is the Orchestrator's:
# a Provider is stateless across invocations and cannot enforce a budget it cannot remember.
PROVEN_PRE_SIDE_EFFECT_RETRY_LIMIT = 3

# A CLI's stdout is untrusted input. Parsing is refused above this size rather than attempted,
# so a runaway process cannot turn a report parse into unbounded memory growth. Matches the
# report-size ceiling the Validation Skills already apply to target-repository artifacts.
MAX_PROVIDER_STDOUT_BYTES = 8 * 1024 * 1024

# stderr is bounded for the same reason and separately, because it is a separate stream with a
# separate failure mode: a CLI that loops printing progress or a stack trace can exhaust memory
# through stderr while stdout stays empty. The ceiling is lower because nothing parses stderr —
# it is diagnostic evidence attached to a failure, never a report (AUTO-010).
MAX_PROVIDER_STDERR_BYTES = 1024 * 1024

# Read size for draining the child's pipes. Small enough that a limit breach is noticed promptly,
# large enough that an ordinary report costs a couple of reads.
_OUTPUT_READ_CHUNK_BYTES = 64 * 1024

# How long a process group gets to honour SIGTERM before SIGKILL follows (AUTO-010).
_TERMINATION_GRACE_SECONDS = 5.0

# How long to wait for the pipe-draining threads to finish once the child is gone. They are
# daemon threads reading pipes that termination has already closed, so this bounds an
# interpreter-level hang rather than a realistic wait.
_STREAM_JOIN_TIMEOUT_SECONDS = 10.0

# An invocation identifier becomes one path segment of the isolated session directory, so it is
# held to a single unambiguous shape. `.` and `..` are excluded by construction rather than by a
# separate check: neither matches a pattern that requires at least one alphanumeric character and
# permits no other punctuation than `-` and `_`.
_INVOCATION_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class ProviderKind(StrEnum):
    """Which CLI a Provider wraps. Also the session-directory segment naming that provider."""

    CLAUDE_CLI = "claude_cli"
    CODEX_CLI = "codex_cli"
    MOCK = "mock"


class ProviderRole(StrEnum):
    """The role an invocation serves (`MODEL_PROVIDER_CONTRACTS.md` §2, §3).

    Roles, not provider names, are what an Agent asks for; the default assignment of role to
    provider (Claude = implementation/repair, Codex = QA) lives in the live selection registry,
    so changing it is one edit in one place rather than a change to every call site.
    """

    IMPLEMENTATION = "implementation"
    REPAIR = "repair"
    QA = "qa"


class ProviderVerdict(StrEnum):
    """The explicit pass/fail a report must carry (`MODEL_PROVIDER_CONTRACTS.md` §3).

    This is the provider's *self-reported* verdict and is never a machine-gate outcome. The
    Orchestrator treats it as evidence to be independently verified (§1).
    """

    PASS = "pass"
    FAIL = "fail"


class ProviderRunStatus(StrEnum):
    """The terminal status every non-interactive provider execution must reach (AUTO-010).

    This is the auto-mode contract's third layer. Layers one and two — the prompt's explicit
    never-ask clauses and the mechanical non-interactivity of the process itself — make a question
    unlikely and unanswerable respectively; this layer makes a question *invalid*. A CLI that
    replies with conversational text instead of one of these four statuses has not produced a
    result at all, and the runtime records a provider contract failure rather than treating the
    text as an outcome.

    It is deliberately a different axis from `ProviderVerdict`, not a replacement for it. The
    verdict answers "did the work pass or fail"; the status answers "how did this execution
    terminate". A `BLOCKED` run has no meaningful pass/fail, and a `COMPLETED` run that reports
    `fail` (a QA provider finding real defects) is a perfectly successful execution.
    """

    COMPLETED = "completed"
    COMPLETED_WITH_ASSUMPTIONS = "completed_with_assumptions"
    BLOCKED = "blocked"
    FAILED = "failed"


class ProviderFailureKind(StrEnum):
    """Why an invocation failed, at a granularity the Orchestrator can branch on."""

    UNSAFE_INPUT = "unsafe_input"
    PRECONDITION = "precondition"
    SPAWN_FAILED = "spawn_failed"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    MALFORMED_OUTPUT = "malformed_output"
    IO_ERROR = "io_error"
    # AUTO-010: the CLI ran, produced a well-formed report, and that report itself declared the
    # execution failed. Distinct from `COMMAND_FAILED` (the process exited non-zero) because the
    # two need different responses: this one carries the provider's own account of what went
    # wrong, and the process exited cleanly.
    PROVIDER_REPORTED = "provider_reported"


@dataclass(frozen=True)
class ProviderFailure:
    """A typed failure. Never an exception crossing the Orchestrator boundary."""

    provider: ProviderKind
    kind: ProviderFailureKind
    detail: str
    retry_classification: RetryClassification = RetryClassification.NON_RETRYABLE
    execution: CommandExecution | None = None

    def __str__(self) -> str:
        return f"{self.provider.value}: {self.kind.value}: {self.detail}"


@dataclass(frozen=True)
class ProviderReport:
    """The structured report a Provider returns to the calling Agent.

    One type serves both provider roles because both are the same thing to the Orchestrator —
    evidence to verify. An implementation/repair report populates `files_changed`,
    `validation_performed`, and `recommended_commit_message` (§2); a QA report populates
    `verdict` and `findings` (§3). Neither is required to fill the other's fields, and no field
    is ever inferred: an absent value stays absent rather than being defaulted into a claim the
    CLI never made.

    **AUTO-010 extension.** `status`, `assumptions`, and `blocking_issues` were added for the
    non-interactive Provider Runtime, which needs to distinguish "finished", "finished only by
    assuming something", "could not safely continue", and "failed" — four outcomes the pass/fail
    `verdict` cannot express, and in particular the difference between a provider that stopped
    safely and one that stopped because it wanted to ask a question. They are the smallest
    extension that expresses the auto-mode contract; all three are optional and default to
    absent/empty, so every report shape AUTO-004 accepted is still accepted unchanged. The full
    unified agent-result schema is AUTO-011's, not this stage's.
    """

    provider: ProviderKind
    role: ProviderRole
    verdict: ProviderVerdict
    summary: str
    files_changed: tuple[str, ...] = ()
    validation_performed: tuple[str, ...] = ()
    recommended_commit_message: str | None = None
    findings: tuple[str, ...] = ()
    execution: CommandExecution | None = None
    status: ProviderRunStatus | None = None
    assumptions: tuple[str, ...] = ()
    blocking_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderResult:
    """A Provider's outcome: exactly one of `value` or `error` is meaningful."""

    ok: bool
    value: ProviderReport | None = None
    error: ProviderFailure | None = None

    def unwrap(self) -> ProviderReport:
        """Return the report, or raise. *Test and caller convenience only* — the Orchestrator
        branches on `ok` and never calls this."""
        if not self.ok or self.value is None:
            raise AssertionError(f"unwrap() on a failed result: {self.error}")
        return self.value


def provider_success(report: ProviderReport) -> ProviderResult:
    return ProviderResult(ok=True, value=report)


def provider_failure(
    provider: ProviderKind,
    kind: ProviderFailureKind,
    detail: str,
    *,
    retry_classification: RetryClassification = RetryClassification.NON_RETRYABLE,
    execution: CommandExecution | None = None,
) -> ProviderResult:
    """Build a failed result. `detail` is redacted before it is ever stored or surfaced."""
    return ProviderResult(
        ok=False,
        error=ProviderFailure(
            provider=provider,
            kind=kind,
            detail=redact_secrets(detail),
            retry_classification=retry_classification,
            execution=execution,
        ),
    )


@dataclass(frozen=True)
class ProviderExecution:
    """One CLI invocation's audit record, plus the stdout the parser reads.

    The two are deliberately separate. `execution` is the `AUDIT_MODEL.md` §2 record and holds
    **redacted** output, because that is what gets stored and surfaced. `raw_stdout` is the
    unredacted text and exists only long enough to be parsed, is never stored, never logged, and
    never reaches a report field: `_report_from_payload` redacts every value it extracts.

    Parsing the redacted text instead was the obvious design and is wrong. Redaction rewrites
    arbitrary spans of a byte stream, so applying it *before* `json.loads` can consume a
    structural character — a finding reading `password = hunter2` is replaced by a marker that
    swallows the closing quote, and a perfectly valid report becomes `MALFORMED_OUTPUT`. That
    fails in the worst direction: the reports most likely to be destroyed are exactly the QA
    findings that mention a credential, which are the ones an operator most needs to see. Parsing
    first and redacting each extracted value preserves both properties at once — the structure
    survives, and nothing unredacted ever leaves this module.

    The two limit flags record that a stream was cut off at its ceiling rather than ending on its
    own. They are separate from the captured text because the text is still usable evidence: what
    was read before the ceiling is kept, and only the claim that it is *complete* is withdrawn.
    """

    execution: CommandExecution
    raw_stdout: str
    stdout_limit_exceeded: bool = False
    stderr_limit_exceeded: bool = False


@dataclass(frozen=True)
class ProviderInvocation:
    """Everything one invocation needs. Assembled by the Orchestrator/Agents, never by a Provider.

    `session_root` plus `invocation_id` give this invocation its own scratch directory
    (`MODEL_PROVIDER_CONTRACTS.md` §5). The identifier is supplied rather than generated so the
    Orchestrator owns the audit trail's identity and a test can be deterministic; it is validated
    as a single safe path segment before it is ever joined to a path.

    `stage_id` is carried, not consumed here: a Provider never reads a stage contract or decides
    anything from it (§1). It travels with the invocation so the Agent layer (AUTO-005) that
    assembles the prompt and the Orchestrator that records the result are working from one
    record. It is deliberately kept out of `normalized_command_identity`, which is built only from
    values this module validates — an unvalidated caller string embedded in an audit identity is a
    log-injection surface for no benefit.
    """

    workflow_id: str
    stage_id: str
    role: ProviderRole
    prompt: str
    working_directory: Path
    session_root: Path
    invocation_id: str


def build_provider_environment(
    allowed_environment_variables: tuple[str, ...],
    *,
    session_directory: Path | None = None,
) -> dict[str, str]:
    """Build a Provider subprocess environment from an explicit allowlist
    (`SECURITY_MODEL.md` §1).

    Only `PATH` is unconditional, because a fixed-argv command still has to be found; every other
    *inherited* variable must be named in the target repository's
    `allowed_environment_variables`. `LC_ALL`/`LANG` are pinned to `C` so output is parseable and
    identical across operator locales.

    Note what is deliberately *not* here: `HOME`. A CLI that needs its own configuration or
    credential store must have `HOME` named in the allowlist by the target repository's operator,
    as a visible, auditable configuration act. Forwarding it implicitly "because the CLI probably
    needs it" would silently hand every provider process the operator's entire credential
    directory — precisely the leak the allowlist exists to prevent.

    When a `session_directory` is given, `TMPDIR` is pointed at it and it is published as
    `AGENTOS_SESSION_DIRECTORY`. That is what makes the per-invocation directory an actual
    isolation boundary rather than an empty directory nothing uses
    (`MODEL_PROVIDER_CONTRACTS.md` §5, "separate working-state directories where the provider
    needs scratch space"): whatever scratch the CLI writes lands inside its own invocation's
    directory instead of a shared `/tmp` where the implementation and QA sessions could observe,
    collide with, or overwrite each other's files.

    These three are *engine-set* values, not inherited ones, so they do not weaken the allowlist:
    none of them carries anything from the operator's environment, and each is overwritten
    unconditionally — an allowlisted `TMPDIR` cannot be used to redirect a provider's scratch back
    out of its session directory.
    """
    environment = {
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": os.environ.get("PATH", ""),
    }
    for name in allowed_environment_variables:
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    if session_directory is not None:
        environment["TMPDIR"] = str(session_directory)
        environment["AGENTOS_SESSION_DIRECTORY"] = str(session_directory)
    return environment


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """`object_pairs_hook` that refuses an object naming the same key twice (AUTO-010).

    `json.loads` silently keeps the last of a repeated key. For a *report* that is unacceptable:
    two different values for `verdict` or `blocking_issues` is not a report with a winner, it is
    an ambiguous document, and quietly choosing one is how a second value hides behind a first.
    """
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r} in provider JSON output")
        seen.add(key)
    return dict(pairs)


def strict_json_loads(text: str) -> object:
    """`json.loads` with duplicate object keys rejected.

    The only JSON entry point in this package, so no adapter can parse provider output leniently.
    """
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def unfenced(text: str) -> str:
    """Strip a Markdown code fence wrapping a model's whole final answer, if present.

    The prompt contract asks for a bare JSON object and says so explicitly, but a fenced block is
    the single most common way a language model complies-but-not-quite, and failing an otherwise
    perfect report over three backticks would reject the run for a formatting habit rather than for
    anything about the work. Only a fence wrapping the *entire* answer is removed, nothing inside
    it is rewritten, and text that is not fenced is returned byte-for-byte — so this cannot turn
    malformed output into something that parses by accident.
    """
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```") or len(stripped) < 6:
        return text
    body = stripped[3:-3]
    newline = body.find("\n")
    if newline == -1:
        return text
    # Drop the info string (```json) on the opening line; keep everything after it verbatim.
    return body[newline + 1 :]


def _decode(raw: bytes | str | None) -> str:
    """Decode CLI output without ever failing on invalid UTF-8.

    A model CLI's output is not required to be valid UTF-8, and a `UnicodeDecodeError` escaping
    here would violate this module's never-raise contract.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")


class _BoundedStreamReader(threading.Thread):
    """Drain one of the child's pipes, keeping at most `limit` bytes (AUTO-010).

    Draining has to happen concurrently with the wait: a pipe holds only a page or two, so a CLI
    that writes more than that while nothing reads blocks forever, and the timeout that was
    supposed to bound the run would be measuring a deadlock this module created.

    Past the ceiling the thread keeps reading and stops keeping. Stopping the *reads* would
    reintroduce exactly that deadlock; discarding what was already read would throw away the
    diagnostic evidence. `on_limit_exceeded` fires once, on the transition, so the caller can
    reclaim a process that has started producing output without end.
    """

    def __init__(self, stream: IO[bytes], limit: int, on_limit_exceeded: Callable[[], None]):
        super().__init__(daemon=True)
        self._stream = stream
        self._limit = limit
        self._on_limit_exceeded = on_limit_exceeded
        self._chunks: list[bytes] = []
        self._kept = 0
        self.limit_exceeded = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(_OUTPUT_READ_CHUNK_BYTES)
                if not chunk:
                    break
                if self.limit_exceeded:
                    continue
                self._kept += len(chunk)
                self._chunks.append(chunk)
                if self._kept > self._limit:
                    self.limit_exceeded = True
                    self._on_limit_exceeded()
        except (OSError, ValueError):
            # The pipe was closed under us — normally by the process-group termination this
            # module just performed. Not an error: whatever was captured before the kill is still
            # the honest record of what the CLI emitted.
            pass
        finally:
            with suppress(OSError, ValueError):
                self._stream.close()

    @property
    def data(self) -> bytes:
        """What was captured, truncated to the ceiling this reader was given."""
        return b"".join(self._chunks)[: self._limit]


def _send_prompt(stdin: IO[bytes], payload: bytes) -> None:
    """Write the one and only prompt, then close stdin (`AUTO-010` never-ask layer 2).

    Closing is the mechanical half of the never-ask rule: after this, the CLI's stdin is at EOF,
    so a provider that decides to ask a question receives an immediate end-of-input rather than
    waiting for an answer that no one is there to give. It happens in a thread because a prompt
    larger than the pipe buffer would otherwise block the writer before the readers start.

    A `BrokenPipeError` here is an ordinary outcome, not a failure: a CLI is entitled to exit
    without reading its input, and the exit code already records that it did.
    """
    try:
        stdin.write(payload)
        stdin.flush()
    except (OSError, ValueError):
        pass
    finally:
        with suppress(OSError, ValueError):
            stdin.close()


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """SIGTERM then SIGKILL the child's whole *process group*, never just the child (AUTO-010).

    Killing only the direct child is what `subprocess.run(timeout=...)` does, and it is not enough
    here. A model CLI spawns subprocesses — a test run, a language server, a sandbox helper — and
    those are children of the child. Terminating the CLI alone leaves them running, reparented and
    unowned, after the timeout whose entire purpose was to reclaim them. `start_new_session=True`
    at spawn puts the CLI in its own process group precisely so this call can reach all of them
    with one signal and no PID bookkeeping.

    The SIGKILL is unconditional rather than conditional on the child surviving SIGTERM: the
    direct child exiting politely says nothing about whether its grandchildren did, and those are
    exactly what a bounded timeout has to reclaim. Signalling an already-empty group is a no-op.

    POSIX-only, like `start_new_session` itself — the same runtime boundary the rest of this
    engine already documents.
    """
    try:
        process_group_id = os.getpgid(process.pid)
    except OSError:
        # Already reaped, or no permission to ask. Fall back to the child alone: there is no
        # group id to signal, and leaving the child running would be worse than an imperfect kill.
        with suppress(OSError):
            process.kill()
        return
    with suppress(OSError):
        os.killpg(process_group_id, signal.SIGTERM)
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=_TERMINATION_GRACE_SECONDS)
    with suppress(OSError):
        os.killpg(process_group_id, signal.SIGKILL)


def run_provider_process(
    argv: tuple[str, ...],
    *,
    identity: str,
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
    allowed_environment_variables: tuple[str, ...] = (),
    session_directory: Path | None = None,
) -> ProviderExecution:
    """Run one fixed-argv CLI invocation with `prompt` on stdin, and return its audit record.

    `argv` is a real argument vector assembled from a provider-owned constant plus the configured
    executable path — never a caller-supplied command string and never a shell. There is no
    `shell=True` path in this package, so metacharacters in a configured executable path are
    inert data rather than executable syntax.

    Like the Skill layer's equivalent, this raises nothing: a non-zero exit, a timeout, and a
    spawn failure are all ordinary outcomes recorded in the returned `CommandExecution`, so the
    audit trail has no gaps. `normalized_command_identity` is a provider/role shape, never raw
    argv, because argv is written to the audit log and a configured path can itself be sensitive.

    **Why `Popen` rather than `subprocess.run` (AUTO-010).** Three of this stage's guarantees are
    unreachable through `run`: it kills only the direct child on timeout (see
    `_terminate_process_group`), it buffers both streams without limit (see
    `_BoundedStreamReader`), and it offers no way to put the child in its own session. That last
    one matters most for the never-ask rule — `start_new_session=True` detaches the child from
    this process's controlling terminal, so a CLI that tries to open `/dev/tty` to prompt a human
    finds no terminal to open rather than finding the operator's.
    """
    start_time = utc_now()
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env=build_provider_environment(
                allowed_environment_variables, session_directory=session_directory
            ),
            # No TTY is allocated and the child gets its own session, so it has no controlling
            # terminal at all: it cannot prompt, and its whole group is killable as one unit.
            start_new_session=True,
        )
    except OSError as exc:
        # The executable could not be spawned at all — the one case `MODEL_PROVIDER_CONTRACTS.md`
        # §2 accepts as *proven* pre-side-effect, because the CLI never ran and therefore cannot
        # have written anything to the stage branch.
        return ProviderExecution(
            execution=CommandExecution(
                normalized_command_identity=identity,
                start_time=start_time,
                completion_time=utc_now(),
                exit_code=None,
                timeout_status=False,
                outcome=CommandOutcome.SPAWN_FAILED,
                stdout="",
                stderr=redact_secrets(str(exc)),
            ),
            raw_stdout="",
        )

    # `stdin`/`stdout`/`stderr` are `PIPE` above, so all three are present. The casts state that
    # rather than asserting it: an `assert` would be a raise inside a never-raise module, and a
    # runtime branch would be unreachable code pretending to be a real failure path.
    stdout_reader = _BoundedStreamReader(
        cast(IO[bytes], process.stdout),
        MAX_PROVIDER_STDOUT_BYTES,
        lambda: _terminate_process_group(process),
    )
    stderr_reader = _BoundedStreamReader(
        cast(IO[bytes], process.stderr),
        MAX_PROVIDER_STDERR_BYTES,
        lambda: _terminate_process_group(process),
    )
    writer = threading.Thread(
        target=_send_prompt,
        args=(cast(IO[bytes], process.stdin), prompt.encode("utf-8")),
        daemon=True,
    )
    stdout_reader.start()
    stderr_reader.start()
    writer.start()

    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=_TERMINATION_GRACE_SECONDS)

    writer.join(timeout=_STREAM_JOIN_TIMEOUT_SECONDS)
    stdout_reader.join(timeout=_STREAM_JOIN_TIMEOUT_SECONDS)
    stderr_reader.join(timeout=_STREAM_JOIN_TIMEOUT_SECONDS)

    raw_stdout = _decode(stdout_reader.data)
    return ProviderExecution(
        execution=CommandExecution(
            normalized_command_identity=identity,
            start_time=start_time,
            completion_time=utc_now(),
            # A timed-out run reports no exit code even though termination produced one: the
            # signal number this module chose is not the CLI's answer, and recording it as one
            # would put a fabricated result in the audit trail.
            exit_code=None if timed_out else process.returncode,
            timeout_status=timed_out,
            outcome=CommandOutcome.TIMED_OUT if timed_out else CommandOutcome.COMPLETED,
            stdout=redact_secrets(raw_stdout),
            stderr=redact_secrets(_decode(stderr_reader.data)),
        ),
        raw_stdout=raw_stdout,
        stdout_limit_exceeded=stdout_reader.limit_exceeded,
        stderr_limit_exceeded=stderr_reader.limit_exceeded,
    )


class Provider(ABC):
    """The abstract interface every Provider implements (`MODEL_PROVIDER_CONTRACTS.md` §1).

    The interface is exactly `invoke(context) -> ProviderReport`-shaped, which is what makes
    `MockProvider` a drop-in substitute for either CLI provider in tests: a caller typed against
    `Provider` cannot tell them apart, and none of them can widen the contract, because there is
    nothing else to call.
    """

    @property
    @abstractmethod
    def kind(self) -> ProviderKind:
        """Which CLI this Provider wraps."""

    @abstractmethod
    def invoke(self, invocation: ProviderInvocation) -> ProviderResult:
        """Run one isolated invocation. Never raises; every failure is a typed result."""


class CLIProvider(Provider):
    """A Provider backed by a real local CLI executable (`MODEL_PROVIDER_CONTRACTS.md` §2, §3).

    This class is the type boundary that keeps `MockProvider` out of live workflows. Live
    provider selection is typed to return a `CLIProvider`; `MockProvider` subclasses `Provider`
    directly and is therefore not merely absent from the live registry but *type-impossible* to
    return from it (`MVP_SCOPE.md` §3).

    Subclasses supply only their CLI's identity and argv shape. The invocation sequence — validate,
    isolate, run, classify, parse — lives here once, so the two CLI providers cannot drift apart
    in how they enforce the timeout, the environment allowlist, or session isolation.
    """

    #: The fixed argument vector appended to the configured executable. A provider-owned constant,
    #: never caller-supplied, so no call site can inject a flag.
    _ARGV_SUFFIX: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        executable: Path,
        timeout_seconds: int,
        allowed_environment_variables: tuple[str, ...] = (),
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._allowed_environment_variables = allowed_environment_variables

    @property
    def executable(self) -> Path:
        return self._executable

    @property
    def timeout_seconds(self) -> int:
        return self._timeout_seconds

    @property
    def allowed_environment_variables(self) -> tuple[str, ...]:
        return self._allowed_environment_variables

    def invoke(self, invocation: ProviderInvocation) -> ProviderResult:
        """Run one isolated CLI invocation and return its structured report."""
        precondition = self._validate(invocation)
        if precondition is not None:
            return precondition

        session_directory = self.session_directory(invocation)
        try:
            # `0o700`: the CLI's scratch (and its `TMPDIR`) lands here, so on a shared host no
            # other local user may read what an implementation or QA session wrote.
            session_directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        except FileExistsError:
            # A reused invocation id would let two invocations share scratch space, which is
            # exactly the isolation §5 forbids. `exist_ok=False` makes the collision visible
            # instead of silently merging the two sessions.
            return provider_failure(
                self.kind,
                ProviderFailureKind.PRECONDITION,
                f"session directory already exists for invocation id {invocation.invocation_id!r}",
            )
        except OSError as exc:
            return provider_failure(self.kind, ProviderFailureKind.IO_ERROR, str(exc))

        execution = run_provider_process(
            self.argv(session_directory),
            identity=self._identity(invocation),
            prompt=invocation.prompt,
            cwd=invocation.working_directory,
            timeout_seconds=self._timeout_seconds,
            allowed_environment_variables=self._allowed_environment_variables,
            session_directory=session_directory,
        )
        return self._interpret(invocation, execution, session_directory)

    def argv(self, session_directory: Path) -> tuple[str, ...]:
        """The exact argument vector this provider will execute.

        Public so that a test — and the completion report's argv evidence — can assert the real
        vector without reaching into the class or spawning anything. It stays impossible for a
        *caller* to influence it: every element comes from the configured executable, this
        provider's own closed constants and enums, and the engine-owned session directory.
        """
        return (str(self._executable), *self._argv_suffix(session_directory))

    def _argv_suffix(self, session_directory: Path) -> tuple[str, ...]:
        """The flags appended to the executable. Overridden by adapters whose flags depend on a
        configured mode or on this invocation's own session directory (AUTO-010)."""
        return self._ARGV_SUFFIX

    def _identity(self, invocation: ProviderInvocation) -> str:
        """The audit identity: provider and role shape only, never argv and never the prompt."""
        return f"{self.kind.value}:{invocation.role.value}"

    def session_directory(self, invocation: ProviderInvocation) -> Path:
        """This invocation's own scratch directory (`MODEL_PROVIDER_CONTRACTS.md` §5).

        Keyed by workflow, then provider, then invocation: two providers in the same workflow can
        never be handed the same directory, and neither can two invocations of the same provider.

        Public since AUTO-010 so the Provider Runtime can persist this invocation's stdout and
        stderr artifacts into the same isolated directory the process itself was given, without
        either layer having to re-derive the layout the other owns.
        """
        return (
            invocation.session_root
            / invocation.workflow_id
            / self.kind.value
            / invocation.invocation_id
        )

    def _validate(self, invocation: ProviderInvocation) -> ProviderResult | None:
        """Refuse an unsafe or incomplete invocation before any process is spawned."""
        if not _INVOCATION_ID_RE.match(invocation.invocation_id):
            return provider_failure(
                self.kind,
                ProviderFailureKind.UNSAFE_INPUT,
                f"invocation_id is not a single safe path segment: {invocation.invocation_id!r}",
            )
        if not _INVOCATION_ID_RE.match(invocation.workflow_id):
            return provider_failure(
                self.kind,
                ProviderFailureKind.UNSAFE_INPUT,
                f"workflow_id is not a single safe path segment: {invocation.workflow_id!r}",
            )
        if not invocation.prompt.strip():
            return provider_failure(
                self.kind,
                ProviderFailureKind.UNSAFE_INPUT,
                "prompt is empty",
            )
        if not invocation.session_root.is_absolute():
            return provider_failure(
                self.kind,
                ProviderFailureKind.PRECONDITION,
                f"session_root must be an absolute path: {invocation.session_root}",
            )
        if not invocation.working_directory.is_dir():
            return provider_failure(
                self.kind,
                ProviderFailureKind.PRECONDITION,
                f"working_directory is not a directory: {invocation.working_directory}",
            )
        return None

    def _interpret(
        self,
        invocation: ProviderInvocation,
        ran: ProviderExecution,
        session_directory: Path,
    ) -> ProviderResult:
        """Turn one command execution into a report or a classified failure.

        The retry classification follows `MODEL_PROVIDER_CONTRACTS.md` §2 exactly: the question is
        *when* the failure happened, never what kind it was. A timeout is not evidence the CLI
        wrote nothing — it may already have written a partial or complete diff — so it is
        `POSSIBLE_SIDE_EFFECT` and never eligible for a blind retry, while a spawn failure is the
        one provably pre-effect case.
        """
        execution = ran.execution
        if execution.outcome is CommandOutcome.SPAWN_FAILED:
            return provider_failure(
                self.kind,
                ProviderFailureKind.SPAWN_FAILED,
                f"could not spawn {self._executable}: {execution.stderr}",
                retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
                execution=execution,
            )
        if execution.outcome is CommandOutcome.TIMED_OUT:
            return provider_failure(
                self.kind,
                ProviderFailureKind.TIMEOUT,
                f"{self.kind.value} exceeded its {self._timeout_seconds}s timeout",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        # Checked before the exit code, because exceeding a limit is *why* the process exited the
        # way it did: this module killed its group. Reporting the resulting signal as a CLI
        # failure would describe the symptom and hide the cause.
        if ran.stdout_limit_exceeded:
            return provider_failure(
                self.kind,
                ProviderFailureKind.MALFORMED_OUTPUT,
                f"stdout exceeds {MAX_PROVIDER_STDOUT_BYTES} bytes",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        if ran.stderr_limit_exceeded:
            return provider_failure(
                self.kind,
                ProviderFailureKind.MALFORMED_OUTPUT,
                f"stderr exceeds {MAX_PROVIDER_STDERR_BYTES} bytes",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        if execution.exit_code != 0:
            return provider_failure(
                self.kind,
                ProviderFailureKind.COMMAND_FAILED,
                f"{self.kind.value} exited {execution.exit_code}: {execution.stderr}",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        return self._parse_report(invocation, ran, session_directory)

    def _parse_report(
        self,
        invocation: ProviderInvocation,
        ran: ProviderExecution,
        session_directory: Path,
    ) -> ProviderResult:
        """Parse the CLI's stdout into a `ProviderReport`.

        Reads `raw_stdout`, never the redacted copy, so redaction cannot corrupt the JSON
        structure; every value extracted is redacted individually on the way into the report. A
        clean exit with unparseable output is `POSSIBLE_SIDE_EFFECT`, not a clean failure: the CLI
        ran to completion and may well have written a diff before emitting output this adapter
        could not read.
        """
        execution = ran.execution
        if len(ran.raw_stdout.encode("utf-8")) > MAX_PROVIDER_STDOUT_BYTES:
            return provider_failure(
                self.kind,
                ProviderFailureKind.MALFORMED_OUTPUT,
                f"stdout exceeds {MAX_PROVIDER_STDOUT_BYTES} bytes",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        try:
            payload = self._extract_report_payload(ran.raw_stdout, session_directory)
        except (json.JSONDecodeError, ValueError, TypeError, OSError) as exc:
            return provider_failure(
                self.kind,
                ProviderFailureKind.MALFORMED_OUTPUT,
                f"could not read a report from stdout: {exc}",
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        try:
            report = _report_from_payload(payload, self.kind, invocation.role, execution)
        except ValueError as exc:
            return provider_failure(
                self.kind,
                ProviderFailureKind.MALFORMED_OUTPUT,
                str(exc),
                retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                execution=execution,
            )
        return provider_success(report)

    def _extract_report_payload(self, stdout: str, session_directory: Path) -> object:
        """Pull the report object out of this CLI's stdout.

        The default is the stdout/stderr protocol this stage defines: stdout is exactly one JSON
        object matching the report schema. A CLI that wraps its answer in an envelope overrides
        this hook rather than the whole parse path, so envelope handling never leaks into the
        shared schema validation below.

        `session_directory` is passed because one real CLI delivers its final message to a file
        this engine names rather than to stdout (see `codex_cli`); an adapter that does not need
        it ignores it.
        """
        return strict_json_loads(stdout)


def _report_from_payload(
    payload: object,
    provider: ProviderKind,
    role: ProviderRole,
    execution: CommandExecution | None,
) -> ProviderReport:
    """Validate a decoded payload against the report schema.

    Strict on purpose: a report is *evidence* the Orchestrator's gates will act on, so a missing
    verdict is an error rather than an assumed pass, and a field of the wrong type is an error
    rather than a coerced value. Silently defaulting either would manufacture a claim the CLI
    never made.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"report must be a JSON object, got {type(payload).__name__}")

    raw_verdict = payload.get("verdict")
    if not isinstance(raw_verdict, str):
        raise ValueError("report is missing a string 'verdict'")
    try:
        verdict = ProviderVerdict(raw_verdict)
    except ValueError:
        raise ValueError(
            f"report 'verdict' must be 'pass' or 'fail', got {raw_verdict!r}"
        ) from None

    summary = payload.get("summary")
    if not isinstance(summary, str):
        raise ValueError("report is missing a string 'summary'")

    commit_message = payload.get("recommended_commit_message")
    if commit_message is not None and not isinstance(commit_message, str):
        raise ValueError("report 'recommended_commit_message' must be a string when present")

    status = _run_status(payload)
    assumptions = _string_tuple(payload, "assumptions")
    blocking_issues = _string_tuple(payload, "blocking_issues")

    # AUTO-010 layer 3: the two statuses that make a claim about *why* the run ended must carry
    # the evidence for that claim. A `blocked` report with no blocking issue is the exact shape a
    # provider produces when it wanted to ask a question and dressed the question as a status, and
    # a `completed_with_assumptions` report with no assumption is an unrecorded assumption. Both
    # are rejected as malformed rather than accepted as outcomes.
    if status is ProviderRunStatus.BLOCKED and not blocking_issues:
        raise ValueError("report status 'blocked' requires at least one 'blocking_issues' entry")
    if status is ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS and not assumptions:
        raise ValueError(
            "report status 'completed_with_assumptions' requires at least one "
            "'assumptions' entry"
        )

    return ProviderReport(
        provider=provider,
        role=role,
        verdict=verdict,
        summary=redact_secrets(summary),
        files_changed=_string_tuple(payload, "files_changed"),
        validation_performed=_string_tuple(payload, "validation_performed"),
        recommended_commit_message=(
            None if commit_message is None else redact_secrets(commit_message)
        ),
        findings=_string_tuple(payload, "findings"),
        execution=execution,
        status=status,
        assumptions=assumptions,
        blocking_issues=blocking_issues,
    )


def _run_status(payload: dict[str, object]) -> ProviderRunStatus | None:
    """Read the optional auto-mode terminal status (AUTO-010).

    Optional at *this* layer and required at the runtime's: a report carrying no status is still a
    valid AUTO-004 report, which is why parsing does not reject it here, but the Provider Runtime
    demands one because an execution with no terminal status has not satisfied the auto-mode
    contract. An unrecognized status string is always an error — never coerced, and never treated
    as absent, since the difference between "said nothing" and "said something this engine does
    not understand" is exactly the difference a strict parser exists to preserve.
    """
    raw = payload.get("status")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("report 'status' must be a string when present")
    try:
        return ProviderRunStatus(raw)
    except ValueError:
        permitted = ", ".join(repr(member.value) for member in ProviderRunStatus)
        raise ValueError(f"report 'status' must be one of {permitted}, got {raw!r}") from None


def _string_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    """Read an optional list-of-strings field, redacting each entry."""
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        raise ValueError(f"report {key!r} must be a list of strings")
    return tuple(redact_secrets(entry) for entry in value)
