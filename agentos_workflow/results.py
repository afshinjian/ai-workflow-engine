"""The canonical run-result contract (AUTO-011).

One result type for every execution this engine performs, now and later::

    WorkflowService
        -> ProviderRuntime.invoke -> ProviderRunResult
            -> agent_run_result_from_provider_run -> AgentRunResult

`AgentRunResult` is what a Claude execution, a Codex execution, a future internal agent, and the
future Preparation, Reviewer, and Implementer Modes all produce. AUTO-011 implements none of those
modes and no workflow lifecycle: this module standardizes the *shape* of an execution outcome and
nothing else. It holds no `StateStore`, no `RepositoryLock`, no `WorkflowSession`, and no provider;
it cannot start, advance, approve, or record anything, and it spawns no process.

**Why a new type rather than promoting `ProviderRunResult`.** AUTO-010's result is the Provider
Runtime's boundary type and callers depend on it unchanged, so it stays exactly as it is. It is
also provider-shaped in ways a unified contract cannot be: it has no execution mode, no agent
identity, no artifact vocabulary beyond stdout/stderr, and no place for a producer's own read of
what should happen next. The canonical result is reached from it by an adapter
(`agent_run_result_from_provider_run`), which is a projection, not a replacement.

**What is deliberately reused rather than redeclared.** `ProviderRunStatus` supplies the four
terminal statuses, `ProviderVerdict` the pass/fail axis, `ProviderFailureKind` and
`RetryClassification` the failure taxonomy, `ProviderKind` the provider identity, `AgentKind` the
agent identity, and `WorkflowState` the state vocabulary. Declaring parallel versions of any of
them would create two answers to one question plus a mapping between them that can silently drift,
which is the specific failure a "unified" contract exists to prevent.

**Authority.** `recommended_next_state` is advisory and nothing more. Nothing in this module
transitions a workflow, authorizes a transition, or is consulted by anything that does; the field
is a record of what the producer thought, kept because an operator and a future Orchestrator both
benefit from seeing it, and it is never a substitute for the Orchestrator's own deterministic
validation. `AGENT_CONTRACTS.md` §1 and `ARCHITECTURE.md` §6 are unchanged: an agent reports, the
Orchestrator decides.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from agentos_workflow.agents import AgentKind
from agentos_workflow.orchestrator.engine import WorkflowState
from agentos_workflow.providers.base import (
    ProviderFailure,
    ProviderFailureKind,
    ProviderKind,
    ProviderReport,
    ProviderRunStatus,
    ProviderVerdict,
    strict_json_loads,
)
from agentos_workflow.providers.runtime import ProviderRunResult
from agentos_workflow.skills import RetryClassification, redact_secrets

__all__ = [
    "STDERR_LIMIT_DETAIL_PREFIX",
    "STDOUT_LIMIT_DETAIL_PREFIX",
    "AgentRunResult",
    "ArtifactKind",
    "ArtifactReference",
    "ExecutionMode",
    "RunFailure",
    "RunStatus",
    "agent_run_result_from_provider_run",
]

#: The canonical result's status vocabulary *is* AUTO-010's, exported under a producer-neutral name
#: because agents and modes will reach for it too. This is an alias, not a second enum: the
#: identity `RunStatus is ProviderRunStatus` holds and is asserted by a test, so there is exactly
#: one set of terminal statuses in the engine and no mapping between two of them can drift.
RunStatus = ProviderRunStatus

#: The two engine-generated failure details that mean "a stream hit its ceiling"
#: (`providers/base.py`). AUTO-010 records an output-limit breach as `MALFORMED_OUTPUT` with one of
#: these prefixes rather than as a distinct failure kind, and this stage may not change that
#: classification. Matching the prefix is therefore how the canonical failure recovers the
#: output-limit fact — coupled to wording, and so pinned by a test that provokes a real breach
#: through the real process runner rather than by rebuilding the string here.
STDOUT_LIMIT_DETAIL_PREFIX = "stdout exceeds "
STDERR_LIMIT_DETAIL_PREFIX = "stderr exceeds "


class _ResultModel(BaseModel):
    """`extra="forbid"`, `frozen=True` — the convention every record model in this package uses.

    Forbidding extras is what makes an unknown field an error instead of silently discarded data,
    and freezing is what lets a result be passed around, cached, and compared without a caller
    being able to edit an outcome after the fact.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionMode(StrEnum):
    """What kind of execution produced a result.

    A closed set, because an unknown mode in an audit trail is not information. Naming a mode here
    implements nothing: `PREPARATION`, `REVIEW`, and `IMPLEMENTATION` exist so that the canonical
    result can *type* the modes AUTO-011 was chartered to serve, and no code in this engine
    produces them yet. `PROVIDER_INVOCATION` is the one mode that has a producer today — a direct
    `ProviderRuntime.invoke` with no workflow mode around it, which is exactly what AUTO-010
    delivered.
    """

    PROVIDER_INVOCATION = "provider_invocation"
    PREPARATION = "preparation"
    REVIEW = "review"
    IMPLEMENTATION = "implementation"


