# Milestone 4 Architecture Plan — Controlled Commit and Push

Status: APPROVED (round 2, 2026-07-18). An independent fresh plan review — no memory of round 1 —
approved these contracts, confirming every safety property holds and that each residual ambiguity
fails safe (toward refusing a write, never toward an unauthorized one). Its five non-blocking
spec nits (apply_check error type, post-hoc message trailing-newline, allowed-paths sort/dedupe,
a forms undercount, stdin spelling) are folded in above. Round 1 had returned REJECTED with five
blocking findings; this revision remediated all of them:
B1 (unstage mechanism was self-contradictory) and B2/B3 (the substring-scanning allowlist was
both false-rejecting operand data and missing real dangers) are fixed by making `GitWriter` a
**typed-methods-only** class that builds a fixed argv shape per operation with no arbitrary-argv
path; B4 (the gate reads had no public API) is fixed by adding read-only methods to `GitClient`
that use forms already in the unchanged `READ_ONLY_FORMS`, and adding `git/client.py` to the
file list; B5 (push-gate divergence from the M-2 algorithm) is reconciled with an explicit
design note and a new strict `rev-list` reader. Reviewed by an independent session with no memory
of round 1, per `docs/AGENT_PROTOCOL.md`.

## Goal and hard boundary

Milestone 4 performs the first — and only — writable-Git operations this project makes on the
**target repository**: staging an explicitly approved set of paths, creating one commit, and
pushing once. Each **human-authorized** operation (commit, push) is bound to a per-invocation
**human approval artifact** that pins the exact branch, HEAD, and path set it authorizes. The one
non-human-approved writable op is the optional `apply-patch` bridge, which is instead bound to a
verified Milestone 3 `AgentRunRecord` and a live-HEAD check (never a human approval — see that
command's gate). Per `docs/milestones.md`: "Approval-bound staging allowlists, commit
verification, protected-path enforcement, remote/upstream checks, and explicit push gates."

The following decisions are binding:

1. `GitClient.READ_ONLY_FORMS` remains byte-for-byte unchanged as a tuple. Every writable Git
   operation goes through a **new, separate `GitWriter` class** (`src/ai_workflow_engine/git/
   writer.py`) that exposes **only typed methods** (`stage_paths`, `unstage_paths`, `commit`,
   `push`, `apply_patch`) — it has no public method that runs a caller-supplied argv. Each method
   constructs a single fixed argv shape internally (see "GitWriter"), so there is no scanning of
   operand data and no way to smuggle an unlisted or dangerous form through it. The read-only
   client and the writer are different objects; no read-only surface gains a write capability.
   `GitClient` may gain new **read-only** methods that use forms already present in
   `READ_ONLY_FORMS` (`diff`, `rev-list`, `rev-parse`, `show`); adding those methods does not alter the tuple.
2. **No commit or push happens without a matching, per-invocation human approval artifact.** A
   prior approval never carries forward to a later commit or push — each requires its own fresh
   artifact, echoing `docs/AGENT_PROTOCOL.md`. `workflow.allow_automatic_commit` and
   `workflow.allow_automatic_push` remain `false` and are never consulted to *bypass* a gate;
   they stay hard-blocked exactly as Milestone 1 requires.
3. The writer can express none of: `push --force`/`--force-with-lease`, remote branch deletion
   (`push --delete` or a `:`/`+`-refspec), `reset` (any mode), `commit --amend`/`-a`/`--all`,
   `add -A`/`add .`/glob pathspecs, `clean`, `rebase`, `merge`, `cherry-pick`, history rewriting,
   or branch creation/deletion — not because a denylist rejects those tokens, but because **no
   typed method emits them**. Each method's argv is a fixed template with only validated
   repo-relative path operands or the approved message filling the operand slots; there is no
   flag or refspec the caller can inject.
4. The push gate mirrors the Milestone 2 `push` prompt's algorithm mechanically (branch/HEAD/
   upstream equality, `rev-list --left-right --count` behind/ahead parsing, behind == 0, clean
   tree). Milestone 2 *described* this for an operator; Milestone 4 *executes* it, and the two
   must agree.
