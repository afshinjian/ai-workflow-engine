#!/usr/bin/env python3
"""Independent ORCH-001 post-approval probe (claude-code-independent-reviewer-orch-001-3).

Freshly written for this review; does not reuse, import or execute the
remediator's own probe.

Method (deliberately distinct from every prior probe on this stage, all of
which operated on a *single copied state file*): export the entire committed
tree at HEAD with `git archive` into an isolated throwaway directory, drive the
real `transition` CLI *inside that copy* to move ORCH-001 VERIFIED ->
REVIEW_APPROVED, then run the real pytest suite *inside that copy*, so
TestRealRepositoryState's REPO_ROOT resolves to the post-approval document and
the new durable-invariant tests are exercised end-to-end against a genuinely
approved governance state -- not merely via in-process helper calls.

Checks:
  1. Pre-approval: the copy's real-state tests pass; frontier is ORCH-001.
  2. No permanent pin: static scan for an unguarded literal frontier assertion.
  3. Approval simulated through the real CLI (CAS digest guard engaged).
  4. Post-approval: frontier == ORCH-002; copy's state still validates.
  5. Post-approval: full focused suite passes inside the copy (records
     pass/skip counts, and which tests skipped -- the coverage-gap question).
  6. The removed pinned assertion would have failed after the transition.
  7. ORCH-002 remains NOT_STARTED in the copy.
  8. The real repository is byte-for-byte untouched.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/afshin-jian/ai-workflow-engine")
STATE_REL = "docs/implementation/orchestration/implementation-state.yaml"
PLAN_REL = "docs/implementation/orchestration/implementation-plan.md"
SCRIPT_REL = "scripts/orchestration_feature_state.py"
TESTS_REL = "tests/test_orchestration_feature_state.py"

failures: list[str] = []
notes: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_state(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def frontier_of(state: dict) -> str | None:
    """Independent re-implementation of the frontier rule from
    session-protocol.md, NOT a call into the tool under review."""
    gb = state.get("blockers") or []
    if any(b.get("resolution") in (None, "") for b in gb):
        return None
    stages = state["stages"]
    for sid in state["delivery_order"]:
        st = stages.get(sid)
        if st is None or st["status"] == "REVIEW_APPROVED":
            continue
        if all(stages.get(p, {}).get("status") == "REVIEW_APPROVED" for p in st["prerequisites"]):
            return sid
    return None


def main() -> int:
    real_state = REPO / STATE_REL
    real_digest_before = sha256_file(real_state)
    head = run(["git", "rev-parse", "HEAD"], REPO).stdout.strip()
    status_before = run(["git", "status", "--porcelain"], REPO).stdout

    tmp = Path(tempfile.mkdtemp(prefix="orch001-reviewer3-"))
    try:
        work = tmp / "tree"
        work.mkdir()
        archive = tmp / "head.tar"
        with archive.open("wb") as fh:
            proc = subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"],
                cwd=str(REPO),
                stdout=fh,
                stderr=subprocess.PIPE,
            )
        check("git archive HEAD succeeded", proc.returncode == 0, proc.stderr.decode()[:200])
        subprocess.run(["tar", "-xf", str(archive), "-C", str(work)], check=True)

        copy_state = work / STATE_REL
        check("isolated copy of committed HEAD created", copy_state.is_file(), f"HEAD {head[:12]}")
        check(
            "copy's state file is byte-identical to the real one",
            sha256_file(copy_state) == real_digest_before,
        )

        # ---- 2. static scan: no permanent pin of the live frontier ----------
        src = (work / TESTS_REL).read_text(encoding="utf-8")
        # Bound the scan to TestRealRepositoryState only (the sole class that
        # reads the live governance document); later classes operate on
        # synthetic make_state() fixtures in tmp_path, where a literal stage
        # name is legitimate and cannot break on real-state advancement.
        after = src.split("class TestRealRepositoryState:", 1)[1]
        next_cls = re.search(r"^class \w+", after, flags=re.MULTILINE)
        real_state_cls = after[: next_cls.start()] if next_cls else after
        pinned = [
            ln.strip()
            for ln in real_state_cls.splitlines()
            if re.search(r"recompute_next_eligible\([^)]*\)\s*==\s*[\"']ORCH-", ln)
            or re.search(r"next_eligible_stage.*==\s*[\"']ORCH-", ln)
        ]
        check(
            "no unguarded pinned-stage assertion on the live document",
            not pinned,
            f"matches={pinned}",
        )
        guarded = [ln.strip() for ln in real_state_cls.splitlines() if 'if frontier == "ORCH-001"' in ln]
        notes.append(f"guarded self-disabling anchor present: {bool(guarded)} {guarded}")

        # ---- 1. pre-approval run inside the copy ---------------------------
        pre = run([sys.executable, "-m", "pytest", "-q", f"{TESTS_REL}::TestRealRepositoryState", "-v"], work)
        check("pre-approval TestRealRepositoryState passes in the copy", pre.returncode == 0, pre.stdout[-400:])
        state0 = load_state(copy_state)
        f0 = frontier_of(state0)
        check("pre-approval frontier (independently recomputed) is ORCH-001", f0 == "ORCH-001", str(f0))
        check("declared next_eligible_stage agrees", state0["next_eligible_stage"] == f0)
        check("ORCH-001 is VERIFIED / review PENDING before approval",
              state0["stages"]["ORCH-001"]["status"] == "VERIFIED"
              and state0["stages"]["ORCH-001"]["review_status"] == "PENDING")

        # ---- 3. approval through the real CLI ------------------------------
        digest = "sha256:" + sha256_file(copy_state)
        tr = run(
            [
                sys.executable, SCRIPT_REL, "transition",
                "--state", STATE_REL,
                "--stage", "ORCH-001",
                "--to", "REVIEW_APPROVED",
                "--actor", "probe-independent-reviewer-3",
                "--role", "REVIEWER",
                "--action", "PROBE_APPROVE_ORCH_001",
                "--reason", "reviewer-3 independent post-approval probe (isolated copy)",
                "--at", "2026-07-21T15:00:00Z",
                "--reviewer", "probe-independent-reviewer-3",
                "--review-status", "APPROVED",
                "--implementation-commit", head,
                "--add-review-evidence", "reviews/ORCH-001/probe.yaml",
                "--expected-digest", digest,
                "--output", "json",
            ],
            work,
        )
        check("real CLI transition VERIFIED -> REVIEW_APPROVED applied", tr.returncode == 0, tr.stderr[-300:])
        payload = json.loads(tr.stdout) if tr.returncode == 0 else {}
        check("CLI reports APPLIED", payload.get("status") == "APPLIED", str(payload)[:200])

        # ---- 4/7. post-approval state ---------------------------------------
        state1 = load_state(copy_state)
        f1 = frontier_of(state1)
        check("post-approval frontier is ORCH-002 (independent recomputation)", f1 == "ORCH-002", str(f1))
        check("CLI's own new_next_eligible_stage agrees", payload.get("new_next_eligible_stage") == "ORCH-002",
              str(payload.get("new_next_eligible_stage")))
        check("declared next_eligible_stage updated to ORCH-002", state1["next_eligible_stage"] == "ORCH-002")
        check("ORCH-001 recorded REVIEW_APPROVED/APPROVED",
              state1["stages"]["ORCH-001"]["status"] == "REVIEW_APPROVED"
              and state1["stages"]["ORCH-001"]["review_status"] == "APPROVED")
        check("ORCH-002 remains NOT_STARTED in the copy",
              state1["stages"]["ORCH-002"]["status"] == "NOT_STARTED")
        val = run([sys.executable, SCRIPT_REL, "validate", "--state", STATE_REL, "--plan", PLAN_REL, "--output", "json"], work)
        check("post-approval state validates in the copy", val.returncode == 0, val.stdout[-200:])

        # ---- 6. the removed pin would now fail ------------------------------
        check("removed pinned assertion (== 'ORCH-001') would now fail", f1 != "ORCH-001", f"frontier={f1}")

        # ---- 5. the new durable tests, post-approval, inside the copy -------
        post = run([sys.executable, "-m", "pytest", "-q", TESTS_REL, "-rs"], work)
        check("full focused suite passes post-approval inside the copy", post.returncode == 0, post.stdout[-600:])
        tail = post.stdout.strip().splitlines()[-1]
        notes.append(f"post-approval focused suite result line: {tail}")
        skipped = [ln.strip() for ln in post.stdout.splitlines() if ln.startswith("SKIPPED")]
        notes.append(f"post-approval skips: {skipped or 'none'}")

        post_real = run([sys.executable, "-m", "pytest", "-q", f"{TESTS_REL}::TestRealRepositoryState", "-v", "-rs"], work)
        check("post-approval TestRealRepositoryState passes in the copy", post_real.returncode == 0, post_real.stdout[-500:])
        notes.append(
            "post-approval real-state test outcomes: "
            + "; ".join(
                ln.strip()
                for ln in post_real.stdout.splitlines()
                if "TestRealRepositoryState" in ln or ln.startswith("SKIPPED")
            )
        )

        # ---- 8. real repository untouched -----------------------------------
        check("real state file byte-identical after probe", sha256_file(real_state) == real_digest_before)
        check("real repository git status unchanged", run(["git", "status", "--porcelain"], REPO).stdout == status_before)
        check("real repository HEAD unchanged", run(["git", "rev-parse", "HEAD"], REPO).stdout.strip() == head)
        live = load_state(real_state)
        check("live frontier still ORCH-001", frontier_of(live) == "ORCH-001")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    for n in notes:
        print("NOTE:", n)
    print()
    print("REVIEWER3_POST_APPROVAL_PROBE:", "PASS" if not failures else f"FAIL {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
