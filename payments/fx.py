"""USD -> crypto conversion with a keyless free-API attempt + config fallback.

Demo mode needs no network: when the price endpoints are unreachable we fall
back to the manual rates in config.yaml (fx.usd_btc / fx.usd_sol).
"""
from __future__ import annotations

import time

from .config import get_path
from .http import http_get_json

_CACHE: dict = {}
_CACHE_TTL = 60.0


def _cached(key, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _btc_per_usd(cfg: dict) -> float | None:
    endpoint = get_path(cfg, "fx.btc_price_endpoint", "https://mempool.space/api/v1/prices")
    ok, data = http_get_json(endpoint, timeout=6)
    if ok and isinstance(data, dict) and data.get("USD"):
        try:
            return 1.0 / float(data["USD"])
        except (TypeError, ValueError):
            return None
    return None


def _sol_per_usd(cfg: dict) -> float | None:
    endpoint = get_path(cfg, "fx.sol_price_endpoint",
                        "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")
    ok, data = http_get_json(endpoint, timeout=6)
    if ok and isinstance(data, dict):
        usd = (data.get("solana") or {}).get("usd")
        if usd:
            return 1.0 / float(usd)
    return None


def rates(cfg: dict) -> dict:
    """Return {'usd_btc': x, 'usd_sol': y, 'source': 'live'|'config', 'updated_at': iso}."""

    def compute():
        btc = _btc_per_usd(cfg)
        sol = _sol_per_usd(cfg)
        fallback_btc = float(get_path(cfg, "fx.usd_btc", 0.0))
        fallback_sol = float(get_path(cfg, "fx.usd_sol", 0.0))
        source = "live" if (btc or sol) else "config"
        return {
            "usd_btc": btc if btc and btc > 0 else fallback_btc,
            "usd_sol": sol if sol and sol > 0 else fallback_sol,
            "source": source,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    return _cached("rates", compute)
