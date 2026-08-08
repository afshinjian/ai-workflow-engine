"""The single gated Git façade of the AUTO-016 milestone runner.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 20 surface 2
of 2, section 22 invariants 4, 5 and 13, section 31's one deliberate exception to "never", and
section 6 defect P-5.

This is the **only** module in the package able to construct a mutating Git argument vector, and
it can construct exactly two shapes: `add` + `commit`, and `push`. It ships disabled. Executing
anything requires all three of section 20's gates, at the point of use:

1. the configuration flip (`git.execute_commit` / `git.execute_push`, both `false` by default);
2. the interactive typed confirmation (`APPROVE COMMIT` / `APPROVE PUSH`), byte-for-byte;
3. a bound, unexpired, unconsumed approval that still matches the repository as it is right now.

None of the three can be satisfied by a project-wide or built-in default, which is
`HUMAN_AUTHORIZATION_MODEL.md` section 5a constraint 6 and `MACHINE_GATES.md` section 4a's
"opt-in at the point of use". With the shipped defaults :meth:`ApprovalGit.commit` and
:meth:`ApprovalGit.push` print the exact commands and execute nothing, so `HEAD`, the reflog and
the remote refs are untouched.

Argv shapes, not policy comments
--------------------------------
`SECURITY_MODEL.md` section 2 requires "argv shapes that make the forbidden operations
unreachable, not merely policy comments". :func:`_permitted_argv` is therefore a closed recognizer
over **complete** vectors, and :meth:`ApprovalGit._run` refuses anything it does not recognize
before a process exists. `reset`, `restore`, `clean`, `stash`, `rebase`, `checkout`, `switch`,
`merge`, `cherry-pick`, `revert`, `fetch`, `pull` and a branch deletion are not operations this
module declines -- they are vectors it has no way to build. There is no caller-supplied
subcommand, no caller-supplied flag, no `--force`, no `--admin` and no branch-protection override
anywhere in the surface; the two builders below take a bound approval and a message, and nothing
else reaches a vector.

This is the second half of the correction of prototype defect P-5, where `git add`, `git commit`
and `git push` called the raw subprocess helper directly and bypassed the allowlisted wrapper, so
the structural guarantee rested on configuration defaults alone.

The approval is evidence, never authority
-----------------------------------------
Nothing here transitions a run. :func:`bind_approval` records what was observed;
:func:`validate_approval` re-checks it against a fresh, independent observation and refuses on any
of section 20's six invalidation triggers -- branch drift, `HEAD` drift, changed-path or digest
drift, a verification failure, expiry, or prior use. An approval is never silently re-bound: a
drifted approval is refused, and a new one has to be granted against what is actually there. A
failed deterministic gate still fails with an approval in hand, and there is no override path.
"""

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError, field_validator, model_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.config import RunnerConfig
from ai_workflow_engine.milestone_runner.git_inspect import RepositoryEvidence
from ai_workflow_engine.milestone_runner.models import (
    MAX_TEXT_CHARS,
    ApprovalOperation,
    ApprovalRecord,
    Finding,
    MilestoneRunnerModel,
    ReviewVerdict,
    RunRecord,
    VerificationResult,
    canonical_digest,
    normalize_repository_path,
)
from ai_workflow_engine.milestone_runner.state import reject_symlink_components

#: Section 20's two typed confirmations, compared byte-for-byte. A near miss is a refusal: the
#: point of a typed confirmation is that a human typed exactly this and not something like it.
COMMIT_CONFIRMATION: Final = "APPROVE COMMIT"
PUSH_CONFIRMATION: Final = "APPROVE PUSH"

#: Which confirmation each operation demands. Named as a mapping so no call site restates it and
#: the two can never be crossed -- an approval authorizes one operation, never both, never a
#: substitute.
REQUIRED_CONFIRMATION: Final[Mapping[ApprovalOperation, str]] = {
    ApprovalOperation.COMMIT: COMMIT_CONFIRMATION,
    ApprovalOperation.PUSH: PUSH_CONFIRMATION,
}

