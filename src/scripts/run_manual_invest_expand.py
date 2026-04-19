"""Runner for the Invest & Expand manual round (P4-R2).

Produces a full decision packet to stdout and an optional markdown
report. Covers:

1. Candidate generation across a rich v grid.
2. Evaluation under a library of opponent v-priors.
3. Regret / robustness table (sorted by max-regret ascending).
4. Symmetric quantal-response equilibrium (QRE) for reference.
5. Head-to-head against two public team picks (xpablolo 16/50/34,
   rjav1 13/37/50) so we can see whether our analysis converges.

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand \
        --n-opponents 4500 \
        --output outputs/manual_rounds/p4_r2_invest_expand

The ``--n-opponents`` default is 4500, triangulated from the external
research (P4 active-team count + manual-participation rate).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.manual_rounds.invest_expand import (
    Allocation,
    best_allocation_under_prior,
    evaluate,
    expected_mu,
    research,
    scale,
)
from src.manual_rounds.invest_expand_equilibrium import (
    generate_candidate_grid,
    regret_table,
    symmetric_qre,
)
from src.manual_rounds.invest_expand_priors import (
    bimodal_split_vs_zero,
    consensus_cluster,
    leapfrog_adversary,
    mixture,
    naive_ignore_speed,
    naive_thirds,
    nice_number_heavy,
    optimising_at_mu,
    quant_cluster,
    semi_naive_insurance_cluster,
    spike,
    trimodal_naive,
    truncated_geometric,
    uniform,
    VPrior,
)


# ---------------------------------------------------------------------------
# Reference priors (the canonical library we evaluate against)
# ---------------------------------------------------------------------------


def reference_priors() -> dict[str, VPrior]:
    """Library of plausible opponent v-distributions.

    Names deliberately describe the *belief about the field*, not the
    mathematical structure. Adding one here is sufficient to include
    it in the regret table.
    """
    return {
        # Naive heuristic fields
        "all_coast_v0": naive_ignore_speed(),
        "all_thirds_v33": naive_thirds(),
        "all_half_v50": spike(50),
        "nice_numbers": nice_number_heavy(),
        "trimodal_0_33_50": trimodal_naive(0.3, 0.4, 0.3),
        "uniform_0_100": uniform(),
        # Heavier-tailed belief fields
        "geo_mean_15": truncated_geometric(15),
        "geo_mean_30": truncated_geometric(30),
        "geo_mean_45": truncated_geometric(45),
        # Quant-heavy fields (teams optimising given some mu belief)
        "quants_mu_cluster": quant_cluster(
            mu_beliefs=(0.3, 0.5, 0.7, 0.9),
            weights=(0.25, 0.35, 0.25, 0.15),
        ),
        # Field = rjav1's mixture guess (35% sharp, 45% mid anchors, 20% coast)
        "rjav1_blend": mixture(
            [
                (0.20, naive_ignore_speed()),  # 20% coasters at v=0
                (0.15, spike(25)),  # 15% at 25
                (0.20, spike(33)),  # 20% at 33
                (0.15, spike(40)),  # 15% at 40
                (0.15, spike(50)),  # 15% at 50
                (0.10, optimising_at_mu(0.5)),  # 10% quant-optimise mid
                (0.05, uniform(30, 70)),  # 5% high-variance aggressive
            ]
        ),
        # Sharp-optimiser field: most teams run the math
        "sharp_optimiser_field": quant_cluster(
            mu_beliefs=(0.4, 0.5, 0.6, 0.7),
            weights=(0.2, 0.35, 0.3, 0.15),
        ),
        # Speed-race field: a large fraction overspend on v
        "speed_race": mixture(
            [
                (0.1, naive_ignore_speed()),
                (0.2, spike(50)),
                (0.3, spike(60)),
                (0.2, spike(70)),
                (0.2, uniform(60, 90)),
            ]
        ),
        # --- MAF-aware priors (consensus-fragility scenarios) ---
        # Field = MAF-insurance cluster at v=5-10 dominates
        "maf_v5_cluster": semi_naive_insurance_cluster(
            center=5, spread=3, cluster_share=0.45, coast_share=0.15, high_share=0.15
        ),
        # Field = MAF cluster shifted to v=10-15 (slightly more rational naive)
        "maf_v12_cluster": semi_naive_insurance_cluster(
            center=12, spread=5, cluster_share=0.45, coast_share=0.15, high_share=0.15
        ),
        # Realistic MAF-aware blend: 10% coast + 35% MAF + 30% mid-anchors + 15% high + 10% uniform
        "maf_realistic_blend": mixture(
            [
                (0.10, naive_ignore_speed()),
                (0.35, semi_naive_insurance_cluster(
                    center=8, spread=4, cluster_share=1.0, coast_share=0.0, high_share=0.0
                )),
                (0.10, spike(33)),
                (0.15, spike(40)),
                (0.15, spike(50)),
                (0.05, spike(60)),
                (0.10, uniform(0, 100)),
            ]
        ),
        # Leapfrog adversary: what if the field plays exactly v=35 to
        # beat the common v=34 consensus pick?
        "adversary_leapfrog_34": leapfrog_adversary(beat_v=34),
        # Consensus cluster: 60% of field lands at v=40 (a very likely
        # focal point given "sharp optimiser" fraction + level-k L1)
        "cluster_v40_60pct": consensus_cluster(center=40, cluster_share=0.6),
    }


# ---------------------------------------------------------------------------
# Public benchmark allocations for head-to-head comparison
# ---------------------------------------------------------------------------


def public_benchmarks() -> dict[str, Allocation]:
    return {
        "user_seed_23_77_0": Allocation(r=23, s=77, v=0),
        "maf_insurance_22_73_5": Allocation(r=22, s=73, v=5),
        "maf_defensive_21_69_10": Allocation(r=21, s=69, v=10),
        "maf_overshoot_20_60_20": Allocation(r=20, s=60, v=20),
        "maf_fence_sitter_19_56_25": Allocation(r=19, s=56, v=25),
        "tie_thirds_17_50_33": Allocation(r=17, s=50, v=33),
        "xpablolo_minimax_16_50_34": Allocation(r=16, s=50, v=34),
        "xpablolo_alt_16_48_36": Allocation(r=16, s=48, v=36),
        "rjav1_foodio_13_37_50": Allocation(r=13, s=37, v=50),
        "behavioral_14_42_44": Allocation(r=14, s=42, v=44),
        "bayesian_15_45_40": Allocation(r=15, s=45, v=40),
    }


# ---------------------------------------------------------------------------
# Summary formatters
# ---------------------------------------------------------------------------


def _fmt_alloc(a: Allocation) -> str:
    return f"(r={a.r:2d}, s={a.s:2d}, v={a.v:2d})"


def _fmt_money(x: float) -> str:
    return f"{x:>10,.0f}"


def build_report(n_opponents: int) -> dict[str, Any]:
    priors = reference_priors()
    benchmarks = public_benchmarks()

    # Candidate set: every integer v, plus its optimal (r, s) under
    # each of 5 mu beliefs + the public benchmarks themselves.
    auto_cands = generate_candidate_grid(
        v_values=tuple(range(0, 81)),
        priors_for_mu=(0.2, 0.4, 0.5, 0.6, 0.8),
    )
    candidate_pool: list[Allocation] = list(
        {*auto_cands, *benchmarks.values()}
    )

    summaries = regret_table(candidate_pool, priors, n_opponents)
    best_by_regret = summaries[0]
    best_by_mean = max(summaries, key=lambda c: c.mean_pnl)
    best_by_worst = max(summaries, key=lambda c: c.worst.report.net_pnl)

    # Per-prior best (to know what the upper bound is)
    per_prior_best: dict[str, tuple[Allocation, float]] = {}
    for name, p in priors.items():
        rep, _ = best_allocation_under_prior(p, n_opponents)
        per_prior_best[name] = (rep.allocation, rep.net_pnl)

    # Symmetric QRE
    qre = symmetric_qre(n_opponents=n_opponents, temperature=30_000.0, max_iter=300)

    # Benchmark evaluations under the rjav1_blend prior (the most
    # plausible single prior absent empirical data)
    default_prior = priors["rjav1_blend"]
    bench_evals = {
        name: evaluate(alloc, default_prior, n_opponents)
        for name, alloc in benchmarks.items()
    }

    return {
        "n_opponents": n_opponents,
        "priors": list(priors.keys()),
        "per_prior_best": per_prior_best,
        "best_by_regret": best_by_regret,
        "best_by_mean": best_by_mean,
        "best_by_worst": best_by_worst,
        "top5_by_regret": summaries[:5],
        "top5_by_mean": sorted(summaries, key=lambda c: c.mean_pnl, reverse=True)[:5],
        "qre_equilibrium_top5": qre.best_responses,
        "qre_converged": qre.converged,
        "benchmark_under_default_prior": bench_evals,
        "default_prior_name": "rjav1_blend",
    }


def print_human_report(report: dict[str, Any]) -> None:
    print("=" * 78)
    print(f"INVEST & EXPAND — P4-R2 analysis  (n_opponents = {report['n_opponents']})")
    print("=" * 78)

    print("\nPer-prior best (upper bound of each scenario):")
    print(f"  {'prior':<28s}  {'alloc':<18s}  {'net_pnl':>10s}")
    for name, (alloc, pnl) in report["per_prior_best"].items():
        print(f"  {name:<28s}  {_fmt_alloc(alloc):<18s}  {_fmt_money(pnl)}")

    print("\nTop 5 candidates by ASCENDING max regret (most robust first):")
    print(f"  {'alloc':<18s}  {'mean':>10s}  {'worst':>10s}  {'max_regret':>12s}")
    for cs in report["top5_by_regret"]:
        print(
            f"  {_fmt_alloc(cs.allocation):<18s}  "
            f"{_fmt_money(cs.mean_pnl)}  "
            f"{_fmt_money(cs.worst.report.net_pnl)}  "
            f"{_fmt_money(cs.max_regret)}"
        )

    print("\nTop 5 candidates by DESCENDING mean PnL:")
    for cs in report["top5_by_mean"]:
        print(
            f"  {_fmt_alloc(cs.allocation):<18s}  "
            f"{_fmt_money(cs.mean_pnl)}  "
            f"{_fmt_money(cs.worst.report.net_pnl)}  "
            f"{_fmt_money(cs.max_regret)}"
        )

    print(f"\nSymmetric QRE top-5 best-response v: {report['qre_equilibrium_top5']}")
    print(f"QRE converged: {report['qre_converged']}")

    print(f"\nPublic benchmarks under prior '{report['default_prior_name']}':")
    print(f"  {'name':<32s}  {'alloc':<18s}  {'mu_exp':>6s}  {'net_pnl':>10s}")
    for name, ev in report["benchmark_under_default_prior"].items():
        print(
            f"  {name:<32s}  {_fmt_alloc(ev.allocation):<18s}  "
            f"{ev.mu_expected:>6.3f}  {_fmt_money(ev.net_pnl)}"
        )

    print("\nRECOMMENDATION summary:")
    cs = report["best_by_regret"]
    print(f"  Most robust (min max-regret): {_fmt_alloc(cs.allocation)}")
    print(f"      mean PnL = {_fmt_money(cs.mean_pnl)}")
    print(f"      worst PnL = {_fmt_money(cs.worst.report.net_pnl)}  "
          f"on prior '{cs.worst.prior_name}'")
    print(f"      max regret = {_fmt_money(cs.max_regret)}")

    cs2 = report["best_by_mean"]
    print(f"  Highest mean PnL: {_fmt_alloc(cs2.allocation)}")
    print(f"      mean PnL = {_fmt_money(cs2.mean_pnl)}")
    print(f"      worst PnL = {_fmt_money(cs2.worst.report.net_pnl)}  "
          f"on prior '{cs2.worst.prior_name}'")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _json_safe(obj: Any) -> Any:
    """Recursively coerce dataclasses & tuples into JSON-compatible types."""
    from src.manual_rounds.invest_expand_equilibrium import (
        CandidateSummary,
        PriorEval,
    )
    from src.manual_rounds.invest_expand import AllocationReport

    if isinstance(obj, Allocation):
        return {"r": obj.r, "s": obj.s, "v": obj.v}
    if isinstance(obj, AllocationReport):
        return {
            "allocation": _json_safe(obj.allocation),
            "mu_expected": obj.mu_expected,
            "gross": obj.gross,
            "cost": obj.cost,
            "net_pnl": obj.net_pnl,
        }
    if isinstance(obj, PriorEval):
        return {
            "prior_name": obj.prior_name,
            "report": _json_safe(obj.report),
        }
    if isinstance(obj, CandidateSummary):
        return {
            "allocation": _json_safe(obj.allocation),
            "evaluations": [_json_safe(e) for e in obj.evaluations],
            "worst": _json_safe(obj.worst),
            "best": _json_safe(obj.best),
            "mean_pnl": obj.mean_pnl,
            "max_regret": obj.max_regret,
            "regret_by_prior": list(obj.regret_by_prior),
        }
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n-opponents",
        type=int,
        default=4500,
        help="Assumed manual-submission field size minus self (default 4500)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output dir for JSON + markdown artefacts",
    )
    args = parser.parse_args()

    report = build_report(n_opponents=args.n_opponents)
    print_human_report(report)

    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "report.json").write_text(
            json.dumps(_json_safe(report), indent=2)
        )
        print(f"\nWrote JSON report to {args.output}/report.json")


if __name__ == "__main__":
    main()
