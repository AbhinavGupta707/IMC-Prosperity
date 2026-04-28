"""Analyze official Round 4 simulator logs.

The official result `.log` file is a JSON envelope with:
  - activitiesLog: semicolon CSV of book snapshots and per-product PnL
  - tradeHistory: public trades, including SUBMISSION fills

This script is intentionally diagnostic. It answers:
  - where each candidate's PnL came from;
  - when the strategy stopped trading;
  - whether the long flat region is capacity, thresholds, or no flow;
  - how much passive flow existed after the last fill;
  - whether VEV_5500 changes are doing only the expected thing.
"""
from __future__ import annotations

import argparse
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


PRODUCT_LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    "VEV_4000": 300,
    "VEV_4500": 300,
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
    "VEV_6000": 300,
    "VEV_6500": 300,
}

# The schedule in the current R4 candidates for the first 100k-tick probe.
SCHEDULES_100K = {
    "VELVETFRUIT_EXTRACT": [(0, 200, 40, 5246, 5272)],
    "VEV_4000": [(0, 300, 10, 1233, 1263)],
    "VEV_4500": [(0, 300, 20, 732, 766)],
    "VEV_5000": [(0, 300, 40, 255, 270)],
    "VEV_5100": [(0, 300, 40, 165, 179)],
    "VEV_5200": [(0, 300, 40, 92, 106)],
    "VEV_5300": [(0, 300, 20, 45, 52), (50000, 300, 40, 45, 52)],
    "VEV_5400": [(0, 300, 40, 13, 17)],
    "VEV_5500": [(0, 300, 40, 6, 8)],
}


@dataclass(frozen=True)
class OfficialRun:
    name: str
    path: Path
    activities: pd.DataFrame
    trades: pd.DataFrame


def _candidate_name(path: Path) -> str:
    parent = path.parent.name
    if parent and parent not in {".", "extracted"}:
        return parent
    return path.stem


