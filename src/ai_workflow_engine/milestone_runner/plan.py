"""Milestone plan loading, ordering and coverage reconciliation (AUTO-016).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 14 (the plan
format and the three DEC-016-005 plan-location rules), section 4 entry condition 6 (the plan
loads, schema-validates, is acyclic, and covers the configured surface exactly), section 11 (the
repository-scoped artifact root) and section 22 invariants 7, 8 and 19.

Where a plan may come from, and nothing else
--------------------------------------------
DEC-016-005 is ruled, and it is narrow:

1. With no `stage.plan_directory`, the plan root is
   `~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/` -- outside the target repository,
   a sibling of the run directories, addressed by the one identity derivation `git_inspect`
   defines and governed by the one containment check below. Nothing inside the worktree is
   opened.
2. A repository-local plan is accepted only when the governing stage contract's implementation
   allowlist lists that **exact path**. A directory entry does not cover the files under it, a
   glob does not stand in for what it would expand to, and a prefix is not a path. Anything else
   is `PLAN_PATH_NOT_ALLOWLISTED`.
3. There is no discovery. No search, no walk, no glob, no default-directory scan and no
   "nearest plan wins" behaviour exists in this module or anywhere in this package (invariant
   19). The external root is *listed* -- one non-recursive pass over one directory that provably
   sits outside the repository -- and a repository-local plan's file set comes from the
   configured allowlist itself, so no directory inside the worktree is ever enumerated.

The reasoning section 14 records is worth restating: letting the runner *discover* plans inside
the worktree would let a file the runner is supposed to be guarding decide what the runner is
allowed to change. The narrow exception keeps a deliberately contract-published plan possible
without reopening discovery -- the escape hatch is a written allowlist entry a human authored,
not a path the runner found.

Fail-closed validation
----------------------
`MilestoneSpec` (`models.py`) already rejects an unknown field and an unknown `schema_version`,
because it is a closed schema. This module adds the plan-level rules that no single milestone can
see: a duplicate `milestone_id`, a dependency naming a milestone that is not in the plan, a
dependency cycle -- reported with the full cycle named -- and section 4 item 6's exact
reconciliation of the union of every `allowed_files` against the configured `required_coverage`,
where a gap and an extra are detected independently and both are `PLAN_COVERAGE_MISMATCH`.
"""

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Final

import yaml
from pydantic import ValidationError

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.config import RunnerConfig
from ai_workflow_engine.milestone_runner.models import (
    MilestoneSpec,
    StopReason,
    normalize_repository_path,
)

#: Section 11: the external, repository-scoped artifact root that holds both `plans/` (run input)
#: and the per-run directories (run output). One root, one identity derivation, one containment
#: check -- which is exactly why they are siblings rather than two independently configured
#: locations.
ARTIFACT_ROOT_DIRECTORY: Final = ".ai-workflow-engine"
MILESTONE_RUNS_DIRECTORY: Final = "milestone-runs"
PLANS_DIRECTORY: Final = "plans"

#: A plan file is named for the milestone it defines. The grammar is closed, so listing the
#: external root is a filter over exact names rather than a pattern search.
PLAN_FILE_NAME_RE = re.compile(r"(?P<milestone_id>AUTO-[0-9]{3}-M[0-9]{2})\.yaml")

#: The characters that make an allowlist entry a pattern rather than a path. DEC-016-005 rule 2
#: requires the *exact path*; an entry carrying any of these is a glob, and a glob is refused.
_PATTERN_CHARACTERS: Final = frozenset("*?[]")

#: The largest plan file this loader will read. A milestone definition is a hand-authored
#: document; anything larger is a mistake or an attempt to exhaust memory.
MAX_PLAN_BYTES: Final = 1 << 20

#: The largest number of milestone files one plan may hold, so listing the external root is
#: bounded even if something else fills it.
MAX_PLAN_FILES: Final = 64


class PlanError(WorkflowEngineError):
    """Base fail-closed plan failure.

    `stop_reason` is `None` here and set only on the two subclasses whose codes the contract
    names verbatim. Section 4 item 6 gives `PLAN_COVERAGE_MISMATCH` and section 14 rule 2 gives
    `PLAN_PATH_NOT_ALLOWLISTED`; the contract names no code for a malformed plan document, so
    none is coined for one.
    """

    stop_reason: ClassVar[StopReason | None] = None


