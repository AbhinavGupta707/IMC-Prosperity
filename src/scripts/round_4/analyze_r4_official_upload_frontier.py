"""Summarize all Round 4 official simulator uploads.

This is an evidence-control script: when many official uploads exist, separate
new VELVET alpha from unrelated HYDROGEL/stack effects and duplicate archives.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from src.scripts.round_4.test_core_recycler_probes import markdown_table


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SIM_DIR = REPO_ROOT / "r4 Sim Results"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "official_upload_frontier"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "R4_OFFICIAL_UPLOAD_FRONTIER.md"

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


def _candidate_name(path: Path, sim_dir: Path) -> str:
    rel = path.relative_to(sim_dir)
    if path.suffix == ".zip":
        return path.stem
    if len(rel.parts) >= 2:
        return rel.parts[-2]
    return path.stem


def _read_json_text(raw: bytes | str, *, require_result: bool = True) -> dict | None:
    try:
        text = raw.decode() if isinstance(raw, bytes) else raw
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if require_result and ("activitiesLog" not in payload or "profit" not in payload):
        return None
    return payload


def _iter_payloads(sim_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(sim_dir.rglob("*")):
        if path.name.startswith(".") or path.is_dir():
            continue
        payload = None
        log_payload = None
        source_kind = path.suffix.lstrip(".")
        if path.suffix == ".zip":
            try:
                with zipfile.ZipFile(path) as zf:
                    json_name = next((name for name in zf.namelist() if name.endswith(".json")), None)
                    if json_name is None:
                        continue
                    payload = _read_json_text(zf.read(json_name), require_result=True)
                    log_name = next((name for name in zf.namelist() if name.endswith(".log")), None)
                    if log_name is not None:
                        log_payload = _read_json_text(zf.read(log_name), require_result=False)
            except zipfile.BadZipFile:
                continue
        elif path.suffix == ".json":
            payload = _read_json_text(path.read_text(), require_result=True)
            log_path = path.with_suffix(".log")
            if log_path.exists():
                log_payload = _read_json_text(log_path.read_text(), require_result=False)
        else:
            continue
        if payload is None:
            continue
        rows.append(
            {
                "candidate": _candidate_name(path, sim_dir),
                "source": str(path.relative_to(sim_dir)),
                "source_kind": source_kind,
                "payload": payload,
                "log_payload": log_payload,
            }
        )
    return rows


def _activities(payload: dict) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")


def _product_final(payload: dict) -> dict[str, float]:
    activities = _activities(payload)
    final = activities.sort_values("timestamp").groupby("product", as_index=False).tail(1)
    return {str(row.product): float(row.profit_and_loss) for row in final.itertuples(index=False)}


def _positions(payload: dict, log_payload: dict | None) -> dict[str, int]:
    if payload.get("positions"):
        return {str(row["symbol"]): int(row["quantity"]) for row in payload["positions"]}
    if not log_payload:
        return {}
    trades = pd.DataFrame(log_payload.get("tradeHistory", []))
    if trades.empty:
        return {}
    own = trades[(trades["buyer"].eq("SUBMISSION")) | (trades["seller"].eq("SUBMISSION"))].copy()
    if own.empty:
        return {}
    own["signed_qty"] = own.apply(
        lambda row: int(row["quantity"]) if row["buyer"] == "SUBMISSION" else -int(row["quantity"]),
        axis=1,
    )
    return own.groupby("symbol")["signed_qty"].sum().astype(int).to_dict()


def _own_trade_summary(log_payload: dict | None) -> dict[str, int | None]:
    if not log_payload:
        return {
            "submission_rows": None,
            "velvet_rows": None,
            "velvet_abs_qty": None,
            "velvet_first_ts": None,
            "velvet_last_ts": None,
        }
    trades = pd.DataFrame(log_payload.get("tradeHistory", []))
    if trades.empty:
        return {
            "submission_rows": 0,
            "velvet_rows": 0,
            "velvet_abs_qty": 0,
            "velvet_first_ts": None,
            "velvet_last_ts": None,
        }
    own = trades[(trades["buyer"].eq("SUBMISSION")) | (trades["seller"].eq("SUBMISSION"))].copy()
    velvet = own[own["symbol"].eq("VELVETFRUIT_EXTRACT")].copy()
    return {
        "submission_rows": int(len(own)),
        "velvet_rows": int(len(velvet)),
        "velvet_abs_qty": int(velvet["quantity"].sum()) if not velvet.empty else 0,
        "velvet_first_ts": int(velvet["timestamp"].min()) if not velvet.empty else None,
        "velvet_last_ts": int(velvet["timestamp"].max()) if not velvet.empty else None,
    }


def analyze(sim_dir: Path, out_dir: Path, doc: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    payload_rows = _iter_payloads(sim_dir)
    if not payload_rows:
        raise SystemExit(f"No official simulator payloads under {sim_dir}")

    product_maps = {row["source"]: _product_final(row["payload"]) for row in payload_rows}
    position_maps = {row["source"]: _positions(row["payload"], row["log_payload"]) for row in payload_rows}

    def source_row(source: str) -> dict:
        matches = [row for row in payload_rows if row["source"] == source]
        if not matches:
            raise SystemExit(f"Missing required baseline source: {source}")
        return matches[0]

    sell7 = source_row("validated/511763.json")
    probe = source_row("probe/513378.json")
    sell7_profit = float(sell7["payload"]["profit"])
    probe_profit = float(probe["payload"]["profit"])
    sell7_products = product_maps[sell7["source"]]
    sell7_complex = sum(sell7_products.get(product, 0.0) for product in VELVET_PRODUCTS)

    summary_rows = []
    product_rows = []
    for row in payload_rows:
        products = product_maps[row["source"]]
        positions = position_maps[row["source"]]
        complex_pnl = sum(products.get(product, 0.0) for product in VELVET_PRODUCTS)
        own = _own_trade_summary(row["log_payload"])
        summary_rows.append(
            {
                "candidate": row["candidate"],
                "source": row["source"],
                "kind": row["source_kind"],
                "profit": float(row["payload"]["profit"]),
                "delta_vs_sell7": float(row["payload"]["profit"]) - sell7_profit,
                "delta_vs_probe_stack": float(row["payload"]["profit"]) - probe_profit,
                "velvet_complex": complex_pnl,
                "velvet_complex_delta": complex_pnl - sell7_complex,
                "hydrogel": products.get("HYDROGEL_PACK", 0.0),
                "velvet_pnl": products.get("VELVETFRUIT_EXTRACT", 0.0),
                "velvet_pos": positions.get("VELVETFRUIT_EXTRACT"),
                **own,
            }
        )
        for product, pnl in products.items():
            product_rows.append(
                {
                    "candidate": row["candidate"],
                    "source": row["source"],
                    "product": product,
                    "pnl": pnl,
                    "base_pnl": sell7_products.get(product, 0.0),
                    "delta_vs_sell7": pnl - sell7_products.get(product, 0.0),
                    "position": positions.get(product),
                }
            )

    summary = pd.DataFrame(summary_rows).sort_values("profit", ascending=False)
    product_delta = pd.DataFrame(product_rows)
    summary.to_csv(out_dir / "all_upload_summary.csv", index=False)
    product_delta.to_csv(out_dir / "all_upload_product_delta.csv", index=False)

    top_unique = (
        summary.sort_values("profit", ascending=False)
        .drop_duplicates(subset=["candidate"], keep="first")
        .head(30)
    )
    top_velvet = (
        summary.sort_values(["velvet_complex_delta", "profit"], ascending=False)
        .drop_duplicates(subset=["candidate"], keep="first")
        .head(30)
    )
    nonzero_velvet_products = product_delta[
        product_delta["product"].isin(VELVET_PRODUCTS) & product_delta["delta_vs_sell7"].abs().gt(1e-6)
    ].sort_values(["source", "delta_vs_sell7"], ascending=[True, False])

    text = f"""# R4 Official Upload Frontier

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_r4_official_upload_frontier
```

Artifacts live under `{out_dir}`.

## Purpose

Separate genuine VELVET-complex improvement from full-stack PnL that comes from
other sleeves, duplicate archives, or official-prefix luck.

## Top Unique Uploads By Profit

{markdown_table(top_unique[["candidate", "source", "profit", "delta_vs_sell7", "delta_vs_probe_stack", "velvet_complex_delta", "hydrogel", "velvet_pnl", "velvet_pos", "velvet_abs_qty"]], max_rows=30)}

## Top VELVET-Complex Deltas

{markdown_table(top_velvet[["candidate", "source", "profit", "delta_vs_sell7", "velvet_complex_delta", "hydrogel", "velvet_pnl", "velvet_pos", "velvet_abs_qty"]], max_rows=30)}

## Nonzero VELVET Product Deltas

{markdown_table(nonzero_velvet_products[["candidate", "source", "product", "pnl", "base_pnl", "delta_vs_sell7", "position"]], max_rows=120)}

## Read

Use this as official calibration only. A candidate that improves the official
100k but does not improve public full-day/window robustness should still be
treated as path-sensitive for the 1M final.
"""
    doc.write_text(text)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(top_unique[["candidate", "source", "profit", "delta_vs_sell7", "velvet_complex_delta", "hydrogel"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-dir", type=Path, default=DEFAULT_SIM_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    analyze(args.sim_dir, args.out_dir, args.doc)


if __name__ == "__main__":
    main()
