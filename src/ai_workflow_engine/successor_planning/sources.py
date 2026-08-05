"""Typed, additive readers for AUTO-015's authoritative evidence set.

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 4 items
1-3 and 5-7 (entry conditions), 4.1 (the required predecessor argument and its typed
failures), 8 (the authoritative evidence model: precedence 1-10, mirrors, contradictory
evidence, historical prose as inert data), 13 (the failure taxonomy) and 16.2
(canonicalization, ordering and locale independence).

What this module composes, and what it adds
-------------------------------------------
`docs/TASK_QUEUE.md` and every configured `STAGE_REGISTRY.md` are parsed by the existing
`governance.parser.parse_tasks` and `governance.registry.parse_registry` functions, and the
documented state-to-status mapping is the existing `REGISTRY_STATE_TO_TASK_STATUS`. None of
them is modified, wrapped in a corrected copy, or replaced by a second parser: section 23.4
records those modules as needing no change, and section 24 makes `governance/**` a forbidden
surface. What is added here is typed, additive readers for the four documents no existing
reader covers -- `DECISION_LOG.md`, `PROJECT_STATE.md`, completion reports and
`OPEN_QUESTIONS.md` -- plus the handover manifest, which composes the existing
`handover.manifest.parse_manifest` the same way.

One consequence of composing rather than replacing is worth stating plainly, because it is
visible in this repository's own documents: `governance.parser`'s task-identifier grammar
matches `AUTO-08` inside `GOV-AUTO-08`, so a stage recorded as `GOV-AUTO-08` in the Task Queue
appears here as `AUTO-08`. That is the existing parser's behaviour, this stage does not modify
it, and no local normalization is invented to paper over it -- a dependency naming
`GOV-AUTO-08` is therefore reported as unresolved against the queue rather than silently
matched to something the parser did not actually produce. Completion reports are bound to
their stage by filename instead, so `GOV-AUTO-08-completion-report.md` still resolves.

Fail-closed reading discipline
------------------------------
Every document is opened through the section 7.3 read discipline the snapshot module already
owns: no-follow open, symlink refusal, an explicit byte ceiling, strict UTF-8, CRLF folded to
LF with a bare CR refused, then NFC. Those failures propagate as the snapshot module's own
typed errors rather than being re-wrapped, so one section 13 code is never derived in two
places. This module adds exactly one new exception -- :class:`PredecessorError` -- carrying
the section 4.1 code that applies.

Historical prose is inert data
------------------------------
Quoted or historical directive-shaped text inside a decision-log entry, a completion report or
an open-question disposition is read as data and never re-interpreted as a live directive.
That is structural here rather than conventional: nothing this module returns is prose that
some later step executes. Every field is either a typed identifier, a typed status drawn from
a closed enum, a bounded scalar, or a digest.

What this module does not do
----------------------------
No eligibility verdict, no `lifecycle_status`, no recommendation, no rendering, no
publication. It reads, reconciles and reports; section 11 decides.
"""

import hashlib
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import field_validator, model_validator

from ai_workflow_engine.exceptions import (
    InvalidConfigurationError,
    ManifestParseError,
    WorkflowEngineError,
)
from ai_workflow_engine.governance.models import RegistryState, TaskStatus
from ai_workflow_engine.governance.parser import extract_fact, parse_tasks
from ai_workflow_engine.governance.registry import (
    REGISTRY_STATE_TO_TASK_STATUS,
    classify_state,
    parse_registry,
)
from ai_workflow_engine.governance.validators import (
    check_governance,
    check_registries,
    check_task_state,
)
from ai_workflow_engine.handover.manifest import parse_manifest
from ai_workflow_engine.handover.validators import check_handover
from ai_workflow_engine.models import EngineConfig, FactRule
from ai_workflow_engine.result import CheckResult, Status
from ai_workflow_engine.successor_planning.catalog import CandidateFinding, safe_message
from ai_workflow_engine.successor_planning.models import (
    FAILURE_SCOPES,
    MAX_MESSAGE_CHARS,
    MAX_PATH_CHARS,
    MAX_STATUS_CHARS,
    Candidate,
    EvidenceReference,
    FailureCode,
    PredecessorRegistryEvidence,
    PredecessorStatusReconciliation,
    RepositoryIdentity,
    SuccessorPlanningModel,
    _hex64,
    _int64,
    _relative_path,
    _require_sorted_unique,
    _scalar,
)
from ai_workflow_engine.successor_planning.snapshot import (
    AuthoritativeSourceError,
    InvalidInvocationError,
    _confine,
    normalize_evidence_text,
    read_evidence_bytes,
    sorted_directory_entries,
)

# --------------------------------------------------------------------------------------
# Document grammars
# --------------------------------------------------------------------------------------

# Section 4.1: the repository's canonical stage identifier grammar.
_PREDECESSOR_ID_RE = re.compile(r"AUTO-[0-9]{3}")

# `<STAGE_ID>-completion-report.md`, the naming section 8 item 3 and section 23.6 both use.
# The stage half is deliberately wider than the predecessor grammar so `GOV-AUTO-08`'s report
# is found; binding a report to a stage is not the same question as accepting a `--predecessor`.
_REPORT_NAME_RE = re.compile(
    r"(?P<stage>[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-[0-9]+)" r"-completion-report\.md"
)
_REPORT_TITLE_RE = re.compile(
    r"^#\s+(?P<title>(?P<stage>[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-[0-9]+)\b[^\n]*)",
    re.MULTILINE,
)
_REPORT_STATUS_RE = re.compile(
    r"^\|\s*(?:\*\*)?Status(?:\*\*)?\s*\|(?P<value>[^|]*)\|", re.MULTILINE
)

# The three dash characters this repository's headings actually use (em dash, en dash, hyphen),
# written as escapes so the pattern names the codepoints it means rather than relying on how
# they happen to render in a diff.
_DASH = r"[\u2014\u2013-]"

# `## 2026-08-04 - Human Owner accepted ...`, the only heading shape `DECISION_LOG.md` uses for
# an entry. A heading that is not dated is a document section (`## Format`), not a decision.
_DECISION_HEADING_RE = re.compile(
    r"^##\s+(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\s*" + _DASH + r"\s*(?P<title>\S.*?)\s*$",
    re.MULTILINE,
)

_SECTION_HEADING_RE = re.compile(r"^##\s+(?P<name>\S.*?)\s*$", re.MULTILINE)
_QUESTION_HEADING_RE = re.compile(
    r"^###\s+(?P<id>(?:OD|D)-[0-9]+)\s*(?:" + _DASH + r"\s*(?P<title>\S.*?))?\s*$",
    re.MULTILINE,
)
_DISPOSITION_RE = re.compile(
    r"^-\s+\*\*Disposition:?\*\*:?\s*(?P<status>Open|Resolved)\b(?P<rest>[^\n]*)", re.MULTILINE
)
# The register's Format section names the `Disposition` field, but three of its own already
# resolved entries state their answer as `- **Resolution (<date>):**` instead. Both are explicit
# statements by the entry itself, so both are recognized; nothing else is. In particular the
# enclosing `## Open`/`## Resolved` section heading is never treated as an answer, because this
# register genuinely holds entries dispositioned `Resolved` that still sit under `## Open`.
_RESOLUTION_RE = re.compile(r"^-\s+\*\*Resolution\b[^*\n]*\*\*:?(?P<rest>[^\n]*)", re.MULTILINE)
# `OPEN_QUESTIONS.md`'s own Format section defines exactly one phrase for a hard authorization
# gate: "Blocks stage X's authorization". Only that phrase is recognized -- the weaker
# "blocks/affects stage X's implementation" category explicitly does not gate authorization,
# and "Blocks nothing's authorization" names no stage and therefore matches nothing.
_AUTHORIZATION_BLOCK_RE = re.compile(
    r"[Bb]locks\s+(?:stage\s+)?`?(?P<stage>[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-[0-9]+)`?"
    r"(?:'s|\u2019s)?\s+\*{0,2}authorization"
)

_MAX_COMPLETION_REPORTS = 512


# --------------------------------------------------------------------------------------
# Typed, fail-closed errors
# --------------------------------------------------------------------------------------


class PredecessorError(WorkflowEngineError):
    """One of section 4.1's typed, whole-proposal predecessor failures.

    A single class carrying its code as data, rather than one subclass per code: section 4.1
    names nine codes plus section 4 item 1's `PREDECESSOR_INCOMPLETE`, all with the same scope
    and the same handling, and ten near-empty subclasses would carry no information the `code`
    attribute does not already carry exactly.
    """

    def __init__(self, code: FailureCode, message: str) -> None:
        self.code: FailureCode = code
        super().__init__(message)


