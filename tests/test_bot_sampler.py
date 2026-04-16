"""Tests for bot_sampler: empirical conditional book sampling."""
from __future__ import annotations

import numpy as np
import pytest

from src.analysis.calibration.bot_sampler import (
    BookSampler, _bucket_for, _reanchor,
)
from src.analysis.calibration.types import BookLevel, FactRow


def _make_fact(
    *,
    fv: float = 5000.0,
    bid_offsets: tuple[int, ...] = (-8,),
    ask_offsets: tuple[int, ...] = (+8,),
    bid_volumes: tuple[int, ...] = (10,),
    ask_volumes: tuple[int, ...] = (10,),
    timestamp: int = 0,
) -> FactRow:
    bids = tuple(
        BookLevel(price=int(round(fv + off)), volume=v)
        for off, v in zip(bid_offsets, bid_volumes)
    )
    asks = tuple(
        BookLevel(price=int(round(fv + off)), volume=v)
        for off, v in zip(ask_offsets, ask_volumes)
    )
    return FactRow(
        timestamp=timestamp, product="P", server_fv=fv,
        bids=bids, asks=asks, mid_price=fv, pnl=0.0,
    )


def test_constructor_rejects_empty_facts():
    with pytest.raises(ValueError, match="at least one"):
        BookSampler([])


def test_constructor_rejects_zero_buckets():
    with pytest.raises(ValueError, match="positive"):
        BookSampler([_make_fact()], n_frac_buckets=0)


def test_bucket_for_simple_cases():
    assert _bucket_for(5000.0, 10) == 0
    assert _bucket_for(5000.05, 10) == 0
    assert _bucket_for(5000.5, 10) == 5
    assert _bucket_for(5000.99, 10) == 9
    # Boundary clamp
    assert _bucket_for(5000.999999, 10) == 9


def test_bucket_for_negative_fv():
    """Frac of negative FVs handled via positive modulo."""
    # -5000.5 has frac = 0.5 (using floor convention)
    assert _bucket_for(-5000.5, 10) == 5


def test_reanchor_preserves_offsets():
    fact = _make_fact(fv=5000.0, bid_offsets=(-8,), ask_offsets=(+8,))
    new_bids, new_asks = _reanchor(fact, new_fv=10000.0)
    assert new_bids[0].price == 9992
    assert new_asks[0].price == 10008
    assert new_bids[0].volume == fact.bids[0].volume


def test_reanchor_preserves_multi_level_structure():
    fact = _make_fact(
        fv=5000.0,
        bid_offsets=(-7, -10),
        ask_offsets=(+6, +10),
        bid_volumes=(10, 20),
        ask_volumes=(8, 25),
    )
    new_bids, new_asks = _reanchor(fact, new_fv=5050.0)
    assert [b.price for b in new_bids] == [5043, 5040]
    assert [a.price for a in new_asks] == [5056, 5060]
    assert [b.volume for b in new_bids] == [10, 20]
    assert [a.volume for a in new_asks] == [8, 25]


def test_sample_book_deterministic_given_rng():
    facts = [_make_fact(fv=5000.0 + i * 0.1) for i in range(50)]
    sampler = BookSampler(facts)
    a = sampler.sample_book(fv=5000.0, rng=np.random.default_rng(42))
    b = sampler.sample_book(fv=5000.0, rng=np.random.default_rng(42))
    assert a == b


def test_sample_book_returns_correct_types():
    sampler = BookSampler([_make_fact()])
    bids, asks = sampler.sample_book(fv=5000.0, rng=np.random.default_rng(0))
    assert isinstance(bids, tuple)
    assert isinstance(asks, tuple)
    assert all(isinstance(b, BookLevel) for b in bids)
    assert all(isinstance(a, BookLevel) for a in asks)


