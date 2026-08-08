"""Bounded verification execution and the machine-readable governance gate (AUTO-016).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 16
(verification execution), section 4 item 7 (the canonical governance checks and their single
documented tolerance), section 17a (sanitization before persistence), section 22 invariants 3
(no shell), 15 (evidence preservation) and 18 (no fabricated success), and section 6 defects P-7
(a scraped governance gate) and P-8 (evidence loss).

What this module runs, and what it never runs
---------------------------------------------
Deterministic commands only. Every vector arrives as an argv **list** from validated
configuration or from a milestone's own `focused_verification` entries; nothing here builds a
command from a string, and there is no `shell=True` path anywhere in the package (invariant 3).
No provider is invoked and no provider argv is constructible from this module -- the provider
boundary is `providers/`, and section 22 invariant 20 keeps it there.

Three properties are structural rather than checked downstream
--------------------------------------------------------------
* **A timeout is never a pass.** `models.VerificationResult` recomputes `passed` from the exit
  code and the timeout flag, so a record claiming success after a timeout cannot be constructed at
  all. `WORKFLOW_STATES.md` section 5a item 6 is therefore true by type rather than by convention
  (invariant 18).
* **The full output is persisted, never truncated to a tail.** Defect P-8 is the prototype keeping
  the last 800 characters of a failed command. Here each command's complete stdout and stderr pass
  through the single section 17a redaction boundary into the run's transcript directory, and the
  record carries only the exit code, the duration, the timeout flag and the two references.
* **The governance gate reads structured results, never a rendered table.** Defect P-7 is the
  prototype scraping box-drawing characters out of `workflowctl verify`'s console output under a
  forced `LC_ALL=C`. Here every check is evaluated from its own machine-readable document; this
  module forces no locale, and a console-formatting change can neither silently open the gate nor
  silently close it. A document that does not parse is a `GOVERNANCE_CONTRADICTION`, which is the
  fail-closed direction.

Why `subprocess.run` and not `Popen`
------------------------------------
`Popen` with process-group termination belongs to `providers/base.py`, which spawns untrusted,
long-running model CLIs; invariant 20 keeps that primitive inside the subpackage that owns it.
A verification command is a runner-configured deterministic tool, so the simpler primitive is
used here, with the honest limitations stated where they bite: the byte ceilings below bound what
is *persisted* rather than what is buffered, and a timeout kills the direct child rather than a
process tree.
"""

import json
import re
import subprocess
import time
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Final

from pydantic import Field

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.config import VerificationCommandSettings
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    MAX_ARGUMENT_CHARS,
    MilestoneRunnerModel,
    StopReason,
    VerificationResult,
)
from ai_workflow_engine.milestone_runner.state import (
    RedactedWrite,
    RunStateStore,
    TranscriptKind,
)

#: What is kept from each stream. Generous by design: section 16 requires the *complete* output to
#: reach disk, and defect P-8 is exactly a tail-sized ceiling. These sit under
#: `state.MAX_ARTIFACT_BYTES`, so a capture at the ceiling still writes.
MAX_CAPTURED_STDOUT_BYTES: Final = 8 << 20
MAX_CAPTURED_STDERR_BYTES: Final = 8 << 20

#: Section 11's transcript label for verification output. `state.transcript_name` validates it
#: against the same lowercase-slug grammar a provider role is validated against.
VERIFICATION_TRANSCRIPT_LABEL: Final = "verification"

#: The largest machine-readable check document the gate will read. A governance check emits a
#: small typed record; anything larger is not one.
MAX_CHECK_DOCUMENT_BYTES: Final = 1 << 20

#: Section 4 item 7's canonical governance checks, each run individually (section 16) so the `git`
#: check can be evaluated against its single documented tolerance without loosening the others.
#: The four content checks are the ones AUTO-015 section 4 item 4 records as passing
#: unconditionally; `git` is the fifth and the only one carrying a tolerance.
GOVERNANCE_GIT_CHECK: Final = "git"
UNCONDITIONAL_GOVERNANCE_CHECKS: Final[tuple[str, ...]] = (
    "task-state",
    "governance",
    "registries",
    "handover",
)
REQUIRED_GOVERNANCE_CHECKS: Final[tuple[str, ...]] = (
    GOVERNANCE_GIT_CHECK,
    *UNCONDITIONAL_GOVERNANCE_CHECKS,
)

