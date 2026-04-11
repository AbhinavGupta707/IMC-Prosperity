"""Offline backtest simulator.

Drives a ``Trader`` against a ``ReplayEngine`` stream, applies fills via
a ``FillModel``, tracks per-product cash and position, and produces a
``SimulationResult`` at the end.

This is the only place in the engine that tracks PnL. Strategies and
core modules never touch cash. Position, cash, and fill attribution all
live here because they are simulator concerns, not live-engine concerns.

Phase 2A scope deliberately keeps things simple:

- taker-only fill model (via ``FillModel``)
- mark-to-market at the last observed mid per product
- no slippage modeling beyond visible-book consumption
- no latency modeling
- no maker fill heuristics

Phase 2B will add markouts, maker/taker decomposition, and reporting.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.backtest.fill_model import FillModel
from src.backtest.metrics import ProductResult, SimulationResult
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.datamodel import OrderDepth, Trade, TradingState
from src.trader import Trader


@dataclass
class _ProductAccounting:
    cash: float = 0.0
    position: int = 0
    trade_count: int = 0
    order_count: int = 0
    buy_trade_quantity: int = 0
    sell_trade_quantity: int = 0
    mark_price: float | None = None


class BacktestSimulator:
    def __init__(self, trader: Trader, fill_model: FillModel | None = None) -> None:
        self.trader = trader
        self.fill_model = fill_model or FillModel()

    def run(self, replay: ReplayEngine) -> SimulationResult:
        books: dict[str, _ProductAccounting] = defaultdict(_ProductAccounting)
        trader_data = ""
        recent_own_trades: dict[str, list[Trade]] = {}
        step_count = 0

        for step in replay.iter_steps():
            step_count += 1
            state = self._build_state(step, trader_data, books, recent_own_trades)
            orders, _, trader_data = self.trader.run(state)

            next_own_trades: dict[str, list[Trade]] = {}
            for product, product_orders in orders.items():
                accounting = books[product]
                accounting.order_count += len(product_orders)
                depth = state.order_depths.get(product)
                if depth is None or not product_orders:
                    continue
                fills = self.fill_model.fill_orders(product_orders, depth, timestamp=step.timestamp)
                for fill in fills:
                    self._apply_fill(accounting, fill)
                if fills:
                    next_own_trades[product] = fills

            for product, depth in state.order_depths.items():
                mark = _mid_from_depth(depth)
                if mark is not None:
                    books[product].mark_price = mark

            recent_own_trades = next_own_trades

        return self._finalize(step_count, books)

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _build_state(
        step: ReplayStep,
        trader_data: str,
        books: dict[str, _ProductAccounting],
        recent_own_trades: dict[str, list[Trade]],
    ) -> TradingState:
        position = {product: acct.position for product, acct in books.items()}
        return ReplayEngine.build_trading_state(
            step,
            trader_data=trader_data,
            position=position,
            own_trades=recent_own_trades,
        )

    @staticmethod
    def _apply_fill(accounting: _ProductAccounting, fill: Trade) -> None:
        quantity = fill.quantity
        if fill.buyer == "SELF":
            accounting.position += quantity
            accounting.cash -= float(fill.price) * quantity
            accounting.buy_trade_quantity += quantity
        else:
            accounting.position -= quantity
            accounting.cash += float(fill.price) * quantity
            accounting.sell_trade_quantity += quantity
        accounting.trade_count += 1

    @staticmethod
    def _finalize(steps: int, books: dict[str, _ProductAccounting]) -> SimulationResult:
        per_product: dict[str, ProductResult] = {}
        total_pnl = 0.0
        for product, acct in books.items():
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
                buy_trade_quantity=acct.buy_trade_quantity,
                sell_trade_quantity=acct.sell_trade_quantity,
            )
        return SimulationResult(steps=steps, total_pnl=total_pnl, per_product=per_product)


def _mid_from_depth(depth: OrderDepth) -> float | None:
    if not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
