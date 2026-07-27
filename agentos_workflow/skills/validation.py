"""Validation Skills (`SKILL_CONTRACTS.md` §4).

These Skills form the deterministic validation gate (`MACHINE_GATES.md` §3). They are read-only
with respect to repository state: they run configured commands and judge artifacts, and none of
them writes to the repository.

Every configured command is split with `shlex.split` and executed as a real argument vector.
There is no `shell=True` path anywhere in this package, so shell metacharacters in a configured
command are inert data rather than executable syntax — a configuration value cannot become a
second command. The cost is that shell features (pipes, `&&`, redirection) are unavailable in a
configured command; a target repository needing those must put them in a script and configure
the script, which is the safer arrangement anyway because the script is then reviewable.

Every invocation returns the command-execution audit record of `AUDIT_MODEL.md` §2 with stdout
and stderr already redacted (`SECURITY_MODEL.md` §1), so a caller cannot accidentally log a raw
credential that leaked into command output.
"""

from __future__ import annotations

import json
import re
import shlex
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos_workflow.skills import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    CommandExecution,
    CommandOutcome,
    FailureKind,
    RetryClassification,
    SkillResult,
    failure,
    redact_secrets,
    run_fixed_argv,
    success,
)
from agentos_workflow.skills.contract import ScopeVerdict, validate_allowed_paths

__all__ = [
    "CommandValidation",
    "ReportValidation",
    "SecretFinding",
    "SecretScan",
    "run_formatting_checks",
    "run_lint",
    "run_scope_validation",
    "run_secret_detection",
    "run_security_checks",
    "run_tests",
    "validate_completion_report",
    "validate_qa_report",
]

_MAX_REPORT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class CommandValidation:
    """The outcome of one configured validation command."""

    check: str
    passed: bool
    execution: CommandExecution

    @property
    def exit_code(self) -> int | None:
        return self.execution.exit_code


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line_number: int
    kind: str
    redacted_line: str


@dataclass(frozen=True)
class SecretScan:
    passed: bool
    findings: tuple[SecretFinding, ...]


@dataclass(frozen=True)
class ReportValidation:
    passed: bool
    schema_errors: tuple[str, ...]
    report: dict[str, Any] | None = None


# --------------------------------------------------------------------------------------------
# Configured-command Skills
# --------------------------------------------------------------------------------------------


def _run_configured_command(
    *,
    skill: str,
    check: str,
    command: str,
    repository_path: Path,
    timeout_seconds: int,
    allowed_environment_variables: tuple[str, ...],
) -> SkillResult[CommandValidation]:
    """Split, validate, and run one configured command inside the target repository."""
    if not command.strip():
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"configured {check} command is blank",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    try:
        argv = tuple(shlex.split(command))
    except ValueError as exc:
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"configured {check} command is not a parseable argument vector: {exc}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if not argv:
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"configured {check} command splits to an empty argument vector",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    if not repository_path.is_dir():
        return failure(
            skill, FailureKind.NOT_FOUND, f"{repository_path} does not exist or is not a directory"
        )
    execution = run_fixed_argv(
        argv,
        # The identity is the skill plus the *shape* of the command, never raw argv: argv can
        # carry a credential, and this record is written to the audit log (`AUDIT_MODEL.md` §2).
        identity=f"{skill}:{argv[0]}({len(argv) - 1} args)",
        cwd=str(repository_path),
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )
    if execution.outcome is CommandOutcome.SPAWN_FAILED:
        return failure(
            skill,
            FailureKind.SPAWN_FAILED,
            f"could not execute configured {check} command: {execution.stderr or 'no diagnostic'}",
            retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
        )
    # A timeout and a non-zero exit are both *results*, not Skill failures: the gate's job is to
    # report that the check did not pass, and the Orchestrator routes that to repair. Only an
    # inability to run the check at all is a Skill failure.
    return success(CommandValidation(check=check, passed=execution.succeeded, execution=execution))


