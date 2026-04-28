"""Analyze the official VELVET probe ladder uploads.

This reads the five official simulator zip files for the VELVET ladder and
compares them against validated sell7 and the earlier probe_stack upload.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SIM_DIR = REPO_ROOT / "r4 Sim Results"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_official_probe_batch"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_OFFICIAL_PROBE_BATCH_READOUT.md"

BASE_RUNS = {
    "sell7_validated": Path("validated/511763.json"),
    "probe_stack": Path("probe/513378.json"),
    "expstack8060": Path("expstack8060/516313.json"),
}

PROBE_ZIPS = {
    "one_shot": Path("velvet one shot.zip"),
    "negative_control": Path("velvet negative control.zip"),
    "plus80": Path("velvet plus 80.zip"),
    "delayed_full": Path("velvet full recycle.zip"),
    "rolling_diagnostic": Path("velvet diagnostic.zip"),
}

VELVET_PRODUCTS = [
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
]


def _read_json(sim_dir: Path, rel: Path) -> dict:
    path = sim_dir / rel
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            name = next(name for name in zf.namelist() if name.endswith(".json"))
            return json.loads(zf.read(name))
    return json.loads(path.read_text())


def _read_log(sim_dir: Path, rel: Path) -> dict | None:
    path = sim_dir / rel
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            name = next(name for name in zf.namelist() if name.endswith(".log"))
            return json.loads(zf.read(name))
    log_path = path.with_suffix(".log")
    if log_path.exists():
        return json.loads(log_path.read_text())
    return None


def _activities(payload: dict) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")


def _product_final(payload: dict) -> dict[str, float]:
    df = _activities(payload)
    final = df.sort_values("timestamp").groupby("product", as_index=False).tail(1)
    return {
        str(row.product): float(row.profit_and_loss)
        for row in final.itertuples(index=False)
    }


def _positions(payload: dict) -> dict[str, int]:
    return {
        str(row["symbol"]): int(row["quantity"])
        for row in payload.get("positions", [])
    }


def _submission_trades(log_payload: dict | None) -> pd.DataFrame:
    if not log_payload:
        return pd.DataFrame()
    trades = pd.DataFrame(log_payload.get("tradeHistory", []))
    if trades.empty:
        return pd.DataFrame()
    trades = trades[
        trades["buyer"].eq("SUBMISSION") | trades["seller"].eq("SUBMISSION")
    ].copy()
    if trades.empty:
        return trades
    trades["signed_qty"] = trades.apply(
        lambda row: int(row["quantity"])
        if row["buyer"] == "SUBMISSION"
        else -int(row["quantity"]),
        axis=1,
    )
    return trades.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _markdown_table(df: pd.DataFrame, max_rows: int = 80) -> str:
    if df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy()
    for column in view.columns:
        if pd.api.types.is_float_dtype(view[column]):
            view[column] = view[column].map(lambda value: f"{value:.2f}")
    headers = list(view.columns)
    rows = [headers, ["---"] * len(headers)]
    rows.extend([[str(row[column]) for column in headers] for _, row in view.iterrows()])
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    lines = []
    for i, row in enumerate(rows):
        lines.append("| " + " | ".join(row[j].ljust(widths[j]) for j in range(len(headers))) + " |")
        if i == 0:
            continue
    return "\n".join(lines[:1] + ["| " + " | ".join("-" * widths[j] for j in range(len(headers))) + " |"] + lines[2:])


def analyze(sim_dir: Path, out_dir: Path, doc: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)

    rels = {**BASE_RUNS, **PROBE_ZIPS}
    payloads = {name: _read_json(sim_dir, rel) for name, rel in rels.items()}
    logs = {name: _read_log(sim_dir, rel) for name, rel in rels.items()}
    product_pnls = {name: _product_final(payload) for name, payload in payloads.items()}
    positions = {name: _positions(payload) for name, payload in payloads.items()}

    sell7_profit = float(payloads["sell7_validated"]["profit"])
    probe_profit = float(payloads["probe_stack"]["profit"])
    sell7_complex = sum(product_pnls["sell7_validated"].get(product, 0.0) for product in VELVET_PRODUCTS)

    summary_rows = []
    for name, payload in payloads.items():
        complex_pnl = sum(product_pnls[name].get(product, 0.0) for product in VELVET_PRODUCTS)
        summary_rows.append(
            {
                "candidate": name,
                "profit": float(payload["profit"]),
                "delta_vs_sell7": float(payload["profit"]) - sell7_profit,
                "delta_vs_probe_stack": float(payload["profit"]) - probe_profit,
                "velvet_complex": complex_pnl,
                "velvet_complex_delta": complex_pnl - sell7_complex,
                "hydrogel": product_pnls[name].get("HYDROGEL_PACK", 0.0),
                "velvet_pnl": product_pnls[name].get("VELVETFRUIT_EXTRACT", 0.0),
                "velvet_pos": positions[name].get("VELVETFRUIT_EXTRACT"),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("profit", ascending=False)

    product_rows = []
    base_product = product_pnls["sell7_validated"]
    for name in ["probe_stack", *PROBE_ZIPS.keys()]:
        for product in ["HYDROGEL_PACK", *VELVET_PRODUCTS]:
            pnl = product_pnls[name].get(product, 0.0)
            base = base_product.get(product, 0.0)
            product_rows.append(
                {
                    "candidate": name,
                    "product": product,
                    "pnl": pnl,
                    "base_pnl": base,
                    "delta_vs_sell7": pnl - base,
                    "position": positions[name].get(product),
                }
            )
    product_delta = pd.DataFrame(product_rows)

    trade_summary_rows = []
    trade_path_rows = []
    for name in PROBE_ZIPS:
        trades = _submission_trades(logs[name])
        velvet = trades[trades["symbol"].eq("VELVETFRUIT_EXTRACT")].copy()
        pos = 0
        for row in velvet.itertuples(index=False):
            pos += int(row.signed_qty)
            trade_path_rows.append(
                {
                    "candidate": name,
                    "timestamp": int(row.timestamp),
                    "side": "BUY" if int(row.signed_qty) > 0 else "SELL",
                    "price": float(row.price),
                    "qty": int(abs(row.signed_qty)),
                    "pos_after": pos,
                }
            )
        trade_summary_rows.append(
            {
                "candidate": name,
                "total_submission_trades": int(len(trades)),
                "velvet_trades": int(len(velvet)),
                "velvet_abs_qty": int(velvet["quantity"].sum()) if not velvet.empty else 0,
                "velvet_first_ts": int(velvet["timestamp"].min()) if not velvet.empty else None,
                "velvet_last_ts": int(velvet["timestamp"].max()) if not velvet.empty else None,
                "velvet_final_pos": int(velvet["signed_qty"].sum()) if not velvet.empty else 0,
                "velvet_buy_qty": int(velvet[velvet["signed_qty"] > 0]["quantity"].sum()) if not velvet.empty else 0,
                "velvet_sell_qty": int(velvet[velvet["signed_qty"] < 0]["quantity"].sum()) if not velvet.empty else 0,
            }
        )
    trade_summary = pd.DataFrame(trade_summary_rows)
    trade_path = pd.DataFrame(trade_path_rows)

    expected = pd.DataFrame(
        [
            {"candidate": "one_shot", "expected_local_delta": 2704.5},
            {"candidate": "negative_control", "expected_local_delta": 2279.0},
            {"candidate": "plus80", "expected_local_delta": 2259.0},
            {"candidate": "delayed_full", "expected_local_delta": 1528.5},
            {"candidate": "rolling_diagnostic", "expected_local_delta": 2704.5},
        ]
    ).merge(summary[["candidate", "delta_vs_sell7"]], on="candidate", how="left")
    expected["actual_minus_expected"] = expected["delta_vs_sell7"] - expected["expected_local_delta"]

    summary.to_csv(out_dir / "official_probe_batch_summary.csv", index=False)
    product_delta.to_csv(out_dir / "official_probe_batch_product_delta.csv", index=False)
    trade_summary.to_csv(out_dir / "official_probe_batch_velvet_trade_summary.csv", index=False)
    trade_path.to_csv(out_dir / "official_probe_batch_velvet_trade_path.csv", index=False)
    expected.to_csv(out_dir / "official_probe_expected_vs_actual.csv", index=False)

    high_signal = summary[summary["candidate"].isin(["sell7_validated", "probe_stack", *PROBE_ZIPS.keys()])]
    nonzero_product = product_delta[product_delta["delta_vs_sell7"].abs() > 1e-6].sort_values(
        ["candidate", "delta_vs_sell7"], ascending=[True, False]
    )

    text = f"""# VELVET Official Probe Batch Readout

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_velvet_official_probe_batch
```

Artifacts live under `{out_dir}`.

## Executive Read

The official results validate the implementation and local official-proxy
calibration: every uploaded VELVET probe landed within about `70-113` XIRECS of
its expected delta versus `sell7`.

The mechanism read is less bullish. The matched negative control captured
`{float(summary.loc[summary.candidate.eq('negative_control'), 'delta_vs_sell7'].iloc[0]):.2f}`
of the one-shot's `{float(summary.loc[summary.candidate.eq('one_shot'), 'delta_vs_sell7'].iloc[0]):.2f}`
gain. That is about
`{100 * float(summary.loc[summary.candidate.eq('negative_control'), 'delta_vs_sell7'].iloc[0]) / float(summary.loc[summary.candidate.eq('one_shot'), 'delta_vs_sell7'].iloc[0]):.1f}%`.
So most of the official 100k VELVET edge is terminal/short-cover exposure, not
a robust recycle/re-short structure. The incremental recycle/spread piece is
only about
`{float(summary.loc[summary.candidate.eq('one_shot'), 'delta_vs_sell7'].iloc[0]) - float(summary.loc[summary.candidate.eq('negative_control'), 'delta_vs_sell7'].iloc[0]):.2f}`.

## Candidate Summary

{_markdown_table(high_signal[["candidate", "profit", "delta_vs_sell7", "delta_vs_probe_stack", "velvet_complex", "velvet_complex_delta", "hydrogel", "velvet_pnl", "velvet_pos"]])}

## Expected vs Actual

{_markdown_table(expected)}

## Product Deltas vs Sell7

{_markdown_table(nonzero_product[["candidate", "product", "pnl", "base_pnl", "delta_vs_sell7", "position"]], max_rows=80)}

## VELVET Trade Summary

{_markdown_table(trade_summary)}

## Interpretation

- `one_shot` works officially, but it is not a final proof. It adds
  `+2,806.44` versus `sell7`, all from `VELVETFRUIT_EXTRACT`.
- `negative_control` also works, adding `+2,392.00`. This is the critical
  anti-overfit evidence: the main reward is getting out of the early short and
  carrying favorable terminal exposure.
- `plus80` adds `+2,338.06`, close to the negative control. This says we can
  reduce terminal long risk and keep most of the 100k gain, but it did not beat
  the control.
- `delayed_full` adds `+1,598.83`. It is lower on the official 100k path, but
  had the best public sliding-window left tail before upload. It remains the
  more final-leaning VELVET-only variant.
- `rolling_diagnostic` is identical in realized PnL to `one_shot` on this
  official path. That was possible under the proxy and does not make it robust;
  public windows showed it overfires.
- `probe_stack` still beats the VELVET-only files by `+535.00`, entirely from
  `VEV_5000/5100/5200`. That core add-on is official-positive but fragile in
  public-window tests.

## Decision

Do not treat the one-shot VELVET gate as fully robust alpha. It is a good
official 100k candidate and an additive component, but the control says the
edge is mostly terminal exposure. For final 1M, prefer either:

1. `probe_stack` if maximizing official 100k-calibrated EV and accepting path
   risk; or
2. `delayed_full` / `plus80` style inventory risk control if prioritizing
   robustness over the last `400-1,200` XIRECS of official 100k upside.

The VELVET family has not extracted all theoretical edge. It has extracted the
obvious one-shot official 100k edge. Remaining real alpha likely requires a
new inventory/regime controller, not more tuning around this same gate.
"""
    doc.write_text(text)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-dir", type=Path, default=DEFAULT_SIM_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    analyze(args.sim_dir, args.out_dir, args.doc)


if __name__ == "__main__":
    main()
