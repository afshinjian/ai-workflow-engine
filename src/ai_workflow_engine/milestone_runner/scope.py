"""Segment-aware scope guard for the AUTO-016 milestone runner.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 15 (the three
independent checks and segment-aware matching), section 6 defect P-1, section 4 item 5 and
section 22 invariant 12.

Defect P-1, and why matching is written out here
------------------------------------------------
The prototype's `path_matches()` used `fnmatch`, whose `*` crosses `/`. Under those semantics
`tests/test_*.py` also matches `tests/test_pkg/inner.py`, so an allowlist entry meant to name a
handful of test modules silently admitted an entire subtree -- a latent hole in the one guard
whose whole job is to refuse exactly that. The prototype's own `t_path_matches` self-test never
covered the directory-crossing case, which is why the defect survived a real run.

:func:`path_matches` therefore matches segment by segment. Within one segment the ordinary
wildcard characters apply; across segments only a literal `**` segment spans anything. There is
no way to widen this at runtime: :class:`ScopeGuard` is frozen, holds tuples, and exposes no
method that adds a pattern (invariant 12).

What a violation is
-------------------
`SECURITY_MODEL.md` section 7 is binding: "scope creep is a validation failure, not a warning."
The guard therefore reports every violating path as typed data and never repairs anything -- it
does not revert, restore, discard or delete the offending change, and it holds no code path that
could. Deciding what to do with a violation is `application.py`'s job; the guard's job is to be
unable to miss one.

The contract names a stop code for exactly one of the three checks
(`OUT_OF_MILESTONE_SCOPE`, section 15 check 2). It describes the other two as stops without
naming a code, so none is coined here: :class:`ScopeViolation` carries `stop_reason=None` for
them and records which check failed, which is the narrower reading of an under-specified
contract rather than a guess dressed up as a constant.
"""

import fnmatch
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field, field_validator

from ai_workflow_engine.milestone_runner.config import RunnerConfig
from ai_workflow_engine.milestone_runner.models import (
    MilestoneRunnerModel,
    MilestoneSpec,
    StopReason,
    normalize_repository_path,
)

#: The one construct that spans path segments. A segment equal to this string matches zero or
#: more whole segments; every other segment is matched within itself, so `*` never crosses `/`.
RECURSIVE_SEGMENT: str = "**"


class ScopeCheck(StrEnum):
    """Which of section 15's three independent checks a violation came from.

    The order of the members is the order of evaluation, and it is load-bearing: forbidden is
    evaluated first and wins outright, so a path that is both forbidden and allowed is a
    forbidden path (invariant 12 -- "a forbidden path always loses to nothing").
    """

    FORBIDDEN_PATH = "FORBIDDEN_PATH"
    CUMULATIVE_ALLOWLIST = "CUMULATIVE_ALLOWLIST"
    MILESTONE_SCOPE = "MILESTONE_SCOPE"


def _match_segments(path_segments: Sequence[str], pattern_segments: Sequence[str]) -> bool:
    """Match one normalized path against one normalized pattern, segment by segment.

    A `**` pattern segment matches zero or more path segments; any other pattern segment matches
    exactly one path segment, using `fnmatch.fnmatchcase` *on that segment alone*. Applying the
    wildcard within a single segment is the whole correction of defect P-1: `*` and `?` cannot
    see a separator they are never given.

    The walk is an explicit reachable-position set rather than recursion, so a pattern carrying
    several `**` segments costs `len(path) * len(pattern)` steps instead of exponentially many --
    a pattern set is operator-authored, but a guard should not have a pathological input at all.
    """
    reachable = {0}
    for pattern_segment in pattern_segments:
        if pattern_segment == RECURSIVE_SEGMENT:
            # `**` consumes zero or more segments: every position at or after the earliest
            # currently reachable one becomes reachable.
            earliest = min(reachable)
            reachable = set(range(earliest, len(path_segments) + 1))
            continue
        advanced = set()
        for index in reachable:
            if index < len(path_segments) and fnmatch.fnmatchcase(
                path_segments[index], pattern_segment
            ):
                advanced.add(index + 1)
        if not advanced:
            return False
        reachable = advanced
    return len(path_segments) in reachable


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    """Return whether `path` matches any pattern in `patterns`, segment-aware (section 15).

    Both sides are normalized to repository-relative POSIX paths first, through the single
    canonicalization `models.normalize_repository_path` defines, so two spellings of one path
    compare equal and an absolute or traversal-shaped input is refused rather than resolved.

    `*` matches within one segment and never crosses `/`; `**` is the only segment-spanning
    construct. `path_matches("tests/test_pkg/inner.py", ["tests/test_*.py"])` is therefore
    `False` -- the prototype defect P-1 case -- while
    `path_matches("tests/test_pkg/inner.py", ["tests/**"])` is `True`.

    A pattern names what it names: `src/pkg` matches `src/pkg` and not `src/pkg/module.py`.
    Nothing is implicitly expanded into a prefix, because an implicit expansion is how a guard
    ends up permitting more than its author wrote.
    """
    path_segments = normalize_repository_path(path, "path").split("/")
    for pattern in patterns:
        pattern_segments = normalize_repository_path(pattern, "pattern").split("/")
        if _match_segments(path_segments, pattern_segments):
            return True
    return False


class ScopeViolation(MilestoneRunnerModel):
    """One changed path that failed one of section 15's checks.

    `stop_reason` is `OUT_OF_MILESTONE_SCOPE` for the per-milestone check, which is the one code
    section 15 names, and `None` for the other two, whose stops the contract describes without
    giving a code. A violation is a validation failure, never a warning, in all three cases.
    """

    path: str
    check: ScopeCheck
    stop_reason: StopReason | None = None
    detail: str

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return normalize_repository_path(value, "path")


