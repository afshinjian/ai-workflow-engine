"""AUTO-016 section 27: Tier 1 disposable-repository acceptance, the packaging proofs, Tier 2.

Everything in Tier 1 is real. The repository is a real `git init` worktree with a real remote and a
real commit, created under `tmp_path` and discarded with it. The plan is three real milestone files
under the external plan root DEC-016-005 fixes. The run directory, the run lock, the transcripts and
the verification commands are the production ones. The provider is a scripted **fake**: a real
Python program, spawned through the production
:class:`~...providers.base.ProviderInvoker` by a test-owned adapter with its own argv -- so no
`claude` and no `codex` process is ever spawned, which :class:`TestNoAutomaticGitMutation` proves at
the process level rather than asserting by convention.

Four assertions ride along with **every** test in this module, as autouse fixtures, because
section 27 requires them of every acceptance run rather than of a chosen case:

* the AUTO-015 prototype at `~/.local/share/auto015-runner/` is byte-, size- and mtime-identical
  before and after, and nothing in the module opens it (DEC-016-006);
* this repository's own governance state is untouched -- the suite writes only under `tmp_path` and
  a redirected `HOME`;
* `HEAD` and the reflog of the disposable repository are whatever the test left them, and no
  mutating Git or `gh` process was spawned;
* no plan file is created inside the disposable repository and no directory scan of the worktree
  occurs (DEC-016-005).

Tier 2 lives at the bottom under the existing `live_cli` marker, excluded from the default run by
`addopts`. It is written here and executed only during an authorized implementation or verification
phase; nothing in the default suite spawns a real provider.
"""

import ast
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from ai_workflow_engine.milestone_runner.application import (
    MilestoneRunnerApplication,
    ProviderBinding,
    RunRefused,
    record_latest_run,
)
from ai_workflow_engine.milestone_runner.config import RunnerConfig, load_runner_config
from ai_workflow_engine.milestone_runner.lock import RunLock
from ai_workflow_engine.milestone_runner.models import (
    STATE_SCHEMA_VERSION,
    Finding,
    FindingSeverity,
    FindingStatus,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
    RecoveryCommand,
    RunRecord,
    RunStatus,
    StopReason,
)
from ai_workflow_engine.milestone_runner.plan import MilestonePlanLoader
from ai_workflow_engine.milestone_runner.providers.base import (
    ProviderAdapter,
    ProviderRequest,
    transcript_label_for,
)
from ai_workflow_engine.milestone_runner.recovery import (
    RECONSTRUCTED_FROM_VERIFIED_EVIDENCE,
    RecoveryRefused,
)
from ai_workflow_engine.milestone_runner.state import RunStateStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "ai_workflow_engine" / "milestone_runner"

#: The AUTO-015 prototype, resolved from the real home at import time -- before any fixture
#: redirects `HOME` -- so the non-interference proof is about the prototype that actually exists.
PROTOTYPE_ROOT = Path("~/.local/share/auto015-runner").expanduser()

#: The disposable repository every AUTO-016 suite pins, so one artifact root serves them all.
REMOTE = "https://github.com/example/demo-repo.git"
IDENTITY = "demo-repo--2059e82cffa9"
STAGE_ID = "AUTO-099"
CONTRACT_PATH = "docs/workflow-automation/stage-prompts/AUTO-099.md"
CONTRACT_TEXT = "# AUTO-099 -- a disposable contract for a disposable repository\n"

#: The three milestones section 27 requires the Tier 1 plan to carry, and the one file each owns.
MILESTONES: tuple[str, ...] = ("AUTO-099-M01", "AUTO-099-M02", "AUTO-099-M03")
MILESTONE_FILES: Mapping[str, str] = {
    "AUTO-099-M01": "src/demo/one.py",
    "AUTO-099-M02": "src/demo/two.py",
    "AUTO-099-M03": "src/demo/three.py",
}

#: The governance documents the disposable repository carries, so "no governance file is touched"
#: is an assertion about real files rather than about their absence.
GOVERNANCE_DOCUMENTS: tuple[str, ...] = (
    "docs/TASK_QUEUE.md",
    "docs/current_task.md",
    "docs/DECISION_LOG.md",
    "docs/PROJECT_STATE.md",
    "docs/workflow-automation/STAGE_REGISTRY.md",
)

#: Section 16's five governance checks, each emitting the machine-readable document the gate reads.
GOVERNANCE_CHECKS: tuple[str, ...] = ("git", "task-state", "governance", "registries", "handover")

#: The argv element meaning "no milestone" / "nothing to write". A sentinel rather than an empty
#: string because `ProviderRequest` refuses an empty argument outright.
NONE_SENTINEL = "-"


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def porcelain(repository: Path) -> list[str]:
    """Every path `git status --porcelain` reports, which is what section 27 asserts on."""
    output = git(repository, "status", "--porcelain")
    return sorted(line[3:] for line in output.splitlines() if line)


def worktree_digest(repository: Path) -> dict[str, str]:
    """Every tracked and untracked file's digest, excluding Git's own directory."""
    return {
        path.relative_to(repository).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(repository.rglob("*"))
        if path.is_file() and ".git/" not in path.relative_to(repository).as_posix() + "/"
    }


def governance_snapshot(repository: Path) -> dict[str, tuple[bytes, int]]:
    return {
        document: (
            (repository / document).read_bytes(),
            (repository / document).stat().st_mtime_ns,
        )
        for document in GOVERNANCE_DOCUMENTS
    }


def governance_command(name: str) -> list[str]:
    document = json.dumps({"check_name": name, "status": "PASS", "findings": []})
    return [sys.executable, "-c", f"print({document!r})"]


#: A verification command that passes once and fails afterwards. It carries a purpose that is not
#: one of section 16's five governance checks, so it runs only when the *full* set runs -- at
#: `FINAL_VERIFYING` and again at `CLOSURE_VERIFYING` -- and never as part of a boundary's
#: governance gate. That is what makes "the verification set did not pass after the correction
#: round" reachable without making any earlier gate flaky.
CLOSURE_CANARY = """\
import pathlib, sys

counter = pathlib.Path(sys.argv[1])
seen = int(counter.read_text(encoding="utf-8")) if counter.is_file() else 0
counter.write_text(str(seen + 1), encoding="utf-8")
raise SystemExit(0 if seen == 0 else 1)
"""


def closure_canary_verification(tmp_path: Path) -> dict[str, Any]:
    """The `verification` section with the canary appended to the final set."""
    counter = tmp_path / "closure-canary.count"
    canary = tmp_path / "closure_canary.py"
    canary.write_text(CLOSURE_CANARY, encoding="utf-8")
    return {
        "focused": [],
        "final": [
            {"command": governance_command(name), "timeout_seconds": 120, "purpose": name}
            for name in GOVERNANCE_CHECKS
        ]
        + [
            {
                "command": [sys.executable, str(canary), str(counter)],
                "timeout_seconds": 120,
                "purpose": "closure canary",
            }
        ],
    }


def repository_evidence(repository: Path) -> tuple[str, str, str]:
    """`HEAD`, the reflog and the remote refs -- section 27's Git-level proof, in one tuple."""
    return (
        git(repository, "rev-parse", "HEAD"),
        git(repository, "reflog", "--format=%H %gs"),
        git(repository, "for-each-ref", "refs/remotes"),
    )


# --------------------------------------------------------------------------------------
# The section 18 blocks the scripted provider returns
# --------------------------------------------------------------------------------------


def milestone_block(
    milestone_id: str, changed_paths: Sequence[str], status: str = "COMPLETE"
) -> str:
    return (
        "AUTO016_MILESTONE_RESULT\n"
        f"milestone: {milestone_id}\n"
        f"status: {status}\n"
        f"changed_paths: [{', '.join(changed_paths)}]\n"
        "END_AUTO016_MILESTONE_RESULT\n"
    )


def review_block(*, verdict: str = "APPROVED", blockers: Sequence[Mapping[str, str]] = ()) -> str:
    body = ["AUTO016_REVIEW_RESULT", f"verdict: {verdict}"]
    if blockers:
        body.append("blockers:")
        for blocker in blockers:
            body.append(f"  - id: {blocker['id']}")
            body.append(f"    severity: {blocker['severity']}")
            body.append(f"    title: {blocker['title']}")
            body.append(f"    summary: {blocker['summary']}")
    else:
        body.append("blockers: []")
    body.append("deferred: []")
    body.append("END_AUTO016_REVIEW_RESULT")
    return "\n".join(body) + "\n"


def correction_block(*, status: str = "COMPLETE", addressed: Sequence[str] = ()) -> str:
    body = ["AUTO016_CORRECTION_RESULT", f"status: {status}"]
    if addressed:
        body.append("findings_addressed:")
        for identifier in addressed:
            body.append(f"  - id: {identifier}")
            body.append("    resolution: The correction round addressed it.")
    else:
        body.append("findings_addressed: []")
    body.append("changed_paths: []")
    body.append("END_AUTO016_CORRECTION_RESULT")
    return "\n".join(body) + "\n"


def closure_block(rulings: Mapping[str, str]) -> str:
    body = ["AUTO016_CLOSURE_RESULT", "findings:"]
    for identifier, status in rulings.items():
        body.append(f"  - id: {identifier}")
        body.append(f"    status: {status}")
        body.append("    reason: Closure verification ruled on it.")
    body.append("END_AUTO016_CLOSURE_RESULT")
    return "\n".join(body) + "\n"


HIGH_BLOCKER: Mapping[str, str] = {
    "id": "R-1",
    "severity": "HIGH",
    "title": "The reviewer found one blocking defect",
    "summary": "It is a real blocker the correction round has to address.",
}


def happy_path_script() -> dict[str, Any]:
    """The scripted provider for a run that goes exactly as section 5 describes."""
    return {
        "results": {
            **{
                f"IMPLEMENTATION:{milestone}": milestone_block(
                    milestone, [MILESTONE_FILES[milestone]]
                )
                for milestone in MILESTONES
            },
            "REVIEW": review_block(),
        },
        "writes": {
            milestone: {MILESTONE_FILES[milestone]: f"# written for {milestone}\n"}
            for milestone in MILESTONES
        },
    }


# --------------------------------------------------------------------------------------
# The scripted fake provider: a real program, spawned through the production invoker
# --------------------------------------------------------------------------------------