class PlanValidationError(PlanError):
    """The plan document is absent, unreadable, malformed, or breaks a plan-level rule."""


class PlanDependencyCycle(PlanValidationError):
    """The dependency graph is cyclic. The message names the full cycle, not just one member."""


class PlanCoverageMismatch(PlanError):
    """The union of every milestone's `allowed_files` is not the configured coverage exactly.

    A gap and an extra are two different mistakes and are reported as two independent sets, both
    under section 4 item 6's one code: a gap means the plan leaves part of the authorized surface
    unimplemented, an extra means the plan claims surface the configuration never authorized.
    """

    stop_reason: ClassVar[StopReason | None] = StopReason.PLAN_COVERAGE_MISMATCH

    def __init__(
        self, message: str, *, missing: Sequence[str] = (), unexpected: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.missing: tuple[str, ...] = tuple(missing)
        self.unexpected: tuple[str, ...] = tuple(unexpected)


class PlanPathNotAllowlisted(PlanError):
    """A repository-local plan path the governing contract does not list verbatim (rule 2)."""

    stop_reason: ClassVar[StopReason | None] = StopReason.PLAN_PATH_NOT_ALLOWLISTED


@dataclass(frozen=True, slots=True)
class PlanRoot:
    """Where this run's plan lives, and which of DEC-016-005's two rules admitted it.

    `is_repository_local` is not a detail: it decides how the file set is determined. An external
    root is listed; a repository-local root never is, and its files come from the contract
    allowlist instead.
    """

    path: Path
    is_repository_local: bool


@dataclass(frozen=True, slots=True)
class MilestonePlan:
    """A validated plan: its milestones in dependency order, and where each came from."""

    milestones: tuple[MilestoneSpec, ...]
    source_paths: tuple[str, ...]

    @property
    def milestone_ids(self) -> tuple[str, ...]:
        """Every milestone id, in the plan's dependency order."""
        return tuple(milestone.milestone_id for milestone in self.milestones)

    def covered_paths(self) -> tuple[str, ...]:
        """The sorted union of every milestone's `allowed_files` (section 4 item 6)."""
        union = {
            normalize_repository_path(path, "allowed_files")
            for milestone in self.milestones
            for path in milestone.allowed_files
        }
        return tuple(sorted(union, key=lambda item: item.encode("utf-8")))


def repository_scoped_root(repository_identity: str) -> Path:
    """Return `~/.ai-workflow-engine/milestone-runs/<repository-id>/` (section 11).

    Pure derivation: nothing is created, resolved or verified here. This is the single function
    both the plan root and the run root are built from, so "the plan root and the run root share
    one repository-identity derivation" is a call graph rather than a claim.
    """
    if not repository_identity or "/" in repository_identity or repository_identity.startswith("."):
        raise PlanValidationError(
            f"{repository_identity!r} is not a usable repository identity for an artifact root"
        )
    return Path.home() / ARTIFACT_ROOT_DIRECTORY / MILESTONE_RUNS_DIRECTORY / repository_identity


def default_plan_root(repository_identity: str) -> Path:
    """Return DEC-016-005 rule 1's external default plan root, a sibling of the run directories."""
    return repository_scoped_root(repository_identity) / PLANS_DIRECTORY


def reject_repository_containment(root: Path, repository_root: Path) -> None:
    """Refuse `root` if it is inside `repository_root` (invariant 7).

    The single containment check the plan root and the run root share. Both sides are fully
    realized before comparison, so a symlink pointing back into the worktree cannot dress an
    inside path up as an outside one. A runner operating on a repository must not be able to
    pollute the diff it is guarding, and plan *input* is under the same rule as run output
    because section 11 makes them siblings.
    """
    real_repository = os.path.realpath(repository_root)
    real_root = os.path.realpath(root)
    if real_root == real_repository or real_root.startswith(real_repository + os.sep):
        raise PlanValidationError(
            f"The plan root {real_root} must not be inside the repository {real_repository}: "
            "DEC-016-005 rule 1 fixes an external root that is never part of Git"
        )


def reject_symlink_components(path: Path, label: str) -> None:
    """Refuse `path` if any component of it is a symbolic link (invariant 8).

    Walked from the filesystem root downwards with `lstat`, so no component is followed in order
    to decide whether it should have been followed. A component that does not exist yet is not a
    link; whatever opens the path afterwards reports its absence.
    """
    absolute = path if path.is_absolute() else Path(os.path.abspath(path))
    current = Path(absolute.anchor or os.sep)
    for part in absolute.relative_to(current).parts:
        current = current / part
        if current.is_symlink():
            raise PlanValidationError(f"{label} path component {current} is a symbolic link")


def _is_verbatim_path(entry: str) -> bool:
    """Whether an allowlist entry is an exact path rather than a pattern (rule 2)."""
    return not (_PATTERN_CHARACTERS & set(entry))


def resolve_plan_root(config: RunnerConfig, repository_root: Path) -> PlanRoot:
    """Resolve this run's plan root under DEC-016-005's three rules (section 14, section 21).

    * No `stage.plan_directory`: rule 1's external default,
      `~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`, verified to sit outside the
      worktree and to contain no symlinked component. Nothing inside the worktree is opened.
    * A `plan_directory` outside the worktree: accepted only under the same repository-scoped
      artifact root, because section 21 admits an external location only there. An arbitrary
      external directory is refused.
    * A `plan_directory` inside the worktree: accepted as a *location* here and constrained by
      rule 2 at :func:`MilestonePlanLoader.plan_paths`, which admits only files the governing
      contract lists verbatim.

    No branch of this function searches, walks, globs or scans for a plan (invariant 19).
    """
    identity = config.repository.identity
    scoped_root = repository_scoped_root(identity)
    configured = config.stage.plan_directory

    if configured is None:
        root = default_plan_root(identity)
        reject_repository_containment(root, repository_root)
        reject_symlink_components(root, "The default plan root")
        return PlanRoot(path=root, is_repository_local=False)

    real_repository = os.path.realpath(repository_root)
    candidate = (
        Path(configured) if configured.startswith("/") else Path(repository_root) / configured
    )
    real_candidate = os.path.realpath(candidate)
    inside = real_candidate == real_repository or real_candidate.startswith(
        real_repository + os.sep
    )

    if inside:
        reject_symlink_components(candidate, "The repository-local plan root")
        return PlanRoot(path=candidate, is_repository_local=True)

    real_scoped = os.path.realpath(scoped_root)
    if real_candidate != real_scoped and not real_candidate.startswith(real_scoped + os.sep):
        raise PlanValidationError(
            f"stage.plan_directory {configured!r} resolves to {real_candidate}, which is neither "
            f"inside the repository nor under the repository-scoped artifact root {real_scoped}: "
            "section 21 admits an external plan location only under that root"
        )
    reject_repository_containment(candidate, repository_root)
    reject_symlink_components(candidate, "The configured plan root")
    return PlanRoot(path=candidate, is_repository_local=False)


class MilestonePlanLoader:
    """Load, validate, dependency-order and coverage-reconcile one milestone plan (section 14).

    The loader owns the whole fail-closed path from "where may a plan come from" to "these
    milestones, in this order, cover exactly this surface". It refuses before it reads whenever it
    can: a repository-local plan the contract does not list verbatim is refused without the file
    ever being opened, which is what section 14 rule 3 means by "refused at load, before any
    provider is invoked".
    """

    def __init__(self, config: RunnerConfig, repository_root: Path) -> None:
        self.config = config
        self.repository_root = repository_root

    def plan_root(self) -> PlanRoot:
        """This run's plan root, resolved under DEC-016-005 (see :func:`resolve_plan_root`)."""
        return resolve_plan_root(self.config, self.repository_root)

    def plan_paths(self) -> tuple[Path, ...]:
        """The exact plan files this run will read, in a deterministic order.

        For an external root this is one non-recursive listing of that directory, filtered to the
        closed `AUTO-0XX-MNN.yaml` grammar and sorted. The directory provably sits outside the
        worktree, so listing it is not repository discovery.

        For a repository-local root the file set comes from `allowlist.allowed_paths` -- the
        governing contract's implementation surface as the configuration restates it -- and never
        from the filesystem. An entry qualifies only when it is a verbatim path (rule 2: not a
        glob), sits directly in the configured plan directory (not merely under it, so a prefix
        does not qualify), and carries a plan file's name. A directory entry names a directory and
        therefore qualifies nothing. If no entry qualifies, the refusal is
        `PLAN_PATH_NOT_ALLOWLISTED` and no path inside the worktree is opened at all.
        """
        root = self.plan_root()
        if root.is_repository_local:
            return self._allowlisted_plan_paths(root.path)
        return self._external_plan_paths(root.path)

    def _external_plan_paths(self, root: Path) -> tuple[Path, ...]:
        try:
            entries = sorted(os.listdir(root))
        except OSError as exc:
            raise PlanValidationError(f"Cannot read the plan root {root}: {exc}") from exc
        selected: list[Path] = []
        for name in entries:
            if PLAN_FILE_NAME_RE.fullmatch(name) is None:
                continue
            candidate = root / name
            if candidate.is_symlink() or not candidate.is_file():
                raise PlanValidationError(
                    f"The plan file {candidate} is a symbolic link or not a regular file"
                )
            selected.append(candidate)
        if not selected:
            raise PlanValidationError(
                f"The plan root {root} holds no milestone file named AUTO-0XX-MNN.yaml"
            )
        if len(selected) > MAX_PLAN_FILES:
            raise PlanValidationError(
                f"The plan root {root} holds more than {MAX_PLAN_FILES} milestone files"
            )
        return tuple(selected)

    def _allowlisted_plan_paths(self, root: Path) -> tuple[Path, ...]:
        directory = self._repository_relative_directory(root)
        selected: list[Path] = []
        for entry in self.config.allowlist.allowed_paths:
            if not _is_verbatim_path(entry):
                continue
            parent, _, name = entry.rpartition("/")
            if parent != directory or PLAN_FILE_NAME_RE.fullmatch(name) is None:
                continue
            selected.append(self.repository_root / entry)
        if not selected:
            raise PlanPathNotAllowlisted(
                f"The repository-local plan root {root} holds no plan path the governing stage "
                "contract's implementation allowlist lists verbatim: DEC-016-005 rule 2 requires "
                "the exact path, and neither a directory entry, nor a glob, nor a prefix is one"
            )
        for candidate in selected:
            reject_symlink_components(candidate, "The repository-local plan file")
            if not candidate.is_file():
                raise PlanValidationError(
                    f"The allowlisted plan path {candidate} is not a regular file"
                )
        return tuple(sorted(selected, key=lambda item: str(item).encode("utf-8")))

    def _repository_relative_directory(self, root: Path) -> str:
        """The configured plan directory as a normalized repository-relative path."""
        try:
            relative = os.path.relpath(root, self.repository_root)
        except ValueError as exc:  # pragma: no cover - only on a cross-drive path
            raise PlanValidationError(f"Cannot relate {root} to {self.repository_root}") from exc
        if relative == ".":
            return ""
        return normalize_repository_path(relative, "stage.plan_directory")

    def _read_milestone(self, path: Path) -> MilestoneSpec:
        """Read and schema-validate exactly one milestone file, fail-closed."""
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise PlanValidationError(f"Cannot read the plan file {path}: {exc}") from exc
        if len(payload) > MAX_PLAN_BYTES:
            raise PlanValidationError(f"The plan file {path} exceeds {MAX_PLAN_BYTES} bytes")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlanValidationError(f"The plan file {path} is not valid UTF-8: {exc}") from exc
        try:
            document: Any = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise PlanValidationError(f"The plan file {path} is not valid YAML: {exc}") from exc
        if not isinstance(document, dict):
            raise PlanValidationError(f"The plan file {path} must be a YAML mapping at its root")
        try:
            milestone = MilestoneSpec.model_validate(document)
        except ValidationError as exc:
            raise PlanValidationError(
                f"The plan file {path} is not a valid milestone: {exc}"
            ) from exc
        expected = PLAN_FILE_NAME_RE.fullmatch(path.name)
        if expected is not None and expected.group("milestone_id") != milestone.milestone_id:
            raise PlanValidationError(
                f"The plan file {path} defines {milestone.milestone_id}, which its name does not "
                "name: a plan file and the milestone it holds must agree"
            )
        return milestone

    def load(self) -> MilestonePlan:
        """Load every plan file, validate the plan as a whole, and order it (section 4 item 6).

        The order of the checks is the order of the contract's own list, and each is fail-closed:
        every file schema-validates, no `milestone_id` repeats, every dependency names a
        milestone in this plan, the graph is acyclic, and the union of every `allowed_files`
        equals `allowlist.required_coverage` exactly.
        """
        paths = self.plan_paths()
        milestones = [self._read_milestone(path) for path in paths]

        by_id: dict[str, MilestoneSpec] = {}
        for milestone in milestones:
            if milestone.milestone_id in by_id:
                raise PlanValidationError(
                    f"{milestone.milestone_id} is defined more than once in this plan"
                )
            by_id[milestone.milestone_id] = milestone

        for milestone in milestones:
            for dependency in milestone.depends_on:
                if dependency not in by_id:
                    raise PlanValidationError(
                        f"{milestone.milestone_id} depends on {dependency}, which this plan does "
                        "not define"
                    )

        ordered = _dependency_order(by_id)
        plan = MilestonePlan(
            milestones=ordered,
            source_paths=tuple(str(path) for path in paths),
        )
        self._reconcile_coverage(plan)
        return plan

    def _reconcile_coverage(self, plan: MilestonePlan) -> None:
        """Section 4 item 6: the union of `allowed_files` equals `required_coverage` exactly."""
        covered = set(plan.covered_paths())
        required = set(self.config.allowlist.required_coverage)
        missing = sorted(required - covered)
        unexpected = sorted(covered - required)
        if missing or unexpected:
            raise PlanCoverageMismatch(
                "The plan does not cover allowlist.required_coverage exactly: "
                f"{len(missing)} required path(s) no milestone claims ({missing}), and "
                f"{len(unexpected)} milestone path(s) the coverage does not require "
                f"({unexpected})",
                missing=missing,
                unexpected=unexpected,
            )


def _dependency_order(by_id: Mapping[str, MilestoneSpec]) -> tuple[MilestoneSpec, ...]:
    """Return the milestones in a deterministic dependency order, or name the cycle.

    Kahn's algorithm with ties broken by `milestone_id`, so one plan always yields one order --
    a run that resumes must continue the sequence it started, not a differently-shuffled one with
    the same dependency structure.
    """
    remaining = {
        milestone_id: set(milestone.depends_on) for milestone_id, milestone in by_id.items()
    }
    ordered: list[MilestoneSpec] = []
    while remaining:
        ready = sorted(milestone_id for milestone_id, pending in remaining.items() if not pending)
        if not ready:
            raise PlanDependencyCycle(
                "The plan's dependency graph is cyclic: " + _describe_cycle(remaining)
            )
        for milestone_id in ready:
            ordered.append(by_id[milestone_id])
            del remaining[milestone_id]
        for pending in remaining.values():
            pending.difference_update(ready)
    return tuple(ordered)


def _describe_cycle(remaining: Mapping[str, set[str]]) -> str:
    """Name one full cycle in `remaining`, as `A -> B -> A` (section 14).

    Naming the whole cycle rather than one member of it is the contract's requirement, and the
    practical difference between an operator who can fix the plan and one who has to bisect it.
    """
    for start in sorted(remaining):
        path: list[str] = []
        seen: set[str] = set()
        current = start
        while current in remaining and current not in seen:
            seen.add(current)
            path.append(current)
            candidates = sorted(remaining[current] & remaining.keys())
            if not candidates:
                break
            current = candidates[0]
        if current in path:
            cycle = [*path[path.index(current) :], current]
            return " -> ".join(cycle)
    return " -> ".join(sorted(remaining))
