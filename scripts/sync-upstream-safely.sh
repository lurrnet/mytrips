#!/usr/bin/env bash
# Run from a clean checkout of main. Never pushes/merges into production main.
set -Eeuo pipefail
[[ -z "$(git status --porcelain)" ]] || { echo "Worktree must be clean" >&2; exit 1; }
[[ "$(git branch --show-current)" == main ]] || { echo "Checkout main first" >&2; exit 1; }
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream https://github.com/thiagodsti/partiu.git
git fetch upstream main --tags
git fetch origin main
git merge-base --is-ancestor HEAD origin/main || { echo "Local main diverged" >&2; exit 1; }
git merge --ff-only origin/main
if git merge-base --is-ancestor upstream/main HEAD; then echo "Already synchronized"; exit 0; fi
branch="chore/upstream-sync-$(date -u +%Y%m%d-%H%M%S)"
git switch -c "$branch"
if ! git merge --no-edit --no-ff upstream/main; then echo "Resolve conflicts on $branch and test before PR" >&2; exit 1; fi
echo "Upstream merge staged on $branch; review, test, push and open PR"
