"""Unit tests for the single-agent bid optimizer.

Regression check: P2-R1 with the linear-ramp reserve on [900, 1000]
reproduces the canonical EV-optimal answer ``(952, 978)``.
"""

from __future__ import annotations

import pytest

from src.manual_rounds.bid_optimizer import (
    BimodalUniformReserve,
    LinearRampReserve,
    UniformReserve,
    one_bid_expected_pnl,
    optimize_one_bid,
    optimize_two_bids,
    two_bid_expected_pnl,
)


@pytest.mark.unit
def test_uniform_cdf_endpoints() -> None:
    d = UniformReserve(low=900, high=1000)
    assert d.cdf(800) == 0.0
    assert d.cdf(900) == 0.0
    assert d.cdf(950) == pytest.approx(0.5)
    assert d.cdf(1000) == 1.0
    assert d.cdf(1100) == 1.0


@pytest.mark.unit
def test_linear_ramp_integrates_to_one() -> None:
    d = LinearRampReserve(low=900, high=1000)
    assert d.cdf(900) == 0.0
    assert d.cdf(1000) == 1.0
    assert d.cdf(950) == pytest.approx(0.25)  # (50/100)^2


@pytest.mark.unit
def test_bimodal_skips_gap() -> None:
    d = BimodalUniformReserve(low_a=160, high_a=200, low_b=250, high_b=320)
    assert d.cdf(160) == 0.0
    assert d.cdf(180) == pytest.approx(0.25)  # mass_low * (20/40)
    assert d.cdf(220) == pytest.approx(0.5)  # flat through the gap
    assert d.cdf(280) == pytest.approx(0.5 + 0.5 * (30 / 70))
    assert d.cdf(320) == 1.0


@pytest.mark.unit
def test_p2_r1_two_bid_ev_optimal() -> None:
    # Prosperity 2 Round 1: linear reserve on [900, 1000], resale 1000.
    # Public solution: EV-optimal bids (952, 978).
    d = LinearRampReserve(low=900, high=1000)
    best, _ = optimize_two_bids(d, resale_value=1000, bid_grid=list(range(900, 1001)))
    assert (best.low_bid, best.high_bid) == (952, 978)


@pytest.mark.unit
def test_two_bid_ev_decomposes_into_low_plus_high_mass() -> None:
    d = UniformReserve(low=100, high=200)
    total = two_bid_expected_pnl(d, resale_value=200, low_bid=130, high_bid=160)
    low_part = one_bid_expected_pnl(d, resale_value=200, bid=130)
    high_part = (200 - 160) * (d.cdf(160) - d.cdf(130))
    assert total == pytest.approx(low_part + high_part)


@pytest.mark.unit
def test_optimize_one_bid_sorts_descending() -> None:
    d = LinearRampReserve(low=900, high=1000)
    best, top = optimize_one_bid(d, resale_value=1000, bid_grid=list(range(900, 1001)))
    assert top[0].expected_pnl_per_unit >= top[1].expected_pnl_per_unit
    assert best.bid == top[0].bid


@pytest.mark.unit
def test_bid_above_resale_is_always_zero() -> None:
    d = UniformReserve(low=0, high=100)
    assert one_bid_expected_pnl(d, resale_value=100, bid=100) == 0.0
    assert one_bid_expected_pnl(d, resale_value=100, bid=110) == 0.0
