"""Audit whether Mark flow conditions existing R4 schedule signals.

The earlier counterparty tests asked whether Mark prints are good enough to
cross the spread as new standalone trades. They mostly are not. This script
asks the more relevant question for the current strategy:

    When the R3/R4 schedule already wants to trade, does recent Mark flow
    identify which schedule signals have better or worse forward edge?

It is intentionally an audit, not a parameter optimizer. The output is meant to
support decisions such as "size this existing schedule signal more/less after
Mark 67 buys VELVET" or "do not use Mark 22 flow to override VEV_5300 unless it
passes leave-one-day validation."
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OUT_DIR = Path("outputs/round_4/mark_conditioned")

DAYS = (1, 2, 3)
HORIZONS = (1_000, 5_000, 10_000, 30_000, 100_000)
WINDOWS = (1_000, 5_000, 10_000, 30_000)

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

# Current family of R4 schedules, using the t<100k schedule where applicable.
# The 100k official simulator cannot reveal later schedule changes, but the
# historical audit needs the full schedule because we validate across 1m days.
SCHEDULES = {
    "VELVETFRUIT_EXTRACT": [(0, 5246, 5272)],
    "VEV_4000": [(0, 1233, 1263)],
    "VEV_4500": [(0, 732, 766)],
    "VEV_5000": [(0, 255, 270), (100_000, 241, 273)],
    "VEV_5100": [(0, 165, 179), (150_000, 164, 183)],
    "VEV_5200": [(0, 92, 106), (300_000, 93, 105)],
    "VEV_5300": [(0, 45, 52), (50_000, 45, 52)],
    "VEV_5400": [(0, 13, 17), (100_000, 15, 18)],
    # Compare buy-disabled/sell-only behavior in a separate simulator upload.
    # Here we audit the schedule signal surface; sell threshold 7 is now also
    # reported through the VEV5500_sell7 feature in summary filters below.
    "VEV_5500": [(0, 6, 8)],
}


@dataclass(frozen=True)
class MarkFeature:
    label: str
    mark: str
    product: str | tuple[str, ...]
    side: str

    def products(self) -> tuple[str, ...]:
        if isinstance(self.product, str):
            return (self.product,)
        return self.product


FEATURES = (
    MarkFeature("m67_velvet_buy", "Mark 67", "VELVETFRUIT_EXTRACT", "buy"),
    MarkFeature("m49_velvet_sell", "Mark 49", "VELVETFRUIT_EXTRACT", "sell"),
    MarkFeature("m55_velvet_buy", "Mark 55", "VELVETFRUIT_EXTRACT", "buy"),
    MarkFeature("m55_velvet_sell", "Mark 55", "VELVETFRUIT_EXTRACT", "sell"),
    MarkFeature("m14_velvet_buy", "Mark 14", "VELVETFRUIT_EXTRACT", "buy"),
    MarkFeature("m22_velvet_sell", "Mark 22", "VELVETFRUIT_EXTRACT", "sell"),
    MarkFeature("m22_vev5200_sell", "Mark 22", "VEV_5200", "sell"),
    MarkFeature("m22_vev5300_sell", "Mark 22", "VEV_5300", "sell"),
    MarkFeature("m22_vev5400_sell", "Mark 22", "VEV_5400", "sell"),
    MarkFeature("m22_vev5500_sell", "Mark 22", "VEV_5500", "sell"),
    MarkFeature(
        "m22_otm_sell",
        "Mark 22",
        ("VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500"),
        "sell",
    ),
    MarkFeature("m14_hyd_buy", "Mark 14", "HYDROGEL_PACK", "buy"),
    MarkFeature("m38_hyd_sell", "Mark 38", "HYDROGEL_PACK", "sell"),
    MarkFeature("m22_hyd_buy", "Mark 22", "HYDROGEL_PACK", "buy"),
)


VELVET_FEATURES = {
    "m67_velvet_buy",
    "m49_velvet_sell",
    "m55_velvet_buy",
    "m55_velvet_sell",
    "m14_velvet_buy",
    "m22_velvet_sell",
}
VOUCHER_FEATURES = VELVET_FEATURES | {
    "m22_vev5200_sell",
    "m22_vev5300_sell",
    "m22_vev5400_sell",
    "m22_vev5500_sell",
    "m22_otm_sell",
}
HYD_FEATURES = {"m14_hyd_buy", "m38_hyd_sell", "m22_hyd_buy"}


def _features_for_product(product: str) -> tuple[MarkFeature, ...]:
    if product == "VELVETFRUIT_EXTRACT":
        labels = VELVET_FEATURES
    elif product == "HYDROGEL_PACK":
        labels = HYD_FEATURES
    elif product.startswith("VEV_"):
        labels = VOUCHER_FEATURES
    else:
        labels = set()
    return tuple(feature for feature in FEATURES if feature.label in labels)


def _read_price_files(data_dir: Path) -> pd.DataFrame:
    frames = []
    for day in DAYS:
        path = data_dir / f"prices_round_4_day_{day}.csv"
        frames.append(pd.read_csv(path, sep=";"))
    prices = pd.concat(frames, ignore_index=True)
    prices = prices[prices["product"].isin(PRODUCTS)].copy()
    prices.sort_values(["day", "product", "timestamp"], inplace=True)
    return prices


def _read_trade_files(data_dir: Path) -> pd.DataFrame:
    frames = []
    for day in DAYS:
        path = data_dir / f"trades_round_4_day_{day}.csv"
        frame = pd.read_csv(path, sep=";")
        frame["day"] = day
        frames.append(frame)
    trades = pd.concat(frames, ignore_index=True)
    trades = trades[trades["symbol"].isin(PRODUCTS)].copy()
    trades["quantity"] = trades["quantity"].astype(int)
    trades.sort_values(["day", "timestamp", "symbol"], inplace=True)
    return trades


def _schedule_for(product: str, ts: int) -> tuple[int, int] | None:
    schedule = SCHEDULES.get(product)
    if not schedule:
        return None
    selected = schedule[0]
    for candidate in schedule:
        if ts >= candidate[0]:
            selected = candidate
        else:
            break
    return selected[1], selected[2]


def _build_book_lookup(prices: pd.DataFrame) -> dict[tuple[int, str], pd.DataFrame]:
    out: dict[tuple[int, str], pd.DataFrame] = {}
    for (day, product), group in prices.groupby(["day", "product"], sort=False):
        out[(int(day), str(product))] = group.sort_values("timestamp").reset_index(drop=True)
    return out


def _future_value(series: pd.DataFrame, ts: int, col: str) -> float | None:
    timestamps = series["timestamp"].to_numpy()
    idx = bisect_left(timestamps, ts)
    if idx >= len(series):
        return None
    value = series.iloc[idx][col]
    if pd.isna(value):
        return None
    return float(value)


def _build_schedule_events(prices: pd.DataFrame, book_lookup: dict[tuple[int, str], pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for row in prices.itertuples(index=False):
        product = str(row.product)
        if product not in SCHEDULES:
            continue
        ts = int(row.timestamp)
        thresholds = _schedule_for(product, ts)
        if thresholds is None:
            continue
        buy, sell = thresholds
        ask = getattr(row, "ask_price_1")
        bid = getattr(row, "bid_price_1")
        candidates: list[tuple[str, float]] = []
        if pd.notna(ask) and float(ask) <= buy:
            candidates.append(("buy", float(ask)))
        if pd.notna(bid) and float(bid) >= sell:
            candidates.append(("sell", float(bid)))
        if not candidates:
            continue
        series = book_lookup[(int(row.day), product)]
        for side, entry_px in candidates:
            edge_by_horizon = {}
            for horizon in HORIZONS:
                future_ts = ts + horizon
                future_col = "bid_price_1" if side == "buy" else "ask_price_1"
                future_px = _future_value(series, future_ts, future_col)
                if future_px is None:
                    edge_by_horizon[horizon] = np.nan
                elif side == "buy":
                    edge_by_horizon[horizon] = future_px - entry_px
                else:
                    edge_by_horizon[horizon] = entry_px - future_px
            rows.append(
                {
                    "day": int(row.day),
                    "timestamp": ts,
                    "product": product,
                    "signal_side": side,
                    "entry_price": entry_px,
                    "bid_price_1": None if pd.isna(bid) else float(bid),
                    "ask_price_1": None if pd.isna(ask) else float(ask),
                    "mid_price": None if pd.isna(row.mid_price) else float(row.mid_price),
                    "schedule_buy": buy,
                    "schedule_sell": sell,
                    **{f"edge_{h}": edge_by_horizon[h] for h in HORIZONS},
                }
            )
    events = pd.DataFrame(rows)
    if not events.empty:
        events.sort_values(["day", "timestamp", "product", "signal_side"], inplace=True)
    return events


def _events_for_feature(trades: pd.DataFrame, feature: MarkFeature) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    product_mask = trades["symbol"].isin(feature.products())
    if feature.side == "buy":
        mark_mask = trades["buyer"] == feature.mark
    else:
        mark_mask = trades["seller"] == feature.mark
    matches = trades[product_mask & mark_mask]
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for day, group in matches.groupby("day"):
        out[int(day)] = (
            group["timestamp"].to_numpy(dtype=int),
            group["quantity"].to_numpy(dtype=float),
        )
    return out


def _recent_count_and_qty(
    timestamps: np.ndarray,
    quantities: np.ndarray,
    ts: int,
    window: int,
) -> tuple[int, float]:
    if len(timestamps) == 0:
        return 0, 0.0
    left = bisect_right(timestamps, ts - window)
    right = bisect_right(timestamps, ts)
    if right <= left:
        return 0, 0.0
    return int(right - left), float(quantities[left:right].sum())


def _attach_mark_features(events: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    feature_series = {feature.label: _events_for_feature(trades, feature) for feature in FEATURES}
    new_cols = {}
    for feature in FEATURES:
        by_day = feature_series[feature.label]
        for window in WINDOWS:
            counts = []
            qtys = []
            for row in out.itertuples(index=False):
                timestamps, quantities = by_day.get(int(row.day), (np.array([], dtype=int), np.array([], dtype=float)))
                count, qty = _recent_count_and_qty(timestamps, quantities, int(row.timestamp), window)
                counts.append(count)
                qtys.append(qty)
            new_cols[f"{feature.label}_cnt_{window}"] = counts
            new_cols[f"{feature.label}_qty_{window}"] = qtys
            new_cols[f"{feature.label}_active_{window}"] = np.asarray(counts) > 0
    return pd.concat([out, pd.DataFrame(new_cols, index=out.index)], axis=1)


def _summarize_conditionals(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base_group_cols = ["product", "signal_side"]
    for (product, signal_side), group in events.groupby(base_group_cols, sort=False):
        product_features = _features_for_product(str(product))
        for horizon in HORIZONS:
            edge_col = f"edge_{horizon}"
            valid = group[pd.notna(group[edge_col])]
            if len(valid) == 0:
                continue
            base_mean = float(valid[edge_col].mean())
            base_sum = float(valid[edge_col].sum())
            for feature in product_features:
                for window in WINDOWS:
                    active_col = f"{feature.label}_active_{window}"
                    feature_rows = valid[valid[active_col]]
                    no_feature_rows = valid[~valid[active_col]]
                    if len(feature_rows) == 0 or len(no_feature_rows) == 0:
                        continue
                    feature_mean = float(feature_rows[edge_col].mean())
                    no_feature_mean = float(no_feature_rows[edge_col].mean())
                    uplift = feature_mean - no_feature_mean
                    day_uplifts = {}
                    day_feature_means = {}
                    sign_agree = 0
                    for day in DAYS:
                        day_active = feature_rows[feature_rows["day"] == day]
                        day_inactive = no_feature_rows[no_feature_rows["day"] == day]
                        if len(day_active) == 0 or len(day_inactive) == 0:
                            day_uplifts[day] = np.nan
                            day_feature_means[day] = np.nan
                            continue
                        d_uplift = float(day_active[edge_col].mean() - day_inactive[edge_col].mean())
                        day_uplifts[day] = d_uplift
                        day_feature_means[day] = float(day_active[edge_col].mean())
                        if d_uplift > 0:
                            sign_agree += 1
                    rows.append(
                        {
                            "product": product,
                            "signal_side": signal_side,
                            "horizon": horizon,
                            "feature": feature.label,
                            "window": window,
                            "n": int(len(valid)),
                            "base_mean": base_mean,
                            "base_sum": base_sum,
                            "feature_n": int(len(feature_rows)),
                            "feature_mean": feature_mean,
                            "feature_sum": float(feature_rows[edge_col].sum()),
                            "feature_pos_rate": float((feature_rows[edge_col] > 0).mean()),
                            "no_feature_n": int(len(no_feature_rows)),
                            "no_feature_mean": no_feature_mean,
                            "uplift_vs_no_feature": uplift,
                            "day1_uplift": day_uplifts[1],
                            "day2_uplift": day_uplifts[2],
                            "day3_uplift": day_uplifts[3],
                            "day1_feature_mean": day_feature_means[1],
                            "day2_feature_mean": day_feature_means[2],
                            "day3_feature_mean": day_feature_means[3],
                            "sign_agree_days": sign_agree,
                            "min_day_uplift": float(
                                np.nanmin([day_uplifts[day] for day in DAYS])
                            )
                            if any(pd.notna(day_uplifts[day]) for day in DAYS)
                            else np.nan,
                        }
                    )
    summary = pd.DataFrame(rows)
    if not summary.empty:
        summary.sort_values(
            ["sign_agree_days", "uplift_vs_no_feature", "feature_n"],
            ascending=[False, False, False],
            inplace=True,
        )
    return summary


def _leave_one_day_feature_search(events: pd.DataFrame) -> pd.DataFrame:
    """Choose active/inactive state on train days and report held-out edge.

    This treats the feature only as a binary gate for an existing schedule
    signal. A row is useful if train repeatedly picks the same state and the
    held-out day also improves edge versus taking all schedule signals.
    """
    rows = []
    group_cols = ["product", "signal_side"]
    for (product, signal_side), group in events.groupby(group_cols, sort=False):
        product_features = _features_for_product(str(product))
        for horizon in HORIZONS:
            edge_col = f"edge_{horizon}"
            valid = group[pd.notna(group[edge_col])]
            if len(valid) == 0:
                continue
            for feature in product_features:
                for window in WINDOWS:
                    active_col = f"{feature.label}_active_{window}"
                    holdout_rows = []
                    for holdout in DAYS:
                        train = valid[valid["day"] != holdout]
                        test = valid[valid["day"] == holdout]
                        if len(test) == 0:
                            continue
                        train_active = train[train[active_col]]
                        train_inactive = train[~train[active_col]]
                        test_active = test[test[active_col]]
                        test_inactive = test[~test[active_col]]
                        if len(train_active) < 10 or len(train_inactive) < 10:
                            continue
                        if len(test_active) < 3 or len(test_inactive) < 3:
                            continue
                        base_train = float(train[edge_col].mean())
                        active_train = float(train_active[edge_col].mean())
                        inactive_train = float(train_inactive[edge_col].mean())
                        if active_train >= inactive_train:
                            chosen_state = "active"
                            chosen_train = active_train
                            chosen_test = float(test_active[edge_col].mean())
                            chosen_n = len(test_active)
                        else:
                            chosen_state = "inactive"
                            chosen_train = inactive_train
                            chosen_test = float(test_inactive[edge_col].mean())
                            chosen_n = len(test_inactive)
                        base_test = float(test[edge_col].mean())
                        holdout_rows.append(
                            {
                                "holdout": holdout,
                                "chosen_state": chosen_state,
                                "chosen_n": int(chosen_n),
                                "train_edge": chosen_train,
                                "train_base_edge": base_train,
                                "test_edge": chosen_test,
                                "test_base_edge": base_test,
                                "test_uplift": chosen_test - base_test,
                            }
                        )
                    if len(holdout_rows) != len(DAYS):
                        continue
                    chosen_states = [r["chosen_state"] for r in holdout_rows]
                    rows.append(
                        {
                            "product": product,
                            "signal_side": signal_side,
                            "horizon": horizon,
                            "feature": feature.label,
                            "window": window,
                            "state_consistent": int(len(set(chosen_states)) == 1),
                            "chosen_states": ",".join(chosen_states),
                            "mean_train_edge": float(np.mean([r["train_edge"] for r in holdout_rows])),
                            "mean_train_base_edge": float(np.mean([r["train_base_edge"] for r in holdout_rows])),
                            "mean_test_edge": float(np.mean([r["test_edge"] for r in holdout_rows])),
                            "mean_test_base_edge": float(np.mean([r["test_base_edge"] for r in holdout_rows])),
                            "mean_test_uplift": float(np.mean([r["test_uplift"] for r in holdout_rows])),
                            "min_test_uplift": float(np.min([r["test_uplift"] for r in holdout_rows])),
                            "positive_holdouts": int(sum(r["test_uplift"] > 0 for r in holdout_rows)),
                            "min_holdout_n": int(min(r["chosen_n"] for r in holdout_rows)),
                            "day1_test_uplift": float(next(r["test_uplift"] for r in holdout_rows if r["holdout"] == 1)),
                            "day2_test_uplift": float(next(r["test_uplift"] for r in holdout_rows if r["holdout"] == 2)),
                            "day3_test_uplift": float(next(r["test_uplift"] for r in holdout_rows if r["holdout"] == 3)),
                        }
                    )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(
            ["positive_holdouts", "state_consistent", "mean_test_uplift", "min_test_uplift"],
            ascending=[False, False, False, False],
            inplace=True,
        )
    return out


def _print_table(title: str, frame: pd.DataFrame, cols: Iterable[str], limit: int = 20) -> None:
    print(f"\n=== {title} ===")
    if frame.empty:
        print("(none)")
        return
    print(frame.loc[:, list(cols)].head(limit).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--write-wide-events",
        action="store_true",
        help="Also write the wide per-signal feature matrix; useful for debugging but slower.",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    prices = _read_price_files(args.data_dir)
    trades = _read_trade_files(args.data_dir)
    books = _build_book_lookup(prices)
    schedule_events = _build_schedule_events(prices, books)
    print(f"built schedule events: {len(schedule_events):,}", flush=True)
    enriched = _attach_mark_features(schedule_events, trades)
    print("attached Mark features", flush=True)
    summary = _summarize_conditionals(enriched)
    print(f"built conditional summary: {len(summary):,}", flush=True)
    loo = _leave_one_day_feature_search(enriched)
    print(f"built leave-one-day gates: {len(loo):,}", flush=True)

    schedule_events.to_csv(args.out_dir / "schedule_signal_edges.csv", index=False)
    if args.write_wide_events:
        enriched.to_csv(args.out_dir / "schedule_signal_edges_with_mark_features.csv", index=False)
    summary.to_csv(args.out_dir / "conditioned_schedule_edges.csv", index=False)
    loo.to_csv(args.out_dir / "loo_feature_gates.csv", index=False)

    print(f"schedule_signal_rows={len(schedule_events):,}")
    print(f"conditioned_rows={len(summary):,}")
    print(f"loo_rows={len(loo):,}")
    print(f"output_dir={args.out_dir.resolve()}")

    strong = summary[
        (summary["feature_n"] >= 10)
        & (summary["sign_agree_days"] == 3)
        & (summary["uplift_vs_no_feature"] > 0.0)
        & (summary["min_day_uplift"] > 0.0)
    ].copy()
    _print_table(
        "In-sample conditional candidates with 3/3 day-positive uplift",
        strong,
        [
            "product",
            "signal_side",
            "horizon",
            "feature",
            "window",
            "feature_n",
            "base_mean",
            "feature_mean",
            "no_feature_mean",
            "uplift_vs_no_feature",
            "min_day_uplift",
        ],
    )

    loo_strong = loo[
        (loo["positive_holdouts"] == 3)
        & (loo["state_consistent"] == 1)
        & (loo["mean_test_uplift"] > 0.0)
        & (loo["min_test_uplift"] > 0.0)
    ].copy()
    _print_table(
        "Leave-one-day feature gates with 3/3 positive holdouts",
        loo_strong,
        [
            "product",
            "signal_side",
            "horizon",
            "feature",
            "window",
            "chosen_states",
            "mean_test_edge",
            "mean_test_base_edge",
            "mean_test_uplift",
            "min_test_uplift",
            "min_holdout_n",
        ],
    )

    velvet = summary[
        (summary["product"] == "VELVETFRUIT_EXTRACT")
        & (summary["feature"].str.contains("velvet"))
        & (summary["feature_n"] >= 10)
    ].copy()
    velvet.sort_values(["sign_agree_days", "uplift_vs_no_feature"], ascending=[False, False], inplace=True)
    _print_table(
        "VELVET schedule signals conditioned on VELVET Mark flow",
        velvet,
        [
            "product",
            "signal_side",
            "horizon",
            "feature",
            "window",
            "feature_n",
            "base_mean",
            "feature_mean",
            "uplift_vs_no_feature",
            "sign_agree_days",
            "min_day_uplift",
        ],
    )

    otm = summary[
        (summary["product"].isin(["VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]))
        & (summary["feature"].str.contains("m22"))
        & (summary["feature_n"] >= 5)
    ].copy()
    otm.sort_values(["sign_agree_days", "uplift_vs_no_feature"], ascending=[False, False], inplace=True)
    _print_table(
        "OTM voucher schedule signals conditioned on Mark 22 flow",
        otm,
        [
            "product",
            "signal_side",
            "horizon",
            "feature",
            "window",
            "feature_n",
            "base_mean",
            "feature_mean",
            "uplift_vs_no_feature",
            "sign_agree_days",
            "min_day_uplift",
        ],
    )


if __name__ == "__main__":
    main()
