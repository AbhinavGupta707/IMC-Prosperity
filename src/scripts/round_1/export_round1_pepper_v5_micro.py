"""Export the PEPPER micro-overlay research bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.scripts.round_1._pepper_bundle import (
    PepperBundleSpec,
    export_pepper_bundle,
)
from src.strategies.pepper_core_long import CoreLongParams

SPEC = PepperBundleSpec(
    slug="pepper_v5_micro",
    label="Round-1 PEPPER guarded carry + micro timing overlay",
    purpose=(
        "Research PEPPER bundle built on the balanced 0.01 guarded-carry core "
        "with a tiny residual+imbalance timing overlay. This is the current "
        "best candidate for any incremental PEPPER alpha beyond the carry core."
    ),
    expectation=(
        "Expect slightly less real-day PEPPER carry than the balanced guarded "
        "bundle, but somewhat better behavior on flat / high-vol / late-reversal "
        "synthetic regimes."
    ),
    core_long_params=CoreLongParams(
        base_long=80,
        add_thresh=3.0,
        trim_thresh=8.0,
        add_gain=5.0,
        trim_gain=2.0,
        floor=0,
        ceiling=80,
        step=8,
        exec_style="taker",
        hybrid_threshold=2.0,
        maker_edge_offset=0.0,
        open_seed_size=65,
        open_window=500,
        open_no_short=True,
        open_take_mode="level1_only",
        guard_window=32,
        guard_negative_slope=0.01,
        guard_r2_min=0.0,
        guard_target=0,
        micro_residual_threshold=3.0,
        micro_imbalance_threshold=0.30,
        micro_add_size=2,
        micro_trim_size=2,
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    path = export_pepper_bundle(SPEC, out_dir=args.out_dir) if args.out_dir else export_pepper_bundle(SPEC)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
