#!/usr/bin/env bash
#
# scripts/lib/branch_prepare.sh — shared registered-branch lookup, preparation, and verification
# routines (GOV-AUTO-04), sourced by both scripts/workflow-authorize.sh and
# scripts/workflow-next.sh so the two gates cannot drift on how a registry-governed stage's
# branch precondition is satisfied. Resolves OD-D10 (docs/agentos-dashboard/OPEN_QUESTIONS.md):
# the registered-branch requirement and the local runner's no-branch-creation rule previously
# could not both be satisfied by one session.
#
# Every function here is read-only except workflow_prepare_branch, which is the only one that
# ever creates or switches a branch — and only from a clean worktree already sitting on the
# default branch. None of these functions ever push, merge, delete a branch, rewrite history, or
# touch a stash. This file is meant to be sourced, not executed.

# workflow_registered_branch <repo_root> <task_id>
#
# Prints the registered branch for <task_id> from whichever of this repository's stage
# registries (workflow-automation, agentos-dashboard) contains a matching row. Prints nothing
# (and returns 0) when the task has no registry row at all — the correct outcome for GOV/plain
# tasks, which are governed on the default branch, not a registered stage branch.
workflow_registered_branch() {
    local repo_root="$1" task_id="$2" candidate candidate_path row branch
    for candidate in \
        "docs/workflow-automation/STAGE_REGISTRY.md" \
        "docs/agentos-dashboard/STAGE_REGISTRY.md"; do
        candidate_path="$repo_root/$candidate"
        [ -f "$candidate_path" ] || continue
        row="$(awk -F '|' -v wanted="$task_id" '
            {
                cell = $2
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", cell)
                if (cell == wanted) { print; exit }
            }
        ' "$candidate_path")"
        [ -n "$row" ] || continue
        branch="$(printf '%s\n' "$row" | awk -F '|' '{gsub(/[` ]/, "", $6); print $6}')"
        [ -n "$branch" ] || continue
        printf '%s\n' "$branch"
        return 0
    done
    return 0
}

# workflow_prepare_branch <repo_root> <default_branch> <required_branch>
#
# No-op when <required_branch> is empty or equals <default_branch> — GOV/plain tasks stay on the
# default branch, exactly as before. Otherwise, from a clean worktree currently on
# <default_branch>, creates <required_branch> from the current HEAD and switches to it; or, if it
# already exists and already points at the current HEAD (a resumed session re-running
# preparation), just switches to it — idempotent, not a second creation.
#
# Refuses — prints one diagnostic line to stderr, returns 1, mutates nothing — when: the worktree
# is not clean; the current branch is neither <default_branch> nor already <required_branch>; or
# <required_branch> already exists but points somewhere other than the current HEAD (divergent or
# otherwise ambiguous history a human must resolve, never guessed at by this routine).
workflow_prepare_branch() {
    local repo_root="$1" default_branch="$2" required_branch="$3"
    local current_branch head_now branch_head

    if [ -z "$required_branch" ] || [ "$required_branch" = "$default_branch" ]; then
        return 0
    fi

    if [ -n "$(git -C "$repo_root" status --porcelain --untracked-files=all)" ]; then
        printf 'ERROR: cannot prepare branch %s: worktree is not clean\n' "$required_branch" >&2
        return 1
    fi
    if [ -n "$(git -C "$repo_root" ls-files --unmerged)" ]; then
        printf 'ERROR: cannot prepare branch %s: unresolved conflict entries exist\n' \
            "$required_branch" >&2
        return 1
    fi

    current_branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
    if [ "$current_branch" = "$required_branch" ]; then
        return 0
    fi
    if [ "$current_branch" != "$default_branch" ]; then
        printf 'ERROR: cannot prepare branch %s: expected to be on %s, found %s\n' \
            "$required_branch" "$default_branch" "$current_branch" >&2
        return 1
    fi

    head_now="$(git -C "$repo_root" rev-parse HEAD)"
    if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$required_branch"; then
        branch_head="$(git -C "$repo_root" rev-parse "refs/heads/$required_branch")"
        if [ "$branch_head" != "$head_now" ]; then
            printf \
                'ERROR: branch %s already exists at %s, diverging from %s at %s; refusing to switch\n' \
                "$required_branch" "$branch_head" "$default_branch" "$head_now" >&2
            return 1
        fi
        git -C "$repo_root" checkout --quiet "$required_branch" || return 1
        return 0
    fi

    git -C "$repo_root" checkout --quiet -b "$required_branch" || return 1

    if [ -n "$(git -C "$repo_root" status --porcelain --untracked-files=all)" ]; then
        printf 'ERROR: worktree became dirty while preparing branch %s\n' "$required_branch" >&2
        return 1
    fi
    return 0
}

# workflow_verify_branch <repo_root> <task_id> <current_branch>
#
# Read-only launch precondition (never creates or switches anything): if <task_id> has a
# registered branch that differs from <current_branch>, prints an explanatory error and returns
# 1. Returns 0 silently when the task has no registry row, or its registered branch already
# matches <current_branch>.
workflow_verify_branch() {
    local repo_root="$1" task_id="$2" current_branch="$3" required_branch
    required_branch="$(workflow_registered_branch "$repo_root" "$task_id")"
    if [ -n "$required_branch" ] && [ "$required_branch" != "$current_branch" ]; then
        printf 'ERROR: task %s is registered on branch %s but the current branch is %s\n' \
            "$task_id" "$required_branch" "$current_branch" >&2
        printf \
            'Run scripts/workflow-authorize.sh again to prepare it automatically, or switch manually.\n' \
            >&2
        return 1
    fi
    return 0
}
