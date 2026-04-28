"""Evaluate second-generation VELVET regime/recycling probes.

The first-generation official winner was a one-shot early-drop gate:
if VELVET drops enough by 30k, use a looser buy/re-sell band. That proved the
mechanism can fill on the official 100k path, but it is too path-specific for a
1M final upload.

This harness tests cleaner VELVET-only variants:

* the official VELVET-only gate;
* matched negative controls;
* rolling drawdown state machines with optional rebound confirmation.

It deliberately excludes the fragile VEV_5000/5100/5200 core recycler.
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
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_rolling_regime"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_ROLLING_REGIME_PROBES.md"


@dataclass(frozen=True)
class VelvetRegimeConfig:
    label: str
    mode: str
    buy: int = 5248
    sell: int = 5264
    active_buy_limit: int = 200
    active_sell_limit: int = 200
    gate_ts: int = 30_000
    drop_ticks: float = 20.0
    min_ts: int = 20_000
    active_duration: int = 40_000
    cooldown: int = 20_000
    rebound_confirm: float = 0.0
    stop_loss_ticks: float | None = None


def configs() -> list[VelvetRegimeConfig | None]:
    return [
        None,
        VelvetRegimeConfig("one_shot_v5248_5264", "one_shot", buy=5248, sell=5264),
        VelvetRegimeConfig("negctrl_cover_only_v5248_5272", "one_shot", buy=5248, sell=5272),
        VelvetRegimeConfig("one_shot_cover_to_flat_v5248_5264", "one_shot", buy=5248, sell=5264, active_buy_limit=0),
        VelvetRegimeConfig("one_shot_cover_to_short100_v5248_5264", "one_shot", buy=5248, sell=5264, active_buy_limit=-100),
        VelvetRegimeConfig("one_shot_long_cap80_v5248_5264", "one_shot", buy=5248, sell=5264, active_buy_limit=80),
        VelvetRegimeConfig("delayed_gate50_v5248_5264", "one_shot", buy=5248, sell=5264, gate_ts=50_000),
        VelvetRegimeConfig("delayed_gate50_cover_to_flat_v5248_5264", "one_shot", buy=5248, sell=5264, active_buy_limit=0, gate_ts=50_000),
        VelvetRegimeConfig("rolling_d20_dur40_v5248_5264", "rolling", buy=5248, sell=5264, drop_ticks=20, active_duration=40_000),
        VelvetRegimeConfig("rolling_d25_dur30_v5248_5264", "rolling", buy=5248, sell=5264, drop_ticks=25, active_duration=30_000),
        VelvetRegimeConfig("rolling_confirm_d20_r3_v5248_5264", "rolling", buy=5248, sell=5264, drop_ticks=20, rebound_confirm=3, active_duration=40_000),
        VelvetRegimeConfig("rolling_confirm_d25_r3_v5248_5264", "rolling", buy=5248, sell=5264, drop_ticks=25, rebound_confirm=3, active_duration=40_000),
        VelvetRegimeConfig("rolling_confirm_d20_r5_v5247_5264", "rolling", buy=5247, sell=5264, drop_ticks=20, rebound_confirm=5, active_duration=40_000),
        VelvetRegimeConfig("rolling_confirm_d20_r3_stop8", "rolling", buy=5248, sell=5264, drop_ticks=20, rebound_confirm=3, active_duration=40_000, stop_loss_ticks=8),
    ]


def _windowed_prices(historical: pd.DataFrame, *, step: int, window: int) -> pd.DataFrame:
    rows = []
    for day, day_prices in historical.groupby("day", sort=True):
        max_ts = int(day_prices["timestamp"].max())
        for start in range(0, max_ts - window + 1, step):
            end = start + window
            subset = day_prices[
                (day_prices["timestamp"] >= start)
                & (day_prices["timestamp"] < end)
                & (day_prices["product"].isin(PRODUCTS))
            ].copy()
            if subset.empty:
                continue
            subset["timestamp"] = subset["timestamp"].astype(int) - start
            subset["dataset"] = f"hist_d{int(day)}_s{start}"
            subset["day"] = int(day)
            subset["window_start"] = int(start)
            rows.append(subset)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _default_state() -> dict:
    return {
        "open_mid": None,
        "gate_decided": False,
        "gate_active": False,
        "peak_mid": None,
        "trough_mid": None,
        "active_until": -1,
        "cooldown_until": -1,
        "last_seen_ts": -1,
    }


def _update_state(state: dict, timestamp: int, mid: float, cfg: VelvetRegimeConfig | None) -> None:
    if cfg is None:
        return
    if int(state.get("last_seen_ts", -1)) > timestamp:
        state.clear()
        state.update(_default_state())
    state["last_seen_ts"] = timestamp
    if state.get("open_mid") is None:
        state["open_mid"] = mid
    peak = state.get("peak_mid")
    trough = state.get("trough_mid")
    if peak is None or mid > float(peak):
        state["peak_mid"] = mid
    if trough is None or mid < float(trough):
        state["trough_mid"] = mid

    if cfg.mode == "one_shot":
        if not state.get("gate_decided", False) and timestamp >= cfg.gate_ts:
            state["gate_active"] = float(state["open_mid"]) - mid >= cfg.drop_ticks
            state["gate_decided"] = True
        return

    if cfg.mode != "rolling" or timestamp < cfg.min_ts:
        return
    if timestamp < int(state.get("cooldown_until", -1)):
        return
    drawdown = float(state["peak_mid"]) - mid
    if drawdown < cfg.drop_ticks:
        return
    trough = min(float(state.get("trough_mid") or mid), mid)
    state["trough_mid"] = trough
    if cfg.rebound_confirm > 0 and mid < trough + cfg.rebound_confirm:
        return
    state["gate_active"] = True
    state["active_until"] = max(int(state.get("active_until", -1)), timestamp + cfg.active_duration)
    state["cooldown_until"] = timestamp + cfg.cooldown


def _gate_active(state: dict, timestamp: int, cfg: VelvetRegimeConfig | None) -> bool:
    if cfg is None:
        return False
    if cfg.mode == "one_shot":
        return bool(state.get("gate_active", False)) and timestamp >= cfg.gate_ts
    if cfg.mode == "rolling":
        return bool(state.get("gate_active", False)) and timestamp <= int(state.get("active_until", -1))
    return False


def _velvet_cfg(timestamp: int, active: bool, cfg: VelvetRegimeConfig | None) -> dict[str, int]:
    base = {"limit": 200, "buy_limit": 200, "sell_limit": 200, "max_order": 40, "buy": 5246, "sell": 5272}
    if cfg is not None and active and timestamp >= min(cfg.gate_ts, cfg.min_ts):
        return {
            "limit": 200,
            "buy_limit": cfg.active_buy_limit,
            "sell_limit": cfg.active_sell_limit,
            "max_order": 40,
            "buy": cfg.buy,
            "sell": cfg.sell,
        }
    return base


def simulate(prices: pd.DataFrame, cfg: VelvetRegimeConfig | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    variant = "sell7_base" if cfg is None else cfg.label
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []

    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        position = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        costs = {product: PositionCost() for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak_pnl = -float("inf")
        regime_state = _default_state()

        for timestamp, group in day_prices.sort_values(["timestamp", "product"]).groupby("timestamp", sort=True):
            timestamp = int(timestamp)
            group_rows = {str(row.product): row._asdict() for row in group.itertuples(index=False)}
            velvet_row = group_rows.get(UNDERLYING)
            velvet_mid = None
            if velvet_row is not None and pd.notna(velvet_row["mid_price"]):
                velvet_mid = float(velvet_row["mid_price"])
                _update_state(regime_state, timestamp, velvet_mid, cfg)

            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])

            active = _gate_active(regime_state, timestamp, cfg)
            for product in SELL7_SCHEDULES:
                row = group_rows.get(product)
                if row is None:
                    continue
                if product == UNDERLYING:
                    schedule_cfg = _velvet_cfg(timestamp, active, cfg)
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
                            _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="flatten", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)
                    elif position[product] < 0 and pd.notna(ask):
                        qty = min(schedule_cfg["max_order"], ask_volume, -position[product])
                        if qty > 0:
                            _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="buy", reason="flatten", price=float(ask), qty=qty, position=position, cash=cash, costs=costs)
                    continue

                if (
                    product == UNDERLYING
                    and cfg is not None
                    and cfg.stop_loss_ticks is not None
                    and active
                    and position[product] > 0
                    and velvet_mid is not None
                    and velvet_mid <= cfg.buy - cfg.stop_loss_ticks
                    and pd.notna(bid)
                ):
                    qty = min(schedule_cfg["max_order"], bid_volume, position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="stop", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)
                    continue

                buy_limit = int(schedule_cfg.get("buy_limit", schedule_cfg["limit"]))
                sell_limit = int(schedule_cfg.get("sell_limit", schedule_cfg["limit"]))

                if pd.notna(ask) and float(ask) <= schedule_cfg["buy"] and position[product] < buy_limit:
                    qty = min(schedule_cfg["max_order"], ask_volume, buy_limit - position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="buy", reason="schedule", price=float(ask), qty=qty, position=position, cash=cash, costs=costs)
                if pd.notna(bid) and float(bid) >= schedule_cfg["sell"] and position[product] > -sell_limit:
                    qty = min(schedule_cfg["max_order"], bid_volume, sell_limit + position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="schedule", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)

            product_pnls = {
                product: cash[product] + position[product] * last_mid.get(product, 0.0)
                for product in PRODUCTS
            }
            total = float(sum(product_pnls.values()))
            peak_pnl = max(peak_pnl, total)
            pnl_rows.append(
                {
                    "variant": variant,
                    "dataset": dataset,
                    "day": int(day),
                    "timestamp": timestamp,
                    "gate_active": bool(active),
                    "total_pnl": total,
                    "drawdown": total - peak_pnl,
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
            (trades["variant"].eq(variant))
            & (trades["dataset"].eq(dataset))
            & (trades["day"].eq(day))
            & (trades["product"].eq(UNDERLYING))
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


def summarize_windows(summary: pd.DataFrame) -> pd.DataFrame:
    if {"base_total", "base_velvet", "delta_total", "delta_velvet"}.issubset(summary.columns):
        merged = summary.copy()
    else:
        base = summary[summary["variant"].eq("sell7_base")][["dataset", "total_pnl", "velvet_pnl"]].rename(
            columns={"total_pnl": "base_total", "velvet_pnl": "base_velvet"}
        )
        merged = summary.merge(base, on="dataset", how="left")
        merged["delta_total"] = merged["total_pnl"] - merged["base_total"]
        merged["delta_velvet"] = merged["velvet_pnl"] - merged["base_velvet"]
    rows = []
    for variant, group in merged.groupby("variant", sort=False):
        if variant == "sell7_base":
            continue
        active = group[group["gate_ever_active"]]
        eval_group = active if not active.empty else group
        rows.append(
            {
                "variant": variant,
                "windows": int(len(group)),
                "active_windows": int(len(active)),
                "active_rate": float(len(active) / len(group)),
                "all_hit_rate": float((group["delta_total"] > 0).mean()),
                "all_mean_delta": float(group["delta_total"].mean()),
                "active_hit_rate": float((eval_group["delta_total"] > 0).mean()),
                "active_mean_delta": float(eval_group["delta_total"].mean()),
                "active_median_delta": float(eval_group["delta_total"].median()),
                "active_p10_delta": float(eval_group["delta_total"].quantile(0.10)),
                "active_p90_delta": float(eval_group["delta_total"].quantile(0.90)),
                "active_min_delta": float(eval_group["delta_total"].min()),
                "active_max_delta": float(eval_group["delta_total"].max()),
            }
        )
    return pd.DataFrame(rows).sort_values(["all_mean_delta", "active_mean_delta"], ascending=False)


def write_report(
    doc: Path,
    out_dir: Path,
    full_summary: pd.DataFrame,
    window_summary: pd.DataFrame,
    window_detail: pd.DataFrame,
    step: int,
    window: int,
) -> None:
    hist = full_summary[full_summary["dataset"].eq("historical")].copy()
    official = full_summary[full_summary["dataset"].str.contains("official", na=False)].copy()
    hist_agg = (
        hist.groupby("variant", sort=False)
        .agg(
            mean_total=("total_pnl", "mean"),
            min_total=("total_pnl", "min"),
            mean_drawdown=("max_drawdown", "mean"),
            active_days=("gate_ever_active", "sum"),
            mean_velvet=("velvet_pnl", "mean"),
            mean_velvet_qty=("velvet_qty", "mean"),
        )
        .reset_index()
    )
    base_hist = float(hist_agg.loc[hist_agg["variant"].eq("sell7_base"), "mean_total"].iloc[0])
    hist_agg["delta_vs_base"] = hist_agg["mean_total"] - base_hist
    official_view = official.copy()
    official_view["delta_vs_base"] = official_view.groupby("dataset")["total_pnl"].transform(
        lambda s: s - float(s[official_view.loc[s.index, "variant"].eq("sell7_base")].iloc[0])
    )
    worst = window_detail[window_detail["variant"].ne("sell7_base")].nsmallest(12, "delta_total")
    best = window_detail[window_detail["variant"].ne("sell7_base")].nlargest(12, "delta_total")
    text = f"""# VELVET Rolling Regime Probes

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_velvet_rolling_regime_probes
```

Artifacts live under `{out_dir}`.

## Purpose

This is the second-generation VELVET recycling test. It removes the fragile
core-voucher recycler and asks whether VELVET itself can be recycled by a more
robust regime state than the one-shot `30k` official gate.

## Full Public-Day Summary

{markdown_table(hist_agg.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Official 100k Proxy

{markdown_table(official_view.sort_values(["dataset", "delta_vs_base"], ascending=[True, False]), max_rows=160)}

## Sliding {window:,}-Tick Robustness

Public windows are stepped by `{step:,}` ticks.

{markdown_table(window_summary, max_rows=120)}

Worst windows:

{markdown_table(worst[["variant", "dataset", "day", "total_pnl", "base_total", "delta_total", "velvet_pnl", "base_velvet", "delta_velvet", "gate_ever_active", "velvet_end_pos", "velvet_qty"]], max_rows=12)}

Best windows:

{markdown_table(best[["variant", "dataset", "day", "total_pnl", "base_total", "delta_total", "velvet_pnl", "base_velvet", "delta_velvet", "gate_ever_active", "velvet_end_pos", "velvet_qty"]], max_rows=12)}

## Read

For final 1M robustness, prefer variants that preserve the official VELVET
gain while improving active-window hit rate and left-tail behavior. A high
official proxy with a matching negative-control win should be treated as
path luck, not alpha.
"""
    doc.write_text(text)


def run(
    data_dir: Path,
    official_dir: Path,
    out_dir: Path,
    doc: Path,
    step: int,
    window: int,
    labels: set[str] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    historical = load_historical(data_dir)
    official_books, _ = load_official_books(official_dir)
    official = [
        book
        for name, book in official_books.items()
        if name in {"official_sellonly8", "official_disabled", "official_sell7_validated"}
    ]
    full_prices = pd.concat([historical, *official], ignore_index=True)
    window_prices = _windowed_prices(historical, step=step, window=window)
    all_full_trades = []
    all_full_pnl = []
    all_window_summaries = []

    selected = []
    for cfg in configs():
        label = "sell7_base" if cfg is None else cfg.label
        if labels is not None and label != "sell7_base" and label not in labels:
            continue
        selected.append(cfg)

    for cfg in selected:
        label = "sell7_base" if cfg is None else cfg.label
        print(f"full simulate {label}", flush=True)
        trades, pnl = simulate(full_prices, cfg)
        all_full_trades.append(trades)
        all_full_pnl.append(pnl)
        print(f"window simulate {label}", flush=True)
        wtrades, wpnl = simulate(window_prices, cfg)
        all_window_summaries.append(summarize(wtrades, wpnl))

    full_trades = pd.concat(all_full_trades, ignore_index=True)
    full_pnl = pd.concat(all_full_pnl, ignore_index=True)
    full_summary = summarize(full_trades, full_pnl)
    window_detail = pd.concat(all_window_summaries, ignore_index=True)
    base = window_detail[window_detail["variant"].eq("sell7_base")][["dataset", "total_pnl", "velvet_pnl"]].rename(
        columns={"total_pnl": "base_total", "velvet_pnl": "base_velvet"}
    )
    window_detail = window_detail.merge(base, on="dataset", how="left")
    window_detail["delta_total"] = window_detail["total_pnl"] - window_detail["base_total"]
    window_detail["delta_velvet"] = window_detail["velvet_pnl"] - window_detail["base_velvet"]
    window_summary = summarize_windows(window_detail)

    full_trades.to_csv(out_dir / "velvet_rolling_full_trades.csv", index=False)
    full_pnl.to_csv(out_dir / "velvet_rolling_full_pnl.csv", index=False)
    full_summary.to_csv(out_dir / "velvet_rolling_full_summary.csv", index=False)
    window_detail.to_csv(out_dir / "velvet_rolling_window_detail.csv", index=False)
    window_summary.to_csv(out_dir / "velvet_rolling_window_summary.csv", index=False)
    write_report(doc, out_dir, full_summary, window_summary, window_detail, step, window)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(window_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-dir", type=Path, default=DEFAULT_OFFICIAL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--step", type=int, default=25_000)
    parser.add_argument("--window", type=int, default=100_000)
    parser.add_argument("--labels", nargs="*", default=None)
    args = parser.parse_args()
    labels = set(args.labels) if args.labels else None
    run(args.data_dir, args.official_dir, args.out_dir, args.doc, args.step, args.window, labels)


if __name__ == "__main__":
    main()
