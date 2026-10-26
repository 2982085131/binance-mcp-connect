import pytest

from binance_mcp_connect import Order, OrderValidationError, round_price, validate


def make(**kw):
    base = dict(symbol="ETHUSDT", side="BUY", position_side="LONG",
                order_type="LIMIT", quantity=0.009, price=2400.0, time_in_force="GTX")
    base.update(kw)
    return Order(**base)


def test_valid_order_passes():
    assert validate(make()) is not None


def test_hedge_mode_rejects_both():
    with pytest.raises(OrderValidationError, match="positionSide"):
        validate(make(position_side="BOTH"))


def test_hedge_mode_rejects_reduce_only():
    with pytest.raises(OrderValidationError, match="reduceOnly"):
        validate(make(reduce_only=True))


def test_min_notional():
    with pytest.raises(OrderValidationError, match="notional"):
        validate(make(quantity=0.005, price=2400.0))


def test_quantity_step():
    with pytest.raises(OrderValidationError, match="multiple"):
        validate(make(quantity=0.0095))


def test_round_price():
    assert round_price(2399.999) == 2400.0
