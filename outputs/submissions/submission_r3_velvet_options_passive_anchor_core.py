from datamodel import Order, TradingState


ANCHORS = {
    "VELVETFRUIT_EXTRACT": 5257.0,
    "VEV_5000": 262.5,
    "VEV_5100": 172.0,
    "VEV_5200": 99.0,
    "VEV_5300": 48.5,
    "VEV_5400": 15.0,
    "VEV_5500": 6.0,
}

LIMITS = {
    "VELVETFRUIT_EXTRACT": 200,
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
}

SIZES = {
    "VELVETFRUIT_EXTRACT": 25,
    "VEV_5000": 12,
    "VEV_5100": 16,
    "VEV_5200": 20,
    "VEV_5300": 20,
    "VEV_5400": 22,
    "VEV_5500": 22,
}

EDGE = 1.0
SOFT_LIMIT = 160


class Trader:
    """Passive-only VELVET/core-voucher anchor maker diagnostic."""

    def run(self, state: TradingState):
        all_orders = {}
        for product, fair in ANCHORS.items():
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                continue

            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            if best_ask <= best_bid + 2:
                continue

            position = state.position.get(product, 0)
            limit = LIMITS[product]
            size = SIZES[product]
            orders = []

            bid_price = best_bid + 1
            ask_price = best_ask - 1

            if bid_price < ask_price and fair - bid_price >= EDGE and position < SOFT_LIMIT:
                qty = min(size, limit - position)
                if qty > 0:
                    orders.append(Order(product, bid_price, qty))

            if ask_price > bid_price and ask_price - fair >= EDGE and position > -SOFT_LIMIT:
                qty = min(size, limit + position)
                if qty > 0:
                    orders.append(Order(product, ask_price, -qty))

            if orders:
                all_orders[product] = orders

        return all_orders, 0, state.traderData
