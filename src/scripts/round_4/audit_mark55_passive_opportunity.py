"""Measure Mark55 passive-bid opportunity before building upload probes.

`test_mark55_passive_probe.py` answers, "does a wrapper around the current
submission make money under local exact-price replay?" This script asks the
cleaner microstructure question:

    After a decision timestamp with a given gate active, how often does the
    next timestamp contain VELVET sell-taker flow, and what would the
    markout have been for a passive bid posted at the prior touch/inside?

This is deliberately an opportunity audit, not a strategy optimizer. It keeps
the assumptions visible:

- touch/exact: fill only if the next tape prints exactly at our posted price,
  with 30% allocation, matching the local passive-fill convention.
- inside/potential: if we improve the bid by one tick without crossing, a
  future sell-taker could hit us even though the historical print would have
  occurred at the old bid. This is an official-simulator calibration
  hypothesis, not a local replay fact.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.scripts.round_4.audit_mark_behavior_classification import (
    _attach_book,
    _book_features,
    _load_historical,
    _load_official,
)


DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OFFICIAL_LOG = Path("/Users/abhinavgupta/Desktop/IMC/r4 Sim Results/sellonly/497595.log")
DEFAULT_OUT_DIR = Path("outputs/round_4/mark_policy")

VELVET = "VELVETFRUIT_EXTRACT"
SELL_TAKER = {"sell", "sell_mid"}
BUY_TAKER = {"buy", "buy_mid"}
HORIZONS = (1_000, 5_000, 10_000, 30_000)


class RollingCounter:
    def __init__(self, window: int) -> None:
        self.window = int(window)
        self.events: deque[tuple[int, int]] = deque()
        self.total_qty = 0

    def add(self, timestamp: int, quantity: int) -> None:
        quantity = int(quantity)
        if quantity <= 0:
            return
        self.events.append((int(timestamp), quantity))
        self.total_qty += quantity
        self.prune(timestamp)

    def prune(self, timestamp: int) -> None:
        cutoff = int(timestamp) - self.window
        while self.events and self.events[0][0] < cutoff:
            _, qty = self.events.popleft()
            self.total_qty -= qty

    @property
    def count(self) -> int:
        return len(self.events)

    @property
    def qty(self) -> int:
        return self.total_qty


@dataclass(frozen=True)
class GateState:
    mark67_count_ge3: bool
    mark67_cnt5k_ge1: bool
    mark67_since_1k_5k: bool
    mark67_since_1k_10k: bool
    mark67_count_ge3_since_1k_5k: bool
    mark22_qty_ge7: bool
    mark67_or_mark22: bool
    anti_mark67: bool
    periodic_11pct: bool
    always: bool = True


def _trade_stats_by_key(trade_book: pd.DataFrame) -> dict[tuple[int, int], dict[str, object]]:
    out: dict[tuple[int, int], dict[str, object]] = {}
    if trade_book.empty:
        return out
    keep = trade_book[trade_book["symbol"].eq(VELVET)].copy()
    keep = keep[(keep["buyer"] != "SUBMISSION") & (keep["seller"] != "SUBMISSION")]
    keep["quantity"] = keep["quantity"].astype(int)
    keep["price_int"] = keep["price"].astype(int)
    for (day, timestamp), group in keep.groupby(["day", "timestamp"], sort=False):
        sell_taker = group[group["aggressor_side"].isin(SELL_TAKER)]
        m55_sell = sell_taker[sell_taker["seller"].eq("Mark 55")]
        mark67_buy = group[group["buyer"].eq("Mark 67") & group["aggressor_side"].isin(BUY_TAKER)]
        mark22_sell = group[group["seller"].eq("Mark 22") & group["aggressor_side"].isin(SELL_TAKER)]
        out[(int(day), int(timestamp))] = {
            "all_sell_qty": int(sell_taker["quantity"].sum()),
            "m55_sell_qty": int(m55_sell["quantity"].sum()),
            "all_sell_by_price": sell_taker.groupby("price_int")["quantity"].sum().to_dict(),
            "m55_sell_by_price": m55_sell.groupby("price_int")["quantity"].sum().to_dict(),
            "mark67_buy_count": int(len(mark67_buy)),
            "mark67_buy_qty": int(mark67_buy["quantity"].sum()),
            "mark22_sell_count": int(len(mark22_sell)),
            "mark22_sell_qty": int(mark22_sell["quantity"].sum()),
        }
    return out


def _allocated_touch_qty(by_price: dict[int, int], price: int, order_size: int) -> int:
    printed = int(by_price.get(int(price), 0) or 0)
    if printed <= 0:
        return 0
    return min(int(order_size), int(printed * 0.3))


def _decision_panel(
    *,
    dataset: str,
    prices: pd.DataFrame,
    trades: pd.DataFrame,
    order_size: int,
) -> pd.DataFrame:
    book = _book_features(prices)
    trade_book = _attach_book(trades, book)
    stats_by_key = _trade_stats_by_key(trade_book)

    velvet_book = book[book["product"].eq(VELVET)].copy()
    velvet_book.sort_values(["day", "timestamp"], inplace=True)
    rows: list[dict[str, object]] = []

    for day, day_book in velvet_book.groupby("day", sort=False):
        mark67 = RollingCounter(30_000)
        mark67_5k = RollingCounter(5_000)
        mark22 = RollingCounter(30_000)
        last_mark67_ts: int | None = None
        day_book = day_book.reset_index(drop=True)
        for idx, row in day_book.iterrows():
            timestamp = int(row["timestamp"])
            current_stats = stats_by_key.get((int(day), timestamp), {})
            mark67.prune(timestamp)
            mark67_5k.prune(timestamp)
            mark22.prune(timestamp)
            mark67_qty = int(current_stats.get("mark67_buy_qty", 0) or 0)
            mark22_qty = int(current_stats.get("mark22_sell_qty", 0) or 0)
            if mark67_qty:
                mark67.add(timestamp, mark67_qty)
                mark67_5k.add(timestamp, mark67_qty)
                last_mark67_ts = timestamp
            if mark22_qty:
                mark22.add(timestamp, mark22_qty)

            if idx + 1 >= len(day_book):
                continue
            if pd.isna(row["bid"]) or pd.isna(row["ask"]):
                continue
            next_row = day_book.iloc[idx + 1]
            next_timestamp = int(next_row["timestamp"])
            next_stats = stats_by_key.get((int(day), next_timestamp), {})

            bid = int(row["bid"])
            ask = int(row["ask"])
            touch_price = bid
            inside_price = bid + 1 if bid + 1 < ask else bid
            gates = GateState(
                mark67_count_ge3=mark67.count >= 3,
                mark67_cnt5k_ge1=mark67_5k.count >= 1,
                mark67_since_1k_5k=(
                    last_mark67_ts is not None and 1_000 <= timestamp - last_mark67_ts <= 5_000
                ),
                mark67_since_1k_10k=(
                    last_mark67_ts is not None and 1_000 <= timestamp - last_mark67_ts <= 10_000
                ),
                mark67_count_ge3_since_1k_5k=(
                    mark67.count >= 3
                    and last_mark67_ts is not None
                    and 1_000 <= timestamp - last_mark67_ts <= 5_000
                ),
                mark22_qty_ge7=mark22.qty >= 7,
                mark67_or_mark22=mark67.count >= 3 or mark22.qty >= 7,
                anti_mark67=mark67.count < 3,
                periodic_11pct=timestamp % 10_000 < 1_100,
            )

            all_sell_by_price = next_stats.get("all_sell_by_price", {}) or {}
            m55_sell_by_price = next_stats.get("m55_sell_by_price", {}) or {}
            all_sell_qty = int(next_stats.get("all_sell_qty", 0) or 0)
            m55_sell_qty = int(next_stats.get("m55_sell_qty", 0) or 0)

            base = {
                "dataset": dataset,
                "day": int(day),
                "timestamp": timestamp,
                "next_timestamp": next_timestamp,
                "bid": bid,
                "ask": ask,
                "spread": int(ask - bid),
                "mark67_cnt_30k": int(mark67.count),
                "mark67_cnt_5k": int(mark67_5k.count),
                "mark67_qty_30k": int(mark67.qty),
                "mark67_since": int(timestamp - last_mark67_ts) if last_mark67_ts is not None else np.nan,
                "mark22_qty_30k": int(mark22.qty),
                "next_all_sell_qty": all_sell_qty,
                "next_m55_sell_qty": m55_sell_qty,
                "touch_price": touch_price,
                "inside_price": inside_price,
                "touch_all_qty_30pct": _allocated_touch_qty(all_sell_by_price, touch_price, order_size),
                "touch_m55_qty_30pct": _allocated_touch_qty(m55_sell_by_price, touch_price, order_size),
                "inside_all_qty_100pct": min(order_size, all_sell_qty),
                "inside_m55_qty_100pct": min(order_size, m55_sell_qty),
            }
            for horizon in HORIZONS:
                future = next_row.get(f"mid_future_{horizon}")
                if pd.isna(future):
                    base[f"touch_markout_{horizon}"] = np.nan
                    base[f"inside_markout_{horizon}"] = np.nan
                else:
                    base[f"touch_markout_{horizon}"] = float(future) - float(touch_price)
                    base[f"inside_markout_{horizon}"] = float(future) - float(inside_price)
            for gate_name, active in gates.__dict__.items():
                gate_row = dict(base)
                gate_row["gate"] = gate_name
                gate_row["active"] = bool(active)
                rows.append(gate_row)

    return pd.DataFrame(rows)


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    clean = pd.DataFrame({"v": values, "w": weights}).dropna()
    clean = clean[clean["w"] > 0]
    if clean.empty:
        return np.nan
    return float(np.average(clean["v"], weights=clean["w"]))


def _summarize(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    fill_specs = [
        ("touch_all_30pct", "touch_all_qty_30pct", "touch_price", "touch_markout"),
        ("touch_m55_30pct", "touch_m55_qty_30pct", "touch_price", "touch_markout"),
        ("inside_all_100pct", "inside_all_qty_100pct", "inside_price", "inside_markout"),
        ("inside_m55_100pct", "inside_m55_qty_100pct", "inside_price", "inside_markout"),
    ]
    active_panel = panel[panel["active"]].copy()
    for (dataset, gate), group in active_panel.groupby(["dataset", "gate"], sort=False):
        for label, qty_col, price_col, markout_prefix in fill_specs:
            qty = group[qty_col].astype(int)
            row = {
                "dataset": dataset,
                "gate": gate,
                "fill_model": label,
                "active_steps": int(len(group)),
                "steps_with_next_m55_sell": int((group["next_m55_sell_qty"] > 0).sum()),
                "next_m55_sell_qty": int(group["next_m55_sell_qty"].sum()),
                "steps_with_fill": int((qty > 0).sum()),
                "fill_qty": int(qty.sum()),
                "avg_price": _weighted_mean(group[price_col].astype(float), qty),
                "fill_per_active_step": float(qty.sum() / len(group)) if len(group) else np.nan,
            }
            for horizon in HORIZONS:
                row[f"avg_markout_{horizon}"] = _weighted_mean(
                    group[f"{markout_prefix}_{horizon}"].astype(float), qty
                )
                row[f"total_markout_{horizon}"] = (
                    row[f"avg_markout_{horizon}"] * row["fill_qty"]
                    if not pd.isna(row[f"avg_markout_{horizon}"])
                    else np.nan
                )
            rows.append(row)
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(
            ["dataset", "fill_model", "total_markout_1000", "fill_qty"],
            ascending=[True, True, False, False],
            inplace=True,
        )
    return out


def run(data_dir: Path, official_log: Path, out_dir: Path, order_size: int) -> None:
    hist_prices, hist_trades = _load_historical(data_dir)
    off_prices, off_trades = _load_official(official_log)
    panels = [
        _decision_panel(dataset="historical", prices=hist_prices, trades=hist_trades, order_size=order_size),
        _decision_panel(dataset="official_sellonly", prices=off_prices, trades=off_trades, order_size=order_size),
    ]
    panel = pd.concat(panels, ignore_index=True)
    summary = _summarize(panel)
    out_dir.mkdir(parents=True, exist_ok=True)
    panel_path = out_dir / "mark55_passive_opportunity_panel.csv"
    summary_path = out_dir / "mark55_passive_opportunity_summary.csv"
    panel.to_csv(panel_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(summary.to_string(index=False))
    print(f"wrote {panel_path}")
    print(f"wrote {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_OFFICIAL_LOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--order-size", type=int, default=5)
    args = parser.parse_args()
    run(args.data_dir, args.official_log, args.out_dir, args.order_size)


if __name__ == "__main__":
    main()
