"""Contract Skills (`SKILL_CONTRACTS.md` §3).

These Skills read stage contracts and the stage registry, and judge a change set against the
contract's declared scope. Nothing here mutates anything: the whole family is read-only, so no
retry classification beyond `NOT_APPLICABLE` ever arises.

Parsing is deliberately tolerant of Markdown formatting and strict about meaning, matching this
project's existing conservative-parsing principle (`docs/DECISION_LOG.md`, "Milestone 1"): a
table cell may be padded, bolded, or backticked without changing the parse, but a *missing*
required field is an error rather than a silently empty default. A contract whose metadata
cannot be read is never treated as a contract with no restrictions.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fnmatch import fnmatchcase
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentos_workflow.config.schema import canonical_repository_relative_path
from agentos_workflow.skills import FailureKind, RetryClassification, SkillResult, failure, success

__all__ = [
    "ContractHash",
    "PathViolation",
    "ScopeVerdict",
    "StageMetadata",
    "calculate_contract_hash",
    "detect_future_stage_work",
    "locate_stage_contract",
    "parse_stage_metadata",
    "validate_allowed_paths",
    "validate_stage_ordering",
]

_STAGE_ID_RE = re.compile(r"[A-Z][A-Z0-9]{1,15}-[0-9]{1,4}")
_MAX_CONTRACT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class StageMetadata:
    stage_id: str
    title: str
    role: str
    branch: str
    commit_message: str
    report_path: str


@dataclass(frozen=True)
class ContractHash:
    stage_id: str
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class PathViolation:
    path: str
    reason: str


@dataclass(frozen=True)
class ScopeVerdict:
    passed: bool
    violations: tuple[PathViolation, ...]


# --------------------------------------------------------------------------------------------
# Shared parsing helpers
# --------------------------------------------------------------------------------------------


def _clean_cell(cell: str) -> str:
    """Strip Markdown emphasis and code fencing from a table cell, leaving its text.

    Contracts write the same value as `**Branch**`, `` `branch` ``, or bare text depending on
    the column, and all three mean the same branch.
    """
    text = cell.strip()
    text = text.strip("|").strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text.strip()


def _table_rows(text: str) -> list[list[str]]:
    """Extract every Markdown table row as a list of cleaned cells.

    Separator rows (`|---|---|`) are dropped. A line that merely contains a `|` is not a table
    row unless it starts with one, so prose mentioning a pipe is not misparsed.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [_clean_cell(cell) for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        rows.append(cells)
    return rows


def _read_contract_text(skill: str, path: Path) -> SkillResult[str]:
    """Read a contract file with a size ceiling and no symlink following at the final component."""
    try:
        if path.is_symlink():
            return failure(
                skill,
                FailureKind.UNSAFE_INPUT,
                f"{path} is a symlink; contracts must be regular files",
                retry_classification=RetryClassification.NON_RETRYABLE,
            )
        if not path.is_file():
            return failure(skill, FailureKind.NOT_FOUND, f"{path} is not a regular file")
        size = path.stat().st_size
        if size > _MAX_CONTRACT_BYTES:
            return failure(
                skill,
                FailureKind.UNSAFE_INPUT,
                f"{path} is {size} bytes, over the {_MAX_CONTRACT_BYTES}-byte contract ceiling",
            )
        return success(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        return failure(skill, FailureKind.MALFORMED_OUTPUT, f"{path} is not valid UTF-8: {exc}")
    except OSError as exc:
        return failure(skill, FailureKind.IO_ERROR, f"could not read {path}: {exc}")


def _validate_stage_id(skill: str, stage_id: str) -> SkillResult[Any] | None:
    if not _STAGE_ID_RE.fullmatch(stage_id):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"stage_id={stage_id!r} is not a well-formed stage identifier",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return None


# --------------------------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------------------------


def locate_stage_contract(*, stage_id: str, contract_directory: Path) -> SkillResult[Path]:
    """Resolve the contract file for `stage_id` inside `contract_directory`.

    The stage ID is validated against a strict pattern *before* it is joined to a path, so a
    caller-supplied `../../etc/passwd` is rejected as a malformed stage ID rather than
    normalized into a traversal. The resolved path is then independently re-checked to be inside
    the contract directory, which also catches a symlinked contract pointing outside the tree.
    """
    skill = "locate_stage_contract"
    if problem := _validate_stage_id(skill, stage_id):
        return problem
    try:
        root = contract_directory.resolve(strict=True)
    except OSError as exc:
        return failure(skill, FailureKind.NOT_FOUND, f"contract directory unusable: {exc}")
    if not root.is_dir():
        return failure(skill, FailureKind.NOT_FOUND, f"{root} is not a directory")
    candidate = root / f"{stage_id}.md"
    if not candidate.is_file():
        return failure(skill, FailureKind.NOT_FOUND, f"no contract file for {stage_id} in {root}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        return failure(skill, FailureKind.IO_ERROR, f"could not resolve {candidate}: {exc}")
    if not resolved.is_relative_to(root):
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"contract for {stage_id} resolves outside {root}",
            retry_classification=RetryClassification.NON_RETRYABLE,
        )
    return success(resolved)


def parse_stage_metadata(contract_file: Path) -> SkillResult[StageMetadata]:
    """Parse a stage contract's metadata table into a typed record.

    The `Stage` cell carries both the ID and the role as `AUTO-003 · Role: Engine implementation
    session`; both halves are extracted rather than storing the raw cell, so a caller never has
    to re-parse. A missing required field fails rather than defaulting — an empty `Branch` would
    otherwise silently become "no branch restriction".
    """
    skill = "parse_stage_metadata"
    text_result = _read_contract_text(skill, contract_file)
    if not text_result.ok or text_result.value is None:
        return SkillResult(ok=False, error=text_result.error)
    text = text_result.value
    fields: dict[str, str] = {}
    for cells in _table_rows(text):
        if len(cells) == 2 and cells[0] and cells[0].lower() not in ("field", "value"):
            fields.setdefault(cells[0].lower(), cells[1])
    title_match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    if title_match is None:
        return failure(skill, FailureKind.MALFORMED_OUTPUT, "contract has no level-1 heading")
    heading = title_match.group(1).strip()

    stage_cell = fields.get("stage", "")
    stage_match = _STAGE_ID_RE.search(stage_cell) or _STAGE_ID_RE.search(heading)
    if stage_match is None:
        return failure(
            skill, FailureKind.MALFORMED_OUTPUT, "contract declares no recognizable stage ID"
        )
    stage_id = stage_match.group(0)
    role_match = re.search(r"Role:\s*(.+)$", stage_cell)
    role = role_match.group(1).strip() if role_match else ""

    missing = [name for name in ("branch", "commit message", "report") if not fields.get(name)]
    if missing:
        return failure(
            skill,
            FailureKind.MALFORMED_OUTPUT,
            f"contract is missing required metadata field(s): {', '.join(sorted(missing))}",
        )
    # The heading is `AUTO-003 — Deterministic repository and validation skills`; keep only the
    # human title, matching how the registry's own Title column is written.
    title = re.sub(rf"^{re.escape(stage_id)}\s*[—:-]\s*", "", heading).strip()
    return success(
        StageMetadata(
            stage_id=stage_id,
            title=title,
            role=role,
            branch=fields["branch"],
            commit_message=fields["commit message"],
            report_path=fields["report"],
        )
    )


def calculate_contract_hash(contract_file: Path) -> SkillResult[ContractHash]:
    """Hash a contract's exact bytes.

    This value is bound into the authorization record (`HUMAN_AUTHORIZATION_MODEL.md`), so any
    later mismatch invalidates the authorization. It therefore hashes raw bytes, never decoded
    or normalized text: a change that alters only line endings or trailing whitespace still
    changes the contract the Human Owner authorized and must still invalidate it.
    """
    skill = "calculate_contract_hash"
    try:
        if contract_file.is_symlink():
            return failure(
                skill,
                FailureKind.UNSAFE_INPUT,
                f"{contract_file} is a symlink; contracts must be regular files",
                retry_classification=RetryClassification.NON_RETRYABLE,
            )
        if not contract_file.is_file():
            return failure(skill, FailureKind.NOT_FOUND, f"{contract_file} is not a regular file")
        raw = contract_file.read_bytes()
    except OSError as exc:
        return failure(skill, FailureKind.IO_ERROR, f"could not read {contract_file}: {exc}")
    if len(raw) > _MAX_CONTRACT_BYTES:
        return failure(
            skill,
            FailureKind.UNSAFE_INPUT,
            f"{contract_file} is {len(raw)} bytes, over the contract ceiling",
        )
    stage_match = _STAGE_ID_RE.search(contract_file.stem)
    return success(
        ContractHash(
            stage_id=stage_match.group(0) if stage_match else contract_file.stem,
            path=contract_file.name,
            sha256=sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )
    )


def validate_stage_ordering(*, stage_id: str, stage_registry: Path) -> SkillResult[int]:
    """Confirm `stage_id` is the next stage eligible to run, per the registry's own ordering.

    Stages are strictly sequential (`stage-prompts/README.md`), so a stage may run only when
    every earlier stage in the registry table is in a terminal state. Returns the stage's
    1-based position on success.

    `COMPLETE` and `SUPERSEDED` are both terminal here — `STAGE_REGISTRY.md` §2 is explicit that
    a superseded stage is administratively closed, not pending, so it does not block its
    successor even though it was never successfully finished.
    """
    skill = "validate_stage_ordering"
    if problem := _validate_stage_id(skill, stage_id):
        return problem
    text_result = _read_contract_text(skill, stage_registry)
    if not text_result.ok or text_result.value is None:
        return SkillResult(ok=False, error=text_result.error)
    terminal = {"COMPLETE", "SUPERSEDED"}
    ordering: list[tuple[str, str]] = []
    for cells in _table_rows(text_result.value):
        if len(cells) < 4:
            continue
        candidate = cells[0]
        if not _STAGE_ID_RE.fullmatch(candidate):
            continue
        state = cells[3].upper()
        if any(existing == candidate for existing, _ in ordering):
            return failure(
                skill,
                FailureKind.MALFORMED_OUTPUT,
                f"registry lists {candidate} more than once",
            )
        ordering.append((candidate, state))
    if not ordering:
        return failure(
            skill, FailureKind.MALFORMED_OUTPUT, f"no registry table rows found in {stage_registry}"
        )
    position = next((index for index, (sid, _) in enumerate(ordering) if sid == stage_id), None)
    if position is None:
        return failure(skill, FailureKind.NOT_FOUND, f"{stage_id} is not listed in the registry")
    unfinished = [sid for sid, state in ordering[:position] if state not in terminal]
    if unfinished:
        return failure(
            skill,
            FailureKind.PRECONDITION,
            f"{stage_id} cannot run before earlier stage(s) reach a terminal state: "
            f"{', '.join(unfinished)}",
        )
    return success(position + 1)


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    """Match a canonical repository-relative path against canonical glob patterns.

    `fnmatchcase` is case-sensitive by design: on a case-insensitive filesystem a forbidden
    `docs/SECRET/**` must not be evadable by committing `docs/secret/x`, and matching
    case-sensitively means the *pattern author's* spelling is what governs. `**` is expanded to
    also match zero directories so `docs/**` covers `docs/x` as well as `docs/a/x`, which is
    what every contract in this program means by it.
    """
    for pattern in patterns:
        if fnmatchcase(path, pattern):
            return True
        if pattern.endswith("/**") and fnmatchcase(path, pattern[: -len("/**")]):
            return True
        if "/**/" in pattern and fnmatchcase(path, pattern.replace("/**/", "/", 1)):
            return True
    return False


def _canonical_or_none(path: str) -> str | None:
    """Canonicalize an observed path, refusing anything that escapes the repository root.

    Unicode is normalized to NFC first: a forbidden path and a decomposed spelling of the same
    filename are the same file on macOS, and comparing raw code points would let the decomposed
    form slip past a forbidden rule.
    """
    normalized = unicodedata.normalize("NFC", path)
    if "\x00" in normalized or normalized.startswith("/"):
        return None
    canonical = canonical_repository_relative_path(normalized)
    if not canonical or canonical.startswith(".."):
        return None
    return canonical


def validate_allowed_paths(
    *,
    changed_files: tuple[str, ...],
    allowed_paths: tuple[str, ...],
    forbidden_paths: tuple[str, ...],
) -> SkillResult[ScopeVerdict]:
    """Judge a change set against a contract's allowed and forbidden path patterns.

    Forbidden wins over allowed, unconditionally. Where the two overlap, the only safe reading of
    "forbidden" is that it is a prohibition rather than a default an `allowed` entry can
    outrank — treating an overlap as permission would let a broad `docs/**` allowance silently
    re-open a narrow `docs/secret/**` prohibition.

    A path matching *nothing* is a violation, not a pass: scope is an allowlist, so an
    unanticipated path is exactly the scope creep `SECURITY_MODEL.md` §7 requires be treated as
    a validation failure rather than a warning.
    """
    violations: list[PathViolation] = []
    for raw_path in changed_files:
        canonical = _canonical_or_none(raw_path)
        if canonical is None:
            violations.append(
                PathViolation(path=raw_path, reason="path is not a safe repository-relative path")
            )
            continue
        if _matches_any(canonical, forbidden_paths):
            violations.append(
                PathViolation(path=canonical, reason="matches a forbidden path pattern")
            )
            continue
        if not _matches_any(canonical, allowed_paths):
            violations.append(
                PathViolation(path=canonical, reason="matches no allowed path pattern")
            )
    return success(ScopeVerdict(passed=not violations, violations=tuple(violations)))


def detect_future_stage_work(
    *,
    changed_files: tuple[str, ...],
    current_stage_allowed_paths: tuple[str, ...],
    later_stage_paths: dict[str, tuple[str, ...]],
) -> SkillResult[ScopeVerdict]:
    """Flag changes that belong to a *later* stage's scope rather than this one's.

    This is a distinct check from `validate_allowed_paths`, not a duplicate of it: a path can
    sit inside the current stage's allowed patterns and still be recognizably a later stage's
    deliverable, which is how "completing a stage never authorizes its successor" gets enforced
    against an implementation session that runs ahead. A path claimed by the current stage's own
    patterns *and* a later stage's is reported, because that ambiguity is precisely what needs a
    human to look at it.
    """
    violations: list[PathViolation] = []
    for raw_path in changed_files:
        canonical = _canonical_or_none(raw_path)
        if canonical is None:
            violations.append(
                PathViolation(path=raw_path, reason="path is not a safe repository-relative path")
            )
            continue
        claiming = sorted(
            stage
            for stage, patterns in later_stage_paths.items()
            if _matches_any(canonical, patterns)
        )
        if not claiming:
            continue
        if _matches_any(canonical, current_stage_allowed_paths):
            violations.append(
                PathViolation(
                    path=canonical,
                    reason=f"claimed by both this stage and later stage(s): {', '.join(claiming)}",
                )
            )
        else:
            violations.append(
                PathViolation(
                    path=canonical, reason=f"belongs to later stage(s): {', '.join(claiming)}"
                )
            )
    return success(ScopeVerdict(passed=not violations, violations=tuple(violations)))
