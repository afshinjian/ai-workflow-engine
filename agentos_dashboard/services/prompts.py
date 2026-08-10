"""DR-042/043 (`PRODUCT_SPEC.md`): the gated prompt renderer, its SHA-256 identity, and the
in-memory `GeneratedPrompt`/audit stores (`API_SPEC.md` EP-21; `DATA_MODEL.md` EN-13).

`generate_stage_prompt` is the one entry point: it evaluates `services.stages.
evaluate_preconditions`, and either renders, hashes, stores, and audits a new prompt, or audits
the refusal and returns the failing `PreconditionReport` untouched — the caller (`api.prompts`)
turns that into a 422 with the itemized unmet-precondition list `API_SPEC.md` §5 requires.
Success and refusal are both audited (DR-043), in-memory only: `DATA_MODEL.md` §3 assigns
`dashboard.db` persistence to DASH-008, which does not exist yet, so `PromptStore`/
`PromptAuditLog` are process-lifetime state, the same disposable-cache posture
`api.acknowledgments.AcknowledgmentStore` already uses for exactly the same reason.

The rendered prompt is the tracked `stage-prompts/README.md` SSP section plus the stage's own
canonical `stage-prompts/DASH-0XX.md` text, verbatim after placeholder substitution — never a
duplicated or rewritten copy, per `stage-prompts/README.md` rule 2 ("the SSP is applied by
reference and is never duplicated into stage files"). Every live, repository-derived fact (branch,
HEAD, tree state, date, and the precondition report itself) is embedded only inside a fenced
`text` block explicitly labeled `(data)`, never inlined into prose — `SECURITY_MODEL.md` SC-20's
prompt-injection resistance: a hostile branch name or finding message can only ever read as
inert data, never as an instruction, to whatever later reads the generated prompt.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from agentos_dashboard.core import DashboardError, utc_now
from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.gitread import GitReadError, read_status
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.core.redact import redact_secrets
from agentos_dashboard.core.snapshot import RepositorySnapshot
from agentos_dashboard.prompt_templates.placeholders import substitute
from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA_BY_ID, StageSchema
from agentos_dashboard.services.stages import PreconditionReport, evaluate_preconditions

__all__ = [
    "STAGE_PROMPTS_DIR",
    "AuditEntry",
    "GeneratedPromptRecord",
    "PromptAuditLog",
    "PromptStore",
    "UnknownStageError",
    "generate_stage_prompt",
]

STAGE_PROMPTS_DIR = "docs/agentos-dashboard/stage-prompts"
_SSP_README_PATH = f"{STAGE_PROMPTS_DIR}/README.md"
_SSP_HEADING = "## Standard Stage Protocol (SSP)"

_TEMPLATE_VERSION_RE = re.compile(
    r"\*\*(?:Status/Version|Version)\*\*\s*\|\s*[^|\n]*?([0-9]+\.[0-9]+)\s*\|"
)


class UnknownStageError(DashboardError):
    """`stage_id` is not one of the ten coded DASH stages."""


@dataclass(frozen=True)
class GeneratedPromptRecord:
    """EN-13: one rendered, hashed prompt (`prompt_uuid` is this stage's local identity — the
    engine's own `prompt_id` addressing scheme, `PromptMetadata` in
    `src/ai_workflow_engine/prompt/models.py`, is a different subsystem for a different document
    set and is never reused here)."""

    prompt_uuid: str
    stage_id: str
    template_version: str
    generated_at: str
    sha256: str
    markdown: str
    filename: str


@dataclass(frozen=True)
class AuditEntry:
    """DR-043: one audited generation or refusal."""

    kind: str  # "generated" | "refused"
    stage_id: str
    at: str
    detail: str


class PromptStore:
    """Process-lifetime `GeneratedPromptRecord` storage, addressed by UUID and, for idempotent
    replay (`API_SPEC.md` §1), by the caller-supplied client token."""

    def __init__(self) -> None:
        self._records: dict[str, GeneratedPromptRecord] = {}
        self._by_token: dict[str, str] = {}

    def get(self, prompt_uuid: str) -> GeneratedPromptRecord | None:
        return self._records.get(prompt_uuid)

    def get_by_token(self, client_token: str) -> GeneratedPromptRecord | None:
        prompt_uuid = self._by_token.get(client_token)
        return self._records.get(prompt_uuid) if prompt_uuid is not None else None

    def add(self, record: GeneratedPromptRecord, *, client_token: str | None = None) -> None:
        self._records[record.prompt_uuid] = record
        if client_token is not None:
            self._by_token[client_token] = record.prompt_uuid

    def all(self) -> tuple[GeneratedPromptRecord, ...]:
        return tuple(self._records.values())


class PromptAuditLog:
    """Process-lifetime, append-only audit of every generation attempt (success and refusal)."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def all(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)


def _read_or_none(root: RepositoryRoot, relative: str) -> str | None:
    try:
        return read_text(root, relative).text
    except (FileAccessError, PathRefusedError):
        return None


def _extract_section(text: str, start_heading: str, end_prefix: str) -> str:
    start = text.find(start_heading)
    if start == -1:
        return text
    start += len(start_heading)
    end = text.find(end_prefix, start)
    return text[start:] if end == -1 else text[start:end]


def _template_version(stage_text: str) -> str:
    match = _TEMPLATE_VERSION_RE.search(stage_text)
    return match.group(1) if match is not None else "unknown"


