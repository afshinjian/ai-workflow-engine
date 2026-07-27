"""Per-target-repository configuration schema (CONFIGURATION_MODEL.md §3-4)."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# A Windows drive prefix (`C:\...` or `C:/...`). Matched before segment analysis because `C:` would
# otherwise read as an ordinary first segment and the pattern would look canonical.
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _noncanonical_pattern_reason(pattern: str) -> str | None:
    """Why `pattern` is not already a canonical repository-relative POSIX glob, or `None`.

    Judges only structural separators and path segments, never glob metacharacters: `*`, `?`,
    `[...]`, and `**` pass through untouched, so valid glob semantics are fully preserved. A
    leading-dot *filename* such as `.github` is a perfectly canonical segment — only the special
    segments `.` and `..` are refused.
    """
    if not pattern:
        return "empty pattern"
    if not pattern.strip():
        return "whitespace-only pattern"
    if "\\" in pattern:
        # Covers Windows-style separators and UNC forms (`\\server\share\**`) alike. Rejecting
        # rather than translating: a backslash is a legal character in a POSIX filename, so
        # rewriting it to `/` would silently reinterpret a legitimate path.
        return "backslash separator (use POSIX '/' separators)"
    if _WINDOWS_DRIVE_RE.match(pattern):
        return "Windows drive-letter prefix"
    if pattern.startswith("/"):
        return "absolute path (leading '/')"
    segments = pattern.split("/")
    if any(segment == "" for segment in segments):
        return "empty path segment (repeated '//' or a trailing '/')"
    if any(segment == "." for segment in segments):
        return "'.' current-directory segment"
    if any(segment == ".." for segment in segments):
        return "'..' parent-traversal segment"
    return None


def canonical_repository_relative_path(path: str) -> str:
    """Reduce an observed Git path to the same canonical representation patterns are held to.

    Git already emits repository-relative POSIX paths, so this is an identity function for every
    path Git actually produces; it exists so that matching is provably performed on one
    representation on *both* sides (AUTO002-IR-03), rather than assuming the observation side is
    canonical. Backslashes are deliberately left alone — they are legal POSIX filename characters.
    """
    segments = [segment for segment in path.split("/") if segment not in ("", ".")]
    canonical: list[str] = []
    for segment in segments:
        if segment == ".." and canonical and canonical[-1] != "..":
            canonical.pop()
        else:
            canonical.append(segment)
    return "/".join(canonical)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowConfig(StrictModel):
    repository_path: Path
    repository_identity: str = Field(min_length=1)
    remote_name: str = Field(min_length=1)
    baseline_branch: str = Field(min_length=1)
    stage_contract_directory: Path
    stage_branch_naming: str = Field(min_length=1)
    test_command: str = Field(min_length=1)
    lint_command: str = Field(min_length=1)
    formatting_command: str = Field(min_length=1)
    security_command: str = Field(min_length=1)
    required_github_checks: list[str]
    merge_method: Literal["squash"]
    claude_cli_executable: Path
    claude_cli_timeout_seconds: int = Field(ge=1)
    codex_cli_executable: Path
    codex_cli_timeout_seconds: int = Field(ge=1)
    allowed_environment_variables: list[str]
    allowed_changed_paths: list[str]
    forbidden_changed_paths: list[str]
    repair_attempt_limit: Literal[3]
    state_directory: Path
    audit_directory: Path

    @field_validator("repository_path")
    @classmethod
    def _repository_path_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("repository_path must be an absolute path")
        return value

    @field_validator("stage_contract_directory")
    @classmethod
    def _stage_contract_directory_relative(cls, value: Path) -> Path:
        if value.is_absolute():
            raise ValueError("stage_contract_directory must be relative to repository_path")
        return value

    @field_validator("claude_cli_executable", "codex_cli_executable")
    @classmethod
    def _cli_executable_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("CLI executable paths must be absolute")
        return value

    @field_validator("state_directory", "audit_directory")
    @classmethod
    def _local_root_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("state_directory and audit_directory must be absolute paths")
        return value

    @field_validator("allowed_environment_variables")
    @classmethod
    def _no_environment_wildcard(cls, value: list[str]) -> list[str]:
        if any("*" in entry for entry in value):
            raise ValueError(
                "allowed_environment_variables must never include a wildcard that would "
                "forward the entire environment"
            )
        return value

    @field_validator("allowed_changed_paths", "forbidden_changed_paths")
    @classmethod
    def _changed_path_patterns_repository_relative(cls, value: list[str]) -> list[str]:
        """`CONFIGURATION_MODEL.md` §4: "no path may resolve outside the intended boundary."
        These are glob patterns matched (`fnmatch.fnmatchcase`) against repository-relative
        changed-file paths (never against an absolute filesystem path) — an absolute pattern or
        one containing a `..` segment can therefore never match any real changed path at all. A
        bare `list[str]` previously accepted such a pattern silently: for `forbidden_changed_paths`
        specifically, an inert pattern doesn't merely do nothing, it gives the false appearance of
        a protection that was never actually in effect, since the *intended* forbidden path would
        then fall through unmatched into `allowed`/`unexpected` instead.

        AUTO002-IR-03 widened this from "absolute or `..`" to *every* noncanonical spelling. An
        independent review reproduced `docs/./secret/**` and `docs//secret/**` being accepted and
        passed raw into matching: Git reports the changed file as the canonical `docs/secret/x`,
        which those patterns do not match, so the forbidden rule stayed inert and a broader
        `allowed` rule won — a configuration that reads as forbidding a path while actually
        allowing it. The chosen design is *strict rejection*, not normalization (`DD-23`): a
        pattern is accepted only if it is already in the one canonical repository-relative POSIX
        representation that observed Git paths are also reduced to, so there is exactly one
        spelling per intent and no rewriting step that could reinterpret a glob token (`*`, `?`,
        `[...]`, `**` are never touched, only structural separators and segments are judged).
        """
        for pattern in value:
            reason = _noncanonical_pattern_reason(pattern)
            if reason is not None:
                raise ValueError(
                    "changed-path patterns must be nonblank, repository-relative POSIX glob "
                    f"patterns already in canonical form ({reason}): {pattern!r}"
                )
        return value

    @model_validator(mode="after")
    def _stage_contract_directory_confined(self) -> "WorkflowConfig":
        root = self.repository_path.resolve()
        resolved = (root / self.stage_contract_directory).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("stage_contract_directory must resolve inside repository_path")
        return self
