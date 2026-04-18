"""Phase 8.5 targeted follow-up — PEPPER + ASH candidate runner.

Runs a small, interpretable set of candidate configs against the
Round-1 local replay (3 days × 10 000 snapshots). Emits bucketed and
aggregate PnL so the Phase-8.5 memo can narrow the next upload
shortlist without any broad sweeping.

Usage::

    PYTHONPATH=. .venv/bin/python \
        outputs/round_1/phase8_5/run_phase8_5.py

Outputs under ``outputs/round_1/phase8_5/``:
    pepper_candidates.{csv,md}
    ash_candidates.{csv,md}
    combined_shortlist.{csv,md}
"""

from __future__ import annotations

import csv
import statistics
from dataclasses import replace
from pathlib import Path

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    round1_alt_engine_config,
    round1_baseline_engine_config,
    round1_engine_config,
    round1_promoted_engine_config,
)
from src.trader import Trader

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path("data/raw/round_1")
ASH = "ASH_COATED_OSMIUM"
PEPPER = "INTARIAN_PEPPER_ROOT"


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------

def _swap(engine: EngineConfig, product: str, **overrides) -> EngineConfig:
    base = engine.product_config(product)
    assert base is not None, product
    new_products = dict(engine.products)
    new_products[product] = replace(base, **overrides)
    return EngineConfig(
        state_version=engine.state_version,
        max_trader_data_chars=engine.max_trader_data_chars,
        diagnostics_verbosity=engine.diagnostics_verbosity,
        products=new_products,
        scanner_config=engine.scanner_config,
        residual_config=engine.residual_config,
    )


def pepper_configs() -> dict[str, EngineConfig]:
    """5 PEPPER candidates, each modifying ONLY the PEPPER leg.

    ASH is held at the shipped **promoted** leg in all PEPPER trials so
    the PEPPER comparison is clean.
    """
    promoted = round1_promoted_engine_config()
    alt = round1_alt_engine_config()

    out = {
        # P0: shipped promoted (baseline of this workstream)
        "P0_promoted": promoted,
        # P1: shipped alt (upside reference)
        "P1_alt_upside": _swap(
            promoted,
            PEPPER,
            **_config_dict(alt.product_config(PEPPER)),
        ),
        # P2: faster fair value — promoted with history_length=16
        "P2_h16_fast_fv": _swap(
            promoted, PEPPER, history_length=16,
        ),
        # P3: stronger inventory aversion via larger skew
        "P3_skew4_recovery": _swap(
            promoted, PEPPER, inventory_skew=4.0,
        ),
        # P4: earlier flattening, 0.5 (trigger flatten at ±25 units)
        "P4_flat50_early": _swap(
            promoted, PEPPER, flatten_threshold=0.5,
        ),
    }
    return out


def ash_configs() -> dict[str, EngineConfig]:
    """4 ASH candidates, each modifying ONLY the ASH leg.

    PEPPER is held at the shipped **promoted** leg in all ASH trials.
    """
    promoted = round1_promoted_engine_config()
    alt = round1_alt_engine_config()

    out = {
        # A0: shipped promoted
        "A0_promoted_ewma_t025": promoted,
        # A1: shipped alt
        "A1_alt_wall_t05_m15": _swap(
            promoted,
            ASH,
            **_config_dict(alt.product_config(ASH)),
        ),
        # A2: promoted FV, looser taker edge (0.5 instead of 0.25)
        "A2_ewma_t05": _swap(
            promoted, ASH, taker_edge=0.5,
        ),
        # A3: alt FV, promoted-style maker (m=1.0 instead of 1.5)
        "A3_wall_t05_m10": _swap(
            promoted, ASH,
            fair_value_method="wall_mid",
            fair_value_fallbacks=("mid", "microprice"),
            taker_edge=0.5,
            maker_edge=1.0,
            history_length=48,
        ),
    }
    return out


def combined_configs(best_ash_key: str, best_pepper_key: str) -> dict[str, EngineConfig]:
    """Build 2–3 combined candidates from the winning legs."""
    promoted = round1_promoted_engine_config()
    alt = round1_alt_engine_config()
    ash_cfg = ash_configs()[best_ash_key].product_config(ASH)
    pepper_cfg = pepper_configs()[best_pepper_key].product_config(PEPPER)
    assert ash_cfg is not None and pepper_cfg is not None

    # C0 = shipped promoted
    c0 = promoted
    # C1 = winning ASH + winning PEPPER
    c1 = _swap(
        _swap(promoted, ASH, **_config_dict(ash_cfg)),
        PEPPER,
        **_config_dict(pepper_cfg),
    )
    # C2 = alt variant = shipped alt (upside reference)
    c2 = alt

    return {
        "C0_promoted_control": c0,
        "C1_best_combined": c1,
        "C2_alt_upside": c2,
    }


