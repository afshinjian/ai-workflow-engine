#!/usr/bin/env bash
#
# workflow-authorize.sh — Human-controlled authorization and launch gate (GOV-AUTO-02).
#
# Authorizes exactly the task named by the Human Owner, records the governance transition in one
# local governance-only commit, and optionally invokes workflow-next.sh. It never chooses a task,
# implements one, pushes, merges, changes branches/upstream, or mutates stashes.

set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_REPOSITORY=3
readonly EXIT_DIRTY=4
readonly EXIT_TASK=5
readonly EXIT_PRECONDITION=6
readonly EXIT_DECLINED=7
readonly EXIT_VALIDATION=8
readonly EXIT_COMMIT=9
readonly EXIT_BRANCH_PREP=10

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit "${2:-1}"
}

note() { printf '%s\n' "$1"; }
rule() { printf -- '----------------------------------------------------------------\n'; }

usage() {
    cat >&2 <<'USAGE'
Usage: workflow-authorize.sh <TASK_ID> [claude|codex]

  <TASK_ID>   Exact existing task to authorize (the script never selects one)
  agent       Optional: claude | codex

Without an agent, authorization is committed and the script stops. With an agent, the verified
authorization commit is followed by scripts/workflow-next.sh <agent>.
USAGE
}

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    usage
    die "exactly one task ID and at most one agent are required" "$EXIT_USAGE"
fi

task_id="$1"
[[ "$task_id" =~ ^[A-Z][A-Z0-9-]*-[0-9]+$ ]] || {
    usage
    die "invalid task ID: '$task_id'" "$EXIT_USAGE"
}

agent="${2:-}"
case "$agent" in
    "" | claude | codex) ;;
    *)
        usage
        die "unsupported agent: '$agent' (expected 'claude' or 'codex')" "$EXIT_USAGE"
        ;;
esac
readonly task_id agent

# Resolve the real script location, so invocation cwd and symlink spelling cannot select a repo.
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
    die "script is not inside a Git repository" "$EXIT_REPOSITORY"
readonly script_dir repo_root

# shellcheck source=lib/branch_prepare.sh
source "$script_dir/lib/branch_prepare.sh" ||
    die "missing required library: $script_dir/lib/branch_prepare.sh" "$EXIT_REPOSITORY"

config="$repo_root/self-governance.yaml"
queue="$repo_root/docs/TASK_QUEUE.md"
current_mirror="$repo_root/docs/current_task.md"
remaining_mirror="$repo_root/docs/remaining_tasks.md"
project_state="$repo_root/docs/PROJECT_STATE.md"
decision_log="$repo_root/docs/DECISION_LOG.md"
changelog="$repo_root/docs/CHANGELOG.md"
handover="$repo_root/handover/PROJECT_HANDOVER.md"
checksum="$repo_root/handover/PROJECT_CHECKSUM.md"
readonly config queue current_mirror remaining_mirror project_state decision_log changelog
readonly handover checksum

if [ ! -f "$config" ] ||
    ! grep -Eq '^[[:space:]]*id:[[:space:]]*ai-workflow-engine[[:space:]]*$' "$config"; then
    die "stable repository marker does not identify ai-workflow-engine" "$EXIT_REPOSITORY"
fi
for required in "$queue" "$current_mirror" "$remaining_mirror" "$project_state" \
    "$decision_log" "$changelog" "$handover" "$checksum"; do
    [ -f "$required" ] || die "required governance file is missing: $required" "$EXIT_REPOSITORY"
done
[ -x "$repo_root/scripts/workflow-next.sh" ] ||
    die "required runner is missing or not executable" "$EXIT_REPOSITORY"

default_branch="$(
    awk '$1 == "default_branch:" { print $2; exit }' "$config"
)"
conda_environment="$(
    awk '$1 == "conda_environment:" { print $2; exit }' "$config"
)"
require_upstream="$(
    awk '$1 == "require_upstream:" { print $2; exit }' "$config"
)"
if [ -z "$default_branch" ] || [ -z "$conda_environment" ]; then
    die "self-governance.yaml lacks default_branch or conda_environment" "$EXIT_REPOSITORY"
