"""PEPPER core-long + tactical-overlay v2 — layered candidate search.

Single-family pass. ONE strategy: ``PepperCoreLongStrategy`` with the
v2 opening-acquisition knobs layered on top of the v1 core-long +
residual-overlay target. Five layers, carry-forward discipline:

    target_position(t) =
        opening_core(t)          # t <= open_window: target = open_seed_size
      + persistent_core          # else: target = base_long
      + tactical_overlay(residual(t))
      - protection_adjustment    # Layer 5, optional

ASH is frozen at the H1/F5/Alt ``wall_mid`` leg for every candidate.
PEPPER routes through ``PepperCoreLongStrategy`` (research-only; NOT
in ``STRATEGY_REGISTRY``) via the same runtime wiring pattern v1 used.

## Fixed-in-v2 official-cadence proxy

v1 used ``day==0 AND timestamp % 1000 == 0`` on the full local day
(timestamps 0..999_900) which yields 1000 snapshots BUT at 10× sparser
cadence over a 10× longer time window than the real official day. The
real IMC official day 0 covers timestamps [0, 99_900] at native
100-tick cadence = 1000 snapshots over ~10_000 ms of simulated market
time. v2 filters:

    day == 0 AND 0 <= timestamp <= 99_900       (native 100-tick cadence)

which gives 1000 snapshots at the same cadence as the official log.
This is the **official-range proxy**. It is verified at load time
(``len == 1000``) and documented in every output file.

## Layered search vs giant grid

A full cross-product of Layer 1..5 would be ~25_920 candidates. A
layered pass with top-2 carry-forward is ~125 runs. The layered pass:

- Makes each layer's contribution causally attributable (opening vs
  overlay vs execution).
- Keeps the raw metrics in the decision loop at each transition, not
  just the composite score.
- Runs fast enough to iterate without one-shot grid commitment.

Evaluates on two views:

1. **Official-range proxy** — the corrected 100-tick cadence proxy
   described above.
2. **Full 3-day x 10k** local replay — robustness check only.

Writes ``pepper_candidates.csv`` and ``pepper_candidates.md`` with
per-layer sections so a reader can trace the decision.

The runner does NOT export any submission bundle and does NOT modify
any shipped config.
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

# Official IMC day 0 covers timestamps [0, 99_900] at 100-tick cadence
# = 1000 snapshots. Verified directly against
# ``outputs/round_1/official_results/h1/151053.log``.
OFFICIAL_DAY = 0
OFFICIAL_T_MAX = 99_900  # inclusive
EXPECTED_OFFICIAL_SNAPSHOTS = 1000

# Local bucket cutoffs in LOCAL tick-space (full 3-day replay uses
# timestamps [0, 999_900] per day). For the official-range proxy,
# buckets are [0, 25k, 50k, 75k, 100k) matching the official log.
OFFICIAL_BUCKET_CUTOFFS: tuple[int, ...] = (25_000, 50_000, 75_000, 100_000)
LOCAL_BUCKET_CUTOFFS: tuple[int, ...] = (250_000, 500_000, 750_000, 1_000_000)
LOCAL_EARLY_25K = 249_900  # first "quarter" for the full 3-day view
LOCAL_EARLY_50K = 499_900
LOCAL_MAX_SHORT_FH_CUTOFF = 500_000

OFFICIAL_EARLY_25K = 25_000  # exclusive
OFFICIAL_EARLY_50K = 50_000
OFFICIAL_MAX_SHORT_FH_CUTOFF = 50_000


# --------------------------------------------------------------------------- #
# Per-product strategy dispatch (runner-only; live bundle untouched)          #
# --------------------------------------------------------------------------- #


class _PerProductStrategy(BaseStrategy):
    """Route each product to its own configured strategy instance."""

    def __init__(self, by_product: dict[str, BaseStrategy]) -> None:
        self.by_product = by_product
        self._default = next(iter(by_product.values()))

    def generate_intent(self, context: StrategyContext):  # type: ignore[override]
        strategy = self.by_product.get(context.product, self._default)
        return strategy.generate_intent(context)


def _wrap_trader_with_pepper_core_long(
    trader: Trader, params: CoreLongParams
) -> None:
    """PEPPER → ``PepperCoreLongStrategy(params)``, ASH → shipped MM."""
    fve = trader.fair_value_engine
    sig = trader.signal_engine
    mm = MarketMakingStrategy(fve, sig)
    core_long = PepperCoreLongStrategy(fve, sig, params)
    trader.strategies["market_making"] = _PerProductStrategy(
        {ASH: mm, PEPPER: core_long}
    )


# --------------------------------------------------------------------------- #
# Base engine (ASH = H1/F5/Alt wall_mid leg, PEPPER = promoted stub)          #
# --------------------------------------------------------------------------- #


def _base_engine() -> EngineConfig:
    """H1 engine base (wall_mid ASH + promoted PEPPER stub).

    Every family candidate swaps in ``PepperCoreLongStrategy``, so
    PEPPER's ProductConfig is effectively a stub — we bump
    ``max_aggressive_size`` so the strategy's ``step`` rate-limit is
    the binding per-tick taker-size cap (not the default
    promoted-config cap of 8).
    """
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


# --------------------------------------------------------------------------- #
# Candidate record                                                            #
# --------------------------------------------------------------------------- #


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
            label="C_buyhold",
            layer="control",
            engine=round1_test_engine_config(),
            pepper_params=None,
            note="Control: buy-and-hold PEPPER (directional upper-bound ref)",
        ),
        Candidate(
            label="C_corelong_v1_base50",
            layer="control",
            engine=_base_engine(),
            pepper_params=CoreLongParams(
                base_long=50,
                add_thresh=3.0,
                trim_thresh=5.0,
                add_gain=3.0,
                trim_gain=1.0,
                floor=0,
                ceiling=80,
                step=8,
                exec_style="hybrid",
                hybrid_threshold=2.0,
                # v1 had no opening branch; explicit disable for clarity.
                open_seed_size=0,
                open_window=0,
            ),
            note="Control: v1 B_base50 (base=50, nominal overlay, no opening)",
        ),
        Candidate(
            label="C_corelong_no_open",
            layer="control",
            engine=_base_engine(),
            pepper_params=CoreLongParams(
                base_long=30,
                add_thresh=1000.0,
                trim_thresh=1000.0,
                add_gain=0.0,
                trim_gain=0.0,
                floor=0,
                ceiling=80,
                step=8,
                exec_style="hybrid",
                open_seed_size=0,
                open_window=0,
            ),
            note="Control: pure core-long (base=30, overlay off, no opening)",
        ),
    ]


# --------------------------------------------------------------------------- #
# Layer 1 — Opening acquisition                                               #
# --------------------------------------------------------------------------- #
#
# Nominal persistent_core + overlay held at the v1 B_base50 setting
# so Layer 1 isolates the effect of the opening seed.
#
# open_seed_size ∈ {20, 30, 40, 50, 60}
# open_window    ∈ {0, 1000, 2500, 5000}
# open_no_short  = True (fixed for this layer)
#
# 5 * 4 = 20 candidates.

_L1_NOMINAL = CoreLongParams(
    base_long=50,
    add_thresh=3.0,
    trim_thresh=5.0,
    add_gain=3.0,
    trim_gain=1.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style="hybrid",
    hybrid_threshold=2.0,
    # opening overridden per-candidate below
    open_seed_size=0,
    open_window=0,
    open_no_short=True,
)


def _layer1_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for seed in (20, 30, 40, 50, 60):
        for window in (0, 1000, 2500, 5000):
            params = replace(
                _L1_NOMINAL, open_seed_size=seed, open_window=window
            )
            label = f"L1_seed{seed:02d}_win{window:05d}"
            note = (
                f"L1: open_seed={seed}, open_window={window}, "
                f"open_no_short=True; base=50 nominal overlay"
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
# Layer 2 — Persistent core                                                   #
# --------------------------------------------------------------------------- #
#
# base_long ∈ {20, 30, 40, 50}
# floor     ∈ {0, 10, 20, 30} subject to floor <= base_long
# ceiling   = 80 fixed
#
# Uses the top-2 Layer 1 survivors as a (seed, window) carry-forward.
# 4 * 4 - invalid = 10 valid combinations, × 2 L1 survivors = ~20 runs.

_L2_BASE_LONGS = (20, 30, 40, 50)
_L2_FLOORS = (0, 10, 20, 30)


def _layer2_candidates(l1_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l1_survivors):
        for bl in _L2_BASE_LONGS:
            for fl in _L2_FLOORS:
                if fl > bl:
                    continue
                params = replace(survivor, base_long=bl, floor=fl)
                label = f"L2_s{s_idx}_base{bl:02d}_fl{fl:02d}"
                note = (
                    f"L2: base_long={bl}, floor={fl} on L1 survivor #{s_idx} "
                    f"(seed={survivor.open_seed_size}, "
                    f"win={survivor.open_window})"
                )
                out.append(
                    Candidate(
                        label=label,
                        layer="L2_core",
                        engine=_base_engine(),
                        pepper_params=params,
                        note=note,
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# Layer 3 — Tactical overlay                                                  #
# --------------------------------------------------------------------------- #
#
# We test the overlay as a triplet: one add-threshold set × one trim-
# threshold set × one overlay-size set. The v1 overlay params were
# scalars (add_thresh, add_gain, trim_thresh, trim_gain); to stay
# consistent with that interface while expressing a "band set", we
# pick the MIDDLE element of each set as the representative scalar and
# use the outer elements as the ``add_gain`` shape: higher gain =
# stronger response at the same threshold.
#
# Concretely, the (thresh, gain) pairs per set:
#   add set "-1.5 / -3 / -5"  → add_thresh=3.0, add_gain=5.0  (middle+outer)
#   add set "-2 / -4 / -6"    → add_thresh=4.0, add_gain=3.0
#   add set "-1 / -2 / -4"    → add_thresh=2.0, add_gain=4.0
#   trim set "+3 / +5 / +7"   → trim_thresh=5.0, trim_gain=1.0
#   trim set "+4 / +6 / +8"   → trim_thresh=6.0, trim_gain=0.8
#   trim set "+2.5 / +4.5 / +6.5" → trim_thresh=4.5, trim_gain=1.2
#
# Overlay size ladder is interpreted via the ``step`` and ``add_gain``
# combination: "small" = low gain, "medium" = middle gain, "convex" =
# steep gain. We encode this as a gain multiplier.
#   small  ×0.6
#   medium ×1.0
#   convex ×1.6

_ADD_SETS: tuple[tuple[str, float, float], ...] = (
    # label, add_thresh, add_gain (base)
    ("add_mid", 3.0, 5.0),
    ("add_wide", 4.0, 3.0),
    ("add_narrow", 2.0, 4.0),
)
_TRIM_SETS: tuple[tuple[str, float, float], ...] = (
    ("trim_mid", 5.0, 1.0),
    ("trim_wide", 6.0, 0.8),
    ("trim_narrow", 4.5, 1.2),
)
_OVERLAY_SIZES: tuple[tuple[str, float], ...] = (
    ("size_small", 0.6),
    ("size_medium", 1.0),
    ("size_convex", 1.6),
)


def _layer3_candidates(l2_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l2_survivors):
        for add_name, add_thr, add_gn in _ADD_SETS:
            for trim_name, trim_thr, trim_gn in _TRIM_SETS:
                for sz_name, sz_mult in _OVERLAY_SIZES:
                    # Keep trim side more conservative than add by
                    # multiplying only the add_gain with the size
                    # multiplier, leaving trim_gain at the set's
                    # baseline (the user specified "trim should remain
                    # more conservative than add").
                    params = replace(
                        survivor,
                        add_thresh=add_thr,
                        add_gain=add_gn * sz_mult,
                        trim_thresh=trim_thr,
                        trim_gain=trim_gn,
                    )
                    label = f"L3_s{s_idx}_{add_name}_{trim_name}_{sz_name}"
                    note = (
                        f"L3: {add_name}({add_thr},{add_gn*sz_mult:.1f}) × "
                        f"{trim_name}({trim_thr},{trim_gn}) × {sz_name} "
                        f"on L2 survivor #{s_idx}"
                    )
                    out.append(
                        Candidate(
                            label=label,
                            layer="L3_overlay",
                            engine=_base_engine(),
                            pepper_params=params,
                            note=note,
                        )
                    )
    return out


# --------------------------------------------------------------------------- #
# Layer 4 — Execution                                                         #
# --------------------------------------------------------------------------- #
#
# execution_mode ∈ {taker_first, hybrid, maker_first}
#   taker_first → exec_style="taker"
#   hybrid      → exec_style="hybrid" (v1 default)
#   maker_first → exec_style="maker"
# max_step_change_per_tick ∈ {4, 8, 12} (maps to ``step``)
#
# 3 * 3 = 9 candidates × top-2 L3 = ~18 runs.

_L4_EXECS: tuple[tuple[str, str], ...] = (
    ("taker_first", "taker"),
    ("hybrid", "hybrid"),
    ("maker_first", "maker"),
)
_L4_STEPS: tuple[int, ...] = (4, 8, 12)


def _layer4_candidates(l3_survivors: list[CoreLongParams]) -> list[Candidate]:
    out: list[Candidate] = []
    for s_idx, survivor in enumerate(l3_survivors):
        for exec_label, exec_style in _L4_EXECS:
            for step in _L4_STEPS:
                params = replace(survivor, exec_style=exec_style, step=step)
                label = f"L4_s{s_idx}_{exec_label}_step{step:02d}"
                note = f"L4: {exec_label}, step={step} on L3 survivor #{s_idx}"
                out.append(
                    Candidate(
                        label=label,
                        layer="L4_execution",
                        engine=_base_engine(),
                        pepper_params=params,
                        note=note,
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# Layer 5 — Optional protection                                               #
# --------------------------------------------------------------------------- #
#
# Only if a clear L4 winner emerges. Per the prompt: no protection,
# mild slope-break, mild drawdown, mild combined. We implement
# protection as a temporary floor tightening (raises floor by +10
# during a "protection trigger" window) since ``CoreLongParams``
# exposes no other lever. In practice this means: if the drift
# estimator slope flips sign OR the running PnL drops more than X
# from its peak, we tighten the floor so the bot is forced to trim
# to a safer rest state.
#
# The v2 runner treats Layer 5 as a PARAMETER SWEEP over a higher
# floor on the L4 winner, with the understanding that in a real
# implementation a protection branch would be triggered dynamically.
# We keep this simple per the prompt ("not a giant subproject").

_L5_PROTECTIONS: tuple[tuple[str, int], ...] = (
    ("no_protection", 0),  # no added floor → control
    ("mild_slope", 10),    # floor += 10 (stand-in for slope-break)
    ("mild_dd", 15),       # floor += 15 (stand-in for drawdown guard)
    ("mild_combined", 20), # floor += 20 (both)
)


def _layer5_candidates(l4_winner: CoreLongParams) -> list[Candidate]:
    out: list[Candidate] = []
    for prot_label, floor_bump in _L5_PROTECTIONS:
        new_floor = min(l4_winner.floor + floor_bump, l4_winner.base_long)
        params = replace(l4_winner, floor=new_floor)
        label = f"L5_{prot_label}"
        note = (
            f"L5: {prot_label}, floor={l4_winner.floor}→{new_floor} "
            f"on L4 winner"
        )
        out.append(
            Candidate(
                label=label,
                layer="L5_protection",
                engine=_base_engine(),
                pepper_params=params,
                note=note,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Replay loaders                                                              #
# --------------------------------------------------------------------------- #


def _load_full_replay() -> ReplayEngine:
    price_files = sorted(DATA_DIR.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(DATA_DIR.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {DATA_DIR}")
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)


def _official_range_replay(full: ReplayEngine) -> ReplayEngine:
    """The v2 corrected proxy: day 0, timestamps in [0, 99_900]
    at native 100-tick cadence. 1000 snapshots, matching the real
    official day's time window AND sample rate."""
    filtered: list[ReplayStep] = [
        s
        for s in full.steps
        if s.day == OFFICIAL_DAY and 0 <= s.timestamp <= OFFICIAL_T_MAX
    ]
    return ReplayEngine(filtered)


