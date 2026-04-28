"""Post-upload robustness analysis for R4 VELVET/voucher probes.

The IMC simulator gives one 100k unseen slice, but the final upload is scored
on 1M unseen ticks. This script separates:

* official 100k calibration results;
* product/fill attribution of the latest probe;
* public-data sliding 100k windows that test whether the early-selloff gate is
  a reusable regime or just a path fit to the validated simulator sample.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    DEFAULT_OFFICIAL_DIR,
    load_historical,
    load_official_log,
)
from src.scripts.round_4.test_stacked_alpha_probes import (
    AlphaConfig,
    GATE30_DROP20,
    LONG_CORE3_TP8,
    VelvetBand,
    simulate,
)
from src.scripts.round_4.test_core_recycler_probes import markdown_table


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "upload_probe_robustness"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "UPLOAD_PROBE_ROBUSTNESS.md"

UNDERLYING = "VELVETFRUIT_EXTRACT"
CORE = ("VEV_5000", "VEV_5100", "VEV_5200")
PRODUCTS = (
    UNDERLYING,
    "VEV_4000",
    "VEV_4500",
    "VEV_5000",
    "VEV_5100",
    "VEV_5200",
    "VEV_5300",
    "VEV_5400",
    "VEV_5500",
)
ALL_ATTR_PRODUCTS = ("HYDROGEL_PACK",) + PRODUCTS

OFFICIAL_RUNS = {
    "flat995": {
        "json": ("extracted", "flat995", "493202.json"),
        "log": ("extracted", "flat995", "493202.log"),
    },
    "flat95k": {"json": ("flat95k", "511270.json"), "log": ("flat95k", "511270.log")},
    "new_flat995": {
        "json": ("new_flat995", "511373.json"),
        "log": ("new_flat995", "511373.log"),
    },
    "sell7_validated": {
        "json": ("validated", "511763.json"),
        "log": ("validated", "511763.log"),
    },
    "probe_stack": {"json": ("probe", "513378.json"), "log": ("probe", "513378.log")},
    "cap4060k": {"json": ("cap4060k", "512019.json"), "log": ("cap4060k", "512019.log")},
    "cap8060k": {"json": ("cap8060k", "512331.json"), "log": ("cap8060k", "512331.log")},
    "hardflat60k": {
        "json": ("hardflat60k", "512637.json"),
        "log": ("hardflat60k", "512637.log"),
    },
    "hardlong4060k": {
        "json": ("hardlong4060k", "512695.json"),
        "log": ("hardlong4060k", "512695.log"),
    },
    "noshort60k": {
        "json": ("noshort60k", "512110.json"),
        "log": ("noshort60k", "512110.log"),
    },
}


def run_path(official_dir: Path, name: str, kind: str) -> Path:
    return official_dir.joinpath(*OFFICIAL_RUNS[name][kind])


def load_json_run(path: Path) -> dict:
    return json.loads(path.read_text())


def load_official_log_all_products(path: Path, *, dataset: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(path.read_text())
    activities = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    activities["dataset"] = dataset
    for column in (
        "timestamp",
        "day",
        "mid_price",
        "profit_and_loss",
        "bid_price_1",
        "bid_price_2",
        "bid_price_3",
        "ask_price_1",
        "ask_price_2",
        "ask_price_3",
    ):
        if column in activities.columns:
            activities[column] = pd.to_numeric(activities[column], errors="coerce")
    activities["timestamp"] = activities["timestamp"].astype(int)
    activities["day"] = activities["day"].astype(int)
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
    else:
        trades["dataset"] = dataset
        for column in ("timestamp", "price", "quantity"):
            trades[column] = pd.to_numeric(trades[column], errors="coerce")
        trades["timestamp"] = trades["timestamp"].astype(int)
        trades["quantity"] = trades["quantity"].astype(int)
    return activities.sort_values(["dataset", "day", "timestamp", "product"]), trades


def official_profit_table(official_dir: Path) -> pd.DataFrame:
    rows = []
    for name in OFFICIAL_RUNS:
        path = run_path(official_dir, name, "json")
        if not path.exists():
            continue
        payload = load_json_run(path)
        rows.append({"candidate": name, "official_profit": float(payload.get("profit", 0.0))})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    base = float(df.loc[df["candidate"].eq("sell7_validated"), "official_profit"].iloc[0])
    df["delta_vs_sell7_validated"] = df["official_profit"] - base
    return df.sort_values("official_profit", ascending=False)


def official_candidate_sleeve_attribution(
    official_dir: Path, official_profits: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for name in OFFICIAL_RUNS:
        path = run_path(official_dir, name, "log")
        if not path.exists():
            continue
        activities, _ = load_official_log_all_products(path, dataset=name)
        final = (
            activities[activities["product"].isin(ALL_ATTR_PRODUCTS)]
            .sort_values("timestamp")
            .groupby("product")
            .tail(1)
        )
        pnl_by_product = {
            str(row.product): float(row.profit_and_loss)
            for row in final.itertuples(index=False)
        }
        velvet_products = [pnl_by_product.get(product, 0.0) for product in PRODUCTS]
        core_products = [pnl_by_product.get(product, 0.0) for product in CORE]
        rows.append(
            {
                "candidate": name,
                "hyd_pnl": pnl_by_product.get("HYDROGEL_PACK", 0.0),
                "velvet_complex_pnl": sum(velvet_products),
                "velvet_underlying_pnl": pnl_by_product.get(UNDERLYING, 0.0),
                "core_5000_5200_pnl": sum(core_products),
                "vev5500_pnl": pnl_by_product.get("VEV_5500", 0.0),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.merge(official_profits, on="candidate", how="left")
    base = df[df["candidate"].eq("sell7_validated")].iloc[0]
    for col in [
        "hyd_pnl",
        "velvet_complex_pnl",
        "velvet_underlying_pnl",
        "core_5000_5200_pnl",
        "vev5500_pnl",
    ]:
        df[f"delta_{col}"] = df[col] - float(base[col])
    return df.sort_values("official_profit", ascending=False)


def official_product_attribution(official_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    logs = {
        "sell7_validated": run_path(official_dir, "sell7_validated", "log"),
        "probe_stack": run_path(official_dir, "probe_stack", "log"),
    }
    product_rows = []
    trade_rows = []
    for name, path in logs.items():
        if not path.exists():
            continue
        activities, trades = load_official_log(path, dataset=name)
        final = (
            activities[activities["product"].isin(PRODUCTS)]
            .sort_values("timestamp")
            .groupby("product")
            .tail(1)
        )
        for row in final.itertuples(index=False):
            product_rows.append(
                {
                    "candidate": name,
                    "product": row.product,
                    "final_pnl": float(row.profit_and_loss),
                }
            )
        own = trades[
            (trades["buyer"].eq("SUBMISSION")) | (trades["seller"].eq("SUBMISSION"))
        ].copy()
        if own.empty:
            continue
        own["side"] = own.apply(
            lambda r: "buy" if r["buyer"] == "SUBMISSION" else "sell", axis=1
        )
        for (symbol, side), group in own.groupby(["symbol", "side"], sort=False):
            if symbol not in PRODUCTS and symbol != "HYDROGEL_PACK":
                continue
            trade_rows.append(
                {
                    "candidate": name,
                    "product": symbol,
                    "side": side,
                    "qty": int(group["quantity"].sum()),
                    "avg_price": float((group["price"] * group["quantity"]).sum() / group["quantity"].sum()),
                    "first_ts": int(group["timestamp"].min()),
                    "last_ts": int(group["timestamp"].max()),
                    "rows": int(len(group)),
                }
            )
    product = pd.DataFrame(product_rows)
    if not product.empty:
        base = product[product["candidate"].eq("sell7_validated")][["product", "final_pnl"]]
        base = base.rename(columns={"final_pnl": "sell7_pnl"})
        product = product.merge(base, on="product", how="left")
        product["delta_vs_sell7"] = product["final_pnl"] - product["sell7_pnl"]
    return product, pd.DataFrame(trade_rows)


def _windowed_prices(historical: pd.DataFrame, *, step: int, window: int) -> pd.DataFrame:
    rows = []
    for day, day_prices in historical.groupby("day", sort=True):
        timestamps = sorted(int(t) for t in day_prices["timestamp"].unique())
        max_ts = max(timestamps)
        for start in range(0, max_ts - window + 1, step):
            end = start + window
            subset = day_prices[
                (day_prices["timestamp"] >= start)
                & (day_prices["timestamp"] < end)
                & (day_prices["product"].isin(PRODUCTS))
            ].copy()
            if subset.empty:
                continue
            subset["timestamp"] = subset["timestamp"].astype(int) - start
            subset["dataset"] = f"hist_d{int(day)}_s{start}"
            subset["day"] = int(day)
            subset["window_start"] = int(start)
            rows.append(subset)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def sliding_window_probe(historical: pd.DataFrame, *, step: int, window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = _windowed_prices(historical, step=step, window=window)
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame()
    configs = [
        AlphaConfig("sell7_base"),
        AlphaConfig(
            "stack_officialmax_v5248_5264_core3_tp8",
            gate=GATE30_DROP20,
            velvet_band=VelvetBand(5248, 5264),
            long_recycle=LONG_CORE3_TP8,
            long_requires_gate=True,
        ),
    ]
    pnl_frames = []
    trade_frames = []
    for cfg in configs:
        print(f"sliding simulate {cfg.label}", flush=True)
        trades, pnl = simulate(prices, cfg)
        pnl_frames.append(pnl)
        trade_frames.append(trades)
    pnl = pd.concat(pnl_frames, ignore_index=True)
    trades = pd.concat(trade_frames, ignore_index=True)

    summary_rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        parts = str(dataset).split("_s")
        start = int(parts[-1])
        summary_rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "window_start": start,
                "gate_active": bool(group["gate_active"].any()) if "gate_active" in group else False,
                "total_pnl": float(last["total_pnl"]),
                "velvet_pnl": float(last[f"pnl_{UNDERLYING}"]),
                "pnl_VEV_5000": float(last["pnl_VEV_5000"]),
                "pnl_VEV_5100": float(last["pnl_VEV_5100"]),
                "pnl_VEV_5200": float(last["pnl_VEV_5200"]),
                "pos_velvet": int(last[f"pos_{UNDERLYING}"]),
            }
        )
    summary = pd.DataFrame(summary_rows)
    base = summary[summary["variant"].eq("sell7_base")].copy()
    stack = summary[summary["variant"].ne("sell7_base")].copy()
    merged = stack.merge(
        base[
            [
                "dataset",
                "total_pnl",
                "velvet_pnl",
                "pnl_VEV_5000",
                "pnl_VEV_5100",
                "pnl_VEV_5200",
            ]
        ].rename(
            columns={
                "total_pnl": "base_total",
                "velvet_pnl": "base_velvet",
                "pnl_VEV_5000": "base_5000",
                "pnl_VEV_5100": "base_5100",
                "pnl_VEV_5200": "base_5200",
            }
        ),
        on="dataset",
        how="left",
    )
    merged["delta_total"] = merged["total_pnl"] - merged["base_total"]
    merged["delta_velvet"] = merged["velvet_pnl"] - merged["base_velvet"]
    merged["delta_core"] = (
        merged["pnl_VEV_5000"]
        + merged["pnl_VEV_5100"]
        + merged["pnl_VEV_5200"]
        - merged["base_5000"]
        - merged["base_5100"]
        - merged["base_5200"]
    )
    return merged.sort_values(["day", "window_start"]), trades


def summarize_windows(windows: pd.DataFrame) -> pd.DataFrame:
    if windows.empty:
        return windows
    rows = []
    for label, group in [
        ("all_windows", windows),
        ("gate_active", windows[windows["gate_active"]]),
        ("gate_inactive", windows[~windows["gate_active"]]),
    ]:
        if group.empty:
            continue
        rows.append(
            {
                "bucket": label,
                "windows": int(len(group)),
                "hit_rate": float((group["delta_total"] > 0).mean()),
                "mean_delta": float(group["delta_total"].mean()),
                "median_delta": float(group["delta_total"].median()),
                "min_delta": float(group["delta_total"].min()),
                "p10_delta": float(group["delta_total"].quantile(0.10)),
                "p90_delta": float(group["delta_total"].quantile(0.90)),
                "max_delta": float(group["delta_total"].max()),
                "mean_delta_velvet": float(group["delta_velvet"].mean()),
                "mean_delta_core": float(group["delta_core"].mean()),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    doc: Path,
    out_dir: Path,
    official_profits: pd.DataFrame,
    sleeve_attr: pd.DataFrame,
    product_attr: pd.DataFrame,
    trade_attr: pd.DataFrame,
    windows: pd.DataFrame,
    window_summary: pd.DataFrame,
) -> None:
    active = windows[windows["gate_active"]].copy() if not windows.empty else pd.DataFrame()
    worst_active = active.nsmallest(10, "delta_total") if not active.empty else pd.DataFrame()
    best_active = active.nlargest(10, "delta_total") if not active.empty else pd.DataFrame()
    text = f"""# R4 Upload Probe Robustness

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_upload_probe_robustness
```

Artifacts live under `{out_dir}`.

## Official 100k Calibration

{markdown_table(official_profits, max_rows=80)}

## Official Candidate Sleeve Attribution

This table is the check against over-reading the VELVET probe. A positive
official score can come from HYDROGEL timing, VELVET/voucher timing, or both.

{markdown_table(sleeve_attr[["candidate", "official_profit", "delta_vs_sell7_validated", "hyd_pnl", "delta_hyd_pnl", "velvet_complex_pnl", "delta_velvet_complex_pnl", "velvet_underlying_pnl", "delta_velvet_underlying_pnl", "core_5000_5200_pnl", "delta_core_5000_5200_pnl", "vev5500_pnl", "delta_vev5500_pnl"]], max_rows=80)}

## Probe vs sell7 Product Attribution

{markdown_table(product_attr.sort_values(["candidate", "delta_vs_sell7"], ascending=[True, False]), max_rows=80)}

## Probe Trade Attribution

{markdown_table(trade_attr.sort_values(["candidate", "product", "side"]), max_rows=120)}

## Sliding 100k Public-Window Robustness

This treats every public 100k slice, stepped by 10k ticks, as if it were a
fresh simulator sample. It is not a perfect final-1M model, but it is the right
sanity check against fitting one official 100k path.

{markdown_table(window_summary, max_rows=20)}

Worst active-gate windows:

{markdown_table(worst_active[["dataset", "day", "window_start", "delta_total", "delta_velvet", "delta_core", "total_pnl", "base_total"]], max_rows=10)}

Best active-gate windows:

{markdown_table(best_active[["dataset", "day", "window_start", "delta_total", "delta_velvet", "delta_core", "total_pnl", "base_total"]], max_rows=10)}

## Critical Decision Read

`probe_stack` is a real official 100k improvement, but it is not a clean
general edge yet. Its `+3,341.44` over `sell7_validated` is exactly:

- `VELVETFRUIT_EXTRACT`: `+2,806.44`
- `VEV_5000/5100/5200` recycle: `+535.00`
- `HYDROGEL_PACK`: unchanged
- `VEV_5500`: unchanged from `sell7`

The best leaderboard line, `hardlong4060k`, is a different mechanism:
`HYDROGEL_PACK` improves by `+5,471.00`, but that candidate gives back the
validated `VEV_5500 sell7` edge (`-2,068.90` versus `sell7_validated`). Its
top-line win is therefore not evidence against the VELVET/voucher stack. It is
evidence that the next upload should combine the stronger HYDROGEL timing
wrapper with the validated VELVET/voucher sleeve.

The overfit warning is material. Across public sliding 100k windows, the
current VELVET gate fires in only `25 / 270` windows. Conditional on firing, it
wins only `36%` of windows, has median `0`, p10 `-1,662.8`, and worst active
window `-4,262`. The mean is positive because a few windows look like the
official/probe path. That is not enough to call this final-1M robust.

The broad strategy group still looks right: static/regime inventory, spread
capture, terminal mark exposure, and carefully gated recycling. The tested
option-native pivots have not shown enough evidence to replace the baseline.
Do not spend the next upload budget on random IV/gamma parameter tweaks unless
the probe is delta-hedged and attribution-first.

## Next Upload Probes

1. `hardlong4060k + sell7 VEV_5500`: isolate whether HYDROGEL timing and
   validated VEV_5500 sell7 are additive.
2. `hardlong4060k + probe_stack`: test the full additive stack. This is the
   highest-upside candidate, but also the easiest to overfit to the official
   100k path.
3. VELVET-only gate, no `VEV_5000/5100/5200` recycle: the sliding-window core
   recycler has negative mean when the gate fires, so isolate the cleaner leg.
4. Rolling VELVET regime controller: replace one early `30k` gate with repeated
   intraday state checks, hysteresis, stop/kill logic, and inventory caps.
5. Negative-control gate: same trade count/fill opportunity with shifted or
   inverted regime condition. If that also wins, the current result is mostly
   path churn or terminal luck.
"""
    doc.write_text(text)


def run(data_dir: Path, official_dir: Path, out_dir: Path, doc: Path, step: int, window: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    official_profits = official_profit_table(official_dir)
    sleeve_attr = official_candidate_sleeve_attribution(official_dir, official_profits)
    product_attr, trade_attr = official_product_attribution(official_dir)
    historical = load_historical(data_dir)
    windows, trades = sliding_window_probe(historical, step=step, window=window)
    window_summary = summarize_windows(windows)

    official_profits.to_csv(out_dir / "official_profit_table.csv", index=False)
    sleeve_attr.to_csv(out_dir / "official_candidate_sleeve_attribution.csv", index=False)
    product_attr.to_csv(out_dir / "official_probe_product_attribution.csv", index=False)
    trade_attr.to_csv(out_dir / "official_probe_trade_attribution.csv", index=False)
    windows.to_csv(out_dir / "sliding_window_summary.csv", index=False)
    trades.to_csv(out_dir / "sliding_window_trades.csv", index=False)
    window_summary.to_csv(out_dir / "sliding_window_bucket_summary.csv", index=False)
    write_report(doc, out_dir, official_profits, sleeve_attr, product_attr, trade_attr, windows, window_summary)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print("Official profits")
    print(official_profits.to_string(index=False))
    print("Window summary")
    print(window_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-dir", type=Path, default=DEFAULT_OFFICIAL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--step", type=int, default=10_000)
    parser.add_argument("--window", type=int, default=100_000)
    args = parser.parse_args()
    run(args.data_dir, args.official_dir, args.out_dir, args.doc, args.step, args.window)


if __name__ == "__main__":
    main()
