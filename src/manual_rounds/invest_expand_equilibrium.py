"""Symmetric equilibrium / regret analysis for Invest & Expand.

Two orthogonal pieces:

1. ``symmetric_qre`` - logit quantal-response fixed point over v.
   Approximates the mixed-strategy symmetric equilibrium of the
   all-pay-on-speed sub-game when every player optimises (r, s)
   given the mu implied by the field.

2. ``regret_table`` - evaluates a set of candidate allocations
   against a set of named priors and returns worst-case PnL, mean,
   and max-regret vs. the best-in-prior alternative. Picks the
   "parameter plateau" winner (smallest max regret).

Neither requires numpy. The QRE iteration is O(101 * max_iters) which
is trivial.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from src.manual_rounds.invest_expand import (
    MAX_PCT,
    Allocation,
    AllocationReport,
    VPrior,
    best_rs_cached,
    evaluate,
    expected_mu,
)


# ---------------------------------------------------------------------------
# Symmetric quantal-response equilibrium
# ---------------------------------------------------------------------------


def _payoff_by_v(prior: VPrior, n_opponents: int) -> list[float]:
    """Net PnL a rational player achieves for each integer v in [0,100]
    when they best-respond with (r, s) to the expected mu implied by
    ``prior``.
    """
    out: list[float] = []
    for v in range(MAX_PCT + 1):
        mu = expected_mu(v, prior, n_opponents)
        budget_rs = MAX_PCT - v
        alloc_rs, _ = best_rs_cached(mu, budget_rs)
        alloc = Allocation(r=alloc_rs.r, s=alloc_rs.s, v=v)
        out.append(evaluate(alloc, prior, n_opponents).net_pnl)
    return out


def _logit(payoffs: Sequence[float], temperature: float) -> VPrior:
    if temperature <= 0:
        raise ValueError(f"temperature must be > 0, got {temperature}")
    m = max(payoffs)
    # Subtract the max for numerical stability (standard softmax trick).
    exps = [math.exp((p - m) / temperature) for p in payoffs]
    z = sum(exps)
    return tuple(x / z for x in exps)


@dataclass(frozen=True)
class QREResult:
    equilibrium: VPrior
    iterations: int
    payoffs: tuple[float, ...]
    converged: bool
    best_responses: tuple[int, ...]  # top-5 v by equilibrium payoff


def symmetric_qre(
    n_opponents: int,
    *,
    temperature: float = 20_000.0,
    damping: float = 0.3,
    max_iter: int = 400,
    tol: float = 1e-6,
    initial: VPrior | None = None,
) -> QREResult:
    """Logit quantal-response fixed point over the symmetric v
    strategy.

    ``temperature`` controls rationality: low T -> hard best response
    (closer to pure NE); high T -> broader mixing. Payoffs are in the
    range of ~1e5 XIREC so T ~ 1e4-5e4 gives a meaningfully mixed
    but well-discriminated equilibrium.

    ``damping`` prevents oscillation: ``new = damping * logit(payoffs)
    + (1 - damping) * old``. Smaller damping = more conservative.
    """
    if not (0 < damping <= 1):
        raise ValueError(f"damping must be in (0, 1], got {damping}")

    uniform = tuple([1.0 / (MAX_PCT + 1)] * (MAX_PCT + 1))
    prior = initial if initial is not None else uniform

    converged = False
    payoffs_final: list[float] = []
    for it in range(max_iter):
        payoffs_final = _payoff_by_v(prior, n_opponents)
        br = _logit(payoffs_final, temperature)
        new_prior = tuple(
            damping * br_i + (1 - damping) * p_i for br_i, p_i in zip(br, prior)
        )
        delta = max(abs(a - b) for a, b in zip(new_prior, prior))
        prior = new_prior
        if delta < tol:
            converged = True
            break

    # Top-5 v by payoff (best responses a pure-strategy team might pick).
    top5 = sorted(range(MAX_PCT + 1), key=lambda v: payoffs_final[v], reverse=True)[:5]
    return QREResult(
        equilibrium=prior,
        iterations=it + 1,
        payoffs=tuple(payoffs_final),
        converged=converged,
        best_responses=tuple(top5),
    )


# ---------------------------------------------------------------------------
# Regret / robustness table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriorEval:
    prior_name: str
    report: AllocationReport


@dataclass(frozen=True)
class CandidateSummary:
    """Cross-prior evaluation of a single candidate allocation."""

    allocation: Allocation
    evaluations: tuple[PriorEval, ...]
    worst: PriorEval
    best: PriorEval
    mean_pnl: float
    max_regret: float  # worst (best-in-prior - me) gap
    regret_by_prior: tuple[tuple[str, float], ...]


def regret_table(
    candidates: Sequence[Allocation],
    priors: Mapping[str, VPrior],
    n_opponents: int,
) -> list[CandidateSummary]:
    """Evaluate each candidate against each prior.

    Returns a list sorted ascending by ``max_regret`` (most robust
    first). ``max_regret`` is the worst gap between the candidate's
    PnL and the best-possible allocation *for that specific prior*.
    """
    if not candidates:
        raise ValueError("candidates must be non-empty")
    if not priors:
        raise ValueError("priors must be non-empty")

    # Precompute the best-in-prior net PnL for every named prior so we
    # can score regret.
    from src.manual_rounds.invest_expand import best_allocation_under_prior

    best_under: dict[str, float] = {}
    for name, p in priors.items():
        rep, _ = best_allocation_under_prior(p, n_opponents)
        best_under[name] = rep.net_pnl

    summaries: list[CandidateSummary] = []
    for alloc in candidates:
        evals: list[PriorEval] = []
        regrets: list[tuple[str, float]] = []
        for name, p in priors.items():
            rep = evaluate(alloc, p, n_opponents)
            evals.append(PriorEval(prior_name=name, report=rep))
            regrets.append((name, best_under[name] - rep.net_pnl))
        evals_tuple = tuple(evals)
        worst = min(evals_tuple, key=lambda e: e.report.net_pnl)
        best = max(evals_tuple, key=lambda e: e.report.net_pnl)
        mean_pnl = sum(e.report.net_pnl for e in evals_tuple) / len(evals_tuple)
        max_regret = max(r for _, r in regrets)
        summaries.append(
            CandidateSummary(
                allocation=alloc,
                evaluations=evals_tuple,
                worst=worst,
                best=best,
                mean_pnl=mean_pnl,
                max_regret=max_regret,
                regret_by_prior=tuple(regrets),
            )
        )
    summaries.sort(key=lambda c: c.max_regret)
    return summaries


# ---------------------------------------------------------------------------
# Candidate generation helpers
# ---------------------------------------------------------------------------


def generate_candidate_grid(
    v_values: Sequence[int],
    priors_for_mu: Sequence[float] | None = None,
) -> list[Allocation]:
    """Build a candidate set by taking each v and picking the optimal
    (r, s) under each of several mu beliefs.

    ``priors_for_mu`` defaults to ``(0.1, 0.3, 0.5, 0.7, 0.9)``,
    spanning the full multiplier range. This produces a rich but
    not-too-large candidate set (|v_values| * |mu_beliefs|).
    """
    if priors_for_mu is None:
        priors_for_mu = (0.1, 0.3, 0.5, 0.7, 0.9)
    seen: set[Allocation] = set()
    out: list[Allocation] = []
    for v in v_values:
        budget_rs = MAX_PCT - v
        for mu in priors_for_mu:
            alloc_rs, _ = best_rs_cached(mu, budget_rs)
            cand = Allocation(r=alloc_rs.r, s=alloc_rs.s, v=v)
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out
