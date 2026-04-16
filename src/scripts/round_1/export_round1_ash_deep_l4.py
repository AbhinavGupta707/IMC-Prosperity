"""Export L4 — Phase-L K2 4-level extension (2.5/4/6/8, weights 3/1/1/1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import round1_ash_deep_l4_engine_config
from src.scripts.round_1._ash_deep_bundle import (
    DEFAULT_OUT_DIR,
    AshDeepBundleSpec,
    InlineSpec,
    export_bundle,
)

_SPEC = AshDeepBundleSpec(
    variant="ash_deep_l4",
    factory_name="round1_ash_deep_l4_engine_config",
    factory=round1_ash_deep_l4_engine_config,
    label="Round-1 Phase-L L4 — 4-level tight K2 extension",
    purpose=(
        "K2 plus a 4th outer level at d=8. Weights 3/1/1/1 = "
        "inner 50%, outers 16.7% each. Phase-K showed K3 with "
        "d=12 failed due to dilution; L4 keeps the 4th level at "
        "a more reachable depth (d=8). Local +3 535 — **best of "
        "Phase-L**, with 48 maker fills (vs K2's 26). Highest "
        "upside candidate."
    ),
    inline=InlineSpec(
        strategy_module_path="src/strategies/ash_ladder.py",
        strategy_class_name="AshLadderStrategy",
        params_class_name="LadderParams",
        new_strategy_name="ash_ladder",
        params_dict={
            "edges": (2.5, 4.0, 6.0, 8.0),
            "size_mults": (1.0, 1.5, 2.0, 3.0),
            "skew_coef": 2.0,
            "flatten_threshold": 0.7,
            "weights": (3, 1, 1, 1),
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
