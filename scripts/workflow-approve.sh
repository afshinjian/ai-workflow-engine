#!/usr/bin/env bash
#
# workflow-approve.sh — the Human approval and local commit gate (GOV-AUTO-01), extended with
# automatic task closeout (GOV-AUTO-03).
#
# Shows the Human Owner exactly what changed, requires two explicit confirmations, then creates
# exactly one local commit. In this repository (identified by the `id: ai-workflow-engine`
# marker in self-governance.yaml, with the full governance file set present) that one commit
# also performs the deterministic governance closeout of the single Current task — task queue,
# mirrors, project state, decision log, changelog, stage registry, program changelog, completion
# report, handover, and checksum — so the implementation and its closure land together. In any
# other repository (no marker, or the marker present but the governance files absent) the script
# behaves exactly as the original GOV-AUTO-01 gate: it commits the approved diff and nothing else.
#
# This script NEVER pushes, merges, changes branches, alters upstream, rebases, resets, restores,
# amends, cherry-picks, or touches stashes. Publishing is always a separate, deliberate act.
#
# Usage:
#   scripts/workflow-approve.sh
#   scripts/workflow-approve.sh -m "feat(scope): subject (TASK-ID)"

set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_NOT_A_REPO=3
readonly EXIT_NOTHING_TO_COMMIT=4
readonly EXIT_WHITESPACE=5
readonly EXIT_CONFLICTS=6
readonly EXIT_DECLINED=7
readonly EXIT_BAD_MESSAGE=8
readonly EXIT_COMMIT_FAILED=9
readonly EXIT_NO_CURRENT_TASK=10
readonly EXIT_MULTIPLE_CURRENT=11
readonly EXIT_MIRROR_MISMATCH=12
readonly EXIT_NOT_CLOSEABLE=13
readonly EXIT_MISSING_REPORT=14
readonly EXIT_SCOPE_MISMATCH=15
readonly EXIT_CLOSEOUT_FAILED=16
readonly EXIT_GOVERNANCE_MISSING=17
readonly EXIT_REPORT_CONFLICT=18

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit "${2:-1}"
}

note() { printf '%s\n' "$1"; }
rule() { printf -- '---------------------------------------------------------------\n'; }

usage() {
    cat >&2 <<'USAGE'
Usage: workflow-approve.sh [-m <commit-message>]

  -m <msg>   Conventional Commit message. Prompted for interactively when omitted.

Displays the pending changes, requires the Human Owner to type APPROVE, confirms the exact file
list, and creates exactly one local commit. Never pushes, merges, or touches stashes.

In this repository, also performs the deterministic governance closeout of the single Current
task in that same commit. In any other repository it behaves as the plain approval/commit gate.
USAGE
}

commit_message=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -m | --message)
            [ "$#" -ge 2 ] || die "-m requires a value" "$EXIT_USAGE"
            commit_message="$2"
            shift 2
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            usage
            die "unrecognised argument: '$1'" "$EXIT_USAGE"
            ;;
    esac
done

# --- Repository root: derived from this script's own location, never the caller's cwd ----------

