"""Day-rollover history flush — Trader detects timestamp resets and
clears ``recent_mids`` / ``recent_spreads`` for products that opt in
via ``ProductConfig.flush_history_on_day_rollover=True``.

This is the Round-2 fix for PEPPER: each Prosperity day starts at
``timestamp=0`` and the inter-day anchor jumps ~+1 000. Without the
flush, ``linear_drift`` keeps the previous day's mids in its window
and mis-anchors for the first ~30 snapshots of the new day.

Coverage:
- Default (flag False) preserves Round-1 behaviour: history survives
  across the boundary.
- Flag True: history is cleared exactly when ``snapshot.timestamp``
  drops below the last seen value, and only then.
- Repeated calls inside the same day never trigger a flush.
- Cold start (no last_seen) does not trigger a flush.
- The ``last_seen_timestamp`` counter is updated regardless of the
  flag value, so flipping the flag mid-stream still works the next
  time a day rollover occurs.
"""

from __future__ import annotations

import pytest

from src.core.config import (
    EngineConfig,
    ProductConfig,
)
from src.core.types import EngineState, ProductMemory
from src.datamodel import Listing, Order, OrderDepth, TradingState
from src.trader import Trader


def _make_state(
    *,
    timestamp: int,
    bid: int = 99,
    ask: int = 101,
    bid_vol: int = 10,
    ask_vol: int = 10,
    trader_data: str = "",
    product: str = "PEPPER_TEST",
) -> TradingState:
    listings = {product: Listing(symbol=product, product=product, denomination="XIRECS")}
    depth = OrderDepth()
    depth.buy_orders = {bid: bid_vol}
    depth.sell_orders = {ask: -ask_vol}
    return TradingState(
        traderData=trader_data,
        timestamp=timestamp,
        listings=listings,
        order_depths={product: depth},
        own_trades={product: []},
        market_trades={product: []},
        position={product: 0},
        observations={},  # type: ignore[arg-type]
    )


def _engine_with_flag(*, flush: bool) -> EngineConfig:
    pc = ProductConfig(
        position_limit=80,
        strategy_name="market_making",
        fair_value_method="mid",
        fair_value_fallbacks=("microprice",),
        history_length=10,
        flush_history_on_day_rollover=flush,
    )
    return EngineConfig(products={"PEPPER_TEST": pc})


@pytest.mark.unit
def test_flush_disabled_default_preserves_history_across_rollover() -> None:
    trader = Trader(config=_engine_with_flag(flush=False))
    # Day 1: timestamps 0..400, accumulate four mids
    td = ""
    for ts in (0, 100, 200, 300, 400):
        _, _, td = trader.run(_make_state(timestamp=ts, bid=100, ask=102, trader_data=td))
    # Snapshot trader's view of memory after day 1
    state_after_day1 = trader.engine_state_from(td)
    mids_after_day1 = list(state_after_day1.products["PEPPER_TEST"].recent_mids)
    assert len(mids_after_day1) == 5

    # Day 2 begins (timestamp=0 < 400)
    _, _, td = trader.run(_make_state(timestamp=0, bid=200, ask=202, trader_data=td))
    state_after_rollover = trader.engine_state_from(td)
    mids_after_rollover = list(state_after_rollover.products["PEPPER_TEST"].recent_mids)
    # Default behaviour: previous-day mids retained (stale anchor risk).
    assert mids_after_rollover[:5] == mids_after_day1


@pytest.mark.unit
def test_flush_enabled_clears_history_on_rollover() -> None:
    trader = Trader(config=_engine_with_flag(flush=True))
    td = ""
    for ts in (0, 100, 200, 300, 400):
        _, _, td = trader.run(_make_state(timestamp=ts, bid=100, ask=102, trader_data=td))
    state_after_day1 = trader.engine_state_from(td)
    assert len(state_after_day1.products["PEPPER_TEST"].recent_mids) == 5

    # Day 2: timestamp=0 < 400 → flush before strategy runs, then this
    # snapshot's mid (201.0) is appended.
    _, _, td = trader.run(_make_state(timestamp=0, bid=200, ask=202, trader_data=td))
    state_after_rollover = trader.engine_state_from(td)
    mids = list(state_after_rollover.products["PEPPER_TEST"].recent_mids)
    assert mids == [201.0], (
        "after rollover the only retained mid should be the new day's "
        f"first snapshot mid; got {mids}"
    )


