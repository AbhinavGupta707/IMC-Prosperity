"""Fill-model calibration harness (P10 in R3+_ENGINE_ARCHITECTURE).

Without this, every backtest lies to us. D5 proved our sweep winners
are noise-selected under biased `passive_allocation=0.3`. Before any
R3 sweep decision, we must know the value of `passive_allocation`
that makes our backtest reproduce a known-good reference result.

**Procedure:**

1. Find a reference dataset where we know both:
   - The strategy's output P&L under IMC simulator (truth), and
   - A machine-readable version of that strategy's code we can run
     through our `BacktestSimulator`.

2. Sweep `passive_allocation ∈ {0.05, 0.10, 0.15, 0.20, 0.25, 0.30,
   0.40, 0.50}` — running the reference strategy through our sim at
   each value.

3. Find the value that minimizes |simulated - truth| / |truth|. Adopt
   that as the calibrated fill rate.

**Reference datasets we can use:**

- **Our own R2 `Promoted` variant** (the shipped wide_w113 bundle) —
  4 IMC simulator runs with mean 7,654 ± 366. Our backtest on the
  same config currently reports 249,375 total (≈ 10× the sample).
  If scaled: sim/10 ≈ 24,937 vs IMC 7,654. Ratio: 3.26× over-predict.

- **Port chrispyroberts R2/R3 code** (if we can get the repo cleanly).
  His published live P&L per round gives a known-truth anchor.

This harness implements the machinery for BOTH. For now, the first
reference (our own R2 promoted) is always available. External-repo
calibration is a stretch goal that can be added without breaking the
primary flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.backtest.fill_model import FillModelConfig
from src.backtest.simulator import BacktestSimulator


@dataclass(frozen=True)
class CalibrationPoint:
    """One reference data point for fill-model calibration."""

    label: str
    """Human-readable name (e.g., 'R2 Promoted', 'chrispyroberts_R1')."""

    truth_pnl: float
    """The reference's IMC-simulator P&L (mean across N runs)."""

    truth_n_samples: int
    """How many IMC simulator runs contributed to truth_pnl."""

    truth_stdev: float
    """Stdev of the IMC simulator runs. Used for tolerance."""

    scale_to_truth: float = 1.0
    """If truth_pnl is 1-day 1000-snapshot sample and our backtest is
    3-day 10,000-snapshot (30× truth in ticks), set scale=30 so the
    comparison is apples-to-apples."""


@dataclass(frozen=True)
class CalibrationResult:
    """One (fill_rate, simulated_pnl) measurement for a calibration point."""

    fill_rate: float
    simulated_pnl_raw: float
    simulated_pnl_scaled: float  # raw / point.scale_to_truth
    truth_pnl: float
    abs_error: float  # |simulated_scaled - truth|
    rel_error: float  # abs_error / |truth|


@dataclass
class CalibrationSweep:
    """Result of sweeping fill_rate against one reference point."""

    point: CalibrationPoint
    results: list[CalibrationResult] = field(default_factory=list)

    def best_fill_rate(self) -> float | None:
        if not self.results:
            return None
        best = min(self.results, key=lambda r: r.abs_error)
        return best.fill_rate

    def within_tolerance(self, tolerance_pct: float = 5.0) -> list[CalibrationResult]:
        """Return fill rates whose simulated P&L is within ±tolerance_pct% of truth."""
        return [r for r in self.results if r.rel_error * 100 <= tolerance_pct]


# =========================================================== harness API


def sweep_fill_rate(
    *,
    point: CalibrationPoint,
    run_simulation_fn,  # Callable[[FillModelConfig], float]  returning raw total P&L
    fill_rates: list[float] | None = None,
) -> CalibrationSweep:
    """Sweep ``passive_allocation`` values against a reference P&L.

    ``run_simulation_fn`` is a user-supplied closure that constructs a
    trader + replay and runs ``BacktestSimulator.run()`` with the given
    `FillModelConfig`, returning the total P&L. This keeps the harness
    decoupled from any specific trader/strategy setup.
    """
    if fill_rates is None:
        fill_rates = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]

    sweep = CalibrationSweep(point=point)
    for fr in fill_rates:
        fm = FillModelConfig(passive_allocation=fr)
        simulated_raw = run_simulation_fn(fm)
        simulated_scaled = simulated_raw / max(1e-9, point.scale_to_truth)
        abs_err = abs(simulated_scaled - point.truth_pnl)
        rel_err = abs_err / max(1e-9, abs(point.truth_pnl))
        sweep.results.append(
            CalibrationResult(
                fill_rate=fr,
                simulated_pnl_raw=simulated_raw,
                simulated_pnl_scaled=simulated_scaled,
                truth_pnl=point.truth_pnl,
                abs_error=abs_err,
                rel_error=rel_err,
            )
        )
    return sweep


def consensus_fill_rate(sweeps: list[CalibrationSweep]) -> float | None:
    """If multiple reference points agree within tolerance, return the consensus.

    Picks the fill_rate whose AVERAGE rel_error across all sweeps is
    minimized. Warns if no single fill_rate is within tolerance on all
    reference points.
    """
    if not sweeps:
        return None
    # All sweeps must have used the same set of fill_rates.
    rates = [r.fill_rate for r in sweeps[0].results]
    avg_errors: dict[float, float] = {}
    for rate in rates:
        errs = []
        for sweep in sweeps:
            match = next((r for r in sweep.results if r.fill_rate == rate), None)
            if match is None:
                continue
            errs.append(match.rel_error)
        if errs:
            avg_errors[rate] = sum(errs) / len(errs)
    if not avg_errors:
        return None
    return min(avg_errors, key=lambda r: avg_errors[r])


# ======================================================= reporting


def format_sweep(sweep: CalibrationSweep) -> str:
    """Markdown-friendly summary of a sweep."""
    p = sweep.point
    lines = [
        f"## Calibration sweep: {p.label}",
        "",
        f"- Truth: {p.truth_pnl:.0f} (n={p.truth_n_samples}, σ={p.truth_stdev:.0f})",
        f"- Scale factor (backtest ticks / truth ticks): {p.scale_to_truth:.1f}",
        "",
        "| fill_rate | sim_raw | sim_scaled | truth | abs_err | rel_err |",
        "|---|---|---|---|---|---|",
    ]
    for r in sweep.results:
        lines.append(
            f"| {r.fill_rate:.2f} | {r.simulated_pnl_raw:,.0f} | "
            f"{r.simulated_pnl_scaled:,.0f} | {r.truth_pnl:,.0f} | "
            f"{r.abs_error:,.0f} | {r.rel_error * 100:.1f}% |"
        )
    best = sweep.best_fill_rate()
    within = sweep.within_tolerance(5.0)
    lines.append("")
    if best is not None:
        lines.append(f"**Best fill_rate:** {best:.2f} (minimizes absolute error)")
    if within:
        lines.append(
            f"**Within ±5% tolerance:** "
            f"{[r.fill_rate for r in within]}"
        )
    else:
        lines.append(
            f"**Within ±5% tolerance:** none — the best we can do is "
            f"{min(sweep.results, key=lambda r: r.rel_error).rel_error * 100:.1f}% error"
        )
    return "\n".join(lines)