script_path="${BASH_SOURCE[0]}"
while [ -L "$script_path" ]; do
    link_target="$(readlink "$script_path")"
    case "$link_target" in
        /*) script_path="$link_target" ;;
        *) script_path="$(cd -P "$(dirname "$script_path")" && pwd)/$link_target" ;;
    esac
done
script_dir="$(cd -P "$(dirname "$script_path")" && pwd)"

repo_root="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null)" ||
    die "not inside a Git repository (script located at $script_dir)" "$EXIT_NOT_A_REPO"
readonly repo_root

branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
head_before="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || echo '(no commits yet)')"
readonly branch head_before
upstream_before="$(git -C "$repo_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
stash_before="$(git -C "$repo_root" stash list)"
readonly upstream_before stash_before

note "AgentOS approval and local commit gate"
rule
note "Repository : $repo_root"
note "Branch     : $branch"
note "HEAD       : $head_before"
rule

# --- Refuse when there is nothing to approve ---------------------------------------------------

if [ -z "$(git -C "$repo_root" status --porcelain)" ]; then
    die "no uncommitted changes — nothing to approve or commit" "$EXIT_NOTHING_TO_COMMIT"
fi

# --- Refuse on unresolved merge conflicts ------------------------------------------------------
#
# `U` in either status column, or any stage>0 entry in the index, means a conflict is unresolved.
# Committing that state would record conflict markers as if they were intended content.

if git -C "$repo_root" status --porcelain | grep -Eq '^(U.|.U|AA|DD)'; then
    note "Unresolved merge conflicts:"
    git -C "$repo_root" status --short | grep -E '^(U.|.U|AA|DD)' || true
    die "resolve merge conflicts before approving" "$EXIT_CONFLICTS"
fi
if [ -n "$(git -C "$repo_root" ls-files --unmerged)" ]; then
    die "the index contains unmerged entries — resolve conflicts before approving" "$EXIT_CONFLICTS"
fi

# --- Whitespace / conflict-marker check --------------------------------------------------------

if ! git -C "$repo_root" diff --check; then
    die "git diff --check reported whitespace or conflict-marker errors" "$EXIT_WHITESPACE"
fi
note "git diff --check : clean"
note ""

# --- Resolve the exact set of individually changed paths from `git status` ----------------------
#
# Read with -z --untracked-files=all so: (a) paths containing spaces, quotes, or newlines survive
# intact — the status short format is "XY <path>", NUL-terminated; (b) a newly created,
# entirely-untracked directory is expanded to every file it actually contains rather than
# collapsed into one directory-summary path. Git's *default* untracked mode ("normal") does that
# collapsing for any untracked directory — e.g. a brand-new `agentos_workflow/tests/e2e/` with
# several files inside reports as the single path "agentos_workflow/tests/e2e/", not each file —
# and `--untracked-files=all` is the only mode that recurses fully, so it must be used at every
# call site that compares against an approved-file list, or a directory marker path gets compared
# as if it were an independent implementation file (it never is one: `git add` on that same marker
# path stages the real files underneath it, but the two path strings never string-compare equal).
# A rename/copy record carries the origin path as its own NUL-terminated field immediately
# following the destination path; both halves are resolved. Writes into the array named by $1.
resolve_changed_paths() {
    local -n __resolve_changed_paths_out="$1"
    local -a status_records
    local record path x y index
    mapfile -d '' -t status_records < <(
        git -C "$repo_root" status --porcelain=v1 -z --untracked-files=all
    )
    __resolve_changed_paths_out=()
    index=0
    while [ "$index" -lt "${#status_records[@]}" ]; do
        record="${status_records[$index]}"
        index=$((index + 1))
        [ -n "$record" ] || continue
        x="${record:0:1}"
        y="${record:1:1}"
        path="${record:3}"
        __resolve_changed_paths_out+=("$path")
        if [ "$x" = "R" ] || [ "$y" = "R" ] || [ "$x" = "C" ] || [ "$y" = "C" ]; then
            if [ "$index" -lt "${#status_records[@]}" ]; then
                __resolve_changed_paths_out+=("${status_records[$index]}")
                index=$((index + 1))
            fi
        fi
    done
}

# --- Build the exact implementation file list, and display it in full --------------------------

impl_files=()
resolve_changed_paths impl_files

[ "${#impl_files[@]}" -gt 0 ] || die "no changed files resolved from git status" "$EXIT_NOTHING_TO_COMMIT"

note "Changed files (${#impl_files[@]}):"
git -C "$repo_root" status --short --untracked-files=all
note ""
note "Diff stat (tracked changes):"
git -C "$repo_root" diff --stat
note ""
rule

# =================================================================================================
# Decide whether the automatic task-closeout transaction applies to this repository.
#
# Gated on the same stable repository marker `workflow-authorize.sh` already uses. Any other
# repository (no self-governance.yaml, or a different `project.id`) gets the plain GOV-AUTO-01
# approval/commit gate unchanged, so existing callers and existing tests are unaffected.
# =================================================================================================

config="$repo_root/self-governance.yaml"
closeout_enabled=0
if [ -f "$config" ] &&
    grep -Eq '^[[:space:]]*id:[[:space:]]*ai-workflow-engine[[:space:]]*$' "$config"; then
    closeout_enabled=1
fi
readonly config closeout_enabled

if [ "$closeout_enabled" -eq 0 ]; then
    # =============================================================================================
    # Legacy path — identical to the original GOV-AUTO-01 gate.
    # =============================================================================================

    note "Review the changes above."
    note "Type exactly APPROVE to continue, or anything else to abort."
    printf 'Approval: '
    approval=""
    IFS= read -r approval || true
    if [ "$approval" != "APPROVE" ]; then
        note ""
        note "Approval not granted. Nothing was staged and nothing was committed."
        exit "$EXIT_DECLINED"
    fi

    if [ -z "$commit_message" ]; then
        note ""
        note "Enter the Conventional Commit message (single line):"
        printf 'Message: '
        IFS= read -r commit_message || true
    fi

    trimmed="${commit_message#"${commit_message%%[![:space:]]*}"}"
    trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
    commit_message="$trimmed"

    [ -n "$commit_message" ] || die "commit message is empty" "$EXIT_BAD_MESSAGE"

    if ! printf '%s' "$commit_message" |
        grep -Eq '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9._/-]+\))?!?: .+'; then
        die "not a valid Conventional Commit message: '$commit_message'" "$EXIT_BAD_MESSAGE"
    fi
    if [ "${#commit_message}" -lt 12 ]; then
        die "commit message subject is implausibly short: '$commit_message'" "$EXIT_BAD_MESSAGE"
    fi

    note ""
    rule
    note "The following ${#impl_files[@]} file(s) will be staged and committed:"
    for file in "${impl_files[@]}"; do
        printf '  %s\n' "$file"
    done
    note ""
    note "Commit message:"
    printf '  %s\n' "$commit_message"
    rule
    note "Type exactly APPROVE to create this commit, or anything else to abort."
    printf 'Confirm commit: '
    confirm=""
    IFS= read -r confirm || true
    if [ "$confirm" != "APPROVE" ]; then
        note ""
        note "Commit declined. Nothing was staged and nothing was committed."
        exit "$EXIT_DECLINED"
    fi

    # shellcheck disable=SC2317  # Invoked indirectly by the EXIT trap below.
    unstage_on_failure() {
        local status=$?
        if [ "$status" -ne 0 ]; then
            printf '\nERROR: failed after staging. Unstaging the files this script staged.\n' >&2
            printf 'Working-tree content is NOT modified; your changes are intact.\n' >&2
            if [ "$head_before" = "(no commits yet)" ]; then
                git -C "$repo_root" rm --cached -r --quiet -- "${impl_files[@]}" 2>/dev/null || true
            else
                git -C "$repo_root" restore --staged -- "${impl_files[@]}" 2>/dev/null || true
            fi
            printf 'Index restored. Re-run scripts/workflow-approve.sh when resolved.\n' >&2
        fi
    }
    trap unstage_on_failure EXIT

    git -C "$repo_root" add -- "${impl_files[@]}"

    note ""
    note "Staged changes (git diff --cached --name-status):"
    git -C "$repo_root" diff --cached --name-status
    note ""
    git -C "$repo_root" diff --cached --check
    note "git diff --cached --check : clean"

    if ! git -C "$repo_root" commit --quiet -m "$commit_message"; then
        die "git commit failed" "$EXIT_COMMIT_FAILED"
    fi

    trap - EXIT

    commit_hash="$(git -C "$repo_root" rev-parse HEAD)"

    note ""
    rule
    note "Commit hash    : $commit_hash"
    note "Commit message : $commit_message"
    note ""
    note "Committed files:"
    git -C "$repo_root" show --stat --format='' "$commit_hash"
    note ""
    note "Final Git status:"
    git -C "$repo_root" status --short --branch
    note ""
    note "Not pushed. Not merged. Branch unchanged. Stashes untouched."
    rule
    note "COMMIT_COMPLETE_READY_FOR_NEXT_TASK"
    exit 0
fi

# =================================================================================================
# GOV-AUTO-03 path — approval with automatic task closeout, one commit.
# =================================================================================================

queue="$repo_root/docs/TASK_QUEUE.md"
current_mirror="$repo_root/docs/current_task.md"
remaining_mirror="$repo_root/docs/remaining_tasks.md"
project_state="$repo_root/docs/PROJECT_STATE.md"
decision_log="$repo_root/docs/DECISION_LOG.md"
changelog="$repo_root/docs/CHANGELOG.md"
handover="$repo_root/handover/PROJECT_HANDOVER.md"
checksum="$repo_root/handover/PROJECT_CHECKSUM.md"
readonly queue current_mirror remaining_mirror project_state decision_log changelog
readonly handover checksum

for required in "$queue" "$current_mirror" "$remaining_mirror" "$project_state" \
    "$decision_log" "$changelog" "$handover" "$checksum"; do
    [ -f "$required" ] || die "required governance file is missing: $required" "$EXIT_GOVERNANCE_MISSING"
done

# --- Task discovery: exactly one Current task, from the authoritative task queue ----------------

current_ids="$(
    awk '
        /^#{2,6}[[:space:]]/ {
            heading=$0
            gsub(/[`*_~]/, "", heading)
            id=""
            if (match(heading, /[A-Z][A-Z0-9-]*-[0-9]+/)) id=substr(heading,RSTART,RLENGTH)
            next
        }
        id != "" && /^[[:space:]]*(Status:|- \*\*Status:\*\*)/ {
            line=$0
            gsub(/[`*_~-]/, "", line)
            if (line ~ /Status:[[:space:]]*Current([[:space:]]|$)/) print id
            id=""
        }
    ' "$queue"
)"

current_count=0
if [ -n "$current_ids" ]; then
    current_count="$(printf '%s\n' "$current_ids" | wc -l | tr -d ' ')"
fi

case "$current_count" in
    0)
        printf 'NO_CURRENT_TASK\n' >&2
        die "no Current task in $queue — nothing for this gate to close out" "$EXIT_NO_CURRENT_TASK"
        ;;
    1) task_id="$current_ids" ;;
    *)
        printf 'MULTIPLE_CURRENT_TASKS\n' >&2
        die "more than one Current task: $(printf '%s' "$current_ids" | tr '\n' ' ')" \
            "$EXIT_MULTIPLE_CURRENT"
        ;;
esac
readonly task_id

heading_count="$(
    awk -v wanted="$task_id" '
        /^#{2,6}[[:space:]]/ {
            line=$0
            gsub(/[`*_~]/, "", line)
            if (line ~ "(^|[^A-Z0-9-])" wanted "([^A-Z0-9-]|$)") count++
        }
        END { print count+0 }
    ' "$queue"
)"
[ "$heading_count" -eq 1 ] ||
    die "task queue contains $heading_count headings for $task_id (expected exactly 1)" \
        "$EXIT_MIRROR_MISMATCH"

task_title="$(
    awk -v wanted="$task_id" '
        /^#{2,6}[[:space:]]/ {
            line=$0
            gsub(/[`*_~]/, "", line)
            if (line ~ "(^|[^A-Z0-9-])" wanted "([^A-Z0-9-]|$)") {
                sub(/^#{2,6}[[:space:]]+/, "", line)
                sub(wanted, "", line)
                gsub(/^[[:space:]]*[—:-]+[[:space:]]*/, "", line)
                print line
                exit
            }
        }
    ' "$queue"
)"

