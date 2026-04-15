"""Unit tests for BuyAndHoldStrategy and round1_test_engine_config."""

from __future__ import annotations

import pytest

from src.core.config import (
    ProductConfig,
    round1_f5_engine_config,
    round1_test_engine_config,
)
from src.core.execution import ExecutionEngine
from src.core.risk import RiskManager
from src.core.types import BookLevel, NormalizedSnapshot, ProductMemory
from src.strategies import STRATEGY_REGISTRY
from src.strategies.base import StrategyContext
from src.strategies.buy_and_hold import BuyAndHoldStrategy


def _pepper_config() -> ProductConfig:
    pc = round1_test_engine_config().product_config("INTARIAN_PEPPER_ROOT")
    assert pc is not None
    return pc


def _snapshot(position: int) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product="INTARIAN_PEPPER_ROOT",
        timestamp=0,
        bids=(BookLevel(11990, 30),),
        asks=(BookLevel(12010, 30), BookLevel(12015, 10)),
        position=position,
    )


@pytest.mark.unit
def test_buy_and_hold_registered() -> None:
    """Strategy name ``buy_and_hold`` must resolve to BuyAndHoldStrategy."""
    factory = STRATEGY_REGISTRY.get("buy_and_hold")
    assert factory is BuyAndHoldStrategy


@pytest.mark.unit
def test_buy_and_hold_intent_never_sells() -> None:
    strategy = BuyAndHoldStrategy()
    context = StrategyContext(
        product="INTARIAN_PEPPER_ROOT",
        snapshot=_snapshot(position=0),
        memory=ProductMemory(),
        config=_pepper_config(),
    )
    intent = strategy.generate_intent(context)
    assert intent.buy_below is not None and intent.buy_below > 10_000
    assert intent.sell_above is None
    assert intent.mode == "taker"
    assert intent.rationale == "buy_and_hold"
    assert intent.quote is not None
    assert intent.quote.bid_size == 0
    assert intent.quote.ask_size == 0
    assert intent.quote.bid_price is None
    assert intent.quote.ask_price is None


@pytest.mark.unit
def test_buy_and_hold_produces_only_buy_orders_up_to_cap() -> None:
    """At position 0, emits a buy sweep up to max_aggressive_size; no sells."""
    config = _pepper_config()
    snap = _snapshot(position=0)
    intent = BuyAndHoldStrategy().generate_intent(
        StrategyContext(
            product=snap.product,
            snapshot=snap,
            memory=ProductMemory(),
            config=config,
        )
    )
    orders = ExecutionEngine().generate_orders(snap, intent, config)
    assert orders, "expected at least one buy order"
    assert all(order.quantity > 0 for order in orders), "never sells"
    total_buy = sum(order.quantity for order in orders)
    assert total_buy <= config.max_aggressive_size


@pytest.mark.unit
def test_buy_and_hold_stops_buying_at_limit() -> None:
    """Risk manager clips buys to limit - position (==0 at limit)."""
    config = _pepper_config()
    snap = _snapshot(position=config.position_limit)
    intent = BuyAndHoldStrategy().generate_intent(
        StrategyContext(
            product=snap.product,
            snapshot=snap,
            memory=ProductMemory(),
            config=config,
        )
    )
    raw = ExecutionEngine().generate_orders(snap, intent, config)
    clipped = RiskManager().clip_orders(
        product=snap.product,
        orders=raw,
        current_position=snap.position,
        limit=config.position_limit,
    )
    # At the limit, no additional buys allowed.
    total_buy = sum(o.quantity for o in clipped if o.quantity > 0)
    assert total_buy == 0


@pytest.mark.unit
def test_round1_test_factory_composition() -> None:
    """ASH leg matches F5; PEPPER leg switches to buy_and_hold."""
    test = round1_test_engine_config()
    f5 = round1_f5_engine_config()
    ash_test = test.product_config("ASH_COATED_OSMIUM")
    ash_f5 = f5.product_config("ASH_COATED_OSMIUM")
    assert ash_test is not None and ash_f5 is not None
    assert ash_test == ash_f5  # wall-based ASH shared

    pepper_test = test.product_config("INTARIAN_PEPPER_ROOT")
    assert pepper_test is not None
    assert pepper_test.strategy_name == "buy_and_hold"
    assert pepper_test.position_limit == 80
    # max_aggressive_size matches position_limit so one tick fills
    # the cap (buy-and-hold's contract).
    assert pepper_test.max_aggressive_size == pepper_test.position_limit


@pytest.mark.unit
def test_round1_test_variant_registered_in_exporter() -> None:
    from src.scripts.round_1.export_round1_submission import VARIANTS

    assert "test" in VARIANTS
    entry = VARIANTS["test"]
    assert entry["factory_name"] == "round1_test_engine_config"
    assert entry["factory"] is round1_test_engine_config
