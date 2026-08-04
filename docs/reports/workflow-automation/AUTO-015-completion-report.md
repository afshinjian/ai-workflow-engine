# AUTO-015 — Completion Report

| Field | Value |
|---|---|
| Stage | AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation |
| Branch | `feature/auto-015-successor-planning` |
| Contract | `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) |
| Baseline commit | `54530019bd809d2e1bcfc2f8456723ffc0a0814d` |
| Status | Implemented and fully validated; stopped at the Human Owner decision gate (§30) |

## Verdict

AUTO-015 is implemented as the Core Engine Planning Service DEC-001 selected: a new
`src/ai_workflow_engine/successor_planning/` subpackage plus one additive, read-only
`workflowctl successor-planning propose` Typer subcommand group. The capability resolves this
repository's own identity and Git baseline, takes a hashed evidence snapshot of every §8
authoritative source, reconciles the Task Queue against its mirrors and registries, validates the
required `--predecessor`, loads the static authoritative catalog, evaluates deterministic
eligibility, applies DEC-004/DEC-005's recommendation policy, renders and structurally validates
the governed prompt, assembles a hash-bound proposal artifact labelled `NOT_AUTHORIZED`, re-snapshots
and compares before publishing, and publishes once — atomically, no-clobber, into an external
repository-scoped root outside this repository entirely.

It selects nothing, registers nothing, authorizes nothing, invokes no provider, and mutates no Git,
task, Registry, workflow or governance state. Its single side effect is the artifact write, and
`--dry-run` removes even that while still performing every inspection and validation.

## Implementation completed

| File | Role |
|---|---|
| `successor_planning/models.py` | Strict Pydantic models: Candidate (§10.1), the proposal artifact (§16.1), `RepositoryIdentity` (§7.1), the §12/§13 outcome and failure taxonomies, and canonicalization (§16.2). |
| `successor_planning/snapshot.py` | Repository identity, Git baseline, the thirteen-step evidence-snapshot protocol, drift detection, DEC-010's canonical repository ID and artifact root. |
| `successor_planning/sources.py` | Typed readers for every §8 authoritative source, mirror/registry reconciliation, and §4.1 predecessor resolution. |
| `successor_planning/catalog.py` | The DEC-003 static authoritative catalog reader, §10.2's duplicate/conflict rules and the dependency graph. |
| `successor_planning/eligibility.py` | §11's deterministic per-candidate policy and §12's result-variant selection. |
| `successor_planning/redaction.py` | The new, isolated core secret-redaction utility (§19.3). |
| `successor_planning/prompt.py` | The §14 governed-prompt renderer and §15 structural validator. |
| `successor_planning/proposal.py` | Hash-bound assembly, §11.3 refusal records, §16.4 load-time re-verification, and the flow-composing application entry point `propose_successor` (§5). |
| `successor_planning/store.py` | §17.2's atomic, no-clobber, content-addressed publication protocol. |
| `cli.py` | The one additive `successor-planning propose` command, following the `prompt_app`/`check-*` pattern. No existing command changed. |

### The CLI is a thin adapter

`cli.py` gained `successor_planning_app` and `successor_planning_propose` and nothing else. The
command validates command-line syntax, hands four inputs (`--config`, `--predecessor`, `--output`,
`--dry-run`) to `successor_planning.proposal.propose_successor`, and renders the typed `ProposalRun`
it gets back. No eligibility, repository, catalog, prompt, publication or authorization logic lives
in the CLI, per §23.2/§23.3.

`--predecessor` is deliberately optional at the parser level and required by the contract: making it
a required Typer option would replace §13's `MISSING_PREDECESSOR` with a parser usage error that says
nothing about the governance contract, so the classification stays where §4.1 puts it — in the
planning service.

Human output is written directly to stdout rather than through Rich, for the same reason
`_emit_prompt_success` already does: Rich soft-wraps to the console width and highlights numbers and
paths, which would silently corrupt a digest, an artifact path or a failure code.

## Design notes

### Residual risk of the snapshot protocol (§7.4, restated as that section requires)

The evidence-snapshot protocol is **not** an OS-level atomic snapshot. No filesystem-level
point-in-time isolation is taken and no lock is held across the read window. A sufficiently
precisely-timed concurrent writer could in principle alter a file *between* an individual file's own
read and its own hash within a single pass, or between two different files' reads within the same
pass, producing a read that is individually self-consistent per file but not perfectly atomic
*across* files at the same instant. The mitigation is not perfection but fail-closed detection at the
boundary that matters: the full re-snapshot immediately before publication guarantees that whatever
was actually published is provably identical, byte-for-byte and field-for-field, to a state that
existed at two distinct, individually-hashed points in time (initial read and pre-publication check)
— it does not guarantee that no third, intermediate state existed which neither snapshot observed.
This residual risk is judged acceptable because (a) AUTO-015 is a local, single-operator, read-only
advisory tool with no security boundary between the invoking operator and the repository, and (b) the
fail-closed re-check makes exploiting the residual window require winning a race against a re-hash
that happens immediately before the one write AUTO-015 ever performs — not a standing window an
attacker can probe repeatedly. **This is not perfect isolation and must never be described as such.**

`O_NOFOLLOW` is a POSIX facility. Where the platform exposes it the snapshot's open is atomically
no-follow; where it does not, the implementation degrades to "check `is_symlink()`, then open", which
is check-then-use and is a genuine residual TOCTOU gap in that narrow case (§7.5). A symlinked
*parent directory component* is outside `O_NOFOLLOW`'s reach entirely; that case is caught after the
fact by the device+inode and content comparison, not before the fact by the open.

### Where the non-`EngineConfig` inputs come from

DEC-011 states that policy and identity inputs come only from validated configuration and this
contract, and §23.4 confirms `self-governance.yaml` needs no new field. The active `EngineConfig`
therefore supplies every location it already defines (task queue, both mirrors, project state, stage
registries, handover manifest and files). The four locations it does not define — the decision log,
the open-questions register, the completion-report directory and the candidate catalog — are fixed as
contract constants in `proposal.py`, naming exactly the documents §8, §9 and §23.6 name. They are
constants rather than new configuration fields precisely because widening the configuration surface
would broaden a contract this stage may only implement.

The DEC-010 repository ID is derived from the primary remote URL, which is read from the
repository's own `.git/config` as ordinary bytes through the same bounded, no-follow read discipline
every other file read uses. That is not a Git *command*: `GitClient.READ_ONLY_FORMS` admits neither
`git remote` nor `git config`, and widening that allowlist would open exactly the new,
independently-audited Git access path §7.1 forbids. `.git/config` is not a §8 authoritative source
and therefore never enters the evidence manifest or the proposal hash — it identifies where the
artifact is published, nothing more. The upstream this invocation actually observed selects the
remote; `origin` is used only when there is no upstream, and a lone remote only when there is no
`origin`. Zero remotes, or several with neither an upstream nor an `origin`, is a fail-closed
`REPOSITORY_IDENTITY_MISMATCH` — nothing is guessed.

### Milestone-plan correction recorded

`proposal.py` was created in M04 with the assembly primitives `build_proposal`, `build_refusal` and
`load_and_verify`. §23.2 fixes the CLI as a thin adapter delegating *entirely* to
`successor_planning.proposal`, so the flow-composing operation could not live in `cli.py` and no
other authorized file could host it. Under the Human Owner scope ruling of 2026-08-04, `proposal.py`
was reopened **additively** for M07 to add that entry point only. M04's three primitives keep their
behaviour and signatures unchanged; the cumulative AUTO-015 contract allowlist is unchanged.

## Correction round — three independent-review blockers closed

An independent review of the implementation raised three High blockers. All three were reproduced
first, then closed with the smallest change that satisfies the contract. No other finding was
addressed, and no file outside §23's allowlist was touched.

### AUTO015-REV-001 — secret-bearing catalog fields reached the persisted artifact

Redaction ran only while rendering the prompt. `catalog.candidates` was passed unchanged into
`build_proposal`, so a recognized credential inside a *valid* candidate's `mission` was serialized
verbatim into `candidate_list` (§16.1) — §22 invariant 2 requires every document-sourced string to be
redacted "before being embedded in any rendered span **or persisted field**".

`catalog.py` now redacts every repository-sourced free-text field of a candidate — `title`,
`mission`, each `required_owner_decisions` entry, and the two declared status strings — before that
candidate leaves the reader, and re-derives its §10.1 `content_hash` from the redacted definition so
§16.4's load-time re-derivation still holds over what was actually persisted. Every other candidate
field is a closed enum, a grammar-checked identifier, a repository-relative path, a digest or an
integer, none of which can hold a credential the §19.3 patterns recognize. Each redaction is surfaced
as a `SECRET_REDACTED` warning on the artifact, never a silent substitution. `safe_message` — which
quotes rejected field text into a persisted `warnings`/`errors` message — passes through the same
utility. When a redacted value is no longer representable under its own §10.1 bound (a replacement
marker pushing it past its ceiling, or two owner decisions collapsing onto one string), §14.2 forbids
truncating or merging, so the invocation refuses with §13's `SECRET_DETECTED`.

### AUTO015-REV-002 — the §4 item 6 preflight was never performed

Nothing in the flow classified unrecognized successor state, and
`UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED` appeared only in the failure-code table.

`sources.check_no_unauthorized_successor` now runs immediately after configuration load, before the
evidence-snapshot pass begins, over the three surfaces §4 item 6 names:

- **Branches** — every loose reference under `.git/refs/heads` and `.git/refs/remotes` plus
  `packed-refs`, read as ordinary bytes. `GitClient.READ_ONLY_FORMS` admits no branch-listing form,
  and widening that allowlist would open exactly the new Git access path §7.1 forbids; this is the
  same discipline the primary-remote resolution already uses for `.git/config`.
- **Source symbols** — path components under `src/`, plus module-level definitions and bindings in
  each `.py` file. Only *names* are examined, so a document or docstring that merely mentions a later
  stage is never mistaken for an implementation of one.
- **Registry rows** — every configured stage registry's own rows.

A stage identifier counts as a successor only when its number is strictly greater than AUTO-015's,
which is §4 item 6's category (a) — this implementation itself — with no lookup needed. Category (b)
is recognized by the one observable artifact the contract names for it: the candidate's own distinct
contract at `docs/workflow-automation/stage-prompts/<STAGE_ID>.md`. Anything in neither category fails
closed.

One sub-clause of §4 item 6 was **not** implementable as written and is recorded here rather than
guessed at: the clause validating AUTO-015's "package identity … against the version recorded in this
contract's implementation manifest (§22)" cites §22, which is the Security Invariants section and
defines no implementation manifest. No such manifest exists anywhere in the contract or repository, so
no version comparison was invented for it. The rest of item 6 is implemented in full.

### AUTO015-REV-003 — the four mandated governance checks were not all required

Only `check_git` was run (inside identity resolution, where §7.2 rule 4's one documented
`upstream_missing` tolerance applies to it). The narrower mirror/Registry reconciliation is not
equivalent to `check-governance`: conflicting configured governance facts across `PROJECT_STATE.md`
and another configured path fail that check and are invisible to any status reconciliation.

`sources.run_required_governance_checks` now composes the existing
`check_task_state`/`check_governance`/`check_registries`/`check_handover` validators unmodified —
§23.4 records `governance/validators.py` as needing no change and §24 makes `governance/**` a
forbidden surface, so a locally corrected second copy is exactly what both rules exist to prevent —
and every one of the four must pass before candidate evaluation. A check that raises has not passed
and is treated as a failure. §13 defines no code of its own for "a `workflowctl verify` check
failed" and this stage may not widen the taxonomy, so each finding is placed under the existing code
whose stated meaning covers it: an unreadable handover document is `AUTHORITATIVE_SOURCE_MISSING`
(§8 item 10, §13), an over-count of `Current` tasks is §4 item 3's `CONFLICTING_CURRENT_TASK`, and
every other finding is the whole-evidence-set inconsistency §11.3 refuses on
(`MIRROR_CONTRADICTION`). The reconciliation record is kept alongside, because a boolean
`CheckResult` cannot carry the typed, artifact-embedded disagreement §8 requires the proposal to
show.

### Ordering consequence recorded

§4 orders item 6 before item 3, so a Registry row for an uncontracted later stage now refuses before
a conflicting `Current` task is reached. One existing CLI test exercising `CONFLICTING_CURRENT_TASK`
used an `AUTO-016` Registry row for its fixture; it now also writes that stage's own contract, so the
row is recognized under category (b) and the test still exercises the condition it was written for.

## Validation

Every command below was run in the `ai-workflow-engine` conda environment against this branch.

| Check | Result |
|---|---|
| `pytest -q` | PASS — 4,007 passed, 32 deselected (214s) after the correction round; 3,983 before it |
| `pytest -q -m live_cli -rs` | PASS — 32 passed, 3,983 deselected; no authentication skips. Wall time varies run to run (412s and 823s observed) because these tests spawn real provider CLIs. |
| `ruff check .` | PASS |
| `black --check .` | PASS — 244 files unchanged |
| `mypy --strict` | PASS — no issues in 134 source files |
| `pre-commit run --all-files` | PASS — ruff, black, mypy |
| `pip wheel --no-deps` | PASS — `ai_workflow_engine-1.0.0-py3-none-any.whl`, 837,435 bytes |
| Out-of-tree import from a fresh venv | PASS — see below |
| `git diff --check` | PASS |
| `workflowctl check-task-state --config self-governance.yaml` | PASS before and after — 1 Current, 49 Done, 6 Planned |
| `workflowctl check-governance --config self-governance.yaml` | PASS before and after |
| `workflowctl check-registries --config self-governance.yaml` | PASS before and after — 25 stages across 2 registries |
| `workflowctl check-handover --config self-governance.yaml` | PASS before and after |
| Changed-path allowlist (`git status --porcelain`) | PASS — every path inside §23 |
| Forbidden destructive commands / commit / push / PR / merge | PASS — none run |

### Packaging and out-of-tree import evidence

The wheel was built with `pip wheel --no-deps` into `/tmp/auto015-wheel` and contains all ten
`successor_planning` modules:

```text
ai_workflow_engine/successor_planning/{__init__,catalog,eligibility,models,prompt,
                                       proposal,redaction,snapshot,sources,store}.py
```

A fresh virtual environment was created outside the repository (`/tmp/auto015-venv`), the wheel was
installed into it, and the package was imported with `cwd=/tmp` — not the repository:

```text
cwd: /tmp
proposal module: /tmp/auto015-venv/lib/python3.11/site-packages/
                 ai_workflow_engine/successor_planning/proposal.py
propose_successor: propose_successor
ProposalRun: ProposalRun
cli app groups ok: True successor_planning_propose
OUT_OF_TREE_IMPORT: PASS
```

`pyproject.toml` was not changed: its existing wheel packaging, `mypy` file list and `testpaths`
already cover whole-tree paths that include a new subpackage, and no new pytest marker was required
— exactly as §23.4 predicted.

## Live acceptance evidence (§27)

Every acceptance case runs against a **disposable** local Git repository under `tmp_path` — real
`git init`, real commits, real Markdown governance documents, a real YAML catalog whose digests are
really computed, and a real artifact root under a `HOME` pinned into `tmp_path`. Nothing about the
behaviour under test is mocked. This repository's own governance state is never the subject under
test; it appears only as the thing proven untouched.

| §27 controlled evidence case | Observed outcome |
|---|---|
| Missing predecessor | `MISSING_PREDECESSOR` |
| Malformed predecessor ID | `INVALID_PREDECESSOR_ID` |
| Unknown predecessor | `PREDECESSOR_NOT_REGISTERED` |
| Incomplete predecessor | `PREDECESSOR_NOT_COMPLETE` |
| Contradictory Task Queue/Registry status | `PREDECESSOR_STATUS_CONTRADICTION` |
| Missing completion report | `PREDECESSOR_COMPLETION_EVIDENCE_MISSING` |
| Invalid completion evidence | `PREDECESSOR_EVIDENCE_INVALID` |
| Repository mismatch / baseline mismatch | `PREDECESSOR_REPOSITORY_MISMATCH` / `PREDECESSOR_BASELINE_MISMATCH` (M03 suite) |
| Successful AUTO-014-shaped predecessor | proceeds to candidate evaluation |
| One eligible candidate | `PROPOSAL_READY` / `RECOMMENDATION_READY`, advisory recommendation issued |
| Competing eligible candidates | `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION`, all listed, `recommendation` structurally absent |
| No eligible candidate | `NO_ELIGIBLE_CANDIDATE`, blocking OD-# named in the verdict's reasons |
| All candidates insufficient evidence | `INSUFFICIENT_EVIDENCE` (distinct from `NO_ELIGIBLE_CANDIDATE`) |
| Duplicate/conflicting candidate definitions | `DUPLICATE_CANDIDATE_CONFLICT`, that identifier excluded entirely |
| Dependency cycle | every participant `blocked` with `DEPENDENCY_CYCLE` naming the full cycle |
| Malicious / prompt-injection-like content | neutralized, reported as warnings, `authorization_status` and both banners unaffected |
| Repository-identity mismatch | `REPOSITORY_IDENTITY_MISMATCH` (M02 suite) |
| Mid-run drift | `INPUT_DRIFT`, refusal record published, proposal withheld |
| Mirror contradiction | `MIRROR_CONTRADICTION` refusal record, no candidate list at all |
| Conflicting `Current` task | `CONFLICTING_CURRENT_TASK` |
| Configuration failure | `INVALID_INVOCATION` |
| Publication failure | `PUBLICATION_FAILURE`, artifact assembled and validated, nothing written |
| `--dry-run` | full inspection, reconciliation, evaluation, rendering and validation; zero publication |
| Repeated identical invocation | converges on one content-addressed artifact; second run reports `created: false` |

**Git before/after comparison.** `git status --porcelain` empty, HEAD SHA unchanged, and every
working-tree file byte- and mtime-identical after both a publishing run and a dry run
(`test_successor_planning_never_touches_the_repository_it_reads`).

**Governance/task/Registry before/after comparison on this repository.** All fourteen authoritative
documents (`TASK_QUEUE.md`, `current_task.md`, `remaining_tasks.md`, `PROJECT_STATE.md`,
`DECISION_LOG.md`, `CONTEXT.md`, both `STAGE_REGISTRY.md` files, `OPEN_QUESTIONS.md`, the
authoritative catalog, both handover files, `self-governance.yaml` and `pyproject.toml`) were hashed
with their `st_mtime_ns` before and after the acceptance run: **zero differences**.

**Process/environment evidence proving no provider call.** `subprocess.run` was wrapped for a full
invocation and every spawned executable recorded; the only executable spawned is `git`, and no
`claude` or `codex` process was spawned at any point
(`test_successor_planning_spawns_no_provider_subprocess`).

**AST-level structural evidence.** A package-wide sweep over all ten modules asserts: no
`agentos_workflow` or `agentos_dashboard` import; no provider-, `claude`-, `codex`- or
`cli_auto`-named import; no `subprocess` import; no `os.system`/`popen`/`exec*`/`spawn*` attribute;
no `shell=` keyword anywhere; and no mutating Git subcommand string (§22 invariant 12's exact list:
`push`, `commit`, `checkout`, `reset`, `clean`, `fetch`, `pull`, `clone`, `merge`, `rebase`). The ban
list is deliberately not one name wider — `branch` and `remote` are read forms Git also offers, and
`RepositoryIdentity` legitimately carries a `branch` field.

### Live invocation against this repository

```text
$ workflowctl successor-planning propose --config self-governance.yaml \
      --predecessor AUTO-014 --dry-run
Outcome: FAILURE
Failure code: CONFLICTING_CURRENT_TASK
Predecessor: AUTO-014
Proposal ID: 92730cb352426d46bc3bf821e2ac90af455e0d74be3be630512c12aafcec1dca
Authorization status: NOT_AUTHORIZED
Candidates evaluated: 0
Warnings: 0
Recommendation: (none)
Dry run: yes
Artifact: (not published)
Error [CONFLICTING_CURRENT_TASK] docs/TASK_QUEUE.md: AUTO-015 is Current at invocation time;
this tool never runs during another stage's active work
```

This is the correct result, not a defect: §4 item 3 forbids running while any task is `Current`, and
AUTO-015's own implementation task is `Current` on this branch. The tool refused, published nothing,
and left every governance document byte-identical.

The `Proposal ID` above is the digest observed at the moment that run was recorded, before this
report existed. It is content-derived by construction (§16.1, §18), and this report is itself a
completion report under §8 item 3, so writing it changes the evidence set and therefore the digest —
a re-run after this file was created produced
`bff243322e081ca4732a5e8e3793b03af6634adb255c0e554bef4b6f40c00eda` with an otherwise byte-identical
result. That is the determinism property working as specified, not drift: identical evidence always
produces an identical digest, and different evidence always produces a different one.

## Deferred Findings

Per §28, a defect not proven to directly block this contract's own authorized scope is recorded and
left unimplemented. No GOV stage is created for any of them, and none was bundled into this
implementation.

| Finding | Disposition |
|---|---|
| **D-14, D-15, D-16** (AUTO-013) | `RemoteRefEvidence`/`PullRequestEvidence` reconciliation and report sequencing in `agentos_workflow`'s runtime evidence model. Not applicable to AUTO-015's read-only, non-runtime scope. Left unimplemented. |
| **OD-6** (cancellation semantics) | Concerns `agentos_workflow`'s `CANCELLED`/`FAILED` transition rule. AUTO-015 performs no implementation and owns no runtime transition. Not a blocker. |
| **OD-7** (re-authorization after baseline drift) | Concerns re-binding an `AUTHORIZED` runtime workflow. AUTO-015 authorizes nothing. Any baseline-drift-shaped signal AUTO-015 observes is treated as an unresolved hard stop by §7's own protocol, never given a more lenient local reading. Not a blocker. |
| **OD-10** (`allowed_environment_variables` not forwarded at five Git/GitHub Skill call sites) | Concerns live `gh` CLI authentication in `GitAgent`/`MergeAgent`. AUTO-015 invokes no Git/GitHub Skill and no `gh` CLI. Not a blocker. |
| **OD-11** (`stage_contract_hash` prefix disagreement) | A distinct hashing function for runtime authorization binding. AUTO-015's hash binding uses `prompt.renderer.canonical_json`/SHA-256 directly with `proposal_id` defined as the *full* 64-character digest, so the prefix-disagreement bug class is structurally avoided here rather than merely unaffected. Not a blocker. |
| **OD-12** (QA round-numbering collision in `run_repair_loop`) | AUTO-015 runs no repair loop. Not a blocker. |

### Newly observed, not fixed

| Observation | Disposition |
|---|---|
| The AST structural assertions written in M02 (`tests/test_successor_planning_snapshot.py`) scan `snapshot.py` alone, while §26's `TestStructuralSecurityProperties` asks for them "anywhere in the new package". | Not a defect in shipped behaviour, and the frozen M02 test file was out of this milestone's allowlist. The package-wide sweep was added to `tests/test_cli.py` instead, where it passes over all ten modules. No frozen file was modified. |
| A whole-proposal failure reached *before* the predecessor resolves cannot be expressed as a §11.3 refusal record, because §16.1 makes the predecessor fields mandatory and there is nothing to bind an artifact to. | Reported as a typed bare failure (`ProposalRun` with `proposal: null`) carrying the same §13 code. This is the narrower reading of §11.3 and is recorded here rather than resolved by inventing an artifact shape the contract does not define. |

## Stop condition (§30)

This stage stops here. Proposal generation, structural validation, artifact publication and Human
Owner notification are complete. No candidate was selected authoritatively, no stage was registered
in `STAGE_REGISTRY.md`, nothing was authorized or implemented, no workflow was started, no `Current`
task-queue entry was created for any invocation, and **no commit, push, pull request, merge or
successor closeout occurred**. The branch remains `feature/auto-015-successor-planning` at baseline
`54530019bd809d2e1bcfc2f8456723ffc0a0814d` with the implementation uncommitted, awaiting the Human
Owner's review.
