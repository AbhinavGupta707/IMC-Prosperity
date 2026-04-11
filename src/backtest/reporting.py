"""Review pack generation and persistence.

Every non-trivial backtest run produces a review pack: a structured
JSON summary under ``outputs/review_packs/<run_id>/summary.json`` plus
the plain-text table the simulator emits. This lets every strategy
change be reviewed against the same artifact shape.

Phase 2B scope: summary metrics only. Phase 4 adds charts, timestamp
drilldowns, and markouts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.backtest.metrics import ProductResult, SimulationResult

_DEFAULT_REVIEW_DIR = Path("outputs/review_packs")


def build_review_pack(result: SimulationResult, *, run_label: str = "") -> dict[str, Any]:
    return {
        "run_label": run_label,
        "generated_at": datetime.now(UTC).isoformat(),
        "steps": result.steps,
        "total_pnl": result.total_pnl,
        "per_product": {product: _product_to_dict(r) for product, r in result.per_product.items()},
    }


def write_review_pack(
    result: SimulationResult,
    *,
    run_label: str = "",
    base_dir: Path | str = _DEFAULT_REVIEW_DIR,
) -> Path:
    """Persist a review pack to disk and return the directory it was written to."""
    run_id = _run_id(run_label)
    directory = Path(base_dir) / run_id
    directory.mkdir(parents=True, exist_ok=True)

    pack = build_review_pack(result, run_label=run_label)
    (directory / "summary.json").write_text(json.dumps(pack, indent=2, sort_keys=True))
    (directory / "summary.txt").write_text(result.summary_table() + "\n")
    return directory


def _product_to_dict(r: ProductResult) -> dict[str, Any]:
    return {
        "pnl": r.pnl,
        "cash": r.cash,
        "final_position": r.final_position,
        "mark_price": r.mark_price,
        "order_count": r.order_count,
        "trade_count": r.trade_count,
        "taker_trade_count": r.taker_trade_count,
        "maker_trade_count": r.maker_trade_count,
        "taker_trade_quantity": r.taker_trade_quantity,
        "maker_trade_quantity": r.maker_trade_quantity,
        "buy_trade_quantity": r.buy_trade_quantity,
        "sell_trade_quantity": r.sell_trade_quantity,
        "steps_near_limit": r.steps_near_limit,
    }


def _run_id(run_label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if run_label:
        clean = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_label)
        return f"{stamp}_{clean}"
    return stamp
