"""Shared runtime helpers for Round-2 research scripts.

The Round-2 sweep / baseline / kill-switch scripts all build the same
trader stack (v5_micro PEPPER + L1 or wide_w113 ASH ladder, wired
through ``PerProductStrategy``). Before this module they each carried
their own copies of the helpers and reached into ``run_baseline.py``'s
private symbols. That cross-coupling is now resolved here:

- Constants: product names, ``L1_ASH_LADDER_PARAMS``.
- Replay loader: ``load_round_2_replay`` (with explicit "missing
  file" diagnostics).
- Trader wiring: ``PerProductStrategy`` dispatcher + the
  ``wrap_trader_with_v5micro_l1`` factory swap.
- Engine config: ``baseline_engine`` (Round-1 H1 base + R2-shape
  ASH/PEPPER patches; toggleable day-rollover flush).
- PnL helpers: ``per_day_pnl`` (cumulative-to-contribution diff).

The canonical ``V5_MICRO_PARAMS`` lives on
``src.strategies.pepper_core_long`` — import from there.

This module is import-safe (no I/O at module load) and is tested
indirectly by the runners; the integration smoke test in
``tests/test_round2_export_e2e.py`` covers the full pipeline.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine
from src.core.config import EngineConfig, round1_h1_engine_config
from src.strategies.ash_ladder import AshLadderStrategy, LadderParams
from src.strategies.base import BaseStrategy, StrategyContext
from src.strategies.pepper_core_long import (
    V5_MICRO_PARAMS,
    CoreLongParams,
    PepperCoreLongStrategy,
)
from src.trader import Trader

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "raw" / "round_2"

ASH = "ASH_COATED_OSMIUM"
PEPPER = "INTARIAN_PEPPER_ROOT"

# L1 ASH LadderParams — the Round-1 winning ladder (edges 2.5/3.5/5,
# weights 3:1:1). Used as the *baseline* in batch-C/D runs and as
# the reference row in the batch-D1 sweep.
L1_ASH_LADDER_PARAMS = LadderParams(
    edges=(2.5, 3.5, 5.0),
    size_mults=(1.0, 1.5, 2.0),
    skew_coef=2.0,
    flatten_threshold=0.7,
    weights=(3, 1, 1),
)

# Re-export V5_MICRO_PARAMS so callers can import everything they
# need from the same module without importing src.strategies directly.
V5_MICRO_PEPPER_PARAMS = V5_MICRO_PARAMS

__all__ = [
    "ASH",
    "DATA_DIR",
    "L1_ASH_LADDER_PARAMS",
    "PEPPER",
    "PerProductStrategy",
    "REPO_ROOT",
    "V5_MICRO_PEPPER_PARAMS",
    "baseline_engine",
    "load_round_2_replay",
    "per_day_pnl",
    "wrap_trader_with_v5micro_l1",
]


# --------------------------------------------------------------- runtime wiring


class PerProductStrategy(BaseStrategy):
    """Route each product to its own configured strategy instance.

    Used by the Round-2 research runners to swap the shipped
    ``market_making`` slot with a per-product dispatcher: ASH gets
    ``AshLadderStrategy``, PEPPER gets ``PepperCoreLongStrategy``.
    """

    def __init__(self, by_product: dict[str, BaseStrategy]) -> None:
        if not by_product:
            raise ValueError("PerProductStrategy requires at least one product")
        self.by_product = by_product
        self._default = next(iter(by_product.values()))

    def generate_intent(self, context: StrategyContext):  # type: ignore[override]
        strategy = self.by_product.get(context.product, self._default)
        return strategy.generate_intent(context)


def wrap_trader_with_v5micro_l1(
    trader: Trader,
    *,
    pepper_params: CoreLongParams = V5_MICRO_PEPPER_PARAMS,
    ash_params: LadderParams = L1_ASH_LADDER_PARAMS,
) -> None:
    """Replace the shipped market_making strategy with v5micro + ladder wiring.

    Mirrors the strategy stack inlined by the Round-2 export script:
    ASH → ``AshLadderStrategy(ash_params)``, PEPPER →
    ``PepperCoreLongStrategy(pepper_params)``. Defaults to v5_micro
    PEPPER + L1 ASH; sweep callers pass their own ``ash_params``.
    """
    fve = trader.fair_value_engine
    sig = trader.signal_engine
    trader.strategies["market_making"] = PerProductStrategy(
        {
            ASH: AshLadderStrategy(fve, sig, ash_params),
            PEPPER: PepperCoreLongStrategy(fve, sig, pepper_params),
        }
    )


# --------------------------------------------------------------- engine config


def baseline_engine(*, flush_pepper: bool) -> EngineConfig:
    """Round-2 baseline EngineConfig mirroring combined_v5micro_l1.

    Both ProductConfigs are *stubs* — strategies are swapped at
    runtime via ``wrap_trader_with_v5micro_l1``. We use H1 as the
    engine base because every Round-1 winning factory shares the
    same surface, then patch:

    - ASH: weighted_mid FV, maker_edge=2.5 (matches L1 inner edge),
      taker_edge=0.5, flatten=0.7.
    - PEPPER: keep linear_drift FV, bump quote_size/max_aggressive_size
      so the strategy's ``step`` rate-limit is the binding constraint.

    ``flush_pepper`` toggles day-rollover flush on PEPPER only.
    """
    base = round1_h1_engine_config()
    products = dict(base.products)
    products[PEPPER] = replace(
        products[PEPPER],
        max_aggressive_size=20,
        quote_size=10,
        flush_history_on_day_rollover=flush_pepper,
    )
    products[ASH] = replace(
        products[ASH],
        fair_value_method="weighted_mid",
        fair_value_fallbacks=("wall_mid", "mid"),
        maker_edge=2.5,
        taker_edge=0.5,
        flatten_threshold=0.7,
    )
    return replace(base, products=products)


# --------------------------------------------------------------- pnl helpers


def per_day_pnl(result: SimulationResult, product: str) -> dict[int, float]:
    """Per-day PnL **contribution** for ``product`` (not cumulative).

    PnL series is cumulative across the stitched replay; we recover
    per-day contribution by grabbing the last (= end-of-day cumulative)
    value for each day, then differencing in calendar order.
    """
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    if not series or not keys or len(series) != len(keys):
        return {}
    end_of_day: dict[int, float] = {}
    for (day, _ts), (_seq_ts, pnl) in zip(keys, series, strict=True):
        if day is None:
            continue
        end_of_day[day] = pnl
    out: dict[int, float] = {}
    prev = 0.0
    for day in sorted(end_of_day):
        out[day] = end_of_day[day] - prev
        prev = end_of_day[day]
    return out


# --------------------------------------------------------------- data loader


def load_round_2_replay(*, data_dir: Path = DATA_DIR) -> ReplayEngine:
    """Build the canonical 3-day Round-2 replay engine.

    Raises ``FileNotFoundError`` with the exact missing path so
    operators don't have to dig into a generic ``ReplayEngine`` stack
    trace when the data directory is incomplete.
    """
    price_files = [
        data_dir / "prices_round_2_day_-1.csv",
        data_dir / "prices_round_2_day_0.csv",
        data_dir / "prices_round_2_day_1.csv",
    ]
    trade_files = [
        data_dir / "trades_round_2_day_-1.csv",
        data_dir / "trades_round_2_day_0.csv",
        data_dir / "trades_round_2_day_1.csv",
    ]
    for p in (*price_files, *trade_files):
        if not p.exists():
            raise FileNotFoundError(
                f"Round-2 data file missing: {p}. "
                f"Expected layout: {data_dir}/{{prices,trades}}_round_2_day_{{-1,0,1}}.csv"
            )
    return ReplayEngine.from_files(
        price_paths=[str(p) for p in price_files],
        trade_paths=[str(p) for p in trade_files],
    )
