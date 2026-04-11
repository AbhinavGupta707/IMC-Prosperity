"""Unit tests for the news-portfolio integer QP solver.

Regression: with a tight L1 budget, the greedy shrinkage must match a
brute-force enumeration on small inputs. We also verify the
unconstrained optimum shape (``x* = K r / (2 f)``) for an easy case.
"""

from __future__ import annotations

from itertools import product

import pytest

from src.manual_rounds.news_portfolio import (
    NewsPayoff,
    Product,
    _marginal_last_unit,
    _unconstrained_integer_optimum,
    sensitivity_grid,
    solve,
)


def _brute_force_pnl(products: list[Product], payoff: NewsPayoff) -> float:
    """Reference implementation: enumerate all position vectors up to
    budget 5 on <= 4 products. Returns the optimal total PnL only --
    positions may be degenerate when the unconstrained optimum is a
    half-integer, so PnL is the meaningful thing to compare."""
    assert len(products) <= 4
    assert payoff.budget <= 5
    best_pnl = float("-inf")
    bounds = [range(-payoff.budget, payoff.budget + 1) for _ in products]
    K, f = payoff.capital_per_unit, payoff.fee_coefficient
    for combo in product(*bounds):
        if sum(abs(x) for x in combo) > payoff.budget:
            continue
        pnl = sum(
            K * p.expected_return * x - f * x * x
            for p, x in zip(products, combo, strict=True)
        )
        if pnl > best_pnl:
            best_pnl = pnl
    return best_pnl


@pytest.mark.unit
def test_unconstrained_optimum_matches_closed_form() -> None:
    payoff = NewsPayoff(capital_per_unit=10000, fee_coefficient=120, budget=100)
    # r = 0.05 => x* = 10000 * 0.05 / 240 = 2.083 -> round to 2.
    assert _unconstrained_integer_optimum(payoff, 0.05) == 2
    # r = -0.10 => x* = -4.17 -> round to -4.
    assert _unconstrained_integer_optimum(payoff, -0.10) == -4


@pytest.mark.unit
def test_unconstrained_fits_budget_no_shrinkage_needed() -> None:
    payoff = NewsPayoff(capital_per_unit=10000, fee_coefficient=120, budget=100)
    products = [
        Product("A", 0.05),
        Product("B", -0.05),
        Product("C", 0.02),
    ]
    sol = solve(products, payoff)
    assert sol.binding is False
    # Each small return is far from the L1 budget of 100.
    assert sol.budget_used <= 10


@pytest.mark.unit
def test_greedy_matches_brute_force_small_budget() -> None:
    # Use a tight budget so the L1 constraint binds and greedy
    # shrinkage is actually exercised.
    payoff = NewsPayoff(capital_per_unit=100, fee_coefficient=10, budget=3)
    products = [
        Product("A", 0.35),
        Product("B", -0.22),
        Product("C", 0.18),
        Product("D", -0.11),
    ]
    greedy = solve(products, payoff)
    reference_pnl = _brute_force_pnl(products, payoff)
    assert greedy.total_pnl == pytest.approx(reference_pnl)
    assert greedy.budget_used <= payoff.budget


@pytest.mark.unit
def test_marginal_last_unit_zero_for_empty_position() -> None:
    assert _marginal_last_unit(K=100, r=0.1, f=10, x=0) == 0.0


@pytest.mark.unit
def test_marginal_positive_for_optimal_positive_position() -> None:
    # Last unit of a positive, unconstrained-optimal position has
    # positive marginal -- otherwise we would not have taken it.
    assert _marginal_last_unit(K=100, r=0.3, f=10, x=1) > 0


@pytest.mark.unit
def test_binding_budget_flag() -> None:
    # Force binding: make every return strongly positive so the
    # unconstrained optimum blows the L1 budget.
    payoff = NewsPayoff(capital_per_unit=10000, fee_coefficient=10, budget=20)
    products = [
        Product("A", 0.5),
        Product("B", 0.4),
        Product("C", 0.35),
        Product("D", 0.3),
    ]
    sol = solve(products, payoff)
    assert sol.binding is True
    assert sol.budget_used == 20


@pytest.mark.unit
def test_total_pnl_matches_sum_of_pieces() -> None:
    payoff = NewsPayoff(capital_per_unit=10000, fee_coefficient=120, budget=100)
    products = [Product("A", 0.12), Product("B", -0.07), Product("C", 0.04)]
    sol = solve(products, payoff)
    assert sol.total_pnl == pytest.approx(sum(sol.pnl_by_product.values()))


@pytest.mark.unit
def test_sensitivity_grid_reports_expected_shape() -> None:
    payoff = NewsPayoff(capital_per_unit=10000, fee_coefficient=120, budget=100)
    products = [Product("A", 0.05), Product("B", -0.05)]
    grid = sensitivity_grid(products, payoff, delta=0.02, steps=2)
    assert set(grid.keys()) == {"A", "B"}
    assert len(grid["A"]) == 5  # -2..+2 inclusive
