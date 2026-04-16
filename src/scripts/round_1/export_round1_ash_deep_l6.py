"""Export L6 — Phase-L K2 with lighter inner weights (5/2/2)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import round1_ash_deep_l6_engine_config
from src.scripts.round_1._ash_deep_bundle import (
    DEFAULT_OUT_DIR,
    AshDeepBundleSpec,
    InlineSpec,
    export_bundle,
)

_SPEC = AshDeepBundleSpec(
    variant="ash_deep_l6",
    factory_name="round1_ash_deep_l6_engine_config",
    factory=round1_ash_deep_l6_engine_config,
    label="Round-1 Phase-L L6 — K2 with weights 5/2/2 (55% inner)",
    purpose=(
        "K2 edges (2.5/4/6) with weights (5, 2, 2) = inner 55.6%, "
        "outers 22.2% each. Tests whether shifting slightly more "
        "weight toward outers (vs K2's 60%/20%/20%) captures "
        "more outer-level edge without losing inner coverage. "
        "Local +3 515 (vs K2 +3 497). Close call — officially "
        "could go either way."
    ),
    inline=InlineSpec(
        strategy_module_path="src/strategies/ash_ladder.py",
        strategy_class_name="AshLadderStrategy",
        params_class_name="LadderParams",
        new_strategy_name="ash_ladder",
        params_dict={
            "edges": (2.5, 4.0, 6.0),
            "size_mults": (1.0, 1.5, 2.0),
            "skew_coef": 2.0,
            "flatten_threshold": 0.7,
            "weights": (5, 2, 2),
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
