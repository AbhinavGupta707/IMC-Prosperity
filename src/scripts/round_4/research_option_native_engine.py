"""Option-native VELVET/voucher research engine.

This is the missing Round-3 lesson applied to Round 4: test option families as
option portfolios, not as isolated price thresholds. The engine uses causal
EWMA-IV fair values, delta hedging with VELVET, explicit hedge cash, stale-quote
filters, and cross-strike packages.

It is offline research code, not a submission.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.options.bsm import BSMInputs, call_greeks, call_price
from src.scripts.round_4.test_core_recycler_probes import markdown_table


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEATURES = REPO_ROOT / "outputs" / "round_4" / "velvet_option_complex" / "option_iv_greeks_smile.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "option_native_engine"
DEFAULT_DOC = REPO_ROOT / "docs" / "round_4" / "OPTION_NATIVE_ENGINE_RESEARCH.md"

UNDERLYING = "VELVETFRUIT_EXTRACT"
OPTIONS = ("VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500")
OPTION_LIMIT = 300
UNDERLYING_LIMIT = 200


@dataclass(frozen=True)
class Config:
    label: str
    family: str
    products: tuple[str, ...] = ()
    legs: tuple[tuple[str, int], ...] = ()
    fair_source: str = "ewma"
    direction: str = "both"
    max_pos: int = 60
    max_order: int = 10
    entry_edge: float = 2.0
    exit_edge: float = 0.50
    delta_band: float = 35.0
    hedge_order: int = 40
    max_spread: float = 8.0
    stale_horizon: int | None = None
    stale_move: float = 0.0
    vol_edge: float | None = None
    flatten_buffer: int = 20_000


@dataclass
class Book:
    products: tuple[str, ...]
    cash: dict[str, float]
    pos: dict[str, int]
    trades: list[dict]
    peak: float = -float("inf")
    max_drawdown: float = 0.0

    @classmethod
    def create(cls, products: tuple[str, ...]) -> "Book":
        all_products = (UNDERLYING, *products)
        return cls(
            products=products,
            cash={product: 0.0 for product in all_products},
            pos={product: 0 for product in all_products},
            trades=[],
        )

    def limit(self, product: str) -> int:
        return UNDERLYING_LIMIT if product == UNDERLYING else OPTION_LIMIT

    def buy(self, dataset: str, day: int, ts: int, product: str, price: float, qty: int, reason: str) -> int:
        qty = max(0, int(qty))
        qty = min(qty, self.limit(product) - self.pos.get(product, 0))
        if qty <= 0:
            return 0
        self.cash[product] -= float(price) * qty
        self.pos[product] = self.pos.get(product, 0) + qty
        self.trades.append(_trade(dataset, day, ts, product, "buy", price, qty, reason, self.pos[product]))
        return qty

    def sell(self, dataset: str, day: int, ts: int, product: str, price: float, qty: int, reason: str) -> int:
        qty = max(0, int(qty))
        qty = min(qty, self.limit(product) + self.pos.get(product, 0))
        if qty <= 0:
            return 0
        self.cash[product] += float(price) * qty
        self.pos[product] = self.pos.get(product, 0) - qty
        self.trades.append(_trade(dataset, day, ts, product, "sell", price, qty, reason, self.pos[product]))
        return qty

    def mark(self, mids: dict[str, float]) -> float:
        return float(sum(self.cash[p] + self.pos.get(p, 0) * mids.get(p, 0.0) for p in self.cash))

    def observe(self, pnl: float) -> float:
        self.peak = max(self.peak, pnl)
        self.max_drawdown = min(self.max_drawdown, pnl - self.peak)
        return self.max_drawdown


def _trade(dataset: str, day: int, ts: int, product: str, side: str, price: float, qty: int, reason: str, pos_after: int) -> dict:
    return {
        "dataset": dataset,
        "day": int(day),
        "timestamp": int(ts),
        "product": product,
        "side": side,
        "price": float(price),
        "qty": int(qty),
        "reason": reason,
        "pos_after": int(pos_after),
    }


def configs(include_packages: bool = False) -> list[Config]:
    core = ("VEV_5000", "VEV_5100", "VEV_5200")
    single_configs = [
        Config("single_ewma_core_both_e025", "single", core, direction="both", entry_edge=0.25, exit_edge=0.05, max_pos=35, max_order=5),
        Config("single_ewma_core_long_e025", "single", core, direction="long", entry_edge=0.25, exit_edge=0.05, max_pos=35, max_order=5),
        Config("single_ewma_core_both_e2", "single", core, direction="both", entry_edge=2.0, max_pos=50, max_order=8),
        Config("single_ewma_core_long_e2", "single", core, direction="long", entry_edge=2.0, max_pos=50, max_order=8, vol_edge=0.002),
        Config("single_ewma_mid_short_e025", "single", ("VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"), direction="short", entry_edge=0.25, exit_edge=0.05, max_pos=35, max_order=5, max_spread=4.0),
        Config("single_ewma_stale_core_long_m4_e1", "single", core, direction="long", entry_edge=1.0, max_pos=50, max_order=8, stale_horizon=5_000, stale_move=4.0),
        Config("single_ewma_stale_core_both_m4_e1", "single", core, direction="both", entry_edge=1.0, max_pos=40, max_order=8, stale_horizon=5_000, stale_move=4.0),
        Config("single_smile_core_long_e05", "single", ("VEV_5000", "VEV_5100", "VEV_5200"), fair_source="smile", direction="long", entry_edge=0.50, exit_edge=0.10, max_pos=35, max_order=5),
        Config("single_smile_rich_5300_5500_short_e1", "single", ("VEV_5300", "VEV_5500"), fair_source="smile", direction="short", entry_edge=1.0, max_pos=40, max_order=8, max_spread=4.0),
    ]
    if not include_packages:
        return single_configs
    return [
        *single_configs,
        Config("vertical_5000_5100_ewma_e025", "package", legs=(("VEV_5000", 1), ("VEV_5100", -1)), entry_edge=0.25, exit_edge=0.05, max_pos=30, max_order=5),
        Config("vertical_5100_5200_ewma_e025", "package", legs=(("VEV_5100", 1), ("VEV_5200", -1)), entry_edge=0.25, exit_edge=0.05, max_pos=30, max_order=5),
        Config("vertical_5000_5100_ewma_e2", "package", legs=(("VEV_5000", 1), ("VEV_5100", -1)), entry_edge=2.0, max_pos=40, max_order=8),
        Config("vertical_5100_5200_ewma_e2", "package", legs=(("VEV_5100", 1), ("VEV_5200", -1)), entry_edge=2.0, max_pos=40, max_order=8),
        Config("vertical_5200_5300_ewma_e2", "package", legs=(("VEV_5200", 1), ("VEV_5300", -1)), entry_edge=2.0, max_pos=40, max_order=8),
        Config("vertical_5000_5200_ewma_e3", "package", legs=(("VEV_5000", 1), ("VEV_5200", -1)), entry_edge=3.0, max_pos=35, max_order=7),
        Config("butterfly_5000_5100_5200_ewma_e05", "package", legs=(("VEV_5000", 1), ("VEV_5100", -2), ("VEV_5200", 1)), entry_edge=0.50, exit_edge=0.10, max_pos=20, max_order=4, delta_band=25.0),
        Config("butterfly_5000_5100_5200_ewma_e2", "package", legs=(("VEV_5000", 1), ("VEV_5100", -2), ("VEV_5200", 1)), entry_edge=2.0, max_pos=25, max_order=5, delta_band=25.0),
        Config("butterfly_5100_5200_5300_ewma_e2", "package", legs=(("VEV_5100", 1), ("VEV_5200", -2), ("VEV_5300", 1)), entry_edge=2.0, max_pos=25, max_order=5, delta_band=25.0),
    ]


def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["timestamp"].mod(1_000).eq(0)].copy()
    numeric = [
        "day",
        "timestamp",
        "strike",
        "spot_mid",
        "spot_bid",
        "spot_ask",
        "tte",
        "bid",
        "ask",
        "mid",
        "spread",
        "iv",
        "fair_price",
        "delta",
        "rv_back_30000",
    ]
    for col in numeric:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["product"].isin(OPTIONS)].copy()
    df = df.sort_values(["dataset", "day", "product", "timestamp"]).reset_index(drop=True)
    return _add_causal_fair(_add_path_features(df))


def _add_path_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for horizon in (1_000, 5_000, 10_000):
        steps = max(1, horizon // 1_000)
        out[f"spot_move_{horizon}"] = out.groupby(["dataset", "day", "product"])["spot_mid"].diff(steps)
    return out


def _add_causal_fair(df: pd.DataFrame, halflife: float = 40.0, warmup: int = 20) -> pd.DataFrame:
    alpha = 1.0 - 0.5 ** (1.0 / halflife)
    frames = []
    for (_dataset, _day, _product), group in df.groupby(["dataset", "day", "product"], sort=False):
        group = group.sort_values("timestamp").copy()
        ewma_values: list[float] = []
        counts: list[int] = []
        ewma = np.nan
        count = 0
        for iv in group["iv"].to_numpy(dtype=float):
            ewma_values.append(ewma)
            counts.append(count)
            if math.isfinite(iv) and 0.001 <= iv <= 0.50:
                ewma = iv if not math.isfinite(ewma) else alpha * iv + (1.0 - alpha) * ewma
                count += 1
        group["ewma_iv"] = ewma_values
        group["ewma_count"] = counts
        group["fair_ewma"] = np.nan
        group["delta_ewma"] = np.nan
        valid = group["ewma_count"].ge(warmup) & group["ewma_iv"].between(0.001, 0.50)
        fair = []
        delta = []
        for idx, row in group.iterrows():
            if not bool(valid.loc[idx]):
                fair.append(np.nan)
                delta.append(np.nan)
                continue
            try:
                inputs = BSMInputs(
                    spot=float(row["spot_mid"]),
                    strike=float(row["strike"]),
                    time_to_expiry=float(row["tte"]),
                    volatility=float(row["ewma_iv"]),
                )
                fair.append(float(call_price(inputs)))
                delta.append(float(call_greeks(inputs).delta))
            except (ValueError, OverflowError, ZeroDivisionError):
                fair.append(np.nan)
                delta.append(np.nan)
        group["fair_ewma"] = fair
        group["delta_ewma"] = delta
        frames.append(group)
    return pd.concat(frames, ignore_index=True).sort_values(["dataset", "day", "timestamp", "product"]).reset_index(drop=True)


def _fair(row: pd.Series, cfg: Config) -> tuple[float, float]:
    if cfg.fair_source == "smile":
        return float(row["fair_price"]), float(row["delta"])
    return float(row["fair_ewma"]), float(row["delta_ewma"])


def _feature_active(row: pd.Series, cfg: Config, side: str) -> bool:
    if pd.isna(row["bid"]) or pd.isna(row["ask"]) or pd.isna(row["mid"]):
        return False
    if float(row["spread"]) > cfg.max_spread:
        return False
    fair, _delta = _fair(row, cfg)
    if not math.isfinite(fair):
        return False
    if cfg.vol_edge is not None and side == "buy":
        iv = float(row["iv"]) if pd.notna(row["iv"]) else np.nan
        rv = float(row["rv_back_30000"]) if pd.notna(row["rv_back_30000"]) else np.nan
        if not (math.isfinite(iv) and math.isfinite(rv) and rv - iv >= cfg.vol_edge):
            return False
    if cfg.stale_horizon is not None:
        move = float(row.get(f"spot_move_{cfg.stale_horizon}", np.nan))
        if side == "buy" and not (math.isfinite(move) and move >= cfg.stale_move):
            return False
        if side == "sell" and not (math.isfinite(move) and move <= -cfg.stale_move):
            return False
    return True


def _net_delta(book: Book, rows: pd.DataFrame, cfg: Config) -> float:
    total = float(book.pos.get(UNDERLYING, 0))
    for row in rows.itertuples(index=False):
        product = str(row.product)
        pos = book.pos.get(product, 0)
        if pos == 0:
            continue
        delta = getattr(row, "delta_ewma") if cfg.fair_source == "ewma" else getattr(row, "delta")
        if pd.notna(delta):
            total += pos * float(delta)
    return total


def _hedge(book: Book, dataset: str, day: int, ts: int, rows: pd.DataFrame, cfg: Config) -> None:
    if rows.empty:
        return
    delta = _net_delta(book, rows, cfg)
    first = rows.iloc[0]
    if abs(delta) <= cfg.delta_band:
        return
    if delta > cfg.delta_band and pd.notna(first["spot_bid"]):
        qty = min(cfg.hedge_order, int(math.ceil(delta - cfg.delta_band)))
        book.sell(dataset, day, ts, UNDERLYING, float(first["spot_bid"]), qty, "delta_hedge")
    elif delta < -cfg.delta_band and pd.notna(first["spot_ask"]):
        qty = min(cfg.hedge_order, int(math.ceil(-delta - cfg.delta_band)))
        book.buy(dataset, day, ts, UNDERLYING, float(first["spot_ask"]), qty, "delta_hedge")


def _flatten_options(book: Book, dataset: str, day: int, ts: int, rows: pd.DataFrame, cfg: Config) -> None:
    by_product = {str(row.product): row for row in rows.itertuples(index=False)}
    for product in book.products:
        pos = book.pos.get(product, 0)
        row = by_product.get(product)
        if row is None or pos == 0:
            continue
        if pos > 0 and pd.notna(row.bid):
            book.sell(dataset, day, ts, product, float(row.bid), min(cfg.max_order, pos), "flatten")
        elif pos < 0 and pd.notna(row.ask):
            book.buy(dataset, day, ts, product, float(row.ask), min(cfg.max_order, -pos), "flatten")
    first = rows.iloc[0] if not rows.empty else None
    if first is not None:
        upos = book.pos.get(UNDERLYING, 0)
        if upos > 0 and pd.notna(first["spot_bid"]):
            book.sell(dataset, day, ts, UNDERLYING, float(first["spot_bid"]), min(cfg.hedge_order, upos), "flatten_hedge")
        elif upos < 0 and pd.notna(first["spot_ask"]):
            book.buy(dataset, day, ts, UNDERLYING, float(first["spot_ask"]), min(cfg.hedge_order, -upos), "flatten_hedge")


def simulate(features: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    products = cfg.products if cfg.family == "single" else tuple(product for product, _coef in cfg.legs)
    trade_rows: list[dict] = []
    pnl_rows: list[dict] = []
    subset = features[features["product"].isin(products)].copy()
    for (dataset, day), day_df in subset.groupby(["dataset", "day"], sort=False):
        book = Book.create(products)
        package_pos = 0
        end_ts = int(day_df["timestamp"].max())
        flatten_start = max(0, end_ts - cfg.flatten_buffer)
        for ts, rows in day_df.groupby("timestamp", sort=True):
            ts = int(ts)
            rows = rows.sort_values("product").copy()
            mids = {UNDERLYING: float(rows.iloc[0]["spot_mid"])}
            mids.update({str(row.product): float(row.mid) for row in rows.itertuples(index=False)})

            if ts >= flatten_start:
                _flatten_options(book, str(dataset), int(day), ts, rows, cfg)
            elif cfg.family == "single":
                _trade_single(book, str(dataset), int(day), ts, rows, cfg)
            else:
                package_pos = _trade_package(book, str(dataset), int(day), ts, rows, cfg, package_pos)

            _hedge(book, str(dataset), int(day), ts, rows, cfg)
            pnl = book.mark(mids)
            dd = book.observe(pnl)
            pnl_rows.append(
                {
                    "variant": cfg.label,
                    "dataset": dataset,
                    "day": int(day),
                    "timestamp": ts,
                    "total_pnl": pnl,
                    "drawdown": dd,
                    "net_delta": _net_delta(book, rows, cfg),
                    "package_pos": int(package_pos),
                    **{f"pos_{product}": book.pos.get(product, 0) for product in (UNDERLYING, *products)},
                }
            )
        trade_rows.extend({**row, "variant": cfg.label} for row in book.trades)
    return pd.DataFrame(trade_rows), pd.DataFrame(pnl_rows)


def _trade_single(book: Book, dataset: str, day: int, ts: int, rows: pd.DataFrame, cfg: Config) -> None:
    for _, row in rows.iterrows():
        product = str(row["product"])
        pos = book.pos.get(product, 0)
        fair, _delta = _fair(row, cfg)
        if not math.isfinite(fair):
            continue
        buy_edge = fair - float(row["ask"])
        sell_edge = float(row["bid"]) - fair
        can_buy = cfg.direction in {"both", "long"} and _feature_active(row, cfg, "buy")
        can_sell = cfg.direction in {"both", "short"} and _feature_active(row, cfg, "sell")
        if can_buy and buy_edge >= cfg.entry_edge and pos < cfg.max_pos:
            qty = min(cfg.max_order, cfg.max_pos - pos)
            book.buy(dataset, day, ts, product, float(row["ask"]), qty, "option_fair_buy")
        elif can_sell and sell_edge >= cfg.entry_edge and pos > -cfg.max_pos:
            qty = min(cfg.max_order, cfg.max_pos + pos)
            book.sell(dataset, day, ts, product, float(row["bid"]), qty, "option_fair_sell")
        elif pos > 0 and (buy_edge <= cfg.exit_edge or cfg.direction == "short"):
            book.sell(dataset, day, ts, product, float(row["bid"]), min(cfg.max_order, pos), "option_exit")
        elif pos < 0 and (sell_edge <= cfg.exit_edge or cfg.direction == "long"):
            book.buy(dataset, day, ts, product, float(row["ask"]), min(cfg.max_order, -pos), "option_exit")


def _package_values(rows: pd.DataFrame, cfg: Config) -> tuple[float, float, float, float, float] | None:
    by_product = {str(row.product): row for row in rows.itertuples(index=False)}
    fair_value = 0.0
    long_cost = 0.0
    short_credit = 0.0
    package_delta = 0.0
    max_spread = 0.0
    for product, coef in cfg.legs:
        row = by_product.get(product)
        if row is None or pd.isna(row.bid) or pd.isna(row.ask):
            return None
        fair = float(getattr(row, "fair_ewma") if cfg.fair_source == "ewma" else getattr(row, "fair_price"))
        delta = float(getattr(row, "delta_ewma") if cfg.fair_source == "ewma" else getattr(row, "delta"))
        if not (math.isfinite(fair) and math.isfinite(delta)):
            return None
        bid = float(row.bid)
        ask = float(row.ask)
        spread = float(row.spread)
        if spread > cfg.max_spread:
            return None
        fair_value += coef * fair
        package_delta += coef * delta
        max_spread = max(max_spread, spread)
        if coef > 0:
            long_cost += coef * ask
            short_credit += coef * bid
        else:
            long_cost += coef * bid
            short_credit += coef * ask
    buy_edge = fair_value - long_cost
    sell_edge = short_credit - fair_value
    return fair_value, long_cost, short_credit, buy_edge, sell_edge


def _trade_package(book: Book, dataset: str, day: int, ts: int, rows: pd.DataFrame, cfg: Config, package_pos: int) -> int:
    values = _package_values(rows, cfg)
    if values is None:
        return package_pos
    _fair_value, _long_cost, _short_credit, buy_edge, sell_edge = values
    if buy_edge >= cfg.entry_edge and package_pos < cfg.max_pos:
        qty = min(cfg.max_order, cfg.max_pos - package_pos, _package_capacity(book, cfg, side=1))
        _execute_package(book, dataset, day, ts, rows, cfg, side=1, qty=qty, reason="package_buy")
        package_pos += qty
    elif sell_edge >= cfg.entry_edge and package_pos > -cfg.max_pos:
        qty = min(cfg.max_order, cfg.max_pos + package_pos, _package_capacity(book, cfg, side=-1))
        _execute_package(book, dataset, day, ts, rows, cfg, side=-1, qty=qty, reason="package_sell")
        package_pos -= qty
    elif package_pos > 0 and buy_edge <= cfg.exit_edge:
        qty = min(cfg.max_order, package_pos, _package_capacity(book, cfg, side=-1))
        _execute_package(book, dataset, day, ts, rows, cfg, side=-1, qty=qty, reason="package_exit")
        package_pos -= qty
    elif package_pos < 0 and sell_edge <= cfg.exit_edge:
        qty = min(cfg.max_order, -package_pos, _package_capacity(book, cfg, side=1))
        _execute_package(book, dataset, day, ts, rows, cfg, side=1, qty=qty, reason="package_exit")
        package_pos += qty
    return package_pos


def _package_capacity(book: Book, cfg: Config, side: int) -> int:
    cap = cfg.max_order
    for product, coef in cfg.legs:
        signed = side * coef
        if signed > 0:
            cap = min(cap, (OPTION_LIMIT - book.pos.get(product, 0)) // abs(coef))
        else:
            cap = min(cap, (OPTION_LIMIT + book.pos.get(product, 0)) // abs(coef))
    return max(0, int(cap))


def _execute_package(book: Book, dataset: str, day: int, ts: int, rows: pd.DataFrame, cfg: Config, *, side: int, qty: int, reason: str) -> None:
    if qty <= 0:
        return
    by_product = {str(row.product): row for row in rows.itertuples(index=False)}
    for product, coef in cfg.legs:
        row = by_product[product]
        signed = side * coef * qty
        if signed > 0:
            book.buy(dataset, day, ts, product, float(row.ask), signed, reason)
        elif signed < 0:
            book.sell(dataset, day, ts, product, float(row.bid), -signed, reason)


def summarize(trades: pd.DataFrame, pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        last = group.sort_values("timestamp").iloc[-1]
        own = trades[(trades["variant"].eq(variant)) & (trades["dataset"].eq(dataset)) & (trades["day"].eq(day))]
        option_trades = own[own["product"].ne(UNDERLYING)] if not own.empty else own
        hedge_trades = own[own["product"].eq(UNDERLYING)] if not own.empty else own
        rows.append(
            {
                "variant": variant,
                "dataset": dataset,
                "day": int(day),
                "total_pnl": float(last["total_pnl"]),
                "max_drawdown": float(group["drawdown"].min()),
                "max_abs_delta": float(group["net_delta"].abs().max()),
                "end_delta": float(last["net_delta"]),
                "trade_rows": int(len(own)),
                "option_rows": int(len(option_trades)),
                "hedge_rows": int(len(hedge_trades)),
                "abs_qty": int(own["qty"].sum()) if not own.empty else 0,
            }
        )
    return pd.DataFrame(rows)


def summarize_windows(pnl: pd.DataFrame, trades: pd.DataFrame, window: int = 100_000, step: int = 25_000) -> pd.DataFrame:
    rows = []
    for (variant, dataset, day), group in pnl.groupby(["variant", "dataset", "day"], sort=False):
        group = group.sort_values("timestamp")
        own = trades[(trades["variant"].eq(variant)) & (trades["dataset"].eq(dataset)) & (trades["day"].eq(day))]
        max_ts = int(group["timestamp"].max())
        for start in range(0, max_ts - window + 1, step):
            end = start + window
            before = group[group["timestamp"] <= start]
            after = group[group["timestamp"] <= end]
            if before.empty or after.empty:
                continue
            active = not own[(own["timestamp"] >= start) & (own["timestamp"] < end)].empty
            rows.append(
                {
                    "variant": variant,
                    "dataset": dataset,
                    "day": int(day),
                    "start": int(start),
                    "pnl_delta": float(after.iloc[-1]["total_pnl"] - before.iloc[-1]["total_pnl"]),
                    "active": bool(active),
                }
            )
    detail = pd.DataFrame(rows)
    if detail.empty:
        return pd.DataFrame()
    summary_rows = []
    for variant, group in detail.groupby("variant", sort=False):
        active = group[group["active"]]
        eval_group = active if not active.empty else group
        summary_rows.append(
            {
                "variant": variant,
                "windows": int(len(group)),
                "active_windows": int(len(active)),
                "active_rate": float(len(active) / len(group)),
                "all_mean_delta": float(group["pnl_delta"].mean()),
                "all_hit_rate": float((group["pnl_delta"] > 0).mean()),
                "active_mean_delta": float(eval_group["pnl_delta"].mean()),
                "active_hit_rate": float((eval_group["pnl_delta"] > 0).mean()),
                "active_p10_delta": float(eval_group["pnl_delta"].quantile(0.10)),
                "active_min_delta": float(eval_group["pnl_delta"].min()),
                "active_max_delta": float(eval_group["pnl_delta"].max()),
            }
        )
    return pd.DataFrame(summary_rows).sort_values(["active_mean_delta", "all_mean_delta"], ascending=False)


def single_leg_edge_screen(features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    enriched = _attach_single_future(features)
    thresholds = (0.0, 0.25, 0.50, 1.0, 2.0)
    stale_moves = (None, 4.0)
    for source, fair_col, delta_col in (("ewma", "fair_ewma", "delta_ewma"), ("smile", "fair_price", "delta")):
        if fair_col not in enriched:
            continue
        base = enriched[enriched[fair_col].notna()].copy()
        base["buy_edge"] = base[fair_col] - base["ask"]
        base["sell_edge"] = base["bid"] - base[fair_col]
        for side in ("buy", "sell"):
            edge_col = f"{side}_edge"
            for threshold in thresholds:
                for stale_move in stale_moves:
                    mask = base[edge_col] >= threshold
                    if stale_move is not None:
                        if side == "buy":
                            mask &= base["spot_move_5000"] >= stale_move
                        else:
                            mask &= base["spot_move_5000"] <= -stale_move
                    selected = base[mask].copy()
                    if selected.empty:
                        continue
                    for dataset_scope, scope_df in (("all", selected), ("historical", selected[selected["dataset"].eq("historical")]), ("official", selected[selected["dataset"].str.contains("official", na=False)])):
                        if scope_df.empty:
                            continue
                        row = {
                            "source": source,
                            "side": side,
                            "dataset_scope": dataset_scope,
                            "threshold": threshold,
                            "stale_move_5k": stale_move if stale_move is not None else np.nan,
                            "events": int(len(scope_df)),
                            "mean_edge": float(scope_df[edge_col].mean()),
                        }
                        for horizon in (10_000, 30_000, 100_000):
                            pnl_col = _single_touch_pnl(scope_df, side, delta_col, horizon)
                            row[f"mean_touch_pnl_{horizon}"] = float(pnl_col.mean(skipna=True))
                            row[f"hit_touch_{horizon}"] = float((pnl_col > 0).mean())
                        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["dataset_scope", "mean_touch_pnl_30000", "events"], ascending=[True, False, False])


def single_leg_edge_screen_by_product(features: pd.DataFrame, min_events: int = 5) -> pd.DataFrame:
    rows = []
    enriched = _attach_single_future(features)
    thresholds = (0.0, 0.25, 0.50, 1.0, 2.0)
    for source, fair_col, delta_col in (("ewma", "fair_ewma", "delta_ewma"), ("smile", "fair_price", "delta")):
        if fair_col not in enriched:
            continue
        base = enriched[enriched[fair_col].notna()].copy()
        base["buy_edge"] = base[fair_col] - base["ask"]
        base["sell_edge"] = base["bid"] - base[fair_col]
        for side in ("buy", "sell"):
            edge_col = f"{side}_edge"
            pnl_col = _single_touch_pnl(base, side, delta_col, 30_000)
            base_with_pnl = base.assign(touch_pnl_30000=pnl_col)
            for threshold in thresholds:
                selected = base_with_pnl[base_with_pnl[edge_col] >= threshold]
                if selected.empty:
                    continue
                scopes = (
                    ("all", selected),
                    ("historical", selected[selected["dataset"].eq("historical")]),
                    ("official", selected[selected["dataset"].str.contains("official", na=False)]),
                )
                for dataset_scope, scope_df in scopes:
                    if scope_df.empty:
                        continue
                    for product, product_df in scope_df.groupby("product", sort=False):
                        if len(product_df) < min_events:
                            continue
                        rows.append(
                            {
                                "source": source,
                                "side": side,
                                "dataset_scope": dataset_scope,
                                "threshold": threshold,
                                "product": product,
                                "events": int(len(product_df)),
                                "mean_edge": float(product_df[edge_col].mean()),
                                "mean_touch_pnl_30000": float(product_df["touch_pnl_30000"].mean(skipna=True)),
                                "hit_touch_30000": float((product_df["touch_pnl_30000"] > 0).mean()),
                            }
                        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["dataset_scope", "mean_touch_pnl_30000", "events"], ascending=[True, False, False])


def _attach_single_future(features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    for horizon in (10_000, 30_000, 100_000):
        steps = max(1, horizon // 1_000)
        for col in ("bid", "ask", "mid", "spot_bid", "spot_ask", "spot_mid"):
            out[f"{col}_fwd_{horizon}"] = out.groupby(["dataset", "day", "product"])[col].shift(-steps)
    return out


def _single_touch_pnl(df: pd.DataFrame, side: str, delta_col: str, horizon: int) -> pd.Series:
    delta = pd.to_numeric(df[delta_col], errors="coerce").fillna(0.0)
    if side == "buy":
        option_pnl = df[f"bid_fwd_{horizon}"] - df["ask"]
        hedge_pnl = delta * (df["spot_bid"] - df[f"spot_ask_fwd_{horizon}"])
    else:
        option_pnl = df["bid"] - df[f"ask_fwd_{horizon}"]
        hedge_pnl = delta * (df[f"spot_bid_fwd_{horizon}"] - df["spot_ask"])
    return option_pnl + hedge_pnl


def package_edge_screen(features: pd.DataFrame) -> pd.DataFrame:
    package_cfgs = [cfg for cfg in configs(include_packages=True) if cfg.family == "package"]
    rows = []
    lookup = {
        (str(row.dataset), int(row.day), int(row.timestamp), str(row.product)): row._asdict()
        for row in features.itertuples(index=False)
    }
    for cfg in package_cfgs:
        products = tuple(product for product, _coef in cfg.legs)
        anchors = features[features["product"].eq(products[0])][["dataset", "day", "timestamp"]].drop_duplicates()
        for anchor in anchors.itertuples(index=False):
            dataset = str(anchor.dataset)
            day = int(anchor.day)
            ts = int(anchor.timestamp)
            current_rows = [lookup.get((dataset, day, ts, product)) for product in products]
            if any(row is None for row in current_rows):
                continue
            group = pd.DataFrame(current_rows)
            current = _package_values(group, cfg)
            if current is None:
                continue
            _fair, _cost, _credit, buy_edge, sell_edge = current
            for horizon in (10_000, 30_000, 100_000):
                future_rows = [lookup.get((dataset, day, ts + horizon, product)) for product in products]
                if any(row is None for row in future_rows):
                    continue
                future = pd.DataFrame(future_rows)
                long_pnl = _package_touch_pnl(group, future, cfg, side=1)
                short_pnl = _package_touch_pnl(group, future, cfg, side=-1)
                rows.append(
                    {
                        "variant": cfg.label,
                        "dataset": dataset,
                        "day": int(day),
                        "timestamp": int(ts),
                        "horizon": horizon,
                        "buy_edge": float(buy_edge),
                        "sell_edge": float(sell_edge),
                        "long_touch_pnl": float(long_pnl),
                        "short_touch_pnl": float(short_pnl),
                    }
                )
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail
    summary_rows = []
    thresholds = (0.0, 0.25, 0.50, 1.0, 2.0)
    for (variant, horizon), group in detail.groupby(["variant", "horizon"], sort=False):
        for side, edge_col, pnl_col in (("long", "buy_edge", "long_touch_pnl"), ("short", "sell_edge", "short_touch_pnl")):
            for threshold in thresholds:
                selected = group[group[edge_col] >= threshold]
                if selected.empty:
                    continue
                for scope, scope_df in (("all", selected), ("historical", selected[selected["dataset"].eq("historical")]), ("official", selected[selected["dataset"].str.contains("official", na=False)])):
                    if scope_df.empty:
                        continue
                    summary_rows.append(
                        {
                            "variant": variant,
                            "side": side,
                            "dataset_scope": scope,
                            "horizon": int(horizon),
                            "threshold": threshold,
                            "events": int(len(scope_df)),
                            "mean_edge": float(scope_df[edge_col].mean()),
                            "mean_touch_pnl": float(scope_df[pnl_col].mean()),
                            "hit_touch": float((scope_df[pnl_col] > 0).mean()),
                        }
                    )
    out = pd.DataFrame(summary_rows)
    if out.empty:
        return out
    return out.sort_values(["dataset_scope", "horizon", "mean_touch_pnl"], ascending=[True, True, False])


def _package_touch_pnl(current: pd.DataFrame, future: pd.DataFrame, cfg: Config, side: int) -> float:
    cur = {str(row.product): row for row in current.itertuples(index=False)}
    fut = {str(row.product): row for row in future.itertuples(index=False)}
    option_pnl = 0.0
    package_delta = 0.0
    for product, coef in cfg.legs:
        c = cur[product]
        f = fut[product]
        signed = side * coef
        delta = float(getattr(c, "delta_ewma") if cfg.fair_source == "ewma" else getattr(c, "delta"))
        package_delta += signed * delta
        if signed > 0:
            option_pnl += signed * (float(f.bid) - float(c.ask))
        else:
            option_pnl += -signed * (float(c.bid) - float(f.ask))
    first_cur = current.iloc[0]
    first_fut = future.iloc[0]
    hedge_units = -package_delta
    if hedge_units > 0:
        hedge_pnl = hedge_units * (float(first_fut["spot_bid"]) - float(first_cur["spot_ask"]))
    else:
        hedge_pnl = -hedge_units * (float(first_cur["spot_bid"]) - float(first_fut["spot_ask"]))
    return option_pnl + hedge_pnl


def write_report(
    doc: Path,
    out_dir: Path,
    summary: pd.DataFrame,
    window_summary: pd.DataFrame,
    trades: pd.DataFrame,
    single_edges: pd.DataFrame,
    product_edges: pd.DataFrame,
    package_edges: pd.DataFrame,
    package_edge_screen_enabled: bool,
) -> None:
    hist = summary[summary["dataset"].eq("historical")]
    official = summary[summary["dataset"].str.contains("official", na=False)]
    hist_rank = (
        hist.groupby("variant", sort=False)
        .agg(
            mean_total=("total_pnl", "mean"),
            min_total=("total_pnl", "min"),
            mean_drawdown=("max_drawdown", "mean"),
            max_abs_delta=("max_abs_delta", "max"),
            mean_option_rows=("option_rows", "mean"),
            mean_hedge_rows=("hedge_rows", "mean"),
        )
        .reset_index()
        .sort_values(["mean_total", "min_total"], ascending=False)
    )
    trade_reasons = (
        trades.groupby(["variant", "product", "reason"], sort=False)
        .agg(rows=("qty", "count"), qty=("qty", "sum"), avg_price=("price", "mean"))
        .reset_index()
        .sort_values(["variant", "product", "reason"])
        if not trades.empty
        else pd.DataFrame()
    )
    promoted = hist_rank[(hist_rank["mean_total"] > 0) & (hist_rank["min_total"] > 0)]
    decision = "No standalone option-native family cleared the promotion gate." if promoted.empty else f"Positive standalone families: {', '.join(promoted['variant'].tolist())}."
    text = f"""# Option-Native VELVET Engine Research

