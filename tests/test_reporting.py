"""Unit tests for ``src.backtest.reporting``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.backtest.metrics import (
    ProductResult,
    SimulationResult,
    TradeRecord,
)
from src.backtest.reporting import build_review_pack, write_review_pack
from src.core.config import EngineConfig, ProductConfig


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
                avg_entry_edge=0.75,
                entry_edge_count=4,
                avg_markout_1=1.2,
                markout_1_count=4,
                avg_markout_5=0.6,
                markout_5_count=4,
                avg_markout_20=None,
                markout_20_count=0,
            )
        },
        trade_records=(
            TradeRecord(
                product="P",
                side="buy",
                price=70.0,
                quantity=1,
                mode="taker",
                decision_timestamp=0,
                fill_timestamp=0,
                fair_value_at_decision=70.5,
                fair_value_method_at_decision="anchor",
                mid_at_decision=70.0,
                mid_at_fill=70.0,
                decision_day=-1,
                fill_day=-1,
            ),
        ),
        mid_series={"P": tuple((ts, 70.0 + 0.1 * ts) for ts in range(10))},
        fair_value_series={"P": tuple((ts, 70.5) for ts in range(10))},
        pnl_series={"P": tuple((ts, float(ts)) for ts in range(10))},
        mid_keys={"P": tuple((-1, ts) for ts in range(10))},
        fair_value_keys={"P": tuple((-1, ts) for ts in range(10))},
        pnl_keys={"P": tuple((-1, ts) for ts in range(10))},
    )


def _engine_config() -> EngineConfig:
    return EngineConfig(
        products={
            "P": ProductConfig(
                position_limit=20,
                strategy_name="market_making",
                fair_value_method="anchor",
                fair_value_fallbacks=("mid", "microprice"),
                anchor_price=70.5,
            )
        }
    )


@pytest.mark.unit
def test_build_review_pack_serializes_per_product_metrics() -> None:
    pack = build_review_pack(_result(), run_label="test")
    assert pack["steps"] == 10
    assert pack["total_pnl"] == 42.0
    assert pack["run_label"] == "test"
    payload = pack["per_product"]["P"]
    assert payload["pnl"] == 42.0
    assert payload["maker_trade_count"] == 3
    assert payload["steps_near_limit"] == 2
    assert payload["avg_entry_edge"] == pytest.approx(0.75)
    assert payload["entry_edge_count"] == 4
    assert payload["avg_markout_1"] == pytest.approx(1.2)
    assert payload["markout_1_count"] == 4
    assert payload["avg_markout_20"] is None
    assert payload["markout_20_count"] == 0


@pytest.mark.unit
def test_write_review_pack_creates_summary_json_and_text(tmp_path: Path) -> None:
    directory = write_review_pack(
        _result(),
        run_label="test_run",
        base_dir=tmp_path,
        git_commit=None,
        git_dirty=None,
    )
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
    directory = write_review_pack(
        _result(),
        run_label="",
        base_dir=tmp_path,
        git_commit=None,
        git_dirty=None,
    )
    assert directory.parent == tmp_path
    assert directory.name.startswith("2")  # ISO-like timestamp starts with year


@pytest.mark.unit
def test_write_review_pack_writes_trades_and_series_unconditionally(tmp_path: Path) -> None:
    directory = write_review_pack(
        _result(),
        run_label="phase4a",
        base_dir=tmp_path,
        git_commit=None,
        git_dirty=None,
    )
    trades_path = directory / "trades.json"
    series_path = directory / "series.json"
    assert trades_path.exists()
    assert series_path.exists()

    trades = json.loads(trades_path.read_text())
    assert len(trades["trades"]) == 1
    trade = trades["trades"][0]
    assert trade["product"] == "P"
    assert trade["side"] == "buy"
    assert trade["decision_day"] == -1
    assert trade["decision_timestamp"] == 0
    assert trade["fill_day"] == -1
    assert trade["fill_timestamp"] == 0
    assert trade["fair_value_at_decision"] == pytest.approx(70.5)

    series = json.loads(series_path.read_text())
    assert "mid_series" in series
    assert "fair_value_series" in series
    assert "pnl_series" in series
    assert "mid_keys" in series
    assert series["mid_keys"]["P"][0] == [-1, 0]
    assert len(series["mid_series"]["P"]) == 10


@pytest.mark.unit
def test_write_review_pack_writes_manifest_with_provenance_fields(tmp_path: Path) -> None:
    directory = write_review_pack(
        _result(),
        run_label="phase4a_manifest",
        base_dir=tmp_path,
        engine_config=_engine_config(),
        data_files=["data/raw/tutorial_round_1/prices_round_0_day_-1.csv"],
        git_commit="abc1234",
        git_dirty=False,
    )
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["run_label"] == "phase4a_manifest"
    assert manifest["git_commit"] == "abc1234"
    assert manifest["git_dirty"] is False
    assert manifest["markout_horizons"] == [1, 5, 20]
    assert manifest["data_files"] == ["data/raw/tutorial_round_1/prices_round_0_day_-1.csv"]
    assert manifest["estimators_per_product"]["P"]["primary"] == "anchor"
    assert manifest["engine_config"]["products"]["P"]["anchor_price"] == 70.5
    # Required artifact keys.
    for key in (
        "summary_json",
        "summary_text",
        "trades_json",
        "series_json",
        "charts_dir",
        "notes_md",
    ):
        assert key in manifest["artifacts"]
    assert manifest["charts_rendered"] is False


@pytest.mark.integration
def test_write_review_pack_renders_charts_and_notes(tmp_path: Path) -> None:
    directory = write_review_pack(
        _result(),
        run_label="phase4a_charts",
        base_dir=tmp_path,
        render_charts=True,
        engine_config=_engine_config(),
        data_files=(),
        git_commit="deadbee",
        git_dirty=True,
    )
    charts_dir = directory / "charts"
    assert charts_dir.exists()

    files = {p.name for p in charts_dir.iterdir()}
    assert "price_vs_fair_P.png" in files
    assert "pnl_over_time_P.png" in files
    assert "position_over_time_P.png" in files
    assert "pnl_over_time_total.png" in files
    # Product P has trades -> maker/taker + markouts should render.
    assert "maker_taker_P.png" in files
    assert "markouts_P.png" in files

    notes = (directory / "notes.md").read_text()
    assert "## Decision" in notes
    assert "## What looked good" in notes
    assert "## What looked bad" in notes
    assert "## Most important chart to inspect" in notes
    assert "## Next change to test" in notes
    assert "deadbee" in notes

    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["charts_rendered"] is True
    assert manifest["git_commit"] == "deadbee"
    assert manifest["git_dirty"] is True
