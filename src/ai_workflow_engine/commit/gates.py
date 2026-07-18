"""Controlled commit, push, and apply-patch gates (Milestone 4, tasks T-402/T-403).

Each gate reads live Git state via the read-only `GitClient`, performs its write (if any) via
`GitWriter`, and re-verifies; any mismatch refuses and performs no (further) write. The commit and
push gates are bound to a human approval artifact; apply-patch is bound instead to a verified
Milestone 3 run artifact and a live-HEAD check (it writes only the working tree). See
``docs/milestone-4-plan.md``.
"""

import hashlib
from pathlib import Path

from ai_workflow_engine.agents.artifacts import ArtifactError, load_run, run_patch_path
from ai_workflow_engine.git.approval import CommitApproval, PushApproval, approval_digest
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.validators import matching_paths
from ai_workflow_engine.git.writer import GitWriteError, GitWriter
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import normalize_allowed_path, normalize_text
from ai_workflow_engine.prompt.models import WorkflowStage
from ai_workflow_engine.result import CheckResult, Finding, Status

_CHECK_NAME = "commit"
_PUSH_CHECK_NAME = "push"
_APPLY_CHECK_NAME = "apply-patch"


def _fail(summary: str, findings: list[Finding], evidence: dict[str, object]) -> CheckResult:
    return _fail_named(_CHECK_NAME, summary, findings, evidence)


def _fail_named(
    check_name: str, summary: str, findings: list[Finding], evidence: dict[str, object]
) -> CheckResult:
    return CheckResult(
        check_name=check_name,
        status=Status.FAIL,
        summary=summary,
        findings=findings,
        evidence=evidence,
        affected_paths=sorted({f.path for f in findings if f.path}),
        remediation_hint="Reconcile the approval with the working tree, or correct the approval.",
    )


def _normalized_allowed_paths(config: EngineConfig, approval: CommitApproval) -> list[str]:
    repository = config.project.repository
    normalized = {
        normalize_allowed_path(raw, repository=repository) for raw in approval.allowed_paths
    }
    if not normalized:
        raise GitWriteError("approval allowed_paths is empty after normalization")
    return sorted(normalized)


