"""The shared provider subprocess discipline: one process, one prompt, one durable record.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 8 (the
four-file `providers/` subpackage), section 17 (the provider boundary and DEC-016-002's ruling),
section 17a (sanitization before persistence), section 10 (`PROVIDER_WAIT` and
`PROVIDER_RETRY_PENDING`), section 22 invariants 1, 3, 5, 6, 14, 17 and 20, and section 6 defect
P-10.

What DEC-016-002 fixed, and what this module therefore is
--------------------------------------------------------
The Human Owner ruled that provider adapters are owned by this package and that the
`agentos_workflow` provider runtime is **not** reused directly. The ruling is binding and the
alternative is closed. Nothing here imports `agentos_workflow`; no code was copied from it. What
was adopted is its documented discipline, verbatim as section 17 lists it: a fixed argv built from
a provider-owned constant, no shell, `Popen` with process-group termination on timeout, bounded
stream readers, environment allowlisting, and a normalized command identity in the record. The
honest cost -- a second subprocess implementation in the tree -- is the cost the ruling accepted.

Five properties are structural rather than checked somewhere downstream
----------------------------------------------------------------------
* **The prompt cannot reach argv.** :class:`ProviderRequest` refuses a vector that contains the
  prompt, and :func:`run_provider_process` re-checks before it spawns. The prompt travels on the
  child's stdin, so it never appears in a process listing (section 17).
* **There is no default timeout.** `timeout_seconds` is a required field with no default here and
  no default in `config.ProviderSettings`; a configuration that omits it fails at load. No call
  site can supply one either, because every parameter that carries it is keyword-only and required.
* **Classification turns on when the failure occurred.** :func:`classify_invocation_failure` takes
  an :class:`InvocationPhase` and nothing else -- no exit text, no stderr, no output at all. This
  is defect P-10 stated as a signature: recovery reads the class recorded on the run and no code
  path re-greps stderr for `"401"`, `"websocket"` or `"connection"`, substrings a model may itself
  have authored. `AUTH_FAILED` and `TRANSPORT_FAILED` are deliberately unreachable from this
  function: section 13 obtains them from the Human Owner's typed `--classification` at
  `recover-failed-review`, which is the only place that judgement is admissible.
* **No provider is invoked from inside a provider's handling path.** :class:`ProviderInvoker`
  refuses a re-entrant call outright, so the per-milestone invocation count is bounded by the
  application's own loop rather than by a provider's output (section 17, invariant 14).
* **Only the explicit allowlist is forwarded.** :func:`build_provider_environment` copies exactly
  the named variables the configuration lists, refuses a credential-shaped name even when listed,
  and forwards nothing else. The runner never reads, writes, forwards, logs or stores provider
  authentication; an installed CLI keeps whatever it already uses (invariant 1).

Retry, and why this module does not perform one
-----------------------------------------------
Section 17 permits a bounded retry **only** for `SPAWN_FAILED` -- the one class proven to be
pre-side-effect -- capped at three attempts in a durable counter kept independent of the repair
counter and the review budget. :func:`retry_permitted` encodes both halves of that rule, and
:meth:`ProviderInvoker.invoke` performs exactly one attempt: the counter section 17 requires is
durable, and durable state belongs to the run record, so the loop is the application's to run
through `PROVIDER_RETRY_PENDING` (section 10) rather than a silent in-adapter repetition.

Evidence is never destroyed
---------------------------
Every invocation writes its prompt, stdout and stderr transcript -- a spawn failure and a timeout
included -- through `state.write_redacted_artifact`, the single section 17a boundary, before this
module reports anything. A failed or rejected result therefore always has its transcripts on disk
(invariant 15), and no code path here deletes one.
"""

import io
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, ClassVar, Final

from pydantic import Field, field_validator, model_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    MAX_ARGUMENT_CHARS,
    MilestoneRunnerModel,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
)
from ai_workflow_engine.milestone_runner.state import (
    RedactedWrite,
    RunStateStore,
    TranscriptKind,
    transcript_reference,
)

#: Section 17's explicit byte ceilings. Provider output is untrusted and unbounded in principle;
#: these are what make "captured with explicit byte ceilings" a number rather than a hope. They
#: sit well under `state.MAX_ARTIFACT_BYTES`, so a capture that reaches the ceiling still writes.
MAX_CAPTURED_STDOUT_BYTES: Final = 8 << 20
MAX_CAPTURED_STDERR_BYTES: Final = 8 << 20

#: The largest prompt this package will hand to a child. A prompt is assembled by `prompts.py`
#: from typed data, so a larger one means a caller is streaming something into a prompt.
MAX_PROMPT_BYTES: Final = 1 << 20

#: How much of Codex's last-message file is read back. Same reasoning as the stream ceilings.
MAX_LAST_MESSAGE_BYTES: Final = 8 << 20

