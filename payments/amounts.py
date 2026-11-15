"""Exact crypto amounts for an order.

Each order gets a tiny deterministic "noise" suffix derived from its sequence
number so two orders rarely demand the same amount on the same chain — that
makes amount-based matching reliable even on chains without memos (BTC, ETH).

Wei policy (18-decimal asset): **integer math only**. Base conversion goes
through Decimal, the stored truth is `raw_amount` (int wei), and both the
base amount and the noise live in clean steps of 0.00001 ETH (10**13 wei)
so on-chain exact matching still works and displayed amounts stay readable.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from . import fx
from .config import get_path

DECIMALS = {"eth": 18, "btc": 8, "sol": 9}

# 0.00001 ETH — the clean step for base amounts AND per-order noise.
ETH_STEP_WEI = 10 ** 13


def compute_amount(cfg: dict, chain: str, price_usd: float, seq: int) -> dict:
    """Return {'amount': display amount (float), 'raw_amount': int units, 'currency': str}."""
    price = Decimal(str(price_usd))
    if price <= 0:
        raise ValueError("price_usd must be positive")

    if chain == "eth":
        rate = Decimal(str(fx.rates(cfg)["usd_eth"]))
        step = Decimal(ETH_STEP_WEI)
        wei_total = Decimal(10) ** 18
        base_steps = int(((price * rate * wei_total) / step)
                         .to_integral_value(rounding=ROUND_HALF_UP))
        noise_steps = ((seq - 1) % 9) + 1           # 1..9 steps — NEVER zero
        wei = int((base_steps + noise_steps) * step)  # exact integer wei, no floats
        display = (Decimal(wei) / wei_total).quantize(Decimal("0.00001"),
                                                      rounding=ROUND_HALF_UP)
        return {"amount": float(display), "raw_amount": wei, "currency": "ETH"}

    if chain == "btc":
        rate = Decimal(str(fx.rates(cfg)["usd_btc"]))
        sats = int(((price * rate * Decimal(10) ** 8)
                    .to_integral_value(rounding=ROUND_HALF_UP))) + (seq % 40) + 1
        return {"amount": sats / 1e8, "raw_amount": sats, "currency": "BTC"}

    if chain == "sol":
        rate = Decimal(str(fx.rates(cfg)["usd_sol"]))
        lamports = int(((price * rate * Decimal(10) ** 9)
                        .to_integral_value(rounding=ROUND_HALF_UP))) + (seq % 100) + 1
        return {"amount": lamports / 1e9, "raw_amount": lamports, "currency": "SOL"}

    raise ValueError(f"unknown chain: {chain}")


def display_for(cfg: dict, chain: str, raw: int) -> float:
    """Exact display amount for a given raw unit amount (post-bump)."""
    if chain == "eth":
        d = (Decimal(raw) / (Decimal(10) ** 18)).quantize(
            Decimal("0.00001"), rounding=ROUND_HALF_UP)
        return float(d)
    if chain == "btc":
        return raw / 1e8
    if chain == "sol":
        return raw / 1e9
    raise ValueError(f"unknown chain: {chain}")


def bump_step(cfg: dict, chain: str) -> int:
    """Smallest raw-unit increment that keeps the amount pay-exact."""
    if chain == "eth":
        return ETH_STEP_WEI
    return 1  # BTC sats / SOL lamports


def chain_name(cfg: dict, chain: str) -> str:
    if chain == "eth":
        return str(get_path(cfg, "addresses.eth_chain_name", "Base"))
    return {"btc": "Bitcoin", "sol": "Solana"}.get(chain, chain)


def currency_for(chain: str) -> str:
    return {"eth": "ETH", "btc": "BTC", "sol": "SOL"}[chain]


def address_for(cfg: dict, chain: str) -> str:
    key = {"eth": "addresses.eth", "btc": "addresses.btc", "sol": "addresses.sol"}[chain]
    addr = get_path(cfg, key)
    if not addr or "PLACEHOLDER" in str(addr).upper():
        # Still returns the placeholder: the module must work in demo mode.
        pass
    return str(addr)