#: The one finding section 4 item 7 tolerates, and only on the `git` check: a local-only, unpushed
#: stage branch has no upstream, which `STAGE_REGISTRY.md` section 3 rule 16 and AUTO-015 section
#: 7.2 already established. Nothing else is tolerated on any check.
TOLERATED_GIT_FINDING_CODES: Final[frozenset[str]] = frozenset({"upstream_missing"})

#: A governance check name, as it appears in the machine-readable document.
_CHECK_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

#: A finding code, as it appears in the machine-readable document. Bounded and closed so an
#: arbitrary provider-authored string cannot be reported back as a "finding code".
_FINDING_CODE_RE = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")

#: What a check other than `git` may raise and still pass: nothing at all (section 4 item 7).
_NO_TOLERANCE: Final[frozenset[str]] = frozenset()


# --------------------------------------------------------------------------------------
# Typed failures
# --------------------------------------------------------------------------------------


class VerificationError(WorkflowEngineError):
    """A verification command could not be run at all, or was described unusably.

    A command that *fails* is not an exception: it is a :class:`VerificationOutcome` with
    `passed` false and its full output on disk, because a failure is evidence the run must record
    rather than an error that unwinds the run.
    """

    stop_reason: ClassVar[StopReason | None] = None


class GovernanceContradiction(VerificationError):
    """Section 4 item 7's stop: the governance gate is not satisfied, or cannot be evaluated.

    Both halves are the same refusal on purpose. A finding outside the single documented
    tolerance and a check whose machine-readable document does not parse are equally reasons the
    gate does not open: the gate is fail-closed, so "I could not tell" is never "probably fine".

    The offending checks travel with the refusal, as do the verification outcomes that produced
    them, so a stop record can reference the persisted output of every check it ran
    (invariant 15).
    """

    stop_reason: ClassVar[StopReason | None] = StopReason.GOVERNANCE_CONTRADICTION

    def __init__(
        self,
        message: str,
        *,
        findings: Sequence[str] = (),
        outcomes: Sequence["VerificationOutcome"] = (),
    ) -> None:
        super().__init__(message)
        self.findings: tuple[str, ...] = tuple(findings)
        self.outcomes: tuple[VerificationOutcome, ...] = tuple(outcomes)


# --------------------------------------------------------------------------------------
# Section 16 -- the environment a verification command runs in
# --------------------------------------------------------------------------------------


def build_verification_environment(
    source: Mapping[str, str], *, conda_bin: Path | None = None
) -> dict[str, str]:
    """Return the environment section 16 describes: `source`, with `conda_bin` ahead of `PATH`.

    Section 16 fixes one environment property -- "the conda environment's `bin` prepended to
    `PATH`" -- and this is it, as a pure function over a caller-supplied mapping. Resolving an
    environment *name* to its `bin` directory is deliberately not done here: that is an
    observation about the machine the runner is on, and this module makes none.

    `source` is copied, never mutated, and nothing is invented: a caller that passes an
    environment without `PATH` gets one whose `PATH` is exactly `conda_bin`.
    """
    environment = dict(source)
    if conda_bin is None:
        return environment
    existing = environment.get("PATH", "")
    environment["PATH"] = f"{conda_bin}:{existing}" if existing else str(conda_bin)
    return environment


# --------------------------------------------------------------------------------------
# Section 16 -- one bounded command
# --------------------------------------------------------------------------------------


