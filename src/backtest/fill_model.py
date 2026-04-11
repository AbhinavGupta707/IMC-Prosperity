"""Backtest fill model with taker and conservative passive fills.

Two-phase lifecycle, matching how Prosperity actually works:

1. **Taker phase.** Immediately after ``Trader.run`` returns, we walk
   each order against the visible book. Any marketable portion fills
   at the visible prices; any non-marketable portion (a pure maker
   quote) becomes *pending* for the next step. A partially-taker-filled
   order's residual is dropped because Prosperity cancels unfilled
   order remainders at iteration end.

2. **Passive phase.** At the start of the NEXT step, pending maker
   orders are matched against that step's observed market trades. A
   market trade at exactly our price is evidence that our resting
   level got touched. We credit ourselves with a fractional share of
   the traded quantity (``passive_allocation``, default 0.3) to avoid
   fantasy PnL from assuming we were the only maker at that price.

The fill model knows nothing about the simulator's cash/position
bookkeeping. It returns structured ``Fill`` records and the simulator
applies them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from src.datamodel import Order, OrderDepth, Trade

_SELF_USER_ID = "SELF"
FillMode = Literal["taker", "maker"]


@dataclass(frozen=True)
class Fill:
    trade: Trade
    mode: FillMode


@dataclass(frozen=True)
class TakerSplitResult:
    fills: list[Fill]
    pending_maker: list[Order]


@dataclass(frozen=True)
class FillModelConfig:
    passive_allocation: float = 0.3
    passive_fills_enabled: bool = True


class FillModel:
    def __init__(self, config: FillModelConfig | None = None) -> None:
        self.config = config or FillModelConfig()
        if not 0.0 <= self.config.passive_allocation <= 1.0:
            raise ValueError("passive_allocation must be in [0, 1]")

    # --------------------------------------------------------- taker phase

    def split_taker_and_residual(
        self,
        orders: list[Order],
        order_depth: OrderDepth,
        *,
        timestamp: int,
    ) -> TakerSplitResult:
        """Apply taker fills and return pending maker residuals.

        For each order:
        - If any part of it is marketable against the visible book, the
          marketable quantity fills and the residual is dropped.
        - If the entire order is non-marketable (a pure maker quote),
          the full order is kept as pending for the passive phase.
        """
        fills: list[Fill] = []
        pending: list[Order] = []

        asks = {int(price): abs(int(volume)) for price, volume in order_depth.sell_orders.items()}
        bids = {int(price): int(volume) for price, volume in order_depth.buy_orders.items()}

        for order in orders:
            if order.quantity == 0:
                continue
            if order.quantity > 0:
                filled, remaining = _match_buy(order, asks, timestamp)
                fills.extend(filled)
                if not filled:
                    # Non-marketable: fully maker.
                    pending.append(order)
                # Partial or full taker fill: residual dropped.
                del remaining
            else:
                filled, remaining = _match_sell(order, bids, timestamp)
                fills.extend(filled)
                if not filled:
                    pending.append(order)
                del remaining

        return TakerSplitResult(fills=fills, pending_maker=pending)

    # ------------------------------------------------------- passive phase

    def score_passive_fills(
        self,
        pending_orders: list[Order],
        market_trades: list[Trade],
        *,
        timestamp: int,
    ) -> list[Fill]:
        """Match resting maker orders against observed market trades.

        A market trade at price P is treated as evidence that liquidity
        changed hands at that level. For each of our pending maker
        orders at P, we credit ourselves with
        ``floor(trade.quantity * passive_allocation)`` units up to our
        remaining size. A single trade cannot fill more than its own
        quantity and cannot double-fill a buy + sell at the same price.
        """
        if not self.config.passive_fills_enabled or not pending_orders or not market_trades:
            return []

        remaining_buy: dict[int, int] = defaultdict(int)
        remaining_sell: dict[int, int] = defaultdict(int)
        for order in pending_orders:
            if order.quantity > 0:
                remaining_buy[order.price] += order.quantity
            elif order.quantity < 0:
                remaining_sell[order.price] += -order.quantity

        fills: list[Fill] = []
        allocation = self.config.passive_allocation

        for trade in market_trades:
            trade_remaining = int(trade.quantity)
            if trade_remaining <= 0:
                continue

            # Passive buy at this price? Credit up to our share.
            if remaining_buy.get(trade.price, 0) > 0 and trade_remaining > 0:
                share = min(
                    remaining_buy[trade.price],
                    int(trade_remaining * allocation),
                )
                if share > 0:
                    fills.append(
                        Fill(
                            trade=Trade(
                                symbol=trade.symbol,
                                price=trade.price,
                                quantity=share,
                                buyer=_SELF_USER_ID,
                                seller=None,
                                timestamp=timestamp,
                            ),
                            mode="maker",
                        )
                    )
                    remaining_buy[trade.price] -= share
                    trade_remaining -= share

            # Passive sell at this price? Credit up to our share.
            if remaining_sell.get(trade.price, 0) > 0 and trade_remaining > 0:
                share = min(
                    remaining_sell[trade.price],
                    int(trade_remaining * allocation),
                )
                if share > 0:
                    fills.append(
                        Fill(
                            trade=Trade(
                                symbol=trade.symbol,
                                price=trade.price,
                                quantity=share,
                                buyer=None,
                                seller=_SELF_USER_ID,
                                timestamp=timestamp,
                            ),
                            mode="maker",
                        )
                    )
                    remaining_sell[trade.price] -= share

        return fills


# ------------------------------------------------------------- matching


def _match_buy(order: Order, asks: dict[int, int], timestamp: int) -> tuple[list[Fill], int]:
    remaining = order.quantity
    filled: list[Fill] = []
    for price in sorted(asks):
        if remaining <= 0 or price > order.price:
            break
        available = asks[price]
        if available <= 0:
            continue
        fill_qty = min(available, remaining)
        filled.append(
            Fill(
                trade=Trade(
                    symbol=order.symbol,
                    price=price,
                    quantity=fill_qty,
                    buyer=_SELF_USER_ID,
                    seller=None,
                    timestamp=timestamp,
                ),
                mode="taker",
            )
        )
        asks[price] = available - fill_qty
        remaining -= fill_qty
    return filled, remaining


def _match_sell(order: Order, bids: dict[int, int], timestamp: int) -> tuple[list[Fill], int]:
    remaining = -order.quantity
    filled: list[Fill] = []
    for price in sorted(bids, reverse=True):
        if remaining <= 0 or price < order.price:
            break
        available = bids[price]
        if available <= 0:
            continue
        fill_qty = min(available, remaining)
        filled.append(
            Fill(
                trade=Trade(
                    symbol=order.symbol,
                    price=price,
                    quantity=fill_qty,
                    buyer=None,
                    seller=_SELF_USER_ID,
                    timestamp=timestamp,
                ),
                mode="taker",
            )
        )
        bids[price] = available - fill_qty
        remaining -= fill_qty
    return filled, remaining
