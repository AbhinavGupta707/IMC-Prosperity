"""Round 4 HYDROGEL_PACK isolation research.

This script is deliberately diagnostic rather than a submission generator. It
asks first-principles questions about HYDROGEL:

* What is the size of the hindsight opportunity?
* Is current PnL realized or mostly terminal mark?
* Do static mean-reversion signals have positive forward edge cross-day?
* Do rolling/path/trend families beat the current static geometry without
  leaning on one day?
* Is Mark flow a primary driver or only a weak conditioner?

Outputs are written under ``outputs/round_4/hydrogel_isolation`` by default.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import sys
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config_core import EngineConfig, ProductConfig


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OFFICIAL_DIR = REPO_ROOT / "r4 Sim Results"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_isolation"

PRODUCT = "HYDROGEL_PACK"
LIMIT = 200
TIMESTAMP_STEP = 100

CURRENT_FINAL_MEAN = 9988.0
CURRENT_FINAL_TAKE_WIDTH = 32.0
CURRENT_PUBLIC_MEAN = 9955.0
CURRENT_PUBLIC_TAKE_WIDTH = 22.0

HORIZON_STEPS = {
    "1k": 10,
    "5k": 50,
    "10k": 100,
    "30k": 300,
    "100k": 1000,
}


@dataclass(frozen=True)
class Dataset:
    name: str
    kind: str
    day: int | None
    prices: pd.DataFrame
    trades: pd.DataFrame


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    mean: float = CURRENT_FINAL_MEAN
    width: float = CURRENT_FINAL_TAKE_WIDTH
    reset_gap: float = 8.0
    rebound_size: int = 40
    rebound_exit_gap: float = 35.0
    flat_gap: float = 0.0
    flatten_ts: int | None = 995_000
    cap_after_ts: int | None = None
    cap_after_abs: int = LIMIT
    rolling_window: int = 500
    rolling_offset: float = 0.0
    slope_window: int = 50
    slope_gate: float = 0.0
    max_step: int = 200


@dataclass(frozen=True)
class CandidateResult:
    dataset: str
    day: int | None
    candidate: str
    family: str
    pnl: float
    cash: float
    terminal_mark_component: float
    final_pos: int
    mark_price: float
    trades: int
    abs_qty: int
    max_abs_pos: int
    max_drawdown: float
    peak_pnl: float
    min_pnl: float


@dataclass(frozen=True)
class OracleResult:
    dataset: str
    day: int | None
    rows: int
    final_mid: float
    force_flat_pnl: float
    force_flat_pos: int
    terminal_mark_pnl: float
    terminal_mark_pos: int
    terminal_uplift_vs_flat: float


class _SubmissionAdapter:
    """Give a standalone Prosperity submission the repo simulator contract."""

    def __init__(self, trader_cls: type) -> None:
        self._inner = trader_cls()
        self.config = EngineConfig(
            products={
                PRODUCT: ProductConfig(
                    position_limit=LIMIT,
                    strategy_name="market_making",
                    fair_value_method="anchor",
                    anchor_price=CURRENT_FINAL_MEAN,
                )
            }
        )

    def run(self, state):
        orders, conversions, trader_data = self._inner.run(state)
        if orders:
            orders = {PRODUCT: list(orders.get(PRODUCT, []))}
        else:
            orders = {PRODUCT: []}
        return orders, conversions, trader_data


def _num(value: object, default: float = 0.0) -> float:
    try:
        if value == "" or value is None:
            return default
        out = float(value)
        if math.isnan(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def _as_positive_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).abs().astype(int)


def _prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    out = prices[prices["product"] == PRODUCT].copy()
    for col in out.columns:
        if col != "product":
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.sort_values("timestamp").reset_index(drop=True)
    out["bid_volume_1"] = _as_positive_int(out["bid_volume_1"])
    out["ask_volume_1"] = _as_positive_int(out["ask_volume_1"])
    out["spread"] = out["ask_price_1"] - out["bid_price_1"]
    out["ret"] = out["mid_price"].diff()
    out["tick_index"] = np.arange(len(out))
    return out


def _prepare_trades(trades: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "buyer",
                "seller",
                "symbol",
                "price",
                "quantity",
                "side",
                "aggressor",
            ]
        )
    out = trades[trades["symbol"] == PRODUCT].copy()
    for col in ("timestamp", "price", "quantity"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["timestamp", "price", "quantity"])
    out["timestamp"] = out["timestamp"].astype(int)
    out["quantity"] = out["quantity"].astype(int)
    book = prices[
        ["timestamp", "bid_price_1", "ask_price_1", "mid_price"]
    ].drop_duplicates("timestamp")
    out = out.merge(book, on="timestamp", how="left")
    out["side"] = "inside"
    out.loc[out["price"] >= out["ask_price_1"], "side"] = "buy"
    out.loc[out["price"] <= out["bid_price_1"], "side"] = "sell"
    out["aggressor"] = None
    out.loc[out["side"] == "buy", "aggressor"] = out.loc[out["side"] == "buy", "buyer"]
    out.loc[out["side"] == "sell", "aggressor"] = out.loc[out["side"] == "sell", "seller"]
    return out.sort_values("timestamp").reset_index(drop=True)


def _load_historical_datasets(data_dir: Path) -> list[Dataset]:
    datasets: list[Dataset] = []
    for price_path in sorted(data_dir.glob("prices_round_4_day_*.csv")):
        day = int(price_path.stem.rsplit("_day_", 1)[1])
        trade_path = data_dir / f"trades_round_4_day_{day}.csv"
        prices = _prepare_prices(pd.read_csv(price_path, sep=";"))
        trades = pd.read_csv(trade_path, sep=";") if trade_path.exists() else pd.DataFrame()
        trades = _prepare_trades(trades, prices)
        datasets.append(
            Dataset(
                name=f"hist_day_{day}",
                kind="historical",
                day=day,
                prices=prices,
                trades=trades,
            )
        )
    if not datasets:
        raise FileNotFoundError(f"No R4 price files found under {data_dir}")
    return datasets


def _iter_official_logs(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.suffix == ".log":
            yield root
        return
    yield from sorted(root.rglob("*.log"))


def _official_name(path: Path) -> str:
    parent = path.parent.name
    if parent and parent not in {".", "extracted"}:
        return parent
    return path.stem


def _load_official_dataset(path: Path) -> Dataset:
    payload = json.loads(path.read_text())
    activities = _prepare_prices(pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";"))
    trades = pd.DataFrame(payload.get("tradeHistory", []))
    if not trades.empty:
        trades = trades[
            (trades.get("buyer") != "SUBMISSION") & (trades.get("seller") != "SUBMISSION")
        ].copy()
    trades = _prepare_trades(trades, activities)
    return Dataset(
        name=f"official_{_official_name(path)}",
        kind="official",
        day=None,
        prices=activities,
        trades=trades,
    )


def _slice_prices(prices: pd.DataFrame, name: str) -> pd.DataFrame:
    if name == "full":
        return prices
    if name == "first_100k":
        return prices[prices["timestamp"] <= 99_900]
    if name == "post_100k":
        return prices[prices["timestamp"] >= 100_000]
    if name == "last_100k":
        end_ts = int(prices["timestamp"].max())
        return prices[prices["timestamp"] >= end_ts - 99_900]
    raise ValueError(name)


def _max_drawdown(values: pd.Series | list[float]) -> float:
    series = pd.Series(values, dtype=float)
    if series.empty:
        return 0.0
    return float((series - series.cummax()).min())


def build_path_stats(datasets: list[Dataset]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for dataset in datasets:
        for slice_name in ("full", "first_100k", "post_100k", "last_100k"):
            prices = _slice_prices(dataset.prices, slice_name)
            if prices.empty:
                continue
            mid = prices["mid_price"].astype(float)
            ret = mid.diff().dropna()
            row: dict[str, object] = {
                "dataset": dataset.name,
                "kind": dataset.kind,
                "day": dataset.day,
                "slice": slice_name,
                "rows": len(prices),
                "start_ts": int(prices["timestamp"].iloc[0]),
                "end_ts": int(prices["timestamp"].iloc[-1]),
                "mid_open": float(mid.iloc[0]),
                "mid_end": float(mid.iloc[-1]),
                "mid_mean": float(mid.mean()),
                "mid_median": float(mid.median()),
                "mid_std": float(mid.std(ddof=0)),
                "mid_min": float(mid.min()),
                "mid_max": float(mid.max()),
                "spread_mean": float(prices["spread"].mean()),
                "spread_median": float(prices["spread"].median()),
                "ret_abs_mean": float(ret.abs().mean()) if not ret.empty else 0.0,
                "ret_lag1_corr": float(ret.autocorr(1)) if len(ret) > 2 else np.nan,
            }
            for label, steps in {"1k": 10, "10k": 100, "100k": 1000}.items():
                future = mid.shift(-steps) - mid
                aligned = future.dropna()
                dev = (mid - CURRENT_FINAL_MEAN).loc[aligned.index]
                row[f"dev_to_fwd_{label}_corr_vs_9988"] = (
                    float(dev.corr(aligned)) if len(aligned) > 3 else np.nan
                )
            rows.append(row)
    return pd.DataFrame(rows)


def _sliding_window_max(values: np.ndarray, window: int, *, trailing: bool) -> np.ndarray:
    """Return max over [i-window, i] or [i, i+window] for each i."""
    n = len(values)
    out = np.full(n, -np.inf)
    dq: deque[int] = deque()
    indices = range(n) if trailing else range(n - 1, -1, -1)
    for i in indices:
        while dq and values[dq[-1]] <= values[i]:
            dq.pop()
        dq.append(i)
        if trailing:
            while dq and dq[0] < i - window:
                dq.popleft()
        else:
            while dq and dq[0] > i + window:
                dq.popleft()
        out[i] = values[dq[0]]
    return out


def hindsight_l1_oracle(prices: pd.DataFrame) -> tuple[float, int, float, int]:
    """Top-of-book taker DP with hindsight and position limit."""
    positions = np.arange(-LIMIT, LIMIT + 1, dtype=float)
    n_pos = len(positions)
    flat_index = LIMIT
    dp = np.full(n_pos, -np.inf)
    dp[flat_index] = 0.0

    bids = prices["bid_price_1"].astype(float).to_numpy()
    asks = prices["ask_price_1"].astype(float).to_numpy()
    bid_vols = prices["bid_volume_1"].astype(int).to_numpy()
    ask_vols = prices["ask_volume_1"].astype(int).to_numpy()

    for bid, ask, bid_vol, ask_vol in zip(bids, asks, bid_vols, ask_vols, strict=True):
        new_dp = dp.copy()
        if ask_vol > 0:
            window = min(int(ask_vol), n_pos - 1)
            source = dp + positions * ask
            buy_best = _sliding_window_max(source, window, trailing=True)
            new_dp = np.maximum(new_dp, -positions * ask + buy_best)
        if bid_vol > 0:
            window = min(int(bid_vol), n_pos - 1)
            source = dp + positions * bid
            sell_best = _sliding_window_max(source, window, trailing=False)
            new_dp = np.maximum(new_dp, -positions * bid + sell_best)
        dp = new_dp

    final_mid = float(prices["mid_price"].iloc[-1])
    flat_pnl = float(dp[flat_index])
    marked = dp + positions * final_mid
    marked_idx = int(np.argmax(marked))
    marked_pnl = float(marked[marked_idx])
    marked_pos = int(positions[marked_idx])
    return flat_pnl, 0, marked_pnl, marked_pos


def build_oracle_summary(datasets: list[Dataset]) -> pd.DataFrame:
    rows: list[OracleResult] = []
    for dataset in datasets:
        flat_pnl, flat_pos, marked_pnl, marked_pos = hindsight_l1_oracle(dataset.prices)
        final_mid = float(dataset.prices["mid_price"].iloc[-1])
        rows.append(
            OracleResult(
                dataset=dataset.name,
                day=dataset.day,
                rows=len(dataset.prices),
                final_mid=final_mid,
                force_flat_pnl=flat_pnl,
                force_flat_pos=flat_pos,
                terminal_mark_pnl=marked_pnl,
                terminal_mark_pos=marked_pos,
                terminal_uplift_vs_flat=marked_pnl - flat_pnl,
            )
        )
    return pd.DataFrame([asdict(row) for row in rows])


def _submission_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=["timestamp", "buyer", "seller", "symbol", "price", "quantity", "signed_qty", "cash"]
        )
    own = trades[
        (trades["buyer"] == "SUBMISSION") | (trades["seller"] == "SUBMISSION")
    ].copy()
    if own.empty:
        return own
    own = own[own["symbol"] == PRODUCT].copy()
    own["signed_qty"] = np.where(own["buyer"] == "SUBMISSION", own["quantity"], -own["quantity"])
    own["cash"] = np.where(
        own["buyer"] == "SUBMISSION",
        -own["price"].astype(float) * own["quantity"].astype(int),
        own["price"].astype(float) * own["quantity"].astype(int),
    )
    return own.sort_values("timestamp").reset_index(drop=True)


def build_official_strategy_summary(log_paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in log_paths:
        payload = json.loads(path.read_text())
        activities = pd.read_csv(io.StringIO(payload["activitiesLog"]), sep=";")
        hyd = _prepare_prices(activities)
        trades = pd.DataFrame(payload.get("tradeHistory", []))
        own = _submission_trades(trades)
        pnl = hyd["profit_and_loss"].astype(float)
        final_mid = float(hyd["mid_price"].iloc[-1])
        final_pnl = float(pnl.iloc[-1])
        final_pos = int(own["signed_qty"].sum()) if not own.empty else 0
        cash = float(own["cash"].sum()) if not own.empty else 0.0
        terminal = final_pos * final_mid
        official_terminal = final_pnl - cash
        implied_mark = (official_terminal / final_pos) if final_pos else np.nan
        break_even = (-cash / final_pos) if final_pos else np.nan
        first_limit_ts = None
        pos = 0
        max_abs_pos = 0
        for trade in own.itertuples(index=False):
            pos += int(trade.signed_qty)
            max_abs_pos = max(max_abs_pos, abs(pos))
            if first_limit_ts is None and abs(pos) >= LIMIT:
                first_limit_ts = int(trade.timestamp)
        rows.append(
            {
                "candidate": _official_name(path),
                "path": str(path),
                "final_pnl": final_pnl,
                "cash": cash,
                "final_pos": final_pos,
                "final_mid": final_mid,
                "terminal_mark_component": terminal,
                "official_terminal_mark_component": official_terminal,
                "implied_official_terminal_mark": implied_mark,
                "cash_plus_terminal_mid": cash + terminal,
                "break_even_terminal_mid": break_even,
                "pnl_per_terminal_tick": final_pos,
                "pnl_if_terminal_9988": cash + final_pos * 9988.0,
                "pnl_if_terminal_9995": cash + final_pos * 9995.0,
                "pnl_if_terminal_10000": cash + final_pos * 10000.0,
                "pnl_if_terminal_mid_minus_25": cash + final_pos * (final_mid - 25.0),
                "pnl_if_terminal_mid_plus_25": cash + final_pos * (final_mid + 25.0),
                "min_pnl": float(pnl.min()),
                "peak_pnl": float(pnl.max()),
                "max_drawdown": _max_drawdown(pnl),
                "trade_rows": len(own),
                "abs_qty": int(own["quantity"].sum()) if not own.empty else 0,
                "first_trade_ts": int(own["timestamp"].min()) if not own.empty else None,
                "first_limit_ts": first_limit_ts,
                "last_trade_ts": int(own["timestamp"].max()) if not own.empty else None,
                "max_abs_pos": max_abs_pos,
            }
        )
    return pd.DataFrame(rows)


def _hydrogel_only_replay(data_dir: Path, day: int | None = None) -> ReplayEngine:
    days = sorted(
        int(path.stem.rsplit("_day_", 1)[1])
        for path in data_dir.glob("prices_round_4_day_*.csv")
    )
    if day is not None:
        days = [day]
    steps: list[ReplayStep] = []
    for d in days:
        replay = ReplayEngine.from_files(
            price_paths=[data_dir / f"prices_round_4_day_{d}.csv"],
            trade_paths=[data_dir / f"trades_round_4_day_{d}.csv"],
        )
        for step in replay.iter_steps():
            if PRODUCT not in step.rows_by_product:
                continue
            steps.append(
                ReplayStep(
                    day=step.day,
                    timestamp=step.timestamp,
                    rows_by_product={PRODUCT: step.rows_by_product[PRODUCT]},
                    market_trades={PRODUCT: step.market_trades.get(PRODUCT, [])},
                )
            )
    return ReplayEngine(steps)


def _load_trader_class(path: Path) -> type:
    module_name = "hyd_sub_" + path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.Trader


def build_current_local_summary(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    variants = {
        "current_no_terminal_guard": REPO_ROOT
        / "outputs"
        / "submissions"
        / "r4"
        / "submission_r4_diag_hydrogel_only.py",
        "flat995": REPO_ROOT
        / "outputs"
        / "submissions"
        / "r4"
        / "submission_r4_safer_hydflat995.py",
        "cap50_990": REPO_ROOT
        / "outputs"
        / "submissions"
        / "r4"
        / "submission_r4_safer_hydcap50_990.py",
    }
    rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    for variant, path in variants.items():
        trader_cls = _load_trader_class(path)
        for day in (None, 1, 2, 3):
            replay = _hydrogel_only_replay(data_dir, day=day)
            result = BacktestSimulator(
                _SubmissionAdapter(trader_cls),
                FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True)),
            ).run(replay)
            product = result.per_product.get(PRODUCT)
            if product is None:
                continue
            pnl_series = pd.Series([value for _, value in result.pnl_series.get(PRODUCT, ())])
            terminal = product.final_position * (product.mark_price or 0.0)
            rows.append(
                {
                    "variant": variant,
                    "day": "all" if day is None else day,
                    "pnl": product.pnl,
                    "cash": product.cash,
                    "terminal_mark_component": terminal,
                    "final_pos": product.final_position,
                    "mark_price": product.mark_price,
                    "pnl_if_terminal_9988": product.cash + product.final_position * 9988.0,
                    "pnl_if_terminal_9995": product.cash + product.final_position * 9995.0,
                    "pnl_per_terminal_tick": product.final_position,
                    "trade_count": product.trade_count,
                    "order_count": product.order_count,
                    "taker_qty": product.taker_trade_quantity,
                    "maker_qty": product.maker_trade_quantity,
                    "buy_qty": product.buy_trade_quantity,
                    "sell_qty": product.sell_trade_quantity,
                    "steps_near_limit": product.steps_near_limit,
                    "min_pnl": float(pnl_series.min()) if not pnl_series.empty else np.nan,
                    "peak_pnl": float(pnl_series.max()) if not pnl_series.empty else np.nan,
                    "max_drawdown": _max_drawdown(pnl_series),
                    "avg_entry_edge": product.avg_entry_edge,
                    "avg_markout_1": product.avg_markout_1,
                    "avg_markout_5": product.avg_markout_5,
                    "avg_markout_20": product.avg_markout_20,
                }
            )
            if day is not None:
                for (ts, value), key in zip(
                    result.pnl_series.get(PRODUCT, ()), result.pnl_keys.get(PRODUCT, ()), strict=True
                ):
                    series_rows.append(
                        {
                            "variant": variant,
                            "day": day,
                            "timestamp": ts,
                            "pnl": value,
                            "key_day": key[0],
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(series_rows)


def _future_value(series: pd.Series, index: int, steps: int) -> float | None:
    j = index + steps
    if j >= len(series):
        return None
    return float(series.iloc[j])


def build_signal_edge_grid(datasets: list[Dataset]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    means = [9955.0, 9975.0, 9988.0, 9995.0, 10005.0]
    widths = [18.0, 22.0, 26.0, 32.0, 38.0, 44.0]
    for dataset in [d for d in datasets if d.kind == "historical"]:
        prices = dataset.prices.reset_index(drop=True)
        mids = prices["mid_price"].astype(float)
        for mean in means:
            for width in widths:
                for side in ("buy", "sell"):
                    if side == "buy":
                        mask = prices["ask_price_1"] <= mean - width
                        entry = prices["ask_price_1"].astype(float)
                    else:
                        mask = prices["bid_price_1"] >= mean + width
                        entry = prices["bid_price_1"].astype(float)
                    idxs = list(np.flatnonzero(mask.to_numpy()))
                    if not idxs:
                        rows.append(
                            {
                                "dataset": dataset.name,
                                "day": dataset.day,
                                "mean": mean,
                                "width": width,
                                "side": side,
                                "events": 0,
                            }
                        )
                        continue
                    edge_sums: dict[str, float] = {label: 0.0 for label in HORIZON_STEPS}
                    edge_counts: dict[str, int] = {label: 0 for label in HORIZON_STEPS}
                    terminal_edges: list[float] = []
                    for i in idxs:
                        px = float(entry.iloc[i])
                        terminal_mid = float(mids.iloc[-1])
                        terminal_edge = terminal_mid - px if side == "buy" else px - terminal_mid
                        terminal_edges.append(terminal_edge)
                        for label, steps in HORIZON_STEPS.items():
                            fut = _future_value(mids, i, steps)
                            if fut is None:
                                continue
                            edge = fut - px if side == "buy" else px - fut
                            edge_sums[label] += edge
                            edge_counts[label] += 1
                            detail_rows.append(
                                {
                                    "dataset": dataset.name,
                                    "day": dataset.day,
                                    "mean": mean,
                                    "width": width,
                                    "side": side,
                                    "timestamp": int(prices["timestamp"].iloc[i]),
                                    "horizon": label,
                                    "edge": edge,
                                }
                            )
                    row = {
                        "dataset": dataset.name,
                        "day": dataset.day,
                        "mean": mean,
                        "width": width,
                        "side": side,
                        "events": len(idxs),
                        "terminal_edge_mean": float(np.mean(terminal_edges)),
                    }
                    for label in HORIZON_STEPS:
                        count = edge_counts[label]
                        row[f"edge_{label}_mean"] = edge_sums[label] / count if count else np.nan
                        row[f"edge_{label}_count"] = count
                    rows.append(row)
    grid = pd.DataFrame(rows)
    if grid.empty:
        return grid, pd.DataFrame()
    grouped = (
        grid.groupby(["mean", "width", "side"], dropna=False)
        .agg(
            events=("events", "sum"),
            day_count=("day", "nunique"),
            edge_10k_mean=("edge_10k_mean", "mean"),
            edge_30k_mean=("edge_30k_mean", "mean"),
            edge_100k_mean=("edge_100k_mean", "mean"),
            terminal_edge_mean=("terminal_edge_mean", "mean"),
            edge_10k_min_day=("edge_10k_mean", "min"),
            edge_30k_min_day=("edge_30k_mean", "min"),
            edge_100k_min_day=("edge_100k_mean", "min"),
        )
        .reset_index()
    )
    grouped["robust_score"] = (
        grouped["edge_30k_mean"].fillna(-999)
        + grouped["edge_30k_min_day"].fillna(-999)
        + 0.25 * np.log1p(grouped["events"].astype(float))
    )
    grouped = grouped.sort_values("robust_score", ascending=False)
    return grid, grouped


def _candidate_list() -> list[Candidate]:
    out = [
        Candidate(
            name="current_static_flat995",
            family="static_cycle",
            mean=9988.0,
            width=32.0,
            reset_gap=8.0,
            rebound_exit_gap=35.0,
            flatten_ts=995_000,
        ),
        Candidate(
            name="current_static_no_flat",
            family="static_cycle",
            mean=9988.0,
            width=32.0,
            reset_gap=8.0,
            rebound_exit_gap=35.0,
            flatten_ts=None,
        ),
    ]
    for mean in (9975.0, 9988.0, 9995.0, 10005.0):
        for width in (22.0, 28.0, 32.0, 38.0):
            for flatten_ts in (950_000, 990_000, 995_000):
                out.append(
                    Candidate(
                        name=f"static_m{int(mean)}_w{int(width)}_flat{flatten_ts // 1000}",
                        family="static_cycle",
                        mean=mean,
                        width=width,
                        reset_gap=8.0,
                        rebound_exit_gap=35.0,
                        flatten_ts=flatten_ts,
                    )
                )
    for window in (250, 500, 1000, 2500):
        for width in (18.0, 24.0, 32.0):
            out.append(
                Candidate(
                    name=f"rolling_w{window}_width{int(width)}",
                    family="rolling_mr",
                    width=width,
                    rolling_window=window,
                    flatten_ts=995_000,
                )
            )
    for slope_window in (50, 100, 300):
        for gate in (0.0, 4.0, 8.0):
            out.append(
                Candidate(
                    name=f"trend_w{slope_window}_g{int(gate)}",
                    family="trend",
                    width=0.0,
                    slope_window=slope_window,
                    slope_gate=gate,
                    flatten_ts=995_000,
                )
            )
            out.append(
                Candidate(
                    name=f"path_fade_w{slope_window}_g{int(gate)}",
                    family="path_fade",
                    width=0.0,
                    slope_window=slope_window,
                    slope_gate=gate,
                    flatten_ts=995_000,
                )
            )
    return out


def _cap_for(candidate: Candidate, ts: int) -> int:
    if candidate.cap_after_ts is not None and ts >= candidate.cap_after_ts:
        return min(candidate.cap_after_abs, LIMIT)
    return LIMIT


def _trade_to_target(row: pd.Series, pos: int, target: int, max_step: int) -> tuple[int, float, int]:
    target = max(-LIMIT, min(LIMIT, target))
    delta = max(-max_step, min(max_step, target - pos))
    if delta == 0:
        return pos, 0.0, 0
    if delta > 0:
        qty = min(delta, int(row["ask_volume_1"]), LIMIT - pos)
        if qty <= 0:
            return pos, 0.0, 0
        return pos + qty, -qty * float(row["ask_price_1"]), qty
    qty = min(-delta, int(row["bid_volume_1"]), LIMIT + pos)
    if qty <= 0:
        return pos, 0.0, 0
    return pos - qty, qty * float(row["bid_price_1"]), qty


def simulate_candidate(dataset: Dataset, candidate: Candidate) -> CandidateResult:
    prices = dataset.prices.reset_index(drop=True)
    mids = prices["mid_price"].astype(float)
    rolling = mids.rolling(candidate.rolling_window, min_periods=1).mean().shift(1)
    rolling = rolling.fillna(mids.expanding().mean())
    slopes = mids - mids.shift(candidate.slope_window)
    pos = 0
    cash = 0.0
    trades = 0
    abs_qty = 0
    max_abs_pos = 0
    long_mode = False
    pnl_path: list[float] = []

    for i, row in prices.iterrows():
        ts = int(row["timestamp"])
        mid = float(row["mid_price"])
        cap = _cap_for(candidate, ts)
        target = pos
        if candidate.flatten_ts is not None and ts >= candidate.flatten_ts:
            target = 0
            long_mode = False
        elif candidate.family == "static_cycle":
            if long_mode and pos > 0 and mid >= candidate.mean + candidate.rebound_exit_gap:
                target = 0
                long_mode = False
            elif pos < 0 and mid <= candidate.mean - candidate.reset_gap:
                target = candidate.rebound_size
                long_mode = True
            elif long_mode:
                target = max(pos, candidate.rebound_size)
            elif float(row["bid_price_1"]) >= candidate.mean + candidate.width:
                target = -cap
            elif float(row["ask_price_1"]) <= candidate.mean - candidate.width:
                target = cap
            elif candidate.flat_gap and abs(mid - candidate.mean) <= candidate.flat_gap:
                target = 0
        elif candidate.family == "rolling_mr":
            fair = float(rolling.iloc[i]) + candidate.rolling_offset
            if float(row["bid_price_1"]) >= fair + candidate.width:
                target = -cap
            elif float(row["ask_price_1"]) <= fair - candidate.width:
                target = cap
            elif abs(mid - fair) <= 2:
                target = 0
        elif candidate.family in {"trend", "path_fade"}:
            slope = 0.0 if pd.isna(slopes.iloc[i]) else float(slopes.iloc[i])
            if abs(slope) >= candidate.slope_gate:
                sign = 1 if slope > 0 else -1
                if candidate.family == "path_fade":
                    sign *= -1
                target = int(sign * cap)
            else:
                target = 0

        pos, cash_delta, qty = _trade_to_target(row, pos, target, candidate.max_step)
        cash += cash_delta
        if qty:
            trades += 1
            abs_qty += qty
        max_abs_pos = max(max_abs_pos, abs(pos))
        pnl_path.append(cash + pos * mid)

    mark_price = float(prices["mid_price"].iloc[-1])
    pnl = cash + pos * mark_price
    path = pd.Series(pnl_path, dtype=float)
    return CandidateResult(
        dataset=dataset.name,
        day=dataset.day,
        candidate=candidate.name,
        family=candidate.family,
        pnl=float(pnl),
        cash=float(cash),
        terminal_mark_component=float(pos * mark_price),
        final_pos=int(pos),
        mark_price=mark_price,
        trades=trades,
        abs_qty=abs_qty,
        max_abs_pos=max_abs_pos,
        max_drawdown=_max_drawdown(path),
        peak_pnl=float(path.max()) if not path.empty else 0.0,
        min_pnl=float(path.min()) if not path.empty else 0.0,
    )


def build_candidate_summary(datasets: list[Dataset]) -> tuple[pd.DataFrame, pd.DataFrame]:
    historical = [d for d in datasets if d.kind == "historical"]
    rows = [
        asdict(simulate_candidate(dataset, candidate))
        for candidate in _candidate_list()
        for dataset in historical
    ]
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()
    summary = (
        detail.groupby(["candidate", "family"], dropna=False)
        .agg(
            mean_pnl=("pnl", "mean"),
            min_pnl=("pnl", "min"),
            max_pnl=("pnl", "max"),
            mean_drawdown=("max_drawdown", "mean"),
            worst_drawdown=("max_drawdown", "min"),
            mean_abs_qty=("abs_qty", "mean"),
            max_abs_pos=("max_abs_pos", "max"),
            final_pos_abs_mean=("final_pos", lambda s: float(np.mean(np.abs(s)))),
        )
        .reset_index()
    )
    summary["robust_score"] = (
        summary["mean_pnl"]
        + 0.8 * summary["min_pnl"]
        + 0.15 * summary["worst_drawdown"]
        - 0.02 * summary["final_pos_abs_mean"]
    )
    summary = summary.sort_values("robust_score", ascending=False)
    return detail, summary


def build_mark_flow_edges(datasets: list[Dataset]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for dataset in datasets:
        if dataset.trades.empty:
            continue
        prices = dataset.prices.reset_index(drop=True)
        mid_by_ts = prices.set_index("timestamp")["mid_price"].astype(float)
        ts_to_idx = {int(ts): i for i, ts in enumerate(prices["timestamp"])}
        mids = prices["mid_price"].astype(float)
        for trade in dataset.trades.itertuples(index=False):
            side = getattr(trade, "side", "inside")
            if side not in {"buy", "sell"}:
                continue
            aggressor = getattr(trade, "aggressor", None)
            if not isinstance(aggressor, str) or aggressor == "SUBMISSION":
                continue
            ts = int(trade.timestamp)
            idx = ts_to_idx.get(ts)
            if idx is None:
                continue
            price = float(trade.price)
            signed = 1.0 if side == "buy" else -1.0
            row: dict[str, object] = {
                "dataset": dataset.name,
                "kind": dataset.kind,
                "day": dataset.day,
                "mark": aggressor,
                "side": side,
                "timestamp": ts,
                "price": price,
                "quantity": int(trade.quantity),
                "entry_vs_mid": signed * (float(mid_by_ts.loc[ts]) - price),
            }
            for label, steps in HORIZON_STEPS.items():
                fut = _future_value(mids, idx, steps)
                row[f"follow_edge_{label}"] = signed * (fut - price) if fut is not None else np.nan
            terminal_mid = float(mids.iloc[-1])
            row["follow_edge_terminal"] = signed * (terminal_mid - price)
            rows.append(row)
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()
    summary = (
        detail.groupby(["kind", "mark", "side"], dropna=False)
        .agg(
            events=("timestamp", "count"),
            qty=("quantity", "sum"),
            datasets=("dataset", "nunique"),
            edge_5k=("follow_edge_5k", "mean"),
            edge_10k=("follow_edge_10k", "mean"),
            edge_30k=("follow_edge_30k", "mean"),
            edge_100k=("follow_edge_100k", "mean"),
            edge_terminal=("follow_edge_terminal", "mean"),
        )
        .reset_index()
        .sort_values(["kind", "edge_30k"], ascending=[True, False])
    )
    return detail, summary


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "(empty)"
    display = df.copy()
    display = display.astype(object).where(pd.notna(display), "")
    headers = [str(col) for col in display.columns]
    rows = [[str(value) for value in row] for row in display.to_numpy()]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    header = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    body = [
        "| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(headers))) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def write_report(
    out_dir: Path,
    path_stats: pd.DataFrame,
    oracle: pd.DataFrame,
    official: pd.DataFrame,
    local: pd.DataFrame,
    signal_summary: pd.DataFrame,
    candidate_summary: pd.DataFrame,
    mark_summary: pd.DataFrame,
) -> None:
    lines: list[str] = [
        "# HYDROGEL Isolation Diagnostics",
        "",
        "Generated by `src/scripts/round_4/analyze_hydrogel_isolation.py`.",
        "",
        "## Key Tables",
        "",
        "- `path_stats.csv`: path geometry and first/last-window stationarity checks.",
        "- `hindsight_oracle.csv`: top-of-book L1 hindsight upper bounds.",
        "- `official_strategy_attribution.csv`: official 100k cash vs terminal mark exposure.",
        "- `current_local_backtest.csv`: current HYD variants in local HYD-only replay.",
        "- `signal_edge_grid.csv` and `signal_edge_summary.csv`: spread-aware forward edge of static entry signals.",
        "- `candidate_family_results.csv` and `candidate_family_summary.csv`: lightweight taker-only family tests.",
        "- `mark_flow_edges.csv` and `mark_flow_summary.csv`: HYD Mark-flow forward edges.",
        "",
    ]

    hist_stats = path_stats[(path_stats["kind"] == "historical") & (path_stats["slice"] == "full")]
    if not hist_stats.empty:
        lines.extend(
            [
                "## Historical Geometry Snapshot",
                "",
                hist_stats[
                    ["dataset", "mid_mean", "mid_std", "mid_min", "mid_max", "mid_end", "ret_lag1_corr"]
                ]
                .round(3)
                .pipe(_markdown_table),
                "",
            ]
        )
    official_stats = path_stats[(path_stats["kind"] == "official") & (path_stats["slice"] == "full")]
    if not official_stats.empty:
        lines.extend(
            [
                "## Official 100k Geometry Snapshot",
                "",
                official_stats[
                    ["dataset", "mid_mean", "mid_std", "mid_min", "mid_max", "mid_end"]
                ]
                .drop_duplicates("dataset")
                .round(3)
                .pipe(_markdown_table),
                "",
            ]
        )
    if not official.empty:
        lines.extend(
            [
                "## Official Current HYD Attribution",
                "",
                official[
                    [
                        "candidate",
                        "final_pnl",
                        "cash",
                        "final_pos",
                        "final_mid",
                        "official_terminal_mark_component",
                        "implied_official_terminal_mark",
                        "break_even_terminal_mid",
                        "pnl_per_terminal_tick",
                        "max_drawdown",
                    ]
                ]
                .drop_duplicates("candidate")
                .round(2)
                .pipe(_markdown_table),
                "",
            ]
        )
    if not oracle.empty:
        lines.extend(
            [
                "## Hindsight Opportunity",
                "",
                _markdown_table(oracle.round(2)),
                "",
            ]
        )
    if not local.empty:
        all_rows = local[local["day"].astype(str) == "all"]
        if not all_rows.empty:
            lines.extend(
                [
                    "## Local Current-Variant Replay",
                    "",
                    all_rows[
                        [
                            "variant",
                            "pnl",
                            "cash",
                            "terminal_mark_component",
                            "final_pos",
                            "max_drawdown",
                            "trade_count",
                            "maker_qty",
                            "taker_qty",
                        ]
                    ]
                    .round(2)
                    .pipe(_markdown_table),
                    "",
                ]
            )
    if not signal_summary.empty:
        lines.extend(
            [
                "## Static Signal Edge Leaders",
                "",
                _markdown_table(signal_summary.head(12).round(3)),
                "",
            ]
        )
    if not candidate_summary.empty:
        lines.extend(
            [
                "## Candidate Family Leaders",
                "",
                _markdown_table(candidate_summary.head(12).round(2)),
                "",
            ]
        )
    if not mark_summary.empty:
        interesting = mark_summary[(mark_summary["kind"] == "historical") & (mark_summary["events"] >= 5)]
        lines.extend(
            [
                "## Mark-Flow Leaders",
                "",
                _markdown_table(interesting.head(15).round(3)),
                "",
            ]
        )
    (out_dir / "HYDROGEL_DIAGNOSTICS_AUTOGEN.md").write_text("\n".join(lines))


def run(data_dir: Path, official_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    historical = _load_historical_datasets(data_dir)
    official_logs = list(_iter_official_logs(official_dir))
    official_datasets = [_load_official_dataset(path) for path in official_logs]
    datasets = historical + official_datasets

    path_stats = build_path_stats(datasets)
    path_stats.to_csv(out_dir / "path_stats.csv", index=False)

    oracle = build_oracle_summary(datasets)
    oracle.to_csv(out_dir / "hindsight_oracle.csv", index=False)

    official_summary = build_official_strategy_summary(official_logs)
    official_summary.to_csv(out_dir / "official_strategy_attribution.csv", index=False)

    local_summary, local_series = build_current_local_summary(data_dir)
    local_summary.to_csv(out_dir / "current_local_backtest.csv", index=False)
    local_series.to_csv(out_dir / "current_local_pnl_series.csv", index=False)

    signal_grid, signal_summary = build_signal_edge_grid(datasets)
    signal_grid.to_csv(out_dir / "signal_edge_grid.csv", index=False)
    signal_summary.to_csv(out_dir / "signal_edge_summary.csv", index=False)

    candidate_detail, candidate_summary = build_candidate_summary(datasets)
    candidate_detail.to_csv(out_dir / "candidate_family_results.csv", index=False)
    candidate_summary.to_csv(out_dir / "candidate_family_summary.csv", index=False)

    mark_detail, mark_summary = build_mark_flow_edges(datasets)
    mark_detail.to_csv(out_dir / "mark_flow_edges.csv", index=False)
    mark_summary.to_csv(out_dir / "mark_flow_summary.csv", index=False)

    write_report(
        out_dir,
        path_stats,
        oracle,
        official_summary,
        local_summary,
        signal_summary,
        candidate_summary,
        mark_summary,
    )

    print(f"Wrote HYDROGEL isolation diagnostics to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--official-dir", type=Path, default=DEFAULT_OFFICIAL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    run(args.data_dir, args.official_dir, args.out_dir)


if __name__ == "__main__":
    main()
