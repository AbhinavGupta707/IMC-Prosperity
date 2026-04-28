"""Audit Discord-style VELVET microprice / Mark67 claims.

Checks:
- VELVET top-of-book microprice imbalance persistence across historical days.
- Whether the signal is directional after spread costs, not just mid-markout.
- Overlap between persistent imbalance and Mark67 buys.
- Official 100k replication on one simulator log.
- Whether Mark67 is only a public buyer while still appearing as seller against
  SUBMISSION fills.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_SIM_DIR = Path("r4 Sim Results")
DEFAULT_OFFICIAL_LOG = Path("r4 Sim Results/expstack8060/516313.log")
DEFAULT_OUT_DIR = Path("outputs/round_4/velvet_microprice_mark67")

PRODUCT = "VELVETFRUIT_EXTRACT"
DAYS = (1, 2, 3)
HORIZONS = (100, 200, 500, 1_000, 5_000, 10_000, 30_000)


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
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
    if "day" not in prices:
        prices["day"] = 0
    # Official logs for this round carry day=3 in activitiesLog even though the
    # simulator slice is unseen. Trade history has no day field, so align it to
    # the single day present in activitiesLog.
    trades["day"] = int(prices["day"].dropna().iloc[0]) if not prices.empty else 0
    return prices, trades


def prepare_velvet_book(prices: pd.DataFrame) -> pd.DataFrame:
    book = prices[prices["product"].eq(PRODUCT)].copy()
    book.rename(
        columns={
            "bid_price_1": "bid",
            "ask_price_1": "ask",
            "bid_volume_1": "bid_vol",
            "ask_volume_1": "ask_vol",
            "mid_price": "mid",
        },
        inplace=True,
    )
    book.sort_values(["day", "timestamp"], inplace=True)
    book["spread"] = book["ask"] - book["bid"]
    denom = book["bid_vol"].fillna(0) + book["ask_vol"].fillna(0)
    book["imbalance"] = np.where(denom > 0, (book["bid_vol"].fillna(0) - book["ask_vol"].fillna(0)) / denom, np.nan)
    book["microprice"] = np.where(
        denom > 0,
        (book["ask"] * book["bid_vol"].fillna(0) + book["bid"] * book["ask_vol"].fillna(0)) / denom,
        np.nan,
    )
    book["micro_skew"] = np.where(book["spread"] > 0, (book["microprice"] - book["mid"]) / (book["spread"] / 2.0), np.nan)
    for horizon in HORIZONS:
        steps = horizon // 100
        for col in ("mid", "bid", "ask"):
            book[f"{col}_future_{horizon}"] = book.groupby("day")[col].shift(-steps)
    for threshold in (0.4, 0.5, 0.6, 0.7):
        pos = book["imbalance"] > threshold
        neg = book["imbalance"] < -threshold
        book[f"pos_persist3_{threshold}"] = pos & pos.groupby(book["day"]).shift(1, fill_value=False) & pos.groupby(book["day"]).shift(2, fill_value=False)
        book[f"neg_persist3_{threshold}"] = neg & neg.groupby(book["day"]).shift(1, fill_value=False) & neg.groupby(book["day"]).shift(2, fill_value=False)
        book[f"pos_start3_{threshold}"] = book[f"pos_persist3_{threshold}"] & ~book[f"pos_persist3_{threshold}"].groupby(book["day"]).shift(1, fill_value=False)
        book[f"neg_start3_{threshold}"] = book[f"neg_persist3_{threshold}"] & ~book[f"neg_persist3_{threshold}"].groupby(book["day"]).shift(1, fill_value=False)
    return book


def summarize_signal(book: pd.DataFrame, prefix: str) -> pd.DataFrame:
    rows = []
    for threshold in (0.4, 0.5, 0.6, 0.7):
        specs = (
            (f"pos_persist3_{threshold}", 1, "pos_all_active"),
            (f"neg_persist3_{threshold}", -1, "neg_all_active"),
            (f"pos_start3_{threshold}", 1, "pos_run_starts"),
            (f"neg_start3_{threshold}", -1, "neg_run_starts"),
        )
        for col, sign, label in specs:
            selected = book[book[col]].copy()
            if selected.empty:
                continue
            for horizon in HORIZONS:
                signed_mid = sign * (selected[f"mid_future_{horizon}"] - selected["mid"])
                if sign > 0:
                    aggressive_edge = selected[f"bid_future_{horizon}"] - selected["ask"]
                    passive_markout = selected[f"mid_future_{horizon}"] - selected["bid"]
                else:
                    aggressive_edge = selected["bid"] - selected[f"ask_future_{horizon}"]
                    passive_markout = selected["ask"] - selected[f"mid_future_{horizon}"]
                valid = signed_mid.notna() & aggressive_edge.notna()
                vals = signed_mid[valid]
                aggr = aggressive_edge[valid]
                passive = passive_markout[valid]
                if len(vals) == 0:
                    continue
                daily = []
                daily_aggr = []
                for day, day_group in selected[valid].groupby("day"):
                    if sign > 0:
                        day_aggr = day_group[f"bid_future_{horizon}"] - day_group["ask"]
                        day_mid = day_group[f"mid_future_{horizon}"] - day_group["mid"]
                    else:
                        day_aggr = day_group["bid"] - day_group[f"ask_future_{horizon}"]
                        day_mid = day_group["mid"] - day_group[f"mid_future_{horizon}"]
                    daily.append(float(day_mid.mean()))
                    daily_aggr.append(float(day_aggr.mean()))
                rows.append(
                    {
                        "sample": prefix,
                        "threshold": threshold,
                        "signal": label,
                        "horizon": horizon,
                        "n": int(len(vals)),
                        "days": int(selected[valid]["day"].nunique()),
                        "signed_mid_mean": float(vals.mean()),
                        "signed_mid_t_naive": float(vals.mean() / (vals.std(ddof=1) / np.sqrt(len(vals)))) if len(vals) > 1 and vals.std(ddof=1) > 0 else np.nan,
                        "aggressive_edge_mean": float(aggr.mean()),
                        "passive_mid_markout_mean": float(passive.mean()),
                        "positive_mid_rate": float((vals > 0).mean()),
                        "positive_aggr_rate": float((aggr > 0).mean()),
                        "daily_mid_min": float(np.nanmin(daily)) if daily else np.nan,
                        "daily_mid_max": float(np.nanmax(daily)) if daily else np.nan,
                        "daily_aggr_min": float(np.nanmin(daily_aggr)) if daily_aggr else np.nan,
                        "daily_aggr_max": float(np.nanmax(daily_aggr)) if daily_aggr else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def mark67_stats(book: pd.DataFrame, trades: pd.DataFrame, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    velvet = trades[trades["symbol"].eq(PRODUCT)].copy()
    m67 = velvet[(velvet["buyer"].eq("Mark 67")) | (velvet["seller"].eq("Mark 67"))].copy()
    if m67.empty:
        return pd.DataFrame(), pd.DataFrame()
    merged = m67.merge(
        book,
        left_on=["day", "timestamp"],
        right_on=["day", "timestamp"],
        how="left",
        suffixes=("", "_book"),
    )
    merged["m67_side"] = np.where(merged["buyer"].eq("Mark 67"), "buy", "sell")
    rows = []
    for side, sign in (("buy", 1), ("sell", -1)):
        group = merged[merged["m67_side"].eq(side)]
        if group.empty:
            continue
        for horizon in HORIZONS:
            signed_mid = sign * (group[f"mid_future_{horizon}"] - group["mid"])
            if sign > 0:
                aggr = group[f"bid_future_{horizon}"] - group["price"]
            else:
                aggr = group["price"] - group[f"ask_future_{horizon}"]
            rows.append(
                {
                    "sample": prefix,
                    "m67_side": side,
                    "horizon": horizon,
                    "n": int(signed_mid.notna().sum()),
                    "days": int(group["day"].nunique()),
                    "qty": int(group["quantity"].sum()),
                    "signed_mid_mean": float(signed_mid.mean()),
                    "aggressive_edge_mean": float(aggr.mean()),
                    "positive_mid_rate": float((signed_mid > 0).mean()),
                    "imbalance_mean_at_m67": float(group["imbalance"].mean()),
                    "persist_pos06_rate": float(group["pos_persist3_0.6"].mean()) if "pos_persist3_0.6" in group else np.nan,
                    "persist_neg06_rate": float(group["neg_persist3_0.6"].mean()) if "neg_persist3_0.6" in group else np.nan,
                }
            )
    overlap_rows = []
    timeline = {
        int(day): sorted(group["timestamp"].astype(int).tolist()) for day, group in book.groupby("day")
    }
    m67_buy_times = {
        int(day): sorted(group["timestamp"].astype(int).tolist())
        for day, group in m67[m67["buyer"].eq("Mark 67")].groupby("day")
    }
    for threshold in (0.4, 0.5, 0.6, 0.7):
        for col in (f"pos_persist3_{threshold}", f"neg_persist3_{threshold}", f"pos_start3_{threshold}", f"neg_start3_{threshold}"):
            selected = book[book[col]]
            if selected.empty:
                continue
            for horizon in (1_000, 5_000, 10_000, 30_000):
                hits = 0
                n = 0
                base_rates = []
                for day, group in selected.groupby("day"):
                    times = m67_buy_times.get(int(day), [])
                    if not times:
                        continue
                    for ts in group["timestamp"].astype(int):
                        idx = np.searchsorted(times, int(ts), side="right")
                        hits += int(idx < len(times) and times[idx] <= int(ts) + horizon)
                        n += 1
                    base_timeline = timeline.get(int(day), [])
                    base_hits = 0
                    for ts in base_timeline:
                        idx = np.searchsorted(times, int(ts), side="right")
                        base_hits += int(idx < len(times) and times[idx] <= int(ts) + horizon)
                    if base_timeline:
                        base_rates.append(base_hits / len(base_timeline))
                if n:
                    base = float(np.nanmean(base_rates)) if base_rates else np.nan
                    rate = hits / n
                    overlap_rows.append(
                        {
                            "sample": prefix,
                            "condition": col,
                            "horizon_to_m67_buy": horizon,
                            "n_condition_rows": int(n),
                            "m67_buy_hit_rate": float(rate),
                            "baseline_hit_rate": base,
                            "lift": float(rate / base) if base and base > 0 else np.nan,
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(overlap_rows)


def official_mark67_fill_counts(sim_dir: Path) -> pd.DataFrame:
    rows = []
    for log_path in sorted(sim_dir.glob("*/*.log")):
        try:
            payload = json.loads(log_path.read_text())
        except Exception:
            continue
        trades = pd.DataFrame(payload.get("tradeHistory", []))
        if trades.empty:
            continue
        m67 = trades[(trades["buyer"].eq("Mark 67")) | (trades["seller"].eq("Mark 67"))].copy()
        if m67.empty:
            continue
        own = m67[(m67["buyer"].eq("SUBMISSION")) | (m67["seller"].eq("SUBMISSION"))]
        public = m67[(m67["buyer"].ne("SUBMISSION")) & (m67["seller"].ne("SUBMISSION"))]
        rows.append(
            {
                "folder": log_path.parent.name,
                "log": log_path.name,
                "m67_public_buy_rows": int(public["buyer"].eq("Mark 67").sum()),
                "m67_public_sell_rows": int(public["seller"].eq("Mark 67").sum()),
                "m67_public_buy_qty": int(public.loc[public["buyer"].eq("Mark 67"), "quantity"].sum()) if not public.empty else 0,
                "m67_public_sell_qty": int(public.loc[public["seller"].eq("Mark 67"), "quantity"].sum()) if not public.empty else 0,
                "submission_bought_from_m67_rows": int(((own["buyer"] == "SUBMISSION") & (own["seller"] == "Mark 67")).sum()),
                "submission_sold_to_m67_rows": int(((own["seller"] == "SUBMISSION") & (own["buyer"] == "Mark 67")).sum()),
                "submission_bought_from_m67_qty": int(own.loc[(own["buyer"] == "SUBMISSION") & (own["seller"] == "Mark 67"), "quantity"].sum()) if not own.empty else 0,
                "submission_sold_to_m67_qty": int(own.loc[(own["seller"] == "SUBMISSION") & (own["buyer"] == "Mark 67"), "quantity"].sum()) if not own.empty else 0,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["submission_bought_from_m67_qty", "submission_sold_to_m67_qty", "m67_public_buy_qty"], ascending=False, inplace=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_OFFICIAL_LOG)
    parser.add_argument("--sim-dir", type=Path, default=DEFAULT_SIM_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    hist_prices, hist_trades = load_historical(args.data_dir)
    hist_book = prepare_velvet_book(hist_prices)
    hist_signal = summarize_signal(hist_book, "historical")
    hist_m67, hist_overlap = mark67_stats(hist_book, hist_trades, "historical")

    hist_book.to_csv(args.out_dir / "historical_velvet_book_features.csv", index=False)
    hist_signal.to_csv(args.out_dir / "historical_microprice_signal_summary.csv", index=False)
    hist_m67.to_csv(args.out_dir / "historical_mark67_summary.csv", index=False)
    hist_overlap.to_csv(args.out_dir / "historical_microprice_to_mark67_overlap.csv", index=False)

    if args.official_log.exists():
        off_prices, off_trades = load_official(args.official_log)
        off_book = prepare_velvet_book(off_prices)
        off_signal = summarize_signal(off_book, "official")
        off_m67, off_overlap = mark67_stats(off_book, off_trades, "official")
        off_book.to_csv(args.out_dir / "official_velvet_book_features.csv", index=False)
        off_signal.to_csv(args.out_dir / "official_microprice_signal_summary.csv", index=False)
        off_m67.to_csv(args.out_dir / "official_mark67_summary.csv", index=False)
        off_overlap.to_csv(args.out_dir / "official_microprice_to_mark67_overlap.csv", index=False)

    fill_counts = official_mark67_fill_counts(args.sim_dir)
    fill_counts.to_csv(args.out_dir / "official_mark67_fill_counts_by_upload.csv", index=False)

    def show(title: str, frame: pd.DataFrame, cols: list[str], mask: pd.Series | None = None, n: int = 20) -> None:
        print(f"\n=== {title} ===")
        if frame.empty:
            print("(none)")
            return
        view = frame[mask].copy() if mask is not None else frame.copy()
        if view.empty:
            print("(none)")
            return
        print(view.loc[:, cols].head(n).to_string(index=False))

    show(
        "Historical pos imbalance >0.6 persist3",
        hist_signal,
        ["signal", "horizon", "n", "days", "signed_mid_mean", "signed_mid_t_naive", "aggressive_edge_mean", "daily_mid_min", "daily_mid_max", "daily_aggr_min", "daily_aggr_max"],
        (hist_signal["threshold"] == 0.6) & (hist_signal["signal"].isin(["pos_all_active", "pos_run_starts"])),
    )
    if args.official_log.exists():
        off_signal = pd.read_csv(args.out_dir / "official_microprice_signal_summary.csv")
        show(
            "Official pos imbalance >0.6 persist3",
            off_signal,
            ["signal", "horizon", "n", "days", "signed_mid_mean", "signed_mid_t_naive", "aggressive_edge_mean", "positive_mid_rate", "positive_aggr_rate"],
            (off_signal["threshold"] == 0.6) & (off_signal["signal"].isin(["pos_all_active", "pos_run_starts"])),
        )
    show(
        "Historical Mark67 summary",
        hist_m67,
        ["m67_side", "horizon", "n", "days", "qty", "signed_mid_mean", "aggressive_edge_mean", "positive_mid_rate", "imbalance_mean_at_m67", "persist_pos06_rate"],
        hist_m67["horizon"].isin([100, 1_000, 5_000, 10_000]),
    )
    if args.official_log.exists():
        off_m67 = pd.read_csv(args.out_dir / "official_mark67_summary.csv")
        show(
            "Official Mark67 summary",
            off_m67,
            ["m67_side", "horizon", "n", "days", "qty", "signed_mid_mean", "aggressive_edge_mean", "positive_mid_rate", "imbalance_mean_at_m67", "persist_pos06_rate"],
            off_m67["horizon"].isin([100, 1_000, 5_000, 10_000]),
        )
    show(
        "Mark67 fill counts by upload",
        fill_counts,
        ["folder", "m67_public_buy_rows", "m67_public_sell_rows", "submission_bought_from_m67_rows", "submission_sold_to_m67_rows", "submission_bought_from_m67_qty", "submission_sold_to_m67_qty"],
        n=40,
    )


if __name__ == "__main__":
    main()
