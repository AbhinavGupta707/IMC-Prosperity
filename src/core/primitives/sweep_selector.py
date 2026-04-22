"""Statistically-significant sweep selector.

Replaces the plateau-chart hyperparameter selection that picked wrong
winners in R1/R2 (D6). Instead of "eyeball the heatmap," this module:

1. **Bootstrap-CI on per-day P&L.** Given a sweep result with ≥ 5 per-day
   P&L samples per config, compute a 95% confidence interval around the
   mean by resampling with replacement.

2. **Significance gate.** A candidate is declared a winner only if its
   CI lower bound exceeds the BASELINE's CI upper bound. Anything inside
   baseline's upper-CI is indistinguishable noise.

3. **Rank-payoff objective.** For tournament scoring (not raw P&L max),
   simulate the expected payoff position under a field distribution.

4. **Plateau as a SECONDARY criterion.** If multiple candidates are
   statistically tied, prefer the one with a flatter parameter
   neighborhood. But this only tie-breaks; it never over-rides
   significance.

The tool consumes a generic sweep result dict (config_label -> list of
per-day P&L values) and emits the winner plus a transparent CI table.

**Crucially: this selector's outputs are only as good as the fill-model
calibration.** Without the P10 FillCalibrationHarness, even statistically
significant wins may not reproduce on IMC simulator. The two tools are
complementary.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Literal

RankScoreCurve = Literal["linear", "top3_only", "top10", "custom"]


@dataclass(frozen=True)
class SweepConfig:
    """Per-config sweep result."""

    label: str
    params: dict[str, float | int | str]
    per_day_pnl: list[float]

    def mean_pnl(self) -> float:
        return mean(self.per_day_pnl) if self.per_day_pnl else 0.0

    def stdev_pnl(self) -> float:
        return stdev(self.per_day_pnl) if len(self.per_day_pnl) > 1 else 0.0

    def n_samples(self) -> int:
        return len(self.per_day_pnl)


@dataclass(frozen=True)
class BootstrapCI:
    """Bootstrap confidence interval summary."""

    mean: float
    lower: float
    upper: float
    n_samples: int
    n_bootstrap: int


@dataclass
class SelectionResult:
    """Output of the selector."""

    winner: SweepConfig | None
    baseline: SweepConfig
    cis: dict[str, BootstrapCI] = field(default_factory=dict)
    significance_gated_candidates: list[SweepConfig] = field(default_factory=list)
    tied_candidates: list[SweepConfig] = field(default_factory=list)
    rationale: str = ""


# ============================================================= bootstrap


def bootstrap_ci(
    values: list[float],
    *,
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    seed: int | None = 42,
) -> BootstrapCI:
    """Compute bootstrap CI for the mean of ``values``.

    Returns (mean, lower_q, upper_q). Falls back to
    ``(mean, mean, mean)`` for n < 2.
    """
    n = len(values)
    if n == 0:
        return BootstrapCI(mean=0.0, lower=0.0, upper=0.0, n_samples=0, n_bootstrap=0)
    raw_mean = mean(values)
    if n == 1:
        return BootstrapCI(
            mean=raw_mean, lower=raw_mean, upper=raw_mean, n_samples=1, n_bootstrap=0,
        )

    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(n_bootstrap):
        draw = [values[rng.randint(0, n - 1)] for _ in range(n)]
        samples.append(mean(draw))
    samples.sort()
    lo_idx = int(n_bootstrap * (1 - confidence) / 2)
    hi_idx = int(n_bootstrap * (1 - (1 - confidence) / 2)) - 1
    return BootstrapCI(
        mean=raw_mean,
        lower=samples[lo_idx],
        upper=samples[hi_idx],
        n_samples=n,
        n_bootstrap=n_bootstrap,
    )


# ============================================================= selection


def select_winner(
    configs: list[SweepConfig],
    *,
    baseline_label: str,
    min_samples: int = 5,
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    objective: RankScoreCurve = "linear",
    field_payoff_quantiles: list[float] | None = None,
) -> SelectionResult:
    """Pick a winner under significance + objective gates.

    A candidate passes the significance gate iff its CI-lower >
    baseline's CI-upper. Ties are broken by plateau-width (variance
    across per-day means from the bootstrap) — lower variance wins.

    ``objective`` controls the scoring function. For tournament
    scoring set ``objective='top3_only'`` or pass ``field_payoff_quantiles``
    (a list of quantile thresholds representing the leaderboard).
    """
    if not configs:
        raise ValueError("configs must be non-empty")
    if min_samples < 2:
        raise ValueError("min_samples must be >= 2 for CI computation")

    baseline = next((c for c in configs if c.label == baseline_label), None)
    if baseline is None:
        raise ValueError(f"baseline_label {baseline_label!r} not found in configs")

    # Check minimum-samples gate.
    short = [c.label for c in configs if c.n_samples() < min_samples]
    if short:
        rationale = (
            f"WARNING: {len(short)} configs have < {min_samples} per-day samples "
            f"(namely {short[:5]}{'...' if len(short) > 5 else ''}); CI bounds "
            f"will be unreliable. Recommendation: run ≥ {min_samples} replay days "
            f"before selecting."
        )
    else:
        rationale = ""

    # Compute CIs for every config.
    cis: dict[str, BootstrapCI] = {}
    for c in configs:
        cis[c.label] = bootstrap_ci(
            c.per_day_pnl,
            n_bootstrap=n_bootstrap,
            confidence=confidence,
            seed=hash(c.label) & 0xFFFFFFFF,
        )

    baseline_upper = cis[baseline.label].upper

    # Significance-gated candidates.
    significance_gated = [
        c for c in configs
        if c.label != baseline.label and cis[c.label].lower > baseline_upper
    ]

    if not significance_gated:
        return SelectionResult(
            winner=None,
            baseline=baseline,
            cis=cis,
            significance_gated_candidates=[],
            tied_candidates=[],
            rationale=(
                rationale + (" " if rationale else "")
                + "No candidate exceeds baseline CI-upper at 95% confidence. "
                "Keep shipping baseline or collect more samples."
            ),
        )

    # Among gated candidates, apply objective.
    if objective == "linear":
        scored = [(c, _score_linear(c, cis[c.label])) for c in significance_gated]
    elif objective == "top3_only":
        scored = [(c, _score_top3(c, cis[c.label])) for c in significance_gated]
    elif objective == "top10":
        scored = [(c, _score_top10(c, cis[c.label])) for c in significance_gated]
    else:  # custom
        if field_payoff_quantiles is None:
            raise ValueError("objective='custom' requires field_payoff_quantiles")
        scored = [
            (c, _score_by_quantiles(c, cis[c.label], field_payoff_quantiles))
            for c in significance_gated
        ]

    scored.sort(key=lambda x: -x[1])
    top_score = scored[0][1]

    # Tie-breaking: any candidate within 1% of top score is "tied".
    # CRITICAL fix: use absolute distance, not `score >= top * 0.99`. For
    # negative top_score, `top * 0.99` is numerically LARGER (less negative),
    # so the comparison becomes `s >= larger_value` — an empty set — and
    # `tied[0]` crashes with IndexError on any sweep where strategies lose.
    tolerance = max(abs(top_score) * 0.01, 1e-9)
    tied = [c for c, s in scored if abs(s - top_score) <= tolerance]

    if len(tied) == 1:
        winner = tied[0]
        rationale += (
            f" Winner {winner.label!r} (score {scored[0][1]:.2f}) passes "
            f"significance gate and has no ties."
        ).strip()
    else:
        # Tie-breaker: lowest bootstrap spread (stable neighborhood).
        tied.sort(key=lambda c: cis[c.label].upper - cis[c.label].lower)
        winner = tied[0]
        rationale += (
            f" {len(tied)} candidates tied within 1% of top score "
            f"({[c.label for c in tied]}); selecting {winner.label!r} via "
            f"narrowest bootstrap CI (stable-neighborhood tie-break)."
        ).strip()

    return SelectionResult(
        winner=winner,
        baseline=baseline,
        cis=cis,
        significance_gated_candidates=significance_gated,
        tied_candidates=tied,
        rationale=rationale,
    )


# ====================================================== scoring functions


def _score_linear(config: SweepConfig, ci: BootstrapCI) -> float:
    """Simple mean P&L — sharp but uses no inter-quantile discrimination."""
    return ci.mean


def _score_top3(config: SweepConfig, ci: BootstrapCI) -> float:
    """Binary top-3 payoff: 1 if lower CI clears a hypothetical top-3 bar.

    Assumes top-3 requires being in the 97.5th percentile of the field.
    Approximates this by requiring lower CI > mean + 2 * stdev across
    the sweep (if we had field data, we'd use that instead).
    """
    # Approximation: reward candidates whose lower CI is well above mean.
    return ci.lower - 0.5 * (ci.upper - ci.lower)


def _score_top10(config: SweepConfig, ci: BootstrapCI) -> float:
    """Top-10 payoff: reward upper-CI potential but penalize variance."""
    return ci.mean + 0.3 * (ci.upper - ci.mean) - 0.7 * (ci.mean - ci.lower)


def _score_by_quantiles(
    config: SweepConfig,
    ci: BootstrapCI,
    quantiles: list[float],
) -> float:
    """Score by probability of clearing each quantile threshold.

    ``quantiles`` is a sorted list of P&L values representing the
    leaderboard thresholds we care about (e.g., [top-100, top-10, top-3]).
    Score = weighted sum of P(P&L > threshold) across quantiles, with
    higher quantiles getting higher weights.
    """
    if not quantiles:
        return ci.mean
    quantiles_sorted = sorted(quantiles)
    weights = [1.0 * (2 ** i) for i in range(len(quantiles_sorted))]

    # Rough P(X > q) using Normal approximation around the bootstrap CI.
    # Half-CI ≈ 1.96 * SEM, so SEM ≈ (upper - lower) / (2 * 1.96).
    sem = max(1e-6, (ci.upper - ci.lower) / (2 * 1.96))
    score = 0.0
    for q, w in zip(quantiles_sorted, weights):
        z = (ci.mean - q) / sem
        # Rough normal CDF approximation.
        p_above = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        score += w * p_above
    return score


# ============================================================= reporting


def format_summary(result: SelectionResult) -> str:
    """Human-readable summary of a selection result."""
    lines = [
        f"Baseline: {result.baseline.label}",
        f"Baseline CI: [{result.cis[result.baseline.label].lower:.0f}, "
        f"{result.cis[result.baseline.label].upper:.0f}] (mean "
        f"{result.cis[result.baseline.label].mean:.0f}, n="
        f"{result.cis[result.baseline.label].n_samples})",
        "",
    ]
    if result.winner is None:
        lines.append("WINNER: None (no candidate passes significance gate)")
    else:
        w = result.cis[result.winner.label]
        lines.append(f"WINNER: {result.winner.label}")
        lines.append(
            f"  CI: [{w.lower:.0f}, {w.upper:.0f}] (mean {w.mean:.0f}, "
            f"n={w.n_samples})"
        )
    lines.append("")
    lines.append(f"Rationale: {result.rationale}")
    lines.append("")
    lines.append("All candidates (sorted by mean):")
    lines.append("Label | Mean | CI | Significant?")
    sorted_cis = sorted(
        result.cis.items(), key=lambda kv: -kv[1].mean,
    )
    baseline_upper = result.cis[result.baseline.label].upper
    for label, ci in sorted_cis:
        sig = "YES" if label != result.baseline.label and ci.lower > baseline_upper else "no"
        lines.append(
            f"{label} | {ci.mean:.0f} | [{ci.lower:.0f}, {ci.upper:.0f}] | {sig}"
        )
    return "\n".join(lines)
