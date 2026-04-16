"""Tests for the generative_simulator orchestrator.

Verifies tick-loop semantics + reproducibility on tiny synthetic
configurations. Heavier validation (round-trip + marginal match) lives
in the Gate 1 / Gate 2 runners.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.analysis.calibration.bot_sampler import BookSampler
from src.analysis.calibration.fv_evolver import FVProcess
from src.analysis.calibration.generative_simulator import (
    SessionConfig, run_session,
)
from src.analysis.calibration.trade_sampler import TradeSampler
from src.analysis.calibration.types import BookLevel, FactRow, TradeRow


def _make_facts(n: int, fv: float = 5000.0) -> list[FactRow]:
    return [
        FactRow(
            timestamp=i * 100, product="P", server_fv=fv,
            bids=(BookLevel(price=int(fv) - 8, volume=10),
                  BookLevel(price=int(fv) - 10, volume=20)),
            asks=(BookLevel(price=int(fv) + 8, volume=10),
                  BookLevel(price=int(fv) + 10, volume=20)),
            mid_price=fv, pnl=0.0,
        )
        for i in range(n)
    ]


class _NoOpTrader:
    def run(self, state):
        return ({}, 0, "")


def _no_op_trader_factory():
    """Trader that emits no orders. Used for FV-only tests."""
    return _NoOpTrader()


def _aggressive_buyer_factory():
    """Trader that buys 1 unit at the best ask each tick."""
    from src.datamodel import Order

    class Buyer:
        def run(self, state):
            orders = {}
            for product, ob in state.order_depths.items():
                if ob.sell_orders:
                    best_ask = min(ob.sell_orders.keys())
                    orders[product] = [Order(product, best_ask, 1)]
            return (orders, 0, "")
    return Buyer()


def test_run_session_returns_correct_shape_with_no_op_trader():
    facts = _make_facts(100)
    fv_proc = FVProcess(sigma=0.1, drift=0.0, start_value=5000.0,
                        quantization_grid=None)
    config = SessionConfig(
        products=("P",), n_ticks=50,
        fv_processes={"P": fv_proc},
        book_samplers={"P": BookSampler(facts)},
        trade_samplers={"P": TradeSampler(product="P", trades=[], facts=facts)},
        seed=0,
    )
    result = run_session(config, trader_factory=_no_op_trader_factory)
    assert result.n_ticks == 50
    assert len(result.per_tick_equity) == 50
    assert len(result.per_tick_position["P"]) == 50
    assert result.final_pnl == 0.0
    # No-op trader → no fills.
    assert result.n_fills["P"] == 0


def test_run_session_deterministic_given_seed():
    facts = _make_facts(100)
    fv_proc = FVProcess(sigma=0.5, drift=0.0, start_value=5000.0,
                        quantization_grid=None)
    config = SessionConfig(
        products=("P",), n_ticks=100,
        fv_processes={"P": fv_proc},
        book_samplers={"P": BookSampler(facts)},
        trade_samplers={"P": TradeSampler(product="P", trades=[], facts=facts)},
        seed=42,
    )
    a = run_session(config, trader_factory=_aggressive_buyer_factory)
    b = run_session(config, trader_factory=_aggressive_buyer_factory)
    assert a.final_pnl == b.final_pnl
    assert a.per_tick_equity == b.per_tick_equity
    assert a.per_tick_position["P"] == b.per_tick_position["P"]


def test_aggressive_buyer_accumulates_position_until_limit():
    facts = _make_facts(200)
    fv_proc = FVProcess(sigma=0.0, drift=0.0, start_value=5000.0,
                        quantization_grid=None)
    config = SessionConfig(
        products=("P",), n_ticks=200,
        fv_processes={"P": fv_proc},
        book_samplers={"P": BookSampler(facts)},
        trade_samplers={"P": TradeSampler(product="P", trades=[], facts=facts)},
        position_limit=80,
        seed=0,
    )
    result = run_session(config, trader_factory=_aggressive_buyer_factory)
    # Should accumulate up to 80, then reject further buys.
    final_position = result.per_tick_position["P"][-1]
    assert final_position == 80
    # Subsequent rejected orders should be tracked.
    assert result.n_orders_rejected_limit["P"] >= 100


def test_position_limit_enforced_per_product():
    """Order batch that breaches limit should be REJECTED ENTIRELY."""
    facts = _make_facts(100)
    fv_proc = FVProcess(sigma=0.0, drift=0.0, start_value=5000.0,
                        quantization_grid=None)

    def big_buyer_factory():
        from src.datamodel import Order

        class Big:
            def run(self, state):
                orders = {}
                for product, ob in state.order_depths.items():
                    if ob.sell_orders:
                        best_ask = min(ob.sell_orders.keys())
                        orders[product] = [Order(product, best_ask, 100)]
                return (orders, 0, "")
        return Big()

    config = SessionConfig(
        products=("P",), n_ticks=10,
        fv_processes={"P": fv_proc},
        book_samplers={"P": BookSampler(facts)},
        trade_samplers={"P": TradeSampler(product="P", trades=[], facts=facts)},
        position_limit=80,
        seed=0,
    )
    result = run_session(config, trader_factory=big_buyer_factory)
    # All orders rejected → position stays 0.
    assert all(p == 0 for p in result.per_tick_position["P"])
    assert result.n_orders_rejected_limit["P"] == 10


def test_run_session_supports_multiple_products():
    facts_p = _make_facts(50, fv=5000.0)
    facts_q = _make_facts(50, fv=10000.0)
    # Rename product on facts for Q.
    facts_q = [
        FactRow(
            timestamp=f.timestamp, product="Q", server_fv=f.server_fv,
            bids=f.bids, asks=f.asks, mid_price=f.mid_price, pnl=f.pnl,
        )
        for f in facts_q
    ]
    fv_p = FVProcess(sigma=0.1, drift=0.0, start_value=5000.0, quantization_grid=None)
    fv_q = FVProcess(sigma=0.2, drift=0.0, start_value=10000.0, quantization_grid=None)
    config = SessionConfig(
        products=("P", "Q"), n_ticks=30,
        fv_processes={"P": fv_p, "Q": fv_q},
        book_samplers={"P": BookSampler(facts_p), "Q": BookSampler(facts_q)},
        trade_samplers={
            "P": TradeSampler(product="P", trades=[], facts=facts_p),
            "Q": TradeSampler(product="Q", trades=[], facts=facts_q),
        },
        seed=0,
    )
    result = run_session(config, trader_factory=_no_op_trader_factory)
    assert "P" in result.per_tick_position
    assert "Q" in result.per_tick_position
    assert "P" in result.per_tick_fv
    assert "Q" in result.per_tick_fv


def test_realized_alpha_recovered_for_known_drift_strategy():
    """Buy-and-hold under +drift should produce positive alpha + high R^2."""
    facts = _make_facts(500)
    # FV drifts UP by 0.1/tick → buy-and-hold appreciates.
    fv_proc = FVProcess(sigma=0.0, drift=0.1, start_value=5000.0,
                        quantization_grid=None)
    config = SessionConfig(
        products=("P",), n_ticks=500,
        fv_processes={"P": fv_proc},
        book_samplers={"P": BookSampler(facts)},
        trade_samplers={"P": TradeSampler(product="P", trades=[], facts=facts)},
        seed=0,
    )
    result = run_session(config, trader_factory=_aggressive_buyer_factory)
    # After 80 buys, position pinned at limit, equity grows linearly with FV.
    assert result.realized_alpha > 0, (
        f"expected positive alpha for buy+drift strategy, got {result.realized_alpha:.4f}"
    )


def test_passive_orders_do_not_persist_across_ticks():
    """If trader quotes a passive order at tick 0 and quotes nothing at
    tick 1, no fill should land at tick 1 even if a market trade
    arrives at the prior quote price.
    """
    facts = _make_facts(20)

    def one_shot_quoter_factory():
        """Quotes only at tick 0; silent thereafter."""
        from src.datamodel import Order

        class OneShot:
            def __init__(self):
                self._done = False

            def run(self, state):
                if self._done or state.timestamp != 0:
                    return ({}, 0, "")
                self._done = True
                return ({"P": [Order("P", 4990, 5)]}, 0, "")
        return OneShot()

    fv_proc = FVProcess(sigma=0.0, drift=0.0, start_value=5000.0,
                        quantization_grid=None)
    # Inject a market trade at tick 5 hitting price 4990.
    trade_at_4990 = TradeRow(
        timestamp=500, product="P", price=4990, quantity=3, buyer=None, seller=None,
    )
    config = SessionConfig(
        products=("P",), n_ticks=20,
        fv_processes={"P": fv_proc},
        book_samplers={"P": BookSampler(facts)},
        trade_samplers={
            "P": TradeSampler(product="P", trades=[trade_at_4990], facts=facts),
        },
        seed=0,
    )
    result = run_session(config, trader_factory=one_shot_quoter_factory)
    # Passive order from tick 0 should NOT persist to tick 5 → zero fills.
    # (Tick-0 order was not aggressive (5000-base_bid=4992 vs quote 4990) so it would
    # have queued passive → cleared at tick end → not present at tick 5.)
    assert result.n_fills["P"] == 0
