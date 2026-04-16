"""Smoke tests for src.analysis.calibration.strategy_replay.

Verifies the replay machinery loads a Trader, builds TradingStates,
and produces QuoteScore records with correct edges + markouts on a
tiny synthetic dataset.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.calibration.strategy_replay import (
    load_trader_class, replay_strategy,
)
from src.analysis.calibration.types import BookLevel, FactRow


_DUMMY_TRADER_SOURCE = '''
from datamodel import Order, OrderDepth, TradingState


class Trader:
    """Quotes one tick inside the visible bid/ask each tick."""

    def run(self, state: TradingState):
        orders = {}
        for product, ob in state.order_depths.items():
            ours = []
            if ob.buy_orders and ob.sell_orders:
                best_bid = max(ob.buy_orders)
                best_ask = min(ob.sell_orders)
                if best_ask - best_bid >= 2:
                    ours.append(Order(product, best_bid + 1, 1))
                    ours.append(Order(product, best_ask - 1, -1))
            if ours:
                orders[product] = ours
        return orders, 0, ""
'''


def _build_minimal_facts(n_ticks: int = 50) -> list[FactRow]:
    facts: list[FactRow] = []
    fv = 5000.0
    for tick in range(n_ticks):
        ts = tick * 100
        # Drift FV up by 0.1 per tick so markouts have a clear sign.
        fv += 0.1
        bid_price = int(fv) - 5
        ask_price = int(fv) + 5
        facts.append(FactRow(
            timestamp=ts, product="P", server_fv=fv,
            bids=(BookLevel(price=bid_price, volume=10),),
            asks=(BookLevel(price=ask_price, volume=10),),
            mid_price=fv, pnl=0.0,
        ))
    return facts


_BIG_BUYER_SOURCE = '''
from datamodel import Order, OrderDepth, TradingState


class Trader:
    """Tries to buy 100 every tick — should be rejected (limit 80)."""

    def run(self, state: TradingState):
        orders = {}
        for product, ob in state.order_depths.items():
            if ob.sell_orders:
                best_ask = min(ob.sell_orders.keys())
                orders[product] = [Order(product, best_ask, 100)]
        return orders, 0, ""
'''


def test_load_trader_class_from_inline_source(tmp_path: Path):
    src = tmp_path / "trader.py"
    src.write_text(_DUMMY_TRADER_SOURCE)
    cls = load_trader_class(src)
    assert cls is not None
    instance = cls()
    assert hasattr(instance, "run")


def test_replay_enforces_position_limit_rejecting_oversized_batch(tmp_path: Path):
    """P0-2 regression: a batch that would exceed position_limit in
    either direction must be rejected entirely (not partially filled).
    Matches generative_simulator semantics + IMC behavior.
    """
    src = tmp_path / "trader.py"
    src.write_text(_BIG_BUYER_SOURCE)
    cls = load_trader_class(src)
    facts = _build_minimal_facts(n_ticks=20)
    results = replay_strategy(
        trader_factory=cls,
        facts=facts,
        market_trades_by_ts={},
        products=("P",),
        position_limit=80,
    )
    r = results["P"]
    # Trader requested 100 every tick. Limit is 80. Every batch should be
    # rejected → 0 fills → 0 quote_scores recorded (the limit check fires
    # before quote_score collection).
    assert r.n_fills == 0, (
        f"P0-2: oversized buy batch should be rejected; got {r.n_fills} fills"
    )
    assert r.n_quotes == 0, (
        f"P0-2: rejected batch should produce no quote_scores; got {r.n_quotes}"
    )


def test_replay_emits_quote_scores_with_correct_signs(tmp_path: Path):
    src = tmp_path / "trader.py"
    src.write_text(_DUMMY_TRADER_SOURCE)
    cls = load_trader_class(src)
    facts = _build_minimal_facts(n_ticks=20)
    results = replay_strategy(
        trader_factory=cls,
        facts=facts,
        market_trades_by_ts={},
        products=("P",),
    )
    assert "P" in results
    r = results["P"]
    assert r.n_ticks == 20
    assert r.n_quotes > 0
    # Each tick produces a bid + ask quote (when spread >= 2).
    bids = [s for s in r.quote_scores if s.side == "bid"]
    asks = [s for s in r.quote_scores if s.side == "ask"]
    assert len(bids) > 0
    assert len(asks) > 0
    # Each bid_price = best_bid + 1 = (fv-5) + 1 = fv - 4.
    # edge_at_quote (bid) = fv - quote_price = fv - (fv-4) = +4 (favorable).
    bid_edges = [s.edge_at_quote for s in bids]
    assert all(e > 3 for e in bid_edges), (
        f"bid edges should be ~+4 (we quote inside bid), got {bid_edges[:5]}"
    )
    # Markout h1 for a bid = future_fv - quote_price.
    # FV drifts +0.1/tick so a quote at t with buy at fv-4 marks out positive.
    h1_filled_or_not = [s.markout_h1 for s in bids if s.markout_h1 is not None]
    if h1_filled_or_not:
        # All should be near +4.1 (favorable + drift).
        assert all(m > 3 for m in h1_filled_or_not)