def _config_dict(pc) -> dict:
    return {
        "fair_value_method": pc.fair_value_method,
        "fair_value_fallbacks": pc.fair_value_fallbacks,
        "tick_size": pc.tick_size,
        "anchor_price": pc.anchor_price,
        "taker_edge": pc.taker_edge,
        "maker_edge": pc.maker_edge,
        "quote_size": pc.quote_size,
        "max_aggressive_size": pc.max_aggressive_size,
        "inventory_skew": pc.inventory_skew,
        "flatten_threshold": pc.flatten_threshold,
        "history_length": pc.history_length,
        "ewma_alpha": pc.ewma_alpha,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _load_replay() -> ReplayEngine:
    price_files = sorted(DATA_DIR.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(DATA_DIR.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {DATA_DIR}")
    return ReplayEngine.from_files(
        price_paths=price_files, trade_paths=trade_files
    )


def _run_one(engine: EngineConfig, replay: ReplayEngine) -> SimulationResult:
    trader = Trader(config=engine)
    return BacktestSimulator(trader=trader).run(replay)


# ---------------------------------------------------------------------------
# Metrics extraction
# ---------------------------------------------------------------------------


def _early_day_pnl(result: SimulationResult, product: str, end_ts: int) -> float:
    """Sum of (last_in_day_pnl_up_to_end_ts - 0) across all days."""
    # pnl_series per product: ordered list of (timestamp, cumulative_pnl).
    # mid_keys / pnl_keys carry (day, timestamp). Use pnl_keys to know day.
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    if not series or not keys:
        return 0.0
    # Walk per-day
    total = 0.0
    prev_day_end = 0.0
    current_day = None
    last_val_before_end = None
    day_start_val = 0.0
    for (day, ts), (_ts, val) in zip(keys, series):
        if day != current_day:
            # close previous day
            if current_day is not None and last_val_before_end is not None:
                total += last_val_before_end - day_start_val
            current_day = day
            day_start_val = val  # starting value for this new day's cumulative
            last_val_before_end = None
        if ts <= end_ts:
            last_val_before_end = val
    if last_val_before_end is not None:
        total += last_val_before_end - day_start_val
    return total


def _per_day_pnl(result: SimulationResult, product: str) -> list[tuple[int, float]]:
    """Return (day, total_day_pnl) list."""
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    out: list[tuple[int, float]] = []
    current_day = None
    day_start = 0.0
    last_val = 0.0
    for (day, ts), (_ts, val) in zip(keys, series):
        if day != current_day:
            if current_day is not None:
                out.append((current_day, last_val - day_start))
            current_day = day
            day_start = val
        last_val = val
    if current_day is not None:
        out.append((current_day, last_val - day_start))
    return out


def _max_short_first_half(result: SimulationResult, product: str) -> int:
    """Running min of position over the first 50k of each day, then take
    the deepest short across all days (most negative).

    Derived by sweeping trade_records with side-aware quantity applied.
    """
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return 0
    # Group by day
    by_day: dict[int, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    deepest = 0
    for day, rs in by_day.items():
        rs.sort(key=lambda r: r.fill_timestamp)
        pos = 0
        for r in rs:
            if r.fill_timestamp > 50_000:
                break
            pos += r.quantity if r.side == "buy" else -r.quantity
            deepest = min(deepest, pos)
    return deepest


def _pnl_by_bucket(result: SimulationResult, product: str, day_buckets=(25_000, 50_000, 75_000, 100_000)) -> list[float]:
    """Aggregate per-day bucketed PnL across all days.

    Returns 4 values: Σ_days PnL(bucket i) where buckets split one day's
    timestamps into [0,25k), [25k,50k), [50k,75k), [75k,100k).
    """
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    totals = [0.0] * len(day_buckets)
    if not series:
        return totals

    # Group by day, record cumulative values at bucket boundaries
    by_day: dict[int, list[tuple[int, float]]] = {}
    for (day, ts), (_ts, val) in zip(keys, series):
        by_day.setdefault(day, []).append((ts, val))

    for day, day_series in by_day.items():
        day_start = day_series[0][1] if day_series else 0.0
        # For each bucket end, find the last timestamp <= end_ts
        prev_val = day_start
        for i, end_ts in enumerate(day_buckets):
            last_val = prev_val
            for ts, v in day_series:
                if ts < end_ts:
                    last_val = v
            totals[i] += last_val - prev_val
            prev_val = last_val
    return totals


def _summary(result: SimulationResult, product: str) -> dict:
    pr = result.per_product.get(product)
    assert pr is not None, product
    buckets = _pnl_by_bucket(result, product)
    return {
        "pnl": pr.pnl,
        "trade_count": pr.trade_count,
        "maker_trades": pr.maker_trade_count,
        "taker_trades": pr.taker_trade_count,
        "maker_qty": pr.maker_trade_quantity,
        "taker_qty": pr.taker_trade_quantity,
        "final_pos": pr.final_position,
        "steps_near_limit": pr.steps_near_limit,
        "avg_entry_edge": pr.avg_entry_edge,
        "avg_markout_1": pr.avg_markout_1,
        "avg_markout_5": pr.avg_markout_5,
        "avg_markout_20": pr.avg_markout_20,
        "early_25k": _early_day_pnl(result, product, 24_900),
        "early_50k": _early_day_pnl(result, product, 49_900),
        "bucket_0_25": buckets[0],
        "bucket_25_50": buckets[1],
        "bucket_50_75": buckets[2],
        "bucket_75_100": buckets[3],
        "max_short_first_half": _max_short_first_half(result, product),
        "per_day": _per_day_pnl(result, product),
    }


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------


PEPPER_COLS = [
    "label",
    "pnl_pep",
    "early25_pep",
    "early50_pep",
    "b0_pep",
    "b1_pep",
    "b2_pep",
    "b3_pep",
    "trades_pep",
    "mkr_pep",
    "tkr_pep",
    "edge_pep",
    "mk1_pep",
    "mk5_pep",
    "mk20_pep",
    "final_pos_pep",
    "max_short_fh_pep",
    "near_limit_pep",
    "pnl_ash",
    "total_pnl",
]

ASH_COLS = [
    "label",
    "pnl_ash",
    "b0_ash",
    "b1_ash",
    "b2_ash",
    "b3_ash",
    "trades_ash",
    "mkr_ash",
    "tkr_ash",
    "edge_ash",
    "mk1_ash",
    "mk5_ash",
    "mk20_ash",
    "final_pos_ash",
    "near_limit_ash",
    "late_pnl_ash",
    "pnl_pep",
    "total_pnl",
]

COMBINED_COLS = [
    "label",
    "total_pnl",
    "pnl_ash",
    "pnl_pep",
    "b0_ash",
    "b3_ash",
    "b0_pep",
    "b3_pep",
    "trades_ash",
    "trades_pep",
    "near_limit_ash",
    "near_limit_pep",
    "max_short_fh_pep",
]


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def emit_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in cols})


def emit_md(path: Path, title: str, cols: list[str], rows: list[dict]) -> None:
    lines = [f"# {title}\n"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    lines.append("")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    replay = _load_replay()
    print(f"[loaded] {len(replay.steps)} replay steps")

    # --- PEPPER workstream -------------------------------------------------
    pepper_rows: list[dict] = []
    results_pep: dict[str, SimulationResult] = {}
    for label, engine in pepper_configs().items():
        result = _run_one(engine, replay)
        results_pep[label] = result
        p = _summary(result, PEPPER)
        a = _summary(result, ASH)
        pepper_rows.append(
            {
                "label": label,
                "pnl_pep": p["pnl"],
                "early25_pep": p["early_25k"],
                "early50_pep": p["early_50k"],
                "b0_pep": p["bucket_0_25"],
                "b1_pep": p["bucket_25_50"],
                "b2_pep": p["bucket_50_75"],
                "b3_pep": p["bucket_75_100"],
                "trades_pep": p["trade_count"],
                "mkr_pep": p["maker_trades"],
                "tkr_pep": p["taker_trades"],
                "edge_pep": p["avg_entry_edge"],
                "mk1_pep": p["avg_markout_1"],
                "mk5_pep": p["avg_markout_5"],
                "mk20_pep": p["avg_markout_20"],
                "final_pos_pep": p["final_pos"],
                "max_short_fh_pep": p["max_short_first_half"],
                "near_limit_pep": p["steps_near_limit"],
                "pnl_ash": a["pnl"],
                "total_pnl": result.total_pnl,
            }
        )
        print(
            f"[pep] {label:<24s} pnl_pep={p['pnl']:+8.1f} "
            f"early25={p['early_25k']:+7.1f} max_short_fh={p['max_short_first_half']:+4d} "
            f"b0={p['bucket_0_25']:+7.1f} total={result.total_pnl:+8.1f}"
        )

    emit_csv(ROOT / "pepper_candidates.csv", PEPPER_COLS, pepper_rows)
    emit_md(ROOT / "pepper_candidates.md", "PEPPER candidates (local replay, 3 days × 10k)", PEPPER_COLS, pepper_rows)

    # --- ASH workstream ----------------------------------------------------
    ash_rows: list[dict] = []
    results_ash: dict[str, SimulationResult] = {}
    for label, engine in ash_configs().items():
        result = _run_one(engine, replay)
        results_ash[label] = result
        a = _summary(result, ASH)
        p = _summary(result, PEPPER)
        # "late_pnl_ash" ≡ sum over bucket 2+3 of ASH
        late = a["bucket_50_75"] + a["bucket_75_100"]
        ash_rows.append(
            {
                "label": label,
                "pnl_ash": a["pnl"],
                "b0_ash": a["bucket_0_25"],
                "b1_ash": a["bucket_25_50"],
                "b2_ash": a["bucket_50_75"],
                "b3_ash": a["bucket_75_100"],
                "trades_ash": a["trade_count"],
                "mkr_ash": a["maker_trades"],
                "tkr_ash": a["taker_trades"],
                "edge_ash": a["avg_entry_edge"],
                "mk1_ash": a["avg_markout_1"],
                "mk5_ash": a["avg_markout_5"],
                "mk20_ash": a["avg_markout_20"],
                "final_pos_ash": a["final_pos"],
                "near_limit_ash": a["steps_near_limit"],
                "late_pnl_ash": late,
                "pnl_pep": p["pnl"],
                "total_pnl": result.total_pnl,
            }
        )
        print(
            f"[ash] {label:<24s} pnl_ash={a['pnl']:+8.1f} "
            f"trades={a['trade_count']:3d} tkr={a['taker_trades']:3d} "
            f"mk20={(a['avg_markout_20'] if a['avg_markout_20'] is not None else float('nan')):+.3f} "
            f"total={result.total_pnl:+8.1f}"
        )
    emit_csv(ROOT / "ash_candidates.csv", ASH_COLS, ash_rows)
    emit_md(ROOT / "ash_candidates.md", "ASH candidates (local replay, 3 days × 10k)", ASH_COLS, ash_rows)

    # --- Combined ----------------------------------------------------------
    # Best PEPPER = argmax of pnl_pep among candidates that don't add extra near-limit time
    # over the shipped promoted.
    promoted_near = next(r for r in pepper_rows if r["label"] == "P0_promoted")["near_limit_pep"]
    pepper_ok = [r for r in pepper_rows if r["near_limit_pep"] <= promoted_near + 5 or r["label"].startswith("P1_alt")]
    best_pepper = max(pepper_ok, key=lambda r: r["pnl_pep"])["label"]

    # Best ASH = argmax of pnl_ash among all candidates
    best_ash = max(ash_rows, key=lambda r: r["pnl_ash"])["label"]

    print(f"[combine] best ASH={best_ash}, best PEPPER={best_pepper}")

    combined_rows: list[dict] = []
    for label, engine in combined_configs(best_ash, best_pepper).items():
        result = _run_one(engine, replay)
        a = _summary(result, ASH)
        p = _summary(result, PEPPER)
        combined_rows.append(
            {
                "label": label,
                "total_pnl": result.total_pnl,
                "pnl_ash": a["pnl"],
                "pnl_pep": p["pnl"],
                "b0_ash": a["bucket_0_25"],
                "b3_ash": a["bucket_75_100"],
                "b0_pep": p["bucket_0_25"],
                "b3_pep": p["bucket_75_100"],
                "trades_ash": a["trade_count"],
                "trades_pep": p["trade_count"],
                "near_limit_ash": a["steps_near_limit"],
                "near_limit_pep": p["steps_near_limit"],
                "max_short_fh_pep": p["max_short_first_half"],
            }
        )
        print(
            f"[comb] {label:<24s} total={result.total_pnl:+9.1f} "
            f"ash={a['pnl']:+8.1f} pep={p['pnl']:+8.1f} "
            f"pep_ms_fh={p['max_short_first_half']:+4d}"
        )

    emit_csv(ROOT / "combined_shortlist.csv", COMBINED_COLS, combined_rows)
    emit_md(ROOT / "combined_shortlist.md", "Combined candidates (local replay, 3 days × 10k)", COMBINED_COLS, combined_rows)

    print("\nDone. Outputs:")
    for name in [
        "pepper_candidates.csv",
        "pepper_candidates.md",
        "ash_candidates.csv",
        "ash_candidates.md",
        "combined_shortlist.csv",
        "combined_shortlist.md",
    ]:
        print(" -", ROOT / name)


if __name__ == "__main__":
    main()
