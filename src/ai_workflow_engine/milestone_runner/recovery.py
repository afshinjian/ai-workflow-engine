"""The four recovery commands and their append-only ledgers (AUTO-016 section 13).

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 13 (the four
commands, what each clears, its budget effect and its guard, plus the closing constraint), section
11 (the four append-only recovery ledgers), section 10 (`HUMAN_INTERVENTION_REQUIRED` exits only
through an explicit recovery command), section 19 and section 22 invariant 11 (budget integrity
under recovery), and section 6 (the recorded real-run evidence for each of the four commands, and
defect P-10).

What a recovery command is, and what it is not
----------------------------------------------
Each command clears exactly one recorded stop and returns the run to the ordinary flow, where every
gate it already faced applies again. Section 13's closing constraint is the boundary:

    no recovery command may widen an allowlist beyond the authorized contract surface, raise a
    budget above its configured ceiling, mark a blocker closed, or move the run directly to
    `READY_FOR_COMMIT_APPROVAL`.

Three of those four are unrepresentable here rather than checked somewhere downstream. No function
in this module takes a finding, a status or a target state, so there is no argument that closes a
blocker or names an approval state; :data:`RECOVERY_POST_STATES` is a closed mapping in which no
approval state appears; and a corrected plan is accepted only when its `allowed_files` union still
equals the configured `required_coverage` **exactly** (section 4 item 6), so a widened allowlist is
a refusal rather than an accepted correction. The fourth -- a raised budget -- is checked, because a
counter is a number and arithmetic cannot be made unrepresentable: every derivation passes through
:func:`reject_forbidden_recovery_effect`, which refuses any counter that came out higher than it
went in.

Nothing here transitions a run
------------------------------
Section 10 makes `MilestoneRunnerApplication` the sole transition authority, and this coordinator is
not it. Every entry point returns a :class:`RecoveryOutcome` carrying a *derived* record and the
ledger entry that record now holds; the application decides whether to publish it, under the run
lock (section 12), through `state.py`'s single write boundary (section 17a). This module opens no
file for writing, publishes nothing, acquires no lock and invokes no provider -- it reads exactly
two things, and only for `reconcile-milestone`: the operator's result file and the transcript the
run already persisted.

The prototype's own state (`~/.local/share/auto015-runner/`) is never read as input by any path
here (DEC-016-006, section 28). Recovery reads this run's record and this run's transcripts, both
addressed through the run directory `state.py` pinned.

Defect P-10, structurally
-------------------------
`recover-failed-review` consults `ProviderRunRecord.failure_class` -- the class section 17 fixes at
invocation time and persists with the run -- and refuses when the recorded class is not the one the
operator's ruling names. It never re-reads stderr and never matches a substring such as `"401"`,
`"websocket"` or `"connection"` against text a model may itself have authored. There is no code
path here that opens a `stderr` transcript at all.

Append-only, and what that means for a rewrite
----------------------------------------------
Section 11 keeps the four ledgers append-only: "no record is ever rewritten or deleted".
:func:`append_recovery_ledger_entry` is the only way an entry is added, it has no index parameter,
and it refuses an entry already present rather than recording it twice.
:func:`reject_ledger_rewrite` checks the other direction -- that a derived record's ledgers still
begin with the previous record's entries verbatim -- so an altered or dropped entry is a refusal
even when it arrives on a record this module did not build.
"""

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from pydantic import ValidationError

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.git_inspect import RepositoryEvidence
from ai_workflow_engine.milestone_runner.models import (
    RUN_COUNTER_FIELDS,
    FindingStatus,
    ProviderFailureClass,
    ProviderRole,
    ProviderRunRecord,
    RecoveryCommand,
    RecoveryLedgerEntry,
    RunRecord,
    RunStatus,
)
from ai_workflow_engine.milestone_runner.plan import MilestonePlan
from ai_workflow_engine.milestone_runner.state import RunStateStore

#: Section 11's four append-only ledgers, keyed by the command that writes to each. The mapping is
#: closed and read-only: a command writes to its own ledger and to no other, and `RunRecord`'s own
#: validator rejects an entry filed under the wrong one.
RECOVERY_LEDGER_FIELDS: Final[Mapping[RecoveryCommand, str]] = MappingProxyType(
    {
        RecoveryCommand.RECONCILE_MILESTONE: "reconciliations",
        RecoveryCommand.REOPEN_MILESTONE: "reopenings",
        RecoveryCommand.RECOVER_FAILED_REVIEW: "review_recoveries",
        RecoveryCommand.REVALIDATE_CORRECTION: "revalidations",
    }
)

#: Where each command returns the run to. Every value is an ordinary working state: a recovered run
#: re-enters the flow and faces every gate again. No approval state appears here, which is section
#: 13's "no recovery command may ... move the run directly to `READY_FOR_COMMIT_APPROVAL`" stated as
#: the absence of a value rather than as a check on one.
RECOVERY_POST_STATES: Final[Mapping[RecoveryCommand, RunStatus]] = MappingProxyType(
    {
        RecoveryCommand.RECONCILE_MILESTONE: RunStatus.FOCUSED_VERIFYING,
        RecoveryCommand.REOPEN_MILESTONE: RunStatus.IMPLEMENTING,
        RecoveryCommand.RECOVER_FAILED_REVIEW: RunStatus.REVIEWING,
        RecoveryCommand.REVALIDATE_CORRECTION: RunStatus.CLOSURE_VERIFYING,
    }
)

