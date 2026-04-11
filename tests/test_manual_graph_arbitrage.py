"""Unit tests for the graph-arbitrage solver.

Regression check: the P3-R1 FX matrix produces the canonical
Shell -> Snow -> SiNug -> Pizza -> Snow -> Shell path with ~8.9% return.
"""

from __future__ import annotations

import pytest

from src.manual_rounds.graph_arbitrage import RateMatrix, best_path


@pytest.fixture
def p3_r1_matrix() -> RateMatrix:
    # Prosperity 3 Round 1 rates. Rows are FROM, columns are TO.
    # Order: Snowballs, Pizza, Silicon Nuggets, SeaShells.
    rates = (
        (1.00, 1.45, 0.52, 0.72),
        (0.70, 1.00, 0.31, 0.48),
        (1.95, 3.10, 1.00, 1.49),
        (1.34, 1.98, 0.64, 1.00),
    )
    return RateMatrix(
        currencies=("Snow", "Pizza", "SiNug", "Shell"),
        rates=rates,
    )


@pytest.mark.unit
def test_p3_r1_best_path_matches_public_writeup(p3_r1_matrix: RateMatrix) -> None:
    best, top = best_path(p3_r1_matrix, start="Shell", end="Shell", max_hops=5, top_k=5)
    assert best.hops == ("Shell", "Snow", "SiNug", "Pizza", "Snow", "Shell")
    assert 1.088 < best.product < 1.090  # ~8.9% return
    assert top[0].product == best.product
    # All returned paths must start and end in Shell.
    for path in top:
        assert path.hops[0] == "Shell"
        assert path.hops[-1] == "Shell"


@pytest.mark.unit
def test_best_path_respects_max_hops(p3_r1_matrix: RateMatrix) -> None:
    # With only 2 hops (one intermediate) the best round trip is worse
    # than the 5-hop answer.
    short_best, _ = best_path(p3_r1_matrix, "Shell", "Shell", max_hops=2)
    long_best, _ = best_path(p3_r1_matrix, "Shell", "Shell", max_hops=5)
    assert short_best.product < long_best.product


@pytest.mark.unit
def test_rate_matrix_from_dict_matches_tuple_form() -> None:
    m = RateMatrix.from_dict(
        currencies=("A", "B"),
        rates={("A", "A"): 1.0, ("A", "B"): 2.0, ("B", "A"): 0.4, ("B", "B"): 1.0},
    )
    assert m.rate("A", "B") == 2.0
    assert m.rate("B", "A") == 0.4


@pytest.mark.unit
def test_rate_matrix_validation() -> None:
    with pytest.raises(ValueError):
        RateMatrix(currencies=("A",), rates=((1.0, 2.0),))  # wrong row width
    with pytest.raises(ValueError):
        RateMatrix(currencies=("A", "A"), rates=((1.0, 1.0), (1.0, 1.0)))  # dup
    with pytest.raises(ValueError):
        RateMatrix(currencies=("A", "B"), rates=((1.0, -0.5), (1.0, 1.0)))  # neg


@pytest.mark.unit
def test_best_path_requires_reachability() -> None:
    m = RateMatrix(
        currencies=("A", "B"),
        rates=((1.0, 0.0), (0.0, 1.0)),  # no cross-edges
    )
    with pytest.raises(ValueError):
        best_path(m, "A", "B", max_hops=5)
