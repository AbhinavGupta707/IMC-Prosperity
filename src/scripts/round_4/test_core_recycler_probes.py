"""Evaluate bounded core VEV_5000/5100 recycling probes.

The current R4 schedule often pins voucher inventory early. This harness tests
one conservative mechanism before creating upload candidates:

    When VEV_5000/5100 are near a position limit, take a small profit back
    toward a reserve floor to free capacity for future schedule signals.

The goal is mechanism evidence, not a broad threshold sweep. A deterministic
timestamp-window negative control is included to check whether benefits come
from generic churn rather than capacity-state recycling.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    DEFAULT_OFFICIAL_DIR,
    FLATTEN_START,
    PRODUCTS,
    SELL7_SCHEDULES,
    UNDERLYING,
    load_historical,
    load_official_books,
    _schedule_for,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "core_recycler"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "CORE_RECYCLER_PROBES.md"

CORE_PRODUCTS = ("VEV_5000", "VEV_5100")


@dataclass(frozen=True)
class RecyclerConfig:
    label: str
    active_abs: int
    floor_abs: int
    take_profit: int
    max_order: int
    products: tuple[str, ...] = CORE_PRODUCTS
    negative_window: bool = False


@dataclass
class PositionCost:
    position: int = 0
    avg_price: float | None = None

    def apply(self, side: str, price: float, qty: int) -> None:
        signed = qty if side == "buy" else -qty
        if qty <= 0:
            return
        if self.position == 0:
            self.position = signed
            self.avg_price = float(price)
            return
        if self.position * signed > 0:
            total_qty = abs(self.position) + qty
            prev_avg = self.avg_price if self.avg_price is not None else float(price)
            self.avg_price = (prev_avg * abs(self.position) + float(price) * qty) / total_qty
            self.position += signed
            return
        remaining = self.position + signed
        if self.position * remaining > 0:
            self.position = remaining
            return
        if remaining == 0:
            self.position = 0
            self.avg_price = None
            return
        self.position = remaining
        self.avg_price = float(price)


def _record_trade(
    rows: list[dict],
    *,
    variant: str,
    dataset: str,
    day: int,
    timestamp: int,
    product: str,
    side: str,
    reason: str,
    price: float,
    qty: int,
    position: dict[str, int],
    cash: dict[str, float],
    costs: dict[str, PositionCost],
) -> None:
    pos_before = position[product]
    if side == "buy":
        signed = qty
        cash[product] -= price * qty
        position[product] += qty
    else:
        signed = -qty
        cash[product] += price * qty
        position[product] -= qty
    costs[product].apply(side, price, qty)
    rows.append(
        {
            "variant": variant,
            "dataset": dataset,
            "day": int(day),
            "timestamp": int(timestamp),
            "product": product,
            "side": side,
            "reason": reason,
            "price": float(price),
            "qty": int(qty),
            "signed_qty": int(signed),
            "pos_before": int(pos_before),
            "pos_after": int(position[product]),
            "avg_price_after": costs[product].avg_price,
        }
    )


def _negative_window_active(timestamp: int) -> bool:
    # Deterministic non-market condition with roughly sparse activations.
    return timestamp % 30_000 < 5_000


def _volume(value: object) -> int:
    if pd.isna(value):
        return 0
    return int(abs(float(value)))


def _maybe_recycle(
    *,
    cfg: RecyclerConfig | None,
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
    if cfg is None:
        return False
    product = str(rows["product"])
    if product not in cfg.products:
        return False
    if cfg.negative_window and not _negative_window_active(timestamp):
        return False
    cost = costs[product]
    avg = cost.avg_price
    pos = position[product]
    if avg is None or pos == 0:
        return False

    best_bid = rows["bid_price_1"]
    best_ask = rows["ask_price_1"]
    bid_volume = _volume(rows["bid_volume_1"])
    ask_volume = _volume(rows["ask_volume_1"])

    if pos >= cfg.active_abs and pd.notna(best_bid):
        qty = min(cfg.max_order, bid_volume, pos - cfg.floor_abs)
        if qty > 0 and float(best_bid) >= avg + cfg.take_profit:
            _record_trade(
                trade_rows,
                variant=variant,
                dataset=dataset,
                day=day,
                timestamp=timestamp,
                product=product,
                side="sell",
                reason="recycle_sell_long_tp",
                price=float(best_bid),
                qty=qty,
                position=position,
                cash=cash,
                costs=costs,
            )
            return True

    if pos <= -cfg.active_abs and pd.notna(best_ask):
        qty = min(cfg.max_order, ask_volume, -pos - cfg.floor_abs)
        if qty > 0 and float(best_ask) <= avg - cfg.take_profit:
            _record_trade(
                trade_rows,
                variant=variant,
                dataset=dataset,
                day=day,
                timestamp=timestamp,
                product=product,
                side="buy",
                reason="recycle_buy_short_tp",
                price=float(best_ask),
                qty=qty,
                position=position,
                cash=cash,
                costs=costs,
            )
            return True
    return False


def simulate(prices: pd.DataFrame, cfg: RecyclerConfig | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    variant = "sell7_base" if cfg is None else cfg.label
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []

    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        position = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        costs = {product: PositionCost() for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak = -float("inf")

        for timestamp, group in day_prices.sort_values(["timestamp", "product"]).groupby("timestamp", sort=True):
            timestamp = int(timestamp)
            group_rows = {str(row.product): row._asdict() for row in group.itertuples(index=False)}
            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])

            for product, schedule in SELL7_SCHEDULES.items():
                row = group_rows.get(product)
                if row is None:
                    continue
                did_recycle = _maybe_recycle(
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

                if pd.notna(ask) and float(ask) <= schedule_cfg["buy"] and position[product] < schedule_cfg["limit"]:
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
                if pd.notna(bid) and float(bid) >= schedule_cfg["sell"] and position[product] > -schedule_cfg["limit"]:
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


def _configs() -> list[RecyclerConfig | None]:
    return [
        None,
        RecyclerConfig("core_tp4_abs280_floor240_mo20", 280, 240, 4, 20),
        RecyclerConfig("core_tp6_abs280_floor240_mo20", 280, 240, 6, 20),
        RecyclerConfig("core_tp8_abs280_floor240_mo20", 280, 240, 8, 20),
        RecyclerConfig("core_tp4_abs300_floor260_mo20", 300, 260, 4, 20),
        RecyclerConfig("core_tp6_abs300_floor260_mo20", 300, 260, 6, 20),
        RecyclerConfig("core_tp4_abs280_floor240_mo40", 280, 240, 4, 40),
        RecyclerConfig("negctrl_window_tp4_abs280_floor240_mo20", 280, 240, 4, 20, negative_window=True),
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
        r = t[t["reason"].str.startswith("recycle", na=False)]
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
                "end_pos_VEV_5000": int(last["pos_VEV_5000"]),
                "end_pos_VEV_5100": int(last["pos_VEV_5100"]),
            }
        )
        for product in (UNDERLYING, *CORE_PRODUCTS, "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"):
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


def markdown_table(df: pd.DataFrame, *, max_rows: int = 40) -> str:
    if df.empty:
        return "_empty_"
    display = df.head(max_rows).copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda v: f"{v:.2f}")
    headers = [str(c) for c in display.columns]
    rows = [[str(v) for v in row] for row in display.to_numpy()]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(values: list[str]) -> str:
        return "| " + " | ".join(values[i].ljust(widths[i]) for i in range(len(widths))) + " |"

    return "\n".join([fmt(headers), "| " + " | ".join("-" * w for w in widths) + " |", *(fmt(r) for r in rows)])


def write_report(doc: Path, out_dir: Path, summary: pd.DataFrame, product: pd.DataFrame) -> None:
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
            "end_pos_VEV_5000",
            "end_pos_VEV_5100",
        ]
    ]
    text = f"""# Core Recycler Probe Results

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_core_recycler_probes
```

Artifacts live under `{out_dir}`.

## Mechanism

The probe starts from the `sell7` VELVET schedule. For `VEV_5000` and
`VEV_5100`, when the position is near a limit, it takes a small profit back
toward a reserve floor. This is meant to free capacity without changing the
core static entry thresholds.

The negative control applies the same profit rule only inside deterministic
timestamp windows. It is not a final candidate; it tests whether any improvement
is just generic churn.

## Historical Three-Day Summary

{markdown_table(agg.sort_values("delta_vs_base", ascending=False))}

## Official 100k Book Proxy

{markdown_table(official_view.sort_values(["dataset", "total_pnl"], ascending=[True, False]), max_rows=80)}

## Read

Promote only if the recycler beats `sell7_base` on historical mean, does not
concentrate gains in one day, and beats the negative control. A recycler that
only improves the official 100k proxy is not robust enough; the official window
is exactly where the current book saturates early and can reward path-specific
extra churn.
"""
    doc.write_text(text)


def run(data_dir: Path, official_dir: Path, out_dir: Path, doc: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    historical = load_historical(data_dir)
    official_books, _ = load_official_books(official_dir)
    official = [
        book for name, book in official_books.items() if name in {"official_sellonly8", "official_disabled"}
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
    trades.to_csv(out_dir / "recycler_trades.csv", index=False)
    pnl.to_csv(out_dir / "recycler_pnl_path.csv", index=False)
    summary.to_csv(out_dir / "recycler_summary.csv", index=False)
    product.to_csv(out_dir / "recycler_product_pnl.csv", index=False)
    write_report(doc, out_dir, summary, product)
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
