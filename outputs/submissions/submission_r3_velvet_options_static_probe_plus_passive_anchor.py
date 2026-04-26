from datamodel import Order, TradingState


STATIC_CONFIGS = {
    "VELVETFRUIT_EXTRACT": {"limit": 200, "max_order": 80, "buy": 5245, "sell": 5269},
    "VEV_5000": {"limit": 300, "max_order": 40, "buy": 255, "sell": 270},
    "VEV_5100": {"limit": 300, "max_order": 40, "buy": 165, "sell": 179},
    "VEV_5200": {"limit": 300, "max_order": 40, "buy": 93, "sell": 105},
    "VEV_5300": {"limit": 300, "max_order": 20, "buy": 45, "sell": 52},
    "VEV_5400": {"limit": 300, "max_order": 40, "buy": 13, "sell": 17},
    "VEV_5500": {"limit": 300, "max_order": 40, "buy": 5, "sell": 7},
}

PASSIVE_ANCHORS = {
    "VELVETFRUIT_EXTRACT": 5257.0,
    "VEV_4000": 1250.0,
    "VEV_4500": 750.0,
    "VEV_5000": 262.5,
    "VEV_5100": 172.0,
    "VEV_5200": 99.0,
    "VEV_5300": 48.5,
    "VEV_5400": 15.0,
    "VEV_5500": 6.0,
}

PASSIVE_SIZES = {
    "VELVETFRUIT_EXTRACT": 15,
    "VEV_4000": 6,
    "VEV_4500": 6,
    "VEV_5000": 8,
    "VEV_5100": 10,
    "VEV_5200": 12,
    "VEV_5300": 12,
    "VEV_5400": 14,
    "VEV_5500": 14,
}

LIMITS = {"VELVETFRUIT_EXTRACT": 200}
for _product in PASSIVE_ANCHORS:
    if _product != "VELVETFRUIT_EXTRACT":
        LIMITS[_product] = 300

PASSIVE_EDGE = 1.0
PASSIVE_SOFT_LIMIT = 180


class Trader:
    """High-PnL static probe plus passive maker diagnostic."""

    def run(self, state: TradingState):
        all_orders = {}
        touched = set()

        for product, cfg in STATIC_CONFIGS.items():
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            position = state.position.get(product, 0)
            orders = []

            if depth.sell_orders:
                best_ask = min(depth.sell_orders)
                ask_volume = -depth.sell_orders[best_ask]
                if best_ask <= cfg["buy"] and position < cfg["limit"]:
                    qty = min(cfg["max_order"], ask_volume, cfg["limit"] - position)
                    if qty > 0:
                        orders.append(Order(product, best_ask, qty))
                        position += qty

            if depth.buy_orders:
                best_bid = max(depth.buy_orders)
                bid_volume = depth.buy_orders[best_bid]
                if best_bid >= cfg["sell"] and position > -cfg["limit"]:
                    qty = min(cfg["max_order"], bid_volume, cfg["limit"] + position)
                    if qty > 0:
                        orders.append(Order(product, best_bid, -qty))
                        position -= qty

            if orders:
                all_orders[product] = orders
                touched.add(product)

        for product, fair in PASSIVE_ANCHORS.items():
            if product in touched:
                continue
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                continue
            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            if best_ask <= best_bid + 2:
                continue

            position = state.position.get(product, 0)
            limit = LIMITS[product]
            size = PASSIVE_SIZES[product]
            bid_price = best_bid + 1
            ask_price = best_ask - 1
            orders = []

            if bid_price < ask_price and fair - bid_price >= PASSIVE_EDGE and position < PASSIVE_SOFT_LIMIT:
                qty = min(size, limit - position)
                if qty > 0:
                    orders.append(Order(product, bid_price, qty))

            if ask_price > bid_price and ask_price - fair >= PASSIVE_EDGE and position > -PASSIVE_SOFT_LIMIT:
                qty = min(size, limit + position)
                if qty > 0:
                    orders.append(Order(product, ask_price, -qty))

            if orders:
                all_orders[product] = orders

        return all_orders, 0, state.traderData