# --------------------------------------------------------------------------------------
# Shared reading helpers
# --------------------------------------------------------------------------------------


def _cell(value: str, field: str) -> str:
    """Validate one verbatim document cell, permitting the empty cell.

    A table cell can legitimately be empty, and blanking it out or substituting a marker would
    rewrite the evidence. Everything else section 14.2 refuses is still refused.
    """
    return "" if value == "" else _scalar(value, field, MAX_STATUS_CHARS)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def read_document(root: Path, relative: str, label: str) -> tuple[str, EvidenceReference]:
    """Read one authoritative document and return its normalized text and its reference.

    The digest is over the normalized text, matching the snapshot protocol's own
    evidence-manifest digest (section 7.3 step 7), so the two never disagree about what a
    document hashed to. `size` is the on-disk byte size from the same `fstat` the read used.
    """
    try:
        _relative_path(relative, "authoritative source path")
    except ValueError as exc:
        raise InvalidInvocationError(
            f"The authoritative source {relative!r} is not a usable repository-relative path: "
            f"{exc}"
        ) from exc
    data, metadata = read_evidence_bytes(_confine(root, relative), label)
    text = normalize_evidence_text(data, label)
    reference = EvidenceReference(
        path=relative,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        size=metadata.st_size,
    )
    return text, reference


def _invalid(label: str, exc: Exception) -> AuthoritativeSourceError:
    return AuthoritativeSourceError(f"{label} failed structural validation: {safe_message(exc)}")


# --------------------------------------------------------------------------------------
# Section 8 items 1, 5, 6 -- task documents (composed `governance.parser`)
# --------------------------------------------------------------------------------------


class TaskStatusRecord(SuccessorPlanningModel):
    """One task's status as one document records it, verbatim."""

    task_id: str
    status: TaskStatus
    line: int

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, value: str) -> str:
        return _scalar(value, "task_id", MAX_STATUS_CHARS)

    @field_validator("line")
    @classmethod
    def _validate_line(cls, value: int) -> int:
        if value < 1:
            raise ValueError("line numbers start at 1")
        return _int64(value, "line")


class TaskDocument(SuccessorPlanningModel):
    """One parsed task-status document: the authoritative queue, or one of its mirrors."""

    reference: EvidenceReference
    records: list[TaskStatusRecord]

    def status_of(self, task_id: str) -> TaskStatus | None:
        for record in self.records:
            if record.task_id == task_id:
                return record.status
        return None

    def with_status(self, status: TaskStatus) -> list[str]:
        return sorted(
            {record.task_id for record in self.records if record.status == status},
            key=lambda value: value.encode("utf-8"),
        )


def read_task_document(root: Path, relative: str) -> TaskDocument:
    """Read one task-status document through the existing `parse_tasks` (section 8 items 1/6)."""
    label = f"The task document {relative!r}"
    text, reference = read_document(root, relative, label)
    try:
        records = [
            TaskStatusRecord(task_id=record.task_id, status=record.status, line=record.line)
            for record in parse_tasks(text, relative)
        ]
    except ValueError as exc:
        raise _invalid(label, exc) from exc
    return TaskDocument(reference=reference, records=records)


# --------------------------------------------------------------------------------------
# Section 8 item 2 -- the stage registries (composed `governance.registry`)
# --------------------------------------------------------------------------------------


class RegistryStageRecord(SuccessorPlanningModel):
    """One Registry-table row: the verbatim State cell plus its recognized state, if any.

    `state` is `None` when the cell is not one of the ten documented lifecycle states. The raw
    cell is kept either way, because an unrecognized state is evidence about the registry, not
    something to normalize away.
    """

    stage_id: str
    raw_state: str
    state: RegistryState | None
    line: int

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str) -> str:
        return _scalar(value, "stage_id", MAX_STATUS_CHARS)

    @field_validator("raw_state")
    @classmethod
    def _validate_raw_state(cls, value: str) -> str:
        return _cell(value, "registry State cell")

    @field_validator("line")
    @classmethod
    def _validate_line(cls, value: int) -> int:
        if value < 1:
            raise ValueError("line numbers start at 1")
        return _int64(value, "line")


class RegistryDocument(SuccessorPlanningModel):
    """One parsed stage registry (section 8 item 2)."""

    reference: EvidenceReference
    table_found: bool
    rows: list[RegistryStageRecord]

    def row_for(self, stage_id: str) -> RegistryStageRecord | None:
        for row in self.rows:
            if row.stage_id == stage_id:
                return row
        return None


def read_registry_document(root: Path, relative: str) -> RegistryDocument:
    """Read one stage registry through the existing `parse_registry`/`classify_state`."""
    label = f"The stage registry {relative!r}"
    text, reference = read_document(root, relative, label)
    parsed = parse_registry(text, relative)
    try:
        rows = [
            RegistryStageRecord(
                stage_id=row.stage_id,
                raw_state=row.raw_state,
                state=classify_state(row.raw_state),
                line=row.line,
            )
            for row in parsed.rows
        ]
    except ValueError as exc:
        raise _invalid(label, exc) from exc
    return RegistryDocument(reference=reference, table_found=parsed.table_found, rows=rows)


# --------------------------------------------------------------------------------------
# Section 8 item 4 -- the decision log
# --------------------------------------------------------------------------------------


class DecisionLogEntry(SuccessorPlanningModel):
    """One append-only decision-log entry heading, read as inert data.

    The entry's body is deliberately not carried: section 8 makes the decision log
    authoritative for rationale, and section 14 forbids repository prose from ever becoming
    directive text. A dated heading and a line number are enough to cite an entry; quoting its
    body would move untrusted prose one step closer to a rendered surface for no gain here.
    """

    date: str
    title: str
    line: int

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        _scalar(value, "decision date", MAX_STATUS_CHARS)
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ValueError("decision date must be an ISO-8601 calendar date")
        return value

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "decision title", MAX_MESSAGE_CHARS)

    @field_validator("line")
    @classmethod
    def _validate_line(cls, value: int) -> int:
        if value < 1:
            raise ValueError("line numbers start at 1")
        return _int64(value, "line")


class DecisionLogDocument(SuccessorPlanningModel):
    """`docs/DECISION_LOG.md` as typed entries (section 8 item 4)."""

    reference: EvidenceReference
    entries: list[DecisionLogEntry]


def read_decision_log(root: Path, relative: str) -> DecisionLogDocument:
    """Read `DECISION_LOG.md`'s dated entry headings (section 8 item 4).

    Conservative by construction, matching this repository's own parsing principle: only a
    heading of the documented `## <ISO date> — <title>` shape is an entry. An undated `##`
    heading is document structure, not a decision, and is not guessed at.
    """
    label = f"The decision log {relative!r}"
    text, reference = read_document(root, relative, label)
    try:
        entries = [
            DecisionLogEntry(
                date=match.group("date"),
                title=match.group("title"),
                line=_line_number(text, match.start()),
            )
            for match in _DECISION_HEADING_RE.finditer(text)
        ]
    except ValueError as exc:
        raise _invalid(label, exc) from exc
    return DecisionLogDocument(reference=reference, entries=entries)


# --------------------------------------------------------------------------------------
# Section 8 item 5 -- project state
# --------------------------------------------------------------------------------------


class DocumentFact(SuccessorPlanningModel):
    """One `governance.facts` fact as this document states it, or `None` if it is absent."""

    name: str
    value: str | None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _scalar(value, "fact name", MAX_STATUS_CHARS)

    @field_validator("value")
    @classmethod
    def _validate_value(cls, value: str | None) -> str | None:
        return None if value is None else _scalar(value, "fact value", MAX_STATUS_CHARS)


class ProjectStateDocument(SuccessorPlanningModel):
    """`docs/PROJECT_STATE.md`: a prose mirror plus its `governance.facts` values.

    Section 8 item 5 makes this document a mirror and a fact source and *never* an independent
    status source, so its task records are carried for visibility only and are not reconciled
    against the queue by :func:`reconcile_mirrors`, which section 13 scopes to
    `current_task.md`/`remaining_tasks.md`.
    """

    reference: EvidenceReference
    facts: list[DocumentFact]
    records: list[TaskStatusRecord]


