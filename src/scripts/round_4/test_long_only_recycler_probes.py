"""Evaluate late long-only core voucher recycling probes.

The first core recycler test was deliberately symmetric: it took profit both
from long and short inventory. Official `sell7` context shows that symmetry is
the wrong mechanism. The early short voucher book is part of the edge; buying
those shorts back early can destroy terminal/regime value.

This harness tests a narrower mechanism:

    After the schedule has reloaded long core vouchers, sell a bounded amount
    only from long inventory on a rebound, then let the original cheap-entry
    schedule refill that capacity on a later dip.

This is still a local/offline proxy. Promote only if it improves historical
robustness and does not just exploit one official 100k path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    DEFAULT_OFFICIAL_DIR,
    FLATTEN_START,
    PRODUCTS,
    SELL7_SCHEDULES,
    UNDERLYING,
    _schedule_for,
    load_historical,
    load_official_books,
)
from src.scripts.round_4.test_core_recycler_probes import (
    PositionCost,
    _record_trade,
    _volume,
    markdown_table,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "long_only_recycler"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "LONG_ONLY_RECYCLER_PROBES.md"

CORE_5100 = ("VEV_5000", "VEV_5100")
CORE_5200 = ("VEV_5000", "VEV_5100", "VEV_5200")


@dataclass(frozen=True)
class LongOnlyConfig:
    label: str
    active_abs: int
    floor_abs: int
    take_profit: int
    max_order: int
    start_ts: int
    products: tuple[str, ...] = CORE_5200
    negative_window: bool = False


def _negative_window_active(timestamp: int) -> bool:
    # Sparse deterministic non-structural control. It may overlap some good
    # windows, but it does not condition on inventory-quality or rebound state.
    return timestamp % 35_000 < 5_000


def _maybe_long_recycle(
    *,
    cfg: LongOnlyConfig | None,
    rows: dict[str, object],
    variant: str,
    dataset: str,
    day: int,
    timestamp: int,
    position: dict[str, int],
    cash: dict[str, float],
    costs: dict[str, PositionCost],
    trade_rows: list[dict],
) -> bool:
    if cfg is None or timestamp < cfg.start_ts:
        return False
    product = str(rows["product"])
    if product not in cfg.products:
        return False
    if cfg.negative_window and not _negative_window_active(timestamp):
        return False

    cost = costs[product]
    avg = cost.avg_price
    pos = position[product]
    if avg is None or pos < cfg.active_abs:
        return False

    best_bid = rows["bid_price_1"]
    if pd.isna(best_bid):
        return False
    bid_volume = _volume(rows["bid_volume_1"])
    qty = min(cfg.max_order, bid_volume, pos - cfg.floor_abs)
    if qty <= 0 or float(best_bid) < avg + cfg.take_profit:
        return False

    _record_trade(
        trade_rows,
        variant=variant,
        dataset=dataset,
        day=day,
        timestamp=timestamp,
        product=product,
        side="sell",
        reason="long_recycle_sell",
        price=float(best_bid),
        qty=qty,
        position=position,
        cash=cash,
        costs=costs,
    )
    return True


def simulate(prices: pd.DataFrame, cfg: LongOnlyConfig | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    variant = "sell7_base" if cfg is None else cfg.label
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []

    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        position = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        costs = {product: PositionCost() for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak = -float("inf")

        for timestamp, group in day_prices.sort_values(["timestamp", "product"]).groupby(
            "timestamp", sort=True
        ):
            timestamp = int(timestamp)
            group_rows = {str(row.product): row._asdict() for row in group.itertuples(index=False)}
            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])

            for product, schedule in SELL7_SCHEDULES.items():
                row = group_rows.get(product)
                if row is None:
                    continue

                did_recycle = _maybe_long_recycle(
                    cfg=cfg,
                    rows=row,
                    variant=variant,
                    dataset=str(dataset),
                    day=int(day),
                    timestamp=timestamp,
                    position=position,
                    cash=cash,
                    costs=costs,
                    trade_rows=trade_rows,
                )
                if did_recycle:
                    continue

                schedule_cfg = _schedule_for(product, timestamp, SELL7_SCHEDULES)
                if schedule_cfg is None:
                    continue

                bid = row["bid_price_1"]
                ask = row["ask_price_1"]
                bid_volume = _volume(row["bid_volume_1"])
                ask_volume = _volume(row["ask_volume_1"])

                if timestamp >= FLATTEN_START:
                    if position[product] > 0 and pd.notna(bid):
                        qty = min(schedule_cfg["max_order"], bid_volume, position[product])
                        if qty > 0:
                            _record_trade(
                                trade_rows,
                                variant=variant,
                                dataset=str(dataset),
                                day=int(day),
                                timestamp=timestamp,
                                product=product,
                                side="sell",
                                reason="flatten",
                                price=float(bid),
                                qty=qty,
                                position=position,
                                cash=cash,
                                costs=costs,
                            )
                    elif position[product] < 0 and pd.notna(ask):
                        qty = min(schedule_cfg["max_order"], ask_volume, -position[product])
                        if qty > 0:
                            _record_trade(
                                trade_rows,
                                variant=variant,
                                dataset=str(dataset),
                                day=int(day),
                                timestamp=timestamp,
                                product=product,
                                side="buy",
                                reason="flatten",
                                price=float(ask),
                                qty=qty,
                                position=position,
                                cash=cash,
                                costs=costs,
                            )
                    continue

                if (
                    pd.notna(ask)
                    and float(ask) <= schedule_cfg["buy"]
                    and position[product] < schedule_cfg["limit"]
                ):
                    qty = min(schedule_cfg["max_order"], ask_volume, schedule_cfg["limit"] - position[product])
                    if qty > 0:
                        _record_trade(
                            trade_rows,
                            variant=variant,
                            dataset=str(dataset),
                            day=int(day),
                            timestamp=timestamp,
                            product=product,
                            side="buy",
                            reason="schedule",
                            price=float(ask),
                            qty=qty,
                            position=position,
                            cash=cash,
                            costs=costs,
                        )
                if (
                    pd.notna(bid)
                    and float(bid) >= schedule_cfg["sell"]
                    and position[product] > -schedule_cfg["limit"]
                ):
                    qty = min(schedule_cfg["max_order"], bid_volume, schedule_cfg["limit"] + position[product])
                    if qty > 0:
                        _record_trade(
                            trade_rows,
                            variant=variant,
                            dataset=str(dataset),
                            day=int(day),
                            timestamp=timestamp,
                            product=product,
                            side="sell",
                            reason="schedule",
                            price=float(bid),
                            qty=qty,
                            position=position,
                            cash=cash,
                            costs=costs,
                        )

            product_pnls = {
                product: cash[product] + position[product] * last_mid.get(product, 0.0)
                for product in PRODUCTS
            }
            total = float(sum(product_pnls.values()))
            peak = max(peak, total)
            pnl_rows.append(
                {
                    "variant": variant,
                    "dataset": dataset,
                    "day": int(day),
                    "timestamp": timestamp,
                    "total_pnl": total,
                    "drawdown": total - peak,
                    **{f"pos_{product}": position[product] for product in PRODUCTS},
                    **{f"pnl_{product}": product_pnls[product] for product in PRODUCTS},
                }
            )

    return pd.DataFrame(trade_rows), pd.DataFrame(pnl_rows)


def _configs() -> list[LongOnlyConfig | None]:
    return [
        None,
        LongOnlyConfig("longonly_50k_5000_5100_tp6_abs280_floor240_mo20", 280, 240, 6, 20, 50_000, CORE_5100),
        LongOnlyConfig("longonly_50k_5000_5100_tp8_abs280_floor240_mo20", 280, 240, 8, 20, 50_000, CORE_5100),
        LongOnlyConfig("longonly_50k_core3_tp6_abs280_floor240_mo20", 280, 240, 6, 20, 50_000, CORE_5200),
        LongOnlyConfig("longonly_50k_core3_tp8_abs280_floor240_mo20", 280, 240, 8, 20, 50_000, CORE_5200),
        LongOnlyConfig("longonly_60k_core3_tp6_abs280_floor240_mo20", 280, 240, 6, 20, 60_000, CORE_5200),
        LongOnlyConfig("longonly_50k_core3_tp6_abs300_floor260_mo20", 300, 260, 6, 20, 50_000, CORE_5200),
        LongOnlyConfig(
            "negctrl_longonly_core3_tp6_abs280_floor240_mo20",
            280,
            240,
            6,
            20,
            50_000,
            CORE_5200,
            negative_window=True,
        ),
    ]


def summarize(trades: pd.DataFrame, pnl: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    product_rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        t = trades[
            (trades["variant"] == variant)
            & (trades["dataset"] == dataset)
            & (trades["day"] == day)
        ]
        r = t[t["reason"].eq("long_recycle_sell")]
        summary_rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "total_pnl": float(last["total_pnl"]),
                "max_drawdown": float(group["drawdown"].min()),
                "trades": int(len(t)),
                "abs_qty": int(t["qty"].sum()) if not t.empty else 0,
                "recycle_trades": int(len(r)),
                "recycle_qty": int(r["qty"].sum()) if not r.empty else 0,
                "pnl_VEV_5000": float(last["pnl_VEV_5000"]),
                "pnl_VEV_5100": float(last["pnl_VEV_5100"]),
                "pnl_VEV_5200": float(last["pnl_VEV_5200"]),
                "end_pos_VEV_5000": int(last["pos_VEV_5000"]),
                "end_pos_VEV_5100": int(last["pos_VEV_5100"]),
                "end_pos_VEV_5200": int(last["pos_VEV_5200"]),
            }
        )
        for product in (UNDERLYING, "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"):
            product_rows.append(
                {
                    "variant": variant,
                    "dataset": dataset,
                    "day": int(day),
                    "product": product,
                    "pnl": float(last[f"pnl_{product}"]),
                    "end_position": int(last[f"pos_{product}"]),
                }
            )
    return pd.DataFrame(summary_rows), pd.DataFrame(product_rows)


def write_report(doc: Path, out_dir: Path, summary: pd.DataFrame) -> None:
    hist = summary[summary["dataset"] == "historical"].copy()
    official = summary[summary["dataset"].str.contains("official", na=False)].copy()
    agg = (
        hist.groupby("variant", sort=False)
        .agg(
            mean_total=("total_pnl", "mean"),
            min_total=("total_pnl", "min"),
            mean_drawdown=("max_drawdown", "mean"),
            recycle_qty=("recycle_qty", "sum"),
            mean_5000=("pnl_VEV_5000", "mean"),
            mean_5100=("pnl_VEV_5100", "mean"),
            mean_5200=("pnl_VEV_5200", "mean"),
        )
        .reset_index()
    )
    base_total = float(agg.loc[agg["variant"] == "sell7_base", "mean_total"].iloc[0])
    agg["delta_vs_base"] = agg["mean_total"] - base_total
    official_view = official[
        [
            "variant",
            "dataset",
            "total_pnl",
            "max_drawdown",
            "recycle_qty",
            "pnl_VEV_5000",
            "pnl_VEV_5100",
            "pnl_VEV_5200",
            "end_pos_VEV_5000",
            "end_pos_VEV_5100",
            "end_pos_VEV_5200",
        ]
    ]
    text = f"""# Long-Only Recycler Probe Results

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_long_only_recycler_probes
```

Artifacts live under `{out_dir}`.

## Mechanism

This starts from `sell7_base` and only recycles long `VEV_5000/5100/5200`
inventory after the core cheap reload window. It never buys back early short
inventory for a profit. The intended mechanism is rebound-sale plus later
cheap refill, not generic churn.

## Historical Three-Day Summary

{markdown_table(agg.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Official 100k Book Proxy

{markdown_table(official_view.sort_values(["dataset", "total_pnl"], ascending=[True, False]), max_rows=120)}

## Read

Promote only if this beats `sell7_base` on historical mean, avoids a single-day
dependency, and beats the negative control. A result that improves only the
validated official 100k path should be treated as a calibration idea, not a
final upload candidate.
"""
    doc.write_text(text)


def run(data_dir: Path, official_dir: Path, out_dir: Path, doc: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    historical = load_historical(data_dir)
    official_books, _ = load_official_books(official_dir)
    official = [
        book
        for name, book in official_books.items()
        if name in {"official_sellonly8", "official_disabled", "official_sell7_validated"}
    ]
    prices = pd.concat([historical, *official], ignore_index=True)
    all_trades = []
    all_pnl = []
    for cfg in _configs():
        label = "sell7_base" if cfg is None else cfg.label
        print(f"running {label}", flush=True)
        trades, pnl = simulate(prices, cfg)
        all_trades.append(trades)
        all_pnl.append(pnl)
    trades = pd.concat(all_trades, ignore_index=True)
    pnl = pd.concat(all_pnl, ignore_index=True)
    summary, product = summarize(trades, pnl)
    trades.to_csv(out_dir / "long_only_recycler_trades.csv", index=False)
    pnl.to_csv(out_dir / "long_only_recycler_pnl_path.csv", index=False)
    summary.to_csv(out_dir / "long_only_recycler_summary.csv", index=False)
    product.to_csv(out_dir / "long_only_recycler_product_pnl.csv", index=False)
    write_report(doc, out_dir, summary)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(summary.sort_values(["dataset", "day", "total_pnl"], ascending=[True, True, False]).to_string(index=False))


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