class ArtifactKind(StrEnum):
    """What a referenced artifact *is*, so a reader never has to infer it from a filename."""

    STDOUT = "stdout"
    STDERR = "stderr"
    PROVIDER_REPORT = "provider_report"
    SESSION_DIRECTORY = "session_directory"
    CHANGED_FILE_EVIDENCE = "changed_file_evidence"
    TEST_RESULT_EVIDENCE = "test_result_evidence"


def _safe_reference_path(value: str) -> str:
    """Validate and redact one artifact path.

    Confinement is enforced by refusing the constructs that defeat it rather than by resolving
    against a root this module does not know: a `..` segment is the one way a stored reference
    escapes wherever a reader joins it, and a NUL byte is how a path means one thing to a validator
    and another to the kernel. Both are refused outright.

    Redaction runs last and applies to the path itself, because a session or repository path can
    embed a credential (a token in a directory name, a URL with userinfo) and this string is
    written to results that are stored and surfaced.
    """
    if not value:
        raise ValueError("artifact path must not be empty")
    if "\x00" in value:
        raise ValueError("artifact path must not contain a NUL byte")
    if any(part == ".." for part in PurePosixPath(value).parts):
        raise ValueError(f"artifact path must not contain a '..' segment: {value!r}")
    return redact_secrets(value)


class ArtifactReference(_ResultModel):
    """A pointer to evidence, never the evidence itself.

    Embedding content would put unbounded, unredacted bytes inside a result that is meant to be
    stored, compared, and serialized — the same reason AUTO-010 writes `stdout.txt`/`stderr.txt`
    into the invocation's own session directory and keeps only the path. A reader that wants the
    bytes opens the file, under whatever confinement its own layer enforces.
    """

    kind: ArtifactKind
    path: str

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _safe_reference_path(value)


