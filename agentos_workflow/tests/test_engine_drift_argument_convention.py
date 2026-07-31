"""GOV-AUTO-07: one canonical `expected`/`actual` convention for `AuthorizationBindingDriftError`.

Resolves AUTO-008's F-1 finding. `AuthorizationBindingDriftError(field, expected, actual)` was
raised from two authorization-drift call paths that passed those arguments in opposite senses:
`_detect_authorization_binding_drift` passed the independently-supplied *current* value as
`expected` and the persisted `AuthorizationRecord` as `actual`, while
`_validate_live_resume_observation` / `_live_drift` passed the persisted record as `expected` and
the *live observation* as `actual`. `.expected` and `.actual` therefore meant opposite things
depending on which safety path raised.

The canonical convention, now binding at every raise site:

* `expected` is the **reference** — the authorization-bound value where the comparison has one,
  otherwise the invariant the check requires.
* `actual` is the **value under judgement** — the current runtime, repository, live-observation, or
  caller/disk-supplied value found in the reference's place.

Every test here asserts the *sides*, not merely `.field`; `.field` was already correct before this
stage and so could never have caught the inversion. The existing drift suites
(`test_engine_resume.py::TestAuthorizationBindingDrift`, `test_f03_live_resume.py`,
`recovery/test_interruption_resume_matrix.py`) continue to cover which drifts are detected at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.observation import (
    ResumeObservation,
    WorktreeChange,
    canonical_repository_identity,
)
from agentos_workflow.orchestrator.engine import (
    _BINDING_DRIFT_FIELDS,
    AuthorizationBindingDriftError,
    AuthorizationContext,
    AuthorizationRecord,
    CurrentAuthorizationBinding,
    WorkflowState,
    WorkflowStateMachine,
    _detect_authorization_binding_drift,
    _validate_live_resume_observation,
    _validate_persisted_authorization_evidence,
    authorize,
)
from agentos_workflow.orchestrator.state_store import StateStore

_WORKFLOW_ID = "wf-conv"
_IDENTITY = "github.com/org/repo"
_STAGE_ID = "AUTO-002"
_CONTRACT = "docs/contracts/AUTO-002.md"
_CONTRACT_HASH = "sha256:deadbeef"
_BASELINE_SHA = "163bcee1c280bccd6ad4b41fd3840777ef0769f1"
_PLANNED = "feature/auto-002-orchestrator-state-machine"
_ENGINE_VERSION = "0.1.0"


def _repository_path(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir(exist_ok=True)
    return repository


def _store(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def _record(tmp_path: Path, **overrides: object) -> AuthorizationRecord:
    defaults: dict[str, object] = {
        "workflow_id": _WORKFLOW_ID,
        "repository_identity": _IDENTITY,
        "repository_path": str(_repository_path(tmp_path)),
        "stage_id": _STAGE_ID,
        "stage_contract_path": _CONTRACT,
        "stage_contract_hash": _CONTRACT_HASH,
        "baseline_branch": "main",
        "baseline_commit_sha": _BASELINE_SHA,
        "planned_stage_branch": _PLANNED,
        "authorized_at": "2026-07-24T10:00:00+00:00",
        "authorized_by": "human-owner",
        "engine_version": _ENGINE_VERSION,
    }
    defaults.update(overrides)
    return AuthorizationRecord.model_validate(defaults)


def _context(**overrides: object) -> AuthorizationContext:
    defaults: dict[str, object] = {
        "workflow_id": _WORKFLOW_ID,
        "repository_identity": _IDENTITY,
        "stage_id": _STAGE_ID,
        "planned_stage_branch": _PLANNED,
        "baseline_branch": "main",
    }
    defaults.update(overrides)
    return AuthorizationContext.model_validate(defaults)


def _binding(tmp_path: Path, **overrides: object) -> CurrentAuthorizationBinding:
    defaults: dict[str, object] = {
        "repository_path": str(_repository_path(tmp_path)),
        "stage_contract_path": _CONTRACT,
        "stage_contract_hash": _CONTRACT_HASH,
        "baseline_commit_sha": _BASELINE_SHA,
        "engine_version": _ENGINE_VERSION,
    }
    defaults.update(overrides)
    return CurrentAuthorizationBinding.model_validate(defaults)


def _config(tmp_path: Path, **overrides: object) -> WorkflowConfig:
    defaults: dict[str, object] = {
        "repository_path": _repository_path(tmp_path),
        "repository_identity": _IDENTITY,
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/contracts",
        "stage_branch_naming": "feature/{stage_id}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "true",
        "required_github_checks": [],
        "merge_method": "squash",
        "claude_cli_executable": Path("/bin/true"),
        "claude_cli_timeout_seconds": 1,
        "codex_cli_executable": Path("/bin/true"),
        "codex_cli_timeout_seconds": 1,
        "allowed_environment_variables": [],
        "allowed_changed_paths": ["docs/work/**"],
        "forbidden_changed_paths": ["src/**"],
        "repair_attempt_limit": 3,
        "state_directory": tmp_path / "state",
        "audit_directory": tmp_path / "audit",
    }
    defaults.update(overrides)
    return WorkflowConfig.model_validate(defaults)


def _observation(tmp_path: Path, **overrides: object) -> ResumeObservation:
    repository = _repository_path(tmp_path).resolve()
    defaults: dict[str, object] = {
        "canonical_repository_path": str(repository),
        "repository_exists": True,
        "is_git_repository": True,
        "observed_repository_identity": _IDENTITY,
        "current_branch": "main",
        "head_sha": _BASELINE_SHA,
        "baseline_sha": _BASELINE_SHA,
        "planned_branch_sha": None,
        "baseline_is_ancestor_of_planned": None,
        "worktree_changes": (),
        "canonical_contract_path": str(repository / _CONTRACT),
        "contract_exists": True,
        "contract_hash": _CONTRACT_HASH,
        "engine_version": _ENGINE_VERSION,
    }
    defaults.update(overrides)
    return ResumeObservation(**defaults)  # type: ignore[arg-type]


def _assert_message_order(error: AuthorizationBindingDriftError) -> None:
    """The rendered message must present `expected` before `actual`, so the convention the
    attributes now carry is the same one an operator reads off the message.
    """
    message = str(error)
    assert f"expected {error.expected!r}" in message
    assert f"found {error.actual!r}" in message
    assert message.index(f"expected {error.expected!r}") < message.index(f"found {error.actual!r}")


# --------------------------------------------------------------------------------------------
# Cluster 1: `_detect_authorization_binding_drift` — the path F-1 named as inverted.
# --------------------------------------------------------------------------------------------

# field -> (context overrides, current_binding overrides, the drifted current value)
_DRIFTED_CURRENT: dict[str, tuple[dict[str, object], dict[str, object], str]] = {
    "workflow_id": ({"workflow_id": "wf-other"}, {}, "wf-other"),
    "repository_identity": (
        {"repository_identity": "github.com/attacker/repo"},
        {},
        "github.com/attacker/repo",
    ),
    "repository_path": ({}, {"repository_path": "/elsewhere/repo"}, "/elsewhere/repo"),
    "stage_id": ({"stage_id": "AUTO-099"}, {}, "AUTO-099"),
    "stage_contract_path": (
        {},
        {"stage_contract_path": "docs/contracts/AUTO-099.md"},
        "docs/contracts/AUTO-099.md",
    ),
    "stage_contract_hash": (
        {},
        {"stage_contract_hash": "sha256:changedcontents"},
        "sha256:changedcontents",
    ),
    "baseline_branch": ({"baseline_branch": "develop"}, {}, "develop"),
    "baseline_commit_sha": (
        {},
        {"baseline_commit_sha": "f" * 40},
        "f" * 40,
    ),
    "planned_stage_branch": (
        {"planned_stage_branch": "feature/some-other-branch"},
        {},
        "feature/some-other-branch",
    ),
    "engine_version": ({}, {"engine_version": "0.2.0"}, "0.2.0"),
}


class TestBoundVsCurrentPath:
    """`_detect_authorization_binding_drift` must report the persisted record as `expected`."""

    def test_every_drift_checked_field_is_covered(self) -> None:
        """A new binding added to `_BINDING_DRIFT_FIELDS` must not silently escape this suite."""
        assert set(_DRIFTED_CURRENT) == set(_BINDING_DRIFT_FIELDS)

    @pytest.mark.parametrize("field", _BINDING_DRIFT_FIELDS)
    def test_bound_value_is_expected_and_current_value_is_actual(
        self, tmp_path: Path, field: str
    ) -> None:
        context_overrides, binding_overrides, drifted = _DRIFTED_CURRENT[field]
        record = _record(tmp_path)
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _detect_authorization_binding_drift(
                _context(**context_overrides),
                _binding(tmp_path, **binding_overrides),
                record,
            )
        error = exc_info.value
        assert error.field == field
        # The authorization binding is the reference...
        assert error.expected == getattr(record, field)
        # ...and the independently-supplied current value is what was found in its place.
        assert error.actual == drifted
        _assert_message_order(error)

    def test_no_drift_when_current_values_match_the_binding(self, tmp_path: Path) -> None:
        """Guards against a normalization slip turning the argument reordering into a behaviour
        change: identical inputs must still be silent.
        """
        _detect_authorization_binding_drift(_context(), _binding(tmp_path), _record(tmp_path))


# --------------------------------------------------------------------------------------------
# Cluster 2: `_validate_live_resume_observation` / `_live_drift`.
# --------------------------------------------------------------------------------------------


class TestLiveObservationPath:
    def _validate(self, tmp_path: Path, *, record: AuthorizationRecord, **kwargs: object) -> None:
        _validate_live_resume_observation(
            context=_context(),
            record=record,
            machine=WorkflowStateMachine(),
            observation=kwargs.pop("observation", None) or _observation(tmp_path),
            config=kwargs.pop("config", None) or _config(tmp_path),
            state_store=_store(tmp_path),
        )

    def test_bound_repository_path_is_expected_against_the_configured_path(
        self, tmp_path: Path
    ) -> None:
        """Normalized by GOV-AUTO-07: this site previously reported the configured path as
        `expected` and the *binding* as `actual`, the opposite of the binding-vs-current rule the
        very next identity check now follows.
        """
        record = _record(tmp_path, repository_path="/authorized/elsewhere")
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            self._validate(tmp_path, record=record)
        error = exc_info.value
        assert error.field == "repository_path"
        assert error.expected == "/authorized/elsewhere"
        assert error.actual == str(_repository_path(tmp_path).resolve())
        _assert_message_order(error)

    def test_bound_identity_is_expected_against_the_configured_identity(
        self, tmp_path: Path
    ) -> None:
        """Normalized by GOV-AUTO-07: this raise and the observed-identity raise immediately
        below it are two adjacent checks on the same field that previously put the bound identity
        on opposite sides of each other.
        """
        record = _record(tmp_path, repository_identity="github.com/org/authorized-repo")
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            self._validate(tmp_path, record=record)
        error = exc_info.value
        assert error.field == "repository_identity"
        assert error.expected == canonical_repository_identity("github.com/org/authorized-repo")
        assert error.actual == canonical_repository_identity(_IDENTITY)
        _assert_message_order(error)

    def test_bound_identity_is_expected_against_the_observed_identity(self, tmp_path: Path) -> None:
        """Already conforming before GOV-AUTO-07 — pinned so the normalization did not flip it."""
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            self._validate(
                tmp_path,
                record=_record(tmp_path),
                observation=_observation(
                    tmp_path, observed_repository_identity="github.com/attacker/repo"
                ),
            )
        error = exc_info.value
        assert error.field == "repository_identity"
        assert error.expected == canonical_repository_identity(_IDENTITY)
        assert error.actual == canonical_repository_identity("github.com/attacker/repo")
        _assert_message_order(error)

    @pytest.mark.parametrize(
        ("field", "observation_key", "observed", "bound"),
        [
            ("stage_contract_hash", "contract_hash", "sha256:changed", _CONTRACT_HASH),
            ("engine_version", "engine_version", "0.2.0", _ENGINE_VERSION),
            ("baseline_commit_sha", "baseline_sha", "f" * 40, _BASELINE_SHA),
        ],
    )
    def test_conforming_bound_vs_observed_sites_are_unchanged(
        self,
        tmp_path: Path,
        field: str,
        observation_key: str,
        observed: str,
        bound: str,
    ) -> None:
        """These sites already followed the convention; GOV-AUTO-07 must leave them alone."""
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            self._validate(
                tmp_path,
                record=_record(tmp_path),
                observation=_observation(tmp_path, **{observation_key: observed}),
            )
        error = exc_info.value
        assert error.field == field
        assert error.expected == bound
        assert error.actual == observed
        _assert_message_order(error)

    def test_sites_without_a_binding_report_the_required_invariant_as_expected(
        self, tmp_path: Path
    ) -> None:
        """Where neither side is an authorization binding, `expected` carries the invariant the
        check demands and `actual` carries what violated it. This is why the rendered message
        still says "expected/found" rather than re-adopting "bound value".
        """
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            self._validate(
                tmp_path,
                record=_record(tmp_path),
                observation=_observation(
                    tmp_path,
                    worktree_changes=(WorktreeChange("?", "?", "src/forbidden.py"),),
                ),
            )
        error = exc_info.value
        assert error.field == "working_tree_forbidden_paths"
        assert error.expected == "()"
        assert "src/forbidden.py" in error.actual
        _assert_message_order(error)


# --------------------------------------------------------------------------------------------
# Cluster 3: `_validate_persisted_authorization_evidence` cross-record checks.
# --------------------------------------------------------------------------------------------


def _seed_and_tamper(tmp_path: Path, **record_overrides: object) -> StateStore:
    """Authorize through the real API, then overwrite the persisted `AuthorizationRecord` alone,
    leaving the transition history untouched — the only way to make the persisted authorization
    and the persisted transition disagree.
    """
    store = _store(tmp_path)
    record = _record(tmp_path)
    authorize(WorkflowStateMachine(), _context(), record, state_store=store)
    if record_overrides:
        tampered = _record(tmp_path, **record_overrides)
        path = store.state_directory / _WORKFLOW_ID / "authorization.json"
        path.write_text(tampered.model_dump_json(), encoding="utf-8")
    return store


class TestPersistedAuthorizationEvidencePath:
    """The persisted `AuthorizationRecord` is the root of trust when a replayed transition is
    checked against it, so it is `expected` and the transition record is the value judged.
    """

    @pytest.mark.parametrize(
        ("field", "override", "authorized", "transition_attribute"),
        [
            ("workflow_id", {"workflow_id": "wf-authorized"}, "wf-authorized", "workflow_id"),
            (
                "repository_identity",
                {"repository_identity": "github.com/org/authorized-repo"},
                "github.com/org/authorized-repo",
                "target_repository",
            ),
            ("stage_id", {"stage_id": "AUTO-authorized"}, "AUTO-authorized", "stage_id"),
        ],
    )
    def test_authorization_record_is_expected_and_transition_record_is_actual(
        self,
        tmp_path: Path,
        field: str,
        override: dict[str, object],
        authorized: str,
        transition_attribute: str,
    ) -> None:
        store = _seed_and_tamper(tmp_path, **override)
        transition = store.read_transitions(_WORKFLOW_ID)[0]
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _validate_persisted_authorization_evidence(
                WorkflowStateMachine(), record=transition, state_store=store
            )
        error = exc_info.value
        assert error.field == field
        assert error.expected == authorized
        assert error.actual == getattr(transition, transition_attribute)
        _assert_message_order(error)

    def test_repository_path_reports_the_authorized_path_as_expected(self, tmp_path: Path) -> None:
        authorized_path = tmp_path / "authorized-repo"
        authorized_path.mkdir()
        store = _seed_and_tamper(tmp_path, repository_path=str(authorized_path))
        transition = store.read_transitions(_WORKFLOW_ID)[0]
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _validate_persisted_authorization_evidence(
                WorkflowStateMachine(), record=transition, state_store=store
            )
        error = exc_info.value
        assert error.field == "repository_path"
        assert error.expected == str(authorized_path)
        assert error.actual == transition.repository_path
        _assert_message_order(error)

    @pytest.mark.parametrize(
        ("field", "expected", "attribute", "replacement"),
        [
            ("from_state", WorkflowState.CREATED.value, "from_state", WorkflowState.MERGED.value),
            ("actor", "human", "actor", "orchestrator"),
        ],
    )
    def test_required_constant_sites_still_report_the_constant_as_expected(
        self,
        tmp_path: Path,
        field: str,
        expected: str,
        attribute: str,
        replacement: str,
    ) -> None:
        """These three checks have no authorization record on either side; the required constant
        is the reference. Already conforming — pinned so the normalization did not flip them.
        """
        store = _seed_and_tamper(tmp_path)
        transition = store.read_transitions(_WORKFLOW_ID)[0].model_copy(
            update={attribute: replacement}
        )
        with pytest.raises(AuthorizationBindingDriftError) as exc_info:
            _validate_persisted_authorization_evidence(
                WorkflowStateMachine(), record=transition, state_store=store
            )
        error = exc_info.value
        assert error.field == field
        assert error.expected == expected
        assert error.actual == replacement
        _assert_message_order(error)


# --------------------------------------------------------------------------------------------
# The F-1 regression proper: the two paths must now agree with each other.
# --------------------------------------------------------------------------------------------


def test_both_drift_paths_report_the_binding_on_the_same_side(tmp_path: Path) -> None:
    """The defect F-1 named, stated directly: drive the same field's drift through both
    authorization-drift call paths and require that both put the authorization-bound value in
    `.expected`. Before GOV-AUTO-07 these two produced mirror-image payloads for the same
    condition, so an operator or caller reading `.expected` got opposite answers depending on
    which path happened to raise. No assertion on `.field` alone can detect that.
    """
    bound_identity = "github.com/org/authorized-repo"
    record = _record(tmp_path, repository_identity=bound_identity)

    with pytest.raises(AuthorizationBindingDriftError) as bound_vs_current:
        _detect_authorization_binding_drift(
            _context(repository_identity=_IDENTITY), _binding(tmp_path), record
        )

    with pytest.raises(AuthorizationBindingDriftError) as live_observation:
        _validate_live_resume_observation(
            context=_context(),
            record=record,
            machine=WorkflowStateMachine(),
            observation=_observation(tmp_path),
            config=_config(tmp_path),
            state_store=_store(tmp_path),
        )

    assert bound_vs_current.value.field == live_observation.value.field == "repository_identity"
    assert bound_vs_current.value.expected == bound_identity
    assert live_observation.value.expected == canonical_repository_identity(bound_identity)
    assert bound_vs_current.value.actual == _IDENTITY
    assert live_observation.value.actual == canonical_repository_identity(_IDENTITY)


def test_public_exception_attributes_are_unchanged(tmp_path: Path) -> None:
    """GOV-AUTO-07 normalizes argument *meaning*, not the public surface: the attribute names and
    the rendered message shape stay exactly as AUTO-008 left them, so no caller must migrate.
    """
    error = AuthorizationBindingDriftError("engine_version", "0.1.0", "0.2.0")
    assert (error.field, error.expected, error.actual) == ("engine_version", "0.1.0", "0.2.0")
    assert str(error) == (
        "Authorization binding drift on 'engine_version': expected '0.1.0', found '0.2.0'. "
        "Per HUMAN_AUTHORIZATION_MODEL.md §4, this authorization is invalid; the workflow "
        "moves to FAILED and must be re-authorized from CREATED."
    )