def read_project_state(
    root: Path, relative: str, facts: Sequence[FactRule] = ()
) -> ProjectStateDocument:
    """Read `PROJECT_STATE.md`'s facts and task prose (section 8 item 5).

    `facts` are the configured `governance.facts` rules; only the rules that name this document
    are evaluated, and each is evaluated with the existing `extract_fact`, so a fact means here
    exactly what `workflowctl check-governance` already means by it.
    """
    label = f"The project state document {relative!r}"
    text, reference = read_document(root, relative, label)
    try:
        extracted = [
            DocumentFact(name=rule.name, value=extract_fact(text, rule.pattern, rule.group))
            for rule in facts
            if relative in rule.paths
        ]
        records = [
            TaskStatusRecord(task_id=record.task_id, status=record.status, line=record.line)
            for record in parse_tasks(text, relative)
        ]
    except ValueError as exc:
        raise _invalid(label, exc) from exc
    return ProjectStateDocument(reference=reference, facts=extracted, records=records)


# --------------------------------------------------------------------------------------
# Section 11 -- open questions
# --------------------------------------------------------------------------------------


class OpenQuestion(SuccessorPlanningModel):
    """One `OPEN_QUESTIONS.md` entry, with its own stated disposition.

    `status` is the entry's own `**Disposition:**` word, not the section it happens to sit
    under: this repository's register genuinely holds entries dispositioned `Resolved` that
    have not yet been moved out of the `Open` section, and trusting the section heading over
    the entry's own statement would misreport them. `section` is recorded alongside so the
    disagreement stays visible rather than being silently resolved.

    `blocks_authorization_of` holds only stages named by the register's own documented hard-gate
    phrase. The weaker "blocks/affects implementation" category is deliberately not collected:
    section 11 draws its eligibility line on exactly that distinction.
    """

    question_id: str
    title: str
    section: str
    status: Literal["Open", "Resolved"]
    disposition: str
    blocks_authorization_of: list[str]
    line: int

    @field_validator("question_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        _scalar(value, "question_id", MAX_STATUS_CHARS)
        if re.fullmatch(r"(?:OD|D)-[0-9]+", value) is None:
            raise ValueError("question_id must match ^(OD|D)-[0-9]+$")
        return value

    @field_validator("title", "section")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "open-question heading", MAX_MESSAGE_CHARS)

    @field_validator("disposition")
    @classmethod
    def _validate_disposition(cls, value: str) -> str:
        return _scalar(value, "disposition", MAX_MESSAGE_CHARS)

    @field_validator("blocks_authorization_of")
    @classmethod
    def _validate_blocked(cls, value: list[str]) -> list[str]:
        for stage in value:
            _scalar(stage, "blocked stage", MAX_STATUS_CHARS)
        _require_sorted_unique(value, "blocks_authorization_of", "stage id")
        return value

    @field_validator("line")
    @classmethod
    def _validate_line(cls, value: int) -> int:
        if value < 1:
            raise ValueError("line numbers start at 1")
        return _int64(value, "line")


class OpenQuestionsDocument(SuccessorPlanningModel):
    """`docs/workflow-automation/OPEN_QUESTIONS.md` as typed entries."""

    reference: EvidenceReference
    questions: list[OpenQuestion]

    def question(self, question_id: str) -> OpenQuestion | None:
        for entry in self.questions:
            if entry.question_id == question_id:
                return entry
        return None


def _enclosing_section(sections: Sequence[tuple[int, str]], offset: int) -> str:
    name = "(none)"
    for start, heading in sections:
        if start > offset:
            break
        name = heading
    return name


def read_open_questions(root: Path, relative: str) -> OpenQuestionsDocument:
    """Read the owner-decision register (`OD-#`/`D-#`) as typed entries.

    An entry with neither a `**Disposition:**` nor a `**Resolution (...):**` line is read as
    `Open`: the register's own format makes that line the entry's answer, and the absence of an
    answer is not evidence that a question is settled. That is the fail-closed direction, and it
    is also why the `## Open`/`## Resolved` section heading is never used as the answer -- it is
    recorded in `section` so a disagreement between the two stays visible instead.
    """
    label = f"The open-questions register {relative!r}"
    text, reference = read_document(root, relative, label)
    sections = [
        (match.start(), match.group("name")) for match in _SECTION_HEADING_RE.finditer(text)
    ]
    headings = list(_QUESTION_HEADING_RE.finditer(text))
    questions: list[OpenQuestion] = []
    try:
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            body = text[heading.end() : end]
            disposition = _DISPOSITION_RE.search(body)
            resolution = _RESOLUTION_RE.search(body)
            status: Literal["Open", "Resolved"] = "Open"
            statement = "(no disposition recorded)"
            if disposition is not None:
                status = "Resolved" if disposition.group("status") == "Resolved" else "Open"
                statement = safe_message(disposition.group(0))
            elif resolution is not None:
                status = "Resolved"
                statement = safe_message(resolution.group(0))
            blocked = sorted(
                {match.group("stage") for match in _AUTHORIZATION_BLOCK_RE.finditer(body)},
                key=lambda value: value.encode("utf-8"),
            )
            questions.append(
                OpenQuestion(
                    question_id=heading.group("id"),
                    title=safe_message(heading.group("title") or heading.group("id")),
                    section=safe_message(_enclosing_section(sections, heading.start())),
                    status=status,
                    disposition=statement,
                    blocks_authorization_of=blocked,
                    line=_line_number(text, heading.start()),
                )
            )
    except ValueError as exc:
        raise _invalid(label, exc) from exc
    return OpenQuestionsDocument(reference=reference, questions=questions)


# --------------------------------------------------------------------------------------
# Section 8 item 3 -- completion reports
# --------------------------------------------------------------------------------------


class CompletionReport(SuccessorPlanningModel):
    """One stage's completion report (section 8 item 3).

    Authoritative for what that stage did and found, and never for current task or registry
    status, which a report does not govern and cannot update. Only the report's identity fields
    are carried here for exactly that reason.
    """

    reference: EvidenceReference
    stage_id: str
    title: str
    status: str | None

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str) -> str:
        return _scalar(value, "report stage_id", MAX_STATUS_CHARS)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _scalar(value, "report title", MAX_MESSAGE_CHARS)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str | None) -> str | None:
        return None if value is None else _scalar(value, "report status", MAX_MESSAGE_CHARS)


class UnreadableSource(SuccessorPlanningModel):
    """One named source that exists but could not be read or validated.

    Kept as evidence rather than dropped: a completion report that is present but unreadable is
    a different fact from one that is absent, and section 4.1 gives the two different codes.
    """

    path: str
    stage_id: str | None
    code: FailureCode
    message: str

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _relative_path(value, "unreadable source path")

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str | None) -> str | None:
        return None if value is None else _scalar(value, "stage_id", MAX_STATUS_CHARS)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _scalar(value, "message", MAX_MESSAGE_CHARS)


def read_completion_report(root: Path, relative: str) -> CompletionReport:
    """Read one completion report and bind it to exactly one stage (section 8 item 3).

    The filename is the binding (`<STAGE_ID>-completion-report.md`) and the document's own
    first heading must agree with it. A report whose heading names a different stage is
    refused rather than attributed to either stage: the tool does not guess which of two
    disagreeing identities is the real one.
    """
    label = f"The completion report {relative!r}"
    name = relative.rsplit("/", 1)[-1]
    filename_match = _REPORT_NAME_RE.fullmatch(name)
    if filename_match is None:
        raise AuthoritativeSourceError(
            f"{label} is not named <STAGE_ID>-completion-report.md and cannot be bound to a stage"
        )
    stage_id = filename_match.group("stage")
    text, reference = read_document(root, relative, label)
    title_match = _REPORT_TITLE_RE.search(text)
    if title_match is None:
        raise AuthoritativeSourceError(f"{label} has no level-1 heading naming its stage")
    if title_match.group("stage") != stage_id:
        raise AuthoritativeSourceError(
            f"{label} is named for {stage_id} but its heading names "
            f"{safe_message(title_match.group('stage'))}"
        )
    status_match = _REPORT_STATUS_RE.search(text)
    status = safe_message(status_match.group("value")) if status_match is not None else None
    try:
        return CompletionReport(
            reference=reference,
            stage_id=stage_id,
            title=safe_message(title_match.group("title")),
            status=status,
        )
    except ValueError as exc:
        raise _invalid(label, exc) from exc


