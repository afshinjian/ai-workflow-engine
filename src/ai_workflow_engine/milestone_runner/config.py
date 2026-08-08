"""Validated runner configuration for the AUTO-016 milestone runner.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 21
(configuration model), section 4 entry condition 8 (a missing or invalid configuration is a
precondition failure), section 17 (closed capability enums, required per-provider timeouts, the
non-wildcard environment allowlist), section 19 (the budget ceilings) and section 22 invariants 1,
12 and 17.

This module reads exactly one file -- the configuration named by `--config` -- and validates it.
It resolves nothing against the repository, opens no plan, spawns no process and derives no
default from the environment. Section 4 item 8 is binding: a missing or invalid configuration is
`INVALID_CONFIGURATION`, never an assumed default, so every field below is either present in the
file or has a default the contract states in so many words (the two `git` flags of section 20,
which default to `false`, and the two capability modes, which default to their least-capable
member).

Three properties are structural rather than checked
---------------------------------------------------
* **Capability modes are unrepresentable, not rejected** (invariant 17). :class:`
  ClaudePermissionMode` and :class:`CodexSandboxMode` are closed enums with no
  `bypassPermissions` and no `danger-full-access` member, so no configuration, request or call
  site can express either -- the discipline `agentos_workflow/config/policy.py` already
  establishes and `CONFIGURATION_MODEL.md` section 4 requires.
* **The environment allowlist admits no wildcard.** `allowed_environment_variables` entries must
  match a POSIX environment-variable name grammar, which contains no metacharacter at all, so
  `*`, `PATH*` and `**` are refused by the grammar rather than by a special case that a later
  edit could forget.
* **Budget ceilings are explicitness, not tuning** (section 21). Each review-policy field is
  bounded above by the section 19 default it restates, so the configuration surface can lower a
  budget and can never raise one.

`plan_directory` is deliberately the only plan-related key, and it names a location rather than a
search: DEC-016-005 forbids plan discovery, and section 21 states that no configuration key
enables it and none exists to add. Resolution of that location -- and the refusal of a
repository-local plan the governing contract does not list verbatim -- belongs to `plan.py`,
which is where the repository root is known.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Final

import yaml
from pydantic import Field, ValidationError, ValidationInfo, field_validator, model_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.models import (
    BLOCKING_SEVERITIES,
    DEFERRED_SEVERITIES,
    MAX_ARGUMENT_CHARS,
    MAX_IDENTIFIER_CHARS,
    MAX_ROOT_PATH_CHARS,
    FindingSeverity,
    MilestoneRunnerModel,
    StopReason,
    normalize_repository_path,
)

#: Section 21: the configuration document is versioned exactly as the plan and the state record
#: are, and an unknown version is a hard refusal rather than a best-effort read.
CONFIG_SCHEMA_VERSION: Final = 1

#: The largest configuration document this loader will read. A configuration is a small
#: hand-authored file; anything larger is a mistake or an attempt to exhaust memory, and either
#: way it is refused before it is parsed.
MAX_CONFIG_BYTES: Final = 1 << 20

_STAGE_ID_RE = re.compile(r"AUTO-[0-9]{3}")
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_CONDA_ENVIRONMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_EXECUTABLE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: DEC-010's canonical repository identity: a normalized repository name, the `--` separator, and
#: the first twelve hexadecimal characters of the digest over the canonical remote identity. The
#: derivation itself lives in `git_inspect.py`, which is the module that can observe a remote;
#: this grammar is what the configuration must restate so the two can be compared.
_REPOSITORY_IDENTITY_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*--[0-9a-f]{12}")

#: POSIX environment-variable names. No metacharacter is admissible, which is what makes
#: "no wildcard is permitted" (section 17, `CONFIGURATION_MODEL.md` section 4) a property of the
#: grammar rather than a rule someone has to remember to apply.
_ENVIRONMENT_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Section 19's default policy, restated here as the ceiling each configured value is bounded by.
#: Section 21 is explicit that these exist "for explicitness and auditability, not as knobs to
#: raise a limit", so the configuration surface can only lower them.
MAX_FULL_REVIEWS_CEILING: Final = 1
MAX_CORRECTION_ROUNDS_CEILING: Final = 1
MAX_CLOSURE_REVIEWS_CEILING: Final = 1
MAX_BLOCKERS_CEILING: Final = 3

#: An upper bound on any configured timeout: twelve hours. The recorded real run held one
#: provider invocation open for 1,022 seconds (section 6), so the bound is generous by design;
#: its purpose is to refuse an unbounded-in-practice value, not to tune anything.
MAX_TIMEOUT_SECONDS: Final = 12 * 60 * 60


class InvalidRunnerConfiguration(WorkflowEngineError):
    """The configuration is absent, unreadable, malformed or invalid (section 4 item 8).

    One error for every way a configuration can fail, because the contract names exactly one
    code for all of them. `CONFIGURATION_MODEL.md` section 2's rule applies unchanged: this is a
    precondition failure, never a fallback to an assumed value.
    """

    stop_reason: ClassVar[StopReason] = StopReason.INVALID_CONFIGURATION


class ClaudePermissionMode(StrEnum):
    """Claude's permission mode -- a closed enum (section 17, invariant 17).

    `bypassPermissions` is absent and unrepresentable: it is not a value this enum rejects at
    load, it is a value the type system cannot express, so no configuration, request or call site
    can ask for it. The default is the least-capable member.
    """

    PLAN = "plan"
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"


class CodexSandboxMode(StrEnum):
    """Codex's sandbox mode -- a closed enum (section 17, invariant 17).

    `danger-full-access` is absent and unrepresentable, for the same reason. The review role is
    fixed read-only by section 17; that binding belongs to the adapter, and this enum is what
    makes the stronger mode unavailable to it in the first place.
    """

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"


def _as_enum(value: Any, enum_class: type[StrEnum]) -> Any:
    """Resolve a YAML scalar to a closed-enum member before strict validation sees it.

    A configuration file holds strings, and naming a closed enum's member by its value is a
    lookup rather than a coercion -- which is why this runs `mode="before"` and leaves every
    other strict rule untouched. An unknown value raises here, so `bypassPermissions` and
    `danger-full-access` fail as "not a member" rather than reaching any downstream check: they
    are unrepresentable, and this is where that becomes visible.
    """
    if isinstance(value, str):
        return enum_class(value)
    return value


def _scalar(value: str, field: str, pattern: re.Pattern[str], maximum: int) -> str:
    """Validate one bounded single-line scalar against a closed grammar."""
    if not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters, got {len(value)}")
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{field} must match the grammar {pattern.pattern!r}")
    return value


def _repository_relative(value: str, field: str) -> str:
    """Normalize one repository-relative path field (section 21's path binding rule).

    Every path field either resolves inside the repository or under an explicitly configured
    external root; nothing lands outside both. This helper enforces the first half as a grammar:
    an absolute, drive-letter, backslash-separated or traversal-shaped value is refused rather
    than resolved, reusing the single canonicalization `models.normalize_repository_path` defines
    so a configured path is byte-comparable with a path the scope guard matches.
    """
    return normalize_repository_path(value, field)


def _unique(values: list[str], field: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain a duplicate entry")
    return values


class RepositorySettings(MilestoneRunnerModel):
    """Section 21's `repository` section: root, identity, expected branch, baseline, environment.

    `identity` is the canonical repository identity of section 11 as the *configuration* states
    it. Section 4 item 2 compares it against the identity derived from the live worktree, and a
    difference is `REPOSITORY_IDENTITY_MISMATCH`; recording the expectation here is what makes
    that comparison possible at all.
    """

    root: str
    identity: str
    expected_branch: str
    baseline_sha: str
    conda_environment: str

    @field_validator("root")
    @classmethod
    def _validate_root(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("repository.root must be an absolute POSIX path")
        if len(value) > MAX_ROOT_PATH_CHARS:
            raise ValueError(f"repository.root must be at most {MAX_ROOT_PATH_CHARS} characters")
        return value

    @field_validator("identity")
    @classmethod
    def _validate_identity(cls, value: str) -> str:
        return _scalar(value, "repository.identity", _REPOSITORY_IDENTITY_RE, MAX_IDENTIFIER_CHARS)

    @field_validator("expected_branch")
    @classmethod
    def _validate_expected_branch(cls, value: str) -> str:
        return _scalar(value, "repository.expected_branch", _BRANCH_RE, MAX_IDENTIFIER_CHARS)

    @field_validator("baseline_sha")
    @classmethod
    def _validate_baseline_sha(cls, value: str) -> str:
        if _GIT_OBJECT_ID_RE.fullmatch(value) is None:
            raise ValueError("repository.baseline_sha must be a lowercase Git object id")
        return value

    @field_validator("conda_environment")
    @classmethod
    def _validate_conda_environment(cls, value: str) -> str:
        return _scalar(
            value, "repository.conda_environment", _CONDA_ENVIRONMENT_RE, MAX_IDENTIFIER_CHARS
        )


class StageSettings(MilestoneRunnerModel):
    """Section 21's `stage` section: the pinned contract, and the optional plan location.

    `contract_sha256` is section 4 item 1's pin: the runner never authorizes the stage it
    implements, so the contract it was pointed at must be provably the contract that was
    authorized.

    `plan_directory` is optional. Omitted, DEC-016-005 rule 1's external default root is used and
    nothing inside the worktree is consulted. Present, it must satisfy rule 1 or rule 2, which
    `plan.py` decides because that decision needs the repository root. No sibling key enables a
    search; section 21 states that none exists to add.
    """

    stage_id: str
    contract_path: str
    contract_sha256: str
    plan_directory: str | None = None

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str) -> str:
        return _scalar(value, "stage.stage_id", _STAGE_ID_RE, MAX_IDENTIFIER_CHARS)

    @field_validator("contract_path")
    @classmethod
    def _validate_contract_path(cls, value: str) -> str:
        return _repository_relative(value, "stage.contract_path")

    @field_validator("contract_sha256")
    @classmethod
    def _validate_contract_sha256(cls, value: str) -> str:
        if _SHA256_HEX_RE.fullmatch(value) is None:
            raise ValueError("stage.contract_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("plan_directory")
    @classmethod
    def _validate_plan_directory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("/"):
            if len(value) > MAX_ROOT_PATH_CHARS:
                raise ValueError(
                    f"stage.plan_directory must be at most {MAX_ROOT_PATH_CHARS} characters"
                )
            return value
        return _repository_relative(value, "stage.plan_directory")


class AllowlistSettings(MilestoneRunnerModel):
    """Section 15's three path sets: the cumulative allowlist, the forbidden set, the coverage.

    `allowed_paths` and `forbidden_paths` are match patterns evaluated by `scope.path_matches`,
    where `*` never crosses `/`. `required_coverage` is not a pattern set: section 4 item 6
    reconciles it against the union of every milestone's `allowed_files` **exactly**, so its
    entries are literal repository-relative paths and any pattern character in one is matched as
    the literal character it is.
    """

    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(default_factory=list)
    required_coverage: list[str] = Field(min_length=1)

    @field_validator("allowed_paths", "forbidden_paths", "required_coverage")
    @classmethod
    def _validate_paths(cls, value: list[str], info: ValidationInfo) -> list[str]:
        field = f"allowlist.{info.field_name}"
        normalized = [
            _repository_relative(item, f"{field}[{index}]") for index, item in enumerate(value)
        ]
        return _unique(normalized, field)


class ReviewPolicySettings(MilestoneRunnerModel):
    """Section 19's policy, each budget bounded above by the default it restates.

    A configured value may be lower than its ceiling and may never exceed it (section 21), so
    this model is where "the runner refuses to start if any value exceeds its ceiling" happens --
    at load, before anything else runs.

    The severity split must partition all four severities, and `CRITICAL` and `HIGH` must remain
    blocking: a configuration may make the policy stricter and may never demote a finding the
    contract says blocks.
    """

    max_full_reviews: int = Field(ge=1, le=MAX_FULL_REVIEWS_CEILING)
    max_correction_rounds: int = Field(ge=0, le=MAX_CORRECTION_ROUNDS_CEILING)
    max_closure_reviews: int = Field(ge=0, le=MAX_CLOSURE_REVIEWS_CEILING)
    max_blockers: int = Field(ge=1, le=MAX_BLOCKERS_CEILING)
    blocking_severities: list[FindingSeverity] = Field(min_length=1)
    defer_severities: list[FindingSeverity] = Field(default_factory=list)

    @field_validator("blocking_severities", "defer_severities", mode="before")
    @classmethod
    def _coerce_severities(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [_as_enum(item, FindingSeverity) for item in value]
        return value

    @model_validator(mode="after")
    def _validate_severity_split(self) -> "ReviewPolicySettings":
        blocking = set(self.blocking_severities)
        deferred = set(self.defer_severities)
        if len(blocking) != len(self.blocking_severities):
            raise ValueError("review_policy.blocking_severities must not repeat a severity")
        if len(deferred) != len(self.defer_severities):
            raise ValueError("review_policy.defer_severities must not repeat a severity")
        overlap = blocking & deferred
        if overlap:
            raise ValueError(
                "a severity cannot both block and be deferred: "
                f"{sorted(severity.value for severity in overlap)}"
            )
        if blocking | deferred != set(FindingSeverity):
            unclassified = set(FindingSeverity) - blocking - deferred
            raise ValueError(
                "review_policy must classify every severity as blocking or deferred; "
                f"unclassified: {sorted(severity.value for severity in unclassified)}"
            )
        if not BLOCKING_SEVERITIES <= blocking:
            raise ValueError(
                "review_policy.blocking_severities must retain "
                f"{sorted(severity.value for severity in BLOCKING_SEVERITIES)}: a configuration "
                "may make the policy stricter and may never demote a blocking severity"
            )
        if not deferred <= DEFERRED_SEVERITIES:
            raise ValueError(
                "review_policy.defer_severities may contain only "
                f"{sorted(severity.value for severity in DEFERRED_SEVERITIES)}"
            )
        return self


class GitSettings(MilestoneRunnerModel):
    """Section 20's two execution flags, both `false` by default and both insufficient alone.

    Flipping a flag does not authorize anything: section 20 requires the flag **and** an
    interactive typed confirmation **and** a bound, single-use approval, at the point of use.
    This model carries the first of the three and nothing else.
    """

    execute_commit: bool = False
    execute_push: bool = False


class ProviderSettings(MilestoneRunnerModel):
    """One provider's closed argv template and its required timeout (section 17).

    `arguments` is a fixed argument vector, never a caller-supplied command string and never a
    shell fragment; `timeout_seconds` is required with no default, because section 17 requires a
    bounded timeout "per provider, from configuration, required -- no default".
    """

    executable: str
    arguments: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(ge=1, le=MAX_TIMEOUT_SECONDS)

    @field_validator("executable")
    @classmethod
    def _validate_executable(cls, value: str) -> str:
        return _scalar(value, "executable", _EXECUTABLE_RE, MAX_IDENTIFIER_CHARS)

    @field_validator("arguments")
    @classmethod
    def _validate_arguments(cls, value: list[str]) -> list[str]:
        for index, argument in enumerate(value):
            if not argument or len(argument) > MAX_ARGUMENT_CHARS:
                raise ValueError(f"arguments[{index}] must be a bounded, non-empty argument")
        return value


class ClaudeProviderSettings(ProviderSettings):
    """Claude's adapter settings. The permission mode defaults to the least-capable member."""

    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PLAN

    @field_validator("permission_mode", mode="before")
    @classmethod
    def _coerce_permission_mode(cls, value: Any) -> Any:
        return _as_enum(value, ClaudePermissionMode)


class CodexProviderSettings(ProviderSettings):
    """Codex's adapter settings. The sandbox mode defaults to the least-capable member."""

    sandbox_mode: CodexSandboxMode = CodexSandboxMode.READ_ONLY

    @field_validator("sandbox_mode", mode="before")
    @classmethod
    def _coerce_sandbox_mode(cls, value: Any) -> Any:
        return _as_enum(value, CodexSandboxMode)


class ProvidersSettings(MilestoneRunnerModel):
    """Section 17's provider section, including the non-wildcard environment allowlist.

    `allowed_environment_variables` is the only environment the runner forwards to a provider.
    The runner never reads, writes, forwards or stores provider authentication (invariant 1); an
    installed CLI keeps whatever it already uses.
    """

    claude: ClaudeProviderSettings
    codex: CodexProviderSettings
    allowed_environment_variables: list[str] = Field(default_factory=list)

    @field_validator("allowed_environment_variables")
    @classmethod
    def _validate_environment(cls, value: list[str]) -> list[str]:
        for index, name in enumerate(value):
            _scalar(
                name,
                f"providers.allowed_environment_variables[{index}]",
                _ENVIRONMENT_NAME_RE,
                MAX_IDENTIFIER_CHARS,
            )
        return _unique(value, "providers.allowed_environment_variables")


class VerificationCommandSettings(MilestoneRunnerModel):
    """One verification command: an argv list and its own bounded timeout (section 16).

    A list-typed `command` is how "never a shell string" becomes unrepresentable rather than
    discouraged; there is no `shell=True` path anywhere in this package.
    """

    command: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(ge=1, le=MAX_TIMEOUT_SECONDS)
    purpose: str | None = None

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: list[str]) -> list[str]:
        for index, argument in enumerate(value):
            if not argument or len(argument) > MAX_ARGUMENT_CHARS:
                raise ValueError(f"command[{index}] must be a bounded, non-empty argument")
        return value