def run_tests(
    repository_path: Path,
    *,
    test_command: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[CommandValidation]:
    """Run the target repository's configured test command."""
    return _run_configured_command(
        skill="run_tests",
        check="tests",
        command=test_command,
        repository_path=repository_path,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


def run_lint(
    repository_path: Path,
    *,
    lint_command: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[CommandValidation]:
    """Run the target repository's configured lint command."""
    return _run_configured_command(
        skill="run_lint",
        check="lint",
        command=lint_command,
        repository_path=repository_path,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


def run_formatting_checks(
    repository_path: Path,
    *,
    formatting_command: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[CommandValidation]:
    """Run the target repository's configured formatting check."""
    return _run_configured_command(
        skill="run_formatting_checks",
        check="formatting",
        command=formatting_command,
        repository_path=repository_path,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


def run_security_checks(
    repository_path: Path,
    *,
    security_command: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> SkillResult[CommandValidation]:
    """Run the target repository's configured security command."""
    return _run_configured_command(
        skill="run_security_checks",
        check="security",
        command=security_command,
        repository_path=repository_path,
        timeout_seconds=timeout_seconds,
        allowed_environment_variables=allowed_environment_variables,
    )


# --------------------------------------------------------------------------------------------
# Scope and secret Skills
# --------------------------------------------------------------------------------------------


def run_scope_validation(
    *,
    changed_files: tuple[str, ...],
    allowed_paths: tuple[str, ...],
    forbidden_paths: tuple[str, ...],
) -> SkillResult[ScopeVerdict]:
    """Run scope enforcement as part of the deterministic validation gate.

    Thin by design: `SECURITY_MODEL.md` §7 names `validate_allowed_paths` as the authority, and
    duplicating its logic here would create two rule engines that could disagree. This Skill
    exists as its own name because the gate and the Agent contracts refer to it by that name.
    """
    return validate_allowed_paths(
        changed_files=changed_files,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
    )


# Line-oriented detection patterns. These intentionally overlap the redaction patterns in
# `skills/__init__.py` but serve the opposite purpose: redaction *hides* a secret that already
# reached output, whereas detection *fails the gate* because a secret reached the diff. A secret
# committed to the repository is a finding even though it would also be redacted downstream.
_DETECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{16,255}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,255}")),
    ("aws-access-key-id", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,255}")),
    ("stripe-key", re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{10,255}")),
    ("google-api-key", re.compile(r"AIza[A-Za-z0-9_-]{35}")),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{4,4096}\.eyJ[A-Za-z0-9_-]{4,4096}\.[A-Za-z0-9_-]{4,4096}"),
    ),
    ("url-credentials", re.compile(r"://[^\s/@:]{1,256}:[^\s/@]{1,256}@")),
    (
        "labelled-secret",
        re.compile(
            r"(?i:pass(?:wd|word)|secret|token|api[_-]?key|access[_-]?key|credential)s?"
            r"\s*[=:]\s*(?:\"[^\"\r\n]{8,4096}\"|'[^'\r\n]{8,4096}'|[^\s,;)\]}\r\n]{8,4096})"
        ),
    ),
)

# A placeholder is the overwhelmingly common false positive: every example config and test
# fixture in a real repository contains `password = "changeme"`. Treating those as findings
# would make the gate noise that operators learn to override, which is worse than a narrower
# gate that operators trust.
_PLACEHOLDER_RE = re.compile(
    r"(?i)\b(?:changeme|example|placeholder|redacted|dummy|sample|your[_-]?\w+|xxx+|todo"
    r"|fake|test|notasecret|<[^>]{1,64}>|\$\{[^}]{1,64}\}|\*{3,})\b"
)


def run_secret_detection(
    *,
    changed_files: tuple[str, ...],
    repository_path: Path,
    max_file_bytes: int = 2 * 1024 * 1024,
) -> SkillResult[SecretScan]:
    """Scan the changed files for committed secrets, reporting findings already redacted.

    Findings never carry the matched value: the whole point of the check is that the secret must
    not be copied anywhere else, and a finding is written to an audit record. The line is
    redacted before it enters a `SecretFinding`, so the report says *what kind* of credential
    appeared on which line without reproducing it.

    Binary files and files above `max_file_bytes` are skipped rather than scanned: a
    line-oriented regex over a large binary produces meaningless findings, and a deleted file is
    simply absent. Skipping is safe here because this is one layer of defense-in-depth, not the
    only control (`SECURITY_MODEL.md` §1).
    """
    skill = "run_secret_detection"
    if not repository_path.is_dir():
        return failure(
            skill, FailureKind.NOT_FOUND, f"{repository_path} does not exist or is not a directory"
        )
    root = repository_path.resolve()
    findings: list[SecretFinding] = []
    for raw_path in changed_files:
        normalized = unicodedata.normalize("NFC", raw_path)
        if "\x00" in normalized or normalized.startswith("/") or ".." in normalized.split("/"):
            return failure(
                skill,
                FailureKind.UNSAFE_INPUT,
                f"changed path {raw_path!r} is not a safe repository-relative path",
                retry_classification=RetryClassification.NON_RETRYABLE,
            )
        candidate = root / normalized
        try:
            resolved = candidate.resolve()
            # A changed path that resolves outside the repository is a symlink escape, not a
            # file to scan; refusing beats silently reading an arbitrary host file.
            if not resolved.is_relative_to(root):
                return failure(
                    skill,
                    FailureKind.UNSAFE_INPUT,
                    f"changed path {raw_path!r} resolves outside the repository",
                    retry_classification=RetryClassification.NON_RETRYABLE,
                )
            if candidate.is_symlink() or not resolved.is_file():
                continue
            if resolved.stat().st_size > max_file_bytes:
                continue
            raw = resolved.read_bytes()
        except OSError:
            # A path listed as changed but unreadable (deleted in a later commit, permission
            # denied) is skipped, not fatal: the diff is a historical record, not a guarantee
            # that every path still exists.
            continue
        if b"\x00" in raw[:8192]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if len(line) > 4096:
                line = line[:4096]
            if _PLACEHOLDER_RE.search(line):
                continue
            for kind, pattern in _DETECTION_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        SecretFinding(
                            path=normalized,
                            line_number=line_number,
                            kind=kind,
                            redacted_line=redact_secrets(line.strip()),
                        )
                    )
                    break
    return success(SecretScan(passed=not findings, findings=tuple(findings)))


# --------------------------------------------------------------------------------------------
# Report-artifact Skills
# --------------------------------------------------------------------------------------------


class _DuplicateJSONKeyError(Exception):
    """Internal signal from the duplicate-key hook, carrying only the offending key."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"duplicate JSON object key {key!r}")


def _loads_rejecting_duplicate_keys(text: str) -> object:
    """`json.loads`, but a repeated key in any object at any nesting level is an error.

    Same rule AUTO-002 applies to persisted state (DD-25/DD-30), for the same reason: standard
    JSON silently applies last-key-wins, so a report carrying two `verdict` keys would be judged
    as whichever the parser happened to keep. A report with no single correct reading must fail
    closed rather than have one chosen for it. Re-implemented rather than imported so this
    module takes on no dependency on the state store's internals.
    """

    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJSONKeyError(key)
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


def _load_report(skill: str, report_path: Path) -> SkillResult[dict[str, Any]]:
    try:
        if report_path.is_symlink():
            return failure(
                skill,
                FailureKind.UNSAFE_INPUT,
                f"{report_path} is a symlink; report artifacts must be regular files",
                retry_classification=RetryClassification.NON_RETRYABLE,
            )
        if not report_path.is_file():
            return failure(skill, FailureKind.NOT_FOUND, f"{report_path} is not a regular file")
        if report_path.stat().st_size > _MAX_REPORT_BYTES:
            return failure(
                skill, FailureKind.UNSAFE_INPUT, f"{report_path} exceeds the report size ceiling"
            )
        text = report_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return failure(skill, FailureKind.MALFORMED_OUTPUT, f"report is not valid UTF-8: {exc}")
    except OSError as exc:
        return failure(skill, FailureKind.IO_ERROR, f"could not read {report_path}: {exc}")
    try:
        payload = _loads_rejecting_duplicate_keys(text)
    except _DuplicateJSONKeyError as exc:
        return failure(
            skill, FailureKind.MALFORMED_OUTPUT, f"report has a duplicate JSON key {exc.key!r}"
        )
    except json.JSONDecodeError as exc:
        return failure(skill, FailureKind.MALFORMED_OUTPUT, f"report is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        return failure(
            skill, FailureKind.MALFORMED_OUTPUT, "report must be a JSON object at the top level"
        )
    return success(payload)


def _check_schema(
    payload: dict[str, Any],
    *,
    required_strings: tuple[str, ...],
    required_lists: tuple[str, ...],
    enums: dict[str, frozenset[str]],
) -> tuple[str, ...]:
    """Collect *every* schema error rather than stopping at the first.

    A report author fixing one field at a time across repeated gate runs is a slow, expensive
    loop when the Agent producing the report is a model session; reporting the full error set
    lets one repair pass fix everything.
    """
    errors: list[str] = []
    for field_name in required_strings:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field_name!r} must be a non-empty string")
    for field_name in required_lists:
        value = payload.get(field_name)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{field_name!r} must be a list of strings")
    for field_name, permitted in enums.items():
        value = payload.get(field_name)
        if not isinstance(value, str) or value not in permitted:
            errors.append(f"{field_name!r} must be one of {sorted(permitted)}")
    return tuple(errors)


def validate_completion_report(report_path: Path) -> SkillResult[ReportValidation]:
    """Validate an implementation completion report artifact against its schema.

    A schema-invalid report is a *result* (`passed=False` with the error list), not a Skill
    failure: the Orchestrator routes it to repair exactly as it would a failing test. Only an
    unreadable or unparseable artifact is a Skill failure, because then there is no report to
    judge at all.
    """
    skill = "validate_completion_report"
    loaded = _load_report(skill, report_path)
    if not loaded.ok or loaded.value is None:
        return SkillResult(ok=False, error=loaded.error)
    payload = loaded.value
    errors = _check_schema(
        payload,
        required_strings=("stage_id", "branch", "head_sha", "summary", "commit_message"),
        required_lists=("created_files", "modified_files", "deleted_files", "tests_added"),
        enums={"final_status": frozenset({"COMPLETE", "BLOCKED", "RETURNED"})},
    )
    return success(
        ReportValidation(
            passed=not errors,
            schema_errors=errors,
            report=payload if not errors else None,
        )
    )


def validate_qa_report(report_path: Path) -> SkillResult[ReportValidation]:
    """Validate an independent QA report artifact against its schema.

    The `verdict` enum is exactly two tokens, matching `docs/AGENT_PROTOCOL.md`'s rule that a
    verdict is one token with no partial or hedged form. A QA report that fails schema
    validation is never read as a pass: the caller sees `passed=False` and `report=None`, so
    there is no partially-validated payload to mistake for a verdict.
    """
    skill = "validate_qa_report"
    loaded = _load_report(skill, report_path)
    if not loaded.ok or loaded.value is None:
        return SkillResult(ok=False, error=loaded.error)
    payload = loaded.value
    errors = list(
        _check_schema(
            payload,
            required_strings=("stage_id", "branch", "head_sha", "summary"),
            required_lists=("findings",),
            enums={"verdict": frozenset({"APPROVED", "REJECTED"})},
        )
    )
    # A `REJECTED` verdict with no findings is self-contradictory: the repair loop would have
    # nothing to act on, and the stage would fail with no stated reason.
    if payload.get("verdict") == "REJECTED":
        findings = payload.get("findings")
        if isinstance(findings, list) and not findings:
            errors.append("'findings' must be non-empty when 'verdict' is 'REJECTED'")
    return success(
        ReportValidation(
            passed=not errors,
            schema_errors=tuple(errors),
            report=payload if not errors else None,
        )
    )