def read_completion_reports(
    root: Path, directory: str
) -> tuple[list[CompletionReport], list[UnreadableSource]]:
    """Read every completion report in one configured directory, in canonical order.

    The listing is sorted by name before use (section 16.2), so the evidence set never depends
    on raw `readdir` order. A file in the directory that is not named
    `<STAGE_ID>-completion-report.md` is not a completion report and contributes nothing --
    this directory also holds contract reviews, which are not completion evidence for any
    stage. A file that *is* named as a report but cannot be read or validated is recorded as an
    unreadable source rather than aborting the whole evidence read: section 11 makes a specific
    document's unreadability a per-candidate concern, not a whole-proposal one.

    That narrowing applies to unreadability only. A symlinked report, or one whose path escapes
    the repository, is a section 7.3 step 3 / section 22 invariant 1 policy violation with
    whole-proposal scope, so those errors propagate rather than being downgraded to a
    per-candidate record.
    """
    try:
        _relative_path(directory, "completion report directory")
    except ValueError as exc:
        raise InvalidInvocationError(
            f"The completion-report directory {directory!r} is not a usable repository-relative "
            f"path: {exc}"
        ) from exc
    label = f"The completion-report directory {directory!r}"
    names = sorted_directory_entries(_confine(root, directory), label)
    if len(names) > _MAX_COMPLETION_REPORTS:
        raise AuthoritativeSourceError(
            f"{label} holds {len(names)} entries, over the "
            f"{_MAX_COMPLETION_REPORTS}-entry ceiling"
        )
    reports: list[CompletionReport] = []
    unreadable: list[UnreadableSource] = []
    for name in names:
        match = _REPORT_NAME_RE.fullmatch(name)
        if match is None:
            continue
        relative = f"{directory}/{name}"
        try:
            reports.append(read_completion_report(root, relative))
        except AuthoritativeSourceError as exc:
            unreadable.append(
                UnreadableSource(
                    path=relative,
                    stage_id=match.group("stage"),
                    code="AUTHORITATIVE_SOURCE_MISSING",
                    message=safe_message(exc),
                )
            )
    return reports, unreadable


# --------------------------------------------------------------------------------------
# Section 8 item 10 -- handover evidence (required, never optional)
# --------------------------------------------------------------------------------------


class HandoverRecordCheck(SuccessorPlanningModel):
    """One manifest row verified against the working tree.

    Digests here are over the file's exact bytes, matching `check_handover`'s own comparison;
    the evidence-manifest digests alongside them are over normalized text (section 7.3 step 7).
    The two answer different questions and are deliberately both present.
    """

    path: str
    expected_size: int
    actual_size: int
    expected_digest: str
    actual_digest: str
    consistent: bool

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _relative_path(value, "handover record path")

    @field_validator("expected_size", "actual_size")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sizes must not be negative")
        return _int64(value, "handover size")

    @field_validator("expected_digest")
    @classmethod
    def _validate_expected(cls, value: str) -> str:
        # The manifest format allows a truncated digest prefix, which `check_handover` compares
        # with `startswith`; the same tolerance applies here and nowhere else.
        if re.fullmatch(r"[0-9a-f]{8,64}", value) is None:
            raise ValueError("expected_digest must be 8 to 64 lowercase hexadecimal characters")
        return value

    @field_validator("actual_digest")
    @classmethod
    def _validate_actual(cls, value: str) -> str:
        return _hex64(value, "actual_digest")


class HandoverEvidence(SuccessorPlanningModel):
    """The handover manifest and its verified files (section 8 item 10).

    Required, not optional, whenever the active configuration configures it, and read
    unconditionally by :func:`read_evidence_set` for that reason. A manifest that is absent,
    unreadable or unparsable fails closed; a manifest row whose file disagrees with it is
    recorded as an inconsistency and carried, never silently resolved.
    """

    manifest: EvidenceReference
    files: list[EvidenceReference]
    records: list[HandoverRecordCheck]
    consistent: bool

    @model_validator(mode="after")
    def _validate_ordering(self) -> "HandoverEvidence":
        _require_sorted_unique([item.path for item in self.files], "handover files", "path")
        return self


def read_handover_manifest(
    root: Path, manifest: str, files: Sequence[str] = ()
) -> HandoverEvidence:
    """Read and verify the configured handover manifest (section 8 item 10).

    Composes the existing `handover.manifest.parse_manifest` rather than adding a second
    manifest parser. Every row is verified against the working tree the same way
    `workflowctl check-handover` verifies it; every configured handover file is additionally
    read as evidence in its own right, so a file the manifest happens not to list is still
    hashed into the evidence set.
    """
    label = f"The handover manifest {manifest!r}"
    try:
        _relative_path(manifest, "handover manifest path")
    except ValueError as exc:
        raise InvalidInvocationError(
            f"The handover manifest {manifest!r} is not a usable repository-relative path: {exc}"
        ) from exc
    data, metadata = read_evidence_bytes(_confine(root, manifest), label)
    normalized = normalize_evidence_text(data, label)
    manifest_reference = EvidenceReference(
        path=manifest,
        sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        size=metadata.st_size,
    )
    try:
        parsed = parse_manifest(data)
    except (ManifestParseError, InvalidConfigurationError) as exc:
        raise AuthoritativeSourceError(f"{label} is unparsable: {safe_message(exc)}") from exc

    records: list[HandoverRecordCheck] = []
    references: dict[str, EvidenceReference] = {}
    for record in parsed:
        label_file = f"The handover file {record.path!r}"
        try:
            _relative_path(record.path, "handover file path")
        except ValueError as exc:
            raise AuthoritativeSourceError(
                f"{label} names an unusable path {record.path!r}: {exc}"
            ) from exc
        file_data, file_metadata = read_evidence_bytes(_confine(root, record.path), label_file)
        digest = hashlib.sha256(file_data).hexdigest()
        records.append(
            HandoverRecordCheck(
                path=record.path,
                expected_size=record.size,
                actual_size=len(file_data),
                expected_digest=record.digest,
                actual_digest=digest,
                consistent=len(file_data) == record.size and digest.startswith(record.digest),
            )
        )
        references[record.path] = EvidenceReference(
            path=record.path,
            sha256=hashlib.sha256(
                normalize_evidence_text(file_data, label_file).encode("utf-8")
            ).hexdigest(),
            size=file_metadata.st_size,
        )

    for relative in files:
        if relative in references or relative == manifest:
            continue
        _, reference = read_document(root, relative, f"The handover file {relative!r}")
        references[relative] = reference

    return HandoverEvidence(
        manifest=manifest_reference,
        files=[references[path] for path in sorted(references, key=lambda p: p.encode("utf-8"))],
        records=records,
        consistent=all(record.consistent for record in records),
    )


# --------------------------------------------------------------------------------------
# Section 8 -- the assembled evidence set
# --------------------------------------------------------------------------------------


class EvidenceSources(SuccessorPlanningModel):
    """The section 8 document locations the active configuration must name.

    `self-governance.yaml` defines locations for the task queue, its mirrors, the project state
    and the stage registries, but none for the decision log, the open-questions register or the
    completion-report directory. Section 4 item 8 requires those to come from the tool's own
    validated configuration and forbids an assumed default, so they are required inputs here
    with no defaults rather than constants baked into the reader.
    """

    decision_log: str
    open_questions: str
    completion_reports: str

    @field_validator("decision_log", "open_questions", "completion_reports")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _relative_path(value, "configured evidence path")


class EvidenceSet(SuccessorPlanningModel):
    """Every section 8 authoritative source, read once, in precedence order.

    The ordering of the fields follows section 8's precedence list so the record itself
    documents which source wins on a status contradiction -- and, per section 8's
    contradictory-evidence rule, a disagreement is never silently resolved by that precedence:
    :func:`reconcile_mirrors` records it, and the record travels with `manifest` into the
    proposal artifact.
    """

    identity: RepositoryIdentity
    task_queue: TaskDocument
    registries: list[RegistryDocument]
    completion_reports: list[CompletionReport]
    unreadable_completion_reports: list[UnreadableSource]
    decision_log: DecisionLogDocument
    project_state: ProjectStateDocument
    current_task: TaskDocument
    remaining_tasks: TaskDocument
    open_questions: OpenQuestionsDocument
    handover: HandoverEvidence
    manifest: list[EvidenceReference]

    @model_validator(mode="after")
    def _validate_manifest(self) -> "EvidenceSet":
        _require_sorted_unique([item.path for item in self.manifest], "evidence manifest", "path")
        return self

    @property
    def mirrors(self) -> tuple[TaskDocument, TaskDocument]:
        """The two pure mirrors of the task queue (section 8 item 6)."""
        return (self.current_task, self.remaining_tasks)

    def completion_report(self, stage_id: str) -> CompletionReport | None:
        for report in self.completion_reports:
            if report.stage_id == stage_id:
                return report
        return None

    def unreadable_report(self, stage_id: str) -> UnreadableSource | None:
        for source in self.unreadable_completion_reports:
            if source.stage_id == stage_id:
                return source
        return None

    def registry_rows(self, stage_id: str) -> list[tuple[RegistryDocument, RegistryStageRecord]]:
        rows: list[tuple[RegistryDocument, RegistryStageRecord]] = []
        for document in self.registries:
            row = document.row_for(stage_id)
            if row is not None:
                rows.append((document, row))
        return rows

    def known_stage_ids(self) -> frozenset[str]:
        """Every stage identifier the authoritative lifecycle evidence actually names."""
        identifiers = {record.task_id for record in self.task_queue.records}
        for document in self.registries:
            identifiers.update(row.stage_id for row in document.rows)
        return frozenset(identifiers)


