#!/usr/bin/env python3
"""Telegram Broadcast & Scheduler Bot — raw Bot API, stdlib only, one file.

No python-telegram-bot, no webhooks, no server. Your bot token + a JSON
subscriber list is all you need.

Setup (one time):
    1. Talk to @BotFather on Telegram -> /newbot -> copy the token.
    2. export TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
    3. python3 broadcast_bot.py poll          # leave running; /start captures subs
    4. People message your bot -> they're added to data/subscribers.json

Daily use:
    python3 broadcast_bot.py list
    python3 broadcast_bot.py send 123456789 "direct message"
    python3 broadcast_bot.py broadcast "New drop is live 🚀"
    python3 broadcast_bot.py schedule add --at "2026-11-20 09:00" --text "Weekly digest"
    python3 broadcast_bot.py schedule list
    python3 broadcast_bot.py run-scheduler --interval 30   # or run it from cron

Offline / dry-run mode: every command accepts --dry-run (prints payloads,
touches no network) so you can test the CLI without a token.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SUBSCRIBERS = DATA / "subscribers.json"
SCHEDULE = DATA / "schedule.json"
RATE_PER_SECOND = 0.9          # stay under Telegram's ~30 msg/s global limit


def api(token: str, method: str, payload: dict | None = None) -> dict:
    """Call the Bot API. Raises RuntimeError with Telegram's description on failure."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"ok": False, "description": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"network error: {type(exc).__name__}: {exc}") from exc
    if not body.get("ok"):
        raise RuntimeError(f"telegram: {body.get('description', 'unknown error')}")
    return body.get("result", {})


def token_from_env() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("error: TELEGRAM_BOT_TOKEN not set (get one from @BotFather). "
              "Use --dry-run to test without a token.", file=sys.stderr)
        sys.exit(2)
    return token


def load_json(path: Path, default):
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def subscribers() -> list[int]:
    return load_json(SUBSCRIBERS, [])


def add_subscriber(chat_id: int) -> bool:
    subs = subscribers()
    if chat_id in subs:
        return False
    subs.append(chat_id)
    save_json(SUBSCRIBERS, sorted(subs))
    return True


def send_one(token: str, chat_id: int, text: str, dry: bool, html: bool = False) -> tuple[bool, str]:
    # Plain text by default: a stray "<" or "&" in an HTML-parsed message makes
    # Telegram reject the whole send. Opt into HTML with --html.
    payload = {"chat_id": chat_id, "text": text}
    if html:
        payload["parse_mode"] = "HTML"
    if dry:
        return True, "dry-run"
    try:
        api(token, "sendMessage", payload)
        return True, "sent"
    except RuntimeError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_poll(token: str, args) -> None:
    """Long-poll getUpdates; /start (any message) adds the sender as subscriber."""
    offset = 0
    print("Polling for new subscribers… Ctrl-C to stop. Users must message the bot once.")
    while True:
        try:
            if args.dry_run:
                print("(dry-run: would long-poll getUpdates; capturing /start as subscribers)")
                return
            res = api(token, "getUpdates", {"offset": offset, "timeout": 25})
            for upd in res:
                offset = max(offset, upd.get("update_id", 0) + 1)
                msg = upd.get("message") or upd.get("channel_post") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id is None:
                    continue
                added = add_subscriber(int(chat_id))
                name = chat.get("username") or chat.get("title") or chat_id
                print(f"{'added' if added else 'known '} subscriber: {name} ({chat_id})")
        except KeyboardInterrupt:
            print("bye")
            return
        except RuntimeError as exc:
            print(f"poll error: {exc} — retrying in 5s", file=sys.stderr)
            time.sleep(5)


def cmd_list(token: str, args) -> None:
    subs = subscribers()
    print(f"{len(subs)} subscriber(s):")
    for s in subs:
        print(f"  {s}")


def cmd_send(token: str, args) -> None:
    ok, info = send_one(token, int(args.chat_id), args.text, args.dry_run, getattr(args, "html", False))
    print(("sent" if ok else f"FAILED: {info}"), f"-> {args.chat_id}")
    if not ok:
        sys.exit(1)


