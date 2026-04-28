"""Smoke replay stack-based Mark55 interposition probes.

This is a runtime check only. Local exact-price replay is not the official
inside-quote fill model, so treat PnL as a sanity screen rather than proof.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/tmp/imc-r4-counterparty-audit/data/raw/round_4")
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"

R4_POSITION_LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in (4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500)},
}


@dataclass
class _ProductCfg:
    position_limit: int


@dataclass
class _EngineCfg:
    products: dict[str, _ProductCfg] = field(default_factory=dict)


def _stub_config() -> _EngineCfg:
    return _EngineCfg({p: _ProductCfg(limit) for p, limit in R4_POSITION_LIMITS.items()})


def load_trader(path: Path, name: str):
    src_dir = str(REPO_ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    trader = module.Trader()
    trader.config = _stub_config()
    return trader


def replay(path: Path, name: str, data_dir: Path, days: list[int]) -> dict[str, object]:
    from src.backtest.replay_engine import ReplayEngine
    from src.backtest.simulator import BacktestSimulator

    price_paths = [data_dir / f"prices_round_4_day_{day}.csv" for day in days]
    trade_paths = [data_dir / f"trades_round_4_day_{day}.csv" for day in days]
    trader = load_trader(path, name)
    result = BacktestSimulator(trader=trader).run(
        ReplayEngine.from_files(price_paths=price_paths, trade_paths=trade_paths)
    )
    velvet = result.per_product.get("VELVETFRUIT_EXTRACT")
    return {
        "name": name,
        "file": path.name,
        "total_pnl": round(float(result.total_pnl), 2),
        "velvet_pnl": round(float(velvet.pnl), 2) if velvet else 0.0,
        "velvet_pos": int(velvet.final_position) if velvet else 0,
        "velvet_qty": int(velvet.taker_trade_quantity + velvet.maker_trade_quantity) if velvet else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--days", type=int, nargs="+", default=[3])
    parser.add_argument("--lite", action="store_true", help="smoke the size-safe lite upload set")
    args = parser.parse_args()

    if args.lite:
        files = [
            ("base", SUB_DIR / "submission_r4_exp_stack_hydhardlong80_60k.py"),
            ("bidonly", SUB_DIR / "submission_r4_lite_stack80_m55_interpose_bidonly_markgate_s1.py"),
            ("periodic", SUB_DIR / "submission_r4_lite_stack80_m55_interpose_periodic_s1_control.py"),
            ("markgate", SUB_DIR / "submission_r4_lite_stack80_m55_interpose_markgate_s1_twosided.py"),
            ("always", SUB_DIR / "submission_r4_lite_stack80_m55_interpose_always_s1_control.py"),
            ("askonly", SUB_DIR / "submission_r4_lite_stack80_m55_interpose_askonly_markgate_s1.py"),
        ]
    else:
        files = [
            ("base", SUB_DIR / "submission_r4_final_stack_hydabort18l80_nomark_control.py"),
            ("markgate", SUB_DIR / "submission_r4_final_stack_hydabort18l80_m55_interpose_markgate_s1.py"),
            ("periodic", SUB_DIR / "submission_r4_final_stack_hydabort18l80_m55_interpose_periodic_s1.py"),
            ("always", SUB_DIR / "submission_r4_final_stack_hydabort18l80_m55_interpose_always_s1.py"),
            ("bidonly", SUB_DIR / "submission_r4_final_stack_hydabort18l80_m55_interpose_bidonly_markgate_s1.py"),
            ("askonly", SUB_DIR / "submission_r4_final_stack_hydabort18l80_m55_interpose_askonly_markgate_s1.py"),
        ]
    rows = []
    for label, path in files:
        row = replay(path, f"r4_m55_stack_{label}", args.data_dir, args.days)
        rows.append(row)
        print(row)
    base = float(rows[0]["total_pnl"])
    print("deltas_vs_base")
    for row in rows[1:]:
        print(row["name"], round(float(row["total_pnl"]) - base, 2))


if __name__ == "__main__":
    main()
