"""Run a strategy across N synthetic Monte Carlo sessions.

End-to-end: load calibration data, build samplers, instantiate the
strategy via dynamic import, run N independent sessions with distinct
seeds, aggregate into distribution stats.

Output:
    <out>/per_session.csv   one row per session: seed, pnl, alpha, r2, ...
    <out>/report.md         human-readable distribution summary
    <out>/raw_results.json  every SessionResult serialized (large; for re-analysis)

Usage:

    PYTHONPATH=. .venv/bin/python -m src.scripts.calibration.run_monte_carlo \\
        --strategy outputs/submissions/round_1/limit_80/trader_round1_ash_deep_f3a.py \\
        --hold1-log "outputs/round_1/official_results/tutorial/round 1 trader/206432.json" \\
        --trades-csv data/raw/round_1/trades_round_1_day_0.csv \\
        --product ASH_COATED_OSMIUM --product INTARIAN_PEPPER_ROOT \\
        --n-sessions 100 \\
        --out outputs/calibration/mc_audit_f3a
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import logging
from pathlib import Path

from src.analysis.calibration.bot_sampler import BookSampler
from src.analysis.calibration.extract_fv import (
    build_fact_table, extract_book_records, load_activity_log,
    load_trades_csv,
)
from src.analysis.calibration.fair_value_fit import fit_fair_value_process
from src.analysis.calibration.fv_evolver import FVProcess
from src.analysis.calibration.generative_simulator import (
    SessionConfig, SessionResult, run_session,
)
from src.analysis.calibration.stability_metrics import (
    render_report_markdown, summarize_sessions,
)
from src.analysis.calibration.strategy_replay import load_trader_class
from src.analysis.calibration.trade_sampler import TradeSampler

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument("--hold1-log", type=Path, required=True)
    parser.add_argument(
        "--trades-csv", type=Path, action="append", required=True,
    )
    parser.add_argument(
        "--product", action="append", required=True,
        help="Product symbol(s) to include (may be passed multiple times)",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--n-sessions", type=int, default=100,
        help="Number of MC sessions per candidate (default 100)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help=(
            "Fast mode: 20 sessions, deterministic seeds. Sufficient "
            "to distinguish structural-vs-lucky candidates (the 50%% "
            "win-rate gap between F3a-class and wall_mid-class is "
            "loud enough at n=20). Use for day-2 quick triage; switch "
            "to default n=100 for the final memo."
        ),
    )
    parser.add_argument("--n-ticks", type=int, default=0,
                        help="0 = match real-data length per product")
    parser.add_argument("--base-seed", type=int, default=20260417)
    parser.add_argument(
        "--priority-mode", choices=("bot", "player", "split"),
        default="bot",
        help=(
            "Passive-fill queue priority. 'bot' (default): bots fill "
            "first at any price level. 'player': player passive fills "
            "first (test variant for matching-model bias diagnosis). "
            "'split': proportional by standing volume."
        ),
    )
    parser.add_argument("--position-limit", type=int, default=80)
    parser.add_argument(
        "--strategy-name", type=str, default=None,
        help="Display name (defaults to strategy file stem)",
    )
    args = parser.parse_args(argv)
    if args.fast:
        args.n_sessions = 20

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args.out.mkdir(parents=True, exist_ok=True)
    strategy_name = args.strategy_name or args.strategy.stem

    # 1. Load calibration data.
    LOGGER.info("Loading hold-1 log and trades CSV(s)")
    payload = load_activity_log(args.hold1_log)
    book_records = extract_book_records(payload)
    facts_by_product = build_fact_table(book_records, mode="hold_one")
    trades_all = []
    for csv_path in args.trades_csv:
        trades_all.extend(load_trades_csv(csv_path))

    # 2. Build samplers per product.
    fv_processes = {}
    book_samplers = {}
    trade_samplers = {}
    n_ticks_for_session = args.n_ticks
    for product in args.product:
        if product not in facts_by_product:
            raise RuntimeError(
                f"Product {product} not in hold-1 log (have: "
                f"{sorted(facts_by_product.keys())})"
            )
        facts = facts_by_product[product]
        product_trades = [t for t in trades_all if t.product == product]
        # Keep only trades within the calibration window (matches gate convention).
        max_ts = facts[-1].timestamp if facts else 0
        product_trades = [t for t in product_trades if t.timestamp <= max_ts]
        fv_fit = fit_fair_value_process(facts)
        fv_processes[product] = FVProcess.from_fit(fv_fit)
        book_samplers[product] = BookSampler(facts)
        trade_samplers[product] = TradeSampler(
            product=product, trades=product_trades, facts=facts,
        )
        if n_ticks_for_session == 0:
            n_ticks_for_session = len(facts)
        LOGGER.info(
            "  %s: sigma=%.4f drift=%+.4f n_facts=%d n_trades=%d",
            product, fv_fit.sigma, fv_fit.mean_return,
            len(facts), len(product_trades),
        )

    # 3. Load strategy.
    LOGGER.info("Loading strategy: %s", args.strategy)
    trader_cls = load_trader_class(args.strategy)

    # 4. Run N sessions.
    LOGGER.info(
        "Running %d sessions, n_ticks=%d, products=%s",
        args.n_sessions, n_ticks_for_session, args.product,
    )
    sessions: list[SessionResult] = []
    for i in range(args.n_sessions):
        seed = args.base_seed + i
        config = SessionConfig(
            products=tuple(args.product),
            n_ticks=n_ticks_for_session,
            fv_processes=fv_processes,
            book_samplers=book_samplers,
            trade_samplers=trade_samplers,
            position_limit=args.position_limit,
            seed=seed,
            priority_mode=args.priority_mode,
        )
        result = run_session(config, trader_factory=trader_cls)
        sessions.append(result)
        if (i + 1) % 10 == 0:
            LOGGER.info(
                "  session %d/%d done (last PnL=%+.0f)",
                i + 1, args.n_sessions, result.final_pnl,
            )

    # 5. Aggregate + emit outputs.
    report = summarize_sessions(sessions, strategy_name=strategy_name)
    md = render_report_markdown([report])
    (args.out / "report.md").write_text(md)
    LOGGER.info("Wrote %s", args.out / "report.md")

    _write_per_session_csv(args.out / "per_session.csv", sessions)
    LOGGER.info("Wrote %s", args.out / "per_session.csv")

    _write_raw_results_json(args.out / "raw_results.json", sessions)
    LOGGER.info("Wrote %s", args.out / "raw_results.json")

    # 6. Console summary.
    print()
    print(f"=== {strategy_name} — Monte Carlo summary ===")
    print(f"Sessions: {report.n_sessions}")
    print(f"PnL mean / median:   {report.pnl.mean:+.0f} / {report.pnl.median:+.0f}")
    print(f"PnL std / q05-q95:   {report.pnl.std:.0f} / [{report.pnl.q05:+.0f}, {report.pnl.q95:+.0f}]")
    print(f"Win rate (PnL > 0):  {report.win_rate:.1%}")
    print(f"Mean R^2:            {report.r2.mean:+.3f}")
    print(f"Mean alpha:          {report.alpha.mean:+.4f}")
    print(f"Worst seeds:         {report.worst_seeds}")
    print(f"Best seeds:          {report.best_seeds}")
    return 0


def _write_per_session_csv(path: Path, sessions: list[SessionResult]) -> None:
    fields = [
        "seed", "n_ticks", "final_pnl", "realized_alpha", "realized_r2",
        "realized_downside_dev", "n_fills_total", "n_orders_rejected_total",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        for s in sessions:
            writer.writerow([
                s.seed, s.n_ticks, f"{s.final_pnl:.4f}",
                f"{s.realized_alpha:.6f}", f"{s.realized_r2:.6f}",
                f"{s.realized_downside_dev:.6f}",
                sum(s.n_fills.values()),
                sum(s.n_orders_rejected_limit.values()),
            ])


def _write_raw_results_json(path: Path, sessions: list[SessionResult]) -> None:
    """Serialize SessionResults (without per-tick equity arrays — too large)."""
    payload = []
    for s in sessions:
        d = dataclasses.asdict(s)
        # Drop per-tick arrays to keep file size reasonable; re-runnable
        # if needed by re-running the MC with the same seed.
        d.pop("per_tick_equity", None)
        d.pop("per_tick_position", None)
        d.pop("per_tick_fv", None)
        payload.append(d)
    path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