fi
readonly default_branch conda_environment require_upstream

if [ -n "$(git -C "$repo_root" status --porcelain --untracked-files=all)" ]; then
    git -C "$repo_root" status --short >&2
    die "authorization requires a clean worktree and index" "$EXIT_DIRTY"
fi
if [ -n "$(git -C "$repo_root" ls-files --unmerged)" ]; then
    die "authorization refused: unresolved conflict entries exist" "$EXIT_DIRTY"
fi
git -C "$repo_root" diff --check ||
    die "git diff --check failed" "$EXIT_VALIDATION"

branch_before="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
head_before="$(git -C "$repo_root" rev-parse HEAD)"
upstream_before="$(git -C "$repo_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
stash_before="$(git -C "$repo_root" stash list)"
readonly branch_before head_before upstream_before stash_before

# Extract the first task heading's explicit Status field. Markdown task IDs are data, not regex.
task_status="$(
    awk -v wanted="$task_id" '
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
    ' "$queue"
)"
[ -n "$task_status" ] || die "unknown task ID: $task_id" "$EXIT_TASK"
case "$task_status" in
    Done) die "task $task_id is already Done" "$EXIT_TASK" ;;
    Current) die "task $task_id is already Current" "$EXIT_TASK" ;;
    Planned | READY | Ready) ;;
    *) die "task $task_id has unsupported status '$task_status'" "$EXIT_TASK" ;;
esac

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
if [ -n "$current_ids" ]; then
    printf '%s\n' "ACTIVE_TASK_MUST_BE_CLOSED_FIRST" >&2
    die "existing Current task(s): $(printf '%s' "$current_ids" | tr '\n' ' ')" "$EXIT_PRECONDITION"
fi

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
    die "task $task_id is blocked" "$EXIT_PRECONDITION"
fi

registry=""
registry_relative=""
registry_state=""
required_branch="$default_branch"
predecessors="none declared"
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

if [ -n "$registry" ]; then
    case "$registry_state" in
        NOT_STARTED | PROPOSED) ;;
        COMPLETE | SUPERSEDED)
            die "task $task_id has completed registry state $registry_state" "$EXIT_TASK"
            ;;
        BLOCKED) die "task $task_id is blocked in its stage registry" "$EXIT_PRECONDITION" ;;
        *) die "task $task_id is already active in registry state $registry_state" "$EXIT_TASK" ;;
    esac

    prefix="${task_id%-*}"
    number="${task_id##*-}"
    if [[ "$number" =~ ^[0-9]+$ ]] && [ "$((10#$number))" -gt 1 ]; then
        previous_number="$(printf "%0${#number}d" "$((10#$number - 1))")"
        predecessor="${prefix}-${previous_number}"
        predecessor_state="$(
            awk -F '|' -v wanted="$predecessor" '
                {
                    cell=$2
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
                    if (cell == wanted) { state=$5; gsub(/ /,"",state); print state; exit }
                }
            ' "$registry"
        )"
        predecessors="$predecessor ($predecessor_state)"
        [ "$predecessor_state" = "COMPLETE" ] ||
            die "predecessor $predecessor is not COMPLETE" "$EXIT_PRECONDITION"
    fi

    open_questions="${registry%/*}/OPEN_QUESTIONS.md"
    if [ -f "$open_questions" ] &&
        grep -Eiq "must be resolved before ${task_id//-/[- ]} authorization|${task_id}[^.]*blocked on" \
            "$open_questions"; then
        die "task $task_id has an unresolved Human Owner decision" "$EXIT_PRECONDITION"
    fi
fi

# Authorization is recorded on the clean default-branch baseline. The canonical implementation
# branch shown above is created later by the implementation session, never by this gate.
[ "$branch_before" = "$default_branch" ] ||
    die "branch baseline not met: expected $default_branch, found $branch_before" "$EXIT_PRECONDITION"
