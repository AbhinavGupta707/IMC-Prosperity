"""Round 1 fair-value comparison.

Runs the shared ``build_fair_value_report`` tooling against the two
Round-1 products using a **local, round-1-only** ``EngineConfig``.
This keeps the shared default config (EMERALDS + TOMATOES) untouched
until Phase 3, where Round-1 product configs are promoted.

Outputs land in ``outputs/round_1/fair_value_comparison/<timestamp>_<label>/``.

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.run_round1_fv_compare \
        --label round1_fv_phase1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.fair_value_compare import (
    build_fair_value_report,
    write_fair_value_report,
)
from src.backtest.replay_engine import ReplayEngine
from src.core.config import EngineConfig, ProductConfig

_ROUND1_DATA_DIR = Path("data/raw/round_1")
_ROUND1_REPORT_DIR = Path("outputs/round_1/fair_value_comparison")

# All estimators except anchor (anchor is product-specific and added only
# when the product has an anchor_price set).
_NON_ANCHOR_ESTIMATORS: tuple[str, ...] = (
    "mid",
    "microprice",
    "rolling_mid",
    "weighted_mid",
    "ewma_mid",
    "depth_mid",
    "wall_mid",
    "filtered_wall_mid",
    "hybrid_wall_micro",
)

# Phase-1 placeholder product configs. These are NOT promoted to
# ``default_engine_config()``; they live here only so the fair-value
# compare replay has a reasonable ``ProductConfig`` to run against.
# The promoted Round-1 defaults will be chosen in Phase 3.
_PHASE1_PRODUCT_CONFIGS: dict[str, ProductConfig] = {
    "ASH_COATED_OSMIUM": ProductConfig(
        position_limit=50,
        strategy_name="market_making",
        fair_value_method="anchor",
        fair_value_fallbacks=("microprice", "mid"),
        anchor_price=10_000.0,
        taker_edge=1.0,
        maker_edge=1.0,
        quote_size=5,
        max_aggressive_size=10,
        inventory_skew=2.0,
        flatten_threshold=0.8,
        history_length=48,
    ),
    "INTARIAN_PEPPER_ROOT": ProductConfig(
        position_limit=50,
        strategy_name="market_making",
        fair_value_method="weighted_mid",
        fair_value_fallbacks=("mid", "microprice"),
        taker_edge=1.0,
        maker_edge=1.0,
        quote_size=5,
        max_aggressive_size=10,
        inventory_skew=2.0,
        flatten_threshold=0.8,
        history_length=48,
    ),
}


def _phase1_engine_config() -> EngineConfig:
    return EngineConfig(products=dict(_PHASE1_PRODUCT_CONFIGS))


def _estimators_for(product_config: ProductConfig) -> tuple[str, ...]:
    if product_config.anchor_price is not None:
        return ("anchor",) + _NON_ANCHOR_ESTIMATORS
    return _NON_ANCHOR_ESTIMATORS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="round1_fv_phase1")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_ROUND1_DATA_DIR,
        help="Directory containing prices_round_1_day_*.csv and trades_round_1_day_*.csv",
    )
    parser.add_argument(
        "--products",
        nargs="+",
        default=sorted(_PHASE1_PRODUCT_CONFIGS),
        help="Products to analyse.",
    )
    args = parser.parse_args()

    price_files = sorted(args.data_dir.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(args.data_dir.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {args.data_dir}")

    replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)
    engine_config = _phase1_engine_config()

    # Run per-product so each product gets its own estimator list
    # (anchor only for products that have an anchor_price).
    all_reports = []
    for product in args.products:
        product_config = engine_config.product_config(product)
        if product_config is None:
            print(f"[skip] {product}: no ProductConfig")
            continue
        estimator_names = _estimators_for(product_config)
        report = build_fair_value_report(
            replay,
            config=engine_config,
            run_label=f"{args.label}_{product}",
            products=(product,),
            estimator_names=estimator_names,
        )
        all_reports.append(report)
        directory = write_fair_value_report(report, base_dir=_ROUND1_REPORT_DIR)
        print(f"\n[{product}] report written to {directory}")
        print(report.summary_text())


if __name__ == "__main__":
    main()