class ScopeDecision(MilestoneRunnerModel):
    """The result of evaluating one changed-path set against the guard.

    Carrying every violation rather than the first one is deliberate: an operator reading a stop
    record needs the whole picture, and a guard that stops at the first violation hides the rest
    behind a fix-one-at-a-time loop.
    """

    changed_paths: list[str] = Field(default_factory=list)
    violations: list[ScopeViolation] = Field(default_factory=list)

    @property
    def permitted(self) -> bool:
        """Whether every changed path passed every applicable check."""
        return not self.violations

    @property
    def stop_reasons(self) -> tuple[StopReason, ...]:
        """The distinct typed stop reasons this decision carries, in first-seen order."""
        seen: list[StopReason] = []
        for violation in self.violations:
            if violation.stop_reason is not None and violation.stop_reason not in seen:
                seen.append(violation.stop_reason)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class ScopeGuard:
    """Section 15's three independent checks over one cumulative allowlist.

    Frozen, and holding tuples rather than lists, because invariant 12 forbids a runtime path
    that widens `allowlist.allowed_paths` or a milestone's `allowed_files`. There is no `add`,
    `extend` or `update` method to call and no mutable attribute to append to: widening the
    surface requires editing the configuration or the plan, which is a human act with a diff.
    """

    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]

    @classmethod
    def from_config(cls, config: RunnerConfig) -> "ScopeGuard":
        """Build the guard from the validated configuration's `allowlist` section."""
        return cls(
            allowed_paths=tuple(config.allowlist.allowed_paths),
            forbidden_paths=tuple(config.allowlist.forbidden_paths),
        )

    def is_forbidden(self, path: str) -> bool:
        """Whether `path` matches the forbidden set (check 3, evaluated first)."""
        return path_matches(path, self.forbidden_paths)

    def is_allowed(self, path: str) -> bool:
        """Whether `path` matches the cumulative allowlist (check 1)."""
        return path_matches(path, self.allowed_paths)

    def evaluate(
        self,
        changed_paths: Sequence[str],
        milestone: MilestoneSpec | None = None,
        *,
        milestone_owned_paths: Sequence[str] | None = None,
    ) -> ScopeDecision:
        """Evaluate `changed_paths` against all three checks (section 15).

        Order is the contract's: forbidden first and decisive, then the cumulative allowlist,
        then -- when a milestone is active -- that milestone's own `allowed_files`. A path inside
        the cumulative allowlist but outside the active milestone is `OUT_OF_MILESTONE_SCOPE`, a
        stop rather than a warning.

        Checks 1 and 3 are **cumulative**: they see every changed path, always. Check 2 is
        **milestone-local**, and `milestone_owned_paths` is the set the caller has durable
        evidence the current milestone actually introduced or modified -- the delta against the
        previous milestone checkpoint. Passing it is what keeps a completed milestone's own
        authorized files from being reclassified as the current milestone's violations
        (GOV-AUTO-11-F1), and passing a *narrower* set can only remove a stop that was never the
        current milestone's to answer for: nothing here widens `allowed_files`, and a path in
        the owned set that the milestone does not list still stops, so no milestone can acquire
        another's paths.

        Omitting `milestone_owned_paths` evaluates check 2 against every changed path. That is
        the honest reading when no checkpoint exists yet -- the first milestone of a run owns the
        whole diff -- and it is what a caller holding no checkpoint evidence must assume.

        Passing `milestone=None` evaluates checks 1 and 3 only, which is what a gate outside a
        milestone (preflight, final verification, an approval gate) has to work with; it is not a
        way to skip check 2 while a milestone is active, because the caller that has a milestone
        passes it.
        """
        normalized = [
            normalize_repository_path(path, f"changed_paths[{index}]")
            for index, path in enumerate(changed_paths)
        ]
        owned: set[str] | None = (
            None
            if milestone_owned_paths is None
            else {
                normalize_repository_path(path, f"milestone_owned_paths[{index}]")
                for index, path in enumerate(milestone_owned_paths)
            }
        )
        violations: list[ScopeViolation] = []
        for path in normalized:
            if self.is_forbidden(path):
                violations.append(
                    ScopeViolation(
                        path=path,
                        check=ScopeCheck.FORBIDDEN_PATH,
                        detail=(
                            "the path matches allowlist.forbidden_paths, which is decided before "
                            "and independently of any allowlist entry"
                        ),
                    )
                )
                continue
            if not self.is_allowed(path):
                violations.append(
                    ScopeViolation(
                        path=path,
                        check=ScopeCheck.CUMULATIVE_ALLOWLIST,
                        detail=(
                            "the path is outside allowlist.allowed_paths, the authorized stage "
                            "contract's implementation surface"
                        ),
                    )
                )
                continue
            if milestone is None:
                continue
            if owned is not None and path not in owned:
                # An earlier, completed milestone's own authorized file, unchanged since its
                # checkpoint. It passed checks 1 and 3 above like every other path; it is simply
                # not this milestone's to answer for.
                continue
            if not path_matches(path, milestone.allowed_files):
                violations.append(
                    ScopeViolation(
                        path=path,
                        check=ScopeCheck.MILESTONE_SCOPE,
                        stop_reason=StopReason.OUT_OF_MILESTONE_SCOPE,
                        detail=(
                            f"the path is inside the cumulative allowlist but outside "
                            f"{milestone.milestone_id}'s own allowed_files"
                        ),
                    )
                )
        return ScopeDecision(changed_paths=normalized, violations=violations)
