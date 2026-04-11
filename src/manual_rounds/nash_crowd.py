"""Game-theoretic crowding solver.

Used in:
- Prosperity 2 Round 3 (5x5 treasure-hunt expeditions, 25 cells)
- Prosperity 3 Round 2 (10 containers, 1 free + 50k second)
- Prosperity 3 Round 4 (20 suitcases, 1 free + 50k second + 100k third)

Doctrine:

- Every cell has a multiplier ``M`` and base inhabitants ``I``. Your share
  of a cell's ``base_treasure * M`` pot is diluted by ``I + coupling * p``,
  where ``p`` is the fraction of all player picks landing on that cell.
- We solve for ``p`` under a logit quantal-response equilibrium. Pure
  best-response on a finite cell grid oscillates; logit with a small
  temperature damps that out while still preferring high-EV cells.
- A "pick bundle" ``S`` is a subset of cells you choose. Its PnL is
  ``sum_{j in S} ev_j - pick_fees[|S|-1]``. We enumerate bundles up to
  ``max_picks`` and report the optimum plus any close alternatives.
- The solver does not commit to a single prior. It returns the logit
  equilibrium distribution; callers can overlay priors from
  :mod:`src.manual_rounds.priors` and re-run ``evaluate_bundles``.

This module is used *offline* during the 72-hour window for a manual
round. It is deliberately small, pure, and dependency-free (no numpy)
so it can be audited quickly under time pressure.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class CrowdCell:
    """A single crowding option.

    ``name`` is an arbitrary label (e.g. "C7" or "80x6"). ``multiplier``
    and ``inhabitants`` match the numbers printed on the IMC manual-round
    board; ``inhabitants`` must be strictly positive to avoid divide-by-zero
    when the cell has zero crowd share.
    """

    name: str
    multiplier: float
    inhabitants: float

    def __post_init__(self) -> None:
        if self.multiplier <= 0:
            raise ValueError(f"cell {self.name!r}: multiplier must be > 0")
        if self.inhabitants <= 0:
            raise ValueError(f"cell {self.name!r}: inhabitants must be > 0")


@dataclass(frozen=True)
class CrowdPayoff:
    """Configuration for the payoff formula.

    The per-cell payoff is

        ev_j = base_treasure * M_j / (I_j + coupling * p_j)

    ``coupling`` is 100 in every public Prosperity crowding round seen
    so far (P2-R3, P3-R2, P3-R4). ``base_treasure`` is 7500 in P2 and
    10000 in P3 — check the round page.
    """

    base_treasure: float
    coupling: float = 100.0

    def __post_init__(self) -> None:
        if self.base_treasure <= 0:
            raise ValueError("base_treasure must be > 0")
        if self.coupling <= 0:
            raise ValueError("coupling must be > 0")

    def ev(self, cell: CrowdCell, share: float) -> float:
        return self.base_treasure * cell.multiplier / (cell.inhabitants + self.coupling * share)


@dataclass(frozen=True)
class Bundle:
    """A concrete pick choice with its net PnL."""

    cells: tuple[str, ...]
    gross_ev: float
    fee: float
    net_ev: float

    @property
    def size(self) -> int:
        return len(self.cells)


@dataclass(frozen=True)
class CrowdSolution:
    """Result of ``solve``.

    ``shares`` is the equilibrium share distribution used to score
    bundles. ``ev_per_cell`` is the per-cell expected value under those
    shares, sorted highest-first by name order.
    """

    shares: Mapping[str, float]
    ev_per_cell: Mapping[str, float]
    best_by_size: Mapping[int, Bundle]
    top_bundles: tuple[Bundle, ...]
    iterations: int
    converged: bool


def _validate_inputs(
    cells: Sequence[CrowdCell],
    pick_fees: Sequence[float],
    max_picks: int,
) -> None:
    if not cells:
        raise ValueError("cells must be non-empty")
    names = [c.name for c in cells]
    if len(set(names)) != len(names):
        raise ValueError("cell names must be unique")
    if max_picks < 1:
        raise ValueError("max_picks must be >= 1")
    if max_picks > len(cells):
        raise ValueError("max_picks cannot exceed number of cells")
    if len(pick_fees) != max_picks:
        raise ValueError(
            f"pick_fees must have length {max_picks} (one entry per allowed size)"
        )
    if pick_fees[0] != 0:
        raise ValueError("pick_fees[0] (single pick) must be 0 by convention")
    if any(f < 0 for f in pick_fees):
        raise ValueError("pick_fees must be non-negative")


def logit_quantal_equilibrium(
    cells: Sequence[CrowdCell],
    payoff: CrowdPayoff,
    temperature: float = 10_000.0,
    damping: float = 0.3,
    max_iterations: int = 2_000,
    tolerance: float = 1e-8,
) -> tuple[dict[str, float], int, bool]:
    """Iterate logit best-response to a fixed-point share distribution.

    Parameters
    ----------
    cells:
        The candidate cells.
    payoff:
        The payoff configuration (base treasure + coupling).
    temperature:
        Logit temperature. Low T -> sharp best response (oscillates or
        amplifies small share changes); high T -> smooth mixing
        (converges reliably). The default of 10 000 is tuned for
        Prosperity-scale rewards where per-cell EVs sit in the tens of
        thousands of SeaShells. Raise T if convergence is slow, lower
        it if the equilibrium looks uniform.
    damping:
        Fraction of the new response mixed into the current shares per
        step. 0.3 is the default: gentle enough that the fixed-point
        iteration is a contraction for any realistic EV scale, while
        still converging in tens of iterations for smooth problems.
    max_iterations:
        Upper bound on iterations before giving up.
    tolerance:
        L-infinity change threshold for convergence.

    Returns
    -------
    A tuple of (shares, iterations_used, converged_flag).
    """
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    if not (0 < damping <= 1):
        raise ValueError("damping must be in (0, 1]")
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    n = len(cells)
    shares = {c.name: 1.0 / n for c in cells}
    converged = False
    used = 0

    for step in range(1, max_iterations + 1):
        used = step
        evs = {c.name: payoff.ev(c, shares[c.name]) for c in cells}
        # Numerically stable softmax.
        max_ev = max(evs.values())
        exps = {name: math.exp((ev - max_ev) / temperature) for name, ev in evs.items()}
        total = sum(exps.values())
        logit = {name: v / total for name, v in exps.items()}
        new_shares = {
            name: (1 - damping) * shares[name] + damping * logit[name] for name in shares
        }
        delta = max(abs(new_shares[name] - shares[name]) for name in shares)
        shares = new_shares
        if delta < tolerance:
            converged = True
            break

    return shares, used, converged


def evaluate_bundles(
    cells: Sequence[CrowdCell],
    payoff: CrowdPayoff,
    shares: Mapping[str, float],
    pick_fees: Sequence[float],
    max_picks: int,
    top_k: int = 10,
) -> tuple[dict[int, Bundle], tuple[Bundle, ...]]:
    """Enumerate every bundle up to ``max_picks`` and rank by net EV.

    Returns a tuple ``(best_by_size, top_bundles)``:

    - ``best_by_size[k]`` is the highest net-EV bundle of exactly size ``k``.
    - ``top_bundles`` is a tuple of the ``top_k`` bundles overall, sorted
      highest net-EV first.
    """
    evs = {c.name: payoff.ev(c, shares[c.name]) for c in cells}
    all_bundles: list[Bundle] = []
    for size in range(1, max_picks + 1):
        fee = pick_fees[size - 1]
        for combo in combinations(cells, size):
            names = tuple(c.name for c in combo)
            gross = sum(evs[name] for name in names)
            all_bundles.append(
                Bundle(cells=names, gross_ev=gross, fee=fee, net_ev=gross - fee)
            )

    all_bundles.sort(key=lambda b: b.net_ev, reverse=True)

    best_by_size: dict[int, Bundle] = {}
    for bundle in all_bundles:
        if bundle.size not in best_by_size:
            best_by_size[bundle.size] = bundle
        if len(best_by_size) == max_picks:
            break

    return best_by_size, tuple(all_bundles[:top_k])


def solve(
    cells: Sequence[CrowdCell],
    payoff: CrowdPayoff,
    pick_fees: Sequence[float],
    max_picks: int = 1,
    shares_override: Mapping[str, float] | None = None,
    temperature: float = 10_000.0,
    damping: float = 0.3,
    max_iterations: int = 2_000,
    top_k: int = 10,
) -> CrowdSolution:
    """End-to-end crowding solve.

    If ``shares_override`` is supplied, the equilibrium solver is skipped
    and those shares are used directly (useful for overlaying priors
    from :mod:`src.manual_rounds.priors`).
    """
    _validate_inputs(cells, pick_fees, max_picks)

    if shares_override is not None:
        missing = {c.name for c in cells} - set(shares_override)
        if missing:
            raise ValueError(f"shares_override missing cells: {sorted(missing)}")
        if any(v < 0 for v in shares_override.values()):
            raise ValueError("shares_override must be non-negative")
        total = sum(shares_override[c.name] for c in cells)
        if total <= 0:
            raise ValueError("shares_override sum must be > 0")
        shares: dict[str, float] = {c.name: shares_override[c.name] / total for c in cells}
        iterations = 0
        converged = True
    else:
        shares, iterations, converged = logit_quantal_equilibrium(
            cells,
            payoff,
            temperature=temperature,
            damping=damping,
            max_iterations=max_iterations,
        )

    evs = {c.name: payoff.ev(c, shares[c.name]) for c in cells}
    best_by_size, top_bundles = evaluate_bundles(
        cells, payoff, shares, pick_fees, max_picks, top_k
    )

    return CrowdSolution(
        shares=shares,
        ev_per_cell=evs,
        best_by_size=best_by_size,
        top_bundles=top_bundles,
        iterations=iterations,
        converged=converged,
    )


def sensitivity_sweep(
    cells: Sequence[CrowdCell],
    payoff: CrowdPayoff,
    pick_fees: Sequence[float],
    max_picks: int,
    share_variants: Iterable[tuple[str, Mapping[str, float]]],
) -> dict[str, CrowdSolution]:
    """Evaluate the same cell grid under multiple crowd assumptions.

    ``share_variants`` is an iterable of ``(label, shares)`` pairs. Use
    this to stress-test the chosen bundle against different priors: Nash
    quantal response, "top cells over-picked", nice-number bias, etc.
    """
    out: dict[str, CrowdSolution] = {}
    for label, shares in share_variants:
        out[label] = solve(
            cells,
            payoff,
            pick_fees,
            max_picks=max_picks,
            shares_override=shares,
        )
    return out