#: The states each command may be invoked from. Section 10 fixes the shape: a run leaves
#: `HUMAN_INTERVENTION_REQUIRED` only through an explicit recovery command, and `MILESTONE_FAILED`
#: -- the state section 10 added to separate a failed focused verification from a safety stop -- is
#: additionally reopenable.
RECOVERY_ENTRY_STATES: Final[Mapping[RecoveryCommand, frozenset[RunStatus]]] = MappingProxyType(
    {
        RecoveryCommand.RECONCILE_MILESTONE: frozenset({RunStatus.HUMAN_INTERVENTION_REQUIRED}),
        RecoveryCommand.REOPEN_MILESTONE: frozenset(
            {RunStatus.HUMAN_INTERVENTION_REQUIRED, RunStatus.MILESTONE_FAILED}
        ),
        RecoveryCommand.RECOVER_FAILED_REVIEW: frozenset({RunStatus.HUMAN_INTERVENTION_REQUIRED}),
        RecoveryCommand.REVALIDATE_CORRECTION: frozenset({RunStatus.HUMAN_INTERVENTION_REQUIRED}),
    }
)

#: The states no recovery may produce. `DONE` joins the two approval states because reaching it
#: would skip both gates rather than only the first, and section 13's prohibition is about reaching
#: an approval directly, not about which of them is named in the sentence.
FORBIDDEN_RECOVERY_POST_STATES: Final[frozenset[RunStatus]] = frozenset(
    {
        RunStatus.READY_FOR_COMMIT_APPROVAL,
        RunStatus.READY_FOR_PUSH_APPROVAL,
        RunStatus.DONE,
    }
)

#: The key section 13 requires `reconcile-milestone` to record "honestly rather than as an
#: unqualified success". It is written into the ledger entry's reason, next to the digest that was
#: actually matched, so the record says what was reconstructed and from what -- never that the
#: milestone passed.
RECONSTRUCTED_FROM_VERIFIED_EVIDENCE: Final = "reconstructed_from_verified_evidence"

#: The record fields no recovery may move. Every one is either a section 4 pin, evidence of work
#: already done, or a ledger of findings and approvals that only the ordinary flow may touch.
_IMMOVABLE_RECORD_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "run_id",
    "repository_root",
    "repository_identity",
    "expected_branch",
    "baseline_sha",
    "contract_sha256",
    "created_at",
    "completed_milestones",
    "changed_paths",
    "provider_runs",
    "blocking_findings",
    "deferred_findings",
    "approvals",
)

#: A ceiling on the operator's result file, applied before a byte is pulled into memory. A provider
#: transcript is the thing being matched, so this is `state.py`'s artifact ceiling, not its much
#: smaller state ceiling.
MAX_RECONCILED_RESULT_BYTES: Final = 64 << 20

_DIGEST_CHUNK_BYTES: Final = 1 << 20

_UTC_TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"


class RecoveryRefused(WorkflowEngineError):
    """A recovery command was refused, and nothing was derived (section 13).

    One error class for every refusal, because the operator's response to all of them is the same:
    the run stays exactly where it stopped, no ledger entry exists, and a human decides what to do
    next. The message names the guard that refused and what it observed; a refusal never carries a
    partially-derived record, so there is nothing a caller could publish by mistake.
    """


# --------------------------------------------------------------------------------------
# Section 13 -- what a recovery observes, and what it produces
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    """The branch and `HEAD` observed at recovery time, and the moment it happened (section 13).

    Observed, never assumed: :meth:`observed` takes the evidence some caller obtained
    independently, which is `MACHINE_GATES.md` section 2a's rule that "caller-copied authorization
    strings are never live evidence". Re-verifying section 4's pins against this observation is the
    application's gate and is deliberately not restated here -- this module records what it was
    handed and refuses to invent it.
    """

    branch: str
    head_sha: str
    recorded_at: str

    @classmethod
    def observed(cls, evidence: RepositoryEvidence, moment: datetime) -> "RecoveryContext":
        """Build a context from an independent repository observation and a UTC moment."""
        if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
            raise RecoveryRefused(
                "A recovery moment must be timezone-aware UTC; a naive or offset stamp would order "
                "two recoveries differently in one ledger"
            )
        return cls(
            branch=evidence.branch,
            head_sha=evidence.head_sha,
            recorded_at=moment.strftime(_UTC_TIMESTAMP_FORMAT),
        )


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    """One recovery's derived record, its ledger entry, and what it honestly claims.

    A proposal, not a transition. `record` is a fully validated :class:`RunRecord` the application
    may publish under the run lock; until it does, the durable record is untouched and the run is
    still stopped exactly where it was.

    `reconstructed_from_verified_evidence` and `evidence_digest` are set only by
    `reconcile-milestone`, and they say precisely what happened: a result was accepted because it is
    byte-identical to the transcript the run itself persisted. Neither field claims the milestone
    passed -- the post-state is `FOCUSED_VERIFYING`, so the deterministic commands still decide
    that.
    """

    command: RecoveryCommand
    record: RunRecord
    entry: RecoveryLedgerEntry
    summary: str
    reconstructed_from_verified_evidence: bool = False
    evidence_digest: str | None = None
    corrected_plan: MilestonePlan | None = None

    @property
    def budgets_touched(self) -> Mapping[str, int]:
        """The counters this recovery moved, and by how much. Empty for three of the four."""
        return MappingProxyType(dict(self.entry.budgets_touched))

    @property
    def ledger_field(self) -> str:
        """Which of section 11's four append-only ledgers now carries :attr:`entry`."""
        return RECOVERY_LEDGER_FIELDS[self.command]