if [ -n "$upstream_before" ]; then
    upstream_head="$(git -C "$repo_root" rev-parse '@{upstream}')"
    [ "$head_before" = "$upstream_head" ] ||
        die "branch baseline not met: HEAD differs from $upstream_before" "$EXIT_PRECONDITION"
elif [ "$require_upstream" = "true" ]; then
    die "branch baseline not met: $default_branch has no upstream" "$EXIT_PRECONDITION"
fi

validation_cmd=(conda run -n "$conda_environment" workflowctl)
run_governance_validation() {
    "${validation_cmd[@]}" check-task-state --config "$config"
    "${validation_cmd[@]}" check-governance --config "$config"
    "${validation_cmd[@]}" check-handover --config "$config"
}

run_governance_validation ||
    die "pre-authorization repository validation failed" "$EXIT_VALIDATION"

governance_files=(
    "docs/TASK_QUEUE.md"
    "docs/current_task.md"
    "docs/remaining_tasks.md"
    "docs/PROJECT_STATE.md"
    "docs/DECISION_LOG.md"
    "docs/CHANGELOG.md"
    "handover/PROJECT_HANDOVER.md"
    "handover/PROJECT_CHECKSUM.md"
)
if [ -n "$registry_relative" ]; then governance_files+=("$registry_relative"); fi
if [ -n "$program_changelog" ] && [ -f "$program_changelog" ]; then
    governance_files+=("${program_changelog#"$repo_root/"}")
fi

rule
note "Local task authorization gate"
note "Requested task       : $task_id"
note "Current task status   : $task_status"
note "Required predecessors : $predecessors"
if [ -n "$registry" ]; then
    note "Required branch       : $required_branch (created during implementation)"
else
    note "Required branch       : $required_branch (authorization baseline)"
fi
note "Baseline branch       : $branch_before"
note "Current HEAD          : $head_before"
note "Selected agent        : ${agent:-none (authorization only)}"
note "Governance files that will change:"
for file in "${governance_files[@]}"; do printf '  %s\n' "$file"; done
rule
note "Type exactly AUTHORIZE to authorize $task_id, or anything else to stop."
printf 'Authorization: '
authorization=""
IFS= read -r authorization || true
if [ "$authorization" != "AUTHORIZE" ]; then
    note "Authorization declined. Repository unchanged."
    exit "$EXIT_DECLINED"
fi

note ""
note "Second confirmation: the files above will be changed and exactly one local"
note "governance-only commit will be created. Type exactly AUTHORIZE again."
printf 'Confirm authorization commit: '
confirmation=""
IFS= read -r confirmation || true
if [ "$confirmation" != "AUTHORIZE" ]; then
    note "Second confirmation declined. Repository unchanged."
    exit "$EXIT_DECLINED"
fi

date_value="${WORKFLOW_AUTHORIZE_DATE:-$(date +%F)}"
[[ "$date_value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] ||
    die "invalid authorization date" "$EXIT_REPOSITORY"
readonly date_value

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
        die "could not update $wanted in ${file#"$repo_root/"}" "$EXIT_VALIDATION"
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
        die "could not update mirror row for $wanted" "$EXIT_VALIDATION"
    fi
    mv -- "$tmp" "$file"
}

replace_task_status "$queue" "$task_id" "$task_status" "Current"
replace_table_status "$remaining_mirror" "$task_id" "$task_status" "Current"

current_tmp="$(mktemp "${current_mirror}.tmp.XXXXXX")"
{
    printf '# Current Task\n\n'
    printf "Mirror of docs/TASK_QUEUE.md's Current set. This task was selected explicitly by the\n"
    printf 'Human Owner through scripts/workflow-authorize.sh; no ordering was inferred.\n\n'
    printf '## %s\n\n' "$task_id"
    printf 'Status: Current\n\n'
    printf 'Authorized by the Human Owner on %s. Implementation remains a separate phase and must stop\n' \
        "$date_value"
    printf 'for Human Owner approval before any implementation commit.\n'
} >"$current_tmp"
mv -- "$current_tmp" "$current_mirror"

cat >>"$project_state" <<EOF

## Authorization update — $date_value

## $task_id

Status: Current

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.
EOF

decision_tmp="$(mktemp "${decision_log}.tmp.XXXXXX")"
awk -v date_value="$date_value" -v task_id="$task_id" -v branch="$branch_before" \
    -v head="$head_before" '
    !inserted && /^## / {
        print "## " date_value " — Human Owner authorized " task_id
        print ""
        print "**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for"
        print "`" task_id "`. The task moves `Planned → Current`; implementation remains separate."
        print "The authorization was recorded from branch `" branch "` at `" head "`."
        print ""
        print "**Boundaries:** This decision authorizes only the named task. It authorizes no successor,"
        print "push, merge, implementation approval, stash mutation, or automatic predecessor closure."
        print ""
        inserted=1
    }
    { print }
    END { if (!inserted) exit 42 }