5. Milestone 4 consumes the Milestone 3 verified-patch artifacts conceptually (a scoped-write
   run's stored patch is what a human reviews before approving a commit) but does not *require*
   them: a human may approve a commit of the current working tree directly. Applying a stored
   `AgentRunRecord` patch to the working tree is an **optional** `writer`-gated step, not a
   precondition of committing.
6. No clock-derived value is part of an approval artifact's identity or any gate decision. (Git
   itself stamps the commit's author/committer dates; that is Git's own metadata, outside the
   artifact-identity hash.)

Milestone 4 must not add agent execution, prompt changes, or workflow-state model changes. It
may append a workflow event recording a completed `push` stage (the state machine already models
`push`), but only through the existing `record_outcome` path, never a new state surface.

## The approval artifact

A commit or push is authorized by a human-created YAML file the operator passes with
`--approval <file>`. It is strict (`extra="forbid"`) and its fields pin exactly what is
authorized:

```python
class CommitApproval(StrictModel):
    kind: Literal["commit"]
    task_id: str                 # M-2 normalized
    branch: str                  # the branch this approval authorizes a commit on
    head: str                    # the exact parent HEAD the commit must build on (40/64 hex)
    allowed_paths: list[str]     # repo-relative POSIX; exactly the paths that may be staged
    message: str                 # the commit message, verbatim
    approved_by: str             # a human identifier, recorded in the audit trail

class PushApproval(StrictModel):
    kind: Literal["push"]
    task_id: str
    branch: str                  # authorized branch
    head: str                    # authorized HEAD to be published (must be the live HEAD)
    upstream: str                # authorized upstream ref (e.g. origin/main)
    approved_by: str
```

`PushApproval` deliberately carries **no** `ahead`/`behind` counts, and this is where Milestone 4
reconciles its relationship to the Milestone 2 `push` prompt (see the push gate below). The M-2
prompt was rendered from a *snapshot* and therefore had to cross-check the live `rev-list` counts
against the *recorded* counts to detect drift between render time and execution time. The M-4
gate reads live Git state directly at the moment of the push, so there is no snapshot to drift
from — the live computation is itself the authority, and a recorded count would add nothing to
verify against. The *decision rule* is identical to M-2's ("behind must be zero, computed from
`git rev-list --left-right --count @{upstream}...HEAD`"); only the redundant recorded-count
cross-check, which exists solely because of M-2's render/execute split, is intentionally absent.

`allowed_paths` are normalized with the exact Milestone 2 `normalize_allowed_path` algorithm
(surrogate/NFC/backslash/rooted/drive/UNC rejection, repository containment, symlink-escape
defense), then **de-duplicated and code-point sorted** (exactly as `prompt/context.py` does for
the M-2 allowed-path list), and an empty result is rejected. This normalization happens in the
**commit gate**, not the approval loader: `normalize_allowed_path` needs the repository root and
the protected-path check needs `config.protected_paths`, neither of which the loader
(`load_commit_approval(path)`, which sees only the file) has — the gate is the first place both
are available. Every later "must equal `allowed_paths` exactly" comparison against
`staged_names()` / `commit_change_names()` (both of which return sorted lists) is therefore a
comparison of two sorted, de-duplicated lists. Protected paths (`protected_paths.never_stage` /
`never_commit`) are **rejected even if listed** in `allowed_paths` — the approval cannot override
a protected-path rule. `head`/`upstream` are validated shapes at load; existence is checked at
gate time against live Git.

The artifact is loaded, validated, and its `kind` must match the invoked command. There is no
signature/crypto in this milestone (it is a local-operator control, not an authentication
system); the audit trail records the file's SHA-256 and `approved_by` so a reviewer can see
exactly which artifact authorized which action. This limitation is stated honestly in the docs.

## `GitWriter` — the only writable surface

