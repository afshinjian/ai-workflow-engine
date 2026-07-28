"""`PMOAgent` — precondition verification and stage-branch creation
(`AGENT_CONTRACTS.md` §2).

Drives `AUTHORIZED → PRECONDITIONS_CHECKED → BRANCH_CREATED` by *reporting*, never by deciding:
`check_preconditions` returns a pass/fail line per check and `create_branch` returns the created
branch and its base commit. `MACHINE_GATES.md` §2's rule that any precondition failure means
`FAILED` — a precondition failure is a target-repository or authorization-state problem, not
something `ImplementationAgent` could repair — is the Orchestrator's to apply.

This module imports no Skill module and no Provider module. Everything it can do arrives through
the `CapabilityBroker`, bounded by `AGENT_SKILL_CONTRACTS[AgentKind.PMO]`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agentos_workflow.agents import (
    Agent,
    AgentFailureKind,
    AgentKind,
    AgentResult,
    agent_failure,
    agent_success,
    retry_classification_of,
)

__all__ = ["BoundAuthorization", "PMOAgent", "PreconditionCheck"]


class BoundAuthorization(Protocol):
    """The authorization record's fields this Agent verifies live state against.

    A Protocol rather than an import of `orchestrator.AuthorizationRecord`: the Orchestrator
    drives Agents, so an Agent importing it would invert the layering, and the record this Agent
    needs is fully described by the seven read-only fields below. The real record satisfies this
    structurally, so the Orchestrator passes its own object unchanged.
    """

    @property
    def workflow_id(self) -> str: ...  # pragma: no cover - structural

    @property
    def stage_id(self) -> str: ...  # pragma: no cover - structural

    @property
    def repository_identity(self) -> str: ...  # pragma: no cover - structural

    @property
    def stage_contract_hash(self) -> str: ...  # pragma: no cover - structural

    @property
    def baseline_branch(self) -> str: ...  # pragma: no cover - structural

    @property
    def baseline_commit_sha(self) -> str: ...  # pragma: no cover - structural

    @property
    def planned_stage_branch(self) -> str: ...  # pragma: no cover - structural


@dataclass(frozen=True)
class PreconditionCheck:
    """One precondition's outcome, in the order `MACHINE_GATES.md` §2 lists them."""

    name: str
    passed: bool
    detail: str = ""


