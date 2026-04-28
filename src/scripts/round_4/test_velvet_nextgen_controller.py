"""Research next-generation VELVET/options inventory controllers.

This is intentionally robustness-first. It tests controller families that could
generalize to the final 1M run better than the one-time official 100k gate:

* session-open drawdown gates instead of fixed 30k-only gates;
* capped target VELVET inventory;
* core option reduce-only recycling gated by VELVET rebound.

It is not a broad threshold sweep. The output is meant to decide whether any
next-gen mechanism is worth exporting as an upload candidate.
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
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_nextgen_controller"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_NEXTGEN_CONTROLLER_RESEARCH.md"

CORE3 = ("VEV_5000", "VEV_5100", "VEV_5200")


@dataclass(frozen=True)
class GateConfig:
    mode: str
    gate_ts: int = 30_000
    min_ts: int = 20_000
    drop_ticks: float = 20.0
    rebound_confirm: float = 0.0
    active_duration: int | None = None
    cooldown: int = 20_000


@dataclass(frozen=True)
class CoreReduceConfig:
    products: tuple[str, ...] = CORE3
    active_abs: int = 280
    floor_abs: int = 240
    take_profit: int = 8
    max_order: int = 20
    start_ts: int = 50_000
    require_gate: bool = True
    min_spot: float | None = None
    negative_window: bool = False


@dataclass(frozen=True)
class NextGenConfig:
    label: str
    gate: GateConfig | None = None
    buy: int = 5248
    sell: int = 5264
    active_buy_limit: int = 200
    active_sell_limit: int = 200
    core_reduce: CoreReduceConfig | None = None


def _configs() -> list[NextGenConfig]:
    one_shot = GateConfig("one_shot", gate_ts=30_000, drop_ticks=20)
    delayed50 = GateConfig("one_shot", gate_ts=50_000, drop_ticks=20)
    session30 = GateConfig("session_drop", min_ts=50_000, drop_ticks=30)
    session40 = GateConfig("session_drop", min_ts=50_000, drop_ticks=40)
    rebound30 = GateConfig("session_drop", min_ts=50_000, drop_ticks=30, rebound_confirm=5)
    rebound40 = GateConfig("session_drop", min_ts=50_000, drop_ticks=40, rebound_confirm=5)
    core_rebound = CoreReduceConfig(take_profit=8, min_spot=5260)
    core_rebound_hi = CoreReduceConfig(take_profit=10, min_spot=5262)
    core_rebound_neg = CoreReduceConfig(take_profit=8, min_spot=5260, negative_window=True)
    return [
        NextGenConfig("sell7_base"),
        NextGenConfig("ref_one_shot_v5248_5264", gate=one_shot),
        NextGenConfig("ref_delayed50_v5248_5264", gate=delayed50),
        NextGenConfig("ref_one_shot_plus80", gate=one_shot, active_buy_limit=80),
        NextGenConfig("session_drop30_v5248_5264", gate=session30),
        NextGenConfig("session_drop40_v5248_5264", gate=session40),
        NextGenConfig("session_drop30_plus80", gate=session30, active_buy_limit=80),
        NextGenConfig("session_drop40_plus80", gate=session40, active_buy_limit=80),
        NextGenConfig("session_rebound30_r5_v5248_5264", gate=rebound30),
        NextGenConfig("session_rebound40_r5_v5248_5264", gate=rebound40),
        NextGenConfig("one_shot_core_rebound5260_tp8", gate=one_shot, core_reduce=core_rebound),
        NextGenConfig("delayed50_core_rebound5260_tp8", gate=delayed50, core_reduce=core_rebound),
        NextGenConfig("session40_core_rebound5260_tp8", gate=session40, core_reduce=core_rebound),
        NextGenConfig("one_shot_core_rebound5262_tp10", gate=one_shot, core_reduce=core_rebound_hi),
        NextGenConfig("negctrl_one_shot_core_rebound5260_tp8", gate=one_shot, core_reduce=core_rebound_neg),
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


def _default_gate_state() -> dict[str, float | int | bool | None]:
    return {
        "open_mid": None,
        "peak_mid": None,
        "trough_mid": None,
        "gate_decided": False,
        "gate_active": False,
        "active_until": -1,
        "cooldown_until": -1,
        "last_seen_ts": -1,
    }


def _update_gate(state: dict, timestamp: int, mid: float, cfg: GateConfig | None) -> None:
    if cfg is None:
        return
    if int(state.get("last_seen_ts", -1)) > timestamp:
        state.clear()
        state.update(_default_gate_state())
    state["last_seen_ts"] = timestamp
    if state.get("open_mid") is None:
        state["open_mid"] = mid
    if state.get("peak_mid") is None or mid > float(state["peak_mid"]):
        state["peak_mid"] = mid
    if state.get("trough_mid") is None or mid < float(state["trough_mid"]):
        state["trough_mid"] = mid

    open_mid = float(state["open_mid"])
    if cfg.mode == "one_shot":
        if not bool(state.get("gate_decided", False)) and timestamp >= cfg.gate_ts:
            state["gate_active"] = open_mid - mid >= cfg.drop_ticks
            state["gate_decided"] = True
        return

    if cfg.mode != "session_drop":
        return
    if timestamp < cfg.min_ts or timestamp < int(state.get("cooldown_until", -1)):
        return
    if open_mid - mid < cfg.drop_ticks:
        return
    trough = float(state.get("trough_mid") or mid)
    if cfg.rebound_confirm > 0 and mid < trough + cfg.rebound_confirm:
        return
    state["gate_active"] = True
    if cfg.active_duration is not None:
        state["active_until"] = max(int(state.get("active_until", -1)), timestamp + cfg.active_duration)
        state["cooldown_until"] = timestamp + cfg.cooldown


def _gate_active(state: dict, timestamp: int, cfg: GateConfig | None) -> bool:
    if cfg is None:
        return False
    if cfg.mode == "one_shot":
        return bool(state.get("gate_active", False)) and timestamp >= cfg.gate_ts
    if cfg.mode == "session_drop":
        if not bool(state.get("gate_active", False)):
            return False
        if cfg.active_duration is None:
            return True
        return timestamp <= int(state.get("active_until", -1))
    return False


def _negative_window_active(timestamp: int) -> bool:
    return timestamp % 35_000 < 5_000


def _maybe_core_reduce(
    *,
    cfg: CoreReduceConfig | None,
    row: dict[str, object],
    variant: str,
    dataset: str,
    day: int,
    timestamp: int,
    gate_active: bool,
    velvet_mid: float | None,
    position: dict[str, int],
    cash: dict[str, float],
    costs: dict[str, PositionCost],
    trade_rows: list[dict],
) -> bool:
    if cfg is None:
        return False
    if cfg.require_gate and not gate_active:
        return False
    if timestamp < cfg.start_ts:
        return False
    if cfg.min_spot is not None and (velvet_mid is None or velvet_mid < cfg.min_spot):
        return False
    if cfg.negative_window and not _negative_window_active(timestamp):
        return False
    product = str(row["product"])
    if product not in cfg.products:
        return False
    pos = position[product]
    avg = costs[product].avg_price
    if avg is None or pos < cfg.active_abs:
        return False
    best_bid = row["bid_price_1"]
    if pd.isna(best_bid):
        return False
    qty = min(cfg.max_order, _volume(row["bid_volume_1"]), pos - cfg.floor_abs)
    if qty <= 0 or float(best_bid) < float(avg) + cfg.take_profit:
        return False
    _record_trade(
        trade_rows,
        variant=variant,
        dataset=dataset,
        day=day,
        timestamp=timestamp,
        product=product,
        side="sell",
        reason="core_reduce_rebound",
        price=float(best_bid),
        qty=qty,
        position=position,
        cash=cash,
        costs=costs,
    )
    return True


def _schedule_cfg(product: str, timestamp: int, active: bool, cfg: NextGenConfig) -> dict[str, int] | None:
    if product != UNDERLYING:
        return _schedule_for(product, timestamp, SELL7_SCHEDULES)
    base = {"limit": 200, "max_order": 40, "buy": 5246, "sell": 5272, "buy_limit": 200, "sell_limit": 200}
    if cfg.gate is not None and active:
        return {
            "limit": 200,
            "max_order": 40,
            "buy": cfg.buy,
            "sell": cfg.sell,
            "buy_limit": cfg.active_buy_limit,
            "sell_limit": cfg.active_sell_limit,
        }
    return base


def simulate(prices: pd.DataFrame, cfg: NextGenConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []
    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        position = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        costs = {product: PositionCost() for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak_pnl = -float("inf")
        gate_state = _default_gate_state()

        for timestamp, group in day_prices.sort_values(["timestamp", "product"]).groupby("timestamp", sort=True):
            timestamp = int(timestamp)
            group_rows = {str(row.product): row._asdict() for row in group.itertuples(index=False)}
            velvet_mid = None
            velvet_row = group_rows.get(UNDERLYING)
            if velvet_row is not None and pd.notna(velvet_row["mid_price"]):
                velvet_mid = float(velvet_row["mid_price"])
                _update_gate(gate_state, timestamp, velvet_mid, cfg.gate)
            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])

            active = _gate_active(gate_state, timestamp, cfg.gate)
            for product in SELL7_SCHEDULES:
                row = group_rows.get(product)
                if row is None:
                    continue
                if _maybe_core_reduce(
                    cfg=cfg.core_reduce,
                    row=row,
                    variant=cfg.label,
                    dataset=str(dataset),
                    day=int(day),
                    timestamp=timestamp,
                    gate_active=active,
                    velvet_mid=velvet_mid,
                    position=position,
                    cash=cash,
                    costs=costs,
                    trade_rows=trade_rows,
                ):
                    continue

                scfg = _schedule_cfg(product, timestamp, active, cfg)
                if scfg is None:
                    continue
                bid = row["bid_price_1"]
                ask = row["ask_price_1"]
                bid_volume = _volume(row["bid_volume_1"])
                ask_volume = _volume(row["ask_volume_1"])

                if timestamp >= FLATTEN_START:
                    if position[product] > 0 and pd.notna(bid):
                        qty = min(int(scfg["max_order"]), bid_volume, position[product])
                        if qty > 0:
                            _record_trade(trade_rows, variant=cfg.label, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="flatten", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)
                    elif position[product] < 0 and pd.notna(ask):
                        qty = min(int(scfg["max_order"]), ask_volume, -position[product])
                        if qty > 0:
                            _record_trade(trade_rows, variant=cfg.label, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="buy", reason="flatten", price=float(ask), qty=qty, position=position, cash=cash, costs=costs)
                    continue

                buy_limit = int(scfg.get("buy_limit", scfg["limit"]))
                sell_limit = int(scfg.get("sell_limit", scfg["limit"]))
                if pd.notna(ask) and float(ask) <= int(scfg["buy"]) and position[product] < buy_limit:
                    qty = min(int(scfg["max_order"]), ask_volume, buy_limit - position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=cfg.label, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="buy", reason="schedule", price=float(ask), qty=qty, position=position, cash=cash, costs=costs)
                if pd.notna(bid) and float(bid) >= int(scfg["sell"]) and position[product] > -sell_limit:
                    qty = min(int(scfg["max_order"]), bid_volume, sell_limit + position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=cfg.label, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="schedule", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)

            product_pnls = {
                product: cash[product] + position[product] * last_mid.get(product, 0.0)
                for product in PRODUCTS
            }
            total = float(sum(product_pnls.values()))
            peak_pnl = max(peak_pnl, total)
            pnl_rows.append(
                {
                    "variant": cfg.label,
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
        t = trades[(trades["variant"].eq(variant)) & (trades["dataset"].eq(dataset)) & (trades["day"].eq(day))]
        core_reduce = t[t["reason"].eq("core_reduce_rebound")] if not t.empty else t
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
                "core_pnl": sum(float(last[f"pnl_{product}"]) for product in CORE3),
                "core_reduce_qty": int(core_reduce["qty"].sum()) if not core_reduce.empty else 0,
                "core_reduce_trades": int(len(core_reduce)) if not core_reduce.empty else 0,
            }
        )
    return pd.DataFrame(rows)


def summarize_windows(summary: pd.DataFrame) -> pd.DataFrame:
    if {"base_total", "base_velvet", "base_core", "delta_total", "delta_velvet", "delta_core"}.issubset(summary.columns):
        merged = summary.copy()
    else:
        base = summary[summary["variant"].eq("sell7_base")][["dataset", "total_pnl", "velvet_pnl", "core_pnl"]].rename(
            columns={"total_pnl": "base_total", "velvet_pnl": "base_velvet", "core_pnl": "base_core"}
        )
        merged = summary.merge(base, on="dataset", how="left")
        merged["delta_total"] = merged["total_pnl"] - merged["base_total"]
        merged["delta_velvet"] = merged["velvet_pnl"] - merged["base_velvet"]
        merged["delta_core"] = merged["core_pnl"] - merged["base_core"]
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
                "active_min_delta": float(eval_group["delta_total"].min()),
                "active_max_delta": float(eval_group["delta_total"].max()),
                "active_mean_velvet_delta": float(eval_group["delta_velvet"].mean()),
                "active_mean_core_delta": float(eval_group["delta_core"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["all_mean_delta", "active_mean_delta"], ascending=False)


def write_report(
    doc: Path,
    out_dir: Path,
    full_summary: pd.DataFrame,
    official_summary: pd.DataFrame,
    window_summary: pd.DataFrame,
    window_detail: pd.DataFrame,
    step: int,
    window: int,
) -> None:
    hist = full_summary[full_summary["dataset"].eq("historical")].copy()
    hist_agg = hist.groupby("variant", sort=False).agg(
        mean_total=("total_pnl", "mean"),
        min_total=("total_pnl", "min"),
        mean_drawdown=("max_drawdown", "mean"),
        active_days=("gate_ever_active", "sum"),
        mean_velvet=("velvet_pnl", "mean"),
        mean_core=("core_pnl", "mean"),
        core_reduce_qty=("core_reduce_qty", "sum"),
    ).reset_index()
    base_hist = float(hist_agg.loc[hist_agg["variant"].eq("sell7_base"), "mean_total"].iloc[0])
    hist_agg["delta_vs_base"] = hist_agg["mean_total"] - base_hist

    official = official_summary.copy()
    official["delta_vs_base"] = official.groupby("dataset")["total_pnl"].transform(
        lambda values: values - float(values[official.loc[values.index, "variant"].eq("sell7_base")].iloc[0])
    )
    worst = window_detail[window_detail["variant"].ne("sell7_base")].nsmallest(15, "delta_total")
    best = window_detail[window_detail["variant"].ne("sell7_base")].nlargest(15, "delta_total")
    text = f"""# VELVET Next-Generation Controller Research

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_velvet_nextgen_controller
```

Artifacts live under `{out_dir}`.

## Purpose

This pass tries to extract additional VELVET/options alpha without fitting to
the official 100k prefix. It tests session-open drawdown gates, capped VELVET
inventory, and core option reduce-only rules gated by VELVET rebound.

## Historical Full-Day Summary

{markdown_table(hist_agg.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Official 100k Proxy

{markdown_table(official.sort_values(["dataset", "delta_vs_base"], ascending=[True, False]), max_rows=160)}

## Sliding {window:,}-Tick Robustness

Public windows are stepped by `{step:,}` ticks.

{markdown_table(window_summary, max_rows=120)}

Worst windows:

{markdown_table(worst[["variant", "dataset", "day", "total_pnl", "base_total", "delta_total", "delta_velvet", "delta_core", "gate_ever_active", "velvet_end_pos", "core_reduce_qty"]], max_rows=15)}

Best windows:

{markdown_table(best[["variant", "dataset", "day", "total_pnl", "base_total", "delta_total", "delta_velvet", "delta_core", "gate_ever_active", "velvet_end_pos", "core_reduce_qty"]], max_rows=15)}

## Read

Promote only variants that improve public full-day behavior and sliding-window
left tail, or that add official PnL with a clean mechanism and strong controls.
Official-only gains are calibration, not final-1M proof.
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
        if name in {"official_sell7_validated", "official_disabled", "official_sellonly8"}
    ]
    full_prices = pd.concat([historical, *official], ignore_index=True)
    window_prices = _windowed_prices(historical, step=step, window=window)

    full_trades = []
    full_pnls = []
    window_summaries = []
    selected = [cfg for cfg in _configs() if labels is None or cfg.label == "sell7_base" or cfg.label in labels]
    for cfg in selected:
        print(f"full simulate {cfg.label}", flush=True)
        trades, pnl = simulate(full_prices, cfg)
        full_trades.append(trades)
        full_pnls.append(pnl)
        print(f"window simulate {cfg.label}", flush=True)
        wtrades, wpnl = simulate(window_prices, cfg)
        window_summaries.append(summarize(wtrades, wpnl))

    all_full_trades = pd.concat(full_trades, ignore_index=True)
    all_full_pnl = pd.concat(full_pnls, ignore_index=True)
    full_summary = summarize(all_full_trades, all_full_pnl)
    official_summary = full_summary[full_summary["dataset"].str.startswith("official")].copy()
    window_detail = pd.concat(window_summaries, ignore_index=True)
    base = window_detail[window_detail["variant"].eq("sell7_base")][["dataset", "total_pnl", "velvet_pnl", "core_pnl"]].rename(
        columns={"total_pnl": "base_total", "velvet_pnl": "base_velvet", "core_pnl": "base_core"}
    )
    window_detail = window_detail.merge(base, on="dataset", how="left")
    window_detail["delta_total"] = window_detail["total_pnl"] - window_detail["base_total"]
    window_detail["delta_velvet"] = window_detail["velvet_pnl"] - window_detail["base_velvet"]
    window_detail["delta_core"] = window_detail["core_pnl"] - window_detail["base_core"]
    window_summary = summarize_windows(window_detail)

    all_full_trades.to_csv(out_dir / "nextgen_full_trades.csv", index=False)
    all_full_pnl.to_csv(out_dir / "nextgen_full_pnl.csv", index=False)
    full_summary.to_csv(out_dir / "nextgen_full_summary.csv", index=False)
    official_summary.to_csv(out_dir / "nextgen_official_summary.csv", index=False)
    window_detail.to_csv(out_dir / "nextgen_window_detail.csv", index=False)
    window_summary.to_csv(out_dir / "nextgen_window_summary.csv", index=False)
    write_report(doc, out_dir, full_summary, official_summary, window_summary, window_detail, step, window)
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
