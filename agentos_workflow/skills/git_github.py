"""Git and GitHub Skills (`SKILL_CONTRACTS.md` §5) — commit, push, pull request, and merge.

AUTO-003 scoped `repository.py` to local-Git-only Skills and left the eight GitHub-facing ones
named but unbound (`agentos_workflow.agents.PROVISIONAL_SKILL_NAMES`); this module delivers all
eight. `GitAgent`/`MergeAgent` (`agents/git.py`, `agents/merge.py`) already call these Skills
against fakes with the exact keyword shapes used here — this module changes no Agent code, only
binds the real implementation those shapes were written against.

Delivering them was not the same as making them reachable: `agents._DEFAULT_SKILL_BINDINGS` was not
updated when this module landed, so for the whole period afterwards the production registry still
answered "not yet implemented" for all eight and neither Agent could run against it. GOV-AUTO-06
bound them. The lesson is recorded here because this docstring's own claim to "deliver all eight"
read as complete while half the wiring was missing.

Three security properties are structural, not merely reviewed:

- **No admin bypass** (`SECURITY_MODEL.md` §4). `enable_automatic_squash_merge` has exactly one
  `gh pr merge` call site, and its argv is `("pr", "merge", <number>, "--auto", "--squash")` — a
  fixed tuple with no caller-suppliable flag and no `--admin` anywhere in this module's source.
  `test_skills_git_github.py::test_no_forbidden_argv_tokens` asserts this over the module's own
  AST, the same technique `repository.py` uses for its own forbidden-token claim.
- **No repository redirection.** Every `gh` invocation runs with `cwd=repository_path` and no
  `--repo` flag, so `gh` always resolves the target repository from the local Git remote — a
  caller cannot point a Skill at an arbitrary GitHub repository by supplying one.
- **No force-push, no baseline target.** `push_stage_branch`'s argv contains no `--force`/
  `--force-with-lease`, and `create_pull_request` refuses when `branch == baseline_branch`
  (`_reject_baseline`, mirroring `repository.py`), so opening a pull request *from* the baseline
  is unexpressible.

**Retry classification** (`SKILL_CONTRACTS.md` §5) is deliberately asymmetric across this module's
eight Skills. `create_commit`, `push_stage_branch`, and `create_pull_request` are the three Skills
that policy names explicitly: once their subprocess has actually run, a failure is
`POSSIBLE_SIDE_EFFECT` even for `create_commit`, which never touches a remote — a hook or a
partially-applied local write could already have taken effect, so "local" does not mean "provably
safe to retry" for these three. The other five Skills (reads, plus the single merge-enabling
write) are not named by that policy; their own network failures still classify
`POSSIBLE_SIDE_EFFECT` once invoked, matching the convention `repository.py` already uses for its
own network-touching reads (e.g. `delete_remote_branch`'s `ls-remote` listing). `verify_head_sha`
is the one Skill in this module that is purely local with no remote counterpart at all, so its
failures are always `NOT_APPLICABLE`. A spawn failure — the executable could not be found or run —
is `PROVEN_PRE_SIDE_EFFECT` for every Skill here, and a diagnosably permanent failure (auth/
permission, an unknown ref, a definitive non-429 4xx) is `NON_RETRYABLE` regardless of the above,
per the explicit non-retryable list in `SKILL_CONTRACTS.md` §5.

**`create_commit`'s staging design.** `GitAgent.create_commit` calls this Skill with no path list
(`repository_path`, `branch`, `message`, `expected_head_sha` only), even though
`SKILL_CONTRACTS.md` §5's table names "staged allowed paths" as its input. This module accepts the
Agent's actual call shape as authoritative — modifying `agents/git.py` is outside this stage's
allowed files — and implements the input as "stage the working tree's current diff, then commit
it": `git add -A` followed by `git commit`. This is safe by construction at the point this Skill
runs (`READY_TO_COMMIT`): the working tree's diff has already passed `run_scope_validation`
(`MACHINE_GATES.md` §3) before the workflow reaches this state, so "everything currently changed"
and "everything in the allowed path set" are the same set of files. Recorded as a stage
implementation decision, `DECISIONS.md` DD-36.

**Testing.** `gh` invocations are mocked at the process boundary — a fake `gh` executable placed
first on `PATH` for the duration of a test — never by patching this module's own internals, so the
tests exercise the exact argv this module constructs (`test_skills_git_github.py`). `git`
invocations run against real temporary repositories with a local remote, the same technique
`test_skills_repository.py` already established; no test reaches the network or a real GitHub
repository.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos_workflow.skills import (
    CommandExecution,
    CommandOutcome,
    FailureKind,
    MergeConfirmation,
    RetryClassification,
    SkillResult,
    failure,
    run_fixed_argv,
    success,
    utc_now,
)

__all__ = [
    "AutoMergeResult",
    "CommitResult",
    "PullRequestInfo",
    "PullRequestState",
    "PushResult",
    "RequiredChecks",
    "create_commit",
    "create_pull_request",
    "enable_automatic_squash_merge",
    "push_stage_branch",
    "read_pull_request_state",
    "read_required_checks",
    "verify_head_sha",
    "verify_merge_completion",
]

GIT_TIMEOUT_SECONDS = 30
GH_TIMEOUT_SECONDS = 60

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_REMOTE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_PR_URL_RE = re.compile(r"/pull/(\d+)\s*$")

_PERMANENT_MARKERS: tuple[str, ...] = (
    "permission denied",
    "authentication failed",
    "could not read username",
    "could not read password",
    "http 401",
    "http 403",
    "http 404",
    "http 422",
    "protected branch",
    "not authorized",
    "not permitted",
    "bad credentials",
    "unknown revision or path",
    "couldn't find remote ref",
    "does not appear to be a git repository",
)


@dataclass(frozen=True)
class CommitResult:
    commit_sha: str
    branch: str


@dataclass(frozen=True)
class PushResult:
    remote_ref: str
    head_sha: str


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    url: str
    head_sha: str


@dataclass(frozen=True)
class PullRequestState:
    number: int
    state: str
    head_sha: str
    merged: bool


@dataclass(frozen=True)
class RequiredChecks:
    all_passed: bool
    pending: tuple[str, ...]
    failed: tuple[str, ...]


@dataclass(frozen=True)
class AutoMergeResult:
    pull_request_number: int
    enabled: bool


# --------------------------------------------------------------------------------------------
# Input validation. Deliberately duplicated in miniature from `repository.py` rather than
# imported: `skills/__init__.py`'s module docstring keeps the four family modules independent of
# one another so each can be imported in isolation, and this module follows the same rule.
# --------------------------------------------------------------------------------------------


def _ref_problem(value: str) -> str | None:
    forbidden = ("..", "@{", "\\", " ", "~", "^", ":", "?", "*", "[")
    if not value:
        return "empty ref name"
    if value.startswith(("-", ".", "/")):
        return "ref name starts with '-', '.', or '/'"
    if value.endswith((".", "/", ".lock")):
        return "ref name ends with '.', '/', or '.lock'"
    if "//" in value:
        return "repeated '/' separator"
    if any(token in value for token in forbidden):
        return "ref name contains a forbidden token"
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return "ref name contains a control character"
    if len(value) > 255:
        return "ref name longer than 255 characters"
    return None


def _validate_refs(skill: str, **refs: str) -> SkillResult[Any] | None:
    for name, value in refs.items():
        problem = _ref_problem(value)
        if problem is not None:
            return failure(
                skill,
                FailureKind.UNSAFE_INPUT,
                f"{name}={value!r} is not a safe Git ref name: {problem}",
                retry_classification=RetryClassification.NON_RETRYABLE,
            )
    return None


def _validate_remote(skill: str, remote: str) -> SkillResult[Any] | None:
    if not _REMOTE_NAME_RE.fullmatch(remote):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"remote={remote!r} is not a safe remote name",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


def _reject_baseline(skill: str, target: str, baseline_branch: str) -> SkillResult[Any] | None:
    if target == baseline_branch:
        return failure(
            skill,
            FailureKind.PERMANENT,
            f"refusing to target the configured baseline branch {baseline_branch!r}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


def _validate_pr_number(skill: str, pull_request_number: int) -> SkillResult[Any] | None:
    if (
        not isinstance(pull_request_number, int)
        or isinstance(pull_request_number, bool)
        or pull_request_number <= 0
    ):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"pull_request_number={pull_request_number!r} is not a positive integer",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


def _validate_sha(skill: str, field: str, value: str) -> SkillResult[Any] | None:
    if not _SHA_RE.fullmatch(value):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"{field}={value!r} is not a full 40-character SHA",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


# --------------------------------------------------------------------------------------------
# Subprocess invocation
# --------------------------------------------------------------------------------------------


def _git(
    repository_path: Path,
    args: tuple[str, ...],
    *,
    identity: str,
    timeout_seconds: int = GIT_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> CommandExecution:
    return run_fixed_argv(
        ("git", "--no-optional-locks", "-C", str(repository_path), *args),
        identity=identity,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


def _gh(
    repository_path: Path,
    args: tuple[str, ...],
    *,
    identity: str,
    timeout_seconds: int = GH_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> CommandExecution:
    """Invoke the GitHub CLI, `cwd`-scoped to the target repository.

    No argv here ever carries a `--repo` flag: `gh` resolves which repository to talk to from the
    local Git remote of `cwd` alone, so this Skill layer has no expressible way for a caller to
    redirect it at an arbitrary GitHub repository (`SECURITY_MODEL.md` §2).
    """
    return run_fixed_argv(
        ("gh", *args),
        identity=identity,
        cwd=str(repository_path),
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


def _looks_permanent(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _PERMANENT_MARKERS)


def _invoked_failure(
    skill: str,
    execution: CommandExecution,
    *,
    network: bool,
    ambiguous: bool = False,
) -> SkillResult[Any]:
    """Classify a failure from a subprocess that actually ran, per `SKILL_CONTRACTS.md` §5.

    `ambiguous=True` is for the three Skills that policy names explicitly
    (`create_commit`/`push_stage_branch`/`create_pull_request`): even a purely local failure
    there is never provably pre-effect once the subprocess has run. `network=True` covers every
    other Skill's own network-touching failures, matching `repository.py`'s existing convention.
    Either flag alone is enough to produce `POSSIBLE_SIDE_EFFECT`; only a spawn failure is
    `PROVEN_PRE_SIDE_EFFECT`, and a diagnosably permanent failure is always `NON_RETRYABLE`
    regardless of either flag.
    """
    if execution.outcome is CommandOutcome.SPAWN_FAILED:
        return failure(
            skill,
            FailureKind.SPAWN_FAILED,
            f"could not execute: {execution.stderr or 'no diagnostic'}",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )
    detail = execution.stderr.strip() or execution.stdout.strip() or "no diagnostic"
    if _looks_permanent(detail):
        return failure(
            skill,
            FailureKind.PERMANENT,
            f"non-retryable failure: {detail}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    classification = (
        RetryClassification.POSSIBLE_SIDE_EFFECT
        if (network or ambiguous)
        else RetryClassification.NOT_APPLICABLE
    )
    if execution.outcome is CommandOutcome.TIMED_OUT:
        return failure(
            skill,
            FailureKind.TIMEOUT,
            f"timed out: {detail}",
            retry_classification=classification,
        )
    return failure(
        skill,
        FailureKind.COMMAND_FAILED,
        f"exited {execution.exit_code}: {detail}",
        retry_classification=classification,
    )


def _parse_gh_json(skill: str, execution: CommandExecution) -> tuple[Any, SkillResult[Any] | None]:
    text = execution.stdout.strip()
    if not text:
        return None, failure(skill, FailureKind.MALFORMED_OUTPUT, "gh returned empty output")
    try:
        return json.loads(text), None
    except (json.JSONDecodeError, ValueError):
        return None, failure(
            skill, FailureKind.MALFORMED_OUTPUT, f"gh did not return valid JSON: {text[:200]!r}"
        )


# --------------------------------------------------------------------------------------------
# Local Git Skills
# --------------------------------------------------------------------------------------------


def verify_head_sha(
    repository_path: Path, *, branch: str, expected_head_sha: str
) -> SkillResult[bool]:
    """Confirm `branch`'s local head is still `expected_head_sha` (`MACHINE_GATES.md` §5).

    Purely local — a `git rev-parse` against the repository's own refs, never a network call —
    so there is no remote side effect to ever reconcile; every failure here is `NOT_APPLICABLE`.
    """
    skill = "verify_head_sha"
    if problem := _validate_refs(skill, branch=branch):
        return problem
    if problem := _validate_sha(skill, "expected_head_sha", expected_head_sha):
        return problem
    execution = _git(
        repository_path,
        ("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"),
        identity=skill,
    )
    if execution.outcome is not CommandOutcome.COMPLETED:
        return _invoked_failure(skill, execution, network=False)
    if execution.exit_code != 0:
        return failure(skill, FailureKind.NOT_FOUND, f"branch {branch!r} does not exist locally")
    current = execution.stdout.strip()
    if not _SHA_RE.fullmatch(current):
        return failure(
            skill, FailureKind.MALFORMED_OUTPUT, f"unexpected rev-parse output {current!r}"
        )
    return success(current == expected_head_sha)


def _reused_commit(
    repository_path: Path,
    skill: str,
    *,
    expected_head_sha: str,
    message: str,
    current_head: str,
    branch: str,
) -> SkillResult[CommitResult] | None:
    """Whether `current_head` is already the commit a repeated `create_commit` call would make.

    Idempotency per `SKILL_CONTRACTS.md` §5: `HEAD`'s parent must be the expected prior commit,
    the tree must be clean (nothing left uncommitted), and the subject line must match — anything
    less is a real precondition mismatch, not a safe reuse.
    """
    parent = _git(repository_path, ("rev-parse", f"{current_head}^"), identity=skill)
    if not parent.succeeded or parent.stdout.strip() != expected_head_sha:
        return None
    tree = _git(repository_path, ("status", "--porcelain"), identity=skill)
    if not tree.succeeded or tree.stdout.strip():
        return None
    subject = _git(repository_path, ("log", "-1", "--format=%s", current_head), identity=skill)
    expected_subject = message.strip().splitlines()[0] if message.strip() else ""
    if not subject.succeeded or subject.stdout.strip() != expected_subject:
        return None
    return success(CommitResult(commit_sha=current_head, branch=branch))


def create_commit(
    repository_path: Path,
    *,
    branch: str,
    message: str,
    expected_head_sha: str,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[CommitResult]:
    """Stage the working tree's current diff and commit it on `branch`.

    See the module docstring for why staging is `git add -A` rather than a caller-supplied path
    list. `expected_head_sha` is re-verified immediately before staging, so a branch that moved
    since validation is refused before anything is touched.
    """
    skill = "create_commit"
    if problem := _validate_refs(skill, branch=branch):
        return problem
    if not message.strip():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            "commit message must not be blank",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if problem := _validate_sha(skill, "expected_head_sha", expected_head_sha):
        return problem

    symbolic = _git(repository_path, ("symbolic-ref", "--quiet", "--short", "HEAD"), identity=skill)
    if symbolic.outcome is not CommandOutcome.COMPLETED or symbolic.exit_code != 0:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            "repository is not on a named branch",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )
    current_branch = symbolic.stdout.strip()
    if current_branch != branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"expected to be on branch {branch!r}, found {current_branch!r}",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )

    head = _git(repository_path, ("rev-parse", "HEAD"), identity=skill)
    if not head.succeeded:
        return _invoked_failure(skill, head, network=False, ambiguous=True)
    current_head = head.stdout.strip()
    if current_head != expected_head_sha:
        reused = _reused_commit(
            repository_path,
            skill,
            expected_head_sha=expected_head_sha,
            message=message,
            current_head=current_head,
            branch=branch,
        )
        if reused is not None:
            return reused
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"branch {branch!r} is at {current_head}, not the expected {expected_head_sha}",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )

    added = _git(repository_path, ("add", "-A", "--"), identity=skill)
    if not added.succeeded:
        return _invoked_failure(skill, added, network=False, ambiguous=True)
    staged = _git(repository_path, ("diff", "--cached", "--quiet"), identity=skill)
    if staged.outcome is not CommandOutcome.COMPLETED:
        return _invoked_failure(skill, staged, network=False, ambiguous=True)
    if staged.exit_code == 0:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            "nothing to commit: the working tree matches HEAD",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )

    committed = _git(repository_path, ("commit", "-m", message), identity=skill)
    if not committed.succeeded:
        return _invoked_failure(skill, committed, network=False, ambiguous=True)
    new_head = _git(repository_path, ("rev-parse", "HEAD"), identity=skill)
    if not new_head.succeeded:
        return _invoked_failure(skill, new_head, network=False, ambiguous=True)
    commit_sha = new_head.stdout.strip()
    if not _SHA_RE.fullmatch(commit_sha):
        return failure(skill, FailureKind.MALFORMED_OUTPUT, f"unexpected HEAD SHA {commit_sha!r}")
    return success(CommitResult(commit_sha=commit_sha, branch=branch))


def push_stage_branch(
    repository_path: Path,
    *,
    branch: str,
    remote: str,
    expected_head_sha: str,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[PushResult]:
    """Push the stage branch to `remote`, never the baseline, never with `--force`.

    Idempotent: if the remote ref already carries `expected_head_sha`, this is a no-op success —
    the reconciliation `SKILL_CONTRACTS.md` §5 requires after a possible-side-effect failure.
    """
    skill = "push_stage_branch"
    if problem := _validate_refs(skill, branch=branch):
        return problem
    if problem := _validate_remote(skill, remote):
        return problem
    if problem := _validate_sha(skill, "expected_head_sha", expected_head_sha):
        return problem

    local = _git(
        repository_path,
        ("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"),
        identity=skill,
    )
    if local.outcome is not CommandOutcome.COMPLETED or local.exit_code != 0:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"local branch {branch!r} not found",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )
    if local.stdout.strip() != expected_head_sha:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"local branch {branch!r} is at {local.stdout.strip()}, not the expected "
            f"{expected_head_sha}",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )

    remote_ref = f"refs/heads/{branch}"
    listing = _git(
        repository_path,
        ("ls-remote", "--exit-code", "--heads", remote, remote_ref),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if listing.outcome is not CommandOutcome.COMPLETED:
        return _invoked_failure(skill, listing, network=True, ambiguous=True)
    if listing.exit_code == 0:
        fields = listing.stdout.split()
        remote_sha = fields[0] if fields else ""
        if _SHA_RE.fullmatch(remote_sha) and remote_sha == expected_head_sha:
            return success(PushResult(remote_ref=remote_ref, head_sha=expected_head_sha))
    elif listing.exit_code != 2:
        # `--exit-code` reports 2 for "no matching refs"; anything else is a real failure.
        return _invoked_failure(skill, listing, network=True, ambiguous=True)

    pushed = _git(
        repository_path,
        ("push", remote, f"{branch}:{remote_ref}"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not pushed.succeeded:
        return _invoked_failure(skill, pushed, network=True, ambiguous=True)
    return success(PushResult(remote_ref=remote_ref, head_sha=expected_head_sha))


# --------------------------------------------------------------------------------------------
# GitHub Skills
# --------------------------------------------------------------------------------------------


def create_pull_request(
    repository_path: Path,
    *,
    branch: str,
    baseline_branch: str,
    title: str,
    body: str,
    head_sha: str,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[PullRequestInfo]:
    """Open a pull request from `branch` into `baseline_branch`, or reuse an existing open one.

    The reuse check runs first and unconditionally: `SKILL_CONTRACTS.md` §5 requires this Skill
    to be idempotent by reusing an existing open PR for the branch rather than duplicating one,
    which matters both for ordinary idempotent re-calls and for `POSSIBLE_SIDE_EFFECT`
    reconciliation after an ambiguous prior failure.
    """
    skill = "create_pull_request"
    if problem := _validate_refs(skill, branch=branch, baseline_branch=baseline_branch):
        return problem
    if problem := _reject_baseline(skill, branch, baseline_branch):
        return problem
    if not title.strip():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            "pull request title must not be blank",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if problem := _validate_sha(skill, "head_sha", head_sha):
        return problem

    listed = _gh(
        repository_path,
        (
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,url,headRefOid",
            "--limit",
            "1",
        ),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not listed.succeeded:
        return _invoked_failure(skill, listed, network=True, ambiguous=True)
    payload, error = _parse_gh_json(skill, listed)
    if error is not None:
        return error
    if isinstance(payload, list) and payload:
        record = payload[0]
        return success(
            PullRequestInfo(
                number=int(record["number"]),
                url=str(record.get("url", "")),
                head_sha=str(record.get("headRefOid", head_sha)),
            )
        )

    created = _gh(
        repository_path,
        (
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            baseline_branch,
            "--head",
            branch,
        ),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not created.succeeded:
        return _invoked_failure(skill, created, network=True, ambiguous=True)
    match = _PR_URL_RE.search(created.stdout.strip())
    if match is None:
        return failure(
            skill,
            FailureKind.MALFORMED_OUTPUT,
            f"could not find a pull request URL in gh output: {created.stdout.strip()[:200]!r}",
        )
    number = int(match.group(1))

    confirmed = _gh(
        repository_path,
        ("pr", "view", str(number), "--json", "number,url,headRefOid"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not confirmed.succeeded:
        # The PR was created (its number came from the URL gh just printed); a failure to read
        # it back is reported as ambiguous rather than assumed successful with a guessed SHA.
        return _invoked_failure(skill, confirmed, network=True, ambiguous=True)
    payload, error = _parse_gh_json(skill, confirmed)
    if error is not None:
        return error
    return success(
        PullRequestInfo(
            number=int(payload["number"]),
            url=str(payload.get("url", created.stdout.strip())),
            head_sha=str(payload.get("headRefOid", head_sha)),
        )
    )


def read_pull_request_state(
    repository_path: Path,
    *,
    pull_request_number: int,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[PullRequestState]:
    """Read a pull request's current state — the reconciliation read used when an earlier
    `create_pull_request`/merge step failed ambiguously."""
    skill = "read_pull_request_state"
    if problem := _validate_pr_number(skill, pull_request_number):
        return problem
    execution = _gh(
        repository_path,
        ("pr", "view", str(pull_request_number), "--json", "number,state,headRefOid,mergedAt"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not execution.succeeded:
        return _invoked_failure(skill, execution, network=True)
    payload, error = _parse_gh_json(skill, execution)
    if error is not None:
        return error
    state = str(payload.get("state", "")).upper()
    return success(
        PullRequestState(
            number=int(payload["number"]),
            state=state.lower(),
            head_sha=str(payload.get("headRefOid", "")),
            merged=state == "MERGED" or payload.get("mergedAt") is not None,
        )
    )


def read_required_checks(
    repository_path: Path,
    *,
    pull_request_number: int,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[RequiredChecks]:
    """Read every check configured as required for the pull request (`MACHINE_GATES.md` §6).

    `gh pr checks` exits non-zero by design whenever a required check is pending or failing, but
    still emits `--json` output in that case — so JSON parsing is attempted first, regardless of
    exit code, and only a genuinely unparseable response is treated as a failure. A repository
    with no checks reported at all is a documented `gh` message rather than JSON; that specific
    case is read as "nothing required" rather than an error.
    """
    skill = "read_required_checks"
    if problem := _validate_pr_number(skill, pull_request_number):
        return problem
    execution = _gh(
        repository_path,
        ("pr", "checks", str(pull_request_number), "--required", "--json", "name,state,bucket"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    text = execution.stdout.strip()
    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = None
    if parsed is None:
        if "no checks reported" in execution.stderr.lower():
            return success(RequiredChecks(all_passed=True, pending=(), failed=()))
        if execution.outcome is not CommandOutcome.COMPLETED:
            return _invoked_failure(skill, execution, network=True)
        return failure(
            skill,
            FailureKind.MALFORMED_OUTPUT,
            f"gh pr checks did not return valid JSON: stdout={text[:200]!r} "
            f"stderr={execution.stderr.strip()[:200]!r}",
        )
    if not isinstance(parsed, list):
        return failure(skill, FailureKind.MALFORMED_OUTPUT, "gh pr checks did not return a list")
    pending = tuple(str(item["name"]) for item in parsed if str(item.get("bucket")) == "pending")
    failed = tuple(
        str(item["name"]) for item in parsed if str(item.get("bucket")) in ("fail", "cancel")
    )
    return success(
        RequiredChecks(all_passed=not pending and not failed, pending=pending, failed=failed)
    )


def enable_automatic_squash_merge(
    repository_path: Path,
    *,
    pull_request_number: int,
    expected_head_sha: str,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[AutoMergeResult]:
    """Enable GitHub's native squash auto-merge (OD-1) for the pull request.

    Re-verifies the head SHA against GitHub itself immediately before the one merge-enabling call
    (`SECURITY_MODEL.md` §5's "destructive Skills re-verify their precondition immediately before
    execution", applied here even though this Skill is not in §5's named list, because enabling
    auto-merge is an irreversible GitHub-side state change). This Skill's argv has exactly one
    `gh pr merge` call site and it is always `--auto --squash`; there is no branch anywhere in
    this function, and no argument anywhere in this module, that reaches `--admin`
    (`SECURITY_MODEL.md` §4).
    """
    skill = "enable_automatic_squash_merge"
    if problem := _validate_pr_number(skill, pull_request_number):
        return problem
    if problem := _validate_sha(skill, "expected_head_sha", expected_head_sha):
        return problem

    current = _gh(
        repository_path,
        ("pr", "view", str(pull_request_number), "--json", "headRefOid,state"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not current.succeeded:
        return _invoked_failure(skill, current, network=True)
    payload, error = _parse_gh_json(skill, current)
    if error is not None:
        return error
    if str(payload.get("headRefOid", "")) != expected_head_sha:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            "pull request head SHA no longer matches the SHA validated for this merge",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )

    enabled = _gh(
        repository_path,
        ("pr", "merge", str(pull_request_number), "--auto", "--squash"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not enabled.succeeded:
        if "already" in enabled.stderr.lower() and "auto" in enabled.stderr.lower():
            # Idempotent: auto-merge was already enabled with the requested configuration.
            return success(AutoMergeResult(pull_request_number=pull_request_number, enabled=True))
        return _invoked_failure(skill, enabled, network=True)
    return success(AutoMergeResult(pull_request_number=pull_request_number, enabled=True))


def verify_merge_completion(
    repository_path: Path,
    *,
    pull_request_number: int,
    branch: str,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[MergeConfirmation]:
    """Independently confirm GitHub reports the pull request merged (`MACHINE_GATES.md` §6).

    The only Skill in this module that produces a `MergeConfirmation` — the token
    `CloseoutAgent.close_out` requires and cannot run without (`AGENT_CONTRACTS.md` §7). Refuses
    unless the PR's head branch still matches `branch`, so a confirmation can never be produced
    for the wrong pull request.
    """
    skill = "verify_merge_completion"
    if problem := _validate_pr_number(skill, pull_request_number):
        return problem
    if problem := _validate_refs(skill, branch=branch):
        return problem
    execution = _gh(
        repository_path,
        ("pr", "view", str(pull_request_number), "--json", "state,headRefName,mergeCommit"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not execution.succeeded:
        return _invoked_failure(skill, execution, network=True)
    payload, error = _parse_gh_json(skill, execution)
    if error is not None:
        return error
    if str(payload.get("headRefName", "")) != branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"pull request #{pull_request_number} head branch is "
            f"{payload.get('headRefName')!r}, not the expected {branch!r}",
        )
    if str(payload.get("state", "")).upper() != "MERGED":
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"GitHub reports pull request #{pull_request_number} as "
            f"{payload.get('state', 'unknown')!r}, not merged",
        )
    merge_commit = payload.get("mergeCommit") or {}
    merge_commit_sha = str(merge_commit.get("oid", ""))
    if not _SHA_RE.fullmatch(merge_commit_sha):
        return failure(
            skill, FailureKind.MALFORMED_OUTPUT, "gh reported no usable merge commit SHA"
        )
    return success(
        MergeConfirmation(branch=branch, merge_commit_sha=merge_commit_sha, verified_at=utc_now())
    )