#: How long an approval stays valid. Section 20 names expiry as an invalidation trigger without
#: fixing a duration; thirty minutes is short enough that an approval cannot outlive the state it
#: was read against and long enough for a human to type a confirmation. It is a ceiling, not a
#: guarantee: every other trigger is checked independently at the point of use.
DEFAULT_APPROVAL_TTL_SECONDS: Final = 30 * 60

#: An upper bound on the configurable lifetime, so no caller can turn expiry off by making it
#: effectively infinite.
MAX_APPROVAL_TTL_SECONDS: Final = 4 * 60 * 60

#: The remote a push may name. A literal, so a push cannot be redirected and cannot carry a
#: refspec of its own choosing.
PUSH_REMOTE: Final = "origin"

#: The digest recorded for a changed path that is absent from the worktree -- a deletion. A
#: distinct constant rather than the digest of empty bytes, so "the file was deleted" and "the
#: file is empty" are two different bindings and one cannot drift into the other unnoticed.
ABSENT_PATH_DIGEST: Final = hashlib.sha256(b"milestone-runner:absent-path").hexdigest()

#: The largest file this module will digest when binding an approval.
MAX_DIGESTED_FILE_BYTES: Final = 64 << 20

#: How long either mutating vector may take.
DEFAULT_EXECUTION_TIMEOUT_SECONDS: Final = 300

_UTC_TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"
_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_DIGEST_CHUNK_BYTES: Final = 1 << 20


class ApprovalRefused(WorkflowEngineError):
    """A gate was not satisfied, and no vector ran (section 20).

    One class for all three gates, because the operator's position after any of them is identical:
    nothing was executed, the worktree is exactly as it was, `HEAD` has not moved and a fresh
    approval is what comes next. The message names the gate that refused and what it observed.
    """


class ApprovalInvalid(ApprovalRefused):
    """The approval no longer describes the repository it was granted against (section 20).

    Raised for each of the six invalidation triggers -- branch drift, `HEAD` drift, changed-path
    drift, digest drift, a verification failure, expiry, and prior use. The approval is never
    re-bound in place: a new one is granted against a fresh observation, or nothing happens.
    """