# --------------------------------------------------------------------------------------
# Section 11 -- the append-only ledgers
# --------------------------------------------------------------------------------------


def _ledger_entries(record: RunRecord, field: str) -> list[RecoveryLedgerEntry]:
    entries: list[RecoveryLedgerEntry] = list(getattr(record, field))
    return entries


def reject_ledger_rewrite(previous: RunRecord, updated: RunRecord) -> None:
    """Refuse `updated` unless every recovery ledger still begins with `previous`'s entries.

    Section 11 keeps the ledgers append-only: "no record is ever rewritten or deleted". Appending
    is therefore the only admissible difference, and it is admissible at most once -- one recovery
    command writes one entry. A shortened ledger, an altered entry at any position, an entry
    inserted ahead of an existing one, or two new entries at once are each a refusal.
    """
    appended = 0
    for field in RECOVERY_LEDGER_FIELDS.values():
        before = _ledger_entries(previous, field)
        after = _ledger_entries(updated, field)
        if len(after) < len(before):
            raise RecoveryRefused(
                f"The {field} ledger lost {len(before) - len(after)} entry(ies); a recovery ledger "
                "is append-only and no entry is ever deleted (section 11)"
            )
        if after[: len(before)] != before:
            raise RecoveryRefused(
                f"The {field} ledger no longer begins with the entries it already carried; a "
                "recovery ledger is append-only and no entry is ever rewritten (section 11)"
            )
        appended += len(after) - len(before)
    if appended > 1:
        raise RecoveryRefused(
            f"{appended} ledger entries were appended at once; one recovery command writes exactly "
            "one entry"
        )


def append_recovery_ledger_entry(record: RunRecord, entry: RecoveryLedgerEntry) -> RunRecord:
    """Return `record` with `entry` appended to the ledger its command owns (section 11).

    The only way an entry reaches a ledger, and it takes no position: there is no signature here
    that expresses replacing entry *n*, so a rewrite is not something a caller can ask for. An entry
    identical to one already present is refused rather than appended -- a replayed recovery would
    otherwise record a second act that never happened.

    The record is rebuilt through full validation rather than mutated, so the appended entry has to
    satisfy `RunRecord`'s closed schema like any other: its transition must be one
    `ALLOWED_RUN_TRANSITIONS` admits, its `budgets_touched` may only name one of the five counters,
    and it must be filed under the ledger its command owns.
    """
    field = RECOVERY_LEDGER_FIELDS[entry.command]
    for index, present in enumerate(_ledger_entries(record, field)):
        if present == entry:
            raise RecoveryRefused(
                f"The {field} ledger already carries this exact entry at position {index}; a "
                "ledger entry is never rewritten or replayed (section 11)"
            )
    payload = json.loads(record.model_dump_json())
    payload[field] = [*payload[field], json.loads(entry.model_dump_json())]
    updated = _validated(payload, f"appending a {entry.command.value} entry")
    reject_ledger_rewrite(record, updated)
    return updated


# --------------------------------------------------------------------------------------
# Section 13's closing constraint
# --------------------------------------------------------------------------------------


def reject_forbidden_recovery_effect(previous: RunRecord, updated: RunRecord) -> None:
    """Refuse any derived record that does something section 13 forbids a recovery to do.

    The closing constraint, checked in one place so all four commands are bound by one rule:

    * **no approval state** -- `READY_FOR_COMMIT_APPROVAL`, `READY_FOR_PUSH_APPROVAL` and `DONE`
      are refused as post-states, so a recovered run re-enters the ordinary flow and passes every
      gate again;
    * **no raised budget** -- not one of section 19's five counters may come out higher than it went
      in, so a recovery can restore a budget and can never grant one;
    * **no closed blocker and no new finding** -- both finding lists must be byte-identical, which
      also means a recovery cannot promote, demote, delete or introduce one;
    * **nothing else moved** -- section 4's pins, `completed_milestones`, the observed
      `changed_paths`, every provider transcript reference and every approval are all carried
      through unchanged, so recovery preserves the evidence base rather than editing it;
    * **append-only ledgers** -- :func:`reject_ledger_rewrite`, applied to the same pair.
    """
    if updated.workflow_state in FORBIDDEN_RECOVERY_POST_STATES:
        raise RecoveryRefused(
            f"A recovery may not move the run to {updated.workflow_state.value}: a recovered run "
            "re-enters the ordinary flow and must pass every gate again (section 13)"
        )

    for counter in sorted(RUN_COUNTER_FIELDS):
        before = int(getattr(previous, counter))
        after = int(getattr(updated, counter))
        if after > before:
            raise RecoveryRefused(
                f"A recovery raised {counter} from {before} to {after}; no recovery may raise a "
                "budget, and a ceiling is never raised at runtime (sections 13, 19, 21)"
            )

    before_payload = json.loads(previous.model_dump_json())
    after_payload = json.loads(updated.model_dump_json())
    for field in _IMMOVABLE_RECORD_FIELDS:
        if before_payload[field] != after_payload[field]:
            raise RecoveryRefused(
                f"A recovery changed {field}, which no recovery command may touch: a blocker is "
                "never closed, a finding is never introduced, and no prior evidence is ever "
                "rewritten or deleted (section 13)"
            )

    reject_ledger_rewrite(previous, updated)


