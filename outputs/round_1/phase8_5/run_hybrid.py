"""Phase 8.5 narrow hybrid-candidate pass.

Builds and compares exactly four combined candidates against the
Round-1 local replay (3 days × 10 000 snapshots):

    Promoted  : shipped promoted (control)
    Alt       : shipped alt (upside reference)
    H1        : promoted PEPPER + Alt ASH leg (wall_mid, t=0.5, m=1.5)
    H2        : promoted PEPPER + A3 ASH leg  (wall_mid, t=0.5, m=1.0)

The goal is to answer: **does swapping only the ASH leg produce a
better next upload than the current promoted?**

No broad tuning, no PEPPER code changes, no silent promotion — this
script only emits CSV, MD, and memo under
``outputs/round_1/phase8_5/``.

Usage::

    PYTHONPATH=. .venv/bin/python \
        outputs/round_1/phase8_5/run_hybrid.py
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from src.backtest.metrics import SimulationResult
from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.core.config import (
    EngineConfig,
    round1_alt_engine_config,
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
    """Return a new EngineConfig with one product's config overridden."""
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


def hybrid_configs() -> dict[str, EngineConfig]:
    """Four combined candidates. PEPPER stays on promoted for H1/H2."""
    promoted = round1_promoted_engine_config()
    alt = round1_alt_engine_config()

    # Shared ASH-leg parameters for H1/H2 — both use wall_mid and the
    # tighter taker_edge=0.5; only the maker width differs.
    ash_common = dict(
        fair_value_method="wall_mid",
        fair_value_fallbacks=("mid", "microprice"),
        taker_edge=0.5,
        inventory_skew=4.0,
        flatten_threshold=0.7,
        history_length=48,
    )

    return {
        "Promoted": promoted,
        "Alt": alt,
        "H1_pepP_ashA1_wall_t05_m15": _swap(
            promoted, ASH, maker_edge=1.5, **ash_common,
        ),
        "H2_pepP_ashA3_wall_t05_m10": _swap(
            promoted, ASH, maker_edge=1.0, **ash_common,
        ),
    }


# ---------------------------------------------------------------------------
# Runner + metrics (borrowed from run_phase8_5.py — kept local to this file
# so the hybrid pass is self-contained).
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


def _early_day_pnl(
    result: SimulationResult, product: str, end_ts: int
) -> float:
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    if not series or not keys:
        return 0.0
    total = 0.0
    current_day = None
    last_val_before_end = None
    day_start_val = 0.0
    for (day, ts), (_ts, val) in zip(keys, series):
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


def _pnl_by_bucket(
    result: SimulationResult,
    product: str,
    day_buckets: tuple[int, ...] = (25_000, 50_000, 75_000, 100_000),
) -> list[float]:
    series = result.pnl_series.get(product, ())
    keys = result.pnl_keys.get(product, ())
    totals = [0.0] * len(day_buckets)
    if not series:
        return totals

    by_day: dict[int, list[tuple[int, float]]] = {}
    for (day, ts), (_ts, val) in zip(keys, series):
        by_day.setdefault(day, []).append((ts, val))

    for _day, day_series in by_day.items():
        day_start = day_series[0][1] if day_series else 0.0
        prev_val = day_start
        for i, end_ts in enumerate(day_buckets):
            last_val = prev_val
            for ts, v in day_series:
                if ts < end_ts:
                    last_val = v
            totals[i] += last_val - prev_val
            prev_val = last_val
    return totals


def _max_short_first_half(result: SimulationResult, product: str) -> int:
    records = [r for r in result.trade_records if r.product == product]
    if not records:
        return 0
    by_day: dict[int, list] = {}
    for r in records:
        by_day.setdefault(r.fill_day, []).append(r)
    deepest = 0
    for _day, rs in by_day.items():
        rs.sort(key=lambda r: r.fill_timestamp)
        pos = 0
        for r in rs:
            if r.fill_timestamp > 50_000:
                break
            pos += r.quantity if r.side == "buy" else -r.quantity
            deepest = min(deepest, pos)
    return deepest


