"""Tests for trade_sampler: renewal-process arrivals + joint draws."""
from __future__ import annotations

import numpy as np
import pytest

from src.analysis.calibration.trade_sampler import TradeSampler
from src.analysis.calibration.types import BookLevel, FactRow, TradeRow


def _make_facts(n: int = 100, fv0: float = 5000.0) -> list[FactRow]:
    return [
        FactRow(
            timestamp=i * 100, product="P", server_fv=fv0,
            bids=(BookLevel(price=int(fv0 - 5), volume=10),),
            asks=(BookLevel(price=int(fv0 + 5), volume=10),),
            mid_price=fv0, pnl=0.0,
        )
        for i in range(n)
    ]


def _make_trade(ts: int, price: int, qty: int = 5) -> TradeRow:
    return TradeRow(
        timestamp=ts, product="P", price=price, quantity=qty,
        buyer=None, seller=None,
    )


def test_constructor_rejects_no_facts():
    with pytest.raises(ValueError, match="no facts"):
        TradeSampler(product="P", trades=[], facts=[])


def test_stats_with_no_trades_returns_zero_active_rate():
    sampler = TradeSampler(product="P", trades=[], facts=_make_facts(100))
    stats = sampler.stats
    assert stats.n_trades == 0
    assert stats.p_active_per_tick == 0.0


def test_stats_recovers_basic_metrics():
    facts = _make_facts(1000)
    # 50 trades sprinkled across the 1000 ticks
    trades = [_make_trade(ts=i * 2000, price=5005) for i in range(50)]
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    stats = sampler.stats
    assert stats.n_trades == 50
    # Active ticks: 50 trades, all unique tick indices (i*2000 // 100 = i*20)
    assert stats.p_active_per_tick == pytest.approx(50 / 1000)
    assert stats.n_unique_offsets >= 1


def test_sample_session_no_trades_returns_empty():
    sampler = TradeSampler(product="P", trades=[], facts=_make_facts(100))
    fv_path = np.full(100, 5000.0)
    result = sampler.sample_session(
        fv_path=fv_path, rng=np.random.default_rng(0),
    )
    assert result == []


def test_sample_session_arrival_rate_matches_input():
    """Empirical p_active should be reproduced in synthetic samples."""
    facts = _make_facts(10000)
    # Trades at every 25th tick → p_active = 1/25 = 0.04
    trades = [_make_trade(ts=i * 2500, price=5005) for i in range(400)]
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    fv_path = np.full(10000, 5000.0)
    syn = sampler.sample_session(fv_path=fv_path, rng=np.random.default_rng(42))
    # Synthetic count should be near 400 (within 20%).
    assert 320 <= len(syn) <= 480, f"got {len(syn)}, expected ~400"


def test_sample_session_offset_size_pairs_drawn_jointly():
    """Joint sampling should preserve offset-size correlation."""
    facts = _make_facts(1000)
    # 50 trades with small_size at small_offset, big_size at big_offset
    trades = []
    for i in range(25):
        # offset +1, size 2
        trades.append(_make_trade(ts=i * 4000, price=5001, qty=2))
    for i in range(25):
        # offset +5, size 10
        trades.append(_make_trade(ts=50000 + i * 4000, price=5005, qty=10))
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    fv_path = np.full(1000, 5000.0)
    syn = sampler.sample_session(
        fv_path=fv_path, rng=np.random.default_rng(0),
    )
    # All synthetic trades should be one of the two joint pairs.
    for t in syn:
        offset = t.price - 5000
        if offset == 1:
            assert t.quantity == 2, f"offset 1 should have qty 2, got {t.quantity}"
        elif offset == 5:
            assert t.quantity == 10, f"offset 5 should have qty 10, got {t.quantity}"
        else:
            pytest.fail(f"unexpected offset {offset}")


