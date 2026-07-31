"""Capability-boundary tests for the six Agents (`AGENT_CONTRACTS.md` §1-8).

The property under test is the one §1 states first: *an Agent may only invoke the Skills and Model
Providers explicitly listed in its contract*. It is checked three ways, because any one of them
alone would be evadable:

1. **Runtime** — every out-of-contract Skill name and Provider role is refused by the broker.
2. **Against the contract document** — the capability tables in `agents/__init__.py` are compared
   to the Skill lists in `docs/workflow-automation/AGENT_CONTRACTS.md` itself, so the two cannot
   drift apart silently.
3. **Structurally** — no Agent module imports a Skill family or a Provider implementation, so an
   Agent cannot reach past its broker at all. Asserted over the modules' own source with `ast`,
   the technique AUTO-003 and AUTO-004 already use for their structural claims.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from agentos_workflow.agents import (
    AGENT_PROVIDER_CONTRACTS,
    AGENT_SKILL_CONTRACTS,
    PROVISIONAL_SKILL_NAMES,
    Agent,
    AgentKind,
    CapabilityBroker,
    CapabilityViolation,
    default_skill_registry,
)
from agentos_workflow.agents.closeout import CloseoutAgent
from agentos_workflow.agents.git import GitAgent
from agentos_workflow.agents.implementation import ImplementationAgent
from agentos_workflow.agents.merge import MergeAgent
from agentos_workflow.agents.pmo import PMOAgent
from agentos_workflow.agents.qa import QAAgent
from agentos_workflow.providers import ProviderRole
from agentos_workflow.skills import FailureKind, RetryClassification
from agentos_workflow.skills import git_github as git_github_skills

AGENT_CLASSES: dict[AgentKind, type[Agent]] = {
    AgentKind.PMO: PMOAgent,
    AgentKind.IMPLEMENTATION: ImplementationAgent,
    AgentKind.QA: QAAgent,
    AgentKind.GIT: GitAgent,
    AgentKind.MERGE: MergeAgent,
    AgentKind.CLOSEOUT: CloseoutAgent,
}

AGENT_MODULES = {
    AgentKind.PMO: "pmo",
    AgentKind.IMPLEMENTATION: "implementation",
    AgentKind.QA: "qa",
    AgentKind.GIT: "git",
    AgentKind.MERGE: "merge",
    AgentKind.CLOSEOUT: "closeout",
}

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DOCUMENT = PACKAGE_ROOT.parent / "docs" / "workflow-automation" / "AGENT_CONTRACTS.md"

ALL_CONTRACT_SKILLS = frozenset().union(*AGENT_SKILL_CONTRACTS.values())


def _executable_source(path: Path) -> str:
    """The module's source with every docstring removed.

    Structural assertions about what code *does* must not be defeated — or satisfied — by prose
    that describes it. Comments are already absent from the AST; docstrings are stripped here.
    """
    tree = ast.parse(path.read_text("utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


class TestRuntimeEnforcement:
    """Every Agent refuses every Skill and Provider role outside its own contract."""

    @pytest.mark.parametrize("agent", list(AgentKind))
    def test_out_of_contract_skills_are_refused(self, agent: AgentKind) -> None:
        broker = CapabilityBroker(agent)
        forbidden = ALL_CONTRACT_SKILLS - AGENT_SKILL_CONTRACTS[agent]
        assert forbidden, "every Agent has at least one Skill it may not invoke"
        for name in sorted(forbidden):
            with pytest.raises(CapabilityViolation) as raised:
                broker.invoke_skill(name)
            assert name in str(raised.value)
            assert agent.value in str(raised.value)

    @pytest.mark.parametrize("agent", list(AgentKind))
    def test_unknown_skill_names_are_refused_identically(self, agent: AgentKind) -> None:
        """A name that is not a Skill at all is refused the same way as a real one out of contract.

        Same exception, no hint about whether the name exists: the broker must not be an
        enumeration oracle for what is or is not implemented.
        """
        broker = CapabilityBroker(agent)
        with pytest.raises(CapabilityViolation):
            broker.invoke_skill("definitely_not_a_skill")

    @pytest.mark.parametrize("agent", list(AgentKind))
    def test_out_of_contract_provider_roles_are_refused(self, agent: AgentKind) -> None:
        allowed = AGENT_PROVIDER_CONTRACTS[agent]
        broker = CapabilityBroker(agent, providers=lambda role: pytest.fail("never reached"))
        for role in ProviderRole:
            if role in allowed:
                continue
            with pytest.raises(CapabilityViolation) as raised:
                broker.provider(role)
            assert role.value in str(raised.value)

    def test_four_agents_may_reach_no_provider_at_all(self) -> None:
        """Only `ImplementationAgent` and `QAAgent` may invoke a model at all."""
        for agent in (AgentKind.PMO, AgentKind.GIT, AgentKind.MERGE, AgentKind.CLOSEOUT):
            assert AGENT_PROVIDER_CONTRACTS[agent] == frozenset()
            broker = CapabilityBroker(agent, providers=lambda role: pytest.fail("never reached"))
            for role in ProviderRole:
                with pytest.raises(CapabilityViolation):
                    broker.provider(role)

    def test_in_contract_skill_is_permitted(self) -> None:
        """The boundary refuses the right things without refusing everything."""
        calls: list[str] = []

        def fake(**kwargs: object) -> object:
            calls.append("called")
            return kwargs

        broker = CapabilityBroker(
            AgentKind.PMO,
            skills={"inspect_working_tree": fake},  # type: ignore[dict-item]
        )
        broker.invoke_skill("inspect_working_tree", repository_path="x")
        assert calls == ["called"]
        assert broker.skill_calls == ("inspect_working_tree",)

    def test_agent_rejects_a_broker_bound_to_a_different_agent(self) -> None:
        with pytest.raises(CapabilityViolation):
            PMOAgent(CapabilityBroker(AgentKind.QA))

    def test_provider_without_a_gateway_is_a_wiring_error(self) -> None:
        broker = CapabilityBroker(AgentKind.QA)
        with pytest.raises(CapabilityViolation):
            broker.provider(ProviderRole.QA)


class TestContractDocumentAgreement:
    """The capability tables match `AGENT_CONTRACTS.md`'s own Skill lists."""

    @pytest.mark.parametrize(
        ("agent", "section"),
        [
            (AgentKind.PMO, "## 2. PMOAgent"),
            (AgentKind.IMPLEMENTATION, "## 3. ImplementationAgent"),
            (AgentKind.QA, "## 4. QAAgent"),
            (AgentKind.GIT, "## 5. GitAgent"),
            (AgentKind.MERGE, "## 6. MergeAgent"),
            (AgentKind.CLOSEOUT, "## 7. CloseoutAgent"),
        ],
    )
    def test_skill_set_matches_the_document(self, agent: AgentKind, section: str) -> None:
        text = CONTRACT_DOCUMENT.read_text(encoding="utf-8")
        start = text.index(section)
        end = text.index("\n## ", start + len(section))
        body = text[start:end]
        allowed_line = re.search(r"\*\*Allowed skills(?:/providers)?:\*\*(.+?)\n\n", body, re.S)
        assert allowed_line is not None, f"{section} has no allowed-skills line"
        documented = {
            name
            for name in re.findall(r"`([a-z_]+)`", allowed_line.group(1))
            # Provider class names are backticked in the same list but are not Skills; they are
            # covered by `AGENT_PROVIDER_CONTRACTS` and its own test below.
            if not name.endswith("provider")
        }
        assert documented == set(AGENT_SKILL_CONTRACTS[agent])

    def test_provider_roles_match_the_document(self) -> None:
        text = CONTRACT_DOCUMENT.read_text(encoding="utf-8")
        assert "`ClaudeCLIProvider`" in text and "`CodexCLIProvider`" in text
        assert AGENT_PROVIDER_CONTRACTS[AgentKind.IMPLEMENTATION] == frozenset(
            {ProviderRole.IMPLEMENTATION, ProviderRole.REPAIR}
        )
        assert AGENT_PROVIDER_CONTRACTS[AgentKind.QA] == frozenset({ProviderRole.QA})

    def test_there_are_exactly_six_agents(self) -> None:
        assert len(AgentKind) == 6
        assert set(AGENT_SKILL_CONTRACTS) == set(AgentKind)
        assert set(AGENT_PROVIDER_CONTRACTS) == set(AgentKind)
        assert set(AGENT_CLASSES) == set(AgentKind)

    def test_every_non_provisional_contract_skill_is_bound(self) -> None:
        """Nothing a contract names is silently missing from the production registry.

        The invariant is unchanged since AUTO-003 — the unbound set must equal the provisional set
        — but both sides are now empty (GOV-AUTO-06). Written as an equality rather than
        `unbound == set()` so the invariant, not today's membership, is what is pinned: if a future
        contract legitimately names a Skill before its implementing stage lands, this test keeps
        passing only while that name is *declared* provisional.
        """
        registry = default_skill_registry()
        unbound = {name for name in ALL_CONTRACT_SKILLS if name not in registry}
        assert unbound == set(PROVISIONAL_SKILL_NAMES)

    def test_no_contract_skill_is_unbound_today(self) -> None:
        """Every name any Agent contract mentions resolves in the production registry.

        The concrete GOV-AUTO-06 guarantee, stated separately from the invariant above because the
        invariant would also hold in the broken state it replaced: before this fix, `unbound` and
        `PROVISIONAL_SKILL_NAMES` were both the same eight Git/GitHub Skills, so the equality
        passed while `GitAgent` and `MergeAgent` could not run at all.
        """
        registry = default_skill_registry()
        assert {name for name in ALL_CONTRACT_SKILLS if name not in registry} == set()
        assert PROVISIONAL_SKILL_NAMES == frozenset()


