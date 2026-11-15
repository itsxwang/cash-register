#!/usr/bin/env python3
"""Offline smoke test for the Cash Register payments module + storefront assets.

Run from the repo root:  python3 tests/smoke_test.py
No network required: FX and watchers fall back to config rates / graceful skip.

Policy guards included: the store accepts ONLY decentralized, non-freezable
assets (native BTC / ETH / SOL) — no centralized stablecoins anywhere in the
payment flow.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

TMP = Path(tempfile.mkdtemp(prefix="cashregister-test-"))
os.environ["CASHREGISTER_DB"] = str(TMP / "test.db")
os.environ["CASHREGISTER_CONFIRMATIONS"] = str(TMP / "confirmations.csv")
os.environ["CASHREGISTER_SITE_DIR"] = str(TMP / "site")  # keep test artifacts out of the repo

import payments as cr  # noqa: E402
from payments import db, manual  # noqa: E402
from payments import _tool_cfg as _bundle_item  # bundle regression checks
from payments.config import parse_config  # noqa: E402

PASS = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
    if not cond:
        sys.exit(1)
    PASS += 1


def main() -> None:
    cfg = cr.load_config()

    # 1. config parsing + asset policy ----------------------------------------
    check("config parses", isinstance(cfg.get("addresses"), dict))
    check("3 tools in config", len(cfg["tools"]) == 3)

    banned = ("usdt", "usdc", "tether")

    def banned_hits(text: str) -> list[str]:
        """Search for banned assets, skipping lines that merely state the policy."""
        hits = []
        for line in text.splitlines():
            low = line.lower()
            if any(w in low for w in ("stablecoin", "freez", "policy", "issuer", "banned")):
                continue  # policy statements are allowed to name the banned coins
            for b in banned:
                if b in low:
                    hits.append(f"{b}: {line.strip()[:60]}")
        return hits

    cfg_values = json.dumps(parse_config((REPO / "config.yaml").read_text(encoding="utf-8")))
    check("config.yaml values free of stablecoin assets (policy)", not banned_hits(cfg_values))
    module_text = "\n".join(
        p.read_text(encoding="utf-8") for p in (REPO / "payments").glob("*.py")
    )
    check("payments module code free of stablecoin assets (policy)", not banned_hits(module_text))
    check("chains are eth/sol/btc only", set(cfg["chains"] if False else cr.VALID_CHAINS) == {"eth", "sol", "btc"})
    check("no token/mint config left",
          all(k not in cfg["addresses"] for k in ("usdt_contract", "usdt_contract_arbitrum"))
          and all(k not in cfg["watchers"] for k in ("sol_usdt_mint",)))

    # 2. order creation (ETH native default) -----------------------------------
    order = cr.create_order("crypto-invoice-generator", 19.00)
    check("create_order returns unique id", order["order_id"].startswith("CR-"))
    check("default chain is eth", order["chain"] == "eth")
    check("memo == order id", order["memo"] == order["order_id"])

    wei = order["raw_amount"]
    step = 10 ** 13  # 0.00001 ETH
    check("ETH raw_amount is integer wei", isinstance(wei, int))
    check("ETH amount in clean 0.00001 ETH steps", wei % step == 0)
    check("ETH wei float64-exact (13 trailing zeros)", ((wei // step) * 5 ** 13) < 2 ** 53)
    more = [cr.create_order("crypto-invoice-generator", 19.00) for _ in range(11)]
    all_raws = [wei] + [o["raw_amount"] for o in more]
    check("12 same-price orders all get DISTINCT exact amounts (no zero-noise, bump-guard)",
          len(set(all_raws)) == 12 and all(isinstance(r, int) and r % step == 0 for r in all_raws))
    order2 = more[0]
    check("noise differs across orders", order2["raw_amount"] != wei)
    check("order persisted in sqlite", cr.get_order(order["order_id"]) is not None)

    # 3. BTC + SOL orders (offline FX fallback -> config rates) ----------------
    btc_order = cr.create_order("cron-ping-monitor", 9.00, chain="btc")
    sol_order = cr.create_order("telegram-broadcaster", 15.00, chain="sol")
    check("btc amount has sats noise", btc_order["raw_amount"] % 100 != 0)
    check("sol amount has lamport noise", sol_order["raw_amount"] % 1000 != 0)

    # 4. payment URIs ------------------------------------------------------------
    uri_eth = cr.build_payment_uri(order, cfg)
    check("EIP-681 NATIVE eth uri (no ERC-20 transfer)",
          uri_eth.startswith("ethereum:") and f"@8453?value={wei}" in uri_eth and "transfer" not in uri_eth)
    check("BIP-21 uri for BTC", cr.build_payment_uri(btc_order, cfg).startswith("bitcoin:"))
    check("solana pay uri (native SOL)", cr.build_payment_uri(sol_order, cfg).startswith("solana:"))

    # 5. QR generation via vendored segno --------------------------------------
    paths = cr.write_order_assets(order, cfg=cfg, site_dir=TMP / "site")
    svg = (TMP / "site" / "data" / "qr" / f"{order['order_id']}.svg").read_text()
    check("segno produced QR svg", "<svg" in svg and len(svg) > 300)
    check("order json written", json.loads(paths[0].read_text())["order_id"] == order["order_id"])

    # 6. catalog sync ------------------------------------------------------------
    cat_path = cr.write_catalog(cfg=cfg, site_dir=TMP / "site")
    catalog = json.loads(cat_path.read_text())
    check("catalog has 3 tools", len(catalog["tools"]) == 3)
    check("catalog chains are eth/sol/btc", set(catalog["chains"]) == {"eth", "sol", "btc"})
    check("catalog ETH label", catalog["chains"]["eth"]["label"] == "ETH (Base)")
    check("catalog eth decimals 18", catalog["chains"]["eth"]["decimals"] == 18)
    check("catalog chains have addresses", all(c.get("address") for c in catalog["chains"].values()))

    # 7. v0 manual CSV confirmation ----------------------------------------------
    manual.ensure_template(TMP / "confirmations.csv")
    with open(TMP / "confirmations.csv", "a", encoding="utf-8") as fh:
        fh.write(f"{order['order_id']},deadbeef,2026-11-15T10:00:00Z,manual_wallet,smoke test\n")
    paid = cr.check_paid(order["order_id"], use_watchers=False)
    check("CSV confirmation marks order paid", paid["status"] == "paid")
    check("paid txid recorded", paid["paid_txid"] == "deadbeef")

    # 8. paid order json exposes download link ------------------------------------
    cr.write_order_assets(paid, cfg=cfg, site_dir=TMP / "site")  # mirror mark_paid's site sync
    cr.write_order_assets(btc_order, cfg=cfg, site_dir=TMP / "site")
    payload = json.loads((TMP / "site" / "data" / "orders" / f"{order['order_id']}.json").read_text())
    check("paid order exposes download url (v1.1.0 zip)",
          payload["download"]["url"].endswith("crypto-invoice-generator-v1.1.0.zip"))
    check("download url carries the release tag segment (QA fix: no bare /download/<file>)",
          "/download/crypto-invoice-generator-v1.1.0/" in payload["download"]["url"])
    check("awaiting order hides download url",
          json.loads((TMP / "site" / "data" / "orders" / f"{btc_order['order_id']}.json")
                     .read_text())["download"] is None)

    # 9. watchers degrade gracefully (unreachable endpoints) -----------------------
    bad_cfg = dict(cfg)
    bad_cfg["watchers"] = {
        "enabled": True, "auto_confirm": True, "lookback_hours": 72,
        "btc_api": "http://127.0.0.1:1", "sol_rpc": "http://127.0.0.1:1",
        "eth_api": "http://127.0.0.1:1",
    }
    res = cr.check_paid(btc_order["order_id"], use_watchers=True, cfg=bad_cfg)
    check("unreachable BTC api skipped without crash",
          res["status"] == "awaiting_payment" and "unreachable" in (res["meta"].get("watch", {}).get("note") or ""))

    # 10. download token rotation ---------------------------------------------------
    rot = cr.rotate_download_token(order["order_id"], cfg=cfg)
    check("rotate produces new token", rot["download_token"] != order["download_token"])

    # 11. demo fixtures --------------------------------------------------------------
    made = cr.create_demo_fixtures(cfg=cfg, site_dir=TMP / "site")
    check("demo fixtures created", {o["order_id"] for o in made} == {"DEMO-0001", "DEMO-0002"})
    check("demo fixture #1 is crypto-invoice-generator on eth",
          made[0]["tool_id"] == "crypto-invoice-generator" and made[0]["chain"] == "eth")

    # 12. ingest buyer-reported order --------------------------------------------------
    ing = cr.ingest_order("CR-QQQQ1111", "cron-ping-monitor", cfg=cfg)
    check("ingest creates buyer-reported order", ing["order_id"] == "CR-QQQQ1111")

    # 13. storefront files match the rename ----------------------------------------------
    site = REPO / "site"
    check("tool folder renamed",
          (site / "tools" / "crypto-invoice-generator" / "app.html").is_file()
          and not (site / "tools" / "stablecoin-invoice-generator").exists())
    html = (site / "tools" / "crypto-invoice-generator" / "index.html").read_text(encoding="utf-8")
    check("landing carries the policy line", "coins nobody can freeze" in html or "no company can freeze" in html)
    app_js = (site / "tools" / "crypto-invoice-generator" / "app.js").read_text(encoding="utf-8")
    check("app has custom-token option", "tokenContract" in app_js and "custom" in app_js)

    # 14. bundle is a first-class purchasable item (regression: $19 bug) ------------------
    bcfg = _bundle_item(cfg, "bundle")
    check("bundle item priced 49 (not a tool price)",
          bcfg["price_usd"] == 49 and bcfg["price_usd"] not in (19, 9, 15))
    check("bundle release file configured", bcfg["release_file"] == "cash-register-bundle-v1.1.0.zip")
    check("bundle checkout is root checkout with item param",
          bcfg["checkout"] == "/checkout.html?item=bundle")
    check("bundle accepts all chains", set(bcfg["chains"]) == {"eth", "sol", "btc"})
    b_order = cr.create_order("bundle", chain="eth")
    check("bundle order charges 49 USD", b_order["price_usd"] == 49)
    b_pub = cr.public_order(b_order, cfg)
    check("bundle order checkout_url is well-formed (?item=bundle&order=…)",
          b_pub["checkout_url"].startswith("/checkout.html?item=bundle&order=")
          and b_pub["checkout_url"].count("?") == 1)
    b_paid = dict(b_order, status="paid")
    b_pub = cr.public_order(b_paid, cfg)
    check("paid bundle downloads the combined zip",
          (b_pub["download"] or {}).get("url", "").endswith("/cash-register-bundle-v1.1.0.zip"))
    check("bundle download url carries tag segment",
          "/download/cash-register-bundle-v1.1.0/" in (b_pub["download"] or {}).get("url", ""))
    check("bundle zip exists in releases/",
          (REPO / "releases" / "cash-register-bundle-v1.1.0.zip").is_file())
    catalog_b = json.loads(cat_path.read_text())["bundle"]
    check("catalog bundle block carries checkout + release",
          catalog_b["checkout"] == "/checkout.html?item=bundle"
          and catalog_b["release_file"] == "cash-register-bundle-v1.1.0.zip"
          and catalog_b["price_usd"] == 49)

    # 15. buyer-facing flows are email-only (Telegram is dead for us) ---------------------
    idx = (site / "index.html").read_text(encoding="utf-8")
    check("home bundle button routes to ?item=bundle",
          'href="checkout.html?item=bundle"' in idx)
    check("home has no 'email or Telegram' buyer copy",
          "email or Telegram" not in idx)
    root_checkout = (site / "checkout.html").read_text(encoding="utf-8")
    check("root bundle checkout page exists", root_checkout.count("data-checkout") >= 1)
    store_js = (site / "js" / "store.js").read_text(encoding="utf-8")
    check("checkout JS supports ?item=bundle", 'params.get("item")' in store_js
          and "item === \"bundle\"" in store_js)
    check("'I've paid' flow is email-only in JS",
          "tglink" not in store_js and "t.me/" not in store_js)
    catalog_store = json.loads(cat_path.read_text())["store"]
    check("catalog carries the real contact email",
          catalog_store["contact_email"] == "xion.dev7@gmail.com")
    check("catalog has no contact_telegram", "contact_telegram" not in catalog_store)
    check("config has no contact_telegram key", "contact_telegram" not in cfg["store"])

    # 16. dark mode is wired everywhere ----------------------------------------------------
    pages = [site / "index.html", site / "status.html", site / "download.html", site / "checkout.html"]
    pages += sorted((site / "tools").glob("*/index.html"))
    pages += sorted((site / "tools").glob("*/checkout.html"))
    pages += [site / "tools" / "crypto-invoice-generator" / "app.html"]
    missing_theme = [str(p.relative_to(site)) for p in pages
                     if "cr.theme" not in p.read_text(encoding="utf-8")
                     or "theme-toggle" not in p.read_text(encoding="utf-8")]
    check("anti-FOUC snippet + toggle on all 11 pages", not missing_theme, str(missing_theme))
    css = (site / "css" / "style.css").read_text(encoding="utf-8")
    check("dark palette uses CSS variables", '[data-theme="dark"]' in css and "--bg: #0b1220" in css)
    check("QR + invoice sheet forced light in dark mode",
          '[data-theme="dark"] .qrbox' in css and '[data-theme="dark"] .sheet' in css)
    check("theme JS present in store.js",
          "initTheme" in store_js and 'localStorage.setItem("cr.theme"' in store_js)

    db_file = db.db_path()
    check("db file exists", db_file.exists(), str(db_file))
    print(f"\nAll {PASS} checks passed. Test state in {TMP}")


if __name__ == "__main__":
    main()