#: The read size for the bounded stream readers. Large enough to be cheap, small enough that the
#: ceiling is enforced promptly rather than after an arbitrarily large single read.
READ_CHUNK_BYTES: Final = 64 << 10

#: How long a terminated process group is given to die between `SIGTERM` and `SIGKILL`, and how
#: long the reader threads are then given to finish. Not a configuration knob: it bounds cleanup,
#: never the invocation, which `timeout_seconds` alone bounds.
TERMINATION_GRACE_SECONDS: Final = 5.0

#: Section 17's retry cap. Present as a named constant because section 6 defect P-4 is exactly a
#: ceiling no code path could reach: this one is reachable, and :func:`retry_permitted` is the
#: only reader of it.
MAX_SPAWN_RETRY_ATTEMPTS: Final = 3

#: The timestamp grammar `models.ProviderRunRecord` requires.
_TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"

#: POSIX environment-variable names, restated here so this module refuses a wildcard on its own
#: authority rather than trusting that the configuration loader already did. No metacharacter is
#: admissible, so `*`, `PATH*` and `**` fail the grammar rather than a special case.
_ENVIRONMENT_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Names whose *shape* says the value is a credential. Invariant 1 forbids the runner to forward
#: authentication at all, so such a name is refused even when the configuration lists it: an
#: installed CLI already has whatever it needs, and a runner that forwarded a token would be
#: handling one. The set is deliberately shape-based and small; it narrows what may be forwarded
#: and can never widen it.
_CREDENTIAL_SHAPED_NAME_RE = re.compile(
    r".*(TOKEN|KEY|SECRET|PASSWORD|PASSWD|PASSPHRASE|CREDENTIAL).*"
)

#: The transcript-label grammar `state.transcript_name` enforces, restated so a label is refused
#: here -- where the provider and the role are known -- rather than deep inside the writer.
_TRANSCRIPT_LABEL_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


# --------------------------------------------------------------------------------------
# Typed failures
# --------------------------------------------------------------------------------------


class ProviderError(WorkflowEngineError):
    """Base failure for the provider boundary.

    A failure *of the provider* is not an exception: it is a classified
    :class:`ProviderInvocation` with transcripts on disk, because the run has to record what
    happened. These exceptions are raised only when the runner itself was asked for something it
    must refuse -- an argv it does not own, an environment it may not forward, a re-entrant call.
    """


class ProviderArgvRefused(ProviderError):
    """The requested argv is not one this package owns, or expresses a capability it may not."""


class ProviderEnvironmentRefused(ProviderError):
    """An environment allowlist entry is malformed or credential-shaped (invariant 1)."""


class RecursiveProviderInvocation(ProviderError):
    """A provider was invoked from inside another provider's handling path (section 17)."""


# --------------------------------------------------------------------------------------
# Section 17 / defect P-10 -- classification turns on *when*, never on text
# --------------------------------------------------------------------------------------


class InvocationPhase(StrEnum):
    """When a provider invocation failed -- the only input classification is permitted to read.

    `MODEL_PROVIDER_CONTRACTS.md` section 2 requires classification to turn on when the failure
    occurred rather than on what the error text said. These five members are the five moments a
    single invocation can fail at, in order, and each maps to exactly one class.
    """

    #: The executable never started: not found, not executable, permission denied. The only
    #: provably pre-side-effect moment, and therefore the only retryable one (section 17).
    SPAWN = "SPAWN"
    #: The process started and the bounded timeout expired before it exited.
    DEADLINE = "DEADLINE"
    #: The process ran to completion and exited non-zero.
    EXIT = "EXIT"
    #: The process exited zero and its output did not satisfy the section 18 grammar.
    PARSE = "PARSE"
    #: The output parsed and the provider itself reported that it failed.
    REPORT = "REPORT"


#: The closed phase-to-class mapping. It is injective, so the recorded class names the moment
#: unambiguously, and total, so no phase falls through to a default.
_FAILURE_CLASS_BY_PHASE: Final[Mapping[InvocationPhase, ProviderFailureClass]] = {
    InvocationPhase.SPAWN: ProviderFailureClass.SPAWN_FAILED,
    InvocationPhase.DEADLINE: ProviderFailureClass.TIMEOUT,
    InvocationPhase.EXIT: ProviderFailureClass.COMMAND_FAILED,
    InvocationPhase.PARSE: ProviderFailureClass.MALFORMED_OUTPUT,
    InvocationPhase.REPORT: ProviderFailureClass.PROVIDER_REPORTED,
}


def classify_invocation_failure(phase: InvocationPhase) -> ProviderFailureClass:
    """Return the failure class for `phase` -- fixed at invocation time, then persisted.

    The signature is the point. There is no `stderr`, no `output` and no `message` parameter, so
    no revision of this function can quietly start matching `"401"`, `"websocket"` or
    `"connection"` against text a model authored. That is prototype defect P-10, closed by
    construction rather than by a rule someone has to keep obeying.

    `AUTH_FAILED` and `TRANSPORT_FAILED` are absent from the mapping deliberately. They are real
    classes in the section 17 taxonomy, but they are judgements about *why* a started process
    failed, which no observation available at invocation time can make. Section 13 obtains them
    from the Human Owner's typed `--classification` on `recover-failed-review`, together with an
    explicit ruling string -- evidence a human supplied, never a substring the runner guessed at.
    """
    return _FAILURE_CLASS_BY_PHASE[phase]


