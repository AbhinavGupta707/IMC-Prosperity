"""Round 1 minimum-viable end-to-end backtest.

Runs the full ``Trader`` against Round-1 replay data and prints per-
product metrics. This is the Phase-3 sanity check: it verifies that
the engine wires up both new products end-to-end (market data →
strategy → execution → risk → memory) with the new ``linear_drift``
estimator and the registered default configs.

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.run_round1_backtest

Writes a compact JSON summary to ``outputs/round_1/backtests/``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.fair_value_compare import filter_replay_to_product
from src.backtest.replay_engine import ReplayEngine
from src.backtest.simulator import BacktestSimulator
from src.core.config import ROUND1_PRODUCTS, round1_engine_config
from src.trader import Trader

_ROUND1_DATA_DIR = Path("data/raw/round_1")
_ROUND1_BACKTEST_DIR = Path("outputs/round_1/backtests")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="round1_mvb")
    parser.add_argument("--data-dir", type=Path, default=_ROUND1_DATA_DIR)
    args = parser.parse_args()

    price_files = sorted(args.data_dir.glob("prices_round_1_day_*.csv"))
    trade_files = sorted(args.data_dir.glob("trades_round_1_day_*.csv"))
    if not price_files:
        raise SystemExit(f"No price files in {args.data_dir}")

    # Round-1-only config: keeps tutorial products (EMERALDS, TOMATOES)
    # out of the replay even if they ever share the same data directory.
    config = round1_engine_config()

    # We still want a per-product breakdown per day. Easiest is to run
    # the combined replay once, then one per-product replay too.
    full_replay = ReplayEngine.from_files(price_paths=price_files, trade_paths=trade_files)
    trader = Trader(config=config)
    simulator = BacktestSimulator(trader=trader)
    full_result = simulator.run(full_replay)

    combined_summary: dict[str, dict] = {}
    for product in ROUND1_PRODUCTS:
        pr = full_result.per_product.get(product)
        if pr is None:
            combined_summary[product] = {"present": False}
            continue
        combined_summary[product] = {
            "present": True,
            "pnl": pr.pnl,
            "trades": pr.trade_count,
            "maker_trades": pr.maker_trade_count,
            "taker_trades": pr.taker_trade_count,
            "maker_qty": pr.maker_trade_quantity,
            "taker_qty": pr.taker_trade_quantity,
            "final_position": pr.final_position,
            "steps_near_limit": pr.steps_near_limit,
            "avg_entry_edge": pr.avg_entry_edge,
            "avg_markout_1": pr.avg_markout_1,
            "avg_markout_5": pr.avg_markout_5,
            "avg_markout_20": pr.avg_markout_20,
        }

    # Per-day metrics (one simulator per day for cleanliness)
    per_day: dict[str, dict[int, dict]] = {p: {} for p in ROUND1_PRODUCTS}
    for day in sorted({step.day for step in full_replay.steps}):
        day_price_files = [p for p in price_files if f"day_{day}." in p.name or f"day_{day}_" in p.name]
        day_trade_files = [t for t in trade_files if f"day_{day}." in t.name or f"day_{day}_" in t.name]
        if not day_price_files:
            continue
        day_replay = ReplayEngine.from_files(
            price_paths=day_price_files, trade_paths=day_trade_files
        )
        day_trader = Trader(config=config)
        day_sim = BacktestSimulator(trader=day_trader)
        day_result = day_sim.run(day_replay)
        for product in ROUND1_PRODUCTS:
            pr = day_result.per_product.get(product)
            if pr is None:
                continue
            per_day[product][day] = {
                "pnl": pr.pnl,
                "trades": pr.trade_count,
                "maker_qty": pr.maker_trade_quantity,
                "taker_qty": pr.taker_trade_quantity,
                "final_position": pr.final_position,
                "steps_near_limit": pr.steps_near_limit,
                "avg_entry_edge": pr.avg_entry_edge,
                "avg_markout_1": pr.avg_markout_1,
                "avg_markout_5": pr.avg_markout_5,
                "avg_markout_20": pr.avg_markout_20,
            }

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = _ROUND1_BACKTEST_DIR / f"{stamp}_{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_dir": str(args.data_dir),
        "config_source": "round1_engine_config()",
        "products": list(ROUND1_PRODUCTS),
        "combined": combined_summary,
        "per_day": per_day,
        "product_configs": {
            p: asdict(config.product_config(p)) for p in ROUND1_PRODUCTS if config.product_config(p) is not None
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))

    # Human-readable summary
    lines = [
        f"Round 1 minimum-viable backtest | label={args.label}",
        f"data_dir={args.data_dir}",
        "",
        "Combined (all days)",
        f"  total PnL (entire config): {full_result.total_pnl:.2f}",
        f"  steps: {full_result.steps}",
        "",
    ]
    lines.append(f"{'product':<22} {'pnl':>10} {'trades':>7} {'mk_q':>6} {'tk_q':>6} {'pos':>5} {'near':>6} {'edge':>8} {'mk_1':>8} {'mk_5':>8} {'mk_20':>8}")
    lines.append("-" * 105)
    for product, blk in combined_summary.items():
        if not blk.get("present"):
            lines.append(f"{product:<22} (no data)")
            continue
        e = blk.get("avg_entry_edge")
        m1 = blk.get("avg_markout_1")
        m5 = blk.get("avg_markout_5")
        m20 = blk.get("avg_markout_20")
        lines.append(
            f"{product:<22} {blk['pnl']:>10.0f} {blk['trades']:>7} "
            f"{blk['maker_qty']:>6} {blk['taker_qty']:>6} "
            f"{blk['final_position']:>5} {blk['steps_near_limit']:>6} "
            f"{(f'{e:+.3f}' if e is not None else 'n/a'):>8} "
            f"{(f'{m1:+.3f}' if m1 is not None else 'n/a'):>8} "
            f"{(f'{m5:+.3f}' if m5 is not None else 'n/a'):>8} "
            f"{(f'{m20:+.3f}' if m20 is not None else 'n/a'):>8}"
        )
    lines.append("")
    for product in ROUND1_PRODUCTS:
        if not per_day.get(product):
            continue
        lines.append(f"{product} per-day")
        lines.append(f"  {'day':>4} {'pnl':>10} {'trades':>7} {'pos':>5} {'near':>6} {'edge':>8} {'mk_5':>8}")
        for day, blk in sorted(per_day[product].items()):
            e = blk.get("avg_entry_edge")
            m5 = blk.get("avg_markout_5")
            lines.append(
                f"  {day:>4} {blk['pnl']:>10.0f} {blk['trades']:>7} "
                f"{blk['final_position']:>5} {blk['steps_near_limit']:>6} "
                f"{(f'{e:+.3f}' if e is not None else 'n/a'):>8} "
                f"{(f'{m5:+.3f}' if m5 is not None else 'n/a'):>8}"
            )
        lines.append("")
    text = "\n".join(lines)
    (run_dir / "summary.txt").write_text(text + "\n")
    print(text)
    print(f"\nArtifacts: {run_dir}")


if __name__ == "__main__":
    # ``filter_replay_to_product`` is unused here directly; imported to
    # hint at the companion API for per-product single-threaded runs.
    _ = filter_replay_to_product
    main()
