from datamodel import Order, TradingState


FLATTEN_START = 980000

CONFIGS = {
    "VEV_4000": {"limit": 300, "max_order": 20, "buy": 1233, "sell": 1263},
    "VEV_4500": {"limit": 300, "max_order": 20, "buy": 732, "sell": 766},
}


class Trader:
    """Isolated VEV_4000/4500 diagnostic."""

    def run(self, state: TradingState):
        all_orders = {}
        for product, cfg in CONFIGS.items():
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            position = state.position.get(product, 0)
            orders = []

            if state.timestamp >= FLATTEN_START:
                if position > 0 and depth.buy_orders:
                    best_bid = max(depth.buy_orders)
                    bid_volume = depth.buy_orders[best_bid]
                    qty = min(cfg["max_order"], bid_volume, position)
                    if qty > 0:
                        orders.append(Order(product, best_bid, -qty))
                elif position < 0 and depth.sell_orders:
                    best_ask = min(depth.sell_orders)
                    ask_volume = -depth.sell_orders[best_ask]
                    qty = min(cfg["max_order"], ask_volume, -position)
                    if qty > 0:
                        orders.append(Order(product, best_ask, qty))
                if orders:
                    all_orders[product] = orders
                continue

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

            if orders:
                all_orders[product] = orders

        return all_orders, 0, state.traderData
