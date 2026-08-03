"""Tests for the configurable approval subsystem (AUTO-012).

Six things are proved here, deliberately separately.

*Policy is strict and its precedence is real.* Built-in, project, gate, and run layers resolve in
that order, the result is an immutable snapshot, and `AUTO_APPROVE` cannot be acquired by
inheritance — the one policy value that can turn an absent human into a granted permission.

*Persistence is the store's, not a second framework.* Append-only, fsync'd, duplicate-key
rejecting, monotonically ordered, symlink refusing, per-workflow confined — every one of those
properties is exercised through `ApprovalService`, because reusing `StateStore`'s discipline is
only worth claiming if the approval path actually inherits it.

*Deadlines are facts on disk.* No thread, no timer, no sleep. Every assertion about a timeout is
made by moving an injected clock, and one test proves a deadline survives constructing an entirely
new service over the same directory — which is what "survives a restart" means.

*Checksums bind an approval to a state of the world.* Each of the four independently invalidates,
unchanged inputs preserve validity, and the comparison happens immediately before consumption.

*Nothing gained authority.* The service executes nothing, mutates no repository, and cannot make a
deterministic gate pass. Asserted over the parsed syntax tree, not in prose.

*Nothing existing changed.* AUTO-010's runtime, AUTO-011's contract, the CLI, and the state machine
are all still exactly what they were.
"""

from __future__ import annotations

import ast
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentos_workflow.approvals import (
    APPROVALS_FILENAME,
    CHECKSUM_ALGORITHM_PREFIX,
    ApprovalChannel,
    ApprovalChecksums,
    ApprovalDecision,
    ApprovalEvent,
    ApprovalEventKind,
    ApprovalNotFoundError,
    ApprovalPolicy,
    ApprovalPolicyError,
    ApprovalPolicyOverlay,
    ApprovalService,
    ApprovalStateError,
    ApprovalStatus,
    ChecksumKind,
    DecisionOrigin,
    PolicyLayer,
    TimeoutAction,
    checksum_of_agent_result,
    checksum_of_mapping,
    checksum_of_text,
    resolve_approval_policy,
)
from agentos_workflow.orchestrator.state_store import (
    StateStore,
    StateStoreCorruptionError,
    StateStoreOrderingError,
    StateStorePathConfinementError,
)
from agentos_workflow.providers.base import ProviderKind
from agentos_workflow.results import AgentRunResult, ExecutionMode, RunStatus

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
WORKFLOW = "wf-1"
GATE = "ready_to_commit"


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def store_at(tmp_path: Path) -> StateStore:
    return StateStore(state_directory=tmp_path / "state", audit_directory=tmp_path / "audit")


def service(tmp_path: Path) -> ApprovalService:
    return ApprovalService(store_at(tmp_path))


def checksums(**overrides: str) -> ApprovalChecksums:
    values: dict[str, str] = {
        "repo_state": checksum_of_text("HEAD=abc123"),
        "diff": checksum_of_text("--- a\n+++ b\n"),
        "agent_result": checksum_of_text("agent"),
        "gate_result": checksum_of_mapping({"tests": "pass", "lint": "pass"}),
    }
    return ApprovalChecksums(**{**values, **overrides})


def policy(**overlay: Any) -> ApprovalPolicy:
    """A gate-layer policy, because that is the layer a real gate configures."""
    return resolve_approval_policy(gate=ApprovalPolicyOverlay(**overlay))


def opened(
    tmp_path: Path,
    *,
    approval_id: str = "ap-1",
    workflow_id: str = WORKFLOW,
    now: datetime = T0,
    bound: ApprovalChecksums | None = None,
    **overlay: Any,
) -> tuple[ApprovalService, str]:
    svc = service(tmp_path)
    svc.request_approval(
        workflow_id=workflow_id,
        gate=GATE,
        approval_id=approval_id,
        checksums=bound or checksums(),
        policy=policy(**overlay),
        now=now,
    )
    return svc, approval_id


# ---------------------------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------------------------


