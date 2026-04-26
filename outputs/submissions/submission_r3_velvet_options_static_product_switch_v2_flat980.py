from datamodel import Order, TradingState


FLATTEN_START = 980000

SCHEDULES = {
    "VELVETFRUIT_EXTRACT": [
        (0, {"limit": 200, "max_order": 40, "buy": 5246, "sell": 5272}),
    ],
    "VEV_4000": [
        (0, {"limit": 300, "max_order": 10, "buy": 1233, "sell": 1263}),
    ],
    "VEV_4500": [
        (0, {"limit": 300, "max_order": 20, "buy": 732, "sell": 766}),
    ],
    "VEV_5000": [
        (0, {"limit": 300, "max_order": 40, "buy": 255, "sell": 270}),
        (100000, {"limit": 300, "max_order": 20, "buy": 241, "sell": 273}),
    ],
    "VEV_5100": [
        (0, {"limit": 300, "max_order": 40, "buy": 165, "sell": 179}),
        (150000, {"limit": 300, "max_order": 40, "buy": 164, "sell": 183}),
    ],
    "VEV_5200": [
        (0, {"limit": 300, "max_order": 40, "buy": 92, "sell": 106}),
        (300000, {"limit": 300, "max_order": 40, "buy": 93, "sell": 105}),
    ],
    "VEV_5300": [
        (0, {"limit": 300, "max_order": 20, "buy": 45, "sell": 52}),
        (50000, {"limit": 300, "max_order": 40, "buy": 45, "sell": 52}),
    ],
    "VEV_5400": [
        (0, {"limit": 300, "max_order": 40, "buy": 13, "sell": 17}),
        (100000, {"limit": 300, "max_order": 40, "buy": 15, "sell": 18}),
    ],
    "VEV_5500": [
        (0, {"limit": 300, "max_order": 40, "buy": 7, "sell": 8}),
    ],
}


class Trader:
    """Balanced product-switch profile for the 1M VELVET/options sleeve."""

    def run(self, state: TradingState):
        all_orders = {}
        for product, schedule in SCHEDULES.items():
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            cfg = _config_for_timestamp(schedule, state.timestamp)
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


def _config_for_timestamp(schedule, timestamp):
    cfg = schedule[0][1]
    for start, candidate in schedule:
        if timestamp >= start:
            cfg = candidate
        else:
            break
    return cfg
