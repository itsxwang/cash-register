"""v0 confirmations: the founder checks the wallet and appends a row to a CSV.

Format (header required, extra columns ignored):

    order_id,txid,confirmed_at,source,note
    CR-AB12CD34,abc123...,2026-11-15T10:00:00Z,manual_wallet,great client

The default path is `payments/confirmations.csv` (gitignored); override with
the CASHREGISTER_CONFIRMATIONS env var.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = _PACKAGE_DIR / "confirmations.csv"

HEADER = ["order_id", "txid", "confirmed_at", "source", "note"]


def csv_path(override: str | os.PathLike | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("CASHREGISTER_CONFIRMATIONS")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_CSV_PATH


def ensure_template(path: str | os.PathLike | None = None) -> Path:
    """Create the CSV with just the header row if it does not exist yet."""
    p = csv_path(path)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(HEADER)
    return p


def read_confirmations(path: str | os.PathLike | None = None) -> list[dict]:
    """Return all confirmation rows as dicts. Missing file -> empty list."""
    p = csv_path(path)
    if not p.is_file():
        return []
    rows: list[dict] = []
    with open(p, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            clean = {k: (v or "").strip() for k, v in row.items() if k}
            oid = clean.get("order_id", "")
            if oid:
                rows.append(clean)
    return rows


def find_confirmation(order_id: str, path: str | os.PathLike | None = None) -> dict | None:
    oid = (order_id or "").strip().upper()
    for row in read_confirmations(path):
        if row.get("order_id", "").strip().upper() == oid:
            return row
    return None
