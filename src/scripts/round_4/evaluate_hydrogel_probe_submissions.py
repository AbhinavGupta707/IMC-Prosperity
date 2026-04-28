"""Evaluate Round 4 HYDROGEL probe submissions in isolation.

This is a fast sanity harness for upload-calibration candidates. It imports
standalone submission files, filters their output to HYDROGEL_PACK, and replays:

* the three historical 1M R4 days;
* the first 100k of each historical day;
* one official 100k log path, using non-SUBMISSION market trades only.

The official-log replay is an approximation of fills, not a replacement for an
official upload. Its job is to prevent obviously broken probes from being sent.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from src.backtest.fill_model import FillModel, FillModelConfig
from src.backtest.replay_engine import ReplayEngine, ReplayStep
from src.backtest.simulator import BacktestSimulator
from src.core.config_core import EngineConfig, ProductConfig
from src.datamodel import Trade


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
OFFICIAL_LOG = REPO_ROOT / "r4 Sim Results" / "extracted" / "hydrogel_only" / "493452.log"
OUT_DIR = REPO_ROOT / "outputs" / "round_4" / "hydrogel_probes"
PRODUCT = "HYDROGEL_PACK"
LIMIT = 200


DEFAULT_CANDIDATES = {
    "baseline_hydonly": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_diag_hydrogel_only.py",
    "baseline_flat995": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_safer_hydflat995.py",
    "probe_hydonly_flat95k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hydonly_flat95k.py",
    "probe_width28_flat995": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_width28_flat995.py",
    "probe_width28_flat990": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_width28_flat990.py",
    "probe_highregime_cap40_60k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_cap40_60k.py",
    "probe_highregime_cap80_60k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_cap80_60k.py",
    "probe_highregime_noshort_60k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_noshort_60k.py",
    "probe_highregime_noshort_50k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_noshort_50k.py",
    "probe_highregime_hardflat_60k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_hardflat_60k.py",
    "probe_highregime_hardlong40_60k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_hardlong40_60k.py",
    "probe_highregime_hardlong80_60k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_hardlong80_60k.py",
    "probe_highregime_hardlong40_bid10052_70k": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_highregime_hardlong40_bid10052_70k.py",
    "probe_slopegate15_cap40_flat60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_slopegate15_cap40_flat60.py",
    "probe_slopegate15_cap40_long40_60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_slopegate15_cap40_long40_60.py",
    "probe_slopegate18_cap80_flat60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_probe_hyd_slopegate18_cap80_flat60.py",
    "final_sell7_abortgate15_flat60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate15_flat60.py",
    "final_sell7_abortgate15_long20_60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate15_long20_60.py",
    "final_sell7_abortgate15_long40_60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate15_long40_60.py",
    "final_sell7_abortgate18_flat60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate18_flat60.py",
    "final_sell7_abortgate18_long40_60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate18_long40_60.py",
    "final_sell7_abortgate18_long80_60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate18_long80_60.py",
    "final_sell7_abortgate18_long120_60": REPO_ROOT / "outputs" / "submissions" / "r4" / "submission_r4_final_sell7_hyd_abortgate18_long120_60.py",
}


@dataclass(frozen=True)
class ReplayCase:
    name: str
    replay: ReplayEngine


class SubmissionHydAdapter:
    def __init__(self, trader_cls: type) -> None:
        self._inner = trader_cls()
        self.config = EngineConfig(
            products={
                PRODUCT: ProductConfig(
                    position_limit=LIMIT,
                    strategy_name="market_making",
                    fair_value_method="anchor",
                    anchor_price=9988.0,
                )
            }
        )

    def run(self, state):
        orders, conversions, trader_data = self._inner.run(state)
        hyd_orders = list((orders or {}).get(PRODUCT, []))
        return {PRODUCT: hyd_orders}, conversions, trader_data


def load_trader(path: Path) -> type:
    module_name = "r4_hyd_probe_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.Trader


def historical_replay(day: int | None, *, end_ts: int | None = None) -> ReplayEngine:
    days: list[int]
    if day is None:
        days = [1, 2, 3]
    else:
        days = [day]
    steps: list[ReplayStep] = []
    for d in days:
        replay = ReplayEngine.from_files(
            price_paths=[DATA_DIR / f"prices_round_4_day_{d}.csv"],
            trade_paths=[DATA_DIR / f"trades_round_4_day_{d}.csv"],
        )
        for step in replay.iter_steps():
            if end_ts is not None and step.timestamp > end_ts:
                continue
            if PRODUCT not in step.rows_by_product:
                continue
            steps.append(
                ReplayStep(
                    day=step.day,
                    timestamp=step.timestamp,
                    rows_by_product={PRODUCT: step.rows_by_product[PRODUCT]},
                    market_trades={PRODUCT: step.market_trades.get(PRODUCT, [])},
                )
            )
    return ReplayEngine(steps)


def official_log_replay(path: Path) -> ReplayEngine:
    payload = json.loads(path.read_text())
    rows_by_ts: dict[int, dict[str, str]] = {}
    reader = csv.DictReader(io.StringIO(payload["activitiesLog"]), delimiter=";")
    for row in reader:
        if row.get("product") != PRODUCT:
            continue
        rows_by_ts[int(row["timestamp"])] = row

    trades_by_ts: dict[int, list[Trade]] = {}
    for row in payload.get("tradeHistory", []):
        if row.get("symbol") != PRODUCT:
            continue
        if row.get("buyer") == "SUBMISSION" or row.get("seller") == "SUBMISSION":
            continue
        ts = int(row["timestamp"])
        trades_by_ts.setdefault(ts, []).append(
            Trade(
                symbol=PRODUCT,
                price=int(float(row["price"])),
                quantity=int(float(row["quantity"])),
                buyer=row.get("buyer"),
                seller=row.get("seller"),
                timestamp=ts,
            )
        )

    steps = [
        ReplayStep(
            day=0,
            timestamp=ts,
            rows_by_product={PRODUCT: rows_by_ts[ts]},
            market_trades={PRODUCT: trades_by_ts.get(ts, [])},
        )
        for ts in sorted(rows_by_ts)
    ]
    return ReplayEngine(steps)


def replay_cases() -> list[ReplayCase]:
    cases = [
        ReplayCase("hist_all_1m", historical_replay(None)),
        ReplayCase("hist_first100k_all", historical_replay(None, end_ts=99_900)),
        ReplayCase("official100k_log_replay", official_log_replay(OFFICIAL_LOG)),
    ]
    for day in (1, 2, 3):
        cases.append(ReplayCase(f"hist_day_{day}_1m", historical_replay(day)))
        cases.append(ReplayCase(f"hist_day_{day}_first100k", historical_replay(day, end_ts=99_900)))
    return cases


def max_drawdown(values: list[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        peak = value if peak is None else max(peak, value)
        worst = min(worst, value - peak)
    return worst


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = replay_cases()
    rows: list[dict[str, object]] = []
    fill_model = FillModel(FillModelConfig(passive_allocation=0.3, passive_fills_enabled=True))

    for candidate, path in DEFAULT_CANDIDATES.items():
        trader_cls = load_trader(path)
        for case in cases:
            result = BacktestSimulator(SubmissionHydAdapter(trader_cls), fill_model).run(case.replay)
            product = result.per_product.get(PRODUCT)
            if product is None:
                continue
            pnl_values = [value for _, value in result.pnl_series.get(PRODUCT, ())]
            rows.append(
                {
                    "candidate": candidate,
                    "path": str(path),
                    "case": case.name,
                    "pnl": round(product.pnl, 2),
                    "cash": round(product.cash, 2),
                    "terminal_mark_component": round(
                        product.final_position * (product.mark_price or 0.0), 2
                    ),
                    "final_pos": product.final_position,
                    "mark_price": product.mark_price,
                    "trade_count": product.trade_count,
                    "taker_qty": product.taker_trade_quantity,
                    "maker_qty": product.maker_trade_quantity,
                    "buy_qty": product.buy_trade_quantity,
                    "sell_qty": product.sell_trade_quantity,
                    "min_pnl": round(min(pnl_values), 2) if pnl_values else "",
                    "peak_pnl": round(max(pnl_values), 2) if pnl_values else "",
                    "max_drawdown": round(max_drawdown(pnl_values), 2),
                }
            )

    fieldnames = list(rows[0].keys()) if rows else []
    out_path = out_dir / "probe_local_summary.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