class VerificationSettings(MilestoneRunnerModel):
    """Section 21's `verification` section: the focused and final command sets.

    `final` is the set section 5 runs once at `FINAL_VERIFYING` and again at `CLOSURE_VERIFYING`,
    so it is required and non-empty. `focused` is the configured focused set; it may be an empty
    list, because a milestone carries its own `focused_verification` commands (section 14) and a
    plan that supplies all of them leaves nothing for the configuration to add. An empty list is
    still an explicit statement in the file -- an absent key is not, and is refused.
    """

    focused: list[VerificationCommandSettings]
    final: list[VerificationCommandSettings] = Field(min_length=1)


class RunnerConfig(MilestoneRunnerModel):
    """The validated runner configuration of section 21.

    Every section the contract names is present and required, save the two the contract itself
    gives a default: `git`, whose two flags default to `false` (section 20). Nothing here is
    globally hard-coded in the engine -- `CONFIGURATION_MODEL.md` section 1's rule that "`main`
    ... has no special status to the engine" is why `expected_branch` is a configured value with
    no built-in fallback.
    """

    schema_version: int
    repository: RepositorySettings
    stage: StageSettings
    allowlist: AllowlistSettings
    review_policy: ReviewPolicySettings
    providers: ProvidersSettings
    verification: VerificationSettings
    git: GitSettings = Field(default_factory=GitSettings)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"configuration schema_version {value} is unknown; this build understands "
                f"only {CONFIG_SCHEMA_VERSION}"
            )
        return value

    @model_validator(mode="after")
    def _validate_contract_is_not_forbidden(self) -> "RunnerConfig":
        """The pinned contract may not also be declared writable.

        A configuration that lists its own governing contract inside `allowed_paths` would let a
        run edit the document that bounds it. That is a scope question, not a taste question, so
        it is refused at load rather than caught later by the guard.
        """
        if self.stage.contract_path in self.allowlist.allowed_paths:
            raise ValueError(
                f"stage.contract_path {self.stage.contract_path!r} must not appear in "
                "allowlist.allowed_paths: the governing contract is never writable surface"
            )
        return self