def _summary(result: SimulationResult, product: str) -> dict:
    pr = result.per_product.get(product)
    assert pr is not None, product
    buckets = _pnl_by_bucket(result, product)
    return {
        "pnl": pr.pnl,
        "trade_count": pr.trade_count,
        "maker_trades": pr.maker_trade_count,
        "taker_trades": pr.taker_trade_count,
        "final_pos": pr.final_position,
        "near_limit": pr.steps_near_limit,
        "avg_entry_edge": pr.avg_entry_edge,
        "mk1": pr.avg_markout_1,
        "mk5": pr.avg_markout_5,
        "mk20": pr.avg_markout_20,
        "early_25k": _early_day_pnl(result, product, 24_900),
        "early_50k": _early_day_pnl(result, product, 49_900),
        "b0": buckets[0],
        "b1": buckets[1],
        "b2": buckets[2],
        "b3": buckets[3],
        "max_short_fh": _max_short_first_half(result, product),
    }


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------


COLS = [
    "label",
    "total_pnl",
    "pnl_ash",
    "pnl_pep",
    # ASH detail
    "ash_trades",
    "ash_mkr",
    "ash_tkr",
    "ash_edge",
    "ash_mk20",
    "ash_b0",
    "ash_b1",
    "ash_b2",
    "ash_b3",
    "ash_final_pos",
    "ash_near_limit",
    # PEPPER detail
    "pep_trades",
    "pep_mkr",
    "pep_tkr",
    "pep_edge",
    "pep_mk20",
    "pep_b0",
    "pep_b1",
    "pep_b2",
    "pep_b3",
    "pep_final_pos",
    "pep_near_limit",
    "pep_early25",
    "pep_max_short_fh",
]


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def emit_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in COLS})


def emit_md(path: Path, rows: list[dict]) -> None:
    """Emit a narrow markdown table — the full flat table is in the CSV."""
    narrow_cols = [
        "label",
        "total_pnl",
        "pnl_ash",
        "pnl_pep",
        "ash_trades",
        "ash_mkr",
        "ash_tkr",
        "ash_mk20",
        "ash_near_limit",
        "pep_trades",
        "pep_early25",
        "pep_max_short_fh",
        "pep_near_limit",
    ]
    lines = [
        "# Hybrid shortlist — local replay (3 days × 10k snapshots)\n",
        "See `run_hybrid.py` for candidate definitions. Full per-bucket "
        "detail in `hybrid_shortlist.csv`.\n",
    ]
    lines.append("| " + " | ".join(narrow_cols) + " |")
    lines.append("|" + "|".join(["---"] * len(narrow_cols)) + "|")
    for r in rows:
        lines.append(
            "| " + " | ".join(_fmt(r.get(c)) for c in narrow_cols) + " |"
        )
    lines.append("")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    replay = _load_replay()
    print(f"[loaded] {len(replay.steps)} replay steps")

    rows: list[dict] = []
    for label, engine in hybrid_configs().items():
        result = _run_one(engine, replay)
        a = _summary(result, ASH)
        p = _summary(result, PEPPER)
        rows.append(
            {
                "label": label,
                "total_pnl": result.total_pnl,
                "pnl_ash": a["pnl"],
                "pnl_pep": p["pnl"],
                # ASH detail
                "ash_trades": a["trade_count"],
                "ash_mkr": a["maker_trades"],
                "ash_tkr": a["taker_trades"],
                "ash_edge": a["avg_entry_edge"],
                "ash_mk20": a["mk20"],
                "ash_b0": a["b0"],
                "ash_b1": a["b1"],
                "ash_b2": a["b2"],
                "ash_b3": a["b3"],
                "ash_final_pos": a["final_pos"],
                "ash_near_limit": a["near_limit"],
                # PEPPER detail
                "pep_trades": p["trade_count"],
                "pep_mkr": p["maker_trades"],
                "pep_tkr": p["taker_trades"],
                "pep_edge": p["avg_entry_edge"],
                "pep_mk20": p["mk20"],
                "pep_b0": p["b0"],
                "pep_b1": p["b1"],
                "pep_b2": p["b2"],
                "pep_b3": p["b3"],
                "pep_final_pos": p["final_pos"],
                "pep_near_limit": p["near_limit"],
                "pep_early25": p["early_25k"],
                "pep_max_short_fh": p["max_short_fh"],
            }
        )
        print(
            f"[run ] {label:<28s} total={result.total_pnl:+9.1f} "
            f"ash={a['pnl']:+8.1f} pep={p['pnl']:+8.1f} "
            f"ash_nl={a['near_limit']:3d} pep_nl={p['near_limit']:4d}"
        )

    emit_csv(ROOT / "hybrid_shortlist.csv", rows)
    emit_md(ROOT / "hybrid_shortlist.md", rows)

    print("\nDone. Outputs:")
    for name in ("hybrid_shortlist.csv", "hybrid_shortlist.md"):
        print(" -", ROOT / name)


if __name__ == "__main__":
    main()
