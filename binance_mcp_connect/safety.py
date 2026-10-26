"""Order validation and hedge-mode helpers for Binance USD-M futures."""
from __future__ import annotations

import math
from dataclasses import dataclass

# Defaults observed on a small Binance Agentic sub-account (2026-10).
MIN_NOTIONAL = 20.0
QTY_STEP = 0.001
PRICE_TICK = 0.01


class OrderValidationError(ValueError):
    pass


@dataclass
class Order:
    symbol: str
    side: str                 # BUY / SELL
    position_side: str        # LONG / SHORT (hedge mode)
    order_type: str           # LIMIT / MARKET / STOP_MARKET ...
    quantity: float
    price: float | None = None
    time_in_force: str | None = None
    reduce_only: bool = False

    def params(self) -> dict:
        out: dict = {
            "symbol": self.symbol,
            "side": self.side,
            "positionSide": self.position_side,
            "type": self.order_type,
            "quantity": self.quantity,
            "newOrderRespType": "RESULT",
        }
        if self.price is not None:
            out["price"] = self.price
        if self.time_in_force:
            out["timeInForce"] = self.time_in_force
        if self.reduce_only:
            out["reduceOnly"] = "true"
        return out


def round_qty(qty: float, step: float = QTY_STEP) -> float:
    return round(math.floor(qty / step) * step, 8)


def round_price(price: float, tick: float = PRICE_TICK) -> float:
    return round(round(price / tick) * tick, 8)


def validate(order: Order, hedge_mode: bool = True, min_notional: float = MIN_NOTIONAL,
             qty_step: float = QTY_STEP, price_tick: float = PRICE_TICK) -> Order:
    if order.side not in ("BUY", "SELL"):
        raise OrderValidationError("side must be BUY or SELL")
    if hedge_mode and order.position_side not in ("LONG", "SHORT"):
        raise OrderValidationError(
            "hedge mode requires positionSide LONG/SHORT; BOTH is rejected with -4061")
    if hedge_mode and order.reduce_only:
        raise OrderValidationError(
            "reduceOnly is not allowed in hedge mode (-1106); close with the opposite "
            "side and the same positionSide instead")
    if order.quantity <= 0:
        raise OrderValidationError("quantity must be positive")
    if abs(order.quantity / qty_step - round(order.quantity / qty_step)) > 1e-6:
        raise OrderValidationError(f"quantity must be a multiple of {qty_step}")
    notional = order.quantity * (order.price or 0)
    if order.order_type == "LIMIT" and not price_tick_ok(order.price, price_tick):
        raise OrderValidationError(f"price must be a multiple of {price_tick}")
    if order.order_type == "LIMIT" and notional < min_notional:
        raise OrderValidationError(
            f"notional {notional:.2f} < {min_notional} USDT; increase quantity "
            "or the order is rejected with -4164")
    if order.order_type == "MARKET" and order.quantity <= 0:
        raise OrderValidationError("market order needs quantity")
    return order


def price_tick_ok(price: float | None, tick: float) -> bool:
    if price is None:
        return True
    return abs(price / tick - round(price / tick)) < 1e-6


def close_params(position: dict) -> dict:
    """Build a market order that closes a hedge-mode position."""
    amt = float(position["positionAmt"])
    side = "SELL" if amt > 0 else "BUY"
    return {
        "symbol": position["symbol"],
        "side": side,
        "positionSide": position["positionSide"],
        "type": "MARKET",
        "quantity": abs(amt),
        "newOrderRespType": "RESULT",
    }
