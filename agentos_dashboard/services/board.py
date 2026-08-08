"""DR-020..023 (`PRODUCT_SPEC.md`): the workflow board — queue lanes for the three
`docs/TASK_QUEUE.md` statuses, the engine's coded workflow-stage strip (`services.workflow`,
display-only), the ORCH program lane (`parsing.orchestration`, TR-09), and an "unclassified"
lane plus finding for any `## <ID>` heading whose Status field DASH-003's task-queue parser did
not recognize (DR-022).

Built from the tolerant parsers and consistency-finding types DASH-003/DASH-004 already ship;
the one thing this module computes itself is unclassified-record identity (below), which
`parsing.task_queue.parse_task_records` intentionally discards once it decides not to trust a
section's Status field (it only keeps an aggregate skipped-count note). Rather than duplicating
that parser's private status-recognition regex here — which would risk the two disagreeing about
what "unclassified" means — this module treats "recognized by `parse_task_records`" as the
single source of truth: a `## <ID>` heading (found via the same public `TASK_ID` regex
`parsing._common` already exports) whose id is not in that parser's result set is unclassified,
full stop, never a second independent status judgement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.parsing._common import TASK_ID
from agentos_dashboard.parsing.models import TaskStatus
from agentos_dashboard.parsing.orchestration import OrchestrationStage, parse_implementation_state
from agentos_dashboard.parsing.task_queue import TaskRecord, parse_task_records
from agentos_dashboard.services._prose import (
    DocRef,
    extract_doc_references,
    extract_task_references,
)
from agentos_dashboard.services.consistency import (
    IMPLEMENTATION_STATE_PATH,
    TASK_QUEUE_PATH,
    ConsistencyFinding,
    ConsistencySeverity,
)
from agentos_dashboard.services.workflow import (
    WORKFLOW_STAGES,
    QueueTransition,
    compute_queue_transitions,
)

__all__ = [
    "BoardCard",
    "BoardData",
    "EvidenceState",
    "UnclassifiedCard",
    "build_board",
]

_HEADING = re.compile(r"^(#{2,6})[ \t]+(.*)$", re.MULTILINE)
# Purely informational (never a classification decision, see module docstring): a whole-line
# "Status:" field with any value, for display only. Requires the colon and a line start, unlike
# `parsing.task_queue`'s stricter `_STATUS_FIELD`, so it also surfaces an unrecognized value
# (e.g. "Status: Blocked") rather than only a missing field.
_LOOSE_STATUS = re.compile(r"^\s*(?:\*\*)?Status(?:\*\*)?:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE)
_TITLE_PREFIX = re.compile(r"^[\s—-]+")
_STATUS_LINE = re.compile(r"^(?:\*\*)?Status:?(?:\*\*)?\s*\S", re.IGNORECASE)


class EvidenceState(StrEnum):
    """DR-021's card-level "evidence-completeness" signal (`UI_SPEC.md` Badge Vocabulary)."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BoardCard:
    """DR-021: one task-queue record's card fields."""

    task_id: str
    title: str
    program: str
    status: TaskStatus
    referenced_tasks: tuple[str, ...]
    evidence: EvidenceState
    evidence_notes: tuple[str, ...]
    transition: QueueTransition
    source: str
    line: int


@dataclass(frozen=True)
class UnclassifiedCard:
    """DR-022: one `## <ID>` heading whose Status field was not recognized."""

    task_id: str
    title: str
    raw_status: str | None
    source: str
    line: int


@dataclass(frozen=True)
class BoardData:
    planned: tuple[BoardCard, ...]
    current: tuple[BoardCard, ...]
    done: tuple[BoardCard, ...]
    unclassified: tuple[UnclassifiedCard, ...]
    orch_stages: tuple[OrchestrationStage, ...]
    workflow_stages: tuple[str, ...]
    findings: tuple[ConsistencyFinding, ...]


def _read_or_none(root: RepositoryRoot, relative: str) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError):
        return None


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _title_from_detail(detail_text: str, fallback: str) -> str:
    """The heading's own "— Title" suffix, when the heading line carried one.

    When it did not (`## FIX-003` with no title text before the line break), `detail_text`'s
    first line is instead whatever the section's own next content line is — most commonly the
    `Status:` field — which must never be mistaken for a title.
    """
    first_line = detail_text.strip().splitlines()[0] if detail_text.strip() else ""
    title = _TITLE_PREFIX.sub("", first_line).strip()
    if not title or _STATUS_LINE.match(title):
        return fallback
    return title


def _evidence_state(doc_refs: tuple[DocRef, ...]) -> tuple[EvidenceState, tuple[str, ...]]:
    if not doc_refs:
        return EvidenceState.UNKNOWN, ("no report/document reference found in queue prose",)
    missing = tuple(ref.path for ref in doc_refs if not ref.exists)
    if missing:
        return EvidenceState.FAIL, tuple(f"referenced but missing: {path}" for path in missing)
    return EvidenceState.PASS, tuple(f"verified present: {ref.path}" for ref in doc_refs)


