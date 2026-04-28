"""Evaluate structural HYDROGEL high-regime release policies.

This script follows the official-probe lesson that fixed ``60k`` hard-long
works on the current 100k path, but may be timestamp-fit. It wraps the current
``flat995`` R4 bundle with HYD-only high-regime controls and compares:

* fixed timestamp release;
* bid-threshold release;
* bid-threshold with persistence;
* local-turn release from a high bid;
* simple false-trigger abort guards.

The outputs are diagnostic. Official simulator uploads are still needed for
fill calibration, but this keeps us honest about cross-window fragility before
spending upload budget.
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
class ReleaseConfig:
    name: str
    target_pos: int
    release_policy: str
    fallback_ts: int
    release_bid: int | None = None
    persist_ticks: int = 1
    turn_min_bid: int | None = None
    turn_drop: int | None = None
    abort_mid: float | None = None
    trigger_start: int = 20_000
    trigger_end: int = 30_000
    trigger_mid: float = 10_020.0


def release_configs() -> list[ReleaseConfig]:
    configs = [
        ReleaseConfig("baseline_flat995", 0, "base", 0),
        ReleaseConfig("hardflat_fixed60k", 0, "fixed", 60_000),
        ReleaseConfig("hardlong40_fixed60k", 40, "fixed", 60_000),
        ReleaseConfig("hardlong80_fixed60k", 80, "fixed", 60_000),
    ]

    for threshold in (10_044, 10_048, 10_052, 10_056):
        configs.append(
            ReleaseConfig(
                name=f"hardlong40_bid{threshold}_fallback70k",
                target_pos=40,
                release_policy="bid",
                release_bid=threshold,
                fallback_ts=70_000,
            )
        )
    for threshold in (10_048, 10_052):
        configs.append(
            ReleaseConfig(
                name=f"hardflat_bid{threshold}_fallback70k",
                target_pos=0,
                release_policy="bid",
                release_bid=threshold,
                fallback_ts=70_000,
            )
        )
        configs.append(
            ReleaseConfig(
                name=f"hardlong40_bid{threshold}_persist3_fallback70k",
                target_pos=40,
                release_policy="bid",
                release_bid=threshold,
                persist_ticks=3,
                fallback_ts=70_000,
            )
        )

    for drop in (2, 4, 6):
        configs.append(
            ReleaseConfig(
                name=f"hardlong40_turn_bid10052_drop{drop}_fallback70k",
                target_pos=40,
                release_policy="turn",
                turn_min_bid=10_052,
                turn_drop=drop,
                fallback_ts=70_000,
            )
        )

    for abort_mid in (10_018.0, 10_015.0):
        configs.append(
            ReleaseConfig(
                name=f"hardlong40_bid10052_abort{int(abort_mid)}_fallback70k",
                target_pos=40,
                release_policy="bid",
                release_bid=10_052,
                fallback_ts=70_000,
                abort_mid=abort_mid,
            )
        )
    return configs


def replay_cases():
    return [
        ("official100k_log_replay", official_log_replay(OFFICIAL_LOG)),
        ("hist_first100k_all", historical_replay(None, end_ts=99_900)),
        ("hist_day_1_first100k", historical_replay(1, end_ts=99_900)),
        ("hist_day_2_first100k", historical_replay(2, end_ts=99_900)),
        ("hist_day_3_first100k", historical_replay(3, end_ts=99_900)),
        ("hist_day_1_1m", historical_replay(1)),
        ("hist_day_2_1m", historical_replay(2)),
        ("hist_day_3_1m", historical_replay(3)),
        ("hist_all_1m", historical_replay(None)),
    ]


def build_trader_cls(base_cls: type, config: ReleaseConfig) -> type:
    if config.release_policy == "base":
        return base_cls

    class Trader:
        def __init__(self) -> None:
            self._inner = base_cls()
            self._hyd_high_regime = False
            self._released = False
            self._aborted = False
            self._bid_persist_count = 0
            self._peak_bid: int | None = None
            self._trigger_ts: int | None = None
            self._release_ts: int | None = None
            self._abort_ts: int | None = None

        def run(self, state):
            orders, conversions, trader_data = self._inner.run(state)
            self._observe_hyd_regime(state)
            self._observe_release_or_abort(state)
            if self._hyd_high_regime and self._aborted:
                if int(state.position.get(PRODUCT, 0)) != 0:
                    orders = self._hard_target_hyd(state, orders, 0)
                return orders, conversions, trader_data
            if self._hyd_high_regime and not self._released:
                orders = self._hard_target_hyd(state, orders, config.target_pos)
            return orders, conversions, trader_data

        @property
        def event_state(self) -> dict[str, object]:
            return {
                "triggered": self._hyd_high_regime,
                "released": self._released,
                "aborted": self._aborted,
                "trigger_ts": self._trigger_ts,
                "release_ts": self._release_ts,
                "abort_ts": self._abort_ts,
                "peak_bid": self._peak_bid,
            }

        def _observe_hyd_regime(self, state) -> None:
            if self._hyd_high_regime:
                return
            if state.timestamp < config.trigger_start or state.timestamp > config.trigger_end:
                return
            mid = _mid(state)
            if mid is not None and mid >= config.trigger_mid:
                self._hyd_high_regime = True
                self._trigger_ts = int(state.timestamp)

        def _observe_release_or_abort(self, state) -> None:
            if not self._hyd_high_regime or self._released or self._aborted:
                return

            bid = _best_bid(state)
            mid = _mid(state)
            if bid is not None:
                self._peak_bid = bid if self._peak_bid is None else max(self._peak_bid, bid)

            if (
                config.abort_mid is not None
                and mid is not None
                and mid <= config.abort_mid
                and state.timestamp < config.fallback_ts
            ):
                self._aborted = True
                self._abort_ts = int(state.timestamp)
                return

            should_release = False
            if config.release_policy == "fixed":
                should_release = state.timestamp >= config.fallback_ts
            elif config.release_policy == "bid":
                if bid is not None and config.release_bid is not None and bid >= config.release_bid:
                    self._bid_persist_count += 1
                else:
                    self._bid_persist_count = 0
                should_release = self._bid_persist_count >= max(1, config.persist_ticks)
            elif config.release_policy == "turn":
                if (
                    bid is not None
                    and self._peak_bid is not None
                    and config.turn_min_bid is not None
                    and config.turn_drop is not None
                    and self._peak_bid >= config.turn_min_bid
                    and bid <= self._peak_bid - config.turn_drop
                ):
                    should_release = True

            if should_release or state.timestamp >= config.fallback_ts:
                self._released = True
                self._release_ts = int(state.timestamp)

        def _hard_target_hyd(self, state, orders, target_pos: int):
            orders = dict(orders or {})
            depth = state.order_depths.get(PRODUCT)
            pos = int(state.position.get(PRODUCT, 0))
            delta = int(target_pos - pos)
            if depth is None or delta == 0:
                orders[PRODUCT] = []
                return orders
            if delta > 0 and depth.sell_orders:
                best_ask = min(depth.sell_orders.keys())
                orders[PRODUCT] = [Order(PRODUCT, int(best_ask), delta)]
            elif delta < 0 and depth.buy_orders:
                best_bid = max(depth.buy_orders.keys())
                orders[PRODUCT] = [Order(PRODUCT, int(best_bid), delta)]
            else:
                orders[PRODUCT] = []
            return orders

    return Trader


def _best_bid(state) -> int | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.buy_orders:
        return None
    return int(max(depth.buy_orders.keys()))


def _mid(state) -> float | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2


def avg_price(records, side: str) -> float | None:
    selected = [record for record in records if record.product == PRODUCT and record.side == side]
    qty = sum(record.quantity for record in selected)
    if qty <= 0:
        return None
    return sum(record.price * record.quantity for record in selected) / qty


def hyd_qty_before(records, side: str, ts: int | None) -> int:
    if ts is None:
        return 0
    return sum(
        record.quantity
        for record in records
        if record.product == PRODUCT and record.side == side and record.fill_timestamp < ts
    )


def _round_or_blank(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def _event_state(adapter: SubmissionHydAdapter) -> dict[str, object]:
    inner = getattr(adapter, "_inner", None)
    if inner is None:
        return {}
    event_state = getattr(inner, "event_state", None)
    if isinstance(event_state, dict):
        return event_state
    return {}


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fill_model = FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True))
    base_cls = load_trader(BASELINE)
    cases = replay_cases()
    rows: list[dict[str, object]] = []

    for config in release_configs():
        trader_cls = build_trader_cls(base_cls, config)
        for case_name, replay in cases:
            adapter = SubmissionHydAdapter(trader_cls)
            result = BacktestSimulator(adapter, fill_model).run(replay)
            product = result.per_product[PRODUCT]
            pnl_values = [value for _, value in result.pnl_series.get(PRODUCT, ())]
            events = _event_state(adapter)
            release_ts = events.get("release_ts")
            abort_ts = events.get("abort_ts")
            rows.append(
                {
                    "candidate": config.name,
                    "case": case_name,
                    "target_pos": config.target_pos,
                    "release_policy": config.release_policy,
                    "release_bid": "" if config.release_bid is None else config.release_bid,
                    "persist_ticks": config.persist_ticks,
                    "turn_min_bid": "" if config.turn_min_bid is None else config.turn_min_bid,
                    "turn_drop": "" if config.turn_drop is None else config.turn_drop,
                    "abort_mid": "" if config.abort_mid is None else config.abort_mid,
                    "fallback_ts": config.fallback_ts,
                    "triggered": events.get("triggered", ""),
                    "released": events.get("released", ""),
                    "aborted": events.get("aborted", ""),
                    "trigger_ts": events.get("trigger_ts", ""),
                    "release_ts": "" if release_ts is None else release_ts,
                    "abort_ts": "" if abort_ts is None else abort_ts,
                    "peak_bid": events.get("peak_bid", ""),
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
                    "sell_qty_before_release": hyd_qty_before(
                        result.trade_records, "sell", int(release_ts) if release_ts else None
                    ),
                    "buy_qty_before_release": hyd_qty_before(
                        result.trade_records, "buy", int(release_ts) if release_ts else None
                    ),
                    "min_pnl": round(min(pnl_values), 2) if pnl_values else "",
                    "peak_pnl": round(max(pnl_values), 2) if pnl_values else "",
                    "max_drawdown": round(max_drawdown(pnl_values), 2),
                }
            )

    out_path = out_dir / "structural_release_summary.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
