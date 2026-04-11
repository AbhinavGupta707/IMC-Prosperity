"""Run the tutorial replay through the live ``Trader`` and print results.

This is the Phase 2A end-to-end backtest entrypoint. It is deliberately
small: load CSVs, build a replay engine, run the simulator, print a
summary table. Richer reporting and review packs land in Phase 2B.
"""

from __future__ import annotations

from pathlib import Path

from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.trader import Trader

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")


def main() -> None:
    price_files = sorted(_TUTORIAL_DIR.glob("prices_*.csv"))
    if not price_files:
        raise SystemExit(f"No tutorial price files found in {_TUTORIAL_DIR}")

    replay = ReplayEngine.from_price_files(price_files)
    simulator = BacktestSimulator(trader=Trader())
    result = simulator.run(replay)

    print(f"Loaded {len(replay.steps)} replay steps from {len(price_files)} files.")
    print()
    print(result.summary_table())


if __name__ == "__main__":
    main()