class RunFailure(_ResultModel):
    """Why an execution failed, preserved as a classification rather than flattened to prose.

    A projection of `ProviderFailure`, not a duplicate of it, and the difference is deliberate.
    `ProviderFailure` carries a whole `CommandExecution` — including captured stdout and stderr —
    which a canonical result must not embed (see `ArtifactReference`). What survives here is
    everything a caller can branch on: the typed `kind`, the redacted `detail`, the
    `retry_classification` that answers both "may this be retried" and "could the work already
    have taken effect" (one field, because `SKILL_CONTRACTS.md` §5 makes them one question), and
    two booleans recovering facts the kind alone cannot express.

    `timed_out` and `output_limit_exceeded` exist because AUTO-010 collapses an output-limit breach
    into `MALFORMED_OUTPUT`, so `kind` alone cannot distinguish "the model emitted garbage" from
    "the model emitted more than the ceiling allows" — two failures with different responses.
    """

    kind: ProviderFailureKind
    detail: str
    retry_classification: RetryClassification
    provider: ProviderKind | None = None
    timed_out: bool = False
    output_limit_exceeded: bool = False

    @field_validator("detail")
    @classmethod
    def _redact_detail(cls, value: str) -> str:
        return redact_secrets(value)

    @model_validator(mode="after")
    def _timeout_is_recorded(self) -> Self:
        """A `TIMEOUT` failure that does not say it timed out is a contradiction.

        Checked in one direction only: a failure may be recorded as timed out under another kind
        (a process killed at its ceiling is terminated the same way), so the reverse is a legal
        combination rather than an error.
        """
        if self.kind is ProviderFailureKind.TIMEOUT and not self.timed_out:
            raise ValueError("a TIMEOUT failure must record timed_out=True")
        return self

    @classmethod
    def from_provider_failure(cls, failure: ProviderFailure) -> RunFailure:
        """Project one AUTO-010 typed failure into the canonical form. Total, and lossless for
        every field a caller can branch on."""
        execution = failure.execution
        timed_out = failure.kind is ProviderFailureKind.TIMEOUT or (
            execution is not None and execution.timeout_status
        )
        return cls(
            kind=failure.kind,
            detail=failure.detail,
            retry_classification=failure.retry_classification,
            provider=failure.provider,
            timed_out=timed_out,
            output_limit_exceeded=failure.detail.startswith(
                (STDOUT_LIMIT_DETAIL_PREFIX, STDERR_LIMIT_DETAIL_PREFIX)
            ),
        )


