from datamodel import Order, TradingState


CONFIGS = {
    "VELVETFRUIT_EXTRACT": {"limit": 200, "max_order": 80, "buy": 5246, "sell": 5272},
    "VEV_4000": {"limit": 300, "max_order": 20, "buy": 1233, "sell": 1263},
    "VEV_4500": {"limit": 300, "max_order": 20, "buy": 732, "sell": 766},
    "VEV_5000": {"limit": 300, "max_order": 20, "buy": 241, "sell": 273},
    "VEV_5100": {"limit": 300, "max_order": 40, "buy": 154, "sell": 183},
    "VEV_5200": {"limit": 300, "max_order": 40, "buy": 92, "sell": 106},
    "VEV_5300": {"limit": 300, "max_order": 40, "buy": 44, "sell": 52},
    "VEV_5400": {"limit": 300, "max_order": 40, "buy": 15, "sell": 17},
    "VEV_5500": {"limit": 300, "max_order": 20, "buy": 4, "sell": 11},
}


class Trader:
    """Higher-risk VELVET/options all-strike static threshold diagnostic.

    This includes VEV_4000/4500 because public full-day replay likes them.
    Treat it as a simulator calibration probe before any final merge.
    """

    def run(self, state: TradingState):
        all_orders = {}
        for product, cfg in CONFIGS.items():
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

            if orders:
                all_orders[product] = orders

        return all_orders, 0, state.traderData
