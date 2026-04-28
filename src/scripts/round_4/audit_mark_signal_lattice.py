"""Broad Round 4 Mark signal-lattice audit.

This script is intentionally wider than the earlier Mark22/Mark55 probes. It
asks: across every Mark, product, side, role, and sequence pair, which patterns
are visible on all three historical days, which survive basic controls, and
which are large enough to be strategy-relevant after spread/capacity costs?

It is descriptive research, not a fitted trader.
"""

from __future__ import annotations

import argparse
import bisect
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OUT_DIR = Path("outputs/round_4/mark_signal_lattice")
DEFAULT_OFFICIAL_LOG = Path("r4 Sim Results/sellonly/497595.log")

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


def load_historical(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = []
    trades = []
    for day in DAYS:
        price = pd.read_csv(data_dir / f"prices_round_4_day_{day}.csv", sep=";")
        trade = pd.read_csv(data_dir / f"trades_round_4_day_{day}.csv", sep=";")
        price["day"] = day
        trade["day"] = day
        prices.append(price)
        trades.append(trade)
    return pd.concat(prices, ignore_index=True), pd.concat(trades, ignore_index=True)


def load_official(log_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(log_path.read_text())
    prices = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    prices["day"] = 0
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
    trades = trades[(trades["buyer"] != "SUBMISSION") & (trades["seller"] != "SUBMISSION")].copy()
    trades["day"] = 0
    return prices, trades


def book_features(prices: pd.DataFrame) -> pd.DataFrame:
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
    depth = keep["bid_vol"].fillna(0) + keep["ask_vol"].fillna(0)
    keep["imbalance"] = np.where(depth > 0, (keep["bid_vol"].fillna(0) - keep["ask_vol"].fillna(0)) / depth, np.nan)

    frames = []
    for (_day, _product), group in keep.groupby(["day", "product"], sort=False):
        group = group.copy()
        for horizon in HORIZONS:
            steps = horizon // 100
            group[f"mid_future_{horizon}"] = group["mid"].shift(-steps)
            group[f"bid_future_{horizon}"] = group["bid"].shift(-steps)
            group[f"ask_future_{horizon}"] = group["ask"].shift(-steps)
            group[f"mid_lag_{horizon}"] = group["mid"].shift(steps)
            group[f"mid_move_future_{horizon}"] = group[f"mid_future_{horizon}"] - group["mid"]
            group[f"mid_move_past_{horizon}"] = group["mid"] - group[f"mid_lag_{horizon}"]
        rolling = group["mid"].rolling(101, min_periods=10)
        group["roll10k_min"] = rolling.min()
        group["roll10k_max"] = rolling.max()
        width = group["roll10k_max"] - group["roll10k_min"]
        group["roll10k_pos"] = np.where(width > 0, (group["mid"] - group["roll10k_min"]) / width, np.nan)
        frames.append(group)
    return pd.concat(frames, ignore_index=True)


def attach_book(trades: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    trades = trades[trades["symbol"].isin(PRODUCTS)].copy()
    trades["quantity"] = trades["quantity"].astype(int)
    trades["price"] = trades["price"].astype(float)
    merged = trades.merge(
        book,
        left_on=["day", "symbol", "timestamp"],
        right_on=["day", "product", "timestamp"],
        how="left",
    )
    merged["aggressor_side"] = "unknown"
    merged.loc[pd.notna(merged["ask"]) & (merged["price"] >= merged["ask"]), "aggressor_side"] = "buy"
    merged.loc[pd.notna(merged["bid"]) & (merged["price"] <= merged["bid"]), "aggressor_side"] = "sell"
    between = merged["aggressor_side"].eq("unknown") & pd.notna(merged["mid"])
    merged.loc[between & (merged["price"] > merged["mid"]), "aggressor_side"] = "buy_mid"
    merged.loc[between & (merged["price"] < merged["mid"]), "aggressor_side"] = "sell_mid"
    return merged


def actor_rows(trade_book: pd.DataFrame) -> pd.DataFrame:
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
            part[f"signed_past_mid_{horizon}"] = side_sign * part[f"mid_move_past_{horizon}"]
            part[f"signed_future_mid_{horizon}"] = side_sign * part[f"mid_move_future_{horizon}"]
            buy_edge = part[f"bid_future_{horizon}"] - part["price"]
            sell_edge = part["price"] - part[f"ask_future_{horizon}"]
            part[f"follow_spread_edge_{horizon}"] = np.where(side == "buy", buy_edge, sell_edge)
            part[f"passive_maker_edge_{horizon}"] = -part[f"follow_spread_edge_{horizon}"]
        rows.append(part)
    actors = pd.concat(rows, ignore_index=True)
    actors = actors[actors["mark"].astype(str).str.startswith("Mark ")].copy()
    actors.sort_values(["day", "timestamp", "product", "side", "mark"], inplace=True)
    actors["event_code"] = actors["mark"] + "|" + actors["product"] + "|" + actors["side"]
    return actors


def event_edges(actors: pd.DataFrame) -> pd.DataFrame:
    baseline = {}
    for (product, side), group in actors.groupby(["product", "side"]):
        baseline[(product, side)] = {
            f"baseline_follow_{h}": float(group[f"follow_spread_edge_{h}"].mean()) for h in HORIZONS
        }

    records = []
    group_cols = ["mark", "product", "side", "role"]
    for keys, group in actors.groupby(group_cols, dropna=False):
        if len(group) < 8:
            continue
        rec = dict(zip(group_cols, keys, strict=False))
        rec["rows"] = int(len(group))
        rec["days"] = int(group["day"].nunique())
        rec["qty"] = int(group["quantity"].sum())
        rec["avg_qty"] = float(group["quantity"].mean())
        rec["avg_spread"] = float(group["spread"].mean())
        rec["avg_roll10k_pos"] = float(group["roll10k_pos"].mean())
        rec["avg_imbalance"] = float(group["imbalance"].mean())
        rec["taker_rate"] = float((group["role"] == "taker").mean())
        product_side_base = baseline.get((rec["product"], rec["side"]), {})
        for horizon in HORIZONS:
            follow = group[f"follow_spread_edge_{horizon}"].mean()
            maker = group[f"passive_maker_edge_{horizon}"].mean()
            signed_mid = group[f"signed_future_mid_{horizon}"].mean()
            rec[f"follow_edge_{horizon}"] = float(follow)
            rec[f"passive_maker_edge_{horizon}"] = float(maker)
            rec[f"signed_mid_{horizon}"] = float(signed_mid)
            rec[f"uplift_vs_same_product_side_{horizon}"] = float(follow - product_side_base.get(f"baseline_follow_{horizon}", np.nan))
            for day in sorted(group["day"].unique()):
                day_group = group[group["day"] == day]
                rec[f"day{day}_follow_edge_{horizon}"] = float(day_group[f"follow_spread_edge_{horizon}"].mean())
                rec[f"day{day}_n"] = int(len(day_group))
        edge_days = []
        maker_days = []
        for day in DAYS:
            col = f"day{day}_follow_edge_5000"
            if col in rec and not np.isnan(rec[col]):
                edge_days.append(np.sign(rec[col]))
                maker_days.append(np.sign(-rec[col]))
        rec["follow_positive_days_5k"] = int(sum(v > 0 for v in edge_days))
        rec["follow_negative_days_5k"] = int(sum(v < 0 for v in edge_days))
        rec["maker_positive_days_5k"] = int(sum(v > 0 for v in maker_days))
        records.append(rec)
    out = pd.DataFrame(records)
    if out.empty:
        return out
    out["abs_follow_edge_5k"] = out["follow_edge_5000"].abs()
    out["abs_maker_edge_5k"] = out["passive_maker_edge_5000"].abs()
    out.sort_values(["days", "rows", "abs_maker_edge_5k"], ascending=[False, False, False], inplace=True)
    return out


def same_timestamp_signatures(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    clean = trades[trades["symbol"].isin(PRODUCTS)].copy()
    for (day, timestamp, buyer, seller), group in clean.groupby(["day", "timestamp", "buyer", "seller"], sort=False):
        symbols = tuple(sorted(group["symbol"].astype(str).unique()))
        for mark, side, counterparty in ((buyer, "buy", seller), (seller, "sell", buyer)):
            if not str(mark).startswith("Mark "):
                continue
            rows.append(
                {
                    "day": int(day),
                    "timestamp": int(timestamp),
                    "mark": str(mark),
                    "side": side,
                    "counterparty": str(counterparty),
                    "product_set": "|".join(symbols),
                    "product_count": len(symbols),
                    "component_rows": int(len(group)),
                    "qty": int(group["quantity"].sum()),
                }
            )
    sigs = pd.DataFrame(rows)
    if sigs.empty:
        return sigs
    records = []
    for keys, group in sigs.groupby(["mark", "side", "counterparty", "product_set"]):
        dts = []
        for _day, day_group in group.groupby("day"):
            times = np.sort(day_group["timestamp"].to_numpy(dtype=int))
            if len(times) > 1:
                dts.extend(np.diff(times).tolist())
        records.append(
            {
                "mark": keys[0],
                "side": keys[1],
                "counterparty": keys[2],
                "product_set": keys[3],
                "clusters": int(len(group)),
                "days": int(group["day"].nunique()),
                "component_rows": int(group["component_rows"].sum()),
                "qty": int(group["qty"].sum()),
                "avg_product_count": float(group["product_count"].mean()),
                "median_dt": float(np.median(dts)) if dts else np.nan,
                "p10_dt": float(np.quantile(dts, 0.1)) if dts else np.nan,
                "p90_dt": float(np.quantile(dts, 0.9)) if dts else np.nan,
                "first_ts": int(group["timestamp"].min()),
                "last_ts": int(group["timestamp"].max()),
            }
        )
    out = pd.DataFrame(records)
    out.sort_values(["days", "component_rows", "clusters"], ascending=[False, False, False], inplace=True)
    return out


def _target_times_by_day(actors: pd.DataFrame) -> dict[tuple[str, int], list[int]]:
    out: dict[tuple[str, int], list[int]] = {}
    for (code, day), group in actors.groupby(["event_code", "day"]):
        out[(code, int(day))] = sorted(set(group["timestamp"].astype(int).tolist()))
    return out


def _window_hit(times: list[int], start: int, horizon: int) -> bool:
    idx = bisect.bisect_right(times, start)
    return idx < len(times) and times[idx] <= start + horizon


def sequence_lifts(actors: pd.DataFrame, book: pd.DataFrame, min_trigger_rows: int = 20, min_target_rows: int = 20) -> pd.DataFrame:
    trigger_counts = actors["event_code"].value_counts()
    trigger_codes = trigger_counts[trigger_counts >= min_trigger_rows].index.tolist()
    target_codes = trigger_codes.copy()
    times_by_day = _target_times_by_day(actors)
    timeline_by_day = {
        int(day): sorted(set(group["timestamp"].astype(int).tolist())) for day, group in book.groupby("day")
    }
    rows = []
    for trigger_code in trigger_codes:
        triggers = actors[actors["event_code"] == trigger_code]
        trigger_mark, trigger_product, trigger_side = trigger_code.split("|")
        for target_code in target_codes:
            if target_code == trigger_code:
                continue
            target_mark, target_product, target_side = target_code.split("|")
            # Keep the search broad, but avoid huge tables of irrelevant cross-asset coincidences.
            same_family = (
                trigger_product == target_product
                or (trigger_product.startswith("VEV_") and target_product.startswith("VEV_"))
                or {trigger_product, target_product} <= {"VELVETFRUIT_EXTRACT", "VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500"}
                or trigger_product == "HYDROGEL_PACK"
                or target_product == "HYDROGEL_PACK"
            )
            if not same_family:
                continue
            if trigger_counts.get(target_code, 0) < min_target_rows:
                continue
            for horizon in HORIZONS:
                n = 0
                hits = 0
                day_parts = {}
                base_parts = {}
                for day, day_triggers in triggers.groupby("day"):
                    day = int(day)
                    target_times = times_by_day.get((target_code, day), [])
                    if not target_times:
                        continue
                    day_n = 0
                    day_hits = 0
                    for ts in day_triggers["timestamp"].astype(int):
                        day_n += 1
                        day_hits += int(_window_hit(target_times, int(ts), horizon))
                    if day_n == 0:
                        continue
                    timeline = timeline_by_day.get(day, [])
                    base_hits = sum(int(_window_hit(target_times, int(ts), horizon)) for ts in timeline)
                    base_rate = base_hits / len(timeline) if timeline else np.nan
                    rate = day_hits / day_n
                    day_parts[day] = rate
                    base_parts[day] = base_rate
                    n += day_n
                    hits += day_hits
                if n < min_trigger_rows:
                    continue
                weighted_base = np.nanmean(list(base_parts.values())) if base_parts else np.nan
                active_rate = hits / n
                diff = active_rate - weighted_base
                lift = active_rate / weighted_base if weighted_base and weighted_base > 0 else np.nan
                if np.isnan(lift):
                    continue
                rows.append(
                    {
                        "trigger_code": trigger_code,
                        "trigger_mark": trigger_mark,
                        "trigger_product": trigger_product,
                        "trigger_side": trigger_side,
                        "target_code": target_code,
                        "target_mark": target_mark,
                        "target_product": target_product,
                        "target_side": target_side,
                        "horizon": horizon,
                        "trigger_rows": int(n),
                        "hit_rate": float(active_rate),
                        "baseline_rate": float(weighted_base),
                        "diff_rate": float(diff),
                        "lift": float(lift),
                        "days_seen": int(len(day_parts)),
                        **{f"day{day}_hit_rate": day_parts.get(day, np.nan) for day in DAYS},
                        **{f"day{day}_baseline_rate": base_parts.get(day, np.nan) for day in DAYS},
                    }
                )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out.sort_values(["days_seen", "diff_rate", "lift", "trigger_rows"], ascending=[False, False, False, False], inplace=True)
    return out


def mark_state_bins(actors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in actors.groupby(["mark", "product", "side"]):
        if len(group) < 10:
            continue
        q = group["roll10k_pos"]
        rows.append(
            {
                "mark": keys[0],
                "product": keys[1],
                "side": keys[2],
                "rows": int(len(group)),
                "qty": int(group["quantity"].sum()),
                "roll10k_pos_mean": float(q.mean()),
                "roll10k_pos_p25": float(q.quantile(0.25)),
                "roll10k_pos_p50": float(q.quantile(0.50)),
                "roll10k_pos_p75": float(q.quantile(0.75)),
                "spread_mean": float(group["spread"].mean()),
                "imbalance_mean": float(group["imbalance"].mean()),
                "past_mid_5k": float(group["signed_past_mid_5000"].mean()),
                "future_mid_5k": float(group["signed_future_mid_5000"].mean()),
                "follow_edge_5k": float(group["follow_spread_edge_5000"].mean()),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out.sort_values(["rows", "qty"], ascending=[False, False], inplace=True)
    return out


def run(prefix: str, prices: pd.DataFrame, trades: pd.DataFrame, out_dir: Path) -> dict[str, pd.DataFrame]:
    book = book_features(prices)
    tb = attach_book(trades, book)
    actors = actor_rows(tb)
    edges = event_edges(actors)
    sigs = same_timestamp_signatures(trades)
    seq = sequence_lifts(actors, book)
    states = mark_state_bins(actors)

    frames = {
        "actors": actors,
        "event_edges": edges,
        "same_timestamp_signatures": sigs,
        "sequence_lifts": seq,
        "mark_state_bins": states,
    }
    for name, frame in frames.items():
        frame.to_csv(out_dir / f"{prefix}_{name}.csv", index=False)
    return frames


def print_table(title: str, frame: pd.DataFrame, columns: list[str], n: int = 12) -> None:
    print(f"\n=== {title} ===")
    if frame.empty:
        print("(none)")
        return
    print(frame.loc[:, columns].head(n).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_OFFICIAL_LOG)
    parser.add_argument("--skip-official", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    prices, trades = load_historical(args.data_dir)
    hist = run("historical", prices, trades, args.out_dir)
    print(f"output_dir={args.out_dir.resolve()}")
    print(f"historical_actor_rows={len(hist['actors']):,}")

    robust_edges = hist["event_edges"][
        (hist["event_edges"]["days"] == 3)
        & (hist["event_edges"]["rows"] >= 20)
        & (
            (hist["event_edges"]["follow_positive_days_5k"] == 3)
            | (hist["event_edges"]["maker_positive_days_5k"] == 3)
        )
    ].copy()
    robust_edges["best_abs_edge_5k"] = np.maximum(
        robust_edges["follow_edge_5000"].abs(), robust_edges["passive_maker_edge_5000"].abs()
    )
    robust_edges.sort_values(["best_abs_edge_5k", "rows"], ascending=[False, False], inplace=True)
    robust_edges.to_csv(args.out_dir / "historical_robust_event_edges.csv", index=False)

    robust_seq = hist["sequence_lifts"][
        (hist["sequence_lifts"]["days_seen"] == 3)
        & (hist["sequence_lifts"]["trigger_rows"] >= 30)
        & (hist["sequence_lifts"]["diff_rate"] >= 0.10)
        & (hist["sequence_lifts"]["lift"] >= 1.25)
    ].copy()
    robust_seq.sort_values(["diff_rate", "lift", "trigger_rows"], ascending=[False, False, False], inplace=True)
    robust_seq.to_csv(args.out_dir / "historical_robust_sequence_lifts.csv", index=False)

    print_table(
        "Cross-day robust event edges",
        robust_edges,
        [
            "mark",
            "product",
            "side",
            "role",
            "rows",
            "qty",
            "follow_edge_5000",
            "passive_maker_edge_5000",
            "uplift_vs_same_product_side_5000",
            "day1_follow_edge_5000",
            "day2_follow_edge_5000",
            "day3_follow_edge_5000",
        ],
    )
    print_table(
        "Same-timestamp program signatures",
        hist["same_timestamp_signatures"],
        ["mark", "side", "counterparty", "product_set", "clusters", "days", "component_rows", "qty", "median_dt"],
    )
    print_table(
        "Cross-day robust sequence lifts",
        robust_seq,
        [
            "trigger_code",
            "target_code",
            "horizon",
            "trigger_rows",
            "hit_rate",
            "baseline_rate",
            "diff_rate",
            "lift",
            "day1_hit_rate",
            "day2_hit_rate",
            "day3_hit_rate",
        ],
    )
    print_table(
        "State dependency by Mark/product/side",
        hist["mark_state_bins"],
        [
            "mark",
            "product",
            "side",
            "rows",
            "roll10k_pos_mean",
            "roll10k_pos_p25",
            "roll10k_pos_p75",
            "past_mid_5k",
            "future_mid_5k",
            "follow_edge_5k",
        ],
    )

    if not args.skip_official and args.official_log.exists():
        off_prices, off_trades = load_official(args.official_log)
        off = run("official_sellonly", off_prices, off_trades, args.out_dir)
        print(f"\nofficial_actor_rows={len(off['actors']):,}")
        print_table(
            "Official event edges",
            off["event_edges"].sort_values(["rows", "qty"], ascending=[False, False]),
            [
                "mark",
                "product",
                "side",
                "role",
                "rows",
                "qty",
                "follow_edge_5000",
                "passive_maker_edge_5000",
                "uplift_vs_same_product_side_5000",
            ],
        )


if __name__ == "__main__":
    main()
