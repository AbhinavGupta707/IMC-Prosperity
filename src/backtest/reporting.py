"""Review pack generation.

Phase 2A placeholder. Phase 2B will fill this out with summary metrics,
charts, and timestamp drilldowns per the plan's review protocol.
"""

from __future__ import annotations

from src.backtest.metrics import SimulationResult


def build_review_pack(result: SimulationResult) -> dict[str, object]:
    return {
        "steps": result.steps,
        "total_pnl": result.total_pnl,
        "per_product": {
            product: {
                "pnl": r.pnl,
                "cash": r.cash,
                "final_position": r.final_position,
                "mark_price": r.mark_price,
                "trade_count": r.trade_count,
                "order_count": r.order_count,
            }
            for product, r in result.per_product.items()
        },
    }
