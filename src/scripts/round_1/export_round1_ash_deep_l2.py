"""Export L2 — Phase-L K2_split (2.5/4.5/7)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import round1_ash_deep_l2_engine_config
from src.scripts.round_1._ash_deep_bundle import (
    DEFAULT_OUT_DIR,
    AshDeepBundleSpec,
    InlineSpec,
    export_bundle,
)

_SPEC = AshDeepBundleSpec(
    variant="ash_deep_l2",
    factory_name="round1_ash_deep_l2_engine_config",
    factory=round1_ash_deep_l2_engine_config,
    label="Round-1 Phase-L L2 — split outer (2.5/4.5/7)",
    purpose=(
        "Middle ground between K2 (2.5/4/6) and J2 (2.5/5/8). "
        "Hypothesis: if the optimum is between K2 and J2 on the "
        "outer-edge axis, L2 wins. Local +3 482 (vs K2 +3 497)."
    ),
    inline=InlineSpec(
        strategy_module_path="src/strategies/ash_ladder.py",
        strategy_class_name="AshLadderStrategy",
        params_class_name="LadderParams",
        new_strategy_name="ash_ladder",
        params_dict={
            "edges": (2.5, 4.5, 7.0),
            "size_mults": (1.0, 1.5, 2.0),
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
