"""Greek-aware R4 VELVET/voucher complex research.

This is an offline research harness, not submission code. It treats
VELVETFRUIT_EXTRACT and VEV_* as one option book and produces the evidence
needed to decide whether the current R3 schedule is earning from real option
structure, path luck, spread capture, IV/smile residuals, gamma, or terminal
mark exposure.
"""

from __future__ import annotations

import argparse
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from src.options.bsm import BSMInputs, call_greeks, call_price, implied_vol


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OFFICIAL_DIR = REPO_ROOT / "r4 Sim Results"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "velvet_option_complex"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "VELVET_OPTION_COMPLEX_RESEARCH.md"

UNDERLYING = "VELVETFRUIT_EXTRACT"
STRIKES: tuple[int, ...] = (4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500)
OPTIONS: tuple[str, ...] = tuple(f"VEV_{strike}" for strike in STRIKES)
PRODUCTS: tuple[str, ...] = (UNDERLYING, *OPTIONS)
CORE_SMILE: tuple[str, ...] = ("VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500")
STRIKE_BY_PRODUCT = {f"VEV_{strike}": strike for strike in STRIKES}
LIMITS = {UNDERLYING: 200, **{product: 300 for product in OPTIONS}}
TICKS_PER_DAY = 1_000_000
LIVE_TTE_DAYS = 4.0
FLATTEN_START = 980_000

HORIZONS: tuple[int, ...] = (1_000, 5_000, 10_000, 30_000, 100_000)

SELL7_SCHEDULES = {
    UNDERLYING: [(0, {"limit": 200, "max_order": 40, "buy": 5246, "sell": 5272})],
    "VEV_4000": [(0, {"limit": 300, "max_order": 10, "buy": 1233, "sell": 1263})],
    "VEV_4500": [(0, {"limit": 300, "max_order": 20, "buy": 732, "sell": 766})],
    "VEV_5000": [
        (0, {"limit": 300, "max_order": 40, "buy": 255, "sell": 270}),
        (100_000, {"limit": 300, "max_order": 20, "buy": 241, "sell": 273}),
    ],
    "VEV_5100": [
        (0, {"limit": 300, "max_order": 40, "buy": 165, "sell": 179}),
        (150_000, {"limit": 300, "max_order": 40, "buy": 164, "sell": 183}),
    ],
    "VEV_5200": [
        (0, {"limit": 300, "max_order": 40, "buy": 92, "sell": 106}),
        (300_000, {"limit": 300, "max_order": 40, "buy": 93, "sell": 105}),
    ],
    "VEV_5300": [
        (0, {"limit": 300, "max_order": 20, "buy": 45, "sell": 52}),
        (50_000, {"limit": 300, "max_order": 40, "buy": 45, "sell": 52}),
    ],
    "VEV_5400": [
        (0, {"limit": 300, "max_order": 40, "buy": 13, "sell": 17}),
        (100_000, {"limit": 300, "max_order": 40, "buy": 15, "sell": 18}),
    ],
    "VEV_5500": [(0, {"limit": 300, "max_order": 40, "buy": -1, "sell": 7})],
}


def _copy_schedules() -> dict[str, list[tuple[int, dict[str, int]]]]:
    return {
        product: [(start, dict(cfg)) for start, cfg in schedule]
        for product, schedule in SELL7_SCHEDULES.items()
    }


def schedule_variants() -> dict[str, dict[str, list[tuple[int, dict[str, int]]]]]:
    sell7 = _copy_schedules()
    disabled = _copy_schedules()
    disabled["VEV_5500"] = [(0, {"limit": 300, "max_order": 40, "buy": -1, "sell": 999_999})]
    baseline = _copy_schedules()
    baseline["VEV_5500"] = [(0, {"limit": 300, "max_order": 40, "buy": 7, "sell": 8})]
    sellonly8 = _copy_schedules()
    sellonly8["VEV_5500"] = [(0, {"limit": 300, "max_order": 40, "buy": -1, "sell": 8})]
    return {
        "baseline_buy7_sell8": baseline,
        "disabled": disabled,
        "sellonly8": sellonly8,
        "sell7": sell7,
    }


def tte_live(timestamp: int) -> float:
    return max(LIVE_TTE_DAYS - timestamp / TICKS_PER_DAY, 1e-6)


def moneyness(strike: float, spot: float, tte: float) -> float:
    return math.log(strike / spot) / math.sqrt(tte)


def product_strike(product: str) -> int | None:
    return STRIKE_BY_PRODUCT.get(product)


def _schedule_for(product: str, timestamp: int, schedules: dict[str, list[tuple[int, dict[str, int]]]]) -> dict[str, int] | None:
    schedule = schedules.get(product)
    if not schedule:
        return None
    selected = schedule[0][1]
    for start, cfg in schedule:
        if timestamp >= start:
            selected = cfg
        else:
            break
    return selected


def _numeric_prices(prices: pd.DataFrame, *, dataset: str) -> pd.DataFrame:
    out = prices.copy()
    out["dataset"] = dataset
    numeric = ["day", "timestamp", "mid_price", "profit_and_loss"]
    for level in (1, 2, 3):
        numeric.extend(
            [
                f"bid_price_{level}",
                f"bid_volume_{level}",
                f"ask_price_{level}",
                f"ask_volume_{level}",
            ]
        )
    for column in numeric:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    for level in (1, 2, 3):
        for column in (f"bid_volume_{level}", f"ask_volume_{level}"):
            if column in out.columns:
                out[column] = out[column].abs().fillna(0).astype(int)
    out["timestamp"] = out["timestamp"].astype(int)
    out["day"] = out["day"].astype(int)
    return out[out["product"].isin(PRODUCTS)].sort_values(
        ["dataset", "day", "timestamp", "product"]
    ).reset_index(drop=True)


def load_historical(data_dir: Path) -> pd.DataFrame:
    frames = []
    for day in (1, 2, 3):
        path = data_dir / f"prices_round_4_day_{day}.csv"
        frames.append(pd.read_csv(path, sep=";"))
    return _numeric_prices(pd.concat(frames, ignore_index=True), dataset="historical")


