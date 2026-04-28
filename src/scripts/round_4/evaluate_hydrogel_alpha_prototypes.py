"""Evaluate next-step HYDROGEL alpha extraction prototypes.

These prototypes are deliberately wrappers around the current `flat995` bundle.
They test structural ideas before producing upload artifacts:

1. hard high-regime flat/idle, to avoid leakage from the inner R3 cycle state;
2. price-triggered release instead of exact timestamp release;
3. small controlled long inventory before the high-regime short release.

The goal is to separate "more alpha" from "more path overfit".
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
class PrototypeConfig:
    name: str
    mode: str
    control_until: int = 60_000
    short_cap: int = -40
    target_pos: int = 0
    release_bid: int | None = None
    trigger_start: int = 20_000
    trigger_end: int = 30_000
    trigger_mid: float = 10_020.0


def prototype_configs() -> list[PrototypeConfig]:
    return [
        PrototypeConfig("baseline_flat995", "base"),
        PrototypeConfig("cap40_until_60k_filter", "filter_cap", short_cap=-40),
        PrototypeConfig("hard_flat_until_60k", "hard_target", target_pos=0),
        PrototypeConfig("hard_long40_until_60k", "hard_target", target_pos=40),
        PrototypeConfig("hard_long80_until_60k", "hard_target", target_pos=80),
        PrototypeConfig(
            "cap40_until_bid10048",
            "filter_cap",
            short_cap=-40,
            control_until=99_900,
            release_bid=10_048,
        ),
        PrototypeConfig(
            "hard_long40_until_bid10048",
            "hard_target",
            target_pos=40,
            control_until=99_900,
            release_bid=10_048,
        ),
    ]


def replay_cases():
    return [
        ("official100k_log_replay", official_log_replay(OFFICIAL_LOG)),
        ("hist_first100k_all", historical_replay(None, end_ts=99_900)),
        ("hist_day_1_first100k", historical_replay(1, end_ts=99_900)),
        ("hist_day_2_first100k", historical_replay(2, end_ts=99_900)),
        ("hist_day_3_first100k", historical_replay(3, end_ts=99_900)),
        ("hist_day_3_1m", historical_replay(3)),
        ("hist_all_1m", historical_replay(None)),
    ]


def build_trader_cls(base_cls: type, config: PrototypeConfig) -> type:
    if config.mode == "base":
        return base_cls

    class Trader:
        def __init__(self) -> None:
            self._inner = base_cls()
            self._hyd_high_regime = False
            self._released = False

        def run(self, state):
            orders, conversions, trader_data = self._inner.run(state)
            self._observe_hyd_regime(state)
            self._observe_release(state)
            if self._hyd_high_regime and not self._released and state.timestamp < config.control_until:
                if config.mode == "filter_cap":
                    orders = self._filter_short_cap(state, orders, config.short_cap)
                elif config.mode == "hard_target":
                    orders = self._hard_target(state, orders, config.target_pos)
            return orders, conversions, trader_data

        def _observe_hyd_regime(self, state) -> None:
            if self._hyd_high_regime:
                return
            if state.timestamp < config.trigger_start or state.timestamp > config.trigger_end:
                return
            mid = _mid(state)
            if mid is not None and mid >= config.trigger_mid:
                self._hyd_high_regime = True

        def _observe_release(self, state) -> None:
            if not self._hyd_high_regime or self._released:
                return
            if config.release_bid is None:
                self._released = state.timestamp >= config.control_until
                return
            depth = state.order_depths.get(PRODUCT)
            if depth is not None and depth.buy_orders and max(depth.buy_orders) >= config.release_bid:
                self._released = True

        def _hard_target(self, state, orders, target_pos: int):
            orders = dict(orders or {})
            depth = state.order_depths.get(PRODUCT)
            pos = int(state.position.get(PRODUCT, 0))
            delta = target_pos - pos
            if depth is None or delta == 0:
                orders[PRODUCT] = []
                return orders
            if delta > 0 and depth.sell_orders:
                orders[PRODUCT] = [Order(PRODUCT, int(min(depth.sell_orders)), int(delta))]
            elif delta < 0 and depth.buy_orders:
                orders[PRODUCT] = [Order(PRODUCT, int(max(depth.buy_orders)), int(delta))]
            else:
                orders[PRODUCT] = []
            return orders

        def _filter_short_cap(self, state, orders, short_cap: int):
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


def _mid(state) -> float | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders) + min(depth.sell_orders)) / 2


def avg_price(records, side: str) -> float | None:
    selected = [record for record in records if record.product == PRODUCT and record.side == side]
    qty = sum(record.quantity for record in selected)
    if qty <= 0:
        return None
    return sum(record.price * record.quantity for record in selected) / qty


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fill_model = FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True))
    base_cls = load_trader(BASELINE)
    cases = replay_cases()
    rows: list[dict[str, object]] = []

    for config in prototype_configs():
        trader_cls = build_trader_cls(base_cls, config)
        for case_name, replay in cases:
            result = BacktestSimulator(SubmissionHydAdapter(trader_cls), fill_model).run(replay)
            product = result.per_product[PRODUCT]
            pnl_values = [value for _, value in result.pnl_series.get(PRODUCT, ())]
            rows.append(
                {
                    "candidate": config.name,
                    "mode": config.mode,
                    "case": case_name,
                    "target_pos": config.target_pos if config.mode == "hard_target" else "",
                    "short_cap": config.short_cap if config.mode == "filter_cap" else "",
                    "control_until": config.control_until,
                    "release_bid": "" if config.release_bid is None else config.release_bid,
                    "pnl": round(product.pnl, 2),
                    "cash": round(product.cash, 2),
                    "terminal_mark_component": round(
                        product.final_position * (product.mark_price or 0.0), 2
                    ),
                    "final_pos": product.final_position,
                    "trade_count": product.trade_count,
                    "buy_qty": product.buy_trade_quantity,
                    "sell_qty": product.sell_trade_quantity,
                    "avg_buy_price": _round_or_blank(avg_price(result.trade_records, "buy")),
                    "avg_sell_price": _round_or_blank(avg_price(result.trade_records, "sell")),
                    "min_pnl": round(min(pnl_values), 2) if pnl_values else "",
                    "peak_pnl": round(max(pnl_values), 2) if pnl_values else "",
                    "max_drawdown": round(max_drawdown(pnl_values), 2),
                }
            )

    out_path = out_dir / "alpha_prototype_summary.csv"
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
