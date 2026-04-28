"""Analyze official Mark55 q5 recycler uploads.

Compares the validated baseline, the plain Mark67 q5 probe, the always-q5
control, and the new recycler upload. The key question is whether the recycler
turns the target Mark55 passive fills into realized short-horizon PnL while
restoring the core VELVET short exposure.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_DIR = REPO_ROOT / "r4 Sim Results"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "mark55_recycler_official"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "MARK55_RECYCLER_OFFICIAL_READOUT.md"

VELVET = "VELVETFRUIT_EXTRACT"

DEFAULT_RUNS = {
    "validated": SIM_DIR / "validated" / "511763.log",
    "m67_q5": SIM_DIR / "m67 q5.zip",
    "always_q5": SIM_DIR / "always q5.zip",
    "age10k_recycler": SIM_DIR / "age 10k.zip",
}


def markdown_table(df: pd.DataFrame, *, max_rows: int = 40) -> str:
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


def _read_payload(path: Path) -> tuple[str, dict]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            logs = sorted(name for name in archive.namelist() if name.endswith(".log"))
            if not logs:
                raise ValueError(f"No .log member found in {path}")
            log_name = logs[0]
            return Path(log_name).stem, json.loads(archive.read(log_name).decode())
    return path.stem, json.loads(path.read_text())


def load_run(label: str, path: Path) -> dict[str, object]:
    subid, payload = _read_payload(path)
    activities = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(
            columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"]
        )
    return {"label": label, "subid": subid, "path": path, "activities": activities, "trades": trades}


def _total_pnl(activities: pd.DataFrame) -> pd.Series:
    return activities.groupby("timestamp")["profit_and_loss"].sum().sort_index()


def _product_final_pnl(activities: pd.DataFrame) -> pd.Series:
    return (
        activities.sort_values("timestamp")
        .groupby("product")
        .tail(1)
        .set_index("product")["profit_and_loss"]
    )


def _submission_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    own = trades[
        (trades["buyer"].eq("SUBMISSION")) | (trades["seller"].eq("SUBMISSION"))
    ].copy()
    if own.empty:
        return own
    own["side"] = own.apply(
        lambda row: "buy" if row["buyer"] == "SUBMISSION" else "sell",
        axis=1,
    )
    own["counterparty"] = own.apply(
        lambda row: row["seller"] if row["buyer"] == "SUBMISSION" else row["buyer"],
        axis=1,
    )
    own["signed_qty"] = own.apply(
        lambda row: int(row["quantity"]) if row["buyer"] == "SUBMISSION" else -int(row["quantity"]),
        axis=1,
    )
    own["cash"] = own.apply(
        lambda row: -float(row["price"]) * int(row["quantity"])
        if row["buyer"] == "SUBMISSION"
        else float(row["price"]) * int(row["quantity"]),
        axis=1,
    )
    own.sort_values(["timestamp", "symbol", "side", "price", "quantity"], inplace=True)
    return own.reset_index(drop=True)


def _position_rows(own: pd.DataFrame) -> pd.DataFrame:
    if own.empty:
        return pd.DataFrame()
    rows = []
    for symbol, group in own.groupby("symbol"):
        rows.append(
            {
                "product": symbol,
                "final_pos": int(group["signed_qty"].sum()),
                "abs_qty": int(group["quantity"].sum()),
                "rows": int(len(group)),
                "first_fill": int(group["timestamp"].min()),
                "last_fill": int(group["timestamp"].max()),
                "cash": float(group["cash"].sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("product")


def _summary_rows(runs: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for run in runs:
        activities = run["activities"]
        trades = run["trades"]
        assert isinstance(activities, pd.DataFrame)
        assert isinstance(trades, pd.DataFrame)
        total = _total_pnl(activities)
        products = _product_final_pnl(activities)
        own = _submission_trades(trades)
        positions = _position_rows(own)
        velvet_pos = 0
        velvet_qty = 0
        velvet_rows = 0
        velvet_last = None
        if not positions.empty and (positions["product"] == VELVET).any():
            vrow = positions[positions["product"].eq(VELVET)].iloc[0]
            velvet_pos = int(vrow["final_pos"])
            velvet_qty = int(vrow["abs_qty"])
            velvet_rows = int(vrow["rows"])
            velvet_last = int(vrow["last_fill"])
        rows.append(
            {
                "label": run["label"],
                "subid": run["subid"],
                "final_pnl": float(total.iloc[-1]),
                "max_pnl": float(total.max()),
                "min_pnl": float(total.min()),
                "last_submission_fill": int(own["timestamp"].max()) if not own.empty else None,
                "submission_rows": int(len(own)),
                "submission_abs_qty": int(own["quantity"].sum()) if not own.empty else 0,
                "pnl_HYDROGEL_PACK": float(products.get("HYDROGEL_PACK", 0.0)),
                "pnl_VELVETFRUIT_EXTRACT": float(products.get(VELVET, 0.0)),
                "pnl_VEV_5500": float(products.get("VEV_5500", 0.0)),
                "velvet_final_pos": velvet_pos,
                "velvet_abs_qty": velvet_qty,
                "velvet_rows": velvet_rows,
                "velvet_last_fill": velvet_last,
            }
        )
    out = pd.DataFrame(rows)
    base = out[out["label"].eq("validated")].iloc[0]
    out["delta_vs_validated"] = out["final_pnl"] - float(base["final_pnl"])
    out["velvet_delta_vs_validated"] = (
        out["pnl_VELVETFRUIT_EXTRACT"] - float(base["pnl_VELVETFRUIT_EXTRACT"])
    )
    return out.sort_values("final_pnl", ascending=False)


def _velvet_own_fills(runs: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for run in runs:
        own = _submission_trades(run["trades"])  # type: ignore[arg-type]
        if own.empty:
            continue
        v = own[own["symbol"].eq(VELVET)].copy()
        if v.empty:
            continue
        v["label"] = str(run["label"])
        rows.append(v)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _velvet_counterparty_summary(velvet: pd.DataFrame) -> pd.DataFrame:
    if velvet.empty:
        return pd.DataFrame()
    return (
        velvet.groupby(["label", "side", "counterparty"], sort=False)
        .agg(
            rows=("quantity", "count"),
            qty=("quantity", "sum"),
            avg_price=("price", lambda s: float(s.mean())),
            first_ts=("timestamp", "min"),
            last_ts=("timestamp", "max"),
        )
        .reset_index()
        .sort_values(["label", "side", "qty"], ascending=[True, True, False])
    )


def _age10k_event_path(velvet: pd.DataFrame) -> pd.DataFrame:
    if velvet.empty:
        return pd.DataFrame()
    age = velvet[velvet["label"].eq("age10k_recycler")].copy()
    if age.empty:
        return age
    age = age[["timestamp", "side", "price", "quantity", "counterparty", "signed_qty", "cash"]].copy()
    age["velvet_pos_after"] = age["signed_qty"].cumsum()
    return age


def _delta_fill_compare(velvet: pd.DataFrame) -> pd.DataFrame:
    if velvet.empty:
        return pd.DataFrame()
    labels = ["validated", "m67_q5", "age10k_recycler"]
    frames = []
    for label in labels:
        frame = velvet[velvet["label"].eq(label)].copy()
        frame = frame[
            ["timestamp", "side", "price", "quantity", "counterparty", "signed_qty"]
        ]
        frame["label"] = label
        frames.append(frame)
    all_rows = pd.concat(frames, ignore_index=True)
    key_cols = ["timestamp", "side", "price", "counterparty"]
    pivot = (
        all_rows.groupby(key_cols + ["label"])["quantity"]
        .sum()
        .unstack("label")
        .fillna(0)
        .reset_index()
    )
    for label in labels:
        if label not in pivot.columns:
            pivot[label] = 0
    pivot["age_minus_validated"] = pivot["age10k_recycler"] - pivot["validated"]
    pivot["age_minus_m67_q5"] = pivot["age10k_recycler"] - pivot["m67_q5"]
    out = pivot[(pivot["age_minus_validated"] != 0) | (pivot["age_minus_m67_q5"] != 0)].copy()
    return out.sort_values(["timestamp", "side", "price"])


def write_report(
    doc: Path,
    out_dir: Path,
    summary: pd.DataFrame,
    cp_summary: pd.DataFrame,
    age_path: pd.DataFrame,
    delta_fills: pd.DataFrame,
) -> None:
    age = summary[summary["label"].eq("age10k_recycler")].iloc[0]
    m67 = summary[summary["label"].eq("m67_q5")].iloc[0]
    validated = summary[summary["label"].eq("validated")].iloc[0]
    age_vs_m67 = float(age["final_pnl"]) - float(m67["final_pnl"])
    text = f"""# Mark55 Recycler Official Readout

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_mark55_recycler_official
```

Artifacts live under `{out_dir}`.

## Headline

`age10k_recycler` scored `{float(age['final_pnl']):.2f}`.

Versus:

- validated: `{float(age['delta_vs_validated']):+.2f}`
- plain `m67_q5`: `{float(age['final_pnl'] - float(m67['final_pnl'])):+.2f}`

The recycler improved on the plain q5 probe, but it **did not** restore the
VELVET final position from the q5 failure state:

- validated VELVET pos: `{int(validated['velvet_final_pos'])}`
- m67_q5 VELVET pos: `{int(m67['velvet_final_pos'])}`
- age10k VELVET pos: `{int(age['velvet_final_pos'])}`

That is the key result. The wrapper sold some q5 inventory back, then the
still-active q5 logic refilled it. The net effect versus `m67_q5` was only
`{age_vs_m67:+.2f}`.

## Candidate Summary

{markdown_table(summary, max_rows=20)}

## VELVET Counterparty Attribution

{markdown_table(cp_summary, max_rows=80)}

## age10k VELVET Fill Path

{markdown_table(age_path, max_rows=80)}

## Fill Differences

Rows where age10k differs from validated or m67_q5:

{markdown_table(delta_fills, max_rows=100)}

## Interpretation

This validates one part of the hypothesis and rejects another:

- Validated: Mark55 fills were real and targetable.
- Validated: recycling can add PnL versus plain q5.
- Rejected: age10k as implemented is enough to restore the core `-200`
  structural short.

The implementation is leaky because the inner q5 probe still targets `-150`.
Whenever the recycler sells back, it reopens q5 capacity, so later Mark55/67
fills refill the position. The result is a small execution gain versus `m67_q5`,
but still worse than validated because the strategy finishes with the same
unwanted `-150` VELVET exposure.

The next probe should be a **single-lot/no-refill recycler**: allow a q5 buy
only when VELVET is already at `-200` and no q5 lot is outstanding, block
further q5 buys until the lot is recycled, then repeat. That tests the execution
edge without allowing the overlay to become a permanent long inventory sleeve.
"""
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text)


def run(runs: dict[str, Path], out_dir: Path, doc: Path) -> None:
    loaded = [load_run(label, path) for label, path in runs.items()]
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = _summary_rows(loaded)
    velvet = _velvet_own_fills(loaded)
    cp_summary = _velvet_counterparty_summary(velvet)
    age_path = _age10k_event_path(velvet)
    delta_fills = _delta_fill_compare(velvet)

    summary.to_csv(out_dir / "mark55_recycler_official_summary.csv", index=False)
    velvet.to_csv(out_dir / "mark55_recycler_velvet_own_fills.csv", index=False)
    cp_summary.to_csv(out_dir / "mark55_recycler_counterparty_summary.csv", index=False)
    age_path.to_csv(out_dir / "mark55_recycler_age10k_path.csv", index=False)
    delta_fills.to_csv(out_dir / "mark55_recycler_fill_differences.csv", index=False)
    write_report(doc, out_dir, summary, cp_summary, age_path, delta_fills)
    print(summary.to_string(index=False))
    print()
    print(cp_summary.to_string(index=False))
    print()
    print(age_path.to_string(index=False))
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    run(DEFAULT_RUNS, args.out_dir, args.doc)


if __name__ == "__main__":
    main()
