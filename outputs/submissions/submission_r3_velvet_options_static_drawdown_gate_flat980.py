import json

from datamodel import Order, TradingState


FLATTEN_START = 980000

BASE_CONFIGS = {
    "VELVETFRUIT_EXTRACT": {"limit": 200, "max_order": 40, "buy": 5246, "sell": 5272},
    "VEV_4000": {"limit": 300, "max_order": 10, "buy": 1233, "sell": 1263},
    "VEV_4500": {"limit": 300, "max_order": 20, "buy": 732, "sell": 766},
    "VEV_5000": {"limit": 300, "max_order": 20, "buy": 241, "sell": 273},
    "VEV_5100": {"limit": 300, "max_order": 40, "buy": 164, "sell": 183},
    "VEV_5200": {"limit": 300, "max_order": 40, "buy": 93, "sell": 105},
    "VEV_5300": {"limit": 300, "max_order": 40, "buy": 45, "sell": 52},
    "VEV_5400": {"limit": 300, "max_order": 40, "buy": 15, "sell": 18},
    "VEV_5500": {"limit": 300, "max_order": 40, "buy": 7, "sell": 8},
}

GATES = {
    "VEV_5000": {
        "drawdown": 3000,
        "config": {"limit": 300, "max_order": 40, "buy": 255, "sell": 270},
    },
    "VEV_5100": {
        "drawdown": 1500,
        "config": {"limit": 300, "max_order": 40, "buy": 165, "sell": 179},
    },
    "VEV_5200": {
        "drawdown": 0,
        "config": {"limit": 300, "max_order": 40, "buy": 92, "sell": 106},
    },
    "VEV_5300": {
        "drawdown": 500,
        "config": {"limit": 300, "max_order": 40, "buy": 44, "sell": 52},
    },
    "VEV_5400": {
        "drawdown": 500,
        "config": {"limit": 300, "max_order": 40, "buy": 15, "sell": 17},
    },
    "VEV_5500": {
        "drawdown": 500,
        "config": {"limit": 300, "max_order": 40, "buy": 5, "sell": 7},
    },
}


class Trader:
    """Aggressive-all with product-level marked-PnL drawdown gates."""

    def run(self, state: TradingState):
        blob = _load_blob(state.traderData)
        cash = blob.get("cash", {})
        peak = blob.get("peak", {})
        last_trade_ts = int(blob.get("last_trade_ts", -1))
        new_last_trade_ts = last_trade_ts

        for product, trades in state.own_trades.items():
            for trade in trades:
                trade_ts = int(getattr(trade, "timestamp", -1))
                if trade_ts <= last_trade_ts:
                    continue
                qty = int(getattr(trade, "quantity", 0))
                price = float(getattr(trade, "price", 0))
                buyer = getattr(trade, "buyer", "")
                seller = getattr(trade, "seller", "")
                if buyer == "SUBMISSION":
                    cash[product] = float(cash.get(product, 0.0)) - price * qty
                elif seller == "SUBMISSION":
                    cash[product] = float(cash.get(product, 0.0)) + price * qty
                if trade_ts > new_last_trade_ts:
                    new_last_trade_ts = trade_ts
        last_trade_ts = new_last_trade_ts

        all_orders = {}
        for product, base_cfg in BASE_CONFIGS.items():
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            if not depth.buy_orders or not depth.sell_orders:
                continue
            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            mid = (best_bid + best_ask) / 2.0
            position = state.position.get(product, 0)
            pnl = float(cash.get(product, 0.0)) + position * mid
            previous_peak = float(peak.get(product, pnl))
            if pnl > previous_peak:
                previous_peak = pnl
            peak[product] = previous_peak
            drawdown = previous_peak - pnl

            cfg = base_cfg
            gate = GATES.get(product)
            if gate is not None and drawdown >= gate["drawdown"]:
                cfg = gate["config"]

            orders = []
            if state.timestamp >= FLATTEN_START:
                if position > 0:
                    bid_volume = depth.buy_orders[best_bid]
                    qty = min(cfg["max_order"], bid_volume, position)
                    if qty > 0:
                        orders.append(Order(product, best_bid, -qty))
                elif position < 0:
                    ask_volume = -depth.sell_orders[best_ask]
                    qty = min(cfg["max_order"], ask_volume, -position)
                    if qty > 0:
                        orders.append(Order(product, best_ask, qty))
                if orders:
                    all_orders[product] = orders
                continue

            ask_volume = -depth.sell_orders[best_ask]
            if best_ask <= cfg["buy"] and position < cfg["limit"]:
                qty = min(cfg["max_order"], ask_volume, cfg["limit"] - position)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
                    position += qty

            bid_volume = depth.buy_orders[best_bid]
            if best_bid >= cfg["sell"] and position > -cfg["limit"]:
                qty = min(cfg["max_order"], bid_volume, cfg["limit"] + position)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

            if orders:
                all_orders[product] = orders

        next_blob = {
            "cash": cash,
            "peak": peak,
            "last_trade_ts": last_trade_ts,
        }
        trader_data = json.dumps(next_blob, separators=(",", ":"))
        return all_orders, 0, trader_data


def _load_blob(raw):
    if not raw:
        return {}
    try:
        blob = json.loads(raw)
    except Exception:
        return {}
    return blob if isinstance(blob, dict) else {}
