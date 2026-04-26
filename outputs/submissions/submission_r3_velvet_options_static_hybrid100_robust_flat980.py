from datamodel import Order, TradingState


ROBUST_START = 100000
FLATTEN_START = 980000

EARLY_CONFIGS = {
    "VELVETFRUIT_EXTRACT": {"limit": 200, "max_order": 80, "buy": 5245, "sell": 5269},
    "VEV_5000": {"limit": 300, "max_order": 40, "buy": 255, "sell": 270},
    "VEV_5100": {"limit": 300, "max_order": 40, "buy": 165, "sell": 179},
    "VEV_5200": {"limit": 300, "max_order": 40, "buy": 93, "sell": 105},
    "VEV_5300": {"limit": 300, "max_order": 20, "buy": 45, "sell": 52},
    "VEV_5400": {"limit": 300, "max_order": 40, "buy": 13, "sell": 17},
    "VEV_5500": {"limit": 300, "max_order": 40, "buy": 5, "sell": 7},
}

ROBUST_CONFIGS = {
    "VELVETFRUIT_EXTRACT": {"limit": 200, "max_order": 80, "buy": 5246, "sell": 5272},
    "VEV_5000": {"limit": 300, "max_order": 20, "buy": 241, "sell": 273},
    "VEV_5100": {"limit": 300, "max_order": 40, "buy": 154, "sell": 183},
    "VEV_5200": {"limit": 300, "max_order": 40, "buy": 92, "sell": 106},
    "VEV_5300": {"limit": 300, "max_order": 40, "buy": 44, "sell": 52},
    "VEV_5400": {"limit": 300, "max_order": 40, "buy": 15, "sell": 17},
    "VEV_5500": {"limit": 300, "max_order": 20, "buy": 4, "sell": 11},
}


class Trader:
    """Early probe thresholds, then robust-core thresholds with late flattening."""

    def run(self, state: TradingState):
        configs = EARLY_CONFIGS if state.timestamp < ROBUST_START else ROBUST_CONFIGS
        all_orders = {}
        for product, cfg in configs.items():
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