def load_official_log(path: Path, *, dataset: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(path.read_text())
    activities = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
    activities = _numeric_prices(activities, dataset=dataset)
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if trades.empty:
        trades = pd.DataFrame(columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity"])
    else:
        trades["dataset"] = dataset
        for column in ("timestamp", "price", "quantity"):
            trades[column] = pd.to_numeric(trades[column], errors="coerce")
        trades["timestamp"] = trades["timestamp"].astype(int)
        trades["quantity"] = trades["quantity"].astype(int)
    return activities, trades


def load_official_books(official_dir: Path) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    paths = {
        "official_flat995": official_dir / "extracted" / "flat995" / "493202.log",
        "official_disabled": official_dir / "disabled" / "497554.log",
        "official_sellonly8": official_dir / "sellonly" / "497595.log",
        "official_sell7_validated": official_dir / "validated" / "511763.log",
        "official_tte4": official_dir / "extracted" / "tte4" / "492648.log",
    }
    books: dict[str, pd.DataFrame] = {}
    trades: dict[str, pd.DataFrame] = {}
    for name, path in paths.items():
        if not path.exists():
            continue
        books[name], trades[name] = load_official_log(path, dataset=name)
    return books, trades


def compute_realized_vol(prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = prices[prices["product"] == UNDERLYING][
        ["dataset", "day", "timestamp", "mid_price", "bid_price_1", "ask_price_1"]
    ].copy()
    for (dataset, day), group in base.groupby(["dataset", "day"], sort=False):
        group = group.sort_values("timestamp").reset_index(drop=True)
        log_mid = np.log(group["mid_price"].to_numpy(dtype=float))
        step_ticks = int(np.median(np.diff(group["timestamp"].to_numpy(dtype=int)))) if len(group) > 1 else 100
        step_days = step_ticks / TICKS_PER_DAY
        one_step_returns = np.diff(log_mid, prepend=log_mid[0])
        out = group[["dataset", "day", "timestamp", "mid_price", "bid_price_1", "ask_price_1"]].copy()
        out.rename(
            columns={
                "mid_price": "spot_mid",
                "bid_price_1": "spot_bid",
                "ask_price_1": "spot_ask",
            },
            inplace=True,
        )
        for horizon in HORIZONS:
            steps = max(1, int(round(horizon / step_ticks)))
            horizon_days = steps * step_days
            sq = pd.Series(one_step_returns * one_step_returns)
            back_var = sq.rolling(steps, min_periods=max(2, min(steps, 5))).sum() / horizon_days
            fwd_var = sq.shift(-steps + 1).rolling(steps, min_periods=max(2, min(steps, 5))).sum().shift(-(steps - 1)) / horizon_days
            out[f"rv_back_{horizon}"] = np.sqrt(back_var.clip(lower=0.0))
            out[f"rv_fwd_{horizon}"] = np.sqrt(fwd_var.clip(lower=0.0))
            out[f"spot_mid_fwd_{horizon}"] = out["spot_mid"].shift(-steps)
            out[f"spot_bid_fwd_{horizon}"] = out["spot_bid"].shift(-steps)
            out[f"spot_ask_fwd_{horizon}"] = out["spot_ask"].shift(-steps)
        rows.append(out)
    return pd.concat(rows, ignore_index=True)


def enrich_options(
    prices: pd.DataFrame,
    rv: pd.DataFrame,
    *,
    feature_keys: set[tuple[str, int, int]] | None = None,
    sample_interval: int = 1_000,
) -> pd.DataFrame:
    spot = rv[["dataset", "day", "timestamp", "spot_mid", "spot_bid", "spot_ask"]].copy()
    option_rows = prices[prices["product"].isin(OPTIONS)].merge(
        spot, on=["dataset", "day", "timestamp"], how="left"
    )
    sample_mask = option_rows["timestamp"].mod(sample_interval).eq(0)
    if feature_keys:
        key_frame = pd.DataFrame(
            list(feature_keys), columns=["dataset", "day", "timestamp"]
        ).drop_duplicates()
        key_frame["_feature_key"] = True
        option_rows = option_rows.merge(
            key_frame, on=["dataset", "day", "timestamp"], how="left"
        )
        sample_mask = sample_mask | option_rows["_feature_key"].fillna(False)
        option_rows = option_rows.drop(columns=["_feature_key"])
    option_rows = option_rows[sample_mask].copy()
    print(f"  option feature rows: {len(option_rows):,}")
    records = []
    for row in option_rows.itertuples(index=False):
        product = str(row.product)
        strike = float(STRIKE_BY_PRODUCT[product])
        spot_mid = float(row.spot_mid)
        mid = float(row.mid_price)
        timestamp = int(row.timestamp)
        tte = tte_live(timestamp)
        intrinsic = max(0.0, spot_mid - strike)
        extrinsic = mid - intrinsic
        iv = implied_vol(
            mid,
            spot=spot_mid,
            strike=strike,
            time_to_expiry=tte,
            lo=0.001,
            hi=2.0,
            tol=1e-4,
            max_iter=32,
        )
        delta = gamma = vega = theta = np.nan
        scaled_m = np.nan
        if iv is not None and math.isfinite(iv) and 0.001 <= iv <= 2.0:
            try:
                inputs = BSMInputs(
                    spot=spot_mid,
                    strike=strike,
                    time_to_expiry=tte,
                    volatility=iv,
                )
                greeks = call_greeks(inputs)
                delta = greeks.delta
                gamma = greeks.gamma
                vega = greeks.vega
                theta = greeks.theta
                scaled_m = moneyness(strike, spot_mid, tte)
            except (ValueError, OverflowError, ZeroDivisionError):
                pass
        records.append(
            {
                "dataset": row.dataset,
                "day": int(row.day),
                "timestamp": timestamp,
                "product": product,
                "strike": int(strike),
                "spot_mid": spot_mid,
                "spot_bid": float(row.spot_bid),
                "spot_ask": float(row.spot_ask),
                "tte": tte,
                "bid": float(row.bid_price_1),
                "ask": float(row.ask_price_1),
                "mid": mid,
                "spread": float(row.ask_price_1) - float(row.bid_price_1),
                "intrinsic": intrinsic,
                "extrinsic": extrinsic,
                "iv": iv if iv is not None else np.nan,
                "moneyness": spot_mid / strike,
                "scaled_moneyness": scaled_m,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta,
            }
        )
    options = pd.DataFrame(records)
    options = fit_smile_residuals(options)
    options = options.merge(rv, on=["dataset", "day", "timestamp"], how="left", suffixes=("", "_rv"))
    return options


def fit_smile_residuals(options: pd.DataFrame) -> pd.DataFrame:
    options = options.copy()
    for column in ("fair_iv", "fair_price", "iv_residual", "price_residual"):
        options[column] = np.nan

    grouped = options.groupby(["dataset", "day", "timestamp"], sort=False)
    updates: list[pd.DataFrame] = []
    for _, group in grouped:
        core = group[
            group["product"].isin(CORE_SMILE)
            & group["iv"].between(0.001, 0.50)
            & np.isfinite(group["scaled_moneyness"])
        ]
        if len(core) < 3:
            continue
        update = group[["dataset", "day", "timestamp", "product", "spot_mid", "strike", "tte", "mid", "iv", "scaled_moneyness"]].copy()
        fair_ivs: list[float] = []
        fair_prices: list[float] = []
        for row in update.itertuples(index=False):
            fit = core[core["product"] != row.product]
            if len(fit) < 3:
                fit = core
            degree = 2 if len(fit) >= 4 else 1
            try:
                coeff = np.polyfit(
                    fit["scaled_moneyness"].to_numpy(dtype=float),
                    fit["iv"].to_numpy(dtype=float),
                    deg=degree,
                )
            except (np.linalg.LinAlgError, ValueError):
                fair_ivs.append(np.nan)
                fair_prices.append(np.nan)
                continue
            fair_iv = float(np.polyval(coeff, float(row.scaled_moneyness)))
            if not math.isfinite(fair_iv) or fair_iv <= 0.0 or fair_iv > 1.0:
                fair_ivs.append(np.nan)
                fair_prices.append(np.nan)
                continue
            try:
                fair = call_price(
                    BSMInputs(
                        spot=float(row.spot_mid),
                        strike=float(row.strike),
                        time_to_expiry=float(row.tte),
                        volatility=fair_iv,
                    )
                )
            except (ValueError, OverflowError, ZeroDivisionError):
                fair = np.nan
            fair_ivs.append(fair_iv)
            fair_prices.append(float(fair))
        update["fair_iv"] = fair_ivs
        update["fair_price"] = fair_prices
        update["iv_residual"] = update["iv"] - update["fair_iv"]
        update["price_residual"] = update["mid"] - update["fair_price"]
        updates.append(update[["dataset", "day", "timestamp", "product", "fair_iv", "fair_price", "iv_residual", "price_residual"]])

    if not updates:
        return options
    fitted = pd.concat(updates, ignore_index=True)
    options = options.drop(columns=["fair_iv", "fair_price", "iv_residual", "price_residual"]).merge(
        fitted, on=["dataset", "day", "timestamp", "product"], how="left"
    )
    return options


@dataclass(frozen=True)
class ScheduleRun:
    label: str
    trades: pd.DataFrame
    pnl: pd.DataFrame
    path: pd.DataFrame
    blocked: pd.DataFrame


def simulate_schedule(
    prices: pd.DataFrame,
    *,
    schedules: dict[str, list[tuple[int, dict[str, int]]]],
    label: str,
) -> ScheduleRun:
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []
    path_rows: list[dict] = []
    blocked_rows: list[dict] = []

    for (dataset, day), day_prices in prices.groupby(["dataset", "day"], sort=False):
        positions = {product: 0 for product in PRODUCTS}
        cash = {product: 0.0 for product in PRODUCTS}
        last_mid: dict[str, float] = {}
        peak_total = -float("inf")
        day_prices = day_prices.sort_values(["timestamp", "product"])
        for timestamp, group in day_prices.groupby("timestamp", sort=True):
            timestamp = int(timestamp)
            rows = {str(row.product): row for row in group.itertuples(index=False)}
            for product, row in rows.items():
                if pd.notna(row.mid_price):
                    last_mid[product] = float(row.mid_price)

            for product in schedules:
                row = rows.get(product)
                cfg = _schedule_for(product, timestamp, schedules)
                if row is None or cfg is None:
                    continue
                position_before_tick = positions[product]
                bid = float(row.bid_price_1) if pd.notna(row.bid_price_1) else np.nan
                ask = float(row.ask_price_1) if pd.notna(row.ask_price_1) else np.nan
                bid_volume = int(abs(row.bid_volume_1)) if pd.notna(row.bid_volume_1) else 0
                ask_volume = int(abs(row.ask_volume_1)) if pd.notna(row.ask_volume_1) else 0

                if timestamp >= FLATTEN_START:
                    if positions[product] > 0 and math.isfinite(bid):
                        qty = min(cfg["max_order"], bid_volume, positions[product])
                        if qty > 0:
                            _record_trade(trade_rows, label, dataset, day, timestamp, product, "sell_flatten", bid, qty, positions, cash, cfg)
                    elif positions[product] < 0 and math.isfinite(ask):
                        qty = min(cfg["max_order"], ask_volume, -positions[product])
                        if qty > 0:
                            _record_trade(trade_rows, label, dataset, day, timestamp, product, "buy_flatten", ask, qty, positions, cash, cfg)
                    continue

                if math.isfinite(ask) and ask <= cfg["buy"]:
                    if positions[product] < cfg["limit"]:
                        qty = min(cfg["max_order"], ask_volume, cfg["limit"] - positions[product])
                        if qty > 0:
                            _record_trade(trade_rows, label, dataset, day, timestamp, product, "buy", ask, qty, positions, cash, cfg)
                    else:
                        blocked_rows.append(
                            _blocked_record(label, dataset, day, timestamp, product, "buy_blocked_long_limit", ask, ask_volume, cfg, position_before_tick)
                        )
                if math.isfinite(bid) and bid >= cfg["sell"]:
                    if positions[product] > -cfg["limit"]:
                        qty = min(cfg["max_order"], bid_volume, cfg["limit"] + positions[product])
                        if qty > 0:
                            _record_trade(trade_rows, label, dataset, day, timestamp, product, "sell", bid, qty, positions, cash, cfg)
                    else:
                        blocked_rows.append(
                            _blocked_record(label, dataset, day, timestamp, product, "sell_blocked_short_limit", bid, bid_volume, cfg, position_before_tick)
                        )

            product_pnls = {
                product: cash[product] + positions[product] * last_mid.get(product, 0.0)
                for product in PRODUCTS
            }
            total = float(sum(product_pnls.values()))
            peak_total = max(peak_total, total)
            pnl_rows.append(
                {
                    "variant": label,
                    "dataset": dataset,
                    "day": day,
                    "timestamp": timestamp,
                    "total_pnl": total,
                    "drawdown": total - peak_total,
                    **{f"pnl_{product}": product_pnls[product] for product in PRODUCTS},
                }
            )
            for product in schedules:
                path_rows.append(
                    {
                        "variant": label,
                        "dataset": dataset,
                        "day": day,
                        "timestamp": timestamp,
                        "product": product,
                        "position": positions[product],
                        "cash": cash[product],
                        "mark": last_mid.get(product, np.nan),
                        "pnl": product_pnls[product],
                    }
                )

    trades = pd.DataFrame(trade_rows)
    pnl = pd.DataFrame(pnl_rows)
    path = pd.DataFrame(path_rows)
    blocked = pd.DataFrame(blocked_rows)
    return ScheduleRun(label=label, trades=trades, pnl=pnl, path=path, blocked=blocked)


def _record_trade(
    rows: list[dict],
    variant: str,
    dataset: str,
    day: int,
    timestamp: int,
    product: str,
    side: str,
    price: float,
    qty: int,
    positions: dict[str, int],
    cash: dict[str, float],
    cfg: dict[str, int],
) -> None:
    pos_before = positions[product]
    if side.startswith("buy"):
        signed = qty
        cash[product] -= price * qty
        positions[product] += qty
    else:
        signed = -qty
        cash[product] += price * qty
        positions[product] -= qty
    rows.append(
        {
            "variant": variant,
            "dataset": dataset,
            "day": int(day),
            "timestamp": int(timestamp),
            "product": product,
            "side": "buy" if signed > 0 else "sell",
            "reason": side,
            "price": float(price),
            "qty": int(qty),
            "signed_qty": int(signed),
            "pos_before": int(pos_before),
            "pos_after": int(positions[product]),
            "schedule_buy": cfg["buy"],
            "schedule_sell": cfg["sell"],
        }
    )


def _blocked_record(
    variant: str,
    dataset: str,
    day: int,
    timestamp: int,
    product: str,
    side: str,
    price: float,
    volume: int,
    cfg: dict[str, int],
    position: int,
) -> dict:
    return {
        "variant": variant,
        "dataset": dataset,
        "day": int(day),
        "timestamp": int(timestamp),
        "product": product,
        "side": side,
        "price": float(price),
        "visible_volume": int(volume),
        "position": int(position),
        "schedule_buy": cfg["buy"],
        "schedule_sell": cfg["sell"],
    }


def attach_forward_edges(
    trades: pd.DataFrame,
    prices: pd.DataFrame,
    options: pd.DataFrame,
    rv: pd.DataFrame,
) -> pd.DataFrame:
    if trades.empty:
        return trades
    out = trades.copy()
    quote_cols = [
        "dataset",
        "day",
        "timestamp",
        "product",
        "bid_price_1",
        "ask_price_1",
        "mid_price",
    ]
    quotes = prices[quote_cols].copy()
    out = out.merge(quotes, on=["dataset", "day", "timestamp", "product"], how="left")
    option_features = options[
        [
            "dataset",
            "day",
            "timestamp",
            "product",
            "strike",
            "spot_mid",
            "moneyness",
            "iv",
            "fair_iv",
            "iv_residual",
            "price_residual",
            "delta",
            "gamma",
            "vega",
            "theta",
            *[f"rv_fwd_{h}" for h in HORIZONS],
        ]
    ].copy()
    out = out.merge(option_features, on=["dataset", "day", "timestamp", "product"], how="left")
    spot = rv[["dataset", "day", "timestamp", "spot_mid", *[f"spot_mid_fwd_{h}" for h in HORIZONS]]]
    out = out.merge(spot, on=["dataset", "day", "timestamp"], how="left", suffixes=("", "_underlying"))

    final_mid = (
        prices.sort_values("timestamp")
        .groupby(["dataset", "day", "product"], sort=False)
        .tail(1)[["dataset", "day", "product", "mid_price"]]
        .rename(columns={"mid_price": "end_mid"})
    )
    out = out.merge(final_mid, on=["dataset", "day", "product"], how="left")
    side_sign = np.where(out["side"] == "buy", 1.0, -1.0)
    out["edge_mid_end"] = side_sign * (out["end_mid"] - out["price"])
    out["raw_pnl_end"] = out["edge_mid_end"] * out["qty"]

    for horizon in HORIZONS:
        future = quotes.copy()
        future["timestamp"] = future["timestamp"] - horizon
        future = future.rename(
            columns={
                "bid_price_1": f"bid_fwd_{horizon}",
                "ask_price_1": f"ask_fwd_{horizon}",
                "mid_price": f"mid_fwd_{horizon}",
            }
        )
        out = out.merge(
            future[
                [
                    "dataset",
                    "day",
                    "timestamp",
                    "product",
                    f"bid_fwd_{horizon}",
                    f"ask_fwd_{horizon}",
                    f"mid_fwd_{horizon}",
                ]
            ],
            on=["dataset", "day", "timestamp", "product"],
            how="left",
        )
        out[f"edge_mid_{horizon}"] = np.where(
            out["side"] == "buy",
            out[f"mid_fwd_{horizon}"] - out["price"],
            out["price"] - out[f"mid_fwd_{horizon}"],
        )
        out[f"edge_spread_{horizon}"] = np.where(
            out["side"] == "buy",
            out[f"bid_fwd_{horizon}"] - out["price"],
            out["price"] - out[f"ask_fwd_{horizon}"],
        )
        delta = out["delta"].fillna(0.0)
        d_spot = out[f"spot_mid_fwd_{horizon}"] - out["spot_mid_underlying"]
        out[f"delta_hedged_mid_{horizon}"] = out[f"edge_mid_{horizon}"] - side_sign * delta * d_spot
        out[f"raw_pnl_mid_{horizon}"] = out[f"edge_mid_{horizon}"] * out["qty"]
        out[f"raw_pnl_delta_hedged_{horizon}"] = out[f"delta_hedged_mid_{horizon}"] * out["qty"]

    out["moneyness_bucket"] = pd.cut(
        out["moneyness"],
        bins=[-np.inf, 0.90, 0.98, 1.02, 1.10, np.inf],
        labels=["far_otm", "otm", "atm", "itm", "deep_itm"],
    )
    out["iv_richness"] = np.where(
        out["iv_residual"] < -0.005,
        "cheap",
        np.where(out["iv_residual"] > 0.005, "rich", "near_smile"),
    )
    return out


def attach_blocked_edges(blocked: pd.DataFrame, prices: pd.DataFrame, options: pd.DataFrame, rv: pd.DataFrame) -> pd.DataFrame:
    if blocked.empty:
        return blocked
    pseudo = blocked.rename(columns={"visible_volume": "qty"}).copy()
    pseudo["side"] = np.where(pseudo["side"].str.startswith("buy"), "buy", "sell")
    pseudo["reason"] = pseudo["side"] + "_blocked"
    pseudo["signed_qty"] = np.where(pseudo["side"] == "buy", pseudo["qty"], -pseudo["qty"])
    pseudo["pos_before"] = pseudo["position"]
    pseudo["pos_after"] = pseudo["position"]
    enriched = attach_forward_edges(pseudo, prices, options, rv)
    return enriched


def summarize_pnl(run: ScheduleRun) -> pd.DataFrame:
    if run.pnl.empty:
        return pd.DataFrame()
    rows = []
    for (variant, dataset, day), group in run.pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        row = {
            "variant": variant,
            "dataset": dataset,
            "day": int(day),
            "total_pnl": float(last["total_pnl"]),
            "max_drawdown": float(group["drawdown"].min()),
            "first_ts_50pct": _first_fraction_ts(group, 0.50),
            "first_ts_80pct": _first_fraction_ts(group, 0.80),
            "first_ts_99pct": _first_fraction_ts(group, 0.99),
        }
        for product in SELL7_SCHEDULES:
            row[f"{product}_pnl"] = float(last.get(f"pnl_{product}", 0.0))
        rows.append(row)
    return pd.DataFrame(rows)


def _first_fraction_ts(group: pd.DataFrame, fraction: float) -> int | None:
    final = float(group["total_pnl"].iloc[-1])
    if final <= 0:
        return None
    hits = group[group["total_pnl"] >= final * fraction]
    if hits.empty:
        return None
    return int(hits.iloc[0]["timestamp"])


def summarize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    group_cols = ["variant", "dataset", "product", "side"]
    for key, group in trades.groupby(group_cols, dropna=False, sort=False):
        row = dict(zip(group_cols, key, strict=True))
        row["events"] = int(len(group))
        row["qty"] = int(group["qty"].sum())
        row["end_raw_pnl"] = float(group["raw_pnl_end"].sum())
        row["avg_iv"] = float(group["iv"].mean()) if "iv" in group else np.nan
        row["avg_iv_residual"] = float(group["iv_residual"].mean()) if "iv_residual" in group else np.nan
        row["avg_delta"] = float(group["delta"].mean()) if "delta" in group else np.nan
        row["avg_gamma"] = float(group["gamma"].mean()) if "gamma" in group else np.nan
        row["avg_vega"] = float(group["vega"].mean()) if "vega" in group else np.nan
        for horizon in HORIZONS:
            row[f"qty_edge_mid_{horizon}"] = _wavg(group, f"edge_mid_{horizon}")
            row[f"qty_edge_spread_{horizon}"] = _wavg(group, f"edge_spread_{horizon}")
            row[f"qty_delta_hedged_{horizon}"] = _wavg(group, f"delta_hedged_mid_{horizon}")
            row[f"raw_delta_hedged_pnl_{horizon}"] = float(group[f"raw_pnl_delta_hedged_{horizon}"].sum(skipna=True))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["variant", "dataset", "product", "side"])


def summarize_by_condition(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    group_cols = ["variant", "dataset", "product", "side", "moneyness_bucket", "iv_richness"]
    for key, group in trades.groupby(group_cols, dropna=False, sort=False):
        row = dict(zip(group_cols, key, strict=True))
        row["events"] = int(len(group))
        row["qty"] = int(group["qty"].sum())
        row["end_raw_pnl"] = float(group["raw_pnl_end"].sum())
        row["avg_iv_residual"] = float(group["iv_residual"].mean()) if "iv_residual" in group else np.nan
        row["qty_delta_hedged_30000"] = _wavg(group, "delta_hedged_mid_30000")
        row["qty_edge_mid_30000"] = _wavg(group, "edge_mid_30000")
        row["qty_edge_mid_100000"] = _wavg(group, "edge_mid_100000")
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["variant", "dataset", "product", "side", "moneyness_bucket", "iv_richness"]
    )


def _wavg(group: pd.DataFrame, column: str) -> float:
    valid = group.dropna(subset=[column, "qty"])
    if valid.empty or valid["qty"].sum() == 0:
        return np.nan
    return float(np.average(valid[column].to_numpy(dtype=float), weights=valid["qty"].to_numpy(dtype=float)))


def summarize_options(options: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (dataset, product), group in options.groupby(["dataset", "product"], sort=False):
        row = {
            "dataset": dataset,
            "product": product,
            "strike": int(group["strike"].iloc[0]),
            "rows": int(len(group)),
            "mean_spread": float(group["spread"].mean()),
            "mean_mid": float(group["mid"].mean()),
            "mean_intrinsic": float(group["intrinsic"].mean()),
            "mean_extrinsic": float(group["extrinsic"].mean()),
            "iv_valid_rows": int(group["iv"].notna().sum()),
            "mean_iv": float(group["iv"].mean()),
            "p10_iv": float(group["iv"].quantile(0.10)),
            "p50_iv": float(group["iv"].quantile(0.50)),
            "p90_iv": float(group["iv"].quantile(0.90)),
            "mean_fair_iv": float(group["fair_iv"].mean()),
            "mean_iv_residual": float(group["iv_residual"].mean()),
            "mean_price_residual": float(group["price_residual"].mean()),
            "mean_delta": float(group["delta"].mean()),
            "mean_gamma": float(group["gamma"].mean()),
            "mean_vega": float(group["vega"].mean()),
            "mean_theta": float(group["theta"].mean()),
            "mean_rv_fwd_30000": float(group["rv_fwd_30000"].mean()),
            "mean_rv_fwd_100000": float(group["rv_fwd_100000"].mean()),
        }
        row["iv_minus_rv_30000"] = row["mean_iv"] - row["mean_rv_fwd_30000"]
        row["iv_minus_rv_100000"] = row["mean_iv"] - row["mean_rv_fwd_100000"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["dataset", "strike"])


def compute_portfolio_greeks(path: pd.DataFrame, options: pd.DataFrame) -> pd.DataFrame:
    if path.empty:
        return pd.DataFrame()
    opt = options[["dataset", "day", "timestamp", "product", "delta", "gamma", "vega", "theta"]]
    sampled_keys = opt[["dataset", "day", "timestamp"]].drop_duplicates()
    path = path.merge(sampled_keys, on=["dataset", "day", "timestamp"], how="inner")
    merged = path.merge(opt, on=["dataset", "day", "timestamp", "product"], how="left")
    merged["delta_contrib"] = np.where(
        merged["product"] == UNDERLYING,
        merged["position"].astype(float),
        merged["position"].astype(float) * merged["delta"].fillna(0.0),
    )
    for greek in ("gamma", "vega", "theta"):
        merged[f"{greek}_contrib"] = np.where(
            merged["product"] == UNDERLYING,
            0.0,
            merged["position"].astype(float) * merged[greek].fillna(0.0),
        )
    grouped = merged.groupby(["variant", "dataset", "day", "timestamp"], sort=False).agg(
        total_pnl=("pnl", "sum"),
        net_delta=("delta_contrib", "sum"),
        net_gamma=("gamma_contrib", "sum"),
        net_vega=("vega_contrib", "sum"),
        net_theta=("theta_contrib", "sum"),
        gross_position=("position", lambda s: int(s.abs().sum())),
    )
    return grouped.reset_index()


def _rolling_max_left(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 0:
        return values.copy()
    width = min(width, len(values) - 1)
    padded = np.pad(values, (width, 0), mode="constant", constant_values=-1e100)
    return sliding_window_view(padded, width + 1).max(axis=1)


def _rolling_max_right(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 0:
        return values.copy()
    width = min(width, len(values) - 1)
    padded = np.pad(values, (0, width), mode="constant", constant_values=-1e100)
    return sliding_window_view(padded, width + 1).max(axis=1)


def l1_oracle_product(
    group: pd.DataFrame,
    *,
    limit: int,
    max_order_cap: int | None = None,
) -> float:
    group = group.sort_values("timestamp")
    positions = np.arange(-limit, limit + 1, dtype=float)
    value = np.full(2 * limit + 1, -1e100, dtype=float)
    value[limit] = 0.0
    for row in group.itertuples(index=False):
        next_value = value.copy()
        bid = getattr(row, "bid_price_1")
        ask = getattr(row, "ask_price_1")
        bid_vol = int(getattr(row, "bid_volume_1") or 0)
        ask_vol = int(getattr(row, "ask_volume_1") or 0)
        if max_order_cap is not None:
            bid_vol = min(bid_vol, max_order_cap)
            ask_vol = min(ask_vol, max_order_cap)
        if pd.notna(ask) and ask_vol > 0:
            base = value + float(ask) * positions
            next_value = np.maximum(next_value, _rolling_max_left(base, ask_vol) - float(ask) * positions)
        if pd.notna(bid) and bid_vol > 0:
            base = value + float(bid) * positions
            next_value = np.maximum(next_value, _rolling_max_right(base, bid_vol) - float(bid) * positions)
        value = next_value
    end_mid = float(group.iloc[-1]["mid_price"])
    return float(np.max(value + positions * end_mid))


def compute_oracles(
    prices: pd.DataFrame,
    schedule_pnl: pd.DataFrame,
    *,
    include_capped: bool = False,
) -> pd.DataFrame:
    rows = []
    sell7_product_pnl = _schedule_product_pnl_lookup(schedule_pnl)
    for (dataset, day, product), group in prices[prices["product"].isin(SELL7_SCHEDULES)].groupby(
        ["dataset", "day", "product"], sort=False
    ):
        full_oracle = l1_oracle_product(group, limit=LIMITS[product], max_order_cap=None)
        capped_oracle = np.nan
        if include_capped:
            cfg = _schedule_for(product, 0, SELL7_SCHEDULES)
            max_order = cfg["max_order"] if cfg else None
            capped_oracle = l1_oracle_product(group, limit=LIMITS[product], max_order_cap=max_order)
        schedule_value = sell7_product_pnl.get((dataset, int(day), product), np.nan)
        rows.append(
            {
                "dataset": dataset,
                "day": int(day),
                "product": product,
                "strike": STRIKE_BY_PRODUCT.get(product, np.nan),
                "oracle_l1_full_volume": full_oracle,
                "oracle_l1_schedule_order_cap": capped_oracle,
                "sell7_schedule_pnl": schedule_value,
                "gap_full_vs_schedule": full_oracle - schedule_value if pd.notna(schedule_value) else np.nan,
                "gap_capped_vs_schedule": capped_oracle - schedule_value if pd.notna(schedule_value) else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["dataset", "day", "product"])


def _schedule_product_pnl_lookup(schedule_pnl: pd.DataFrame) -> dict[tuple[str, int, str], float]:
    out: dict[tuple[str, int, str], float] = {}
    if schedule_pnl.empty:
        return out
    sell7 = schedule_pnl[schedule_pnl["variant"] == "sell7"]
    for row in sell7.itertuples(index=False):
        for product in SELL7_SCHEDULES:
            out[(row.dataset, int(row.day), product)] = float(getattr(row, f"{product}_pnl"))
    return out


def summarize_oracles(oracles: pd.DataFrame) -> pd.DataFrame:
    if oracles.empty:
        return pd.DataFrame()
    return (
        oracles.groupby(["dataset", "product"], sort=False)
        .agg(
            strike=("strike", "first"),
            oracle_full_mean=("oracle_l1_full_volume", "mean"),
            oracle_full_min=("oracle_l1_full_volume", "min"),
            oracle_capped_mean=("oracle_l1_schedule_order_cap", "mean"),
            sell7_pnl_mean=("sell7_schedule_pnl", "mean"),
            sell7_pnl_min=("sell7_schedule_pnl", "min"),
            gap_full_mean=("gap_full_vs_schedule", "mean"),
            gap_capped_mean=("gap_capped_vs_schedule", "mean"),
        )
        .reset_index()
        .sort_values(["dataset", "gap_full_mean"], ascending=[True, False])
    )


def official_actual_summary(books: dict[str, pd.DataFrame], trades_by_run: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, book in books.items():
        final = (
            book.sort_values("timestamp")
            .groupby("product", sort=False)
            .tail(1)
            .set_index("product")["profit_and_loss"]
        )
        trades = trades_by_run.get(name, pd.DataFrame())
        own = pd.DataFrame()
        if not trades.empty:
            own = trades[(trades["buyer"] == "SUBMISSION") | (trades["seller"] == "SUBMISSION")].copy()
            own["signed_qty"] = np.where(own["buyer"] == "SUBMISSION", own["quantity"], -own["quantity"])
        row = {"dataset": name, "total_final": float(final.sum())}
        for product in SELL7_SCHEDULES:
            row[f"{product}_pnl"] = float(final.get(product, 0.0))
            row[f"{product}_pos"] = int(own[own["symbol"] == product]["signed_qty"].sum()) if not own.empty else 0
            row[f"{product}_abs_qty"] = int(own[own["symbol"] == product]["quantity"].sum()) if not own.empty else 0
        rows.append(row)
    return pd.DataFrame(rows).sort_values("dataset")


def write_plots(options: pd.DataFrame, greeks: pd.DataFrame, out_dir: Path) -> None:
    hist = options[options["dataset"] == "historical"].copy()
    if not hist.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        for day, group in hist.groupby("day"):
            summary = group.groupby("strike")["iv"].median().dropna()
            ax.plot(summary.index, summary.values, marker="o", label=f"day {day}")
        ax.set_title("R4 VELVET Voucher Median IV Smile (live TTE=4 assumption)")
        ax.set_xlabel("Strike")
        ax.set_ylabel("Implied vol per day")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "iv_smile_by_day.png", dpi=150)
        plt.close(fig)

    sell7 = greeks[(greeks["variant"] == "sell7") & (greeks["dataset"] == "historical")]
    if not sell7.empty:
        fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
        for day, group in sell7.groupby("day"):
            group = group.sort_values("timestamp")
            axes[0].plot(group["timestamp"], group["net_delta"], label=f"day {day}")
            axes[1].plot(group["timestamp"], group["net_gamma"], label=f"day {day}")
            axes[2].plot(group["timestamp"], group["net_vega"], label=f"day {day}")
        axes[0].set_ylabel("Net delta")
        axes[1].set_ylabel("Net gamma")
        axes[2].set_ylabel("Net vega")
        axes[2].set_xlabel("Timestamp")
        axes[0].set_title("sell7 Historical Portfolio Greeks")
        for ax in axes:
            ax.grid(True, alpha=0.25)
            ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "sell7_historical_greeks.png", dpi=150)
        plt.close(fig)


def markdown_table(df: pd.DataFrame, *, max_rows: int = 30) -> str:
    if df.empty:
        return "_empty_"
    display = df.head(max_rows).copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.2f}")
    headers = [str(column) for column in display.columns]
    rows = [[str(value) for value in row] for row in display.to_numpy()]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def fmt(values: Iterable[str]) -> str:
        cells = list(values)
        return "| " + " | ".join(cells[i].ljust(widths[i]) for i in range(len(widths))) + " |"

    return "\n".join([fmt(headers), "| " + " | ".join("-" * width for width in widths) + " |", *(fmt(row) for row in rows)])


def write_report(
    doc_path: Path,
    out_dir: Path,
    option_summary: pd.DataFrame,
    schedule_summary: pd.DataFrame,
    trade_summary: pd.DataFrame,
    oracle_summary: pd.DataFrame,
    greeks: pd.DataFrame,
    official_summary: pd.DataFrame,
) -> None:
    hist_oracle = oracle_summary[oracle_summary["dataset"] == "historical"][
        [
            "product",
            "strike",
            "oracle_full_mean",
            "oracle_capped_mean",
            "sell7_pnl_mean",
            "gap_full_mean",
        ]
    ]
    official_oracle = oracle_summary[oracle_summary["dataset"].str.contains("official", na=False)][
        [
            "dataset",
            "product",
            "strike",
            "oracle_full_mean",
            "sell7_pnl_mean",
            "gap_full_mean",
        ]
    ]
    hist_options = option_summary[option_summary["dataset"] == "historical"][
        [
            "product",
            "strike",
            "mean_iv",
            "mean_iv_residual",
            "mean_price_residual",
            "mean_delta",
            "mean_gamma",
            "mean_vega",
            "iv_minus_rv_30000",
            "iv_minus_rv_100000",
        ]
    ]
    sell7_pnl = schedule_summary[
        (schedule_summary["variant"] == "sell7") & (schedule_summary["dataset"] == "historical")
    ][["day", "total_pnl", "max_drawdown", "first_ts_99pct"]]
    greek_summary = (
        greeks[(greeks["variant"] == "sell7") & (greeks["dataset"] == "historical")]
        .groupby("day")
        .agg(
            mean_delta=("net_delta", "mean"),
            min_delta=("net_delta", "min"),
            max_delta=("net_delta", "max"),
            mean_gamma=("net_gamma", "mean"),
            mean_vega=("net_vega", "mean"),
            max_gross_position=("gross_position", "max"),
        )
        .reset_index()
    )
    trade_focus = trade_summary[
        (trade_summary["variant"] == "sell7") & (trade_summary["dataset"] == "historical")
    ][
        [
            "product",
            "side",
            "qty",
            "end_raw_pnl",
            "avg_iv_residual",
            "avg_delta",
            "qty_edge_mid_30000",
            "qty_delta_hedged_30000",
            "qty_edge_mid_100000",
            "qty_delta_hedged_100000",
        ]
    ]

    text = f"""# Round 4 VELVET Option Complex Research

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_velvet_option_complex
```

Artifacts live under `{out_dir}`.

## Executive Decision Read

The current VELVET/voucher sleeve is profitable, but the evidence does not
support calling it a clean option-native gamma or smile strategy. It behaves
mostly like a static directional/regime and spread-capture book that happens to
hold options. Historical voucher fills often have positive raw mark-to-end PnL,
but their 30k and 100k delta-hedged markouts are mostly negative. That means
the book is being paid for spot/path exposure, execution against favorable
quotes, and terminal mark exposure more than for standalone volatility alpha.

The real official `sell7` upload confirms the narrow `VEV_5500` mechanism:
isolated VELVET/voucher PnL moves from `64,906.90` in `flat995`, to `65,941.36`
with `VEV_5500` disabled/sellonly, to `66,975.81` with validated bid-7 selling.
Full official JSON profit is `68,655.81` after adding the unchanged HYDROGEL
contribution. The `VEV_5500` leg itself flips from `-1,034.45` long, to `0`,
to `+1,034.45` short. That is a real upload improvement, but it is still a
terminal/spread calibration edge, not evidence for an aggressive wing-vol book.

## How To Capture The Edge

Capture this as a target-inventory controller, not as a looser collection of
price thresholds.

1. **Terminal/regime inventory:** explicitly aim for the proven terminal book:
   short `VELVETFRUIT_EXTRACT`, short deep-ITM `VEV_4000/4500`, long core
   `VEV_5000/5100/5200`, limited/opportunistic `VEV_5300/5400`, and short
   `VEV_5500` only when bid `>= 7`. This is the part the current static
   schedule already captures well.
2. **Spread capture:** keep using hard entry prices only where the book offers
   real edge versus robust mid/terminal mark. Do not pay for every IV residual.
   The official value is in crossing stale/favorable quotes early, then holding
   the right inventory.
3. **Dynamic capacity:** the hindsight gap says inventory is pinned too early,
   but the tested take-profit recycler failed. The next controller should
   reserve capacity unless the quote is both structurally cheap/rich and moves
   the portfolio toward the target Greek/inventory vector. Naive profit-taking
   is not enough.
4. **Reduce-only before refill:** first test reducing `VEV_5000/5100/5200` only
   when a strike is rich to smile, over target delta/vega, and has a replacement
   opportunity nearby. Refill logic should be gated separately; otherwise the
   strategy churns away terminal edge.
5. **Negative controls:** every recycler or smile package needs a same-frequency
   non-structural control. If the control performs similarly, the edge is path
   luck or generic churn.

## Method Notes

- This ignores the manual challenge and isolates `VELVETFRUIT_EXTRACT` plus
  `VEV_*`.
- IV/Greeks use Black-Scholes calls with live-equivalent TTE
  `4 - timestamp / 1_000_000` days. That is the live R4 TTE assumption; it is
  the right calibration target for uploads, even if historical public days may
  encode a different absolute calendar.
- Local schedule replay is top-of-book taker only, with the same static
  thresholds and limits as the current R4 candidates. It is evidence for
  structure, not a promise of official fills.
- Hindsight oracle is an independent-product L1 dynamic program with position
  limits and terminal mid marking. It is deliberately overfit and should be
  read as a ceiling diagnostic.

## Hindsight Opportunity

Historical mean by strike/product:

{markdown_table(hist_oracle, max_rows=20)}

Official 100k books:

{markdown_table(official_oracle, max_rows=80)}

## IV / Smile / Realized Vol

{markdown_table(hist_options, max_rows=20)}

## Current sell7 Schedule Replay

{markdown_table(sell7_pnl, max_rows=10)}

Portfolio Greek path:

{markdown_table(greek_summary, max_rows=10)}

## Fill Attribution

Historical sell7 schedule fills:

{markdown_table(trade_focus, max_rows=80)}

## Official Candidate Calibration

{markdown_table(official_summary, max_rows=20)}

## Provisional Research Read

1. The current schedule is not a clean gamma strategy. The Greek path swings
   between large long and short delta states while gamma/vega are mostly an
   accidental consequence of which strikes hit static price thresholds.
2. The schedule has real repeatable spread/regime capture in the local tapes,
   but the oracle gap remains large, especially in VELVET and the 5000-5200
   voucher region. That points to inventory-state and capacity value, not a
   need for blind wider thresholds.
3. IV/smile residuals are useful conditioners, not standalone upload rules.
   Treat them as filters on entry/reduction quality inside a target-position
   controller.
4. `VEV_5500 sell7` is a validated calibration upload. It should be preferred
   to `flat995`/disabled if we are sending this family, but it should not become
   an aggressive wing-vol sleeve.
5. The next upload after `sell7` should be a reduce-only core-voucher probe or
   an options-only diagnostic, not the failed naive recycler/gamma/smile probes.
"""
    doc_path.write_text(text)


def run(data_dir: Path, official_dir: Path, out_dir: Path, doc_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    print("Loading historical and official books...")
    historical = load_historical(data_dir)
    official_books, official_trades = load_official_books(official_dir)
    official_for_analysis = []
    for official_name in ("official_sellonly8", "official_disabled", "official_sell7_validated"):
        if official_name in official_books:
            official_for_analysis.append(official_books[official_name])
    all_prices = pd.concat([historical, *official_for_analysis], ignore_index=True)

    print("Computing realized volatility...")
    rv = compute_realized_vol(all_prices)

    runs: list[ScheduleRun] = []
    for label, schedules in schedule_variants().items():
        print(f"Replaying schedule variant: {label}")
        runs.append(simulate_schedule(all_prices, schedules=schedules, label=label))

    schedule_summary = pd.concat([summarize_pnl(run) for run in runs], ignore_index=True)
    all_trades = pd.concat([run.trades for run in runs], ignore_index=True)
    all_blocked = pd.concat([run.blocked for run in runs], ignore_index=True)
    all_paths = pd.concat([run.path for run in runs], ignore_index=True)

    feature_keys = {
        (str(row.dataset), int(row.day), int(row.timestamp))
        for row in all_trades.itertuples(index=False)
    }
    print("Computing sampled IV, Greeks, and smile residuals...")
    options = enrich_options(all_prices, rv, feature_keys=feature_keys, sample_interval=1_000)
    option_summary = summarize_options(options)

    enriched_trades = attach_forward_edges(all_trades, all_prices, options, rv)
    enriched_blocked = attach_blocked_edges(all_blocked, all_prices, options, rv)
    trade_summary = summarize_trades(enriched_trades)
    condition_summary = summarize_by_condition(enriched_trades)
    blocked_summary = summarize_trades(enriched_blocked)
    greeks = compute_portfolio_greeks(all_paths, options)

    print("Computing L1 hindsight oracles...")
    oracles = compute_oracles(
        all_prices[
            all_prices["dataset"].isin(
                ["historical", "official_sellonly8", "official_sell7_validated"]
            )
        ],
        schedule_summary,
        include_capped=False,
    )
    oracle_summary = summarize_oracles(oracles)
    official_summary = official_actual_summary(official_books, official_trades)

    historical.to_csv(out_dir / "historical_prices_normalized.csv", index=False)
    rv.to_csv(out_dir / "underlying_realized_vol.csv", index=False)
    options.to_csv(out_dir / "option_iv_greeks_smile.csv", index=False)
    option_summary.to_csv(out_dir / "option_summary_by_product.csv", index=False)
    schedule_summary.to_csv(out_dir / "schedule_variant_pnl_summary.csv", index=False)
    enriched_trades.to_csv(out_dir / "schedule_trades_with_greeks.csv", index=False)
    trade_summary.to_csv(out_dir / "schedule_trade_attribution.csv", index=False)
    condition_summary.to_csv(out_dir / "schedule_trade_attribution_by_condition.csv", index=False)
    enriched_blocked.to_csv(out_dir / "blocked_schedule_signals_with_greeks.csv", index=False)
    blocked_summary.to_csv(out_dir / "blocked_schedule_signal_summary.csv", index=False)
    greeks.to_csv(out_dir / "portfolio_greek_path.csv", index=False)
    oracles.to_csv(out_dir / "l1_hindsight_oracles_by_day.csv", index=False)
    oracle_summary.to_csv(out_dir / "l1_hindsight_oracle_summary.csv", index=False)
    official_summary.to_csv(out_dir / "official_candidate_actual_summary.csv", index=False)

    write_plots(options, greeks, out_dir)
    write_report(
        doc_path=doc_path,
        out_dir=out_dir,
        option_summary=option_summary,
        schedule_summary=schedule_summary,
        trade_summary=trade_summary,
        oracle_summary=oracle_summary,
        greeks=greeks,
        official_summary=official_summary,
    )

    print(f"Wrote outputs to {out_dir}")
    print(f"Wrote report to {doc_path}")
    print("\nTop historical oracle gaps:")
    cols = ["dataset", "product", "oracle_full_mean", "sell7_pnl_mean", "gap_full_mean"]
    print(oracle_summary[oracle_summary["dataset"] == "historical"][cols].head(12).to_string(index=False))
    print("\nSchedule summary:")
    print(schedule_summary[["variant", "dataset", "day", "total_pnl", "max_drawdown", "first_ts_99pct"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-dir", type=Path, default=DEFAULT_OFFICIAL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()
    run(args.data_dir, args.official_dir, args.out_dir, args.doc_path)


if __name__ == "__main__":
    main()
