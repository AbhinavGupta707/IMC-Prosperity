"""5-minute pre-MC sanity check: rank FV estimators by MAE.

Runs after calibration; before the full cohort MC. Whichever estimator
has the lowest MAE vs recovered server FV is the strategy's
recommended FV foundation. Use this to gate which strategy candidates
even get sent to MC.

Usage:

    PYTHONPATH=. .venv/bin/python -m src.scripts.calibration.run_fv_mae_check \\
        --hold1-log "outputs/round_1/official_results/tutorial/round 1 trader/206432.json" \\
        --out outputs/calibration/fv_mae_check
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.analysis.calibration.extract_fv import (
    build_fact_table, extract_book_records, load_activity_log,
)
from src.analysis.calibration.fv_estimator_mae import (
    render_score_markdown, score_estimators,
)

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold1-log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--anchor", type=float, default=None,
        help=(
            "Optional anchor value for a constant-FV estimator (useful "
            "for products like EMERALDS where the FV is pinned to a "
            "known integer e.g. 10000)"
        ),
    )
    parser.add_argument(
        "--weighted-window", type=int, default=5,
        help="Rolling window for weighted_mid estimator (default 5)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args.out.mkdir(parents=True, exist_ok=True)

    payload = load_activity_log(args.hold1_log)
    book_records = extract_book_records(payload)
    facts_by_product = build_fact_table(book_records, mode="hold_one")

    summary_lines: list[str] = ["# FV estimator MAE — all products", ""]
    for product in sorted(facts_by_product):
        facts = facts_by_product[product]
        LOGGER.info("=== %s: scoring %d ticks ===", product, len(facts))
        scores = score_estimators(
            facts,
            weighted_mid_window=args.weighted_window,
            anchor_value=args.anchor,
        )
        per_product_md = render_score_markdown(scores)
        # Replace top-line title with product name.
        product_md = per_product_md.replace(
            "# FV estimator MAE ranking",
            f"## {product}",
        )
        summary_lines.append(product_md)
        summary_lines.append("")

        # Per-product file too.
        product_path = args.out / f"fv_mae_{product.lower()}.md"
        product_path.write_text(per_product_md.replace(
            "# FV estimator MAE ranking",
            f"# {product} — FV estimator MAE ranking",
        ))
        LOGGER.info("Wrote %s", product_path)

        # Console summary.
        print()
        print(f"=== {product} ===")
        for s in scores[:3]:
            print(f"  #{scores.index(s) + 1} {s.name:25s} MAE={s.mae:.4f} "
                  f"bias={s.bias:+.4f} (n={s.n_evaluated})")

    summary_path = args.out / "fv_mae_summary.md"
    summary_path.write_text("\n".join(summary_lines))
    LOGGER.info("Wrote %s", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
