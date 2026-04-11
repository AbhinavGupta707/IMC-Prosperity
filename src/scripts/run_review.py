"""Generate and persist a review pack for the tutorial replay.

Writes ``outputs/review_packs/<run_id>/summary.json`` and
``summary.txt`` and prints the target directory. Pass ``--label`` to
tag the run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.replay_engine import ReplayEngine
from src.backtest.reporting import write_review_pack
from src.backtest.simulator import BacktestSimulator
from src.trader import Trader

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="tutorial_round_1", help="run label")
    args = parser.parse_args()

    price_files = sorted(_TUTORIAL_DIR.glob("prices_*.csv"))
    trade_files = sorted(_TUTORIAL_DIR.glob("trades_*.csv"))
    if not price_files:
        raise SystemExit(f"No tutorial price files found in {_TUTORIAL_DIR}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)
    simulator = BacktestSimulator(trader=Trader())
    result = simulator.run(replay)

    directory = write_review_pack(result, run_label=args.label)
    print(f"Wrote review pack to {directory}")
    print()
    print(result.summary_table())


if __name__ == "__main__":
    main()
