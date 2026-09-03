"""Engine-executed verification bundles (T-307): HEAD binding, ordering, and isolation."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_workflow_engine import verification_bundles
from ai_workflow_engine.models import VerificationBundleSettings
from ai_workflow_engine.verification_bundles import (
    SCRUBBED_KEYS,
    BundleCommandObservation,
    run_verification_bundles,
)


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def python_command(source: str) -> list[str]:
    """An argv that runs `source`, so a command's outcome is exact and shell-free."""
    return [sys.executable, "-c", source]


def bundle(
    name: str, *commands: list[str], timeout_seconds: int = 3600
) -> VerificationBundleSettings:
    return VerificationBundleSettings(
        name=name, commands=list(commands), timeout_seconds=timeout_seconds
    )


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """A two-commit repository whose worktree content differs from the first commit."""
    repository = tmp_path / "target"
    repository.mkdir()
    git(repository.parent, "init", "-b", "main", str(repository))
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "Workflow Tests")
    (repository / "marker.txt").write_text("one\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "first")
    (repository / "marker.txt").write_text("two\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "second")
    return repository


def head_of(repository: Path, revision: str) -> str:
    return git(repository, "rev-parse", revision)


def run(
    repository: Path, revision: str, *bundles: VerificationBundleSettings
) -> list[BundleCommandObservation]:
    return run_verification_bundles(
        repository=repository,
        repository_head=head_of(repository, revision),
        bundles=list(bundles),
    )


# ---- Exact HEAD binding (AC2) -------------------------------------------------


def test_commands_observe_the_recorded_head_not_the_worktree(target: Path) -> None:
    first = head_of(target, "HEAD~1")
    observations = run_verification_bundles(
        repository=target,
        repository_head=first,
        bundles=[
            bundle(
                "b",
                ["grep", "-q", "one", "marker.txt"],
                ["grep", "-q", "two", "marker.txt"],
            )
        ],
    )
    # The clone carries the recorded commit's content, not the tip the worktree is sitting on.
    assert [observation.exit_code for observation in observations] == [0, 1]


def test_the_clone_head_equals_the_recorded_object_id(target: Path) -> None:
    first = head_of(target, "HEAD~1")
    source = (
        "import subprocess,sys;"
        "head=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True)"
        ".stdout.strip();"
        f"sys.exit(0 if head == {first!r} else 3)"
    )
    observations = run_verification_bundles(
        repository=target, repository_head=first, bundles=[bundle("b", python_command(source))]
    )
    assert observations[0].exit_code == 0


def test_an_unavailable_recorded_head_fails_before_any_command_runs(target: Path) -> None:
    from ai_workflow_engine.agents.sandbox import SnapshotUnavailable

    with pytest.raises(SnapshotUnavailable):
        run_verification_bundles(
            repository=target,
            repository_head="0" * 40,
            bundles=[bundle("b", python_command("raise SystemExit(0)"))],
        )


# ---- Ordering and argv fidelity (AC3) -----------------------------------------


def test_selection_order_is_execution_order_with_one_global_index(target: Path) -> None:
    ok = python_command("raise SystemExit(0)")
    observations = run(
        target,
        "HEAD",
        bundle("first", ok, ok),
        bundle("second", ok),
        bundle("third", ok, ok),
    )
    assert [observation.index for observation in observations] == [0, 1, 2, 3, 4]
    assert [observation.bundle for observation in observations] == [
        "first",
        "first",
        "second",
        "third",
        "third",
    ]


def test_selection_order_is_never_sorted(target: Path) -> None:
    ok = python_command("raise SystemExit(0)")
    observations = run(target, "HEAD", bundle("zeta", ok), bundle("alpha", ok))
    assert [observation.bundle for observation in observations] == ["zeta", "alpha"]


def test_argv_is_recorded_exactly(target: Path) -> None:
    argv = python_command("raise SystemExit(0)")
    observations = run(target, "HEAD", bundle("b", argv))
    assert observations[0].argv == argv


# ---- Outcome mapping (AC3) ----------------------------------------------------


def test_non_zero_exit_is_evidence_not_an_error(target: Path) -> None:
    observations = run(target, "HEAD", bundle("b", python_command("raise SystemExit(3)")))
    assert observations[0].exit_code == 3
    assert observations[0].timed_out is False


def test_timeout_maps_to_124_and_is_flagged(target: Path) -> None:
    observations = run(
        target,
        "HEAD",
        bundle("b", python_command("import time; time.sleep(30)"), timeout_seconds=1),
    )
    assert observations[0].exit_code == 124
    assert observations[0].timed_out is True


def test_command_that_cannot_be_executed_maps_to_127(target: Path, tmp_path: Path) -> None:
    absent = tmp_path / "definitely-not-executable"
    observations = run(target, "HEAD", bundle("b", [str(absent)]))
    assert observations[0].exit_code == 127
    assert observations[0].timed_out is False


def test_a_failing_command_does_not_stop_the_remaining_commands(target: Path) -> None:
    observations = run(
        target,
        "HEAD",
        bundle(
            "b",
            python_command("raise SystemExit(5)"),
            python_command("raise SystemExit(0)"),
        ),
    )
    assert [observation.exit_code for observation in observations] == [5, 0]


# ---- No captured output -------------------------------------------------------


def test_observations_carry_no_stdout_or_stderr(target: Path) -> None:
    # The markers are assembled at run time so they appear in the command's *output* without
    # appearing in its argv, which is recorded verbatim and would otherwise mask the check.
    source = (
        "import sys; sys.stdout.write('OUT' + 'PUT_MARKER'); sys.stderr.write('ERR' + 'OR_MARKER')"
    )
    observations = run(target, "HEAD", bundle("b", python_command(source)))
    assert set(vars(observations[0])) == {"bundle", "index", "argv", "exit_code", "timed_out"}
    recorded = repr(observations[0])
    assert "OUTPUT_MARKER" not in recorded
    assert "ERROR_MARKER" not in recorded


# ---- Isolation: the target repository is never written -------------------------


def test_bundle_writes_land_in_the_sandbox_and_never_in_the_target(target: Path) -> None:
    before_head = head_of(target, "HEAD")
    before_content = (target / "marker.txt").read_text(encoding="utf-8")
    before_status = git(target, "status", "--porcelain=v1", "--untracked-files=all")
    before_tracked = git(target, "ls-files")

    writing = python_command(
        "import pathlib,subprocess;"
        "pathlib.Path('marker.txt').write_text('clobbered\\n');"
        "pathlib.Path('intruder.txt').write_text('new\\n');"
        "subprocess.run(['git','config','user.email','s@example.invalid'],check=True);"
        "subprocess.run(['git','config','user.name','Sandbox'],check=True);"
        "subprocess.run(['git','add','-A'],check=True);"
        "subprocess.run(['git','commit','-m','sandbox commit'],check=True)"
    )
    observations = run(target, "HEAD", bundle("b", writing))
    assert observations[0].exit_code == 0

    assert head_of(target, "HEAD") == before_head
    assert (target / "marker.txt").read_text(encoding="utf-8") == before_content
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == before_status
    assert git(target, "ls-files") == before_tracked
    assert not (target / "intruder.txt").exists()


def test_commands_run_inside_the_sandbox_clone_not_the_target(target: Path) -> None:
    source = (
        "import os,pathlib,sys;"
        f"sys.exit(0 if pathlib.Path(os.getcwd()).resolve() != pathlib.Path({str(target)!r})"
        ".resolve() else 4)"
    )
    observations = run(target, "HEAD", bundle("b", python_command(source)))
    assert observations[0].exit_code == 0


# ---- Unconditional teardown ---------------------------------------------------


def test_the_sandbox_is_removed_after_a_successful_run(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[Path] = []
    real = verification_bundles.create_sandbox

    def recording(repository: Path, repository_head: str) -> Path:
        sandbox = real(repository, repository_head)
        created.append(sandbox)
        return sandbox

    monkeypatch.setattr(verification_bundles, "create_sandbox", recording)
    run(target, "HEAD", bundle("b", python_command("raise SystemExit(0)")))
    assert created and not created[0].exists()


def test_the_sandbox_is_removed_even_when_execution_raises(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[Path] = []
    real = verification_bundles.create_sandbox

    def recording(repository: Path, repository_head: str) -> Path:
        sandbox = real(repository, repository_head)
        created.append(sandbox)
        return sandbox

    def exploding(*args: object, **kwargs: object) -> BundleCommandObservation:
        raise RuntimeError("infrastructure failure")

    monkeypatch.setattr(verification_bundles, "create_sandbox", recording)
    monkeypatch.setattr(verification_bundles, "_execute_command", exploding)
    with pytest.raises(RuntimeError, match="infrastructure failure"):
        run(target, "HEAD", bundle("b", python_command("raise SystemExit(0)")))
    assert created and not created[0].exists()


# ---- Environment (§6) ---------------------------------------------------------


def test_the_scrubbed_key_set_is_exactly_these_four() -> None:
    assert SCRUBBED_KEYS == ("PATH", "HOME", "LANG", "LC_ALL")


def test_a_command_sees_only_scrubbed_keys(target: Path) -> None:
    expected = sorted(key for key in SCRUBBED_KEYS if key in os.environ)
    source = "import os,sys;" f"sys.exit(0 if sorted(os.environ) == {expected!r} else 4)"
    observations = run(target, "HEAD", bundle("b", python_command(source)))
    assert observations[0].exit_code == 0


def test_a_bundle_runs_with_tmpdir_absent_from_the_parent_environment(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TMPDIR", raising=False)
    source = "import os,sys; sys.exit(0 if 'TMPDIR' not in os.environ else 4)"
    observations = run(target, "HEAD", bundle("b", python_command(source)))
    assert observations[0].exit_code == 0


def test_no_bundles_selected_runs_nothing(target: Path) -> None:
    assert run(target, "HEAD") == []
