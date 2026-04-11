"""Single-agent sealed-bid optimizer against a known reserve distribution.

Used in P2-R1 (linear reserve on [900, 1000], two bids).

Problem shape: a mass of counterparties with private reserves drawn
i.i.d. from a known distribution ``F``. You post one or two integer
bids; a counterparty trades at the *lowest* bid that is >= its reserve,
and you resell each unit at a fixed value ``V``.

Expected PnL per unit, for a single bid ``p``:

    E[Pi(p)] = (V - p) * P(R <= p)

For two bids ``p_l <= p_h``:

    E[Pi(p_l, p_h)] = (V - p_l) * P(R <= p_l)
                    + (V - p_h) * P(p_l < R <= p_h)

We expose a ``ReserveDistribution`` abstraction with concrete
implementations for uniform, piecewise-linear (P2-R1's
``f(r) = r/5000 - 9/50``), and *bimodal* (P3-R3's ``[160,200]`` and
``[250,320]`` with a forbidden gap between 200 and 250). Custom
distributions can plug in by subclassing ``ReserveDistribution`` and
implementing ``cdf``.

Solvers:

- ``optimize_one_bid``: exhaustive grid over integer bids.
- ``optimize_two_bids``: exhaustive grid over ``(p_l, p_h)`` pairs with
  ``p_l < p_h``.

Both return the full ranked table so the caller can pick a robust
answer rather than a sharp optimum (a recurring lesson: the EV-optimal
``(952, 978)`` in P2-R1 was only ex-post best ~9% of the time).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class ReserveDistribution(Protocol):
    """Continuous reserve distribution over prices.

    Only ``cdf`` is strictly required; implementations are free to
    expose more methods. A callable returns ``P(R <= x)``.
    """

    def cdf(self, x: float) -> float: ...


@dataclass(frozen=True)
class UniformReserve:
    low: float
    high: float

    def __post_init__(self) -> None:
        if self.high <= self.low:
            raise ValueError("high must exceed low")

    def cdf(self, x: float) -> float:
        if x <= self.low:
            return 0.0
        if x >= self.high:
            return 1.0
        return (x - self.low) / (self.high - self.low)


@dataclass(frozen=True)
class LinearRampReserve:
    """PDF proportional to ``(x - low)`` on ``[low, high]``.

    This is the P2-R1 distribution: ``f(r) = r/5000 - 9/50`` on
    ``[900, 1000]`` is exactly ``(r - 900) / 5000``, which integrates
    to 1 over ``[900, 1000]``.

    CDF closed form: ``F(x) = ((x - low) / (high - low)) ** 2``.
    """

    low: float
    high: float

    def __post_init__(self) -> None:
        if self.high <= self.low:
            raise ValueError("high must exceed low")

    def cdf(self, x: float) -> float:
        if x <= self.low:
            return 0.0
        if x >= self.high:
            return 1.0
        return ((x - self.low) / (self.high - self.low)) ** 2


@dataclass(frozen=True)
class BimodalUniformReserve:
    """Two disjoint uniform regions with a forbidden gap.

    Used in P3-R3: ``[160, 200]`` and ``[250, 320]`` (gap between 200
    and 250). Each region gets weight ``mass_low`` and ``1 - mass_low``
    respectively; inside a region the distribution is uniform. Reserves
    in the gap are impossible — bidding there is legal but fills nothing
    extra vs bidding at the top of the lower region.
    """

    low_a: float
    high_a: float
    low_b: float
    high_b: float
    mass_low: float = 0.5

    def __post_init__(self) -> None:
        if self.high_a <= self.low_a:
            raise ValueError("high_a must exceed low_a")
        if self.high_b <= self.low_b:
            raise ValueError("high_b must exceed low_b")
        if self.low_b < self.high_a:
            raise ValueError("regions must not overlap (low_b >= high_a)")
        if not (0 < self.mass_low < 1):
            raise ValueError("mass_low must be in (0, 1)")

    def cdf(self, x: float) -> float:
        if x <= self.low_a:
            return 0.0
        if x >= self.high_b:
            return 1.0
        if x < self.high_a:
            return self.mass_low * (x - self.low_a) / (self.high_a - self.low_a)
        if x < self.low_b:
            return self.mass_low  # inside the gap
        return self.mass_low + (1 - self.mass_low) * (x - self.low_b) / (self.high_b - self.low_b)


@dataclass(frozen=True)
class OneBidResult:
    bid: int
    expected_pnl_per_unit: float


@dataclass(frozen=True)
class TwoBidResult:
    low_bid: int
    high_bid: int
    expected_pnl_per_unit: float


def one_bid_expected_pnl(
    distribution: ReserveDistribution,
    resale_value: float,
    bid: float,
) -> float:
    if bid >= resale_value:
        return 0.0
    return (resale_value - bid) * distribution.cdf(bid)


def two_bid_expected_pnl(
    distribution: ReserveDistribution,
    resale_value: float,
    low_bid: float,
    high_bid: float,
) -> float:
    if low_bid > high_bid:
        raise ValueError("low_bid must be <= high_bid")
    if high_bid >= resale_value:
        # High bid earns no margin when you pay what you resell for.
        high_bid_contribution = 0.0
    else:
        high_bid_contribution = (resale_value - high_bid) * (
            distribution.cdf(high_bid) - distribution.cdf(low_bid)
        )
    low_bid_contribution = one_bid_expected_pnl(distribution, resale_value, low_bid)
    return low_bid_contribution + high_bid_contribution


def optimize_one_bid(
    distribution: ReserveDistribution,
    resale_value: float,
    bid_grid: Sequence[int],
    top_k: int = 5,
) -> tuple[OneBidResult, tuple[OneBidResult, ...]]:
    scored = [
        OneBidResult(bid=b, expected_pnl_per_unit=one_bid_expected_pnl(distribution, resale_value, b))
        for b in bid_grid
    ]
    scored.sort(key=lambda r: r.expected_pnl_per_unit, reverse=True)
    return scored[0], tuple(scored[:top_k])


def optimize_two_bids(
    distribution: ReserveDistribution,
    resale_value: float,
    bid_grid: Sequence[int],
    top_k: int = 10,
) -> tuple[TwoBidResult, tuple[TwoBidResult, ...]]:
    scored: list[TwoBidResult] = []
    grid = sorted(set(bid_grid))
    for i, low in enumerate(grid):
        for high in grid[i:]:
            if high == low:
                continue
            pnl = two_bid_expected_pnl(distribution, resale_value, low, high)
            scored.append(TwoBidResult(low_bid=low, high_bid=high, expected_pnl_per_unit=pnl))
    scored.sort(key=lambda r: r.expected_pnl_per_unit, reverse=True)
    return scored[0], tuple(scored[:top_k])