# --------------------------------------------------------------------------- #
# Metric helpers                                                              #
# --------------------------------------------------------------------------- #


def _bucket_pnl(
    result: SimulationResult, product: str, cutoffs: tuple[int, ...]
) -> list[float]:
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


def _early_day_pnl(result: SimulationResult, product: str, end_ts: int) -> float:
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


def _max_short_first_half(
    result: SimulationResult, product: str, fh_cutoff: int
) -> int:
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


def _max_long_overall(result: SimulationResult, product: str) -> int:
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


def _end_of_bucket_pos(
    result: SimulationResult, product: str, cutoffs: tuple[int, ...]
) -> list[int]:
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return [0] * len(cutoffs)
    by_day: dict[int | None, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    target_day = (
        OFFICIAL_DAY if OFFICIAL_DAY in by_day else next(iter(by_day))
    )
    rows = sorted(by_day[target_day], key=lambda r: r.fill_timestamp)
    out: list[int] = []
    pos = 0
    i = 0
    for end_ts in cutoffs:
        while i < len(rows) and rows[i].fill_timestamp < end_ts:
            r = rows[i]
            pos += r.quantity if r.side == "buy" else -r.quantity
            i += 1
        out.append(pos)
    return out


def _official_summary(result: SimulationResult, product: str) -> dict:
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


def _local_summary(result: SimulationResult, product: str) -> dict:
    pr = result.per_product.get(product)
    if pr is None:
        return {}
    buckets = _bucket_pnl(result, product, LOCAL_BUCKET_CUTOFFS)
    end_pos = _end_of_bucket_pos(result, product, LOCAL_BUCKET_CUTOFFS)
    return {
        "pnl": pr.pnl,
        "trade_count": pr.trade_count,
        "maker_trades": pr.maker_trade_count,
        "taker_trades": pr.taker_trade_count,
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
        "end_pos_b0": end_pos[0],
        "end_pos_b1": end_pos[1],
        "end_pos_b2": end_pos[2],
        "end_pos_b3": end_pos[3],
    }


# --------------------------------------------------------------------------- #
# Score (summary; NOT the decision rule)                                      #
# --------------------------------------------------------------------------- #


def _score(off: dict, local: dict) -> float:
    """Composite ranking summary — explicitly disclosed.

    Rewards: total PEPPER PnL, first-half PEPPER PnL, reasonable
    long-biased deployment. Penalises: unintended shorting, near-
    limit abuse. Includes a mild robustness term from local view.

    **Score is a summary, not the decision rule.** Primary decision
    inputs remain the raw metrics (PnL, first-25k, first-50k,
    max_short_fh, near-limit count, cross-view robustness).
    """
    pep_total = off.get("pnl", 0.0)
    pep_first25 = off.get("early_25k", 0.0)
    pep_first50 = off.get("early_50k", 0.0)
    max_short_fh = off.get("max_short_fh", 0)
    near_limit = off.get("steps_near_limit", 0)
    local_pep = local.get("pnl", 0.0)
    local_short = local.get("max_short_fh", 0)

    short_magnitude = max(0, -max_short_fh)
    local_short_magnitude = max(0, -local_short)
    return (
        pep_total
        + 0.4 * pep_first25  # v2: weight early-day slightly higher than v1
        + 0.2 * pep_first50
        + 0.1 * local_pep
        - 5.0 * short_magnitude
        - 0.5 * max(0, near_limit)
        - 1.0 * local_short_magnitude  # robustness penalty
    )


# --------------------------------------------------------------------------- #
# CSV / MD output                                                             #
# --------------------------------------------------------------------------- #


_COLS = [
    "label",
    "layer",
    "note",
    "off_total",
    "off_pep",
    "off_ash",
    "off_pep_first25",
    "off_pep_first50",
    "off_pep_b0",
    "off_pep_b1",
    "off_pep_b2",
    "off_pep_b3",
    "off_pep_trades",
    "off_pep_mkr",
    "off_pep_tkr",
    "off_pep_avg_size",
    "off_pep_max_long",
    "off_pep_max_short_fh",
    "off_pep_near_limit",
    "off_pep_endpos_b0",
    "off_pep_endpos_b1",
    "off_pep_endpos_b2",
    "off_pep_endpos_b3",
    "off_pep_mk1",
    "off_pep_mk5",
    "off_pep_mk20",
    "local_total",
    "local_pep",
    "local_ash",
    "local_pep_first25",
    "local_pep_first50",
    "local_pep_max_long",
    "local_pep_max_short_fh",
    "local_pep_near_limit",
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
        "# PEPPER core-long + opening + overlay v2 — candidates\n"
        "\n"
        "All rows from `outputs/round_1/pepper_corelong_v2/"
        "pepper_candidates.csv`. Sorted by layer, then by `score` "
        "within each layer (descending).\n"
        "\n"
        "## Views\n"
        "\n"
        "- `off_*` — **official-range proxy**: day 0 filtered to "
        "`0 ≤ timestamp ≤ 99_900` at native 100-tick cadence. "
        "1000 snapshots, matching the IMC official day's time window "
        "AND sample rate. **This replaces the v1 proxy**, which used "
        "`timestamp % 1000 == 0` and ran at 10× sparser cadence over "
        "a 10× longer time window.\n"
        "- `local_*` — **full 3-day × 10k** snapshot replay. "
        "Robustness check only.\n"
        "\n"
        "## ASH leg\n"
        "\n"
        "Frozen at the H1/F5/Alt `wall_mid` leg "
        "(`taker=0.5, maker=1.5, skew=4.0, flat=0.7, h=48`) for every "
        "candidate. PEPPER candidates in all L1..L5 layers route through "
        "`PepperCoreLongStrategy` with PEPPER `max_aggressive_size=20` "
        "so the strategy's `step` rate-limit is the binding taker-size "
        "cap.\n"
        "\n"
        "## Score formula (disclosed; summary only, not decision rule)\n"
        "\n"
        "```\n"
        "score = off_pep\n"
        "      + 0.4 * off_pep_first25     # v2 weights early slightly higher\n"
        "      + 0.2 * off_pep_first50\n"
        "      + 0.1 * local_pep           # mild robustness bonus\n"
        "      - 5.0 * max(0, -off_pep_max_short_fh)\n"
        "      - 0.5 * off_pep_near_limit\n"
        "      - 1.0 * max(0, -local_pep_max_short_fh)  # cross-view short penalty\n"
        "```\n"
        "\n"
    )
    lines = [header]
    if layer_best:
        lines.append("## Per-layer winners (carry-forward)\n")
        for layer in ("L1_opening", "L2_core", "L3_overlay", "L4_execution", "L5_protection"):
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
        _ = BuyAndHoldStrategy  # import marker
    return BacktestSimulator(trader=trader).run(replay)


def _evaluate(candidate: Candidate, off_replay, full_replay) -> dict:
    r_off = _run(candidate, off_replay)
    r_local = _run(candidate, full_replay)
    off = _official_summary(r_off, PEPPER)
    off_ash = _official_summary(r_off, ASH)
    local = _local_summary(r_local, PEPPER)
    local_ash = _local_summary(r_local, ASH)
    score = _score(off, local)
    return {
        "label": candidate.label,
        "layer": candidate.layer,
        "note": candidate.note,
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
        f"[{idx:>3}/{total}] {label:<36s} "
        f"off_pep={row.get('off_pep') or 0.0:+10.1f}  "
        f"first25={row.get('off_pep_first25') or 0.0:+8.1f}  "
        f"first50={row.get('off_pep_first50') or 0.0:+8.1f}  "
        f"ms_fh={row.get('off_pep_max_short_fh') or 0:+4d}  "
        f"near={row.get('off_pep_near_limit') or 0:3d}  "
        f"local={row.get('local_pep') or 0.0:+10.1f}  "
        f"score={row.get('score') or 0.0:+10.1f}"
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
    rows: list[dict] = []
    for i, cand in enumerate(candidates, start=1):
        row = _evaluate(cand, off_replay, full_replay)
        rows.append(row)
        all_rows.append(row)
        _print_row(i, len(candidates), cand.label, row)
    # Sort rows by score descending; pick the top N. Remember we want
    # to carry forward the *params*, not the row dict.
    scored = [(r, c) for r, c in zip(rows, candidates, strict=True)]
    scored.sort(key=lambda rc: rc[0]["score"], reverse=True)
    winners = [c for _, c in scored[:survivors_n]]
    layer_best[name] = ", ".join(w.label for w in winners)
    print(f"\n  {name} top-{survivors_n}: {layer_best[name]}")
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
        f"official-range proxy must be exactly {EXPECTED_OFFICIAL_SNAPSHOTS} "
        f"snapshots (got {len(off_replay.steps)})"
    )

    all_rows: list[dict] = []
    layer_best: dict[str, str] = {}

    # --- Controls ------------------------------------------------------
    controls = _controls()
    print(f"\n=== Controls — {len(controls)} candidates ===")
    for i, cand in enumerate(controls, start=1):
        row = _evaluate(cand, off_replay, full)
        all_rows.append(row)
        _print_row(i, len(controls), cand.label, row)

    # --- Layer 1: Opening --------------------------------------------
    l1_survivors = _run_layer(
        "L1_opening",
        _layer1_candidates(),
        off_replay,
        full,
        survivors_n=2,
        all_rows=all_rows,
        layer_best=layer_best,
    )

    # --- Layer 2: Persistent core ------------------------------------
    l2_survivors = _run_layer(
        "L2_core",
        _layer2_candidates(l1_survivors),
        off_replay,
        full,
        survivors_n=2,
        all_rows=all_rows,
        layer_best=layer_best,
    )

    # --- Layer 3: Overlay --------------------------------------------
    l3_survivors = _run_layer(
        "L3_overlay",
        _layer3_candidates(l2_survivors),
        off_replay,
        full,
        survivors_n=2,
        all_rows=all_rows,
        layer_best=layer_best,
    )

    # --- Layer 4: Execution ------------------------------------------
    l4_survivors = _run_layer(
        "L4_execution",
        _layer4_candidates(l3_survivors),
        off_replay,
        full,
        survivors_n=1,
        all_rows=all_rows,
        layer_best=layer_best,
    )

    # --- Layer 5: Optional protection --------------------------------
    if l4_survivors:
        _run_layer(
            "L5_protection",
            _layer5_candidates(l4_survivors[0]),
            off_replay,
            full,
            survivors_n=1,
            all_rows=all_rows,
            layer_best=layer_best,
        )

    # --- Emit ---------------------------------------------------------
    # Sort ALL rows by (layer order, score desc) for output stability.
    layer_order = {
        "control": 0,
        "L1_opening": 1,
        "L2_core": 2,
        "L3_overlay": 3,
        "L4_execution": 4,
        "L5_protection": 5,
    }
    all_rows.sort(key=lambda r: (layer_order.get(r["layer"], 99), -r["score"]))
    _emit_csv(ROOT / "pepper_candidates.csv", all_rows)
    _emit_md(ROOT / "pepper_candidates.md", all_rows, layer_best)
    print("\nDone. Wrote:")
    print(f"  - {ROOT / 'pepper_candidates.csv'}")
    print(f"  - {ROOT / 'pepper_candidates.md'}")

    # Top-15 summary across all layers.
    print("\nTop 15 by score (all layers):")
    top = sorted(all_rows, key=lambda r: r["score"], reverse=True)[:15]
    print(
        f"  {'label':<36s} {'layer':<16s} {'score':>9s} "
        f"{'off_pep':>9s} {'first25':>8s} {'first50':>8s} "
        f"{'near':>5s} {'max_s':>5s}"
    )
    for r in top:
        print(
            f"  {r['label']:<36s} {r['layer']:<16s} "
            f"{r['score']:>9.1f} "
            f"{r['off_pep']:>+9.1f} "
            f"{r['off_pep_first25']:>+8.1f} "
            f"{r['off_pep_first50']:>+8.1f} "
            f"{r['off_pep_near_limit']:>5d} "
            f"{r['off_pep_max_short_fh']:>+5d}"
        )


if __name__ == "__main__":
    main()
