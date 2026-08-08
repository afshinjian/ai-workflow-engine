"""Shared, tolerant text-extraction helpers for `services.board`/`services.tasks` (DASH-005.md
DR-021/DR-030..033).

`docs/TASK_QUEUE.md` prose has no uniform per-field structure (`parsing.task_queue`'s own module
docstring already says so, and defers finer-grained extraction to "a later stage that needs
it" — this is that stage). Nothing here invents structure the prose does not have: every
function is a best-effort, clearly-labeled scan for a recognizable pattern (a task id, a
backtick-quoted path, a backtick-quoted hex token, a coarse clause boundary), never a semantic
parse. Every extracted fact is cited to the task record's own `(source, line)` — the heading
line the fact was recorded under — rather than a fabricated sub-line position: `detail_text` has
already been `.strip()`-ped of a variable, unrecorded amount of leading whitespace by
`parsing.task_queue`, so a precise per-clause line number would be false precision. This matches
the granularity `services.consistency.ConsistencyFinding` already uses (file-level `sources`,
no line field at all).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentos_dashboard.core.files import FileAccessError, stat_file
from agentos_dashboard.core.gitread import GitReadError, resolve_revision
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.parsing._common import TASK_ID

__all__ = [
    "DocRef",
    "ResolvedCommit",
    "extract_commit_references",
    "extract_doc_references",
    "extract_task_references",
    "split_into_clauses",
]

_DOC_PATH = re.compile(r"[A-Za-z0-9_./-]+\.(?:md|ya?ml)\b")
_COMMIT_TOKEN = re.compile(r"`([0-9a-f]{7,40})`")
# A coarse clause boundary: end-of-sentence/semicolon punctuation followed by whitespace and
# what looks like the start of a new clause. Not sentence-aware NLP — a deliberately simple
# proxy good enough to break narrative prose into checklist-sized, citable spans.
_CLAUSE_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z0-9`*(])")


def split_into_clauses(text: str) -> tuple[str, ...]:
    return tuple(clause.strip() for clause in _CLAUSE_SPLIT.split(text) if clause.strip())


def extract_task_references(text: str, *, exclude: str) -> tuple[str, ...]:
    """Other task ids mentioned in `text`, in first-occurrence order, `exclude`d task omitted.

    Labeled "referenced tasks" rather than "dependencies" everywhere this is displayed: the
    queue prose records no structured dependency field, so this is only every other task id the
    prose happens to name (DR-021's closest honest proxy for "dependencies").
    """
    seen: list[str] = []
    for match in TASK_ID.finditer(text):
        task_id = match.group(1).upper()
        if task_id == exclude or task_id in seen:
            continue
        seen.append(task_id)
    return tuple(seen)


@dataclass(frozen=True)
class DocRef:
    """A repository-relative document path named in prose, and whether it actually exists."""

    path: str
    exists: bool


def extract_doc_references(root: RepositoryRoot, text: str) -> tuple[DocRef, ...]:
    """Doc-like paths (`*.md`/`*.yaml`/`*.yml`) named in `text`, existence-checked (DR-033).

    A path that resolves outside the confined root or is otherwise refused is silently excluded
    rather than surfaced as "missing": it was never a real repository reference to begin with
    (most commonly a false-positive token that merely looks path-shaped), and `RepositoryRoot`
    is the sole authority on what counts as a reachable repository path.
    """
    refs: list[DocRef] = []
    seen: set[str] = set()
    for match in _DOC_PATH.finditer(text):
        candidate = match.group(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            stat_file(root, candidate)
        except FileAccessError:
            refs.append(DocRef(path=candidate, exists=False))
        except PathRefusedError:
            continue
        else:
            refs.append(DocRef(path=candidate, exists=True))
    return tuple(refs)


@dataclass(frozen=True)
class ResolvedCommit:
    """One backtick-quoted hex token from prose, resolved against Git (DR-032, TR-07)."""

    token: str
    resolved_sha: str | None
    resolvable: bool


def extract_commit_references(root: RepositoryRoot, text: str) -> tuple[ResolvedCommit, ...]:
    """Backtick-quoted hex tokens in `text`, each resolved against Git (mirrors
    `services.consistency._check_doc_named_commits`'s technique, applied to task-queue prose
    instead of the decision log)."""
    refs: list[ResolvedCommit] = []
    seen: set[str] = set()
    for match in _COMMIT_TOKEN.finditer(text):
        token = match.group(1)
        if token in seen:
            continue
        seen.add(token)
        try:
            sha = resolve_revision(root.path, token)
        except GitReadError:
            refs.append(ResolvedCommit(token=token, resolved_sha=None, resolvable=False))
        else:
            refs.append(ResolvedCommit(token=token, resolved_sha=sha, resolvable=True))
    return tuple(refs)
