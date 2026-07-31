"""The public Provider Runtime boundary (AUTO-010).

One layer, one job: turn a request naming a provider and a task into a real, non-interactive CLI
execution and a typed terminal result::

    WorkflowService
        -> ProviderRuntime.invoke(ProviderRunRequest) -> ProviderRunResult
            -> ClaudeCLIProvider / CodexCLIProvider
                -> base.run_provider_process

Everything below this module already existed (AUTO-004). This module is deliberately *not* a
second provider framework: it owns no subprocess call, no argv, no environment handling, no
timeout, and no session layout. It owns exactly three things the layer below cannot own — the
auto-mode prompt contract, the mapping from a closed provider target to a selected provider, and
the terminal-result contract that decides whether what came back is a result at all.

**Why a boundary rather than exposing the providers.** `CLIProvider.invoke` takes a
`ProviderInvocation` whose `prompt` is whatever the caller wrote. That is the right shape for the
layer that runs a process and the wrong shape for a public API, because a caller who writes the
whole prompt can omit the never-ask clauses, and the strongest of the three enforcement layers
would then be optional. Here the caller supplies a *task* and the runtime supplies the contract
around it, so no call site can produce a provider prompt that lacks it.

**What this module cannot do.** It cannot start, advance, approve, or record a workflow: it holds
no `StateStore`, no `RepositoryLock`, and no `WorkflowSession`, and it imports none of them. A
provider execution therefore cannot transition workflow state by itself, structurally, and not
because a comment says so. Choosing *when* to invoke a provider and what to do with the result
belongs to the Orchestrator and to stages after this one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers.base import (
    CLIProvider,
    ProviderFailure,
    ProviderFailureKind,
    ProviderInvocation,
    ProviderKind,
    ProviderReport,
    ProviderResult,
    ProviderRole,
    ProviderRunStatus,
)
from agentos_workflow.providers.selection import select_live_provider
from agentos_workflow.skills import CommandExecution, redact_secrets, utc_now

__all__ = [
    "AUTO_MODE_PROMPT_CONTRACT",
    "STDERR_ARTIFACT_FILENAME",
    "STDOUT_ARTIFACT_FILENAME",
    "ProviderRunRequest",
    "ProviderRunResult",
    "ProviderRuntime",
    "ProviderRuntimeTarget",
    "build_provider_prompt",
]

#: Filenames for the captured output this runtime persists into the invocation's own session
#: directory. Fixed rather than configurable: an audit reader should not have to be told where an
#: invocation's evidence is.
STDOUT_ARTIFACT_FILENAME = "stdout.txt"
STDERR_ARTIFACT_FILENAME = "stderr.txt"


class ProviderRuntimeTarget(StrEnum):
    """Which provider a request selects. A closed set of exactly two.

    Named for the CLI rather than for a workflow role because that is the honest description of
    what a caller is choosing at this boundary: "run Claude" or "run Codex". `ProviderRole`
    (implementation / repair / QA) stays the layer below's vocabulary, and the mapping between the
    two lives in `_ROLE_FOR_TARGET` — one place, matching the existing selection registry's
    defaults rather than restating them.
    """

    CLAUDE = "claude"
    CODEX = "codex"


#: Target to role, and thence to provider through the existing live-selection registry. This is the
#: only place the two vocabularies meet. The role also becomes the invocation's audit identity, and
#: is carried for that reason alone: AUTO-010 implements no workflow lifecycle, so nothing here
#: acts on the role's workflow meaning.
_ROLE_FOR_TARGET: Mapping[ProviderRuntimeTarget, ProviderRole] = MappingProxyType(
    {
        ProviderRuntimeTarget.CLAUDE: ProviderRole.IMPLEMENTATION,
        ProviderRuntimeTarget.CODEX: ProviderRole.QA,
    }
)


AUTO_MODE_PROMPT_CONTRACT = """\
You are running as a non-interactive automation provider inside the AgentOS workflow engine.

Do not ask the user questions.

Do not pause for clarification.

Inspect available evidence and proceed using only safe,
scope-preserving assumptions.

If safe continuation is impossible, return a structured BLOCKED result.

No terminal is attached to this session and no human is reading its output while it runs. Your
standard input is closed after this prompt, so a question cannot be answered, and a run that waits
for one is terminated by timeout and recorded as a failure.

## Required output

Your final message must be exactly one JSON object and nothing else: no prose before or after it.
It has this shape, and every field it names must be present:

