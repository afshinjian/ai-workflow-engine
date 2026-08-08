"""AUTO-016 sections 16 and 18: verification execution and the machine-result grammar.

Two halves of one milestone, tested the same way the rest of this package is tested: with real
things. Every verification test runs a **real** subprocess -- a small deterministic script the
test writes, never `claude` and never `codex` -- against a real `git init` repository under
`tmp_path`, a real run lock and a real durable state store, so a transcript assertion is an
assertion about bytes on disk rather than about a mock's call list. Every parser test parses text
in exactly the grammar `prompts.py` tells a provider to emit.

The three prototype defects this milestone corrects each have their own named class:
`TestP2MissingResultFieldIsTypedRejection` (never a `KeyError`),
`TestP7GovernanceGateUsesMachineReadableOutput` (structured results, never a scraped table) and
`TestP8FullVerificationOutputPersisted` (the complete output on disk, not an 800-character tail).

The governance-gate tests feed the parser documents rendered by the engine's **own** reporting
function from its **own** `CheckResult` model, so the gate is proved against the shape
`workflowctl` actually emits rather than against a shape this suite invented.
"""

import ast
import json
import os
import stat
import subprocess
import sys
import textwrap
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from ai_workflow_engine.milestone_runner.config import VerificationCommandSettings
from ai_workflow_engine.milestone_runner.git_inspect import derive_repository_identity
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    FindingSeverity,
    FindingStatus,
    ProviderRole,
    ProviderRunRecord,
    ReviewVerdict,
    VerificationResult,
)
from ai_workflow_engine.milestone_runner.prompts import RESULT_SENTINELS
from ai_workflow_engine.milestone_runner.providers.base import ProviderInvoker, ProviderRequest
from ai_workflow_engine.milestone_runner.results import (
    ALL_SENTINELS,
    MAX_RESULT_BLOCK_CHARS,
    ClosureResult,
    CorrectionResult,
    MachineResultGrammar,
    MalformedResult,
    MilestoneReportStatus,
    MilestoneResult,
    ResultTranscripts,
    ReviewResult,
    extract_result_block,
    parse_closure_result,
    parse_correction_result,
    parse_milestone_result,
    parse_review_result,
)
from ai_workflow_engine.milestone_runner.state import RunStateStore
from ai_workflow_engine.milestone_runner.verification import (
    GOVERNANCE_GIT_CHECK,
    REQUIRED_GOVERNANCE_CHECKS,
    TOLERATED_GIT_FINDING_CODES,
    UNCONDITIONAL_GOVERNANCE_CHECKS,
    CommandOutcome,
    GovernanceCheckResult,
    GovernanceCheckStatus,
    GovernanceContradiction,
    VerificationError,
    VerificationExecutor,
    VerificationOutcome,
    build_verification_environment,
    evaluate_governance_gate,
    parse_governance_check_document,
    run_bounded_command,
)
from ai_workflow_engine.reporting.json_report import render_json
from ai_workflow_engine.result import CheckResult, Status
from ai_workflow_engine.result import Finding as EngineFinding

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner"
VERIFICATION_SOURCE = PACKAGE_ROOT / "verification.py"
RESULTS_SOURCE = PACKAGE_ROOT / "results.py"

#: The same disposable repository the M03/M04 suites pin, so all of them address one artifact root.
DEMO_REMOTE = "https://github.com/example/demo-repo.git"
DEMO_IDENTITY = derive_repository_identity(DEMO_REMOTE)
DEMO_RUN_ID = "auto016-20260805T213855Z-7fea75fc"

FAKE_PROVIDER = "fake-provider"


# --------------------------------------------------------------------------------------
# Real repository, real artifact root, real lock, real executor
# --------------------------------------------------------------------------------------


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    repository = tmp_path / "worktree"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "Milestone Runner Tests")
    git(repository, "remote", "add", "origin", DEMO_REMOTE)
    (repository / "kept.txt").write_text("kept\n", encoding="utf-8")
    git(repository, "add", "kept.txt")
    git(repository, "commit", "-m", "initial")
    return repository


@pytest.fixture
def store(isolated_home: Path, worktree: Path) -> RunStateStore:
    return RunStateStore.pin(
        repository_id=DEMO_IDENTITY, run_id=DEMO_RUN_ID, repository_root=worktree
    )


@pytest.fixture
def held_lock(store: RunStateStore) -> Iterator[RunLock]:
    lock = RunLock(
        run_id=store.run_id,
        repository_identity=store.repository_id,
        artifact_root=store.artifact_root,
    )
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


