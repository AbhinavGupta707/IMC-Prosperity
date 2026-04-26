from datamodel import Order, TradingState


class Trader:
    """VELVET-only aggressive path probe.

    This intentionally targets the strong short-VELVET opportunity observed in
    the uploaded 100k-tick result slice. Use it to test whether that edge
    repeats in the simulator; do not treat it as robust without official
    confirmation.
    """

    PRODUCT = "VELVETFRUIT_EXTRACT"
    LIMIT = 200
    MAX_ORDER = 80
    BUY_TRIGGER = 5245
    SELL_TRIGGER = 5269

    def run(self, state: TradingState):
        orders = []
        depth = state.order_depths.get(self.PRODUCT)
        position = state.position.get(self.PRODUCT, 0)
        if depth is not None:
            if depth.sell_orders:
                best_ask = min(depth.sell_orders)
                ask_volume = -depth.sell_orders[best_ask]
                if best_ask <= self.BUY_TRIGGER and position < self.LIMIT:
                    qty = min(self.MAX_ORDER, ask_volume, self.LIMIT - position)
                    if qty > 0:
                        orders.append(Order(self.PRODUCT, best_ask, qty))
                        position += qty

            if depth.buy_orders:
                best_bid = max(depth.buy_orders)
                bid_volume = depth.buy_orders[best_bid]
                if best_bid >= self.SELL_TRIGGER and position > -self.LIMIT:
                    qty = min(self.MAX_ORDER, bid_volume, self.LIMIT + position)
                    if qty > 0:
                        orders.append(Order(self.PRODUCT, best_bid, -qty))

        return ({self.PRODUCT: orders} if orders else {}, 0, state.traderData)
