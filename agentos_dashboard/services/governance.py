"""DR-090/091 (`PRODUCT_SPEC.md`), added to this stage's contract by PLAN-001: a strictly
read-only governance document browser and bounded full-text search over a fixed, coded
allowlist — never an arbitrary repository browser (`DASH-007.md` Build section).

A document is addressed only by an opaque coded identifier (`GovernanceDocument.doc_id`), never
by a caller-supplied path: `render_document`/`search_governance` look the identifier up in
`GOVERNANCE_DOCUMENTS_BY_ID`, a fixed `dict` built at import time, so a traversal-shaped or
unknown identifier simply misses that dict and is refused before any filesystem call is made —
the same "refused without touching the filesystem" property `core.paths` gives path-shaped input,
achieved here by never accepting a path as input at all.

Rendering is a small, dependency-free Markdown-*lite* transform (headings with anchors, fenced
code, bold, inline code, and cross-reference links between allowlisted documents), not a
CommonMark implementation — this package's `dashboard` dependency group
(`docs/agentos-dashboard/OPEN_QUESTIONS.md` OD-D9) is FastAPI/Jinja2/Uvicorn only, and adding a
Markdown library is outside this stage's authorization. Every text fragment is escaped with
`html.escape` before assembly; nothing from repository content is ever passed through as trusted
HTML (`SECURITY_MODEL.md` SC-04). A render that raises degrades to the raw-source fallback plus a
finding, never a crash (SC-34).
"""

from __future__ import annotations

import html
import posixpath
import re
from dataclasses import dataclass

from agentos_dashboard.core import DEFAULT_MAX_READ_BYTES, DashboardError
from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.services.consistency import ConsistencyFinding, ConsistencySeverity

__all__ = [
    "GOVERNANCE_DOCUMENTS",
    "GOVERNANCE_DOCUMENTS_BY_ID",
    "MAX_QUERY_LENGTH",
    "MAX_SEARCH_RESULTS",
    "GovernanceDocument",
    "GovernanceQueryRefused",
    "GovernanceQueryTooLong",
    "GovernanceSearch",
    "Heading",
    "RenderedDocument",
    "SearchResult",
    "list_governance_documents",
    "render_document",
    "search_governance",
]

MAX_QUERY_LENGTH = 200
MAX_SEARCH_RESULTS = 200


@dataclass(frozen=True)
class GovernanceDocument:
    """One DR-090 allowlisted document: a stable identifier independent of filesystem layout."""

    doc_id: str
    path: str
    title: str
    authority: str


# DR-090's exact list, verbatim: `README.md`, `self-governance.yaml`,
# `docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, the governance mirrors, `docs/DECISION_LOG.md`,
# `docs/GOVERNANCE_AUDIT.md`, and the orchestration package's own top-level Markdown documents
# (`docs/implementation/orchestration/*.md` — its YAML state files are data already covered by
# `parsing.orchestration`/`services.consistency`, not "package documents" in DR-090's sense).
GOVERNANCE_DOCUMENTS: tuple[GovernanceDocument, ...] = (
    GovernanceDocument("readme", "README.md", "README", "informational"),
    GovernanceDocument(
        "self-governance",
        "self-governance.yaml",
        "self-governance.yaml",
        "authoritative configuration",
    ),
    GovernanceDocument(
        "agent-protocol", "docs/AGENT_PROTOCOL.md", "Agent Protocol", "authoritative policy"
    ),
    GovernanceDocument("context", "docs/CONTEXT.md", "Context", "informational"),
    GovernanceDocument(
        "project-state", "docs/PROJECT_STATE.md", "Project State", "authoritative project record"
    ),
    GovernanceDocument(
        "task-queue", "docs/TASK_QUEUE.md", "Task Queue", "authoritative task record"
    ),
    GovernanceDocument("current-task", "docs/current_task.md", "Current Task", "derived mirror"),
    GovernanceDocument(
        "remaining-tasks", "docs/remaining_tasks.md", "Remaining Tasks", "derived mirror"
    ),
    GovernanceDocument(
        "decision-log", "docs/DECISION_LOG.md", "Decision Log", "authoritative record"
    ),
    GovernanceDocument(
        "governance-audit", "docs/GOVERNANCE_AUDIT.md", "Governance Audit", "authoritative record"
    ),
    GovernanceDocument(
        "orch-readme",
        "docs/implementation/orchestration/README.md",
        "Orchestration — README",
        "informational",
    ),
    GovernanceDocument(
        "orch-architecture",
        "docs/implementation/orchestration/architecture-v3.md",
        "Orchestration — Architecture v3",
        "informational",
    ),
    GovernanceDocument(
        "orch-decision-log",
        "docs/implementation/orchestration/decision-log.md",
        "Orchestration — Decision Log",
        "authoritative record",
    ),
    GovernanceDocument(
        "orch-implementation-plan",
        "docs/implementation/orchestration/implementation-plan.md",
        "Orchestration — Implementation Plan",
        "informational",
    ),
    GovernanceDocument(
        "orch-session-protocol",
        "docs/implementation/orchestration/session-protocol.md",
        "Orchestration — Session Protocol",
        "informational",
    ),
)

