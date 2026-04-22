"""Invest & Expand manual round solver (P4-R2 family).

Problem
-------
Allocate integer percentages ``(r, s, v)`` with ``0 <= r,s,v`` and
``r + s + v <= 100``. Budget is 50 000 XIREC; cost per % is 500.

- ``research(r) = 200_000 * ln(1+r) / ln(101)``   (concave, 0 -> 200k)
- ``scale(s)   = 7 * s / 100``                     (linear, 0 -> 7)
- ``speed(v)   = rank-based mu``, linearly spread from 0.9 (rank 1)
  to 0.1 (rank N) across all submitting teams, where N includes *you*.
  Ties share the *best* rank in their tied block (example in rules:
  investments ``70,70,70,50,40,40,30`` -> ranks ``1,1,1,4,5,5,7``).

- ``gross_pnl = research(r) * scale(s) * mu``
- ``net_pnl  = gross_pnl - 500 * (r + s + v)``

Doctrine
--------
1. The game-theoretic content is entirely in ``v``. Given a realised
   multiplier ``mu``, the ``(r, s)`` choice is a deterministic concave
   optimisation with a closed-form FOC: at an interior optimum with
   the full remaining budget spent, ``s = (1+r) * ln(1+r)``.

2. Under the tie rule + large N, your multiplier collapses to a
   percentile expression::

       mu(v_you) ~ 0.9 - 0.8 * P(v_opp > v_you)

   with ``P(v_opp > v_you)`` taken under your prior on the opponent
   v-distribution. Because PnL is linear in mu,
   ``E[PnL] = research(r) * scale(s) * E[mu] - costs``; there is no
   need to Monte-Carlo over distributions-over-distributions.

3. Integer-percent inputs force massive ties. If 30% of the field
   plays ``v = 0``, they all tie at rank ``M_above + 1`` where
   ``M_above`` is the count of opponents with ``v > 0``. This makes
   popular integers (0, 33, 50) natural Schelling points.

4. All funcs are stdlib-only + ``math``, mirror the ``nash_crowd`` /
   ``bid_optimizer`` style so the module is auditable under time
   pressure.

References: ``nash_crowd`` (Family 3) and ``priors``. This module is
Family-3-adjacent but introduces a rank-auction dimension.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

PILLAR_COST = 500  # XIREC per 1%
BUDGET_TOTAL = 50_000  # XIREC
MAX_PCT = 100
RESEARCH_CAP = 200_000
RESEARCH_DENOM = math.log(1 + MAX_PCT)  # ln(101)
SCALE_CAP = 7
MU_MAX = 0.9
MU_MIN = 0.1


def research(r: int | float) -> float:
    """Research edge. Concave log, 0 -> 200k on r in [0, 100]."""
    if r < 0:
        raise ValueError(f"r must be >= 0, got {r}")
    return RESEARCH_CAP * math.log(1 + r) / RESEARCH_DENOM


def scale(s: int | float) -> float:
    """Scale. Linear 0 -> 7 on s in [0, 100]."""
    if s < 0:
        raise ValueError(f"s must be >= 0, got {s}")
    return SCALE_CAP * s / MAX_PCT


def multiplier(rank: int, n_total: int) -> float:
    """Speed multiplier from 1-indexed rank in a field of ``n_total``.

    ``rank=1`` -> 0.9, ``rank=n_total`` -> 0.1, linear in rank.
    If ``n_total == 1`` the single submitter is awarded 0.9.
    """
    if rank < 1 or rank > n_total:
        raise ValueError(f"rank {rank} outside [1, {n_total}]")
    if n_total <= 1:
        return MU_MAX
    return MU_MAX - (rank - 1) * (MU_MAX - MU_MIN) / (n_total - 1)


@dataclass(frozen=True)
class Allocation:
    """Immutable (r, s, v) integer allocation.

    Raises on invalid inputs so we fail loudly if a caller mis-types a
    fraction as a percent or forgets the 100% budget cap.
    """

    r: int
    s: int
    v: int

    def __post_init__(self) -> None:
        for name, val in (("r", self.r), ("s", self.s), ("v", self.v)):
            if not isinstance(val, int):
                raise TypeError(f"{name} must be int, got {type(val).__name__}")
            if val < 0 or val > MAX_PCT:
                raise ValueError(f"{name}={val} outside [0, {MAX_PCT}]")
        if self.used > MAX_PCT:
            raise ValueError(f"r+s+v={self.used} exceeds {MAX_PCT}")

    @property
    def used(self) -> int:
        return self.r + self.s + self.v

    @property
    def cost(self) -> int:
        return PILLAR_COST * self.used


def gross_pnl(alloc: Allocation, mu: float) -> float:
    return research(alloc.r) * scale(alloc.s) * mu


def net_pnl(alloc: Allocation, mu: float) -> float:
    return gross_pnl(alloc, mu) - alloc.cost


# ---------------------------------------------------------------------------
# Rank computation
# ---------------------------------------------------------------------------


def compute_rank(my_v: int, opponent_vs: Sequence[int]) -> int:
    """Your 1-indexed rank when ties share the best rank in the block.

    ``rank = 1 + |{opp : v_opp > my_v}|``.

    Matches the official example: me = 40 in ``[70,70,70,50,40,30]``
    -> 4 opponents above me -> rank 5.
    """
    above = sum(1 for v in opponent_vs if v > my_v)
    return above + 1


def mu_for_my_v(my_v: int, opponent_vs: Sequence[int]) -> float:
    """Realised mu given my v and a full realisation of opponent vs."""
    n_total = len(opponent_vs) + 1
    return multiplier(compute_rank(my_v, opponent_vs), n_total)


# ---------------------------------------------------------------------------
# Expected mu from an opponent prior
# ---------------------------------------------------------------------------


# A V-prior is a pmf over integer v in [0, 100]. We carry it as a
# plain tuple of 101 floats summing to 1.0 to keep things simple,
# hashable, and stdlib-friendly.

VPrior = tuple[float, ...]  # length 101


def _validate_prior(prior: VPrior) -> None:
    if len(prior) != MAX_PCT + 1:
        raise ValueError(f"prior must have {MAX_PCT + 1} entries, got {len(prior)}")
    if any(p < 0 for p in prior):
        raise ValueError("prior entries must be >= 0")
    s = sum(prior)
    if not math.isclose(s, 1.0, abs_tol=1e-9):
        raise ValueError(f"prior must sum to 1.0, got {s}")


def prob_opp_strictly_above(my_v: int, prior: VPrior) -> float:
    """P(v_opp > my_v) under ``prior``."""
    _validate_prior(prior)
    if my_v < 0 or my_v > MAX_PCT:
        raise ValueError(f"my_v={my_v} outside [0,{MAX_PCT}]")
    return sum(prior[my_v + 1 :])


def expected_mu(my_v: int, prior: VPrior, n_opponents: int) -> float:
    """E[mu | my_v] under integer-v prior.

    Uses the large-N percentile approximation
    ``mu ~= 0.9 - 0.8 * P(v_opp > my_v)``, valid when the opponent
    distribution is well-approximated by its cdf. For exact finite-N
    ties on integer points it is conservative (integer ties sharing
    the best rank push my mu marginally up relative to the approx).
    """
    if n_opponents < 0:
        raise ValueError("n_opponents must be non-negative")
    p_above = prob_opp_strictly_above(my_v, prior)
    return MU_MAX - (MU_MAX - MU_MIN) * p_above


def expected_mu_exact(my_v: int, prior: VPrior, n_opponents: int) -> float:
    """Finite-N expected mu, treating ``prior`` as the distribution
    that generates each opponent's v i.i.d.

    For an opponent field of size N, the expected rank is
    ``E[rank] = 1 + N * P(v_opp > my_v)`` and
    ``E[mu] = 0.9 - 0.8 * E[rank-1] / (n_total - 1)``
    ``       = 0.9 - 0.8 * N * P_above / (N)``
    ``       = 0.9 - 0.8 * P_above``  (since n_total = N + 1).

    So for large N the exact and approximate expressions converge.
    Kept as a separate entry point so the difference is auditable.
    """
    p_above = prob_opp_strictly_above(my_v, prior)
    n_total = n_opponents + 1
    if n_total <= 1:
        return MU_MAX
    expected_rank = 1 + n_opponents * p_above
    return MU_MAX - (MU_MAX - MU_MIN) * (expected_rank - 1) / (n_total - 1)


# ---------------------------------------------------------------------------
# Best (r, s) given mu and a budget cap on (r+s)
# ---------------------------------------------------------------------------


def best_rs_given_mu(
    mu: float,
    budget_rs: int,
    *,
    require_full_spend: bool = False,
) -> tuple[Allocation, float]:
    """Best integer ``(r, s)`` with ``r + s <= budget_rs`` given fixed mu.

    Returns ``(Allocation(r, s, 0), net_pnl_ignoring_v_cost)``. The
    v=0 here is a placeholder; the caller supplies v separately and
    we combine the two costs.

    ``require_full_spend=True`` restricts to ``r + s == budget_rs``,
    useful for the "we already committed to budget" branch.
    """
    if budget_rs < 0 or budget_rs > MAX_PCT:
        raise ValueError(f"budget_rs={budget_rs} outside [0, {MAX_PCT}]")
    if mu < 0:
        raise ValueError(f"mu must be >= 0, got {mu}")

    best: tuple[int, int] | None = None
    best_net = -math.inf
    r_range = range(0, budget_rs + 1)
    for r in r_range:
        s_max = budget_rs - r
        s_iter = (s_max,) if require_full_spend else range(0, s_max + 1)
        for s in s_iter:
            gross = research(r) * scale(s) * mu
            # cost for (r, s) only; v cost is paid outside.
            net = gross - PILLAR_COST * (r + s)
            if net > best_net:
                best_net = net
                best = (r, s)
    assert best is not None
    r, s = best
    return Allocation(r=r, s=s, v=0), best_net


@lru_cache(maxsize=1024)
def _best_rs_cache(mu_key: int, budget_rs: int) -> tuple[int, int, float]:
    """Cached helper keyed on ``round(mu*1e6)``."""
    mu = mu_key / 1e6
    alloc, net = best_rs_given_mu(mu, budget_rs)
    return alloc.r, alloc.s, net


def best_rs_cached(mu: float, budget_rs: int) -> tuple[Allocation, float]:
    key = int(round(mu * 1e6))
    r, s, net = _best_rs_cache(key, budget_rs)
    return Allocation(r=r, s=s, v=0), net


# ---------------------------------------------------------------------------
# Best (r, s, v) given an opponent prior
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllocationReport:
    """Evaluation of one candidate allocation under one prior."""

    allocation: Allocation
    mu_expected: float
    gross: float
    cost: int
    net_pnl: float


def evaluate(
    alloc: Allocation,
    prior: VPrior,
    n_opponents: int,
) -> AllocationReport:
    mu = expected_mu(alloc.v, prior, n_opponents)
    g = research(alloc.r) * scale(alloc.s) * mu
    return AllocationReport(
        allocation=alloc,
        mu_expected=mu,
        gross=g,
        cost=alloc.cost,
        net_pnl=g - alloc.cost,
    )


def best_allocation_under_prior(
    prior: VPrior,
    n_opponents: int,
    *,
    v_grid: Iterable[int] | None = None,
) -> tuple[AllocationReport, list[AllocationReport]]:
    """Full optimum over integer ``(r, s, v)`` with ``r+s+v <= 100``.

    For each ``v`` in the grid, solve the inner ``(r, s)`` problem at
    the expected mu implied by the prior, then pick the best v.

    Returns ``(best, top10)`` sorted by net PnL descending.
    """
    grid = list(range(0, MAX_PCT + 1)) if v_grid is None else list(v_grid)
    reports: list[AllocationReport] = []
    for v in grid:
        mu = expected_mu(v, prior, n_opponents)
        budget_rs = MAX_PCT - v
        alloc_rs, _ = best_rs_cached(mu, budget_rs)
        alloc = Allocation(r=alloc_rs.r, s=alloc_rs.s, v=v)
        reports.append(evaluate(alloc, prior, n_opponents))
    reports.sort(key=lambda rep: rep.net_pnl, reverse=True)
    return reports[0], reports[:10]


# ---------------------------------------------------------------------------
# Public helpers for the call site
# ---------------------------------------------------------------------------


def interior_s_from_r(r: int | float) -> float:
    """FOC curve ``s = (1+r) * ln(1+r)``.

    Locus of (r, s) pairs where dPnL/dr = 0 along the constraint
    ``r + s = const`` for any mu > 0. The actual optimum sits at the
    intersection of this curve with the binding budget line for the
    chosen (r+s) budget. Useful for sanity checks.
    """
    return (1 + r) * math.log(1 + r)
