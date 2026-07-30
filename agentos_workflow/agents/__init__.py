"""Agents (`AGENT_CONTRACTS.md`) and the primitives that bound what each one can do.

An Agent is a *bounded caller*. It holds no subprocess, filesystem, or network access of its own
(`AGENT_CONTRACTS.md` §1): every side effect goes through a named Skill or Model Provider reached
via the `CapabilityBroker` below, and every method returns a structured `AgentResult` the
Orchestrator reads as evidence. No Agent decides its own resulting workflow-state transition —
there is no state field anywhere in this package's result types, so "the Agent chose the next
state" is unrepresentable rather than merely forbidden.

**The capability boundary.** Each Agent's contract lists exactly which Skills and Provider roles it
may invoke. That list is data here (`AGENT_SKILL_CONTRACTS`, `AGENT_PROVIDER_CONTRACTS`), the
broker checks every call against it, and the six Agent modules import no Skill or Provider module
directly — they receive a broker. Two independent properties therefore enforce the boundary: the
runtime check, and the absence of any import that would let an Agent bypass the broker at all
(asserted over the modules' own source in `test_agents_capabilities.py`, the same AST technique
AUTO-003 and AUTO-004 already use for their structural claims).

**Why this module also holds two Orchestrator-owned sequences.** `run_deterministic_validation`
(the `VALIDATING` step, `MACHINE_GATES.md` §3) and `run_repair_loop`
(`FAILURE_RECOVERY.md` §1-2) are deliberately **not** a seventh Agent, per
`AGENT_CONTRACTS.md` §8: they are the Orchestrator's own logic, unbounded by any capability set,
and they decide nothing about state either — each returns an outcome the Orchestrator acts on.
They live in this module rather than in `orchestrator/` because AUTO-005's contract scopes this
stage to `agentos_workflow/agents/**`; both take their collaborators as Protocols, so neither is
coupled to a concrete Agent class and this package has no import cycle.

**Provisional Skills.** Eight Skills named by the Agent contracts are GitHub-facing and are
delivered by AUTO-006, not by AUTO-003: `create_commit`, `push_stage_branch`,
`create_pull_request`, `read_pull_request_state`, `verify_head_sha`, `read_required_checks`,
`enable_automatic_squash_merge`, and `verify_merge_completion`. They are named in the contracts
here and left **unbound** in the default registry, so an Agent that reaches for one gets a typed
`SKILL_UNAVAILABLE` failure naming AUTO-006 rather than a stub that silently claims success. A
fake binding is how `GitAgent`/`MergeAgent` are tested today; AUTO-006 replaces the fakes with
real bindings and changes no Agent code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from agentos_workflow.config.schema import WorkflowConfig
from agentos_workflow.providers import (
    Provider,
    ProviderRole,
    select_live_provider,
)
from agentos_workflow.skills import (
    FailureKind,
    RetryClassification,
    SkillFailure,
    SkillResult,
    redact_secrets,
    utc_now,
)
from agentos_workflow.skills import contract as contract_skills
from agentos_workflow.skills import git_github as git_github_skills
from agentos_workflow.skills import reporting as reporting_skills
from agentos_workflow.skills import repository as repository_skills
from agentos_workflow.skills import validation as validation_skills

__all__ = [
    "AGENT_PROVIDER_CONTRACTS",
    "AGENT_SKILL_CONTRACTS",
    "PROVISIONAL_SKILL_NAMES",
    "VALIDATION_GATE_CHECKS",
    "Agent",
    "AgentFailure",
    "AgentFailureKind",
    "AgentKind",
    "AgentResult",
    "CapabilityBroker",
    "CapabilityViolation",
    "ProviderGateway",
    "RepairAttemptRecord",
    "RepairLoopOutcome",
    "RepairingImplementationAgent",
    "ReviewingQAAgent",
    "ValidationCheck",
    "ValidationOutcome",
    "agent_failure",
    "agent_success",
    "default_skill_registry",
    "live_provider_gateway",
    "retry_classification_of",
    "run_deterministic_validation",
    "run_repair_loop",
]


def retry_classification_of(result: SkillResult[Any]) -> RetryClassification:
    """Carry a Skill's own retry classification onto the Agent result that reports it.

    An Agent never *decides* retryability — `SKILL_CONTRACTS.md` §5 classifies by whether the
    underlying operation could already have taken effect, which only the Skill that ran it knows.
    Forwarding the Skill's answer keeps the Orchestrator's retry/reconciliation decision
    (`WORKFLOW_STATES.md` §5a) working from the original evidence rather than an Agent's guess.
    """
    error = result.error
    return error.retry_classification if error is not None else RetryClassification.NOT_APPLICABLE


class AgentKind(StrEnum):
    """The six Agents of `AGENT_CONTRACTS.md` §2-7. There is no seventh."""

    PMO = "pmo"
    IMPLEMENTATION = "implementation"
    QA = "qa"
    GIT = "git"
    MERGE = "merge"
    CLOSEOUT = "closeout"


class AgentFailureKind(StrEnum):
    """Why an Agent action did not succeed, at a granularity the Orchestrator can branch on."""

    PRECONDITION = "precondition"
    SKILL_FAILED = "skill_failed"
    SKILL_UNAVAILABLE = "skill_unavailable"
    PROVIDER_FAILED = "provider_failed"
    GATE_EVIDENCE = "gate_evidence"


@dataclass(frozen=True)
class AgentFailure:
    """A typed failure. Never an exception crossing the Orchestrator boundary."""

    agent: AgentKind
    action: str
    kind: AgentFailureKind
    detail: str
    retry_classification: RetryClassification = RetryClassification.NOT_APPLICABLE
    source: str | None = None

    def __str__(self) -> str:
        return f"{self.agent.value}.{self.action}: {self.kind.value}: {self.detail}"


@dataclass(frozen=True)
class AgentResult:
    """One Agent action's outcome.

    `evidence` is what the Orchestrator's machine gates read; it is never itself an authority
    (`AGENT_CONTRACTS.md` §1, `ARCHITECTURE.md` §6). Note what this type does **not** have: a next
    state, a transition name, or a verdict the Orchestrator is expected to apply. An Agent reports;
    the Orchestrator decides.
    """

    agent: AgentKind
    action: str
    ok: bool
    evidence: Mapping[str, Any] = field(default_factory=dict)
    error: AgentFailure | None = None


def agent_success(
    agent: AgentKind, action: str, evidence: Mapping[str, Any] | None = None
) -> AgentResult:
    return AgentResult(
        agent=agent, action=action, ok=True, evidence=MappingProxyType(dict(evidence or {}))
    )


def agent_failure(
    agent: AgentKind,
    action: str,
    kind: AgentFailureKind,
    detail: str,
    *,
    retry_classification: RetryClassification = RetryClassification.NOT_APPLICABLE,
    source: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> AgentResult:
    """Build a failed result. `detail` is redacted before it is stored or surfaced."""
    return AgentResult(
        agent=agent,
        action=action,
        ok=False,
        evidence=MappingProxyType(dict(evidence or {})),
        error=AgentFailure(
            agent=agent,
            action=action,
            kind=kind,
            detail=redact_secrets(detail),
            retry_classification=retry_classification,
            source=source,
        ),
    )


class CapabilityViolation(Exception):
    """An Agent attempted a Skill or Provider role outside its own contract.

    This raises rather than returning a typed failure, and does so deliberately. It is the same
    judgement `providers.select_live_provider` already makes for an unmapped role: a capability
    violation is a programming error in the engine, not a workflow outcome a machine gate could
    sensibly branch on. Returning it as an ordinary failure would let it be logged, counted as a
    repair-worthy problem, and stepped over — when the only correct response is to fix the caller.

    It does not weaken `AGENT_CONTRACTS.md` §1's "always returns a structured result": every one of
    the six Agents names only Skills from its own contract, so no public Agent method can reach
    this path. `test_agents_capabilities.py` proves that over the modules' own source rather than
    asserting it in prose.
    """


SkillBinding = Callable[..., SkillResult[Any]]
ProviderGateway = Callable[[ProviderRole], Provider]

# Skills an Agent contract names that no delivered module implements yet.
#
# Empty since GOV-AUTO-06. It previously listed the eight GitHub-facing Skills as undelivered,
# which was true when AUTO-003 wrote it and stopped being true when AUTO-006 landed
# `skills/git_github.py` — but nothing updated this set or `_DEFAULT_SKILL_BINDINGS`, so
# `GitAgent` and `MergeAgent` were told their own contracted Skills "will be delivered by
# AUTO-006" *by the stage that had already delivered them*. Every one of the eight is now bound
# below.
#
# The set itself is kept rather than deleted, and `CapabilityBroker.invoke_skill` still consults
# it. The mechanism is general and worth preserving: a contract may legitimately name a Skill
# before its implementing stage lands, and answering that with a typed `PRECONDITION` failure
# instead of a `CapabilityViolation` is the right distinction — "not built yet" is a deployment
# state a machine gate can act on, whereas "not permitted" is a programming error. What was stale
# was the membership, not the concept. An empty set simply means nothing is currently in that
# state.
PROVISIONAL_SKILL_NAMES: frozenset[str] = frozenset()

_DEFAULT_SKILL_BINDINGS: Mapping[str, SkillBinding] = MappingProxyType(
    {
        # Repository family (`SKILL_CONTRACTS.md` §2).
        "verify_repository_identity": repository_skills.verify_repository_identity,
        "inspect_working_tree": repository_skills.inspect_working_tree,
        "inspect_current_branch": repository_skills.inspect_current_branch,
        "verify_baseline_ancestry": repository_skills.verify_baseline_ancestry,
        "list_changed_files": repository_skills.list_changed_files,
        "inspect_diff": repository_skills.inspect_diff,
        "verify_final_repository_state": repository_skills.verify_final_repository_state,
        "create_stage_branch": repository_skills.create_stage_branch,
        "checkout_baseline": repository_skills.checkout_baseline,
        "fast_forward_pull": repository_skills.fast_forward_pull,
        "delete_local_branch": repository_skills.delete_local_branch,
        "delete_remote_branch": repository_skills.delete_remote_branch,
        # Contract family (§3).
        "locate_stage_contract": contract_skills.locate_stage_contract,
        "parse_stage_metadata": contract_skills.parse_stage_metadata,
        "calculate_contract_hash": contract_skills.calculate_contract_hash,
        "validate_stage_ordering": contract_skills.validate_stage_ordering,
        "validate_allowed_paths": contract_skills.validate_allowed_paths,
        "detect_future_stage_work": contract_skills.detect_future_stage_work,
        # Git/GitHub family (§5), delivered by AUTO-006 and bound here by GOV-AUTO-06.
        #
        # These are the eight Skills `PROVISIONAL_SKILL_NAMES` used to list as undelivered. Binding
        # them changes no capability boundary: `AGENT_SKILL_CONTRACTS` already permitted exactly
        # these names to exactly `GIT` and `MERGE` (and to no other Agent), and the broker checks
        # that contract before it ever consults this registry. What changes is only that a
        # permitted call now reaches its real implementation instead of a "not yet implemented"
        # failure.
        "create_commit": git_github_skills.create_commit,
        "push_stage_branch": git_github_skills.push_stage_branch,
        "create_pull_request": git_github_skills.create_pull_request,
        "read_pull_request_state": git_github_skills.read_pull_request_state,
        "verify_head_sha": git_github_skills.verify_head_sha,
        "read_required_checks": git_github_skills.read_required_checks,
        "enable_automatic_squash_merge": git_github_skills.enable_automatic_squash_merge,
        "verify_merge_completion": git_github_skills.verify_merge_completion,
        # Validation family (§4).
        "run_tests": validation_skills.run_tests,
        "run_lint": validation_skills.run_lint,
        "run_formatting_checks": validation_skills.run_formatting_checks,
        "run_security_checks": validation_skills.run_security_checks,
        "run_scope_validation": validation_skills.run_scope_validation,
        "run_secret_detection": validation_skills.run_secret_detection,
        "validate_completion_report": validation_skills.validate_completion_report,
        "validate_qa_report": validation_skills.validate_qa_report,
        # Reporting family (§6).
        "generate_stage_report": reporting_skills.generate_stage_report,
        "generate_qa_report": reporting_skills.generate_qa_report,
        "generate_failure_report": reporting_skills.generate_failure_report,
        "generate_closeout_report": reporting_skills.generate_closeout_report,
        "write_sanitized_output": reporting_skills.write_sanitized_output,
        "append_audit_event": reporting_skills.append_audit_event,
    }
)


def default_skill_registry() -> Mapping[str, SkillBinding]:
    """Every delivered Skill, bound to its implementation — the production registry.

    Complete as of GOV-AUTO-06: every name any Agent contract mentions resolves here, so no Agent
    is told a Skill is missing that in fact exists. The eight Git/GitHub Skills were absent for as
    long as AUTO-006 had not landed, which was the honest answer then — a stub returning success
    would have been a lie a machine gate would happily accept. Once AUTO-006 delivered them, the
    same absence became the opposite kind of lie, and `GitAgent`/`MergeAgent` could not run against
    this registry at all. They are bound now.

    This function grants nothing on its own. `AGENT_SKILL_CONTRACTS` decides which Agent may invoke
    which name, and `CapabilityBroker` enforces that before consulting this mapping — a Skill being
    present here never widens any Agent's reach.
    """
    return _DEFAULT_SKILL_BINDINGS


# The Skills each Agent may invoke, transcribed from `AGENT_CONTRACTS.md` §2-7. This mapping is the
# single source of truth for the capability boundary: the broker enforces it and
# `test_agents_capabilities.py` checks it against the contract document's own lists.
AGENT_SKILL_CONTRACTS: Mapping[AgentKind, frozenset[str]] = MappingProxyType(
    {
        AgentKind.PMO: frozenset(
            {
                "verify_repository_identity",
                "inspect_working_tree",
                "inspect_current_branch",
                "verify_baseline_ancestry",
                "locate_stage_contract",
                "parse_stage_metadata",
                "calculate_contract_hash",
                "validate_stage_ordering",
                "detect_future_stage_work",
                "create_stage_branch",
                "append_audit_event",
            }
        ),
        AgentKind.IMPLEMENTATION: frozenset(
            {
                "inspect_diff",
                "list_changed_files",
                "validate_allowed_paths",
                "validate_completion_report",
                "append_audit_event",
            }
        ),
        AgentKind.QA: frozenset(
            {
                "run_tests",
                "run_lint",
                "run_formatting_checks",
                "run_scope_validation",
                "run_security_checks",
                "run_secret_detection",
                "validate_qa_report",
                "generate_qa_report",
                "append_audit_event",
            }
        ),
        AgentKind.GIT: frozenset(
            {
                "create_commit",
                "push_stage_branch",
                "create_pull_request",
                "read_pull_request_state",
                "verify_head_sha",
                "append_audit_event",
            }
        ),
        AgentKind.MERGE: frozenset(
            {
                "verify_head_sha",
                "read_required_checks",
                "enable_automatic_squash_merge",
                "verify_merge_completion",
                "append_audit_event",
            }
        ),
        AgentKind.CLOSEOUT: frozenset(
            {
                "checkout_baseline",
                "fast_forward_pull",
                "delete_local_branch",
                "delete_remote_branch",
                "verify_final_repository_state",
                "generate_closeout_report",
                "append_audit_event",
            }
        ),
    }
)

# Provider roles each Agent may invoke. Only two Agents may reach a Provider at all; the other four
# are deterministic-Skill-only by contract, and an empty set is what makes that structural.
AGENT_PROVIDER_CONTRACTS: Mapping[AgentKind, frozenset[ProviderRole]] = MappingProxyType(
    {
        AgentKind.PMO: frozenset(),
        AgentKind.IMPLEMENTATION: frozenset({ProviderRole.IMPLEMENTATION, ProviderRole.REPAIR}),
        AgentKind.QA: frozenset({ProviderRole.QA}),
        AgentKind.GIT: frozenset(),
        AgentKind.MERGE: frozenset(),
        AgentKind.CLOSEOUT: frozenset(),
    }
)


def live_provider_gateway(config: WorkflowConfig) -> ProviderGateway:
    """The Provider gateway a real authorized workflow uses.

    Delegates to `providers.select_live_provider`, which is typed to return a `CLIProvider` and so
    cannot yield a `MockProvider` (`MODEL_PROVIDER_CONTRACTS.md` §4). A test or dry run supplies
    its own gateway explicitly instead; there is no configuration value that swaps this one out.
    """

    def gateway(role: ProviderRole) -> Provider:
        return select_live_provider(role, config)

    return gateway


class CapabilityBroker:
    """The only route an Agent has to a Skill or a Provider.

    Construction binds the broker to one `AgentKind`, and every call is checked against that
    Agent's contract before the registry is consulted. Ordering matters: the capability check
    happens *first*, so an out-of-contract call is refused identically whether the Skill exists,
    is provisional, or was never a Skill at all — a broker that leaked "no such Skill" for one
    denied name and "not permitted" for another would be an enumeration oracle for the boundary.
    """

    def __init__(
        self,
        agent: AgentKind,
        *,
        skills: Mapping[str, SkillBinding] | None = None,
        providers: ProviderGateway | None = None,
    ) -> None:
        self._agent = agent
        self._skills: Mapping[str, SkillBinding] = dict(
            skills if skills is not None else default_skill_registry()
        )
        self._providers = providers
        self._allowed_skills = AGENT_SKILL_CONTRACTS[agent]
        self._allowed_roles = AGENT_PROVIDER_CONTRACTS[agent]
        self._skill_calls: list[str] = []
        self._provider_calls: list[ProviderRole] = []

    @property
    def agent(self) -> AgentKind:
        return self._agent

    @property
    def skill_calls(self) -> tuple[str, ...]:
        """Every Skill name invoked through this broker, in order — the Orchestrator's and a
        test's record of what an Agent actually reached for."""
        return tuple(self._skill_calls)

    @property
    def provider_calls(self) -> tuple[ProviderRole, ...]:
        return tuple(self._provider_calls)

    def permits_skill(self, name: str) -> bool:
        return name in self._allowed_skills

    def permits_role(self, role: ProviderRole) -> bool:
        return role in self._allowed_roles

    def invoke_skill(self, name: str, /, **kwargs: Any) -> SkillResult[Any]:
        """Invoke a Skill by name, or refuse.

        Raises `CapabilityViolation` for a name outside this Agent's contract. Returns a typed
        `SkillFailure` for a permitted-but-unbound (provisional, AUTO-006) name — that is a
        deployment state a machine gate can reasonably observe, not a programming error.
        """
        if name not in self._allowed_skills:
            raise CapabilityViolation(
                f"{self._agent.value} may not invoke skill {name!r}; its contract permits "
                f"{sorted(self._allowed_skills)}"
            )
        binding = self._skills.get(name)
        if binding is None:
            # GOV-AUTO-06 removed the "delivered by AUTO-006" wording: naming one stage made this
            # message go stale the moment that stage landed, and it kept asserting AUTO-006 was
            # pending for the whole period after it had shipped. The distinction being drawn is
            # between "contract names it, nothing implements it yet" and "this registry happens not
            # to bind it", which is what an operator needs and is true regardless of stage.
            detail = (
                f"skill {name!r} is not yet implemented"
                if name in PROVISIONAL_SKILL_NAMES
                else f"skill {name!r} is not bound in this registry"
            )
            return SkillResult(
                ok=False,
                error=SkillFailure(
                    skill=name,
                    kind=FailureKind.PRECONDITION,
                    detail=detail,
                    retry_classification=RetryClassification.NON_RETRYABLE,
                ),
            )
        self._skill_calls.append(name)
        return binding(**kwargs)

    def provider(self, role: ProviderRole) -> Provider:
        """Return the Provider for `role`, or refuse.

        Raises `CapabilityViolation` for a role outside this Agent's contract, and for a broker
        constructed without a gateway at all — an Agent that reaches for a Provider it was never
        given one for is a wiring error, and a silent no-op would let a workflow proceed as though
        a model had been consulted when none was.
        """
        if role not in self._allowed_roles:
            raise CapabilityViolation(
                f"{self._agent.value} may not invoke provider role {role.value!r}; its contract "
                f"permits {sorted(existing.value for existing in self._allowed_roles)}"
            )
        if self._providers is None:
            raise CapabilityViolation(
                f"{self._agent.value} was constructed without a provider gateway"
            )
        self._provider_calls.append(role)
        return self._providers(role)


