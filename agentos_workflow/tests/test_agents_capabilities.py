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
        """Only the eight AUTO-006 Skills are unbound; nothing else is silently missing."""
        registry = default_skill_registry()
        unbound = {name for name in ALL_CONTRACT_SKILLS if name not in registry}
        assert unbound == set(PROVISIONAL_SKILL_NAMES)


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