{
  "status": "completed" | "completed_with_assumptions" | "blocked" | "failed",
  "verdict": "pass" | "fail",
  "summary": "one sentence describing what you actually did",
  "assumptions": ["each safe, scope-preserving assumption you relied on"],
  "blocking_issues": ["each concrete reason safe continuation was impossible"],
  "files_changed": ["repository-relative path of each file you actually changed"],
  "validation_performed": ["each command or check you actually ran"],
  "findings": ["each defect you found, when the task was a review"]
}

Rules this engine enforces mechanically, so a violation fails the run:

- "completed_with_assumptions" requires at least one entry in "assumptions".
- "blocked" requires at least one entry in "blocking_issues", each naming concrete evidence.
- "failed" is for an execution failure you could not recover from.
- Use empty lists, never omitted fields, where you have nothing to report.
- Never list a file as changed unless you actually changed it, and never report a validation you
  did not actually run.

## Task

"""


def build_provider_prompt(task: str) -> str:
    """Wrap one task in the auto-mode contract (`AUTO-010` never-ask layer 1).

    The contract goes first and the task second, and the caller supplies only the second half.
    That ordering is not cosmetic: a task that tries to countermand the contract — including one
    assembled from untrusted target-repository content — is read as part of the work to be done,
    after the rules, rather than as a replacement for them.
    """
    return f"{AUTO_MODE_PROMPT_CONTRACT}{task.strip()}\n"


@dataclass(frozen=True)
class ProviderRunRequest:
    """One provider execution, as asked for from outside this package.

    Note what a caller cannot say here: no executable path, no CLI flag, no permission or sandbox
    mode, no timeout, and no environment. Every one of those is configuration
    (`WorkflowConfig`) or a provider-owned constant, so the public request cannot widen what a
    provider is allowed to do — the worst a caller can do is choose which of two providers runs.

    `working_directory` and `session_root` are the caller's because they are facts about the
    deployment, not policy: which checkout to work in, and where invocation scratch belongs. Both
    are validated by the provider layer before anything is spawned.
    """

    target: ProviderRuntimeTarget
    workflow_id: str
    stage_id: str
    task: str
    working_directory: Path
    session_root: Path
    invocation_id: str


@dataclass(frozen=True)
class ProviderRunResult:
    """The typed terminal result of one provider execution.

    Every invocation produces exactly one of these, including the ones that failed to spawn, timed
    out, or returned something unreadable. There is no path out of `ProviderRuntime.invoke` that
    raises, and no path that returns conversational text: an execution either reached one of the
    four statuses or is recorded as `FAILED` with a typed cause.

    The invariants below are checked on construction because they are what makes the status
    *mean* something. A `BLOCKED` result with no blocking issue is indistinguishable from a
    provider that wanted to ask a question, and a `COMPLETED_WITH_ASSUMPTIONS` result with no
    assumption is an unrecorded assumption — the exact failure this stage exists to prevent. They
    raise rather than returning a failure because reaching them means this module built a result
    wrongly, which is a defect in the engine and not an outcome of the run; every provider-caused
    version of the same violation is rejected earlier, during report parsing, and arrives here as
    an ordinary `FAILED`.
    """

    provider: ProviderKind
    status: ProviderRunStatus
    summary: str
    session_id: str
    #: Timezone-aware, from the engine's single timestamp source, and measuring *this boundary's*
    #: work rather than only the child process's: a request refused before spawn still has an
    #: honest interval, and the process's own start/completion stay on its `CommandExecution`.
    started_at: datetime
    completed_at: datetime
    exit_code: int | None
    stdout_artifact: Path | None
    stderr_artifact: Path | None
    assumptions: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    failure: ProviderFailure | None
    #: The parsed CLI report, when there was one. Carried rather than flattened so nothing the
    #: provider reported (verdict, files changed, validation performed, findings) is lost at this
    #: boundary, and so AUTO-011 has the whole thing to build its unified result from.
    report: ProviderReport | None = None

    def __post_init__(self) -> None:
        if self.status is ProviderRunStatus.BLOCKED and not self.blocking_issues:
            raise ValueError("a BLOCKED result requires at least one blocking issue")
        if self.status is ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS and not self.assumptions:
            raise ValueError("a COMPLETED_WITH_ASSUMPTIONS result requires at least one assumption")
        if self.status is ProviderRunStatus.FAILED and self.failure is None:
            raise ValueError("a FAILED result requires a typed failure")
        if self.status is not ProviderRunStatus.FAILED and self.failure is not None:
            raise ValueError(f"a {self.status.value} result must carry no failure")

    @property
    def succeeded(self) -> bool:
        """Whether the provider finished its work, with or without recorded assumptions.

        `BLOCKED` is deliberately not success: it is a well-formed report that the work was *not*
        done. Treating it as success is precisely the mistake that would let an unfinished stage
        advance.
        """
        return self.status in (
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS,
        )


class ProviderRuntime:
    """Runs one provider, once, non-interactively (AUTO-010).

    Stateless between invocations by construction: it holds only the validated configuration, and
    a fresh provider instance is selected per call, so nothing an invocation learns can leak into
    the next one.
    """

    def __init__(self, config: WorkflowConfig) -> None:
        self._config = config

    def invoke(self, request: ProviderRunRequest) -> ProviderRunResult:
        """Execute one provider run and return its terminal result. Never raises.

        The sequence is: select the provider for the requested target, wrap the task in the
        auto-mode contract, hand the whole thing to the provider layer, persist the captured
        output into the invocation's own session directory, and classify what came back. Nothing
        here spawns a process or names a CLI flag — those belong to the layer below, and this
        method would be the wrong place to duplicate either.
        """
        started_at = utc_now()
        provider = self.provider_for(request.target)

        if not request.task.strip():
            # Refused here rather than downstream: the provider layer would see the contract text
            # and a non-empty prompt, so an empty task is invisible to it by the time it arrives.
            return self._pre_execution_failure(
                provider,
                request,
                started_at,
                ProviderFailureKind.UNSAFE_INPUT,
                "task is empty",
            )

        invocation = ProviderInvocation(
            workflow_id=request.workflow_id,
            stage_id=request.stage_id,
            role=_ROLE_FOR_TARGET[request.target],
            prompt=build_provider_prompt(request.task),
            working_directory=request.working_directory,
            session_root=request.session_root,
            invocation_id=request.invocation_id,
        )
        result = provider.invoke(invocation)
        completed_at = utc_now()

        session_directory = provider.session_directory(invocation)
        execution = _execution_of(result)
        stdout_artifact, stderr_artifact = _persist_artifacts(session_directory, execution)

        return self._classify(
            provider=provider,
            request=request,
            result=result,
            execution=execution,
            started_at=started_at,
            completed_at=completed_at,
            stdout_artifact=stdout_artifact,
            stderr_artifact=stderr_artifact,
        )

    def provider_for(self, target: ProviderRuntimeTarget) -> CLIProvider:
        """The provider a target selects, built from this runtime's configuration.

        Routed through `providers.selection.select_live_provider` rather than a mapping of its own,
        so this stage adds no second provider registry: the role-to-provider assignment stays in
        the one place `MODEL_PROVIDER_CONTRACTS.md` §8 put it. Its return type is `CLIProvider`,
        which is what keeps `MockProvider` unreachable from here — it subclasses `Provider`
        directly and cannot be produced by this path at all.
        """
        return select_live_provider(_ROLE_FOR_TARGET[target], self._config)

    def _classify(
        self,
        *,
        provider: CLIProvider,
        request: ProviderRunRequest,
        result: ProviderResult,
        execution: CommandExecution | None,
        started_at: datetime,
        completed_at: datetime,
        stdout_artifact: Path | None,
        stderr_artifact: Path | None,
    ) -> ProviderRunResult:
        """Decide which of the four terminal statuses this execution reached.

        Three cases, in order. A typed failure from the provider layer — spawn failure, timeout,
        non-zero exit, unreadable or contract-violating output — is `FAILED` carrying that
        failure. A well-formed report with no `status` field is *also* `FAILED`: the auto-mode
        contract requires the field, and a report that omits it has not said how the run ended, so
        inferring one from the pass/fail verdict would manufacture the very claim this stage is
        supposed to verify. Otherwise the report's own status is the result's status.
        """

        def build(
            *,
            status: ProviderRunStatus,
            summary: str,
            assumptions: tuple[str, ...],
            blocking_issues: tuple[str, ...],
            failure: ProviderFailure | None,
            report: ProviderReport | None,
        ) -> ProviderRunResult:
            """The fields every branch shares, named once."""
            return ProviderRunResult(
                provider=provider.kind,
                status=status,
                summary=summary,
                session_id=_session_id(provider.kind, request),
                started_at=started_at,
                completed_at=completed_at,
                exit_code=None if execution is None else execution.exit_code,
                stdout_artifact=stdout_artifact,
                stderr_artifact=stderr_artifact,
                assumptions=assumptions,
                blocking_issues=blocking_issues,
                failure=failure,
                report=report,
            )

        if not result.ok or result.value is None:
            failure = result.error
            if failure is None:  # pragma: no cover - `provider_failure` always sets one
                failure = ProviderFailure(
                    provider=provider.kind,
                    kind=ProviderFailureKind.COMMAND_FAILED,
                    detail="provider returned a failed result with no failure attached",
                )
            return build(
                status=ProviderRunStatus.FAILED,
                summary=str(failure),
                assumptions=(),
                blocking_issues=(),
                failure=failure,
                report=None,
            )

        report = result.value
        if report.status is None:
            return build(
                status=ProviderRunStatus.FAILED,
                summary=(
                    "provider report omitted the required auto-mode 'status' field; "
                    "the run has no terminal result"
                ),
                assumptions=report.assumptions,
                blocking_issues=report.blocking_issues,
                failure=ProviderFailure(
                    provider=provider.kind,
                    kind=ProviderFailureKind.MALFORMED_OUTPUT,
                    detail=(
                        "report omitted the required auto-mode 'status' field: "
                        f"{redact_secrets(report.summary)}"
                    ),
                    execution=execution,
                ),
                report=report,
            )

        # A provider that reports its own failure has produced a valid result about an invalid
        # run. It keeps a typed failure so the outcome is branchable exactly like an engine-
        # detected one, distinguished by kind rather than by whether a failure is present at all.
        failure = (
            ProviderFailure(
                provider=provider.kind,
                kind=ProviderFailureKind.PROVIDER_REPORTED,
                detail=f"provider reported a failed execution: {report.summary}",
                execution=execution,
            )
            if report.status is ProviderRunStatus.FAILED
            else None
        )
        return build(
            status=report.status,
            summary=report.summary,
            assumptions=report.assumptions,
            blocking_issues=report.blocking_issues,
            failure=failure,
            report=report,
        )

    def _pre_execution_failure(
        self,
        provider: CLIProvider,
        request: ProviderRunRequest,
        started_at: datetime,
        kind: ProviderFailureKind,
        detail: str,
    ) -> ProviderRunResult:
        """A `FAILED` result for a request refused before any process was spawned."""
        return ProviderRunResult(
            provider=provider.kind,
            status=ProviderRunStatus.FAILED,
            summary=detail,
            session_id=_session_id(provider.kind, request),
            started_at=started_at,
            completed_at=utc_now(),
            exit_code=None,
            stdout_artifact=None,
            stderr_artifact=None,
            assumptions=(),
            blocking_issues=(),
            failure=ProviderFailure(
                provider=provider.kind, kind=kind, detail=redact_secrets(detail)
            ),
            report=None,
        )


def _session_id(kind: ProviderKind, request: ProviderRunRequest) -> str:
    """This invocation's session identity: the same three segments that key its directory."""
    return f"{request.workflow_id}/{kind.value}/{request.invocation_id}"


def _execution_of(result: ProviderResult) -> CommandExecution | None:
    """The command-execution record, from whichever half of the result carries it."""
    if result.ok and result.value is not None:
        return result.value.execution
    return None if result.error is None else result.error.execution


def _persist_artifacts(
    session_directory: Path, execution: CommandExecution | None
) -> tuple[Path | None, Path | None]:
    """Write this invocation's captured stdout and stderr into its own session directory.

    The **redacted** text is what gets written, because these files persist: they are the evidence
    an operator reads after the run, and the unredacted stdout exists only long enough to be
    parsed (see `ProviderExecution`). Writing is best-effort — a failure to persist evidence must
    not turn a successful provider run into a failed one — so an unwritable directory yields
    `None` for that artifact and nothing else changes.

    There is no artifact when nothing ran: a request refused before spawn has no output to record,
    and inventing an empty file would suggest a process produced no output rather than that no
    process existed.
    """
    if execution is None:
        return (None, None)
    return (
        _write_artifact(session_directory / STDOUT_ARTIFACT_FILENAME, execution.stdout),
        _write_artifact(session_directory / STDERR_ARTIFACT_FILENAME, execution.stderr),
    )


def _write_artifact(path: Path, content: str) -> Path | None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError:
        return None
    return path
