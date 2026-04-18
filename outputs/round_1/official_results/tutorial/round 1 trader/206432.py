"""Hold-one diagnostic trader for tutorial-round FV recovery.

Strategy:
    On every Trader.run call, for each product currently visible in
    ``state.order_depths``, if our position in that product is zero,
    submit a single buy-1 order at the current best ask. Once the buy
    fills and position becomes 1, the trader stops issuing orders for
    that product and holds the unit position for the remainder of the
    session.

Why:
    IMC Prosperity marks every position to PnL every tick using the
    server-side continuous fair value. For a unit long position with
    known entry price, the mark-to-market PnL at any time t is:

        PnL(t)  =  1 * (server_fv(t) - buy_price)

    Inverting gives us the server's internal fair value stream at full
    resolution (far finer than the 1-tick mid grid). That hidden-state
    stream is the foundation for all downstream bot calibration.

Design notes:
    - Product-name agnostic: buys 1 of whatever appears in the book.
      Tutorial-round products are EMERALDS and TOMATOES; this trader
      does not hard-code those names so it can be reused for diagnostic
      probes on any future round.
    - Defensive: if no ask side exists at t=0, retries every tick until
      filled. Once filled, becomes a silent no-op.
    - Returns empty trader_data string; this trader is fully memoryless.
    - Does not breach position limits (requested qty = 1 per product).

Submission:
    Upload this file directly to the IMC tutorial environment. Let it
    run for the full 10k-step tutorial day, then download the activity
    log JSON from the submission history page. The per-tick PnL stream
    embedded in the log recovers server fair value for every product
    this trader held a unit position in.
"""
from __future__ import annotations

from datamodel import Order, OrderDepth, TradingState


class Trader:
    """Buy exactly one unit of every visible product, then hold forever."""

    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:
        orders: dict[str, list[Order]] = {}
        for symbol, order_depth in state.order_depths.items():
            position = state.position.get(symbol, 0)
            if position != 0:
                # Already holding (or somehow short); do nothing.
                continue
            if not order_depth.sell_orders:
                # No ask liquidity this tick; retry next call.
                continue
            best_ask = min(order_depth.sell_orders.keys())
            orders[symbol] = [Order(symbol, best_ask, 1)]
        return orders, 0, ""