"""HYDROGEL high-regime generalization checks.

The official 100k uploads show that hard-flat / hard-long until 60k extract
more HYD PnL than the R3-derived static short. This script asks whether that
idea is structural or just a 100k-path fit.

It scans rolling 100k windows in historical R4 data and compares:

* whether a high-regime trigger fires in the relative 20k-30k window;
* the incremental value of delaying a short from trigger to 60k;
* the incremental value of holding a +40 long from trigger to 60k;
* the value of releasing by price threshold rather than a fixed timestamp.

This is a diagnostic approximation, not a full fill simulator.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
OFFICIAL_LOG = REPO_ROOT / "r4 Sim Results" / "extracted" / "flat995" / "493202.log"
OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_probes"
PRODUCT = "HYDROGEL_PACK"

WINDOW = 99_900
STEP = 10_000
TRIGGER_START = 20_000
TRIGGER_END = 30_000
TRIGGER_MID = 10_020.0
FIXED_RELEASE = 60_000
PRICE_RELEASE_BID = 10_048
TARGET_LONG = 40
SHORT_SIZE = 200


def load_historical(data_dir: Path) -> list[tuple[str, pd.DataFrame]]:
    out = []
    for path in sorted(data_dir.glob("prices_round_4_day_*.csv")):
        day = path.stem.rsplit("_day_", 1)[1]
        prices = prepare_prices(pd.read_csv(path, sep=";"))
        out.append((f"hist_day_{day}", prices))
    return out


def load_official(path: Path) -> tuple[str, pd.DataFrame]:
    payload = json.loads(path.read_text())
    prices = prepare_prices(pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";"))
    return "official_100k", prices


def prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    out = prices[prices["product"] == PRODUCT].copy()
    for col in out.columns:
        if col != "product":
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values("timestamp").reset_index(drop=True)


def row_at(prices: pd.DataFrame, timestamp: int) -> pd.Series | None:
    row = prices[prices["timestamp"] == timestamp]
    if row.empty:
        return None
    return row.iloc[0]


def scan_dataset(name: str, prices: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    max_ts = int(prices["timestamp"].max())
    starts = [0] if name == "official_100k" else list(range(0, max_ts - WINDOW + 1, STEP))
    for start in starts:
        window = prices[(prices["timestamp"] >= start) & (prices["timestamp"] <= start + WINDOW)]
        if window.empty:
            continue
        trigger_window = window[
            (window["timestamp"] >= start + TRIGGER_START)
            & (window["timestamp"] <= start + TRIGGER_END)
            & (window["mid_price"] >= TRIGGER_MID)
        ]
        if trigger_window.empty:
            rows.append(
                {
                    "dataset": name,
                    "start": start,
                    "triggered": False,
                }
            )
            continue

        trigger = trigger_window.iloc[0]
        fixed = row_at(prices, start + FIXED_RELEASE)
        terminal = row_at(prices, start + WINDOW)
        if fixed is None or terminal is None:
            continue

        after_trigger = window[window["timestamp"] >= int(trigger["timestamp"])]
        price_release = after_trigger[after_trigger["bid_price_1"] >= PRICE_RELEASE_BID]
        release = price_release.iloc[0] if not price_release.empty else fixed
        release_kind = "bid_threshold" if not price_release.empty else "fixed_60k_fallback"

        trigger_bid = float(trigger["bid_price_1"])
        trigger_ask = float(trigger["ask_price_1"])
        fixed_bid = float(fixed["bid_price_1"])
        fixed_mid = float(fixed["mid_price"])
        release_bid = float(release["bid_price_1"])
        release_mid = float(release["mid_price"])
        terminal_mid = float(terminal["mid_price"])

        rows.append(
            {
                "dataset": name,
                "start": start,
                "triggered": True,
                "trigger_ts": int(trigger["timestamp"]),
                "trigger_rel": int(trigger["timestamp"]) - start,
                "trigger_mid": float(trigger["mid_price"]),
                "trigger_bid": trigger_bid,
                "trigger_ask": trigger_ask,
                "fixed_release_ts": start + FIXED_RELEASE,
                "fixed_release_mid": fixed_mid,
                "fixed_release_bid": fixed_bid,
                "price_release_ts": int(release["timestamp"]),
                "price_release_rel": int(release["timestamp"]) - start,
                "price_release_kind": release_kind,
                "price_release_mid": release_mid,
                "price_release_bid": release_bid,
                "terminal_mid": terminal_mid,
                "long40_to_fixed_pnl": TARGET_LONG * (fixed_bid - trigger_ask),
                "long40_to_price_release_pnl": TARGET_LONG * (release_bid - trigger_ask),
                "short_delay_to_fixed_delta": SHORT_SIZE * (fixed_bid - trigger_bid),
                "short_delay_to_price_release_delta": SHORT_SIZE * (release_bid - trigger_bid),
                "fixed_short_to_terminal_pnl": SHORT_SIZE * (fixed_bid - terminal_mid),
                "price_release_short_to_terminal_pnl": SHORT_SIZE * (release_bid - terminal_mid),
                "trigger_short_to_terminal_pnl": SHORT_SIZE * (trigger_bid - terminal_mid),
            }
        )
    return rows


def summarize(rows: pd.DataFrame) -> pd.DataFrame:
    trig = rows[rows["triggered"] == True].copy()  # noqa: E712 - pandas comparison
    if trig.empty:
        return pd.DataFrame()
    grouped = []
    for dataset, group in trig.groupby("dataset"):
        grouped.append(
            {
                "dataset": dataset,
                "triggered_windows": len(group),
                "long40_fixed_mean": group["long40_to_fixed_pnl"].mean(),
                "long40_fixed_min": group["long40_to_fixed_pnl"].min(),
                "long40_fixed_positive_rate": (group["long40_to_fixed_pnl"] > 0).mean(),
                "short_delay_fixed_mean": group["short_delay_to_fixed_delta"].mean(),
                "short_delay_fixed_min": group["short_delay_to_fixed_delta"].min(),
                "short_delay_fixed_positive_rate": (
                    group["short_delay_to_fixed_delta"] > 0
                ).mean(),
                "fixed_short_terminal_mean": group["fixed_short_to_terminal_pnl"].mean(),
                "fixed_short_terminal_min": group["fixed_short_to_terminal_pnl"].min(),
                "price_release_mean_rel": group["price_release_rel"].mean(),
                "price_release_short_terminal_mean": group[
                    "price_release_short_to_terminal_pnl"
                ].mean(),
                "price_release_short_terminal_min": group[
                    "price_release_short_to_terminal_pnl"
                ].min(),
            }
        )
    grouped.append(
        {
            "dataset": "ALL_HIST",
            "triggered_windows": len(trig[trig["dataset"].str.startswith("hist_")]),
            "long40_fixed_mean": trig[trig["dataset"].str.startswith("hist_")][
                "long40_to_fixed_pnl"
            ].mean(),
            "long40_fixed_min": trig[trig["dataset"].str.startswith("hist_")][
                "long40_to_fixed_pnl"
            ].min(),
            "long40_fixed_positive_rate": (
                trig[trig["dataset"].str.startswith("hist_")]["long40_to_fixed_pnl"] > 0
            ).mean(),
            "short_delay_fixed_mean": trig[trig["dataset"].str.startswith("hist_")][
                "short_delay_to_fixed_delta"
            ].mean(),
            "short_delay_fixed_min": trig[trig["dataset"].str.startswith("hist_")][
                "short_delay_to_fixed_delta"
            ].min(),
            "short_delay_fixed_positive_rate": (
                trig[trig["dataset"].str.startswith("hist_")][
                    "short_delay_to_fixed_delta"
                ]
                > 0
            ).mean(),
            "fixed_short_terminal_mean": trig[trig["dataset"].str.startswith("hist_")][
                "fixed_short_to_terminal_pnl"
            ].mean(),
            "fixed_short_terminal_min": trig[trig["dataset"].str.startswith("hist_")][
                "fixed_short_to_terminal_pnl"
            ].min(),
            "price_release_mean_rel": trig[trig["dataset"].str.startswith("hist_")][
                "price_release_rel"
            ].mean(),
            "price_release_short_terminal_mean": trig[
                trig["dataset"].str.startswith("hist_")
            ]["price_release_short_to_terminal_pnl"].mean(),
            "price_release_short_terminal_min": trig[
                trig["dataset"].str.startswith("hist_")
            ]["price_release_short_to_terminal_pnl"].min(),
        }
    )
    return pd.DataFrame(grouped)


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    datasets = load_historical(DATA_DIR)
    if OFFICIAL_LOG.exists():
        datasets.append(load_official(OFFICIAL_LOG))

    rows = []
    for name, prices in datasets:
        rows.extend(scan_dataset(name, prices))
    row_df = pd.DataFrame(rows)
    summary_df = summarize(row_df)

    windows_path = out_dir / "regime_generalization_windows.csv"
    summary_path = out_dir / "regime_generalization_summary.csv"
    row_df.to_csv(windows_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    print(f"Wrote {windows_path}")
    print(f"Wrote {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