FAKE_PROVIDER_SCRIPT = """\
import json, os, pathlib, sys

script = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
role, milestone = sys.argv[2], sys.argv[3]
sys.stdin.read()

for target, payload in script.get("writes", {}).get(milestone, {}).items():
    path = pathlib.Path(os.getcwd()) / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")

results = script["results"]
sys.stdout.write(results.get(role + ":" + milestone, results.get(role, "")))
sys.stderr.write(script.get("stderr", ""))
raise SystemExit(int(script.get("exit_codes", {}).get(role, 0)))
"""

SLOW_PROVIDER_SCRIPT = """\
import sys, time

sys.stdin.read()
sys.stdout.write("the provider started\\n")
sys.stdout.flush()
time.sleep(120)
"""


class ScriptedAdapter(ProviderAdapter):
    """A provider adapter this suite owns, driving a real subprocess with its own fixed argv.

    It is a real adapter: the prompt goes to the child's stdin, the transcripts are written through
    section 17a's boundary, and the failure class is fixed at invocation time by the production
    invoker. What it is not is either shipped adapter, so nothing here spawns `claude` or `codex`.
    """

    name: ClassVar[str] = "fake"
    roles: ClassVar[frozenset[ProviderRole]] = frozenset(ProviderRole)

    def __init__(self, program: Path, script: Path, *, timeout_seconds: int = 120) -> None:
        self._program = program
        self._script = script
        self._timeout_seconds = timeout_seconds

    def build_request(
        self, *, role: ProviderRole, prompt: str, milestone_id: str | None = None
    ) -> ProviderRequest:
        self._require_role(role)
        return ProviderRequest(
            provider=self.name,
            role=role,
            argv=[
                sys.executable,
                str(self._program),
                str(self._script),
                role.value,
                milestone_id or NONE_SENTINEL,
            ],
            prompt=prompt,
            timeout_seconds=self._timeout_seconds,
            transcript_label=transcript_label_for(self.name, role),
            milestone_id=milestone_id,
        )


# --------------------------------------------------------------------------------------
# Fixtures: a real repository, a real external plan root, a real configuration
# --------------------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    repository = tmp_path / "worktree"
    (repository / "docs" / "workflow-automation" / "stage-prompts").mkdir(parents=True)
    (repository / "src" / "demo").mkdir(parents=True)
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "Milestone Runner Tests")
    git(repository, "remote", "add", "origin", REMOTE)
    (repository / CONTRACT_PATH).write_text(CONTRACT_TEXT, encoding="utf-8")
    for document in GOVERNANCE_DOCUMENTS:
        (repository / document).write_text(
            f"# {Path(document).name}\n\n| Row | Status |\n|---|---|\n"
            f"| {STAGE_ID} | AUTHORIZED |\n",
            encoding="utf-8",
        )
    (repository / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "initial")
    return repository