class Agent(ABC):
    """Common base: an Agent is a capability set plus a set of actions over it."""

    def __init__(self, broker: CapabilityBroker) -> None:
        if broker.agent is not self.kind:
            raise CapabilityViolation(
                f"{type(self).__name__} requires a {self.kind.value} broker, got "
                f"{broker.agent.value}"
            )
        self._broker = broker

    @property
    @abstractmethod
    def kind(self) -> AgentKind:
        """Which Agent of `AGENT_CONTRACTS.md` §2-7 this is."""

    @property
    def broker(self) -> CapabilityBroker:
        return self._broker

    def _audit(self, event: dict[str, Any], *, audit_root: Path, workflow_id: str) -> None:
        """Append one audit event, ignoring the result.

        Deliberately fire-and-forget: an audit-append failure must not turn a successful workflow
        action into a failed one, and the Skill already never raises. The event's own content is
        the record; a failure to write it is visible in the Skill's own return value, which the
        Orchestrator can also observe through `broker.skill_calls`.
        """
        self._broker.invoke_skill(
            "append_audit_event",
            audit_root=audit_root,
            workflow_id=workflow_id,
            event={"agent": self.kind.value, **event},
        )


# ------------------------------------------------------------------------------------------------
# Orchestrator-owned sequences (`AGENT_CONTRACTS.md` §8) — not Agents.
# ------------------------------------------------------------------------------------------------