class AgentRunResult(_ResultModel):
    """One execution's canonical outcome.

    Every field earns its place by answering a question a caller must be able to ask without
    reaching past this boundary: *which workflow and which invocation* (`workflow_id`,
    `session_id`), *what kind of execution and who ran it* (`mode`, `provider`, `agent`), *how it
    ended* (`status`, `summary`, `failure`, `exit_code`, `final_verdict`), *what it relied on or
    was stopped by* (`assumptions`, `blocking_issues`), *what it actually did* (`changed_files`,
    `tests_run`), *where the evidence is* (`artifacts`), *when and for how long* (`started_at`,
    `completed_at`, `duration_seconds`), and *what the producer thinks should happen next*
    (`recommended_next_state`, advisory only).

    The status invariants are enforced on construction because they are what makes a status mean
    something. A `BLOCKED` result with no blocking issue is indistinguishable from a producer that
    wanted to ask a question; a `COMPLETED_WITH_ASSUMPTIONS` result with no assumption is an
    unrecorded assumption; a `COMPLETED` result carrying a failure or a blocking issue claims two
    contradictory things at once.
    """

    workflow_id: str
    session_id: str
    mode: ExecutionMode
    provider: ProviderKind | None
    agent: AgentKind | None
    status: ProviderRunStatus
    summary: str
    assumptions: tuple[str, ...] = ()
    blocking_issues: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    tests_run: tuple[str, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    started_at: datetime
    completed_at: datetime
    #: Seconds between `started_at` and `completed_at`, stored so it survives serialization and
    #: cross-checked so it can never disagree with them. Filled automatically when a caller omits
    #: it; a supplied value that contradicts the interval is an error rather than a second opinion.
    duration_seconds: float
    exit_code: int | None = None
    failure: RunFailure | None = None
    final_verdict: ProviderVerdict | None = None
    #: **Advisory only.** Never read by anything that transitions a workflow. See the module
    #: docstring; `TestAuthorityBoundaries` proves no transition depends on it.
    recommended_next_state: WorkflowState | None = None

    @field_validator("summary")
    @classmethod
    def _redact_summary(cls, value: str) -> str:
        return redact_secrets(value)

    @field_validator("assumptions", "blocking_issues", "tests_run")
    @classmethod
    def _redact_entries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Redact each entry, preserving order: an assumption list and a validation list are
        sequences whose order is part of what they report."""
        return tuple(redact_secrets(entry) for entry in value)

    @field_validator("changed_files")
    @classmethod
    def _normalize_changed_files(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Redact, de-duplicate, and sort the changed-file set.

        A changed-file list is a *set* of paths — naming the same file twice says nothing more than
        naming it once, and the order a producer happened to emit them in carries no information.
        Normalizing here is what makes two results for the same work serialize identically, and it
        matches the sorted-and-unique rule the legacy `AgentReport` already enforces.

        Deliberately *not* rejected here: an absolute path or one containing `..`. The provider
        layer does not validate what a model claims it changed, so rejecting would make the adapter
        fail on real output; these strings are a producer's claim to be verified elsewhere, never a
        path this engine opens. `ArtifactReference`, which *is* a path a reader follows, is strict.
        """
        return tuple(sorted({redact_secrets(entry) for entry in value}))

    @field_validator("started_at", "completed_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        """A naive timestamp cannot be safely compared against another (Python raises mixing naive
        and aware), which would silently defeat the ordering check below — the same rule the state
        store applies to every persisted audit timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="before")
    @classmethod
    def _fill_duration(cls, data: Any) -> Any:
        """Supply `duration_seconds` when the caller omitted it.

        Runs before field validation so a constructed result and a parsed one take the same path.
        Only fills; a supplied value is left alone for `_validate_consistency` to check, so a
        round-tripped result is verified rather than quietly recomputed.

        Both timestamps must already be timezone-aware to be subtracted at all — Python raises
        mixing naive and aware — so an ill-formed pair is left untouched here and reported by
        `_require_timezone_aware`, which says what is actually wrong. Computing first would
        surface a `TypeError` about subtraction instead of the real defect.
        """
        if not isinstance(data, dict) or "duration_seconds" in data:
            return data
        started, completed = data.get("started_at"), data.get("completed_at")
        if (
            isinstance(started, datetime)
            and isinstance(completed, datetime)
            and started.tzinfo is not None
            and completed.tzinfo is not None
        ):
            return {**data, "duration_seconds": (completed - started).total_seconds()}
        return data

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        """Every cross-field rule, in one place so none of them can be satisfied in isolation."""
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        expected = (self.completed_at - self.started_at).total_seconds()
        if self.duration_seconds != expected:
            raise ValueError(
                f"duration_seconds {self.duration_seconds} contradicts the interval "
                f"({expected} seconds) between started_at and completed_at"
            )
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative")

        if self.provider is None and self.agent is None:
            raise ValueError("a result must name a producer: provider, agent, or both")

        if self.status is ProviderRunStatus.BLOCKED and not self.blocking_issues:
            raise ValueError("a BLOCKED result requires at least one blocking issue")
        if self.status is ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS and not self.assumptions:
            raise ValueError("a COMPLETED_WITH_ASSUMPTIONS result requires at least one assumption")
        if self.status is ProviderRunStatus.FAILED and self.failure is None:
            raise ValueError("a FAILED result requires a typed failure")
        if self.status is not ProviderRunStatus.FAILED and self.failure is not None:
            raise ValueError(f"a {self.status.value} result must carry no failure")
        if self.status is ProviderRunStatus.COMPLETED and self.blocking_issues:
            raise ValueError("a COMPLETED result must carry no blocking issues")
        return self

    @property
    def succeeded(self) -> bool:
        """Whether the work finished, with or without recorded assumptions.

        `BLOCKED` is deliberately not success — it is a well-formed report that the work was *not*
        done, and treating it as success is precisely what would let an unfinished stage advance.
        Matches `ProviderRunResult.succeeded` exactly, so the projection does not change the
        question's answer.
        """
        return self.status in (
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.COMPLETED_WITH_ASSUMPTIONS,
        )

    def to_canonical_json(self) -> str:
        """Serialize deterministically: sorted keys, fixed separators, no incidental whitespace.

        Sorting by key rather than trusting field-declaration order means the bytes stay stable
        even if this class's fields are later reordered, so a stored result and a freshly produced
        one can be compared as text and a digest over the output means something.
        """
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def from_canonical_json(cls, text: str) -> AgentRunResult:
        """Parse a canonical result, rejecting duplicate keys and unknown fields.

        Parsing goes through `strict_json_loads`, the package's only JSON entry point, so an object
        naming the same key twice is an ambiguous document rather than one with a silent winner —
        `json.loads` would keep the last value and hide the first. Unknown fields are refused by
        `extra="forbid"` and every invariant above is re-checked, so a result that was edited on
        disk into an illegal shape does not load.
        """
        return cls.model_validate(strict_json_loads(text))


def agent_run_result_from_provider_run(
    result: ProviderRunResult,
    *,
    workflow_id: str,
    mode: ExecutionMode = ExecutionMode.PROVIDER_INVOCATION,
    agent: AgentKind | None = None,
    session_directory: Path | None = None,
) -> AgentRunResult:
    """Project one AUTO-010 provider run into the canonical result. The compatibility layer.

    Total for every `ProviderRunResult` the Provider Runtime can construct, and a pure field copy
    for all but one of them. Nothing is inferred: `final_verdict`, `changed_files`, and `tests_run`
    come from the parsed report when there was one and stay absent when there was not, because an
    absent claim must not become an empty claim that looks checked.

    `workflow_id` is a parameter rather than a field read off the result because AUTO-010's
    `ProviderRunResult` does not carry one — its `session_id` embeds it as a path segment, and
    recovering it by splitting a string would invent structure the producer never promised.

    `recommended_next_state` is always `None` here, and that is the point. A provider run says how
    an execution ended; deciding what a workflow should do next is the Orchestrator's, and an
    adapter that guessed a next state from a status would be exactly the invented transition this
    stage's authority rule forbids.

    **The one non-copy.** A provider that reports `COMPLETED` while also naming blocking issues has
    violated the auto-mode output contract — it claims both that the work finished and that
    something stopped it. AUTO-010 permits that shape (recorded as deferred finding D-8), the
    canonical contract does not, and neither dropping the blockers nor raising is acceptable:
    dropping erases the only evidence something was wrong, and raising would make the adapter
    partial. It is therefore recorded as `FAILED` with a `MALFORMED_OUTPUT` failure naming the
    contradiction, which is precisely how AUTO-010 already classifies every other violation of that
    same contract. Nothing is lost — the summary and the blocking issues are both preserved.
    """
    report: ProviderReport | None = result.report
    status = result.status
    failure = None if result.failure is None else RunFailure.from_provider_failure(result.failure)

    if status is ProviderRunStatus.COMPLETED and result.blocking_issues:
        status = ProviderRunStatus.FAILED
        failure = RunFailure(
            kind=ProviderFailureKind.MALFORMED_OUTPUT,
            detail=(
                "provider reported status 'completed' while naming blocking issues: "
                f"{'; '.join(result.blocking_issues)}"
            ),
            retry_classification=RetryClassification.NON_RETRYABLE,
            provider=result.provider,
        )

    artifacts: list[ArtifactReference] = []
    if session_directory is not None:
        artifacts.append(
            ArtifactReference(kind=ArtifactKind.SESSION_DIRECTORY, path=str(session_directory))
        )
    if result.stdout_artifact is not None:
        artifacts.append(
            ArtifactReference(kind=ArtifactKind.STDOUT, path=str(result.stdout_artifact))
        )
    if result.stderr_artifact is not None:
        artifacts.append(
            ArtifactReference(kind=ArtifactKind.STDERR, path=str(result.stderr_artifact))
        )

    return AgentRunResult(
        workflow_id=workflow_id,
        session_id=result.session_id,
        mode=mode,
        provider=result.provider,
        agent=agent,
        status=status,
        summary=result.summary,
        assumptions=result.assumptions,
        blocking_issues=result.blocking_issues,
        changed_files=() if report is None else report.files_changed,
        tests_run=() if report is None else report.validation_performed,
        artifacts=tuple(artifacts),
        started_at=result.started_at,
        completed_at=result.completed_at,
        # Passed explicitly rather than left to the model's filler, so this call names every field
        # the type checker requires. The cross-check in `_validate_consistency` still runs, so the
        # explicit value cannot disagree with the interval it is computed from.
        duration_seconds=(result.completed_at - result.started_at).total_seconds(),
        exit_code=result.exit_code,
        failure=failure,
        final_verdict=None if report is None else report.verdict,
        recommended_next_state=None,
    )
