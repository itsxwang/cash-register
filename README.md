# Cash Register 💸⛓️

**A reusable crypto-checkout + digital-product-delivery stack** — plus the first
three sellable micro-tools. Built for a solo founder with a $0 service budget:

- **Crypto-only revenue**: BTC, SOL, USDT on an EVM L2 (Base). No Stripe, no
  PayPal, no KYC, no processor cutoffs.
- **Static storefront**: pure HTML/CSS/JS, no framework, no build step.
  Serves from GitHub Pages or Cloudflare Pages for free.
- **Semi-automated confirmation**: manual CSV (v0) + keyless on-chain watchers
  (v1: mempool.space, public Solana RPC, Etherscan free tier).
- **Zero pip installs needed to run**: `requests` is optional (stdlib fallback);
  QR generation is vendored (`segno`, `qrcode.js`).

> Demo right now: `cd site && python3 -m http.server 8000` → http://localhost:8000
> Demo orders `DEMO-0001` (paid → download unlocked) and `DEMO-0002` (awaiting)
> are preloaded.

---

## Repository layout

```
├── config.yaml                # addresses, prices, watcher endpoints (placeholders!)
├── payments/                  # THE REUSABLE MODULE (generic, clean)
│   ├── __init__.py            # create_order / check_paid / mark_paid / sync_static
│   ├── config.py              # tiny YAML-subset parser (no PyYAML)
│   ├── db.py                  # SQLite persistence
│   ├── amounts.py             # exact crypto amounts (+ per-order noise)
│   ├── uris.py                # BIP-21 / Solana Pay / EIP-681 URIs
│   ├── manual.py              # v0: confirmations.csv
│   ├── watchers.py            # v1: BTC / SOL / EVM keyless watchers
│   ├── fx.py                  # USD→BTC/SOL rates (free APIs → config fallback)
│   ├── qr.py                  # segno wrapper (vendored)
│   └── cli.py                 # python3 -m payments create|check|mark|sync|demo|doctor
├── site/                      # the storefront (static, serves anywhere)
│   ├── index.html             # home: tool grid from data/catalog.json
│   ├── status.html            # order status lookup
│   ├── download.html          # unlocked download page
│   ├── data/                  # catalog.json + per-order JSON + QR SVGs (generated)
│   └── tools/<slug>/          # landing + checkout per tool (+ the invoice app)
├── tools_src/
│   ├── cron_ping/             # tool #2: cron pinger + static status page
│   └── tg_broadcast/          # tool #3: telegram broadcast/scheduler (raw API)
├── tests/smoke_test.py        # 25 offline checks of the whole pipeline
└── vendor/                    # segno (BSD-3), qrcode.js (MIT) — no pip needed
```

## How a payment flows, end to end

