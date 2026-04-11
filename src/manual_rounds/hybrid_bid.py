"""Hybrid bid optimizer with an average-bid coupling.

Used in P2-R4 (linear penalty) and P3-R3 (cubic penalty).

Same two-bid template as :mod:`bid_optimizer`, but the payoff from the
*high* bid is scaled when it falls below the ex-post average of other
teams' high bids ``mu``:

    scale(p_h, mu) = min(1, ((V - mu) / (V - p_h)) ** alpha)

- ``alpha = 1`` reproduces P2-R4.
- ``alpha = 3`` reproduces P3-R3 (noticeably sharper; pushes bids upward
  more aggressively).

The solver takes a *range* of plausible ``mu`` values, not a single
point estimate, and reports the bid pair whose worst-case PnL across
that range is highest. Every public round saw players under-shoot the
realised average; the robustness report is the antidote to that
failure mode.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.manual_rounds.bid_optimizer import (
    ReserveDistribution,
    one_bid_expected_pnl,
)


@dataclass(frozen=True)
class HybridScenario:
    """One assumption about the population average high bid."""

    label: str
    mu: float


@dataclass(frozen=True)
class HybridResult:
    low_bid: int
    high_bid: int
    expected_pnl_by_scenario: tuple[tuple[str, float], ...]
    mean_pnl: float
    worst_case_pnl: float


def average_bid_scale(
    resale_value: float,
    high_bid: float,
    mu: float,
    alpha: float,
) -> float:
    if alpha <= 0:
        raise ValueError("alpha must be > 0")
    if mu <= high_bid:
        return 1.0
    if resale_value <= high_bid:
        return 0.0
    ratio = (resale_value - mu) / (resale_value - high_bid)
    if ratio <= 0:
        return 0.0
    return float(min(1.0, ratio**alpha))


def hybrid_expected_pnl(
    distribution: ReserveDistribution,
    resale_value: float,
    low_bid: float,
    high_bid: float,
    mu: float,
    alpha: float,
) -> float:
    if low_bid > high_bid:
        raise ValueError("low_bid must be <= high_bid")
    low_contribution = one_bid_expected_pnl(distribution, resale_value, low_bid)
    if high_bid >= resale_value:
        return low_contribution
    mass = distribution.cdf(high_bid) - distribution.cdf(low_bid)
    scale = average_bid_scale(resale_value, high_bid, mu, alpha)
    return low_contribution + (resale_value - high_bid) * mass * scale


def optimize_hybrid(
    distribution: ReserveDistribution,
    resale_value: float,
    bid_grid: Sequence[int],
    scenarios: Sequence[HybridScenario],
    alpha: float = 1.0,
    top_k: int = 10,
) -> tuple[HybridResult, tuple[HybridResult, ...]]:
    """Pick ``(p_l, p_h)`` with the best worst-case PnL across scenarios.

    The primary return is the worst-case optimum. Top-k alternatives are
    also ranked by worst-case PnL, so the caller can pick an answer
    that's robust to mis-estimating ``mu``.
    """
    if not scenarios:
        raise ValueError("scenarios must be non-empty")

    grid = sorted(set(bid_grid))
    candidates: list[HybridResult] = []

    for i, low in enumerate(grid):
        for high in grid[i:]:
            if high == low:
                continue
            by_scenario: list[tuple[str, float]] = []
            for scenario in scenarios:
                pnl = hybrid_expected_pnl(
                    distribution, resale_value, low, high, scenario.mu, alpha
                )
                by_scenario.append((scenario.label, pnl))
            pnls = [p for _, p in by_scenario]
            candidates.append(
                HybridResult(
                    low_bid=low,
                    high_bid=high,
                    expected_pnl_by_scenario=tuple(by_scenario),
                    mean_pnl=sum(pnls) / len(pnls),
                    worst_case_pnl=min(pnls),
                )
            )

    candidates.sort(key=lambda r: r.worst_case_pnl, reverse=True)
    return candidates[0], tuple(candidates[:top_k])