def retry_permitted(failure_class: ProviderFailureClass, attempts_already_made: int) -> bool:
    """Whether section 17 permits another attempt after `failure_class`.

    Two independent conditions, both required. The class must be `SPAWN_FAILED`, the sole class
    proven to have occurred before any side effect -- every other failure requires reconciliation
    before repetition, because the process ran and may have changed the worktree. And the attempt
    count must be below :data:`MAX_SPAWN_RETRY_ATTEMPTS`.

    `attempts_already_made` is passed in rather than held here: section 17 requires the counter to
    be durable and independent of both the repair counter and the review budget, so it lives on
    the run record and this function only reads it.
    """
    if attempts_already_made < 0:
        raise ProviderError("An attempt count cannot be negative")
    return (
        failure_class is ProviderFailureClass.SPAWN_FAILED
        and attempts_already_made < MAX_SPAWN_RETRY_ATTEMPTS
    )


# --------------------------------------------------------------------------------------
# Section 17 -- the closed argv template
# --------------------------------------------------------------------------------------


class ArgvSlot(StrEnum):
    """The closed set of named interpolation slots an argv template may carry (section 17).

    The member *value* is the literal template element, so a template is readable as the command
    it becomes and :func:`render_argv` needs no parsing beyond an exact-match lookup. Section 17
    names `{repo_root}` and `{last_message_path}`; the executable and the two capability modes are
    slots for the same reason -- they are the only parts of a vector that configuration supplies.
    """

    EXECUTABLE = "{executable}"
    REPO_ROOT = "{repo_root}"
    LAST_MESSAGE_PATH = "{last_message_path}"
    PERMISSION_MODE = "{permission_mode}"
    SANDBOX_MODE = "{sandbox_mode}"


_SLOT_BY_TEMPLATE_ELEMENT: Final[Mapping[str, ArgvSlot]] = {slot.value: slot for slot in ArgvSlot}


def render_argv(template: Sequence[str], values: Mapping[ArgvSlot, str]) -> list[str]:
    """Render one provider-owned argv template into a concrete argument vector.

    Substitution is whole-element and exact: an element is either a literal that is copied through
    or a slot name that is replaced entirely. There is no `str.format`, no `%`, no concatenation
    and no partial interpolation, so no configured or provider-supplied value can extend a vector
    with an argument the template did not declare. A slot with no value, and a value for a slot
    the template does not use, are both refusals rather than silently ignored.
    """
    if not template:
        raise ProviderArgvRefused("An argv template must not be empty")
    required = {slot for element in template if (slot := _SLOT_BY_TEMPLATE_ELEMENT.get(element))}
    missing = required - set(values)
    if missing:
        raise ProviderArgvRefused(
            f"The argv template needs values for {sorted(slot.value for slot in missing)}"
        )
    unused = set(values) - required
    if unused:
        raise ProviderArgvRefused(
            f"The argv template declares no {sorted(slot.value for slot in unused)} slot"
        )
    rendered: list[str] = []
    for index, element in enumerate(template):
        slot = _SLOT_BY_TEMPLATE_ELEMENT.get(element)
        argument = values[slot] if slot is not None else element
        if not argument or len(argument) > MAX_ARGUMENT_CHARS:
            raise ProviderArgvRefused(f"argv[{index}] must be a bounded, non-empty argument")
        if "\x00" in argument:
            raise ProviderArgvRefused(f"argv[{index}] must not contain a NUL byte")
        rendered.append(argument)
    return rendered


# --------------------------------------------------------------------------------------
# Invariant 1 -- the forwarded environment
# --------------------------------------------------------------------------------------


def build_provider_environment(
    allowed_names: Sequence[str], source: Mapping[str, str]
) -> dict[str, str]:
    """Return exactly the allowlisted variables present in `source`, and nothing else.

    The child inherits no environment of its own: `Popen` is given this mapping, so a variable
    that is not listed does not exist for the provider. A name that is not a POSIX
    environment-variable name is refused, which is how "no wildcard is permitted" (section 17,
    `CONFIGURATION_MODEL.md` section 4) holds here independently of the loader having enforced it.

    A credential-shaped name is refused even when the configuration lists it. Invariant 1 is that
    the runner never reads, writes, forwards, logs or stores provider authentication -- it
    inherits nothing and grants nothing; the installed CLI already has whatever it uses. A listed
    name is a configuration author's intent, and this refusal narrows that intent rather than
    widening it.
    """
    environment: dict[str, str] = {}
    for name in allowed_names:
        if _ENVIRONMENT_NAME_RE.fullmatch(name) is None:
            raise ProviderEnvironmentRefused(
                f"{name!r} is not a POSIX environment-variable name; no wildcard is permitted"
            )
        if _CREDENTIAL_SHAPED_NAME_RE.fullmatch(name.upper()) is not None:
            raise ProviderEnvironmentRefused(
                f"Refusing to forward {name!r}: the name is credential-shaped, and the runner "
                "never reads, forwards or stores provider authentication (invariant 1)"
            )
        value = source.get(name)
        if value is not None:
            environment[name] = value
    return environment


