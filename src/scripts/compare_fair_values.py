"""Compare fair-value estimators on the tutorial replay data.

Writes a metrics report under ``outputs/fair_value_comparison/<run_id>``
and prints the summary table to stdout.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.fair_value_compare import (
    DEFAULT_COMPARISON_ESTIMATORS,
    build_fair_value_report,
    write_fair_value_report,
)
from src.backtest.replay_engine import ReplayEngine
from src.core.fair_value import ESTIMATORS

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")


def _parse_estimators(raw: str) -> tuple[str, ...]:
    names = tuple(name.strip() for name in raw.split(",") if name.strip())
    if not names:
        raise argparse.ArgumentTypeError("--estimators must list at least one estimator")
    unknown = [name for name in names if name not in ESTIMATORS]
    if unknown:
        available = ", ".join(sorted(ESTIMATORS))
        raise argparse.ArgumentTypeError(
            f"unknown estimators: {unknown}; available: {available}"
        )
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="tutorial_round_1", help="run label")
    parser.add_argument(
        "--estimators",
        type=_parse_estimators,
        default=DEFAULT_COMPARISON_ESTIMATORS,
        help=(
            "comma-separated list of estimators to compare "
            "(default: full lineup). Example: mid,rolling_mid,weighted_mid,ewma_mid"
        ),
    )
    args = parser.parse_args()

    price_files = sorted(_TUTORIAL_DIR.glob("prices_*.csv"))
    trade_files = sorted(_TUTORIAL_DIR.glob("trades_*.csv"))
    if not price_files:
        raise SystemExit(f"No tutorial price files found in {_TUTORIAL_DIR}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)
    report = build_fair_value_report(
        replay,
        run_label=args.label,
        estimator_names=args.estimators,
    )
    directory = write_fair_value_report(report)

    print(f"Wrote fair value comparison report to {directory}")
    print()
    print(report.summary_text())


if __name__ == "__main__":
    main()