def _manifest_of(references: Sequence[EvidenceReference]) -> list[EvidenceReference]:
    unique: dict[str, EvidenceReference] = {}
    for reference in references:
        unique.setdefault(reference.path, reference)
    return [unique[path] for path in sorted(unique, key=lambda value: value.encode("utf-8"))]


def read_evidence_set(
    config: EngineConfig, identity: RepositoryIdentity, sources: EvidenceSources
) -> EvidenceSet:
    """Read every section 8 authoritative source once, into one typed record.

    Handover evidence (section 8 item 10) is read unconditionally, because the active
    configuration configures it and section 8 makes it required rather than corroborating.
    Git evidence (item 9) and the active configuration (item 8) are already bound in
    `identity`; the candidate catalog (item 7) is read separately by the catalog module, which
    has its own file-level failure semantics.
    """
    root = Path(identity.resolved_repository_root)
    task_queue = read_task_document(root, config.governance.task_queue)
    current_task = read_task_document(root, config.governance.current_task)
    remaining_tasks = read_task_document(root, config.governance.remaining_tasks)
    project_state = read_project_state(
        root, config.governance.project_state, config.governance.facts
    )
    registries = [
        read_registry_document(root, relative) for relative in config.governance.registries
    ]
    decision_log = read_decision_log(root, sources.decision_log)
    open_questions = read_open_questions(root, sources.open_questions)
    reports, unreadable = read_completion_reports(root, sources.completion_reports)
    handover = read_handover_manifest(root, config.handover.manifest, config.handover.files)

    return EvidenceSet(
        identity=identity,
        task_queue=task_queue,
        registries=registries,
        completion_reports=reports,
        unreadable_completion_reports=unreadable,
        decision_log=decision_log,
        project_state=project_state,
        current_task=current_task,
        remaining_tasks=remaining_tasks,
        open_questions=open_questions,
        handover=handover,
        manifest=_manifest_of(
            [
                task_queue.reference,
                current_task.reference,
                remaining_tasks.reference,
                project_state.reference,
                *(document.reference for document in registries),
                decision_log.reference,
                open_questions.reference,
                *(report.reference for report in reports),
                handover.manifest,
                *handover.files,
            ]
        ),
    )


# --------------------------------------------------------------------------------------
# Section 4 items 2-3, section 8 -- mirror and registry reconciliation
# --------------------------------------------------------------------------------------


