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

Phase 2B scope keeps things focused: maker/taker counters and
time-near-limit tracking. Markouts and charts land in Phase 4.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.backtest.fill_model import Fill, FillModel
from src.backtest.metrics import ProductResult, SimulationResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.core.config import EngineConfig
from src.datamodel import Order, OrderDepth, Trade, TradingState
from src.trader import Trader

_NEAR_LIMIT_FRACTION = 0.75


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
    _seen: bool = False


@dataclass
class _RunState:
    trader_data: str = ""
    pending_maker: dict[str, list[Order]] = field(default_factory=dict)
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

        for step in replay.iter_steps():
            step_count += 1
            state = self._build_state(step, run_state, books)

            fills_this_step: dict[str, list[Fill]] = defaultdict(list)

            # --- passive phase: score last step's residuals against this step's trades
            for product, orders in run_state.pending_maker.items():
                if not orders:
                    continue
                product_trades = state.market_trades.get(product, [])
                passive_fills = self.fill_model.score_passive_fills(
                    orders, product_trades, timestamp=step.timestamp
                )
                for fill in passive_fills:
                    self._apply_fill(books[product], fill)
                    fills_this_step[product].append(fill)

            # --- trader call
            orders_by_product, _, run_state.trader_data = self.trader.run(state)

            # --- taker phase + residual handoff
            next_pending: dict[str, list[Order]] = {}
            for product, product_orders in orders_by_product.items():
                books[product].order_count += len(product_orders)
                depth = state.order_depths.get(product)
                if depth is None or not product_orders:
                    next_pending[product] = []
                    continue
                split = self.fill_model.split_taker_and_residual(
                    product_orders, depth, timestamp=step.timestamp
                )
                for fill in split.fills:
                    self._apply_fill(books[product], fill)
                    fills_this_step[product].append(fill)
                next_pending[product] = split.pending_maker

            # --- mark-to-market and near-limit tracking
            for product, depth in state.order_depths.items():
                accounting = books[product]
                accounting._seen = True
                mark = _mid_from_depth(depth)
                if mark is not None:
                    accounting.mark_price = mark
                limit = limits.get(product)
                if limit and abs(accounting.position) >= _NEAR_LIMIT_FRACTION * limit:
                    accounting.steps_near_limit += 1

            run_state.pending_maker = next_pending
            run_state.recent_own_trades = {
                product: [fill.trade for fill in fills]
                for product, fills in fills_this_step.items()
            }

        return self._finalize(step_count, books)

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
    def _finalize(steps: int, books: dict[str, _ProductAccounting]) -> SimulationResult:
        per_product: dict[str, ProductResult] = {}
        total_pnl = 0.0
        for product, acct in books.items():
            if not acct._seen and acct.trade_count == 0:
                continue
            mark = acct.mark_price or 0.0
            pnl = acct.cash + acct.position * mark
            total_pnl += pnl
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
            )
        return SimulationResult(steps=steps, total_pnl=total_pnl, per_product=per_product)


def _mid_from_depth(depth: OrderDepth) -> float | None:
    if not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0


def _position_limits(config: EngineConfig) -> dict[str, int]:
    return {product: cfg.position_limit for product, cfg in config.products.items()}
