"""Phase 6 — TOMATOES cross-slice parameter sweep (three sub-sweeps).

Three independent sub-sweeps are run on TOMATOES across three
tutorial slices (``day_-2``, ``day_-1``, combined):

1. **Sub-sweep A — ``weighted_mid``** (incumbent family). Promotion-eligible.
   Sweeps execution axes only; ``history_length`` is pinned at the
   current default (48) because ``weighted_mid``'s LOOKBACK is hard-capped
   at 4 (``src/core/fair_value.py:123``) and history_length is a no-op
   for any value >= 4.
2. **Sub-sweep B — ``rolling_mid``** (history-sensitive). Promotion-eligible.
   Adds ``history_length`` because ``rolling_mid`` consumes the entire
   ``recent_mids`` ring buffer.
3. **Sub-sweep C — ``ewma_mid`` at fixed ``alpha=0.20``**. **Diagnostic-only.**
   Validates whether the Phase 5 narrow-peak finding survives cross-day
   slices. Phase 6 does NOT promote EWMA regardless of cross-day
   behaviour. ``ewma_alpha=0.20`` is a Phase 5 validation pin, not a
   tuned Phase 6 parameter.

Sub-sweep C is intentionally excluded from the product-level
``compare_subsweep_winners`` step. Sub-sweeps are intersected
**independently**: pooling them into one product-level plateau would
muddy the bands because sub-sweep A has no history axis while B and C
do.

Heatmaps are rendered per slice as a non-blocking diagnostic. See
``Tutorial/Implementation Plan.md:649`` and the robustness note
(``docs/phase_6_robustness_note.md``) for context.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.parameter_sweep import (
    ParameterSweepReport,
    SweepValue,
    build_parameter_sweep_report,
)
from src.backtest.plateau import (
    Phase6CrossSliceReport,
    compare_subsweep_winners,
    intersect_plateaus,
    write_phase6_cross_slice_report,
    write_product_comparison,
)
from src.backtest.plateau_charts import render_plateau_heatmaps
from src.backtest.replay_engine import ReplayEngine

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")
_PRODUCT = "TOMATOES"

# Sub-sweep grids ------------------------------------------------------------
#
# A — weighted_mid: incumbent family, execution-only sweep. history_length
# is a single-element axis at the current default (48) because the
# WeightedMidEstimator hard-caps its LOOKBACK at 4, making history_length
# a no-op on this estimator for any value >= 4 (src/core/fair_value.py:123).
_SUB_A_GRID: dict[str, list[SweepValue]] = {
    "fair_value_method": ["weighted_mid"],
    "history_length": [48],
    "maker_edge": [1.0, 2.0],
    "taker_edge": [1.0, 2.0],
    "inventory_skew": [2.0, 2.5, 3.0, 3.5],
}

# B — rolling_mid: history-sensitive (uses the entire recent_mids buffer).
_SUB_B_GRID: dict[str, list[SweepValue]] = {
    "fair_value_method": ["rolling_mid"],
    "history_length": [16, 32, 48, 64],
    "maker_edge": [1.0, 2.0],
    "taker_edge": [1.0, 2.0],
    "inventory_skew": [2.0, 2.5, 3.0, 3.5],
}

# C — ewma_mid at fixed alpha=0.20 (Phase 5 validation pin, not a Phase 6
# tunable parameter). Diagnostic-only — never promotes.
_SUB_C_GRID: dict[str, list[SweepValue]] = {
    "fair_value_method": ["ewma_mid"],
    "ewma_alpha": [0.20],
    "history_length": [16, 32, 48, 64],
    "maker_edge": [1.0, 2.0],
    "taker_edge": [1.0, 2.0],
    "inventory_skew": [2.0, 2.5, 3.0, 3.5],
}

_SUB_SWEEPS: tuple[tuple[str, dict[str, list[SweepValue]], str], ...] = (
    ("weighted_mid", _SUB_A_GRID, "promotion_eligible"),
    ("rolling_mid", _SUB_B_GRID, "promotion_eligible"),
    ("ewma_mid_alpha_020", _SUB_C_GRID, "diagnostic"),
)

_HEATMAP_X = "maker_edge"
_HEATMAP_Y = "inventory_skew"

_SLICES: dict[str, tuple[list[Path], list[Path]]] = {
    "day_-2": (
        [_TUTORIAL_DIR / "prices_round_0_day_-2.csv"],
        [_TUTORIAL_DIR / "trades_round_0_day_-2.csv"],
    ),
    "day_-1": (
        [_TUTORIAL_DIR / "prices_round_0_day_-1.csv"],
        [_TUTORIAL_DIR / "trades_round_0_day_-1.csv"],
    ),
    "combined": (
        [
            _TUTORIAL_DIR / "prices_round_0_day_-2.csv",
            _TUTORIAL_DIR / "prices_round_0_day_-1.csv",
        ],
        [
            _TUTORIAL_DIR / "trades_round_0_day_-2.csv",
            _TUTORIAL_DIR / "trades_round_0_day_-1.csv",
        ],
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 TOMATOES cross-slice parameter sweep (three sub-sweeps)"
    )
    parser.add_argument("--label", default="phase6_tomatoes", help="run label")
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="skip heatmap rendering (plateau logic still runs)",
    )
    args = parser.parse_args()

    run_id = _resolve_run_id(args.label, product=_PRODUCT)
    cross_reports: list[Phase6CrossSliceReport] = []

    for sub_sweep_name, grid, role in _SUB_SWEEPS:
        per_slice_reports = _run_slices(
            label=args.label,
            sub_sweep_name=sub_sweep_name,
            grid=grid,
        )
        cross = intersect_plateaus(
            per_slice_reports,
            product=_PRODUCT,
            sub_sweep=sub_sweep_name,
            role=role,
            run_label=args.label,
        )
        sub_sweep_dir = write_phase6_cross_slice_report(
            cross,
            per_slice_reports,
            run_id=run_id,
        )
        if not args.no_charts:
            _render_heatmaps(
                per_slice_reports,
                sub_sweep_dir,
                sub_sweep_name=sub_sweep_name,
            )

        cross_reports.append(cross)
        print(f"\n=== sub-sweep {sub_sweep_name} ===")
        print(cross.summary_text())

    comparison = compare_subsweep_winners(tuple(cross_reports))
    write_product_comparison(comparison, run_id=run_id)
    print("\n=== product-level comparison ===")
    print(comparison.summary_text())


def _run_slices(
    *,
    label: str,
    sub_sweep_name: str,
    grid: dict[str, list[SweepValue]],
) -> dict[str, ParameterSweepReport]:
    reports: dict[str, ParameterSweepReport] = {}
    for slice_name, (price_paths, trade_paths) in _SLICES.items():
        if not all(path.exists() for path in price_paths):
            raise SystemExit(
                f"Tutorial price files missing for slice {slice_name!r}; "
                f"expected under {_TUTORIAL_DIR}"
            )
        replay = ReplayEngine.from_files(
            price_paths=price_paths,
            trade_paths=trade_paths,
        )
        reports[slice_name] = build_parameter_sweep_report(
            replay,
            product=_PRODUCT,
            grid=grid,
            run_label=f"{label}_{sub_sweep_name}_{slice_name}",
        )
    return reports


def _render_heatmaps(
    per_slice_reports: dict[str, ParameterSweepReport],
    sub_sweep_dir: Path,
    *,
    sub_sweep_name: str,
) -> None:
    heatmap_dir = sub_sweep_dir / "heatmaps"
    for slice_name, report in per_slice_reports.items():
        try:
            render_plateau_heatmaps(
                report,
                x_axis=_HEATMAP_X,
                y_axis=_HEATMAP_Y,
                slice_name=slice_name,
                out_dir=heatmap_dir,
            )
        except Exception as exc:
            # Heatmaps are non-blocking per the Phase 6 plan.
            print(
                f"[phase6 tomatoes/{sub_sweep_name}] heatmap render failed "
                f"for {slice_name}: {exc}; continuing (plateau artifacts still written)"
            )


def _resolve_run_id(label: str, *, product: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    clean = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in f"{label}_{product.lower()}"
    )
    return f"{stamp}_{clean}" if clean else stamp


if __name__ == "__main__":
    main()
