"""QR code generation via the vendored segno library (no network, no pip install)."""
from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

import segno  # noqa: E402  (vendored: vendor/segno, BSD-3)


def svg_string(data: str, *, scale: int = 6, border: int = 2,
               dark: str = "#0f172a", light: str = "#ffffff") -> str:
    qr = segno.make(data, error="m")
    return qr.svg_outstring(scale=scale, border=border, dark=dark, light=light, xmldecl=False)


def save_svg(data: str, path: str | Path, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    qr = segno.make(data, error="m")
    qr.save(str(path), kind="svg", **kwargs)
    return path