# The deterministic validation gate's complete check list (`MACHINE_GATES.md` §3). Ordering is
# fixed and cheap-first so an obviously-broken diff fails fast, but *every* check runs regardless:
# a repair attempt that sees only the first failure fixes one thing per attempt and exhausts the
# attempt budget on a diff with three problems.
VALIDATION_GATE_CHECKS: tuple[str, ...] = (
    "run_scope_validation",
    "run_secret_detection",
    "run_formatting_checks",
    "run_lint",
    "run_tests",
    "run_security_checks",
    "validate_completion_report",
)


@dataclass(frozen=True)
class ValidationCheck:
    """One deterministic check's outcome."""

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ValidationOutcome:
    """The `VALIDATING` gate's result (`MACHINE_GATES.md` §3).

    `passed` is the conjunction of every check — never a subset, and never short-circuited into a
    pass. The Orchestrator, not this function, turns a `False` into `REPAIRING` or `FAILED`.
    """

    passed: bool
    checks: tuple[ValidationCheck, ...]

    @property
    def failed_checks(self) -> tuple[ValidationCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def failure_report(self) -> dict[str, Any]:
        """The deterministic-validation failure detail a repair attempt receives
        (`FAILURE_RECOVERY.md` §2)."""
        return {
            "source": "deterministic_validation",
            "failed_checks": [
                {"check": check.name, "detail": check.detail} for check in self.failed_checks
            ],
        }


def run_deterministic_validation(
    *,
    config: WorkflowConfig,
    changed_files: Sequence[str],
    completion_report_path: Path,
    skills: Mapping[str, SkillBinding] | None = None,
) -> ValidationOutcome:
    """Run the `VALIDATING` gate as an Orchestrator-owned sequence of Validation Skills.

    This is not an Agent and has no capability set: the Orchestrator is the authority the
    capability boundary protects, not a subject of it (`AGENT_CONTRACTS.md` §8). It decides
    nothing about state — it returns what every check found, and the Orchestrator applies
    `MACHINE_GATES.md` §3's on-fail rule.

    Every check runs even after one fails, for the reason `VALIDATION_GATE_CHECKS` records. A Skill
    that fails to *run* (an unspawnable command) is a failed check here, not an exception: from the
    gate's point of view "the tests could not be run" and "the tests failed" are both "the gate did
    not pass", and only the detail differs.
    """
    registry = dict(skills if skills is not None else default_skill_registry())
    paths = tuple(changed_files)
    arguments: Mapping[str, Mapping[str, Any]] = {
        "run_scope_validation": {
            "changed_files": paths,
            "allowed_paths": tuple(config.allowed_changed_paths),
            "forbidden_paths": tuple(config.forbidden_changed_paths),
        },
        "run_secret_detection": {
            "changed_files": paths,
            "repository_path": config.repository_path,
        },
        "run_formatting_checks": {
            "repository_path": config.repository_path,
            "formatting_command": config.formatting_command,
            "allowed_environment_variables": tuple(config.allowed_environment_variables),
        },
        "run_lint": {
            "repository_path": config.repository_path,
            "lint_command": config.lint_command,
            "allowed_environment_variables": tuple(config.allowed_environment_variables),
        },
        "run_tests": {
            "repository_path": config.repository_path,
            "test_command": config.test_command,
            "allowed_environment_variables": tuple(config.allowed_environment_variables),
        },
        "run_security_checks": {
            "repository_path": config.repository_path,
            "security_command": config.security_command,
            "allowed_environment_variables": tuple(config.allowed_environment_variables),
        },
        "validate_completion_report": {"report_path": completion_report_path},
    }

    checks: list[ValidationCheck] = []
    for name in VALIDATION_GATE_CHECKS:
        binding = registry.get(name)
        if binding is None:
            checks.append(
                ValidationCheck(name=name, passed=False, detail=f"skill {name!r} is not bound")
            )
            continue
        result = binding(**arguments[name])
        checks.append(_interpret_validation_result(name, result))
    return ValidationOutcome(passed=all(check.passed for check in checks), checks=tuple(checks))


def _interpret_validation_result(name: str, result: SkillResult[Any]) -> ValidationCheck:
    """Turn one Validation Skill's typed result into a gate check.

    Three shapes exist and are kept distinct: a Skill failure (could not run), a successful run
    reporting a `passed=False` verdict (ran, found problems), and a plain success. Collapsing the
    first two would lose the difference between "the security scanner is missing" and "the
    security scanner found something", which is exactly what an operator reads the report for.
    """
    if not result.ok or result.value is None:
        return ValidationCheck(name=name, passed=False, detail=str(result.error))
    value = result.value
    passed = getattr(value, "passed", True)
    if not isinstance(passed, bool):  # pragma: no cover - every Skill value uses a bool
        passed = True
    detail = ""
    if not passed:
        detail = _describe_validation_failure(value)
    return ValidationCheck(name=name, passed=passed, detail=redact_secrets(detail))


def _describe_validation_failure(value: Any) -> str:
    """A short, already-redacted description of why a check reported `passed=False`."""
    violations = getattr(value, "violations", None)
    if violations:
        return "; ".join(f"{item.path}: {item.reason}" for item in violations)
    findings = getattr(value, "findings", None)
    if findings:
        return "; ".join(f"{item.path}:{item.line_number}: {item.kind}" for item in findings)
    schema_errors = getattr(value, "schema_errors", None)
    if schema_errors:
        return "; ".join(str(error) for error in schema_errors)
    execution = getattr(value, "execution", None)
    if execution is not None:
        return f"exit_code={execution.exit_code} outcome={execution.outcome.value}"
    return "check reported failure"


class RepairingImplementationAgent(Protocol):
    """The repair-side surface `run_repair_loop` needs from `ImplementationAgent`.

    A Protocol, not the concrete class, for two reasons: it keeps this Orchestrator-owned function
    from importing an Agent module (which would make the package cyclic), and it states exactly
    what the loop is allowed to ask an Agent to do — produce one repair attempt, nothing else.
    """

    def repair(
        self, *, failure_report: Mapping[str, Any], attempt_number: int
    ) -> AgentResult: ...  # pragma: no cover - structural


class ReviewingQAAgent(Protocol):
    """The review-side surface `run_repair_loop` needs from `QAAgent`."""

    def review(
        self, *, validation: ValidationOutcome, attempt_number: int
    ) -> AgentResult: ...  # pragma: no cover - structural


@dataclass(frozen=True)
class RepairAttemptRecord:
    """What one repair attempt did and what re-validation found afterwards.

    `validation` and `qa` are both present (or explicitly absent with a reason) for *every*
    attempt, which is how `FAILURE_RECOVERY.md` §1's "all deterministic validations and
    independent QA run again in full after every attempt" is made checkable rather than asserted.
    """

    attempt_number: int
    implementation: AgentResult
    validation: ValidationOutcome | None
    qa: AgentResult | None
    passed: bool


@dataclass(frozen=True)
class RepairLoopOutcome:
    """The repair loop's result. Terminal-state selection remains the Orchestrator's."""

    repaired: bool
    attempts: tuple[RepairAttemptRecord, ...]
    attempt_limit: int
    exhausted: bool
    failure_report: Mapping[str, Any] | None = None

    @property
    def repair_attempts_used(self) -> int:
        return len(self.attempts)

    @property
    def total_implementation_attempts(self) -> int:
        """Repair attempts plus the one initial implementation that preceded this loop."""
        return len(self.attempts) + 1


def run_repair_loop(
    *,
    implementation: RepairingImplementationAgent,
    qa: ReviewingQAAgent,
    validate: Callable[[], ValidationOutcome],
    initial_failure_report: Mapping[str, Any],
    attempt_limit: int,
    workflow_id: str = "",
    stage_id: str = "",
) -> RepairLoopOutcome:
    """Drive `FAILURE_RECOVERY.md` §1-2's bounded automatic repair.

    Each attempt: `ImplementationAgent.repair` receives the **latest** failure report — the one
    produced by the attempt immediately before it, never a stale report from an earlier round
    (§1) — then *all* deterministic validation runs again in full, then independent QA runs again
    in full. A repair is never assumed correct and never partially re-validated: QA runs even when
    validation passed and validation runs even when the previous attempt's QA was the only
    failure.

    The loop stops hard at `attempt_limit` repair attempts (`repair_attempt_limit`, pinned to 3 by
    the configuration schema). There is no fourth attempt, no escalation to a different provider,
    and no path that extends the budget: exhaustion produces a failure report and returns.

    This function selects no workflow state. `RepairLoopOutcome.repaired`/`exhausted` are evidence;
    `MACHINE_GATES.md` §3-4 and `WORKFLOW_STATES.md` decide what `FAILED` means and when.
    """
    attempts: list[RepairAttemptRecord] = []
    latest_failure: Mapping[str, Any] = dict(initial_failure_report)

    for attempt_number in range(1, max(attempt_limit, 0) + 1):
        implementation_result = implementation.repair(
            failure_report=latest_failure, attempt_number=attempt_number
        )
        if not implementation_result.ok:
            # `FAILURE_RECOVERY.md` §1: a repair attempt that itself produced nothing usable is
            # not re-validated against a diff that does not exist — the loop ends here and the
            # Orchestrator reads `REPAIRING → FAILED` from the recorded evidence.
            attempts.append(
                RepairAttemptRecord(
                    attempt_number=attempt_number,
                    implementation=implementation_result,
                    validation=None,
                    qa=None,
                    passed=False,
                )
            )
            return RepairLoopOutcome(
                repaired=False,
                attempts=tuple(attempts),
                attempt_limit=attempt_limit,
                exhausted=False,
                failure_report=_repair_failure_report(
                    workflow_id=workflow_id,
                    stage_id=stage_id,
                    attempts=attempts,
                    reason="repair_attempt_unusable",
                    detail=str(implementation_result.error),
                ),
            )

        validation = validate()
        qa_result = qa.review(validation=validation, attempt_number=attempt_number)
        passed = validation.passed and qa_result.ok
        attempts.append(
            RepairAttemptRecord(
                attempt_number=attempt_number,
                implementation=implementation_result,
                validation=validation,
                qa=qa_result,
                passed=passed,
            )
        )
        if passed:
            return RepairLoopOutcome(
                repaired=True,
                attempts=tuple(attempts),
                attempt_limit=attempt_limit,
                exhausted=False,
            )
        latest_failure = _latest_failure_report(validation, qa_result, attempt_number)

    return RepairLoopOutcome(
        repaired=False,
        attempts=tuple(attempts),
        attempt_limit=attempt_limit,
        exhausted=True,
        failure_report=_repair_failure_report(
            workflow_id=workflow_id,
            stage_id=stage_id,
            attempts=attempts,
            reason="repair_attempts_exhausted",
            detail=f"{len(attempts)} of {attempt_limit} repair attempts failed",
        ),
    )


def _latest_failure_report(
    validation: ValidationOutcome, qa_result: AgentResult, attempt_number: int
) -> dict[str, Any]:
    """Build the report the *next* repair attempt receives.

    Whichever gate failed is what the next attempt is told about, and both are included when both
    failed. This is the "latest, never stale" requirement of `FAILURE_RECOVERY.md` §1 expressed as
    data: the next attempt cannot receive an earlier round's report because this value is rebuilt
    from the round that just ran.
    """
    report: dict[str, Any] = {"attempt_number": attempt_number}
    if not validation.passed:
        report.update(validation.failure_report())
    if not qa_result.ok:
        report["qa"] = {
            "source": "independent_qa",
            "detail": str(qa_result.error),
            "findings": list(qa_result.evidence.get("findings", ())),
        }
    return report


def _repair_failure_report(
    *,
    workflow_id: str,
    stage_id: str,
    attempts: Sequence[RepairAttemptRecord],
    reason: str,
    detail: str,
) -> dict[str, Any]:
    """The `FAILED` report of `FAILURE_RECOVERY.md` §3: which gate failed, on which attempt, with
    what evidence."""
    return {
        "report_kind": "failure",
        "workflow_id": workflow_id,
        "stage_id": stage_id,
        "reason": reason,
        "detail": redact_secrets(detail),
        "generated_at": utc_now().isoformat(),
        "attempts": [
            {
                "attempt_number": attempt.attempt_number,
                "implementation_ok": attempt.implementation.ok,
                "validation_passed": (
                    attempt.validation.passed if attempt.validation is not None else None
                ),
                "failed_checks": (
                    [check.name for check in attempt.validation.failed_checks]
                    if attempt.validation is not None
                    else []
                ),
                "qa_ok": attempt.qa.ok if attempt.qa is not None else None,
            }
            for attempt in attempts
        ],
    }
