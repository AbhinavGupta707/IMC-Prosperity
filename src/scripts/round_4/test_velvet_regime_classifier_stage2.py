"""Targeted VELVET regime-classifier stage 2.

Stage 1 found that counterparty/liquidity features were not robust enough by
themselves, while "still pinned near the trough" path-shape features survived
leave-one-day screening. This script tests that specific hypothesis as a
strategy, using denser public 100k windows before looking at the official 100k.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    FLATTEN_START,
    SELL7_SCHEDULES,
    UNDERLYING,
    _schedule_for,
    load_historical,
)
from src.scripts.round_4.research_velvet_regime_classifier import (
    DEFAULT_OFFICIAL_LOG,
    GateRule,
    _rule_active,
    _windowed_prices_and_features,
    build_feature_lookup,
    build_features,
    load_historical_trades,
    load_official,
    summarize_windows,
)
from src.scripts.round_4.test_core_recycler_probes import _volume, markdown_table


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_regime_classifier_stage2"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_REGIME_CLASSIFIER_STAGE2.md"


def rules() -> list[GateRule]:
    return [
        GateRule("ref_open20_30k", "open", 20, 30_000),
        GateRule("ref_open20_50k", "open", 20, 50_000),
        GateRule("path_open20_lowreb4_dur20", "open", 20, 30_000, rebound_max=4, active_duration=20_000),
        GateRule("path_open20_lowreb4_dur40", "open", 20, 30_000, rebound_max=4, active_duration=40_000),
        GateRule("path_open20_lowreb8_dur40", "open", 20, 30_000, rebound_max=8, active_duration=40_000),
        GateRule("path_open20_lowreb12_dur40", "open", 20, 30_000, rebound_max=12, active_duration=40_000),
        GateRule("path_open30_lowreb8_dur40", "open", 30, 30_000, rebound_max=8, active_duration=40_000),
        GateRule("path_open20_lowroll20_dur40", "open", 20, 30_000, roll10k_pos_max=0.20, active_duration=40_000),
        GateRule("path_open20_lowroll30_dur40", "open", 20, 30_000, roll10k_pos_max=0.30, active_duration=40_000),
        GateRule(
            "path_open20_lowreb8_roll30_dur40",
            "open",
            20,
            30_000,
            rebound_max=8,
            roll10k_pos_max=0.30,
            active_duration=40_000,
        ),
        GateRule(
            "path_open20_lowreb8_mom10neg6_dur40",
            "open",
            20,
            30_000,
            rebound_max=8,
            past_move_max=-6,
            active_duration=40_000,
        ),
        GateRule(
            "liq_open20_lowreb8_imbpos_dur40",
            "open",
            20,
            30_000,
            rebound_max=8,
            imbalance_min=0.15,
            active_duration=40_000,
        ),
        GateRule(
            "cp_open20_lowreb8_m22sell6_dur40",
            "open",
            20,
            30_000,
            rebound_max=8,
            mark22_sell_qty30_min=6,
            active_duration=40_000,
        ),
        GateRule(
            "cp_open20_lowreb8_m55sell10_dur40",
            "open",
            20,
            30_000,
            rebound_max=8,
            mark55_sell_qty30_min=10,
            active_duration=40_000,
        ),
    ]


def _simulate_velvet_summary(
    prices: pd.DataFrame,
    features: pd.DataFrame,
    rule: GateRule | None,
    feature_lookup: dict[tuple[str, int, int], dict] | None = None,
) -> pd.DataFrame:
    variant = "sell7_base" if rule is None else rule.label
    if feature_lookup is None:
        feature_lookup = build_feature_lookup(features)
    panel = prices[prices["product"].eq(UNDERLYING)].sort_values(["dataset", "day", "timestamp"])
    rows = []
    for (dataset, day), group in panel.groupby(["dataset", "day"], sort=False):
        position = 0
        cash = 0.0
        last_mid = 0.0
        peak_pnl = -float("inf")
        max_drawdown = 0.0
        active_until = -1
        gate_ever = False
        for row in group.itertuples(index=False):
            timestamp = int(row.timestamp)
            if pd.notna(row.mid_price):
                last_mid = float(row.mid_price)
            active = timestamp <= active_until
            if rule is not None:
                frow = feature_lookup.get((str(dataset), int(day), timestamp))
                if frow is not None and _rule_active(pd.Series(frow), rule):
                    gate_ever = True
                    if rule.active_duration is None:
                        active_until = 10**9
                    else:
                        active_until = max(active_until, timestamp + rule.active_duration)
                    active = True
            if rule is not None and active:
                scfg = {
                    "limit": 200,
                    "max_order": 40,
                    "buy": rule.buy,
                    "sell": rule.sell,
                    "buy_limit": rule.active_buy_limit,
                    "sell_limit": rule.active_sell_limit,
                }
            else:
                scfg = _schedule_for(UNDERLYING, timestamp, SELL7_SCHEDULES)
                if scfg is not None:
                    scfg = dict(scfg)
                    scfg["buy_limit"] = scfg["limit"]
                    scfg["sell_limit"] = scfg["limit"]
            if scfg is not None:
                bid = row.bid_price_1
                ask = row.ask_price_1
                bid_volume = _volume(row.bid_volume_1)
                ask_volume = _volume(row.ask_volume_1)
                if timestamp >= FLATTEN_START:
                    if position > 0 and pd.notna(bid):
                        qty = min(int(scfg["max_order"]), bid_volume, position)
                        if qty > 0:
                            cash += float(bid) * qty
                            position -= qty
                    elif position < 0 and pd.notna(ask):
                        qty = min(int(scfg["max_order"]), ask_volume, -position)
                        if qty > 0:
                            cash -= float(ask) * qty
                            position += qty
                else:
                    if pd.notna(ask) and float(ask) <= int(scfg["buy"]) and position < int(scfg["buy_limit"]):
                        qty = min(int(scfg["max_order"]), ask_volume, int(scfg["buy_limit"]) - position)
                        if qty > 0:
                            cash -= float(ask) * qty
                            position += qty
                    if pd.notna(bid) and float(bid) >= int(scfg["sell"]) and position > -int(scfg["sell_limit"]):
                        qty = min(int(scfg["max_order"]), bid_volume, int(scfg["sell_limit"]) + position)
                        if qty > 0:
                            cash += float(bid) * qty
                            position -= qty
            pnl = cash + position * last_mid
            peak_pnl = max(peak_pnl, pnl)
            max_drawdown = min(max_drawdown, pnl - peak_pnl)
        rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "total_pnl": float(cash + position * last_mid),
                "velvet_pnl": float(cash + position * last_mid),
                "velvet_pos": int(position),
                "max_drawdown": float(max_drawdown),
                "gate_ever_active": bool(gate_ever),
            }
        )
    return pd.DataFrame(rows)


def _run_rules(prices: pd.DataFrame, features: pd.DataFrame, rule_set: list[GateRule], label: str) -> pd.DataFrame:
    lookup = build_feature_lookup(features)
    summaries = []
    for rule in [None, *rule_set]:
        variant = "sell7_base" if rule is None else rule.label
        print(f"{label} simulate {variant}", flush=True)
        summaries.append(_simulate_velvet_summary(prices, features, rule, feature_lookup=lookup))
    return pd.concat(summaries, ignore_index=True)


def _add_deltas(summary: pd.DataFrame) -> pd.DataFrame:
    base = summary[summary["variant"].eq("sell7_base")][["dataset", "day", "total_pnl", "velvet_pnl"]].rename(
        columns={"total_pnl": "base_total", "velvet_pnl": "base_velvet"}
    )
    out = summary.merge(base, on=["dataset", "day"], how="left")
    out["delta_total"] = out["total_pnl"] - out["base_total"]
    out["delta_velvet"] = out["velvet_pnl"] - out["base_velvet"]
    return out


def _full_rank(full_summary: pd.DataFrame) -> pd.DataFrame:
    full = _add_deltas(full_summary)
    rank = (
        full.groupby("variant", sort=False)
        .agg(
            days=("dataset", "count"),
            active_days=("gate_ever_active", "sum"),
            mean_delta=("delta_total", "mean"),
            min_day_delta=("delta_total", "min"),
            max_day_delta=("delta_total", "max"),
            mean_total=("total_pnl", "mean"),
            mean_velvet=("velvet_pnl", "mean"),
            worst_drawdown=("max_drawdown", "min"),
        )
        .reset_index()
    )
    return rank.sort_values(["mean_delta", "min_day_delta"], ascending=False)


def _candidate_read(full_rank: pd.DataFrame, window_rank: pd.DataFrame, official_delta: pd.DataFrame) -> pd.DataFrame:
    official = official_delta[["variant", "delta_total"]].rename(columns={"delta_total": "official_delta"})
    merged = full_rank.merge(window_rank, on="variant", how="left").merge(official, on="variant", how="left")
    merged = merged[~merged["variant"].eq("sell7_base")].copy()
    merged["passes_stage2"] = (
        (merged["mean_delta"] > 0)
        & (merged["min_day_delta"] >= 0)
        & (merged["active_windows"] >= 3)
        & (merged["active_hit_rate"] >= 0.50)
        & (merged["active_p10_delta"] >= -250)
        & (merged["official_delta"] > 0)
    )
    cols = [
        "variant",
        "passes_stage2",
        "mean_delta",
        "min_day_delta",
        "active_windows",
        "active_mean_delta",
        "active_hit_rate",
        "active_p10_delta",
        "official_delta",
    ]
    return merged[cols].sort_values(["passes_stage2", "mean_delta", "official_delta"], ascending=False)


def write_report(
    doc: Path,
    out_dir: Path,
    full_rank: pd.DataFrame,
    window_rank: pd.DataFrame,
    official_delta: pd.DataFrame,
    candidate_read: pd.DataFrame,
    step: int,
    window: int,
) -> None:
    promoted = candidate_read[candidate_read["passes_stage2"]]
    if promoted.empty:
        decision = (
            "No stage-2 classifier passed the non-overfit promotion gate. The best path-shape filters are useful "
            "diagnostics, but they do not yet justify a new upload candidate."
        )
    else:
        labels = ", ".join(promoted["variant"].tolist())
        decision = f"Stage-2 promotion candidates: {labels}."
    official_delta = official_delta.sort_values("delta_total", ascending=False)
    text = f"""# VELVET Regime Classifier Stage 2

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_velvet_regime_classifier_stage2
```

Artifacts live under `{out_dir}`.

## Question

Can the next VELVET alpha come from a more selective regime classifier using
path shape plus liquidity/counterparty filters, rather than another open-drop
threshold? This stage uses a VELVET-only simulator because every candidate here
changes only the underlying; voucher PnL is unchanged, so VELVET delta is the
right quantity to validate.

## Decision

{decision}

## Promotion Gate

A rule must have positive mean public full-day delta, nonnegative worst public
day delta, at least three active public `{window:,}`-tick windows stepped by
`{step:,}`, active-window hit rate at least 50%, active-window p10 no worse than
`-250`, and positive official 100k calibration.

## Candidate Read

{markdown_table(candidate_read, max_rows=80)}

## Public Full Days

{markdown_table(full_rank, max_rows=80)}

## Public Sliding Windows

{markdown_table(window_rank, max_rows=80)}

## Official 100k Calibration

{markdown_table(official_delta, max_rows=80)}

## Interpretation

Stage 1 found the strongest feature evidence in low `trough_rebound` and low
rolling-position states. This stage tests those as executable regimes. The
counterparty/liquidity variants are included only as filters on that path-shape
state; if they cannot improve public robustness, they should not be promoted.
"""
    doc.write_text(text)


def run(data_dir: Path, official_log: Path, out_dir: Path, doc: Path, step: int, window: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    rule_set = rules()

    historical_prices = load_historical(data_dir)
    historical_trades = load_historical_trades(data_dir)
    historical_features = build_features(historical_prices, historical_trades)
    full_summary = _run_rules(historical_prices, historical_features, rule_set, "full")
    full_rank = _full_rank(full_summary)

    window_prices, window_features = _windowed_prices_and_features(historical_prices, historical_features, step=step, window=window)
    window_detail = _run_rules(window_prices, window_features, rule_set, "window")
    window_rank = summarize_windows(window_detail)

    official_prices, official_trades = load_official(official_log)
    official_features = build_features(official_prices, official_trades)
    official_summary = _run_rules(official_prices, official_features, rule_set, "official")
    official_delta = _add_deltas(official_summary)
    candidate_read = _candidate_read(full_rank, window_rank, official_delta)

    full_summary.to_csv(out_dir / "stage2_full_summary.csv", index=False)
    full_rank.to_csv(out_dir / "stage2_full_rank.csv", index=False)
    window_detail.to_csv(out_dir / "stage2_window_detail.csv", index=False)
    window_rank.to_csv(out_dir / "stage2_window_rank.csv", index=False)
    official_summary.to_csv(out_dir / "stage2_official_summary.csv", index=False)
    official_delta.to_csv(out_dir / "stage2_official_delta.csv", index=False)
    candidate_read.to_csv(out_dir / "stage2_candidate_read.csv", index=False)
    write_report(doc, out_dir, full_rank, window_rank, official_delta, candidate_read, step, window)

    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(candidate_read.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_OFFICIAL_LOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--step", type=int, default=25_000)
    parser.add_argument("--window", type=int, default=100_000)
    args = parser.parse_args()
    run(args.data_dir, args.official_log, args.out_dir, args.doc, args.step, args.window)


if __name__ == "__main__":
    main()