' "$decision_log" >"$decision_tmp" || die "could not update decision log" "$EXIT_VALIDATION"
mv -- "$decision_tmp" "$decision_log"

changelog_tmp="$(mktemp "${changelog}.tmp.XXXXXX")"
awk -v date_value="$date_value" -v task_id="$task_id" '
    !inserted && /^### Added/ {
        print
        print "- " task_id " (" date_value "): explicitly authorized by the Human Owner through the local"
        print "  two-confirmation task gate; authorization commit and implementation remain separate."
        inserted=1
        next
    }
    { print }
    END { if (!inserted) exit 42 }
' "$changelog" >"$changelog_tmp" || die "could not update changelog" "$EXIT_VALIDATION"
mv -- "$changelog_tmp" "$changelog"

if [ -n "$registry" ]; then
    replace_table_status "$registry" "$task_id" "$registry_state" "AUTHORIZED"
    registry_tmp="$(mktemp "${registry}.tmp.XXXXXX")"
    awk -v date_value="$date_value" -v task_id="$task_id" -v head="$head_before" '
        /^## [0-9]+\. Authorization Log/ { in_log=1 }
        !inserted && in_log && /^## [0-9]+\./ && $0 !~ /Authorization Log/ {
            print "| " date_value " | " task_id " | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `" head "`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |"
            print ""
            inserted=1
        }
        { print }
        END { if (!inserted) exit 42 }
    ' "$registry" >"$registry_tmp" || die "could not append registry authorization" "$EXIT_VALIDATION"
    mv -- "$registry_tmp" "$registry"
fi

if [ -n "$program_changelog" ] && [ -f "$program_changelog" ]; then
    cat >>"$program_changelog" <<EOF

## $date_value — $task_id authorized

