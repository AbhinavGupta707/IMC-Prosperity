"""Focused multi-scenario sweep for the PEPPER guarded-carry family.

This pass starts from the V3_nearhold PEPPER core and varies only the
new guarded-carry axes:

- guard_window
- guard_negative_slope
- guard_target (with floor matched to the guard target)
- opening take mode

Scoring is relative to the uploaded `V3_nearhold` control. The goal is
not to beat V3 by tiny amounts on the real drift-up tape; it is to find
variants that preserve the real-day ceiling while materially improving
flat / reversed / stepped robustness.

Outputs:

- `outputs/round_1/multi_day_cv/guarded_carry_sweep.csv`
- `outputs/round_1/multi_day_cv/guarded_carry_sweep.md`
"""

from __future__ import annotations

import argparse
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
    buy_hold_control,
    v3_nearhold_control,
)
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.pepper_core_long import CoreLongParams, PepperCoreLongStrategy

OUT_DIR = Path("outputs/round_1/multi_day_cv")
REAL_FOLDS = (-2, -1, 0)
STRESS_FOLDS = ("flat", "reversed", "high_vol", "stepped")
OPEN_TAKE_MODES = ("all_asks", "level1_only")
PRESETS: dict[str, dict[str, tuple[float | int, ...]]] = {
    "focused": {
        "windows": (16, 24, 32),
        "neg_slopes": (0.01, 0.02, 0.05),
        "guard_targets": (0, 20),
    },
    "wide": {
        "windows": (8, 16, 24, 32),
        "neg_slopes": (0.01, 0.02, 0.05, 0.10),
        "guard_targets": (0, 20, 40),
    },
}

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
)


def _stress_replay(label: str) -> ReplayEngine:
    return ReplayEngine.from_files(
        price_paths=[Path("data/raw/round_1_stress") / f"prices_{label}.csv"],
        trade_paths=[DATA / "trades_round_1_day_-2.csv"],
    )


def _load_replays() -> tuple[dict[int, ReplayEngine], dict[str, ReplayEngine]]:
    real = {day: _load_day_replay(day) for day in REAL_FOLDS}
    stress = {name: _stress_replay(name) for name in STRESS_FOLDS}
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


def _fmt_slope(value: float) -> str:
    return f"{value:.2f}".replace(".", "p")


def _candidate_grid(
    *,
    windows: tuple[int, ...],
    neg_slopes: tuple[float, ...],
    guard_targets: tuple[int, ...],
) -> list[Candidate]:
    candidates: list[Candidate] = [buy_hold_control(), v3_nearhold_control()]
    for window in windows:
        for neg_slope in neg_slopes:
            for guard_target in guard_targets:
                for open_take_mode in OPEN_TAKE_MODES:
                    params = replace(
                        _BASE_PARAMS,
                        floor=guard_target,
                        guard_window=window,
                        guard_negative_slope=neg_slope,
                        guard_r2_min=0.0,
                        guard_target=guard_target,
                        open_take_mode=open_take_mode,
                    )
                    mode_tag = "l1" if open_take_mode == "level1_only" else "all"
                    label = (
                        f"GC_w{window:02d}_g{_fmt_slope(neg_slope)}"
                        f"_t{guard_target:02d}_{mode_tag}"
                    )
                    note = (
                        "guarded carry: "
                        f"window={window}, neg_slope={neg_slope:.2f}, "
                        f"guard_target={guard_target}, open_take_mode={open_take_mode}"
                    )
                    candidates.append(
                        Candidate(
                            label=label,
                            engine=base_engine(),
                            pepper_params=params,
                            note=note,
                        )
                    )
    return candidates


def _score_row(row: dict[str, float], v3: dict[str, float]) -> float:
    """Score for robust unseen-data edge, relative to V3."""
    delta_reversed = row["reversed"] - v3["reversed"]
    delta_stepped = row["stepped"] - v3["stepped"]
    delta_flat = row["flat"] - v3["flat"]
    delta_high_vol = row["high_vol"] - v3["high_vol"]
    return (
        row["mean_real"]
        + 0.10 * delta_reversed
        + 0.10 * delta_stepped
        + 0.02 * delta_flat
        + 0.05 * delta_high_vol
    )


def _evaluate(
    cand: Candidate,
    real_replays: dict[int, ReplayEngine],
    stress_replays: dict[str, ReplayEngine],
) -> dict[str, object]:
    real = {day: _run_candidate(cand, replay) for day, replay in real_replays.items()}
    stress = {
        label: _run_candidate(cand, replay) for label, replay in stress_replays.items()
    }
    real_values = [real[day] for day in REAL_FOLDS]
    row: dict[str, object] = {
        "label": cand.label,
        "note": cand.note,
        "day_-2": real[-2],
        "day_-1": real[-1],
        "day_0": real[0],
        "mean_real": mean(real_values),
        "std_real": pstdev(real_values),
        "min_real": min(real_values),
        "max_real": max(real_values),
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
        "flat",
        "reversed",
        "high_vol",
        "stepped",
        "robust_score",
        "delta_vs_v3_real",
        "delta_vs_v3_flat",
        "delta_vs_v3_reversed",
        "delta_vs_v3_high_vol",
        "delta_vs_v3_stepped",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in cols})