class CommitApproval(MilestoneRunnerModel):
    """One Human Owner approval for exactly one commit or one push, with its expiry.

    The binding itself lives on :class:`~...models.ApprovalRecord`, which is what the run record
    persists: repository identity, branch, baseline SHA and current `HEAD`, the canonical
    changed-path set, a digest per changed file, the verification result set's digest, the review
    verdict with its finding ids, the exact operation, and whether a human supplied the typed
    confirmation. `expires_at` is the one property section 20 names that the durable record has no
    field for, so it is carried here, alongside the record rather than inside it.

    A value object: nothing here executes, transitions or authorizes anything.
    """

    record: ApprovalRecord
    expires_at: str

    @field_validator("expires_at")
    @classmethod
    def _validate_expires_at(cls, value: str) -> str:
        if _parse_timestamp(value) is None:
            raise ValueError("expires_at must be an ISO-8601 UTC timestamp of the form ...Z")
        return value

    @model_validator(mode="after")
    def _validate_lifetime(self) -> "CommitApproval":
        granted = _parse_timestamp(self.record.granted_at)
        expires = _parse_timestamp(self.expires_at)
        if granted is None or expires is None:  # pragma: no cover - field validators refuse first
            raise ValueError("an approval must carry two readable UTC timestamps")
        lifetime = (expires - granted).total_seconds()
        if lifetime <= 0:
            raise ValueError("an approval must expire after it was granted, not before")
        if lifetime > MAX_APPROVAL_TTL_SECONDS:
            raise ValueError(
                f"an approval may live at most {MAX_APPROVAL_TTL_SECONDS} seconds; "
                f"{int(lifetime)} would make expiry no longer a real invalidation trigger"
            )
        return self

    @property
    def operation(self) -> ApprovalOperation:
        """The one operation this approval authorizes -- never both, never a substitute."""
        return self.record.operation

    @property
    def consumed(self) -> bool:
        """Whether the single use this approval carries has already been spent."""
        return self.record.consumed

    @property
    def execution_attempted(self) -> bool:
        """Whether this approval's gated vector was already begun (section 20, durable record)."""
        return self.record.execution_started_at is not None

    def _revised(self, **updates: Any) -> "CommitApproval":
        """Return this approval with `updates` applied, re-validated rather than mutated."""
        payload: dict[str, Any] = json.loads(self.record.model_dump_json())
        payload.update(updates)
        try:
            revised = ApprovalRecord.model_validate_json(json.dumps(payload))
        except ValidationError as exc:  # pragma: no cover - the record was valid a line ago
            raise ApprovalInvalid(f"The revised approval is not a valid record: {exc}") from exc
        return CommitApproval(record=revised, expires_at=self.expires_at)

    def execution_attempted_at(self, moment: datetime) -> "CommitApproval":
        """Return this approval stamped as being executed now (section 20's durable record).

        Stamped *before* the vector runs, so the grant and the attempt are durable before the act
        they authorize can have happened. A process lost between the mutation and the consumption
        record therefore leaves an attempted, unconsumed approval -- an act nobody reconciled --
        rather than no evidence at all.
        """
        if self.execution_attempted:
            raise ApprovalInvalid(
                f"This approval's execution was already begun at {self.record.execution_started_at}"
            )
        return self._revised(execution_started_at=_format_timestamp(moment))

    def consumed_at(self, moment: datetime) -> "CommitApproval":
        """Return this approval marked consumed at `moment` (section 20's single use).

        A new value rather than a mutation: an approval that has been spent is a different fact
        from one that has not, and the run record keeps both spellings apart.
        """
        if self.record.consumed:
            raise ApprovalInvalid(
                "This approval has already been consumed; a second execution requires a fresh "
                "approval (section 20, single use)"
            )
        return self._revised(
            consumed=True,
            consumed_at=_format_timestamp(moment),
            execution_started_at=(
                self.record.execution_started_at
                if self.execution_attempted
                else _format_timestamp(moment)
            ),
        )

    def landed_at(self, head_sha: str) -> "CommitApproval":
        """Return this consumed approval carrying where its execution left `HEAD` (section 4.4)."""
        return self._revised(resulting_head_sha=head_sha)


#: What the gate hands a caller once all three gates have passed and before the first mutating
#: vector runs, so the grant and the attempt can be made durable while nothing has happened yet.
ExecutionAttemptHook = Callable[["CommitApproval"], None]


def unreconciled_attempt(record: RunRecord) -> ApprovalRecord | None:
    """The approval whose execution began and was never recorded as consumed, if there is one.

    Section 20 requires every approval and every consumption to be durably recorded, and section 22
    requires that evidence survive a crash. An approval stamped `execution_started_at` but never
    consumed is precisely the gap: a gated vector was begun and the run never recorded how it
    ended. Whether the mutation landed is not knowable from here -- a push leaves local `HEAD`
    exactly where it was -- so the pair is reported and the gate refuses, which is the only answer
    that cannot execute an approved act twice.
    """
    for approval in record.approvals:
        if approval.execution_started_at is not None and not approval.consumed:
            return approval
    return None


@dataclass(frozen=True, slots=True)
class ApprovalExecution:
    """What one gate did: the exact commands, and whether any of them ran.

    `executed` is `False` for the shipped defaults, and `commands` is populated either way --
    section 20's print-only gate prints *the same* vectors it would have run, so an operator can
    read what would happen before deciding whether it should.
    """

    operation: ApprovalOperation
    executed: bool
    commands: tuple[tuple[str, ...], ...]
    reason: str
    approval: CommitApproval | None = None

    @property
    def rendered_commands(self) -> tuple[str, ...]:
        """The commands as a human reads them, one line each."""
        return tuple(" ".join(["git", *command]) for command in self.commands)


