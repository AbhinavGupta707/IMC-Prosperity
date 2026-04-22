from __future__ import annotations

from src.core.config_core import ProductConfig
from src.core.types import NormalizedSnapshot, SignalIntent
from src.datamodel import Order


class ExecutionEngine:
    def generate_orders(
        self,
        snapshot: NormalizedSnapshot,
        intent: SignalIntent,
        config: ProductConfig,
    ) -> list[Order]:
        orders: list[Order] = []

        remaining_buy = config.max_aggressive_size
        remaining_sell = config.max_aggressive_size

        if intent.buy_below is not None:
            for ask in snapshot.asks:
                if ask.price > intent.buy_below or remaining_buy <= 0:
                    break
                quantity = min(ask.volume, remaining_buy)
                if quantity > 0:
                    orders.append(Order(snapshot.product, ask.price, quantity))
                    remaining_buy -= quantity

        if intent.sell_above is not None:
            for bid in snapshot.bids:
                if bid.price < intent.sell_above or remaining_sell <= 0:
                    break
                quantity = min(bid.volume, remaining_sell)
                if quantity > 0:
                    orders.append(Order(snapshot.product, bid.price, -quantity))
                    remaining_sell -= quantity

        if intent.quote is not None:
            if intent.quote.bid_price is not None and intent.quote.bid_size > 0:
                orders.append(
                    Order(snapshot.product, intent.quote.bid_price, intent.quote.bid_size)
                )
            if intent.quote.ask_price is not None and intent.quote.ask_size > 0:
                orders.append(
                    Order(snapshot.product, intent.quote.ask_price, -intent.quote.ask_size)
                )

        return orders
