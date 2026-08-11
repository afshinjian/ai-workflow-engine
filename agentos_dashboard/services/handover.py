"""DR-100..102 (`PRODUCT_SPEC.md`): the handover viewer.

Displays the handover pair (`handover/PROJECT_HANDOVER.md`, `handover/PROJECT_CHECKSUM.md`),
recomputes and compares the checksum manifest exactly as `workflowctl check-handover` defines it
(reusing the same size/digest reconciliation `services.consistency._check_handover_checksum`
already implements, applied here per-record rather than as findings-only, so a MISSING row
renders explicitly, DR-100), and raises a staleness warning when the narrative file is older than
the governance mirrors it summarizes (DR-101). The manifest refresh procedure (DR-102,
`OPEN_QUESTIONS.md` OD-D6) is presented as the manifest's own documented preamble prose, verbatim
— MVP deliberately has no refresh button.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos_dashboard.core.files import FileAccessError, digest_file, read_text, stat_file
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing.handover import parse_checksum_manifest
from agentos_dashboard.services.consistency import (
    CURRENT_TASK_PATH,
    HANDOVER_MANIFEST_PATH,
    PROJECT_STATE_PATH,
    REMAINING_TASKS_PATH,
    TASK_QUEUE_PATH,
    ConsistencyFinding,
    ConsistencySeverity,
)

__all__ = [
    "GOVERNANCE_MIRROR_PATHS",
    "HANDOVER_NARRATIVE_PATH",
    "HandoverData",
    "HandoverRecord",
    "build_handover_view",
]

HANDOVER_NARRATIVE_PATH = "handover/PROJECT_HANDOVER.md"

# DR-101's "the governance mirrors it summarizes" — the same task-queue/project-state documents
# `services.overview`/`services.consistency` already treat as this repository's governance record.
GOVERNANCE_MIRROR_PATHS: tuple[str, ...] = (
    PROJECT_STATE_PATH,
    TASK_QUEUE_PATH,
    CURRENT_TASK_PATH,
    REMAINING_TASKS_PATH,
)


@dataclass(frozen=True)
class HandoverRecord:
    """DR-100: one checksum-manifest row, reconciled against the real file. `exists=False` is a
    first-class MISSING state, not folded into a mismatch."""

    path: str
    claimed_size: int
    claimed_digest: str
    exists: bool
    actual_size: int | None
    actual_digest: str | None
    size_match: bool
    digest_match: bool
    source: str
    line: int


@dataclass(frozen=True)
class HandoverData:
    """PG-09's aggregate."""

    manifest_path: str
    manifest_instructions: str
    manifest_raw_text: str | None
    narrative_path: str
    narrative_text: str | None
    narrative_truncated: bool
    records: tuple[HandoverRecord, ...]
    narrative_mtime_ns: int | None
    newest_governance_mtime_ns: int | None
    newest_governance_path: str | None
    stale: bool
    findings: tuple[ConsistencyFinding, ...]


def _read_or_none(root: RepositoryRoot, relative: str) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError):
        return None


def _manifest_instructions(text: str) -> str:
    """The manifest's own preamble prose — everything before its first table row — verbatim."""
    table_start = text.find("\n|")
    return text[:table_start].strip() if table_start != -1 else text.strip()


def _reconcile_record(
    root: RepositoryRoot,
    path: str,
    claimed_size: int,
    claimed_digest: str,
    source: str,
    line: int,
) -> tuple[HandoverRecord, ConsistencyFinding | None]:
    try:
        facts = stat_file(root, path)
        actual_digest = digest_file(root, path)
    except (FileAccessError, PathRefusedError) as exc:
        return (
            HandoverRecord(
                path=path,
                claimed_size=claimed_size,
                claimed_digest=claimed_digest,
                exists=False,
                actual_size=None,
                actual_digest=None,
                size_match=False,
                digest_match=False,
                source=source,
                line=line,
            ),
            ConsistencyFinding(
                rule="handover_file_missing",
                severity=ConsistencySeverity.ERROR,
                message=f"{path} named in {HANDOVER_MANIFEST_PATH} could not be read: {exc}",
                sources=(HANDOVER_MANIFEST_PATH, path),
            ),
        )

    size_match = facts.size_bytes == claimed_size
    digest_match = actual_digest.startswith(claimed_digest)
    finding: ConsistencyFinding | None = None
    if not size_match:
        finding = ConsistencyFinding(
            rule="handover_size_mismatch",
            severity=ConsistencySeverity.ERROR,
            message=f"{path}: manifest size {claimed_size} != actual {facts.size_bytes}",
            sources=(HANDOVER_MANIFEST_PATH, path),
        )
    elif not digest_match:
        finding = ConsistencyFinding(
            rule="handover_checksum_mismatch",
            severity=ConsistencySeverity.ERROR,
            message=f"{path}: SHA-256 digest does not match {HANDOVER_MANIFEST_PATH}",
            sources=(HANDOVER_MANIFEST_PATH, path),
        )
    return (
        HandoverRecord(
            path=path,
            claimed_size=claimed_size,
            claimed_digest=claimed_digest,
            exists=True,
            actual_size=facts.size_bytes,
            actual_digest=actual_digest,
            size_match=size_match,
            digest_match=digest_match,
            source=source,
            line=line,
        ),
        finding,
    )