The Human Owner authorized $task_id through the two-confirmation local gate. The stage is
\`AUTHORIZED\`; implementation, approval, push, and merge remain separate.
EOF
fi

cat >>"$handover" <<EOF

## Authorization update — $date_value

$task_id is the single \`Current\` task after two exact Human Owner \`AUTHORIZE\` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.
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
' "$checksum" >"$checksum_tmp" || die "could not regenerate handover checksum" "$EXIT_VALIDATION"
mv -- "$checksum_tmp" "$checksum"

git -C "$repo_root" diff --check ||
    die "post-change git diff --check failed; governance changes remain for inspection" \
        "$EXIT_VALIDATION"
run_governance_validation ||
    die "post-change governance validation failed; refusing to commit" "$EXIT_VALIDATION"

changed_files=()
mapfile -t changed_files < <(git -C "$repo_root" status --porcelain=v1 | sed 's/^...//')
[ "${#changed_files[@]}" -gt 0 ] || die "authorization produced no changes" "$EXIT_VALIDATION"
for changed in "${changed_files[@]}"; do
    allowed=0
    for expected in "${governance_files[@]}"; do
        if [ "$changed" = "$expected" ]; then allowed=1; break; fi
    done
    [ "$allowed" -eq 1 ] ||
        die "refusing non-governance authorization change: $changed" "$EXIT_VALIDATION"
done

staged=0
# shellcheck disable=SC2317  # Invoked indirectly by the EXIT trap below.
restore_index_on_failure() {
    local status=$?
    if [ "$status" -ne 0 ] && [ "$staged" -eq 1 ]; then
        git -C "$repo_root" restore --staged -- "${changed_files[@]}" 2>/dev/null || true
        printf 'Index restored; working-tree governance content was not discarded.\n' >&2
    fi
}
trap restore_index_on_failure EXIT

git -C "$repo_root" add -- "${changed_files[@]}"
staged=1
git -C "$repo_root" diff --cached --check ||
    die "staged validation failed" "$EXIT_VALIDATION"
staged_files=()
mapfile -t staged_files < <(git -C "$repo_root" diff --cached --name-only)
[ "${#staged_files[@]}" -eq "${#changed_files[@]}" ] ||
    die "staged authorization set differs from reviewed set" "$EXIT_VALIDATION"

commit_message="docs(governance): authorize $task_id"
if ! git -C "$repo_root" commit --quiet -m "$commit_message"; then
    die "authorization commit failed" "$EXIT_COMMIT"
fi
staged=0
trap - EXIT

commit_hash="$(git -C "$repo_root" rev-parse HEAD)"
[ "$(git -C "$repo_root" rev-parse HEAD^)" = "$head_before" ] ||
    die "authorization did not create exactly one commit" "$EXIT_COMMIT"
for committed in $(git -C "$repo_root" diff-tree --no-commit-id --name-only -r "$commit_hash"); do
    allowed=0
    for expected in "${governance_files[@]}"; do
        if [ "$committed" = "$expected" ]; then allowed=1; break; fi
    done
    [ "$allowed" -eq 1 ] || die "authorization commit contains disallowed file: $committed" \
        "$EXIT_COMMIT"
done
[ "$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)" = "$branch_before" ] ||
    die "branch changed unexpectedly" "$EXIT_COMMIT"
[ "$(git -C "$repo_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)" = \
    "$upstream_before" ] || die "upstream changed unexpectedly" "$EXIT_COMMIT"
[ "$(git -C "$repo_root" stash list)" = "$stash_before" ] ||
    die "stash list changed unexpectedly" "$EXIT_COMMIT"
[ -z "$(git -C "$repo_root" status --porcelain)" ] ||
    die "worktree is not clean after authorization commit" "$EXIT_COMMIT"

# --- Registered-branch preparation (GOV-AUTO-04) -------------------------------------------------
#
# Authorization is always recorded on the clean default-branch baseline verified above. Once that
# commit is safely in place, a registry-governed stage's own registered branch is created (or, on
# a resumed session, switched to) from it here — resolving OD-D10
# (docs/agentos-dashboard/OPEN_QUESTIONS.md): the local runner prompt forbids an implementation
# session from creating or switching branches itself, so this gate does it instead, immediately
# after the authorization commit and before any agent is launched. GOV/plain tasks (no registry
# row; required_branch == default_branch) are left exactly on default_branch, unchanged from
# before this task.
branch_after="$branch_before"
if [ -n "$registry" ] && [ "$required_branch" != "$default_branch" ]; then
    if workflow_prepare_branch "$repo_root" "$default_branch" "$required_branch"; then
        branch_after="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
    else
        die "authorization committed as $commit_hash, but the registered branch $required_branch could not be prepared automatically; resolve manually, then run scripts/workflow-next.sh" \
            "$EXIT_BRANCH_PREP"
    fi
fi

rule
note "Authorization commit : $commit_hash"
note "Commit message        : $commit_message"
note "Task                  : $task_id (single Current task)"
note "Working branch        : $branch_after"
note "Not pushed. Not merged. Upstream/stashes unchanged."
rule

if [ -z "$agent" ]; then
    note "Authorization complete. To launch implementation next, run:"
    note "  scripts/workflow-next.sh claude"
    note "  # or: scripts/workflow-next.sh codex"
    note "WORKFLOW_AUTHORIZATION_COMPLETE task=$task_id"
    exit 0
fi

runner=("$repo_root/scripts/workflow-next.sh" "$agent")
note "Launching the already-authorized task with: scripts/workflow-next.sh $agent"
set +e
"${runner[@]}"
runner_status=$?
set -e
exit "$runner_status"
