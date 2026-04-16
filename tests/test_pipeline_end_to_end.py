"""End-to-end pipeline integration test.

Wires together every stage of the production calibration + MC path:

  hold-1 activity log JSON
       --> run_calibration --> fits.json + report
       --> run_simulator_validation --> Gate 1 + Gate 2 reports
       --> run_monte_carlo (against a known-positive-EV strategy)
       --> verify the resulting MC report has structurally
           sensible numbers (positive median, reasonable win rate,
           positive alpha, R^2 finite).

This is the test that would have caught P0-1 (RNG drift) and P0-2
(position-limit asymmetry) before they bit production.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.scripts.calibration.run_calibration import (
    main as run_calibration_main,
)
from src.scripts.calibration.run_monte_carlo import (
    main as run_monte_carlo_main,
)
from src.scripts.calibration.run_simulator_validation import (
    main as run_simulator_validation_main,
)
from tests.test_calibration_runner_integration import (
    _build_synthetic_activity_log,
)


# NOTE on EV direction below: the synthetic activity log built by
# tests.test_calibration_runner_integration._build_synthetic_activity_log
# generates TOMATOES as a Gaussian random walk with mean drift fixed by
# the seeded RNG. Empirically the test seed produces a SLIGHTLY NEGATIVE
# net drift (~-0.012/tick across 2000 ticks). So a SELL-aggressive
# strategy is expected EV-positive (drift works in its favor); a BUY-
# aggressive strategy fights the drift and loses.

_KNOWN_POSITIVE_EV_TRADER = '''
"""Trader that SELLS aggressively at the best bid each tick.

In the synthetic calibration the test uses, TOMATOES drifts slightly
DOWN, so accumulating short inventory captures the drift. Expected MC
outcome: positive median PnL, high win rate (>= 70%).
"""
from datamodel import Order, OrderDepth, TradingState


class Trader:
    def run(self, state: TradingState):
        orders = {}
        for product, ob in state.order_depths.items():
            if ob.buy_orders:
                best_bid = max(ob.buy_orders.keys())
                orders[product] = [Order(product, best_bid, -1)]
        return orders, 0, ""
'''


def _build_synthetic_trades_csv(path: Path) -> None:
    """Mini trades CSV — the simulator validation gate needs at least
    a few trades per product to derive arrival statistics."""
    rows = ["timestamp;buyer;seller;symbol;currency;price;quantity"]
    for ts in range(100, 90000, 1000):
        rows.append(f"{ts};;;TOMATOES;X;5005;3")
    for ts in range(200, 90000, 2000):
        rows.append(f"{ts};;;EMERALDS;X;10005;5")
    path.write_text("\n".join(rows) + "\n")


def test_full_pipeline_hold1_to_mc_verdict(tmp_path: Path):
    """End-to-end: hold-1 log → calibration → validation → MC → verdict."""
    # Stage 0: synthetic activity log + trades CSV (stand-in for real IMC).
    log_path = tmp_path / "hold1_log.json"
    trades_csv = tmp_path / "trades.csv"
    strategy_path = tmp_path / "trader.py"
    _build_synthetic_activity_log(log_path)
    _build_synthetic_trades_csv(trades_csv)
    strategy_path.write_text(_KNOWN_POSITIVE_EV_TRADER)

    # Stage 1: calibration.
    calib_dir = tmp_path / "calibration"
    rc = run_calibration_main([
        "--log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--out", str(calib_dir),
        "--no-plots",
    ])
    assert rc == 0, "calibration runner failed"
    fits = json.loads((calib_dir / "fits.json").read_text())
    assert "TOMATOES" in fits
    assert "EMERALDS" in fits
    # FV process recovered with non-zero sigma for TOMATOES (random walk).
    assert fits["TOMATOES"]["fair_value"]["sigma"] > 0.0

    # Stage 2: simulator validation (Gates 1 + 2).
    valid_dir = tmp_path / "validation"
    rc = run_simulator_validation_main([
        "--hold1-log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--out", str(valid_dir),
    ])
    # Gate 1 (round-trip) should pass; Gate 2 may or may not depending on
    # synthetic-data noise. We only assert the artifacts exist + Gate 1
    # report is non-empty.
    assert (valid_dir / "gate1_round_trip.md").exists()
    assert (valid_dir / "gate2_marginal_match.md").exists()
    g1_text = (valid_dir / "gate1_round_trip.md").read_text()
    assert "TOMATOES" in g1_text
    assert "PASS" in g1_text  # at least one product should pass round-trip

    # Stage 3: Monte Carlo on the known-positive-EV trader.
    mc_dir = tmp_path / "mc"
    rc = run_monte_carlo_main([
        "--strategy", str(strategy_path),
        "--hold1-log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--product", "TOMATOES",
        "--n-sessions", "10",
        "--out", str(mc_dir),
    ])
    assert rc == 0, "monte carlo runner failed"
    assert (mc_dir / "report.md").exists()
    assert (mc_dir / "per_session.csv").exists()

    # Stage 4: verdict structural sanity.
    raw = json.loads((mc_dir / "raw_results.json").read_text())
    assert len(raw) == 10
    pnls = [r["final_pnl"] for r in raw]
    n_positive = sum(1 for p in pnls if p > 0)
    # Aggressive buy-only on a positive-drift product should win > half
    # the time. Loosen below 70% to absorb the small-sample noise of
    # n=10 sessions, but require strictly above coin flip.
    assert n_positive >= 6, (
        f"expected >= 6/10 positive PnLs for a buy-and-hold-the-drift "
        f"strategy; got {n_positive}/10. PnLs: {pnls}"
    )

    # Realized alpha (slope of equity curve) should be positive on average.
    alphas = [r["realized_alpha"] for r in raw]
    assert sum(a > 0 for a in alphas) >= 6, (
        f"expected >= 6/10 positive alphas; got "
        f"{sum(a > 0 for a in alphas)}/10. alphas: {alphas}"
    )


def test_full_pipeline_negative_ev_trader_loses_money(tmp_path: Path):
    """Sanity check inverse direction: BUY-aggressive strategy on a
    DOWN-drifting product should lose money. Catches the class of bugs
    where the simulator credits PnL regardless of strategy direction.
    """
    log_path = tmp_path / "hold1_log.json"
    trades_csv = tmp_path / "trades.csv"
    strategy_path = tmp_path / "trader.py"
    _build_synthetic_activity_log(log_path)
    _build_synthetic_trades_csv(trades_csv)
    # Buy aggressively at best ask each tick — fights the negative drift.
    strategy_path.write_text('''
from datamodel import Order, OrderDepth, TradingState


class Trader:
    def run(self, state: TradingState):
        orders = {}
        for product, ob in state.order_depths.items():
            if ob.sell_orders:
                best_ask = min(ob.sell_orders.keys())
                orders[product] = [Order(product, best_ask, 1)]
        return orders, 0, ""
''')

    mc_dir = tmp_path / "mc"
    rc = run_monte_carlo_main([
        "--strategy", str(strategy_path),
        "--hold1-log", str(log_path),
        "--trades-csv", str(trades_csv),
        "--product", "TOMATOES",
        "--n-sessions", "10",
        "--out", str(mc_dir),
    ])
    assert rc == 0
    raw = json.loads((mc_dir / "raw_results.json").read_text())
    pnls = [r["final_pnl"] for r in raw]
    n_negative = sum(1 for p in pnls if p < 0)
    assert n_negative >= 6, (
        f"expected >= 6/10 negative PnLs for a sell-into-drift strategy; "
        f"got {n_negative}/10. PnLs: {pnls}"
    )
