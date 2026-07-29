"""Root-confined path resolution (`ARCHITECTURE.md` §3; SC-06, SC-07, SC-08).

Every filesystem access the dashboard makes goes through `RepositoryRoot.resolve`. The
resolver takes a *repository-relative POSIX path* and returns an absolute path proven to lie
inside the repository root, or raises `PathRefusedError` naming the exact refusal reason. There
is no bypass: `files.py` has no other way to build a path, and nothing in this package accepts
an absolute path from a caller.

Three properties are structural rather than advisory:

* **No decoding happens here.** The resolver never percent-decodes, URL-decodes, or unescapes
  its input. `%2e%2e%2f` is an ordinary (almost certainly nonexistent) filename, not a
  traversal, so a future HTTP layer cannot smuggle `../` past this check by encoding it — and
  cannot rely on this layer to decode for it either.
* **The deny-list is checked twice**: once on the caller's normalized relative path, and again
  on the path the filesystem actually resolved to. A symlink inside the root pointing at
  `.git/config` is therefore denied by the second check even though its own name is innocuous.
* **Traversal is rejected lexically, before touching the filesystem**, so refusals do not
  depend on whether the target happens to exist.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from agentos_dashboard.core import DashboardError

__all__ = [
    "DENIED_COMPONENT_PATTERNS",
    "DENIED_PREFIXES",
    "PathRefusal",
    "PathRefusedError",
    "RepositoryRoot",
    "RepositoryRootError",
    "is_denied",
]


class PathRefusal(StrEnum):
    """Why a path was refused, at a granularity a caller (and a test) can branch on."""

    EMPTY = "empty"
    ABSOLUTE = "absolute"
    NUL_BYTE = "nul_byte"
    TRAVERSAL = "traversal"
    DENIED = "denied"
    OUTSIDE_ROOT = "outside_root"
    SYMLINK_ESCAPE = "symlink_escape"
    UNREADABLE = "unreadable"


class PathRefusedError(DashboardError):
    """A path was refused before any content was read."""

    def __init__(self, relative: str, refusal: PathRefusal, detail: str) -> None:
        super().__init__(f"{refusal.value}: {detail} ({relative!r})")
        self.relative = relative
        self.refusal = refusal
        self.detail = detail


class RepositoryRootError(DashboardError):
    """The configured repository root is not a usable directory."""


# `SECURITY_MODEL.md` SC-08 deny-list. `.env*` is matched against *every* path component, not
# just the final one, so `config/.env.local` and `.env.d/key` are both denied; this is
# deliberately broader than the literal file `.env`, because the most conservative reading wins
# for secret material (`SECURITY_MODEL.md` §1 puts any local secret out of bounds).
DENIED_COMPONENT_PATTERNS: tuple[str, ...] = (".env*",)

# Denied path prefixes, as component tuples. `.git` is reachable only through the Git adapter
# (`gitread.py`), which never opens a file; `data/agentos_dashboard` is the dashboard's own
# local store, which is never part of a snapshot of the repository.
DENIED_PREFIXES: tuple[tuple[str, ...], ...] = (
    (".git",),
    ("data", "agentos_dashboard"),
)


def is_denied(parts: tuple[str, ...]) -> bool:
    """True when a normalized relative path is on the SC-08 deny-list."""
    for component in parts:
        if any(fnmatch.fnmatch(component, pattern) for pattern in DENIED_COMPONENT_PATTERNS):
            return True
    # A nested `.git` (a submodule's, say) is denied at any depth, not only at the root.
    if ".git" in parts:
        return True
    return any(parts[: len(prefix)] == prefix for prefix in DENIED_PREFIXES)


def _normalize(relative: str) -> tuple[str, ...]:
    """Lexically normalize a caller-supplied repository-relative path.

    Raises `PathRefusedError` for everything that is not a plain relative path: empty input, a
    NUL byte, an absolute path, and any `..` component. `.` segments are dropped. No filesystem
    access occurs.
    """
    if not relative or not relative.strip():
        raise PathRefusedError(relative, PathRefusal.EMPTY, "empty path")
    if "\x00" in relative:
        raise PathRefusedError(relative, PathRefusal.NUL_BYTE, "NUL byte in path")
    if relative.startswith(("/", "\\")) or os.path.isabs(relative):
        raise PathRefusedError(relative, PathRefusal.ABSOLUTE, "absolute paths are never accepted")

    parts: list[str] = []
    for component in PurePosixPath(relative).parts:
        if component == ".":
            continue
        if component == "..":
            raise PathRefusedError(relative, PathRefusal.TRAVERSAL, "'..' component")
        parts.append(component)
    if not parts:
        raise PathRefusedError(relative, PathRefusal.EMPTY, "path normalizes to the root itself")
    return tuple(parts)


@dataclass(frozen=True)
class RepositoryRoot:
    """The one directory the dashboard may read, resolved once at construction."""

    path: Path

    @classmethod
    def from_path(cls, path: Path | str) -> RepositoryRoot:
        """Build a root from a directory that must already exist.

        The root is fully resolved here — including symlinks — so every later containment check
        compares real paths against a real path rather than two differently-spelled versions of
        the same directory.
        """
        candidate = Path(path)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise RepositoryRootError(f"repository root is not accessible: {candidate}") from exc
        if not resolved.is_dir():
            raise RepositoryRootError(f"repository root is not a directory: {resolved}")
        return cls(path=resolved)

    def resolve(self, relative: str) -> Path:
        """Resolve `relative` inside this root, or raise `PathRefusedError`.

        The returned path is absolute and proven to be inside the root. It is not proven to
        exist: existence is `files.py`'s concern, and refusing a nonexistent path here would
        leak which files exist through the choice of exception.
        """
        parts = _normalize(relative)
        if is_denied(parts):
            raise PathRefusedError(relative, PathRefusal.DENIED, "path is on the deny-list")

        candidate = self.path.joinpath(*parts)
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            # A symlink loop surfaces as `RuntimeError("Symlink loop from ...")` from
            # `pathlib` on CPython 3.11, not as the `OSError(ELOOP)` the underlying syscall
            # raised, so both have to be caught for SC-34 to hold.
            raise PathRefusedError(relative, PathRefusal.UNREADABLE, str(exc)) from exc

        if not resolved.is_relative_to(self.path):
            refusal = (
                PathRefusal.SYMLINK_ESCAPE
                if self._contains_symlink(candidate)
                else PathRefusal.OUTSIDE_ROOT
            )
            raise PathRefusedError(relative, refusal, f"resolves outside the root: {resolved}")

        # Second deny-list check, against what the filesystem actually pointed at: a symlink
        # whose own name is innocuous cannot be used to reach `.git/**` or `.env*`.
        if is_denied(resolved.relative_to(self.path).parts):
            raise PathRefusedError(
                relative, PathRefusal.DENIED, "resolved target is on the deny-list"
            )
        return resolved

    def relative_of(self, resolved: Path) -> str:
        """The repository-relative POSIX form of a path this root already resolved."""
        return resolved.relative_to(self.path).as_posix()

    def _contains_symlink(self, candidate: Path) -> bool:
        """True when any component of `candidate` at or below the root is a symlink.

        Used only to choose between two refusal reasons, never to decide *whether* to refuse —
        containment is decided by the resolved path alone, so a race here cannot widen access.
        """
        current = self.path
        for component in candidate.relative_to(self.path).parts:
            current = current / component
            if current.is_symlink():
                return True
        return False
