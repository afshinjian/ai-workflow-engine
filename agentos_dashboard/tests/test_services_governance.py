"""`services.governance`: the fixed-allowlist document browser and bounded search (DR-090/091,
added to DASH-007 by PLAN-001)."""

from __future__ import annotations

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.governance import (
    GOVERNANCE_DOCUMENTS,
    MAX_QUERY_LENGTH,
    GovernanceQueryRefused,
    GovernanceQueryTooLong,
    render_document,
    search_governance,
)
from agentos_dashboard.tests.conftest import write


def test_every_allowlisted_document_has_a_unique_id_and_path() -> None:
    ids = [doc.doc_id for doc in GOVERNANCE_DOCUMENTS]
    paths = [doc.path for doc in GOVERNANCE_DOCUMENTS]
    assert len(ids) == len(set(ids))
    assert len(paths) == len(set(paths))


def test_authority_labels_distinguish_task_source_from_derived_mirrors() -> None:
    by_id = {doc.doc_id: doc for doc in GOVERNANCE_DOCUMENTS}
    assert by_id["task-queue"].authority == "authoritative task record"
    assert by_id["current-task"].authority == "derived mirror"
    assert by_id["remaining-tasks"].authority == "derived mirror"


def test_render_document_unknown_identifier_returns_none_without_touching_filesystem(
    root: RepositoryRoot,
) -> None:
    """Acceptance: an unknown document identifier is refused (404 at the API layer)."""
    assert render_document(root, "not-a-real-doc") is None


def test_render_document_traversal_shaped_identifier_is_refused(root: RepositoryRoot) -> None:
    """Acceptance: a traversal-shaped identifier is refused without touching the filesystem
    outside the allowlist — identifiers are opaque dict keys, never paths, so this is
    structural: `../etc/passwd` simply is not a key in the allowlist."""
    for hostile in ("../../etc/passwd", "docs/AGENT_PROTOCOL.md", "/etc/passwd", "..%2f..%2f"):
        assert render_document(root, hostile) is None


def test_render_document_renders_headings_and_escapes_content(root: RepositoryRoot) -> None:
    write(
        root.path,
        "docs/AGENT_PROTOCOL.md",
        "# Title\n\nSome **bold** and `docs/CONTEXT.md` text.\n",
    )
    write(root.path, "docs/CONTEXT.md", "# Context\n")
    document = render_document(root, "agent-protocol")
    assert document is not None
    assert document.degraded is False
    assert document.headings and document.headings[0].text == "Title"
    assert "<strong>bold</strong>" in (document.rendered_html or "")
    # Cross-reference resolution: a backtick-quoted path to another allowlisted document links.
    assert '<a href="/governance/context">' in (document.rendered_html or "")


def test_render_document_resolves_allowlisted_markdown_links(root: RepositoryRoot) -> None:
    write(
        root.path,
        "docs/DECISION_LOG.md",
        "[Audit](GOVERNANCE_AUDIT.md) and [unsafe](javascript:alert(1))\n",
    )
    write(root.path, "docs/GOVERNANCE_AUDIT.md", "# Audit\n")
    document = render_document(root, "decision-log")
    assert document is not None
    rendered = document.rendered_html or ""
    assert '<a href="/governance/governance-audit">Audit</a>' in rendered
    assert 'href="javascript:' not in rendered
    assert "[unsafe](javascript:alert(1))" in rendered


def test_render_document_escapes_hostile_script_content(root: RepositoryRoot) -> None:
    write(
        root.path,
        "docs/AGENT_PROTOCOL.md",
        "# Title\n\n<script>alert(1)</script> and `<img src=x>`\n",
    )
    document = render_document(root, "agent-protocol")
    assert document is not None
    rendered = document.rendered_html or ""
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<img" not in rendered


def test_render_document_degrades_on_unterminated_code_fence(root: RepositoryRoot) -> None:
    write(root.path, "docs/AGENT_PROTOCOL.md", "# Title\n\n```text\nunterminated\n")
    document = render_document(root, "agent-protocol")
    assert document is not None
    assert document.degraded is True
    assert document.rendered_html is None
    assert document.raw_text  # raw fallback always available
    assert any(f.rule == "governance_render_degraded" for f in document.findings)


def test_render_document_hostile_nul_token_shape_never_crashes(root: RepositoryRoot) -> None:
    write(root.path, "docs/AGENT_PROTOCOL.md", "before \x000\x00 after `code`\n")
    document = render_document(root, "agent-protocol")
    assert document is not None
    assert document.degraded is False
    assert "before" in (document.rendered_html or "")


def test_render_document_malformed_utf8_degrades_to_raw_with_finding(root: RepositoryRoot) -> None:
    target = root.path / "docs/AGENT_PROTOCOL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"# valid\n\xff malformed\n")
    document = render_document(root, "agent-protocol")
    assert document is not None
    assert document.degraded is True
    assert document.rendered_html is None
    assert "\ufffd" in document.raw_text
    assert any(f.rule == "governance_render_degraded" for f in document.findings)


def test_render_document_missing_file_degrades_with_finding(root: RepositoryRoot) -> None:
    document = render_document(root, "agent-protocol")
    assert document is not None
    assert document.degraded is True
    assert document.rendered_html is None
    assert any(f.rule == "document_missing" for f in document.findings)


def test_search_governance_rejects_overlong_query(root: RepositoryRoot) -> None:
    try:
        search_governance(root, "x" * (MAX_QUERY_LENGTH + 1))
    except GovernanceQueryTooLong:
        pass
    else:
        raise AssertionError("expected GovernanceQueryTooLong")


def test_search_governance_refuses_traversal_shaped_query_before_file_reads(
    root: RepositoryRoot, monkeypatch
) -> None:
    def unexpected_read(*args, **kwargs):
        raise AssertionError("traversal-shaped query reached the filesystem")

    monkeypatch.setattr("agentos_dashboard.services.governance.read_text", unexpected_read)
    for query in ("../../etc/passwd", "/etc/passwd", "..\\..\\secret"):
        try:
            search_governance(root, query)
        except GovernanceQueryRefused:
            pass
        else:
            raise AssertionError("expected GovernanceQueryRefused")


def test_search_governance_accepts_query_at_the_exact_limit(root: RepositoryRoot) -> None:
    write(root.path, "README.md", "needle\n")
    search = search_governance(root, "x" * MAX_QUERY_LENGTH)
    assert search.results == ()


def test_search_governance_finds_matches_across_documents(root: RepositoryRoot) -> None:
    write(root.path, "README.md", "line one\nfindme here\nline three\n")
    write(root.path, "docs/CONTEXT.md", "unrelated content\n")
    results = search_governance(root, "findme").results
    assert len(results) == 1
    assert results[0].doc_id == "readme"
    assert results[0].line == 2
    assert "findme" in results[0].snippet


def test_search_governance_empty_query_returns_no_results(root: RepositoryRoot) -> None:
    write(root.path, "README.md", "content\n")
    assert search_governance(root, "").results == ()
    assert search_governance(root, "   ").results == ()


def test_search_governance_caps_results(root: RepositoryRoot) -> None:
    write(root.path, "README.md", "\n".join(["needle"] * 500) + "\n")
    results = search_governance(root, "needle").results
    assert len(results) <= 200


def test_search_governance_reports_unreadable_allowlisted_documents(root: RepositoryRoot) -> None:
    write(root.path, "README.md", "needle\n")
    search = search_governance(root, "needle")
    assert search.results and search.results[0].doc_id == "readme"
    assert any(
        finding.rule == "document_missing" and "docs/AGENT_PROTOCOL.md" in finding.sources
        for finding in search.findings
    )