def test_sample_book_falls_back_to_nearest_populated_bucket():
    """Bucket 5 is empty; FV at bucket-5 should sample from bucket 4 or 6."""
    # Populate only bucket 0 and bucket 9.
    facts = [
        _make_fact(fv=5000.0 + 0.05),   # bucket 0
        _make_fact(fv=5000.0 + 0.95),   # bucket 9
    ]
    sampler = BookSampler(facts)
    # Sample at FV with frac = 0.5 (bucket 5).
    bids, asks = sampler.sample_book(
        fv=5000.5, rng=np.random.default_rng(0),
    )
    # Should not raise; returns a valid book from a fallback bucket.
    assert bids and asks


def test_sample_distribution_matches_input_per_rank_at_same_fv():
    """Statistical: at fixed FV, sampled offsets match input distribution."""
    rng_init = np.random.default_rng(123)
    # Build 1000 facts with bid offsets drawn from {-7, -8, -10}
    # (probabilities 0.5, 0.3, 0.2) and ask offsets from {+6, +8} (0.6, 0.4).
    bid_pool = [-7] * 500 + [-8] * 300 + [-10] * 200
    ask_pool = [+6] * 600 + [+8] * 400
    rng_init.shuffle(bid_pool)
    rng_init.shuffle(ask_pool)
    facts = [
        _make_fact(
            fv=5000.0,  # all in bucket 0
            bid_offsets=(bid_pool[i],),
            ask_offsets=(ask_pool[i],),
        )
        for i in range(1000)
    ]
    sampler = BookSampler(facts)
    rng = np.random.default_rng(456)
    samples = [
        sampler.sample_book(fv=5000.0, rng=rng) for _ in range(10000)
    ]
    sampled_bid_offsets = [b[0][0].price - 5000 for b in samples]
    sampled_ask_offsets = [b[1][0].price - 5000 for b in samples]
    # Frequencies should match input proportions within 2% tolerance.
    bid_minus7 = sum(1 for o in sampled_bid_offsets if o == -7) / 10000
    bid_minus8 = sum(1 for o in sampled_bid_offsets if o == -8) / 10000
    bid_minus10 = sum(1 for o in sampled_bid_offsets if o == -10) / 10000
    assert abs(bid_minus7 - 0.50) < 0.02, f"bid -7 freq {bid_minus7:.3f}"
    assert abs(bid_minus8 - 0.30) < 0.02, f"bid -8 freq {bid_minus8:.3f}"
    assert abs(bid_minus10 - 0.20) < 0.02, f"bid -10 freq {bid_minus10:.3f}"
    ask_plus6 = sum(1 for o in sampled_ask_offsets if o == +6) / 10000
    ask_plus8 = sum(1 for o in sampled_ask_offsets if o == +8) / 10000
    assert abs(ask_plus6 - 0.60) < 0.02, f"ask +6 freq {ask_plus6:.3f}"
    assert abs(ask_plus8 - 0.40) < 0.02, f"ask +8 freq {ask_plus8:.3f}"


def test_stats_reports_bucket_populations():
    facts = [
        _make_fact(fv=5000.0),  # bucket 0
        _make_fact(fv=5000.5),  # bucket 5
        _make_fact(fv=5000.5),  # bucket 5
    ]
    sampler = BookSampler(facts, n_frac_buckets=10)
    stats = sampler.stats
    assert stats.n_buckets == 10
    assert stats.n_facts_total == 3
    assert stats.bucket_populations[0] == 1
    assert stats.bucket_populations[5] == 2
    assert 1 in stats.empty_bucket_indices
    assert 5 not in stats.empty_bucket_indices


def test_sample_book_at_distant_fv_translates_correctly():
    """Sample at FV far from any historical FV; translation must be exact."""
    facts = [
        _make_fact(fv=5000.0, bid_offsets=(-8,), ask_offsets=(+8,))
        for _ in range(10)
    ]
    sampler = BookSampler(facts)
    rng = np.random.default_rng(0)
    bids, asks = sampler.sample_book(fv=20000.0, rng=rng)
    # Offset preserved exactly.
    assert bids[0].price == 19992
    assert asks[0].price == 20008
