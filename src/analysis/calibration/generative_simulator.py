"""Generative simulator orchestrator: tick loop that runs a Trader.

Per-tick mechanics (one product, repeated for every product in config):

  1. FV is precomputed at session init: ``fv_path[tick]`` is the FV
     for that product at that tick. (Random walk via fv_evolver.)

  2. Book is sampled from empirical historical distribution
     conditioned on frac(FV). (bot_sampler.)

  3. Player aggressive orders cross the bot book first (player_matcher
     phase 1). Unfilled remainders queue as player passive for this tick.

  4. Trade tape (precomputed at session init via trade_sampler) walks
     the combined book at this tick's timestamp. Bots have time
     priority at every price level; player passive only fills leftover.

  5. Mark-to-market: ``equity = sum(cash[p] + position[p] * fv[p])``.

  6. Player passive orders ARE NOT carried to the next tick (matches
     IMC Prosperity semantics: every tick the trader must re-quote).

Position-limit enforcement: if a product's order batch would breach
the limit (in either direction), the ENTIRE batch is rejected for
that product (matches IMC behavior). This is a hard enforcement at
the simulator boundary; the strategy is responsible for self-limiting.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from src.analysis.calibration.bot_sampler import BookSampler
from src.analysis.calibration.fv_evolver import FVProcess, spawn_fv_path
from src.analysis.calibration.player_matcher import (
    PlayerOrder, apply_fills_to_account,
    match_aggressive_orders, match_bot_taker_trades,
)
from src.analysis.calibration.trade_sampler import SyntheticTrade, TradeSampler

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionConfig:
    """One session's configuration: products + samplers + scheduling."""

    products: tuple[str, ...]
    n_ticks: int
    fv_processes: Mapping[str, FVProcess]
    book_samplers: Mapping[str, BookSampler]
    trade_samplers: Mapping[str, TradeSampler]
    position_limit: int = 80
    tick_step: int = 100
    seed: int = 0


@dataclass(frozen=True)
class SessionResult:
    """One session's outputs: PnL, equity curve, positions, fills."""

    seed: int
    n_ticks: int
    products: tuple[str, ...]
    per_tick_equity: tuple[float, ...]
    per_tick_position: dict[str, tuple[int, ...]]
    per_tick_fv: dict[str, tuple[float, ...]]
    final_pnl: float
    realized_alpha: float       # OLS slope of equity curve vs tick
    realized_r2: float          # R^2 of that fit
    realized_downside_dev: float
    n_fills: dict[str, int]
    n_orders_rejected_limit: dict[str, int]


