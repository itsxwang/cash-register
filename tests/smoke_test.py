#!/usr/bin/env python3
"""Offline smoke test for the Cash Register payments module + storefront assets.

Run from the repo root:  python3 tests/smoke_test.py
No network required: FX and watchers fall back to config rates / graceful skip.
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

import payments as cr  # noqa: E402
from payments import db, manual  # noqa: E402

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

    # 1. config parsing -------------------------------------------------------
    check("config parses", isinstance(cfg.get("addresses"), dict))
    check("3 tools in config", len(cfg["tools"]) == 3)

    # 2. order creation -------------------------------------------------------
    order = cr.create_order("stablecoin-invoice-generator", 19.00)
    check("create_order returns unique id", order["order_id"].startswith("CR-"))
    check("memo == order id", order["memo"] == order["order_id"])
    check("USDT amount has per-order noise", order["amount"] >= 19.01)
    check("raw amount = amount * 1e6", order["raw_amount"] == round(order["amount"] * 1e6))
    check("order persisted in sqlite", cr.get_order(order["order_id"]) is not None)

    # 3. BTC + SOL orders (offline FX fallback -> config rates) ----------------
    btc_order = cr.create_order("cron-ping-monitor", 9.00, chain="btc")
    sol_order = cr.create_order("telegram-broadcaster", 15.00, chain="sol")
    check("btc amount has sats noise", btc_order["raw_amount"] % 100 != 0)
    check("sol amount has lamport noise", sol_order["raw_amount"] % 1000 != 0)

    # 4. payment URIs -----------------------------------------------------------
    uri_usdt = cr.build_payment_uri(order, cfg)
    check("EIP-681 uri for USDT", uri_usdt.startswith("ethereum:0x") and "@8453/transfer" in uri_usdt)
    check("BIP-21 uri for BTC", cr.build_payment_uri(btc_order, cfg).startswith("bitcoin:"))
    check("solana pay uri", cr.build_payment_uri(sol_order, cfg).startswith("solana:"))

    # 5. QR generation via vendored segno --------------------------------------
    paths = cr.write_order_assets(order, cfg=cfg, site_dir=TMP / "site")
    svg = (TMP / "site" / "data" / "qr" / f"{order['order_id']}.svg").read_text()
    check("segno produced QR svg", "<svg" in svg and len(svg) > 300)
    check("order json written", json.loads(paths[0].read_text())["order_id"] == order["order_id"])

    # 6. catalog sync ------------------------------------------------------------
    cat_path = cr.write_catalog(cfg=cfg, site_dir=TMP / "site")
    catalog = json.loads(cat_path.read_text())
    check("catalog has 3 tools", len(catalog["tools"]) == 3)
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
    check("paid order exposes download url", payload["download"]["url"].endswith(".zip"))
    check("awaiting order hides download url",
          json.loads((TMP / "site" / "data" / "orders" / f"{btc_order['order_id']}.json")
                     .read_text())["download"] is None)

    # 9. watchers degrade gracefully (unreachable endpoints) -----------------------
    bad_cfg = dict(cfg)
    bad_cfg["watchers"] = {
        "enabled": True, "auto_confirm": True, "lookback_hours": 72,
        "btc_api": "http://127.0.0.1:1", "sol_rpc": "http://127.0.0.1:1",
        "evm_api": "http://127.0.0.1:1",
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

    # 12. ingest buyer-reported order --------------------------------------------------
    ing = cr.ingest_order("CR-QQQQ1111", "cron-ping-monitor", cfg=cfg)
    check("ingest creates buyer-reported order", ing["order_id"] == "CR-QQQQ1111")

    db_file = db.db_path()
    check("db file exists", db_file.exists(), str(db_file))
    print(f"\nAll {PASS} checks passed. Test state in {TMP}")


if __name__ == "__main__":
    main()
