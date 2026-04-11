"""Unit tests for ``src.core.signals.SignalEngine``."""

from __future__ import annotations

import pytest

from src.core.config import ProductConfig
from src.core.signals import SignalEngine
from src.core.types import BookLevel, FairValueEstimate, NormalizedSnapshot


def _config(position_limit: int = 20, flatten_threshold: float = 0.75) -> ProductConfig:
    return ProductConfig(
        position_limit=position_limit,
        strategy_name="stable_anchor",
        fair_value_method="anchor",
        anchor_price=10_000.0,
        taker_edge=1.0,
        maker_edge=2.0,
        quote_size=5,
        max_aggressive_size=10,
        inventory_skew=2.0,
        flatten_threshold=flatten_threshold,
    )


def _snapshot(position: int) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        product="P",
        timestamp=0,
        bids=(BookLevel(9992, 15),),
        asks=(BookLevel(10008, 15),),
        position=position,
    )


def _fair() -> FairValueEstimate:
    return FairValueEstimate(price=10_000.0, method="anchor")


@pytest.mark.unit
def test_neutral_position_produces_hybrid_mode_with_buy_and_sell_intents() -> None:
    engine = SignalEngine()
    intent = engine.build_market_making_intent("P", _snapshot(0), _fair(), _config())
    assert intent.mode == "hybrid"
    assert intent.buy_below is not None
    assert intent.sell_above is not None
    assert intent.quote is not None
    assert intent.quote.bid_size > 0
    assert intent.quote.ask_size > 0


@pytest.mark.unit
def test_long_at_flatten_threshold_disables_buy_side_entirely() -> None:
    engine = SignalEngine()
    # 0.75 * 20 = 15 -> position 15 hits the threshold.
    intent = engine.build_market_making_intent("P", _snapshot(15), _fair(), _config())
    assert intent.mode == "recovery"
    assert intent.buy_below is None
    assert intent.quote is not None
    assert intent.quote.bid_size == 0
    assert intent.quote.bid_price is None
    # Ask should still be alive and pulled in toward fair value.
    assert intent.quote.ask_size > 0
    assert intent.quote.ask_price is not None
    assert intent.quote.ask_price <= 10_000


@pytest.mark.unit
def test_short_at_flatten_threshold_disables_sell_side_entirely() -> None:
    engine = SignalEngine()
    intent = engine.build_market_making_intent("P", _snapshot(-15), _fair(), _config())
    assert intent.mode == "recovery"
    assert intent.sell_above is None
    assert intent.quote is not None
    assert intent.quote.ask_size == 0
    assert intent.quote.ask_price is None
    assert intent.quote.bid_size > 0
    assert intent.quote.bid_price is not None
    assert intent.quote.bid_price >= 10_000


@pytest.mark.unit
def test_mild_position_still_skews_but_does_not_flatten() -> None:
    engine = SignalEngine()
    intent = engine.build_market_making_intent(
        "P", _snapshot(5), _fair(), _config(flatten_threshold=0.9)
    )
    assert intent.mode == "hybrid"
    assert intent.buy_below is not None
    assert intent.sell_above is not None
