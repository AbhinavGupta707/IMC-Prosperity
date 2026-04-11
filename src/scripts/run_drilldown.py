"""Run Phase 4b drilldowns on top of an existing Phase 4a review pack.

Reads an ``outputs/review_packs/<run_id>/`` directory, selects one or
more drilldown cases by CLI flag, rebuilds a local window of book
context from the manifest's CSVs, and writes per-case artifacts
under ``outputs/review_packs/<run_id>/drilldowns/<case_id>/``.

Selection modes may be combined in one invocation — e.g.
``--best-trades 3 --worst-trades 3`` produces six cases in a single
run. When no selection flag is passed the script exits with a
non-zero status and an explanation.

This tool never mutates the source pack. Drilldowns live under the
pack's own ``drilldowns/`` subdirectory so provenance stays
self-contained: given a run id you can navigate to every case
generated against it without touching the pack's top-level files.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from src.backtest.drilldown import (
    DEFAULT_RANK_METRIC,
    DEFAULT_WINDOW_RADIUS,
    DrilldownCase,
    DrilldownError,
    ReviewPack,
    build_case_window,
    load_review_pack,
    select_best_trades,
    select_by_timestamp,
    select_by_trade_id,
    select_near_limit,
    select_worst_trades,
)
from src.backtest.drilldown_writer import (
    update_drilldowns_index,
    write_case_artifacts,
)

_RANK_METRIC_CHOICES = ["edge", "markout_1", "markout_5", "markout_20"]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    pack_dir = Path(args.pack)
    if not pack_dir.is_dir():
        parser.error(f"--pack must point at a directory: {pack_dir}")

    pack = load_review_pack(pack_dir)
    cases = _collect_cases(pack, args)
    if not cases:
        parser.error(
            "no drilldown selection flags provided; pass at least one of "
            "--trade-id, --timestamp, --best-trades, --worst-trades, "
            "--near-limit"
        )

    out_root = pack_dir / "drilldowns"
    out_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for case in cases:
            window = build_case_window(case, pack, window_radius=args.window)
            case_dir = write_case_artifacts(
                case,
                window,
                out_dir=out_root,
                pack=pack,
                render_charts=not args.no_charts,
            )
            written.append(case_dir)
            print(
                f"  [{case.kind}] {case.case_id}  "
                f"(window {window.start_timestamp}..{window.end_timestamp}, "
                f"{len(window.trades_in_window)} trades, "
                f"{len(window.book_snapshots)} book snaps)"
            )
    except DrilldownError as exc:
        # Surface manifest / book-rebuild errors without a Python traceback.
        print(f"drilldown error: {exc}", file=sys.stderr)
        return 2

    index_path = update_drilldowns_index(out_root, pack=pack, cases=cases)

    print()
    print(f"Wrote {len(written)} drilldown case(s) under {out_root}")
    print(f"Updated index: {index_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 4b drilldown generator for review packs",
    )
    parser.add_argument(
        "--pack",
        required=True,
        help="path to a Phase 4a review pack directory",
    )
    parser.add_argument(
        "--trade-id",
        type=int,
        default=None,
        help="index into trades.json (0-based) to drill into",
    )
    parser.add_argument(
        "--timestamp",
        type=int,
        default=None,
        help="timestamp to anchor a drilldown on (requires --product)",
    )
    parser.add_argument(
        "--product",
        default=None,
        help="product symbol, required when using --timestamp",
    )
    parser.add_argument(
        "--day",
        type=int,
        default=None,
        help="optional day disambiguator for --timestamp on combined multi-day packs",
    )
    parser.add_argument(
        "--best-trades",
        type=int,
        default=0,
        help="number of best trades to drill into (ranked by --rank-metric)",
    )
    parser.add_argument(
        "--worst-trades",
        type=int,
        default=0,
        help="number of worst trades to drill into (ranked by --rank-metric)",
    )
    parser.add_argument(
        "--near-limit",
        action="store_true",
        help="emit drilldowns for the most extreme near-position-limit steps",
    )
    parser.add_argument(
        "--near-limit-count",
        type=int,
        default=3,
        help="how many near-limit cases to emit when --near-limit is set",
    )
    parser.add_argument(
        "--rank-metric",
        choices=_RANK_METRIC_CHOICES,
        default=DEFAULT_RANK_METRIC,
        help="per-trade score used for --best-trades / --worst-trades",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_WINDOW_RADIUS,
        help="window radius in steps around the anchor (default 30)",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="skip chart rendering; still writes summary/window/notes",
    )
    return parser


def _collect_cases(pack: ReviewPack, args: argparse.Namespace) -> list[DrilldownCase]:
    cases: list[DrilldownCase] = []

    if args.trade_id is not None:
        cases.append(select_by_trade_id(pack, args.trade_id))

    if args.timestamp is not None:
        if not args.product:
            raise SystemExit("--timestamp requires --product PRODUCT (e.g. --product TOMATOES)")
        cases.append(select_by_timestamp(pack, args.product, args.timestamp, args.day))

    if args.best_trades > 0:
        cases.extend(select_best_trades(pack, args.best_trades, args.rank_metric))

    if args.worst_trades > 0:
        cases.extend(select_worst_trades(pack, args.worst_trades, args.rank_metric))

    if args.near_limit:
        cases.extend(select_near_limit(pack, args.near_limit_count))

    return _dedupe(cases)


def _dedupe(cases: Iterable[DrilldownCase]) -> list[DrilldownCase]:
    """Drop duplicate case ids while preserving order.

    Combining ``--best-trades N --trade-id K`` could pick the same
    fill twice; we keep only the first occurrence so we don't
    overwrite an already-written case directory mid-run.
    """
    seen: set[str] = set()
    unique: list[DrilldownCase] = []
    for case in cases:
        if case.case_id in seen:
            continue
        seen.add(case.case_id)
        unique.append(case)
    return unique


if __name__ == "__main__":
    sys.exit(main())
