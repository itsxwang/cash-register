"""v1 on-chain payment watchers — keyless free APIs, graceful degradation.

- BTC:  mempool.space REST (no key)
- SOL:  public Solana RPC `getSignaturesForAddress` + `getTransaction`
- EVM:  Etherscan v2 multichain free tier (key via ETHERSCAN_API_KEY env var;
        if the env var is absent the EVM chain is skipped, never crashes)

Matching strategy per order:
1. amount: the exact raw amount (sats / lamports / USDT units) carries a
   deterministic per-order noise suffix (see amounts.py), so an exact match
   within the lookback window is treated as the payment.
2. memo:   where the chain supports one (BTC OP_RETURN, Solana Memo program)
   a memo equal to the order id also confirms the match.

Every watcher returns a result dict and NEVER raises. Unreachable APIs or
rate limits produce found=False plus a human-readable note.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from .config import get_path
from .http import http_get_json, http_post_json

ZERO = {"found": False, "confirmed": False, "txid": None, "note": "", "checked": 0}


def _result(**kw) -> dict:
    out = dict(ZERO)
    out.update(kw)
    return out


def _order_created_ts(order: dict) -> float:
    raw = order.get("created_at") or ""
    try:
        return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# BTC — mempool.space
# ---------------------------------------------------------------------------
def watch_btc(order: dict, cfg: dict) -> dict:
    base = get_path(cfg, "watchers.btc_api", "https://mempool.space").rstrip("/")
    addr = order.get("address") or ""
    raw_amount = int(order.get("raw_amount") or 0)
    memo = order.get("memo") or ""
    created_ts = _order_created_ts(order)

    ok, txs = http_get_json(f"{base}/api/address/{addr}/txs", timeout=10)
    if not ok:
        return _result(note=f"mempool.space unreachable: {txs.get('error', '?')}")

    try:
        txs = list(txs)
    except TypeError:
        return _result(note="mempool.space returned unexpected payload")

    checked = 0
    for tx in txs:
        status = tx.get("status") or {}
        block_time = status.get("block_time") or 0
        if created_ts and block_time and block_time < created_ts - 3600:
            continue
        checked += 1
        memo_ok = any(
            (v.get("scriptpubkey_type") == "op_return")
            and memo.lower() in (v.get("scriptpubkey_asnsm", "") or "")
            for v in tx.get("vout", [])
        ) or _memo_in_raw(tx, memo)
        for vout in tx.get("vout", []):
            if vout.get("scriptpubkey_address") != addr:
                continue
            value = int(vout.get("value") or 0)
            if value == raw_amount or (memo_ok and value >= raw_amount):
                confirmed = bool(status.get("confirmed"))
                return _result(
                    found=True, confirmed=confirmed,
                    txid=tx.get("txid"),
                    note="exact amount" + (" + OP_RETURN memo" if memo_ok else ""),
                    checked=checked,
                )
    return _result(note=f"no matching tx in last {checked} btc txs", checked=checked)


# ---------------------------------------------------------------------------
# SOL — public RPC
# ---------------------------------------------------------------------------
def watch_sol(order: dict, cfg: dict) -> dict:
    rpc = get_path(cfg, "watchers.sol_rpc", "https://api.mainnet-beta.solana.com").rstrip("/")
    addr = order.get("address") or ""
    raw_amount = int(order.get("raw_amount") or 0)
    usdt_mint = get_path(cfg, "watchers.sol_usdt_mint", "")
    memo = order.get("memo") or ""
    created_ts = _order_created_ts(order)

    def rpc_call(method, params):
        return http_post_json(rpc, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                              timeout=12)

    ok, resp = rpc_call("getSignaturesForAddress", [addr, {"limit": 25}])
    if not ok:
        return _result(note=f"solana rpc unreachable: {resp.get('error', '?')}")
    sigs = (resp.get("result") or []) if isinstance(resp, dict) else []

    checked = 0
    for sig_info in sigs[:12]:  # stay polite on the public RPC
        block_time = sig_info.get("blockTime") or 0
        if created_ts and block_time and block_time < created_ts - 3600:
            continue
        checked += 1
        ok, resp = rpc_call("getTransaction", [
            sig_info.get("signature"),
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
        ])
        if not ok or not isinstance(resp, dict) or not resp.get("result"):
            continue
        tx = resp["result"]
        meta = tx.get("meta") or {}

        # (a) SPL token balance delta credited to our receiving wallet
        for bal in meta.get("postTokenBalances") or []:
            if not isinstance(bal, dict):
                continue
            if addr and bal.get("owner") != addr:
                continue
            if usdt_mint and bal.get("mint") != usdt_mint:
                continue
            post_raw = int((bal.get("uiTokenAmount") or {}).get("amount") or 0)
            pre_raw = 0
            for pre in meta.get("preTokenBalances") or []:
                if pre.get("accountIndex") == bal.get("accountIndex"):
                    pre_raw = int((pre.get("uiTokenAmount") or {}).get("amount") or 0)
            if post_raw - pre_raw == raw_amount:
                confirmed = sig_info.get("confirmationStatus") in ("finalized", "confirmed")
                return _result(found=True, confirmed=bool(confirmed),
                               txid=sig_info.get("signature"),
                               note="USDT balance delta matches", checked=checked)

        # (b) native SOL transfer delta
        keys = [k.get("pubkey") for k in (tx.get("transaction", {}).get("message", {})
                                          .get("accountKeys") or [])]
        pre = meta.get("preBalances") or []
        post = meta.get("postBalances") or []
        for i, key in enumerate(keys):
            if key == addr and i < len(pre) and i < len(post):
                if post[i] - pre[i] == raw_amount:
                    confirmed = sig_info.get("confirmationStatus") in ("finalized", "confirmed")
                    return _result(found=True, confirmed=bool(confirmed),
                                   txid=sig_info.get("signature"),
                                   note="SOL balance delta matches", checked=checked)

        # (c) memo-only fallback (memo present + transfer to us happened above;
        #     here we merely record that the memo was seen)
        if memo and _memo_in_raw(tx, memo):
            note = f"memo {memo} seen in tx (amount not auto-matched)"
            return _result(found=False, note=note, checked=checked)

    return _result(note=f"no matching tx in last {checked} sol sigs", checked=checked)


# ---------------------------------------------------------------------------
# EVM — Etherscan v2 multichain (free tier, key from env)
# ---------------------------------------------------------------------------
def watch_evm(order: dict, cfg: dict) -> dict:
    api_key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    if not api_key:
        return _result(note="ETHERSCAN_API_KEY not set — EVM watcher skipped "
                            "(manual CSV confirmations still work)")
    api = get_path(cfg, "watchers.evm_api", "https://api.etherscan.io/v2/api")
    chain_id = get_path(cfg, "addresses.usdt_chain_id", 8453)
    contract = str(get_path(cfg, "addresses.usdt_contract", ""))
    addr = (order.get("address") or "").lower()
    raw_amount = int(order.get("raw_amount") or 0)
    created_ts = _order_created_ts(order)

    params = {
        "chainid": chain_id, "module": "account", "action": "tokentx",
        "contractaddress": contract, "address": order.get("address"),
        "page": 1, "offset": 50, "sort": "desc", "apikey": api_key,
    }
    import urllib.parse
    url = api + "?" + urllib.parse.urlencode(params)
    ok, data = http_get_json(url, timeout=12)
    if not ok:
        return _result(note=f"etherscan unreachable: {data.get('error', '?')}")
    if isinstance(data, dict) and str(data.get("status")) != "1":
        return _result(note=f"etherscan api: {data.get('message', '?')} "
                            f"{data.get('result', '') if isinstance(data.get('result'), str) else ''}")

    txs = data.get("result") or []
    checked = 0
    for t in txs:
        if not isinstance(t, dict):
            continue
        if (t.get("to") or "").lower() != addr:
            continue
        if (t.get("contractAddress") or "").lower() != contract.lower():
            continue
        ts = int(t.get("timeStamp") or 0)
        if created_ts and ts < created_ts - 3600:
            continue
        checked += 1
        if int(t.get("value") or 0) == raw_amount:
            return _result(found=True, confirmed=True,
                           txid=t.get("hash"), note="exact USDT amount", checked=checked)
    return _result(note=f"no matching tx in last {checked} USDT transfers", checked=checked)


def _memo_in_raw(obj, memo: str) -> bool:
    try:
        return memo in json.dumps(obj)
    except (TypeError, ValueError):
        return False


WATCHERS = {"btc": watch_btc, "sol": watch_sol, "usdt_evm": watch_evm}


def run_watcher(order: dict, cfg: dict) -> dict | None:
    """Dispatch to the watcher for the order's chain. None if disabled/unknown."""
    if not get_path(cfg, "watchers.enabled", True):
        return None
    fn = WATCHERS.get(order.get("chain"))
    if fn is None:
        return _result(note=f"no watcher for chain {order.get('chain')}")
    try:
        return fn(order, cfg)
    except Exception as exc:  # noqa: BLE001 - watchers must never crash the app
        return _result(note=f"{order.get('chain')} watcher error: {type(exc).__name__}: {exc}")


def probe(cfg: dict) -> dict:
    """Cheap reachability probe for each chain API (used by `payments doctor`)."""
    out = {}
    ok, _ = http_get_json(get_path(cfg, "watchers.btc_api", "https://mempool.space") + "/api/blocks/tip/height",
                          timeout=6)
    out["btc_mempool_space"] = bool(ok)

    ok, resp = http_post_json(get_path(cfg, "watchers.sol_rpc", "https://api.mainnet-beta.solana.com"),
                              {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}, timeout=6)
    out["sol_public_rpc"] = bool(ok and isinstance(resp, dict) and resp.get("result") == "ok")

    out["evm_etherscan"] = bool(os.environ.get("ETHERSCAN_API_KEY", "").strip())
    return out
