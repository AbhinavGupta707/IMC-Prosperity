"""Offline backtest simulator.

Drives a ``Trader`` against a ``ReplayEngine`` stream, applies taker
fills immediately and passive fills with a one-step delay, tracks
per-product cash, position, and maker/taker decomposition, and produces
a ``SimulationResult`` at the end.

Order lifecycle matches Prosperity semantics:

- At step T, we observe a book and the market trades that happened in
  the interval ending at T. We score any maker residual from step T-1
  against those trades first (passive phase).
- We then call ``Trader.run(state)``. The returned orders are scored
  against step T's visible book (taker phase). Marketable portions
  fill immediately; non-marketable orders become the next step's
  pending residual.
- Partial residuals from a partially-taker-filled order are dropped
  because Prosperity cancels unfilled remainders at iteration end.

Phase 4a adds per-trade records with decision and fill context,
step-indexed time series for mids / fair values / PnL, and
quantity-weighted aggregates (entry edge, markouts at +1/+5/+20).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.backtest.fill_model import Fill, FillModel
from src.backtest.metrics import (
    ProductResult,
    SimulationResult,
    TimeSeries,
    TradeRecord,
    TradeSide,
    compute_entry_edges,
    compute_markouts,
)
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.core.config import EngineConfig
from src.datamodel import Order, OrderDepth, Trade, TradingState
from src.trader import Trader

_NEAR_LIMIT_FRACTION = 0.75
MARKOUT_HORIZONS: tuple[int, ...] = (1, 5, 20)


@dataclass
class _ProductAccounting:
    cash: float = 0.0
    position: int = 0
    trade_count: int = 0
    order_count: int = 0
    taker_trade_count: int = 0
    maker_trade_count: int = 0
    taker_trade_quantity: int = 0
    maker_trade_quantity: int = 0
    buy_trade_quantity: int = 0
    sell_trade_quantity: int = 0
    mark_price: float | None = None
    steps_near_limit: int = 0
    seen: bool = False


@dataclass(frozen=True)
class _DecisionContext:
    """Frozen snapshot of what we believed when an order was sent."""

    decision_timestamp: int
    decision_day: int | None
    fair_value: float | None
    fair_value_method: str | None
    mid: float | None


@dataclass(frozen=True)
class _PendingMakerOrder:
    """A resting maker order carrying its decision-time context forward."""

    order: Order
    decision: _DecisionContext


@dataclass
class _RunState:
    trader_data: str = ""
    pending_maker: dict[str, list[_PendingMakerOrder]] = field(default_factory=dict)
    recent_own_trades: dict[str, list[Trade]] = field(default_factory=dict)


class BacktestSimulator:
    def __init__(
        self,
        trader: Trader,
        fill_model: FillModel | None = None,
    ) -> None:
        self.trader = trader
        self.fill_model = fill_model or FillModel()

    def run(self, replay: ReplayEngine) -> SimulationResult:
        books: dict[str, _ProductAccounting] = defaultdict(_ProductAccounting)
        run_state = _RunState()
        limits = _position_limits(self.trader.config)
        step_count = 0

        trade_records: list[TradeRecord] = []
        mid_series: dict[str, list[tuple[int, float]]] = defaultdict(list)
        fair_value_series: dict[str, list[tuple[int, float]]] = defaultdict(list)
        pnl_series: dict[str, list[tuple[int, float]]] = defaultdict(list)
        mid_keys: dict[str, list[tuple[int | None, int]]] = defaultdict(list)
        fair_value_keys: dict[str, list[tuple[int | None, int]]] = defaultdict(list)
        pnl_keys: dict[str, list[tuple[int | None, int]]] = defaultdict(list)
        last_seen_mid: dict[str, float] = {}

        for step in replay.iter_steps():
            step_count += 1
            state = self._build_state(step, run_state, books)

            fills_this_step: dict[str, list[Fill]] = defaultdict(list)

            # --- passive phase: score last step's residuals against this step's trades
            for product, pending in run_state.pending_maker.items():
                if not pending:
                    continue
                product_trades = state.market_trades.get(product, [])
                orders = [item.order for item in pending]
                passive_fills = self.fill_model.score_passive_fills(
                    orders, product_trades, timestamp=step.timestamp
                )
                if not passive_fills:
                    continue

                # Map each resting price/side to its decision context so the
                # passive-fill bookkeeping can look it up. Multiple pending
                # orders on the same side at the same price collapse to the
                # latest decision, which is a principled tiebreaker (we
                # believed it most recently) and conservative when all
                # pending orders share the same step anyway.
                contexts: dict[int, _DecisionContext] = {}
                for item in pending:
                    key = _price_side_key(item.order.price, item.order.quantity)
                    contexts[key] = item.decision

                for fill in passive_fills:
                    self._apply_fill(books[product], fill)
                    fills_this_step[product].append(fill)
                    context = _lookup_context(contexts, fill)
                    mid_at_fill = _mid_from_depth(state.order_depths.get(product))
                    trade_records.append(
                        _build_trade_record(
                            product=product,
                            fill=fill,
                            fill_timestamp=step.timestamp,
                            fill_day=step.day,
                            decision=context,
                            mid_at_fill=mid_at_fill,
                        )
                    )

            # --- trader call
            if hasattr(self.trader, "logger") and hasattr(self.trader.logger, "events"):
                self.trader.logger.events.clear()
            orders_by_product, _, run_state.trader_data = self.trader.run(state)

            # --- pull decision-time context out of the trader log
            decision_by_product = _collect_decision_contexts(
                self.trader,
                step_day=step.day,
                step_timestamp=step.timestamp,
                order_depths=state.order_depths,
            )

            # --- taker phase + residual handoff
            next_pending: dict[str, list[_PendingMakerOrder]] = {}
            for product, product_orders in orders_by_product.items():
                books[product].order_count += len(product_orders)
                depth = state.order_depths.get(product)
                if depth is None or not product_orders:
                    next_pending[product] = []
                    continue

                decision_context = decision_by_product.get(
                    product,
                    _DecisionContext(
                        decision_timestamp=step.timestamp,
                        decision_day=step.day,
                        fair_value=None,
                        fair_value_method=None,
                        mid=_mid_from_depth(depth),
                    ),
                )

                split = self.fill_model.split_taker_and_residual(
                    product_orders, depth, timestamp=step.timestamp
                )
                for fill in split.fills:
                    self._apply_fill(books[product], fill)
                    fills_this_step[product].append(fill)
                    trade_records.append(
                        _build_trade_record(
                            product=product,
                            fill=fill,
                            fill_timestamp=step.timestamp,
                            fill_day=step.day,
                            decision=decision_context,
                            mid_at_fill=_mid_from_depth(depth),
                        )
                    )
                next_pending[product] = [
                    _PendingMakerOrder(order=order, decision=decision_context)
                    for order in split.pending_maker
                ]

            # --- mark-to-market, series, and near-limit tracking
            for product, depth in state.order_depths.items():
                accounting = books[product]
                accounting.seen = True
                mark = _mid_from_depth(depth)
                if mark is not None:
                    accounting.mark_price = mark
                    mid_series[product].append((step.timestamp, mark))
                    mid_keys[product].append((step.day, step.timestamp))
                    last_seen_mid[product] = mark
                limit = limits.get(product)
                if limit and abs(accounting.position) >= _NEAR_LIMIT_FRACTION * limit:
                    accounting.steps_near_limit += 1

            # Fair-value series from the decision log (always for every
            # product the trader priced this step, including zero-order
            # steps).
            for product, context in decision_by_product.items():
                if context.fair_value is not None:
                    fair_value_series[product].append((step.timestamp, context.fair_value))
                    fair_value_keys[product].append((context.decision_day, step.timestamp))

            # PnL series: one entry per seen product per step, with
            # carry-forward mid when the book is one-sided and no mark
            # is available this step.
            for product, accounting in books.items():
                if not accounting.seen:
                    continue
                carry_mark = last_seen_mid.get(product)
                if carry_mark is None:
                    pnl = accounting.cash
                else:
                    pnl = accounting.cash + accounting.position * carry_mark
                pnl_series[product].append((step.timestamp, pnl))
                pnl_keys[product].append((step.day, step.timestamp))

            run_state.pending_maker = next_pending
            run_state.recent_own_trades = {
                product: [fill.trade for fill in fills]
                for product, fills in fills_this_step.items()
            }

        return self._finalize(
            step_count=step_count,
            books=books,
            trade_records=trade_records,
            mid_series=mid_series,
            fair_value_series=fair_value_series,
            pnl_series=pnl_series,
            mid_keys=mid_keys,
            fair_value_keys=fair_value_keys,
            pnl_keys=pnl_keys,
        )

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _build_state(
        step: ReplayStep,
        run_state: _RunState,
        books: dict[str, _ProductAccounting],
    ) -> TradingState:
        position = {product: acct.position for product, acct in books.items()}
        return ReplayEngine.build_trading_state(
            step,
            trader_data=run_state.trader_data,
            position=position,
            own_trades=run_state.recent_own_trades,
        )

    @staticmethod
    def _apply_fill(accounting: _ProductAccounting, fill: Fill) -> None:
        trade = fill.trade
        quantity = trade.quantity
        if trade.buyer == "SELF":
            accounting.position += quantity
            accounting.cash -= float(trade.price) * quantity
            accounting.buy_trade_quantity += quantity
        else:
            accounting.position -= quantity
            accounting.cash += float(trade.price) * quantity
            accounting.sell_trade_quantity += quantity
        accounting.trade_count += 1
        if fill.mode == "taker":
            accounting.taker_trade_count += 1
            accounting.taker_trade_quantity += quantity
        else:
            accounting.maker_trade_count += 1
            accounting.maker_trade_quantity += quantity

    @staticmethod
    def _finalize(
        *,
        step_count: int,
        books: dict[str, _ProductAccounting],
        trade_records: list[TradeRecord],
        mid_series: dict[str, list[tuple[int, float]]],
        fair_value_series: dict[str, list[tuple[int, float]]],
        pnl_series: dict[str, list[tuple[int, float]]],
        mid_keys: dict[str, list[tuple[int | None, int]]],
        fair_value_keys: dict[str, list[tuple[int | None, int]]],
        pnl_keys: dict[str, list[tuple[int | None, int]]],
    ) -> SimulationResult:
        frozen_mid_series: dict[str, TimeSeries] = {
            product: tuple(series) for product, series in mid_series.items()
        }
        frozen_fv_series: dict[str, TimeSeries] = {
            product: tuple(series) for product, series in fair_value_series.items()
        }
        frozen_pnl_series: dict[str, TimeSeries] = {
            product: tuple(series) for product, series in pnl_series.items()
        }
        frozen_mid_keys = {product: tuple(keys) for product, keys in mid_keys.items()}
        frozen_fv_keys = {product: tuple(keys) for product, keys in fair_value_keys.items()}
        frozen_pnl_keys = {product: tuple(keys) for product, keys in pnl_keys.items()}

        records_tuple = tuple(trade_records)
        edge_per_product = compute_entry_edges(records_tuple)
        markouts_per_product = compute_markouts(
            records_tuple,
            frozen_mid_series,
            MARKOUT_HORIZONS,
            mid_keys=frozen_mid_keys,
        )

        per_product: dict[str, ProductResult] = {}
        total_pnl = 0.0
        for product, acct in books.items():
            if not acct.seen and acct.trade_count == 0:
                continue
            mark = acct.mark_price or 0.0
            pnl = acct.cash + acct.position * mark
            total_pnl += pnl

            edge_avg, edge_count = edge_per_product.get(product, (None, 0))
            product_markouts = markouts_per_product.get(product, {})
            mk1_avg, mk1_count = product_markouts.get(1, (None, 0))
            mk5_avg, mk5_count = product_markouts.get(5, (None, 0))
            mk20_avg, mk20_count = product_markouts.get(20, (None, 0))

            per_product[product] = ProductResult(
                product=product,
                pnl=pnl,
                cash=acct.cash,
                final_position=acct.position,
                mark_price=acct.mark_price,
                order_count=acct.order_count,
                trade_count=acct.trade_count,
                taker_trade_count=acct.taker_trade_count,
                maker_trade_count=acct.maker_trade_count,
                taker_trade_quantity=acct.taker_trade_quantity,
                maker_trade_quantity=acct.maker_trade_quantity,
                buy_trade_quantity=acct.buy_trade_quantity,
                sell_trade_quantity=acct.sell_trade_quantity,
                steps_near_limit=acct.steps_near_limit,
                avg_entry_edge=edge_avg,
                entry_edge_count=edge_count,
                avg_markout_1=mk1_avg,
                markout_1_count=mk1_count,
                avg_markout_5=mk5_avg,
                markout_5_count=mk5_count,
                avg_markout_20=mk20_avg,
                markout_20_count=mk20_count,
            )

        return SimulationResult(
            steps=step_count,
            total_pnl=total_pnl,
            per_product=per_product,
            trade_records=records_tuple,
            mid_series=frozen_mid_series,
            fair_value_series=frozen_fv_series,
            pnl_series=frozen_pnl_series,
            mid_keys=frozen_mid_keys,
            fair_value_keys=frozen_fv_keys,
            pnl_keys=frozen_pnl_keys,
        )


# ------------------------------------------------------------ free helpers


def _mid_from_depth(depth: OrderDepth | None) -> float | None:
    if depth is None or not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0


def _position_limits(config: EngineConfig) -> dict[str, int]:
    return {product: cfg.position_limit for product, cfg in config.products.items()}


def _collect_decision_contexts(
    trader: Trader,
    *,
    step_day: int | None,
    step_timestamp: int,
    order_depths: dict[str, OrderDepth],
) -> dict[str, _DecisionContext]:
    """Walk the trader's (per-step, freshly-cleared) decision log.

    The simulator clears ``trader.logger.events`` immediately before
    calling ``run``, so everything we see here was emitted during the
    current step. We combine that with the step's visible mid so the
    decision context captures both what the trader believed fair
    value was *and* the observable book at the moment it decided.
    """
    contexts: dict[str, _DecisionContext] = {}
    if not hasattr(trader, "logger") or not hasattr(trader.logger, "events"):
        return contexts
    for event in trader.logger.events:
        product = event.get("product")
        if not isinstance(product, str):
            continue
        fair_value = event.get("fair_value")
        method = event.get("method")
        contexts[product] = _DecisionContext(
            decision_timestamp=step_timestamp,
            decision_day=step_day,
            fair_value=(float(fair_value) if isinstance(fair_value, (int, float)) else None),
            fair_value_method=method if isinstance(method, str) else None,
            mid=_mid_from_depth(order_depths.get(product)),
        )
    return contexts


def _price_side_key(price: int, signed_quantity: int) -> int:
    """Pack (price, side) into a single int key.

    We use the sign of the price: buy keys are positive, sell keys are
    negative. Works because Prosperity prices are positive integers.
    """
    return price if signed_quantity > 0 else -price


def _lookup_context(contexts: dict[int, _DecisionContext], fill: Fill) -> _DecisionContext:
    """Find the decision context that matches a passive fill's side."""
    # If SELF is the buyer, we rested a buy at that price.
    trade = fill.trade
    sign = 1 if trade.buyer == "SELF" else -1
    key = _price_side_key(int(trade.price), sign)
    ctx = contexts.get(key)
    if ctx is not None:
        return ctx
    # Defensive fallback: return a context with no decision data
    # rather than raising. This should never hit in practice because
    # the passive fill engine only credits orders we submitted.
    return _DecisionContext(
        decision_timestamp=trade.timestamp,
        decision_day=None,
        fair_value=None,
        fair_value_method=None,
        mid=None,
    )


def _build_trade_record(
    *,
    product: str,
    fill: Fill,
    fill_timestamp: int,
    fill_day: int | None,
    decision: _DecisionContext,
    mid_at_fill: float | None,
) -> TradeRecord:
    trade = fill.trade
    side: TradeSide = "buy" if trade.buyer == "SELF" else "sell"
    return TradeRecord(
        product=product,
        side=side,
        price=float(trade.price),
        quantity=int(trade.quantity),
        mode=fill.mode,
        decision_timestamp=decision.decision_timestamp,
        fill_timestamp=fill_timestamp,
        fair_value_at_decision=decision.fair_value,
        fair_value_method_at_decision=decision.fair_value_method,
        mid_at_decision=decision.mid,
        mid_at_fill=mid_at_fill,
        decision_day=decision.decision_day,
        fill_day=fill_day,
    )