# --------------------------------------------------------------------------------------
# The subprocess itself
# --------------------------------------------------------------------------------------


class ProcessOutcome(MilestoneRunnerModel):
    """What one spawned process did, before any of it is written down or classified.

    `spawn_error` is set only when no process ever existed. When it is set every other field is
    the empty observation it has to be -- there was nothing to observe -- and the invocation is
    the one section 17 permits a bounded retry for.
    """

    exit_code: int | None = None
    timed_out: bool = False
    spawn_error: str | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    duration_ms: int = Field(default=0, ge=0)

    @property
    def phase(self) -> InvocationPhase | None:
        """The phase this outcome failed at, or `None` when the process exited zero in time.

        `PARSE` and `REPORT` are not decidable here -- they are questions about the *content* of
        the output, which this layer deliberately does not read.
        """
        if self.spawn_error is not None:
            return InvocationPhase.SPAWN
        if self.timed_out:
            return InvocationPhase.DEADLINE
        if self.exit_code != 0:
            return InvocationPhase.EXIT
        return None


class _BoundedReader(threading.Thread):
    """Drain one pipe to a byte ceiling, and keep draining after it is reached.

    Both halves matter. Keeping only `ceiling` bytes is section 17's explicit capture ceiling.
    Continuing to read past it is what keeps the child from blocking forever on a full pipe -- a
    reader that stopped would turn a chatty provider into a hang that only the timeout could end.
    """

    def __init__(self, stream: IO[bytes], ceiling: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._ceiling = ceiling
        self._chunks: list[bytes] = []
        self._kept = 0
        self.truncated = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                room = self._ceiling - self._kept
                if room > 0:
                    self._chunks.append(chunk[:room])
                    self._kept += min(room, len(chunk))
                if len(chunk) > room:
                    self.truncated = True
        except (OSError, ValueError):
            # The pipe was closed under us by termination. What was already read is still
            # evidence, so this is not an error to raise; it is the end of the stream.
            pass
        finally:
            try:
                self._stream.close()
            except OSError:
                pass

    @property
    def text(self) -> str:
        """The captured bytes as text. Provider output is untrusted, so decoding never raises."""
        return b"".join(self._chunks).decode("utf-8", errors="replace")


def _send_prompt_to_stdin(stream: IO[bytes], payload: bytes) -> None:
    """Copy the prompt into the child's stdin and close it, tolerating an early exit.

    A provider that exits before reading its prompt gives us `EPIPE`; that is the child's
    behaviour, recorded through its exit code, and not a failure of this transfer.

    Note what this is *not*: the destination is a pipe to a child process, never a file. The
    package's one filesystem-write boundary is `state.write_redacted_artifact` (section 17a), and
    no module here holds a filesystem-mutation primitive of its own.
    """
    try:
        shutil.copyfileobj(io.BytesIO(payload), stream)
        stream.flush()
    except OSError:
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _terminate_process_group(process: "subprocess.Popen[bytes]") -> None:
    """End the child *and everything it started*, `SIGTERM` first and `SIGKILL` after.

    The process was spawned with `start_new_session=True`, so it leads its own process group and
    one `killpg` reaches the whole tree. This is the discipline section 17 names: a model CLI
    spawns subprocesses of its own, and signalling only the direct child would leave them running
    against a repository the runner has already stopped guarding.
    """
    try:
        group = os.getpgid(process.pid)
    except OSError:
        group = -1
    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        try:
            if group > 0:
                os.killpg(group, signal_number)
            else:
                process.send_signal(signal_number)
        except OSError:
            return
        try:
            process.wait(timeout=TERMINATION_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            continue


def run_provider_process(
    *,
    argv: Sequence[str],
    prompt: str,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    stdout_ceiling: int = MAX_CAPTURED_STDOUT_BYTES,
    stderr_ceiling: int = MAX_CAPTURED_STDERR_BYTES,
) -> ProcessOutcome:
    """Run one provider process under the whole of section 17's discipline.

    A fixed argument **list**, never a string; no shell, no `os.system` and no command assembled
    by concatenation, anywhere (invariant 3). The prompt goes to stdin and is refused if it
    appears in the vector, so it never reaches a process listing. The child leads its own process
    group, so a timeout ends its whole tree rather than orphaning it. Both output streams are
    drained by bounded readers, so neither an enormous output nor a full pipe can hang the runner.
    The environment is exactly what the caller allowlisted.

    Nothing is raised for a provider's own failure: a spawn failure, a timeout and a non-zero exit
    are all returned as a :class:`ProcessOutcome`, because each is evidence the run must record.
    """
    if timeout_seconds < 1:
        raise ProviderArgvRefused("A provider timeout must be a positive number of seconds")
    vector = list(argv)
    if not vector:
        raise ProviderArgvRefused("A provider argv must not be empty")
    if not prompt:
        # Checked before the containment test below, which an empty prompt would satisfy against
        # every argument and turn into an unreadable refusal.
        raise ProviderArgvRefused("A provider prompt must not be empty")
    if any(prompt == argument or prompt in argument for argument in vector):
        raise ProviderArgvRefused(
            "The prompt must travel on the child's stdin and never in its argument vector, "
            "where a process listing would expose it (section 17)"
        )
    payload = prompt.encode("utf-8")
    if len(payload) > MAX_PROMPT_BYTES:
        raise ProviderArgvRefused(
            f"The prompt is {len(payload)} bytes, above the {MAX_PROMPT_BYTES}-byte ceiling"
        )

    started_ns = time.monotonic_ns()
    try:
        process = subprocess.Popen(
            vector,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env=dict(environment),
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        # No process ever existed, so no side effect can have occurred: this is the one class
        # section 17 permits a bounded retry for.
        return ProcessOutcome(
            spawn_error=f"{vector[0]}: {exc}",
            duration_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
        )

    stdin_stream, stdout_stream, stderr_stream = process.stdin, process.stdout, process.stderr
    if stdin_stream is None or stdout_stream is None or stderr_stream is None:
        # Unreachable while all three are `PIPE` above; refused rather than assumed, because an
        # unpiped stream would mean the prompt or the output escaped this boundary entirely.
        _terminate_process_group(process)
        raise ProviderError(f"{vector[0]} was spawned without all three pipes attached")

    out_reader = _BoundedReader(stdout_stream, stdout_ceiling)
    err_reader = _BoundedReader(stderr_stream, stderr_ceiling)
    out_reader.start()
    err_reader.start()
    writer = threading.Thread(
        target=_send_prompt_to_stdin, args=(stdin_stream, payload), daemon=True
    )
    writer.start()

    timed_out = False
    try:
        exit_code: int | None = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
        exit_code = process.poll()
    finally:
        writer.join(timeout=TERMINATION_GRACE_SECONDS)
        out_reader.join(timeout=TERMINATION_GRACE_SECONDS)
        err_reader.join(timeout=TERMINATION_GRACE_SECONDS)

    return ProcessOutcome(
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=out_reader.text,
        stderr=err_reader.text,
        stdout_truncated=out_reader.truncated,
        stderr_truncated=err_reader.truncated,
        duration_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
    )


# --------------------------------------------------------------------------------------
# One invocation: what was asked, and what came back
# --------------------------------------------------------------------------------------


class ProviderRequest(MilestoneRunnerModel):
    """Exactly one provider invocation, as the adapter that owns the argv describes it.

    Only an adapter builds one of these: the vector comes from that adapter's own template
    constant, so invariant 20 -- every provider-spawning call site lives under `providers/` -- is
    a property of who can fill this model in, not of a comment asking callers to behave.

    `timeout_seconds` has no default here for the same reason it has none in the configuration:
    section 17 requires the bound to be configured, and a default is exactly the fallback that
    turns "bounded" into "bounded unless someone forgot".
    """

    provider: str
    role: ProviderRole
    argv: list[str] = Field(min_length=1)
    prompt: str
    timeout_seconds: int = Field(ge=1)
    transcript_label: str
    milestone_id: str | None = None
    #: Where the child is told to write its final message, for a provider whose result does not
    #: come back on stdout. It is a scratch path outside both the repository and the state root;
    #: :class:`ProviderInvoker` reads it, writes it through the section 17a boundary as a durable
    #: transcript, and removes the scratch so no unredacted byte is left behind.
    last_message_path: str | None = None

    @field_validator("argv")
    @classmethod
    def _validate_argv(cls, value: list[str]) -> list[str]:
        for index, argument in enumerate(value):
            if not argument or len(argument) > MAX_ARGUMENT_CHARS:
                raise ValueError(f"argv[{index}] must be a bounded, non-empty argument")
        return value

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        if len(value.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ValueError(f"prompt must be at most {MAX_PROMPT_BYTES} bytes")
        return value

    @field_validator("transcript_label")
    @classmethod
    def _validate_transcript_label(cls, value: str) -> str:
        if _TRANSCRIPT_LABEL_RE.fullmatch(value) is None:
            raise ValueError(f"transcript_label must match {_TRANSCRIPT_LABEL_RE.pattern!r}")
        return value

    @field_validator("last_message_path")
    @classmethod
    def _validate_last_message_path(cls, value: str | None) -> str | None:
        """An answer file lives in a private scratch directory, and nowhere else.

        The path is where a *child* writes bytes the runner then moves across the section 17a
        boundary and removes. So it is confined here, at the boundary that admits it: it must be a
        file directly inside a directory directly inside the system temporary root -- the shape
        `mkdtemp` produces. Neither the repository the runner is guarding nor the state root can
        satisfy that, which is what makes :func:`_remove_scratch`'s recursive removal safe by
        construction rather than by the caller having chosen well (invariant 13).
        """
        if value is None:
            return None
        if not value.startswith("/"):
            raise ValueError("last_message_path must be an absolute POSIX path")
        if not _is_scratch_answer_path(Path(value)):
            raise ValueError(
                "last_message_path must name a file inside a private scratch directory directly "
                f"under {_temporary_root()}, the shape `tempfile.mkdtemp` produces"
            )
        return value

    @model_validator(mode="after")
    def _validate_prompt_is_not_an_argument(self) -> "ProviderRequest":
        """The prompt never appears in the vector -- section 17, checked before a process exists.

        Containment rather than equality: a vector element that merely *carries* the prompt puts
        it in a process listing just as surely as one that equals it.
        """
        if any(self.prompt == argument or self.prompt in argument for argument in self.argv):
            raise ValueError(
                "the prompt must be delivered on stdin and must never appear in argv, where a "
                "process listing would expose it"
            )
        return self


class ProviderInvocation(MilestoneRunnerModel):
    """One completed invocation: its durable record, and the text the caller may now read.

    `record` is what the run record carries -- references to transcripts, the exit code, the
    duration, the timeout flag and the class fixed at invocation time. The text fields are the
    same content in memory for a caller that has to parse it (section 18); every persisted copy
    went through the section 17a redaction boundary on its way to disk, and this in-memory copy
    is never written anywhere except through that same boundary.

    `writes` carries what each pass through the boundary neutralized, so the application can turn
    a redaction into the counted, visible finding section 17a requires instead of a silent event.
    """

    record: ProviderRunRecord
    stdout: str
    stderr: str
    last_message: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    writes: list[RedactedWrite] = Field(default_factory=list)

    @property
    def failure_class(self) -> ProviderFailureClass | None:
        """The class fixed at invocation time, or `None` when the process exited zero in time."""
        return self.record.failure_class

    @property
    def succeeded(self) -> bool:
        """Whether the *invocation* succeeded. Never a claim about what the provider said.

        A timeout is a failure here and can never be read as a success: `record.timed_out` forces
        a `TIMEOUT` class at the model boundary, so this property cannot return `True` for one
        (`WORKFLOW_STATES.md` section 5a item 6, invariant 18).
        """
        return self.record.failure_class is None

    @property
    def timed_out(self) -> bool:
        return self.record.timed_out


# --------------------------------------------------------------------------------------
# The invoker, and the adapter contract it serves
# --------------------------------------------------------------------------------------


#: What the invoker hands a caller the moment an invocation becomes durable, before the process
#: exists. The record it carries is incomplete by construction -- no `completed_at`, no exit code
#: -- because nothing about the outcome is known yet.
ProviderStartedHook = Callable[[ProviderRunRecord], None]


def _pending_record(
    request: ProviderRequest, *, sequence: int, moment: datetime
) -> ProviderRunRecord:
    """The in-flight record of an invocation that is about to start (section 13).

    Everything already decided is recorded: the sequence, the role, the provider, the milestone and
    the three transcript references, which are a function of the sequence and the moment and so are
    knowable before the transcripts they name exist. Everything the outcome decides is left open --
    `completed_at` is `None`, which is exactly what makes this row readable as "in flight".
    """
    references = {
        kind: transcript_reference(sequence, moment, request.transcript_label, kind)
        for kind in (TranscriptKind.PROMPT, TranscriptKind.STDOUT, TranscriptKind.STDERR)
    }
    return ProviderRunRecord(
        sequence=sequence,
        role=request.role,
        provider=request.provider,
        milestone_id=request.milestone_id,
        started_at=moment.strftime(_TIMESTAMP_FORMAT),
        completed_at=None,
        duration_ms=0,
        prompt_path=references[TranscriptKind.PROMPT],
        stdout_path=references[TranscriptKind.STDOUT],
        stderr_path=references[TranscriptKind.STDERR],
    )


def transcript_label_for(provider: str, role: ProviderRole) -> str:
    """Return the `<provider>-<role>` transcript label, in the grammar `state.py` accepts."""
    label = f"{provider.lower()}-{role.value.lower()}"
    if _TRANSCRIPT_LABEL_RE.fullmatch(label) is None:
        raise ProviderArgvRefused(f"{label!r} is not a usable transcript label")
    return label


class ProviderInvoker:
    """The one path from a :class:`ProviderRequest` to a durable, classified invocation.

    Both adapters run through this object, so the discipline is written once: allocate the
    monotonic transcript sequence (defect P-9), persist the prompt, forward only the allowlisted
    environment, spawn under section 17's rules, persist stdout and stderr, classify by phase and
    return a record that references every transcript by path.

    Re-entrancy is refused rather than counted. Section 17 requires that no provider be invoked
    from inside another provider's handling path; an invoker that simply refuses a nested call
    makes the per-milestone invocation count a property of the application's loop, which no
    provider's output can influence (invariant 14).
    """

    def __init__(
        self,
        *,
        store: RunStateStore,
        lock: RunLock,
        repository_root: Path,
        allowed_environment_variables: Sequence[str],
        source_environment: Mapping[str, str] | None = None,
    ) -> None:
        self._store = store
        self._lock = lock
        self._repository_root = repository_root
        self._allowed_environment_variables = tuple(allowed_environment_variables)
        self._source_environment: Mapping[str, str] = (
            dict(os.environ) if source_environment is None else dict(source_environment)
        )
        self._in_flight = False

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def in_flight(self) -> bool:
        """Whether an invocation is running on this invoker right now."""
        return self._in_flight

    def invoke(
        self,
        request: ProviderRequest,
        *,
        on_started: ProviderStartedHook | None = None,
    ) -> ProviderInvocation:
        """Run `request` exactly once and return its durable outcome.

        Exactly once: no retry happens here. Section 17 permits one only for `SPAWN_FAILED` and
        requires the counter to be durable, so the decision belongs to the application, which owns
        the run record and the `PROVIDER_RETRY_PENDING` state. :func:`retry_permitted` is the rule
        it applies; this method is the single attempt it applies it to.

        `on_started` is called with the invocation's *incomplete* record after the sequence and the
        transcript names are fixed and before the process exists, so the caller can make the
        invocation durable before it can have any effect (section 13).
        """
        if self._in_flight:
            raise RecursiveProviderInvocation(
                f"Refusing to invoke {request.provider} for {request.role} while an invocation is "
                "already in flight on this invoker: no provider is invoked from inside another "
                "provider's handling path (section 17)"
            )
        self._in_flight = True
        try:
            return self._invoke_once(request, on_started)
        finally:
            self._in_flight = False

    def _invoke_once(
        self, request: ProviderRequest, on_started: ProviderStartedHook | None
    ) -> ProviderInvocation:
        moment = datetime.now(UTC)
        sequence = self._store.next_transcript_sequence(lock=self._lock)
        writes: list[RedactedWrite] = [
            self._write(
                sequence, moment, request.transcript_label, TranscriptKind.PROMPT, request.prompt
            )
        ]

        # Section 13: the invocation becomes durable *here* -- after the sequence and the three
        # transcript names are fixed, and before a process exists. A runner that dies once the
        # provider has started therefore leaves a record naming an invocation with no
        # `completed_at`, which is the persisted operation evidence `MACHINE_GATES.md` section 2a
        # requires resume to reconcile against before repeating anything.
        if on_started is not None:
            on_started(_pending_record(request, sequence=sequence, moment=moment))

        environment = build_provider_environment(
            self._allowed_environment_variables, self._source_environment
        )
        outcome = run_provider_process(
            argv=request.argv,
            prompt=request.prompt,
            cwd=self._repository_root,
            environment=environment,
            timeout_seconds=request.timeout_seconds,
        )
        completed = datetime.now(UTC)

        # Evidence first, and unconditionally: a spawn failure, a timeout and a rejected result
        # all keep their transcripts (invariant 15). A spawn failure has no provider stderr,
        # so the refusal the operating system gave us is what the stderr transcript records.
        stderr_text = outcome.stderr if outcome.spawn_error is None else outcome.spawn_error
        writes.append(
            self._write(
                sequence, moment, request.transcript_label, TranscriptKind.STDOUT, outcome.stdout
            )
        )
        writes.append(
            self._write(
                sequence, moment, request.transcript_label, TranscriptKind.STDERR, stderr_text
            )
        )
        last_message = self._collect_last_message(request)
        if last_message is not None:
            writes.append(
                self._write(
                    sequence,
                    moment,
                    request.transcript_label,
                    TranscriptKind.LAST_MESSAGE,
                    last_message,
                )
            )

        phase = outcome.phase
        record = ProviderRunRecord(
            sequence=sequence,
            role=request.role,
            provider=request.provider,
            milestone_id=request.milestone_id,
            started_at=moment.strftime(_TIMESTAMP_FORMAT),
            completed_at=completed.strftime(_TIMESTAMP_FORMAT),
            duration_ms=outcome.duration_ms,
            exit_code=outcome.exit_code,
            timed_out=outcome.timed_out,
            failure_class=None if phase is None else classify_invocation_failure(phase),
            prompt_path=_reference(writes[0]),
            stdout_path=_reference(writes[1]),
            stderr_path=_reference(writes[2]),
        )
        return ProviderInvocation(
            record=record,
            stdout=outcome.stdout,
            stderr=stderr_text,
            last_message=last_message,
            stdout_truncated=outcome.stdout_truncated,
            stderr_truncated=outcome.stderr_truncated,
            writes=writes,
        )

    def _write(
        self,
        sequence: int,
        moment: datetime,
        label: str,
        kind: TranscriptKind,
        text: str,
    ) -> RedactedWrite:
        """Persist one transcript through the single section 17a boundary."""
        return self._store.write_transcript(
            sequence=sequence,
            label=label,
            kind=kind,
            text=text,
            moment=moment,
            lock=self._lock,
        )

    def _collect_last_message(self, request: ProviderRequest) -> str | None:
        """Read the child's last-message scratch file, then remove it.

        The scratch file exists because a provider writes its final message itself, and a child's
        write cannot pass through the section 17a boundary on its way to disk. So it is written
        somewhere that is neither the repository -- which the runner is guarding -- nor the state
        root -- where every byte must already be redacted -- and this method moves its content
        across the boundary and then removes the unredacted original. The durable transcript is
        written before the scratch is gone, so removing it destroys no evidence (invariant 15).
        """
        if request.last_message_path is None:
            return None
        scratch = Path(request.last_message_path)
        try:
            with scratch.open("rb") as handle:
                payload = handle.read(MAX_LAST_MESSAGE_BYTES + 1)
        except OSError:
            # A provider that failed to start, timed out, or exited before writing leaves no file.
            payload = b""
        finally:
            _remove_scratch(scratch)
        if not payload:
            return ""
        return payload[:MAX_LAST_MESSAGE_BYTES].decode("utf-8", errors="replace")


def _temporary_root() -> Path:
    """The system temporary root, as `tempfile.mkdtemp` itself resolves it."""
    return Path(tempfile.gettempdir()).resolve()


def _is_scratch_answer_path(candidate: Path) -> bool:
    """Whether `candidate` has the shape a `mkdtemp` answer file has, and only that shape.

    A file directly inside a directory directly inside the temporary root. The check is on the
    shape rather than on a prefix string, so no `..` segment and no symlinked component can
    present something else as a scratch path: both sides are resolved before they are compared.
    """
    try:
        directory = candidate.parent.resolve()
    except OSError:
        return False
    return directory != _temporary_root() and directory.parent == _temporary_root()


def _remove_scratch(scratch: Path) -> None:
    """Remove the private scratch directory an adapter created for one answer file.

    The whole directory goes, because the whole directory is what was created: it is a
    `mkdtemp` result outside both the repository and the state root, holding one file a child
    wrote. Nothing under the worktree and nothing under the state root is reachable from here
    (invariant 13): the shape is re-checked immediately before the removal, so this call site is
    safe on its own evidence rather than on `ProviderRequest` having validated the same thing
    earlier. A path that fails the check has nothing removed at all -- refusing to delete
    something this package did not create is the conservative half of invariant 13. The durable
    transcript was already written before this runs, so no evidence is lost (invariant 15).
    """
    if not _is_scratch_answer_path(scratch):
        return
    shutil.rmtree(scratch.parent, ignore_errors=True)


def _reference(write: RedactedWrite) -> str:
    """The run-relative path a record references a transcript by (section 11)."""
    if write.relative_path is None:
        raise ProviderError(f"{write.path} was written without a run-relative reference")
    return write.relative_path


class ProviderAdapter(ABC):
    """What both adapters share: a name, its roles, and one provider-owned argv template.

    An adapter is the only thing that may build a :class:`ProviderRequest`, and it builds one
    solely from its own template constant plus validated configuration. Everything a role-specific
    prompt needs is rendered by `prompts.py` and arrives here as one already-assembled string, so
    an adapter never composes a directive from provider output.
    """

    #: The provider's name as it appears in the durable record.
    name: ClassVar[str]
    #: The roles this adapter is permitted to serve. A role outside the set is refused, which is
    #: what keeps Claude out of review and Codex out of implementation.
    roles: ClassVar[frozenset[ProviderRole]]

    @abstractmethod
    def build_request(
        self, *, role: ProviderRole, prompt: str, milestone_id: str | None = None
    ) -> ProviderRequest:
        """Build the one request this adapter's template and configuration describe."""

    def invoke(
        self,
        invoker: ProviderInvoker,
        *,
        role: ProviderRole,
        prompt: str,
        milestone_id: str | None = None,
        on_started: ProviderStartedHook | None = None,
    ) -> ProviderInvocation:
        """Build the request and run it through the shared discipline, exactly once."""
        return invoker.invoke(
            self.build_request(role=role, prompt=prompt, milestone_id=milestone_id),
            on_started=on_started,
        )

    def _require_role(self, role: ProviderRole) -> None:
        if role not in self.roles:
            raise ProviderArgvRefused(
                f"{self.name} serves {sorted(member.value for member in self.roles)}, not {role}"
            )
