#!/usr/bin/env bash
# Build the sellable release zips (3 tools + lifetime bundle) into releases/
# (gitignored). Reproducible: same inputs -> same file names; no absolute paths.
# Names must match config.yaml tools.<id>.release_file / bundle.release_file —
# verified at the end.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

rm -rf releases
mkdir -p releases

# Tool #1 — Crypto Invoice Generator v1.1.0 (client-side app + product README)
( cd site/tools/crypto-invoice-generator &&
  zip -q -r "$ROOT/releases/crypto-invoice-generator-v1.1.0.zip" \
      app.html app.css app.js README.md )

# Tool #2 — Cron Ping Monitor v1.0.0
( cd tools_src/cron_ping &&
  zip -q "$ROOT/releases/cron-ping-monitor-v1.0.0.zip" \
      cron_ping.py monitors.example.json README.md )

# Tool #3 — Telegram Broadcast & Scheduler Bot v1.0.0
( cd tools_src/tg_broadcast &&
  zip -q "$ROOT/releases/telegram-broadcaster-v1.0.0.zip" \
      broadcast_bot.py README.md )

# Product #4 — Citation Monitor Weekly Digest v1.0.0 (agent-run service).
# The zip is the subscriber's onboarding pack: service README + sample digest.
# Delivery of the product itself is email (weekly digest), per config delivery_note.
( cd tools_src/citation_digest &&
  zip -q "$ROOT/releases/citation-monitor-weekly-digest-v1.0.0.zip" \
      README.md sample_digest.html )

# Lifetime bundle — all three tools in one zip, each in its own subfolder,
# plus a top-level README explaining what's inside. One payment, one download.
BUNDLE_ZIP="$ROOT/releases/cash-register-bundle-v1.1.0.zip"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/cash-register-bundle/crypto-invoice-generator" \
         "$STAGE/cash-register-bundle/cron-ping-monitor" \
         "$STAGE/cash-register-bundle/telegram-broadcaster"
( cd site/tools/crypto-invoice-generator &&
  cp app.html app.css app.js README.md "$STAGE/cash-register-bundle/crypto-invoice-generator/" )
( cd tools_src/cron_ping &&
  cp cron_ping.py monitors.example.json README.md "$STAGE/cash-register-bundle/cron-ping-monitor/" )
( cd tools_src/tg_broadcast &&
  cp broadcast_bot.py README.md "$STAGE/cash-register-bundle/telegram-broadcaster/" )
cat > "$STAGE/cash-register-bundle/README.md" <<'MD'
# Cash Register Bundle — all tools, one payment

Thank you for buying the lifetime bundle! Everything you paid for is in the
subfolders; each tool also has its own README.

- `crypto-invoice-generator/` — open `app.html` in any browser (works offline)
- `cron-ping-monitor/` — `python3 cron_ping.py --help` (stdlib only)
- `telegram-broadcaster/` — `python3 broadcast_bot.py --help` (needs a bot token)

Lifetime updates: keep your order id — re-download any time from the store's
download page, or email the founder (the address on your receipt).
MD
( cd "$STAGE" && zip -q -r "$BUNDLE_ZIP" cash-register-bundle )

# Verify names match config.yaml
python3 - <<'EOF'
import sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from payments.config import load_config
cfg = load_config()
missing = []
for tid, tool in cfg["tools"].items():
    z = Path("releases") / tool["release_file"]
    if not z.is_file():
        missing.append(str(z)); continue
    with zipfile.ZipFile(z) as zf:
        bad = zf.testzip()
        assert bad is None, f"corrupt member {bad} in {z}"
    print(f"OK  {z}  ({z.stat().st_size} bytes)")
bundle = Path("releases") / cfg["bundle"]["release_file"]
if bundle.is_file():
    with zipfile.ZipFile(bundle) as zf:
        names = zf.namelist()
        assert zf.testzip() is None
        for sub in ("crypto-invoice-generator/app.html", "cron-ping-monitor/cron_ping.py",
                    "telegram-broadcaster/broadcast_bot.py", "README.md"):
            assert any(n.endswith(sub) for n in names), f"bundle missing {sub}"
    print(f"OK  {bundle}  ({bundle.stat().st_size} bytes, {len(names)} members)")
else:
    missing.append(str(bundle))
if missing:
    sys.exit("release_file names in config.yaml do not match built zips: " + ", ".join(missing))
print("All release zips match config.yaml.")
EOF

echo "Done. Upload each zip as a GitHub Release asset named exactly as above."
