"""Crowd behaviour priors for game-theoretic manual rounds.

Produces share distributions over a set of named cells. The typical
workflow for a Family-3 or Family-4 round:

1. Solve the logit quantal equilibrium with
   :func:`src.manual_rounds.nash_crowd.solve`.
2. Build alternative prior distributions from this module (uniform,
   inverse Nash, concentrated on top multipliers, nice-number overlay).
3. Mix them with :func:`mix_priors` in different proportions and pass
   the results back through :func:`nash_crowd.sensitivity_sweep`.
4. Pick a bundle that stays near-optimal across every prior -- the
   "parameter plateau" principle from the deep-research report.

Every function returns a ``dict[str, float]`` that sums to 1.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from src.manual_rounds.nash_crowd import CrowdCell


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("prior weights must sum to > 0")
    return {name: w / total for name, w in weights.items()}


def uniform_prior(cells: Sequence[CrowdCell]) -> dict[str, float]:
    """Equal share across all cells. Useful as a naive baseline."""
    n = len(cells)
    if n == 0:
        raise ValueError("cells must be non-empty")
    return {c.name: 1.0 / n for c in cells}


def proportional_to_multiplier(
    cells: Sequence[CrowdCell],
    exponent: float = 1.0,
) -> dict[str, float]:
    """Share proportional to ``multiplier ** exponent``.

    Models "crowd flocks to the biggest number on the board". Raise
    ``exponent`` toward 2 or 3 to represent stronger over-concentration.
    Both P3-R2 and P3-R4 exhibited this pattern: the top multipliers
    (89 and 90) were wildly over-picked even though they were dominated
    by mid cells.
    """
    if exponent < 0:
        raise ValueError("exponent must be >= 0")
    weights = {c.name: float(c.multiplier) ** exponent for c in cells}
    return _normalize(weights)


def proportional_to_ratio(
    cells: Sequence[CrowdCell],
    exponent: float = 1.0,
) -> dict[str, float]:
    """Share proportional to ``(multiplier / inhabitants) ** exponent``.

    This models a somewhat smarter crowd that accounts for base
    inhabitants. Often the best "adversarial prior" because it picks
    exactly the cells that look good on paper.
    """
    if exponent < 0:
        raise ValueError("exponent must be >= 0")
    weights = {c.name: (c.multiplier / c.inhabitants) ** exponent for c in cells}
    return _normalize(weights)


def inverse_nash(shares: Mapping[str, float]) -> dict[str, float]:
    """The "anti-Nash" distribution: weight inversely to quantal response.

    Useful as a stress test: if your chosen bundle still makes money
    even when crowds go *opposite* to Nash, you have a robust answer.
    """
    weights: dict[str, float] = {}
    eps = 1e-9
    for name, share in shares.items():
        weights[name] = 1.0 / (share + eps)
    return _normalize(weights)


def concentrated_on(
    cells: Sequence[CrowdCell],
    targets: Iterable[str],
    bleed: float = 0.05,
) -> dict[str, float]:
    """All crowd lands on ``targets``; everyone else gets a small bleed.

    ``bleed`` is the fraction of mass left on non-target cells, spread
    uniformly. Set to 0 for a hard concentration.
    """
    if not 0 <= bleed < 1:
        raise ValueError("bleed must be in [0, 1)")
    names = {c.name for c in cells}
    target_set = set(targets)
    unknown = target_set - names
    if unknown:
        raise ValueError(f"unknown targets: {sorted(unknown)}")
    if not target_set:
        raise ValueError("targets must be non-empty")

    n_cells = len(cells)
    n_targets = len(target_set)
    n_other = n_cells - n_targets

    weights: dict[str, float] = {}
    if n_other > 0:
        other_weight = bleed / n_other
        target_weight = (1.0 - bleed) / n_targets
    else:
        other_weight = 0.0
        target_weight = 1.0 / n_targets
    for c in cells:
        weights[c.name] = target_weight if c.name in target_set else other_weight
    return _normalize(weights)


def nice_number_overlay(
    cells: Sequence[CrowdCell],
    base: Mapping[str, float],
    nice_cell_names: Iterable[str],
    boost: float = 0.2,
) -> dict[str, float]:
    """Tilt ``base`` toward cells whose multiplier is a "nice number".

    The canonical nice number in Prosperity folklore is 37 (a common
    answer to "pick a random number"). Historically this bias has been
    over-estimated: every known season's post-mortem showed the 37 bias
    either failed to materialise or was dominated by other effects.
    Use small ``boost`` values and treat this as a *stress overlay*,
    not a primary model.
    """
    if boost < 0:
        raise ValueError("boost must be >= 0")
    nice = set(nice_cell_names)
    unknown = nice - {c.name for c in cells}
    if unknown:
        raise ValueError(f"unknown nice cells: {sorted(unknown)}")
    weights = {name: w * (1 + boost if name in nice else 1) for name, w in base.items()}
    return _normalize(weights)


def mix_priors(
    priors: Sequence[tuple[float, Mapping[str, float]]],
) -> dict[str, float]:
    """Linearly combine several priors with given weights.

    Each entry is ``(weight, prior_distribution)``. The output is the
    normalised weighted sum. Use this to model the population as a
    mixture: e.g. 60% Nash + 20% concentrated + 10% inverse +
    10% nice-number-biased.
    """
    if not priors:
        raise ValueError("priors must be non-empty")
    if any(w < 0 for w, _ in priors):
        raise ValueError("mixture weights must be non-negative")
    total_w = sum(w for w, _ in priors)
    if total_w <= 0:
        raise ValueError("mixture weights must sum to > 0")

    # Use the first prior's keys as the canonical order and require the
    # others to cover the same set.
    canonical = set(priors[0][1].keys())
    for _, p in priors[1:]:
        if set(p.keys()) != canonical:
            raise ValueError("all priors in a mix must cover the same cell set")

    combined: dict[str, float] = {name: 0.0 for name in canonical}
    for weight, p in priors:
        share = weight / total_w
        for name, value in p.items():
            combined[name] += share * value
    return _normalize(combined)