@pytest.fixture
def environment() -> dict[str, str]:
    """A minimal, explicit environment. Nothing is inherited that is not named here."""
    return {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp")}


@pytest.fixture
def executor(
    store: RunStateStore, held_lock: RunLock, worktree: Path, environment: dict[str, str]
) -> VerificationExecutor:
    return VerificationExecutor(
        store=store, lock=held_lock, repository_root=worktree, environment=environment
    )


def python_command(source: str) -> list[str]:
    """A real, deterministic command: this interpreter running one inline program.

    Single-line only, because `models.VerificationResult` validates every argument as a bounded
    single-line scalar -- a command a run record cannot hold is not a command this executor may be
    asked to run. Multi-line programs go through :func:`python_script`.
    """
    return [sys.executable, "-c", source]


@pytest.fixture
def python_script(tmp_path: Path) -> Callable[[str], list[str]]:
    """Write a real multi-line program to a file and return the argv that runs it."""
    counter = {"n": 0}

    def make(source: str) -> list[str]:
        counter["n"] += 1
        script = tmp_path / f"program-{counter['n']}.py"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        return [sys.executable, str(script)]

    return make


def code_string_constants(source: Path) -> list[str]:
    """Every string literal in `source` that is not a docstring.

    A module docstring quoting the defect it corrects -- "truncated to a tail", "a forced
    `LC_ALL=C`" -- is prose about the old behaviour, not the behaviour. The structural assertions
    below are about what the code operates on, so the prose is excluded.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def transcript_text(store: RunStateStore, relative_path: str) -> str:
    return (store.run_directory / relative_path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Section 18 -- the grammar
# --------------------------------------------------------------------------------------


MILESTONE_BODY = """\
milestone: AUTO-016-M05
status: COMPLETE
changed_paths:
  - src/ai_workflow_engine/milestone_runner/results.py
verification:
  - command: pytest -q tests/test_milestone_runner_results.py
    result: PASS
blockers: []
"""

CORRECTION_BODY = """\
status: COMPLETE
findings_addressed:
  - id: F-1
    resolution: The uncaught KeyError is now a typed rejection.
changed_paths:
  - src/ai_workflow_engine/milestone_runner/results.py
verification:
  - command: pytest -q
    result: PASS
"""

REVIEW_BODY = """\
verdict: BLOCKED
blockers:
  - id: R-1
    severity: CRITICAL
    title: The parser reads a field before validating it
    summary: parse_milestone_result indexes the mapping before the model runs.
deferred:
  - id: R-2
    severity: LOW
    title: A docstring is stale
    summary: The module docstring names a section that moved.
"""

CLOSURE_BODY = """\
findings:
  - id: R-1
    status: CLOSED
    reason: The parser now validates the whole mapping first.
"""

BODY_BY_ROLE: dict[ProviderRole, str] = {
    ProviderRole.IMPLEMENTATION: MILESTONE_BODY,
    ProviderRole.CORRECTION: CORRECTION_BODY,
    ProviderRole.REVIEW: REVIEW_BODY,
    ProviderRole.CLOSURE: CLOSURE_BODY,
}


def block(role: ProviderRole, body: str | None = None) -> str:
    """One well-formed result block for `role`, exactly as `prompts.py` asks for it."""
    sentinels = RESULT_SENTINELS[role]
    return f"{sentinels.start}\n{body if body is not None else BODY_BY_ROLE[role]}{sentinels.end}\n"


def parse_for_role(role: ProviderRole, text: str) -> Any:
    """Drive the parser that owns `role`, so one grammar test covers all four."""
    if role is ProviderRole.IMPLEMENTATION:
        return parse_milestone_result(text)
    if role is ProviderRole.CORRECTION:
        return parse_correction_result(text)
    if role is ProviderRole.REVIEW:
        return parse_review_result(text, max_blockers=3)
    return parse_closure_result(text, open_finding_ids=["R-1"])


class TestResultGrammarPerRole:
    """Section 18: four roles, four distinct sentinel pairs, four typed results."""

    def test_the_four_sentinel_pairs_are_the_contract_s(self) -> None:
        assert {role: (pair.start, pair.end) for role, pair in RESULT_SENTINELS.items()} == {
            ProviderRole.IMPLEMENTATION: (
                "AUTO016_MILESTONE_RESULT",
                "END_AUTO016_MILESTONE_RESULT",
            ),
            ProviderRole.CORRECTION: (
                "AUTO016_CORRECTION_RESULT",
                "END_AUTO016_CORRECTION_RESULT",
            ),
            ProviderRole.REVIEW: ("AUTO016_REVIEW_RESULT", "END_AUTO016_REVIEW_RESULT"),
            ProviderRole.CLOSURE: ("AUTO016_CLOSURE_RESULT", "END_AUTO016_CLOSURE_RESULT"),
        }

    def test_the_grammar_reads_its_sentinels_from_the_prompt_module(self) -> None:
        """One definition, so the block a provider is asked for is the block that is parsed."""
        for role, pair in RESULT_SENTINELS.items():
            grammar = MachineResultGrammar.for_role(role)
            assert (grammar.start, grammar.end) == (pair.start, pair.end)
        assert ALL_SENTINELS == {
            value for pair in RESULT_SENTINELS.values() for value in (pair.start, pair.end)
        }

    @pytest.mark.parametrize("role", list(ProviderRole))
    def test_each_role_s_own_block_parses(self, role: ProviderRole) -> None:
        assert parse_for_role(role, block(role)) is not None

    def test_a_milestone_result_carries_its_typed_fields(self) -> None:
        result = parse_milestone_result(block(ProviderRole.IMPLEMENTATION))
        assert isinstance(result, MilestoneResult)
        assert result.milestone == "AUTO-016-M05"
        assert result.status is MilestoneReportStatus.COMPLETE
        assert result.changed_paths == ["src/ai_workflow_engine/milestone_runner/results.py"]
        assert result.verification[0].command.startswith("pytest")

    def test_a_correction_result_carries_its_typed_fields(self) -> None:
        result = parse_correction_result(block(ProviderRole.CORRECTION))
        assert isinstance(result, CorrectionResult)
        assert [entry.id for entry in result.findings_addressed] == ["F-1"]

    def test_a_review_result_becomes_canonical_findings(self) -> None:
        result = parse_review_result(block(ProviderRole.REVIEW), max_blockers=3)
        assert isinstance(result, ReviewResult)
        assert result.verdict is ReviewVerdict.BLOCKED
        assert [finding.finding_id for finding in result.blockers] == ["R-1"]
        assert result.blockers[0].status is FindingStatus.OPEN
        assert result.blockers[0].severity is FindingSeverity.CRITICAL
        assert result.deferred[0].status is FindingStatus.DEFERRED

    def test_a_closure_result_separates_closed_from_open(self) -> None:
        text = block(
            ProviderRole.CLOSURE,
            "findings:\n"
            "  - id: R-1\n"
            "    status: CLOSED\n"
            "    reason: addressed by the new parser boundary\n"
            "  - id: R-2\n"
            "    status: OPEN\n"
            "    reason: still unaddressed in the diff\n",
        )
        result = parse_closure_result(text, open_finding_ids=["R-1", "R-2"])
        assert isinstance(result, ClosureResult)
        assert result.closed_ids == ("R-1",)
        assert result.open_ids == ("R-2",)

    @pytest.mark.parametrize("role", list(ProviderRole))
    def test_a_block_for_one_role_is_not_readable_as_another(self, role: ProviderRole) -> None:
        text = block(role)
        for other in ProviderRole:
            if other is role:
                continue
            with pytest.raises(MalformedResult):
                parse_for_role(other, text)

    def test_an_unknown_field_in_the_body_is_rejected(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION, MILESTONE_BODY + "extra_field: whatever\n")
        with pytest.raises(MalformedResult, match="not a valid"):
            parse_milestone_result(text)

    def test_a_body_that_is_not_a_mapping_is_rejected(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION, "- just\n- a\n- list\n")
        with pytest.raises(MalformedResult, match="mapping"):
            parse_milestone_result(text)

    def test_an_oversized_block_is_rejected(self) -> None:
        filler = "\n".join(f"  - blocker number {index}" for index in range(60_000))
        text = block(ProviderRole.IMPLEMENTATION, f"blockers:\n{filler}\n")
        assert len(text) > MAX_RESULT_BLOCK_CHARS
        with pytest.raises(MalformedResult, match="ceiling"):
            parse_milestone_result(text)

    def test_narrative_before_the_block_is_tolerated(self) -> None:
        """A provider explaining itself before its result block is the ordinary case."""
        text = "I implemented the milestone.\n\nHere is the block:\n\n" + block(
            ProviderRole.IMPLEMENTATION
        )
        assert parse_milestone_result(text).milestone == "AUTO-016-M05"


class TestSingleOptionalFenceTolerated:
    """Section 18: exactly one optional Markdown fence, the empirically observed case (section 6).

    Tolerating it weakens nothing else -- the fence is stripped and the body still has to satisfy
    every rule -- which is what the second test here asserts.
    """

    @pytest.mark.parametrize("role", list(ProviderRole))
    def test_one_fence_around_the_block_is_stripped(self, role: ProviderRole) -> None:
        text = f"```\n{block(role)}```\n"
        assert parse_for_role(role, text) is not None

    def test_a_fence_with_an_info_string_is_tolerated(self) -> None:
        text = f"```yaml\n{block(ProviderRole.IMPLEMENTATION)}```\n"
        assert parse_milestone_result(text).milestone == "AUTO-016-M05"

    def test_a_fenced_block_still_satisfies_every_other_rule(self) -> None:
        incomplete = block(ProviderRole.IMPLEMENTATION, "status: COMPLETE\n")
        with pytest.raises(MalformedResult, match="not a valid"):
            parse_milestone_result(f"```yaml\n{incomplete}```\n")

    def test_the_extracted_body_is_the_body_and_nothing_else(self) -> None:
        grammar = MachineResultGrammar.for_role(ProviderRole.IMPLEMENTATION)
        body = extract_result_block(f"```\n{block(ProviderRole.IMPLEMENTATION)}```\n", grammar)
        assert body.strip().splitlines()[0] == "milestone: AUTO-016-M05"
        assert "```" not in body
        assert grammar.start not in body
        assert grammar.end not in body


class TestDoubleFenceRejected:
    """Section 18: two fences are rejected. One tolerance, not a general fence tolerance."""

    def test_two_fences_after_the_end_sentinel_are_rejected(self) -> None:
        text = f"```\n{block(ProviderRole.IMPLEMENTATION)}```\n```\n"
        with pytest.raises(MalformedResult):
            parse_milestone_result(text)

    def test_two_fences_before_the_start_sentinel_are_rejected(self) -> None:
        text = f"```\n```yaml\n{block(ProviderRole.IMPLEMENTATION)}```\n"
        with pytest.raises(MalformedResult, match="one matched pair"):
            parse_milestone_result(text)

    def test_a_doubly_wrapped_block_is_rejected(self) -> None:
        inner = f"```yaml\n{block(ProviderRole.REVIEW)}```\n"
        with pytest.raises(MalformedResult):
            parse_review_result(f"````\n{inner}````\n", max_blockers=3)


class TestPartialFenceRejected:
    """Section 18: a partial fence is rejected -- a fence is tolerated only as a matched pair."""

    def test_an_opening_fence_with_no_closing_fence_is_rejected(self) -> None:
        text = f"```yaml\n{block(ProviderRole.IMPLEMENTATION)}"
        with pytest.raises(MalformedResult, match="matched pair"):
            parse_milestone_result(text)

    def test_a_closing_fence_with_no_opening_fence_is_rejected(self) -> None:
        text = f"{block(ProviderRole.IMPLEMENTATION)}```\n"
        with pytest.raises(MalformedResult, match="matched pair"):
            parse_milestone_result(text)

    def test_a_fence_that_does_not_wrap_the_block_is_not_a_wrapper(self) -> None:
        """An opening fence separated from the block by prose is still an unmatched opening."""
        text = "```yaml\nsome: earlier yaml\n```\n\n" + block(ProviderRole.IMPLEMENTATION) + "```\n"
        with pytest.raises(MalformedResult, match="matched pair"):
            parse_milestone_result(text)


class TestTextAfterEndSentinelRejected:
    """Section 18: text after the end sentinel is rejected, whatever it says."""

    @pytest.mark.parametrize(
        "trailer",
        [
            "Let me know if you want anything else.\n",
            "status: COMPLETE\n",
            "AUTO016_MILESTONE_RESULT_EXTRA\n",
        ],
    )
    def test_prose_after_the_end_sentinel_is_rejected(self, trailer: str) -> None:
        with pytest.raises(MalformedResult, match="follows"):
            parse_milestone_result(block(ProviderRole.IMPLEMENTATION) + trailer)

    def test_blank_lines_after_the_end_sentinel_are_not_text(self) -> None:
        assert parse_milestone_result(block(ProviderRole.IMPLEMENTATION) + "\n\n   \n") is not None

    def test_a_closing_fence_plus_prose_is_rejected(self) -> None:
        text = f"```\n{block(ProviderRole.IMPLEMENTATION)}```\nthanks!\n"
        with pytest.raises(MalformedResult):
            parse_milestone_result(text)


class TestMissingBlockRejected:
    """Section 18: a missing sentinel is a rejection, never an empty result."""

    def test_text_with_no_block_at_all_is_rejected(self) -> None:
        with pytest.raises(MalformedResult, match="No AUTO016_MILESTONE_RESULT"):
            parse_milestone_result("I finished the milestone. Everything passed.\n")

    def test_a_start_sentinel_with_no_end_sentinel_is_rejected(self) -> None:
        text = f"AUTO016_MILESTONE_RESULT\n{MILESTONE_BODY}"
        with pytest.raises(MalformedResult, match="No END_AUTO016_MILESTONE_RESULT"):
            parse_milestone_result(text)

    def test_an_end_sentinel_with_no_start_sentinel_is_rejected(self) -> None:
        text = f"{MILESTONE_BODY}END_AUTO016_MILESTONE_RESULT\n"
        with pytest.raises(MalformedResult, match="No AUTO016_MILESTONE_RESULT"):
            parse_milestone_result(text)

    def test_a_sentinel_mentioned_inside_a_sentence_is_not_a_sentinel(self) -> None:
        """The grammar is line-oriented, so prose naming a sentinel does not open a block."""
        text = "I would emit AUTO016_MILESTONE_RESULT here if I had finished.\n"
        with pytest.raises(MalformedResult, match="No AUTO016_MILESTONE_RESULT"):
            parse_milestone_result(text)

    def test_an_empty_result_is_never_returned_for_missing_input(self) -> None:
        for text in ("", "\n", "   \n"):
            with pytest.raises(MalformedResult):
                parse_milestone_result(text)


class TestMultipleBlocksRejected:
    """Section 18: more than one block is rejected -- there is no "last one wins"."""

    def test_two_complete_blocks_are_rejected(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION) + block(ProviderRole.IMPLEMENTATION)
        with pytest.raises(MalformedResult, match="Exactly one result block"):
            parse_milestone_result(text)

    def test_a_second_start_sentinel_is_rejected(self) -> None:
        text = f"AUTO016_MILESTONE_RESULT\n{block(ProviderRole.IMPLEMENTATION)}"
        with pytest.raises(MalformedResult, match="Exactly one result block"):
            parse_milestone_result(text)

    def test_a_second_block_for_a_different_role_is_rejected(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION) + block(ProviderRole.REVIEW)
        with pytest.raises(MalformedResult, match="another role"):
            parse_milestone_result(text)


class TestMismatchedSentinelsRejected:
    """Section 18: a mismatched sentinel pair is rejected, in either direction."""

    def test_a_milestone_start_with_a_review_end_is_rejected(self) -> None:
        text = f"AUTO016_MILESTONE_RESULT\n{MILESTONE_BODY}END_AUTO016_REVIEW_RESULT\n"
        with pytest.raises(MalformedResult, match="another role"):
            parse_milestone_result(text)

    def test_a_review_start_with_a_milestone_end_is_rejected(self) -> None:
        text = f"AUTO016_REVIEW_RESULT\n{REVIEW_BODY}END_AUTO016_MILESTONE_RESULT\n"
        with pytest.raises(MalformedResult, match="another role"):
            parse_review_result(text, max_blockers=3)

    def test_an_end_sentinel_before_its_start_is_rejected(self) -> None:
        text = (
            "END_AUTO016_MILESTONE_RESULT\n"
            f"{MILESTONE_BODY}"
            "AUTO016_MILESTONE_RESULT\n"
            f"{MILESTONE_BODY}"
        )
        with pytest.raises(MalformedResult):
            parse_milestone_result(text)

    def test_a_correction_block_is_not_a_milestone_block(self) -> None:
        with pytest.raises(MalformedResult, match="another role"):
            parse_milestone_result(block(ProviderRole.CORRECTION))


class TestUnsafeYamlConstructRejected:
    """Section 18: a safe loader, so an unsafe construct is rejected and never constructed."""

    def test_a_python_object_tag_is_rejected(self) -> None:
        text = block(
            ProviderRole.IMPLEMENTATION,
            "milestone: !!python/object/apply:os.getcwd []\nstatus: COMPLETE\n",
        )
        with pytest.raises(MalformedResult, match="safe loader"):
            parse_milestone_result(text)

    def test_the_unsafe_construct_is_never_executed(self, tmp_path: Path) -> None:
        """The proof is a side effect that would exist if the loader had constructed anything."""
        target = tmp_path / "should-not-exist"
        text = block(
            ProviderRole.IMPLEMENTATION,
            f"milestone: !!python/object/apply:os.mkdir ['{target}']\nstatus: COMPLETE\n",
        )
        with pytest.raises(MalformedResult):
            parse_milestone_result(text)
        assert not target.exists()

    @pytest.mark.parametrize("role", list(ProviderRole))
    def test_every_role_uses_the_same_safe_loader(self, role: ProviderRole) -> None:
        text = block(role, "value: !!python/object/apply:os.getcwd []\n")
        with pytest.raises(MalformedResult, match="safe loader"):
            parse_for_role(role, text)

    def test_the_module_never_reaches_for_an_unsafe_loader(self) -> None:
        """A structural complement: the unsafe entry points are not named in the source at all."""
        tree = ast.parse(RESULTS_SOURCE.read_text(encoding="utf-8"))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "safe_load" in called
        for unsafe in ("load", "unsafe_load", "full_load", "load_all"):
            assert unsafe not in called

    def test_a_yaml_syntax_error_is_a_typed_rejection(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION, "milestone: [unclosed\nstatus: COMPLETE\n")
        with pytest.raises(MalformedResult):
            parse_milestone_result(text)


# --------------------------------------------------------------------------------------
# Section 18 / section 19 -- semantic contradictions
# --------------------------------------------------------------------------------------


def review_block(verdict: str, blockers: Sequence[tuple[str, str]] = ()) -> str:
    entries = "".join(
        f"  - id: {identifier}\n"
        f"    severity: {severity}\n"
        f"    title: a finding\n"
        f"    summary: something is wrong somewhere.\n"
        for identifier, severity in blockers
    )
    body = f"verdict: {verdict}\nblockers:\n{entries}deferred: []\n"
    return block(ProviderRole.REVIEW, body)


class TestBlockedVerdictWithNoBlockersRejected:
    """Section 18: a `BLOCKED` verdict with no blockers is a contradiction, not a verdict."""

    def test_blocked_with_an_empty_blocker_list_is_rejected(self) -> None:
        with pytest.raises(MalformedResult, match="at least one blocker"):
            parse_review_result(review_block("BLOCKED"), max_blockers=3)

    def test_blocked_with_a_null_blocker_list_is_rejected(self) -> None:
        text = block(ProviderRole.REVIEW, "verdict: BLOCKED\nblockers:\ndeferred:\n")
        with pytest.raises(MalformedResult, match="at least one blocker"):
            parse_review_result(text, max_blockers=3)

    def test_blocked_with_only_deferred_findings_is_rejected(self) -> None:
        text = block(
            ProviderRole.REVIEW,
            "verdict: BLOCKED\n"
            "blockers: []\n"
            "deferred:\n"
            "  - id: D-1\n"
            "    severity: LOW\n"
            "    title: nit\n"
            "    summary: a small thing.\n",
        )
        with pytest.raises(MalformedResult, match="at least one blocker"):
            parse_review_result(text, max_blockers=3)

    def test_a_blocked_verdict_with_one_blocker_is_accepted(self) -> None:
        result = parse_review_result(review_block("BLOCKED", [("B-1", "HIGH")]), max_blockers=3)
        assert result.verdict is ReviewVerdict.BLOCKED


class TestApprovedVerdictWithBlockersRejected:
    """Section 18: an `APPROVED` verdict carrying blockers is the mirror contradiction."""

    def test_approved_with_one_blocker_is_rejected(self) -> None:
        with pytest.raises(MalformedResult, match="no blocker"):
            parse_review_result(review_block("APPROVED", [("B-1", "HIGH")]), max_blockers=3)

    def test_approved_with_no_blockers_is_accepted(self) -> None:
        result = parse_review_result(review_block("APPROVED"), max_blockers=3)
        assert result.verdict is ReviewVerdict.APPROVED
        assert result.blockers == []

    def test_approved_may_still_carry_deferred_findings(self) -> None:
        text = block(
            ProviderRole.REVIEW,
            "verdict: APPROVED\n"
            "blockers: []\n"
            "deferred:\n"
            "  - id: D-1\n"
            "    severity: MEDIUM\n"
            "    title: worth noting\n"
            "    summary: not blocking, recorded for the ledger.\n",
        )
        result = parse_review_result(text, max_blockers=3)
        assert [finding.finding_id for finding in result.deferred] == ["D-1"]


class TestNonBlockingSeverityInBlockersRejected:
    """Section 18: a blocker whose severity is not Critical or High is malformed."""

    @pytest.mark.parametrize("severity", ["MEDIUM", "LOW"])
    def test_a_deferrable_severity_cannot_be_a_blocker(self, severity: str) -> None:
        with pytest.raises(MalformedResult, match="only"):
            parse_review_result(review_block("BLOCKED", [("B-1", severity)]), max_blockers=3)

    def test_an_unknown_severity_is_rejected(self) -> None:
        with pytest.raises(MalformedResult, match="not a valid"):
            parse_review_result(review_block("BLOCKED", [("B-1", "SEVERE")]), max_blockers=3)

    def test_a_blocking_severity_cannot_be_filed_as_deferred(self) -> None:
        """The mirror rule: a Critical finding is not demoted by putting it in the other list."""
        text = block(
            ProviderRole.REVIEW,
            "verdict: APPROVED\n"
            "blockers: []\n"
            "deferred:\n"
            "  - id: D-1\n"
            "    severity: CRITICAL\n"
            "    title: serious\n"
            "    summary: filed in the wrong list.\n",
        )
        with pytest.raises(MalformedResult, match="cannot be filed as deferred"):
            parse_review_result(text, max_blockers=3)


class TestBlockerCapExceededRejected:
    """Section 18 and section 19: more blockers than `max_blockers` is malformed."""

    def test_four_blockers_against_a_cap_of_three_is_rejected(self) -> None:
        blockers = [(f"B-{index}", "HIGH") for index in range(4)]
        with pytest.raises(MalformedResult, match="above the configured maximum"):
            parse_review_result(review_block("BLOCKED", blockers), max_blockers=3)

    def test_exactly_the_cap_is_accepted(self) -> None:
        blockers = [(f"B-{index}", "HIGH") for index in range(3)]
        result = parse_review_result(review_block("BLOCKED", blockers), max_blockers=3)
        assert len(result.blockers) == 3

    def test_the_cap_is_the_caller_s_configured_value(self) -> None:
        blockers = [(f"B-{index}", "HIGH") for index in range(2)]
        with pytest.raises(MalformedResult, match="above the configured maximum"):
            parse_review_result(review_block("BLOCKED", blockers), max_blockers=1)

    def test_a_duplicate_finding_id_is_rejected(self) -> None:
        blockers = [("B-1", "HIGH"), ("B-1", "CRITICAL")]
        with pytest.raises(MalformedResult, match="same finding id twice"):
            parse_review_result(review_block("BLOCKED", blockers), max_blockers=3)


class TestClosureIsLimitedToTheOpenFindings:
    """Section 19: a closure result naming an unknown finding id is malformed."""

    def test_an_unknown_finding_id_is_rejected(self) -> None:
        with pytest.raises(MalformedResult, match="not one of the open findings"):
            parse_closure_result(block(ProviderRole.CLOSURE), open_finding_ids=["R-9"])

    def test_a_new_finding_cannot_be_introduced_at_closure(self) -> None:
        text = block(
            ProviderRole.CLOSURE,
            "findings:\n"
            "  - id: R-1\n"
            "    status: CLOSED\n"
            "    reason: addressed.\n"
            "  - id: BRAND-NEW\n"
            "    status: OPEN\n"
            "    reason: I found something else.\n",
        )
        with pytest.raises(MalformedResult, match="may not introduce a finding"):
            parse_closure_result(text, open_finding_ids=["R-1"])

    def test_a_deferred_ruling_is_not_a_closure_outcome(self) -> None:
        text = block(
            ProviderRole.CLOSURE,
            "findings:\n  - id: R-1\n    status: DEFERRED\n    reason: later.\n",
        )
        with pytest.raises(MalformedResult, match="closure outcome"):
            parse_closure_result(text, open_finding_ids=["R-1"])

    def test_ruling_on_one_id_twice_is_rejected(self) -> None:
        text = block(
            ProviderRole.CLOSURE,
            "findings:\n"
            "  - id: R-1\n"
            "    status: CLOSED\n"
            "    reason: addressed.\n"
            "  - id: R-1\n"
            "    status: OPEN\n"
            "    reason: actually not.\n",
        )
        with pytest.raises(MalformedResult, match="twice"):
            parse_closure_result(text, open_finding_ids=["R-1"])

    def test_silence_on_an_open_id_is_not_a_ruling(self) -> None:
        result = parse_closure_result(block(ProviderRole.CLOSURE), open_finding_ids=["R-1", "R-2"])
        assert result.closed_ids == ("R-1",)
        assert "R-2" not in result.open_ids


class TestP2MissingResultFieldIsTypedRejection:
    """Defect P-2: a missing field is a typed rejection at the parser, never a caller `KeyError`.

    The prototype's `parse_milestone_result` neither required nor defaulted `milestone`, and two
    callers indexed `result["milestone"]`, producing a traceback with no `stop_reason` recorded.
    """

    def test_a_milestone_result_missing_its_milestone_key_is_rejected(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION, "status: COMPLETE\nchanged_paths: []\n")
        with pytest.raises(MalformedResult) as raised:
            parse_milestone_result(text)
        assert "milestone" in str(raised.value)

    def test_the_rejection_is_never_a_key_error(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION, "status: COMPLETE\n")
        try:
            parse_milestone_result(text)
        except MalformedResult:
            pass
        except KeyError as exc:  # pragma: no cover - the defect this test exists to prevent
            pytest.fail(f"the parser raised an uncaught KeyError: {exc}")

    def test_no_partially_validated_mapping_is_ever_returned(self) -> None:
        """There is no value to read a field off: the parser raised instead of returning one."""
        text = block(ProviderRole.IMPLEMENTATION, "status: COMPLETE\n")
        result: MilestoneResult | None = None
        with pytest.raises(MalformedResult):
            result = parse_milestone_result(text)
        assert result is None

    def test_every_field_is_required_or_explicitly_defaulted(self) -> None:
        """The rule stated as a property of the model, so a new field cannot slip through."""
        for model in (MilestoneResult, CorrectionResult, ClosureResult):
            for name, field in model.model_fields.items():
                assert (
                    field.is_required() or field.default is not None or field.default_factory
                ), f"{model.__name__}.{name} is neither required nor explicitly defaulted"

    def test_a_result_reporting_on_another_milestone_is_rejected(self) -> None:
        with pytest.raises(MalformedResult, match="not on the requested"):
            parse_milestone_result(
                block(ProviderRole.IMPLEMENTATION), expected_milestone_id="AUTO-016-M06"
            )

    def test_a_blocked_status_with_no_blockers_is_rejected(self) -> None:
        text = block(ProviderRole.IMPLEMENTATION, "milestone: AUTO-016-M05\nstatus: BLOCKED\n")
        with pytest.raises(MalformedResult, match="at least one blocker"):
            parse_milestone_result(text)

    def test_a_complete_status_carrying_blockers_is_rejected(self) -> None:
        text = block(
            ProviderRole.IMPLEMENTATION,
            "milestone: AUTO-016-M05\nstatus: COMPLETE\nblockers:\n  - something is wrong\n",
        )
        with pytest.raises(MalformedResult, match="no blocker"):
            parse_milestone_result(text)

    def test_an_absolute_changed_path_is_rejected(self) -> None:
        text = block(
            ProviderRole.IMPLEMENTATION,
            "milestone: AUTO-016-M05\nstatus: COMPLETE\nchanged_paths:\n  - /etc/passwd\n",
        )
        with pytest.raises(MalformedResult):
            parse_milestone_result(text)


# --------------------------------------------------------------------------------------
# Section 18 / invariant 15 -- a rejection destroys no evidence
# --------------------------------------------------------------------------------------


FAKE_PROVIDER_SOURCE = '''#!/usr/bin/env python3
"""A scripted stand-in for a model-provider CLI: reads stdin, prints a fixed answer."""
import sys

sys.stdin.read()
sys.stdout.write(OUTPUT)
sys.stderr.write("provider diagnostics\\n")
'''


@pytest.fixture
def make_fake_provider(tmp_path: Path) -> Callable[[str], Path]:
    """Write a real, executable fake provider that prints `output` and return its path."""
    counter = {"n": 0}

    def make(output: str) -> Path:
        counter["n"] += 1
        directory = tmp_path / f"fake-{counter['n']}"
        directory.mkdir()
        script = directory / FAKE_PROVIDER
        script.write_text(FAKE_PROVIDER_SOURCE.replace("OUTPUT", repr(output), 1), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return script

    return make


class TestRejectedResultPreservesTranscripts:
    """Section 18 and invariant 15: a rejected result keeps every transcript, and references it.

    Driven end to end through the real provider boundary: a real subprocess writes a malformed
    result, the real invoker persists the transcript triple, and the parser rejects what it said.
    The assertion is that the three files are still on disk afterwards and that the rejection
    names them.
    """

    def _invocation_and_rejection(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        environment: dict[str, str],
        script: Path,
    ) -> tuple[ProviderRunRecord, MalformedResult]:
        invoker = ProviderInvoker(
            store=store,
            lock=held_lock,
            repository_root=worktree,
            allowed_environment_variables=("PATH", "HOME"),
            source_environment=environment,
        )
        invocation = invoker.invoke(
            ProviderRequest(
                provider="fake",
                role=ProviderRole.IMPLEMENTATION,
                argv=[sys.executable, str(script)],
                prompt="implement AUTO-016-M05",
                timeout_seconds=30,
                transcript_label="fake-implementation",
                milestone_id="AUTO-016-M05",
            )
        )
        transcripts = ResultTranscripts.of(invocation.record)
        with pytest.raises(MalformedResult) as raised:
            parse_milestone_result(invocation.stdout, transcripts=transcripts)
        return invocation.record, raised.value

    def test_the_transcript_triple_survives_the_rejection(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        environment: dict[str, str],
        make_fake_provider: Callable[[str], Path],
    ) -> None:
        script = make_fake_provider("I could not produce a block.\n")
        record, error = self._invocation_and_rejection(
            store, held_lock, worktree, environment, script
        )
        for reference in (record.prompt_path, record.stdout_path, record.stderr_path):
            assert (store.run_directory / reference).is_file(), reference
        assert transcript_text(store, record.prompt_path) == "implement AUTO-016-M05"
        assert "could not produce a block" in transcript_text(store, record.stdout_path)
        assert "provider diagnostics" in transcript_text(store, record.stderr_path)
        assert error.transcripts is not None

    def test_the_rejection_references_every_transcript_by_path(
        self,
        store: RunStateStore,
        held_lock: RunLock,
        worktree: Path,
        environment: dict[str, str],
        make_fake_provider: Callable[[str], Path],
    ) -> None:
        script = make_fake_provider(block(ProviderRole.IMPLEMENTATION, "status: COMPLETE\n"))
        record, error = self._invocation_and_rejection(
            store, held_lock, worktree, environment, script
        )
        assert error.transcripts == ResultTranscripts(
            prompt_path=record.prompt_path,
            stdout_path=record.stdout_path,
            stderr_path=record.stderr_path,
        )
        assert error.role is ProviderRole.IMPLEMENTATION

    def test_the_parser_module_removes_nothing_from_the_filesystem(self) -> None:
        """The structural half: no removal primitive is named in the module at all."""
        tree = ast.parse(RESULTS_SOURCE.read_text(encoding="utf-8"))
        names = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for primitive in ("unlink", "remove", "rmtree", "rmdir", "truncate", "open", "write_text"):
            assert primitive not in names, primitive


# --------------------------------------------------------------------------------------
# Section 16 -- bounded execution and PASS/FAIL classification
# --------------------------------------------------------------------------------------


class TestBoundedCommandExecution:
    """Section 16: argv lists, bounded timeouts, and exit-code classification."""

    def test_exit_code_zero_is_a_pass(self, executor: VerificationExecutor) -> None:
        outcome = executor.run(python_command("print('ok')"), timeout_seconds=30)
        assert outcome.passed
        assert outcome.exit_code == 0
        assert outcome.timed_out is False
        assert "ok" in outcome.stdout

    @pytest.mark.parametrize("code", [1, 2, 7])
    def test_any_other_exit_code_is_a_fail(self, executor: VerificationExecutor, code: int) -> None:
        outcome = executor.run(python_command(f"raise SystemExit({code})"), timeout_seconds=30)
        assert not outcome.passed
        assert outcome.exit_code == code

    def test_a_command_runs_in_the_repository_root(
        self, executor: VerificationExecutor, worktree: Path
    ) -> None:
        outcome = executor.run(python_command("import os; print(os.getcwd())"), timeout_seconds=30)
        assert Path(outcome.stdout.strip()).resolve() == worktree.resolve()

    def test_the_child_gets_exactly_the_configured_environment(
        self, executor: VerificationExecutor
    ) -> None:
        outcome = executor.run(
            python_command("import os; print(sorted(os.environ))"), timeout_seconds=30
        )
        assert "PATH" in outcome.stdout
        assert "LC_ALL" not in outcome.stdout

    def test_an_empty_argument_vector_is_refused(self, worktree: Path) -> None:
        with pytest.raises(VerificationError, match="empty argument vector"):
            run_bounded_command(argv=[], cwd=worktree, environment={}, timeout_seconds=5)

    def test_a_non_positive_timeout_is_refused(self, worktree: Path) -> None:
        with pytest.raises(VerificationError, match="positive"):
            run_bounded_command(
                argv=[sys.executable, "-c", "pass"],
                cwd=worktree,
                environment={},
                timeout_seconds=0,
            )

    def test_a_command_the_record_could_not_hold_is_refused_before_it_runs(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        """A multi-line argument is refused up front, not discovered after the command ran."""
        with pytest.raises(VerificationError, match="control character"):
            executor.run([sys.executable, "-c", "print('a')\nprint('b')"], timeout_seconds=30)
        assert not list(store.transcripts_directory.glob("*verification*"))

    def test_a_missing_executable_is_a_fail_not_a_crash(
        self, executor: VerificationExecutor
    ) -> None:
        outcome = executor.run(["definitely-not-an-executable-9zq"], timeout_seconds=5)
        assert not outcome.passed
        assert outcome.spawn_error is not None
        assert outcome.exit_code is None

    def test_the_spawn_failure_still_writes_its_evidence(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        outcome = executor.run(["definitely-not-an-executable-9zq"], timeout_seconds=5)
        assert "definitely-not-an-executable-9zq" in transcript_text(
            store, outcome.result.stderr_path
        )

    def test_the_environment_builder_prepends_the_conda_bin(self) -> None:
        built = build_verification_environment(
            {"PATH": "/usr/bin", "HOME": "/home/x"}, conda_bin=Path("/opt/conda/envs/e/bin")
        )
        assert built["PATH"] == "/opt/conda/envs/e/bin:/usr/bin"
        assert built["HOME"] == "/home/x"

    def test_the_environment_builder_copies_rather_than_mutates(self) -> None:
        source = {"PATH": "/usr/bin"}
        build_verification_environment(source, conda_bin=Path("/opt/bin"))
        assert source == {"PATH": "/usr/bin"}


class TestTimeoutIsNeverASuccess:
    """Section 16 and invariant 18: a timeout is a FAIL with `timed_out` true, never a pass."""

    def test_a_timeout_is_recorded_as_a_failure(self, executor: VerificationExecutor) -> None:
        outcome = executor.run(python_command("import time; time.sleep(30)"), timeout_seconds=1)
        assert outcome.timed_out is True
        assert outcome.passed is False
        assert outcome.result.passed is False

    def test_a_record_claiming_a_pass_after_a_timeout_cannot_be_built(self) -> None:
        with pytest.raises(ValueError, match="passed must be exactly"):
            VerificationResult(
                command=["pytest", "-q"],
                exit_code=0,
                timed_out=True,
                passed=True,
                duration_ms=10,
                stdout_path="transcripts/0001-20260806T000000Z-verification.stdout.txt",
                stderr_path="transcripts/0001-20260806T000000Z-verification.stderr.txt",
            )

    def test_output_produced_before_the_deadline_is_still_persisted(
        self,
        executor: VerificationExecutor,
        store: RunStateStore,
        python_script: Callable[[str], list[str]],
    ) -> None:
        outcome = executor.run(
            python_script(
                """
                import sys, time
                sys.stdout.write("before the deadline\\n")
                sys.stdout.flush()
                time.sleep(30)
                """
            ),
            timeout_seconds=2,
        )
        assert outcome.timed_out
        assert "before the deadline" in transcript_text(store, outcome.result.stdout_path)


class TestP8FullVerificationOutputPersisted:
    """Defect P-8: the complete output reaches disk; the record carries only references.

    The prototype kept the last 800 characters of a failed command's output. Here the whole of
    both streams is sanitized and written to the run's transcript directory, and the record holds
    the exit code, the duration, the timeout flag and two paths -- nothing else.
    """

    LINES = 5_000

    def _noisy_command(self, python_script: Callable[[str], list[str]]) -> list[str]:
        return python_script(
            f"""
            import sys
            for index in range({self.LINES}):
                sys.stdout.write(f"stdout line {{index}}\\n")
                sys.stderr.write(f"stderr line {{index}}\\n")
            raise SystemExit(1)
            """
        )

    def test_the_whole_of_both_streams_reaches_disk(
        self,
        executor: VerificationExecutor,
        store: RunStateStore,
        python_script: Callable[[str], list[str]],
    ) -> None:
        outcome = executor.run(self._noisy_command(python_script), timeout_seconds=60)
        assert not outcome.passed
        stdout = transcript_text(store, outcome.result.stdout_path)
        stderr = transcript_text(store, outcome.result.stderr_path)
        assert stdout.count("stdout line ") == self.LINES
        assert stderr.count("stderr line ") == self.LINES
        assert "stdout line 0\n" in stdout
        assert f"stdout line {self.LINES - 1}\n" in stdout
        assert len(stdout) > 800

    def test_no_output_is_kept_as_a_tail(
        self,
        executor: VerificationExecutor,
        store: RunStateStore,
        python_script: Callable[[str], list[str]],
    ) -> None:
        """The first line survives, which an 800-character tail of 5,000 lines could not."""
        outcome = executor.run(self._noisy_command(python_script), timeout_seconds=60)
        assert transcript_text(store, outcome.result.stdout_path).startswith("stdout line 0\n")

    def test_the_record_carries_references_and_no_output(
        self, executor: VerificationExecutor, python_script: Callable[[str], list[str]]
    ) -> None:
        outcome = executor.run(self._noisy_command(python_script), timeout_seconds=60)
        payload = json.loads(outcome.result.model_dump_json())
        assert set(payload) == {
            "command",
            "exit_code",
            "timed_out",
            "passed",
            "duration_ms",
            "stdout_path",
            "stderr_path",
        }
        assert "stdout line" not in json.dumps(payload)

    def test_the_references_are_run_relative_transcript_paths(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        outcome = executor.run(python_command("print('hi')"), timeout_seconds=30)
        for reference in (outcome.result.stdout_path, outcome.result.stderr_path):
            assert reference.startswith("transcripts/")
            assert (store.run_directory / reference).is_file()

    def test_two_commands_never_share_a_transcript(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        """Defect P-9's sequence number applies to verification output too."""
        first = executor.run(python_command("print('first')"), timeout_seconds=30)
        second = executor.run(python_command("print('second')"), timeout_seconds=30)
        assert first.result.stdout_path != second.result.stdout_path
        assert transcript_text(store, first.result.stdout_path).strip() == "first"
        assert transcript_text(store, second.result.stdout_path).strip() == "second"

    def test_output_passes_the_redaction_boundary_before_it_lands(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        """Section 17a: a verification command's output is sanitized like any other byte."""
        outcome = executor.run(
            python_command("print('token ghp_0123456789abcdefghijklmnopqrstuvwx')"),
            timeout_seconds=30,
        )
        persisted = transcript_text(store, outcome.result.stdout_path)
        assert "ghp_0123456789abcdefghijklmnopqrstuvwx" not in persisted
        assert any(write.redacted for write in outcome.writes)

    def test_the_module_keeps_no_tail_slice_of_captured_output(self) -> None:
        """A structural complement: nothing in the code slices a stream from its end."""
        tree = ast.parse(VERIFICATION_SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript) or not isinstance(node.slice, ast.Slice):
                continue
            lower = node.slice.lower
            assert not isinstance(lower, ast.UnaryOp) or not isinstance(
                lower.op, ast.USub
            ), "a negative lower bound would be a tail of the captured output (defect P-8)"


# --------------------------------------------------------------------------------------
# Section 4 item 7 / section 16 -- the governance gate (defect P-7)
# --------------------------------------------------------------------------------------


def check_document(check_name: str, status: Status, codes: Sequence[str] = ()) -> str:
    """One machine-readable check document, rendered by the engine's own reporting function.

    Built from the real `CheckResult` model and rendered by `render_json`, which is exactly what
    `workflowctl check-<name> --output json` emits under the stable 1.0 contract. The gate is
    therefore proved against the shape the CLI actually produces.
    """
    return render_json(
        CheckResult(
            check_name=check_name,
            status=status,
            summary=f"{check_name}: {status.value}",
            findings=[
                EngineFinding(code=code, message=f"{code} was observed", severity="error")
                for code in codes
            ],
        )
    )


def passing_checks() -> list[GovernanceCheckResult]:
    return [
        GovernanceCheckResult(check_name=name, status=GovernanceCheckStatus.PASS)
        for name in REQUIRED_GOVERNANCE_CHECKS
    ]


class TestP7GovernanceGateUsesMachineReadableOutput:
    """Defect P-7: the gate reads structured per-check results, never a rendered console table.

    The prototype scraped box-drawing characters out of `workflowctl verify`'s table under a
    forced `LC_ALL=C`, so any formatting change moved the gate unpredictably in either direction.
    Here the gate is decided by parsed documents; a console rendering cannot open it, and a
    formatting change cannot close it.
    """

    def test_a_real_check_document_parses(self) -> None:
        result = parse_governance_check_document(
            check_document("git", Status.FAIL, ["upstream_missing"]), check_name="git"
        )
        assert result.status is GovernanceCheckStatus.FAIL
        assert result.finding_codes == ["upstream_missing"]

    def test_a_rendered_console_table_can_never_open_the_gate(self) -> None:
        rendered = (
            "┏━━━━━━━━━━━━┳━━━━━━━━┓\n"
            "┃ Check      ┃ Status ┃\n"
            "┡━━━━━━━━━━━━╇━━━━━━━━┩\n"
            "│ git        │ PASS   │\n"
            "└────────────┴────────┘\n"
        )
        with pytest.raises(GovernanceContradiction, match="machine-readable"):
            parse_governance_check_document(rendered, check_name="git")

    def test_a_formatting_change_cannot_close_the_gate(self) -> None:
        """The same structured verdict, rendered differently, is still the same verdict."""
        spaced = json.dumps(
            json.loads(check_document("git", Status.PASS)), indent=8, sort_keys=True
        )
        assert (
            parse_governance_check_document(spaced, check_name="git").status
            is GovernanceCheckStatus.PASS
        )

    def test_the_module_scrapes_nothing_and_forces_no_locale(self) -> None:
        """No box-drawing character and no locale variable exists in anything the code operates on.

        The module docstring names both, because it records the defect being corrected; the
        assertion is about the literals the code itself uses.
        """
        for literal in code_string_constants(VERIFICATION_SOURCE):
            for scraped in ("┃", "│", "─", "━", "┏", "└"):
                assert scraped not in literal, literal
            assert "LC_ALL" not in literal, literal

    def test_a_document_identifying_another_check_is_refused(self) -> None:
        with pytest.raises(GovernanceContradiction, match="identifies itself"):
            parse_governance_check_document(
                check_document("task-state", Status.PASS), check_name="git"
            )

    def test_a_duplicate_key_makes_a_document_unreadable(self) -> None:
        document = '{"check_name": "git", "status": "PASS", "status": "FAIL", "findings": []}'
        with pytest.raises(GovernanceContradiction):
            parse_governance_check_document(document, check_name="git")

    def test_an_unknown_status_is_refused(self) -> None:
        document = '{"check_name": "git", "status": "PROBABLY_FINE", "findings": []}'
        with pytest.raises(GovernanceContradiction, match="unknown status"):
            parse_governance_check_document(document, check_name="git")

    def test_a_finding_without_a_usable_code_is_refused(self) -> None:
        document = '{"check_name": "git", "status": "FAIL", "findings": [{"message": "bad"}]}'
        with pytest.raises(GovernanceContradiction, match="no usable code"):
            parse_governance_check_document(document, check_name="git")


class TestTheGovernanceGateTolerance:
    """Section 4 item 7: exactly one tolerance, on exactly one check, and nothing else."""

    def test_all_five_checks_passing_opens_the_gate(self) -> None:
        decision = evaluate_governance_gate(passing_checks())
        assert [check.check_name for check in decision.checks] == list(REQUIRED_GOVERNANCE_CHECKS)
        assert decision.tolerated == []

    def test_upstream_missing_on_the_git_check_is_tolerated(self) -> None:
        checks = passing_checks()
        checks[0] = GovernanceCheckResult(
            check_name=GOVERNANCE_GIT_CHECK,
            status=GovernanceCheckStatus.FAIL,
            finding_codes=["upstream_missing"],
        )
        decision = evaluate_governance_gate(checks)
        assert decision.tolerated == ["git:upstream_missing"]

    def test_any_other_git_finding_is_a_contradiction(self) -> None:
        checks = passing_checks()
        checks[0] = GovernanceCheckResult(
            check_name=GOVERNANCE_GIT_CHECK,
            status=GovernanceCheckStatus.FAIL,
            finding_codes=["upstream_missing", "branch_mismatch"],
        )
        with pytest.raises(GovernanceContradiction) as raised:
            evaluate_governance_gate(checks)
        assert raised.value.findings == ("git:branch_mismatch",)

    @pytest.mark.parametrize("name", UNCONDITIONAL_GOVERNANCE_CHECKS)
    def test_the_tolerance_does_not_extend_to_another_check(self, name: str) -> None:
        checks = [
            (
                GovernanceCheckResult(
                    check_name=check,
                    status=GovernanceCheckStatus.FAIL,
                    finding_codes=["upstream_missing"],
                )
                if check == name
                else GovernanceCheckResult(check_name=check, status=GovernanceCheckStatus.PASS)
            )
            for check in REQUIRED_GOVERNANCE_CHECKS
        ]
        with pytest.raises(GovernanceContradiction, match=f"{name}:upstream_missing"):
            evaluate_governance_gate(checks)

    def test_a_check_error_is_a_contradiction(self) -> None:
        checks = passing_checks()
        checks[1] = GovernanceCheckResult(
            check_name=checks[1].check_name, status=GovernanceCheckStatus.ERROR
        )
        with pytest.raises(GovernanceContradiction, match="CHECK_ERROR"):
            evaluate_governance_gate(checks)

    def test_a_failure_naming_no_finding_is_a_contradiction(self) -> None:
        checks = passing_checks()
        checks[0] = GovernanceCheckResult(
            check_name=GOVERNANCE_GIT_CHECK, status=GovernanceCheckStatus.FAIL
        )
        with pytest.raises(GovernanceContradiction, match="CHECK_FAIL_WITHOUT_FINDING"):
            evaluate_governance_gate(checks)

    def test_a_missing_check_result_is_a_contradiction(self) -> None:
        with pytest.raises(GovernanceContradiction, match="missing"):
            evaluate_governance_gate(passing_checks()[:-1])

    def test_a_duplicate_check_result_is_a_contradiction(self) -> None:
        checks = passing_checks()
        checks.append(checks[0])
        with pytest.raises(GovernanceContradiction, match="Two results"):
            evaluate_governance_gate(checks)

    def test_an_unasked_for_result_is_a_contradiction(self) -> None:
        checks = passing_checks()
        checks.append(
            GovernanceCheckResult(check_name="invented", status=GovernanceCheckStatus.PASS)
        )
        with pytest.raises(GovernanceContradiction, match="did not ask for"):
            evaluate_governance_gate(checks)

    def test_the_tolerance_set_is_exactly_the_one_documented_finding(self) -> None:
        assert TOLERATED_GIT_FINDING_CODES == frozenset({"upstream_missing"})
        assert REQUIRED_GOVERNANCE_CHECKS == (
            GOVERNANCE_GIT_CHECK,
            *UNCONDITIONAL_GOVERNANCE_CHECKS,
        )

    def test_the_gate_writes_nothing_and_reads_no_document(self) -> None:
        """A pure decision: the evaluator opens no file and spawns nothing."""
        tree = ast.parse(VERIFICATION_SOURCE.read_text(encoding="utf-8"))
        evaluator = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "evaluate_governance_gate"
        )
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(evaluator)
            if isinstance(node, ast.Call)
        }
        for forbidden in ("run", "Popen", "open", "read_text", "write_text", "safe_load"):
            assert forbidden not in called


