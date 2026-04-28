"""Grid stress test for HYDROGEL high-regime slope gates.

This is deliberately an approximate inventory-path oracle, not a fill replay.
It asks whether a high-regime policy has structural support across historical
rolling windows:

* trigger when HYD mid trades >= 10020 in relative 20k-30k;
* carry only a bounded short until a slope gate;
* if the rise from 20k to the gate persists, promote to a flat/long target
  until 60k; otherwise abort at the gate.

The goal is final-1M robustness. A candidate that wins only on the public day-3
100k prefix but has a bad false-trigger distribution should not be trusted.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.scripts.round_4.evaluate_hydrogel_probe_submissions import DATA_DIR, PRODUCT, REPO_ROOT


OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_probes"
WINDOW = 99_900
STEP = 10_000
LIMIT = 200


def load_prices(day_path: Path) -> pd.DataFrame:
    prices = pd.read_csv(day_path, sep=";")
    out = prices[prices["product"] == PRODUCT].copy()
    return out.sort_values("timestamp").reset_index(drop=True)


def row_at(prices: pd.DataFrame, timestamp: int):
    row = prices[prices["timestamp"] == timestamp]
    if row.empty:
        return None
    return row.iloc[0]


def triggered_windows() -> list[dict[str, object]]:
    windows = []
    for path in sorted(DATA_DIR.glob("prices_round_4_day_*.csv")):
        dataset = "hist_day_" + path.stem.rsplit("_day_", 1)[1]
        prices = load_prices(path)
        max_ts = int(prices["timestamp"].max())
        for start in range(0, max_ts - WINDOW + 1, STEP):
            window = prices[(prices["timestamp"] >= start) & (prices["timestamp"] <= start + WINDOW)]
            trigger_window = window[
                (window["timestamp"] >= start + 20_000)
                & (window["timestamp"] <= start + 30_000)
                & (window["mid_price"] >= 10_020.0)
            ]
            if trigger_window.empty:
                continue
            trigger = trigger_window.iloc[0]
            release = row_at(prices, start + 60_000)
            slope_start = row_at(prices, start + 20_000)
            if release is None or slope_start is None:
                continue
            windows.append(
                {
                    "dataset": dataset,
                    "start": start,
                    "prices": prices,
                    "trigger_ts": int(trigger["timestamp"]),
                    "trigger_bid": float(trigger["bid_price_1"]),
                    "trigger_ask": float(trigger["ask_price_1"]),
                    "release_bid": float(release["bid_price_1"]),
                    "release_mid": float(release["mid_price"]),
                    "slope_start_mid": float(slope_start["mid_price"]),
                }
            )
    return windows


def overlay_for_window(window: dict[str, object], short_cap: int, gate_ts: int, threshold: float, target: int):
    prices = window["prices"]
    start = int(window["start"])
    gate = row_at(prices, start + gate_ts)
    if gate is None:
        return None

    trigger_bid = float(window["trigger_bid"])
    gate_bid = float(gate["bid_price_1"])
    gate_ask = float(gate["ask_price_1"])
    release_bid = float(window["release_bid"])
    slope = float(gate["mid_price"]) - float(window["slope_start_mid"])
    passed = slope >= threshold

    cap_abs = abs(short_cap)
    missing_from_trigger = LIMIT - cap_abs
    if not passed:
        # The cap avoided selling missing_from_trigger units until the gate.
        return missing_from_trigger * (gate_bid - trigger_bid), slope, passed

    # From trigger to gate we avoided the missing short. At the gate we promote
    # from the cap to target, then release back to the base sleeve at 60k.
    gate_to_target = target + cap_abs
    release_from_target = LIMIT + target
    overlay = (
        missing_from_trigger * (gate_bid - trigger_bid)
        - gate_to_target * max(0.0, gate_ask - gate_bid)
        + release_from_target * (release_bid - gate_bid)
    )
    return overlay, slope, passed


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    windows = triggered_windows()
    rows = []
    for short_cap in (0, -20, -40, -80, -120):
        for gate_ts in (35_000, 40_000, 45_000):
            for threshold in (8.0, 10.0, 12.0, 15.0, 18.0, 20.0):
                for target in (0, 20, 40, 80):
                    overlays = []
                    pass_count = 0
                    official_like = None
                    official_passed = None
                    for window in windows:
                        result = overlay_for_window(window, short_cap, gate_ts, threshold, target)
                        if result is None:
                            continue
                        overlay, slope, passed = result
                        overlays.append(overlay)
                        pass_count += int(passed)
                        if window["dataset"] == "hist_day_3" and window["start"] == 0:
                            official_like = overlay
                            official_passed = passed
                    if not overlays:
                        continue
                    series = pd.Series(overlays)
                    rows.append(
                        {
                            "short_cap": short_cap,
                            "gate_ts": gate_ts,
                            "threshold": threshold,
                            "target": target,
                            "windows": len(series),
                            "pass_rate": pass_count / len(series),
                            "overlay_mean": series.mean(),
                            "overlay_median": series.median(),
                            "overlay_min": series.min(),
                            "overlay_p10": series.quantile(0.10),
                            "overlay_positive_rate": (series > 0).mean(),
                            "official_like_overlay": official_like,
                            "official_like_passed": official_passed,
                        }
                    )
    summary = pd.DataFrame(rows).sort_values(
        ["overlay_mean", "overlay_min", "official_like_overlay"], ascending=[False, False, False]
    )
    out_path = out_dir / "slope_gate_grid_summary.csv"
    summary.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
