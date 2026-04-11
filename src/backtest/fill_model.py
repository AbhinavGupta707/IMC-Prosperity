"""Conservative fill model for the offline backtest simulator.

Phase 2A scope: *taker fills only*. An order is considered filled only
if it is marketable against the visible book the exchange published for
that timestamp. Passive orders — i.e. maker quotes that rest inside the
spread — produce no fills by default.

Rationale: the plan is explicit that optimistic passive fills produce
fantasy PnL. Better to start with a strict taker-only model and later
add heuristic passive fills (Phase 4) only once we can observe maker
behavior against real trade tapes.

The fill model operates on a *mutable copy* of the order depth so a
sequence of orders from one iteration shares liquidity correctly: if the
first buy consumes the whole top ask level, the second buy walks into
the next ask level.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.datamodel import Order, OrderDepth, Trade

_SELF_USER_ID = "SELF"


@dataclass(frozen=True)
class FillModelConfig:
    passive_fills_enabled: bool = False


class FillModel:
    def __init__(self, config: FillModelConfig | None = None) -> None:
        self.config = config or FillModelConfig()

    def fill_orders(
        self,
        orders: list[Order],
        order_depth: OrderDepth,
        *,
        timestamp: int,
    ) -> list[Trade]:
        """Fill a batch of orders against a single product's order depth.

        Returns a list of ``Trade`` objects tagged with ``SELF`` as the
        initiator. The ``order_depth`` passed in is *not* mutated; a
        local copy is used.
        """
        trades: list[Trade] = []
        asks = {int(price): abs(int(volume)) for price, volume in order_depth.sell_orders.items()}
        bids = {int(price): int(volume) for price, volume in order_depth.buy_orders.items()}

        for order in orders:
            if order.quantity > 0:
                trades.extend(self._match_buy(order, asks, timestamp))
            elif order.quantity < 0:
                trades.extend(self._match_sell(order, bids, timestamp))

        return trades

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _match_buy(order: Order, asks: dict[int, int], timestamp: int) -> list[Trade]:
        remaining = order.quantity
        filled: list[Trade] = []
        for price in sorted(asks):
            if remaining <= 0 or price > order.price:
                break
            available = asks[price]
            if available <= 0:
                continue
            fill_qty = min(available, remaining)
            filled.append(
                Trade(
                    symbol=order.symbol,
                    price=price,
                    quantity=fill_qty,
                    buyer=_SELF_USER_ID,
                    seller=None,
                    timestamp=timestamp,
                )
            )
            asks[price] = available - fill_qty
            remaining -= fill_qty
        return filled

    @staticmethod
    def _match_sell(order: Order, bids: dict[int, int], timestamp: int) -> list[Trade]:
        remaining = -order.quantity
        filled: list[Trade] = []
        for price in sorted(bids, reverse=True):
            if remaining <= 0 or price < order.price:
                break
            available = bids[price]
            if available <= 0:
                continue
            fill_qty = min(available, remaining)
            filled.append(
                Trade(
                    symbol=order.symbol,
                    price=price,
                    quantity=fill_qty,
                    buyer=None,
                    seller=_SELF_USER_ID,
                    timestamp=timestamp,
                )
            )
            bids[price] = available - fill_qty
            remaining -= fill_qty
        return filled