class TestTheGovernanceChecksRunIndividually:
    """Section 16: the checks run one by one, so the git tolerance loosens nothing else."""

    def _check_commands(self, documents: dict[str, str]) -> dict[str, VerificationCommandSettings]:
        return {
            name: VerificationCommandSettings(
                command=python_command(f"import sys; sys.stdout.write({document!r})"),
                timeout_seconds=60,
                purpose=f"the {name} governance check",
            )
            for name, document in documents.items()
        }

    def _documents(self, **overrides: str) -> dict[str, str]:
        documents = {name: check_document(name, Status.PASS) for name in REQUIRED_GOVERNANCE_CHECKS}
        documents.update(overrides)
        return documents

    def test_every_required_check_is_run_as_its_own_command(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        decision = executor.run_governance_gate(self._check_commands(self._documents()))
        assert [outcome.purpose for outcome in decision.outcomes] == [
            f"the {name} governance check" for name in REQUIRED_GOVERNANCE_CHECKS
        ]
        assert len({outcome.result.stdout_path for outcome in decision.outcomes}) == len(
            REQUIRED_GOVERNANCE_CHECKS
        )
        for outcome in decision.outcomes:
            assert (store.run_directory / outcome.result.stdout_path).is_file()

    def test_the_git_tolerance_applies_only_to_the_git_check(
        self, executor: VerificationExecutor
    ) -> None:
        documents = self._documents(
            git=check_document("git", Status.FAIL, ["upstream_missing"]),
        )
        decision = executor.run_governance_gate(self._check_commands(documents))
        assert decision.tolerated == ["git:upstream_missing"]

    def test_a_failing_content_check_stops_the_gate(self, executor: VerificationExecutor) -> None:
        documents = self._documents(
            governance=check_document("governance", Status.FAIL, ["stale_registry_row"]),
        )
        with pytest.raises(GovernanceContradiction, match="governance:stale_registry_row"):
            executor.run_governance_gate(self._check_commands(documents))

    def test_a_check_that_emits_a_table_stops_the_gate(
        self, executor: VerificationExecutor
    ) -> None:
        documents = self._documents(handover="│ handover │ PASS │\n")
        with pytest.raises(GovernanceContradiction, match="machine-readable"):
            executor.run_governance_gate(self._check_commands(documents))

    def test_a_check_command_that_cannot_run_stops_the_gate(
        self, executor: VerificationExecutor
    ) -> None:
        commands = self._check_commands(self._documents())
        commands["registries"] = VerificationCommandSettings(
            command=["definitely-not-an-executable-9zq"], timeout_seconds=5
        )
        with pytest.raises(GovernanceContradiction, match="did not produce a result"):
            executor.run_governance_gate(commands)

    def test_a_missing_check_command_stops_the_gate_before_anything_runs(
        self, executor: VerificationExecutor, store: RunStateStore
    ) -> None:
        commands = self._check_commands(self._documents())
        del commands["handover"]
        with pytest.raises(GovernanceContradiction, match="missing"):
            executor.run_governance_gate(commands)
        assert not list(store.transcripts_directory.glob("*verification*"))

    def test_a_check_the_gate_does_not_run_is_refused_rather_than_skipped(
        self, executor: VerificationExecutor
    ) -> None:
        commands = self._check_commands(self._documents())
        commands["invented-check"] = VerificationCommandSettings(
            command=python_command("pass"), timeout_seconds=5
        )
        with pytest.raises(GovernanceContradiction, match="does not run"):
            executor.run_governance_gate(commands)

    def test_the_gate_carries_its_outcomes_for_the_stop_record(
        self, executor: VerificationExecutor
    ) -> None:
        documents = self._documents(
            **{"task-state": check_document("task-state", Status.FAIL, ["task_state_mismatch"])}
        )
        with pytest.raises(GovernanceContradiction) as raised:
            executor.run_governance_gate(self._check_commands(documents))
        assert [outcome.result.command for outcome in raised.value.outcomes]
        assert raised.value.findings == ("task-state:task_state_mismatch",)


class TestTheExecutorRunsConfiguredSets:
    """Section 16: a configured set runs in order, and every command is recorded."""

    def test_a_set_runs_every_command_even_after_a_failure(
        self, executor: VerificationExecutor
    ) -> None:
        outcomes = executor.run_set(
            [
                VerificationCommandSettings(
                    command=python_command("raise SystemExit(1)"), timeout_seconds=30
                ),
                VerificationCommandSettings(
                    command=python_command("print('still ran')"), timeout_seconds=30
                ),
            ]
        )
        assert [outcome.passed for outcome in outcomes] == [False, True]
        assert "still ran" in outcomes[1].stdout

    def test_a_configured_command_keeps_its_purpose(self, executor: VerificationExecutor) -> None:
        outcome = executor.run_configured(
            VerificationCommandSettings(
                command=python_command("pass"), timeout_seconds=30, purpose="a stated purpose"
            )
        )
        assert outcome.purpose == "a stated purpose"

    def test_the_executor_exposes_a_copy_of_its_environment(
        self, executor: VerificationExecutor, environment: dict[str, str]
    ) -> None:
        exposed = dict(executor.environment)
        exposed["PATH"] = "/tampered"
        assert executor.environment["PATH"] == environment["PATH"]


class TestNoShellAndNoStringCommand:
    """Invariant 3, restated for this milestone's two modules."""

    def test_neither_module_passes_shell_true(self) -> None:
        for source in (VERIFICATION_SOURCE, RESULTS_SOURCE):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg == "shell":
                    assert isinstance(node.value, ast.Constant)
                    assert node.value.value is False, source

    def test_neither_module_names_a_shell_primitive(self) -> None:
        for source in (VERIFICATION_SOURCE, RESULTS_SOURCE):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in {"system", "popen", "getoutput"}, source

    def test_the_spawn_receives_a_list_never_a_string(self) -> None:
        tree = ast.parse(VERIFICATION_SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "run":
                continue
            assert node.args, "the vector is the first positional argument"
            assert not isinstance(node.args[0], ast.JoinedStr)
            assert not (
                isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            )

    def test_the_results_module_spawns_nothing_at_all(self) -> None:
        tree = ast.parse(RESULTS_SOURCE.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules.add(node.module)
        assert "subprocess" not in modules
        assert "os" not in modules

    def test_neither_module_imports_agentos_workflow(self) -> None:
        for source in (VERIFICATION_SOURCE, RESULTS_SOURCE):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module is not None:
                    assert not node.module.startswith("agentos_"), source
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("agentos_"), source


class TestNoBudgetAccountingInTheParsers:
    """This milestone's explicit exclusion: `results.py` parses, and counts nothing."""

    def test_the_module_never_names_a_counter(self) -> None:
        source = RESULTS_SOURCE.read_text(encoding="utf-8")
        for counter in (
            "review_attempts",
            "successful_review_rounds",
            "provider_failure_count",
            "correction_round",
            "closure_round",
        ):
            assert counter not in source, counter

    def test_the_module_never_increments_anything(self) -> None:
        tree = ast.parse(RESULTS_SOURCE.read_text(encoding="utf-8"))
        assert not [node for node in ast.walk(tree) if isinstance(node, ast.AugAssign)]


def test_every_required_symbol_of_this_milestone_is_present() -> None:
    """The milestone's `required_symbols`, checked as importable objects rather than as prose."""
    from ai_workflow_engine.milestone_runner import results, verification

    for module, names in (
        (
            verification,
            (
                "VerificationExecutor",
                "VerificationOutcome",
                "run_bounded_command",
                "evaluate_governance_gate",
                "GovernanceContradiction",
            ),
        ),
        (
            results,
            (
                "MachineResultGrammar",
                "extract_result_block",
                "parse_milestone_result",
                "parse_correction_result",
                "parse_review_result",
                "parse_closure_result",
                "MalformedResult",
            ),
        ),
    ):
        for name in names:
            assert hasattr(module, name), f"{module.__name__}.{name}"


def test_the_command_outcome_classifies_exactly_as_section_16_states() -> None:
    """One table, read straight off the contract: `0` passes, everything else fails."""
    assert CommandOutcome(exit_code=0).passed
    assert not CommandOutcome(exit_code=1).passed
    assert not CommandOutcome(exit_code=0, timed_out=True).passed
    assert not CommandOutcome(spawn_error="no such executable").passed
    assert not CommandOutcome().passed


def test_a_verification_outcome_reports_its_record_faithfully(
    executor: VerificationExecutor,
) -> None:
    outcome = executor.run(python_command("print('x')"), timeout_seconds=30)
    assert isinstance(outcome, VerificationOutcome)
    assert outcome.command == outcome.result.command
    assert outcome.passed is outcome.result.passed
    assert outcome.timed_out is outcome.result.timed_out
    assert outcome.exit_code == outcome.result.exit_code
