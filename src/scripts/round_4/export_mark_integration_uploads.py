"""Export Round 4 final-HYD plus Mark-integration upload probes.

There are two base families:

* ``stack_hydabort18l80``: current VELVET/options stack wrapped with the
  selected HYD abort-gate policy.
* ``sell7_hydabort18l80``: the existing sell7 + HYD abortgate18_long80 file.

Both families then optionally append the same narrow Mark layers.

These are calibration uploads, not a claim that Mark is standalone alpha.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"
BASE_STACK = SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_stack_officialmax_probe.py"
BASE_SELL7_HYD_ABORT18_L80 = SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long80_60.py"


@dataclass(frozen=True)
class ExportSpec:
    family: str
    label: str
    base: Path
    wrap_hyd_abort: bool
    mark55_exec: bool = False
    mark22_core: bool = False
    mark22_time_control: bool = False

    @property
    def out(self) -> Path:
        return SUB_DIR / f"submission_r4_final_{self.family}_{self.label}.py"


def specs() -> list[ExportSpec]:
    base_variants = [
        ("stack_hydabort18l80", BASE_STACK, True),
        ("sell7_hydabort18l80", BASE_SELL7_HYD_ABORT18_L80, False),
    ]
    labels = [
        ("nomark_control", False, False, False),
        ("mark55_exec", True, False, False),
        ("mark22_core", False, True, False),
        ("mark22_time_control", False, False, True),
        ("mark55_mark22_combo", True, True, False),
    ]
    return [
        ExportSpec(
            family=family,
            base=base,
            wrap_hyd_abort=wrap_hyd_abort,
            label=label,
            mark55_exec=mark55_exec,
            mark22_core=mark22_core,
            mark22_time_control=mark22_time_control,
        )
        for family, base, wrap_hyd_abort in base_variants
        for label, mark55_exec, mark22_core, mark22_time_control in labels
    ]


def _rename_final_trader(source: str, new_name: str) -> str:
    marker = "\nclass Trader:"
    index = source.rfind(marker)
    if index < 0:
        raise ValueError("bundle does not contain a final top-level class Trader")
    return source[:index] + f"\nclass {new_name}:" + source[index + len(marker) :]


def _append_hyd_abortgate(source: str) -> str:
    base_name = "_R4StackHydAbortBaseTrader"
    renamed = _rename_final_trader(source.rstrip(), base_name)
    appendix = f'''

# ====================================================================
# R4 FINAL SPINE -- VELVET/options stack + HYD abortgate18_long80_60.
#
# HYD policy:
#   - trigger high regime if HYD mid >= 10020 during 20k-30k;
#   - target +80 immediately after trigger;
#   - at 40k require 20k->40k slope >= 18;
#   - at 60k require best bid >= 10048, else abort and flatten.
#
# This keeps the current VELVET stack unchanged and replaces only the HYD
# high-regime overlay.
# ====================================================================
_R4_HYD_ABORT_BASE_TRADER = {base_name}
_HYD_ABORT_TRIGGER_START = 20_000
_HYD_ABORT_TRIGGER_END = 30_000
_HYD_ABORT_TRIGGER_MID = 10_020.0
_HYD_ABORT_SLOPE_START_TS = 20_000
_HYD_ABORT_GATE_TS = 40_000
_HYD_ABORT_SLOPE_THRESHOLD = 18.0
_HYD_ABORT_CONFIRM_TS = 60_000
_HYD_ABORT_CONFIRM_BID = 10_048
_HYD_ABORT_TARGET_POS = 80

class Trader:
    def __init__(self):
        self._inner = _R4_HYD_ABORT_BASE_TRADER()
        self._last_timestamp = None
        self._reset_hyd_state()

    def run(self, state):
        ts = int(state.timestamp)
        if self._last_timestamp is not None and ts < self._last_timestamp:
            self._reset_hyd_state()
        self._last_timestamp = ts

        orders, conversions, trader_data = self._inner.run(state)
        self._observe_slope_start(state)
        self._observe_trigger(state)
        self._observe_abort_gate(state)
        self._observe_release_or_abort(state)

        if self._hyd_triggered and self._hyd_aborted:
            if int(state.position.get('HYDROGEL_PACK', 0)) != 0:
                orders = self._hard_target_hyd(state, orders, 0)
            return orders, conversions, trader_data

        if self._hyd_triggered and not self._hyd_released:
            orders = self._hard_target_hyd(state, orders, _HYD_ABORT_TARGET_POS)
        return orders, conversions, trader_data

    def _reset_hyd_state(self):
        self._hyd_triggered = False
        self._hyd_released = False
        self._hyd_aborted = False
        self._hyd_slope_mid = None
        self._hyd_gate_checked = False

    def _observe_slope_start(self, state):
        if self._hyd_slope_mid is not None or int(state.timestamp) < _HYD_ABORT_SLOPE_START_TS:
            return
        self._hyd_slope_mid = self._mid(state)

    def _observe_trigger(self, state):
        if self._hyd_triggered:
            return
        ts = int(state.timestamp)
        if ts < _HYD_ABORT_TRIGGER_START or ts > _HYD_ABORT_TRIGGER_END:
            return
        mid = self._mid(state)
        if mid is not None and mid >= _HYD_ABORT_TRIGGER_MID:
            self._hyd_triggered = True

    def _observe_abort_gate(self, state):
        if (
            not self._hyd_triggered
            or self._hyd_released
            or self._hyd_aborted
            or self._hyd_gate_checked
            or int(state.timestamp) < _HYD_ABORT_GATE_TS
        ):
            return
        self._hyd_gate_checked = True
        mid = self._mid(state)
        if (
            mid is None
            or self._hyd_slope_mid is None
            or mid - self._hyd_slope_mid < _HYD_ABORT_SLOPE_THRESHOLD
        ):
            self._hyd_aborted = True

    def _observe_release_or_abort(self, state):
        if not self._hyd_triggered or self._hyd_released or self._hyd_aborted:
            return
        if int(state.timestamp) >= _HYD_ABORT_CONFIRM_TS:
            bid = self._best_bid(state)
            if bid is not None and bid >= _HYD_ABORT_CONFIRM_BID:
                self._hyd_released = True
            else:
                self._hyd_aborted = True

    def _best_bid(self, state):
        depth = state.order_depths.get('HYDROGEL_PACK')
        if depth is None or not depth.buy_orders:
            return None
        return int(max(depth.buy_orders.keys()))

    def _mid(self, state):
        depth = state.order_depths.get('HYDROGEL_PACK')
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2

    def _hard_target_hyd(self, state, orders, target_pos):
        orders = dict(orders or {{}})
        depth = state.order_depths.get('HYDROGEL_PACK')
        pos = int(state.position.get('HYDROGEL_PACK', 0))
        delta = int(target_pos - pos)
        if depth is None or delta == 0:
            orders['HYDROGEL_PACK'] = []
            return orders
        if delta > 0 and depth.sell_orders:
            best_ask = min(depth.sell_orders.keys())
            orders['HYDROGEL_PACK'] = [Order('HYDROGEL_PACK', int(best_ask), delta)]
        elif delta < 0 and depth.buy_orders:
            best_bid = max(depth.buy_orders.keys())
            orders['HYDROGEL_PACK'] = [Order('HYDROGEL_PACK', int(best_bid), delta)]
        else:
            orders['HYDROGEL_PACK'] = []
        return orders
'''
    return renamed + appendix + "\n"


def _append_wrapper(source: str, base_name: str, base_constant: str, appendix: str) -> str:
    renamed = _rename_final_trader(source.rstrip(), base_name)
    patched_appendix = appendix.replace(f"{base_constant} = Trader", f"{base_constant} = {base_name}", 1)
    return renamed + patched_appendix + "\n"


MARK55_EXEC_APPENDIX = r'''

# ====================================================================
# R4 MARK55 EXECUTION-ONLY OVERLAY.
#
# This layer does not create a new VELVET inventory target. If the base
# strategy already sends a VELVET buy/cover order and recent Mark67 VELVET
# buying predicts Mark55 sell flow, it moves up to 5 units from the crossing
# order to a non-crossing one-tick-inside bid.
# ====================================================================
_M55X_BASE_TRADER = Trader
_M55X_PRODUCT = 'VELVETFRUIT_EXTRACT'
_M55X_WINDOW = 30_000
_M55X_COUNT_THRESHOLD = 3
_M55X_SIZE = 5

class _M55XRollingCounter:
    def __init__(self, window):
        self.window = int(window)
        self.events = deque()

    def clear(self):
        self.events.clear()

    def prune(self, timestamp):
        cutoff = int(timestamp) - self.window
        while self.events and self.events[0] < cutoff:
            self.events.popleft()

    def add(self, timestamp):
        self.events.append(int(timestamp))
        self.prune(timestamp)

    @property
    def count(self):
        return len(self.events)

class Trader:
    def __init__(self):
        self._inner = _M55X_BASE_TRADER()
        self._mark67_buy = _M55XRollingCounter(_M55X_WINDOW)
        self._seen_market = set()
        self._last_timestamp = None

    def _ingest(self, state):
        ts = int(state.timestamp)
        if self._last_timestamp is not None and ts < self._last_timestamp:
            self._mark67_buy.clear()
            self._seen_market.clear()
        self._last_timestamp = ts
        self._mark67_buy.prune(ts)
        for trade in (state.market_trades or {}).get(_M55X_PRODUCT, []) or []:
            if getattr(trade, 'buyer', None) != 'Mark 67':
                continue
            trade_ts = int(getattr(trade, 'timestamp', ts) or ts)
            price = int(getattr(trade, 'price', 0) or 0)
            qty = int(getattr(trade, 'quantity', 0) or 0)
            key = (trade_ts, price, qty, getattr(trade, 'buyer', None), getattr(trade, 'seller', None))
            if key in self._seen_market:
                continue
            self._seen_market.add(key)
            self._mark67_buy.add(trade_ts)

    def _active(self):
        return self._mark67_buy.count >= _M55X_COUNT_THRESHOLD

    def _price_improve_existing_buy(self, orders, state):
        if not self._active():
            return orders
        depth = state.order_depths.get(_M55X_PRODUCT)
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return orders
        existing = list((orders or {}).get(_M55X_PRODUCT, []) or [])
        if not any(int(order.quantity) > 0 for order in existing):
            return orders
        best_bid = int(max(depth.buy_orders))
        best_ask = int(min(depth.sell_orders))
        passive_price = best_bid + 1
        if passive_price >= best_ask:
            return orders

        remaining = _M55X_SIZE
        rewritten = []
        shifted = 0
        for order in existing:
            qty = int(order.quantity)
            if qty <= 0 or remaining <= 0:
                rewritten.append(order)
                continue
            take = min(qty, remaining)
            left = qty - take
            if left > 0:
                rewritten.append(Order(_M55X_PRODUCT, int(order.price), left))
            shifted += take
            remaining -= take
        if shifted <= 0:
            return orders
        rewritten.append(Order(_M55X_PRODUCT, passive_price, shifted))
        new_orders = dict(orders or {})
        new_orders[_M55X_PRODUCT] = rewritten
        return new_orders

    def run(self, state):
        self._ingest(state)
        orders, conversions, trader_data = self._inner.run(state)
        orders = self._price_improve_existing_buy(orders, state)
        return orders, conversions, trader_data
'''


MARK22_CORE_APPENDIX = r'''

# ====================================================================
# R4 MARK22 CORE-OPTION FILTER.
#
# This is a tiny integration probe. It does not open fresh option longs.
# When recent Mark22 sell/basket flow is active, it allows one small reduce
# sell in already-long VEV_5000/5100 positions at strong bids.
# ====================================================================
_M22X_BASE_TRADER = Trader
_M22X_PRODUCTS = ('VEV_5000', 'VEV_5100')
_M22X_PRODUCT_THRESH = {'VEV_5000': 268, 'VEV_5100': 177}
_M22X_PRODUCT_MIN_POS = {'VEV_5000': 100, 'VEV_5100': 100}
_M22X_FIRE_SIZE = 5
_M22X_GATE_WINDOW = 5_000
_M22X_FIRE_COOLDOWN = 5_000
_M22X_GATE_SYMBOLS = (
    'VELVETFRUIT_EXTRACT',
    'VEV_4000', 'VEV_4500', 'VEV_5000', 'VEV_5100', 'VEV_5200',
    'VEV_5300', 'VEV_5400', 'VEV_5500', 'VEV_6000', 'VEV_6500',
)

class Trader:
    def __init__(self):
        self._inner = _M22X_BASE_TRADER()
        self._last_fire_ts = -10**9
        self._gate_recent_ts = -10**9
        self._seen_market_trades = set()
        self._last_seen_timestamp = None

    def _ingest_market_trades(self, state):
        ts = int(state.timestamp)
        if self._last_seen_timestamp is not None and ts < self._last_seen_timestamp:
            self._seen_market_trades.clear()
            self._last_fire_ts = -10**9
            self._gate_recent_ts = -10**9
        self._last_seen_timestamp = ts
        market = state.market_trades or {}
        for sym in _M22X_GATE_SYMBOLS:
            for trade in market.get(sym, []) or []:
                if getattr(trade, 'seller', None) != 'Mark 22':
                    continue
                trade_ts = int(getattr(trade, 'timestamp', ts) or ts)
                price = int(getattr(trade, 'price', 0) or 0)
                qty = int(getattr(trade, 'quantity', 0) or 0)
                key = (trade_ts, sym, price, qty, getattr(trade, 'seller', None))
                if key in self._seen_market_trades:
                    continue
                self._seen_market_trades.add(key)
                if trade_ts > self._gate_recent_ts:
                    self._gate_recent_ts = trade_ts

    def _gate_active(self, ts):
        return self._gate_recent_ts > 0 and (int(ts) - self._gate_recent_ts) <= _M22X_GATE_WINDOW

    def _maybe_fire(self, orders, state):
        ts = int(state.timestamp)
        if not self._gate_active(ts):
            return orders
        if ts - self._last_fire_ts < _M22X_FIRE_COOLDOWN:
            return orders
        fired_any = False
        new_orders = dict(orders or {})
        for product in _M22X_PRODUCTS:
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders:
                continue
            pos = int(state.position.get(product, 0))
            if pos < _M22X_PRODUCT_MIN_POS[product]:
                continue
            best_bid = int(max(depth.buy_orders))
            if best_bid < _M22X_PRODUCT_THRESH[product]:
                continue
            existing = list(new_orders.get(product, []) or [])
            already_selling = sum(-int(order.quantity) for order in existing if int(order.quantity) < 0)
            qty = min(_M22X_FIRE_SIZE, pos)
            extra = qty - max(0, already_selling)
            if extra <= 0:
                continue
            new_orders[product] = existing + [Order(product, best_bid, -extra)]
            fired_any = True
        if fired_any:
            self._last_fire_ts = ts
        return new_orders

    def run(self, state):
        self._ingest_market_trades(state)
        orders, conversions, trader_data = self._inner.run(state)
        orders = self._maybe_fire(orders, state)
        return orders, conversions, trader_data
'''


MARK22_TIME_CONTROL_APPENDIX = r'''

# ====================================================================
# R4 MARK22 CORE-OPTION MATCHED TIME CONTROL.
#
# Same VEV_5000/5100 reduce action as the Mark22 filter, but the gate is a
# fixed cadence. Use this to test whether Mark identity matters.
# ====================================================================
_M22C_BASE_TRADER = Trader
_M22C_PRODUCTS = ('VEV_5000', 'VEV_5100')
_M22C_PRODUCT_THRESH = {'VEV_5000': 268, 'VEV_5100': 177}
_M22C_PRODUCT_MIN_POS = {'VEV_5000': 100, 'VEV_5100': 100}
_M22C_FIRE_SIZE = 5
_M22C_FIRE_PERIOD = 10_000
_M22C_FIRE_COOLDOWN = 5_000
_M22C_FIRE_FIRST_TS = 30_000

class Trader:
    def __init__(self):
        self._inner = _M22C_BASE_TRADER()
        self._last_fire_ts = -10**9
        self._last_seen_timestamp = None

    def _maybe_reset(self, state):
        ts = int(state.timestamp)
        if self._last_seen_timestamp is not None and ts < self._last_seen_timestamp:
            self._last_fire_ts = -10**9
        self._last_seen_timestamp = ts

    def _gate_active(self, ts):
        if ts < _M22C_FIRE_FIRST_TS:
            return False
        if self._last_fire_ts <= 0:
            return True
        return (ts - self._last_fire_ts) >= _M22C_FIRE_PERIOD

    def _maybe_fire(self, orders, state):
        ts = int(state.timestamp)
        if not self._gate_active(ts):
            return orders
        if ts - self._last_fire_ts < _M22C_FIRE_COOLDOWN:
            return orders
        fired_any = False
        new_orders = dict(orders or {})
        for product in _M22C_PRODUCTS:
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders:
                continue
            pos = int(state.position.get(product, 0))
            if pos < _M22C_PRODUCT_MIN_POS[product]:
                continue
            best_bid = int(max(depth.buy_orders))
            if best_bid < _M22C_PRODUCT_THRESH[product]:
                continue
            existing = list(new_orders.get(product, []) or [])
            already_selling = sum(-int(order.quantity) for order in existing if int(order.quantity) < 0)
            qty = min(_M22C_FIRE_SIZE, pos)
            extra = qty - max(0, already_selling)
            if extra <= 0:
                continue
            new_orders[product] = existing + [Order(product, best_bid, -extra)]
            fired_any = True
        if fired_any:
            self._last_fire_ts = ts
        return new_orders

    def run(self, state):
        self._maybe_reset(state)
        orders, conversions, trader_data = self._inner.run(state)
        orders = self._maybe_fire(orders, state)
        return orders, conversions, trader_data
'''


def build_source(spec: ExportSpec) -> str:
    source = spec.base.read_text()
    if spec.wrap_hyd_abort:
        source = _append_hyd_abortgate(source)
    if spec.mark55_exec:
        source = _append_wrapper(source, "_R4Mark55ExecBaseTrader", "_M55X_BASE_TRADER", MARK55_EXEC_APPENDIX)
    if spec.mark22_core:
        source = _append_wrapper(source, "_R4Mark22CoreBaseTrader", "_M22X_BASE_TRADER", MARK22_CORE_APPENDIX)
    if spec.mark22_time_control:
        source = _append_wrapper(
            source,
            "_R4Mark22TimeControlBaseTrader",
            "_M22C_BASE_TRADER",
            MARK22_TIME_CONTROL_APPENDIX,
        )
    return source.rstrip() + "\n"


def export_one(spec: ExportSpec) -> Path:
    path = spec.out
    path.write_text(build_source(spec))
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=sorted({spec.family for spec in specs()}), nargs="*")
    parser.add_argument("--only", choices=sorted({spec.label for spec in specs()}), nargs="*")
    args = parser.parse_args()
    selected = [
        spec
        for spec in specs()
        if (not args.family or spec.family in args.family)
        and (not args.only or spec.label in args.only)
    ]
    for spec in selected:
        path = export_one(spec)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