task_section="$(
    awk -v wanted="$task_id" '
        /^#{2,6}[[:space:]]/ {
            if (inside) exit
            line=$0
            gsub(/[`*_~]/, "", line)
            if (line ~ "(^|[^A-Z0-9-])" wanted "([^A-Z0-9-]|$)") inside=1
        }
        inside { print }
    ' "$queue"
)"
if printf '%s\n' "$task_section" |
    grep -Eiq 'Status:[[:space:]]*Blocked|blocked[[:space:]]+on|authorization[[:space:]]+blocked'; then
    die "task $task_id is blocked — not closeable" "$EXIT_NOT_CLOSEABLE"
fi

# --- Mirror agreement: docs/current_task.md must name exactly this task as Current --------------

mirror_current_ids="$(
    awk '
        /^#{2,6}[[:space:]]/ {
            heading=$0
            gsub(/[`*_~]/, "", heading)
            id=""
            if (match(heading, /[A-Z][A-Z0-9-]*-[0-9]+/)) id=substr(heading,RSTART,RLENGTH)
            next
        }
        id != "" && /^[[:space:]]*(Status:|- \*\*Status:\*\*)/ {
            line=$0
            gsub(/[`*_~-]/, "", line)
            if (line ~ /Status:[[:space:]]*Current([[:space:]]|$)/) print id
            id=""
        }
    ' "$current_mirror"
)"
[ "$mirror_current_ids" = "$task_id" ] ||
    die "docs/current_task.md Current set ('$mirror_current_ids') disagrees with the task queue ('$task_id')" \
        "$EXIT_MIRROR_MISMATCH"

remaining_row_count="$(
    awk -F '|' -v wanted="$task_id" '
        {
            cell=$2
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
            if (cell == wanted) count++
        }
        END { print count+0 }
    ' "$remaining_mirror"
)"
[ "$remaining_row_count" -eq 1 ] ||
    die "docs/remaining_tasks.md has $remaining_row_count row(s) for $task_id (expected exactly 1)" \
        "$EXIT_MIRROR_MISMATCH"
remaining_row_status="$(
    awk -F '|' -v wanted="$task_id" '
        {
            cell=$2
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
            if (cell == wanted) {
                status=$4
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", status)
                print status
                exit
            }
        }
    ' "$remaining_mirror"
)"
case "$remaining_row_status" in
    Current) ;;
    *)
        die "docs/remaining_tasks.md shows $task_id as '$remaining_row_status', expected 'Current'" \
            "$EXIT_MIRROR_MISMATCH"
        ;;
esac

# --- Stage registry agreement (AUTO/DASH-family tasks only) -------------------------------------

registry=""
registry_relative=""
registry_state=""
required_branch=""
program_changelog=""
for candidate in \
    "docs/workflow-automation/STAGE_REGISTRY.md" \
    "docs/agentos-dashboard/STAGE_REGISTRY.md"; do
    candidate_path="$repo_root/$candidate"
    [ -f "$candidate_path" ] || continue
    row="$(awk -F '|' -v wanted="$task_id" '
        {
            cell=$2
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
            if (cell == wanted) { print; exit }
        }
    ' "$candidate_path")"
    [ -n "$row" ] || continue
    registry="$candidate_path"
    registry_relative="$candidate"
    registry_state="$(printf '%s\n' "$row" | awk -F '|' '{gsub(/ /,"",$5); print $5}')"
    required_branch="$(printf '%s\n' "$row" | awk -F '|' '{gsub(/[` ]/,"",$6); print $6}')"
    case "$candidate" in
        docs/workflow-automation/*)
            program_changelog="$repo_root/docs/workflow-automation/CHANGELOG.md"
            ;;
        docs/agentos-dashboard/*)
            program_changelog="$repo_root/docs/agentos-dashboard/CHANGELOG.md"
            ;;
    esac
    break
done

if [[ "$task_id" =~ ^(AUTO|DASH)-[0-9]+$ ]] && [ -z "$registry" ]; then
    die "task $task_id looks like a registry-governed stage but has no registry row" \
        "$EXIT_MIRROR_MISMATCH"
fi

if [ -n "$registry" ]; then
    case "$registry_state" in
        AUTHORIZED | IN_PROGRESS | SELF_REVIEW | REVIEW | APPROVAL) ;;
        BLOCKED) die "stage $task_id is BLOCKED in its registry — not closeable" "$EXIT_NOT_CLOSEABLE" ;;
        COMPLETE | SUPERSEDED)
            die "stage $task_id already has completed registry state $registry_state" \
                "$EXIT_MIRROR_MISMATCH"
            ;;
        NOT_STARTED | PROPOSED)
            die "stage $task_id has registry state $registry_state, but the task queue shows it Current" \
                "$EXIT_MIRROR_MISMATCH"
            ;;
        *) die "stage $task_id has unrecognised registry state '$registry_state'" "$EXIT_MIRROR_MISMATCH" ;;
    esac
    if [ -n "$required_branch" ] && [ "$branch" != "$required_branch" ]; then
        die "current branch '$branch' does not match the stage's registered branch '$required_branch'" \
            "$EXIT_SCOPE_MISMATCH"
    fi
fi

# --- Locate the task's completion report (must already exist; closeout only appends) ------------
#
# AUTO/GOV tasks use the fixed <TASK_ID>-completion-report.md naming, checked first, unchanged
# from before this task.

report=""
report_relative=""
for candidate in \
    "docs/reports/workflow-automation/${task_id}-completion-report.md" \
    "docs/reports/agentos-dashboard/${task_id}-completion-report.md" \
    "docs/reports/${task_id}-completion-report.md"; do
    candidate_path="$repo_root/$candidate"
    if [ -f "$candidate_path" ]; then
        report="$candidate_path"
        report_relative="$candidate"
        break
    fi
done

# --- Dashboard-program canonical name (GOV-AUTO-04, resolves OD-D11) -----------------------------
#
# `docs/agentos-dashboard/STAGE_REGISTRY.md` documents `STAGE-XX-completion.md` as this program's
# own convention (`STAGE_REGISTRY.md` §3), but the naming above never matched it, so every DASH
# stage's report needed a manual duplicate copy to satisfy this gate. Accept the canonical name
# too, but only for a task this session has *already* confirmed, via the registry lookup above, is
# a DASH stage — and only after deriving its two-digit stage number from the registry's own
# Branch cell (`required_branch`, e.g. `feature/dash-002-repo-adapter`), not from unchecked
# filename construction on the task ID alone. If the branch cell's embedded number disagrees with
# the task ID's own numeric suffix, the registry row is treated as malformed and the canonical
# name is never attempted — this session refuses to guess. The resulting path never varies beyond
# `docs/reports/agentos-dashboard/STAGE-<2 digits>-completion.md`: two ASCII digits derived from
# already-registry-confirmed data can never encode `..` or a path separator, so no path escapes
# that directory.
if [[ "$task_id" =~ ^DASH-([0-9]{3})$ ]] &&
    [ "$registry_relative" = "docs/agentos-dashboard/STAGE_REGISTRY.md" ]; then
    task_stage_number="${BASH_REMATCH[1]}"
    if [[ "$required_branch" =~ dash-([0-9]{3})- ]] &&
        [ "${BASH_REMATCH[1]}" = "$task_stage_number" ]; then
        canonical_stage="$(printf '%02d' "$((10#$task_stage_number))")"
        if [[ "$canonical_stage" =~ ^[0-9]{2}$ ]]; then
            canonical_relative="docs/reports/agentos-dashboard/STAGE-${canonical_stage}-completion.md"
            canonical_path="$repo_root/$canonical_relative"
            if [ -f "$canonical_path" ]; then
                if [ -n "$report" ]; then
                    if ! diff -q "$report" "$canonical_path" >/dev/null 2>&1; then
                        die "conflicting completion reports for $task_id: $report_relative and $canonical_relative disagree" \
                            "$EXIT_REPORT_CONFLICT"
                    fi
                    # Identical content under both names: keep the already-found report path.
                else
                    report="$canonical_path"
                    report_relative="$canonical_relative"
                fi
            fi
        fi
    fi
fi

[ -n "$report" ] || die "no completion report found for $task_id (expected e.g. docs/reports/${task_id}-completion-report.md, or for a Dashboard stage the canonical docs/reports/agentos-dashboard/STAGE-XX-completion.md)" \
    "$EXIT_MISSING_REPORT"
readonly report report_relative

# --- Build the fixed closeout target list --------------------------------------------------------

closeout_files=(
    "docs/TASK_QUEUE.md"
    "docs/current_task.md"
    "docs/remaining_tasks.md"
    "docs/PROJECT_STATE.md"
    "docs/DECISION_LOG.md"
    "docs/CHANGELOG.md"
    "handover/PROJECT_HANDOVER.md"
    "handover/PROJECT_CHECKSUM.md"
    "$report_relative"
)
if [ -n "$registry_relative" ]; then closeout_files+=("$registry_relative"); fi
if [ -n "$program_changelog" ] && [ -f "$program_changelog" ]; then
    closeout_files+=("${program_changelog#"$repo_root/"}")
fi

# --- Commit message, determined and validated before any Human confirmation ---------------------

if [ -z "$commit_message" ]; then
    note ""
    note "Enter the Conventional Commit message for $task_id (single line):"
    printf 'Message: '
    IFS= read -r commit_message || true
fi

trimmed="${commit_message#"${commit_message%%[![:space:]]*}"}"
trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
commit_message="$trimmed"

[ -n "$commit_message" ] || die "commit message is empty" "$EXIT_BAD_MESSAGE"

if ! printf '%s' "$commit_message" |
    grep -Eq '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9._/-]+\))?!?: .+'; then
    die "not a valid Conventional Commit message: '$commit_message'" "$EXIT_BAD_MESSAGE"
fi
if [ "${#commit_message}" -lt 12 ]; then
    die "commit message subject is implausibly short: '$commit_message'" "$EXIT_BAD_MESSAGE"
fi
case "$commit_message" in
    *"$task_id"*) ;;
    *)
        die "commit message does not name $task_id — approval evidence does not correspond to the Current task" \
            "$EXIT_SCOPE_MISMATCH"
        ;;
esac
readonly commit_message

# --- Display the full transition before asking for approval -------------------------------------

rule
note "Task            : $task_id"
note "Title           : $task_title"
note "Branch          : $branch"
note "Base HEAD       : $head_before"
note ""
note "Implementation files (${#impl_files[@]}):"
for file in "${impl_files[@]}"; do printf '  %s\n' "$file"; done
note ""
note "Governance files that will be generated or updated by closeout (${#closeout_files[@]}):"
for file in "${closeout_files[@]}"; do printf '  %s\n' "$file"; done
note ""
note "Proposed commit message:"
printf '  %s\n' "$commit_message"
rule

# --- First confirmation ---------------------------------------------------------------------------

note "Review the transition above."
note "Type exactly APPROVE to continue, or anything else to abort."
printf 'Approval: '
approval=""
IFS= read -r approval || true
if [ "$approval" != "APPROVE" ]; then
    note ""
    note "Approval not granted. Nothing was staged, nothing was closed out, nothing was committed."
    exit "$EXIT_DECLINED"
fi

# --- Second confirmation ---------------------------------------------------------------------------

note ""
note "Second confirmation: this will close $task_id (Current -> Done), regenerate handover/checksum,"
note "and create exactly one local commit containing the implementation and the closeout records."
note "Type exactly APPROVE to proceed, or anything else to abort."
printf 'Confirm commit: '
confirm=""
IFS= read -r confirm || true
if [ "$confirm" != "APPROVE" ]; then
    note ""
    note "Commit declined. Nothing was staged, nothing was closed out, nothing was committed."
    exit "$EXIT_DECLINED"
fi

# =================================================================================================
# Deterministic closeout generation — fail-closed, atomically reversible.
# =================================================================================================

date_value="${WORKFLOW_APPROVE_DATE:-$(date +%F)}"
[[ "$date_value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "invalid closeout date" "$EXIT_CLOSEOUT_FAILED"
readonly date_value

closeout_backup_dir="$(mktemp -d)"
readonly closeout_backup_dir
for relative in "${closeout_files[@]}"; do
    src="$repo_root/$relative"
    dest="$closeout_backup_dir/$relative"
    mkdir -p "$(dirname "$dest")"
    cp -p -- "$src" "$dest"
done

closeout_started=1
staged=0
# shellcheck disable=SC2317  # Invoked indirectly by the EXIT trap below.
restore_on_failure() {
    local status=$?
    if [ "$status" -eq 0 ]; then
        return
    fi
    if [ "$staged" -eq 1 ]; then
        git -C "$repo_root" restore --staged -- "${impl_files[@]}" "${closeout_files[@]}" \
            2>/dev/null || true
        printf 'Index restored.\n' >&2
    fi
    if [ "${closeout_started:-0}" -eq 1 ]; then
        for relative in "${closeout_files[@]}"; do
            cp -p -- "$closeout_backup_dir/$relative" "$repo_root/$relative"
        done
        printf 'Closeout-generated governance files restored to their pre-closeout content.\n' >&2
    fi
    printf 'Implementation working-tree content was not touched by closeout and is intact.\n' >&2
    rm -rf -- "$closeout_backup_dir"
    printf 'ERROR: closeout failed; nothing was committed. See diagnostics above.\n' >&2
}
trap restore_on_failure EXIT

extract_task_status() {
    local file="$1" wanted="$2"
    awk -v wanted="$wanted" '
        /^#{2,6}[[:space:]]/ {
            if (inside) exit
            line = $0
            gsub(/[`*_~]/, "", line)
            if (line ~ "(^|[^A-Z0-9-])" wanted "([^A-Z0-9-]|$)") inside = 1
            next
        }
        inside && /^[[:space:]]*(Status:|- \*\*Status:\*\*)/ {
            line = $0
            gsub(/[`*_~-]/, "", line)
            sub(/^[[:space:]]*Status:[[:space:]]*/, "", line)
            split(line, words, /[[:space:]]+/)
            print words[1]
            exit
        }
    ' "$file"
}

