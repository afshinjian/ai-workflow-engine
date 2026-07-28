"""Session isolation and the `MockProvider` structural exclusion
(`MODEL_PROVIDER_CONTRACTS.md` §4, §5; `SECURITY_MODEL.md` §3; `MVP_SCOPE.md` §3).

Isolation is a security boundary, not only a correctness one: an implementation session that has
been manipulated — say by a prompt-injection attempt planted in target-repository content — must
not be able to reach the session that judges its work. These tests prove the boundary holds by
construction rather than by convention, so they assert on structure (types, registries, imports,
object identity) wherever asserting on behavior alone would leave a future edit free to reopen the
path.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agentos_workflow import providers
from agentos_workflow.providers import (
    ClaudeCLIProvider,
    CLIProvider,
    CodexCLIProvider,
    Provider,
    ProviderRole,
    live_provider_roles,
    select_live_provider,
)
from agentos_workflow.providers.base import ProviderKind
from agentos_workflow.providers.mock import MockProvider
from agentos_workflow.tests.test_providers_base import invocation, stub_cli
from agentos_workflow.tests.test_providers_cli import valid_config

LIVE_MODULES = ("__init__", "base", "claude_cli", "codex_cli")


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    directory = tmp_path / "repo"
    directory.mkdir()
    return directory


@pytest.fixture
def sessions(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


def providers_source(module: str) -> str:
    return (Path(providers.__file__).parent / f"{module}.py").read_text()


def imported_names(module: str) -> set[str]:
    """Every module name imported by `module`, however it is spelled."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(providers_source(module))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


# ---------------------------------------------------------------------------------------------
# Session isolation (§5)
# ---------------------------------------------------------------------------------------------


