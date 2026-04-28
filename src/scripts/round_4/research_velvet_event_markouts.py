"""Event-level VELVET markout and final robustness readout.

This is intentionally narrow. It tests whether the profitable VELVET sleeve is
earning from short-horizon reaction/quote lag, or mostly from inventory/terminal
mark exposure. It is research code, not a submission.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    DEFAULT_OFFICIAL_DIR,
    UNDERLYING,
    load_historical,
    load_official_books,
)
from src.scripts.round_4.test_core_recycler_probes import markdown_table


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_event_markouts"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_EVENT_MARKOUTS_AND_ROBUSTNESS.md"
OFFICIAL_PROBE_OUT = REPO_ROOT / "outputs" / "round_4" / "velvet_official_probe_batch"
ROLLING_OUT = REPO_ROOT / "outputs" / "round_4" / "velvet_rolling_regime"
OPTION_NATIVE_OUT = REPO_ROOT / "outputs" / "round_4" / "option_native_engine"

HORIZONS = (1_000, 5_000, 10_000, 30_000, 100_000)
RULE_HORIZON = 30_000


def _scope(dataset: str) -> str:
    return "official" if str(dataset).startswith("official") else "historical"


def _load_prices(data_dir: Path, official_dir: Path) -> pd.DataFrame:
    historical = load_historical(data_dir)
    official_books, _ = load_official_books(official_dir)
    official = [
        book
        for name, book in official_books.items()
        if name in {"official_sell7_validated", "official_disabled", "official_sellonly8"}
    ]
    prices = pd.concat([historical, *official], ignore_index=True)
    velvet = prices[prices["product"].eq(UNDERLYING)].copy()
    return velvet.sort_values(["dataset", "day", "timestamp"]).reset_index(drop=True)


def _enrich(prices: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for (dataset, day), group in prices.groupby(["dataset", "day"], sort=False):
        group = group.sort_values("timestamp").reset_index(drop=True).copy()
        bid = pd.to_numeric(group["bid_price_1"], errors="coerce")
        ask = pd.to_numeric(group["ask_price_1"], errors="coerce")
        mid = pd.to_numeric(group["mid_price"], errors="coerce")
        bid_vol = pd.to_numeric(group["bid_volume_1"], errors="coerce").fillna(0.0).abs()
        ask_vol = pd.to_numeric(group["ask_volume_1"], errors="coerce").fillna(0.0).abs()
        denom = (bid_vol + ask_vol).replace(0, np.nan)
        group["spread"] = ask - bid
        group["imbalance"] = (bid_vol - ask_vol) / denom
        group["microprice"] = (ask * bid_vol + bid * ask_vol) / denom
        group["micro_mid_gap"] = group["microprice"] - mid
        group["open_mid"] = float(mid.iloc[0])
        group["final_mid"] = float(mid.iloc[-1])
        group["open_drop"] = group["open_mid"] - mid
        group["open_gain"] = mid - group["open_mid"]
        group["peak_mid"] = mid.cummax()
        group["trough_mid"] = mid.cummin()
        group["peak_drawdown"] = group["peak_mid"] - mid
        group["rebound_from_trough"] = mid - group["trough_mid"]
        if len(group) > 1:
            step = int(np.nanmedian(np.diff(group["timestamp"].to_numpy(dtype=int))))
            step = max(step, 1)
        else:
            step = 100
        for horizon in HORIZONS:
            steps = max(1, int(round(horizon / step)))
            group[f"bid_fwd_{horizon}"] = bid.shift(-steps)
            group[f"ask_fwd_{horizon}"] = ask.shift(-steps)
            group[f"mid_fwd_{horizon}"] = mid.shift(-steps)
        for lookback in (1_000, 5_000, 10_000):
            steps = max(1, int(round(lookback / step)))
            group[f"move_back_{lookback}"] = mid - mid.shift(steps)
        frames.append(group)
    out = pd.concat(frames, ignore_index=True)
    out["dataset_scope"] = out["dataset"].map(_scope)
    return out


def _rule_masks(df: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    ask = pd.to_numeric(df["ask_price_1"], errors="coerce")
    bid = pd.to_numeric(df["bid_price_1"], errors="coerce")
    spread = pd.to_numeric(df["spread"], errors="coerce")
    imb = pd.to_numeric(df["imbalance"], errors="coerce")
    ts = pd.to_numeric(df["timestamp"], errors="coerce")
    open_drop = pd.to_numeric(df["open_drop"], errors="coerce")
    drawdown = pd.to_numeric(df["peak_drawdown"], errors="coerce")
    rebound = pd.to_numeric(df["rebound_from_trough"], errors="coerce")
    move5 = pd.to_numeric(df["move_back_5000"], errors="coerce")
    move10 = pd.to_numeric(df["move_back_10000"], errors="coerce")
    return [
        ("base_buy_ask_le_5246", "buy", ask <= 5246),
        ("active_buy_ask_le_5248", "buy", ask <= 5248),
        ("base_sell_bid_ge_5272", "sell", bid >= 5272),
        ("active_sell_bid_ge_5264", "sell", bid >= 5264),
        ("gate30_drop20_buy_5248", "buy", (ts >= 30_000) & (open_drop >= 20) & (ask <= 5248)),
        ("gate50_drop20_buy_5248", "buy", (ts >= 50_000) & (open_drop >= 20) & (ask <= 5248)),
        ("drawdown20_buy_5248", "buy", (drawdown >= 20) & (ask <= 5248)),
        ("drawdown25_buy_5248", "buy", (drawdown >= 25) & (ask <= 5248)),
        ("drawdown20_rebound3_buy_5248", "buy", (drawdown >= 20) & (rebound >= 3) & (ask <= 5248)),
        ("drop20_lowspread_posimb_buy", "buy", (open_drop >= 20) & (ask <= 5248) & (spread <= 6) & (imb > 0)),
        ("move5_down10_buy_5248", "buy", (move5 <= -10) & (ask <= 5248)),
        ("move10_down15_buy_5248", "buy", (move10 <= -15) & (ask <= 5248)),
        ("move5_up10_sell_5264", "sell", (move5 >= 10) & (bid >= 5264)),
        ("move10_up15_sell_5264", "sell", (move10 >= 15) & (bid >= 5264)),
    ]


def _touch_pnl(df: pd.DataFrame, side: str, horizon: int) -> pd.Series:
    if side == "buy":
        return pd.to_numeric(df[f"bid_fwd_{horizon}"], errors="coerce") - pd.to_numeric(df["ask_price_1"], errors="coerce")
    return pd.to_numeric(df["bid_price_1"], errors="coerce") - pd.to_numeric(df[f"ask_fwd_{horizon}"], errors="coerce")


def _terminal_pnl(df: pd.DataFrame, side: str) -> pd.Series:
    final_mid = pd.to_numeric(df["final_mid"], errors="coerce")
    if side == "buy":
        return final_mid - pd.to_numeric(df["ask_price_1"], errors="coerce")
    return pd.to_numeric(df["bid_price_1"], errors="coerce") - final_mid


def rule_markouts(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows = []
    summary_rows = []
    for rule, side, mask in _rule_masks(features):
        selected = features[mask.fillna(False)].copy()
        if selected.empty:
            continue
        selected["rule"] = rule
        selected["side"] = side
        selected["terminal_pnl"] = _terminal_pnl(selected, side)
        for horizon in HORIZONS:
            selected[f"touch_pnl_{horizon}"] = _touch_pnl(selected, side, horizon)
        keep = [
            "dataset",
            "dataset_scope",
            "day",
            "timestamp",
            "rule",
            "side",
            "bid_price_1",
            "ask_price_1",
            "mid_price",
            "spread",
            "imbalance",
            "open_drop",
            "peak_drawdown",
            "rebound_from_trough",
            "move_back_5000",
            "move_back_10000",
            "terminal_pnl",
            *[f"touch_pnl_{h}" for h in HORIZONS],
        ]
        detail_rows.append(selected[keep])
        for scope_name, scope_df in (
            ("all", selected),
            ("historical", selected[selected["dataset_scope"].eq("historical")]),
            ("official", selected[selected["dataset_scope"].eq("official")]),
        ):
            if scope_df.empty:
                continue
            for horizon in HORIZONS:
                pnl = scope_df[f"touch_pnl_{horizon}"].dropna()
                if pnl.empty:
                    continue
                summary_rows.append(
                    {
                        "rule": rule,
                        "side": side,
                        "dataset_scope": scope_name,
                        "horizon": horizon,
                        "events": int(len(pnl)),
                        "mean_touch_pnl": float(pnl.mean()),
                        "median_touch_pnl": float(pnl.median()),
                        "hit_rate": float((pnl > 0).mean()),
                        "p10_touch_pnl": float(pnl.quantile(0.10)),
                        "p90_touch_pnl": float(pnl.quantile(0.90)),
                        "mean_terminal_pnl": float(scope_df["terminal_pnl"].mean(skipna=True)),
                    }
                )
    detail = pd.concat(detail_rows, ignore_index=True) if detail_rows else pd.DataFrame()
    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        summary = summary.sort_values(["dataset_scope", "horizon", "mean_touch_pnl"], ascending=[True, True, False])
    return detail, summary


def official_fill_markouts(features: pd.DataFrame) -> pd.DataFrame:
    trade_path = OFFICIAL_PROBE_OUT / "official_probe_batch_velvet_trade_path.csv"
    if not trade_path.exists():
        return pd.DataFrame()
    trades = pd.read_csv(trade_path)
    if trades.empty:
        return pd.DataFrame()
    official = features[features["dataset"].eq("official_sell7_validated")].copy()
    market = official.set_index("timestamp")
    rows = []
    for row in trades.itertuples(index=False):
        ts = int(row.timestamp)
        if ts not in market.index:
            continue
        m = market.loc[ts]
        side = str(row.side).lower()
        record = {
            "candidate": str(row.candidate),
            "timestamp": ts,
            "side": side,
            "price": float(row.price),
            "qty": int(row.qty),
            "pos_after": int(row.pos_after),
        }
        if side == "buy":
            record["terminal_pnl_per_unit"] = float(m["final_mid"]) - float(row.price)
            for horizon in HORIZONS:
                record[f"touch_pnl_{horizon}"] = float(m[f"bid_fwd_{horizon}"]) - float(row.price) if pd.notna(m[f"bid_fwd_{horizon}"]) else np.nan
        else:
            record["terminal_pnl_per_unit"] = float(row.price) - float(m["final_mid"])
            for horizon in HORIZONS:
                record[f"touch_pnl_{horizon}"] = float(row.price) - float(m[f"ask_fwd_{horizon}"]) if pd.notna(m[f"ask_fwd_{horizon}"]) else np.nan
        rows.append(record)
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail
    summary_rows = []
    for (candidate, side), group in detail.groupby(["candidate", "side"], sort=False):
        row = {
            "candidate": candidate,
            "side": side,
            "fills": int(len(group)),
            "qty": int(group["qty"].sum()),
            "mean_terminal_pnl_per_unit": float(group["terminal_pnl_per_unit"].mean()),
            "qty_weighted_terminal_pnl": float((group["terminal_pnl_per_unit"] * group["qty"]).sum()),
        }
        for horizon in HORIZONS:
            pnl = group[f"touch_pnl_{horizon}"].dropna()
            row[f"mean_touch_pnl_{horizon}"] = float(pnl.mean()) if not pnl.empty else np.nan
            row[f"hit_touch_{horizon}"] = float((pnl > 0).mean()) if not pnl.empty else np.nan
            row[f"qty_weighted_touch_pnl_{horizon}"] = float((group[f"touch_pnl_{horizon}"] * group["qty"]).sum(skipna=True))
        summary_rows.append(row)
    return pd.DataFrame(summary_rows).sort_values(["candidate", "side"])


def _load_existing(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write_report(
    doc: Path,
    out_dir: Path,
    rule_summary: pd.DataFrame,
    fill_summary: pd.DataFrame,
    rolling_summary: pd.DataFrame,
    official_batch: pd.DataFrame,
    option_native_summary: pd.DataFrame,
) -> None:
    top_30k = rule_summary[
        (rule_summary["horizon"].eq(RULE_HORIZON)) & (rule_summary["dataset_scope"].isin(["historical", "official"]))
    ].sort_values(["dataset_scope", "mean_touch_pnl"], ascending=[True, False])
    buy_30k = top_30k[top_30k["side"].eq("buy")]
    sell_30k = top_30k[top_30k["side"].eq("sell")]
    robust_view = rolling_summary.sort_values(["all_mean_delta", "active_min_delta"], ascending=False) if not rolling_summary.empty else pd.DataFrame()
    official_view = official_batch.sort_values("delta_vs_sell7", ascending=False) if not official_batch.empty else pd.DataFrame()
    option_view = option_native_summary.sort_values(["dataset", "total_pnl"], ascending=[True, False]) if not option_native_summary.empty else pd.DataFrame()

    text = f"""# VELVET Event Markouts and Robustness Decision

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.research_velvet_event_markouts
```

Artifacts live under `{out_dir}`.

## Decision

The event-level evidence shows a **small real short-horizon VELVET effect**:
recent sharp down-move buys and high-price sells have positive 30k
touch-to-touch markouts. So VELVET is not purely terminal luck.

However, this is not automatically uploadable alpha. The effect is small,
overlapping, and quickly becomes an inventory-control problem. The bounded
position-limited follow-up in `VELVET_EVENT_HARDENED_PROBES.md` is the
promotion test; it did not produce a clean new final candidate.

Net: use this as evidence for why the existing sleeve works, not as permission
to open another broad parameter sweep.

## 30k Touch Markouts

Rules pay the current touch and exit at the future opposite touch. Positive
terminal PnL without positive short-horizon touch PnL is terminal exposure, not
reaction-lag alpha.

Buy-side rules:

{markdown_table(buy_30k, max_rows=80)}

Sell-side rules:

{markdown_table(sell_30k, max_rows=80)}

## Official Upload Fill Markouts

These are actual official-upload VELVET fills, marked against the official
market path. The key read is whether fills worked before terminal marking.

{markdown_table(fill_summary, max_rows=80)}

## Existing Official Probe Frontier

{markdown_table(official_view, max_rows=40)}

## Existing Rolling-Robustness Frontier

{markdown_table(robust_view, max_rows=80)}

## Option-Native Sanity Check

Recent standalone option-native engines are included only as a guardrail: we
should not reopen this path unless new evidence appears.

{markdown_table(option_view, max_rows=80)}

## Final Robustness Read

For final 1M, the VELVET decision is now mostly risk preference:

- Maximum official-100k calibrated EV: keep `probe_stack` / `expstack8060`.
- More robust VELVET-only posture: prefer `delayed_gate50_v5248_5264` or the
  uploaded `delayed_full` style, which gives up official upside but had the
  cleanest public-window left tail.
- Do not add rolling drawdown controllers; they overfire.
- Do not add vanilla Greek/smile/stale-quote sleeves; current evidence is
  negative after touch costs.

My recommendation is to keep `expstack8060` as the current best full-stack
candidate if optimizing leaderboard EV, and keep a delayed/plus80 VELVET file
as the robustness hedge. I would not create another VELVET upload candidate
from event markouts alone.
"""
    doc.write_text(text)


def run(data_dir: Path, official_dir: Path, out_dir: Path, doc: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)

    features = _enrich(_load_prices(data_dir, official_dir))
    detail, rule_summary = rule_markouts(features)
    fill_summary = official_fill_markouts(features)
    rolling_summary = _load_existing(ROLLING_OUT / "velvet_rolling_window_summary.csv")
    official_batch = _load_existing(OFFICIAL_PROBE_OUT / "official_probe_batch_summary.csv")
    option_native_summary = _load_existing(OPTION_NATIVE_OUT / "option_native_summary.csv")

    features.to_csv(out_dir / "velvet_event_features.csv", index=False)
    detail.to_csv(out_dir / "velvet_event_rule_detail.csv", index=False)
    rule_summary.to_csv(out_dir / "velvet_event_rule_summary.csv", index=False)
    fill_summary.to_csv(out_dir / "velvet_official_fill_markout_summary.csv", index=False)
    write_report(doc, out_dir, rule_summary, fill_summary, rolling_summary, official_batch, option_native_summary)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    view = rule_summary[
        (rule_summary["horizon"].eq(RULE_HORIZON)) & (rule_summary["dataset_scope"].isin(["historical", "official"]))
    ].sort_values(["dataset_scope", "mean_touch_pnl"], ascending=[True, False])
    print(view.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-dir", type=Path, default=DEFAULT_OFFICIAL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    run(args.data_dir, args.official_dir, args.out_dir, args.doc)


if __name__ == "__main__":
    main()
