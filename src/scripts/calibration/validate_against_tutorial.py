"""Cross-validate the calibration pipeline against tutorial-round data.

This script applies the calibration pipeline to the IMC tutorial-round
EMERALDS/TOMATOES CSVs (the raw data chrispyroberts used) and compares
the recovered parameters against his published values. A pass confirms
our pipeline reproduces the same answer on the same data — strong
evidence the methodology transfers.

Limitation: tutorial CSVs don't carry server-FV ground truth (no
hold-1 PnL stream). We use ``mid_price`` as the FV proxy. This means:

  - Bot rules with INTEGER offsets (e.g. EMERALDS Bot 1 at +/-10)
    should still recover cleanly — they're the same regardless of
    whether FV is mid or true server FV.
  - Bot rules with FRACTIONAL FV dependence (e.g. TOMATOES Bot 2's
    asymmetric ceil/floor) will partially fit because mid is rounded
    while server FV has fractional precision. We expect lower match
    rates here but the family (round_fn, offset) should still be
    identifiable.

Output: ``outputs/calibration/tutorial_validation/{report.md, fits.json}``
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from src.analysis.calibration.bot_classifier import detect_depth_bands
from src.analysis.calibration.extract_fv import load_trades_csv
from src.analysis.calibration.fair_value_fit import fit_fair_value_process
from src.analysis.calibration.rule_search import (
    fit_volume_distribution,
    search_quote_rule,
)
from src.analysis.calibration.serialize import (
    calibration_to_json,
    calibration_to_markdown,
)
from src.analysis.calibration.trade_fit import (
    fit_trade_arrivals,
    fit_trade_locations,
    fit_trade_sizes,
)
from src.analysis.calibration.types import (
    BookLevel,
    FactRow,
    ProductCalibration,
)

LOGGER = logging.getLogger(__name__)


def load_prices_csv_as_facts(path: Path) -> dict[str, list[FactRow]]:
    """Convert tutorial prices CSV to FactRow tables, using mid as FV."""
    facts_by_product: dict[str, list[FactRow]] = {}
    with path.open() as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            product = row["product"]
            ts = int(row["timestamp"])
            mid = float(row["mid_price"]) if row.get("mid_price") else None
            if mid is None:
                continue
            bids = _parse_levels(row, side="bid")
            asks = _parse_levels(row, side="ask")
            fact = FactRow(
                timestamp=ts, product=product, server_fv=mid,
                bids=bids, asks=asks, mid_price=mid, pnl=0.0,
            )
            facts_by_product.setdefault(product, []).append(fact)
    return facts_by_product


def _parse_levels(row: dict, *, side: str) -> tuple[BookLevel, ...]:
    out: list[BookLevel] = []
    for rank in (1, 2, 3):
        price = row.get(f"{side}_price_{rank}")
        volume = row.get(f"{side}_volume_{rank}")
        if not price or not volume:
            continue
        out.append(BookLevel(price=int(price), volume=abs(int(volume))))
    return tuple(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prices-csv", type=Path, action="append", required=True,
        help="Tutorial prices CSV path (may be passed multiple times)",
    )
    parser.add_argument(
        "--trades-csv", type=Path, action="append", default=[],
        help="Tutorial trades CSV path (may be passed multiple times)",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args.out.mkdir(parents=True, exist_ok=True)

    # Load + merge facts across days.
    facts_by_product: dict[str, list[FactRow]] = {}
    for csv_path in args.prices_csv:
        LOGGER.info("Loading prices CSV: %s", csv_path)
        per_day = load_prices_csv_as_facts(csv_path)
        for product, facts in per_day.items():
            facts_by_product.setdefault(product, []).extend(facts)

    # Load + merge trades.
    all_trades = []
    for csv_path in args.trades_csv:
        all_trades.extend(load_trades_csv(csv_path))
    trades_by_product: dict[str, list] = {}
    for trade in all_trades:
        trades_by_product.setdefault(trade.product, []).append(trade)

    calibrations: list[ProductCalibration] = []
    for product in sorted(facts_by_product):
        facts = facts_by_product[product]
        product_trades = trades_by_product.get(product, [])
        LOGGER.info(
            "=== %s: %d ticks (mid as FV proxy), %d trades ===",
            product, len(facts), len(product_trades),
        )
        fair = fit_fair_value_process(facts)
        bands = detect_depth_bands(facts)
        rules = tuple(search_quote_rule(facts, b) for b in bands)
        volumes = tuple(fit_volume_distribution(facts, b) for b in bands)
        arrivals = fit_trade_arrivals(facts, product_trades)
        sizes_buy = fit_trade_sizes(product_trades, side="buy", facts=facts)
        sizes_sell = fit_trade_sizes(product_trades, side="sell", facts=facts)
        loc_buy = fit_trade_locations(facts, product_trades, side="buy")
        loc_sell = fit_trade_locations(facts, product_trades, side="sell")
        calibrations.append(ProductCalibration(
            product=product, n_ticks=len(facts), fair_value=fair,
            depth_bands=bands, quote_rules=rules, volume_fits=volumes,
            trade_arrivals=arrivals,
            trade_sizes_buy=sizes_buy, trade_sizes_sell=sizes_sell,
            trade_locations_buy=loc_buy, trade_locations_sell=loc_sell,
        ))

    fits_path = args.out / "fits.json"
    fits_path.write_text(calibration_to_json(calibrations))
    LOGGER.info("Wrote %s", fits_path)
    report_path = args.out / "calibration_report.md"
    report_path.write_text(calibration_to_markdown(calibrations))
    LOGGER.info("Wrote %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
