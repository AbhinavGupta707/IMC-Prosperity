"""Export additive R4 HYD + VELVET/options combo upload candidates.

These candidates answer the next official-simulator calibration question after
the separate HYD and VELVET/options uploads:

* does high-regime HYD hardlong timing add cleanly to validated VEV_5500 sell7?
* does it also add to the VELVET/options stack, or do inventory interactions
  make the combined risk too path-specific?
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"


@dataclass(frozen=True)
class ComboSpec:
    label: str
    base: Path
    target_pos: int
    out: Path


def specs() -> list[ComboSpec]:
    sell7 = SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_validated.py"
    stack = SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_stack_officialmax_probe.py"
    return [
        ComboSpec(
            "sell7_hydhardlong40_60k",
            sell7,
            40,
            SUB_DIR / "submission_r4_exp_sell7_hydhardlong40_60k.py",
        ),
        ComboSpec(
            "sell7_hydhardlong80_60k",
            sell7,
            80,
            SUB_DIR / "submission_r4_exp_sell7_hydhardlong80_60k.py",
        ),
        ComboSpec(
            "stack_hydhardlong40_60k",
            stack,
            40,
            SUB_DIR / "submission_r4_exp_stack_hydhardlong40_60k.py",
        ),
        ComboSpec(
            "stack_hydhardlong80_60k",
            stack,
            80,
            SUB_DIR / "submission_r4_exp_stack_hydhardlong80_60k.py",
        ),
    ]


def _rename_final_trader(source: str, new_name: str) -> str:
    marker = "\nclass Trader:"
    index = source.rfind(marker)
    if index < 0:
        raise ValueError("base bundle does not contain a final top-level class Trader")
    return source[:index] + f"\nclass {new_name}:" + source[index + len(marker) :]


def _append_hyd_wrapper(source: str, *, target_pos: int, label: str) -> str:
    base_name = "_R4ComboBaseTrader"
    renamed = _rename_final_trader(source.rstrip(), base_name)
    appendix = f'''

# ====================================================================
# R4 COMBO PROBE -- {label}.
#
# This appends the official-calibrated HYDROGEL high-regime hardlong wrapper
# to a validator-clean VELVET/options base. It is an additivity calibration,
# not proof that the opening HYD regime is robust on every unseen path.
# ====================================================================
_R4_COMBO_HYD_BASE_TRADER = {base_name}
_R4_COMBO_HYD_TRIGGER_START = 20_000
_R4_COMBO_HYD_TRIGGER_END = 30_000
_R4_COMBO_HYD_TRIGGER_MID = 10_020.0
_R4_COMBO_HYD_CONTROL_UNTIL = 60_000
_R4_COMBO_HYD_TARGET_POS = {target_pos}

class Trader:
    def __init__(self):
        self._inner = _R4_COMBO_HYD_BASE_TRADER()
        self._hyd_high_regime = False
        self._last_timestamp = None

    def run(self, state):
        if self._last_timestamp is not None and int(state.timestamp) < self._last_timestamp:
            self._hyd_high_regime = False
        self._last_timestamp = int(state.timestamp)
        orders, conversions, trader_data = self._inner.run(state)
        self._observe_hyd_regime(state)
        if self._hyd_high_regime and int(state.timestamp) < _R4_COMBO_HYD_CONTROL_UNTIL:
            orders = self._hard_target_hyd(state, orders, _R4_COMBO_HYD_TARGET_POS)
        return orders, conversions, trader_data

    def _observe_hyd_regime(self, state):
        if self._hyd_high_regime:
            return
        if int(state.timestamp) < _R4_COMBO_HYD_TRIGGER_START or int(state.timestamp) > _R4_COMBO_HYD_TRIGGER_END:
            return
        depth = state.order_depths.get('HYDROGEL_PACK')
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return
        mid = (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2
        if mid >= _R4_COMBO_HYD_TRIGGER_MID:
            self._hyd_high_regime = True

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


def export_one(spec: ComboSpec) -> Path:
    source = spec.base.read_text()
    spec.out.write_text(
        _append_hyd_wrapper(source, target_pos=spec.target_pos, label=spec.label)
    )
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
