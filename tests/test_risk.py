"""Unit tests for ``src.core.risk``.

The risk manager owns the final word on what orders leave the trader.
These tests nail down per-side aggregate capacity clipping against
Prosperity's hard per-product position limits.
"""

from __future__ import annotations

import pytest

from src.core.risk import Capacity, RiskManager
from src.datamodel import Order


@pytest.mark.unit
def test_clip_orders_scales_buys_to_remaining_capacity() -> None:
    risk = RiskManager()
    orders = [
        Order("EMERALDS", 9998, 8),
        Order("EMERALDS", 9997, 7),
        Order("EMERALDS", 10002, -6),
    ]

    clipped = risk.clip_orders("EMERALDS", orders, current_position=15, limit=20)

    # Buy capacity is 5: first buy takes 5, second buy is dropped.
    # Sell capacity is 35: the -6 survives unchanged.
    assert [(o.price, o.quantity) for o in clipped] == [(9998, 5), (10002, -6)]


@pytest.mark.unit
def test_clip_orders_scales_sells_to_remaining_capacity() -> None:
    risk = RiskManager()
    orders = [
        Order("P", 100, -8),
        Order("P", 99, -7),
        Order("P", 101, 3),
    ]

    clipped = risk.clip_orders("P", orders, current_position=-15, limit=20)

    # Sell capacity = 20 + (-15) = 5. First sell takes 5, second is dropped.
    # Buy capacity = 20 - (-15) = 35, so the +3 survives.
    assert [(o.price, o.quantity) for o in clipped] == [(100, -5), (101, 3)]


@pytest.mark.unit
def test_clip_orders_drops_zero_quantity_inputs() -> None:
    risk = RiskManager()
    orders = [Order("P", 100, 0), Order("P", 101, 4)]
    clipped = risk.clip_orders("P", orders, current_position=0, limit=20)
    assert [(o.price, o.quantity) for o in clipped] == [(101, 4)]


@pytest.mark.unit
def test_clip_orders_raises_on_symbol_mismatch() -> None:
    risk = RiskManager()
    with pytest.raises(ValueError):
        risk.clip_orders("A", [Order("B", 100, 1)], current_position=0, limit=10)


@pytest.mark.unit
def test_clip_orders_raises_on_negative_limit() -> None:
    risk = RiskManager()
    with pytest.raises(ValueError):
        risk.clip_orders("P", [], current_position=0, limit=-1)


@pytest.mark.unit
def test_clip_orders_at_limit_drops_further_same_side_orders() -> None:
    risk = RiskManager()
    orders = [Order("P", 100, 5)]
    clipped = risk.clip_orders("P", orders, current_position=20, limit=20)
    assert clipped == []


@pytest.mark.unit
def test_capacity_helper_matches_individual_methods() -> None:
    risk = RiskManager()
    capacity = risk.capacity(position=7, limit=20)
    assert capacity == Capacity(buy=13, sell=27)
    assert RiskManager.remaining_buy_capacity(7, 20) == 13
    assert RiskManager.remaining_sell_capacity(7, 20) == 27


@pytest.mark.unit
def test_inventory_ratio_reports_signed_fraction() -> None:
    assert RiskManager.inventory_ratio(10, 20) == pytest.approx(0.5)
    assert RiskManager.inventory_ratio(-10, 20) == pytest.approx(-0.5)
    assert RiskManager.inventory_ratio(0, 0) == 0.0


@pytest.mark.unit
def test_clip_orders_handles_position_beyond_limit_gracefully() -> None:
    risk = RiskManager()
    # Position somehow exceeds limit: no further buys allowed, but selling
    # is allowed (in fact the sell capacity is increased).
    orders = [Order("P", 100, 3), Order("P", 99, -10)]
    clipped = risk.clip_orders("P", orders, current_position=25, limit=20)
    assert [(o.price, o.quantity) for o in clipped] == [(99, -10)]


# ---- Phase 1: Limit-80 worst-case legality tests ----


@pytest.mark.unit
def test_limit_80_long_exact_boundary_at_65() -> None:
    """At position 65, buy capacity=15 exactly fits taker(10)+maker(5)."""
    risk = RiskManager()
    orders = [Order("P", 100, 10), Order("P", 99, 5)]
    clipped = risk.clip_orders("P", orders, current_position=65, limit=80)
    assert [(o.price, o.quantity) for o in clipped] == [(100, 10), (99, 5)]


@pytest.mark.unit
def test_limit_80_long_clip_at_66() -> None:
    """At position 66, buy capacity=14 clips second order."""
    risk = RiskManager()
    orders = [Order("P", 100, 10), Order("P", 99, 5)]
    clipped = risk.clip_orders("P", orders, current_position=66, limit=80)
    assert [(o.price, o.quantity) for o in clipped] == [(100, 10), (99, 4)]


@pytest.mark.unit
def test_limit_80_long_minimal_at_78() -> None:
    """At position 78, buy capacity=2: only 2 units survive."""
    risk = RiskManager()
    orders = [Order("P", 100, 10), Order("P", 99, 5)]
    clipped = risk.clip_orders("P", orders, current_position=78, limit=80)
    assert [(o.price, o.quantity) for o in clipped] == [(100, 2)]


@pytest.mark.unit
def test_limit_80_short_exact_boundary_at_minus_65() -> None:
    """At position -65, sell capacity=15 exactly fits."""
    risk = RiskManager()
    orders = [Order("P", 100, -10), Order("P", 101, -5)]
    clipped = risk.clip_orders("P", orders, current_position=-65, limit=80)
    assert [(o.price, o.quantity) for o in clipped] == [(100, -10), (101, -5)]


@pytest.mark.unit
def test_limit_80_short_clip_at_minus_66() -> None:
    """At position -66, sell capacity=14 clips second order."""
    risk = RiskManager()
    orders = [Order("P", 100, -10), Order("P", 101, -5)]
    clipped = risk.clip_orders("P", orders, current_position=-66, limit=80)
    assert [(o.price, o.quantity) for o in clipped] == [(100, -10), (101, -4)]


@pytest.mark.unit
def test_limit_80_short_minimal_at_minus_78() -> None:
    """At position -78, sell capacity=2: only 2 units survive."""
    risk = RiskManager()
    orders = [Order("P", 100, -10), Order("P", 101, -5)]
    clipped = risk.clip_orders("P", orders, current_position=-78, limit=80)
    assert [(o.price, o.quantity) for o in clipped] == [(100, -2)]
