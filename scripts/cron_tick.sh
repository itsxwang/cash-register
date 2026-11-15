#!/usr/bin/env bash
# Cron tick: check on-chain payments, re-sync site data, push to GitHub (main + gh-pages).
set -u
[ -f "$HOME/.cashregister-env" ] && . "$HOME/.cashregister-env"
cd /home/xion/venture-00-cash-register || exit 1
mkdir -p payments/data
{
  echo "--- tick $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  python3 -m payments check --all || true
  python3 -m payments sync || true
  if [ -n "$(git status --porcelain site/data)" ]; then
    git add site/data
    git commit -qm "sync: order data $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    git push -q origin main || true
    bash scripts/sync_ghpages.sh || true
  fi
} >> payments/data/cron.log 2>&1
