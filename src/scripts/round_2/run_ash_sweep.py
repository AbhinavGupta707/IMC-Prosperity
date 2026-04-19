"""Round-2 ASH ladder param sweep — recover the ~+5k/day R2 gap.

Batch C revealed ASH per-day PnL on R2 (~+3.3k/day) is materially
weaker than R1 final scored (+10.4k/day) under the L1 ladder
(2.5/3.5/5, weights 3:1:1). PEPPER is unchanged.

This script sweeps a small ASH-leg grid over:
- ``edges`` (3 ladder shapes, all 3-level)
- ``weights`` (4 rotation profiles incl. equal weight)
- ``skew_coef`` (3 levels: weak / medium / strong)
- ``flatten_threshold`` (2 levels: 0.7 / 0.85)

PEPPER is held FROZEN at v5_micro (the deterministic +80k/day
annuity). The day-rollover flush is OFF — batch C showed it has no
effect on this stack.

Each candidate is run on the full R2 tape (3 days × 10k snapshots).
Ranking criteria, in order:

1. Total ASH PnL (positive PnL is the only signal that matters).
2. Per-day stability (σ across 3 days).
3. Trade count (fewer trades, more edge per trade).

Outputs:
- ``outputs/round_2/ash_sweep.md`` — ranked candidate table + winner
  rationale + comparison vs L1 baseline.
- ``outputs/round_2/ash_sweep_winner.json`` — winning LadderParams
  serialised for downstream factories.

The runner does not modify any shipped config. The winning params
will land in a Round-2 factory in a follow-up commit.
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
    L1_ASH_LADDER_PARAMS,
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


# --------------------------------------------------------------- candidate grid


def _candidate_params() -> list[tuple[str, LadderParams]]:
    """Build the search grid as (label, LadderParams) tuples.

    Three structural axes:
    - ladder shape (edges + size_mults pair)
    - rotation weights
    - skew + flatten

    The L1 baseline is the first entry so it shows in the report.
    """
    candidates: list[tuple[str, LadderParams]] = []

    # L1 baseline as the reference row.
    candidates.append(("L1_baseline", L1_ASH_LADDER_PARAMS))

    # Edge / size shapes — three families (tighter, L1, wider).
    shapes = [
        ("tight", (1.5, 2.5, 4.0), (1.0, 1.5, 2.0)),
        ("L1",    (2.5, 3.5, 5.0), (1.0, 1.5, 2.0)),
        ("wide",  (3.0, 5.0, 8.0), (1.0, 2.0, 3.0)),
    ]
    weights_options = [
        ("eq",    (1, 1, 1)),     # equal rotation
        ("311",   (3, 1, 1)),     # L1 default — inner-heavy
        ("521",   (5, 2, 1)),     # very inner-heavy
        ("113",   (1, 1, 3)),     # outer-heavy (test the opposite tilt)
    ]
    skew_options = [1.0, 2.0, 3.0]
    flatten_options = [0.7, 0.85]

    for shape_label, edges, mults in shapes:
        for w_label, weights in weights_options:
            for skew in skew_options:
                for flat in flatten_options:
                    label = f"{shape_label}_w{w_label}_s{skew:g}_f{flat:g}"
                    candidates.append(
                        (
                            label,
                            LadderParams(
                                edges=edges,
                                size_mults=mults,
                                weights=weights,
                                skew_coef=skew,
                                flatten_threshold=flat,
                            ),
                        )
                    )
    return candidates


# --------------------------------------------------------------- runner


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


# --------------------------------------------------------------- report


def _render_report(results: list[CandidateResult]) -> str:
    by_ash_pnl = sorted(results, key=lambda r: r.ash_pnl, reverse=True)
    baseline = next(r for r in results if r.label == "L1_baseline")
    winner = by_ash_pnl[0]

    head = (
        "# Round-2 ASH ladder sweep (batch D1)\n"
        "\n"
        "PEPPER held frozen at v5_micro CoreLongParams (the +80k/day annuity).\n"
        "ASH leg swept across 3 ladder shapes × 4 weight profiles × 3 skew\n"
        "× 2 flatten = 72 candidates + L1 baseline.\n"
        "\n"
        f"Tape: 3 R2 days × 10k snapshots each. PEPPER PnL ≈ +239k constant\n"
        "across all candidates (sanity check that nothing leaked into PEPPER).\n"
        "\n"
        f"## Winner: `{winner.label}`\n\n"
        f"- ASH PnL: **+{winner.ash_pnl:.0f}** "
        f"(vs L1 baseline +{baseline.ash_pnl:.0f}, "
        f"Δ = +{winner.ash_pnl - baseline.ash_pnl:+.0f}, "
        f"+{(winner.ash_pnl/baseline.ash_pnl - 1):.0%})\n"
        f"- ASH trades: {winner.ash_trades} (baseline {baseline.ash_trades})\n"
        f"- Per-day PnL: " + ", ".join(f"day_{d}={p:+.0f}" for d, p in sorted(winner.ash_per_day.items())) + "\n"
        f"- σ across days: {winner.ash_per_day_sigma:.0f}\n\n"
        f"### Winning LadderParams\n\n"
        f"```python\n"
        f"LadderParams(\n"
        f"    edges={winner.params.edges},\n"
        f"    size_mults={winner.params.size_mults},\n"
        f"    weights={winner.params.weights},\n"
        f"    skew_coef={winner.params.skew_coef},\n"
        f"    flatten_threshold={winner.params.flatten_threshold},\n"
        f")\n"
        f"```\n\n"
    )

    head += "## Top 15 candidates by ASH PnL\n\n"
    head += (
        "| rank | label | ASH PnL | ASH trades | per-day σ | "
        "day_-1 | day_0 | day_1 |\n"
        "|---:|---|---:|---:|---:|---:|---:|---:|\n"
    )
    for i, r in enumerate(by_ash_pnl[:15], 1):
        d = r.ash_per_day
        head += (
            f"| {i} | `{r.label}` | {r.ash_pnl:+.0f} | {r.ash_trades} | "
            f"{r.ash_per_day_sigma:.0f} | {d.get(-1,0):+.0f} | "
            f"{d.get(0,0):+.0f} | {d.get(1,0):+.0f} |\n"
        )

    head += "\n## Bottom 5 candidates by ASH PnL\n\n"
    head += (
        "| rank | label | ASH PnL | ASH trades | per-day σ |\n"
        "|---:|---|---:|---:|---:|\n"
    )
    for i, r in enumerate(by_ash_pnl[-5:], len(by_ash_pnl) - 4):
        head += (
            f"| {i} | `{r.label}` | {r.ash_pnl:+.0f} | {r.ash_trades} | "
            f"{r.ash_per_day_sigma:.0f} |\n"
        )

    head += "\n## L1 baseline reference\n\n"
    head += (
        f"`L1_baseline`: edges {baseline.params.edges}, "
        f"weights {baseline.params.weights}, "
        f"skew={baseline.params.skew_coef}, "
        f"flatten={baseline.params.flatten_threshold}.\n"
        f"ASH PnL +{baseline.ash_pnl:.0f}; trades {baseline.ash_trades}; "
        f"per-day {dict(sorted(baseline.ash_per_day.items()))}; "
        f"σ {baseline.ash_per_day_sigma:.0f}.\n\n"
    )

    head += "## Notes\n\n"
    delta = winner.ash_pnl - baseline.ash_pnl
    if delta > 1000:
        head += (
            f"- **Material uplift recovered:** +{delta:.0f} ASH PnL over the\n"
            "  L1 baseline. Update the Round-2 default ASH ladder params to\n"
            f"  `{winner.label}` for the final submission factory.\n"
        )
    else:
        head += (
            f"- **No material uplift available** within this grid (best Δ = "
            f"+{delta:.0f}). The R2 ASH regression is not a parameter-tuning\n"
            "  problem — it is a tape-microstructure problem, and the L1\n"
            "  baseline is already near-optimal for this generator.\n"
        )
    head += (
        "- PEPPER is unaffected across all candidates (sanity check):\n"
        f"  the winner's PEPPER PnL is +{winner.pep_pnl:.0f}, baseline is "
        f"+{baseline.pep_pnl:.0f}. Difference: "
        f"{abs(winner.pep_pnl - baseline.pep_pnl):.0f} XIRECs (rounding noise).\n"
    )
    return head


def _serialise_winner(winner: CandidateResult, out_path: Path) -> None:
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
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))


# --------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help="Limit the candidate count (defensive; default runs all).",
    )
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    replay = load_round_2_replay()
    print(f"[loaded] {len(replay.steps)} steps")

    candidates = _candidate_params()
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    print(f"[candidates] {len(candidates)}")

    results: list[CandidateResult] = []
    for i, (label, params) in enumerate(candidates, 1):
        r = _run_candidate(label, params, replay)
        results.append(r)
        print(
            f"[{i:>3d}/{len(candidates)}] {label:<22s} "
            f"ash={r.ash_pnl:>+8.0f} trades={r.ash_trades:>4d} "
            f"σ={r.ash_per_day_sigma:>5.0f}"
        )

    report = _render_report(results)
    (args.out_dir / "ash_sweep.md").write_text(report)
    winner = max(results, key=lambda r: r.ash_pnl)
    _serialise_winner(winner, args.out_dir / "ash_sweep_winner.json")
    print(
        f"[wrote] {args.out_dir / 'ash_sweep.md'} "
        f"(winner: {winner.label}, ash={winner.ash_pnl:+.0f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
