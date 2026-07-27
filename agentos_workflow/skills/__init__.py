"""Deterministic Skills (`SKILL_CONTRACTS.md`) and the primitives every Skill family shares.

A Skill is deterministic: given the same repository state and inputs it produces the same result.
No Skill invokes a Model Provider (`SKILL_CONTRACTS.md` §1), and no Skill raises an unhandled
exception to the Orchestrator — every failure is returned as a typed `SkillFailure` carrying
enough evidence for the Orchestrator to choose the next workflow-state transition
(`SKILL_CONTRACTS.md` §7).

This module deliberately holds the shared primitives rather than a re-export surface: the four
family modules (`repository`, `contract`, `validation`, `reporting`) import *from* it and are
never imported *by* it, so the package has no import cycle and each family module can be imported
in isolation.

Subprocess discipline follows the boundary AUTO-002 already established in
`agentos_workflow/observation/` (DD-14): fixed argv assembled from validated components, never a
caller-supplied command string interpolated into a shell, `LC_ALL=C`/`LANG=C` for parseable
output, a bounded timeout, and an environment built from an explicit allowlist rather than
inherited wholesale (`SECURITY_MODEL.md` §1).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, TypeVar

__all__ = [
    "DEFAULT_COMMAND_TIMEOUT_SECONDS",
    "CommandExecution",
    "CommandOutcome",
    "FailureKind",
    "MergeConfirmation",
    "RetryClassification",
    "SkillFailure",
    "SkillResult",
    "failure",
    "redact_secrets",
    "run_fixed_argv",
    "success",
    "utc_now",
]

T = TypeVar("T")

DEFAULT_COMMAND_TIMEOUT_SECONDS = 300
GIT_TIMEOUT_SECONDS = 30


def utc_now() -> datetime:
    """The single timestamp source, so records are comparable and always timezone-aware."""
    return datetime.now(UTC)


class FailureKind(StrEnum):
    """Why a Skill failed, at a granularity the Orchestrator can branch on."""

    UNSAFE_INPUT = "unsafe_input"
    PRECONDITION = "precondition"
    NOT_FOUND = "not_found"
    SPAWN_FAILED = "spawn_failed"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    MALFORMED_OUTPUT = "malformed_output"
    IO_ERROR = "io_error"
    PERMANENT = "permanent"


class RetryClassification(StrEnum):
    """`SKILL_CONTRACTS.md` §5: the determining question is never *which* error occurred, but
    *when* — could the underlying subprocess already have reached the remote before the failure
    was observed?

    `NOT_APPLICABLE` is the honest answer for a purely local read-only Skill, where no remote
    side effect is reachable by construction. It is never used to downgrade a real ambiguity.
    """

    PROVEN_PRE_SIDE_EFFECT = "proven_pre_side_effect"
    POSSIBLE_SIDE_EFFECT = "possible_side_effect"
    NON_RETRYABLE = "non_retryable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SkillFailure:
    """A typed failure. Never an exception crossing the Orchestrator boundary."""

    skill: str
    kind: FailureKind
    detail: str
    retry_classification: RetryClassification = RetryClassification.NOT_APPLICABLE

    def __str__(self) -> str:
        return f"{self.skill}: {self.kind.value}: {self.detail}"


@dataclass(frozen=True)
class SkillResult(Generic[T]):
    """A Skill's outcome: exactly one of `value` (on success) or `failure` is meaningful."""

    ok: bool
    value: T | None = None
    error: SkillFailure | None = None

    def unwrap(self) -> T:
        """Return the value, or raise. For *test and caller convenience only* — the Orchestrator
        branches on `ok` and never calls this."""
        if not self.ok or self.value is None:
            raise AssertionError(f"unwrap() on a failed result: {self.error}")
        return self.value


def success(value: T) -> SkillResult[T]:
    return SkillResult(ok=True, value=value)


def failure(
    skill: str,
    kind: FailureKind,
    detail: str,
    *,
    retry_classification: RetryClassification = RetryClassification.NOT_APPLICABLE,
) -> SkillResult[T]:
    """Build a failed result. `detail` is redacted before it is ever stored or surfaced."""
    return SkillResult(
        ok=False,
        error=SkillFailure(
            skill=skill,
            kind=kind,
            detail=redact_secrets(detail),
            retry_classification=retry_classification,
        ),
    )


