"""Tests for the R3+ persistence foundation (Commit 1 of the wiring plan).

Scope:
- StrategyContext optional ``portfolio`` / ``signal_bus`` fields (non-breaking)
- EngineState.engines dict + for_engine / set_engine_state helpers
- StateStore round-trip of engines field
- StateStore budget-tiered truncation preserves engine state over product memory
"""

from __future__ import annotations

import pytest

from src.core.config import ProductConfig
from src.core.state_store import StateStore
from src.core.types import EngineState, NormalizedSnapshot, ProductMemory
from src.strategies.base import StrategyContext


# ============================================================= StrategyContext


@pytest.mark.unit
def test_strategy_context_constructible_without_portfolio_or_bus():
    """Legacy single-product strategies must not break. Default fields are None."""
    ctx = StrategyContext(
        product="TEST",
        snapshot=NormalizedSnapshot(product="TEST", timestamp=0),
        memory=ProductMemory(),
        config=ProductConfig(
            position_limit=10, strategy_name="market_making", fair_value_method="mid",
        ),
    )
    assert ctx.portfolio is None
    assert ctx.signal_bus is None


@pytest.mark.unit
def test_strategy_context_accepts_optional_portfolio_and_bus():
    """R3+ strategies can opt in to cross-product / signal-aware context."""
    from src.core.primitives.portfolio_context import (
        PortfolioSnapshot,
        build_portfolio_snapshot,
    )
    from src.core.primitives.signal_bus import SignalBus

    portfolio = build_portfolio_snapshot(
        timestamp=0, snapshots={}, position_limits={},
    )
    bus = SignalBus()
    ctx = StrategyContext(
        product="TEST",
        snapshot=NormalizedSnapshot(product="TEST", timestamp=0),
        memory=ProductMemory(),
        config=ProductConfig(
            position_limit=10, strategy_name="market_making", fair_value_method="mid",
        ),
        portfolio=portfolio,
        signal_bus=bus,
    )
    assert ctx.portfolio is portfolio
    assert ctx.signal_bus is bus


# ============================================================= EngineState


@pytest.mark.unit
def test_engine_state_default_engines_is_empty_dict():
    state = EngineState()
    assert state.engines == {}


@pytest.mark.unit
def test_engine_state_for_engine_auto_creates_blob():
    state = EngineState()
    blob = state.for_engine("basket_b1")
    assert blob == {}
    assert "basket_b1" in state.engines
    # Second call returns the same blob (same identity).
    assert state.for_engine("basket_b1") is blob


@pytest.mark.unit
def test_engine_state_set_overwrites():
    state = EngineState()
    state.set_engine_state("e1", {"mean": 100.0, "n": 5})
    assert state.engines["e1"] == {"mean": 100.0, "n": 5}
    state.set_engine_state("e1", {"mean": 50.0, "n": 3})
    assert state.engines["e1"] == {"mean": 50.0, "n": 3}


# ============================================================= StateStore


@pytest.mark.unit
def test_statestore_roundtrip_engines_field():
    store = StateStore(version=1, max_chars=50_000)
    state = EngineState(version=1)
    state.set_engine_state("b1_arb", {"mean": 123.4, "n": 10})
    state.set_engine_state("options_rock", {"smile": {"9500": 0.20}})

    blob = store.save(state)
    restored = store.load(blob)

    assert restored.engines["b1_arb"] == {"mean": 123.4, "n": 10}
    assert restored.engines["options_rock"] == {"smile": {"9500": 0.20}}


@pytest.mark.unit
def test_statestore_handles_missing_engines_key_for_legacy_payloads():
    """Old traderData blobs have no 'engines' key — must deserialize cleanly."""
    legacy = '{"version":1,"products":{}}'
    store = StateStore(version=1)
    state = store.load(legacy)
    assert state.engines == {}


@pytest.mark.unit
def test_statestore_ignores_malformed_engines_entries():
    """Garbage engine entries must not crash the loader."""
    malformed = (
        '{"version":1,"products":{},'
        '"engines":{"valid":{"x":1},"bad_num":42,"bad_list":[1,2]}}'
    )
    store = StateStore(version=1)
    state = store.load(malformed)
    assert state.engines == {"valid": {"x": 1}}


@pytest.mark.unit
def test_statestore_tiered_budget_preserves_engines_over_product_memory():
    """Under budget pressure, engine state must be preserved even when
    product memory is truncated (engines have expensive cold-start)."""
    store = StateStore(version=1, max_chars=500)  # tiny budget
    state = EngineState(version=1)
    # Huge product memory that will exceed budget.
    state.products["BIG"] = ProductMemory(
        recent_mids=[float(i) for i in range(200)],
        recent_spreads=[float(i) for i in range(200)],
    )
    # Small engine state.
    state.set_engine_state("e1", {"critical": "preserve_me"})

    blob = store.save(state)
    assert len(blob) <= 500

    restored = store.load(blob)
    # Engine state survives.
    assert "e1" in restored.engines
    assert restored.engines["e1"]["critical"] == "preserve_me"
    # Product memory may have been truncated or dropped — that's OK.


@pytest.mark.unit
def test_statestore_tier_4_drops_everything_if_engines_overflow():
    """If even engine state can't fit, fall back to empty payload gracefully."""
    store = StateStore(version=1, max_chars=100)  # absurdly tight
    state = EngineState(version=1)
    # Engine state that alone exceeds 100 chars.
    state.set_engine_state("e1", {"payload": "x" * 200})

    blob = store.save(state)
    assert len(blob) <= 100
    # Must be deserializable.
    restored = store.load(blob)
    # Engine state was dropped under extreme pressure.
    assert restored.engines == {} or "e1" not in restored.engines


@pytest.mark.unit
def test_statestore_save_is_json_valid():
    import json

    store = StateStore(version=1)
    state = EngineState(version=1)
    state.set_engine_state("e1", {"a": 1, "b": [1.0, 2.0], "c": "str"})
    blob = store.save(state)
    parsed = json.loads(blob)
    assert parsed["engines"]["e1"]["a"] == 1