def write_plan(
    root: Path, *, disjoint_scopes: bool = False, failing_focused: Sequence[str] = ()
) -> Path:
    """Write the three-milestone plan into `root`, and return it.

    Each milestone's `allowed_files` carries its own file **and every earlier milestone's**. That
    shape is the one the accumulating reading of section 15 check 2 required, and it is kept as
    the default because most of this suite is about something other than scope: section 4 item 6
    is satisfied either way, because the union of the three `allowed_files` sets equals
    `required_coverage` exactly in both shapes.

    `disjoint_scopes=True` writes the other shape -- strictly disjoint per-milestone scopes --
    which is what finding GOV-AUTO-11-F1 was about and what
    :class:`TestPerMilestoneScopeAgainstAnAccumulatingTree` now drives to the commit gate.
    """
    root.mkdir(parents=True, exist_ok=True)
    for index, milestone in enumerate(MILESTONES):
        scope = (
            [MILESTONE_FILES[milestone]]
            if disjoint_scopes
            else [MILESTONE_FILES[earlier] for earlier in MILESTONES[: index + 1]]
        )
        root.joinpath(f"{milestone}.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "milestone_id": milestone,
                    "title": f"Milestone {index + 1} of the disposable plan",
                    "objective": "Write one file inside this milestone's own scope.",
                    "depends_on": list(MILESTONES[:index][-1:]),
                    "contract_sections": ["section 5"],
                    "allowed_files": scope,
                    "forbidden_files": ["everything else"],
                    "required_symbols": [f"demo.{milestone.lower()}"],
                    "explicit_exclusions": ["Do not touch anything else."],
                    "acceptance_criteria": ["The file exists."],
                    "focused_verification": [
                        {
                            "command": [
                                sys.executable,
                                "-c",
                                "raise SystemExit(1)" if milestone in failing_focused else "pass",
                            ],
                            "purpose": "a real command",
                        }
                    ],
                    "completion_evidence": ["The focused command passes."],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return root


@pytest.fixture
def plan_root(isolated_home: Path) -> Path:
    """The three-milestone plan, at the external default root DEC-016-005 fixes."""
    return write_plan(isolated_home / ".ai-workflow-engine" / "milestone-runs" / IDENTITY / "plans")


@pytest.fixture
def contract_sha256(worktree: Path) -> str:
    return hashlib.sha256((worktree / CONTRACT_PATH).read_bytes()).hexdigest()


@pytest.fixture
def baseline_sha(worktree: Path) -> str:
    return git(worktree, "rev-parse", "HEAD")


ConfigFactory = Callable[..., Path]


@pytest.fixture
def config_factory(
    tmp_path: Path,
    worktree: Path,
    plan_root: Path,
    baseline_sha: str,
    contract_sha256: str,
) -> ConfigFactory:
    def factory(**overrides: Any) -> Path:
        document: dict[str, Any] = {
            "schema_version": 1,
            "repository": {
                "root": str(worktree),
                "identity": IDENTITY,
                "expected_branch": "main",
                "baseline_sha": baseline_sha,
                "conda_environment": "ai-workflow-engine",
            },
            "stage": {
                "stage_id": STAGE_ID,
                "contract_path": CONTRACT_PATH,
                "contract_sha256": contract_sha256,
            },
            "allowlist": {
                "allowed_paths": sorted(MILESTONE_FILES.values()),
                "forbidden_paths": ["self-governance.yaml", "docs/**"],
                "required_coverage": sorted(MILESTONE_FILES.values()),
            },
            "review_policy": {
                "max_full_reviews": 1,
                "max_correction_rounds": 1,
                "max_closure_reviews": 1,
                "max_blockers": 3,
                "blocking_severities": ["CRITICAL", "HIGH"],
                "defer_severities": ["MEDIUM", "LOW"],
            },
            "providers": {
                "claude": {"executable": "claude", "timeout_seconds": 60},
                "codex": {"executable": "codex", "timeout_seconds": 60},
                "allowed_environment_variables": ["PATH", "HOME"],
            },
            "verification": {
                "focused": [],
                "final": [
                    {"command": governance_command(name), "timeout_seconds": 120, "purpose": name}
                    for name in GOVERNANCE_CHECKS
                ],
            },
        }
        for section, values in overrides.items():
            if isinstance(values, dict):
                document[section] = {**document.get(section, {}), **values}
            else:
                document[section] = values
        path = tmp_path / f"runner-{len(list(tmp_path.glob('runner-*.yaml')))}.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
        return path

    return factory


@pytest.fixture
def config(config_factory: ConfigFactory) -> RunnerConfig:
    return load_runner_config(config_factory())


@pytest.fixture
def program(tmp_path: Path) -> Path:
    path = tmp_path / "fake_provider.py"
    path.write_text(FAKE_PROVIDER_SCRIPT, encoding="utf-8")
    return path


ProviderFactory = Callable[..., ProviderBinding]


@pytest.fixture
def providers_for(tmp_path: Path, program: Path) -> ProviderFactory:
    """Bind a scripted provider to both roles, from a script document the test supplies."""
    counter = {"value": 0}

    def factory(script: Mapping[str, Any] | None = None, **overrides: Any) -> ProviderBinding:
        document: dict[str, Any] = dict(script or happy_path_script())
        document.update(overrides)
        counter["value"] += 1
        path = tmp_path / f"provider-script-{counter['value']}.json"
        path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
        adapter = ScriptedAdapter(program, path)
        return ProviderBinding(implementation=adapter, review=adapter)

    return factory


ApplicationFactory = Callable[..., MilestoneRunnerApplication]


@pytest.fixture
def application_factory(
    config_factory: ConfigFactory, providers_for: ProviderFactory
) -> ApplicationFactory:
    def factory(
        *,
        script: Mapping[str, Any] | None = None,
        providers: ProviderBinding | None = None,
        config_path: Path | None = None,
        config_overrides: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> MilestoneRunnerApplication:
        path = config_path or config_factory(**dict(config_overrides or {}))
        return MilestoneRunnerApplication(
            load_runner_config(path),
            providers=providers or providers_for(script),
            **kwargs,
        )

    return factory


# --------------------------------------------------------------------------------------
# The per-run assertions section 27 requires of every acceptance case
# --------------------------------------------------------------------------------------


def prototype_snapshot() -> dict[str, tuple[int, str, int]]:
    """Every prototype file's size, content digest and mtime (DEC-016-006, section 27)."""
    if not PROTOTYPE_ROOT.is_dir():
        return {}
    snapshot: dict[str, tuple[int, str, int]] = {}
    for path in sorted(PROTOTYPE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        snapshot[path.relative_to(PROTOTYPE_ROOT).as_posix()] = (
            stat.st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            stat.st_mtime_ns,
        )
    return snapshot


@pytest.fixture(autouse=True)
def _prototype_unchanged() -> Iterator[None]:
    """Section 27: every acceptance run asserts the prototype is byte-identical before and after."""
    before = prototype_snapshot()
    yield
    assert prototype_snapshot() == before


@pytest.fixture(autouse=True)
def _no_prototype_access(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """DEC-016-006: no acceptance case reads prototype state as input, and none writes there."""
    real_open = os.open

    def guarded(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        assert str(PROTOTYPE_ROOT) not in str(path), f"the prototype was opened at {path}"
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    yield


@dataclass
class SpawnLog:
    """Every process this test spawned, as argv, for section 27's process-level proof."""

    calls: list[list[str]] = field(default_factory=list)

    def record(self, args: Any) -> None:
        if isinstance(args, str | bytes | os.PathLike):
            self.calls.append([os.fspath(args) if not isinstance(args, str) else args])
            return
        self.calls.append([str(argument) for argument in args])

    def clear(self) -> None:
        self.calls.clear()

    def matching(self, *tokens: str) -> list[list[str]]:
        """Every recorded vector carrying all of `tokens`, in order-insensitive membership."""
        return [call for call in self.calls if set(tokens) <= set(call)]

    @property
    def provider_processes(self) -> list[list[str]]:
        return [
            call for call in self.calls if call and Path(call[0]).name in {"claude", "codex", "gh"}
        ]

    @property
    def mutating_git(self) -> list[list[str]]:
        mutating = {
            "commit",
            "push",
            "add",
            "reset",
            "restore",
            "clean",
            "stash",
            "rebase",
            "checkout",
            "switch",
            "merge",
            "cherry-pick",
            "revert",
            "fetch",
            "pull",
        }
        return [
            call
            for call in self.calls
            if call and Path(call[0]).name == "git" and mutating & set(call)
        ]


@pytest.fixture
def spawns(worktree: Path, monkeypatch: pytest.MonkeyPatch) -> SpawnLog:
    """Record every spawned process. Depends on `worktree` so the fixture's own setup commits
    happen before recording starts."""
    log = SpawnLog()
    real_popen = subprocess.Popen
    real_run = subprocess.run

    class RecordingPopen(real_popen):  # type: ignore[misc,valid-type]
        def __init__(self, args: Any, *positional: Any, **keyword: Any) -> None:
            log.record(args)
            super().__init__(args, *positional, **keyword)

    def recording_run(args: Any, *positional: Any, **keyword: Any) -> Any:
        log.record(args)
        return real_run(args, *positional, **keyword)

    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    monkeypatch.setattr(subprocess, "run", recording_run)
    return log


@dataclass
class ScanLog:
    """Every directory enumeration, for DEC-016-005's "no directory scan of the worktree"."""

    paths: list[str] = field(default_factory=list)

    def clear(self) -> None:
        self.paths.clear()

    def inside(self, root: Path) -> list[str]:
        return [path for path in self.paths if path.startswith(str(root))]


@pytest.fixture
def scans(monkeypatch: pytest.MonkeyPatch) -> ScanLog:
    log = ScanLog()
    real_listdir = os.listdir
    real_scandir = os.scandir

    def recording_listdir(path: Any = ".") -> Any:
        log.paths.append(str(path))
        return real_listdir(path)

    def recording_scandir(path: Any = ".") -> Any:
        log.paths.append(str(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "listdir", recording_listdir)
    monkeypatch.setattr(os, "scandir", recording_scandir)
    return log


def assert_plan_location_holds(worktree: Path, plan_root: Path, scanned: Sequence[str]) -> None:
    """DEC-016-005: loaded from the external root, no plan file in the repository, no scan."""
    assert not [path for path in scanned if path.startswith(str(worktree))], scanned
    assert list(worktree.rglob("*.yaml")) == []
    assert plan_root.is_dir() and sorted(path.name for path in plan_root.iterdir()) == [
        f"{milestone}.yaml" for milestone in MILESTONES
    ]


def assert_repository_untouched_except(
    worktree: Path,
    evidence: tuple[str, str, str],
    governance: Mapping[str, tuple[bytes, int]],
    expected: Sequence[str],
) -> None:
    """Section 27's after-every-case assertions, in one place so no case can forget one."""
    assert porcelain(worktree) == sorted(expected)
    assert repository_evidence(worktree) == evidence
    assert governance_snapshot(worktree) == governance


# --------------------------------------------------------------------------------------
# Section 27 -- the full happy path
# --------------------------------------------------------------------------------------


class TestHappyPathAllMilestones:
    """Section 5 and section 31: three milestones, one review, and a stop at the commit gate."""

    def test_the_run_reaches_ready_for_commit_approval(
        self,
        application_factory: ApplicationFactory,
        worktree: Path,
        plan_root: Path,
        spawns: SpawnLog,
        scans: ScanLog,
    ) -> None:
        evidence = repository_evidence(worktree)
        governance = governance_snapshot(worktree)
        spawns.clear()
        scans.clear()

        report = application_factory().start()
        scanned = list(scans.paths)

        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        assert report.completed_milestones == MILESTONES
        assert_repository_untouched_except(
            worktree, evidence, governance, list(MILESTONE_FILES.values())
        )
        assert spawns.provider_processes == []
        assert spawns.mutating_git == []
        assert_plan_location_holds(worktree, plan_root, scanned)

    def test_every_milestone_wrote_only_its_own_file(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        application_factory().start()
        for milestone, relative in MILESTONE_FILES.items():
            assert (worktree / relative).read_text(
                encoding="utf-8"
            ) == f"# written for {milestone}\n"

    def test_the_durable_record_carries_the_whole_run(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory()
        application.start()
        record = application.status().record
        assert record is not None
        assert record.workflow_state is RunStatus.READY_FOR_COMMIT_APPROVAL
        assert record.completed_milestones == list(MILESTONES)
        assert record.changed_paths == sorted(MILESTONE_FILES.values())
        assert record.review_attempts == 1
        assert record.successful_review_rounds == 1
        assert record.provider_failure_count == 0
        assert record.correction_round == 0
        assert [run.role for run in record.provider_runs] == [
            ProviderRole.IMPLEMENTATION,
            ProviderRole.IMPLEMENTATION,
            ProviderRole.IMPLEMENTATION,
            ProviderRole.REVIEW,
        ]

    def test_every_provider_invocation_left_its_three_transcripts(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        application = application_factory()
        application.start()
        record = application.status().record
        assert record is not None
        store = RunStateStore.pin(
            repository_id=IDENTITY, run_id=record.run_id, repository_root=worktree
        )
        for run in record.provider_runs:
            for reference in (run.prompt_path, run.stdout_path, run.stderr_path):
                assert (store.run_directory / reference).is_file(), reference

    def test_resume_after_a_complete_run_repeats_nothing(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory()
        application.start()
        before = application.status().record
        resumed = application.resume()
        after = application.status().record
        assert resumed.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        assert before is not None and after is not None
        assert before.provider_runs == after.provider_runs


# --------------------------------------------------------------------------------------
# Section 19 -- one correction round, and still blocked after one
# --------------------------------------------------------------------------------------


def open_blocker() -> Finding:
    """The blocker :func:`blocked_review_script`'s review files, as a durable record entry.

    A run resumed from a correction state has to have one: a correction round presupposes an open
    blocker, and a record that carries none is not a state the flow can reach.
    """
    return Finding(
        finding_id=HIGH_BLOCKER["id"],
        severity=FindingSeverity.HIGH,
        title=HIGH_BLOCKER["title"],
        summary=HIGH_BLOCKER["summary"],
        status=FindingStatus.OPEN,
    )


def blocked_review_script(*, closure: Mapping[str, str]) -> dict[str, Any]:
    """A run whose single review blocks, is corrected, and is then ruled on by closure."""
    script = happy_path_script()
    script["results"]["REVIEW"] = review_block(verdict="BLOCKED", blockers=[HIGH_BLOCKER])
    script["results"]["CORRECTION"] = correction_block(addressed=["R-1"])
    script["results"]["CLOSURE"] = closure_block(closure)
    return script


class TestOneCorrectionRound:
    """Section 19: exactly one review, one correction round and one closure verification."""

    def test_a_closed_blocker_reaches_the_commit_gate(
        self, application_factory: ApplicationFactory, worktree: Path, spawns: SpawnLog
    ) -> None:
        evidence = repository_evidence(worktree)
        governance = governance_snapshot(worktree)
        spawns.clear()

        application = application_factory(script=blocked_review_script(closure={"R-1": "CLOSED"}))
        report = application.start()

        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        record = application.status().record
        assert record is not None
        assert record.successful_review_rounds == 1
        assert record.correction_round == 1
        assert record.closure_round == 1
        assert record.provider_failure_count == 0
        assert [finding.status for finding in record.blocking_findings] == [FindingStatus.CLOSED]
        assert [run.role for run in record.provider_runs][-3:] == [
            ProviderRole.REVIEW,
            ProviderRole.CORRECTION,
            ProviderRole.CLOSURE,
        ]
        assert_repository_untouched_except(
            worktree, evidence, governance, list(MILESTONE_FILES.values())
        )
        assert spawns.mutating_git == []

    def test_the_correction_round_is_the_only_one(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory(script=blocked_review_script(closure={"R-1": "CLOSED"}))
        application.start()
        record = application.status().record
        assert record is not None
        assert record.correction_round == 1
        assert record.review_attempts == 1


class TestStillBlockedAfterCorrection:
    """Section 19: a blocker still open after the single correction round stops the run."""

    def test_the_run_stops_at_human_intervention_required(
        self, application_factory: ApplicationFactory, worktree: Path, spawns: SpawnLog
    ) -> None:
        evidence = repository_evidence(worktree)
        governance = governance_snapshot(worktree)
        spawns.clear()

        application = application_factory(script=blocked_review_script(closure={"R-1": "OPEN"}))
        report = application.start()

        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        record = application.status().record
        assert record is not None
        assert [finding.status for finding in record.blocking_findings] == [FindingStatus.OPEN]
        assert record.closure_round == 1
        assert_repository_untouched_except(
            worktree, evidence, governance, list(MILESTONE_FILES.values())
        )
        assert spawns.mutating_git == []

    def test_resume_refuses_what_only_recovery_clears(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory(script=blocked_review_script(closure={"R-1": "OPEN"}))
        application.start()
        with pytest.raises(RunRefused, match="explicit recovery command"):
            application.resume()


# --------------------------------------------------------------------------------------
# Section 15 -- every scope-violation class
# --------------------------------------------------------------------------------------


def scope_violation_script(target: str) -> dict[str, Any]:
    """A first milestone whose provider writes `target` as well as its own file."""
    script = happy_path_script()
    script["writes"]["AUTO-099-M01"] = {
        MILESTONE_FILES["AUTO-099-M01"]: "# written for AUTO-099-M01\n",
        target: "# a path this milestone may not write\n",
    }
    return script


class TestEveryScopeViolationClass:
    """Section 15's three independent checks, each driven to a real stop, each leaving the
    working tree exactly as the provider left it."""

    @pytest.mark.parametrize(
        ("target", "stop_reason"),
        [
            ("docs/TASK_QUEUE.md", StopReason.DIRTY_TREE),
            ("unexpected.txt", StopReason.DIRTY_TREE),
            (MILESTONE_FILES["AUTO-099-M02"], StopReason.OUT_OF_MILESTONE_SCOPE),
        ],
        ids=["forbidden-path", "outside-cumulative-allowlist", "out-of-milestone-scope"],
    )
    def test_a_violation_stops_the_run_and_touches_nothing(
        self,
        application_factory: ApplicationFactory,
        worktree: Path,
        target: str,
        stop_reason: StopReason,
    ) -> None:
        head_before = git(worktree, "rev-parse", "HEAD")
        report = application_factory(script=scope_violation_script(target)).start()

        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert report.stop_reason is stop_reason
        # Nothing was reverted, restored, checked out or deleted: the offending change is exactly
        # where the provider left it, which is section 15's "leaves every file as found".
        assert (worktree / target).is_file()
        assert git(worktree, "rev-parse", "HEAD") == head_before

    def test_the_stop_leaves_the_working_tree_byte_identical(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        application = application_factory(script=scope_violation_script("unexpected.txt"))
        application.start()
        after_stop = worktree_digest(worktree)
        # A second command against the stopped run changes nothing either.
        with pytest.raises(RunRefused):
            application.resume()
        assert worktree_digest(worktree) == after_stop

    def test_a_forbidden_path_is_reported_as_a_violation_of_the_forbidden_check(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        application = application_factory(script=scope_violation_script("docs/DECISION_LOG.md"))
        application.start()
        record = application.status().record
        assert record is not None
        assert record.workflow_state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert (worktree / "docs" / "DECISION_LOG.md").read_text(encoding="utf-8").startswith("# a")


class TestPerMilestoneScopeAgainstAnAccumulatingTree:
    """Finding GOV-AUTO-11-F1, reproduced here and now remediated.

    Section 15 check 2 was evaluated against the repository's whole changed-path set, so once the
    first milestone's file was written every later milestone saw it as a path outside its own
    `allowed_files`. A plan whose milestones own strictly disjoint scopes could therefore not get
    past its second milestone, even though every milestone did exactly what it was asked to do.

    The contract's wording -- "every changed path must additionally match the *current*
    milestone's own `allowed_files`" -- does not say whether "changed" means changed by this run
    or changed by this milestone, and the implementation took the literal, wider reading. Under
    the Human Owner's GOV-AUTO-11 remediation ruling the narrower reading is the binding one: a
    milestone answers for the paths it introduced or modified since the previous durable
    checkpoint, decided by content digest rather than by filename, while checks 1 and 3 keep
    seeing every changed path. A plan whose scopes accumulate (the shape :func:`write_plan`
    writes by default) satisfies both readings, which is how the rest of this suite drives three
    milestones end to end.
    """

    def test_a_disjoint_scope_plan_now_runs_to_the_commit_gate(
        self, application_factory: ApplicationFactory, worktree: Path, plan_root: Path
    ) -> None:
        write_plan(plan_root, disjoint_scopes=True)
        application = application_factory()
        report = application.start()

        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        assert report.stop_reason is None
        assert report.completed_milestones == ("AUTO-099-M01", "AUTO-099-M02", "AUTO-099-M03")
        # Every milestone's own file is exactly where its milestone wrote it.
        for milestone_id in report.completed_milestones:
            assert (worktree / MILESTONE_FILES[milestone_id]).is_file()

    def test_each_milestone_records_the_checkpoint_the_next_one_is_measured_against(
        self, application_factory: ApplicationFactory, plan_root: Path
    ) -> None:
        write_plan(plan_root, disjoint_scopes=True)
        application = application_factory()
        application.start()

        record = application.status().record
        assert record is not None
        assert [entry.milestone_id for entry in record.milestone_checkpoints] == [
            "AUTO-099-M01",
            "AUTO-099-M02",
            "AUTO-099-M03",
        ]
        first = record.milestone_checkpoints[0]
        assert MILESTONE_FILES["AUTO-099-M01"] in first.path_digests
        # The second milestone's file did not exist when the first one finished, so the delta
        # that check 2 evaluated for AUTO-099-M02 really was AUTO-099-M02's own work.
        assert MILESTONE_FILES["AUTO-099-M02"] not in first.path_digests

    def test_a_milestone_writing_another_milestones_file_still_stops(
        self, application_factory: ApplicationFactory, plan_root: Path
    ) -> None:
        """No milestone acquires another's paths implicitly: the delta decides, not the name."""
        write_plan(plan_root, disjoint_scopes=True)
        script = happy_path_script()
        script["writes"]["AUTO-099-M02"][MILESTONE_FILES["AUTO-099-M03"]] = "# trespass\n"
        application = application_factory(script=script)
        report = application.start()

        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        assert report.stop_reason is StopReason.OUT_OF_MILESTONE_SCOPE
        assert report.completed_milestones == ("AUTO-099-M01",)
        assert report.current_milestone == "AUTO-099-M02"

    def test_the_accumulating_plan_shape_is_what_makes_the_run_complete(
        self, application_factory: ApplicationFactory
    ) -> None:
        assert application_factory().start().state is RunStatus.READY_FOR_COMMIT_APPROVAL


# --------------------------------------------------------------------------------------
# Section 18 -- every parser-rejection class
# --------------------------------------------------------------------------------------

WELL_FORMED = milestone_block("AUTO-099-M01", ["src/demo/one.py"])

PARSER_REJECTIONS: Mapping[str, str] = {
    "missing-block": "The provider explained its work and wrote no result block at all.\n",
    "double-fence": f"```\n```\n{WELL_FORMED}```\n```\n",
    "partial-fence": f"```\n{WELL_FORMED}",
    "text-after-end-sentinel": f"{WELL_FORMED}\nand one more thought afterwards\n",
    "multiple-blocks": WELL_FORMED + WELL_FORMED,
    "mismatched-sentinels": (
        "AUTO016_MILESTONE_RESULT\n"
        "milestone: AUTO-099-M01\n"
        "status: COMPLETE\n"
        "END_AUTO016_REVIEW_RESULT\n"
    ),
    "unsafe-yaml-construct": (
        "AUTO016_MILESTONE_RESULT\n"
        "milestone: !!python/object/apply:os.system ['echo unsafe']\n"
        "status: COMPLETE\n"
        "END_AUTO016_MILESTONE_RESULT\n"
    ),
    "missing-required-field": (
        "AUTO016_MILESTONE_RESULT\nstatus: COMPLETE\nEND_AUTO016_MILESTONE_RESULT\n"
    ),
    "unknown-field": (
        "AUTO016_MILESTONE_RESULT\n"
        "milestone: AUTO-099-M01\n"
        "status: COMPLETE\n"
        "confidence: high\n"
        "END_AUTO016_MILESTONE_RESULT\n"
    ),
    "blocked-with-no-blockers": (
        "AUTO016_MILESTONE_RESULT\n"
        "milestone: AUTO-099-M01\n"
        "status: BLOCKED\n"
        "blockers: []\n"
        "END_AUTO016_MILESTONE_RESULT\n"
    ),
    "complete-with-blockers": (
        "AUTO016_MILESTONE_RESULT\n"
        "milestone: AUTO-099-M01\n"
        "status: COMPLETE\n"
        "blockers: [one that contradicts the status]\n"
        "END_AUTO016_MILESTONE_RESULT\n"
    ),
    "wrong-milestone": milestone_block("AUTO-099-M03", ["src/demo/one.py"]),
}


class TestEveryParserRejectionClass:
    """Section 18: every rejection class is refused, and none is ever recorded as a pass.

    Finding GOV-AUTO-11-F2, reproduced here and now remediated. `_drive_milestone` answers a
    malformed implementation result with `MILESTONE_FAILED`, but section 10's closed table
    admitted that state only from `FOCUSED_VERIFYING`, so the stop was refused by the transition
    authority and :class:`TransitionRefused` left the driving command instead. The safety
    property section 18 is actually about held either way -- nothing is accepted, no milestone is
    completed, no budget moves and every transcript survives, all asserted below -- but the run
    stopped by raising rather than by publishing `MILESTONE_FAILED` with a reason, which is the
    shape defect P-2 was about, and it left the run wedged in a state no recovery command admits.
    `(IMPLEMENTING, MILESTONE_FAILED)` is now in the table, so the stop is durable and
    `reopen-milestone` can clear it.
    """

    @pytest.mark.parametrize("case", sorted(PARSER_REJECTIONS), ids=sorted(PARSER_REJECTIONS))
    def test_a_malformed_implementation_result_is_never_accepted(
        self, application_factory: ApplicationFactory, worktree: Path, case: str
    ) -> None:
        script = happy_path_script()
        script["results"]["IMPLEMENTATION:AUTO-099-M01"] = PARSER_REJECTIONS[case]
        application = application_factory(script=script)

        report = application.start()
        assert report.state is RunStatus.MILESTONE_FAILED, report.detail

        record = application.status().record
        assert record is not None
        assert record.completed_milestones == []
        assert record.current_milestone == "AUTO-099-M01"
        assert record.workflow_state is RunStatus.MILESTONE_FAILED
        assert record.workflow_state not in {
            RunStatus.MILESTONE_COMPLETE,
            RunStatus.READY_FOR_COMMIT_APPROVAL,
        }
        assert record.successful_review_rounds == 0

    @pytest.mark.parametrize("case", sorted(PARSER_REJECTIONS), ids=sorted(PARSER_REJECTIONS))
    def test_a_rejected_result_keeps_every_transcript(
        self, application_factory: ApplicationFactory, worktree: Path, case: str
    ) -> None:
        script = happy_path_script()
        script["results"]["IMPLEMENTATION:AUTO-099-M01"] = PARSER_REJECTIONS[case]
        application = application_factory(script=script)
        assert application.start().state is RunStatus.MILESTONE_FAILED
        record = application.status().record
        assert record is not None
        store = RunStateStore.pin(
            repository_id=IDENTITY, run_id=record.run_id, repository_root=worktree
        )
        assert record.provider_runs != []
        for run in record.provider_runs:
            for reference in (run.prompt_path, run.stdout_path, run.stderr_path):
                assert (store.run_directory / reference).is_file()

    def test_a_malformed_review_result_is_a_provider_failure_not_a_consumed_budget(
        self, application_factory: ApplicationFactory
    ) -> None:
        script = happy_path_script()
        script["results"]["REVIEW"] = "the reviewer wrote prose and no result block\n"
        application = application_factory(script=script)
        report = application.start()

        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED
        record = application.status().record
        assert record is not None
        assert record.review_attempts == 1
        assert record.successful_review_rounds == 0
        assert record.provider_failure_count == 1

    def test_a_provider_that_exits_non_zero_is_never_accepted(
        self, application_factory: ApplicationFactory
    ) -> None:
        script = happy_path_script()
        script["exit_codes"] = {"IMPLEMENTATION": 3}
        application = application_factory(script=script)
        assert application.start().state is RunStatus.MILESTONE_FAILED
        record = application.status().record
        assert record is not None
        assert record.provider_runs[-1].failure_class is ProviderFailureClass.COMMAND_FAILED
        assert record.completed_milestones == []

    def test_a_reopened_milestone_can_be_resumed_after_a_malformed_result(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        """The point of publishing the stop: `MILESTONE_FAILED` is a state recovery can clear.

        Refusing the transition left the run at `IMPLEMENTING`, which `reopen-milestone` does not
        admit as an entry state and `resume` could not continue -- so the only exit was `abort`,
        discarding the run over one unparseable result block.
        """
        script = happy_path_script()
        script["results"]["IMPLEMENTATION:AUTO-099-M01"] = PARSER_REJECTIONS["missing-block"]
        application = application_factory(script=script)
        assert application.start().state is RunStatus.MILESTONE_FAILED

        recovered = application.reopen_milestone(
            milestone="AUTO-099-M01", reason="Human Owner ruling: the provider result was retried."
        )
        assert recovered.satisfied
        assert recovered.pre_state is RunStatus.MILESTONE_FAILED
        assert recovered.post_state is RunStatus.IMPLEMENTING
        assert recovered.budgets_touched == {}

        record = application.status().record
        assert record is not None
        assert record.workflow_state is RunStatus.IMPLEMENTING
        assert record.current_milestone == "AUTO-099-M01"
        assert record.completed_milestones == []
        # Reopening consumed nothing and deleted nothing: the partial file the failed attempt
        # left behind is still exactly where the provider wrote it.
        assert record.successful_review_rounds == 0
        assert (worktree / MILESTONE_FILES["AUTO-099-M01"]).is_file()

    def test_a_failing_focused_command_stops_the_milestone_with_a_published_state(
        self, application_factory: ApplicationFactory, plan_root: Path
    ) -> None:
        """The rejection path section 10's table does admit, for contrast with the two above."""
        write_plan(plan_root, failing_focused=["AUTO-099-M01"])
        application = application_factory()
        report = application.start()

        assert report.state is RunStatus.MILESTONE_FAILED, report.detail
        record = application.status().record
        assert record is not None
        assert record.completed_milestones == []
        assert [result.passed for result in record.verification_results] == [False]


# --------------------------------------------------------------------------------------
# Section 13 -- interruption, resume and lock contention
# --------------------------------------------------------------------------------------

#: The driver a real interruption needs: a separate process that starts a run and can be killed
#: mid-invocation. Its adapter is written out here rather than imported from this module because a
#: killed child must not depend on pytest being importable in it.
DRIVER_SCRIPT = """\
import json, sys
from pathlib import Path

from ai_workflow_engine.milestone_runner.application import (
    MilestoneRunnerApplication,
    ProviderBinding,
)
from ai_workflow_engine.milestone_runner.config import load_runner_config
from ai_workflow_engine.milestone_runner.models import ProviderRole
from ai_workflow_engine.milestone_runner.recovery import (
    RECONSTRUCTED_FROM_VERIFIED_EVIDENCE,
    RecoveryRefused,
)
from ai_workflow_engine.milestone_runner.providers.base import (
    ProviderAdapter,
    ProviderRequest,
    transcript_label_for,
)


class DriverAdapter(ProviderAdapter):
    name = "fake"
    roles = frozenset(ProviderRole)

    def __init__(self, program):
        self._program = program

    def build_request(self, *, role, prompt, milestone_id=None):
        self._require_role(role)
        return ProviderRequest(
            provider=self.name,
            role=role,
            argv=[sys.executable, self._program, role.value, milestone_id or "-"],
            prompt=prompt,
            timeout_seconds=600,
            transcript_label=transcript_label_for(self.name, role),
            milestone_id=milestone_id,
        )


config_path, program = sys.argv[1], sys.argv[2]
adapter = DriverAdapter(program)
application = MilestoneRunnerApplication(
    load_runner_config(Path(config_path)),
    providers=ProviderBinding(implementation=adapter, review=adapter),
)
report = application.start()
print(json.dumps({"state": report.state.value}))
"""


class TestInterruptionAndResume:
    """Section 13: a run interrupted mid-invocation resumes from exactly where it stopped, and
    resume repeats no completed side effect."""

    def test_a_hard_kill_mid_invocation_leaves_a_resumable_run(
        self,
        tmp_path: Path,
        worktree: Path,
        isolated_home: Path,
        config_factory: ConfigFactory,
        application_factory: ApplicationFactory,
    ) -> None:
        slow = tmp_path / "slow_provider.py"
        slow.write_text(SLOW_PROVIDER_SCRIPT, encoding="utf-8")
        driver = tmp_path / "driver.py"
        driver.write_text(DRIVER_SCRIPT, encoding="utf-8")
        config_path = config_factory()

        child = subprocess.Popen(
            [sys.executable, str(driver), str(config_path), str(slow)],
            cwd=REPOSITORY_ROOT,
            env={**os.environ, "HOME": str(isolated_home)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            store_directory = isolated_home / ".ai-workflow-engine" / "milestone-runs" / IDENTITY
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if store_directory.is_dir() and list(store_directory.glob("auto016-*/state.json")):
                    break
                if child.poll() is not None:  # pragma: no cover - the driver should still be alive
                    raise AssertionError(f"the driver exited early: {child.communicate()}")
                time.sleep(0.1)
            else:  # pragma: no cover - a stuck driver is a failure, not a skip
                raise AssertionError("the driver never published a run")
            time.sleep(1.0)
            child.send_signal(signal.SIGKILL)
        finally:
            child.wait(timeout=60)
            if child.stdout is not None:
                child.stdout.close()
            if child.stderr is not None:
                child.stderr.close()

        state = json.loads(
            next(store_directory.glob("auto016-*/state.json")).read_text(encoding="utf-8")
        )
        assert state["workflow_state"] in {
            RunStatus.PROVIDER_WAIT.value,
            RunStatus.IMPLEMENTING.value,
            RunStatus.PREFLIGHT.value,
        }

        # The killed process released the `flock` on exit, so the run is resumable here, and the
        # resumed run drives the plan to the commit gate with the scripted provider.
        resumed = application_factory(config_path=config_path).resume()
        assert resumed.state is RunStatus.READY_FOR_COMMIT_APPROVAL, resumed.detail

    @pytest.mark.parametrize(
        "state",
        [
            RunStatus.PREFLIGHT,
            RunStatus.IMPLEMENTING,
            RunStatus.FOCUSED_VERIFYING,
            RunStatus.PROVIDER_WAIT,
            RunStatus.PROVIDER_RETRY_PENDING,
            RunStatus.MILESTONE_COMPLETE,
        ],
        ids=lambda state: str(state.value),
    )
    def test_resume_drives_a_mid_run_state_to_the_commit_gate(
        self,
        application_factory: ApplicationFactory,
        worktree: Path,
        config: RunnerConfig,
        state: RunStatus,
    ) -> None:
        """Finding GOV-AUTO-11-F3: every resumable mid-run state continues, none is refused.

        A crash inside a milestone can leave any of these published -- `IMPLEMENTING` is published
        before the prompt is even rendered -- and resume used to ask for `<state> -> IMPLEMENTING`,
        a pair section 10's closed table does not carry, so section 13's "continue from exactly
        where the run stopped" was unavailable from three of the six. Resume now dispatches on the
        state it loaded rather than restarting the flow.
        """
        publish(worktree, record_at(worktree, config, workflow_state=state))
        report = application_factory().resume()
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        assert report.completed_milestones == MILESTONES

    def test_resume_from_focused_verifying_does_not_regenerate_the_implementation(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        """Section 13: an interrupted focused verification resumes verification, not the provider.

        The first milestone's work is already on disk when `FOCUSED_VERIFYING` is published, so
        re-invoking its implementer would discard finished work and repeat a completed side
        effect -- exactly what section 13 forbids.
        """
        publish(
            worktree,
            record_at(worktree, config, workflow_state=RunStatus.FOCUSED_VERIFYING),
        )
        application = application_factory()
        assert application.resume().state is RunStatus.READY_FOR_COMMIT_APPROVAL

        record = application.status().record
        assert record is not None
        implementations = [
            run.milestone_id
            for run in record.provider_runs
            if run.role is ProviderRole.IMPLEMENTATION
        ]
        # The first milestone was already implemented; only the other two were invoked.
        assert implementations == list(MILESTONES[1:])

    def test_resume_from_a_provider_excursion_returns_to_the_invoking_state(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        """A bounded retry resumes the failed provider operation, and only that one.

        The excursion's own caller is gone after a crash, so the invoking state is read from the
        last recorded invocation's role -- section 17 binds each role to exactly one state.
        """
        publish(
            worktree,
            record_at(
                worktree,
                config,
                workflow_state=RunStatus.PROVIDER_RETRY_PENDING,
                completed_milestones=list(MILESTONES),
            ),
        )
        application = application_factory()
        assert application.resume().state is RunStatus.READY_FOR_COMMIT_APPROVAL

        record = application.status().record
        assert record is not None
        # No milestone was reimplemented: with the plan complete the excursion returned to the
        # review, which is the only provider operation left to run.
        assert [run.role for run in record.provider_runs] == [ProviderRole.REVIEW]

    @pytest.mark.parametrize(
        "state",
        [
            RunStatus.FINAL_VERIFYING,
            RunStatus.REVIEWING,
            RunStatus.NEEDS_CORRECTION,
            RunStatus.CORRECTING,
            RunStatus.CLOSURE_VERIFYING,
        ],
        ids=lambda state: str(state.value),
    )
    def test_resume_from_a_post_milestone_state_advances_the_run(
        self,
        application_factory: ApplicationFactory,
        worktree: Path,
        config: RunnerConfig,
        state: RunStatus,
    ) -> None:
        """The same finding from the other side: resume carries a post-milestone state onward.

        With every milestone already complete these five used to fall through the milestone loop
        and return the record untouched -- no side effect repeated, which section 13 does require,
        but no progress either, so the run sat where it was forever. Each now continues its own
        step. The two correction states need an open blocker to correct, which is what the
        `NEEDS_CORRECTION` script supplies.
        """
        mid_correction = state in (
            RunStatus.NEEDS_CORRECTION,
            RunStatus.CORRECTING,
            RunStatus.CLOSURE_VERIFYING,
        )
        script = blocked_review_script(closure={"R-1": "CLOSED"})
        publish(
            worktree,
            record_at(
                worktree,
                config,
                workflow_state=state,
                completed_milestones=list(MILESTONES),
                blocking_findings=[open_blocker()] if mid_correction else [],
                successful_review_rounds=1 if mid_correction else 0,
                review_attempts=1 if mid_correction else 0,
                correction_round=1 if state is RunStatus.CLOSURE_VERIFYING else 0,
            ),
        )
        application = application_factory(script=script)
        report = application.resume()

        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        record = application.status().record
        assert record is not None
        # No milestone was reimplemented: the plan was already complete.
        assert record.completed_milestones == list(MILESTONES)
        assert not any(
            run.role is ProviderRole.IMPLEMENTATION for run in record.provider_runs
        ), "a completed milestone is never rerun"

    def test_resuming_a_review_never_raises_a_budget_ceiling(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        """Section 19: a round interrupted before its result parsed consumed nothing."""
        publish(
            worktree,
            record_at(
                worktree,
                config,
                workflow_state=RunStatus.REVIEWING,
                completed_milestones=list(MILESTONES),
                review_attempts=1,
            ),
        )
        application = application_factory()
        assert application.resume().state is RunStatus.READY_FOR_COMMIT_APPROVAL

        record = application.status().record
        assert record is not None
        # The interrupted attempt is still counted, the resumed one is counted too, and exactly
        # one review round -- the one whose result actually parsed -- was consumed.
        assert record.review_attempts == 2
        assert record.successful_review_rounds == 1
        assert record.correction_round == 0
        assert record.closure_round == 0

    @pytest.mark.parametrize(
        ("state", "message"),
        [
            (RunStatus.MILESTONE_FAILED, "reopen-milestone"),
            (RunStatus.HUMAN_INTERVENTION_REQUIRED, "explicit recovery command"),
            (RunStatus.DONE, "terminal state"),
            (RunStatus.ABORTED, "terminal state"),
        ],
        ids=lambda value: str(getattr(value, "value", value)),
    )
    def test_resume_refuses_a_state_only_an_operator_act_clears(
        self,
        application_factory: ApplicationFactory,
        worktree: Path,
        config: RunnerConfig,
        state: RunStatus,
        message: str,
    ) -> None:
        publish(
            worktree,
            record_at(
                worktree,
                config,
                workflow_state=state,
                stop_reason=(
                    StopReason.DIRTY_TREE
                    if state is RunStatus.HUMAN_INTERVENTION_REQUIRED
                    else None
                ),
                current_milestone=(MILESTONES[0] if state is RunStatus.MILESTONE_FAILED else None),
            ),
        )
        with pytest.raises(RunRefused, match=message):
            application_factory().resume()

    def test_resume_twice_with_no_intervening_change_is_a_no_op(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory()
        application.start()
        first = application.resume()
        second = application.resume()
        assert first.state is second.state is RunStatus.READY_FOR_COMMIT_APPROVAL

    def test_resume_refuses_a_terminal_run(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        publish(worktree, record_at(worktree, config, workflow_state=RunStatus.ABORTED))
        with pytest.raises(RunRefused, match="terminal state"):
            application_factory().resume()


class TestLockContention:
    """Section 12: exactly one runner process per canonical repository."""

    def test_a_second_runner_is_refused_while_the_lock_is_held(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        store = publish(worktree, record_at(worktree, config, workflow_state=RunStatus.PREFLIGHT))
        holder = RunLock(
            run_id="auto016-20260807T110000Z-otherrun",
            repository_identity=IDENTITY,
            artifact_root=store.artifact_root,
        )
        holder.acquire()
        try:
            with pytest.raises(RunRefused):
                application_factory().resume()
            with pytest.raises(RunRefused):
                application_factory().abort(reason="an operator asked for it")
        finally:
            holder.release()
        assert store.load().workflow_state is RunStatus.PREFLIGHT

    def test_the_read_only_commands_need_no_lock(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        store = publish(worktree, record_at(worktree, config, workflow_state=RunStatus.PREFLIGHT))
        holder = RunLock(
            run_id="auto016-20260807T110000Z-otherrun",
            repository_identity=IDENTITY,
            artifact_root=store.artifact_root,
        )
        holder.acquire()
        try:
            application = application_factory()
            assert application.status().record is not None
            assert application.plan().satisfied
            assert application.doctor().satisfied
        finally:
            holder.release()


def record_at(worktree: Path, config: RunnerConfig, **overrides: Any) -> RunRecord:
    """A published-shaped run record consistent with the fixtures above."""
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": "auto016-20260807T120000Z-deadbeef",
        "repository_root": str(worktree),
        "repository_identity": IDENTITY,
        "expected_branch": "main",
        "baseline_sha": git(worktree, "rev-parse", "HEAD"),
        "contract_sha256": config.stage.contract_sha256,
        "workflow_state": RunStatus.PREFLIGHT,
        "created_at": "2026-08-07T11:00:00Z",
        "updated_at": "2026-08-07T12:00:00Z",
    }
    payload.update(overrides)
    return RunRecord.model_validate(payload)


def publish(worktree: Path, record: RunRecord) -> RunStateStore:
    """Publish `record` the way the runner does: under a real lock, atomically."""
    store = RunStateStore.pin(
        repository_id=IDENTITY, run_id=record.run_id, repository_root=worktree
    )
    lock = RunLock(
        run_id=record.run_id, repository_identity=IDENTITY, artifact_root=store.artifact_root
    )
    lock.acquire()
    try:
        store.publish(record, lock=lock)
    finally:
        lock.release()
    record_latest_run(store.artifact_root, record.run_id)
    return store


# --------------------------------------------------------------------------------------
# Section 13 -- each of the four recovery commands
# --------------------------------------------------------------------------------------


class TestTheFourRecoveryCommands:
    """Section 13: each recovery command, driven against a real stopped run."""

    def test_reopen_milestone_clears_a_failed_milestone(
        self, application_factory: ApplicationFactory, plan_root: Path
    ) -> None:
        write_plan(plan_root, failing_focused=["AUTO-099-M01"])
        application = application_factory()
        assert application.start().state is RunStatus.MILESTONE_FAILED

        report = application.reopen_milestone(
            milestone="AUTO-099-M01", reason="the Human Owner ruled the milestone reopened"
        )
        assert report.command is RecoveryCommand.REOPEN_MILESTONE
        assert report.pre_state is RunStatus.MILESTONE_FAILED
        assert report.post_state is RunStatus.IMPLEMENTING
        record = application.status().record
        assert record is not None
        assert record.reopenings != []
        assert record.provider_runs != []

    def test_reconcile_milestone_accepts_a_result_matching_its_own_transcript(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory(
            script=scope_violation_script(MILESTONE_FILES["AUTO-099-M02"])
        )
        assert application.start().stop_reason is StopReason.OUT_OF_MILESTONE_SCOPE

        report = application.reconcile_milestone(
            milestone="AUTO-099-M01",
            reason="the result was semantically valid and is reconciled against its transcript",
        )
        assert report.command is RecoveryCommand.RECONCILE_MILESTONE
        assert report.post_state is RunStatus.FOCUSED_VERIFYING
        record = application.status().record
        assert record is not None
        assert record.reconciliations != []
        # Section 13: the reconciliation records what it reconstructed and from what, honestly --
        # never that the milestone passed. The post-state above is where that is decided.
        assert RECONSTRUCTED_FROM_VERIFIED_EVIDENCE in record.reconciliations[-1].reason

    def test_revalidate_correction_clears_a_post_correction_failure(
        self, tmp_path: Path, application_factory: ApplicationFactory
    ) -> None:
        """The recorded real run needed this once, to clear "tests failed after the correction
        round" (section 6). The canary below is what produces that stop honestly: it passes the
        first time the full set runs, at `FINAL_VERIFYING`, and fails the second, at
        `CLOSURE_VERIFYING`."""
        application = application_factory(
            script=blocked_review_script(closure={"R-1": "CLOSED"}),
            config_overrides={"verification": closure_canary_verification(tmp_path)},
        )
        report = application.start()
        assert report.state is RunStatus.HUMAN_INTERVENTION_REQUIRED, report.detail
        record = application.status().record
        assert record is not None
        assert record.correction_round == 1
        budgets_before = (
            record.successful_review_rounds,
            record.correction_round,
            record.closure_round,
            record.provider_failure_count,
        )

        recovery = application.revalidate_correction()
        assert recovery.command is RecoveryCommand.REVALIDATE_CORRECTION
        assert recovery.post_state is RunStatus.CLOSURE_VERIFYING
        assert recovery.budgets_touched == {}
        after = application.status().record
        assert after is not None
        assert (
            after.successful_review_rounds,
            after.correction_round,
            after.closure_round,
            after.provider_failure_count,
        ) == budgets_before
        assert after.revalidations != []

    def test_recover_failed_review_restores_exactly_one_budget(
        self, application_factory: ApplicationFactory, worktree: Path, config: RunnerConfig
    ) -> None:
        """Section 13's `recover-failed-review`, on the shape the prototype's real run produced.

        The combination it repairs -- a consumed review budget beside a review invocation that
        recorded a failure class -- is one AUTO-016's own accounting no longer produces, because a
        provider failure never consumes a review budget here (section 19, defect P-3). The record
        is therefore published directly, and the paired test below proves the driven flow really
        does refuse to create that combination.
        """
        publish(
            worktree,
            record_at(
                worktree,
                config,
                workflow_state=RunStatus.HUMAN_INTERVENTION_REQUIRED,
                stop_reason=StopReason.GOVERNANCE_CONTRADICTION,
                review_attempts=1,
                successful_review_rounds=1,
                provider_failure_count=1,
                provider_runs=[
                    ProviderRunRecord(
                        sequence=1,
                        role=ProviderRole.REVIEW,
                        provider="fake",
                        started_at="2026-08-07T11:59:00Z",
                        completed_at="2026-08-07T12:00:00Z",
                        duration_ms=1_000,
                        exit_code=1,
                        failure_class=ProviderFailureClass.AUTH_FAILED,
                        prompt_path="transcripts/0001-20260807T115900Z-fake-review.prompt.md",
                        stdout_path="transcripts/0001-20260807T115900Z-fake-review.stdout.txt",
                        stderr_path="transcripts/0001-20260807T115900Z-fake-review.stderr.txt",
                    )
                ],
            ),
        )
        report = application_factory().recover_failed_review(
            classification=ProviderFailureClass.AUTH_FAILED.value,
            ruling="the Human Owner ruled the authentication expiry a provider failure",
        )
        assert report.command is RecoveryCommand.RECOVER_FAILED_REVIEW
        assert report.budgets_touched == {"successful_review_rounds": -1}
        assert report.post_state is RunStatus.REVIEWING

    def test_a_driven_provider_failure_never_consumes_a_review_budget(
        self, application_factory: ApplicationFactory
    ) -> None:
        """The other half of the case above: the driven flow cannot produce what it repairs."""
        script = happy_path_script()
        script["results"]["REVIEW"] = "the reviewer returned no parseable block\n"
        application = application_factory(script=script)
        application.start()
        record = application.status().record
        assert record is not None
        assert record.successful_review_rounds == 0
        assert record.provider_failure_count == 1
        with pytest.raises(RecoveryRefused, match="No review budget is consumed"):
            application.recover_failed_review(
                classification=ProviderFailureClass.AUTH_FAILED.value,
                ruling="a ruling this run does not support",
            )

    def test_no_recovery_reaches_an_approval_state(
        self, application_factory: ApplicationFactory, plan_root: Path
    ) -> None:
        write_plan(plan_root, failing_focused=["AUTO-099-M01"])
        application = application_factory()
        application.start()
        report = application.reopen_milestone(
            milestone="AUTO-099-M01", reason="the Human Owner ruled the milestone reopened"
        )
        assert report.post_state not in {
            RunStatus.READY_FOR_COMMIT_APPROVAL,
            RunStatus.READY_FOR_PUSH_APPROVAL,
            RunStatus.DONE,
        }


# --------------------------------------------------------------------------------------
# Section 20 and section 27 -- the four-way no-automatic-mutation proof
# --------------------------------------------------------------------------------------


class TestNoAutomaticGitMutation:
    """Section 27: commit, push, pull-request creation and merge are never performed
    automatically, proved by all four independent means."""

    def test_a_the_ast_proof(self) -> None:
        """(a) No mutating Git subcommand outside `approval_git.py`, and no `gh` invocation."""
        sources = [
            source
            for source in sorted(PACKAGE_ROOT.rglob("*.py"))
            if "__pycache__" not in source.parts
        ]
        mutating = {"commit", "push", "merge", "reset", "checkout", "clean", "stash"}
        for source in sources:
            literals = {
                node.value
                for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            assert "gh" not in literals, source.name
            if source.name == "approval_git.py":
                continue
            assert not mutating & literals, f"{source.name} names {sorted(mutating & literals)}"

    def test_b_the_behavioural_print_only_proof(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        """(b) `approve-commit` with the shipped defaults produces output and changes nothing."""
        application = application_factory()
        assert application.start().state is RunStatus.READY_FOR_COMMIT_APPROVAL
        before = repository_evidence(worktree)

        report = application.approve_commit()
        assert not report.execution.executed
        assert report.execution.rendered_commands[0].startswith("git add --")
        assert any("commit --message" in command for command in report.execution.rendered_commands)
        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL
        assert repository_evidence(worktree) == before

    def test_c_the_git_level_proof(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        """(c) `HEAD`, the reflog and the remote refs are unchanged across a complete run."""
        before = repository_evidence(worktree)
        application = application_factory()
        application.start()
        application.approve_commit()
        assert repository_evidence(worktree) == before

    def test_d_the_process_level_proof(
        self, application_factory: ApplicationFactory, worktree: Path, spawns: SpawnLog
    ) -> None:
        """(d) No `git commit`, `git push` or `gh` subprocess was ever spawned."""
        spawns.clear()
        application = application_factory()
        application.start()
        application.approve_commit()

        assert spawns.matching("commit") == []
        assert spawns.matching("push") == []
        assert spawns.provider_processes == []
        assert spawns.mutating_git == []
        # The run really did spawn processes, so the emptiness above is evidence rather than an
        # artifact of a recorder that saw nothing.
        assert spawns.matching("rev-parse", "--verify", "HEAD") != []

    def test_the_push_gate_is_unreachable_from_the_commit_gate(
        self, application_factory: ApplicationFactory
    ) -> None:
        application = application_factory()
        application.start()
        with pytest.raises(RunRefused, match="reachable only from"):
            application.approve_push()

    def test_the_typed_confirmation_alone_executes_nothing(
        self, application_factory: ApplicationFactory, worktree: Path
    ) -> None:
        """Section 20: the confirmation is one of two conditions, and the flip ships `false`."""
        before = repository_evidence(worktree)
        application = application_factory()
        application.start()
        report = application.approve_commit(confirmation="APPROVE COMMIT")
        assert not report.execution.executed
        assert repository_evidence(worktree) == before


# --------------------------------------------------------------------------------------
# DEC-016-006 -- prototype non-interference
# --------------------------------------------------------------------------------------


class TestPrototypeRunnerUnchanged:
    """Section 27 and DEC-016-006: the AUTO-015 prototype is byte-identical before and after."""

    def test_a_complete_run_leaves_the_prototype_untouched(
        self, application_factory: ApplicationFactory
    ) -> None:
        if not PROTOTYPE_ROOT.is_dir():
            pytest.skip(f"the AUTO-015 prototype is not installed at {PROTOTYPE_ROOT}")
        before = prototype_snapshot()
        assert before, "the prototype directory is present but carries no file to compare"
        application = application_factory()
        assert application.start().state is RunStatus.READY_FOR_COMMIT_APPROVAL
        application.approve_commit()
        after = prototype_snapshot()
        assert after == before
        assert {name for name in after} == {name for name in before}

    def test_the_snapshot_compares_contents_and_mtimes(self, tmp_path: Path) -> None:
        """The comparison would notice a change: proved on a directory this test owns."""
        sample = tmp_path / "sample"
        sample.mkdir()
        (sample / "state.json").write_text("{}", encoding="utf-8")

        def snapshot_of(root: Path) -> dict[str, tuple[int, str, int]]:
            return {
                path.relative_to(root).as_posix(): (
                    path.stat().st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    path.stat().st_mtime_ns,
                )
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }

        before = snapshot_of(sample)
        (sample / "state.json").write_text('{"changed": true}', encoding="utf-8")
        assert snapshot_of(sample) != before

    def test_no_package_module_addresses_the_prototype(self) -> None:
        """No executable string in the package names the prototype's location.

        Prose about it is another matter and is welcome: `recovery.py`'s docstring records that the
        prototype is never opened by any path there. What would actually reach it is a string
        literal in code, and there is none.
        """
        for source in sorted(PACKAGE_ROOT.rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            docstrings = set()
            for node in ast.walk(tree):
                if not isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                ):
                    continue
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docstrings
                ):
                    assert "auto015" not in node.value.lower(), source.name


# --------------------------------------------------------------------------------------
# DEC-016-005 -- the plan-location assertions
# --------------------------------------------------------------------------------------


class TestPlanLocation:
    """Section 27 and DEC-016-005: the plan comes from the external root, nothing is created
    inside the repository, and no directory scan of the worktree occurs."""

    def test_the_plan_is_loaded_from_the_external_root(
        self, config: RunnerConfig, worktree: Path, plan_root: Path
    ) -> None:
        plan = MilestonePlanLoader(config, worktree).load()
        assert plan.milestone_ids == MILESTONES
        for source in plan.source_paths:
            assert str(source).startswith(str(plan_root))
            assert not str(source).startswith(str(worktree))

    def test_a_complete_run_creates_no_plan_file_inside_the_repository(
        self, application_factory: ApplicationFactory, worktree: Path, plan_root: Path
    ) -> None:
        application_factory().start()
        assert list(worktree.rglob("*.yaml")) == []
        assert list(worktree.rglob("plan.json")) == []

    def test_a_complete_run_scans_no_directory_inside_the_worktree(
        self, application_factory: ApplicationFactory, worktree: Path, scans: ScanLog
    ) -> None:
        scans.clear()
        application_factory().start()
        assert scans.inside(worktree) == []

    def test_the_resolved_snapshot_never_rewrites_the_source_plan(
        self, application_factory: ApplicationFactory, plan_root: Path
    ) -> None:
        before = {
            path.name: path.read_bytes() for path in sorted(plan_root.iterdir()) if path.is_file()
        }
        application_factory().start()
        after = {
            path.name: path.read_bytes() for path in sorted(plan_root.iterdir()) if path.is_file()
        }
        assert after == before


# --------------------------------------------------------------------------------------
# Section 25 -- the packaging proofs
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One real wheel, built once from this repository with `pip wheel --no-deps`."""
    directory = tmp_path_factory.mktemp("wheel")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(directory),
            str(REPOSITORY_ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = sorted(directory.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


class TestWheelContainsMilestoneRunner:
    """Section 25: `pip wheel --no-deps` ships the new subpackage, with no `pyproject.toml` edit."""

    def test_the_wheel_carries_every_module_of_section_8(self, built_wheel: Path) -> None:
        with zipfile.ZipFile(built_wheel) as archive:
            names = set(archive.namelist())
        shipped = {
            name
            for name in names
            if name.startswith("ai_workflow_engine/milestone_runner/") and name.endswith(".py")
        }
        expected = {
            f"ai_workflow_engine/milestone_runner/{source.relative_to(PACKAGE_ROOT).as_posix()}"
            for source in sorted(PACKAGE_ROOT.rglob("*.py"))
            if "__pycache__" not in source.parts
        }
        assert shipped == expected
        assert len(expected) == 19, sorted(expected)

    def test_the_wheel_still_carries_the_three_top_level_packages(self, built_wheel: Path) -> None:
        with zipfile.ZipFile(built_wheel) as archive:
            roots = {name.split("/")[0] for name in archive.namelist()}
        assert {"ai_workflow_engine", "agentos_workflow", "agentos_dashboard"} <= roots


class TestOutOfTreeImport:
    """Section 25: a fresh virtual environment with the built wheel imports the package cleanly
    from outside the repository."""

    def test_the_package_imports_from_a_fresh_environment_outside_the_repository(
        self, built_wheel: Path, tmp_path: Path
    ) -> None:
        venv = tmp_path / "venv"
        # `--system-site-packages` so the wheel's declared dependencies resolve without reaching
        # the network; the wheel itself is installed `--no-deps --no-index`, and the assertion
        # below proves the imported module is the installed one and not this checkout.
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
            capture_output=True,
            text=True,
            check=True,
        )
        interpreter = venv / "bin" / "python"
        install = subprocess.run(
            [
                str(interpreter),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--quiet",
                str(built_wheel),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert install.returncode == 0, install.stdout + install.stderr

        probe = (
            "import ai_workflow_engine.milestone_runner as package;"
            "import ai_workflow_engine.milestone_runner.application as application;"
            "import ai_workflow_engine.milestone_runner.providers.codex_cli as codex;"
            "print(application.__file__)"
        )
        imported = subprocess.run(
            [str(interpreter), "-c", probe],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
        )
        assert imported.returncode == 0, imported.stdout + imported.stderr
        resolved = imported.stdout.strip()
        assert resolved.startswith(str(venv))
        assert not resolved.startswith(str(REPOSITORY_ROOT))

    def test_the_command_group_is_reachable_from_the_installed_console_script(
        self, built_wheel: Path, tmp_path: Path
    ) -> None:
        venv = tmp_path / "venv-cli"
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
            capture_output=True,
            text=True,
            check=True,
        )
        interpreter = venv / "bin" / "python"
        subprocess.run(
            [
                str(interpreter),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--quiet",
                str(built_wheel),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        completed = subprocess.run(
            [str(venv / "bin" / "workflowctl"), "milestone-runner", "--help"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "doctor" in completed.stdout


# --------------------------------------------------------------------------------------
# Section 27 Tier 2 -- the real-provider smoke suite, under the existing `live_cli` marker
# --------------------------------------------------------------------------------------

#: Maps each CLI's own credential-store variable to the operator-side variable naming the account
#: this suite runs as. Lifted from `agentos_workflow/tests/live/test_live_providers.py`, which is
#: this repository's only proven pattern for reaching a real provider from a test: the account is
#: selected out here, once, so no account path is hard-coded in this file or in the runner.
ACCOUNT_ENVIRONMENT: dict[str, str] = {
    "CLAUDE_CONFIG_DIR": "CLAUDE_CONFIG_DIR_A",
    "CODEX_HOME": "CODEX_HOME_A",
}

#: The only files copied out of an account template into a disposable store. Deliberately one file
#: per provider: everything the CLI itself writes afterwards -- Claude's `.claude.json`, `projects/`
#: and session JSONL, Codex's `history.jsonl` and caches -- is client-side continuity state that
#: must not accumulate across invocations, so the allowlist stays this short rather than becoming
#: "everything except a denylist". The sibling suite records the incident that established this.
AUTH_TEMPLATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CLAUDE_CONFIG_DIR", (".credentials.json",)),
    ("CODEX_HOME", ("auth.json",)),
)

#: What the runner may forward to a live provider. `PATH` and `HOME` are what every other test in
#: this module allows; the two credential-store variables name a *location*, never a secret, and
#: `build_provider_environment` independently refuses any credential-shaped name, so adding them
#: widens the forwarded environment by exactly two directory paths and nothing else.
LIVE_PROVIDER_ENVIRONMENT: list[str] = ["PATH", "HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME"]

#: A trivial, read-only turn. Its only job is to separate "this provider is usable here" from
#: "this provider is installed but cannot authenticate".
LIVE_PROBE_PROMPT = "Do nothing at all. Reply with exactly: READY"

#: Generous for one real model turn; only ever spent once per session.
LIVE_PROBE_TIMEOUT_SECONDS = 180


def stage_ephemeral_store(root: Path, variable: str, allowlist: Sequence[str]) -> Path | None:
    """A fresh, disposable credential store under `root`, or `None` if no account is configured.

    The configured account's directory is a **read-only authentication template**: this copies only
    `allowlist` out of it into a brand-new private directory and never writes back. Everything the
    CLI subsequently creates lives and dies with the caller's `tmp_path`.
    """
    template = os.environ.get(ACCOUNT_ENVIRONMENT[variable])
    if not template:
        return None
    template_path = Path(template)
    destination = root / f"{variable.lower()}-store"
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    for name in allowlist:
        source_file = template_path / name
        if source_file.is_file():
            destination_file = destination / name
            destination_file.write_bytes(source_file.read_bytes())
            os.chmod(destination_file, 0o600)
    return destination


def stage_live_provider_environment(root: Path, environment: dict[str, str]) -> dict[str, str]:
    """Add each provider's disposable store to `environment`, staged under `root`."""
    for variable, allowlist in AUTH_TEMPLATES:
        staged = stage_ephemeral_store(root, variable, allowlist)
        if staged is not None:
            environment[variable] = str(staged)
    return environment


def probe_repository(root: Path) -> Path:
    """A throwaway git repository. `codex exec` refuses to run outside one."""
    repository = root / "probe-repo"
    repository.mkdir(parents=True, exist_ok=True)
    (repository / "README.md").write_text("# probe\n", encoding="utf-8")
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "live-probe@example.invalid"],
        ["git", "config", "user.name", "AUTO-016 live probe"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "initial"],
    ):
        subprocess.run(argv, cwd=repository, check=True, capture_output=True)
    return repository


def live_provider_reason(executable: str, root: Path) -> str | None:
    """Run one trivial real invocation. `None` if it worked, else why it did not.

    `shutil.which` alone is not the question: these tests redirect `HOME`, and a Claude or Codex
    CLI that is on `PATH` and authenticated under the operator's real home is *not* authenticated
    under a fresh one. Probing under the same redirected home and the same staged stores the tests
    themselves use is what makes a skip here mean "no usable live provider" rather than
    "the binary exists". The flags mirror each adapter's fixed argv template; the tests exercise
    the real vectors through the production adapters.
    """
    if shutil.which(executable) is None:
        return f"{executable} is not installed on this machine"

    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    environment = stage_live_provider_environment(
        root, {"PATH": os.environ.get("PATH", ""), "HOME": str(home)}
    )

    if executable == "claude":
        argv = [executable, "--print", "--permission-mode", "plan"]
        cwd = root
    else:
        argv = [executable, "exec", "--sandbox", "read-only", "-c", 'approval_policy="never"']
        cwd = probe_repository(root)

    completed = subprocess.run(
        argv,
        input=LIVE_PROBE_PROMPT,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=LIVE_PROBE_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return f"{executable} could not complete a trivial invocation: {detail[:400]}"
    return None


@pytest.fixture(scope="session")
def live_providers_usable(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Skip the whole Tier 2 class unless both real CLIs complete a trivial turn.

    Session-scoped because each probe is a real, billable model turn, and because its outcome is a
    property of the machine rather than of any one test.
    """
    for executable in ("claude", "codex"):
        root = tmp_path_factory.mktemp(f"probe-{executable}")
        reason = live_provider_reason(executable, root)
        if reason is not None:
            pytest.skip(reason)


@pytest.fixture
def live_provider_home(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`isolated_home`, with one disposable copy of each configured account's credentials.

    Staged per test rather than per session, and inside the test's own redirected home, so no
    provider's client-side state survives into the next test and nothing is written back to the
    operator's account directory.
    """
    for variable, value in stage_live_provider_environment(isolated_home, {}).items():
        monkeypatch.setenv(variable, value)
    return isolated_home


@pytest.mark.live_cli
class TestLiveProviderSmokeAcceptance:
    """Section 27 Tier 2: one real Claude implementation invocation and one real Codex read-only
    review, against a disposable repository.

    Excluded from the default run and from CI by `addopts` (`-m 'not live_cli'`), and executable
    only during an authorized implementation or verification phase: it spawns real provider CLIs,
    which costs money and needs credentials this repository neither holds nor manages. Nothing in
    the default suite reaches this class.
    """

    def test_a_single_milestone_run_reaches_the_commit_gate_without_committing(
        self,
        tmp_path: Path,
        worktree: Path,
        live_providers_usable: None,
        live_provider_home: Path,
        config_factory: ConfigFactory,
    ) -> None:
        before = repository_evidence(worktree)
        application = MilestoneRunnerApplication(
            load_runner_config(
                config_factory(
                    providers={"allowed_environment_variables": LIVE_PROVIDER_ENVIRONMENT}
                )
            ),
        )
        report = application.start()
        record = application.status().record

        assert report.state is RunStatus.READY_FOR_COMMIT_APPROVAL, report.detail
        assert record is not None
        assert record.provider_runs != []
        assert record.successful_review_rounds == 1
        assert repository_evidence(worktree) == before

    def test_the_shipped_gates_execute_nothing_with_a_real_provider_run(
        self,
        tmp_path: Path,
        worktree: Path,
        live_providers_usable: None,
        live_provider_home: Path,
        config_factory: ConfigFactory,
    ) -> None:
        before = repository_evidence(worktree)
        prototype_before = prototype_snapshot()
        application = MilestoneRunnerApplication(
            load_runner_config(
                config_factory(
                    providers={"allowed_environment_variables": LIVE_PROVIDER_ENVIRONMENT}
                )
            )
        )
        application.start()
        approval = application.approve_commit()
        assert not approval.execution.executed
        assert repository_evidence(worktree) == before
        # DEC-016-006, against the snapshot taken before the run rather than against a second
        # reading of the same moment, which would compare nothing.
        assert prototype_snapshot() == prototype_before