class StatusDisagreement(SuccessorPlanningModel):
    """One named disagreement between the authoritative queue and another source."""

    identifier: str
    path: str
    observed_status: str
    authoritative_status: str
    message: str

    @field_validator("identifier")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        return _scalar(value, "identifier", MAX_STATUS_CHARS)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _relative_path(value, "disagreement path")

    @field_validator("observed_status", "authoritative_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return _scalar(value, "status", MAX_STATUS_CHARS)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _scalar(value, "message", MAX_MESSAGE_CHARS)


class MirrorReconciliation(SuccessorPlanningModel):
    """The section 8 reconciliation across the queue, its mirrors and every registry.

    Section 13 gives one code, `MIRROR_CONTRADICTION`, to both halves of this: the mirrors
    disagreeing with the queue, and a registry disagreeing materially with it. `failure_code`
    carries that code when either holds, and both disagreement lists are kept separately and in
    full, because section 8 forbids resolving a disagreement by picking the higher-precedence
    source and discarding it. Nothing here decides an outcome; it records one.

    `current_tasks` is the queue's own `Current` set. Section 4 item 3 makes any non-empty set
    `CONFLICTING_CURRENT_TASK` at invocation time, with no exception for the invocation itself,
    which never appears in the queue. Classifying that is the invocation path's call; reading it
    is this record's.
    """

    task_queue_path: str
    mirror_paths: list[str]
    registry_paths: list[str]
    current_tasks: list[str]
    mirror_disagreements: list[StatusDisagreement]
    registry_disagreements: list[StatusDisagreement]
    consistent: bool
    failure_code: FailureCode | None

    @model_validator(mode="after")
    def _validate_code(self) -> "MirrorReconciliation":
        disagreements = bool(self.mirror_disagreements or self.registry_disagreements)
        if self.consistent == disagreements:
            raise ValueError("consistent must be false exactly when a disagreement was recorded")
        if disagreements != (self.failure_code is not None):
            raise ValueError("failure_code must be present exactly when a disagreement was found")
        return self


def reconcile_mirrors(evidence: EvidenceSet) -> MirrorReconciliation:
    """Reconcile the task queue against its mirrors and every configured stage registry.

    Mirror half (section 4 item 2, section 8 item 6): every task the two pure mirrors record is
    compared against the queue, and the queue's `Current` set is compared against the
    current-task mirror's, which is exactly what `workflowctl check-task-state` already checks.
    A mirror that records a task the queue does not is itself a disagreement, since a pure
    mirror has no independent content to add.

    Registry half (section 8 item 2): each registry row's State is mapped to a task status
    through the existing documented mapping, and compared with the queue. A state the mapping
    does not recognize is a disagreement too -- the tool does not assume an unknown state is
    compatible with whatever the queue says.
    """
    authoritative = {record.task_id: record.status for record in evidence.task_queue.records}
    queue_path = evidence.task_queue.reference.path

    mirror_disagreements: list[StatusDisagreement] = []
    for mirror in evidence.mirrors:
        path = mirror.reference.path
        for record in mirror.records:
            expected = authoritative.get(record.task_id)
            if expected is None:
                mirror_disagreements.append(
                    StatusDisagreement(
                        identifier=record.task_id,
                        path=path,
                        observed_status=str(record.status),
                        authoritative_status="(absent)",
                        message=f"{record.task_id} is recorded here but absent from {queue_path}",
                    )
                )
            elif record.status != expected:
                mirror_disagreements.append(
                    StatusDisagreement(
                        identifier=record.task_id,
                        path=path,
                        observed_status=str(record.status),
                        authoritative_status=str(expected),
                        message=(
                            f"{record.task_id} is {record.status} here but {expected} in "
                            f"{queue_path}"
                        ),
                    )
                )

    queue_current = set(evidence.task_queue.with_status(TaskStatus.CURRENT))
    mirror_current = set(evidence.current_task.with_status(TaskStatus.CURRENT))
    if queue_current != mirror_current:
        mirror_disagreements.append(
            StatusDisagreement(
                identifier="(Current set)",
                path=evidence.current_task.reference.path,
                observed_status=", ".join(sorted(mirror_current)) or "(none)",
                authoritative_status=", ".join(sorted(queue_current)) or "(none)",
                message=(f"The current-task mirror's Current set differs from {queue_path}'s"),
            )
        )

    registry_disagreements: list[StatusDisagreement] = []
    for document in evidence.registries:
        path = document.reference.path
        for row in document.rows:
            actual = authoritative.get(row.stage_id)
            if row.state is None:
                registry_disagreements.append(
                    StatusDisagreement(
                        identifier=row.stage_id,
                        path=path,
                        observed_status=row.raw_state or "(empty)",
                        authoritative_status=str(actual) if actual is not None else "(absent)",
                        message=(
                            f"{row.stage_id} has an unrecognized registry state "
                            f"{row.raw_state or '(empty)'}"
                        ),
                    )
                )
                continue
            expected = REGISTRY_STATE_TO_TASK_STATUS[row.state]
            if actual is None:
                registry_disagreements.append(
                    StatusDisagreement(
                        identifier=row.stage_id,
                        path=path,
                        observed_status=str(row.state),
                        authoritative_status="(absent)",
                        message=f"{row.stage_id} is registered here but absent from {queue_path}",
                    )
                )
            elif actual != expected:
                registry_disagreements.append(
                    StatusDisagreement(
                        identifier=row.stage_id,
                        path=path,
                        observed_status=str(row.state),
                        authoritative_status=str(actual),
                        message=(
                            f"{row.stage_id} registry state {row.state} maps to {expected} but "
                            f"{queue_path} says {actual}"
                        ),
                    )
                )

    disagreements = bool(mirror_disagreements or registry_disagreements)
    return MirrorReconciliation(
        task_queue_path=queue_path,
        mirror_paths=[mirror.reference.path for mirror in evidence.mirrors],
        registry_paths=[document.reference.path for document in evidence.registries],
        current_tasks=evidence.task_queue.with_status(TaskStatus.CURRENT),
        mirror_disagreements=mirror_disagreements,
        registry_disagreements=registry_disagreements,
        consistent=not disagreements,
        failure_code="MIRROR_CONTRADICTION" if disagreements else None,
    )


# --------------------------------------------------------------------------------------
# Section 4 item 4 -- the four mandated `workflowctl verify` governance checks
# --------------------------------------------------------------------------------------
#
# Section 4 item 4 requires `workflowctl verify --config self-governance.yaml`'s `task-state`,
# `governance`, `registries` and `handover` checks to pass *unconditionally* before an
# invocation may proceed. The `git` check is already run, with section 7.2 rule 4's documented
# `upstream_missing` tolerance applied to it, inside the snapshot module's identity resolution;
# the other four have no tolerance at all and are run here.
#
# The existing validators are composed, never reimplemented: section 23.4 records
# `governance/validators.py` as needing no change and section 24 makes `governance/**` a
# forbidden surface, so a second, locally-corrected copy of these checks would be exactly the
# divergence both rules exist to prevent. `reconcile_mirrors` above answers a different and
# narrower question -- it produces the *typed, artifact-embedded* record of which documents
# disagree, which a boolean `CheckResult` cannot carry -- so the two are complementary rather
# than duplicative, and both must hold.


#: Section 4 item 4's four checks, in the order `workflowctl verify` itself runs them.
REQUIRED_GOVERNANCE_CHECKS: tuple[str, ...] = ("task-state", "governance", "registries", "handover")

#: `check_handover` findings that mean a required document could not be read at all, rather
#: than that two readings of it disagree. Section 13 gives those two meanings different codes.
_HANDOVER_SOURCE_FAILURES: frozenset[str] = frozenset(
    {"manifest_error", "manifest_file_missing", "commit_error", "check_error"}
)


class GovernanceCheckFailure(SuccessorPlanningModel):
    """One finding from a section 4 item 4 check that did not pass, with its section 13 code."""

    check_name: str
    finding_code: str
    failure_code: FailureCode
    path: str
    message: str

    @field_validator("check_name", "finding_code")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _scalar(value, "governance check identifier", MAX_STATUS_CHARS)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _scalar(value, "governance check subject", MAX_STATUS_CHARS)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _scalar(value, "governance check message", MAX_MESSAGE_CHARS)

    @field_validator("failure_code")
    @classmethod
    def _validate_scope(cls, value: FailureCode) -> FailureCode:
        if FAILURE_SCOPES[value] != "whole_proposal":
            raise ValueError(f"{value} is a per-candidate code and never fails an entry condition")
        return value


def _governance_failure_code(check_name: str, finding_code: str) -> FailureCode:
    """Map one failed check finding onto the section 13 code that already covers it.

    Section 13 defines no code of its own for "a `workflowctl verify` check failed", and this
    stage may not widen the taxonomy, so each finding is placed under the existing code whose
    stated meaning actually covers it: a handover document that could not be read at all is
    `AUTHORITATIVE_SOURCE_MISSING` (section 8 item 10 makes handover evidence required, and
    section 13 gives that code the meaning "a required document is absent or unreadable"), an
    over-count of `Current` tasks is section 4 item 3's own `CONFLICTING_CURRENT_TASK`, and
    every remaining finding is the whole-evidence-set inconsistency section 11.3 refuses on.
    """
    if check_name == "handover" and finding_code in _HANDOVER_SOURCE_FAILURES:
        return "AUTHORITATIVE_SOURCE_MISSING"
    if finding_code == "check_error":
        return "AUTHORITATIVE_SOURCE_MISSING"
    if finding_code == "too_many_current_tasks":
        return "CONFLICTING_CURRENT_TASK"
    return "MIRROR_CONTRADICTION"


def _run_governance_check(
    check_name: str, operation: Callable[[], CheckResult]
) -> list[GovernanceCheckFailure]:
    """Run one check and return its failures, treating an exception as a failure of the check.

    A check that raises has not passed, and section 4 item 4 requires it to pass. Converting the
    exception into a typed failure rather than letting it escape keeps section 11.3's promise
    that no contract failure surfaces as a bare exception.
    """
    try:
        result = operation()
    except Exception as exc:  # a check that cannot run has not passed (section 22 invariant 6)
        return [
            GovernanceCheckFailure(
                check_name=check_name,
                finding_code="check_error",
                failure_code="AUTHORITATIVE_SOURCE_MISSING",
                path=check_name,
                message=safe_message(f"the {check_name} check could not be completed: {exc}"),
            )
        ]
    if result.status == Status.PASS:
        return []
    failures = [
        GovernanceCheckFailure(
            check_name=check_name,
            finding_code=finding.code,
            failure_code=_governance_failure_code(check_name, finding.code),
            path=finding.path or check_name,
            message=safe_message(f"{check_name}: {finding.message}"),
        )
        for finding in result.findings
    ]
    if failures:
        return failures
    # A non-`PASS` status with no finding attached still has not passed, and failing closed
    # means refusing on the status itself rather than reading an empty finding list as consent.
    return [
        GovernanceCheckFailure(
            check_name=check_name,
            finding_code="check_not_passed",
            failure_code="MIRROR_CONTRADICTION",
            path=check_name,
            message=safe_message(f"the {check_name} check reported {result.status}"),
        )
    ]


def run_required_governance_checks(config: EngineConfig) -> list[GovernanceCheckFailure]:
    """Run section 4 item 4's four checks and report every finding that keeps one from passing.

    An empty list means all four passed, which is the only state section 4 item 4 permits an
    invocation to continue from.
    """
    return [
        *_run_governance_check("task-state", lambda: check_task_state(config)),
        *_run_governance_check("governance", lambda: check_governance(config)),
        *_run_governance_check("registries", lambda: check_registries(config)),
        *_run_governance_check("handover", lambda: check_handover(config)),
    ]


# --------------------------------------------------------------------------------------
# Section 4 item 6 -- the unauthorized-successor-implementation preflight
# --------------------------------------------------------------------------------------
#
# Section 4 item 6 admits exactly two categories of successor-stage state: (a) AUTO-015's own
# already-authorized, already-registered implementation, and (b) a candidate stage separately
# and explicitly authorized through its own distinct stage contract. Anything else -- a branch,
# a source symbol or a Registry row naming a later stage -- is
# `UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED`, whole-proposal, fail-closed.
#
# Category (a) needs no lookup: AUTO-015 is this implementation, and a stage identifier is a
# *successor* here only when its number is strictly greater than AUTO-015's own. Category (b) is
# recognized by the one observable, deterministic artifact the contract names for it -- the
# candidate's own distinct stage contract at
# `docs/workflow-automation/stage-prompts/<STAGE_ID>.md`. A stage with no such contract has not
# been separately authorized through one, so state naming it fails closed.

#: This implementation's own stage. Only a strictly later stage is a successor.
SELF_STAGE_NUMBER = 15

#: Where a candidate stage's own distinct stage contract lives (section 4 item 6 category b).
STAGE_CONTRACT_DIRECTORY = "docs/workflow-automation/stage-prompts"

#: The repository source root scanned for a successor-stage source symbol.
SOURCE_ROOT = "src"

# A stage identifier as it appears in a name: `AUTO-016`, `auto-016`, `auto_016`. The lookarounds
# stop `auto-0161` or `xauto-016` from being read as a three-digit stage number.
_STAGE_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z])[Aa][Uu][Tt][Oo][-_]?(?P<number>[0-9]{3})(?![0-9])")

