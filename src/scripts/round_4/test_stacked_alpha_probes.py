"""Evaluate stacked R4 VELVET/voucher alpha probes.

The prior isolated probes found two official/day-3-like opportunities:

* a regime-gated VELVET recycle band after a large early selloff;
* a late long-only core-voucher recycler that sells only profitable long
  inventory and lets the base schedule refill on a later dip.

This harness checks whether those two mechanisms stack and, more importantly,
whether the voucher recycler should be gated by the same early VELVET regime
condition to avoid damaging calmer historical days.
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
from src.scripts.round_4.test_long_only_recycler_probes import (
    CORE_5100,
    CORE_5200,
    LongOnlyConfig,
    _maybe_long_recycle,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "stacked_alpha_probes"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "STACKED_ALPHA_PROBES.md"


@dataclass(frozen=True)
class RegimeGate:
    gate_ts: int
    drop_ticks: float


@dataclass(frozen=True)
class VelvetBand:
    buy: int
    sell: int


@dataclass(frozen=True)
class AlphaConfig:
    label: str
    gate: RegimeGate | None = None
    velvet_band: VelvetBand | None = None
    long_recycle: LongOnlyConfig | None = None
    long_requires_gate: bool = False


GATE30_DROP20 = RegimeGate(30_000, 20.0)

LONG_CORE3_TP8 = LongOnlyConfig(
    "core3_tp8_abs280_floor240_mo20",
    active_abs=280,
    floor_abs=240,
    take_profit=8,
    max_order=20,
    start_ts=50_000,
    products=CORE_5200,
)

LONG_CORE3_TP6 = LongOnlyConfig(
    "core3_tp6_abs280_floor240_mo20",
    active_abs=280,
    floor_abs=240,
    take_profit=6,
    max_order=20,
    start_ts=50_000,
    products=CORE_5200,
)

LONG_5000_5100_TP8 = LongOnlyConfig(
    "5000_5100_tp8_abs280_floor240_mo20",
    active_abs=280,
    floor_abs=240,
    take_profit=8,
    max_order=20,
    start_ts=50_000,
    products=CORE_5100,
)


def _configs() -> list[AlphaConfig]:
    return [
        AlphaConfig("sell7_base"),
        AlphaConfig(
            "core_gated_5000_5100_tp8",
            gate=GATE30_DROP20,
            long_recycle=LONG_5000_5100_TP8,
            long_requires_gate=True,
        ),
        AlphaConfig(
            "core_gated_core3_tp8",
            gate=GATE30_DROP20,
            long_recycle=LONG_CORE3_TP8,
            long_requires_gate=True,
        ),
        AlphaConfig(
            "core_gated_core3_tp6",
            gate=GATE30_DROP20,
            long_recycle=LONG_CORE3_TP6,
            long_requires_gate=True,
        ),
        AlphaConfig(
            "velvet_gate_buy5248_sell5264",
            gate=GATE30_DROP20,
            velvet_band=VelvetBand(5248, 5264),
        ),
        AlphaConfig(
            "velvet_gate_buy5247_sell5262",
            gate=GATE30_DROP20,
            velvet_band=VelvetBand(5247, 5262),
        ),
        AlphaConfig(
            "stack_officialmax_v5248_5264_core3_tp8",
            gate=GATE30_DROP20,
            velvet_band=VelvetBand(5248, 5264),
            long_recycle=LONG_CORE3_TP8,
            long_requires_gate=True,
        ),
        AlphaConfig(
            "stack_officialmax_v5248_5264_5100_tp8",
            gate=GATE30_DROP20,
            velvet_band=VelvetBand(5248, 5264),
            long_recycle=LONG_5000_5100_TP8,
            long_requires_gate=True,
        ),
        AlphaConfig(
            "stack_histmax_v5247_5262_core3_tp6",
            gate=GATE30_DROP20,
            velvet_band=VelvetBand(5247, 5262),
            long_recycle=LONG_CORE3_TP6,
            long_requires_gate=True,
        ),
    ]


def _velvet_cfg(timestamp: int, gate_active: bool, cfg: AlphaConfig) -> dict[str, int]:
    base = {"limit": 200, "max_order": 40, "buy": 5246, "sell": 5272}
    if (
        cfg.gate is not None
        and cfg.velvet_band is not None
        and gate_active
        and timestamp >= cfg.gate.gate_ts
    ):
        return {
            "limit": 200,
            "max_order": 40,
            "buy": cfg.velvet_band.buy,
            "sell": cfg.velvet_band.sell,
        }
    return base


def simulate(prices: pd.DataFrame, cfg: AlphaConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
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
        gate_decided = cfg.gate is None

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
                if cfg.gate is not None and not gate_decided and timestamp >= cfg.gate.gate_ts:
                    gate_active = open_mid - current_mid >= cfg.gate.drop_ticks
                    gate_decided = True

            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])

            for product in SELL7_SCHEDULES:
                row = group_rows.get(product)
                if row is None:
                    continue

                long_allowed = (
                    cfg.long_recycle is not None
                    and (not cfg.long_requires_gate or gate_active)
                )
                if long_allowed:
                    did_recycle = _maybe_long_recycle(
                        cfg=cfg.long_recycle,
                        rows=row,
                        variant=cfg.label,
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
                                variant=cfg.label,
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
                                variant=cfg.label,
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
                            variant=cfg.label,
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
                            variant=cfg.label,
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
                    "variant": cfg.label,
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


def summarize(trades: pd.DataFrame, pnl: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    product_rows = []
    core_products = ("VEV_5000", "VEV_5100", "VEV_5200")
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        t = trades[
            (trades["variant"] == variant)
            & (trades["dataset"] == dataset)
            & (trades["day"] == day)
        ]
        r = t[t["reason"].eq("long_recycle_sell")]
        vtrades = t[t["product"].eq(UNDERLYING)]
        summary_rows.append(
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
                "recycle_qty": int(r["qty"].sum()) if not r.empty else 0,
                "pnl_VEV_5000": float(last["pnl_VEV_5000"]),
                "pnl_VEV_5100": float(last["pnl_VEV_5100"]),
                "pnl_VEV_5200": float(last["pnl_VEV_5200"]),
            }
        )
        for product in (UNDERLYING, *core_products, "VEV_5300", "VEV_5400", "VEV_5500"):
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


def write_report(doc: Path, out_dir: Path, summary: pd.DataFrame, product: pd.DataFrame) -> None:
    hist = summary[summary["dataset"] == "historical"].copy()
    official = summary[summary["dataset"].str.contains("official", na=False)].copy()
    agg = (
        hist.groupby("variant", sort=False)
        .agg(
            mean_total=("total_pnl", "mean"),
            min_total=("total_pnl", "min"),
            mean_drawdown=("max_drawdown", "mean"),
            active_days=("gate_ever_active", "sum"),
            recycle_qty=("recycle_qty", "sum"),
            mean_velvet=("velvet_pnl", "mean"),
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
            "gate_ever_active",
            "velvet_pnl",
            "velvet_end_pos",
            "velvet_qty",
            "recycle_qty",
            "pnl_VEV_5000",
            "pnl_VEV_5100",
            "pnl_VEV_5200",
        ]
    ].copy()
    official_view["delta_vs_base"] = official_view.groupby("dataset")["total_pnl"].transform(
        lambda s: s - float(s[official_view.loc[s.index, "variant"].eq("sell7_base")].iloc[0])
    )

    product_official = product[product["dataset"].eq("official_sell7_validated")].copy()
    base_product = product_official[product_official["variant"].eq("sell7_base")][["product", "pnl"]]
    base_product = base_product.rename(columns={"pnl": "base_pnl"})
    product_delta = product_official.merge(base_product, on="product", how="left")
    product_delta["delta_vs_base"] = product_delta["pnl"] - product_delta["base_pnl"]
    product_delta = product_delta[
        [
            "variant",
            "product",
            "pnl",
            "base_pnl",
            "delta_vs_base",
            "end_position",
        ]
    ]

    text = f"""# Stacked Alpha Probe Results

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_stacked_alpha_probes
```

Artifacts live under `{out_dir}`.

## Mechanism

This stacks two non-option-native edges found after the `sell7` upload:

1. VELVET regime-gated recycle: after a large early selloff, loosen the VELVET
   buy/sell band so the bot can buy the drop and resell the rebound.
2. Core-voucher long-only recycle: after cheap `VEV_5000/5100/5200` reloads,
   sell only profitable long inventory on a rebound, then let the base schedule
   refill. In the stacked variants, this recycler is gated by the same early
   VELVET selloff condition.

## Historical Three-Day Summary

{markdown_table(agg.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Official 100k Book Proxy

{markdown_table(official_view.sort_values(["dataset", "total_pnl"], ascending=[True, False]), max_rows=120)}

## Official Sell7-Validated Product Deltas

{markdown_table(product_delta.sort_values(["variant", "delta_vs_base"], ascending=[True, False]), max_rows=120)}

## Read

The strongest official-proxy stack is `stack_officialmax_v5248_5264_core3_tp8`.
It is additive because VELVET and the long-only core recycler touch disjoint
limits. The cleaner robustness point is that gating the core recycler avoids
the day-1/day-2 losses seen in the ungated long-only test. This is still a
regime-conditioned probe, not proof of a stable option-native alpha, because
the official 100k path is day-3-like.
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
        print(f"running {cfg.label}", flush=True)
        trades, pnl = simulate(prices, cfg)
        all_trades.append(trades)
        all_pnl.append(pnl)
    trades = pd.concat(all_trades, ignore_index=True)
    pnl = pd.concat(all_pnl, ignore_index=True)
    summary, product = summarize(trades, pnl)
    trades.to_csv(out_dir / "stacked_alpha_trades.csv", index=False)
    pnl.to_csv(out_dir / "stacked_alpha_pnl_path.csv", index=False)
    summary.to_csv(out_dir / "stacked_alpha_summary.csv", index=False)
    product.to_csv(out_dir / "stacked_alpha_product_pnl.csv", index=False)
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
