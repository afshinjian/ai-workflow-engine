"""Repository Skills (`SKILL_CONTRACTS.md` §2).

Every Skill here is a named function over a fixed argv. There is no general "run a git command"
entry point and no caller-supplied verb: the mutating verb of each Skill is a literal in that
Skill's own argv tuple, so the operations `SECURITY_MODEL.md` §2 forbids are not merely refused
at runtime — they are unreachable by construction. Specifically, no argv in this module contains
`--force`, `-f`, `--force-with-lease`, `push` to a baseline ref, `rebase`, `reset`, `commit
--amend`, or `filter-branch`, and no argv is assembled from a caller-supplied verb, so no
argument a caller can pass will produce one. `test_repository.py::test_no_forbidden_argv_tokens`
asserts this property against the module source rather than trusting the review that wrote it.

Baseline protection is structural in the same way. Every Skill that mutates a ref takes the
baseline branch name as a *required* parameter and refuses when its target equals the baseline,
so "delete the baseline" and "create a branch over the baseline" have no expressible form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos_workflow.skills import (
    GIT_TIMEOUT_SECONDS,
    CommandExecution,
    CommandOutcome,
    FailureKind,
    MergeConfirmation,
    RetryClassification,
    SkillResult,
    failure,
    run_fixed_argv,
    success,
)

__all__ = [
    "BranchState",
    "DiffSummary",
    "RepositoryIdentity",
    "WorkingTree",
    "WorkingTreeEntry",
    "checkout_baseline",
    "create_stage_branch",
    "delete_local_branch",
    "delete_remote_branch",
    "fast_forward_pull",
    "inspect_current_branch",
    "inspect_diff",
    "list_changed_files",
    "verify_baseline_ancestry",
    "verify_final_repository_state",
    "verify_repository_identity",
]

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_REMOTE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


@dataclass(frozen=True)
class RepositoryIdentity:
    remote_name: str
    remote_url: str
    normalized_identity: str
    matches_expected: bool


@dataclass(frozen=True)
class WorkingTreeEntry:
    index_status: str
    worktree_status: str
    path: str

    @property
    def is_untracked(self) -> bool:
        return self.index_status == "?" and self.worktree_status == "?"


@dataclass(frozen=True)
class WorkingTree:
    clean: bool
    entries: tuple[WorkingTreeEntry, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.entries)


@dataclass(frozen=True)
class BranchState:
    branch: str | None
    head_sha: str
    detached: bool


@dataclass(frozen=True)
class DiffSummary:
    base: str
    branch: str
    files_changed: int
    insertions: int
    deletions: int
    paths: tuple[str, ...]


# --------------------------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------------------------


def _ref_problem(value: str) -> str | None:
    """Why `value` is not a safe Git ref component, or `None`.

    Same rule set AUTO-002 established in `observation/local.py`. A leading `-` matters most:
    without this check a branch literally named `--force` would be assembled into an argv where
    Git reads it as an option rather than a ref.
    """
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
    """Validate every ref argument, returning a failure result on the first problem."""
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
    """Refuse any ref mutation whose target is the configured baseline (`SECURITY_MODEL.md` §2)."""
    if target == baseline_branch:
        return failure(
            skill,
            FailureKind.PERMANENT,
            f"refusing to target the configured baseline branch {baseline_branch!r}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


# --------------------------------------------------------------------------------------------
# Git invocation
# --------------------------------------------------------------------------------------------


def _git(
    repository_path: Path,
    args: tuple[str, ...],
    *,
    identity: str,
    timeout_seconds: int = GIT_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> CommandExecution:
    """Invoke Git with a fixed argv against an explicit repository.

    `-C <repo>` rather than a process-wide chdir keeps Skills safe to call concurrently, and
    `--no-optional-locks` keeps read-only Skills from taking a lock that would contend with the
    Orchestrator's own repository lock.
    """
    return run_fixed_argv(
        ("git", "--no-optional-locks", "-C", str(repository_path), *args),
        identity=identity,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


def _git_failure(
    skill: str, execution: CommandExecution, *, network: bool = False
) -> SkillResult[Any]:
    """Translate a failed Git invocation into the typed failure the Orchestrator expects.

    The retry classification follows `SKILL_CONTRACTS.md` §5 exactly. A spawn failure is the only
    *proven* pre-side-effect case — Git was never invoked, so nothing could have reached a
    remote. Every other failure of an invoked subprocess that could have touched a remote is
    `POSSIBLE_SIDE_EFFECT`, including a timeout: a timeout cannot distinguish "the request never
    left the machine" from "the write landed and the acknowledgment was lost".
    """
    if execution.outcome is CommandOutcome.SPAWN_FAILED:
        return failure(
            skill,
            FailureKind.SPAWN_FAILED,
            f"git could not be executed: {execution.stderr or 'no diagnostic'}",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )
    classification = (
        RetryClassification.POSSIBLE_SIDE_EFFECT if network else RetryClassification.NOT_APPLICABLE
    )
    if execution.outcome is CommandOutcome.TIMED_OUT:
        return failure(
            skill,
            FailureKind.TIMEOUT,
            f"git timed out after {GIT_TIMEOUT_SECONDS}s",
            retry_classification=classification,
        )
    detail = execution.stderr.strip() or execution.stdout.strip() or "no diagnostic"
    return failure(
        skill,
        FailureKind.COMMAND_FAILED,
        f"git exited {execution.exit_code}: {detail}",
        retry_classification=classification,
    )


# --------------------------------------------------------------------------------------------
# Read-only Skills
# --------------------------------------------------------------------------------------------


def _normalize_remote_url(url: str) -> str:
    """Reduce a remote URL to a comparable `host/owner/repo` identity.

    SSH (`git@host:owner/repo.git`), HTTPS, and `ssh://` spellings of the same repository must
    compare equal, or a workflow configured with one spelling would refuse a repository cloned
    with the other. Any userinfo component is dropped rather than compared — it is a credential
    (`SECURITY_MODEL.md` §1), and it is not part of repository identity.
    """
    candidate = url.strip()
    for scheme in ("ssh://", "git://", "https://", "http://"):
        if candidate.startswith(scheme):
            candidate = candidate[len(scheme) :]
            break
    else:
        # `git@host:owner/repo.git` — the scp-like form, where `:` separates host from path.
        if "@" in candidate and ":" in candidate.split("@", 1)[1]:
            host, _, path = candidate.split("@", 1)[1].partition(":")
            candidate = f"{host}/{path}"
    if "@" in candidate:
        candidate = candidate.split("@", 1)[1]
    candidate = candidate.split("#", 1)[0].split("?", 1)[0]
    if candidate.endswith(".git"):
        candidate = candidate[: -len(".git")]
    host, _, path = candidate.partition("/")
    host = host.split(":", 1)[0].lower()
    return f"{host}/{path.strip('/')}" if path else host


def verify_repository_identity(
    repository_path: Path, *, expected_identity: str, remote_name: str
) -> SkillResult[RepositoryIdentity]:
    """Confirm the repository at `repository_path` is the one the workflow was authorized for.

    `SECURITY_MODEL.md` §6 requires this before any mutation and again on resume. A mismatch is
    `PERMANENT`: pointing the engine at the wrong repository is never something a retry fixes.
    """
    skill = "verify_repository_identity"
    if problem := _validate_remote(skill, remote_name):
        return problem
    if not expected_identity.strip():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            "expected_identity must not be blank",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if not repository_path.is_dir():
        return failure(
            skill,
            FailureKind.NOT_FOUND,
            f"{repository_path} does not exist or is not a directory",
        )
    inside = _git(repository_path, ("rev-parse", "--is-inside-work-tree"), identity=skill)
    if not inside.succeeded or inside.stdout.strip() != "true":
        return failure(skill, FailureKind.PRECONDITION, f"{repository_path} is not a Git work tree")
    execution = _git(repository_path, ("remote", "get-url", remote_name), identity=skill)
    if not execution.succeeded:
        return _git_failure(skill, execution)
    remote_url = execution.stdout.strip()
    normalized = _normalize_remote_url(remote_url)
    expected_normalized = _normalize_remote_url(expected_identity)
    identity = RepositoryIdentity(
        remote_name=remote_name,
        # The raw URL may carry userinfo; never surface it in evidence.
        remote_url=_normalize_remote_url(remote_url),
        normalized_identity=normalized,
        matches_expected=normalized == expected_normalized,
    )
    if not identity.matches_expected:
        return failure(
            skill,
            FailureKind.PERMANENT,
            f"repository identity {normalized!r} does not match expected "
            f"{expected_normalized!r}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return success(identity)


def inspect_working_tree(repository_path: Path) -> SkillResult[WorkingTree]:
    """Report whether the working tree is clean, and every path that makes it dirty."""
    skill = "inspect_working_tree"
    execution = _git(
        repository_path,
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
        identity=skill,
    )
    if not execution.succeeded:
        return _git_failure(skill, execution)
    entries: list[WorkingTreeEntry] = []
    fields = execution.stdout.split("\0")
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            return failure(
                skill, FailureKind.MALFORMED_OUTPUT, f"malformed porcelain record {record!r}"
            )
        x, y, path = record[0], record[1], record[3:]
        if "R" in (x, y) or "C" in (x, y):
            # A rename/copy record is followed by its origin path in the NUL stream; consume it
            # so it is not mistaken for the next entry.
            index += 1
        entries.append(WorkingTreeEntry(index_status=x, worktree_status=y, path=path))
    return success(WorkingTree(clean=not entries, entries=tuple(entries)))


def inspect_current_branch(repository_path: Path) -> SkillResult[BranchState]:
    """Report the checked-out branch and HEAD SHA, tolerating a detached HEAD."""
    skill = "inspect_current_branch"
    head = _git(repository_path, ("rev-parse", "HEAD"), identity=skill)
    if not head.succeeded:
        return _git_failure(skill, head)
    head_sha = head.stdout.strip()
    if not _SHA_RE.fullmatch(head_sha):
        return failure(skill, FailureKind.MALFORMED_OUTPUT, f"unexpected HEAD SHA {head_sha!r}")
    symbolic = _git(repository_path, ("symbolic-ref", "--quiet", "--short", "HEAD"), identity=skill)
    if symbolic.succeeded:
        return success(
            BranchState(branch=symbolic.stdout.strip(), head_sha=head_sha, detached=False)
        )
    if symbolic.outcome is not CommandOutcome.COMPLETED:
        return _git_failure(skill, symbolic)
    # `symbolic-ref --quiet` exits non-zero with no diagnostic exactly when HEAD is detached.
    return success(BranchState(branch=None, head_sha=head_sha, detached=True))


def verify_baseline_ancestry(
    repository_path: Path, *, baseline_branch: str, branch: str = "HEAD"
) -> SkillResult[bool]:
    """Confirm `branch` descends from `baseline_branch`.

    A stage branch that does not descend from the baseline was cut from the wrong place, and
    every scope and diff judgment made against it afterwards would be measured from the wrong
    origin.
    """
    skill = "verify_baseline_ancestry"
    if problem := _validate_refs(skill, baseline_branch=baseline_branch):
        return problem
    if branch != "HEAD" and (problem := _validate_refs(skill, branch=branch)):
        return problem
    execution = _git(
        repository_path,
        ("merge-base", "--is-ancestor", baseline_branch, branch),
        identity=skill,
    )
    if execution.outcome is not CommandOutcome.COMPLETED:
        return _git_failure(skill, execution)
    if execution.exit_code == 0:
        return success(True)
    if execution.exit_code == 1:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"{branch} does not descend from baseline {baseline_branch!r}",
        )
    return _git_failure(skill, execution)


def list_changed_files(
    repository_path: Path, *, base: str, branch: str
) -> SkillResult[tuple[str, ...]]:
    """List the paths `branch` changed relative to its merge base with `base`.

    Three-dot (`base...branch`) rather than two-dot is deliberate: it answers "what did this
    branch introduce", which is the question scope enforcement actually asks. Two-dot would also
    report everything that landed on the baseline after the branch was cut, so an unrelated
    baseline commit touching a forbidden path would be attributed to the stage.
    """
    skill = "list_changed_files"
    if problem := _validate_refs(skill, base=base, branch=branch):
        return problem
    execution = _git(
        repository_path, ("diff", "--name-only", "-z", f"{base}...{branch}", "--"), identity=skill
    )
    if not execution.succeeded:
        return _git_failure(skill, execution)
    return success(tuple(sorted(path for path in execution.stdout.split("\0") if path)))


def inspect_diff(repository_path: Path, *, base: str, branch: str) -> SkillResult[DiffSummary]:
    """Summarize the diff `branch` introduces relative to `base` (counts and paths, never content).

    The diff *content* is deliberately not returned: it is unbounded, may contain secrets, and no
    deterministic Skill needs it. Agents that need content get it through their own contract.
    """
    skill = "inspect_diff"
    if problem := _validate_refs(skill, base=base, branch=branch):
        return problem
    execution = _git(
        repository_path, ("diff", "--numstat", "-z", f"{base}...{branch}", "--"), identity=skill
    )
    if not execution.succeeded:
        return _git_failure(skill, execution)
    insertions = 0
    deletions = 0
    paths: list[str] = []
    fields = [entry for entry in execution.stdout.split("\0") if entry]
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        parts = record.split("\t")
        if len(parts) != 3:
            return failure(skill, FailureKind.MALFORMED_OUTPUT, f"malformed numstat {record!r}")
        added, removed, path = parts
        if not path:
            # A rename in `-z` numstat emits an empty path field followed by the old and new
            # paths as their own NUL-terminated fields.
            if index + 1 >= len(fields):
                return failure(skill, FailureKind.MALFORMED_OUTPUT, "truncated rename record")
            path = fields[index + 1]
            index += 2
        # `-` means a binary file, whose line counts are undefined rather than zero.
        insertions += int(added) if added.isdigit() else 0
        deletions += int(removed) if removed.isdigit() else 0
        paths.append(path)
    return success(
        DiffSummary(
            base=base,
            branch=branch,
            files_changed=len(paths),
            insertions=insertions,
            deletions=deletions,
            paths=tuple(sorted(paths)),
        )
    )


def verify_final_repository_state(
    repository_path: Path, *, baseline_branch: str
) -> SkillResult[BranchState]:
    """Confirm the repository is back on a clean baseline at the end of a workflow."""
    skill = "verify_final_repository_state"
    if problem := _validate_refs(skill, baseline_branch=baseline_branch):
        return problem
    branch_result = inspect_current_branch(repository_path)
    if not branch_result.ok or branch_result.value is None:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"could not determine current branch: {branch_result.error}",
        )
    state = branch_result.value
    if state.branch != baseline_branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"expected to be on baseline {baseline_branch!r}, found "
            f"{'detached HEAD' if state.detached else repr(state.branch)}",
        )
    tree_result = inspect_working_tree(repository_path)
    if not tree_result.ok or tree_result.value is None:
        return failure(
            skill, FailureKind.PRECONDITION, f"could not inspect working tree: {tree_result.error}"
        )
    if not tree_result.value.clean:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"working tree is not clean: {len(tree_result.value.entries)} changed path(s)",
        )
    return success(state)


# --------------------------------------------------------------------------------------------
# Mutating Skills
# --------------------------------------------------------------------------------------------


def create_stage_branch(
    repository_path: Path, *, branch_name: str, base_sha: str, baseline_branch: str
) -> SkillResult[BranchState]:
    """Create the stage branch at `base_sha`, or confirm it already exists there.

    Idempotent per `SKILL_CONTRACTS.md` §2: a second call with the same inputs is a no-op that
    succeeds. A branch that already exists at a *different* commit is a hard failure rather than
    a silent move — moving it would rewrite the stage's baseline, which `SECURITY_MODEL.md` §2
    forbids. Note the argv is `branch <name> <sha>`, which refuses to move an existing branch;
    `--force` is absent by construction.
    """
    skill = "create_stage_branch"
    if problem := _validate_refs(skill, branch_name=branch_name, baseline_branch=baseline_branch):
        return problem
    if problem := _reject_baseline(skill, branch_name, baseline_branch):
        return problem
    if not _SHA_RE.fullmatch(base_sha):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"base_sha={base_sha!r} is not a full 40-character SHA",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    existing = _git(
        repository_path,
        ("show-ref", "--verify", "--hash", f"refs/heads/{branch_name}"),
        identity=skill,
    )
    if existing.succeeded:
        current = existing.stdout.strip()
        if current == base_sha:
            return success(BranchState(branch=branch_name, head_sha=current, detached=False))
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"branch {branch_name!r} already exists at {current}, not the expected {base_sha}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if existing.outcome is not CommandOutcome.COMPLETED:
        return _git_failure(skill, existing)
    execution = _git(repository_path, ("branch", branch_name, base_sha), identity=skill)
    if not execution.succeeded:
        return _git_failure(skill, execution)
    return success(BranchState(branch=branch_name, head_sha=base_sha, detached=False))


def checkout_baseline(repository_path: Path, *, baseline_branch: str) -> SkillResult[BranchState]:
    """Switch the working tree to the baseline branch.

    Destructive with respect to local state, so `SECURITY_MODEL.md` §5's precondition — "only
    after confirming no uncommitted stage-branch work would be lost" — is re-verified here,
    immediately before execution, not merely earlier in the workflow. The argv is `checkout
    <branch>` with no `--force` and no `-B`, so an unclean tree makes Git itself refuse too;
    the explicit check exists so the refusal is a typed precondition failure rather than an
    opaque exit code.
    """
    skill = "checkout_baseline"
    if problem := _validate_refs(skill, baseline_branch=baseline_branch):
        return problem
    branch_result = inspect_current_branch(repository_path)
    if not branch_result.ok or branch_result.value is None:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"could not determine current branch: {branch_result.error}",
        )
    if branch_result.value.branch == baseline_branch:
        return success(branch_result.value)
    tree_result = inspect_working_tree(repository_path)
    if not tree_result.ok or tree_result.value is None:
        return failure(
            skill, FailureKind.PRECONDITION, f"could not inspect working tree: {tree_result.error}"
        )
    if not tree_result.value.clean:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            "refusing to switch to baseline with uncommitted work in the tree: "
            f"{len(tree_result.value.entries)} changed path(s) would be at risk",
        )
    execution = _git(repository_path, ("checkout", baseline_branch, "--"), identity=skill)
    if not execution.succeeded:
        return _git_failure(skill, execution)
    return verify_final_repository_state(repository_path, baseline_branch=baseline_branch)


def fast_forward_pull(
    repository_path: Path,
    *,
    baseline_branch: str,
    remote: str,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[BranchState]:
    """Fast-forward the baseline from its remote, refusing any divergence.

    Split into `fetch` then `merge --ff-only` rather than `git pull` so the merge behavior is
    fixed in this module's argv and cannot be changed by the target repository's `pull.rebase`
    or `pull.ff` configuration. `--ff-only` means divergence is a hard refusal, never a forced
    update (`SECURITY_MODEL.md` §5); no `--rebase` and no `--force` appear here.
    """
    skill = "fast_forward_pull"
    if problem := _validate_refs(skill, baseline_branch=baseline_branch):
        return problem
    if problem := _validate_remote(skill, remote):
        return problem
    current = inspect_current_branch(repository_path)
    if not current.ok or current.value is None:
        return failure(
            skill, FailureKind.PRECONDITION, f"could not determine current branch: {current.error}"
        )
    if current.value.branch != baseline_branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"must be on baseline {baseline_branch!r} to fast-forward it, found "
            f"{'detached HEAD' if current.value.detached else repr(current.value.branch)}",
        )
    tree_result = inspect_working_tree(repository_path)
    if not tree_result.ok or tree_result.value is None:
        return failure(
            skill, FailureKind.PRECONDITION, f"could not inspect working tree: {tree_result.error}"
        )
    if not tree_result.value.clean:
        return failure(
            skill, FailureKind.PRECONDITION, "refusing to fast-forward with an unclean working tree"
        )
    fetch = _git(
        repository_path,
        ("fetch", "--no-tags", remote, baseline_branch),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not fetch.succeeded:
        # A fetch is read-only at the remote, so a failure here cannot have mutated anything;
        # it is nonetheless reported as a possible-side-effect network failure because the
        # local ref update is what the caller cares about and cannot be confirmed from here.
        return _git_failure(skill, fetch, network=True)
    merge = _git(repository_path, ("merge", "--ff-only", "FETCH_HEAD"), identity=skill)
    if not merge.succeeded:
        return _git_failure(skill, merge)
    return inspect_current_branch(repository_path)


def delete_local_branch(
    repository_path: Path,
    *,
    branch: str,
    baseline_branch: str,
    merge_confirmation: MergeConfirmation,
) -> SkillResult[bool]:
    """Delete a merged stage branch locally. No-op if already absent.

    `merge_confirmation` is required and has no default: `SECURITY_MODEL.md` §5 forbids deleting
    a branch without the merge having been independently verified first, and a required token
    makes "delete without verifying" unexpressible rather than merely discouraged. The argv uses
    `branch -d` (safe delete), never `-D`/`--force`, so Git independently refuses an unmerged
    branch even if a caller were to forge the token.
    """
    skill = "delete_local_branch"
    if problem := _validate_refs(skill, branch=branch, baseline_branch=baseline_branch):
        return problem
    if problem := _reject_baseline(skill, branch, baseline_branch):
        return problem
    if merge_confirmation.branch != branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"merge confirmation is for {merge_confirmation.branch!r}, not {branch!r}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    existing = _git(
        repository_path, ("show-ref", "--verify", "--quiet", f"refs/heads/{branch}"), identity=skill
    )
    if existing.outcome is not CommandOutcome.COMPLETED:
        return _git_failure(skill, existing)
    if existing.exit_code != 0:
        return success(False)
    current = inspect_current_branch(repository_path)
    if current.ok and current.value is not None and current.value.branch == branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"cannot delete {branch!r} while it is checked out; check out the baseline first",
        )
    execution = _git(repository_path, ("branch", "-d", branch), identity=skill)
    if not execution.succeeded:
        return _git_failure(skill, execution)
    return success(True)


def delete_remote_branch(
    repository_path: Path,
    *,
    branch: str,
    baseline_branch: str,
    remote: str,
    merge_confirmation: MergeConfirmation,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[bool]:
    """Delete a merged stage branch on the remote. No-op if already absent.

    The argv is `push <remote> --delete <branch>`. `--delete` cannot create or overwrite a ref,
    so this Skill has no reachable force-push or history-rewrite behavior even though it is the
    only Skill in this module that writes to a remote. The baseline check above it means the
    branch being deleted can never be the baseline.

    A failure after the subprocess ran is `POSSIBLE_SIDE_EFFECT`: the remote may have processed
    the deletion before the connection dropped, so the caller must reconcile (re-observe whether
    the remote ref still exists) rather than blindly retry.
    """
    skill = "delete_remote_branch"
    if problem := _validate_refs(skill, branch=branch, baseline_branch=baseline_branch):
        return problem
    if problem := _validate_remote(skill, remote):
        return problem
    if problem := _reject_baseline(skill, branch, baseline_branch):
        return problem
    if merge_confirmation.branch != branch:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"merge confirmation is for {merge_confirmation.branch!r}, not {branch!r}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    listing = _git(
        repository_path,
        ("ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}"),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if listing.outcome is not CommandOutcome.COMPLETED:
        return _git_failure(skill, listing, network=True)
    if listing.exit_code == 2:
        # `--exit-code` reports 2 for "no matching refs" — already deleted, so this is the
        # idempotent no-op rather than a failure.
        return success(False)
    if listing.exit_code != 0:
        return _git_failure(skill, listing, network=True)
    execution = _git(
        repository_path,
        ("push", remote, "--delete", branch),
        identity=skill,
        allowed_environment_variables=allowed_environment_variables,
    )
    if not execution.succeeded:
        return _git_failure(skill, execution, network=True)
    return success(True)
