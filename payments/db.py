"""SQLite persistence for orders."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = _PACKAGE_DIR / "data" / "cashregister.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    tool_id         TEXT NOT NULL,
    price_usd       REAL NOT NULL,
    chain           TEXT NOT NULL,
    chain_name      TEXT,
    address         TEXT NOT NULL,
    currency        TEXT,
    amount          REAL,
    raw_amount      INTEGER,
    memo            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'awaiting_payment',
    created_at      TEXT NOT NULL,
    paid_at         TEXT,
    paid_txid       TEXT,
    paid_source     TEXT,
    delivered_at    TEXT,
    download_token  TEXT,
    notes           TEXT,
    meta            TEXT
);
"""

STATUSES = ("awaiting_payment", "paid", "delivered", "expired")


def db_path(override: str | os.PathLike | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("CASHREGISTER_DB")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DB_PATH


def connect(override: str | os.PathLike | None = None) -> sqlite3.Connection:
    path = db_path(override)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def row_to_order(row: sqlite3.Row) -> dict:
    order = dict(row)
    meta = order.pop("meta", None)
    order["meta"] = json.loads(meta) if meta else {}
    return order


def insert_order(conn: sqlite3.Connection, order: dict) -> None:
    order = dict(order)
    meta = order.pop("meta", {})
    order["meta"] = json.dumps(meta)
    cols = ", ".join(order.keys())
    marks = ", ".join("?" for _ in order)
    conn.execute(f"INSERT INTO orders ({cols}) VALUES ({marks})", list(order.values()))
    conn.commit()


def update_order(conn: sqlite3.Connection, order_id: str, **fields) -> None:
    if "meta" in fields and not isinstance(fields["meta"], str):
        fields["meta"] = json.dumps(fields["meta"])
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE orders SET {sets} WHERE order_id = ?", [*fields.values(), order_id])
    conn.commit()


def get_order(conn: sqlite3.Connection, order_id: str) -> dict | None:
    cur = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id.strip().upper(),))
    row = cur.fetchone()
    return row_to_order(row) if row else None


def list_orders(conn: sqlite3.Connection, status: str | None = None,
                tool_id: str | None = None) -> list[dict]:
    q = "SELECT * FROM orders"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if tool_id:
        clauses.append("tool_id = ?")
        params.append(tool_id)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY created_at DESC"
    return [row_to_order(r) for r in conn.execute(q, params)]


def next_sequence(conn: sqlite3.Connection) -> int:
    """Row count used for the per-order amount-noise suffix (amount uniqueness)."""
    return (conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] or 0) + 1
