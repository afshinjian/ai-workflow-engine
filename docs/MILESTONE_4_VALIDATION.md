# Milestone 4 Validation Report

Evidence that Milestone 4 (controlled commit and push) works, produced by running the real
`workflowctl` commands against a throwaway repository with a local `file://` remote. Milestone 4
was built across tasks T-401..T-404; the plan review took two rounds (five blocking findings
remediated), and every implementation review is recorded in `docs/CHANGELOG.md`. Normative
specification: `docs/milestone-4-plan.md`.

## What Milestone 4 delivered

- **A separate writable-Git surface** (`git/writer.py`): `GitWriter` exposes only typed methods
  (`stage_paths`, `unstage_paths`, `commit`, `push`, `apply_check`, `apply_patch`), each a fixed
  argv shape with no arbitrary-argv path — force-push, remote-branch deletion, `reset`,
  `commit --amend`/`-a`, `add -A`/glob, and `clean` are *structurally unreachable*. The read-only
  `GitClient.READ_ONLY_FORMS` tuple is byte-unchanged; the six new gate-read methods use only
  forms already in it.
- **Per-invocation human approval artifacts** (`git/approval.py`): a `CommitApproval` pins the
  branch, parent HEAD, exact allowed-path set, and message; a `PushApproval` pins branch, HEAD,
  and upstream. `allow_automatic_commit`/`allow_automatic_push` stay hard-false and are never
  consulted to bypass a gate; a prior approval never carries forward.
- **`workflowctl commit`** — stages exactly the approved paths, refuses any un-approved or
  protected-path change, refuses a dirty index or branch/HEAD mismatch, commits, and re-verifies
  the resulting commit's parent, path set, and message.
- **`workflowctl push`** — mechanically applies the Milestone 2 push algorithm (branch/HEAD/
  upstream equality, `git rev-list --left-right --count @{upstream}...HEAD` with `behind == 0`,
  clean tree) and then pushes exactly once.
- **`workflowctl apply-patch`** (optional) — applies a verified Milestone 3 patch to the working
  tree only, gated by the run artifact + live-HEAD match + clean-tree + `apply --check` +
  a patch-digest re-check. It is the one writable op bound to a run artifact rather than a human
  approval; it never stages, commits, or pushes.

## Suite and standing checks (run at version 0.3.0)

```
$ pytest -q                     -> 684 passed
$ FORCE_COLOR=3 pytest -q       -> 684 passed
$ ruff check .                  -> All checks passed
$ black --check .               -> 69 files unchanged
$ mypy src                      -> Success: no issues in 44 source files
$ workflowctl verify --config self-governance.yaml  -> Verdict: PASS (all four checks)
```

## Full-cycle demonstration (real `workflowctl` output)

A throwaway repository with a bare local `file://` remote. A working tree with one approved
change (`feature.txt`) and one un-approved change (`unrelated.txt`):

```
1. commit with an un-approved change present:
   FAIL commit: Working tree has changes outside the approved path set | exit 1
2. commit after removing the un-approved change:
   PASS commit: Committed 1 approved path(s) as bebf27901d6f | exit 0
   committed: feature.txt | message: add feature
3. push the approved commit:
   PASS push: Pushed 1 commit(s) to origin/main | exit 0
   remote advanced: True | remote == local HEAD: True
```

Step 1 is the core safety property: a commit **cannot** quietly include a change outside its
approval — the gate refuses and writes nothing. Step 2 commits exactly the one approved path with
exactly the approved message. Step 3 advances the remote ref by exactly the approved commit.

## Boundary honored

Every writable operation goes through `GitWriter`'s typed methods; the read-only `GitClient` and
its allowlist are unchanged. No commit or push happens without a matching per-invocation approval
artifact, and no gate failure ever reaches a write (the push tests assert the remote ref is
unchanged after every refusal; the apply-patch tests assert the working tree is unchanged after
every refusal). `apply-patch` writes the working tree only, never the index. No clock value
enters an approval's identity or any gate decision.

## Limitations / notes

- Approval artifacts are a local-operator control, not an authentication system: there is no
  signature/crypto. The gate records the approval file's SHA-256 and `approved_by` in its audit
  trail so a reviewer can see exactly which artifact authorized which action.
- `apply-patch` is the one writable op not human-approval-gated (it is bound to a verified M-3 run
  artifact instead). This was flagged for explicit human awareness in
  `docs/milestone-4-plan.md`'s disposition and retained per the approved plan.
- The `version` governance-fact regex still only matches `0.x.y`; 0.3.0 is fine, but the 1.0.0
  bump requires the regex fix scheduled as T-501.
