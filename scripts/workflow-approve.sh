#!/usr/bin/env bash
#
# workflow-approve.sh — the Human approval and local commit gate (GOV-AUTO-01).
#
# Shows the Human Owner exactly what changed, requires two explicit confirmations, then creates
# exactly one local commit containing exactly the files that were displayed and approved.
#
# This script NEVER pushes, merges, changes branches, alters upstream, rebases, resets, restores,
# amends, cherry-picks, or touches stashes. Publishing is always a separate, deliberate act.
#
# Usage:
#   scripts/workflow-approve.sh
#   scripts/workflow-approve.sh -m "feat(scope): subject"

set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_NOT_A_REPO=3
readonly EXIT_NOTHING_TO_COMMIT=4
readonly EXIT_WHITESPACE=5
readonly EXIT_CONFLICTS=6
readonly EXIT_DECLINED=7
readonly EXIT_BAD_MESSAGE=8
readonly EXIT_COMMIT_FAILED=9

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

# --- Build the exact file list, and display it in full -----------------------------------------
#
# Read with -z so paths containing spaces, quotes, or newlines survive intact. The status short
# format is "XY <path>"; a rename carries "XY <new>\0<old>" and both halves must be staged.

mapfile -d '' -t status_records < <(git -C "$repo_root" status --porcelain=v1 -z --untracked-files=all)

files=()
index=0
while [ "$index" -lt "${#status_records[@]}" ]; do
    record="${status_records[$index]}"
    index=$((index + 1))
    [ -n "$record" ] || continue
    x="${record:0:1}"
    y="${record:1:1}"
    path="${record:3}"
    files+=("$path")
    if [ "$x" = "R" ] || [ "$y" = "R" ] || [ "$x" = "C" ] || [ "$y" = "C" ]; then
        # The origin path of a rename/copy follows as its own NUL-terminated field.
        if [ "$index" -lt "${#status_records[@]}" ]; then
            files+=("${status_records[$index]}")
            index=$((index + 1))
        fi
    fi
done

[ "${#files[@]}" -gt 0 ] || die "no changed files resolved from git status" "$EXIT_NOTHING_TO_COMMIT"

note "Changed files (${#files[@]}):"
git -C "$repo_root" status --short --untracked-files=all
note ""
note "Diff stat (tracked changes):"
git -C "$repo_root" diff --stat
note ""
rule

# --- First confirmation: exact token ------------------------------------------------------------

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

# --- Commit message ------------------------------------------------------------------------------

if [ -z "$commit_message" ]; then
    note ""
    note "Enter the Conventional Commit message (single line):"
    printf 'Message: '
    IFS= read -r commit_message || true
fi

# Trim surrounding whitespace so a message of only spaces is treated as empty.
trimmed="${commit_message#"${commit_message%%[![:space:]]*}"}"
trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
commit_message="$trimmed"

[ -n "$commit_message" ] || die "commit message is empty" "$EXIT_BAD_MESSAGE"

# Conventional Commit shape: type(optional scope)!: subject. Validated so an accidental paste of a
# diff, a bare filename, or a stray shell fragment cannot become a commit subject.
if ! printf '%s' "$commit_message" |
    grep -Eq '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9._/-]+\))?!?: .+'; then
    die "not a valid Conventional Commit message: '$commit_message'" "$EXIT_BAD_MESSAGE"
fi
if [ "${#commit_message}" -lt 12 ]; then
    die "commit message subject is implausibly short: '$commit_message'" "$EXIT_BAD_MESSAGE"
fi

# --- Second confirmation: the exact staging list -------------------------------------------------

note ""
rule
note "The following ${#files[@]} file(s) will be staged and committed:"
for file in "${files[@]}"; do
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

# --- Stage exactly the displayed files -----------------------------------------------------------
#
# `git add --` with the explicit, previously displayed path list: never `git add -A`, so a file
# that appeared after the list was shown cannot be swept into the commit unseen.
#
# From here until the commit succeeds, a failure must unstage what this script staged without
# discarding any working-tree content. `git restore --staged` only rewrites the index.

unstage_on_failure() {
    local status=$?
    if [ "$status" -ne 0 ]; then
        printf '\nERROR: failed after staging. Unstaging the files this script staged.\n' >&2
        printf 'Working-tree content is NOT modified; your changes are intact.\n' >&2
        if [ "$head_before" = "(no commits yet)" ]; then
            git -C "$repo_root" rm --cached -r --quiet -- "${files[@]}" 2>/dev/null || true
        else
            git -C "$repo_root" restore --staged -- "${files[@]}" 2>/dev/null || true
        fi
        printf 'Index restored. Re-run scripts/workflow-approve.sh when resolved.\n' >&2
    fi
}
trap unstage_on_failure EXIT

git -C "$repo_root" add -- "${files[@]}"

note ""
note "Staged changes (git diff --cached --name-status):"
git -C "$repo_root" diff --cached --name-status
note ""
git -C "$repo_root" diff --cached --check
note "git diff --cached --check : clean"

# --- Exactly one commit ---------------------------------------------------------------------------

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
