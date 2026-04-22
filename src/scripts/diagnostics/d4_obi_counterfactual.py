"""Diagnostic D4 — OBI-skewed fair-value counterfactual (F5 hypothesis).

Registers a new Estimator that adds a predictive OBI skew on top of the
existing weighted_mid: `fair' = weighted_mid + beta * book_imbalance *
spread`. Sweeps beta, re-runs the R2 baseline, reports ASH P&L delta.

If best beta > 0 produces a material ASH P&L lift, F5 is confirmed:
the existing reactive-only FairValueEngine leaves predictive alpha
unexploited, and plugging an OBI predictor into the FV chain captures it.

Usage:
    PYTHONPATH=. .venv/bin/python -m src.scripts.diagnostics.d4_obi_counterfactual
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from src.backtest.simulator import BacktestSimulator
from src.core.config import ProductConfig
from src.core.fair_value import ESTIMATORS, FairValueEngine, WeightedMidEstimator
from src.core.types import FairValueEstimate, NormalizedSnapshot, ProductMemory, Scalar
from src.scripts.round_2._runtime import (
    L1_ASH_LADDER_PARAMS,
    V5_MICRO_PEPPER_PARAMS,
    baseline_engine,
    load_round_2_replay,
    wrap_trader_with_v5micro_l1,
)
from src.trader import Trader

_OUTPUT = Path("outputs/diagnostics/d4_obi_counterfactual.md")


class ObiSkewedWeightedMid:
    """weighted_mid + beta * book_imbalance * spread.

    At beta=0 this exactly reproduces weighted_mid (the existing ASH primary).
    Positive beta tilts fair value toward the thicker side of the book
    proportional to the spread — a cheap linear predictor of next-tick drift.
    """

    def __init__(self, beta: float) -> None:
        self.beta = beta
        self.name = f"obi_weighted_mid_b{beta:+.2f}"
        self._base = WeightedMidEstimator()

    def estimate(
        self,
        snapshot: NormalizedSnapshot,
        memory: ProductMemory,
        config: ProductConfig,
    ) -> FairValueEstimate | None:
        base = self._base.estimate(snapshot, memory, config)
        if base is None:
            return None
        obi = snapshot.book_imbalance
        spread = snapshot.spread
        if obi is None or spread is None:
            return base
        adjusted = base.price + self.beta * obi * spread
        components: Mapping[str, Scalar] = MappingProxyType(
            {"base": float(base.price), "obi": float(obi), "spread": float(spread)}
        )
        return FairValueEstimate(
            price=float(adjusted),
            method=self.name,
            confidence=base.confidence,
            components=components,
        )


def _run_with_beta(beta: float) -> dict:
    replay = load_round_2_replay()
    config = baseline_engine(flush_pepper=True)

    # Replace the *registered* weighted_mid estimator with our OBI-skewed
    # variant (it re-exposes the same .name="weighted_mid"). The existing
    # ProductConfig keeps fair_value_method="weighted_mid"; the behavior
    # changes because the estimator underneath is different.
    class _Override(ObiSkewedWeightedMid):
        def __init__(self, beta: float) -> None:
            super().__init__(beta)
            self.name = "weighted_mid"

    estimator = _Override(beta)
    estimators = dict(ESTIMATORS)
    estimators["weighted_mid"] = estimator

    trader = Trader(config=config)
    # Inject custom FV engine BEFORE wrap_trader_with_v5micro_l1 runs —
    # the wrap function captures trader.fair_value_engine by reference
    # and passes it to AshLadderStrategy/PepperCoreLongStrategy.
    trader.fair_value_engine = FairValueEngine(estimators=estimators)
    wrap_trader_with_v5micro_l1(
        trader,
        pepper_params=V5_MICRO_PEPPER_PARAMS,
        ash_params=L1_ASH_LADDER_PARAMS,
    )
    result = BacktestSimulator(trader=trader).run(replay)
    per_product = {name: r.pnl for name, r in result.per_product.items()}
    return {
        "total_pnl": result.total_pnl,
        "per_product": per_product,
        "trades_total": sum(r.trade_count for r in result.per_product.values()),
    }


def main() -> None:
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Sweep beta. beta=0 = baseline (reproduces weighted_mid).
    # Spread on ASH is typically 16-18 ticks; obi is in [-1, 1].
    # So beta=0.5 shifts fair by up to ±8 ticks — meaningful.
    betas = [-0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 1.0, 2.0]

    out_lines: list[str] = [
        "# D4 — OBI-Skewed Fair-Value Counterfactual",
        "",
        "Adds `beta * book_imbalance * spread` to the existing weighted_mid fair "
        "value for ASH_COATED_OSMIUM. beta=0 reproduces baseline. If best beta "
        "yields a material ASH P&L lift, F5 is confirmed — predictive OBI "
        "signal captures alpha the current reactive FairValueEngine cannot.",
        "",
        "| β | Total P&L | ΔTotal vs β=0 | ASH P&L | ΔASH vs β=0 | PEPPER P&L | Trades |",
        "|---|---|---|---|---|---|---|",
    ]

    baseline_results: dict | None = None
    for beta in betas:
        print(f"running: beta={beta:+.2f}")
        res = _run_with_beta(beta)
        if beta == 0.0:
            baseline_results = res
        total = res["total_pnl"]
        ash = res["per_product"].get("ASH_COATED_OSMIUM", 0.0)
        pep = res["per_product"].get("INTARIAN_PEPPER_ROOT", 0.0)
        if baseline_results is None:
            d_total = 0.0
            d_ash = 0.0
        else:
            d_total = total - baseline_results["total_pnl"]
            d_ash = ash - baseline_results["per_product"].get("ASH_COATED_OSMIUM", 0.0)
        out_lines.append(
            f"| {beta:+.2f} | {total:,.0f} | {d_total:+,.0f} | "
            f"{ash:,.0f} | {d_ash:+,.0f} | {pep:,.0f} | {res['trades_total']} |"
        )

    out_lines += [
        "",
        "## Interpretation",
        "",
        "- **Best β positive with ΔASH > 500:** F5 confirmed. OBI predictor "
        "captures real alpha; build predictive estimator into FairValueEngine.",
        "- **Best β at 0:** F5 not confirmed on ASH; reactive FV is already "
        "near-optimal for this product.",
        "- **Asymmetric response (positive β helps, negative hurts):** confirms "
        "the direction of the causal signal.",
        "- **Symmetric response:** suspicious — may indicate tuning sensitivity "
        "rather than directional edge.",
        "",
        "D1 already showed IC(OBI, 10-tick) = +0.52 on ASH. If D4 also shows a "
        "material positive β, the signal is *both* statistically significant "
        "*and* actionable given the existing execution stack — double confirmation.",
    ]

    _OUTPUT.write_text("\n".join(out_lines) + "\n")
    print(f"wrote {_OUTPUT}")


if __name__ == "__main__":
    main()
