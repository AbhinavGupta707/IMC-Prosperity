"""Run the tutorial replay through the live ``Trader`` and print results.

Loads both the price and trade CSVs so the simulator can score passive
fills against observed market trades. Prints the summary table; use
``run_review`` for a persisted review pack.
"""

from __future__ import annotations

from pathlib import Path

from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.trader import Trader

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")


def main() -> None:
    price_files = sorted(_TUTORIAL_DIR.glob("prices_*.csv"))
    trade_files = sorted(_TUTORIAL_DIR.glob("trades_*.csv"))
    if not price_files:
        raise SystemExit(f"No tutorial price files found in {_TUTORIAL_DIR}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)
    simulator = BacktestSimulator(trader=Trader())
    result = simulator.run(replay)

    print(
        f"Loaded {len(replay.steps)} replay steps from "
        f"{len(price_files)} price files and {len(trade_files)} trade files."
    )
    print()
    print(result.summary_table())


if __name__ == "__main__":
    main()