def test_sample_session_side_derived_from_offset_sign():
    facts = _make_facts(1000)
    trades = (
        [_make_trade(ts=i * 4000, price=5005) for i in range(25)]  # offset +5
        + [_make_trade(ts=50000 + i * 4000, price=4995) for i in range(25)]  # -5
    )
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    fv_path = np.full(1000, 5000.0)
    syn = sampler.sample_session(
        fv_path=fv_path, rng=np.random.default_rng(0),
    )
    for t in syn:
        offset = t.price - 5000
        if offset > 0:
            assert t.side == "buy"
        elif offset < 0:
            assert t.side == "sell"


def test_sample_session_deterministic_given_rng():
    facts = _make_facts(1000)
    trades = [_make_trade(ts=i * 1000, price=5005) for i in range(100)]
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    fv_path = np.full(1000, 5000.0)
    a = sampler.sample_session(fv_path=fv_path, rng=np.random.default_rng(7))
    b = sampler.sample_session(fv_path=fv_path, rng=np.random.default_rng(7))
    assert a == b


def test_sample_session_prices_anchored_to_fv_path():
    """Trade price = round(fv_path[tick] + offset). Verify with non-flat path."""
    facts = _make_facts(1000)
    trades = [_make_trade(ts=i * 100, price=5005) for i in range(20)]  # offset +5
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    # Non-flat synthetic FV path: fv = 5000 + tick * 1.0
    fv_path = np.array([5000.0 + i for i in range(1000)])
    syn = sampler.sample_session(
        fv_path=fv_path, rng=np.random.default_rng(0),
    )
    # Each synthetic trade's (price - fv_path[tick]) must be one of the
    # historical offsets (in this case, only +5).
    for t in syn:
        tick = t.timestamp // 100
        offset = t.price - fv_path[tick]
        assert abs(offset - 5) < 1e-6, (
            f"trade at t={t.timestamp}: price={t.price}, "
            f"fv={fv_path[tick]:.2f}, offset={offset:.4f} (expected +5)"
        )


def test_zero_offset_trades_get_side_not_unknown():
    """P0-3 regression: trades printed exactly at FV (offset=0) used
    to emit side='unknown' which the matcher silently dropped. They
    should now get a randomized 50/50 side so they participate in
    matching.
    """
    facts = _make_facts(1000)
    # All historical trades print at FV exactly (offset=0).
    trades = [_make_trade(ts=i * 4000, price=5000) for i in range(50)]
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    fv_path = np.full(1000, 5000.0)
    syn = sampler.sample_session(
        fv_path=fv_path, rng=np.random.default_rng(0),
    )
    assert len(syn) > 0, "expected synthetic trades to be emitted"
    sides = [t.side for t in syn]
    # No 'unknown' should appear.
    assert "unknown" not in sides, (
        f"P0-3 regression: zero-offset trade emitted side='unknown' "
        f"({sides[:5]})"
    )
    # Sides should be a mix of buy and sell (50/50 in expectation).
    assert "buy" in sides
    assert "sell" in sides


def test_sample_session_clusters_preserved_with_renewal_process():
    """If real gaps are clustered, synthetic gaps should be too."""
    facts = _make_facts(10000)
    # Build a clustered trade pattern: bursts of 5 consecutive ticks,
    # then 200-tick quiet, repeated.
    trades = []
    burst_start = 0
    while burst_start < 9500:
        for i in range(5):
            trades.append(_make_trade(
                ts=(burst_start + i) * 100, price=5005,
            ))
        burst_start += 200
    sampler = TradeSampler(product="P", trades=trades, facts=facts)
    fv_path = np.full(10000, 5000.0)
    syn = sampler.sample_session(
        fv_path=fv_path, rng=np.random.default_rng(0),
    )
    # Active synthetic ticks
    active = sorted({t.timestamp // 100 for t in syn})
    if len(active) < 10:
        return  # too few; can't compute gap stats meaningfully
    syn_gaps = np.diff(np.asarray(active))
    # Real gaps had a bimodal distribution (gap=1 within burst, gap=196 between bursts).
    # The synthetic should also show small gaps and large gaps.
    assert syn_gaps.min() == 1
    assert syn_gaps.max() >= 100, f"max syn gap {syn_gaps.max()} should reflect inter-burst gap"
