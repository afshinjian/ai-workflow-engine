"""Tests for the Contract Skills (`SKILL_CONTRACTS.md` §3) against fixture stage contracts and
fixture registries, plus the traversal/symlink rejection the stage contract requires."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from agentos_workflow.skills import FailureKind, RetryClassification
from agentos_workflow.skills.contract import (
    calculate_contract_hash,
    detect_future_stage_work,
    locate_stage_contract,
    parse_stage_metadata,
    validate_allowed_paths,
    validate_stage_ordering,
)

CONTRACT = """# AUTO-003 — Deterministic Repository and Validation Skills

| Field | Value |
|---|---|
| **Stage** | AUTO-003 · Role: Engine implementation session |
| **Branch** | `feature/auto-003-repository-validation-skills` |
| **Commit message** | `feat(workflow): add skills (AUTO-003)` |
| **Report** | `docs/reports/workflow-automation/AUTO-003-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

## Canonical Prompt
Body text.
"""

REGISTRY = """# Registry fixture

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| AUTO-001 | Contracts | Docs | COMPLETE | `a` | `AUTO-001.md` |
| AUTO-002 | Orchestrator | Impl | COMPLETE | `b` | `AUTO-002.md` |
| AUTO-003 | Skills | Impl | IN_PROGRESS | `c` | `AUTO-003.md` |
| AUTO-004 | Providers | Impl | NOT_STARTED | `d` | `AUTO-004.md` |
"""


@pytest.fixture
def contracts(tmp_path: Path) -> Path:
    directory = tmp_path / "stage-prompts"
    directory.mkdir()
    (directory / "AUTO-003.md").write_text(CONTRACT, encoding="utf-8")
    return directory


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    path = tmp_path / "STAGE_REGISTRY.md"
    path.write_text(REGISTRY, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------------------------
# locate_stage_contract
# ---------------------------------------------------------------------------------------------


def test_locate_stage_contract_finds_the_contract(contracts: Path) -> None:
    result = locate_stage_contract(stage_id="AUTO-003", contract_directory=contracts)
    assert result.ok and result.value is not None
    assert result.value.name == "AUTO-003.md"


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "AUTO-003/../../x",
        "/etc/passwd",
        "..",
        ".",
        "AUTO_003",
        "auto-003",
        "AUTO-003.md",
        "",
        "AUTO-003\x00",
    ],
)
def test_locate_stage_contract_rejects_traversal_and_malformed_ids(
    contracts: Path, hostile: str
) -> None:
    """The stage ID is validated before it is ever joined to a path."""
    result = locate_stage_contract(stage_id=hostile, contract_directory=contracts)
    assert not result.ok and result.error is not None
    assert result.error.kind in (FailureKind.UNSAFE_INPUT, FailureKind.NOT_FOUND)


def test_locate_stage_contract_rejects_a_symlink_escaping_the_directory(
    contracts: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text(CONTRACT, encoding="utf-8")
    link = contracts / "AUTO-009.md"
    link.symlink_to(outside)
    result = locate_stage_contract(stage_id="AUTO-009", contract_directory=contracts)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_locate_stage_contract_reports_a_missing_contract(contracts: Path) -> None:
    result = locate_stage_contract(stage_id="AUTO-007", contract_directory=contracts)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.NOT_FOUND


# ---------------------------------------------------------------------------------------------
# parse_stage_metadata
# ---------------------------------------------------------------------------------------------


def test_parse_stage_metadata_extracts_every_field(contracts: Path) -> None:
    result = parse_stage_metadata(contracts / "AUTO-003.md")
    assert result.ok and result.value is not None
    metadata = result.value
    assert metadata.stage_id == "AUTO-003"
    assert metadata.title == "Deterministic Repository and Validation Skills"
    assert metadata.role == "Engine implementation session"
    assert metadata.branch == "feature/auto-003-repository-validation-skills"
    assert metadata.commit_message == "feat(workflow): add skills (AUTO-003)"
    assert metadata.report_path.endswith("AUTO-003-completion-report.md")


def test_parse_stage_metadata_tolerates_formatting_variation(tmp_path: Path) -> None:
    """Padding, bolding, and backticks are formatting; they must not change the parse."""
    variant = tmp_path / "AUTO-005.md"
    variant.write_text(
        "# AUTO-005 — Agents\n\n"
        "|Field|Value|\n|:--|:--|\n"
        "|  **Stage**  |   AUTO-005 · Role:  Engine implementation session  |\n"
        "|Branch|feature/auto-005-agents|\n"
        "|**Commit message**|`feat: agents`|\n"
        "|Report|`docs/r.md`|\n",
        encoding="utf-8",
    )
    result = parse_stage_metadata(variant)
    assert result.ok and result.value is not None
    assert result.value.stage_id == "AUTO-005"
    assert result.value.branch == "feature/auto-005-agents"
    assert result.value.role == "Engine implementation session"


def test_parse_stage_metadata_fails_on_a_missing_required_field(tmp_path: Path) -> None:
    """A missing `Branch` must fail, never default to "no branch restriction"."""
    incomplete = tmp_path / "AUTO-006.md"
    incomplete.write_text(
        "# AUTO-006 — PR\n\n| Field | Value |\n|---|---|\n| **Stage** | AUTO-006 |\n",
        encoding="utf-8",
    )
    result = parse_stage_metadata(incomplete)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT
    assert "branch" in result.error.detail


def test_parse_stage_metadata_fails_without_a_heading(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    path.write_text("| **Stage** | AUTO-003 |\n", encoding="utf-8")
    assert not parse_stage_metadata(path).ok


def test_parse_stage_metadata_rejects_a_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.md"
    real.write_text(CONTRACT, encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    result = parse_stage_metadata(link)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.UNSAFE_INPUT


def test_parse_stage_metadata_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_bytes(b"# AUTO-003 \xff\xfe\n")
    result = parse_stage_metadata(path)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT


# ---------------------------------------------------------------------------------------------
# calculate_contract_hash
# ---------------------------------------------------------------------------------------------


def test_calculate_contract_hash_matches_raw_bytes(contracts: Path) -> None:
    path = contracts / "AUTO-003.md"
    result = calculate_contract_hash(path)
    assert result.ok and result.value is not None
    assert result.value.sha256 == sha256(path.read_bytes()).hexdigest()
    assert result.value.stage_id == "AUTO-003"
    assert result.value.size_bytes == len(path.read_bytes())


def test_calculate_contract_hash_is_deterministic(contracts: Path) -> None:
    path = contracts / "AUTO-003.md"
    assert calculate_contract_hash(path).unwrap().sha256 == (
        calculate_contract_hash(path).unwrap().sha256
    )


def test_calculate_contract_hash_changes_on_whitespace_only_edits(contracts: Path) -> None:
    """The hash binds the authorization; a whitespace change still changes what was authorized."""
    path = contracts / "AUTO-003.md"
    before = calculate_contract_hash(path).unwrap().sha256
    path.write_bytes(path.read_bytes() + b"\n")
    assert calculate_contract_hash(path).unwrap().sha256 != before


def test_calculate_contract_hash_rejects_a_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.md"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    result = calculate_contract_hash(link)
    assert not result.ok and result.error is not None
    assert result.error.retry_classification is RetryClassification.NON_RETRYABLE


def test_calculate_contract_hash_reports_a_missing_file(tmp_path: Path) -> None:
    result = calculate_contract_hash(tmp_path / "absent.md")
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.NOT_FOUND


# ---------------------------------------------------------------------------------------------
# validate_stage_ordering
# ---------------------------------------------------------------------------------------------


def test_validate_stage_ordering_accepts_the_next_stage(registry: Path) -> None:
    result = validate_stage_ordering(stage_id="AUTO-003", stage_registry=registry)
    assert result.ok and result.value == 3


def test_validate_stage_ordering_refuses_a_stage_whose_predecessor_is_unfinished(
    tmp_path: Path,
) -> None:
    path = tmp_path / "R.md"
    path.write_text(
        "| Stage | Title | Role | State | Branch | Prompt |\n|---|---|---|---|---|---|\n"
        "| AUTO-001 | a | r | COMPLETE | b | p |\n"
        "| AUTO-002 | b | r | IN_PROGRESS | b | p |\n"
        "| AUTO-003 | c | r | NOT_STARTED | b | p |\n",
        encoding="utf-8",
    )
    result = validate_stage_ordering(stage_id="AUTO-003", stage_registry=path)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.PRECONDITION
    assert "AUTO-002" in result.error.detail


def test_validate_stage_ordering_treats_superseded_as_terminal(tmp_path: Path) -> None:
    """`STAGE_REGISTRY.md` §2: superseded is administratively closed, so it does not block."""
    path = tmp_path / "R.md"
    path.write_text(
        "| Stage | Title | Role | State | Branch | Prompt |\n|---|---|---|---|---|---|\n"
        "| AUTO-001 | a | r | SUPERSEDED | b | p |\n"
        "| AUTO-002 | b | r | COMPLETE | b | p |\n",
        encoding="utf-8",
    )
    assert validate_stage_ordering(stage_id="AUTO-002", stage_registry=path).ok


def test_validate_stage_ordering_rejects_a_duplicate_registry_row(tmp_path: Path) -> None:
    path = tmp_path / "R.md"
    path.write_text(
        "| Stage | Title | Role | State | Branch | Prompt |\n|---|---|---|---|---|---|\n"
        "| AUTO-001 | a | r | COMPLETE | b | p |\n"
        "| AUTO-001 | a | r | NOT_STARTED | b | p |\n",
        encoding="utf-8",
    )
    result = validate_stage_ordering(stage_id="AUTO-001", stage_registry=path)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT


def test_validate_stage_ordering_reports_an_unlisted_stage(registry: Path) -> None:
    result = validate_stage_ordering(stage_id="AUTO-009", stage_registry=registry)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.NOT_FOUND


def test_validate_stage_ordering_reports_an_empty_registry(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    path.write_text("# No table here\n", encoding="utf-8")
    result = validate_stage_ordering(stage_id="AUTO-001", stage_registry=path)
    assert not result.ok and result.error is not None
    assert result.error.kind is FailureKind.MALFORMED_OUTPUT


def test_validate_stage_ordering_works_against_the_real_registry() -> None:
    """The parser must handle this repository's actual registry, not just fixtures."""
    real = Path(__file__).resolve().parents[2] / "docs/workflow-automation/STAGE_REGISTRY.md"
    result = validate_stage_ordering(stage_id="AUTO-003", stage_registry=real)
    assert result.ok, f"{result.error}"


# ---------------------------------------------------------------------------------------------
# validate_allowed_paths
# ---------------------------------------------------------------------------------------------


def test_validate_allowed_paths_accepts_paths_inside_scope() -> None:
    result = validate_allowed_paths(
        changed_files=("agentos_workflow/skills/repository.py", "agentos_workflow/tests/t.py"),
        allowed_paths=("agentos_workflow/skills/**", "agentos_workflow/tests/**"),
        forbidden_paths=("src/**",),
    )
    assert result.ok and result.value is not None
    assert result.value.passed is True
    assert result.value.violations == ()


def test_validate_allowed_paths_flags_unmatched_paths() -> None:
    """Scope is an allowlist: an unanticipated path is scope creep, not a pass."""
    result = validate_allowed_paths(
        changed_files=("pyproject.toml",),
        allowed_paths=("agentos_workflow/**",),
        forbidden_paths=(),
    )
    verdict = result.unwrap()
    assert verdict.passed is False
    assert verdict.violations[0].reason == "matches no allowed path pattern"


def test_forbidden_wins_over_allowed_on_overlap() -> None:
    """A broad allowance must never silently re-open a narrow prohibition."""
    result = validate_allowed_paths(
        changed_files=("docs/secret/keys.md",),
        allowed_paths=("docs/**",),
        forbidden_paths=("docs/secret/**",),
    )
    verdict = result.unwrap()
    assert verdict.passed is False
    assert verdict.violations[0].reason == "matches a forbidden path pattern"


def test_double_star_matches_zero_directories() -> None:
    result = validate_allowed_paths(
        changed_files=("docs/x.md",), allowed_paths=("docs/**",), forbidden_paths=()
    )
    assert result.unwrap().passed is True


def test_validate_allowed_paths_matching_is_case_sensitive() -> None:
    """A forbidden `docs/SECRET/**` must not be evadable by spelling it `docs/secret/`."""
    result = validate_allowed_paths(
        changed_files=("docs/secret/x.md",),
        allowed_paths=("docs/**",),
        forbidden_paths=("docs/SECRET/**",),
    )
    verdict = result.unwrap()
    # It does not match the forbidden rule, but it is still judged against the allowlist rather
    # than silently passing on a case technicality.
    assert verdict.passed is True  # `docs/**` legitimately allows it
    result2 = validate_allowed_paths(
        changed_files=("docs/SECRET/x.md",),
        allowed_paths=("docs/**",),
        forbidden_paths=("docs/SECRET/**",),
    )
    assert result2.unwrap().passed is False


@pytest.mark.parametrize("hostile", ["../outside.py", "/etc/passwd", "a/../../b", "with\x00null"])
def test_validate_allowed_paths_rejects_unsafe_paths(hostile: str) -> None:
    result = validate_allowed_paths(
        changed_files=(hostile,), allowed_paths=("**",), forbidden_paths=()
    )
    verdict = result.unwrap()
    assert verdict.passed is False
    assert "not a safe repository-relative path" in verdict.violations[0].reason


def test_validate_allowed_paths_normalizes_unicode() -> None:
    """A decomposed spelling is the same file; comparing raw code points would let it slip past."""
    decomposed = "docs/secret/über.md"  # u + COMBINING DIAERESIS
    precomposed = "docs/secret/über.md"  # LATIN SMALL LETTER U WITH DIAERESIS
    assert decomposed != precomposed, "fixture must use genuinely different code points"

    result = validate_allowed_paths(
        changed_files=(decomposed,),
        allowed_paths=("docs/**",),
        forbidden_paths=(precomposed,),
    )
    assert result.unwrap().passed is False, "decomposed path must still hit the forbidden rule"


def test_validate_allowed_paths_reports_every_violation() -> None:
    result = validate_allowed_paths(
        changed_files=("a.py", "b.py", "src/c.py"),
        allowed_paths=("docs/**",),
        forbidden_paths=("src/**",),
    )
    assert len(result.unwrap().violations) == 3


def test_validate_allowed_paths_with_no_changes_passes() -> None:
    result = validate_allowed_paths(changed_files=(), allowed_paths=(), forbidden_paths=())
    assert result.unwrap().passed is True


# ---------------------------------------------------------------------------------------------
# detect_future_stage_work
# ---------------------------------------------------------------------------------------------


def test_detect_future_stage_work_flags_a_later_stages_deliverable() -> None:
    result = detect_future_stage_work(
        changed_files=("agentos_workflow/providers/claude.py",),
        current_stage_allowed_paths=("agentos_workflow/skills/**",),
        later_stage_paths={"AUTO-004": ("agentos_workflow/providers/**",)},
    )
    verdict = result.unwrap()
    assert verdict.passed is False
    assert "AUTO-004" in verdict.violations[0].reason


def test_detect_future_stage_work_passes_for_in_scope_work() -> None:
    result = detect_future_stage_work(
        changed_files=("agentos_workflow/skills/repository.py",),
        current_stage_allowed_paths=("agentos_workflow/skills/**",),
        later_stage_paths={"AUTO-004": ("agentos_workflow/providers/**",)},
    )
    assert result.unwrap().passed is True


def test_detect_future_stage_work_flags_ambiguous_overlap() -> None:
    """A path claimed by both this stage and a later one is exactly what needs a human look."""
    result = detect_future_stage_work(
        changed_files=("agentos_workflow/shared.py",),
        current_stage_allowed_paths=("agentos_workflow/**",),
        later_stage_paths={"AUTO-005": ("agentos_workflow/**",)},
    )
    verdict = result.unwrap()
    assert verdict.passed is False
    assert "both" in verdict.violations[0].reason


def test_detect_future_stage_work_names_every_claiming_stage() -> None:
    result = detect_future_stage_work(
        changed_files=("agentos_workflow/agents/git.py",),
        current_stage_allowed_paths=("agentos_workflow/skills/**",),
        later_stage_paths={
            "AUTO-005": ("agentos_workflow/agents/**",),
            "AUTO-006": ("agentos_workflow/agents/git.py",),
        },
    )
    reason = result.unwrap().violations[0].reason
    assert "AUTO-005" in reason and "AUTO-006" in reason


def test_detect_future_stage_work_rejects_unsafe_paths() -> None:
    result = detect_future_stage_work(
        changed_files=("../escape.py",),
        current_stage_allowed_paths=("**",),
        later_stage_paths={},
    )
    assert result.unwrap().passed is False
