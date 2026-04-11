"""Unit tests for the Nash-crowd solver.

Regression check: the P3-R2 container grid (10 cells, 1 free pick +
50k second) reproduces the qualitative shape reported by top teams:

- The equilibrium is finite and stable.
- The best single pick is NOT the container with the largest multiplier
  -- top multipliers are dominated by mid cells once crowding is priced
  in.
- The best 2-pick bundle costs 50,000 and must clear that hurdle to be
  net-positive.
"""

from __future__ import annotations

import pytest

from src.manual_rounds.nash_crowd import (
    Bundle,
    CrowdCell,
    CrowdPayoff,
    evaluate_bundles,
    logit_quantal_equilibrium,
    sensitivity_sweep,
    solve,
)


def _p3_r2_cells() -> tuple[CrowdCell, ...]:
    # (multiplier, inhabitants) from TimoDiehm P3 README.
    raw = [
        ("C1", 10, 1),
        ("C2", 80, 6),
        ("C3", 37, 3),
        ("C4", 17, 1),
        ("C5", 31, 2),
        ("C6", 50, 4),
        ("C7", 89, 8),
        ("C8", 73, 4),
        ("C9", 20, 2),
        ("C10", 90, 10),
    ]
    return tuple(CrowdCell(name=name, multiplier=m, inhabitants=i) for name, m, i in raw)


@pytest.mark.unit
def test_cell_validation() -> None:
    with pytest.raises(ValueError):
        CrowdCell(name="bad", multiplier=0, inhabitants=1)
    with pytest.raises(ValueError):
        CrowdCell(name="bad", multiplier=10, inhabitants=0)


@pytest.mark.unit
def test_payoff_formula() -> None:
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    cell = CrowdCell(name="X", multiplier=50, inhabitants=4)
    # share = 0.05 -> ev = 10000 * 50 / (4 + 100 * 0.05) = 500000 / 9
    assert payoff.ev(cell, 0.05) == pytest.approx(500000 / 9)


@pytest.mark.unit
def test_logit_equilibrium_converges_on_simple_grid() -> None:
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    shares, iterations, converged = logit_quantal_equilibrium(cells, payoff)
    assert converged is True
    assert iterations >= 1
    assert sum(shares.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in shares.values())


@pytest.mark.unit
def test_p3_r2_single_pick_never_the_biggest_multiplier() -> None:
    # Under any reasonable prior with crowding, (90, 10) -- the headline
    # biggest multiplier -- should not be the best single pick.
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    sol = solve(cells, payoff, pick_fees=(0,), max_picks=1)
    assert sol.best_by_size[1].cells[0] != "C10"


@pytest.mark.unit
def test_second_pick_must_clear_fee() -> None:
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    sol = solve(cells, payoff, pick_fees=(0, 50_000), max_picks=2, top_k=30)
    single = sol.best_by_size[1]
    double = sol.best_by_size[2]
    # The double is either worse than the single (fee doesn't clear)
    # or its gross gain over the single exceeds the 50k fee.
    if double.net_ev > single.net_ev:
        assert double.gross_ev - single.gross_ev >= 50_000


@pytest.mark.unit
def test_sensitivity_sweep_reports_each_label() -> None:
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    uniform_shares = {c.name: 1.0 / len(cells) for c in cells}
    concentrated_shares = {c.name: 0.0 for c in cells}
    concentrated_shares["C7"] = 1.0
    results = sensitivity_sweep(
        cells,
        payoff,
        pick_fees=(0, 50_000),
        max_picks=2,
        share_variants=[("uniform", uniform_shares), ("allC7", concentrated_shares)],
    )
    assert set(results.keys()) == {"uniform", "allC7"}
    # Under concentrated-on-C7, the best single pick cannot be C7 (it's
    # maximally crowded).
    assert results["allC7"].best_by_size[1].cells[0] != "C7"


@pytest.mark.unit
def test_shares_override_must_cover_every_cell() -> None:
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    bad_override = {c.name: 1.0 for c in cells[:3]}  # missing 7 cells
    with pytest.raises(ValueError):
        solve(cells, payoff, pick_fees=(0,), max_picks=1, shares_override=bad_override)


@pytest.mark.unit
def test_pick_fees_length_must_match_max_picks() -> None:
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    with pytest.raises(ValueError):
        solve(cells, payoff, pick_fees=(0, 50_000), max_picks=1)


@pytest.mark.unit
def test_evaluate_bundles_returns_nonempty_top_k() -> None:
    cells = _p3_r2_cells()
    payoff = CrowdPayoff(base_treasure=10000, coupling=100)
    shares = {c.name: 1.0 / len(cells) for c in cells}
    best_by_size, top = evaluate_bundles(cells, payoff, shares, (0, 50_000), max_picks=2)
    assert 1 in best_by_size and 2 in best_by_size
    assert len(top) <= 10
    assert isinstance(top[0], Bundle)
