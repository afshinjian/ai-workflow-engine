"""AUTO-009: the read-only `WorkflowService` boundary.

Two properties dominate this suite, because they are what makes the boundary safe to expose at
all: the surface is *exactly* four operations, and every one of them is read-only in a way that is
demonstrated rather than asserted — the storage tree is hashed before and after each call, and the
repository lock is booby-trapped so any attempt to acquire it fails the test loudly.
"""

import ast
import hashlib
import inspect
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agentos_workflow.config.loader import (
    ConfigurationNotFoundError,
    ConfigurationRepositoryMismatchError,
    InvalidConfigurationError,
)
from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.orchestrator import lock as lock_module
from agentos_workflow.orchestrator.state_store import (
    CommandExecutionRecord,
    StateStore,
    StateStoreCorruptionError,
    StateStoreError,
    StateStorePathConfinementError,
    StateTransitionRecord,
)
from agentos_workflow.service import (
    AuditResult,
    ReportNotFoundError,
    ReportResult,
    StatusResult,
    WorkflowListResult,
    WorkflowNotFoundError,
    WorkflowService,
    WorkflowServiceError,
    open_workflow_service,
)
from agentos_workflow.skills import FailureKind, RetryClassification
from agentos_workflow.skills.reporting import generate_qa_report, generate_stage_report

# The complete, closed set of operations AUTO-009 authorizes. A test below asserts the class has
# exactly these and nothing else, so adding a fifth operation cannot pass unnoticed.
APPROVED_OPERATIONS = frozenset({"status", "list", "audit", "report"})

# Everything AUTO-009 is explicitly forbidden to implement, as it would be spelled on a service or
# a CLI. Checked as a *structural* assertion, not a review convention.
FORBIDDEN_OPERATIONS = frozenset(
    {
        "start",
        "authorize",
        "approve",
        "reject",
        "resume",
        "cancel",
        "prepare",
        "review",
        "implement",
        "commit",
        "push",
        "merge",
    }
)


# ------------------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------------------


def _config_dict(repository: Path, state: Path, audit: Path) -> dict[str, object]:
    return {
        "repository_path": str(repository),
        "repository_identity": "github.com/org/demo",
        "remote_name": "origin",
        "baseline_branch": "main",
        "stage_contract_directory": "docs/stage-prompts",
        "stage_branch_naming": "feature/{stage_id}",
        "test_command": "pytest",
        "lint_command": "ruff check .",
        "formatting_command": "black --check .",
        "security_command": "bandit -r src",
        "required_github_checks": ["ci/tests"],
        "merge_method": "squash",
        "claude_cli_executable": "/usr/local/bin/claude",
        "claude_cli_timeout_seconds": 1800,
        "codex_cli_executable": "/usr/local/bin/codex",
        "codex_cli_timeout_seconds": 1800,
        "allowed_environment_variables": ["PATH"],
        "allowed_changed_paths": ["docs/**"],
        "forbidden_changed_paths": ["src/**"],
        "repair_attempt_limit": 3,
        "state_directory": str(state),
        "audit_directory": str(audit),
    }


@pytest.fixture
def target(tmp_path: Path) -> dict[str, Path]:
    repository = tmp_path / "repo"
    (repository / ".agentos").mkdir(parents=True)
    state = tmp_path / "state"
    audit = tmp_path / "audit"
    (repository / ".agentos" / "workflow.yaml").write_text(
        yaml.safe_dump(_config_dict(repository, state, audit)), encoding="utf-8"
    )
    return {"repository": repository, "state": state, "audit": audit}


@pytest.fixture
def config(target: dict[str, Path]) -> WorkflowConfig:
    return WorkflowConfig.model_validate(
        _config_dict(target["repository"], target["state"], target["audit"])
    )


@pytest.fixture
def service(config: WorkflowConfig) -> WorkflowService:
    return WorkflowService(config)


def _transition(
    workflow_id: str,
    repository: Path,
    *,
    from_state: str,
    to_state: str,
    at: datetime,
    actor: str = "orchestrator",
    evidence: str | None = None,
    stage_id: str = "STAGE-1",
) -> StateTransitionRecord:
    return StateTransitionRecord(
        workflow_id=workflow_id,
        target_repository="github.com/org/demo",
        repository_path=str(repository),
        stage_id=stage_id,
        from_state=from_state,
        to_state=to_state,
        timestamp=at.isoformat(),
        actor=actor,
        gate_evidence_ref=evidence,
    )


