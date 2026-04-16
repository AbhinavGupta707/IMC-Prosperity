"""Export the balanced guarded-carry PEPPER bundle.

Candidate:
- best current balanced PEPPER unseen-data bundle
- `guard_negative_slope=0.01`
- `open_take_mode="level1_only"`
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.scripts.round_1._pepper_bundle import (
    PepperBundleSpec,
    export_pepper_bundle,
)
from src.strategies.pepper_core_long import CoreLongParams

SPEC = PepperBundleSpec(
    slug="pepper_guard01",
    label="Round-1 PEPPER guarded carry (balanced)",
    purpose=(
        "Current best balanced PEPPER candidate for unseen data. Keeps the "
        "near-buy-and-hold carry core, uses level-1-only opening acquisition, "
        "and caps the target at flat when 32-step drift slope falls below 0.01."
    ),
    expectation=(
        "Expect near-V3 real-day PEPPER carry with much better behavior on "
        "reversals and weaker negative-drift regimes."
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