def _emit_md(path: Path, rows: list[dict[str, object]], v3: dict[str, float]) -> None:
    top_robust = rows[:10]
    top_real = sorted(rows, key=lambda r: float(r["mean_real"]), reverse=True)[:10]

    def render_table(items: list[dict[str, object]]) -> str:
        lines = [
            "| label | mean_real | std | flat | reversed | high_vol | stepped | robust_score |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in items:
            lines.append(
                "| "
                f"{row['label']} | "
                f"{float(row['mean_real']):.1f} | "
                f"{float(row['std_real']):.1f} | "
                f"{float(row['flat']):.1f} | "
                f"{float(row['reversed']):.1f} | "
                f"{float(row['high_vol']):.1f} | "
                f"{float(row['stepped']):.1f} | "
                f"{float(row['robust_score']):.1f} |"
            )
        return "\n".join(lines)

    best = rows[0]
    body = [
        "# Guarded carry sweep",
        "",
        "Focused PEPPER sweep around the new guarded-carry family.",
        "",
        "## Scoring",
        "",
        "Robust score is:",
        "",
        "```",
        "score = mean_real",
        "      + 0.10 * (reversed - v3_reversed)",
        "      + 0.10 * (stepped  - v3_stepped)",
        "      + 0.02 * (flat     - v3_flat)",
        "      + 0.05 * (high_vol - v3_high_vol)",
        "```",
        "",
        "This intentionally rewards keeping the real-day ceiling while",
        "adding protection on reversal / regime-flip tapes.",
        "",
        "## V3 reference",
        "",
        f"- mean_real: {v3['mean_real']:.1f}",
        f"- flat: {v3['flat']:.1f}",
        f"- reversed: {v3['reversed']:.1f}",
        f"- high_vol: {v3['high_vol']:.1f}",
        f"- stepped: {v3['stepped']:.1f}",
        "",
        "## Best robust candidate",
        "",
        f"- label: `{best['label']}`",
        f"- note: {best['note']}",
        f"- mean_real: {float(best['mean_real']):.1f}",
        f"- reversed: {float(best['reversed']):.1f}",
        f"- high_vol: {float(best['high_vol']):.1f}",
        f"- stepped: {float(best['stepped']):.1f}",
        "",
        "## Top 10 by robust score",
        "",
        render_table(top_robust),
        "",
        "## Top 10 by real-day mean",
        "",
        render_table(top_real),
        "",
    ]
    path.write_text("\n".join(body) + "\n")


def _csv_path(preset: str) -> Path:
    return OUT_DIR / f"guarded_carry_sweep_{preset}.csv"


def _md_path(preset: str) -> Path:
    return OUT_DIR / f"guarded_carry_sweep_{preset}.md"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preset",
        choices=tuple(PRESETS),
        default="focused",
        help="Candidate-grid preset to run",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    preset = PRESETS[args.preset]
    real_replays, stress_replays = _load_replays()
    rows = [
        _evaluate(cand, real_replays, stress_replays)
        for cand in _candidate_grid(
            windows=tuple(int(v) for v in preset["windows"]),
            neg_slopes=tuple(float(v) for v in preset["neg_slopes"]),
            guard_targets=tuple(int(v) for v in preset["guard_targets"]),
        )
    ]

    v3_row = next(row for row in rows if row["label"] == "C_v3_nearhold")
    v3 = {
        "mean_real": float(v3_row["mean_real"]),
        "flat": float(v3_row["flat"]),
        "reversed": float(v3_row["reversed"]),
        "high_vol": float(v3_row["high_vol"]),
        "stepped": float(v3_row["stepped"]),
    }

    for row in rows:
        row["delta_vs_v3_real"] = float(row["mean_real"]) - v3["mean_real"]
        row["delta_vs_v3_flat"] = float(row["flat"]) - v3["flat"]
        row["delta_vs_v3_reversed"] = float(row["reversed"]) - v3["reversed"]
        row["delta_vs_v3_high_vol"] = float(row["high_vol"]) - v3["high_vol"]
        row["delta_vs_v3_stepped"] = float(row["stepped"]) - v3["stepped"]
        row["robust_score"] = _score_row(
            {
                "mean_real": float(row["mean_real"]),
                "flat": float(row["flat"]),
                "reversed": float(row["reversed"]),
                "high_vol": float(row["high_vol"]),
                "stepped": float(row["stepped"]),
            },
            v3,
        )

    rows.sort(key=lambda row: float(row["robust_score"]), reverse=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = _csv_path(args.preset)
    md_path = _md_path(args.preset)
    _emit_csv(csv_path, rows)
    _emit_md(md_path, rows, v3)

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print("top 5:")
    for row in rows[:5]:
        print(
            f"  {row['label']:<22s} "
            f"mean_real={float(row['mean_real']):+9.1f} "
            f"reversed={float(row['reversed']):+9.1f} "
            f"high_vol={float(row['high_vol']):+9.1f} "
            f"stepped={float(row['stepped']):+9.1f} "
            f"score={float(row['robust_score']):+10.1f}"
        )


if __name__ == "__main__":
    main()