def load_runner_config(path: Path) -> RunnerConfig:
    """Read, parse and validate the runner configuration at `path` (section 4 item 8).

    Every failure -- an absent file, an unreadable one, a YAML error, a non-mapping root, an
    oversized document, an unknown field, an out-of-range budget -- raises
    :class:`InvalidRunnerConfiguration`. None of them falls back to a default: section 4 item 8
    and `CONFIGURATION_MODEL.md` section 2 both make a missing configuration a precondition
    failure.

    The document is parsed with `yaml.safe_load`, so no arbitrary object is constructed from a
    file the runner did not author.
    """
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise InvalidRunnerConfiguration(
            f"Cannot read the runner configuration {path}: {exc}"
        ) from exc
    if len(raw_bytes) > MAX_CONFIG_BYTES:
        raise InvalidRunnerConfiguration(
            f"The runner configuration {path} exceeds {MAX_CONFIG_BYTES} bytes"
        )
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidRunnerConfiguration(
            f"The runner configuration {path} is not valid UTF-8: {exc}"
        ) from exc
    try:
        document: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InvalidRunnerConfiguration(
            f"The runner configuration {path} is not valid YAML: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise InvalidRunnerConfiguration(
            f"The runner configuration {path} must be a YAML mapping at its root"
        )
    try:
        return RunnerConfig.model_validate(document)
    except ValidationError as exc:
        raise InvalidRunnerConfiguration(
            f"The runner configuration {path} is invalid: {exc}"
        ) from exc
