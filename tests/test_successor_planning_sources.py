"""AUTO-015 sections 8, 9 and 10: authoritative evidence readers and the catalog reader.

Every fixture here is a real governed repository on a real filesystem: real Markdown
governance documents, a real YAML catalog, a real handover manifest whose digests are really
computed, a real symlink where a symlink is under test, and the real `governance.parser` /
`governance.registry` / `handover.manifest` functions the readers compose. Nothing about the
behaviour under test is mocked -- a mirror-contradiction test really writes a contradicting
mirror, a stale-evidence test really deletes a completion report, and the content-hash tests
recompute every digest from the catalog's own YAML through `canonical_json` independently of
the reader, so a reader that agreed with itself but not with the file would fail.

The last test in the catalog group reads this repository's own authoritative catalog
(`AUTO-015-AUTHORITATIVE-CATALOG.yaml`) read-only, which is the one place the real,
hand-authored file is proven to parse and to reproduce all twelve of its own digests.
"""

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_workflow_engine.config import load_config
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.successor_planning.catalog import (
    CandidateFinding,
    CatalogSchemaError,
    candidate_content_hash,
    detect_duplicate_conflicts,
    read_catalog,
    resolve_dependency_graph,
    safe_message,
)
from ai_workflow_engine.successor_planning.models import Candidate, RepositoryIdentity
from ai_workflow_engine.successor_planning.snapshot import (
    AuthoritativeSourceError,
    SymlinkPolicyViolationError,
    resolve_repository_identity,
)
from ai_workflow_engine.successor_planning.sources import (
    REQUIRED_GOVERNANCE_CHECKS,
    EvidenceSet,
    EvidenceSources,
    PredecessorError,
    UnauthorizedSuccessorError,
    check_completion_claims,
    check_no_unauthorized_successor,
    detect_unauthorized_successors,
    read_completion_report,
    read_decision_log,
    read_evidence_set,
    read_handover_manifest,
    read_open_questions,
    reconcile_mirrors,
    resolve_predecessor,
    run_required_governance_checks,
    stale_completion_findings,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_CATALOG = (
    "docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml"
)

CATALOG_PATH = "docs/catalog.yaml"
DECISION_LOG_PATH = "docs/DECISION_LOG.md"
OPEN_QUESTIONS_PATH = "docs/OPEN_QUESTIONS.md"
REGISTRY_PATH = "docs/STAGE_REGISTRY.md"
REPORTS_PATH = "docs/reports"


# --------------------------------------------------------------------------------------
# Fixture construction
# --------------------------------------------------------------------------------------


def write(repository: Path, relative: str, text: str) -> None:
    target = repository / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def content_hash(entry: dict[str, Any]) -> str:
    """Recompute one entry's section 10.1 `content_hash` independently of the reader."""
    payload = {
        key: value
        for key, value in entry.items()
        if key not in {"content_hash", "lifecycle_status"}
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def candidate_entry(candidate_id: str = "alpha-candidate", **overrides: Any) -> dict[str, Any]:
    """One schema-valid catalog entry, with its own digest computed over its final fields."""
    entry: dict[str, Any] = {
        "candidate_id": candidate_id,
        "schema_version": "1.0",
        "title": f"Candidate {candidate_id}",
        "mission": "A bounded, plain-text mission statement carried as data, never directive.",
        "source_kind": "static_catalog",
        "source_reference": {
            "catalog_path": CATALOG_PATH,
            "catalog_version": "1.0",
            "entry_index": 0,
        },
        "mvp_relation": "inside",
        "dependencies": [],
        "blockers": [],
        "required_owner_decisions": [],
        "allowed_recommendation_status": True,
        "evidence_references": [],
    }
    entry.update(overrides)
    entry.setdefault("content_hash", content_hash(entry))
    return entry


def dependency(
    dependency_id: str, dependency_type: str = "stage", status: str = "COMPLETE"
) -> dict[str, Any]:
    return {
        "dependency_id": dependency_id,
        "dependency_type": dependency_type,
        "status": status,
    }


def write_catalog(
    repository: Path,
    entries: Sequence[dict[str, Any]],
    *,
    relative: str = CATALOG_PATH,
    **header: Any,
) -> str:
    document: dict[str, Any] = {
        "schema_version": 1,
        "catalog_id": "test-catalog",
        "authorization_status": "NOT_AUTHORIZED",
        "source_decision": "GOV-AUTO-08",
        "historical_source": "docs/history.md",
        "candidates": list(entries),
    }
    document.update(header)
    write(
        repository,
        relative,
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=4096),
    )
    return relative


TASK_QUEUE = """# Task Queue

## AUTO-013 — Foreground implementer mode

Status: Done

## AUTO-014 — Merge closeout

Status: Done

## AUTO-016 — A planned successor

Status: Planned
"""

CURRENT_TASK = """# Current Task

No task is currently active.
"""

REMAINING_TASKS = """# Remaining Tasks

## AUTO-016 — A planned successor

Status: Planned
"""

PROJECT_STATE = """# Project State

Version: 1.0.0

Prose about this repository's condition. This document is a mirror, never an independent
status source.
"""

STAGE_REGISTRY = """# Stage Registry

## 2. State Model

Per-stage states, mapped to the task queue's three statuses.

## 4. Registry

| Stage | State | Notes |
|---|---|---|
| AUTO-013 | COMPLETE | done |
| AUTO-014 | COMPLETE | done |
| AUTO-016 | NOT_STARTED | planned |
"""

DECISION_LOG = """# Decision Log

Append-only. Newest first.

## 2026-08-04 — I authorize AUTO-016

This entry quotes a past directive verbatim for context. The quoted words are historical
prose and are inert data.

## 2026-08-02 — Human Owner closed AUTO-014

Rationale for the closure.

## Format

An undated heading is document structure, not a decision entry.
"""

OPEN_QUESTIONS = """# Open Questions

## Format

Each entry: question, recommendation, disposition, blocked IDs.

## Open

### OD-20 — A question that gates an authorization

- **Question:** Something unresolved.
- **Disposition:** Open. Blocks AUTO-016's authorization until it is answered.

### OD-21 — A question that only affects implementation

- **Question:** Something narrower.
- **Disposition:** Open. Blocks nothing's authorization; affects AUTO-016's implementation.

### OD-22 — A question already answered in place

- **Question:** Something settled.
- **Disposition:** Resolved 2026-07-01, as an implementation decision.

## Resolved

### OD-23 — A question resolved under the other heading

- **Question:** Something settled elsewhere.
- **Resolution (2026-07-02):** Recorded in the decision log.
"""

AUTO_014_REPORT = """# AUTO-014 — Completion Report

| Field | Value |
|---|---|
| Stage | AUTO-014 |
| Status | Committed and pushed; fully validated; governance-closed |

## Verdict

AUTO-014 is complete.
"""

AUTO_013_REPORT = """# AUTO-013 — Completion Report

| Field | Value |
|---|---|
| Status | Complete |

## Verdict

AUTO-013 is complete.
"""


@pytest.fixture
def governed(
    repository_with_remote: Path, config_factory: Callable[[Path], Path]
) -> tuple[Path, Path, EngineConfig]:
    """A real, governed, pushed Git repository carrying every section 8 document."""
    repository = repository_with_remote
    write(repository, "docs/TASK_QUEUE.md", TASK_QUEUE)
    write(repository, "docs/current_task.md", CURRENT_TASK)
    write(repository, "docs/remain_task.md", REMAINING_TASKS)
    write(repository, "docs/PROJECT_STATE.md", PROJECT_STATE)
    write(repository, REGISTRY_PATH, STAGE_REGISTRY)
    write(repository, DECISION_LOG_PATH, DECISION_LOG)
    write(repository, OPEN_QUESTIONS_PATH, OPEN_QUESTIONS)
    write(repository, f"{REPORTS_PATH}/AUTO-013-completion-report.md", AUTO_013_REPORT)
    write(repository, f"{REPORTS_PATH}/AUTO-014-completion-report.md", AUTO_014_REPORT)
    write(repository, f"{REPORTS_PATH}/AUTO-015-contract-review.md", "# AUTO-015 Contract Review\n")

    config_path = config_factory(repository)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw["governance"]["registries"] = [REGISTRY_PATH]
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return repository, config_path, load_config(config_path)


@pytest.fixture
def identity(governed: tuple[Path, Path, EngineConfig]) -> RepositoryIdentity:
    _, config_path, config = governed
    return resolve_repository_identity(config, config_path)


@pytest.fixture
def sources() -> EvidenceSources:
    return EvidenceSources(
        decision_log=DECISION_LOG_PATH,
        open_questions=OPEN_QUESTIONS_PATH,
        completion_reports=REPORTS_PATH,
    )


@pytest.fixture
def evidence(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> EvidenceSet:
    _, _, config = governed
    return read_evidence_set(config, identity, sources)


def reload_evidence(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> EvidenceSet:
    _, _, config = governed
    return read_evidence_set(config, identity, sources)


def findings_by_code(findings: Sequence[CandidateFinding], code: str) -> list[CandidateFinding]:
    return [finding for finding in findings if finding.code == code]


# --------------------------------------------------------------------------------------
# Section 10.1 -- the catalog file's own schema
# --------------------------------------------------------------------------------------


def test_catalog_reads_entries_in_canonical_order(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    relative = write_catalog(
        repository, [candidate_entry("zeta-candidate"), candidate_entry("alpha-candidate")]
    )
    document = read_catalog(repository, relative)

    assert [candidate.candidate_id for candidate in document.candidates] == [
        "alpha-candidate",
        "zeta-candidate",
    ]
    assert document.findings == []
    assert document.entry_count == 2
    assert document.authorization_status == "NOT_AUTHORIZED"
    assert document.reference.path == relative
    assert (
        document.reference.sha256
        == hashlib.sha256((repository / relative).read_bytes()).hexdigest()
    )


def test_unknown_file_level_schema_version_is_whole_proposal(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    relative = write_catalog(repository, [candidate_entry()], schema_version=2)

    with pytest.raises(CatalogSchemaError) as excinfo:
        read_catalog(repository, relative)
    assert excinfo.value.code == "AUTHORITATIVE_SOURCE_MISSING"
    assert "schema_version" in str(excinfo.value)


def test_unknown_entry_schema_version_is_per_candidate(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    relative = write_catalog(
        repository,
        [
            candidate_entry("alpha-candidate"),
            candidate_entry("beta-candidate", schema_version="9.9"),
        ],
    )
    document = read_catalog(repository, relative)

    assert [candidate.candidate_id for candidate in document.candidates] == ["alpha-candidate"]
    (finding,) = document.findings
    assert finding.code == "MALFORMED_CANDIDATE"
    assert finding.candidate_id == "beta-candidate"
    assert "9.9" in finding.message


def test_unrecognized_entry_field_is_a_schema_error(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    entry = candidate_entry("beta-candidate")
    entry["unexpected_field"] = "never silently ignored"
    relative = write_catalog(repository, [candidate_entry("alpha-candidate"), entry])
    document = read_catalog(repository, relative)

    assert [candidate.candidate_id for candidate in document.candidates] == ["alpha-candidate"]
    (finding,) = document.findings
    assert finding.code == "MALFORMED_CANDIDATE"
    assert "unexpected_field" in finding.message


def test_unrecognized_file_level_field_refuses_the_catalog(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    relative = write_catalog(repository, [candidate_entry()], unexpected_header="no")

    with pytest.raises(CatalogSchemaError):
        read_catalog(repository, relative)


def test_authored_lifecycle_status_is_refused(governed: tuple[Path, Path, EngineConfig]) -> None:
    repository, _, _ = governed
    entry = candidate_entry("beta-candidate")
    entry["lifecycle_status"] = "eligible"
    relative = write_catalog(repository, [entry])
    document = read_catalog(repository, relative)

    assert document.candidates == []
    (finding,) = document.findings
    assert finding.code == "MALFORMED_CANDIDATE"
    assert "lifecycle_status" in finding.message


def test_catalog_cannot_declare_itself_authorized(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    relative = write_catalog(repository, [candidate_entry()], authorization_status="AUTHORIZED")

    with pytest.raises(CatalogSchemaError):
        read_catalog(repository, relative)


def test_content_hash_is_re_derived_not_trusted(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    entry = candidate_entry("beta-candidate")
    entry["content_hash"] = "0" * 64
    relative = write_catalog(repository, [entry])
    document = read_catalog(repository, relative)

    assert document.candidates == []
    (finding,) = document.findings
    assert finding.code == "MALFORMED_CANDIDATE"
    assert "content_hash" in finding.message


def test_symlinked_catalog_is_refused(governed: tuple[Path, Path, EngineConfig]) -> None:
    repository, _, _ = governed
    write_catalog(repository, [candidate_entry()])
    link = repository / "docs" / "catalog-link.yaml"
    link.symlink_to(repository / CATALOG_PATH)

    with pytest.raises(SymlinkPolicyViolationError):
        read_catalog(repository, "docs/catalog-link.yaml")


def test_missing_catalog_is_authoritative_source_missing(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed

    with pytest.raises(AuthoritativeSourceError) as excinfo:
        read_catalog(repository, "docs/absent-catalog.yaml")
    assert excinfo.value.code == "AUTHORITATIVE_SOURCE_MISSING"


# --------------------------------------------------------------------------------------
# Section 10.2 -- unknown types, duplicates, conflicts
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"source_kind": "bounded_derived"}, "source_kind"),
        ({"dependencies": [dependency("AUTO-014", dependency_type="program")]}, "dependency_type"),
        (
            {
                "blockers": [
                    {"blocker_id": "OD-20", "blocker_type": "policy_note", "live_status": "Open"}
                ]
            },
            "blocker_type",
        ),
    ],
)
def test_unknown_types_exclude_the_candidate(
    governed: tuple[Path, Path, EngineConfig], overrides: dict[str, Any], needle: str
) -> None:
    repository, _, _ = governed
    relative = write_catalog(
        repository,
        [candidate_entry("alpha-candidate"), candidate_entry("beta-candidate", **overrides)],
    )
    document = read_catalog(repository, relative)

    assert [candidate.candidate_id for candidate in document.candidates] == ["alpha-candidate"]
    (finding,) = document.findings
    assert finding.code == "UNKNOWN_CANDIDATE_TYPE"
    assert finding.candidate_id == "beta-candidate"
    assert needle in finding.message


def test_identical_duplicate_definitions_deduplicate_silently(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    entry = candidate_entry("alpha-candidate")
    relative = write_catalog(repository, [entry, dict(entry)])
    document = read_catalog(repository, relative)

    assert [candidate.candidate_id for candidate in document.candidates] == ["alpha-candidate"]
    assert document.findings == []
    assert document.entry_count == 2


def test_conflicting_duplicate_definitions_list_both_verbatim(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    first = candidate_entry("alpha-candidate")
    second = candidate_entry("alpha-candidate", title="A different title entirely")
    relative = write_catalog(repository, [first, second, candidate_entry("beta-candidate")])
    document = read_catalog(repository, relative)

    assert [candidate.candidate_id for candidate in document.candidates] == ["beta-candidate"]
    (finding,) = document.findings
    assert finding.code == "DUPLICATE_CANDIDATE_CONFLICT"
    assert finding.candidate_id == "alpha-candidate"
    assert [definition.title for definition in finding.definitions] == [
        first["title"],
        second["title"],
    ]
    assert [definition.content_hash for definition in finding.definitions] == [
        first["content_hash"],
        second["content_hash"],
    ]


def test_duplicate_detection_is_independent_of_the_reader(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    relative = write_catalog(repository, [candidate_entry("alpha-candidate")])
    (candidate,) = read_catalog(repository, relative).candidates
    conflicting = candidate.model_copy(update={"title": "Another title", "content_hash": "a" * 64})

    resolution = detect_duplicate_conflicts([candidate, conflicting])

    assert resolution.candidates == []
    assert [finding.code for finding in resolution.findings] == ["DUPLICATE_CANDIDATE_CONFLICT"]
    assert len(resolution.findings[0].definitions) == 2


# --------------------------------------------------------------------------------------
# Section 10.2 -- the dependency graph
# --------------------------------------------------------------------------------------


def read_candidates(repository: Path, entries: Sequence[dict[str, Any]]) -> list[Candidate]:
    relative = write_catalog(repository, entries)
    document = read_catalog(repository, relative)
    assert document.findings == []
    return document.candidates


def test_dependency_cycle_names_every_participant(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    candidates = read_candidates(
        repository,
        [
            candidate_entry(
                "alpha-candidate", dependencies=[dependency("beta-candidate", "capability", "x")]
            ),
            candidate_entry(
                "beta-candidate", dependencies=[dependency("alpha-candidate", "capability", "x")]
            ),
            candidate_entry("gamma-candidate"),
        ],
    )

    resolution = resolve_dependency_graph(candidates)

    assert resolution.cycles == [["alpha-candidate", "beta-candidate"]]
    assert {(edge.candidate_id, edge.depends_on) for edge in resolution.edges} == {
        ("alpha-candidate", "beta-candidate"),
        ("beta-candidate", "alpha-candidate"),
    }
    cycle_findings = findings_by_code(resolution.findings, "DEPENDENCY_CYCLE")
    assert [finding.candidate_id for finding in cycle_findings] == [
        "alpha-candidate",
        "beta-candidate",
    ]
    for finding in cycle_findings:
        assert finding.cycle == ["alpha-candidate", "beta-candidate"]
        assert "alpha-candidate" in finding.message and "beta-candidate" in finding.message
    # The candidate outside the cycle is untouched, and no edge was dropped to break the cycle.
    assert all(finding.candidate_id != "gamma-candidate" for finding in resolution.findings)
    assert resolution.unmet == []


def test_self_dependency_is_a_cycle(governed: tuple[Path, Path, EngineConfig]) -> None:
    repository, _, _ = governed
    candidates = read_candidates(
        repository,
        [
            candidate_entry(
                "alpha-candidate", dependencies=[dependency("alpha-candidate", "capability", "x")]
            )
        ],
    )

    resolution = resolve_dependency_graph(candidates)

    assert resolution.cycles == [["alpha-candidate"]]
    assert [finding.code for finding in resolution.findings] == ["DEPENDENCY_CYCLE"]


def test_missing_dependency_is_named(governed: tuple[Path, Path, EngineConfig]) -> None:
    repository, _, _ = governed
    candidates = read_candidates(
        repository,
        [
            candidate_entry(
                "alpha-candidate",
                dependencies=[
                    dependency("AUTO-014"),
                    dependency("AUTO-999"),
                    dependency("prompt-renderer", "subsystem", "existing"),
                ],
            )
        ],
    )

    resolution = resolve_dependency_graph(
        candidates, known_stages={"AUTO-014"}, known_subsystems={"prompt-renderer"}
    )

    assert [(item.dependency_id, item.dependency_type) for item in resolution.unmet] == [
        ("AUTO-999", "stage")
    ]
    assert resolution.unmet[0].candidate_id == "alpha-candidate"
    assert resolution.unmet[0].declared_status == "COMPLETE"
    assert resolution.cycles == []


def test_empty_known_sets_report_every_dependency_unmet(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    candidates = read_candidates(
        repository, [candidate_entry("alpha-candidate", dependencies=[dependency("AUTO-014")])]
    )

    assert [item.dependency_id for item in resolve_dependency_graph(candidates).unmet] == [
        "AUTO-014"
    ]


def test_dependency_type_must_match_the_known_set(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    candidates = read_candidates(
        repository,
        [candidate_entry("alpha-candidate", dependencies=[dependency("AUTO-014", "subsystem")])],
    )

    resolution = resolve_dependency_graph(candidates, known_stages={"AUTO-014"})

    assert [item.dependency_id for item in resolution.unmet] == ["AUTO-014"]


# --------------------------------------------------------------------------------------
# The real repository's own authoritative catalog
# --------------------------------------------------------------------------------------


def test_real_authoritative_catalog_parses_and_reproduces_every_hash() -> None:
    document = read_catalog(REPOSITORY_ROOT, AUTHORITATIVE_CATALOG)

    assert document.catalog_id == "auto-015-successor-catalog"
    assert document.authorization_status == "NOT_AUTHORIZED"
    assert document.findings == []
    assert document.entry_count == len(document.candidates) == 12

    raw = yaml.safe_load((REPOSITORY_ROOT / AUTHORITATIVE_CATALOG).read_text(encoding="utf-8"))
    declared = {entry["candidate_id"]: entry["content_hash"] for entry in raw["candidates"]}
    independent = {entry["candidate_id"]: content_hash(entry) for entry in raw["candidates"]}
    through_reader = {
        candidate.candidate_id: candidate_content_hash(candidate)
        for candidate in document.candidates
    }
    assert declared == independent == through_reader
    assert all("lifecycle_status" not in entry for entry in raw["candidates"])
    assert all(candidate.lifecycle_status is None for candidate in document.candidates)


def test_real_authoritative_catalog_has_no_dependency_cycle() -> None:
    document = read_catalog(REPOSITORY_ROOT, AUTHORITATIVE_CATALOG)

    resolution = resolve_dependency_graph(document.candidates)

    assert resolution.cycles == []
    assert {(edge.candidate_id, edge.depends_on) for edge in resolution.edges} == {
        ("codex-correction-mode", "reviewer-mode"),
        ("multi-task-orchestration", "runtime-daemon-scheduler"),
    }


# --------------------------------------------------------------------------------------
# Section 8 -- the evidence set
# --------------------------------------------------------------------------------------


def test_evidence_set_reads_every_section_8_source(evidence: EvidenceSet) -> None:
    assert evidence.task_queue.reference.path == "docs/TASK_QUEUE.md"
    assert evidence.task_queue.status_of("AUTO-014") is not None
    assert [document.reference.path for document in evidence.registries] == [REGISTRY_PATH]
    assert [report.stage_id for report in evidence.completion_reports] == ["AUTO-013", "AUTO-014"]
    assert evidence.completion_report("AUTO-014") is not None
    assert evidence.completion_report("AUTO-014").title == "AUTO-014 — Completion Report"
    assert evidence.completion_report("AUTO-014").status == (
        "Committed and pushed; fully validated; governance-closed"
    )
    assert evidence.unreadable_completion_reports == []
    assert [entry.date for entry in evidence.decision_log.entries] == ["2026-08-04", "2026-08-02"]
    assert [fact.name for fact in evidence.project_state.facts] == ["version"]
    assert evidence.project_state.facts[0].value == "1.0.0"
    assert [question.question_id for question in evidence.open_questions.questions] == [
        "OD-20",
        "OD-21",
        "OD-22",
        "OD-23",
    ]
    assert evidence.handover.consistent is True

    paths = [reference.path for reference in evidence.manifest]
    assert paths == sorted(paths)
    assert "handover/PROJECT_CHECKSUM.md" in paths
    assert f"{REPORTS_PATH}/AUTO-014-completion-report.md" in paths
    assert f"{REPORTS_PATH}/AUTO-015-contract-review.md" not in paths


def test_evidence_manifest_digests_are_over_normalized_content(
    governed: tuple[Path, Path, EngineConfig], evidence: EvidenceSet
) -> None:
    repository, _, _ = governed
    for reference in evidence.manifest:
        data = (repository / reference.path).read_bytes()
        normalized = data.decode("utf-8").replace("\r\n", "\n")
        assert reference.sha256 == hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert reference.size == len(data)


def test_historical_directive_prose_is_inert_data(evidence: EvidenceSet) -> None:
    (authorization_entry,) = [
        entry for entry in evidence.decision_log.entries if "authorize" in entry.title
    ]

    assert authorization_entry.title == "I authorize AUTO-016"
    # The quoted directive changes nothing: AUTO-016 is still not a registered, complete stage.
    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, "AUTO-016", identity=evidence.identity)
    assert excinfo.value.code == "PREDECESSOR_NOT_COMPLETE"


def test_open_questions_distinguish_authorization_gates(evidence: EvidenceSet) -> None:
    questions = {question.question_id: question for question in evidence.open_questions.questions}

    assert questions["OD-20"].status == "Open"
    assert questions["OD-20"].blocks_authorization_of == ["AUTO-016"]
    # "blocks nothing's authorization ... affects AUTO-016's implementation" is the weaker
    # category and gates no authorization.
    assert questions["OD-21"].blocks_authorization_of == []
    assert questions["OD-22"].status == "Resolved"
    assert questions["OD-22"].section == "Open"
    assert questions["OD-23"].status == "Resolved"
    assert questions["OD-23"].section == "Resolved"


def test_open_question_without_a_disposition_is_read_as_open(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    write(
        repository,
        OPEN_QUESTIONS_PATH,
        "# Open Questions\n\n## Open\n\n### OD-30 — Unanswered\n\n- **Question:** No answer.\n",
    )

    (question,) = read_open_questions(repository, OPEN_QUESTIONS_PATH).questions

    assert question.status == "Open"
    assert question.disposition == "(no disposition recorded)"


def test_completion_report_heading_must_match_its_filename(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, config = governed
    write(
        repository,
        f"{REPORTS_PATH}/AUTO-013-completion-report.md",
        "# AUTO-999 — Completion Report\n\nMismatched heading.\n",
    )

    with pytest.raises(AuthoritativeSourceError):
        read_completion_report(repository, f"{REPORTS_PATH}/AUTO-013-completion-report.md")

    evidence = read_evidence_set(config, identity, sources)
    assert [report.stage_id for report in evidence.completion_reports] == ["AUTO-014"]
    (unreadable,) = evidence.unreadable_completion_reports
    assert unreadable.stage_id == "AUTO-013"
    assert unreadable.code == "AUTHORITATIVE_SOURCE_MISSING"


def test_symlinked_completion_report_is_not_downgraded_to_unreadable(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, config = governed
    link = repository / REPORTS_PATH / "AUTO-017-completion-report.md"
    link.symlink_to(repository / REPORTS_PATH / "AUTO-014-completion-report.md")

    # A symlinked authoritative input is a whole-proposal policy violation, never a
    # per-candidate "this one report was unreadable" record.
    with pytest.raises(SymlinkPolicyViolationError):
        read_evidence_set(config, identity, sources)


def test_decision_log_ignores_undated_headings(governed: tuple[Path, Path, EngineConfig]) -> None:
    repository, _, _ = governed

    document = read_decision_log(repository, DECISION_LOG_PATH)

    assert [entry.title for entry in document.entries] == [
        "I authorize AUTO-016",
        "Human Owner closed AUTO-014",
    ]
    assert all(entry.line > 1 for entry in document.entries)


# --------------------------------------------------------------------------------------
# Section 8 item 10 -- handover evidence is required
# --------------------------------------------------------------------------------------


def test_handover_evidence_is_required_not_optional(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, config = governed
    (repository / config.handover.manifest).unlink()

    with pytest.raises(AuthoritativeSourceError) as excinfo:
        read_evidence_set(config, identity, sources)
    assert excinfo.value.code == "AUTHORITATIVE_SOURCE_MISSING"


def test_handover_digest_mismatch_is_recorded_not_silently_resolved(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, config = governed
    (repository / "handover/PROJECT_HANDOVER.md").write_text("tampered\n", encoding="utf-8")

    evidence = read_evidence_set(config, identity, sources)

    assert evidence.handover.consistent is False
    mismatched = [record for record in evidence.handover.records if not record.consistent]
    assert [record.path for record in mismatched] == ["handover/PROJECT_HANDOVER.md"]
    assert mismatched[0].actual_digest != mismatched[0].expected_digest


def test_handover_manifest_file_must_exist(governed: tuple[Path, Path, EngineConfig]) -> None:
    repository, _, config = governed
    (repository / "handover/BOOTSTRAP_PROMPT.md").unlink()

    with pytest.raises(AuthoritativeSourceError):
        read_handover_manifest(repository, config.handover.manifest, config.handover.files)


# --------------------------------------------------------------------------------------
# Section 4 items 2-3, section 8 -- mirror and registry reconciliation
# --------------------------------------------------------------------------------------


def test_consistent_evidence_reconciles(evidence: EvidenceSet) -> None:
    reconciliation = reconcile_mirrors(evidence)

    assert reconciliation.consistent is True
    assert reconciliation.failure_code is None
    assert reconciliation.current_tasks == []
    assert reconciliation.registry_paths == [REGISTRY_PATH]


def test_mirror_disagreement_is_mirror_contradiction(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        "docs/remain_task.md",
        "# Remaining Tasks\n\n## AUTO-016 — A planned successor\n\nStatus: Current\n",
    )

    reconciliation = reconcile_mirrors(reload_evidence(governed, identity, sources))

    assert reconciliation.consistent is False
    assert reconciliation.failure_code == "MIRROR_CONTRADICTION"
    (disagreement,) = reconciliation.mirror_disagreements
    assert disagreement.identifier == "AUTO-016"
    assert disagreement.path == "docs/remain_task.md"
    assert disagreement.observed_status == "Current"
    assert disagreement.authoritative_status == "Planned"
    assert reconciliation.registry_disagreements == []


def test_current_task_mirror_set_is_compared(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        "docs/TASK_QUEUE.md",
        TASK_QUEUE.replace("## AUTO-016 — A planned successor\n\nStatus: Planned", ""),
    )
    write(
        repository,
        "docs/remain_task.md",
        "# Remaining Tasks\n\nNothing planned.\n",
    )
    write(
        repository,
        "docs/current_task.md",
        "# Current Task\n\n## AUTO-016 — A planned successor\n\nStatus: Current\n",
    )

    reconciliation = reconcile_mirrors(reload_evidence(governed, identity, sources))

    assert reconciliation.failure_code == "MIRROR_CONTRADICTION"
    assert any(
        disagreement.identifier == "(Current set)"
        for disagreement in reconciliation.mirror_disagreements
    )


def test_registry_queue_disagreement_is_recorded_never_resolved_by_precedence(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        REGISTRY_PATH,
        STAGE_REGISTRY.replace("| AUTO-016 | NOT_STARTED |", "| AUTO-016 | IN_PROGRESS |"),
    )

    evidence = reload_evidence(governed, identity, sources)
    reconciliation = reconcile_mirrors(evidence)

    assert reconciliation.failure_code == "MIRROR_CONTRADICTION"
    assert reconciliation.mirror_disagreements == []
    (disagreement,) = reconciliation.registry_disagreements
    assert disagreement.identifier == "AUTO-016"
    assert disagreement.observed_status == "IN_PROGRESS"
    assert disagreement.authoritative_status == "Planned"
    # The disagreement itself travels with the evidence manifest; neither source is discarded.
    assert disagreement.path in [reference.path for reference in evidence.manifest]
    assert evidence.task_queue.status_of("AUTO-016") is not None


def test_unrecognized_registry_state_is_a_disagreement(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(repository, REGISTRY_PATH, STAGE_REGISTRY.replace("NOT_STARTED", "MAYBE_LATER"))

    reconciliation = reconcile_mirrors(reload_evidence(governed, identity, sources))

    assert reconciliation.failure_code == "MIRROR_CONTRADICTION"
    assert reconciliation.registry_disagreements[0].observed_status == "MAYBE_LATER"


def test_conflicting_current_task_is_reported(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository, "docs/TASK_QUEUE.md", TASK_QUEUE.replace("Status: Planned", "Status: Current")
    )
    write(
        repository,
        "docs/current_task.md",
        "# Current Task\n\n## AUTO-016 — A planned successor\n\nStatus: Current\n",
    )
    write(
        repository,
        "docs/remain_task.md",
        "# Remaining Tasks\n\n## AUTO-016 — A planned successor\n\nStatus: Current\n",
    )
    write(repository, REGISTRY_PATH, STAGE_REGISTRY.replace("NOT_STARTED", "IN_PROGRESS"))

    reconciliation = reconcile_mirrors(reload_evidence(governed, identity, sources))

    assert reconciliation.current_tasks == ["AUTO-016"]
    assert reconciliation.consistent is True


# --------------------------------------------------------------------------------------
# Section 4.1 -- predecessor resolution
# --------------------------------------------------------------------------------------


def test_valid_predecessor_resolves(evidence: EvidenceSet, identity: RepositoryIdentity) -> None:
    resolved = resolve_predecessor(evidence, "AUTO-014", identity=identity)

    assert resolved.stage_id == "AUTO-014"
    assert resolved.registry_evidence.registry_status == "COMPLETE"
    assert resolved.registry_evidence.registry_reference.path == REGISTRY_PATH
    assert [reference.path for reference in resolved.completion_evidence] == [
        f"{REPORTS_PATH}/AUTO-014-completion-report.md"
    ]
    assert resolved.reconciliation.task_queue_status == "Done"
    assert resolved.reconciliation.reconciled_status == "COMPLETE"
    assert resolved.reconciliation.consistent is True
    assert resolved.repository_identity == identity


@pytest.mark.parametrize("argument", [None, "", "   "])
def test_missing_predecessor(
    evidence: EvidenceSet, identity: RepositoryIdentity, argument: str | None
) -> None:
    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, argument, identity=identity)
    assert excinfo.value.code == "MISSING_PREDECESSOR"


@pytest.mark.parametrize(
    "argument", ["auto-014", "AUTO-14", "AUTO-0014", "GOV-AUTO-08", "AUTO-014 "]
)
def test_invalid_predecessor_id(
    evidence: EvidenceSet, identity: RepositoryIdentity, argument: str
) -> None:
    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, argument, identity=identity)
    assert excinfo.value.code == "INVALID_PREDECESSOR_ID"


def test_unregistered_predecessor(evidence: EvidenceSet, identity: RepositoryIdentity) -> None:
    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, "AUTO-777", identity=identity)
    assert excinfo.value.code == "PREDECESSOR_NOT_REGISTERED"


@pytest.mark.parametrize("state", ["IN_PROGRESS", "SUPERSEDED", "MAYBE_LATER"])
def test_predecessor_not_complete(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
    state: str,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        REGISTRY_PATH,
        STAGE_REGISTRY.replace("| AUTO-014 | COMPLETE |", f"| AUTO-014 | {state} |"),
    )

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(
            reload_evidence(governed, identity, sources), "AUTO-014", identity=identity
        )
    assert excinfo.value.code == "PREDECESSOR_NOT_COMPLETE"
    assert state in str(excinfo.value)


def test_predecessor_status_contradiction_between_registry_and_queue(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        "docs/TASK_QUEUE.md",
        TASK_QUEUE.replace(
            "## AUTO-014 — Merge closeout\n\nStatus: Done",
            "## AUTO-014 — Merge closeout\n\nStatus: Current",
        ),
    )

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(
            reload_evidence(governed, identity, sources), "AUTO-014", identity=identity
        )
    assert excinfo.value.code == "PREDECESSOR_STATUS_CONTRADICTION"


def test_predecessor_status_contradiction_between_queue_and_mirror(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        "docs/remain_task.md",
        "# Remaining Tasks\n\n## AUTO-014 — Merge closeout\n\nStatus: Planned\n",
    )

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(
            reload_evidence(governed, identity, sources), "AUTO-014", identity=identity
        )
    assert excinfo.value.code == "PREDECESSOR_STATUS_CONTRADICTION"


def test_predecessor_absent_from_the_queue_is_incomplete(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        "docs/TASK_QUEUE.md",
        TASK_QUEUE.replace("## AUTO-014 — Merge closeout\n\nStatus: Done\n\n", ""),
    )

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(
            reload_evidence(governed, identity, sources), "AUTO-014", identity=identity
        )
    assert excinfo.value.code == "PREDECESSOR_INCOMPLETE"


def test_predecessor_completion_evidence_missing(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    (repository / f"{REPORTS_PATH}/AUTO-014-completion-report.md").unlink()

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(
            reload_evidence(governed, identity, sources), "AUTO-014", identity=identity
        )
    assert excinfo.value.code == "PREDECESSOR_COMPLETION_EVIDENCE_MISSING"


def test_predecessor_completion_evidence_invalid(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        f"{REPORTS_PATH}/AUTO-014-completion-report.md",
        "No heading at all, so this report binds to no stage.\n",
    )

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(
            reload_evidence(governed, identity, sources), "AUTO-014", identity=identity
        )
    assert excinfo.value.code == "PREDECESSOR_EVIDENCE_INVALID"


def test_predecessor_repository_mismatch(
    evidence: EvidenceSet, identity: RepositoryIdentity
) -> None:
    other = identity.model_copy(update={"configured_repository_id": "a-different-repository"})

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, "AUTO-014", identity=other)
    assert excinfo.value.code == "PREDECESSOR_REPOSITORY_MISMATCH"


def test_predecessor_baseline_mismatch(evidence: EvidenceSet, identity: RepositoryIdentity) -> None:
    other = identity.model_copy(update={"head_sha": "0" * 40})

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, "AUTO-014", identity=other)
    assert excinfo.value.code == "PREDECESSOR_BASELINE_MISMATCH"


def test_predecessor_branch_change_is_a_baseline_mismatch(
    evidence: EvidenceSet, identity: RepositoryIdentity
) -> None:
    other = identity.model_copy(update={"branch": "some-other-branch"})

    with pytest.raises(PredecessorError) as excinfo:
        resolve_predecessor(evidence, "AUTO-014", identity=other)
    assert excinfo.value.code == "PREDECESSOR_BASELINE_MISMATCH"


# --------------------------------------------------------------------------------------
# Section 8 -- per-candidate completion evidence
# --------------------------------------------------------------------------------------


def test_completion_claims_without_a_report_are_per_candidate(
    governed: tuple[Path, Path, EngineConfig], evidence: EvidenceSet
) -> None:
    repository, _, _ = governed
    candidates = read_candidates(
        repository,
        [
            candidate_entry("alpha-candidate", dependencies=[dependency("AUTO-014")]),
            candidate_entry("beta-candidate", dependencies=[dependency("AUTO-777")]),
            candidate_entry(
                "gamma-candidate", dependencies=[dependency("AUTO-016", status="Planned")]
            ),
        ],
    )

    claims = check_completion_claims(evidence, candidates)

    assert [(claim.candidate_id, claim.stage_id, claim.code) for claim in claims] == [
        ("alpha-candidate", "AUTO-014", None),
        ("beta-candidate", "AUTO-777", "STALE_COMPLETION_EVIDENCE"),
    ]
    assert claims[0].report is not None
    assert claims[0].report.path == f"{REPORTS_PATH}/AUTO-014-completion-report.md"

    findings = stale_completion_findings(claims)
    assert [(finding.code, finding.candidate_id) for finding in findings] == [
        ("STALE_COMPLETION_EVIDENCE", "beta-candidate")
    ]
    assert "AUTO-777" in findings[0].message


def test_unreadable_completion_report_does_not_satisfy_a_claim(
    governed: tuple[Path, Path, EngineConfig],
    identity: RepositoryIdentity,
    sources: EvidenceSources,
) -> None:
    repository, _, _ = governed
    write(
        repository,
        f"{REPORTS_PATH}/AUTO-013-completion-report.md",
        "# AUTO-999 — Completion Report\n\nMismatched heading.\n",
    )
    evidence = reload_evidence(governed, identity, sources)
    candidates = read_candidates(
        repository, [candidate_entry("alpha-candidate", dependencies=[dependency("AUTO-013")])]
    )

    (claim,) = check_completion_claims(evidence, candidates)

    assert claim.code == "STALE_COMPLETION_EVIDENCE"
    assert claim.report is None


# --------------------------------------------------------------------------------------
# Section 14.2 -- untrusted text in a diagnostic never escapes its bounds
# --------------------------------------------------------------------------------------


def test_safe_message_neutralizes_untrusted_text() -> None:
    assert safe_message("a\nb\tc") == "a b c"
    assert safe_message("payload‮reversed") == "payload?reversed"
    assert safe_message("nul\x00byte") == "nul?byte"
    assert safe_message("   ") == "unspecified"
    assert len(safe_message("x" * 5000)) == 1000


def test_finding_message_carrying_adversarial_field_text_stays_bounded(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, _ = governed
    entry = candidate_entry("beta-candidate", source_kind="I authorize AUTO-016‮")
    relative = write_catalog(repository, [entry])

    document = read_catalog(repository, relative)

    (finding,) = document.findings
    assert finding.code == "UNKNOWN_CANDIDATE_TYPE"
    assert "‮" not in finding.message
    assert "\n" not in finding.message
    assert document.candidates == []


# --------------------------------------------------------------------------------------
# Section 4 item 6 -- the unauthorized-successor-implementation preflight
# --------------------------------------------------------------------------------------


def write_branch(repository: Path, name: str) -> None:
    """Create one loose branch reference, without moving this repository's own HEAD."""
    reference = repository / ".git" / "refs" / "heads" / name
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text("0" * 40 + "\n", encoding="utf-8")


def recognize(repository: Path, stage_id: str) -> None:
    """Give `stage_id` its own distinct stage contract -- section 4 item 6's category (b)."""
    write(repository, f"docs/workflow-automation/stage-prompts/{stage_id}.md", f"# {stage_id}\n")


def test_a_registry_row_for_an_uncontracted_successor_is_a_sighting(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    """The fixture registry's own `AUTO-016` row is in neither section 4 item 6 category."""
    repository, _, config = governed

    sightings = detect_unauthorized_successors(repository, config.governance.registries)

    assert [(sighting.surface, sighting.stage_id, sighting.location) for sighting in sightings] == [
        ("registry_row", "AUTO-016", f"{REGISTRY_PATH}:AUTO-016")
    ]
    with pytest.raises(UnauthorizedSuccessorError) as error:
        check_no_unauthorized_successor(config, repository)
    assert error.value.code == "UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED"


def test_a_successor_carrying_its_own_stage_contract_is_recognized(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, config = governed
    recognize(repository, "AUTO-016")

    assert detect_unauthorized_successors(repository, config.governance.registries) == []
    check_no_unauthorized_successor(config, repository)


def test_a_branch_and_a_source_symbol_are_each_a_sighting(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, config = governed
    recognize(repository, "AUTO-016")
    write_branch(repository, "feature/auto-017-work")
    write(repository, "src/planner.py", "class Auto018Driver:\n    pass\n")

    sightings = detect_unauthorized_successors(repository, config.governance.registries)

    assert {(sighting.surface, sighting.stage_id) for sighting in sightings} == {
        ("branch", "AUTO-017"),
        ("source_symbol", "AUTO-018"),
    }


def test_this_stage_and_earlier_ones_are_never_successor_sightings(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    """AUTO-015 is this implementation itself, and an earlier stage is not a successor at all."""
    repository, _, config = governed
    recognize(repository, "AUTO-016")
    write_branch(repository, "feature/auto-015-successor-planning")
    write_branch(repository, "feature/gov-auto-07-drift")
    write(repository, "src/successor_planning.py", "class SuccessorPlanner:\n    pass\n")

    assert detect_unauthorized_successors(repository, config.governance.registries) == []


def test_prose_naming_a_later_stage_is_never_a_sighting(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    """Section 4 item 6 names branches, symbols and rows -- not documents that mention a stage."""
    repository, _, config = governed
    recognize(repository, "AUTO-016")
    write(repository, "src/planner.py", '"""Groundwork for AUTO-017."""\n\nVALUE = 1\n')

    assert detect_unauthorized_successors(repository, config.governance.registries) == []


# --------------------------------------------------------------------------------------
# Section 4 item 4 -- the four mandated `workflowctl verify` governance checks
# --------------------------------------------------------------------------------------


def test_the_four_mandated_checks_are_exactly_the_contract_list() -> None:
    assert REQUIRED_GOVERNANCE_CHECKS == ("task-state", "governance", "registries", "handover")


def test_a_governed_repository_passes_all_four_checks(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    _, _, config = governed

    assert run_required_governance_checks(config) == []


def test_a_governance_fact_disagreement_fails_the_governance_check(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    """The reviewer's own example: two configured paths disagreeing on one governance fact."""
    repository, _, config = governed
    write(repository, "docs/CHATGPT_CONTEXT.md", "# Context\n\nVersion: 9.9.9\n")

    failures = run_required_governance_checks(config)

    assert [failure.check_name for failure in failures] == ["governance"]
    assert failures[0].finding_code == "governance_fact_mismatch"
    assert failures[0].failure_code == "MIRROR_CONTRADICTION"


def test_a_tampered_handover_file_fails_the_handover_check(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    """Section 8 item 10: handover evidence is required, never merely corroborating."""
    repository, _, config = governed
    write(repository, "handover/PROJECT_HANDOVER.md", "tampered\n")

    failures = run_required_governance_checks(config)

    assert failures
    assert {failure.check_name for failure in failures} == {"handover"}
    assert {failure.failure_code for failure in failures} == {"MIRROR_CONTRADICTION"}


def test_an_unreadable_handover_manifest_is_an_absent_authoritative_source(
    governed: tuple[Path, Path, EngineConfig],
) -> None:
    repository, _, config = governed
    (repository / "handover/PROJECT_CHECKSUM.md").unlink()

    failures = run_required_governance_checks(config)

    assert [failure.failure_code for failure in failures] == ["AUTHORITATIVE_SOURCE_MISSING"]
