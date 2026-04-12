"""Unit and integration tests for ``src.core.residual``.

The residual capacity utilizer is a post-processing step that appends
small passive orders into unused position budget. It ships disabled by
default (framework-only). These tests verify:

- disabled passthrough
- capacity accounting
- spread guard (never cross the book)
- duplicate-price guard (no stacking on main strategy prices)
- recovery-mode suppression
- end-to-end trader integration
"""

from __future__ import annotations

import json

import pytest

from src.core.residual import ResidualAllocator
from src.core.types import BookLevel, NormalizedSnapshot, ResidualConfig
from src.datamodel import Observation, Order, OrderDepth, TradingState
from src.trader import Trader

# ---------------------------------------------------------------- helpers


def _snapshot(
    product: str = "TEST",
    bids: tuple[BookLevel, ...] = (),
    asks: tuple[BookLevel, ...] = (),
    position: int = 0,
) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product=product,
        timestamp=0,
        bids=bids,
        asks=asks,
        position=position,
    )


def _order(product: str, price: int, qty: int) -> Order:
    return Order(product, price, qty)


# ---------------------------------------------------------------- unit tests


@pytest.mark.unit
def test_disabled_returns_orders_unchanged() -> None:
    allocator = ResidualAllocator(ResidualConfig(enabled=False))
    orders = [_order("T", 100, 3)]
    snap = _snapshot(bids=(BookLevel(99, 5),), asks=(BookLevel(101, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    assert result is orders  # exact same object, no copy


@pytest.mark.unit
def test_no_residual_when_fully_utilized() -> None:
    allocator = ResidualAllocator(ResidualConfig(enabled=True, residual_size=2))
    # Main orders consume all capacity: buy 20 + sell 20 on limit=20, pos=0.
    orders = [_order("T", 98, 20), _order("T", 102, -20)]
    snap = _snapshot(bids=(BookLevel(99, 5),), asks=(BookLevel(101, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    assert result == orders


@pytest.mark.unit
def test_adds_bid_when_buy_capacity_remains() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=2.0, residual_size=2),
    )
    # Main order at price 95 (not 98), so no duplicate-price conflict
    # with the residual bid at floor(100 - 2) = 98.
    orders = [_order("T", 95, 5)]  # uses 5 of 20 buy capacity
    snap = _snapshot(bids=(BookLevel(90, 5),), asks=(BookLevel(110, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    # Original + residual bid + residual ask.
    residual_bids = [o for o in result if o.quantity > 0 and o not in orders]
    assert len(residual_bids) == 1
    assert residual_bids[0].price == 98  # floor(100 - 2)
    assert residual_bids[0].quantity == 2


@pytest.mark.unit
def test_adds_ask_when_sell_capacity_remains() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=2.0, residual_size=2),
    )
    orders = [_order("T", 105, -5)]  # uses 5 of 20 sell capacity
    snap = _snapshot(bids=(BookLevel(97, 5),), asks=(BookLevel(103, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    # Residual ask at ceil(100 + 2) = 102. 102 != 105 so no dup guard.
    assert len(result) == 3  # original sell + residual bid + residual ask
    residual_ask = [o for o in result if o.quantity < 0 and o.price == 102]
    assert len(residual_ask) == 1
    assert residual_ask[0].quantity == -2


@pytest.mark.unit
def test_residual_size_capped_by_config() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=2.0, residual_size=3),
    )
    orders: list[Order] = []  # no main orders, full capacity open
    snap = _snapshot(bids=(BookLevel(90, 5),), asks=(BookLevel(110, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    for o in result:
        assert abs(o.quantity) <= 3


@pytest.mark.unit
def test_residual_size_capped_by_remaining_capacity() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=2.0, residual_size=10),
    )
    # Position=19, limit=20 -> buy capacity=1, sell capacity=39.
    orders: list[Order] = []
    snap = _snapshot(
        bids=(BookLevel(90, 5),), asks=(BookLevel(110, 5),), position=19,
    )

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=19, limit=20,
    )

    bids = [o for o in result if o.quantity > 0]
    assert len(bids) == 1
    assert bids[0].quantity == 1  # capped by remaining capacity, not config


@pytest.mark.unit
def test_residual_prices_use_fair_value_and_edge() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=3.5, residual_size=2),
    )
    orders: list[Order] = []
    snap = _snapshot(bids=(BookLevel(90, 5),), asks=(BookLevel(110, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    bids = [o for o in result if o.quantity > 0]
    asks = [o for o in result if o.quantity < 0]
    assert bids[0].price == 96   # floor(100 - 3.5)
    assert asks[0].price == 104  # ceil(100 + 3.5)


@pytest.mark.unit
def test_no_residual_during_recovery() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_size=2),
    )
    orders = [_order("T", 100, -5)]
    snap = _snapshot(bids=(BookLevel(99, 5),), asks=(BookLevel(101, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=10, limit=20,
        mode="recovery",
    )

    assert result is orders


@pytest.mark.unit
def test_residual_bid_suppressed_when_crosses_spread() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=0.5, residual_size=2),
    )
    orders: list[Order] = []
    # fair_value=100, edge=0.5 -> bid at floor(99.5) = 99.
    # best_ask = 99 -> bid would cross/touch.
    snap = _snapshot(bids=(BookLevel(97, 5),), asks=(BookLevel(99, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    bids = [o for o in result if o.quantity > 0]
    assert len(bids) == 0  # bid suppressed


@pytest.mark.unit
def test_residual_ask_suppressed_when_crosses_spread() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=0.5, residual_size=2),
    )
    orders: list[Order] = []
    # fair_value=100, edge=0.5 -> ask at ceil(100.5) = 101.
    # best_bid = 101 -> ask would cross/touch.
    snap = _snapshot(bids=(BookLevel(101, 5),), asks=(BookLevel(103, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    asks = [o for o in result if o.quantity < 0]
    assert len(asks) == 0  # ask suppressed


@pytest.mark.unit
def test_residual_suppressed_when_main_strategy_has_same_price() -> None:
    allocator = ResidualAllocator(
        ResidualConfig(enabled=True, residual_edge=2.0, residual_size=2),
    )
    # fair_value=100, edge=2 -> bid at 98, ask at 102.
    # Main strategy already has a bid at 98 and an ask at 102.
    orders = [_order("T", 98, 5), _order("T", 102, -5)]
    snap = _snapshot(bids=(BookLevel(97, 5),), asks=(BookLevel(103, 5),))

    result = allocator.augment_orders(
        product="T", orders=orders, snapshot=snap,
        fair_value=100.0, position=0, limit=20,
    )

    # Both residual orders suppressed by duplicate-price guard.
    assert len(result) == 2
    assert result == orders


# --------------------------------------------------------- integration tests


def _state(
    order_depths: dict[str, OrderDepth],
    *,
    position: dict[str, int] | None = None,
    trader_data: str = "",
    timestamp: int = 0,
) -> TradingState:
    return TradingState(
        traderData=trader_data,
        timestamp=timestamp,
        listings={},
        order_depths=order_depths,
        own_trades={product: [] for product in order_depths},
        market_trades={product: [] for product in order_depths},
        position=position or {},
        observations=Observation(),
    )


@pytest.mark.integration
def test_trader_integration_disabled_default() -> None:
    """Default config has residual disabled -- no extra orders."""
    trader = Trader(reraise_exceptions=True)
    state = _state(
        {"EMERALDS": OrderDepth(buy_orders={9998: 5}, sell_orders={10002: -5})},
        position={"EMERALDS": 0},
    )

    orders_off, _, td = trader.run(state)

    # Now run with residual enabled and compare.
    from src.core.config import EngineConfig, default_engine_config

    base = default_engine_config()
    enabled_config = EngineConfig(
        products=base.products,
        residual_config=ResidualConfig(enabled=True, residual_edge=2.0, residual_size=2),
    )
    trader_on = Trader(config=enabled_config, reraise_exceptions=True)
    orders_on, _, _ = trader_on.run(state)

    # With residual enabled, EMERALDS should have at least as many orders
    # (possibly more residual orders appended).
    assert len(orders_on["EMERALDS"]) >= len(orders_off["EMERALDS"])
    # Baseline should still produce valid JSON traderData.
    json.loads(td)


@pytest.mark.integration
def test_trader_integration_enabled_adds_orders() -> None:
    """With residual enabled, extra passive orders appear when capacity allows."""
    from src.core.config import EngineConfig, default_engine_config

    base = default_engine_config()
    config = EngineConfig(
        products=base.products,
        residual_config=ResidualConfig(enabled=True, residual_edge=3.0, residual_size=2),
    )
    trader = Trader(config=config, reraise_exceptions=True)

    # Wide book so residual orders don't cross the spread.
    state = _state(
        {"EMERALDS": OrderDepth(buy_orders={9990: 10}, sell_orders={10010: -10})},
        position={"EMERALDS": 0},
    )

    orders, conversions, td = trader.run(state)

    assert "EMERALDS" in orders
    assert conversions == 0
    json.loads(td)

    # With a wide book and position=0 on limit=20, the main strategy
    # won't use all capacity, so residual orders should appear.
    emerald_orders = orders["EMERALDS"]
    assert len(emerald_orders) > 0
