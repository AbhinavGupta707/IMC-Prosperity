"""Export stack-based Mark55 passive interposition probes.

These probes test the actual Round 4 Mark mechanism we have not fully exhausted:
posting one-tick-improved passive VELVET quotes in front of predictable Mark55
taker flow, then recycling fills quickly so the overlay does not become a
terminal inventory bet.

The generated submissions are upload-calibration experiments. Local replay is
not authoritative for one-tick-inside fill priority.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"
BASE = SUB_DIR / "submission_r4_final_stack_hydabort18l80_nomark_control.py"


@dataclass(frozen=True)
class Spec:
    label: str
    gate: str
    side_mode: str = "both"
    size: int = 1
    recycle_age: int = 5_000

    @property
    def out(self) -> Path:
        return SUB_DIR / f"submission_r4_final_stack_hydabort18l80_{self.label}.py"


def specs() -> list[Spec]:
    return [
        Spec("m55_interpose_markgate_s1", "markgate", "both", 1),
        Spec("m55_interpose_periodic_s1", "periodic", "both", 1),
        Spec("m55_interpose_always_s1", "always", "both", 1),
        Spec("m55_interpose_bidonly_markgate_s1", "markgate", "bid", 1),
        Spec("m55_interpose_askonly_markgate_s1", "markgate", "ask", 1),
    ]


def _rename_final_trader(source: str, new_name: str) -> str:
    marker = "\nclass Trader:"
    index = source.rfind(marker)
    if index < 0:
        raise ValueError("bundle does not contain a final top-level class Trader")
    return source[:index] + f"\nclass {new_name}:" + source[index + len(marker) :]


APPENDIX_TEMPLATE = r'''

# ====================================================================
# R4 MARK55 STACK INTERPOSITION PROBE.
#
# Upload-calibration experiment:
#   * post one-tick-improved passive VELVET bid/ask in front of predictable
#     Mark55 taker flow;
#   * use tiny size and recycle lots quickly so this tests execution, not a
#     new terminal VELVET thesis;
#   * compare markgate against periodic/always controls.
# ====================================================================
_M55I_BASE_TRADER = Trader
_M55I_PRODUCT = 'VELVETFRUIT_EXTRACT'
_M55I_GATE = '__GATE__'
_M55I_SIDE_MODE = '__SIDE_MODE__'
_M55I_SIZE = __SIZE__
_M55I_RECYCLE_AGE = __RECYCLE_AGE__
_M55I_MIN_AGE = 100
_M55I_PROFIT_TICKS = 1
_M55I_M67_WINDOW = 30_000
_M55I_M55_WINDOW = 5_000
_M55I_M22_WINDOW = 30_000
_M55I_M67_COUNT_THRESHOLD = 3
_M55I_M22_QTY_THRESHOLD = 7
_M55I_LONG_MAX = 200
_M55I_SHORT_MAX = -200
_M55I_TARGET_COUNTERPARTIES = ('Mark 55', 'Mark 67')

class _M55IRolling:
    def __init__(self, window):
        self.window = int(window)
        self.events = []
        self.total_qty = 0

    def clear(self):
        self.events = []
        self.total_qty = 0

    def prune(self, timestamp):
        cutoff = int(timestamp) - self.window
        kept = []
        total = 0
        for ts, qty in self.events:
            if ts >= cutoff:
                kept.append((ts, qty))
                total += qty
        self.events = kept
        self.total_qty = total

    def add(self, timestamp, qty):
        qty = int(qty)
        if qty <= 0:
            return
        self.events.append((int(timestamp), qty))
        self.total_qty += qty
        self.prune(timestamp)

    @property
    def count(self):
        return len(self.events)

    @property
    def qty(self):
        return int(self.total_qty)

class _M55ILot:
    def __init__(self, side, timestamp, price, qty, counterparty):
        self.side = side
        self.timestamp = int(timestamp)
        self.price = int(price)
        self.qty = int(qty)
        self.counterparty = counterparty

class Trader:
    def __init__(self):
        self._inner = _M55I_BASE_TRADER()
        self._m67_buy = _M55IRolling(_M55I_M67_WINDOW)
        self._m55_sell = _M55IRolling(_M55I_M55_WINDOW)
        self._m55_buy = _M55IRolling(_M55I_M55_WINDOW)
        self._m22_sell = _M55IRolling(_M55I_M22_WINDOW)
        self._any_velvet = _M55IRolling(_M55I_M55_WINDOW)
        self._seen_market = set()
        self._seen_own = set()
        self._lots = []
        self._last_timestamp = None

    def _reset_if_needed(self, timestamp):
        if self._last_timestamp is not None and int(timestamp) < self._last_timestamp:
            self._m67_buy.clear()
            self._m55_sell.clear()
            self._m55_buy.clear()
            self._m22_sell.clear()
            self._any_velvet.clear()
            self._seen_market = set()
            self._seen_own = set()
            self._lots = []
        self._last_timestamp = int(timestamp)

    def _ingest_market(self, state):
        ts = int(state.timestamp)
        self._reset_if_needed(ts)
        self._m67_buy.prune(ts)
        self._m55_sell.prune(ts)
        self._m55_buy.prune(ts)
        self._m22_sell.prune(ts)
        self._any_velvet.prune(ts)
        for trade in (state.market_trades or {}).get(_M55I_PRODUCT, []) or []:
            qty = int(getattr(trade, 'quantity', 0) or 0)
            if qty <= 0:
                continue
            trade_ts = int(getattr(trade, 'timestamp', ts) or ts)
            price = int(getattr(trade, 'price', 0) or 0)
            buyer = getattr(trade, 'buyer', None)
            seller = getattr(trade, 'seller', None)
            key = (trade_ts, price, qty, buyer, seller)
            if key in self._seen_market:
                continue
            self._seen_market.add(key)
            self._any_velvet.add(trade_ts, qty)
            if buyer == 'Mark 67':
                self._m67_buy.add(trade_ts, qty)
            if buyer == 'Mark 55':
                self._m55_buy.add(trade_ts, qty)
            if seller == 'Mark 55':
                self._m55_sell.add(trade_ts, qty)
            if seller == 'Mark 22':
                self._m22_sell.add(trade_ts, qty)

    def _ingest_own(self, state):
        ts = int(state.timestamp)
        for trade in (state.own_trades or {}).get(_M55I_PRODUCT, []) or []:
            qty = int(getattr(trade, 'quantity', 0) or 0)
            if qty <= 0:
                continue
            price = int(getattr(trade, 'price', 0) or 0)
            trade_ts = int(getattr(trade, 'timestamp', ts) or ts)
            buyer = getattr(trade, 'buyer', None)
            seller = getattr(trade, 'seller', None)
            key = (trade_ts, price, qty, buyer, seller)
            if key in self._seen_own:
                continue
            self._seen_own.add(key)
            if buyer == 'SUBMISSION' and seller in _M55I_TARGET_COUNTERPARTIES:
                self._lots.append(_M55ILot('long', trade_ts, price, qty, seller))
            elif seller == 'SUBMISSION' and buyer in _M55I_TARGET_COUNTERPARTIES:
                self._lots.append(_M55ILot('short', trade_ts, price, qty, buyer))

    def _bid_gate(self, timestamp):
        if _M55I_GATE == 'always':
            return True
        if _M55I_GATE == 'periodic':
            return int(timestamp) % 10_000 < 1_100
        if _M55I_GATE == 'anyflow':
            return self._any_velvet.count >= 1
        return (
            self._m67_buy.count >= _M55I_M67_COUNT_THRESHOLD
            or self._m55_sell.count >= 1
            or self._m22_sell.qty >= _M55I_M22_QTY_THRESHOLD
        )

    def _ask_gate(self, timestamp):
        if _M55I_GATE == 'always':
            return True
        if _M55I_GATE == 'periodic':
            return int(timestamp) % 10_000 < 1_100
        if _M55I_GATE == 'anyflow':
            return self._any_velvet.count >= 1
        return self._m55_buy.count >= 1

    def _split_shift(self, existing, want_buy, passive_price, size):
        remaining = int(size)
        shifted = 0
        rewritten = []
        for order in existing:
            qty = int(order.quantity)
            same_side = qty > 0 if want_buy else qty < 0
            if not same_side or remaining <= 0:
                rewritten.append(order)
                continue
            take = min(abs(qty), remaining)
            left = abs(qty) - take
            if left > 0:
                rewritten.append(Order(_M55I_PRODUCT, int(order.price), left if want_buy else -left))
            shifted += take
            remaining -= take
        if shifted > 0:
            rewritten.append(Order(_M55I_PRODUCT, int(passive_price), shifted if want_buy else -shifted))
        return rewritten, shifted

    def _append_interpose_orders(self, orders, state):
        depth = state.order_depths.get(_M55I_PRODUCT)
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return orders
        bid = int(max(depth.buy_orders))
        ask = int(min(depth.sell_orders))
        if ask - bid <= 1:
            return orders
        pos = int(state.position.get(_M55I_PRODUCT, 0))
        existing = list((orders or {}).get(_M55I_PRODUCT, []) or [])
        new_orders = dict(orders or {})

        if _M55I_SIDE_MODE in ('both', 'bid') and self._bid_gate(state.timestamp) and pos < _M55I_LONG_MAX:
            buy_price = bid + 1
            buy_size = min(_M55I_SIZE, _M55I_LONG_MAX - pos)
            if buy_size > 0 and buy_price < ask:
                rewritten, shifted = self._split_shift(existing, True, buy_price, buy_size)
                if shifted > 0:
                    existing = rewritten
                    new_orders[_M55I_PRODUCT] = existing
                elif not any(int(order.quantity) > 0 for order in existing):
                    existing = existing + [Order(_M55I_PRODUCT, buy_price, buy_size)]
                    new_orders[_M55I_PRODUCT] = existing

        if _M55I_SIDE_MODE in ('both', 'ask') and self._ask_gate(state.timestamp) and pos > _M55I_SHORT_MAX:
            sell_price = ask - 1
            sell_size = min(_M55I_SIZE, pos - _M55I_SHORT_MAX)
            if sell_size > 0 and sell_price > bid:
                rewritten, shifted = self._split_shift(existing, False, sell_price, sell_size)
                if shifted > 0:
                    existing = rewritten
                    new_orders[_M55I_PRODUCT] = existing
                elif not any(int(order.quantity) < 0 for order in existing):
                    existing = existing + [Order(_M55I_PRODUCT, sell_price, -sell_size)]
                    new_orders[_M55I_PRODUCT] = existing
        return new_orders

    def _append_recycle_orders(self, orders, state):
        if not self._lots:
            return orders
        depth = state.order_depths.get(_M55I_PRODUCT)
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return orders
        bid = int(max(depth.buy_orders))
        ask = int(min(depth.sell_orders))
        pos = int(state.position.get(_M55I_PRODUCT, 0))
        existing = list((orders or {}).get(_M55I_PRODUCT, []) or [])
        has_buy = any(int(order.quantity) > 0 for order in existing)
        has_sell = any(int(order.quantity) < 0 for order in existing)
        ts = int(state.timestamp)
        buy_back = 0
        sell_back = 0
        kept = []
        for lot in self._lots:
            age = ts - lot.timestamp
            if age < _M55I_MIN_AGE:
                kept.append(lot)
                continue
            if lot.side == 'long':
                should_sell = bid >= lot.price + _M55I_PROFIT_TICKS
                stale_flat = age > _M55I_RECYCLE_AGE and bid >= lot.price
                capacity = max(0, pos - _M55I_SHORT_MAX - sell_back)
                if (should_sell or stale_flat) and not has_sell and capacity > 0:
                    qty = min(lot.qty, capacity, _M55I_SIZE)
                    sell_back += qty
                    lot.qty -= qty
                    if lot.qty > 0:
                        kept.append(lot)
                else:
                    kept.append(lot)
            else:
                should_buy = ask <= lot.price - _M55I_PROFIT_TICKS
                stale_flat = age > _M55I_RECYCLE_AGE and ask <= lot.price
                capacity = max(0, _M55I_LONG_MAX - pos - buy_back)
                if (should_buy or stale_flat) and not has_buy and capacity > 0:
                    qty = min(lot.qty, capacity, _M55I_SIZE)
                    buy_back += qty
                    lot.qty -= qty
                    if lot.qty > 0:
                        kept.append(lot)
                else:
                    kept.append(lot)
        self._lots = kept
        if buy_back <= 0 and sell_back <= 0:
            return orders
        new_orders = dict(orders or {})
        existing = list(new_orders.get(_M55I_PRODUCT, []) or [])
        if buy_back > 0:
            existing.append(Order(_M55I_PRODUCT, ask, int(buy_back)))
        if sell_back > 0:
            existing.append(Order(_M55I_PRODUCT, bid, -int(sell_back)))
        new_orders[_M55I_PRODUCT] = existing
        return new_orders

    def run(self, state):
        self._ingest_market(state)
        self._ingest_own(state)
        orders, conversions, trader_data = self._inner.run(state)
        orders = self._append_recycle_orders(orders, state)
        orders = self._append_interpose_orders(orders, state)
        return orders, conversions, trader_data
'''


def build_source(spec: Spec) -> str:
    source = BASE.read_text()
    source = _rename_final_trader(source.rstrip(), "_R4M55InterposeBaseTrader")
    appendix = (
        APPENDIX_TEMPLATE.replace("_M55I_BASE_TRADER = Trader", "_M55I_BASE_TRADER = _R4M55InterposeBaseTrader", 1)
        .replace("__GATE__", spec.gate)
        .replace("__SIDE_MODE__", spec.side_mode)
        .replace("__SIZE__", str(spec.size))
        .replace("__RECYCLE_AGE__", str(spec.recycle_age))
    )
    return source + appendix + "\n"


def export_one(spec: Spec) -> Path:
    path = spec.out
    path.write_text(build_source(spec))
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted({spec.label for spec in specs()}), nargs="*")
    args = parser.parse_args()
    selected = [spec for spec in specs() if not args.only or spec.label in args.only]
    for spec in selected:
        print(f"Wrote {export_one(spec)}")


if __name__ == "__main__":
    main()
