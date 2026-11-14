#!/usr/bin/env bash
# Build the three sellable-tool release zips into releases/ (gitignored).
# Reproducible: same inputs -> same file names; zips carry no absolute paths.
# Names must match config.yaml tools.<id>.release_file — verified at the end.
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
if missing:
    sys.exit("release_file names in config.yaml do not match built zips: " + ", ".join(missing))
print("All release zips match config.yaml.")
EOF

echo "Done. Upload each zip as a GitHub Release asset named exactly as above."
