"""Controlled passive-liquidity probes for the Mark 55 VELVET pattern.

The Mark policy audit found a repeatable conditional pattern:

    recent Mark 67 VELVET buys -> elevated probability of Mark 55
    VELVET sell-taker flow over the next short horizon.

If that pattern is real and executable, the natural response is not to
chase with a taker order. It is to post bid liquidity just before the
expected sell-taker arrives. This script wraps a baseline R4 submission and
tests small passive VELVET bids under several gates, including controls.

Important calibration caveat:
The local replay only credits passive fills when the historical tape prints
at our exact posted price. Official simulation can differ, especially for
inside quotes that would alter the displayed best bid. Treat local results as
a mechanism and risk screen, then use official uploads as calibration.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.datamodel import Order


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_BASE = (
    REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_exp_flat995_vev5500_sell7.py"
)
DEFAULT_OUT = REPO_ROOT / "outputs" / "round_4" / "mark_policy" / "mark55_passive_probe_summary.csv"

VELVET = "VELVETFRUIT_EXTRACT"
R4_POSITION_LIMITS = {
    "HYDROGEL_PACK": 200,
    VELVET: 200,
    **{f"VEV_{k}": 300 for k in (4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500)},
}


@dataclass
class _StubProductCfg:
    position_limit: int


@dataclass
class _StubEngineCfg:
    products: dict[str, _StubProductCfg] = field(default_factory=dict)


def _make_stub_config() -> _StubEngineCfg:
    return _StubEngineCfg(
        products={product: _StubProductCfg(position_limit=limit) for product, limit in R4_POSITION_LIMITS.items()}
    )


def load_submission(path: Path, module_name: str):
    src_dir = str(REPO_ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    trader = module.Trader()
    trader.config = _make_stub_config()
    return trader


class RollingCounter:
    def __init__(self, window: int) -> None:
        self.window = int(window)
        self.events: deque[tuple[int, int]] = deque()
        self.total_qty = 0

    def clear(self) -> None:
        self.events.clear()
        self.total_qty = 0

    def add(self, timestamp: int, quantity: int) -> None:
        quantity = int(quantity)
        if quantity <= 0:
            return
        self.events.append((int(timestamp), quantity))
        self.total_qty += quantity
        self.prune(int(timestamp))

    def prune(self, timestamp: int) -> None:
        cutoff = int(timestamp) - self.window
        while self.events and self.events[0][0] < cutoff:
            _, quantity = self.events.popleft()
            self.total_qty -= quantity

    @property
    def count(self) -> int:
        return len(self.events)

    @property
    def qty(self) -> int:
        return self.total_qty


@dataclass(frozen=True)
class ProbeConfig:
    label: str
    gate: str
    quote_offset: int = 0
    order_size: int = 5
    target_max_position: int = -150
    mark67_window: int = 30_000
    mark67_count_threshold: int = 3
    mark67_qty_threshold: int = 10
    mark22_window: int = 30_000
    mark22_qty_threshold: int = 7
    periodic_mod: int = 10_000
    periodic_active: int = 1_100
    warmup: int = 0


class Mark55PassiveProbeWrapper:
    def __init__(self, base, config: ProbeConfig) -> None:
        self.base = base
        self.config = base.config
        self.probe_config = config
        self._mark67_buy = RollingCounter(config.mark67_window)
        self._mark22_sell = RollingCounter(config.mark22_window)
        self._any_velvet_trade = RollingCounter(config.mark67_window)
        self._last_timestamp: int | None = None

        self.active_steps = 0
        self.orders_added = 0
        self.qty_added = 0
        self.skipped_cap = 0
        self.skipped_cross = 0
        self.skipped_existing_buy = 0
        self.mark67_buy_events = 0
        self.mark22_sell_events = 0

    def _reset_on_rollover(self, timestamp: int) -> None:
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            self._mark67_buy.clear()
            self._mark22_sell.clear()
            self._any_velvet_trade.clear()
        self._last_timestamp = timestamp

    def _ingest_market_trades(self, state) -> None:
        timestamp = int(state.timestamp)
        self._reset_on_rollover(timestamp)
        self._mark67_buy.prune(timestamp)
        self._mark22_sell.prune(timestamp)
        self._any_velvet_trade.prune(timestamp)

        for trade in (state.market_trades or {}).get(VELVET, []) or []:
            quantity = int(getattr(trade, "quantity", 0) or 0)
            if quantity <= 0:
                continue
            self._any_velvet_trade.add(timestamp, quantity)
            if getattr(trade, "buyer", None) == "Mark 67":
                self._mark67_buy.add(timestamp, quantity)
                self.mark67_buy_events += 1
            if getattr(trade, "seller", None) == "Mark 22":
                self._mark22_sell.add(timestamp, quantity)
                self.mark22_sell_events += 1

    def _gate_active(self, state) -> bool:
        cfg = self.probe_config
        timestamp = int(state.timestamp)
        if timestamp < cfg.warmup:
            return False
        if cfg.gate == "always":
            return True
        if cfg.gate == "anti_mark67":
            return self._mark67_buy.count < cfg.mark67_count_threshold
        if cfg.gate == "mark67_count":
            return self._mark67_buy.count >= cfg.mark67_count_threshold
        if cfg.gate == "mark67_qty":
            return self._mark67_buy.qty >= cfg.mark67_qty_threshold
        if cfg.gate == "mark22_qty":
            return self._mark22_sell.qty >= cfg.mark22_qty_threshold
        if cfg.gate == "mark67_or_mark22":
            return (
                self._mark67_buy.count >= cfg.mark67_count_threshold
                or self._mark22_sell.qty >= cfg.mark22_qty_threshold
            )
        if cfg.gate == "periodic":
            return timestamp % cfg.periodic_mod < cfg.periodic_active
        raise ValueError(f"unknown gate {cfg.gate!r}")

    def _append_probe_order(self, orders: dict, state) -> None:
        cfg = self.probe_config
        depth = state.order_depths.get(VELVET)
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return

        existing = list((orders or {}).get(VELVET, []) or [])
        if any(int(order.quantity) > 0 for order in existing):
            self.skipped_existing_buy += 1
            return

        position = int(state.position.get(VELVET, 0))
        remaining_to_target = int(cfg.target_max_position) - position
        if remaining_to_target <= 0:
            self.skipped_cap += 1
            return

        best_bid = int(max(depth.buy_orders))
        best_ask = int(min(depth.sell_orders))
        price = best_bid + int(cfg.quote_offset)
        if price >= best_ask:
            price = best_bid
            if price >= best_ask:
                self.skipped_cross += 1
                return

        quantity = min(int(cfg.order_size), remaining_to_target)
        if quantity <= 0:
            self.skipped_cap += 1
            return

        orders.setdefault(VELVET, []).append(Order(VELVET, int(price), int(quantity)))
        self.orders_added += 1
        self.qty_added += quantity

    def run(self, state):
        self._ingest_market_trades(state)
        orders, conversions, trader_data = self.base.run(state)
        orders = dict(orders or {})
        if self._gate_active(state):
            self.active_steps += 1
            self._append_probe_order(orders, state)
        return orders, conversions, trader_data


def _summarize_result(label: str, trader, result) -> dict[str, float | int | str]:
    velvet = result.per_product.get(VELVET)
    maker_buy_records = [
        record
        for record in result.trade_records
        if record.product == VELVET and record.mode == "maker" and record.side == "buy"
    ]
    taker_sell_records = [
        record
        for record in result.trade_records
        if record.product == VELVET and record.mode == "taker" and record.side == "sell"
    ]
    return {
        "label": label,
        "total_pnl": round(float(result.total_pnl), 2),
        "velvet_pnl": round(float(velvet.pnl), 2) if velvet else 0.0,
        "velvet_pos": int(velvet.final_position) if velvet else 0,
        "velvet_maker_buy_qty": int(sum(record.quantity for record in maker_buy_records)),
        "velvet_maker_buy_trades": len(maker_buy_records),
        "velvet_taker_sell_qty": int(sum(record.quantity for record in taker_sell_records)),
        "velvet_trade_qty": int((velvet.taker_trade_quantity + velvet.maker_trade_quantity) if velvet else 0),
        "velvet_maker_qty": int(velvet.maker_trade_quantity) if velvet else 0,
        "velvet_mk1": round(float(velvet.avg_markout_1), 4) if velvet and velvet.avg_markout_1 is not None else "",
        "velvet_mk5": round(float(velvet.avg_markout_5), 4) if velvet and velvet.avg_markout_5 is not None else "",
        "velvet_mk20": round(float(velvet.avg_markout_20), 4) if velvet and velvet.avg_markout_20 is not None else "",
        "active_steps": int(getattr(trader, "active_steps", 0)),
        "orders_added": int(getattr(trader, "orders_added", 0)),
        "qty_added": int(getattr(trader, "qty_added", 0)),
        "skipped_cap": int(getattr(trader, "skipped_cap", 0)),
        "skipped_cross": int(getattr(trader, "skipped_cross", 0)),
        "skipped_existing_buy": int(getattr(trader, "skipped_existing_buy", 0)),
        "mark67_buy_events": int(getattr(trader, "mark67_buy_events", 0)),
        "mark22_sell_events": int(getattr(trader, "mark22_sell_events", 0)),
    }


def _run_variant(base_path: Path, data_dir: Path, cfg: ProbeConfig | None) -> dict[str, float | int | str]:
    from src.backtest.replay_engine import ReplayEngine
    from src.backtest.simulator import BacktestSimulator

    label = "base" if cfg is None else cfg.label
    trader = load_submission(base_path, f"r4_mark55_passive_{label}")
    if cfg is not None:
        trader = Mark55PassiveProbeWrapper(trader, cfg)
    price_paths = sorted(data_dir.glob("prices_round_4_day_*.csv"))
    trade_paths = sorted(data_dir.glob("trades_round_4_day_*.csv"))
    replay = ReplayEngine.from_files(price_paths=price_paths, trade_paths=trade_paths)
    result = BacktestSimulator(trader=trader).run(replay)
    return _summarize_result(label, trader, result)


def _variant_grid(*, quick: bool) -> Iterable[ProbeConfig | None]:
    yield None
    base_kwargs = {"order_size": 5, "target_max_position": -150}
    yield ProbeConfig("mark67_touch_q5_tgt-150", gate="mark67_count", quote_offset=0, **base_kwargs)
    yield ProbeConfig("mark67_inside1_q5_tgt-150", gate="mark67_count", quote_offset=1, **base_kwargs)
    yield ProbeConfig("mark67_or_m22_touch_q5_tgt-150", gate="mark67_or_mark22", quote_offset=0, **base_kwargs)
    yield ProbeConfig("periodic_touch_q5_tgt-150", gate="periodic", quote_offset=0, **base_kwargs)
    yield ProbeConfig("always_touch_q5_tgt-150", gate="always", quote_offset=0, **base_kwargs)
    yield ProbeConfig("anti_mark67_touch_q5_tgt-150", gate="anti_mark67", quote_offset=0, **base_kwargs)

    if quick:
        return

    for target in (-175, -100, -50, 0):
        yield ProbeConfig(
            f"mark67_touch_q5_tgt{target}",
            gate="mark67_count",
            quote_offset=0,
            order_size=5,
            target_max_position=target,
        )
    for size in (2, 10, 20):
        yield ProbeConfig(
            f"mark67_touch_q{size}_tgt-150",
            gate="mark67_count",
            quote_offset=0,
            order_size=size,
            target_max_position=-150,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--quick", action="store_true", help="Run only the core signal/control variants.")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for cfg in _variant_grid(quick=args.quick):
        label = "base" if cfg is None else cfg.label
        print(f"running {label}", flush=True)
        rows.append(_run_variant(args.base, args.data_dir, cfg))

    df = pd.DataFrame(rows)
    if not df.empty:
        base_total = float(df.loc[df["label"] == "base", "total_pnl"].iloc[0])
        base_velvet = float(df.loc[df["label"] == "base", "velvet_pnl"].iloc[0])
        df["total_delta_vs_base"] = (df["total_pnl"].astype(float) - base_total).round(2)
        df["velvet_delta_vs_base"] = (df["velvet_pnl"].astype(float) - base_velvet).round(2)
        df.sort_values(["total_delta_vs_base", "velvet_delta_vs_base"], ascending=False, inplace=True)
    df.to_csv(args.out, index=False)
    print(df.to_string(index=False))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
