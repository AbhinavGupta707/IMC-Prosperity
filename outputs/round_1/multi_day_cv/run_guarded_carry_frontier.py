"""Tighter PEPPER guarded-carry frontier pass on expanded stress tapes.

This script narrows the search to the current best family only:

- `open_take_mode="level1_only"`
- `guard_target=0`
- `guard_window=32`

It then sweeps only the negative-slope trigger and compares the
frontier across the original 4 PEPPER stress tapes plus 4 extra
regimes aimed at separating "too early", "about right", and
"too late" guard activation.
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
    DATA,
    PEPPER,
    Candidate,
    _PerProductStrategy,
    _load_day_replay,
    _research_trader,
    base_engine,
    v3_nearhold_control,
)
from outputs.round_1.multi_day_cv.stress_tapes import TAPES, make_tape
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.pepper_core_long import CoreLongParams, PepperCoreLongStrategy

OUT_DIR = Path("outputs/round_1/multi_day_cv")
REAL_FOLDS = (-2, -1, 0)
STRESS_FOLDS = (
    "flat",
    "reversed",
    "high_vol",
    "stepped",
    "mild_reversed",
    "late_reversed",
    "reversed_high_vol",
    "shock_down_recover",
)
NEG_SLOPES = (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.10)

_BASE_PARAMS = CoreLongParams(
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
    guard_r2_min=0.0,
    guard_target=0,
)


def _fmt_slope(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", "p")


def _ensure_stress_tapes() -> None:
    for label, fn in TAPES.items():
        path = Path("data/raw/round_1_stress") / f"prices_{label}.csv"
        if not path.exists():
            make_tape(label, fn)


def _stress_replay(label: str) -> ReplayEngine:
    return ReplayEngine.from_files(
        price_paths=[Path("data/raw/round_1_stress") / f"prices_{label}.csv"],
        trade_paths=[DATA / "trades_round_1_day_-2.csv"],
    )


def _load_replays() -> tuple[dict[int, ReplayEngine], dict[str, ReplayEngine]]:
    _ensure_stress_tapes()
    real = {day: _load_day_replay(day) for day in REAL_FOLDS}
    stress = {label: _stress_replay(label) for label in STRESS_FOLDS}
    return real, stress


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
    out = [v3_nearhold_control()]
    out.append(
        Candidate(
            label="GC_l1_noguard",
            engine=base_engine(),
            pepper_params=replace(
                _BASE_PARAMS,
                guard_window=0,
                guard_negative_slope=0.0,
            ),
            note="level1-only opening, no guard",
        )
    )
    for neg_slope in NEG_SLOPES:
        out.append(
            Candidate(
                label=f"GC_w32_g{_fmt_slope(neg_slope)}_t00_l1",
                engine=base_engine(),
                pepper_params=replace(_BASE_PARAMS, guard_negative_slope=neg_slope),
                note=(
                    "frontier: window=32, target=0, open_take_mode=level1_only, "
                    f"neg_slope={neg_slope:.3f}"
                ),
            )
        )
    return out


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


def _score_row(row: dict[str, float], v3: dict[str, float]) -> float:
    """Heuristic score for unseen-data PEPPER robustness."""
    return (
        row["mean_real"]
        + 0.10 * (row["reversed"] - v3["reversed"])
        + 0.08 * (row["mild_reversed"] - v3["mild_reversed"])
        + 0.08 * (row["late_reversed"] - v3["late_reversed"])
        + 0.10 * (row["reversed_high_vol"] - v3["reversed_high_vol"])
        + 0.08 * (row["stepped"] - v3["stepped"])
        + 0.04 * (row["shock_down_recover"] - v3["shock_down_recover"])
        + 0.02 * (row["flat"] - v3["flat"])
        + 0.04 * (row["high_vol"] - v3["high_vol"])
    )


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
        "frontier_score",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in cols})


def _emit_md(path: Path, rows: list[dict[str, object]], v3: dict[str, float]) -> None:
    top = rows[:8]
    lines = [
        "# Guarded carry frontier",
        "",
        "Tight PEPPER frontier around `window=32`, `target=0`, `open_take_mode=level1_only`.",
        "",
        "## Expanded stress set",
        "",
        "- `flat`",
        "- `reversed`",
        "- `high_vol`",
        "- `stepped`",
        "- `mild_reversed`",
        "- `late_reversed`",
        "- `reversed_high_vol`",
        "- `shock_down_recover`",
        "",
        "## V3 reference",
        "",
        f"- mean_real: {v3['mean_real']:.1f}",
        f"- reversed: {v3['reversed']:.1f}",
        f"- mild_reversed: {v3['mild_reversed']:.1f}",
        f"- late_reversed: {v3['late_reversed']:.1f}",
        f"- reversed_high_vol: {v3['reversed_high_vol']:.1f}",
        f"- stepped: {v3['stepped']:.1f}",
        f"- shock_down_recover: {v3['shock_down_recover']:.1f}",
        "",
        "## Top frontier candidates",
        "",
        "| label | mean_real | reversed | mild_rev | late_rev | rev_high_vol | stepped | shock | score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in top:
        lines.append(
            "| "
            f"{row['label']} | "
            f"{float(row['mean_real']):.1f} | "
            f"{float(row['reversed']):.1f} | "
            f"{float(row['mild_reversed']):.1f} | "
            f"{float(row['late_reversed']):.1f} | "
            f"{float(row['reversed_high_vol']):.1f} | "
            f"{float(row['stepped']):.1f} | "
            f"{float(row['shock_down_recover']):.1f} | "
            f"{float(row['frontier_score']):.1f} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    real_replays, stress_replays = _load_replays()
    rows = [_evaluate(cand, real_replays, stress_replays) for cand in _candidates()]

    v3_row = next(row for row in rows if row["label"] == "C_v3_nearhold")
    v3 = {
        "mean_real": float(v3_row["mean_real"]),
        "flat": float(v3_row["flat"]),
        "reversed": float(v3_row["reversed"]),
        "high_vol": float(v3_row["high_vol"]),
        "stepped": float(v3_row["stepped"]),
        "mild_reversed": float(v3_row["mild_reversed"]),
        "late_reversed": float(v3_row["late_reversed"]),
        "reversed_high_vol": float(v3_row["reversed_high_vol"]),
        "shock_down_recover": float(v3_row["shock_down_recover"]),
    }

    for row in rows:
        row["frontier_score"] = _score_row(
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
            v3,
        )

    rows.sort(key=lambda row: float(row["frontier_score"]), reverse=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "guarded_carry_frontier.csv"
    md_path = OUT_DIR / "guarded_carry_frontier.md"
    _emit_csv(csv_path, rows)
    _emit_md(md_path, rows, v3)

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print("top 6:")
    for row in rows[:6]:
        print(
            f"  {row['label']:<20s} "
            f"mean_real={float(row['mean_real']):+9.1f} "
            f"reversed={float(row['reversed']):+9.1f} "
            f"mild_rev={float(row['mild_reversed']):+9.1f} "
            f"late_rev={float(row['late_reversed']):+9.1f} "
            f"rev_hv={float(row['reversed_high_vol']):+9.1f} "
            f"shock={float(row['shock_down_recover']):+9.1f} "
            f"score={float(row['frontier_score']):+10.1f}"
        )


if __name__ == "__main__":
    main()