class CommandOutcome(MilestoneRunnerModel):
    """What one bounded command did, before any of it is written down.

    `spawn_error` is set only when no process ever existed -- an executable that is not on `PATH`,
    or one this user may not execute. Every other field is then the empty observation it has to
    be, and `passed` is false, because nothing ran.
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
    def passed(self) -> bool:
        """Section 16: exit code `0` is a PASS, anything else is a FAIL, a timeout is a FAIL."""
        return self.exit_code == 0 and not self.timed_out and self.spawn_error is None


def _decode(payload: bytes | str | None, ceiling: int) -> tuple[str, bool]:
    """Decode one captured stream to text and apply the persistence ceiling.

    Command output is untrusted in the same way provider output is -- a test can print anything --
    so decoding never raises. The returned flag says whether the ceiling actually cut anything,
    which is recorded on the outcome so a reader is never left guessing whether a transcript is
    the whole story.
    """
    if payload is None:
        return "", False
    raw = payload.encode("utf-8", errors="replace") if isinstance(payload, str) else payload
    if len(raw) <= ceiling:
        return raw.decode("utf-8", errors="replace"), False
    return raw[:ceiling].decode("utf-8", errors="replace"), True


def validate_recordable_argv(argv: Sequence[str]) -> list[str]:
    """Return `argv` as a list, refusing any vector the durable record could not hold.

    The grammar is `models.VerificationResult`'s own -- a bounded, single-line, NFC-normalized,
    untrimmed-whitespace-free scalar per argument -- applied *before* the process rather than
    after it. Checking afterwards would mean running a command and only then discovering that its
    result cannot be written down, which is the one outcome a verification step must never have.
    """
    vector = list(argv)
    if not vector:
        raise VerificationError("A verification command must not be an empty argument vector")
    for index, argument in enumerate(vector):
        if not argument:
            raise VerificationError(f"argv[{index}] must be a non-empty argument")
        if len(argument) > MAX_ARGUMENT_CHARS:
            raise VerificationError(
                f"argv[{index}] is {len(argument)} characters, above the "
                f"{MAX_ARGUMENT_CHARS}-character ceiling"
            )
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in argument):
            raise VerificationError(
                f"argv[{index}] carries a control character, so the run record could not hold it"
            )
        if argument.strip() != argument:
            raise VerificationError(
                f"argv[{index}] has leading or trailing whitespace, so the run record could not "
                "hold it"
            )
        if unicodedata.normalize("NFC", argument) != argument:
            raise VerificationError(f"argv[{index}] must already be NFC-normalized")
    return vector


def run_bounded_command(
    *,
    argv: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    stdout_ceiling: int = MAX_CAPTURED_STDOUT_BYTES,
    stderr_ceiling: int = MAX_CAPTURED_STDERR_BYTES,
) -> CommandOutcome:
    """Run one validated argv list under a bounded timeout and return what it did.

    A **list**, never a string: `argv` is passed to `subprocess.run` as a vector, no shell is
    involved, and no argument is assembled by concatenation (invariant 3). The child inherits
    exactly the environment the caller built and nothing else.

    Nothing is raised for a command's own failure. A non-zero exit, a timeout and a spawn failure
    are all returned as a :class:`CommandOutcome`, because each is evidence the run has to record;
    only an unusable *description* of a command -- an empty vector, an unbounded timeout -- raises.

    Two honest limitations, stated rather than papered over. The byte ceilings bound what is
    persisted, not what the parent buffers while the child runs. And a timeout terminates the
    direct child; a verification tool that spawns a tree of its own may leave part of it behind,
    which is the trade for keeping the process-group primitive inside `providers/` where the
    untrusted, long-running invocations are.
    """
    vector = validate_recordable_argv(argv)
    if timeout_seconds < 1:
        raise VerificationError("A verification timeout must be a positive number of seconds")

    started_ns = time.monotonic_ns()
    try:
        completed = subprocess.run(
            vector,
            cwd=str(cwd),
            env=dict(environment),
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        # The output the command produced before the deadline is still evidence, so it is kept and
        # persisted; the outcome is a FAIL with `timed_out` set, never a pass (invariant 18).
        stdout, stdout_truncated = _decode(expired.stdout, stdout_ceiling)
        stderr, stderr_truncated = _decode(expired.stderr, stderr_ceiling)
        return CommandOutcome(
            exit_code=None,
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            duration_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
        )
    except OSError as exc:
        # No process ever existed. Recorded as a FAIL with the operating system's refusal as the
        # command's stderr, so the transcript says what happened instead of being empty.
        return CommandOutcome(
            spawn_error=f"{vector[0]}: {exc}",
            duration_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
        )

    stdout, stdout_truncated = _decode(completed.stdout, stdout_ceiling)
    stderr, stderr_truncated = _decode(completed.stderr, stderr_ceiling)
    return CommandOutcome(
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        duration_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
    )


class VerificationOutcome(MilestoneRunnerModel):
    """One executed verification command: its durable record, and the output behind it.

    `result` is what the run record keeps -- the exit code, the duration, the timeout flag and the
    two transcript references, and nothing else (defect P-8's correction is that the *record*
    stays small while the *output* stays complete). The captured text is carried here so a caller
    that has to read the output -- the governance gate reading a machine-readable document -- can
    do so without re-reading a file it just wrote.
    """

    result: VerificationResult
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    spawn_error: str | None = None
    purpose: str | None = None
    writes: list[RedactedWrite] = Field(default_factory=list)

    @property
    def command(self) -> list[str]:
        return list(self.result.command)

    @property
    def passed(self) -> bool:
        return self.result.passed

    @property
    def timed_out(self) -> bool:
        return self.result.timed_out

    @property
    def exit_code(self) -> int | None:
        return self.result.exit_code


class VerificationExecutor:
    """Section 16's executor: bounded commands, full persisted output, PASS/FAIL classification.

    Every command runs through :meth:`run`, so the discipline is written once: allocate the
    monotonic transcript sequence (defect P-9), run the vector under its own bounded timeout,
    persist the complete stdout and stderr through the single section 17a redaction boundary, and
    build a record that references both by path.

    The executor holds a store and a held run lock for the same reason every other writer in this
    package does (section 12, defect P-6): a durable write demands a lock, and there is no method
    here that writes without one.
    """

    def __init__(
        self,
        *,
        store: RunStateStore,
        lock: RunLock,
        repository_root: Path,
        environment: Mapping[str, str],
    ) -> None:
        self._store = store
        self._lock = lock
        self._repository_root = repository_root
        self._environment: Mapping[str, str] = dict(environment)

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def environment(self) -> Mapping[str, str]:
        """The environment every command is given -- a copy, so no caller can widen it later."""
        return dict(self._environment)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int,
        purpose: str | None = None,
    ) -> VerificationOutcome:
        """Run one command, persist its complete output, and classify it PASS or FAIL."""
        moment = datetime.now(UTC)
        outcome = run_bounded_command(
            argv=argv,
            cwd=self._repository_root,
            environment=self._environment,
            timeout_seconds=timeout_seconds,
        )
        # Evidence first, and unconditionally: a spawn failure and a timeout keep their transcripts
        # exactly as a completed command does (invariant 15). A spawn failure has no command
        # stderr, so the refusal the operating system gave us is what the stderr transcript holds.
        stderr_text = outcome.stderr if outcome.spawn_error is None else outcome.spawn_error
        sequence = self._store.next_transcript_sequence(lock=self._lock)
        stdout_write = self._write(sequence, moment, TranscriptKind.STDOUT, outcome.stdout)
        stderr_write = self._write(sequence, moment, TranscriptKind.STDERR, stderr_text)
        result = VerificationResult(
            command=list(argv),
            exit_code=outcome.exit_code,
            timed_out=outcome.timed_out,
            passed=outcome.passed,
            duration_ms=outcome.duration_ms,
            stdout_path=_reference(stdout_write),
            stderr_path=_reference(stderr_write),
        )
        return VerificationOutcome(
            result=result,
            stdout=outcome.stdout,
            stderr=stderr_text,
            stdout_truncated=outcome.stdout_truncated,
            stderr_truncated=outcome.stderr_truncated,
            spawn_error=outcome.spawn_error,
            purpose=purpose,
            writes=[stdout_write, stderr_write],
        )

    def run_configured(self, settings: VerificationCommandSettings) -> VerificationOutcome:
        """Run one configured command, taking its argv, timeout and purpose from the settings."""
        return self.run(
            settings.command,
            timeout_seconds=settings.timeout_seconds,
            purpose=settings.purpose,
        )

    def run_set(self, commands: Sequence[VerificationCommandSettings]) -> list[VerificationOutcome]:
        """Run a whole configured set in order and return every outcome.

        Every command runs: a failure does not stop the set, because a run that stops at the first
        red command reports less evidence than the operator needs and the caller decides what a
        failure means anyway.
        """
        return [self.run_configured(settings) for settings in commands]

    def run_governance_gate(
        self,
        checks: Mapping[str, VerificationCommandSettings],
        *,
        required_checks: Sequence[str] = REQUIRED_GOVERNANCE_CHECKS,
    ) -> "GovernanceGateDecision":
        """Run each governance check individually and evaluate the gate from what they emitted.

        Section 16: the checks are run individually rather than as one combined command, so the
        `git` check can be evaluated against its single documented tolerance (section 4 item 7)
        without loosening the other four. Each check's argv comes from validated configuration --
        nothing here hard-codes a `workflowctl` invocation -- and each check's verdict comes from
        the machine-readable document it printed, never from its console rendering and never from
        its exit code (defect P-7).

        Raises :class:`GovernanceContradiction` when the gate is not satisfied, carrying every
        outcome so a stop record can reference the persisted output of each check that ran.
        """
        missing = [name for name in required_checks if name not in checks]
        if missing:
            raise GovernanceContradiction(
                f"The governance gate needs a command for every required check; missing: {missing}"
            )
        unexpected = sorted(set(checks) - set(required_checks))
        if unexpected:
            # Refused rather than skipped: a configured check the gate quietly declined to run
            # would be evidence an operator believes exists and does not.
            raise GovernanceContradiction(
                f"The governance gate was given commands it does not run: {unexpected}"
            )
        outcomes: list[VerificationOutcome] = []
        results: list[GovernanceCheckResult] = []
        for name in required_checks:
            outcome = self.run_configured(checks[name])
            outcomes.append(outcome)
            if outcome.timed_out or outcome.spawn_error is not None:
                raise GovernanceContradiction(
                    f"The {name} governance check did not produce a result "
                    f"({'timed out' if outcome.timed_out else outcome.spawn_error}); the gate "
                    "cannot be evaluated and therefore does not open",
                    outcomes=outcomes,
                )
            results.append(
                parse_governance_check_document(outcome.stdout, check_name=name, outcomes=outcomes)
            )
        try:
            decision = evaluate_governance_gate(results, required_checks=required_checks)
        except GovernanceContradiction as contradiction:
            # Re-raised with the outcomes attached: the pure evaluator cannot know where its
            # inputs came from, and a stop record has to be able to reference the persisted
            # output of every check that ran (invariant 15).
            raise GovernanceContradiction(
                str(contradiction), findings=contradiction.findings, outcomes=outcomes
            ) from contradiction
        return GovernanceGateDecision(
            checks=decision.checks, tolerated=decision.tolerated, outcomes=outcomes
        )

    # -- persistence --------------------------------------------------------------------

    def _write(
        self, sequence: int, moment: datetime, kind: TranscriptKind, text: str
    ) -> RedactedWrite:
        """Persist one stream through the single section 17a boundary, complete and unabridged."""
        return self._store.write_transcript(
            sequence=sequence,
            label=VERIFICATION_TRANSCRIPT_LABEL,
            kind=kind,
            text=text,
            moment=moment,
            lock=self._lock,
        )


def _reference(write: RedactedWrite) -> str:
    """The run-relative path a record references a persisted stream by (section 11)."""
    if write.relative_path is None:
        raise VerificationError(f"{write.path} was written without a run-relative reference")
    return write.relative_path


# --------------------------------------------------------------------------------------
# Section 4 item 7 / section 16 -- the machine-readable governance gate (defect P-7)
# --------------------------------------------------------------------------------------


class GovernanceCheckStatus(StrEnum):
    """The three statuses a governance check document may report.

    Defined here rather than imported from the engine's own result vocabulary so the gate's
    grammar is closed by this package: the gate reads a *document*, and what it will accept in
    that document must not widen because some other module's enum gained a member.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class GovernanceCheckResult(MilestoneRunnerModel):
    """One governance check as its machine-readable document reported it.

    The only three things the gate is allowed to consider: which check this is, what it concluded,
    and the codes of the findings it raised. No summary, no rendering, no exit code.
    """

    check_name: str
    status: GovernanceCheckStatus
    finding_codes: list[str] = Field(default_factory=list)


