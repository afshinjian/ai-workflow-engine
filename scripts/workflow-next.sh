#!/usr/bin/env bash
#
# workflow-next.sh — launch exactly one Human-gated implementation session (GOV-AUTO-01).
#
# Runs the read-only preflight for the repository's standard task cycle, then hands the canonical
# implementation prompt to one agent session. It performs no Git mutation of any kind: no commit,
# no push, no merge, no branch change, no upstream change, and no stash operation. The approval
# and commit gate is a separate, explicitly Human-driven step (scripts/workflow-approve.sh).
#
# Usage:
#   scripts/workflow-next.sh claude
#   scripts/workflow-next.sh codex
#
# Exit status: the agent command's own exit status, or a non-zero preflight failure code.

set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_NOT_A_REPO=3
readonly EXIT_DIRTY_WORKTREE=4
readonly EXIT_MISSING_PROMPT=5
readonly EXIT_WHITESPACE=6
readonly EXIT_AGENT_MISSING=7

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit "${2:-1}"
}

note() { printf '%s\n' "$1"; }

rule() { printf -- '---------------------------------------------------------------\n'; }

usage() {
    cat >&2 <<'USAGE'
Usage: workflow-next.sh <agent>

  <agent>   claude | codex

Launches one Human-gated implementation session using the canonical prompt at
scripts/prompts/implement-next-task.md. Performs no Git mutation.
USAGE
}

# --- Argument handling: fail closed on anything unrecognised -----------------------------------

if [ "$#" -ne 1 ]; then
    usage
    die "exactly one agent argument is required (got $#)" "$EXIT_USAGE"
fi

case "$1" in
    claude | codex)
        agent="$1"
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        usage
        die "unsupported agent: '$1' (expected 'claude' or 'codex')" "$EXIT_USAGE"
        ;;
esac
readonly agent

# --- Repository root: derived from this script's own location, never the caller's cwd ----------

# BASH_SOURCE rather than $0 so the path is correct when the script is sourced or invoked through
# a symlink, and `cd -P` so a symlinked scripts/ directory resolves to its real location.
script_path="${BASH_SOURCE[0]}"
while [ -L "$script_path" ]; do
    link_target="$(readlink "$script_path")"
    case "$link_target" in
        /*) script_path="$link_target" ;;
        *) script_path="$(cd -P "$(dirname "$script_path")" && pwd)/$link_target" ;;
    esac
done
script_dir="$(cd -P "$(dirname "$script_path")" && pwd)"
readonly script_dir

repo_root="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null)" ||
    die "not inside a Git repository (script located at $script_dir)" "$EXIT_NOT_A_REPO"
readonly repo_root

# --- Confirm this is the expected repository ---------------------------------------------------
#
# "Expected" means the worktree that actually contains this script and the repository's own
# governance marker. Checking markers rather than a hard-coded absolute path keeps the script
# correct if the repository is cloned elsewhere, while still refusing to drive an unrelated tree.

readonly prompt_file="$repo_root/scripts/prompts/implement-next-task.md"

[ -f "$repo_root/self-governance.yaml" ] ||
    die "missing self-governance.yaml in $repo_root — not the expected repository" "$EXIT_NOT_A_REPO"

note "AgentOS local task runner — preflight"
rule
note "Repository : $repo_root"
note "Agent      : $agent"
rule

# --- Read-only repository state ----------------------------------------------------------------

branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
head_sha="$(git -C "$repo_root" rev-parse HEAD)"

note "Branch     : $branch"
note "HEAD       : $head_sha"
note ""
note "Git status:"
git -C "$repo_root" status --short --branch
note ""
note "Stashes (must remain unchanged):"
if stash_list="$(git -C "$repo_root" stash list)" && [ -n "$stash_list" ]; then
    printf '%s\n' "$stash_list"
else
    note "  (none)"
fi
stash_before="$(git -C "$repo_root" stash list | wc -l)"
readonly stash_before
note ""

# --- Whitespace / conflict-marker check --------------------------------------------------------

if ! git -C "$repo_root" diff --check; then
    die "git diff --check reported whitespace or conflict-marker errors" "$EXIT_WHITESPACE"
fi
note "git diff --check : clean"

# --- Refuse to start on a dirty worktree -------------------------------------------------------
#
# A new task must never begin on top of unreviewed work: the resulting diff could not be
# attributed to one task, and the approval gate would be asked to approve a mixture.

if [ -n "$(git -C "$repo_root" status --porcelain)" ]; then
    note ""
    note "Uncommitted changes present:"
    git -C "$repo_root" status --short
    note ""
    die "worktree is not clean — commit or set aside the current work before starting a new task (see scripts/workflow-approve.sh)" "$EXIT_DIRTY_WORKTREE"
fi
note "Worktree         : clean"

# --- Prompt file -------------------------------------------------------------------------------

[ -f "$prompt_file" ] || die "missing implementation prompt: $prompt_file" "$EXIT_MISSING_PROMPT"
[ -s "$prompt_file" ] || die "implementation prompt is empty: $prompt_file" "$EXIT_MISSING_PROMPT"
note "Prompt file      : $prompt_file"

command -v "$agent" >/dev/null 2>&1 ||
    die "agent CLI '$agent' not found on PATH" "$EXIT_AGENT_MISSING"

prompt_text="$(cat -- "$prompt_file")"

rule
note "Preflight passed. Launching one $agent session."
note "No commit, push, merge, branch change, or stash operation will be performed."
rule

# --- Launch exactly one agent session ----------------------------------------------------------
#
# The command is built as an array and expanded with "${cmd[@]}", so the prompt is passed as a
# single argv element. It is never interpolated into a command string and `eval` is never used:
# shell metacharacters inside the prompt are inert data.

case "$agent" in
    claude) cmd=(claude "$prompt_text") ;;
    codex) cmd=(codex "$prompt_text") ;;
esac

set +e
"${cmd[@]}"
agent_status=$?
set -e

# --- Post-run integrity note -------------------------------------------------------------------

stash_after="$(git -C "$repo_root" stash list | wc -l)"
rule
if [ "$stash_before" != "$stash_after" ]; then
    printf 'WARNING: stash count changed during the session (%s -> %s). Investigate before approving.\n' \
        "$stash_before" "$stash_after" >&2
fi

if [ "$agent_status" -eq 0 ]; then
    note "Session finished (exit 0)."
    note "Next: review the implementation report and the repository diff, then run:"
    note "  scripts/workflow-approve.sh"
else
    note "Session exited non-zero (exit $agent_status). No changes were committed."
fi
note "WORKFLOW_NEXT_COMPLETE agent=$agent status=$agent_status"

exit "$agent_status"
