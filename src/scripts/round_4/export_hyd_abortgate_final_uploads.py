"""Export final HYDROGEL abort-gate upload candidates.

These are the final mechanism-discriminating HYD candidates before choosing the
Round 4 submission. They are built on the validated sell7 base and vary only the
HYD high-regime inventory overlay:

* flat: robust core edge;
* long20: balanced alpha/risk;
* long40: max reasonable alpha without jumping to the path-fitted long80;
* strict flat: defensive confirmation.
* strict long40/long80: final post-selection probes for whether stricter
  confirmation can preserve the official high-regime path while carrying more
  size without promoting raw hardlong80 path risk.
* strict long120: frontier probe only; tests whether the size edge continues
  past +80, with higher false-trigger tail risk.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"
BASE = SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_validated.py"


@dataclass(frozen=True)
class AbortGateSpec:
    label: str
    target_pos: int
    slope_threshold: float
    out: Path


def specs() -> list[AbortGateSpec]:
    return [
        AbortGateSpec(
            "sell7_hyd_abortgate15_flat60",
            0,
            15.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate15_flat60.py",
        ),
        AbortGateSpec(
            "sell7_hyd_abortgate15_long20_60",
            20,
            15.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate15_long20_60.py",
        ),
        AbortGateSpec(
            "sell7_hyd_abortgate15_long40_60",
            40,
            15.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate15_long40_60.py",
        ),
        AbortGateSpec(
            "sell7_hyd_abortgate18_flat60",
            0,
            18.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_flat60.py",
        ),
        AbortGateSpec(
            "sell7_hyd_abortgate18_long40_60",
            40,
            18.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long40_60.py",
        ),
        AbortGateSpec(
            "sell7_hyd_abortgate18_long80_60",
            80,
            18.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long80_60.py",
        ),
        AbortGateSpec(
            "sell7_hyd_abortgate18_long120_60",
            120,
            18.0,
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long120_60.py",
        ),
    ]


def _rename_final_trader(source: str, new_name: str) -> str:
    marker = "\nclass Trader:"
    index = source.rfind(marker)
    if index < 0:
        raise ValueError("base bundle does not contain a final top-level class Trader")
    return source[:index] + f"\nclass {new_name}:" + source[index + len(marker) :]


def _append_abortgate_wrapper(source: str, spec: AbortGateSpec) -> str:
    base_name = "_R4AbortGateBaseTrader"
    renamed = _rename_final_trader(source.rstrip(), base_name)
    threshold_literal = repr(float(spec.slope_threshold))
    appendix = f'''

# ====================================================================
# R4 FINAL HYDROGEL CANDIDATE -- {spec.label}.
#
# Mechanism:
#   - Detect early high-regime HYD path: mid >= 10020 during 20k-30k.
#   - Act immediately instead of waiting for confirmation: target {spec.target_pos}.
#   - At 40k, require the 20k->40k mid slope to be >= {spec.slope_threshold:g}.
#   - If failed, abort and flatten before allowing the base sleeve to resume.
#   - If passed, keep the target until the 60k bid-confirmed release.
#
# This is designed to preserve the official high-regime cash edge while adding
# a false-trigger escape hatch for unseen 1M robustness.
# ====================================================================
_R4_HYD_ABORT_BASE_TRADER = {base_name}
_HYD_ABORT_TRIGGER_START = 20_000
_HYD_ABORT_TRIGGER_END = 30_000
_HYD_ABORT_TRIGGER_MID = 10_020.0
_HYD_ABORT_SLOPE_START_TS = 20_000
_HYD_ABORT_GATE_TS = 40_000
_HYD_ABORT_SLOPE_THRESHOLD = {threshold_literal}
_HYD_ABORT_CONFIRM_TS = 60_000
_HYD_ABORT_CONFIRM_BID = 10_048
_HYD_ABORT_TARGET_POS = {int(spec.target_pos)}

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


def export_one(spec: AbortGateSpec) -> Path:
    source = BASE.read_text()
    spec.out.write_text(_append_abortgate_wrapper(source, spec))
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
