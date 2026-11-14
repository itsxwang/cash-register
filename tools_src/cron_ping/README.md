# Cron Ping Monitor

One file, Python stdlib only. A cron-friendly uptime pinger that renders a
static status page you can host anywhere for $0.

## Files

- `cron_ping.py` — the monitor + status-page generator
- `monitors.example.json` — copy to `monitors.json` and edit
- `data/` — created at runtime: `history.jsonl`, `status.json`, `status.html`

## Quick start

```bash
cp monitors.example.json monitors.json   # edit with your URLs
python3 cron_ping.py                     # one sweep, prints per-monitor lines
python3 cron_ping.py --serve 8080        # sweep + preview at http://localhost:8080/status.html
```

Exit codes: `0` all up · `1` any monitor down · `2` setup error — so cron
itself can alert you if you configure a mailer on non-zero exit.

## Production cron

```
* * * * * cd /path/to/cron_ping && python3 cron_ping.py >> cron.log 2>&1
```

Every minute is the sweet spot; each run is a few HTTP GETs. The status page
is regenerated on every run — host `data/` on any static host
(Cloudflare Pages / GitHub Pages / S3) if you want it public.

## Telegram alerts (optional)

```bash
export TELEGRAM_BOT_TOKEN=123456:ABC...
export TELEGRAM_CHAT_ID=123456789
python3 cron_ping.py --notify-telegram
```

Fires a message on up→down and down→up transitions (state tracked in
`data/state.json`). Reuse the broadcaster bot's token from the Telegram
Broadcast tool if you have it.
