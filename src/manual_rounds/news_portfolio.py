"""News-driven integer portfolio with quadratic fee.

Used in P1-R4, P2-R5, P3-R5. This is always the final manual round.

Problem shape::

    max_{x in Z^n}  sum_i  K * r_i * x_i  -  f * x_i^2
    subject to      sum_i |x_i| <= budget
                    -budget <= x_i <= budget

The per-product unconstrained optimum is ``x_i* = K * r_i / (2 * f)``.
If the unconstrained solution fits the L1 budget, it is also the
constrained optimum. Otherwise we greedily shrink positions by whichever
unit has the smallest marginal PnL contribution until the budget binds.

Greedy works here because each product's quadratic objective is strictly
concave: the marginal contribution of the last unit (going from ``|x|-1``
to ``|x|``) is monotonically decreasing in ``|x|``, so a greedy removal
is globally optimal for L1-constrained separable quadratic programs.

We keep this solver dependency-free (no scipy/cvxpy) so it can be run
offline with nothing but the stdlib, and so the math is auditable at
3am during a 72-hour manual round window.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """A single tradeable product in the news round.

    ``name`` is the IMC product name (e.g. "Haystacks"). ``expected_return``
    is your sentiment-derived directional estimate (use signed floats,
    e.g. +0.05 for +5%, -0.12 for -12%). ``rationale`` is a free-text
    field for the submission note; it is not used in the math.
    """

    name: str
    expected_return: float
    rationale: str = ""


@dataclass(frozen=True)
class NewsPayoff:
    """Configuration for the news portfolio round.

    ``capital_per_unit`` is ``K`` in the formula; historical values:
    P1 used 75, P2 used 7500, P3 used 10000.

    ``fee_coefficient`` is ``f``; P1 and P2 used 90, P3 used 120.

    ``budget`` is the L1 budget for |positions|. Every public round
    to date used 100 (percent points).
    """

    capital_per_unit: float
    fee_coefficient: float
    budget: int = 100

    def __post_init__(self) -> None:
        if self.capital_per_unit <= 0:
            raise ValueError("capital_per_unit must be > 0")
        if self.fee_coefficient <= 0:
            raise ValueError("fee_coefficient must be > 0")
        if self.budget < 1:
            raise ValueError("budget must be >= 1")


@dataclass(frozen=True)
class PortfolioSolution:
    positions: Mapping[str, int]
    pnl_by_product: Mapping[str, float]
    total_pnl: float
    budget_used: int
    unconstrained_positions: Mapping[str, int]
    binding: bool


def _pnl(K: float, r: float, f: float, x: int) -> float:
    return K * r * x - f * (x * x)


def _marginal_last_unit(K: float, r: float, f: float, x: int) -> float:
    """PnL contribution of the *last* unit, i.e. ``PnL(x) - PnL(x - sign(x))``.

    Removing that last unit costs the caller this amount (signed). A unit
    with a negative marginal contribution would already have been removed
    by the unconstrained optimum, so during greedy shrinking we only see
    non-negative marginals — we pick the smallest.
    """
    if x == 0:
        return 0.0
    if x > 0:
        return _pnl(K, r, f, x) - _pnl(K, r, f, x - 1)
    return _pnl(K, r, f, x) - _pnl(K, r, f, x + 1)


def _unconstrained_integer_optimum(payoff: NewsPayoff, r: float) -> int:
    raw = payoff.capital_per_unit * r / (2 * payoff.fee_coefficient)
    candidate = round(raw)
    # Clip to [-budget, +budget].
    if candidate > payoff.budget:
        return payoff.budget
    if candidate < -payoff.budget:
        return -payoff.budget
    return int(candidate)


def solve(
    products: Sequence[Product],
    payoff: NewsPayoff,
) -> PortfolioSolution:
    """Solve the news round as a separable integer QP with L1 budget.

    Strategy:

    1. Compute each product's unconstrained integer optimum by rounding
       ``K r / (2 f)``. Clip to ``[-budget, +budget]``.
    2. If the L1 sum already fits, we are done.
    3. Otherwise, repeatedly remove the unit whose marginal contribution
       is smallest in absolute value, walking the position toward zero
       one integer at a time, until the L1 sum equals the budget.
    """
    if not products:
        raise ValueError("products must be non-empty")

    unconstrained = {p.name: _unconstrained_integer_optimum(payoff, p.expected_return) for p in products}
    positions: dict[str, int] = dict(unconstrained)

    K = payoff.capital_per_unit
    f = payoff.fee_coefficient
    r_by_name = {p.name: p.expected_return for p in products}

    binding = False
    while sum(abs(x) for x in positions.values()) > payoff.budget:
        binding = True
        victim = min(
            (name for name, x in positions.items() if x != 0),
            key=lambda name: _marginal_last_unit(K, r_by_name[name], f, positions[name]),
        )
        if positions[victim] > 0:
            positions[victim] -= 1
        else:
            positions[victim] += 1

    pnl_by_product = {
        p.name: _pnl(K, r_by_name[p.name], f, positions[p.name]) for p in products
    }
    total = sum(pnl_by_product.values())
    budget_used = sum(abs(x) for x in positions.values())

    return PortfolioSolution(
        positions=positions,
        pnl_by_product=pnl_by_product,
        total_pnl=total,
        budget_used=budget_used,
        unconstrained_positions=unconstrained,
        binding=binding,
    )


def sensitivity_grid(
    products: Sequence[Product],
    payoff: NewsPayoff,
    delta: float = 0.02,
    steps: int = 3,
) -> dict[str, list[tuple[float, int]]]:
    """For each product, sweep its return by ``+/- delta * steps`` and
    report the resulting position.

    Useful for answering "which products' positions would flip sign if
    my sentiment was wrong by 2%?". A robust answer has positions that
    stay stable across the sweep.
    """
    out: dict[str, list[tuple[float, int]]] = {p.name: [] for p in products}
    base = {p.name: p.expected_return for p in products}
    for target in products:
        for i in range(-steps, steps + 1):
            shift = i * delta
            perturbed = tuple(
                Product(
                    name=p.name,
                    expected_return=(base[p.name] + shift) if p.name == target.name else base[p.name],
                )
                for p in products
            )
            sol = solve(perturbed, payoff)
            out[target.name].append((base[target.name] + shift, sol.positions[target.name]))
    return out
