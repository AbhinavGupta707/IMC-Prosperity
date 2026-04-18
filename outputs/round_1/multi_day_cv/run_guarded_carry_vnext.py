"""Targeted PEPPER vNext pass: adaptive caps + tiny micro overlays.

This is intentionally a *small* candidate set built on top of the
best current guarded-carry core:

- `open_take_mode="level1_only"`
- `guard_window=32`
- `guard_negative_slope=0.01`
- `guard_target=0`

Goal: see whether adaptive long-cap tiers and very small
residual/imbalance timing overlays can create more unseen-data edge
without giving up the real-day carry ceiling.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from statistics import mean, pstdev

from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator

from outputs.round_1.multi_day_cv.cv_harness import (
    ASH,
    PEPPER,
    Candidate,
    _PerProductStrategy,
    _research_trader,
    base_engine,
)
from outputs.round_1.multi_day_cv.run_guarded_carry_frontier import (
    STRESS_FOLDS,
    _load_replays,
    _score_row,
)
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.pepper_core_long import CoreLongParams, PepperCoreLongStrategy

OUT_DIR = Path("outputs/round_1/multi_day_cv")
REAL_FOLDS = (-2, -1, 0)

_BASE = CoreLongParams(
    base_long=80,
    add_thresh=3.0,
    trim_thresh=8.0,
    add_gain=5.0,
    trim_gain=2.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style="taker",
    hybrid_threshold=2.0,
    maker_edge_offset=0.0,
    open_seed_size=65,
    open_window=500,
    open_no_short=True,
    open_take_mode="level1_only",
    guard_window=32,
    guard_negative_slope=0.01,
    guard_r2_min=0.0,
    guard_target=0,
)


def _run_candidate(cand: Candidate, replay: ReplayEngine) -> float:
    trader = _research_trader(cand.engine)
    if cand.pepper_params is not None:
        fve, sig = trader.fair_value_engine, trader.signal_engine
        mm = MarketMakingStrategy(fve, sig)
        cl = PepperCoreLongStrategy(fve, sig, cand.pepper_params)
        trader.strategies["market_making"] = _PerProductStrategy({ASH: mm, PEPPER: cl})
    result = BacktestSimulator(trader=trader).run(replay)
    per_product = result.per_product.get(PEPPER)
    return per_product.pnl if per_product is not None else 0.0


def _candidates() -> list[Candidate]:
    configs: list[tuple[str, CoreLongParams, str]] = [
        (
            "V5_guard01_ref",
            _BASE,
            "reference guarded carry: g=0.01, no adaptive caps, no micro overlay",
        ),
        (
            "V5_caps_40_60_80",
            replace(
                _BASE,
                adaptive_caps_enabled=True,
                adaptive_r2_min=0.9,
                adaptive_mid_slope=0.05,
                adaptive_high_slope=0.10,
                adaptive_low_cap=40,
                adaptive_mid_cap=60,
                adaptive_high_cap=80,
            ),
            "adaptive caps: 40/60/80 at slope cutoffs 0.05/0.10",
        ),
        (
            "V5_caps_50_65_80",
            replace(
                _BASE,
                adaptive_caps_enabled=True,
                adaptive_r2_min=0.9,
                adaptive_mid_slope=0.06,
                adaptive_high_slope=0.10,
                adaptive_low_cap=50,
                adaptive_mid_cap=65,
                adaptive_high_cap=80,
            ),
            "gentler adaptive caps: 50/65/80 at slope cutoffs 0.06/0.10",
        ),
        (
            "V5_micro_only",
            replace(
                _BASE,
                micro_residual_threshold=3.0,
                micro_imbalance_threshold=0.30,
                micro_add_size=2,
                micro_trim_size=2,
            ),
            "tiny residual/imbalance timing overlay only",
        ),
        (
            "V5_caps_40_60_80_micro2",
            replace(
                _BASE,
                adaptive_caps_enabled=True,
                adaptive_r2_min=0.9,
                adaptive_mid_slope=0.05,
                adaptive_high_slope=0.10,
                adaptive_low_cap=40,
                adaptive_mid_cap=60,
                adaptive_high_cap=80,
                micro_residual_threshold=3.0,
                micro_imbalance_threshold=0.30,
                micro_add_size=2,
                micro_trim_size=2,
            ),
            "adaptive caps 40/60/80 plus tiny 2-lot micro overlay",
        ),
        (
            "V5_caps_50_65_80_micro1",
            replace(
                _BASE,
                adaptive_caps_enabled=True,
                adaptive_r2_min=0.9,
                adaptive_mid_slope=0.06,
                adaptive_high_slope=0.10,
                adaptive_low_cap=50,
                adaptive_mid_cap=65,
                adaptive_high_cap=80,
                micro_residual_threshold=2.0,
                micro_imbalance_threshold=0.40,
                micro_add_size=1,
                micro_trim_size=1,
            ),
            "gentle adaptive caps plus tiny 1-lot micro overlay",
        ),
    ]
    return [
        Candidate(label=label, engine=base_engine(), pepper_params=params, note=note)
        for label, params, note in configs
    ]


def _evaluate(
    cand: Candidate,
    real_replays: dict[int, ReplayEngine],
    stress_replays: dict[str, ReplayEngine],
) -> dict[str, object]:
    real = {day: _run_candidate(cand, replay) for day, replay in real_replays.items()}
    stress = {label: _run_candidate(cand, replay) for label, replay in stress_replays.items()}
    real_values = [real[day] for day in REAL_FOLDS]
    row: dict[str, object] = {
        "label": cand.label,
        "note": cand.note,
        "day_-2": real[-2],
        "day_-1": real[-1],
        "day_0": real[0],
        "mean_real": mean(real_values),
        "std_real": pstdev(real_values),
    }
    row.update(stress)
    return row


def _emit_csv(path: Path, rows: list[dict[str, object]]) -> None:
    cols = [
        "label",
        "note",
        "mean_real",
        "std_real",
        "day_-2",
        "day_-1",
        "day_0",
        *STRESS_FOLDS,
        "vnext_score",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in cols})


def _emit_md(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# Guarded Carry vNext",
        "",
        "Adaptive-cap and micro-overlay PEPPER candidates on the expanded stress set.",
        "",
        "| label | mean_real | mild_rev | reversed | rev_high_vol | high_vol | stepped | shock | score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['label']} | "
            f"{float(row['mean_real']):.1f} | "
            f"{float(row['mild_reversed']):.1f} | "
            f"{float(row['reversed']):.1f} | "
            f"{float(row['reversed_high_vol']):.1f} | "
            f"{float(row['high_vol']):.1f} | "
            f"{float(row['stepped']):.1f} | "
            f"{float(row['shock_down_recover']):.1f} | "
            f"{float(row['vnext_score']):.1f} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    real_replays, stress_replays = _load_replays()
    rows = [_evaluate(cand, real_replays, stress_replays) for cand in _candidates()]

    ref = next(row for row in rows if row["label"] == "V5_guard01_ref")
    ref_metrics = {
        "mean_real": float(ref["mean_real"]),
        "flat": float(ref["flat"]),
        "reversed": float(ref["reversed"]),
        "high_vol": float(ref["high_vol"]),
        "stepped": float(ref["stepped"]),
        "mild_reversed": float(ref["mild_reversed"]),
        "late_reversed": float(ref["late_reversed"]),
        "reversed_high_vol": float(ref["reversed_high_vol"]),
        "shock_down_recover": float(ref["shock_down_recover"]),
    }
    for row in rows:
        row["vnext_score"] = _score_row(
            {
                "mean_real": float(row["mean_real"]),
                "flat": float(row["flat"]),
                "reversed": float(row["reversed"]),
                "high_vol": float(row["high_vol"]),
                "stepped": float(row["stepped"]),
                "mild_reversed": float(row["mild_reversed"]),
                "late_reversed": float(row["late_reversed"]),
                "reversed_high_vol": float(row["reversed_high_vol"]),
                "shock_down_recover": float(row["shock_down_recover"]),
            },
            ref_metrics,
        )
    rows.sort(key=lambda row: float(row["vnext_score"]), reverse=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "guarded_carry_vnext.csv"
    md_path = OUT_DIR / "guarded_carry_vnext.md"
    _emit_csv(csv_path, rows)
    _emit_md(md_path, rows)
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print("ranking:")
    for row in rows:
        print(
            f"  {row['label']:<24s} "
            f"mean_real={float(row['mean_real']):+9.1f} "
            f"mild_rev={float(row['mild_reversed']):+9.1f} "
            f"rev_hv={float(row['reversed_high_vol']):+9.1f} "
            f"high_vol={float(row['high_vol']):+9.1f} "
            f"shock={float(row['shock_down_recover']):+9.1f} "
            f"score={float(row['vnext_score']):+10.1f}"
        )


if __name__ == "__main__":
    main()