replace_task_status() {
    local file="$1" wanted="$2" old="$3" new="$4" tmp
    tmp="$(mktemp "${file}.tmp.XXXXXX")"
    if ! awk -v wanted="$wanted" -v old="$old" -v new="$new" '
        /^#{2,6}[[:space:]]/ {
            if (inside) inside=0
            line=$0
            gsub(/[`*_~]/, "", line)
            if (line ~ "(^|[^A-Z0-9-])" wanted "([^A-Z0-9-]|$)") inside=1
        }
        inside && !changed && $0 ~ "Status:[[:space:]]*" old "([[:space:]]|$)" {
            sub("Status:[[:space:]]*" old, "Status: " new)
            changed=1
        }
        { print }
        END { if (!changed) exit 42 }
    ' "$file" >"$tmp"; then
        rm -f -- "$tmp"
        die "could not update $wanted in ${file#"$repo_root/"}" "$EXIT_CLOSEOUT_FAILED"
    fi
    mv -- "$tmp" "$file"
}

remove_table_row() {
    local file="$1" wanted="$2" tmp
    tmp="$(mktemp "${file}.tmp.XXXXXX")"
    if ! awk -F '|' -v wanted="$wanted" '
        {
            cell=$2
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
            if (cell == wanted) { removed++; next }
        }
        { print }
        END { if (removed != 1) exit 42 }
    ' "$file" >"$tmp"; then
        rm -f -- "$tmp"
        die "could not remove exactly one row for $wanted in ${file#"$repo_root/"}" \
            "$EXIT_CLOSEOUT_FAILED"
    fi
    mv -- "$tmp" "$file"
}

replace_table_status() {
    local file="$1" wanted="$2" old="$3" new="$4" tmp
    tmp="$(mktemp "${file}.tmp.XXXXXX")"
    if ! awk -F '|' -v wanted="$wanted" -v old="$old" -v new="$new" '
        BEGIN { OFS="|" }
        {
            cell=$2
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
            if (cell == wanted) {
                for (i=1; i<=NF; i++) {
                    plain=$i
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", plain)
                    if (plain == old) {
                        sub(old, new, $i)
                        changed=1
                        break
                    }
                }
            }
            print
        }
        END { if (!changed) exit 42 }
    ' "$file" >"$tmp"; then
        rm -f -- "$tmp"
        die "could not update registry row for $wanted" "$EXIT_CLOSEOUT_FAILED"
    fi
    mv -- "$tmp" "$file"
}

# 1. Task queue: Current -> Done.
replace_task_status "$queue" "$task_id" "Current" "Done"

# 2. current_task.md: rewrite to the empty-Current template.
current_tmp="$(mktemp "${current_mirror}.tmp.XXXXXX")"
{
    printf '# Current Task\n\n'
    printf "Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at\n"
    printf 'the same status as the task queue — workflowctl check-task-state fails otherwise.\n\n'
    printf '## No task is currently active\n\n'
    # shellcheck disable=SC2016  # printf format string; %s are placeholders, not expansions.
    printf '%s — %s was closed `Current -> Done` on %s by explicit Human Owner approval\n' \
        "$task_id" "$task_title" "$date_value"
    printf "through scripts/workflow-approve.sh's automatic task closeout (GOV-AUTO-03). The\n"
    printf 'approved implementation was committed together with this closeout in one local commit.\n\n'
    printf "The Current set is therefore empty. Under self-governance.yaml's maximum_current_tasks: 1\n"
    printf 'this is a legal state — the maximum is a ceiling, not a quota.\n\n'
    printf 'Every remaining task (docs/remaining_tasks.md) is Planned and requires its own fresh\n'
    printf 'written Human Owner authorization naming it before it may become Current. Closing %s\n' \
        "$task_id"
    printf 'authorizes no successor.\n'
} >"$current_tmp"
mv -- "$current_tmp" "$current_mirror"

# 3. remaining_tasks.md: the task row is removed (it mirrors only not-yet-Done entries).
remove_table_row "$remaining_mirror" "$task_id"

# 4. Project state: flip an existing per-task heading if one exists (e.g. left by
#    workflow-authorize.sh), otherwise append a plain prose bullet under "## Completed". Never
#    unconditionally append a *new* "## <task-id>" heading here: parse_tasks() treats the first
#    occurrence of a heading as authoritative for that source, so a later, unrelated stale
#    heading for the same task id would silently out-rank this one and reintroduce a mismatch.
project_state_status="$(extract_task_status "$project_state" "$task_id")"
if [ -n "$project_state_status" ]; then
    replace_task_status "$project_state" "$task_id" "$project_state_status" "Done"
else
    project_state_tmp="$(mktemp "${project_state}.tmp.XXXXXX")"
    if ! awk -v task_id="$task_id" -v date_value="$date_value" '
        !inserted && /^## Completed/ {
            print
            print "- " task_id " (closed " date_value "): implemented, Human-Owner-approved, and"
            print "  closed via scripts/workflow-approve.sh'"'"'s automatic task closeout (GOV-AUTO-03)."
            inserted=1
            next
        }
        { print }
        END { if (!inserted) exit 42 }
    ' "$project_state" >"$project_state_tmp"; then
        rm -f -- "$project_state_tmp"
        die "could not update docs/PROJECT_STATE.md" "$EXIT_CLOSEOUT_FAILED"
    fi
    mv -- "$project_state_tmp" "$project_state"
fi

# 5. Decision log: one new dated, append-only entry.
decision_tmp="$(mktemp "${decision_log}.tmp.XXXXXX")"
awk -v date_value="$date_value" -v task_id="$task_id" -v msg="$commit_message" \
    -v branch="$branch" -v head="$head_before" '
    !inserted && /^## / {
        print "## " date_value " — Human Owner approved and closed " task_id
        print ""
        print "**Decision:** The Human Owner reviewed the implementation diff for `" task_id "` on"
        print "branch `" branch "` at base `" head "`, typed the two exact `APPROVE` confirmations"
        print "required by `scripts/workflow-approve.sh`, and approved the Conventional Commit"
        print "message `" msg "`. The script then performed the deterministic governance closeout"
        print "(`" task_id "` moves `Current -> Done`) and staged the approved implementation"
        print "together with the generated closeout records in one local commit."
        print ""
        print "**Boundaries:** This decision approves and closes only `" task_id "`. It does not"
        print "push, merge, authorize a successor task, change branches, alter upstream, or mutate"
        print "stashes."
        print ""
        inserted=1
    }
    { print }
    END { if (!inserted) exit 42 }
' "$decision_log" >"$decision_tmp" || die "could not update decision log" "$EXIT_CLOSEOUT_FAILED"
mv -- "$decision_tmp" "$decision_log"

# 6. Changelog: one new [Unreleased] entry.
changelog_tmp="$(mktemp "${changelog}.tmp.XXXXXX")"
awk -v date_value="$date_value" -v task_id="$task_id" '
    !inserted && /^### Added/ {
        print
        print "- " task_id " (" date_value "): implemented, Human-Owner-approved, and closed"
        print "  `Current -> Done` in one local commit via scripts/workflow-approve.sh'"'"'s automatic"
        print "  task closeout (GOV-AUTO-03)."
        inserted=1
        next
    }
    { print }
    END { if (!inserted) exit 42 }
' "$changelog" >"$changelog_tmp" || die "could not update changelog" "$EXIT_CLOSEOUT_FAILED"
mv -- "$changelog_tmp" "$changelog"

# 7. Stage registry (AUTO/DASH-family only): state -> COMPLETE, plus one new Authorization Log row.
if [ -n "$registry" ]; then
    replace_table_status "$registry" "$task_id" "$registry_state" "COMPLETE"
    registry_tmp="$(mktemp "${registry}.tmp.XXXXXX")"
    awk -v date_value="$date_value" -v task_id="$task_id" -v branch="$branch" '
        /^## [0-9]+\. Authorization Log/ { in_log=1 }
        !inserted && in_log && /^## [0-9]+\./ && $0 !~ /Authorization Log/ {
            print "| " date_value " | " task_id " (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `" branch "` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |"
            print ""
            inserted=1
        }
        { print }
        END { if (!inserted) exit 42 }
    ' "$registry" >"$registry_tmp" || die "could not append registry closure row" "$EXIT_CLOSEOUT_FAILED"
    mv -- "$registry_tmp" "$registry"
fi

# 8. Program changelog, if this program keeps one.
if [ -n "$program_changelog" ] && [ -f "$program_changelog" ]; then
    cat >>"$program_changelog" <<EOF

## $date_value — $task_id closed

The Human Owner approved and closed $task_id through the automatic task-closeout gate
(\`scripts/workflow-approve.sh\`, GOV-AUTO-03). Registry state \`COMPLETE\`; task status \`Done\`.
EOF
fi

# 9. Completion report: one new append-only addendum. Never claims a commit hash, push, or merge.
cat >>"$report" <<EOF

## Addendum — Human Owner approval and closure ($date_value)

The Human Owner reviewed this report and the implementation diff, typed the two exact \`APPROVE\`
confirmations required by \`scripts/workflow-approve.sh\`, and approved the Conventional Commit
message \`$commit_message\`. The script then performed the deterministic governance closeout
recorded in \`docs/DECISION_LOG.md\`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
EOF

# 10. Handover: append-only update, then regenerate the checksum manifest.
cat >>"$handover" <<EOF

## Closure update — $date_value

$task_id was approved and closed \`Current -> Done\` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is \`Current\` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.
EOF

handover_size="$(wc -c <"$handover" | tr -d ' ')"
handover_digest="$(sha256sum "$handover" | awk '{print $1}')"
checksum_tmp="$(mktemp "${checksum}.tmp.XXXXXX")"
awk -v size="$handover_size" -v date_value="$date_value" -v digest="$handover_digest" '
    /^\| handover\/PROJECT_HANDOVER.md \|/ {
        print "| handover/PROJECT_HANDOVER.md | " size " | " date_value " | " digest " |"
        changed=1
        next
    }
    { print }
    END { if (!changed) exit 42 }
' "$checksum" >"$checksum_tmp" || die "could not regenerate handover checksum" "$EXIT_CLOSEOUT_FAILED"
mv -- "$checksum_tmp" "$checksum"

# --- Post-closeout validation: fail before commit if anything is inconsistent -------------------

git -C "$repo_root" diff --check ||
    die "post-closeout git diff --check failed; refusing to commit" "$EXIT_CLOSEOUT_FAILED"

validation_cmd=(conda run -n ai-workflow-engine workflowctl)
if command -v workflowctl >/dev/null 2>&1; then
    validation_cmd=(workflowctl)
fi
if ! "${validation_cmd[@]}" check-task-state --config "$config" ||
    ! "${validation_cmd[@]}" check-governance --config "$config" ||
    ! "${validation_cmd[@]}" check-handover --config "$config"; then
    die "post-closeout governance validation failed; refusing to commit" "$EXIT_CLOSEOUT_FAILED"
fi

# --- Verify exactly the expected files changed: implementation set + closeout set, nothing else -
#
# Uses the same `resolve_changed_paths` helper as the implementation file list above, for the same
# reason: without `--untracked-files=all`, a newly created untracked directory collapses to one
# directory-summary path that can never string-compare equal to the individual files inside it
# that `impl_files` actually approved, so every closeout of a stage that added a new untracked
# directory would be wrongly rejected as "unexpected change outside the approved+closeout set."

all_changed=()
resolve_changed_paths all_changed
for changed in "${all_changed[@]}"; do
    allowed=0
    for expected in "${impl_files[@]}" "${closeout_files[@]}"; do
        if [ "$changed" = "$expected" ]; then allowed=1; break; fi
    done
    [ "$allowed" -eq 1 ] || die "unexpected change outside the approved+closeout set: $changed" \
        "$EXIT_CLOSEOUT_FAILED"
done

# --- Stage, verify, and commit exactly the displayed + generated files --------------------------

note ""
note "Closeout complete. Final staged file set:"
for file in "${impl_files[@]}" "${closeout_files[@]}"; do printf '  %s\n' "$file"; done
note ""

git -C "$repo_root" add -- "${impl_files[@]}" "${closeout_files[@]}"
staged=1

note "Staged changes (git diff --cached --name-status):"
git -C "$repo_root" diff --cached --name-status
note ""
git -C "$repo_root" diff --cached --check
note "git diff --cached --check : clean"

if ! git -C "$repo_root" commit --quiet -m "$commit_message"; then
    die "git commit failed" "$EXIT_COMMIT_FAILED"
fi
staged=0
closeout_started=0
trap - EXIT
rm -rf -- "$closeout_backup_dir"

commit_hash="$(git -C "$repo_root" rev-parse HEAD)"

# --- Git safety: branch, upstream, and stashes must be exactly as they were before this run -----

[ "$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)" = "$branch" ] ||
    die "branch changed unexpectedly during closeout" "$EXIT_COMMIT_FAILED"
[ "$(git -C "$repo_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)" = \
    "$upstream_before" ] || die "upstream changed unexpectedly during closeout" "$EXIT_COMMIT_FAILED"
[ "$(git -C "$repo_root" stash list)" = "$stash_before" ] ||
    die "stash list changed unexpectedly during closeout" "$EXIT_COMMIT_FAILED"

rule
note "Commit hash    : $commit_hash"
note "Commit message : $commit_message"
note "Task closed    : $task_id (Current -> Done)"
note ""
note "Committed files:"
git -C "$repo_root" show --stat --format='' "$commit_hash"
note ""
note "Final Git status:"
git -C "$repo_root" status --short --branch
note ""

next_planned="$(
    awk '
        /^#{2,6}[[:space:]]/ {
            heading=$0
            gsub(/[`*_~]/, "", heading)
            id=""
            if (match(heading, /[A-Z][A-Z0-9-]*-[0-9]+/)) id=substr(heading,RSTART,RLENGTH)
            next
        }
        id != "" && /^[[:space:]]*(Status:|- \*\*Status:\*\*)/ {
            line=$0
            gsub(/[`*_~-]/, "", line)
            if (line ~ /Status:[[:space:]]*Planned([[:space:]]|$)/ && found=="") found=id
            id=""
        }
        END { print found }
    ' "$queue"
)"
if [ -n "$next_planned" ]; then
    note "Next Planned (unauthorized) task: $next_planned"
else
    note "No Planned task remains in the queue."
fi

note ""
note "Not pushed. Not merged. Branch unchanged. Stashes untouched. No task authorized."
rule
note "COMMIT_COMPLETE_READY_FOR_NEXT_TASK"