`GitWriter` exposes **only** these typed methods; it has no public `_run(args)` or any way to run
a caller-supplied argv. Each method builds one fixed argv template internally, validates its
operands, runs `git -C <repository> ...` once, and raises `GitWriteError` on nonzero exit.
`GitWriteError` is a new exception **defined in `git/writer.py`**, subclassing `ValueError` and
carrying a `code` attribute — matching the existing module-local error pattern
(`PromptStorageError(ValueError)` in `prompt/store.py`, `SandboxError(ValueError)` in
`agents/sandbox.py`, `ArtifactError(ValueError)` in `agents/artifacts.py`). It is not added to
`exceptions.py`. The CLI's `_protected` wrapper already catches any `Exception` and renders it as
`ERROR: <message>` (exit 2) without a traceback, so no change to the error-handling surface is
needed. Because the flag/subcommand positions are
literals baked into each template and only validated path or message operands ever fill the
operand slots (always after a `--` separator where pathspecs apply), none of the forbidden forms
in decision 3 is expressible.

```python
class GitWriter:
    def __init__(self, repository: Path) -> None: ...

    def stage_paths(self, paths: list[str]) -> None:
        # argv = ["add", "--", *paths]; each path validated repo-relative POSIX, non-empty,
        # no leading "-", not "." ; empty list is a caller error. No -A, no glob (the "--"
        # plus explicit paths means git treats each as a literal pathspec).

    def unstage_paths(self, paths: list[str]) -> None:
        # argv = ["restore", "--staged", "--", *paths]. Index-only; never touches the worktree.
        # Used solely by the commit gate's defensive abort path.

    def commit(self, message: str) -> None:
        # argv = ["commit", "-m", message]. `message` is an operand, never inspected for tokens.
        # No -a/--all/--amend possible.

    def push(self) -> None:
        # argv = ["push"]. Exactly that — no refspec, no --force, no --delete, no ":" spelling.

    def apply_check(self, patch: bytes) -> bool:
        # argv = ["apply", "--check", "-"]; patch on stdin. Dry run, performs no write; returns
        # True on exit 0 and False on GitWriteError (the writer's own error type; NOT
        # GitCommandError, which is GitClient's).

    def apply_patch(self, patch: bytes) -> None:
        # argv = ["apply", "-"]; patch on stdin (explicit "-" matches apply_check's spelling).
        # Never --index/--cached (worktree only).
```

Path operands are validated with the exact Milestone 2 `normalize_allowed_path` result form
(already repo-relative POSIX, no traversal); `stage_paths`/`unstage_paths` additionally reject an
empty list and any path beginning with `-` (defence in depth, though `--` already prevents option
interpretation). Every read the gates need goes through the read-only `GitClient` (extended
below), never the writer.

## `GitClient` read-only extension (B4)

The gates need three reads that `GitClient` does not yet expose. They are added as **new public
read-only methods** using forms already in `READ_ONLY_FORMS` (`diff`, `rev-list`, `rev-parse`, `show`), so the
`READ_ONLY_FORMS` tuple is unchanged and `git/client.py` is added to the file list:

```python
def staged_names(self) -> list[str]:
    # ["diff", "--cached", "--name-only", "-z"] -> sorted repo-relative POSIX list

def commit_change_names(self, parent: str, commit: str) -> list[str]:
    # ["diff", "--name-only", "-z", "--end-of-options", parent, commit] -> sorted list

def commit_parent(self, commit: str) -> str:
    # ["rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}~1"] -> parent hash
    # (rev-parse is already in READ_ONLY_FORMS)

def commit_message(self, commit: str) -> str:
    # ["show", "--no-patch", "--format=%B", "--end-of-options", commit] -> exact message
    # (show is already in READ_ONLY_FORMS)

def strict_left_right_count(self) -> tuple[int, int]:
    # ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"]
    # Parse the sole line as exactly "<behind>\t<ahead>\n" (two base-10 nonneg ints, one tab,
    # one terminal newline); return (behind, ahead). This is the exact M-2 push command and
    # parse. The existing lax `ahead_behind()` (HEAD...upstream, .split()) is left untouched
    # for the inspect/prompt path; the push gate uses only this strict method.

def diff_check(self) -> bool:
    # ["diff", "--check"] -> True when exit 0 (no conflict markers / whitespace errors).
    # `_run` raises on nonzero; the method catches GitCommandError and returns False.
```

