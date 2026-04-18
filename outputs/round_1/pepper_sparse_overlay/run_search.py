"""PEPPER near-buy-and-hold + sparse-overlay v3 search.

Single-family pass. ONE strategy: ``PepperCoreLongStrategy`` with
``base_long=80, ceiling=80, open_no_short=True`` fixed for every
candidate in the family. That pins the default rest state at the
position limit, so the strategy auto-reloads to +80 whenever the
residual is not triggering a trim. Trims are SPARSE (high threshold,
small gain) and bounded below by ``floor``.

    target_position =
        opening_core(t)                     # t <= open_window
      | clip(80 + trim_overlay(r), floor, 80)
          trim_overlay(r) = 0                       if r <= trim_thresh
                          = -trim_gain*(r - thresh) if r > trim_thresh

ASH is frozen at the H1/F5/Alt ``wall_mid`` leg. PEPPER routes through
``PepperCoreLongStrategy`` (research-only; NOT shipped) via the same
runtime wiring pattern v2 used.

## Layered search

* L1  (25)   opening seed: size × window × no_short=True
* L2  (14)   high floor: floor ∈ {40..70} × top-2 L1 survivors
* L3  (24)   sparse trims: trim_thresh × trim_gain × top-2 L2 survivors
* L4  (24)   fast rebuy: hybrid_threshold × step × top-2 L3 survivors
* L5  (24)   execution: exec_style × step × top-2 L4 survivors
* L6  (2)    hand-tuned alternates (ultra-conservative + higher-upside)
* Controls (5): promoted / alt / f5 / v2_clean_ref / buy_hold_80

Evaluates on two views:

1. Official-range proxy — day 0, [0, 99900] at native 100-tick
   cadence. 1000 snapshots. Verified 1:1 calibration to official for
   seeded candidates (V2_clean proxy 5472.5 vs official 5426).
2. Full 3-day × 10k local replay — robustness check only.

Writes ``pepper_candidates.csv`` and ``pepper_candidates.md`` with
per-layer sections. No shipped code modified; no bundle exported.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    round1_alt_engine_config,
    round1_f5_engine_config,
    round1_h1_engine_config,
    round1_promoted_engine_config,
    round1_test_engine_config,
)
from src.strategies.base import BaseStrategy, StrategyContext
from src.strategies.buy_and_hold import BuyAndHoldStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.pepper_core_long import (
    CoreLongParams,
    PepperCoreLongStrategy,
)
from src.trader import Trader

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path("data/raw/round_1")
ASH = "ASH_COATED_OSMIUM"
PEPPER = "INTARIAN_PEPPER_ROOT"

OFFICIAL_DAY = 0
OFFICIAL_T_MAX = 99_900
EXPECTED_OFFICIAL_SNAPSHOTS = 1000

OFFICIAL_BUCKET_CUTOFFS: tuple[int, ...] = (25_000, 50_000, 75_000, 100_000)
LOCAL_BUCKET_CUTOFFS: tuple[int, ...] = (250_000, 500_000, 750_000, 1_000_000)
LOCAL_EARLY_25K = 249_900
LOCAL_EARLY_50K = 499_900
LOCAL_MAX_SHORT_FH_CUTOFF = 500_000

OFFICIAL_EARLY_25K = 25_000
OFFICIAL_EARLY_50K = 50_000
OFFICIAL_MAX_SHORT_FH_CUTOFF = 50_000


class _PerProductStrategy(BaseStrategy):
    def __init__(self, by_product: dict[str, BaseStrategy]) -> None:
        self.by_product = by_product
        self._default = next(iter(by_product.values()))

    def generate_intent(self, context: StrategyContext):  # type: ignore[override]
        strategy = self.by_product.get(context.product, self._default)
        return strategy.generate_intent(context)


def _wrap_trader_with_pepper_core_long(
    trader: Trader, params: CoreLongParams
) -> None:
    fve = trader.fair_value_engine
    sig = trader.signal_engine
    mm = MarketMakingStrategy(fve, sig)
    core_long = PepperCoreLongStrategy(fve, sig, params)
    trader.strategies["market_making"] = _PerProductStrategy(
        {ASH: mm, PEPPER: core_long}
    )


def _base_engine() -> EngineConfig:
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
    layer: str
    engine: EngineConfig
    pepper_params: CoreLongParams | None
    note: str


# --------------------------------------------------------------------------- #
# Controls                                                                    #
# --------------------------------------------------------------------------- #


def _controls() -> list[Candidate]:
    return [
        Candidate(
            label="C_promoted",
            layer="control",
            engine=round1_promoted_engine_config(),
            pepper_params=None,
            note="Control: promoted PEPPER (linear_drift t=2.0 skew=2 flat=0.7)",
        ),
        Candidate(
            label="C_alt",
            layer="control",
            engine=round1_alt_engine_config(),
            pepper_params=None,
            note="Control: alt PEPPER (linear_drift t=2.0 skew=1 flat=0.9)",
        ),
        Candidate(
            label="C_f5",
            layer="control",
            engine=round1_f5_engine_config(),
            pepper_params=None,
            note="Control: F5 PEPPER (asymmetric taker buy=1.5 sell=3.0)",
        ),
        Candidate(
            label="C_v2_clean_ref",
            layer="control",
            engine=_base_engine(),
            pepper_params=CoreLongParams(
                base_long=50,
                add_thresh=3.0,
                trim_thresh=5.0,
                add_gain=5.0,
                trim_gain=1.0,
                floor=0,
                ceiling=80,
                step=8,
                exec_style="hybrid",
                hybrid_threshold=2.0,
                open_seed_size=60,
                open_window=1000,
                open_no_short=True,
            ),
            note="Control: V2_clean reference (base=50, seed=60/win=1000)",
        ),
        Candidate(
            label="C_buyhold_80",
            layer="control",
            engine=round1_test_engine_config(),
            pepper_params=None,
            note="Control: buy-and-hold PEPPER at limit=80 (directional reference)",
        ),
    ]


# --------------------------------------------------------------------------- #
# Family nominal                                                              #
# --------------------------------------------------------------------------- #
#
# Fixed for the entire family: base_long=80, ceiling=80, open_no_short=True.
# Layer 1 varies opening size + window on top of this nominal.

_FAMILY_NOMINAL = CoreLongParams(
    base_long=80,
    add_thresh=3.0,          # add-branch inert (base=ceiling=80) but keep default
    trim_thresh=8.0,
    add_gain=5.0,
    trim_gain=2.0,
    floor=50,                # mid-level floor (L2 sweeps this)
    ceiling=80,
    step=8,
    exec_style="hybrid",
    hybrid_threshold=2.0,
    open_seed_size=0,        # L1 sets this
    open_window=0,           # L1 sets this
    open_no_short=True,
)


# --------------------------------------------------------------------------- #
# Layer 1 — Opening seed                                                      #
# --------------------------------------------------------------------------- #

_L1_SEEDS: tuple[int, ...] = (60, 65, 70, 75, 80)
_L1_WINDOWS: tuple[int, ...] = (0, 200, 500, 1000, 2000)


def _layer1_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for seed in _L1_SEEDS:
        for window in _L1_WINDOWS:
            params = replace(_FAMILY_NOMINAL, open_seed_size=seed, open_window=window)
            label = f"L1_seed{seed:02d}_win{window:05d}"
            note = (
                f"L1: open_seed={seed}, open_window={window}, "
                f"open_no_short=True; base=80 nominal overlay"
            )
            out.append(
                Candidate(
                    label=label,
                    layer="L1_opening",
                    engine=_base_engine(),
                    pepper_params=params,
                    note=note,
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Layer 2 — High long floor                                                   #
# --------------------------------------------------------------------------- #

_L2_FLOORS: tuple[int, ...] = (40, 45, 50, 55, 60, 65, 70)


def _layer2_candidates(l1_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l1_survivors):
        for fl in _L2_FLOORS:
            params = replace(survivor, floor=fl)
            label = f"L2_s{s_idx}_fl{fl:02d}"
            note = (
                f"L2: floor={fl} on L1 survivor #{s_idx} "
                f"(seed={survivor.open_seed_size}, win={survivor.open_window})"
            )
            out.append(
                Candidate(
                    label=label,
                    layer="L2_floor",
                    engine=_base_engine(),
                    pepper_params=params,
                    note=note,
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Layer 3 — Sparse trims                                                      #
# --------------------------------------------------------------------------- #
#
# trim_size ∈ {5, 10, 15} maps to trim_gain ∈ {1.0, 2.0, 3.0} because the
# per-tick trim magnitude under a typical positive residual excess of ~5
# equals gain × excess.
# The user's spec calls out trim_threshold ∈ {6, 8, 10, 12} and
# trim_size ∈ {5, 10, 15}.

_L3_TRIM_THRESHOLDS: tuple[float, ...] = (6.0, 8.0, 10.0, 12.0)
_L3_TRIM_SIZES: tuple[tuple[str, float], ...] = (
    ("size5", 1.0),     # small trim
    ("size10", 2.0),    # medium trim
    ("size15", 3.0),    # larger trim (still sparse)
)


def _layer3_candidates(l2_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l2_survivors):
        for thr in _L3_TRIM_THRESHOLDS:
            for size_label, gain in _L3_TRIM_SIZES:
                params = replace(survivor, trim_thresh=thr, trim_gain=gain)
                label = f"L3_s{s_idx}_trim{thr:g}_{size_label}"
                note = (
                    f"L3: trim_thresh={thr}, trim_gain={gain} ({size_label}) "
                    f"on L2 survivor #{s_idx}"
                )
                out.append(
                    Candidate(
                        label=label,
                        layer="L3_trim",
                        engine=_base_engine(),
                        pepper_params=params,
                        note=note,
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# Layer 4 — Fast rebuy (re-cross threshold + rate of re-accumulation)         #
# --------------------------------------------------------------------------- #
#
# With base_long=80=ceiling, target auto-snaps to 80 when residual is in
# the dead zone. "rebuy_threshold" maps to hybrid_threshold (how aggressively
# we cross the spread to close the gap) and "rebuy_gain" maps to step
# (how many units per tick we move toward target).

_L4_HYBRID_THRESHOLDS: tuple[float, ...] = (2.0, 3.0, 4.0, 5.0)
_L4_STEPS: tuple[tuple[str, int], ...] = (
    ("small", 4),
    ("medium", 8),
    ("aggressive", 16),
)


def _layer4_candidates(l3_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l3_survivors):
        for thr in _L4_HYBRID_THRESHOLDS:
            for step_label, step in _L4_STEPS:
                params = replace(
                    survivor, hybrid_threshold=thr, step=step
                )
                label = f"L4_s{s_idx}_h{thr:g}_{step_label}"
                note = (
                    f"L4: rebuy_threshold={thr}, step={step} ({step_label}) "
                    f"on L3 survivor #{s_idx}"
                )
                out.append(
                    Candidate(
                        label=label,
                        layer="L4_rebuy",
                        engine=_base_engine(),
                        pepper_params=params,
                        note=note,
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# Layer 5 — Execution style × step                                            #
# --------------------------------------------------------------------------- #

_L5_EXECS: tuple[tuple[str, str], ...] = (
    ("taker_first", "taker"),
    ("hybrid", "hybrid"),
    ("maker_first", "maker"),
)
_L5_STEPS: tuple[int, ...] = (4, 8, 12, 16)


def _layer5_candidates(l4_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l4_survivors):
        for exec_label, exec_style in _L5_EXECS:
            for step in _L5_STEPS:
                params = replace(survivor, exec_style=exec_style, step=step)
                label = f"L5_s{s_idx}_{exec_label}_step{step:02d}"
                note = f"L5: {exec_label}, step={step} on L4 survivor #{s_idx}"
                out.append(
                    Candidate(
                        label=label,
                        layer="L5_exec",
                        engine=_base_engine(),
                        pepper_params=params,
                        note=note,
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# Layer 6 — Optional alternates (hand-tuned on top of L5 winner)              #
# --------------------------------------------------------------------------- #


def _layer6_candidates(l5_winner: CoreLongParams) -> list[Candidate]:
    out: list[Candidate] = []
    # Ultra-conservative: floor=70, rare large-threshold trims
    out.append(
        Candidate(
            label="L6_ultra_conservative",
            layer="L6_alternate",
            engine=_base_engine(),
            pepper_params=replace(
                l5_winner,
                floor=70,
                trim_thresh=12.0,
                trim_gain=1.0,
                open_seed_size=80,
                open_window=0,
            ),
            note="L6: ultra-conservative (floor=70, rare trims, seed=80/win=0)",
        )
    )
    # Higher-upside: looser floor but aggressive exec
    out.append(
        Candidate(
            label="L6_higher_upside",
            layer="L6_alternate",
            engine=_base_engine(),
            pepper_params=replace(
                l5_winner,
                floor=50,
                trim_thresh=6.0,
                trim_gain=3.0,
                open_seed_size=80,
                open_window=0,
                step=16,
                exec_style="taker",
            ),
            note="L6: higher-upside (floor=50, narrow/large trims, aggressive taker reload)",
        )
    )
    return out


# --------------------------------------------------------------------------- #
# Replay loaders (identical to v2)                                            #
# --------------------------------------------------------------------------- #


def _load_full_replay() -> ReplayEngine:
    price_files = sorted(DATA_DIR.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(DATA_DIR.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {DATA_DIR}")
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)


def _official_range_replay(full: ReplayEngine) -> ReplayEngine:
    filtered: list[ReplayStep] = [
        s
        for s in full.steps
        if s.day == OFFICIAL_DAY and 0 <= s.timestamp <= OFFICIAL_T_MAX
    ]
    return ReplayEngine(filtered)


# --------------------------------------------------------------------------- #
# Metric helpers (copied verbatim from v2 runner)                             #
# --------------------------------------------------------------------------- #


def _bucket_pnl(result, product, cutoffs):
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    totals = [0.0] * len(cutoffs)
    if not series:
        return totals
    by_day: dict[int, list[tuple[int, float]]] = {}
    for (day, ts), (_ts, val) in zip(keys, series, strict=True):
        by_day.setdefault(day, []).append((ts, val))
    for _day, day_series in by_day.items():
        day_start = day_series[0][1] if day_series else 0.0
        prev_val = day_start
        for i, end_ts in enumerate(cutoffs):
            last_val = prev_val
            for ts, v in day_series:
                if ts < end_ts:
                    last_val = v
            totals[i] += last_val - prev_val
            prev_val = last_val
    return totals


def _early_day_pnl(result, product, end_ts):
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    if not series:
        return 0.0
    total = 0.0
    current_day = None
    day_start_val = 0.0
    last_val_before_end: float | None = None
    for (day, ts), (_ts, val) in zip(keys, series, strict=True):
        if day != current_day:
            if current_day is not None and last_val_before_end is not None:
                total += last_val_before_end - day_start_val
            current_day = day
            day_start_val = val
            last_val_before_end = None
        if ts <= end_ts:
            last_val_before_end = val
    if last_val_before_end is not None:
        total += last_val_before_end - day_start_val
    return total


def _max_short_first_half(result, product, fh_cutoff):
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return 0
    by_day: dict[int | None, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    deepest = 0
    for _day, rs in by_day.items():
        rs.sort(key=lambda r: r.fill_timestamp)
        pos = 0
        for r in rs:
            if r.fill_timestamp > fh_cutoff:
                break
            pos += r.quantity if r.side == "buy" else -r.quantity
            if pos < deepest:
                deepest = pos
    return deepest


def _max_long_overall(result, product):
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return 0
    by_day: dict[int | None, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    highest = 0
    for _day, rs in by_day.items():
        rs.sort(key=lambda r: r.fill_timestamp)
        pos = 0
        for r in rs:
            pos += r.quantity if r.side == "buy" else -r.quantity
            if pos > highest:
                highest = pos
    return highest


def _end_of_bucket_pos(result, product, cutoffs):
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return [0] * len(cutoffs)
    by_day: dict[int | None, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    target_day = OFFICIAL_DAY if OFFICIAL_DAY in by_day else next(iter(by_day))
    rows = sorted(by_day[target_day], key=lambda r: r.fill_timestamp)
    out = []
    pos = 0
    i = 0
    for end_ts in cutoffs:
        while i < len(rows) and rows[i].fill_timestamp < end_ts:
            r = rows[i]
            pos += r.quantity if r.side == "buy" else -r.quantity
            i += 1
        out.append(pos)
    return out


def _avg_position(result, product, cutoffs):
    """Average PEPPER position across the session (time-weighted by trade ticks)."""
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return 0.0
    by_day = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    total_ts = 0.0
    weighted = 0.0
    for _day, rs in by_day.items():
        rs.sort(key=lambda r: r.fill_timestamp)
        pos = 0
        prev_ts = 0
        for r in rs:
            dur = r.fill_timestamp - prev_ts
            if dur > 0:
                total_ts += dur
                weighted += pos * dur
            pos += r.quantity if r.side == "buy" else -r.quantity
            prev_ts = r.fill_timestamp
        # tail to end of bucket range
        dur = cutoffs[-1] - prev_ts
        if dur > 0:
            total_ts += dur
            weighted += pos * dur
    return weighted / total_ts if total_ts > 0 else 0.0


def _official_summary(result, product):
    pr = result.per_product.get(product)
    if pr is None:
        return {}
    buckets = _bucket_pnl(result, product, OFFICIAL_BUCKET_CUTOFFS)
    end_pos = _end_of_bucket_pos(result, product, OFFICIAL_BUCKET_CUTOFFS)
    avg_size = (
        (pr.buy_trade_quantity + pr.sell_trade_quantity) / pr.trade_count
        if pr.trade_count
        else 0.0
    )
    return {
        "pnl": pr.pnl,
        "trade_count": pr.trade_count,
        "maker_trades": pr.maker_trade_count,
        "taker_trades": pr.taker_trade_count,
        "final_pos": pr.final_position,
        "steps_near_limit": pr.steps_near_limit,
        "avg_entry_edge": pr.avg_entry_edge,
        "avg_markout_1": pr.avg_markout_1,
        "avg_markout_5": pr.avg_markout_5,
        "avg_markout_20": pr.avg_markout_20,
        "avg_size": avg_size,
        "avg_position": _avg_position(result, product, OFFICIAL_BUCKET_CUTOFFS),
        "early_25k": _early_day_pnl(result, product, OFFICIAL_EARLY_25K),
        "early_50k": _early_day_pnl(result, product, OFFICIAL_EARLY_50K),
        "bucket_0_25": buckets[0],
        "bucket_25_50": buckets[1],
        "bucket_50_75": buckets[2],
        "bucket_75_100": buckets[3],
        "max_short_fh": _max_short_first_half(
            result, product, OFFICIAL_MAX_SHORT_FH_CUTOFF
        ),
        "max_long": _max_long_overall(result, product),
        "end_pos_b0": end_pos[0],
        "end_pos_b1": end_pos[1],
        "end_pos_b2": end_pos[2],
        "end_pos_b3": end_pos[3],
    }


def _local_summary(result, product):
    pr = result.per_product.get(product)
    if pr is None:
        return {}
    buckets = _bucket_pnl(result, product, LOCAL_BUCKET_CUTOFFS)
    end_pos = _end_of_bucket_pos(result, product, LOCAL_BUCKET_CUTOFFS)
    return {
        "pnl": pr.pnl,
        "trade_count": pr.trade_count,
        "steps_near_limit": pr.steps_near_limit,
        "early_25k": _early_day_pnl(result, product, LOCAL_EARLY_25K),
        "early_50k": _early_day_pnl(result, product, LOCAL_EARLY_50K),
        "bucket_0_25": buckets[0],
        "bucket_25_50": buckets[1],
        "bucket_50_75": buckets[2],
        "bucket_75_100": buckets[3],
        "max_short_fh": _max_short_first_half(
            result, product, LOCAL_MAX_SHORT_FH_CUTOFF
        ),
        "max_long": _max_long_overall(result, product),
        "end_pos_b3": end_pos[3],
    }


# --------------------------------------------------------------------------- #
# Scoring                                                                     #
# --------------------------------------------------------------------------- #


def _score(off: dict, local: dict) -> float:
    """Rewards PEPPER total PnL + first-half capture + high average long
    exposure; penalises unintended shorting, near-limit abuse, and
    cross-view short excursions.
    """
    pep_total = off.get("pnl", 0.0)
    pep_first25 = off.get("early_25k", 0.0)
    pep_first50 = off.get("early_50k", 0.0)
    max_short_fh = off.get("max_short_fh", 0)
    near_limit = off.get("steps_near_limit", 0)
    avg_pos = off.get("avg_position", 0.0)
    local_pep = local.get("pnl", 0.0)
    local_short = local.get("max_short_fh", 0)

    short_mag = max(0, -max_short_fh)
    local_short_mag = max(0, -local_short)
    return (
        pep_total
        + 0.3 * pep_first25
        + 0.2 * pep_first50
        + 0.05 * local_pep
        + 10.0 * avg_pos       # reward keeping the bot long on average
        - 50.0 * short_mag     # strong penalty for any short
        - 0.1 * max(0, near_limit - 100)  # soft near-limit penalty; first 100 free
        - 5.0 * local_short_mag
    )


# --------------------------------------------------------------------------- #
# Output                                                                      #
# --------------------------------------------------------------------------- #


_COLS = [
    "label", "layer", "note",
    "off_total", "off_pep", "off_ash",
    "off_pep_first25", "off_pep_first50",
    "off_pep_b0", "off_pep_b1", "off_pep_b2", "off_pep_b3",
    "off_pep_trades", "off_pep_mkr", "off_pep_tkr", "off_pep_avg_size",
    "off_pep_avg_pos", "off_pep_max_long", "off_pep_max_short_fh",
    "off_pep_near_limit",
    "off_pep_endpos_b0", "off_pep_endpos_b1", "off_pep_endpos_b2", "off_pep_endpos_b3",
    "off_pep_mk1", "off_pep_mk5", "off_pep_mk20",
    "local_total", "local_pep", "local_ash",
    "local_pep_first25", "local_pep_first50",
    "local_pep_max_long", "local_pep_max_short_fh", "local_pep_near_limit",
    "score",
]


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _emit_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in _COLS})


def _emit_md(path: Path, rows: list[dict], layer_best: dict[str, str]) -> None:
    header = (
        "# PEPPER near-buy-and-hold + sparse-overlay candidates\n"
        "\n"
        "All rows from `pepper_candidates.csv`. Sorted by layer, then by "
        "`score` within each layer (descending).\n"
        "\n"
        "## Views\n"
        "\n"
        "- `off_*` — official-range proxy: day 0, `0 ≤ timestamp ≤ 99_900` "
        "at native 100-tick cadence (1000 snapshots). "
        "Seeded-candidate calibration to official is ~1:1 "
        "(V2_clean proxy +5 472.5 vs official +5 426 = 1.009×).\n"
        "- `local_*` — full 3-day × 10k replay. Robustness only.\n"
        "\n"
        "## ASH leg\n"
        "\n"
        "Frozen at the H1/F5/Alt `wall_mid` leg for every candidate. "
        "PEPPER routes through `PepperCoreLongStrategy` with "
        "`max_aggressive_size=20` so `step` is the binding per-tick cap.\n"
        "\n"
        "## Score formula (disclosed; summary only)\n"
        "\n"
        "```\n"
        "score = off_pep\n"
        "      + 0.3 * off_pep_first25\n"
        "      + 0.2 * off_pep_first50\n"
        "      + 0.05 * local_pep\n"
        "      + 10.0 * avg_pos          # reward staying long\n"
        "      - 50.0 * max(0, -off_pep_max_short_fh)\n"
        "      - 0.1 * max(0, off_pep_near_limit - 100)\n"
        "      - 5.0 * max(0, -local_pep_max_short_fh)\n"
        "```\n"
        "\n"
    )
    lines = [header]
    if layer_best:
        lines.append("## Per-layer winners (carry-forward)\n")
        for layer in ("L1_opening", "L2_floor", "L3_trim", "L4_rebuy", "L5_exec", "L6_alternate"):
            if layer in layer_best:
                lines.append(f"- **{layer}**: {layer_best[layer]}")
        lines.append("")
    lines.append("## Candidates\n")
    lines.append("| " + " | ".join(_COLS) + " |")
    lines.append("|" + "|".join(["---"] * len(_COLS)) + "|")
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in _COLS) + " |")
    lines.append("")
    path.write_text("\n".join(lines))


# --------------------------------------------------------------------------- #
# Runner                                                                      #
# --------------------------------------------------------------------------- #


def _run(candidate: Candidate, replay: ReplayEngine) -> SimulationResult:
    trader = Trader(config=candidate.engine)
    if candidate.pepper_params is not None:
        _wrap_trader_with_pepper_core_long(trader, candidate.pepper_params)
    else:
        _ = BuyAndHoldStrategy
    return BacktestSimulator(trader=trader).run(replay)


def _evaluate(cand: Candidate, off_replay, full_replay) -> dict:
    r_off = _run(cand, off_replay)
    r_local = _run(cand, full_replay)
    off = _official_summary(r_off, PEPPER)
    off_ash = _official_summary(r_off, ASH)
    local = _local_summary(r_local, PEPPER)
    local_ash = _local_summary(r_local, ASH)
    score = _score(off, local)
    return {
        "label": cand.label,
        "layer": cand.layer,
        "note": cand.note,
        "off_total": r_off.total_pnl,
        "off_pep": off.get("pnl"),
        "off_ash": off_ash.get("pnl"),
        "off_pep_first25": off.get("early_25k"),
        "off_pep_first50": off.get("early_50k"),
        "off_pep_b0": off.get("bucket_0_25"),
        "off_pep_b1": off.get("bucket_25_50"),
        "off_pep_b2": off.get("bucket_50_75"),
        "off_pep_b3": off.get("bucket_75_100"),
        "off_pep_trades": off.get("trade_count"),
        "off_pep_mkr": off.get("maker_trades"),
        "off_pep_tkr": off.get("taker_trades"),
        "off_pep_avg_size": off.get("avg_size"),
        "off_pep_avg_pos": off.get("avg_position"),
        "off_pep_max_long": off.get("max_long"),
        "off_pep_max_short_fh": off.get("max_short_fh"),
        "off_pep_near_limit": off.get("steps_near_limit"),
        "off_pep_endpos_b0": off.get("end_pos_b0"),
        "off_pep_endpos_b1": off.get("end_pos_b1"),
        "off_pep_endpos_b2": off.get("end_pos_b2"),
        "off_pep_endpos_b3": off.get("end_pos_b3"),
        "off_pep_mk1": off.get("avg_markout_1"),
        "off_pep_mk5": off.get("avg_markout_5"),
        "off_pep_mk20": off.get("avg_markout_20"),
        "local_total": r_local.total_pnl,
        "local_pep": local.get("pnl"),
        "local_ash": local_ash.get("pnl"),
        "local_pep_first25": local.get("early_25k"),
        "local_pep_first50": local.get("early_50k"),
        "local_pep_max_long": local.get("max_long"),
        "local_pep_max_short_fh": local.get("max_short_fh"),
        "local_pep_near_limit": local.get("steps_near_limit"),
        "score": score,
    }


def _print_row(idx: int, total: int, label: str, row: dict) -> None:
    print(
        f"[{idx:>3}/{total}] {label:<40s} "
        f"off_pep={row.get('off_pep') or 0.0:+9.1f}  "
        f"f25={row.get('off_pep_first25') or 0.0:+8.1f}  "
        f"f50={row.get('off_pep_first50') or 0.0:+8.1f}  "
        f"apos={row.get('off_pep_avg_pos') or 0.0:+5.1f}  "
        f"ms={row.get('off_pep_max_short_fh') or 0:+3d}  "
        f"near={row.get('off_pep_near_limit') or 0:3d}  "
        f"score={row.get('score') or 0.0:+9.1f}"
    )


def _run_layer(
    name: str,
    candidates: list[Candidate],
    off_replay,
    full_replay,
    survivors_n: int,
    all_rows: list[dict],
    layer_best: dict[str, str],
) -> list[CoreLongParams]:
    print(f"\n=== {name} — {len(candidates)} candidates ===")
    rows = []
    for i, cand in enumerate(candidates, start=1):
        row = _evaluate(cand, off_replay, full_replay)
        rows.append(row)
        all_rows.append(row)
        _print_row(i, len(candidates), cand.label, row)
    scored = list(zip(rows, candidates, strict=True))
    scored.sort(key=lambda rc: rc[0]["score"], reverse=True)
    winners = [c for _, c in scored[:survivors_n]]
    layer_best[name] = ", ".join(w.label for w in winners)
    print(f"  {name} top-{survivors_n}: {layer_best[name]}")
    return [w.pepper_params for w in winners if w.pepper_params is not None]


def main() -> None:
    full = _load_full_replay()
    off_replay = _official_range_replay(full)
    print(
        f"[loaded] full 3-day = {len(full.steps)} steps | "
        f"official-range proxy day {OFFICIAL_DAY} "
        f"[0, {OFFICIAL_T_MAX}] at 100-tick cadence "
        f"= {len(off_replay.steps)} steps"
    )
    assert len(off_replay.steps) == EXPECTED_OFFICIAL_SNAPSHOTS, (
        f"official-range proxy must be {EXPECTED_OFFICIAL_SNAPSHOTS} "
        f"snapshots (got {len(off_replay.steps)})"
    )

    all_rows: list[dict] = []
    layer_best: dict[str, str] = {}

    # Controls
    controls = _controls()
    print(f"\n=== Controls — {len(controls)} candidates ===")
    for i, cand in enumerate(controls, start=1):
        row = _evaluate(cand, off_replay, full)
        all_rows.append(row)
        _print_row(i, len(controls), cand.label, row)

    # Layers 1-5
    l1_surv = _run_layer("L1_opening", _layer1_candidates(), off_replay, full, 2, all_rows, layer_best)
    l2_surv = _run_layer("L2_floor", _layer2_candidates(l1_surv), off_replay, full, 2, all_rows, layer_best)
    l3_surv = _run_layer("L3_trim", _layer3_candidates(l2_surv), off_replay, full, 2, all_rows, layer_best)
    l4_surv = _run_layer("L4_rebuy", _layer4_candidates(l3_surv), off_replay, full, 2, all_rows, layer_best)
    l5_surv = _run_layer("L5_exec", _layer5_candidates(l4_surv), off_replay, full, 1, all_rows, layer_best)

    # Layer 6
    if l5_surv:
        _run_layer("L6_alternate", _layer6_candidates(l5_surv[0]), off_replay, full, 1, all_rows, layer_best)

    # Emit
    layer_order = {"control": 0, "L1_opening": 1, "L2_floor": 2, "L3_trim": 3,
                   "L4_rebuy": 4, "L5_exec": 5, "L6_alternate": 6}
    all_rows.sort(key=lambda r: (layer_order.get(r["layer"], 99), -r["score"]))
    _emit_csv(ROOT / "pepper_candidates.csv", all_rows)
    _emit_md(ROOT / "pepper_candidates.md", all_rows, layer_best)
    print(f"\nDone. Wrote:\n  - {ROOT / 'pepper_candidates.csv'}\n  - {ROOT / 'pepper_candidates.md'}")

    # Top-15 summary
    print("\nTop 15 by score (all layers):")
    top = sorted(all_rows, key=lambda r: r["score"], reverse=True)[:15]
    print(
        f"  {'label':<40s} {'layer':<14s} {'score':>9s} "
        f"{'off_pep':>9s} {'f25':>8s} {'apos':>5s} {'near':>5s}"
    )
    for r in top:
        print(
            f"  {r['label']:<40s} {r['layer']:<14s} {r['score']:>9.1f} "
            f"{r['off_pep']:>+9.1f} {r['off_pep_first25']:>+8.1f} "
            f"{r['off_pep_avg_pos']:>+5.1f} {r['off_pep_near_limit']:>5d}"
        )


if __name__ == "__main__":
    main()