# Module-level Python symbols: a definition, or a plain/annotated module-level binding.
_DEFINITION_RE = re.compile(
    r"^(?:async[ \t]+)?(?:def|class)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)
_BINDING_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*(?::[^=\n]+)?=", re.MULTILINE)

#: Section 22 invariant 14: an explicit ceiling on each surface scanned by the preflight.
MAX_PREFLIGHT_ENTRIES = 4_096


class UnauthorizedSuccessorError(WorkflowEngineError):
    """Section 4 item 6's fail-closed entry condition, carrying its section 13 code."""

    code: ClassVar[FailureCode] = "UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED"


class SuccessorSighting(SuccessorPlanningModel):
    """One successor-stage identifier observed on one surface, named with where it was seen."""

    surface: Literal["branch", "source_symbol", "registry_row"]
    stage_id: str
    location: str

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str) -> str:
        return _scalar(value, "successor stage id", MAX_STATUS_CHARS)

    @field_validator("location")
    @classmethod
    def _validate_location(cls, value: str) -> str:
        return _scalar(value, "successor sighting location", MAX_PATH_CHARS)


def _successor_stage_ids(name: str) -> list[str]:
    """Every strictly-later stage identifier a name mentions, in canonical `AUTO-0NN` form."""
    found = {
        f"AUTO-{match.group('number')}"
        for match in _STAGE_TOKEN_RE.finditer(name)
        if int(match.group("number")) > SELF_STAGE_NUMBER
    }
    return sorted(found)


def _declared_branch_names(root: Path) -> list[str]:
    """Every branch name this repository declares, read as ordinary bytes.

    Read from `.git`'s own loose-reference tree and `packed-refs` rather than through a Git
    command: `GitClient.READ_ONLY_FORMS` admits no branch-listing form, and widening that
    allowlist would open exactly the new, independently-audited Git access path section 7.1
    forbids. This mirrors how the primary remote identity is already resolved.
    """
    git_directory = root / ".git"
    if not git_directory.is_dir():
        return []
    names: set[str] = set()
    for kind in ("heads", "remotes"):
        base = git_directory / "refs" / kind
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*"))[:MAX_PREFLIGHT_ENTRIES]:
            if path.is_file():
                names.add(str(path.relative_to(base)))
    packed = git_directory / "packed-refs"
    if packed.is_file():
        try:
            text = packed.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for line in text.splitlines()[:MAX_PREFLIGHT_ENTRIES]:
            _, _, reference = line.partition(" ")
            reference = reference.strip()
            for prefix in ("refs/heads/", "refs/remotes/"):
                if reference.startswith(prefix):
                    names.add(reference[len(prefix) :])
    return sorted(names)


def _declared_source_symbols(root: Path) -> list[tuple[str, str]]:
    """Every `(location, symbol)` pair the repository's own source tree declares.

    A module or package name is itself a symbol, so both path components and module-level
    definitions and bindings are collected. Only names are examined -- never prose, comments or
    docstrings -- so a document that merely *mentions* a later stage is not mistaken for an
    implementation of one.
    """
    source_root = root / SOURCE_ROOT
    if not source_root.is_dir():
        return []
    symbols: list[tuple[str, str]] = []
    for path in sorted(source_root.rglob("*"))[:MAX_PREFLIGHT_ENTRIES]:
        if path.is_symlink():
            continue
        location = str(path.relative_to(root))
        symbols.append((location, path.name))
        if not path.is_file() or path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in (_DEFINITION_RE, _BINDING_RE):
            symbols.extend((location, match.group("name")) for match in pattern.finditer(text))
    return symbols


def _has_own_stage_contract(root: Path, stage_id: str) -> bool:
    """Whether `stage_id` has its own distinct stage contract (section 4 item 6 category b)."""
    contract = root / STAGE_CONTRACT_DIRECTORY / f"{stage_id}.md"
    return contract.is_file() and not contract.is_symlink()


def detect_unauthorized_successors(
    root: Path, registries: Sequence[str]
) -> list[SuccessorSighting]:
    """Find every successor-stage branch, source symbol or Registry row that is unrecognized.

    An empty list is the only state section 4 item 6 permits an invocation to continue from.
    """
    sightings: list[SuccessorSighting] = []

    def record(surface: str, location: str, name: str) -> None:
        for stage_id in _successor_stage_ids(name):
            if _has_own_stage_contract(root, stage_id):
                continue
            sightings.append(
                SuccessorSighting(
                    surface=surface,  # type: ignore[arg-type]
                    stage_id=stage_id,
                    location=_scalar(location, "sighting location", MAX_PATH_CHARS),
                )
            )

    for branch in _declared_branch_names(root):
        record("branch", branch, branch)
    for location, symbol in _declared_source_symbols(root):
        record("source_symbol", f"{location}:{symbol}", symbol)
    for relative in registries:
        for row in read_registry_document(root, relative).rows:
            record("registry_row", f"{relative}:{row.stage_id}", row.stage_id)
    return sightings


def check_no_unauthorized_successor(config: EngineConfig, root: Path) -> None:
    """Section 4 item 6, run before the evidence-snapshot pass begins.

    Raises :class:`UnauthorizedSuccessorError` when a branch, source symbol or Registry row
    names a successor stage that is neither this implementation itself nor a stage carrying its
    own distinct contract. Reading the configured registries can itself fail; those failures
    propagate as the reader's own typed errors, exactly as the later evidence read would report
    them, so one section 13 code is never derived in two places.
    """
    sightings = detect_unauthorized_successors(root, config.governance.registries)
    if not sightings:
        return
    described = ", ".join(
        f"{sighting.stage_id} ({sighting.surface} {sighting.location})" for sighting in sightings
    )
    raise UnauthorizedSuccessorError(
        "Successor-stage state exists that is neither this already-authorized AUTO-015 "
        "implementation nor a stage carrying its own distinct contract under "
        f"{STAGE_CONTRACT_DIRECTORY!r}: {safe_message(described)}"
    )


# --------------------------------------------------------------------------------------
# Section 4.1 -- predecessor resolution
# --------------------------------------------------------------------------------------

# Section 7.1 fields that identify the *repository*, as distinct from the baseline within it.
_REPOSITORY_FIELDS = (
    "configured_repository_id",
    "configured_repository_root",
    "resolved_repository_root",
    "git_worktree_root",
)
# Section 7.1 fields that identify the *baseline*. Deliberately just these two: a working-tree
# file list that moved between two reads is snapshot drift (`INPUT_DRIFT`, section 7.3), which
# is a different question from the predecessor's evidence being bound to a different baseline.
_BASELINE_FIELDS = ("branch", "head_sha")


class PredecessorEvidence(SuccessorPlanningModel):
    """The validated predecessor binding section 16.1 embeds in the proposal.

    It identifies the proposal's target only. It never selects a successor, authorizes or
    registers anything, mutates or reopens the predecessor, or requires the predecessor to be
    numerically latest.
    """

    stage_id: str
    registry_evidence: PredecessorRegistryEvidence
    completion_evidence: list[EvidenceReference]
    reconciliation: PredecessorStatusReconciliation
    repository_identity: RepositoryIdentity

    @field_validator("stage_id")
    @classmethod
    def _validate_stage_id(cls, value: str) -> str:
        _scalar(value, "predecessor stage_id", MAX_STATUS_CHARS)
        if _PREDECESSOR_ID_RE.fullmatch(value) is None:
            raise ValueError("predecessor stage_id must match ^AUTO-[0-9]{3}$")
        return value

    @field_validator("completion_evidence")
    @classmethod
    def _validate_evidence_order(cls, value: list[EvidenceReference]) -> list[EvidenceReference]:
        _require_sorted_unique(
            [reference.path for reference in value], "completion_evidence", "path"
        )
        return value


def _check_identity_binding(evidence: EvidenceSet, identity: RepositoryIdentity) -> None:
    """Section 4.1: the predecessor's evidence must be bound to this repository and baseline.

    Checked before the evidence is consulted at all, because evidence read from a different
    repository, or at a different baseline, cannot answer any later question about this one.
    """
    for field in _REPOSITORY_FIELDS:
        before = getattr(evidence.identity, field)
        after = getattr(identity, field)
        if before != after:
            raise PredecessorError(
                "PREDECESSOR_REPOSITORY_MISMATCH",
                f"The predecessor evidence is bound to {field} {before!r}, but this invocation's "
                f"repository identity is {after!r}",
            )
    for field in _BASELINE_FIELDS:
        before = getattr(evidence.identity, field)
        after = getattr(identity, field)
        if before != after:
            raise PredecessorError(
                "PREDECESSOR_BASELINE_MISMATCH",
                f"The predecessor evidence is bound to {field} {before!r}, but this invocation's "
                f"Git baseline is {after!r}",
            )


