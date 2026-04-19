"""Sensitivity sweeps for Invest & Expand.

- Field-size sensitivity (N from 3000 to 6000)
- QRE sensitivity to rationality temperature
- Benchmark head-to-head across all priors
- Focal-cluster stress test (what if the field concentrates on a
  single round-number v like 50?)

The baseline runner (``run_manual_invest_expand``) produces the
primary recommendation. This runner is for the "am I sure?" audit.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from src.manual_rounds.invest_expand import (
    Allocation,
    best_allocation_under_prior,
    evaluate,
)
from src.manual_rounds.invest_expand_equilibrium import (
    regret_table,
    symmetric_qre,
)
from src.manual_rounds.invest_expand_priors import (
    mixture,
    naive_ignore_speed,
    optimising_at_mu,
    spike,
    trimodal_naive,
    uniform,
)
from src.scripts.run_manual_invest_expand import (
    public_benchmarks,
    reference_priors,
)


def _fmt_alloc(a: Allocation) -> str:
    return f"(r={a.r:2d}, s={a.s:2d}, v={a.v:2d})"


def _fmt_money(x: float) -> str:
    return f"{x:>10,.0f}"


def sweep_field_size() -> None:
    print("\n# FIELD SIZE SENSITIVITY")
    print("Same rjav1_blend prior, varying n_opponents.")
    prior = reference_priors()["rjav1_blend"]
    print(f"\n  {'N':>6s}  {'best_alloc':<18s}  {'mu_exp':>6s}  {'net_pnl':>10s}")
    for n in (2000, 3000, 3500, 4000, 4500, 5000, 5500, 6500):
        rep, _ = best_allocation_under_prior(prior, n_opponents=n)
        print(
            f"  {n:>6d}  {_fmt_alloc(rep.allocation):<18s}  "
            f"{rep.mu_expected:>6.3f}  {_fmt_money(rep.net_pnl)}"
        )


def sweep_qre_temperature() -> None:
    print("\n# QRE TEMPERATURE SENSITIVITY")
    print("As T -> 0, QRE approaches pure NE. As T -> infinity, uniform mixing.")
    print(f"\n  {'T':>10s}  {'top 5 v':<30s}  {'converged':>10s}")
    for t in (2_000, 5_000, 10_000, 30_000, 100_000, 500_000):
        res = symmetric_qre(
            n_opponents=4500, temperature=float(t), max_iter=500, damping=0.2
        )
        top5 = ",".join(str(v) for v in res.best_responses)
        print(f"  {t:>10d}  {top5:<30s}  {res.converged!s:>10s}")


def benchmark_head_to_head() -> None:
    print("\n# PUBLIC BENCHMARKS — HEAD-TO-HEAD ACROSS ALL PRIORS")
    bench = public_benchmarks()
    priors = reference_priors()
    print(f"\n  {'allocation':<18s} ", end="")
    for name in priors:
        print(f"{name[:12]:>12s}", end="")
    print(f"  {'mean':>10s}  {'min':>10s}")

    for bench_name, alloc in bench.items():
        pnls: list[float] = []
        print(f"  {_fmt_alloc(alloc):<18s} ", end="")
        for p in priors.values():
            rep = evaluate(alloc, p, 4500)
            pnls.append(rep.net_pnl)
            print(f"{rep.net_pnl:>12,.0f}", end="")
        print(
            f"  {sum(pnls)/len(pnls):>10,.0f}  {min(pnls):>10,.0f}  "
            f"<-- {bench_name}"
        )


def focal_cluster_stress() -> None:
    print("\n# FOCAL-CLUSTER STRESS")
    print(
        "How do candidates perform if most of the field concentrates on a\n"
        "single round-number v in {0, 33, 40, 45, 50}?"
    )
    bench = public_benchmarks()
    stress = {
        "cluster_v0_80pct": mixture([(0.8, spike(0)), (0.2, uniform(1, 100))]),
        "cluster_v33_60pct": mixture([(0.6, spike(33)), (0.4, uniform(0, 100))]),
        "cluster_v40_60pct": mixture([(0.6, spike(40)), (0.4, uniform(0, 100))]),
        "cluster_v45_50pct": mixture([(0.5, spike(45)), (0.5, uniform(0, 100))]),
        "cluster_v50_60pct": mixture([(0.6, spike(50)), (0.4, uniform(0, 100))]),
        "cluster_v60_40pct": mixture([(0.4, spike(60)), (0.6, uniform(0, 100))]),
    }
    print(f"\n  {'alloc':<18s}", end="")
    for name in stress:
        print(f"{name[:18]:>19s}", end="")
    print()

    for bname, alloc in bench.items():
        print(f"  {_fmt_alloc(alloc):<18s}", end="")
        for p in stress.values():
            rep = evaluate(alloc, p, 4500)
            print(f"{rep.net_pnl:>19,.0f}", end="")
        print(f"  <-- {bname}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    sweep_field_size()
    sweep_qre_temperature()
    benchmark_head_to_head()
    focal_cluster_stress()


if __name__ == "__main__":
    main()
