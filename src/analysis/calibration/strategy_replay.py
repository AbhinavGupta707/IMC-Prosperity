"""Replay any submitted Trader against ground-truth server FV.

Engine infra for retrospectively scoring a strategy on a round we
have a hold-1 trader log for. Given:

  - A submission .py file (the Trader class),
  - The recovered server FV stream for that day (from a hold-1 log),
  - The book snapshots for the same day (CSV or activity log),
  - The market trade tape,

this module replays the strategy tick-by-tick and produces per-quote
scoring data: where each quote sat relative to true FV, whether it
filled, and how the FV moved over the next N ticks (markout). The
output is a clean per-quote table the audit script aggregates into a
structural-edge verdict.

This is the building block for "is this strategy actually catching
mispricing or just lucky on this seed?" — without needing a generative
Monte Carlo. It works for any strategy + any round where we have a
hold-1 log to recover FV from.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from src.analysis.calibration.types import FactRow

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuoteScore:
    """Score for a single quote the strategy emitted at one tick."""

    timestamp: int
    product: str
    side: str  # "bid" or "ask"
    quote_price: int
    quoted_qty: int
    server_fv: float
    edge_at_quote: float  # signed: + means quote was on the favorable side of FV
    filled_qty: int  # 0 if no fill; else <= quoted_qty
    fill_price: int | None
    markout_h1: float | None  # server_fv(t+1) - quote_price (signed by side)
    markout_h5: float | None
    markout_h20: float | None
    markout_h50: float | None


@dataclass(frozen=True)
class ReplayResult:
    """Aggregate output of a strategy replay."""

    product: str
    n_ticks: int
    n_quotes: int
    n_fills: int
    quote_scores: tuple[QuoteScore, ...]
    realized_pnl: float
    edge_capture: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------- public API


def load_trader_class(submission_path: Path) -> Any:
    """Dynamically import a submission .py and return its Trader class.

    The submission file imports ``from datamodel import ...`` — we
    install our local ``src.datamodel`` under the name ``datamodel``
    in sys.modules before importing so the submission resolves it.
    """
    if "datamodel" not in sys.modules:
        from src import datamodel  # noqa: PLC0415
        sys.modules["datamodel"] = datamodel

    module_name = f"submission_{submission_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, submission_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load submission at {submission_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    # Register BEFORE exec_module so dataclass introspection (which looks
    # up cls.__module__ in sys.modules) finds the in-flight module.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if not hasattr(module, "Trader"):
        raise AttributeError(
            f"{submission_path} does not define a top-level Trader class"
        )
    return module.Trader


def replay_strategy(
    *,
    trader_factory: Any,
    facts: list[FactRow],
    market_trades_by_ts: dict[int, list[dict]],
    products: tuple[str, ...],
    position_limit: int = 80,
    markout_horizons: tuple[int, ...] = (1, 5, 20, 50),
) -> dict[str, ReplayResult]:
    """Replay a Trader against recovered server FV + book snapshots.

    For each tick, builds a TradingState (from the fact row's book + own
    position), calls Trader.run(state), captures returned orders, then
    simulates a simple fill model:

      - Aggressive orders (price crossing the visible book) fill against
        opposing levels in price-priority order, immediately.
      - Passive orders (resting at non-crossing prices) fill if the next
        tick's market trades print at or through them. Conservative:
        only count fills if at least one market trade printed at our
        exact price level.

    For each quote we record the quote price minus server FV (= edge),
    whether it filled, and FV markouts at horizons.

    The function does not import any of the engine codepath (signals,
    risk, fair_value modules) — it only needs the Trader.run interface.
    This makes the replay mechanism agnostic to which strategy is loaded.
    """
    from src.datamodel import (  # noqa: PLC0415
        Observation, Order, OrderDepth, Trade, TradingState,
    )

    trader = trader_factory()
    trader_data = ""
    facts_by_product_and_ts = _index_facts(facts)
    timestamps = sorted({f.timestamp for f in facts})
    fv_grid = {(f.product, f.timestamp): f.server_fv for f in facts}

    positions = {p: 0 for p in products}
    cash = {p: 0.0 for p in products}
    quote_scores: dict[str, list[QuoteScore]] = {p: [] for p in products}
    n_fills = {p: 0 for p in products}
    pending_orders: dict[str, list[Any]] = {p: [] for p in products}

    for ts in timestamps:
        order_depths: dict[str, OrderDepth] = {}
        for product in products:
            fact = facts_by_product_and_ts.get((product, ts))
            if fact is None:
                continue
            buy_orders = {lvl.price: lvl.volume for lvl in fact.bids}
            sell_orders = {lvl.price: -lvl.volume for lvl in fact.asks}
            order_depths[product] = OrderDepth(
                buy_orders=buy_orders, sell_orders=sell_orders,
            )

        # Settle pending passive orders against this tick's market trades.
        for product, pendings in list(pending_orders.items()):
            new_pending: list[Any] = []
            for order in pendings:
                trades_now = market_trades_by_ts.get(ts, [])
                product_trades = [t for t in trades_now if t["product"] == product]
                fill_qty = _check_passive_fill(order, product_trades)
                if fill_qty > 0:
                    n_fills[product] += 1
                    positions[product] += fill_qty if order.quantity > 0 else -fill_qty
                    cash[product] -= order.price * (fill_qty if order.quantity > 0 else -fill_qty)
                    # update last quote_score for this order:
                    if quote_scores[product]:
                        last = quote_scores[product][-1]
                        if last.timestamp <= ts and last.quote_price == order.price:
                            quote_scores[product][-1] = _with_fill(last, fill_qty, order.price)
                else:
                    new_pending.append(order)
            pending_orders[product] = new_pending

        state = TradingState(
            traderData=trader_data, timestamp=ts, listings={},
            order_depths=order_depths, own_trades={}, market_trades={},
            position={p: positions[p] for p in products},
            observations=Observation(),
        )
        try:
            orders, _, trader_data = trader.run(state)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Trader.run raised at t=%d: %s", ts, exc)
            orders = {}

        # P0-2 fix: enforce position limit per-product per-batch, matching
        # the generative_simulator.run_session semantics. If the entire
        # batch for a product would breach the limit (in either direction),
        # the entire batch is rejected for that product. This makes
        # strategy_replay's risk model consistent with MC's.
        validated_orders: dict[str, list] = {}
        for product, product_orders in orders.items():
            if product not in products:
                continue
            non_empty = [o for o in product_orders if o.quantity != 0]
            total_buy = sum(o.quantity for o in non_empty if o.quantity > 0)
            total_sell = sum(-o.quantity for o in non_empty if o.quantity < 0)
            current = positions[product]
            if (current + total_buy > position_limit
                    or current - total_sell < -position_limit):
                # Reject entire batch (matches generative_simulator + IMC semantics)
                continue
            validated_orders[product] = non_empty

        for product, product_orders in validated_orders.items():
            for order in product_orders:
                fv = fv_grid.get((product, ts))
                if fv is None:
                    continue
                side = "bid" if order.quantity > 0 else "ask"
                edge = fv - order.price if side == "bid" else order.price - fv
                # Aggressive vs passive:
                depth = order_depths.get(product)
                fill_qty = 0
                fill_price = None
                if depth is not None:
                    if side == "bid":
                        # Buy at order.price hits asks <= order.price
                        marketable_levels = sorted(
                            (p for p in depth.sell_orders if p <= order.price),
                        )
                        for lvl_price in marketable_levels:
                            available = -depth.sell_orders[lvl_price]
                            take = min(order.quantity - fill_qty, available)
                            if take <= 0:
                                continue
                            fill_qty += take
                            fill_price = lvl_price
                            cash[product] -= take * lvl_price
                            positions[product] += take
                            if fill_qty >= order.quantity:
                                break
                    else:
                        # Sell at order.price hits bids >= order.price
                        marketable_levels = sorted(
                            (p for p in depth.buy_orders if p >= order.price),
                            reverse=True,
                        )
                        for lvl_price in marketable_levels:
                            available = depth.buy_orders[lvl_price]
                            take = min(abs(order.quantity) - fill_qty, available)
                            if take <= 0:
                                continue
                            fill_qty += take
                            fill_price = lvl_price
                            cash[product] += take * lvl_price
                            positions[product] -= take
                            if fill_qty >= abs(order.quantity):
                                break
                if fill_qty > 0:
                    n_fills[product] += 1
                # Compute markouts
                markouts = {}
                for h in markout_horizons:
                    future_fv = fv_grid.get((product, ts + h * 100))
                    if future_fv is None:
                        markouts[h] = None
                    else:
                        markouts[h] = (
                            (future_fv - order.price)
                            if side == "bid"
                            else (order.price - future_fv)
                        )
                quote_scores[product].append(QuoteScore(
                    timestamp=ts, product=product, side=side,
                    quote_price=order.price, quoted_qty=abs(order.quantity),
                    server_fv=fv, edge_at_quote=edge,
                    filled_qty=fill_qty, fill_price=fill_price,
                    markout_h1=markouts.get(1),
                    markout_h5=markouts.get(5),
                    markout_h20=markouts.get(20),
                    markout_h50=markouts.get(50),
                ))
                # If unfilled, queue as passive for next tick's settlement
                if fill_qty < abs(order.quantity):
                    pending_orders[product].append(order)

    results: dict[str, ReplayResult] = {}
    for product in products:
        scores = quote_scores[product]
        # Mark-to-market PnL using last available FV.
        last_fv = max((f.server_fv for f in facts if f.product == product), default=0.0)
        realized = cash[product] + positions[product] * last_fv
        edge_capture = _compute_edge_capture(scores)
        results[product] = ReplayResult(
            product=product, n_ticks=len(timestamps),
            n_quotes=len(scores), n_fills=n_fills[product],
            quote_scores=tuple(scores), realized_pnl=realized,
            edge_capture=edge_capture,
        )
    return results


# ---------------------------------------------------------- internals


def _index_facts(facts: list[FactRow]) -> dict[tuple[str, int], FactRow]:
    return {(f.product, f.timestamp): f for f in facts}


def _check_passive_fill(order: Any, market_trades: list[dict]) -> int:
    """Return fill qty if a market trade printed at the order's price."""
    if not market_trades:
        return 0
    # If our order is a buy at price P, we fill when a market sell prints at P.
    matching = [t for t in market_trades if t["price"] == order.price]
    if not matching:
        return 0
    # Conservative: take 30% of the first matching trade's qty.
    available = sum(t["quantity"] for t in matching)
    desired = abs(order.quantity)
    return min(int(0.3 * available), desired)


