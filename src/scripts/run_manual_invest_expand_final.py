"""Final decision runner for Invest & Expand.

Incorporates the live Discord poll signal + weighted meta-regret with
explicit subjective probabilities + VoI analysis.

Outputs:
  1. Best response under each Discord-informed prior (and legacy priors).
  2. Weighted meta-regret table using the analyst's subjective weights.
  3. Value of information: expected gain from learning the true prior.
  4. Final recommendation with a dated rationale line.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from src.manual_rounds.invest_expand import (
    Allocation,
    best_allocation_under_prior,
    evaluate,
)
from src.manual_rounds.invest_expand_decision import (
    value_of_information,
    weighted_meta_regret,
)
from src.manual_rounds.invest_expand_priors import (
    VPrior,
    active_submitters_only_blend,
    consensus_cluster,
    discord_poll_discounted_p4r2,
    discord_poll_raw_p4r2,
    discord_realistic_blend_p4r2,
    mixture,
    naive_ignore_speed,
    naive_thirds,
    optimising_at_mu,
    semi_naive_insurance_cluster,
    spike,
    uniform,
)
from src.manual_rounds.invest_expand_equilibrium import generate_candidate_grid


# ---------------------------------------------------------------------------
# The prior library used for the final decision
# ---------------------------------------------------------------------------


def final_prior_library() -> dict[str, VPrior]:
    """Priors the final decision is evaluated against.

    Each prior represents a coherent hypothesis about the field.
    """
    return {
        "discord_poll_raw": discord_poll_raw_p4r2(),
        "discord_poll_mild_discount": discord_poll_discounted_p4r2(0.3),
        "discord_poll_heavy_discount": discord_poll_discounted_p4r2(0.7),
        "discord_blend_35pct_engage": discord_realistic_blend_p4r2(0.35, 0.4),
        "discord_blend_50pct_engage": discord_realistic_blend_p4r2(0.50, 0.4),
        "discord_blend_20pct_engage": discord_realistic_blend_p4r2(0.20, 0.4),
        "rjav1_blend_ensemble": mixture(
            [
                (0.20, naive_ignore_speed()),
                (0.15, spike(25)),
                (0.20, spike(33)),
                (0.15, spike(40)),
                (0.15, spike(50)),
                (0.10, optimising_at_mu(0.5)),
                (0.05, uniform(30, 70)),
            ]
        ),
        "maf_cluster_v5_heavy": mixture(
            [
                (0.40, semi_naive_insurance_cluster(center=5, spread=3, cluster_share=1.0, coast_share=0.0, high_share=0.0)),
                (0.15, naive_ignore_speed()),
                (0.15, spike(33)),
                (0.15, spike(50)),
                (0.15, uniform(0, 100)),
            ]
        ),
        "maf_cluster_v27_meme": mixture(
            [
                (0.30, spike(27)),
                (0.15, naive_ignore_speed()),
                (0.15, spike(33)),
                (0.15, spike(50)),
                (0.10, spike(41)),
                (0.15, uniform(0, 100)),
            ]
        ),
        # Active-submitters-only family: corrects the Discord-poll
        # conflation of R1 non-submitters with R2 deliberate-v=0 teams.
        # Since non-submitters are excluded from the speed rank pool,
        # the true v=0 mass is smaller than the poll suggests.
        "active_submitters_base": active_submitters_only_blend(),
        "active_submitters_mid_heavy": active_submitters_only_blend(
            coaster_share=0.05,
            maf_insurance_share=0.15,
            thirds_share=0.22,
            mid_share=0.25,
            half_share=0.12,
            high_share=0.08,
            extreme_share=0.03,
            uniform_share=0.10,
        ),
        "active_submitters_low_heavy": active_submitters_only_blend(
            coaster_share=0.10,
            maf_insurance_share=0.25,
            thirds_share=0.22,
            mid_share=0.15,
            half_share=0.10,
            high_share=0.05,
            extreme_share=0.03,
            uniform_share=0.10,
        ),
        "all_thirds_schelling": naive_thirds(),
        "all_half_schelling": spike(50),
        "all_coast": naive_ignore_speed(),
        "uniform_flat": uniform(),
    }


# ---------------------------------------------------------------------------
# Subjective belief weights: how likely each prior is to be reality
# ---------------------------------------------------------------------------


def default_subjective_weights() -> dict[str, float]:
    """Hand-calibrated subjective probability distribution over priors.

    Rationale, dated 2026-04-19 after integrating the Discord signal:
      - Discord-informed blends carry the most weight (~55% cumulative)
        because they are the most empirically grounded, but each
        individual blend has modest weight because engagement
        fraction is uncertain.
      - rjav1 ensemble blend carries ~15% (rjav1 has lived access to
        R1 leaderboard data, but their prior predates the Discord poll).
      - MAF-cluster and focal-cluster priors each carry 5-7% to keep
        the downside modeled but not dominant.
      - Pure Schelling priors (all-thirds, all-half, all-coast) carry
        very little weight individually -- they are worst-case rather
        than most-likely.
      - Uniform_flat is the "I know nothing" baseline: 5%.
    """
    # v3 (post-critical-review):
    # - Discord down-weighted to 25% cumulative (reference, not truth;
    #   self-selected sample, spite/lying inflates tails, 17%-at-v=0
    #   was conflated with R1-non-submitter stat).
    # - Active-submitters-only family added at 40% (primary belief
    #   about the rank pool after excluding non-submitters).
    # - Other weights unchanged.
    # weighted_meta_regret normalises internally; exact sum-to-1 optional.
    return {
        # Discord family: 25% (reference, not truth)
        "discord_poll_raw": 0.02,
        "discord_poll_mild_discount": 0.05,
        "discord_poll_heavy_discount": 0.03,
        "discord_blend_35pct_engage": 0.08,
        "discord_blend_50pct_engage": 0.04,
        "discord_blend_20pct_engage": 0.03,
        # Active-submitters-only family: 40% (primary belief)
        "active_submitters_base": 0.20,
        "active_submitters_mid_heavy": 0.14,
        "active_submitters_low_heavy": 0.06,
        # Legacy pre-Discord ensemble: 10%
        "rjav1_blend_ensemble": 0.10,
        # Focal-cluster / MAF: 9%
        "maf_cluster_v5_heavy": 0.04,
        "maf_cluster_v27_meme": 0.05,
        # Edge / Schelling worst-cases: 11%
        "all_thirds_schelling": 0.03,
        "all_half_schelling": 0.02,
        "all_coast": 0.03,
        "uniform_flat": 0.03,
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _fmt_alloc(a: Allocation) -> str:
    return f"(r={a.r:2d}, s={a.s:2d}, v={a.v:2d})"


def _fmt_money(x: float) -> str:
    return f"{x:>10,.0f}"


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def show_per_prior_best(priors: dict[str, VPrior], n_opp: int) -> None:
    print("\n# PER-PRIOR BEST RESPONSE")
    print(f"  {'prior':<34s}  {'alloc':<18s}  {'mu':>5s}  {'net_pnl':>10s}")
    for name, prior in priors.items():
        rep, _ = best_allocation_under_prior(prior, n_opp)
        print(
            f"  {name:<34s}  {_fmt_alloc(rep.allocation):<18s}  "
            f"{rep.mu_expected:>5.2f}  {_fmt_money(rep.net_pnl)}"
        )


def show_weighted_meta_regret(
    priors: dict[str, VPrior],
    weights: dict[str, float],
    n_opp: int,
) -> list[Allocation]:
    print("\n# WEIGHTED META-REGRET (top 10 by weighted E[PnL])")
    print("Subjective weights over priors applied below:")
    for name, w in weights.items():
        print(f"  P({name:<38s}) = {w:>.3f}")

    # Candidate pool: every integer v 0..80 with its optimal (r, s) under
    # several mu beliefs, plus a few published picks.
    pool = set(generate_candidate_grid(
        v_values=tuple(range(0, 71)),
        priors_for_mu=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7),
    ))
    pool.update([
        Allocation(r=23, s=77, v=0),
        Allocation(r=22, s=73, v=5),
        Allocation(r=21, s=67, v=12),
        Allocation(r=19, s=54, v=27),  # Discord-meme-tie (FOC best at v=27)
        Allocation(r=18, s=52, v=30),  # leapfrog v=27 by 3
        Allocation(r=17, s=50, v=33),
        Allocation(r=16, s=50, v=34),
        Allocation(r=16, s=48, v=36),
        Allocation(r=15, s=45, v=40),
        Allocation(r=13, s=37, v=50),
        Allocation(r=8, s=22, v=70),
        Allocation(r=3, s=7, v=90),
    ])

    rows = weighted_meta_regret(
        candidates=list(pool),
        priors=priors,
        weights=weights,
        n_opponents=n_opp,
    )
    print(f"\n  {'alloc':<18s}  {'E[PnL]':>10s}  {'worst':>10s}  "
          f"{'worst_prior':<28s}  {'best_prior':<28s}")
    for r in rows[:15]:
        print(
            f"  {_fmt_alloc(r.allocation):<18s}  "
            f"{_fmt_money(r.weighted_mean_pnl)}  "
            f"{_fmt_money(r.worst_prior_pnl)}  "
            f"{r.worst_prior:<28s}  {r.best_prior:<28s}"
        )
    return [r.allocation for r in rows[:3]]


def show_voi(
    committed: Allocation,
    priors: dict[str, VPrior],
    weights: dict[str, float],
    n_opp: int,
) -> None:
    print(f"\n# VALUE OF INFORMATION   committed = {_fmt_alloc(committed)}")
    voi = value_of_information(committed, priors, weights, n_opp)
    print(f"Expected VoI (regret vs. perfect info): {_fmt_money(voi.expected_voi)}")
    print(
        "Interpretation: learning the true prior would, in expectation,"
        f" improve PnL by ~{voi.expected_voi:,.0f} XIREC."
    )
    print(
        "\nBreakdown per possible revelation (what we gain from knowing"
        " each prior is the truth):"
    )
    print(
        f"  {'revealed_prior':<36s}  {'w':>5s}  {'committed_pnl':>12s}  "
        f"{'optimal_alloc':<18s}  {'optimal_pnl':>12s}  {'marg_gain':>10s}"
    )
    for row in voi.rows:
        print(
            f"  {row.revealed_prior:<36s}  {row.weight:>5.3f}  "
            f"{_fmt_money(row.committed_pick_pnl)}  "
            f"{_fmt_alloc(row.best_pick_allocation):<18s}  "
            f"{_fmt_money(row.best_pick_pnl)}  "
            f"{_fmt_money(row.voi_marginal)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-opponents", type=int, default=4500)
    args = parser.parse_args()

    print("=" * 78)
    print("INVEST & EXPAND — FINAL DECISION RUNNER")
    print(f"n_opponents = {args.n_opponents}   (per Discord chatter: ~5000 active)")
    print("=" * 78)

    priors = final_prior_library()
    weights = default_subjective_weights()

    show_per_prior_best(priors, args.n_opponents)
    top3 = show_weighted_meta_regret(priors, weights, args.n_opponents)

    for pick in top3:
        show_voi(pick, priors, weights, args.n_opponents)


if __name__ == "__main__":
    main()
