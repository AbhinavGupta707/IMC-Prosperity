"""Stress R4 final-spine candidates on synthetic day splices.

This is a robustness diagnostic, not a leaderboard estimate. It stitches the
first 100k ticks from one public R4 day to the 100k-1M tail from another day,
then replays a small candidate set. The purpose is to test whether a candidate
that wins on an official-like prefix survives a different 1M tail.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from src.scripts.round_4.audit_final_spine_overfit import (
    Candidate,
    REPO_ROOT,
    SUB_DIR,
    run_audit,
)


DEFAULT_SOURCE_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "final_spine_splice_stress"
SPLIT_TS = 100_000


@dataclass(frozen=True)
class SpliceScenario:
    label: str
    synthetic_day: int
    prefix_day: int
    tail_day: int


SCENARIOS = [
    SpliceScenario("d3_prefix_d1_tail", 91, 3, 1),
    SpliceScenario("d3_prefix_d2_tail", 92, 3, 2),
    SpliceScenario("d1_prefix_d3_tail", 93, 1, 3),
    SpliceScenario("d2_prefix_d3_tail", 94, 2, 3),
]


def candidates() -> list[Candidate]:
    return [
        Candidate(
            "sell7_validated",
            SUB_DIR / "submission_r4_exp_flat995_vev5500_sell7_validated.py",
            "R4 TTE=4 sell7 baseline",
        ),
        Candidate(
            "sell7_abort80",
            SUB_DIR / "submission_r4_final_sell7_hyd_abortgate18_long80_60.py",
            "sell7 + HYD abortgate18_long80_60",
        ),
        Candidate(
            "combo_probe_stack_abort80",
            SUB_DIR / "submission_r4_final_probe_stack_hyd_abortgate18_long80_60.py",
            "probe_stack + HYD abortgate18_long80_60",
        ),
    ]


def _copy_price_segment(
    *,
    reader: csv.DictReader,
    writer: csv.DictWriter,
    synthetic_day: int,
    prefix: bool,
) -> None:
    for row in reader:
        ts = int(row["timestamp"])
        if prefix and ts >= SPLIT_TS:
            continue
        if not prefix and ts < SPLIT_TS:
            continue
        row["day"] = str(synthetic_day)
        writer.writerow(row)


def _copy_trade_segment(
    *,
    reader: csv.DictReader,
    writer: csv.DictWriter,
    prefix: bool,
) -> None:
    for row in reader:
        ts = int(row["timestamp"])
        if prefix and ts >= SPLIT_TS:
            continue
        if not prefix and ts < SPLIT_TS:
            continue
        writer.writerow(row)


def build_splice(source_dir: Path, synthetic_dir: Path, scenario: SpliceScenario) -> None:
    synthetic_dir.mkdir(parents=True, exist_ok=True)
    out_prices = synthetic_dir / f"prices_round_4_day_{scenario.synthetic_day}.csv"
    out_trades = synthetic_dir / f"trades_round_4_day_{scenario.synthetic_day}.csv"

    price_prefix = source_dir / f"prices_round_4_day_{scenario.prefix_day}.csv"
    price_tail = source_dir / f"prices_round_4_day_{scenario.tail_day}.csv"
    trade_prefix = source_dir / f"trades_round_4_day_{scenario.prefix_day}.csv"
    trade_tail = source_dir / f"trades_round_4_day_{scenario.tail_day}.csv"

    with price_prefix.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        fieldnames = reader.fieldnames or []
        with out_prices.open("w", newline="") as out_handle:
            writer = csv.DictWriter(out_handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            _copy_price_segment(
                reader=reader,
                writer=writer,
                synthetic_day=scenario.synthetic_day,
                prefix=True,
            )
            with price_tail.open(newline="") as tail_handle:
                tail_reader = csv.DictReader(tail_handle, delimiter=";")
                _copy_price_segment(
                    reader=tail_reader,
                    writer=writer,
                    synthetic_day=scenario.synthetic_day,
                    prefix=False,
                )

    with trade_prefix.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        fieldnames = reader.fieldnames or []
        with out_trades.open("w", newline="") as out_handle:
            writer = csv.DictWriter(out_handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            _copy_trade_segment(reader=reader, writer=writer, prefix=True)
            with trade_tail.open(newline="") as tail_handle:
                tail_reader = csv.DictReader(tail_handle, delimiter=";")
                _copy_trade_segment(reader=tail_reader, writer=writer, prefix=False)


def write_splice_report(out_dir: Path, scenarios: list[SpliceScenario]) -> None:
    rows: list[dict[str, str]] = []
    with (out_dir / "audit" / "full_day_summary.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows.extend(reader)

    by_day = {scenario.synthetic_day: scenario.label for scenario in scenarios}
    lines = [
        "# Final Spine Splice Stress",
        "",
        "Synthetic diagnostic: prefix <100k from one public day, tail >=100k from another.",
        "These paths contain artificial joins, so use them as stress tests only.",
        "",
        "| scenario | candidate | total | first_100k | HYD | VELVET_complex | max_DD | HYD_pos | VELVET_pos | voucher_abs_pos |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        scenario = by_day.get(int(row["day"]), row["day"])
        lines.append(
            "| {scenario} | {candidate} | {total_pnl} | {prefix_100k_pnl} | {hyd_pnl} | "
            "{velvet_complex_pnl} | {max_drawdown} | {hyd_pos} | {velvet_pos} | {voucher_abs_pos} |".format(
                scenario=scenario,
                **row,
            )
        )

    baseline = {
        (row["day"], row["candidate"]): float(row["total_pnl"])
        for row in rows
    }
    lines.extend(
        [
            "",
            "## Deltas vs sell7_validated",
            "",
            "| scenario | sell7_abort80 | combo_probe_stack_abort80 |",
            "|---|---:|---:|",
        ]
    )
    for scenario in scenarios:
        day = str(scenario.synthetic_day)
        base = baseline[(day, "sell7_validated")]
        abort_delta = baseline[(day, "sell7_abort80")] - base
        combo_delta = baseline[(day, "combo_probe_stack_abort80")] - base
        lines.append(
            f"| {scenario.label} | {abort_delta:.2f} | {combo_delta:.2f} |"
        )

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    synthetic_dir = args.out_dir / "synthetic_data"
    for scenario in SCENARIOS:
        print(
            f"build {scenario.label}: d{scenario.prefix_day}<100k + d{scenario.tail_day}>=100k",
            flush=True,
        )
        build_splice(args.source_dir, synthetic_dir, scenario)

    run_audit(
        candidates=candidates(),
        data_dir=synthetic_dir,
        days=[scenario.synthetic_day for scenario in SCENARIOS],
        out_dir=args.out_dir / "audit",
    )
    write_splice_report(args.out_dir, SCENARIOS)
    print(f"wrote {args.out_dir}", flush=True)


if __name__ == "__main__":
    main()
