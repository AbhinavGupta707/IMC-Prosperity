"""Evaluate HYDROGEL high-regime inventory-control variants.

This is a diagnostic grid, not a submission generator. It wraps the current
`flat995` submission in a HYDROGEL-only adapter and asks one focused question:

If HYDROGEL has revealed a high path in the 20k-30k discovery window, how late
should we allow the base short-mean-reversion sleeve to build short inventory?

Outputs are written to `outputs/round_4/hydrogel_probes`.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.simulator import BacktestSimulator
from src.datamodel import Order
from src.scripts.round_4.evaluate_hydrogel_probe_submissions import (
    OFFICIAL_LOG,
    PRODUCT,
    REPO_ROOT,
    SubmissionHydAdapter,
    historical_replay,
    load_trader,
    max_drawdown,
    official_log_replay,
)


if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

BASELINE = REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_safer_hydflat995.py"
OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_probes"


@dataclass(frozen=True)
class GridConfig:
    name: str
    short_cap: int | None
    control_until: int | None
    trigger_start: int = 20_000
    trigger_end: int = 30_000
    trigger_mid: float = 10_020.0


def grid_configs() -> list[GridConfig]:
    configs = [GridConfig("baseline_flat995", None, None)]
    for control_until in (45_000, 50_000, 55_000, 60_000, 65_000, 70_000, 75_000):
        configs.append(
            GridConfig(
                name=f"noshort_until_{control_until // 1000}k",
                short_cap=0,
                control_until=control_until,
            )
        )
    for short_cap in (-40, -80, -120, -160):
        configs.append(
            GridConfig(
                name=f"cap{abs(short_cap)}_until_60k",
                short_cap=short_cap,
                control_until=60_000,
            )
        )
    return configs


def build_trader_cls(base_cls: type, config: GridConfig) -> type:
    if config.short_cap is None or config.control_until is None:
        return base_cls

    class Trader:
        def __init__(self) -> None:
            self._inner = base_cls()
            self._hyd_high_regime = False

        def run(self, state):
            orders, conversions, trader_data = self._inner.run(state)
            self._observe_hyd_regime(state)
            if self._hyd_high_regime and state.timestamp < config.control_until:
                orders = self._apply_hyd_short_cap(state, orders, config.short_cap)
            return orders, conversions, trader_data

        def _observe_hyd_regime(self, state) -> None:
            if self._hyd_high_regime:
                return
            if state.timestamp < config.trigger_start or state.timestamp > config.trigger_end:
                return
            depth = state.order_depths.get(PRODUCT)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                return
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            if mid >= config.trigger_mid:
                self._hyd_high_regime = True

        def _apply_hyd_short_cap(self, state, orders, short_cap: int):
            orders = dict(orders or {})
            depth = state.order_depths.get(PRODUCT)
            pos = int(state.position.get(PRODUCT, 0))
            if depth is not None and pos < short_cap and depth.sell_orders:
                best_ask = min(depth.sell_orders)
                orders[PRODUCT] = [Order(PRODUCT, int(best_ask), int(short_cap - pos))]
                return orders

            filtered = []
            projected = pos
            for order in list(orders.get(PRODUCT, [])):
                qty = int(order.quantity)
                if qty < 0:
                    max_sell = max(0, projected - short_cap)
                    allowed = min(-qty, max_sell)
                    if allowed > 0:
                        filtered.append(Order(PRODUCT, int(order.price), -allowed))
                        projected -= allowed
                else:
                    filtered.append(order)
                    projected += qty
            orders[PRODUCT] = filtered
            return orders

    return Trader


def replay_cases():
    return [
        ("official100k_log_replay", official_log_replay(OFFICIAL_LOG)),
        ("hist_day_1_first100k", historical_replay(1, end_ts=99_900)),
        ("hist_day_2_first100k", historical_replay(2, end_ts=99_900)),
        ("hist_day_3_first100k", historical_replay(3, end_ts=99_900)),
        ("hist_day_3_1m", historical_replay(3)),
    ]


def avg_price(records, side: str) -> float | None:
    selected = [record for record in records if record.product == PRODUCT and record.side == side]
    qty = sum(record.quantity for record in selected)
    if qty <= 0:
        return None
    return sum(record.price * record.quantity for record in selected) / qty


def signed_qty_before(records, side: str, ts: int | None) -> int:
    if ts is None:
        return 0
    return sum(
        record.quantity
        for record in records
        if record.product == PRODUCT and record.side == side and record.fill_timestamp < ts
    )


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fill_model = FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True))
    base_cls = load_trader(BASELINE)
    cases = replay_cases()

    rows: list[dict[str, object]] = []
    for config in grid_configs():
        trader_cls = build_trader_cls(base_cls, config)
        for case_name, replay in cases:
            result = BacktestSimulator(SubmissionHydAdapter(trader_cls), fill_model).run(replay)
            product = result.per_product[PRODUCT]
            pnl_values = [value for _, value in result.pnl_series.get(PRODUCT, ())]
            rows.append(
                {
                    "candidate": config.name,
                    "case": case_name,
                    "trigger_mid": config.trigger_mid,
                    "short_cap": "" if config.short_cap is None else config.short_cap,
                    "control_until": "" if config.control_until is None else config.control_until,
                    "pnl": round(product.pnl, 2),
                    "cash": round(product.cash, 2),
                    "terminal_mark_component": round(
                        product.final_position * (product.mark_price or 0.0), 2
                    ),
                    "final_pos": product.final_position,
                    "mark_price": product.mark_price,
                    "trade_count": product.trade_count,
                    "buy_qty": product.buy_trade_quantity,
                    "sell_qty": product.sell_trade_quantity,
                    "avg_buy_price": _round_or_blank(avg_price(result.trade_records, "buy")),
                    "avg_sell_price": _round_or_blank(avg_price(result.trade_records, "sell")),
                    "sell_qty_before_control_release": signed_qty_before(
                        result.trade_records, "sell", config.control_until
                    ),
                    "min_pnl": round(min(pnl_values), 2) if pnl_values else "",
                    "peak_pnl": round(max(pnl_values), 2) if pnl_values else "",
                    "max_drawdown": round(max_drawdown(pnl_values), 2),
                }
            )

    out_path = out_dir / "highregime_grid_summary.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path}")


def _round_or_blank(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