def _with_fill(score: QuoteScore, fill_qty: int, fill_price: int) -> QuoteScore:
    """Return a new QuoteScore with fill fields updated."""
    return QuoteScore(
        timestamp=score.timestamp, product=score.product, side=score.side,
        quote_price=score.quote_price, quoted_qty=score.quoted_qty,
        server_fv=score.server_fv, edge_at_quote=score.edge_at_quote,
        filled_qty=score.filled_qty + fill_qty,
        fill_price=fill_price if score.fill_price is None else score.fill_price,
        markout_h1=score.markout_h1, markout_h5=score.markout_h5,
        markout_h20=score.markout_h20, markout_h50=score.markout_h50,
    )


def _compute_edge_capture(scores: list[QuoteScore]) -> dict[str, float]:
    """Aggregate quote-level edges into summary statistics.

    Returns:
        - mean_edge_per_quote
        - mean_edge_per_fill
        - mean_markout_h{1,5,20,50}_per_fill
        - fill_rate (n_fills / n_quotes)
    """
    if not scores:
        return {}
    n = len(scores)
    fills = [s for s in scores if s.filled_qty > 0]
    out: dict[str, float] = {
        "mean_edge_per_quote": sum(s.edge_at_quote for s in scores) / n,
        "fill_rate": len(fills) / n,
    }
    if fills:
        out["mean_edge_per_fill"] = sum(s.edge_at_quote for s in fills) / len(fills)
        for label, attr in (
            ("mean_markout_h1_per_fill", "markout_h1"),
            ("mean_markout_h5_per_fill", "markout_h5"),
            ("mean_markout_h20_per_fill", "markout_h20"),
            ("mean_markout_h50_per_fill", "markout_h50"),
        ):
            valid = [getattr(s, attr) for s in fills if getattr(s, attr) is not None]
            if valid:
                out[label] = sum(valid) / len(valid)
    return out
