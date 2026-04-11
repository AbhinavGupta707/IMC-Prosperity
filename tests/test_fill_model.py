"""Unit tests for ``src.backtest.fill_model``."""

from __future__ import annotations

import pytest

from src.backtest.fill_model import FillModel
from src.datamodel import Order, OrderDepth


def _depth(buys: dict[int, int], sells: dict[int, int]) -> OrderDepth:
    return OrderDepth(buy_orders=dict(buys), sell_orders=dict(sells))


@pytest.mark.unit
def test_marketable_buy_fills_against_visible_ask() -> None:
    model = FillModel()
    depth = _depth({9998: 3}, {10002: -5})
    trades = model.fill_orders([Order("P", 10003, 4)], depth, timestamp=100)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "P"
    assert trade.price == 10002
    assert trade.quantity == 4
    assert trade.buyer == "SELF"
    assert trade.seller is None
    assert trade.timestamp == 100


@pytest.mark.unit
def test_marketable_sell_fills_against_visible_bid() -> None:
    model = FillModel()
    depth = _depth({9998: 5}, {10002: -5})
    trades = model.fill_orders([Order("P", 9997, -3)], depth, timestamp=200)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.price == 9998
    assert trade.quantity == 3
    assert trade.buyer is None
    assert trade.seller == "SELF"


@pytest.mark.unit
def test_non_marketable_order_produces_no_fills() -> None:
    model = FillModel()
    depth = _depth({9998: 5}, {10002: -5})
    buys = model.fill_orders([Order("P", 9997, 3)], depth, timestamp=0)
    sells = model.fill_orders([Order("P", 10003, -3)], depth, timestamp=0)
    assert buys == []
    assert sells == []


@pytest.mark.unit
def test_buy_walks_through_multiple_ask_levels() -> None:
    model = FillModel()
    depth = _depth({100: 1}, {101: -2, 102: -3, 103: -10})
    trades = model.fill_orders([Order("P", 102, 4)], depth, timestamp=0)

    quantities = [(t.price, t.quantity) for t in trades]
    assert quantities == [(101, 2), (102, 2)]


@pytest.mark.unit
def test_sell_walks_through_multiple_bid_levels() -> None:
    model = FillModel()
    depth = _depth({100: 2, 99: 3, 98: 10}, {105: -1})
    trades = model.fill_orders([Order("P", 99, -4)], depth, timestamp=0)

    quantities = [(t.price, t.quantity) for t in trades]
    assert quantities == [(100, 2), (99, 2)]


@pytest.mark.unit
def test_batch_of_orders_share_liquidity() -> None:
    model = FillModel()
    depth = _depth({100: 10}, {101: -5})
    # First order consumes all 5 at 101, second should find nothing.
    trades = model.fill_orders([Order("P", 101, 5), Order("P", 101, 5)], depth, timestamp=0)
    assert len(trades) == 1
    assert trades[0].quantity == 5


@pytest.mark.unit
def test_zero_quantity_order_is_dropped() -> None:
    model = FillModel()
    depth = _depth({100: 5}, {101: -5})
    trades = model.fill_orders([Order("P", 101, 0)], depth, timestamp=0)
    assert trades == []


@pytest.mark.unit
def test_passive_fills_default_off() -> None:
    """Our phase 2A fill model must never fill passive orders."""
    model = FillModel()
    depth = _depth({100: 5}, {101: -5})
    # A maker bid at 100 is exactly at the existing best bid: not marketable.
    trades = model.fill_orders([Order("P", 100, 3)], depth, timestamp=0)
    assert trades == []
