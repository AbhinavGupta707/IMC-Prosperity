"""Smoke-test the paired Mark22 recycle submissions (treatment + control).

Loads both submission files, replays them on R4 historical days 1-3, and
prints PnL summaries side-by-side against the validated baseline.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/Users/abhinavgupta/Desktop/IMC-r4-counterparty/data/raw/round_4")

R4_POSITION_LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in (4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500)},
}


def _stub_engine_cfg():
    from dataclasses import dataclass, field

    @dataclass
    class _ProductCfg:
        position_limit: int

    @dataclass
    class _EngineCfg:
        products: dict[str, _ProductCfg] = field(default_factory=dict)

    return _EngineCfg(
        products={p: _ProductCfg(position_limit=lim) for p, lim in R4_POSITION_LIMITS.items()}
    )


def load_trader(path: Path, name: str):
    src_dir = str(REPO_ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    trader = mod.Trader()
    trader.config = _stub_engine_cfg()
    return trader


def replay_one(path: Path, name: str, data_dir: Path, days: Iterable[int]) -> dict:
    from src.backtest.replay_engine import ReplayEngine
    from src.backtest.simulator import BacktestSimulator

    trader = load_trader(path, name)
    price_paths = [data_dir / f"prices_round_4_day_{d}.csv" for d in days]
    trade_paths = [data_dir / f"trades_round_4_day_{d}.csv" for d in days]
    replay = ReplayEngine.from_files(price_paths=price_paths, trade_paths=trade_paths)
    sim = BacktestSimulator(trader=trader)
    res = sim.run(replay)
    return {
        "name": name,
        "total_pnl": round(float(res.total_pnl), 2),
        "per_product": {
            p: {
                "pnl": round(float(v.pnl), 2),
                "final_position": int(v.final_position),
                "qty": int(v.taker_trade_quantity + v.maker_trade_quantity),
            }
            for p, v in res.per_product.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--days", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()

    files = [
        ("validated", REPO_ROOT / "outputs/submissions/r4/submission_r4_exp_flat995_vev5500_sell7_validated.py"),
        ("treatment", REPO_ROOT / "outputs/submissions/r4/submission_r4_probe_m22sell_recycle_treatment.py"),
        ("control", REPO_ROOT / "outputs/submissions/r4/submission_r4_probe_m22sell_recycle_control.py"),
    ]
    data_dir = Path(args.data_dir)
    print(f"Replaying days {args.days} from {data_dir}")
    results = []
    for label, path in files:
        try:
            res = replay_one(path, f"r4_smoke_{label}", data_dir, args.days)
        except Exception as exc:
            print(f"FAIL {label}: {type(exc).__name__}: {exc}")
            raise
        results.append((label, res))
        print(f"\n=== {label} (file={path.name}) ===")
        print(f"total_pnl: {res['total_pnl']}")
        for prod in (
            "HYDROGEL_PACK",
            "VELVETFRUIT_EXTRACT",
            "VEV_5000",
            "VEV_5100",
            "VEV_5200",
            "VEV_5500",
        ):
            v = res["per_product"].get(prod)
            if not v:
                continue
            print(f"  {prod}: pnl={v['pnl']} pos={v['final_position']} qty={v['qty']}")

    if len(results) >= 2:
        base = results[0][1]["total_pnl"]
        print("\n=== Deltas vs validated ===")
        for label, res in results[1:]:
            delta = res["total_pnl"] - base
            for prod in ("VEV_5000", "VEV_5100", "VELVETFRUIT_EXTRACT"):
                pv = res["per_product"].get(prod, {})
                bv = results[0][1]["per_product"].get(prod, {})
                if pv and bv:
                    pdiff = pv.get("pnl", 0.0) - bv.get("pnl", 0.0)
                    print(f"  {label} -> {prod}: pnl_delta={pdiff:+.2f}, pos={pv.get('final_position', 'n/a')}")
            print(f"  {label} -> total_delta={delta:+.2f}")


if __name__ == "__main__":
    main()