def _format_precondition_report(report: PreconditionReport) -> str:
    lines = [f"stage: {report.stage_id}", f"all_passed: {report.all_passed}"]
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"[{status}] {result.name}: {result.detail}")
    return "\n".join(lines)


def _tree_state_summary(root: RepositoryRoot) -> tuple[str | None, str | None, str]:
    """Returns `(branch, head_sha, tree_state_summary)`."""
    try:
        status = read_status(root.path)
    except GitReadError as exc:
        return None, None, f"unavailable: {exc.detail}"
    if status.clean:
        summary = "clean"
    else:
        summary = f"{len(status.entries)} changed path(s)"
    return status.branch, status.head, summary


def _render_markdown(
    schema: StageSchema,
    ssp_text: str,
    stage_text: str,
    report: PreconditionReport,
    *,
    branch: str | None,
    head_sha: str | None,
    tree_state: str,
    date: str,
) -> str:
    raw_values = {
        "branch": redact_secrets(branch or "(none)"),
        "head_sha": head_sha or "(unborn)",
        "tree_state": redact_secrets(tree_state),
        "date": date,
        "precondition_report": redact_secrets(_format_precondition_report(report)),
    }

    def data_block(label: str, value: str) -> str:
        longest_run = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
        fence = "`" * max(3, longest_run + 1)
        return f"{label} (data)\n\n{fence}text\n{value}\n{fence}"

    placeholder_values = {name: data_block(name, value) for name, value in raw_values.items()}
    ssp_rendered = substitute(ssp_text, placeholder_values)
    stage_rendered = substitute(stage_text, placeholder_values)

    facts = (
        f"branch: {raw_values['branch']}\n"
        f"head_sha: {raw_values['head_sha']}\n"
        f"tree_state: {raw_values['tree_state']}\n"
        f"date: {raw_values['date']}"
    )
    facts_block = f"## Live Repository Facts (data)\n\n{data_block('live_repository_facts', facts)}"
    precondition_block = "## Precondition Report (data)\n\n" + data_block(
        "precondition_report", raw_values["precondition_report"]
    )

    return (
        "\n\n".join(
            (
                f"# Generated Prompt — {schema.stage_id}",
                facts_block,
                precondition_block,
                f"{_SSP_HEADING}{ssp_rendered}",
                stage_rendered,
            )
        )
        + "\n"
    )


def generate_stage_prompt(
    snapshot: RepositorySnapshot,
    stage_id: str,
    *,
    store: PromptStore,
    audit_log: PromptAuditLog,
    client_token: str | None = None,
    now: Callable[[], datetime] = utc_now,
) -> GeneratedPromptRecord | PreconditionReport:
    """Evaluate preconditions for `stage_id`; on success render, hash, store, and audit a new
    prompt; on failure, audit the refusal and return the unmet `PreconditionReport`.

    Raises `UnknownStageError` for a `stage_id` outside the ten coded DASH stages — the caller
    turns that into a typed 404, distinct from a 422 refusal for a real, known stage.
    """
    if client_token is not None:
        cached = store.get_by_token(client_token)
        if cached is not None:
            return cached

    report = evaluate_preconditions(snapshot, stage_id)
    if report is None:
        raise UnknownStageError(f"unknown stage id: {stage_id!r}")

    if not report.all_passed:
        audit_log.record(
            AuditEntry(
                kind="refused",
                stage_id=stage_id,
                at=now().isoformat(),
                detail=redact_secrets("; ".join(f"{r.name}: {r.detail}" for r in report.unmet)),
            )
        )
        return report

    schema = STAGE_SCHEMA_BY_ID[stage_id]
    root = snapshot.root
    # Source completeness is a precondition, so these reads cannot silently turn a missing or
    # truncated contract into an empty prompt.  Re-read after the gate to render the exact bytes
    # currently present; a raced-away source is refused by the second precondition evaluation.
    readme_text = redact_secrets(_read_or_none(root, _SSP_README_PATH) or "")
    ssp_text = _extract_section(readme_text, _SSP_HEADING, "\n## ")
    stage_prompt_path = f"docs/agentos-dashboard/{schema.prompt_path}"
    stage_text = redact_secrets(_read_or_none(root, stage_prompt_path) or "")
    template_version = _template_version(stage_text)

    final_report = evaluate_preconditions(snapshot, stage_id)
    if final_report is None or not final_report.all_passed:
        refused = final_report or report
        audit_log.record(
            AuditEntry(
                kind="refused",
                stage_id=stage_id,
                at=now().isoformat(),
                detail="repository evidence changed during generation",
            )
        )
        return refused

    branch, head_sha, tree_state = _tree_state_summary(root)
    generated_at = now()
    markdown = _render_markdown(
        schema,
        ssp_text,
        stage_text,
        report,
        branch=branch,
        head_sha=head_sha,
        tree_state=tree_state,
        date=generated_at.date().isoformat(),
    )
    sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    record = GeneratedPromptRecord(
        prompt_uuid=str(uuid.uuid4()),
        stage_id=stage_id,
        template_version=template_version,
        generated_at=generated_at.isoformat(),
        sha256=sha256,
        markdown=markdown,
        filename=f"{stage_id}-prompt-{sha256[:12]}.md",
    )
    store.add(record, client_token=client_token)
    audit_log.record(
        AuditEntry(
            kind="generated",
            stage_id=stage_id,
            at=record.generated_at,
            detail=record.prompt_uuid,
        )
    )
    return record
