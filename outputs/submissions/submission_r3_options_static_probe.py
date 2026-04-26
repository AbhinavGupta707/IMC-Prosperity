from datamodel import Order, TradingState


CONFIGS = {
    "VEV_5000": {"limit": 300, "max_order": 40, "buy": 255, "sell": 270},
    "VEV_5100": {"limit": 300, "max_order": 40, "buy": 165, "sell": 179},
    "VEV_5200": {"limit": 300, "max_order": 40, "buy": 93, "sell": 105},
    "VEV_5300": {"limit": 300, "max_order": 20, "buy": 45, "sell": 52},
    "VEV_5400": {"limit": 300, "max_order": 40, "buy": 13, "sell": 17},
    "VEV_5500": {"limit": 300, "max_order": 40, "buy": 5, "sell": 7},
}


class Trader:
    """Options-only static-threshold probe.

    This is deliberately aggressive and should be read as a simulator
    diagnostic for the core voucher surface, not a final production sleeve.
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
