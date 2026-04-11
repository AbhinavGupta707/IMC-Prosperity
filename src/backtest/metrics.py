"""Aggregate metrics for a backtest run.

Phase 2B: per-product PnL / cash / position, maker vs taker
decomposition, time near position limit, final mark price, and the
raw order/trade counts. Markouts land in Phase 4.
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
    taker_trade_count: int
    maker_trade_count: int
    taker_trade_quantity: int
    maker_trade_quantity: int
    buy_trade_quantity: int
    sell_trade_quantity: int
    steps_near_limit: int


@dataclass(frozen=True)
class SimulationResult:
    steps: int
    total_pnl: float
    per_product: dict[str, ProductResult] = field(default_factory=dict)

    def summary_table(self) -> str:
        header = (
            f"{'product':<10} {'pnl':>10} {'cash':>12} {'pos':>4} "
            f"{'mark':>9} {'trades':>7} {'tk_q':>6} {'mk_q':>6} "
            f"{'buy_q':>6} {'sell_q':>7} {'near_lim':>9}"
        )
        lines = [header, "-" * len(header)]
        for product in sorted(self.per_product):
            r = self.per_product[product]
            mark = f"{r.mark_price:.2f}" if r.mark_price is not None else "   n/a"
            lines.append(
                f"{product:<10} {r.pnl:>10.2f} {r.cash:>12.2f} {r.final_position:>4d} "
                f"{mark:>9} {r.trade_count:>7d} {r.taker_trade_quantity:>6d} "
                f"{r.maker_trade_quantity:>6d} {r.buy_trade_quantity:>6d} "
                f"{r.sell_trade_quantity:>7d} {r.steps_near_limit:>9d}"
            )
        lines.append("-" * len(header))
        lines.append(f"{'TOTAL':<10} {self.total_pnl:>10.2f}")
        return "\n".join(lines)
