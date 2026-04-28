"""Summarize official HYDROGEL probe logs.

The official simulator logs are the only reliable calibration for Prosperity
fill behavior, but the current 100k price path is not an independent HYD path
sample. This script keeps those two facts separate by producing:

* per-run total and HYD PnL;
* HYD cash/terminal-mark attribution;
* HYD trade path, final inventory, liquidation-at-touch stress;
* other-product PnL so non-HYD changes are visible.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO_ROOT / "r4 Sim Results"
OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_probes"
PRODUCT = "HYDROGEL_PACK"


@dataclass(frozen=True)
class RunInput:
    name: str
    path: Path


RUNS = [
    RunInput("old_flat995", DEFAULT_ROOT / "extracted" / "flat995" / "493202.log"),
    RunInput("width28", DEFAULT_ROOT / "new_flat995" / "511373.log"),
    RunInput("flat95k", DEFAULT_ROOT / "flat95k" / "511270.log"),
    RunInput("cap40_60k", DEFAULT_ROOT / "cap4060k" / "512019.log"),
    RunInput("noshort60k_soft", DEFAULT_ROOT / "noshort60k" / "512110.log"),
    RunInput("cap80_60k", DEFAULT_ROOT / "cap8060k" / "512331.log"),
    RunInput("hardflat60k", DEFAULT_ROOT / "hardflat60k" / "512637.log"),
    RunInput("hardlong40_60k", DEFAULT_ROOT / "hardlong4060k" / "512695.log"),
    RunInput("bid10052_70k", DEFAULT_ROOT / "bid70k" / "513524.log"),
    RunInput("hardlong80_60k", DEFAULT_ROOT / "hardlong8060k" / "513589.log"),
    RunInput("slopegate15_cap40_flat60", DEFAULT_ROOT / "slopgate4060" / "514947.log"),
    RunInput("slopegate15_cap40_long40_60", DEFAULT_ROOT / "slopegatelong4060" / "515041.log"),
    RunInput("slopegate18_cap80_flat60", DEFAULT_ROOT / "slopegate8060" / "515153.log"),
    RunInput("combo_sell7_hardlong40_60k", DEFAULT_ROOT / "exphardlong4060" / "514845.log"),
    RunInput("combo_stack_hardlong40_60k", DEFAULT_ROOT / "expstack4060" / "515276.log"),
    RunInput("combo_sell7_hardlong80_60k", DEFAULT_ROOT / "expsell8060" / "515381.log"),
    RunInput("abortgate15_flat60", DEFAULT_ROOT / "abortgateflat60" / "515880.log"),
    RunInput("abortgate15_long20_60", DEFAULT_ROOT / "abortgatelong2060" / "515982.log"),
    RunInput("abortgate18_flat60", DEFAULT_ROOT / "abortgate18flat60" / "516235.log"),
    RunInput("abortgate15_long40_60", DEFAULT_ROOT / "abortgate4060" / "516429.log"),
    RunInput("abortgate18_long80_60", DEFAULT_ROOT / "abortgate18long8060" / "518320.log"),
    RunInput("abortgate18_long120_60", DEFAULT_ROOT / "abortgate120" / "518758.log"),
    RunInput("probe_513378", DEFAULT_ROOT / "probe" / "513378.log"),
]


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text())


def read_activities(payload: dict) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload["activitiesLog"]), delimiter=";"))


def own_trades(payload: dict, product: str | None = None) -> list[dict]:
    rows = []
    for row in payload.get("tradeHistory", []):
        if product is not None and row.get("symbol") != product:
            continue
        if row.get("buyer") != "SUBMISSION" and row.get("seller") != "SUBMISSION":
            continue
        qty = int(row["quantity"])
        signed_qty = qty if row.get("buyer") == "SUBMISSION" else -qty
        cash = -float(row["price"]) * qty if signed_qty > 0 else float(row["price"]) * qty
        out = dict(row)
        out["timestamp"] = int(row["timestamp"])
        out["price"] = float(row["price"])
        out["quantity"] = qty
        out["signed_qty"] = signed_qty
        out["cash"] = cash
        rows.append(out)
    return sorted(rows, key=lambda r: (r["timestamp"], r.get("symbol", "")))


def max_drawdown(values: list[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        peak = value if peak is None else max(peak, value)
        worst = min(worst, value - peak)
    return worst


def avg_price(trades: list[dict], side: str) -> float | None:
    if side == "buy":
        selected = [r for r in trades if r["signed_qty"] > 0]
    elif side == "sell":
        selected = [r for r in trades if r["signed_qty"] < 0]
    else:
        raise ValueError(side)
    qty = sum(r["quantity"] for r in selected)
    if qty <= 0:
        return None
    return sum(r["price"] * r["quantity"] for r in selected) / qty


def product_final_rows(activities: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in activities:
        out[row["product"]] = row
    return out


def product_pnl_series(activities: list[dict[str, str]], product: str) -> list[tuple[int, float]]:
    rows = [
        (int(row["timestamp"]), float(row["profit_and_loss"]))
        for row in activities
        if row["product"] == product
    ]
    return sorted(rows)


def total_final_pnl(final_rows: dict[str, dict[str, str]]) -> float:
    return sum(float(row["profit_and_loss"]) for row in final_rows.values())


def liquidation_stress(cash: float, final_pos: int, final_bid: float | None, final_ask: float | None) -> float:
    if final_pos == 0:
        return cash
    if final_pos > 0:
        if final_bid is None:
            return cash
        return cash + final_pos * final_bid
    if final_ask is None:
        return cash
    return cash + final_pos * final_ask


def summarize_run(run: RunInput) -> dict[str, object]:
    payload = load_payload(run.path)
    activities = read_activities(payload)
    final_rows = product_final_rows(activities)
    hyd_final = final_rows[PRODUCT]
    hyd_series = product_pnl_series(activities, PRODUCT)
    hyd_trades = own_trades(payload, PRODUCT)
    all_own = own_trades(payload)

    cash = sum(r["cash"] for r in hyd_trades)
    final_pos = sum(r["signed_qty"] for r in hyd_trades)
    mark_mid = float(hyd_final["mid_price"])
    bid = _float_or_none(hyd_final.get("bid_price_1"))
    ask = _float_or_none(hyd_final.get("ask_price_1"))
    terminal_mark_component = final_pos * mark_mid
    touch_liquidation_pnl = liquidation_stress(cash, final_pos, bid, ask)
    other_pnl = total_final_pnl(final_rows) - float(hyd_final["profit_and_loss"])
    last_hyd_trade_ts = max((r["timestamp"] for r in hyd_trades), default=None)
    first_hyd_trade_ts = min((r["timestamp"] for r in hyd_trades), default=None)
    buy_qty = sum(r["quantity"] for r in hyd_trades if r["signed_qty"] > 0)
    sell_qty = sum(r["quantity"] for r in hyd_trades if r["signed_qty"] < 0)

    product_pnls = {
        product: float(row["profit_and_loss"])
        for product, row in sorted(final_rows.items())
    }
    non_hyd_products_touched = sorted(
        {r["symbol"] for r in all_own if r["symbol"] != PRODUCT}
    )

    return {
        "run": run.name,
        "path": str(run.path),
        "total_pnl": round(total_final_pnl(final_rows), 2),
        "hyd_pnl": round(float(hyd_final["profit_and_loss"]), 2),
        "other_pnl": round(other_pnl, 2),
        "hyd_cash": round(cash, 2),
        "hyd_terminal_mark_component": round(terminal_mark_component, 2),
        "hyd_touch_liquidation_pnl": round(touch_liquidation_pnl, 2),
        "hyd_touch_liquidation_delta": round(touch_liquidation_pnl - float(hyd_final["profit_and_loss"]), 2),
        "hyd_final_pos": final_pos,
        "hyd_mark_mid": mark_mid,
        "hyd_final_bid": "" if bid is None else bid,
        "hyd_final_ask": "" if ask is None else ask,
        "hyd_buy_qty": buy_qty,
        "hyd_sell_qty": sell_qty,
        "hyd_avg_buy": _round_or_blank(avg_price(hyd_trades, "buy")),
        "hyd_avg_sell": _round_or_blank(avg_price(hyd_trades, "sell")),
        "hyd_first_trade_ts": "" if first_hyd_trade_ts is None else first_hyd_trade_ts,
        "hyd_last_trade_ts": "" if last_hyd_trade_ts is None else last_hyd_trade_ts,
        "hyd_trade_rows": len(hyd_trades),
        "hyd_min_pnl": round(min(v for _, v in hyd_series), 2),
        "hyd_peak_pnl": round(max(v for _, v in hyd_series), 2),
        "hyd_max_drawdown": round(max_drawdown([v for _, v in hyd_series]), 2),
        "non_hyd_products_touched": "|".join(non_hyd_products_touched),
        "product_pnls_json": json.dumps(product_pnls, sort_keys=True, separators=(",", ":")),
    }


def _float_or_none(value: object) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_blank(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [summarize_run(item) for item in RUNS if item.path.exists()]
    out_path = out_dir / "official_hydrogel_probe_batch_summary.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
