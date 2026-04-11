"""Generate a review pack for the tutorial replay.

Phase 2A placeholder: runs the simulator, prints the review pack dict.
Phase 2B will persist the pack under ``outputs/review_packs/`` and add
charts.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.backtest.replay_engine import ReplayEngine
from src.backtest.reporting import build_review_pack
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
    pack = build_review_pack(result)
    print(json.dumps(pack, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
