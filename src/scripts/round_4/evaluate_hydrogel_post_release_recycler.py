"""Research post-release HYDROGEL recycling after the high-regime release.

The high-regime wrapper fixes the first-order R4 official issue: do not short
HYDROGEL too early when the first 20k-30k ticks prove high.  This script asks a
second-order question:

    After releasing the high-regime overlay near 60k, is there causal value in
    covering part of the resulting short and re-shorting later?

The script has two layers:

* full replay wrappers around the current abortgate-long40 candidate;
* price-only rolling-window stress for many historical high-trigger windows.

The rolling layer deliberately reports both raw score impact and
terminal-equalized impact.  A policy that only helps by changing final exposure
is not a clean realized recycler.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.simulator import BacktestSimulator
from src.datamodel import Order
from src.scripts.round_4.evaluate_hydrogel_probe_submissions import (
    DATA_DIR,
    LIMIT,
    OFFICIAL_LOG,
    PRODUCT,
    REPO_ROOT,
    SubmissionHydAdapter,
    historical_replay,
    load_trader,
    max_drawdown,
    official_log_replay,
)


if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

BASE_ABORTGATE = (
    REPO_ROOT
    / "outputs"
    / "submissions"
    / "r4"
    / "submission_r4_final_sell7_hyd_abortgate15_long40_60.py"
)
OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_post_release_recycler"
DOC_PATH = REPO_ROOT / "docs" / "round_4" / "HYDROGEL_POST_RELEASE_RECYCLER_RESEARCH.md"

WINDOW = 99_900
STEP = 10_000
TRIGGER_START = 20_000
TRIGGER_END = 30_000
TRIGGER_MID = 10_020.0
SLOPE_GATE_TS = 40_000
SLOPE_THRESHOLD = 15.0
RELEASE_TS = 60_000


@dataclass(frozen=True)
class RecyclerConfig:
    name: str
    mode: str
    qty: int = 0
    cover_drop: float = 0.0
    turn_up: float = 0.0
    profit_ticks: float = 0.0
    latest_open_ts: int = 90_000
    max_cycles: int = 1
    force_reclose: bool = False


def recycler_configs() -> list[RecyclerConfig]:
    configs = [RecyclerConfig("abortgate_long40_base", "base")]

    # Blunt de-risk controls.  These are expected to be dangerous because they
    # alter final short exposure if HYD keeps falling.
    for qty in (20, 40, 80):
        for cover_drop in (12.0, 20.0, 28.0):
            configs.append(
                RecyclerConfig(
                    name=f"cover_drop{int(cover_drop)}_qty{qty}_no_force",
                    mode="drop_cover",
                    qty=qty,
                    cover_drop=cover_drop,
                    max_cycles=1,
                    force_reclose=False,
                )
            )

    # Plausible recycler: only cover after a real drop and a local turn, then
    # re-short only if the rebound pays the spread plus a profit threshold.
    for qty in (20, 40):
        for cover_drop in (16.0, 24.0, 32.0):
            for turn_up in (4.0, 8.0):
                for profit_ticks in (6.0, 10.0):
                    configs.append(
                        RecyclerConfig(
                            name=(
                                f"turn_cover_drop{int(cover_drop)}_turn{int(turn_up)}"
                                f"_profit{int(profit_ticks)}_qty{qty}"
                            ),
                            mode="turn_recycle",
                            qty=qty,
                            cover_drop=cover_drop,
                            turn_up=turn_up,
                            profit_ticks=profit_ticks,
                            max_cycles=1,
                            force_reclose=False,
                        )
                    )

    # Terminal-equalized controls: useful diagnostically, not recommended unless
    # they still look good after crossing the terminal spread.
    for cover_drop in (16.0, 24.0, 32.0):
        configs.append(
            RecyclerConfig(
                name=f"turn_cover_drop{int(cover_drop)}_turn8_profit10_qty40_force",
                mode="turn_recycle",
                qty=40,
                cover_drop=cover_drop,
                turn_up=8.0,
                profit_ticks=10.0,
                max_cycles=1,
                force_reclose=True,
            )
        )
    return configs


def replay_cases():
    return [
        ("official100k_log_replay", official_log_replay(OFFICIAL_LOG)),
        ("hist_day_1_first100k", historical_replay(1, end_ts=99_900)),
        ("hist_day_2_first100k", historical_replay(2, end_ts=99_900)),
        ("hist_day_3_first100k", historical_replay(3, end_ts=99_900)),
        ("hist_day_1_1m", historical_replay(1)),
        ("hist_day_2_1m", historical_replay(2)),
        ("hist_day_3_1m", historical_replay(3)),
        ("hist_all_1m", historical_replay(None)),
    ]


def full_replay_configs() -> list[RecyclerConfig]:
    """Small representative set for expensive simulator runs.

    The larger parameter grid belongs in the price-only rolling stress.  Full
    replay is only for checking whether implementation-like wrappers behave as
    expected on the main paths.
    """
    names = {
        "abortgate_long40_base",
        "cover_drop12_qty40_no_force",
        "cover_drop20_qty40_no_force",
        "cover_drop28_qty40_no_force",
        "turn_cover_drop16_turn8_profit10_qty40",
        "turn_cover_drop24_turn8_profit10_qty40",
        "turn_cover_drop32_turn8_profit10_qty40",
        "turn_cover_drop24_turn8_profit10_qty40_force",
    }
    return [config for config in recycler_configs() if config.name in names]


def build_trader_cls(base_cls: type, config: RecyclerConfig) -> type:
    if config.mode == "base":
        return base_cls

    class Trader:
        def __init__(self) -> None:
            self._inner = base_cls()
            self._high_regime = False
            self._trigger_mid_20k: float | None = None
            self._slope_passed = False
            self._released = False
            self._release_peak_mid: float | None = None
            self._post_release_low_mid: float | None = None
            self._covered_qty = 0
            self._cover_price: float | None = None
            self._cycles = 0
            self._events: list[str] = []

        def run(self, state):
            orders, conversions, trader_data = self._inner.run(state)
            self._observe_regime(state)
            if self._high_regime and self._slope_passed and state.timestamp >= RELEASE_TS:
                self._released = True
                orders = self._post_release_orders(state, orders)
            return orders, conversions, trader_data

        @property
        def event_state(self) -> dict[str, object]:
            return {
                "high_regime": self._high_regime,
                "slope_passed": self._slope_passed,
                "released": self._released,
                "covered_qty": self._covered_qty,
                "cover_price": self._cover_price,
                "cycles": self._cycles,
                "events": "|".join(self._events[:12]),
            }

        def _observe_regime(self, state) -> None:
            mid = _mid(state)
            if mid is None:
                return
            if state.timestamp == TRIGGER_START:
                self._trigger_mid_20k = mid
            if (
                not self._high_regime
                and TRIGGER_START <= state.timestamp <= TRIGGER_END
                and mid >= TRIGGER_MID
            ):
                self._high_regime = True
                if self._trigger_mid_20k is None:
                    self._trigger_mid_20k = mid
            if self._high_regime and state.timestamp >= SLOPE_GATE_TS and not self._slope_passed:
                start_mid = self._trigger_mid_20k
                if start_mid is not None and mid - start_mid >= SLOPE_THRESHOLD:
                    self._slope_passed = True

        def _post_release_orders(self, state, orders):
            mid = _mid(state)
            bid = _best_bid(state)
            ask = _best_ask(state)
            if mid is None or bid is None or ask is None:
                return orders

            self._release_peak_mid = mid if self._release_peak_mid is None else max(self._release_peak_mid, mid)
            self._post_release_low_mid = (
                mid if self._post_release_low_mid is None else min(self._post_release_low_mid, mid)
            )

            pos = int(state.position.get(PRODUCT, 0))
            rel_ts = int(state.timestamp)
            if (
                self._covered_qty <= 0
                and self._cycles < config.max_cycles
                and rel_ts <= config.latest_open_ts
                and pos <= -LIMIT + max(0, config.qty)
            ):
                if self._should_cover(mid):
                    qty = min(config.qty, max(0, LIMIT - pos))
                    if qty > 0:
                        self._covered_qty = qty
                        self._cover_price = float(ask)
                        self._events.append(f"cover@{rel_ts}:{ask}x{qty}")
                        return self._hard_target_hyd(state, orders, pos + qty)

            if self._covered_qty > 0 and self._cover_price is not None:
                if bid >= self._cover_price + config.profit_ticks:
                    self._events.append(f"reshort@{rel_ts}:{bid}x{self._covered_qty}")
                    self._covered_qty = 0
                    self._cover_price = None
                    self._cycles += 1
                    return self._hard_target_hyd(state, orders, -LIMIT)
                if config.force_reclose and rel_ts >= WINDOW:
                    self._events.append(f"force@{rel_ts}:{bid}x{self._covered_qty}")
                    self._covered_qty = 0
                    self._cover_price = None
                    self._cycles += 1
                    return self._hard_target_hyd(state, orders, -LIMIT)
                return self._hard_target_hyd(state, orders, -LIMIT + self._covered_qty)

            return orders

        def _should_cover(self, mid: float) -> bool:
            if self._release_peak_mid is None:
                return False
            if config.mode == "drop_cover":
                return self._release_peak_mid - mid >= config.cover_drop
            if config.mode == "turn_recycle":
                low = self._post_release_low_mid
                return (
                    low is not None
                    and self._release_peak_mid - low >= config.cover_drop
                    and mid - low >= config.turn_up
                )
            return False

        def _hard_target_hyd(self, state, orders, target_pos: int):
            orders = dict(orders or {})
            depth = state.order_depths.get(PRODUCT)
            pos = int(state.position.get(PRODUCT, 0))
            delta = int(target_pos - pos)
            if depth is None or delta == 0:
                orders[PRODUCT] = []
                return orders
            if delta > 0 and depth.sell_orders:
                orders[PRODUCT] = [Order(PRODUCT, int(min(depth.sell_orders)), delta)]
            elif delta < 0 and depth.buy_orders:
                orders[PRODUCT] = [Order(PRODUCT, int(max(depth.buy_orders)), delta)]
            else:
                orders[PRODUCT] = []
            return orders

    return Trader


def _best_bid(state) -> int | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.buy_orders:
        return None
    return int(max(depth.buy_orders.keys()))


def _best_ask(state) -> int | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.sell_orders:
        return None
    return int(min(depth.sell_orders.keys()))


def _mid(state) -> float | None:
    bid = _best_bid(state)
    ask = _best_ask(state)
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


def _event_state(adapter: SubmissionHydAdapter) -> dict[str, object]:
    inner = getattr(adapter, "_inner", None)
    if inner is None:
        return {}
    event_state = getattr(inner, "event_state", None)
    if isinstance(event_state, dict):
        return event_state
    return {}


def avg_price(records, side: str) -> float | None:
    selected = [record for record in records if record.product == PRODUCT and record.side == side]
    qty = sum(record.quantity for record in selected)
    if qty <= 0:
        return None
    return sum(record.price * record.quantity for record in selected) / qty


def run_full_replay(out_dir: Path) -> pd.DataFrame:
    fill_model = FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True))
    base_cls = load_trader(BASE_ABORTGATE)
    rows: list[dict[str, object]] = []
    for config in full_replay_configs():
        trader_cls = build_trader_cls(base_cls, config)
        for case_name, replay in replay_cases():
            adapter = SubmissionHydAdapter(trader_cls)
            result = BacktestSimulator(adapter, fill_model).run(replay)
            product = result.per_product[PRODUCT]
            pnl_values = [value for _, value in result.pnl_series.get(PRODUCT, ())]
            events = _event_state(adapter)
            rows.append(
                {
                    "candidate": config.name,
                    "mode": config.mode,
                    "case": case_name,
                    "qty": config.qty,
                    "cover_drop": config.cover_drop,
                    "turn_up": config.turn_up,
                    "profit_ticks": config.profit_ticks,
                    "force_reclose": config.force_reclose,
                    "pnl": round(product.pnl, 2),
                    "cash": round(product.cash, 2),
                    "terminal_mark_component": round(product.final_position * (product.mark_price or 0.0), 2),
                    "final_pos": product.final_position,
                    "mark_price": product.mark_price,
                    "trade_count": product.trade_count,
                    "buy_qty": product.buy_trade_quantity,
                    "sell_qty": product.sell_trade_quantity,
                    "avg_buy": _round_or_blank(avg_price(result.trade_records, "buy")),
                    "avg_sell": _round_or_blank(avg_price(result.trade_records, "sell")),
                    "min_pnl": round(min(pnl_values), 2) if pnl_values else "",
                    "peak_pnl": round(max(pnl_values), 2) if pnl_values else "",
                    "max_drawdown": round(max_drawdown(pnl_values), 2),
                    "covered_qty_state": events.get("covered_qty", ""),
                    "cycles": events.get("cycles", ""),
                    "events": events.get("events", ""),
                }
            )
    out_path = out_dir / "post_release_recycler_full_replay.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Wrote {out_path}")
    return pd.DataFrame(rows)


def _round_or_blank(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def official_prices() -> pd.DataFrame:
    payload = json.loads(OFFICIAL_LOG.read_text())
    rows = []
    reader = csv.DictReader(io.StringIO(payload["activitiesLog"]), delimiter=";")
    for row in reader:
        if row.get("product") != PRODUCT:
            continue
        rows.append(
            {
                "dataset": "official_100k",
                "day": 0,
                "timestamp": int(row["timestamp"]),
                "bid": float(row["bid_price_1"]),
                "ask": float(row["ask_price_1"]),
                "mid": float(row["mid_price"]),
            }
        )
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def historical_prices() -> pd.DataFrame:
    frames = []
    for path in sorted(DATA_DIR.glob("prices_round_4_day_*.csv")):
        day = int(path.stem.rsplit("_day_", 1)[1])
        raw = pd.read_csv(path, sep=";")
        hyd = raw[raw["product"].eq(PRODUCT)].copy()
        hyd["dataset"] = f"hist_day_{day}"
        hyd["day"] = day
        hyd = hyd.rename(
            columns={
                "bid_price_1": "bid",
                "ask_price_1": "ask",
                "mid_price": "mid",
            }
        )
        frames.append(hyd[["dataset", "day", "timestamp", "bid", "ask", "mid"]])
    return pd.concat(frames, ignore_index=True).sort_values(["day", "timestamp"]).reset_index(drop=True)


def row_at(prices: pd.DataFrame, timestamp: int) -> pd.Series | None:
    row = prices[prices["timestamp"].eq(timestamp)]
    if row.empty:
        return None
    return row.iloc[0]


def high_windows(hist: pd.DataFrame, official: pd.DataFrame) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    for dataset, prices in hist.groupby("dataset"):
        max_ts = int(prices["timestamp"].max())
        for start in range(0, max_ts - WINDOW + 1, STEP):
            maybe = _window_record(dataset, prices.reset_index(drop=True), start)
            if maybe is not None:
                windows.append(maybe)
    maybe_official = _window_record("official_100k", official, 0)
    if maybe_official is not None:
        windows.append(maybe_official)
    return windows


def _window_record(dataset: str, prices: pd.DataFrame, start: int) -> dict[str, object] | None:
    w = prices[(prices["timestamp"] >= start) & (prices["timestamp"] <= start + WINDOW)].copy()
    if w.empty:
        return None
    trigger_rows = w[
        (w["timestamp"] >= start + TRIGGER_START)
        & (w["timestamp"] <= start + TRIGGER_END)
        & (w["mid"] >= TRIGGER_MID)
    ]
    if trigger_rows.empty:
        return None
    trigger = trigger_rows.iloc[0]
    slope_start = row_at(prices, start + TRIGGER_START)
    slope_gate = row_at(prices, start + SLOPE_GATE_TS)
    release = row_at(prices, start + RELEASE_TS)
    terminal = row_at(prices, start + WINDOW)
    if slope_start is None or slope_gate is None or release is None or terminal is None:
        return None
    slope = float(slope_gate["mid"]) - float(slope_start["mid"])
    if slope < SLOPE_THRESHOLD:
        return None
    return {
        "dataset": dataset,
        "start": start,
        "trigger_ts": int(trigger["timestamp"]),
        "slope": slope,
        "release_bid": float(release["bid"]),
        "release_ask": float(release["ask"]),
        "release_mid": float(release["mid"]),
        "terminal_bid": float(terminal["bid"]),
        "terminal_ask": float(terminal["ask"]),
        "terminal_mid": float(terminal["mid"]),
        "prices": w.reset_index(drop=True),
    }


@dataclass
class PricePolicyState:
    pos: int = -LIMIT
    cash: float = 0.0
    peak_mid: float | None = None
    low_mid: float | None = None
    covered_qty: int = 0
    cover_price: float | None = None
    cycles: int = 0
    events: list[str] | None = None


def simulate_price_policy(window: dict[str, object], config: RecyclerConfig) -> dict[str, object]:
    prices: pd.DataFrame = window["prices"]  # type: ignore[assignment]
    start = int(window["start"])
    state = PricePolicyState(events=[])
    if config.mode == "base":
        return _price_result(window, config, state)

    post = prices[prices["timestamp"] >= start + RELEASE_TS]
    for row in post.itertuples(index=False):
        ts = int(row.timestamp)
        bid = float(row.bid)
        ask = float(row.ask)
        mid = float(row.mid)
        state.peak_mid = mid if state.peak_mid is None else max(state.peak_mid, mid)
        state.low_mid = mid if state.low_mid is None else min(state.low_mid, mid)

        if (
            state.covered_qty <= 0
            and state.cycles < config.max_cycles
            and ts <= start + config.latest_open_ts
            and state.pos <= -LIMIT + max(0, config.qty)
            and _price_should_cover(config, state, mid)
        ):
            qty = min(config.qty, max(0, LIMIT - state.pos))
            if qty > 0:
                state.cash -= ask * qty
                state.pos += qty
                state.covered_qty = qty
                state.cover_price = ask
                state.events.append(f"cover@{ts}:{ask}x{qty}")
                continue

        if state.covered_qty > 0 and state.cover_price is not None:
            if bid >= state.cover_price + config.profit_ticks:
                qty = state.covered_qty
                state.cash += bid * qty
                state.pos -= qty
                state.covered_qty = 0
                state.cover_price = None
                state.cycles += 1
                state.events.append(f"reshort@{ts}:{bid}x{qty}")
            elif config.force_reclose and ts >= start + WINDOW:
                qty = state.covered_qty
                state.cash += bid * qty
                state.pos -= qty
                state.covered_qty = 0
                state.cover_price = None
                state.cycles += 1
                state.events.append(f"force@{ts}:{bid}x{qty}")

    return _price_result(window, config, state)


def _price_should_cover(config: RecyclerConfig, state: PricePolicyState, mid: float) -> bool:
    if state.peak_mid is None:
        return False
    if config.mode == "drop_cover":
        return state.peak_mid - mid >= config.cover_drop
    if config.mode == "turn_recycle":
        if state.low_mid is None:
            return False
        return state.peak_mid - state.low_mid >= config.cover_drop and mid - state.low_mid >= config.turn_up
    return False


def _price_result(
    window: dict[str, object], config: RecyclerConfig, state: PricePolicyState
) -> dict[str, object]:
    terminal_mid = float(window["terminal_mid"])
    score_delta = state.cash + state.pos * terminal_mid - (-LIMIT * terminal_mid)
    terminal_equalized = state.cash
    if state.pos != -LIMIT:
        # If final pos is less short than -LIMIT, force a sell back to -LIMIT
        # at the terminal bid.  Example: pos=-180 => sell 20 => cash +20*bid.
        terminal_equalized += (state.pos + LIMIT) * float(window["terminal_bid"])
    return {
        "candidate": config.name,
        "mode": config.mode,
        "dataset": window["dataset"],
        "start": window["start"],
        "trigger_ts": window["trigger_ts"],
        "slope": round(float(window["slope"]), 2),
        "release_mid": window["release_mid"],
        "terminal_mid": window["terminal_mid"],
        "raw_score_delta_vs_hold_short": round(score_delta, 2),
        "terminal_equalized_delta": round(terminal_equalized, 2),
        "final_pos": state.pos,
        "cycles": state.cycles,
        "events": "|".join(state.events or []),
    }


def run_price_stress(out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    hist = historical_prices()
    official = official_prices()
    windows = high_windows(hist, official)
    rows = []
    for config in recycler_configs():
        for window in windows:
            rows.append(simulate_price_policy(window, config))
    detail = pd.DataFrame(rows)
    detail_path = out_dir / "post_release_recycler_price_windows.csv"
    detail.to_csv(detail_path, index=False)
    print(f"Wrote {detail_path}")

    summary_rows = []
    for candidate, group in detail.groupby("candidate"):
        hist_group = group[group["dataset"].ne("official_100k")]
        official_group = group[group["dataset"].eq("official_100k")]
        cfg = next(c for c in recycler_configs() if c.name == candidate)
        raw = hist_group["raw_score_delta_vs_hold_short"]
        eq = hist_group["terminal_equalized_delta"]
        summary_rows.append(
            {
                "candidate": candidate,
                "mode": cfg.mode,
                "qty": cfg.qty,
                "cover_drop": cfg.cover_drop,
                "turn_up": cfg.turn_up,
                "profit_ticks": cfg.profit_ticks,
                "force_reclose": cfg.force_reclose,
                "hist_windows": len(hist_group),
                "hist_raw_mean": raw.mean(),
                "hist_raw_median": raw.median(),
                "hist_raw_min": raw.min(),
                "hist_raw_p10": raw.quantile(0.10),
                "hist_raw_positive_rate": (raw > 0).mean(),
                "hist_equalized_mean": eq.mean(),
                "hist_equalized_median": eq.median(),
                "hist_equalized_min": eq.min(),
                "hist_equalized_p10": eq.quantile(0.10),
                "hist_equalized_positive_rate": (eq > 0).mean(),
                "hist_action_rate": hist_group["events"].astype(bool).mean(),
                "official_raw_delta": (
                    float(official_group["raw_score_delta_vs_hold_short"].iloc[0])
                    if not official_group.empty
                    else None
                ),
                "official_equalized_delta": (
                    float(official_group["terminal_equalized_delta"].iloc[0])
                    if not official_group.empty
                    else None
                ),
                "official_events": official_group["events"].iloc[0] if not official_group.empty else "",
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["hist_equalized_mean", "hist_raw_mean", "official_raw_delta"],
        ascending=[False, False, False],
    )
    summary_path = out_dir / "post_release_recycler_price_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {summary_path}")
    return detail, summary


def write_doc(full: pd.DataFrame, summary: pd.DataFrame, doc_path: Path) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    official = full[full["case"].eq("official100k_log_replay")].copy()
    base_official = float(official[official["candidate"].eq("abortgate_long40_base")]["pnl"].iloc[0])
    official["delta_vs_base"] = official["pnl"] - base_official
    top_official = official.sort_values("delta_vs_base", ascending=False).head(8)
    top_robust = summary[summary["mode"].ne("base")].head(10)
    bad_raw = summary[summary["mode"].eq("drop_cover")].sort_values("hist_raw_mean").head(3)

    def md_table(df: pd.DataFrame, cols: list[str]) -> str:
        if df.empty:
            return "_No rows._"
        out = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, row in df[cols].iterrows():
            vals = []
            for col in cols:
                value = row[col]
                if isinstance(value, float):
                    vals.append(f"{value:.2f}")
                else:
                    vals.append(str(value))
            out.append("| " + " | ".join(vals) + " |")
        return "\n".join(out)

    text = f"""# HYDROGEL Post-Release Recycler Research

