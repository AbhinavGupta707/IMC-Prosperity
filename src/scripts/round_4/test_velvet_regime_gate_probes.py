"""Evaluate regime-gated VELVET recycle probes on top of `sell7`.

Ungated VELVET recycle improves the official/day-3-like path but damages
historical days 1 and 2. This harness tests whether a simple early-path regime
condition can separate those cases:

    activate post-30k VELVET recycle only if VELVET is down at least N ticks
    from its opening mid by the gate timestamp.

This is still high overfit risk because there are only three public days. The
point is to distinguish a structural early-selloff regime from unconditional
threshold widening.
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
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_regime_gate"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_REGIME_GATE_PROBES.md"


@dataclass(frozen=True)
class GateConfig:
    label: str
    gate_ts: int
    drop_ticks: float
    buy: int
    sell: int


def _configs() -> list[GateConfig | None]:
    return [
        None,
        GateConfig("gate30_drop20_buy5247_sell5264", 30_000, 20.0, 5247, 5264),
        GateConfig("gate30_drop20_buy5248_sell5264", 30_000, 20.0, 5248, 5264),
        GateConfig("gate30_drop20_buy5247_sell5262", 30_000, 20.0, 5247, 5262),
        GateConfig("gate30_drop25_buy5247_sell5262", 30_000, 25.0, 5247, 5262),
        GateConfig("gate40_drop30_buy5247_sell5262", 40_000, 30.0, 5247, 5262),
    ]


def _velvet_cfg(timestamp: int, gate_active: bool, cfg: GateConfig | None) -> dict[str, int]:
    base = {"limit": 200, "max_order": 40, "buy": 5246, "sell": 5272}
    if cfg is not None and timestamp >= cfg.gate_ts and gate_active:
        return {"limit": 200, "max_order": 40, "buy": cfg.buy, "sell": cfg.sell}
    return base


def simulate(prices: pd.DataFrame, cfg: GateConfig | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    variant = "sell7_base" if cfg is None else cfg.label
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []

    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        position = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        costs = {product: PositionCost() for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak = -float("inf")
        open_mid: float | None = None
        gate_active = False
        gate_decided = cfg is None

        for timestamp, group in day_prices.sort_values(["timestamp", "product"]).groupby(
            "timestamp", sort=True
        ):
            timestamp = int(timestamp)
            group_rows = {str(row.product): row._asdict() for row in group.itertuples(index=False)}
            velvet_row = group_rows.get(UNDERLYING)
            if velvet_row is not None and pd.notna(velvet_row["mid_price"]):
                current_mid = float(velvet_row["mid_price"])
                if open_mid is None:
                    open_mid = current_mid
                if cfg is not None and not gate_decided and timestamp >= cfg.gate_ts:
                    gate_active = open_mid - current_mid >= cfg.drop_ticks
                    gate_decided = True

            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])

            for product in SELL7_SCHEDULES:
                row = group_rows.get(product)
                if row is None:
                    continue

                if product == UNDERLYING:
                    schedule_cfg = _velvet_cfg(timestamp, gate_active, cfg)
                else:
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
                    "gate_active": bool(gate_active),
                    "total_pnl": total,
                    "drawdown": total - peak,
                    **{f"pos_{product}": position[product] for product in PRODUCTS},
                    **{f"pnl_{product}": product_pnls[product] for product in PRODUCTS},
                }
            )

    return pd.DataFrame(trade_rows), pd.DataFrame(pnl_rows)


def summarize(trades: pd.DataFrame, pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        vtrades = trades[
            (trades["variant"] == variant)
            & (trades["dataset"] == dataset)
            & (trades["day"] == day)
            & (trades["product"] == UNDERLYING)
        ]
        rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "total_pnl": float(last["total_pnl"]),
                "max_drawdown": float(group["drawdown"].min()),
                "gate_ever_active": bool(group["gate_active"].any()),
                "velvet_pnl": float(last[f"pnl_{UNDERLYING}"]),
                "velvet_end_pos": int(last[f"pos_{UNDERLYING}"]),
                "velvet_qty": int(vtrades["qty"].sum()) if not vtrades.empty else 0,
                "velvet_trade_count": int(len(vtrades)),
            }
        )
    return pd.DataFrame(rows)


def write_report(doc: Path, out_dir: Path, summary: pd.DataFrame, trades: pd.DataFrame) -> None:
    hist = summary[summary["dataset"] == "historical"].copy()
    official = summary[summary["dataset"].str.contains("official", na=False)].copy()
    agg = (
        hist.groupby("variant", sort=False)
        .agg(
            mean_total=("total_pnl", "mean"),
            min_total=("total_pnl", "min"),
            mean_drawdown=("max_drawdown", "mean"),
            active_days=("gate_ever_active", "sum"),
            mean_velvet=("velvet_pnl", "mean"),
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
            "gate_ever_active",
            "velvet_pnl",
            "velvet_end_pos",
            "velvet_qty",
        ]
    ]
    velvet_trades = trades[trades["product"] == UNDERLYING]
    trade_view = (
        velvet_trades.groupby(["variant", "dataset", "day", "side"], sort=False)
        .agg(qty=("qty", "sum"), avg_price=("price", "mean"), first_ts=("timestamp", "min"), last_ts=("timestamp", "max"))
        .reset_index()
    )
    text = f"""# VELVET Regime-Gate Probe Results

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_velvet_regime_gate_probes
```

Artifacts live under `{out_dir}`.

## Mechanism

Activate the looser post-30k/40k VELVET recycle band only after a large early
drop from the opening mid. This tries to capture the day-3/official selloff
without damaging calmer days.

## Historical Three-Day Summary

{markdown_table(agg.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Official 100k Book Proxy

{markdown_table(official_view.sort_values(["dataset", "total_pnl"], ascending=[True, False]), max_rows=120)}

## VELVET Trade Summary

{markdown_table(trade_view, max_rows=120)}

## Read

This is more structurally defensible than the ungated VELVET recycle because it
does not fire on historical days 1 and 2. It is still high overfit risk: the
gate is learned from only three public days, and the official 100k path matches
public day 3. Treat as an isolated upload probe, not a replacement baseline,
unless official/live calibration confirms the same early selloff regime.
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
    summary = summarize(trades, pnl)
    trades.to_csv(out_dir / "velvet_regime_gate_trades.csv", index=False)
    pnl.to_csv(out_dir / "velvet_regime_gate_pnl_path.csv", index=False)
    summary.to_csv(out_dir / "velvet_regime_gate_summary.csv", index=False)
    write_report(doc, out_dir, summary, trades)
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
