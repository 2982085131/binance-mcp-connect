"""Order validation and hedge-mode helpers for Binance USD-M futures."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP

# Defaults observed on a small Binance Agentic sub-account (2026-10).
MIN_NOTIONAL = 20.0
QTY_STEP = 0.001
PRICE_TICK = 0.01

ORDER_TYPES = {"LIMIT", "MARKET", "STOP", "STOP_MARKET", "TAKE_PROFIT",
               "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET"}
LIMIT_TIF = {"GTC", "IOC", "FOK", "GTX", "GTD"}


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


def _dec(value: float | str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise OrderValidationError(f"invalid number: {value!r}") from exc


def round_qty(qty: float, step: float = QTY_STEP) -> float:
    """Floor to the quantity step without float drift.

    ``0.043 / 0.001`` is 42.99999999999999 in binary floats; a naive floor
    returns 0.042. Decimal arithmetic keeps 0.043 intact.
    """
    q, s = _dec(qty), _dec(step)
    if s <= 0:
        raise OrderValidationError("step must be positive")
    return float((q / s).to_integral_value(rounding=ROUND_FLOOR) * s)


def round_price(price: float, tick: float = PRICE_TICK) -> float:
    t = _dec(tick)
    if t <= 0:
        raise OrderValidationError("tick must be positive")
    return float((_dec(price) / t).to_integral_value(rounding=ROUND_HALF_UP) * t)


def _is_multiple(value: float, step: float) -> bool:
    v, s = _dec(value), _dec(step)
    return v % s == 0


def validate(order: Order, hedge_mode: bool = True, min_notional: float = MIN_NOTIONAL,
             qty_step: float = QTY_STEP, price_tick: float = PRICE_TICK) -> Order:
    if order.side not in ("BUY", "SELL"):
        raise OrderValidationError("side must be BUY or SELL")
    if order.order_type not in ORDER_TYPES:
        raise OrderValidationError(f"unsupported order type: {order.order_type}")
    if hedge_mode and order.position_side not in ("LONG", "SHORT"):
        raise OrderValidationError(
            "hedge mode requires positionSide LONG/SHORT; BOTH is rejected with -4061")
    if hedge_mode and order.reduce_only:
        raise OrderValidationError(
            "reduceOnly is not allowed in hedge mode (-1106); close with the opposite "
            "side and the same positionSide instead")
    if order.quantity <= 0:
        raise OrderValidationError("quantity must be positive")
    if not _is_multiple(order.quantity, qty_step):
        raise OrderValidationError(f"quantity must be a multiple of {qty_step}")
    if order.order_type == "LIMIT":
        if order.price is None:
            raise OrderValidationError("LIMIT order requires a price")
        if order.time_in_force not in LIMIT_TIF:
            raise OrderValidationError(f"LIMIT timeInForce must be one of {sorted(LIMIT_TIF)}")
        if not _is_multiple(order.price, price_tick):
            raise OrderValidationError(f"price must be a multiple of {price_tick}")
        notional = _dec(order.quantity) * _dec(order.price)
        if notional < _dec(min_notional):
            raise OrderValidationError(
                f"notional {float(notional):.2f} < {min_notional} USDT; increase quantity "
                "or the order is rejected with -4164")
    else:
        if order.price is not None:
            raise OrderValidationError("price is only valid for LIMIT orders")
        if order.time_in_force is not None:
            raise OrderValidationError("timeInForce is only valid for LIMIT orders")
    return order


def price_tick_ok(price: float | None, tick: float) -> bool:
    if price is None:
        return True
    return _is_multiple(price, tick)


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
