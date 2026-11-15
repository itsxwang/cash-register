"""Command-line interface: python3 -m payments <command> ..."""
from __future__ import annotations

import argparse
import sys

from . import (check_all, check_paid, create_demo_fixtures, create_order,
               get_order, ingest_order, list_orders, load_config,
               manual, mark_paid, public_order, rotate_download_token,
               sync_static)
from . import watchers


def _print_order(order: dict) -> None:
    print(f"order        {order['order_id']}")
    print(f"tool         {order['tool_id']}")
    print(f"status       {order['status']}")
    print(f"chain        {order['chain']} ({order.get('chain_name', '')})")
    print(f"price        ${order['price_usd']:.2f}")
    print(f"send         {order['amount']} {order['currency']} (exactly)")
    print(f"to           {order['address']}")
    print(f"memo         {order['memo']}")
    print(f"created_at   {order['created_at']}")


def cmd_create(args) -> int:
    cfg = load_config(args.config)
    order = create_order(args.tool, args.price, chain=args.chain,
                         note=args.note, cfg=cfg)
    _print_order(order)
    print(f"\nStorefront assets written: site/data/orders/{order['order_id']}.json")
    print(f"Run `python3 -m payments sync` if you changed addresses or prices.")
    return 0


def cmd_ingest(args) -> int:
    cfg = load_config(args.config)
    order = ingest_order(args.order, args.tool, price_usd=args.price,
                         chain=args.chain, cfg=cfg)
    _print_order(order)
    return 0


def cmd_list(args) -> int:
    cfg = load_config(args.config)
    orders = list_orders(status=args.status, tool_id=args.tool, cfg=cfg)
    if not orders:
        print("(no orders)")
        return 0
    print(f"{'ORDER':<12} {'TOOL':<32} {'CHAIN':<10} {'AMOUNT':<16} "
          f"{'STATUS':<18} CREATED")
    for o in orders:
        print(f"{o['order_id']:<12} {o['tool_id'][:31]:<32} {o['chain']:<10} "
              f"{o['amount']} {o['currency']:<11} {o['status']:<18} {o['created_at']}")
    return 0


def cmd_check(args) -> int:
    cfg = load_config(args.config)
    if args.order:
        order = check_paid(args.order, use_watchers=not args.no_watchers, cfg=cfg)
        _print_order(order)
        meta_watch = (order.get("meta") or {}).get("watch")
        if meta_watch and not order["status"].startswith("p"):
            print(f"watcher     {meta_watch.get('note', '')}")
        return 0
    results = check_all(use_watchers=not args.no_watchers, cfg=cfg)
    if not results:
        print("no awaiting orders")
    for order in results:
        line = f"{order['order_id']:<12} {order['status']}"
        meta_watch = (order.get("meta") or {}).get("watch")
        if meta_watch and meta_watch.get("note"):
            line += f"  [{meta_watch['note']}]"
        print(line)
    return 0


def cmd_mark(args) -> int:
    cfg = load_config(args.config)
    order = mark_paid(args.order, txid=args.txid,
                      source=args.source or "manual_cli", cfg=cfg)
    _print_order(order)
    return 0


def cmd_sync(args) -> int:
    cfg = load_config(args.config)
    written = sync_static(cfg=cfg, refresh_fx=args.refresh_fx)
    for path in written:
        print(f"wrote {path}")
    print(f"total: {len(written)} files")
    return 0


def cmd_rotate(args) -> int:
    cfg = load_config(args.config)
    order = rotate_download_token(args.order, cfg=cfg)
    print(f"new download token for {order['order_id']}: {order['download_token']}")
    print("order JSON rewritten; the old link stops working on the next site deploy")
    return 0


def cmd_demo(args) -> int:
    cfg = load_config(args.config)
    made = create_demo_fixtures(cfg=cfg)
    for order in made:
        _print_order(order)
        print()
    print("Demo fixtures written into site/data/. Run the site:")
    print("  cd site && python3 -m http.server 8000")
    return 0


def cmd_doctor(args) -> int:
    cfg = load_config(args.config)
    print("Checking chain APIs (keyless endpoints + env keys)...")
    for name, ok in watchers.probe(cfg).items():
        state = "OK" if ok else ("SKIPPED (no ETHERSCAN_API_KEY)" if name == "eth_etherscan" else "UNREACHABLE")
        print(f"  {name:<20} {state}")
    print("Watchers degrade gracefully: an unreachable chain is skipped, "
          "manual CSV confirmations always work.")
    return 0


def cmd_confirm_template(args) -> int:
    path = manual.ensure_template()
    print(f"confirmations CSV ready: {path}")
    print("Add one row per paid order: order_id,txid,confirmed_at,source,note")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="payments",
        description="Cash Register — crypto checkout + delivery for digital products")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("create", help="create a new order")
    sp.add_argument("--tool", required=True)
    sp.add_argument("--price", type=float, default=None, help="override price in USD")
    sp.add_argument("--chain", default=None, choices=["eth", "sol", "btc"])
    sp.add_argument("--note", default=None)
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("ingest", help="register a buyer-reported order id")
    sp.add_argument("--order", required=True)
    sp.add_argument("--tool", required=True)
    sp.add_argument("--price", type=float, default=None)
    sp.add_argument("--chain", default=None, choices=["eth", "sol", "btc"])
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("list", help="list orders")
    sp.add_argument("--status", default=None)
    sp.add_argument("--tool", default=None)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("check", help="check payment (CSV first, then watchers)")
    sp.add_argument("order", nargs="?", default=None)
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--no-watchers", action="store_true")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("mark", help="manually mark an order paid")
    sp.add_argument("--order", required=True)
    sp.add_argument("--txid", default=None)
    sp.add_argument("--source", default="manual_cli")
    sp.set_defaults(func=cmd_mark)

    sp = sub.add_parser("sync", help="regenerate catalog + order JSON + QRs")
    sp.add_argument("--refresh-fx", action="store_true",
                    help="refresh live FX rates (falls back to config offline)")
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("rotate", help="rotate an order's download token")
    sp.add_argument("--order", required=True)
    sp.set_defaults(func=cmd_rotate)

    sp = sub.add_parser("demo", help="(re)create demo fixture orders")
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("doctor", help="probe chain APIs reachability")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("confirm-template", help="create payments/confirmations.csv")
    sp.set_defaults(func=cmd_confirm_template)

    for sp in sub.choices.values():
        sp.add_argument("--config", default=None, help="path to config.yaml")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