Generated by:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.research_option_native_engine
```

Artifacts live under `{out_dir}`.

## Question

Does the R4 VELVET/voucher complex contain robust option-native alpha from
delta-hedged gamma, stale option quotes after spot moves, or cross-strike
packages?

## Decision

{decision}

This is a standalone family test. A positive standalone result would still need
an integration test against `sell7` capacity because the current schedule often
uses the same strike limits.

## Historical Standalone PnL

{markdown_table(hist_rank, max_rows=80)}

## Single-Leg Edge Markouts

These rows ask: if the model says the executable touch is cheap/rich by at
least the threshold, what is the conservative delta-hedged touch-to-touch PnL?

{markdown_table(single_edges.head(80), max_rows=80)}

## Strike-Level Edge Markouts

This is the check for hidden strike-specific edge. Positive model residuals
would be interesting only if at least one strike has positive touch-to-touch PnL
after paying the spread and delta hedge.

{markdown_table(product_edges.head(80), max_rows=80)}

## Package Edge Markouts

Verticals and butterflies are entered at touch, exited at future touch, and
delta-hedged with VELVET touch prices.

Package edge screen enabled: `{package_edge_screen_enabled}`.

{markdown_table(package_edges.head(80), max_rows=80)}

## Public 100k Window Distribution

{markdown_table(window_summary, max_rows=80)}

## Official 100k Proxy / Calibration

{markdown_table(official.sort_values(["dataset", "total_pnl"], ascending=[True, False]), max_rows=120)}

## Trade Reason Summary

{markdown_table(trade_reasons, max_rows=160)}

## Read

The engine is materially closer to the R3 playbook than the first gamma/smile
probe: fair values are causal EWMA-IV or cross-sectional smile, option entries
pay the touch, VELVET hedge cash is explicit, and package legs are traded as
verticals/butterflies. If this still fails across public days and windows, the
burden of proof for pure option-native alpha becomes much higher.
"""
    doc.write_text(text)


def run(
    features_path: Path,
    out_dir: Path,
    doc: Path,
    *,
    include_packages: bool = False,
    package_edge_screen_enabled: bool = False,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    features = load_features(features_path)
    all_trades = []
    all_pnl = []
    for cfg in configs(include_packages=include_packages):
        print(f"running {cfg.label}", flush=True)
        trades, pnl = simulate(features, cfg)
        all_trades.append(trades)
        all_pnl.append(pnl)
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    pnl = pd.concat(all_pnl, ignore_index=True) if all_pnl else pd.DataFrame()
    summary = summarize(trades, pnl)
    window_summary = summarize_windows(pnl, trades)
    single_edges = single_leg_edge_screen(features)
    product_edges = single_leg_edge_screen_by_product(features)
    package_edges = package_edge_screen(features) if package_edge_screen_enabled else pd.DataFrame()
    features.to_csv(out_dir / "option_native_features.csv", index=False)
    trades.to_csv(out_dir / "option_native_trades.csv", index=False)
    pnl.to_csv(out_dir / "option_native_pnl_path.csv", index=False)
    summary.to_csv(out_dir / "option_native_summary.csv", index=False)
    window_summary.to_csv(out_dir / "option_native_window_summary.csv", index=False)
    single_edges.to_csv(out_dir / "single_leg_edge_markouts.csv", index=False)
    product_edges.to_csv(out_dir / "single_leg_edge_markouts_by_product.csv", index=False)
    package_edges.to_csv(out_dir / "package_edge_markouts.csv", index=False)
    write_report(doc, out_dir, summary, window_summary, trades, single_edges, product_edges, package_edges, package_edge_screen_enabled)
    print(f"Wrote {out_dir}")
    print(f"Wrote {doc}")
    print(summary.sort_values(["dataset", "day", "total_pnl"], ascending=[True, True, False]).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument(
        "--package-edge-screen",
        action="store_true",
        help="Run the expensive package touch-to-future markout screen.",
    )
    parser.add_argument(
        "--include-packages",
        action="store_true",
        help="Run cross-strike package simulations. Disabled by default because low-edge package churn is slow.",
    )
    args = parser.parse_args()
    run(
        args.features,
        args.out_dir,
        args.doc,
        include_packages=args.include_packages,
        package_edge_screen_enabled=args.package_edge_screen,
    )


if __name__ == "__main__":
    main()
