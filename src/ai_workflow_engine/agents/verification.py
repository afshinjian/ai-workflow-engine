"""Independent verification of an agent run (Milestone 3, task T-305).

Turns a :class:`~ai_workflow_engine.agents.runner.RunObservation` into a ``CheckResult``. This
module *judges* the evidence the runner already captured — it does not re-run the agent or the
verification commands. Every claim the agent made is checked against the sandbox reality the
runner observed; an unverifiable or false claim is a FAIL finding, never a warning. See
``docs/milestone-3-plan.md``.
"""

import posixpath

from ai_workflow_engine.agents.runner import RunObservation
from ai_workflow_engine.git.validators import matching_paths
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.models import RenderedPrompt
from ai_workflow_engine.result import CheckResult, Finding, Status

_CHECK_NAME = "agent-run"


def _is_within(path: str, allowed: str) -> bool:
    """True if ``path`` equals ``allowed`` or lies strictly beneath it (directory prefix)."""
    if path == allowed:
        return True
    prefix = allowed.rstrip("/") + "/"
    return path.startswith(prefix)


def _repo_relative_posix(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path:
        return False
    normalized = posixpath.normpath(path)
    return not (normalized in {"", ".", ".."} or normalized.startswith("../"))


def verify_run(
    config: EngineConfig, rendered: RenderedPrompt, observation: RunObservation
) -> CheckResult:
    """Judge a completed run's observations against the governing prompt."""
    findings: list[Finding] = []

    # A runner-classified failure (timeout, bad output, repository mutation, ...) is terminal;
    # there is no verified report to judge, so surface it as the finding and stop.
    if not observation.ok or observation.report is None:
        code = observation.failure_code or "run_failed"
        return CheckResult(
            check_name=_CHECK_NAME,
            status=Status.FAIL,
            summary=f"Agent run did not produce a verifiable report ({code})",
            findings=[Finding(code=code, message=f"Run failed with {code}")],
            remediation_hint="Inspect the stored agent-run artifact and the agent's stderr.",
        )

    report = observation.report
    actual = observation.actual_changed_paths
    claimed = report.changed_paths

    # 1. Every actually-changed path must be a well-formed repo-relative POSIX path.
    for path in actual:
        if not _repo_relative_posix(path):
            findings.append(
                Finding(
                    code="malformed_changed_path",
                    message="Sandbox changed path is not repo-relative POSIX",
                    path=path,
                )
            )

    # 2. Claim equality: the report's changed_paths must equal the sandbox reality exactly.
    if claimed != actual:
        findings.append(
            Finding(
                code="claim_mismatch",
                message=(
                    f"Reported changed_paths {claimed} do not equal the actual sandbox "
                    f"change set {actual}"
                ),
            )
        )

    # 3. Scope containment: every actual change must be inside a rendered allowed path.
    allowed = rendered.context.allowed_paths
    for path in actual:
        if not any(_is_within(path, entry) for entry in allowed):
            findings.append(
                Finding(
                    code="scope_violation",
                    message="Changed path is outside the rendered allowed-path list",
                    path=path,
                )
            )

    # 4. Protected paths must never be changed.
    protected = matching_paths(actual, config.protected_paths.never_stage) + matching_paths(
        actual, config.protected_paths.never_commit
    )
    for path in sorted(set(protected)):
        findings.append(
            Finding(
                code="protected_path_violation",
                message="Changed path matches a protected-path pattern",
                path=path,
            )
        )

    # 5. Every re-run verification command must have exited 0.
    for result in observation.verification_results:
        if result.exit_code != 0:
            findings.append(
                Finding(
                    code="verification_command_failed",
                    message=f"Command {result.argv} exited {result.exit_code}",
                )
            )

    status = Status.PASS if not findings else Status.FAIL
    verdict = report.verdict
    summary = (
        f"Agent run verified: {report.stage}"
        + (f" verdict {verdict}" if verdict is not None else "")
        if status == Status.PASS
        else f"Agent run failed verification with {len(findings)} finding(s)"
    )
    return CheckResult(
        check_name=_CHECK_NAME,
        status=status,
        summary=summary,
        findings=findings,
        evidence={
            "verdict": verdict,
            "claimed_changed_paths": claimed,
            "actual_changed_paths": actual,
            "verification_exit_codes": [r.exit_code for r in observation.verification_results],
        },
        affected_paths=sorted({finding.path for finding in findings if finding.path}),
        remediation_hint=(
            "Re-run the agent within scope, or correct its report to match reality."
            if findings
            else None
        ),
    )
