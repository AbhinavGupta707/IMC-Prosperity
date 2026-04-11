"""Unit tests for ``src.backtest.reporting``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.backtest.metrics import ProductResult, SimulationResult
from src.backtest.reporting import build_review_pack, write_review_pack


def _result() -> SimulationResult:
    return SimulationResult(
        steps=10,
        total_pnl=42.0,
        per_product={
            "P": ProductResult(
                product="P",
                pnl=42.0,
                cash=-100.0,
                final_position=2,
                mark_price=71.0,
                order_count=20,
                trade_count=4,
                taker_trade_count=1,
                maker_trade_count=3,
                taker_trade_quantity=1,
                maker_trade_quantity=3,
                buy_trade_quantity=4,
                sell_trade_quantity=0,
                steps_near_limit=2,
            )
        },
    )


@pytest.mark.unit
def test_build_review_pack_serializes_per_product_metrics() -> None:
    pack = build_review_pack(_result(), run_label="test")
    assert pack["steps"] == 10
    assert pack["total_pnl"] == 42.0
    assert pack["run_label"] == "test"
    assert pack["per_product"]["P"]["pnl"] == 42.0
    assert pack["per_product"]["P"]["maker_trade_count"] == 3
    assert pack["per_product"]["P"]["steps_near_limit"] == 2


@pytest.mark.unit
def test_write_review_pack_creates_summary_json_and_text(tmp_path: Path) -> None:
    directory = write_review_pack(_result(), run_label="test_run", base_dir=tmp_path)
    assert directory.exists()
    summary_json = directory / "summary.json"
    summary_text = directory / "summary.txt"
    assert summary_json.exists()
    assert summary_text.exists()
    payload = json.loads(summary_json.read_text())
    assert payload["total_pnl"] == 42.0
    assert "TOTAL" in summary_text.read_text()


@pytest.mark.unit
def test_write_review_pack_uses_unlabeled_dir_when_label_empty(tmp_path: Path) -> None:
    directory = write_review_pack(_result(), run_label="", base_dir=tmp_path)
    assert directory.parent == tmp_path
    assert directory.name.startswith("2")  # ISO-like timestamp starts with year