def _build_card(root: RepositoryRoot, record: TaskRecord, transition: QueueTransition) -> BoardCard:
    doc_refs = extract_doc_references(root, record.detail_text)
    evidence, notes = _evidence_state(doc_refs)
    return BoardCard(
        task_id=record.task_id,
        title=_title_from_detail(record.detail_text, record.task_id),
        program=record.task_id.split("-", 1)[0],
        status=record.status,
        referenced_tasks=extract_task_references(record.detail_text, exclude=record.task_id),
        evidence=evidence,
        evidence_notes=notes,
        transition=transition,
        source=record.source,
        line=record.line,
    )


def _unclassified_records(
    text: str, source: str, recognized_ids: frozenset[str]
) -> tuple[UnclassifiedCard, ...]:
    headings = list(_HEADING.finditer(text))
    cards: list[UnclassifiedCard] = []
    seen: set[str] = set()
    for index, heading in enumerate(headings):
        id_match = TASK_ID.search(heading.group(2))
        if id_match is None:
            continue
        task_id = id_match.group(1).upper()
        if task_id in recognized_ids or task_id in seen:
            continue
        seen.add(task_id)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end() : end]
        status_match = _LOOSE_STATUS.search(section[:500])
        cards.append(
            UnclassifiedCard(
                task_id=task_id,
                title=_title_from_detail(heading.group(2)[id_match.end() :], task_id),
                raw_status=status_match.group(1).strip() if status_match else None,
                source=source,
                line=_line_number(text, heading.start()),
            )
        )
    return tuple(cards)


def build_board(snapshot: RepositorySnapshot) -> BoardData:
    """Build one `BoardData` from `snapshot`'s root.

    Never raises for repository content, mirroring `api.overview.build_overview`'s SC-34
    discipline: a missing or unparsable `docs/TASK_QUEUE.md` degrades to empty lanes plus a
    `document_missing`/`parse_failed` finding, never an exception a page render would surface as
    a 500.
    """
    root = snapshot.root
    findings: list[ConsistencyFinding] = []

    # The ORCH program lane (DR-020: "visually separated") is read independently of the
    # task-queue lanes below: it is a different program's data source
    # (`implementation-state.yaml`, TR-09) and must render even when `docs/TASK_QUEUE.md` itself
    # is missing or unparsable, exactly as the two lanes are visually separated on the page.
    orch_text = _read_or_none(root, IMPLEMENTATION_STATE_PATH)
    orch_view = (
        parse_implementation_state(orch_text, IMPLEMENTATION_STATE_PATH).value
        if orch_text is not None
        else None
    )
    orch_stages = orch_view.stages if orch_view is not None else ()

    queue_text = _read_or_none(root, TASK_QUEUE_PATH)
    if queue_text is None:
        findings.append(
            ConsistencyFinding(
                rule="document_missing",
                severity=ConsistencySeverity.ERROR,
                message=f"{TASK_QUEUE_PATH} could not be read",
                sources=(TASK_QUEUE_PATH,),
            )
        )
        return BoardData(
            planned=(),
            current=(),
            done=(),
            unclassified=(),
            orch_stages=orch_stages,
            workflow_stages=WORKFLOW_STAGES,
            findings=tuple(findings),
        )

    parsed = parse_task_records(queue_text, TASK_QUEUE_PATH)
    records = parsed.value or ()
    if parsed.value is None:
        findings.append(
            ConsistencyFinding(
                rule="parse_failed",
                severity=ConsistencySeverity.ERROR,
                message=(
                    f"{TASK_QUEUE_PATH} could not be parsed: "
                    f"{'; '.join(parsed.notes) or 'no recognizable structure'}"
                ),
                sources=(TASK_QUEUE_PATH,),
            )
        )
    transitions = {t.task_id: t for t in compute_queue_transitions(records)}
    cards = [_build_card(root, record, transitions[record.task_id]) for record in records]

    unclassified = _unclassified_records(
        queue_text, TASK_QUEUE_PATH, frozenset(record.task_id for record in records)
    )
    if unclassified:
        findings.append(
            ConsistencyFinding(
                rule="unclassified_task_status",
                severity=ConsistencySeverity.WARNING,
                message=(
                    f"{len(unclassified)} task heading(s) in {TASK_QUEUE_PATH} have an "
                    f"unrecognized or missing Status field: "
                    f"{', '.join(card.task_id for card in unclassified)}"
                ),
                sources=(TASK_QUEUE_PATH,),
            )
        )

    return BoardData(
        planned=tuple(card for card in cards if card.status is TaskStatus.PLANNED),
        current=tuple(card for card in cards if card.status is TaskStatus.CURRENT),
        done=tuple(card for card in cards if card.status is TaskStatus.DONE),
        unclassified=unclassified,
        orch_stages=orch_stages,
        workflow_stages=WORKFLOW_STAGES,
        findings=tuple(findings),
    )
