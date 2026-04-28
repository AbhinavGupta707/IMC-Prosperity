"""Capacity-reserve probe for Mark-conditioned VEV_5000/5100 sell signals.

The Mark-conditioned schedule audit found that Mark 22 sell-flow can identify
better short-horizon sell signals in VEV_5000/5100. The current schedule often
uses all short capacity at the open, so this probe asks the practical question:

    Is it worth reserving some short capacity until Mark 22 sell-flow appears?

This is a local research probe, not a submission. It wraps an existing
submission, caps early/inactive short inventory for VEV_5000 and VEV_5100, and
compares realized replay PnL.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_BASE = REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_exp_flat995_vev5500_sell7.py"
DEFAULT_OUT = REPO_ROOT / "outputs" / "round_4" / "mark_conditioned" / "reserve_probe_summary.csv"

R4_POSITION_LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in (4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500)},
}

MARK_PRODUCTS = {"VELVETFRUIT_EXTRACT", "VEV_5300", "VEV_5400", "VEV_5500"}
RESERVE_PRODUCTS = ("VEV_5000", "VEV_5100")


@dataclass
class _StubProductCfg:
    position_limit: int


@dataclass
class _StubEngineCfg:
    products: dict[str, _StubProductCfg] = field(default_factory=dict)


def _make_stub_config() -> _StubEngineCfg:
    return _StubEngineCfg(
        products={p: _StubProductCfg(position_limit=lim) for p, lim in R4_POSITION_LIMITS.items()}
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


class MarkReserveWrapper:
    def __init__(
        self,
        base,
        *,
        inactive_floor: int,
        window: int,
        reserve_until: int | None,
    ) -> None:
        self.base = base
        self.config = base.config
        self.inactive_floor = inactive_floor
        self.window = window
        self.reserve_until = reserve_until
        self.active_until = -1
        self.orders_trimmed = 0
        self.qty_trimmed = 0
        self.trigger_count = 0

    def _ingest_mark_flow(self, state) -> None:
        market_trades = state.market_trades or {}
        for product, trades in market_trades.items():
            if product not in MARK_PRODUCTS:
                continue
            for trade in trades or []:
                if getattr(trade, "seller", None) == "Mark 22":
                    self.active_until = max(self.active_until, int(state.timestamp) + self.window)
                    self.trigger_count += 1

    def _reserve_active(self, timestamp: int) -> bool:
        return timestamp <= self.active_until

    def _should_reserve(self, timestamp: int) -> bool:
        if self.reserve_until is not None and timestamp > self.reserve_until:
            return False
        return not self._reserve_active(timestamp)

    def _clip_product_orders(self, product: str, orders: list, position: int) -> list:
        if product not in RESERVE_PRODUCTS:
            return orders
        clipped = []
        working_position = position
        for order in orders:
            qty = int(order.quantity)
            if qty >= 0:
                clipped.append(order)
                working_position += qty
                continue
            allowed_sell = max(0, working_position - self.inactive_floor)
            requested_sell = -qty
            if requested_sell <= allowed_sell:
                clipped.append(order)
                working_position += qty
                continue
            if allowed_sell > 0:
                clipped.append(type(order)(order.symbol, order.price, -allowed_sell))
            self.orders_trimmed += 1
            self.qty_trimmed += requested_sell - allowed_sell
            working_position -= allowed_sell
        return clipped

    def run(self, state):
        self._ingest_mark_flow(state)
        orders, conversions, trader_data = self.base.run(state)
        if not self._should_reserve(int(state.timestamp)):
            return orders, conversions, trader_data
        orders = dict(orders or {})
        for product in RESERVE_PRODUCTS:
            product_orders = orders.get(product)
            if not product_orders:
                continue
            clipped = self._clip_product_orders(
                product,
                list(product_orders),
                int(state.position.get(product, 0)),
            )
            if clipped:
                orders[product] = clipped
            else:
                orders.pop(product, None)
        return orders, conversions, trader_data


def _summarize_result(label: str, trader, result) -> dict[str, float | int | str]:
    rows: dict[str, float | int | str] = {"label": label}
    final_total = 0.0
    for product, series in result.pnl_series.items():
        if series:
            pnl = float(series[-1][1])
            rows[f"pnl_{product}"] = round(pnl, 2)
            final_total += pnl
    rows["total_pnl"] = round(final_total, 2)
    rows["trade_count"] = len(result.trade_records)
    rows["abs_qty"] = int(sum(abs(t.quantity) for t in result.trade_records))
    rows["orders_trimmed"] = getattr(trader, "orders_trimmed", 0)
    rows["qty_trimmed"] = getattr(trader, "qty_trimmed", 0)
    rows["trigger_count"] = getattr(trader, "trigger_count", 0)
    return rows


def _run_variant(base_path: Path, data_dir: Path, label: str, inactive_floor: int | None, window: int, reserve_until: int | None):
    from src.backtest.replay_engine import ReplayEngine
    from src.backtest.simulator import BacktestSimulator

    trader = load_submission(base_path, f"r4_mark_reserve_{label}")
    if inactive_floor is not None:
        trader = MarkReserveWrapper(
            trader,
            inactive_floor=inactive_floor,
            window=window,
            reserve_until=reserve_until,
        )
    price_paths = sorted(data_dir.glob("prices_round_4_day_*.csv"))
    trade_paths = sorted(data_dir.glob("trades_round_4_day_*.csv"))
    replay = ReplayEngine.from_files(price_paths=price_paths, trade_paths=trade_paths)
    result = BacktestSimulator(trader=trader).run(replay)
    return _summarize_result(label, trader, result)


def _variant_grid(*, quick: bool) -> Iterable[tuple[str, int | None, int, int | None]]:
    yield "base", None, 0, None
    if quick:
        yield "floor-250_win10000", -250, 10_000, None
        yield "floor-200_win10000", -200, 10_000, None
        yield "floor-100_win10000", -100, 10_000, None
        yield "floor-200_win10000_until50000", -200, 10_000, 50_000
        return
    for floor in (-250, -200, -150, -100, 0):
        for window in (10_000, 30_000):
            yield f"floor{floor}_win{window}", floor, window, None
    for floor in (-250, -200, -150, -100):
        yield f"floor{floor}_win10000_until50000", floor, 10_000, 50_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--quick", action="store_true", help="Run only the mechanism-check variants.")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, floor, window, reserve_until in _variant_grid(quick=args.quick):
        print(f"running {label}", flush=True)
        rows.append(_run_variant(args.base, args.data_dir, label, floor, window, reserve_until))
    df = pd.DataFrame(rows)
    df.sort_values("total_pnl", ascending=False, inplace=True)
    df.to_csv(args.out, index=False)
    print(df.to_string(index=False))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