class TestStructuralIsolation:
    """No Agent module can reach a Skill or Provider except through its broker."""

    @pytest.mark.parametrize("module_name", sorted(set(AGENT_MODULES.values())))
    def test_agent_modules_import_no_skill_family(self, module_name: str) -> None:
        tree = ast.parse((PACKAGE_ROOT / "agents" / f"{module_name}.py").read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("agentos_workflow.skills."), (
                    f"{module_name}.py imports the Skill family {node.module!r} directly, "
                    "bypassing its capability broker"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("agentos_workflow.skills.")

    @pytest.mark.parametrize("module_name", sorted(set(AGENT_MODULES.values())))
    def test_agent_modules_never_select_a_provider_themselves(self, module_name: str) -> None:
        """`select_live_provider` is the Orchestrator's; an Agent receives a gateway."""
        source = (PACKAGE_ROOT / "agents" / f"{module_name}.py").read_text("utf-8")
        assert "select_live_provider" not in source
        assert "MockProvider" not in source

    @pytest.mark.parametrize("module_name", sorted(set(AGENT_MODULES.values())))
    def test_agent_modules_run_no_subprocess(self, module_name: str) -> None:
        """`AGENT_CONTRACTS.md` §1: an Agent has no direct subprocess, filesystem, or network
        access. Every side effect goes through a Skill or Provider."""
        source = (PACKAGE_ROOT / "agents" / f"{module_name}.py").read_text("utf-8")
        for forbidden in ("subprocess", "os.system", "socket", "urllib", "requests"):
            assert forbidden not in source, f"{module_name}.py names {forbidden!r}"

    def test_no_agent_result_carries_a_workflow_state(self) -> None:
        """`AGENT_CONTRACTS.md` §1: the Orchestrator decides the transition, not the Agent.

        Checked over the package source rather than one result object, because the property is
        "no Agent ever returns a state", which a single instance cannot demonstrate.
        """
        for module_name in {*AGENT_MODULES.values(), "__init__"}:
            source = (PACKAGE_ROOT / "agents" / f"{module_name}.py").read_text("utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "WorkflowState" not in (node.module or ""), module_name
                    for alias in node.names:
                        assert "WorkflowState" not in alias.name, module_name

    def test_merge_agent_has_no_admin_bypass_path(self) -> None:
        """`MACHINE_GATES.md` §5 / `SECURITY_MODEL.md` §4: never `--admin`, never a bypass.

        Checked over the module's *executable* source with docstrings stripped. Checking the raw
        file would be a worse test, not a stricter one: it would fail on the docstring that
        explains the rule, so the only way to keep it green would be to stop documenting the
        guarantee — which is exactly backwards.
        """
        code = _executable_source(PACKAGE_ROOT / "agents" / "merge.py").lower()
        for forbidden in ("admin", "bypass", "force", "--no-verify"):
            assert forbidden not in code, f"merge.py's executable code names {forbidden!r}"

    def test_no_agent_module_names_a_force_or_history_rewriting_flag(self) -> None:
        """`SECURITY_MODEL.md` §2's forbidden Git operations stay unreachable from the Agent
        layer."""
        for module_name in sorted(set(AGENT_MODULES.values())):
            code = _executable_source(PACKAGE_ROOT / "agents" / f"{module_name}.py").lower()
            for forbidden in ("--force", "-f'", "reset", "rebase", "--amend", "-d'"):
                assert forbidden not in code, f"{module_name}.py's code names {forbidden!r}"

    def test_closeout_deletion_requires_a_merge_confirmation_parameter(self) -> None:
        """The token is required and has no default, so "delete without confirming" cannot be
        written."""
        tree = ast.parse((PACKAGE_ROOT / "agents" / "closeout.py").read_text("utf-8"))
        close_out = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "close_out"
        )
        names = [argument.arg for argument in close_out.args.kwonlyargs]
        assert "merge_confirmation" in names
        assert close_out.args.kw_defaults[names.index("merge_confirmation")] is None


class TestGitHubSkillsAreBoundInTheProductionRegistry:
    """GOV-AUTO-06 — the eight delivered Git/GitHub Skills are reachable by default.

    AUTO-006 delivered `skills/git_github.py` but nothing updated `_DEFAULT_SKILL_BINDINGS` or
    `PROVISIONAL_SKILL_NAMES`, so the production registry kept answering "not yet implemented" for
    all eight and `GitAgent`/`MergeAgent` could not invoke their own contracted Skills. The
    end-to-end dry run had to bind all eight by hand, which is what hid the gap: the only test that
    exercised these Agents supplied its own registry.
    """

    DELIVERED_GITHUB_SKILLS = frozenset(
        {
            "create_commit",
            "push_stage_branch",
            "create_pull_request",
            "read_pull_request_state",
            "verify_head_sha",
            "read_required_checks",
            "enable_automatic_squash_merge",
            "verify_merge_completion",
        }
    )

    def test_all_eight_delivered_skills_are_in_the_default_registry(self) -> None:
        registry = default_skill_registry()
        missing = sorted(self.DELIVERED_GITHUB_SKILLS - set(registry))
        assert missing == [], f"delivered but unbound: {missing}"

    def test_the_bound_implementations_are_the_delivered_ones(self) -> None:
        """Bound to `skills/git_github.py`, not to a stub or a look-alike.

        A registry entry pointing at something *named* correctly would satisfy presence while still
        being wrong, so identity is asserted against the delivering module itself.
        """
        registry = default_skill_registry()
        for name in sorted(self.DELIVERED_GITHUB_SKILLS):
            assert registry[name] is getattr(git_github_skills, name), name

    def test_none_of_the_eight_is_classified_provisional(self) -> None:
        assert self.DELIVERED_GITHUB_SKILLS & PROVISIONAL_SKILL_NAMES == frozenset()
        assert PROVISIONAL_SKILL_NAMES == frozenset()

    @pytest.mark.parametrize("agent", [AgentKind.GIT, AgentKind.MERGE])
    def test_git_and_merge_resolve_every_contracted_skill_via_the_default_registry(
        self, agent: AgentKind
    ) -> None:
        """The capability path that was broken: contract -> broker -> production registry.

        Uses `CapabilityBroker` with `default_skill_registry()` and no test-supplied bindings,
        which is precisely what no test did before.
        """
        broker = CapabilityBroker(agent, skills=default_skill_registry())
        for name in sorted(AGENT_SKILL_CONTRACTS[agent]):
            assert broker.permits_skill(name), name
            assert name in default_skill_registry(), name

    def test_binding_widened_no_agent_reach(self) -> None:
        """Presence in the registry grants nothing; the contract still decides.

        The real risk in this change is over-granting, so this asserts the negative directly: the
        four Agents whose contracts name no Git/GitHub Skill must still be refused all eight, and
        `GIT`/`MERGE` must be refused the ones their own contracts omit.
        """
        for agent in AgentKind:
            permitted = AGENT_SKILL_CONTRACTS[agent]
            broker = CapabilityBroker(agent, skills=default_skill_registry())
            for name in sorted(self.DELIVERED_GITHUB_SKILLS):
                if name in permitted:
                    continue
                assert not broker.permits_skill(name), (agent, name)
                with pytest.raises(CapabilityViolation):
                    broker.invoke_skill(name)

    def test_github_skills_reach_only_git_and_merge(self) -> None:
        """No Agent outside GIT/MERGE has any Git/GitHub Skill in its contract."""
        for agent in AgentKind:
            if agent in (AgentKind.GIT, AgentKind.MERGE):
                continue
            assert AGENT_SKILL_CONTRACTS[agent] & self.DELIVERED_GITHUB_SKILLS == frozenset(), agent

    def test_no_manual_registration_is_required_for_this_capability_path(self) -> None:
        """A broker built from the unmodified production registry needs no augmentation.

        Expressed as an identity check on the mapping actually used: if any of the eight had to be
        patched in, the broker's registry would differ from `default_skill_registry()`.
        """
        production = dict(default_skill_registry())
        for agent in (AgentKind.GIT, AgentKind.MERGE):
            required = AGENT_SKILL_CONTRACTS[agent]
            assert required <= set(production), sorted(required - set(production))
        # And the dry run's hand-registration is now redundant rather than load-bearing.
        assert self.DELIVERED_GITHUB_SKILLS <= set(production)

    @staticmethod
    def _thinned_broker() -> CapabilityBroker:
        """A `GIT` broker whose registry omits one Skill the GIT contract permits."""
        thinned = {
            name: binding
            for name, binding in default_skill_registry().items()
            if name != "create_commit"
        }
        return CapabilityBroker(AgentKind.GIT, skills=thinned)

    def test_a_permitted_but_unbound_skill_returns_a_typed_failure_not_a_raise(self) -> None:
        """A missing binding degrades to typed failure; only an out-of-contract name raises.

        Guards the mechanism GOV-AUTO-06 deliberately kept rather than deleted. "Not built here" is
        a deployment state a machine gate can branch on; "not permitted" is a programming error.
        Simulated with a thinned registry, since no real name is unbound any more.
        """
        result = self._thinned_broker().invoke_skill(
            "create_commit", repository_path=Path("/nonexistent")
        )
        assert not result.ok
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION
        assert result.error.retry_classification is RetryClassification.NON_RETRYABLE
        # With nothing classified provisional, an absent binding is a registry gap, not a
        # not-yet-built Skill — and the message says so rather than blaming an unshipped stage.
        assert result.error.detail == "skill 'create_commit' is not bound in this registry"

    def test_the_provisional_message_no_longer_names_a_shipped_stage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The provisional branch reports "not yet implemented" without naming AUTO-006.

        Reaching that branch requires a name to actually be classified provisional, so this
        monkeypatches the set — which is also the only way to prove the branch still works now that
        the set is legitimately empty. Pinning the *absence* of "AUTO-006" is the point: naming one
        stage is what let this message keep asserting AUTO-006 was pending for the entire period
        after AUTO-006 had shipped.
        """
        monkeypatch.setattr(
            "agentos_workflow.agents.PROVISIONAL_SKILL_NAMES", frozenset({"create_commit"})
        )
        result = self._thinned_broker().invoke_skill(
            "create_commit", repository_path=Path("/nonexistent")
        )
        assert result.error is not None
        assert result.error.detail == "skill 'create_commit' is not yet implemented"
        assert "AUTO-006" not in result.error.detail
