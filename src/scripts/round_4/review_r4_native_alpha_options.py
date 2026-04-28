"""Review three Round 4-native alpha hypotheses.

This script is a synthesis/audit layer over the existing R4 research outputs.
It deliberately separates "there is a Mark pattern" from "there is an
executable, upload-worthy strategy":

1. Mark55/Mark67 VELVET passive fills as a short-horizon recycler.
2. Mark22 option-basket flow as an option-regime conditioner.
3. HYDROGEL own-fill counterparty IDs as post-fill inventory control.

The output is meant to decide next uploads, not to optimize parameters.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from bisect import bisect_left
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "native_alpha_options"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "R4_NATIVE_ALPHA_OPTIONS_REVIEW.md"

SIM_DIR = REPO_ROOT / "r4 Sim Results"
Q5_M67_ZIP = SIM_DIR / "m67 q5.zip"
Q5_SUMMARY = REPO_ROOT / "outputs" / "round_4" / "mark_policy" / "q5_official_upload_summary.csv"
Q5_EXTRA = REPO_ROOT / "outputs" / "round_4" / "mark_policy" / "q5_official_extra_velvet_fills.csv"
MARK55_OPPORTUNITY = (
    REPO_ROOT / "outputs" / "round_4" / "mark_policy" / "mark55_passive_opportunity_summary.csv"
)
LOO_GATES = REPO_ROOT / "outputs" / "round_4" / "mark_conditioned" / "loo_feature_gates.csv"
CONDITIONED_EDGES = (
    REPO_ROOT / "outputs" / "round_4" / "mark_conditioned" / "conditioned_schedule_edges.csv"
)
RESERVE_PROBE = (
    REPO_ROOT / "outputs" / "round_4" / "mark_conditioned" / "reserve_probe_summary.csv"
)
HYD_UNIQUE = (
    REPO_ROOT
    / "outputs"
    / "round_4"
    / "mark_policy"
    / "hyd_own_fill_counterparty"
    / "hyd_counterparty_summary_unique.csv"
)
HYD_BUCKETS = (
    REPO_ROOT
    / "outputs"
    / "round_4"
    / "mark_policy"
    / "hyd_own_fill_counterparty"
    / "hyd_counterparty_time_bucket_summary.csv"
)
HYD_CANDIDATES = (
    REPO_ROOT
    / "outputs"
    / "round_4"
    / "mark_policy"
    / "hyd_own_fill_counterparty"
    / "hyd_candidate_summary.csv"
)

VELVET = "VELVETFRUIT_EXTRACT"
HORIZONS = (100, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 30_000)


def markdown_table(df: pd.DataFrame, *, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows).copy()
    for col in show.columns:
        if pd.api.types.is_float_dtype(show[col]):
            show[col] = show[col].map(lambda value: "" if pd.isna(value) else f"{value:.2f}")
    cols = list(show.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for row in show.itertuples(index=False):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _read_payload(path: Path) -> dict:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = sorted(name for name in archive.namelist() if name.endswith(".log"))
            if not names:
                raise ValueError(f"no .log member in {path}")
            return json.loads(archive.read(names[0]).decode())
    return json.loads(path.read_text())


def _activities(path: Path) -> pd.DataFrame:
    payload = _read_payload(path)
    return pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")


def _future_value(book: pd.DataFrame, timestamp: int, column: str) -> float:
    timestamps = book["timestamp"].to_numpy(dtype=int)
    idx = bisect_left(timestamps, int(timestamp))
    if idx >= len(book):
        return float("nan")
    value = book.iloc[idx][column]
    return float(value) if pd.notna(value) else float("nan")


def review_mark55_recycler(out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary = pd.read_csv(Q5_SUMMARY)
    extra = pd.read_csv(Q5_EXTRA)
    fills = extra[extra["candidate"].eq("m67_q5")].copy()
    fills["extra_qty"] = fills["extra_qty"].astype(float)

    q5_delta = float(summary.loc[summary["label"].eq("m67_q5"), "delta_vs_validated"].iloc[0])
    activities = _activities(Q5_M67_ZIP)
    book = (
        activities[activities["product"].eq(VELVET)][
            ["timestamp", "bid_price_1", "ask_price_1", "mid_price"]
        ]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    final_mid = float(book.iloc[-1]["mid_price"])

    horizon_rows = []
    for horizon in HORIZONS:
        exit_values = []
        delta_values = []
        roundtrip_values = []
        for fill in fills.itertuples(index=False):
            exit_bid = _future_value(book, int(fill.timestamp) + horizon, "bid_price_1")
            qty = float(fill.extra_qty)
            if np.isnan(exit_bid):
                continue
            exit_values.append(exit_bid)
            roundtrip_values.append((exit_bid - float(fill.price)) * qty)
            delta_values.append((exit_bid - final_mid) * qty)
        delta_vs_q5 = float(np.sum(delta_values))
        horizon_rows.append(
            {
                "exit_rule": f"sell_at_bid_after_{horizon}",
                "fills": int(len(exit_values)),
                "qty": int(fills["extra_qty"].sum()),
                "realized_roundtrip_pnl": float(np.sum(roundtrip_values)),
                "delta_vs_hold_to_end": delta_vs_q5,
                "projected_delta_vs_validated": q5_delta + delta_vs_q5,
            }
        )

    policy_rows = []
    for target in (0, 1, 2, 3):
        for max_age in (1_000, 2_000, 5_000, 10_000):
            for force_mode in ("target_only", "breakeven_stop", "force_exit"):
                exited = 0
                exit_qty = 0.0
                roundtrip = 0.0
                delta_vs_hold = 0.0
                ages: list[int] = []
                for fill in fills.itertuples(index=False):
                    start = int(fill.timestamp) + 100
                    end = int(fill.timestamp) + max_age
                    entry = float(fill.price)
                    qty = float(fill.extra_qty)
                    window = book[(book["timestamp"] >= start) & (book["timestamp"] <= end)]
                    if window.empty:
                        continue
                    hit = window[window["bid_price_1"].astype(float) >= entry + target]
                    if not hit.empty:
                        exit_row = hit.iloc[0]
                    elif force_mode == "breakeven_stop":
                        last = window.iloc[-1]
                        if float(last["bid_price_1"]) < entry:
                            continue
                        exit_row = last
                    elif force_mode == "force_exit":
                        exit_row = window.iloc[-1]
                    else:
                        continue
                    exit_bid = float(exit_row["bid_price_1"])
                    exited += 1
                    exit_qty += qty
                    ages.append(int(exit_row["timestamp"]) - int(fill.timestamp))
                    roundtrip += (exit_bid - entry) * qty
                    delta_vs_hold += (exit_bid - final_mid) * qty
                policy_rows.append(
                    {
                        "target_ticks": target,
                        "max_age": max_age,
                        "force_mode": force_mode,
                        "exited_lots": exited,
                        "exit_qty": int(exit_qty),
                        "avg_exit_age": float(np.mean(ages)) if ages else np.nan,
                        "realized_roundtrip_pnl": roundtrip,
                        "delta_vs_hold_to_end": delta_vs_hold,
                        "projected_delta_vs_validated": q5_delta + delta_vs_hold,
                    }
                )

    horizon_df = pd.DataFrame(horizon_rows).sort_values(
        "projected_delta_vs_validated", ascending=False
    )
    policy_df = pd.DataFrame(policy_rows).sort_values(
        ["projected_delta_vs_validated", "realized_roundtrip_pnl"], ascending=False
    )

    opportunity = pd.read_csv(MARK55_OPPORTUNITY)
    opp = opportunity[
        opportunity["dataset"].eq("official_sellonly")
        & opportunity["gate"].isin(["mark67_count_ge3", "always", "anti_mark67"])
        & opportunity["fill_model"].isin(["inside_m55_100pct", "inside_all_100pct"])
    ].copy()
    opp.sort_values(["gate", "fill_model"], inplace=True)

    horizon_df.to_csv(out_dir / "mark55_recycler_horizon_counterfactual.csv", index=False)
    policy_df.to_csv(out_dir / "mark55_recycler_policy_counterfactual.csv", index=False)
    opp.to_csv(out_dir / "mark55_official_opportunity_focus.csv", index=False)
    return horizon_df, policy_df, opp


def review_mark22(out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    loo = pd.read_csv(LOO_GATES)
    cond = pd.read_csv(CONDITIONED_EDGES)
    reserve = pd.read_csv(RESERVE_PROBE)

    active_sell = loo[
        loo["feature"].astype(str).str.contains("m22")
        & loo["chosen_states"].astype(str).str.contains("active")
        & loo["signal_side"].eq("sell")
        & loo["state_consistent"].eq(1)
        & (loo["positive_holdouts"] == 3)
        & (loo["min_holdout_n"] >= 30)
    ].copy()
    active_sell = active_sell[
        [
            "product",
            "signal_side",
            "horizon",
            "feature",
            "window",
            "mean_test_uplift",
            "min_test_uplift",
            "min_holdout_n",
            "day1_test_uplift",
            "day2_test_uplift",
            "day3_test_uplift",
        ]
    ].sort_values(["mean_test_uplift", "min_test_uplift"], ascending=False)

    otm_buy = cond[
        cond["feature"].astype(str).str.contains("m22")
        & cond["signal_side"].eq("buy")
        & cond["product"].isin(["VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300"])
        & (cond["horizon"] >= 30_000)
        & (cond["sign_agree_days"] == 3)
        & (cond["min_day_uplift"] > 0)
        & (cond["feature_n"] >= 100)
    ].copy()
    otm_buy = otm_buy[
        [
            "product",
            "signal_side",
            "horizon",
            "feature",
            "window",
            "feature_n",
            "feature_mean",
            "no_feature_mean",
            "uplift_vs_no_feature",
            "min_day_uplift",
            "day1_uplift",
            "day2_uplift",
            "day3_uplift",
        ]
    ].sort_values(["uplift_vs_no_feature", "min_day_uplift"], ascending=False)

    reserve_focus = reserve[
        [
            "label",
            "total_pnl",
            "orders_trimmed",
            "qty_trimmed",
            "trigger_count",
            "pnl_VEV_5000",
            "pnl_VEV_5100",
        ]
    ].copy()

    active_sell.to_csv(out_dir / "mark22_active_sell_gates.csv", index=False)
    otm_buy.to_csv(out_dir / "mark22_otm_buy_conditioning.csv", index=False)
    reserve_focus.to_csv(out_dir / "mark22_capacity_reserve_focus.csv", index=False)
    return active_sell, otm_buy, reserve_focus


def review_hyd(out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    unique = pd.read_csv(HYD_UNIQUE)
    buckets = pd.read_csv(HYD_BUCKETS)
    candidates = pd.read_csv(HYD_CANDIDATES)

    unique_focus = unique[
        [
            "side",
            "counterparty",
            "rows",
            "qty",
            "first_ts",
            "last_ts",
            "avg_markout_1000",
            "avg_markout_5000",
            "avg_markout_30000",
            "avg_markout_end",
            "avg_flatten_advantage_1000",
            "avg_flatten_advantage_5000",
            "avg_flatten_advantage_30000",
        ]
    ].copy()
    unique_focus.sort_values(["side", "qty"], ascending=[True, False], inplace=True)

    bucket_focus = buckets[
        [
            "bucket",
            "side",
            "counterparty",
            "qty",
            "avg_mo_1k",
            "avg_mo_5k",
            "avg_mo_30k",
            "avg_mo_end",
        ]
    ].copy()

    candidate_focus = candidates[
        [
            "label",
            "total_pnl",
            "hyd_pnl",
            "hyd_final_pos",
            "hyd_abs_qty",
            "hyd_first_fill_ts",
            "hyd_last_fill_ts",
        ]
    ].head(12)

    unique_focus.to_csv(out_dir / "hyd_counterparty_wrapper_focus.csv", index=False)
    bucket_focus.to_csv(out_dir / "hyd_counterparty_time_confounds.csv", index=False)
    candidate_focus.to_csv(out_dir / "hyd_official_candidate_focus.csv", index=False)
    return unique_focus, bucket_focus, candidate_focus


def write_report(
    doc: Path,
    out_dir: Path,
    mark55_horizon: pd.DataFrame,
    mark55_policy: pd.DataFrame,
    mark55_opp: pd.DataFrame,
    mark22_sell: pd.DataFrame,
    mark22_buy: pd.DataFrame,
    mark22_reserve: pd.DataFrame,
    hyd_unique: pd.DataFrame,
    hyd_buckets: pd.DataFrame,
    hyd_candidates: pd.DataFrame,
) -> None:
    text = f"""# R4 Native Alpha Options Review

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.review_r4_native_alpha_options
```

Artifacts live under `{out_dir}`.

## Executive Read

These are not equal opportunities.

1. **Mark55/Mark67 VELVET** is real but small. The current q5 upload proved we
   can attract mostly Mark55 sells, but holding those fills reduced the core
   profitable VELVET short. A recycler can probably recover tens to a few
   hundred PnL in the 100k slice, not the missing theoretical maximum.
2. **Mark22 option basket flow** is the most coherent R4 information signal,
   but it is mostly a regime/timing conditioner. It should shape option
   recycling and schedule sizing; it should not replace the price/Greek
   framework with a broad "Mark22 = trade" rule.
3. **HYDROGEL own-fill counterparty** is not a standalone edge yet. Timestamp
   and high-regime state dominate the Mark ID. The useful lesson is what not to
   do: do not stop out profitable HYD sells because short markouts are bad.

## 1. Mark55 Recycler

The q5 official upload bought 50 extra VELVET units and lost `65.81` versus the
validated baseline, entirely in VELVET. The counterparty filter worked: those
fills were mostly against Mark55. The failure was inventory horizon, not
prediction.

Conservative counterfactual using future **bid** exits:

{markdown_table(mark55_horizon, max_rows=12)}

Top target/age recycler policies:

{markdown_table(mark55_policy, max_rows=12)}

Official opportunity focus:

{markdown_table(mark55_opp, max_rows=12)}

Read: this is upload-calibratable, but not where the large edge lives. The best
version is a tiny passive fill plus quick re-short. The worst version is what
we already uploaded: passive fill plus terminal hold.

## 2. Mark22 Option Basket

Strong historical leave-one-day active sell conditioners:

{markdown_table(mark22_sell, max_rows=12)}

OTM-voucher sell flow also conditions longer-horizon buy quality:

{markdown_table(mark22_buy, max_rows=12)}

Capacity-reserve test:

{markdown_table(mark22_reserve, max_rows=8)}

Read: Mark22 is useful as a state variable, but current capacity-reserve logic
does not extract anything locally. The better use is to combine Mark22 state
with the VELVET/options recycler family: short-horizon sell/reduce actions in
VEV_5000/VEV_5100, and maybe guarded long-recycle in VEV_5200/VEV_5300. The
official 100k schedule calibration was mixed: short-horizon VEV_5000/5100 sell
edges improved during Mark22 windows, but 30k edges were inconsistent.

## 3. HYD Own-Fill Counterparty

Deduplicated official own-fill summary:

{markdown_table(hyd_unique, max_rows=12)}

Time-bucket confound:

{markdown_table(hyd_buckets, max_rows=12)}

Official HYD-containing candidates:

{markdown_table(hyd_candidates, max_rows=12)}

Read: HYD alpha is regime/timing/inventory design, not counterparty ID. Mark14
sells look excellent to terminal because they occur in the profitable short
regime; the same Mark14 ID on buys is terminal-toxic. A pure Mark wrapper would
confuse cause and effect.

## Upload Implications

- Upload-worthy diagnostic: **Mark55 recycler**, because it directly tests the
  only counterparty exploit that has already produced target fills.
- Upload-worthy but lower priority: **Mark22 micro/recycler**, only if paired
  with a negative control of similar frequency.
- Not upload-worthy yet: **HYD pure counterparty wrapper**. Keep HYD work in the
  isolation thread focused on high-regime release and terminal exposure.

## Critical Interpretation

Round 4 alpha is not absent, but it is not a magic Mark label either. The new
mechanic gives us three things:

1. A way to anticipate/passively catch specific liquidity takers.
2. A regime variable for option schedule quality.
3. A post-fill diagnostic for whether our inventory is alpha or risk control.

Only the first is a literal bot exploit, and its observed size is small. The
big PnL gap still seems to come from inventory allocation in HYDROGEL and the
VELVET/options complex, with Mark flow acting as a conditioner rather than the
main engine.
"""
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text)


def run(out_dir: Path, doc: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    mark55_horizon, mark55_policy, mark55_opp = review_mark55_recycler(out_dir)
    mark22_sell, mark22_buy, mark22_reserve = review_mark22(out_dir)
    hyd_unique, hyd_buckets, hyd_candidates = review_hyd(out_dir)
    write_report(
        doc,
        out_dir,
        mark55_horizon,
        mark55_policy,
        mark55_opp,
        mark22_sell,
        mark22_buy,
        mark22_reserve,
        hyd_unique,
        hyd_buckets,
        hyd_candidates,
    )
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print("\nMark55 recycler policies")
    print(mark55_policy.head(12).to_string(index=False))
    print("\nMark22 active sell gates")
    print(mark22_sell.head(12).to_string(index=False))
    print("\nHYD counterparty focus")
    print(hyd_unique.head(12).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    run(args.out_dir, args.doc)


if __name__ == "__main__":
    main()
