"""Cash Register — a generic crypto-checkout + delivery module.

Revenue arrives in decentralized, non-freezable assets only: native BTC /
ETH / SOL. No Stripe, no PayPal, no KYC, and no centralized stablecoins
(issuer-controlled tokens can be frozen — banned from our payment flow).
The module is deliberately generic so it can power any future digital product:

    from payments import create_order, check_paid, mark_paid, sync_static

    order = create_order("crypto-invoice-generator", 19.00)
    # ... customer pays order['amount'] to order['address'] with memo order['memo']
    order = check_paid(order["order_id"])          # CSV (v0) + on-chain (v1)
    mark_paid(order["order_id"], txid="...")       # or confirm manually
    sync_static()                                  # refresh the static storefront

v0 (always available):  the founder checks the wallet and appends a row to
                        payments/confirmations.csv.
v1 (assist mode):       keyless free-API watchers confirm exact-amount
                        payments on-chain. Unreachable APIs are skipped.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from . import amounts, db, ids, manual, watchers
from .config import DEFAULT_CONFIG_PATH, REPO_ROOT, get_path, load_config
from .qr import save_svg
from .uris import build_payment_uri

# Asset policy: decentralized, non-freezable assets only (native BTC/ETH/SOL).
# No centralized stablecoins (USDT/USDC/...) — issuer-controlled tokens can be
# frozen by a handful of keys and are deliberately unsupported here.
VALID_CHAINS = ("eth", "sol", "btc")


def _default_site_dir() -> Path:
    env = os.environ.get("CASHREGISTER_SITE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return REPO_ROOT / "site"


DEFAULT_SITE_DIR = _default_site_dir()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tool_cfg(cfg: dict, tool_id: str) -> dict:
    tools = get_path(cfg, "tools", {}) or {}
    if tool_id == "bundle":
        # The lifetime bundle is a first-class purchasable item: same order
        # flow, single combined release zip, all chains accepted.
        bundle = get_path(cfg, "bundle", {}) or {}
        return {
            "name": "Lifetime bundle — all tools",
            "blurb": bundle.get("note", ""),
            "price_usd": bundle.get("price_usd"),
            "chains": list(VALID_CHAINS),
            "default_chain": "eth",
            "release_file": bundle.get("release_file"),
            "landing": "/",
            "checkout": "/checkout.html?item=bundle",
        }
    if tool_id not in tools:
        raise ValueError(f"unknown tool '{tool_id}'. Known tools: "
                         f"{', '.join(sorted(list(tools) + ['bundle']))}")
    return tools[tool_id]


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------
def create_order(tool_id: str, price_usd: float | None = None, *,
                 chain: str | None = None, note: str | None = None,
                 cfg: dict | None = None, conn=None) -> dict:
    """Create a new order with a unique id, memo and exact crypto amount."""
    cfg = cfg or load_config()
    tool = _tool_cfg(cfg, tool_id)
    if price_usd is None:
        price_usd = float(tool.get("price_usd") or 0)
    if chain is None:
        chain = tool.get("default_chain") or "eth"
    if chain not in VALID_CHAINS:
        raise ValueError(f"unknown chain '{chain}'. Valid: {', '.join(VALID_CHAINS)}")

    own_conn = conn is None
    conn = conn or db.connect()
    try:
        seq = db.next_sequence(conn)
        amt = amounts.compute_amount(cfg, chain, float(price_usd), seq)
        # Collision guard: no two AWAITING orders may expect the same exact
        # amount on the same chain, or a buyer's payment could auto-confirm
        # the wrong order. Bump by one minimal step until unique.
        step = amounts.bump_step(cfg, chain)
        raw = amt["raw_amount"]
        bumps = 0
        while db.has_awaiting_amount(conn, chain, raw) and bumps < 100:
            raw += step
            bumps += 1
        amt["raw_amount"] = raw
        amt["amount"] = amounts.display_for(cfg, chain, raw)
        order_id = ids.new_order_id()
        order = {
            "order_id": order_id,
            "tool_id": tool_id,
            "price_usd": round(float(price_usd), 2),
            "chain": chain,
            "chain_name": amounts.chain_name(cfg, chain),
            "address": amounts.address_for(cfg, chain),
            "currency": amt["currency"],
            "amount": amt["amount"],
            "raw_amount": amt["raw_amount"],
            "memo": ids.memo_for(order_id),
            "status": "awaiting_payment",
            "created_at": _now(),
            "download_token": secrets.token_hex(16),
            "notes": note or "",
            "meta": {},
        }
        db.insert_order(conn, order)
    finally:
        if own_conn:
            conn.close()

    created = get_order(order_id, cfg=cfg)
    write_order_assets(created, cfg=cfg)
    return created


def ingest_order(order_id: str, tool_id: str, *, price_usd: float | None = None,
                 chain: str | None = None, cfg: dict | None = None) -> dict:
    """Register an order id that a buyer generated client-side (checkout page).

    If the order already exists it is returned untouched; otherwise it is
    created with the given id so `check_paid` / `sync` can track it.
    """
    order_id = ids.normalize_order_id(order_id)
    existing = get_order(order_id, cfg=cfg)
    if existing:
        return existing
    cfg = cfg or load_config()
    tool = _tool_cfg(cfg, tool_id)
    own_conn = None
    try:
        conn = own_conn = db.connect()
        seq = db.next_sequence(conn)
        price_usd = float(price_usd if price_usd is not None else tool.get("price_usd") or 0)
        chain = chain or tool.get("default_chain") or "eth"
        amt = amounts.compute_amount(cfg, chain, price_usd, seq)
        order = {
            "order_id": order_id,
            "tool_id": tool_id,
            "price_usd": round(price_usd, 2),
            "chain": chain,
            "chain_name": amounts.chain_name(cfg, chain),
            "address": amounts.address_for(cfg, chain),
            "currency": amt["currency"],
            "amount": amt["amount"],
            "raw_amount": amt["raw_amount"],
            "memo": ids.memo_for(order_id),
            "status": "awaiting_payment",
            "created_at": _now(),
            "download_token": secrets.token_hex(16),
            "notes": "ingested from buyer-reported checkout form",
            "meta": {},
        }
        db.insert_order(conn, order)
    finally:
        if own_conn is not None:
            own_conn.close()
    created = get_order(order_id, cfg=cfg)
    write_order_assets(created, cfg=cfg)
    return created


# ---------------------------------------------------------------------------
# Lookup / listing
# ---------------------------------------------------------------------------
def get_order(order_id: str, *, cfg: dict | None = None, conn=None) -> dict | None:
    order_id = ids.normalize_order_id(order_id)
    own = conn is None
    conn = conn or db.connect()
    try:
        return db.get_order(conn, order_id)
    finally:
        if own:
            conn.close()


def list_orders(*, status: str | None = None, tool_id: str | None = None,
                cfg: dict | None = None) -> list[dict]:
    conn = db.connect()
    try:
        return db.list_orders(conn, status=status, tool_id=tool_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Payment confirmation
# ---------------------------------------------------------------------------
def mark_paid(order_id: str, *, txid: str | None = None, source: str = "manual",
              paid_at: str | None = None, cfg: dict | None = None) -> dict:
    """Mark an order paid (used by the CSV path, the CLI, and the watchers)."""
    cfg = cfg or load_config()
    conn = db.connect()
    try:
        order = db.get_order(conn, ids.normalize_order_id(order_id))
        if order is None:
            raise KeyError(f"unknown order {order_id}")
        if order["status"] in ("paid", "delivered"):
            return order
        db.update_order(
            conn, order["order_id"],
            status="paid",
            paid_at=paid_at or _now(),
            paid_txid=txid or "",
            paid_source=source,
        )
        updated = db.get_order(conn, order["order_id"])
    finally:
        conn.close()
    write_order_assets(updated, cfg=cfg)
    return updated


def check_paid(order_id: str, *, use_watchers: bool = True,
               cfg: dict | None = None) -> dict:
    """Check one order: manual CSV first (v0), then on-chain watchers (v1).

    Never raises on network problems — a watcher that cannot reach its API is
    skipped and the note is stored in the order's meta.
    """
    cfg = cfg or load_config()
    order = get_order(order_id, cfg=cfg)
    if order is None:
        raise KeyError(f"unknown order {order_id}")
    if order["status"] in ("paid", "delivered"):
        return order

    # --- v0: manual CSV confirmations -------------------------------------
    row = manual.find_confirmation(order["order_id"])
    if row:
        return mark_paid(order["order_id"],
                         txid=row.get("txid") or None,
                         source=row.get("source") or "manual_csv",
                         paid_at=row.get("confirmed_at") or None,
                         cfg=cfg)

    # --- v1: on-chain watchers --------------------------------------------
    if use_watchers:
        result = watchers.run_watcher(order, cfg)
        if result is not None:
            if result.get("found") and result.get("confirmed") \
                    and get_path(cfg, "watchers.auto_confirm", True):
                return mark_paid(order["order_id"],
                                 txid=result.get("txid"),
                                 source=f"watcher_{order['chain']}",
                                 cfg=cfg)
            conn = db.connect()
            try:
                meta = dict(order.get("meta") or {})
                meta["watch"] = result
                db.update_order(conn, order["order_id"], meta=meta)
                order = db.get_order(conn, order["order_id"])
            finally:
                conn.close()

    return order


def check_all(*, use_watchers: bool = True, cfg: dict | None = None) -> list[dict]:
    """Run check_paid over every awaiting order (cron-friendly)."""
    cfg = cfg or load_config()
    out = []
    for order in list_orders(status="awaiting_payment", cfg=cfg):
        out.append(check_paid(order["order_id"], use_watchers=use_watchers, cfg=cfg))
    return out


def rotate_download_token(order_id: str, *, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    conn = db.connect()
    try:
        order = db.get_order(conn, ids.normalize_order_id(order_id))
        if order is None:
            raise KeyError(f"unknown order {order_id}")
        token = secrets.token_hex(16)
        db.update_order(conn, order["order_id"], download_token=token)
        updated = db.get_order(conn, order["order_id"])
    finally:
        conn.close()
    write_order_assets(updated, cfg=cfg)
    return updated


# ---------------------------------------------------------------------------
# Static storefront artifacts (JSON + QR) — no backend needed on the site
# ---------------------------------------------------------------------------
def _release_url(cfg: dict, release_file: str | None) -> str | None:
    """GitHub Releases asset URL.

    Convention (matches the founder's live releases): the release *tag* equals
    the asset file name minus extension, so the asset lives at
    <releases_base>/<tag>/<asset>. e.g.
      crypto-invoice-generator-v1.1.0.zip ->
      .../releases/download/crypto-invoice-generator-v1.1.0/crypto-invoice-generator-v1.1.0.zip
    """
    if not release_file:
        return None
    base = str(get_path(cfg, "delivery.releases_base", "")).rstrip("/")
    if not base:
        return None
    tag = release_file[:-4] if release_file.endswith(".zip") else release_file
    return f"{base}/{tag}/{release_file}"


def public_order(order: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    tool = _tool_cfg(cfg, order["tool_id"])
    paid = order["status"] in ("paid", "delivered")
    release_file = tool.get("release_file") or ""
    download_url = _release_url(cfg, release_file) if (paid and release_file) else None
    oid = order["order_id"]
    checkout_url = str(tool.get("checkout") or "")
    # bundle checkout already carries a query (?item=bundle) — join with &
    checkout_url += ("&" if "?" in checkout_url else "?") + f"order={oid}"
    return {
        "order_id": oid,
        "tool": {"id": order["tool_id"], "name": tool.get("name", order["tool_id"])},
        "chain": order["chain"],
        "chain_name": order.get("chain_name") or amounts.chain_name(cfg, order["chain"]),
        "address": order.get("address"),
        "currency": order.get("currency"),
        "amount": order.get("amount"),
        "raw_amount": order.get("raw_amount"),
        "payment_uri": build_payment_uri(order, cfg),
        "memo": order.get("memo") or oid,
        "price_usd": order.get("price_usd"),
        "status": order["status"],
        "created_at": order.get("created_at"),
        "paid_at": order.get("paid_at"),
        "checkout_url": checkout_url,
        "status_url": f"/status.html?order={oid}",
        "qr": f"/data/qr/{oid}.svg",
        "download": ({"url": download_url, "token": order.get("download_token")}
                     if paid and download_url else None),
        "watch_note": ((order.get("meta") or {}).get("watch", {}) or {}).get("note"),
    }


def write_order_assets(order: dict, *, cfg: dict | None = None,
                       site_dir: str | Path | None = None) -> list[Path]:
    """Write the public order JSON + QR SVG into the static site tree."""
    cfg = cfg or load_config()
    site = Path(site_dir) if site_dir else DEFAULT_SITE_DIR
    payload = public_order(order, cfg)
    oid = order["order_id"]

    json_path = site / "data" / "orders" / f"{oid}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    qr_rel = f"data/qr/{oid}.svg"
    qr_path = site / qr_rel
    save_svg(payload.get("payment_uri") or payload.get("address") or oid,
             qr_path, scale=6, border=2, dark="#0f172a", light="#ffffff")
    return [json_path, qr_path]


def write_catalog(*, cfg: dict | None = None, site_dir: str | Path | None = None,
                  refresh_fx: bool = False) -> Path:
    """Generate the public catalog the static storefront JS consumes."""
    cfg = cfg or load_config()
    site = Path(site_dir) if site_dir else DEFAULT_SITE_DIR
    fx_rates = {}
    if refresh_fx:
        from . import fx as fx_mod
        fx_rates = fx_mod.rates(cfg)

    tools_pub = {}
    for tid, tool in (get_path(cfg, "tools", {}) or {}).items():
        tools_pub[tid] = {
            "name": tool.get("name", tid),
            "blurb": tool.get("blurb", ""),
            "price_usd": tool.get("price_usd"),
            "chains": tool.get("chains", list(VALID_CHAINS)),
            "landing": tool.get("landing"),
            "checkout": tool.get("checkout"),
        }

    chain_id = get_path(cfg, "addresses.eth_chain_id", 8453)
    catalog = {
        "store": {
            "name": get_path(cfg, "store.name", "Micro Tools"),
            "tagline": get_path(cfg, "store.tagline", ""),
            "url": get_path(cfg, "store.url", ""),
            "contact_email": get_path(cfg, "store.contact_email", ""),
        },
        "chains": {
            "eth": {
                "label": f"ETH ({get_path(cfg, 'addresses.eth_chain_name', 'Base')})",
                "address": get_path(cfg, "addresses.eth"),
                "chain_id": chain_id,
                "chain_name": get_path(cfg, "addresses.eth_chain_name", "Base"),
                "decimals": 18,
                "asset_policy": "native ETH only — no tokens",
            },
            "sol": {"label": "SOL", "address": get_path(cfg, "addresses.sol"), "decimals": 9},
            "btc": {"label": "BTC", "address": get_path(cfg, "addresses.btc"), "decimals": 8},
        },
        "fx": fx_rates or None,
        "tools": tools_pub,
        "bundle": {
            "price_usd": get_path(cfg, "bundle.price_usd"),
            "note": get_path(cfg, "bundle.note", ""),
            "checkout": "/checkout.html?item=bundle",
            "release_file": get_path(cfg, "bundle.release_file", ""),
        },
        "manual_confirm_note":
            "Payments are confirmed by the founder (manual CSV, assisted by "
            "on-chain watchers). Allow a few minutes after paying.",
        "generated_at": _now(),
    }
    path = site / "data" / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return path


def sync_static(*, cfg: dict | None = None, site_dir: str | Path | None = None,
                refresh_fx: bool = False) -> list[Path]:
    """Regenerate catalog.json + every order JSON + QR SVGs."""
    cfg = cfg or load_config()
    written = [write_catalog(cfg=cfg, site_dir=site_dir, refresh_fx=refresh_fx)]
    for order in list_orders(cfg=cfg):
        written.extend(write_order_assets(order, cfg=cfg, site_dir=site_dir))
    return written


# ---------------------------------------------------------------------------
# Demo fixtures — make `python3 -m http.server` demo work out of the box
# ---------------------------------------------------------------------------
def create_demo_fixtures(*, cfg: dict | None = None,
                         site_dir: str | Path | None = None) -> list[dict]:
    """Create DEMO-0001 (paid) and DEMO-0002 (awaiting) for local demos."""
    cfg = cfg or load_config()
    site = Path(site_dir) if site_dir else DEFAULT_SITE_DIR
    made = []
    specs = [
        ("DEMO-0001", "crypto-invoice-generator", "eth", "paid"),
        ("DEMO-0002", "cron-ping-monitor", "sol", "awaiting_payment"),
    ]
    conn = db.connect()
    try:
        for oid, tool_id, chain, status in specs:
            tool = _tool_cfg(cfg, tool_id)
            price = float(tool.get("price_usd") or 0)
            seq = db.next_sequence(conn)
            amt = amounts.compute_amount(cfg, chain, price, seq)
            order = {
                "order_id": oid,
                "tool_id": tool_id,
                "price_usd": round(price, 2),
                "chain": chain,
                "chain_name": amounts.chain_name(cfg, chain),
                "address": amounts.address_for(cfg, chain),
                "currency": amt["currency"],
                "amount": amt["amount"],
                "raw_amount": amt["raw_amount"],
                "memo": oid,
                "status": status,
                "created_at": _now(),
                "download_token": secrets.token_hex(16) if status == "paid" else None,
                "notes": "demo fixture (safe to delete)",
                "meta": {},
            }
            if status == "paid":
                order["paid_at"] = _now()
                order["paid_source"] = "manual_csv"
            if db.get_order(conn, oid) is None:
                db.insert_order(conn, order)
            made.append(db.get_order(conn, oid))
    finally:
        conn.close()
    for order in made:
        write_order_assets(order, cfg=cfg, site_dir=site)
    write_catalog(cfg=cfg, site_dir=site)
    return made
