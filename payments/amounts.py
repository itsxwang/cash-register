"""Exact crypto amounts for an order.

Each order gets a tiny deterministic "noise" suffix derived from its sequence
number so two orders rarely demand the same amount on the same chain — that
makes amount-based matching reliable even on chains without memos (BTC, EVM).
"""
from __future__ import annotations

from . import fx
from .config import get_path

DECIMALS = {"usdt_evm": 6, "btc": 8, "sol": 9}


def compute_amount(cfg: dict, chain: str, price_usd: float, seq: int) -> dict:
    """Return {'amount': human crypto amount, 'raw_amount': int units, 'currency': str}."""
    if price_usd <= 0:
        raise ValueError("price_usd must be positive")

    if chain == "usdt_evm":
        amount = round(float(price_usd) + (seq % 100) / 100.0, 2)
        raw = int(round(amount * (10 ** DECIMALS[chain])))
        return {"amount": amount, "raw_amount": raw, "currency": "USDT"}

    if chain == "btc":
        rate = fx.rates(cfg)["usd_btc"]
        sats = int(round(float(price_usd) * rate * 1e8)) + (seq % 40) + 1
        return {"amount": sats / 1e8, "raw_amount": sats, "currency": "BTC"}

    if chain == "sol":
        rate = fx.rates(cfg)["usd_sol"]
        lamports = int(round(float(price_usd) * rate * 1e9)) + (seq % 100) + 1
        return {"amount": lamports / 1e9, "raw_amount": lamports, "currency": "SOL"}

    raise ValueError(f"unknown chain: {chain}")


def chain_name(cfg: dict, chain: str) -> str:
    if chain == "usdt_evm":
        return str(get_path(cfg, "addresses.usdt_chain_name", "Base"))
    return {"btc": "Bitcoin", "sol": "Solana"}.get(chain, chain)


def currency_for(chain: str) -> str:
    return {"usdt_evm": "USDT", "btc": "BTC", "sol": "SOL"}[chain]


def address_for(cfg: dict, chain: str) -> str:
    key = {"usdt_evm": "addresses.usdt_evm", "btc": "addresses.btc", "sol": "addresses.sol"}[chain]
    addr = get_path(cfg, key)
    if not addr or "PLACEHOLDER" in str(addr).upper():
        # Still returns the placeholder: the module must work in demo mode.
        pass
    return str(addr)