@pytest.mark.unit
def test_in_day_progression_never_triggers_flush() -> None:
    trader = Trader(config=_engine_with_flag(flush=True))
    td = ""
    for ts in (0, 100, 200, 300, 400):
        _, _, td = trader.run(_make_state(timestamp=ts, bid=100, ask=102, trader_data=td))
    state = trader.engine_state_from(td)
    assert len(state.products["PEPPER_TEST"].recent_mids) == 5
    # Same-timestamp re-entry (defensive — should not flush).
    _, _, td = trader.run(_make_state(timestamp=400, bid=100, ask=102, trader_data=td))
    state = trader.engine_state_from(td)
    assert len(state.products["PEPPER_TEST"].recent_mids) == 6


@pytest.mark.unit
def test_cold_start_with_flag_enabled_does_not_flush() -> None:
    trader = Trader(config=_engine_with_flag(flush=True))
    # First call ever: no last_seen_timestamp → flush must NOT fire.
    _, _, td = trader.run(_make_state(timestamp=0, bid=100, ask=102))
    state = trader.engine_state_from(td)
    mids = list(state.products["PEPPER_TEST"].recent_mids)
    assert mids == [101.0]


@pytest.mark.unit
def test_helper_is_idempotent_when_called_directly() -> None:
    """Direct unit on the static helper — defensive coverage in case
    the trader call site is later refactored.
    """
    pc = ProductConfig(
        position_limit=80,
        strategy_name="market_making",
        fair_value_method="mid",
        flush_history_on_day_rollover=True,
    )
    memory = ProductMemory()
    memory.recent_mids[:] = [100.0, 101.0, 102.0]
    memory.recent_spreads[:] = [2.0, 2.0, 2.0]
    memory.counters["last_seen_timestamp"] = 400
    snap = _make_state(timestamp=0).order_depths["PEPPER_TEST"]
    # Build a NormalizedSnapshot via MarketDataAdapter for realism
    from src.core.market_data import MarketDataAdapter

    adapter = MarketDataAdapter()
    snapshots = adapter.normalize_state(_make_state(timestamp=0))
    snap_norm = snapshots["PEPPER_TEST"]

    Trader._maybe_flush_for_day_rollover(
        memory=memory, snapshot=snap_norm, product_config=pc
    )
    assert memory.recent_mids == []
    assert memory.recent_spreads == []
    assert memory.counters["last_seen_timestamp"] == 400  # left for trader to update

    # Idempotent: calling again with no new last_seen update is a no-op.
    Trader._maybe_flush_for_day_rollover(
        memory=memory, snapshot=snap_norm, product_config=pc
    )
    assert memory.recent_mids == []


@pytest.mark.unit
def test_flag_false_skips_flush_even_after_rollover() -> None:
    pc = ProductConfig(
        position_limit=80,
        strategy_name="market_making",
        fair_value_method="mid",
        flush_history_on_day_rollover=False,
    )
    memory = ProductMemory()
    memory.recent_mids[:] = [100.0, 101.0]
    memory.counters["last_seen_timestamp"] = 999
    from src.core.market_data import MarketDataAdapter

    snapshots = MarketDataAdapter().normalize_state(_make_state(timestamp=0))
    Trader._maybe_flush_for_day_rollover(
        memory=memory,
        snapshot=snapshots["PEPPER_TEST"],
        product_config=pc,
    )
    assert memory.recent_mids == [100.0, 101.0]
