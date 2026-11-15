#!/usr/bin/env bash
# Sync site/ into the gh-pages worktree and push to GitHub Pages.
# Run after 'payments sync'. Usage: scripts/sync_ghpages.sh [worktree-dir]
set -e
WT="${1:-$HOME/venture-00-ghpages}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -e "$WT/.git" ] || { echo "ERROR: gh-pages worktree not found at $WT"; exit 1; }
if command -v rsync >/dev/null; then
  rsync -a --delete --exclude .git --exclude .nojekyll "$ROOT/site/" "$WT/"
else
  find "$WT" -mindepth 1 -maxdepth 1 ! -name .git ! -name .nojekyll -exec rm -rf {} +
  cp -a "$ROOT/site/." "$WT/"
fi
touch "$WT/.nojekyll"
cd "$WT"
git add -A
if git diff --cached --quiet; then echo "gh-pages already up to date"; exit 0; fi
git commit -qm "sync: site data $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
git push -q origin gh-pages
echo "gh-pages pushed."
