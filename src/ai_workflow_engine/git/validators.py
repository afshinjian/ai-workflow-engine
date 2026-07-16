from fnmatch import fnmatchcase

from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.result import CheckResult, Finding, Status


def matching_paths(paths: list[str], patterns: list[str]) -> list[str]:
    return sorted({path for path in paths for pattern in patterns if fnmatchcase(path, pattern)})


def check_git(
    config: EngineConfig,
    *,
    expected_branch: str | None = None,
    expected_head: str | None = None,
) -> CheckResult:
    client = GitClient(config.project.repository)
    state = client.status()
    findings: list[Finding] = []
    if expected_branch and state.branch != expected_branch:
        findings.append(
            Finding(
                code="branch_mismatch", message=f"Expected {expected_branch}, got {state.branch}"
            )
        )
    if expected_head and state.head != expected_head:
        findings.append(
            Finding(code="head_mismatch", message=f"Expected {expected_head}, got {state.head}")
        )
    if config.project.require_upstream and state.upstream is None:
        findings.append(
            Finding(code="upstream_missing", message="The configured project requires an upstream")
        )
    protected = matching_paths(state.staged_files, config.protected_paths.never_stage)
    never_commit = matching_paths(state.staged_files, config.protected_paths.never_commit)
    for path in protected:
        findings.append(
            Finding(code="protected_path_staged", message="Protected path is staged", path=path)
        )
    for path in never_commit:
        findings.append(
            Finding(
                code="protected_path_would_commit", message="Never-commit path is staged", path=path
            )
        )
    # Without an explicit allowed-stage list, any staged path is unexpected in read-only M1.
    for path in state.staged_files:
        if path not in protected:
            findings.append(
                Finding(code="unexpected_staged_path", message="Path is staged", path=path)
            )
    affected = sorted(set(state.modified_files + state.staged_files + state.untracked_files))
    return CheckResult(
        check_name="git",
        status=Status.FAIL if findings else Status.PASS,
        summary=(
            "Git state satisfies configured invariants"
            if not findings
            else f"Git check found {len(findings)} violation(s)"
        ),
        findings=findings,
        evidence=state.model_dump(mode="json"),
        affected_paths=affected,
        remediation_hint=(
            "Unstage unexpected paths or select the expected branch/commit." if findings else None
        ),
    )
