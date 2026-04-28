"""Export HYD-abort + safer VELVET risk-ladder submissions.

These are final-portfolio alternatives to the max-EV `probe_stack` spine. They
start from the confirmed HYD `abortgate18_long80_60` base and wrap only the
VELVET schedule layer with the already-uploaded VELVET-only risk controls.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.scripts.round_4.export_velvet_regime_probe_uploads import (
    REPO_ROOT,
    SUB_DIR,
    VelvetUploadSpec,
    _append_wrapper,
)


BASE = SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long80_60.py"


def specs() -> list[VelvetUploadSpec]:
    return [
        VelvetUploadSpec(
            "final_plus80_hyd_abortgate18_long80_60",
            "one_shot",
            SUB_DIR
            / "submission_r4_final_velvet_plus80_hyd_abortgate18_long80_60.py",
            buy=5248,
            sell=5264,
            active_buy_limit=80,
            gate_ts=30_000,
            drop_ticks=20.0,
        ),
        VelvetUploadSpec(
            "final_delayed_hyd_abortgate18_long80_60",
            "one_shot",
            SUB_DIR
            / "submission_r4_final_velvet_delayed_hyd_abortgate18_long80_60.py",
            buy=5248,
            sell=5264,
            active_buy_limit=200,
            gate_ts=50_000,
            drop_ticks=20.0,
        ),
    ]


def export_one(spec: VelvetUploadSpec) -> Path:
    source = BASE.read_text(encoding="utf-8")
    spec.out.write_text(_append_wrapper(source, spec), encoding="utf-8")
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
