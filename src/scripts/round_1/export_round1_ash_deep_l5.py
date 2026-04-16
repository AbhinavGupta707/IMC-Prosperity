"""Export L5 — Phase-L K2 with big outer sizes (1/3/5)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import round1_ash_deep_l5_engine_config
from src.scripts.round_1._ash_deep_bundle import (
    DEFAULT_OUT_DIR,
    AshDeepBundleSpec,
    InlineSpec,
    export_bundle,
)

_SPEC = AshDeepBundleSpec(
    variant="ash_deep_l5",
    factory_name="round1_ash_deep_l5_engine_config",
    factory=round1_ash_deep_l5_engine_config,
    label="Round-1 Phase-L L5 — K2 with big outer sizes (1/3/5)",
    purpose=(
        "K2 edges (2.5/4/6) with size_mults (1, 3, 5) — outer "
        "levels quote 3x and 5x the inner size. Hypothesis: outer "
        "fills are rare but high-edge; making each fill bigger "
        "captures more PnL per event. Local identical to K2 "
        "(+3 497) because sim caps maker fill size — should "
        "diverge officially where counterparty depth allows "
        "larger fills."
    ),
    inline=InlineSpec(
        strategy_module_path="src/strategies/ash_ladder.py",
        strategy_class_name="AshLadderStrategy",
        params_class_name="LadderParams",
        new_strategy_name="ash_ladder",
        params_dict={
            "edges": (2.5, 4.0, 6.0),
            "size_mults": (1.0, 3.0, 5.0),
            "skew_coef": 2.0,
            "flatten_threshold": 0.7,
            "weights": (3, 1, 1),
        },
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    path = export_bundle(_SPEC, out_dir=args.out_dir)
    print(f"[{_SPEC.variant}] wrote {path.name} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