`apply --check` (a non-mutating dry run) cannot live on the read-only client because `apply` is
not in `READ_ONLY_FORMS` and must not be added there (that would let the read client run a real
`apply`). It is therefore a typed method on `GitWriter` — `apply_check(patch) -> bool`, argv
`["apply", "--check", "-"]` — alongside the mutating `apply_patch`. Both are the writer's domain;
`apply_check` simply performs no write.

`commit_change_names` uses `--end-of-options` so a caller-supplied ref can never become an option
(the same defence `read_commit_blob` already uses). All three parse NUL-delimited (`-z`) output
where applicable so paths with spaces are handled exactly.

## Gate algorithms

### `workflowctl commit --config <c> --approval <file>`

1. Load config and the `CommitApproval` (kind must be `commit`).
2. Read live state via `GitClient`: branch, HEAD, `status()`.
3. **Branch/HEAD gate:** live branch must equal `approval.branch`; live HEAD must equal
   `approval.head` (the commit builds on exactly the approved parent). Mismatch → `FAIL`
   (`branch_mismatch` / `head_mismatch`), no write.
4. **Clean-index precondition:** the index must start empty — `status().staged_files` is `[]`.
   A non-empty index is `index_not_clean` and fails before any write. This is what makes step 6
   a defensive assertion rather than a routine branch: because nothing was staged before and we
   stage exactly `allowed_paths`, the resulting staged set is exactly `allowed_paths` whenever
   the gate itself is correct.
5. **Path gate:** the set of paths to stage is exactly `approval.allowed_paths`. Each must (a)
   pass `normalize_allowed_path`; (b) not match `never_stage`/`never_commit` (`protected_path_
   violation`); (c) actually exist as a change in the working tree (modified/added/deleted) —
   an approved path with no change is `nothing_to_stage`. The live set of changed paths
   (`modified ∪ untracked` from `status()`, plus deletions) must be a **subset** of
   `allowed_paths`; any changed path outside the approved set is `unapproved_change` and fails
   the gate (so a commit can never quietly include an un-approved edit). Combined with (c), the
   live changed set equals `allowed_paths` exactly. Deletions are staged by `stage_paths` too
   (`git add -- <path>` stages a deletion).
6. **Stage:** `GitWriter.stage_paths(allowed_paths)`.
7. **Pre-commit verification (defensive assertion):** `GitClient.staged_names()` must equal
   `allowed_paths` exactly. Under the clean-index precondition this cannot fail unless something
   external raced; if it does, abort **before** committing and call
   `GitWriter.unstage_paths(allowed_paths)` to restore the empty index, then FAIL
   (`staged_set_mismatch`). `unstage_paths` is `git restore --staged -- <paths>`, index-only,
   and is the sole caller of that method.
8. **Commit:** `GitWriter.commit(approval.message)` (argv `["commit", "-m", message]`; the
   message is an operand and is never scanned).
9. **Post-hoc commit verification:** the new HEAD's parent (`GitClient.commit_parent(new_head)`)
   must equal `approval.head`; `GitClient.commit_change_names(approval.head, new_head)` must equal
   `allowed_paths` exactly. For the message, `git commit -m X` stores exactly `X` while
   `commit_message` reads `%B` which git returns with a single trailing newline; the check
   therefore compares `commit_message(new_head).rstrip("\n") == approval.message.rstrip("\n")`
   (both sides right-stripped of trailing newlines) so a correct commit never spuriously trips.
   Any mismatch is `commit_mismatch` and is reported loudly (the commit exists but is flagged —
   Milestone 4 does not auto-revert; a human decides).
10. Emit a `CheckResult` (`check_name="commit"`), PASS only when every gate passed and post-hoc
    verification matched. Record the approval file's SHA-256 and `approved_by` in the evidence.

### `workflowctl push --config <c> --approval <file>`

Applies the Milestone 2 `push` prompt's decision rule mechanically (see the `PushApproval`
reconciliation note above for why there is no recorded-count cross-check):

