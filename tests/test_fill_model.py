"""Unit tests for ``src.backtest.fill_model``."""

from __future__ import annotations

import pytest

from src.backtest.fill_model import FillModel, FillModelConfig
from src.datamodel import Order, OrderDepth, Trade


def _depth(buys: dict[int, int], sells: dict[int, int]) -> OrderDepth:
    return OrderDepth(buy_orders=dict(buys), sell_orders=dict(sells))


@pytest.mark.unit
def test_marketable_buy_fills_against_visible_ask_and_drops_residual() -> None:
    model = FillModel()
    depth = _depth({9998: 3}, {10002: -5})
    result = model.split_taker_and_residual([Order("P", 10003, 8)], depth, timestamp=100)
    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.mode == "taker"
    assert fill.trade.price == 10002
    assert fill.trade.quantity == 5  # walked whole ask
    # Residual from a partial taker fill is dropped (Prosperity cancels it).
    assert result.pending_maker == []


@pytest.mark.unit
def test_marketable_sell_fills_against_visible_bid_and_drops_residual() -> None:
    model = FillModel()
    depth = _depth({9998: 5}, {10002: -5})
    result = model.split_taker_and_residual([Order("P", 9997, -8)], depth, timestamp=0)
    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.mode == "taker"
    assert fill.trade.price == 9998
    assert fill.trade.quantity == 5
    assert result.pending_maker == []


@pytest.mark.unit
def test_non_marketable_order_becomes_pending_maker() -> None:
    model = FillModel()
    depth = _depth({9998: 5}, {10002: -5})
    result = model.split_taker_and_residual([Order("P", 9997, 3)], depth, timestamp=0)
    assert result.fills == []
    assert len(result.pending_maker) == 1
    assert result.pending_maker[0].price == 9997
    assert result.pending_maker[0].quantity == 3


@pytest.mark.unit
def test_buy_walks_through_multiple_ask_levels() -> None:
    model = FillModel()
    depth = _depth({100: 1}, {101: -2, 102: -3, 103: -10})
    result = model.split_taker_and_residual([Order("P", 102, 4)], depth, timestamp=0)
    quantities = [(f.trade.price, f.trade.quantity) for f in result.fills]
    assert quantities == [(101, 2), (102, 2)]


@pytest.mark.unit
def test_batch_of_orders_share_liquidity() -> None:
    model = FillModel()
    depth = _depth({100: 10}, {101: -5})
    result = model.split_taker_and_residual(
        [Order("P", 101, 5), Order("P", 101, 5)], depth, timestamp=0
    )
    assert len(result.fills) == 1
    assert result.fills[0].trade.quantity == 5


@pytest.mark.unit
def test_zero_quantity_order_is_dropped() -> None:
    model = FillModel()
    depth = _depth({100: 5}, {101: -5})
    result = model.split_taker_and_residual([Order("P", 101, 0)], depth, timestamp=0)
    assert result.fills == []
    assert result.pending_maker == []


# ---------------------------------------------------------------- passive


@pytest.mark.unit
def test_passive_fill_credits_share_of_market_trade_at_matching_price() -> None:
    model = FillModel(FillModelConfig(passive_allocation=0.5))
    orders = [Order("P", 9998, 10)]  # resting buy at 9998
    market_trades = [Trade("P", 9998, 6, timestamp=100)]

    fills = model.score_passive_fills(orders, market_trades, timestamp=100)

    assert len(fills) == 1
    fill = fills[0]
    assert fill.mode == "maker"
    assert fill.trade.buyer == "SELF"
    assert fill.trade.quantity == 3  # floor(6 * 0.5)


@pytest.mark.unit
def test_passive_fill_never_exceeds_resting_size() -> None:
    model = FillModel(FillModelConfig(passive_allocation=1.0))
    orders = [Order("P", 9998, 2)]
    market_trades = [Trade("P", 9998, 10, timestamp=0)]
    fills = model.score_passive_fills(orders, market_trades, timestamp=0)
    assert fills[0].trade.quantity == 2


@pytest.mark.unit
def test_passive_fill_ignores_non_matching_prices() -> None:
    model = FillModel(FillModelConfig(passive_allocation=1.0))
    orders = [Order("P", 9998, 5)]
    market_trades = [Trade("P", 9999, 5, timestamp=0)]
    fills = model.score_passive_fills(orders, market_trades, timestamp=0)
    assert fills == []


@pytest.mark.unit
def test_passive_fills_disabled_returns_empty() -> None:
    model = FillModel(FillModelConfig(passive_fills_enabled=False))
    orders = [Order("P", 9998, 5)]
    market_trades = [Trade("P", 9998, 5, timestamp=0)]
    fills = model.score_passive_fills(orders, market_trades, timestamp=0)
    assert fills == []


@pytest.mark.unit
def test_passive_fill_handles_both_buy_and_sell_at_same_price() -> None:
    """A trade at P can't fill both a buy and a sell at P in the same step.

    The fill model should allocate the trade to the first side that
    needs it and not double-count.
    """
    model = FillModel(FillModelConfig(passive_allocation=1.0))
    orders = [Order("P", 100, 4), Order("P", 100, -4)]
    market_trades = [Trade("P", 100, 4, timestamp=0)]
    fills = model.score_passive_fills(orders, market_trades, timestamp=0)
    # Only one side gets the 4 units; the trade_remaining goes to zero.
    total_q = sum(f.trade.quantity for f in fills)
    assert total_q == 4


@pytest.mark.unit
def test_passive_allocation_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        FillModel(FillModelConfig(passive_allocation=1.5))
    with pytest.raises(ValueError):
        FillModel(FillModelConfig(passive_allocation=-0.1))
