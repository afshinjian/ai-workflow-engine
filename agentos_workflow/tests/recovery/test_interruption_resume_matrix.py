"""AUTO-007 §4a deliverable: the interruption/resume matrix (`TEST_STRATEGY.md` §4a,
`WORKFLOW_STATES.md` §3/§6).

`test_engine_resume.py` already proves the resume mechanics in depth, but every one of its
`TestAuthorizationBindingDrift` cases resumes from `AUTHORIZED` alone. `WORKFLOW_STATES.md` §3's
prose names eight states where "interruption/resume detects authorization-bound-value drift" is
a distinct `-> FAILED` reason: `BRANCH_CREATED`, `IMPLEMENTING`, `REPAIRING`, `READY_TO_COMMIT`,
`COMMITTED`, `PUSHED`, `AUTO_MERGE_ENABLED`, `MERGED`. This module is what TEST_STRATEGY.md §4a
calls "at each state": one dedicated test per state, seeding real transition history up to that
state via the same public `authorize()`/`StateTransitionRecord` machinery
`test_engine_resume.py` already uses, then resuming with an independently drifted
`current_binding` and asserting the workflow fails closed and the lock is released — never
silently continuing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_workflow.orchestrator.engine import (
    AuthorizationBindingDriftError,
    WorkflowState,
    resume_workflow,
)
from agentos_workflow.orchestrator.state_store import StateStore
from agentos_workflow.tests.test_engine_resume import (
    _context,
    _current_binding,
    _lock,
    _seed_authorized,
    _store,
    _transition,
    _write_happy_path,
)

# States reachable through `_write_happy_path`'s own linear chain (`test_engine_resume.py`).
_REACHABLE_VIA_HAPPY_PATH = (
    WorkflowState.BRANCH_CREATED,
    WorkflowState.IMPLEMENTING,
    WorkflowState.READY_TO_COMMIT,
    WorkflowState.COMMITTED,
    WorkflowState.PUSHED,
    WorkflowState.AUTO_MERGE_ENABLED,
    WorkflowState.MERGED,
)

# The eight states `WORKFLOW_STATES.md` §3 prose names for this drift reason, in table order.
ALL_DRIFT_TESTABLE_STATES = (
    WorkflowState.BRANCH_CREATED,
    WorkflowState.IMPLEMENTING,
    WorkflowState.REPAIRING,
    WorkflowState.READY_TO_COMMIT,
    WorkflowState.COMMITTED,
    WorkflowState.PUSHED,
    WorkflowState.AUTO_MERGE_ENABLED,
    WorkflowState.MERGED,
)


def _seed_to_repairing(store: StateStore, tmp_path: Path) -> None:
    """`REPAIRING` is not on `_write_happy_path`'s linear chain (it is only ever reached via
    `VALIDATING -> REPAIRING`, `WORKFLOW_STATES.md` §3), so it needs its own short seed."""
    _seed_authorized(store, tmp_path)
    for from_state, to_state in [
        ("AUTHORIZED", "PRECONDITIONS_CHECKED"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED"),
        ("BRANCH_CREATED", "IMPLEMENTING"),
        ("IMPLEMENTING", "VALIDATING"),
        ("VALIDATING", "REPAIRING"),
    ]:
        store.record_transition(
            _transition(tmp_path=tmp_path, from_state=from_state, to_state=to_state)
        )


def _seed_to(store: StateStore, tmp_path: Path, state: WorkflowState) -> None:
    if state is WorkflowState.REPAIRING:
        _seed_to_repairing(store, tmp_path)
    else:
        _write_happy_path(store, tmp_path, up_to=state)


class TestAuthorizationBindingDriftAtEachState:
    """One dedicated test per state named in `WORKFLOW_STATES.md` §3's drift-reachability list —
    the matrix `TEST_STRATEGY.md` §4a requires "at each state"."""

    @pytest.mark.parametrize("state", ALL_DRIFT_TESTABLE_STATES, ids=lambda s: s.value)
    def test_drifted_baseline_commit_sha_fails_closed(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        store = _store(tmp_path)
        _seed_to(store, tmp_path, state)
        lock = _lock(tmp_path)

        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            resume_workflow(
                _context(),
                state_store=store,
                lock=lock,
                current_binding=_current_binding(tmp_path, baseline_commit_sha="f" * 40),
            )

        assert exc_info.value.field == "baseline_commit_sha"
        assert not lock.is_held, f"a rejected resume from {state.value} must release the lock"

    def test_every_named_state_is_exercised(self) -> None:
        """A structural guard against silently dropping a state from the matrix above: if
        `WORKFLOW_STATES.md` §3's prose ever names a ninth state for this drift reason, this
        assertion (not just the parametrize list) is what forces this file to be updated."""
        assert set(ALL_DRIFT_TESTABLE_STATES) == {
            WorkflowState.BRANCH_CREATED,
            WorkflowState.IMPLEMENTING,
            WorkflowState.REPAIRING,
            WorkflowState.READY_TO_COMMIT,
            WorkflowState.COMMITTED,
            WorkflowState.PUSHED,
            WorkflowState.AUTO_MERGE_ENABLED,
            WorkflowState.MERGED,
        }

    @pytest.mark.parametrize("state", _REACHABLE_VIA_HAPPY_PATH, ids=lambda s: s.value)
    def test_a_clean_resume_with_no_drift_still_reaches_the_seeded_state(
        self, tmp_path: Path, state: WorkflowState
    ) -> None:
        """Negative control for the matrix above: without this, a bug that made every resume
        fail (drifted or not) would still pass every drift test in this file."""
        store = _store(tmp_path)
        _seed_to(store, tmp_path, state)
        lock = _lock(tmp_path)

        resumed = resume_workflow(
            _context(),
            state_store=store,
            lock=lock,
            current_binding=_current_binding(tmp_path),
        )

        assert resumed.machine.state is state
        assert lock.is_held