@dataclass(frozen=True)
class MergeConfirmation:
    """Proof that a stage branch's pull request was independently confirmed merged.

    `SECURITY_MODEL.md` §5 requires `delete_local_branch`/`delete_remote_branch` to run *only*
    after `verify_merge_completion` has independently confirmed the merge. That verification is a
    GitHub-facing Skill delivered by AUTO-006, so AUTO-003 defines the token it must produce and
    makes the deletion Skills structurally unable to run without one: the precondition cannot be
    satisfied by a bare boolean a caller could pass by accident, and there is no default value.
    """

    branch: str
    merge_commit_sha: str
    verified_at: datetime


# --------------------------------------------------------------------------------------------
# Secret redaction (OD-2)
# --------------------------------------------------------------------------------------------

# `SECURITY_MODEL.md` §1 names two controls; OD-2 asked which to build and recommended both.
# AUTO-003 implements both (DD-33): the environment allowlist below is the *primary* control
# (a secret never forwarded cannot leak), and these patterns are defense-in-depth for secrets
# that reach command output by another route — a token baked into a target repository's own
# config, a CI variable echoed by a test, a remote URL carrying userinfo.
#
# Every pattern is written to match in linear time: no nested quantifier over an overlapping
# character class, and every unbounded run is over a class that excludes its own delimiter. This
# matters because redaction runs over untrusted subprocess output, where a catastrophically
# backtracking pattern would be a denial-of-service vector reachable by a target repository.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Private key blocks: redact the whole body, not just the header.
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----.*?-----END [A-Z ]{0,40}PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    # GitHub tokens, including fine-grained PATs.
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{16,255}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,255}")),
    # AWS access key IDs, and secret keys when explicitly labelled.
    ("aws-access-key-id", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    # Slack, Stripe, and Google API key shapes.
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,255}")),
    ("stripe-key", re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{10,255}")),
    ("google-api-key", re.compile(r"AIza[A-Za-z0-9_-]{35}")),
    # JSON Web Tokens.
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{4,4096}\.eyJ[A-Za-z0-9_-]{4,4096}\.[A-Za-z0-9_-]{4,4096}"),
    ),
    # Credentials embedded in a URL's userinfo component (`https://user:token@host/...`).
    ("url-credentials", re.compile(r"(?<=://)[^\s/@:]{1,256}:[^\s/@]{1,256}(?=@)")),
    # `Authorization: Bearer <token>` and friends.
    (
        "authorization-header",
        re.compile(r"(?i:authorization)\s*:\s*(?!\[REDACTED:)[^\r\n]{1,4096}"),
    ),
    ("bearer-token", re.compile(r"(?i:bearer)\s+(?!\[REDACTED:)[A-Za-z0-9._~+/=-]{8,4096}")),
    # Labelled assignments: `password=...`, `api_key: ...`, `SECRET_TOKEN = "..."`.
    (
        "labelled-secret",
        re.compile(
            r"(?i:pass(?:wd|word)?|secret|token|api[_-]?key|access[_-]?key|private[_-]?key"
            r"|credential)s?\s*[=:]\s*(?!\[REDACTED:)(?:\"[^\"\r\n]{1,4096}\"|'[^'\r\n]{1,4096}'"
            r"|[^\s,;)\]}\r\n]{1,4096})"
        ),
    ),
)

_REDACTED = "[REDACTED:{kind}]"


def redact_secrets(text: str) -> str:
    """Replace known secret shapes with an opaque, kind-labelled marker.

    Redaction is applied to *every* string that leaves a Skill: failure details, audit records,
    and the sanitized stdout/stderr files referenced by `AUDIT_MODEL.md` §2. It is deliberately
    lossy and never reversible — the marker names the pattern that matched so an operator can
    tell *what kind* of credential was present without the value being recoverable.

    This is defense-in-depth, not a guarantee: a secret with no recognizable shape (a bare
    high-entropy string with no label) is not detectable by pattern alone, which is exactly why
    `SECURITY_MODEL.md` §1 makes the environment allowlist the primary control. Entropy-based
    detection was considered and rejected — it would flag Git SHAs, content hashes, and base64
    test fixtures, all of which this engine's own output is full of, and a redactor that fires
    on ordinary output trains operators to ignore it.
    """
    if not text:
        return text
    redacted = text
    for kind, pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED.format(kind=kind), redacted)
    return redacted


