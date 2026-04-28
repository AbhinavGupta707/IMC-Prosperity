"""Search for robust VELVET regime classifiers.

The previous next-gen pass showed that plain open-drawdown / rolling-drawdown
gates overfire. This script asks a stricter question:

Do path-shape, liquidity, or counterparty-flow features separate reboundable
VELVET drawdowns from toxic ones in a way that survives leave-one-day checks?

If a feature family survives, the script simulates a small number of transparent
gates. It does not fit on the official 100k simulator; official logs are used
only as calibration after historical public checks.
"""

from __future__ import annotations

import argparse
import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.scripts.round_4.analyze_velvet_option_complex import (
    DEFAULT_DATA_DIR,
    FLATTEN_START,
    PRODUCTS,
    SELL7_SCHEDULES,
    UNDERLYING,
    _numeric_prices,
    _schedule_for,
    load_historical,
)
from src.scripts.round_4.test_core_recycler_probes import (
    PositionCost,
    _record_trade,
    _volume,
    markdown_table,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OFFICIAL_LOG = REPO_ROOT / "r4 Sim Results" / "validated" / "511763.log"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_regime_classifier"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_REGIME_CLASSIFIER_RESEARCH.md"

FLOW_WINDOWS = (1_000, 5_000, 10_000, 30_000)
MOVE_HORIZONS = (1_000, 5_000, 10_000, 30_000, 100_000)
KEY_MARKS = ("Mark 22", "Mark 55", "Mark 67")


@dataclass(frozen=True)
class GateRule:
    label: str
    drop_source: str
    drop_ticks: float
    min_ts: int
    buy: int = 5248
    sell: int = 5264
    active_buy_limit: int = 200
    active_sell_limit: int = 200
    max_ts: int | None = None
    rebound_min: float | None = None
    rebound_max: float | None = None
    roll10k_pos_max: float | None = None
    past_move_min: float | None = None
    past_move_max: float | None = None
    imbalance_min: float | None = None
    imbalance_max: float | None = None
    spread_max: float | None = None
    mark67_buy_cnt30_min: float | None = None
    mark67_buy_qty30_min: float | None = None
    mark55_sell_qty30_min: float | None = None
    mark22_sell_qty30_min: float | None = None
    active_duration: int | None = None


def load_historical_trades(data_dir: Path) -> pd.DataFrame:
    frames = []
    for day in (1, 2, 3):
        trades = pd.read_csv(data_dir / f"trades_round_4_day_{day}.csv", sep=";")
        trades["day"] = day
        frames.append(trades)
    out = pd.concat(frames, ignore_index=True)
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce").astype(int)
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(0).astype(int)
    return out


def load_official(log_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(log_path.read_text())
    prices = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    prices = _numeric_prices(prices, dataset="official_sell7_validated")
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
    trades = trades[(trades["buyer"] != "SUBMISSION") & (trades["seller"] != "SUBMISSION")].copy()
    trades["day"] = 3
    for col in ("timestamp", "price", "quantity"):
        trades[col] = pd.to_numeric(trades[col], errors="coerce")
    trades["timestamp"] = trades["timestamp"].astype(int)
    trades["quantity"] = trades["quantity"].fillna(0).astype(int)
    return prices, trades


def _velvet_panel(prices: pd.DataFrame) -> pd.DataFrame:
    panel = prices[prices["product"].eq(UNDERLYING)].copy()
    panel = panel.sort_values(["dataset", "day", "timestamp"]).reset_index(drop=True)
    panel.rename(
        columns={
            "bid_price_1": "bid",
            "ask_price_1": "ask",
            "bid_volume_1": "bid_vol",
            "ask_volume_1": "ask_vol",
            "mid_price": "mid",
        },
        inplace=True,
    )
    panel["spread"] = panel["ask"] - panel["bid"]
    denom = panel["bid_vol"].fillna(0) + panel["ask_vol"].fillna(0)
    panel["imbalance"] = np.where(denom > 0, (panel["bid_vol"].fillna(0) - panel["ask_vol"].fillna(0)) / denom, 0.0)
    frames = []
    for (_dataset, _day), group in panel.groupby(["dataset", "day"], sort=False):
        group = group.copy()
        group["open_mid"] = float(group["mid"].iloc[0])
        group["open_drop"] = group["open_mid"] - group["mid"]
        group["peak_mid"] = group["mid"].cummax()
        group["trough_mid"] = group["mid"].cummin()
        group["peak_drawdown"] = group["peak_mid"] - group["mid"]
        group["trough_rebound"] = group["mid"] - group["trough_mid"]
        for horizon in MOVE_HORIZONS:
            steps = max(1, horizon // 100)
            group[f"move_past_{horizon}"] = group["mid"] - group["mid"].shift(steps)
            group[f"move_fwd_{horizon}"] = group["mid"].shift(-steps) - group["mid"]
        group["terminal_move"] = float(group["mid"].iloc[-1]) - group["mid"]
        rolling = group["mid"].rolling(101, min_periods=10)
        group["roll10k_min"] = rolling.min()
        group["roll10k_max"] = rolling.max()
        width = group["roll10k_max"] - group["roll10k_min"]
        group["roll10k_pos"] = np.where(width > 0, (group["mid"] - group["roll10k_min"]) / width, 0.5)
        frames.append(group)
    return pd.concat(frames, ignore_index=True)


def _flow_events(trades: pd.DataFrame) -> pd.DataFrame:
    events = trades[trades["symbol"].eq(UNDERLYING)].copy()
    if events.empty:
        return events
    events["buyer"] = events["buyer"].astype(str)
    events["seller"] = events["seller"].astype(str)
    return events.sort_values(["day", "timestamp"]).reset_index(drop=True)


def _rolling_trade_feature(panel: pd.DataFrame, events: pd.DataFrame, actor: str, side: str, window: int, kind: str) -> list[float]:
    out: list[float] = []
    if events.empty:
        return [0.0] * len(panel)
    for (_dataset, day), group in panel.groupby(["dataset", "day"], sort=False):
        day_events = events[events["day"].eq(day)].copy()
        if side == "buy":
            day_events = day_events[day_events["buyer"].eq(actor)]
        else:
            day_events = day_events[day_events["seller"].eq(actor)]
        times = day_events["timestamp"].to_numpy(dtype=int)
        qtys = day_events["quantity"].to_numpy(dtype=float)
        values = []
        for ts in group["timestamp"].to_numpy(dtype=int):
            right = np.searchsorted(times, ts, side="right")
            left = np.searchsorted(times, ts - window, side="right")
            if kind == "cnt":
                values.append(float(max(0, right - left)))
            else:
                values.append(float(qtys[left:right].sum()) if right > left else 0.0)
        out.extend(values)
    return out


def add_flow_features(panel: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    events = _flow_events(trades)
    for mark in KEY_MARKS:
        compact = mark.replace(" ", "").lower()
        for side in ("buy", "sell"):
            for window in FLOW_WINDOWS:
                for kind in ("cnt", "qty"):
                    out[f"{compact}_{side}_{kind}_{window}"] = _rolling_trade_feature(out, events, mark, side, window, kind)
    for window in FLOW_WINDOWS:
        out[f"all_buy_qty_{window}"] = sum(out[f"{mark.replace(' ', '').lower()}_buy_qty_{window}"] for mark in KEY_MARKS)
        out[f"all_sell_qty_{window}"] = sum(out[f"{mark.replace(' ', '').lower()}_sell_qty_{window}"] for mark in KEY_MARKS)
        out[f"all_net_qty_{window}"] = out[f"all_buy_qty_{window}"] - out[f"all_sell_qty_{window}"]
    return out


def build_features(prices: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    return add_flow_features(_velvet_panel(prices), trades)


def feature_screen(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = [
        "move_past_5000",
        "move_past_10000",
        "move_past_30000",
        "trough_rebound",
        "roll10k_pos",
        "imbalance",
        "spread",
        "mark67_buy_cnt_30000",
        "mark67_buy_qty_30000",
        "mark55_sell_qty_30000",
        "mark22_sell_qty_30000",
        "all_net_qty_30000",
    ]
    labels = ["move_fwd_30000", "move_fwd_100000", "terminal_move"]
    base = features[(features["timestamp"] >= 30_000) & (features["open_drop"] >= 20)].copy()
    rows = []
    loo_rows = []
    for feature in candidates:
        if feature not in base:
            continue
        for direction in ("high", "low"):
            for q in (0.10, 0.20, 0.30, 0.70, 0.80, 0.90):
                if direction == "high" and q < 0.5:
                    continue
                if direction == "low" and q > 0.5:
                    continue
                vals = base[feature].dropna()
                if vals.nunique() < 2:
                    continue
                threshold = float(vals.quantile(q))
                mask = base[feature] >= threshold if direction == "high" else base[feature] <= threshold
                support = int(mask.sum())
                if support < 20:
                    continue
                row = {
                    "feature": feature,
                    "direction": direction,
                    "quantile": q,
                    "threshold": threshold,
                    "support": support,
                    "support_frac": float(mask.mean()),
                }
                for label in labels:
                    row[f"{label}_selected_mean"] = float(base.loc[mask, label].mean())
                    row[f"{label}_base_mean"] = float(base[label].mean())
                    row[f"{label}_lift"] = row[f"{label}_selected_mean"] - row[f"{label}_base_mean"]
                rows.append(row)

                day_lifts = []
                day_supports = []
                for test_day in sorted(base["day"].unique()):
                    train = base[base["day"] != test_day]
                    test = base[base["day"] == test_day]
                    if len(train) < 20 or len(test) < 20:
                        continue
                    train_vals = train[feature].dropna()
                    if train_vals.nunique() < 2:
                        continue
                    th = float(train_vals.quantile(q))
                    test_mask = test[feature] >= th if direction == "high" else test[feature] <= th
                    if int(test_mask.sum()) < 5:
                        day_lifts.append(np.nan)
                        day_supports.append(int(test_mask.sum()))
                        continue
                    lift = float(test.loc[test_mask, "terminal_move"].mean() - test["terminal_move"].mean())
                    day_lifts.append(lift)
                    day_supports.append(int(test_mask.sum()))
                clean = [x for x in day_lifts if pd.notna(x)]
                loo_rows.append(
                    {
                        "feature": feature,
                        "direction": direction,
                        "quantile": q,
                        "mean_terminal_lift_loo": float(np.mean(clean)) if clean else np.nan,
                        "min_terminal_lift_loo": float(np.min(clean)) if clean else np.nan,
                        "positive_days": int(sum(x > 0 for x in clean)),
                        "valid_days": int(len(clean)),
                        "min_test_support": int(min(day_supports)) if day_supports else 0,
                    }
                )
    screen = pd.DataFrame(rows)
    loo = pd.DataFrame(loo_rows)
    if not screen.empty:
        screen = screen.sort_values("terminal_move_lift", ascending=False)
    if not loo.empty:
        loo = loo.sort_values(["positive_days", "mean_terminal_lift_loo"], ascending=False)
    return screen, loo


def _windowed_prices_and_features(prices: pd.DataFrame, features: pd.DataFrame, *, step: int, window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_rows = []
    feature_rows = []
    for day, day_prices in prices.groupby("day", sort=True):
        max_ts = int(day_prices["timestamp"].max())
        day_features = features[features["day"].eq(day)]
        for start in range(0, max_ts - window + 1, step):
            end = start + window
            psubset = day_prices[(day_prices["timestamp"] >= start) & (day_prices["timestamp"] < end)].copy()
            fsubset = day_features[(day_features["timestamp"] >= start) & (day_features["timestamp"] < end)].copy()
            if psubset.empty or fsubset.empty:
                continue
            dataset = f"hist_d{int(day)}_s{start}"
            psubset["timestamp"] = psubset["timestamp"].astype(int) - start
            psubset["dataset"] = dataset
            psubset["day"] = int(day)
            fsubset["timestamp"] = fsubset["timestamp"].astype(int) - start
            fsubset["dataset"] = dataset
            fsubset["day"] = int(day)
            # Recompute path features inside the window so rules do not see
            # pre-window state.
            fsubset = fsubset.drop(columns=["open_mid", "open_drop", "peak_mid", "trough_mid", "peak_drawdown", "trough_rebound"], errors="ignore")
            fpath = _velvet_panel(psubset)
            keep_cols = [c for c in fsubset.columns if c not in fpath.columns or c in {"dataset", "day", "timestamp"}]
            fsubset = fpath.merge(fsubset[["dataset", "day", "timestamp", *[c for c in keep_cols if c not in {"dataset", "day", "timestamp"}]]], on=["dataset", "day", "timestamp"], how="left")
            price_rows.append(psubset)
            feature_rows.append(fsubset)
    return pd.concat(price_rows, ignore_index=True), pd.concat(feature_rows, ignore_index=True)


def _rule_active(row: pd.Series, rule: GateRule) -> bool:
    ts = int(row["timestamp"])
    if ts < rule.min_ts:
        return False
    if rule.max_ts is not None and ts > rule.max_ts:
        return False
    drop = float(row["open_drop"] if rule.drop_source == "open" else row["peak_drawdown"])
    if drop < rule.drop_ticks:
        return False
    if rule.rebound_min is not None and float(row["trough_rebound"]) < rule.rebound_min:
        return False
    if rule.rebound_max is not None and float(row["trough_rebound"]) > rule.rebound_max:
        return False
    if rule.roll10k_pos_max is not None and float(row["roll10k_pos"]) > rule.roll10k_pos_max:
        return False
    if rule.past_move_min is not None and float(row["move_past_10000"]) < rule.past_move_min:
        return False
    if rule.past_move_max is not None and float(row["move_past_10000"]) > rule.past_move_max:
        return False
    if rule.imbalance_min is not None and float(row["imbalance"]) < rule.imbalance_min:
        return False
    if rule.imbalance_max is not None and float(row["imbalance"]) > rule.imbalance_max:
        return False
    if rule.spread_max is not None and float(row["spread"]) > rule.spread_max:
        return False
    if rule.mark67_buy_cnt30_min is not None and float(row["mark67_buy_cnt_30000"]) < rule.mark67_buy_cnt30_min:
        return False
    if rule.mark67_buy_qty30_min is not None and float(row["mark67_buy_qty_30000"]) < rule.mark67_buy_qty30_min:
        return False
    if rule.mark55_sell_qty30_min is not None and float(row["mark55_sell_qty_30000"]) < rule.mark55_sell_qty30_min:
        return False
    if rule.mark22_sell_qty30_min is not None and float(row["mark22_sell_qty_30000"]) < rule.mark22_sell_qty30_min:
        return False
    return True


def _rules() -> list[GateRule]:
    return [
        GateRule("ref_open_drop20_30k", "open", 20, 30_000),
        GateRule("ref_open_drop20_50k", "open", 20, 50_000),
        GateRule("open_drop40_50k", "open", 40, 50_000),
        GateRule("open_drop40_rebound5", "open", 40, 50_000, rebound_min=5),
        GateRule("open_drop30_mom10k_pos", "open", 30, 30_000, past_move_min=0),
        GateRule("open_drop30_imb_pos", "open", 30, 30_000, imbalance_min=0.15),
        GateRule("open_drop30_spread6", "open", 30, 30_000, spread_max=6),
        GateRule("open_drop20_m67buy3", "open", 20, 30_000, mark67_buy_cnt30_min=3),
        GateRule("open_drop20_m67buyqty10", "open", 20, 30_000, mark67_buy_qty30_min=10),
        GateRule("open_drop20_m55sellqty10", "open", 20, 30_000, mark55_sell_qty30_min=10),
        GateRule("open_drop20_m22sellqty6", "open", 20, 30_000, mark22_sell_qty30_min=6),
        GateRule("open_drop20_m67buy3_plus80", "open", 20, 30_000, mark67_buy_cnt30_min=3, active_buy_limit=80),
        GateRule("open_drop20_lowrebound4_dur40", "open", 20, 30_000, rebound_max=4, active_duration=40_000),
        GateRule("open_drop30_lowrebound4_dur40", "open", 30, 30_000, rebound_max=4, active_duration=40_000),
        GateRule("open_drop20_lowroll20_dur40", "open", 20, 30_000, roll10k_pos_max=0.20, active_duration=40_000),
        GateRule("peak_dd40_rebound5", "peak", 40, 50_000, rebound_min=5),
        GateRule("peak_dd40_rebound5_mompos", "peak", 40, 50_000, rebound_min=5, past_move_min=0),
        GateRule("peak_dd40_rebound5_m67buy3", "peak", 40, 50_000, rebound_min=5, mark67_buy_cnt30_min=3),
    ]


def build_feature_lookup(features: pd.DataFrame) -> dict[tuple[str, int, int], dict]:
    return {
        (str(row.dataset), int(row.day), int(row.timestamp)): row._asdict()
        for row in features.itertuples(index=False)
    }


def simulate(
    prices: pd.DataFrame,
    features: pd.DataFrame,
    rule: GateRule | None,
    feature_lookup: dict[tuple[str, int, int], dict] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    variant = "sell7_base" if rule is None else rule.label
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []
    if feature_lookup is None:
        feature_lookup = build_feature_lookup(features)
    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        position = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        costs = {product: PositionCost() for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak_pnl = -float("inf")
        active_until = -1
        gate_ever = False
        for timestamp, group in day_prices.sort_values(["timestamp", "product"]).groupby("timestamp", sort=True):
            timestamp = int(timestamp)
            group_rows = {str(row.product): row._asdict() for row in group.itertuples(index=False)}
            for product, row in group_rows.items():
                if pd.notna(row["mid_price"]):
                    last_mid[product] = float(row["mid_price"])
            active = timestamp <= active_until
            if rule is not None:
                frow = feature_lookup.get((str(dataset), int(day), timestamp))
                if frow is not None and _rule_active(pd.Series(frow), rule):
                    gate_ever = True
                    if rule.active_duration is None:
                        active_until = 10**9
                    else:
                        active_until = max(active_until, timestamp + rule.active_duration)
                    active = True
            for product in SELL7_SCHEDULES:
                row = group_rows.get(product)
                if row is None:
                    continue
                if product == UNDERLYING and rule is not None and active:
                    scfg = {
                        "limit": 200,
                        "max_order": 40,
                        "buy": rule.buy,
                        "sell": rule.sell,
                        "buy_limit": rule.active_buy_limit,
                        "sell_limit": rule.active_sell_limit,
                    }
                else:
                    scfg = _schedule_for(product, timestamp, SELL7_SCHEDULES)
                    if scfg is not None:
                        scfg = dict(scfg)
                        scfg["buy_limit"] = scfg["limit"]
                        scfg["sell_limit"] = scfg["limit"]
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
                            _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="flatten", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)
                    elif position[product] < 0 and pd.notna(ask):
                        qty = min(int(scfg["max_order"]), ask_volume, -position[product])
                        if qty > 0:
                            _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="buy", reason="flatten", price=float(ask), qty=qty, position=position, cash=cash, costs=costs)
                    continue
                if pd.notna(ask) and float(ask) <= int(scfg["buy"]) and position[product] < int(scfg["buy_limit"]):
                    qty = min(int(scfg["max_order"]), ask_volume, int(scfg["buy_limit"]) - position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="buy", reason="schedule", price=float(ask), qty=qty, position=position, cash=cash, costs=costs)
                if pd.notna(bid) and float(bid) >= int(scfg["sell"]) and position[product] > -int(scfg["sell_limit"]):
                    qty = min(int(scfg["max_order"]), bid_volume, int(scfg["sell_limit"]) + position[product])
                    if qty > 0:
                        _record_trade(trade_rows, variant=variant, dataset=str(dataset), day=int(day), timestamp=timestamp, product=product, side="sell", reason="schedule", price=float(bid), qty=qty, position=position, cash=cash, costs=costs)
            product_pnls = {product: cash[product] + position[product] * last_mid.get(product, 0.0) for product in PRODUCTS}
            total = float(sum(product_pnls.values()))
            peak_pnl = max(peak_pnl, total)
            pnl_rows.append(
                {
                    "variant": variant,
                    "dataset": dataset,
                    "day": int(day),
                    "timestamp": timestamp,
                    "gate_ever_active": bool(gate_ever),
                    "gate_active": bool(active),
                    "total_pnl": total,
                    "drawdown": total - peak_pnl,
                    "velvet_pnl": product_pnls[UNDERLYING],
                    "velvet_pos": position[UNDERLYING],
                }
            )
    return pd.DataFrame(trade_rows), pd.DataFrame(pnl_rows)


def summarize(pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "total_pnl": float(last["total_pnl"]),
                "velvet_pnl": float(last["velvet_pnl"]),
                "velvet_pos": int(last["velvet_pos"]),
                "max_drawdown": float(group["drawdown"].min()),
                "gate_ever_active": bool(group["gate_ever_active"].any()),
            }
        )
    return pd.DataFrame(rows)


def summarize_windows(summary: pd.DataFrame) -> pd.DataFrame:
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
                "all_mean_delta": float(group["delta_total"].mean()),
                "all_hit_rate": float((group["delta_total"] > 0).mean()),
                "active_mean_delta": float(eval_group["delta_total"].mean()),
                "active_hit_rate": float((eval_group["delta_total"] > 0).mean()),
                "active_median_delta": float(eval_group["delta_total"].median()),
                "active_p10_delta": float(eval_group["delta_total"].quantile(0.10)),
                "active_min_delta": float(eval_group["delta_total"].min()),
                "active_max_delta": float(eval_group["delta_total"].max()),
            }
        )
    return pd.DataFrame(rows).sort_values(["all_mean_delta", "active_mean_delta"], ascending=False)


def write_report(
    doc: Path,
    out_dir: Path,
    screen: pd.DataFrame,
    loo: pd.DataFrame,
    full_summary: pd.DataFrame,
    window_summary: pd.DataFrame,
    official_summary: pd.DataFrame,
    step: int,
) -> None:
    hist = full_summary[full_summary["dataset"].eq("historical")].copy()
    hist_agg = hist.groupby("variant", sort=False).agg(
        mean_total=("total_pnl", "mean"),
        min_total=("total_pnl", "min"),
        active_days=("gate_ever_active", "sum"),
        mean_velvet=("velvet_pnl", "mean"),
    ).reset_index()
    base = float(hist_agg.loc[hist_agg["variant"].eq("sell7_base"), "mean_total"].iloc[0])
    hist_agg["delta_vs_base"] = hist_agg["mean_total"] - base
    official = official_summary.copy()
    official["delta_vs_base"] = official["total_pnl"] - float(official.loc[official["variant"].eq("sell7_base"), "total_pnl"].iloc[0])
    text = f"""# VELVET Regime Classifier Research

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.research_velvet_regime_classifier
```

Artifacts live under `{out_dir}`.

## Purpose

This researches the next likely VELVET alpha path: not another static
open-drawdown threshold, but path-shape + liquidity + counterparty-flow filters
for deciding whether a drawdown is reboundable.

## Feature Screen

Rows are historical VELVET states with `open_drop >= 20` after `30k`. The screen
looks for transparent single-feature conditions that improve forward/terminal
outcomes.

Top in-sample feature lifts:

{markdown_table(screen.head(20), max_rows=20)}

Leave-one-day terminal-move screen:

{markdown_table(loo.head(30), max_rows=30)}

## Full-Day Strategy Simulation

{markdown_table(hist_agg.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Sliding 100k Windows

Public windows are stepped by `{step:,}` ticks.

{markdown_table(window_summary, max_rows=80)}

## Official 100k Calibration

{markdown_table(official.sort_values("delta_vs_base", ascending=False), max_rows=80)}

## Read

Promote only if a classifier beats the simple one-shot/delayed references on
historical full days and sliding windows, and if counterparty/liquidity filters
show leave-one-day stability. Otherwise the apparent feature is path luck.
"""
    doc.write_text(text)


def run(data_dir: Path, official_log: Path, out_dir: Path, doc: Path, step: int, window: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    historical_prices = load_historical(data_dir)
    historical_trades = load_historical_trades(data_dir)
    historical_features = build_features(historical_prices, historical_trades)
    screen, loo = feature_screen(historical_features)

    full_trades = []
    full_pnls = []
    for rule in [None, *_rules()]:
        print(f"full simulate {'sell7_base' if rule is None else rule.label}", flush=True)
        trades, pnl = simulate(historical_prices, historical_features, rule)
        full_trades.append(trades)
        full_pnls.append(pnl)
    full_pnl = pd.concat(full_pnls, ignore_index=True)
    full_summary = summarize(full_pnl)

    window_prices, window_features = _windowed_prices_and_features(historical_prices, historical_features, step=step, window=window)
    window_summaries = []
    for rule in [None, *_rules()]:
        print(f"window simulate {'sell7_base' if rule is None else rule.label}", flush=True)
        _, pnl = simulate(window_prices, window_features, rule)
        window_summaries.append(summarize(pnl))
    window_detail = pd.concat(window_summaries, ignore_index=True)
    window_summary = summarize_windows(window_detail)

    official_prices, official_trades = load_official(official_log)
    official_features = build_features(official_prices, official_trades)
    official_summaries = []
    for rule in [None, *_rules()]:
        print(f"official simulate {'sell7_base' if rule is None else rule.label}", flush=True)
        _, pnl = simulate(official_prices, official_features, rule)
        official_summaries.append(summarize(pnl))
    official_summary = pd.concat(official_summaries, ignore_index=True)

    screen.to_csv(out_dir / "feature_screen.csv", index=False)
    loo.to_csv(out_dir / "feature_screen_loo.csv", index=False)
    full_summary.to_csv(out_dir / "classifier_full_summary.csv", index=False)
    window_detail.to_csv(out_dir / "classifier_window_detail.csv", index=False)
    window_summary.to_csv(out_dir / "classifier_window_summary.csv", index=False)
    official_summary.to_csv(out_dir / "classifier_official_summary.csv", index=False)
    write_report(doc, out_dir, screen, loo, full_summary, window_summary, official_summary, step)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(window_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-log", type=Path, default=DEFAULT_OFFICIAL_LOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--step", type=int, default=100_000)
    parser.add_argument("--window", type=int, default=100_000)
    args = parser.parse_args()
    run(args.data_dir, args.official_log, args.out_dir, args.doc, args.step, args.window)


if __name__ == "__main__":
    main()