1. Load config and `PushApproval` (kind `push`).
2. Live reads: branch, HEAD, upstream, `status()`.
3. Require live branch == `approval.branch`, live HEAD == `approval.head`, live upstream ==
   `approval.upstream` (and non-null), and all of modified/staged/untracked empty. Any mismatch
   is the corresponding `*_mismatch` / `dirty_worktree` finding; no push.
4. **Commit-chain gate:** `GitClient.strict_left_right_count()` runs the exact
   `git rev-list --left-right --count @{upstream}...HEAD` and returns `(behind, ahead)` from the
   strict `"<behind>\t<ahead>\n"` parse; require behind == 0 (`behind_remote` otherwise — a
   fast-forward is impossible; refuse) and ahead > 0 (`nothing_to_push` otherwise).
5. `git diff --check` clean (no conflict markers / whitespace errors) via a `GitClient` read.
6. **Only if every gate passes:** `GitWriter.push()` once (argv exactly `["push"]`).
7. Emit `CheckResult` (`check_name="push"`); PASS only after a successful push. Any gate failure
   exits 1 with the specific finding and performs no push.

### `workflowctl apply-patch --config <c> --run-id <id> --task-id <t> --stage <s>` (optional)

Applies a Milestone 3 verified patch to the working tree, gated: load + re-verify the
`AgentRunRecord` (must exist, verification PASS, mode scoped-write); live HEAD must equal the
record's `repository_head`; `GitWriter.apply_check(patch)` must pass; the patch's paths must not
overlap the live modified/staged/untracked sets (never clobber un-committed human work). Only then
`GitWriter.apply_patch(patch)`. This is a convenience bridge from M-3 to a subsequent `commit`; it
is not required and stages nothing (the human still approves the commit separately). Because it is
bound to a verified run artifact and a HEAD check rather than a human approval, it is the one
writable op that is not human-approval-gated (per the goal section) — and it only ever writes what
an already-verified, already-reviewed patch contains.

## CLI, output, exit codes

`commit`, `push`, and `apply-patch` follow the existing command conventions: `--config` required;
human/JSON `--output`; a gate failure is a `CheckResult` `FAIL` → exit 1; a configuration/
approval/IO error runs through `_protected` → `ERROR: <message>` on stderr, exit 2; success exits
0. JSON output is Rich-free canonical bytes on stdout (the T-104 discipline). No command writes
anything on a `FAIL` or `ERROR` path.

## Exact planned files

- add `src/ai_workflow_engine/git/writer.py`
- add `src/ai_workflow_engine/git/approval.py` (the two approval models + loader)
- add `src/ai_workflow_engine/commit/__init__.py`
- add `src/ai_workflow_engine/commit/gates.py` (the commit/push/apply-patch gate logic)
- modify `src/ai_workflow_engine/git/client.py` (new read-only methods `staged_names`,
  `commit_change_names`, `commit_parent`, `commit_message`, `strict_left_right_count`,
  `diff_check` — all using forms already in `READ_ONLY_FORMS`, which is byte-unchanged)
- modify `src/ai_workflow_engine/cli.py` (the three commands)
- modify `docs/configuration.md`, `docs/architecture.md`, `README.md`
- add `tests/test_git_writer.py`
- add `tests/test_approval.py`
- add `tests/test_git_client_reads.py` (the six new read-only methods, incl. the strict
  `rev-list` parse)
- add `tests/test_commit_gates.py`
- add `tests/test_push_gates.py`
- add `tests/test_apply_patch_gate.py`
- modify `tests/conftest.py` (a helper for a temp repo with a local `file://` remote)
- modify `tests/test_cli.py`

The prompt package and the workflow state model are unchanged. This file list finalizes the
Milestone 4 breakdown that `docs/MASTER_ROADMAP.md` (T-401) authorized: it deliberately does
**not** touch `models.py`, `self-governance.yaml`, or `examples/amozesh_konkur.yaml` (which the
roadmap anticipated as *possible*), because Milestone 4 adds no `EngineConfig` schema field — the
approval is a separate per-invocation artifact, not config. The version bump to 0.3.0 belongs to
the T-404 closeout, not this implementation list.

## Testing strategy

