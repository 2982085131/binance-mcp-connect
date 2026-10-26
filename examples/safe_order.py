"""Place a post-only limit order (dry run unless --execute is passed).

The order is validated against hedge-mode rules and the 20 USDT minimum
notional before anything is sent.
"""
from __future__ import annotations

import argparse
import sys
import time

from binance_mcp_connect import (
    BinanceMCPClient,
    Order,
    get_codex_token,
    round_price,
    round_qty,
    validate,
)


def place_and_cancel(client, order: Order, symbol: str, wait_seconds: float = 2.0) -> int:
    """Place, query, then always attempt to cancel. Returns a process exit code."""
    placed = client.call("futures_usds.newOrder", order.params())
    print("placed:", placed)
    order_id = placed.get("orderId")
    if not order_id:
        print("no orderId in the response; not confirmed, check the exchange UI",
              file=sys.stderr)
        return 1
    try:
        time.sleep(wait_seconds)
        print("status:", client.call("futures_usds.queryOrder",
                                     {"symbol": symbol, "orderId": order_id}))
    except Exception as exc:  # noqa: BLE001
        print(f"query failed for order {order_id}: {exc}; will try to cancel",
              file=sys.stderr)
    finally:
        try:
            print("cancel:", client.call("futures_usds.cancelOrder",
                                         {"symbol": symbol, "orderId": order_id}))
        except Exception as exc:  # noqa: BLE001
            print(f"CANCEL FAILED for order {order_id}: {exc}. "
                  "The order may still be live; cancel it manually.", file=sys.stderr)
            return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETHUSDT")
    ap.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    ap.add_argument("--qty", type=float, default=0.009)
    ap.add_argument("--offset-bp", type=float, default=2.0)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    client = BinanceMCPClient(get_codex_token()["access_token"])
    px = client.price(args.symbol)
    offset = args.offset_bp / 1e4
    limit = round_price(px * (1 - offset) if args.side == "BUY" else px * (1 + offset))
    order = Order(
        symbol=args.symbol,
        side=args.side,
        position_side="LONG" if args.side == "BUY" else "SHORT",
        order_type="LIMIT",
        quantity=round_qty(args.qty),
        price=limit,
        time_in_force="GTX",
    )
    validate(order)
    print("price :", px)
    print("order :", order.params())
    if not args.execute:
        print("dry run; pass --execute to send")
        return 0
    return place_and_cancel(client, order, args.symbol)


if __name__ == "__main__":
    raise SystemExit(main())
