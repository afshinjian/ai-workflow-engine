"""Deterministic engine execution provenance (Milestone 3, task T-307).

Governed review evidence is only meaningful if it records *which engine produced it*. This
module is the single place that answers that question, and the only symbol tests substitute in
order to obtain deterministic provenance. It resolves five facts about the running engine:

- ``engine_version`` — the canonical running version (the imported module constant), with the
  distribution metadata version cross-checked rather than silently preferred;
- ``engine_head`` / ``engine_worktree_clean`` — the engine's own Git worktree state;
- ``engine_install_mode`` — ``editable`` | ``installed`` | ``source``;
- ``engine_package_path`` — the package directory actually imported.

Everything is derived from the *imported package's* own location, never from
``config.project.repository``: that names the target repository, which coincides with the engine
only under self-governance.

**Fail-closed rule (Human Owner decision OD-1, binding).** An ``editable`` installation whose
engine worktree is dirty refuses every governed prompt/review/provenance execution, whether or
not a verification bundle is selected — governed evidence must never be produced by uncommitted
engine code. The refusal is bounded to that governed surface; ordinary development commands are
unaffected because they never call this module.

The governing rule for metadata is that *absent* metadata is a defined state, while
*present-but-unreadable or contradictory* metadata is a refusal. A malformed ``direct_url.json``
is never coerced to ``installed``, because ``installed`` is the permissive branch of OD-1 and
coercion would silently turn an unreadable engine into a permitted one.

There is deliberately no injection parameter, CLI option, configuration key, or environment
variable that bypasses any of this.
"""

import json
from importlib import metadata
from pathlib import Path
from typing import Literal

import ai_workflow_engine
from ai_workflow_engine.exceptions import GitCommandError, WorkflowEngineError
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.prompt.models import CanonicalEngineProvenance

InstallMode = Literal["editable", "installed", "source"]

_DISTRIBUTION_NAME = "ai-workflow-engine"

# PEP 610 declares these three source descriptors mutually exclusive.
_SOURCE_DESCRIPTORS: tuple[str, ...] = ("dir_info", "vcs_info", "archive_info")

_VCS_REQUIRED_FIELDS: tuple[str, ...] = ("vcs", "commit_id")
_VCS_OPTIONAL_FIELDS: tuple[str, ...] = (
    "requested_revision",
    "resolved_revision",
    "resolved_revision_type",
)

# A package that is not inside any Git worktree has no HEAD to record. The empty string states
# that explicitly and cannot be confused with a real object id, and the worktree is reported
# clean because an installed artifact carries no uncommitted modifications by construction. This
# case is unreachable for an `editable` install, which is refused outright when it has no
# worktree, so it can never soften the OD-1 dirty-engine rule.
_NO_ENGINE_WORKTREE_HEAD = ""


class EngineProvenanceError(WorkflowEngineError):
    """Engine provenance could not be established, or establishes a refused state.

    One error type, as frozen by the contract, carrying a distinct ``code`` per condition so a
    failure stays diagnosable and testable rather than collapsing into one opaque message.
    """

    code = "engine_provenance_error"

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _error(code: str, message: str) -> EngineProvenanceError:
    return EngineProvenanceError(message, code=code)


def _package_path() -> Path:
    """The package directory actually imported."""
    package_file = getattr(ai_workflow_engine, "__file__", None)
    if package_file is None:  # pragma: no cover - namespace package, not how this ships
        raise _error(
            "engine_package_path_unresolvable",
            "The ai_workflow_engine package has no resolvable file location",
        )
    return Path(package_file).parent.resolve()


