"""Unit tests for ``src.backtest.fair_value_compare``."""

from __future__ import annotations

import pytest

from src.backtest.fair_value_compare import build_fair_value_report, filter_replay_to_product
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.core.config import EngineConfig, ProductConfig


def _row(timestamp: int, product: str, bid: int, ask: int) -> dict[str, str]:
    return {
        "day": "-1",
        "timestamp": str(timestamp),
        "product": product,
        "bid_price_1": str(bid),
        "bid_volume_1": "2",
        "bid_price_2": str(bid - 1),
        "bid_volume_2": "2",
        "bid_price_3": "",
        "bid_volume_3": "",
        "ask_price_1": str(ask),
        "ask_volume_1": "2",
        "ask_price_2": str(ask + 1),
        "ask_volume_2": "2",
        "ask_price_3": "",
        "ask_volume_3": "",
        "mid_price": str((bid + ask) / 2),
        "profit_and_loss": "0.0",
    }


def _replay() -> ReplayEngine:
    return ReplayEngine(
        [
            ReplayStep(
                day=-1,
                timestamp=0,
                rows_by_product={
                    "P": _row(0, "P", 99, 101),
                    "Q": _row(0, "Q", 49, 51),
                },
            ),
            ReplayStep(
                day=-1,
                timestamp=1,
                rows_by_product={
                    "P": _row(1, "P", 101, 103),
                    "Q": _row(1, "Q", 50, 52),
                },
            ),
            ReplayStep(
                day=-1,
                timestamp=2,
                rows_by_product={
                    "P": _row(2, "P", 100, 102),
                    "Q": _row(2, "Q", 51, 53),
                },
            ),
        ]
    )


@pytest.mark.unit
def test_filter_replay_to_product_removes_other_products() -> None:
    filtered = filter_replay_to_product(_replay(), "P")

    assert len(filtered.steps) == 3
    assert all(set(step.rows_by_product) == {"P"} for step in filtered.steps)


@pytest.mark.unit
def test_build_fair_value_report_scores_snapshot_fit() -> None:
    config = EngineConfig(
        products={
            "P": ProductConfig(
                position_limit=20,
                strategy_name="market_making",
                fair_value_method="anchor",
                anchor_price=100.0,
                maker_edge=1.0,
                taker_edge=1.0,
                quote_size=1,
                max_aggressive_size=1,
            )
        }
    )

    report = build_fair_value_report(
        _replay(),
        config=config,
        run_label="unit",
        products=("P",),
        estimator_names=("anchor", "mid", "depth_mid"),
    )

    assert len(report.products) == 1
    product = report.products[0]
    assert product.product == "P"
    assert product.live_method == "anchor"
    assert product.baseline_next_mid_mae == pytest.approx(1.5)

    rows = {row.estimator: row for row in product.comparisons}
    assert rows["mid"].coverage == pytest.approx(1.0)
    assert rows["mid"].current_mid_mae == pytest.approx(0.0)
    assert rows["mid"].next_mid_mae == pytest.approx(1.5)
    assert rows["mid"].next_mid_delta_vs_mid == pytest.approx(0.0)

    assert rows["anchor"].current_mid_mae == pytest.approx(1.0)
    assert rows["anchor"].next_mid_mae == pytest.approx(1.5)

    # Symmetric multi-level book -> depth_mid equals the regular mid here.
    assert rows["depth_mid"].current_mid_mae == pytest.approx(0.0)


@pytest.mark.unit
def test_build_fair_value_report_skips_anchor_without_configured_anchor_price() -> None:
    config = EngineConfig(
        products={
            "P": ProductConfig(
                position_limit=20,
                strategy_name="market_making",
                fair_value_method="weighted_mid",
                maker_edge=1.0,
                taker_edge=1.0,
                quote_size=1,
                max_aggressive_size=1,
            )
        }
    )

    report = build_fair_value_report(
        _replay(),
        config=config,
        run_label="unit",
        products=("P",),
        estimator_names=("anchor", "mid", "weighted_mid"),
    )

    assert len(report.products) == 1
    product = report.products[0]
    assert product.live_method == "weighted_mid"
    assert {row.estimator for row in product.comparisons} == {"mid", "weighted_mid"}
