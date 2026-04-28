"""Classify Round 4 Mark counterparty behavior.

This is the groundwork implied by the IMC hint: do not only ask whether a Mark
has positive markout. First classify how each Mark behaves:

- rhythm: periodic clips versus opportunistic arrivals;
- volume fingerprint: repeated sizes, basket-like flow, large blocks;
- role: taker-like, maker-like, or mixed;
- market state: momentum/contrarian and leading/lagging behavior;
- schedule relation: whether Mark flow tends to precede our existing schedule
  signals.

The output is descriptive evidence for later strategy design. It should not be
treated as a fitted strategy by itself.
"""

from __future__ import annotations

import argparse
import io
import json
from bisect import bisect_left
from pathlib import Path

import numpy as np
import pandas as pd

from src.scripts.round_4.audit_mark_conditioned_schedule import SCHEDULES


DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OUT_DIR = Path("outputs/round_4/mark_behavior")
DEFAULT_OFFICIAL_LOG = Path("/Users/abhinavgupta/Desktop/IMC/r4 Sim Results/sellonly/497595.log")

DAYS = (1, 2, 3)
PRODUCTS = (
    "HYDROGEL_PACK",
    "VELVETFRUIT_EXTRACT",
    "VEV_4000",
    "VEV_4500",
    "VEV_5000",
    "VEV_5100",
    "VEV_5200",
    "VEV_5300",
    "VEV_5400",
    "VEV_5500",
    "VEV_6000",
    "VEV_6500",
)
HORIZONS = (1_000, 5_000, 10_000, 30_000)


def _schedule_for(product: str, ts: int) -> tuple[int, int] | None:
    schedule = SCHEDULES.get(product)
    if schedule is None:
        return None
    selected = schedule[0]
    for candidate in schedule:
        if ts >= candidate[0]:
            selected = candidate
        else:
            break
    return selected[1], selected[2]


