"""Tiny HTTP helper for the payments module.

Uses `requests` when installed (see requirements.txt) and falls back to the
Python standard library `urllib` otherwise, so the module also runs with zero
installed dependencies.

Every function returns `(ok, data)` and NEVER raises on network errors —
callers (the chain watchers) must degrade gracefully when an API is
unreachable.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

try:  # optional, nicer than urllib
    import requests  # type: ignore
except Exception:  # pragma: no cover - fallback path
    requests = None

DEFAULT_TIMEOUT = 10


def http_json(method: str, url: str, *, payload=None, headers=None,
              timeout: float = DEFAULT_TIMEOUT):
    """Return (ok, parsed_json). ok=False -> {'error': '...'} payload."""
    headers = dict(headers or {})
    # Some free APIs (e.g. Blockscout) 403 default bot user-agents; identify
    # as a normal browser client on both HTTP backends.
    headers.setdefault(
        "User-Agent", "Mozilla/5.0 (X11; Linux x86_64) CashRegister/1.1")
    try:
        if requests is not None:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=timeout)
            else:
                resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            body = resp.text
            status = resp.status_code
        else:
            req = urllib.request.Request(url, method=method)
            for k, v in headers.items():
                req.add_header(k, v)
            data = None
            if method != "GET":
                data = json.dumps(payload).encode("utf-8")
                req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
                status = r.status
                body = r.read().decode("utf-8", "replace")
        if status >= 400:
            return False, {"error": f"HTTP {status}"}
        return True, json.loads(body)
    except Exception as exc:  # noqa: BLE001 - graceful by design
        return False, {"error": f"{type(exc).__name__}: {exc}"}


def http_get_json(url: str, *, headers=None, timeout: float = DEFAULT_TIMEOUT):
    return http_json("GET", url, headers=headers, timeout=timeout)


def http_post_json(url: str, payload, *, headers=None, timeout: float = DEFAULT_TIMEOUT):
    return http_json("POST", url, payload=payload, headers=headers, timeout=timeout)