def run_commit_gate(
    config: EngineConfig, approval: CommitApproval, approval_path: Path
) -> CheckResult:
    """Stage exactly the approved paths and create the approved commit, or refuse."""
    client = GitClient(config.project.repository)
    writer = GitWriter(config.project.repository)
    audit: dict[str, object] = {
        "approval_sha256": approval_digest(approval_path),
        "approved_by": approval.approved_by,
        "task_id": approval.task_id,
    }

    allowed = _normalized_allowed_paths(config, approval)

    # Protected paths are rejected even if the approval lists them.
    protected = sorted(
        set(
            matching_paths(allowed, config.protected_paths.never_stage)
            + matching_paths(allowed, config.protected_paths.never_commit)
        )
    )
    if protected:
        return _fail(
            "Approval lists protected paths",
            [
                Finding(code="protected_path_violation", message="Path is protected", path=path)
                for path in protected
            ],
            audit,
        )

    state = client.status()

    # Branch / HEAD gate.
    findings: list[Finding] = []
    if state.branch != approval.branch:
        findings.append(
            Finding(
                code="branch_mismatch",
                message=f"Live branch {state.branch!r} != approved {approval.branch!r}",
            )
        )
    if state.head != approval.head:
        findings.append(
            Finding(
                code="head_mismatch",
                message=f"Live HEAD {state.head} != approved parent {approval.head}",
            )
        )
    if findings:
        return _fail("Branch/HEAD do not match the approval", findings, audit)

    # Clean-index precondition: the index must start empty so staging is deterministic.
    if state.staged_files:
        return _fail(
            "The index is not clean before staging",
            [Finding(code="index_not_clean", message="Unexpected staged paths present")],
            audit,
        )

    # Live changed set (modified + untracked). Deletions appear in modified_files via porcelain.
    live_changed = sorted(set(state.modified_files) | set(state.untracked_files))

    # Every changed path must be approved; every approved path must be a real change.
    unapproved = [path for path in live_changed if path not in allowed]
    if unapproved:
        return _fail(
            "Working tree has changes outside the approved path set",
            [
                Finding(
                    code="unapproved_change", message="Change is not in the approval", path=path
                )
                for path in unapproved
            ],
            audit,
        )
    missing = [path for path in allowed if path not in live_changed]
    if missing:
        return _fail(
            "Approved paths have no working-tree change",
            [
                Finding(code="nothing_to_stage", message="Approved path is unchanged", path=path)
                for path in missing
            ],
            audit,
        )

    # Stage exactly the approved paths.
    writer.stage_paths(allowed)

    # Defensive assertion: the staged set must equal the approval exactly.
    staged = client.staged_names()
    if staged != allowed:
        writer.unstage_paths(allowed)
        return _fail(
            "Staged set diverged from the approval",
            [Finding(code="staged_set_mismatch", message=f"Staged {staged} != approved {allowed}")],
            audit,
        )

    # Commit.
    writer.commit(approval.message)

    # Post-hoc verification.
    new_head = client.head()
    post_findings: list[Finding] = []
    parent = client.commit_parent(new_head)
    if parent != approval.head:
        post_findings.append(
            Finding(
                code="commit_mismatch",
                message=f"Commit parent {parent} != approved {approval.head}",
            )
        )
    committed = client.commit_change_names(approval.head, new_head)
    if committed != allowed:
        post_findings.append(
            Finding(
                code="commit_mismatch", message=f"Committed paths {committed} != approved {allowed}"
            )
        )
    if client.commit_message(new_head).rstrip("\n") != approval.message.rstrip("\n"):
        post_findings.append(
            Finding(code="commit_mismatch", message="Committed message does not match the approval")
        )

    audit["commit"] = new_head
    if post_findings:
        # The commit exists but does not match; report loudly (Milestone 4 does not auto-revert).
        return _fail("Commit created but does not match the approval", post_findings, audit)

    return CheckResult(
        check_name=_CHECK_NAME,
        status=Status.PASS,
        summary=f"Committed {len(allowed)} approved path(s) as {new_head[:12]}",
        findings=[],
        evidence=audit,
        affected_paths=allowed,
        remediation_hint=None,
    )


def run_push_gate(config: EngineConfig, approval: PushApproval, approval_path: Path) -> CheckResult:
    """Verify the push preconditions against live Git, then push once, or refuse."""
    client = GitClient(config.project.repository)
    writer = GitWriter(config.project.repository)
    audit: dict[str, object] = {
        "approval_sha256": approval_digest(approval_path),
        "approved_by": approval.approved_by,
        "task_id": approval.task_id,
    }

    state = client.status()
    findings: list[Finding] = []
    if state.branch != approval.branch:
        findings.append(
            Finding(
                code="branch_mismatch",
                message=f"Live branch {state.branch!r} != approved {approval.branch!r}",
            )
        )
    if state.head != approval.head:
        findings.append(
            Finding(
                code="head_mismatch", message=f"Live HEAD {state.head} != approved {approval.head}"
            )
        )
    if state.upstream is None or state.upstream != approval.upstream:
        findings.append(
            Finding(
                code="upstream_mismatch",
                message=f"Live upstream {state.upstream!r} != approved {approval.upstream!r}",
            )
        )
    if state.modified_files or state.staged_files or state.untracked_files:
        findings.append(
            Finding(code="dirty_worktree", message="The working tree must be clean before pushing")
        )
    if findings:
        return _fail_named(_PUSH_CHECK_NAME, "Push preconditions not met", findings, audit)

    behind, ahead = client.strict_left_right_count()
    audit["behind"] = behind
    audit["ahead"] = ahead
    if behind != 0:
        return _fail_named(
            _PUSH_CHECK_NAME,
            "Local branch is behind the upstream",
            [
                Finding(
                    code="behind_remote",
                    message=f"behind by {behind}; a fast-forward is impossible",
                )
            ],
            audit,
        )
    if ahead == 0:
        return _fail_named(
            _PUSH_CHECK_NAME,
            "Nothing to push",
            [Finding(code="nothing_to_push", message="the branch is not ahead of its upstream")],
            audit,
        )
    if not client.diff_check():
        return _fail_named(
            _PUSH_CHECK_NAME,
            "Working tree has conflict markers or whitespace errors",
            [Finding(code="diff_check_failed", message="git diff --check reported problems")],
            audit,
        )

    writer.push()
    return CheckResult(
        check_name=_PUSH_CHECK_NAME,
        status=Status.PASS,
        summary=f"Pushed {ahead} commit(s) to {approval.upstream}",
        findings=[],
        evidence=audit,
        affected_paths=[],
        remediation_hint=None,
    )


