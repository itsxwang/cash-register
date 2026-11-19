# Telegram Broadcast & Scheduler Bot

Raw Telegram Bot API, Python stdlib only, one file. No `python-telegram-bot`,
no webhooks, no server.

## Setup (5 minutes)

1. Message **@BotFather** on Telegram → `/newbot` → copy the token.
2. `export TELEGRAM_BOT_TOKEN=123456:ABC-DEF...`
3. `python3 broadcast_bot.py poll` — leave it running (tmux/nohup) or run it
   from cron every minute with `--interval 55` semantics: each run long-polls
   for ~25s and captures anyone who messages the bot.
4. Send anything to your bot from your phone → you're now a subscriber
   (`data/subscribers.json`).

## Daily use

```bash
python3 broadcast_bot.py list
python3 broadcast_bot.py send 123456789 "private ping"
python3 broadcast_bot.py broadcast "New drop is live 🚀"
python3 broadcast_bot.py schedule add --at "2026-11-20 09:00" --text "Weekly digest"
# add --html to any send/broadcast/schedule command to use Telegram HTML formatting
python3 broadcast_bot.py schedule list
python3 broadcast_bot.py run-scheduler --interval 30    # long-running, or via cron
```

Cron for the scheduler instead of a resident process:

```
* * * * * cd /path && python3 broadcast_bot.py run-scheduler --interval 55 >> cron.log 2>&1
```

## Message formatting

Messages are sent as **plain text** by default, so characters like `<`, `>` and
`&` never break a send. If you want Telegram's HTML formatting (bold, links,
code), add `--html` and write valid HTML tags:

```bash
python3 broadcast_bot.py broadcast "<b>New drop</b> is live: https://example.com" --html
```

## Offline testing

Every command accepts `--dry-run`: it prints what it would send and touches
no network, so you can verify the CLI without a token.

## Rate limits

`broadcast` sleeps ~0.9s per message (Telegram's global cap is ~30 msg/s;
per-chat caps are far lower). Failed sends are reported per chat id —
typically blocked bots (user pressed "Block") — prune them with a future
`remove` command or edit `data/subscribers.json` by hand.
