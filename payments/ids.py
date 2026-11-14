"""Order ID + memo helpers."""
from __future__ import annotations

import secrets

# Unambiguous alphabet (no 0/O/1/I) so buyers can read IDs off a QR or chat message.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PREFIX = "CR"


def new_order_id() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{PREFIX}-{body}"


def normalize_order_id(raw: str) -> str:
    return (raw or "").strip().upper()


def memo_for(order_id: str) -> str:
    """The payment memo is the order id itself: short, unique, human-typeable."""
    return order_id
