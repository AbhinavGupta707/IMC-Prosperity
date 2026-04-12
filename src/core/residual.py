"""Optional residual capacity utilizer (framework-only, ships disabled).

After the main strategy emits orders, there is often unused position
budget on one or both sides.  This module inspects the leftover capacity
and optionally appends small passive maker orders to capture spread from
the residual room.

Hard rules enforced here:

1. **Maker-only** -- residual orders never cross the spread.
2. **No duplicate prices** -- if the main strategy already placed an
   order on the same side at the exact price the residual would use,
   the residual order on that side is suppressed.
3. **Post-processing only, zero coupling** -- the module receives the
   main strategy's raw order list as read-only input and appends to it.
   It never modifies existing orders, never reads or writes strategy /
   signal / fair-value state.
4. **Default disabled** -- ``ResidualConfig.enabled`` is ``False``.
   The enablement gate (PnL, trade count, maker/taker mix, markouts,
   time-near-limits comparison) must pass before the flag is flipped.

Design:
- Runs after ``ExecutionEngine.generate_orders()`` and before
  ``RiskManager.clip_orders()``.
- The risk manager still clips the combined list, so this module
  cannot breach position limits.
"""

from __future__ import annotations

import math

from src.core.types import ExecutionMode, NormalizedSnapshot, ResidualConfig
from src.datamodel import Order


class ResidualAllocator:
    """Append small passive orders into unused position capacity."""

    def __init__(self, config: ResidualConfig) -> None:
        self._config = config

    def augment_orders(
        self,
        *,
        product: str,
        orders: list[Order],
        snapshot: NormalizedSnapshot,
        fair_value: float,
        position: int,
        limit: int,
        mode: ExecutionMode = "maker",
    ) -> list[Order]:
        """Return *orders* with optional residual orders appended.

        If the module is disabled or the strategy is in recovery mode,
        returns the input list unchanged.
        """
        if not self._config.enabled:
            return orders

        # Never add residual orders during recovery (flattening).
        if mode == "recovery":
            return orders

        buy_capacity = max(0, limit - position)
        sell_capacity = max(0, limit + position)

        # Subtract capacity already consumed by main orders.
        # Also collect main-strategy prices per side for duplicate guard.
        main_bid_prices: set[int] = set()
        main_ask_prices: set[int] = set()

        for order in orders:
            if order.quantity > 0:
                buy_capacity -= order.quantity
                main_bid_prices.add(order.price)
            elif order.quantity < 0:
                sell_capacity -= abs(order.quantity)
                main_ask_prices.add(order.price)

        buy_capacity = max(0, buy_capacity)
        sell_capacity = max(0, sell_capacity)

        residual_orders: list[Order] = []

        if buy_capacity > 0:
            bid_price = math.floor(fair_value - self._config.residual_edge)
            bid_size = min(self._config.residual_size, buy_capacity)

            # Spread guard: suppress if bid would cross or touch best ask.
            best_ask = snapshot.best_ask
            crosses_spread = best_ask is not None and bid_price >= best_ask.price

            # Duplicate-price guard.
            duplicates_main = bid_price in main_bid_prices

            if bid_size > 0 and not crosses_spread and not duplicates_main:
                residual_orders.append(Order(product, bid_price, bid_size))

        if sell_capacity > 0:
            ask_price = math.ceil(fair_value + self._config.residual_edge)
            ask_size = min(self._config.residual_size, sell_capacity)

            # Spread guard: suppress if ask would cross or touch best bid.
            best_bid = snapshot.best_bid
            crosses_spread = best_bid is not None and ask_price <= best_bid.price

            # Duplicate-price guard.
            duplicates_main = ask_price in main_ask_prices

            if ask_size > 0 and not crosses_spread and not duplicates_main:
                residual_orders.append(Order(product, ask_price, -ask_size))

        if not residual_orders:
            return orders

        return [*orders, *residual_orders]