def resolve_predecessor(
    evidence: EvidenceSet, stage_id: str | None, *, identity: RepositoryIdentity
) -> PredecessorEvidence:
    """Resolve and validate the required `--predecessor <STAGE_ID>` (section 4.1).

    The checks run in one fixed order, and each produces exactly one section 4.1 code:

    1. the argument is present -- `MISSING_PREDECESSOR`;
    2. it matches `^AUTO-[0-9]{3}$` -- `INVALID_PREDECESSOR_ID`;
    3. the evidence is bound to this repository and baseline --
       `PREDECESSOR_REPOSITORY_MISMATCH`, `PREDECESSOR_BASELINE_MISMATCH`;
    4. it exists in the authoritative Stage Registry -- `PREDECESSOR_NOT_REGISTERED`;
    5. two registries do not disagree about it -- `PREDECESSOR_STATUS_CONTRADICTION`;
    6. its registry state is `COMPLETE` -- `PREDECESSOR_NOT_COMPLETE`. `SUPERSEDED` is not
       `COMPLETE`: both map to task status `Done`, but the registry's own state model states
       they are never interchangeable in meaning, and section 4.1 requires `COMPLETE`;
    7. the queue records it at all -- `PREDECESSOR_INCOMPLETE`, section 4 item 1's "not
       confirmed `COMPLETE` in both";
    8. the queue and the mirrors agree it is `Done` -- `PREDECESSOR_STATUS_CONTRADICTION`;
    9. a completion report exists -- `PREDECESSOR_COMPLETION_EVIDENCE_MISSING` -- and is
       readable -- `PREDECESSOR_EVIDENCE_INVALID`.

    Every one of these is whole-proposal and fails closed before any candidate is evaluated.
    """
    if stage_id is None or not stage_id.strip():
        raise PredecessorError(
            "MISSING_PREDECESSOR",
            "Every invocation must supply --predecessor <STAGE_ID>; no invocation infers the "
            "most recent stage",
        )
    if _PREDECESSOR_ID_RE.fullmatch(stage_id) is None:
        raise PredecessorError(
            "INVALID_PREDECESSOR_ID",
            f"The predecessor {safe_message(stage_id)!r} does not match ^AUTO-[0-9]{{3}}$",
        )

    _check_identity_binding(evidence, identity)

    rows = evidence.registry_rows(stage_id)
    if not rows:
        raise PredecessorError(
            "PREDECESSOR_NOT_REGISTERED",
            f"{stage_id} has no row in any configured stage registry",
        )
    states = {row.raw_state for _, row in rows}
    if len(states) > 1:
        raise PredecessorError(
            "PREDECESSOR_STATUS_CONTRADICTION",
            f"{stage_id} is recorded with disagreeing registry states "
            f"{sorted(safe_message(state) for state in states)}",
        )
    document, row = rows[0]
    if row.state != RegistryState.COMPLETE:
        raise PredecessorError(
            "PREDECESSOR_NOT_COMPLETE",
            f"{stage_id} is {safe_message(row.raw_state) or '(empty)'} in "
            f"{document.reference.path}, not COMPLETE",
        )

    queue_status = evidence.task_queue.status_of(stage_id)
    if queue_status is None:
        raise PredecessorError(
            "PREDECESSOR_INCOMPLETE",
            f"{stage_id} is COMPLETE in {document.reference.path} but is absent from "
            f"{evidence.task_queue.reference.path}, so it is not confirmed COMPLETE in both",
        )
    if queue_status != TaskStatus.DONE:
        raise PredecessorError(
            "PREDECESSOR_STATUS_CONTRADICTION",
            f"{stage_id} is COMPLETE in {document.reference.path} but {queue_status} in "
            f"{evidence.task_queue.reference.path}",
        )

    mirror_status = "absent"
    for mirror in evidence.mirrors:
        observed = mirror.status_of(stage_id)
        if observed is None:
            continue
        if observed != TaskStatus.DONE:
            raise PredecessorError(
                "PREDECESSOR_STATUS_CONTRADICTION",
                f"{stage_id} is {queue_status} in {evidence.task_queue.reference.path} but "
                f"{observed} in the mirror {mirror.reference.path}",
            )
        mirror_status = str(observed)

    report = evidence.completion_report(stage_id)
    if report is None:
        unreadable = evidence.unreadable_report(stage_id)
        if unreadable is not None:
            raise PredecessorError(
                "PREDECESSOR_EVIDENCE_INVALID",
                f"{stage_id}'s completion report {unreadable.path} could not be validated: "
                f"{unreadable.message}",
            )
        raise PredecessorError(
            "PREDECESSOR_COMPLETION_EVIDENCE_MISSING",
            f"No readable completion report exists for {stage_id}",
        )

    return PredecessorEvidence(
        stage_id=stage_id,
        registry_evidence=PredecessorRegistryEvidence(
            registry_reference=document.reference, registry_status=row.raw_state
        ),
        completion_evidence=[report.reference],
        reconciliation=PredecessorStatusReconciliation(
            registry_status=row.raw_state,
            task_queue_status=str(queue_status),
            mirror_status=mirror_status,
            reconciled_status=str(RegistryState.COMPLETE),
            consistent=True,
        ),
        repository_identity=identity,
    )


# --------------------------------------------------------------------------------------
# Section 8 -- completion evidence for a candidate's own claims
# --------------------------------------------------------------------------------------

_COMPLETION_CLAIM_STATUSES = frozenset({"COMPLETE", "DONE"})


class CompletionClaim(SuccessorPlanningModel):
    """One candidate's declared stage-completion dependency, re-checked against live evidence.

    Section 8: a candidate whose predecessor-completion claim has no corresponding, readable
    completion report is `insufficient_evidence` for that candidate specifically, never a
    whole-proposal refusal -- section 13 names that per-candidate code
    `STALE_COMPLETION_EVIDENCE`.
    """

    candidate_id: str
    stage_id: str
    declared_status: str
    report: EvidenceReference | None
    code: FailureCode | None

    @field_validator("candidate_id", "stage_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        return _scalar(value, "completion claim identifier", MAX_STATUS_CHARS)

    @field_validator("declared_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return _scalar(value, "declared status", MAX_STATUS_CHARS)


def check_completion_claims(
    evidence: EvidenceSet, candidates: Sequence[Candidate]
) -> list[CompletionClaim]:
    """Re-check every candidate's declared stage-completion dependency against live evidence.

    The catalog's own frozen `status` text is never the answer: a claim is satisfied only when
    a completion report for that stage was actually read and validated in this invocation. A
    report that exists but failed validation is not a readable report, so it satisfies nothing.
    """
    claims: list[CompletionClaim] = []
    for candidate in candidates:
        for dependency in candidate.dependencies:
            if dependency.dependency_type != "stage":
                continue
            if dependency.status.strip().upper() not in _COMPLETION_CLAIM_STATUSES:
                continue
            report = evidence.completion_report(dependency.dependency_id)
            claims.append(
                CompletionClaim(
                    candidate_id=candidate.candidate_id,
                    stage_id=dependency.dependency_id,
                    declared_status=dependency.status,
                    report=report.reference if report is not None else None,
                    code=None if report is not None else "STALE_COMPLETION_EVIDENCE",
                )
            )
    return sorted(
        claims,
        key=lambda claim: (
            claim.candidate_id.encode("utf-8"),
            claim.stage_id.encode("utf-8"),
        ),
    )


def stale_completion_findings(claims: Sequence[CompletionClaim]) -> list[CandidateFinding]:
    """Turn unsatisfied completion claims into per-candidate `STALE_COMPLETION_EVIDENCE`."""
    findings = [
        CandidateFinding(
            code="STALE_COMPLETION_EVIDENCE",
            candidate_id=claim.candidate_id,
            message=safe_message(
                f"{claim.stage_id} is claimed {claim.declared_status} but no readable "
                f"completion report for it was found"
            ),
        )
        for claim in claims
        if claim.code is not None
    ]
    return sorted(
        findings,
        key=lambda finding: (
            finding.code.encode("utf-8"),
            finding.candidate_id.encode("utf-8"),
        ),
    )