def run_session(
    config: SessionConfig,
    *,
    trader_factory: Callable[[], object],
) -> SessionResult:
    """Run a single synthetic session.

    Args:
        config: SessionConfig with per-product FV / book / trade samplers.
        trader_factory: zero-arg callable returning a fresh Trader
            instance (matches the IMC contract: state is carried via
            traderData string, not via instance state).

    Returns:
        SessionResult with per-tick equity / position / FV traces and
        aggregate stats.
    """
    from src.datamodel import (  # noqa: PLC0415
        Observation, OrderDepth, TradingState,
    )

    # P0-1 fix: spawn one Generator per (component, product) pair so that
    # changes to per-call random consumption in any sampler (e.g. trade
    # arrivals adding a new draw) cannot break determinism in unrelated
    # samplers downstream. Each child generator is reproducibly derived
    # from the master seed.
    master = np.random.default_rng(config.seed)
    n_products = len(config.products)
    # 3 component slots: FV, trade-arrival pre-spawn, per-tick book sample.
    fv_rngs, trade_rngs, book_rngs = (
        master.spawn(n_products),
        master.spawn(n_products),
        master.spawn(n_products),
    )
    fv_rng_by_p = dict(zip(config.products, fv_rngs))
    trade_rng_by_p = dict(zip(config.products, trade_rngs))
    book_rng_by_p = dict(zip(config.products, book_rngs))

    # 1. Pre-spawn FV paths per product (independent draws).
    fv_paths: dict[str, np.ndarray] = {}
    for product in config.products:
        if product not in config.fv_processes:
            raise KeyError(f"Missing fv_process for {product}")
        fv_paths[product] = spawn_fv_path(
            config.fv_processes[product],
            n_ticks=config.n_ticks,
            rng=fv_rng_by_p[product],
        )

    # 2. Pre-spawn trade tapes per product.
    takers_by_tick: dict[int, list[SyntheticTrade]] = {}
    for product in config.products:
        if product not in config.trade_samplers:
            continue  # No trade sampler for this product → no synthetic trades
        trade_list = config.trade_samplers[product].sample_session(
            fv_path=fv_paths[product], rng=trade_rng_by_p[product],
        )
        for trade in trade_list:
            tick = trade.timestamp // config.tick_step
            takers_by_tick.setdefault(tick, []).append(trade)

    # 3. Tick loop.
    trader = trader_factory()
    trader_data = ""
    positions: dict[str, int] = {p: 0 for p in config.products}
    cash: dict[str, float] = {p: 0.0 for p in config.products}
    n_fills: dict[str, int] = {p: 0 for p in config.products}
    n_rejected: dict[str, int] = {p: 0 for p in config.products}
    per_tick_equity: list[float] = []
    per_tick_position: dict[str, list[int]] = {p: [] for p in config.products}

    for tick in range(config.n_ticks):
        ts = tick * config.tick_step

        # 3a. Sample bot books per product.
        order_depths: dict[str, OrderDepth] = {}
        bot_bids_by_p: dict[str, tuple] = {}
        bot_asks_by_p: dict[str, tuple] = {}
        for product in config.products:
            bids, asks = config.book_samplers[product].sample_book(
                fv=float(fv_paths[product][tick]),
                rng=book_rng_by_p[product],
            )
            order_depths[product] = OrderDepth(
                buy_orders={lvl.price: lvl.volume for lvl in bids},
                sell_orders={lvl.price: -lvl.volume for lvl in asks},
            )
            bot_bids_by_p[product] = bids
            bot_asks_by_p[product] = asks

        # 3b. Build TradingState, call Trader.run.
        state = TradingState(
            traderData=trader_data, timestamp=ts, listings={},
            order_depths=order_depths, own_trades={}, market_trades={},
            position={p: positions[p] for p in config.products},
            observations=Observation(),
        )
        try:
            raw_orders, _, trader_data = trader.run(state)
            if not isinstance(trader_data, str):
                trader_data = ""
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Trader.run raised at t=%d: %s", ts, exc)
            raw_orders = {}

        # 3c. Position-limit enforcement: reject entire batch per product
        #     if it would breach the limit.
        validated_orders: dict[str, list[PlayerOrder]] = {}
        for product, product_orders in raw_orders.items():
            if product not in config.products:
                continue
            converted = [
                PlayerOrder(product=product, price=o.price, quantity=o.quantity)
                for o in product_orders if o.quantity != 0
            ]
            total_buy = sum(o.quantity for o in converted if o.quantity > 0)
            total_sell = sum(-o.quantity for o in converted if o.quantity < 0)
            current = positions[product]
            if (current + total_buy > config.position_limit
                    or current - total_sell < -config.position_limit):
                n_rejected[product] += len(converted)
                continue
            validated_orders[product] = converted

        # 3d. Phase 1: aggressive matching against bot book.
        passive_by_p: dict[str, list[PlayerOrder]] = {p: [] for p in config.products}
        dep_bids_by_p: dict[str, dict[int, int]] = {}
        dep_asks_by_p: dict[str, dict[int, int]] = {}
        for product in config.products:
            orders_for_product = validated_orders.get(product, [])
            fills, unfilled, dep_bid, dep_ask = match_aggressive_orders(
                timestamp=ts,
                player_orders=orders_for_product,
                bot_bids=bot_bids_by_p[product],
                bot_asks=bot_asks_by_p[product],
            )
            cash_d, pos_d = apply_fills_to_account(fills)
            cash[product] += cash_d
            positions[product] += pos_d
            n_fills[product] += len(fills)
            passive_by_p[product] = unfilled
            dep_bids_by_p[product] = dep_bid
            dep_asks_by_p[product] = dep_ask

        # 3e. Phase 2: bot takers walk combined book; player passive may fill.
        tick_takers = takers_by_tick.get(tick, [])
        for product in config.products:
            takers_for_product = [t for t in tick_takers if t.product == product]
            if not takers_for_product:
                continue
            passive_fills = match_bot_taker_trades(
                bot_takers=takers_for_product,
                player_passive=passive_by_p[product],
                depleted_bid_inv=dep_bids_by_p[product],
                depleted_ask_inv=dep_asks_by_p[product],
            )
            cash_d, pos_d = apply_fills_to_account(passive_fills)
            cash[product] += cash_d
            positions[product] += pos_d
            n_fills[product] += len(passive_fills)

        # 3f. Mark to FV.
        equity_t = sum(
            cash[p] + positions[p] * float(fv_paths[p][tick])
            for p in config.products
        )
        per_tick_equity.append(equity_t)
        for p in config.products:
            per_tick_position[p].append(positions[p])

    # 4. Aggregate session-level stats.
    equity_arr = np.asarray(per_tick_equity)
    alpha, r2 = _fit_equity_slope(equity_arr)
    downside_dev = _downside_deviation(equity_arr)
    return SessionResult(
        seed=config.seed, n_ticks=config.n_ticks, products=config.products,
        per_tick_equity=tuple(per_tick_equity),
        per_tick_position={p: tuple(v) for p, v in per_tick_position.items()},
        per_tick_fv={p: tuple(fv_paths[p].tolist()) for p in config.products},
        final_pnl=float(equity_arr[-1]) if len(equity_arr) else 0.0,
        realized_alpha=alpha, realized_r2=r2,
        realized_downside_dev=downside_dev,
        n_fills=n_fills, n_orders_rejected_limit=n_rejected,
    )


def _fit_equity_slope(equity: np.ndarray) -> tuple[float, float]:
    """OLS slope of equity vs tick index, with R^2.

    Used as the session-stability metric. A genuine alpha appears as a
    high-slope, high-R^2 equity curve. Lucky one-day strategies produce
    high-slope but low-R^2 (jaggedy) curves.
    """
    n = len(equity)
    if n < 3:
        return (0.0, 0.0)
    x = np.arange(n, dtype=float)
    # OLS: slope = cov(x, y) / var(x). With x = arange(n), var(x) is fixed.
    x_mean = x.mean()
    y_mean = equity.mean()
    cov = float(np.sum((x - x_mean) * (equity - y_mean)))
    var_x = float(np.sum((x - x_mean) ** 2))
    if var_x == 0:
        return (0.0, 0.0)
    slope = cov / var_x
    intercept = y_mean - slope * x_mean
    y_pred = slope * x + intercept
    ss_res = float(np.sum((equity - y_pred) ** 2))
    ss_tot = float(np.sum((equity - y_mean) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return (slope, r2)


def _downside_deviation(equity: np.ndarray) -> float:
    """Std of negative returns (downside semi-deviation)."""
    if len(equity) < 2:
        return 0.0
    returns = np.diff(equity)
    negatives = returns[returns < 0]
    if len(negatives) == 0:
        return 0.0
    return float(math.sqrt(np.mean(negatives ** 2)))
