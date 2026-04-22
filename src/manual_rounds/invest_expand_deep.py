"""Deeper analytics for Invest & Expand beyond the base regret table.

Four pieces the MAF consensus-fragility warning forced into scope:

1. ``level_k_iteration`` - starts from a naive (level-0) field, computes
   best response, feeds that back as the new field, iterates. Shows
   whether the game converges or cycles across sophistication levels.

2. ``monte_carlo_mu`` - numerical validator for the closed-form
   ``E[mu] ~= 0.9 - 0.8 * P(opp > me)`` expression. Draws opponent
   fields from a prior and computes realised mu directly.

3. ``adversarial_worst_prior`` - for a fixed candidate allocation,
   search the prior space for the distribution that punishes it most.
   Returns the minimum-over-priors PnL and the offending prior.

4. ``field_phase_diagram`` - sweeps ``(mean_v, spread_v)`` of a
   truncated-normal opponent field and computes the best-response v
   at each grid point. Produces the "where is the optimum v as a
   function of what we believe about the field" map.

All pure stdlib + ``random`` + ``statistics``.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from src.manual_rounds.invest_expand import (
    MAX_PCT,
    Allocation,
    AllocationReport,
    VPrior,
    best_allocation_under_prior,
    best_rs_cached,
    evaluate,
    expected_mu,
    mu_for_my_v,
)
from src.manual_rounds.invest_expand_priors import (
    _normalize_pmf,
    consensus_cluster,
    leapfrog_adversary,
    naive_thirds,
    optimising_at_mu,
    semi_naive_insurance_cluster,
    spike,
    uniform,
)


# ---------------------------------------------------------------------------
# Level-k iteration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LevelKStep:
    level: int
    field_prior_argmax: int  # mode of the field at this level
    best_response: Allocation
    net_pnl: float
    expected_mu: float


def level_k_iteration(
    naive_prior: VPrior,
    n_opponents: int,
    depth: int = 6,
) -> list[LevelKStep]:
    """Iterate best-response: every level replaces the field with a
    spike at the previous level's best-response v.

    Level 0 uses ``naive_prior``.
    Level k best-responds to Level (k-1).

    Convergence = field argmax stops moving. Cycling = field argmax
    visits a closed loop. Both are informative.
    """
    steps: list[LevelKStep] = []
    current: VPrior = naive_prior
    for level in range(depth):
        # Mode of current prior
        mode_v = max(range(MAX_PCT + 1), key=lambda v: current[v])
        rep, _ = best_allocation_under_prior(current, n_opponents)
        steps.append(
            LevelKStep(
                level=level,
                field_prior_argmax=mode_v,
                best_response=rep.allocation,
                net_pnl=rep.net_pnl,
                expected_mu=rep.mu_expected,
            )
        )
        # Next level: field plays the BR v (pure strategy spike)
        current = spike(rep.allocation.v)
    return steps


# ---------------------------------------------------------------------------
# Monte Carlo validator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCResult:
    my_v: int
    closed_form_mu: float
    mc_mean_mu: float
    mc_std_mu: float
    n_trials: int


def _sample_from_prior(prior: VPrior, n: int, rng: random.Random) -> list[int]:
    """Draw ``n`` integer samples from a 101-entry discrete pmf."""
    cum = []
    c = 0.0
    for p in prior:
        c += p
        cum.append(c)
    out: list[int] = []
    for _ in range(n):
        u = rng.random()
        # Simple linear search; 101 buckets makes bisect overkill.
        for i, ci in enumerate(cum):
            if u <= ci:
                out.append(i)
                break
        else:
            out.append(MAX_PCT)
    return out


def monte_carlo_mu(
    my_v: int,
    prior: VPrior,
    n_opponents: int,
    n_trials: int = 2000,
    seed: int = 1234,
) -> MCResult:
    """Validate the closed-form E[mu] via direct simulation.

    Draws ``n_opponents`` opponent v-samples from the prior, computes
    realised mu under the tie-rank rule, averages over ``n_trials``.
    Should match ``expected_mu(my_v, prior, n_opponents)`` to within a
    few MC-std (~1 / sqrt(n_trials)).
    """
    rng = random.Random(seed)
    closed = expected_mu(my_v, prior, n_opponents)
    mus: list[float] = []
    for _ in range(n_trials):
        opponents = _sample_from_prior(prior, n_opponents, rng)
        mus.append(mu_for_my_v(my_v, opponents))
    return MCResult(
        my_v=my_v,
        closed_form_mu=closed,
        mc_mean_mu=statistics.fmean(mus),
        mc_std_mu=statistics.pstdev(mus),
        n_trials=n_trials,
    )


# ---------------------------------------------------------------------------
# Adversarial worst-case prior
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdversaryResult:
    allocation: Allocation
    worst_prior_name: str
    worst_pnl: float
    mu_at_worst: float
    best_prior_name: str
    best_pnl: float


def _stress_prior_library() -> dict[str, VPrior]:
    """Broader prior library including MAF-fragility + focal-cluster
    adversarial families."""
    out: dict[str, VPrior] = {}
    # Sharp focal clusters at every round number
    for c in (0, 5, 10, 15, 20, 25, 30, 33, 35, 40, 45, 50, 60, 70):
        out[f"cluster_v{c}_60pct"] = consensus_cluster(c, cluster_share=0.6)
    # Leapfrog adversaries targeting each candidate's likely v
    for v in (0, 5, 10, 20, 30, 34, 40, 45, 50):
        out[f"leapfrog_beating_v{v}"] = leapfrog_adversary(v)
    # MAF-style fragility clusters
    out["maf_v5_cluster"] = semi_naive_insurance_cluster(center=5, spread=3)
    out["maf_v10_cluster"] = semi_naive_insurance_cluster(center=10, spread=4)
    out["maf_v15_cluster"] = semi_naive_insurance_cluster(center=15, spread=5)
    # Heterogeneous fields
    out["uniform_full"] = uniform()
    return out


def adversarial_worst_prior(
    alloc: Allocation,
    n_opponents: int,
    prior_library: dict[str, VPrior] | None = None,
) -> AdversaryResult:
    """Find the prior in the library that punishes ``alloc`` most.

    Returns the worst and best scoring priors for reference. This is a
    *bounded adversary* — real worst case may be worse if you let the
    prior space range freely, but that space is infinite; we lean on
    the canonical stress library.
    """
    lib = prior_library or _stress_prior_library()
    best_name, best_pnl = "", -math.inf
    worst_name, worst_pnl, worst_mu = "", math.inf, 0.0
    for name, p in lib.items():
        rep = evaluate(alloc, p, n_opponents)
        if rep.net_pnl < worst_pnl:
            worst_pnl = rep.net_pnl
            worst_name = name
            worst_mu = rep.mu_expected
        if rep.net_pnl > best_pnl:
            best_pnl = rep.net_pnl
            best_name = name
    return AdversaryResult(
        allocation=alloc,
        worst_prior_name=worst_name,
        worst_pnl=worst_pnl,
        mu_at_worst=worst_mu,
        best_prior_name=best_name,
        best_pnl=best_pnl,
    )


# ---------------------------------------------------------------------------
# Phase diagram sweep: (mean_v, spread_v) -> best-response
# ---------------------------------------------------------------------------


def _truncated_normal_prior(mean_v: float, std_v: float) -> VPrior:
    """Discrete truncated-normal pmf on integer v in [0, 100]."""
    if std_v <= 0:
        raise ValueError(f"std_v must be > 0, got {std_v}")
    # Evaluate a Gaussian pdf at each integer, then normalise.
    weights = [
        math.exp(-0.5 * ((v - mean_v) / std_v) ** 2) for v in range(MAX_PCT + 1)
    ]
    return _normalize_pmf(weights)


@dataclass(frozen=True)
class PhaseCell:
    mean_v: float
    std_v: float
    best_v: int
    best_r: int
    best_s: int
    net_pnl: float


def field_phase_diagram(
    mean_grid: Sequence[float],
    std_grid: Sequence[float],
    n_opponents: int,
) -> list[PhaseCell]:
    """For each (mean, std) of a truncated-normal opponent field,
    return the optimal (r, s, v) allocation and its PnL."""
    out: list[PhaseCell] = []
    for m in mean_grid:
        for s_ in std_grid:
            prior = _truncated_normal_prior(m, s_)
            rep, _ = best_allocation_under_prior(prior, n_opponents)
            out.append(
                PhaseCell(
                    mean_v=m,
                    std_v=s_,
                    best_v=rep.allocation.v,
                    best_r=rep.allocation.r,
                    best_s=rep.allocation.s,
                    net_pnl=rep.net_pnl,
                )
            )
    return out