def _load_distribution() -> metadata.Distribution | None:
    """The engine's installed distribution, or ``None`` when it has no metadata at all."""
    try:
        return metadata.distribution(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return None


def _classify_direct_url(raw: str) -> InstallMode:
    """Classify a PEP 610 ``direct_url.json`` record, refusing every unreadable shape."""
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise _error(
            "engine_direct_url_malformed", f"direct_url.json is not valid JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise _error(
            "engine_direct_url_not_object",
            f"direct_url.json must be a JSON object, found {type(document).__name__}",
        )
    if "url" not in document:
        raise _error("engine_direct_url_missing_url", "direct_url.json has no 'url' field")
    if not isinstance(document["url"], str):
        raise _error(
            "engine_direct_url_invalid_url_type",
            "direct_url.json 'url' must be a string",
        )
    if "subdirectory" in document and not isinstance(document["subdirectory"], str):
        raise _error(
            "engine_direct_url_invalid_subdirectory",
            "direct_url.json 'subdirectory' must be a string when present",
        )

    present = [name for name in _SOURCE_DESCRIPTORS if name in document]
    if not present:
        raise _error(
            "engine_direct_url_no_source",
            "direct_url.json names no recognized source descriptor",
        )
    if len(present) > 1:
        # Checked before any descriptor's own fields, so the contradiction is reported as such
        # whether `editable` is true, false, or absent — it is structural, not a flag's function.
        raise _error(
            "engine_direct_url_multiple_sources",
            f"direct_url.json names mutually exclusive source descriptors {present}",
        )

    descriptor = present[0]
    if descriptor == "dir_info":
        return _classify_dir_info(document["dir_info"])
    if descriptor == "vcs_info":
        _validate_vcs_info(document["vcs_info"])
        # PEP 610 expresses editability only through `dir_info`, so a VCS install is never
        # editable.
        return "installed"
    _validate_archive_info(document["archive_info"])
    return "installed"


def _classify_dir_info(info: object) -> InstallMode:
    if not isinstance(info, dict):
        raise _error(
            "engine_direct_url_invalid_dir_info",
            f"direct_url.json 'dir_info' must be an object, found {type(info).__name__}",
        )
    if "editable" not in info:
        # A bare `{"dir_info": {}}` is a real, valid, non-editable local install.
        return "installed"
    editable = info["editable"]
    if not isinstance(editable, bool):
        raise _error(
            "engine_direct_url_invalid_editable",
            "direct_url.json 'dir_info.editable' must be a boolean when present",
        )
    return "editable" if editable else "installed"


def _validate_vcs_info(info: object) -> None:
    if not isinstance(info, dict):
        raise _error(
            "engine_direct_url_invalid_vcs_info",
            f"direct_url.json 'vcs_info' must be an object, found {type(info).__name__}",
        )
    for field in _VCS_REQUIRED_FIELDS:
        if not isinstance(info.get(field), str):
            raise _error(
                "engine_direct_url_invalid_vcs_field",
                f"direct_url.json 'vcs_info.{field}' must be a string",
            )
    for field in _VCS_OPTIONAL_FIELDS:
        if field in info and not isinstance(info[field], str):
            raise _error(
                "engine_direct_url_invalid_vcs_field",
                f"direct_url.json 'vcs_info.{field}' must be a string when present",
            )


def _validate_archive_info(info: object) -> None:
    if not isinstance(info, dict):
        raise _error(
            "engine_direct_url_invalid_archive_info",
            f"direct_url.json 'archive_info' must be an object, found {type(info).__name__}",
        )
    if "hashes" in info:
        hashes = info["hashes"]
        if not isinstance(hashes, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in hashes.items()
        ):
            raise _error(
                "engine_direct_url_invalid_archive_field",
                "direct_url.json 'archive_info.hashes' must map strings to strings",
            )
    if "hash" in info and not isinstance(info["hash"], str):
        raise _error(
            "engine_direct_url_invalid_archive_field",
            "direct_url.json 'archive_info.hash' must be a string when present",
        )


def _classify_install_mode(distribution: metadata.Distribution | None) -> InstallMode:
    """Classify the install mode, distinguishing the two metadata-absent cases explicitly."""
    if distribution is None:
        # The distribution's own metadata is unavailable: a source checkout on `sys.path`.
        return "source"
    raw = distribution.read_text("direct_url.json")
    if raw is None:
        # The distribution resolves but records no direct URL: an ordinary index/wheel install.
        return "installed"
    return _classify_direct_url(raw)


def _resolve_version(distribution: metadata.Distribution | None) -> str:
    """Canonical version is the imported module constant; metadata is cross-checked only."""
    canonical = getattr(ai_workflow_engine, "__version__", None)
    if not isinstance(canonical, str) or canonical == "":
        raise _error(
            "engine_version_unresolvable",
            "The imported ai_workflow_engine package declares no usable __version__",
        )
    if distribution is None:
        return canonical
    try:
        observed = distribution.metadata["Version"]
    except KeyError:  # pragma: no cover - defensive: METADATA without a Version field
        observed = None
    if observed is None:
        return canonical
    if observed != canonical:
        raise _error(
            "engine_version_mismatch",
            f"Engine version disagreement: imported module reports {canonical!r} but the "
            f"installed distribution metadata reports {observed!r}",
        )
    return canonical


def _engine_worktree_root(package_path: Path) -> Path | None:
    """The Git worktree containing the imported package, found by a pure path walk.

    Deliberately a `pathlib` parent walk rather than a Git call: locating the engine's own
    worktree must not depend on, or extend, the read-only Git command surface.
    """
    for candidate in (package_path, *package_path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _resolve_worktree_state(root: Path) -> tuple[str, bool]:
    client = GitClient(root)
    try:
        head = client.head()
    except GitCommandError as exc:
        raise _error(
            "engine_head_unresolvable",
            f"Unable to resolve the engine repository HEAD at {root}: {exc}",
        ) from exc
    try:
        modified, staged, untracked = client.porcelain()
    except GitCommandError as exc:
        raise _error(
            "engine_worktree_status_unresolvable",
            f"Unable to resolve the engine worktree status at {root}: {exc}",
        ) from exc
    return head, not (modified or staged or untracked)


def resolve_engine_provenance() -> CanonicalEngineProvenance:
    """Resolve the running engine's provenance, or fail closed.

    Called on every governed prompt render and every governed agent run, independent of whether
    any verification bundle is selected.
    """
    package_path = _package_path()
    distribution = _load_distribution()
    install_mode = _classify_install_mode(distribution)
    version = _resolve_version(distribution)

    root = _engine_worktree_root(package_path)
    if root is None:
        if install_mode == "editable":
            raise _error(
                "engine_editable_without_worktree",
                f"The engine is installed editable from {package_path}, which is not inside a "
                "Git worktree, so its provenance cannot be established",
            )
        head, worktree_clean = _NO_ENGINE_WORKTREE_HEAD, True
    else:
        head, worktree_clean = _resolve_worktree_state(root)

    if install_mode == "editable" and not worktree_clean:
        raise _error(
            "engine_editable_worktree_dirty",
            f"The engine worktree at {root} has uncommitted changes and the engine is installed "
            "editable; governed verification evidence must never be produced by uncommitted "
            "engine code",
        )

    return CanonicalEngineProvenance(
        engine_version=version,
        engine_head=head,
        engine_worktree_clean=worktree_clean,
        engine_install_mode=install_mode,
        engine_package_path=package_path.as_posix(),
    )