def build_handover_view(snapshot: RepositorySnapshot) -> HandoverData:
    """Build one `HandoverData` from `snapshot`'s root.

    Never raises for repository content, mirroring `services.consistency.run_consistency_checks`'s
    SC-34 discipline: a missing manifest or narrative degrades to `None`/empty plus a
    `document_missing` finding, never an exception a page render would surface as a 500.
    """
    root = snapshot.root
    findings: list[ConsistencyFinding] = []

    manifest_text = _read_or_none(root, HANDOVER_MANIFEST_PATH)
    instructions = ""
    records: list[HandoverRecord] = []
    if manifest_text is None:
        findings.append(
            ConsistencyFinding(
                rule="document_missing",
                severity=ConsistencySeverity.ERROR,
                message=f"{HANDOVER_MANIFEST_PATH} could not be read",
                sources=(HANDOVER_MANIFEST_PATH,),
            )
        )
    else:
        instructions = _manifest_instructions(manifest_text)
        parsed = parse_checksum_manifest(manifest_text, HANDOVER_MANIFEST_PATH)
        if parsed.value is None:
            findings.append(
                ConsistencyFinding(
                    rule="parse_failed",
                    severity=ConsistencySeverity.ERROR,
                    message=(
                        f"{HANDOVER_MANIFEST_PATH} could not be parsed: "
                        f"{'; '.join(parsed.notes) or 'no recognizable structure'}"
                    ),
                    sources=(HANDOVER_MANIFEST_PATH,),
                )
            )
        else:
            for manifest_record in parsed.value:
                record, finding = _reconcile_record(
                    root,
                    manifest_record.path,
                    manifest_record.size,
                    manifest_record.digest,
                    manifest_record.source,
                    manifest_record.line,
                )
                records.append(record)
                if finding is not None:
                    findings.append(finding)

    narrative_text: str | None = None
    narrative_truncated = False
    narrative_mtime: int | None = None
    try:
        narrative_read = read_text(root, HANDOVER_NARRATIVE_PATH)
        # SC-09: display-only copy — the checksum reconciliation above reads/digests each
        # manifest record's raw bytes independently, so redacting this narrative copy cannot
        # affect DR-100's checksum verification.
        narrative_text = redact_secrets(narrative_read.text)
        narrative_truncated = narrative_read.truncated
        narrative_mtime = stat_file(root, HANDOVER_NARRATIVE_PATH).mtime_ns
    except (FileAccessError, PathRefusedError):
        findings.append(
            ConsistencyFinding(
                rule="document_missing",
                severity=ConsistencySeverity.ERROR,
                message=f"{HANDOVER_NARRATIVE_PATH} could not be read",
                sources=(HANDOVER_NARRATIVE_PATH,),
            )
        )

    newest_governance_mtime: int | None = None
    newest_governance_path: str | None = None
    for path in GOVERNANCE_MIRROR_PATHS:
        try:
            facts = stat_file(root, path)
        except (FileAccessError, PathRefusedError):
            continue
        if newest_governance_mtime is None or facts.mtime_ns > newest_governance_mtime:
            newest_governance_mtime = facts.mtime_ns
            newest_governance_path = path

    stale = (
        narrative_mtime is not None
        and newest_governance_mtime is not None
        and narrative_mtime < newest_governance_mtime
    )
    if stale:
        findings.append(
            ConsistencyFinding(
                rule="handover_narrative_stale",
                severity=ConsistencySeverity.WARNING,
                message=(
                    f"{HANDOVER_NARRATIVE_PATH} is older than {newest_governance_path}, "
                    "which it summarizes"
                ),
                sources=(HANDOVER_NARRATIVE_PATH, newest_governance_path or ""),
            )
        )

    return HandoverData(
        manifest_path=HANDOVER_MANIFEST_PATH,
        manifest_instructions=redact_secrets(instructions),
        manifest_raw_text=(redact_secrets(manifest_text) if manifest_text is not None else None),
        narrative_path=HANDOVER_NARRATIVE_PATH,
        narrative_text=narrative_text,
        narrative_truncated=narrative_truncated,
        records=tuple(
            HandoverRecord(
                path=redact_secrets(record.path),
                claimed_size=record.claimed_size,
                claimed_digest=record.claimed_digest,
                exists=record.exists,
                actual_size=record.actual_size,
                actual_digest=record.actual_digest,
                size_match=record.size_match,
                digest_match=record.digest_match,
                source=record.source,
                line=record.line,
            )
            for record in records
        ),
        narrative_mtime_ns=narrative_mtime,
        newest_governance_mtime_ns=newest_governance_mtime,
        newest_governance_path=newest_governance_path,
        stale=stale,
        findings=tuple(
            ConsistencyFinding(
                rule=finding.rule,
                severity=finding.severity,
                message=redact_secrets(finding.message),
                sources=finding.sources,
            )
            for finding in findings
        ),
    )
