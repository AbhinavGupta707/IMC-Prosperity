"""Run a focused parameter sweep for the tutorial replay baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.parameter_sweep import (
    SweepValue,
    build_parameter_sweep_report,
    write_parameter_sweep_report,
)
from src.backtest.replay_engine import ReplayEngine

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")
_TOMATOES_GRID: dict[str, list[SweepValue]] = {
    "maker_edge": [1.0, 2.0, 3.0],
    "taker_edge": [1.0, 2.0],
    "inventory_skew": [2.0, 2.5, 3.0],
    "flatten_threshold": [0.65, 0.7, 0.75],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="tomatoes_depth_mid", help="run label")
    parser.add_argument("--product", default="TOMATOES", help="product to sweep")
    args = parser.parse_args()

    price_files = sorted(_TUTORIAL_DIR.glob("prices_*.csv"))
    trade_files = sorted(_TUTORIAL_DIR.glob("trades_*.csv"))
    if not price_files:
        raise SystemExit(f"No tutorial price files found in {_TUTORIAL_DIR}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)
    report = build_parameter_sweep_report(
        replay,
        product=args.product,
        grid=_TOMATOES_GRID,
        run_label=args.label,
    )
    directory = write_parameter_sweep_report(report)

    print(f"Wrote parameter sweep report to {directory}")
    print()
    print(report.summary_text())


if __name__ == "__main__":
    main()