class TestPolicyResolution:
    def test_built_in_defaults_are_the_conservative_floor(self) -> None:
        resolved = resolve_approval_policy()
        assert resolved.required is True
        assert resolved.timeout_seconds is None
        assert resolved.timeout_action is TimeoutAction.PAUSE
        assert resolved.channels == (ApprovalChannel.CLI,)
        assert resolved.approvers == ()
        assert resolved.timeout_action_source is PolicyLayer.BUILT_IN

    def test_each_layer_overrides_the_one_below(self) -> None:
        resolved = resolve_approval_policy(
            project=ApprovalPolicyOverlay(timeout_seconds=60, approvers=("project-owner",)),
            gate=ApprovalPolicyOverlay(timeout_seconds=120),
            run=ApprovalPolicyOverlay(timeout_seconds=5),
        )
        assert resolved.timeout_seconds == 5
        # The gate and run said nothing about approvers, so the project's value survives rather
        # than being reset by a layer that simply did not mention it.
        assert resolved.approvers == ("project-owner",)

    def test_precedence_is_run_over_gate_over_project_over_built_in(self) -> None:
        assert (
            resolve_approval_policy(
                project=ApprovalPolicyOverlay(timeout_action=TimeoutAction.FAIL),
                gate=ApprovalPolicyOverlay(timeout_action=TimeoutAction.CANCEL),
            ).timeout_action
            is TimeoutAction.CANCEL
        )
        assert (
            resolve_approval_policy(
                gate=ApprovalPolicyOverlay(timeout_action=TimeoutAction.CANCEL),
                run=ApprovalPolicyOverlay(timeout_action=TimeoutAction.FAIL),
            ).timeout_action
            is TimeoutAction.FAIL
        )

    def test_the_resolved_snapshot_is_immutable(self) -> None:
        resolved = resolve_approval_policy()
        with pytest.raises(ValidationError):
            resolved.timeout_action = TimeoutAction.AUTO_APPROVE  # type: ignore[misc]
        with pytest.raises(ValidationError):
            resolved.required = False  # type: ignore[misc]

    def test_unknown_fields_are_rejected_in_both_overlay_and_snapshot(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalPolicyOverlay(auto_approve=True)
        with pytest.raises(ValidationError):
            ApprovalPolicy.model_validate(
                {**resolve_approval_policy().model_dump(), "bypass": True}
            )

    def test_invalid_enum_values_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalPolicyOverlay(timeout_action="approve_everything")
        with pytest.raises(ValidationError):
            ApprovalPolicyOverlay(channels=("smoke_signal",))

    @pytest.mark.parametrize("seconds", [0, -1, -3600])
    def test_non_positive_durations_are_rejected(self, seconds: int) -> None:
        with pytest.raises(ValidationError):
            ApprovalPolicyOverlay(timeout_seconds=seconds)
        with pytest.raises(ValidationError):
            ApprovalPolicyOverlay(escalation_extension_seconds=seconds)

    def test_a_policy_must_permit_at_least_one_channel(self) -> None:
        with pytest.raises(ApprovalPolicyError, match="at least one channel"):
            resolve_approval_policy(gate=ApprovalPolicyOverlay(channels=()))

    def test_escalate_requires_someone_to_escalate_to(self) -> None:
        with pytest.raises(ApprovalPolicyError, match="escalate_to"):
            resolve_approval_policy(
                gate=ApprovalPolicyOverlay(timeout_action=TimeoutAction.ESCALATE)
            )

    def test_escalation_cannot_fall_back_to_escalation(self) -> None:
        """The bound on escalation: no configuration, however assembled, can express a loop."""
        with pytest.raises(ApprovalPolicyError, match="must not be ESCALATE"):
            resolve_approval_policy(
                gate=ApprovalPolicyOverlay(escalation_fallback_action=TimeoutAction.ESCALATE)
            )

    def test_channels_and_approvers_are_carried_into_the_snapshot(self) -> None:
        resolved = resolve_approval_policy(
            gate=ApprovalPolicyOverlay(
                channels=(ApprovalChannel.CLI, ApprovalChannel.TELEGRAM), approvers=("a", "b")
            )
        )
        assert resolved.channels == (ApprovalChannel.CLI, ApprovalChannel.TELEGRAM)
        assert resolved.approvers == ("a", "b")


class TestAutoApproveRequiresExplicitOptIn:
    """The subsystem's most security-sensitive rule, tested from every direction."""

    @pytest.mark.parametrize("layer", ["project"])
    def test_a_broad_layer_cannot_enable_auto_approve(self, layer: str) -> None:
        with pytest.raises(ApprovalPolicyError, match="explicit opt-in"):
            resolve_approval_policy(
                **{layer: ApprovalPolicyOverlay(timeout_action=TimeoutAction.AUTO_APPROVE)}
            )

    def test_the_built_in_default_is_not_auto_approve(self) -> None:
        assert resolve_approval_policy().timeout_action is not TimeoutAction.AUTO_APPROVE

    def test_a_gate_may_opt_in(self) -> None:
        resolved = resolve_approval_policy(
            gate=ApprovalPolicyOverlay(timeout_action=TimeoutAction.AUTO_APPROVE)
        )
        assert resolved.timeout_action is TimeoutAction.AUTO_APPROVE
        assert resolved.timeout_action_source is PolicyLayer.GATE

    def test_a_run_override_may_opt_in(self) -> None:
        resolved = resolve_approval_policy(
            run=ApprovalPolicyOverlay(timeout_action=TimeoutAction.AUTO_APPROVE)
        )
        assert resolved.timeout_action_source is PolicyLayer.RUN

    def test_inheriting_a_projects_auto_approve_is_still_refused_when_a_gate_sets_other_fields(
        self,
    ) -> None:
        """The gate participating in resolution does not launder the project's choice: the gate
        must select `AUTO_APPROVE` *itself*."""
        with pytest.raises(ApprovalPolicyError, match="explicit opt-in"):
            resolve_approval_policy(
                project=ApprovalPolicyOverlay(timeout_action=TimeoutAction.AUTO_APPROVE),
                gate=ApprovalPolicyOverlay(timeout_seconds=30),
            )

    def test_a_gate_may_override_a_projects_auto_approve_back_to_something_safe(self) -> None:
        resolved = resolve_approval_policy(
            project=ApprovalPolicyOverlay(timeout_action=TimeoutAction.AUTO_APPROVE),
            gate=ApprovalPolicyOverlay(timeout_action=TimeoutAction.PAUSE),
        )
        assert resolved.timeout_action is TimeoutAction.PAUSE

    def test_the_escalation_fallback_obeys_the_same_rule(self) -> None:
        with pytest.raises(ApprovalPolicyError, match="explicit opt-in"):
            resolve_approval_policy(
                project=ApprovalPolicyOverlay(escalation_fallback_action=TimeoutAction.AUTO_APPROVE)
            )
        assert (
            resolve_approval_policy(
                gate=ApprovalPolicyOverlay(escalation_fallback_action=TimeoutAction.AUTO_APPROVE)
            ).escalation_fallback_source
            is PolicyLayer.GATE
        )

    def test_the_snapshot_records_where_auto_approve_came_from(self, tmp_path: Path) -> None:
        svc, approval_id = opened(
            tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.AUTO_APPROVE
        )
        snapshot = svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id).policy_snapshot
        assert snapshot.timeout_action_source is PolicyLayer.GATE


# ---------------------------------------------------------------------------------------------
# The immutable snapshot
# ---------------------------------------------------------------------------------------------


class TestSnapshotIsNotRetroactive:
    def test_later_configuration_changes_do_not_alter_an_open_request(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=60, timeout_action=TimeoutAction.PAUSE)
        # The operator "edits configuration" — which, since the snapshot is a value rather than a
        # reference, cannot reach the request that already exists.
        resolve_approval_policy(
            gate=ApprovalPolicyOverlay(timeout_seconds=1, timeout_action=TimeoutAction.FAIL)
        )
        current = svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id)
        assert current.policy_snapshot.timeout_seconds == 60
        assert current.policy_snapshot.timeout_action is TimeoutAction.PAUSE
        assert current.deadline == at(60)

    def test_the_request_holds_no_reference_to_the_overlays(self, tmp_path: Path) -> None:
        overlay = ApprovalPolicyOverlay(timeout_seconds=60)
        svc = service(tmp_path)
        svc.request_approval(
            workflow_id=WORKFLOW,
            gate=GATE,
            approval_id="ap-1",
            checksums=checksums(),
            policy=resolve_approval_policy(gate=overlay),
            now=T0,
        )
        request = svc.get_approval(workflow_id=WORKFLOW, approval_id="ap-1")
        assert request.policy_snapshot.timeout_seconds == 60
        assert isinstance(request.policy_snapshot, ApprovalPolicy)

    def test_channels_and_approvers_cannot_drift_from_the_snapshot(self) -> None:
        from agentos_workflow.approvals import ApprovalRequest

        snapshot = resolve_approval_policy(gate=ApprovalPolicyOverlay(approvers=("a",)))
        with pytest.raises(ValidationError, match="approvers must equal"):
            ApprovalRequest(
                approval_id="x",
                workflow_id=WORKFLOW,
                gate=GATE,
                requested_at=T0,
                deadline=None,
                policy_snapshot=snapshot,
                channels=snapshot.channels,
                approvers=("someone-else",),
                checksums=checksums(),
                status=ApprovalStatus.PENDING,
            )


