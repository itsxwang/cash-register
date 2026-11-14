# Vendored dependencies

Everything here is committed so the project runs with **zero pip installs**
(only `requests` is listed in requirements.txt, and even that is optional —
stdlib `urllib` is the fallback).

## vendor/segno — QR code generator (Python)

- Source: https://github.com/heuer/segno (imported at tag master, Nov 2026)
- License: BSD-3-Clause (see `segno/LICENSE`)
- Used by: `payments/qr.py` — generates the SVG QR codes for orders and
  invoices at order-creation time. Pure Python, no network needed.

## vendor/js/qrcode.js — QR code generator (JavaScript)

- Source: https://github.com/kazuhikoarase/qrcode-generator v1.4.4
  (via unpkg, file `qrcode.js`)
- License: MIT
- Used by: `site/js/qr.js` (copy) — client-side QR rendering on the checkout
  pages and inside the Stablecoin Invoice Generator, so buyers/invoicers can
  scan payment URIs without any server-side call.

Keep both pinned; update only after running `python3 tests/smoke_test.py`.
