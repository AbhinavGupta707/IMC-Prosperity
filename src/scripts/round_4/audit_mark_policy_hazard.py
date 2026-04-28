"""Reverse-engineer simple Mark bot policies with transparent hazard rules.

This script asks whether Mark behavior is predictable *before* it happens.
It is deliberately not a black-box ML model. With only three historical days,
the right first test is a transparent leave-one-day rule search:

    Given current book state + recent Mark history, can a simple condition
    identify a higher probability of a target Mark event in the next horizon?

Targets are the role-based behaviors found in the classification audit:

- Mark55 VELVET taker buy/sell flow;
- Mark38 HYDROGEL taker buy/sell flow;
- Mark38 VEV_4000 taker buy/sell flow;
- Mark22 OTM voucher basket sells.

The output ranks candidate "exploits" by out-of-sample hazard lift and coverage.
It does not itself place trades.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.scripts.round_4.audit_mark_behavior_classification import (
    PRODUCTS,
    _actor_rows,
    _attach_book,
    _book_features,
    _load_historical,
    _schedule_for,
)


DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OUT_DIR = Path("outputs/round_4/mark_policy")
HORIZONS = (1_000, 5_000, 10_000)
WINDOWS = (1_000, 5_000, 10_000, 30_000)
QUANTILES = (0.05, 0.10, 0.20, 0.80, 0.90, 0.95)
MIN_TRAIN_SUPPORT = 80
MIN_TRAIN_POSITIVES = 5
MIN_TEST_SUPPORT = 20


@dataclass(frozen=True)
class TargetSpec:
    label: str
    panel_product: str
    target_type: str  # actor or basket
    mark: str | None = None
    product: str | None = None
    side: str | None = None
    role: str | None = "taker"


TARGETS = (
    TargetSpec("m55_velvet_buy_taker", "VELVETFRUIT_EXTRACT", "actor", "Mark 55", "VELVETFRUIT_EXTRACT", "buy", "taker"),
    TargetSpec("m55_velvet_sell_taker", "VELVETFRUIT_EXTRACT", "actor", "Mark 55", "VELVETFRUIT_EXTRACT", "sell", "taker"),
    TargetSpec("m38_hyd_buy_taker", "HYDROGEL_PACK", "actor", "Mark 38", "HYDROGEL_PACK", "buy", "taker"),
    TargetSpec("m38_hyd_sell_taker", "HYDROGEL_PACK", "actor", "Mark 38", "HYDROGEL_PACK", "sell", "taker"),
    TargetSpec("m38_vev4000_buy_taker", "VEV_4000", "actor", "Mark 38", "VEV_4000", "buy", "taker"),
    TargetSpec("m38_vev4000_sell_taker", "VEV_4000", "actor", "Mark 38", "VEV_4000", "sell", "taker"),
    TargetSpec("m22_otm_basket_sell", "VEV_5400", "basket"),
)


BASE_FEATURES = (
    "timestamp_frac",
    "spread",
    "imbalance",
    "bid_vol",
    "ask_vol",
    "roll10k_pos",
    "mid_move_past_1000",
    "mid_move_past_5000",
    "mid_move_past_10000",
    "schedule_buy_active",
    "schedule_sell_active",
)


def _build_actor_events(actors: pd.DataFrame, mark: str, product: str, side: str, role: str | None) -> pd.DataFrame:
    mask = (
        (actors["mark"] == mark)
        & (actors["product"] == product)
        & (actors["side"] == side)
    )
    if role is not None:
        mask &= actors["role"] == role
    events = actors.loc[mask, ["day", "timestamp", "quantity"]].copy()
    events.sort_values(["day", "timestamp"], inplace=True)
    return events


def _build_otm_basket_events(trades: pd.DataFrame) -> pd.DataFrame:
    otm = {"VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500"}
    rows = []
    clean = trades[trades["symbol"].isin(otm)].copy()
    for (day, ts, buyer, seller), group in clean.groupby(["day", "timestamp", "buyer", "seller"], sort=False):
        products = set(group["symbol"])
        if seller == "Mark 22" and len(products) >= 4:
            rows.append(
                {
                    "day": int(day),
                    "timestamp": int(ts),
                    "quantity": int(group["quantity"].sum()),
                    "product_count": int(len(products)),
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["day", "timestamp"], inplace=True)
    return out


def _target_events(spec: TargetSpec, actors: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    if spec.target_type == "basket":
        return _build_otm_basket_events(trades)
    assert spec.mark is not None and spec.product is not None and spec.side is not None
    return _build_actor_events(actors, spec.mark, spec.product, spec.side, spec.role)


def _book_panel(book: pd.DataFrame, product: str) -> pd.DataFrame:
    panel = book[book["product"] == product].copy()
    panel.sort_values(["day", "timestamp"], inplace=True)
    panel["timestamp_frac"] = panel["timestamp"] / 1_000_000.0
    buy_active = []
    sell_active = []
    for row in panel.itertuples(index=False):
        sched = _schedule_for(str(row.product), int(row.timestamp))
        if sched is None:
            buy_active.append(0)
            sell_active.append(0)
            continue
        buy, sell = sched
        buy_active.append(int(pd.notna(row.ask) and row.ask <= buy))
        sell_active.append(int(pd.notna(row.bid) and row.bid >= sell))
    panel["schedule_buy_active"] = buy_active
    panel["schedule_sell_active"] = sell_active
    return panel


def _events_by_day(events: pd.DataFrame) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    if events.empty:
        return out
    for day, group in events.groupby("day"):
        out[int(day)] = (
            group["timestamp"].to_numpy(dtype=int),
            group["quantity"].to_numpy(dtype=float),
        )
    return out


def _future_count_qty(times: np.ndarray, qtys: np.ndarray, ts: int, horizon: int) -> tuple[int, float]:
    if len(times) == 0:
        return 0, 0.0
    left = np.searchsorted(times, ts, side="right")
    right = np.searchsorted(times, ts + horizon, side="right")
    if right <= left:
        return 0, 0.0
    return int(right - left), float(qtys[left:right].sum())


def _recent_count_qty_since(times: np.ndarray, qtys: np.ndarray, ts: int, window: int) -> tuple[int, float, float]:
    if len(times) == 0:
        return 0, 0.0, np.nan
    right = np.searchsorted(times, ts, side="right")
    left = np.searchsorted(times, ts - window, side="right")
    count = max(0, right - left)
    qty = float(qtys[left:right].sum()) if count else 0.0
    since = float(ts - times[right - 1]) if right > 0 else np.nan
    return int(count), qty, since


def _add_event_history(panel: pd.DataFrame, events: pd.DataFrame, prefix: str) -> pd.DataFrame:
    by_day = _events_by_day(events)
    new_cols: dict[str, list[float | int]] = {}
    for window in WINDOWS:
        new_cols[f"{prefix}_cnt_{window}"] = []
        new_cols[f"{prefix}_qty_{window}"] = []
    new_cols[f"{prefix}_since"] = []

    for row in panel.itertuples(index=False):
        times, qtys = by_day.get(int(row.day), (np.array([], dtype=int), np.array([], dtype=float)))
        since_value = np.nan
        for window in WINDOWS:
            count, qty, since = _recent_count_qty_since(times, qtys, int(row.timestamp), window)
            new_cols[f"{prefix}_cnt_{window}"].append(count)
            new_cols[f"{prefix}_qty_{window}"].append(qty)
            since_value = since
        new_cols[f"{prefix}_since"].append(since_value)
    return pd.concat([panel, pd.DataFrame(new_cols, index=panel.index)], axis=1)


def _add_target_labels(panel: pd.DataFrame, target_events: pd.DataFrame, label: str) -> pd.DataFrame:
    by_day = _events_by_day(target_events)
    new_cols: dict[str, list[float | int]] = {}
    for horizon in HORIZONS:
        new_cols[f"{label}_event_{horizon}"] = []
        new_cols[f"{label}_qty_{horizon}"] = []
    for row in panel.itertuples(index=False):
        times, qtys = by_day.get(int(row.day), (np.array([], dtype=int), np.array([], dtype=float)))
        for horizon in HORIZONS:
            count, qty = _future_count_qty(times, qtys, int(row.timestamp), horizon)
            new_cols[f"{label}_event_{horizon}"].append(int(count > 0))
            new_cols[f"{label}_qty_{horizon}"].append(qty)
    return pd.concat([panel, pd.DataFrame(new_cols, index=panel.index)], axis=1)


def _same_product_actor_cells(actors: pd.DataFrame, product: str, min_rows: int = 1) -> list[tuple[str, pd.DataFrame]]:
    cells: list[tuple[str, pd.DataFrame]] = []
    subset = actors[(actors["product"] == product) & (actors["role"] == "taker")]
    for (mark, side), group in subset.groupby(["mark", "side"], sort=False):
        if len(group) < min_rows:
            continue
        label = f"{mark.replace(' ', '').lower()}_{product.lower()}_{side}_taker"
        events = group[["day", "timestamp", "quantity"]].copy()
        events.sort_values(["day", "timestamp"], inplace=True)
        cells.append((label, events))
    return cells


def _build_panel_for_target(
    spec: TargetSpec,
    book: pd.DataFrame,
    actors: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    panel = _book_panel(book, spec.panel_product)
    target = _target_events(spec, actors, trades)
    panel = _add_target_labels(panel, target, spec.label)

    # Add histories for all same-product taker actors with enough data.
    for label, events in _same_product_actor_cells(actors, spec.panel_product):
        panel = _add_event_history(panel, events, label)

    # Add the target itself and key cross-product program state.
    if spec.target_type == "basket":
        panel = _add_event_history(panel, target, "m22_otm_basket")
    else:
        panel = _add_event_history(panel, target, f"{spec.label}_self")
    basket = _build_otm_basket_events(trades)
    if not basket.empty and spec.label != "m22_otm_basket_sell":
        panel = _add_event_history(panel, basket, "m22_otm_basket")
    return panel


def _candidate_feature_columns(panel: pd.DataFrame, target_label: str) -> list[str]:
    excluded_fragments = (f"{target_label}_event_", f"{target_label}_qty_")
    cols = []
    for col in panel.columns:
        if col in {"day", "timestamp", "product", "profit_and_loss", "currency"}:
            continue
        if "future" in col:
            continue
        if any(fragment in col for fragment in excluded_fragments):
            continue
        if not pd.api.types.is_numeric_dtype(panel[col]):
            continue
        values = panel[col].dropna()
        if len(values) < 100 or values.nunique() < 2:
            continue
        cols.append(col)
    return cols


def _rule_mask(values: pd.Series, direction: str, threshold: float) -> pd.Series:
    if direction == "high":
        return values >= threshold
    return values <= threshold


def _evaluate_rule(frame: pd.DataFrame, event_col: str, qty_col: str, feature: str, direction: str, threshold: float) -> dict[str, float | int]:
    valid = frame[pd.notna(frame[feature])]
    if valid.empty:
        return {
            "support": 0,
            "positives": 0,
            "event_rate": np.nan,
            "base_rate": np.nan,
            "lift": np.nan,
            "qty_coverage": np.nan,
            "mean_future_qty": np.nan,
        }
    mask = _rule_mask(valid[feature], direction, threshold)
    selected = valid[mask]
    positives = int(selected[event_col].sum()) if len(selected) else 0
    total_qty = float(valid[qty_col].sum())
    selected_qty = float(selected[qty_col].sum()) if len(selected) else 0.0
    base_rate = float(valid[event_col].mean())
    event_rate = float(selected[event_col].mean()) if len(selected) else np.nan
    return {
        "support": int(len(selected)),
        "positives": positives,
        "event_rate": event_rate,
        "base_rate": base_rate,
        "lift": event_rate / base_rate if base_rate > 0 and pd.notna(event_rate) else np.nan,
        "qty_coverage": selected_qty / total_qty if total_qty > 0 else np.nan,
        "mean_future_qty": float(selected[qty_col].mean()) if len(selected) else np.nan,
    }


def _train_rules(panel: pd.DataFrame, target_label: str, horizon: int, train_days: set[int]) -> pd.DataFrame:
    event_col = f"{target_label}_event_{horizon}"
    qty_col = f"{target_label}_qty_{horizon}"
    train = panel[panel["day"].isin(train_days)]
    rows = []
    for feature in _candidate_feature_columns(panel, target_label):
        values = train[feature].dropna()
        if values.nunique() < 2:
            continue
        for q in QUANTILES:
            threshold = float(values.quantile(q))
            direction = "low" if q < 0.5 else "high"
            metrics = _evaluate_rule(train, event_col, qty_col, feature, direction, threshold)
            if metrics["support"] < MIN_TRAIN_SUPPORT or metrics["positives"] < MIN_TRAIN_POSITIVES:
                continue
            rows.append(
                {
                    "feature": feature,
                    "direction": direction,
                    "quantile": q,
                    "threshold": threshold,
                    **metrics,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["score"] = (
        (out["event_rate"] - out["base_rate"])
        * np.log1p(out["support"])
        * np.sqrt(out["qty_coverage"].clip(lower=0.0).fillna(0.0))
    )
    out.sort_values(["score", "lift", "support"], ascending=[False, False, False], inplace=True)
    return out


def _leave_one_day_rules(panel: pd.DataFrame, target_label: str) -> pd.DataFrame:
    days = sorted(int(day) for day in panel["day"].dropna().unique())
    records = []
    for horizon in HORIZONS:
        event_col = f"{target_label}_event_{horizon}"
        qty_col = f"{target_label}_qty_{horizon}"
        if panel[event_col].sum() == 0:
            continue
        for holdout in days:
            train_days = set(days) - {holdout}
            train_rules = _train_rules(panel, target_label, horizon, train_days)
            if train_rules.empty:
                continue
            # Keep a diverse top set so one feature does not monopolize the output.
            top = train_rules.groupby("feature", sort=False).head(2).head(25)
            test = panel[panel["day"] == holdout]
            for rank, rule in enumerate(top.itertuples(index=False), start=1):
                test_metrics = _evaluate_rule(
                    test,
                    event_col,
                    qty_col,
                    str(rule.feature),
                    str(rule.direction),
                    float(rule.threshold),
                )
                if test_metrics["support"] < MIN_TEST_SUPPORT:
                    continue
                records.append(
                    {
                        "target": target_label,
                        "horizon": horizon,
                        "holdout_day": holdout,
                        "train_rank": rank,
                        "feature": str(rule.feature),
                        "direction": str(rule.direction),
                        "quantile": float(rule.quantile),
                        "threshold": float(rule.threshold),
                        "train_support": int(rule.support),
                        "train_positives": int(rule.positives),
                        "train_event_rate": float(rule.event_rate),
                        "train_base_rate": float(rule.base_rate),
                        "train_lift": float(rule.lift),
                        "train_qty_coverage": float(rule.qty_coverage),
                        "test_support": int(test_metrics["support"]),
                        "test_positives": int(test_metrics["positives"]),
                        "test_event_rate": float(test_metrics["event_rate"]),
                        "test_base_rate": float(test_metrics["base_rate"]),
                        "test_lift": float(test_metrics["lift"]),
                        "test_qty_coverage": float(test_metrics["qty_coverage"]),
                        "test_mean_future_qty": float(test_metrics["mean_future_qty"]),
                    }
                )
    out = pd.DataFrame(records)
    if not out.empty:
        out.sort_values(["target", "horizon", "holdout_day", "train_rank"], inplace=True)
    return out


def _aggregate_loo(loo: pd.DataFrame) -> pd.DataFrame:
    if loo.empty:
        return loo
    group_cols = ["target", "horizon", "feature", "direction", "quantile"]
    rows = []
    for keys, group in loo.groupby(group_cols, sort=False):
        if group["holdout_day"].nunique() < 3:
            continue
        rows.append(
            {
                "target": keys[0],
                "horizon": keys[1],
                "feature": keys[2],
                "direction": keys[3],
                "quantile": keys[4],
                "holdouts": int(group["holdout_day"].nunique()),
                "mean_train_lift": float(group["train_lift"].mean()),
                "mean_test_lift": float(group["test_lift"].mean()),
                "min_test_lift": float(group["test_lift"].min()),
                "positive_lift_holdouts": int((group["test_lift"] > 1.0).sum()),
                "mean_test_event_rate": float(group["test_event_rate"].mean()),
                "mean_test_base_rate": float(group["test_base_rate"].mean()),
                "mean_test_support": float(group["test_support"].mean()),
                "mean_test_qty_coverage": float(group["test_qty_coverage"].mean()),
                "min_test_qty_coverage": float(group["test_qty_coverage"].min()),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(
            ["positive_lift_holdouts", "mean_test_lift", "min_test_lift", "mean_test_qty_coverage"],
            ascending=[False, False, False, False],
            inplace=True,
        )
    return out


def _write_target_base_rates(panel: pd.DataFrame, target_label: str) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        event_col = f"{target_label}_event_{horizon}"
        qty_col = f"{target_label}_qty_{horizon}"
        for day, group in panel.groupby("day"):
            rows.append(
                {
                    "target": target_label,
                    "horizon": horizon,
                    "day": int(day),
                    "rows": int(len(group)),
                    "event_rows": int(group[event_col].sum()),
                    "event_rate": float(group[event_col].mean()),
                    "future_qty_sum": float(group[qty_col].sum()),
                    "mean_future_qty": float(group[qty_col].mean()),
                }
            )
    return pd.DataFrame(rows)


def _print_table(title: str, frame: pd.DataFrame, cols: list[str], n: int = 30) -> None:
    print(f"\n=== {title} ===")
    if frame.empty:
        print("(none)")
        return
    print(frame.loc[:, cols].head(n).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    prices, trades = _load_historical(args.data_dir)
    book = _book_features(prices)
    actors = _actor_rows(_attach_book(trades, book))

    all_base_rates = []
    all_loo = []
    all_agg = []
    for spec in TARGETS:
        print(f"building target {spec.label}", flush=True)
        panel = _build_panel_for_target(spec, book, actors, trades)
        base_rates = _write_target_base_rates(panel, spec.label)
        loo = _leave_one_day_rules(panel, spec.label)
        agg = _aggregate_loo(loo)
        panel.to_csv(args.out_dir / f"{spec.label}_panel.csv", index=False)
        base_rates.to_csv(args.out_dir / f"{spec.label}_base_rates.csv", index=False)
        loo.to_csv(args.out_dir / f"{spec.label}_loo_rules.csv", index=False)
        agg.to_csv(args.out_dir / f"{spec.label}_rule_summary.csv", index=False)
        all_base_rates.append(base_rates)
        all_loo.append(loo)
        all_agg.append(agg)

    base_out = pd.concat(all_base_rates, ignore_index=True) if all_base_rates else pd.DataFrame()
    loo_out = pd.concat(all_loo, ignore_index=True) if all_loo else pd.DataFrame()
    agg_out = pd.concat(all_agg, ignore_index=True) if all_agg else pd.DataFrame()
    base_out.to_csv(args.out_dir / "all_base_rates.csv", index=False)
    loo_out.to_csv(args.out_dir / "all_loo_rules.csv", index=False)
    agg_out.to_csv(args.out_dir / "all_rule_summary.csv", index=False)

    strong = agg_out[
        (agg_out["positive_lift_holdouts"] == 3)
        & (agg_out["mean_test_lift"] > 1.25)
        & (agg_out["mean_test_qty_coverage"] > 0.05)
    ].copy() if not agg_out.empty else pd.DataFrame()
    _print_table(
        "Strong leave-one-day hazard rules",
        strong,
        [
            "target",
            "horizon",
            "feature",
            "direction",
            "quantile",
            "mean_test_lift",
            "min_test_lift",
            "mean_test_event_rate",
            "mean_test_base_rate",
            "mean_test_qty_coverage",
        ],
    )
    _print_table(
        "Base event rates",
        base_out,
        ["target", "horizon", "day", "rows", "event_rows", "event_rate", "future_qty_sum"],
        n=50,
    )
    print(f"\noutput_dir={args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
