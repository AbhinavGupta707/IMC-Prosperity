"""Audit overfit risk for the current R4 final-spine candidates.

The official simulator gives a 100k unseen slice, but the final round scores
1M ticks. This script replays candidate submissions over the three public R4
1M days and writes coarse PnL, inventory, drawdown, and bucket summaries.

Local replay is not the official simulator. Treat these outputs as
distributional sanity checks, not leaderboard estimates.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "final_spine_overfit_audit"

HYD = "HYDROGEL_PACK"
VELVET = "VELVETFRUIT_EXTRACT"
VOUCHERS = tuple(
    f"VEV_{strike}"
    for strike in (4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500)
)
VELVET_COMPLEX = (VELVET, *VOUCHERS)

R4_POSITION_LIMITS = {
    HYD: 200,
    VELVET: 200,
    **{product: 300 for product in VOUCHERS},
}


@dataclass(frozen=True)
class Candidate:
    label: str
    path: Path
    note: str


@dataclass
class _ProductCfg:
    position_limit: int


@dataclass
class _EngineCfg:
    products: dict[str, _ProductCfg] = field(default_factory=dict)


def _stub_config() -> _EngineCfg:
    return _EngineCfg({p: _ProductCfg(limit) for p, limit in R4_POSITION_LIMITS.items()})


def default_candidates() -> list[Candidate]:
    return [
        Candidate(
            "sell7_validated",
            SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_validated.py",
            "R4 TTE=4 validated/static sell7 baseline",
        ),
        Candidate(
            "probe_stack",
            SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_stack_officialmax_probe.py",
            "VELVET/options probe_stack on old HYD",
        ),
        Candidate(
            "sell7_abort80",
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long80_60.py",
            "HYD abortgate18_long80_60 on sell7",
        ),
        Candidate(
            "combo_probe_stack_abort80",
            SUB_DIR / "submission_r4_final_probe_stack_hyd_abortgate18_long80_60.py",
            "desired combo: probe_stack + HYD abortgate18_long80_60",
        ),
        Candidate(
            "stack_hardlong80",
            SUB_DIR / "submission_r4_exp_stack_hydhardlong80_60k.py",
            "uploaded expstack8060: probe_stack + ungated hardlong80",
        ),
    ]


def load_trader(path: Path, module_name: str):
    src_dir = str(REPO_ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load submission module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    trader = module.Trader()
    trader.config = _stub_config()
    return trader


def total_pnl_series(result) -> list[tuple[int, float]]:
    totals: dict[int, float] = defaultdict(float)
    for series in result.pnl_series.values():
        for timestamp, pnl in series:
            totals[int(timestamp)] += float(pnl)
    return sorted(totals.items())


def point_at_or_before(series: list[tuple[int, float]], timestamp: int) -> float:
    value = 0.0
    for ts, pnl in series:
        if ts > timestamp:
            break
        value = pnl
    return value


def max_drawdown(series: list[tuple[int, float]]) -> tuple[float, int, int]:
    if not series:
        return 0.0, 0, 0
    peak = series[0][1]
    peak_ts = series[0][0]
    worst_dd = 0.0
    worst_peak_ts = peak_ts
    worst_trough_ts = peak_ts
    for ts, pnl in series:
        if pnl > peak:
            peak = pnl
            peak_ts = ts
        dd = pnl - peak
        if dd < worst_dd:
            worst_dd = dd
            worst_peak_ts = peak_ts
            worst_trough_ts = ts
    return worst_dd, worst_peak_ts, worst_trough_ts


def product_pnl(result, products: tuple[str, ...]) -> float:
    return sum(float(result.per_product[p].pnl) for p in products if p in result.per_product)


def group_position_abs(result, products: tuple[str, ...]) -> int:
    return sum(abs(int(result.per_product[p].final_position)) for p in products if p in result.per_product)


def product_terminal_component(result, product: str) -> float:
    row = result.per_product.get(product)
    if row is None or row.mark_price is None:
        return 0.0
    return float(row.final_position) * float(row.mark_price)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_audit(candidates: list[Candidate], data_dir: Path, days: list[int], out_dir: Path) -> None:
    from src.backtest.replay_engine import ReplayEngine
    from src.backtest.simulator import BacktestSimulator

    out_dir.mkdir(parents=True, exist_ok=True)
    full_rows: list[dict[str, object]] = []
    product_rows: list[dict[str, object]] = []
    bucket_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []

    for candidate in candidates:
        if not candidate.path.exists():
            raise FileNotFoundError(candidate.path)
        for day in days:
            print(f"replay {candidate.label} day {day}", flush=True)
            price_path = data_dir / f"prices_round_4_day_{day}.csv"
            trade_path = data_dir / f"trades_round_4_day_{day}.csv"
            replay = ReplayEngine.from_files(price_paths=[price_path], trade_paths=[trade_path])
            trader = load_trader(candidate.path, f"audit_{candidate.label}_d{day}")
            result = BacktestSimulator(trader=trader).run(replay)
            series = total_pnl_series(result)
            dd, dd_peak_ts, dd_trough_ts = max_drawdown(series)
            final_ts = series[-1][0] if series else 0

            full_rows.append(
                {
                    "candidate": candidate.label,
                    "day": day,
                    "note": candidate.note,
                    "total_pnl": round(float(result.total_pnl), 2),
                    "prefix_100k_pnl": round(point_at_or_before(series, 100_000), 2),
                    "hyd_pnl": round(product_pnl(result, (HYD,)), 2),
                    "velvet_complex_pnl": round(product_pnl(result, VELVET_COMPLEX), 2),
                    "max_drawdown": round(dd, 2),
                    "drawdown_peak_ts": dd_peak_ts,
                    "drawdown_trough_ts": dd_trough_ts,
                    "final_ts": final_ts,
                    "hyd_pos": int(result.per_product.get(HYD).final_position)
                    if HYD in result.per_product
                    else 0,
                    "velvet_pos": int(result.per_product.get(VELVET).final_position)
                    if VELVET in result.per_product
                    else 0,
                    "voucher_abs_pos": group_position_abs(result, VOUCHERS),
                    "hyd_terminal_component": round(product_terminal_component(result, HYD), 2),
                    "velvet_terminal_component": round(product_terminal_component(result, VELVET), 2),
                    "trade_records": len(result.trade_records),
                }
            )

            for product, row in sorted(result.per_product.items()):
                product_rows.append(
                    {
                        "candidate": candidate.label,
                        "day": day,
                        "product": product,
                        "pnl": round(float(row.pnl), 2),
                        "cash": round(float(row.cash), 2),
                        "terminal_component": round(
                            float(row.final_position) * float(row.mark_price or 0.0), 2
                        ),
                        "final_position": int(row.final_position),
                        "mark_price": round(float(row.mark_price or 0.0), 2),
                        "trade_count": int(row.trade_count),
                        "taker_qty": int(row.taker_trade_quantity),
                        "maker_qty": int(row.maker_trade_quantity),
                        "buy_qty": int(row.buy_trade_quantity),
                        "sell_qty": int(row.sell_trade_quantity),
                        "steps_near_limit": int(row.steps_near_limit),
                        "avg_entry_edge": ""
                        if row.avg_entry_edge is None
                        else round(float(row.avg_entry_edge), 4),
                        "avg_markout_20": ""
                        if row.avg_markout_20 is None
                        else round(float(row.avg_markout_20), 4),
                    }
                )

            for start in range(0, 1_000_000, 100_000):
                end = min(start + 100_000, final_ts)
                start_pnl = point_at_or_before(series, start)
                end_pnl = point_at_or_before(series, end)
                bucket_rows.append(
                    {
                        "candidate": candidate.label,
                        "day": day,
                        "bucket_start": start,
                        "bucket_end": end,
                        "pnl_start": round(start_pnl, 2),
                        "pnl_end": round(end_pnl, 2),
                        "delta": round(end_pnl - start_pnl, 2),
                    }
                )

            grouped: dict[tuple[int, str, str], dict[str, int]] = defaultdict(
                lambda: {"rows": 0, "qty": 0}
            )
            for trade in result.trade_records:
                bucket = int(trade.fill_timestamp // 100_000) * 100_000
                key = (bucket, trade.product, trade.side)
                grouped[key]["rows"] += 1
                grouped[key]["qty"] += int(trade.quantity)
            for (bucket, product, side), agg in sorted(grouped.items()):
                trade_rows.append(
                    {
                        "candidate": candidate.label,
                        "day": day,
                        "bucket_start": bucket,
                        "product": product,
                        "side": side,
                        "rows": agg["rows"],
                        "qty": agg["qty"],
                    }
                )

    write_csv(out_dir / "full_day_summary.csv", full_rows)
    write_csv(out_dir / "product_summary.csv", product_rows)
    write_csv(out_dir / "bucket_summary.csv", bucket_rows)
    write_csv(out_dir / "trade_activity_100k.csv", trade_rows)
    write_report(out_dir, full_rows, bucket_rows)


def write_report(
    out_dir: Path,
    full_rows: list[dict[str, object]],
    bucket_rows: list[dict[str, object]],
) -> None:
    labels = sorted({str(row["candidate"]) for row in full_rows})
    lines = [
        "# Final Spine Overfit Audit",
        "",
        "Local replay over R4 public 1M days. This is a distributional check, not an official fill estimate.",
        "",
        "## Full-Day Summary",
        "",
        "| candidate | day | total | first_100k | HYD | VELVET_complex | max_DD | HYD_pos | VELVET_pos | voucher_abs_pos |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in full_rows:
        lines.append(
            "| {candidate} | {day} | {total_pnl} | {prefix_100k_pnl} | {hyd_pnl} | "
            "{velvet_complex_pnl} | {max_drawdown} | {hyd_pos} | {velvet_pos} | {voucher_abs_pos} |".format(
                **row
            )
        )

    lines.extend(["", "## Bucket Deltas", ""])
    for label in labels:
        lines.extend(
            [
                f"### {label}",
                "",
                "| day | 0-100k | 100-200k | 200-300k | 300-400k | 400-500k | 500-600k | 600-700k | 700-800k | 800-900k | 900-1000k |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        by_day: dict[int, list[float]] = defaultdict(list)
        for row in bucket_rows:
            if row["candidate"] == label:
                by_day[int(row["day"])].append(float(row["delta"]))
        for day in sorted(by_day):
            deltas = by_day[day]
            lines.append("| " + str(day) + " | " + " | ".join(f"{x:.0f}" for x in deltas) + " |")
        lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--days", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument(
        "--candidate",
        action="append",
        metavar="LABEL=PATH",
        help="Override candidates. Can be repeated.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.candidate:
        candidates = []
        for item in args.candidate:
            label, raw_path = item.split("=", 1)
            candidates.append(Candidate(label, Path(raw_path), "manual override"))
    else:
        candidates = default_candidates()
    run_audit(candidates, args.data_dir, args.days, args.out_dir)
    print(f"wrote {args.out_dir}", flush=True)


if __name__ == "__main__":
    main()