def _validated(payload: dict[str, Any], what: str) -> RunRecord:
    """Rebuild a `RunRecord` from a JSON payload, refusing anything the closed schema rejects."""
    try:
        return RunRecord.model_validate_json(json.dumps(payload))
    except ValidationError as exc:
        raise RecoveryRefused(
            f"The record produced by {what} is not a valid run record: {exc}"
        ) from exc


def _require_entry_state(record: RunRecord, command: RecoveryCommand) -> None:
    """Refuse a command invoked from a state it does not clear (sections 10, 13)."""
    permitted = RECOVERY_ENTRY_STATES[command]
    if record.workflow_state not in permitted:
        raise RecoveryRefused(
            f"{command.value} clears a run stopped at "
            f"{sorted(state.value for state in permitted)}, not one at "
            f"{record.workflow_state.value}"
        )


def _require_reason(reason: str, field: str) -> str:
    """Refuse an empty reason. Section 13 requires an explicit one from every command."""
    if not reason.strip():
        raise RecoveryRefused(
            f"{field} must be explicit; a recovery without a stated reason is refused"
        )
    return reason


def _derive(
    record: RunRecord,
    command: RecoveryCommand,
    *,
    context: RecoveryContext,
    current_milestone: str | None,
    counters: Mapping[str, int] = MappingProxyType({}),
) -> RunRecord:
    """Return the post-recovery record: the new state, the cleared stop, and nothing else.

    `stop_reason` is cleared because clearing the recorded stop is what a recovery command *is*
    (section 13's "Clears" column). `updated_at` moves to the recovery moment, as it does on every
    other publication, and matches the ledger entry's own `recorded_at`. Every other field is
    carried through untouched, and :func:`reject_forbidden_recovery_effect` proves it afterwards.
    """
    payload = json.loads(record.model_dump_json())
    payload["workflow_state"] = RECOVERY_POST_STATES[command].value
    payload["stop_reason"] = None
    payload["current_milestone"] = current_milestone
    payload["updated_at"] = context.recorded_at
    for counter, value in counters.items():
        payload[counter] = value
    return _validated(payload, f"the {command.value} recovery")


def _entry(
    record: RunRecord,
    command: RecoveryCommand,
    *,
    reason: str,
    context: RecoveryContext,
    milestone_id: str | None = None,
    budgets_touched: Mapping[str, int] = MappingProxyType({}),
    classification: ProviderFailureClass | None = None,
    human_owner_ruling: str | None = None,
) -> RecoveryLedgerEntry:
    """Build the append-only ledger entry section 13 requires of every recovery command.

    Pre-state, post-state, the budgets touched and the branch and `HEAD` observed at recovery time,
    all on one record. The entry is validated on construction: its transition must be one the state
    machine admits and its `budgets_touched` may only name a counter that exists.
    """
    try:
        return RecoveryLedgerEntry(
            command=command,
            reason=reason,
            recorded_at=context.recorded_at,
            pre_state=record.workflow_state,
            post_state=RECOVERY_POST_STATES[command],
            branch=context.branch,
            head_sha=context.head_sha,
            milestone_id=milestone_id,
            budgets_touched=dict(budgets_touched),
            classification=classification,
            human_owner_ruling=human_owner_ruling,
        )
    except ValidationError as exc:
        raise RecoveryRefused(
            f"The {command.value} ledger entry is not one section 11 admits: {exc}"
        ) from exc


def _finish(
    previous: RunRecord,
    derived: RunRecord,
    entry: RecoveryLedgerEntry,
) -> RunRecord:
    """Append the ledger entry and prove the whole derivation against section 13's constraint."""
    updated = append_recovery_ledger_entry(derived, entry)
    reject_forbidden_recovery_effect(previous, updated)
    return updated


def _require_untouched_budgets(previous: RunRecord, updated: RunRecord) -> None:
    """Refuse unless all five counters came out exactly as they went in (sections 13, 19).

    Three of the four commands have "None" in section 13's budget-effect column, and "none" means
    equality rather than "no increase": a recovery that quietly *spent* a budget would be as wrong
    as one that granted itself another.
    """
    for counter in sorted(RUN_COUNTER_FIELDS):
        before = int(getattr(previous, counter))
        after = int(getattr(updated, counter))
        if before != after:
            raise RecoveryRefused(
                f"This recovery touches no budget, but {counter} moved from {before} to {after}"
            )


# --------------------------------------------------------------------------------------
# Section 13 -- reconcile-milestone
# --------------------------------------------------------------------------------------


