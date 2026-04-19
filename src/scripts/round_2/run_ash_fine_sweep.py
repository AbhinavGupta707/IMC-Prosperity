"""Fine-grained ASH ladder sweep around the batch-D1 winner.

Batch D1 found `wide_w113` (edges 3/5/8, weights 1:1:3, skew 1.0,
flatten 0.7) as the winner across a 73-candidate coarse grid. Top
4 were all `wide_w113_*`, suggesting a coherent plateau. Official
test data confirmed wide_w113 ASH > L1 ASH within the R2 factory
by +131 per 1k snaps (Welch t=3.08, p~0.02).

This sweep zooms in around wide_w113 along three axes:

1. Edge fine-grain — micro-shifts on the (inner, mid, outer) edges
2. Weight fine-grain — alternative outer-heavy distributions
3. Skew fine-grain — gentler / stronger position skew

Plus a small slice of 4-level ladders to test whether the 3-level
constraint is leaving PnL on the table.

PEPPER held frozen at v5_micro (the deterministic +80k/day annuity).
Runs on the R2 3-day tape (30k snapshots).

Outputs:
- `outputs/round_2/ash_fine_sweep.md`       — ranked candidate table
- `outputs/round_2/ash_fine_sweep_winner.json` — winner LadderParams
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.scripts.round_2._runtime import (
    ASH,
    PEPPER,
    REPO_ROOT,
    V5_MICRO_PEPPER_PARAMS,
    baseline_engine,
    load_round_2_replay,
    per_day_pnl,
    wrap_trader_with_v5micro_l1,
)
from src.strategies.ash_ladder import LadderParams
from src.trader import Trader

OUT_DIR = REPO_ROOT / "outputs" / "round_2"

# Reference: batch-D1 winner.
WIDE_W113 = LadderParams(
    edges=(3.0, 5.0, 8.0),
    size_mults=(1.0, 2.0, 3.0),
    weights=(1, 1, 3),
    skew_coef=1.0,
    flatten_threshold=0.7,
)


def _candidate_grid() -> list[tuple[str, LadderParams]]:
    """Three slices around the wide_w113 winner."""
    candidates: list[tuple[str, LadderParams]] = []

    # Slice 1: 3-level edge fine-grain (16 candidates).
    # Hold weights/skew/flatten at the wide_w113 winner.
    candidates.append(("wide_w113_REF", WIDE_W113))
    edge_variants_3lvl = [
        # Tighter inner
        ("e2.5_5_8",   (2.5, 5.0, 8.0), (1.0, 2.0, 3.0)),
        ("e3_4.5_8",   (3.0, 4.5, 8.0), (1.0, 2.0, 3.0)),
        ("e3_4_8",     (3.0, 4.0, 8.0), (1.0, 2.0, 3.0)),
        # Wider outer
        ("e3_5_9",     (3.0, 5.0, 9.0), (1.0, 2.0, 3.0)),
        ("e3_5_10",    (3.0, 5.0, 10.0), (1.0, 2.0, 3.0)),
        ("e3_5_12",    (3.0, 5.0, 12.0), (1.0, 2.0, 3.0)),
        # Both wider
        ("e3.5_5.5_9", (3.5, 5.5, 9.0), (1.0, 2.0, 3.0)),
        ("e4_6_10",    (4.0, 6.0, 10.0), (1.0, 2.0, 3.0)),
        # Both tighter
        ("e2.5_4_7",   (2.5, 4.0, 7.0), (1.0, 2.0, 3.0)),
        # Larger outer size
        ("e3_5_8_x4",  (3.0, 5.0, 8.0), (1.0, 2.0, 4.0)),
        # Smaller inner size
        ("e3_5_8_x.5", (3.0, 5.0, 8.0), (0.5, 2.0, 3.0)),
        # Symmetric mults
        ("e3_5_8_eq",  (3.0, 5.0, 8.0), (1.0, 1.0, 1.0)),
        # Mid pulled in
        ("e3_4.5_7",   (3.0, 4.5, 7.0), (1.0, 2.0, 3.0)),
        # Mid pushed out
        ("e3_6_9",     (3.0, 6.0, 9.0), (1.0, 2.0, 3.0)),
        # Compress range
        ("e4_5_7",     (4.0, 5.0, 7.0), (1.0, 1.5, 2.0)),
    ]
    for label, edges, mults in edge_variants_3lvl:
        candidates.append(
            (
                f"3lvl_{label}_w113_s1_f0.7",
                LadderParams(
                    edges=edges,
                    size_mults=mults,
                    weights=(1, 1, 3),
                    skew_coef=1.0,
                    flatten_threshold=0.7,
                ),
            )
        )

    # Slice 2: weight + skew + flatten fine-grain at the canonical
    # 3/5/8 wide edges (12 candidates).
    weights_options = [
        ("w112", (1, 1, 2)),
        ("w113", (1, 1, 3)),
        ("w114", (1, 1, 4)),
        ("w213", (2, 1, 3)),
        ("w123", (1, 2, 3)),
        ("w124", (1, 2, 4)),
    ]
    skew_options = [0.5, 1.0]  # 1.5 already covered by D1; gentler region of interest
    flatten_options = [0.7]    # D1 plateau here
    for w_label, weights in weights_options:
        for skew in skew_options:
            for flat in flatten_options:
                label = f"3lvl_e3_5_8_{w_label}_s{skew:g}_f{flat:g}"
                candidates.append(
                    (
                        label,
                        LadderParams(
                            edges=(3.0, 5.0, 8.0),
                            size_mults=(1.0, 2.0, 3.0),
                            weights=weights,
                            skew_coef=skew,
                            flatten_threshold=flat,
                        ),
                    )
                )

    # Slice 3: 4-level ladders (10 candidates) — does adding an inner
    # layer or an extreme outer layer help? Outer-heavy weights again.
    four_level = [
        # Add inner layer at 1.5 below wide_w113's 3
        ("4lvl_e1.5_3_5_8_w1113", (1.5, 3.0, 5.0, 8.0),  (1.0, 1.0, 2.0, 3.0), (1, 1, 1, 3)),
        ("4lvl_e2_3_5_8_w1113",   (2.0, 3.0, 5.0, 8.0),  (1.0, 1.0, 2.0, 3.0), (1, 1, 1, 3)),
        # Add outer layer at 12 (above wide_w113's 8)
        ("4lvl_e3_5_8_12_w1113",  (3.0, 5.0, 8.0, 12.0), (1.0, 2.0, 3.0, 4.0), (1, 1, 1, 3)),
        ("4lvl_e3_5_8_15_w1113",  (3.0, 5.0, 8.0, 15.0), (1.0, 2.0, 3.0, 5.0), (1, 1, 1, 3)),
        # Both ends extended
        ("4lvl_e2_4_6_10_w1113",  (2.0, 4.0, 6.0, 10.0), (1.0, 2.0, 3.0, 4.0), (1, 1, 1, 3)),
        ("4lvl_e2_4_6_10_w1113b", (2.0, 4.0, 6.0, 10.0), (1.0, 1.5, 2.5, 4.0), (1, 1, 1, 3)),
        # Equal weight 4-level
        ("4lvl_e2_4_6_10_eq",     (2.0, 4.0, 6.0, 10.0), (1.0, 1.5, 2.0, 3.0), (1, 1, 1, 1)),
        # Outer-heaviest weight on 12 / 15
        ("4lvl_e3_5_8_12_w1114",  (3.0, 5.0, 8.0, 12.0), (1.0, 2.0, 3.0, 4.0), (1, 1, 1, 4)),
        # Skew variation on a 4-level
        ("4lvl_e2_4_6_10_w1113_s0.5", (2.0, 4.0, 6.0, 10.0), (1.0, 2.0, 3.0, 4.0), (1, 1, 1, 3)),
    ]
    for label, edges, mults, weights in four_level:
        skew = 1.0
        if "s0.5" in label:
            skew = 0.5
        candidates.append(
            (
                f"{label}_s{skew:g}_f0.7",
                LadderParams(
                    edges=edges,
                    size_mults=mults,
                    weights=weights,
                    skew_coef=skew,
                    flatten_threshold=0.7,
                ),
            )
        )

    return candidates


@dataclass(frozen=True)
class CandidateResult:
    label: str
    params: LadderParams
    ash_pnl: float
    pep_pnl: float
    total_pnl: float
    ash_trades: int
    ash_per_day: dict[int, float]
    ash_per_day_sigma: float


def _run_candidate(
    label: str, params: LadderParams, replay: ReplayEngine
) -> CandidateResult:
    config = baseline_engine(flush_pepper=False)
    trader = Trader(config=config)
    wrap_trader_with_v5micro_l1(
        trader, pepper_params=V5_MICRO_PEPPER_PARAMS, ash_params=params
    )
    result = BacktestSimulator(trader=trader).run(replay)
    ash = result.per_product.get(ASH)
    pep = result.per_product.get(PEPPER)
    ash_per_day = per_day_pnl(result, ASH)
    sigma = (
        statistics.stdev(ash_per_day.values()) if len(ash_per_day) >= 2 else 0.0
    )
    return CandidateResult(
        label=label,
        params=params,
        ash_pnl=ash.pnl if ash else 0.0,
        pep_pnl=pep.pnl if pep else 0.0,
        total_pnl=result.total_pnl,
        ash_trades=ash.trade_count if ash else 0,
        ash_per_day=ash_per_day,
        ash_per_day_sigma=sigma,
    )


def _render_report(results: list[CandidateResult]) -> str:
    by_ash = sorted(results, key=lambda r: r.ash_pnl, reverse=True)
    ref = next(r for r in results if r.label == "wide_w113_REF")
    winner = by_ash[0]

    head = (
        "# Round-2 ASH FINE sweep around wide_w113 (D1 winner)\n"
        "\n"
        f"PEPPER frozen at v5_micro. {len(results)} candidates spanning "
        "3-level edge fine-grain (16), weight × skew fine-grain (12), and "
        "4-level ladders (9). Reference row is the D1 winner `wide_w113`.\n"
        "\n"
        f"## Winner: `{winner.label}`\n\n"
        f"- ASH PnL: **+{winner.ash_pnl:.0f}** "
        f"(vs wide_w113 reference +{ref.ash_pnl:.0f}, "
        f"Δ = {winner.ash_pnl - ref.ash_pnl:+.0f})\n"
        f"- ASH trades: {winner.ash_trades} (ref {ref.ash_trades})\n"
        f"- Per-day: " + ", ".join(f"day_{d}={p:+.0f}" for d, p in sorted(winner.ash_per_day.items())) + "\n"
        f"- σ across days: {winner.ash_per_day_sigma:.0f}\n\n"
        "### Winning LadderParams\n\n```python\n"
        f"LadderParams(\n"
        f"    edges={winner.params.edges},\n"
        f"    size_mults={winner.params.size_mults},\n"
        f"    weights={winner.params.weights},\n"
        f"    skew_coef={winner.params.skew_coef},\n"
        f"    flatten_threshold={winner.params.flatten_threshold},\n"
        f")\n```\n\n"
    )

    head += "## Top 15 candidates by ASH PnL\n\n"
    head += (
        "| rank | label | ASH PnL | trades | σ | day_-1 | day_0 | day_1 |\n"
        "|---:|---|---:|---:|---:|---:|---:|---:|\n"
    )
    for i, r in enumerate(by_ash[:15], 1):
        d = r.ash_per_day
        head += (
            f"| {i} | `{r.label}` | {r.ash_pnl:+.0f} | {r.ash_trades} | "
            f"{r.ash_per_day_sigma:.0f} | {d.get(-1, 0):+.0f} | "
            f"{d.get(0, 0):+.0f} | {d.get(1, 0):+.0f} |\n"
        )
    head += "\n## Bottom 5 candidates by ASH PnL\n\n"
    head += (
        "| rank | label | ASH PnL | trades | σ |\n"
        "|---:|---|---:|---:|---:|\n"
    )
    for i, r in enumerate(by_ash[-5:], len(by_ash) - 4):
        head += (
            f"| {i} | `{r.label}` | {r.ash_pnl:+.0f} | {r.ash_trades} | "
            f"{r.ash_per_day_sigma:.0f} |\n"
        )

    head += "\n## Reference\n\n"
    head += (
        f"`wide_w113` (batch-D1 winner): edges {ref.params.edges}, "
        f"weights {ref.params.weights}, skew {ref.params.skew_coef}, "
        f"flatten {ref.params.flatten_threshold}.\n"
        f"ASH PnL +{ref.ash_pnl:.0f}, trades {ref.ash_trades}, "
        f"per-day {dict(sorted(ref.ash_per_day.items()))}, "
        f"σ {ref.ash_per_day_sigma:.0f}.\n\n"
    )

    head += "## Notes\n\n"
    delta = winner.ash_pnl - ref.ash_pnl
    if delta > 500:
        head += (
            f"- **Material uplift available:** +{delta:.0f} ASH PnL over the\n"
            f"  D1 winner. Update production factory to `{winner.label}`.\n"
        )
    elif delta > 100:
        head += (
            f"- **Marginal uplift:** +{delta:.0f} ASH PnL over D1 winner.\n"
            "  Likely within local noise (the D1 plateau was already coherent).\n"
            "  Check if winner sits inside a coherent plateau or is an outlier.\n"
        )
    else:
        head += (
            f"- **No material improvement** over D1 winner (best Δ = +{delta:.0f}).\n"
            "  `wide_w113` was already at or near the local optimum.\n"
        )
    return head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    replay = load_round_2_replay()
    print(f"[loaded] {len(replay.steps)} steps")
    candidates = _candidate_grid()
    print(f"[candidates] {len(candidates)}")

    results: list[CandidateResult] = []
    for i, (label, params) in enumerate(candidates, 1):
        r = _run_candidate(label, params, replay)
        results.append(r)
        print(
            f"[{i:>3d}/{len(candidates)}] {label:<42s} "
            f"ash={r.ash_pnl:>+8.0f} trades={r.ash_trades:>4d} σ={r.ash_per_day_sigma:>5.0f}"
        )

    (args.out_dir / "ash_fine_sweep.md").write_text(_render_report(results))
    winner = max(results, key=lambda r: r.ash_pnl)
    payload = {
        "label": winner.label,
        "ash_pnl": winner.ash_pnl,
        "pep_pnl": winner.pep_pnl,
        "ash_trades": winner.ash_trades,
        "ash_per_day": winner.ash_per_day,
        "ash_per_day_sigma": winner.ash_per_day_sigma,
        "params": {
            "edges": list(winner.params.edges),
            "size_mults": list(winner.params.size_mults),
            "weights": list(winner.params.weights) if winner.params.weights else None,
            "skew_coef": winner.params.skew_coef,
            "flatten_threshold": winner.params.flatten_threshold,
        },
    }
    (args.out_dir / "ash_fine_sweep_winner.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True)
    )
    print(f"[wrote] {(args.out_dir / 'ash_fine_sweep.md').relative_to(REPO_ROOT)}")
    print(f"[winner] {winner.label}: ash={winner.ash_pnl:+.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
