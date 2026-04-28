"""Official HYDROGEL own-fill counterparty attribution.

Round 4 exposes buyer/seller IDs in live own_trades. This script asks whether
that information is useful *after* a HYDROGEL fill:

    If our order filled against Mark 14, Mark 38, Mark 22, etc., did the
    resulting inventory have different short/medium/terminal markouts?

This is intentionally separate from the active HYDROGEL strategy work. It does
not modify a trader. It produces evidence for a possible wrapper rule such as
"after a fill against counterparty X, flatten/recycle faster" or "hold longer".

Important caveat: official uploads share the same hidden 100k market path and
many share the same fills. The script therefore emits both run-weighted and
deduplicated-by-event summaries.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_ROOT = Path("/Users/abhinavgupta/Desktop/IMC/r4 Sim Results")
DEFAULT_OUT_DIR = Path("outputs/round_4/mark_policy/hyd_own_fill_counterparty")
HYD = "HYDROGEL_PACK"
HORIZONS = (100, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 30_000, 50_000)


@dataclass(frozen=True)
class OfficialRun:
    label: str
    subid: str
    source: Path
    activities: pd.DataFrame
    trades: pd.DataFrame


def _read_payload(path: Path) -> tuple[str, dict]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            log_names = sorted(name for name in archive.namelist() if name.endswith(".log"))
            if not log_names:
                raise ValueError(f"No .log member in {path}")
            log_name = log_names[0]
            return Path(log_name).stem, json.loads(archive.read(log_name).decode())
    return path.stem, json.loads(path.read_text())


def _label_for(path: Path) -> str:
    if path.suffix == ".zip":
        return path.stem.replace(" ", "_")
    parent = path.parent.name
    if parent and parent not in {".", "extracted"}:
        return parent.replace(" ", "_")
    return path.stem


def _iter_candidate_files(root: Path) -> list[Path]:
    files = []
    files.extend(sorted(root.rglob("*.log")))
    files.extend(sorted(root.glob("*.zip")))
    return files


def load_runs(root: Path) -> list[OfficialRun]:
    # Deduplicate extracted logs and zip archives by submission id. Prefer an
    # extracted .log over a .zip when both exist because the folder name is
    # usually cleaner.
    by_subid: dict[str, OfficialRun] = {}
    for path in _iter_candidate_files(root):
        try:
            subid, payload = _read_payload(path)
        except Exception as exc:  # pragma: no cover - diagnostic script
            print(f"skipping {path}: {exc}")
            continue
        if subid in by_subid and by_subid[subid].source.suffix == ".log":
            continue
        if subid in by_subid and path.suffix == ".zip":
            continue

        activities = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
        trades = pd.DataFrame(payload.get("tradeHistory", []))
        if trades.empty:
            trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
        run = OfficialRun(
            label=_label_for(path),
            subid=subid,
            source=path,
            activities=activities,
            trades=trades,
        )
        by_subid[subid] = run
    return sorted(by_subid.values(), key=lambda run: (run.label, run.subid))


def _total_pnl(activities: pd.DataFrame) -> pd.Series:
    return activities.groupby("timestamp")["profit_and_loss"].sum().sort_index()


def _product_final_pnl(activities: pd.DataFrame, product: str) -> float:
    rows = activities[activities["product"].eq(product)].sort_values("timestamp")
    if rows.empty:
        return 0.0
    return float(rows.iloc[-1]["profit_and_loss"])


def _hyd_book(activities: pd.DataFrame) -> pd.DataFrame:
    book = activities[activities["product"].eq(HYD)][
        ["timestamp", "bid_price_1", "ask_price_1", "mid_price", "profit_and_loss"]
    ].copy()
    book.sort_values("timestamp", inplace=True)
    for horizon in HORIZONS:
        future = book[["timestamp", "mid_price"]].copy()
        future["timestamp"] = future["timestamp"] - horizon
        book = book.merge(
            future.rename(columns={"mid_price": f"mid_future_{horizon}"}),
            on="timestamp",
            how="left",
        )
    return book


def _own_hyd_trades(run: OfficialRun) -> pd.DataFrame:
    trades = run.trades
    if trades.empty:
        return trades.copy()
    own = trades[
        trades["symbol"].eq(HYD)
        & ((trades["buyer"] == "SUBMISSION") | (trades["seller"] == "SUBMISSION"))
    ].copy()
    if own.empty:
        return own
    own.sort_values(["timestamp", "price", "quantity", "buyer", "seller"], inplace=True)
    own["side"] = np.where(own["buyer"].eq("SUBMISSION"), "buy", "sell")
    own["counterparty"] = np.where(own["buyer"].eq("SUBMISSION"), own["seller"], own["buyer"])
    own["signed_qty"] = np.where(own["side"].eq("buy"), own["quantity"].astype(int), -own["quantity"].astype(int))
    own["cash"] = np.where(
        own["side"].eq("buy"),
        -own["price"].astype(float) * own["quantity"].astype(int),
        own["price"].astype(float) * own["quantity"].astype(int),
    )
    pos = 0
    before = []
    after = []
    for qty in own["signed_qty"].astype(int):
        before.append(pos)
        pos += qty
        after.append(pos)
    own["pos_before"] = before
    own["pos_after"] = after
    return own


def build_fill_records(runs: list[OfficialRun]) -> tuple[pd.DataFrame, pd.DataFrame]:
    record_frames = []
    candidate_rows = []
    for run in runs:
        total = _total_pnl(run.activities)
        hyd_pnl = _product_final_pnl(run.activities, HYD)
        book = _hyd_book(run.activities)
        end_mid = float(book.iloc[-1]["mid_price"]) if not book.empty else np.nan
        own = _own_hyd_trades(run)
        final_pos = int(own["signed_qty"].sum()) if not own.empty else 0
        candidate_rows.append(
            {
                "label": run.label,
                "subid": run.subid,
                "source": str(run.source),
                "total_pnl": float(total.iloc[-1]) if not total.empty else 0.0,
                "hyd_pnl": hyd_pnl,
                "hyd_final_pos": final_pos,
                "hyd_rows": int(len(own)),
                "hyd_abs_qty": int(own["quantity"].sum()) if not own.empty else 0,
                "hyd_first_fill_ts": int(own["timestamp"].min()) if not own.empty else np.nan,
                "hyd_last_fill_ts": int(own["timestamp"].max()) if not own.empty else np.nan,
                "hyd_end_mid": end_mid,
            }
        )
        if own.empty:
            continue
        records = own.merge(book, on="timestamp", how="left")
        records["candidate"] = run.label
        records["subid"] = run.subid
        records["end_mid"] = end_mid
        records["entry_edge_to_mid"] = np.where(
            records["side"].eq("buy"),
            records["mid_price"].astype(float) - records["price"].astype(float),
            records["price"].astype(float) - records["mid_price"].astype(float),
        )
        for horizon in HORIZONS:
            future_col = f"mid_future_{horizon}"
            markout_col = f"markout_{horizon}"
            records[markout_col] = np.where(
                records["side"].eq("buy"),
                records[future_col].astype(float) - records["price"].astype(float),
                records["price"].astype(float) - records[future_col].astype(float),
            )
        records["markout_end"] = np.where(
            records["side"].eq("buy"),
            end_mid - records["price"].astype(float),
            records["price"].astype(float) - end_mid,
        )
        for horizon in HORIZONS:
            records[f"flatten_advantage_{horizon}"] = records[f"markout_{horizon}"] - records["markout_end"]
        record_frames.append(records)

    fill_records = pd.concat(record_frames, ignore_index=True) if record_frames else pd.DataFrame()
    candidate_summary = pd.DataFrame(candidate_rows).sort_values("total_pnl", ascending=False)
    return fill_records, candidate_summary


def _qty_weighted(group: pd.DataFrame, column: str) -> float:
    valid = group.dropna(subset=[column])
    qty = valid["quantity"].astype(float).sum()
    if qty <= 0:
        return np.nan
    return float((valid[column].astype(float) * valid["quantity"].astype(float)).sum() / qty)


def _summarize(grouped: pd.core.groupby.generic.DataFrameGroupBy) -> pd.DataFrame:
    rows = []
    group_names = list(getattr(getattr(grouped, "grouper", None), "names", []) or getattr(grouped._grouper, "names", []))
    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        record = {
            "rows": int(len(group)),
            "qty": int(group["quantity"].sum()),
            "candidate_count": int(group["candidate"].nunique()) if "candidate" in group.columns else np.nan,
            "first_ts": int(group["timestamp"].min()),
            "last_ts": int(group["timestamp"].max()),
            "avg_price": _qty_weighted(group, "price"),
            "avg_entry_edge_to_mid": _qty_weighted(group, "entry_edge_to_mid"),
            "avg_markout_end": _qty_weighted(group, "markout_end"),
        }
        for name, value in zip(group_names, keys, strict=True):
            record[name] = value
        for horizon in HORIZONS:
            record[f"avg_markout_{horizon}"] = _qty_weighted(group, f"markout_{horizon}")
            record[f"avg_flatten_advantage_{horizon}"] = _qty_weighted(group, f"flatten_advantage_{horizon}")
            valid = group.dropna(subset=[f"flatten_advantage_{horizon}"])
            record[f"total_flatten_advantage_{horizon}"] = float(
                (valid[f"flatten_advantage_{horizon}"] * valid["quantity"]).sum()
            )
        rows.append(record)
    out = pd.DataFrame(rows)
    if not out.empty:
        key_cols = [name for name in group_names if name in out.columns]
        out = out[key_cols + [col for col in out.columns if col not in key_cols]]
        out.sort_values(["qty", "rows"], ascending=False, inplace=True)
    return out


def unique_event_records(fill_records: pd.DataFrame) -> pd.DataFrame:
    if fill_records.empty:
        return fill_records.copy()
    rows = []
    group_cols = ["timestamp", "side", "counterparty", "price"]
    for keys, group in fill_records.groupby(group_cols, sort=False):
        row = group.iloc[0].copy()
        row["quantity"] = int(group["quantity"].max())
        row["candidate"] = ",".join(sorted(group["candidate"].unique()))
        row["subid"] = ",".join(sorted(group["subid"].astype(str).unique()))
        row["duplicate_run_count"] = int(len(group))
        for col, value in zip(group_cols, keys, strict=True):
            row[col] = value
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["timestamp", "side", "counterparty", "price"])


def run(root: Path, out_dir: Path) -> None:
    runs = load_runs(root)
    fill_records, candidate_summary = build_fill_records(runs)
    out_dir.mkdir(parents=True, exist_ok=True)

    fill_records.to_csv(out_dir / "hyd_own_fill_records.csv", index=False)
    candidate_summary.to_csv(out_dir / "hyd_candidate_summary.csv", index=False)

    if fill_records.empty:
        print("No HYDROGEL own fills found.")
        return

    runweighted = _summarize(fill_records.groupby(["side", "counterparty"], dropna=False))
    runweighted.to_csv(out_dir / "hyd_counterparty_summary_runweighted.csv", index=False)

    by_candidate = _summarize(fill_records.groupby(["candidate", "side", "counterparty"], dropna=False))
    by_candidate.to_csv(out_dir / "hyd_counterparty_summary_by_candidate.csv", index=False)

    unique = unique_event_records(fill_records)
    unique.to_csv(out_dir / "hyd_own_fill_unique_events.csv", index=False)
    unique_summary = _summarize(unique.groupby(["side", "counterparty"], dropna=False))
    unique_summary.to_csv(out_dir / "hyd_counterparty_summary_unique.csv", index=False)

    print("candidate summary")
    print(
        candidate_summary[
            [
                "label",
                "subid",
                "total_pnl",
                "hyd_pnl",
                "hyd_final_pos",
                "hyd_rows",
                "hyd_abs_qty",
                "hyd_last_fill_ts",
            ]
        ].to_string(index=False)
    )
    print("\nunique event summary by side/counterparty")
    keep_cols = [
        "side",
        "counterparty",
        "rows",
        "qty",
        "candidate_count",
        "avg_price",
        "avg_entry_edge_to_mid",
        "avg_markout_1000",
        "avg_markout_5000",
        "avg_markout_30000",
        "avg_markout_end",
        "avg_flatten_advantage_1000",
        "avg_flatten_advantage_5000",
        "avg_flatten_advantage_30000",
    ]
    print(unique_summary[[col for col in keep_cols if col in unique_summary.columns]].to_string(index=False))
    print(f"\nwrote {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    run(args.root, args.out_dir)


if __name__ == "__main__":
    main()
