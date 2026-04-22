"""Diagnostic D8 — Fill-model calibration sweep against R2 Promoted truth.

Uses the shipped R2 `Promoted` bundle (wide_w113 ASH + v5_micro PEPPER)
as a known-truth reference (4 IMC simulator runs, mean profit 7,654).
Sweeps `passive_allocation` and finds the value that reproduces the
truth under our 3-day replay backtest.

If the best fill_rate differs materially from 0.3 (the current default),
every historical sweep result in outputs/round_2/*.json is suspect and
should be rerun.

Output: `outputs/diagnostics/d8_fill_calibration.md`.

Usage:
    PYTHONPATH=. .venv/bin/python -m src.scripts.diagnostics.d8_fill_calibration
"""

from __future__ import annotations

from pathlib import Path

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.simulator import BacktestSimulator
from src.core.primitives.fill_calibration import (
    CalibrationPoint,
    consensus_fill_rate,
    format_sweep,
    sweep_fill_rate,
)
from src.scripts.round_2._runtime import (
    L1_ASH_LADDER_PARAMS,
    V5_MICRO_PEPPER_PARAMS,
    baseline_engine,
    load_round_2_replay,
    wrap_trader_with_v5micro_l1,
)
from src.trader import Trader

_OUTPUT = Path("outputs/diagnostics/d8_fill_calibration.md")


def _run_promoted_at_fill(fill_cfg: FillModelConfig) -> float:
    """Run the R2 Promoted (wide_w113 ASH + v5micro PEPPER) and return total P&L."""
    replay = load_round_2_replay()
    config = baseline_engine(flush_pepper=True)
    trader = Trader(config=config)
    wrap_trader_with_v5micro_l1(
        trader,
        pepper_params=V5_MICRO_PEPPER_PARAMS,
        ash_params=L1_ASH_LADDER_PARAMS,
    )
    sim = BacktestSimulator(trader=trader, fill_model=FillModel(fill_cfg))
    result = sim.run(replay)
    return result.total_pnl


def main() -> None:
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Reference point: R2 Promoted, 4 IMC simulator runs.
    # Truth from outputs/round_2/Official Results/Promoted/*.json:
    #   profits: 8013, 7385, 7923, 7295 → mean 7,654, stdev 366.
    # Each IMC sample = 1 day × 1,000 snapshots = 100k ticks.
    # Our backtest = 3 days × 10,000 snapshots = 300k ticks × 10 snap/tick
    #             = 3,000,000 tick-units.
    # Ratio: 3M backtest ticks / 100k sample ticks = 30× more ticks.
    # So if the backtest is linear in ticks, sim / 30 should ≈ truth.
    promoted = CalibrationPoint(
        label="R2 Promoted (wide_w113) vs 4 IMC simulator runs",
        truth_pnl=7_654.0,
        truth_n_samples=4,
        truth_stdev=366.0,
        scale_to_truth=30.0,  # 3-day backtest tick-count vs 1-day 1k-snapshot IMC sample
    )

    print("running calibration sweep on R2 Promoted...")
    sweep = sweep_fill_rate(
        point=promoted,
        run_simulation_fn=_run_promoted_at_fill,
    )

    # Write report.
    out_lines: list[str] = [
        "# D8 — Fill-Model Calibration Sweep",
        "",
        "Calibrates our backtest's `passive_allocation` parameter against a "
        "known-truth reference: R2 `Promoted` variant with 4 IMC simulator "
        "runs (mean profit **7,654**, σ 366).",
        "",
        "If best fill_rate != 0.3 (the current default), every historical "
        "sweep is biased. **No R3 tuning decision should be made until this "
        "value is calibrated.**",
        "",
        format_sweep(sweep),
        "",
        "## Interpretation",
        "",
        "- **If best fill_rate < 0.3:** our backtest OVER-credits passive fills. "
        "Historical winners are inflated; some may be live losers (like our "
        "wide_w113 experience).",
        "- **If best fill_rate > 0.3:** our backtest UNDER-credits passive fills. "
        "We've been missing good configs.",
        "- **If ±5% tolerance is never reached:** our fill model itself is the "
        "wrong shape, not just miscalibrated. May need a structural fix "
        "(conservative maker matching, bot-specific take rates, etc.).",
        "",
        "## Next step",
        "",
        "1. Adopt the best fill_rate as the new default in `FillModelConfig`.",
        "2. Re-run every historical sweep with the calibrated value.",
        "3. Re-promote based on corrected rankings.",
        "4. Add more reference points if available (port a top-team P3 repo's "
        "published scored P&L as a second anchor).",
    ]

    best = sweep.best_fill_rate()
    if best is not None:
        out_lines.insert(
            3,
            f"**CALIBRATION RESULT: best `passive_allocation` = {best:.2f}** "
            f"(vs current default 0.3).",
        )
        out_lines.insert(4, "")

    _OUTPUT.write_text("\n".join(out_lines) + "\n")
    print(f"wrote {_OUTPUT}")

    if best is not None:
        print(f"\nbest fill_rate: {best:.2f}")
        within = sweep.within_tolerance(5.0)
        if within:
            print(f"within ±5% tolerance: {[r.fill_rate for r in within]}")
        else:
            best_err = min(sweep.results, key=lambda r: r.rel_error)
            print(
                f"best achievable error: {best_err.rel_error * 100:.1f}% at "
                f"fill_rate={best_err.fill_rate:.2f}"
            )


if __name__ == "__main__":
    main()
