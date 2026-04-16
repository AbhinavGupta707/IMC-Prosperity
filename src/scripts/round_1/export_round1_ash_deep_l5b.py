"""Export L5b — Phase-L K2 with mid outer sizes (1/2/4)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import round1_ash_deep_l5b_engine_config
from src.scripts.round_1._ash_deep_bundle import (
    DEFAULT_OUT_DIR,
    AshDeepBundleSpec,
    InlineSpec,
    export_bundle,
)

_SPEC = AshDeepBundleSpec(
    variant="ash_deep_l5b",
    factory_name="round1_ash_deep_l5b_engine_config",
    factory=round1_ash_deep_l5b_engine_config,
    label="Round-1 Phase-L L5b — K2 with mid outer sizes (1/2/4)",
    purpose=(
        "Between K2 (sizes 1/1.5/2) and L5 (sizes 1/3/5). Tests "
        "the middle-ground size-scaling hypothesis. Local "
        "identical to K2 (sim caps fill size) — official outcome "
        "should calibrate the right size-mult level."
    ),
    inline=InlineSpec(
        strategy_module_path="src/strategies/ash_ladder.py",
        strategy_class_name="AshLadderStrategy",
        params_class_name="LadderParams",
        new_strategy_name="ash_ladder",
        params_dict={
            "edges": (2.5, 4.0, 6.0),
            "size_mults": (1.0, 2.0, 4.0),
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
