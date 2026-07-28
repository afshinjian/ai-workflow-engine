"""Tests for `MockProvider` (`MODEL_PROVIDER_CONTRACTS.md` §4) — canned reports and, above all,
**drop-in equivalence** with the CLI providers.

Drop-in equivalence is the property the whole test strategy rests on (`TEST_STRATEGY.md`): if a
caller typed against `Provider` can tell a mock from a real adapter, then every Orchestrator test
driven by a mock is testing a different code path than production takes, and the coverage is an
illusion. These tests therefore drive the mock and a CLI adapter through the *same* caller and
assert the caller cannot distinguish them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos_workflow.providers import ProviderRole, ProviderVerdict
from agentos_workflow.providers.base import (
    Provider,
    ProviderFailureKind,
    ProviderInvocation,
    ProviderKind,
    ProviderResult,
    provider_failure,
    provider_success,
)
from agentos_workflow.providers.claude_cli import ClaudeCLIProvider
from agentos_workflow.providers.mock import MockProvider, canned_report
from agentos_workflow.skills import RetryClassification
from agentos_workflow.tests.test_providers_base import echo_report_cli, invocation


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    directory = tmp_path / "repo"
    directory.mkdir()
    return directory


@pytest.fixture
def sessions(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


def drive(provider: Provider, invocation_: ProviderInvocation) -> ProviderResult:
    """A caller that knows only the abstract interface — the shape production code has."""
    return provider.invoke(invocation_)


class TestCannedReports:
    def test_default_result_is_a_passing_implementation_report(
        self, workdir: Path, sessions: Path
    ) -> None:
        report = MockProvider().invoke(invocation(workdir, sessions)).unwrap()
        assert report.verdict is ProviderVerdict.PASS
        assert report.provider is ProviderKind.MOCK

    def test_results_are_returned_in_order_then_the_last_repeats(
        self, workdir: Path, sessions: Path
    ) -> None:
        # Queue fail-then-pass to drive exactly one repair cycle; the tail repeats so a loop
        # driven past the queue's length keeps getting a defined answer instead of an IndexError.
        provider = MockProvider(
            [
                provider_success(canned_report(role=ProviderRole.QA, verdict=ProviderVerdict.FAIL)),
                provider_success(canned_report(role=ProviderRole.QA, verdict=ProviderVerdict.PASS)),
            ]
        )
        verdicts = [
            provider.invoke(invocation(workdir, sessions)).unwrap().verdict for _ in range(4)
        ]
        assert verdicts == [
            ProviderVerdict.FAIL,
            ProviderVerdict.PASS,
            ProviderVerdict.PASS,
            ProviderVerdict.PASS,
        ]

    def test_failures_can_be_canned_including_a_typed_timeout(
        self, workdir: Path, sessions: Path
    ) -> None:
        provider = MockProvider(
            [
                provider_failure(
                    ProviderKind.MOCK,
                    ProviderFailureKind.TIMEOUT,
                    "canned timeout",
                    retry_classification=RetryClassification.POSSIBLE_SIDE_EFFECT,
                )
            ]
        )
        result = provider.invoke(invocation(workdir, sessions))

        assert not result.ok
        assert result.error is not None
        assert result.error.kind is ProviderFailureKind.TIMEOUT
        assert result.error.retry_classification is RetryClassification.POSSIBLE_SIDE_EFFECT

    def test_canned_report_cannot_impersonate_a_real_cli(self) -> None:
        # A mocked run must never be mistakable for a real one in an audit record.
        assert canned_report(role=ProviderRole.QA).provider is ProviderKind.MOCK

    def test_invocations_are_recorded_for_assertions(self, workdir: Path, sessions: Path) -> None:
        provider = MockProvider()
        first = invocation(workdir, sessions, invocation_id="inv-1")
        second = invocation(workdir, sessions, invocation_id="inv-2")
        provider.invoke(first)
        provider.invoke(second)

        assert provider.invocations == (first, second)

    def test_no_process_is_ever_spawned(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("MockProvider must never spawn a process")

        monkeypatch.setattr(subprocess, "run", explode)
        MockProvider().invoke(invocation(workdir, sessions))

    def test_no_session_directory_is_created(self, workdir: Path, sessions: Path) -> None:
        MockProvider().invoke(invocation(workdir, sessions))
        assert not sessions.exists()


class TestDropInEquivalence:
    def test_both_satisfy_the_same_abstract_interface(self) -> None:
        assert issubclass(MockProvider, Provider)
        assert issubclass(ClaudeCLIProvider, Provider)

    def test_one_caller_drives_both_identically(self, workdir: Path, sessions: Path) -> None:
        payload = {
            "verdict": "pass",
            "summary": "done",
            "files_changed": ["a.py"],
            "recommended_commit_message": "feat: x",
        }
        real: Provider = ClaudeCLIProvider(
            executable=echo_report_cli(workdir.parent, payload), timeout_seconds=30
        )
        mock: Provider = MockProvider(
            [
                provider_success(
                    canned_report(
                        role=ProviderRole.IMPLEMENTATION,
                        summary="done",
                        files_changed=["a.py"],
                        recommended_commit_message="feat: x",
                    )
                )
            ]
        )

        real_result = drive(real, invocation(workdir, sessions))
        mock_result = drive(mock, invocation(workdir, sessions, invocation_id="inv-2"))

        # Every field the caller reads is identical; only `provider` and the execution record —
        # the two things that must stay honest about what actually ran — differ.
        for result in (real_result, mock_result):
            assert result.ok
        assert real_result.unwrap().verdict == mock_result.unwrap().verdict
        assert real_result.unwrap().summary == mock_result.unwrap().summary
        assert real_result.unwrap().files_changed == mock_result.unwrap().files_changed
        assert real_result.unwrap().role == mock_result.unwrap().role
        assert (
            real_result.unwrap().recommended_commit_message
            == mock_result.unwrap().recommended_commit_message
        )
        assert real_result.unwrap().provider is not mock_result.unwrap().provider

    def test_failure_results_have_the_same_shape(self, workdir: Path, sessions: Path) -> None:
        real: Provider = ClaudeCLIProvider(
            executable=workdir / "missing-executable", timeout_seconds=30
        )
        mock: Provider = MockProvider(
            [
                provider_failure(
                    ProviderKind.MOCK,
                    ProviderFailureKind.SPAWN_FAILED,
                    "canned spawn failure",
                    retry_classification=RetryClassification.PROVEN_PRE_SIDE_EFFECT,
                )
            ]
        )

        real_result = drive(real, invocation(workdir, sessions))
        mock_result = drive(mock, invocation(workdir, sessions))

        assert real_result.ok is mock_result.ok is False
        assert real_result.error is not None and mock_result.error is not None
        assert real_result.error.kind is mock_result.error.kind
        assert real_result.error.retry_classification is mock_result.error.retry_classification

    def test_mock_never_raises_either(self, workdir: Path, sessions: Path) -> None:
        result = MockProvider([]).invoke(invocation(workdir, sessions))
        assert isinstance(result, ProviderResult)

    def test_mock_tolerates_an_invocation_a_cli_provider_would_refuse(
        self, workdir: Path, sessions: Path
    ) -> None:
        # The mock deliberately does not re-implement validation: a test that wants to exercise
        # the refusal path must use a real adapter, so the two can never disagree about what is
        # refused while both claiming to have checked.
        bad = invocation(workdir, sessions, invocation_id="../escape")
        assert MockProvider().invoke(bad).ok
        assert not ClaudeCLIProvider(executable=workdir / "x", timeout_seconds=1).invoke(bad).ok


class TestNoConfigurationPath:
    def test_mock_has_no_from_config_constructor(self) -> None:
        # A MockProvider cannot be built from a target repository's configuration at all: there is
        # no field, and no value of any field, that produces one (`MVP_SCOPE.md` §3).
        assert not hasattr(MockProvider, "from_config")
        assert hasattr(ClaudeCLIProvider, "from_config")

    def test_mock_reads_no_configuration_and_no_environment(
        self, workdir: Path, sessions: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANY_SECRET", "super-secret-value")
        report = MockProvider().invoke(invocation(workdir, sessions)).unwrap()

        # No process ran, so there is no execution record to carry environment-derived content,
        # and nothing from the ambient environment can appear in a canned report.
        assert report.execution is None
        assert "super-secret-value" not in json.dumps(report.summary)
        assert report.summary == "canned report"
