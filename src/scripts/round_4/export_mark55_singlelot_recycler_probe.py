"""Export a single-lot Mark55 q5 recycler diagnostic submission.

The age10k recycler upload showed that recycling can add PnL versus plain q5,
but the inner q5 probe kept refilling back to -150. This stricter wrapper turns
the probe into a true execution recycler:

* allow a q5 buy only when VELVET is already at -200 and no q5 lot is open;
* block further q5 buys while the lot is open or position is above -200;
* sell the lot back at best bid once bid >= entry + 1 tick within 10k ticks.

This should test the Mark55 execution edge without allowing terminal inventory
drift to dominate the result.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE = (
    REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_mark55_m67_inside_q5.py"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "outputs"
    / "submissions"
    / "r4"
    / "submission_r4_probe_mark55_singlelot_recycle_pt1_age10k.py"
)


APPENDIX = r'''

# ====================================================================
# R4 MARK55 SINGLE-LOT RECYCLER PROBE.
#
# Diagnostic upload, not a final candidate by itself.
#
# age10k_recycler improved on m67_q5, but q5 kept refilling back to -150.
# This wrapper allows the q5 bid only when VELVET is already at -200 and no
# Mark55/Mark67 lot is open. Once a lot is open, it blocks further positive
# VELVET orders from the q5 wrapper until the lot is recycled.
# ====================================================================
_M55_SINGLE_BASE_TRADER = Trader
_M55S_PRODUCT = 'VELVETFRUIT_EXTRACT'
_M55S_TARGET_TICKS = 1
_M55S_MAX_AGE = 10_000
_M55S_MIN_AGE = 100
_M55S_MAX_SHORT = -200
_M55S_COUNTERPARTIES = ('Mark 55', 'Mark 67')

class _M55SLot:
    def __init__(self, timestamp, price, qty, seller):
        self.timestamp = int(timestamp)
        self.price = int(price)
        self.qty = int(qty)
        self.seller = seller

class Trader:
    def __init__(self):
        self._inner = _M55_SINGLE_BASE_TRADER()
        self._lots = []
        self._seen_own = set()
        self._last_timestamp = None

    def _ingest_own(self, state):
        ts = int(state.timestamp)
        if self._last_timestamp is not None and ts < self._last_timestamp:
            self._lots = []
            self._seen_own = set()
        self._last_timestamp = ts
        for trade in (state.own_trades or {}).get(_M55S_PRODUCT, []) or []:
            if getattr(trade, 'buyer', None) != 'SUBMISSION':
                continue
            seller = getattr(trade, 'seller', None)
            if seller not in _M55S_COUNTERPARTIES:
                continue
            qty = int(getattr(trade, 'quantity', 0) or 0)
            if qty <= 0:
                continue
            price = int(getattr(trade, 'price', 0) or 0)
            key = (int(getattr(trade, 'timestamp', ts) or ts), price, qty, seller)
            if key in self._seen_own:
                continue
            self._seen_own.add(key)
            self._lots.append(_M55SLot(key[0], price, qty, seller))

    def _block_refill_buys(self, orders, state):
        pos = int(state.position.get(_M55S_PRODUCT, 0))
        if pos <= _M55S_MAX_SHORT and not self._lots:
            return orders
        existing = list((orders or {}).get(_M55S_PRODUCT, []) or [])
        if not existing:
            return orders
        kept = [order for order in existing if int(order.quantity) <= 0]
        if len(kept) == len(existing):
            return orders
        orders = dict(orders or {})
        if kept:
            orders[_M55S_PRODUCT] = kept
        else:
            orders.pop(_M55S_PRODUCT, None)
        return orders

    def _append_recycle_sell(self, orders, state):
        if not self._lots:
            return orders
        depth = state.order_depths.get(_M55S_PRODUCT)
        if depth is None or not depth.buy_orders:
            return orders
        existing = list((orders or {}).get(_M55S_PRODUCT, []) or [])
        if any(int(order.quantity) < 0 for order in existing):
            return orders

        ts = int(state.timestamp)
        pos = int(state.position.get(_M55S_PRODUCT, 0))
        sell_capacity = pos - _M55S_MAX_SHORT
        if sell_capacity <= 0:
            return orders

        bid = int(max(depth.buy_orders))
        qty_to_sell = 0
        remaining_capacity = int(sell_capacity)
        kept = []
        for lot in self._lots:
            age = ts - lot.timestamp
            if age < _M55S_MIN_AGE or (age <= _M55S_MAX_AGE and bid < lot.price + _M55S_TARGET_TICKS):
                kept.append(lot)
                continue
            if age > _M55S_MAX_AGE and bid < lot.price:
                kept.append(lot)
                continue
            take = min(lot.qty, remaining_capacity)
            if take <= 0:
                kept.append(lot)
                continue
            qty_to_sell += take
            remaining_capacity -= take
            lot.qty -= take
            if lot.qty > 0:
                kept.append(lot)
            if remaining_capacity <= 0:
                kept.extend(self._lots[self._lots.index(lot) + 1:])
                break
        self._lots = kept
        if qty_to_sell <= 0:
            return orders
        orders = dict(orders or {})
        orders.setdefault(_M55S_PRODUCT, []).append(Order(_M55S_PRODUCT, bid, -int(qty_to_sell)))
        return orders

    def run(self, state):
        self._ingest_own(state)
        orders, conversions, trader_data = self._inner.run(state)
        orders = self._block_refill_buys(orders, state)
        orders = self._append_recycle_sell(orders, state)
        return orders, conversions, trader_data
'''


def export(base: Path, out: Path) -> Path:
    source = base.read_text()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source.rstrip() + APPENDIX + "\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    path = export(args.base, args.out)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
