"""3-day 1M-tick cross-validation harness for Round 1 PEPPER strategies.

Replaces the 100k day-0 proxy with a 3-fold evaluation across days
-2, -1, 0 (each 1M ticks at 100-tick cadence = 10000 snapshots).

Scoring: mean PnL across 3 folds, with min / max / std recorded to
surface robustness. All candidates routed through the same
_base_engine (wall_mid ASH + PEPPER with max_aggressive_size=20)
so ASH contribution is constant; PEPPER is the only moving part.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean, pstdev

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    round1_h1_engine_config,
    round1_test_engine_config,
)
from src.core.state_store import InMemoryStateStore
from src.strategies.base import BaseStrategy, StrategyContext
from src.strategies.buy_and_hold import BuyAndHoldStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.pepper_core_long import (
    CoreLongParams,
    PepperCoreLongStrategy,
)
from src.trader import Trader

DATA = Path("data/raw/round_1")
PEPPER = "INTARIAN_PEPPER_ROOT"
ASH = "ASH_COATED_OSMIUM"
FOLDS = (-2, -1, 0)


class _PerProductStrategy(BaseStrategy):
    def __init__(self, by_product: dict[str, BaseStrategy]) -> None:
        self.by_product = by_product

    def generate_intent(self, ctx: StrategyContext):  # type: ignore[override]
        return self.by_product[ctx.product].generate_intent(ctx)


def base_engine() -> EngineConfig:
    base = round1_h1_engine_config()
    products = dict(base.products)
    pep = products[PEPPER]
    products[PEPPER] = replace(pep, max_aggressive_size=20, quote_size=10)
    return EngineConfig(
        state_version=base.state_version,
        max_trader_data_chars=base.max_trader_data_chars,
        diagnostics_verbosity=base.diagnostics_verbosity,
        products=products,
        scanner_config=base.scanner_config,
        residual_config=base.residual_config,
    )


@dataclass(frozen=True)
class Candidate:
    label: str
    engine: EngineConfig
    pepper_params: CoreLongParams | None
    note: str


def _load_day_replay(day: int) -> ReplayEngine:
    price_files = [DATA / f"prices_round_1_day_{day}.csv"]
    trade_files = [DATA / f"trades_round_1_day_{day}.csv"]
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)


def _research_engine(engine: EngineConfig) -> EngineConfig:
    return replace(
        engine,
        scanner_config=replace(engine.scanner_config, enabled=False),
    )


def _research_trader(engine: EngineConfig) -> Trader:
    research_engine = _research_engine(engine)
    return Trader(
        config=research_engine,
        state_store=InMemoryStateStore(
            version=research_engine.state_version,
            max_chars=research_engine.max_trader_data_chars,
        ),
    )


def _run_candidate(cand: Candidate, replay: ReplayEngine) -> SimulationResult:
    trader = _research_trader(cand.engine)
    if cand.pepper_params is not None:
        fve, sig = trader.fair_value_engine, trader.signal_engine
        mm = MarketMakingStrategy(fve, sig)
        cl = PepperCoreLongStrategy(fve, sig, cand.pepper_params)
        trader.strategies["market_making"] = _PerProductStrategy(
            {ASH: mm, PEPPER: cl}
        )
    else:
        _ = BuyAndHoldStrategy  # noqa: F841
    return BacktestSimulator(trader=trader).run(replay)


def _fold_pnl(result: SimulationResult, product: str) -> float:
    pr = result.per_product.get(product)
    return pr.pnl if pr else 0.0


def evaluate(cand: Candidate, replays: dict[int, ReplayEngine]) -> dict:
    """Return a fold-summary dict: per-day PEPPER PnL + aggregate stats."""
    per_day: dict[int, dict[str, float]] = {}
    for day, replay in replays.items():
        result = _run_candidate(cand, replay)
        per_day[day] = {
            "pep_pnl": _fold_pnl(result, PEPPER),
            "ash_pnl": _fold_pnl(result, ASH),
            "total": result.total_pnl,
        }
    pep_pnls = [per_day[d]["pep_pnl"] for d in FOLDS]
    return {
        "label": cand.label,
        "note": cand.note,
        "day_-2_pep": per_day[-2]["pep_pnl"],
        "day_-1_pep": per_day[-1]["pep_pnl"],
        "day_0_pep":  per_day[0]["pep_pnl"],
        "day_-2_total": per_day[-2]["total"],
        "day_-1_total": per_day[-1]["total"],
        "day_0_total":  per_day[0]["total"],
        "mean_pep": mean(pep_pnls),
        "min_pep":  min(pep_pnls),
        "max_pep":  max(pep_pnls),
        "std_pep":  pstdev(pep_pnls),
        "spread_pep": max(pep_pnls) - min(pep_pnls),
    }


def load_all_replays() -> dict[int, ReplayEngine]:
    return {d: _load_day_replay(d) for d in FOLDS}


def buy_hold_control() -> Candidate:
    return Candidate(
        label="C_buyhold_80",
        engine=round1_test_engine_config(),
        pepper_params=None,
        note="Control: buy-and-hold PEPPER, position_limit=80",
    )


def v3_nearhold_control() -> Candidate:
    return Candidate(
        label="C_v3_nearhold",
        engine=base_engine(),
        pepper_params=CoreLongParams(
            base_long=80, add_thresh=3.0, trim_thresh=8.0, add_gain=5.0,
            trim_gain=2.0, floor=40, ceiling=80, step=8, exec_style="taker",
            hybrid_threshold=2.0, maker_edge_offset=0.0,
            open_seed_size=65, open_window=500, open_no_short=True,
        ),
        note="Control: V3_nearhold (uploaded, scored +7259 official on day 0)",
    )


def v2_clean_control() -> Candidate:
    return Candidate(
        label="C_v2_clean",
        engine=base_engine(),
        pepper_params=CoreLongParams(
            base_long=50, add_thresh=3.0, trim_thresh=5.0, add_gain=5.0,
            trim_gain=1.0, floor=0, ceiling=80, step=8, exec_style="hybrid",
            hybrid_threshold=2.0, maker_edge_offset=0.0,
            open_seed_size=60, open_window=1000, open_no_short=True,
        ),
        note="Control: V2_clean (uploaded, scored +5426 official on day 0)",
    )


def fmt_row(row: dict) -> str:
    return (
        f"{row['label']:<28s} "
        f"mean={row['mean_pep']:+10.1f}  "
        f"[{row['min_pep']:+9.1f} .. {row['max_pep']:+9.1f}]  "
        f"std={row['std_pep']:5.1f}  "
        f"d-2={row['day_-2_pep']:+9.1f}  "
        f"d-1={row['day_-1_pep']:+9.1f}  "
        f"d0={row['day_0_pep']:+9.1f}"
    )


def emit_csv(path: Path, rows: list[dict]) -> None:
    cols = [
        "label", "note", "mean_pep", "min_pep", "max_pep", "std_pep",
        "spread_pep", "day_-2_pep", "day_-1_pep", "day_0_pep",
        "day_-2_total", "day_-1_total", "day_0_total",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