All write-path tests run against disposable temp repositories; push tests use a bare local
`file://` remote (`git init --bare`, `git remote add`, `git push -u` for setup). Coverage:

- **Approval models:** strict rejection of unknown fields, wrong `kind`, malformed head/upstream,
  and protected paths listed in `allowed_paths`; normalization of `allowed_paths`.
- **GitWriter (typed methods, not a denylist):** each method emits exactly its fixed argv shape
  (asserted by capturing the argv); `stage_paths` always inserts `--` before paths and rejects an
  empty list or a leading-`-` path; there is no public method that accepts arbitrary argv, so
  `--force`/`--amend`/`-a`/`reset`/`clean`/`push --delete`/`:`-refspec/`+`-refspec are structurally
  unreachable (proven by the absence of any argv-taking entry point, not by a denylist test); a
  commit message containing the literal word "reset" commits fine (proving operand data is never
  scanned); `READ_ONLY_FORMS` proven byte-unchanged.
- **GitClient reads:** `staged_names`, `commit_change_names`, `commit_parent`, `commit_message`,
  `diff_check`, and the strict `strict_left_right_count` — including the exact
  `"<behind>\t<ahead>\n"` parse and rejection of any other shape; `--end-of-options` guards on
  ref-taking methods.
- **Commit gate:** refusal-by-default (no approval → no commit); branch/HEAD mismatch;
  non-clean starting index (`index_not_clean`); a changed path outside `allowed_paths`
  (`unapproved_change`); an approved path with no change (`nothing_to_stage`); a protected path in
  the approval; post-hoc `commit_mismatch` (parent / path-set / message, each independently); the
  happy path produces exactly the approved commit and nothing else; deletions; a commit message
  containing shell/git-flag-looking text round-trips exactly.
- **Push gate:** refusal-by-default; branch/HEAD/upstream mismatch; dirty tree; nonzero behind
  (`behind_remote`); ahead == 0 (`nothing_to_push`); the exact strict `rev-list` parse; the happy
  path pushes once to the `file://` remote and the remote ref advances; proof that no gate failure
  ever reaches `GitWriter.push` (e.g. by asserting the remote ref is unchanged after each refusal).
- **apply-patch:** every precondition individually violated and refused with nothing changed
  (missing/unverified/wrong-mode record, HEAD drift, `apply_check` failure, dirty-overlap); the
  happy path changes exactly the patch's paths in the working tree (index untouched).
- **CLI:** human/JSON/exit-code contracts; JSON Rich-free under `FORCE_COLOR`; `_protected`
  exit-2 on bad approval/config; no filesystem/Git write on any FAIL/ERROR path.
- **Regression:** the full existing suite stays green; `allow_automatic_commit`/`_push` remain
  false and are never consulted to bypass a gate.

## Versioning

Milestone 4 closes at version `0.3.0` (SemVer minor: backward-compatible CLI additions, no
breaking change to existing surfaces). `docs/PROJECT_STATE.md` and `pyproject.toml` bump together
so the `version` fact stays consistent (0.3.0 still matches the current `0\.\d+\.\d+` pattern;
the 1.0.0 regex fix remains T-501).

## Plan Review disposition

APPROVED by an independent round-2 review (2026-07-18). Round 1's five blocking findings (B1–B5)
and both rounds' non-blocking notes are remediated above. Implementation may proceed: T-402
(staging + commit gate), then T-403 (push gate + apply-patch), then T-404 (closeout at 0.3.0).

One item is flagged for explicit human awareness (round-2 finding N4): `apply-patch` is a third
writable command and the sole writable op **not** bound to a per-invocation human approval —
it is instead gated by a verified Milestone 3 run artifact, a live-HEAD match, an `apply --check`
dry run, and a no-overlap check, and it only ever writes the working tree (never stages, commits,
or pushes). It is the bridge that lets a human actually use a scoped-write agent's verified patch.
The reviewer confirmed it is not a gate hole and that T-401 was delegated authority to finalize
the M-4 surface; it is retained. A human who prefers M-4 to be *exclusively* human-approval-gated
may direct that `apply-patch` be dropped (the primary commit/push loop does not depend on it).