GOVERNANCE_DOCUMENTS_BY_ID: dict[str, GovernanceDocument] = {
    doc.doc_id: doc for doc in GOVERNANCE_DOCUMENTS
}
_PATH_TO_DOC_ID: dict[str, str] = {doc.path: doc.doc_id for doc in GOVERNANCE_DOCUMENTS}


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    anchor: str


@dataclass(frozen=True)
class RenderedDocument:
    """PG-08's per-document aggregate."""

    doc_id: str
    title: str
    authority: str
    path: str
    raw_text: str
    rendered_html: str | None
    headings: tuple[Heading, ...]
    truncated: bool
    degraded: bool
    findings: tuple[ConsistencyFinding, ...]


@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    title: str
    line: int
    snippet: str


@dataclass(frozen=True)
class GovernanceSearch:
    """A bounded result set plus fail-visible corpus-read findings."""

    results: tuple[SearchResult, ...]
    findings: tuple[ConsistencyFinding, ...]


class GovernanceQueryTooLong(DashboardError):
    """A search query exceeded `MAX_QUERY_LENGTH` (`API_SPEC.md` EP-08)."""


class GovernanceQueryRefused(DashboardError):
    """A search query was traversal-shaped and was refused before any file read."""


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^```")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_INLINE_TOKEN_RE = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\n]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9\s-]")
_SLUG_SPACE_RE = re.compile(r"\s+")
_SAFE_FRAGMENT_RE = re.compile(r"[A-Za-z0-9_-]+")
_TRAVERSAL_QUERY_RE = re.compile(
    r"(?:^|[\\/])\.\.(?:[\\/]|$)|^\s*[\\/]|%2e%2e(?:%2f|%5c)", re.IGNORECASE
)


def _slugify(text: str) -> str:
    lowered = _SLUG_STRIP_RE.sub("", text.lower())
    slug = _SLUG_SPACE_RE.sub("-", lowered).strip("-")
    return slug or "section"


def _escaped_emphasis(text: str) -> str:
    escaped = html.escape(text)
    return _BOLD_RE.sub(lambda match: f"<strong>{match.group(1)}</strong>", escaped)


def _cross_reference_href(source_path: str, target: str) -> str | None:
    """Resolve a Markdown/code-span target without touching the filesystem.

    Only a path already present in the fixed allowlist can produce a link.  Root-relative-looking
    repository paths are tried first, then a path relative to the source document.  URL schemes,
    absolute paths, traversal outside the repository, and unsafe fragments remain escaped text.
    """
    path, separator, fragment = target.partition("#")
    if separator and (not fragment or _SAFE_FRAGMENT_RE.fullmatch(fragment) is None):
        return None
    if not path:
        normalized = source_path
    elif path.startswith(("/", "\\")) or ":" in path:
        return None
    elif path in _PATH_TO_DOC_ID:
        normalized = path
    else:
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), path))
        if normalized == ".." or normalized.startswith("../"):
            return None
    doc_id = _PATH_TO_DOC_ID.get(normalized)
    if doc_id is None:
        return None
    suffix = f"#{fragment}" if separator else ""
    return f"/governance/{doc_id}{suffix}"


def _inline_html(text: str, source_path: str) -> str:
    """Escape-first inline rendering with allowlist-only cross-reference links.

    Segments are assembled directly rather than through sentinel strings, so hostile repository
    bytes (including NUL-delimited digit sequences) cannot be mistaken for renderer metadata.
    """
    rendered: list[str] = []
    position = 0
    for match in _INLINE_TOKEN_RE.finditer(text):
        rendered.append(_escaped_emphasis(text[position : match.start()]))
        code_content = match.group(1)
        if code_content is not None:
            escaped = html.escape(code_content)
            href = _cross_reference_href(source_path, code_content)
            rendered.append(
                f'<a href="{href}"><code>{escaped}</code></a>'
                if href is not None
                else f"<code>{escaped}</code>"
            )
        else:
            label = match.group(2) or ""
            target = match.group(3) or ""
            href = _cross_reference_href(source_path, target)
            rendered.append(
                f'<a href="{href}">{_escaped_emphasis(label)}</a>'
                if href is not None
                else html.escape(match.group(0))
            )
        position = match.end()
    rendered.append(_escaped_emphasis(text[position:]))
    return "".join(rendered)


def _render_body(text: str, source_path: str) -> tuple[str, tuple[Heading, ...]]:
    headings: list[Heading] = []
    blocks: list[str] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False
    in_list = False
    seen_anchors: dict[str, int] = {}

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    def flush_paragraph() -> None:
        close_list()
        if paragraph:
            blocks.append(f"<p>{_inline_html(' '.join(paragraph), source_path)}</p>")
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if _FENCE_RE.match(line):
            if in_code:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            anchor = _slugify(heading_text)
            seen = seen_anchors.get(anchor, 0)
            seen_anchors[anchor] = seen + 1
            if seen:
                anchor = f"{anchor}-{seen}"
            headings.append(Heading(level=level, text=heading_text, anchor=anchor))
            blocks.append(
                f'<h{level} id="{anchor}">{_inline_html(heading_text, source_path)}</h{level}>'
            )
            continue

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue

        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            if paragraph:
                flush_paragraph()
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{_inline_html(bullet_match.group(1), source_path)}</li>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    if in_code:
        raise ValueError("unterminated fenced code block")
    return "\n".join(blocks), tuple(headings)


def list_governance_documents() -> tuple[GovernanceDocument, ...]:
    return GOVERNANCE_DOCUMENTS


def render_document(root: RepositoryRoot, doc_id: str) -> RenderedDocument | None:
    """Render one allowlisted document, or `None` for an unknown identifier (the caller turns
    that into a typed 404 — `api.governance`). No filesystem call is made for an identifier not
    already present in `GOVERNANCE_DOCUMENTS_BY_ID`."""
    doc = GOVERNANCE_DOCUMENTS_BY_ID.get(doc_id)
    if doc is None:
        return None

    try:
        read = read_text(root, doc.path, max_bytes=DEFAULT_MAX_READ_BYTES)
    except (FileAccessError, PathRefusedError) as exc:
        return RenderedDocument(
            doc_id=doc.doc_id,
            title=doc.title,
            authority=doc.authority,
            path=doc.path,
            raw_text="",
            rendered_html=None,
            headings=(),
            truncated=False,
            degraded=True,
            findings=(
                ConsistencyFinding(
                    rule="document_missing",
                    severity=ConsistencySeverity.ERROR,
                    message=f"{doc.path} could not be read: {exc}",
                    sources=(doc.path,),
                ),
            ),
        )

    try:
        if read.decoded_with_replacement:
            raise ValueError("document contains malformed UTF-8")
        rendered_html, headings = _render_body(read.text, doc.path)
        degraded = False
        findings: tuple[ConsistencyFinding, ...] = ()
    except ValueError as exc:
        rendered_html = None
        headings = ()
        degraded = True
        findings = (
            ConsistencyFinding(
                rule="governance_render_degraded",
                severity=ConsistencySeverity.WARNING,
                message=f"{doc.path} could not be rendered ({exc}); showing raw source",
                sources=(doc.path,),
            ),
        )

    return RenderedDocument(
        doc_id=doc.doc_id,
        title=doc.title,
        authority=doc.authority,
        path=doc.path,
        raw_text=read.text,
        rendered_html=rendered_html,
        headings=headings,
        truncated=read.truncated,
        degraded=degraded,
        findings=findings,
    )


def search_governance(root: RepositoryRoot, query: str) -> GovernanceSearch:
    """Bounded, escape-safe-at-render-time full-text search over every allowlisted document.

    Raises `GovernanceQueryTooLong` before touching the filesystem when `query` exceeds
    `MAX_QUERY_LENGTH` characters (`API_SPEC.md` EP-08). Results are capped at
    `MAX_SEARCH_RESULTS`; a hostile (script-injection-shaped) line is returned as a plain string
    snippet — the HTML page renders it through Jinja2's default autoescaping, never raw.
    """
    if len(query) > MAX_QUERY_LENGTH:
        raise GovernanceQueryTooLong(f"query exceeds {MAX_QUERY_LENGTH} characters")
    if _TRAVERSAL_QUERY_RE.search(query):
        raise GovernanceQueryRefused("traversal-shaped search query is not allowed")
    stripped = query.strip()
    if not stripped:
        return GovernanceSearch(results=(), findings=())
    needle = stripped.lower()

    results: list[SearchResult] = []
    findings: list[ConsistencyFinding] = []
    for doc in GOVERNANCE_DOCUMENTS:
        try:
            read = read_text(root, doc.path)
        except (FileAccessError, PathRefusedError) as exc:
            findings.append(
                ConsistencyFinding(
                    rule="document_missing",
                    severity=ConsistencySeverity.ERROR,
                    message=f"{doc.path} could not be searched: {exc}",
                    sources=(doc.path,),
                )
            )
            continue
        if read.truncated or read.decoded_with_replacement:
            findings.append(
                ConsistencyFinding(
                    rule="governance_search_degraded",
                    severity=ConsistencySeverity.WARNING,
                    message=(
                        f"{doc.path} search input is "
                        f"{'truncated' if read.truncated else 'malformed UTF-8'}"
                    ),
                    sources=(doc.path,),
                )
            )
        for line_number, line in enumerate(read.text.splitlines(), start=1):
            if needle in line.lower():
                results.append(
                    SearchResult(
                        doc_id=doc.doc_id,
                        title=doc.title,
                        line=line_number,
                        snippet=line.strip()[:300],
                    )
                )
                if len(results) >= MAX_SEARCH_RESULTS:
                    return GovernanceSearch(results=tuple(results), findings=tuple(findings))
    return GovernanceSearch(results=tuple(results), findings=tuple(findings))