# --------------------------------------------------------------------------------------
# Section 20 -- binding an approval to the state it was granted against
# --------------------------------------------------------------------------------------


def _format_timestamp(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise ApprovalRefused(
            "An approval moment must be timezone-aware UTC; a naive or offset stamp would make "
            "expiry unorderable"
        )
    return moment.strftime(_UTC_TIMESTAMP_FORMAT)


def _parse_timestamp(value: str) -> datetime | None:
    """Read one `...Z` stamp as an aware UTC moment, or `None` when it is not one.

    The offset is appended to the *value* and parsed with `%z` rather than attached afterwards, so
    the result is aware by construction. A naive stamp that something later attached a zone to
    would be a moment nobody observed, and expiry has to be orderable against a real one.
    """
    try:
        return datetime.strptime(f"{value}+0000", f"{_UTC_TIMESTAMP_FORMAT}%z")
    except ValueError:
        return None


def digest_changed_path(repository_root: Path, relative_path: str) -> str:
    """SHA-256 over one changed path's current bytes, or :data:`ABSENT_PATH_DIGEST` if deleted.

    Every component is checked for a symbolic link before the file is opened, and the open is
    `O_NOFOLLOW`, so a link substituted for a changed path is refused rather than followed
    (invariant 8). The read is bounded and chunked, so binding an approval over a large worktree
    does not pull it all into memory at once.
    """
    normalized = normalize_repository_path(relative_path, "changed_path")
    target = repository_root / normalized
    if not target.exists() and not target.is_symlink():
        return ABSENT_PATH_DIGEST
    reject_symlink_components(target, f"The changed path {normalized}")
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ApprovalRefused(f"Cannot digest the changed path {normalized}: {exc}") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(descriptor, "rb") as handle:
            while True:
                chunk = handle.read(_DIGEST_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DIGESTED_FILE_BYTES:
                    raise ApprovalRefused(
                        f"The changed path {normalized} exceeds {MAX_DIGESTED_FILE_BYTES} bytes"
                    )
                digest.update(chunk)
    except OSError as exc:
        raise ApprovalRefused(f"Cannot digest the changed path {normalized}: {exc}") from exc
    return digest.hexdigest()


def verification_digest(results: Sequence[VerificationResult]) -> str:
    """The digest of the final verification result set an approval is bound to (section 20).

    Taken over the canonical serialization of every result, with the wall-clock fields
    :data:`~...models.DIGEST_EXCLUDED_FIELDS` names dropped, so re-deriving it over the same
    evidence at the moment of use reproduces it. A result set with a failure digests to something
    different from the same set with that failure fixed, which is what makes "invalidated by a
    verification failure" checkable rather than declarative.
    """
    return canonical_digest([result.model_dump(mode="json") for result in results])


def review_verdict_of(record: RunRecord) -> ReviewVerdict:
    """The verdict the run's own findings ledger implies -- `BLOCKED` while a blocker is open.

    Derived from the record rather than taken from a caller, because section 20 binds an approval
    to "the review verdict with its finding IDs" and a caller-supplied verdict would be exactly
    the caller-copied authorization string `MACHINE_GATES.md` section 2a refuses as live evidence.
    """
    open_blockers = [
        finding for finding in record.blocking_findings if finding.status.value == "OPEN"
    ]
    return ReviewVerdict.BLOCKED if open_blockers else ReviewVerdict.APPROVED


def _finding_ids(findings: Sequence[Finding]) -> list[str]:
    return sorted({finding.finding_id for finding in findings}, key=lambda item: item.encode())


def bind_approval(
    *,
    operation: ApprovalOperation,
    record: RunRecord,
    evidence: RepositoryEvidence,
    repository_root: Path,
    moment: datetime,
    human_confirmation_supplied: bool,
    ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS,
) -> CommitApproval:
    """Bind one approval to the state it is granted against (section 20, constraint 4).

    Every bound value is *observed* now, not copied from configuration: the branch, `HEAD`, the
    repository identity and the changed-path set come from `evidence`, which the caller obtained
    from an independent read-only observation, and each changed file's digest is computed from the
    bytes on disk at this moment. The baseline SHA, the verification result set, the review verdict
    and its finding ids come from the durable run record, which is the runner's own evidence.

    Nothing is executed and nothing is transitioned. The returned approval is a fact about a
    moment; whether that moment still holds is :func:`validate_approval`'s question.
    """
    if ttl_seconds <= 0 or ttl_seconds > MAX_APPROVAL_TTL_SECONDS:
        raise ApprovalRefused(
            f"An approval lifetime must be between 1 and {MAX_APPROVAL_TTL_SECONDS} seconds, "
            f"not {ttl_seconds}"
        )
    if evidence.repository_identity != record.repository_identity:
        raise ApprovalRefused(
            f"Refusing to bind an approval: the worktree is {evidence.repository_identity}, and "
            f"the run was pinned to {record.repository_identity}"
        )
    granted_at = _format_timestamp(moment)
    changed_paths = sorted(
        {normalize_repository_path(path, "changed_path") for path in evidence.changed_paths},
        key=lambda item: item.encode("utf-8"),
    )
    digests = {path: digest_changed_path(repository_root, path) for path in changed_paths}
    approval = ApprovalRecord(
        operation=operation,
        granted_at=granted_at,
        repository_identity=evidence.repository_identity,
        branch=evidence.branch,
        baseline_sha=record.baseline_sha,
        head_sha=evidence.head_sha,
        changed_paths=changed_paths,
        changed_path_digests=digests,
        verification_digest=verification_digest(record.verification_results),
        review_verdict=review_verdict_of(record),
        finding_ids=_finding_ids([*record.blocking_findings, *record.deferred_findings]),
        human_confirmation_supplied=human_confirmation_supplied,
    )
    return CommitApproval(
        record=approval,
        expires_at=_format_timestamp(moment + timedelta(seconds=ttl_seconds)),
    )


def validate_approval(
    approval: CommitApproval,
    *,
    operation: ApprovalOperation,
    record: RunRecord,
    evidence: RepositoryEvidence,
    repository_root: Path,
    moment: datetime,
) -> None:
    """Refuse `approval` on any of section 20's invalidation triggers, each checked independently.

    The triggers, in the order the contract lists them: branch drift, `HEAD` drift, changed-path
    drift, digest drift, a verification failure, expiry, and prior use. Repository identity and the
    authorized operation are checked alongside them, because an approval that names another
    repository or another operation was never bound to this act at all.

    Returns nothing and raises :class:`ApprovalInvalid` on the first trigger that fires. It never
    re-binds: an approval that no longer matches is spent evidence, and the only remedy is a fresh
    one granted against a fresh observation.
    """
    bound = approval.record
    if bound.operation is not operation:
        raise ApprovalInvalid(
            f"This approval authorizes {bound.operation.value}, not {operation.value}; one "
            "approval authorizes exactly one operation, never both and never a substitute"
        )
    if bound.consumed:
        raise ApprovalInvalid(
            f"This approval was already consumed at {bound.consumed_at}; a second execution "
            "requires a fresh approval (single use)"
        )
    expires = _parse_timestamp(approval.expires_at)
    if expires is None:  # pragma: no cover - the model validator refuses first
        raise ApprovalInvalid("This approval carries an unreadable expiry")
    _format_timestamp(moment)
    if moment >= expires:
        raise ApprovalInvalid(
            f"This approval expired at {approval.expires_at}; an approval is bound to the moment "
            "it was granted and is never silently re-bound"
        )
    if bound.repository_identity != evidence.repository_identity:
        raise ApprovalInvalid(
            f"This approval was granted against {bound.repository_identity}; the worktree is "
            f"{evidence.repository_identity}"
        )
    if bound.branch != evidence.branch:
        raise ApprovalInvalid(
            f"Branch drift: this approval was granted on {bound.branch}, and the worktree is on "
            f"{evidence.branch}"
        )
    if bound.head_sha != evidence.head_sha:
        raise ApprovalInvalid(
            f"HEAD drift: this approval was granted at {bound.head_sha}, and HEAD is now "
            f"{evidence.head_sha}"
        )
    if bound.baseline_sha != record.baseline_sha:
        raise ApprovalInvalid(
            f"This approval was granted against baseline {bound.baseline_sha}; the run records "
            f"{record.baseline_sha}"
        )
    observed_paths = sorted(
        {normalize_repository_path(path, "changed_path") for path in evidence.changed_paths},
        key=lambda item: item.encode("utf-8"),
    )
    if observed_paths != bound.changed_paths:
        raise ApprovalInvalid(
            "Changed-path drift: this approval was granted over "
            f"{bound.changed_paths} and the worktree now shows {observed_paths}"
        )
    for path in observed_paths:
        current = digest_changed_path(repository_root, path)
        if current != bound.changed_path_digests[path]:
            raise ApprovalInvalid(
                f"Digest drift on {path}: this approval was granted over "
                f"{bound.changed_path_digests[path]} and the file now digests to {current}"
            )
    failures = [result for result in record.verification_results if not result.passed]
    if failures:
        raise ApprovalInvalid(
            f"{len(failures)} verification command(s) did not pass; an approval is evidence and "
            "never authority, and a failed deterministic gate still fails with one in hand"
        )
    current_digest = verification_digest(record.verification_results)
    if current_digest != bound.verification_digest:
        raise ApprovalInvalid(
            "The verification result set this approval was granted over has changed: it digested "
            f"to {bound.verification_digest} and now digests to {current_digest}"
        )
    if bound.review_verdict is not review_verdict_of(record):
        raise ApprovalInvalid(
            f"The review verdict this approval was granted under ({bound.review_verdict.value}) "
            "is not the verdict the run's findings ledger now implies"
        )


# --------------------------------------------------------------------------------------
# Section 20 surface 2 -- the two mutating vectors, and nothing else
# --------------------------------------------------------------------------------------


def _is_safe_path_argument(value: str) -> bool:
    try:
        return normalize_repository_path(value, "path") == value
    except ValueError:
        return False


def _permitted_argv(argv: Sequence[str]) -> bool:
    """Whether `argv` is one of the two mutating shapes this module may build, and nothing else.

    A closed recognizer over the whole vector. `add` is admitted only in its `--`-terminated form
    over normalized repository-relative paths, so no element can be read as an option; `commit` is
    admitted only with a single `--message` value; `push` is admitted only as the fixed remote plus
    one branch name from a closed grammar, so it can carry no refspec, no `--force`, no `--delete`
    and no `--admin`. Every other subcommand -- `reset`, `restore`, `clean`, `stash`, `rebase`,
    `checkout`, `switch`, `merge`, `cherry-pick`, `revert`, `fetch`, `pull`, a branch deletion --
    fails this recognizer because there is no branch here that accepts it.
    """
    vector = tuple(argv)
    if len(vector) >= 3 and vector[0] == "add" and vector[1] == "--":
        return all(_is_safe_path_argument(item) for item in vector[2:])
    if len(vector) == 3 and vector[0] == "commit" and vector[1] == "--message":
        return bool(vector[2].strip()) and len(vector[2]) <= MAX_TEXT_CHARS
    if len(vector) == 3 and vector[0] == "push" and vector[1] == PUSH_REMOTE:
        return _BRANCH_RE.fullmatch(vector[2]) is not None
    return False


def _commit_vectors(approval: CommitApproval, message: str) -> tuple[tuple[str, ...], ...]:
    """The `add` + `commit` pair for one bound commit approval, and nothing else.

    The paths come from the approval, which took them from an independent observation and bound a
    digest to each -- so the vector stages exactly what the Human Owner approved, and a path that
    appeared afterwards is not in it (and would have invalidated the approval anyway).
    """
    paths = tuple(approval.record.changed_paths)
    if not paths:
        raise ApprovalRefused(
            "There is nothing to commit: the approval was bound over an empty changed-path set"
        )
    return (("add", "--", *paths), ("commit", "--message", message))


def _push_vectors(approval: CommitApproval) -> tuple[tuple[str, ...], ...]:
    """The single `push` vector for one bound push approval: the fixed remote and one branch."""
    return (("push", PUSH_REMOTE, approval.record.branch),)


class ApprovalGit:
    """Section 20 surface 2: the two gated vectors, disabled by the shipped defaults.

    Constructed from the validated configuration's `git` section, whose two flags are `false`
    unless the file says otherwise. A flipped flag alone authorizes nothing: :meth:`commit` and
    :meth:`push` additionally require the typed confirmation and a bound, unexpired, unconsumed
    approval that still matches a fresh observation, and any one of the three being unsatisfied
    means no process is started and the worktree is left exactly as it was.

    The object holds no state that a caller could set to skip a gate: the flags are read-only, the
    confirmation is an argument compared at the point of use, and the approval is re-validated on
    every call rather than remembered.
    """

    def __init__(
        self,
        *,
        repository_root: Path,
        execute_commit: bool = False,
        execute_push: bool = False,
        timeout_seconds: int = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ApprovalRefused("The execution timeout must be a positive number of seconds")
        self._repository_root = repository_root
        self._execute_commit = execute_commit
        self._execute_push = execute_push
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_config(cls, config: RunnerConfig, repository_root: Path) -> "ApprovalGit":
        """Build the façade from the validated configuration's two `false`-by-default flags."""
        return cls(
            repository_root=repository_root,
            execute_commit=config.git.execute_commit,
            execute_push=config.git.execute_push,
        )

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def execution_enabled(self) -> Mapping[ApprovalOperation, bool]:
        """The two configuration flips, read-only. Neither is sufficient on its own."""
        return {
            ApprovalOperation.COMMIT: self._execute_commit,
            ApprovalOperation.PUSH: self._execute_push,
        }

    # -- the two gates -------------------------------------------------------------------

    def commit(
        self,
        approval: CommitApproval,
        *,
        message: str,
        confirmation: str | None,
        record: RunRecord,
        evidence: RepositoryEvidence,
        moment: datetime,
        on_execute: ExecutionAttemptHook | None = None,
    ) -> ApprovalExecution:
        """Print, and -- under all three gates -- execute, the `add` + `commit` pair."""
        return self._gate(
            ApprovalOperation.COMMIT,
            _commit_vectors(approval, message),
            approval,
            confirmation=confirmation,
            record=record,
            evidence=evidence,
            moment=moment,
            on_execute=on_execute,
        )

    def push(
        self,
        approval: CommitApproval,
        *,
        confirmation: str | None,
        record: RunRecord,
        evidence: RepositoryEvidence,
        moment: datetime,
        on_execute: ExecutionAttemptHook | None = None,
    ) -> ApprovalExecution:
        """Print, and -- under all three gates -- execute, the single `push` vector."""
        return self._gate(
            ApprovalOperation.PUSH,
            _push_vectors(approval),
            approval,
            confirmation=confirmation,
            record=record,
            evidence=evidence,
            moment=moment,
            on_execute=on_execute,
        )

    def _gate(
        self,
        operation: ApprovalOperation,
        commands: tuple[tuple[str, ...], ...],
        approval: CommitApproval,
        *,
        confirmation: str | None,
        record: RunRecord,
        evidence: RepositoryEvidence,
        moment: datetime,
        on_execute: ExecutionAttemptHook | None = None,
    ) -> ApprovalExecution:
        """Apply section 20's three gates in order, then execute exactly `commands` or nothing.

        Order matters for what an operator learns. The configuration flip is checked first,
        because with the shipped defaults there is nothing further to decide and the answer is the
        printed commands. The typed confirmation is checked next, at the point of use, so it can
        never be inherited. The binding is checked last and against a fresh observation, so an
        approval that drifted between being granted and being used is refused on the state of the
        repository rather than on the state of the request.

        `on_execute` runs only once all three gates have passed and only before the first vector,
        so the caller can make the grant and the attempt durable while `HEAD`, the reflog and the
        remote refs are still exactly as the gates observed them. A refusal never reaches it, and
        the print-only default never reaches it either.
        """
        if not self.execution_enabled[operation]:
            return ApprovalExecution(
                operation=operation,
                executed=False,
                commands=commands,
                reason=(
                    f"git.execute_{operation.value.lower()} is false, the shipped default. These "
                    "are the exact commands; nothing was executed and nothing changed."
                ),
            )
        required = REQUIRED_CONFIRMATION[operation]
        if confirmation != required:
            raise ApprovalRefused(
                f"Refusing to execute {operation.value}: the typed confirmation must be exactly "
                f"{required!r}, supplied at the point of use. The configuration flip alone "
                "authorizes nothing and no default can satisfy this gate."
            )
        validate_approval(
            approval,
            operation=operation,
            record=record,
            evidence=evidence,
            repository_root=self._repository_root,
            moment=moment,
        )
        attempted = approval.execution_attempted_at(moment)
        if on_execute is not None:
            on_execute(attempted)
        for command in commands:
            self._run(command)
        return ApprovalExecution(
            operation=operation,
            executed=True,
            commands=commands,
            reason=(
                f"{operation.value} executed under the configuration flip, the typed confirmation "
                f"{required!r} and a bound single-use approval, which is now consumed."
            ),
            approval=attempted.consumed_at(moment),
        )

    # -- the single process boundary -----------------------------------------------------

    def _run(self, argv: tuple[str, ...]) -> str:
        """Run one recognized vector and return its stdout.

        The recognizer runs on the whole vector before a process exists, so a shape this module
        cannot build is also a shape it cannot run. No shell is involved: the argument list is
        passed to `subprocess.run` as a list, and there is no `shell=True` path in this package.
        """
        if not _permitted_argv(argv):
            raise ApprovalRefused(
                f"{list(argv)!r} is not one of the two mutating vectors this module can build; "
                "every other Git operation is unreachable from here, not merely unused"
            )
        try:
            process = subprocess.run(
                ["git", "-C", str(self._repository_root), *argv],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApprovalRefused(
                f"git {argv[0]} exceeded {self._timeout_seconds}s in {self._repository_root}"
            ) from exc
        except OSError as exc:
            raise ApprovalRefused(f"Unable to execute Git: {exc}") from exc
        if process.returncode != 0:
            raise ApprovalRefused(
                f"git {argv[0]} failed in {self._repository_root}: {process.stderr.strip()}"
            )
        return process.stdout


#: The two vector shapes, named so a reader and a test can see the whole mutating surface in one
#: place. Descriptive, never the source of the recognizer: :func:`_permitted_argv` is.
MUTATING_ARGV_SHAPES: Final[tuple[str, ...]] = (
    "add -- <approved path>...",
    "commit --message <message>",
    f"push {PUSH_REMOTE} <branch>",
)


def approval_summary(approval: CommitApproval) -> tuple[str, ...]:
    """The bound approval as an operator reads it, one line per bound property (section 20)."""
    bound = approval.record
    return (
        f"Operation: {bound.operation.value}",
        f"Repository identity: {bound.repository_identity}",
        f"Branch: {bound.branch}",
        f"Baseline SHA: {bound.baseline_sha}",
        f"HEAD: {bound.head_sha}",
        f"Changed paths: {len(bound.changed_paths)}",
        f"Changed-path digests: {len(bound.changed_path_digests)}",
        f"Verification digest: {bound.verification_digest}",
        f"Review verdict: {bound.review_verdict.value} "
        f"({', '.join(bound.finding_ids) if bound.finding_ids else 'no findings'})",
        f"Granted at: {bound.granted_at}",
        f"Expires at: {approval.expires_at}",
        f"Human confirmation supplied: {'yes' if bound.human_confirmation_supplied else 'no'}",
        f"Consumed: {'yes' if bound.consumed else 'no'}",
    )