class PMOAgent(Agent):
    """Verifies every precondition, then creates the stage branch."""

    @property
    def kind(self) -> AgentKind:
        return AgentKind.PMO

    def check_preconditions(
        self,
        *,
        authorization: BoundAuthorization,
        repository_path: Path,
        remote_name: str,
        contract_directory: Path,
        stage_registry: Path,
        audit_root: Path,
        later_stage_paths: dict[str, tuple[str, ...]] | None = None,
        current_stage_allowed_paths: tuple[str, ...] = (),
    ) -> AgentResult:
        """Run the Precondition Gate's checks and report all of them.

        Every check runs even after one fails. An operator resolving a precondition failure needs
        the whole picture — "wrong remote *and* dirty tree" is one fix cycle, whereas reporting
        them one gate run at a time is three.

        The contract-hash comparison is the one check that is not merely an observation: it
        compares the live contract file's hash against the hash bound at authorization
        (`HUMAN_AUTHORIZATION_MODEL.md` §2). A mismatch means the stage contract changed after the
        Human Owner authorized it, so what would be implemented is not what was authorized.
        """
        action = "check_preconditions"
        checks: list[PreconditionCheck] = []

        identity = self._broker.invoke_skill(
            "verify_repository_identity",
            repository_path=repository_path,
            expected_identity=authorization.repository_identity,
            remote_name=remote_name,
        )
        identity_ok = bool(
            identity.ok and identity.value is not None and identity.value.matches_expected
        )
        checks.append(
            PreconditionCheck(
                name="repository_identity",
                passed=identity_ok,
                detail="" if identity_ok else _detail(identity, "remote identity does not match"),
            )
        )

        tree = self._broker.invoke_skill("inspect_working_tree", repository_path=repository_path)
        tree_clean = bool(tree.ok and tree.value is not None and tree.value.clean)
        working_tree_paths: tuple[str, ...] = (
            tree.value.paths if tree.ok and tree.value is not None else ()
        )
        checks.append(
            PreconditionCheck(
                name="working_tree_clean",
                passed=tree_clean,
                detail="" if tree_clean else _detail(tree, "working tree is not clean"),
            )
        )

        branch = self._broker.invoke_skill(
            "inspect_current_branch", repository_path=repository_path
        )
        on_baseline = bool(
            branch.ok
            and branch.value is not None
            and not branch.value.detached
            and branch.value.branch == authorization.baseline_branch
        )
        checks.append(
            PreconditionCheck(
                name="current_branch",
                passed=on_baseline,
                detail=(
                    ""
                    if on_baseline
                    else _detail(branch, f"expected baseline {authorization.baseline_branch!r}")
                ),
            )
        )

        ancestry = self._broker.invoke_skill(
            "verify_baseline_ancestry",
            repository_path=repository_path,
            baseline_branch=authorization.baseline_branch,
        )
        checks.append(
            PreconditionCheck(
                name="baseline_ancestry",
                passed=bool(ancestry.ok),
                detail="" if ancestry.ok else _detail(ancestry, "ancestry check failed"),
            )
        )

        located = self._broker.invoke_skill(
            "locate_stage_contract",
            stage_id=authorization.stage_id,
            contract_directory=contract_directory,
        )
        contract_file = located.value if located.ok else None
        checks.append(
            PreconditionCheck(
                name="stage_contract_located",
                passed=contract_file is not None,
                detail="" if contract_file is not None else _detail(located, "contract not found"),
            )
        )

        metadata: Any = None
        contract_hash_matches = False
        hash_detail = "stage contract could not be located"
        if contract_file is not None:
            parsed = self._broker.invoke_skill("parse_stage_metadata", contract_file=contract_file)
            metadata = parsed.value if parsed.ok else None
            checks.append(
                PreconditionCheck(
                    name="stage_contract_parsed",
                    passed=metadata is not None,
                    detail="" if metadata is not None else _detail(parsed, "contract unparseable"),
                )
            )
            hashed = self._broker.invoke_skill(
                "calculate_contract_hash", contract_file=contract_file
            )
            if hashed.ok and hashed.value is not None:
                contract_hash_matches = hashed.value.sha256 == authorization.stage_contract_hash
                hash_detail = (
                    ""
                    if contract_hash_matches
                    else (
                        "stage contract changed since authorization: bound "
                        f"{authorization.stage_contract_hash}, found {hashed.value.sha256}"
                    )
                )
            else:
                hash_detail = _detail(hashed, "contract hash could not be calculated")
        else:
            checks.append(
                PreconditionCheck(
                    name="stage_contract_parsed",
                    passed=False,
                    detail="stage contract could not be located",
                )
            )
        checks.append(
            PreconditionCheck(
                name="stage_contract_hash",
                passed=contract_hash_matches,
                detail=hash_detail,
            )
        )

        ordering = self._broker.invoke_skill(
            "validate_stage_ordering",
            stage_id=authorization.stage_id,
            stage_registry=stage_registry,
        )
        checks.append(
            PreconditionCheck(
                name="stage_ordering",
                passed=bool(ordering.ok),
                detail="" if ordering.ok else _detail(ordering, "stage ordering is not satisfied"),
            )
        )

        future_work = self._broker.invoke_skill(
            "detect_future_stage_work",
            changed_files=working_tree_paths,
            current_stage_allowed_paths=current_stage_allowed_paths,
            later_stage_paths=dict(later_stage_paths or {}),
        )
        no_future_work = bool(
            future_work.ok and future_work.value is not None and future_work.value.passed
        )
        checks.append(
            PreconditionCheck(
                name="no_future_stage_work",
                passed=no_future_work,
                detail="" if no_future_work else _detail(future_work, "future-stage work detected"),
            )
        )

        passed = all(check.passed for check in checks)
        evidence: dict[str, Any] = {
            "stage_id": authorization.stage_id,
            "workflow_id": authorization.workflow_id,
            "checks": [
                {"check": check.name, "passed": check.passed, "detail": check.detail}
                for check in checks
            ],
            "planned_stage_branch": authorization.planned_stage_branch,
            "baseline_commit_sha": authorization.baseline_commit_sha,
            "stage_contract_path": str(contract_file) if contract_file is not None else None,
            "stage_metadata_branch": getattr(metadata, "branch", None),
        }
        self._audit(
            {
                "action": action,
                "passed": passed,
                "failed": [check.name for check in checks if not check.passed],
            },
            audit_root=audit_root,
            workflow_id=authorization.workflow_id,
        )
        if not passed:
            failed = ", ".join(check.name for check in checks if not check.passed)
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.PRECONDITION,
                f"precondition(s) not satisfied: {failed}",
                evidence=evidence,
            )
        return agent_success(self.kind, action, evidence)

    def create_branch(
        self,
        *,
        authorization: BoundAuthorization,
        repository_path: Path,
        audit_root: Path,
    ) -> AgentResult:
        """Create the stage branch at the authorized baseline commit.

        The branch name and the base SHA both come from the authorization record, never from
        configuration or from the stage contract's own metadata: the branch that gets created must
        be the branch the Human Owner authorized, and reading either value from anywhere else
        would let a contract edit redirect the work.
        """
        action = "create_branch"
        created = self._broker.invoke_skill(
            "create_stage_branch",
            repository_path=repository_path,
            branch_name=authorization.planned_stage_branch,
            base_sha=authorization.baseline_commit_sha,
            baseline_branch=authorization.baseline_branch,
        )
        if not created.ok or created.value is None:
            self._audit(
                {"action": action, "passed": False},
                audit_root=audit_root,
                workflow_id=authorization.workflow_id,
            )
            return agent_failure(
                self.kind,
                action,
                AgentFailureKind.SKILL_FAILED,
                _detail(created, "stage branch could not be created"),
                retry_classification=retry_classification_of(created),
                source="create_stage_branch",
            )
        state = created.value
        evidence = {
            "stage_branch": state.branch,
            "base_commit_sha": state.head_sha,
            "workflow_id": authorization.workflow_id,
            "stage_id": authorization.stage_id,
        }
        self._audit(
            {"action": action, "passed": True, "stage_branch": state.branch},
            audit_root=audit_root,
            workflow_id=authorization.workflow_id,
        )
        return agent_success(self.kind, action, evidence)


def _detail(result: Any, fallback: str) -> str:
    """The Skill's own failure text when there is one, else a caller-supplied description."""
    error = getattr(result, "error", None)
    return str(error) if error is not None else fallback
