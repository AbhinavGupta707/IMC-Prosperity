"""Unit tests for the hybrid bid (average-bid coupling) solver.

Regression check: P3-R3 bimodal reserve with cubic penalty recovers
optimal bids in the neighbourhood reported by top teams
(``high_bid`` in the 285-305 band, ``low_bid`` at the top of the lower
mode around 200).
"""

from __future__ import annotations

import pytest

from src.manual_rounds.bid_optimizer import BimodalUniformReserve, LinearRampReserve
from src.manual_rounds.hybrid_bid import (
    HybridScenario,
    average_bid_scale,
    hybrid_expected_pnl,
    optimize_hybrid,
)


@pytest.mark.unit
def test_scale_is_one_when_below_average() -> None:
    # mu below high bid means no penalty.
    assert average_bid_scale(resale_value=1000, high_bid=980, mu=970, alpha=1) == 1.0


@pytest.mark.unit
def test_scale_linear_vs_cubic_ordering() -> None:
    s_linear = average_bid_scale(1000, 970, 985, alpha=1)
    s_cubic = average_bid_scale(1000, 970, 985, alpha=3)
    assert 0 < s_cubic < s_linear < 1


@pytest.mark.unit
def test_hybrid_matches_non_hybrid_when_mu_below_high_bid() -> None:
    d = LinearRampReserve(low=900, high=1000)
    # When mu <= high_bid, scale is 1 and the hybrid reduces to the
    # plain two-bid PnL.
    plain = hybrid_expected_pnl(d, 1000, 950, 978, mu=970, alpha=1.0)
    # Manually compute equivalent plain two-bid PnL.
    low_part = (1000 - 950) * d.cdf(950)
    high_part = (1000 - 978) * (d.cdf(978) - d.cdf(950))
    assert plain == pytest.approx(low_part + high_part)


@pytest.mark.unit
def test_hybrid_penalises_below_average_bids() -> None:
    d = LinearRampReserve(low=900, high=1000)
    # Two candidate bid pairs: one with a low high-bid, one with a
    # high-bid that matches mu. Under a punitive penalty the lower pair
    # should do strictly worse per unit.
    lower_pair = hybrid_expected_pnl(d, 1000, 950, 970, mu=985, alpha=3)
    higher_pair = hybrid_expected_pnl(d, 1000, 950, 985, mu=985, alpha=3)
    assert higher_pair > lower_pair


@pytest.mark.unit
def test_p3_r3_cubic_penalty_pushes_bid_up() -> None:
    # Use the bimodal reserve with the cubic penalty to reproduce the
    # P3-R3 shape. The high bid should land above the individual
    # single-agent optimum (~284) once game theory kicks in.
    d = BimodalUniformReserve(low_a=160, high_a=200, low_b=250, high_b=320)
    scenarios = [
        HybridScenario("mu=280", 280),
        HybridScenario("mu=287", 287),
        HybridScenario("mu=293", 293),
    ]
    best, top = optimize_hybrid(
        distribution=d,
        resale_value=320,
        bid_grid=list(range(160, 321)),
        scenarios=scenarios,
        alpha=3.0,
        top_k=10,
    )
    # Low bid should settle near the top of the lower mode (200) because
    # bidding higher in the gap does nothing useful.
    assert 195 <= best.low_bid <= 200
    # High bid sits in the 285-305 region.
    assert 285 <= best.high_bid <= 310
    # Top-k list is sorted by worst-case PnL descending.
    assert all(
        top[i].worst_case_pnl >= top[i + 1].worst_case_pnl for i in range(len(top) - 1)
    )


@pytest.mark.unit
def test_scenarios_must_be_nonempty() -> None:
    d = LinearRampReserve(low=900, high=1000)
    with pytest.raises(ValueError):
        optimize_hybrid(
            distribution=d,
            resale_value=1000,
            bid_grid=[950, 960, 970],
            scenarios=[],
            alpha=1.0,
        )
