"""PEPPER core-long + residual-overlay candidate search.

Runs ~25 PEPPER candidates in the single family:

    target_position = base_long + overlay(residual)
        residual = mid - drift_fair
        overlay is asymmetric (add side ≠ trim side)
        target clipped to [floor, ceiling]
        adjustment rate-limited by `step` per tick

ASH is frozen at the H1 / Alt / F5 wall-based leg for every candidate.
PEPPER is routed through ``PepperCoreLongStrategy`` (research-only,
not in ``STRATEGY_REGISTRY``) via the same runtime wiring pattern
used by ``outputs/round_1/ash_target/run_ash_target.py``.

Evaluates on two views of the local replay:

1. **Official-cadence view** — day 0 filtered to ``timestamp % 1000
   == 0``, 1000 snapshots (matches the IMC 1-per-1000 cadence; NOT
   250 as was mis-stated at plan time — verified directly against
   ``data/raw/round_1/prices_round_1_day_0.csv``).
2. **Full 3-day × 10k** snapshot replay — robustness check.

Writes:

- ``pepper_candidates.csv`` — all candidates, both views.
- ``pepper_candidates.md`` — same as markdown with an explicit score
  formula and the caveat that score is a SUMMARY, not a decision rule.

The runner does **not** export any submission bundle and does not
modify any shipped config.
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
OFFICIAL_CADENCE_STEP = 1_000
OFFICIAL_CADENCE_DAY = 0
# Near-limit threshold is 0.75 × position_limit inside the simulator.
# For limit=80 that is 60 absolute units.
NEAR_LIMIT_THRESHOLD = 60

# Bucket cutoffs in LOCAL timestamp units. The local replay runs one
# day over [0, 999_900]; the IMC official day covers [0, 99_900] at
# 100-tick cadence (= 1000 snapshots, VERIFIED directly against
# ``outputs/round_1/official_results/h1/151053.log``). We therefore
# bucket the local day into quarters at 250k / 500k / 750k / 1M so the
# reported b0..b3 ranges map cleanly onto the official 0-25k / 25k-50k
# / 50k-75k / 75k-100k buckets when projected. This fixes a latent bug
# in the Phase-9 fastsearch runner, which used the official cutoffs
# unchanged and therefore only covered the first 10% of the local day
# in its ``bucket_breakdown`` columns.
LOCAL_BUCKET_CUTOFFS: tuple[int, ...] = (250_000, 500_000, 750_000, 1_000_000)
LOCAL_EARLY_25K = 249_900  # first "quarter" (maps to official first-25k)
LOCAL_EARLY_50K = 499_900  # first "half"    (maps to official first-50k)
LOCAL_MAX_SHORT_FH_CUTOFF = 500_000  # first half in local-tick-space


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
    """Replace ``trader.strategies['market_making']`` with a per-product dispatcher.

    PEPPER routes to ``PepperCoreLongStrategy(params)``; ASH keeps the
    shipped ``MarketMakingStrategy``.
    """
    fve = trader.fair_value_engine
    sig = trader.signal_engine
    mm = MarketMakingStrategy(fve, sig)
    core_long = PepperCoreLongStrategy(fve, sig, params)
    trader.strategies["market_making"] = _PerProductStrategy(
        {ASH: mm, PEPPER: core_long}
    )


# --------------------------------------------------------------------------- #
# Base engine (ASH = H1/F5/Alt wall_mid leg, PEPPER = promoted, max_agg = 20) #
# --------------------------------------------------------------------------- #


def _base_engine() -> EngineConfig:
    """H1 engine base (wall_mid ASH + promoted PEPPER).

    The PEPPER leg is effectively a stub because every research
    candidate swaps in ``PepperCoreLongStrategy``. We bump
    ``max_aggressive_size`` on PEPPER to 20 so the strategy's ``step``
    rate-limit is the binding constraint (not the per-tick taker cap
    of the default promoted leg, which is 8).
    """
    base = round1_h1_engine_config()
    products = dict(base.products)
    pep = products[PEPPER]
    # Keep linear_drift FV, shift max_aggressive_size up so step is the
    # effective rate limit. Quote size matches the strategy's natural
    # upper bound on a single tick.
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
    engine: EngineConfig
    pepper_params: CoreLongParams | None  # None → use the engine's configured strategy
    note: str


# --------------------------------------------------------------------------- #
# Controls                                                                    #
# --------------------------------------------------------------------------- #


def _controls() -> list[Candidate]:
    return [
        Candidate(
            label="C_promoted",
            engine=round1_promoted_engine_config(),
            pepper_params=None,
            note="Control: promoted PEPPER (linear_drift t=2.0 skew=2 flat=0.7)",
        ),
        Candidate(
            label="C_alt",
            engine=round1_alt_engine_config(),
            pepper_params=None,
            note="Control: alt PEPPER (linear_drift t=2.0 skew=1 flat=0.9)",
        ),
        Candidate(
            label="C_f5",
            engine=round1_f5_engine_config(),
            pepper_params=None,
            note="Control: F5 PEPPER (asymmetric taker buy=1.5 sell=3.0)",
        ),
        Candidate(
            label="C_buyhold",
            engine=round1_test_engine_config(),
            pepper_params=None,
            note="Control: buy-and-hold PEPPER (directional upper-bound ref)",
        ),
        Candidate(
            # Pure drift-carry baseline inside the new family: base_long
            # with all overlay gains OFF. Separates drift carry from
            # overlay contribution. Requested by the user.
            label="C_corelong_only",
            engine=_base_engine(),
            pepper_params=CoreLongParams(
                base_long=30,
                add_thresh=1000.0,  # so the add branch never fires
                trim_thresh=1000.0,  # so the trim branch never fires
                add_gain=0.0,
                trim_gain=0.0,
                floor=0,
                ceiling=80,
                step=8,
                exec_style="hybrid",
                hybrid_threshold=2.0,
            ),
            note="Control: core-long = 30, NO overlay (pure drift carry baseline)",
        ),
    ]


# --------------------------------------------------------------------------- #
# Family candidates (nominal-centered ladders)                                #
# --------------------------------------------------------------------------- #


# Nominal default — every axis sweep perturbs ONE dimension off this.
_NOMINAL = CoreLongParams(
    base_long=30,
    add_thresh=3.0,
    trim_thresh=5.0,
    add_gain=3.0,
    trim_gain=1.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style="hybrid",
    hybrid_threshold=2.0,
)


def _C(label: str, note: str, **overrides) -> Candidate:
    """Build a candidate by perturbing the nominal along one axis."""
    params = replace(_NOMINAL, **overrides)
    return Candidate(
        label=label,
        engine=_base_engine(),
        pepper_params=params,
        note=note,
    )


def _family_candidates() -> list[Candidate]:
    out: list[Candidate] = []

    # --- B. base_long ladder (5) ---------------------------------------
    for bl in (10, 20, 30, 40, 50):
        out.append(
            _C(
                f"B_base{bl:02d}",
                f"base_long={bl}, default overlay",
                base_long=bl,
            )
        )

    # --- C. add_thresh ladder (3) --------------------------------------
    for thr in (1.5, 3.0, 5.0):
        out.append(
            _C(
                f"C_add{thr:g}",
                f"add_thresh={thr}, default trim",
                add_thresh=thr,
            )
        )

    # --- D. trim_thresh ladder (3) -------------------------------------
    for thr in (3.0, 5.0, 7.0):
        out.append(
            _C(
                f"D_trim{thr:g}",
                f"trim_thresh={thr}, default add",
                trim_thresh=thr,
            )
        )

    # --- E. floor ladder (3) -------------------------------------------
    for fl in (0, 10, 20):
        out.append(
            _C(
                f"E_floor{fl:02d}",
                f"floor={fl}, default overlay",
                floor=fl,
            )
        )

    # --- F. step ladder (3) --------------------------------------------
    for step in (4, 8, 16):
        out.append(
            _C(
                f"F_step{step:02d}",
                f"step={step} (adjustment speed)",
                step=step,
            )
        )

    # --- G. exec_style (2) ---------------------------------------------
    out.append(_C("G_maker", "exec_style=maker (passive only)", exec_style="maker"))
    out.append(_C("G_taker", "exec_style=taker (no passive quotes)", exec_style="taker"))

    # --- H. Upside alternate (2) ---------------------------------------
    # More aggressive add + higher base_long + wider trim band.
    out.append(
        Candidate(
            label="H_upside40_agg",
            engine=_base_engine(),
            pepper_params=replace(
                _NOMINAL,
                base_long=40,
                add_thresh=1.5,
                add_gain=5.0,
                trim_thresh=7.0,
                trim_gain=0.5,
                step=12,
                floor=10,
            ),
            note="Upside: base=40 + aggressive add + wider trim + floor=10",
        )
    )
    out.append(
        Candidate(
            label="H_upside50_agg",
            engine=_base_engine(),
            pepper_params=replace(
                _NOMINAL,
                base_long=50,
                add_thresh=2.0,
                add_gain=4.0,
                trim_thresh=8.0,
                trim_gain=0.5,
                step=12,
                floor=20,
            ),
            note="Upside: base=50 + aggressive add + wider trim + floor=20",
        )
    )

    return out


def candidate_list() -> list[Candidate]:
    return [*_controls(), *_family_candidates()]


# --------------------------------------------------------------------------- #
# Replay loaders                                                              #
# --------------------------------------------------------------------------- #


def _load_full_replay() -> ReplayEngine:
    price_files = sorted(DATA_DIR.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(DATA_DIR.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {DATA_DIR}")
    return ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)


def _official_cadence_replay(full: ReplayEngine) -> ReplayEngine:
    filtered: list[ReplayStep] = [
        s
        for s in full.steps
        if s.day == OFFICIAL_CADENCE_DAY and s.timestamp % OFFICIAL_CADENCE_STEP == 0
    ]
    return ReplayEngine(filtered)


# --------------------------------------------------------------------------- #
# Metric helpers (analogous to Phase-9 fastsearch)                            #
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


def _max_short_first_half(result: SimulationResult, product: str) -> int:
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
            if r.fill_timestamp > LOCAL_MAX_SHORT_FH_CUTOFF:
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
        OFFICIAL_CADENCE_DAY if OFFICIAL_CADENCE_DAY in by_day else next(iter(by_day))
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


def _summary(result: SimulationResult, product: str) -> dict:
    pr = result.per_product.get(product)
    if pr is None:
        return {}
    buckets = _bucket_pnl(result, product, LOCAL_BUCKET_CUTOFFS)
    end_pos = _end_of_bucket_pos(result, product, LOCAL_BUCKET_CUTOFFS)
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
        "early_25k": _early_day_pnl(result, product, LOCAL_EARLY_25K),
        "early_50k": _early_day_pnl(result, product, LOCAL_EARLY_50K),
        "bucket_0_25": buckets[0],
        "bucket_25_50": buckets[1],
        "bucket_50_75": buckets[2],
        "bucket_75_100": buckets[3],
        "max_short_fh": _max_short_first_half(result, product),
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
    """Composite ranking summary — explicitly printed in the MD.

    Primary decision inputs are the raw metrics (total PEPPER PnL,
    first-25k / first-50k PnL, max_short_fh, near-limit count,
    robustness across views). This score is a SUMMARY, not a
    decision rule. See shortlist.md for how the score interacts
    with the shortlist selection.
    """
    pep_total = off.get("pnl", 0.0)
    pep_first25 = off.get("early_25k", 0.0)
    pep_first50 = off.get("early_50k", 0.0)
    max_short_fh = off.get("max_short_fh", 0)
    near_limit = off.get("steps_near_limit", 0)
    local_pep = local.get("pnl", 0.0)

    # Magnitude of unintended shorting (0 if never short).
    short_magnitude = max(0, -max_short_fh)
    return (
        pep_total
        + 0.3 * pep_first25
        + 0.2 * local_pep  # mild robustness bonus; local scale >> official
        - 5.0 * short_magnitude
        - 0.5 * max(0, near_limit)
        + 0.0 * pep_first50  # first50 already absorbed into pep_total
    )


# --------------------------------------------------------------------------- #
# CSV / MD output                                                             #
# --------------------------------------------------------------------------- #


_COLS = [
    "label",
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


def _emit_md(path: Path, rows: list[dict]) -> None:
    header = (
        "# PEPPER core-long + residual-overlay candidates\n"
        "\n"
        "Sorted by `score` (descending). **Score is a summary, not the "
        "decision rule.** Primary interpretation comes from the raw "
        "metrics: `off_pep` (official-cadence total PEPPER PnL), "
        "`off_pep_first25` / `off_pep_first50` (early-day capture), "
        "`off_pep_max_short_fh` (unintended shorting), "
        "`off_pep_near_limit` (near-limit snapshots), plus the "
        "`local_*` robustness columns.\n"
        "\n"
        "## Score formula (disclosed, not hidden)\n"
        "\n"
        "```\n"
        "score = off_pep\n"
        "      + 0.3 * off_pep_first25\n"
        "      + 0.2 * local_pep       # mild cross-view robustness\n"
        "      - 5.0 * max(0, -off_pep_max_short_fh)\n"
        "      - 0.5 * off_pep_near_limit\n"
        "```\n"
        "\n"
        "## Views\n"
        "\n"
        "- `off_*` — **official-cadence view**: day 0 filtered to "
        "`timestamp % 1000 == 0`. Verified 1000 snapshots, matching the "
        "IMC 1-per-1000 sample rate on the one official Round-1 day.\n"
        "- `local_*` — **full 3-day × 10k** snapshot replay. Used for "
        "robustness only.\n"
        "\n"
        "## ASH leg\n"
        "\n"
        "Frozen at the H1 / Alt / F5 wall-based leg "
        "(`wall_mid, t=0.5, m=1.5, skew=4.0, flat=0.7, h=48`) for every "
        "candidate. PEPPER candidates in the `B..H` families route "
        "through the research-only `PepperCoreLongStrategy` with PEPPER "
        "`max_aggressive_size=20` so the strategy's `step` rate-limit "
        "is the binding taker-size cap.\n"
        "\n"
    )
    lines = [header]
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
        # If the engine's PEPPER strategy is buy_and_hold, make sure
        # the per-product dispatch still uses MarketMakingStrategy for
        # ASH and BuyAndHoldStrategy for PEPPER (which is what the
        # factory intends). Trader already handles this via STRATEGY_
        # REGISTRY — no override needed.
        _ = BuyAndHoldStrategy  # re-export marker for import clarity
    return BacktestSimulator(trader=trader).run(replay)


def main() -> None:
    full = _load_full_replay()
    official = _official_cadence_replay(full)
    print(
        f"[loaded] full 3-day = {len(full.steps)} steps | "
        f"official-cadence day {OFFICIAL_CADENCE_DAY} at {OFFICIAL_CADENCE_STEP}-step "
        f"= {len(official.steps)} steps"
    )
    assert 900 <= len(official.steps) <= 1100, (
        f"official-cadence view should be ~1000 snapshots (got {len(official.steps)})"
    )

    candidates = candidate_list()
    print(f"[candidates] {len(candidates)} total\n")

    rows: list[dict] = []
    for i, cand in enumerate(candidates):
        r_off = _run(cand, official)
        r_local = _run(cand, full)
        off = _summary(r_off, PEPPER)
        off_ash = _summary(r_off, ASH)
        local = _summary(r_local, PEPPER)
        local_ash = _summary(r_local, ASH)
        score = _score(off, local)
        rows.append(
            {
                "label": cand.label,
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
        )
        print(
            f"[{i + 1:>2}/{len(candidates)}] {cand.label:<22s} "
            f"off_pep={off.get('pnl', 0):+9.1f}  "
            f"first25={off.get('early_25k', 0):+7.1f}  "
            f"first50={off.get('early_50k', 0):+7.1f}  "
            f"ms_fh={off.get('max_short_fh', 0):+4d}  "
            f"near_lim={off.get('steps_near_limit', 0):3d}  "
            f"local={local.get('pnl', 0):+10.1f}  "
            f"score={score:+10.1f}"
        )

    rows.sort(key=lambda r: r["score"], reverse=True)
    _emit_csv(ROOT / "pepper_candidates.csv", rows)
    _emit_md(ROOT / "pepper_candidates.md", rows)
    print("\nDone. Wrote:")
    print(f"  - {ROOT / 'pepper_candidates.csv'}")
    print(f"  - {ROOT / 'pepper_candidates.md'}")

    # Compact top-10 summary for diagnostic scrolling.
    print("\nTop 10 by score:")
    print(
        f"  {'label':<22s} {'score':>9s} {'off_pep':>9s} "
        f"{'first25':>8s} {'first50':>8s} {'near':>5s} {'max_s':>5s}"
    )
    for r in rows[:10]:
        print(
            f"  {r['label']:<22s} {r['score']:>9.1f} "
            f"{r['off_pep']:>+9.1f} "
            f"{r['off_pep_first25']:>+8.1f} "
            f"{r['off_pep_first50']:>+8.1f} "
            f"{r['off_pep_near_limit']:>5d} "
            f"{r['off_pep_max_short_fh']:>+5d}"
        )


if __name__ == "__main__":
    main()
