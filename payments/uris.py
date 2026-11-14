"""Standard payment URIs for the three supported chains.

- BTC:  BIP-21 `bitcoin:` URI (amount in BTC, label/message carry the memo)
- SOL:  Solana Pay `solana:` URI (amount in SOL, memo parameter)
- ETH:  EIP-681 native transfer `ethereum:<address>@<chainId>?value=<wei>`
        (no ERC-20 transfer params — the store only accepts the native asset)

Asset policy: no token-transfer URIs here. A freelancer who chooses to bill
in some other token does so in their own copy of the invoice tool — our
checkout and watchers only ever speak native BTC / ETH / SOL.
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

    if chain == "eth":
        if cfg is None:
            return None
        chain_id = get_path(cfg, "addresses.eth_chain_id", 8453)
        wei = order.get("raw_amount")
        if wei is None and amount is not None:   # legacy/derived orders
            wei = int(round(float(amount) * 10 ** 18))
        return f"ethereum:{address}@{chain_id}?value={wei}"
    return None
