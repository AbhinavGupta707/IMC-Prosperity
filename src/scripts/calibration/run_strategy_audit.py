"""Audit a strategy against ground-truth server FV.

Loads a submission .py, replays it tick-by-tick against the recovered
server FV from a hold-1 trader log, and produces a verdict:

  - Per-quote edge (quote price vs true FV at quote time)
  - Per-fill markouts (FV move at h={1,5,20,50} ticks after fill)
  - Realized PnL (cash + position * last FV)
  - Aggregate "is this strategy structurally catching mispricing?"

Output: ``<out>/{quote_scores.csv, summary.md}``

Usage:

    PYTHONPATH=. .venv/bin/python -m src.scripts.calibration.run_strategy_audit \\
        --strategy outputs/submissions/round_1/limit_80/trader_round1_ash_deep_f3a.py \\
        --hold1-log "outputs/round_1/official_results/tutorial/round 1 trader/206432.json" \\
        --trades-csv data/raw/round_1/trades_round_1_day_0.csv \\
        --product ASH_COATED_OSMIUM \\
        --out outputs/calibration/f3a_retrospective
"""
from __future__ import annotations

import argparse
import csv
import logging
from collections.abc import Sequence
from pathlib import Path

from src.analysis.calibration.extract_fv import (
    build_fact_table, extract_book_records, load_activity_log,
    load_trades_csv,
)
from src.analysis.calibration.strategy_replay import (
    QuoteScore, ReplayResult, load_trader_class, replay_strategy,
)
from src.analysis.calibration.types import FactRow, TradeRow

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument(
        "--hold1-log", type=Path, required=True,
        help="Activity log JSON from a hold-1 submission for the same day",
    )
    parser.add_argument(
        "--trades-csv", type=Path, action="append", required=True,
        help="Market trades CSV for the same day (passive-fill model input)",
    )
    parser.add_argument(
        "--product", action="append", required=True,
        help="Product symbol(s) to audit (may be passed multiple times)",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args.out.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Loading hold-1 activity log: %s", args.hold1_log)
    payload = load_activity_log(args.hold1_log)
    book_records = extract_book_records(payload)
    facts_by_product = build_fact_table(book_records, mode="hold_one")

    facts: list[FactRow] = []
    for product in args.product:
        facts.extend(facts_by_product.get(product, []))
    if not facts:
        raise RuntimeError(
            f"No facts recovered for products {args.product} from {args.hold1_log}"
        )

    market_trades: list[TradeRow] = []
    for csv_path in args.trades_csv:
        market_trades.extend(load_trades_csv(csv_path))
    market_trades_by_ts: dict[int, list[dict]] = {}
    for tr in market_trades:
        market_trades_by_ts.setdefault(tr.timestamp, []).append({
            "product": tr.product, "price": tr.price, "quantity": tr.quantity,
        })

    LOGGER.info("Loading strategy: %s", args.strategy)
    trader_cls = load_trader_class(args.strategy)

    LOGGER.info("Replaying %d ticks across products %s", len(facts), args.product)
    results = replay_strategy(
        trader_factory=trader_cls,
        facts=facts,
        market_trades_by_ts=market_trades_by_ts,
        products=tuple(args.product),
    )

    _write_quote_scores_csv(results, args.out / "quote_scores.csv")
    _write_summary(
        results, args.out / "summary.md",
        strategy_path=args.strategy, hold1_log=args.hold1_log,
    )
    LOGGER.info("Wrote outputs to %s/", args.out)
    return 0


def _write_quote_scores_csv(
    results: dict[str, ReplayResult], out_path: Path,
) -> None:
    fields = [
        "timestamp", "product", "side", "quote_price", "quoted_qty",
        "server_fv", "edge_at_quote", "filled_qty", "fill_price",
        "markout_h1", "markout_h5", "markout_h20", "markout_h50",
    ]
    with out_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        for result in results.values():
            for s in result.quote_scores:
                writer.writerow([
                    s.timestamp, s.product, s.side, s.quote_price,
                    s.quoted_qty, s.server_fv, s.edge_at_quote,
                    s.filled_qty, s.fill_price,
                    s.markout_h1, s.markout_h5, s.markout_h20, s.markout_h50,
                ])


def _write_summary(
    results: dict[str, ReplayResult], out_path: Path,
    *, strategy_path: Path, hold1_log: Path,
) -> None:
    lines: list[str] = [
        f"# Strategy audit — `{strategy_path.name}`", "",
        f"- Strategy: `{strategy_path}`",
        f"- FV source: `{hold1_log}`", "",
    ]
    for product in sorted(results):
        r = results[product]
        lines.append(f"## {product}")
        lines.append("")
        lines.append(f"- Ticks replayed: **{r.n_ticks}**")
        lines.append(f"- Quotes emitted: **{r.n_quotes}**")
        lines.append(f"- Fills: **{r.n_fills}** "
                     f"({r.n_fills / max(r.n_quotes, 1):.1%})")
        lines.append(f"- Realized PnL (mark-to-FV): **{r.realized_pnl:+.2f}**")
        lines.append("")
        lines.append("### Edge capture")
        lines.append("")
        lines.append("| metric | value | interpretation |")
        lines.append("|---|---:|---|")
        for label, key in (
            ("Mean edge per quote", "mean_edge_per_quote"),
            ("Mean edge per fill", "mean_edge_per_fill"),
            ("Markout h=1 per fill", "mean_markout_h1_per_fill"),
            ("Markout h=5 per fill", "mean_markout_h5_per_fill"),
            ("Markout h=20 per fill", "mean_markout_h20_per_fill"),
            ("Markout h=50 per fill", "mean_markout_h50_per_fill"),
        ):
            v = r.edge_capture.get(key)
            if v is None:
                continue
            interp = _interpret(key, v)
            lines.append(f"| {label} | {v:+.4f} | {interp} |")
        lines.append("")
        lines.append("### Per-side breakdown")
        lines.append("")
        for side in ("bid", "ask"):
            scores = [s for s in r.quote_scores if s.side == side]
            fills = [s for s in scores if s.filled_qty > 0]
            if not scores:
                continue
            mean_edge = sum(s.edge_at_quote for s in scores) / len(scores)
            lines.append(f"**{side}**: n_quotes={len(scores)}, n_fills={len(fills)}, "
                         f"mean_edge={mean_edge:+.3f}")
            if fills:
                fills_edge = sum(s.edge_at_quote for s in fills) / len(fills)
                lines.append(f"  - fill mean_edge={fills_edge:+.3f}")
                for h_label, h_attr in (
                    ("h=1", "markout_h1"), ("h=5", "markout_h5"),
                    ("h=20", "markout_h20"), ("h=50", "markout_h50"),
                ):
                    valid = [getattr(s, h_attr) for s in fills
                             if getattr(s, h_attr) is not None]
                    if valid:
                        m = sum(valid) / len(valid)
                        lines.append(f"  - markout {h_label}: {m:+.3f}")
        lines.append("")
    out_path.write_text("\n".join(lines))


def _interpret(metric_key: str, value: float) -> str:
    if value > 0:
        return "favorable (quote on the profitable side of FV)"
    if value < 0:
        return "adverse (quote on the unfavorable side of FV)"
    return "neutral"


if __name__ == "__main__":
    raise SystemExit(main())