@pytest.fixture
def populated(config: WorkflowConfig, target: dict[str, Path]) -> StateStore:
    """One workflow driven to `IMPLEMENTING`, with a command record and two reports."""
    store = StateStore.for_config(config)
    base = datetime(2026, 7, 31, 9, 0, tzinfo=UTC)
    chain = [
        ("CREATED", "AUTHORIZED", "human", "evidence/authorization.json"),
        ("AUTHORIZED", "PRECONDITIONS_CHECKED", "orchestrator", "evidence/preconditions.json"),
        ("PRECONDITIONS_CHECKED", "BRANCH_CREATED", "orchestrator", None),
        ("BRANCH_CREATED", "IMPLEMENTING", "agent:Implementer", None),
    ]
    for index, (from_state, to_state, actor, evidence) in enumerate(chain):
        store.record_transition(
            _transition(
                "wf-1",
                target["repository"],
                from_state=from_state,
                to_state=to_state,
                at=base + timedelta(minutes=index),
                actor=actor,
                evidence=evidence,
            )
        )
    store.record_command_execution(
        "wf-1",
        CommandExecutionRecord(
            normalized_command_identity="run_tests(<argv>)",
            start_time=base.isoformat(),
            completion_time=(base + timedelta(minutes=1)).isoformat(),
            exit_code=0,
            timeout_status=False,
            stdout_ref="wf-1/output/op-1/stdout.txt",
            stderr_ref="wf-1/output/op-1/stderr.txt",
        ),
    )
    assert generate_stage_report(
        audit_root=target["audit"], workflow_id="wf-1", results={"verdict": "PASS"}
    ).ok
    assert generate_qa_report(
        audit_root=target["audit"], workflow_id="wf-1", results={"verdict": "PASS"}, sequence=2
    ).ok
    return store


def _tree_digest(*roots: Path) -> str:
    """A hash of every file's path, mode, and bytes under `roots` — the read-only witness."""
    digest = hashlib.sha256()
    for root in sorted(roots):
        for path in sorted(root.rglob("*")) if root.exists() else []:
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(str(path.lstat().st_mode).encode("utf-8"))
            if path.is_file() and not path.is_symlink():
                digest.update(path.read_bytes())
    return digest.hexdigest()


# ------------------------------------------------------------------------------------------
# The surface itself
# ------------------------------------------------------------------------------------------


