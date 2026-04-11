"""Phase 5 — TOMATOES EWMA alpha plateau sweep.

Sweeps ``ewma_alpha`` alone on TOMATOES while holding execution
parameters at the current Phase 3 tuned baseline. Writes a sweep
report under ``outputs/sweeps/<run_id>`` and prints a plateau-focused
alpha-vs-pnl table so Stage 2 of the Phase 5 plan is readable at a
glance.

The sweep is deliberately alpha-only so Stage 2 produces a clean
plateau rather than a muddy multi-axis grid.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.parameter_sweep import (
    ParameterSweepReport,
    SweepRow,
    SweepValue,
    build_parameter_sweep_report,
    write_parameter_sweep_report,
)
from src.backtest.replay_engine import ReplayEngine

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")
_ALPHA_GRID_COARSE: list[float] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9]
_ALPHA_GRID_FINE: list[float] = [0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25, 0.28]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="phase5_tomatoes_alpha", help="run label")
    parser.add_argument("--product", default="TOMATOES", help="product to sweep")
    parser.add_argument(
        "--grid",
        choices=("coarse", "fine"),
        default="coarse",
        help="coarse = 0.1..0.9; fine = localized around the plateau candidate",
    )
    args = parser.parse_args()
    alpha_grid = _ALPHA_GRID_COARSE if args.grid == "coarse" else _ALPHA_GRID_FINE

    price_files = sorted(_TUTORIAL_DIR.glob("prices_*.csv"))
    trade_files = sorted(_TUTORIAL_DIR.glob("trades_*.csv"))
    if not price_files:
        raise SystemExit(f"No tutorial price files found in {_TUTORIAL_DIR}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)

    # Single-axis grid: alpha only. fair_value_method is pinned to
    # ewma_mid as a single-element axis so the sweep infrastructure's
    # dataclasses.replace() call rewrites the product config correctly
    # and so the baseline row (current weighted_mid) is a meaningful
    # contrast when read side-by-side with the report.
    grid: dict[str, list[SweepValue]] = {
        "fair_value_method": ["ewma_mid"],
        "ewma_alpha": list(alpha_grid),
    }
    report = build_parameter_sweep_report(
        replay,
        product=args.product,
        grid=grid,
        run_label=args.label,
    )
    directory = write_parameter_sweep_report(report)

    print(f"Wrote parameter sweep report to {directory}")
    print(f"grid: {args.grid}")
    print()
    _print_plateau_table(report)


def _print_plateau_table(report: ParameterSweepReport) -> None:
    """Print an alpha-vs-pnl plateau table keyed to the EWMA axis only."""
    print(f"EWMA alpha plateau: {report.product}")
    print(f"run_label: {report.run_label}")
    print(f"incumbent method: {report.fair_value_method}")
    print()

    header = f"{'alpha':>6} {'pnl':>10} {'trades':>7} {'mk%':>6} " f"{'near':>5} {'pos':>4}"
    print(header)
    print("-" * len(header))

    baseline_label = (
        f"{'n/a':>6} {report.baseline.pnl:>10.2f} "
        f"{report.baseline.trade_count:>7d} "
        f"{_fmt_maker_share(report.baseline.maker_share):>6} "
        f"{report.baseline.steps_near_limit:>5d} "
        f"{report.baseline.final_position:>4d}"
        f"   <- incumbent ({report.fair_value_method})"
    )
    print(baseline_label)

    for row in _sort_by_alpha(report.rows):
        alpha = row.params.get("ewma_alpha")
        print(
            f"{alpha!s:>6} {row.pnl:>10.2f} {row.trade_count:>7d} "
            f"{_fmt_maker_share(row.maker_share):>6} "
            f"{row.steps_near_limit:>5d} {row.final_position:>4d}"
        )
    print("-" * len(header))


def _sort_by_alpha(rows: tuple[SweepRow, ...]) -> list[SweepRow]:
    def key(row: SweepRow) -> float:
        alpha = row.params.get("ewma_alpha")
        return float(alpha) if isinstance(alpha, (int, float)) else -1.0

    return sorted(rows, key=key)


def _fmt_maker_share(value: float | None) -> str:
    return f"{value * 100:.1f}" if value is not None else "n/a"


if __name__ == "__main__":
    main()
