"""Export uploadable VELVET-only regime probe submissions.

These files start from validated `sell7` and override only the VELVET/voucher
schedule layer. HYDROGEL and the rest of the R3 bundle are left as-is.

The goal is simulator calibration, not a final all-in candidate:

* max-alpha VELVET-only one-shot gate;
* cover-only negative control;
* lower-tail delayed gate;
* rolling-confirm diagnostic.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"
BASE = SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_validated.py"


@dataclass(frozen=True)
class VelvetUploadSpec:
    label: str
    mode: str
    out: Path
    buy: int = 5248
    sell: int = 5264
    active_buy_limit: int = 200
    active_sell_limit: int = 200
    gate_ts: int = 30_000
    drop_ticks: float = 20.0
    min_ts: int = 20_000
    active_duration: int = 40_000
    cooldown: int = 20_000
    rebound_confirm: float = 0.0


def specs() -> list[VelvetUploadSpec]:
    return [
        VelvetUploadSpec(
            "velvet_only_gate30_d20_buy5248_sell5264",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_only_gate30_d20_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            gate_ts=30_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_negctrl_gate30_cover_only_sell5272",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_negctrl_gate30_cover_only_sell5272.py",
            buy=5248,
            sell=5272,
            gate_ts=30_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_capflat_gate30_d20_buy5248_sell5264",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_capflat_gate30_d20_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            active_buy_limit=0,
            gate_ts=30_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_capshort100_gate30_d20_buy5248_sell5264",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_capshort100_gate30_d20_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            active_buy_limit=-100,
            gate_ts=30_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_caplong80_gate30_d20_buy5248_sell5264",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_caplong80_gate30_d20_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            active_buy_limit=80,
            gate_ts=30_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_delayed_gate50_d20_buy5248_sell5264",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_delayed_gate50_d20_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            gate_ts=50_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_capflat_delayed_gate50_d20_buy5248_sell5264",
            "one_shot",
            SUB_DIR / "submission_r4_probe_velvet_capflat_delayed_gate50_d20_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            active_buy_limit=0,
            gate_ts=50_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "velvet_rolling_confirm_d25_r3_buy5248_sell5264",
            "rolling",
            SUB_DIR / "submission_r4_probe_velvet_rolling_confirm_d25_r3_buy5248_sell5264.py",
            buy=5248,
            sell=5264,
            drop_ticks=25.0,
            rebound_confirm=3.0,
            active_duration=40_000,
            cooldown=20_000,
        ),
    ]


def _rename_final_trader(source: str, new_name: str) -> str:
    marker = "\nclass Trader:"
    index = source.rfind(marker)
    if index < 0:
        raise ValueError("base bundle does not contain a final top-level class Trader")
    return source[:index] + f"\nclass {new_name}:" + source[index + len(marker) :]


def _append_wrapper(source: str, spec: VelvetUploadSpec) -> str:
    base_name = "_R4VelvetProbeBaseTrader"
    renamed = _rename_final_trader(source.rstrip(), base_name)
    appendix = f'''

# ====================================================================
# R4 VELVET-ONLY REGIME PROBE -- {spec.label}.
#
# This is a calibration upload. It starts from validated sell7 and replaces
# only the VELVET/voucher schedule orders. HYDROGEL remains unchanged.
# ====================================================================
_R4_VELVET_PROBE_BASE_TRADER = {base_name}
_R4_VELVET_PROBE_MODE = {spec.mode!r}
_R4_VELVET_PROBE_BUY = {spec.buy}
_R4_VELVET_PROBE_SELL = {spec.sell}
_R4_VELVET_PROBE_ACTIVE_BUY_LIMIT = {spec.active_buy_limit}
_R4_VELVET_PROBE_ACTIVE_SELL_LIMIT = {spec.active_sell_limit}
_R4_VELVET_PROBE_GATE_TS = {spec.gate_ts}
_R4_VELVET_PROBE_DROP = {spec.drop_ticks}
_R4_VELVET_PROBE_MIN_TS = {spec.min_ts}
_R4_VELVET_PROBE_ACTIVE_DURATION = {spec.active_duration}
_R4_VELVET_PROBE_COOLDOWN = {spec.cooldown}
_R4_VELVET_PROBE_REBOUND_CONFIRM = {spec.rebound_confirm}

def _r4_vp_default_state():
    return {{
        'open_mid': None,
        'gate_decided': False,
        'gate_active': False,
        'peak_mid': None,
        'trough_mid': None,
        'active_until': -1,
        'cooldown_until': -1,
        'last_seen_ts': -1,
    }}

def _r4_vp_mid(state):
    depth = state.order_depths.get('VELVETFRUIT_EXTRACT')
    if depth is None or not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2

def _r4_vp_update(probe_state, timestamp, mid):
    if int(probe_state.get('last_seen_ts', -1)) > int(timestamp):
        probe_state.clear()
        probe_state.update(_r4_vp_default_state())
    probe_state['last_seen_ts'] = int(timestamp)
    if probe_state.get('open_mid') is None:
        probe_state['open_mid'] = float(mid)
    peak = probe_state.get('peak_mid')
    trough = probe_state.get('trough_mid')
    if peak is None or float(mid) > float(peak):
        probe_state['peak_mid'] = float(mid)
    if trough is None or float(mid) < float(trough):
        probe_state['trough_mid'] = float(mid)
    if _R4_VELVET_PROBE_MODE == 'one_shot':
        if (not bool(probe_state.get('gate_decided', False))) and int(timestamp) >= _R4_VELVET_PROBE_GATE_TS:
            probe_state['gate_active'] = float(probe_state['open_mid']) - float(mid) >= _R4_VELVET_PROBE_DROP
            probe_state['gate_decided'] = True
        return
    if _R4_VELVET_PROBE_MODE != 'rolling' or int(timestamp) < _R4_VELVET_PROBE_MIN_TS:
        return
    if int(timestamp) < int(probe_state.get('cooldown_until', -1)):
        return
    drawdown = float(probe_state['peak_mid']) - float(mid)
    if drawdown < _R4_VELVET_PROBE_DROP:
        return
    trough = min(float(probe_state.get('trough_mid') or mid), float(mid))
    probe_state['trough_mid'] = trough
    if _R4_VELVET_PROBE_REBOUND_CONFIRM > 0 and float(mid) < trough + _R4_VELVET_PROBE_REBOUND_CONFIRM:
        return
    probe_state['gate_active'] = True
    probe_state['active_until'] = max(int(probe_state.get('active_until', -1)), int(timestamp) + _R4_VELVET_PROBE_ACTIVE_DURATION)
    probe_state['cooldown_until'] = int(timestamp) + _R4_VELVET_PROBE_COOLDOWN

def _r4_vp_active(probe_state, timestamp):
    if _R4_VELVET_PROBE_MODE == 'one_shot':
        return bool(probe_state.get('gate_active', False)) and int(timestamp) >= _R4_VELVET_PROBE_GATE_TS
    if _R4_VELVET_PROBE_MODE == 'rolling':
        return bool(probe_state.get('gate_active', False)) and int(timestamp) <= int(probe_state.get('active_until', -1))
    return False

def _r4_vp_cfg(product, schedule, timestamp, active):
    cfg = schedule[0][1]
    for start, candidate in schedule:
        if int(timestamp) >= start:
            cfg = candidate
        else:
            break
    if product == 'VELVETFRUIT_EXTRACT' and active:
        cfg = dict(cfg)
        cfg['buy'] = _R4_VELVET_PROBE_BUY
        cfg['sell'] = _R4_VELVET_PROBE_SELL
        cfg['buy_limit'] = _R4_VELVET_PROBE_ACTIVE_BUY_LIMIT
        cfg['sell_limit'] = _R4_VELVET_PROBE_ACTIVE_SELL_LIMIT
    return cfg

def _r4_vp_orders_for_product(product, schedule, state, active):
    depth = state.order_depths.get(product)
    if depth is None:
        return []
    cfg = _r4_vp_cfg(product, schedule, state.timestamp, active)
    position = int(state.position.get(product, 0))
    orders = []
    if int(state.timestamp) >= _VELVET_FLATTEN_START:
        if position > 0 and depth.buy_orders:
            best_bid = max(depth.buy_orders.keys())
            qty = min(int(cfg['max_order']), int(depth.buy_orders[best_bid]), position)
            if qty > 0:
                orders.append(Order(product, int(best_bid), -qty))
        elif position < 0 and depth.sell_orders:
            best_ask = min(depth.sell_orders.keys())
            qty = min(int(cfg['max_order']), -int(depth.sell_orders[best_ask]), -position)
            if qty > 0:
                orders.append(Order(product, int(best_ask), qty))
        return orders
    buy_limit = int(cfg.get('buy_limit', cfg['limit']))
    sell_limit = int(cfg.get('sell_limit', cfg['limit']))
    if depth.sell_orders:
        best_ask = min(depth.sell_orders.keys())
        ask_volume = -int(depth.sell_orders[best_ask])
        if int(best_ask) <= int(cfg['buy']) and position < buy_limit:
            qty = min(int(cfg['max_order']), ask_volume, buy_limit - position)
            if qty > 0:
                orders.append(Order(product, int(best_ask), qty))
                position += qty
    if depth.buy_orders:
        best_bid = max(depth.buy_orders.keys())
        bid_volume = int(depth.buy_orders[best_bid])
        if int(best_bid) >= int(cfg['sell']) and position > -sell_limit:
            qty = min(int(cfg['max_order']), bid_volume, sell_limit + position)
            if qty > 0:
                orders.append(Order(product, int(best_bid), -qty))
    return orders

class Trader:
    def __init__(self):
        self._inner = _R4_VELVET_PROBE_BASE_TRADER()
        self._probe_state = _r4_vp_default_state()

    def run(self, state):
        orders, conversions, trader_data = self._inner.run(state)
        orders = dict(orders or {{}})
        mid = _r4_vp_mid(state)
        if mid is not None:
            _r4_vp_update(self._probe_state, int(state.timestamp), float(mid))
        active = _r4_vp_active(self._probe_state, int(state.timestamp))
        for product, schedule in _VELVET_SCHEDULES.items():
            replacement = _r4_vp_orders_for_product(product, schedule, state, active)
            if replacement:
                orders[product] = replacement
            else:
                orders.pop(product, None)
        return orders, conversions, trader_data
'''
    return renamed + appendix + "\n"


def export_one(spec: VelvetUploadSpec) -> Path:
    source = BASE.read_text()
    spec.out.write_text(_append_wrapper(source, spec))
    return spec.out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=[s.label for s in specs()])
    args = parser.parse_args()
    selected = [s for s in specs() if args.label in (None, s.label)]
    for spec in selected:
        path = export_one(spec)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
