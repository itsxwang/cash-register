#!/usr/bin/env python3
"""Cron Ping Monitor — a tiny cron-friendly uptime pinger with a static status page.

One file, Python stdlib only, no dependencies. Designed to be called once per
cron tick; each run pings every monitor, appends to history, regenerates the
status page, and (optionally) pings Telegram on up<->down transitions.

Quick start:
    python3 cron_ping.py                          # one sweep with monitors.json
    python3 cron_ping.py --out data               # write status files to ./data
    python3 cron_ping.py --serve 8080             # serve the status page locally
Cron:
    * * * * * cd /path/to/monitors && python3 cron_ping.py >> cron.log 2>&1
Telegram alerts:
    export TELEGRAM_BOT_TOKEN=123456:ABC...
    export TELEGRAM_CHAT_ID=123456789
    python3 cron_ping.py --notify-telegram

Exit codes: 0 = all up, 1 = any monitor down, 2 = setup error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "cron-ping-monitor/1.0"
HISTORY_KEEP = 4000


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_monitors(path: Path) -> list[dict]:
    if not path.is_file():
        print(f"error: monitors file not found: {path}\n"
              f"Copy monitors.example.json to monitors.json and edit it.", file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {path} is not valid JSON (line {exc.lineno}: {exc.msg})", file=sys.stderr)
        sys.exit(2)
    if isinstance(data, dict):
        data = data.get("monitors", [])
    out = []
    for i, m in enumerate(data):
        if not m.get("url"):
            continue
        out.append({
            "name": m.get("name") or f"monitor-{i + 1}",
            "url": m["url"],
            "expect_status": int(m.get("expect_status") or 200),
            "expect_text": m.get("expect_text"),
        })
    if not out:
        print("error: no monitors configured", file=sys.stderr)
        sys.exit(2)
    return out


def check(m: dict, timeout: float = 10.0) -> dict:
    started = time.time()
    result = {"name": m["name"], "url": m["url"], "ok": False,
              "status": None, "latency_ms": None, "error": None}
    try:
        req = urllib.request.Request(m["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536).decode("utf-8", "replace")
            result["status"] = resp.status
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        body = ""
    except Exception as exc:  # noqa: BLE001 — a monitor failing must never crash the run
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["latency_ms"] = int((time.time() - started) * 1000)
        return result

    result["latency_ms"] = int((time.time() - started) * 1000)
    if result["status"] != m["expect_status"]:
        result["error"] = f"expected HTTP {m['expect_status']}, got {result['status']}"
        return result
    if m["expect_text"] and m["expect_text"] not in body:
        result["error"] = f"'{m['expect_text']}' not found in response"
        return result
    result["ok"] = True
    return result


def load_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    # trim
    if len(out) > HISTORY_KEEP:
        keep = out[-int(HISTORY_KEEP * 0.8):]
        path.write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8")
        out = keep
    return out


def load_state(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def notify_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# status page
# ---------------------------------------------------------------------------
STATUS_CSS = """
:root{--bg:#0b1220;--surface:#111a2e;--ink:#e2e8f0;--muted:#7d8db1;--line:#1e2a44;
      --good:#10b981;--bad:#ef4444;--warn:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:1.6rem;margin:0 0 4px}
.updated{color:var(--muted);font-size:.9rem;margin:0 0 28px}
.grid{display:grid;gap:14px}
.m{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.m .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.m h2{font-size:1.05rem;margin:0}
.m .url{color:var(--muted);font-size:.85rem;font-family:ui-monospace,Menlo,Consolas,monospace;
        word-break:break-all}
.pill{padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:700}
.pill.up{background:#06281f;color:var(--good)}
.pill.down{background:#2b1113;color:var(--bad)}
.pill.unknown{background:#1e2a44;color:var(--muted)}
.stats{display:flex;gap:18px;color:var(--muted);font-size:.85rem;margin:10px 0 8px}
.stats b{color:var(--ink);font-variant-numeric:tabular-nums}
.bars{display:flex;gap:2px;align-items:flex-end;height:34px;margin-top:6px}
.bars i{width:8px;border-radius:2px;background:var(--good);opacity:.85;display:block}
.bars i.bad{background:var(--bad)}
.m .err{color:var(--bad);font-size:.85rem;margin-top:6px}
footer{margin-top:36px;color:var(--muted);font-size:.8rem}
a{color:#8ab4ff}
"""


def render_status_html(monitors: list[dict], history: list[dict]) -> str:
    by_name: dict[str, list[dict]] = {}
    for r in history:
        by_name.setdefault(r["name"], []).append(r)

    cards = []
    for m in monitors:
        runs = by_name.get(m["name"], [])[-400:]
        recent = runs[-48:]
        if runs:
            week = [r for r in runs if r.get("ts", "") >= _week_ago_iso()]
            uptime = 100.0 * (sum(1 for r in week if r.get("ok")) / len(week)) if week else None
            last = runs[-1]
            lat = [r["latency_ms"] for r in runs if r.get("latency_ms")]
            avg = int(sum(lat) / len(lat)) if lat else None
            state = "up" if last.get("ok") else "down"
        else:
            uptime, last, avg, state = None, None, None, "unknown"

        bars = "".join(
            f"<i class='{'bad' if not r.get('ok') else ''}' style=\"height:{max(8, min(34, (r.get('latency_ms') or 8) / 40))}px\"></i>"
            for r in recent
        )
        cards.append(f"""
<div class="m">
  <div class="top">
    <h2>{_esc(m['name'])}</h2>
    <span class="pill {state}">{state.upper()}</span>
  </div>
  <div class="url">{_esc(m['url'])}</div>
  <div class="stats">
    <span>7d uptime <b>{f'{uptime:.2f}%' if uptime is not None else '—'}</b></span>
    <span>avg latency <b>{f'{avg} ms' if avg is not None else '—'}</b></span>
    <span>last check <b>{_esc((last or {}).get('ts', '—'))}</b></span>
    <span>checks <b>{len(runs)}</b></span>
  </div>
  <div class="bars">{bars or '<span style="color:#7d8db1;font-size:.8rem">no history yet</span>'}</div>
  {(last and last.get('error')) and f'<div class="err">last error: {_esc(last["error"])}</div>' or ''}
</div>""")

    return ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<meta http-equiv='refresh' content='60'>"
            "<title>Status — all monitors</title>"
            f"<style>{STATUS_CSS}</style></head><body><div class='wrap'>"
            "<h1>📊 Service status</h1>"
            f"<p class='updated'>generated {now_iso()} by cron-ping-monitor</p>"
            f"<div class='grid'>{''.join(cards)}</div>"
            "<footer>cron-ping-monitor — one file, stdlib only. "
            "History: last 400 checks per monitor.</footer>"
            "</div></body></html>")


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _week_ago_iso() -> str:
    return _ts_to_iso(datetime.now(timezone.utc).timestamp() - 7 * 86400)


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Cron Ping Monitor")
    ap.add_argument("--config", default="monitors.json")
    ap.add_argument("--out", default="data", help="output directory (default ./data)")
    ap.add_argument("--notify-telegram", action="store_true",
                    help="alert on up->down / down->up transitions (env TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
    ap.add_argument("--serve", type=int, default=0, metavar="PORT",
                    help="after the sweep, serve --out over HTTP for a quick look")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    monitors = load_monitors(Path(args.config))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    history_path = out / "history.jsonl"
    state_path = out / "state.json"

    history = load_history(history_path)
    prev_state = load_state(state_path)

    results = []
    for m in monitors:
        r = check(m)
        r["ts"] = now_iso()
        results.append(r)
        history.append(r)
        if not args.quiet:
            mark = "OK  " if r["ok"] else "DOWN"
            extra = f" {r['error']}" if r.get("error") else ""
            print(f"[{mark}] {r['name']:<20} {r['status']} {r['latency_ms']}ms{extra}")

    history_path.write_text("".join(json.dumps(r) + "\n" for r in history), encoding="utf-8")

    # transitions -> telegram
    if args.notify_telegram:
        token = __import__("os").environ.get("TELEGRAM_BOT_TOKEN", "")
        chat = __import__("os").environ.get("TELEGRAM_CHAT_ID", "")
        if token and chat:
            for r in results:
                prev = prev_state.get(r["name"], {}).get("ok")
                if prev is not None and prev != r["ok"]:
                    direction = "🟢 BACK UP" if r["ok"] else "🔴 DOWN"
                    notify_telegram(token, chat,
                                    f"{direction} — {r['name']} ({r['url']})\n{r.get('error') or 'HTTP ' + str(r['status'])} at {r['ts']}")
        prev_state = {r["name"]: {"ok": r["ok"], "ts": r["ts"]} for r in results}
        state_path.write_text(json.dumps(prev_state, indent=2), encoding="utf-8")

    (out / "status.json").write_text(json.dumps(
        {"generated_at": now_iso(), "monitors": results}, indent=2), encoding="utf-8")
    (out / "status.html").write_text(render_status_html(monitors, history), encoding="utf-8")
    if not args.quiet:
        print(f"status page: {out / 'status.html'}")

    if args.serve:
        import http.server
        import functools
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
        print(f"serving {out} on http://localhost:{args.serve}/status.html (Ctrl-C to stop)")
        http.server.ThreadingHTTPServer(("127.0.0.1", args.serve), handler).serve_forever()

    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