def _iter_logs(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.suffix == ".log":
            yield root
        return
    yield from sorted(root.rglob("*.log"))


def load_run(path: Path) -> OfficialRun:
    payload = json.loads(path.read_text())
    activities = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(
            columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"]
        )
    return OfficialRun(
        name=_candidate_name(path),
        path=path,
        activities=activities,
        trades=trades,
    )


def _submission_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    out = trades[
        (trades["buyer"] == "SUBMISSION") | (trades["seller"] == "SUBMISSION")
    ].copy()
    if out.empty:
        return out
    out["signed_qty"] = out.apply(
        lambda r: int(r["quantity"])
        if r["buyer"] == "SUBMISSION"
        else -int(r["quantity"]),
        axis=1,
    )
    out["cash"] = out.apply(
        lambda r: -float(r["price"]) * int(r["quantity"])
        if r["buyer"] == "SUBMISSION"
        else float(r["price"]) * int(r["quantity"]),
        axis=1,
    )
    return out.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _total_pnl_series(activities: pd.DataFrame) -> pd.Series:
    return activities.groupby("timestamp")["profit_and_loss"].sum().sort_index()


def _pnl_timing(series: pd.Series) -> dict[str, float | int | None]:
    final = float(series.iloc[-1])
    out: dict[str, float | int | None] = {
        "final": round(final, 2),
        "min": round(float(series.min()), 2),
        "max": round(float(series.max()), 2),
        "end_ts": int(series.index[-1]),
    }
    for frac in (0.5, 0.8, 0.9, 0.95, 0.99):
        hits = series.index[series >= final * frac]
        out[f"ts_{int(frac * 100)}pct_final"] = int(hits[0]) if len(hits) else None
    return out


def _positions_by_timestamp(run: OfficialRun) -> pd.DataFrame:
    timestamps = sorted(run.activities["timestamp"].unique())
    products = sorted(run.activities["product"].unique())
    positions = pd.DataFrame(0, index=timestamps, columns=products, dtype=int)
    own = _submission_trades(run.trades)
    for symbol, group in own.groupby("symbol"):
        if symbol not in positions.columns:
            continue
        increments = pd.Series(0, index=timestamps, dtype=int)
        for row in group.itertuples(index=False):
            increments.loc[int(row.timestamp)] += int(row.signed_qty)
        positions[symbol] = increments.cumsum()
    return positions


def _position_summary(run: OfficialRun) -> pd.DataFrame:
    own = _submission_trades(run.trades)
    rows = []
    for symbol, group in own.groupby("symbol"):
        pos = 0
        cash = 0.0
        first_limit_ts = None
        first_trade_ts = None
        last_trade_ts = None
        max_abs_pos = 0
        limit = PRODUCT_LIMITS.get(symbol)
        for row in group.sort_values("timestamp").itertuples(index=False):
            if first_trade_ts is None:
                first_trade_ts = int(row.timestamp)
            pos += int(row.signed_qty)
            cash += float(row.cash)
            max_abs_pos = max(max_abs_pos, abs(pos))
            last_trade_ts = int(row.timestamp)
            if limit is not None and first_limit_ts is None and abs(pos) >= limit:
                first_limit_ts = int(row.timestamp)
        rows.append(
            {
                "product": symbol,
                "final_pos": pos,
                "cash": round(cash, 2),
                "sub_rows": len(group),
                "sub_abs_qty": int(group["quantity"].sum()),
                "first_sub_ts": first_trade_ts,
                "first_limit_ts": first_limit_ts,
                "last_sub_ts": last_trade_ts,
                "max_abs_pos": max_abs_pos,
            }
        )
    return pd.DataFrame(rows).sort_values("product")


def _schedule_for(product: str, timestamp: int) -> tuple[int, int, int, int] | None:
    schedule = SCHEDULES_100K.get(product)
    if not schedule:
        return None
    selected = schedule[0]
    for candidate in schedule:
        if timestamp >= candidate[0]:
            selected = candidate
    _, limit, max_order, buy, sell = selected
    return limit, max_order, buy, sell


def _no_trade_band_summary(run: OfficialRun, start_ts: int) -> pd.DataFrame:
    positions = _positions_by_timestamp(run)
    rows = []
    for product in sorted(SCHEDULES_100K):
        product_rows = run.activities[
            (run.activities["product"] == product)
            & (run.activities["timestamp"] >= start_ts)
        ]
        buy_with_capacity = buy_blocked = sell_with_capacity = sell_blocked = 0
        for row in product_rows.itertuples(index=False):
            config = _schedule_for(product, int(row.timestamp))
            if config is None:
                continue
            limit, _, buy, sell = config
            pos = int(positions.loc[int(row.timestamp), product])
            ask = getattr(row, "ask_price_1")
            bid = getattr(row, "bid_price_1")
            if pd.notna(ask) and ask <= buy:
                if pos < limit:
                    buy_with_capacity += 1
                else:
                    buy_blocked += 1
            if pd.notna(bid) and bid >= sell:
                if pos > -limit:
                    sell_with_capacity += 1
                else:
                    sell_blocked += 1
        rows.append(
            {
                "product": product,
                "pos_at_start": int(positions.loc[start_ts, product])
                if start_ts in positions.index
                else None,
                "pos_end": int(positions.iloc[-1][product]),
                "buy_signal_with_capacity": buy_with_capacity,
                "buy_signal_blocked": buy_blocked,
                "sell_signal_with_capacity": sell_with_capacity,
                "sell_signal_blocked": sell_blocked,
            }
        )
    return pd.DataFrame(rows)


def _blocked_schedule_signal_upper_bound(run: OfficialRun, start_ts: int) -> pd.DataFrame:
    positions = _positions_by_timestamp(run)
    mids = (
        run.activities.pivot(index="timestamp", columns="product", values="mid_price")
        .ffill()
        .sort_index()
    )
    rows = []
    for product in sorted(SCHEDULES_100K):
        product_rows = run.activities[
            (run.activities["product"] == product)
            & (run.activities["timestamp"] >= start_ts)
        ]
        for row in product_rows.itertuples(index=False):
            timestamp = int(row.timestamp)
            config = _schedule_for(product, timestamp)
            if config is None:
                continue
            limit, max_order, buy, sell = config
            pos = int(positions.loc[timestamp, product])
            bid = getattr(row, "bid_price_1")
            ask = getattr(row, "ask_price_1")
            bid_volume = abs(int(getattr(row, "bid_volume_1") or 0))
            ask_volume = abs(int(getattr(row, "ask_volume_1") or 0))
            if pd.notna(ask) and ask <= buy and pos >= limit:
                qty = min(max_order, ask_volume)
                record = {
                    "product": product,
                    "side": "buy_blocked_long_limit",
                    "timestamp": timestamp,
                    "qty": qty,
                    "edge_to_threshold": buy - float(ask),
                    "price": float(ask),
                }
                for horizon in (1000, 5000, 10000, 20000):
                    future_ts = timestamp + horizon
                    if future_ts in mids.index:
                        record[f"mo_{horizon}"] = float(
                            mids.loc[future_ts, product] - float(ask)
                        )
                record["mo_end"] = float(mids.iloc[-1][product] - float(ask))
                rows.append(record)
            if pd.notna(bid) and bid >= sell and pos <= -limit:
                qty = min(max_order, bid_volume)
                record = {
                    "product": product,
                    "side": "sell_blocked_short_limit",
                    "timestamp": timestamp,
                    "qty": qty,
                    "edge_to_threshold": float(bid) - sell,
                    "price": float(bid),
                }
                for horizon in (1000, 5000, 10000, 20000):
                    future_ts = timestamp + horizon
                    if future_ts in mids.index:
                        record[f"mo_{horizon}"] = float(
                            float(bid) - mids.loc[future_ts, product]
                        )
                record["mo_end"] = float(float(bid) - mids.iloc[-1][product])
                rows.append(record)

    blocked = pd.DataFrame(rows)
    if blocked.empty:
        return blocked

    def qty_weighted(group: pd.DataFrame, column: str) -> float | None:
        valid = group.dropna(subset=[column])
        qty = valid["qty"].sum()
        if qty <= 0:
            return None
        return round(float((valid[column] * valid["qty"]).sum() / qty), 3)

    grouped_rows = []
    for (product, side), group in blocked.groupby(["product", "side"]):
        record = {
            "product": product,
            "side": side,
            "events": len(group),
            "qty": int(group["qty"].sum()),
            "avg_edge_to_threshold": qty_weighted(group, "edge_to_threshold"),
        }
        for horizon in (1000, 5000, 10000, 20000):
            column = f"mo_{horizon}"
            record[f"qty_mo_{horizon}"] = qty_weighted(group, column)
            record[f"raw_pnl_{horizon}"] = round(
                float((group[column] * group["qty"]).sum()), 1
            )
        record["qty_mo_end"] = qty_weighted(group, "mo_end")
        record["raw_pnl_end"] = round(float((group["mo_end"] * group["qty"]).sum()), 1)
        grouped_rows.append(record)
    return pd.DataFrame(grouped_rows).sort_values(["side", "product"])


def _passive_opportunity(run: OfficialRun, start_ts: int) -> pd.DataFrame:
    if run.trades.empty:
        return pd.DataFrame()
    book = run.activities[
        ["timestamp", "product", "bid_price_1", "ask_price_1", "mid_price"]
    ].copy()
    merged = run.trades.merge(
        book.rename(columns={"product": "symbol"}),
        on=["timestamp", "symbol"],
        how="left",
    )
    non_submission = merged[
        (merged["buyer"] != "SUBMISSION") & (merged["seller"] != "SUBMISSION")
    ].copy()
    non_submission = non_submission[non_submission["timestamp"] >= start_ts].copy()
    if non_submission.empty:
        return pd.DataFrame()
    non_submission["aggressor_side"] = "unknown"
    non_submission.loc[
        non_submission["price"] >= non_submission["ask_price_1"], "aggressor_side"
    ] = "buy"
    non_submission.loc[
        non_submission["price"] <= non_submission["bid_price_1"], "aggressor_side"
    ] = "sell"
    non_submission = non_submission[non_submission["aggressor_side"] != "unknown"].copy()
    if non_submission.empty:
        return pd.DataFrame()

    for horizon in (1000, 5000, 10000, 20000):
        future = book[["timestamp", "product", "mid_price"]].copy()
        future["timestamp"] = future["timestamp"] - horizon
        non_submission = non_submission.merge(
            future.rename(
                columns={
                    "product": "symbol",
                    "mid_price": f"future_mid_{horizon}",
                }
            ),
            on=["timestamp", "symbol"],
            how="left",
        )
        col = f"passive_mo_{horizon}"
        non_submission[col] = pd.NA
        buyer_aggressed = non_submission["aggressor_side"] == "buy"
        seller_aggressed = non_submission["aggressor_side"] == "sell"
        # Passive side is the opposite of aggressor. If someone buys, we sell.
        non_submission.loc[buyer_aggressed, col] = (
            non_submission.loc[buyer_aggressed, "price"]
            - non_submission.loc[buyer_aggressed, f"future_mid_{horizon}"]
        )
        non_submission.loc[seller_aggressed, col] = (
            non_submission.loc[seller_aggressed, f"future_mid_{horizon}"]
            - non_submission.loc[seller_aggressed, "price"]
        )
        non_submission[col] = pd.to_numeric(non_submission[col], errors="coerce")

    grouped = non_submission.groupby(["symbol", "aggressor_side"]).agg(
        rows=("quantity", "count"),
        qty=("quantity", "sum"),
    )
    for horizon in (1000, 5000, 10000, 20000):
        col = f"passive_mo_{horizon}"
        grouped[f"qty_mo_{horizon}"] = non_submission.groupby(
            ["symbol", "aggressor_side"]
        ).apply(
            lambda g, c=col: round(float((g[c] * g["quantity"]).sum() / g["quantity"].sum()), 3)
            if g["quantity"].sum()
            else None,
            include_groups=False,
        )
        grouped[f"raw_pnl_{horizon}"] = non_submission.groupby(
            ["symbol", "aggressor_side"]
        ).apply(
            lambda g, c=col: round(float((g[c] * g["quantity"]).sum()), 1),
            include_groups=False,
        )
    return grouped.reset_index().sort_values("qty", ascending=False)


def _product_pnl_at_key_times(run: OfficialRun, key_times: list[int]) -> pd.DataFrame:
    wide = (
        run.activities.pivot(
            index="timestamp", columns="product", values="profit_and_loss"
        )
        .ffill()
        .fillna(0.0)
    )
    wide["TOTAL"] = wide.sum(axis=1)
    available = [t for t in key_times if t in wide.index]
    return wide.loc[available].round(1)


def print_run_report(run: OfficialRun) -> None:
    total = _total_pnl_series(run.activities)
    own = _submission_trades(run.trades)
    last_fill = int(own["timestamp"].max()) if not own.empty else None

    print("\n" + "=" * 96)
    print(f"{run.name}: {run.path}")
    print(f"Final PnL/timing: {_pnl_timing(total)}")
    print(
        f"tradeHistory rows={len(run.trades)} submission_rows={len(own)} "
        f"submission_abs_qty={int(own['quantity'].sum()) if not own.empty else 0} "
        f"last_submission_fill={last_fill}"
    )

    positions = _position_summary(run)
    if not positions.empty:
        print("\nSubmission position summary")
        print(positions.to_string(index=False))

    keys = [0, 5000, 10000, 20000, 30000, 40000, 42000, 50000]
    if last_fill is not None:
        keys.extend([last_fill, 60000, 70000, 80000, 90000, 99900])
    keys = sorted(set(keys))
    print("\nProduct PnL at key timestamps")
    print(_product_pnl_at_key_times(run, keys).to_string())

    if last_fill is not None and last_fill in total.index:
        print("\nSchedule threshold check after last fill")
        print(_no_trade_band_summary(run, last_fill).to_string(index=False))
        print("\nBlocked schedule-signal upper bound after last fill")
        blocked = _blocked_schedule_signal_upper_bound(run, last_fill)
        if blocked.empty:
            print("(no blocked threshold signals)")
        else:
            print(blocked.to_string(index=False))
        print("\nPassive-flow upper bound after last fill")
        passive = _passive_opportunity(run, last_fill)
        if passive.empty:
            print("(no passive non-submission touch prints)")
        else:
            print(passive.to_string(index=False))


def compare_vev5500(runs: list[OfficialRun]) -> None:
    rows = []
    for run in runs:
        final_by_product = (
            run.activities.sort_values("timestamp")
            .groupby("product")
            .tail(1)
            .set_index("product")["profit_and_loss"]
        )
        own = _submission_trades(run.trades)
        vev = own[own["symbol"] == "VEV_5500"] if not own.empty else own
        rows.append(
            {
                "candidate": run.name,
                "total_final": round(float(_total_pnl_series(run.activities).iloc[-1]), 2),
                "vev5500_pnl": round(float(final_by_product.get("VEV_5500", 0.0)), 2),
                "vev5500_pos": int(vev["signed_qty"].sum()) if not vev.empty else 0,
                "vev5500_abs_qty": int(vev["quantity"].sum()) if not vev.empty else 0,
                "vev5500_rows": len(vev),
            }
        )
    if rows:
        print("\n" + "=" * 96)
        print("VEV_5500 comparison")
        print(pd.DataFrame(rows).sort_values("candidate").to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Official .log files or directories containing extracted .log files.",
    )
    args = parser.parse_args()

    log_paths: list[Path] = []
    for path in args.paths:
        log_paths.extend(_iter_logs(path))
    runs = [load_run(path) for path in log_paths]
    if not runs:
        raise SystemExit("No .log files found.")

    for run in runs:
        print_run_report(run)
    compare_vev5500(runs)


if __name__ == "__main__":
    main()