def digest_of_file(path: Path) -> str:
    """Return the SHA-256 of `path`, read no-follow, bounded, and never held whole in memory.

    Used for exactly one purpose: proving that the result an operator hands to
    `reconcile-milestone` is byte-for-byte the transcript this run already persisted. A symlinked
    path, a non-regular file and an over-sized one are each a refusal rather than something to read
    around.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise RecoveryRefused(f"{path} could not be read for reconciliation: {exc}") from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise RecoveryRefused(f"{path} is not a regular file, so it carries no result to match")
        if status.st_size > MAX_RECONCILED_RESULT_BYTES:
            raise RecoveryRefused(
                f"{path} is {status.st_size} bytes, above the "
                f"{MAX_RECONCILED_RESULT_BYTES}-byte reconciliation ceiling"
            )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, _DIGEST_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def reconcile_milestone(
    record: RunRecord,
    *,
    milestone_id: str,
    reason: str,
    result_digest: str,
    transcript_digest: str,
    context: RecoveryContext,
) -> RecoveryOutcome:
    """Clear a milestone whose provider result was semantically valid but non-conforming.

    Section 13's guard, verbatim: "requires the result file to hash-match its recorded transcript;
    records `reconstructed_from_verified_evidence` honestly". The hash match is the whole
    authorization -- a result that is byte-identical to the transcript the run itself persisted is
    the provider's own output, and one that is not is text somebody wrote afterwards. The recorded
    real run needed this for a result "semantically valid but wrapped in a Markdown code fence"
    (section 6); the reconciliation act is what accepts such a result without inventing a tolerance.

    It touches no budget, and it does not claim the milestone passed. The post-state is
    `FOCUSED_VERIFYING`, so the deterministic commands still decide that, and the ledger entry
    records `reconstructed_from_verified_evidence` next to the digest that was actually matched
    rather than an unqualified success.
    """
    _require_entry_state(record, RecoveryCommand.RECONCILE_MILESTONE)
    _require_reason(reason, "reason")
    if record.current_milestone != milestone_id:
        raise RecoveryRefused(
            f"{milestone_id} is not the milestone this run stopped on "
            f"({record.current_milestone}); reconciliation clears the recorded stop, not another "
            "milestone"
        )
    if milestone_id in record.completed_milestones:
        raise RecoveryRefused(
            f"{milestone_id} is already recorded complete; there is no non-conforming result to "
            "reconcile"
        )
    if result_digest != transcript_digest:
        raise RecoveryRefused(
            f"The result offered for {milestone_id} digests to {result_digest}, but the transcript "
            f"this run persisted digests to {transcript_digest}. Reconciliation accepts only the "
            "provider's own recorded output, never a result reconstructed from anything else "
            "(section 13)"
        )

    entry_reason = (
        f"{reason.strip()}\n\n"
        f"{RECONSTRUCTED_FROM_VERIFIED_EVIDENCE}: the {milestone_id} result was reconstructed from "
        f"the transcript this run persisted, whose SHA-256 is {transcript_digest}. No verification "
        "was re-run and no milestone is claimed to have passed; the run returns to "
        f"{RECOVERY_POST_STATES[RecoveryCommand.RECONCILE_MILESTONE].value}, where the "
        "deterministic commands decide that."
    )
    entry = _entry(
        record,
        RecoveryCommand.RECONCILE_MILESTONE,
        reason=entry_reason,
        context=context,
        milestone_id=milestone_id,
    )
    derived = _derive(
        record,
        RecoveryCommand.RECONCILE_MILESTONE,
        context=context,
        current_milestone=milestone_id,
    )
    updated = _finish(record, derived, entry)
    _require_untouched_budgets(record, updated)
    return RecoveryOutcome(
        command=RecoveryCommand.RECONCILE_MILESTONE,
        record=updated,
        entry=entry,
        summary=(
            f"{milestone_id} was reconciled against its own recorded transcript "
            f"({transcript_digest}); no budget was touched and the run returns to "
            f"{updated.workflow_state.value}."
        ),
        reconstructed_from_verified_evidence=True,
        evidence_digest=transcript_digest,
    )


# --------------------------------------------------------------------------------------
# Section 13 -- reopen-milestone
# --------------------------------------------------------------------------------------


def _corrected_plan(
    plan: MilestonePlan,
    milestone_id: str,
    ruling: str,
    required_coverage: Sequence[str],
) -> MilestonePlan:
    """Write the scope ruling onto the reopened milestone and re-prove exact coverage.

    Section 14 makes `human_owner_scope_ruling` the one field only `reopen-milestone` writes, and
    section 13 requires a corrected `allowed_files` set to still satisfy section 4 item 6: the union
    of every milestone's `allowed_files` equals the configured `required_coverage` **exactly**. A
    gap and an extra are both refusals, and the extra is precisely the widening section 13's closing
    constraint forbids -- a corrected plan may move surface between milestones, never add any.
    """
    if milestone_id not in plan.milestone_ids:
        raise RecoveryRefused(
            f"The corrected plan does not define {milestone_id}, so it cannot be the plan that "
            "reopens it"
        )
    try:
        milestones = tuple(
            (
                milestone.model_copy(update={"human_owner_scope_ruling": ruling})
                if milestone.milestone_id == milestone_id
                else milestone
            )
            for milestone in plan.milestones
        )
    except ValidationError as exc:  # pragma: no cover - `model_copy` validates nothing today
        raise RecoveryRefused(
            f"The scope ruling could not be recorded on {milestone_id}: {exc}"
        ) from exc
    corrected = replace(plan, milestones=milestones)

    covered = set(corrected.covered_paths())
    required = set(required_coverage)
    missing = sorted(required - covered)
    unexpected = sorted(covered - required)
    if missing or unexpected:
        raise RecoveryRefused(
            "The corrected plan no longer covers the authorized surface exactly: "
            f"{len(missing)} required path(s) no milestone claims ({missing}), and "
            f"{len(unexpected)} milestone path(s) the coverage does not authorize ({unexpected}). "
            "No recovery may widen an allowlist beyond the authorized contract surface "
            "(sections 4 item 6, 13)"
        )
    return corrected


def reopen_milestone(
    record: RunRecord,
    *,
    milestone_id: str,
    reason: str,
    human_owner_scope_ruling: str,
    context: RecoveryContext,
    corrected_plan: MilestonePlan | None = None,
    required_coverage: Sequence[str] | None = None,
) -> RecoveryOutcome:
    """Reopen an unparseable or scope-corrected milestone under an explicit Human Owner ruling.

    Section 13's budget effect is "None; `completed_milestones` and all budgets preserved", and its
    guard is "prior attempt transcripts preserved, never deleted; a corrected `allowed_files` set
    must still satisfy section 4 item 6 coverage". Both hold structurally: the derivation moves the
    state, the cleared stop and the current milestone and nothing else, and
    :func:`reject_forbidden_recovery_effect` refuses any record whose `provider_runs`,
    `completed_milestones` or counters moved -- so no attempt transcript can be dropped from the
    record, and the files themselves are never opened here at all.

    The scope ruling is required and is recorded twice: on the ledger entry, and -- when a corrected
    plan is supplied -- on the reopened milestone's `human_owner_scope_ruling`, which section 14
    reserves for exactly this command. The recorded real run needed this for a milestone result that
    was "not parseable YAML" under `reason: milestone_plan_correction` (section 6).
    """
    _require_entry_state(record, RecoveryCommand.REOPEN_MILESTONE)
    _require_reason(reason, "reason")
    _require_reason(human_owner_scope_ruling, "human_owner_scope_ruling")
    if milestone_id in record.completed_milestones:
        raise RecoveryRefused(
            f"{milestone_id} is recorded complete; reopening it would reopen work the run already "
            "accepted, and `completed_milestones` is preserved by every recovery (section 13)"
        )

    corrected: MilestonePlan | None = None
    if corrected_plan is not None:
        if required_coverage is None:
            raise RecoveryRefused(
                "A corrected plan must be checked against the configured required_coverage; "
                "without it, exact coverage (section 4 item 6) cannot be re-proved"
            )
        corrected = _corrected_plan(
            corrected_plan, milestone_id, human_owner_scope_ruling, required_coverage
        )
    elif required_coverage is not None:
        raise RecoveryRefused(
            "required_coverage was supplied with no corrected plan to check against it"
        )

    entry = _entry(
        record,
        RecoveryCommand.REOPEN_MILESTONE,
        reason=reason.strip(),
        context=context,
        milestone_id=milestone_id,
        human_owner_ruling=human_owner_scope_ruling.strip(),
    )
    derived = _derive(
        record,
        RecoveryCommand.REOPEN_MILESTONE,
        context=context,
        current_milestone=milestone_id,
    )
    updated = _finish(record, derived, entry)
    _require_untouched_budgets(record, updated)
    return RecoveryOutcome(
        command=RecoveryCommand.REOPEN_MILESTONE,
        record=updated,
        entry=entry,
        summary=(
            f"{milestone_id} was reopened under an explicit Human Owner scope ruling; "
            f"{len(record.completed_milestones)} completed milestone(s), "
            f"{len(record.provider_runs)} prior attempt transcript(s) and every budget are "
            "preserved."
        ),
        corrected_plan=corrected,
    )


# --------------------------------------------------------------------------------------
# Section 13 -- recover-failed-review
# --------------------------------------------------------------------------------------


def _latest_review_invocation(record: RunRecord) -> ProviderRunRecord:
    """The most recent review invocation, which is the one a recovery is about."""
    reviews = [run for run in record.provider_runs if run.role is ProviderRole.REVIEW]
    if not reviews:
        raise RecoveryRefused(
            "This run records no review invocation, so no review budget can have been consumed by "
            "a provider failure"
        )
    return reviews[-1]


def recover_failed_review(
    record: RunRecord,
    *,
    classification: ProviderFailureClass,
    human_owner_ruling: str,
    reason: str,
    context: RecoveryContext,
) -> RecoveryOutcome:
    """Restore exactly one review budget consumed by a **provider** failure (sections 13, 19).

    Three guards, in order. The run must actually show a consumed review budget, because a budget
    that was never spent is not one this command can restore. The most recent review invocation must
    carry a **persisted** failure class -- section 17 fixes that class at invocation time, and this
    command reads it rather than re-deriving one, which is defect P-10's correction: no path here
    re-greps stderr for `"401"`, `"websocket"` or `"connection"`, substrings a model may itself have
    authored. And the recorded class must be the one the operator's typed `classification` names; a
    mismatch is a refusal, so the ruling is about the failure that actually happened.

    A review that completed and returned a verdict has no recorded failure class, which is exactly
    how the first two guards make section 13's "never usable on a review that actually completed"
    hold: the command cannot reach such a review at all.

    Exactly one budget is restored -- `successful_review_rounds` goes down by one and no other
    counter moves -- and the ledger entry records the delta, the typed class and the ruling.
    """
    _require_entry_state(record, RecoveryCommand.RECOVER_FAILED_REVIEW)
    _require_reason(reason, "reason")
    _require_reason(human_owner_ruling, "human_owner_ruling")

    if record.successful_review_rounds < 1:
        raise RecoveryRefused(
            "No review budget is consumed on this run "
            f"(successful_review_rounds={record.successful_review_rounds}), so there is none to "
            "restore. A provider failure never consumes a review budget in the first place "
            "(section 19)"
        )

    invocation = _latest_review_invocation(record)
    if invocation.failure_class is None:
        raise RecoveryRefused(
            f"Review invocation {invocation.sequence} records no failure class, so it "
            "completed and returned a verdict. A completed review's budget is spent, not "
            "recoverable (section 13)"
        )
    if invocation.failure_class is not classification:
        raise RecoveryRefused(
            f"The ruling names {classification.value}, but review invocation "
            f"{invocation.sequence} recorded {invocation.failure_class.value}. Recovery consults "
            "the class persisted at invocation time and never re-interprets provider output "
            "(section 17, defect P-10)"
        )

    restored = record.successful_review_rounds - 1
    entry = _entry(
        record,
        RecoveryCommand.RECOVER_FAILED_REVIEW,
        reason=reason.strip(),
        context=context,
        milestone_id=invocation.milestone_id,
        budgets_touched={"successful_review_rounds": -1},
        classification=classification,
        human_owner_ruling=human_owner_ruling.strip(),
    )
    derived = _derive(
        record,
        RecoveryCommand.RECOVER_FAILED_REVIEW,
        context=context,
        current_milestone=record.current_milestone,
        counters={"successful_review_rounds": restored},
    )
    updated = _finish(record, derived, entry)
    if updated.successful_review_rounds != restored:
        raise RecoveryRefused(
            "Exactly one review budget must be restored; the derived record carries "
            f"{updated.successful_review_rounds} rather than {restored}"
        )
    for counter in sorted(RUN_COUNTER_FIELDS - {"successful_review_rounds"}):
        if getattr(updated, counter) != getattr(record, counter):
            raise RecoveryRefused(
                f"Recovering a failed review moved {counter}; exactly one counter -- the review "
                "budget -- may move (section 19)"
            )
    return RecoveryOutcome(
        command=RecoveryCommand.RECOVER_FAILED_REVIEW,
        record=updated,
        entry=entry,
        summary=(
            f"One review budget was restored after the recorded {classification.value} failure of "
            f"invocation {invocation.sequence}: successful_review_rounds "
            f"{record.successful_review_rounds} -> {restored}."
        ),
    )


# --------------------------------------------------------------------------------------
# Section 13 -- revalidate-correction
# --------------------------------------------------------------------------------------


def revalidate_correction(
    record: RunRecord,
    *,
    reason: str,
    context: RecoveryContext,
    blocker_ids: Sequence[str] = (),
) -> RecoveryOutcome:
    """Clear a post-correction verification failure, with every budget explicitly untouched.

    Section 13's guard is "limited to the already-open blocker IDs; cannot introduce new findings".
    Both hold by construction: there is no parameter here that carries a finding, a severity or a
    status, so a new finding is not something this command can express, and `blocker_ids` -- when an
    operator names the blockers being revalidated -- must be a subset of the ids the run already has
    open. Naming anything else is a refusal, never an addition.

    The findings themselves come out exactly as they went in, which is also how "no recovery may
    mark a blocker closed" holds: :func:`reject_forbidden_recovery_effect` compares both finding
    lists byte-for-byte. Only a closure verification on an already-open blocker id closes one, and
    that is `review.py`'s job under the ordinary flow the run is being returned to.

    The recorded real run needed this once, to clear the stop reason "tests failed after the
    correction round" (section 6).
    """
    _require_entry_state(record, RecoveryCommand.REVALIDATE_CORRECTION)
    _require_reason(reason, "reason")
    if record.correction_round < 1:
        raise RecoveryRefused(
            "No correction round is recorded on this run, so there is no post-correction "
            "verification failure to revalidate"
        )

    open_ids = {
        finding.finding_id
        for finding in record.blocking_findings
        if finding.status is not FindingStatus.CLOSED
    }
    unknown = sorted(set(blocker_ids) - open_ids)
    if unknown:
        raise RecoveryRefused(
            f"{unknown} are not among this run's open blockers {sorted(open_ids)}; revalidation is "
            "limited to the already-open blocker ids and cannot introduce a finding (section 13)"
        )

    entry = _entry(
        record,
        RecoveryCommand.REVALIDATE_CORRECTION,
        reason=reason.strip(),
        context=context,
        milestone_id=record.current_milestone,
    )
    derived = _derive(
        record,
        RecoveryCommand.REVALIDATE_CORRECTION,
        context=context,
        current_milestone=record.current_milestone,
    )
    updated = _finish(record, derived, entry)
    _require_untouched_budgets(record, updated)
    return RecoveryOutcome(
        command=RecoveryCommand.REVALIDATE_CORRECTION,
        record=updated,
        entry=entry,
        summary=(
            "The post-correction verification failure was cleared with every budget untouched; "
            f"{len(sorted(open_ids))} blocker(s) stay exactly as open as they were."
        ),
    )


# --------------------------------------------------------------------------------------
# Section 13 -- the coordinator
# --------------------------------------------------------------------------------------


class RecoveryCoordinator:
    """Section 13's four recovery commands, bound to one run's durable directory.

    The coordinator adds exactly one thing to the four functions above: it resolves the transcript
    `reconcile-milestone` has to hash against, from the run directory `state.py` pinned. Everything
    else it forwards unchanged.

    What it does not do is as much of its definition as what it does. It publishes nothing --
    section 10 makes `MilestoneRunnerApplication` the sole transition authority, so every method
    returns a :class:`RecoveryOutcome` and the application decides whether to publish it under the
    run lock. It invokes no provider, runs no command, acquires no lock and writes no byte. It reads
    exactly one file, only for reconciliation, and only from inside this run's own transcript
    directory: the prototype's state at `~/.local/share/auto015-runner/` is never opened by any path
    here (DEC-016-006).
    """

    def __init__(self, store: RunStateStore) -> None:
        self._store = store

    @property
    def store(self) -> RunStateStore:
        """The run directory this coordinator resolves transcripts against. Read-only here."""
        return self._store

    def recorded_result_transcript(self, record: RunRecord, milestone_id: str) -> Path:
        """The stdout transcript of `milestone_id`'s most recent implementation invocation.

        The transcript is addressed by the run-relative path the record already carries, joined
        onto this run's directory -- so what is hashed is the file the run itself wrote, not a path
        an operator chose. `ProviderRunRecord` normalizes that path at the model boundary and
        refuses an absolute or traversal-shaped one, so the join cannot leave the run directory.
        """
        attempts = [
            run
            for run in record.provider_runs
            if run.milestone_id == milestone_id and run.role is ProviderRole.IMPLEMENTATION
        ]
        if not attempts:
            raise RecoveryRefused(
                f"This run records no implementation invocation for {milestone_id}, so there is no "
                "persisted transcript to reconcile a result against"
            )
        return self._store.run_directory / attempts[-1].stdout_path

    def reconcile_milestone(
        self,
        record: RunRecord,
        *,
        milestone_id: str,
        reason: str,
        result_path: Path,
        context: RecoveryContext,
    ) -> RecoveryOutcome:
        """Reconcile `milestone_id` against the transcript this run persisted (section 13)."""
        transcript = self.recorded_result_transcript(record, milestone_id)
        return reconcile_milestone(
            record,
            milestone_id=milestone_id,
            reason=reason,
            result_digest=digest_of_file(result_path),
            transcript_digest=digest_of_file(transcript),
            context=context,
        )

    def reopen_milestone(
        self,
        record: RunRecord,
        *,
        milestone_id: str,
        reason: str,
        human_owner_scope_ruling: str,
        context: RecoveryContext,
        corrected_plan: MilestonePlan | None = None,
        required_coverage: Sequence[str] | None = None,
    ) -> RecoveryOutcome:
        """Reopen `milestone_id` under an explicit Human Owner scope ruling (section 13)."""
        return reopen_milestone(
            record,
            milestone_id=milestone_id,
            reason=reason,
            human_owner_scope_ruling=human_owner_scope_ruling,
            context=context,
            corrected_plan=corrected_plan,
            required_coverage=required_coverage,
        )

    def recover_failed_review(
        self,
        record: RunRecord,
        *,
        classification: ProviderFailureClass,
        human_owner_ruling: str,
        reason: str,
        context: RecoveryContext,
    ) -> RecoveryOutcome:
        """Restore one review budget consumed by a recorded provider failure (section 13)."""
        return recover_failed_review(
            record,
            classification=classification,
            human_owner_ruling=human_owner_ruling,
            reason=reason,
            context=context,
        )

    def revalidate_correction(
        self,
        record: RunRecord,
        *,
        reason: str,
        context: RecoveryContext,
        blocker_ids: Sequence[str] = (),
    ) -> RecoveryOutcome:
        """Clear a post-correction verification failure, budgets untouched (section 13)."""
        return revalidate_correction(
            record,
            reason=reason,
            context=context,
            blocker_ids=blocker_ids,
        )


#: Named so a reader can see the whole recovery surface in one place, and so a test can assert that
#: the four commands section 13 defines are the four this module exposes -- no more.
RECOVERY_COMMANDS: Final[Mapping[RecoveryCommand, str]] = MappingProxyType(
    {
        RecoveryCommand.RECONCILE_MILESTONE: "reconcile_milestone",
        RecoveryCommand.REOPEN_MILESTONE: "reopen_milestone",
        RecoveryCommand.RECOVER_FAILED_REVIEW: "recover_failed_review",
        RecoveryCommand.REVALIDATE_CORRECTION: "revalidate_correction",
    }
)
