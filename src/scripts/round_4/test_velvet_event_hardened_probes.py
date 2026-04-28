"""Bounded VELVET hardening probes from event-level markouts.

The event-markout pass found one plausible non-oracle mechanism: after a sharp
5k/10k VELVET drop, buying at 5248 has positive short-horizon touch markout.
This script tests only that mechanism under position limits and public-window
robustness. It deliberately avoids a broad sweep.
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
    UNDERLYING,
    load_historical,
    load_official_books,
)
from src.scripts.round_4.test_core_recycler_probes import markdown_table


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_event_hardened"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_EVENT_HARDENED_PROBES.md"


@dataclass(frozen=True)
class Config:
    label: str
    move_horizon: int = 5_000
    move_trigger: float = -10.0
    active_duration: int = 0
    buy: int = 5248
    sell: int = 5272
    buy_limit: int = 200
    sell_limit: int = 200
    max_order: int = 40
    require_open_drop: float | None = None


def configs() -> list[Config | None]:
    return [
        None,
        Config("mom5_down10_pulse_buyonly_cap200", move_horizon=5_000, move_trigger=-10, active_duration=0, buy=5248, sell=5272, buy_limit=200),
        Config("mom5_down10_pulse_buyonly_cap80", move_horizon=5_000, move_trigger=-10, active_duration=0, buy=5248, sell=5272, buy_limit=80),
        Config("mom5_down10_dur10_full_cap200", move_horizon=5_000, move_trigger=-10, active_duration=10_000, buy=5248, sell=5264, buy_limit=200),
        Config("mom5_down10_dur30_full_cap200", move_horizon=5_000, move_trigger=-10, active_duration=30_000, buy=5248, sell=5264, buy_limit=200),
        Config("mom10_down15_pulse_buyonly_cap200", move_horizon=10_000, move_trigger=-15, active_duration=0, buy=5248, sell=5272, buy_limit=200),
        Config("mom5_down10_drop20_pulse_buyonly", move_horizon=5_000, move_trigger=-10, active_duration=0, buy=5248, sell=5272, buy_limit=200, require_open_drop=20),
    ]


def _load_velvet(data_dir: Path, official_dir: Path) -> pd.DataFrame:
    historical = load_historical(data_dir)
    official_books, _ = load_official_books(official_dir)
    official = [
        book
        for name, book in official_books.items()
        if name in {"official_sell7_validated", "official_disabled", "official_sellonly8"}
    ]
    prices = pd.concat([historical, *official], ignore_index=True)
    return prices[prices["product"].eq(UNDERLYING)].sort_values(["dataset", "day", "timestamp"]).reset_index(drop=True)


def _windowed(prices: pd.DataFrame, *, step: int, window: int) -> pd.DataFrame:
    rows = []
    historical = prices[prices["dataset"].eq("historical")]
    for day, day_prices in historical.groupby("day", sort=True):
        max_ts = int(day_prices["timestamp"].max())
        for start in range(0, max_ts - window + 1, step):
            subset = day_prices[(day_prices["timestamp"] >= start) & (day_prices["timestamp"] < start + window)].copy()
            if subset.empty:
                continue
            subset["timestamp"] = subset["timestamp"].astype(int) - start
            subset["dataset"] = f"hist_d{int(day)}_s{start}"
            subset["window_start"] = int(start)
            rows.append(subset)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _volume(value: object) -> int:
    if pd.isna(value):
        return 0
    return int(abs(float(value)))


def _add_moves(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("timestamp").reset_index(drop=True).copy()
    mid = pd.to_numeric(group["mid_price"], errors="coerce")
    if len(group) > 1:
        step = int(np.nanmedian(np.diff(group["timestamp"].to_numpy(dtype=int))))
        step = max(step, 1)
    else:
        step = 100
    group["open_mid"] = float(mid.iloc[0])
    group["open_drop"] = group["open_mid"] - mid
    for horizon in (5_000, 10_000):
        steps = max(1, int(round(horizon / step)))
        group[f"move_back_{horizon}"] = mid - mid.shift(steps)
    return group


def _active_state(row: pd.Series, cfg: Config, active_until: int) -> int:
    ts = int(row["timestamp"])
    move = row.get(f"move_back_{cfg.move_horizon}")
    if pd.isna(move) or float(move) > cfg.move_trigger:
        return active_until
    if cfg.require_open_drop is not None and float(row.get("open_drop", 0.0)) < cfg.require_open_drop:
        return active_until
    return max(active_until, ts + cfg.active_duration)


def simulate(prices: pd.DataFrame, cfg: Config | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    label = "sell7_base" if cfg is None else cfg.label
    trades = []
    pnl_rows = []
    for (dataset, day), raw_group in prices.groupby(["dataset", "day"], sort=False):
        group = _add_moves(raw_group)
        pos = 0
        cash = 0.0
        peak = -float("inf")
        active_until = -1
        for row in group.itertuples(index=False):
            data = row._asdict()
            ts = int(data["timestamp"])
            bid = data.get("bid_price_1")
            ask = data.get("ask_price_1")
            bid_vol = _volume(data.get("bid_volume_1"))
            ask_vol = _volume(data.get("ask_volume_1"))
            max_order = 40 if cfg is None else cfg.max_order
            buy_px = 5246
            sell_px = 5272
            buy_limit = 200
            sell_limit = 200
            active = False
            if cfg is not None:
                active_until = _active_state(pd.Series(data), cfg, active_until)
                active = ts <= active_until
                if active:
                    buy_px = cfg.buy
                    sell_px = cfg.sell
                    buy_limit = cfg.buy_limit
                    sell_limit = cfg.sell_limit

            if ts >= FLATTEN_START:
                if pos > 0 and pd.notna(bid):
                    qty = min(max_order, bid_vol, pos)
                    if qty > 0:
                        cash += float(bid) * qty
                        pos -= qty
                        trades.append(_trade(label, dataset, day, ts, "sell", "flatten", bid, qty, pos, active))
                elif pos < 0 and pd.notna(ask):
                    qty = min(max_order, ask_vol, -pos)
                    if qty > 0:
                        cash -= float(ask) * qty
                        pos += qty
                        trades.append(_trade(label, dataset, day, ts, "buy", "flatten", ask, qty, pos, active))
            else:
                if pd.notna(ask) and float(ask) <= buy_px and pos < buy_limit:
                    qty = min(max_order, ask_vol, buy_limit - pos)
                    if qty > 0:
                        cash -= float(ask) * qty
                        pos += qty
                        trades.append(_trade(label, dataset, day, ts, "buy", "schedule", ask, qty, pos, active))
                if pd.notna(bid) and float(bid) >= sell_px and pos > -sell_limit:
                    qty = min(max_order, bid_vol, sell_limit + pos)
                    if qty > 0:
                        cash += float(bid) * qty
                        pos -= qty
                        trades.append(_trade(label, dataset, day, ts, "sell", "schedule", bid, qty, pos, active))
            pnl = cash + pos * float(data["mid_price"])
            peak = max(peak, pnl)
            pnl_rows.append(
                {
                    "variant": label,
                    "dataset": dataset,
                    "day": int(day),
                    "timestamp": ts,
                    "pnl": float(pnl),
                    "drawdown": float(pnl - peak),
                    "pos": int(pos),
                    "active": bool(active),
                }
            )
    return pd.DataFrame(trades), pd.DataFrame(pnl_rows)


def _trade(label: str, dataset: str, day: int, ts: int, side: str, reason: str, price: float, qty: int, pos: int, active: bool) -> dict:
    return {
        "variant": label,
        "dataset": dataset,
        "day": int(day),
        "timestamp": int(ts),
        "side": side,
        "reason": reason,
        "price": float(price),
        "qty": int(qty),
        "pos_after": int(pos),
        "active": bool(active),
    }


def summarize(trades: pd.DataFrame, pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        own = trades[(trades["variant"].eq(variant)) & (trades["dataset"].eq(dataset)) & (trades["day"].eq(day))]
        active_trades = own[own["active"]] if not own.empty else own
        rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "pnl": float(last["pnl"]),
                "max_drawdown": float(group["drawdown"].min()),
                "end_pos": int(last["pos"]),
                "active_ever": bool(group["active"].any()),
                "trade_rows": int(len(own)),
                "active_trade_rows": int(len(active_trades)),
                "abs_qty": int(own["qty"].sum()) if not own.empty else 0,
            }
        )
    return pd.DataFrame(rows)


def compare_to_base(summary: pd.DataFrame) -> pd.DataFrame:
    base = summary[summary["variant"].eq("sell7_base")][["dataset", "day", "pnl"]].rename(columns={"pnl": "base_pnl"})
    out = summary.merge(base, on=["dataset", "day"], how="left")
    out["delta_vs_base"] = out["pnl"] - out["base_pnl"]
    return out


def window_summary(compared: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant, group in compared.groupby("variant", sort=False):
        if variant == "sell7_base":
            continue
        active = group[group["active_ever"]]
        eval_group = active if not active.empty else group
        rows.append(
            {
                "variant": variant,
                "windows": int(len(group)),
                "active_windows": int(len(active)),
                "all_mean_delta": float(group["delta_vs_base"].mean()),
                "all_hit_rate": float((group["delta_vs_base"] > 0).mean()),
                "active_mean_delta": float(eval_group["delta_vs_base"].mean()),
                "active_hit_rate": float((eval_group["delta_vs_base"] > 0).mean()),
                "active_p10_delta": float(eval_group["delta_vs_base"].quantile(0.10)),
                "active_min_delta": float(eval_group["delta_vs_base"].min()),
                "active_max_delta": float(eval_group["delta_vs_base"].max()),
            }
        )
    return pd.DataFrame(rows).sort_values(["all_mean_delta", "active_mean_delta"], ascending=False)


def write_report(doc: Path, out_dir: Path, full_compared: pd.DataFrame, window_compared: pd.DataFrame, win_summary: pd.DataFrame) -> None:
    hist = full_compared[full_compared["dataset"].eq("historical")]
    official = full_compared[full_compared["dataset"].str.startswith("official", na=False)]
    hist_summary = (
        hist.groupby("variant", sort=False)
        .agg(mean_pnl=("pnl", "mean"), min_pnl=("pnl", "min"), mean_delta=("delta_vs_base", "mean"), min_delta=("delta_vs_base", "min"), mean_abs_qty=("abs_qty", "mean"))
        .reset_index()
        .sort_values("mean_delta", ascending=False)
    )
    official_view = official.sort_values(["dataset", "delta_vs_base"], ascending=[True, False])
    worst = window_compared[window_compared["variant"].ne("sell7_base")].nsmallest(20, "delta_vs_base")
    text = f"""# VELVET Event-Hardened Probes

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.test_velvet_event_hardened_probes
```

Artifacts live under `{out_dir}`.

## Purpose

This is a bounded follow-up to the event markout result. It tests whether the
best short-horizon VELVET entry condition, a sharp recent down-move, improves
the current `sell7` VELVET sleeve under position limits.

## Public Full-Day VELVET-Only Result

{markdown_table(hist_summary, max_rows=80)}

## Official 100k Proxy

{markdown_table(official_view, max_rows=120)}

## Public 100k Window Robustness

{markdown_table(win_summary, max_rows=80)}

Worst windows:

{markdown_table(worst[["variant", "dataset", "pnl", "base_pnl", "delta_vs_base", "end_pos", "active_ever", "abs_qty"]], max_rows=20)}

## Read

Do not promote these as final candidates.

The best-looking bounded variant is `mom5_down10_drop20_pulse_buyonly`: it adds
`+2187` on the official proxy and has positive 100k-window mean, but it loses
`-1093` on public full-day mean and its active-window hit rate is only about
`8%`. The full-duration variants recreate the official one-shot gain, but their
public-window tails are materially worse.

This confirms the event markout effect is real but too small/overlapping to
beat the current `sell7` VELVET inventory sleeve robustly. Keep `expstack8060`
as the max-EV full-stack candidate; keep delayed/plus80 style VELVET only as a
risk hedge, not as a replacement with higher expected alpha.
"""
    doc.write_text(text)


def run(data_dir: Path, official_dir: Path, out_dir: Path, doc: Path, step: int, window: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    velvet = _load_velvet(data_dir, official_dir)
    windows = _windowed(velvet, step=step, window=window)
    all_trades = []
    all_pnl = []
    all_window_trades = []
    all_window_pnl = []
    for cfg in configs():
        label = "sell7_base" if cfg is None else cfg.label
        print(f"simulate {label}", flush=True)
        trades, pnl = simulate(velvet, cfg)
        all_trades.append(trades)
        all_pnl.append(pnl)
        wtrades, wpnl = simulate(windows, cfg)
        all_window_trades.append(wtrades)
        all_window_pnl.append(wpnl)
    trades = pd.concat(all_trades, ignore_index=True)
    pnl = pd.concat(all_pnl, ignore_index=True)
    full_summary = summarize(trades, pnl)
    full_compared = compare_to_base(full_summary)

    window_trades = pd.concat(all_window_trades, ignore_index=True)
    window_pnl = pd.concat(all_window_pnl, ignore_index=True)
    window_compared = compare_to_base(summarize(window_trades, window_pnl))
    win_summary = window_summary(window_compared)

    trades.to_csv(out_dir / "velvet_event_hardened_trades.csv", index=False)
    pnl.to_csv(out_dir / "velvet_event_hardened_pnl.csv", index=False)
    full_compared.to_csv(out_dir / "velvet_event_hardened_full_summary.csv", index=False)
    window_compared.to_csv(out_dir / "velvet_event_hardened_window_detail.csv", index=False)
    win_summary.to_csv(out_dir / "velvet_event_hardened_window_summary.csv", index=False)
    write_report(doc, out_dir, full_compared, window_compared, win_summary)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(win_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-dir", type=Path, default=DEFAULT_OFFICIAL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--step", type=int, default=100_000)
    parser.add_argument("--window", type=int, default=100_000)
    args = parser.parse_args()
    run(args.data_dir, args.official_dir, args.out_dir, args.doc, args.step, args.window)


if __name__ == "__main__":
    main()