class TestSessionIsolation:
    def test_two_providers_in_one_workflow_get_disjoint_session_directories(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = "sys.stdin.read()\nprint(json.dumps({'verdict': 'pass', 'summary': 'ok'}))"
        executable = stub_cli(workdir.parent, body)
        implementation = ClaudeCLIProvider(executable=executable, timeout_seconds=30)
        qa = CodexCLIProvider(executable=executable, timeout_seconds=30)

        implementation.invoke(
            invocation(workdir, sessions, workflow_id="wf-1", invocation_id="inv-1")
        )
        qa.invoke(
            invocation(
                workdir, sessions, role=ProviderRole.QA, workflow_id="wf-1", invocation_id="inv-1"
            )
        )

        created = sorted(p.relative_to(sessions).as_posix() for p in sessions.rglob("inv-1"))
        assert created == ["wf-1/claude_cli/inv-1", "wf-1/codex_cli/inv-1"]

    def test_two_invocations_of_one_provider_get_disjoint_directories(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = "sys.stdin.read()\nprint(json.dumps({'verdict': 'pass', 'summary': 'ok'}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)

        provider.invoke(invocation(workdir, sessions, invocation_id="inv-1"))
        provider.invoke(invocation(workdir, sessions, invocation_id="inv-2"))

        created = sorted(p.name for p in (sessions / "wf-1" / "claude_cli").iterdir())
        assert created == ["inv-1", "inv-2"]

    def test_a_reused_invocation_id_is_refused_rather_than_shared(
        self, workdir: Path, sessions: Path
    ) -> None:
        body = "sys.stdin.read()\nprint(json.dumps({'verdict': 'pass', 'summary': 'ok'}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)

        assert provider.invoke(invocation(workdir, sessions, invocation_id="dup")).ok
        second = provider.invoke(invocation(workdir, sessions, invocation_id="dup"))

        assert not second.ok
        assert second.error is not None
        assert "already exists" in second.error.detail

    def test_session_directories_are_not_world_readable(
        self, workdir: Path, sessions: Path
    ) -> None:
        # The CLI's TMPDIR points here, so scratch from an implementation or QA session must not
        # be readable by another local user on a shared host.
        body = "sys.stdin.read()\nprint(json.dumps({'verdict': 'pass', 'summary': 'ok'}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)
        provider.invoke(invocation(workdir, sessions, invocation_id="inv-1"))

        created = sessions / "wf-1" / "claude_cli" / "inv-1"
        assert created.stat().st_mode & 0o077 == 0

    def test_no_object_is_shared_between_two_provider_instances(self, tmp_path: Path) -> None:
        config = valid_config(tmp_path)
        implementation = select_live_provider(ProviderRole.IMPLEMENTATION, config)
        qa = select_live_provider(ProviderRole.QA, config)

        assert implementation is not qa
        shared = {id(v) for v in vars(implementation).values()} & {id(v) for v in vars(qa).values()}
        # The only values that may compare equal are immutable configuration scalars; no mutable
        # object may be reachable from both.
        for value in vars(implementation).values():
            if id(value) in shared:
                assert isinstance(value, (str, int, tuple, Path, type(None)))

    def test_providers_hold_no_cross_invocation_state(self, workdir: Path, sessions: Path) -> None:
        body = "sys.stdin.read()\nprint(json.dumps({'verdict': 'pass', 'summary': 'ok'}))"
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)

        before = dict(vars(provider))
        provider.invoke(invocation(workdir, sessions, invocation_id="inv-1"))
        after = dict(vars(provider))

        assert before == after

    def test_one_providers_output_never_reaches_the_others_process(
        self, workdir: Path, sessions: Path
    ) -> None:
        # §5: neither provider's process receives the other's raw output. Only artifacts the
        # Orchestrator assembles cross the boundary — here, nothing but the caller's own prompt.
        implementation_body = (
            "sys.stdin.read()\n"
            "print(json.dumps({'verdict': 'pass', 'summary': 'IMPLEMENTATION-SECRET-REASONING'}))"
        )
        qa_body = (
            "received = sys.stdin.read()\n"
            "print(json.dumps({'verdict': 'pass', 'summary': received}))"
        )
        implementation = ClaudeCLIProvider(
            executable=stub_cli(workdir.parent, implementation_body, name="impl"),
            timeout_seconds=30,
        )
        qa = CodexCLIProvider(
            executable=stub_cli(workdir.parent, qa_body, name="qa"), timeout_seconds=30
        )

        implementation_report = implementation.invoke(
            invocation(workdir, sessions, invocation_id="inv-1")
        ).unwrap()
        assert implementation_report.summary == "IMPLEMENTATION-SECRET-REASONING"

        qa_report = qa.invoke(
            invocation(
                workdir,
                sessions,
                role=ProviderRole.QA,
                prompt="review this diff",
                invocation_id="inv-2",
            )
        ).unwrap()

        assert qa_report.summary == "review this diff"
        assert "IMPLEMENTATION-SECRET-REASONING" not in qa_report.summary

    def test_each_invocation_is_a_separate_subprocess(self, workdir: Path, sessions: Path) -> None:
        body = (
            "sys.stdin.read()\n"
            "print(json.dumps({'verdict': 'pass', 'summary': str(os.getpid())}))"
        )
        provider = ClaudeCLIProvider(executable=stub_cli(workdir.parent, body), timeout_seconds=30)

        first = provider.invoke(invocation(workdir, sessions, invocation_id="inv-1")).unwrap()
        second = provider.invoke(invocation(workdir, sessions, invocation_id="inv-2")).unwrap()

        assert first.summary != second.summary


# ---------------------------------------------------------------------------------------------
# MockProvider structural exclusion (§4, MVP_SCOPE.md §3)
# ---------------------------------------------------------------------------------------------


class TestMockProviderIsStructurallyExcluded:
    def test_mock_is_not_a_cli_provider(self) -> None:
        # Live selection is typed to return a `CLIProvider`, so this makes returning a mock from
        # it a type error rather than a policy violation.
        assert issubclass(MockProvider, Provider)
        assert not issubclass(MockProvider, CLIProvider)

    def test_no_role_selects_the_mock(self, tmp_path: Path) -> None:
        config = valid_config(tmp_path)
        for role in live_provider_roles():
            selected = select_live_provider(role, config)
            assert isinstance(selected, CLIProvider)
            assert not isinstance(selected, MockProvider)
            assert selected.kind is not ProviderKind.MOCK

    def test_the_live_registry_contains_only_cli_providers(self, tmp_path: Path) -> None:
        config = valid_config(tmp_path)
        kinds = {select_live_provider(role, config).kind for role in ProviderRole}
        assert kinds == {ProviderKind.CLAUDE_CLI, ProviderKind.CODEX_CLI}

    @pytest.mark.parametrize("module", LIVE_MODULES)
    def test_no_live_module_imports_the_mock(self, module: str) -> None:
        # The strongest form of the exclusion: no live code path can even name `MockProvider`.
        assert not any("mock" in name.lower() for name in imported_names(module))

    @pytest.mark.parametrize("module", LIVE_MODULES)
    def test_no_live_module_references_the_mock_by_name(self, module: str) -> None:
        source = providers_source(module)
        code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
        # Docstrings legitimately discuss the exclusion; executable code must not name the class.
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "MockProvider"
            if isinstance(node, ast.Attribute):
                assert node.attr != "MockProvider"

    def test_no_configuration_value_can_request_a_mock(self, tmp_path: Path) -> None:
        # There is no provider-selection field in the schema at all: the CLI executables are named
        # directly, so "provider: mock" is not a configuration a target repository can express.
        config = valid_config(tmp_path)
        assert not any(
            "mock" in str(getattr(config, field)).lower() for field in type(config).model_fields
        )

    def test_config_json_round_trip_has_no_provider_selector(self, tmp_path: Path) -> None:
        raw = json.loads(valid_config(tmp_path).model_dump_json())
        assert "provider" not in raw
        assert {"claude_cli_executable", "codex_cli_executable"} <= set(raw)
