"""Diagnostic D3 — Residual Allocator A/B test (F2 hypothesis).

Runs the R2 baseline twice: once with ResidualConfig.enabled=False
(current default), once with enabled=True. Reports per-product and
total P&L delta.

F2 is confirmed a leak if total ΔP&L > 0 and stable.

Usage:
    PYTHONPATH=. .venv/bin/python -m src.scripts.diagnostics.d3_residual_ab
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.backtest.simulator import BacktestSimulator
from src.core.types import ResidualConfig
from src.scripts.round_2._runtime import (
    baseline_engine,
    load_round_2_replay,
    wrap_trader_with_v5micro_l1,
    V5_MICRO_PEPPER_PARAMS,
    L1_ASH_LADDER_PARAMS,
)
from src.trader import Trader

_OUTPUT = Path("outputs/diagnostics/d3_residual_ab.md")


def _run(enabled: bool, residual_edge: float, residual_size: int) -> dict:
    replay = load_round_2_replay()
    config = baseline_engine(flush_pepper=True)
    config = replace(
        config,
        residual_config=ResidualConfig(
            enabled=enabled,
            residual_edge=residual_edge,
            residual_size=residual_size,
        ),
    )
    trader = Trader(config=config)
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

    # Variants to test: baseline (off), and 3 calibration points for edge/size.
    variants = [
        ("baseline (off)", False, 2.0, 2),
        ("enabled edge=2/size=2", True, 2.0, 2),
        ("enabled edge=1/size=2", True, 1.0, 2),
        ("enabled edge=2/size=3", True, 2.0, 3),
        ("enabled edge=3/size=2", True, 3.0, 2),
    ]

    out_lines: list[str] = [
        "# D3 — Residual Allocator A/B Test",
        "",
        "Re-runs R2 baseline with ResidualConfig.enabled=True at multiple "
        "(edge, size) calibrations. F2 is a confirmed leak if any variant "
        "shows stable positive ΔP&L vs baseline.",
        "",
        "| Variant | Total P&L | ΔP&L vs baseline | ASH P&L | PEPPER P&L | Trade count |",
        "|---|---|---|---|---|---|",
    ]

    baseline = None
    for label, enabled, edge, size in variants:
        print(f"running: {label}")
        res = _run(enabled, edge, size)
        if baseline is None:
            baseline = res["total_pnl"]
            delta = 0.0
        else:
            delta = res["total_pnl"] - baseline
        ash = res["per_product"].get("ASH_COATED_OSMIUM", 0.0)
        pep = res["per_product"].get("INTARIAN_PEPPER_ROOT", 0.0)
        out_lines.append(
            f"| {label} | {res['total_pnl']:,.1f} | {delta:+,.1f} | "
            f"{ash:,.1f} | {pep:,.1f} | {res['trades_total']} |"
        )

    out_lines += [
        "",
        "## Interpretation",
        "",
        "- **Any variant ΔP&L > 200 stable across params:** F2 is a confirmed "
        "leak. Flip `ResidualConfig.enabled=True` as default.",
        "- **ΔP&L ≈ 0 or negative:** residual allocator is not a leak on this "
        "product set; may still help on R3+ basket products.",
        "- **Best variant picks the production config:** use the (edge, size) "
        "pair that maximizes ΔP&L.",
    ]

    _OUTPUT.write_text("\n".join(out_lines) + "\n")
    print(f"wrote {_OUTPUT}")


if __name__ == "__main__":
    main()
