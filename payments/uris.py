"""Standard payment URIs for the three supported chains.

- BTC:   BIP-21 `bitcoin:` URI (amount in BTC, label/message carry the memo)
- SOL:   Solana Pay `solana:` URI (amount in SOL, memo parameter)
- EVM:   EIP-681 `ethereum:<token>@<chainId>/transfer?...` for USDT on an L2
         (works with MetaMask & most wallet QR scanners)
"""
from __future__ import annotations

from urllib.parse import quote

from .config import get_path


def _q(value) -> str:
    return quote(str(value), safe="")


def build_payment_uri(order: dict, cfg: dict | None = None) -> str | None:
    chain = order.get("chain")
    address = order.get("address") or ""
    amount = order.get("amount")
    memo = order.get("memo") or ""

    if chain == "btc":
        return (f"bitcoin:{address}"
                f"?amount={amount:.8f}&label={_q(memo)}&message={_q(memo)}")

    if chain == "sol":
        return f"solana:{address}?amount={amount}&memo={_q(memo)}"

    if chain == "usdt_evm":
        if cfg is None:
            return None
        chain_id = get_path(cfg, "addresses.usdt_chain_id", 8453)
        token = get_path(cfg, "addresses.usdt_contract", "")
        units = order.get("raw_amount") or int(round(float(amount or 0) * 1e6))
        return (f"ethereum:{token}@{chain_id}/transfer"
                f"?address={address}&uint256={units}")
    return None