class TestApprovedSurface:
    def test_exposes_exactly_the_four_approved_operations(self) -> None:
        public = {
            name
            for name in dir(WorkflowService)
            if not name.startswith("_") and callable(getattr(WorkflowService, name))
        }
        assert public == set(APPROVED_OPERATIONS)

    def test_exposes_no_public_attribute_beyond_those_operations(self) -> None:
        """No property or class attribute hands the `StateStore` (and its append path) back out."""
        assert {name for name in dir(WorkflowService) if not name.startswith("_")} == set(
            APPROVED_OPERATIONS
        )

    @pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_OPERATIONS))
    def test_forbidden_operation_is_absent(self, forbidden: str) -> None:
        assert not hasattr(WorkflowService, forbidden)

    def test_service_instance_holds_no_repository_lock(self, service: WorkflowService) -> None:
        held = [value for value in vars(service).values()]
        assert not any(isinstance(value, lock_module.RepositoryLock) for value in held)

    def test_every_operation_returns_a_typed_result(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        assert isinstance(service.status("wf-1"), StatusResult)
        assert isinstance(service.list(), WorkflowListResult)
        assert isinstance(service.audit("wf-1"), AuditResult)
        assert isinstance(service.report("wf-1"), ReportResult)

    def test_results_are_immutable(self, service: WorkflowService, populated: StateStore) -> None:
        result = service.status("wf-1")
        with pytest.raises(ValidationError):
            result.workflow_count = 99  # type: ignore[misc]


# ------------------------------------------------------------------------------------------
# Read-only proof
# ------------------------------------------------------------------------------------------


class TestReadOnly:
    @pytest.fixture(autouse=True)
    def _forbid_lock_acquisition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Any attempt to take the repository write lock fails the test rather than succeeding.

        Patched on the lock class itself, so it catches an acquisition made through any path — the
        service, anything the service imports, or anything either of them calls.
        """

        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError("a read-only operation attempted to acquire the repository lock")

        for name in ("acquire", "__enter__"):
            if hasattr(lock_module.RepositoryLock, name):
                monkeypatch.setattr(lock_module.RepositoryLock, name, refuse)

    @pytest.mark.parametrize(
        "operation",
        [
            lambda service: service.status(),
            lambda service: service.status("wf-1"),
            lambda service: service.list(),
            lambda service: service.audit("wf-1"),
            lambda service: service.report("wf-1"),
            lambda service: service.report("wf-1", report_kind="stage"),
        ],
    )
    def test_operation_mutates_nothing_and_takes_no_lock(
        self,
        service: WorkflowService,
        populated: StateStore,
        target: dict[str, Path],
        operation: object,
    ) -> None:
        before = _tree_digest(target["state"], target["audit"], target["repository"])
        operation(service)  # type: ignore[operator]
        assert _tree_digest(target["state"], target["audit"], target["repository"]) == before

    def test_repeated_reads_are_identical(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        assert service.audit("wf-1") == service.audit("wf-1")
        assert service.report("wf-1") == service.report("wf-1")
        assert service.list() == service.list()

    def test_list_creates_no_state_directory(
        self, service: WorkflowService, target: dict[str, Path]
    ) -> None:
        """A repository that has never run a workflow stays a repository that has never run one."""
        assert not target["state"].exists()
        assert service.list().workflows == []
        assert not target["state"].exists()
        assert not target["audit"].exists()

    def test_status_without_workflow_creates_no_storage(
        self, service: WorkflowService, target: dict[str, Path]
    ) -> None:
        assert service.status().workflow_count == 0
        assert not target["state"].exists()
        assert not target["audit"].exists()

    def test_report_creates_no_reports_directory(
        self, service: WorkflowService, target: dict[str, Path]
    ) -> None:
        assert service.report("wf-1").reports == []
        assert not target["audit"].exists()

    def test_report_does_not_rewrite_an_existing_artifact(
        self, service: WorkflowService, populated: StateStore, target: dict[str, Path]
    ) -> None:
        artifact = target["audit"] / "wf-1" / "reports" / "stage.json"
        before = (artifact.read_bytes(), artifact.stat().st_mtime_ns)
        result = service.report("wf-1", report_kind="stage")
        assert result.reports[0].sha256
        assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == before

    def test_service_module_imports_no_write_capable_symbol(self) -> None:
        """A structural companion to the behavioural check, read from the parsed import graph.

        Docstrings mention `RepositoryLock` and `WorkflowSession` by name to explain why they are
        absent, so a substring scan over the source would be self-defeating; the AST sees only what
        is actually imported.
        """
        import agentos_workflow.service as service_module

        tree = ast.parse(inspect.getsource(service_module))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(f"{node.module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        assert not any("lock" in name.lower() for name in imported)
        assert not any(name.endswith(("WorkflowSession", "RepositoryLock")) for name in imported)

    def test_service_module_calls_no_write_method(self) -> None:
        """No append/record/generate call appears anywhere in the module's call graph."""
        import agentos_workflow.service as service_module

        tree = ast.parse(inspect.getsource(service_module))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        forbidden = {
            "record_transition",
            "record_command_execution",
            "append_audit_event",
            "generate_stage_report",
            "generate_qa_report",
            "generate_failure_report",
            "generate_closeout_report",
            "write_sanitized_output",
            "mkdir",
            "write_text",
            "write_bytes",
        }
        assert called & forbidden == set()


# ------------------------------------------------------------------------------------------
# status
# ------------------------------------------------------------------------------------------


class TestStatus:
    def test_repository_context_without_workflow(
        self, service: WorkflowService, populated: StateStore, target: dict[str, Path]
    ) -> None:
        result = service.status()
        assert result.workflow is None
        assert result.workflow_count == 1
        assert result.repository.repository_identity == "github.com/org/demo"
        assert result.repository.state_directory == str(target["state"])

    def test_reports_the_replayed_current_state(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        workflow = service.status("wf-1").workflow
        assert workflow is not None
        assert workflow.current_state == "IMPLEMENTING"
        assert workflow.transition_count == 4
        assert workflow.stage_id == "STAGE-1"
        assert workflow.terminal is False
        assert workflow.first_transition_at < workflow.last_transition_at

    def test_terminal_state_is_flagged(
        self, service: WorkflowService, config: WorkflowConfig, target: dict[str, Path]
    ) -> None:
        store = StateStore.for_config(config)
        store.record_transition(
            _transition(
                "wf-done",
                target["repository"],
                from_state="CLOSING",
                to_state="DONE",
                at=datetime(2026, 7, 31, 9, 0, tzinfo=UTC),
            )
        )
        workflow = service.status("wf-done").workflow
        assert workflow is not None
        assert workflow.terminal is True

    def test_missing_workflow_raises_the_typed_error(self, service: WorkflowService) -> None:
        with pytest.raises(WorkflowNotFoundError):
            service.status("never-ran")

    def test_unsafe_workflow_id_keeps_the_state_store_error(self, service: WorkflowService) -> None:
        """Path-component validation is the store's, and it still fires through this boundary."""
        with pytest.raises(StateStoreError):
            service.status("../escape")


# ------------------------------------------------------------------------------------------
# list
# ------------------------------------------------------------------------------------------


class TestList:
    def test_lists_only_workflows_with_persisted_history(
        self, service: WorkflowService, populated: StateStore, target: dict[str, Path]
    ) -> None:
        # A bare directory with no transitions.jsonl is not a workflow.
        (target["state"] / "not-a-workflow").mkdir()
        result = service.list()
        assert [workflow.workflow_id for workflow in result.workflows] == ["wf-1"]

    def test_ordering_is_deterministic(
        self, service: WorkflowService, config: WorkflowConfig, target: dict[str, Path]
    ) -> None:
        store = StateStore.for_config(config)
        for workflow_id in ("wf-c", "wf-a", "wf-b"):
            store.record_transition(
                _transition(
                    workflow_id,
                    target["repository"],
                    from_state="CREATED",
                    to_state="AUTHORIZED",
                    at=datetime(2026, 7, 31, 9, 0, tzinfo=UTC),
                    actor="human",
                )
            )
        assert [workflow.workflow_id for workflow in service.list().workflows] == [
            "wf-a",
            "wf-b",
            "wf-c",
        ]

    def test_empty_storage_is_an_empty_list_not_an_error(self, service: WorkflowService) -> None:
        assert service.list().workflows == []

    def test_symlinked_workflow_directory_is_refused(
        self,
        service: WorkflowService,
        populated: StateStore,
        target: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Confinement is not relaxed for a listing: a symlink where a workflow belongs fails."""
        outside = tmp_path / "outside"
        (outside / "wf-evil").mkdir(parents=True)
        (outside / "wf-evil" / "transitions.jsonl").write_text("", encoding="utf-8")
        os.symlink(outside / "wf-evil", target["state"] / "wf-evil")
        with pytest.raises(StateStorePathConfinementError):
            service.list()


# ------------------------------------------------------------------------------------------
# audit
# ------------------------------------------------------------------------------------------


class TestAudit:
    def test_preserves_order_and_evidence_references(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        result = service.audit("wf-1")
        assert [record.to_state for record in result.transitions] == [
            "AUTHORIZED",
            "PRECONDITIONS_CHECKED",
            "BRANCH_CREATED",
            "IMPLEMENTING",
        ]
        assert result.transitions[0].gate_evidence_ref == "evidence/authorization.json"
        assert result.transitions[1].gate_evidence_ref == "evidence/preconditions.json"
        assert result.transitions[2].gate_evidence_ref is None
        assert result.command_executions[0].stdout_ref == "wf-1/output/op-1/stdout.txt"
        assert result.command_executions[0].stderr_ref == "wf-1/output/op-1/stderr.txt"

    def test_ordering_is_deterministic_across_reads(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        first = [record.timestamp for record in service.audit("wf-1").transitions]
        second = [record.timestamp for record in service.audit("wf-1").transitions]
        assert first == second == sorted(first)

    def test_returns_the_stores_own_record_models(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        result = service.audit("wf-1")
        assert all(isinstance(r, StateTransitionRecord) for r in result.transitions)
        assert all(isinstance(r, CommandExecutionRecord) for r in result.command_executions)

    def test_missing_workflow_raises_the_typed_error(self, service: WorkflowService) -> None:
        with pytest.raises(WorkflowNotFoundError):
            service.audit("never-ran")

    def test_corrupt_history_surfaces_the_existing_corruption_error(
        self, service: WorkflowService, populated: StateStore, target: dict[str, Path]
    ) -> None:
        path = target["state"] / "wf-1" / "transitions.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "{not json}\n", encoding="utf-8")
        with pytest.raises(StateStoreCorruptionError):
            service.audit("wf-1")


# ------------------------------------------------------------------------------------------
# report
# ------------------------------------------------------------------------------------------


class TestReport:
    def test_returns_every_persisted_artifact_with_content(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        result = service.report("wf-1")
        assert [(r.report_kind, r.sequence) for r in result.reports] == [("qa", 2), ("stage", None)]
        assert result.reports[1].content["verdict"] == "PASS"
        assert result.reports[1].content["report_kind"] == "stage"

    def test_filters_by_report_kind(self, service: WorkflowService, populated: StateStore) -> None:
        result = service.report("wf-1", report_kind="qa")
        assert result.report_kind == "qa"
        assert [r.report_kind for r in result.reports] == ["qa"]

    def test_requested_kind_with_no_artifact_raises(
        self, service: WorkflowService, populated: StateStore
    ) -> None:
        with pytest.raises(ReportNotFoundError):
            service.report("wf-1", report_kind="closeout")

    def test_unrequested_empty_result_is_not_an_error(self, service: WorkflowService) -> None:
        assert service.report("wf-1").reports == []

    def test_unsafe_workflow_id_is_refused(self, service: WorkflowService) -> None:
        with pytest.raises(WorkflowServiceError):
            service.report("../escape")

    def test_malformed_report_is_surfaced_not_repaired(
        self, service: WorkflowService, populated: StateStore, target: dict[str, Path]
    ) -> None:
        artifact = target["audit"] / "wf-1" / "reports" / "stage.json"
        artifact.write_text("{ not json", encoding="utf-8")
        with pytest.raises(WorkflowServiceError):
            service.report("wf-1")
        assert artifact.read_text(encoding="utf-8") == "{ not json"

    def test_symlinked_report_is_refused(
        self,
        service: WorkflowService,
        populated: StateStore,
        target: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        secret = tmp_path / "secret.json"
        secret.write_text('{"stolen": true}', encoding="utf-8")
        os.symlink(secret, target["audit"] / "wf-1" / "reports" / "closeout.json")
        with pytest.raises(WorkflowServiceError):
            service.report("wf-1", report_kind="closeout")


# ------------------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------------------


class TestConfiguration:
    def test_discovers_the_default_configuration(self, target: dict[str, Path]) -> None:
        service = open_workflow_service(target["repository"])
        assert service.status().repository.repository_identity == "github.com/org/demo"

    def test_accepts_an_explicit_configuration_path(
        self, target: dict[str, Path], tmp_path: Path
    ) -> None:
        override = tmp_path / "elsewhere.yaml"
        override.write_text(
            yaml.safe_dump(_config_dict(target["repository"], target["state"], target["audit"])),
            encoding="utf-8",
        )
        service = open_workflow_service(target["repository"], override)
        assert service.status().repository.baseline_branch == "main"

    def test_missing_configuration_keeps_the_existing_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationNotFoundError):
            open_workflow_service(tmp_path / "no-such-repo")

    def test_invalid_configuration_keeps_the_existing_error(self, target: dict[str, Path]) -> None:
        (target["repository"] / ".agentos" / "workflow.yaml").write_text(
            "baseline_branch: main\n", encoding="utf-8"
        )
        with pytest.raises(InvalidConfigurationError):
            open_workflow_service(target["repository"])

    def test_wrong_repository_configuration_still_fails_closed(
        self, target: dict[str, Path], tmp_path: Path
    ) -> None:
        other = tmp_path / "other-repo"
        other.mkdir()
        override = tmp_path / "mismatched.yaml"
        override.write_text(
            yaml.safe_dump(_config_dict(target["repository"], target["state"], target["audit"])),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationRepositoryMismatchError):
            open_workflow_service(other, override)


class TestSkillFailurePassThrough:
    """A Skill returns a typed failure rather than raising, so the boundary must not lose it."""

    def test_report_failure_carries_the_original_typed_skill_failure(
        self, service: WorkflowService, populated: StateStore, target: dict[str, Path]
    ) -> None:
        artifact = target["audit"] / "wf-1" / "reports" / "stage.json"
        artifact.write_text("{ not json", encoding="utf-8")
        with pytest.raises(WorkflowServiceError) as raised:
            service.report("wf-1")
        failure = raised.value.skill_failure
        assert failure is not None
        assert failure.skill == "read_reports"
        assert failure.kind is FailureKind.MALFORMED_OUTPUT

    def test_unsafe_input_failure_is_classified_non_retryable(
        self, service: WorkflowService
    ) -> None:
        with pytest.raises(WorkflowServiceError) as raised:
            service.report("../escape")
        failure = raised.value.skill_failure
        assert failure is not None
        assert failure.kind is FailureKind.UNSAFE_INPUT
        assert failure.retry_classification is RetryClassification.NON_RETRYABLE