def cmd_broadcast(token: str, args) -> None:
    subs = subscribers()
    if not subs:
        print("no subscribers yet — run `poll` and have people /start the bot")
        return
    sent, failed = 0, []
    for chat_id in subs:
        ok, info = send_one(token, chat_id, args.text, args.dry_run, getattr(args, "html", False))
        if ok:
            sent += 1
        else:
            failed.append((chat_id, info))
            print(f"failed {chat_id}: {info}", file=sys.stderr)
        if not args.dry_run:
            time.sleep(RATE_PER_SECOND)
    print(f"broadcast done: {sent}/{len(subs)} delivered" + (f", {len(failed)} failed" if failed else ""))


def cmd_schedule(args) -> None:
    items = load_json(SCHEDULE, [])
    if args.schedule_cmd == "add":
        try:
            at = datetime.strptime(args.at, "%Y-%m-%d %H:%M")
        except ValueError:
            print('error: --at must look like "2026-11-20 09:00" (24h local time)', file=sys.stderr)
            sys.exit(2)
        item = {
            "id": f"sched-{int(time.time() * 1000)}",
            "at": at.strftime("%Y-%m-%d %H:%M"),
            "text": args.text,
            "html": bool(getattr(args, "html", False)),
            "status": "pending",
        }
        items.append(item)
        save_json(SCHEDULE, items)
        print(f"scheduled {item['id']}: {item['at']} — {args.text[:60]}")
    else:  # list
        if not items:
            print("(schedule empty)")
            return
        for it in sorted(items, key=lambda x: x["at"]):
            print(f"  {it['id']}  {it['at']}  [{it['status']}]  {it['text'][:50]}")


def cmd_run_scheduler(token: str, args) -> None:
    print(f"scheduler running (interval {args.interval}s). Ctrl-C to stop.")
    while True:
        try:
            items = load_json(SCHEDULE, [])
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            changed = False
            for it in items:
                if it.get("status") == "pending" and it["at"] <= now:
                    subs = subscribers()
                    ok_count = 0
                    for chat_id in subs:
                        ok, _ = send_one(token, chat_id, it["text"], args.dry_run,
                                         bool(it.get("html", False)))
                        ok_count += 1 if ok else 0
                        if not args.dry_run:
                            time.sleep(RATE_PER_SECOND)
                    it["status"] = "sent"
                    it["sent_to"] = ok_count
                    changed = True
                    print(f"[{now}] fired {it['id']} -> {ok_count}/{len(subs)}")
            if changed:
                save_json(SCHEDULE, items)
        except KeyboardInterrupt:
            print("scheduler stopped")
            return
        except RuntimeError as exc:
            print(f"scheduler error: {exc}", file=sys.stderr)
        if args.dry_run:
            print("(dry-run: one scheduler pass complete)")
            return
        time.sleep(args.interval)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Telegram Broadcast & Scheduler Bot")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("poll", help="capture new subscribers from /start")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("list", help="list subscribers")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("send", help="message one chat id")
    p.add_argument("chat_id")
    p.add_argument("text")
    p.add_argument("--html", action="store_true", help="parse the text as Telegram HTML (default: plain text)")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("broadcast", help="message every subscriber")
    p.add_argument("text")
    p.add_argument("--html", action="store_true", help="parse the text as Telegram HTML (default: plain text)")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("schedule", help="schedule posts")
    sched = p.add_subparsers(dest="schedule_cmd", required=True)
    sp = sched.add_parser("add")
    sp.add_argument("--at", required=True, help='"YYYY-MM-DD HH:MM" (24h, local time)')
    sp.add_argument("--text", required=True)
    sp.add_argument("--html", action="store_true", help="parse the text as Telegram HTML (default: plain text)")
    sched.add_parser("list")

    p = sub.add_parser("run-scheduler", help="send due scheduled posts in a loop")
    p.add_argument("--interval", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)

    if args.cmd == "schedule":
        cmd_schedule(args)
        return 0

    token = "DRYRUN" if args.dry_run else token_from_env()
    {"poll": cmd_poll, "list": cmd_list, "send": cmd_send,
     "broadcast": cmd_broadcast, "run-scheduler": cmd_run_scheduler}[args.cmd](token, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