Date: 2026-04-27

## Question

Can we extract additional HYDROGEL alpha after the high-regime release around
60k by covering part of the short and re-shorting later?

## Method

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_post_release_recycler
```

Outputs:

- `outputs/round_4/hydrogel_post_release_recycler/post_release_recycler_full_replay.csv`
- `outputs/round_4/hydrogel_post_release_recycler/post_release_recycler_price_windows.csv`
- `outputs/round_4/hydrogel_post_release_recycler/post_release_recycler_price_summary.csv`

I tested two families:

- blunt `drop_cover`: cover after a post-release drop. This is a negative
  control because it changes terminal exposure if no rebound appears.
- `turn_recycle`: cover only after a drop and a local turn, then re-short only
  if the rebound pays a profit threshold.

The rolling price stress reports both raw score delta versus holding the
`-200` short and terminal-equalized delta that forces the policy back to `-200`
at the terminal bid. Terminal-equalized delta is the cleaner realized-recycler
measure.

## Official-Proxy Full Replay

Base official-proxy HYD for abortgate-long40 is `{base_official:.0f}`.

{md_table(top_official, ["candidate", "mode", "pnl", "delta_vs_base", "final_pos", "max_drawdown", "events"])}

## Best Rolling Historical Policies

Sorted by terminal-equalized mean across historical high-trigger windows:

{md_table(top_robust, ["candidate", "hist_windows", "hist_raw_mean", "hist_raw_min", "hist_equalized_mean", "hist_equalized_min", "hist_action_rate", "official_raw_delta", "official_events"])}

## Negative Controls

Worst blunt cover policies:

{md_table(bad_raw, ["candidate", "hist_raw_mean", "hist_raw_min", "hist_equalized_mean", "hist_action_rate", "official_raw_delta", "official_events"])}

## Readout

The post-release recycler does not currently justify promotion into the final
HYD strategy.

Reasons:

1. Blunt covering is structurally dangerous. It often improves the feeling of
   inventory risk while giving up valuable terminal short exposure.
2. Turn-confirmed recyclers are much safer, but they are sparse. The best ones
   mostly avoid damage rather than adding reliable realized PnL.
3. Official/day-3 post-60k does not offer a clean causal cover/re-short cycle.
   The profitable official HYD shape is still mostly: sell/release high, then
   keep the short into the late lower mark.
4. The remaining hindsight gap is real, but the causal tests say most of it is
   not low-hanging post-release recycling. It is path hindsight.

## Recommendation

Keep `abortgate15_long40_60` / `abortgate15_long20_60` as the HYD finalists.
Do not add a post-release recycler unless we make it tiny and diagnostic only.

If upload budget remains, the only defensible recycler probe would be a
small-size `turn_recycle` negative-control pair, not a final candidate. Expected
official PnL impact is close to zero unless the unseen path contains a clean
drop-and-rebound after release; realistic upside is probably hundreds of HYD,
not thousands, with meaningful downside if it alters terminal exposure.
"""
    doc_path.write_text(text)
    print(f"Wrote {doc_path}")


def run(out_dir: Path, doc_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    full = run_full_replay(out_dir)
    _, summary = run_price_stress(out_dir)
    write_doc(full, summary, doc_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DOC_PATH)
    args = parser.parse_args()
    run(args.out_dir, args.doc)


if __name__ == "__main__":
    main()
