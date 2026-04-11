"""Phase 6 — EMERALDS cross-slice parameter sweep.

Runs the EMERALDS four-axis sweep (``maker_edge × taker_edge ×
inventory_skew × flatten_threshold``) across three tutorial slices
(``day_-2``, ``day_-1``, combined), intersects the plateau bands via
``src.backtest.plateau.intersect_plateaus``, and prints the verdict
plus per-slice incumbent baseline block.

Heatmaps are rendered per slice as a diagnostic but are
**non-blocking** — the script still writes the core
``plateau_intersection.{json,txt}`` artifacts if the renderer
trips. See the Phase 6 plan (``Tutorial/Implementation Plan.md:649``)
and the robustness note (``docs/phase_6_robustness_note.md``) for
context.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.parameter_sweep import (
    ParameterSweepReport,
    build_parameter_sweep_report,
)
from src.backtest.plateau import (
    intersect_plateaus,
    write_phase6_cross_slice_report,
)
from src.backtest.plateau_charts import render_plateau_heatmaps
from src.backtest.replay_engine import ReplayEngine

_TUTORIAL_DIR = Path("data/raw/tutorial_round_1")
_PRODUCT = "EMERALDS"
_SUB_SWEEP_NAME = "emeralds"
_ROLE = "promotion_eligible"

_EMERALDS_GRID: dict[str, list[object]] = {
    # ``maker_edge`` spans principled tick-margins (1..3) through the
    # tutorial-tape "trade-bearing" prices at 9992/10008 (= edge 8).
    # Phase 2C reverted EMERALDS maker_edge from 8 -> 2 because edge=8
    # was chasing a known simulation artifact: the tutorial trade tape
    # only prints at 9992/10000/10008, so inside-spread quotes get
    # zero passive-fill credit. Phase 6's job is to surface that cliff
    # explicitly so the robustness note can rule on it through the
    # six-part promotion gate (gate 5+6 manual checks catch artifact
    # mechanisms even when sweep-level numbers look attractive).
    "maker_edge": [1.0, 2.0, 3.0, 4.0, 6.0, 8.0],
    "taker_edge": [1.0, 2.0],
    "inventory_skew": [1.5, 2.0, 2.5, 3.0],
    "flatten_threshold": [0.65, 0.70, 0.75, 0.80],
}

_HEATMAP_X = "maker_edge"
_HEATMAP_Y = "inventory_skew"

_SLICES: dict[str, tuple[list[Path], list[Path]]] = {
    "day_-2": (
        [_TUTORIAL_DIR / "prices_round_0_day_-2.csv"],
        [_TUTORIAL_DIR / "trades_round_0_day_-2.csv"],
    ),
    "day_-1": (
        [_TUTORIAL_DIR / "prices_round_0_day_-1.csv"],
        [_TUTORIAL_DIR / "trades_round_0_day_-1.csv"],
    ),
    "combined": (
        [
            _TUTORIAL_DIR / "prices_round_0_day_-2.csv",
            _TUTORIAL_DIR / "prices_round_0_day_-1.csv",
        ],
        [
            _TUTORIAL_DIR / "trades_round_0_day_-2.csv",
            _TUTORIAL_DIR / "trades_round_0_day_-1.csv",
        ],
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 EMERALDS cross-slice parameter sweep"
    )
    parser.add_argument("--label", default="phase6_emeralds", help="run label")
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="skip heatmap rendering (plateau logic still runs)",
    )
    args = parser.parse_args()

    per_slice_reports = _run_slices(args.label)

    cross_slice = intersect_plateaus(
        per_slice_reports,
        product=_PRODUCT,
        sub_sweep=_SUB_SWEEP_NAME,
        role=_ROLE,
        run_label=args.label,
    )

    run_id = _resolve_run_id(args.label, product=_PRODUCT)
    sub_sweep_dir = write_phase6_cross_slice_report(
        cross_slice,
        per_slice_reports,
        run_id=run_id,
    )

    if not args.no_charts:
        _render_heatmaps(per_slice_reports, sub_sweep_dir)

    print(f"Wrote Phase 6 EMERALDS artifacts to {sub_sweep_dir}")
    print()
    print(cross_slice.summary_text())


def _run_slices(label: str) -> dict[str, ParameterSweepReport]:
    reports: dict[str, ParameterSweepReport] = {}
    for slice_name, (price_paths, trade_paths) in _SLICES.items():
        if not all(path.exists() for path in price_paths):
            raise SystemExit(
                f"Tutorial price files missing for slice {slice_name!r}; "
                f"expected under {_TUTORIAL_DIR}"
            )
        replay = ReplayEngine.from_files(
            price_paths=price_paths,
            trade_paths=trade_paths,
        )
        reports[slice_name] = build_parameter_sweep_report(
            replay,
            product=_PRODUCT,
            grid=_EMERALDS_GRID,
            run_label=f"{label}_{_SUB_SWEEP_NAME}_{slice_name}",
        )
    return reports


def _render_heatmaps(
    per_slice_reports: dict[str, ParameterSweepReport],
    sub_sweep_dir: Path,
) -> None:
    heatmap_dir = sub_sweep_dir / "heatmaps"
    for slice_name, report in per_slice_reports.items():
        try:
            render_plateau_heatmaps(
                report,
                x_axis=_HEATMAP_X,
                y_axis=_HEATMAP_Y,
                slice_name=slice_name,
                out_dir=heatmap_dir,
            )
        except Exception as exc:  # noqa: BLE001
            # Heatmaps are non-blocking per the Phase 6 plan.
            print(
                f"[phase6 emeralds] heatmap render failed for {slice_name}: {exc}; "
                "continuing (plateau artifacts still written)"
            )


def _resolve_run_id(label: str, *, product: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    clean = "".join(
        char if char.isalnum() or char in "-_" else "_"
        for char in f"{label}_{product.lower()}"
    )
    return f"{stamp}_{clean}" if clean else stamp


if __name__ == "__main__":
    main()