# --------------------------------------------------------------------------------------------
# Subprocess primitive
# --------------------------------------------------------------------------------------------


class CommandOutcome(StrEnum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    SPAWN_FAILED = "spawn_failed"


@dataclass(frozen=True)
class CommandExecution:
    """The command-execution audit record of `AUDIT_MODEL.md` §2.

    `normalized_command_identity` is the skill name plus an argument *shape*, never raw argv:
    argv can carry a credential (a remote URL with userinfo, a `--token` flag), and this record
    is written to the audit log. `stdout`/`stderr` are held redacted in memory so a caller can
    make a pass/fail decision, and are written to disk only through
    `reporting.write_sanitized_output`, which is the only path that produces the `stdout_ref`/
    `stderr_ref` file references the schema names.
    """

    normalized_command_identity: str
    start_time: datetime
    completion_time: datetime
    exit_code: int | None
    timeout_status: bool
    outcome: CommandOutcome
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.outcome is CommandOutcome.COMPLETED and self.exit_code == 0


def _build_environment(allowed_environment_variables: tuple[str, ...]) -> dict[str, str]:
    """Build a subprocess environment from an explicit allowlist (`SECURITY_MODEL.md` §1).

    `PATH` is always present because a fixed-argv command still has to be found; every other
    inherited variable must be named. `LC_ALL`/`LANG` are pinned to `C` so output is parseable
    and identical across operator locales, which is what makes a Skill deterministic.
    """
    environment = {
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_OPTIONAL_LOCKS": "0",
        # Refuse every interactive credential path: a Skill that blocks on a passphrase prompt
        # would hang until its timeout, and one that silently picks up a helper's credential
        # would defeat the allowlist above.
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "PATH": os.environ.get("PATH", ""),
    }
    for name in allowed_environment_variables:
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    return environment


def run_fixed_argv(
    argv: tuple[str, ...],
    *,
    identity: str,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    allowed_environment_variables: tuple[str, ...] = (),
) -> CommandExecution:
    """Run one fixed-argv command and return its audit record.

    `argv` is a real argument vector, never a shell string: no `shell=True` path exists in this
    package, so shell metacharacters in a configured command or a branch name are inert data.
    The process never inherits a stdin — a command that tries to read one gets EOF immediately
    rather than blocking until the timeout.

    This function does not raise for a non-zero exit or a timeout; both are ordinary outcomes
    recorded in the returned `CommandExecution`. It raises nothing at all: even a spawn failure
    becomes a record, so the Orchestrator's audit trail has no gaps.
    """
    start_time = utc_now()
    try:
        process = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=cwd,
            env=_build_environment(allowed_environment_variables),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandExecution(
            normalized_command_identity=identity,
            start_time=start_time,
            completion_time=utc_now(),
            exit_code=None,
            timeout_status=True,
            outcome=CommandOutcome.TIMED_OUT,
            stdout=redact_secrets(_decode(exc.stdout)),
            stderr=redact_secrets(_decode(exc.stderr)),
        )
    except OSError as exc:
        # The executable could not be spawned at all — the one case `SKILL_CONTRACTS.md` §5
        # accepts as *proven* pre-side-effect, because the command was never invoked.
        return CommandExecution(
            normalized_command_identity=identity,
            start_time=start_time,
            completion_time=utc_now(),
            exit_code=None,
            timeout_status=False,
            outcome=CommandOutcome.SPAWN_FAILED,
            stdout="",
            stderr=redact_secrets(str(exc)),
        )
    return CommandExecution(
        normalized_command_identity=identity,
        start_time=start_time,
        completion_time=utc_now(),
        exit_code=process.returncode,
        timeout_status=False,
        outcome=CommandOutcome.COMPLETED,
        stdout=redact_secrets(_decode(process.stdout)),
        stderr=redact_secrets(_decode(process.stderr)),
    )


def _decode(raw: bytes | str | None) -> str:
    """Decode subprocess output without ever failing on invalid UTF-8.

    Target-repository output is not required to be valid UTF-8 (a test can emit arbitrary
    bytes), and a `UnicodeDecodeError` escaping here would violate the never-raise contract.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")
