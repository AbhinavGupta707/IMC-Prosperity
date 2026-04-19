"""Deep-analytics runner for Invest & Expand.

Four analyses the MAF consensus-fragility warning demanded:

1. MC validation of the closed-form ``E[mu]`` for each plausible v.
2. Level-k iteration from a naive field through best-response chain.
3. Adversarial worst-case prior per published / derived candidate.
4. Phase diagram over (mean_v, std_v) of a truncated-normal field.

Produces a comprehensive decision packet beyond the base regret table.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict

from src.manual_rounds.invest_expand import Allocation
from src.manual_rounds.invest_expand_deep import (
    adversarial_worst_prior,
    field_phase_diagram,
    level_k_iteration,
    monte_carlo_mu,
)
from src.manual_rounds.invest_expand_priors import (
    consensus_cluster,
    mixture,
    naive_ignore_speed,
    naive_thirds,
    optimising_at_mu,
    semi_naive_insurance_cluster,
    spike,
    uniform,
)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _fmt_alloc(a: Allocation) -> str:
    return f"(r={a.r:2d}, s={a.s:2d}, v={a.v:2d})"


def _fmt_money(x: float) -> str:
    return f"{x:>10,.0f}"


# ---------------------------------------------------------------------------
# Analysis blocks
# ---------------------------------------------------------------------------


def run_mc_validation(n_opponents: int) -> None:
    print("\n# MONTE CARLO VALIDATION OF E[mu] CLOSED FORM")
    print("Draws opponent v-samples from each prior, computes realised mu.")
    print("Closed-form should match mc_mean to ~1 / sqrt(n_trials) std error.")
    prior_mixed = mixture(
        [
            (0.15, naive_ignore_speed()),
            (0.40, semi_naive_insurance_cluster(center=5, spread=3)),
            (0.15, spike(33)),
            (0.10, spike(50)),
            (0.20, uniform(0, 100)),
        ]
    )
    print(
        f"\nPrior: MAF-aware blend (15% coast, 40% v=5 cluster, 15% v=33, 10% v=50, 20% uniform)"
    )
    print(f"\n  {'v':>4s}  {'closed_mu':>10s}  {'mc_mean':>10s}  {'mc_std':>8s}  "
          f"{'diff':>8s}")
    for v in (0, 5, 10, 15, 20, 25, 30, 34, 40, 45, 50, 60, 70):
        res = monte_carlo_mu(v, prior_mixed, n_opponents=n_opponents, n_trials=1_500)
        diff = res.mc_mean_mu - res.closed_form_mu
        print(
            f"  {v:>4d}  {res.closed_form_mu:>10.4f}  {res.mc_mean_mu:>10.4f}  "
            f"{res.mc_std_mu:>8.4f}  {diff:>+8.4f}"
        )


def run_level_k(n_opponents: int) -> None:
    print("\n# LEVEL-K ITERATION")
    print("L0 = naive field; L(k) best-responds to L(k-1) treated as a pure spike.")
    print("\nStarting from 'naive_thirds' (all mass at v=33):")
    steps = level_k_iteration(naive_thirds(), n_opponents, depth=8)
    print(f"\n  {'L':>3s}  {'field_mode':>10s}  {'BR_alloc':<18s}  {'mu':>6s}  "
          f"{'pnl':>10s}")
    for step in steps:
        print(
            f"  {step.level:>3d}  {step.field_prior_argmax:>10d}  "
            f"{_fmt_alloc(step.best_response):<18s}  {step.expected_mu:>6.3f}  "
            f"{_fmt_money(step.net_pnl)}"
        )

    print("\nStarting from 'naive_coast' (all mass at v=0):")
    steps = level_k_iteration(naive_ignore_speed(), n_opponents, depth=8)
    print(f"\n  {'L':>3s}  {'field_mode':>10s}  {'BR_alloc':<18s}  {'mu':>6s}  "
          f"{'pnl':>10s}")
    for step in steps:
        print(
            f"  {step.level:>3d}  {step.field_prior_argmax:>10d}  "
            f"{_fmt_alloc(step.best_response):<18s}  {step.expected_mu:>6.3f}  "
            f"{_fmt_money(step.net_pnl)}"
        )

    print("\nStarting from MAF v=5 cluster:")
    steps = level_k_iteration(
        semi_naive_insurance_cluster(center=5, spread=3),
        n_opponents,
        depth=8,
    )
    print(f"\n  {'L':>3s}  {'field_mode':>10s}  {'BR_alloc':<18s}  {'mu':>6s}  "
          f"{'pnl':>10s}")
    for step in steps:
        print(
            f"  {step.level:>3d}  {step.field_prior_argmax:>10d}  "
            f"{_fmt_alloc(step.best_response):<18s}  {step.expected_mu:>6.3f}  "
            f"{_fmt_money(step.net_pnl)}"
        )


def run_adversarial(n_opponents: int) -> None:
    print("\n# ADVERSARIAL WORST-CASE PRIOR")
    print("For each candidate, find the prior (from a broad stress library)")
    print("that minimises its PnL. This is the downside-floor under focal")
    print("clustering / leapfrogging / MAF fragility.")
    candidates = {
        "user_seed_23_77_0": Allocation(r=23, s=77, v=0),
        "maf_insurance_22_73_5": Allocation(r=22, s=73, v=5),
        "semi_aware_21_69_10": Allocation(r=21, s=69, v=10),
        "overshoot_20_64_16": Allocation(r=20, s=64, v=16),
        "tie_33_17_50_33": Allocation(r=17, s=50, v=33),
        "xpablolo_16_50_34": Allocation(r=16, s=50, v=34),
        "bayesian_15_45_40": Allocation(r=15, s=45, v=40),
        "rjav1_foodio_13_37_50": Allocation(r=13, s=37, v=50),
        "aggressive_10_30_60": Allocation(r=10, s=30, v=60),
    }
    print(
        f"\n  {'candidate':<25s}  {'alloc':<18s}  {'worst_prior':<22s}  "
        f"{'worst_pnl':>10s}  {'best_prior':<22s}  {'best_pnl':>10s}"
    )
    for name, alloc in candidates.items():
        res = adversarial_worst_prior(alloc, n_opponents)
        print(
            f"  {name:<25s}  {_fmt_alloc(alloc):<18s}  "
            f"{res.worst_prior_name:<22s}  {_fmt_money(res.worst_pnl)}  "
            f"{res.best_prior_name:<22s}  {_fmt_money(res.best_pnl)}"
        )


def run_phase_diagram(n_opponents: int) -> None:
    print("\n# FIELD PHASE DIAGRAM")
    print("Opponent field = truncated normal on [0, 100] with given")
    print("(mean, std). Best-response v as the field mean/spread shifts.")
    mean_grid = list(range(0, 71, 5))
    std_grid = [5.0, 10.0, 15.0, 20.0, 25.0]
    cells = field_phase_diagram(mean_grid, std_grid, n_opponents=n_opponents)

    # Print as a 2-D table: rows = mean_v, cols = std_v
    print()
    print(f"  {'field_mean':>10s}", end="")
    for s in std_grid:
        print(f"    sigma={s:>4.1f}", end="")
    print()
    for m in mean_grid:
        print(f"  {m:>10.1f}", end="")
        for s in std_grid:
            cell = next(c for c in cells if c.mean_v == m and c.std_v == s)
            print(f"  v={cell.best_v:>2d},pnl={cell.net_pnl/1000:>4.0f}k", end="")
        print()

    print("\nInterpretation:")
    print("  - For each (mean, sigma) guess about the opponent field, the")
    print("    best-response v and resulting PnL (in k XIRECs).")
    print("  - Flat regions in v across neighbouring cells indicate a")
    print("    parameter plateau: that v is robust to mild prior mis-spec.")


def run_main(n_opponents: int) -> None:
    print("=" * 78)
    print("INVEST & EXPAND — DEEP ANALYTICS PACKET")
    print(f"n_opponents = {n_opponents}")
    print("=" * 78)
    run_mc_validation(n_opponents)
    run_level_k(n_opponents)
    run_adversarial(n_opponents)
    run_phase_diagram(n_opponents)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-opponents", type=int, default=4500)
    args = parser.parse_args()
    run_main(args.n_opponents)


if __name__ == "__main__":
    main()