# ---------------------------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------------------------


class TestPersistence:
    def test_records_are_appended_never_rewritten(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        path = tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME
        after_request = path.read_bytes()

        svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        after_decision = path.read_bytes()
        assert after_decision.startswith(after_request)
        assert len(after_decision) > len(after_request)

    def test_a_decision_never_overwrites_the_request_line(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.REJECT,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        lines = (tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME).read_text().splitlines()
        assert json.loads(lines[0])["kind"] == ApprovalEventKind.REQUESTED.value
        assert json.loads(lines[1])["kind"] == ApprovalEventKind.DECIDED.value

    def test_history_replays_after_a_simulated_restart(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10)
        svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        # An entirely new service over the same directory — nothing carried in memory.
        restarted = service(tmp_path).get_approval(workflow_id=WORKFLOW, approval_id=approval_id)
        assert restarted.status is ApprovalStatus.APPROVED
        assert restarted.approver == "afshin"
        assert restarted.decided_at == at(5)
        assert restarted.deadline == at(10)

    def test_duplicate_json_keys_are_rejected(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        path = tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME
        line = path.read_text().splitlines()[0]
        path.write_text(line.replace('"gate":', '"gate":"other","gate":', 1) + "\n")
        with pytest.raises(StateStoreCorruptionError, match="duplicate JSON object key"):
            svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id)

    def test_out_of_order_records_are_refused_on_write(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, now=at(100))
        with pytest.raises(StateStoreOrderingError, match="precedes"):
            svc.decide_approval(
                workflow_id=WORKFLOW,
                approval_id=approval_id,
                decision=ApprovalDecision.APPROVE,
                approver="afshin",
                source=ApprovalChannel.CLI,
                now=at(1),
            )

    def test_out_of_order_records_are_refused_on_read(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        path = tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME
        earlier = ApprovalEvent(
            approval_id=approval_id,
            workflow_id=WORKFLOW,
            gate=GATE,
            kind=ApprovalEventKind.CONSUMED,
            timestamp=at(-500).isoformat(),
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(earlier.model_dump_json() + "\n")
        with pytest.raises(StateStoreCorruptionError, match="non-decreasing"):
            svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id)

    def test_a_symlinked_history_is_refused(self, tmp_path: Path) -> None:
        opened(tmp_path)
        path = tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME
        elsewhere = tmp_path / "elsewhere.jsonl"
        elsewhere.write_text(path.read_text())
        path.unlink()
        path.symlink_to(elsewhere)
        with pytest.raises(StateStorePathConfinementError):
            service(tmp_path).get_approval(workflow_id=WORKFLOW, approval_id="ap-1")

    def test_storage_is_confined_per_workflow(self, tmp_path: Path) -> None:
        svc = service(tmp_path)
        for workflow in ("wf-a", "wf-b"):
            svc.request_approval(
                workflow_id=workflow,
                gate=GATE,
                approval_id="ap-1",
                checksums=checksums(),
                policy=policy(),
                now=T0,
            )
        assert (tmp_path / "state" / "wf-a" / APPROVALS_FILENAME).exists()
        assert (tmp_path / "state" / "wf-b" / APPROVALS_FILENAME).exists()
        assert svc.get_approval(workflow_id="wf-a", approval_id="ap-1").workflow_id == "wf-a"

    def test_the_approval_history_lives_beside_the_transition_history(self, tmp_path: Path) -> None:
        opened(tmp_path)
        assert (tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME).is_file()

    def test_the_append_path_fsyncs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Durability is the point of an approval record; a decision that survives only in the page
        cache has not been made. Asserted by observing the real syscall the shared append path
        issues, not by trusting that it does."""
        synced: list[int] = []
        real_fsync = os.fsync

        def recording_fsync(fd: int) -> None:
            synced.append(fd)
            real_fsync(fd)

        monkeypatch.setattr(os, "fsync", recording_fsync)
        opened(tmp_path)
        # One for the record file, one for the directory holding it.
        assert len(synced) >= 2

    def test_an_approval_identifier_is_never_reused(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        with pytest.raises(ApprovalStateError, match="already exists"):
            svc.request_approval(
                workflow_id=WORKFLOW,
                gate=GATE,
                approval_id=approval_id,
                checksums=checksums(),
                policy=policy(),
                now=at(5),
            )

    def test_ordering_is_deterministic_across_reads(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        first = svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id)
        assert first == svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id)

    def test_multiple_approvals_share_one_ordered_history(self, tmp_path: Path) -> None:
        svc = service(tmp_path)
        for index, moment in enumerate((T0, at(10)), start=1):
            svc.request_approval(
                workflow_id=WORKFLOW,
                gate=f"gate-{index}",
                approval_id=f"ap-{index}",
                checksums=checksums(),
                policy=policy(),
                now=moment,
            )
        assert [request.gate for request in svc.list_approvals(workflow_id=WORKFLOW)] == [
            "gate-1",
            "gate-2",
        ]

    def test_a_missing_approval_is_reported_not_invented(self, tmp_path: Path) -> None:
        with pytest.raises(ApprovalNotFoundError):
            service(tmp_path).get_approval(workflow_id=WORKFLOW, approval_id="never-created")


# ---------------------------------------------------------------------------------------------
# Deadlines and timeout actions
# ---------------------------------------------------------------------------------------------


class TestDeadlines:
    def test_the_deadline_is_absolute_and_timezone_aware(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=90)
        deadline = svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id).deadline
        assert deadline == at(90)
        assert deadline is not None and deadline.tzinfo is not None

    def test_no_timeout_means_no_deadline_and_no_expiry(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=None)
        assert svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id).deadline is None
        far_future = svc.evaluate_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, now=at(10_000_000)
        )
        assert far_future.status is ApprovalStatus.PENDING

    def test_the_deadline_survives_a_restart(self, tmp_path: Path) -> None:
        opened(tmp_path, timeout_seconds=30, timeout_action=TimeoutAction.FAIL)
        # A brand-new service, as a fresh process would build: the deadline is read off disk and
        # fires, which is exactly what an in-memory timer could not do.
        restarted = service(tmp_path).evaluate_approval(
            workflow_id=WORKFLOW, approval_id="ap-1", now=at(31)
        )
        assert restarted.status is ApprovalStatus.FAILED

    def test_evaluation_is_lazy_reading_alone_does_not_apply_a_timeout(
        self, tmp_path: Path
    ) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.FAIL)
        # `get_approval` is a pure read: an expired-but-unevaluated approval reads as pending.
        assert (
            svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id).status
            is ApprovalStatus.PENDING
        )
        assert (
            svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11)).status
            is ApprovalStatus.FAILED
        )

    def test_a_deadline_not_yet_reached_leaves_the_approval_pending(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.FAIL)
        assert (
            svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(9)).status
            is ApprovalStatus.PENDING
        )

    def test_evaluation_is_idempotent(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.CANCEL)
        first = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        second = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(99))
        assert first == second

    def test_the_module_depends_on_no_timer_thread_or_sleep(self) -> None:
        """A deadline that needed a running process to fire would not survive a restart, so the
        absence of these is the mechanism, not an implementation detail."""
        tree = ast.parse(Path("agentos_workflow/approvals.py").read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        forbidden = {
            "sleep",
            "Thread",
            "Timer",
            "threading",
            "asyncio",
            "sched",
            "signal",
            "alarm",
            "monotonic",
            "perf_counter",
        }
        assert (names | imported) & forbidden == set()


class TestTimeoutActions:
    def test_auto_approve_approves_and_records_its_origin(self, tmp_path: Path) -> None:
        svc, approval_id = opened(
            tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.AUTO_APPROVE
        )
        result = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert result.status is ApprovalStatus.APPROVED
        assert result.manual_or_auto is DecisionOrigin.AUTO
        assert result.timeout_action_applied is TimeoutAction.AUTO_APPROVE
        assert result.decision is ApprovalDecision.APPROVE
        assert result.approver is None

    def test_pause_requires_human_intervention_and_stays_resumable(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.PAUSE)
        paused = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert paused.status is ApprovalStatus.HUMAN_INTERVENTION_REQUIRED
        assert paused.timeout_action_applied is TimeoutAction.PAUSE
        assert not paused.terminal

        resumed = svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(20),
        )
        assert resumed.status is ApprovalStatus.APPROVED
        assert resumed.manual_or_auto is DecisionOrigin.MANUAL

    def test_fail_is_terminal(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.FAIL)
        result = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert result.status is ApprovalStatus.FAILED
        assert result.terminal
        with pytest.raises(ApprovalStateError, match="settled"):
            svc.decide_approval(
                workflow_id=WORKFLOW,
                approval_id=approval_id,
                decision=ApprovalDecision.APPROVE,
                approver="afshin",
                source=ApprovalChannel.CLI,
                now=at(20),
            )

    def test_cancel_is_terminal(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, timeout_seconds=10, timeout_action=TimeoutAction.CANCEL)
        result = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert result.status is ApprovalStatus.CANCELLED
        assert result.terminal

    def test_escalate_records_escalation_then_grants_one_extension(self, tmp_path: Path) -> None:
        svc, approval_id = opened(
            tmp_path,
            timeout_seconds=10,
            timeout_action=TimeoutAction.ESCALATE,
            escalate_to=("lead",),
            escalation_extension_seconds=20,
            escalation_fallback_action=TimeoutAction.FAIL,
        )
        escalated = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert escalated.status is ApprovalStatus.ESCALATED
        assert escalated.escalated_at == at(11)
        assert escalated.extension_granted
        assert escalated.deadline == at(31)
        assert not escalated.terminal

    def test_escalation_falls_back_once_the_extension_expires(self, tmp_path: Path) -> None:
        svc, approval_id = opened(
            tmp_path,
            timeout_seconds=10,
            timeout_action=TimeoutAction.ESCALATE,
            escalate_to=("lead",),
            escalation_extension_seconds=20,
            escalation_fallback_action=TimeoutAction.FAIL,
        )
        svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        after = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(40))
        assert after.status is ApprovalStatus.FAILED
        assert after.timeout_action_applied is TimeoutAction.FAIL

    def test_escalation_is_bounded_never_extending_twice(self, tmp_path: Path) -> None:
        """The one property that keeps escalation from becoming an unbounded loop."""
        svc, approval_id = opened(
            tmp_path,
            timeout_seconds=10,
            timeout_action=TimeoutAction.ESCALATE,
            escalate_to=("lead",),
            escalation_extension_seconds=20,
            escalation_fallback_action=TimeoutAction.CANCEL,
        )
        for moment in (11, 40, 100, 1_000, 10_000):
            result = svc.evaluate_approval(
                workflow_id=WORKFLOW, approval_id=approval_id, now=at(moment)
            )
        assert result.status is ApprovalStatus.CANCELLED
        events = [
            json.loads(line)
            for line in (tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME)
            .read_text()
            .splitlines()
        ]
        assert sum(1 for e in events if e["kind"] == ApprovalEventKind.EXTENDED.value) == 1
        assert sum(1 for e in events if e["kind"] == ApprovalEventKind.ESCALATED.value) == 1

    def test_escalation_without_an_extension_falls_back_immediately(self, tmp_path: Path) -> None:
        svc, approval_id = opened(
            tmp_path,
            timeout_seconds=10,
            timeout_action=TimeoutAction.ESCALATE,
            escalate_to=("lead",),
            escalation_extension_seconds=None,
            escalation_fallback_action=TimeoutAction.FAIL,
        )
        escalated = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert escalated.status is ApprovalStatus.ESCALATED
        assert not escalated.extension_granted
        # The deadline is unchanged, so the fallback applies at the very next evaluation.
        assert (
            svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(12)).status
            is ApprovalStatus.FAILED
        )

    def test_an_escalated_approval_can_still_be_decided_by_a_human(self, tmp_path: Path) -> None:
        svc, approval_id = opened(
            tmp_path,
            timeout_seconds=10,
            timeout_action=TimeoutAction.ESCALATE,
            escalate_to=("lead",),
            escalation_extension_seconds=60,
            escalation_fallback_action=TimeoutAction.FAIL,
        )
        svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        decided = svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="lead",
            source=ApprovalChannel.CLI,
            now=at(20),
        )
        assert decided.status is ApprovalStatus.APPROVED


# ---------------------------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------------------------


class TestDecisions:
    @pytest.mark.parametrize(
        ("decision", "expected"),
        [
            (ApprovalDecision.APPROVE, ApprovalStatus.APPROVED),
            (ApprovalDecision.REJECT, ApprovalStatus.REJECTED),
            (ApprovalDecision.REQUEST_CHANGES, ApprovalStatus.CHANGES_REQUESTED),
        ],
    )
    def test_every_decision_maps_to_its_status(
        self, tmp_path: Path, decision: ApprovalDecision, expected: ApprovalStatus
    ) -> None:
        svc, approval_id = opened(tmp_path)
        result = svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=decision,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        assert result.status is expected

    def test_a_decision_records_source_approver_timestamp_and_origin(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, channels=(ApprovalChannel.TELEGRAM,))
        result = svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.TELEGRAM,
            now=at(5),
        )
        assert result.source is ApprovalChannel.TELEGRAM
        assert result.approver == "afshin"
        assert result.decided_at == at(5)
        assert result.manual_or_auto is DecisionOrigin.MANUAL

    def test_a_decision_records_the_exact_checksum_binding(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = opened(tmp_path, bound=bound)
        result = svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        assert result.checksums == bound

    def test_a_channel_outside_the_policy_is_refused(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, channels=(ApprovalChannel.CLI,))
        with pytest.raises(ApprovalStateError, match="not permitted"):
            svc.decide_approval(
                workflow_id=WORKFLOW,
                approval_id=approval_id,
                decision=ApprovalDecision.APPROVE,
                approver="afshin",
                source=ApprovalChannel.TELEGRAM,
                now=at(5),
            )

    def test_an_approver_outside_the_allowlist_is_refused(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, approvers=("afshin",))
        with pytest.raises(ApprovalStateError, match="allowlist"):
            svc.decide_approval(
                workflow_id=WORKFLOW,
                approval_id=approval_id,
                decision=ApprovalDecision.APPROVE,
                approver="someone-else",
                source=ApprovalChannel.CLI,
                now=at(5),
            )

    def test_an_empty_approver_allowlist_permits_any_named_approver(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path, approvers=())
        assert (
            svc.decide_approval(
                workflow_id=WORKFLOW,
                approval_id=approval_id,
                decision=ApprovalDecision.APPROVE,
                approver="anyone",
                source=ApprovalChannel.CLI,
                now=at(5),
            ).status
            is ApprovalStatus.APPROVED
        )

    def test_a_settled_approval_cannot_be_decided_again(self, tmp_path: Path) -> None:
        svc, approval_id = opened(tmp_path)
        svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.REJECT,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        with pytest.raises(ApprovalStateError, match="settled"):
            svc.decide_approval(
                workflow_id=WORKFLOW,
                approval_id=approval_id,
                decision=ApprovalDecision.APPROVE,
                approver="afshin",
                source=ApprovalChannel.CLI,
                now=at(6),
            )

    def test_requesting_an_approval_a_policy_says_is_unnecessary_is_refused(
        self, tmp_path: Path
    ) -> None:
        """`required=False` means the gate has no approval; creating one anyway would manufacture a
        gate the configuration says should not exist — and, worse, one nothing will ever decide."""
        with pytest.raises(ApprovalPolicyError, match="does not require approval"):
            service(tmp_path).request_approval(
                workflow_id=WORKFLOW,
                gate=GATE,
                approval_id="ap-1",
                checksums=checksums(),
                policy=policy(required=False),
                now=T0,
            )


# ---------------------------------------------------------------------------------------------
# Checksum binding and invalidation
# ---------------------------------------------------------------------------------------------


def approved(tmp_path: Path, bound: ApprovalChecksums) -> tuple[ApprovalService, str]:
    svc, approval_id = opened(tmp_path, bound=bound)
    svc.decide_approval(
        workflow_id=WORKFLOW,
        approval_id=approval_id,
        decision=ApprovalDecision.APPROVE,
        approver="afshin",
        source=ApprovalChannel.CLI,
        now=at(5),
    )
    return svc, approval_id


class TestChecksums:
    def test_checksums_are_deterministic(self) -> None:
        assert checksum_of_text("same") == checksum_of_text("same")
        assert checksum_of_text("same") != checksum_of_text("different")

    def test_mapping_checksums_ignore_key_order(self) -> None:
        assert checksum_of_mapping({"a": 1, "b": 2}) == checksum_of_mapping({"b": 2, "a": 1})

    def test_mapping_checksums_notice_a_value_change(self) -> None:
        assert checksum_of_mapping({"a": 1}) != checksum_of_mapping({"a": 2})

    def test_the_canonical_agent_result_is_what_is_hashed(self) -> None:
        """AUTO-011's contract supplies the bytes. No second serialization of the same object
        exists, so the checksum cannot drift from the contract it binds."""
        result = AgentRunResult(
            workflow_id=WORKFLOW,
            session_id="wf-1/claude_cli/inv-1",
            mode=ExecutionMode.PROVIDER_INVOCATION,
            provider=ProviderKind.CLAUDE_CLI,
            agent=None,
            status=RunStatus.COMPLETED,
            summary="did the thing",
            started_at=T0,
            completed_at=at(1),
        )
        assert checksum_of_agent_result(result) == checksum_of_text(result.to_canonical_json())

    def test_a_changed_agent_result_changes_its_checksum(self) -> None:
        common: dict[str, Any] = {
            "workflow_id": WORKFLOW,
            "session_id": "s",
            "mode": ExecutionMode.PROVIDER_INVOCATION,
            "provider": ProviderKind.CLAUDE_CLI,
            "agent": None,
            "status": RunStatus.COMPLETED,
            "started_at": T0,
            "completed_at": at(1),
        }
        first = AgentRunResult(**common, summary="one")
        second = AgentRunResult(**common, summary="two")
        assert checksum_of_agent_result(first) != checksum_of_agent_result(second)

    def test_every_checksum_is_algorithm_labelled(self) -> None:
        bound = checksums()
        for value in (bound.repo_state, bound.diff, bound.agent_result, bound.gate_result):
            assert value.startswith(CHECKSUM_ALGORITHM_PREFIX)
            assert len(value) == len(CHECKSUM_ALGORITHM_PREFIX) + 64

    @pytest.mark.parametrize("bad", ["abc", "sha256:xyz", "deadbeef" * 8, "sha256:" + "A" * 64])
    def test_a_malformed_checksum_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            checksums(diff=bad)

    def test_differences_reports_every_changed_binding_in_a_fixed_order(self) -> None:
        original = checksums()
        changed = ApprovalChecksums(
            repo_state=checksum_of_text("moved"),
            diff=original.diff,
            agent_result=checksum_of_text("re-ran"),
            gate_result=original.gate_result,
        )
        assert original.differences(changed) == (ChecksumKind.REPO_STATE, ChecksumKind.AGENT_RESULT)

    def test_no_secret_material_is_persisted_only_its_digest(self, tmp_path: Path) -> None:
        secret = "ghp_aaaaaaaaaaaaaaaaaaaaaaaa"
        bound = checksums(diff=checksum_of_text(f"--- a\n+++ b\n+token = {secret}\n"))
        opened(tmp_path, bound=bound)
        persisted = (tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME).read_text()
        assert secret not in persisted
        assert bound.diff in persisted


class TestInvalidation:
    def test_an_unchanged_binding_consumes_cleanly(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = approved(tmp_path, bound)
        result = svc.consume_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, checksums=bound, now=at(10)
        )
        assert result.status is ApprovalStatus.CONSUMED
        assert result.invalidated_checksums == ()

    @pytest.mark.parametrize(
        ("field", "kind"),
        [
            ("repo_state", ChecksumKind.REPO_STATE),
            ("diff", ChecksumKind.DIFF),
            ("agent_result", ChecksumKind.AGENT_RESULT),
            ("gate_result", ChecksumKind.GATE_RESULT),
        ],
    )
    def test_each_checksum_independently_invalidates(
        self, tmp_path: Path, field: str, kind: ChecksumKind
    ) -> None:
        bound = checksums()
        svc, approval_id = approved(tmp_path, bound)
        observed = bound.model_copy(update={field: checksum_of_text("something else")})
        result = svc.consume_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, checksums=observed, now=at(10)
        )
        assert result.status is ApprovalStatus.INVALIDATED
        assert result.invalidated_checksums == (kind,)

    def test_an_invalidated_approval_cannot_be_consumed(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = approved(tmp_path, bound)
        moved = bound.model_copy(update={"diff": checksum_of_text("moved")})
        svc.consume_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, checksums=moved, now=at(10)
        )
        with pytest.raises(ApprovalStateError, match="invalidated"):
            svc.consume_approval(
                workflow_id=WORKFLOW, approval_id=approval_id, checksums=bound, now=at(11)
            )

    def test_an_invalidated_approval_is_not_silently_recreated(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = approved(tmp_path, bound)
        svc.consume_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            checksums=bound.model_copy(update={"diff": checksum_of_text("moved")}),
            now=at(10),
        )
        assert len(svc.list_approvals(workflow_id=WORKFLOW)) == 1
        assert (
            svc.get_approval(workflow_id=WORKFLOW, approval_id=approval_id).status
            is ApprovalStatus.INVALIDATED
        )

    def test_an_invalidated_approval_is_never_auto_approved(self, tmp_path: Path) -> None:
        """A timeout cannot rescue an approval whose binding is gone: `AUTO_APPROVE` only ever
        applies while the approval is still pending."""
        bound = checksums()
        svc, approval_id = opened(
            tmp_path,
            bound=bound,
            timeout_seconds=10,
            timeout_action=TimeoutAction.AUTO_APPROVE,
        )
        svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        svc.consume_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            checksums=bound.model_copy(update={"repo_state": checksum_of_text("moved")}),
            now=at(12),
        )
        assert (
            svc.evaluate_approval(
                workflow_id=WORKFLOW, approval_id=approval_id, now=at(10_000)
            ).status
            is ApprovalStatus.INVALIDATED
        )

    def test_a_consumed_approval_cannot_be_spent_twice(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = approved(tmp_path, bound)
        svc.consume_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, checksums=bound, now=at(10)
        )
        with pytest.raises(ApprovalStateError, match="consumed"):
            svc.consume_approval(
                workflow_id=WORKFLOW, approval_id=approval_id, checksums=bound, now=at(11)
            )

    def test_an_undecided_approval_cannot_be_consumed(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = opened(tmp_path, bound=bound)
        with pytest.raises(ApprovalStateError, match="not approved"):
            svc.consume_approval(
                workflow_id=WORKFLOW, approval_id=approval_id, checksums=bound, now=at(10)
            )

    def test_a_rejected_approval_cannot_be_consumed(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = opened(tmp_path, bound=bound)
        svc.decide_approval(
            workflow_id=WORKFLOW,
            approval_id=approval_id,
            decision=ApprovalDecision.REJECT,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        with pytest.raises(ApprovalStateError, match="rejected"):
            svc.consume_approval(
                workflow_id=WORKFLOW, approval_id=approval_id, checksums=bound, now=at(10)
            )

    def test_the_invalidation_event_records_what_was_observed(self, tmp_path: Path) -> None:
        bound = checksums()
        svc, approval_id = approved(tmp_path, bound)
        observed = bound.model_copy(update={"gate_result": checksum_of_text("gates now fail")})
        svc.consume_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, checksums=observed, now=at(10)
        )
        events = [
            json.loads(line)
            for line in (tmp_path / "state" / WORKFLOW / APPROVALS_FILENAME)
            .read_text()
            .splitlines()
        ]
        invalidated = next(e for e in events if e["kind"] == ApprovalEventKind.INVALIDATED.value)
        assert invalidated["invalidated_checksums"] == [ChecksumKind.GATE_RESULT.value]
        assert invalidated["observed_checksums"]["gate_result"] == observed.gate_result


# ---------------------------------------------------------------------------------------------
# Authority boundaries
# ---------------------------------------------------------------------------------------------


def _approvals_tree() -> ast.Module:
    return ast.parse(Path("agentos_workflow/approvals.py").read_text(encoding="utf-8"))


class TestAuthorityBoundaries:
    def test_the_service_executes_no_agent_and_no_provider(self) -> None:
        tree = _approvals_tree()
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        forbidden = {
            "ProviderRuntime",
            "CLIProvider",
            "ClaudeCLIProvider",
            "CodexCLIProvider",
            "select_live_provider",
            "ImplementationAgent",
            "QAAgent",
            "PMOAgent",
            "GitAgent",
            "MergeAgent",
            "CloseoutAgent",
            "run_provider_process",
        }
        assert imported & forbidden == set()

    def test_the_service_mutates_no_git_or_github_state(self) -> None:
        tree = _approvals_tree()
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        forbidden = {
            "git_commit",
            "git_push",
            "open_pull_request",
            "enable_auto_merge",
            "delete_branch",
            "create_branch",
            "Popen",
            "check_output",
            "system",
            "urlopen",
            "request",
        }
        assert names & forbidden == set()

    def test_the_service_holds_no_lock_and_no_workflow_session(self) -> None:
        tree = _approvals_tree()
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert imported & {"RepositoryLock", "WorkflowSession", "WorkflowStateMachine"} == set()

    def test_the_service_exposes_no_gate_bypass(self) -> None:
        """An approval is evidence, never an authority: there is no operation here that marks a
        deterministic gate passed, and none that could stand in for one."""
        public = {name for name in dir(ApprovalService) if not name.startswith("_")}
        assert public == {
            "consume_approval",
            "decide_approval",
            "evaluate_approval",
            "for_config",
            "get_approval",
            "list_approvals",
            "request_approval",
        }

    def test_an_approval_cannot_authorize_a_different_repository_state(
        self, tmp_path: Path
    ) -> None:
        """Even an auto-approval binds the state captured at request time. This is the property
        that stops a timeout policy from becoming permission for whatever happened next."""
        bound = checksums()
        svc, approval_id = opened(
            tmp_path, bound=bound, timeout_seconds=10, timeout_action=TimeoutAction.AUTO_APPROVE
        )
        auto = svc.evaluate_approval(workflow_id=WORKFLOW, approval_id=approval_id, now=at(11))
        assert auto.status is ApprovalStatus.APPROVED
        moved = bound.model_copy(update={"repo_state": checksum_of_text("a different HEAD")})
        result = svc.consume_approval(
            workflow_id=WORKFLOW, approval_id=approval_id, checksums=moved, now=at(12)
        )
        assert result.status is ApprovalStatus.INVALIDATED

    def test_an_approval_cannot_be_replayed_for_another_workflow(self, tmp_path: Path) -> None:
        bound = checksums()
        approved(tmp_path, bound)
        with pytest.raises(ApprovalNotFoundError):
            service(tmp_path).consume_approval(
                workflow_id="a-different-workflow",
                approval_id="ap-1",
                checksums=bound,
                now=at(10),
            )

    def test_an_approval_cannot_be_replayed_for_another_gate(self, tmp_path: Path) -> None:
        """Each gate gets its own approval identifier and its own record; there is no operation
        that moves an approval from the gate it was granted for to another."""
        svc = service(tmp_path)
        svc.request_approval(
            workflow_id=WORKFLOW,
            gate="gate-a",
            approval_id="ap-a",
            checksums=checksums(),
            policy=policy(),
            now=T0,
        )
        assert svc.get_approval(workflow_id=WORKFLOW, approval_id="ap-a").gate == "gate-a"
        with pytest.raises(ApprovalNotFoundError):
            svc.get_approval(workflow_id=WORKFLOW, approval_id="ap-b")

    def test_no_telegram_transport_exists_anywhere(self) -> None:
        """`TELEGRAM` is a policy value in this stage and nothing more."""
        tree = _approvals_tree()
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert names & {"requests", "httpx", "urlopen", "socket", "bot", "send_message"} == set()
        offenders = [
            path
            for path in Path("agentos_workflow").rglob("*.py")
            if "tests" not in path.parts
            and "telegram" in path.read_text(encoding="utf-8").lower()
            and path.name != "approvals.py"
        ]
        assert offenders == []


# ---------------------------------------------------------------------------------------------
# Event-record strictness
# ---------------------------------------------------------------------------------------------


class TestEventRecords:
    def test_events_reject_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalEvent(
                approval_id="a",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.CONSUMED,
                timestamp=T0.isoformat(),
                bypass=True,
            )

    def test_events_are_frozen(self) -> None:
        event = ApprovalEvent(
            approval_id="a",
            workflow_id=WORKFLOW,
            gate=GATE,
            kind=ApprovalEventKind.CONSUMED,
            timestamp=T0.isoformat(),
        )
        with pytest.raises(ValidationError):
            event.kind = ApprovalEventKind.REQUESTED  # type: ignore[misc]

    def test_naive_timestamps_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            ApprovalEvent(
                approval_id="a",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.CONSUMED,
                timestamp="2026-08-01T12:00:00",
            )

    def test_a_requested_event_must_carry_its_policy_and_checksums(self) -> None:
        with pytest.raises(ValidationError, match="policy snapshot"):
            ApprovalEvent(
                approval_id="a",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.REQUESTED,
                timestamp=T0.isoformat(),
            )

    def test_a_manual_decision_must_name_its_approver(self) -> None:
        with pytest.raises(ValidationError, match="approver"):
            ApprovalEvent(
                approval_id="a",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.DECIDED,
                timestamp=T0.isoformat(),
                decision=ApprovalDecision.APPROVE,
                origin=DecisionOrigin.MANUAL,
            )

    def test_an_automatic_decision_must_record_the_timeout_action(self) -> None:
        with pytest.raises(ValidationError, match="timeout action"):
            ApprovalEvent(
                approval_id="a",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.DECIDED,
                timestamp=T0.isoformat(),
                decision=ApprovalDecision.APPROVE,
                origin=DecisionOrigin.AUTO,
            )

    def test_an_invalidated_event_must_say_what_changed(self) -> None:
        with pytest.raises(ValidationError, match="which checksums changed"):
            ApprovalEvent(
                approval_id="a",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.INVALIDATED,
                timestamp=T0.isoformat(),
            )

    def test_a_history_not_beginning_with_a_request_is_not_replayable(self, tmp_path: Path) -> None:
        store = store_at(tmp_path)
        store.record_approval(
            WORKFLOW,
            ApprovalEvent(
                approval_id="orphan",
                workflow_id=WORKFLOW,
                gate=GATE,
                kind=ApprovalEventKind.CONSUMED,
                timestamp=T0.isoformat(),
            ),
            timestamp=T0.isoformat(),
        )
        with pytest.raises(ApprovalStateError, match="does not begin with a REQUESTED"):
            ApprovalService(store).get_approval(workflow_id=WORKFLOW, approval_id="orphan")


# ---------------------------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------------------------


class TestCompatibility:
    def test_the_provider_runtime_is_untouched(self) -> None:
        from agentos_workflow.providers import runtime

        assert sorted(runtime.__all__) == sorted(
            [
                "AUTO_MODE_PROMPT_CONTRACT",
                "STDERR_ARTIFACT_FILENAME",
                "STDOUT_ARTIFACT_FILENAME",
                "ProviderRunRequest",
                "ProviderRunResult",
                "ProviderRuntime",
                "ProviderRuntimeTarget",
                "build_provider_prompt",
            ]
        )

    def test_the_canonical_result_contract_is_untouched(self) -> None:
        assert len(AgentRunResult.model_fields) == 19
        assert "recommended_next_state" in AgentRunResult.model_fields

    def test_the_approval_subsystem_introduces_no_second_result_contract(self) -> None:
        """`agent_result_checksum` binds AUTO-011's canonical result, not a copy of it."""
        tree = _approvals_tree()
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "AgentRunResult" in imported
        classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        assert not any(name.endswith("RunResult") for name in classes)

    def test_the_state_machine_is_unchanged(self) -> None:
        from agentos_workflow.orchestrator import engine

        assert len(engine.ALLOWED_TRANSITIONS) == 37
        assert len(list(engine.WorkflowState)) == 19

    def test_no_approval_state_was_added_to_the_workflow_state_machine(self) -> None:
        from agentos_workflow.orchestrator.engine import WorkflowState

        assert not any("APPROVAL" in state.name for state in WorkflowState)
        assert not any("INTERVENTION" in state.name for state in WorkflowState)

    def test_the_workflow_service_kept_every_earlier_operation(self) -> None:
        from agentos_workflow.service import WorkflowService

        public = {name for name in vars(WorkflowService) if not name.startswith("_")}
        assert {"status", "list", "audit", "report", "invoke_provider"} <= public

    def test_the_workflow_service_added_exactly_the_approval_boundary(self) -> None:
        """AUTO-012 added exactly the five approval operations. AUTO-014 later added exactly one
        more, `continue_implementation_to_done` — a separate continuation operation, not part of
        the approval boundary this test is about — so it is excluded here the same way
        `invoke_provider` (AUTO-010) is, and pinned separately by `test_service.py`'s own
        `APPROVED_OPERATIONS`."""
        from agentos_workflow.service import WorkflowService

        public = {name for name in vars(WorkflowService) if not name.startswith("_")}
        excluded = {
            "status",
            "list",
            "audit",
            "report",
            "invoke_provider",
            "continue_implementation_to_done",
        }
        assert public - excluded == {
            "request_approval",
            "get_approval",
            "evaluate_approval",
            "decide_approval",
            "consume_approval",
        }

    def test_no_public_cli_command_was_added(self) -> None:
        source = Path("agentos_workflow/cli_auto.py").read_text(encoding="utf-8")
        assert "approval" not in source.lower()

    def test_the_state_store_gained_only_the_approval_history(self) -> None:
        public = {name for name in vars(StateStore) if not name.startswith("_")}
        assert public == {
            "for_config",
            "state_directory",
            "audit_directory",
            "record_transition",
            "record_command_execution",
            "record_approval",
            "read_approvals",
            "list_workflow_ids",
            "read_transitions",
            "read_command_executions",
            "current_state",
        }

    def test_the_approval_history_does_not_disturb_workflow_listing(self, tmp_path: Path) -> None:
        """A workflow is defined by its transition history; an approvals file alone must not make
        one appear."""
        opened(tmp_path)
        assert store_at(tmp_path).list_workflow_ids() == []


# ---------------------------------------------------------------------------------------------
# WorkflowService boundary
# ---------------------------------------------------------------------------------------------


class TestWorkflowServiceBoundary:
    @staticmethod
    def _service(tmp_path: Path) -> Any:
        from agentos_workflow.config.schema import WorkflowConfig
        from agentos_workflow.service import WorkflowService

        repository = tmp_path / "repo"
        repository.mkdir(exist_ok=True)
        config = WorkflowConfig.model_validate(
            {
                "repository_path": str(repository),
                "repository_identity": "github.com/org/target",
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
                "claude_cli_executable": str(tmp_path / "claude"),
                "claude_cli_timeout_seconds": 30,
                "claude_cli_permission_mode": "plan",
                "codex_cli_executable": str(tmp_path / "codex"),
                "codex_cli_timeout_seconds": 30,
                "codex_cli_sandbox_mode": "read-only",
                "allowed_environment_variables": [],
                "allowed_changed_paths": ["docs/**"],
                "forbidden_changed_paths": ["src/**"],
                "repair_attempt_limit": 3,
                "state_directory": str(tmp_path / "state"),
                "audit_directory": str(tmp_path / "audit"),
            }
        )
        return WorkflowService(config)

    def test_the_full_lifecycle_is_reachable_through_the_service(self, tmp_path: Path) -> None:
        service_under_test = self._service(tmp_path)
        bound = checksums()
        opened_request = service_under_test.request_approval(
            workflow_id=WORKFLOW,
            gate=GATE,
            approval_id="ap-1",
            checksums=bound,
            policy=policy(timeout_seconds=60),
            now=T0,
        )
        assert opened_request.status is ApprovalStatus.PENDING

        assert (
            service_under_test.get_approval(workflow_id=WORKFLOW, approval_id="ap-1").status
            is ApprovalStatus.PENDING
        )
        decided = service_under_test.decide_approval(
            workflow_id=WORKFLOW,
            approval_id="ap-1",
            decision=ApprovalDecision.APPROVE,
            approver="afshin",
            source=ApprovalChannel.CLI,
            now=at(5),
        )
        assert decided.status is ApprovalStatus.APPROVED
        consumed = service_under_test.consume_approval(
            workflow_id=WORKFLOW, approval_id="ap-1", checksums=bound, now=at(10)
        )
        assert consumed.status is ApprovalStatus.CONSUMED

    def test_the_service_evaluates_timeouts_lazily(self, tmp_path: Path) -> None:
        service_under_test = self._service(tmp_path)
        service_under_test.request_approval(
            workflow_id=WORKFLOW,
            gate=GATE,
            approval_id="ap-1",
            checksums=checksums(),
            policy=policy(timeout_seconds=10, timeout_action=TimeoutAction.PAUSE),
            now=T0,
        )
        evaluated = service_under_test.evaluate_approval(
            workflow_id=WORKFLOW, approval_id="ap-1", now=at(11)
        )
        assert evaluated.status is ApprovalStatus.HUMAN_INTERVENTION_REQUIRED

    def test_the_service_adds_no_workflow_lifecycle_verb(self, tmp_path: Path) -> None:
        from agentos_workflow.service import WorkflowService

        forbidden = {
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
        assert forbidden & set(dir(WorkflowService)) == set()
