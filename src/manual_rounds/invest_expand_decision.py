"""Decision-theoretic wrappers on top of the base Invest & Expand
solver.

Two analyses:

1. ``weighted_meta_regret`` - take an explicit subjective probability
   distribution over priors and collapse the full regret table to a
   single expected-PnL per candidate. Forces the analyst to commit to
   beliefs rather than hide behind a minimax-over-everything rule.

2. ``value_of_information`` - quantify how much a future signal would
   improve expected PnL. For each possible "revelation" (learning
   which prior is the true one), compute the best-response and its
   PnL vs. the current committed pick. The gap is the VoI of that
   revelation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.manual_rounds.invest_expand import (
    Allocation,
    VPrior,
    best_allocation_under_prior,
    evaluate,
)


# ---------------------------------------------------------------------------
# Weighted meta-regret
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaRegretRow:
    allocation: Allocation
    weighted_mean_pnl: float
    per_prior_pnl: tuple[tuple[str, float, float], ...]  # (name, weight, pnl)
    best_prior: str
    best_prior_pnl: float
    worst_prior: str
    worst_prior_pnl: float


def weighted_meta_regret(
    candidates: Sequence[Allocation],
    priors: Mapping[str, VPrior],
    weights: Mapping[str, float],
    n_opponents: int,
) -> list[MetaRegretRow]:
    """For each candidate allocation, compute expected PnL under the
    user-supplied probability distribution over priors.

    ``weights`` must have the same keys as ``priors`` and sum to > 0.
    Returns list sorted descending by weighted mean PnL.
    """
    if set(weights) != set(priors):
        missing = set(priors) - set(weights)
        extra = set(weights) - set(priors)
        raise ValueError(
            f"weights keys must match priors: missing={missing}, extra={extra}"
        )
    w_sum = sum(weights.values())
    if w_sum <= 0:
        raise ValueError("weights must sum to > 0")
    normed = {k: v / w_sum for k, v in weights.items()}

    rows: list[MetaRegretRow] = []
    for alloc in candidates:
        per_prior: list[tuple[str, float, float]] = []
        weighted_total = 0.0
        best_pnl, worst_pnl = -math.inf, math.inf
        best_name, worst_name = "", ""
        for name, prior in priors.items():
            rep = evaluate(alloc, prior, n_opponents)
            pnl = rep.net_pnl
            per_prior.append((name, normed[name], pnl))
            weighted_total += normed[name] * pnl
            if pnl > best_pnl:
                best_pnl, best_name = pnl, name
            if pnl < worst_pnl:
                worst_pnl, worst_name = pnl, name
        rows.append(
            MetaRegretRow(
                allocation=alloc,
                weighted_mean_pnl=weighted_total,
                per_prior_pnl=tuple(per_prior),
                best_prior=best_name,
                best_prior_pnl=best_pnl,
                worst_prior=worst_name,
                worst_prior_pnl=worst_pnl,
            )
        )
    rows.sort(key=lambda r: r.weighted_mean_pnl, reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Value of information
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoIRow:
    revealed_prior: str
    committed_pick_pnl: float      # our current commitment's PnL under this prior
    best_pick_pnl: float            # optimal pick given we KNEW this prior
    best_pick_allocation: Allocation
    voi_marginal: float             # gain from switching
    weight: float                   # prior probability of this revelation


@dataclass(frozen=True)
class VoISummary:
    committed_pick: Allocation
    expected_voi: float             # sum(weight * voi_marginal)
    rows: tuple[VoIRow, ...]
    regret_vs_perfect_info: float   # same as expected_voi


def value_of_information(
    committed_pick: Allocation,
    priors: Mapping[str, VPrior],
    weights: Mapping[str, float],
    n_opponents: int,
) -> VoISummary:
    """Compute the expected gain from learning which prior is true.

    For each prior (weighted by the subjective probability it's the
    one that materialises), compare:
      (a) our committed_pick's PnL under that prior
      (b) the optimal allocation if we knew that prior was true

    The weighted average of (b - a) is the expected VoI. It bounds
    how much PnL is on the table from reducing prior uncertainty.

    If expected_voi is small, more modeling is low-value. If large,
    seeking more empirical signal is high-leverage.
    """
    if set(weights) != set(priors):
        raise ValueError("weights keys must match priors")
    w_sum = sum(weights.values())
    if w_sum <= 0:
        raise ValueError("weights must sum to > 0")
    normed = {k: v / w_sum for k, v in weights.items()}

    rows: list[VoIRow] = []
    expected_voi = 0.0
    for name, prior in priors.items():
        committed_rep = evaluate(committed_pick, prior, n_opponents)
        best_rep, _ = best_allocation_under_prior(prior, n_opponents)
        gap = best_rep.net_pnl - committed_rep.net_pnl
        w = normed[name]
        rows.append(
            VoIRow(
                revealed_prior=name,
                committed_pick_pnl=committed_rep.net_pnl,
                best_pick_pnl=best_rep.net_pnl,
                best_pick_allocation=best_rep.allocation,
                voi_marginal=gap,
                weight=w,
            )
        )
        expected_voi += w * gap

    rows.sort(key=lambda r: r.voi_marginal * r.weight, reverse=True)
    return VoISummary(
        committed_pick=committed_pick,
        expected_voi=expected_voi,
        rows=tuple(rows),
        regret_vs_perfect_info=expected_voi,
    )
