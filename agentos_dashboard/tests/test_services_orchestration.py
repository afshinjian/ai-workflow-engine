"""`services.orchestration`: the read-only ORCH feature-state view (EP-18; TR-09)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.consistency import IMPLEMENTATION_STATE_PATH
from agentos_dashboard.services.orchestration import build_orchestration_view

_WELL_FORMED = """\
schema_name: orchestration-implementation-state
feature_id: ORCH
current_stage: ORCH-001
next_eligible_stage: ORCH-002
delivery_order: [ORCH-000, ORCH-001, ORCH-002]
stages:
  ORCH-000:
    title: Bootstrap
    status: VERIFIED
    prerequisites: []
    blockers: []
    evidence: [e1.yaml]
  ORCH-001:
    title: Validator
    status: IN_PROGRESS
    prerequisites: [ORCH-000]
    blockers: [{code: X, summary: some blocker}]
    evidence: []
"""


def test_missing_document_is_unavailable_not_an_error(workspace: Path) -> None:
    root = RepositoryRoot.from_path(workspace)
    view = build_orchestration_view(root)
    assert view.available is False
    assert view.stages == ()


def test_well_formed_document_is_available_with_stages(workspace: Path) -> None:
    target = workspace / IMPLEMENTATION_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_WELL_FORMED, encoding="utf-8")
    root = RepositoryRoot.from_path(workspace)
    view = build_orchestration_view(root)
    assert view.available is True
    assert view.feature_id == "ORCH"
    assert view.current_stage == "ORCH-001"
    assert len(view.stages) == 2
    stage = next(s for s in view.stages if s.stage_id == "ORCH-001")
    assert stage.blockers == ("some blocker",)


def test_malformed_document_is_unavailable_with_notes(workspace: Path) -> None:
    target = workspace / IMPLEMENTATION_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not: [valid, yaml:\n", encoding="utf-8")
    root = RepositoryRoot.from_path(workspace)
    view = build_orchestration_view(root)
    assert view.available is False
    assert view.notes


def test_build_orchestration_view_never_invokes_subprocess(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EP-18 acceptance: zero Git invocation and zero agent/subprocess invocation."""
    target = workspace / IMPLEMENTATION_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_WELL_FORMED, encoding="utf-8")
    root = RepositoryRoot.from_path(workspace)

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("build_orchestration_view must never invoke a subprocess")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    view = build_orchestration_view(root)
    assert view.available is True
