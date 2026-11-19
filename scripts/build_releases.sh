#!/usr/bin/env bash
# Build the sellable release zips (3 tools + 2 services + lifetime bundle) into
# releases/ (gitignored). Names must match config.yaml tools.<id>.release_file /
# bundle.release_file — verified at the end.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

rm -rf releases
mkdir -p releases

INVOICE_STAGE="$(mktemp -d)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$INVOICE_STAGE" "$STAGE"' EXIT

# The invoice app is developed inside the store (it shares the design system),
# but the sold download must work offline on its own. Stage a self-contained
# copy: shared stylesheet + fonts + qr/motion scripts, paths rewritten.
stage_invoice() {
  local dest="$1"
  mkdir -p "$dest/css" "$dest/js" "$dest/fonts"
  cp site/tools/crypto-invoice-generator/app.html \
     site/tools/crypto-invoice-generator/app.css \
     site/tools/crypto-invoice-generator/app.js \
     site/tools/crypto-invoice-generator/README.md "$dest/"
  cp site/css/style.css "$dest/css/"
  cp site/js/qr.js site/js/motion.js "$dest/js/"
  cp site/fonts/*.woff2 "$dest/fonts/"
  python3 - "$dest/app.html" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
# local assets first, then remaining store links point at the live store
s = s.replace('href="../../css/style.css"', 'href="css/style.css"')
s = s.replace('href="../../fonts/', 'href="fonts/')
s = s.replace('src="../../js/qr.js"', 'src="js/qr.js"')
s = s.replace('src="../../js/motion.js"', 'src="js/motion.js"')
s = s.replace('href="../../', 'href="https://itsxwang.github.io/cash-register/')
s = s.replace('src="../../', 'src="https://itsxwang.github.io/cash-register/')
open(p, "w", encoding="utf-8").write(s)
PY
}

# Tool #1 — Crypto Invoice Generator v1.1.1 (client-side app + product README)
stage_invoice "$INVOICE_STAGE"
( cd "$INVOICE_STAGE" && zip -q -r "$ROOT/releases/crypto-invoice-generator-v1.1.1.zip" . )

# Tool #2 — Cron Ping Monitor v1.0.1
( cd tools_src/cron_ping &&
  zip -q "$ROOT/releases/cron-ping-monitor-v1.0.1.zip" \
      cron_ping.py monitors.example.json README.md )

# Tool #3 — Telegram Broadcast & Scheduler Bot v1.0.1
( cd tools_src/tg_broadcast &&
  zip -q "$ROOT/releases/telegram-broadcaster-v1.0.1.zip" \
      broadcast_bot.py README.md )

# Product #4 — Citation Monitor Weekly Digest v1.0.1 (agent-run service).
# The zip is the subscriber's onboarding pack: service README + sample digest.
# Delivery of the product itself is email (weekly digest), per config delivery_note.
( cd tools_src/citation_digest &&
  zip -q "$ROOT/releases/citation-monitor-weekly-digest-v1.0.1.zip" \
      README.md sample_digest.html )

# Product #5 — Citation Monitor Agency (agent-run service, 3 brands).
( cd tools_src/citation_digest_agency &&
  zip -q "$ROOT/releases/citation-monitor-agency-v1.0.1.zip" \
      README.md sample_digest.html )

# Lifetime bundle — all three tools in one zip, each in its own subfolder,
# plus a top-level README explaining what's inside. One payment, one download.
BUNDLE_ZIP="$ROOT/releases/cash-register-bundle-v1.1.1.zip"
mkdir -p "$STAGE/cash-register-bundle/cron-ping-monitor" \
         "$STAGE/cash-register-bundle/telegram-broadcaster"
stage_invoice "$STAGE/cash-register-bundle/crypto-invoice-generator"
( cd tools_src/cron_ping &&
  cp cron_ping.py monitors.example.json README.md "$STAGE/cash-register-bundle/cron-ping-monitor/" )
( cd tools_src/tg_broadcast &&
  cp broadcast_bot.py README.md "$STAGE/cash-register-bundle/telegram-broadcaster/" )
cat > "$STAGE/cash-register-bundle/README.md" <<'MD'
# Cash Register Bundle — all tools, one payment

Thank you for buying the lifetime bundle! Everything you paid for is in the
subfolders; each tool also has its own README.

- `crypto-invoice-generator/` — open `app.html` in any browser (fully offline:
  the folder includes its own CSS, fonts and QR library — keep it together)
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
