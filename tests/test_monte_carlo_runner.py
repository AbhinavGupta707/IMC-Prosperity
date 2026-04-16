"""Smoke tests for the run_monte_carlo CLI.

Spawns a tiny MC run from a synthetic activity log and verifies the
output artifacts are produced with expected structure. Heavy distribution
checks live in the stability_metrics tests.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.scripts.calibration.run_monte_carlo import main as mc_main
from tests.test_calibration_runner_integration import (
    _build_synthetic_activity_log,
)


_DUMMY_TRADER_SOURCE = '''
from datamodel import Order, OrderDepth, TradingState


class Trader:
    def run(self, state: TradingState):
        orders = {}
        for product, ob in state.order_depths.items():
            if ob.buy_orders and ob.sell_orders:
                best_bid = max(ob.buy_orders)
                best_ask = min(ob.sell_orders)
                if best_ask - best_bid >= 2:
                    orders[product] = [
                        Order(product, best_bid + 1, 1),
                        Order(product, best_ask - 1, -1),
                    ]
        return orders, 0, ""
'''


def _build_synthetic_trades_csv(path: Path) -> None:
    """Mini trades CSV (only required columns)."""
    rows = [
        ("timestamp", "buyer", "seller", "symbol", "currency", "price", "quantity"),
        ("100", "", "", "EMERALDS", "X", "10001.0", "5"),
        ("500", "", "", "TOMATOES", "X", "5005.0", "3"),
    ]
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerows(rows)


def test_run_monte_carlo_end_to_end_emits_expected_artifacts(tmp_path: Path):
    log_path = tmp_path / "synth_log.json"
    trades_csv = tmp_path / "trades.csv"
    strategy_path = tmp_path / "trader.py"
    out_dir = tmp_path / "mc_out"

    _build_synthetic_activity_log(log_path)
    _build_synthetic_trades_csv(trades_csv)
    strategy_path.write_text(_DUMMY_TRADER_SOURCE)

    rc = mc_main([
        "--strategy", str(strategy_path),
        "--hold1-log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--product", "EMERALDS",
        "--product", "TOMATOES",
        "--n-sessions", "3",
        "--out", str(out_dir),
    ])
    assert rc == 0
    assert (out_dir / "report.md").exists()
    assert (out_dir / "per_session.csv").exists()
    assert (out_dir / "raw_results.json").exists()

    # per_session.csv should have 3 data rows + 1 header.
    with (out_dir / "per_session.csv").open() as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 4

    # report.md should mention the strategy name.
    md = (out_dir / "report.md").read_text()
    assert strategy_path.stem in md

    # raw_results.json should be a list of length 3.
    raw = json.loads((out_dir / "raw_results.json").read_text())
    assert len(raw) == 3
    assert all("seed" in r and "final_pnl" in r for r in raw)


def test_run_monte_carlo_per_session_seeds_are_unique(tmp_path: Path):
    log_path = tmp_path / "synth_log.json"
    trades_csv = tmp_path / "trades.csv"
    strategy_path = tmp_path / "trader.py"
    out_dir = tmp_path / "mc_out"

    _build_synthetic_activity_log(log_path)
    _build_synthetic_trades_csv(trades_csv)
    strategy_path.write_text(_DUMMY_TRADER_SOURCE)

    mc_main([
        "--strategy", str(strategy_path),
        "--hold1-log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--product", "EMERALDS",
        "--n-sessions", "5",
        "--out", str(out_dir),
        "--base-seed", "1000",
    ])
    raw = json.loads((out_dir / "raw_results.json").read_text())
    seeds = [r["seed"] for r in raw]
    assert seeds == [1000, 1001, 1002, 1003, 1004]


def test_fast_mode_runs_20_sessions(tmp_path: Path):
    """--fast flag should run exactly 20 sessions regardless of --n-sessions."""
    log_path = tmp_path / "synth_log.json"
    trades_csv = tmp_path / "trades.csv"
    strategy_path = tmp_path / "trader.py"
    out_dir = tmp_path / "mc_out"

    _build_synthetic_activity_log(log_path)
    _build_synthetic_trades_csv(trades_csv)
    strategy_path.write_text(_DUMMY_TRADER_SOURCE)

    rc = mc_main([
        "--strategy", str(strategy_path),
        "--hold1-log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--product", "EMERALDS",
        "--fast",
        "--out", str(out_dir),
    ])
    assert rc == 0
    raw = json.loads((out_dir / "raw_results.json").read_text())
    assert len(raw) == 20, f"expected 20 fast-mode sessions, got {len(raw)}"


def test_run_monte_carlo_rejects_unknown_product(tmp_path: Path):
    log_path = tmp_path / "synth_log.json"
    trades_csv = tmp_path / "trades.csv"
    strategy_path = tmp_path / "trader.py"
    out_dir = tmp_path / "mc_out"

    _build_synthetic_activity_log(log_path)
    _build_synthetic_trades_csv(trades_csv)
    strategy_path.write_text(_DUMMY_TRADER_SOURCE)

    with pytest.raises(RuntimeError, match="not in hold-1 log"):
        mc_main([
            "--strategy", str(strategy_path),
            "--hold1-log", str(log_path),
            "--trades-csv", str(trades_csv),
            "--product", "NONEXISTENT_PRODUCT",
            "--n-sessions", "1",
            "--out", str(out_dir),
        ])