```
 BUYER                                     FOUNDER (one laptop, $0 infra)
 ─────                                     ──────────────────────────────
 checkout page
   ├─ picks network (USDT/SOL/BTC)
   ├─ sees exact amount + address
   │    + memo + wallet QR
   │    (QR built client-side)
   ├─ pays from any wallet
   └─ "I've paid" → email/Telegram
        report (order id, txid)  ────────►  1) `payments ingest --order CR-XX… --tool t
                                                    (registers the id, optional --amount)
                                            2) confirms the money arrived:
                                               v0: wallet app → append row to
                                                   payments/confirmations.csv
                                               v1: `payments check --all`
                                                   runs the on-chain watchers
                                                   (mempool.space / Solana RPC /
                                                   Etherscan) and auto-marks
                                                   exact-amount matches
                                            3) `payments sync`
                                               rewrites site/data/orders/*.json
                                            4) git push → Pages redeploys

 buyer opens /status.html?order=CR-XX…
   └─ status paid → download link
      (GitHub Releases URL + per-order token)
```

### Matching logic (why exact amounts + memos)

- **USDT (EVM L2)**: buyer pays the exact USD price. Watcher matches
  `to == receiving address`, `value == expected units (6 decimals)`, recent timestamp.
- **BTC / SOL**: the order carries a per-order "noise" suffix (sats/lamports)
  derived from the order sequence, so two orders rarely demand the same amount
  → an exact match inside the lookback window identifies the payer without a memo.
- **Memos** (where supported — BTC OP_RETURN, Solana Memo program) match the
  order id `CR-XXXXXXXX`.
- Watchers **never crash the flow**: unreachable API ⇒ chain skipped, note stored,
  manual CSV confirmations always remain the fallback.

## The payments module API (reuse for product #4 …)

```python
from payments import create_order, check_paid, mark_paid, sync_static, load_config

cfg = load_config()                       # reads config.yaml
order = create_order("my-new-tool", 19)   # → order id, memo, exact amount, address
order = check_paid(order["order_id"])     # CSV (v0) + watchers (v1)
mark_paid(order["order_id"], txid="...")  # manual override, always works
sync_static()                             # refreshes site/data/*.json + QR SVGs
```

CLI equivalents: `python3 -m payments create|ingest|check|mark|sync|list|rotate|demo|doctor`.
Run `python3 -m payments doctor` to probe every chain API before launch.

## Delivery — how buyers get files (free)

1. Create a **releases repo** (e.g. `cash-register-releases`), then for each
   tool create a Release and upload the tool's zip
   (`stablecoin-invoice-generator-v1.0.0.zip`, …).
2. Put the repo name into `config.yaml → delivery.releases_base`.
3. A **paid** order JSON gets `"download": {"url": <release URL>, "token": …}`;
   `download.html` shows the link only to orders marked paid.
4. **One-time-ness (v0, honest version):** each order gets a random token and
   `payments rotate --order ID` invalidates a leaked link on the next deploy.
   GitHub Release files themselves are not access-controlled — if you need
   hard one-time enforcement later, that's the first thing a paid-tier
   backend would add (see roadmap in LAUNCH_CHECKLIST.md).
5. **Manual delivery (also v0):** from the buyer's report you can just reply on
   Telegram/email with the release link — the storefront link is a convenience,
   not a dependency.

## How to add tool #4

1. Build it (aim: one file or one folder, stdlib-only).
2. Add a block under `tools:` in `config.yaml` (name, blurb, price, chains,
   `release_file`, landing/checkout paths).
3. Copy `site/tools/<any-tool>/checkout.html` into
   `site/tools/<slug>/checkout.html` (slug = config key); write its landing page.
4. `python3 -m payments sync` → catalog + pages pick it up automatically.
5. Zip the tool, upload to the releases repo with the name from `release_file`.
   Nothing else changes — checkout, status, and delivery are generic.

## Pricing (suggested, validated shape for micro-tools)

| Item | Price | Why |
|---|---|---|
| Stablecoin Invoice Generator | **$19** | Highest demand (stablecoin B2B is the strongest crypto adoption lane); saves hours per client |
| Cron Ping Monitor | **$9** | Impulse-buy tier; status page is instantly understandable |
| Telegram Broadcast Bot | **$15** | Mid-tier; direct revenue value for list owners |
| Lifetime bundle | **$49** | ~2.4× single price; anchors bundle > sum feels like a deal |
| Custom tool (request) | **from $99** | One-off builds for crypto freelancers; the bundle page is the lead magnet |

Raise prices, never lower: micro-tools sell on time saved, not cents.

## Local development

```bash
python3 tests/smoke_test.py          # 25 checks, offline, uses temp dirs
cd site && python3 -m http.server    # the storefront demo
python3 -m payments demo             # regenerate demo fixtures
python3 -m payments doctor           # probe chain APIs (EVM needs ETHERSCAN_API_KEY)
```

Only dependency: `requests` (`pip install -r requirements.txt`) — optional;
stdlib `urllib` is used automatically if it's absent.

## Honest limitations (read before launch)

- Addresses in `config.yaml` are **placeholders**; never publish without
  replacing them (see LAUNCH_CHECKLIST.md).
- Confirmation latency: v0 is manual; expect minutes-to-hours, not seconds.
- The static site is public by design; order JSONs contain no personal data —
  order ids are unguessable (`CR-` + 8 chars from a 32-symbol alphabet).
- True one-time download enforcement and auto-fulfilment without a push are
  backend features (v2); v0 relies on tokens + rotation + manual process.
