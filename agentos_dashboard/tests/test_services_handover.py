"""DR-100..102 — `services.handover`: the handover viewer's aggregate (DASH-006)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.core.snapshot import build_snapshot
from agentos_dashboard.services.handover import build_handover_view

from .conftest import write


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_handover_view_without_a_manifest_reports_document_missing(root: RepositoryRoot) -> None:
    data = build_handover_view(build_snapshot(root))
    assert data.records == ()
    assert any(f.rule == "document_missing" for f in data.findings)


def test_handover_view_verifies_a_matching_manifest_row(workspace: Path) -> None:
    narrative = "# Handover\n\nEverything is fine.\n"
    write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    digest = _digest(narrative)
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "Recompute size + sha256sum to refresh this manifest.\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(narrative.encode('utf-8'))} | 2026-01-01 | "
        f"{digest} |\n",
    )
    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert len(data.records) == 1
    record = data.records[0]
    assert record.exists is True
    assert record.size_match is True
    assert record.digest_match is True
    assert not data.findings
    assert "Recompute size" in data.manifest_instructions
    assert data.narrative_text == narrative


def test_handover_view_redacts_narrative_but_checksum_verification_still_uses_raw_bytes(
    workspace: Path,
) -> None:
    """SC-09: the displayed narrative redacts secret-shaped content, but this is a display-only
    copy — `digest_match` is still computed from the file's real, unredacted bytes (DR-100), so
    a genuine narrative checksum still verifies even though the narrative it summarizes happened
    to contain a pasted credential."""
    narrative = "# Handover\n\napi_key=abcd1234efgh5678wxyz was rotated.\n"
    write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    digest = _digest(narrative)
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "Recompute size + sha256sum to refresh this manifest.\n\n"
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(narrative.encode('utf-8'))} | 2026-01-01 | "
        f"{digest} |\n",
    )
    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert data.records[0].digest_match is True
    assert data.narrative_text is not None
    assert "abcd1234efgh5678wxyz" not in data.narrative_text
    assert "[REDACTED]" in data.narrative_text


def test_handover_view_reports_a_missing_referenced_file(workspace: Path) -> None:
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | 10 | 2026-01-01 | {'a' * 64} |\n",
    )
    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert len(data.records) == 1
    assert data.records[0].exists is False
    assert any(f.rule == "handover_file_missing" for f in data.findings)


def test_handover_view_reports_a_size_mismatch(workspace: Path) -> None:
    narrative = "content\n"
    write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | 999999 | 2026-01-01 | {_digest(narrative)} |\n",
    )
    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert data.records[0].size_match is False
    assert any(f.rule == "handover_size_mismatch" for f in data.findings)


def test_handover_view_reports_a_digest_mismatch(workspace: Path) -> None:
    narrative = "content\n"
    write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    write(
        workspace,
        "handover/PROJECT_CHECKSUM.md",
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | {len(narrative.encode('utf-8'))} | 2026-01-01 | "
        f"{'f' * 64} |\n",
    )
    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert data.records[0].size_match is True
    assert data.records[0].digest_match is False
    assert any(f.rule == "handover_checksum_mismatch" for f in data.findings)


def test_handover_view_is_stale_when_narrative_is_older_than_a_governance_mirror(
    workspace: Path,
) -> None:
    import os
    import time

    narrative = "# Handover\n\nOld narrative.\n"
    narrative_path = write(workspace, "handover/PROJECT_HANDOVER.md", narrative)
    old = time.time() - 10_000
    os.utime(narrative_path, (old, old))

    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — thing\n\nStatus: Current\n\n")

    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert data.stale is True
    assert any(f.rule == "handover_narrative_stale" for f in data.findings)


def test_handover_view_is_not_stale_when_narrative_is_newer(workspace: Path) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — thing\n\nStatus: Current\n\n")
    write(workspace, "handover/PROJECT_HANDOVER.md", "# Handover\n\nFresh.\n")
    root = RepositoryRoot.from_path(workspace)
    data = build_handover_view(build_snapshot(root))
    assert data.stale is False