class GovernanceGateDecision(MilestoneRunnerModel):
    """A satisfied governance gate, and the evidence it was satisfied by.

    Only ever constructed for a gate that opened: :func:`evaluate_governance_gate` raises for
    every other case, so there is no `satisfied=False` value a caller could read past. `tolerated`
    names each finding that was admitted under section 4 item 7's single documented tolerance, so
    an operator sees that something was tolerated rather than having to infer it from silence.
    """

    checks: list[GovernanceCheckResult]
    tolerated: list[str] = Field(default_factory=list)
    outcomes: list[VerificationOutcome] = Field(default_factory=list)


def _rejecting_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a mapping from JSON pairs, refusing a key that appears twice at one level.

    A duplicate key makes a document ambiguous -- two readers can disagree about what it says --
    and a gate that reads an ambiguous document is not a gate.
    """
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError(f"the document names {key!r} twice at one level")
        mapping[key] = value
    return mapping


def parse_governance_check_document(
    text: str,
    *,
    check_name: str,
    outcomes: Sequence["VerificationOutcome"] = (),
) -> GovernanceCheckResult:
    """Read one governance check's machine-readable document, fail-closed at every step.

    This is the whole of defect P-7's correction. The document is JSON with a stable shape --
    `check_name`, `status`, `findings[].code` -- and every deviation from it is a
    :class:`GovernanceContradiction` rather than a best-effort reading. Nothing here looks at a
    rendered table, a box-drawing character, a column position or a locale; there is no console
    output this function could be pointed at that would make it report a PASS.

    The document is also required to identify *itself*: a check that reports a different
    `check_name` than the one the runner asked for is refused, so evidence for one check can never
    be counted as evidence for another.
    """
    if _CHECK_NAME_RE.fullmatch(check_name) is None:
        raise GovernanceContradiction(
            f"{check_name!r} is not a governance check name", outcomes=outcomes
        )
    payload = text.encode("utf-8")
    if len(payload) > MAX_CHECK_DOCUMENT_BYTES:
        raise GovernanceContradiction(
            f"The {check_name} check emitted {len(payload)} bytes, above the "
            f"{MAX_CHECK_DOCUMENT_BYTES}-byte machine-readable document ceiling",
            outcomes=outcomes,
        )
    try:
        document: Any = json.loads(text, object_pairs_hook=_rejecting_duplicate_keys)
    except (ValueError, RecursionError) as exc:
        raise GovernanceContradiction(
            f"The {check_name} check did not emit a machine-readable document: {exc}. The gate is "
            "evaluated from structured results only, never from a rendered console table "
            "(defect P-7)",
            outcomes=outcomes,
        ) from exc
    if not isinstance(document, dict):
        raise GovernanceContradiction(
            f"The {check_name} check's document must be a JSON object", outcomes=outcomes
        )
    mapping: dict[str, Any] = document

    reported = mapping.get("check_name")
    if reported != check_name:
        raise GovernanceContradiction(
            f"The document the {check_name} check emitted identifies itself as {reported!r}; "
            "evidence for one check is never evidence for another",
            outcomes=outcomes,
        )
    raw_status = mapping.get("status")
    if not isinstance(raw_status, str):
        raise GovernanceContradiction(
            f"The {check_name} check's document carries no status", outcomes=outcomes
        )
    try:
        status = GovernanceCheckStatus(raw_status)
    except ValueError as exc:
        raise GovernanceContradiction(
            f"The {check_name} check reported the unknown status {raw_status!r}", outcomes=outcomes
        ) from exc

    raw_findings = mapping.get("findings", [])
    if not isinstance(raw_findings, list):
        raise GovernanceContradiction(
            f"The {check_name} check's findings must be a JSON array", outcomes=outcomes
        )
    codes: list[str] = []
    for index, finding in enumerate(raw_findings):
        if not isinstance(finding, dict):
            raise GovernanceContradiction(
                f"The {check_name} check's findings[{index}] must be a JSON object",
                outcomes=outcomes,
            )
        entry: dict[str, Any] = finding
        code = entry.get("code")
        if not isinstance(code, str) or _FINDING_CODE_RE.fullmatch(code) is None:
            raise GovernanceContradiction(
                f"The {check_name} check's findings[{index}] carries no usable code",
                outcomes=outcomes,
            )
        codes.append(code)
    return GovernanceCheckResult(check_name=check_name, status=status, finding_codes=codes)


def evaluate_governance_gate(
    results: Sequence[GovernanceCheckResult],
    *,
    required_checks: Sequence[str] = REQUIRED_GOVERNANCE_CHECKS,
) -> GovernanceGateDecision:
    """Decide section 4 item 7's gate from structured per-check results.

    Every required check must be present exactly once. The four unconditional checks must have
    concluded `PASS` and raised nothing. The `git` check may raise `upstream_missing` and nothing
    else -- the single tolerance `STAGE_REGISTRY.md` section 3 rule 16 and AUTO-015 section 7.2
    established for a local-only, unpushed stage branch -- and an `ERROR` from any check is a
    contradiction, because a check that could not run has not passed.

    A pure function of typed inputs: it runs nothing, reads no file, writes nothing, and consults
    no governance document. Every deviation raises :class:`GovernanceContradiction`; there is no
    return value that means "not satisfied".
    """
    by_name: dict[str, GovernanceCheckResult] = {}
    for result in results:
        if result.check_name in by_name:
            raise GovernanceContradiction(
                f"Two results were supplied for the {result.check_name} check"
            )
        by_name[result.check_name] = result

    missing = [name for name in required_checks if name not in by_name]
    if missing:
        raise GovernanceContradiction(
            f"The governance gate needs a result for every required check; missing: {missing}"
        )
    unexpected = sorted(set(by_name) - set(required_checks))
    if unexpected:
        raise GovernanceContradiction(
            f"The governance gate was handed results it did not ask for: {unexpected}"
        )

    contradictions: list[str] = []
    tolerated: list[str] = []
    for name in required_checks:
        result = by_name[name]
        allowed = TOLERATED_GIT_FINDING_CODES if name == GOVERNANCE_GIT_CHECK else _NO_TOLERANCE
        for code in result.finding_codes:
            if code in allowed:
                tolerated.append(f"{name}:{code}")
            else:
                contradictions.append(f"{name}:{code}")
        if result.status is GovernanceCheckStatus.ERROR:
            contradictions.append(f"{name}:CHECK_ERROR")
        elif result.status is GovernanceCheckStatus.FAIL and not result.finding_codes:
            # A FAIL that names no finding cannot be measured against a tolerance, so it is not
            # tolerable: the gate refuses rather than guessing what failed.
            contradictions.append(f"{name}:CHECK_FAIL_WITHOUT_FINDING")
    if contradictions:
        raise GovernanceContradiction(
            "The canonical governance checks are not satisfied: "
            f"{contradictions}. Section 4 item 7 tolerates exactly one finding -- "
            f"{sorted(TOLERATED_GIT_FINDING_CODES)} on the {GOVERNANCE_GIT_CHECK} check -- and "
            "nothing else",
            findings=contradictions,
        )
    return GovernanceGateDecision(
        checks=[by_name[name] for name in required_checks], tolerated=tolerated
    )
