"""VELVET/options alpha frontier and anti-overfit action plan.

This script answers a narrower question than the upload leaderboard:

* how much of the VELVET/voucher hindsight ceiling is captured now;
* which tested recycling/regime variants survive public 100k-window checks;
* what remains untested before treating a 100k simulator win as final-1M alpha.

The sliding-window frontier is intentionally a robustness diagnostic, not an
upload simulator. It treats public 100k slices as pseudo-unseen samples and
compares every candidate against the same `sell7_base` sleeve.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    PRODUCTS,
    UNDERLYING,
    load_historical,
)
from src.scripts.round_4.test_core_recycler_probes import markdown_table
from src.scripts.round_4.test_stacked_alpha_probes import _configs, simulate


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_alpha_frontier"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_ALPHA_FRONTIER_AND_ACTION_PLAN.md"
VELVET_COMPLEX_OUT = REPO_ROOT / "outputs" / "round_4" / "velvet_option_complex"
UPLOAD_ROBUSTNESS_OUT = REPO_ROOT / "outputs" / "round_4" / "upload_probe_robustness"
STACKED_OUT = REPO_ROOT / "outputs" / "round_4" / "stacked_alpha_probes"

CORE = ("VEV_5000", "VEV_5100", "VEV_5200")


def windowed_prices(historical: pd.DataFrame, *, step: int, window: int) -> pd.DataFrame:
    rows = []
    for day, day_prices in historical.groupby("day", sort=True):
        max_ts = int(day_prices["timestamp"].max())
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


def final_window_rows(pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "window_start": int(str(dataset).split("_s")[-1]),
                "gate_active": bool(group["gate_active"].any()),
                "total_pnl": float(last["total_pnl"]),
                "velvet_pnl": float(last[f"pnl_{UNDERLYING}"]),
                "core_pnl": sum(float(last[f"pnl_{product}"]) for product in CORE),
                "velvet_pos": int(last[f"pos_{UNDERLYING}"]),
            }
        )
    return pd.DataFrame(rows)


def simulate_frontier(historical: pd.DataFrame, *, step: int, window: int) -> pd.DataFrame:
    prices = windowed_prices(historical, step=step, window=window)
    frames = []
    for cfg in _configs():
        print(f"frontier simulate {cfg.label}", flush=True)
        _, pnl = simulate(prices, cfg)
        frames.append(final_window_rows(pnl))
    return pd.concat(frames, ignore_index=True)


def summarize_frontier(finals: pd.DataFrame) -> pd.DataFrame:
    base = finals[finals["variant"].eq("sell7_base")][
        ["dataset", "total_pnl", "velvet_pnl", "core_pnl"]
    ].rename(
        columns={
            "total_pnl": "base_total",
            "velvet_pnl": "base_velvet",
            "core_pnl": "base_core",
        }
    )
    merged = finals.merge(base, on="dataset", how="left")
    merged["delta_total"] = merged["total_pnl"] - merged["base_total"]
    merged["delta_velvet"] = merged["velvet_pnl"] - merged["base_velvet"]
    merged["delta_core"] = merged["core_pnl"] - merged["base_core"]
    rows = []
    for variant, group in merged.groupby("variant", sort=False):
        if variant == "sell7_base":
            continue
        active = group[group["gate_active"]]
        eval_group = active if not active.empty else group
        rows.append(
            {
                "variant": variant,
                "windows": int(len(group)),
                "active_windows": int(len(active)),
                "active_rate": float(len(active) / len(group)),
                "all_hit_rate": float((group["delta_total"] > 0).mean()),
                "all_mean_delta": float(group["delta_total"].mean()),
                "active_hit_rate": float((eval_group["delta_total"] > 0).mean()),
                "active_mean_delta": float(eval_group["delta_total"].mean()),
                "active_median_delta": float(eval_group["delta_total"].median()),
                "active_p10_delta": float(eval_group["delta_total"].quantile(0.10)),
                "active_p90_delta": float(eval_group["delta_total"].quantile(0.90)),
                "active_min_delta": float(eval_group["delta_total"].min()),
                "active_max_delta": float(eval_group["delta_total"].max()),
                "active_mean_velvet_delta": float(eval_group["delta_velvet"].mean()),
                "active_mean_core_delta": float(eval_group["delta_core"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["all_mean_delta", "active_mean_delta"], ascending=False
    )


def official_oracle_capture() -> tuple[pd.DataFrame, pd.DataFrame]:
    oracle = pd.read_csv(VELVET_COMPLEX_OUT / "l1_hindsight_oracle_summary.csv")
    official_oracle = oracle[oracle["dataset"].eq("official_sell7_validated")].copy()
    official_oracle = official_oracle[["product", "strike", "oracle_full_mean"]]

    product_attr = pd.read_csv(UPLOAD_ROBUSTNESS_OUT / "official_probe_product_attribution.csv")
    sell7 = product_attr[product_attr["candidate"].eq("sell7_validated")][
        ["product", "final_pnl"]
    ].rename(columns={"final_pnl": "sell7_pnl"})
    probe = product_attr[product_attr["candidate"].eq("probe_stack")][
        ["product", "final_pnl"]
    ].rename(columns={"final_pnl": "probe_stack_pnl"})
    capture = official_oracle.merge(sell7, on="product", how="left").merge(probe, on="product", how="left")
    capture["sell7_pnl"] = capture["sell7_pnl"].fillna(0.0)
    capture["probe_stack_pnl"] = capture["probe_stack_pnl"].fillna(capture["sell7_pnl"])
    capture["sell7_capture_pct"] = capture["sell7_pnl"] / capture["oracle_full_mean"]
    capture["probe_capture_pct"] = capture["probe_stack_pnl"] / capture["oracle_full_mean"]
    capture["remaining_gap_after_probe"] = capture["oracle_full_mean"] - capture["probe_stack_pnl"]
    capture["probe_delta_vs_sell7"] = capture["probe_stack_pnl"] - capture["sell7_pnl"]
    total = pd.DataFrame(
        [
            {
                "scope": "official_100k_velvet_complex",
                "oracle_upper_bound": float(capture["oracle_full_mean"].sum()),
                "sell7_pnl": float(capture["sell7_pnl"].sum()),
                "probe_stack_pnl": float(capture["probe_stack_pnl"].sum()),
                "sell7_capture_pct": float(capture["sell7_pnl"].sum() / capture["oracle_full_mean"].sum()),
                "probe_capture_pct": float(capture["probe_stack_pnl"].sum() / capture["oracle_full_mean"].sum()),
                "remaining_gap_after_probe": float(capture["remaining_gap_after_probe"].sum()),
                "probe_delta_vs_sell7": float(capture["probe_delta_vs_sell7"].sum()),
            }
        ]
    )
    return capture.sort_values("remaining_gap_after_probe", ascending=False), total


def official_proxy_table() -> pd.DataFrame:
    summary_path = STACKED_OUT / "stacked_alpha_summary.csv"
    if not summary_path.exists():
        return pd.DataFrame()
    summary = pd.read_csv(summary_path)
    official = summary[summary["dataset"].eq("official_sell7_validated")].copy()
    base = float(official.loc[official["variant"].eq("sell7_base"), "total_pnl"].iloc[0])
    official["official_proxy_delta_vs_sell7"] = official["total_pnl"] - base
    return official[
        [
            "variant",
            "total_pnl",
            "official_proxy_delta_vs_sell7",
            "velvet_pnl",
            "velvet_end_pos",
            "recycle_qty",
            "pnl_VEV_5000",
            "pnl_VEV_5100",
            "pnl_VEV_5200",
        ]
    ].sort_values("official_proxy_delta_vs_sell7", ascending=False)


def write_report(
    doc: Path,
    out_dir: Path,
    capture: pd.DataFrame,
    total_capture: pd.DataFrame,
    official_proxy: pd.DataFrame,
    frontier_summary: pd.DataFrame,
    step: int,
    window: int,
) -> None:
    text = f"""# VELVET Alpha Frontier and Action Plan

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.research_velvet_alpha_frontier
```

Artifacts live under `{out_dir}`.

## What Has Been Explored

We have explored the first generation of `VELVET/options recycling/regime
structure`: one-time early-selloff gates, VELVET buy/re-sell bands, and
gated long-only recycling in `VEV_5000/5100/5200`. That is enough to prove the
mechanism can add alpha on the official 100k path, but not enough to prove it
will generalize to a final 1M unseen run.

We have **not** yet fully explored the more important second generation:
rolling intraday regime state, capacity reservation, Greek/target-inventory
controllers, and negative-control-matched recycling.

## Hindsight Ceiling

The independent-product L1 oracle is a hard lookahead ceiling. It is not
directly uploadable, but it tells us where the remaining opportunity lives.

{markdown_table(total_capture, max_rows=10)}

By product/strike:

{markdown_table(capture[["product", "strike", "oracle_full_mean", "sell7_pnl", "probe_stack_pnl", "sell7_capture_pct", "probe_capture_pct", "probe_delta_vs_sell7", "remaining_gap_after_probe"]], max_rows=40)}

Interpretation: the current `probe_stack` captures about 58% of the official
100k hindsight ceiling. `VEV_4000/4500/5500` are already near-saturated under
this oracle. The remaining theoretical gap is concentrated in `VELVET`,
`VEV_5100`, `VEV_5200`, `VEV_5300`, and `VEV_5000`.

## Official-Proxy Candidate Frontier

{markdown_table(official_proxy, max_rows=80)}

## Public Sliding {window:,}-Tick Robustness

This uses public historical windows stepped by `{step:,}` ticks. It is a
distributional sanity check, not a final simulator. Strong candidates should
not rely on a single day-3-like early path.

{markdown_table(frontier_summary, max_rows=80)}

## Research Read

The current broad family is correct: static/regime inventory plus selective
recycling, spread capture, and terminal exposure. The data does not yet justify
a pivot to pure option-native gamma/smile trading. The strongest tested
option-native ideas had poor delta-hedged markouts or failed isolated probes.

But the current `probe_stack` is not the final answer. It is a useful upload
calibration because it verifies that the official 100k path fills the intended
VELVET and core-voucher recycle legs. It remains too path-specific because the
gate is a one-time early decision and the core recycler is slightly negative
on public active-gate windows.

## Action Plan

1. Build and upload `VELVET-only gate, no core recycle`. This isolates the
   cleaner leg; the core recycler is small and less robust.
2. Build a matched negative control with similar trade count and timing. If it
   wins too, the alpha is churn/terminal luck rather than structure.
3. Replace the one-time 30k gate with a rolling regime controller:
   recompute drawdown/rebound state every 10k-25k ticks, require hysteresis,
   and add stop/kill logic when rebound fails.
4. Add capacity reservation for `VEV_5000/5100/5200`: do not pin max long
   early unless the option is cheap versus spot-conditioned fair and the
   portfolio is under target delta/vega.
5. Test reduce-only before refill. First sell rich long core options only when
   replacement probability is high; then separately test refill. Do not bundle
   both until each leg survives controls.
6. Keep `VEV_5500 sell7`; do not spend more VELVET upload budget there unless
   testing a deliberately different terminal-wing hypothesis.

The next real alpha search is not random threshold tuning. It is turning the
existing schedule into a repeated state machine with inventory targets and
controls, then proving each added trade survives sliding-window and negative
control tests.
"""
    doc.write_text(text)


def run(data_dir: Path, out_dir: Path, doc: Path, step: int, window: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    historical = load_historical(data_dir)
    finals = simulate_frontier(historical, step=step, window=window)
    frontier_summary = summarize_frontier(finals)
    capture, total_capture = official_oracle_capture()
    official_proxy = official_proxy_table()

    finals.to_csv(out_dir / "sliding_frontier_final_rows.csv", index=False)
    frontier_summary.to_csv(out_dir / "sliding_frontier_summary.csv", index=False)
    capture.to_csv(out_dir / "official_oracle_capture_by_product.csv", index=False)
    total_capture.to_csv(out_dir / "official_oracle_capture_total.csv", index=False)
    official_proxy.to_csv(out_dir / "official_proxy_candidate_frontier.csv", index=False)
    write_report(
        doc,
        out_dir,
        capture,
        total_capture,
        official_proxy,
        frontier_summary,
        step,
        window,
    )
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(total_capture.to_string(index=False))
    print(frontier_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--step", type=int, default=25_000)
    parser.add_argument("--window", type=int, default=100_000)
    args = parser.parse_args()
    run(args.data_dir, args.out_dir, args.doc, args.step, args.window)


if __name__ == "__main__":
    main()
