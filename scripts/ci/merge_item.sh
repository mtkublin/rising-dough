#!/usr/bin/env bash
# Gated merge of one finished work item into the current work branch
# (orchestrator-mode skill section 5, ADR-0066). Usage: merge_item.sh <ID> <MSG>
# Env: WORK_BRANCH overrides the target (default: the current branch; never main).
# Merges skip the pre-commit hooks, so the checks run here before anything is pushed.
set -euo pipefail

id="${1:?usage: merge_item.sh <ID> <MSG>}"
msg="${2:?usage: merge_item.sh <ID> <MSG> (the summary is required)}"

current="$(git rev-parse --abbrev-ref HEAD)"
work="${WORK_BRANCH:-$current}"
if [[ "$work" == "main" || "$work" == "master" ]]; then
    echo "refusing: work branch is $work" >&2
    exit 1
fi
if [[ "$work" != "$current" ]]; then
    echo "refusing: current branch is $current, expected $work" >&2
    exit 1
fi
git_dir="$(git rev-parse --git-dir)"
if [[ -e "$git_dir/MERGE_HEAD" ]]; then
    echo "refusing: a merge is in progress (MERGE_HEAD exists)" >&2
    exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "refusing: working tree is dirty" >&2
    exit 1
fi

branch="wi/${work}/${id}"
git rev-parse --verify --quiet "refs/heads/${branch}" >/dev/null \
    || { echo "no such branch: ${branch}" >&2; exit 1; }
worktree="$(git worktree list --porcelain | awk -v b="refs/heads/${branch}" '
    $1 == "worktree" { wt = substr($0, 10) }
    $1 == "branch" && $2 == b { print wt }')"

if ! git merge --no-ff "$branch" -m "merge(${id}): ${msg}"; then
    echo "conflicting files:" >&2
    git diff --name-only --diff-filter=U >&2
    git merge --abort
    echo "merge ${work} into the item branch and resolve (git -C <worktree> merge --no-edit ${work})" >&2
    exit 1
fi

fail() {
    echo "FAILED: $1. The merge commit is left in place (not reset, not pushed, nothing pruned)." >&2
    exit 1
}
just guards || fail "just guards"
uv run lint-imports || fail "lint-imports"
uv run ruff check src tests || fail "ruff check"
uv run mypy src tests || fail "mypy"

git push origin "$work"

if [[ -n "$worktree" ]]; then
    git worktree remove -f -f "$worktree"
fi
git branch -D "$branch"
if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    git push origin --delete "$branch"
fi
# Failed worktree creation leaves worktree-agent-* branches with no commits of their own.
while read -r stale; do
    [[ -n "$stale" ]] || continue
    if [[ "$(git rev-list --count "${work}..${stale}")" == "0" ]]; then
        git branch -D "$stale"
    fi
done < <(git for-each-ref --format='%(refname:short)' 'refs/heads/worktree-agent-*')

git rev-parse HEAD
