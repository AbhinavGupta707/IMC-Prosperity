"""Convert an IMC Prosperity simulator result into Kevin BT input CSVs.

The IMC simulator produces a JSON file (book snapshots in `activitiesLog`)
and a LOG file (full tradeHistory). Kevin Fu's `prosperity4bt` backtester
reads CSV files at `prosperity4bt/resources/round{N}/`. This script
converts one IMC result into the matching CSV pair so other strategies
can be replayed against the path you just submitted.

Usage:

    python -m src.scripts.imc_results_to_kevin_bt \
        --input  '/path/to/result_id'        # extension-stripped
        --round  4                            # round number
        --day    4                            # day number
        [--out-base external/kevin-bt/prosperity4bt/resources]

Reads `<input>.json` (activitiesLog) and `<input>.log` (tradeHistory),
writes `<out-base>/round{N}/prices_round_{N}_day_{D}.csv` and
`<out-base>/round{N}/trades_round_{N}_day_{D}.csv`. Trades from the
SUBMISSION participant are filtered so the strategy under test does
not see its own past fills.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def convert(
    input_stem: Path,
    round_num: int,
    day_num: int,
    out_base: Path,
) -> tuple[Path, Path]:
    json_path = input_stem.with_suffix(".json")
    log_path = input_stem.with_suffix(".log")
    if not json_path.is_file():
        raise FileNotFoundError(f"Missing IMC JSON: {json_path}")
    if not log_path.is_file():
        raise FileNotFoundError(f"Missing IMC log: {log_path}")

    out_dir = out_base / f"round{round_num}"
    out_dir.mkdir(parents=True, exist_ok=True)
    init_file = out_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    activities = json.loads(json_path.read_text())["activitiesLog"]
    lines = activities.strip().split("\n")
    prices_path = out_dir / f"prices_round_{round_num}_day_{day_num}.csv"
    prices_path.write_text("\n".join(lines) + "\n")

    log = json.loads(log_path.read_text())
    trade_history = log.get("tradeHistory", [])
    bot_trades = [
        t
        for t in trade_history
        if t.get("buyer") != "SUBMISSION" and t.get("seller") != "SUBMISSION"
    ]
    trades_path = out_dir / f"trades_round_{round_num}_day_{day_num}.csv"
    with trades_path.open("w") as f:
        f.write("timestamp;buyer;seller;symbol;currency;price;quantity\n")
        for t in bot_trades:
            f.write(
                f'{t["timestamp"]};{t["buyer"]};{t["seller"]};'
                f'{t["symbol"]};XIRECS;{t["price"]};{t["quantity"]}\n'
            )

    print(f"Wrote {prices_path} ({len(lines) - 1} price rows)")
    print(
        f"Wrote {trades_path} "
        f"({len(bot_trades)} bot-bot trades, {len(trade_history)} total)"
    )
    return prices_path, trades_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to IMC result, with extension stripped (script reads .json + .log)",
    )
    parser.add_argument("--round", dest="round_num", type=int, required=True)
    parser.add_argument("--day", dest="day_num", type=int, required=True)
    parser.add_argument(
        "--out-base",
        type=Path,
        default=Path("external/kevin-bt/prosperity4bt/resources"),
    )
    args = parser.parse_args()
    convert(args.input, args.round_num, args.day_num, args.out_base)


if __name__ == "__main__":
    main()