def _load_historical(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_frames = []
    trade_frames = []
    for day in DAYS:
        price = pd.read_csv(data_dir / f"prices_round_4_day_{day}.csv", sep=";")
        trade = pd.read_csv(data_dir / f"trades_round_4_day_{day}.csv", sep=";")
        price_frames.append(price)
        trade["day"] = day
        trade_frames.append(trade)
    prices = pd.concat(price_frames, ignore_index=True)
    trades = pd.concat(trade_frames, ignore_index=True)
    return prices, trades


def _load_official(log_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(log_path.read_text())
    prices = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    prices["day"] = 0
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
    trades = trades[(trades["buyer"] != "SUBMISSION") & (trades["seller"] != "SUBMISSION")].copy()
    trades["day"] = 0
    return prices, trades


def _book_features(prices: pd.DataFrame) -> pd.DataFrame:
    keep = prices[prices["product"].isin(PRODUCTS)].copy()
    keep.rename(
        columns={
            "bid_price_1": "bid",
            "ask_price_1": "ask",
            "bid_volume_1": "bid_vol",
            "ask_volume_1": "ask_vol",
            "mid_price": "mid",
        },
        inplace=True,
    )
    keep.sort_values(["day", "product", "timestamp"], inplace=True)
    keep["spread"] = keep["ask"] - keep["bid"]
    denom = keep["bid_vol"].fillna(0) + keep["ask_vol"].fillna(0)
    keep["imbalance"] = np.where(denom > 0, (keep["bid_vol"].fillna(0) - keep["ask_vol"].fillna(0)) / denom, np.nan)

    frames = []
    for (_day, _product), group in keep.groupby(["day", "product"], sort=False):
        group = group.copy()
        for horizon in HORIZONS:
            steps = horizon // 100
            group[f"mid_lag_{horizon}"] = group["mid"].shift(steps)
            group[f"mid_future_{horizon}"] = group["mid"].shift(-steps)
            group[f"bid_future_{horizon}"] = group["bid"].shift(-steps)
            group[f"ask_future_{horizon}"] = group["ask"].shift(-steps)
            group[f"mid_move_past_{horizon}"] = group["mid"] - group[f"mid_lag_{horizon}"]
            group[f"mid_move_future_{horizon}"] = group[f"mid_future_{horizon}"] - group["mid"]
        rolling = group["mid"].rolling(101, min_periods=10)
        group["roll10k_min"] = rolling.min()
        group["roll10k_max"] = rolling.max()
        width = group["roll10k_max"] - group["roll10k_min"]
        group["roll10k_pos"] = np.where(width > 0, (group["mid"] - group["roll10k_min"]) / width, np.nan)
        frames.append(group)
    return pd.concat(frames, ignore_index=True)


def _attach_book(trades: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    trades = trades[trades["symbol"].isin(PRODUCTS)].copy()
    trades["quantity"] = trades["quantity"].astype(int)
    trades["price"] = trades["price"].astype(float)
    merged = trades.merge(
        book,
        left_on=["day", "symbol", "timestamp"],
        right_on=["day", "product", "timestamp"],
        how="left",
    )
    # Infer aggressor from touch. If trade is at/above ask, buyer lifted. If at/below bid, seller hit.
    merged["aggressor_side"] = "unknown"
    merged.loc[pd.notna(merged["ask"]) & (merged["price"] >= merged["ask"]), "aggressor_side"] = "buy"
    merged.loc[pd.notna(merged["bid"]) & (merged["price"] <= merged["bid"]), "aggressor_side"] = "sell"
    between = merged["aggressor_side"].eq("unknown") & pd.notna(merged["mid"])
    merged.loc[between & (merged["price"] > merged["mid"]), "aggressor_side"] = "buy_mid"
    merged.loc[between & (merged["price"] < merged["mid"]), "aggressor_side"] = "sell_mid"
    return merged


def _actor_rows(trade_book: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for side, mark_col, other_col, side_sign in (
        ("buy", "buyer", "seller", 1.0),
        ("sell", "seller", "buyer", -1.0),
    ):
        part = trade_book.copy()
        part["mark"] = part[mark_col]
        part["other_mark"] = part[other_col]
        part["side"] = side
        part["side_sign"] = side_sign
        part["role"] = "unknown"
        if side == "buy":
            part.loc[part["aggressor_side"].isin(["buy", "buy_mid"]), "role"] = "taker"
            part.loc[part["aggressor_side"].isin(["sell", "sell_mid"]), "role"] = "maker"
        else:
            part.loc[part["aggressor_side"].isin(["sell", "sell_mid"]), "role"] = "taker"
            part.loc[part["aggressor_side"].isin(["buy", "buy_mid"]), "role"] = "maker"
        for horizon in HORIZONS:
            part[f"signed_past_move_{horizon}"] = part["side_sign"] * part[f"mid_move_past_{horizon}"]
            part[f"signed_future_move_{horizon}"] = part["side_sign"] * part[f"mid_move_future_{horizon}"]
            buy_edge = part[f"bid_future_{horizon}"] - part["price"]
            sell_edge = part["price"] - part[f"ask_future_{horizon}"]
            part[f"spread_edge_{horizon}"] = np.where(side == "buy", buy_edge, sell_edge)
        rows.append(part)
    actors = pd.concat(rows, ignore_index=True)
    actors.sort_values(["day", "timestamp", "product", "mark", "side"], inplace=True)
    return actors


def _top_value(series: pd.Series) -> tuple[float | int | None, float]:
    counts = series.dropna().value_counts()
    if counts.empty:
        return None, np.nan
    return counts.index[0], float(counts.iloc[0] / counts.sum())


def _role_summary(actors: pd.DataFrame) -> pd.DataFrame:
    records = []
    for keys, group in actors.groupby(["mark", "product", "side"], sort=False):
        mark, product, side = keys
        top_qty, top_qty_frac = _top_value(group["quantity"])
        role_counts = group["role"].value_counts(normalize=True)
        signed_future_days = {}
        positive_future_days = 0
        for day, day_group in group.groupby("day"):
            value = float(day_group["spread_edge_5000"].mean())
            signed_future_days[int(day)] = value
            if value > 0:
                positive_future_days += 1
        records.append(
            {
                "mark": mark,
                "product": product,
                "side": side,
                "rows": int(len(group)),
                "days": int(group["day"].nunique()),
                "qty": int(group["quantity"].sum()),
                "avg_qty": float(group["quantity"].mean()),
                "median_qty": float(group["quantity"].median()),
                "max_qty": int(group["quantity"].max()),
                "top_qty": top_qty,
                "top_qty_frac": top_qty_frac,
                "distinct_qty": int(group["quantity"].nunique()),
                "taker_rate": float(role_counts.get("taker", 0.0)),
                "maker_rate": float(role_counts.get("maker", 0.0)),
                "unknown_role_rate": float(role_counts.get("unknown", 0.0)),
                "avg_spread": float(group["spread"].mean()),
                "avg_imbalance": float(group["imbalance"].mean()),
                "avg_roll10k_pos": float(group["roll10k_pos"].mean()),
                "signed_past_1k": float(group["signed_past_move_1000"].mean()),
                "signed_past_5k": float(group["signed_past_move_5000"].mean()),
                "signed_future_1k": float(group["signed_future_move_1000"].mean()),
                "signed_future_5k": float(group["signed_future_move_5000"].mean()),
                "spread_edge_1k": float(group["spread_edge_1000"].mean()),
                "spread_edge_5k": float(group["spread_edge_5000"].mean()),
                "spread_edge_10k": float(group["spread_edge_10000"].mean()),
                "positive_5k_edge_days": positive_future_days,
                **{f"day{day}_spread_edge_5k": signed_future_days.get(day, np.nan) for day in sorted(actors["day"].unique())},
            }
        )
    out = pd.DataFrame(records)
    if not out.empty:
        out.sort_values(["rows", "qty"], ascending=[False, False], inplace=True)
    return out


def _interval_summary(actors: pd.DataFrame) -> pd.DataFrame:
    records = []
    for keys, group in actors.groupby(["mark", "product", "side"], sort=False):
        dts = []
        for _day, day_group in group.groupby("day"):
            times = np.sort(day_group["timestamp"].to_numpy(dtype=int))
            if len(times) > 1:
                dts.extend(np.diff(times).tolist())
        if not dts:
            continue
        dt_series = pd.Series(dts)
        top_dt, top_dt_frac = _top_value(dt_series)
        mean_dt = float(dt_series.mean())
        std_dt = float(dt_series.std(ddof=0))
        records.append(
            {
                "mark": keys[0],
                "product": keys[1],
                "side": keys[2],
                "intervals": int(len(dt_series)),
                "mean_dt": mean_dt,
                "median_dt": float(dt_series.median()),
                "std_dt": std_dt,
                "cv_dt": std_dt / mean_dt if mean_dt else np.nan,
                "top_dt": top_dt,
                "top_dt_frac": top_dt_frac,
                "frac_100": float((dt_series == 100).mean()),
                "frac_1000_or_less": float((dt_series <= 1_000).mean()),
                "frac_5000_or_less": float((dt_series <= 5_000).mean()),
            }
        )
    out = pd.DataFrame(records)
    if not out.empty:
        out.sort_values(["top_dt_frac", "intervals"], ascending=[False, False], inplace=True)
    return out


def _mark_totals(actors: pd.DataFrame) -> pd.DataFrame:
    records = []
    for mark, group in actors.groupby("mark", sort=False):
        buy_qty = int(group.loc[group["side"].eq("buy"), "quantity"].sum())
        sell_qty = int(group.loc[group["side"].eq("sell"), "quantity"].sum())
        product_count = int(group["product"].nunique())
        role_counts = group["role"].value_counts(normalize=True)
        records.append(
            {
                "mark": mark,
                "rows": int(len(group)),
                "qty": int(group["quantity"].sum()),
                "buy_qty": buy_qty,
                "sell_qty": sell_qty,
                "buy_qty_frac": buy_qty / (buy_qty + sell_qty) if buy_qty + sell_qty else np.nan,
                "product_count": product_count,
                "taker_rate": float(role_counts.get("taker", 0.0)),
                "maker_rate": float(role_counts.get("maker", 0.0)),
                "avg_signed_future_5k": float(group["signed_future_move_5000"].mean()),
                "avg_spread_edge_5k": float(group["spread_edge_5000"].mean()),
            }
        )
    out = pd.DataFrame(records)
    if not out.empty:
        out.sort_values("qty", ascending=False, inplace=True)
    return out


def _schedule_events(book: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in book.itertuples(index=False):
        product = str(row.product)
        thresholds = _schedule_for(product, int(row.timestamp))
        if thresholds is None:
            continue
        buy, sell = thresholds
        if pd.notna(row.ask) and row.ask <= buy:
            rows.append({"day": int(row.day), "timestamp": int(row.timestamp), "product": product, "signal_side": "buy"})
        if pd.notna(row.bid) and row.bid >= sell:
            rows.append({"day": int(row.day), "timestamp": int(row.timestamp), "product": product, "signal_side": "sell"})
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["day", "product", "signal_side", "timestamp"], inplace=True)
    return out


def _next_signal_delta(schedule: pd.DataFrame, day: int, product: str, side: str, ts: int) -> int | None:
    group = schedule[
        (schedule["day"] == day)
        & (schedule["product"] == product)
        & (schedule["signal_side"] == side)
    ]
    if group.empty:
        return None
    times = group["timestamp"].to_numpy(dtype=int)
    idx = bisect_left(times, ts)
    if idx >= len(times):
        return None
    return int(times[idx] - ts)


def _schedule_lead_summary(actors: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    if schedule.empty:
        return pd.DataFrame()
    records = []
    compact = actors[actors["product"].isin(SCHEDULES)].copy()
    for keys, group in compact.groupby(["mark", "product", "side"], sort=False):
        deltas_same = []
        deltas_opp = []
        for row in group.itertuples(index=False):
            same = _next_signal_delta(schedule, int(row.day), str(row.product), str(row.side), int(row.timestamp))
            opp_side = "sell" if row.side == "buy" else "buy"
            opp = _next_signal_delta(schedule, int(row.day), str(row.product), opp_side, int(row.timestamp))
            if same is not None:
                deltas_same.append(same)
            if opp is not None:
                deltas_opp.append(opp)
        if not deltas_same and not deltas_opp:
            continue
        same_arr = np.asarray(deltas_same) if deltas_same else np.array([])
        opp_arr = np.asarray(deltas_opp) if deltas_opp else np.array([])
        records.append(
            {
                "mark": keys[0],
                "product": keys[1],
                "side": keys[2],
                "rows": int(len(group)),
                "same_signal_n": int(len(same_arr)),
                "same_signal_within_1k": float(np.mean(same_arr <= 1_000)) if len(same_arr) else np.nan,
                "same_signal_within_5k": float(np.mean(same_arr <= 5_000)) if len(same_arr) else np.nan,
                "median_to_same_signal": float(np.median(same_arr)) if len(same_arr) else np.nan,
                "opp_signal_n": int(len(opp_arr)),
                "opp_signal_within_1k": float(np.mean(opp_arr <= 1_000)) if len(opp_arr) else np.nan,
                "opp_signal_within_5k": float(np.mean(opp_arr <= 5_000)) if len(opp_arr) else np.nan,
                "median_to_opp_signal": float(np.median(opp_arr)) if len(opp_arr) else np.nan,
            }
        )
    out = pd.DataFrame(records)
    if not out.empty:
        out.sort_values(["same_signal_within_5k", "rows"], ascending=[False, False], inplace=True)
    return out


def _behavior_labels(role: pd.DataFrame, intervals: pd.DataFrame) -> pd.DataFrame:
    if role.empty:
        return pd.DataFrame()
    interval_cols = intervals[
        ["mark", "product", "side", "top_dt", "top_dt_frac", "cv_dt", "frac_1000_or_less"]
    ] if not intervals.empty else pd.DataFrame(columns=["mark", "product", "side"])
    merged = role.merge(interval_cols, on=["mark", "product", "side"], how="left")
    labels = []
    for row in merged.itertuples(index=False):
        tags = []
        if row.taker_rate >= 0.65:
            tags.append("taker_like")
        elif row.maker_rate >= 0.65:
            tags.append("maker_like")
        else:
            tags.append("mixed_role")
        if pd.notna(row.top_qty_frac) and row.top_qty_frac >= 0.45:
            tags.append("clip_size_repeater")
        if pd.notna(row.top_dt_frac) and row.top_dt_frac >= 0.35:
            tags.append("rhythmic")
        if row.signed_past_5k > 2.0:
            tags.append("momentum_arrival")
        elif row.signed_past_5k < -2.0:
            tags.append("contrarian_arrival")
        if row.spread_edge_5k > 1.0 and row.positive_5k_edge_days >= min(3, row.days):
            tags.append("informed_after_spread")
        elif row.spread_edge_5k < -1.0:
            tags.append("adverse_after_spread")
        labels.append(",".join(tags))
    merged["behavior_tags"] = labels
    merged.sort_values(["rows", "qty"], ascending=[False, False], inplace=True)
    return merged


def _basket_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    clean = trades[trades["symbol"].isin(PRODUCTS)].copy()
    for keys, group in clean.groupby(["day", "timestamp", "buyer", "seller"], sort=False):
        day, ts, buyer, seller = keys
        products = tuple(sorted(str(p) for p in group["symbol"].unique()))
        product_set = "|".join(products)
        total_qty = int(group["quantity"].sum())
        component_rows = int(len(group))
        for mark, side, counterparty in ((buyer, "buy", seller), (seller, "sell", buyer)):
            rows.append(
                {
                    "day": int(day),
                    "timestamp": int(ts),
                    "mark": mark,
                    "side": side,
                    "counterparty": counterparty,
                    "component_rows": component_rows,
                    "product_count": len(products),
                    "product_set": product_set,
                    "total_qty": total_qty,
                }
            )
    clusters = pd.DataFrame(rows)
    if clusters.empty:
        return clusters
    records = []
    for keys, group in clusters.groupby(["mark", "side", "counterparty", "product_set"], sort=False):
        dts = []
        for _day, day_group in group.groupby("day"):
            times = np.sort(day_group["timestamp"].to_numpy(dtype=int))
            if len(times) > 1:
                dts.extend(np.diff(times).tolist())
        top_dt = None
        top_dt_frac = np.nan
        if dts:
            top_dt, top_dt_frac = _top_value(pd.Series(dts))
        top_qty, top_qty_frac = _top_value(group["total_qty"])
        records.append(
            {
                "mark": keys[0],
                "side": keys[1],
                "counterparty": keys[2],
                "product_set": keys[3],
                "clusters": int(len(group)),
                "days": int(group["day"].nunique()),
                "component_rows": int(group["component_rows"].sum()),
                "avg_product_count": float(group["product_count"].mean()),
                "total_qty": int(group["total_qty"].sum()),
                "avg_total_qty": float(group["total_qty"].mean()),
                "top_total_qty": top_qty,
                "top_total_qty_frac": top_qty_frac,
                "median_dt": float(np.median(dts)) if dts else np.nan,
                "top_dt": top_dt,
                "top_dt_frac": top_dt_frac,
                "first_ts": int(group["timestamp"].min()),
                "last_ts": int(group["timestamp"].max()),
            }
        )
    out = pd.DataFrame(records)
    out.sort_values(["component_rows", "clusters", "total_qty"], ascending=[False, False, False], inplace=True)
    return out


def _write_outputs(prefix: str, out_dir: Path, prices: pd.DataFrame, trades: pd.DataFrame) -> dict[str, pd.DataFrame]:
    book = _book_features(prices)
    trade_book = _attach_book(trades, book)
    actors = _actor_rows(trade_book)
    role = _role_summary(actors)
    intervals = _interval_summary(actors)
    totals = _mark_totals(actors)
    schedule = _schedule_events(book)
    schedule_lead = _schedule_lead_summary(actors, schedule)
    labels = _behavior_labels(role, intervals)
    baskets = _basket_summary(trades)

    frames = {
        "actor_events": actors,
        "mark_totals": totals,
        "role_summary": role,
        "interval_summary": intervals,
        "schedule_lead_summary": schedule_lead,
        "behavior_labels": labels,
        "basket_summary": baskets,
    }
    for name, frame in frames.items():
        frame.to_csv(out_dir / f"{prefix}_{name}.csv", index=False)
    return frames


def _print_table(title: str, frame: pd.DataFrame, columns: list[str], n: int = 20) -> None:
    print(f"\n=== {title} ===")
    if frame.empty:
        print("(none)")
        return
    print(frame.loc[:, columns].head(n).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_OFFICIAL_LOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--skip-official", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    hist_prices, hist_trades = _load_historical(args.data_dir)
    hist = _write_outputs("historical", args.out_dir, hist_prices, hist_trades)

    print(f"historical_actor_rows={len(hist['actor_events']):,}")
    print(f"output_dir={args.out_dir.resolve()}")
    _print_table(
        "Historical Mark totals",
        hist["mark_totals"],
        ["mark", "rows", "qty", "buy_qty_frac", "product_count", "taker_rate", "maker_rate", "avg_spread_edge_5k"],
    )
    _print_table(
        "Historical behavior labels",
        hist["behavior_labels"],
        [
            "mark",
            "product",
            "side",
            "rows",
            "qty",
            "taker_rate",
            "maker_rate",
            "top_qty",
            "top_qty_frac",
            "top_dt",
            "top_dt_frac",
            "spread_edge_5k",
            "positive_5k_edge_days",
            "behavior_tags",
        ],
    )
    _print_table(
        "Historical rhythmic cells",
        hist["interval_summary"],
        ["mark", "product", "side", "intervals", "median_dt", "top_dt", "top_dt_frac", "cv_dt", "frac_1000_or_less"],
    )
    _print_table(
        "Historical basket/program clusters",
        hist["basket_summary"],
        [
            "mark",
            "side",
            "counterparty",
            "product_set",
            "clusters",
            "days",
            "component_rows",
            "avg_product_count",
            "total_qty",
            "top_total_qty",
            "top_total_qty_frac",
            "median_dt",
        ],
    )

    if not args.skip_official and args.official_log.exists():
        off_prices, off_trades = _load_official(args.official_log)
        official = _write_outputs("official_sellonly", args.out_dir, off_prices, off_trades)
        print(f"\nofficial_actor_rows={len(official['actor_events']):,}")
        _print_table(
            "Official 100k Mark totals",
            official["mark_totals"],
            ["mark", "rows", "qty", "buy_qty_frac", "product_count", "taker_rate", "maker_rate", "avg_spread_edge_5k"],
        )
        _print_table(
            "Official behavior labels",
            official["behavior_labels"],
            [
                "mark",
                "product",
                "side",
                "rows",
                "qty",
                "taker_rate",
                "maker_rate",
                "top_qty",
                "top_qty_frac",
                "top_dt",
                "top_dt_frac",
                "spread_edge_5k",
                "behavior_tags",
            ],
        )
        _print_table(
            "Official basket/program clusters",
            official["basket_summary"],
            [
                "mark",
                "side",
                "counterparty",
                "product_set",
                "clusters",
                "days",
                "component_rows",
                "avg_product_count",
                "total_qty",
                "top_total_qty",
                "top_total_qty_frac",
                "median_dt",
            ],
        )


if __name__ == "__main__":
    main()