def run_apply_patch_gate(
    config: EngineConfig, *, task_id: str, stage: WorkflowStage, run_id: str
) -> CheckResult:
    """Apply a verified Milestone 3 patch to the working tree, gated, or refuse.

    This is the one writable op not bound to a human approval: it is bound to a verified run
    artifact + a live-HEAD match + an apply --check dry run + a no-overlap check, and it writes
    only the working tree (never stages/commits/pushes).
    """
    client = GitClient(config.project.repository)
    writer = GitWriter(config.project.repository)
    # Normalize the task ID the same way the runner/state paths do, so a whitespace/NFC variant
    # addresses the same stored run rather than silently missing it.
    task_id = normalize_text(task_id)
    audit: dict[str, object] = {"task_id": task_id, "stage": stage, "run_id": run_id}

    try:
        record = load_run(config.project.id, task_id, stage, run_id)
    except ArtifactError as exc:
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Agent-run artifact is unavailable or invalid",
            [Finding(code="run_unavailable", message=str(exc))],
            audit,
        )
    if record.verification.status != "PASS":
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Agent run did not pass verification",
            [Finding(code="run_not_verified", message=f"run {run_id} verification is not PASS")],
            audit,
        )
    if record.agent_mode != "scoped-write":
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Agent run is not a scoped-write run",
            [
                Finding(
                    code="run_not_scoped_write", message=f"run {run_id} mode is {record.agent_mode}"
                )
            ],
            audit,
        )

    live_head = client.head()
    if live_head != record.repository_head:
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Live HEAD differs from the run's recorded head",
            [
                Finding(
                    code="head_drift",
                    message=f"live {live_head} != recorded {record.repository_head}",
                )
            ],
            audit,
        )

    # Reconstruct the patch bytes from the stored .patch member and re-verify them against the
    # record's digest (load_run verified the on-disk member, but we re-read here, so close the
    # read-time-of-check/time-of-use window before applying anything).
    patch = run_patch_path(config.project.id, task_id, stage, run_id).read_bytes()
    if hashlib.sha256(patch).hexdigest() != record.patch_sha256:
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Stored patch changed between verification and read",
            [Finding(code="patch_digest_mismatch", message="patch bytes do not match the record")],
            audit,
        )

    # Clean-tree precondition. Requiring a clean working tree is strictly stronger than a
    # per-path no-overlap check: the patch cannot collide with un-committed human work because
    # there is none. (The stored patch's own path set is not needed once the tree is clean.)
    state = client.status()
    if state.modified_files or state.staged_files or state.untracked_files:
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Working tree has uncommitted changes; refusing to apply",
            [
                Finding(
                    code="dirty_overlap", message="clean the working tree before applying a patch"
                )
            ],
            audit,
        )

    if not writer.apply_check(patch):
        return _fail_named(
            _APPLY_CHECK_NAME,
            "Patch does not apply cleanly to the working tree",
            [Finding(code="apply_check_failed", message="git apply --check failed")],
            audit,
        )

    writer.apply_patch(patch)
    after = client.status()
    applied = set(after.modified_files) | set(after.untracked_files)
    return CheckResult(
        check_name=_APPLY_CHECK_NAME,
        status=Status.PASS,
        summary=f"Applied run {run_id}'s patch to the working tree",
        findings=[],
        evidence={**audit, "applied_paths": sorted(applied)},
        affected_paths=sorted(applied),
        remediation_hint=None,
    )
