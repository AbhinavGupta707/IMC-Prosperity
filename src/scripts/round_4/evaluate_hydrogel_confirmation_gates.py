"""Evaluate robust HYDROGEL high-regime confirmation gates.

The official 100k path rewards "do not short early; release near 60k", but
that path equals the public day-3 prefix in the local workspace. This harness
therefore optimizes for final-1M robustness instead of the known 100k score.

It produces two complementary diagnostics:

1. Replay summary for upload-shaped wrappers around the current flat995 bundle.
2. Rolling 100k stress summary for false-trigger risk across all historical
   windows that look high in relative 20k-30k.

The rolling stress is intentionally simple. It is not a fill simulator; it
approximates the incremental value of delaying the high-regime short and, when
configured, carrying a small long until confirmation/release.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.simulator import BacktestSimulator
from src.datamodel import Order
from src.scripts.round_4.evaluate_hydrogel_probe_submissions import (
    DATA_DIR,
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

BASELINE = REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_safer_hydflat995.py"
OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_probes"
WINDOW = 99_900
STEP = 10_000


@dataclass(frozen=True)
class ConfirmConfig:
    name: str
    mode: str
    target_pos: int = 0
    short_cap: int = 0
    trigger_start: int = 20_000
    trigger_end: int = 30_000
    trigger_mid: float = 10_020.0
    confirm_start: int = 60_000
    confirm_deadline: int = 60_000
    confirm_bid: int | None = 10_048
    confirm_mid: float | None = None
    require_confirm: bool = True
    slope_start: int = 20_000
    slope_gate_ts: int | None = None
    slope_threshold: float | None = None


def confirm_configs() -> list[ConfirmConfig]:
    return [
        ConfirmConfig("baseline_flat995", "base"),
        ConfirmConfig("hardflat_fixed60k", "target", target_pos=0, require_confirm=False),
        ConfirmConfig("hardlong40_fixed60k", "target", target_pos=40, require_confirm=False),
        ConfirmConfig("hardlong80_fixed60k", "target", target_pos=80, require_confirm=False),
        ConfirmConfig("cap40_fixed60k", "cap", short_cap=-40, require_confirm=False),
        ConfirmConfig(
            "confirm_flat_bid10048_at60",
            "target",
            target_pos=0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_long40_bid10048_at60",
            "target",
            target_pos=40,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_long80_bid10048_at60",
            "target",
            target_pos=80,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_cap40_bid10048_at60",
            "cap",
            short_cap=-40,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_flat_bid10048_55to60",
            "target",
            target_pos=0,
            confirm_start=55_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_long40_bid10048_55to60",
            "target",
            target_pos=40,
            confirm_start=55_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_flat_mid10048_55to60",
            "target",
            target_pos=0,
            confirm_start=55_000,
            confirm_deadline=60_000,
            confirm_bid=None,
            confirm_mid=10_048.0,
            require_confirm=True,
        ),
        ConfirmConfig(
            "confirm_long40_mid10048_55to60",
            "target",
            target_pos=40,
            confirm_start=55_000,
            confirm_deadline=60_000,
            confirm_bid=None,
            confirm_mid=10_048.0,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate15_cap40_flat60",
            "slope_cap_target",
            target_pos=0,
            short_cap=-40,
            slope_gate_ts=40_000,
            slope_threshold=15.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate18_cap40_flat60",
            "slope_cap_target",
            target_pos=0,
            short_cap=-40,
            slope_gate_ts=40_000,
            slope_threshold=18.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate15_cap40_long40_60",
            "slope_cap_target",
            target_pos=40,
            short_cap=-40,
            slope_gate_ts=40_000,
            slope_threshold=15.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate15_cap40_long80_60",
            "slope_cap_target",
            target_pos=80,
            short_cap=-40,
            slope_gate_ts=40_000,
            slope_threshold=15.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate15_cap80_flat60",
            "slope_cap_target",
            target_pos=0,
            short_cap=-80,
            slope_gate_ts=40_000,
            slope_threshold=15.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate18_cap80_flat60",
            "slope_cap_target",
            target_pos=0,
            short_cap=-80,
            slope_gate_ts=40_000,
            slope_threshold=18.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
        ConfirmConfig(
            "slopegate12_cap40_flat60",
            "slope_cap_target",
            target_pos=0,
            short_cap=-40,
            slope_gate_ts=40_000,
            slope_threshold=12.0,
            confirm_start=60_000,
            confirm_deadline=60_000,
            confirm_bid=10_048,
            require_confirm=True,
        ),
    ]


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


def build_trader_cls(base_cls: type, config: ConfirmConfig) -> type:
    if config.mode == "base":
        return base_cls

    class Trader:
        def __init__(self) -> None:
            self._inner = base_cls()
            self._triggered = False
            self._released = False
            self._aborted = False
            self._trigger_ts: int | None = None
            self._release_ts: int | None = None
            self._abort_ts: int | None = None
            self._slope_start_mid: float | None = None
            self._slope_gate_passed = config.mode != "slope_cap_target"

        @property
        def event_state(self) -> dict[str, object]:
            return {
                "triggered": self._triggered,
                "released": self._released,
                "aborted": self._aborted,
                "trigger_ts": self._trigger_ts,
                "release_ts": self._release_ts,
                "abort_ts": self._abort_ts,
                "slope_gate_passed": self._slope_gate_passed,
            }

        def run(self, state):
            orders, conversions, trader_data = self._inner.run(state)
            self._observe_slope_start(state)
            self._observe_trigger(state)
            self._observe_slope_gate(state)
            self._observe_confirm_or_abort(state)

            if self._triggered and self._aborted:
                if int(state.position.get(PRODUCT, 0)) != 0:
                    orders = _hard_target(state, orders, 0)
                return orders, conversions, trader_data

            if self._triggered and not self._released:
                if config.mode == "target":
                    orders = _hard_target(state, orders, config.target_pos)
                elif config.mode == "cap":
                    orders = _apply_short_cap(state, orders, config.short_cap)
                elif config.mode == "slope_cap_target":
                    if self._slope_gate_passed:
                        orders = _hard_target(state, orders, config.target_pos)
                    else:
                        orders = _apply_short_cap(state, orders, config.short_cap)
            return orders, conversions, trader_data

        def _observe_slope_start(self, state) -> None:
            if config.mode != "slope_cap_target" or self._slope_start_mid is not None:
                return
            if state.timestamp >= config.slope_start:
                self._slope_start_mid = _mid(state)

        def _observe_trigger(self, state) -> None:
            if self._triggered:
                return
            if state.timestamp < config.trigger_start or state.timestamp > config.trigger_end:
                return
            mid = _mid(state)
            if mid is not None and mid >= config.trigger_mid:
                self._triggered = True
                self._trigger_ts = int(state.timestamp)

        def _observe_slope_gate(self, state) -> None:
            if (
                config.mode != "slope_cap_target"
                or not self._triggered
                or self._slope_gate_passed
                or self._aborted
            ):
                return
            if config.slope_gate_ts is None or state.timestamp < config.slope_gate_ts:
                return
            mid = _mid(state)
            if (
                mid is not None
                and self._slope_start_mid is not None
                and config.slope_threshold is not None
                and mid - self._slope_start_mid >= config.slope_threshold
            ):
                self._slope_gate_passed = True
            else:
                self._aborted = True
                self._abort_ts = int(state.timestamp)

        def _observe_confirm_or_abort(self, state) -> None:
            if not self._triggered or self._released or self._aborted:
                return
            if config.mode == "slope_cap_target" and not self._slope_gate_passed:
                return
            if config.require_confirm:
                if state.timestamp >= config.confirm_start and _confirmed(state, config):
                    self._released = True
                    self._release_ts = int(state.timestamp)
                    return
                if state.timestamp >= config.confirm_deadline:
                    self._aborted = True
                    self._abort_ts = int(state.timestamp)
                    return
            elif state.timestamp >= config.confirm_deadline:
                self._released = True
                self._release_ts = int(state.timestamp)

    return Trader


def _confirmed(state, config: ConfirmConfig) -> bool:
    bid = _best_bid(state)
    mid = _mid(state)
    bid_ok = config.confirm_bid is not None and bid is not None and bid >= config.confirm_bid
    mid_ok = config.confirm_mid is not None and mid is not None and mid >= config.confirm_mid
    return bid_ok or mid_ok


def _best_bid(state) -> int | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.buy_orders:
        return None
    return int(max(depth.buy_orders.keys()))


def _mid(state) -> float | None:
    depth = state.order_depths.get(PRODUCT)
    if depth is None or not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2


def _hard_target(state, orders, target_pos: int):
    orders = dict(orders or {})
    depth = state.order_depths.get(PRODUCT)
    pos = int(state.position.get(PRODUCT, 0))
    delta = int(target_pos - pos)
    if depth is None or delta == 0:
        orders[PRODUCT] = []
        return orders
    if delta > 0 and depth.sell_orders:
        orders[PRODUCT] = [Order(PRODUCT, int(min(depth.sell_orders.keys())), delta)]
    elif delta < 0 and depth.buy_orders:
        orders[PRODUCT] = [Order(PRODUCT, int(max(depth.buy_orders.keys())), delta)]
    else:
        orders[PRODUCT] = []
    return orders


def _apply_short_cap(state, orders, short_cap: int):
    orders = dict(orders or {})
    depth = state.order_depths.get(PRODUCT)
    pos = int(state.position.get(PRODUCT, 0))
    if depth is not None and pos < short_cap and depth.sell_orders:
        best_ask = min(depth.sell_orders.keys())
        orders[PRODUCT] = [Order(PRODUCT, int(best_ask), int(short_cap - pos))]
        return orders
    filtered = []
    projected = pos
    for order in list(orders.get(PRODUCT, [])):
        qty = int(order.quantity)
        if qty < 0:
            max_sell = max(0, projected - short_cap)
            allowed = min(-qty, max_sell)
            if allowed > 0:
                filtered.append(Order(PRODUCT, int(order.price), -allowed))
                projected -= allowed
        else:
            filtered.append(order)
            projected += qty
    orders[PRODUCT] = filtered
    return orders


def avg_price(records, side: str) -> float | None:
    selected = [record for record in records if record.product == PRODUCT and record.side == side]
    qty = sum(record.quantity for record in selected)
    if qty <= 0:
        return None
    return sum(record.price * record.quantity for record in selected) / qty


def _event_state(adapter: SubmissionHydAdapter) -> dict[str, object]:
    inner = getattr(adapter, "_inner", None)
    if inner is None:
        return {}
    event_state = getattr(inner, "event_state", None)
    if isinstance(event_state, dict):
        return event_state
    return {}


def run_replay_summary(out_dir: Path) -> Path:
    fill_model = FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True))
    base_cls = load_trader(BASELINE)
    cases = replay_cases()
    rows: list[dict[str, object]] = []

    for config in confirm_configs():
        trader_cls = build_trader_cls(base_cls, config)
        for case_name, replay in cases:
            adapter = SubmissionHydAdapter(trader_cls)
            result = BacktestSimulator(adapter, fill_model).run(replay)
            product = result.per_product[PRODUCT]
            pnl_values = [value for _, value in result.pnl_series.get(PRODUCT, ())]
            events = _event_state(adapter)
            rows.append(
                {
                    "candidate": config.name,
                    "case": case_name,
                    "mode": config.mode,
                    "target_pos": config.target_pos,
                    "short_cap": config.short_cap
                    if config.mode in {"cap", "slope_cap_target"}
                    else "",
                    "confirm_start": config.confirm_start,
                    "confirm_deadline": config.confirm_deadline,
                    "confirm_bid": "" if config.confirm_bid is None else config.confirm_bid,
                    "confirm_mid": "" if config.confirm_mid is None else config.confirm_mid,
                    "require_confirm": config.require_confirm,
                    "slope_gate_ts": "" if config.slope_gate_ts is None else config.slope_gate_ts,
                    "slope_threshold": "" if config.slope_threshold is None else config.slope_threshold,
                    "triggered": events.get("triggered", ""),
                    "released": events.get("released", ""),
                    "aborted": events.get("aborted", ""),
                    "slope_gate_passed": events.get("slope_gate_passed", ""),
                    "trigger_ts": events.get("trigger_ts", ""),
                    "release_ts": events.get("release_ts", ""),
                    "abort_ts": events.get("abort_ts", ""),
                    "pnl": round(product.pnl, 2),
                    "cash": round(product.cash, 2),
                    "terminal_mark_component": round(
                        product.final_position * (product.mark_price or 0.0), 2
                    ),
                    "final_pos": product.final_position,
                    "trade_count": product.trade_count,
                    "buy_qty": product.buy_trade_quantity,
                    "sell_qty": product.sell_trade_quantity,
                    "avg_buy_price": _round_or_blank(avg_price(result.trade_records, "buy")),
                    "avg_sell_price": _round_or_blank(avg_price(result.trade_records, "sell")),
                    "min_pnl": round(min(pnl_values), 2) if pnl_values else "",
                    "peak_pnl": round(max(pnl_values), 2) if pnl_values else "",
                    "max_drawdown": round(max_drawdown(pnl_values), 2),
                }
            )

    out_path = out_dir / "confirmation_gate_replay_summary.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def load_prices(day_path: Path) -> pd.DataFrame:
    prices = pd.read_csv(day_path, sep=";")
    out = prices[prices["product"] == PRODUCT].copy()
    return out.sort_values("timestamp").reset_index(drop=True)


def row_at(prices: pd.DataFrame, timestamp: int):
    row = prices[prices["timestamp"] == timestamp]
    if row.empty:
        return None
    return row.iloc[0]


def rolling_stress_rows() -> pd.DataFrame:
    rows = []
    for path in sorted(DATA_DIR.glob("prices_round_4_day_*.csv")):
        dataset = "hist_day_" + path.stem.rsplit("_day_", 1)[1]
        prices = load_prices(path)
        max_ts = int(prices["timestamp"].max())
        for start in range(0, max_ts - WINDOW + 1, STEP):
            window = prices[(prices["timestamp"] >= start) & (prices["timestamp"] <= start + WINDOW)]
            trigger_window = window[
                (window["timestamp"] >= start + 20_000)
                & (window["timestamp"] <= start + 30_000)
                & (window["mid_price"] >= 10_020.0)
            ]
            if trigger_window.empty:
                continue
            trigger = trigger_window.iloc[0]
            terminal = row_at(prices, start + WINDOW)
            if terminal is None:
                continue
            for config in confirm_configs():
                if config.mode == "base":
                    continue
                release = _rolling_release_row(prices, start, config)
                if release is None:
                    continue
                trigger_bid = float(trigger["bid_price_1"])
                trigger_ask = float(trigger["ask_price_1"])
                release_bid = float(release["bid_price_1"])
                terminal_mid = float(terminal["mid_price"])
                delayed_short_delta = 200 * (release_bid - trigger_bid)
                target_extra = 0.0
                if config.mode == "target" and config.target_pos > 0:
                    target_extra = config.target_pos * (release_bid - trigger_ask)
                if config.mode == "cap":
                    # Allowing a -40 cap during the suspicion window retains
                    # 40/200ths of the immediate-short exposure.
                    delayed_short_delta *= 0.8
                if config.mode == "slope_cap_target":
                    gate = row_at(prices, start + (config.slope_gate_ts or 40_000))
                    slope_start = row_at(prices, start + config.slope_start)
                    if gate is None or slope_start is None:
                        continue
                    gate_bid = float(gate["bid_price_1"])
                    gate_ask = float(gate["ask_price_1"])
                    slope_passed = (
                        float(gate["mid_price"]) - float(slope_start["mid_price"])
                        >= float(config.slope_threshold or 0.0)
                    )
                    missing_size = 200 - abs(config.short_cap)
                    if slope_passed:
                        delayed_short_delta = (
                            missing_size * (gate_bid - trigger_bid)
                            + 200 * (release_bid - gate_bid)
                        )
                        if config.target_pos > 0:
                            target_extra = config.target_pos * (release_bid - gate_ask)
                    else:
                        release = gate
                        release_bid = gate_bid
                        delayed_short_delta = missing_size * (gate_bid - trigger_bid)
                        target_extra = 0.0
                rows.append(
                    {
                        "candidate": config.name,
                        "dataset": dataset,
                        "start": start,
                        "trigger_ts": int(trigger["timestamp"]),
                        "trigger_rel": int(trigger["timestamp"]) - start,
                        "trigger_bid": trigger_bid,
                        "trigger_ask": trigger_ask,
                        "release_ts": int(release["timestamp"]),
                        "release_rel": int(release["timestamp"]) - start,
                        "release_bid": release_bid,
                        "terminal_mid": terminal_mid,
                        "confirmed": _rolling_confirmed(prices, start, config),
                        "slope_gate_passed": _rolling_slope_gate_passed(prices, start, config),
                        "delayed_short_delta": delayed_short_delta,
                        "target_extra": target_extra,
                        "overlay_delta": delayed_short_delta + target_extra,
                        "release_short_to_terminal": 200 * (release_bid - terminal_mid),
                    }
                )
    return pd.DataFrame(rows)


def _rolling_release_row(prices: pd.DataFrame, start: int, config: ConfirmConfig):
    if not config.require_confirm:
        return row_at(prices, start + config.confirm_deadline)
    window = prices[
        (prices["timestamp"] >= start + config.confirm_start)
        & (prices["timestamp"] <= start + config.confirm_deadline)
    ]
    if not window.empty:
        mask = pd.Series(False, index=window.index)
        if config.confirm_bid is not None:
            mask = mask | (window["bid_price_1"] >= config.confirm_bid)
        if config.confirm_mid is not None:
            mask = mask | (window["mid_price"] >= config.confirm_mid)
        confirmed = window[mask]
        if not confirmed.empty:
            return confirmed.iloc[0]
    return row_at(prices, start + config.confirm_deadline)


def _rolling_confirmed(prices: pd.DataFrame, start: int, config: ConfirmConfig) -> bool:
    if not config.require_confirm:
        return True
    window = prices[
        (prices["timestamp"] >= start + config.confirm_start)
        & (prices["timestamp"] <= start + config.confirm_deadline)
    ]
    if window.empty:
        return False
    ok = pd.Series(False, index=window.index)
    if config.confirm_bid is not None:
        ok = ok | (window["bid_price_1"] >= config.confirm_bid)
    if config.confirm_mid is not None:
        ok = ok | (window["mid_price"] >= config.confirm_mid)
    return bool(ok.any())


def _rolling_slope_gate_passed(prices: pd.DataFrame, start: int, config: ConfirmConfig) -> object:
    if config.mode != "slope_cap_target":
        return ""
    if config.slope_gate_ts is None or config.slope_threshold is None:
        return False
    slope_start = row_at(prices, start + config.slope_start)
    gate = row_at(prices, start + config.slope_gate_ts)
    if slope_start is None or gate is None:
        return False
    return bool(float(gate["mid_price"]) - float(slope_start["mid_price"]) >= config.slope_threshold)


def run_rolling_stress(out_dir: Path) -> tuple[Path, Path]:
    rows = rolling_stress_rows()
    detail_path = out_dir / "confirmation_gate_rolling_windows.csv"
    rows.to_csv(detail_path, index=False)
    summaries = []
    for candidate, group in rows.groupby("candidate"):
        confirmed = group[group["confirmed"] == True]  # noqa: E712
        official_like = group[(group["dataset"] == "hist_day_3") & (group["start"] == 0)]
        summaries.append(
            {
                "candidate": candidate,
                "windows": len(group),
                "confirmed_windows": len(confirmed),
                "confirmation_rate": len(confirmed) / len(group) if len(group) else 0.0,
                "overlay_mean": group["overlay_delta"].mean(),
                "overlay_min": group["overlay_delta"].min(),
                "overlay_positive_rate": (group["overlay_delta"] > 0).mean(),
                "confirmed_overlay_mean": confirmed["overlay_delta"].mean()
                if not confirmed.empty
                else "",
                "confirmed_overlay_min": confirmed["overlay_delta"].min()
                if not confirmed.empty
                else "",
                "confirmed_positive_rate": (confirmed["overlay_delta"] > 0).mean()
                if not confirmed.empty
                else "",
                "release_short_terminal_mean": group["release_short_to_terminal"].mean(),
                "release_short_terminal_min": group["release_short_to_terminal"].min(),
                "official_like_overlay": ""
                if official_like.empty
                else float(official_like.iloc[0]["overlay_delta"]),
                "official_like_confirmed": ""
                if official_like.empty
                else bool(official_like.iloc[0]["confirmed"]),
            }
        )
    summary = pd.DataFrame(summaries).sort_values("overlay_mean", ascending=False)
    summary_path = out_dir / "confirmation_gate_rolling_summary.csv"
    summary.to_csv(summary_path, index=False)
    return detail_path, summary_path


def _round_or_blank(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    replay_path = run_replay_summary(out_dir)
    detail_path, summary_path = run_rolling_stress(out_dir)
    print(f"Wrote {replay_path}")
    print(f"Wrote {detail_path}")
    print(f"Wrote {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
