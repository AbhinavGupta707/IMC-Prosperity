"""Aggregate metrics for a backtest run.

Phase 2A scope: the simulator needs somewhere structured to store
per-product PnL, trade counts, and final positions. The full metrics
catalogue required by the plan (markouts, maker/taker decomposition,
time near limits) lands in Phase 2B and Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProductResult:
    product: str
    pnl: float
    cash: float
    final_position: int
    mark_price: float | None
    order_count: int
    trade_count: int
    buy_trade_quantity: int
    sell_trade_quantity: int


@dataclass(frozen=True)
class SimulationResult:
    steps: int
    total_pnl: float
    per_product: dict[str, ProductResult] = field(default_factory=dict)

    def summary_table(self) -> str:
        header = (
            f"{'product':<10} {'pnl':>12} {'cash':>12} {'pos':>6} "
            f"{'mark':>10} {'trades':>8} {'buy_q':>7} {'sell_q':>8}"
        )
        lines = [header, "-" * len(header)]
        for product in sorted(self.per_product):
            r = self.per_product[product]
            mark = f"{r.mark_price:.2f}" if r.mark_price is not None else "   n/a"
            lines.append(
                f"{product:<10} {r.pnl:>12.2f} {r.cash:>12.2f} {r.final_position:>6d} "
                f"{mark:>10} {r.trade_count:>8d} {r.buy_trade_quantity:>7d} "
                f"{r.sell_trade_quantity:>8d}"
            )
        lines.append("-" * len(header))
        lines.append(f"{'TOTAL':<10} {self.total_pnl:>12.2f}")
        return "\n".join(lines)
